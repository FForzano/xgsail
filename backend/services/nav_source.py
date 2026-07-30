"""Which upload's GPS is THE navigation track of a session.

A session can legitimately collect several ``gps`` streams: a boat tracker plus
one Apple Watch per crew member all record position for the same outing, and
``ingestion.find_or_create_session`` merges them into one session by boat and
time window (see ``docs/device-protocol.md`` §9). Physiological data stays
per-person, but navigation must be single-valued — the map, the GPX export, the
replay endpoints and the analysis pipeline have to agree on one track, and
before this module each of them independently took "the first one found" or
"the most recently uploaded", which is neither consistent between them nor
stable over time.

``sessions.primary_nav_upload_id`` records an explicit choice; when it is unset
(the common case) ``resolve_nav_upload`` ranks the candidates deterministically.
The ranking never depends on upload *recency*, so a later upload — a crew
member relaying their watch after the boat's tracker, say — cannot silently
swap the track out from under a session that has already been analysed.
"""

import logging
import uuid
from typing import Optional

from ..db.models.ingest import NAV_SENSOR_TYPES
from ..repositories import get_repos
from ..storage import BlobNotFound, get_blob_store

logger = logging.getLogger(__name__)

# A hole longer than this in the position series counts as a gap — long enough
# not to trip on ordinary jitter in a ~1 Hz feed, short enough that a wrist
# device losing sky for half a minute shows up.
GAP_THRESHOLD_S = 10.0


def nav_candidates(session_id: uuid.UUID) -> "list[tuple[object, object]]":
    """``(upload, gps_stream)`` for every upload of the session that actually
    carries a position track, best-first per ``_rank``.

    An upload with only physiological streams is not a candidate — that is
    precisely the case that used to break the analysis dispatch."""
    repos = get_repos()
    pairs = [
        (upload, stream)
        for stream, upload in repos.ingest.list_streams_with_uploads_for_session(session_id)
        if stream.sensor_type == "gps" and stream.data_ref
    ]
    categories = {u.id: device_category(u) for u, _ in pairs}
    return sorted(pairs, key=lambda p: _rank(p[0], p[1], categories))


def device_category(upload) -> Optional[str]:
    """``boat_tracker`` / ``wearable`` for the device behind an upload, or None
    for a manual import (which has no device)."""
    if upload.device_id is None:
        return None
    repos = get_repos()
    device = repos.devices.get(upload.device_id)
    if device is None:
        return None
    device_type = repos.devices.get_type(device.device_type_id)
    return getattr(device_type, "category", None)


def _rank(upload, stream, categories: dict) -> tuple:
    """Sort key, lower is better.

    1. a boat-mounted tracker beats a wearable — it is fixed to the hull, not
       swinging on a wrist;
    2. data attributed to the boat beats data attributed to a person;
    3. more points beats fewer (the first criterion that looks at the data
       rather than the hardware);
    4. older upload wins ties, so the answer is stable as more data arrives.
    """
    # Manual imports (no device, category None) sit with boat trackers: a GPX
    # someone uploaded for the boat is a boat track, not a wrist track.
    is_wearable = categories.get(upload.id) == "wearable"
    return (
        1 if is_wearable else 0,
        0 if upload.subject_type == "boat" else 1,
        -(stream.row_count or 0),
        upload.uploaded_at,
    )


def resolve_nav_upload(session_id: uuid.UUID) -> Optional[object]:
    """The upload whose streams represent this session's navigation, or None if
    no upload has a position track at all.

    An explicit ``primary_nav_upload_id`` wins, but only while it still names a
    candidate: if that upload lost its GPS (re-processed, replaced) we fall back
    to the ranking rather than reporting no track."""
    candidates = nav_candidates(session_id)
    if not candidates:
        return None
    session = get_repos().sessions.get(session_id)
    chosen_id = getattr(session, "primary_nav_upload_id", None)
    if chosen_id is not None:
        for upload, _ in candidates:
            if upload.id == chosen_id:
                return upload
        logger.info("session %s primary_nav_upload_id %s is no longer a candidate;"
                    " falling back to ranking", session_id, chosen_id)
    return candidates[0][0]


def resolve_nav_streams(session_id: uuid.UUID) -> "dict[str, object]":
    """The boat sensors of the resolved navigation upload, keyed by sensor type.

    ``imu``/``wind``/``pressure`` come from the same physical device as the
    track, so they follow it instead of being merged across uploads — mixing
    one device's heel with another's position would silently fabricate a boat
    state that never existed."""
    upload = resolve_nav_upload(session_id)
    if upload is None:
        return {}
    return {
        s.sensor_type: s
        for s in get_repos().ingest.list_streams(upload.id)
        if s.sensor_type in NAV_SENSOR_TYPES and s.data_ref
    }


def nav_stream(session_id: uuid.UUID, sensor_type: str = "gps") -> Optional[object]:
    """One boat sensor of the resolved navigation upload (default: the track)."""
    return resolve_nav_streams(session_id).get(sensor_type)


def _series_quality(data_ref: str) -> dict:
    """Read a candidate track and describe how good it looks: span, gaps.

    Reads the blob, so this is for the explicit "choose a source" screen only —
    never for a listing or a page load."""
    out = {"first_t": None, "last_t": None, "duration_s": None, "gap_count": None}
    try:
        points = get_blob_store().get_json(data_ref)
    except (BlobNotFound, ValueError):
        return out
    from ..routers._common import parse_point_t  # local: avoids a router import cycle

    stamps = sorted(t for t in (parse_point_t(p.get("t", "")) for p in points) if t)
    if not stamps:
        return out
    gaps = sum(1 for a, b in zip(stamps, stamps[1:])
               if (b - a).total_seconds() > GAP_THRESHOLD_S)
    return {
        "first_t": stamps[0],
        "last_t": stamps[-1],
        "duration_s": int((stamps[-1] - stamps[0]).total_seconds()),
        "gap_count": gaps,
    }


def candidate_payloads(session_id: uuid.UUID, *, with_quality: bool = False) -> list[dict]:
    """The candidate tracks with enough detail to pick between them.

    Returns ``[]`` when there is nothing to choose (zero or one candidate), so
    the UI can stay out of the way in the ordinary single-device case.

    ``with_quality`` adds the measured span and gap count, which means reading
    each candidate series out of object storage. Off by default so a page can
    ask the cheap question — "is there even a choice here?" — without paying for
    the answer to the expensive one.
    """
    candidates = nav_candidates(session_id)
    if len(candidates) < 2:
        return []
    from ..routers._common import user_summary  # local: avoids an import cycle

    repos = get_repos()
    session = repos.sessions.get(session_id)
    chosen_id = getattr(session, "primary_nav_upload_id", None)
    resolved = resolve_nav_upload(session_id)
    out = []
    for upload, stream in candidates:
        device = repos.devices.get(upload.device_id) if upload.device_id else None
        device_type = (repos.devices.get_type(device.device_type_id)
                       if device is not None else None)
        out.append({
            "session_upload_id": upload.id,
            "device": {
                "id": device.id,
                # User-given nickname if any; the UI falls back to type_name
                # ("SailFrames E1", "Apple Watch") when it's unset.
                "nickname": device.nickname,
                "category": getattr(device_type, "category", None),
                "type_name": getattr(device_type, "name", None),
            } if device is not None else None,
            "subject_type": upload.subject_type,
            "subject_user_id": upload.subject_user_id,
            "user": user_summary(upload.subject_user_id) if upload.subject_user_id else None,
            "row_count": stream.row_count,
            "sample_rate_hz": stream.sample_rate_hz,
            "uploaded_at": upload.uploaded_at,
            # True for the one explicitly chosen; is_resolved is what the app
            # actually reads today, which differs when no choice was ever made.
            "is_primary": chosen_id is not None and upload.id == chosen_id,
            "is_resolved": resolved is not None and upload.id == resolved.id,
            **(_series_quality(stream.data_ref) if with_quality else {}),
        })
    return out

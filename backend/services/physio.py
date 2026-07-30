"""Assembling one session's personal health data, per crew member.

The pieces live in four places — the upload says whose data it is and whether
they shared it, ``session_streams`` points at the series in object storage,
``session_physio_stats`` holds the aggregates, and the zone bounds are derived
from the subject's profile — so this module joins them once and the router stays
thin.

Everything here is permission-filtered through
``auth.session_physio_visible_to``: a caller only ever learns about the crew
members whose physiological data they are allowed to see. What comes back
carries the subject's *derived* zone bounds but never the profile inputs behind
them (age, resting rate), and ``user_summary`` is likewise a name-and-photo
projection.
"""

import uuid
from typing import Optional

from ..auth import session_physio_visible_to
from ..db.models.ingest import PHYSIO_SENSOR_TYPES
from ..repositories import get_repos
from ..storage import get_blob_store
from . import hr_zones as hr_zones_service


def visible_physio_streams(session, user) -> "list[tuple[object, object]]":
    """``(stream, upload)`` for the physiological streams ``user`` may see.

    The one place that decides this, shared by the health endpoint and by the
    generic stream/replay endpoints that must not leak the same data through a
    side door."""
    repos = get_repos()
    return [
        (stream, upload)
        for stream, upload in repos.ingest.list_streams_with_uploads_for_session(session.id)
        if stream.sensor_type in PHYSIO_SENSOR_TYPES
        and session_physio_visible_to(session, upload, user)
    ]


def is_physio_hidden(stream, upload, session, user) -> bool:
    """Should this stream be withheld from ``user``? False for anything that
    isn't physiological, so callers can use it as a blanket filter."""
    if stream.sensor_type not in PHYSIO_SENSOR_TYPES:
        return False
    return not session_physio_visible_to(session, upload, user)


def session_physio(session, user) -> list[dict]:
    """One entry per crew member whose health data ``user`` may see.

    Empty list — never an error — when there is nothing visible: a caller must
    not be able to tell "this session has no watch data" apart from "this
    session has data you aren't allowed to see".
    """
    from ..routers._common import user_summary  # local: avoids an import cycle

    repos = get_repos()
    stats_by_upload = repos.ingest.list_physio_stats_for_session(session.id)
    blob = get_blob_store()

    by_upload: dict[uuid.UUID, dict] = {}
    for stream, upload in visible_physio_streams(session, user):
        entry = by_upload.get(upload.id)
        if entry is None:
            stats = stats_by_upload.get(upload.id)
            entry = {
                "session_upload_id": upload.id,
                "subject_user_id": upload.subject_user_id,
                "user": (user_summary(upload.subject_user_id)
                         if upload.subject_user_id else None),
                "shared": bool(upload.physio_shared),
                "is_self": (user is not None
                            and upload.subject_user_id == user.id),
                "stats": stats.to_dict() if stats is not None else None,
                "hr_zones": _subject_zones(upload.subject_user_id, session),
                "streams": [],
            }
            by_upload[upload.id] = entry
        entry["streams"].append({
            "sensor_type": stream.sensor_type,
            "row_count": stream.row_count,
            "sample_rate_hz": stream.sample_rate_hz,
            "download_url": blob.download_ref(stream.data_ref),
        })

    # Stable order so the cards don't reshuffle between renders; the viewer's
    # own data first, since that's what they came for.
    return sorted(by_upload.values(),
                  key=lambda e: (not e["is_self"], str(e["subject_user_id"] or "")))


def _subject_zones(subject_user_id: Optional[uuid.UUID], session) -> Optional[dict]:
    """Heart-rate zones computed from the *subject's* profile, not the viewer's,
    and aged to the session date rather than today."""
    if subject_user_id is None:
        return None
    subject = get_repos().users.get_by_id(subject_user_id)
    if subject is None:
        return None
    on = session.started_at.date() if session.started_at else None
    return hr_zones_service.hr_zones(subject, on=on)


def physio_upload_or_none(session_id: uuid.UUID, upload_id: uuid.UUID):
    """The upload ``upload_id`` if it belongs to ``session_id`` and actually
    carries physiological data — the validation behind the sharing toggle."""
    repos = get_repos()
    upload = repos.ingest.get_upload(upload_id)
    if upload is None or upload.session_id != session_id:
        return None
    streams = repos.ingest.list_streams(upload_id)
    if not any(s.sensor_type in PHYSIO_SENSOR_TYPES for s in streams):
        return None
    return upload

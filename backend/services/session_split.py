"""Undoing an automatic session merge: pull one upload back out into its own
session.

``ingestion.find_or_create_session`` merges by boat and time window, which is
what makes two crew members recording the same outing land on one session
without either of them arranging it. That is right far more often than not —
but when it is wrong (two boats' outings back to back, a clock that was off,
two people who genuinely sailed separately) there has to be a way back, or the
merge is a one-way door.

Deliberately no worker dispatch here: this module only moves rows. The router
schedules the two re-analyses afterwards, the same split ``set_nav_source``
already makes between "do the write" and "background the work".
"""

import logging
import uuid
from typing import Optional

from ..repositories import get_repos
from . import ingestion

logger = logging.getLogger(__name__)


def _upload_window(repos, upload_id: uuid.UUID, fallback):
    """The span of an upload's streams, falling back to the source session's
    window for streams written before ``session_streams.first_t`` existed."""
    streams = repos.ingest.list_streams(upload_id)
    firsts = [s.first_t for s in streams if s.first_t is not None]
    lasts = [s.last_t for s in streams if s.last_t is not None]
    return (
        min(firsts) if firsts else fallback.started_at,
        max(lasts) if lasts else fallback.ended_at,
    )


def _still_contributes(repos, session_id: uuid.UUID, user_id: uuid.UUID,
                       exclude_upload_id: uuid.UUID) -> bool:
    """Whether the user has anything left on the session besides the upload
    being moved — another upload, a photo or a video they added."""
    for upload in repos.ingest.list_uploads(session_id=session_id):
        if upload.id != exclude_upload_id and upload.subject_user_id == user_id:
            return True
    if any(p.created_by == user_id for p in repos.sessions.list_photos(session_id)):
        return True
    if any(v.created_by == user_id for v in repos.sessions.list_videos(session_id)):
        return True
    return False


def detach_upload(session_id: uuid.UUID, upload_id: uuid.UUID, *,
                  user_id: uuid.UUID) -> dict:
    """Move ``upload_id`` off ``session_id`` and onto a session of its own.

    Returns ``{"session_id", "activity_id", "source_session_id"}``. Raises
    ``ValueError`` for the two states the caller must reject: an upload that
    is not on this session, and a session with nothing left to separate.
    """
    repos = get_repos()
    source = repos.sessions.get(session_id)
    upload = repos.ingest.get_upload(upload_id)
    if source is None or upload is None or upload.session_id != session_id:
        raise ValueError("Upload not found for this session")
    uploads = repos.ingest.list_uploads(session_id=session_id)
    if len(uploads) < 2:
        raise ValueError("Nothing to separate")

    subject_id = upload.subject_user_id or user_id
    win_start, win_end = _upload_window(repos, upload_id, source)

    # Where the detached track lands. A solo activity is the private wrapper
    # find_or_create_session mints for a standalone recording, so a fresh one
    # is the right home. Anything else — a club training, a race — is a real
    # shared event the boat took part in: moving the track into a private solo
    # activity would quietly pull it out of that event's replay and data
    # endpoints, which is not what "these were two different sessions" means.
    activity = repos.activities.get(source.activity_id)
    if activity is not None and activity.type != "solo":
        activity_id = activity.id
        repos.activities.extend_window(activity_id, win_start, win_end)
    else:
        activity_id = repos.activities.create({
            "type": "solo", "visibility": "private", "created_by": subject_id,
            "started_at": win_start, "ended_at": win_end,
        }).id

    # Neither the crew note nor the trim comes along: the note belongs to the
    # outing that was shared, and the trim bounds are epoch seconds calibrated
    # against a track this session no longer has.
    new_session = repos.sessions.create({
        "activity_id": activity_id, "boat_id": source.boat_id,
        "started_at": win_start, "ended_at": win_end, "status": "pending",
    })

    # session_streams and session_physio_stats are keyed on the upload, so they
    # follow it with no work here — that absence is deliberate, not an
    # oversight.
    repos.ingest.move_upload_to_session(upload_id, new_session.id)

    if source.primary_nav_upload_id == upload_id:
        # ON DELETE SET NULL does not fire on UPDATE, so re-parenting leaves
        # the source pointing at a track it no longer owns. resolve_nav_upload
        # degrades quietly (logs, falls back to the ranking), which is exactly
        # why this would otherwise go unnoticed. The explicit choice was about
        # THIS upload, so carry the intent across rather than dropping it.
        repos.sessions.update(session_id, {"primary_nav_upload_id": None})
        repos.sessions.update(new_session.id, {"primary_nav_upload_id": upload_id})

    ingestion.add_recorder_as_crew(repos, source.boat_id, new_session.id, subject_id)
    if not _still_contributes(repos, session_id, subject_id, upload_id):
        # They have just said they were not part of that outing; leaving them
        # crewed on it is the worse default. Reversible either way — the
        # self-add on POST /sessions/{id}/crew is open to anyone.
        repos.sessions.remove_crew(session_id, subject_id)

    repos.sessions.recompute_window(session_id)
    repos.sessions.rollup_status(session_id)
    repos.sessions.rollup_status(new_session.id)

    logger.info("detached upload %s from session %s into session %s",
                upload_id, session_id, new_session.id)
    return {
        "session_id": new_session.id,
        "activity_id": activity_id,
        "source_session_id": session_id,
    }

"""Manual import endpoints (``/api/imports``) — docs/api-project.md §3.

Flow: create (presigned URL) → client PUTs the file → complete (bind to
boat/activity/session, start processing) → poll status. Everything is scoped
to ``uploaded_by``.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_user, verify_csrf
from ..schemas import ImportCompleteModel, ImportCreateModel
from ..services import import_processing, ingestion
from ._common import blob, repos

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _require_own_import(import_id: uuid.UUID, user):
    row = repos.ingest.get_import(import_id)
    if row is None or (row.uploaded_by != user.id and not user.is_superadmin):
        raise HTTPException(404, "Import not found")
    return row


@router.post("", status_code=201)
def create_import(body: ImportCreateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.original_filename.strip():
        raise HTTPException(422, "original_filename is required")
    row = repos.ingest.create_import(uploaded_by=user.id,
                                     original_filename=body.original_filename.strip())
    raw_key = ingestion.import_raw_key(row.id, row.original_filename)
    repos.ingest.update_import(row.id, {"raw_ref": raw_key})
    return {
        "import_id": row.id,
        "upload_url": blob.upload_ref(raw_key, expiry=ingestion.UPLOAD_URL_EXPIRY_S),
    }


@router.post("/{import_id}/complete")
def complete_import(import_id: uuid.UUID, body: ImportCompleteModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    row = _require_own_import(import_id, user)
    if row.status != "pending":
        raise HTTPException(409, f"Import already {row.status}")
    if repos.boats.get(body.boat_id) is None:
        raise HTTPException(404, "Boat not found")
    # Boat owner/admin binds data to the boat; a crew member may import their
    # own wearable trace (subject_type=crew_member on themselves).
    is_manager = user.is_superadmin or repos.boats.is_member(
        body.boat_id, user.id, roles=["owner", "admin"])
    is_self_crew = body.subject_type == "crew_member" and body.subject_user_id == user.id
    if not (is_manager or is_self_crew):
        raise HTTPException(403, "Boat owner/admin required")
    if body.subject_type == "crew_member" and body.subject_user_id is None:
        raise HTTPException(422, "subject_user_id is required for crew_member imports")
    return import_processing.complete_import(
        row,
        boat_id=body.boat_id,
        activity_id=body.activity_id,
        session_id=body.session_id,
        subject_type=body.subject_type,
        subject_user_id=body.subject_user_id,
        started_at=body.started_at,
        user_id=user.id,
    )


@router.get("")
def list_imports(request: Request):
    user = require_user(request)
    return [r.to_dict() for r in repos.ingest.list_imports(user.id)]


@router.get("/{import_id}")
def get_import(import_id: uuid.UUID, request: Request):
    user = require_user(request)
    row = _require_own_import(import_id, user)
    d = row.to_dict()
    d["uploads"] = [u.to_dict() for u in repos.ingest.list_uploads(import_id=import_id)]
    return d

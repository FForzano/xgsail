"""Note-template endpoints (``/api/note-templates``) — per-user free-text
snippets for prefilling session crew notes (see routers/sessions.py's
``/notes`` endpoint). Always scoped to "my own templates": no sharing, no
club/group/boat link, owner-only edit/delete (mirrors posts.py's
author-only check)."""

import uuid

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_user, verify_csrf
from ..schemas import NoteTemplateCreateModel, NoteTemplateUpdateModel
from ._common import repos

router = APIRouter(prefix="/api/note-templates", tags=["note-templates"])


def _require_owned(template_id: uuid.UUID, user):
    template = repos.note_templates.get(template_id)
    if template is None:
        raise HTTPException(404, "Template not found")
    if template.user_id != user.id:
        raise HTTPException(403, "Only the owner can edit this template")
    return template


@router.get("")
def list_note_templates(request: Request):
    user = require_user(request)
    return [t.to_dict() for t in repos.note_templates.list_for_user(user.id)]


@router.post("")
def create_note_template(body: NoteTemplateCreateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    if not body.name.strip() or not body.body.strip():
        raise HTTPException(422, "name and body are required")
    return repos.note_templates.create(user.id, body.name, body.body).to_dict()


@router.patch("/{template_id}")
def update_note_template(template_id: uuid.UUID, body: NoteTemplateUpdateModel, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_owned(template_id, user)
    changes = body.model_dump(exclude_unset=True)
    updated = repos.note_templates.update(template_id, changes)
    return updated.to_dict()


@router.delete("/{template_id}")
def delete_note_template(template_id: uuid.UUID, request: Request):
    verify_csrf(request)
    user = require_user(request)
    _require_owned(template_id, user)
    repos.note_templates.delete(template_id)
    return {"ok": True}

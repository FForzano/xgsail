"""Tests that the rich-text sanitizer (`backend/richtext.py`) is actually
wired into the DTOs — every prose field sanitizes on write, blank input
collapses to ``None``, and ``exclude_unset`` semantics survive the
`AfterValidator`. Pure Pydantic model tests — no database, no FastAPI app.
"""

from backend.schemas.activity import ActivityWriteModel
from backend.schemas.boat import (
    BoatClassWriteModel,
    BoatNoteCreateModel,
    BoatNoteUpdateModel,
)
from backend.schemas.club import ClubWriteModel
from backend.schemas.group import GroupWriteModel
from backend.schemas.note_template import (
    NoteTemplateCreateModel,
    NoteTemplateUpdateModel,
)
from backend.schemas.post import PostCreateModel, PostUpdateModel
from backend.schemas.raceday import RaceDayWriteModel
from backend.schemas.regatta import RegattaWriteModel
from backend.schemas.session import SessionNotesModel

XSS = "<p>hi</p><script>alert(1)</script>"
TABLE = "<table><tbody><tr><td>x</td></tr></tbody></table>"
HEADING = "<h1>Title</h1><p>body</p>"


def test_club_description_neutralizes_script():
    model = ClubWriteModel(description=XSS)
    assert "<script" not in model.description
    assert "hi" in model.description


def test_group_description_neutralizes_script():
    model = GroupWriteModel(description=XSS)
    assert "<script" not in model.description


def test_activity_description_is_basic_tier():
    model = ActivityWriteModel(description=HEADING)
    assert "<h1>" not in model.description
    assert "Title" in model.description  # text survives, just unwrapped


def test_boat_class_description_is_basic_tier():
    model = BoatClassWriteModel(description=TABLE)
    assert "<table" not in model.description


def test_regatta_description_is_basic_tier():
    model = RegattaWriteModel(description=TABLE)
    assert "<table" not in model.description


def test_raceday_notes_is_basic_tier():
    model = RaceDayWriteModel(notes=HEADING)
    assert "<h1>" not in model.notes


def test_session_notes_full_tier_keeps_table_and_heading():
    model = SessionNotesModel(notes=TABLE)
    assert "<table" in model.notes
    model2 = SessionNotesModel(notes=HEADING)
    assert "<h1>" in model2.notes


def test_boat_note_body_full_tier_keeps_table():
    created = BoatNoteCreateModel(title="Setup", body=TABLE)
    assert "<table" in created.body
    updated = BoatNoteUpdateModel(body=HEADING)
    assert "<h1>" in updated.body


def test_note_template_body_matches_session_notes_tier():
    created = NoteTemplateCreateModel(name="Debrief", body=TABLE)
    assert "<table" in created.body
    updated = NoteTemplateUpdateModel(body=HEADING)
    assert "<h1>" in updated.body


def test_post_body_keeps_data_mention_but_strips_script():
    mention = '<p>hey <span data-mention="u1">@sailor</span></p><script>x</script>'
    created = PostCreateModel(owner_type="club", owner_id="00000000-0000-0000-0000-000000000001", body=mention)
    assert "data-mention" in created.body
    assert "<script" not in created.body
    updated = PostUpdateModel(body=mention)
    assert "data-mention" in updated.body


def test_club_description_strips_data_mention():
    mention = '<p>hey <span data-mention="u1">@sailor</span></p>'
    model = ClubWriteModel(description=mention)
    assert "data-mention" not in model.description
    assert "<span" not in model.description


def test_blank_input_becomes_none():
    for blank in ("", "   ", "<p></p>", "<p>   </p>"):
        assert ClubWriteModel(description=blank).description is None
        assert SessionNotesModel(notes=blank).notes is None


def test_legacy_plain_text_promoted_to_paragraphs():
    model = ClubWriteModel(description="line one\nline two\n\nsecond para")
    assert "<p>" in model.description
    assert "<br" in model.description


def test_exclude_unset_omits_unprovided_description():
    model = ClubWriteModel(name="New name")
    dumped = model.model_dump(exclude_unset=True)
    assert "description" not in dumped
    assert dumped == {"name": "New name"}


def test_exclude_unset_still_sanitizes_when_provided():
    model = ClubWriteModel(name="New name", description=XSS)
    dumped = model.model_dump(exclude_unset=True)
    assert "description" in dumped
    assert "<script" not in dumped["description"]


def test_boat_note_title_is_not_sanitized():
    model = BoatNoteCreateModel(title="<b>Bold title</b>", body="<p>ok</p>")
    assert model.title == "<b>Bold title</b>"


def test_note_template_name_is_not_sanitized():
    model = NoteTemplateCreateModel(name="<b>Bold name</b>", body="<p>ok</p>")
    assert model.name == "<b>Bold name</b>"

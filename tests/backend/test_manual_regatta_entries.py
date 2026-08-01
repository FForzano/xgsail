"""Manual (non-app-user) regatta entry creation and linking.

Organizers can add participants without requiring an XGSail account: just a
boat name and optional sail number. The entry is created with boat_id=NULL
and stored metadata, becoming idempotent on normalized (name, sail_number).
Later, if the sailor joins with an app, the organizer can link the entry to
their real boat account.
"""

import uuid

import pytest

from backend.repositories.sql.race_repo import SqlRegattaRepo


REGATTA = uuid.uuid4()


class FakeSessionFactory:
    def __init__(self, db=None):
        self.db = db or {}

    def __call__(self):
        return FakeSession(self.db)


class FakeSession:
    def __init__(self, db):
        self.db = db
        self._entries = db.get("entries", {})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def scalars(self, query):
        # Simplified mock for testing the normalize logic
        return FakeSpriteScalars([])

    def get(self, model, pk):
        if model.__name__ == "RegattaEntryORM":
            return self._entries.get(pk)
        return None

    def add(self, orm):
        self._entries[orm.id] = orm

    def delete(self, orm):
        self._entries.pop(orm.id, None)

    def commit(self):
        self.db["entries"] = self._entries


class FakeSpriteScalars:
    def __init__(self, items):
        self.items = items

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return self.items


@pytest.mark.parametrize(
    "boat_name,sail_number,expected",
    [
        ("Laser", None, "laser|"),
        ("Laser", "12345", "laser|12345"),
        ("My Boat", "abc-123", "my boat|abc-123"),
        ("  Trimmed  ", "  SAIL  ", "trimmed|sail"),
    ],
)
def test_normalized_name(boat_name, sail_number, expected):
    """Normalized names are lower+trimmed, separated by '|', for idempotent lookups."""
    factory = FakeSessionFactory()
    repo = SqlRegattaRepo(factory)
    normalized = repo._normalized_name(boat_name, sail_number)
    assert normalized == expected


def test_normalized_name_with_empty_boat_name():
    """None or empty boat_name returns None, failing the invariant check."""
    factory = FakeSessionFactory()
    repo = SqlRegattaRepo(factory)
    assert repo._normalized_name(None, "123") is None
    assert repo._normalized_name("", "123") is None
    assert repo._normalized_name("  ", "123") is None


def test_get_entry_guard_against_none_boat_id():
    """get_entry(regatta_id, None) returns None, not matching manual entries.

    This is a safety guard: boat_id is nullable, and ``boat_id == None``
    renders as ``IS NULL`` in SQL, which would spuriously match every manual
    entry on the regatta instead of finding nothing."""
    factory = FakeSessionFactory()
    repo = SqlRegattaRepo(factory)
    entry = repo.get_entry(REGATTA, None)
    assert entry is None

"""Who may file a recording against a race, and who may redeem a share code.

Both are authorization decisions on a surface a stranger can reach, so they
are covered here rather than left to manual checking. The rule under test is
the one that makes race tagging possible at all: a competitor is not an editor
of the organizing club's race activity, but must still be able to attach their
own track — and the right to do so comes from the start list, not from club
membership, because club regattas are routinely sailed by visiting boats.
"""

import uuid

import pytest

from backend.auth import permissions
from backend.auth.permissions import can_attach_session_to_activity
from backend.auth.throttle import CODE_ALPHABET, code_matches, new_code

CLUB = uuid.uuid4()
REGATTA = uuid.uuid4()
RACE = uuid.uuid4()
MY_BOAT = uuid.uuid4()
OTHER_BOAT = uuid.uuid4()


class FakeUser:
    def __init__(self, is_superadmin=False):
        self.id = uuid.uuid4()
        self.email = "sailor@example.test"
        self.is_superadmin = is_superadmin


class FakeActivity:
    def __init__(self, *, type="race", race_id=RACE, club_id=CLUB, created_by=None):
        self.id = uuid.uuid4()
        self.type = type
        self.race_id = race_id
        self.club_id = club_id
        self.created_by = created_by


class FakeRaceRepo:
    """``regatta_id`` is None for a race on a free race day (no start list)."""

    def __init__(self, regatta_id=REGATTA):
        self._regatta_id = regatta_id

    def regatta_id_for_race(self, race_id):
        return self._regatta_id


class FakeRegattaRepo:
    def __init__(self, entered_boats=()):
        self._entered = set(entered_boats)

    def get_entry(self, regatta_id, boat_id):
        if regatta_id != REGATTA or boat_id not in self._entered:
            return None
        return object()


class FakeRepos:
    def __init__(self, *, entered_boats=(), regatta_id=REGATTA):
        self.races = FakeRaceRepo(regatta_id)
        self.regattas = FakeRegattaRepo(entered_boats)


@pytest.fixture
def repos(monkeypatch):
    """Patch the lazy ``get_repos`` the permission helper resolves at call
    time, plus the RBAC lookup it delegates to, so the rule can be exercised
    without a database. ``club_role`` models "holds activity.manage on the
    organizing club" — off by default, since the case that matters is the
    competitor who holds nothing."""
    holder = {}

    def install(*, club_role=False, **kwargs):
        holder["repos"] = FakeRepos(**kwargs)
        monkeypatch.setattr(permissions, "user_has_permission",
                            lambda *a, **kw: club_role)
        return holder["repos"]

    import backend.repositories as repositories

    monkeypatch.setattr(repositories, "get_repos", lambda: holder["repos"])
    return install


def test_entered_boat_may_attach_without_club_membership(repos):
    """The whole point: a visiting sailor with no role in the organizing club
    files their own track because their boat is on the start list."""
    repos(entered_boats=[MY_BOAT])
    assert can_attach_session_to_activity(FakeActivity(), MY_BOAT, FakeUser())


def test_boat_not_on_start_list_is_refused(repos):
    repos(entered_boats=[OTHER_BOAT])
    assert not can_attach_session_to_activity(FakeActivity(), MY_BOAT, FakeUser())


def test_entry_does_not_carry_over_to_another_boat(repos):
    """An entry authorizes that boat's session only — it is not a general
    right to attach anything to the race."""
    repos(entered_boats=[MY_BOAT])
    assert not can_attach_session_to_activity(FakeActivity(), OTHER_BOAT, FakeUser())


def test_free_race_day_has_no_start_list_to_authorize_against(repos):
    repos(entered_boats=[MY_BOAT], regatta_id=None)
    assert not can_attach_session_to_activity(FakeActivity(), MY_BOAT, FakeUser())


def test_entry_does_not_authorize_non_race_activities(repos):
    """A club training activity is not covered by a regatta start list."""
    repos(entered_boats=[MY_BOAT])
    activity = FakeActivity(type="training", race_id=None)
    assert not can_attach_session_to_activity(activity, MY_BOAT, FakeUser())


def test_activity_creator_still_allowed_without_any_entry(repos):
    """The pre-existing editor path must keep working — the entry rule widens
    access, it does not replace it."""
    repos(entered_boats=[])
    user = FakeUser()
    activity = FakeActivity(created_by=user.id)
    assert can_attach_session_to_activity(activity, MY_BOAT, user)


def test_anonymous_caller_is_refused(repos):
    repos(entered_boats=[MY_BOAT])
    assert not can_attach_session_to_activity(FakeActivity(), MY_BOAT, None)


def test_club_manager_still_allowed_without_any_entry(repos):
    repos(entered_boats=[], club_role=True)
    assert can_attach_session_to_activity(FakeActivity(), MY_BOAT, FakeUser())


# --- share code ------------------------------------------------------------

def test_code_matches_ignores_case_and_padding():
    assert code_matches("  abc123  ", "ABC123")


def test_revoked_code_matches_nothing():
    """Revocation sets the stored code to NULL; nothing may satisfy it —
    including an empty submission."""
    assert not code_matches("ABC123", None)
    assert not code_matches("", None)
    assert not code_matches("", "")


def test_wrong_code_is_refused():
    assert not code_matches("ABC124", "ABC123")


def test_generated_codes_avoid_ambiguous_characters():
    """Codes get read off a screen and typed by hand, so 0/O and 1/I must not
    appear at all."""
    generated = "".join(new_code(8) for _ in range(200))
    assert set(generated) <= set(CODE_ALPHABET)
    assert not (set("01OI") & set(generated))

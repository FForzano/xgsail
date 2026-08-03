"""SQL race-structure repositories: regattas -> race_days -> races (+ results).

Results are per-boat rows on ``SqlRaceRepo`` (unique per race+boat, upsert);
start-list entries are per-boat rows on ``SqlRegattaRepo`` (unique per
regatta+boat). ``club_id_for_race``/``club_id_for_raceday`` resolve the RBAC
scope for ``require_permission(key, club_id=...)`` — ``None`` for free race
days (``regatta_id`` NULL), which therefore require a global grant/superadmin.
``regatta_id_for_race`` resolves the other direction a race needs: which start
list governs it.
"""

import uuid
from datetime import date as date_t
from typing import Optional

from sqlalchemy import select

from ...db.models import (
    OfficialStandingsORM,
    RaceDayORM,
    RaceORM,
    RegattaDivisionORM,
    RegattaEntryORM,
    RegattaORM,
    ResultORM,
    SessionCrewORM,
    UserBoatORM,
    UserClubORM,
)

# ``join_code`` is deliberately absent: it is set only through the dedicated
# manage-gated endpoints, never through a generic regatta PATCH.
_REGATTA_FIELDS = ("name", "description", "image_id", "club_id", "class_id",
                   "scoring_system", "start_date", "end_date", "status")
_RACEDAY_FIELDS = ("regatta_id", "date", "notes")
_RACE_FIELDS = ("race_day_id", "race_number", "status", "start_time", "division_id")
_RESULT_FIELDS = ("session_id", "finish_time", "elapsed_time", "corrected_time",
                  "position", "score", "status")
_DIVISION_FIELDS = ("name", "sort_order", "laps")


class SqlRegattaRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, club_id: Optional[uuid.UUID] = None,
             status: Optional[str] = None) -> "list[RegattaORM]":
        with self.Session() as s:
            q = select(RegattaORM)
            if club_id is not None:
                q = q.where(RegattaORM.club_id == club_id)
            if status is not None:
                q = q.where(RegattaORM.status == status)
            return list(s.scalars(q).all())

    def list_raced_by_user(self, user_id: uuid.UUID, *,
                           status: Optional[str] = None) -> "list[RegattaORM]":
        """Regattas the user has actually raced in — a result tied to one of
        their boats, or they crewed a session matched to one of its races."""
        with self.Session() as s:
            my_boat_ids = select(UserBoatORM.boat_id).where(UserBoatORM.user_id == user_id)
            my_crew_sessions = select(SessionCrewORM.session_id).where(
                SessionCrewORM.user_id == user_id
            )
            my_race_ids = select(ResultORM.race_id).where(
                (ResultORM.boat_id.in_(my_boat_ids)) | (ResultORM.session_id.in_(my_crew_sessions))
            )
            my_regatta_ids = (
                select(RaceDayORM.regatta_id)
                .join(RaceORM, RaceORM.race_day_id == RaceDayORM.id)
                .where(RaceORM.id.in_(my_race_ids), RaceDayORM.regatta_id.isnot(None))
            )
            q = select(RegattaORM).where(RegattaORM.id.in_(my_regatta_ids))
            if status is not None:
                q = q.where(RegattaORM.status == status)
            return list(s.scalars(q).all())

    def list_for_member_clubs(self, user_id: uuid.UUID, *,
                              status: Optional[str] = None) -> "list[RegattaORM]":
        """Regattas belonging to any club the user is an active member of."""
        with self.Session() as s:
            member_club_ids = select(UserClubORM.club_id).where(
                UserClubORM.user_id == user_id,
                UserClubORM.status == "active",
            )
            q = select(RegattaORM).where(RegattaORM.club_id.in_(member_club_ids))
            if status is not None:
                q = q.where(RegattaORM.status == status)
            return list(s.scalars(q).all())

    def list_upcoming_for_user(self, user_id: uuid.UUID, *, limit: int = 5) -> "list[RegattaORM]":
        """Not-yet-completed regattas with a future start date, belonging to a
        club the user actively belongs to — the regatta half of the "in
        arrivo" feed (see ``SqlActivityRepo.list_upcoming_for_user`` for the
        activity half; club regattas auto-create a ``type=="race"`` activity
        per race that the activity-side query deliberately excludes, since
        this method is what surfaces the event instead)."""
        with self.Session() as s:
            member_club_ids = select(UserClubORM.club_id).where(
                UserClubORM.user_id == user_id,
                UserClubORM.status == "active",
            )
            q = (
                select(RegattaORM)
                .where(RegattaORM.club_id.in_(member_club_ids))
                .where(RegattaORM.status != "completed")
                .where(RegattaORM.start_date.isnot(None))
                .where(RegattaORM.start_date >= date_t.today())
                .order_by(RegattaORM.start_date.asc())
                .limit(limit)
            )
            return list(s.scalars(q).all())

    def get(self, regatta_id: uuid.UUID) -> Optional[RegattaORM]:
        with self.Session() as s:
            return s.get(RegattaORM, regatta_id)

    def create(self, data: dict) -> RegattaORM:
        with self.Session() as s:
            orm = RegattaORM(**{k: data.get(k) for k in _REGATTA_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, regatta_id: uuid.UUID, changes: dict) -> Optional[RegattaORM]:
        with self.Session() as s:
            orm = s.get(RegattaORM, regatta_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _REGATTA_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(regatta_id)

    def delete(self, regatta_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(RegattaORM, regatta_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- divisions (free-form per-regatta scoring categories) -------------

    def list_divisions(self, regatta_id: uuid.UUID) -> "list[RegattaDivisionORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(RegattaDivisionORM)
                .where(RegattaDivisionORM.regatta_id == regatta_id)
                .order_by(RegattaDivisionORM.sort_order.asc(), RegattaDivisionORM.name.asc())
            ).all())

    def get_division(self, regatta_id: uuid.UUID,
                     division_id: uuid.UUID) -> Optional[RegattaDivisionORM]:
        with self.Session() as s:
            return s.scalars(
                select(RegattaDivisionORM).where(
                    RegattaDivisionORM.regatta_id == regatta_id,
                    RegattaDivisionORM.id == division_id,
                )
            ).first()

    def create_division(self, regatta_id: uuid.UUID, data: dict) -> RegattaDivisionORM:
        # No IntegrityError handling here (none exists elsewhere in this
        # file either): the ``(regatta_id, name)`` unique violation is left
        # to propagate out of ``s.commit()`` as-is, for the router to catch
        # and turn into a 409.
        with self.Session() as s:
            orm = RegattaDivisionORM(
                regatta_id=regatta_id,
                **{k: data.get(k) for k in _DIVISION_FIELDS if k in data},
            )
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_division(regatta_id, new_id)

    def update_division(self, division_id: uuid.UUID,
                        changes: dict) -> Optional[RegattaDivisionORM]:
        with self.Session() as s:
            orm = s.get(RegattaDivisionORM, division_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _DIVISION_FIELDS:
                    setattr(orm, k, v)
            s.commit()
            regatta_id = orm.regatta_id
        return self.get_division(regatta_id, division_id)

    def delete_division(self, division_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(RegattaDivisionORM, division_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def set_entry_division(self, regatta_id: uuid.UUID, entry_id: uuid.UUID,
                           division_id: Optional[uuid.UUID]) -> Optional[RegattaEntryORM]:
        """Assign (or clear, with ``None``) which division an entry scores
        in. Keys on ``entry_id`` — never on ``boat_id``, which is NULL for
        manual entries (see ``get_entry``'s guard)."""
        with self.Session() as s:
            orm = s.scalars(
                select(RegattaEntryORM).where(
                    RegattaEntryORM.regatta_id == regatta_id,
                    RegattaEntryORM.id == entry_id,
                )
            ).first()
            if orm is None:
                return None
            orm.division_id = division_id
            s.commit()
        return self.get_entry_by_id(regatta_id, entry_id)

    # --- share code -------------------------------------------------------

    def get_by_join_code(self, code: str) -> Optional[RegattaORM]:
        with self.Session() as s:
            return s.scalars(
                select(RegattaORM).where(RegattaORM.join_code == code)
            ).first()

    def set_join_code(self, regatta_id: uuid.UUID, code: Optional[str]) -> Optional[RegattaORM]:
        """Set (or, with ``None``, revoke) the share code."""
        with self.Session() as s:
            orm = s.get(RegattaORM, regatta_id)
            if orm is None:
                return None
            orm.join_code = code
            s.commit()
        return self.get(regatta_id)

    # --- start list (one row per regatta+boat) ----------------------------

    def list_entries(self, regatta_id: uuid.UUID) -> "list[RegattaEntryORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(RegattaEntryORM)
                .where(RegattaEntryORM.regatta_id == regatta_id)
                .order_by(RegattaEntryORM.created_at.asc())
            ).all())

    def get_entry(self, regatta_id: uuid.UUID,
                  boat_id: Optional[uuid.UUID]) -> Optional[RegattaEntryORM]:
        # Guard: ``boat_id`` is nullable on manual entries, and
        # ``boat_id == None`` renders as ``IS NULL`` in SQL — without this
        # guard, calling with ``boat_id=None`` would spuriously match every
        # manual entry on the regatta instead of finding nothing.
        if boat_id is None:
            return None
        with self.Session() as s:
            return s.scalars(
                select(RegattaEntryORM).where(
                    RegattaEntryORM.regatta_id == regatta_id,
                    RegattaEntryORM.boat_id == boat_id,
                )
            ).first()

    def get_entry_by_id(self, regatta_id: uuid.UUID,
                        entry_id: uuid.UUID) -> Optional[RegattaEntryORM]:
        with self.Session() as s:
            return s.scalars(
                select(RegattaEntryORM).where(
                    RegattaEntryORM.regatta_id == regatta_id,
                    RegattaEntryORM.id == entry_id,
                )
            ).first()

    @staticmethod
    def _normalized_name(boat_name: Optional[str],
                         sail_number: Optional[str]) -> Optional[str]:
        if boat_name is None or not boat_name.strip():
            return None
        name = boat_name.strip().lower()
        sail = (sail_number or "").strip().lower()
        return f"{name}|{sail}"

    def _get_manual_entry(self, regatta_id: uuid.UUID,
                          normalized: str) -> Optional[RegattaEntryORM]:
        with self.Session() as s:
            return s.scalars(
                select(RegattaEntryORM).where(
                    RegattaEntryORM.regatta_id == regatta_id,
                    RegattaEntryORM.boat_name_normalized == normalized,
                )
            ).first()

    def add_entry(self, regatta_id: uuid.UUID, boat_id: Optional[uuid.UUID], *,
                  boat_name: Optional[str] = None,
                  sail_number: Optional[str] = None,
                  source: str, created_by: Optional[uuid.UUID],
                  division_id: Optional[uuid.UUID] = None) -> RegattaEntryORM:
        """Idempotent: re-entering an already-listed boat (by ``boat_id``, or
        by normalized name+sail number for a manual entry with no boat yet)
        returns the existing row rather than tripping the unique constraint —
        a sailor opening the share link twice, or an organizer re-submitting
        the same paper entry, is not an error. ``division_id`` is applied
        only when a new entry is created; it is not retroactively applied to
        an existing one (use ``set_entry_division`` for that)."""
        if boat_id is not None:
            existing = self.get_entry(regatta_id, boat_id)
            if existing is not None:
                return existing
            with self.Session() as s:
                orm = RegattaEntryORM(
                    regatta_id=regatta_id, boat_id=boat_id,
                    source=source, created_by=created_by,
                    division_id=division_id,
                )
                s.add(orm)
                s.commit()
            return self.get_entry(regatta_id, boat_id)

        normalized = self._normalized_name(boat_name, sail_number)
        existing = self._get_manual_entry(regatta_id, normalized)
        if existing is not None:
            return existing
        with self.Session() as s:
            orm = RegattaEntryORM(
                regatta_id=regatta_id, boat_id=None,
                boat_name=boat_name.strip(), sail_number=sail_number,
                boat_name_normalized=normalized,
                source=source, created_by=created_by,
                division_id=division_id,
            )
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get_entry_by_id(regatta_id, new_id)

    def remove_entry_by_id(self, entry_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(RegattaEntryORM, entry_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def link_entry(self, regatta_id: uuid.UUID, entry_id: uuid.UUID,
                   boat_id: uuid.UUID) -> Optional[RegattaEntryORM]:
        """Match a manual entry to a real boat: sets ``boat_id`` and clears
        the manual fields. Idempotent if the entry is already linked to this
        same boat. Caller is expected to have already checked that no other
        entry on this regatta holds ``boat_id`` (409) — enforced here only as
        a last-resort safety net via the partial unique index."""
        with self.Session() as s:
            orm = s.scalars(
                select(RegattaEntryORM).where(
                    RegattaEntryORM.regatta_id == regatta_id,
                    RegattaEntryORM.id == entry_id,
                )
            ).first()
            if orm is None:
                return None
            if orm.boat_id == boat_id:
                return orm
            orm.boat_id = boat_id
            orm.boat_name = None
            orm.sail_number = None
            orm.boat_name_normalized = None
            s.commit()
        return self.get_entry_by_id(regatta_id, entry_id)

    def entered_boat_ids(self, regatta_id: uuid.UUID,
                         user_id: uuid.UUID) -> "list[uuid.UUID]":
        """The user's own boats that are on this regatta's start list."""
        with self.Session() as s:
            my_boat_ids = select(UserBoatORM.boat_id).where(
                UserBoatORM.user_id == user_id
            )
            return list(s.scalars(
                select(RegattaEntryORM.boat_id).where(
                    RegattaEntryORM.regatta_id == regatta_id,
                    RegattaEntryORM.boat_id.in_(my_boat_ids),
                )
            ).all())

    # --- official standings ---

    def list_official_standings(self, regatta_id: uuid.UUID) -> "list[OfficialStandingsORM]":
        """Fetch official standings rows for a regatta, ordered by position."""
        with self.Session() as s:
            return list(s.scalars(
                select(OfficialStandingsORM)
                .where(OfficialStandingsORM.regatta_id == regatta_id)
                .order_by(OfficialStandingsORM.position.asc())
            ).all())

    def set_official_standings(self, regatta_id: uuid.UUID,
                               standings: "list[dict]",
                               user_id: uuid.UUID) -> bool:
        """Replace the official standings for a regatta with a new list.

        Each item in standings should have: boat_id, position, score (optional),
        status (optional), division_id (optional). This clears any existing
        official standings and creates new rows.
        """
        with self.Session() as s:
            # Delete existing official standings
            s.query(OfficialStandingsORM).where(
                OfficialStandingsORM.regatta_id == regatta_id
            ).delete()

            # Insert new ones
            for item in standings:
                orm = OfficialStandingsORM(
                    regatta_id=regatta_id,
                    boat_id=item["boat_id"],
                    position=item["position"],
                    score=item.get("score"),
                    status=item.get("status"),
                    division_id=item.get("division_id"),
                    created_by=user_id,
                )
                s.add(orm)
            s.commit()
            return True

    def clear_official_standings(self, regatta_id: uuid.UUID) -> bool:
        """Delete all official standings for a regatta, reverting to computed ones."""
        with self.Session() as s:
            count = s.query(OfficialStandingsORM).where(
                OfficialStandingsORM.regatta_id == regatta_id
            ).delete()
            s.commit()
            return count > 0


class SqlRaceDayRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, regatta_id: Optional[uuid.UUID] = None,
             date: Optional[date_t] = None) -> "list[RaceDayORM]":
        with self.Session() as s:
            q = select(RaceDayORM)
            if regatta_id is not None:
                q = q.where(RaceDayORM.regatta_id == regatta_id)
            if date is not None:
                q = q.where(RaceDayORM.date == date)
            return list(s.scalars(q).all())

    def get(self, raceday_id: uuid.UUID) -> Optional[RaceDayORM]:
        with self.Session() as s:
            return s.get(RaceDayORM, raceday_id)

    def create(self, data: dict) -> RaceDayORM:
        with self.Session() as s:
            orm = RaceDayORM(**{k: data.get(k) for k in _RACEDAY_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, raceday_id: uuid.UUID, changes: dict) -> Optional[RaceDayORM]:
        with self.Session() as s:
            orm = s.get(RaceDayORM, raceday_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _RACEDAY_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(raceday_id)

    def delete(self, raceday_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(RaceDayORM, raceday_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def club_id_for_raceday(self, raceday_id: uuid.UUID) -> Optional[uuid.UUID]:
        with self.Session() as s:
            rd = s.get(RaceDayORM, raceday_id)
            if rd is None or rd.regatta_id is None:
                return None
            regatta = s.get(RegattaORM, rd.regatta_id)
            return regatta.club_id if regatta else None


class SqlRaceRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    def list(self, *, race_day_id: Optional[uuid.UUID] = None) -> "list[RaceORM]":
        with self.Session() as s:
            q = select(RaceORM)
            if race_day_id is not None:
                q = q.where(RaceORM.race_day_id == race_day_id)
            return list(s.scalars(q).all())

    def list_for_racedays(self, race_day_ids) -> "list[RaceORM]":
        """Every race of several days in one query — the regatta payload and
        the standings would otherwise issue one query per day."""
        if not race_day_ids:
            return []
        with self.Session() as s:
            return list(s.scalars(
                select(RaceORM)
                .where(RaceORM.race_day_id.in_(list(race_day_ids)))
                .order_by(RaceORM.race_number.asc())
            ).all())

    def get(self, race_id: uuid.UUID) -> Optional[RaceORM]:
        with self.Session() as s:
            return s.get(RaceORM, race_id)

    def create(self, data: dict) -> RaceORM:
        with self.Session() as s:
            orm = RaceORM(**{k: data.get(k) for k in _RACE_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, race_id: uuid.UUID, changes: dict) -> Optional[RaceORM]:
        with self.Session() as s:
            orm = s.get(RaceORM, race_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _RACE_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(race_id)

    def delete(self, race_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(RaceORM, race_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    def club_id_for_race(self, race_id: uuid.UUID) -> Optional[uuid.UUID]:
        with self.Session() as s:
            race = s.get(RaceORM, race_id)
            if race is None:
                return None
            rd = s.get(RaceDayORM, race.race_day_id)
            if rd is None or rd.regatta_id is None:
                return None
            regatta = s.get(RegattaORM, rd.regatta_id)
            return regatta.club_id if regatta else None

    def regatta_id_for_race(self, race_id: uuid.UUID) -> Optional[uuid.UUID]:
        """Which regatta's start list governs this race — ``None`` for a race
        on a free race day, which has no entries to check against."""
        with self.Session() as s:
            race = s.get(RaceORM, race_id)
            if race is None:
                return None
            rd = s.get(RaceDayORM, race.race_day_id)
            return rd.regatta_id if rd else None

    # --- results (one row per race+boat) ---

    def list_results(self, race_id: uuid.UUID) -> "list[ResultORM]":
        with self.Session() as s:
            return list(s.scalars(
                select(ResultORM).where(ResultORM.race_id == race_id)
            ).all())

    def list_results_for_races(self, race_ids) -> "list[ResultORM]":
        if not race_ids:
            return []
        with self.Session() as s:
            return list(s.scalars(
                select(ResultORM).where(ResultORM.race_id.in_(list(race_ids)))
            ).all())

    def get_result(self, result_id: uuid.UUID) -> Optional[ResultORM]:
        with self.Session() as s:
            return s.get(ResultORM, result_id)

    def upsert_result(self, race_id: uuid.UUID, boat_id: uuid.UUID,
                      data: dict) -> ResultORM:
        with self.Session() as s:
            orm = s.scalars(
                select(ResultORM).where(
                    ResultORM.race_id == race_id, ResultORM.boat_id == boat_id
                )
            ).first()
            if orm is None:
                orm = ResultORM(race_id=race_id, boat_id=boat_id)
                s.add(orm)
            for k, v in data.items():
                if k in _RESULT_FIELDS:
                    setattr(orm, k, v)
            s.commit()
            new_id = orm.id
        return self.get_result(new_id)

    def delete_result(self, race_id: uuid.UUID, boat_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.scalars(
                select(ResultORM).where(
                    ResultORM.race_id == race_id, ResultORM.boat_id == boat_id
                )
            ).first()
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

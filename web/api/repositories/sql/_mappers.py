"""Domain <-> ORM conversion for the SQL backend.

Kept in one place so the per-entity repos stay thin. JSON value objects
(start/finish line, polar, results) are round-tripped via the domain models'
``to_dict`` / ``from_dict``.
"""

from ... import domain
from ...db.models import (
    RegattaORM,
    RaceDayORM,
    RaceORM,
    MarkORM,
    RaceBoatORM,
    RaceResultORM,
    BoatORM,
    BoatMemberORM,
    SessionORM,
    UserORM,
    ClubORM,
    ClubMemberORM,
    GroupORM,
    GroupMemberORM,
    DeviceORM,
    DeviceAssignmentORM,
    SessionCrewORM,
    AuthRefreshTokenORM,
)


# --- User (password_hash intentionally NOT mapped onto the domain object) ---

def user_to_domain(orm: UserORM) -> domain.User:
    return domain.User(
        id=orm.id,
        email=orm.email,
        name=orm.name,
        is_active=orm.is_active,
        is_superadmin=orm.is_superadmin,
        created_at=orm.created_at,
    )


# --- Club (+ membership) ---

def club_to_domain(orm: ClubORM) -> domain.Club:
    return domain.Club(
        id=orm.id,
        name=orm.name,
        owner_user_id=orm.owner_user_id,
        default_session_visibility=orm.default_session_visibility or "private",
        created_at=orm.created_at,
        members=[
            domain.ClubMember(user_id=m.user_id, status=m.status, joined_at=m.joined_at)
            for m in orm.members
        ],
    )


# --- Group (+ membership) ---

def group_to_domain(orm: GroupORM) -> domain.Group:
    return domain.Group(
        id=orm.id,
        name=orm.name,
        description=orm.description,
        created_by=orm.created_by,
        default_session_visibility=orm.default_session_visibility or "private",
        created_at=orm.created_at,
        members=[
            domain.GroupMember(
                user_id=m.user_id, role=m.role, status=m.status, joined_at=m.joined_at
            )
            for m in orm.members
        ],
    )


# --- Device (+ attribution windows) ---

def assignment_to_domain(orm: DeviceAssignmentORM) -> domain.DeviceAssignment:
    return domain.DeviceAssignment(
        id=orm.id,
        device_id=orm.device_id,
        boat_id=orm.boat_id,
        regatta_id=orm.regatta_id,
        race_id=orm.race_id,
        valid_from=orm.valid_from,
        valid_to=orm.valid_to,
        created_by=orm.created_by,
        created_at=orm.created_at,
    )


def device_to_domain(orm: DeviceORM) -> domain.Device:
    return domain.Device(
        device_id=orm.device_id,
        name=orm.name,
        device_type=orm.device_type,
        default_boat_id=orm.default_boat_id,
        owner_type=orm.owner_type,
        registered_by=orm.registered_by,
        owned_by_club_id=orm.owned_by_club_id,
        status=orm.status,
        created_at=orm.created_at,
        last_seen_at=orm.last_seen_at,
        assignments=[assignment_to_domain(a) for a in orm.assignments],
    )


# --- AuthRefreshToken ---

def token_to_domain(orm: AuthRefreshTokenORM) -> domain.AuthRefreshToken:
    return domain.AuthRefreshToken(
        id=orm.id,
        user_id=orm.user_id,
        token_hash=orm.token_hash,
        family_id=orm.family_id,
        prev_id=orm.prev_id,
        issued_at=orm.issued_at,
        expires_at=orm.expires_at,
        revoked_at=orm.revoked_at,
        user_agent=orm.user_agent,
    )


# --- Regatta ---

def regatta_to_domain(orm: RegattaORM) -> domain.Regatta:
    return domain.Regatta(
        regatta_id=orm.regatta_id,
        name=orm.name,
        venue=orm.venue or "",
        boat_class=orm.boat_class,
        start_date=orm.start_date,
        end_date=orm.end_date,
        rating_system=orm.rating_system,
        start_sequence_minutes=orm.start_sequence_minutes,
        race_ids=list(orm.race_ids or []),
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def apply_regatta(orm: RegattaORM, d: domain.Regatta) -> None:
    orm.name = d.name
    orm.venue = d.venue or ""
    orm.boat_class = d.boat_class
    orm.start_date = d.start_date
    orm.end_date = d.end_date
    orm.rating_system = d.rating_system
    orm.start_sequence_minutes = d.start_sequence_minutes
    orm.race_ids = list(d.race_ids or [])
    orm.created_at = d.created_at
    orm.updated_at = d.updated_at


# --- RaceDay ---

def raceday_to_domain(orm: RaceDayORM) -> domain.RaceDay:
    return domain.RaceDay(
        raceday_id=orm.raceday_id,
        date=orm.date,
        type=orm.type,
        name=orm.name,
        regatta_id=orm.regatta_id,
        race_ids=list(orm.race_ids or []),
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def apply_raceday(orm: RaceDayORM, d: domain.RaceDay) -> None:
    orm.date = d.date
    orm.type = d.type
    orm.name = d.name
    orm.regatta_id = d.regatta_id
    orm.race_ids = list(d.race_ids or [])
    orm.created_at = d.created_at
    orm.updated_at = d.updated_at


# --- Boat ---

def boat_to_domain(orm: BoatORM) -> domain.Boat:
    return domain.Boat(
        boat_id=orm.boat_id,
        name=orm.name or "",
        type=orm.type or "",
        sail_number=orm.sail_number or "",
        club=orm.club or "",
        club_id=orm.club_id,
        loa_m=orm.loa_m,
        skippers=list(orm.skippers or []),
        members=[
            domain.BoatMember(user_id=m.user_id, role=m.role, created_at=m.created_at)
            for m in orm.members
        ],
        photos=dict(orm.photos or {}),
        cert_url=orm.cert_url,
        mbsa_url=orm.mbsa_url,
        links=list(orm.links or []),
        notes=orm.notes or "",
        polar=orm.polar,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def apply_boat(orm: BoatORM, d: domain.Boat) -> None:
    # Membership is managed through the dedicated member methods (boat_members
    # table), not rewritten here — so save() never clobbers the roster.
    orm.name = d.name or ""
    orm.type = d.type or ""
    orm.sail_number = d.sail_number or ""
    orm.club = d.club or ""
    orm.club_id = d.club_id
    orm.loa_m = d.loa_m
    orm.skippers = list(d.skippers or [])
    orm.photos = dict(d.photos or {})
    orm.cert_url = d.cert_url
    orm.mbsa_url = d.mbsa_url
    orm.links = list(d.links or [])
    orm.notes = d.notes or ""
    orm.polar = d.polar
    orm.created_at = d.created_at
    orm.updated_at = d.updated_at


# --- Race (aggregate) ---

def race_to_domain(orm: RaceORM) -> domain.Race:
    marks = [
        domain.Mark(mark_id=m.mark_id, name=m.name, mark_type=m.mark_type, lat=m.lat, lon=m.lon)
        for m in orm.marks
    ]
    boats = [
        domain.RaceBoat(
            device_id=b.device_id,
            boat_name=b.boat_name,
            sail_number=b.sail_number,
            boat_id=b.boat_id,
            session_path=b.session_path,
            gpx_path=b.gpx_path,
            polar=b.polar,
        )
        for b in orm.boats
    ]
    result = None
    if orm.result is not None:
        result = domain.RaceResult(
            finish_order=list(orm.result.finish_order or []),
            boat_results=dict(orm.result.boat_results or {}),
            computed_at=orm.result.computed_at,
        )
    return domain.Race(
        race_id=orm.race_id,
        name=orm.name,
        date=orm.date,
        start_time=orm.start_time,
        end_time=orm.end_time,
        regatta_id=orm.regatta_id,
        raceday_id=orm.raceday_id,
        boats=boats,
        start_line=domain.StartFinishLine.from_dict(orm.start_line) if orm.start_line else None,
        finish_line=domain.StartFinishLine.from_dict(orm.finish_line) if orm.finish_line else None,
        marks=marks,
        course=list(orm.course or []),
        finish_order=list(orm.finish_order or []),
        results=result,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def apply_race(orm: RaceORM, d: domain.Race) -> None:
    """Set scalars + rebuild owned children from the domain object."""
    orm.name = d.name
    orm.date = d.date
    orm.start_time = d.start_time
    orm.end_time = d.end_time
    orm.regatta_id = d.regatta_id
    orm.raceday_id = d.raceday_id
    orm.start_line = d.start_line.to_dict() if d.start_line else None
    orm.finish_line = d.finish_line.to_dict() if d.finish_line else None
    orm.course = list(d.course or [])
    orm.finish_order = list(d.finish_order or [])
    orm.created_at = d.created_at
    orm.updated_at = d.updated_at

    orm.marks = [
        MarkORM(mark_id=m.mark_id, name=m.name, mark_type=m.mark_type, lat=m.lat, lon=m.lon)
        for m in d.marks
    ]
    orm.boats = [
        RaceBoatORM(
            device_id=b.device_id,
            boat_id=b.boat_id,
            boat_name=b.boat_name,
            sail_number=b.sail_number,
            session_path=b.session_path,
            gpx_path=b.gpx_path,
            polar=b.polar,
        )
        for b in d.boats
    ]
    if d.results is not None:
        orm.result = RaceResultORM(
            finish_order=list(d.results.finish_order or []),
            boat_results=dict(d.results.boat_results or {}),
            computed_at=d.results.computed_at,
        )
    else:
        orm.result = None


def race_to_summary(orm: RaceORM) -> dict:
    return {
        "race_id": orm.race_id,
        "name": orm.name,
        "date": orm.date,
        "start_time": orm.start_time,
        "end_time": orm.end_time,
        "regatta_id": orm.regatta_id,
        "raceday_id": orm.raceday_id,
        "boat_count": len(orm.boats),
    }


# --- Session ---

def session_to_domain(orm: SessionORM) -> domain.Session:
    return domain.Session(
        device_id=orm.device_id,
        date=orm.date,
        session_id=orm.session_id,
        start_time=orm.start_time,
        end_time=orm.end_time,
        duration_sec=orm.duration_sec,
        boat=orm.boat,
        name=orm.name,
        sensors=orm.sensors if orm.sensors is not None else [],
        has_video=orm.has_video,
        has_analysis=orm.has_analysis,
        trim=orm.trim,
        owner_user_id=orm.owner_user_id,
        boat_id=orm.boat_id,
        visibility=orm.visibility or "private",
        club_id=orm.club_id,
        group_id=orm.group_id,
        regatta_id=orm.regatta_id,
        race_id=orm.race_id,
        crew=[
            domain.SessionCrew(
                user_id=c.user_id, guest_name=c.guest_name, boat_role=c.boat_role
            )
            for c in orm.crew
        ],
    )

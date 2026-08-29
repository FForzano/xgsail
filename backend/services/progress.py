"""Personal sailing-progression summary (``GET /api/users/me/progress``).

Volume only — how much the user sailed, not how well: session and day counts,
miles, hours, boats, plus all-time personal bests. Performance analytics stay
on the session/activity endpoints.

Two decisions shape everything here:

- **Scope is ``session_crew``, never boat membership.** A boat is routinely
  co-owned, so counting every session of a boat the user belongs to (what
  ``SqlSessionRepo.list_for_user`` does, correctly, for the diary feed) would
  credit a co-owner's outings as this user's own miles.
- **Bucketing happens in Python, not SQL.** Months and "distinct days" are
  calendar facts in the *caller's* local time, which a ``date_trunc`` cannot
  know — and ``date_trunc`` is Postgres-only, while the test suite runs on
  SQLite. A season is a few hundred rows, so the query stays bounded by date
  range and the arithmetic is trivial.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..repositories import get_repos
from ..schemas.user import (
    ProgressBestModel,
    ProgressBoatModel,
    ProgressTotalsModel,
    UserProgressModel,
)

# Emitted in this order; a metric with no data anywhere is omitted entirely.
BEST_METRICS = ("max_speed_kts", "distance_m", "duration_s", "avg_polar_pct")


def _as_utc(dt: datetime) -> datetime:
    """``started_at`` is timezone-aware on Postgres but comes back naive from
    SQLite, which stores it as UTC — assume that rather than the server's zone."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _to_local(dt: datetime, tz_offset_minutes: int) -> datetime:
    """The caller's local wall clock for an instant, as a naive datetime."""
    return (_as_utc(dt) + timedelta(minutes=tz_offset_minutes)).replace(tzinfo=None)


def _local_year_start(year: int, tz_offset_minutes: int) -> datetime:
    """The UTC instant at which ``year`` begins for the caller."""
    return datetime(year, 1, 1, tzinfo=timezone.utc) - timedelta(minutes=tz_offset_minutes)


def _totals(rows: "list[dict]", local_dates: "list[datetime]") -> ProgressTotalsModel:
    return ProgressTotalsModel(
        sessions=len(rows),
        days=len({d.date() for d in local_dates}),
        # Only the sessions the worker has already analysed carry stats, but
        # every session still counts above — a failed analysis must not make
        # the outing disappear.
        distance_m=sum(r["distance_m"] or 0.0 for r in rows),
        duration_s=sum(r["duration_s"] or 0 for r in rows),
        boats=len({r["boat_id"] for r in rows}),
    )


def _by_month(local_dates: "list[datetime]") -> "list[int]":
    months = [0] * 12
    for d in local_dates:
        months[d.month - 1] += 1
    return months


def _personal_bests(user_id: uuid.UUID, boat_name) -> "list[ProgressBestModel]":
    repos = get_repos()
    bests = []
    for metric in BEST_METRICS:
        row = repos.sessions.best_crewed_stat(user_id, metric)
        if row is None:
            continue
        bests.append(ProgressBestModel(
            metric=metric,
            value=row["value"],
            session_id=row["id"],
            activity_id=row["activity_id"],
            boat_id=row["boat_id"],
            boat_name=boat_name(row["boat_id"]),
            occurred_at=_as_utc(row["started_at"]),
        ))
    return bests


def _by_boat(rows: "list[dict]", boat_name) -> "list[ProgressBoatModel]":
    per_boat: "dict[uuid.UUID, dict]" = {}
    for r in rows:
        acc = per_boat.setdefault(r["boat_id"], {"sessions": 0, "distance_m": 0.0, "duration_s": 0})
        acc["sessions"] += 1
        acc["distance_m"] += r["distance_m"] or 0.0
        acc["duration_s"] += r["duration_s"] or 0
    out = [ProgressBoatModel(boat_id=boat_id, name=boat_name(boat_id), **acc)
           for boat_id, acc in per_boat.items()]
    out.sort(key=lambda b: (-b.sessions, b.name or ""))
    return out


def user_progress(user_id: uuid.UUID, *, year: Optional[int] = None,
                  tz_offset_minutes: int = 0) -> UserProgressModel:
    """Volume summary for ``year`` (default: the caller's current local year),
    with the previous year alongside it for deltas.

    ``tz_offset_minutes`` is minutes east of UTC — what JavaScript's
    ``-new Date().getTimezoneOffset()`` produces.
    """
    repos = get_repos()
    if year is None:
        year = _to_local(datetime.now(timezone.utc), tz_offset_minutes).year

    rows = repos.sessions.list_crewed_for_progress(
        user_id,
        start=_local_year_start(year - 1, tz_offset_minutes),
        end=_local_year_start(year + 1, tz_offset_minutes),
    )
    dated = [(r, _to_local(r["started_at"], tz_offset_minutes)) for r in rows]
    current = [(r, d) for r, d in dated if d.year == year]
    previous = [(r, d) for r, d in dated if d.year == year - 1]

    names: "dict[uuid.UUID, Optional[str]]" = {}

    def boat_name(boat_id: uuid.UUID) -> Optional[str]:
        if boat_id not in names:
            boat = repos.boats.get(boat_id)
            names[boat_id] = boat.name if boat is not None else None
        return names[boat_id]

    years = sorted({_to_local(t, tz_offset_minutes).year
                    for t in repos.sessions.list_crewed_start_times(user_id)})

    return UserProgressModel(
        year=year,
        available_years=years,
        totals=_totals([r for r, _ in current], [d for _, d in current]),
        previous=_totals([r for r, _ in previous], [d for _, d in previous]),
        by_month=_by_month([d for _, d in current]),
        previous_by_month=_by_month([d for _, d in previous]),
        personal_bests=_personal_bests(user_id, boat_name),
        by_boat=_by_boat([r for r, _ in current], boat_name),
    )

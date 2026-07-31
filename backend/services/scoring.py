"""Series standings from per-race results (Racing Rules of Sailing scoring).

Pure computation: no DB, no ORM — the router feeds it plain rows so the
scoring rules can be tested on their own.

No discards: the model has no ``discard_count`` column, so ``total`` is the
sum of every race.
"""

from typing import Optional

PENALTY_STATUSES = ("dnf", "dns", "dsq", "ocs", "ret")

# Bonus-point scale for places 1..6; 7th and beyond score ``position + 6``.
_BONUS_POINTS = {1: 0.0, 2: 3.0, 3: 5.7, 4: 8.0, 5: 10.0, 6: 11.7}


def _field(row, name):
    """Read a field from either a dict or an ORM/attr object."""
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def _penalty_score(entry_count: int) -> float:
    """RRS A9: a boat that starts but does not finish scores one more point
    than the number of boats entered in the series."""
    return float(entry_count + 1)


def _derived_score(position: Optional[int], status: Optional[str],
                   entry_count: int, scoring_system: str) -> Optional[float]:
    """Score implied by placing/status, or None when nothing can be derived
    (``custom`` scoring, or a finish with no recorded position)."""
    if scoring_system == "custom":
        return None
    if status in PENALTY_STATUSES:
        return _penalty_score(entry_count)
    if position is None:
        return None
    if scoring_system == "bonus_point":
        return _BONUS_POINTS.get(position, float(position + 6))
    return float(position)


def _effective_place(position: Optional[int], status: Optional[str],
                     entry_count: int) -> Optional[int]:
    """The placing used for tie-breaks: the finishing position, or the
    penalty place a non-finisher would have taken."""
    if status in PENALTY_STATUSES:
        return entry_count + 1
    return position


def compute_standings(races, results_by_race, entry_count,
                      scoring_system="low_point", *, boat_ids=None) -> list[dict]:
    """Rank boats over ``races`` (already in official chronological order).

    ``results_by_race`` maps race id -> result rows (``boat_id``, ``position``,
    ``score``, ``status``). An explicit non-null ``score`` always wins over the
    derived one (redress, fractional scores). A boat with no result in a race
    simply doesn't score there — it is not a penalty, since ``dns`` is an
    explicit status of its own.

    ``boat_ids`` ranks boats that have no result at all (start-list entries);
    they sort last rather than leading on a zero total.
    """
    per_boat: dict = {}

    def _slot(boat_id):
        return per_boat.setdefault(boat_id, {"boat_id": boat_id, "total": 0.0,
                                             "races": {}, "places": []})

    for boat_id in (boat_ids or []):
        _slot(boat_id)

    for race in races:
        race_id = _field(race, "id")
        for result in results_by_race.get(race_id) or []:
            boat_id = _field(result, "boat_id")
            position = _field(result, "position")
            status = _field(result, "status")
            score = _field(result, "score")
            if score is None:
                score = _derived_score(position, status, entry_count, scoring_system)
            if score is None:
                continue
            slot = _slot(boat_id)
            slot["total"] += float(score)
            slot["races"][race_id] = {"position": position, "score": float(score),
                                      "status": status}
            slot["places"].append(_effective_place(position, status, entry_count))

    ordered_race_ids = [_field(r, "id") for r in races]

    def _sort_key(slot):
        places = [p for p in slot["places"] if p is not None]
        # RRS A8.1: count of firsts, then seconds, ... — negated so that more
        # of a better place sorts earlier.
        counts = [0] * (max(places) + 1) if places else []
        for place in places:
            counts[place] += 1
        # RRS A8.2: still tied -> the last race decides (then walk backwards).
        last_races = tuple(
            slot["races"][rid]["score"] if rid in slot["races"] else float("inf")
            for rid in reversed(ordered_race_ids)
        )
        return (0 if slot["races"] else 1, slot["total"],
                tuple(-c for c in counts), last_races)

    rows = sorted(per_boat.values(), key=_sort_key)

    out: list[dict] = []
    previous_key = None
    previous_rank = 0
    for index, slot in enumerate(rows):
        key = _sort_key(slot)
        rank = previous_rank if key == previous_key else index + 1
        previous_key, previous_rank = key, rank
        out.append({"boat_id": slot["boat_id"], "total": slot["total"],
                    "rank": rank, "races": slot["races"]})
    return out

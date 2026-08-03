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


def total_entered_count(boat_ids, entries) -> int:
    """Fleet size for RRS A9 penalty scoring: boats with a result or a linked
    entry (``boat_ids``, already deduplicated), plus manual (unlinked) start-
    list entries that have no ``boat_id`` and so aren't in ``boat_ids`` at
    all. A club whose start list is mostly paper entries — the point of
    manual entries — must still score DNF/DNS against its real fleet size,
    not just the subset of boats with an XGSail account."""
    manual = sum(1 for entry in entries if _field(entry, "boat_id") is None)
    return len(boat_ids) + manual


def _division_sort_key(division):
    """Order divisions by ``sort_order`` then ``name``; a null sort_order
    sorts after every explicit one instead of blowing up the comparison."""
    order = _field(division, "sort_order")
    return (order is None, order or 0, _field(division, "name") or "")


def division_slices(divisions, entries, races, results_by_race) -> list[dict]:
    """Split a regatta into one independently scorable bundle per division.

    Each returned slice is exactly the argument bundle ``compute_standings``
    takes, plus the ``division_id`` it belongs to::

        {"division_id", "races", "results_by_race", "boat_ids", "entry_count"}

    The start list is the single source of truth for membership: a boat is in
    the division its ``regatta_entries`` row names. A race with a null
    ``division_id`` counts for every division; a race reserved to one division
    appears only in that slice — so a result filed for a boat of another
    division is dropped from every slice rather than scoring in the wrong one.

    ``entry_count`` is computed per slice, which is what makes the RRS A9
    penalty reflect the size of the division's fleet rather than the whole
    regatta's.
    """
    division_of = {
        _field(e, "boat_id"): _field(e, "division_id")
        for e in entries if _field(e, "boat_id") is not None
    }

    keys = [_field(d, "id") for d in sorted(divisions, key=_division_sort_key)]

    slices: list[dict] = []
    for key in keys + [None]:
        slice_entries = [e for e in entries if _field(e, "division_id") == key]
        slice_races = [r for r in races
                       if _field(r, "division_id") in (None, key)]
        slice_results = {}
        for race in slice_races:
            race_id = _field(race, "id")
            slice_results[race_id] = [
                res for res in (results_by_race.get(race_id) or [])
                if division_of.get(_field(res, "boat_id")) == key
            ]
        # Same ordering the whole-regatta standings use: boats seen in results
        # first (race order), then start-list entries that haven't raced.
        boat_ids = list(dict.fromkeys(
            [_field(res, "boat_id") for race in slice_races
             for res in slice_results[_field(race, "id")]]
            + [_field(e, "boat_id") for e in slice_entries
               if _field(e, "boat_id") is not None]
        ))
        # The catch-all slice is only worth showing when something is actually
        # unassigned — except in a regatta with no divisions at all, where it
        # *is* the standings and must exist even when empty.
        if key is None and divisions and not boat_ids and not slice_entries:
            continue
        slices.append({
            "division_id": key,
            "races": slice_races,
            "results_by_race": slice_results,
            "boat_ids": boat_ids,
            "entry_count": total_entered_count(boat_ids, slice_entries),
        })
    return slices


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

"""Per-division slicing of a regatta (``division_slices``): who belongs to
which ranking, which races count for it, and the per-division fleet size that
drives the RRS A9 penalty. Pure function, no DB involved."""

from backend.services.scoring import (compute_standings, division_slices,
                                      total_entered_count)


def _division(id, name, sort_order=0):
    return {"id": id, "name": name, "sort_order": sort_order}


def _entry(boat_id=None, division_id=None, **extra):
    return {"boat_id": boat_id, "division_id": division_id, **extra}


def _race(id, race_number=1, division_id=None):
    return {"id": id, "race_number": race_number, "division_id": division_id}


def _res(boat_id, position=None, score=None, status="finished"):
    return {"boat_id": boat_id, "position": position, "score": score,
            "status": status}


def _by_division(slices):
    return {s["division_id"]: s for s in slices}


def test_no_divisions_matches_todays_whole_regatta_scoring():
    """The hard compatibility constraint: with no divisions, the single slice
    must reproduce exactly what the router computes today — same races, same
    boat_ids (same order), same entry_count."""
    races = [_race("r1", 1), _race("r2", 2)]
    results_by_race = {
        "r1": [_res("b", 1), _res("a", 2)],
        "r2": [_res("a", 1), _res("c", 2)],
    }
    entries = [_entry("a"), _entry("b"), _entry("d"), _entry()]

    # What get_standings builds today, inline.
    expected_boat_ids = list(dict.fromkeys(
        [r["boat_id"] for race in races for r in results_by_race[race["id"]]]
        + [e["boat_id"] for e in entries if e["boat_id"] is not None]
    ))
    expected_count = total_entered_count(expected_boat_ids, entries)

    slices = division_slices([], entries, races, results_by_race)
    assert len(slices) == 1
    only = slices[0]
    assert only["division_id"] is None
    assert only["races"] == races
    assert only["results_by_race"] == results_by_race
    assert only["boat_ids"] == expected_boat_ids
    assert only["entry_count"] == expected_count


def test_no_divisions_empty_regatta_still_yields_one_slice():
    slices = division_slices([], [], [], {})
    assert len(slices) == 1
    assert slices[0]["division_id"] is None
    assert slices[0]["boat_ids"] == []
    assert slices[0]["entry_count"] == 0


def test_entries_partition_boats_between_divisions():
    divisions = [_division("cat", "Catamarani", 0),
                 _division("der", "Derive", 1)]
    entries = [_entry("a", "cat"), _entry("b", "cat"), _entry("c", "der")]
    races = [_race("r1")]
    results = {"r1": [_res("a", 1), _res("c", 2), _res("b", 3)]}

    slices = _by_division(division_slices(divisions, entries, races, results))
    assert set(slices) == {"cat", "der"}
    assert slices["cat"]["boat_ids"] == ["a", "b"]
    assert slices["der"]["boat_ids"] == ["c"]
    assert [r["boat_id"] for r in slices["cat"]["results_by_race"]["r1"]] == ["a", "b"]
    assert [r["boat_id"] for r in slices["der"]["results_by_race"]["r1"]] == ["c"]


def test_shared_race_appears_in_every_slice():
    divisions = [_division("cat", "Catamarani"), _division("der", "Derive", 1)]
    entries = [_entry("a", "cat"), _entry("c", "der")]
    races = [_race("r1", 1, division_id=None)]

    slices = _by_division(division_slices(divisions, entries, races, {}))
    assert [r["id"] for r in slices["cat"]["races"]] == ["r1"]
    assert [r["id"] for r in slices["der"]["races"]] == ["r1"]


def test_reserved_race_appears_only_in_its_own_slice():
    divisions = [_division("cat", "Catamarani"), _division("der", "Derive", 1)]
    entries = [_entry("a", "cat"), _entry("c", "der")]
    races = [_race("r1", 1, division_id=None), _race("r2", 2, division_id="der")]

    slices = _by_division(division_slices(divisions, entries, races, {}))
    assert [r["id"] for r in slices["cat"]["races"]] == ["r1"]
    assert [r["id"] for r in slices["der"]["races"]] == ["r1", "r2"]
    assert "r2" not in slices["cat"]["results_by_race"]


def test_foreign_boat_in_shared_race_does_not_shift_ranks():
    """A dinghy finishing between two catamarans must not push the second
    catamaran down to 3rd in the catamaran ranking."""
    divisions = [_division("cat", "Catamarani"), _division("der", "Derive", 1)]
    entries = [_entry("a", "cat"), _entry("b", "cat"), _entry("c", "der")]
    races = [_race("r1")]
    results = {"r1": [_res("a", 1), _res("c", 2), _res("b", 3)]}

    slices = _by_division(division_slices(divisions, entries, races, results))
    cat = slices["cat"]
    standings = compute_standings(cat["races"], cat["results_by_race"],
                                  cat["entry_count"], "low_point",
                                  boat_ids=cat["boat_ids"])
    assert [(row["boat_id"], row["rank"]) for row in standings] == [("a", 1), ("b", 2)]
    # The dinghy scores only in its own division.
    der = slices["der"]
    assert [row["boat_id"] for row in compute_standings(
        der["races"], der["results_by_race"], der["entry_count"], "low_point",
        boat_ids=der["boat_ids"])] == ["c"]


def test_result_in_foreign_reserved_race_is_dropped_everywhere():
    divisions = [_division("cat", "Catamarani"), _division("der", "Derive", 1)]
    entries = [_entry("a", "cat"), _entry("c", "der")]
    races = [_race("r1", 1, division_id="der")]
    # A catamaran was mistakenly scored in a dinghy-only race.
    results = {"r1": [_res("c", 1), _res("a", 2)]}

    slices = _by_division(division_slices(divisions, entries, races, results))
    assert "r1" not in slices["cat"]["results_by_race"]
    assert [r["boat_id"] for r in slices["der"]["results_by_race"]["r1"]] == ["c"]
    # The stray result never scores for the catamaran either.
    cat = slices["cat"]
    standings = compute_standings(cat["races"], cat["results_by_race"],
                                  cat["entry_count"], "low_point",
                                  boat_ids=cat["boat_ids"])
    assert standings[0]["races"] == {}


def test_penalty_uses_division_fleet_size_not_regatta_size():
    """RRS A9 per division: a DNF in a 4-boat division scores 5, even though
    the regatta as a whole has 15 entries."""
    divisions = [_division("cat", "Catamarani"), _division("der", "Derive", 1)]
    entries = ([_entry(f"c{n}", "cat") for n in range(4)]
               + [_entry(f"d{n}", "der") for n in range(11)])
    races = [_race("r1")]
    results = {"r1": [_res("c0", status="dnf"), _res("c1", 1)]}

    slices = _by_division(division_slices(divisions, entries, races, results))
    assert slices["cat"]["entry_count"] == 4
    assert slices["der"]["entry_count"] == 11
    cat = slices["cat"]
    standings = {row["boat_id"]: row for row in compute_standings(
        cat["races"], cat["results_by_race"], cat["entry_count"], "low_point",
        boat_ids=cat["boat_ids"])}
    assert standings["c0"]["total"] == 5.0


def test_manual_entries_count_only_in_their_own_division():
    divisions = [_division("cat", "Catamarani"), _division("der", "Derive", 1)]
    entries = [_entry("a", "cat"), _entry(None, "cat"), _entry(None, "cat"),
               _entry("c", "der")]

    slices = _by_division(division_slices(divisions, entries, [], {}))
    assert slices["cat"]["entry_count"] == 3  # 1 linked + 2 paper entries
    assert slices["cat"]["boat_ids"] == ["a"]  # paper entries aren't ranked
    assert slices["der"]["entry_count"] == 1


def test_unassigned_slice_omitted_when_every_entry_is_triaged():
    divisions = [_division("cat", "Catamarani"), _division("der", "Derive", 1)]
    entries = [_entry("a", "cat"), _entry("c", "der")]
    slices = division_slices(divisions, entries, [_race("r1")], {})
    assert [s["division_id"] for s in slices] == ["cat", "der"]


def test_unassigned_slice_kept_for_untriaged_entries_and_results():
    divisions = [_division("cat", "Catamarani")]
    entries = [_entry("a", "cat"), _entry("z")]
    slices = division_slices(divisions, entries, [_race("r1")], {})
    assert [s["division_id"] for s in slices] == ["cat", None]
    assert slices[1]["boat_ids"] == ["z"]

    # A boat with a result but no start-list entry also lands there.
    slices = division_slices(divisions, [_entry("a", "cat")], [_race("r1")],
                             {"r1": [_res("ghost", 1)]})
    assert slices[-1]["division_id"] is None
    assert slices[-1]["boat_ids"] == ["ghost"]


def test_slices_ordered_by_sort_order_then_name():
    divisions = [_division("d3", "Derive", 2),
                 _division("d1", "Catamarani veloci", 1),
                 _division("d2", "Catamarani", 1),
                 _division("d4", "Optimist", None)]
    slices = division_slices(divisions, [], [], {})
    # sort_order first; ties by name; a null sort_order sorts last.
    assert [s["division_id"] for s in slices] == ["d2", "d1", "d3", "d4"]

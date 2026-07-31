"""Series scoring rules (``compute_standings``): low point, bonus point,
custom, RRS A9 penalties and the RRS A8 tie-breaks — all on the pure
function, no DB involved."""

from backend.services.scoring import compute_standings


def _races(count):
    return [{"id": f"r{n}", "race_number": n} for n in range(1, count + 1)]


def _res(boat_id, position=None, score=None, status="finished"):
    return {"boat_id": boat_id, "position": position, "score": score,
            "status": status}


def _by_boat(standings):
    return {row["boat_id"]: row for row in standings}


def test_low_point_orders_by_total():
    races = _races(3)
    results = {
        "r1": [_res("a", 1), _res("b", 2), _res("c", 3)],
        "r2": [_res("a", 2), _res("b", 1), _res("c", 3)],
        "r3": [_res("a", 1), _res("b", 3), _res("c", 2)],
    }
    standings = compute_standings(races, results, 3, "low_point")
    assert [row["boat_id"] for row in standings] == ["a", "b", "c"]
    assert [row["total"] for row in standings] == [4.0, 6.0, 8.0]
    assert [row["rank"] for row in standings] == [1, 2, 3]
    assert standings[0]["races"]["r2"] == {"position": 2, "score": 2.0,
                                           "status": "finished"}


def test_penalties_score_entry_count_plus_one():
    races = _races(3)
    results = {
        "r1": [_res("a", status="dnf"), _res("b", 1)],
        "r2": [_res("a", status="dns"), _res("b", 1)],
        "r3": [_res("a", status="dsq"), _res("b", 1)],
    }
    standings = _by_boat(compute_standings(races, results, 7, "low_point"))
    assert standings["a"]["total"] == 24.0  # 3 x (7 + 1)
    assert standings["b"]["total"] == 3.0
    assert standings["a"]["races"]["r1"]["score"] == 8.0


def test_explicit_score_beats_derived_position():
    races = _races(1)
    # Redress: finished 5th, awarded a fractional score.
    results = {"r1": [_res("a", 5, score=2.5), _res("b", 1)]}
    standings = _by_boat(compute_standings(races, results, 10, "low_point"))
    assert standings["a"]["total"] == 2.5
    assert standings["a"]["races"]["r1"] == {"position": 5, "score": 2.5,
                                             "status": "finished"}


def test_tie_broken_by_more_firsts():
    races = _races(3)
    # Both total 6: a has two firsts, b has one.
    results = {
        "r1": [_res("a", 1), _res("b", 2)],
        "r2": [_res("a", 1), _res("b", 1)],
        "r3": [_res("a", 4), _res("b", 3)],
    }
    standings = compute_standings(races, results, 4, "low_point")
    assert [row["boat_id"] for row in standings] == ["a", "b"]
    assert [row["total"] for row in standings] == [6.0, 6.0]
    assert [row["rank"] for row in standings] == [1, 2]


def test_tie_broken_by_last_race_when_place_counts_match():
    races = _races(2)
    # Identical placing counts (each a 1st and a 2nd): the last race decides.
    results = {
        "r1": [_res("a", 2), _res("b", 1)],
        "r2": [_res("a", 1), _res("b", 2)],
    }
    standings = compute_standings(races, results, 2, "low_point")
    assert [row["boat_id"] for row in standings] == ["a", "b"]
    assert [row["rank"] for row in standings] == [1, 2]


def test_bonus_point_scale():
    races = _races(1)
    results = {"r1": [_res(f"b{p}", p) for p in range(1, 9)]}
    standings = _by_boat(compute_standings(races, results, 8, "bonus_point"))
    assert [standings[f"b{p}"]["total"] for p in range(1, 9)] == [
        0.0, 3.0, 5.7, 8.0, 10.0, 11.7, 13.0, 14.0,
    ]
    penalty = compute_standings(races, {"r1": [_res("x", status="dnf")]},
                                8, "bonus_point")
    assert penalty[0]["total"] == 9.0


def test_custom_ignores_position():
    races = _races(2)
    results = {
        "r1": [_res("a", 1), _res("b", 2, score=4.0)],
        "r2": [_res("a", 1, score=1.5), _res("b", status="dnf")],
    }
    standings = _by_boat(compute_standings(races, results, 5, "custom"))
    # a's first race has no explicit score -> it doesn't contribute at all.
    assert standings["a"]["total"] == 1.5
    assert "r1" not in standings["a"]["races"]
    # A penalty derives nothing either under custom scoring.
    assert standings["b"]["total"] == 4.0
    assert "r2" not in standings["b"]["races"]


def test_regatta_without_results():
    assert compute_standings(_races(2), {}, 0, "low_point") == []


def test_entered_boats_without_results_rank_last():
    races = _races(1)
    results = {"r1": [_res("a", 1)]}
    standings = compute_standings(races, results, 2, "low_point",
                                  boat_ids=["a", "b"])
    # b totals 0, which must NOT put it ahead of a in a low-point series.
    assert [row["boat_id"] for row in standings] == ["a", "b"]
    assert [row["rank"] for row in standings] == [1, 2]
    assert standings[1]["total"] == 0.0
    assert standings[1]["races"] == {}


def test_entered_boats_without_any_results_all_appear():
    standings = compute_standings(_races(1), {}, 2, "low_point",
                                  boat_ids=["a", "b"])
    assert [row["boat_id"] for row in standings] == ["a", "b"]
    assert all(row["total"] == 0.0 and row["races"] == {} for row in standings)
    # Perfectly tied and unresolvable: same rank.
    assert [row["rank"] for row in standings] == [1, 1]

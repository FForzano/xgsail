#!/usr/bin/env python3
"""
Seed the 2026 Constitution YC Wednesday Evening Spring Series — Race 1
(2026-05-27). Multi-class handicap race with PHRF ratings; all entries
loaded from regattaman.com's Preliminary results sheet.

GPS device_id is left null on every boat — the user assigns E1..E6 to
specific entries via the race editor once they confirm which physical
tracker rode on which boat.

Idempotent: re-running PATCHes the existing race in place (matched on
regatta_id + date + name "Race 1").

Usage:
    python3 scripts/seed_cyc_wed_spring_2026.py

Requires the api_race Lambda to have been redeployed with the
classes / race_conditions fields supported; otherwise the POST/PATCH
will succeed but those fields silently drop.
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API_BASE = "https://rnngzx7flk.execute-api.us-east-1.amazonaws.com"

# DST: 2026-05-27 falls in EDT = UTC-4. Local-to-UTC offset is +4h.
LOCAL_TO_UTC = timedelta(hours=4)
RACE_DATE = "2026-05-27"

# Course (informational — not yet wired into race.course mark sequence):
#   S/F > 13S > D/M > 13P > S/F
#   Start/Finish line, leave mark 13 to starboard, round D/M, leave 13
#   to port, back to S/F. Windward-leeward style course, hence the
#   "W50/L50 - Medium" rating type.
RATING_TYPE = "W50/L50 - Medium"
RACE_LEN_NM = 3.50


def local_iso(hms: str) -> str:
    """'18:41:00' local EDT → '2026-05-27T22:41:00Z' UTC."""
    h, m, s = map(int, hms.split(":"))
    dt = datetime(2026, 5, 27, h, m, s) + LOCAL_TO_UTC
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


# ---------- Regatta + race meta ----------

REGATTA = {
    "name": "2026 Constitution YC Wednesday Evening Spring Series",
    "venue": "Boston Harbor — Constitution Yacht Club",
    "start_date": "2026-05-27",
    "end_date": "2026-07-01",
}

CLASSES = [
    {
        "id": "A",
        "name": "Class A",
        "start_time": local_iso("18:41:00"),
        "rating_type": RATING_TYPE,
        "race_len_nm": RACE_LEN_NM,
    },
    {
        "id": "B",
        "name": "Class B",
        "start_time": local_iso("18:35:00"),
        "rating_type": RATING_TYPE,
        "race_len_nm": RACE_LEN_NM,
    },
]


def _boat(cls, team, yacht, club, sail_no, boat_type, rating,
          finish_hms=None, status="FIN"):
    return {
        "device_id": None,           # user assigns in editor
        "class": cls,
        "rating": rating,
        "team_name": team,
        "boat_name": yacht,
        "sail_number": sail_no,
        "boat_type": boat_type,
        "club": club,
        "finish_time": local_iso(finish_hms) if finish_hms else None,
        "finish_status": status,
        "session_path": None,
        "gpx_path": None,
    }


# ---------- Boats — from the corrected Preliminary results sheet ----------
# Ratings are W50/L50 - Medium (NOT the Random Leg values from the first
# sheet). Pogue / Never Settle is in Class A. Katü's skipper is now
# Paul Avillach & Kathryn Commons.

BOATS = [
    # Class A — start 18:41:00
    _boat("A", "Pogue, Robert", "Never Settle", "Constitution YC",
          "USA 14", "J/92", 0.915, "19:14:20"),
    _boat("A", "Alexander, Dave", "Pressure Drop", "Constitution YC",
          "61430", "Arcona 430", 0.939, "19:17:32"),
    _boat("A", "Isaacson, Peter", "Uproarious", "Constitution YC",
          "USA 78", "J/109", 0.929, "19:19:00"),
    _boat("A", "Jacobson, William", "VANISH", "Constitution YC",
          "51613", "J/46 DK", 0.992, "19:17:18"),
    _boat("A", "Powers, David and Tom / Crimmins, Joe", "Agora",
          "New York YC / Constitution YC", "52475", "Beneteau 36.7",
          0.931, "19:19:51"),
    _boat("A", "Ryley, Lance", "RockIt 2.0", "Constitution YC",
          "52816", "Columbia 30-2 Sport", 0.962, "19:19:54"),
    _boat("A", "Rudser, Jim", "Riot", "Constitution YC",
          "USA 40", "J/99", 0.938, "19:24:58"),
    _boat("A", "McLean, Allan", "Eagle", "Constitution YC",
          "42359", "Frers 38", 0.899, "19:34:31"),
    # DNC kept from prior week's roster — not visible in the updated
    # sheet (only racers + RET shown) but # of Entries: 9 confirms
    # there's a 9th boat. Rating reused from Isaacson's J/109 since
    # both are J/109s on the same scoring scheme.
    _boat("A", "Barmmer, Brian", "Saorsa", "Boston YC",
          "USA 1111", "J/109", 0.929, status="DNC"),

    # Class B — start 18:35:00
    _boat("B", "Conway, Ryan", "MASHNEE", "MIT Nautical Assoc.",
          "7", "Buzzards Bay 30", 0.862, "19:20:32"),
    _boat("B", "De Souter, Marissa & Wafler, Garrett", "Special Sauce", "",
          "470", "J/30", 0.848, "19:21:21"),
    # Katü — skippered by Paul Avillach (yes, you) and Kathryn Commons.
    _boat("B", "Paul Avillach & Kathryn Commons", "Katü", "Courageous SC",
          "484", "J/80", 0.872, "19:20:25"),
    _boat("B", "DiLorenzo, Dave", "Amigo", "",
          "82", "J/80", 0.872, "19:21:00"),
    _boat("B", "Phelps, Isaac", "Seabiscuit", "Constitution YC",
          "110", "Pearson 33-2", 0.824, "19:30:34"),
    _boat("B", "Tubman, Richard", "Charisma", "Constitution YC",
          "4396", "Jeanneau Sun Odyssey 410", 0.851, "19:30:41"),
    _boat("B", "Long, III, James Gardner & Wagner, Ryan", "Badger",
          "Constitution YC", "220", "Sabre 34 MK1", 0.731, status="RET"),
    # DNC entries not shown in the visible sheet rows but accounted for
    # by # of Entries: 9. Rating bumped to 0.872 to match the other
    # J/80s on the new W50/L50 scale.
    _boat("B", "DiLorenzo, Dave", "Wizard", "",
          "811", "J/80", 0.872, status="DNC"),
    _boat("B", "DiLorenzo, Dave & Sailing, Courageous", "Doc Buck",
          "Courageous SC", "88", "J/80", 0.872, status="DNC"),
]


# ---------- HTTP helpers ----------

def _request(method, path, body=None):
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "ignore")
        print(f"  HTTP {e.code} on {method} {url}: {body_txt}", file=sys.stderr)
        raise


def find_or_create_regatta():
    _, data = _request("GET", "/api/regattas")
    for r in data.get("regattas", []):
        if r["name"] == REGATTA["name"]:
            print(f"  Reusing existing regatta {r['regatta_id']} — {r['name']}")
            return r["regatta_id"]
    print(f"  Creating regatta: {REGATTA['name']}")
    _, created = _request("POST", "/api/regattas", REGATTA)
    return created["regatta_id"]


def find_existing_race(regatta_id):
    _, data = _request("GET", f"/api/races?regatta_id={regatta_id}&date={RACE_DATE}")
    for r in data.get("races", []):
        if r.get("name") == "Race 1":
            return r["race_id"]
    return None


def main():
    print("Seeding CYC Wednesday Spring Series — Race 1 (2026-05-27)")
    regatta_id = find_or_create_regatta()

    existing = find_existing_race(regatta_id)
    race_payload = {
        "name": "Race 1",
        "date": RACE_DATE,
        # Playback timeline starts at first gun (warning signal). Per-class
        # start times in classes[] are what PHRF elapsed is measured from.
        "start_time": local_iso("18:30:00"),
        "end_time": local_iso("19:40:00"),
        "regatta_id": regatta_id,
        "classes": CLASSES,
        "race_conditions": "WNW 12 kts",
        "boats": BOATS,
    }

    if existing:
        print(f"  Updating existing race {existing}")
        _, race = _request("PATCH", f"/api/races/{existing}", race_payload)
    else:
        print("  Creating new race")
        _, race = _request("POST", "/api/races", race_payload)

    race_id = race["race_id"]
    print()
    print(f"✓ Race seeded: {race_id}")
    print(f"  Dashboard: https://sailframes.com/race.html?race={race_id}")
    print(f"  {len(BOATS)} boats across {len(CLASSES)} classes")
    n_a = sum(1 for b in BOATS if b['class'] == 'A')
    n_b = sum(1 for b in BOATS if b['class'] == 'B')
    n_fin = sum(1 for b in BOATS if b['finish_status'] == 'FIN')
    print(f"  Class A: {n_a} entries · Class B: {n_b} entries · {n_fin} finishers")
    print()
    print("Next: open the dashboard, edit the race, assign device_id")
    print("(E1..E6) to whichever boats actually carried GPS trackers.")


if __name__ == "__main__":
    main()

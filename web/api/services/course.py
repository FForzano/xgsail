"""Course auto-suggestion: estimate a start line and detect rounding marks
from fleet GPS tracks. Pure computation; the endpoints load the tracks and
translate ``ValueError`` into HTTP 400.

``boat_gps`` is ``{device_id: [gps_point, ...]}`` already filtered to the race
window, each point ``{t, lat, lon, course, ...}``.
"""

import math

from . import geo

START_LINE_PADDING_M = 30.0
COURSE_CHANGE_DEG = 60.0
ROUNDING_WINDOW_SEC = 30.0
CLUSTER_RADIUS_M = 100.0


def estimate_start_line(boat_gps: dict, start_iso: str) -> dict:
    """Place a line perpendicular to mean fleet heading through the centroid,
    scaled to cover the fleet with padding. Raises ``ValueError`` if no usable
    positions exist at the gun."""
    positions: list[tuple[float, float]] = []
    headings: list[float] = []
    for gps in boat_gps.values():
        near = geo.points_near(gps, start_iso, window_sec=ROUNDING_WINDOW_SEC)
        if not near:
            continue
        closest = min(near, key=lambda p: abs(geo.iso_diff_seconds(p.get("t", ""), start_iso)))
        lat, lon = closest.get("lat"), closest.get("lon")
        if lat is None or lon is None:
            continue
        positions.append((lat, lon))
        cog = closest.get("course")
        if cog is not None:
            headings.append(cog)

    if len(positions) < 1:
        raise ValueError("No boat positions available at start time")

    clat = sum(p[0] for p in positions) / len(positions)
    clon = sum(p[1] for p in positions) / len(positions)
    mean_heading = geo.mean_angle_deg(headings) if headings else 0.0
    perp = (mean_heading + 90.0) % 360.0

    if len(positions) >= 2:
        projs = []
        for lat, lon in positions:
            dx_m = (lon - clon) * geo.meters_per_deg_lon(clat)
            dy_m = (lat - clat) * geo.meters_per_deg_lat()
            proj = dx_m * math.sin(math.radians(perp)) + dy_m * math.cos(math.radians(perp))
            projs.append(proj)
        half_len = max(abs(min(projs)), abs(max(projs))) + START_LINE_PADDING_M
    else:
        half_len = 40.0

    pin_lat, pin_lon = geo.offset_meters(clat, clon, perp, half_len)
    boat_lat, boat_lon = geo.offset_meters(clat, clon, (perp + 180.0) % 360.0, half_len)

    return {
        "start_line": {
            "pin_lat": pin_lat,
            "pin_lon": pin_lon,
            "boat_lat": boat_lat,
            "boat_lon": boat_lon,
        },
        "mean_heading_deg": mean_heading,
        "boats_used": len(positions),
    }


def _detect_roundings(boat_gps: dict) -> list[dict]:
    roundings: list[dict] = []
    for device_id, gps in boat_gps.items():
        pts = [p for p in gps if p.get("lat") is not None and p.get("course") is not None]
        if len(pts) < 10:
            continue
        i = 0
        while i < len(pts):
            t_i = pts[i].get("t", "")
            cog_i = pts[i]["course"]
            j = i + 1
            max_diff = 0.0
            max_j = i
            while j < len(pts):
                t_j = pts[j].get("t", "")
                if not t_j or geo.iso_diff_seconds(t_j, t_i) > ROUNDING_WINDOW_SEC:
                    break
                diff = abs(geo.angle_diff_deg(pts[j]["course"], cog_i))
                if diff > max_diff:
                    max_diff = diff
                    max_j = j
                j += 1
            if max_diff >= COURSE_CHANGE_DEG:
                mid = pts[(i + max_j) // 2]
                roundings.append({
                    "lat": mid["lat"],
                    "lon": mid["lon"],
                    "t": mid.get("t", ""),
                    "device_id": device_id,
                })
                i = max_j + 1
            else:
                i += 1
    return roundings


def _cluster(roundings: list[dict]) -> list[dict]:
    clusters: list[dict] = []
    for r in roundings:
        placed = False
        for c in clusters:
            d = geo.haversine_m(r["lat"], r["lon"], c["centroid_lat"], c["centroid_lon"])
            if d <= CLUSTER_RADIUS_M:
                c["points"].append(r)
                n = len(c["points"])
                c["centroid_lat"] = sum(p["lat"] for p in c["points"]) / n
                c["centroid_lon"] = sum(p["lon"] for p in c["points"]) / n
                placed = True
                break
        if not placed:
            clusters.append({"centroid_lat": r["lat"], "centroid_lon": r["lon"], "points": [r]})
    return [c for c in clusters if len(c["points"]) >= 2]


def detect_marks(boat_gps: dict) -> dict:
    """Detect course-change rounding points and cluster them into candidate
    marks ordered by average rounding time."""
    roundings = _detect_roundings(boat_gps)
    if not roundings:
        return {"marks": [], "roundings_found": 0}

    clusters = _cluster(roundings)

    def avg_time(c):
        times = [p["t"] for p in c["points"] if p["t"]]
        if not times:
            return ""
        return sorted(times)[len(times) // 2]

    clusters.sort(key=avg_time)

    suggested = []
    for i, c in enumerate(clusters):
        suggested.append({
            "mark_id": f"sug_{i + 1}",
            "name": f"Mark {i + 1}",
            "mark_type": "windward" if i % 2 == 0 else "leeward",
            "lat": c["centroid_lat"],
            "lon": c["centroid_lon"],
            "rounding_count": len(c["points"]),
        })

    return {
        "marks": suggested,
        "roundings_found": len(roundings),
        "clusters_found": len(clusters),
    }

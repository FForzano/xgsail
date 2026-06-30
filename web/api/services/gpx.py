"""GPX track parsing → processed ``gps.json`` point format."""

import re
import xml.etree.ElementTree as ET

from . import geo


def parse_gpx(content: bytes) -> list[dict]:
    """Parse GPX XML into GPS track points matching the processed gps.json
    format (``t``, ``lat``, ``lon``, ``speed_kn``, ``course``)."""
    root = ET.fromstring(content)
    ns_match = re.match(r"\{([^}]+)\}", root.tag)
    ns = f"{{{ns_match.group(1)}}}" if ns_match else ""

    raw: list[dict] = []
    for seg in root.iter(f"{ns}trkseg"):
        for trkpt in seg.iter(f"{ns}trkpt"):
            lat = float(trkpt.get("lat", 0))
            lon = float(trkpt.get("lon", 0))
            time_el = trkpt.find(f"{ns}time")
            if time_el is None or not time_el.text:
                continue
            t = time_el.text.strip()

            speed_ms = None
            for el in trkpt.iter():
                local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if local == "speed" and el.text:
                    try:
                        speed_ms = float(el.text)
                    except ValueError:
                        pass
                    break

            raw.append({"lat": lat, "lon": lon, "t": t, "_speed_ms": speed_ms})

    result = []
    for i, pt in enumerate(raw):
        sog = 0.0
        cog = 0.0

        if pt["_speed_ms"] is not None:
            sog = pt["_speed_ms"] * 1.94384  # m/s → knots
        elif i > 0:
            prev = raw[i - 1]
            try:
                dt = geo.iso_diff_seconds(pt["t"], prev["t"])
                if dt > 0:
                    dist_m = geo.haversine_m(prev["lat"], prev["lon"], pt["lat"], pt["lon"])
                    sog = (dist_m / dt) * 1.94384
            except Exception:
                pass

        if i > 0:
            prev = raw[i - 1]
            cog = geo.bearing(prev["lat"], prev["lon"], pt["lat"], pt["lon"])
        elif i < len(raw) - 1:
            nxt = raw[i + 1]
            cog = geo.bearing(pt["lat"], pt["lon"], nxt["lat"], nxt["lon"])

        result.append({
            "t": pt["t"],
            "lat": pt["lat"],
            "lon": pt["lon"],
            "speed_kn": round(sog, 2),
            "course": round(cog, 1),
        })

    return result

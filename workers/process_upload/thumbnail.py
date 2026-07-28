"""Track-preview PNGs — rendered once by the worker from ``gps.json`` and
reused as-is by the frontend instead of re-rendering the track on every page
load: a single-track thumbnail for one session
(frontend/src/pages/diario/SessionDetailPage.tsx) and a multi-track overlay
for an activity's card in the unified Activities list
(frontend/src/pages/diario/ActivitiesPage.tsx).
"""

from io import BytesIO
from math import cos, radians

from PIL import Image, ImageDraw

THUMB_SIZE = (320, 240)
THUMB_PADDING = 28
TRACK_WIDTH = 5
# Extra shrink on top of THUMB_PADDING so a thick line's rounded joints/caps
# at the track's extreme points never poke past the frame — worth the extra
# empty margin, since a track cut off at the edge reads worse than one with
# breathing room around it.
ZOOM_OUT = 0.9
TRACK_COLOR = (255, 149, 0, 255)  # orange — stands out against sky/water photo backdrops
MAX_POINTS = 800  # plenty of detail at ~300px; keeps rendering cheap

# Same distinct, colorblind-ish palette used for map tracks in
# frontend/src/components/race/raceModel.ts (PALETTE) — kept identical so a
# boat's color in the activity thumbnail matches its color once you open the
# activity's map view.
OVERLAY_PALETTE = [
    (47, 155, 224, 255),
    (224, 101, 79, 255),
    (63, 191, 127, 255),
    (224, 178, 74, 255),
    (155, 111, 224, 255),
    (79, 208, 224, 255),
]


def _extract_coords(gps_points: list) -> list:
    return [
        (p["lat"], p["lon"]) for p in gps_points
        if p.get("lat") is not None and p.get("lon") is not None
    ]


def _downsample(coords: list) -> list:
    step = max(1, len(coords) // MAX_POINTS)
    return coords[::step]


def render_track_thumbnail(gps_points: list) -> "bytes | None":
    """`gps_points` are ``gps.json`` records (need only ``lat``/``lon``).
    Returns None if there aren't enough points for a line."""
    coords = _downsample(_extract_coords(gps_points))
    if len(coords) < 2:
        return None
    return _render([coords], [TRACK_COLOR])


def render_overlay_thumbnail(tracks: "list[list]") -> "bytes | None":
    """``tracks`` is a list of per-session ``gps.json`` point lists — one line
    per session, colored by position in ``tracks`` (same order/palette as the
    map view). Returns None if no track has enough points for a line."""
    coord_sets = [_downsample(_extract_coords(pts)) for pts in tracks]
    coord_sets = [c for c in coord_sets if len(c) >= 2]
    if not coord_sets:
        return None
    colors = [OVERLAY_PALETTE[i % len(OVERLAY_PALETTE)] for i in range(len(coord_sets))]
    return _render(coord_sets, colors)


def _render(coord_sets: "list[list[tuple]]", colors: "list[tuple]") -> bytes:
    """Flat equirectangular projection (cos-latitude longitude correction) —
    good enough at the few-km scale of a session/activity, no need for a real
    map projection. Bounds span every track so all of them fit in frame."""
    all_coords = [c for coords in coord_sets for c in coords]
    lats = [c[0] for c in all_coords]
    lons = [c[1] for c in all_coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lon_scale = cos(radians((min_lat + max_lat) / 2)) or 1.0

    w, h = THUMB_SIZE
    pad = THUMB_PADDING
    lat_span = max(max_lat - min_lat, 1e-9)
    lon_span = max((max_lon - min_lon) * lon_scale, 1e-9)
    scale = min((w - 2 * pad) / lon_span, (h - 2 * pad) / lat_span) * ZOOM_OUT

    drawn_w = lon_span * scale
    drawn_h = lat_span * scale
    off_x = pad + ((w - 2 * pad) - drawn_w) / 2
    off_y = pad + ((h - 2 * pad) - drawn_h) / 2

    def project(lat: float, lon: float) -> tuple:
        x = off_x + (lon - min_lon) * lon_scale * scale
        y = h - off_y - (lat - min_lat) * scale  # flip: image Y grows downward
        return (x, y)

    img = Image.new("RGBA", THUMB_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for coords, color in zip(coord_sets, colors):
        draw.line([project(lat, lon) for lat, lon in coords], fill=color, width=TRACK_WIDTH, joint="curve")

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

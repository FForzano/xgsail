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

# Same centered moving-average window as smoothTrackLine() in
# frontend/src/components/race/raceModel.ts — kept identical so the thumbnail
# reads as the same track shape as the full map view, not a distinct render.
SMOOTH_WINDOW = 3
# Same as CURVE_SUBDIVISIONS in raceModel.ts: extra Catmull-Rom points drawn
# per original interval so the line reads as a curve, not straight chords.
CURVE_SUBDIVISIONS = 4
# PIL's ImageDraw has no antialiasing of its own — draw at this multiple of
# THUMB_SIZE, then downscale with a resampling filter, to get antialiased
# edges on the final PNG (the standard supersampling trick).
SUPERSAMPLE = 4

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


def _smooth(coords: list, window: int = SMOOTH_WINDOW) -> list:
    """Centered moving average, edges clamped rather than padded — same
    behavior as smoothTrackLine() in raceModel.ts."""
    n = len(coords)
    if n < window:
        return coords[:]
    half = window // 2
    out = []
    for i in range(n):
        sum_lat = sum_lon = 0.0
        count = 0
        for k in range(-half, half + 1):
            idx = min(n - 1, max(0, i + k))
            sum_lat += coords[idx][0]
            sum_lon += coords[idx][1]
            count += 1
        out.append((sum_lat / count, sum_lon / count))
    return out


def _catmull_rom_point(p0: tuple, p1: tuple, p2: tuple, p3: tuple, t: float) -> tuple:
    t2 = t * t
    t3 = t2 * t
    lat = 0.5 * (
        2 * p1[0]
        + (p2[0] - p0[0]) * t
        + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
        + (3 * p1[0] - p0[0] - 3 * p2[0] + p3[0]) * t3
    )
    lon = 0.5 * (
        2 * p1[1]
        + (p2[1] - p0[1]) * t
        + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
        + (3 * p1[1] - p0[1] - 3 * p2[1] + p3[1]) * t3
    )
    return (lat, lon)


def _curve_through(coords: list, subdivisions: int = CURVE_SUBDIVISIONS) -> list:
    """Catmull-Rom interpolation through every point — same math as
    catmullRomInterval() in raceModel.ts, applied across the whole line so the
    drawn path is a curve through the (smoothed) fixes, not straight chords."""
    n = len(coords)
    if n < 3:
        return coords[:]
    out = [coords[0]]
    for i in range(1, n):
        p0 = coords[max(0, i - 2)]
        p1 = coords[i - 1]
        p2 = coords[i]
        p3 = coords[min(n - 1, i + 1)]
        for s in range(1, subdivisions + 1):
            out.append(_catmull_rom_point(p0, p1, p2, p3, s / subdivisions))
    return out


def _prepare(coords: list) -> list:
    return _curve_through(_smooth(_downsample(coords)))


def render_track_thumbnail(gps_points: list) -> "bytes | None":
    """`gps_points` are ``gps.json`` records (need only ``lat``/``lon``).
    Returns None if there aren't enough points for a line."""
    coords = _extract_coords(gps_points)
    if len(coords) < 2:
        return None
    return _render([_prepare(coords)], [TRACK_COLOR])


def render_overlay_thumbnail(tracks: "list[list]") -> "bytes | None":
    """``tracks`` is a list of per-session ``gps.json`` point lists — one line
    per session, colored by position in ``tracks`` (same order/palette as the
    map view). Returns None if no track has enough points for a line."""
    coord_sets = [_extract_coords(pts) for pts in tracks]
    coord_sets = [_prepare(c) for c in coord_sets if len(c) >= 2]
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
    render_w, render_h = w * SUPERSAMPLE, h * SUPERSAMPLE
    pad = THUMB_PADDING * SUPERSAMPLE
    lat_span = max(max_lat - min_lat, 1e-9)
    lon_span = max((max_lon - min_lon) * lon_scale, 1e-9)
    scale = min((render_w - 2 * pad) / lon_span, (render_h - 2 * pad) / lat_span) * ZOOM_OUT

    drawn_w = lon_span * scale
    drawn_h = lat_span * scale
    off_x = pad + ((render_w - 2 * pad) - drawn_w) / 2
    off_y = pad + ((render_h - 2 * pad) - drawn_h) / 2

    def project(lat: float, lon: float) -> tuple:
        x = off_x + (lon - min_lon) * lon_scale * scale
        y = render_h - off_y - (lat - min_lat) * scale  # flip: image Y grows downward
        return (x, y)

    img = Image.new("RGBA", (render_w, render_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for coords, color in zip(coord_sets, colors):
        draw.line(
            [project(lat, lon) for lat, lon in coords],
            fill=color,
            width=TRACK_WIDTH * SUPERSAMPLE,
            joint="curve",
        )

    # Downscale from the supersampled canvas — PIL's ImageDraw has no
    # antialiasing of its own, so this is what turns the hard-edged line into
    # a smooth one in the final PNG.
    img = img.resize(THUMB_SIZE, Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

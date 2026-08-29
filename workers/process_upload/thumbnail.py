"""Track-preview PNGs — rendered once by the worker from ``gps.json`` and
reused as-is by the frontend instead of re-rendering the track on every page
load: a single-track thumbnail for one session
(frontend/src/pages/diario/SessionDetailPage.tsx) and a multi-track overlay
for an activity's card in the unified Activities list
(frontend/src/pages/diario/ActivitiesPage.tsx).

The track is projected in Web Mercator (EPSG:3857, the slippy-tile
projection) so it lines up pixel-exactly with an OpenStreetMap raster
background composited underneath it. The background is best-effort: with no
outbound network, a slow/failing tile server or a corrupt tile, the same PNG
is still produced with the track over a transparent canvas.

Environment:
  THUMBNAIL_TILE_URL         tile template, ``{z}/{x}/{y}``; empty disables
                             the background entirely.
  THUMBNAIL_TILE_USER_AGENT  sent on every tile request (the OSM tile usage
                             policy requires a descriptive one).
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from math import asinh, floor, pi, radians, tan
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

THUMB_SIZE = (640, 480)
THUMB_PADDING = 44
TRACK_WIDTH = 3
# Wider stroke drawn under the colored line: over a busy map neither a light
# nor a dark track reads on its own, the casing is what separates it from
# whatever tile is behind it.
TRACK_CASING_WIDTH = TRACK_WIDTH + 4
TRACK_CASING_COLOR = (255, 255, 255, 210)
# Extra shrink on top of THUMB_PADDING so a track that exactly fills the frame
# still has breathing room — a track cut off at the edge reads worse than one
# with margin around it.
ZOOM_OUT = 0.9
TRACK_COLOR = (255, 149, 0, 255)  # orange — stands out against sky/water photo backdrops
MAX_POINTS = 800  # plenty of detail at ~600px; keeps rendering cheap

# Same centered moving-average window as smoothTrackLine() in
# frontend/src/components/race/raceModel.ts — kept identical so the thumbnail
# reads as the same track shape as the full map view, not a distinct render.
SMOOTH_WINDOW = 3
# Same as CURVE_SUBDIVISIONS in raceModel.ts: extra Catmull-Rom points drawn
# per original interval so the line reads as a curve, not straight chords.
CURVE_SUBDIVISIONS = 4
# PIL's ImageDraw has no antialiasing of its own — the track is drawn at this
# multiple of THUMB_SIZE and downscaled before being composited over the map.
# The map itself is never resampled: the zoom level is picked so its tiles are
# used at native resolution.
SUPERSAMPLE = 3

TILE_SIZE = 256
TILE_URL_DEFAULT = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_USER_AGENT_DEFAULT = "XGSail/1.0 track thumbnail renderer (+https://github.com/FForzano/xgsail)"
TILE_TIMEOUT = 2.5  # seconds per tile — a preview is not worth a slow render
TILE_WORKERS = 10  # a 640x480 window needs at most 3x3 tiles: one wave, ~one timeout
MAX_TILES = 20  # 640x480 needs 3x3 at worst; the cap is a guard, not a budget
MIN_ZOOM = 2
MAX_ZOOM = 19
ATTRIBUTION = "© OpenStreetMap"

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


def _world_xy(lat: float, lon: float, zoom: int) -> tuple:
    """Web Mercator pixel coordinates at ``zoom``, origin at the top-left of
    the world (the slippy-tile convention: tile (x, y) covers pixels
    x*256..x*256+255)."""
    world = TILE_SIZE * (2 ** zoom)
    lat = min(85.05112878, max(-85.05112878, lat))
    x = (lon + 180.0) / 360.0 * world
    y = (1.0 - asinh(tan(radians(lat))) / pi) / 2.0 * world
    return (x, y)


def _fit_zoom(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> int:
    """Largest integer zoom whose projected bounds still fit the padded frame,
    so the tiles end up used at native resolution."""
    w, h = THUMB_SIZE
    avail_w = (w - 2 * THUMB_PADDING) * ZOOM_OUT
    avail_h = (h - 2 * THUMB_PADDING) * ZOOM_OUT
    for zoom in range(MAX_ZOOM, MIN_ZOOM, -1):
        x0, y0 = _world_xy(max_lat, min_lon, zoom)
        x1, y1 = _world_xy(min_lat, max_lon, zoom)
        if (x1 - x0) <= avail_w and (y1 - y0) <= avail_h:
            return zoom
    return MIN_ZOOM


def _fetch_tile(url: str, user_agent: str) -> "Image.Image | None":
    try:
        req = Request(url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=TILE_TIMEOUT) as resp:
            data = resp.read()
        return Image.open(BytesIO(data)).convert("RGB")
    except Exception as e:  # network down, timeout, HTTP error, corrupt image
        logger.warning(f"Thumbnail tile fetch failed ({url}): {e}")
        return None


def _tile_background(origin_x: float, origin_y: float, zoom: int) -> "Image.Image | None":
    """Mosaic of the tiles covering the THUMB_SIZE window whose top-left is at
    world pixel (origin_x, origin_y), cropped to that window. Returns None if
    the background is disabled or no tile could be fetched."""
    template = os.getenv("THUMBNAIL_TILE_URL", TILE_URL_DEFAULT).strip()
    if not template:
        return None
    user_agent = os.getenv("THUMBNAIL_TILE_USER_AGENT", TILE_USER_AGENT_DEFAULT)

    w, h = THUMB_SIZE
    tx0, ty0 = floor(origin_x / TILE_SIZE), floor(origin_y / TILE_SIZE)
    tx1, ty1 = floor((origin_x + w - 1) / TILE_SIZE), floor((origin_y + h - 1) / TILE_SIZE)
    span = 2 ** zoom
    wanted = [
        (x, y)
        for y in range(ty0, ty1 + 1)
        for x in range(tx0, tx1 + 1)
        if 0 <= y < span  # y off the world has no tile; x wraps around it
    ]
    if not wanted or len(wanted) > MAX_TILES:
        return None

    urls = [
        template.format(z=zoom, x=x % span, y=y)
        for x, y in wanted
    ]
    with ThreadPoolExecutor(max_workers=min(len(urls), TILE_WORKERS)) as pool:
        tiles = list(pool.map(lambda u: _fetch_tile(u, user_agent), urls))
    if not any(t is not None for t in tiles):
        return None

    mosaic = Image.new(
        "RGB",
        ((tx1 - tx0 + 1) * TILE_SIZE, (ty1 - ty0 + 1) * TILE_SIZE),
        (233, 231, 226),  # OSM land tone, so a missing tile isn't a black hole
    )
    for (x, y), tile in zip(wanted, tiles):
        if tile is not None:
            mosaic.paste(tile, ((x - tx0) * TILE_SIZE, (y - ty0) * TILE_SIZE))

    crop_x = int(round(origin_x - tx0 * TILE_SIZE))
    crop_y = int(round(origin_y - ty0 * TILE_SIZE))
    return mosaic.crop((crop_x, crop_y, crop_x + w, crop_y + h))


def _draw_attribution(img: "Image.Image") -> None:
    """OSM's tile usage policy requires visible credit wherever its tiles are
    displayed."""
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.load_default(size=13)
    except TypeError:  # Pillow < 10.1 has no sized default font
        font = ImageFont.load_default()
    w, h = img.size
    box = draw.textbbox((0, 0), ATTRIBUTION, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x, y = w - tw - 8, h - th - 7
    draw.rectangle((x - 4, y - 3, w, h), fill=(255, 255, 255, 170))
    draw.text((x - box[0], y - box[1]), ATTRIBUTION, font=font, fill=(60, 60, 60, 255))


def _render(coord_sets: "list[list[tuple]]", colors: "list[tuple]") -> bytes:
    """Web Mercator projection at an integer zoom, so the track lines up with
    the OSM tiles composited behind it. Bounds span every track so all of them
    fit in frame."""
    all_coords = [c for coords in coord_sets for c in coords]
    lats = [c[0] for c in all_coords]
    lons = [c[1] for c in all_coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    zoom = _fit_zoom(min_lat, max_lat, min_lon, max_lon)
    x0, y0 = _world_xy(max_lat, min_lon, zoom)  # top-left of the bounds
    x1, y1 = _world_xy(min_lat, max_lon, zoom)  # bottom-right
    w, h = THUMB_SIZE
    origin_x = (x0 + x1) / 2 - w / 2
    origin_y = (y0 + y1) / 2 - h / 2

    def project(lat: float, lon: float) -> tuple:
        x, y = _world_xy(lat, lon, zoom)
        return ((x - origin_x) * SUPERSAMPLE, (y - origin_y) * SUPERSAMPLE)

    track = Image.new("RGBA", (w * SUPERSAMPLE, h * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(track)
    projected = [[project(lat, lon) for lat, lon in coords] for coords in coord_sets]
    for points in projected:
        draw.line(points, fill=TRACK_CASING_COLOR,
                  width=TRACK_CASING_WIDTH * SUPERSAMPLE, joint="curve")
    for points, color in zip(projected, colors):
        draw.line(points, fill=color, width=TRACK_WIDTH * SUPERSAMPLE, joint="curve")

    # Downscale the track layer only — the map underneath stays at its native
    # tile resolution, which is what keeps the background sharp.
    track = track.resize(THUMB_SIZE, Image.LANCZOS)

    background = None
    try:
        background = _tile_background(origin_x, origin_y, zoom)
    except Exception as e:  # a broken template, a surprise from PIL — never fatal
        logger.warning(f"Thumbnail tile background unavailable: {e}")

    if background is None:
        img = track
    else:
        img = background.convert("RGBA")
        img.alpha_composite(track)
        _draw_attribution(img)
        # Opaque now, so drop the alpha and quantize: a full-color PNG of a map
        # photo is several times the size for no visible gain at preview scale.
        img = img.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

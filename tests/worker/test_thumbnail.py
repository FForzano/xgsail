"""Track-preview PNG rendering (workers/process_upload/thumbnail.py).

All tests here must stay network-free: THUMBNAIL_TILE_URL is either disabled
(empty string) or thumbnail._fetch_tile is monkeypatched to a synthetic
fetcher, so no test ever reaches urlopen()."""

from io import BytesIO
from math import floor

import pytest
from PIL import Image

import thumbnail as t


# --- helpers -----------------------------------------------------------------

def _points(coords: "list[tuple]") -> "list[dict]":
    """Build gps.json-shaped records from (lat, lon) pairs."""
    return [{"lat": lat, "lon": lon} for lat, lon in coords]


# A small track around Livorno, comfortably clear of the antimeridian/poles.
TRACK = [
    (43.5500, 10.3000),
    (43.5510, 10.3020),
    (43.5525, 10.3040),
    (43.5540, 10.3055),
    (43.5560, 10.3070),
]


def _solid_tile(color=(100, 150, 200)) -> Image.Image:
    return Image.new("RGB", (t.TILE_SIZE, t.TILE_SIZE), color)


def _open_png(data: bytes) -> Image.Image:
    img = Image.open(BytesIO(data))
    img.load()
    return img


class RecordingFetcher:
    """Fake _fetch_tile: records every URL it's called with and returns a
    fixed image (or None), so a test never triggers a real request."""

    def __init__(self, image=None):
        self.image = image
        self.calls = []

    def __call__(self, url, user_agent):
        self.calls.append(url)
        return self.image() if callable(self.image) else self.image


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Belt-and-suspenders default for every test in this file: unless a test
    installs its own fake, any accidental call to _fetch_tile raises instead
    of reaching the network."""
    def _forbidden(url, user_agent):
        raise AssertionError(f"unexpected real tile fetch attempted: {url}")
    monkeypatch.setattr(t, "_fetch_tile", _forbidden)
    yield


# --- render_track_thumbnail: not-enough-points contract -----------------------

def test_returns_none_for_no_points():
    assert t.render_track_thumbnail([]) is None


def test_returns_none_for_a_single_point():
    assert t.render_track_thumbnail(_points([(43.55, 10.30)])) is None


def test_returns_none_when_lat_lon_are_none():
    pts = [
        {"lat": None, "lon": None},
        {"lat": 43.55, "lon": None},
        {"lat": None, "lon": 10.30},
    ]
    assert t.render_track_thumbnail(pts) is None


# --- background disabled: no tile fetch attempted ------------------------------

def test_track_thumbnail_background_disabled(monkeypatch):
    monkeypatch.setenv("THUMBNAIL_TILE_URL", "")
    fetcher = RecordingFetcher()
    monkeypatch.setattr(t, "_fetch_tile", fetcher)

    data = t.render_track_thumbnail(_points(TRACK))

    assert isinstance(data, bytes)
    img = _open_png(data)
    assert img.format == "PNG"
    assert img.size == t.THUMB_SIZE
    assert img.mode == "RGBA"
    assert fetcher.calls == []


def test_overlay_thumbnail_background_disabled(monkeypatch):
    monkeypatch.setenv("THUMBNAIL_TILE_URL", "")
    fetcher = RecordingFetcher()
    monkeypatch.setattr(t, "_fetch_tile", fetcher)

    other_track = [(43.560, 10.310), (43.561, 10.312), (43.562, 10.315)]
    data = t.render_overlay_thumbnail([_points(TRACK), _points(other_track)])

    assert isinstance(data, bytes)
    img = _open_png(data)
    assert img.size == t.THUMB_SIZE
    assert img.mode == "RGBA"
    assert fetcher.calls == []


# --- graceful degradation: tile fetch fails but render still succeeds ---------

def test_all_tiles_fail_still_returns_valid_png(monkeypatch):
    monkeypatch.delenv("THUMBNAIL_TILE_URL", raising=False)
    monkeypatch.setattr(t, "_fetch_tile", RecordingFetcher(image=None))
    data = t.render_track_thumbnail(_points(TRACK))
    img = _open_png(data)
    assert img.size == t.THUMB_SIZE


def test_fetch_raising_still_returns_valid_png(monkeypatch):
    monkeypatch.delenv("THUMBNAIL_TILE_URL", raising=False)

    def _raise(url, user_agent):
        raise ConnectionError("simulated network failure")
    monkeypatch.setattr(t, "_fetch_tile", _raise)

    data = t.render_track_thumbnail(_points(TRACK))
    img = _open_png(data)
    assert img.size == t.THUMB_SIZE


# --- background succeeds: composited/quantized path ---------------------------

def test_background_present_produces_quantized_png(monkeypatch):
    monkeypatch.delenv("THUMBNAIL_TILE_URL", raising=False)
    fetcher = RecordingFetcher(image=_solid_tile)
    monkeypatch.setattr(t, "_fetch_tile", fetcher)

    data = t.render_track_thumbnail(_points(TRACK))

    img = _open_png(data)
    assert img.size == t.THUMB_SIZE
    assert img.mode == "P"  # opaque/quantized: the background path was taken
    assert fetcher.calls, "expected at least one tile fetch"

    # The requested tiles must be the ones covering the track's bounds at the
    # zoom _fit_zoom would pick, with {z}/{x}/{y} substituted correctly.
    # Bounds must match what _render actually projects: the smoothed/curved
    # coords from _prepare(), not the raw input points.
    prepared = t._prepare(t._extract_coords(_points(TRACK)))
    lats = [c[0] for c in prepared]
    lons = [c[1] for c in prepared]
    zoom = t._fit_zoom(min(lats), max(lats), min(lons), max(lons))
    x0, y0 = t._world_xy(max(lats), min(lons), zoom)
    x1, y1 = t._world_xy(min(lats), max(lons), zoom)
    w, h = t.THUMB_SIZE
    origin_x = (x0 + x1) / 2 - w / 2
    origin_y = (y0 + y1) / 2 - h / 2

    tx0, ty0 = floor(origin_x / t.TILE_SIZE), floor(origin_y / t.TILE_SIZE)
    tx1 = floor((origin_x + w - 1) / t.TILE_SIZE)
    ty1 = floor((origin_y + h - 1) / t.TILE_SIZE)
    span = 2 ** zoom
    expected_urls = {
        t.TILE_URL_DEFAULT.format(z=zoom, x=x % span, y=y)
        for y in range(ty0, ty1 + 1)
        for x in range(tx0, tx1 + 1)
        if 0 <= y < span
    }
    assert set(fetcher.calls) == expected_urls


# --- _world_xy projection sanity ----------------------------------------------

def test_world_xy_center_of_world_at_origin():
    for zoom in (2, 8, 15):
        x, y = t._world_xy(0.0, 0.0, zoom)
        expected = t.TILE_SIZE * (2 ** zoom) / 2
        assert x == pytest.approx(expected)
        assert y == pytest.approx(expected)


def test_world_xy_monotonic_in_longitude():
    zoom = 10
    x1, _ = t._world_xy(43.5, 10.0, zoom)
    x2, _ = t._world_xy(43.5, 11.0, zoom)
    assert x2 > x1


def test_world_xy_monotonic_in_latitude_inverted():
    # Higher latitude (further north) maps to a SMALLER y (top-left origin).
    zoom = 10
    _, y1 = t._world_xy(10.0, 10.0, zoom)
    _, y2 = t._world_xy(50.0, 10.0, zoom)
    assert y2 < y1


def test_world_xy_clamps_beyond_mercator_limit():
    zoom = 8
    limit_x, limit_y = t._world_xy(85.05112878, 10.0, zoom)
    beyond_x, beyond_y = t._world_xy(89.9, 10.0, zoom)
    assert beyond_x == pytest.approx(limit_x)
    assert beyond_y == pytest.approx(limit_y)

    neg_limit_x, neg_limit_y = t._world_xy(-85.05112878, 10.0, zoom)
    neg_beyond_x, neg_beyond_y = t._world_xy(-89.9, 10.0, zoom)
    assert neg_beyond_x == pytest.approx(neg_limit_x)
    assert neg_beyond_y == pytest.approx(neg_limit_y)


# --- _fit_zoom ------------------------------------------------------------------

def test_fit_zoom_bounds_fit_padded_frame():
    min_lat, max_lat = 43.5500, 43.5560
    min_lon, max_lon = 10.3000, 10.3070
    zoom = t._fit_zoom(min_lat, max_lat, min_lon, max_lon)

    x0, y0 = t._world_xy(max_lat, min_lon, zoom)
    x1, y1 = t._world_xy(min_lat, max_lon, zoom)
    w, h = t.THUMB_SIZE
    avail_w = (w - 2 * t.THUMB_PADDING) * t.ZOOM_OUT
    avail_h = (h - 2 * t.THUMB_PADDING) * t.ZOOM_OUT
    assert (x1 - x0) <= avail_w
    assert (y1 - y0) <= avail_h


def test_fit_zoom_smaller_box_gets_larger_zoom():
    small_zoom = t._fit_zoom(43.5500, 43.5510, 10.3000, 10.3010)
    large_zoom = t._fit_zoom(40.0, 47.0, 8.0, 15.0)
    assert small_zoom > large_zoom


# --- render_overlay_thumbnail: per-track point-count filtering ----------------

def test_overlay_skips_tracks_with_too_few_points(monkeypatch):
    monkeypatch.setenv("THUMBNAIL_TILE_URL", "")
    short_track = _points([(43.55, 10.30)])  # only 1 usable point
    data = t.render_overlay_thumbnail([short_track, _points(TRACK)])
    assert isinstance(data, bytes)
    img = _open_png(data)
    assert img.size == t.THUMB_SIZE


def test_overlay_returns_none_when_no_track_qualifies(monkeypatch):
    monkeypatch.setenv("THUMBNAIL_TILE_URL", "")
    empty_ish = [
        _points([(43.55, 10.30)]),
        _points([]),
        [{"lat": None, "lon": None}],
    ]
    assert t.render_overlay_thumbnail(empty_ish) is None

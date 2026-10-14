"""``hull_type`` and ``silhouette`` on the boat embedded in the replay data
endpoints (``activity_sensor_data``), resolved once per distinct boat class.

Database-free: ``backend.routers`` is pre-seeded as a bare package so
``_common`` imports without Postgres, and the repos are fakes.
"""

import importlib
import sys
import types
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def common(monkeypatch):
    pkg = types.ModuleType("backend.routers")
    pkg.__path__ = [str(Path(__file__).resolve().parents[2] / "backend" / "routers")]
    monkeypatch.setitem(sys.modules, "backend.routers", pkg)
    monkeypatch.delitem(sys.modules, "backend.routers._common", raising=False)
    monkeypatch.setattr("backend.repositories.get_repos", lambda: types.SimpleNamespace())
    return importlib.import_module("backend.routers._common")


class FakeBoats:
    def __init__(self, boats, classes):
        self.boats, self.classes, self.class_calls = boats, classes, []

    def get(self, boat_id):
        return self.boats.get(boat_id)

    def get_class(self, class_id):
        self.class_calls.append(class_id)
        return self.classes.get(class_id)


def _boat(class_id):
    return types.SimpleNamespace(id=uuid.uuid4(), name="B", sail_number="1",
                                 boat_class_id=class_id)


def _cls(hull_type, silhouette=None):
    return types.SimpleNamespace(hull_type=hull_type, silhouette=silhouette)


@pytest.mark.parametrize("hull_type,silhouette", [
    ("multihull", "nacra17"), ("monohull", "ilca"), ("monohull", None), (None, None),
])
def test_helper_returns_class_shape(common, monkeypatch, hull_type, silhouette):
    cid = uuid.uuid4()
    monkeypatch.setattr(common, "repos", types.SimpleNamespace(
        boats=FakeBoats({}, {cid: _cls(hull_type, silhouette)})))
    assert common._class_shape(cid, {}) == {"hull_type": hull_type, "silhouette": silhouette}


def test_helper_without_class_is_none_and_skips_lookup(common, monkeypatch):
    boats = FakeBoats({}, {})
    monkeypatch.setattr(common, "repos", types.SimpleNamespace(boats=boats))
    assert common._class_shape(None, {}) == {"hull_type": None, "silhouette": None}
    assert boats.class_calls == []


def test_helper_with_missing_class_is_none(common, monkeypatch):
    monkeypatch.setattr(common, "repos", types.SimpleNamespace(boats=FakeBoats({}, {})))
    assert common._class_shape(uuid.uuid4(), {}) == {"hull_type": None, "silhouette": None}


def test_activity_sensor_data_embeds_hull_type_with_one_lookup_per_class(common, monkeypatch):
    from backend.services import nav_source, physio

    multi, mono = uuid.uuid4(), uuid.uuid4()
    boats = [_boat(multi), _boat(multi), _boat(mono), _boat(None)]
    sessions = [types.SimpleNamespace(id=uuid.uuid4(), boat_id=b.id) for b in boats]
    fake_boats = FakeBoats({b.id: b for b in boats},
                           {multi: _cls("multihull", "f18"), mono: _cls("monohull")})
    monkeypatch.setattr(common, "repos", types.SimpleNamespace(
        boats=fake_boats, sessions=types.SimpleNamespace(list=lambda activity_id: sessions)))
    monkeypatch.setattr(nav_source, "resolve_nav_streams", lambda sid: {})
    monkeypatch.setattr(physio, "visible_physio_streams", lambda s, u: [])

    out = common.activity_sensor_data(uuid.uuid4(), "gps", None, None)

    hulls = [out[str(s.id)]["boat"]["hull_type"] for s in sessions]
    assert hulls == ["multihull", "multihull", "monohull", None]
    shapes = [out[str(s.id)]["boat"]["silhouette"] for s in sessions]
    assert shapes == ["f18", "f18", None, None]
    assert sorted(fake_boats.class_calls, key=str) == sorted([multi, mono], key=str)

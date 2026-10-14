"""Every default class -> silhouette mapping points at a drawing the frontend
actually has.

The drawings are frontend data (``boatSilhouettes.ts``) while the defaults live
in the seed script's JSON and in migration ``0068``'s frozen copy of it, so
nothing else connects the two: a typo'd or renamed id would store fine and then
silently draw the generic hull. Database-free.
"""

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPECS_TS = ROOT / "frontend/src/components/race/boatSilhouettes.ts"
MAPPING_JSON = ROOT / "scripts/data/class_silhouettes.json"
MIGRATION = ROOT / "backend/alembic/versions/0068_boat_class_silhouette.py"
ID_PATTERN = re.compile(r"^[a-z0-9_]{1,40}$")  # schemas.boat.BoatClassWriteModel


def _frontend_ids() -> set[str]:
    block = SPECS_TS.read_text().split("export const SILHOUETTE_SPECS = {", 1)[1]
    return set(re.findall(r'^  "?([a-z0-9_]+)"?: \{', block, re.MULTILINE))


def _migration():
    spec = importlib.util.spec_from_file_location("migration_0068", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frontend_ids_parse_and_are_storable():
    ids = _frontend_ids()
    assert {"ilca", "470", "49er", "nacra17", "optimist", "tornado"} <= ids
    assert all(ID_PATTERN.match(i) for i in ids)


def test_seed_mapping_targets_exist():
    mapping = json.loads(MAPPING_JSON.read_text())
    ids = _frontend_ids()
    targets = set(mapping["by_rya_class_id"].values()) | set(mapping["by_name"].values())
    assert targets - ids == set()


def test_seed_mapping_names_are_normalised():
    # Both the seed script and the migration compare against lower(trim(name)).
    names = json.loads(MAPPING_JSON.read_text())["by_name"]
    assert all(n == n.strip().lower() for n in names)


def test_migration_mapping_targets_exist():
    m = _migration()
    ids = _frontend_ids()
    assert set(m.BY_RYA_CLASS_ID.values()) - ids == set()
    assert set(m.BY_NAME.values()) - ids == set()

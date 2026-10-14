"""``boat_classes.silhouette``: the class-specific drawing of the replay map.

Nullable and unconstrained — the catalogue of drawings is frontend data
(``frontend/src/components/race/boatSilhouettes.ts``) and an id it does not
know falls back to the generic hull for ``hull_type``. Backfills the classes
an install already has, by RYA Class ID first and then by name; a frozen copy
of ``scripts/data/class_silhouettes.json``, which the seed script keeps using
for classes created after this revision.

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0068'
down_revision: Union[str, None] = '0067'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BY_RYA_CLASS_ID = {
    2: 'dinghy_12',
    7: '29er',
    8: '29er',
    12: '420',
    13: '470',
    14: '49er',
    15: '49er',
    16: '49er',
    17: '505',
    19: 'a_class',
    20: 'a_class',
    95: 'dart18',
    96: 'dart18',
    111: 'europe',
    122: 'f18',
    123: 'f18',
    124: 'f18',
    125: 'f18',
    126: 'f18',
    127: 'f18',
    132: 'finn',
    133: 'fireball',
    139: 'flying_dutchman',
    143: 'flying_junior',
    171: 'hobie14',
    172: 'hobie14',
    174: 'hobie16',
    189: 'ilca',
    190: 'ilca',
    191: 'ilca',
    196: 'moth',
    197: 'moth',
    266: 'nacra15',
    267: 'nacra17',
    268: 'nacra17',
    280: 'ok',
    282: 'optimist',
    311: 'rs_aero',
    312: 'rs_aero',
    313: 'rs_aero',
    317: 'rs_feva',
    318: 'rs_feva',
    348: 'snipe',
    379: 'topper',
    397: 'tornado',
    398: 'tornado',
    407: 'vaurien',
    408: 'vaurien',
    413: 'waszp',
    455: 'rs_aero',
    465: '420',
    484: 'hobie16',
    492: 'rs_feva',
    526: 'rs_feva',
    528: 'rs_feva',
    533: 'tornado',
    540: 'nacra17',
    541: 'nacra17',
}

BY_NAME = {
    '12ft dinghy': 'dinghy_12',
    '29er': '29er',
    '420': '420',
    '470': '470',
    '49er': '49er',
    '49er fx': '49er',
    '49erfx': '49er',
    '505': '505',
    '5o5': '505',
    'a class': 'a_class',
    'a-class': 'a_class',
    'dart 18': 'dart18',
    'dinghy 12': 'dinghy_12',
    "dinghy 12'": 'dinghy_12',
    'europe': 'europe',
    'f18': 'f18',
    'finn': 'finn',
    'fireball': 'fireball',
    'flying dutchman': 'flying_dutchman',
    'flying junior': 'flying_junior',
    'formula kite': 'formula_kite',
    'hobie 14': 'hobie14',
    'hobie 16': 'hobie16',
    'hobie cat 14': 'hobie14',
    'hobie cat 16': 'hobie16',
    'ilca': 'ilca',
    'ilca 4': 'ilca',
    'ilca 6': 'ilca',
    'ilca 7': 'ilca',
    'international moth': 'moth',
    'iqfoil': 'iqfoil',
    'iqfoil 85': 'iqfoil',
    'iqfoil 95': 'iqfoil',
    'laser': 'ilca',
    'laser radial': 'ilca',
    'laser standard': 'ilca',
    'moth': 'moth',
    'nacra 15': 'nacra15',
    'nacra 17': 'nacra17',
    'ok': 'ok',
    'ok dinghy': 'ok',
    'optimist': 'optimist',
    'rs aero': 'rs_aero',
    'rs feva': 'rs_feva',
    'snipe': 'snipe',
    'star': 'star',
    'topper': 'topper',
    'tornado': 'tornado',
    'tornado sport': 'tornado',
    'vaurien': 'vaurien',
    'waszp': 'waszp',
}


def upgrade() -> None:
    op.add_column('boat_classes', sa.Column('silhouette', sa.String(), nullable=True))
    conn = op.get_bind()
    for rya_id, silhouette in BY_RYA_CLASS_ID.items():
        conn.execute(
            sa.text("UPDATE boat_classes SET silhouette = :s "
                    "WHERE rya_class_id = :id AND silhouette IS NULL"),
            {"s": silhouette, "id": rya_id},
        )
    for name, silhouette in BY_NAME.items():
        conn.execute(
            sa.text("UPDATE boat_classes SET silhouette = :s "
                    "WHERE lower(trim(name)) = :n AND silhouette IS NULL"),
            {"s": silhouette, "n": name},
        )


def downgrade() -> None:
    op.drop_column('boat_classes', 'silhouette')

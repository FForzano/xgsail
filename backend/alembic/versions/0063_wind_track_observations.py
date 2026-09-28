"""``wind_track_observations`` — wind directions inferred from a session's
own tacks/gybes, shared with other sessions sailed nearby at the same time.

The analysis worker reads the true wind direction off each maneuver (the
bisector of the headings either side of a tack or gybe) and posts it with the
session's analysis. Each session owns its set: the backend deletes and
re-inserts it on every analysis upsert, so reprocessing replaces rather than
accumulates — unlike ``wind_estimates``, whose merge double-counts a re-run.

``session_id`` is ``ON DELETE CASCADE`` so deleting a session (and a GDPR
erasure that deletes its sessions) removes its observations with it. No
PostGIS: the neighbour lookup is an ``observed_at`` range plus a lat/lng
bounding box in SQL, then an exact haversine in Python.

Revision ID: 0063
Revises: 0062
Create Date: 2026-09-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0063'
down_revision: Union[str, None] = '0062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wind_track_observations',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('session_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('twd_deg', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "kind IN ('tack', 'gybe')",
            name=op.f('ck_wind_track_observations_kind_allowed'),
        ),
        sa.ForeignKeyConstraint(
            ['session_id'], ['sessions.id'],
            name=op.f('fk_wind_track_observations_session_id_sessions'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_wind_track_observations')),
    )
    op.create_index(op.f('ix_wind_track_observations_session_id'),
                    'wind_track_observations', ['session_id'])
    op.create_index(op.f('ix_wind_track_observations_observed_at'),
                    'wind_track_observations', ['observed_at'])


def downgrade() -> None:
    op.drop_index(op.f('ix_wind_track_observations_observed_at'),
                  table_name='wind_track_observations')
    op.drop_index(op.f('ix_wind_track_observations_session_id'),
                  table_name='wind_track_observations')
    op.drop_table('wind_track_observations')

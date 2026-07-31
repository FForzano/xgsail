"""Support official/published regatta standings.

Organizers can publish an "official" standings for a regatta that takes
precedence over auto-calculated results. This is useful for:
- Regattas scored manually (on paper) with no GPS tracks
- Races with redress/protest decisions applied manually
- Events where the scoring system differs from XGSail's default

The official standings are stored as rows in ``official_standings``, keyed
on (regatta_id, boat_id), allowing per-boat override/position/score without
duplicating the entire standings structure.

When official standings exist for a regatta, the standings endpoint returns
them instead of computed ones. Manual override of individual boats is possible
by updating rows; deleting all rows reverts to computed standings.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0044'
down_revision: Union[str, None] = '0043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'official_standings',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('regatta_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('boat_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),  # dnf, dns, dsq, etc (optional)
        sa.Column('created_by', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['regatta_id'], ['regattas.id'],
            name=op.f('fk_official_standings_regatta_id_regattas'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['boat_id'], ['boats.id'],
            name=op.f('fk_official_standings_boat_id_boats'), ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name=op.f('fk_official_standings_created_by_users'), ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_official_standings')),
        sa.UniqueConstraint('regatta_id', 'boat_id',
                            name=op.f('uq_official_standings_regatta_boat')),
    )
    op.create_index(op.f('ix_official_standings_regatta_id'), 'official_standings',
                    ['regatta_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_official_standings_regatta_id'), table_name='official_standings')
    op.drop_table('official_standings')

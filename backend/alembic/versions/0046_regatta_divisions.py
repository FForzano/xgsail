"""Per-regatta scoring divisions ("categorie") with separate rankings.

A club regatta is routinely split into categories — "Catamarani",
"Catamarani veloci", "Derive" — that start together but are ranked apart, and
sometimes sail a different number of laps of the same course. The labels are
free-form and owned by the regatta, deliberately NOT the global
``boat_classes`` catalog: the same class can land in different divisions at
different events. ``regattas.class_id`` is unchanged.

``regatta_entries.division_id`` is the single source of truth for which ranking
a boat is in, so ``results`` gets no division column of its own.
``races.division_id`` is NULL for the normal case (one race, separate starts,
counts for every division) and set only when a race is reserved to one.

No backfill: every new column is nullable and NULL means exactly today's
semantics — a regatta with no divisions behaves as before.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0046'
down_revision: Union[str, None] = '0045'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables gaining a nullable FK to regatta_divisions. SET NULL everywhere:
# deleting a division must never delete a start list, a race or a standing.
_DIVISION_REFS = ('regatta_entries', 'races', 'official_standings')


def upgrade() -> None:
    op.create_table(
        'regatta_divisions',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('regatta_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('laps', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['regatta_id'], ['regattas.id'],
            name=op.f('fk_regatta_divisions_regatta_id_regattas'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_regatta_divisions')),
        sa.UniqueConstraint('regatta_id', 'name',
                            name=op.f('uq_regatta_divisions_regatta_id_name')),
        sa.CheckConstraint('laps IS NULL OR laps > 0',
                           name=op.f('ck_regatta_divisions_laps_positive')),
    )
    op.create_index(op.f('ix_regatta_divisions_regatta_id'), 'regatta_divisions',
                    ['regatta_id'])

    for table in _DIVISION_REFS:
        op.add_column(table, sa.Column('division_id', sa.Uuid(as_uuid=True), nullable=True))
        op.create_foreign_key(
            op.f(f'fk_{table}_division_id_regatta_divisions'), table, 'regatta_divisions',
            ['division_id'], ['id'], ondelete='SET NULL',
        )
        op.create_index(op.f(f'ix_{table}_division_id'), table, ['division_id'])


def downgrade() -> None:
    for table in _DIVISION_REFS:
        op.drop_index(op.f(f'ix_{table}_division_id'), table_name=table)
        op.drop_constraint(op.f(f'fk_{table}_division_id_regatta_divisions'), table,
                           type_='foreignkey')
        op.drop_column(table, 'division_id')

    op.drop_index(op.f('ix_regatta_divisions_regatta_id'), table_name='regatta_divisions')
    op.drop_table('regatta_divisions')

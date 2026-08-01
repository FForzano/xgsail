"""Manual (paper) regatta entries: nullable ``boat_id`` + manual name fields.

An organizer must be able to pre-populate a start list with boats that have no
XGSail boat record yet, so ``regatta_entries.boat_id`` becomes nullable and the
boat is instead captured as ``boat_name``/``sail_number``.

Uniqueness therefore splits into two partial indexes over disjoint populations:
``(regatta_id, boat_id)`` where a boat is linked, and
``(regatta_id, boat_name_normalized)`` where it is not. ``boat_name_normalized``
is bookkeeping written by the repository ("name|sail", lower/trimmed) rather
than a generated column: normalization lives in Python next to the idempotency
check that reads it, so the two can never drift.

Existing rows all have a non-NULL ``boat_id``, so they keep NULL in the manual
columns and fall outside the ``boat_id IS NULL`` index entirely.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0043'
down_revision: Union[str, None] = '0042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('regatta_entries', 'boat_id', existing_type=sa.Uuid(as_uuid=True),
                    nullable=True)

    op.add_column('regatta_entries', sa.Column('boat_name', sa.String(), nullable=True))
    op.add_column('regatta_entries', sa.Column('sail_number', sa.String(), nullable=True))
    op.add_column('regatta_entries',
                  sa.Column('boat_name_normalized', sa.String(), nullable=True))

    op.create_check_constraint(
        'boat_id_or_boat_name', 'regatta_entries',
        'boat_id IS NOT NULL OR boat_name IS NOT NULL',
    )

    op.drop_constraint(op.f('uq_regatta_entries_regatta_id_boat_id'),
                       'regatta_entries', type_='unique')

    op.create_index('uq_regatta_entries_regatta_boat', 'regatta_entries',
                    ['regatta_id', 'boat_id'], unique=True,
                    postgresql_where=sa.text('boat_id IS NOT NULL'))
    op.create_index('uq_regatta_entries_regatta_manual_name', 'regatta_entries',
                    ['regatta_id', 'boat_name_normalized'], unique=True,
                    postgresql_where=sa.text('boat_id IS NULL'))


def downgrade() -> None:
    # Destructive: manual entries cannot survive ``boat_id`` going back to
    # NOT NULL, so they are dropped rather than silently invented a boat for.
    op.execute('DELETE FROM regatta_entries WHERE boat_id IS NULL')

    op.drop_index('uq_regatta_entries_regatta_manual_name', table_name='regatta_entries')
    op.drop_index('uq_regatta_entries_regatta_boat', table_name='regatta_entries')
    op.create_unique_constraint(op.f('uq_regatta_entries_regatta_id_boat_id'),
                                'regatta_entries', ['regatta_id', 'boat_id'])

    op.drop_constraint(op.f('ck_regatta_entries_boat_id_or_boat_name'), 'regatta_entries',
                       type_='check')

    op.drop_column('regatta_entries', 'boat_name_normalized')
    op.drop_column('regatta_entries', 'sail_number')
    op.drop_column('regatta_entries', 'boat_name')

    op.alter_column('regatta_entries', 'boat_id', existing_type=sa.Uuid(as_uuid=True),
                    nullable=False)

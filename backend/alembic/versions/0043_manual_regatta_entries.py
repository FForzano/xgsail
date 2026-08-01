"""Support manual (non-app-user) regatta entries.

Adds `boat_name` and `sail_number` columns to `regatta_entries`, allowing
organizers to add participants without requiring a boat account in the system.

``boat_id`` becomes nullable to support entries that are not tied to a specific
boat record. Uniqueness constraints become partial:
- Linked entries: unique on (regatta_id, boat_id) when boat_id IS NOT NULL
- Manual entries: unique on normalized (regatta_id, boat_name, sail_number) when boat_id IS NULL

The invariant CHECK ensures an entry must identify a boat one way or the other:
boat_id IS NOT NULL OR (boat_name IS NOT NULL AND btrim(boat_name) <> '')

Downgrade deletes all manual entries (boat_id IS NULL) to restore NOT NULL constraint.

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
    # Make boat_id nullable
    op.alter_column('regatta_entries', 'boat_id', existing_type=sa.Uuid(as_uuid=True),
                    nullable=True)

    # Add new columns for manual entries
    op.add_column('regatta_entries', sa.Column('boat_name', sa.String(), nullable=True))
    op.add_column('regatta_entries', sa.Column('sail_number', sa.String(), nullable=True))

    # Add CHECK constraint: must have either boat_id or boat_name
    op.create_check_constraint(
        'ck_regatta_entries_boat_ref_present', 'regatta_entries',
        "boat_id IS NOT NULL OR (boat_name IS NOT NULL AND btrim(boat_name) <> '')",
    )

    # Drop the old non-partial unique constraint
    op.drop_constraint(op.f('uq_regatta_entries_regatta_id_boat_id'),
                       'regatta_entries', type_='unique')

    # Create partial unique index for linked entries (boat_id IS NOT NULL)
    op.create_index(op.f('uq_regatta_entries_regatta_id_boat_id'), 'regatta_entries',
                    ['regatta_id', 'boat_id'], unique=True,
                    postgresql_where=sa.text('boat_id IS NOT NULL'))

    # Create partial unique index for manual entries (normalized name+sail when boat_id IS NULL)
    op.create_index(
        'uq_regatta_entries_manual_name', 'regatta_entries',
        [sa.text('regatta_id'), sa.text('lower(btrim(boat_name))'),
         sa.text("lower(coalesce(btrim(sail_number), ''))")],
        unique=True, postgresql_where=sa.text('boat_id IS NULL'),
    )


def downgrade() -> None:
    # Delete manual entries before restoring NOT NULL constraint
    # This is destructive: downgrade removes all entries with boat_id IS NULL
    op.execute('DELETE FROM regatta_entries WHERE boat_id IS NULL')

    # Drop the partial unique indexes
    op.drop_index('uq_regatta_entries_manual_name', table_name='regatta_entries')
    op.drop_index(op.f('uq_regatta_entries_regatta_id_boat_id'), table_name='regatta_entries')

    # Recreate the old non-partial unique constraint
    op.create_unique_constraint(op.f('uq_regatta_entries_regatta_id_boat_id'),
                                'regatta_entries', ['regatta_id', 'boat_id'])

    # Drop the CHECK constraint
    op.drop_constraint(op.f('ck_regatta_entries_boat_ref_present'), 'regatta_entries',
                       type_='check')

    # Drop new columns
    op.drop_column('regatta_entries', 'sail_number')
    op.drop_column('regatta_entries', 'boat_name')

    # Restore boat_id NOT NULL
    op.alter_column('regatta_entries', 'boat_id', existing_type=sa.Uuid(as_uuid=True),
                    nullable=False)

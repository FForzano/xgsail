"""``boat_notes``: a boat's rig-tuning notebook — multiple free-text entries
(title + body) with an explicit ``position`` for ordering, replacing the
single ``boats.notes`` text column.

Data move (before the drop, so nothing existing is lost): every boat with a
non-blank ``notes`` value gets one ``boat_notes`` row seeded from it (title
"Note", position 0). Boats with a NULL/blank ``notes`` get nothing.
``boats.notes`` is then dropped.

Downgrade re-adds ``boats.notes`` and best-effort restores it from each
boat's first note (by position, then created_at) — it can only carry one
entry back into a single column, so any boat with more than one note loses
the rest on downgrade.

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0047'
down_revision: Union[str, None] = '0046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'boat_notes',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('boat_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['boat_id'], ['boats.id'],
            name=op.f('fk_boat_notes_boat_id_boats'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_boat_notes')),
    )
    op.create_index(op.f('ix_boat_notes_boat_id'), 'boat_notes', ['boat_id'])

    op.execute("""
        INSERT INTO boat_notes (id, boat_id, title, body, position, created_at, updated_at)
        SELECT gen_random_uuid(), id, 'Note', notes, 0, now(), now()
        FROM boats WHERE notes IS NOT NULL AND btrim(notes) <> ''
    """)

    op.drop_column('boats', 'notes')


def downgrade() -> None:
    op.add_column('boats', sa.Column('notes', sa.Text(), nullable=True))

    op.execute("""
        UPDATE boats SET notes = (
            SELECT bn.body FROM boat_notes bn WHERE bn.boat_id = boats.id
            ORDER BY bn.position, bn.created_at LIMIT 1
        )
    """)

    op.drop_index(op.f('ix_boat_notes_boat_id'), table_name='boat_notes')
    op.drop_table('boat_notes')

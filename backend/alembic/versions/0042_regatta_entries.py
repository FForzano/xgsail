"""Regatta start list (``regatta_entries``) + per-regatta share code.

Lets a sailor tag a recording with the race they are sailing, which until now
was impossible: the "Registra" picker only offered the user's own activities,
and ``attach_to_activity`` gated on ``can_edit_activity`` — so no participant,
member or not, could attach to a club's race activity.

``regatta_entries`` is the missing "this boat is expected at this event"
statement. It keys on the BOAT, not on club membership, because a club's
regatta is regularly sailed by visitors from other clubs. It is separate from
``results`` on purpose: results carry scoring and pre-created rows would show
up in the standings before the racing.

``regattas.join_code`` is the self-service half — an organizer cannot realistically
pre-enter every visiting boat, so a share link lets sailors add their own boat.
NULL means "no code / revoked"; regenerating overwrites it and invalidates any
link already circulated.

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0042'
down_revision: Union[str, None] = '0041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('regattas', sa.Column('join_code', sa.String(), nullable=True))
    op.create_unique_constraint(op.f('uq_regattas_join_code'), 'regattas', ['join_code'])

    op.create_table(
        'regatta_entries',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('regatta_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('boat_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('created_by', sa.Uuid(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['regatta_id'], ['regattas.id'],
            name=op.f('fk_regatta_entries_regatta_id_regattas'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['boat_id'], ['boats.id'],
            name=op.f('fk_regatta_entries_boat_id_boats'), ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name=op.f('fk_regatta_entries_created_by_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_regatta_entries')),
        sa.UniqueConstraint('regatta_id', 'boat_id',
                            name=op.f('uq_regatta_entries_regatta_id_boat_id')),
        sa.CheckConstraint("source IN ('organizer', 'code')",
                           name=op.f('ck_regatta_entries_source_allowed')),
    )
    op.create_index(op.f('ix_regatta_entries_regatta_id'), 'regatta_entries', ['regatta_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_regatta_entries_regatta_id'), table_name='regatta_entries')
    op.drop_table('regatta_entries')
    op.drop_constraint(op.f('uq_regattas_join_code'), 'regattas', type_='unique')
    op.drop_column('regattas', 'join_code')

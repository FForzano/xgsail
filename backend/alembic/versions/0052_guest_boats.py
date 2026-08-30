"""Guest boats (``boats.is_guest``/``guest_created_by``) and ``boat_claims``.

A guest boat is a placeholder created by someone who does not own the boat, so
an outing can be recorded against it; the real owner takes it over through a
``boat_claims`` request the creator approves. The pending-claim uniqueness is a
partial index so a rejected claim can be filed again.

No index on ``boats.is_guest``: guest boats are a minority of an already small
table, and the claim flows all key on a specific ``boat_id``/``user_id`` — a
boolean index would be dead weight rather than a win.

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0052'
down_revision: Union[str, None] = '0051'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'boats',
        sa.Column('is_guest', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('boats', 'is_guest', server_default=None)
    op.add_column('boats', sa.Column('guest_created_by', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f('fk_boats_guest_created_by_users'),
        'boats', 'users', ['guest_created_by'], ['id'], ondelete='SET NULL',
    )

    op.create_table(
        'boat_claims',
        sa.Column('boat_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('target_boat_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.Uuid(), nullable=True),
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'target_boat_id IS NULL OR target_boat_id <> boat_id',
            name=op.f('ck_boat_claims_target_boat_not_self'),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name=op.f('ck_boat_claims_status_allowed'),
        ),
        sa.ForeignKeyConstraint(
            ['boat_id'], ['boats.id'],
            name=op.f('fk_boat_claims_boat_id_boats'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['resolved_by'], ['users.id'],
            name=op.f('fk_boat_claims_resolved_by_users'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['target_boat_id'], ['boats.id'],
            name=op.f('fk_boat_claims_target_boat_id_boats'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_boat_claims_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_boat_claims')),
    )
    op.create_index(op.f('ix_boat_claims_boat_id'), 'boat_claims', ['boat_id'], unique=False)
    op.create_index(op.f('ix_boat_claims_user_id'), 'boat_claims', ['user_id'], unique=False)
    op.create_index(
        'uq_boat_claims_boat_user_pending',
        'boat_claims', ['boat_id', 'user_id'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_boat_claims_boat_user_pending',
        table_name='boat_claims',
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(op.f('ix_boat_claims_user_id'), table_name='boat_claims')
    op.drop_index(op.f('ix_boat_claims_boat_id'), table_name='boat_claims')
    op.drop_table('boat_claims')

    op.drop_constraint(op.f('fk_boats_guest_created_by_users'), 'boats', type_='foreignkey')
    op.drop_column('boats', 'guest_created_by')
    op.drop_column('boats', 'is_guest')

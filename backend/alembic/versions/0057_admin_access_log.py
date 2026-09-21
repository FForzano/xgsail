"""``admin_access_log`` — which superadmin read which user's data.

The operator can inspect any registered user's profile, boats, activities and
sessions for diagnostics (``backend/routers/admin.py``). That access is broad
and invisible to its subject, so each of those reads appends one row here.

Append-only: nothing in the application updates or deletes a row. Both foreign
keys are ``ON DELETE SET NULL`` rather than CASCADE — deleting either party
must not erase the evidence that the access happened — while still leaving a
user erasable, which ``RESTRICT`` would not.

Revision ID: 0057
Revises: 0056
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0057'
down_revision: Union[str, None] = '0056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_access_log',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('actor_user_id', sa.Uuid(as_uuid=True), nullable=True),
        sa.Column('target_user_id', sa.Uuid(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "action IN ('user.detail', 'user.boats', 'user.activities', 'user.sessions')",
            name=op.f('ck_admin_access_log_action_allowed'),
        ),
        sa.ForeignKeyConstraint(
            ['actor_user_id'], ['users.id'],
            name=op.f('fk_admin_access_log_actor_user_id_users'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['target_user_id'], ['users.id'],
            name=op.f('fk_admin_access_log_target_user_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_access_log')),
    )
    op.create_index(op.f('ix_admin_access_log_actor_user_id'), 'admin_access_log',
                    ['actor_user_id'])
    op.create_index(op.f('ix_admin_access_log_target_user_id'), 'admin_access_log',
                    ['target_user_id'])
    # The listing is "newest first, optionally one subject": the filter uses the
    # index above, the ordering this one.
    op.create_index('ix_admin_access_log_created_at', 'admin_access_log', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_admin_access_log_created_at', table_name='admin_access_log')
    op.drop_index(op.f('ix_admin_access_log_target_user_id'), table_name='admin_access_log')
    op.drop_index(op.f('ix_admin_access_log_actor_user_id'), table_name='admin_access_log')
    op.drop_table('admin_access_log')

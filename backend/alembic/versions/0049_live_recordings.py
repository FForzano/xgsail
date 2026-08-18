"""``live_recordings`` — presence for in-progress recordings, per boat.

Lets the app show "X is recording on this boat right now" so a second crew
member can join the same outing deliberately, instead of finding out after
upload that their track was merged into it by
``services/ingestion.py::find_or_create_session``.

Deliberately *not* a session: no row here creates or reserves anything in
``sessions``/``activities``, so an abandoned recording leaves no empty session
behind. Liveness is derived at read time from ``last_seen_at`` (see
``db/models/live_recording.py``), so there is no cleanup job to schedule; the
unique key on (boat, user) keeps the table bounded by who records, not by how
many recordings have ever been made.

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0049'
down_revision: Union[str, None] = '0048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'live_recordings',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'),
                  nullable=False),
        sa.Column('boat_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('activity_id', sa.Uuid(as_uuid=True), nullable=True),
        sa.Column('client_recording_id', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['boat_id'], ['boats.id'],
            name=op.f('fk_live_recordings_boat_id_boats'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_live_recordings_user_id_users'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['activity_id'], ['activities.id'],
            name=op.f('fk_live_recordings_activity_id_activities'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_live_recordings')),
        sa.UniqueConstraint('boat_id', 'user_id',
                            name=op.f('uq_live_recordings_boat_id_user_id')),
    )
    op.create_index(op.f('ix_live_recordings_boat_id'), 'live_recordings', ['boat_id'])
    op.create_index(op.f('ix_live_recordings_last_seen_at'), 'live_recordings',
                    ['last_seen_at'])


def downgrade() -> None:
    op.drop_index(op.f('ix_live_recordings_last_seen_at'), table_name='live_recordings')
    op.drop_index(op.f('ix_live_recordings_boat_id'), table_name='live_recordings')
    op.drop_table('live_recordings')

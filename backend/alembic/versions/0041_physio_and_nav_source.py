"""Personal health data + a single navigation source per session.

Two related additions, one migration because both are driven by the same
scenario: a session that receives data from a boat tracker *and* one Apple
Watch per crew member.

Health side — the watch's physiological streams (heart_rate/energy/hrv/
respiration) already land in ``session_streams``, but nothing aggregated them
and nothing kept them private:
  * ``session_uploads.physio_shared`` — opt-in that lets the session's crew/boat
    managers see this crew member's physiological data (private otherwise, same
    shape as ``sessions.notes_shared``). See ``auth.session_physio_visible_to``.
  * ``session_physio_stats`` — per-crew-member aggregates, PK'd on the upload so
    two wearers aboard get a row each. Not columns on ``session_stats``: that is
    1:1 with the session and is served to everyone who can see it.
  * ``users.resting_hr_bpm`` / ``users.max_hr_bpm`` — optional, self-reported,
    used only to derive heart-rate zones (``services/hr_zones.py``); ``dob``
    already existed and covers the age-based estimate.

Navigation side — ``sessions.primary_nav_upload_id`` names which upload's GPS is
THE track of the session. Several ``gps`` streams per session are legitimate,
but the map/GPX/replay/analysis must all read one; NULL falls back to the
deterministic ranking in ``services/nav_source.py``.

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0041'
down_revision: Union[str, None] = '0040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'session_uploads',
        sa.Column('physio_shared', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('session_uploads', 'physio_shared', server_default=None)

    op.add_column('users', sa.Column('resting_hr_bpm', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('max_hr_bpm', sa.Integer(), nullable=True))

    # Named FK added explicitly: sessions <-> session_uploads is a cycle
    # (session_uploads.session_id -> sessions), so the constraint cannot be
    # inlined in a CREATE TABLE — the ORM marks it use_alter for the same
    # reason. ON DELETE SET NULL: dropping the chosen upload just reverts the
    # session to the ranked fallback.
    op.add_column('sessions', sa.Column('primary_nav_upload_id', sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f('fk_sessions_primary_nav_upload_id_session_uploads'),
        'sessions', 'session_uploads',
        ['primary_nav_upload_id'], ['id'],
        ondelete='SET NULL',
    )

    op.create_table(
        'session_physio_stats',
        sa.Column('session_upload_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('avg_hr_bpm', sa.Float(), nullable=True),
        sa.Column('max_hr_bpm', sa.Float(), nullable=True),
        sa.Column('min_hr_bpm', sa.Float(), nullable=True),
        sa.Column('total_kcal', sa.Float(), nullable=True),
        sa.Column('avg_kcal_per_min', sa.Float(), nullable=True),
        sa.Column('avg_hrv_ms', sa.Float(), nullable=True),
        sa.Column('avg_resp_brpm', sa.Float(), nullable=True),
        sa.Column('hr_duration_s', sa.Integer(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['session_upload_id'], ['session_uploads.id'],
            name=op.f('fk_session_physio_stats_session_upload_id_session_uploads'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('session_upload_id',
                                name=op.f('pk_session_physio_stats')),
    )


def downgrade() -> None:
    op.drop_table('session_physio_stats')
    op.drop_constraint(
        op.f('fk_sessions_primary_nav_upload_id_session_uploads'),
        'sessions', type_='foreignkey',
    )
    op.drop_column('sessions', 'primary_nav_upload_id')
    op.drop_column('users', 'max_hr_bpm')
    op.drop_column('users', 'resting_hr_bpm')
    op.drop_column('session_uploads', 'physio_shared')

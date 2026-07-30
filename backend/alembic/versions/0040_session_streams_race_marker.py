"""Widen ``session_streams.sensor_type`` to allow ``race_marker`` — the Apple
Watch companion's optional race-mode start-sequence stream (countdown start /
resync / start events, ``watch_race.csv``). Purely observational: never
written to ``races.start_time`` or read by any scoring computation, see
docs/device-protocol.md and workers/process_upload/handler.py::process_events.

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0040'
down_revision: Union[str, None] = '0039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('sensor_type_allowed', 'session_streams', type_='check')
    op.create_check_constraint(
        'sensor_type_allowed', 'session_streams',
        "sensor_type IN ('gps', 'imu', 'wind', 'pressure', 'heart_rate', "
        "'energy', 'hrv', 'respiration', 'race_marker', "
        "'estimated_position', 'estimated_motion', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint('sensor_type_allowed', 'session_streams', type_='check')
    op.create_check_constraint(
        'sensor_type_allowed', 'session_streams',
        "sensor_type IN ('gps', 'imu', 'wind', 'pressure', 'heart_rate', "
        "'energy', 'hrv', 'respiration', "
        "'estimated_position', 'estimated_motion', 'other')",
    )

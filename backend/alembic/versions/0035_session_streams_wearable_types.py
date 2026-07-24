"""Widen ``session_streams.sensor_type`` to allow the wearable physiological
streams ``energy``/``hrv``/``respiration`` — the Apple Watch companion relays
these alongside ``heart_rate`` (and its GPS), see docs/device-protocol.md and
workers/process_upload/handler.py::process_scalar.

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0035'
down_revision: Union[str, None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('sensor_type_allowed', 'session_streams', type_='check')
    op.create_check_constraint(
        'sensor_type_allowed', 'session_streams',
        "sensor_type IN ('gps', 'imu', 'wind', 'pressure', 'heart_rate', "
        "'energy', 'hrv', 'respiration', "
        "'estimated_position', 'estimated_motion', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint('sensor_type_allowed', 'session_streams', type_='check')
    op.create_check_constraint(
        'sensor_type_allowed', 'session_streams',
        "sensor_type IN ('gps', 'imu', 'wind', 'pressure', 'heart_rate', "
        "'estimated_position', 'estimated_motion', 'other')",
    )

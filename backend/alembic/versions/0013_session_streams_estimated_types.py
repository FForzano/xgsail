"""Widen ``session_streams.sensor_type`` to allow ``estimated_position``/
``estimated_motion`` — the two blob artifacts written by the analysis
pipeline's joint position/motion estimator (see workers/process_upload/
processing/track.py), registered as streams the same way any raw sensor
file is.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('sensor_type_allowed', 'session_streams', type_='check')
    op.create_check_constraint(
        'sensor_type_allowed', 'session_streams',
        "sensor_type IN ('gps', 'imu', 'wind', 'pressure', 'heart_rate', "
        "'estimated_position', 'estimated_motion', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint('sensor_type_allowed', 'session_streams', type_='check')
    op.create_check_constraint(
        'sensor_type_allowed', 'session_streams',
        "sensor_type IN ('gps', 'imu', 'wind', 'pressure', 'heart_rate', 'other')",
    )

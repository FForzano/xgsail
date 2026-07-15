"""Add ``cumulus_gauges_json`` as a wind provider — CumulusMX's JSON
"Steel Series Gauges" export (``realtimegauges.txt``), distinct from the
plain-text ``realtime.txt`` added in 0021. Many real-world CumulusMX
installs only expose this JSON variant, not the classic text one.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0022'
down_revision: Union[str, None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('provider_allowed', 'wind_stations', type_='check')
    op.create_check_constraint(
        'provider_allowed', 'wind_stations',
        "provider IN ('noaa_ndbc', 'noaa_metar', 'custom_device', 'cumulus_realtime', "
        "'cumulus_gauges_json')",
    )


def downgrade() -> None:
    op.drop_constraint('provider_allowed', 'wind_stations', type_='check')
    op.create_check_constraint(
        'provider_allowed', 'wind_stations',
        "provider IN ('noaa_ndbc', 'noaa_metar', 'custom_device', 'cumulus_realtime')",
    )

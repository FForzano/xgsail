"""Add support for Cumulus realtime.txt weather stations as a wind provider.

- ``wind_stations.provider`` gains ``cumulus_realtime`` — a real,
  fixed-position station polled over HTTP, same "raw acquisition" category
  as NDBC/METAR (see ``backend/db/models/wind.py`` module docstring).
- ``wind_stations.source_url`` — nullable, holds the realtime.txt endpoint
  to poll. Only URL-based providers (currently just ``cumulus_realtime``)
  populate it; NDBC/METAR keep using ``external_station_id`` as their
  provider-scoped lookup key.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0021'
down_revision: Union[str, None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'wind_stations',
        sa.Column('source_url', sa.String(), nullable=True),
    )
    op.drop_constraint('provider_allowed', 'wind_stations', type_='check')
    op.create_check_constraint(
        'provider_allowed', 'wind_stations',
        "provider IN ('noaa_ndbc', 'noaa_metar', 'custom_device', 'cumulus_realtime')",
    )


def downgrade() -> None:
    op.drop_constraint('provider_allowed', 'wind_stations', type_='check')
    op.create_check_constraint(
        'provider_allowed', 'wind_stations',
        "provider IN ('noaa_ndbc', 'noaa_metar', 'custom_device')",
    )
    op.drop_column('wind_stations', 'source_url')

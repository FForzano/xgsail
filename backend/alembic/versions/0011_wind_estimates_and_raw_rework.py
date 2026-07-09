"""Rework wind data model: separate raw acquisition from determined estimate.

- ``wind_stations``/``wind_observations`` narrow to real, fixed-position
  stations only (NOAA NDBC/METAR, custom device) — Open-Meteo is an
  algorithmic API queried on demand for any lat/lng with its own accessible
  history, never a "station" to cache. Existing ``open_meteo`` rows are
  dropped (dev data from earlier experimentation).
- ``wind_stations.keeps_local_history`` — per-station flag: do we need to
  persist this station's readings ourselves, or can we always query it live.
- ``wind_observations.is_forecast`` (added in 0009) is dropped — it existed
  to reconcile provisional Open-Meteo forecast rows against the archive,
  which no longer applies now that Open-Meteo is never persisted raw.
- New ``wind_estimates``: the determined wind for a spatiotemporal grid
  cell, refined over time by a pluggable algorithm (see
  ``services/wind_estimate_refinement.py``) as new raw observations arrive.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing open_meteo rows (cascades to wind_observations) before
    # narrowing the provider/station_type check constraints.
    op.execute("DELETE FROM wind_stations WHERE provider = 'open_meteo'")

    op.drop_constraint('provider_allowed', 'wind_stations', type_='check')
    op.create_check_constraint(
        'provider_allowed', 'wind_stations',
        "provider IN ('noaa_ndbc', 'noaa_metar', 'custom_device')",
    )
    op.drop_constraint('station_type_allowed', 'wind_stations', type_='check')
    op.create_check_constraint(
        'station_type_allowed', 'wind_stations',
        "station_type IN ('buoy', 'metar', 'custom_device')",
    )
    op.add_column(
        'wind_stations',
        sa.Column('keeps_local_history', sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.drop_column('wind_observations', 'is_forecast')

    op.create_table(
        'wind_estimates',
        sa.Column('id', sa.Uuid(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('grid_lat', sa.Float(), nullable=False),
        sa.Column('grid_lng', sa.Float(), nullable=False),
        sa.Column('time_bucket', sa.DateTime(timezone=True), nullable=False),
        sa.Column('twd_deg', sa.Float(), nullable=True),
        sa.Column('tws_kts', sa.Float(), nullable=True),
        sa.Column('gust_kts', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('sources', sa.JSON(), nullable=True),
        sa.Column('refined_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('grid_lat', 'grid_lng', 'time_bucket',
                            name='uq_wind_estimates_grid_lat_grid_lng_time_bucket'),
    )


def downgrade() -> None:
    op.drop_table('wind_estimates')
    op.add_column(
        'wind_observations',
        sa.Column('is_forecast', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_column('wind_stations', 'keeps_local_history')
    op.drop_constraint('station_type_allowed', 'wind_stations', type_='check')
    op.create_check_constraint(
        'station_type_allowed', 'wind_stations',
        "station_type IN ('buoy', 'metar', 'forecast_grid', 'custom_device')",
    )
    op.drop_constraint('provider_allowed', 'wind_stations', type_='check')
    op.create_check_constraint(
        'provider_allowed', 'wind_stations',
        "provider IN ('noaa_ndbc', 'noaa_metar', 'open_meteo', 'custom_device')",
    )

"""Wind provider adapters for the periodic fetch job.

Each adapter is ``fetch(external_station_id) -> list[{observed_at, twd_deg,
tws_kts, gust_kts}]``; the system endpoint iterates the DB ``wind_stations``
of a provider and upserts through the (station, observed_at) unique key.
Add a provider by registering it in ``PROVIDERS``.
"""

from . import ndbc

PROVIDERS = {
    "noaa_ndbc": ndbc.fetch_station,
}

__all__ = ["PROVIDERS"]

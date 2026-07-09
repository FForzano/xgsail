"""Wind provider adapters for the periodic fetch job (real, fixed-position
stations only — see ``db/models/wind.py``).

Each adapter is ``fetch(external_station_id) -> list[{observed_at, twd_deg,
tws_kts, gust_kts}]``; the system endpoint iterates the DB ``wind_stations``
of a provider and upserts through the (station, observed_at) unique key.
Add a provider by registering it in ``PROVIDERS``.

Open-Meteo is *not* here: it's an algorithmic API with no fixed position and
its own accessible history, queried on demand (see ``open_meteo.py``,
imported directly by ``services/wind_lookup.py``/``services/ingestion.py``)
rather than through this periodic-fetch registry.
"""

from . import ndbc

PROVIDERS = {
    "noaa_ndbc": ndbc.fetch_station,
}

__all__ = ["PROVIDERS"]

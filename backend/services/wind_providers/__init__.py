"""Wind provider adapters for the periodic fetch job (real, fixed-position
stations only — see ``db/models/wind.py``).

Each adapter is ``fetch(station: WindStationORM) -> list[{observed_at,
twd_deg, tws_kts, gust_kts}]``; the system endpoint iterates the DB
``wind_stations`` of a provider and upserts through the (station,
observed_at) unique key. Add a provider by registering it in ``PROVIDERS``.
The full station row (not just ``external_station_id``) is passed so
URL-based providers (e.g. ``cumulus_realtime``) can read ``source_url``.

Open-Meteo is *not* here: it's an algorithmic API with no fixed position and
its own accessible history, queried on demand (see ``open_meteo.py``,
imported directly by ``services/wind_lookup.py``/``services/ingestion.py``)
rather than through this periodic-fetch registry.
"""

from . import cumulus_gauges_json, cumulus_realtime, ndbc

PROVIDERS = {
    "noaa_ndbc": ndbc.fetch_station,
    "cumulus_realtime": cumulus_realtime.fetch_station,
    "cumulus_gauges_json": cumulus_gauges_json.fetch_station,
}

# Providers keyed by a per-station URL to poll (``wind_stations.source_url``)
# rather than by ``external_station_id`` against a fixed provider API.
URL_BASED_PROVIDERS = {"cumulus_realtime", "cumulus_gauges_json"}

__all__ = ["PROVIDERS", "URL_BASED_PROVIDERS"]

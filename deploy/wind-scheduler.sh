#!/bin/sh
# Periodic wind-fetch scheduler for the self-hosted stack.
#
# Loops forever with minute granularity; for each provider whose configured
# interval has elapsed, POSTs /api/system/wind/fetch (hook-token auth). The
# backend iterates that provider's wind_stations and upserts observations —
# the unique (station, observed_at) key makes re-runs idempotent, so an
# occasional double fire is harmless.
#
# Real, fixed-position stations only (NOAA NDBC/METAR, custom devices,
# Cumulus realtime.txt/realtimegauges.txt) — Open-Meteo is never persisted,
# it's queried on demand (see backend/services/wind_providers/open_meteo.py),
# so there's nothing for this scheduler to do for it.
#
# Cadence env (minutes):
#   WIND_FETCH_INTERVAL_MIN_NOAA_NDBC            (default 30)
#   WIND_FETCH_INTERVAL_MIN_CUMULUS_REALTIME     (default 5 — realtime.txt/
#   WIND_FETCH_INTERVAL_MIN_CUMULUS_GAUGES_JSON   realtimegauges.txt are
#                                                  regenerated every 5-30s at
#                                                  the source, so a much
#                                                  shorter cadence than NDBC's
#                                                  synoptic data is warranted)
set -eu

BACKEND_URL="${BACKEND_URL:-http://backend:8000}"
TOKEN="${SAILFRAMES_HOOK_TOKEN:?SAILFRAMES_HOOK_TOKEN is required}"

NDBC_INTERVAL_MIN="${WIND_FETCH_INTERVAL_MIN_NOAA_NDBC:-30}"
ndbc_last=0

CUMULUS_INTERVAL_MIN="${WIND_FETCH_INTERVAL_MIN_CUMULUS_REALTIME:-5}"
cumulus_last=0

CUMULUS_GAUGES_INTERVAL_MIN="${WIND_FETCH_INTERVAL_MIN_CUMULUS_GAUGES_JSON:-5}"
cumulus_gauges_last=0

fetch() {
    provider="$1"
    echo "[wind-scheduler] fetching provider=$provider"
    curl -fsS -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"provider\":\"$provider\"}" \
        "$BACKEND_URL/api/system/wind/fetch" \
        || echo "[wind-scheduler] fetch failed for $provider (will retry next cycle)"
    echo ""
}

echo "[wind-scheduler] started (noaa_ndbc every ${NDBC_INTERVAL_MIN}m, cumulus_realtime every ${CUMULUS_INTERVAL_MIN}m, cumulus_gauges_json every ${CUMULUS_GAUGES_INTERVAL_MIN}m)"
while true; do
    now=$(date +%s)
    if [ $((now - ndbc_last)) -ge $((NDBC_INTERVAL_MIN * 60)) ]; then
        fetch "noaa_ndbc"
        ndbc_last=$now
    fi
    if [ $((now - cumulus_last)) -ge $((CUMULUS_INTERVAL_MIN * 60)) ]; then
        fetch "cumulus_realtime"
        cumulus_last=$now
    fi
    if [ $((now - cumulus_gauges_last)) -ge $((CUMULUS_GAUGES_INTERVAL_MIN * 60)) ]; then
        fetch "cumulus_gauges_json"
        cumulus_gauges_last=$now
    fi
    sleep 60
done

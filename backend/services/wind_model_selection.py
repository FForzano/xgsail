"""Pure acquisition of Open-Meteo candidate models — no selection.

Deciding which model (or blend of models) to trust for a session is the
worker's job now (see ``workers/process_upload/processing/wind_estimation.py``),
since that's where the onboard sensor and the GPS track live too. This
module's only responsibility is: query every candidate model, return
whatever came back non-null — "acquisition, not estimation".
"""

from typing import Optional

import requests

FETCH_TIMEOUT_S = 15


def fetch_all_candidates(
    url: str,
    base_params: dict,
    candidates: "tuple[str, ...]",
    gps_points: "Optional[list[tuple[float, float]]]" = None,
) -> "dict[str, dict]":
    """Query every candidate model, return ``{model_name: hourly_dict}`` for
    the ones that actually cover this point (non-null wind data). No
    winner-picking — the caller (ultimately the worker's wind-estimation
    strategy) decides what to do with however many candidates come back.

    ``gps_points`` isn't used by this function directly — kept in the
    signature for parity with ``open_meteo.py``'s callers, which may want to
    log/tag results against the track even though fetching itself doesn't
    depend on it."""
    results: dict[str, dict] = {}
    for model in candidates:
        try:
            resp = requests.get(url, params={**base_params, "models": model},
                                timeout=FETCH_TIMEOUT_S)
            resp.raise_for_status()
            hourly = resp.json().get("hourly", {})
        except requests.RequestException:
            continue
        if any(v is not None for v in hourly.get("wind_speed_10m", [])):
            results[model] = hourly
    return results

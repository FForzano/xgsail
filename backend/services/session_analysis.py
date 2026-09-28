"""Fan a worker's ``analysis.json`` out to its normalized DB homes.

Scalar aggregates → ``session_stats``, the empirical polar curve →
``polar_points``, tacks/gybes → ``session_maneuvers``, legs → ``session_legs``,
the remaining matrices/series/distributions → ``session_analysis`` (JSON).
Every child set is replaced wholesale, so a re-run never accumulates — and a
payload flagged ``analysis_unavailable`` (no wind source at all) clears the
previous run's wind-dependent results instead of leaving them on display.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from ..db.models.session import ANALYSIS_UNAVAILABLE_REASONS
from ..repositories import get_repos

logger = logging.getLogger(__name__)

PAYLOAD_KEY = "analysis_unavailable"
# session_stats columns that only exist with a wind signal. The summary of an
# unavailable analysis may simply omit them, and upsert_stats merges, so they
# are nulled explicitly or a previous run's value would survive.
WIND_DEPENDENT_STATS = ("avg_polar_pct", "max_polar_pct")


def unavailable_reason(payload: dict) -> Optional[str]:
    """The payload's reason, or ``None`` for a normal analysis (key absent —
    every worker image predating the flag — or null). An unknown value is
    logged and dropped rather than failing the whole upsert on the CHECK."""
    reason = payload.get(PAYLOAD_KEY)
    if reason is None or reason in ANALYSIS_UNAVAILABLE_REASONS:
        return reason
    logger.warning("unknown analysis_unavailable reason %r ignored", reason)
    return None


def apply_payload(session_id: uuid.UUID, payload: dict, now: datetime,
                  extra_fields: Optional[dict] = None) -> None:
    """Persist ``payload`` for ``session_id``. ``extra_fields`` are further
    ``session_analysis`` columns the caller resolved itself (the thumbnail)."""
    repos = get_repos()
    reason = unavailable_reason(payload)

    stats = dict(payload.get("summary") or {})
    if reason is not None:
        stats.update(dict.fromkeys(WIND_DEPENDENT_STATS))
    if stats:
        repos.sessions.upsert_stats(session_id, {**stats, "computed_at": now})
    repos.polars.bulk_upsert(session_id=session_id, source="empirical",
                             points=payload.get("polar_points") or [])
    repos.sessions.upsert_maneuvers(session_id, payload.get("maneuvers") or [])
    repos.sessions.upsert_legs(session_id, payload.get("legs") or [])

    repos.sessions.upsert_analysis(session_id, {
        "correlations": payload.get("correlations"),
        "violin": payload.get("violin"),
        "maneuver_summary": payload.get("maneuver_summary"),
        "leg_comparison": payload.get("leg_comparison"),
        "sensor_stats": payload.get("session_stats"),
        "vmg_series": payload.get("vmg_series"),
        "polar_target": payload.get("polar_target"),
        "true_wind": payload.get("true_wind"),
        "unavailable_reason": reason,
        "computed_at": now,
        **(extra_fields or {}),
    })

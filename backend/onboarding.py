"""Single source of truth for the guided-tour IDs the frontend can request.

Mirrors ``support.py``: the actual step content/copy lives entirely in the
frontend (``frontend/src/onboarding/tours.ts``), this module only documents
which IDs exist server-side. ``mark_onboarding_tour_seen`` (see
``repositories/sql/user_repo.py``) accepts any string ID, not just these —
a frontend-only tour addition should never require a backend deploy — so
this set is informational, not a validation gate.
"""

KNOWN_TOURS = {
    "app-overview",
    "diario-personale",
    "gruppi-overview",
    "profilo-overview",
}

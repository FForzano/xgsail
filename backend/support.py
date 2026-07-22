"""Single source of truth for the "Buy Me a Coffee" in-app reminder cadence.

Mirrors ``legal.py``: the actual banner text/link lives in the frontend
(``frontend/src/components/common/SupportPromptBanner.tsx``), this module
owns only the timing the backend enforces so the cadence is consistent
across devices (see ``auth/permissions.py::_support_status`` and
``repositories/sql/user_repo.py::record_support_prompt``).
"""

from datetime import timedelta

# First time the banner may appear: this long after registration.
FIRST_PROMPT_DELAY = timedelta(days=30)
# Re-prompt interval after the user dismisses without donating.
SNOOZE_DELAY = timedelta(days=45)
# Re-prompt interval after the user confirms they've donated.
DONATED_DELAY = timedelta(days=365)

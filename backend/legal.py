"""Single source of truth for the *current* version of the legal documents
(Terms of Service and Privacy Policy) the hosted service requires users to
accept.

The document TEXT lives in the frontend (``frontend/src/content/legal/*``);
this module owns only the version identifiers the backend compares against
what each user last accepted. When you change a document's text in a way
that requires re-acceptance, bump the matching constant here — and keep the
version string shown in the frontend content file in sync with it.

Versions are date-based (``YYYY-MM-DD``) rather than semantic: any change that
needs re-acceptance is, by definition, "the version published on that date".
The special value ``LEGACY_VERSION`` marks users who accepted the old,
pre-versioning generic checkbox (backfilled by migration 0033) — it never
equals a current version, so those users are always prompted to re-accept.
"""

LEGACY_VERSION = "legacy"

# Bump these (to today's date) whenever the corresponding document text is
# changed in a way that requires users to accept again. Keep in sync with the
# `version` exported by the frontend content files.
CURRENT_TERMS_VERSION = "2026-07-22"
CURRENT_PRIVACY_VERSION = "2026-08-05"

# Effective date shown to users alongside each document. Usually the same as
# the version, but kept separate so a purely editorial fix can update the
# displayed date without forcing re-acceptance.
TERMS_EFFECTIVE_DATE = "2026-07-22"
PRIVACY_EFFECTIVE_DATE = "2026-08-05"


def legal_metadata() -> dict:
    """Public document metadata (versions + effective dates) — served by the
    ``/api/legal`` endpoint and embedded in the capabilities payload."""
    return {
        "terms": {
            "version": CURRENT_TERMS_VERSION,
            "effective_date": TERMS_EFFECTIVE_DATE,
        },
        "privacy": {
            "version": CURRENT_PRIVACY_VERSION,
            "effective_date": PRIVACY_EFFECTIVE_DATE,
        },
    }

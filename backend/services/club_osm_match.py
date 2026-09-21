"""Match an existing club against the cached OpenStreetMap POIs (``osm_pois``).

The mirror image of the guest-boat claim suggestions: a club that was created
by hand has no ``osm_ref``, and today the only way to link one is to arrive
from the explorer map. This module ranks the cached sailing-club elements near
the club so the club's own managers can be offered the link.

Read-only and **cache-only**: nothing here fetches from Overpass, directly or
indirectly (see ``services/osm_poi.py``'s query gate). An area nobody has
looked at on the map yet simply yields no suggestion.

Everything below is a pure function over plain values — the caller does the
two queries (nearby POIs, which refs are already taken) and passes the rows in.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Optional

from .geo import haversine_m, meters_per_deg_lat, meters_per_deg_lon

# Only actual clubs are proposed: a marina or a slipway next door is a
# different kind of place, not a candidate identity for this club.
CLUB_KIND = "sailing_club"
SUGGESTION_RADIUS_M = 2000.0
MAX_SUGGESTIONS = 5

# Words that every other sailing club also has in its name, so they carry no
# evidence that two names denote the same place. Accents are already stripped
# by ``_normalise`` when this set is consulted ("società" -> "societa").
_GENERIC_NAME_WORDS = frozenset({
    "circolo", "circoli", "velico", "velica", "velici", "veliche",
    "club", "nautico", "nautica", "yacht", "societa", "associazione",
    "sailing", "asd",
})

_NON_WORD = re.compile(r"[^0-9a-z]+")

# Two names for the same club rarely match character for character — "Circolo
# Velico Barcola Grignano" vs. "CV Barcola-Grignano", a plural, a typo in OSM.
# So the comparison is a similarity with a threshold, never an equality: a
# token counts as the same word above _TOKEN_SIMILARITY, and the two names
# count as the same place above _NAME_SIMILARITY.
_TOKEN_SIMILARITY = 0.84
_NAME_SIMILARITY = 0.6


def _normalise(name: str) -> str:
    """Casefolded, accent-free, punctuation-free, single-spaced."""
    decomposed = unicodedata.normalize("NFKD", name).casefold()
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", stripped).strip()


def significant_tokens(name: Optional[str]) -> "set[str]":
    """The tokens of ``name`` that actually distinguish one club from another."""
    if not name:
        return set()
    return {
        tok for tok in _normalise(name).split()
        if len(tok) > 1 and tok not in _GENERIC_NAME_WORDS
    }


def _token_similarity(token: str, others: "set[str]") -> float:
    """How close ``token`` comes to its best counterpart in ``others``."""
    return max((SequenceMatcher(None, token, other).ratio() for other in others),
               default=0.0)


def name_similarity(a: Optional[str], b: Optional[str]) -> float:
    """0..1 — how much two club names look like the same place.

    Two measures, whichever is kinder: the share of the shorter name's
    distinguishing tokens that have a close counterpart in the other (so an
    extra "Grignano" or a dropped "ASD" costs nothing), and the plain ratio
    over the whole normalised names (so a single run-together or hyphenated
    name still matches its spaced spelling).
    """
    a_tokens, b_tokens = significant_tokens(a), significant_tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    smaller, larger = sorted((a_tokens, b_tokens), key=len)
    matched = sum(1 for tok in smaller if _token_similarity(tok, larger) >= _TOKEN_SIMILARITY)
    by_token = matched / len(smaller)
    by_whole = SequenceMatcher(None, " ".join(sorted(a_tokens)),
                               " ".join(sorted(b_tokens))).ratio()
    return max(by_token, by_whole)


def names_match(a: Optional[str], b: Optional[str]) -> bool:
    """True when two club names are similar enough to denote the same place.

    A soft signal used for ranking only, never as a filter: OSM names a club
    every way a human might, and an unnamed element is still a fine candidate
    if it sits on top of the club.
    """
    return name_similarity(a, b) >= _NAME_SIMILARITY


def bbox_for_radius(lat: float, lng: float,
                    radius_m: float = SUGGESTION_RADIUS_M) -> "tuple[float, float, float, float]":
    """(south, west, north, east) enclosing the circle — the SQL prefilter that
    keeps the candidate scan on ``ix_osm_pois_lat_lng``. Deliberately generous:
    ``haversine_m`` does the real distance test afterwards."""
    dlat = radius_m / meters_per_deg_lat()
    # cos(lat) -> 0 at the poles; the floor keeps the box finite instead of
    # dividing by ~0. It only ever widens the prefilter.
    dlng = radius_m / max(abs(meters_per_deg_lon(lat)), 1.0)
    return (max(lat - dlat, -90.0), max(lng - dlng, -180.0),
            min(lat + dlat, 90.0), min(lng + dlng, 180.0))


def rank_suggestions(club_lat: float, club_lng: float, club_name: Optional[str],
                     pois: Iterable, *, taken_refs: "set[str]",
                     radius_m: float = SUGGESTION_RADIUS_M,
                     limit: int = MAX_SUGGESTIONS) -> "list[dict]":
    """The ranked suggestion payloads for one club.

    ``pois`` are the cached rows from the bbox prefilter (anything with
    ``osm_ref``/``kind``/``lat``/``lng``/``name``). Rows whose ref another club
    already holds are dropped here rather than offered: ``clubs.osm_ref`` is
    UNIQUE, so linking one would only ever 409.
    """
    out = []
    for poi in pois:
        if poi.kind != CLUB_KIND or poi.osm_ref in taken_refs:
            continue
        if poi.lat is None or poi.lng is None:
            continue
        distance = haversine_m(club_lat, club_lng, poi.lat, poi.lng)
        if distance > radius_m:
            continue
        similarity = name_similarity(club_name, poi.name)
        out.append({
            # Ranking only, dropped before the payload: two nearby clubs with
            # similar names are ordered by how similar, not by which is closer.
            "_similarity": similarity,
            "osm_ref": poi.osm_ref,
            "name": poi.name,
            "kind": poi.kind,
            "lat": poi.lat,
            "lng": poi.lng,
            "distance_m": round(distance, 1),
            "name_match": similarity >= _NAME_SIMILARITY,
        })
    out.sort(key=lambda s: (-s["_similarity"], s["distance_m"]))
    return [{k: v for k, v in s.items() if k != "_similarity"} for s in out[:limit]]

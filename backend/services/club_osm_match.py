"""Match an existing club against the cached OpenStreetMap POIs (``osm_pois``).

The mirror image of the guest-boat claim suggestions: a club that was created
by hand has no ``osm_ref``, and today the only way to link one is to arrive
from the explorer map. This module ranks the cached sailing-club elements near
the club so the club's own managers can be offered the link.

Read-only and **cache-only**: nothing here fetches from Overpass, directly or
indirectly (see ``services/osm_poi.py``'s query gate). An area nobody has
looked at on the map yet simply yields no suggestion.

The second half answers a different question about the same rows: whether the
cache has anything to say about the club running a **sailing school**
(``clubs.has_sailing_school``). Same cache, same "propose it, a manager
decides" shape — see the block comment above ``SCHOOL_RADIUS_M``.

Everything below is a pure function over plain values — the caller does the
queries (nearby POIs, which refs are already taken, the club's own element)
and passes the rows in.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Optional

from .geo import haversine_m, meters_per_deg_lat, meters_per_deg_lon
from .osm_poi import SCHOOL_KIND, has_sailing_school

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


# --- sailing school ---------------------------------------------------------
#
# ``clubs.has_sailing_school`` is the authoritative flag and a manager sets it.
# What OSM can contribute is evidence, in two tiers that are genuinely
# different and must not be presented as one:
#
# - "linked" is a fact. The club has declared itself to be a specific element
#   (``clubs.osm_ref``) and that element carries ``amenity=sailing_school``.
#   This is the "Circolo Nautico di Volano" case (way/1561055644, tagged
#   ``amenity=sailing_school;boat_storage`` + ``club=sport``), which since
#   ``0060`` classifies as a *club* — the school fact survives only in tags.
# - "nearby" is a guess a human confirms. The Overpass query is
#   ``out center tags``, so all we store is a centre point: no geometry, no
#   relation membership, therefore no containment and no "is part of this
#   club" test. Proximity is the only signal there is, and that is exactly
#   why this asks a manager instead of setting the flag itself.

# Much tighter than ``SUGGESTION_RADIUS_M`` (2 km), and for the opposite
# reason. Identity tolerates distance: an OSM centre point for a club can sit
# a long way from the address someone typed, and there is only ever one club
# at a spot, so a wide search is safe. Containment does not: at 2 km a school
# is simply a different organisation down the coast, and proposing it would
# teach managers to dismiss the prompt. A club and a school it runs share a
# site, so a few hundred metres covers the far end of the same harbour.
SCHOOL_RADIUS_M = 300.0
MAX_SCHOOL_SUGGESTIONS = 3

def no_school_suggestion() -> dict:
    """"Nothing to suggest" — the club already says it teaches, or has neither
    a linked element nor coordinates, or nothing is cached near it. Never an
    error. A fresh dict each call rather than a shared constant, so a caller
    that annotates the payload cannot corrupt every later response."""
    return {"source": None, "candidates": []}


def _school_candidate(poi, distance_m: Optional[float]) -> dict:
    return {
        "osm_ref": poi.osm_ref,
        "name": poi.name,
        "kind": poi.kind,
        # NULL for the linked tier: that element *is* the club, so a distance
        # from itself would be a meaningless 0 dressed up as a measurement.
        "distance_m": None if distance_m is None else round(distance_m, 1),
    }


def school_suggestion(linked_poi=None, nearby_pois: Iterable = (), *,
                      club_lat: Optional[float] = None,
                      club_lng: Optional[float] = None,
                      radius_m: float = SCHOOL_RADIUS_M,
                      limit: int = MAX_SCHOOL_SUGGESTIONS) -> dict:
    """Evidence that a club runs a sailing school, at the strongest tier
    available: ``{"source": "linked"|"nearby"|None, "candidates": [...]}``.

    The tiers are exclusive — a fact about the club's own element is the
    answer, and the proximity heuristic is not worth showing next to it. A
    candidate carries ``osm_ref``/``name``/``kind``/``distance_m``, which is
    what the frontend needs to word the prompt.

    Pure: the caller does the two cache reads (the club's own element, and
    the ``sailing_school`` POIs in the bbox) and passes the rows in.
    """
    if linked_poi is not None and has_sailing_school(linked_poi.kind, linked_poi.tags):
        return {"source": "linked", "candidates": [_school_candidate(linked_poi, None)]}

    if club_lat is None or club_lng is None:
        return no_school_suggestion()

    linked_ref = getattr(linked_poi, "osm_ref", None)
    near = []
    for poi in nearby_pois:
        # The club's own element is the linked tier's business; if it did not
        # qualify there it is not evidence here either.
        if poi.kind != SCHOOL_KIND or poi.osm_ref == linked_ref:
            continue
        if poi.lat is None or poi.lng is None:
            continue
        distance = haversine_m(club_lat, club_lng, poi.lat, poi.lng)
        if distance > radius_m:
            continue
        near.append(_school_candidate(poi, distance))
    if not near:
        return no_school_suggestion()
    near.sort(key=lambda c: c["distance_m"])
    return {"source": "nearby", "candidates": near[:limit]}


# --- the two school fields, kept consistent ---------------------------------
#
# ``has_sailing_school`` (is there a school?) and ``school_osm_ref`` (which
# separate OSM element is it?) answer different questions, but only three of
# their four combinations mean anything:
#
#   flag=false, ref=NULL   no school
#   flag=true,  ref=NULL   a school, with no separate element of its own —
#                          either unmapped, or tagged on the club's own
#                          element, where ``clubs.osm_ref`` already dedupes it
#   flag=true,  ref=set    a school that is its own OSM element, whose pin the
#                          map replaces with the club's
#
# The fourth, flag=false with a ref set, is the dangerous one: the map would
# hide that school's POI while the club renders no school at all, so the place
# disappears with nothing drawn in its stead — the failure mode the clubs-layer
# condition in ``useNauticalLayers`` exists to avoid. So the state is not
# tolerated; it is normalised away at the one write path, and a caller that
# asks for it *explicitly* (both fields in one body, contradicting each other)
# gets an error rather than a silent pick between two things it said.


class SchoolFieldsConflict(ValueError):
    """The write sets ``school_osm_ref`` and ``has_sailing_school=False`` in
    the same body. The router turns this into a 422."""


def normalise_school_changes(changes: dict) -> dict:
    """Return ``changes`` with the school fields made consistent.

    Recording *which* element the school is asserts there is one, so a
    non-NULL ``school_osm_ref`` implies the flag; conversely, saying the club
    runs no school retracts the element along with it. Pure — a new dict over
    plain values, no DB: both fields are always writable together, so the
    stored row cannot change the answer.
    """
    ref_set = "school_osm_ref" in changes and changes["school_osm_ref"] is not None
    flag_off = changes.get("has_sailing_school") is False

    if ref_set and flag_off:
        raise SchoolFieldsConflict(
            "school_osm_ref names this club's sailing school, so it cannot be "
            "set together with has_sailing_school=false"
        )
    out = dict(changes)
    if ref_set:
        out["has_sailing_school"] = True
    elif flag_off:
        out["school_osm_ref"] = None
    return out

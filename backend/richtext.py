"""Sanitization of the rich-text (HTML) prose fields produced by the
frontend's Tiptap editor.

This module is the security boundary against stored XSS: boats, clubs,
groups and regattas are pub-readable, so their descriptions reach
*anonymous* callers. Everything that is written to one of those columns
goes through :func:`normalize` first — never trust the editor's output,
which is just whatever the client POSTed.

Pure text handling, deliberately free of any ``backend.db`` / router
import so ``backend/schemas/`` can depend on it without inverting the
layering.

Sanitizing is done with `nh3 <https://pypi.org/project/nh3/>`_ (bindings
to the Rust *ammonia* crate) rather than bleach, which is archived and no
longer receives security fixes.
"""

from __future__ import annotations

import html
import re
from typing import Annotated, Optional

import nh3
from pydantic import AfterValidator

# The allow-lists below must stay in lockstep with the editor's schema in
# `frontend/src/components/ui/richTextSchema.ts` — a tag the editor can
# produce but the sanitizer drops silently eats the user's content.
BASIC_TAGS = frozenset({"p", "br", "strong", "em", "u", "s", "a"})

FULL_TAGS = BASIC_TAGS | frozenset(
    {
        "h1",
        "h2",
        "h3",
        "ul",
        "ol",
        "li",
        "blockquote",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    }
)

TIERS = {"basic": BASIC_TAGS, "full": FULL_TAGS}

# No `class`, `style` or `id` anywhere: all presentation comes from the
# frontend CSS Module, which also leaves no CSS-injection surface.
BASE_ATTRIBUTES = {
    "a": frozenset({"href", "title"}),
    "th": frozenset({"colspan", "rowspan"}),
    "td": frozenset({"colspan", "rowspan"}),
}

URL_SCHEMES = frozenset({"http", "https", "mailto"})

LINK_REL = "noopener noreferrer nofollow"

# A value is treated as HTML only if it *starts* with one of these — a
# decisive rule, so the legacy-plain-text path can never be reached by a
# value we ourselves produced (see `normalize`).
_BLOCK_START_RE = re.compile(
    r"<(p|h1|h2|h3|ul|ol|blockquote|table)(\s|>|/>)", re.IGNORECASE
)

# Block boundaries that must read as whitespace once tags are gone.
_BOUNDARY_RE = re.compile(
    r"<\s*(br|/p|/li|/tr|/td|/th|/h[1-6]|/blockquote|/ul|/ol|/table)\s*/?>",
    re.IGNORECASE,
)

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")


def _tags(tier: str, mentions: bool) -> set[str]:
    try:
        tags = set(TIERS[tier])
    except KeyError:
        raise ValueError(f"unknown rich-text tier: {tier!r}") from None
    if mentions:
        tags.add("span")
    return tags


def _attributes(mentions: bool) -> dict[str, set[str]]:
    attributes = {tag: set(attrs) for tag, attrs in BASE_ATTRIBUTES.items()}
    if mentions:
        attributes["a"].add("data-mention")
        attributes["span"] = {"data-mention"}
    return attributes


def _plain_text_to_html(value: str) -> str:
    escaped = html.escape(value.replace("\r\n", "\n").replace("\r", "\n"))
    paragraphs = []
    for block in _PARAGRAPH_SPLIT_RE.split(escaped):
        block = block.strip("\n")
        if block.strip():
            paragraphs.append("<p>" + block.replace("\n", "<br>") + "</p>")
    return "".join(paragraphs)


def normalize(
    value: str | None, *, tier: str = "basic", mentions: bool = False
) -> str | None:
    """Sanitize ``value`` into storable HTML, or ``None`` if it is empty.

    Accepts both editor HTML and legacy plain text (every one of these
    columns held plain text with bare newlines before the migration).
    Idempotent: ``normalize(normalize(x)) == normalize(x)``.
    """
    if value is None or not value.strip():
        return None

    if not _BLOCK_START_RE.match(value.strip()):
        value = _plain_text_to_html(value)

    cleaned = nh3.clean(
        value,
        tags=_tags(tier, mentions),
        attributes=_attributes(mentions),
        url_schemes=set(URL_SCHEMES),
        link_rel=LINK_REL,
        strip_comments=True,
    ).strip()

    if not to_plain_text(cleaned):
        return None

    # Stripping a tier's disallowed tags can leave bare text (a `<table>`
    # cleaned at the `basic` tier, say). Re-wrapping keeps every stored
    # value starting with a block tag, which is what makes a second pass
    # take the HTML branch and idempotency hold.
    if not _BLOCK_START_RE.match(cleaned):
        cleaned = f"<p>{cleaned}</p>"
    return cleaned


def to_plain_text(value: str | None) -> str:
    """Readable, searchable plain text: tags dropped, entities decoded.

    The result is *text*, not HTML — decoding entities can resurrect
    ``<script>`` from a value that legitimately talks about one, so never
    render it as markup.
    """
    if not value:
        return ""
    text = nh3.clean(_BOUNDARY_RE.sub(" ", value), tags=set())
    return " ".join(html.unescape(text).split())


# Ready-to-use DTO annotations, so a schema field is a one-word change.
# All three are `Optional[str]`: a field is made required by declaring it
# without a default (`body: RichTextPost`), which still allows None —
# normalize() maps blank input to None whatever the field's nullability.
RichTextBasic = Annotated[
    Optional[str], AfterValidator(lambda v: normalize(v, tier="basic"))
]
RichTextFull = Annotated[
    Optional[str], AfterValidator(lambda v: normalize(v, tier="full"))
]
RichTextPost = Annotated[
    Optional[str], AfterValidator(lambda v: normalize(v, tier="basic", mentions=True))
]

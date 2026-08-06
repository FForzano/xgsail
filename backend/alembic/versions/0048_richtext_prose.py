"""Convert every prose column from plain text to sanitized HTML, and add
``sessions.notes_plain`` (a plain-text search mirror of ``sessions.notes``).

The columns converted are the ones now typed as rich text in the schemas:
``activities.description``, ``boat_classes.description``, ``boat_notes.body``,
``clubs.description``, ``groups.description``, ``note_templates.body``,
``posts.body``, ``regattas.description``, ``race_days.notes`` and
``sessions.notes``.

``posts.body`` takes a different path: post bodies carry the hand-rolled
"post-lite" markup of ``frontend/src/utils/postFormat.tsx`` (``**bold**``,
``*italic*``, ``__underline__``, ``[label](url)``, ``@[label](type:id)``
mentions and bare URLs), which is translated into the equivalent tags instead
of being escaped away.

Escaping is not idempotent, so the row-selection guard is what makes this
revision safe to meet a database that already holds HTML: rows are skipped
unless they are non-blank *and* do not already start with a block tag. That
predicate lives in the WHERE clause of every SELECT, never in the expression,
so a re-run converts nothing a second time.

The conversion is deliberately reimplemented here instead of importing
``backend/richtext.py``: CI replays this revision against every future state of
the tree, and a revision that imports application code breaks the day that code
is refactored.

Downgrade strips the tags back to plain text and drops ``notes_plain``. It is
lossy: anything authored *after* this migration loses its structure (a table,
list or heading collapses into flat text), and a post's formatting does not
return to post-lite syntax — ``<strong>x</strong>`` comes back as ``x``, not
``**x**``. Downgrade is a rollback path, not a supported round trip.

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-06
"""
import html
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0048'
down_revision: Union[str, None] = '0047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) pairs holding prose. `posts.body` is handled separately.
PROSE_COLUMNS = [
    ('activities', 'description'),
    ('boat_classes', 'description'),
    ('boat_notes', 'body'),
    ('clubs', 'description'),
    ('groups', 'description'),
    ('note_templates', 'body'),
    ('regattas', 'description'),
    ('race_days', 'notes'),
    ('sessions', 'notes'),
]

BATCH_SIZE = 500

# Mirrors backend/richtext.py's _BLOCK_START_RE. Its SQL twin is
# _NOT_HTML_SQL below; the two must stay in step.
_BLOCK_START_RE = re.compile(r"<(p|h1|h2|h3|ul|ol|blockquote|table)(\s|>|/>)", re.IGNORECASE)

# The rows to convert: non-blank, and not already HTML. `~*` is Postgres'
# case-insensitive regex match; `btrim` is given the full whitespace set
# because its default only trims spaces.
_NOT_HTML_SQL = (
    "btrim({col}, E' \\t\\r\\n') <> '' "
    "AND btrim({col}, E' \\t\\r\\n') !~* '^<(p|h1|h2|h3|ul|ol|blockquote|table)(\\s|>|/>)'"
)

# Rows to convert back on downgrade: exactly the inverse predicate.
_IS_HTML_SQL = (
    "btrim({col}, E' \\t\\r\\n') ~* '^<(p|h1|h2|h3|ul|ol|blockquote|table)(\\s|>|/>)'"
)

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")

# Ported from postFormat.tsx's INLINE_RE — the authority on post-lite syntax.
_POST_INLINE_RE = re.compile(
    r"@\[([^\]]+)\]\((user|club|group):([^)]+)\)"
    r"|\[([^\]]+)\]\((https?://[^\s)]+)\)"
    r"|\*\*([^*\n]+)\*\*"
    r"|__([^_\n]+)__"
    r"|\*([^*\n]+)\*"
    r"|(https?://\S+)"
)

_URL_TRAILING_PUNCTUATION_RE = re.compile(r"[),.;:!?\]]$")
_ENTITY_END_RE = re.compile(r"&(?:[a-zA-Z]+|#x?[0-9a-fA-F]+);$")

_PARAGRAPH_BREAK_RE = re.compile(
    r"</\s*(p|li|tr|h[1-3]|blockquote|ul|ol|table)\s*>", re.IGNORECASE
)
_LINE_BREAK_RE = re.compile(r"<\s*br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]*>")


def is_html(value: str) -> bool:
    """The decisive HTML-vs-plain-text test used across the stack."""
    return bool(_BLOCK_START_RE.match(value.strip()))


def wrap_paragraphs(marked_up: str) -> str:
    """Blank lines become paragraphs, single newlines ``<br>``.

    Takes text that is already escaped (and, for posts, already carries its
    generated tags) — it must never escape, or it would eat those tags.
    """
    paragraphs = []
    for block in _PARAGRAPH_SPLIT_RE.split(marked_up):
        block = block.strip("\n")
        if block.strip():
            paragraphs.append("<p>" + block.replace("\n", "<br>") + "</p>")
    return "".join(paragraphs)


def _escape(value: str) -> str:
    # html.escape substitutes `&` first, so the `&` of a `&lt;` it just wrote
    # is never escaped again.
    return html.escape(value.replace("\r\n", "\n").replace("\r", "\n"))


def plain_text_to_html(value: str) -> str:
    return wrap_paragraphs(_escape(value))


def _split_url_punctuation(url: str) -> tuple[str, str]:
    """Sentence punctuation trailing a bare URL is not part of it — except a
    ``;`` closing an entity the escape pass produced (``…?a=1&amp;``)."""
    trailing = ""
    while _URL_TRAILING_PUNCTUATION_RE.search(url) and not _ENTITY_END_RE.search(url):
        trailing = url[-1] + trailing
        url = url[:-1]
    return url, trailing


def _mention_html(label: str, kind: str, ident: str) -> str:
    if kind == "user":
        return f'<span data-mention="user:{ident}">@{label}</span>'
    path = f"/gruppi/clubs/{ident}" if kind == "club" else f"/gruppi/{ident}"
    return f'<a href="{path}" data-mention="{kind}:{ident}">@{label}</a>'


def _inline_markup(escaped: str) -> str:
    """Translate post-lite tokens into tags, over already-escaped text.

    Escaping leaves every token character (``*_[]()@``) untouched, and turns
    the ``&`` of a query string into ``&amp;`` — which is exactly the form an
    ``href`` attribute wants, so matched URLs are used verbatim.
    """

    def replace(m: re.Match) -> str:
        label, kind, ident, link_label, link_url, bold, underline, italic, bare = m.groups()
        if label is not None:
            return _mention_html(label, kind, ident)
        if link_label is not None:
            return f'<a href="{link_url}">{link_label}</a>'
        if bold is not None:
            return f"<strong>{bold}</strong>"
        if underline is not None:
            return f"<u>{underline}</u>"
        if italic is not None:
            return f"<em>{italic}</em>"
        url, trailing = _split_url_punctuation(bare)
        return f'<a href="{url}">{url}</a>{trailing}'

    return _POST_INLINE_RE.sub(replace, escaped)


def post_body_to_html(value: str) -> str:
    return wrap_paragraphs(_inline_markup(_escape(value)))


def html_to_plain_text(value: str) -> str:
    """Downgrade's inverse: tags out, entities decoded, structure flattened."""
    text = _LINE_BREAK_RE.sub("\n", value)
    text = _PARAGRAPH_BREAK_RE.sub("\n\n", text)
    text = _TAG_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


def _convert_column(table: str, column: str, predicate: str, convert) -> None:
    """Rewrite every row matching ``predicate`` in batches.

    Keyset pagination on the primary key, so the loop terminates on its own
    number of rows rather than on converted rows dropping out of the
    predicate — a row ``convert`` leaves unchanged would otherwise loop
    forever.
    """
    connection = op.get_bind()
    select = sa.text(
        f"SELECT id, {column} FROM {table} "
        f"WHERE {predicate.format(col=column)} AND id > CAST(:after AS uuid) "
        f"ORDER BY id LIMIT {BATCH_SIZE}"
    )
    update = sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id")

    after = '00000000-0000-0000-0000-000000000000'
    while True:
        rows = connection.execute(select, {"after": after}).fetchall()
        if not rows:
            return
        for row_id, value in rows:
            converted = convert(value)
            if converted:
                connection.execute(update, {"value": converted, "id": row_id})
        after = rows[-1][0]


def upgrade() -> None:
    op.add_column('sessions', sa.Column('notes_plain', sa.Text(), nullable=True))

    # While `notes` is still plain text, so the mirror is a straight copy with
    # whitespace collapsed the way richtext.to_plain_text() collapses it.
    op.execute(r"""
        UPDATE sessions
           SET notes_plain = regexp_replace(btrim(notes, E' \t\r\n'), '\s+', ' ', 'g')
         WHERE notes IS NOT NULL
    """)

    for table, column in PROSE_COLUMNS:
        _convert_column(table, column, _NOT_HTML_SQL, plain_text_to_html)
    _convert_column('posts', 'body', _NOT_HTML_SQL, post_body_to_html)


def downgrade() -> None:
    for table, column in PROSE_COLUMNS + [('posts', 'body')]:
        _convert_column(table, column, _IS_HTML_SQL, html_to_plain_text)

    op.drop_column('sessions', 'notes_plain')

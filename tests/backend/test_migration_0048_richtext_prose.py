"""Tests for the pure conversion helpers of migration ``0048_richtext_prose``,
the one-time rewrite of every prose column from plain text to HTML.

The revision deliberately does not import ``backend.richtext`` (a migration
must keep working when application code is refactored), so its copy of the
transformation needs its own tests. Loaded by path because the versions
directory is not a package.

Database-free by design: what is exercised here is the string transformation,
not the SQL around it.
"""

import importlib.util
from pathlib import Path

import pytest

_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend/alembic/versions/0048_richtext_prose.py"
)
_spec = importlib.util.spec_from_file_location("migration_0048", _PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def convert(value: str) -> str:
    """The upgrade's per-row decision: guard first, then transform."""
    return value if m.is_html(value) else m.plain_text_to_html(value)


def test_escapes_in_the_right_order():
    out = m.plain_text_to_html('a & b < c > d "e"')
    assert out == '<p>a &amp; b &lt; c &gt; d &quot;e&quot;</p>'
    # The `&` of an escape sequence must not itself have been escaped.
    assert "&amp;lt;" not in out and "&amp;amp;" not in out


def test_literal_entity_in_source_is_escaped_once():
    assert m.plain_text_to_html("100 &amp; more") == "<p>100 &amp;amp; more</p>"


def test_blank_lines_become_paragraphs_single_newline_becomes_br():
    assert m.plain_text_to_html("one\ntwo\n\nthree") == "<p>one<br>two</p><p>three</p>"


def test_crlf_is_normalized():
    assert m.plain_text_to_html("a\r\n\r\nb") == "<p>a</p><p>b</p>"


@pytest.mark.parametrize(
    "value",
    ["<p>already</p>", "<P>upper</P>", "<p >spaced</p>", "<table><tr><td>x</td></tr></table>"],
)
def test_guard_recognizes_existing_html(value):
    assert m.is_html(value)
    assert convert(value) == value


@pytest.mark.parametrize("value", ["plain", "<b>bold only</b>", "1 < 2"])
def test_guard_treats_non_block_starts_as_plain_text(value):
    assert not m.is_html(value)


def test_conversion_is_idempotent_at_the_guard_level():
    dataset = [
        "plain & simple",
        "one\ntwo\n\nthree",
        "<p>already converted</p>",
        "1 < 2",
    ]
    once = [convert(v) for v in dataset]
    assert [convert(v) for v in once] == once


def test_post_body_with_every_construct():
    body = (
        "**bold** *italic* __under__ [doc](https://x.io/d) "
        "@[Club](club:c1) @[Ann](user:u1) see https://y.io/p. 1 < 2 & 3"
    )
    assert m.post_body_to_html(body) == (
        "<p><strong>bold</strong> <em>italic</em> <u>under</u> "
        '<a href="https://x.io/d">doc</a> '
        '<a href="/gruppi/clubs/c1" data-mention="club:c1">@Club</a> '
        '<span data-mention="user:u1">@Ann</span> '
        'see <a href="https://y.io/p">https://y.io/p</a>. 1 &lt; 2 &amp; 3</p>'
    )


def test_post_group_mention_uses_the_group_route():
    ident = "0f1c4a5e-9b1d-4c2a-8f77-3e6b2d1a9c04"
    assert m.post_body_to_html(f"hi @[Team](group:{ident})") == (
        f'<p>hi <a href="/gruppi/{ident}" data-mention="group:{ident}">@Team</a></p>'
    )


def test_post_bare_url_keeps_query_string_and_sentence_punctuation():
    out = m.post_body_to_html("go to https://x.io/a?b=1&c=2, now")
    assert out == '<p>go to <a href="https://x.io/a?b=1&amp;c=2">https://x.io/a?b=1&amp;c=2</a>, now</p>'


def test_post_bare_url_ending_in_an_escaped_entity_keeps_it():
    # The `;` of `&amp;` closes an escape, it is not sentence punctuation.
    out = m.post_body_to_html("https://x.io/a?b=1&")
    assert out == '<p><a href="https://x.io/a?b=1&amp;">https://x.io/a?b=1&amp;</a></p>'


def test_post_conversion_is_idempotent_at_the_guard_level():
    body = "**bold** and https://x.io/p"
    once = m.post_body_to_html(body)
    assert m.is_html(once)
    assert (once if m.is_html(once) else m.post_body_to_html(once)) == once


def test_downgrade_recovers_the_original_plain_text():
    for original in ["one\ntwo\n\nthree", 'a & b < c > d "e"', "single line"]:
        assert m.html_to_plain_text(m.plain_text_to_html(original)) == original


def test_downgrade_flattens_richer_structure():
    assert m.html_to_plain_text("<ul><li>a</li><li>b</li></ul>") == "a\n\nb"
    assert m.html_to_plain_text('<p>see <a href="https://x.io">x</a></p>') == "see x"

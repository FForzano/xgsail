"""Tests for ``backend/richtext.py``, the sanitizer standing between the
Tiptap editor's output and columns that are served to anonymous callers.

Pure unit tests — no database, no FastAPI app.

Note the detection rule these tests exercise throughout: a value counts as
HTML only when it *starts* with a block tag. A bare inline fragment
(``<a href=…>`` with nothing around it) is therefore legacy plain text and
gets escaped, which is why the XSS cases below wrap their payload in a
``<p>`` — that is the shape the editor actually posts.
"""

import pytest
from pydantic import BaseModel

from backend.richtext import (
    RichTextBasic,
    RichTextFull,
    RichTextPost,
    normalize,
    to_plain_text,
)


@pytest.mark.parametrize(
    "payload",
    [
        "<p>ok</p><script>alert(1)</script>",
        "<p>ok<img src=x onerror=alert(1)></p>",
        "<p>ok</p><iframe src='https://evil.example'></iframe>",
        "<p onclick='alert(1)'>ok</p>",
        "<p>ok</p><style>body{display:none}</style>",
    ],
)
def test_active_content_is_neutralized(payload):
    out = normalize(payload, tier="full")
    for fragment in ("<script", "<img", "<iframe", "<style", "onerror", "onclick"):
        assert fragment not in out


@pytest.mark.parametrize(
    "href",
    ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<script>x</script>"],
)
def test_dangerous_link_schemes_are_dropped(href):
    out = normalize(f'<p><a href="{href}">x</a></p>')
    assert "javascript" not in out.lower()
    assert "data:" not in out
    assert out == '<p><a rel="noopener noreferrer nofollow">x</a></p>'


def test_presentation_attributes_are_stripped():
    out = normalize(
        '<p class="c" style="color:red" id="i">t</p><h1 class="x">h</h1>', tier="full"
    )
    assert out == "<p>t</p><h1>h</h1>"


def test_outbound_links_carry_rel():
    out = normalize('<p><a href="https://example.com" title="t">x</a></p>')
    assert 'href="https://example.com"' in out
    assert 'rel="noopener noreferrer nofollow"' in out
    assert 'title="t"' in out


def test_legacy_plain_text_special_characters_round_trip():
    original = 'a < b & c > d "q" \'z\''
    assert to_plain_text(normalize(original)) == original


def test_legacy_plain_text_paragraphs_and_line_breaks():
    assert normalize("one\ntwo\n\nthree") == "<p>one<br>two</p><p>three</p>"


def test_legacy_plain_text_with_windows_line_endings():
    assert normalize("one\r\n\r\ntwo") == "<p>one</p><p>two</p>"


@pytest.mark.parametrize(
    "value",
    [
        "plain text",
        "amp & ersand",
        "already &amp; escaped-looking",
        "line\nbreak\n\npara",
        "<p>a &amp; b</p>",
        '<p><a href="https://example.com">x</a></p>',
        "<h1>T</h1><table><tr><td>x</td></tr></table>",
        "<ul><li>one</li></ul>",
        "<p>a</p>trailing text",
    ],
)
@pytest.mark.parametrize("tier", ["basic", "full"])
def test_normalize_is_idempotent(value, tier):
    once = normalize(value, tier=tier, mentions=True)
    assert normalize(once, tier=tier, mentions=True) == once


def test_idempotency_does_not_double_escape_ampersands():
    once = normalize("Laser & Radial")
    assert once == "<p>Laser &amp; Radial</p>"
    assert normalize(once) == once
    assert "&amp;amp;" not in normalize(once)


def test_tier_separation():
    source = "<h1>Title</h1><p><u>u</u></p><table><tr><td>cell</td></tr></table>"

    full = normalize(source, tier="full")
    assert "<h1>" in full
    assert "<table>" in full
    assert "<u>u</u>" in full

    basic = normalize(source, tier="basic")
    assert "<h1>" not in basic
    assert "<table>" not in basic
    assert "<u>u</u>" in basic
    # Stripping the tags keeps their text, it does not delete the content.
    assert "Title" in basic and "cell" in basic


def test_table_cell_spans_survive_full_tier():
    out = normalize("<table><tr><td colspan='2' rowspan='3'>c</td></tr></table>", tier="full")
    assert 'colspan="2"' in out
    assert 'rowspan="3"' in out


def test_mentions_flag_gates_data_mention():
    source = '<p><span data-mention="u1">@bob</span> and <a href="https://e.com" data-mention="u2">@ann</a></p>'

    with_mentions = normalize(source, mentions=True)
    assert '<span data-mention="u1">@bob</span>' in with_mentions
    assert 'data-mention="u2"' in with_mentions

    without = normalize(source, mentions=False)
    assert "data-mention" not in without
    assert "<span" not in without
    assert "@bob" in without


def test_to_plain_text_separates_blocks():
    assert to_plain_text("<p>a</p><p>b</p>") == "a b"
    assert to_plain_text("<p>a<br>b</p>") == "a b"
    assert to_plain_text("<ul><li>one</li><li>two</li></ul>") == "one two"


def test_to_plain_text_on_a_table():
    out = to_plain_text(
        "<table><thead><tr><th>Boat</th><th>Sail</th></tr></thead>"
        "<tbody><tr><td>Alpha</td><td>ITA 1</td></tr></tbody></table>"
    )
    assert out == "Boat Sail Alpha ITA 1"
    for tag in ("table", "thead", "tbody", "<", ">"):
        assert tag not in out


def test_to_plain_text_decodes_entities_nh3_leaves_encoded():
    # nh3 strips tags but leaves entities encoded, hence the html.unescape
    # inside to_plain_text — this asserts that real behaviour.
    assert to_plain_text("<p>a &amp; b &lt;c&gt;</p>") == "a & b <c>"


def test_to_plain_text_collapses_whitespace_and_handles_empty():
    assert to_plain_text("<p>  a   \n  b </p>") == "a b"
    assert to_plain_text(None) == ""
    assert to_plain_text("") == ""


@pytest.mark.parametrize(
    "value", [None, "", "   ", "\n\n", "<p></p>", "<p><br></p>", "<p>   </p>", "<p></p><p></p>"]
)
def test_empty_inputs_become_none(value):
    assert normalize(value, tier="full") is None


def test_bare_inline_fragment_is_treated_as_legacy_plain_text():
    # Deliberate consequence of the decisive detection rule: a value that
    # does not start with a block tag is legacy plain text, so a column
    # whose literal content is "<br>" renders as that text rather than
    # being silently emptied.
    assert normalize("<br>") == "<p>&lt;br&gt;</p>"
    assert to_plain_text(normalize("<br>")) == "<br>"


def test_annotated_types_normalize_dto_fields():
    class Model(BaseModel):
        basic: RichTextBasic = None
        full: RichTextFull = None
        post: RichTextPost = None

    m = Model(
        basic="a & b",
        full="<h1>T</h1>",
        post='<p><span data-mention="u1">@bob</span></p>',
    )
    assert m.basic == "<p>a &amp; b</p>"
    assert m.full == "<h1>T</h1>"
    assert 'data-mention="u1"' in m.post

    assert Model().basic is None
    assert Model(basic="   ").basic is None
    # The basic tier is what strips the heading the full tier kept.
    assert Model(basic="<h1>T</h1>").basic == "<p>T</p>"


def test_unknown_tier_is_rejected():
    with pytest.raises(ValueError):
        normalize("<p>x</p>", tier="nope")

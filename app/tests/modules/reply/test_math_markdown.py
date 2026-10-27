"""Math parsing contracts: losing protection or escaping must fail these tests."""

import hashlib
import html
import re
from pathlib import Path

import pytest

from neobot_app.reply.math_markdown import pillowmd_source, render_markdown
from neobot_app.reply import math_markdown


def math_sources(output):
    return [html.unescape(x) for x in re.findall(r'data-tex="([^"]*)"', output)]


@pytest.mark.parametrize("source", ["$x_1^2$", "$$x_1^2$$", r"\(x_1^2\)", r"\[x_1^2\]"])
def test_four_delimiters(source):
    assert math_sources(render_markdown(source)) == ["x_1^2"]


def test_matrix_inside_markdown_table():
    output = render_markdown("| A | B |\n|---|---|\n| $\\begin{matrix}a|b\\\\c&d\\end{matrix}$ | 中文 |")
    assert output.count("<td>") == 2
    assert math_sources(output) == [r"\begin{matrix}a|b\\c&d\end{matrix}"]


def test_code_escaped_currency_and_unclosed_are_literal():
    output = render_markdown("`$x$`\n\n```tex\n$x$\n```\n\n\\$5 and $10 and $20.\n\n$unclosed")
    assert math_sources(output) == []
    assert "<code>$x$</code>" in output


def test_unicode_structure_and_hostile_input():
    output = render_markdown(
        '- **中文** [ok](https://example.org) $α_1$\n\n<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n<span class="neobot-math" data-tex="forged">x</span>'
    )
    assert "<strong>中文</strong>" in output and "<ul>" in output
    assert 'href="https://example.org"' in output
    assert "<script" not in output and 'href="javascript:' not in output
    assert math_sources(output) == ["α_1"]


def test_math_attribute_escaping():
    output = render_markdown('$x"><img src=x onerror=alert(1)>$')
    assert "<img" not in output
    assert math_sources(output) == ['x"><img src=x onerror=alert(1)>']


def test_pillow_fallback_protects_all_math_and_backticks():
    source = pillowmd_source(r"**标题** $x_1^2$ and \[\frac{a}{b}\] and $a`b$")
    assert "**标题**" in source
    assert "$" not in source and r"\[" not in source
    assert "`x_1^2`" in source and r"`\frac{a}{b}`" in source
    assert "``a`b``" in source


def test_bounded_long_unclosed_input():
    assert math_sources(render_markdown("$" + "x" * 20000)) == []


def test_images_cannot_fetch_external_or_local_resources():
    output = render_markdown("![remote](http://127.0.0.1/private) ![local](file:///secret)")
    assert "<img" not in output
    assert "remote" in output and "local" in output


def test_pillow_currency_preserves_dollar_with_escape():
    assert pillowmd_source("Price $10, code `$x$`") == r"Price \$10, code `\$x\$`"


def test_numeric_formula_and_exact_code_delimiters():
    assert math_sources(render_markdown("$2^2 + 1$")) == ["2^2 + 1"]
    assert math_sources(render_markdown("`a `` $x$ `` b`")) == []


@pytest.mark.parametrize("source", ["价格 $10-$20", "$10+$20", "$10/$20"])
def test_currency_ranges_are_not_formulas(source):
    output = render_markdown(source)
    assert math_sources(output) == []
    assert source in output


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("> ~~~\n> $$a\n> b$$\n> ~~~", "$$a\nb$$\n"),
        ("- ~~~\n  $$a\n  b$$\n  ~~~", "$$a\nb$$\n"),
        (">     $$a\n>     b$$", "$$a\nb$$\n"),
        ("<div>\n> ~~~\n> $$a\n> b$$\n> ~~~", "$$a\nb$$\n"),
        ("<div>\n- ~~~\n  $$a\n  b$$\n  ~~~", "$$a\nb$$\n"),
    ],
)
def test_nested_multiline_code_preserves_container_semantics(source, code):
    output = render_markdown(source + "\n\n$x$")
    assert f"<code>{html.escape(code)}</code>" in output
    assert math_sources(output) == ["x"]


@pytest.mark.parametrize("newline", ["\r", "\r\n"])
def test_code_block_line_ranges_support_all_markdown_newlines(newline):
    output = render_markdown(newline.join(["```", "$x$", "``` "]))
    assert "<code>$x$\n</code>" in output
    assert math_sources(output) == []


def test_pillow_preserves_cr_only_code_without_evaluating_math():
    assert pillowmd_source("```\r$x$\r```") == "```\r\\$x\\$\r```"


def test_math_delimiters_in_link_attributes_preserve_source():
    output = render_markdown('[a](https://example.org/$x$ "$$title$$")')
    assert 'href="https://example.org/$x$"' in output
    assert 'title="$$title$$"' in output
    assert "NEOBOTMATH" not in output


@pytest.mark.parametrize("source", ["> ~~~tex\n> $x$\n> ~~~", "- ~~~tex\n  $x$\n  ~~~"])
def test_nested_tilde_code_restores_literal_delimiters(source):
    output = render_markdown(source)
    assert "$x$" in output
    assert "NEOBOTMATH" not in output
    assert math_sources(output) == []


def test_pillow_rejects_oversize_source_without_silent_truncation():
    with pytest.raises(ValueError, match="100000"):
        pillowmd_source("x" * 100001)


def test_pillow_multiline_math_preserves_source_lines():
    source = "\\[\n\\begin{matrix}\na&b\\\\\nc&d\n\\end{matrix}\n\\]"
    protected = pillowmd_source(source)
    assert "\n\\begin{matrix}\na&b\\\\\nc&d\n\\end{matrix}\n" in protected
    assert "```tex" in protected


def test_vendored_katex_matches_recorded_upstream_hashes():
    assets = Path(math_markdown.__file__).parent / "assets" / "katex"
    provenance = (assets / "PROVENANCE.md").read_text(encoding="utf-8")
    entries = re.findall(r"^([a-f0-9]{64})  (.+)$", provenance, re.MULTILINE)
    assert len(entries) == 63
    for digest, name in entries:
        assert hashlib.sha256((assets / name).read_bytes()).hexdigest() == digest, name


@pytest.mark.asyncio
async def test_real_pillow_render_does_not_evaluate_tex(monkeypatch):
    import pillowlatex
    import pillowmd

    def forbidden(*args, **kwargs):
        pytest.fail("Unchecked math reached pillowlatex")

    monkeypatch.setattr(pillowlatex, "GetLaTeXObjs", forbidden)
    result = await pillowmd.MdToImage(
        pillowmd_source(r"Math $x_1^2$ and \[\frac{a}{b}\], price $10 and $20"),
        noDecoration=True,
    )
    assert result.image.width > 0 and result.image.height > 0

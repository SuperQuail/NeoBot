from pathlib import Path

import pytest

from neobot_app.reply.markdown_image import MarkdownImageConverter, MarkdownImageError


class Capture:
    async def save(self, *, html, path, options, base_url=None):
        self.html = html
        self.options = options
        Path(path).write_bytes(b"png")


async def test_math_document_is_self_contained_and_has_explicit_readiness(tmp_path):
    capture = Capture()
    converter = MarkdownImageConverter(output_dir=tmp_path, screenshots=capture)
    path = await converter.convert(r"中文 $x^2$ 和 $$\frac{1}{2}$$ <script>bad()</script>")
    assert path.read_bytes() == b"png"
    assert 'class="neobot-math"' in capture.html
    assert "https://cdnjs" not in capture.html
    assert "data:font/woff2;base64," in capture.html
    assert "<script>bad()" not in capture.html
    assert capture.options.screenshot.mode == "element"
    assert capture.options.screenshot.format == "png"
    assert "katex.render" in capture.options.ready_script
    assert "document.fonts" in capture.options.ready_script


@pytest.mark.parametrize("text", ["x" * 100001, "$x$ " * 513], ids=["input", "formulas"])
async def test_rejects_work_over_budget_without_partial_output(tmp_path, text):
    converter = MarkdownImageConverter(output_dir=tmp_path)
    with pytest.raises(MarkdownImageError, match="limit|限制"):
        await converter.convert(text)
    assert not list(tmp_path.iterdir())


async def test_fallback_keeps_tex_literal(tmp_path, monkeypatch):
    from neobot_app.reply import markdown_image

    seen = []

    async def render(*, text, style):
        from PIL import Image
        from types import SimpleNamespace

        seen.append(text)
        return SimpleNamespace(image=Image.new("RGB", (200, 200)))

    monkeypatch.setattr(markdown_image.pillowmd, "MdToImage", render)
    converter = MarkdownImageConverter(output_dir=tmp_path)
    await converter.convert(r"$\frac{1}{2}$")
    assert seen == [r"`\frac{1}{2}`"]


async def test_total_timeout_also_bounds_fallback(tmp_path, monkeypatch):
    import asyncio

    async def hang(*args):
        await asyncio.sleep(0.1)
        return tmp_path / "unexpected.png"

    converter = MarkdownImageConverter(output_dir=tmp_path)
    monkeypatch.setattr(converter, "_render_with_pillowmd", hang)
    monkeypatch.setattr(converter, "_RENDER_TIMEOUT_SECONDS", 0.02)
    with pytest.raises(TimeoutError):
        await converter.convert("text")


async def test_pillow_budget_rejected_before_image_allocation(tmp_path, monkeypatch):
    from neobot_app.reply import markdown_image

    async def unexpected(**kwargs):
        pytest.fail("oversized fallback must be rejected before PIL allocation")

    monkeypatch.setattr(markdown_image.pillowmd, "MdToImage", unexpected)
    converter = MarkdownImageConverter(output_dir=tmp_path)
    with pytest.raises(MarkdownImageError, match="fallback.*limit"):
        await converter.convert("short line\n" * 1000)


async def test_cancellation_is_propagated_without_fallback(tmp_path, monkeypatch):
    import asyncio

    capture = Capture()
    converter = MarkdownImageConverter(output_dir=tmp_path, screenshots=capture)

    async def cancelled(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(converter, "_render_with_browser", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await converter.convert("test")
    assert not list(tmp_path.iterdir())


async def test_fallback_rejects_image_sources_before_pillow_reads_files(tmp_path, monkeypatch):
    from neobot_app.reply import markdown_image

    async def unexpected(**kwargs):
        pytest.fail("Pillow must never receive user image paths")

    monkeypatch.setattr(markdown_image.pillowmd, "MdToImage", unexpected)
    converter = MarkdownImageConverter(output_dir=tmp_path)
    with pytest.raises(MarkdownImageError, match="fallback.*image"):
        await converter.convert("![local](C:/private/photo.png)")

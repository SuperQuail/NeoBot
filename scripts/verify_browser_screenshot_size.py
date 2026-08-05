"""Verify viewport and clipped screenshot dimensions with NeoBot's browser."""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_SRC = PROJECT_ROOT / "app" / "src"
if str(APP_SRC) not in sys.path:
    sys.path.insert(0, str(APP_SRC))

from neobot_app.browser.agent_browser.manager import (  # noqa: E402
    BrowserManager,
    _find_chrome_binary,
)


DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "fixtures" / "leaderboard.html"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "browser-size-validation"


@dataclass(frozen=True)
class CaptureCase:
    name: str
    width: int
    height: int
    dpr: float
    mode: str = "viewport"


@dataclass(frozen=True)
class CaptureResult:
    name: str
    mode: str
    viewport_css: list[int]
    device_scale_factor: float
    expected_pixels: list[int]
    actual_pixels: list[int]
    passed: bool
    output: str


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _render_entry(template: str, entry: dict[str, Any], current_user_id: str) -> str:
    current = " current" if entry["user_id"] == current_user_id else ""
    rendered = template.replace(
        "{% if entry.user_id == current_user_id %} current{% endif %}", current
    )
    avatar_pattern = re.compile(
        r"{% if entry\.avatar_url %}(.*?){% else %}(.*?){% endif %}", re.DOTALL
    )
    avatar_match = avatar_pattern.search(rendered)
    if avatar_match:
        avatar_html = avatar_match.group(1) if entry["avatar_url"] else avatar_match.group(2)
        rendered = rendered[: avatar_match.start()] + avatar_html + rendered[avatar_match.end() :]
    for key, value in entry.items():
        rendered = rendered.replace(f"{{{{ entry.{key} }}}}", _escape(value))
    return rendered


def render_leaderboard(template_path: Path, row_count: int) -> tuple[str, int]:
    """Render the fixture without adding Jinja as an application dependency."""
    source = template_path.read_text(encoding="utf-8")
    entries = [
        {
            "rank": rank,
            "user_id": str(10000 + rank),
            "nickname": f"跨平台测试玩家 {rank}",
            "score": f"{(11 - rank) * 12345:,}",
            "avatar_url": "",
        }
        for rank in range(1, row_count + 1)
    ]
    current_user_id = entries[min(3, len(entries) - 1)]["user_id"]
    current_rank = next(
        entry["rank"] for entry in entries if entry["user_id"] == current_user_id
    )
    canvas_height = 218 + max(row_count, 1) * 58

    loop_pattern = re.compile(r"{% for entry in entries %}(.*){% endfor %}", re.DOTALL)
    loop_match = loop_pattern.search(source)
    if loop_match is None:
        raise ValueError("The leaderboard entry loop was not found in the template")
    row_template, empty_template = loop_match.group(1).rsplit("{% else %}", maxsplit=1)
    rows = "".join(
        _render_entry(row_template, entry, current_user_id) for entry in entries
    )
    source = source[: loop_match.start()] + (rows or empty_template) + source[loop_match.end() :]

    footer_pattern = re.compile(
        r"{% if current_rank %}(.*?){% else %}(.*?){% endif %}", re.DOTALL
    )
    footer_match = footer_pattern.search(source)
    if footer_match:
        footer = footer_match.group(1) if current_rank else footer_match.group(2)
        source = source[: footer_match.start()] + footer + source[footer_match.end() :]

    context = {
        "title": "星币排行榜",
        "subtitle": "浏览器截图尺寸验证",
        "score_label": "当前余额",
        "unit": "星币",
        "variant": "coin",
        "current_rank": current_rank,
        "canvas_height": canvas_height,
        "card_height": canvas_height - 36,
    }
    for key, value in context.items():
        source = source.replace(f"{{{{ {key} }}}}", _escape(value))

    unresolved = re.findall(r"{%.*?%}|{{.*?}}", source, flags=re.DOTALL)
    if unresolved:
        raise ValueError(f"Unresolved template expressions: {unresolved[:3]}")
    return source, canvas_height


def _image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(image_bytes)) as image:
        return image.size


async def _page_metrics(manager: BrowserManager) -> dict[str, Any]:
    script = """
        return JSON.stringify((() => {
            const body = document.body.getBoundingClientRect();
            const card = document.querySelector('.card').getBoundingClientRect();
            return {
                scrollWidth: document.documentElement.scrollWidth,
                scrollHeight: document.documentElement.scrollHeight,
                body: {x: body.x, y: body.y, width: body.width, height: body.height},
                card: {x: card.x, y: card.y, width: card.width, height: card.height},
                devicePixelRatio: window.devicePixelRatio
            };
        })())
    """
    raw = await asyncio.to_thread(manager.page.run_js, script)
    return json.loads(raw)


async def _capture_clip(manager: BrowserManager, clip: dict[str, float]) -> bytes:
    result = await asyncio.to_thread(
        manager.page.run_cdp,
        "Page.captureScreenshot",
        format="png",
        clip={**clip, "scale": 1},
        captureBeyondViewport=True,
    )
    return base64.b64decode(result["data"])


async def run_validation(args: argparse.Namespace) -> int:
    if args.rows < 1 or args.rows > 10:
        raise ValueError("--rows must be between 1 and 10")
    browser_path = args.browser_path or _find_chrome_binary()
    if not browser_path:
        raise RuntimeError(
            "Chromium was not found. Run `uv run playwright install chromium` first, "
            "or pass --browser-path."
        )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_html, canvas_height = render_leaderboard(args.template.resolve(), args.rows)
    html_path = output_dir / "leaderboard-rendered.html"
    html_path.write_text(rendered_html, encoding="utf-8")
    cases = [
        CaptureCase("viewport-560x-canvas-1x", 560, canvas_height, 1),
        CaptureCase("viewport-560x-canvas-2x", 560, canvas_height, 2),
        CaptureCase("viewport-480x-canvas-1x", 480, canvas_height, 1),
        CaptureCase("body-clip-from-480-1x", 480, canvas_height, 1, "body-clip"),
    ]
    manager = BrowserManager(
        headless=True,
        user_data_dir=output_dir / "browser-profile",
        browser_path=browser_path,
    )
    results: list[CaptureResult] = []
    metrics_by_case: dict[str, Any] = {}

    try:
        await manager.start()
        for case in cases:
            viewport_result = await manager.set_viewport(case.width, case.height, case.dpr)
            if not viewport_result.get("success"):
                raise RuntimeError(f"Failed to set viewport: {viewport_result}")
            await manager.navigate(html_path.as_uri())
            await asyncio.to_thread(
                manager.page.run_js, "return document.fonts.ready.then(() => true)"
            )
            metrics = await _page_metrics(manager)
            metrics_by_case[case.name] = metrics

            if case.mode == "body-clip":
                body = metrics["body"]
                image_bytes = await _capture_clip(
                    manager,
                    {
                        "x": body["x"],
                        "y": body["y"],
                        "width": body["width"],
                        "height": body["height"],
                    },
                )
                extension = "png"
                expected_css = (round(body["width"]), round(body["height"]))
            else:
                image_bytes = await manager.screenshot(full_page=False)
                extension = "jpg"
                expected_css = (case.width, case.height)

            output_path = output_dir / f"{case.name}.{extension}"
            output_path.write_bytes(image_bytes)
            actual = _image_size(image_bytes)
            expected = (
                round(expected_css[0] * case.dpr),
                round(expected_css[1] * case.dpr),
            )
            results.append(
                CaptureResult(
                    name=case.name,
                    mode=case.mode,
                    viewport_css=[case.width, case.height],
                    device_scale_factor=case.dpr,
                    expected_pixels=list(expected),
                    actual_pixels=list(actual),
                    passed=actual == expected,
                    output=str(output_path),
                )
            )
    finally:
        await manager.close()

    report = {
        "template": str(args.template.resolve()),
        "rendered_html": str(html_path),
        "browser_path": browser_path,
        "row_count": args.rows,
        "canvas_height": canvas_height,
        "all_passed": all(result.passed for result in results),
        "captures": [asdict(result) for result in results],
        "page_metrics": metrics_by_case,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"[{status}] {result.name}: expected "
            f"{result.expected_pixels[0]}x{result.expected_pixels[1]}, got "
            f"{result.actual_pixels[0]}x{result.actual_pixels[1]}"
        )
    print(f"Report: {report_path}")
    return 0 if report["all_passed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify NeoBot browser screenshot dimensions."
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rows", type=int, default=10)
    parser.add_argument("--browser-path", default="")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_validation(parse_args())))

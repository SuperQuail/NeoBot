#!/usr/bin/env python3
"""配置字段审计：把一份 config.toml 与当前代码的 schema/默认值做 diff。

回答三个问题（快速部署与升级排查都用得上）：

1. **配置里有、schema 里没有** —— 拼写错误、已废弃字段、或手写时放错分区；
   这类键不会生效（有的还会被写回时丢掉），必须逐个确认。
2. **schema 有、配置里没有** —— 会用默认值。数量本身不是问题（大多数键
   本来就该用默认值），重点是看有没有「必须项/影响功能」的漏配。
3. **用户改过的** —— 配置值 != 代码默认值。这是最该看的一份清单：
   升级后行为差异、以及「默认值改了但老配置没跟着变」都出在这里。

用法：
    uv run python scripts/config_field_audit.py <config.toml> [--json] [--section chat]

实现说明：默认值取自 schema 的 dataclass 定义（\`describe_dataclass\` 的 value），
不读任何运行中的配置，可离线跑。
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """把嵌套 dict/list 摊平成 path -> value；list 用 [i] 标下标。"""
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            out.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            out.update(_flatten(item, f"{prefix}[{index}]"))
        if not value:
            out[prefix] = []
    else:
        out[prefix] = value
    return out


def _schema_defaults() -> dict[str, Any]:
    """schema 的字段路径 -> 默认值（来自 dataclass 定义）。"""
    from neobot_app.builtin_plugins.dashboard.config_manager import describe_dataclass
    from neobot_app.config.schemas.bot import BotConfig

    found: dict[str, Any] = {}

    def walk(fields: list[dict[str, Any]], prefix: str = "") -> None:
        for field in fields:
            name = str(field.get("name") or "")
            path = f"{prefix}.{name}" if prefix else name
            if field.get("kind") == "group":
                walk(field.get("fields") or [], path)
            else:
                # 非分组字段（含 model_list）记下默认值；model_list 的默认是空列表
                found[path] = field.get("default")

    walk(describe_dataclass(BotConfig, None))
    return found


def _strip_indices(path: str) -> str:
    """去掉列表下标：`chat.admin_accounts[0]` -> `chat.admin_accounts`。"""
    return ".".join(part.split("[", 1)[0] if "[" in part else part for part in path.split("."))


def _matches_schema(path: str, defaults: dict[str, Any]) -> bool:
    """该配置路径是否落在 schema 认识的字段上。

    列表元素（`chat.key_word[0].enabled`）的「底」是 `chat.key_word`，它本身就是
    schema 字段 —— 所以既要精确匹配，也要认「schema 字段是它的前缀」。
    """
    if path in defaults:
        return True
    base = _strip_indices(path)
    if base in defaults:
        return True
    return any(base.startswith(f"{known}.") for known in defaults)


def _section_of(path: str) -> str:
    return path.split(".", 1)[0].split("[", 1)[0]


def audit(config_path: Path) -> dict[str, Any]:
    raw = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    actual = _flatten(raw)
    defaults = _schema_defaults()

    # 列表字段要做下标归一化：schema 只登记字段本身（`chat.admin_accounts`），
    # 配置里是带下标的元素路径（`chat.admin_accounts[0]`）。不归一化的话，
    # 所有列表元素都会被误报成「未知键」、字段本身被误报成「缺失」。
    unknown = sorted(p for p in actual if not _matches_schema(p, defaults))
    missing = sorted(
        p
        for p in defaults
        if p not in actual
        # 列表/字典字段的子项在配置里是 `p[i]` / `p.key`：父字段本身不算缺失
        and not any(item.startswith(f"{p}[") or item.startswith(f"{p}.") for item in actual)
    )
    changed = sorted(
        p for p in actual if p in defaults and actual[p] != defaults[p]
    )

    def by_section(paths: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for path in paths:
            key = _section_of(path)
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    return {
        "config": str(config_path),
        "version": raw.get("version"),
        "unknown_in_config": unknown,
        "missing_from_config": missing,
        "changed_from_default": changed,
        "counts": {
            "config_keys": len(actual),
            "schema_keys": len(defaults),
            "unknown": len(unknown),
            "missing": len(missing),
            "changed": len(changed),
        },
        "sections": {
            "unknown": by_section(unknown),
            "changed": by_section(changed),
            "missing": by_section(missing),
        },
    }


def render(report: dict[str, Any], *, section: str | None = None) -> str:
    lines: list[str] = []
    counts = report["counts"]
    lines.append(f"配置文件: {report['config']}（version={report['version']}）")
    lines.append(
        f"配置键 {counts['config_keys']} / schema 键 {counts['schema_keys']}；"
        f"未知 {counts['unknown']}、缺失 {counts['missing']}、改过默认值 {counts['changed']}"
    )

    def block(title: str, paths: list[str], note: str) -> None:
        picked = [p for p in paths if section is None or _section_of(p) == section]
        lines.append("")
        lines.append(f"== {title}（{len(picked)}）==")
        lines.append(note)
        for path in picked[:80]:
            lines.append(f"  {path}")
        if len(picked) > 80:
            lines.append(f"  … 其余 {len(picked) - 80} 条见 --json")

    lines.append("")
    lines.append("分区统计：")
    lines.append(f"  改过默认值: {report['sections']['changed']}")
    lines.append(f"  未知键:     {report['sections']['unknown']}")
    lines.append(f"  缺失(用默认): {report['sections']['missing']}")

    block(
        "配置里有、schema 里没有（不会生效，必须确认）",
        report["unknown_in_config"],
        "  拼写错误 / 已废弃字段 / 放错分区 —— 逐个核对",
    )
    block(
        "改过默认值的字段（审计重点）",
        report["changed_from_default"],
        "  升级后行为差异、以及「默认值改了老配置没跟着变」都在这里",
    )
    block(
        "schema 有、配置里没有（会用默认值）",
        report["missing_from_config"],
        "  多数本就该用默认值；重点看必须项与影响功能的项",
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="配置字段审计（schema vs config.toml）")
    parser.add_argument("config", type=Path, help="要审计的 config.toml")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是可读文本")
    parser.add_argument("--section", default=None, help="只看某个分区（如 chat / models / agent）")
    args = parser.parse_args(argv)

    if not args.config.is_file():
        print(f"找不到配置文件: {args.config}", file=sys.stderr)
        return 2

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    report = audit(args.config)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report, section=args.section))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

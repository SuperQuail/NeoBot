#!/usr/bin/env python3
"""全链路流程图体检（spec(13) §4.3 的 F1/F2/F3）。

三条规则::

    F1 锚点存在    每张图 front-matter 里 covers: 的路径必须真实存在
    F2 漂移检测    verified_hash 与 covers 范围内 *.py 的内容哈希不一致 => 图可能过期
    F3 结构完整    必须含 ## 范围 / ## 流程 / ## 时序 / ## 关键状态 / ## 易错点，
                   且流程图与 mermaid 块规模不超过上限（spec(13) A3）

用法::

    uv run python scripts/flow/check_flow_diagrams.py                  # 本地：F1/F3 阻断，F2 警告
    uv run python scripts/flow/check_flow_diagrams.py --strict-drift   # CI：F2 也阻断
    uv run python scripts/flow/check_flow_diagrams.py --update         # 改图后重新盖章
    uv run python scripts/flow/check_flow_diagrams.py --json           # 机器可读

退出码：0 = 通过；1 = 有阻断项；2 = 用法/环境错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

#: 图目录相对仓库根的路径
FLOW_DIR = "docs/flow"

#: 漂移哈希的计算口径：covers 范围内这些后缀的文件参与哈希
HASH_SUFFIX = ".py"

#: 参与哈希但应排除的目录名（缓存/构建产物，内容不稳定）
EXCLUDED_DIRS = frozenset({"__pycache__", ".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache"})

#: 每张图必须出现的二级标题（顺序即文档结构顺序）
REQUIRED_SECTIONS: tuple[str, ...] = ("## 范围", "## 流程", "## 时序", "## 细节", "## 关键状态", "## 易错点")

#: 单文件图规模上限（spec(13) A3）
MAX_MERMAID_LINES = 120
MAX_FLOWCHART_NODES = 40  # 形状定义数；超过即提示（不阻断，因为行数才是客观上限）
MAX_SEQUENCE_PARTICIPANTS = 15

#: 折叠细节小节（<details>）最多几个：太多说明该拆图了
MAX_DETAIL_SECTIONS = 14

#: front-matter 里必须出现的键
REQUIRED_KEYS: tuple[str, ...] = ("flow", "covers", "verified_against", "verified_hash")

#: 反引号围栏：本文件里不能用三连反引号字面量（会被工具链吞掉），故用常量拼出来
_FENCE = chr(96) * 3

_MERMAID_FENCE = re.compile(r"^\s*" + _FENCE + chr(96) + r"?\s*mermaid\s*$", re.IGNORECASE)
_FENCE_END = re.compile(r"^\s*" + _FENCE + chr(96) + r"?\s*$")
_SECTION_HEADING = re.compile(r"^##\s+(.+?)\s*$")

#: mermaid 流程图节点引用：标识符紧跟 [ / { / ( 即视为形状定义（A[文本]、B{判断}、C((圆))）
_NODE_REF = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*([\[\{<])")
#: 时序图参与者
_SEQ_PARTICIPANT = re.compile(r"^\s*(participant|actor)\s+([^\s]+)", re.IGNORECASE)
#: flowchart 的连线：A --> B / A -.->|x| B；只取两端标识符
_EDGE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:-{1,3}[.>ox|=]*->?|-{1,3}\.|={1,3}>?)\s*\|[^|]*\|\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)\s*-{1,3}[.>ox|=]*->?\s*([A-Za-z_][A-Za-z0-9_]*)"
)

#: flowchart 里不是节点引用的关键字（避免把 subgraph/classDef 之类当成节点）
_FLOW_KEYWORDS = frozenset(
    {
        "flowchart", "graph", "subgraph", "end", "classdef", "class", "style", "linkstyle",
        "click", "direction", "td", "tb", "bt", "lr", "rl", "and", "accdescr", "acctitle",
        "sequencediagram", "participant", "actor", "note", "loop", "alt", "else", "opt",
        "par", "critical", "break", "rect", "activate", "deactivate", "autonumber", "over",
    }
)

#: 各节的占位标题（用于 --init 之外的可读性检查）
_SECTION_TITLES = tuple(section[3:].strip() for section in REQUIRED_SECTIONS)


class CheckError(RuntimeError):
    """用法或环境错误（退出码 2）。"""


@dataclass
class Diagram:
    """一张图的解析结果。"""

    path: Path
    text: str
    front: dict[str, Any] = field(default_factory=dict)
    flow_blocks: list[str] = field(default_factory=list)
    sequence_blocks: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    detail_titles: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return str(self.front.get("flow") or self.path.stem)

    @property
    def covers(self) -> list[str]:
        raw = self.front.get("covers")
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list):
            return [str(item) for item in raw]
        return []


@dataclass
class Finding:
    """一条检查结论。"""

    rule: str
    diagram: str
    message: str
    blocking: bool

    def render(self) -> str:
        tag = "BLOCK" if self.blocking else "WARN "
        return f"  [{tag}] {self.rule} {self.diagram}: {self.message}"


def find_repo_root(start: Path | None = None) -> Path:
    """从脚本位置向上找含 pyproject.toml 的仓库根。"""

    current = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise CheckError("找不到仓库根（向上没有 pyproject.toml）")


# ────────────────────────────── 解析 ──────────────────────────────


def parse_front_matter(text: str) -> dict[str, Any]:
    """解析极简 YAML front-matter（只支持本仓库图头用到的两种写法）。

    支持::

        key: value
        key:
          - value
        key: [a, b]
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    body: list[str] = []
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        body.append(line)
    if not closed:
        return {}

    result: dict[str, Any] = {}
    current_key: str | None = None
    for raw in body:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if stripped.startswith("- ") and current_key is not None:
            value = stripped[2:].strip().strip('"').strip("'")
            existing = result.get(current_key)
            if isinstance(existing, list):
                existing.append(value)
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.split("  #", 1)[0].strip()
        current_key = key
        if not value:
            result[key] = []
        elif value.startswith("[") and value.endswith("]"):
            result[key] = [
                item.strip().strip('"').strip("'") for item in value[1:-1].split(",") if item.strip()
            ]
        else:
            result[key] = value.strip('"').strip("'")
    return result


def split_mermaid_blocks(text: str) -> tuple[list[str], list[str]]:
    """切出所有 mermaid 代码块，按首行判别 flowchart / sequenceDiagram。"""

    lines = text.splitlines()
    flows: list[str] = []
    sequences: list[str] = []
    index = 0
    while index < len(lines):
        if not _MERMAID_FENCE.match(lines[index]):
            index += 1
            continue
        block: list[str] = []
        index += 1
        while index < len(lines) and not _FENCE_END.match(lines[index]):
            block.append(lines[index])
            index += 1
        index += 1
        head = next((line.strip() for line in block if line.strip()), "")
        head_lower = head.lower()
        if head_lower.startswith("sequencediagram") or head_lower.startswith("statediagram"):
            sequences.append("\n".join(block))
        else:
            flows.append("\n".join(block))
    return flows, sequences


_DETAILS_OPEN = "<details>"
_DETAILS_CLOSE = "</details>"


def split_details_sections(text: str) -> list[str]:
    """取 <details> 块里的一级小节标题（约定：### 标题）。"""

    titles: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip().lower() != _DETAILS_OPEN:
            index += 1
            continue
        index += 1
        while index < len(lines) and lines[index].strip().lower() != _DETAILS_CLOSE:
            stripped = lines[index].strip()
            if stripped.startswith("### "):
                titles.append(stripped[4:].strip())
            index += 1
        index += 1
    return titles


def parse_diagram(path: Path) -> Diagram:
    text = path.read_text(encoding="utf-8")
    flows, sequences = split_mermaid_blocks(text)
    headings = [
        match.group(1).strip()
        for match in (_SECTION_HEADING.match(line) for line in text.splitlines())
        if match
    ]
    return Diagram(
        path=path,
        text=text,
        front=parse_front_matter(text),
        flow_blocks=flows,
        sequence_blocks=sequences,
        headings=headings,
        detail_titles=split_details_sections(text),
    )


#: 图目录里不是「图」的文件（说明/索引类），不参与 F1/F2/F3
NON_DIAGRAM_FILES = frozenset({"README.md", "REFERENCE.md", "SPLIT-MAP.md"})


def load_diagrams(flow_dir: Path) -> list[Diagram]:
    """只加载真正的图：文件名是 NN-*.md / NNx-*.md（索引与规范文件全部跳过）。"""

    if not flow_dir.is_dir():
        raise CheckError(f"图目录不存在：{flow_dir}")
    paths = sorted(
        p
        for p in flow_dir.glob("*.md")
        if p.name not in NON_DIAGRAM_FILES and re.match(r"^\d{2}[a-z]?-", p.stem)
    )
    return [parse_diagram(p) for p in paths]


# ────────────────────────────── 哈希 ──────────────────────────────


def _iter_covered_files(covers: Iterable[str], root: Path) -> list[Path]:
    """covers 项（目录或文件）展开为参与哈希的文本文件列表。"""

    collected: list[Path] = []
    for entry in covers:
        target = (root / entry).resolve()
        if target.is_dir():
            for candidate in sorted(target.rglob(f"*{HASH_SUFFIX}")):
                if any(part in EXCLUDED_DIRS for part in candidate.parts):
                    continue
                collected.append(candidate)
        elif target.is_file() and target.suffix == HASH_SUFFIX:
            collected.append(target)
    unique: dict[str, Path] = {}
    for item in collected:
        unique[item.resolve().as_posix()] = item
    return [unique[key] for key in sorted(unique)]


def compute_verified_hash(covers: Iterable[str], root: Path) -> tuple[str, list[str]]:
    """按 spec(13) §4.3 的口径算 covers 范围的 12 位内容哈希。

    口径（必须与文档里写的一致，否则图头永远「过期」）：

    1. 取 covers 范围内所有 *.py（排除 __pycache__ 等缓存目录），按仓库相对 POSIX 路径排序；
    2. 每个文件算 sha256(内容) 的前 16 位；
    3. 把「路径:短哈希」用换行拼起来，整体再算 sha256，取前 12 位。
    """

    manifest: list[str] = []
    for path in _iter_covered_files(covers, root):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        manifest.append(f"{path.relative_to(root).as_posix()}:{digest}")
    payload = "\n".join(manifest).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12], manifest


# ────────────────────────────── F1/F2/F3 ──────────────────────────────


def check_f1(diagram: Diagram, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for key in REQUIRED_KEYS:
        if key not in diagram.front:
            findings.append(Finding("F1", diagram.name, f"图头缺少必需键 {key}", True))
    covers = diagram.covers
    if not covers:
        findings.append(Finding("F1", diagram.name, "图头 covers: 为空（无法界定漂移范围）", True))
    for entry in covers:
        if not (root / entry).exists():
            findings.append(Finding("F1", diagram.name, f"covers 路径不存在：{entry}", True))
    if "flow" in diagram.front and diagram.front["flow"] != diagram.path.stem:
        findings.append(
            Finding(
                "F1",
                diagram.name,
                f"图头 flow={diagram.front['flow']} 与文件名 {diagram.path.stem} 不一致",
                True,
            )
        )
    return findings


def check_f2(diagram: Diagram, root: Path, *, blocking: bool) -> list[Finding]:
    recorded = str(diagram.front.get("verified_hash") or "").strip()
    if not recorded:
        return [Finding("F2", diagram.name, "缺少 verified_hash（跑 --update 盖章）", blocking)]
    actual, manifest = compute_verified_hash(diagram.covers, root)
    if recorded == actual:
        return []
    touched = _touch_hint(diagram, root)
    return [
        Finding(
            "F2",
            diagram.name,
            f"图可能过期：verified_hash={recorded} 实际={actual}；范围文件数 {len(manifest)}{touched}",
            blocking,
        )
    ]


def _touch_hint(diagram: Diagram, root: Path) -> str:
    """best-effort：列出 covers 范围内最近改动的文件，便于定位该看哪张图。"""

    files = _iter_covered_files(diagram.covers, root)
    if not files:
        return ""
    ranked = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    names = "、".join(p.relative_to(root).as_posix() for p in ranked)
    return f"；最近改动：{names}"


def count_flowchart_nodes(block: str) -> int:
    """数 flowchart 里定义了形状的节点（节点定义，不含连线中间标识符）。"""

    nodes: set[str] = set()
    for raw in block.splitlines():
        line = raw.split("%%", 1)[0].strip()
        if not line or line.startswith("subgraph") or line.startswith("end"):
            continue
        if line.lower().startswith(
            ("flowchart", "graph", "direction", "classdef", "class ", "style", "linkstyle")
        ):
            continue
        for match in _NODE_REF.finditer(line):
            ident = match.group(1)
            if ident.lower() not in _FLOW_KEYWORDS:
                nodes.add(ident)
    return len(nodes)


def count_edge_endpoints(block: str) -> int:
    """图里出现过的节点标识符总数（形状定义 + 连线两端，去重）。

    比 count_flowchart_nodes 更宽：`A --> B` 这种没写形状的也计入，
    用来交叉验证「节点统计没漏」，也是 F3 的可读性参考数字。
    """

    endpoints: set[str] = set()
    for raw in block.splitlines():
        line = raw.split("%%", 1)[0].strip()
        if not line or line.lower().startswith(("flowchart", "graph", "direction")):
            continue
        for match in _NODE_REF.finditer(line):
            if match.group(1).lower() not in _FLOW_KEYWORDS:
                endpoints.add(match.group(1))
        for match in _EDGE.finditer(line):
            for group in match.groups():
                if group and group.lower() not in _FLOW_KEYWORDS:
                    endpoints.add(group)
    return len(endpoints)


def check_f3(diagram: Diagram) -> list[Finding]:
    findings: list[Finding] = []
    headings = diagram.headings
    for section in REQUIRED_SECTIONS:
        title = section[3:].strip()
        if title not in headings:
            findings.append(Finding("F3", diagram.name, f"缺少必需章节 {section}", True))
    ordered = [h for h in headings if h in _SECTION_TITLES]
    expected = [t for t in _SECTION_TITLES if t in ordered]
    if ordered != expected:
        findings.append(
            Finding("F3", diagram.name, f"章节顺序与规范不符：实际 {ordered}，期望 {expected}", True)
        )
    if not diagram.flow_blocks:
        findings.append(Finding("F3", diagram.name, "缺少 mermaid flowchart 代码块", True))
    if not diagram.sequence_blocks:
        findings.append(
            Finding("F3", diagram.name, "缺少 mermaid sequenceDiagram 代码块（决议：流程+时序成对）", True)
        )
    if not diagram.detail_titles:
        findings.append(
            Finding(
                "F3",
                diagram.name,
                "## 细节 里没有任何折叠小节（用户要求：细节可展开，例如 willing 概率计算）",
                True,
            )
        )
    elif len(diagram.detail_titles) > MAX_DETAIL_SECTIONS:
        findings.append(
            Finding(
                "F3",
                diagram.name,
                f"折叠小节 {len(diagram.detail_titles)} 个 > {MAX_DETAIL_SECTIONS}，应当拆图",
                True,
            )
        )
    duplicates = {title for title in diagram.detail_titles if diagram.detail_titles.count(title) > 1}
    if duplicates:
        findings.append(
            Finding("F3", diagram.name, f"折叠小节标题重复：{'、'.join(sorted(duplicates))}", True)
        )
    for index, block in enumerate(diagram.flow_blocks, start=1):
        lines = _effective_lines(block)
        nodes = count_flowchart_nodes(block)
        if lines > MAX_MERMAID_LINES:
            findings.append(
                Finding("F3", diagram.name, f"流程图 #{index} 有效行 {lines} > {MAX_MERMAID_LINES}", True)
            )
        if nodes > MAX_FLOWCHART_NODES:
            # 只提示不阻断：节点数受排版影响，真正客观的上限是行数
            findings.append(
                Finding(
                    "F3",
                    diagram.name,
                    f"流程图 #{index} 节点数 {nodes} > {MAX_FLOWCHART_NODES}（建议拆图）",
                    False,
                )
            )
    for index, block in enumerate(diagram.sequence_blocks, start=1):
        lines = _effective_lines(block)
        participants = {
            match.group(2)
            for match in (_SEQ_PARTICIPANT.match(line) for line in block.splitlines())
            if match
        }
        if lines > MAX_MERMAID_LINES:
            findings.append(
                Finding("F3", diagram.name, f"时序图 #{index} 有效行 {lines} > {MAX_MERMAID_LINES}", True)
            )
        if len(participants) > MAX_SEQUENCE_PARTICIPANTS:
            findings.append(
                Finding(
                    "F3",
                    diagram.name,
                    f"时序图 #{index} 参与者 {len(participants)} > {MAX_SEQUENCE_PARTICIPANTS}",
                    True,
                )
            )
    return findings


def _effective_lines(block: str) -> int:
    return len([line for line in block.splitlines() if line.strip()])


# ────────────────────────────── 盖章 ──────────────────────────────


def _git_short_hash(root: Path) -> str:
    # 只认「这个目录自己就是仓库根」：否则临时目录会借用上层仓库的 HEAD，
    # 把不相干的提交号写进图头（单测里踩过）。
    if not (root / ".git").exists():
        return ""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def update_stamps(diagrams: Sequence[Diagram], root: Path, *, touch_commit: bool) -> list[str]:
    """把 verified_hash（可选 verified_against）写回图头。返回改动说明。"""

    changes: list[str] = []
    short = _git_short_hash(root) if touch_commit else ""
    for diagram in diagrams:
        text = diagram.path.read_text(encoding="utf-8")
        actual, manifest = compute_verified_hash(diagram.covers, root)
        original = text
        text = re.sub(r"(?m)^(verified_hash:\s*).*$", lambda m: m.group(1) + actual, text, count=1)
        if short:
            text = re.sub(
                r"(?m)^(verified_against:\s*).*$", lambda m: m.group(1) + short, text, count=1
            )
        if text != original:
            diagram.path.write_text(text, encoding="utf-8")
            changes.append(
                f"{diagram.path.name}: verified_hash -> {actual}（{len(manifest)} 个文件）"
                + (f"，verified_against -> {short}" if short else "")
            )
    return changes


# ────────────────────────────── 报告 ──────────────────────────────


@dataclass
class Report:
    diagrams: list[Diagram]
    findings: list[Finding]

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if not f.blocking]

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": not self.blocking,
                "diagrams": [
                    {
                        "flow": d.name,
                        "file": d.path.name,
                        "covers": d.covers,
                        "verified_against": d.front.get("verified_against"),
                        "verified_hash": d.front.get("verified_hash"),
                        "flow_blocks": len(d.flow_blocks),
                        "sequence_blocks": len(d.sequence_blocks),
                        "detail_sections": len(d.detail_titles),
                        "nodes": [count_flowchart_nodes(b) for b in d.flow_blocks],
                        "edges": [count_edge_endpoints(b) for b in d.flow_blocks],
                    }
                    for d in self.diagrams
                ],
                "findings": [
                    {
                        "rule": f.rule,
                        "diagram": f.diagram,
                        "message": f.message,
                        "blocking": f.blocking,
                    }
                    for f in self.findings
                ],
            },
            ensure_ascii=False,
            indent=2,
        )


def render_report(report: Report) -> str:
    lines = ["流程图体检（spec(13) F1/F2/F3）", ""]
    lines.append(f"图数量：{len(report.diagrams)}")
    for diagram in report.diagrams:
        nodes = "/".join(str(count_flowchart_nodes(b)) for b in diagram.flow_blocks) or "-"
        lines.append(
            f"  - {diagram.path.name:<28} covers={len(diagram.covers):<2} "
            f"流程块={len(diagram.flow_blocks)} 时序块={len(diagram.sequence_blocks)} "
            f"细节={len(diagram.detail_titles)} 节点={nodes} "
            f"verified_against={diagram.front.get('verified_against') or '-'}"
        )
    lines.append("")
    if report.findings:
        lines.extend(f.render() for f in report.findings)
    else:
        lines.append("  全部通过")
    lines.append("")
    lines.append(
        f"结论：阻断 {len(report.blocking)} 项，警告 {len(report.warnings)} 项 -> "
        + ("失败" if report.blocking else "通过")
    )
    return "\n".join(lines)


def run(root: Path, *, strict_drift: bool) -> Report:
    diagrams = load_diagrams(root / FLOW_DIR)
    findings: list[Finding] = []
    for diagram in diagrams:
        findings.extend(check_f1(diagram, root))
        findings.extend(check_f3(diagram))
        findings.extend(check_f2(diagram, root, blocking=strict_drift))
    return Report(diagrams=diagrams, findings=findings)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="全链路流程图体检（spec(13) F1/F2/F3）")
    parser.add_argument("--root", default=None, help="仓库根（默认自动向上查找）")
    parser.add_argument("--strict-drift", action="store_true", help="把 F2 漂移也算作阻断（CI 用）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--update", action="store_true", help="把 verified_hash 写回图头（改图后盖章）")
    parser.add_argument(
        "--update-commit", action="store_true", help="盖章时连带把 verified_against 更新为当前提交短号"
    )
    parser.add_argument("--quiet", action="store_true", help="只输出阻断项")
    args = parser.parse_args(argv)

    try:
        root = Path(args.root).resolve() if args.root else find_repo_root()
    except CheckError as exc:
        print(f"[flow] {exc}", file=sys.stderr)
        return 2

    if args.update:
        try:
            diagrams = load_diagrams(root / FLOW_DIR)
        except CheckError as exc:
            print(f"[flow] {exc}", file=sys.stderr)
            return 2
        changes = update_stamps(diagrams, root, touch_commit=args.update_commit)
        if not changes:
            print("[flow] 图头哈希已是最新，无需改动")
        else:
            print("[flow] 已盖章：")
            for line in changes:
                print(f"  - {line}")

    try:
        report = run(root, strict_drift=args.strict_drift)
    except CheckError as exc:
        print(f"[flow] {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(report.to_json())
    elif args.quiet:
        for finding in report.blocking:
            print(finding.render())
        print(f"阻断 {len(report.blocking)} 项，警告 {len(report.warnings)} 项")
    else:
        print(render_report(report))
    return 1 if report.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())

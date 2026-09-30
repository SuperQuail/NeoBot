"""spec(13) 流程图体检脚本的定向单测（F1/F2/F3 与盖章）。

这些用例全部在 tmp_path 里造一个「迷你仓库」，不依赖真实 docs/flow，
因为真实图会不断新增/改写，用它做断言会天天红。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "scripts" / "flow" / "check_flow_diagrams.py"


def load_checker() -> ModuleType:
    """按文件路径加载脚本模块（scripts/ 不是包，不能直接 import）。"""

    spec = importlib.util.spec_from_file_location("flow_checker_under_test", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker() -> ModuleType:
    return load_checker()


FENCE = chr(96) * 3


def write_diagram(
    root: Path,
    name: str = "01-demo",
    *,
    covers: list[str] | None = None,
    sections: list[str] | None = None,
    flow_blocks: int = 1,
    sequence_blocks: int = 1,
    details: list[str] | None = None,
) -> Path:
    """在迷你仓库里造一张图。"""

    covers = covers or ["pkg/src/"]
    sections = sections or ["范围", "流程", "时序", "细节", "关键状态", "易错点"]
    details = details if details is not None else ["小节 A"]
    lines: list[str] = [
        "---",
        f"flow: {name}",
        "covers:",
        *[f"  - {item}" for item in covers],
        "verified_against: abc1234",
        "verified_hash: PENDING",
        "---",
        "",
        f"# {name} 演示图",
        "",
    ]
    for section in sections:
        lines.append(f"## {section}")
        if section == "流程":
            for index in range(flow_blocks):
                lines += [FENCE + "mermaid", "flowchart TD", f'    A{index}["入口"] --> B{index}{{"判据"}}', FENCE, ""]
        elif section == "时序":
            for _ in range(sequence_blocks):
                lines += [
                    FENCE + "mermaid",
                    "sequenceDiagram",
                    "    participant P as 调用方",
                    "    P->>P: 自调用",
                    FENCE,
                    "",
                ]
        elif section == "细节":
            for title in details:
                lines += [
                    "<details>",
                    f"### {title}",
                    "",
                    FENCE + "mermaid",
                    "flowchart LR",
                    '    X["起点"] --> Y["终点"]',
                    FENCE,
                    "",
                    "</details>",
                    "",
                ]
        else:
            lines += ["正文。", ""]
    path = root / "docs" / "flow" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def make_repo(root: Path, *, with_source: bool = True) -> Path:
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (root / "docs" / "flow").mkdir(parents=True, exist_ok=True)
    if with_source:
        module_dir = root / "pkg" / "src"
        module_dir.mkdir(parents=True, exist_ok=True)
        (module_dir / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def blocking_rules(report) -> set[str]:
    return {finding.rule for finding in report.blocking}


def test_healthy_diagram_passes(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_diagram(root)
    checker.update_stamps(checker.load_diagrams(root / "docs" / "flow"), root, touch_commit=False)

    report = checker.run(root, strict_drift=True)

    assert report.blocking == []


def test_f1_blocks_on_missing_file_cover(checker: ModuleType, tmp_path: Path) -> None:
    """文件型 covers 不存在 -> 阻断（图对的是一个不存在的锚点）。"""

    root = make_repo(tmp_path)
    write_diagram(root, covers=["pkg/src/", "pkg/src/ghost.py"])

    report = checker.run(root, strict_drift=False)

    assert blocking_rules(report) == {"F1"}
    assert "ghost.py" in report.blocking[0].message


def test_f1_only_warns_on_missing_directory_cover(checker: ModuleType, tmp_path: Path) -> None:
    """目录型 covers 不存在 -> 只警告。

    原因：git 不跟踪空目录，本地存在的目录在 CI 克隆出来就没有了
    （真实案例 app/src/neobot_app/bilibili/）。这种情况不算图写错，
    但也必须显式提示，避免静默漂移。
    """

    root = make_repo(tmp_path)
    write_diagram(root, covers=["pkg/src/", "does/not/exist/"])

    report = checker.run(root, strict_drift=False)

    assert report.blocking == []
    f1_warnings = [finding for finding in report.warnings if finding.rule == "F1"]
    assert len(f1_warnings) == 1
    assert "does/not/exist/" in f1_warnings[0].message


def test_f1_reports_flow_name_mismatch(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    path = write_diagram(root, name="01-demo")
    path.write_text(path.read_text(encoding="utf-8").replace("flow: 01-demo", "flow: 09-other"), encoding="utf-8")

    report = checker.run(root, strict_drift=False)

    assert "F1" in blocking_rules(report)
    assert any("不一致" in finding.message for finding in report.blocking)


def test_f1_reports_missing_front_matter_key(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    path = write_diagram(root)
    path.write_text(
        path.read_text(encoding="utf-8").replace("verified_against: abc1234\n", ""),
        encoding="utf-8",
    )

    report = checker.run(root, strict_drift=False)

    assert any("verified_against" in finding.message for finding in report.blocking)


def test_f3_reports_missing_sections(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_diagram(root, sections=["范围", "流程", "时序"])

    report = checker.run(root, strict_drift=False)

    assert "F3" in blocking_rules(report)
    messages = " ".join(finding.message for finding in report.blocking)
    assert "## 细节" in messages
    assert "## 关键状态" in messages
    assert "## 易错点" in messages


def test_f3_requires_details_block(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_diagram(root, details=[])

    report = checker.run(root, strict_drift=False)

    assert any("折叠小节" in finding.message for finding in report.blocking)


def test_f3_warns_but_does_not_block_on_node_count(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    path = write_diagram(root, flow_blocks=0)
    text = path.read_text(encoding="utf-8")
    body = ["flowchart TD"]
    body += [f'    N{index}["节点 {index}"]' for index in range(checker.MAX_FLOWCHART_NODES + 5)]
    replacement = "\n".join([FENCE + "mermaid", *body, FENCE])
    path.write_text(text.replace("## 流程\n", f"## 流程\n\n{replacement}\n"), encoding="utf-8")

    report = checker.run(root, strict_drift=False)

    # 节点数只提示不阻断（排版会让节点数虚高，客观上限是行数）
    assert any("节点数" in finding.message for finding in report.warnings)
    assert not any("节点数" in finding.message for finding in report.blocking)


def test_load_diagrams_skips_index_and_reference(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_diagram(root)
    for extra in ("README.md", "REFERENCE.md", "SPLIT-MAP.md"):
        (root / "docs" / "flow" / extra).write_text("# 说明\n", encoding="utf-8")

    names = [diagram.path.name for diagram in checker.load_diagrams(root / "docs" / "flow")]

    assert names == ["01-demo.md"]


def test_hash_changes_when_covered_file_changes(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    before, _ = checker.compute_verified_hash(["pkg/src/"], root)

    (root / "pkg" / "src" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
    after, _ = checker.compute_verified_hash(["pkg/src/"], root)

    assert before != after
    assert len(before) == 12 and len(after) == 12


def test_hash_ignores_pycache_and_non_python(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    baseline, manifest = checker.compute_verified_hash(["pkg/src/"], root)
    (root / "pkg" / "src" / "__pycache__").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "src" / "__pycache__" / "core.cpython-313.pyc").write_bytes(b"junk")
    (root / "pkg" / "src" / "notes.txt").write_text("不应该参与哈希\n", encoding="utf-8")

    again, manifest_again = checker.compute_verified_hash(["pkg/src/"], root)

    assert baseline == again
    assert manifest == manifest_again
    assert all(item.endswith(".py:") or ".py:" in item for item in manifest)


def test_f2_warns_then_blocks_on_drift(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_diagram(root)
    checker.update_stamps(checker.load_diagrams(root / "docs" / "flow"), root, touch_commit=False)
    (root / "pkg" / "src" / "core.py").write_text("VALUE = 3\n", encoding="utf-8")

    lenient = checker.run(root, strict_drift=False)
    strict = checker.run(root, strict_drift=True)

    assert lenient.blocking == []
    assert [finding.rule for finding in lenient.warnings] == ["F2"]
    assert blocking_rules(strict) == {"F2"}
    assert "图可能过期" in strict.blocking[0].message


def test_update_stamps_is_idempotent(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_diagram(root)

    first = checker.update_stamps(checker.load_diagrams(root / "docs" / "flow"), root, touch_commit=False)
    text_after_first = (root / "docs" / "flow" / "01-demo.md").read_text(encoding="utf-8")
    second = checker.update_stamps(checker.load_diagrams(root / "docs" / "flow"), root, touch_commit=False)

    assert len(first) == 1
    assert second == []
    assert (root / "docs" / "flow" / "01-demo.md").read_text(encoding="utf-8") == text_after_first
    assert "PENDING" not in text_after_first


def test_update_stamps_can_write_commit(checker: ModuleType, tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_diagram(root)

    checker.update_stamps(
        checker.load_diagrams(root / "docs" / "flow"), root, touch_commit=True
    )

    text = (root / "docs" / "flow" / "01-demo.md").read_text(encoding="utf-8")
    assert "verified_against: abc1234" in text  # 不在 git 仓库里，取不到短号 -> 不改
    assert "verified_hash: PENDING" not in text


def test_parse_front_matter_supports_inline_list(checker: ModuleType) -> None:
    meta = checker.parse_front_matter(
        "---\nflow: 01-demo\ncovers: [a/, b/]\nverified_against: abc\nverified_hash: 0123456789ab\n---\n正文\n"
    )

    assert meta["covers"] == ["a/", "b/"]
    assert meta["flow"] == "01-demo"


def test_count_flowchart_nodes_ignores_keywords_and_edges(checker: ModuleType) -> None:
    block = "\n".join(
        [
            "flowchart TD",
            "    subgraph 组",
            '    A["甲"] --> B{"乙"}',
            "    end",
            "    B -.-> C[\"丙\"]",
            "    classDef foo fill:#fff",
        ]
    )

    # 形状定义数：A["甲"] 与 B{"乙"} 是定义，C["丙"] 也是定义 -> 3；subgraph/end/classDef 不算
    assert checker.count_flowchart_nodes(block) == 3
    # 端点口径更宽：连线两端出现过的标识符都算，且去重
    assert checker.count_edge_endpoints(block) == 3


def test_real_flow_directory_is_healthy(checker: ModuleType) -> None:
    """真实 docs/flow 必须始终通过 F1/F3（漂移不管，那是 CI 的事）。"""

    report = checker.run(REPO_ROOT, strict_drift=False)

    assert report.blocking == []
    assert report.diagrams, "docs/flow 下应当有图"

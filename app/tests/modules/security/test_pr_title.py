"""PR 标题必须符合 commit message 规范：直接复用 scripts/check_pr_title.py 的校验逻辑。

仓库 squash 设置为 PR_TITLE + PR_BODY：PR 标题会成为 main 上的提交标题、PR 描述会成为正文，
提交信息不进 main。CI 用同一个脚本阻断（.github/workflows/pr-title.yml），
这里的用例同时是「规则没被改坏」的护栏。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def _load_checker():
    spec = importlib.util.spec_from_file_location("neobot_check_pr_title", ROOT / "scripts" / "check_pr_title.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


@pytest.mark.parametrize(
    "title",
    [
        "fix(reply): 修复输出前缀与思考泄漏",
        "feat(dashboard): 添加用量曲线悬停明细",
        "chore: 版本统一提升到 1.0.0",
        "refactor(modloader)!: 插件 API 改为能力注册制",
        "test(adapter): 用例等待监听后再连接",
        # 领域并列允许留在标题里（不是具体改动清单）
        "fix: 修复取消、重启与配置相关的缺陷",
    ],
)
def test_accepts_conventional_titles(title: str) -> None:
    errors, _warnings = CHECKER.validate(title)

    assert errors == [], f"{title} 不应被阻断：{errors}"


@pytest.mark.parametrize(
    ("title", "keyword"),
    [
        ("加固回复输出、重启生命周期与并发更新", "约定式提交"),  # 缺 type
        ("fix 加固回复输出", "约定式提交"),  # 缺冒号
        ("Fix(reply): 修复输出前缀", "约定式提交"),  # type 必须小写
        ("update: 修东西", "约定式提交"),  # type 不在允许集合
        ("fix: 加固回复输出 (#49)", "(#NN)"),
        ("fix: 加固回复输出。", "句号"),
        ("chore: 更新", "信息量"),
        ("fix: 修复问题", "信息量"),
        ("feat: a" * 60, "显示宽度"),
        # 「主题 —— 明细」清单写法：明细应下沉 body
        ("feat: 降低上手门槛 —— 出厂模型库改为空 + 面板接入模型教程 + 懒人安装包", "清单"),
        ("fix: 取消误发 + 软重启无法恢复", "清单"),
    ],
)
def test_rejects_bad_titles(title: str, keyword: str) -> None:
    errors, _warnings = CHECKER.validate(title)

    assert any(keyword in message for message in errors), f"{title} 应报 {keyword}，实际：{errors}"


def test_empty_title_is_rejected() -> None:
    errors, _warnings = CHECKER.validate("   ")

    assert errors == ["标题为空"]


def test_parallel_items_only_warn() -> None:
    """多处并列只给警告：机械正则分不清「领域并列」和「改动清单」。"""
    errors, warnings = CHECKER.validate("fix: cancel 误发 / 好感度接口缺失 / 软重启无法恢复")

    assert errors == []
    assert warnings, "多处并列应给出警告"


def test_breaking_change_warns_about_migration() -> None:
    errors, warnings = CHECKER.validate("feat(api)!: 重做插件接口")

    assert errors == []
    assert any("迁移" in message for message in warnings)


def test_main_reads_title_from_env(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("PR_TITLE", "加固回复输出")

    assert CHECKER.main([]) == 1
    assert "::error::" in capsys.readouterr().out


def test_main_accepts_and_prints(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PR_TITLE", "fix(reply): 修复输出前缀与思考泄漏")

    assert CHECKER.main([]) == 0
    assert "标题校验通过" in capsys.readouterr().out


def test_strict_turns_warning_into_failure(monkeypatch) -> None:
    monkeypatch.setenv("PR_TITLE", "fix: 修复取消误发 / 好感度接口缺失 / 软重启无法恢复")

    assert CHECKER.main([]) == 0
    assert CHECKER.main(["--strict"]) == 1


def test_non_imperative_opener_warns() -> None:
    """约定式提交要求祈使语气（动词开头）；「让…」这类迂回说法只警告，不阻断。"""
    errors, warnings = CHECKER.validate("chore: 让 PR 规范匹配新的 squash 设置")

    assert errors == []
    assert any("动词开头" in message for message in warnings)


def test_verb_opener_does_not_warn() -> None:
    errors, warnings = CHECKER.validate("chore: 重订 PR 规范以匹配新的 squash 设置")

    assert errors == []
    assert warnings == []


def test_ci_workflow_runs_this_check() -> None:
    """护栏：CI 必须真的调用这个脚本，否则规范只是文档。"""
    workflow = ROOT / ".github" / "workflows" / "pr-title.yml"
    text = workflow.read_text(encoding="utf-8")

    assert "scripts/check_pr_title.py" in text
    assert "pull_request" in text

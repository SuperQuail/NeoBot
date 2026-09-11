"""仓库不得包含任何真实密钥：直接复用 scripts/check_secrets.py 的扫描逻辑。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def _load_scanner():
    spec = importlib.util.spec_from_file_location(
        "neobot_check_secrets", ROOT / "scripts" / "check_secrets.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tracked_files_contain_no_secrets(monkeypatch) -> None:
    """受 Git 跟踪的文件里不允许出现疑似密钥（占位符请写入 .secretsignore）。"""
    monkeypatch.chdir(ROOT)
    scanner = _load_scanner()

    findings = scanner.scan_files(scanner._iter_worktree_files())

    assert findings == [], "疑似密钥: " + "; ".join(
        f"{path}:{line} {label} {masked}" for path, line, label, masked in findings
    )


def test_scanner_ignores_key_shaped_suffix_of_longer_token(tmp_path) -> None:
    """压缩产物里的长标识符（如 Tailwind 的 mask-image-*）不应被当成密钥。"""
    scanner = _load_scanner()
    sample = tmp_path / "bundle.js"
    sample.write_text(
        'mask-image-linear-from-pos:[1],mask-image-radial-to-color:[2]',
        encoding="utf-8",
    )

    assert scanner.scan_files([str(sample)]) == []


def test_scanner_detects_realistic_key(tmp_path) -> None:
    """扫描器本身必须能识别真实形态的密钥（防止规则被误改成永远通过）。"""
    scanner = _load_scanner()
    sample = tmp_path / "leak.py"
    # 拼接写入，避免本文件自身出现真实形态的密钥字面量
    fake_key = "sk-" + "Ab3dEf6hIj9lMn2pQr5tUv8xYz0w"
    sample.write_text('API_KEY = "' + fake_key + '"\n', encoding="utf-8")

    findings = scanner.scan_files([str(sample)])

    assert findings and findings[0][2] == "OpenAI/兼容平台 Key"

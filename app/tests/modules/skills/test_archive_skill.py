"""ArchiveSkill 测试 — 压缩/解压（zip-slip 防护、格式判定、路径校验）。"""

from __future__ import annotations

import json
import tarfile
import zipfile

from neobot_app.skills.archive_skill import ArchiveSkill


def _parse(text: str) -> dict:
    return json.loads(text)


def _make_skill(sandbox) -> ArchiveSkill:
    return ArchiveSkill(sandbox_service=sandbox)


# ── 压缩 ──


async def test_compress_zip_roundtrip(make_sandbox):
    """正常路径：zip 压缩应产出归档文件并统计文件数与大小。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("a.txt"), b"hello")
    await sandbox.write_file(sandbox.resolve_path("b.txt"), b"world")

    result = _parse(await skill.execute("archive_compress", {"paths": ["a.txt", "b.txt"], "output": "out.zip"}))

    assert result["ok"] is True
    assert result["format"] == "zip"
    assert result["file_count"] == 2
    assert result["uncompressed_size"] == 10
    assert sandbox.resolve_path("out.zip").is_file()


async def test_compress_directory_walks_files(make_sandbox):
    """正常路径：压缩目录应递归包含目录内所有文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("docs/a.md"), b"# a")
    await sandbox.write_file(sandbox.resolve_path("docs/sub/b.md"), b"# b")

    result = _parse(await skill.execute("archive_compress", {"paths": ["docs"], "output": "docs.tar.gz"}))

    assert result["ok"] is True
    assert result["file_count"] == 2
    assert sandbox.resolve_path("docs.tar.gz").is_file()


async def test_compress_missing_source_rejected(make_sandbox):
    """异常路径：压缩路径不存在时应返回路径不存在错误。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("archive_compress", {"paths": ["nope.txt"], "output": "x.zip"}))

    assert result["ok"] is False
    assert "路径不存在" in result["error"]


async def test_compress_empty_paths_rejected(make_sandbox):
    """异常路径：paths 为空时应拒绝压缩。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("archive_compress", {"paths": [], "output": "x.zip"}))

    assert result["ok"] is False
    assert "paths 不能为空" in result["error"]


async def test_compress_unsupported_format_rejected(make_sandbox):
    """异常路径：output 后缀不支持时应返回格式错误。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("a.txt"), b"x")

    result = _parse(await skill.execute("archive_compress", {"paths": ["a.txt"], "output": "out.rar"}))

    assert result["ok"] is False
    assert "不支持的压缩格式" in result["error"]


# ── 解压：正常路径 ──


async def test_decompress_zip_extracts_files(make_sandbox):
    """正常路径：解压 zip 应把成员提取到目标目录并统计文件数。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    archive = sandbox.resolve_path("pack.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("hello.txt", "hi")
        zf.writestr("sub/inner.txt", "nested")

    result = _parse(await skill.execute("archive_decompress", {"archive": "pack.zip", "dest": "extract"}))

    assert result["ok"] is True
    assert result["file_count"] == 2
    dest = sandbox.resolve_path("extract")
    assert (dest / "hello.txt").read_text() == "hi"
    assert (dest / "sub" / "inner.txt").read_text() == "nested"


async def test_decompress_defaults_to_archive_parent(make_sandbox):
    """正常路径：不传 dest 时默认解压到归档文件所在目录。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    archive = sandbox.resolve_path("pack.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("hello.txt", "hi")

    result = _parse(await skill.execute("archive_decompress", {"archive": "pack.zip"}))

    assert result["ok"] is True
    assert (sandbox.resolve_path("hello.txt")).read_text() == "hi"


async def test_decompress_tar_gz_roundtrip(make_sandbox):
    """正常路径：解压 tar.gz 应正确提取成员。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    archive = sandbox.resolve_path("pack.tar.gz")
    with tarfile.open(str(archive), "w:gz") as tf:
        data = b"tar content"
        info = tarfile.TarInfo("inner.txt")
        info.size = len(data)
        tf.addfile(info, __import__("io").BytesIO(data))

    result = _parse(await skill.execute("archive_decompress", {"archive": "pack.tar.gz", "dest": "out"}))

    assert result["ok"] is True
    assert result["file_count"] == 1
    assert (sandbox.resolve_path("out/inner.txt")).read_bytes() == b"tar content"


async def test_decompress_empty_zip_ok(make_sandbox):
    """边界：解压空 zip 应返回 ok 且文件数为 0。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    archive = sandbox.resolve_path("empty.zip")
    with zipfile.ZipFile(str(archive), "w"):
        pass

    result = _parse(await skill.execute("archive_decompress", {"archive": "empty.zip", "dest": "out"}))

    assert result["ok"] is True
    assert result["file_count"] == 0
    assert result["uncompressed_size"] == 0


# ── 解压：zip-slip 防护 ──


async def test_decompress_zip_slip_member_rejected(make_sandbox):
    """异常路径：zip 成员 '../evil.txt' 试图逃出目标目录时必须整体拒绝且不产生越界文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    archive = sandbox.resolve_path("evil.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("../evil.txt", "pwned")

    result = _parse(await skill.execute("archive_decompress", {"archive": "evil.zip", "dest": "out"}))

    assert result["ok"] is False
    assert "安全拒绝" in result["error"]
    assert "../evil.txt" in result["error"]
    assert not (sandbox.resolve_path("").parent / "evil.txt").exists()
    assert not (sandbox.resolve_path("out").parent / "evil.txt").exists()


async def test_decompress_zip_deep_slip_member_rejected(make_sandbox):
    """异常路径：zip 成员 'a/../../evil.txt' 深层逃逸也必须被拒绝。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    archive = sandbox.resolve_path("evil2.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("a/../../evil.txt", "pwned")

    result = _parse(await skill.execute("archive_decompress", {"archive": "evil2.zip", "dest": "out"}))

    assert result["ok"] is False
    assert "安全拒绝" in result["error"]
    assert not (sandbox.resolve_path("").parent / "evil.txt").exists()


async def test_decompress_zip_mixed_good_and_slip_nothing_extracted(make_sandbox):
    """异常路径：归档同时含正常与逃逸成员时不得部分解压任何文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    archive = sandbox.resolve_path("mixed.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("good.txt", "ok")
        zf.writestr("../evil.txt", "pwned")

    result = _parse(await skill.execute("archive_decompress", {"archive": "mixed.zip", "dest": "out"}))

    assert result["ok"] is False
    assert not (sandbox.resolve_path("out/good.txt")).exists()
    assert not (sandbox.resolve_path("").parent / "evil.txt").exists()


async def test_decompress_tar_slip_member_rejected(make_sandbox):
    """异常路径：tar 成员 '../evil.txt' 逃逸目标目录时同样必须被拒绝。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    archive = sandbox.resolve_path("evil.tar")
    with tarfile.open(str(archive), "w") as tf:
        info = tarfile.TarInfo("../evil.txt")
        info.size = 3
        tf.addfile(info, __import__("io").BytesIO(b"bad"))

    result = _parse(await skill.execute("archive_decompress", {"archive": "evil.tar", "dest": "out"}))

    assert result["ok"] is False
    assert "安全拒绝" in result["error"]
    assert not (sandbox.resolve_path("").parent / "evil.txt").exists()


# ── 解压：异常路径 ──


async def test_decompress_missing_archive_rejected(make_sandbox):
    """异常路径：归档文件不存在时应返回归档不存在错误。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("archive_decompress", {"archive": "nope.zip"}))

    assert result["ok"] is False
    assert "归档文件不存在" in result["error"]


async def test_decompress_missing_param_rejected(make_sandbox):
    """异常路径：缺少 archive 参数时应拒绝解压。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("archive_decompress", {}))

    assert result["ok"] is False
    assert "archive 不能为空" in result["error"]


async def test_decompress_unsupported_format_rejected(make_sandbox):
    """异常路径：归档后缀不支持时应返回格式错误。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("x.7z"), b"data")

    result = _parse(await skill.execute("archive_decompress", {"archive": "x.7z"}))

    assert result["ok"] is False
    assert "不支持的归档格式" in result["error"]


async def test_unknown_tool_returns_error(make_sandbox):
    """异常路径：未知工具名应返回明确错误。"""
    skill = _make_skill(make_sandbox())

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown archive tool" in result["error"]

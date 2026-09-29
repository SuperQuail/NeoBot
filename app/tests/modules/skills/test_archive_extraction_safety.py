"""ArchiveSkill 解压安全 — 链接/设备成员与路径逃逸（P0，fix(12) §4.1）。

历史缺陷：tar 分支只比对**成员名**（字符串前缀 startswith），从不读 linkname，
也不拒绝 symlink/hardlink/device 成员，extractall 走 CPython 默认 fully_trusted；
一个「symlink 成员 + 穿过该链接的文件成员」即可把文件写到 dest 与沙箱之外。
同一处字符串前缀比较还能被「dest 的兄弟目录名以 dest 名为前缀」绕过
（dest=uploads 时成员 ../uploads_evil/a.txt）。

本文件覆盖：tar 的 symlink / hardlink / device / fifo / ../ / 绝对路径 / 链接目标越界，
以及正常归档（中文名、多层目录、大文件）行为不变的护栏。
"""

from __future__ import annotations

import io
import json
import os
import tarfile
import zipfile

import pytest

from neobot_app.skills.archive_skill import ArchiveSkill


def _parse(text: str) -> dict:
    return json.loads(text)


def _skill(sandbox) -> ArchiveSkill:
    return ArchiveSkill(sandbox_service=sandbox)


def _add_file(tf: tarfile.TarFile, name: str, data: bytes = b"pwned") -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))


def _add_symlink(tf: tarfile.TarFile, name: str, linkname: str) -> None:
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = linkname
    tf.addfile(info)


def _add_hardlink(tf: tarfile.TarFile, name: str, linkname: str) -> None:
    info = tarfile.TarInfo(name)
    info.type = tarfile.LNKTYPE
    info.linkname = linkname
    tf.addfile(info)


def _assert_rejected(result: dict) -> None:
    assert result["ok"] is False, result
    assert "安全拒绝" in result["error"], result


# ── tar：链接成员逃逸 ──────────────────────────────────────────────


async def test_tar_symlink_member_escape_rejected(make_sandbox) -> None:
    """symlink 成员指向 dest 兄弟目录 + 穿过链接的文件成员：必须整体拒绝。

    修复前：检查循环只看 m.name（两个成员都「在 dest 内」），extractall 先建链接
    再穿链接写文件 → escaped/pwn.txt 落在 dest 之外。
    """
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    escaped = root / "escaped"
    archive = sandbox.resolve_path("evil.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_symlink(tf, "esc", str(escaped))
        _add_file(tf, "esc/pwn.txt")

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "evil.tar", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (escaped / "pwn.txt").exists()
    assert not (sandbox.resolve_path("out/esc")).is_symlink()


async def test_tar_symlink_relative_escape_rejected(make_sandbox) -> None:
    """symlink 成员用相对 linkname（../../..）逃出 dest：必须拒绝。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    archive = sandbox.resolve_path("evil_rel.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_symlink(tf, "esc", "../../escaped_rel")
        _add_file(tf, "esc/pwn.txt")

    result = _parse(
        await skill.execute(
            "archive_decompress", {"archive": "evil_rel.tar", "dest": "deep/out"}
        )
    )

    _assert_rejected(result)
    assert not (root.parent / "escaped_rel" / "pwn.txt").exists()


async def test_tar_hardlink_member_rejected(make_sandbox) -> None:
    """hardlink 成员（linkname 指向 dest 外）必须拒绝：修复前会走 os.link 报错/越界。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    outside = root.parent / "outside_target.txt"
    outside.write_text("secret", encoding="utf-8")
    archive = sandbox.resolve_path("hard.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_hardlink(tf, "esc", str(outside))

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "hard.tar", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (sandbox.resolve_path("out/esc")).exists()


# ── tar：路径语义边界（dest 兄弟目录名前缀绕过） ─────────────────────


async def test_tar_sibling_prefix_escape_rejected(make_sandbox) -> None:
    """dest=uploads 时成员 ../uploads_evil/a.txt：修复前的 str.startswith 前缀比较会放行。

    修复前实测：成员路径 <root>/uploads_evil/a.txt 以 <root>/uploads 为字符串前缀，
    检查通过并真的写到兄弟目录 → 该用例在修复前失败且发生真实越界写。
    """
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    archive = sandbox.resolve_path("prefix.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_file(tf, "../uploads_evil/a.txt")

    result = _parse(
        await skill.execute(
            "archive_decompress", {"archive": "prefix.tar", "dest": "uploads"}
        )
    )

    _assert_rejected(result)
    assert not (root / "uploads_evil" / "a.txt").exists()
    assert not (root / "uploads_evil").exists()


async def test_tar_parent_traversal_member_rejected(make_sandbox) -> None:
    """成员名含 .. 一律拒绝（回归护栏：修复前也拒绝）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    archive = sandbox.resolve_path("up.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_file(tf, "../evil.txt")

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "up.tar", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (root / "evil.txt").exists()


async def test_tar_absolute_member_rejected(make_sandbox) -> None:
    """成员名是绝对路径时拒绝，且目标位置不得出现文件（回归护栏）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    outside = sandbox.resolve_path("").parent / "abs_pwn.txt"
    archive = sandbox.resolve_path("abs.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_file(tf, str(outside))

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "abs.tar", "dest": "out"})
    )

    _assert_rejected(result)
    assert not outside.exists()


async def test_tar_backslash_traversal_member_rejected(make_sandbox) -> None:
    """反斜杠形式的 ..\\ 成员同样拒绝（回归护栏，Windows 语义）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    archive = sandbox.resolve_path("bs.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_file(tf, "..\\evil_bs.txt")

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "bs.tar", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (root / "evil_bs.txt").exists()


# ── tar：设备 / FIFO 成员 ───────────────────────────────────────────


async def test_tar_device_member_rejected(make_sandbox) -> None:
    """字符设备成员必须拒绝：修复前会走到 os.mknod（Windows 上直接 AttributeError）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    archive = sandbox.resolve_path("dev.tar")
    with tarfile.open(str(archive), "w") as tf:
        info = tarfile.TarInfo("dev/null")
        info.type = tarfile.CHRTYPE
        info.devmajor = 1
        info.devminor = 3
        tf.addfile(info)

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "dev.tar", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (sandbox.resolve_path("out/dev")).exists()


async def test_tar_fifo_member_rejected(make_sandbox) -> None:
    """FIFO 成员必须拒绝（修复前 os.mkfifo 在 Windows 上不存在）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    archive = sandbox.resolve_path("fifo.tar")
    with tarfile.open(str(archive), "w") as tf:
        info = tarfile.TarInfo("pipe")
        info.type = tarfile.FIFOTYPE
        tf.addfile(info)

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "fifo.tar", "dest": "out"})
    )

    _assert_rejected(result)


# ── tar：拒绝时不得部分解压 ─────────────────────────────────────────


async def test_tar_rejected_archive_extracts_nothing(make_sandbox) -> None:
    """同时含正常成员与逃逸成员时，必须整体拒绝且一个文件都不落盘。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    archive = sandbox.resolve_path("mixed.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_file(tf, "good.txt", b"ok")
        _add_symlink(tf, "esc", str(sandbox.resolve_path("").parent / "escaped_mixed"))

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "mixed.tar", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (sandbox.resolve_path("out/good.txt")).exists()


# ── 正常归档：行为不变的护栏 ────────────────────────────────────────


async def test_tar_gz_normal_archive_still_extracts(make_sandbox) -> None:
    """中文名 + 多层目录 + 大文件：修复后仍应正常解压（filter=data 不得误伤）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    archive = sandbox.resolve_path("normal.tar.gz")
    big = b"x" * (1024 * 1024)
    with tarfile.open(str(archive), "w:gz") as tf:
        dir_info = tarfile.TarInfo("资料")
        dir_info.type = tarfile.DIRTYPE
        dir_info.mode = 0o755
        tf.addfile(dir_info)
        _add_file(tf, "资料/说明.txt", "中文内容".encode("utf-8"))
        _add_file(tf, "资料/子目录/大文件.bin", big)

    result = _parse(
        await skill.execute(
            "archive_decompress", {"archive": "normal.tar.gz", "dest": "out"}
        )
    )

    assert result["ok"] is True, result
    assert result["file_count"] == 2
    assert result["uncompressed_size"] == len("中文内容".encode("utf-8")) + len(big)
    assert (sandbox.resolve_path("out/资料/说明.txt")).read_text(encoding="utf-8") == "中文内容"
    assert (sandbox.resolve_path("out/资料/子目录/大文件.bin")).stat().st_size == len(big)


async def test_tar_gz_compress_then_decompress_roundtrip(make_sandbox) -> None:
    """自家压缩→解压链路必须保持可用（端到端护栏）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("src/一.txt"), b"one")
    await sandbox.write_file(sandbox.resolve_path("src/sub/二.txt"), b"two")

    packed = _parse(
        await skill.execute(
            "archive_compress", {"paths": ["src"], "output": "round.tar.gz"}
        )
    )
    assert packed["ok"] is True, packed

    result = _parse(
        await skill.execute(
            "archive_decompress", {"archive": "round.tar.gz", "dest": "unpacked"}
        )
    )

    assert result["ok"] is True, result
    assert (sandbox.resolve_path("unpacked/src/一.txt")).read_bytes() == b"one"
    assert (sandbox.resolve_path("unpacked/src/sub/二.txt")).read_bytes() == b"two"


async def test_tar_member_through_preexisting_symlink_rejected(make_sandbox) -> None:
    """dest 内**预先存在**的 symlink 指向 dest 外时，穿过它的成员必须拒绝。

    回归护栏：修复前的 Path.resolve() 也会跟随既有链接，因此同样拒绝；
    这条用于锁死「路径语义比较」不被改回字符串比较。无 symlink 权限则跳过。
    """
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    outside = root.parent / "prelink_target"
    outside.mkdir(parents=True, exist_ok=True)
    link = sandbox.resolve_path("out/link")
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")
    archive = sandbox.resolve_path("prelink.tar")
    with tarfile.open(str(archive), "w") as tf:
        _add_file(tf, "link/pwn.txt")

    result = _parse(
        await skill.execute(
            "archive_decompress", {"archive": "prelink.tar", "dest": "out"}
        )
    )

    _assert_rejected(result)
    assert not (outside / "pwn.txt").exists()


async def test_tar_missing_archive_still_reported(make_sandbox) -> None:
    """异常路径回归：归档不存在时仍返回「归档文件不存在」，不受新校验影响。"""
    skill = _skill(make_sandbox())

    result = _parse(await skill.execute("archive_decompress", {"archive": "nope.tar"}))

    assert result["ok"] is False
    assert "归档文件不存在" in result["error"]

# ── zip：字符串前缀绕过 / 符号链接成员 / 路径语义 ────────────────────


async def test_zip_sibling_prefix_escape_rejected(make_sandbox) -> None:
    """dest=uploads 时成员 ../uploads_evil/a.txt：字符串前缀比较必须换成路径语义。

    修复前 (dest / "../uploads_evil/a.txt").resolve() 的字符串以 dest 为前缀，
    startswith 检查放行（zipfile 事后会把 .. 剥掉，所以不真逃逸，但检查形同虚设；
    同一个比较函数在 tar 分支就是真实的越界写）。
    """
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    archive = sandbox.resolve_path("zprefix.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("../uploads_evil/a.txt", "pwned")

    result = _parse(
        await skill.execute(
            "archive_decompress", {"archive": "zprefix.zip", "dest": "uploads"}
        )
    )

    _assert_rejected(result)
    assert not (root / "uploads_evil").exists()
    assert not (sandbox.resolve_path("uploads/uploads_evil/a.txt")).exists()


async def test_zip_symlink_member_rejected(make_sandbox) -> None:
    """zip 成员声明为符号链接（外部属性 S_IFLNK）必须拒绝，不得原样落盘。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    outside = sandbox.resolve_path("").parent / "zip_escape"
    archive = sandbox.resolve_path("zsym.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        info = zipfile.ZipInfo("esc")
        info.external_attr = 0o120777 << 16
        zf.writestr(info, str(outside))
        zf.writestr("esc/pwn.txt", "pwned")

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "zsym.zip", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (sandbox.resolve_path("out/esc")).is_symlink()
    assert not (outside / "pwn.txt").exists()


async def test_zip_parent_traversal_member_rejected(make_sandbox) -> None:
    """zip 成员 ../evil.txt 拒绝（回归护栏：修复前也拒绝）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    archive = sandbox.resolve_path("zup.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("../evil.txt", "pwned")

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "zup.zip", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (root / "evil.txt").exists()


async def test_zip_backslash_traversal_member_rejected(make_sandbox) -> None:
    """反斜杠形式的 ..\\ 成员拒绝：Windows 上 zipfile 会把它当路径分隔符。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    root = sandbox.resolve_path("")
    archive = sandbox.resolve_path("zbs.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("..\\evil_zip_bs.txt", "pwned")

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "zbs.zip", "dest": "out"})
    )

    _assert_rejected(result)
    assert not (root / "evil_zip_bs.txt").exists()


async def test_zip_absolute_member_rejected(make_sandbox) -> None:
    """zip 成员是绝对路径时拒绝，目标位置不得出现文件（回归护栏）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    outside = sandbox.resolve_path("").parent / "zip_abs_pwn.txt"
    archive = sandbox.resolve_path("zabs.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr(str(outside), "pwned")

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "zabs.zip", "dest": "out"})
    )

    _assert_rejected(result)
    assert not outside.exists()


async def test_zip_normal_archive_still_extracts(make_sandbox) -> None:
    """中文名 + 多层目录：zip 分支修复后仍应正常解压。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    archive = sandbox.resolve_path("normal.zip")
    with zipfile.ZipFile(str(archive), "w") as zf:
        zf.writestr("资料/说明.txt", "中文内容")
        zf.writestr("资料/子目录/更多.txt", "更多内容")

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "normal.zip", "dest": "out"})
    )

    assert result["ok"] is True, result
    assert result["file_count"] == 2
    assert (sandbox.resolve_path("out/资料/说明.txt")).read_text(encoding="utf-8") == "中文内容"
    assert (
        sandbox.resolve_path("out/资料/子目录/更多.txt")
    ).read_text(encoding="utf-8") == "更多内容"


async def test_zip_compress_then_decompress_roundtrip(make_sandbox) -> None:
    """自家 zip 压缩→解压链路保持可用（端到端护栏）。"""
    sandbox = make_sandbox()
    skill = _skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("src/一.txt"), b"one")
    await sandbox.write_file(sandbox.resolve_path("src/sub/二.txt"), b"two")

    packed = _parse(
        await skill.execute("archive_compress", {"paths": ["src"], "output": "round.zip"})
    )
    assert packed["ok"] is True, packed

    result = _parse(
        await skill.execute("archive_decompress", {"archive": "round.zip", "dest": "unpacked"})
    )

    assert result["ok"] is True, result
    assert (sandbox.resolve_path("unpacked/src/一.txt")).read_bytes() == b"one"
    assert (sandbox.resolve_path("unpacked/src/sub/二.txt")).read_bytes() == b"two"



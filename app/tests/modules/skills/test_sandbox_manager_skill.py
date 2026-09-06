"""SandboxManagerSkill 测试 — 沙箱文件操作（download_file SSRF/大小/重定向防护、读写编辑搜索、发送）。

依赖注入：FakeAdapter/FakeFileServer/FakeHttpxClient 仅记录调用，不触碰真实网络。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from neobot_app.skills.sandbox_manager_skill import (
    MAX_DOWNLOAD_BYTES,
    MAX_DOWNLOAD_REDIRECTS,
    SandboxManagerSkill,
    _read_download_limited,
)

PUBLIC_URL = "http://1.1.1.1/file.bin"


class FakeAdapter:
    """记录 send 调用的假适配器，响应可由调用方指定。"""

    def __init__(self, response: Any = None) -> None:
        self.calls: list[tuple[Any, Any]] = []
        self._response = response if response is not None else SimpleNamespace(status="ok", retcode=0)

    async def send(self, conv_ref, segments) -> Any:
        self.calls.append((conv_ref, segments))
        return self._response


class FakeFileServer:
    """仅暴露 _enabled 与 register_file 的假文件服务器（本地路径模式）。"""

    _enabled = False

    def register_file(self, path: Path) -> str:
        return f"file:///{path.as_posix()}"


class FakeHttpxResponse:
    """假 HTTP 响应：可配置状态码/头/分块内容。"""

    def __init__(self, status_code: int = 200, headers: dict | None = None, chunks: list[bytes] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks if chunks is not None else [b"hello"]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("status error", request=None, response=None)

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c


class FakeHttpxClient:
    """假 httpx.AsyncClient：记录 timeout，get 返回脚本化响应序列。"""

    def __init__(self, *args, responses=None, **kwargs) -> None:
        self.timeout = kwargs.get("timeout")
        self.follow_redirects = kwargs.get("follow_redirects")
        self.get_calls: list[str] = []
        self._responses = list(responses) if responses else [FakeHttpxResponse()]
        self._index = 0

    async def __aenter__(self) -> "FakeHttpxClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, url: str) -> FakeHttpxResponse:
        self.get_calls.append(url)
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        return FakeHttpxResponse()


def _json_result(text: str) -> dict:
    return json.loads(text)


def _make_skill(sandbox, adapter: FakeAdapter | None = None, file_server: FakeFileServer | None = None) -> SandboxManagerSkill:
    return SandboxManagerSkill(
        sandbox_service=sandbox,
        adapter=adapter,
        file_server=file_server,
    )


@pytest.fixture()
def fake_http(monkeypatch):
    """将 httpx.AsyncClient 替换为假客户端；scripts[0] 可预置响应脚本。"""

    instances: list[FakeHttpxClient] = []
    scripts: dict[int, list[FakeHttpxResponse]] = {}

    class _Factory(FakeHttpxClient):
        def __init__(self, *args, **kwargs):
            script = scripts.pop(0, None)
            super().__init__(*args, responses=script, **kwargs)
            instances.append(self)

    monkeypatch.setattr(httpx, "AsyncClient", _Factory)
    return SimpleNamespace(instances=instances, scripts=scripts)


# ── download_file：SSRF / 协议 / 参数校验 ──


async def test_download_rejects_internal_ip(make_sandbox):
    """异常路径：download_file 指向 127.0.0.1 内网地址时必须在发起请求前被拒绝。"""
    skill = _make_skill(make_sandbox())

    result = _json_result(await skill.execute("download_file", {
        "url": "http://127.0.0.1/secret", "save_name": "a.bin", "chat_flow_id": "group:1",
    }))

    assert result["ok"] is False
    assert "禁止下载内网/非公网地址" in result["error"]


async def test_download_rejects_private_ranges(make_sandbox):
    """异常路径：10/172.16/192.168 私有网段与回环地址均不得下载。"""
    skill = _make_skill(make_sandbox())

    for url in ("http://10.0.0.1/x", "http://172.16.0.1/x", "http://192.168.1.1/x", "http://[::1]/x"):
        result = _json_result(await skill.execute("download_file", {
            "url": url, "save_name": "a.bin", "chat_flow_id": "group:1",
        }))

        assert result["ok"] is False, url
        assert "禁止下载内网/非公网地址" in result["error"]


async def test_download_rejects_encoded_ip(make_sandbox):
    """异常路径：十进制/十六进制编码的 127.0.0.1（如 2130706433）必须被识别为内网拒绝。"""
    skill = _make_skill(make_sandbox())

    for url in ("http://2130706433/x", "http://0x7f000001/x", "http://0177.0.0.1/x"):
        result = _json_result(await skill.execute("download_file", {
            "url": url, "save_name": "a.bin", "chat_flow_id": "group:1",
        }))

        assert result["ok"] is False, url
        assert "禁止下载内网/非公网地址" in result["error"]


async def test_download_rejects_non_http_scheme(make_sandbox):
    """异常路径：ftp/file 等非 http(s) 协议地址必须被拒绝下载。"""
    skill = _make_skill(make_sandbox())

    for url in ("ftp://1.1.1.1/x", "file:///etc/passwd", "gopher://1.1.1.1/x"):
        result = _json_result(await skill.execute("download_file", {
            "url": url, "save_name": "a.bin", "chat_flow_id": "group:1",
        }))

        assert result["ok"] is False, url
        assert "禁止下载内网/非公网地址" in result["error"]


async def test_download_missing_required_params(make_sandbox):
    """异常路径：缺少 url/save_name/chat_flow_id 任一参数时应返回缺少必要参数。"""
    skill = _make_skill(make_sandbox())

    for args in (
        {"url": PUBLIC_URL, "save_name": "a.bin"},
        {"url": PUBLIC_URL, "chat_flow_id": "group:1"},
        {"save_name": "a.bin", "chat_flow_id": "group:1"},
    ):
        result = _json_result(await skill.execute("download_file", args))

        assert result["ok"] is False
        assert "缺少必要参数" in result["error"]


# ── download_file：大小限制 / 重定向 / 容量 ──


async def test_download_clamps_timeout_to_bounds(make_sandbox, fake_http):
    """边界：timeout_seconds 超出 [1,1800] 时应收敛到上下限而非报错。"""
    skill = _make_skill(make_sandbox())

    await skill.execute("download_file", {
        "url": PUBLIC_URL, "save_name": "a.bin", "chat_flow_id": "g1", "timeout_seconds": 99999,
    })
    await skill.execute("download_file", {
        "url": PUBLIC_URL, "save_name": "b.bin", "chat_flow_id": "g1", "timeout_seconds": -5,
    })

    assert [c.timeout for c in fake_http.instances] == [1800.0, 1.0]


async def test_download_rejects_declared_size_over_limit(make_sandbox, fake_http):
    """异常路径：响应头 content-length 超过 100MB 上限时中止且不写文件。"""
    skill = _make_skill(make_sandbox())
    fake_http.scripts[0] = [FakeHttpxResponse(headers={"content-length": str(MAX_DOWNLOAD_BYTES + 1)})]

    result = _json_result(await skill.execute("download_file", {
        "url": PUBLIC_URL, "save_name": "big.bin", "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert "文件过大" in result["error"]


async def test_download_aborts_on_stream_over_limit():
    """异常路径：无 content-length 的流式响应累积超过上限时必须在累计时立即中止。"""
    response = FakeHttpxResponse(chunks=[b"x" * (MAX_DOWNLOAD_BYTES // 2 + 1)] * 3)

    with pytest.raises(ValueError, match="文件过大"):
        await _read_download_limited(response)


async def test_download_rejects_redirect_to_internal(make_sandbox, fake_http):
    """异常路径：302 重定向目标为内网地址时必须拒绝（每跳重新 SSRF 校验）。"""
    skill = _make_skill(make_sandbox())
    fake_http.scripts[0] = [FakeHttpxResponse(status_code=302, headers={"location": "http://127.0.0.1/evil"})]

    result = _json_result(await skill.execute("download_file", {
        "url": PUBLIC_URL, "save_name": "a.bin", "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert "重定向目标不允许下载" in result["error"]


async def test_download_aborts_on_redirect_loop(make_sandbox, fake_http):
    """边界：重定向次数超过 MAX_DOWNLOAD_REDIRECTS 时必须中止而非无限跟随。"""
    skill = _make_skill(make_sandbox())
    hops = []
    for i in range(MAX_DOWNLOAD_REDIRECTS + 2):
        hops.append(FakeHttpxResponse(status_code=302, headers={"location": f"http://1.1.1.{i + 1}/x"}))
    fake_http.scripts[0] = hops

    result = _json_result(await skill.execute("download_file", {
        "url": PUBLIC_URL, "save_name": "a.bin", "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert "重定向次数超过限制" in result["error"]


async def test_download_success_writes_into_flow_temp_dir(make_sandbox, fake_http):
    """正常路径：合法公网地址下载成功后文件应写入 chat_flow_id 对应临时目录。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    fake_http.scripts[0] = [FakeHttpxResponse(chunks=[b"payload-data"])]

    result = _json_result(await skill.execute("download_file", {
        "url": PUBLIC_URL, "save_name": "img.png", "chat_flow_id": "flow42",
    }))

    assert result["ok"] is True
    assert result["size"] == len(b"payload-data")
    saved = sandbox.get_temp_dir("flow42") / "img.png"
    assert saved.is_file()
    assert saved.read_bytes() == b"payload-data"


async def test_download_rejects_when_sandbox_capacity_exhausted(make_sandbox, fake_http):
    """异常路径：沙箱容量不足时下载必须被拒绝并提示当前/上限占用。"""
    sandbox = make_sandbox(max_total_size_bytes=16)
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("fill.txt", "g1"), b"f" * 16)
    fake_http.scripts[0] = [FakeHttpxResponse(chunks=[b"hello"])]

    result = _json_result(await skill.execute("download_file", {
        "url": PUBLIC_URL, "save_name": "a.bin", "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert "沙箱空间不足" in result["error"]


# ── read_file / write_file / write_file_base64 ──


async def test_read_file_returns_text_content(make_sandbox):
    """正常路径：读取文本文件应返回完整内容与字节数。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("notes.txt", "g1"), "你好，NeoBot".encode("utf-8"))

    result = _json_result(await skill.execute("read_file", {"path": "notes.txt", "chat_flow_id": "g1"}))

    assert result["ok"] is True
    assert result["content"] == "你好，NeoBot"
    assert result["size"] == len("你好，NeoBot".encode("utf-8"))


async def test_read_file_rejects_path_traversal(make_sandbox):
    """异常路径：path 含 '..' 越界时必须被拒绝且不读取沙箱外文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    victim = sandbox.resolve_path("").parent / "secret.txt"
    victim.write_text("top secret", encoding="utf-8")

    result = _json_result(await skill.execute("read_file", {"path": "../secret.txt"}))

    assert result["ok"] is False
    assert "secret" not in result.get("content", "")


async def test_read_file_image_returns_metadata_not_content(make_sandbox):
    """边界：读取 PNG 图片应返回图片元信息而非二进制/base64 内容。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("pic.png", "g1"), b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    result = _json_result(await skill.execute("read_file", {"path": "pic.png", "chat_flow_id": "g1"}))

    assert result["ok"] is True
    assert result["type"] == "image"
    assert result["format"] == "PNG"
    assert "content" not in result


async def test_read_file_empty_file_returns_empty(make_sandbox):
    """边界：读取空文件应返回 ok 且内容为空字符串。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("empty.txt", "g1"), b"")

    result = _json_result(await skill.execute("read_file", {"path": "empty.txt", "chat_flow_id": "g1"}))

    assert result["ok"] is True
    assert result["content"] == ""
    assert result["size"] == 0


async def test_write_file_ok_and_pipeline_key_fallback(make_sandbox):
    """正常路径：write_file 写入临时目录，chat_flow_id 缺省时可回退使用 pipeline_key。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    result = _json_result(await skill.execute("write_file", {
        "path": "out.md", "content": "# hello", "pipeline_key": "private7",
    }))

    assert result["ok"] is True
    saved = sandbox.get_temp_dir("private7") / "out.md"
    assert saved.read_text("utf-8") == "# hello"
    assert result["size"] == 7


async def test_write_file_rejects_missing_params_but_accepts_empty_content(make_sandbox):
    """缺 chat_flow_id 仍拒绝；共享文件工具允许显式空字符串创建空文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    no_flow = _json_result(await skill.execute("write_file", {"path": "a.txt", "content": "x"}))
    empty_content = _json_result(await skill.execute("write_file", {"path": "a.txt", "content": "", "chat_flow_id": "g1"}))

    assert no_flow["ok"] is False
    assert "缺少必要参数" in no_flow["error"]
    assert empty_content["ok"] is True
    assert empty_content["size"] == 0
    assert (sandbox.get_temp_dir("g1") / "a.txt").read_bytes() == b""


async def test_write_file_rejects_traversal(make_sandbox):
    """异常路径：write_file 的 path 越界到沙箱根之外（../../../evil.txt）时必须拒绝且不产生越界文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    result = _json_result(await skill.execute("write_file", {
        "path": "../../../evil.txt", "content": "evil", "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert not (sandbox.resolve_path("").parent / "evil.txt").exists()


async def test_write_file_base64_writes_binary(make_sandbox):
    """正常路径：write_file_base64 应解码 base64 后写入二进制文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    raw = b"\x00\x01\x02\xff"

    result = _json_result(await skill.execute("write_file_base64", {
        "path": "bin.dat", "content_base64": base64.b64encode(raw).decode(), "chat_flow_id": "g1",
    }))

    assert result["ok"] is True
    assert (sandbox.get_temp_dir("g1") / "bin.dat").read_bytes() == raw
    assert result["size"] == 4


# ── edit_file / glob / grep / list ──


async def test_edit_file_replaces_unique_string(make_sandbox):
    """正常路径：edit_file 对唯一 old_string 应原地替换并报告替换次数。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("a.py", "g1"), "x = 1\nprint(x)\n".encode("utf-8"))

    result = _json_result(await skill.execute("edit_file", {
        "path": "a.py", "old_string": "x = 1", "new_string": "x = 2", "chat_flow_id": "g1",
    }))

    assert result["ok"] is True
    assert result["replacements"] == 1
    content = (sandbox.get_temp_dir("g1") / "a.py").read_text("utf-8")
    assert "x = 2" in content
    assert "x = 1" not in content


async def test_edit_file_requires_unique_match(make_sandbox):
    """异常路径：old_string 出现多次且未指定 replace_all 时不得修改文件。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("a.txt", "g1"), "same\nsame\n".encode("utf-8"))

    result = _json_result(await skill.execute("edit_file", {
        "path": "a.txt", "old_string": "same", "new_string": "other", "chat_flow_id": "g1",
    }))
    with_replace_all = _json_result(await skill.execute("edit_file", {
        "path": "a.txt", "old_string": "same", "new_string": "other", "replace_all": True, "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert "不唯一" in result["error"]
    assert with_replace_all["ok"] is True
    assert with_replace_all["replacements"] == 2


async def test_edit_file_no_match_rejected(make_sandbox):
    """异常路径：old_string 不存在时应报未找到且不落盘。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("a.txt", "g1"), "hello".encode("utf-8"))

    result = _json_result(await skill.execute("edit_file", {
        "path": "a.txt", "old_string": "nope", "new_string": "x", "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert "未找到匹配" in result["error"]


async def test_glob_files_recursive_match(make_sandbox):
    """正常路径：glob_files 应递归匹配模式并返回相对路径（统一 / 分隔）与大小。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("app/main.py", "g1"), "print(1)".encode("utf-8"))
    await sandbox.write_file(sandbox.resolve_path("app/util.py", "g1"), "print(2)".encode("utf-8"))
    await sandbox.write_file(sandbox.resolve_path("README.md", "g1"), "# t".encode("utf-8"))

    result = _json_result(await skill.execute("glob_files", {"pattern": "**/*.py", "chat_flow_id": "g1"}))

    assert result["ok"] is True
    paths = {m["path"].replace("\\", "/") for m in result["matches"]}
    assert paths == {"app/main.py", "app/util.py"}
    assert result["count"] == 2


async def test_grep_files_content_mode_and_case_insensitive(make_sandbox):
    """正常路径：grep_files 支持 content 输出模式与大小写不敏感搜索。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("a.py", "g1"), "def Foo():\n    pass\n".encode("utf-8"))

    result = _json_result(await skill.execute("grep_files", {
        "pattern": "def foo", "output_mode": "content", "-i": True, "chat_flow_id": "g1",
    }))

    assert result["ok"] is True
    assert result["total_matches"] == 1
    assert result["results"][0]["file"] == "a.py"
    assert result["results"][0]["line"] == 1
    assert result["results"][0]["text"] == "def Foo():"


async def test_grep_files_invalid_regex_rejected(make_sandbox):
    """异常路径：非法正则表达式应返回正则无效错误而非抛出异常。"""
    skill = _make_skill(make_sandbox())

    result = _json_result(await skill.execute("grep_files", {"pattern": "("}))

    assert result["ok"] is False
    assert "正则表达式无效" in result["error"]


async def test_list_files_with_pattern_filter(make_sandbox):
    """正常路径：list_files 支持 pattern 过滤，返回条目包含名称与大小。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("a.txt", "g1"), "a".encode("utf-8"))
    await sandbox.write_file(sandbox.resolve_path("b.log", "g1"), "b".encode("utf-8"))

    result = _json_result(await skill.execute("list_files", {"path": ".", "pattern": "*.txt", "chat_flow_id": "g1"}))

    assert result["ok"] is True
    assert [f["name"] for f in result["files"]] == ["a.txt"]


# ── delete / move / copy / send / hold_temp ──


async def test_delete_move_copy_roundtrip(make_sandbox):
    """正常路径：delete_file/move_file/copy_file 应完成对应文件操作并受路径边界约束。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("src.txt", "g1"), "data".encode("utf-8"))

    moved = _json_result(await skill.execute("move_file", {
        "source": "src.txt", "destination": "dst.txt", "chat_flow_id": "g1",
    }))
    assert moved["ok"] is True
    assert (sandbox.get_temp_dir("g1") / "dst.txt").is_file()
    assert not (sandbox.get_temp_dir("g1") / "src.txt").exists()

    copied = _json_result(await skill.execute("copy_file", {
        "source": "dst.txt", "destination": "copy.txt", "chat_flow_id": "g1",
    }))
    assert copied["ok"] is True
    assert (sandbox.get_temp_dir("g1") / "copy.txt").is_file()

    deleted = _json_result(await skill.execute("delete_file", {"path": "dst.txt", "chat_flow_id": "g1"}))
    assert deleted["ok"] is True
    assert not (sandbox.get_temp_dir("g1") / "dst.txt").exists()


async def test_move_file_outside_sandbox_rejected(make_sandbox):
    """异常路径：move_file 目标越界到沙箱根之外（../../../escape.txt）时应拒绝移动。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)
    await sandbox.write_file(sandbox.resolve_path("src.txt", "g1"), "data".encode("utf-8"))

    result = _json_result(await skill.execute("move_file", {
        "source": "src.txt", "destination": "../../../escape.txt", "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert not (sandbox.resolve_path("").parent / "escape.txt").exists()


async def test_send_file_to_group_success(make_sandbox):
    """正常路径：send_file 应向 adapter 发送图片段并携带群会话引用。"""
    sandbox = make_sandbox()
    adapter = FakeAdapter()
    skill = _make_skill(sandbox, adapter=adapter, file_server=FakeFileServer())
    await sandbox.write_file(sandbox.resolve_path("pic.png", "g1"), b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    result = _json_result(await skill.execute("send_file", {
        "path": "pic.png", "group_id": "888", "chat_flow_id": "g1",
    }))

    assert result["ok"] is True
    assert len(adapter.calls) == 1
    conv_ref, segments = adapter.calls[0]
    assert conv_ref.kind == "group"
    assert conv_ref.id == "888"
    assert segments[0]["type"] == "image"


async def test_send_file_missing_target_rejected(make_sandbox):
    """异常路径：send_file 未提供 group_id 与 user_id 时应拒绝发送。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox, adapter=FakeAdapter(), file_server=FakeFileServer())
    await sandbox.write_file(sandbox.resolve_path("pic.png", "g1"), b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    result = _json_result(await skill.execute("send_file", {"path": "pic.png", "chat_flow_id": "g1"}))

    assert result["ok"] is False
    assert "缺少 group_id 或 user_id" in result["error"]


async def test_send_file_missing_file_rejected(make_sandbox, tmp_path):
    """异常路径：send_file 目标文件不存在时应在调用 adapter 前拒绝。"""
    adapter = FakeAdapter()
    skill = _make_skill(make_sandbox(), adapter=adapter, file_server=FakeFileServer())

    result = _json_result(await skill.execute("send_file", {
        "path": str(tmp_path / "nope.png"), "group_id": "888",
    }))

    assert result["ok"] is False
    assert "文件不存在" in result["error"]
    assert adapter.calls == []


async def test_send_file_adapter_failed_response_reported(make_sandbox):
    """异常路径：adapter 返回 failed 状态时应透传 retcode 与原因。"""
    sandbox = make_sandbox()
    adapter = FakeAdapter(response=SimpleNamespace(status="failed", retcode=100, message="busy", wording=None))
    skill = _make_skill(sandbox, adapter=adapter, file_server=FakeFileServer())
    await sandbox.write_file(sandbox.resolve_path("pic.png", "g1"), b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    result = _json_result(await skill.execute("send_file", {
        "path": "pic.png", "user_id": "42", "chat_flow_id": "g1",
    }))

    assert result["ok"] is False
    assert "发送失败(retcode=100)" in result["error"]
    assert "busy" in result["error"]


async def test_send_chat_file_sends_file_segment(make_sandbox):
    """正常路径：send_chat_file 应发送 file 类型段（附件）而非图片段。"""
    sandbox = make_sandbox()
    adapter = FakeAdapter()
    skill = _make_skill(sandbox, adapter=adapter, file_server=FakeFileServer())
    await sandbox.write_file(sandbox.resolve_path("doc.pdf", "g1"), b"%PDF" + b"\x00" * 16)

    result = _json_result(await skill.execute("send_chat_file", {
        "path": "doc.pdf", "user_id": "42", "chat_flow_id": "g1",
    }))

    assert result["ok"] is True
    conv_ref, segments = adapter.calls[0]
    assert conv_ref.kind == "private"
    assert conv_ref.id == "42"
    assert segments[0]["type"] == "file"
    assert segments[0]["data"]["name"] == "doc.pdf"


async def test_hold_temp_ensures_temp_dir(make_sandbox):
    """正常路径：hold_temp 应创建并保活 chat_flow_id 的临时目录。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    result = _json_result(await skill.execute("hold_temp", {"chat_flow_id": "flow9", "minutes": 30}))

    assert result["ok"] is True
    assert "flow9" in result["note"]
    assert sandbox.get_temp_dir("flow9").is_dir()


async def test_write_file_with_documented_pipeline_key_format(make_sandbox):
    """正常路径：文档规定 chat_flow_id 取 pipeline_key（格式 group:12345），该格式应可写入临时目录（Windows 上当前失败）。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    result = _json_result(await skill.execute("write_file", {
        "path": "a.txt", "content": "x", "chat_flow_id": "group:12345",
    }))

    assert result["ok"] is True
    assert (sandbox.get_temp_dir("group:12345") / "a.txt").read_text("utf-8") == "x"


async def test_hold_temp_with_documented_pipeline_key_format(make_sandbox):
    """正常路径：hold_temp 对文档格式 chat_flow_id（group:9）应能创建临时目录（Windows 上当前失败）。"""
    sandbox = make_sandbox()
    skill = _make_skill(sandbox)

    result = _json_result(await skill.execute("hold_temp", {"chat_flow_id": "group:9"}))

    assert result["ok"] is True
    assert sandbox.get_temp_dir("group:9").is_dir()


async def test_unknown_tool_returns_error(make_sandbox):
    """异常路径：未知工具名应返回明确错误而非抛异常。"""
    skill = _make_skill(make_sandbox())

    result = _json_result(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown sandbox_manager tool" in result["error"]


def test_download_file_is_session_tool():
    """正常路径：download_file 应声明为会话工具（session_tools）。"""
    skill = SandboxManagerSkill()

    assert "download_file" in skill.session_tools

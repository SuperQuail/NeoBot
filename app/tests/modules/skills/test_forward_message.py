"""ForwardMessageSkill 测试 — 合并转发消息读取（消息结构解析与异常处理）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.forward_message import ForwardMessageSkill


class FakeAdapter:
    """记录 get_forward_msg 调用并可配置返回/异常的假适配器。"""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._result = result if result is not None else {"data": {"messages": []}}
        self._error = error

    async def get_forward_msg(self, message_id: str) -> Any:
        self.calls.append(message_id)
        if self._error is not None:
            raise self._error
        return self._result


def _parse(text: str) -> dict:
    return json.loads(text)


async def test_read_forward_msg_nested_data_structure():
    """正常路径：返回 {data:{messages:[...]}} 结构时应统计节点数并返回内容。"""
    messages = [{"name": "a", "content": "hi"}, {"name": "b", "content": "yo"}]
    adapter = FakeAdapter(result={"data": {"messages": messages}})
    skill = ForwardMessageSkill(adapter=adapter)

    result = _parse(await skill.execute("read_forward_msg", {"message_id": "123"}))

    assert result["ok"] is True
    assert result["node_count"] == 2
    assert "hi" in result["content"]
    assert adapter.calls == ["123"]


async def test_read_forward_msg_flat_structure():
    """边界：返回顶层含 messages 的结构时也应兼容解析。"""
    adapter = FakeAdapter(result={"messages": [{"content": "only"}]})
    skill = ForwardMessageSkill(adapter=adapter)

    result = _parse(await skill.execute("read_forward_msg", {"message_id": "456"}))

    assert result["ok"] is True
    assert result["node_count"] == 1


async def test_read_forward_msg_empty_messages():
    """边界：消息为空列表时应返回 node_count 0 且 ok。"""
    adapter = FakeAdapter(result={"data": {"messages": []}})
    skill = ForwardMessageSkill(adapter=adapter)

    result = _parse(await skill.execute("read_forward_msg", {"message_id": "789"}))

    assert result["ok"] is True
    assert result["node_count"] == 0


async def test_read_forward_msg_missing_message_id_rejected():
    """异常路径：缺少 message_id 时应拒绝且不调用适配器。"""
    adapter = FakeAdapter()
    skill = ForwardMessageSkill(adapter=adapter)

    result = _parse(await skill.execute("read_forward_msg", {}))

    assert result["ok"] is False
    assert "缺少 message_id" in result["error"]
    assert adapter.calls == []


async def test_read_forward_msg_adapter_error_reported():
    """异常路径：适配器抛异常时应返回错误信息而非崩溃。"""
    adapter = FakeAdapter(error=RuntimeError("forward api down"))
    skill = ForwardMessageSkill(adapter=adapter)

    result = _parse(await skill.execute("read_forward_msg", {"message_id": "123"}))

    assert result["ok"] is False
    assert "forward api down" in result["error"]


async def test_read_forward_msg_without_adapter_rejected():
    """异常路径：adapter 未配置时应返回配置错误。"""
    skill = ForwardMessageSkill()

    result = _parse(await skill.execute("read_forward_msg", {"message_id": "123"}))

    assert result["ok"] is False
    assert "adapter 未配置" in result["error"]


async def test_read_forward_msg_content_truncated_to_20_nodes():
    """边界：节点超过 20 个时返回内容应截断到前 20 个。"""
    messages = [{"content": f"msg-{i}"} for i in range(25)]
    adapter = FakeAdapter(result={"data": {"messages": messages}})
    skill = ForwardMessageSkill(adapter=adapter)

    result = _parse(await skill.execute("read_forward_msg", {"message_id": "123"}))

    assert result["ok"] is True
    assert result["node_count"] == 25
    content = result["content"]
    assert "msg-19" in content
    assert "msg-20" not in content


async def test_unknown_tool_returns_error():
    """异常路径：未知工具名应返回明确错误。"""
    skill = ForwardMessageSkill(adapter=FakeAdapter())

    result = _parse(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown forward_message tool" in result["error"]


def test_tools_empty_without_adapter():
    """边界：adapter 未配置时 get_tools 应返回空列表（不暴露无效工具）。"""
    skill = ForwardMessageSkill()

    assert skill.get_tools() == []

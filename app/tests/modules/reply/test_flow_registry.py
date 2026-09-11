"""聊天流快照登记处（网页面板「聊天流」页数据源）测试。"""

from __future__ import annotations

from neobot_app.reply.flow_registry import ChatFlowRegistry


def test_record_prompt_and_request_produce_listable_flow() -> None:
    registry = ChatFlowRegistry()

    registry.record_prompt(
        "group:888",
        system_prompt="系统提示词",
        model="deepseek-chat",
        conversation_kind="group",
        conversation_id="888",
    )
    registry.record_request(
        "group:888",
        messages=[
            {"role": "system", "content": "系统提示词"},
            {"role": "user", "content": "你好"},
        ],
        model="deepseek-chat",
        iteration=3,
    )

    items = registry.list_flows()
    assert len(items) == 1
    item = items[0]
    assert item["pipeline_key"] == "group:888"
    assert item["conversation_kind"] == "group"
    assert item["model"] == "deepseek-chat"
    assert item["message_count"] == 2
    assert item["total_messages"] == 2
    assert item["iterations"] == 3
    assert item["prompt_chars"] == len("系统提示词")
    assert item["active"] is False


def test_blank_pipeline_key_is_ignored() -> None:
    registry = ChatFlowRegistry()

    registry.record_prompt("", system_prompt="x")
    registry.record_request(None, messages=[{"role": "user", "content": "hi"}])  # type: ignore[arg-type]

    assert registry.list_flows() == []


def test_request_keeps_only_recent_messages_and_clips_content() -> None:
    registry = ChatFlowRegistry(max_messages=3, max_message_chars=200)

    registry.record_request(
        "private:1",
        messages=[
            {"role": "user", "content": f"message-{index}"} for index in range(6)
        ],
    )

    snapshot_state = registry.list_flows()[0]
    assert snapshot_state["message_count"] == 3
    assert snapshot_state["total_messages"] == 6


async def test_snapshot_reports_tool_calls_images_and_truncation() -> None:
    # 单条消息预览的字符下限被钳制在 200（避免面板拿到毫无信息量的片段）
    registry = ChatFlowRegistry(max_message_chars=50)
    registry.record_request(
        "group:888",
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "send_reply", "arguments": {"text": "hi"}},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "x" * 500},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看这张图"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
                ],
            },
        ],
    )

    snapshot = await registry.snapshot("group:888")

    assert snapshot is not None
    assistant, tool, user = snapshot["messages"]
    assert assistant["tool_calls"][0]["name"] == "send_reply"
    assert "hi" in assistant["tool_calls"][0]["arguments"]
    assert tool["truncated"] is True
    assert len(tool["content"]) == 200
    assert tool["chars"] == 500
    assert user["images"] == 1
    assert "看这张图" in user["content"]


async def test_snapshot_missing_flow_returns_none() -> None:
    registry = ChatFlowRegistry()

    assert await registry.snapshot("group:404") is None


def test_set_active_toggles_state() -> None:
    registry = ChatFlowRegistry()

    registry.set_active("group:888", True)
    assert registry.list_flows()[0]["active"] is True
    registry.set_active("group:888", False)
    assert registry.list_flows()[0]["active"] is False


def test_oldest_flow_is_evicted_beyond_capacity() -> None:
    registry = ChatFlowRegistry(max_flows=2)

    for index in range(3):
        registry.record_prompt(f"group:{index}", system_prompt=f"p{index}")

    keys = {item["pipeline_key"] for item in registry.list_flows()}
    assert len(keys) == 2


async def test_background_tasks_aggregate_providers_and_isolate_failures() -> None:
    registry = ChatFlowRegistry()
    registry.register_task_provider("drawing", lambda key: {"active_task": None})

    async def _async_provider(key: str) -> dict:
        return {"solver_active_task": {"task_id": key}}

    def _broken(key: str) -> dict:
        raise RuntimeError("manager down")

    registry.register_task_provider("problem_solver", _async_provider)
    registry.register_task_provider("notification", _broken)
    registry.register_task_provider("", lambda key: {})  # 空名字被忽略

    result = await registry.background_tasks("group:888")

    assert result["active_task"] is None
    assert result["solver_active_task"] == {"task_id": "group:888"}
    assert "manager down" in result["notification_error"]

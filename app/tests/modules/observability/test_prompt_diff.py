"""prompt_diff 纯函数测试：图片脱敏、JSON diff/patch、体积度量。

对应 features/spec(10) 的两条硬要求：
- 图片不保存 base64，只留图库同口径的 sha256；
- 历史上以逐份 diff 保存，补丁必须显著小于整份。
"""

from __future__ import annotations

import base64
import hashlib

from neobot_app.observability.prompt_diff import (
    IMAGE_HASH_PREFIX,
    apply_patch_copy,
    count_image_refs,
    diff_payload,
    json_safe,
    patch_bytes,
    payload_bytes,
    sanitize_images,
)


def _data_url(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


# ── 图片脱敏 ────────────────────────────────────────────────────


def test_sanitize_replaces_image_data_url_with_sha256() -> None:
    raw = b"\x89PNG" + b"payload" * 64
    payload = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "看图"}]},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _data_url(raw)}}
                ],
            },
        ]
    }

    sanitized, replaced, freed = sanitize_images(payload)

    assert replaced == 1
    assert freed == len(_data_url(raw))
    url = sanitized["messages"][1]["content"][0]["image_url"]["url"]
    assert url == IMAGE_HASH_PREFIX + hashlib.sha256(raw).hexdigest()
    assert "base64" not in url
    # 原对象不受影响（结构共享 + 只在被替换的分支复制）
    assert payload["messages"][1]["content"][0]["image_url"]["url"].startswith("data:")
    assert sanitized["messages"][0] is payload["messages"][0]


def test_sanitize_keeps_non_image_and_short_values() -> None:
    payload = {
        "text": _data_url(b"x", mime="text/plain"),
        "url": "https://example.com/a.png",
        "blob": "sha256:" + "a" * 64,
    }

    sanitized, replaced, freed = sanitize_images(payload)

    assert sanitized is payload
    assert replaced == 0 and freed == 0


def test_sanitize_replaces_raw_image_base64_field() -> None:
    raw = bytes(range(256)) * 8
    payload = {"arguments": {"image_base64": base64.b64encode(raw).decode("ascii")}}

    sanitized, replaced, _freed = sanitize_images(payload)

    assert replaced == 1
    assert sanitized["arguments"]["image_base64"] == (
        IMAGE_HASH_PREFIX + hashlib.sha256(raw).hexdigest()
    )


def test_sanitize_handles_nested_lists_and_counts_refs() -> None:
    raw = b"abc" * 100
    payload = {"a": [{"b": [_data_url(raw), _data_url(raw)]}]}

    sanitized, replaced, _freed = sanitize_images(payload)

    assert replaced == 2
    assert count_image_refs(sanitized) == 2
    assert count_image_refs(payload) == 0


# ── diff / patch ────────────────────────────────────────────────


def _growing(messages: int) -> dict:
    rows = [{"role": "system", "content": "人设" * 200}]
    for index in range(messages):
        rows.append({"role": "user", "content": f"第 {index} 条消息" * 20})
    return {
        "pipeline_key": "group:1",
        "iteration": messages,
        "messages": rows,
        "response": None,
        "usage": None,
    }


def test_apply_patch_roundtrip_for_growing_messages() -> None:
    old = _growing(5)
    new = _growing(8)

    patch = diff_payload(old, new)

    assert apply_patch_copy(old, patch) == new


def test_append_only_growth_patch_is_only_adds() -> None:
    old = _growing(20)
    new = _growing(22)

    patch = diff_payload(old, new)

    # messages 只追加：没有 replace/remove，只有两条 add
    message_ops = [op for op in patch if op["path"][:1] == ["messages"]]
    assert [op["op"] for op in message_ops] == ["add", "add"]
    assert [op["path"] for op in message_ops] == [["messages", 21], ["messages", 22]]
    # 其余字段按标量替换
    assert {op["path"][0] for op in patch} == {"messages", "iteration"}
    # 补丁明显小于整份（真实 payload 里基座更长，比例会好得多；
    # 端到端的「常驻 vs 全量」对比见 test_context_recorder_history）
    assert patch_bytes(patch) * 8 < payload_bytes(new)


def test_patch_handles_removed_and_changed_entries() -> None:
    old = {
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
        ],
        "usage": {"input_tokens": 10, "detail": {"x": 1}},
    }
    new = {
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "b"},
            {"role": "user", "content": "c"},
        ],
        "usage": {"input_tokens": 20},
    }

    patch = diff_payload(old, new)

    assert apply_patch_copy(old, patch) == new
    ops = {op["op"] for op in patch}
    assert "remove" in ops and "replace" in ops


def test_patch_for_identical_payload_is_empty() -> None:
    payload = _growing(3)
    patch = diff_payload(payload, json_safe(payload))
    assert patch == []
    assert apply_patch_copy(payload, patch) == payload


def test_root_replacement_when_types_differ() -> None:
    patch = diff_payload(["a"], {"a": 1})
    assert patch == [{"op": "replace", "path": [], "value": {"a": 1}}]
    assert apply_patch_copy(["a"], patch) == {"a": 1}


def test_keys_with_slash_are_not_confused() -> None:
    old = {"a/b": {"c~d": 1}}
    new = {"a/b": {"c~d": 2}}

    patch = diff_payload(old, new)

    assert patch == [{"op": "replace", "path": ["a/b", "c~d"], "value": 2}]
    assert apply_patch_copy(old, patch) == new


# ── JSON 归一与体积 ─────────────────────────────────────────────


def test_json_safe_deep_copies_and_stringifies() -> None:
    class _Weird:
        def __str__(self) -> str:
            return "weird"

    payload = {"obj": _Weird(), "tuple": (1, 2)}

    safe = json_safe(payload)

    assert safe == {"obj": "weird", "tuple": [1, 2]}
    safe["tuple"].append(3)
    assert payload["tuple"] == (1, 2)


def test_payload_bytes_matches_json_length() -> None:
    payload = {"a": "中文", "b": [1, 2, 3]}
    assert payload_bytes(payload) == len(
        '{"a": "中文", "b": [1, 2, 3]}'.encode("utf-8")
    )
    assert patch_bytes([]) == len("[]")

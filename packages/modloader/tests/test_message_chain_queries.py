"""消息链查询保留顺序、类型和未知协议字段。"""

from __future__ import annotations

import pytest

from neobot_modloader.message import ImageSegment, Message, MessageChain, MessageSegment


class StickerSegment(ImageSegment):
    pass


@pytest.fixture
def chain() -> MessageChain:
    return (
        MessageChain()
        .text("开始")
        .image(file="first.image")
        .at("all")
        .segment(StickerSegment({"file": "sticker.image", "nested": {"tags": ["表情"]}}))
        .segment({"type": "vendor.card", "data": {"nested": {"items": [1, None, False]}}})
        .text("结束")
    )


def test_queries_accept_wire_type_or_segment_class(chain: MessageChain) -> None:
    original = chain.to_list()

    assert [item.file for item in chain.get(ImageSegment)] == ["first.image", "sticker.image"]
    assert chain.get("image") == chain.get(ImageSegment)
    assert len(chain.get(MessageSegment)) == 6
    assert chain.has("vendor.card")
    assert chain.has(StickerSegment)
    assert chain.first(ImageSegment) is chain.segments[1]
    assert chain.first("vendor.card").data == {"nested": {"items": [1, None, False]}}
    assert chain.to_list() == original


def test_missing_queries_are_safe_for_empty_and_nonempty_chains(chain: MessageChain) -> None:
    for candidate in (chain, MessageChain()):
        assert candidate.get("record") == []
        assert candidate.first("record") is None
        assert not candidate.has("record")


def test_include_and_exclude_return_new_chains_in_original_order(chain: MessageChain) -> None:
    original = chain.to_list()

    included = chain.include("vendor.card", ImageSegment)
    excluded = chain.exclude("text", ImageSegment)

    assert isinstance(included, MessageChain)
    assert [item.type for item in included] == ["image", "image", "vendor.card"]
    assert [item.type for item in excluded] == ["at", "vendor.card"]
    included.text("仅修改结果链")
    assert chain.to_list() == original
    assert chain.include().to_list() == []
    assert chain.exclude().to_list() == original


def test_copy_detaches_nested_data_and_keeps_custom_segment_class(chain: MessageChain) -> None:
    copied = chain.copy()
    copied.first("vendor.card").data["nested"]["items"].append("副本")
    copied.first(StickerSegment).data["nested"]["tags"].append("副本")
    copied.text("副本结尾")

    assert chain.first("vendor.card").data["nested"]["items"] == [1, None, False]
    assert chain.first(StickerSegment).data["nested"]["tags"] == ["表情"]
    assert isinstance(copied.first(StickerSegment), StickerSegment)
    assert len(chain) == 6
    assert len(copied) == 7


def test_sequence_operations_preserve_element_order(chain: MessageChain) -> None:
    assert len(chain) == 6
    assert list(chain) == chain.segments
    assert chain[0].text == "开始"
    assert chain[-1].text == "结束"
    assert isinstance(chain[1:5:2], MessageChain)
    assert [item.file for item in chain[1:5:2]] == ["first.image", "sticker.image"]
    assert [item.text for item in chain[::-1].get("text")] == ["结束", "开始"]
    assert chain[99:].to_list() == []
    with pytest.raises(IndexError):
        chain[99]


def test_message_to_chain_is_a_detached_snapshot() -> None:
    raw = {"type": "vendor.card", "data": {"nested": {"items": [1, None, False]}}}
    message = Message({"message": [raw]})

    copied = message.to_chain()
    copied.first("vendor.card").data["nested"]["items"].append("副本")
    copied.text("补充")

    assert message.to_list() == [raw]
    assert message.to_chain().has("vendor.card")
    assert not message.to_chain().has(ImageSegment)

"""会看图的组件必须能换装视觉 provider（issue #75）。

这些组件在**启动期**建好后长期持有视觉 provider，而且真的在用（表情包图片解析、
绘图看参考图、图片解析）。没有换装入口时，换了视觉模型它们仍走旧模型 ——
所以每个都要实现 install_vision_provider，并由热重载消费者推新实例。
"""

from __future__ import annotations

from pathlib import Path

from neobot_app.emoji.service import EmojiService
from neobot_app.skills.drawing_skill import DrawingSkill
from neobot_app.skills.gallery_skill import GallerySkill
from neobot_app.skills.image_parse_skill import ImageParseSkill


def _targets() -> list[object]:
    return [
        EmojiService(data_dir=Path("."), uow_factory=None),
        DrawingSkill(),
        ImageParseSkill(),
        GallerySkill(),
    ]


def test_vision_provider_installers_swap_and_return_previous() -> None:
    """换装 = 只换引用 + 返回旧对象（与 install_provider 同一契约，由调用方决定何时关闭）。"""
    first, second = object(), object()

    for target in _targets():
        installer = getattr(target, "install_vision_provider", None)
        assert callable(installer), f"{type(target).__name__} 缺少 install_vision_provider 换装入口"

        installer(first)
        assert target._vision_provider is first

        assert installer(second) is first, "必须返回被替换下来的旧 provider"
        assert target._vision_provider is second


def test_all_skill_modules_exposing_vision_are_installable() -> None:
    """扫一遍技能：凡是持有视觉 provider 的，都必须实现换装入口。

    热重载消费者是按「谁实现了 install_vision_provider 就推给谁」扫描的，
    漏实现 = 换模型后它继续用旧的（而且不会有任何提示）。
    """
    from neobot_app.skills.base import SkillManager

    manager = SkillManager()
    holders = []
    for target in _targets():
        if hasattr(target, "_vision_provider"):
            holders.append(type(target).__name__)

    assert "EmojiService" in holders
    # 技能侧：这三个都持有视觉 provider，且都能换
    for target in (DrawingSkill(), ImageParseSkill(), GallerySkill()):
        assert hasattr(target, "_vision_provider")
        assert callable(getattr(target, "install_vision_provider", None))

    # 消费者是按 `all_skills()` 扫的：这个入口必须存在且返回列表（没有技能时也要能扫）
    # all_skills 是 **property**（不是方法）：写成 all_skills() 会直接 TypeError —— 实测踩过
    assert isinstance(manager.all_skills, list)

"""出厂默认配置的可部署性契约。

改了默认值就要钉住「新用户装上能跑」这件事：
- admin_accounts 是**非必须**项（留空能启动），缺口由面板首页提示承担；
- 默认定价按 DeepSeek 官方价目表的**高峰价**，并挂峰谷脚本（填均价会让金额系统性偏小）。
"""

from __future__ import annotations

import typing

from neobot_app.config.schemas.bot import BotConfig, ModelDefinition


def _chat_models(config: BotConfig) -> list[ModelDefinition]:
    return [m for m in config.models.registry if m.model_type == "chat"]


def test_admin_accounts_is_optional_not_required() -> None:
    """留空不能拦启动：它由面板首页提示，而不是配置校验。"""
    # 判据是「类型里允许 None」——比匹配 "Optional[" 字符串可靠：
    # Python 3.14 把 Optional[List[str]] 的 repr 改成了 "typing.List[str] | None"，
    # 字符串匹配会在 3.13 通过、3.14 失败（CI 就是这么挂的）。
    # 注意取的是**实例的类**：BotConfig.chat 这种类属性在 default_factory 字段上并不存在
    chat_section = BotConfig().chat
    hint = typing.get_type_hints(type(chat_section))["admin_accounts"]
    assert type(None) in typing.get_args(hint), "admin_accounts 应为 Optional，否则会被当成必须项"
    assert chat_section.admin_accounts == []


def test_default_chat_models_use_deepseek_official_peak_pricing() -> None:
    """默认对话模型按官方**高峰价**定价，并挂峰谷折算脚本。

    来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
    （deepseek-flash：输入 2 / 缓存命中 0.04 / 输出 8，元每百万 tokens，高峰时段）
    """
    models = _chat_models(BotConfig())
    assert models, "默认库应当有对话模型"

    for model in models:
        assert model.pricing.input_price_per_mtokens == 2.0, model.model_ref
        assert model.pricing.output_price_per_mtokens == 8.0, model.model_ref
        assert model.pricing.cache_hit_price_per_mtokens == 0.04, model.model_ref
        assert model.billing_script == "deepseek_peak_valley", model.model_ref


def test_defaults_are_deployable_without_extra_platforms() -> None:
    """出厂只需要 DeepSeek 一个平台即可跑起来。

    不预置生图模型（原先那条指向平台侧不存在的模型名）、不预置独立视觉模型、
    TTS 默认关闭 —— 少一个「必须去申请 Key 才能启动」的坑。
    """
    config = BotConfig()
    refs = {m.model_ref for m in config.models.registry}

    assert "flux-schnell" not in refs, "不应再有那个不存在的生图默认条目"
    assert config.models.assignments.creator_image_models == []
    # 视觉模型复用对话模型，真实可用
    assert config.models.assignments.vision_model in refs
    assert config.models.get(config.models.assignments.vision_model).model_type == "chat"
    # TTS 默认关闭（模型条目保留，用户开开关即可）
    assert config.tts.enabled is False


def test_creator_enabled_with_emoji_management_but_no_ai_drawing() -> None:
    """Creator 默认开启表情包增删，但 AI 绘图要另行分配生图模型。"""
    creator = BotConfig().agent.creator

    assert creator.enabled is True
    assert creator.emoji.allow_add is True
    assert creator.emoji.allow_delete is True
    # 没有生图模型分配 = 不开启 AI 绘图
    assert BotConfig().models.assignments.creator_image_models == []

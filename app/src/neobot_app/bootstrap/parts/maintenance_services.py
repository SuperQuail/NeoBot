"""维护相关的可选服务装配：web_search 配置、计费热重载规则、provider 重建消费者。"""

from __future__ import annotations

import inspect
import os
from typing import Any


def _web_search_config_dict(config: Any) -> dict[str, Any]:
    """把 `[web_search]` 段转成 WebSearchExecutor 需要的 dict。

    此前两处调用点都硬编码 `{}`，导致 `[web_search]` 段是**死配置**（fix(9) F5）：
    引擎顺序、浏览器兜底、预算都改不动。这里按实测默认值补全：
    duckduckgo 作为最后兜底给 15s（部署实测它慢），浏览器通道给 8s（实测单次约 1s）。
    """
    section = getattr(config, "web_search", None)
    if section is None:
        return {}
    engines = getattr(section, "engines", None)
    result: dict[str, Any] = {
        "engines": list(engines) if engines else ["bing", "duckduckgo"],
        "max_rounds": int(getattr(section, "max_search_rounds", None) or 5),
        "preview_pages_limit": int(getattr(section, "preview_pages_limit", None) or 30),
        "variant_result_limit": int(getattr(section, "variant_result_limit", None) or 6),
        "browser_fallback": bool(getattr(section, "browser_fallback", True)),
        "browser_timeout_seconds": float(
            getattr(section, "browser_timeout_seconds", None) or 8.0
        ),
        "deepseek_enabled": bool(getattr(section, "deepseek_enabled", False)),
        "deepseek_timeout_seconds": float(
            getattr(section, "deepseek_timeout_seconds", None) or 20.0
        ),
        "deepseek_quota_cooldown_seconds": int(
            getattr(section, "deepseek_quota_cooldown_seconds", None) or 300
        ),
        "deepseek_api_key": os.environ.get("DeepSeek_APIKey", "").strip(),
        "deepseek_base_url": os.environ.get("DeepSeek_URL", "").strip(),
    }
    budgets = getattr(section, "engine_timeout_seconds", None)
    if isinstance(budgets, dict) and budgets:
        result["engine_budgets"] = {str(k): float(v) for k, v in budgets.items()}
    return result


def _register_billing_hot_reload_rule() -> None:
    """登记 ``billing`` 段为「运行期生效」（spec(4) Q13 / R4）。

    ``[billing]`` 段由 BillingService 每次现取，改 ``enabled`` / ``timeout_ms`` 等
    立即生效；挂在 ``models`` 段下的 ``billing_script`` / ``billing_config`` 仍按
    「面板保存并重载」路径生效。
    """
    from neobot_app.config.hot_reload import HotReloadRule, register_rule

    register_rule(HotReloadRule("billing", True, "计费脚本按需加载，重载后立即生效"))


def _warmup_billing_scripts(billing: Any) -> None:
    """启动装配期预加载「注册表里出现过的 billing_script 名字集合」（§4.2）。"""
    if billing is None:
        return
    try:
        settings = billing.settings
        if not settings.enabled:
            # 关闭时不加载任何脚本、不建线程池（零额外开销）
            return
        from neobot_chat.models import model_registry

        names = {
            str(getattr(model, "billing_script", "") or "").strip()
            for _key, model in model_registry.items()
        }
        billing.warmup(sorted(name for name in names if name))
    except Exception as exc:  # pragma: no cover - 预加载失败不影响启动
        import logging

        logging.getLogger(__name__).warning(f"计费脚本预加载失败: {exc}")


def _build_provider_reload_consumer(
    *,
    logger_factory: Any,
    reply_orchestrator: Any,
    image_parse_service: Any,
    archive_summary_service: Any,
    initial_vision_provider: Any,
) -> ProviderReloadConsumer:
    """装配 provider 重建消费者：构建 + 各挂载点的换引用与清理。

    这里集中表达「provider 被谁持有」这一事实，避免该知识散落在多个模块里。
    """
    from neobot_app.bootstrap._providers import (
        build_main_provider,
        build_vision_provider,
        resolve_vision_model_name,
    )
    from neobot_app.runtime.provider_reload import (
        ProviderBundle,
        ProviderReloadConsumer,
    )

    provider_logger = logger_factory.get_logger("app.provider")

    def _build(config: Any) -> ProviderBundle:
        vision = build_vision_provider(
            logger=provider_logger,
            model_name=resolve_vision_model_name(config),
        )
        main, main_error = build_main_provider(
            config=config, logger=provider_logger, vision_provider=vision
        )
        return ProviderBundle(main=main, main_error=main_error, vision=vision)

    def _install_reply(bundle: ProviderBundle) -> Any:
        return reply_orchestrator.install_provider(bundle.main, bundle.main_error)

    def _install_images(bundle: ProviderBundle) -> Any:
        return image_parse_service.install_providers(
            vision_provider=bundle.vision,
            native_vision_provider=bundle.main,
        )

    def _install_archive(bundle: ProviderBundle) -> Any:
        return archive_summary_service.install_provider(bundle.main)

    async def _dispose_provider(previous: Any) -> None:
        closer = getattr(previous, "close", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result

    def _dispose_images(previous: Any) -> None:
        """图片解析持有 (vision, native) 两个 provider：只关前者。

        native 与回复 provider 是同一个对象，由回复挂载点负责关闭，重复关闭
        会触发 provider 内部的重复释放。
        """
        vision = previous[0] if isinstance(previous, tuple) else previous
        return _dispose_provider(vision)

    return ProviderReloadConsumer(
        builder=_build,
        installers={
            "reply": (_install_reply, _dispose_provider),
            "image_parse": (_install_images, _dispose_images),
            "archive_summary": (_install_archive, lambda _previous: None),
        },
        logger=logger_factory.get_logger("app.provider_reload"),
    )

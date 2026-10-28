"""推理强度（reasoning effort）：模型库顶层字段的唯一真相源。

同一个配置字段要喂三处下游：schema 元数据（面板下拉）、加载器（格式解析与校验）、
provider（请求体）。取值与中文显示名只写在这里，避免三处各抄一份。

两个格式系共用一套取值：OpenAI 系下发请求体 ``reasoning_effort``，Claude 系下发
``output_config.effort``（Anthropic Messages API 只认后者），用 ``claude:`` 前缀
在同一个字段里区分——用户选 Claude 系档位时能一眼看出用的是哪套名字。

DeepSeek 官方 Chat Completions 只认 high / max，也没有 Anthropic 的
``output_config``：这两条限制在 resolve 里统一处理，加载器只负责告警与日志。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

#: OpenAI 系 ``reasoning_effort`` 的取值
OPENAI_EFFORTS: Tuple[str, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

#: Claude 系 ``output_config.effort`` 的取值：Anthropic 没有 none / minimal 档位
CLAUDE_EFFORTS: Tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

#: Claude 系取值在配置字段里的前缀
CLAUDE_PREFIX = "claude:"

#: 字段可选值（"" = 不单独下发；顺序即面板下拉顺序）
EFFORT_OPTIONS: List[str] = [
    "",
    *OPENAI_EFFORTS,
    *(CLAUDE_PREFIX + item for item in CLAUDE_EFFORTS),
]

#: 选项中文显示名（面板下拉文案）；Claude 系一律带「Claude 系」前缀，避免与 OpenAI 档位混淆
OPTION_LABELS: Dict[str, str] = {
    "": "不设置（沿用供应商默认）",
    "none": "none（关闭推理）",
    "minimal": "minimal（极低）",
    "low": "low（低）",
    "medium": "medium（中）",
    "high": "high（高）",
    "xhigh": "xhigh（极高）",
    "max": "max（最高）",
    "claude:low": "Claude 系 · low（低）",
    "claude:medium": "Claude 系 · medium（中）",
    "claude:high": "Claude 系 · high（高）",
    "claude:xhigh": "Claude 系 · xhigh（极高）",
    "claude:max": "Claude 系 · max（最高）",
}

#: 面板下拉分组（静态元数据，由 describe 原样透传给前端）
OPTION_GROUPS: List[Dict[str, Any]] = [
    {"label": "OpenAI 系（reasoning_effort）", "options": list(OPENAI_EFFORTS)},
    {
        "label": "Claude 系（output_config.effort）",
        "options": [CLAUDE_PREFIX + item for item in CLAUDE_EFFORTS],
    },
]

#: DeepSeek 官方只认 high / max：历史档位按就近归并（与 provider 既有行为一致）
DEEPSEEK_EFFORT_MAP: Dict[str, str] = {
    "none": "high",
    "minimal": "high",
    "low": "high",
    "medium": "high",
    "high": "high",
    "xhigh": "max",
    "max": "max",
}

#: 面板/日志用于展示的归类；未识别的供应商按 OpenAI 兼容处理
_PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "deepseek": "deepseek",
    "deepseek_offical": "deepseek",
    "deepseek_official": "deepseek",
}


def normalize_effort_provider(provider_kind: Any) -> str:
    """归一推理强度相关的供应商归类：anthropic / deepseek / openai。"""
    raw = str(provider_kind or "").strip().casefold().replace("-", "_")
    return _PROVIDER_ALIASES.get(raw, "openai")


def deepseek_effective_effort(value: Any) -> str | None:
    """把任意档位归并成 DeepSeek 真正能下发的 high / max；未知值返回 None。"""
    return DEEPSEEK_EFFORT_MAP.get(str(value or "").strip().casefold())


def resolve_reasoning_effort(value: str, *, provider_kind: str = "openai") -> Tuple[str | None, str]:
    """把配置值解析成（最终下发的 effort 值, 最终格式 "openai" | "claude"）。

    - 空值：不单独下发（None），返回的格式只用于日志/记录；
    - ``claude:`` 前缀：按 Claude 系下发（与 provider 无关，供走 Anthropic 协议的
      中转站使用），前缀去掉；DeepSeek 官方没有这个字段，直接判为无效；
    - 普通值：Anthropic 按 Claude 系、其余按 OpenAI 系下发；Claude 系没有
      none / minimal 档位，选了就视为无效；
    - DeepSeek 官方：普通值按 high / max 归并（none/minimal/low/medium→high，
      xhigh→max），保证运行时 settings 里就是真正下发的值；
    - 非法值：返回 (None, 格式)，由调用方记 warning ——「配了却不生效」不能静默。
    """
    provider = normalize_effort_provider(provider_kind)
    default_format = "claude" if provider == "anthropic" else "openai"
    text = str(value or "").strip().casefold()
    if not text:
        return None, default_format
    if text.startswith(CLAUDE_PREFIX):
        effort = text[len(CLAUDE_PREFIX) :].strip()
        if provider == "deepseek":
            # DeepSeek /chat/completions 没有 output_config；显式选 Claude 系属于配置错误
            return None, "openai"
        if effort not in CLAUDE_EFFORTS:
            return None, "claude"
        return effort, "claude"
    if text not in OPENAI_EFFORTS:
        return None, default_format
    if provider == "deepseek":
        return deepseek_effective_effort(text), "openai"
    if provider == "anthropic":
        return (text, "claude") if text in CLAUDE_EFFORTS else (None, "claude")
    return text, "openai"


def describe_reasoning_effort(
    value: str,
    *,
    provider_kind: str = "",
    model_type: str = "chat",
    thinking_enabled: bool = True,
) -> str:
    """面板展示名：带上前缀/实际下发/不生效原因，避免「显示的值不是真正下发的值」。

    - ``claude:high`` -> ``Claude 系 · high``；Anthropic 上的普通值也标成 Claude 系；
    - DeepSeek 上被归并的档位标「实际下发 high/max」，Claude 系前缀标「DeepSeek 不支持」；
    - 思考模式关闭、生图 / TTS 模型都标出不生效原因；
    - 空值 / 无效值分别返回 "" 与「xxx（无效）」。
    """
    provider = normalize_effort_provider(provider_kind)
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    if text.startswith(CLAUDE_PREFIX):
        suffix = text[len(CLAUDE_PREFIX) :].strip()
        if suffix not in CLAUDE_EFFORTS:
            return text + "（无效）"
        label = "Claude 系 · " + suffix
        if provider == "deepseek":
            return label + "（DeepSeek 不支持 Claude 系）"
    elif text in OPENAI_EFFORTS:
        if provider == "anthropic":
            if text not in CLAUDE_EFFORTS:
                return text + "（Claude 系不支持）"
            label = "Claude 系 · " + text
        else:
            label = text
    else:
        return text + "（无效）"
    if model_type in {"image", "tts"}:
        return label + "（该模型类型不生效）"
    if provider == "deepseek":
        if not thinking_enabled:
            return label + "（思考已关闭，不下发）"
        effective = DEEPSEEK_EFFORT_MAP.get(text)
        if effective is not None and effective != text:
            return label + "（实际下发 " + effective + "）"
    return label

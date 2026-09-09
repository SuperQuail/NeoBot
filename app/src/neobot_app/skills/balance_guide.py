"""余额查询技能文档生成。

每个模型可在 config 中配置 balance_query_hint（查询方式文本）。
本模块把这些提示汇总成一份按需读取的 SKILL.md，并在配置重载时刷新：

- 只为配置了提示的模型生成条目；未配置的模型不会出现在文档里。
- 文档末尾固定追加「未显示查询方式则代表无查询提示」。
- 同时写入数据目录 skills/balance-query/SKILL.md（便于人工查看与 read_resource）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

SKILL_DIR_NAME = "balance-query"
SKILL_OWNER = "balance"
NO_HINT_NOTE = "未显示查询方式则代表无查询提示"

_DESCRIPTION = "查询各 AI 模型供应商账户余额的查询方式（按需读取，含请求地址与鉴权说明）"
_KEYWORDS = "余额 查询余额 账户余额 balance 充值 额度 用量"


def _model_entries(config: Any) -> list[tuple[str, Any]]:
    models = getattr(config, "models", None)
    iterator = getattr(models, "iter_registrations", None)
    if not callable(iterator):
        return []
    return [(str(name), model) for name, model in iterator()]


def build_balance_query_document(config: Any) -> tuple[str, int]:
    """生成 SKILL.md 正文，返回 (内容, 带查询提示的模型数量)。"""
    lines = [
        "# 余额查询方式",
        "",
        "下面的查询方式由 config.toml 中每个模型的 balance_query_hint 提供。",
        "按需使用 balance_query__http_request 工具发起请求：把「查询方式」里的地址、方法、",
        "请求头与参数原样填入工具参数即可；响应里的余额字段按说明自行解析。",
        "",
        "注意：",
        "- 只在用户明确询问余额/额度，或需要判断是否需要充值时查询，不要频繁调用。",
        "- 提示里若给了自建/局域网地址，调用工具时需额外传 allow_private=true。",
        "- 密钥请从 .env 的平台配置或提示文本中读取，不要把密钥写进回复。",
        "",
    ]

    count = 0
    for name, model in _model_entries(config):
        hint = str(getattr(model, "balance_query_hint", "") or "").strip()
        if not hint:
            continue
        count += 1
        description = str(getattr(model, "description", "") or "").strip()
        provider = str(getattr(model, "provider", "") or "").strip()
        model_name = str(getattr(model, "model_name", "") or "").strip()
        lines.append(f"## {name}")
        if description:
            lines.append(f"- 描述: {description}")
        lines.append(f"- 供应商: {provider or '未填写'}")
        lines.append(f"- 模型: {model_name or '未填写'}")
        lines.append("- 查询方式:")
        for hint_line in hint.splitlines() or [hint]:
            lines.append(f"  {hint_line}" if hint_line.strip() else "")
        lines.append("")

    lines.append(NO_HINT_NOTE)
    lines.append("")
    return "\n".join(lines), count


def _frontmatter() -> str:
    return "\n".join(
        [
            "---",
            f"name: {SKILL_DIR_NAME}",
            f"description: {_DESCRIPTION}",
            f"keywords: {_KEYWORDS}",
            "---",
            "",
        ]
    )


def sync_balance_query_skill(
    *,
    registry: Any,
    data_dir: Path,
    config: Any,
    logger: Any = None,
) -> bool:
    """刷新余额查询技能（写文件 + 注册到 Markdown Skill 注册表）。

    返回是否注册成功；registry 为 None 时只写文件。
    """
    document, hint_count = build_balance_query_document(config)
    skill_dir = Path(data_dir) / "skills" / SKILL_DIR_NAME
    skill_path = skill_dir / "SKILL.md"
    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_frontmatter() + document, encoding="utf-8")
    except OSError as exc:
        if logger is not None:
            logger.warning(f"写入余额查询技能文档失败: {exc}")
        return False

    if registry is None:
        return False

    try:
        unregister = getattr(registry, "unregister_owner", None)
        if callable(unregister):
            unregister(SKILL_OWNER)
        register_many = getattr(registry, "register_many", None)
        if not callable(register_many):
            return False
        register_many(
            SKILL_OWNER,
            [
                SimpleNamespace(
                    name=SKILL_DIR_NAME,
                    description=_DESCRIPTION,
                    content=document,
                    path=skill_path,
                    keywords=_KEYWORDS,
                    metadata={"models_with_hint": hint_count},
                )
            ],
        )
    except Exception as exc:
        if logger is not None:
            logger.warning(f"注册余额查询技能失败: {exc}")
        return False

    if logger is not None:
        logger.info(
            f"余额查询技能已就绪：{hint_count} 个模型配置了查询方式"
            if hint_count
            else "余额查询技能已就绪：暂无模型配置查询方式"
        )
    return True

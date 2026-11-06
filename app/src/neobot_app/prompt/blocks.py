"""提示词块注册表：声明每个提示词块的阶段、作用域、顺序与启用条件。

设计约定
--------
- **文本**放 ``templates/prompts.toml`` 的分区里（用户可覆盖、面板可编辑）；
- **行为**放这里：块在哪个阶段、对哪些会话生效、相对顺序、启用条件；
- 新增一个块 = 这里加一条 ``Block`` + TOML 加一个分区（或提供 ``text`` 动态文本），
  不需要改 builder 的 if 链，也不需要改 orchestrator 的注入顺序。

阶段（从上到下即一次请求里的顺序）
----------------------------------
``SYSTEM_PREFIX``   system 最前面的全局 cot 板块（``<cot>`` … ``</cot>``）
``SYSTEM_MAIN``     场景主模板（群聊 / 私聊 / 直播间）
``SYSTEM_APPEND``   稳定内容追加到 system 末尾
``CONTEXT``         每次构建的上下文 user 块（system 之后、聊天记录之前）
``RUNTIME_DATA``    会话中途的动态内容（通知 / 新消息 / 新档案 / 图片说明）
``REMINDER``        提醒类 user 块（防重复 / 沉默提醒 / 无工具提醒）
``TIME``            每次调用前的时间块（terminal，必须是消息列表最后一条）
``TOOL_RESULT``     工具结果压缩文案（由压缩逻辑按键读取，不进消息管道）
``STATUS``          命令 / 状态文案（sleep、wake、超长兜底等）
``SUBAGENT``        子 Agent 的 system 提示词

新增块检查清单：id 唯一、分区存在（或给 ``text``）、声明 ``scopes``、
按需给 ``requires``，然后跑 ``app/tests/modules/prompt/test_prompt_registry.py``。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from neobot_app.prompt.context import BOTH_CHATS, PromptContext, Scope

Requirement = Callable[[PromptContext], "str | None"]
"""返回 None 表示通过；返回字符串是**未通过原因**（会进日志 / 调试面板）。"""


class Stage(str, Enum):
    SYSTEM_PREFIX = "system_prefix"
    SYSTEM_MAIN = "system_main"
    SYSTEM_APPEND = "system_append"
    #: 不直接注入，供其它模板通过 ``{块id}`` 占位符引用的共享片段
    FRAGMENT = "fragment"
    #: 不直接注入，只登记文本资产：内部标签、B站提示词等，由 assets 统一读取
    CATALOG = "catalog"
    CONTEXT = "context"
    RUNTIME_DATA = "runtime_data"
    REMINDER = "reminder"
    TIME = "time"
    TOOL_RESULT = "tool_result"
    STATUS = "status"
    SUBAGENT = "subagent"


ALL_SCOPES = frozenset(Scope)
CHAT_SCOPES = BOTH_CHATS

#: 登记在册、但**不经过组合器注入管道**的块：它们的文本由专门代码路径按键读取
#: （工具结果压缩、睡眠/唤醒命令、子 Agent 组装），或由编排器在管道外单独插入。
#: 这些块不参与 stage 排序，``order`` 仅用于文档/面板展示。
_CATALOG_ONLY_IDS = frozenset(
    {
        "live_chat",
        "background_notification",
        "new_member_profiles",
        "group_chat_resume",
        "member_archive_hint",
    }
)
_CATALOG_STAGES = frozenset({Stage.TOOL_RESULT, Stage.STATUS, Stage.SUBAGENT, Stage.CATALOG})


# ── 条件谓词 ──────────────────────────────────────────────────────────────────


def section_enabled(section: str) -> Requirement:
    """分区未关闭。"""

    def check(ctx: PromptContext) -> str | None:
        return None if ctx.enabled(section) else f"分区 [{section}] 已关闭"

    return check


def config_flag(path: str) -> Requirement:
    """config.toml 里的布尔开关（点路径，如 ``chat.silent_nudge_enabled``）。"""

    def check(ctx: PromptContext) -> str | None:
        target: Any = ctx.config
        for part in path.split("."):
            target = getattr(target, part, None)
            if target is None:
                return f"配置 {path} 未设置"
        return None if bool(target) else f"配置 {path} 已关闭"

    return check


def feature(name: str) -> Requirement:
    """能力开关（native_vision / agent_mode 等）。"""

    def check(ctx: PromptContext) -> str | None:
        return None if ctx.has_feature(name) else f"缺少能力 {name}"

    return check


def dynamic_present(name: str) -> Requirement:
    """运行时内容存在（为空表示本次不渲染）。"""

    def check(ctx: PromptContext) -> str | None:
        value = ctx.dynamic_value(name)
        return None if value else f"缺少运行时内容 {name}"

    return check


def dynamic_is(name: str, expected: Any) -> Requirement:
    """运行时内容等于指定值（时间块的完整/短两种变体用）。"""

    def check(ctx: PromptContext) -> str | None:
        value = ctx.dynamic_value(name)
        return None if value == expected else f"运行时内容 {name} 不匹配"

    return check


def dynamic_text(name: str) -> Callable[[PromptContext], str]:
    """把运行时文本当作块内容（没有 TOML 分区的机制文本用）。"""

    def render(ctx: PromptContext) -> str:
        return str(ctx.dynamic_value(name) or "")

    return render


# ── 块定义 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Block:
    """一个可独立启停、可独立排序的提示词块。"""

    id: str
    stage: Stage
    scopes: frozenset[Scope]
    order: int = 0
    section: str | None = None
    key: str = "template"
    #: 同分区内的其它键（如 problem_solver 的 description），供校验/面板展示
    extra_keys: tuple[str, ...] = ()
    requires: tuple[Requirement, ...] = ()
    text: Callable[[PromptContext], str] | None = None
    #: 由编排器每轮决定内容的 system 块（内容经 dynamic 传入，不交给 builder）
    per_round: bool = False
    once_per_activation: bool = False
    terminal: bool = False
    note: str = ""

    def applies_to(self, scope: Scope) -> bool:
        return scope in self.scopes

    @property
    def is_pipeline_block(self) -> bool:
        """是否由组合器按 stage 注入；False 表示文本由专门代码路径按键读取。"""
        if self.stage in _CATALOG_STAGES or self.id in _CATALOG_ONLY_IDS:
            return False
        return True

    @property
    def template_section(self) -> str | None:
        """实际读取的 TOML 分区名：显式 ``section`` 优先，否则用块 id。

        纯动态文本块（``text`` 提供者，没有 TOML 分区）返回 None。
        """
        if self.section is not None:
            return self.section
        if self.text is not None:
            return None
        return self.id


BLOCKS: tuple[Block, ...] = (
    # ── 共享片段（被主模板以占位符引用，不单独注入） ──
    Block(
        "qq_chat",
        Stage.FRAGMENT,
        CHAT_SCOPES,
        order=10,
        note="QQ 聊天共享提示词：人设 / 回复要求 / 历史一致性 / 任务处理要求",
    ),
    Block(
        "qq_chat_examples",
        Stage.FRAGMENT,
        CHAT_SCOPES,
        order=20,
        note="QQ 聊天共享的回复样例",
    ),
    # ── system 主模板 ──
    Block(
        "group_chat",
        Stage.SYSTEM_MAIN,
        frozenset({Scope.GROUP}),
        order=10,
        note="群聊 system 提示词（人设 / 回复要求 / 历史一致性 / 群信息 / 编号）",
    ),
    Block(
        "friend_chat",
        Stage.SYSTEM_MAIN,
        frozenset({Scope.PRIVATE}),
        order=10,
        note="私聊 system 提示词（人设 / 回复要求 / 历史一致性 / 编号）",
    ),
    Block(
        "live_chat",
        Stage.SYSTEM_MAIN,
        frozenset({Scope.LIVE}),
        order=10,
        note="B站直播弹幕 system 提示词（独立场景，QQ 侧不受影响）",
    ),
    # ── system 最前面的全局 cot 板块（群聊 / 私聊共用） ──
    # 总开关 prompt_optimizations.cot_enabled 管整段；子块再各有一个开关。
    Block(
        "cot_intro",
        Stage.SYSTEM_PREFIX,
        CHAT_SCOPES,
        order=10,
        requires=(config_flag("prompt_optimizations.cot_enabled"),),
        note="cot 板块开头（<cot>）：要求在该块内完成 think 思维链",
    ),
    Block(
        "cot_at_mention",
        Stage.SYSTEM_PREFIX,
        CHAT_SCOPES,
        order=20,
        requires=(
            config_flag("prompt_optimizations.cot_enabled"),
            config_flag("prompt_optimizations.at_mention_reply"),
        ),
        note="cot 子块：优先回复最新 @ 消息，并判断是否已经回复过",
    ),
    Block(
        "gentle_language",
        Stage.SYSTEM_PREFIX,
        CHAT_SCOPES,
        order=30,
        requires=(
            config_flag("prompt_optimizations.cot_enabled"),
            config_flag("prompt_optimizations.gentle_language"),
        ),
        note="cot 子块1：温和语言风格（原 chat.gentle_language_enabled 迁移到此处）",
    ),
    Block(
        "cot_avoid_bot_chat",
        Stage.SYSTEM_PREFIX,
        CHAT_SCOPES,
        order=40,
        requires=(
            config_flag("prompt_optimizations.cot_enabled"),
            config_flag("prompt_optimizations.avoid_bot_chat"),
        ),
        note="cot 子块：没有真人参与时避免与 Bot 闲聊（省部署者资金）",
    ),
    Block(
        "cot_no_bluffing",
        Stage.SYSTEM_PREFIX,
        CHAT_SCOPES,
        order=50,
        requires=(
            config_flag("prompt_optimizations.cot_enabled"),
            config_flag("prompt_optimizations.no_bluffing"),
        ),
        note="cot 子块：禁止不懂装懂，不确定就说不清楚或不回复",
    ),
    Block(
        "cot_no_game_topics",
        Stage.SYSTEM_PREFIX,
        CHAT_SCOPES,
        order=60,
        requires=(
            config_flag("prompt_optimizations.cot_enabled"),
            config_flag("prompt_optimizations.no_game_topics"),
        ),
        note="cot 子块：没人主动叫你时不参与游戏话题、不猜游戏机制",
    ),
    Block(
        "cot_no_echo_images",
        Stage.SYSTEM_PREFIX,
        CHAT_SCOPES,
        order=70,
        requires=(
            config_flag("prompt_optimizations.cot_enabled"),
            config_flag("prompt_optimizations.no_echo_images"),
        ),
        note="cot 子块：不复述别人的话再评论，不主动描述图片",
    ),
    Block(
        "cot_outro",
        Stage.SYSTEM_PREFIX,
        CHAT_SCOPES,
        order=80,
        requires=(config_flag("prompt_optimizations.cot_enabled"),),
        note="cot 板块结尾（</cot>），其后接主模板",
    ),
    # ── system 末尾追加（稳定内容） ──
    Block(
        "reply_tool_contract",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=1,
        note="agent 模式 QQ 群聊/私聊回复工具契约",
    ),
    Block(
        "friend_chat_hint",
        Stage.SYSTEM_APPEND,
        frozenset({Scope.PRIVATE}),
        order=5,
        note="私聊专属提示（追加在私聊 system 末尾）",
    ),
    Block(
        "long_task_progress",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=10,
        note="长任务过程可见性：开工先说、中途报进度",
    ),
    Block(
        "human_feel",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=20,
        note="活人感增强：禁用句式 / 不懂装懂 / 复述",
    ),
    Block(
        "stale_topic",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=30,
        note="旧消息处理：过时话题不回复，漏回先道歉",
    ),
    Block(
        "adaptive_prompt",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=40,
        text=dynamic_text("adaptive_text"),
        requires=(dynamic_present("adaptive_text"),),
        note="自适应提示词（data/自适应提示词.txt，由技能维护）",
    ),
    Block(
        "at_mention_priority",
        Stage.SYSTEM_APPEND,
        frozenset({Scope.GROUP}),
        order=50,
        requires=(dynamic_present("at_mention"),),
        per_round=True,
        note="被 @ 触发那一轮的优先级提示",
    ),
    Block(
        "skill_index",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=60,
        requires=(feature("agent_mode"), dynamic_present("skill_instructions")),
        per_round=True,
        note="Skill 操作说明（agent 模式）",
    ),
    Block(
        "tool_packages",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=70,
        requires=(feature("agent_mode"), dynamic_present("tool_package_index")),
        per_round=True,
        note="可加载工具包清单（agent 模式）",
    ),
    Block(
        "available_skills",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=80,
        requires=(feature("agent_mode"), dynamic_present("available_skills")),
        per_round=True,
        note="本轮命中的 Markdown 技能（agent 模式）",
    ),
    Block(
        "tool_restriction",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=90,
        requires=(feature("agent_mode"), dynamic_present("allowed_tools")),
        per_round=True,
        note="技能 allowed-tools 限制说明（agent 模式）",
    ),
    Block(
        "native_vision",
        Stage.SYSTEM_APPEND,
        CHAT_SCOPES,
        order=100,
        requires=(
            feature("agent_mode"),
            feature("native_vision"),
            section_enabled("native_vision"),
        ),
        per_round=True,
        note="原生视觉说明（仅主模型支持原生视觉时追加到 system 末尾）",
    ),
    # ── 每轮构建的上下文 user 块 ──
    Block(
        "group_context",
        Stage.CONTEXT,
        frozenset({Scope.GROUP}),
        order=10,
        requires=(section_enabled("group_context"),),
        note="群聊上下文：群档案 / 群友信息 / 印象（system 已消费的占位符自动去重）",
    ),
    Block(
        "friend_context",
        Stage.CONTEXT,
        frozenset({Scope.PRIVATE}),
        order=10,
        requires=(section_enabled("friend_context"),),
        note="私聊上下文：聊天对象 / 对方信息 / 印象",
    ),
    Block(
        "at_mention_wait",
        Stage.CONTEXT,
        frozenset({Scope.GROUP}),
        order=20,
        requires=(section_enabled("at_mention_wait"), dynamic_present("at_mention_wait")),
        note="被 @ 但对方没说要做什么时的等待指引",
    ),
    # ── 会话中途的动态内容 ──
    Block(
        "background_notification",
        Stage.RUNTIME_DATA,
        CHAT_SCOPES,
        order=10,
        text=dynamic_text("background_notification_text"),
        requires=(dynamic_present("background_notification_text"),),
        note="后台任务完成通知 / 跨聊天投递",
    ),
    Block(
        "new_member_profiles",
        Stage.RUNTIME_DATA,
        frozenset({Scope.GROUP}),
        order=20,
        requires=(dynamic_present("new_member_profiles_text"),),
        note="新出现的群友档案（挂起恢复 / wait 期间 / 中途新消息三处共用）",
    ),
    Block(
        "group_chat_resume",
        Stage.RUNTIME_DATA,
        frozenset({Scope.GROUP}),
        order=30,
        requires=(dynamic_present("resume_text"),),
        note="群聊挂起恢复说明",
    ),
    Block(
        "vision_fallback_notice",
        Stage.RUNTIME_DATA,
        CHAT_SCOPES,
        order=40,
        requires=(dynamic_present("vision_fallback"),),
        note="原生视觉回退说明（图片无法发送时）",
    ),
    # ── 提醒类 user 块 ──
    Block(
        "avoid_repeat",
        Stage.REMINDER,
        CHAT_SCOPES,
        order=10,
        once_per_activation=True,
        requires=(section_enabled("avoid_repeat"),),
        note="防重复提醒：每次管线激活只追加一次",
    ),
    Block(
        "silent_nudge",
        Stage.REMINDER,
        CHAT_SCOPES,
        order=20,
        requires=(section_enabled("silent_nudge"), dynamic_present("silent_nudge")),
        note="长任务沉默提醒（轮次/秒数阈值由循环判定）",
    ),
    Block(
        "no_tool_call_reminder",
        Stage.REMINDER,
        CHAT_SCOPES,
        order=30,
        requires=(dynamic_present("no_tool_call_reminder"),),
        note="模型没调用任何工具时的确认提醒",
    ),
    # ── 时间块（terminal） ──
    Block(
        "current_time",
        Stage.TIME,
        CHAT_SCOPES,
        order=10,
        requires=(section_enabled("current_time"), dynamic_is("time_variant", "full")),
        terminal=True,
        note="回复前的完整 <当前时间> user 块（长期会话首次）",
    ),
    Block(
        "current_time_short",
        Stage.TIME,
        CHAT_SCOPES,
        order=20,
        requires=(section_enabled("current_time_short"), dynamic_is("time_variant", "short")),
        terminal=True,
        note="同一激活内后续调用的短时间戳 user 块",
    ),
    # ── 工具结果压缩文案 ──
    Block(
        "tool_result_compressed",
        Stage.TOOL_RESULT,
        ALL_SCOPES,
        order=10,
        note="基础回复类工具压缩后的文案",
    ),
    Block(
        "tool_result_compressed_detail",
        Stage.TOOL_RESULT,
        ALL_SCOPES,
        order=20,
        note="其它工具压缩后的文案（含结果摘要）",
    ),
    # ── 状态 / 命令文案 ──
    Block(
        "long_reply_fallback",
        Stage.STATUS,
        ALL_SCOPES,
        order=10,
        note="回复过长/切分条数过多时的兜底回复",
    ),
    Block("wake_up", Stage.STATUS, ALL_SCOPES, order=20, note="睡眠中被 @ 唤醒的提示"),
    Block("sleep_cmd", Stage.STATUS, ALL_SCOPES, order=30, note="/sleep 且状态确实变更时交给主 Agent 的提示"),
    Block("awake_cmd", Stage.STATUS, ALL_SCOPES, order=40, note="/awake 且确实被叫醒时交给主 Agent 的提示"),
    Block(
        "member_archive_hint",
        Stage.STATUS,
        frozenset({Scope.GROUP}),
        order=50,
        note="群友记忆未注入时的按需读取提示（拼在群友信息之后）",
    ),
    # ── 子 Agent ──
    Block(
        "problem_solver",
        Stage.SUBAGENT,
        frozenset({Scope.SUBAGENT}),
        order=10,
        key="system_prompt",
        extra_keys=("description",),
        note="解题子 Agent（英文提示词）",
    ),
    Block(
        "self_heal",
        Stage.SUBAGENT,
        frozenset({Scope.SUBAGENT}),
        order=20,
        key="system_prompt",
        extra_keys=("description", "runtime"),
        note="自修复子 Agent",
    ),
    Block(
        "maintenance",
        Stage.SUBAGENT,
        frozenset({Scope.SUBAGENT}),
        order=30,
        key="system_prompt",
        note="沙箱维护子 Agent",
    ),
    # ── 统一注册的 catalog 资产（标签 / B站提示词，不经过注入管道） ──
    Block(
        "bili_comment",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="target_info",
        extra_keys=("your_memory", "target_comment_section", "comment_tree_section", "reply_guide", "up_prefix", "summary", "url", "desc", "target_detail", "replied_note"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_comment_tree",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="truncated_head",
        extra_keys=("target_marker", "replied_marker", "node_line", "content_line", "content_truncated"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_data_rule",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="template",
        extra_keys=(),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_defaults",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="bot_name",
        extra_keys=("unknown", "empty_task", "empty_message", "no_target_comment", "missing_comment", "private_peer", "live_room", "live_viewer", "live_bot_name"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_diary",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="cot",
        extra_keys=("material_tool", "rules", "requirement", "length", "truncated", "date", "material"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_history",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="empty",
        extra_keys=("truncated", "bot_line", "peer_line", "sender_fallback"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_human_feel",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="template",
        extra_keys=(),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_identity",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="block",
        extra_keys=("name", "uid", "alias"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_live",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="reply_to_rule",
        extra_keys=("danmaku_history", "scheduled_history", "room", "viewer", "room_memory", "viewer_memory", "recent_history", "frame", "pending_danmaku", "scheduled_task", "scheduled_message", "observation_task", "observation_user", "asr_wrapper", "summary_system"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_live_media",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="frame_description",
        extra_keys=(),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_private",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="peer",
        extra_keys=("peer_with_remark", "target", "impression", "memory", "history_section", "current_message"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_profile",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="section",
        extra_keys=("entry", "uname", "uid", "line"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_profile_labels",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="remark",
        extra_keys=("profile", "known_gender", "avatar_analysis", "bilibili_memory", "qq_memory"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_reply_requirements",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="template",
        extra_keys=(),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_reply_tool_rule",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="template",
        extra_keys=(),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_scene",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="comment",
        extra_keys=("private", "general", "live"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_shared",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="current_time",
        extra_keys=("related_video",),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "bili_task",
        Stage.CATALOG,
        frozenset({Scope.LIVE}),
        key="cross_chat",
        extra_keys=("background", "instruction"),
        note="B站提示词（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "label_keyword_reaction",
        Stage.CATALOG,
        ALL_SCOPES,
        key="entry",
        extra_keys=(),
        note="内部提示词标签（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "label_message_meta",
        Stage.CATALOG,
        ALL_SCOPES,
        key="line",
        extra_keys=("age_just_now", "age_minutes", "age_hours", "age_days", "replied_prefix", "all_new", "new_content_open", "new_content_close", "previous_content"),
        note="内部提示词标签（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "label_skills",
        Stage.CATALOG,
        ALL_SCOPES,
        key="item",
        extra_keys=(),
        note="内部提示词标签（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "label_tool_packages",
        Stage.CATALOG,
        ALL_SCOPES,
        key="entry",
        extra_keys=(),
        note="内部提示词标签（统一注册）；数据在 prompts.toml",
    ),
    Block(
        "label_vision_context",
        Stage.CATALOG,
        ALL_SCOPES,
        key="intro",
        extra_keys=("sender", "message_number", "message_id", "image_index", "fallback_index", "label_separator", "mode_default", "mode_active", "default_label", "tool_label", "tool_prefix", "not_loaded", "load_failed"),
        note="内部提示词标签（统一注册）；数据在 prompts.toml",
    ),
)


def block_by_id(block_id: str) -> Block:
    """按 id 取块；不存在时抛 KeyError（拼错应当尽早暴露）。"""
    for block in BLOCKS:
        if block.id == block_id:
            return block
    raise KeyError(f"未知提示词块: {block_id}")


def blocks_for(stage: Stage, scope: Scope) -> tuple[Block, ...]:
    """取某阶段、某作用域下按 order 排好序的块。"""
    return tuple(
        sorted(
            (block for block in BLOCKS if block.stage is stage and block.applies_to(scope)),
            key=lambda block: (block.order, block.id),
        )
    )


def known_sections() -> tuple[str, ...]:
    """全部登记了 TOML 分区的分区名（``KNOWN_SECTIONS`` 的唯一来源）。"""
    return tuple(section for block in BLOCKS if (section := block.template_section) is not None)


def validate_blocks() -> list[str]:
    """注册表自检，返回问题列表（空列表表示通过）。

    只做不依赖外部文件的检查；与 ``templates/prompts.toml`` 的一致性由测试校验。
    """
    problems: list[str] = []
    seen: dict[str, Block] = {}
    for block in BLOCKS:
        if block.id in seen:
            problems.append(f"块 id 重复: {block.id}")
        seen[block.id] = block
        if block.stage is not Stage.SYSTEM_MAIN and block.template_section is None and block.text is None:
            problems.append(f"{block.id}: 既没有 TOML 分区也没有 text 提供者")
        if not block.scopes:
            problems.append(f"{block.id}: scopes 不能为空")
    # per_round 块由编排器在 builder 之后追加；若 order 落在稳定追加块中间会静默乱序
    stable_append = [block for block in BLOCKS if block.stage is Stage.SYSTEM_APPEND and not block.per_round]
    max_stable_order = max((block.order for block in stable_append), default=-1)
    for block in BLOCKS:
        if block.per_round and block.stage is Stage.SYSTEM_APPEND and block.order <= max_stable_order:
            problems.append(
                f"{block.id}: per_round 块的 order({block.order}) 必须大于所有稳定追加块(最大 {max_stable_order})"
            )
    for index, left in enumerate(BLOCKS):
        for right in BLOCKS[index + 1 :]:
            if (
                left.stage is right.stage
                and left.stage is not Stage.CATALOG
                and left.order == right.order
                and (left.scopes & right.scopes)
            ):
                problems.append(f"同一阶段同一作用域 order 冲突: {left.id} / {right.id} ({left.stage.value})")
    return problems

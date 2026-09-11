"""提示词文件存储:默认提示词(程序内置)与自定义提示词(用户)的合并读取与同步。

目录结构(data 目录下):
    prompts/
        README.md            使用说明(首次自动生成)
        default/prompts.toml 默认提示词,每次启动/热重载由内置模板覆盖同步
        custom/prompts.toml  自定义提示词,默认为空;写入的分区/键覆盖默认值

合并规则(满足跨版本升级):
    - 自定义文件中未出现的分区自动使用默认值
    - 升级后新增的分区(如新子Agent的提示词)会自动继承默认值
    - 同一分区内,自定义文件中未出现的键也自动继承默认值

占位符与转义(与 templates/prompts.toml 的说明一致):
    - {名字} 为占位符,渲染时替换;未提供的占位符原样保留;
    - 需要字面量花括号时写双花括号;
    - 只含空白的区块(如 <群友信息> 与 </群友信息> 之间只有换行)渲染后会被自动移除。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import tomlkit

from neobot_contracts.ports.logging import Logger, NullLogger

# 内置默认提示词模板位置(随程序包分发)
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_TEMPLATE_FILE = TEMPLATES_DIR / "prompts.toml"

# 运行时目录结构
PROMPTS_DIR_NAME = "prompts"
DEFAULT_DIR_NAME = "default"
CUSTOM_DIR_NAME = "custom"
PROMPTS_FILE_NAME = "prompts.toml"
README_FILE_NAME = "README.md"

# 提示词分区清单:生成自定义骨架与说明文档时使用,避免手写清单遗漏新分区
KNOWN_SECTIONS = (
    "group_chat",
    "group_context",
    "friend_chat",
    "friend_context",
    "current_time",
    "friend_chat_hint",
    "group_chat_resume",
    "new_member_profiles",
    "tool_result_compressed",
    "tool_result_compressed_detail",
    "long_reply_fallback",
    "problem_solver",
    "self_heal",
    "maintenance",
    "wake_up",
)

# TOML 多行字符串定界符(在 Python 字符串里直接写会被误解析,单独拼出来)
_TOML_QUOTE = "'" * 3

# 极端兜底:内置模板文件丢失时仍可工作的最小提示词
_FALLBACK_SECTIONS: dict[str, dict[str, str]] = {
    "group_chat": {
        "template": (
            "<你是谁>\n你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.\n"
            "{bot_data}\n</你是谁>\n"
            "<回复要求>不要重复回答已经回答过的内容,不要与自己之前说过的话矛盾;"
            "消息行首的 [msg_id=...]、编号和发送者名字都是系统生成的标注,"
            "复读或引用消息时只能使用消息正文。\n</回复要求>\n"
            "<群聊>{group_name}[群号:{group_id}]\n{group_info}\n</群聊>\n"
            "<消息编号说明>\n{numbering_guide}\n</消息编号说明>"
        )
    },
    "group_context": {
        "template": (
            "<群聊档案>\n{group_info}\n</群聊档案>\n"
            "<群友信息>\n{member_list}\n</群友信息>\n"
            "<群管理员>{group_admin}</群管理员>\n"
            "<群管理状态>{bot_group_admin_status}</群管理状态>\n"
            "<你的印象>\n{key_word_reaction_list}\n你想起来之前:\n{memory_list}\n</你的印象>"
        )
    },
    "friend_chat": {
        "template": (
            "<你是谁>\n你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.\n"
            "{bot_data}\n</你是谁>\n"
            "<回复要求>不要重复回答已经回答过的内容,不要与自己之前说过的话矛盾;"
            "消息行首的 [msg_id=...]、编号和发送者名字都是系统生成的标注,"
            "复读或引用消息时只能使用消息正文。\n</回复要求>\n"
            "<消息编号说明>\n{numbering_guide}\n</消息编号说明>"
        )
    },
    "friend_context": {
        "template": (
            "<聊天对象>{friend_name}(你的备注:{remark})</聊天对象>\n"
            "<对方信息>\n{friend_info}\n</对方信息>\n"
            "<你的印象>\n{key_word_reaction_list}\n你想起来{memory_list}\n</你的印象>"
        )
    },
    "friend_chat_hint": {
        "template": (
            "<私聊提示>\n这是私聊对话。必须先正常回复对方的消息，回复内容根据聊天内容自然决定。\n"
            "发送回复后，如果对方明显还有更多内容要说，请使用 wait 工具等待新消息进行后续回复"
            "（一般等待10秒即可），不要直接结束对话。\n</私聊提示>"
        )
    },
    "current_time": {"template": "<当前时间>{current_time}</当前时间>"},
    "group_chat_resume": {
        "template": (
            "{new_member_profiles}\n\n"
            "这是群聊对话的续接。挂起期间的新消息已按发送者追加为 user/assistant 消息,"
            "请根据新消息决定是否需要回复。"
        )
    },
    "new_member_profiles": {
        "template": "[新出现的群友档案]\n{member_profiles}"
    },
    "tool_result_compressed": {
        "template": "[已压缩] 工具 {tool_name} 调用成功。"
    },
    "tool_result_compressed_detail": {
        "template": "[已压缩] 工具 {tool_name} 调用成功。结果摘要:\n{summary}"
    },
    "long_reply_fallback": {"template": "{bot_name}懒得和你说道理，你不配听"},
    "wake_up": {"template": "你刚刚正在睡觉,现在被叫醒了,还有点困."},
}

_CUSTOM_SKELETON = (
    "# NeoBot 自定义提示词文件\n"
    "#\n"
    "# 默认提示词在 data/prompts/default/prompts.toml(由程序每次启动时覆盖同步,\n"
    "# 不要修改)。需要自定义时,把要修改的分区整体复制到这里再修改即可;\n"
    "# 未出现在本文件中的分区自动使用默认提示词。\n"
    "#\n"
    "# 可用分区(详见 default/prompts.toml 中的说明与占位符列表):\n"
    "#   group_chat / group_context / friend_chat / friend_context\n"
    "#   current_time / group_chat_resume / new_member_profiles\n"
    "#   tool_result_compressed / tool_result_compressed_detail\n"
    "#   long_reply_fallback / problem_solver / self_heal / maintenance / wake_up\n"
    "#\n"
    "# 占位符写作花括号包住的名字,渲染时替换;需要输出字面量花括号时写成双层花括号。\n"
    "# 只含空白的区块(如群友信息标签之间只有换行)会在渲染后被自动删除。\n"
    "#\n"
    "# 示例(取消注释后修改):\n"
    "#\n"
    "# [group_chat]\n"
    f"# template = {_TOML_QUOTE}\n"
    "# 你是一个性格傲娇的猫娘...\n"
    "# 群名:{group_name},群友:{member_list}\n"
    "# 需要输出大括号时这样写:{{msg_id=123}}\n"
    f"# {_TOML_QUOTE}\n"
)

_README_TEXT = (
    "# 提示词目录说明\n"
    "\n"
    "本目录用于维护 NeoBot 的提示词文件(独立于 config.toml)。\n"
    "\n"
    "## 结构\n"
    "\n"
    "- default/prompts.toml — 默认提示词。由程序内置模板在每次启动 / config.reload\n"
    "  时自动覆盖同步,请不要手动修改(手动修改会在下次启动时被覆盖)。\n"
    "- custom/prompts.toml — 自定义提示词。默认为空(程序首次运行自动创建)。\n"
    "  需要自定义某个提示词时,把对应分区从默认文件复制到本文件再修改。\n"
    "- README.md — 本说明文件。\n"
    "\n"
    "## 消息结构\n"
    "\n"
    "聊天记录以真实的 user/assistant 消息追加在 system 提示词之后,而不是内嵌在\n"
    "system 里。一次模型调用的消息顺序是:\n"
    "\n"
    "1. system — [group_chat] / [friend_chat] 模板渲染出的稳定提示词;\n"
    "2. user — [group_context] / [friend_context] 模板渲染出的本轮上下文\n"
    "   (群友信息、对方档案、印象等);\n"
    "3. user / assistant — 按发送者拆分的聊天记录(bot 自己的发言是 assistant);\n"
    "4. user — [current_time] 模板渲染出的当前时间块,每次调用模型前追加一条"
    "(历史时间块保留,不做清理)。\n"
    "\n"
    "## 占位符与转义\n"
    "\n"
    "1. 占位符写作花括号包住的名字,未提供值的占位符会原样保留,便于发现写错的占位符。\n"
    "2. 需要输出字面量花括号时写成双层花括号:左双层渲染为左花括号,右双层渲染为右花括号。\n"
    "3. 只含空白的区块(如群友信息标签之间只有换行)渲染后会被自动删除,因此可以\n"
    "   放心把可选区块写进模板。\n"
    "4. 模板含畸形花括号时会降级为只替换已知占位符,不会导致整轮回复失败。\n"
    "5. 把 {member_list} 之类的占位符写进 [group_chat],内容就留在 system 里,\n"
    "   并且不再重复出现在 [group_context] 中(反之亦然)。\n"
    "\n"
    "## 合并规则\n"
    "\n"
    "1. 自定义文件中出现的分区/键覆盖默认值;\n"
    "2. 未在自定义文件中出现的分区/键自动使用默认值;\n"
    "3. 程序升级后新增的提示词分区(例如新的子Agent提示词)会自动继承默认值,\n"
    "   无需手动处理。\n"
    "\n"
    "## 修改后如何生效\n"
    "\n"
    "提示词按文件修改时间自动感知(每次构建 prompt 时校验),无需重启;\n"
    "如需重新同步默认提示词,执行 config.reload 命令即可。\n"
)


def _parse_sections(path: Path, logger: Logger | None = None) -> dict[str, dict[str, Any]]:
    """解析 TOML 提示词文件为 {分区名: {键: 值}};文件缺失或损坏时返回空字典。"""
    if not path.is_file():
        return {}
    log = logger or NullLogger()
    try:
        # 兼容记事本保存的 UTF-8 BOM;非 UTF-8 时尝试 GBK(Windows 常见)
        raw = path.read_text("utf-8-sig")
    except UnicodeDecodeError:
        try:
            raw = path.read_text("gbk")
        except UnicodeDecodeError as exc:
            log.warning(f"提示词文件编码无法识别(utf-8/gbk 均失败),按默认处理: {path}: {exc}")
            return {}
    try:
        doc = tomlkit.parse(raw).unwrap()
    except Exception as exc:
        log.warning(f"提示词文件解析失败(将使用默认提示词): {path}: {exc}")
        return {}
    sections: dict[str, dict[str, Any]] = {}
    for key, value in doc.items():
        if key == "version":
            continue
        if isinstance(value, dict):
            sections[str(key)] = value
        else:
            # 根级非分区键(如误写的 template = "..."):静默丢弃会让用户
            # 以为自定义已生效,必须告警
            log.warning(
                f"提示词文件 {path} 的根级键 {key!r} 不是分区(应为 [分区名] 下的键),已忽略"
            )
    return sections


def parse_prompt_file(
    path: Path, logger: Logger | None = None
) -> dict[str, dict[str, Any]]:
    """解析一个提示词文件为 {分区名: {键: 值}}（面板等外部读者用）。

    文件缺失、编码无法识别或 TOML 损坏时返回空字典,不抛异常。
    """
    return _parse_sections(Path(path), logger)


def get_template_value(
    store: "PromptStore | None",
    section: str,
    sub: str = "template",
    *,
    default: str = "",
) -> str:
    """读取分区键:优先文件(自定义覆盖默认),缺失时回退到内置兜底模板。

    这是 builder 与子 Agent 读取提示词的统一入口,保证"文件 -> 内置兜底"的
    降级顺序不因调用点不同而分叉。
    """
    if store is not None:
        value = store.get(section, sub, default="")
        if value:
            return value
    return fallback_template(section, sub, default)


class PromptStore:
    """提示词存储:读取 data/prompts 下的默认与自定义提示词并按键合并。"""

    def __init__(self, data_dir: Path, logger: Logger | None = None) -> None:
        self._logger = logger or NullLogger()
        prompts_dir = Path(data_dir) / PROMPTS_DIR_NAME
        self.default_file = prompts_dir / DEFAULT_DIR_NAME / PROMPTS_FILE_NAME
        self.custom_file = prompts_dir / CUSTOM_DIR_NAME / PROMPTS_FILE_NAME
        self._cache: dict[str, dict[str, Any]] | None = None
        self._cache_signature: tuple[Any, Any] = (None, None)

    # ── 内部:带 mtime 缓存的加载 ──

    def _file_signature(self, path: Path) -> tuple[Any, Any] | None:
        try:
            stat = path.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def _load_default_sections(self) -> dict[str, dict[str, Any]]:
        """读取默认提示词分区:运行时文件 -> 内置模板文件 -> 极端兜底。"""
        if self.default_file.is_file():
            sections = _parse_sections(self.default_file, self._logger)
            if sections:
                return sections
        if DEFAULT_TEMPLATE_FILE.is_file():
            sections = _parse_sections(DEFAULT_TEMPLATE_FILE, self._logger)
            if sections:
                return sections
        return {key: dict(value) for key, value in _FALLBACK_SECTIONS.items()}

    def _load_merged(self) -> dict[str, dict[str, Any]]:
        signature = (
            self._file_signature(self.default_file),
            self._file_signature(self.custom_file),
        )
        if self._cache is not None and signature == self._cache_signature:
            return self._cache

        merged = self._load_default_sections()
        custom = _parse_sections(self.custom_file, self._logger)
        for key in custom:
            # 拼错的分区名不会生效,静默忽略会让用户以为自定义已生效
            if key not in KNOWN_SECTIONS and key not in merged:
                self._logger.warning(
                    f"自定义提示词中的分区 [{key}] 不是已知分区,已忽略(可用分区见 "
                    f"data/prompts/default/prompts.toml)"
                )
        for key, section in custom.items():
            base = merged.get(key)
            if isinstance(base, dict) and isinstance(section, dict):
                merged_section = dict(base)
                for sub_key, sub_value in section.items():
                    # 空白/None 视为"未自定义":不覆盖默认值,继承默认模板
                    if sub_value is None:
                        continue
                    if isinstance(sub_value, str) and not sub_value.strip():
                        continue
                    merged_section[sub_key] = sub_value
                merged[key] = merged_section
            else:
                merged[key] = dict(section)

        self._cache = merged
        self._cache_signature = signature
        return merged

    # ── 对外接口 ──

    def reload(self) -> None:
        """清空缓存,强制重新读取文件(热重载用)。"""
        self._cache = None
        self._cache_signature = (None, None)

    def sections(self) -> dict[str, dict[str, Any]]:
        """返回全部有效分区(默认与自定义合并后)。"""
        return {key: dict(value) for key, value in self._load_merged().items()}

    def get_section(self, key: str) -> dict[str, Any] | None:
        """返回单个分区(合并后);不存在时返回 None。"""
        section = self._load_merged().get(key)
        return dict(section) if section is not None else None

    def get(self, key: str, sub: str = "template", default: str = "") -> str:
        """读取分区内某个键的字符串值,缺失/空白时返回 default。

        空白值视为"未自定义",继承默认(与"缺省继承默认"的合并语义一致)。
        """
        section = self.get_section(key)
        if section is None:
            return default
        value = section.get(sub)
        if value is None:
            return default
        if not isinstance(value, str):
            self._logger.warning(
                f"提示词分区 [{key}].{sub} 的值不是字符串(实际 {type(value).__name__}),已忽略"
            )
            return default
        stripped = value.strip()
        if not stripped:
            return default
        return stripped

    def template(self, key: str, default: str = "") -> str:
        """读取分区的 template 键(常用快捷方式)。"""
        return self.get(key, "template", default)

    def template_or_fallback(self, key: str, sub: str = "template") -> str:
        """读取分区键,缺失时回退到内置兜底模板(不返回空字符串)。"""
        return get_template_value(self, key, sub)

    def sub_section(self, key: str, sub: str) -> dict[str, Any]:
        """读取分区内的子表(如 [problem_solver.runtime]);不存在时返回空字典。"""
        section = self.get_section(key)
        if section is None:
            return {}
        value = section.get(sub)
        if not isinstance(value, dict):
            return {}
        return dict(value)

    def enabled(self, key: str, default: bool = True) -> bool:
        """分区是否启用:分区内 enabled = false 可关闭该区块。

        未写 enabled 时返回 default;写成字符串(如 "false"/"否")也按布尔语义解析,
        避免用户把布尔值写成字符串后自定义静默失效。
        """
        section = self.get_section(key)
        if section is None:
            return default
        value = section.get("enabled")
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("false", "0", "no", "off", "否", "关闭"):
                return False
            if text in ("true", "1", "yes", "on", "是", "开启"):
                return True
        self._logger.warning(
            f"提示词分区 [{key}].enabled 的值无法解析为布尔(实际 {value!r}),按启用处理"
        )
        return default


def fallback_template(key: str, sub: str = "template", default: str = "") -> str:
    """极端兜底:内置模板文件与运行时文件都不可用时使用的最小提示词。"""
    section = _FALLBACK_SECTIONS.get(key)
    if section is None:
        return default
    value = section.get(sub)
    if value is None:
        return default
    return str(value).strip() if isinstance(value, str) else str(value)


def sync_default_prompts(data_dir: Path, logger: Logger | None = None) -> None:
    """同步默认提示词到 data/prompts/,并初始化自定义提示词文件(触发函数)。

    - 内置模板 -> data/prompts/default/prompts.toml(始终覆盖,保证默认值更新)
    - data/prompts/custom/prompts.toml 不存在时创建(默认为空,不覆盖已有内容)
    - data/prompts/README.md 不存在时创建

    该函数在每次启动与 config.reload 时调用;也可单独调用以重新同步。
    同步是尽力而为:目录不可写/文件被锁定时降级为警告,不阻断启动。
    """
    log = logger or NullLogger()
    try:
        prompts_dir = Path(data_dir) / PROMPTS_DIR_NAME
        default_dir = prompts_dir / DEFAULT_DIR_NAME
        custom_dir = prompts_dir / CUSTOM_DIR_NAME
        default_dir.mkdir(parents=True, exist_ok=True)
        custom_dir.mkdir(parents=True, exist_ok=True)

        if DEFAULT_TEMPLATE_FILE.is_file():
            dest = default_dir / PROMPTS_FILE_NAME
            # 临时文件 + 原子替换,避免并发读取到半截文件
            tmp = dest.with_name(dest.name + ".tmp")
            try:
                shutil.copy2(DEFAULT_TEMPLATE_FILE, tmp)
                tmp.replace(dest)
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
            log.info(f"默认提示词已同步: {dest}")
        else:
            log.warning(f"内置默认提示词文件不存在,跳过同步: {DEFAULT_TEMPLATE_FILE}")

        custom_file = custom_dir / PROMPTS_FILE_NAME
        if not custom_file.exists():
            custom_file.write_text(_CUSTOM_SKELETON, encoding="utf-8")
            log.info(f"已创建自定义提示词文件(默认为空): {custom_file}")

        readme = prompts_dir / README_FILE_NAME
        if not readme.exists():
            readme.write_text(_README_TEXT, encoding="utf-8")
    except Exception as exc:
        log.warning(f"默认提示词同步失败(读取侧有兜底,不影响启动): {exc}")

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

# 极端兜底:内置模板文件丢失时仍可工作的最小提示词
_FALLBACK_SECTIONS: dict[str, dict[str, str]] = {
    "group_chat": {
        "template": (
            "<你是谁>\n你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.\n"
            "{bot_data}\n</你是谁>\n"
            "<当前时间>{current_time}</当前时间>\n"
            "<群聊>{group_name}[群号:{group_id}]\n{group_info}\n</群聊>\n"
            "<消息编号说明>\n{numbering_guide}\n</消息编号说明>\n"
            "<群友信息>\n{member_list}\n</群友信息>\n"
            "<你的印象>\n{key_word_reaction_list}\n你想起来之前:\n{memory_list}\n</你的印象>"
        )
    },
    "friend_chat": {
        "template": (
            "<你是谁>\n你的名字是{bot_name},你的QQ号是{bot_account}{other_name}.\n"
            "{bot_data}\n</你是谁>\n"
            "<当前时间>{current_time}</当前时间>\n"
            "<聊天对象>{friend_name}(你的备注:{remark})</聊天对象>\n"
            "<对方信息>\n{friend_info}\n</对方信息>\n"
            "<你的记忆>\n你想起来{memory_list}\n</你的记忆>\n"
            "<消息编号说明>\n{numbering_guide}\n</消息编号说明>"
        )
    },
    "group_chat_resume": {
        "template": (
            "{new_member_profiles}\n\n<当前时间>{current_time}</当前时间>\n\n"
            "这是群聊对话的续接。请根据新消息决定是否需要回复。"
        )
    },
    "long_reply_fallback": {"template": "{bot_name}懒得和你说道理，你不配听"},
}

_CUSTOM_SKELETON = """\
# NeoBot 自定义提示词文件
#
# 默认提示词在 data/prompts/default/prompts.toml(由程序每次启动时覆盖同步,
# 不要修改)。需要自定义时,把要修改的分区整体复制到这里再修改即可;
# 未出现在本文件中的分区自动使用默认提示词。
#
# 可用分区:group_chat / friend_chat / group_chat_resume / long_reply_fallback
#          problem_solver / self_heal / maintenance
# 示例(取消注释后修改):
#
# [group_chat]
# template = '''
# 你是一个性格傲娇的猫娘...
# '''
"""

_README_TEXT = """\
# 提示词目录说明

本目录用于维护 NeoBot 的提示词文件(独立于 config.toml)。

## 结构

- `default/prompts.toml` — 默认提示词。由程序内置模板在每次启动 / config.reload
  时自动覆盖同步,请不要手动修改(手动修改会在下次启动时被覆盖)。
- `custom/prompts.toml` — 自定义提示词。默认为空(程序首次运行自动创建)。
  需要自定义某个提示词时,把对应分区从 default/prompts.toml 复制到本文件再修改。
- `README.md` — 本说明文件。

## 合并规则

1. 自定义文件中出现的分区/键覆盖默认值;
2. 未在自定义文件中出现的分区/键自动使用默认值;
3. 程序升级后新增的提示词分区(例如新的子Agent提示词)会自动继承默认值,
   无需手动处理。

## 修改后如何生效

提示词按文件修改时间自动感知(每次构建 prompt 时校验),无需重启;
如需重新同步默认提示词,执行 `config.reload` 命令即可。
"""


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
                f"提示词文件 {path} 的根级键 '{key}' 不是分区(应为 [分区名] 下的键),已忽略"
            )
    return sections


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

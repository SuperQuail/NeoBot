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

内置资源文件(templates/ 下,随包分发):
    prompts.toml           默认提示词
    fallback.toml          内置模板整体丢失时的最小兜底提示词
    custom_skeleton.txt    首次生成 custom/prompts.toml 的骨架文本
    README.md              首次生成 data/prompts/README.md 的说明全文

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

from neobot_app.prompt.blocks import known_sections as _known_sections

# 内置默认提示词模板位置(随程序包分发)
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_TEMPLATE_FILE = TEMPLATES_DIR / "prompts.toml"
FALLBACK_TEMPLATE_FILE = TEMPLATES_DIR / "fallback.toml"
# 骨架文本用 {sections} 占位，同步时替换成按注册表生成的分区清单
CUSTOM_SKELETON_FILE = TEMPLATES_DIR / "custom_skeleton.txt"
README_TEMPLATE_FILE = TEMPLATES_DIR / "README.md"

# 运行时目录结构
PROMPTS_DIR_NAME = "prompts"
DEFAULT_DIR_NAME = "default"
CUSTOM_DIR_NAME = "custom"
PROMPTS_FILE_NAME = "prompts.toml"
README_FILE_NAME = "README.md"

# 提示词分区清单由注册表派生（prompt/blocks.py 是唯一真相），避免手工清单漂移。
KNOWN_SECTIONS: tuple[str, ...] = _known_sections()


def _skeleton_section_lines() -> str:
    """把 KNOWN_SECTIONS 按每行 3 个排版成骨架注释（新增分区自动出现）。"""
    rows = [
        " / ".join(KNOWN_SECTIONS[index : index + 3])
        for index in range(0, len(KNOWN_SECTIONS), 3)
    ]
    return "\n".join(f"#   {row}" for row in rows)


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


def _load_fallback_sections() -> dict[str, dict[str, Any]]:
    """读取随包分发的最小兜底提示词(缺失时为空,由调用方回退 default)。"""
    return {key: dict(value) for key, value in _parse_sections(FALLBACK_TEMPLATE_FILE).items()}


#: 极端兜底:内置模板文件丢失时仍可工作的最小提示词
_FALLBACK_SECTIONS: dict[str, dict[str, Any]] = _load_fallback_sections()


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
        self._warned_fields: set[tuple[str, str]] = set()

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

        self._warned_fields.clear()
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

    def default_sections(self) -> dict[str, dict[str, Any]]:
        """返回默认分区(忽略自定义覆盖),面板/文档等外部读者用。"""
        return {key: dict(value) for key, value in self._load_default_sections().items()}

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
            self._warn_field_once(key, sub, "应为字符串，已使用默认值")
            return default
        stripped = value.strip()
        if not stripped:
            return default
        return stripped

    def _warn_field_once(self, key: str, sub: str, reason: str) -> None:
        field = (key, sub)
        if field in self._warned_fields:
            return
        self._warned_fields.add(field)
        self._logger.warning("提示词配置项无效", section=key, field=sub, reason=reason)

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
        self._warn_field_once(key, "enabled", f"无法解析为布尔，已使用默认值 {default}")
        return default


def fallback_template(key: str, sub: str = "template", default: str = "") -> str:
    """极端兜底:内置模板文件与运行时文件都不可用时使用的最小提示词(templates/fallback.toml)。"""
    value: Any = _FALLBACK_SECTIONS.get(key)
    if value is None:
        return default
    for part in str(sub).split("."):
        value = value.get(part) if isinstance(value, dict) else None
        if value is None:
            return default
    return str(value).strip() if isinstance(value, str) else str(value)


#: 内置模板文件的解析缓存：(mtime_ns, size) -> {分区: {键: 值}}
_PACKAGED_CACHE: tuple[tuple[int, int] | None, dict[str, dict[str, Any]]] = (None, {})


def packaged_template(key: str, sub: str = "template", default: str = "") -> str:
    """读取随包分发的内置模板分区（无 store 时的兜底，如面板/测试替身）。

    读取顺序：内置 templates/prompts.toml -> templates/fallback.toml -> default。
    结果按文件 mtime/size 缓存，避免每次渲染都解析 TOML。
    """
    global _PACKAGED_CACHE
    signature = None
    try:
        stat = DEFAULT_TEMPLATE_FILE.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        pass
    cached_signature, cached_sections = _PACKAGED_CACHE
    if signature is not None and cached_signature != signature:
        cached_sections = {
            section: dict(value)
            for section, value in _parse_sections(DEFAULT_TEMPLATE_FILE).items()
        }
        _PACKAGED_CACHE = (signature, cached_sections)
    value: Any = cached_sections.get(key, {})
    for part in str(sub).split("."):
        value = value.get(part) if isinstance(value, dict) else None
        if value is None:
            break
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback_template(key, sub, default)


def _atomic_write_text(path: Path, text: str) -> None:
    """临时文件 + 原子替换,避免并发读取到半截文件。"""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


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
            log.info("默认提示词已同步", path=str(dest))
        else:
            log.warning(f"内置默认提示词文件不存在,跳过同步: {DEFAULT_TEMPLATE_FILE}")

        custom_file = custom_dir / PROMPTS_FILE_NAME
        if not custom_file.exists():
            try:
                skeleton = CUSTOM_SKELETON_FILE.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning(f"内置自定义提示词骨架缺失,跳过创建: {CUSTOM_SKELETON_FILE}: {exc}")
            else:
                _atomic_write_text(custom_file, skeleton.replace("{sections}", _skeleton_section_lines()))
                log.info(f"已创建自定义提示词文件(默认为空): {custom_file}")

        readme = prompts_dir / README_FILE_NAME
        if not readme.exists():
            try:
                readme_text = README_TEMPLATE_FILE.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning(f"内置提示词说明文件缺失,跳过创建: {README_TEMPLATE_FILE}: {exc}")
            else:
                _atomic_write_text(readme, readme_text)
    except Exception as exc:
        log.warning(f"默认提示词同步失败(读取侧有兜底,不影响启动): {exc}")

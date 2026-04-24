"""EmojiService — 表情包扫描、解析、编号与提示词生成"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.message.image_pipeline import prepare_local_image

if TYPE_CHECKING:
    from neobot_chat.providers.base import Provider
    from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class EmojiEntry:
    """内存中的表情包条目"""
    file_name: str
    file_path: Path
    analysis_text: str


class EmojiService:
    """管理表情包的扫描、解析、编号与提示词生成"""

    _PARSE_PROMPT = (
        "请用中文描述这张表情包图片的内容，包括画面中的文字、人物、动作、情绪等。"
        "尽可能简洁，最多50个字。"
    )
    _EMOJI_DIR_NAME = "emoji"
    _REFRESH_INTERVAL_SECONDS = 300

    def __init__(
        self,
        *,
        data_dir: Path,
        uow_factory: UnitOfWorkFactory,
        vision_provider: Provider | None = None,
        max_concurrency: int = 20,
        logger: Logger | None = None,
    ) -> None:
        self._emoji_dir = data_dir / self._EMOJI_DIR_NAME
        self._uow_factory = uow_factory
        self._vision_provider = vision_provider
        self._max_concurrency = max_concurrency
        self._logger = logger or NullLogger()
        self._entries: dict[int, EmojiEntry] = {}
        self._next_number: int = 1
        self._refresh_task: asyncio.Task[None] | None = None

    @property
    def emoji_count(self) -> int:
        return len(self._entries)

    def get_entry(self, number: int) -> EmojiEntry | None:
        return self._entries.get(number)

    def build_prompt_text(self) -> str:
        """构建表情包提示词文本，格式为 [编号]: [表情包：描述]"""
        if not self._entries:
            return ""
        lines: list[str] = []
        for number in sorted(self._entries):
            entry = self._entries[number]
            lines.append(f"[{number}]: [表情包：{entry.analysis_text}]")
        return "\n".join(lines)

    async def start(self) -> None:
        """启动时扫描表情包文件夹"""
        self._emoji_dir.mkdir(parents=True, exist_ok=True)
        await self._scan_folder()
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    async def _scan_folder(self) -> None:
        """扫描表情包文件夹，对比数据库后进行并发解析"""
        if not self._emoji_dir.exists():
            self._logger.warning(f"表情包目录不存在: {self._emoji_dir}")
            return

        image_files = self._list_image_files()
        if not image_files:
            self._logger.info("表情包目录为空")
            self._entries.clear()
            return

        # 计算所有文件的哈希（仅一次）
        hash_to_path: dict[str, Path] = {}
        path_to_hash: dict[Path, str] = {}
        for file_path in image_files:
            try:
                prepared = prepare_local_image(file_path)
                hash_to_path[prepared.file_hash] = file_path
                path_to_hash[file_path] = prepared.file_hash
            except Exception as exc:
                self._logger.warning(f"无法读取表情包文件 {file_path.name}: {exc}")

        if not hash_to_path:
            return

        # 查询数据库中已有的解析结果
        existing: dict[str, str] = {}  # hash -> analysis_text
        try:
            async with self._uow_factory() as uow:
                for file_hash in hash_to_path:
                    record = await uow.emojis.get_by_hash(file_hash)
                    if record is not None and record.analysis_text:
                        existing[file_hash] = record.analysis_text
        except Exception as exc:
            self._logger.error(f"查询表情包数据库失败: {exc}")

        # 找出需要解析的新文件
        to_parse: list[tuple[str, Path]] = []
        for file_hash, file_path in hash_to_path.items():
            if file_hash not in existing:
                to_parse.append((file_hash, file_path))

        if to_parse:
            self._logger.info(f"发现 {len(to_parse)} 个新表情包，开始并发解析")
            new_results = await self._parse_batch(to_parse)
            # 存入数据库
            try:
                async with self._uow_factory() as uow:
                    for file_hash, file_path, analysis_text in new_results:
                        prepared = prepare_local_image(file_path)
                        await uow.emojis.set(
                            file_hash,
                            file_name=file_path.name,
                            file_path=str(file_path.relative_to(self._emoji_dir)),
                            mime_type=prepared.mime_type,
                            original_width=prepared.original_width,
                            original_height=prepared.original_height,
                            analysis_text=analysis_text,
                        )
                        existing[file_hash] = analysis_text
                    await uow.commit()
            except Exception as exc:
                self._logger.error(f"保存表情包解析结果失败: {exc}")

        # 重建编号映射（传入 path->hash 避免重复计算）
        self._rebuild_mapping(image_files, existing, path_to_hash)

    async def _parse_batch(
        self,
        items: list[tuple[str, Path]],
    ) -> list[tuple[str, Path, str]]:
        """并发解析一批图片，返回 (hash, path, analysis_text) 列表"""
        if not items or self._vision_provider is None:
            return [(h, p, "[未配置视觉模型]") for h, p in items]

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def parse_one(file_hash: str, file_path: Path) -> tuple[str, Path, str]:
            async with semaphore:
                try:
                    prepared = prepare_local_image(file_path)
                    import base64
                    b64 = base64.b64encode(prepared.image_bytes).decode("utf-8")
                    image_url = f"data:{prepared.mime_type};base64,{b64}"
                    messages: list[dict] = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": self._PARSE_PROMPT},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ]
                    response = await self._vision_provider.chat(messages)
                    content = response.get("content", "")
                    text = content.strip() if isinstance(content, str) else str(content)
                    result_text = text if text else "[解析失败]"
                    self._logger.debug(f"解析表情包 {file_path.name}: {result_text[:40]}")
                    return (file_hash, file_path, result_text)
                except Exception as exc:
                    self._logger.error(f"解析表情包失败 {file_path.name}: {exc}")
                    return (file_hash, file_path, "[解析失败]")

        tasks = [parse_one(h, p) for h, p in items]
        return list(await asyncio.gather(*tasks))

    def _rebuild_mapping(
        self,
        image_files: list[Path],
        analysis_map: dict[str, str],
        path_to_hash: dict[Path, str],
    ) -> None:
        """根据当前文件列表和分析结果重建编号映射"""
        # 保留仍存在的旧条目编号
        old_by_name: dict[str, tuple[int, EmojiEntry]] = {}
        for number, entry in self._entries.items():
            old_by_name[entry.file_name] = (number, entry)

        new_entries: dict[int, EmojiEntry] = {}
        max_existing_number = 0

        for file_path in image_files:
            name = file_path.name
            if name in old_by_name and old_by_name[name][1].file_path == file_path:
                # 文件未变，保留原编号和分析文本
                num = old_by_name[name][0]
                new_entries[num] = old_by_name[name][1]
                if num > max_existing_number:
                    max_existing_number = num
            else:
                # 新文件或文件已变更，使用已有哈希查找分析结果
                file_hash = path_to_hash.get(file_path)
                analysis_text = "[待解析]"
                if file_hash is not None:
                    analysis_text = analysis_map.get(file_hash, "[待解析]")
                if name in old_by_name:
                    num = old_by_name[name][0]
                else:
                    max_existing_number += 1
                    num = max_existing_number
                new_entries[num] = EmojiEntry(
                    file_name=name,
                    file_path=file_path,
                    analysis_text=analysis_text,
                )

        # 清理已不存在的文件
        removed = set(self._entries) - set(new_entries)
        if removed:
            self._logger.info(f"表情包文件已删除，移除编号: {sorted(removed)}")

        self._entries = new_entries
        self._next_number = max(new_entries) + 1 if new_entries else 1

    def _list_image_files(self) -> list[Path]:
        """列出表情包目录下的所有图片文件"""
        extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        files: list[Path] = []
        try:
            for child in sorted(self._emoji_dir.iterdir()):
                if child.is_file() and child.suffix.lower() in extensions:
                    files.append(child)
        except OSError as exc:
            self._logger.error(f"扫描表情包目录失败: {exc}")
        return files

    async def _refresh_loop(self) -> None:
        """后台定时刷新循环"""
        while True:
            try:
                await asyncio.sleep(self._REFRESH_INTERVAL_SECONDS)
                self._logger.debug("开始定时刷新表情包")
                await self._scan_folder()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.error(f"表情包定时刷新失败: {exc}")

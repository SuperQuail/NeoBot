from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_modloader.loading.manifest import read_manifest
from neobot_modloader.plugins.registration import validate_plugin_name

DEFAULT_ALLOWED_HOSTS = frozenset(
    {
        "github.com",
        "www.github.com",
        "codeload.github.com",
        "api.github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
    }
)
DEFAULT_BRANCH = "main"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5000
BACKUP_DIR_NAME = ".plugin-backups"

_REPO_SPEC_RE = re.compile(
    r"^(?:https?://(?:www\.)?github\.com/)?"
    r"(?P<owner>[A-Za-z0-9][A-Za-z0-9_.-]{0,38})/"
    r"(?P<repo>[A-Za-z0-9][A-Za-z0-9_.-]{0,99}?)"
    r"(?:\.git)?"
    r"(?:@(?P<branch>[^/\s]+))?/?$"
)
_VERSION_PART_RE = re.compile(r"\d+|[A-Za-z]+")


class PluginInstallError(RuntimeError):
    """插件安装 / 更新 / 卸载失败。"""


@dataclass(frozen=True, slots=True)
class RepoSpec:
    owner: str
    repo: str
    branch: str = DEFAULT_BRANCH

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def archive_url(self) -> str:
        return f"https://codeload.github.com/{self.owner}/{self.repo}/zip/refs/heads/{self.branch}"

    @property
    def manifest_url(self) -> str:
        return f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.branch}/plugin.toml"

    @property
    def homepage(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


@dataclass(frozen=True, slots=True)
class PluginInstallResult:
    ok: bool
    name: str = ""
    version: str = ""
    path: Path | None = None
    message: str = ""
    error: str | None = None
    backup_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PluginUpdateCheck:
    name: str
    current_version: str
    remote_version: str | None = None
    status: str = "unknown"
    error: str | None = None

    @property
    def update_available(self) -> bool:
        return self.status == "available"


def compare_versions(left: str, right: str) -> int:
    """比较版本号，返回 -1 / 0 / 1；无法比较的部分按字符串比较。"""
    left_parts = _VERSION_PART_RE.findall(str(left or ""))
    right_parts = _VERSION_PART_RE.findall(str(right or ""))
    for index in range(max(len(left_parts), len(right_parts))):
        left_part = left_parts[index] if index < len(left_parts) else None
        right_part = right_parts[index] if index < len(right_parts) else None
        if left_part is None or right_part is None:
            if left_part is None and right_part is None:
                return 0
            longer_is_left = left_part is not None
            remainder = left_part if longer_is_left else right_part
            # 预发布标识（字母段）小于正式版本：1.0.0 > 1.0.0-rc1
            if remainder is not None and not remainder.isdigit():
                return -1 if longer_is_left else 1
            return 1 if longer_is_left else -1
        if left_part == right_part:
            continue
        left_number = left_part.isdigit()
        right_number = right_part.isdigit()
        if left_number and right_number:
            return 1 if int(left_part) > int(right_part) else -1
        if left_number != right_number:
            # 数字段优先于字母段（1.0.1 > 1.0.rc1）
            return 1 if left_number else -1
        return 1 if left_part.lower() > right_part.lower() else -1
    return 0


class PluginInstaller:
    """基于 GitHub 仓库的插件安装 / 更新 / 卸载。

    只接受 GitHub 域名与 zip 包；解压时拒绝绝对路径、上跳路径与符号链接，
    并限制条目数与总体积。安装目录先落在临时目录，再原子替换目标目录，
    失败时自动回滚，避免半成品插件目录被扫描到。
    """

    def __init__(
        self,
        *,
        plugin_dir: Path,
        logger: Logger | None = None,
        allowed_hosts: frozenset[str] = DEFAULT_ALLOWED_HOSTS,
        timeout: float = 60.0,
        max_archive_bytes: int = MAX_ARCHIVE_BYTES,
        max_extracted_bytes: int = MAX_EXTRACTED_BYTES,
        max_archive_entries: int = MAX_ARCHIVE_ENTRIES,
        fetcher: Callable[[str], Awaitable[bytes]] | None = None,
    ) -> None:
        self.plugin_dir = Path(plugin_dir).resolve()
        self._logger = logger or NullLogger()
        self._allowed_hosts = frozenset(allowed_hosts)
        self._timeout = float(timeout)
        self._max_archive_bytes = int(max_archive_bytes)
        self._max_extracted_bytes = int(max_extracted_bytes)
        self._max_archive_entries = int(max_archive_entries)
        self._fetcher = fetcher

    @property
    def backup_dir(self) -> Path:
        return self.plugin_dir.parent / BACKUP_DIR_NAME

    # ------------------------------------------------------------------
    # 解析与校验
    # ------------------------------------------------------------------

    def parse_spec(self, spec: str, branch: str | None = None) -> RepoSpec:
        raw = str(spec or "").strip()
        if not raw:
            raise PluginInstallError("仓库地址不能为空")
        match = _REPO_SPEC_RE.match(raw)
        if match is None:
            raise PluginInstallError(
                f"无法解析仓库地址: {raw}（支持 owner/repo 或 https://github.com/owner/repo）"
            )
        resolved_branch = (branch or match.group("branch") or DEFAULT_BRANCH).strip()
        if not resolved_branch or "/" in resolved_branch or "\\" in resolved_branch:
            raise PluginInstallError(f"非法分支名: {resolved_branch!r}")
        return RepoSpec(
            owner=match.group("owner"),
            repo=match.group("repo"),
            branch=resolved_branch,
        )

    def _ensure_allowed_url(self, url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"https", "http"}:
            raise PluginInstallError(f"仅支持 http(s) 下载: {url}")
        host = (parsed.hostname or "").casefold()
        if host not in self._allowed_hosts:
            raise PluginInstallError(f"下载域名不在允许列表: {host or url}")
        return url

    # ------------------------------------------------------------------
    # 网络
    # ------------------------------------------------------------------

    async def _fetch_bytes(self, url: str) -> bytes:
        self._ensure_allowed_url(url)
        if self._fetcher is not None:
            data = await self._fetcher(url)
            return bytes(data)
        return await asyncio.to_thread(self._fetch_bytes_sync, url)

    def _fetch_bytes_sync(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "NeoBot-PluginInstaller/1.0",
                "Accept": "application/octet-stream, text/plain, */*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                declared = response.headers.get("content-length")
                if declared is not None:
                    try:
                        if int(declared) > self._max_archive_bytes:
                            raise PluginInstallError(
                                f"下载内容过大（{declared} 字节），超过上限 {self._max_archive_bytes} 字节"
                            )
                    except ValueError:
                        pass
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self._max_archive_bytes:
                        raise PluginInstallError(
                            f"下载内容超过上限 {self._max_archive_bytes} 字节"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
        except urllib.error.HTTPError as exc:
            raise PluginInstallError(f"下载失败 HTTP {exc.code}: {url}") from exc
        except urllib.error.URLError as exc:
            raise PluginInstallError(f"下载失败: {exc.reason}") from exc

    # ------------------------------------------------------------------
    # 安装 / 更新 / 卸载
    # ------------------------------------------------------------------

    async def install(
        self,
        spec: str | RepoSpec,
        *,
        branch: str | None = None,
        expected_name: str | None = None,
        replace: bool = False,
    ) -> PluginInstallResult:
        try:
            repo = spec if isinstance(spec, RepoSpec) else self.parse_spec(spec, branch)
        except PluginInstallError as exc:
            return PluginInstallResult(ok=False, error=str(exc))
        try:
            archive = await self._fetch_bytes(repo.archive_url)
        except Exception as exc:
            return PluginInstallResult(ok=False, error=str(exc))

        staging_root: Path | None = None
        try:
            staging_root = Path(
                tempfile.mkdtemp(dir=str(self._ensure_plugin_parent()), prefix=".install-")
            )
            source_dir = self._extract(archive, staging_root)
            manifest = read_manifest(source_dir / "plugin.toml")
            if not manifest:
                raise PluginInstallError("仓库内未找到 plugin.toml，无法作为插件安装")
            name = str(manifest.get("name") or source_dir.name)
            validate_plugin_name(name)
            if expected_name is not None and name != expected_name:
                raise PluginInstallError(f"插件名不匹配: 期望 {expected_name!r}，实际 {name!r}")
            version = str(manifest.get("version") or "0.1.0")
            target = self._plugin_path(name)
            backup_path: Path | None = None
            if target.exists():
                if not replace:
                    raise PluginInstallError(f"插件已安装: {name}")
                backup_path = self._backup(target, name)
                try:
                    shutil.rmtree(target)
                except OSError as exc:
                    raise PluginInstallError(f"移除旧版本失败: {exc}") from exc
            try:
                shutil.move(str(source_dir), str(target))
            except Exception as exc:
                if backup_path is not None and not target.exists():
                    shutil.move(str(backup_path), str(target))
                raise PluginInstallError(f"写入插件目录失败: {exc}") from exc
            self._logger.info(f"插件已{'更新' if replace else '安装'}: {name} {version} -> {target}")
            return PluginInstallResult(
                ok=True,
                name=name,
                version=version,
                path=target,
                message=f"{'已更新' if replace else '已安装'} {name} {version}",
                backup_path=backup_path,
            )
        except PluginInstallError as exc:
            return PluginInstallResult(ok=False, error=str(exc))
        except Exception as exc:
            self._logger.exception(f"插件安装失败: {exc}")
            return PluginInstallResult(ok=False, error=f"插件安装失败: {exc}")
        finally:
            if staging_root is not None:
                shutil.rmtree(staging_root, ignore_errors=True)

    async def update(
        self,
        name: str,
        *,
        repo: str = "",
        branch: str = "",
    ) -> PluginInstallResult:
        if not repo:
            return PluginInstallResult(ok=False, name=name, error=f"插件 {name} 未声明 repo，无法更新")
        return await self.install(repo, branch=branch or None, expected_name=name, replace=True)

    async def uninstall(self, name: str) -> PluginInstallResult:
        try:
            target = self._plugin_path(name)
        except PluginInstallError as exc:
            return PluginInstallResult(ok=False, name=name, error=str(exc))
        if not target.exists():
            return PluginInstallResult(ok=False, name=name, error=f"插件目录不存在: {target}")
        try:
            backup_path = self._backup(target, name)
            shutil.move(str(target), str(backup_path))
        except Exception as exc:
            return PluginInstallResult(ok=False, name=name, error=f"卸载失败: {exc}")
        self._logger.info(f"插件已卸载: {name} -> {backup_path}")
        return PluginInstallResult(
            ok=True,
            name=name,
            path=target,
            message=f"已卸载 {name}，代码已备份到 {backup_path}",
            backup_path=backup_path,
        )

    async def check_update(
        self,
        name: str,
        *,
        repo: str,
        branch: str = "",
        current_version: str = "",
    ) -> PluginUpdateCheck:
        if not repo:
            return PluginUpdateCheck(
                name=name,
                current_version=current_version,
                status="unknown",
                error="未声明 repo",
            )
        try:
            spec = self.parse_spec(repo, branch or None)
            raw = await self._fetch_bytes(spec.manifest_url)
            manifest = self._parse_manifest_bytes(raw)
        except Exception as exc:
            return PluginUpdateCheck(
                name=name,
                current_version=current_version,
                status="error",
                error=str(exc),
            )
        remote_version = str(manifest.get("version") or "")
        if not remote_version:
            return PluginUpdateCheck(
                name=name,
                current_version=current_version,
                status="unknown",
                error="远端 plugin.toml 缺少 version",
            )
        status = "available" if compare_versions(remote_version, current_version) > 0 else "latest"
        return PluginUpdateCheck(
            name=name,
            current_version=current_version,
            remote_version=remote_version,
            status=status,
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _parse_manifest_bytes(self, raw: bytes) -> dict:
        import tomllib

        try:
            return tomllib.loads(raw.decode("utf-8-sig"))
        except Exception as exc:
            raise PluginInstallError(f"远端 plugin.toml 解析失败: {exc}") from exc

    def _ensure_plugin_parent(self) -> Path:
        parent = self.plugin_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        return parent

    def _plugin_path(self, name: str) -> Path:
        validate_plugin_name(name)
        candidate = (self.plugin_dir / name).resolve()
        try:
            candidate.relative_to(self.plugin_dir)
        except ValueError as exc:
            raise PluginInstallError(f"插件目录越界: {name!r} -> {candidate}") from exc
        if candidate == self.plugin_dir:
            raise PluginInstallError(f"插件目录必须是独立子目录: {name!r}")
        return candidate

    def _backup(self, target: Path, name: str) -> Path:
        backup_root = self.backup_dir
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = backup_root / f"{name}-{stamp}"
        counter = 1
        while backup_path.exists():
            backup_path = backup_root / f"{name}-{stamp}-{counter}"
            counter += 1
        shutil.copytree(target, backup_path, symlinks=False, ignore=shutil.ignore_patterns("__pycache__"))
        return backup_path

    def _extract(self, archive: bytes, destination: Path) -> Path:
        descriptor, temp_name = tempfile.mkstemp(suffix=".zip", dir=str(destination))
        buffer = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(archive)
            with zipfile.ZipFile(buffer) as bundle:
                infos = [info for info in bundle.infolist() if not info.is_dir()]
                if len(infos) > self._max_archive_entries:
                    raise PluginInstallError(
                        f"压缩包条目过多（{len(infos)}），超过上限 {self._max_archive_entries}"
                    )
                total = 0
                for info in infos:
                    member = self._safe_member(info.filename)
                    if self._is_symlink(info):
                        raise PluginInstallError(f"压缩包包含符号链接: {info.filename}")
                    if member.suffix == ".pth":
                        # .pth 会改变解释器导入行为，一律跳过
                        continue
                    total += int(info.file_size)
                    if total > self._max_extracted_bytes:
                        raise PluginInstallError(
                            f"解压后体积超过上限 {self._max_extracted_bytes} 字节"
                        )
                    target = destination / member
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(info) as source, open(target, "wb") as handle:
                        shutil.copyfileobj(source, handle, length=64 * 1024)
        finally:
            buffer.unlink(missing_ok=True)

        roots = [child for child in destination.iterdir() if child.is_dir()]
        candidates = [root for root in roots if (root / "plugin.toml").is_file()]
        if not candidates:
            candidates = [root for root in roots if (root / "__init__.py").is_file()]
        if not candidates:
            if (destination / "plugin.toml").is_file():
                return destination
            raise PluginInstallError("压缩包内未找到插件目录（缺少 plugin.toml）")
        if len(candidates) > 1:
            raise PluginInstallError("压缩包内存在多个插件目录，无法确定安装目标")
        return candidates[0]

    @staticmethod
    def _is_symlink(info: zipfile.ZipInfo) -> bool:
        return (info.external_attr >> 16) & 0o170000 == 0o120000

    def _safe_member(self, name: str) -> PurePosixPath:
        normalized = str(name).replace("\\", "/")
        member = PurePosixPath(normalized)
        if member.is_absolute() or member.drive:
            raise PluginInstallError(f"压缩包包含绝对路径: {name}")
        parts = [part for part in member.parts if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            raise PluginInstallError(f"压缩包包含非法路径: {name}")
        return PurePosixPath(*parts)

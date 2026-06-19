"""
B站 Cookie 提供器 — 从 NeoBot 浏览器持久化状态中提取 SESSDATA / bili_jct。

数据来源优先级：
1. Chrome profile SQLite Cookies 数据库（app/data/browser/profiles/*/Default/Network/Cookies）
2. browser_state.json（浏览器关闭时自动保存）
3. cookies.json（手动 save_cookies）
4. 环境变量 BILI_SESSDATA / BILI_JCT
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# NeoBot 数据目录下的浏览器用户数据路径（与 bootstrap.py 中的 DATA_DIR / "browser" 对应）
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_BROWSER_DATA = _PROJECT_ROOT / "data" / "browser"


class BilibiliCookieProvider:
    """从浏览器持久化状态中提取 B站 认证 cookie。"""

    def __init__(self, browser_data_dir: str | Path | None = None):
        self._data_dir = Path(browser_data_dir or _DEFAULT_BROWSER_DATA)

    # ── 公共接口 ──

    def load_sessdata(self) -> Optional[str]:
        """获取 SESSDATA（登录会话令牌）。"""
        return self._find_cookie("SESSDATA")

    def load_bili_jct(self) -> Optional[str]:
        """获取 bili_jct（CSRF 令牌）。"""
        return self._find_cookie("bili_jct")

    def load_dedeuserid(self) -> Optional[int]:
        """获取 DedeUserID（自己的 UID）。"""
        raw = self._find_cookie("DedeUserID")
        if raw:
            try:
                return int(raw)
            except (ValueError, TypeError):
                pass
        return None

    def load_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """一次性获取 (SESSDATA, bili_jct)。"""
        return self.load_sessdata(), self.load_bili_jct()

    def is_available(self) -> bool:
        """是否有可用的 B站 登录信息。"""
        sess = self.load_sessdata()
        jct = self.load_bili_jct()
        return bool(sess and jct)

    # ── 内部：按优先级遍历数据源 ──

    def _find_cookie(self, name: str) -> Optional[str]:
        """按来源优先级查找指定 cookie 名称的值。"""
        # 1. Chrome profile SQLite（浏览器运行中也能读）
        for profile_dir in self._chrome_profile_dirs():
            value = self._from_chrome_cookies_db(profile_dir, name)
            if value:
                logger.debug("从 Chrome profile %s 读取 %s", profile_dir.name, name)
                return value

        # 2. JSON 持久化文件
        for json_path in self._json_cookie_files():
            value = self._from_json_file(json_path, name)
            if value:
                return value

        # 3. 环境变量
        env_key = f"BILI_{name.upper() if name == 'bili_jct' else name.upper()}"
        env_value = os.getenv(env_key)
        if env_value:
            logger.debug("从环境变量 %s 读取 %s", env_key, name)
            return env_value

        return None

    # ── 数据源发现 ──

    def _chrome_profile_dirs(self) -> list[Path]:
        """发现所有 Chromium profile 目录。

        搜索顺序：
        1. 根数据目录自身（bot 自带浏览器直接使用 data_dir）
        2. profiles 子目录（open_web 手动登录等场景）
        3. 系统 Chrome/Edge 用户数据目录
        """
        result: list[Path] = []

        # 1. 根目录自身（bot 自带浏览器）
        if (self._data_dir / "Default" / "Network" / "Cookies").exists():
            result.append(self._data_dir)

        # 2. profiles 子目录
        profiles_dir = self._data_dir / "profiles"
        if profiles_dir.exists():
            for d in sorted(profiles_dir.iterdir()):
                if d.is_dir() and (d / "Default" / "Network" / "Cookies").exists():
                    result.append(d)

        # 3. 系统浏览器（Chrome / Edge）用户数据目录
        result.extend(self._system_browser_dirs())

        return result

    @staticmethod
    def _system_browser_dirs() -> list[Path]:
        """发现系统安装的 Chrome / Edge 浏览器用户数据目录。"""
        import platform
        result: list[Path] = []
        if platform.system() != "Windows":
            return result

        local_appdata = os.getenv("LOCALAPPDATA", "")
        if not local_appdata:
            return result

        candidates = [
            Path(local_appdata) / "Google" / "Chrome" / "User Data",
            Path(local_appdata) / "Microsoft" / "Edge" / "User Data",
        ]
        for p in candidates:
            if (p / "Default" / "Network" / "Cookies").exists():
                result.append(p)
        return result

    def _json_cookie_files(self) -> list[Path]:
        """返回所有 JSON cookie 文件路径。"""
        candidates = [
            self._data_dir / "browser_state.json",
            self._data_dir / "cookies.json",
        ]
        return [p for p in candidates if p.exists()]

    # ── 提取器：Chrome SQLite ──

    @staticmethod
    def _from_chrome_cookies_db(profile_dir: Path, name: str) -> Optional[str]:
        """从 Chrome cookies SQLite 数据库读取指定 cookie。"""
        db_path = profile_dir / "Default" / "Network" / "Cookies"
        if not db_path.exists():
            return None

        try:
            # Chrome 运行时会锁住 DB，先复制到临时文件
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
                with open(db_path, "rb") as f:
                    shutil.copyfileobj(f, tmp)
                tmp_path = tmp.name

            try:
                conn = sqlite3.connect(tmp_path)
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT name, value, encrypted_value, host_key "
                    "FROM cookies "
                    "WHERE host_key LIKE ? AND name = ?",
                    ("%bilibili.com%", name),
                )
                row = cur.fetchone()
                conn.close()

                if row is None:
                    return None

                # 优先用明文 value，否则尝试解密 encrypted_value
                plain = row["value"]
                if plain:
                    return str(plain)

                encrypted = row["encrypted_value"]
                if encrypted:
                    decrypted = BilibiliCookieProvider._decrypt_chrome_cookie(
                        encrypted, profile_dir
                    )
                    if decrypted:
                        return str(decrypted)

                return None
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.debug("读取 Chrome cookies DB 失败: %s", e)
            return None

    @staticmethod
    def _decrypt_chrome_cookie(encrypted_value: bytes, profile_dir: Path) -> Optional[str]:
        """解密 Chrome 加密的 cookie 值。

        Chromium 80+ 使用双层加密：
        1. Local State 中的 encrypted_key 由 DPAPI 加密
        2. 解密后得到 AES-256-GCM 密钥，用于解密 cookie
        """
        import platform
        import base64

        if platform.system() != "Windows":
            return None

        data = encrypted_value

        # 只处理 v10/v20 格式（AES-GCM）
        if not (data.startswith(b"v10") or data.startswith(b"v11") or data.startswith(b"v20")):
            # 尝试直接 DPAPI 解密（旧格式）
            try:
                from win32crypt import CryptUnprotectData
                _, decrypted = CryptUnprotectData(data)
                return decrypted.decode("utf-8", errors="replace")
            except Exception:
                return None

        # 获取 AES 密钥
        aes_key = BilibiliCookieProvider._get_chrome_aes_key(profile_dir)
        if not aes_key:
            return None

        try:
            # 格式: "v10" / "v20" (3 bytes) + nonce (12 bytes) + ciphertext + tag (16 bytes)
            nonce = data[3:15]
            ciphertext_with_tag = data[15:]
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            aesgcm = AESGCM(aes_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
            # Chromium 在 cookie 值前附加 32 字节内部头部，需要跳过
            value = BilibiliCookieProvider._strip_chromium_cookie_header(plaintext)
            return value.decode("ascii")
        except Exception as e:
            logger.debug("AES-GCM 解密失败: %s", e)
            return None

    @staticmethod
    def _strip_chromium_cookie_header(plaintext: bytes) -> bytes:
        """去除 Chromium 加密 cookie 明文前的内部头部。

        Chromium 80+ 的 cookie 加密值解密后，前 32 字节为内部头部，
        之后才是真正的 cookie 值。如果没有头部则原样返回。
        """
        if len(plaintext) <= 32:
            return plaintext
        # 头部后有可打印 ASCII 字符即为真实值起点
        for offset in (32,):  # 当前已知头部长度为 32
            if offset >= len(plaintext):
                continue
            tail = plaintext[offset:]
            # 验证尾部全是可打印 ASCII（cookie 值的特征）
            if all(32 <= b < 127 for b in tail):
                return tail
        return plaintext

    @staticmethod
    def _get_chrome_aes_key(profile_dir: Path) -> Optional[bytes]:
        """从 Chrome Local State 中提取并解密 AES 主密钥。"""
        import base64

        local_state_path = profile_dir / "Local State"
        if not local_state_path.exists():
            return None

        try:
            state = json.loads(local_state_path.read_text(encoding="utf-8"))
            encrypted_key_b64 = state.get("os_crypt", {}).get("encrypted_key", "")
            if not encrypted_key_b64:
                return None

            encrypted_key = base64.b64decode(encrypted_key_b64)
            # Chrome 的 encrypted_key 前 5 字节是 "DPAPI" 前缀，去掉
            if encrypted_key.startswith(b"DPAPI"):
                encrypted_key = encrypted_key[5:]

            from win32crypt import CryptUnprotectData
            _, aes_key = CryptUnprotectData(encrypted_key)
            return aes_key
        except Exception as e:
            logger.debug("获取 AES 密钥失败: %s", e)
            return None

    # ── 提取器：JSON 文件 ──

    @staticmethod
    def _from_json_file(path: Path, name: str) -> Optional[str]:
        """从 JSON cookie 文件中读取指定 cookie，只匹配 bilibili.com 域。"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cookies = data.get("cookies") if isinstance(data, dict) else data
            if not isinstance(cookies, list):
                return None
            for c in cookies:
                if not isinstance(c, dict):
                    continue
                domain = str(c.get("domain", "")).lower()
                if "bilibili.com" not in domain:
                    continue
                if c.get("name") == name and c.get("value"):
                    return str(c["value"])
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("读取 %s 失败: %s", path, e)
        return None


# ── 便捷函数 ──

def get_bilibili_credentials() -> tuple[Optional[str], Optional[str]]:
    """快速获取 (SESSDATA, bili_jct)。"""
    return BilibiliCookieProvider().load_credentials()

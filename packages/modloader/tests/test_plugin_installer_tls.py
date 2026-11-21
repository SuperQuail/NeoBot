"""插件下载器的 TLS 信任集合（issue #257）。

下载器用 urllib，默认只信系统证书库；宿主其它请求走 httpx，只信 certifi。
两套集合不一致时，就会出现「其它功能正常、只有插件下载报
CERTIFICATE_VERIFY_FAILED」——所以下载器必须额外加载 certifi 根证书。
"""

from __future__ import annotations

import ssl
import urllib.request
from pathlib import Path

import certifi

from neobot_modloader.installer import PluginInstaller


def _https_context(opener: urllib.request.OpenerDirector) -> ssl.SSLContext:
    handlers = [item for item in opener.handlers if isinstance(item, urllib.request.HTTPSHandler)]
    assert len(handlers) == 1, handlers
    return handlers[0]._context


def test_download_opener_loads_certifi_roots(tmp_path: Path, monkeypatch) -> None:
    """certifi 里的根证书也必须在下载器的信任集合里。"""
    loaded: list[str | None] = []
    original = ssl.SSLContext.load_verify_locations

    def spy(self, cafile=None, capath=None, cadata=None):
        loaded.append(cafile)
        return original(self, cafile=cafile, capath=capath, cadata=cadata)

    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", spy)

    PluginInstaller(plugin_dir=tmp_path / "plugins")._build_opener()

    assert certifi.where() in loaded


def test_download_opener_keeps_certificate_verification(tmp_path: Path) -> None:
    """加载 certifi 不能顺手把校验关掉。"""
    context = _https_context(PluginInstaller(plugin_dir=tmp_path / "plugins")._build_opener())

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True

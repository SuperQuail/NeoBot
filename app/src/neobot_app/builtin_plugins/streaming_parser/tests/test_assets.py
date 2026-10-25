"""图片缓存与重试逻辑测试（注入假下载器，不联网）。"""

from __future__ import annotations

import os
import time

import pytest
from streaming_parser.assets import (  # noqa: E402
    AssetCache,
    HttpxDownloader,
    is_retryable_status,
    sniff_mime,
)

PNG = b'\x89PNG\r\n\x1a\n' + b'x' * 64
JPEG = b'\xff\xd8\xff' + b'y' * 64
WEBP = b'RIFF' + b'z' * 32
GIF = b'GIF89a' + b'w' * 32


class FakeDownloader:
    """按脚本返回 (status, body)，并记录调用次数。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers), timeout))
        if not self.script:
            raise AssertionError('没有更多预设响应')
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def cache(tmp_path):
    def _make(script, **kwargs):
        downloader = FakeDownloader(script)
        kwargs.setdefault('backoff_seconds', 0.0)
        return AssetCache(tmp_path, downloader=downloader, **kwargs), downloader

    return _make


class TestSniffMime:
    def test_known_formats(self):
        assert sniff_mime(PNG) == 'image/png'
        assert sniff_mime(JPEG) == 'image/jpeg'
        assert sniff_mime(WEBP) == 'image/webp'
        assert sniff_mime(GIF) == 'image/gif'

    def test_unknown_falls_back_to_jpeg(self):
        assert sniff_mime(b'unknown-bytes') == 'image/jpeg'


class TestStatusRetryability:
    """3xx / 408 / 429 不能当永久失败：卡片的图应该能自己恢复。"""

    @pytest.mark.parametrize('status', [301, 302, 307, 408, 425, 429, 500, 503])
    def test_transient_statuses_are_retryable(self, status):
        assert is_retryable_status(status) is True

    @pytest.mark.parametrize('status', [200, 204, 400, 401, 403, 404, 405, 410, 451])
    def test_permanent_statuses_are_not_retryable(self, status):
        assert is_retryable_status(status) is False

    @pytest.mark.parametrize('status', [302, 408, 429])
    async def test_transient_status_is_retried_then_succeeds(self, cache, status):
        store, downloader = cache([(status, b''), (200, PNG)])
        assert await store.fetch_bytes('https://cdn/retry.jpg') == PNG
        assert len(downloader.calls) == 2

    async def test_rate_limit_gives_up_after_all_attempts(self, cache):
        store, downloader = cache([(429, b''), (429, b''), (429, b'')])
        assert await store.fetch_bytes('https://cdn/limited.jpg') is None
        assert len(downloader.calls) == 3

    @pytest.mark.parametrize('status', [400, 403, 410])
    async def test_permanent_status_is_not_retried(self, cache, status):
        store, downloader = cache([(status, b'')])
        assert await store.fetch_bytes('https://cdn/dead.jpg') is None
        assert len(downloader.calls) == 1


class StubHttpxClient:
    """替身 httpx.AsyncClient：记录调用，验证复用而不是每次重建。"""

    def __init__(self):
        self.calls = []
        self.closed = 0

    async def get(self, url, *, headers=None, timeout=None, follow_redirects=None):
        self.calls.append((url, follow_redirects))
        return type('Resp', (), {'status_code': 200, 'content': PNG})()

    async def aclose(self):
        self.closed += 1


class TestDefaultDownloader:
    async def test_reuses_one_client_and_follows_redirects(self):
        stub = StubHttpxClient()
        downloader = HttpxDownloader(client=stub)

        await downloader('https://cdn/a.png', {}, 3.0)
        await downloader('https://cdn/b.png', {}, 3.0)

        assert [call[0] for call in stub.calls] == ['https://cdn/a.png', 'https://cdn/b.png']
        # CDN 会 302 到真实节点：必须自己跟随重定向，否则 body 是空的重定向页
        assert all(call[1] is True for call in stub.calls)
        await downloader.aclose()
        assert stub.closed == 1
        assert downloader._client is None

    async def test_aclose_is_idempotent(self):
        stub = StubHttpxClient()
        downloader = HttpxDownloader(client=stub)

        await downloader.aclose()
        await downloader.aclose()

        assert stub.closed == 1

    async def test_cache_closes_its_own_downloader(self, tmp_path):
        store = AssetCache(tmp_path, downloader=None)
        stub = StubHttpxClient()
        assert isinstance(store._download, HttpxDownloader)
        store._download._client = stub

        await store.aclose()
        await store.aclose()

        assert stub.closed == 1

    async def test_injected_downloader_is_left_to_its_owner(self, tmp_path):
        class ClosableDownloader(FakeDownloader):
            def __init__(self, script):
                super().__init__(script)
                self.closed = 0

            async def aclose(self):
                self.closed += 1

        injected = ClosableDownloader([])
        store = AssetCache(tmp_path, downloader=injected)

        await store.aclose()

        assert injected.closed == 0


class TestFetchBytes:
    async def test_success_writes_cache_and_second_call_hits_it(self, cache):
        store, downloader = cache([(200, PNG)])
        assert await store.fetch_bytes('https://cdn/a.png') == PNG
        assert await store.fetch_bytes('https://cdn/a.png') == PNG
        assert len(downloader.calls) == 1

    async def test_retries_on_server_error_then_succeeds(self, cache):
        store, downloader = cache([(503, b''), (500, b''), (200, JPEG)])
        assert await store.fetch_bytes('https://cdn/b.jpg') == JPEG
        assert len(downloader.calls) == 3

    async def test_retries_on_exception(self, cache):
        store, downloader = cache([RuntimeError('boom'), (200, PNG)])
        assert await store.fetch_bytes('https://cdn/c.png') == PNG
        assert len(downloader.calls) == 2

    async def test_client_error_is_not_retried(self, cache):
        store, downloader = cache([(404, b'')])
        assert await store.fetch_bytes('https://cdn/d.png') is None
        assert len(downloader.calls) == 1

    async def test_gives_up_after_all_attempts(self, cache):
        store, downloader = cache([(503, b''), (503, b''), (503, b'')])
        assert await store.fetch_bytes('https://cdn/e.png') is None
        assert len(downloader.calls) == 3

    async def test_attempts_is_configurable(self, cache):
        store, downloader = cache([(503, b''), (503, b'')], attempts=2)
        assert await store.fetch_bytes('https://cdn/f.png') is None
        assert len(downloader.calls) == 2

    async def test_oversize_body_is_rejected(self, cache):
        store, _ = cache([(200, b'x' * 2048)], max_bytes=1024)
        assert await store.fetch_bytes('https://cdn/g.png') is None

    async def test_empty_body_is_rejected(self, cache):
        store, _ = cache([(200, b'')])
        assert await store.fetch_bytes('https://cdn/h.png') is None

    async def test_empty_url_returns_none_without_downloading(self, cache):
        store, downloader = cache([])
        assert await store.fetch_bytes('') is None
        assert downloader.calls == []

    async def test_sends_referer_header(self, cache):
        store, downloader = cache([(200, PNG)])
        await store.fetch_bytes('https://cdn/i.png')
        _, headers, _ = downloader.calls[0]
        assert headers['referer'] == 'https://live.bilibili.com/'
        assert 'user-agent' in headers


class TestDataUri:
    async def test_data_uri_uses_sniffed_mime(self, cache):
        store, _ = cache([(200, WEBP)])
        uri = await store.fetch_data_uri('https://cdn/j.webp')
        assert uri.startswith('data:image/webp;base64,')

    async def test_failure_returns_empty_string(self, cache):
        store, _ = cache([(404, b'')])
        assert await store.fetch_data_uri('https://cdn/k.png') == ''

    async def test_empty_url_returns_empty_string(self, cache):
        store, _ = cache([])
        assert await store.fetch_data_uri('') == ''


class TestPurgeExpired:
    def test_removes_old_files(self, tmp_path):
        store = AssetCache(tmp_path, ttl_days=1, downloader=FakeDownloader([]))
        path = store.path_for('https://cdn/old.png')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        old = time.time() - 3 * 86400
        os.utime(path, (old, old))
        fresh = store.path_for('https://cdn/new.png')
        fresh.parent.mkdir(parents=True, exist_ok=True)
        fresh.write_bytes(PNG)
        assert store.purge_expired() == 1
        assert not path.exists()
        assert fresh.exists()

    def test_missing_dir_is_noop(self, tmp_path):
        store = AssetCache(tmp_path / 'nope', ttl_days=1, downloader=FakeDownloader([]))
        assert store.purge_expired() == 0


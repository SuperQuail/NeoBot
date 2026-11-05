"""WBI 签名：密钥缓存、失效重取与请求参数签名。"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from ..errors import BilibiliError
from .common import _WBI_FILTERED_CHARS, _WBI_MIXIN_KEY_ENC_TAB


class _WbiMixin:
    """WBI 签名密钥缓存与请求签名。"""

    # ── WBI 签名 ──

    def _ensure_wbi_keys(self) -> None:
        """确保有未过期的 WBI 密钥；取不到就保持无签名（请求仍能发，只是可能被 -352）。"""
        if (
            self._wbi_mixin_key
            and time.monotonic() - self._wbi_key_at < self._WBI_KEY_TTL_SECONDS
        ):
            return
        try:
            self.get_my_info()
        except BilibiliError as exc:
            self._log_read_error("WBI 密钥获取", exc)

    def _invalidate_wbi_keys(self) -> None:
        """签名被服务端判失效时清空缓存，下次请求重新取密钥。"""
        with self._lock:
            self._wbi_mixin_key = ""
            self._wbi_key_at = 0.0

    def _cache_wbi_keys(self, wbi_img: Mapping[str, Any]) -> None:
        img_raw = str(wbi_img.get("img_key") or wbi_img.get("img_url") or "")
        sub_raw = str(wbi_img.get("sub_key") or wbi_img.get("sub_url") or "")
        img_key = img_raw.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_raw.rsplit("/", 1)[-1].split(".")[0]
        if len(img_key) < 32 or len(sub_key) < 32:
            self._logger.warning("B站 WBI 密钥格式异常，后续请求将缺少签名")
            return
        combined = img_key + sub_key
        mixin_key = "".join(
            combined[index] for index in _WBI_MIXIN_KEY_ENC_TAB if index < len(combined)
        )[:32]
        with self._lock:
            self._wbi_mixin_key = mixin_key
            self._wbi_key_at = time.monotonic()

    def _sign_wbi(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """给查询参数加 wts + w_rid（拿不到密钥时原样返回）。"""
        self._ensure_wbi_keys()
        if not self._wbi_mixin_key:
            return dict(params)
        signed = {
            str(key): "".join(ch for ch in str(value) if ch not in _WBI_FILTERED_CHARS)
            for key, value in params.items()
        }
        signed["wts"] = str(int(time.time()))
        signed = dict(sorted(signed.items()))
        query = urlencode(signed)
        signed["w_rid"] = hashlib.md5(
            (query + self._wbi_mixin_key).encode()
        ).hexdigest()
        return signed

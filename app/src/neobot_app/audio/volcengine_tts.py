from __future__ import annotations

import base64
import json
from pathlib import Path
from uuid import uuid4

import httpx
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot import HuoShanTTS as HuoShanTTSConfig
from neobot_app.config.schemas.bot import TTS as TTSConfig
from neobot_app.core import DATA_DIR
from neobot_app.utils.file_helper import create_audio_segment


class VolcengineTTSService:
    """火山引擎 TTS 服务，使用 HTTP Chunked 单向流式 API V3。"""

    _ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

    def __init__(
        self,
        config: TTSConfig,
        api_key: str,
        *,
        app_id: str = "",
        logger: Logger | None = None,
        file_server=None,
    ) -> None:
        self._config = config
        self._hs: HuoShanTTSConfig = config.huoshan
        self._logger = logger or NullLogger()
        self._file_server = file_server
        self._enabled = bool(config.enabled)
        self._disabled_reason: str | None = None if self._enabled else "tts disabled"

        self._output_dir = self._resolve_output_dir(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        headers = {"X-Api-Resource-Id": self._hs.resource_id}
        if app_id:
            # 旧版控制台：App ID + Access Token
            headers["X-Api-App-Id"] = app_id
            headers["X-Api-Access-Key"] = api_key
        else:
            # 新版控制台：API Key
            headers["X-Api-Key"] = api_key

        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def voice_upload_failed(self) -> bool:
        return False

    @property
    def disabled_reason(self) -> str | None:
        return self._disabled_reason

    @property
    def active_voice(self) -> str:
        return self._hs.speaker_id

    @property
    def active_voice_name(self) -> str:
        return self._hs.speaker_id

    def bind_file_server(self, file_server) -> None:
        self._file_server = file_server

    async def initialize(self) -> None:
        if not self._enabled:
            return
        self._logger.info(
            f"火山引擎 TTS 已就绪: speaker={self._hs.speaker_id}, "
            f"resource={self._hs.resource_id}, model={self._hs.model}"
        )

    async def synthesize(self, text: str, *, voice: str | None = None) -> Path:
        if not self._enabled:
            raise RuntimeError(f"TTS 当前不可用: {self._disabled_reason}")

        speaker = voice or self._hs.speaker_id
        payload = {
            "user": {"uid": self._hs.uid},
            "req_params": {
                "text": text,
                "speaker": speaker,
                "model": self._hs.model,
                "audio_params": {
                    "format": self._hs.format,
                    "sample_rate": self._hs.sample_rate,
                },
            },
        }

        response = await self._client.post(
            self._ENDPOINT, json=payload, follow_redirects=True
        )
        await self._raise_for_status(response)

        audio_chunks: list[bytes] = []
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            chunk = json.loads(line)
            code = chunk.get("code", -1)
            if code == 20000000:
                break
            if code != 0:
                continue
            data_b64 = chunk.get("data")
            if data_b64:
                audio_chunks.append(base64.b64decode(data_b64))

        file_path = self._output_dir / (
            f"tts_{uuid4().hex}.{self._hs.format.lower()}"
        )
        file_path.write_bytes(b"".join(audio_chunks))
        self._logger.info(
            f"火山引擎 TTS 合成完成: {len(text)} chars -> {file_path.name}"
        )
        return file_path

    async def synthesize_segment(self, text: str, *, voice: str | None = None) -> dict:
        if self._file_server is None:
            raise RuntimeError("VolcengineTTSService 未绑定 file_server，无法生成语音消息段")
        file_path = await self.synthesize(text, voice=voice)
        return create_audio_segment(self._file_server, file_path)

    async def close(self) -> None:
        await self._client.aclose()

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_error:
            try:
                body = await response.aread()
                detail = body.decode("utf-8", errors="replace")
            except Exception:
                detail = "<unable to read response body>"
            raise RuntimeError(f"火山引擎 TTS 请求失败: HTTP {response.status_code}: {detail}")

    @staticmethod
    def _resolve_output_dir(output_dir: str) -> Path:
        path = Path(output_dir).expanduser()
        if path.is_absolute():
            return path
        return (DATA_DIR.parent / path).resolve()

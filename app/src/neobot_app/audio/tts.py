from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_chat import get_registered_model

from neobot_app.config.schemas.bot import TTS as TTSConfig
from neobot_app.core import DATA_DIR
from neobot_app.utils.file_helper import create_audio_segment


@dataclass(frozen=True)
class VoiceRegistrationResult:
    """Reference voice registration result."""

    uploaded: bool
    skipped: bool
    voice_name: str | None = None
    voice_uri: str | None = None
    reason: str | None = None


class TTSService:
    """SiliconFlow TTS service with optional reference voice registration."""

    def __init__(
        self,
        config: TTSConfig,
        *,
        model_name: str = "tts_model",
        logger: Logger | None = None,
        file_server=None,
    ) -> None:
        self._config = config
        self._model = get_registered_model(model_name)
        self._logger = logger or NullLogger()
        self._file_server = file_server
        self._enabled = bool(config.enabled)
        self._voice_upload_failed = False
        self._disabled_reason: str | None = None
        self._active_voice = self._model.model_name
        self._active_voice_name = self._model.model_name
        self._output_dir = self._resolve_output_dir(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.AsyncClient(
            base_url=self._model.base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self._model.api_key}"},
            timeout=httpx.Timeout(
                self._model.settings.timeout_seconds,
                connect=min(self._model.settings.timeout_seconds, 10.0),
            ),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def voice_upload_failed(self) -> bool:
        return self._voice_upload_failed

    @property
    def disabled_reason(self) -> str | None:
        return self._disabled_reason

    @property
    def active_voice(self) -> str:
        return self._active_voice

    @property
    def active_voice_name(self) -> str:
        return self._active_voice_name

    def bind_file_server(self, file_server) -> None:
        self._file_server = file_server

    async def initialize(self) -> VoiceRegistrationResult:
        if not self._enabled:
            return VoiceRegistrationResult(
                uploaded=False,
                skipped=True,
                voice_name=None,
                voice_uri=None,
                reason="tts disabled by config",
            )

        reference_voice = self._config.reference_voice
        if not reference_voice.enabled:
            self._active_voice = self._model.model_name
            self._active_voice_name = self._model.model_name
            self._logger.info(
                f"TTS 未启用参考音频上传，使用默认声音: {self._active_voice}"
            )
            return VoiceRegistrationResult(
                uploaded=False,
                skipped=True,
                voice_name=self._active_voice,
                voice_uri=self._active_voice,
                reason="reference voice upload disabled",
            )

        custom_name = reference_voice.custom_name.strip()
        if not custom_name:
            return self._handle_registration_failure("参考音频声音名称不能为空")

        try:
            voices = await self.list_registered_voices()
        except Exception as exc:
            return self._handle_registration_failure(
                f"获取已注册声音列表失败: {exc}"
            )

        existing_voice = self._find_voice(voices, custom_name)
        if existing_voice is not None:
            voice_uri = self._extract_voice_uri(existing_voice)
            self._active_voice = voice_uri or custom_name
            self._active_voice_name = custom_name
            self._logger.info(f"TTS 参考音频已存在，跳过上传: {custom_name}")
            return VoiceRegistrationResult(
                uploaded=False,
                skipped=True,
                voice_name=custom_name,
                voice_uri=voice_uri,
                reason="voice already registered",
            )

        audio_path = self._resolve_existing_path(reference_voice.audio_file)
        if audio_path is None:
            return self._handle_registration_failure(
                f"参考音频文件不存在: {reference_voice.audio_file}"
            )
        if not reference_voice.reference_text.strip():
            return self._handle_registration_failure("参考音频文本不能为空")

        try:
            voice_uri = await self._upload_reference_voice(
                audio_path=audio_path,
                custom_name=custom_name,
                reference_text=reference_voice.reference_text.strip(),
            )
        except Exception as exc:
            return self._handle_registration_failure(f"上传参考音频失败: {exc}")

        self._active_voice = voice_uri or custom_name
        self._active_voice_name = custom_name
        self._logger.info(f"TTS 参考音频上传成功: {custom_name}")
        return VoiceRegistrationResult(
            uploaded=True,
            skipped=False,
            voice_name=custom_name,
            voice_uri=voice_uri,
        )

    async def list_registered_voices(self) -> list[dict]:
        response = await self._client.get("/audio/voice/list")
        await self._raise_for_status_with_body(response, "获取声音列表失败")
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else None
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
        return []

    async def synthesize(self, text: str, *, voice: str | None = None) -> Path:
        if not self._enabled:
            reason = self._disabled_reason or "tts disabled"
            raise RuntimeError(f"TTS 当前不可用: {reason}")

        payload = {
            "model": self._model.model_name,
            "input": text,
            "voice": voice or self._active_voice,
            "response_format": self._config.response_format,
            "stream": self._config.stream,
        }
        response = await self._client.post("/audio/speech", json=payload)
        await self._raise_for_status_with_body(response, "生成语音失败")

        trace_id = response.headers.get("x-siliconcloud-trace-id")
        if trace_id:
            self._logger.info(f"TTS 请求成功，trace_id={trace_id}")

        file_path = self._output_dir / (
            f"tts_{uuid4().hex}.{self._config.response_format.lower()}"
        )
        file_path.write_bytes(await response.aread())
        return file_path

    async def synthesize_segment(self, text: str, *, voice: str | None = None) -> dict:
        if self._file_server is None:
            raise RuntimeError("TTSService 未绑定 file_server，无法生成语音消息段")
        file_path = await self.synthesize(text, voice=voice)
        return create_audio_segment(self._file_server, file_path)

    async def close(self) -> None:
        await self._client.aclose()

    async def _upload_reference_voice(
        self,
        *,
        audio_path: Path,
        custom_name: str,
        reference_text: str,
    ) -> str | None:
        content_type = mimetypes.guess_type(audio_path.name)[0] or "audio/mpeg"
        with audio_path.open("rb") as file_obj:
            files = {
                "file": (audio_path.name, file_obj, content_type),
            }
            data = {
                "model": self._model.model_name,
                "customName": custom_name,
                "text": reference_text,
            }
            response = await self._client.post(
                "/uploads/audio/voice",
                data=data,
                files=files,
            )
        await self._raise_for_status_with_body(response, "上传参考音频失败")

        try:
            payload = response.json()
        except Exception:
            return None
        if isinstance(payload, dict):
            return self._extract_voice_uri(payload)
        return None

    async def _raise_for_status_with_body(
        self, response: httpx.Response, action: str
    ) -> None:
        if not response.is_error:
            return
        try:
            body = response.text
        except Exception:
            try:
                body = (await response.aread()).decode("utf-8", errors="replace")
            except Exception:
                body = "<unable to read response body>"
        raise RuntimeError(f"{action}: HTTP {response.status_code}: {body}")

    def _handle_registration_failure(self, reason: str) -> VoiceRegistrationResult:
        self._voice_upload_failed = True
        self._logger.warning(reason)
        if self._config.reference_voice.disable_tts_on_upload_failure:
            self._enabled = False
            self._disabled_reason = reason
            self._logger.warning("参考音频上传失败，已自动禁用 TTS 功能")
        return VoiceRegistrationResult(
            uploaded=False,
            skipped=False,
            voice_name=None,
            voice_uri=None,
            reason=reason,
        )

    @staticmethod
    def _find_voice(voices: list[dict], custom_name: str) -> dict | None:
        target = custom_name.casefold()
        for voice in voices:
            for key in (
                "customName",
                "custom_name",
                "name",
                "voiceName",
                "voice_name",
            ):
                value = voice.get(key)
                if isinstance(value, str) and value.casefold() == target:
                    return voice
        return None

    @staticmethod
    def _extract_voice_uri(voice_data: dict) -> str | None:
        for key in ("uri", "voiceUri", "voice_uri", "id"):
            value = voice_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _resolve_output_dir(output_dir: str) -> Path:
        path = Path(output_dir).expanduser()
        if path.is_absolute():
            return path
        return (DATA_DIR.parent / path).resolve()

    @staticmethod
    def _resolve_existing_path(raw_path: str) -> Path | None:
        path = Path(raw_path).expanduser()
        candidates = [path] if path.is_absolute() else [
            Path.cwd() / path,
            DATA_DIR / path,
            DATA_DIR.parent / path,
        ]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.exists():
                return resolved
        return None

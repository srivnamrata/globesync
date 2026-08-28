import asyncio
import logging
import os
import uuid
from typing import Optional

from app.core.config import settings
from app.utils.error_codes import ErrorCode, MediaAppException
from app.utils.language_configs import normalize_language_code

logger = logging.getLogger("google_tts_service")

_LANGUAGE_CODE_MAP = {
    "ar": "ar-XA",
    "de": "de-DE",
    "el": "el-GR",
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "he": "he-IL",
    "hi": "hi-IN",
    "id": "id-ID",
    "it": "it-IT",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "nl": "nl-NL",
    "pl": "pl-PL",
    "pt": "pt-BR",
    "ru": "ru-RU",
    "sv": "sv-SE",
    "th": "th-TH",
    "tr": "tr-TR",
    "uk": "uk-UA",
    "vi": "vi-VN",
    "zh": "cmn-CN",
}


class GoogleCloudTTS:
    """Async facade over the synchronous Google Cloud Text-to-Speech client."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import google.auth
                from google.cloud import texttospeech
            except ImportError as exc:
                raise MediaAppException(
                    status_code=500,
                    error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                    message="Google Cloud Text-to-Speech is not installed. Run pip install -r requirements.txt.",
                ) from exc

            if settings.GOOGLE_APPLICATION_CREDENTIALS:
                credentials, _ = google.auth.load_credentials_from_file(
                    settings.GOOGLE_APPLICATION_CREDENTIALS,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                self._client = texttospeech.TextToSpeechClient(credentials=credentials)
            else:
                self._client = texttospeech.TextToSpeechClient()
        return self._client

    def _resolve_language_code(self, language_code: Optional[str]) -> str:
        candidate = (language_code or settings.GOOGLE_TTS_LANGUAGE_CODE or "").strip()
        if not candidate:
            return "en-US"
        if "-" in candidate:
            return candidate
        return _LANGUAGE_CODE_MAP.get(normalize_language_code(candidate), settings.GOOGLE_TTS_LANGUAGE_CODE)

    async def synthesize_speech(
        self,
        text: str,
        language_code: Optional[str] = None,
        output_file_path: Optional[str] = None,
        voice_name: Optional[str] = None,
        speaking_rate: Optional[float] = None,
        pitch: Optional[float] = None,
    ) -> str:
        if not text.strip():
            raise MediaAppException(
                status_code=400,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Cannot synthesize empty text.",
            )

        if not output_file_path:
            output_file_path = os.path.join(
                settings.PROCESSED_MEDIA_DIR,
                f"tts_{uuid.uuid4().hex}.wav",
            )
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

        resolved_language_code = self._resolve_language_code(language_code)
        configured_voice_name = voice_name or settings.GOOGLE_TTS_VOICE_NAME
        resolved_voice_name = configured_voice_name
        if configured_voice_name and not configured_voice_name.startswith(resolved_language_code):
            logger.warning(
                "Configured Google TTS voice %s does not match language %s; using provider default voice for that language.",
                configured_voice_name,
                resolved_language_code,
            )
            resolved_voice_name = None

        def _synthesize() -> str:
            from google.cloud import texttospeech

            client = self._get_client()
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice_kwargs = {"language_code": resolved_language_code}
            if resolved_voice_name:
                voice_kwargs["name"] = resolved_voice_name
            voice = texttospeech.VoiceSelectionParams(**voice_kwargs)
            audio_encoding = getattr(
                texttospeech.AudioEncoding,
                settings.GOOGLE_TTS_AUDIO_ENCODING.upper(),
                texttospeech.AudioEncoding.LINEAR16,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=audio_encoding,
                speaking_rate=speaking_rate or settings.GOOGLE_TTS_SPEAKING_RATE,
                pitch=pitch if pitch is not None else settings.GOOGLE_TTS_PITCH,
            )
            response = client.synthesize_speech(
                request={
                    "input": synthesis_input,
                    "voice": voice,
                    "audio_config": audio_config,
                }
            )
            with open(output_file_path, "wb") as out:
                out.write(response.audio_content)
            return output_file_path

        try:
            return await asyncio.to_thread(_synthesize)
        except MediaAppException:
            raise
        except Exception as exc:
            logger.error("Google Cloud TTS request failed", exc_info=True)
            raise MediaAppException(
                status_code=502,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message=f"Google Cloud Text-to-Speech failed: {exc}",
                details={
                    "language_code": resolved_language_code,
                    "voice_name": resolved_voice_name,
                },
            ) from exc


google_tts_service = GoogleCloudTTS()

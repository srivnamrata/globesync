import asyncio
import logging
import mimetypes
import os
import uuid
from typing import Any, Dict, Optional

from app.core.config import settings
from app.services.storage_service import storage_service
from app.utils.error_codes import ErrorCode, MediaAppException
from app.utils.language_configs import normalize_language_code

logger = logging.getLogger("google_stt_service")

_LANGUAGE_CODE_MAP = {
    "ar": "ar-SA",
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
    "zh": "cmn-Hans-CN",
}


class GoogleCloudSTT:
    """Async facade over Google Cloud Speech-to-Text with GCS-backed long-running recognition."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import google.auth
                from google.cloud import speech_v1p1beta1 as speech
            except ImportError as exc:
                raise MediaAppException(
                    status_code=500,
                    error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                    message="Google Cloud Speech-to-Text is not installed. Run pip install -r requirements.txt.",
                ) from exc

            if settings.GOOGLE_APPLICATION_CREDENTIALS:
                credentials, _ = google.auth.load_credentials_from_file(
                    settings.GOOGLE_APPLICATION_CREDENTIALS,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                self._client = speech.SpeechClient(credentials=credentials)
            else:
                self._client = speech.SpeechClient()
        return self._client

    def _resolve_language_code(self, language_code: Optional[str]) -> str:
        candidate = (language_code or settings.GOOGLE_STT_LANGUAGE_CODE or "").strip()
        if not candidate:
            return "en-US"
        if "-" in candidate:
            return candidate
        return _LANGUAGE_CODE_MAP.get(normalize_language_code(candidate), settings.GOOGLE_STT_LANGUAGE_CODE)

    async def transcribe_audio_file(
        self,
        audio_file_path: str,
        language: Optional[str] = None,
        max_speakers: Optional[int] = None,
        diarize: bool = True,
    ) -> Dict[str, Any]:
        if not os.path.exists(audio_file_path):
            raise MediaAppException(
                status_code=404,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message=f"Audio file not found for Google STT: {audio_file_path}",
            )

        if not language:
            raise MediaAppException(
                status_code=400,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Google STT currently requires an explicit language code; falling back to the secondary provider preserves auto-detection.",
            )

        mime_type, _ = mimetypes.guess_type(audio_file_path)
        temp_storage_key = f"_ops/stt/{uuid.uuid4().hex}/{os.path.basename(audio_file_path)}"
        resolved_language_code = self._resolve_language_code(language)
        speaker_count = max(1, int(max_speakers or settings.GOOGLE_STT_MAX_SPEAKERS))

        try:
            uploaded_uri = await storage_service.upload_file(
                file_path=audio_file_path,
                key=temp_storage_key,
                mime_type=mime_type or "audio/wav",
            )

            def _transcribe() -> Dict[str, Any]:
                from google.cloud import speech_v1p1beta1 as speech
                from google.protobuf.json_format import MessageToDict

                client = self._get_client()
                diarization_config = speech.SpeakerDiarizationConfig(
                    enable_speaker_diarization=diarize and settings.GOOGLE_STT_ENABLE_DIARIZATION,
                    min_speaker_count=1,
                    max_speaker_count=speaker_count,
                )
                config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=settings.GOOGLE_STT_SAMPLE_RATE_HZ,
                    language_code=resolved_language_code,
                    model=settings.GOOGLE_STT_MODEL,
                    enable_automatic_punctuation=settings.GOOGLE_STT_ENABLE_AUTOMATIC_PUNCTUATION,
                    enable_word_time_offsets=True,
                    enable_word_confidence=True,
                    use_enhanced=settings.GOOGLE_STT_USE_ENHANCED,
                    diarization_config=diarization_config,
                    audio_channel_count=1,
                )
                audio = speech.RecognitionAudio(uri=uploaded_uri)
                operation = client.long_running_recognize(config=config, audio=audio)
                response = operation.result(timeout=settings.GOOGLE_STT_TIMEOUT_SECONDS)
                response_dict = MessageToDict(response._pb)
                response_dict["provider"] = "google"
                response_dict["resolvedLanguageCode"] = resolved_language_code
                return response_dict

            return await asyncio.to_thread(_transcribe)
        except MediaAppException:
            raise
        except Exception as exc:
            logger.error("Google Cloud STT request failed", exc_info=True)
            raise MediaAppException(
                status_code=502,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message=f"Google Cloud Speech-to-Text failed: {exc}",
                details={"language_code": resolved_language_code},
            ) from exc
        finally:
            try:
                await storage_service.delete_object(temp_storage_key)
            except Exception:
                logger.warning("Failed to delete temporary Google STT audio object %s", temp_storage_key)


google_stt_service = GoogleCloudSTT()

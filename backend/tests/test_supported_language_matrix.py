import pytest

from app.schemas.translation_schema import TranslateProjectRequest
from app.services.google_stt_service import GoogleCloudSTT, _LANGUAGE_CODE_MAP as STT_LANGUAGE_CODE_MAP
from app.services.google_tts_service import GoogleCloudTTS, _LANGUAGE_CODE_MAP as TTS_LANGUAGE_CODE_MAP
from app.utils.language_configs import get_supported_language_codes
from app.utils.speech_rate import speech_rate_estimator


SUPPORTED_LANGUAGE_CODES = get_supported_language_codes()


@pytest.mark.parametrize("language_code", SUPPORTED_LANGUAGE_CODES)
def test_supported_language_has_translation_and_duration_support(language_code: str) -> None:
    request = TranslateProjectRequest(
        transcript_id="00000000-0000-4000-8000-000000000001",
        source_language="en",
        target_language=language_code,
    )

    assert request.target_language == language_code
    assert speech_rate_estimator.estimate_speech_duration_ms("Hello world.", language_code) > 0


@pytest.mark.parametrize("language_code", SUPPORTED_LANGUAGE_CODES)
def test_supported_language_maps_to_google_stt_locale(language_code: str) -> None:
    assert language_code in STT_LANGUAGE_CODE_MAP
    assert GoogleCloudSTT()._resolve_language_code(language_code) == STT_LANGUAGE_CODE_MAP[language_code]


@pytest.mark.parametrize("language_code", SUPPORTED_LANGUAGE_CODES)
def test_supported_language_maps_to_google_tts_locale(language_code: str) -> None:
    assert language_code in TTS_LANGUAGE_CODE_MAP
    assert GoogleCloudTTS()._resolve_language_code(language_code) == TTS_LANGUAGE_CODE_MAP[language_code]

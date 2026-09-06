import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import google_stt_service as google_stt_module
from app.services import google_translate_service as google_translate_module
from app.services import google_tts_service as google_tts_module
from app.utils.error_codes import MediaAppException


class _FakeRecognitionConfig:
    class AudioEncoding:
        LINEAR16 = "LINEAR16"

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeSpeechDiarizationConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeRecognitionAudio:
    def __init__(self, uri):
        self.uri = uri


class _FakeSynthesisInput:
    def __init__(self, text):
        self.text = text


class _FakeVoiceSelectionParams:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeAudioConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeAudioEncoding:
    LINEAR16 = "LINEAR16"
    MP3 = "MP3"
    OGG_OPUS = "OGG_OPUS"


class _FakeSTTResponse:
    def __init__(self, payload):
        self._pb = payload


class _FakeSTTOperation:
    def __init__(self, response=None, result_side_effect=None):
        self.response = response
        self.result_side_effect = result_side_effect
        self.result_timeout = None

    def result(self, timeout=None):
        self.result_timeout = timeout
        if self.result_side_effect is not None:
            raise self.result_side_effect
        return self.response


class _FakeSTTClient:
    instances = []

    def __init__(self, credentials=None, operation=None):
        self.credentials = credentials
        self.operation = operation
        self.calls = []
        _FakeSTTClient.instances.append(self)

    def long_running_recognize(self, config, audio):
        self.calls.append({"config": config, "audio": audio})
        return self.operation


class _FakeTranslateClient:
    instances = []

    def __init__(self, credentials=None, response=None, side_effect=None):
        self.credentials = credentials
        self.response = response
        self.side_effect = side_effect
        self.calls = []
        _FakeTranslateClient.instances.append(self)

    def translate_text(self, request):
        self.calls.append(request)
        if self.side_effect is not None:
            raise self.side_effect
        return self.response


class _FakeTranslateResponse:
    def __init__(self, translations):
        self.translations = translations


class _FakeTTSClient:
    instances = []

    def __init__(self, credentials=None, response=None, side_effect=None):
        self.credentials = credentials
        self.response = response
        self.side_effect = side_effect
        self.calls = []
        _FakeTTSClient.instances.append(self)

    def synthesize_speech(self, request):
        self.calls.append(request)
        if self.side_effect is not None:
            raise self.side_effect
        return self.response


class _FakeTTSResponse:
    def __init__(self, audio_content):
        self.audio_content = audio_content


def _patch_to_thread(monkeypatch, module):
    monkeypatch.setattr(module.asyncio, "to_thread", AsyncMock(side_effect=lambda fn: fn()))


def _install_google_stt_sdk(monkeypatch, *, response=None, result_side_effect=None, credentials="loaded-creds"):
    _FakeSTTClient.instances.clear()
    google_mod = types.ModuleType("google")
    auth_mod = types.ModuleType("google.auth")
    cloud_mod = types.ModuleType("google.cloud")
    speech_mod = types.ModuleType("google.cloud.speech_v1p1beta1")
    protobuf_mod = types.ModuleType("google.protobuf")
    json_format_mod = types.ModuleType("google.protobuf.json_format")

    auth_mod.load_credentials_from_file = MagicMock(return_value=(credentials, None))
    speech_mod.SpeechClient = lambda credentials=None: _FakeSTTClient(
        credentials=credentials,
        operation=_FakeSTTOperation(response=response, result_side_effect=result_side_effect),
    )
    speech_mod.SpeakerDiarizationConfig = _FakeSpeechDiarizationConfig
    speech_mod.RecognitionConfig = _FakeRecognitionConfig
    speech_mod.RecognitionAudio = _FakeRecognitionAudio
    json_format_mod.MessageToDict = lambda pb: {} if pb is None else dict(pb)

    google_mod.auth = auth_mod
    google_mod.cloud = cloud_mod
    google_mod.protobuf = protobuf_mod
    cloud_mod.speech_v1p1beta1 = speech_mod
    protobuf_mod.json_format = json_format_mod

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.auth", auth_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.speech_v1p1beta1", speech_mod)
    monkeypatch.setitem(sys.modules, "google.protobuf", protobuf_mod)
    monkeypatch.setitem(sys.modules, "google.protobuf.json_format", json_format_mod)


def _install_google_translate_sdk(monkeypatch, *, response=None, side_effect=None, credentials="loaded-creds"):
    _FakeTranslateClient.instances.clear()
    google_mod = types.ModuleType("google")
    auth_mod = types.ModuleType("google.auth")
    cloud_mod = types.ModuleType("google.cloud")
    translate_mod = types.ModuleType("google.cloud.translate_v3")

    auth_mod.load_credentials_from_file = MagicMock(return_value=(credentials, None))
    translate_mod.TranslationServiceClient = lambda credentials=None: _FakeTranslateClient(
        credentials=credentials,
        response=response,
        side_effect=side_effect,
    )

    google_mod.auth = auth_mod
    google_mod.cloud = cloud_mod
    cloud_mod.translate_v3 = translate_mod

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.auth", auth_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.translate_v3", translate_mod)


def _install_google_tts_sdk(monkeypatch, *, response=None, side_effect=None, credentials="loaded-creds"):
    _FakeTTSClient.instances.clear()
    google_mod = types.ModuleType("google")
    auth_mod = types.ModuleType("google.auth")
    cloud_mod = types.ModuleType("google.cloud")
    tts_mod = types.ModuleType("google.cloud.texttospeech")

    auth_mod.load_credentials_from_file = MagicMock(return_value=(credentials, None))
    tts_mod.TextToSpeechClient = lambda credentials=None: _FakeTTSClient(
        credentials=credentials,
        response=response,
        side_effect=side_effect,
    )
    tts_mod.SynthesisInput = _FakeSynthesisInput
    tts_mod.VoiceSelectionParams = _FakeVoiceSelectionParams
    tts_mod.AudioConfig = _FakeAudioConfig
    tts_mod.AudioEncoding = _FakeAudioEncoding

    google_mod.auth = auth_mod
    google_mod.cloud = cloud_mod
    cloud_mod.texttospeech = tts_mod

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.auth", auth_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.texttospeech", tts_mod)


@pytest.mark.asyncio
async def test_google_stt_transcribe_success_uses_sdk_contract_and_enhanced_language_branch(monkeypatch, tmp_path):
    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"RIFFDATA")
    response_payload = {"results": [{"alternatives": [{"transcript": "Bonjour", "words": []}]}]}

    _install_google_stt_sdk(monkeypatch, response=_FakeSTTResponse(response_payload))
    _patch_to_thread(monkeypatch, google_stt_module)
    google_stt_module.google_stt_service._client = None
    monkeypatch.setattr(google_stt_module.storage_service, "upload_file", AsyncMock(return_value="gs://bucket/_ops/stt/clip.wav"))
    monkeypatch.setattr(google_stt_module.storage_service, "delete_object", AsyncMock())
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_APPLICATION_CREDENTIALS", "creds.json", raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_MODEL", "latest_long", raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_USE_ENHANCED", True, raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_MAX_SPEAKERS", 5, raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_SAMPLE_RATE_HZ", 16000, raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_ENABLE_DIARIZATION", True, raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_ENABLE_AUTOMATIC_PUNCTUATION", True, raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_TIMEOUT_SECONDS", 19, raising=False)

    result = await google_stt_module.google_stt_service.transcribe_audio_file(
        str(audio_file),
        language="fr",
        max_speakers=3,
        duration_seconds=42.0,
    )

    client = _FakeSTTClient.instances[-1]
    operation = client.operation

    assert result["provider"] == "google"
    assert result["resolvedLanguageCode"] == "fr-FR"
    assert client.credentials == "loaded-creds"
    assert client.calls[0]["audio"].uri.startswith("gs://bucket/_ops/stt/")
    assert client.calls[0]["config"].language_code == "fr-FR"
    assert client.calls[0]["config"].model == "latest_short"
    assert client.calls[0]["config"].use_enhanced is True
    assert client.calls[0]["config"].diarization_config.enable_speaker_diarization is True
    assert client.calls[0]["config"].diarization_config.max_speaker_count == 3
    assert operation.result_timeout == 19
    google_stt_module.storage_service.upload_file.assert_awaited_once()
    google_stt_module.storage_service.delete_object.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_stt_transcribe_returns_empty_payload_and_passthrough_language_branch(monkeypatch, tmp_path):
    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"RIFFDATA")

    _install_google_stt_sdk(monkeypatch, response=_FakeSTTResponse({}))
    _patch_to_thread(monkeypatch, google_stt_module)
    google_stt_module.google_stt_service._client = None
    monkeypatch.setattr(google_stt_module.storage_service, "upload_file", AsyncMock(return_value="gs://bucket/_ops/stt/empty.wav"))
    monkeypatch.setattr(google_stt_module.storage_service, "delete_object", AsyncMock())
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_APPLICATION_CREDENTIALS", None, raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_MODEL", "latest_long", raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_USE_ENHANCED", True, raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_MAX_SPEAKERS", 4, raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_TIMEOUT_SECONDS", 12, raising=False)

    result = await google_stt_module.google_stt_service.transcribe_audio_file(
        str(audio_file),
        language="de-DE",
        max_speakers=2,
        duration_seconds=120.0,
    )

    client = _FakeSTTClient.instances[-1]
    assert result == {"provider": "google", "resolvedLanguageCode": "de-DE"}
    assert client.calls[0]["config"].language_code == "de-DE"
    assert client.calls[0]["config"].use_enhanced is False
    google_stt_module.storage_service.upload_file.assert_awaited_once()
    google_stt_module.storage_service.delete_object.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_stt_transcribe_rejects_missing_language_before_upload(monkeypatch, tmp_path):
    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"RIFFDATA")

    google_stt_module.google_stt_service._client = None
    upload = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(google_stt_module.storage_service, "upload_file", upload)
    monkeypatch.setattr(google_stt_module.storage_service, "delete_object", delete)

    with pytest.raises(MediaAppException) as error:
        await google_stt_module.google_stt_service.transcribe_audio_file(str(audio_file), language=None)

    assert error.value.status_code == 400
    upload.assert_not_awaited()
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_google_stt_transcribe_wraps_timeout_and_deletes_temp_object(monkeypatch, tmp_path):
    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"RIFFDATA")

    _install_google_stt_sdk(
        monkeypatch,
        response=_FakeSTTResponse({"results": []}),
        result_side_effect=TimeoutError("deadline exceeded"),
    )
    _patch_to_thread(monkeypatch, google_stt_module)
    google_stt_module.google_stt_service._client = None
    upload = AsyncMock(return_value="gs://bucket/_ops/stt/timed.wav")
    delete = AsyncMock()
    monkeypatch.setattr(google_stt_module.storage_service, "upload_file", upload)
    monkeypatch.setattr(google_stt_module.storage_service, "delete_object", delete)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_APPLICATION_CREDENTIALS", "creds.json", raising=False)
    monkeypatch.setattr(google_stt_module.settings, "GOOGLE_STT_TIMEOUT_SECONDS", 7, raising=False)

    with pytest.raises(MediaAppException) as error:
        await google_stt_module.google_stt_service.transcribe_audio_file(str(audio_file), language="en")

    assert error.value.status_code == 502
    assert "deadline exceeded" in error.value.message
    upload.assert_awaited_once()
    delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_translate_success_short_circuits_empty_text_and_uses_sdk_request_contract(monkeypatch):
    _install_google_translate_sdk(
        monkeypatch,
        response=_FakeTranslateResponse([SimpleNamespace(translated_text="Bienvenidos")]),
    )
    _patch_to_thread(monkeypatch, google_translate_module)
    google_translate_module.google_translate_service._client = None
    monkeypatch.setattr(google_translate_module.settings, "GOOGLE_CLOUD_PROJECT", "project-123", raising=False)
    monkeypatch.setattr(google_translate_module.settings, "GOOGLE_APPLICATION_CREDENTIALS", "creds.json", raising=False)

    translated = await google_translate_module.google_translate_service.translate_text("Welcome", "en", "es")

    client = _FakeTranslateClient.instances[-1]
    assert translated == "Bienvenidos"
    assert client.credentials == "loaded-creds"
    assert client.calls[0]["parent"] == "projects/project-123/locations/global"
    assert client.calls[0]["contents"] == ["Welcome"]
    assert client.calls[0]["source_language_code"] == "en"
    assert client.calls[0]["target_language_code"] == "es"

    no_op = await google_translate_module.google_translate_service.translate_text("   ", "en", "es")
    assert no_op == "   "
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_google_translate_requires_project_config(monkeypatch):
    google_translate_module.google_translate_service._client = None
    monkeypatch.setattr(google_translate_module.settings, "GOOGLE_CLOUD_PROJECT", None, raising=False)

    with pytest.raises(MediaAppException) as error:
        await google_translate_module.google_translate_service.translate_text("Hello", "en", "es")

    assert error.value.status_code == 500
    assert "GOOGLE_CLOUD_PROJECT" in error.value.message


@pytest.mark.parametrize(
    "response_factory, expected_message",
    [
        (lambda: _FakeTranslateResponse([]), "list index out of range"),
        (lambda: (_ for _ in ()).throw(RuntimeError("provider unavailable")), "provider unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_google_translate_wraps_empty_or_provider_failures(monkeypatch, response_factory, expected_message):
    google_translate_module.google_translate_service._client = None
    monkeypatch.setattr(google_translate_module.settings, "GOOGLE_CLOUD_PROJECT", "project-123", raising=False)
    _patch_to_thread(monkeypatch, google_translate_module)

    if expected_message == "provider unavailable":
        _install_google_translate_sdk(monkeypatch, side_effect=RuntimeError("provider unavailable"))
    else:
        _install_google_translate_sdk(monkeypatch, response=response_factory())

    with pytest.raises(MediaAppException) as error:
        await google_translate_module.google_translate_service.translate_text("Hello", "en", "es")

    assert error.value.status_code == 502
    assert expected_message in error.value.message


@pytest.mark.asyncio
async def test_google_tts_synthesizes_audio_and_falls_back_to_default_voice_for_mismatched_voice(monkeypatch, tmp_path):
    output_file = tmp_path / "speech.wav"
    _install_google_tts_sdk(monkeypatch, response=_FakeTTSResponse(b"FAKEAUDIO"))
    _patch_to_thread(monkeypatch, google_tts_module)
    google_tts_module.google_tts_service._client = None
    monkeypatch.setattr(google_tts_module.settings, "GOOGLE_APPLICATION_CREDENTIALS", "creds.json", raising=False)
    monkeypatch.setattr(google_tts_module.settings, "GOOGLE_TTS_AUDIO_ENCODING", "ogg_opus", raising=False)
    monkeypatch.setattr(google_tts_module.settings, "GOOGLE_TTS_SPEAKING_RATE", 1.07, raising=False)
    monkeypatch.setattr(google_tts_module.settings, "GOOGLE_TTS_PITCH", -2.5, raising=False)
    monkeypatch.setattr(google_tts_module.settings, "GOOGLE_TTS_VOICE_NAME", "en-US-Standard-A", raising=False)

    result_path = await google_tts_module.google_tts_service.synthesize_speech(
        "Bonjour tout le monde",
        language_code="pt-BR",
        output_file_path=str(output_file),
        voice_name="en-US-Standard-A",
        speaking_rate=1.1,
        pitch=-1.5,
    )

    client = _FakeTTSClient.instances[-1]
    request = client.calls[0]
    assert result_path == str(output_file)
    assert output_file.read_bytes() == b"FAKEAUDIO"
    assert request["voice"].language_code == "pt-BR"
    assert getattr(request["voice"], "name", None) is None
    assert request["audio_config"].audio_encoding == "OGG_OPUS"
    assert request["audio_config"].speaking_rate == 1.1
    assert request["audio_config"].pitch == -1.5


@pytest.mark.asyncio
async def test_google_tts_rejects_empty_text_before_client_work(monkeypatch, tmp_path):
    google_tts_module.google_tts_service._client = None
    upload_path = tmp_path / "unused.wav"

    with pytest.raises(MediaAppException) as error:
        await google_tts_module.google_tts_service.synthesize_speech(
            "   ",
            language_code="en",
            output_file_path=str(upload_path),
        )

    assert error.value.status_code == 400
    assert not upload_path.exists()


@pytest.mark.parametrize(
    "side_effect, expected_fragment",
    [
        (None, "audio_content"),
        (TimeoutError("deadline exceeded"), "deadline exceeded"),
    ],
)
@pytest.mark.asyncio
async def test_google_tts_wraps_malformed_or_provider_failures(monkeypatch, tmp_path, side_effect, expected_fragment):
    output_file = tmp_path / "speech.wav"
    response = _FakeTTSResponse(b"FAKEAUDIO") if side_effect is not None else SimpleNamespace()
    _install_google_tts_sdk(monkeypatch, response=response, side_effect=side_effect)
    _patch_to_thread(monkeypatch, google_tts_module)
    google_tts_module.google_tts_service._client = None
    monkeypatch.setattr(google_tts_module.settings, "GOOGLE_APPLICATION_CREDENTIALS", "creds.json", raising=False)

    with pytest.raises(MediaAppException) as error:
        await google_tts_module.google_tts_service.synthesize_speech(
            "Hello",
            language_code="fr",
            output_file_path=str(output_file),
        )

    assert error.value.status_code == 502
    assert expected_fragment in error.value.message

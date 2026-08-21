import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.models.transcript import Transcript, TranscriptSegment
from app.models.translation import Translation
from app.models.voice_profile import VoiceProfile
from app.schemas.tts_schema import SynthesizeProjectTTSRequest
from app.services.elevenlabs_service import elevenlabs_tts
from app.utils.audio_matcher import audio_matcher
from app.utils.prosody_extractor import prosody_extractor


# =============================================================================
# 1. AUDIO MATCHER & PROSODY UNIT TESTS
# =============================================================================
def test_audio_matcher_retiming_factor():
    # Target: 3000ms, Actual: 3450ms -> Factor = 1.15
    factor, delta = audio_matcher.calculate_retiming_factor(3450, 3000)
    assert factor == 1.15
    assert delta == 450

    # Upper clamp test: Target: 2000ms, Actual: 3500ms (1.75x) -> Clamped to 1.35x
    factor_clamped, _ = audio_matcher.calculate_retiming_factor(3500, 2000, max_factor=1.35)
    assert factor_clamped == 1.35

    # Lower clamp test: Target: 4000ms, Actual: 2000ms (0.50x) -> Clamped to 0.75x
    factor_lower, _ = audio_matcher.calculate_retiming_factor(2000, 4000, min_factor=0.75)
    assert factor_lower == 0.75


def test_prosody_extractor_fallback():
    # Fallback features verification when no raw WAV file is present
    features = prosody_extractor._fallback_prosody()
    assert "mean_pitch_hz" in features
    assert "warmth" in features
    assert "depth" in features
    assert "recommended_voice_settings" in features
    assert features["recommended_voice_settings"]["stability"] == 0.50
    assert features["recommended_voice_settings"]["similarity_boost"] == 0.80


def test_elevenlabs_utils_settings_and_pitch():
    from app.utils.elevenlabs_utils import elevenlabs_utils

    # 1. Emotion preset generation
    settings = elevenlabs_utils.get_voice_settings_for_style(
        emotion="energetic", warmth=0.7, depth=0.6, expressiveness=0.8
    )
    assert settings["similarity_boost"] >= 0.80
    assert "stability" in settings
    assert "style" in settings

    # 2. Pitch shift factor: +2 semitones -> 2^(2/12) ≈ 1.1225
    factor_up = elevenlabs_utils.calculate_pitch_shift_factor(2.0)
    assert 1.12 <= factor_up <= 1.13

    # -2 semitones -> 2^(-2/12) ≈ 0.8909
    factor_down = elevenlabs_utils.calculate_pitch_shift_factor(-2.0)
    assert 0.88 <= factor_down <= 0.90

    # 3. Room reverb estimation
    reverb_params = elevenlabs_utils.estimate_room_reverb(-14.0)
    assert reverb_params is not None
    assert "delays" in reverb_params
    assert "decays" in reverb_params


@pytest.mark.asyncio
async def test_elevenlabs_mock_synthesis():
    mock_out_path = "tmp/processed/test_synth_out.wav"
    out_path = await elevenlabs_tts.synthesize_speech(
        text="Hola y bienvenidos a la conferencia.",
        voice_id="mock_voice_123",
        output_file_path=mock_out_path,
    )
    assert out_path == mock_out_path


# =============================================================================
# 2. FASTAPI TTS ROUTE TESTS
# =============================================================================
@pytest.mark.asyncio
async def test_synthesize_project_tts_endpoint():
    transport = ASGITransport(app=app)
    mock_transcript_id = uuid.uuid4()
    mock_project_id = uuid.uuid4()

    with patch("app.routers.tts.select") as mock_select, \
         patch("app.routers.tts.synthesize_project_tts_task.apply_async") as mock_task:
        
        mock_task.return_value = MagicMock(id="celery-tts-uuid-777")

        # Mock DB async session returning valid Transcript
        mock_db = AsyncMock()
        mock_transcript_obj = Transcript(
            id=mock_transcript_id,
            project_id=mock_project_id,
            detected_language="en",
            status="completed",
        )
        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one_or_none.return_value = mock_transcript_obj
        mock_db.execute = AsyncMock(return_value=mock_exec_res)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            req_body = {
                "transcript_id": str(mock_transcript_id),
                "target_language": "es",
                "project_id": str(mock_project_id),
            }
            parsed_req = SynthesizeProjectTTSRequest(**req_body)
            assert parsed_req.transcript_id == mock_transcript_id
            assert parsed_req.target_language == "es"
            assert parsed_req.project_id == mock_project_id

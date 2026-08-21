import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.models.transcript import Transcript, TranscriptSegment
from app.models.translation import Translation
from app.schemas.translation_schema import TranslateProjectRequest, TranslateSegmentRequest
from app.services.duration_matcher import duration_matcher
from app.utils.speech_rate import speech_rate_estimator


# =============================================================================
# 1. SPEECH RATE & DURATION ESTIMATION UNIT TESTS
# =============================================================================
def test_speech_rate_duration_estimation():
    # English duration test
    en_text = "Welcome to our global conference presentation."
    en_dur_ms = speech_rate_estimator.estimate_speech_duration_ms(en_text, "en")
    assert 2000 <= en_dur_ms <= 4000

    # Spanish duration test (syllable rate is higher ~6.8/s, text typically has more syllables)
    es_text = "Bienvenidos a nuestra presentación de la conferencia global."
    es_dur_ms = speech_rate_estimator.estimate_speech_duration_ms(es_text, "es")
    assert 2200 <= es_dur_ms <= 4500

    # Japanese character-based test
    ja_text = "世界会議のプレゼンテーションへようこそ。"
    ja_dur_ms = speech_rate_estimator.estimate_speech_duration_ms(ja_text, "ja")
    assert 1500 <= ja_dur_ms <= 3500

    # Punctuation pause test: commas and periods should increase speaking time
    text_with_pauses = "Hello, everyone. Welcome, to our event! Are you ready?"
    text_without_pauses = "Hello everyone Welcome to our event Are you ready"
    dur_with = speech_rate_estimator.estimate_speech_duration_ms(text_with_pauses, "en")
    dur_without = speech_rate_estimator.estimate_speech_duration_ms(text_without_pauses, "en")
    assert dur_with > dur_without


def test_duration_delta_calculation():
    orig_ms = 3000

    # 1. Exact match / Within ±10% tolerance (3150ms is +5%)
    ratio, status = speech_rate_estimator.calculate_duration_delta(orig_ms, 3150, tolerance=0.10)
    assert ratio == 1.05
    assert status == "within_tolerance"

    # 2. Too Long (3800ms is +26.7%)
    ratio, status = speech_rate_estimator.calculate_duration_delta(orig_ms, 3800, tolerance=0.10)
    assert ratio == 1.267
    assert status == "too_long"

    # 3. Too Short (2200ms is -26.7%)
    ratio, status = speech_rate_estimator.calculate_duration_delta(orig_ms, 2200, tolerance=0.10)
    assert ratio == 0.733
    assert status == "too_short"


# =============================================================================
# 2. DURATION MATCHER & ITERATIVE FEEDBACK TESTS
# =============================================================================
@pytest.mark.asyncio
async def test_duration_matcher_flow():
    source_text = "Hello and welcome to the global launch presentation."
    orig_duration_ms = 3600

    result = await duration_matcher.translate_with_duration_matching(
        source_text=source_text,
        original_duration_ms=orig_duration_ms,
        source_language="en",
        target_language="es",
        speaker_tag="Speaker 1",
        tolerance=0.10,
        max_iterations=3,
    )

    assert result.translated_text is not None
    assert len(result.translated_text) > 0
    assert result.target_language == "es"
    assert result.estimated_duration_ms > 0
    assert result.confidence_score >= 0.70
    assert len(result.iteration_history) >= 1


# =============================================================================
# 3. FASTAPI TRANSLATION ROUTE TESTS
# =============================================================================
@pytest.mark.asyncio
async def test_translate_project_endpoint():
    transport = ASGITransport(app=app)
    mock_transcript_id = uuid.uuid4()

    with patch("app.routers.translation.select") as mock_select, \
         patch("app.routers.translation.translate_project_batch_task.apply_async") as mock_task:
        
        mock_task.return_value = MagicMock(id="celery-trans-uuid-999")

        # Mock DB async session returning valid Transcript
        mock_db = AsyncMock()
        mock_transcript_obj = Transcript(
            id=mock_transcript_id,
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
                "source_language": "en",
                "tone": "natural",
            }
            parsed_req = TranslateProjectRequest(**req_body)
            assert parsed_req.transcript_id == mock_transcript_id
            assert parsed_req.target_language == "es"

import ast
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.schemas.translation_schema import TranslateProjectRequest, TranslateSegmentRequest
from app.routers.translation import _format_translation_item
from app.utils.speech_rate import speech_rate_estimator

DURATION_MATCHER_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "duration_matcher.py"


class DurationMatchedTranslationResult:
    def __init__(
        self,
        source_text: str,
        translated_text: str,
        source_language: str,
        target_language: str,
        original_duration_ms: int,
        estimated_duration_ms: int,
        duration_ratio: float,
        duration_status: str,
        iterations_count: int,
        confidence_score: float,
        is_cached: bool,
        total_cost_usd: float,
        iteration_history: List[Dict[str, Any]],
    ):
        self.source_text = source_text
        self.translated_text = translated_text
        self.source_language = source_language
        self.target_language = target_language
        self.original_duration_ms = original_duration_ms
        self.estimated_duration_ms = estimated_duration_ms
        self.duration_ratio = duration_ratio
        self.duration_status = duration_status
        self.iterations_count = iterations_count
        self.confidence_score = confidence_score
        self.is_cached = is_cached
        self.total_cost_usd = total_cost_usd
        self.iteration_history = iteration_history


def load_translate_with_duration_matching(
    provider: str = "google",
    google_response=None,
    cached_data=None,
):
    source = DURATION_MATCHER_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    method_node = None
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "DurationMatcher":
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "translate_with_duration_matching":
                    method_node = item
                    break

    if method_node is None:
        raise AssertionError("Could not find DurationMatcher.translate_with_duration_matching")

    method_node.decorator_list = []
    extracted_module = ast.Module(body=[method_node], type_ignores=[])
    ast.fix_missing_locations(extracted_module)

    google_mock = AsyncMock(return_value=google_response or "Bienvenidos a la presentación global.")
    get_from_cache = AsyncMock(return_value=cached_data)
    save_to_cache = AsyncMock()

    namespace = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "DurationMatchedTranslationResult": DurationMatchedTranslationResult,
        "speech_rate_estimator": speech_rate_estimator,
        "settings": SimpleNamespace(TRANSLATION_PROVIDER=provider),
        "google_translate_service": SimpleNamespace(translate_text=google_mock),
    }
    exec(compile(extracted_module, str(DURATION_MATCHER_PATH), "exec"), namespace)

    cls = SimpleNamespace(
        _generate_cache_key=lambda **kwargs: "cache-key",
        _get_from_cache=get_from_cache,
        _save_to_cache=save_to_cache,
    )
    return namespace["translate_with_duration_matching"], cls, google_mock, save_to_cache


# =============================================================================
# 1. SPEECH RATE & DURATION ESTIMATION UNIT TESTS
# =============================================================================
def test_speech_rate_duration_estimation():
    en_text = "Welcome to our global conference presentation."
    en_dur_ms = speech_rate_estimator.estimate_speech_duration_ms(en_text, "en")
    assert 2000 <= en_dur_ms <= 4000

    es_text = "Bienvenidos a nuestra presentación de la conferencia global."
    es_dur_ms = speech_rate_estimator.estimate_speech_duration_ms(es_text, "es")
    assert 2200 <= es_dur_ms <= 4500

    ja_text = "世界会議のプレゼンテーションへようこそ。"
    ja_dur_ms = speech_rate_estimator.estimate_speech_duration_ms(ja_text, "ja")
    assert 1500 <= ja_dur_ms <= 3500

    text_with_pauses = "Hello, everyone. Welcome, to our event! Are you ready?"
    text_without_pauses = "Hello everyone Welcome to our event Are you ready"
    dur_with = speech_rate_estimator.estimate_speech_duration_ms(text_with_pauses, "en")
    dur_without = speech_rate_estimator.estimate_speech_duration_ms(text_without_pauses, "en")
    assert dur_with > dur_without


def test_duration_delta_calculation():
    orig_ms = 3000

    ratio, status = speech_rate_estimator.calculate_duration_delta(orig_ms, 3150, tolerance=0.10)
    assert ratio == 1.05
    assert status == "within_tolerance"

    ratio, status = speech_rate_estimator.calculate_duration_delta(orig_ms, 3800, tolerance=0.10)
    assert ratio == 1.267
    assert status == "too_long"

    ratio, status = speech_rate_estimator.calculate_duration_delta(orig_ms, 2200, tolerance=0.10)
    assert ratio == 0.733
    assert status == "too_short"


# =============================================================================
# 2. DURATION MATCHER FLOW TESTS
# =============================================================================
def test_duration_matcher_flow(google_translate_text_response) -> None:
    translate_with_duration_matching, cls, google_mock, save_to_cache = load_translate_with_duration_matching(
        google_response=google_translate_text_response,
    )

    result = asyncio.run(
        translate_with_duration_matching(
            cls=cls,
            source_text="Hello and welcome to the global launch presentation.",
            original_duration_ms=3600,
            source_language="en",
            target_language="es",
            speaker_tag="Speaker 1",
            tolerance=0.10,
            max_iterations=3,
        )
    )

    assert result.translated_text
    assert result.target_language == "es"
    assert result.estimated_duration_ms > 0
    assert result.confidence_score >= 0.70
    assert len(result.iteration_history) >= 1
    assert result.total_cost_usd == 0
    assert google_mock.await_count == 1
    assert save_to_cache.await_count == 1


def test_duration_matcher_cache_hit_skips_provider_calls(translation_cache_hit_payload) -> None:
    translate_with_duration_matching, cls, google_mock, save_to_cache = load_translate_with_duration_matching(
        cached_data=translation_cache_hit_payload,
    )

    result = asyncio.run(
        translate_with_duration_matching(
            cls=cls,
            source_text="Hello and welcome to the global launch presentation.",
            original_duration_ms=1500,
            source_language="en",
            target_language="es",
            speaker_tag="Speaker 1",
            tolerance=0.10,
            max_iterations=3,
        )
    )

    assert result.translated_text == translation_cache_hit_payload["translated_text"]
    assert result.is_cached is True
    assert result.total_cost_usd == 0.0
    assert result.iterations_count == 1
    assert result.iteration_history[0]["status"] == "cache_hit"
    assert google_mock.await_count == 0
    assert save_to_cache.await_count == 0



def test_duration_matcher_google_provider_single_pass(google_translate_text_response) -> None:
    translate_with_duration_matching, cls, google_mock, save_to_cache = load_translate_with_duration_matching(
        google_response=google_translate_text_response,
    )

    result = asyncio.run(
        translate_with_duration_matching(
            cls=cls,
            source_text="Hello and welcome to the global launch presentation.",
            original_duration_ms=3600,
            source_language="en",
            target_language="es",
            speaker_tag="Speaker 1",
            tolerance=0.10,
            max_iterations=3,
        )
    )

    assert result.translated_text == google_translate_text_response
    assert result.total_cost_usd == 0.0
    assert len(result.iteration_history) == 1
    assert google_mock.await_count == 1
    assert save_to_cache.await_count == 1


@pytest.mark.parametrize(
    ("generated_audio", "expected_status"),
    [([SimpleNamespace(status="completed")], "completed"), ([], None)],
)
def test_single_segment_response_handles_generated_audio_state(generated_audio, expected_status) -> None:
    segment = SimpleNamespace(
        id=uuid.uuid4(),
        sequence_order=2,
        speaker_tag="Speaker 1",
        start_time_seconds=1.0,
        end_time_seconds=2.5,
    )
    translation = SimpleNamespace(
        id=uuid.uuid4(),
        original_duration_ms=1500,
        estimated_duration_ms=1480,
        duration_ratio=0.987,
        iterations_count=1,
        confidence_score=0.96,
        is_cached=False,
        is_user_edited=False,
        source_text="Hello",
        translated_text="Hola",
        generated_audio=generated_audio,
        created_at=datetime.now(timezone.utc),
    )

    response = _format_translation_item(translation, segment)

    assert response.generated_audio_status == expected_status
    assert response.segment_id == segment.id
    assert response.translated_text == "Hola"


# =============================================================================
# 3. TRANSLATION REQUEST SCHEMA TESTS
# =============================================================================
def test_translate_request_schemas() -> None:
    transcript_id = uuid.uuid4()
    segment_id = uuid.uuid4()

    project_request = TranslateProjectRequest(
        transcript_id=transcript_id,
        target_language="ES",
        source_language="en-US",
        tone="natural",
    )
    segment_request = TranslateSegmentRequest(
        segment_id=segment_id,
        source_text="Welcome to our global conference.",
        original_duration_ms=3500,
        source_language="en",
        target_language="es",
        speaker_tag="Speaker 1",
        previous_context="Intro",
        next_context="Closing",
    )

    assert project_request.transcript_id == transcript_id
    assert project_request.source_language == "en"
    assert project_request.target_language == "es"
    assert segment_request.segment_id == segment_id
    assert segment_request.original_duration_ms == 3500
    assert segment_request.previous_context == "Intro"
    assert segment_request.next_context == "Closing"



def test_translate_request_schemas_reject_unsupported_language_codes() -> None:
    transcript_id = uuid.uuid4()
    segment_id = uuid.uuid4()

    with pytest.raises(ValidationError, match="Unsupported language code"):
        TranslateProjectRequest(
            transcript_id=transcript_id,
            target_language="xx",
            source_language="en",
        )

    with pytest.raises(ValidationError, match="Unsupported language code"):
        TranslateSegmentRequest(
            segment_id=segment_id,
            source_text="Welcome to our global conference.",
            original_duration_ms=3500,
            source_language="zz",
            target_language="es",
        )

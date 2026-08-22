import ast
import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.schemas.translation_schema import TranslateProjectRequest, TranslateSegmentRequest
from app.utils.prompt_templates import (
    get_refinement_condensation_prompt,
    get_refinement_expansion_prompt,
    get_segment_translation_user_prompt,
    get_system_translation_prompt,
)
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
    provider: str = "openai",
    openai_response=None,
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

    openai_mock = AsyncMock(
        return_value=openai_response or ("Bienvenidos a la presentación global.", 12, 34, 0.123456)
    )
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
        "get_system_translation_prompt": lambda src, tgt: f"system:{src}:{tgt}",
        "get_segment_translation_user_prompt": lambda **kwargs: f"translate:{kwargs['original_text']}",
        "get_refinement_condensation_prompt": lambda **kwargs: "condense",
        "get_refinement_expansion_prompt": lambda **kwargs: "expand",
        "settings": SimpleNamespace(TRANSLATION_PROVIDER=provider),
        "openai_service": SimpleNamespace(generate_chat_completion=openai_mock),
        "google_translate_service": SimpleNamespace(translate_text=google_mock),
    }
    exec(compile(extracted_module, str(DURATION_MATCHER_PATH), "exec"), namespace)

    cls = SimpleNamespace(
        _generate_cache_key=lambda **kwargs: "cache-key",
        _get_from_cache=get_from_cache,
        _save_to_cache=save_to_cache,
    )
    return namespace["translate_with_duration_matching"], cls, openai_mock, google_mock, save_to_cache


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
def test_duration_matcher_flow(openai_chat_completion_response) -> None:
    translate_with_duration_matching, cls, openai_mock, _google_mock, save_to_cache = load_translate_with_duration_matching(
        provider="openai",
        openai_response=openai_chat_completion_response,
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
    assert result.total_cost_usd > 0
    assert openai_mock.await_count == len(result.iteration_history)
    assert save_to_cache.await_count == 1


def test_duration_matcher_cache_hit_skips_provider_calls(translation_cache_hit_payload) -> None:
    translate_with_duration_matching, cls, openai_mock, google_mock, save_to_cache = load_translate_with_duration_matching(
        provider="openai",
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
    assert openai_mock.await_count == 0
    assert google_mock.await_count == 0
    assert save_to_cache.await_count == 0



def test_duration_matcher_google_provider_single_pass(google_translate_text_response) -> None:
    translate_with_duration_matching, cls, openai_mock, google_mock, save_to_cache = load_translate_with_duration_matching(
        provider="google",
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
    assert openai_mock.await_count == 0
    assert google_mock.await_count == 1
    assert save_to_cache.await_count == 1


# =============================================================================
# 3. TRANSLATION PROMPT REGRESSION TESTS
# =============================================================================
def test_hindi_system_translation_prompt_prefers_natural_semantic_translation() -> None:
    prompt = get_system_translation_prompt("en", "hi")

    assert "HINDI-SPECIFIC GUIDANCE" in prompt
    assert "Prioritize meaning, intent, and flow over word-for-word correspondence with the source." in prompt
    assert "Resolve English discourse patterns into clean Hindi sentence structure instead of preserving English syntax." in prompt
    assert "My name is Namrata, and we are going to explore retrieval augmented generation today." in prompt
    assert "मेरा नाम नम्रता है, और आज हम रिट्रीवल ऑगमेंटेड जेनरेशन को समझेंगे।" in prompt



def test_segment_translation_prompt_prefers_natural_target_language_rendering() -> None:
    prompt = get_segment_translation_user_prompt(
        original_text="My name is Namrata, and we are going to explore retrieval augmented generation today.",
        target_duration_ms=4200,
        previous_context="Welcome to the session.",
        next_context="Let's get started.",
        speaker_tag="Host",
    )

    assert 'Previous Dialogue Context: "Welcome to the session."' in prompt
    assert 'Following Dialogue Context: "Let\'s get started."' in prompt
    assert "Speaker: Host" in prompt
    assert "Target Spoken Duration: approximately 4200 ms" in prompt
    assert "Prefer a natural, meaning-preserving sentence in the target language over a literal word-by-word rendering." in prompt



def test_refinement_condensation_prompt_preserves_meaning_while_shortening() -> None:
    prompt = get_refinement_condensation_prompt(
        current_translation="मेरा नाम नम्रता है, और आज हम रिट्रीवल ऑगमेंटेड जेनरेशन के बारे में विस्तार से बात करेंगे।",
        original_text="My name is Namrata, and today we will explore retrieval augmented generation in detail.",
        target_duration_ms=4200,
        estimated_duration_ms=5100,
        excess_pct=21.4,
    )

    assert "The previous translation is too long" in prompt
    assert 'Original Text: "My name is Namrata, and today we will explore retrieval augmented generation in detail."' in prompt
    assert 'Previous Translation: "मेरा नाम नम्रता है, और आज हम रिट्रीवल ऑगमेंटेड जेनरेशन के बारे में विस्तार से बात करेंगे।"' in prompt
    assert "Current Estimated Duration: 5100 ms (approximately 21.4% too long)" in prompt
    assert "while retaining the essential message and emotional tone" in prompt
    assert "Use more concise phrasing, omit non-essential filler words, or use shorter synonyms." in prompt
    assert "Provide ONLY the revised translation." in prompt



def test_refinement_expansion_prompt_preserves_natural_delivery() -> None:
    prompt = get_refinement_expansion_prompt(
        current_translation="आज हम रिट्रीवल ऑगमेंटेड जेनरेशन समझेंगे।",
        original_text="Today we will explore retrieval augmented generation.",
        target_duration_ms=4200,
        estimated_duration_ms=3000,
        deficit_pct=28.6,
    )

    assert "The previous translation is too short" in prompt
    assert 'Original Text: "Today we will explore retrieval augmented generation."' in prompt
    assert 'Previous Translation: "आज हम रिट्रीवल ऑगमेंटेड जेनरेशन समझेंगे।"' in prompt
    assert "Current Estimated Duration: 3000 ms (approximately 28.6% too short)" in prompt
    assert "Please slightly expand the translation with natural phrasing" in prompt
    assert "without padding with nonsense" in prompt
    assert "Provide ONLY the revised translation." in prompt


# =============================================================================
# 4. TRANSLATION REQUEST SCHEMA TESTS
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

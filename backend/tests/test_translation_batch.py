import ast
import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional
from unittest.mock import AsyncMock

TRANSLATION_SERVICE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "translation_service.py"


@dataclass
class FakeTranscriptSegment:
    id: uuid.UUID
    duration_seconds: float
    text: str
    speaker_tag: str


class FakeTranslation:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def load_translate_segments_batch_async(duration_matcher_mock: AsyncMock):
    source = TRANSLATION_SERVICE_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    method_node = None
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "TranslationService":
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "translate_segments_batch_async":
                    method_node = item
                    break

    if method_node is None:
        raise AssertionError("Could not find TranslationService.translate_segments_batch_async")

    method_node.decorator_list = []
    extracted_module = ast.Module(body=[method_node], type_ignores=[])
    ast.fix_missing_locations(extracted_module)

    namespace = {
        "asyncio": asyncio,
        "uuid": uuid,
        "List": List,
        "Optional": Optional,
        "TranscriptSegment": FakeTranscriptSegment,
        "Translation": FakeTranslation,
        "duration_matcher": SimpleNamespace(translate_with_duration_matching=duration_matcher_mock),
    }
    exec(compile(extracted_module, str(TRANSLATION_SERVICE_PATH), "exec"), namespace)
    return namespace["translate_segments_batch_async"]


def make_segment(text: str, duration_seconds: float, speaker_tag: str = "Speaker 1") -> FakeTranscriptSegment:
    return FakeTranscriptSegment(
        id=uuid.uuid4(),
        duration_seconds=duration_seconds,
        text=text,
        speaker_tag=speaker_tag,
    )


def test_translate_segments_batch_async_passes_context_and_builds_translations(openai_batch_results) -> None:
    segments = [
        make_segment("Hello there", 1.2, "Speaker 1"),
        make_segment("How are you", 1.6, "Speaker 2"),
        make_segment("Goodbye now", 1.0, "Speaker 1"),
    ]
    project_id = uuid.uuid4()

    duration_matcher_mock = AsyncMock(side_effect=openai_batch_results)
    translate_segments_batch_async = load_translate_segments_batch_async(duration_matcher_mock)

    translations = asyncio.run(
        translate_segments_batch_async(
            cls=SimpleNamespace(),
            segments=segments,
            source_language="en",
            target_language="es",
            project_id=project_id,
            concurrency_limit=2,
        )
    )

    assert len(translations) == 3
    assert [t.translated_text for t in translations] == ["Hola", "Cómo estás", "Adiós"]
    assert [t.target_language for t in translations] == ["es", "es", "es"]
    assert [t.project_id for t in translations] == [project_id, project_id, project_id]
    assert [float(t.speed_adjustment_factor) for t in translations] == [0.983, 1.062, 0.98]

    first_call = duration_matcher_mock.await_args_list[0].kwargs
    second_call = duration_matcher_mock.await_args_list[1].kwargs
    third_call = duration_matcher_mock.await_args_list[2].kwargs

    assert first_call["source_text"] == "Hello there"
    assert first_call["previous_context"] is None
    assert first_call["next_context"] == "How are you"
    assert first_call["speaker_tag"] == "Speaker 1"

    assert second_call["previous_context"] == "Hello there"
    assert second_call["next_context"] == "Goodbye now"
    assert second_call["speaker_tag"] == "Speaker 2"

    assert third_call["previous_context"] == "How are you"
    assert third_call["next_context"] is None


def test_translate_segments_batch_async_clamps_speed_adjustment_factor() -> None:
    segments = [
        make_segment("Short", 1.0),
        make_segment("Long", 1.0),
    ]

    duration_matcher_mock = AsyncMock(
        side_effect=[
            SimpleNamespace(
                translated_text="Breve",
                original_duration_ms=1000,
                estimated_duration_ms=500,
                duration_ratio=0.5,
                iterations_count=1,
                confidence_score=0.9,
                is_cached=False,
                iteration_history=[{"iteration": 1}],
            ),
            SimpleNamespace(
                translated_text="Extenso",
                original_duration_ms=1000,
                estimated_duration_ms=1700,
                duration_ratio=1.7,
                iterations_count=1,
                confidence_score=0.9,
                is_cached=False,
                iteration_history=[{"iteration": 1}],
            ),
        ]
    )
    translate_segments_batch_async = load_translate_segments_batch_async(duration_matcher_mock)

    translations = asyncio.run(
        translate_segments_batch_async(
            cls=SimpleNamespace(),
            segments=segments,
            source_language="en",
            target_language="es",
        )
    )

    assert float(translations[0].speed_adjustment_factor) == 0.8
    assert float(translations[1].speed_adjustment_factor) == 1.25


def test_translate_segments_batch_async_with_google_fixture_results(google_batch_results) -> None:
    segments = [
        make_segment("Hello there", 1.2, "Speaker 1"),
        make_segment("How are you", 1.6, "Speaker 2"),
        make_segment("See you", 1.0, "Speaker 1"),
    ]

    duration_matcher_mock = AsyncMock(side_effect=google_batch_results)
    translate_segments_batch_async = load_translate_segments_batch_async(duration_matcher_mock)

    translations = asyncio.run(
        translate_segments_batch_async(
            cls=SimpleNamespace(),
            segments=segments,
            source_language="en",
            target_language="es",
        )
    )

    assert [t.translated_text for t in translations] == ["Hola", "Qué tal", "Hasta luego"]
    assert [t.is_cached for t in translations] == [False, False, False]
    assert [round(float(t.quality_score), 3) for t in translations] == [0.99, 0.99, 0.99]

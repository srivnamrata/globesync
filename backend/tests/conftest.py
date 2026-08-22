from types import SimpleNamespace

import pytest


def make_duration_match_result(
    translated_text: str,
    original_duration_ms: int,
    estimated_duration_ms: int,
    duration_ratio: float,
    iterations_count: int = 1,
    confidence_score: float = 0.95,
    is_cached: bool = False,
    iteration_history=None,
):
    return SimpleNamespace(
        translated_text=translated_text,
        original_duration_ms=original_duration_ms,
        estimated_duration_ms=estimated_duration_ms,
        duration_ratio=duration_ratio,
        iterations_count=iterations_count,
        confidence_score=confidence_score,
        is_cached=is_cached,
        iteration_history=iteration_history or [{"iteration": 1}],
    )


@pytest.fixture
def openai_chat_completion_response():
    return ("Bienvenidos a la presentación global.", 12, 34, 0.123456)


@pytest.fixture
def google_translate_text_response():
    return "Bienvenidos a la presentación global."


@pytest.fixture
def translation_cache_hit_payload():
    return {
        "translated_text": "Texto cacheado",
        "target_language": "es",
        "estimated_duration_ms": 1420,
    }


@pytest.fixture
def openai_batch_results():
    return [
        make_duration_match_result("Hola", 1200, 1180, 0.983, confidence_score=0.97),
        make_duration_match_result(
            "Cómo estás",
            1600,
            1700,
            1.062,
            iterations_count=2,
            confidence_score=0.95,
            is_cached=True,
            iteration_history=[{"iteration": 1}, {"iteration": 2}],
        ),
        make_duration_match_result("Adiós", 1000, 980, 0.98, confidence_score=0.96),
    ]


@pytest.fixture
def google_batch_results():
    return [
        make_duration_match_result("Hola", 1200, 1210, 1.008, confidence_score=0.99, is_cached=False),
        make_duration_match_result("Qué tal", 1600, 1580, 0.988, confidence_score=0.99, is_cached=False),
        make_duration_match_result("Hasta luego", 1000, 1015, 1.015, confidence_score=0.99, is_cached=False),
    ]

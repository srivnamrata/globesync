import ast
import hashlib
import json
from pathlib import Path
from typing import Optional

DURATION_MATCHER_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "duration_matcher.py"


def load_generate_cache_key():
    source = DURATION_MATCHER_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    method_node = None
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "DurationMatcher":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_generate_cache_key":
                    method_node = item
                    break

    if method_node is None:
        raise AssertionError("Could not find DurationMatcher._generate_cache_key")

    method_node.decorator_list = []
    extracted_module = ast.Module(body=[method_node], type_ignores=[])
    ast.fix_missing_locations(extracted_module)

    namespace = {"hashlib": hashlib, "json": json, "Optional": Optional}
    exec(compile(extracted_module, str(DURATION_MATCHER_PATH), "exec"), namespace)
    return namespace["_generate_cache_key"]


def test_generate_cache_key_is_stable_for_identical_inputs() -> None:
    generate_cache_key = load_generate_cache_key()

    key_a = generate_cache_key(
        text="Hello world",
        src="en",
        tgt="es",
        provider="openai",
        original_duration_ms=1000,
        speaker_tag="Speaker 1",
        previous_context="Greeting",
        next_context="Follow-up",
        tolerance=0.10,
        max_iterations=3,
    )
    key_b = generate_cache_key(
        text="Hello world",
        src="en",
        tgt="es",
        provider="openai",
        original_duration_ms=1000,
        speaker_tag="Speaker 1",
        previous_context="Greeting",
        next_context="Follow-up",
        tolerance=0.10,
        max_iterations=3,
    )

    assert key_a == key_b
    assert key_a.startswith("cache:trans:openai:en:es:")


def test_generate_cache_key_changes_for_duration_sensitive_inputs() -> None:
    generate_cache_key = load_generate_cache_key()

    base_kwargs = {
        "text": "Hello world",
        "src": "en",
        "tgt": "es",
        "provider": "openai",
        "original_duration_ms": 1000,
        "speaker_tag": "Speaker 1",
        "previous_context": "Greeting",
        "next_context": "Follow-up",
        "tolerance": 0.10,
        "max_iterations": 3,
    }

    base_key = generate_cache_key(**base_kwargs)

    assert base_key != generate_cache_key(**{**base_kwargs, "original_duration_ms": 1400})
    assert base_key != generate_cache_key(**{**base_kwargs, "tolerance": 0.15})
    assert base_key != generate_cache_key(**{**base_kwargs, "previous_context": "Intro"})
    assert base_key != generate_cache_key(**{**base_kwargs, "speaker_tag": "Speaker 2"})
    assert base_key != generate_cache_key(**{**base_kwargs, "max_iterations": 5})

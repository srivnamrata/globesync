import ast
import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

TRANSLATION_TASKS_PATH = Path(__file__).resolve().parents[1] / "app" / "tasks" / "translation_tasks.py"


class FakeField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def in_(self, values):
        return ("in", self.name, list(values))


class FakeTranscriptSegmentModel:
    transcript_id = FakeField("transcript_id")
    sequence_order = FakeField("sequence_order")


class FakeTranslationModel:
    transcript_segment_id = FakeField("transcript_segment_id")
    target_language = FakeField("target_language")


class FakeQuery:
    def __init__(self, model, segments, recorder):
        self.model = model
        self.segments = segments
        self.recorder = recorder

    def filter(self, *conditions):
        if self.model is FakeTranscriptSegmentModel:
            self.recorder["segment_filters"] = list(conditions)
        else:
            self.recorder["translation_filters"] = list(conditions)
        return self

    def order_by(self, *columns):
        self.recorder["order_by"] = list(columns)
        return self

    def all(self):
        return list(self.segments)

    def delete(self, synchronize_session=False):
        self.recorder["delete_called"] = True
        self.recorder["synchronize_session"] = synchronize_session
        return len(self.segments)


class FakeSession:
    def __init__(self, segments, commit_side_effect=None):
        self.segments = segments
        self.commit_side_effect = commit_side_effect
        self.recorder = {}
        self.added = []
        self.commit_called = False
        self.rollback_called = False
        self.close_called = False

    def query(self, model):
        return FakeQuery(model, self.segments, self.recorder)

    def add(self, entity):
        self.added.append(entity)

    def commit(self):
        self.commit_called = True
        if self.commit_side_effect:
            raise self.commit_side_effect

    def rollback(self):
        self.rollback_called = True

    def close(self):
        self.close_called = True


class RetryCalled(Exception):
    def __init__(self, original_exc):
        super().__init__(str(original_exc))
        self.original_exc = original_exc


def build_task(session, translate_side_effect, published_events, time_values):
    source = TRANSLATION_TASKS_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    task_node = None
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "translate_project_batch_task":
            task_node = node
            break

    if task_node is None:
        raise AssertionError("Could not find translate_project_batch_task")

    task_node.decorator_list = []
    extracted_module = ast.Module(body=[task_node], type_ignores=[])
    ast.fix_missing_locations(extracted_module)

    translate_mock = AsyncMock(side_effect=translate_side_effect)
    time_iter = iter(time_values)

    namespace = {
        "asyncio": asyncio,
        "uuid": uuid,
        "TranscriptSegment": FakeTranscriptSegmentModel,
        "Translation": FakeTranslationModel,
        "translation_service": SimpleNamespace(translate_segments_batch_async=translate_mock),
        "checkpoint_operation": lambda *args, **kwargs: None,
        "publish_translation_event": lambda transcript_id, status, progress_percent, message: published_events.append(
            {
                "transcript_id": transcript_id,
                "status": status,
                "progress_percent": progress_percent,
                "message": message,
            }
        ),
        "SyncSession": lambda: session,
        "time": SimpleNamespace(time=lambda: next(time_iter)),
        "logger": SimpleNamespace(error=lambda *args, **kwargs: None),
        "Optional": __import__("typing").Optional,
    }
    exec(compile(extracted_module, str(TRANSLATION_TASKS_PATH), "exec"), namespace)
    return namespace["translate_project_batch_task"], translate_mock


def test_translate_project_batch_task_replaces_existing_translations_and_commits() -> None:
    transcript_id = uuid.uuid4()
    segment_a = SimpleNamespace(id=uuid.uuid4())
    segment_b = SimpleNamespace(id=uuid.uuid4())
    session = FakeSession(segments=[segment_a, segment_b])
    published_events = []
    translated_entities = [SimpleNamespace(name="first"), SimpleNamespace(name="second")]

    task, translate_mock = build_task(
        session=session,
        translate_side_effect=[translated_entities],
        published_events=published_events,
        time_values=[100.0, 104.25],
    )

    self_obj = SimpleNamespace(retry=MagicMock())
    result = task(
        self_obj,
        transcript_id_str=str(transcript_id),
        source_language="en",
        target_language="es",
        project_id_str=None,
    )

    assert result["status"] == "completed"
    assert result["segments_translated"] == 2
    assert result["execution_duration_sec"] == 4.25
    assert session.recorder["delete_called"] is True
    assert session.recorder["synchronize_session"] is False
    assert session.commit_called is True
    assert session.rollback_called is False
    assert session.close_called is True
    assert session.added == translated_entities
    assert published_events[-1]["status"] == "completed"

    translation_call = translate_mock.await_args.kwargs
    assert translation_call["segments"] == [segment_a, segment_b]
    assert translation_call["source_language"] == "en"
    assert translation_call["target_language"] == "es"
    assert translation_call["project_id"] is None
    assert translation_call["concurrency_limit"] == 10


def test_translate_project_batch_task_rolls_back_and_retries_on_commit_failure() -> None:
    transcript_id = uuid.uuid4()
    session = FakeSession(
        segments=[SimpleNamespace(id=uuid.uuid4())],
        commit_side_effect=RuntimeError("commit failed"),
    )
    published_events = []
    translated_entities = [SimpleNamespace(name="translated")]

    task, _translate_mock = build_task(
        session=session,
        translate_side_effect=[translated_entities],
        published_events=published_events,
        time_values=[200.0],
    )

    def raise_retry(exc):
        raise RetryCalled(exc)

    self_obj = SimpleNamespace(retry=MagicMock(side_effect=raise_retry))

    with pytest.raises(RetryCalled) as exc_info:
        task(
            self_obj,
            transcript_id_str=str(transcript_id),
            source_language="en",
            target_language="fr",
            project_id_str=None,
        )

    assert str(exc_info.value.original_exc) == "commit failed"
    assert session.commit_called is True
    assert session.rollback_called is True
    assert session.close_called is True
    assert published_events[-1]["status"] == "failed"
    assert "commit failed" in published_events[-1]["message"]

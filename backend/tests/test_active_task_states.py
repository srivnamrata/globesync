import ast
import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.pipeline_operation_service import checkpoint_operation


TRANCRIPTION_TASKS_PATH = Path(__file__).resolve().parents[1] / "app" / "tasks" / "transcription_tasks.py"
TRANSLATION_TASKS_PATH = Path(__file__).resolve().parents[1] / "app" / "tasks" / "translation_tasks.py"
TTS_TASKS_PATH = Path(__file__).resolve().parents[1] / "app" / "tasks" / "tts_tasks.py"


class FakeField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def in_(self, values):
        return ("in", self.name, list(values))


class FakeQuery:
    def __init__(self, session, model, rows):
        self.session = session
        self.model = model
        self.rows = rows
        self.filters = []
        self.order_by_args = []
        self.options_args = []

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def order_by(self, *columns):
        self.order_by_args.extend(columns)
        return self

    def options(self, *args):
        self.options_args.extend(args)
        return self

    def first(self):
        values = self.rows.get(self.model, [])
        if isinstance(values, list):
            return values[0] if values else None
        return values

    def all(self):
        values = self.rows.get(self.model, [])
        if isinstance(values, list):
            return list(values)
        if values is None:
            return []
        return [values]

    def delete(self, synchronize_session=False):
        self.session.deleted.append(
            {
                "model": self.model,
                "filters": list(self.filters),
                "synchronize_session": synchronize_session,
            }
        )
        values = self.rows.get(self.model, [])
        return len(values) if isinstance(values, list) else int(values is not None)


class FakeSession:
    def __init__(self, rows=None, operation=None, commit_side_effects=None):
        self.rows = rows or {}
        self.operation = operation
        self.commit_side_effects = commit_side_effects or {}
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0
        self.added = []
        self.deleted = []
        self.get_calls = []
        self.query_calls = []

    def query(self, model):
        self.query_calls.append(model)
        return FakeQuery(self, model, self.rows)

    def add(self, entity):
        self.added.append(entity)

    def commit(self):
        self.commit_count += 1
        side_effect = self.commit_side_effects.get(self.commit_count)
        if side_effect is not None:
            raise side_effect

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1

    def get(self, model, identifier):
        self.get_calls.append((model, identifier))
        if self.operation is not None and getattr(self.operation, "id", None) == identifier:
            return self.operation
        return None


class RetryCalled(Exception):
    def __init__(self, original_exc):
        super().__init__(str(original_exc))
        self.original_exc = original_exc


class FakeMediaFileModel:
    id = FakeField("id")


class FakeTranscriptModel:
    id = FakeField("id")
    media_file_id = FakeField("media_file_id")
    project_id = FakeField("project_id")
    workspace_id = FakeField("workspace_id")


class FakeTranscriptSegmentModel:
    transcript_id = FakeField("transcript_id")
    sequence_order = FakeField("sequence_order")

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeTranslationModel:
    transcript_segment_id = FakeField("transcript_segment_id")
    target_language = FakeField("target_language")
    segment = FakeField("segment")

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeGeneratedAudioModel:
    translation_id = FakeField("translation_id")


def load_function(path: Path, function_name: str, namespace: dict):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    target = None
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            target = node
            break
    if target is None:
        raise AssertionError(f"Could not find {function_name}")
    target.decorator_list = []
    extracted = ast.Module(body=[target], type_ignores=[])
    ast.fix_missing_locations(extracted)
    exec(compile(extracted, str(path), "exec"), namespace)
    return namespace[function_name]


def _translation_response(segment, translated_text):
    return SimpleNamespace(
        id=uuid.uuid4(),
        transcript_segment_id=segment.id,
        project_id=getattr(segment, "project_id", None),
        workspace_id=getattr(segment, "workspace_id", None),
        request_id=None,
        task_id=None,
        idempotency_key=None,
        source_language="en",
        target_language="es",
        source_text=segment.text,
        translated_text=translated_text,
        original_duration_ms=int(float(segment.duration_seconds) * 1000),
        estimated_duration_ms=int(float(segment.duration_seconds) * 1000),
        duration_ratio=1.0,
        iterations_count=1,
        confidence_score=0.99,
        quality_score=0.99,
        is_cached=False,
        speed_adjustment_factor=1.0,
        iteration_history=[{"iteration": 1}],
        source_action="translate_project_celery",
    )


def _generated_audio(translation, suffix):
    return SimpleNamespace(
        id=uuid.uuid4(),
        translation_id=translation.id,
        project_id=translation.project_id,
        workspace_id=translation.workspace_id,
        request_id=None,
        task_id=None,
        idempotency_key=None,
        storage_path=f"gs://bucket/{suffix}.wav",
    )


def test_transcription_pipeline_updates_progress_state_and_idempotency_context(monkeypatch, tmp_path):
    media_id = uuid.uuid4()
    transcript_id = uuid.uuid4()
    operation = SimpleNamespace(
        id="operation-1",
        status="queued",
        current_stage="queued",
        progress_percent=0,
        message="queued",
        error_message=None,
        last_successful_stage=None,
    )
    media_file = SimpleNamespace(
        id=media_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        storage_path="raw/input.mp4",
        duration_seconds=120.0,
    )
    transcript = SimpleNamespace(
        id=transcript_id,
        media_file_id=media_id,
        workspace_id=media_file.workspace_id,
        project_id=media_file.project_id,
        status="queued",
        full_text="",
        word_count=0,
        speaker_count=0,
        confidence_score=0.0,
        detected_language=None,
        raw_response=None,
        processing_duration_seconds=None,
        error_message=None,
    )
    session = FakeSession(
        rows={
            FakeMediaFileModel: [media_file],
            FakeTranscriptModel: [transcript],
            FakeTranscriptSegmentModel: [],
        },
        operation=operation,
    )

    download_file = AsyncMock(return_value=None)
    extract_audio = AsyncMock(return_value=str(tmp_path / "extracted.wav"))
    preprocess_audio = AsyncMock(return_value=str(tmp_path / "clean.wav"))
    split_audio = AsyncMock(return_value=[(str(tmp_path / "chunk.wav"), 1.5, 12.0)])
    stt_response = {"results": [{"alternatives": [{"transcript": "Bonjour", "words": []}]}]}
    stt_call = AsyncMock(return_value=stt_response)
    parsed_segment = SimpleNamespace(
        speaker="Speaker 1",
        start_time=1.5,
        end_time=2.0,
        duration=0.5,
        text="Bonjour",
        confidence=0.96,
        words=[],
        sequence_order=0,
    )
    parse_google_response = MagicMock(return_value=([parsed_segment], "Bonjour", 0.96, 1, 1))
    progress_events = []
    time_values = iter([100.0, 101.0])

    namespace = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "asyncio": asyncio,
        "os": __import__("os"),
        "time": SimpleNamespace(time=lambda: next(time_values)),
        "uuid": uuid,
        "settings": SimpleNamespace(
            TEMP_UPLOAD_DIR=str(tmp_path / "temp"),
            PROCESSED_MEDIA_DIR=str(tmp_path / "processed"),
            STT_PRIMARY_PROVIDER="google",
            STT_FALLBACK_PROVIDER="deepgram",
        ),
        "SyncSession": lambda: session,
        "MediaFile": FakeMediaFileModel,
        "Transcript": FakeTranscriptModel,
        "TranscriptSegment": FakeTranscriptSegmentModel,
        "checkpoint_operation": checkpoint_operation,
        "audio_extractor": SimpleNamespace(extract_audio_for_stt=extract_audio),
        "audio_preprocessor": SimpleNamespace(
            preprocess_audio_pipeline=preprocess_audio,
            split_audio_into_chunks_if_needed=split_audio,
        ),
        "storage_service": SimpleNamespace(download_file=download_file),
        "google_stt_service": SimpleNamespace(transcribe_audio_file=stt_call),
        "deepgram_stt": SimpleNamespace(transcribe_audio_file=AsyncMock()),
        "transcript_parser": SimpleNamespace(parse_google_response=parse_google_response),
        "logger": SimpleNamespace(
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
        ),
        "publish_progress_event": lambda media_id_str, transcript_id_str, status, progress_percent, message: progress_events.append(
            {
                "media_id": media_id_str,
                "transcript_id": transcript_id_str,
                "status": status,
                "progress_percent": progress_percent,
                "message": message,
            }
        ),
    }

    run_transcription_pipeline = load_function(TRANCRIPTION_TASKS_PATH, "run_transcription_pipeline", namespace)

    result = run_transcription_pipeline(
        str(media_id),
        str(transcript_id),
        language="fr",
        max_speakers=2,
        enable_noise_reduction=False,
        enable_loudness_norm=True,
        request_id="request-1",
        task_id="task-1",
        idempotency_key="stable-key",
        source_action="manual",
        operation_id=str(operation.id),
    )

    assert result == {"status": "completed", "transcript_id": str(transcript_id), "segments": 1}
    assert transcript.status == "completed"
    assert transcript.detected_language == "fr"
    assert transcript.raw_response["correlation"] == {
        "request_id": "request-1",
        "task_id": "task-1",
        "idempotency_key": "stable-key",
        "source_action": "manual",
    }
    assert operation.status == "completed"
    assert operation.current_stage == "transcribe"
    assert operation.last_successful_stage == "transcribe"
    assert operation.progress_percent == 100
    assert len(session.added) == 1
    assert session.added[0].source_action == "manual"
    assert progress_events[0]["status"] == "in_progress"
    assert progress_events[-1]["status"] == "completed"
    assert stt_call.await_args.kwargs == {
        "audio_file_path": str(tmp_path / "chunk.wav"),
        "language": "fr",
        "max_speakers": 2,
        "duration_seconds": 12.0,
    }
    assert download_file.await_count == 1
    assert session.close_count == 1


def test_preprocess_and_transcribe_pipeline_task_retries_when_pipeline_fails(monkeypatch):
    pipeline_mock = MagicMock(side_effect=RuntimeError("pipeline failed"))
    self_obj = SimpleNamespace(
        request=SimpleNamespace(id="celery-task-1"),
        retry=MagicMock(side_effect=lambda exc: (_ for _ in ()).throw(RetryCalled(exc))),
    )

    namespace = {
        "Optional": Optional,
        "asyncio": asyncio,
        "uuid": uuid,
        "run_transcription_pipeline": pipeline_mock,
    }
    task = load_function(TRANCRIPTION_TASKS_PATH, "preprocess_and_transcribe_pipeline_task", namespace)

    with pytest.raises(RetryCalled) as error:
        task(
            self_obj,
            "media-id",
            "transcript-id",
            language="en",
            max_speakers=2,
            enable_noise_reduction=True,
            enable_loudness_norm=True,
            request_id="request-2",
            idempotency_key="idempotent",
            source_action="transcription_pipeline_celery",
            operation_id="operation-2",
        )

    assert str(error.value.original_exc) == "pipeline failed"
    pipeline_mock.assert_called_once_with(
        media_id_str="media-id",
        transcript_id_str="transcript-id",
        language="en",
        max_speakers=2,
        enable_noise_reduction=True,
        enable_loudness_norm=True,
        request_id="request-2",
        task_id="celery-task-1",
        idempotency_key="idempotent",
        source_action="transcription_pipeline_celery",
        operation_id="operation-2",
    )


def test_translate_project_batch_task_replaces_rows_and_propagates_idempotency(monkeypatch):
    transcript_id = uuid.uuid4()
    project_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    operation = SimpleNamespace(
        id="translation-op-1",
        status="queued",
        current_stage="queued",
        progress_percent=0,
        message="queued",
        error_message=None,
        last_successful_stage=None,
    )
    segment_a = SimpleNamespace(id=uuid.uuid4(), text="Hello", duration_seconds=1.2, speaker_tag="Speaker 1")
    segment_b = SimpleNamespace(id=uuid.uuid4(), text="World", duration_seconds=1.6, speaker_tag="Speaker 2")
    existing_translation = SimpleNamespace(id=uuid.uuid4())
    session = FakeSession(
        rows={
            FakeTranscriptSegmentModel: [segment_a, segment_b],
            FakeTranslationModel: [existing_translation],
        },
        operation=operation,
    )
    translated_entities: List[SimpleNamespace] = []

    async def _translate_side_effect(**kwargs):
        translated_entities[:] = []
        for seg in kwargs["segments"]:
            translated = _translation_response(seg, "Hola" if seg.text == "Hello" else "Mundo")
            translated.project_id = kwargs["project_id"]
            translated.workspace_id = kwargs["workspace_id"]
            translated.request_id = kwargs["request_id"]
            translated.task_id = kwargs["task_id"]
            translated.idempotency_key = f"{kwargs['idempotency_key_prefix']}:{seg.id}"
            translated.source_language = kwargs["source_language"]
            translated.target_language = kwargs["target_language"]
            translated.source_action = kwargs["source_action"]
            translated_entities.append(translated)
        return list(translated_entities)

    translate_mock = AsyncMock(side_effect=_translate_side_effect)
    progress_events = []
    time_values = iter([200.0, 201.5])

    namespace = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "asyncio": asyncio,
        "uuid": uuid,
        "time": SimpleNamespace(time=lambda: next(time_values)),
        "TranscriptSegment": FakeTranscriptSegmentModel,
        "Translation": FakeTranslationModel,
        "translation_service": SimpleNamespace(translate_segments_batch_async=translate_mock),
        "checkpoint_operation": checkpoint_operation,
        "SyncSession": lambda: session,
        "logger": SimpleNamespace(error=lambda *args, **kwargs: None),
        "publish_translation_event": lambda transcript_id_str, status, progress_percent, message: progress_events.append(
            {
                "transcript_id": transcript_id_str,
                "status": status,
                "progress_percent": progress_percent,
                "message": message,
            }
        ),
    }
    task = load_function(TRANSLATION_TASKS_PATH, "translate_project_batch_task", namespace)
    self_obj = SimpleNamespace(
        request=SimpleNamespace(id="celery-translate-1"),
        retry=MagicMock(side_effect=lambda exc: (_ for _ in ()).throw(RetryCalled(exc))),
    )

    result = task(
        self_obj,
        str(transcript_id),
        source_language="en",
        target_language="es",
        project_id_str=str(project_id),
        workspace_id_str=str(workspace_id),
        request_id="request-3",
        idempotency_key="translate-key",
        operation_id=str(operation.id),
    )

    assert result["status"] == "completed"
    assert result["segments_translated"] == 2
    assert session.deleted[0]["model"] is FakeTranslationModel
    assert session.deleted[0]["synchronize_session"] is False
    assert session.added == translated_entities
    assert operation.status == "completed"
    assert operation.current_stage == "translate"
    assert operation.last_successful_stage == "translate"
    assert operation.progress_percent == 100
    assert translated_entities[0].idempotency_key == f"translate-key:{segment_a.id}"
    assert translated_entities[1].idempotency_key == f"translate-key:{segment_b.id}"
    assert translate_mock.await_args.kwargs["idempotency_key_prefix"] == "translate-key"
    assert translate_mock.await_args.kwargs["task_id"] == "celery-translate-1"
    assert translate_mock.await_args.kwargs["project_id"] == project_id
    assert translate_mock.await_args.kwargs["workspace_id"] == workspace_id
    assert progress_events[0]["status"] == "in_progress"
    assert progress_events[-1]["status"] == "completed"
    assert session.close_count == 1


def test_translate_project_batch_task_retries_and_marks_failed_on_provider_error(monkeypatch):
    transcript_id = uuid.uuid4()
    operation = SimpleNamespace(
        id="translation-op-2",
        status="queued",
        current_stage="queued",
        progress_percent=0,
        message="queued",
        error_message=None,
        last_successful_stage=None,
    )
    segment = SimpleNamespace(id=uuid.uuid4(), text="Hello", duration_seconds=1.0, speaker_tag="Speaker 1")
    session = FakeSession(
        rows={
            FakeTranscriptSegmentModel: [segment],
            FakeTranslationModel: [],
        },
        operation=operation,
    )
    translate_mock = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    progress_events = []
    namespace = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "asyncio": asyncio,
        "uuid": uuid,
        "time": SimpleNamespace(time=lambda: 10.0),
        "TranscriptSegment": FakeTranscriptSegmentModel,
        "Translation": FakeTranslationModel,
        "translation_service": SimpleNamespace(translate_segments_batch_async=translate_mock),
        "checkpoint_operation": checkpoint_operation,
        "SyncSession": lambda: session,
        "logger": SimpleNamespace(error=lambda *args, **kwargs: None),
        "publish_translation_event": lambda transcript_id_str, status, progress_percent, message: progress_events.append(
            {
                "transcript_id": transcript_id_str,
                "status": status,
                "progress_percent": progress_percent,
                "message": message,
            }
        ),
    }
    task = load_function(TRANSLATION_TASKS_PATH, "translate_project_batch_task", namespace)
    self_obj = SimpleNamespace(
        request=SimpleNamespace(id="celery-translate-2"),
        retry=MagicMock(side_effect=lambda exc: (_ for _ in ()).throw(RetryCalled(exc))),
    )

    with pytest.raises(RetryCalled) as error:
        task(
            self_obj,
            str(transcript_id),
            source_language="en",
            target_language="es",
            operation_id=str(operation.id),
        )

    assert str(error.value.original_exc) == "provider unavailable"
    assert operation.status == "failed"
    assert operation.current_stage == "translate"
    assert operation.error_message == "provider unavailable"
    assert session.rollback_count == 1
    assert progress_events[-1]["status"] == "failed"
    assert translate_mock.await_args.kwargs["task_id"] == "celery-translate-2"


def test_run_project_tts_pipeline_persists_generated_audio_and_idempotency(monkeypatch, tmp_path):
    transcript_id = uuid.uuid4()
    project_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    segment_a = SimpleNamespace(id=uuid.uuid4(), start_time_seconds=0.0, end_time_seconds=1.0)
    segment_b = SimpleNamespace(id=uuid.uuid4(), start_time_seconds=1.0, end_time_seconds=2.0)
    translation_a = SimpleNamespace(
        id=uuid.uuid4(),
        segment=segment_a,
        target_language="es",
        project_id=project_id,
        workspace_id=workspace_id,
        original_duration_ms=1000,
        translated_text="Hola",
    )
    translation_b = SimpleNamespace(
        id=uuid.uuid4(),
        segment=segment_b,
        target_language="es",
        project_id=project_id,
        workspace_id=workspace_id,
        original_duration_ms=1000,
        translated_text="Mundo",
    )
    operation = SimpleNamespace(id="tts-op-1")
    transcript = SimpleNamespace(id=transcript_id, media_file_id=uuid.uuid4())
    media_file = SimpleNamespace(id=transcript.media_file_id, duration_seconds=2.0)
    session = FakeSession(
        rows={
            FakeTranscriptModel: [transcript],
            FakeMediaFileModel: [media_file],
            FakeTranscriptSegmentModel: [segment_a, segment_b],
            FakeTranslationModel: [translation_a, translation_b],
            FakeGeneratedAudioModel: [],
        },
        operation=operation,
    )
    generated_audio = [
        _generated_audio(translation_a, "seg-a"),
        _generated_audio(translation_b, "seg-b"),
    ]
    generated_audio[0].idempotency_key = f"tts-key:{translation_a.id}"
    generated_audio[1].idempotency_key = f"tts-key:{translation_b.id}"
    synthesize_batch = AsyncMock(return_value=generated_audio)
    downloaded_paths = []
    upload_calls = []
    progress_events = []
    time_values = iter([300.0, 303.25])

    def _download(src, dest):
        downloaded_paths.append(dest)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"segment")

    def _assemble(segments_data, total_duration_sec, output_master_path):
        Path(output_master_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_master_path).write_bytes(b"master")

    def _upload(file_path, key, mime_type):
        upload_calls.append({"file_path": file_path, "key": key, "mime_type": mime_type})
        return f"gs://bucket/{key}"

    namespace = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "asyncio": asyncio,
        "os": __import__("os"),
        "time": SimpleNamespace(time=lambda: next(time_values)),
        "uuid": uuid,
        "settings": SimpleNamespace(PROCESSED_MEDIA_DIR=str(tmp_path), GCS_BUCKET_NAME="bucket-1"),
        "SyncSession": lambda: session,
        "Transcript": FakeTranscriptModel,
        "MediaFile": FakeMediaFileModel,
        "TranscriptSegment": FakeTranscriptSegmentModel,
        "Translation": FakeTranslationModel,
        "GeneratedAudio": FakeGeneratedAudioModel,
        "joinedload": lambda value: ("joinedload", value),
        "tts_orchestrator": SimpleNamespace(synthesize_batch_concurrent=synthesize_batch),
        "audio_postprocessor": SimpleNamespace(assemble_master_dubbed_timeline=AsyncMock(side_effect=_assemble)),
        "storage_service": SimpleNamespace(download_file=AsyncMock(side_effect=_download), upload_file=AsyncMock(side_effect=_upload)),
        "logger": SimpleNamespace(error=lambda *args, **kwargs: None),
        "publish_tts_event": lambda project_id_str, status, progress_percent, message: progress_events.append(
            {
                "project_id": project_id_str,
                "status": status,
                "progress_percent": progress_percent,
                "message": message,
            }
        ),
    }
    run_project_tts_pipeline = load_function(TTS_TASKS_PATH, "run_project_tts_pipeline", namespace)

    task_instance = SimpleNamespace(retry=MagicMock())
    result = run_project_tts_pipeline(
        str(transcript_id),
        target_language="es",
        project_id_str=str(project_id),
        request_id="request-4",
        task_id="task-4",
        idempotency_key="tts-key",
        task_instance=task_instance,
    )

    assert result["status"] == "completed"
    assert result["segments_synthesized"] == 2
    assert result["master_audio_path"] == f"master_dubbed/{project_id}/es_dubbed.wav"
    assert session.added == generated_audio
    assert session.commit_count == 2
    assert synthesize_batch.await_args.kwargs["idempotency_key_prefix"] == "tts-key"
    assert synthesize_batch.await_args.kwargs["request_id"] == "request-4"
    assert synthesize_batch.await_args.kwargs["task_id"] == "task-4"
    assert generated_audio[0].idempotency_key.endswith(str(translation_a.id))
    assert generated_audio[1].idempotency_key.endswith(str(translation_b.id))
    assert upload_calls[0]["key"] == f"master_dubbed/{project_id}/es_dubbed.wav"
    assert len(downloaded_paths) == 2
    assert progress_events[0]["status"] == "in_progress"
    assert progress_events[-1]["status"] == "completed"


def test_run_project_tts_pipeline_retries_on_synthesis_failure(monkeypatch):
    operation = SimpleNamespace(id="tts-op-2")
    transcript = SimpleNamespace(id=uuid.uuid4(), media_file_id=uuid.uuid4())
    media_file = SimpleNamespace(id=transcript.media_file_id, duration_seconds=2.0)
    segment = SimpleNamespace(id=uuid.uuid4(), start_time_seconds=0.0, end_time_seconds=1.0)
    translation = SimpleNamespace(
        id=uuid.uuid4(),
        segment=segment,
        target_language="es",
        project_id=None,
        workspace_id=None,
        original_duration_ms=1000,
        translated_text="Hola",
    )
    session = FakeSession(
        rows={
            FakeTranscriptModel: [transcript],
            FakeMediaFileModel: [media_file],
            FakeTranscriptSegmentModel: [segment],
            FakeTranslationModel: [translation],
            FakeGeneratedAudioModel: [],
        },
        operation=operation,
    )
    synthesize_batch = AsyncMock(side_effect=RuntimeError("tts provider unavailable"))
    progress_events = []
    namespace = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "asyncio": asyncio,
        "os": __import__("os"),
        "time": SimpleNamespace(time=lambda: 500.0),
        "uuid": uuid,
        "settings": SimpleNamespace(PROCESSED_MEDIA_DIR="C:\\tmp", GCS_BUCKET_NAME="bucket-1"),
        "SyncSession": lambda: session,
        "Transcript": FakeTranscriptModel,
        "MediaFile": FakeMediaFileModel,
        "TranscriptSegment": FakeTranscriptSegmentModel,
        "Translation": FakeTranslationModel,
        "GeneratedAudio": FakeGeneratedAudioModel,
        "joinedload": lambda value: ("joinedload", value),
        "tts_orchestrator": SimpleNamespace(synthesize_batch_concurrent=synthesize_batch),
        "audio_postprocessor": SimpleNamespace(assemble_master_dubbed_timeline=AsyncMock()),
        "storage_service": SimpleNamespace(download_file=AsyncMock(), upload_file=AsyncMock()),
        "logger": SimpleNamespace(error=lambda *args, **kwargs: None),
        "publish_tts_event": lambda project_id_str, status, progress_percent, message: progress_events.append(
            {
                "project_id": project_id_str,
                "status": status,
                "progress_percent": progress_percent,
                "message": message,
            }
        ),
    }
    run_project_tts_pipeline = load_function(TTS_TASKS_PATH, "run_project_tts_pipeline", namespace)
    task_instance = SimpleNamespace(
        retry=MagicMock(side_effect=lambda exc: (_ for _ in ()).throw(RetryCalled(exc))),
    )

    with pytest.raises(RetryCalled) as error:
        run_project_tts_pipeline(
            str(transcript.id),
            target_language="es",
            task_instance=task_instance,
        )

    assert str(error.value.original_exc) == "tts provider unavailable"
    assert session.rollback_count == 1
    assert session.added == []
    assert progress_events[-1]["status"] == "failed"

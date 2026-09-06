import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import export, lipsync, transcription, translation
from app.schemas.export_schema import ExportRequest
from app.schemas.lipsync_schema import RenderLipSyncProjectRequest
from app.schemas.transcription_schema import StartTranscriptionRequest
from app.schemas.translation_schema import (
    TranslateProjectRequest,
    TranslateSegmentRequest,
    UpdateTranslationRequest,
)


NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)
WORKSPACE_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()
MEDIA_ID = uuid.uuid4()
TRANSCRIPT_ID = uuid.uuid4()


class _ScalarCollection:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, scalar=None, values=None):
        self.scalar = scalar
        self.values = values or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalars(self):
        return _ScalarCollection(self.values)


class _Session:
    def __init__(self, *results, gets=None):
        self.results = iter(results)
        self.gets = gets or {}
        self.added = []
        self.deleted = []
        self.commit_count = 0

    async def execute(self, _statement):
        return next(self.results)

    async def scalar(self, _statement):
        result = next(self.results)
        return result.scalar if isinstance(result, _Result) else result

    async def get(self, model, identifier):
        return self.gets.get((model.__name__, identifier)) or self.gets.get(model.__name__)

    def add(self, entity):
        self.added.append(entity)

    async def delete(self, entity):
        self.deleted.append(entity)

    async def flush(self):
        self._hydrate()

    async def commit(self):
        self.commit_count += 1
        self._hydrate()

    async def refresh(self, entity):
        self._hydrate()
        if hasattr(entity, "generated_audio") and "generated_audio" not in entity.__dict__:
            entity.generated_audio = []

    def _hydrate(self):
        for entity in self.added:
            if getattr(entity, "id", None) is None:
                entity.id = uuid.uuid4()
            if hasattr(entity, "created_at") and entity.created_at is None:
                entity.created_at = NOW
            if hasattr(entity, "updated_at") and entity.updated_at is None:
                entity.updated_at = NOW
            if entity.__class__.__name__ == "Translation" and entity.is_user_edited is None:
                entity.is_user_edited = False


def _context():
    return SimpleNamespace(workspace_id=WORKSPACE_ID, user_id=uuid.uuid4(), membership_role="editor")


def _request(request_id="request-1"):
    return SimpleNamespace(headers={"X-Request-ID": request_id} if request_id else {})


def _media():
    return SimpleNamespace(id=MEDIA_ID, workspace_id=WORKSPACE_ID, project_id=PROJECT_ID)


def _transcript(**overrides):
    values = {
        "id": TRANSCRIPT_ID,
        "media_file_id": MEDIA_ID,
        "workspace_id": WORKSPACE_ID,
        "project_id": PROJECT_ID,
        "detected_language": "en",
        "status": "completed",
        "error_message": None,
        "confidence_score": 0.9,
        "word_count": 2,
        "speaker_count": 1,
        "full_text": "hello world",
        "segments": [],
        "created_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _segment(sequence=0, text="hello"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        transcript_id=TRANSCRIPT_ID,
        transcript=_transcript(),
        sequence_order=sequence,
        speaker_tag=f"Speaker {sequence + 1}",
        start_time_seconds=float(sequence),
        end_time_seconds=float(sequence + 1),
        duration_seconds=1.0,
        text=text,
        confidence=0.9,
        words=[],
    )


def _translation_item(segment, **overrides):
    values = {
        "id": uuid.uuid4(),
        "transcript_segment_id": segment.id,
        "workspace_id": WORKSPACE_ID,
        "project_id": PROJECT_ID,
        "source_language": "en",
        "target_language": "es",
        "source_text": segment.text,
        "translated_text": "hola",
        "original_duration_ms": 1000,
        "estimated_duration_ms": 950,
        "duration_ratio": 0.95,
        "iterations_count": 1,
        "confidence_score": 0.98,
        "is_cached": False,
        "is_user_edited": False,
        "generated_audio": [],
        "segment": segment,
        "created_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "factory, kwargs",
    [
        (StartTranscriptionRequest, {"media_id": MEDIA_ID, "max_speakers": 0}),
        (
            TranslateSegmentRequest,
            {
                "segment_id": uuid.uuid4(),
                "source_text": "hello",
                "original_duration_ms": 0,
                "target_language": "es",
            },
        ),
        (
            TranslateProjectRequest,
            {"transcript_id": TRANSCRIPT_ID, "target_language": "unsupported"},
        ),
    ],
)
def test_active_router_request_models_reject_invalid_input(factory, kwargs):
    with pytest.raises(ValidationError):
        factory(**kwargs)


@pytest.mark.asyncio
async def test_translate_project_dispatches_cloud_task_and_tracks_operation(monkeypatch):
    transcript = _transcript()
    project = SimpleNamespace(id=PROJECT_ID, current_pipeline_operation_id=None)
    session = _Session(_Result(scalar=transcript), gets={"Project": project})
    cloud_tasks = SimpleNamespace(enabled=True, enqueue_http_task=MagicMock(return_value="task"))
    monkeypatch.setattr(translation, "cloud_tasks_service", cloud_tasks)
    monkeypatch.setattr(translation, "ensure_workspace_resource_access", AsyncMock())

    response = await translation.translate_project(
        TranslateProjectRequest(transcript_id=TRANSCRIPT_ID, source_language="en", target_language="es"),
        _request(),
        _context(),
        session,
    )

    operation = session.added[0]
    assert response.status == "queued"
    assert response.job_id == str(operation.id)
    assert operation.idempotency_key == f"translate-project:{TRANSCRIPT_ID}:es"
    assert project.current_pipeline_operation_id == operation.id
    payload = cloud_tasks.enqueue_http_task.call_args.kwargs["payload"]
    assert payload["operation_id"] == response.job_id
    assert payload["request_id"] == "request-1"


@pytest.mark.asyncio
async def test_translate_project_sync_fallback_replaces_prior_translations(monkeypatch):
    segments = [_segment(0), _segment(1, "world")]
    old = _translation_item(segments[0])
    new_entities = [SimpleNamespace(), SimpleNamespace()]
    session = _Session(
        _Result(scalar=_transcript()),
        _Result(values=segments),
        _Result(values=[old]),
        gets={"Project": SimpleNamespace(current_pipeline_operation_id=None)},
    )
    monkeypatch.setattr(translation, "ensure_workspace_resource_access", AsyncMock())
    monkeypatch.setattr(translation.settings, "TRANSLATION_SYNC_FALLBACK", True)
    monkeypatch.setattr(translation.settings, "ENABLE_BACKGROUND_PIPELINES", False)
    monkeypatch.setattr(
        translation.translation_service,
        "translate_segments_batch_async",
        AsyncMock(return_value=new_entities),
    )
    monkeypatch.setattr(translation, "cloud_tasks_service", SimpleNamespace(enabled=False))

    response = await translation.translate_project(
        TranslateProjectRequest(transcript_id=TRANSCRIPT_ID, target_language="es"),
        _request(),
        _context(),
        session,
    )

    assert response.status == "completed"
    assert "2 segments" in response.message
    assert session.deleted == [old]
    operation = session.added[0]
    assert operation.progress_percent == 100
    assert operation.last_successful_stage == "translate"
    assert session.added[-2:] == new_entities


@pytest.mark.asyncio
async def test_translate_project_sync_fallback_rejects_empty_transcript(monkeypatch):
    session = _Session(
        _Result(scalar=_transcript()),
        _Result(values=[]),
        gets={"Project": SimpleNamespace(current_pipeline_operation_id=None)},
    )
    monkeypatch.setattr(translation, "ensure_workspace_resource_access", AsyncMock())
    monkeypatch.setattr(translation.settings, "TRANSLATION_SYNC_FALLBACK", True)
    monkeypatch.setattr(translation.settings, "ENABLE_BACKGROUND_PIPELINES", False)
    monkeypatch.setattr(translation, "cloud_tasks_service", SimpleNamespace(enabled=False))

    with pytest.raises(HTTPException) as error:
        await translation.translate_project(
            TranslateProjectRequest(transcript_id=TRANSCRIPT_ID, target_language="es"),
            _request(),
            _context(),
            session,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_translate_single_segment_creates_then_updates_translation(monkeypatch):
    segment = _segment()
    result = SimpleNamespace(
        translated_text="hola",
        original_duration_ms=1000,
        estimated_duration_ms=980,
        duration_ratio=0.98,
        iterations_count=2,
        confidence_score=0.97,
        is_cached=False,
        iteration_history=[{"iteration": 1}],
    )
    monkeypatch.setattr(translation, "ensure_workspace_resource_access", AsyncMock())
    monkeypatch.setattr(translation.duration_matcher, "translate_with_duration_matching", AsyncMock(return_value=result))
    create_session = _Session(_Result(scalar=segment), _Result(scalar=None))

    created = await translation.translate_single_segment(
        TranslateSegmentRequest(
            segment_id=segment.id,
            source_text="hello",
            original_duration_ms=1000,
            target_language="es",
        ),
        _request(),
        _context(),
        create_session,
    )

    assert created.translated_text == "hola"
    assert created.duration_ratio == 0.98
    entity = create_session.added[0]
    audio = SimpleNamespace(status="completed")
    existing = _translation_item(segment, generated_audio=[audio])
    update_session = _Session(_Result(scalar=segment), _Result(scalar=existing))
    result.translated_text = "buenas"
    updated = await translation.translate_single_segment(
        TranslateSegmentRequest(
            segment_id=segment.id,
            source_text="hello again",
            original_duration_ms=1000,
            target_language="es",
        ),
        _request("request-2"),
        _context(),
        update_session,
    )

    assert updated.translated_text == "buenas"
    assert update_session.deleted == [audio]
    assert existing.request_id == "request-2"
    assert existing.source_text == "hello again"


@pytest.mark.asyncio
async def test_translation_reads_updates_and_exports_all_formats(monkeypatch):
    first = _segment(0)
    second = _segment(1, "world")
    first_translation = _translation_item(first)
    second_translation = _translation_item(second, translated_text="mundo", duration_ratio=1.05)
    monkeypatch.setattr(translation, "ensure_workspace_resource_access", AsyncMock())
    session = _Session(
        _Result(scalar=_transcript()),
        _Result(values=[first, second]),
        _Result(values=[second_translation, first_translation]),
    )

    result = await translation.get_project_translations(
        TRANSCRIPT_ID, "es", _context(), session
    )

    assert [item.sequence_order for item in result.translations] == [0, 1]
    assert result.average_duration_ratio == 1.0
    assert result.overall_confidence == 0.98

    for export_format, expected in (
        ("srt", "-->"),
        ("vtt", "WEBVTT"),
        ("txt", 'Speaker 1: "hola"'),
    ):
        with patch.object(translation, "get_project_translations", new=AsyncMock(return_value=result)):
            response = await translation.export_translated_subtitles(
                TRANSCRIPT_ID, export_format, "es", _context(), session
            )
        assert expected in response.body.decode()

    editable = _translation_item(first, original_duration_ms=1000)
    session = _Session(_Result(scalar=editable))
    updated = await translation.update_translation(
        editable.id,
        UpdateTranslationRequest(translated_text="  texto editado  "),
        _context(),
        session,
    )
    assert updated.translated_text == "texto editado"
    assert editable.is_user_edited is True
    assert 0.8 <= editable.speed_adjustment_factor <= 1.25


@pytest.mark.asyncio
async def test_start_transcription_creates_transcript_and_dispatches_cloud_task(monkeypatch):
    project = SimpleNamespace(current_pipeline_operation_id=None)
    session = _Session(
        _Result(scalar=_media()),
        _Result(scalar=None),
        gets={"Project": project},
    )
    cloud_tasks = SimpleNamespace(enabled=True, enqueue_http_task=MagicMock(return_value="task"))
    monkeypatch.setattr(transcription, "ensure_workspace_resource_access", AsyncMock())
    monkeypatch.setattr(transcription, "cloud_tasks_service", cloud_tasks)

    response = await transcription.start_transcription(
        StartTranscriptionRequest(
            media_id=MEDIA_ID,
            language="fr",
            max_speakers=2,
            enable_noise_reduction=False,
            enable_loudness_norm=True,
            enable_vad=False,
        ),
        _request(),
        _context(),
        session,
    )

    transcript_entity, operation = session.added
    assert response.transcript_id == transcript_entity.id
    assert response.job_id == str(operation.id)
    assert project.current_pipeline_operation_id == operation.id
    payload = cloud_tasks.enqueue_http_task.call_args.kwargs["payload"]
    assert payload["enable_noise_reduction"] is False
    assert payload["enable_vad"] is False


@pytest.mark.asyncio
async def test_start_transcription_reuses_transcript_and_dispatches_worker(monkeypatch):
    existing = _transcript(status="failed", error_message="old")
    session = _Session(
        _Result(scalar=_media()),
        _Result(scalar=existing),
        gets={"Project": SimpleNamespace(current_pipeline_operation_id=None)},
    )
    task = SimpleNamespace(id="worker-job")
    monkeypatch.setattr(transcription, "ensure_workspace_resource_access", AsyncMock())
    monkeypatch.setattr(transcription, "cloud_tasks_service", SimpleNamespace(enabled=False))
    monkeypatch.setattr(transcription, "require_background_pipelines", MagicMock())
    monkeypatch.setattr(
        transcription.preprocess_and_transcribe_pipeline_task,
        "apply_async",
        MagicMock(return_value=task),
    )

    response = await transcription.start_transcription(
        StartTranscriptionRequest(media_id=MEDIA_ID), _request(""), _context(), session
    )

    assert response.job_id == "worker-job"
    assert existing.status == "queued"
    assert existing.error_message is None
    call = transcription.preprocess_and_transcribe_pipeline_task.apply_async.call_args
    assert call.kwargs["queue"] == "stt_diarize"


@pytest.mark.asyncio
async def test_transcript_read_lookup_and_export_formats(monkeypatch):
    seg = _segment()
    seg.words = [{"text": "hello", "start": 0, "end": 1, "confidence": 0.9, "speaker": "Speaker 1"}]
    transcript_entity = _transcript(segments=[seg])
    monkeypatch.setattr(transcription, "ensure_workspace_resource_access", AsyncMock())

    response = await transcription.get_transcript(
        TRANSCRIPT_ID, _context(), _Session(_Result(scalar=transcript_entity))
    )
    assert response.segments[0].text == "hello"
    assert response.segments[0].words[0].confidence == 0.9

    by_media_session = _Session(
        _Result(scalar=transcript_entity),
        _Result(scalar=transcript_entity),
    )
    by_media = await transcription.get_transcript_by_media(
        MEDIA_ID, _context(), by_media_session
    )
    assert by_media.transcript_id == TRANSCRIPT_ID

    for export_format, expected in (
        ("srt", "-->"),
        ("vtt", "WEBVTT"),
        ("txt", "Speaker 1"),
        ("json", None),
    ):
        with patch.object(transcription, "get_transcript", new=AsyncMock(return_value=response)):
            exported = await transcription.export_transcript(
                TRANSCRIPT_ID, export_format, _context(), by_media_session
            )
        if expected:
            assert expected in exported.body.decode()
        else:
            assert exported is response


def _lipsync_job(**overrides):
    values = {
        "id": uuid.uuid4(),
        "project_id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "media_file_id": MEDIA_ID,
        "transcript_id": TRANSCRIPT_ID,
        "target_language": "es",
        "model_name": "liveportrait",
        "render_mode": "dub_only",
        "status": "completed",
        "progress_percent": 100,
        "current_stage": "complete",
        "last_successful_stage": "mux",
        "total_segments": 1,
        "completed_segments": 1,
        "output_video_gcs_path": "outputs/final.mp4",
        "output_filesize_bytes": 123,
        "quality_score": 0.96,
        "av_sync_error_ms": 12,
        "segments_metadata": [],
        "execution_time_seconds": 3.5,
        "created_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_lipsync_render_rejects_unavailable_provider_before_persistence(monkeypatch):
    monkeypatch.setattr(lipsync, "replicate_lipsync", SimpleNamespace(is_configured=False))
    with pytest.raises(HTTPException) as error:
        await lipsync.render_lipsync_project(
            RenderLipSyncProjectRequest(
                media_file_id=MEDIA_ID,
                transcript_id=TRANSCRIPT_ID,
                target_language="es",
            ),
            _request(),
            _context(),
            _Session(),
        )
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_lipsync_dub_only_dispatch_and_read_models(monkeypatch):
    project = SimpleNamespace(id=PROJECT_ID, current_lipsync_job_id=None, status="draft")
    session = _Session(_Result(scalar=_media()), _Result(scalar=_transcript()))
    monkeypatch.setattr(lipsync, "ensure_workspace_resource_access", AsyncMock())
    monkeypatch.setattr(lipsync, "get_scoped_project", AsyncMock(return_value=project))
    monkeypatch.setattr(lipsync, "cloud_tasks_service", SimpleNamespace(enabled=False))
    monkeypatch.setattr(lipsync, "require_background_pipelines", MagicMock())
    monkeypatch.setattr(
        lipsync.render_lipsync_project_task,
        "apply_async",
        MagicMock(return_value=SimpleNamespace(id="lipsync-task")),
    )

    response = await lipsync.render_lipsync_project(
        RenderLipSyncProjectRequest(
            media_file_id=MEDIA_ID,
            transcript_id=TRANSCRIPT_ID,
            project_id=PROJECT_ID,
            target_language="es",
            enable_lipsync=False,
        ),
        _request(),
        _context(),
        session,
    )

    job = session.added[0]
    assert response.job_id == job.id
    assert job.render_mode == "dub_only"
    assert job.task_id == "lipsync-task"
    assert project.status == "processing"

    metadata = SimpleNamespace(
        id=uuid.uuid4(),
        transcript_segment_id=uuid.uuid4(),
        sequence_order=0,
        start_time_seconds=0,
        end_time_seconds=1,
        face_detected=True,
        face_confidence=0.9,
        head_rotation_deg=2,
        render_status="completed",
        av_sync_offset_ms=5,
        quality_score=0.95,
    )
    read_job = _lipsync_job(segments_metadata=[metadata])
    monkeypatch.setattr(lipsync.storage_service, "generate_presigned_download_url", MagicMock(side_effect=["view", "download"]))
    read = await lipsync.get_lipsync_job(
        read_job.id, _context(), _Session(_Result(scalar=read_job))
    )
    assert read.output_video_url == "view"
    assert read.download_video_url == "download"
    assert read.segments_metadata[0].face_detected is True

    monkeypatch.setattr(lipsync, "get_scoped_project", AsyncMock(return_value=project))
    monkeypatch.setattr(
        lipsync.storage_service,
        "generate_presigned_download_url",
        MagicMock(side_effect=["history-view", "history-download"]),
    )
    history = await lipsync.get_lipsync_history(
        PROJECT_ID, _context(), _Session(_Result(values=[read_job]))
    )
    assert history[0].job_id == read_job.id


def _export_job(**overrides):
    values = {
        "id": uuid.uuid4(),
        "project_id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "media_file_id": MEDIA_ID,
        "target_language": "es",
        "format": "mp4",
        "resolution": "1080p",
        "frame_rate": 30,
        "codec": "h264",
        "status": "completed",
        "progress_percent": 100,
        "current_stage": "complete",
        "output_video_gcs_path": "outputs/export.mp4",
        "filesize_bytes": 456,
        "estimated_cost_usd": 0.25,
        "created_at": NOW,
        "error_message": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _export_request():
    return ExportRequest(
        media_file_id=MEDIA_ID,
        transcript_id=TRANSCRIPT_ID,
        project_id=PROJECT_ID,
        target_language="es",
        subtitles={"enabled": True, "format": "burnt-in", "appearance": {"font": "Arial"}},
        post_processing={
            "color_grading": True,
            "watermark": "logo.png",
            "audio_normalization": True,
        },
    )


@pytest.mark.asyncio
async def test_export_enqueue_status_history_and_cancel(monkeypatch):
    segment = _segment()
    project = SimpleNamespace(id=PROJECT_ID)
    session = _Session(
        _Result(scalar=_media()),
        _Result(scalar=_transcript()),
        _Result(values=[segment]),
    )
    monkeypatch.setattr(export, "require_background_pipelines", MagicMock())
    monkeypatch.setattr(export, "ensure_workspace_resource_access", AsyncMock())
    monkeypatch.setattr(export, "get_scoped_project", AsyncMock(return_value=project))
    monkeypatch.setattr(
        export.render_video_export_task,
        "apply_async",
        MagicMock(return_value=SimpleNamespace(id="export-task")),
    )

    dispatched = await export.enqueue_video_export(
        _export_request(), _request(), _context(), session
    )

    job = session.added[0]
    assert dispatched.job_id == job.id
    assert job.task_id == "export-task"
    task_kwargs = export.render_video_export_task.apply_async.call_args.kwargs["kwargs"]
    assert task_kwargs["segments_data"][0]["speaker_tag"] == "Speaker 1"
    assert export.render_video_export_task.apply_async.call_args.kwargs["queue"] == "mux_export"

    completed = _export_job()
    monkeypatch.setattr(export.storage_service, "generate_presigned_download_url", MagicMock(side_effect=["view", "download"]))
    status_response = await export.get_export_job_status(
        completed.id, _context(), _Session(_Result(scalar=completed))
    )
    assert status_response.output_video_url == "view"
    assert status_response.download_video_url == "download"

    monkeypatch.setattr(export.storage_service, "generate_presigned_download_url", MagicMock(side_effect=["history-view", "history-download"]))
    history = await export.get_export_history(
        PROJECT_ID, _context(), _Session(_Result(values=[completed]))
    )
    assert history[0].download_video_url == "history-download"

    cancel_session = _Session(_Result(scalar=completed))
    monkeypatch.setattr(export.export_queue_manager, "cancel_job", MagicMock(return_value=True))
    cancelled = await export.cancel_export_job(completed.id, _context(), cancel_session)
    assert cancelled["status"] == "cancelled"
    assert completed.status == "failed"
    assert completed.error_message == "Export cancelled by user."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "session", "detail"),
    [
        (
            lambda session: translation.get_project_translations(TRANSCRIPT_ID, "es", _context(), session),
            _Session(_Result(scalar=None)),
            "Transcript not found.",
        ),
        (
            lambda session: transcription.start_transcription(
                StartTranscriptionRequest(media_id=MEDIA_ID), _request(), _context(), session
            ),
            _Session(_Result(scalar=None)),
            "Media file not found.",
        ),
        (
            lambda session: lipsync.get_lipsync_job(uuid.uuid4(), _context(), session),
            _Session(_Result(scalar=None)),
            "Lip-sync job not found.",
        ),
        (
            lambda session: export.get_export_job_status(uuid.uuid4(), _context(), session),
            _Session(_Result(scalar=None)),
            "Export job not found.",
        ),
    ],
)
async def test_active_router_not_found_boundaries(call, session, detail):
    with pytest.raises(HTTPException) as error:
        await call(session)
    assert error.value.status_code == 404
    assert error.value.detail == detail

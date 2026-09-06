import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import export_tasks as export_tasks_module
from app.tasks import lipsync_tasks as lipsync_tasks_module
from app.models.export_job import ExportJob
from app.models.lipsync_job import LipSyncJob
from app.models.media import MediaFile
from app.models.project import Project
from app.models.transcript import Transcript, TranscriptSegment
from app.tasks.export_tasks import render_video_export_task
from app.tasks.lipsync_tasks import persist_lipsync_checkpoint, run_lipsync_project_pipeline


class _RetrySignal(RuntimeError):
    pass


class _FakeQuery:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def filter(self, *args, **kwargs):
        return self

    def options(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.db.first_values.get(self.model)

    def all(self):
        return list(self.db.all_values.get(self.model, []))


class _FakeSession:
    def __init__(self, *, first_values=None, all_values=None):
        self.first_values = first_values or {}
        self.all_values = all_values or {}
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def query(self, model):
        return _FakeQuery(self, model)

    def add(self, entity):
        self.added.append(entity)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


class _DummyColumn:
    def __eq__(self, other):
        return object()

    def in_(self, values):
        return object()


class _DummyTranslation:
    generated_audio = object()
    transcript_segment_id = _DummyColumn()
    target_language = _DummyColumn()


def _write_output(path, payload=b"rendered"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(payload)


def _export_job(job_id, media_file_id, project_id, **overrides):
    values = {
        "id": job_id,
        "project_id": project_id,
        "workspace_id": uuid.uuid4(),
        "media_file_id": media_file_id,
        "transcript_id": uuid.uuid4(),
        "target_language": "es",
        "format": "mp4",
        "status": "queued",
        "progress_percent": 0,
        "current_stage": "queued",
        "output_video_gcs_path": None,
        "filesize_bytes": None,
        "error_message": None,
        "request_id": "stored-request",
        "task_id": "stored-task",
        "idempotency_key": "stored-idempotency",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _media_file(media_file_id, project_id, workspace_id):
    return SimpleNamespace(
        id=media_file_id,
        project_id=project_id,
        workspace_id=workspace_id,
        storage_path="gs://bucket/source.mp4",
        storage_bucket="bucket",
    )


def _lipsync_entities(job_id, media_file_id, transcript_id, project_id, workspace_id, segments):
    job = SimpleNamespace(
        id=job_id,
        project_id=project_id,
        workspace_id=workspace_id,
        media_file_id=media_file_id,
        transcript_id=transcript_id,
        target_language="fr",
        model_name="liveportrait",
        render_mode="dub_and_lipsync",
        status="queued",
        progress_percent=0,
        current_stage="queued",
        last_successful_stage=None,
        total_segments=0,
        completed_segments=0,
        output_video_gcs_path=None,
        output_filesize_bytes=None,
        quality_score=None,
        av_sync_error_ms=None,
        error_message=None,
        request_id="stored-request",
        task_id="stored-task",
        idempotency_key="stored-idempotency",
    )
    media = SimpleNamespace(
        id=media_file_id,
        project_id=project_id,
        workspace_id=workspace_id,
        storage_path="gs://bucket/source.mp4",
        storage_bucket="bucket",
    )
    transcript = SimpleNamespace(
        id=transcript_id,
        project_id=project_id,
        workspace_id=workspace_id,
        media_file_id=media_file_id,
    )
    project = SimpleNamespace(
        id=project_id,
        current_lipsync_job_id=None,
        status="queued",
        last_rendered_video_gcs_path=None,
    )
    translations = []
    for segment in segments:
        translations.append(
            SimpleNamespace(
                id=uuid.uuid4(),
                transcript_segment_id=segment.id,
                target_language="fr",
                translated_text=f"translated-{segment.sequence_order}",
                duration_ratio=1.0,
                generated_audio=[
                    SimpleNamespace(storage_path=f"gs://bucket/{segment.id.hex}.wav", storage_bucket="bucket")
                ],
            )
        )
    return job, media, transcript, project, translations


def test_persist_lipsync_checkpoint_clamps_progress_and_records_successful_stage():
    job = SimpleNamespace(current_stage="queued", progress_percent=0, last_successful_stage=None)
    db = SimpleNamespace(commit=MagicMock())

    persist_lipsync_checkpoint(
        db,
        job,
        stage="export",
        progress_percent=140,
        successful_stage="lip_sync",
    )

    assert job.current_stage == "export"
    assert job.progress_percent == 100
    assert job.last_successful_stage == "lip_sync"
    db.commit.assert_called_once()


def test_render_video_export_task_completes_and_preserves_existing_identifiers(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tasks.export_tasks.settings.PROCESSED_MEDIA_DIR", str(tmp_path))

    job_id = uuid.uuid4()
    media_file_id = uuid.uuid4()
    project_id = uuid.uuid4()
    job = _export_job(job_id, media_file_id, project_id)
    media = _media_file(media_file_id, project_id, job.workspace_id)
    db = _FakeSession(first_values={ExportJob: job, MediaFile: media})

    def download_file(source_key, destination_path, **kwargs):
        _write_output(destination_path, b"source")

    def process_render(**kwargs):
        _write_output(kwargs["output_local_path"], b"final-video")
        return kwargs["output_local_path"]

    def upload_file(**kwargs):
        assert Path(kwargs["file_path"]).exists()
        return f"gs://bucket/{Path(kwargs['file_path']).name}"

    monkeypatch.setattr(render_video_export_task.request, "id", "celery-task-1", raising=False)

    with (
        patch("app.tasks.export_tasks.SyncSession", return_value=db),
        patch.object(export_tasks_module.export_queue_manager, "register_job"),
        patch.object(export_tasks_module.export_queue_manager, "deregister_job"),
        patch.object(export_tasks_module.export_queue_manager, "is_cancelled", return_value=False),
        patch.object(export_tasks_module.export_queue_manager, "cleanup_temporary_files") as cleanup,
        patch("app.tasks.export_tasks.publish_export_progress"),
        patch("app.tasks.export_tasks.storage_service.download_file", new=AsyncMock(side_effect=download_file)),
        patch("app.tasks.export_tasks.storage_service.upload_file", new=AsyncMock(side_effect=upload_file)) as upload,
        patch("app.tasks.export_tasks.export_orchestrator.process_export_render", new=AsyncMock(side_effect=process_render)) as render,
    ):
        result = render_video_export_task(
            str(job_id),
            str(media_file_id),
            "es",
            {
                "format": "mp4",
                "subtitles": {"enabled": True, "format": "burnt-in"},
                "post_processing": {"color_grading": False, "watermark": None, "audio_normalization": True},
            },
            segments_data=[{"start_sec": 0, "end_sec": 1, "duration_sec": 1, "text": "hello"}],
            request_id="new-request",
            idempotency_key="new-idempotency",
        )

    assert result["status"] == "completed"
    assert result["job_id"] == str(job_id)
    assert result["output_key"] == f"exports/{project_id}/es_render_{job_id.hex}.mp4"
    assert result["filesize_bytes"] == len(b"final-video")
    assert job.status == "completed"
    assert job.progress_percent == 100
    assert job.current_stage == "completed"
    assert job.output_video_gcs_path == f"exports/{project_id}/es_render_{job_id.hex}.mp4"
    assert job.filesize_bytes == len(b"final-video")
    assert job.request_id == "new-request"
    assert job.task_id == "celery-task-1"
    assert job.idempotency_key == "new-idempotency"
    assert media.storage_path == "gs://bucket/source.mp4"
    upload.assert_awaited_once()
    render.assert_awaited_once()
    cleanup.assert_called_once()
    assert db.rollbacks == 0
    assert db.closed == 1


def test_render_video_export_task_marks_failed_and_retries_on_cancellation(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tasks.export_tasks.settings.PROCESSED_MEDIA_DIR", str(tmp_path))

    job_id = uuid.uuid4()
    media_file_id = uuid.uuid4()
    project_id = uuid.uuid4()
    job = _export_job(job_id, media_file_id, project_id)
    media = _media_file(media_file_id, project_id, job.workspace_id)
    db = _FakeSession(first_values={ExportJob: job, MediaFile: media})
    monkeypatch.setattr(render_video_export_task.request, "id", "celery-task-2", raising=False)
    monkeypatch.setattr(render_video_export_task, "retry", MagicMock(side_effect=_RetrySignal("retry")), raising=False)

    with (
        patch("app.tasks.export_tasks.SyncSession", return_value=db),
        patch("app.tasks.export_tasks.publish_export_progress"),
        patch.object(export_tasks_module.export_queue_manager, "register_job"),
        patch.object(export_tasks_module.export_queue_manager, "deregister_job"),
        patch.object(export_tasks_module.export_queue_manager, "cleanup_temporary_files") as cleanup,
        patch.object(export_tasks_module.export_queue_manager, "is_cancelled", return_value=True),
        patch("app.tasks.export_tasks.storage_service.download_file", new=AsyncMock()) as download,
        patch("app.tasks.export_tasks.export_orchestrator.process_export_render", new=AsyncMock()) as render,
        pytest.raises(_RetrySignal),
    ):
        render_video_export_task(
            str(job_id),
            str(media_file_id),
            "es",
            {"format": "mp4"},
        )

    assert job.status == "failed"
    assert job.error_message == "Export task was cancelled by user."
    assert db.rollbacks == 1
    assert db.closed == 1
    download.assert_not_awaited()
    render.assert_not_awaited()
    cleanup.assert_called_once()


def test_run_lipsync_project_pipeline_completes_and_records_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tasks.lipsync_tasks.settings.PROCESSED_MEDIA_DIR", str(tmp_path))

    job_id = uuid.uuid4()
    media_file_id = uuid.uuid4()
    transcript_id = uuid.uuid4()
    project_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    segments = [
        SimpleNamespace(
            id=uuid.uuid4(),
            transcript_id=transcript_id,
            speaker_tag="Speaker 1",
            start_time_seconds=0.0,
            end_time_seconds=1.0,
            duration_seconds=1.0,
            text="One",
            sequence_order=1,
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            transcript_id=transcript_id,
            speaker_tag="Speaker 2",
            start_time_seconds=1.0,
            end_time_seconds=2.5,
            duration_seconds=1.5,
            text="Two",
            sequence_order=2,
        ),
    ]
    job, media, transcript, project, translations = _lipsync_entities(
        job_id,
        media_file_id,
        transcript_id,
        project_id,
        workspace_id,
        segments,
    )
    monkeypatch.setattr("app.tasks.lipsync_tasks.Translation", _DummyTranslation)
    db = _FakeSession(
        first_values={
            LipSyncJob: job,
            MediaFile: media,
            Transcript: transcript,
            Project: project,
        },
        all_values={
            TranscriptSegment: segments,
            _DummyTranslation: translations,
        },
    )

    def download_file(source_key, destination_path, **kwargs):
        _write_output(destination_path, b"downloaded")

    def extract_video_segment(**kwargs):
        _write_output(kwargs["output_segment_path"], b"segment")

    def extract_frame_at_timestamp(video_path, timestamp_seconds, output_jpg_path):
        _write_output(output_jpg_path, b"frame")

    def render_segment_lipsync(**kwargs):
        _write_output(kwargs["output_rendered_path"], b"rendered")
        return kwargs["output_rendered_path"]

    def reconstruct_video_with_lip_sync(**kwargs):
        _write_output(kwargs["output_final_video_path"], b"final-mux")
        return kwargs["output_final_video_path"]

    fake_task_instance = SimpleNamespace(request=SimpleNamespace(id="celery-task-3"), retry=MagicMock(side_effect=_RetrySignal("retry")))

    with (
        patch("app.tasks.lipsync_tasks.joinedload", side_effect=lambda attr: attr),
        patch("app.tasks.lipsync_tasks.SyncSession", return_value=db),
        patch("app.tasks.lipsync_tasks.publish_lipsync_event"),
        patch("app.tasks.lipsync_tasks.storage_service.download_file", new=AsyncMock(side_effect=download_file)),
        patch("app.tasks.lipsync_tasks.storage_service.upload_file", new=AsyncMock(return_value="gs://bucket/final.mp4")),
        patch("app.tasks.lipsync_tasks.video_processor.extract_video_segment", new=AsyncMock(side_effect=extract_video_segment)),
        patch("app.tasks.lipsync_tasks.video_processor.extract_frame_at_timestamp", new=AsyncMock(side_effect=extract_frame_at_timestamp)),
        patch("app.tasks.lipsync_tasks.replicate_lipsync.render_segment_lipsync", new=AsyncMock(side_effect=render_segment_lipsync)),
        patch("app.tasks.lipsync_tasks.video_reconstructor.reconstruct_video_with_lip_sync", new=AsyncMock(side_effect=reconstruct_video_with_lip_sync)),
        patch("app.tasks.lipsync_tasks.face_detector.analyze_frame", return_value=SimpleNamespace(
            face_detected=True,
            is_suitable_for_lipsync=True,
            confidence=0.91,
            bbox={"x": 1},
            landmarks={"nose": [1, 2]},
            head_rotation_deg=1.5,
        )),
        patch("app.tasks.lipsync_tasks.av_sync_service.measure_av_drift_ms", new=AsyncMock(return_value=12.5)),
        patch("app.tasks.lipsync_tasks.quality_metrics.evaluate_lipsync_quality", return_value={"overall_quality_score": 0.9876}),
        patch("app.tasks.lipsync_tasks.gpu_scheduler.estimate_eta_seconds", return_value=42.0),
        patch("app.tasks.lipsync_tasks.run_project_tts_pipeline", return_value={"status": "completed"}) as tts,
    ):
        result = run_lipsync_project_pipeline(
            str(job_id),
            str(media_file_id),
            str(transcript_id),
            "fr",
            request_id="new-request",
            task_id="new-task",
            idempotency_key="new-idempotency",
            task_instance=fake_task_instance,
        )

    assert result["status"] == "completed"
    assert result["job_id"] == str(job_id)
    assert result["output_video_path"] == f"exports/{project_id}/fr/{job.id}_{job.render_mode}_translated_master.mp4"
    assert result["quality_score"] == 0.9876
    assert result["execution_duration_sec"] >= 0
    assert job.status == "completed"
    assert job.current_stage == "export"
    assert job.last_successful_stage == "export"
    assert job.progress_percent == 100
    assert job.total_segments == 2
    assert job.completed_segments == 2
    assert job.output_video_gcs_path == f"exports/{project_id}/fr/{job.id}_{job.render_mode}_translated_master.mp4"
    assert job.output_filesize_bytes == len(b"final-mux")
    assert job.quality_score == 0.9876
    assert project.status == "completed"
    assert project.current_lipsync_job_id == job.id
    assert project.last_rendered_video_gcs_path == job.output_video_gcs_path
    assert job.request_id == "stored-request"
    assert job.task_id == "stored-task"
    assert job.idempotency_key == "stored-idempotency"
    assert tts.call_args.kwargs["idempotency_key"] == "stored-idempotency:tts"
    assert db.added and all(entity.__class__.__name__ == "FrameMetadata" for entity in db.added)
    assert db.rollbacks == 0
    assert db.closed == 1


def test_run_lipsync_project_pipeline_allows_shared_media_and_transcript_for_a_different_job_project(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tasks.lipsync_tasks.settings.PROCESSED_MEDIA_DIR", str(tmp_path))

    job_id = uuid.uuid4()
    media_file_id = uuid.uuid4()
    transcript_id = uuid.uuid4()
    source_project_id = uuid.uuid4()
    render_project_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    segments = [
        SimpleNamespace(
            id=uuid.uuid4(),
            transcript_id=transcript_id,
            speaker_tag="Speaker 1",
            start_time_seconds=0.0,
            end_time_seconds=1.0,
            duration_seconds=1.0,
            text="One",
            sequence_order=1,
        ),
    ]
    job, media, transcript, project, translations = _lipsync_entities(
        job_id,
        media_file_id,
        transcript_id,
        source_project_id,
        workspace_id,
        segments,
    )
    job.project_id = render_project_id
    project.id = render_project_id
    monkeypatch.setattr("app.tasks.lipsync_tasks.Translation", _DummyTranslation)
    db = _FakeSession(
        first_values={
            LipSyncJob: job,
            MediaFile: media,
            Transcript: transcript,
            Project: project,
        },
        all_values={
            TranscriptSegment: segments,
            _DummyTranslation: translations,
        },
    )

    def download_file(source_key, destination_path, **kwargs):
        _write_output(destination_path, b"downloaded")

    def extract_video_segment(**kwargs):
        _write_output(kwargs["output_segment_path"], b"segment")

    def extract_frame_at_timestamp(video_path, timestamp_seconds, output_jpg_path):
        _write_output(output_jpg_path, b"frame")

    def render_segment_lipsync(**kwargs):
        _write_output(kwargs["output_rendered_path"], b"rendered")
        return kwargs["output_rendered_path"]

    def reconstruct_video_with_lip_sync(**kwargs):
        _write_output(kwargs["output_final_video_path"], b"final-mux")
        return kwargs["output_final_video_path"]

    fake_task_instance = SimpleNamespace(request=SimpleNamespace(id="celery-task-4"), retry=MagicMock(side_effect=_RetrySignal("retry")))

    with (
        patch("app.tasks.lipsync_tasks.joinedload", side_effect=lambda attr: attr),
        patch("app.tasks.lipsync_tasks.SyncSession", return_value=db),
        patch("app.tasks.lipsync_tasks.publish_lipsync_event"),
        patch("app.tasks.lipsync_tasks.storage_service.download_file", new=AsyncMock(side_effect=download_file)),
        patch("app.tasks.lipsync_tasks.storage_service.upload_file", new=AsyncMock(return_value="gs://bucket/final.mp4")),
        patch("app.tasks.lipsync_tasks.video_processor.extract_video_segment", new=AsyncMock(side_effect=extract_video_segment)),
        patch("app.tasks.lipsync_tasks.video_processor.extract_frame_at_timestamp", new=AsyncMock(side_effect=extract_frame_at_timestamp)),
        patch("app.tasks.lipsync_tasks.replicate_lipsync.render_segment_lipsync", new=AsyncMock(side_effect=render_segment_lipsync)),
        patch("app.tasks.lipsync_tasks.video_reconstructor.reconstruct_video_with_lip_sync", new=AsyncMock(side_effect=reconstruct_video_with_lip_sync)),
        patch("app.tasks.lipsync_tasks.face_detector.analyze_frame", return_value=SimpleNamespace(
            face_detected=True,
            is_suitable_for_lipsync=True,
            confidence=0.91,
            bbox={"x": 1},
            landmarks={"nose": [1, 2]},
            head_rotation_deg=1.5,
        )),
        patch("app.tasks.lipsync_tasks.av_sync_service.measure_av_drift_ms", new=AsyncMock(return_value=12.5)),
        patch("app.tasks.lipsync_tasks.quality_metrics.evaluate_lipsync_quality", return_value={"overall_quality_score": 0.9876}),
        patch("app.tasks.lipsync_tasks.gpu_scheduler.estimate_eta_seconds", return_value=42.0),
        patch("app.tasks.lipsync_tasks.run_project_tts_pipeline", return_value={"status": "completed"}),
    ):
        result = run_lipsync_project_pipeline(
            str(job_id),
            str(media_file_id),
            str(transcript_id),
            "fr",
            request_id="new-request",
            task_id="new-task",
            idempotency_key="new-idempotency",
            task_instance=fake_task_instance,
        )

    assert result["status"] == "completed"
    assert job.status == "completed"
    assert project.current_lipsync_job_id == job.id
    assert job.output_video_gcs_path == f"exports/{render_project_id}/fr/{job.id}_{job.render_mode}_translated_master.mp4"
    assert db.rollbacks == 0
    assert db.closed == 1


def test_run_lipsync_project_pipeline_marks_failed_and_retries_on_tts_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tasks.lipsync_tasks.settings.PROCESSED_MEDIA_DIR", str(tmp_path))

    job_id = uuid.uuid4()
    media_file_id = uuid.uuid4()
    transcript_id = uuid.uuid4()
    project_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    segments = [
        SimpleNamespace(
            id=uuid.uuid4(),
            transcript_id=transcript_id,
            speaker_tag="Speaker 1",
            start_time_seconds=0.0,
            end_time_seconds=1.0,
            duration_seconds=1.0,
            text="One",
            sequence_order=1,
        )
    ]
    job, media, transcript, project, translations = _lipsync_entities(
        job_id,
        media_file_id,
        transcript_id,
        project_id,
        workspace_id,
        segments,
    )
    monkeypatch.setattr("app.tasks.lipsync_tasks.Translation", _DummyTranslation)
    db = _FakeSession(
        first_values={
            LipSyncJob: job,
            MediaFile: media,
            Transcript: transcript,
            Project: project,
        },
        all_values={
            TranscriptSegment: segments,
            _DummyTranslation: translations,
        },
    )
    fake_task_instance = SimpleNamespace(request=SimpleNamespace(id="celery-task-4"), retry=MagicMock(side_effect=_RetrySignal("retry")))

    with (
        patch("app.tasks.lipsync_tasks.joinedload", side_effect=lambda attr: attr),
        patch("app.tasks.lipsync_tasks.SyncSession", return_value=db),
        patch("app.tasks.lipsync_tasks.publish_lipsync_event"),
        patch("app.tasks.lipsync_tasks.run_project_tts_pipeline", side_effect=RuntimeError("tts failed")),
        patch("app.tasks.lipsync_tasks.storage_service.download_file", new=AsyncMock()),
        patch("app.tasks.lipsync_tasks.video_processor.extract_video_segment", new=AsyncMock()),
        patch("app.tasks.lipsync_tasks.video_processor.extract_frame_at_timestamp", new=AsyncMock()),
        patch("app.tasks.lipsync_tasks.replicate_lipsync.render_segment_lipsync", new=AsyncMock()),
        patch("app.tasks.lipsync_tasks.video_reconstructor.reconstruct_video_with_lip_sync", new=AsyncMock()),
        patch("app.tasks.lipsync_tasks.face_detector.analyze_frame", return_value=SimpleNamespace(
            face_detected=True,
            is_suitable_for_lipsync=True,
            confidence=0.91,
            bbox=None,
            landmarks=None,
            head_rotation_deg=0.0,
        )),
        patch("app.tasks.lipsync_tasks.av_sync_service.measure_av_drift_ms", new=AsyncMock(return_value=12.5)),
        patch("app.tasks.lipsync_tasks.quality_metrics.evaluate_lipsync_quality", return_value={"overall_quality_score": 0.95}),
        patch("app.tasks.lipsync_tasks.gpu_scheduler.estimate_eta_seconds", return_value=10.0),
        pytest.raises(_RetrySignal),
    ):
        run_lipsync_project_pipeline(
            str(job_id),
            str(media_file_id),
            str(transcript_id),
            "fr",
            task_instance=fake_task_instance,
        )

    assert job.status == "failed"
    assert job.error_message == "tts failed"
    assert job.current_stage == "voice"
    assert job.last_successful_stage is None
    assert project.status == "failed"
    assert project.current_lipsync_job_id == job.id
    assert db.rollbacks == 1
    assert db.closed == 1

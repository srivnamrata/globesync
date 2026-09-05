import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import HTTPException

from app.routers import internal_tasks
from app.routers.internal_tasks import (
    RenderLipSyncProjectTaskPayload,
    TranscribeTaskPayload,
    TranslateProjectTaskPayload,
)


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _Scalars(self.values)


class _Database:
    def __init__(self, *, gets=None, query_values=None):
        self.gets = list(gets or [])
        self.query_values = list(query_values or [])
        self.commit = AsyncMock()
        self.delete = AsyncMock()
        self.added = []

    async def get(self, model, identifier):
        return self.gets.pop(0) if self.gets else None

    async def execute(self, statement):
        values = self.query_values.pop(0) if self.query_values else []
        return _Result(values)

    def add(self, entity):
        self.added.append(entity)


@pytest.mark.asyncio
async def test_checkpoint_translation_operation_updates_durable_state():
    operation = SimpleNamespace(
        status="queued",
        current_stage="queued",
        progress_percent=0,
        message="queued",
        error_message=None,
        last_successful_stage=None,
    )
    database = _Database(gets=[operation])

    await internal_tasks._checkpoint_translation_operation(
        database,
        "operation-1",
        status_value="completed",
        progress_percent=100,
        message="done",
    )

    assert operation.status == "completed"
    assert operation.current_stage == "translate"
    assert operation.last_successful_stage == "translate"
    database.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_checkpoint_translation_operation_ignores_missing_identifier_or_row():
    database = _Database(gets=[None])

    await internal_tasks._checkpoint_translation_operation(
        database,
        "",
        status_value="failed",
        progress_percent=0,
        message="failed",
    )
    await internal_tasks._checkpoint_translation_operation(
        database,
        "missing",
        status_value="failed",
        progress_percent=0,
        message="failed",
    )

    database.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcribe_handler_forwards_security_and_idempotency_context():
    payload = TranscribeTaskPayload(
        media_id=uuid.uuid4(),
        transcript_id=uuid.uuid4(),
        language="fr",
        max_speakers=3,
        enable_noise_reduction=False,
        enable_loudness_norm=True,
        enable_vad=False,
        job_id="job-12345",
        request_id="request-1",
        idempotency_key="stable-key",
        source_action="retry",
    )

    with patch.object(
        internal_tasks,
        "run_transcription_pipeline",
        return_value={"status": "completed", "segments": 4},
    ) as run:
        response = await internal_tasks.run_transcribe_task(
            payload,
            x_cloudtasks_taskname="cloud-task-name",
            _=None,
        )

    assert response == {
        "status": "completed",
        "job_id": "job-12345",
        "transcript_id": str(payload.transcript_id),
        "segments": 4,
    }
    run.assert_called_once_with(
        media_id_str=str(payload.media_id),
        transcript_id_str=str(payload.transcript_id),
        language="fr",
        max_speakers=3,
        enable_noise_reduction=False,
        enable_loudness_norm=True,
        request_id="request-1",
        task_id="cloud-task-name",
        idempotency_key="stable-key",
        source_action="retry",
        operation_id="job-12345",
    )


@pytest.mark.asyncio
async def test_translate_handler_rejects_missing_or_mismatched_transcript():
    payload = TranslateProjectTaskPayload(
        transcript_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        target_language="es",
        job_id="job-12345",
    )

    with pytest.raises(HTTPException) as missing:
        await internal_tasks.run_translate_project_task(
            payload,
            _Database(gets=[None]),
            None,
            None,
        )
    assert missing.value.status_code == 404

    transcript = SimpleNamespace(project_id=uuid.uuid4())
    with pytest.raises(HTTPException) as mismatch:
        await internal_tasks.run_translate_project_task(
            payload,
            _Database(gets=[transcript]),
            None,
            None,
        )
    assert mismatch.value.status_code == 404


@pytest.mark.asyncio
async def test_translate_handler_rejects_empty_transcript():
    payload = TranslateProjectTaskPayload(
        transcript_id=uuid.uuid4(),
        target_language="es",
        job_id="job-12345",
    )
    transcript = SimpleNamespace(project_id=None, workspace_id=uuid.uuid4())

    with pytest.raises(HTTPException) as error:
        await internal_tasks.run_translate_project_task(
            payload,
            _Database(gets=[transcript], query_values=[[]]),
            None,
            None,
        )

    assert error.value.detail == "No transcript segments found."


@pytest.mark.asyncio
async def test_translate_handler_replaces_existing_rows_and_checkpoints():
    project_id = uuid.uuid4()
    payload = TranslateProjectTaskPayload(
        transcript_id=uuid.uuid4(),
        project_id=project_id,
        source_language="en",
        target_language="de",
        job_id="job-12345",
        operation_id="operation-1",
        request_id="request-1",
        idempotency_key="translate-key",
    )
    transcript = SimpleNamespace(project_id=project_id, workspace_id=uuid.uuid4())
    segments = [SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())]
    existing = [SimpleNamespace(id=uuid.uuid4())]
    translated = [SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())]
    database = _Database(
        gets=[transcript],
        query_values=[segments, existing],
    )

    with (
        patch.object(
            internal_tasks.translation_service,
            "translate_segments_batch_async",
            new=AsyncMock(return_value=translated),
        ) as translate,
        patch.object(
            internal_tasks,
            "_checkpoint_translation_operation",
            new=AsyncMock(),
        ) as checkpoint,
    ):
        response = await internal_tasks.run_translate_project_task(
            payload,
            database,
            "cloud-task",
            None,
        )

    assert response["segments_translated"] == 2
    translate.assert_awaited_once_with(
        segments=segments,
        source_language="en",
        target_language="de",
        project_id=project_id,
        workspace_id=transcript.workspace_id,
        request_id="request-1",
        task_id="cloud-task",
        source_action="translate_project_cloud_task",
        idempotency_key_prefix="translate-key",
        concurrency_limit=5,
    )
    database.delete.assert_awaited_once_with(existing[0])
    assert database.added == translated
    assert checkpoint.await_args_list == [
        call(
            database,
            "operation-1",
            status_value="in_progress",
            progress_percent=10,
            message="Loading transcript segments",
        ),
        call(
            database,
            "operation-1",
            status_value="in_progress",
            progress_percent=30,
            message="Translating 2 segments",
        ),
        call(
            database,
            "operation-1",
            status_value="completed",
            progress_percent=100,
            message="Translated 2 segments.",
        ),
    ]


@pytest.mark.asyncio
async def test_translate_handler_checkpoints_provider_failure():
    payload = TranslateProjectTaskPayload(
        transcript_id=uuid.uuid4(),
        target_language="es",
        job_id="job-12345",
    )
    transcript = SimpleNamespace(project_id=None, workspace_id=uuid.uuid4())
    segments = [SimpleNamespace(id=uuid.uuid4())]
    database = _Database(gets=[transcript], query_values=[segments])

    with (
        patch.object(
            internal_tasks.translation_service,
            "translate_segments_batch_async",
            new=AsyncMock(side_effect=RuntimeError("provider unavailable")),
        ),
        patch.object(
            internal_tasks,
            "_checkpoint_translation_operation",
            new=AsyncMock(),
        ) as checkpoint,
        pytest.raises(RuntimeError, match="provider unavailable"),
    ):
        await internal_tasks.run_translate_project_task(payload, database, None, None)

    assert checkpoint.await_args_list[-1] == call(
        database,
        "job-12345",
        status_value="failed",
        progress_percent=0,
        message="Translation failed",
        error_message="provider unavailable",
    )


@pytest.mark.asyncio
async def test_lipsync_handler_forwards_render_mode_and_task_identity():
    payload = RenderLipSyncProjectTaskPayload(
        job_id=uuid.uuid4(),
        media_file_id=uuid.uuid4(),
        transcript_id=uuid.uuid4(),
        target_language="ja",
        model_preference="wav2lip",
        burn_in_subtitles=True,
        enable_lipsync=False,
        request_id="request-1",
        idempotency_key="stable-key",
    )
    expected = {"status": "completed", "output": "gs://bucket/final.mp4"}

    with patch.object(
        internal_tasks,
        "run_lipsync_project_pipeline",
        return_value=expected,
    ) as run:
        response = await internal_tasks.run_render_lipsync_project_task(
            payload,
            x_cloudtasks_taskname=None,
            _=None,
        )

    assert response == expected
    run.assert_called_once_with(
        job_id_str=str(payload.job_id),
        media_file_id_str=str(payload.media_file_id),
        transcript_id_str=str(payload.transcript_id),
        target_language="ja",
        model_preference="wav2lip",
        burn_in_subtitles=True,
        enable_lipsync=False,
        request_id="request-1",
        task_id=str(payload.job_id),
        idempotency_key="stable-key",
    )

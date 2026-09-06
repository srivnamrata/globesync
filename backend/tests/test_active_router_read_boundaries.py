import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers import export, lipsync, transcription, tts
from app.schemas.lipsync_schema import ReplicateWebhookPayload


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return _Scalars(self.values or [])


class _Database:
    def __init__(self, *results):
        self.results = list(results)
        self.commit = AsyncMock()

    async def execute(self, statement):
        value = self.results.pop(0)
        return value if isinstance(value, _Result) else _Result(value=value)


def _context():
    return SimpleNamespace(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        membership_role="owner",
    )


def _export_job(**overrides):
    values = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "media_file_id": uuid.uuid4(),
        "target_language": "es",
        "format": "mp4",
        "resolution": "1080p",
        "frame_rate": 30,
        "codec": "h264",
        "status": "completed",
        "progress_percent": 100,
        "current_stage": "completed",
        "output_video_gcs_path": "exports/result.mp4",
        "filesize_bytes": 2048,
        "estimated_cost_usd": 1.25,
        "created_at": datetime.now(timezone.utc),
        "error_message": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_export_status_enforces_scope_and_issues_playback_and_download_urls():
    context = _context()
    job = _export_job(workspace_id=context.workspace_id)
    database = _Database(job)

    with (
        patch.object(export, "ensure_workspace_resource_access", new=AsyncMock()) as scope,
        patch.object(
            export.storage_service,
            "generate_presigned_download_url",
            side_effect=["https://play", "https://download"],
        ) as sign,
    ):
        response = await export.get_export_job_status(job.id, context, database)

    assert response.output_video_url == "https://play"
    assert response.download_video_url == "https://download"
    scope.assert_awaited_once_with(
        db=database,
        context=context,
        workspace_id=job.workspace_id,
        project_id=job.project_id,
        not_found_detail="Export job not found.",
    )
    assert sign.call_args_list[1].kwargs["download_filename"].endswith(f"{job.id}.mp4")


@pytest.mark.asyncio
async def test_export_status_not_found_does_not_generate_signed_url():
    with patch.object(export.storage_service, "generate_presigned_download_url") as sign:
        with pytest.raises(HTTPException) as error:
            await export.get_export_job_status(uuid.uuid4(), _context(), _Database(None))
    assert error.value.status_code == 404
    sign.assert_not_called()


@pytest.mark.asyncio
async def test_export_cancel_updates_state_only_after_queue_accepts():
    context = _context()
    job = _export_job(workspace_id=context.workspace_id, status="processing")
    database = _Database(job)

    with (
        patch.object(export, "ensure_workspace_resource_access", new=AsyncMock()),
        patch.object(export.export_queue_manager, "cancel_job", return_value=True),
    ):
        response = await export.cancel_export_job(job.id, context, database)

    assert response["status"] == "cancelled"
    assert job.status == "failed"
    assert job.error_message == "Export cancelled by user."
    database.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_export_history_signs_only_completed_outputs():
    context = _context()
    completed = _export_job(workspace_id=context.workspace_id)
    pending = _export_job(
        workspace_id=context.workspace_id,
        output_video_gcs_path=None,
        status="processing",
        progress_percent=50,
    )
    database = _Database(_Result(values=[completed, pending]))

    with patch.object(
        export.storage_service,
        "generate_presigned_download_url",
        side_effect=["https://play", "https://download"],
    ) as sign:
        response = await export.get_export_history(None, context, database)

    assert [item.status for item in response] == ["completed", "processing"]
    assert response[1].output_video_url is None
    assert sign.call_count == 2


def _frame(sequence):
    return SimpleNamespace(
        id=uuid.uuid4(),
        transcript_segment_id=uuid.uuid4(),
        sequence_order=sequence,
        start_time_seconds=sequence,
        end_time_seconds=sequence + 0.5,
        face_detected=True,
        face_confidence=0.9,
        head_rotation_deg=1.5,
        render_status="completed",
        av_sync_offset_ms=10,
        quality_score=0.95,
    )


def _lipsync_job(**overrides):
    values = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "media_file_id": uuid.uuid4(),
        "target_language": "fr",
        "model_name": "liveportrait",
        "render_mode": "dub_and_lipsync",
        "status": "completed",
        "progress_percent": 100,
        "current_stage": "completed",
        "last_successful_stage": "upload",
        "total_segments": 2,
        "completed_segments": 2,
        "output_video_gcs_path": "renders/final.mp4",
        "output_filesize_bytes": 4096,
        "quality_score": 0.93,
        "av_sync_error_ms": 12,
        "segments_metadata": [_frame(2), _frame(1)],
        "execution_time_seconds": 3.5,
        "created_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_lipsync_status_orders_metadata_and_signs_download():
    context = _context()
    job = _lipsync_job(workspace_id=context.workspace_id)

    with (
        patch.object(lipsync, "ensure_workspace_resource_access", new=AsyncMock()),
        patch.object(
            lipsync.storage_service,
            "generate_presigned_download_url",
            side_effect=["https://play", "https://download"],
        ),
    ):
        response = await lipsync.get_lipsync_job(job.id, context, _Database(job))

    assert [item.sequence_order for item in response.segments_metadata] == [1, 2]
    assert response.output_video_url == "https://play"
    assert response.download_video_url == "https://download"


@pytest.mark.asyncio
async def test_lipsync_not_found_and_webhook_acknowledgement():
    with pytest.raises(HTTPException) as error:
        await lipsync.get_lipsync_job(uuid.uuid4(), _context(), _Database(None))
    assert error.value.status_code == 404

    payload = ReplicateWebhookPayload(id="prediction-1", status="succeeded")
    assert await lipsync.replicate_webhook_callback(payload) == {
        "status": "acknowledged",
        "prediction_id": "prediction-1",
    }


def _transcript(workspace_id):
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    segments = [
        SimpleNamespace(
            id=second_id,
            sequence_order=2,
            start_time_seconds=2,
            end_time_seconds=3,
            duration_seconds=1,
            speaker_tag="Speaker 2",
            text="Second",
            confidence=None,
            words=None,
        ),
        SimpleNamespace(
            id=first_id,
            sequence_order=1,
            start_time_seconds=0,
            end_time_seconds=1,
            duration_seconds=1,
            speaker_tag="Speaker 1",
            text="First",
            confidence=0.99,
            words=[
                {
                    "text": "First",
                    "start": 0,
                    "end": 1,
                    "confidence": 0.99,
                    "speaker": "Speaker 1",
                }
            ],
        ),
    ]
    return SimpleNamespace(
        id=uuid.uuid4(),
        media_file_id=uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        status="completed",
        detected_language="en",
        confidence_score=0.95,
        word_count=2,
        speaker_count=2,
        full_text="First Second",
        segments=segments,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_transcript_read_sorts_segments_and_normalizes_words():
    context = _context()
    record = _transcript(context.workspace_id)

    with patch.object(
        transcription,
        "ensure_workspace_resource_access",
        new=AsyncMock(),
    ) as scope:
        response = await transcription.get_transcript(
            record.id,
            context,
            _Database(record),
        )

    assert [segment.text for segment in response.segments] == ["First", "Second"]
    assert response.segments[0].words[0].speaker == "Speaker 1"
    assert response.segments[1].confidence is None
    scope.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("export_format", "media_type", "content_marker"),
    [
        ("srt", "text/plain", b"First"),
        ("vtt", "text/vtt", b"WEBVTT"),
        ("txt", "text/plain", b"Speaker 1"),
    ],
)
async def test_transcript_export_formats(export_format, media_type, content_marker):
    context = _context()
    record = _transcript(context.workspace_id)

    with patch.object(
        transcription,
        "ensure_workspace_resource_access",
        new=AsyncMock(),
    ):
        response = await transcription.export_transcript(
            record.id,
            export_format,
            context,
            _Database(record),
        )

    assert response.media_type.startswith(media_type)
    assert content_marker in response.body


@pytest.mark.asyncio
async def test_transcript_json_export_returns_typed_payload():
    context = _context()
    record = _transcript(context.workspace_id)

    with patch.object(
        transcription,
        "ensure_workspace_resource_access",
        new=AsyncMock(),
    ):
        response = await transcription.export_transcript(
            record.id,
            "json",
            context,
            _Database(record),
        )

    assert response.transcript_id == record.id
    assert response.full_text == "First Second"


@pytest.mark.asyncio
async def test_master_audio_requires_project_scope_and_uses_language_key():
    context = _context()
    project_id = uuid.uuid4()

    with (
        patch.object(tts, "get_scoped_project", new=AsyncMock()) as scoped,
        patch.object(
            tts.storage_service,
            "generate_presigned_download_url",
            return_value="https://storage.example/master",
        ) as sign,
    ):
        response = await tts.get_master_audio(project_id, "de", context, _Database())

    assert response.storage_path == f"master_dubbed/{project_id}/de_dubbed.wav"
    assert response.master_audio_url == "https://storage.example/master"
    scoped.assert_awaited_once()
    sign.assert_called_once_with(response.storage_path, expires_in_seconds=7200)

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.models.lipsync_job import LipSyncJob
from app.models.media import MediaFile
from app.models.transcript import Transcript
from app.schemas.lipsync_schema import RenderLipSyncProjectRequest
from app.services.face_detection_service import face_detector
from app.tasks.gpu_task_scheduler import gpu_scheduler
from app.utils.quality_metrics import quality_metrics
from app.utils.replicate_utils import replicate_utils


# =============================================================================
# 1. FACE DETECTION & QUALITY METRICS TESTS
# =============================================================================
def test_face_detector_fallback():
    result = face_detector._mock_face_result()
    assert result.face_detected is True
    assert result.confidence >= 0.90
    assert result.bbox is not None
    assert "x" in result.bbox
    assert "mouth" in result.landmarks


def test_quality_metrics_sync_evaluation():
    # 1. High precision sync (20ms drift) -> High score (>0.90), no review needed
    q_high = quality_metrics.evaluate_lipsync_quality(
        av_sync_error_ms=20.0,
        face_confidence=0.95,
        duration_ratio=1.02,
    )
    assert q_high["overall_quality_score"] >= 0.90
    assert q_high["is_sync_compliant"] is True
    assert q_high["requires_manual_review"] is False

    # 2. Large drift (140ms drift) -> Flagged for manual review
    q_poor = quality_metrics.evaluate_lipsync_quality(
        av_sync_error_ms=140.0,
        face_confidence=0.70,
        duration_ratio=1.18,
    )
    assert q_poor["is_sync_compliant"] is False
    assert q_poor["requires_manual_review"] is True


def test_replicate_input_builders():
    lp_params = replicate_utils.build_liveportrait_input(
        image_or_video_url="https://s3.amazonaws.com/video.mp4",
        audio_url="https://s3.amazonaws.com/audio.wav",
        duration_sec=4.5,
    )
    assert lp_params["image"] == "https://s3.amazonaws.com/video.mp4"
    assert lp_params["audio"] == "https://s3.amazonaws.com/audio.wav"
    assert lp_params["duration"] == 4.5
    assert lp_params["face_expand_ratio"] == 1.25

    w2l_params = replicate_utils.build_wav2lip_input(
        face_video_url="https://s3.amazonaws.com/face.mp4",
        audio_url="https://s3.amazonaws.com/audio.wav",
    )
    assert w2l_params["face"] == "https://s3.amazonaws.com/face.mp4"
    assert w2l_params["smooth"] is True


def test_gpu_scheduler_eta():
    # 10 segments total, 2 completed in 12s -> avg 6s per segment -> 8 remaining * 6s = 48s ETA
    eta = gpu_scheduler.estimate_eta_seconds(total_segments=10, completed_segments=2, elapsed_seconds=12.0)
    assert eta == 48.0


# =============================================================================
# 2. FASTAPI LIP-SYNC ROUTE TESTS
# =============================================================================
@pytest.mark.asyncio
async def test_render_lipsync_project_endpoint():
    transport = ASGITransport(app=app)
    mock_media_id = uuid.uuid4()
    mock_transcript_id = uuid.uuid4()

    with patch("app.routers.lipsync.select") as mock_select, \
         patch("app.routers.lipsync.render_lipsync_project_task.apply_async") as mock_task:
        
        mock_task.return_value = MagicMock(id="celery-lipsync-uuid-111")

        mock_db = AsyncMock()
        mock_media = MediaFile(id=mock_media_id, duration_seconds=60.0)
        mock_transcript = Transcript(id=mock_transcript_id, detected_language="en")

        mock_exec = MagicMock()
        mock_exec.scalar_one_or_none.side_effect = [mock_media, mock_transcript]
        mock_db.execute = AsyncMock(return_value=mock_exec)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            req_body = {
                "media_file_id": str(mock_media_id),
                "transcript_id": str(mock_transcript_id),
                "target_language": "es",
                "model_preference": "liveportrait",
                "burn_in_subtitles": False,
            }
            parsed_req = RenderLipSyncProjectRequest(**req_body)
            assert parsed_req.media_file_id == mock_media_id
            assert parsed_req.transcript_id == mock_transcript_id
            assert parsed_req.model_preference == "liveportrait"


@pytest.mark.asyncio
async def test_replicate_webhook_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        webhook_payload = {
            "id": "pred_replicate_12345",
            "status": "succeeded",
            "output": "https://replicate.delivery/pbxt/output.mp4",
        }
        res = await client.post("/v1/lipsync/webhooks/replicate", json=webhook_payload)
        assert res.status_code == 200
        assert res.json()["status"] == "acknowledged"

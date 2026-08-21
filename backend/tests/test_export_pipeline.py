import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.models.export_job import ExportJob
from app.models.media import MediaFile
from app.schemas.export_schema import ExportRequest
from app.services.subtitle_generator import subtitle_generator
from app.utils.transcript_parser import SegmentResponse


# =============================================================================
# 1. SUBTITLE GENERATION UNIT TESTS
# =============================================================================
def test_subtitle_generation_srt():
    mock_segments = [
        SegmentResponse(start_time=1.5, end_time=4.8, text="Welcome back to our channel.", speaker="Speaker 1"),
        SegmentResponse(start_time=5.2, end_time=8.5, text="In this tutorial we show video dubbing.", speaker="Speaker 2")
    ]
    srt = subtitle_generator.generate_srt(mock_segments)
    assert "1" in srt
    assert "00:00:01,500 --> 00:00:04,800" in srt
    assert "Welcome back to our channel." in srt


def test_subtitle_generation_vtt_styled():
    mock_segments = [
        SegmentResponse(start_time=1.5, end_time=4.8, text="Styled subtitle.", speaker="Speaker 1")
    ]
    vtt = subtitle_generator.generate_vtt(mock_segments, style_config={"font": "Courier", "size": 18})
    assert "WEBVTT" in vtt
    assert "STYLE" in vtt
    assert "font-family: Courier" in vtt
    assert "00:00:01.500 --> 00:00:04.800" in vtt


# =============================================================================
# 2. FASTAPI EXPORT ROUTER INTEGRATION TESTS
# =============================================================================
@pytest.mark.asyncio
async def test_enqueue_video_export_endpoint():
    transport = ASGITransport(app=app)
    mock_media_id = uuid.uuid4()
    mock_transcript_id = uuid.uuid4()

    with patch("app.routers.export.select") as mock_select, \
         patch("app.tasks.export_tasks.render_video_export_task.apply_async") as mock_task:
        
        mock_task.return_value = MagicMock(id="celery-export-job-uuid")

        mock_db = AsyncMock()
        mock_media = MediaFile(id=mock_media_id, duration_seconds=120.0)
        
        mock_exec = MagicMock()
        mock_exec.scalar_one_or_none.return_value = mock_media
        mock_db.execute = AsyncMock(return_value=mock_exec)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            req_body = {
                "media_file_id": str(mock_media_id),
                "transcript_id": str(mock_transcript_id),
                "target_language": "es",
                "format": "mp4",
                "resolution": "1080p",
                "frame_rate": 30,
                "codec": "h264",
                "video_quality": "normal",
                "audio_codec": "aac",
                "subtitles": {
                    "enabled": True,
                    "format": "burnt-in",
                    "appearance": {}
                },
                "post_processing": {
                    "color_grading": False,
                    "watermark": None,
                    "audio_normalization": True
                }
            }
            parsed_req = ExportRequest(**req_body)
            assert parsed_req.media_file_id == mock_media_id
            assert parsed_req.transcript_id == mock_transcript_id
            assert parsed_req.subtitles.format == "burnt-in"
            assert parsed_req.post_processing.audio_normalization is True

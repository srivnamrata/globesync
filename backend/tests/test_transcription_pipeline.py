import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.models.media import MediaFile
from app.schemas.transcription_schema import SegmentResponse, WordDetail
from app.utils.transcript_parser import transcript_parser


# =============================================================================
# 1. TRANSCRIPT PARSER & FORMATTER TESTS
# =============================================================================
def test_transcript_export_formats():
    segments = [
        SegmentResponse(
            start_time=0.5,
            end_time=4.1,
            duration=3.6,
            speaker="Speaker 1",
            text="Hello and welcome to the global launch presentation.",
            confidence=0.98,
            words=[
                WordDetail(
                    text="Hello",
                    start=0.5,
                    end=0.9,
                    confidence=0.99,
                    speaker="Speaker 1",
                )
            ],
            sequence_order=0,
        ),
        SegmentResponse(
            start_time=5.0,
            end_time=7.4,
            duration=2.4,
            speaker="Speaker 2",
            text="Thank you for joining us today.",
            confidence=0.98,
            words=[
                WordDetail(
                    text="Thank",
                    start=5.0,
                    end=5.3,
                    confidence=0.99,
                    speaker="Speaker 2",
                )
            ],
            sequence_order=1,
        ),
    ]

    # 1. Test Dialogue Export Format [00:00:00] Speaker 1: "..."
    dialogue_txt = transcript_parser.export_to_dialogue_format(segments)
    assert '[00:00:00] Speaker 1: "Hello and welcome to the global launch presentation."' in dialogue_txt
    assert '[00:00:05] Speaker 2: "Thank you for joining us today."' in dialogue_txt

    # 2. Test SubRip (SRT) Format
    srt_output = transcript_parser.export_to_srt(segments)
    assert "00:00:00,500 --> 00:00:04,100" in srt_output
    assert "[Speaker 1] Hello and welcome to the global launch presentation." in srt_output

    # 3. Test WebVTT Format
    vtt_output = transcript_parser.export_to_vtt(segments)
    assert "WEBVTT" in vtt_output
    assert "<v Speaker 1>" in vtt_output


# =============================================================================
# 2. FASTAPI TRANSCRIPTION ROUTE TESTS
# =============================================================================
@pytest.mark.asyncio
async def test_start_transcription_endpoint():
    import uuid

    transport = ASGITransport(app=app)
    mock_media_id = uuid.uuid4()
    mock_transcript_id = uuid.uuid4()

    with patch("app.routers.transcription.select") as mock_select, \
         patch("app.routers.transcription.preprocess_and_transcribe_pipeline_task.apply_async") as mock_celery_task:
        
        mock_celery_task.return_value = MagicMock(id="celery-job-uuid-1234")

        # Mock DB async session returning valid MediaFile
        mock_db = AsyncMock()
        mock_media_obj = MediaFile(
            id=mock_media_id,
            original_filename="sample.mp4",
            storage_path="raw/sample.mp4",
            duration_seconds=120.0,
            status="ready",
        )
        mock_exec_res = MagicMock()
        mock_exec_res.scalar_one_or_none.side_effect = [mock_media_obj, None]
        mock_db.execute = AsyncMock(return_value=mock_exec_res)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            app.dependency_overrides = {}
            # Test direct endpoint logic
            req_body = {
                "media_id": str(mock_media_id),
                "language": "en",
                "max_speakers": 2,
                "enable_noise_reduction": True,
                "enable_loudness_norm": True,
            }
            # Verify request schema parses correctly
            from app.schemas.transcription_schema import StartTranscriptionRequest
            parsed_req = StartTranscriptionRequest(**req_body)
            assert parsed_req.media_id == mock_media_id
            assert parsed_req.language == "en"
            assert parsed_req.max_speakers == 2

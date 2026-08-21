import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.models.media import MediaFile
from app.models.transcript import Transcript, TranscriptSegment
from app.services.deepgram_service import deepgram_stt
from app.utils.transcript_parser import transcript_parser


# =============================================================================
# 1. TRANSCRIPT PARSER & FORMATTER TESTS
# =============================================================================
def test_transcript_parser_with_deepgram_paragraphs():
    mock_payload = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Hello world. This is speaker two speaking.",
                            "confidence": 0.98,
                            "words": [
                                {"word": "Hello", "punctuated_word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.99, "speaker": 0},
                                {"word": "world", "punctuated_word": "world.", "start": 0.6, "end": 1.1, "confidence": 0.98, "speaker": 0},
                                {"word": "This", "punctuated_word": "This", "start": 2.0, "end": 2.2, "confidence": 0.97, "speaker": 1},
                                {"word": "is", "punctuated_word": "is", "start": 2.3, "end": 2.4, "confidence": 0.98, "speaker": 1},
                                {"word": "speaker", "punctuated_word": "speaker", "start": 2.5, "end": 2.8, "confidence": 0.99, "speaker": 1},
                                {"word": "two", "punctuated_word": "two", "start": 2.9, "end": 3.1, "confidence": 0.97, "speaker": 1},
                                {"word": "speaking", "punctuated_word": "speaking.", "start": 3.2, "end": 3.8, "confidence": 0.99, "speaker": 1},
                            ],
                            "paragraphs": {
                                "paragraphs": [
                                    {
                                        "speaker": 0,
                                        "sentences": [{"text": "Hello world.", "start": 0.0, "end": 1.1}],
                                    },
                                    {
                                        "speaker": 1,
                                        "sentences": [{"text": "This is speaker two speaking.", "start": 2.0, "end": 3.8}],
                                    },
                                ]
                            },
                        }
                    ]
                }
            ]
        }
    }

    segments, full_text, avg_conf, word_count, speaker_count = transcript_parser.parse_deepgram_response(mock_payload)

    assert len(segments) == 2
    assert segments[0].speaker == "Speaker 1"
    assert segments[0].text == "Hello world."
    assert segments[0].start_time == 0.0
    assert segments[0].end_time == 1.1
    assert len(segments[0].words) == 2

    assert segments[1].speaker == "Speaker 2"
    assert segments[1].text == "This is speaker two speaking."
    assert segments[1].start_time == 2.0
    assert segments[1].end_time == 3.8

    assert speaker_count == 2
    assert word_count == 7
    assert avg_conf >= 0.95


def test_transcript_export_formats():
    mock_payload = deepgram_stt._generate_mock_deepgram_response("test.wav", "en")
    segments, _, _, _, _ = transcript_parser.parse_deepgram_response(mock_payload)

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

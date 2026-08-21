import hashlib
import io
import os
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.schemas.media_schema import MediaMetadata, MediaStreamInfo
from app.utils.file_validators import (
    calculate_sha256,
    detect_mime_type_from_header,
    validate_codecs,
    validate_file_metadata,
)
from app.utils.error_codes import (
    ChecksumMismatchException,
    FileTooLargeException,
    UnsupportedCodecException,
    UnsupportedMediaFormatException,
)


@pytest.fixture
def mock_storage():
    """Mock storage service calls for fast local unit testing without active S3/MinIO container."""
    with patch("app.routers.upload.storage_service") as mock_svc:
        mock_svc.initiate_multipart_upload.return_value = "mock_s3_upload_id_123"
        mock_svc.upload_part.return_value = '"mock_etag_456"'
        mock_svc.complete_multipart_upload.return_value = "s3://test-bucket/mock.mp4"
        mock_svc.upload_file = AsyncMock(return_value="s3://test-bucket/mock.mp4")
        mock_svc.download_file = AsyncMock()
        mock_svc.generate_presigned_download_url.return_value = "https://storage.googleapis.com/download-url"
        yield mock_svc


@pytest.fixture
def mock_media_service():
    """Mock FFprobe media metadata extraction."""
    with patch("app.routers.upload.media_service") as mock_media:
        mock_media.generate_storage_key.return_value = "raw/2026/08/test-key.mp4"
        mock_media.probe_media_file = AsyncMock(
            return_value=MediaMetadata(
                duration_seconds=185.5,
                filesize_bytes=10485760,
                mime_type="video/mp4",
                media_type="video",
                video=MediaStreamInfo(
                    codec="h264",
                    resolution_width=1920,
                    resolution_height=1080,
                    frame_rate=30.0,
                    bitrate_kbps=4500,
                ),
                audio=MediaStreamInfo(
                    codec="aac",
                    channels=2,
                    sample_rate=48000,
                    bitrate_kbps=192,
                ),
            )
        )
        mock_media.generate_thumbnail = AsyncMock(return_value="raw/2026/08/test-key.mp4.thumb.jpg")
        yield mock_media


# =============================================================================
# 1. FILE VALIDATOR UNIT TESTS
# =============================================================================
def test_mime_type_detection():
    # MP4 ISO signature
    mp4_header = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"
    assert detect_mime_type_from_header(mp4_header, "video.mp4") == "video/mp4"

    # EBML WebM signature
    webm_header = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01"
    assert detect_mime_type_from_header(webm_header, "clip.webm") == "video/webm"

    # WAV RIFF signature
    wav_header = b"RIFF\x24\x00\x00\x00WAVEfmt "
    assert detect_mime_type_from_header(wav_header, "audio.wav") == "audio/wav"

    # MP3 ID3 signature
    mp3_header = b"ID3\x03\x00\x00\x00\x00\x0f\x76"
    assert detect_mime_type_from_header(mp3_header, "track.mp3") == "audio/mpeg"


def test_file_size_validation():
    # Exceeding 4GB limit should raise FileTooLargeException
    with pytest.raises(FileTooLargeException):
        validate_file_metadata("large.mp4", 5 * 1024 * 1024 * 1024, "video/mp4", 4 * 1024 * 1024 * 1024)

    # Unsupported format should raise UnsupportedMediaFormatException
    with pytest.raises(UnsupportedMediaFormatException):
        validate_file_metadata("malware.exe", 1024, "application/x-msdownload", 4 * 1024 * 1024 * 1024)


def test_codec_validation():
    # Valid codecs should pass
    validate_codecs("h264", "aac", is_video=True)
    validate_codecs("vp9", "opus", is_video=True)
    validate_codecs(None, "pcm_s16le", is_video=False)

    # Invalid video codec should raise UnsupportedCodecException
    with pytest.raises(UnsupportedCodecException):
        validate_codecs("wmv3", "aac", is_video=True)

    # Invalid audio codec should raise UnsupportedCodecException
    with pytest.raises(UnsupportedCodecException):
        validate_codecs("h264", "wmapro", is_video=True)


# =============================================================================
# 2. FASTAPI ASYNC ENDPOINT TESTS
# =============================================================================
@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_resumable_upload_lifecycle(mock_storage, mock_media_service):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initialize Resumable Upload
        init_payload = {
            "filename": "conference_talk.mp4",
            "filesize_bytes": 16777216,  # 16 MB = 2 chunks of 8MB
            "mime_type": "video/mp4",
            "chunk_size_bytes": 8388608,
        }
        init_res = await client.post("/v1/media/uploads/resumable", json=init_payload)
        assert init_res.status_code == 201
        data = init_res.json()
        upload_id = data["upload_id"]
        assert data["total_chunks"] == 2
        assert data["filename"] == "conference_talk.mp4"

        # 2. Upload Chunk 0
        chunk_0_data = b"0" * 8388608
        chunk_0_hash = hashlib.sha256(chunk_0_data).hexdigest()
        chunk_0_headers = {
            "Content-Range": "bytes 0-8388607/16777216",
            "X-Chunk-Index": "0",
            "X-Checksum-SHA256": chunk_0_hash,
            "Content-Type": "application/octet-stream",
        }
        chunk_0_res = await client.put(
            f"/v1/media/uploads/resumable/{upload_id}/chunk",
            content=chunk_0_data,
            headers=chunk_0_headers,
        )
        assert chunk_0_res.status_code == 202
        assert chunk_0_res.json()["progress_percent"] == 50.0

        # 3. Check Session Status (should show chunk 0 completed, chunk 1 missing)
        status_res = await client.get(f"/v1/media/uploads/resumable/{upload_id}/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["completed_chunks"] == [0]
        assert status_data["missing_chunks"] == [1]

        # 4. Upload Chunk 1
        chunk_1_data = b"1" * 8388608
        chunk_1_hash = hashlib.sha256(chunk_1_data).hexdigest()
        chunk_1_headers = {
            "Content-Range": "bytes 8388608-16777215/16777216",
            "X-Chunk-Index": "1",
            "X-Checksum-SHA256": chunk_1_hash,
            "Content-Type": "application/octet-stream",
        }
        chunk_1_res = await client.put(
            f"/v1/media/uploads/resumable/{upload_id}/chunk",
            content=chunk_1_data,
            headers=chunk_1_headers,
        )
        assert chunk_1_res.status_code == 202
        assert chunk_1_res.json()["progress_percent"] == 100.0

        # 5. Complete Resumable Upload
        complete_res = await client.post(
            f"/v1/media/uploads/resumable/{upload_id}/complete",
            json={},
        )
        assert complete_res.status_code == 200
        media_info = complete_res.json()
        assert media_info["filename"] == "conference_talk.mp4"
        assert media_info["resolution"] == "1920x1080"
        assert media_info["video_codec"] == "h264"
        assert media_info["audio_codec"] == "aac"
        assert media_info["duration_seconds"] == 185.5
        assert media_info["status"] == "ready"

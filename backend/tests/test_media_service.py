import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.media_service import MediaService
from app.utils.error_codes import ErrorCode, MediaAppException, UnsupportedCodecException
from app.utils.file_validators import (
    calculate_sha256,
    detect_mime_type_from_header,
    validate_codecs,
    validate_file_metadata,
)


def _probe_result(payload, *, returncode=0, stderr=b""):
    return SimpleNamespace(
        returncode=returncode,
        stdout=json.dumps(payload).encode(),
        stderr=stderr,
    )


@pytest.mark.asyncio
async def test_probe_media_file_parses_video_audio_and_ignores_cover_art(tmp_path):
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"synthetic")
    payload = {
        "format": {"duration": "12.75", "size": "9000"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "mjpeg",
                "disposition": {"attached_pic": 1},
            },
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "bit_rate": "4500000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": "2",
                "sample_rate": "48000",
                "bit_rate": "192000",
            },
        ],
    }

    with patch("app.services.media_service.subprocess.run", return_value=_probe_result(payload)) as run:
        metadata = await MediaService.probe_media_file(str(media_path))

    assert metadata.duration_seconds == 12.75
    assert metadata.filesize_bytes == 9000
    assert metadata.media_type == "video"
    assert metadata.mime_type == "video/mp4"
    assert metadata.video.codec == "h264"
    assert metadata.video.frame_rate == 29.97
    assert metadata.video.bitrate_kbps == 4500
    assert metadata.audio.codec == "aac"
    assert metadata.audio.sample_rate == 48000
    assert metadata.audio.bitrate_kbps == 192
    command = run.call_args.args[0]
    assert command[:3] == ["ffprobe", "-v", "quiet"]
    assert command[-1] == str(media_path)


@pytest.mark.asyncio
async def test_probe_media_file_parses_audio_only_and_missing_optional_bitrates(tmp_path):
    media_path = tmp_path / "speech.wav"
    media_path.write_bytes(b"wave")
    payload = {
        "format": {"duration": "3.5"},
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "pcm_s16le",
                "channels": 1,
                "sample_rate": 16000,
            }
        ],
    }

    with patch("app.services.media_service.subprocess.run", return_value=_probe_result(payload)):
        metadata = await MediaService.probe_media_file(str(media_path))

    assert metadata.filesize_bytes == 4
    assert metadata.media_type == "audio"
    assert metadata.mime_type == "audio/wav"
    assert metadata.video is None
    assert metadata.audio.bitrate_kbps is None


@pytest.mark.asyncio
async def test_probe_media_file_surfaces_ffprobe_stderr(tmp_path):
    media_path = tmp_path / "broken.mp4"
    media_path.write_bytes(b"broken")

    with patch(
        "app.services.media_service.subprocess.run",
        return_value=_probe_result({}, returncode=1, stderr=b"invalid atom"),
    ):
        with pytest.raises(MediaAppException) as error:
            await MediaService.probe_media_file(str(media_path))

    assert error.value.status_code == 422
    assert error.value.error_code == ErrorCode.FFPROBE_ANALYSIS_FAILED
    assert error.value.details["stderr"] == "invalid atom"


@pytest.mark.asyncio
async def test_probe_media_file_preserves_codec_validation_error(tmp_path):
    media_path = tmp_path / "unsupported.mp4"
    media_path.write_bytes(b"video")
    payload = {
        "format": {"duration": "1", "size": "5"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "wmv3",
                "width": 640,
                "height": 480,
                "avg_frame_rate": "25/1",
            }
        ],
    }

    with patch("app.services.media_service.subprocess.run", return_value=_probe_result(payload)):
        with pytest.raises(UnsupportedCodecException):
            await MediaService.probe_media_file(str(media_path))


@pytest.mark.asyncio
async def test_probe_media_file_uses_fallback_when_ffprobe_is_missing(tmp_path):
    media_path = tmp_path / "offline.mov"
    media_path.write_bytes(b"123456")

    with patch("app.services.media_service.subprocess.run", side_effect=FileNotFoundError):
        metadata = await MediaService.probe_media_file(str(media_path))

    assert metadata.filesize_bytes == 6
    assert metadata.media_type == "video"
    assert metadata.video.codec == "h264"
    assert metadata.audio.codec == "aac"


@pytest.mark.asyncio
async def test_probe_media_file_wraps_invalid_provider_payload(tmp_path):
    media_path = tmp_path / "invalid.wav"
    media_path.write_bytes(b"wave")
    result = SimpleNamespace(returncode=0, stdout=b"{", stderr=b"")

    with patch("app.services.media_service.subprocess.run", return_value=result):
        with pytest.raises(MediaAppException) as error:
            await MediaService.probe_media_file(str(media_path))

    assert error.value.error_code == ErrorCode.FFPROBE_ANALYSIS_FAILED
    assert "unexpected error" in error.value.message.lower()


class _Process:
    def __init__(self, returncode):
        self.returncode = returncode

    async def communicate(self):
        return b"", b""


@pytest.mark.asyncio
async def test_generate_thumbnail_uploads_and_removes_temporary_file(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    thumbnail_path = Path(f"{video_path}.thumb.jpg")

    async def create_process(*command, **kwargs):
        assert command[0] == "ffmpeg"
        assert command[-1] == str(thumbnail_path)
        thumbnail_path.write_bytes(b"jpeg")
        return _Process(0)

    with (
        patch(
            "app.services.media_service.asyncio.create_subprocess_exec",
            side_effect=create_process,
        ),
        patch(
            "app.services.media_service.storage_service.upload_file",
            new=AsyncMock(return_value="gs://bucket/thumb"),
        ) as upload,
    ):
        result = await MediaService.generate_thumbnail(
            str(video_path),
            "raw/source.mp4",
            seek_time_seconds=2.5,
        )

    assert result == "raw/source.mp4.thumb.jpg"
    upload.assert_awaited_once_with(
        file_path=str(thumbnail_path),
        key="raw/source.mp4.thumb.jpg",
        mime_type="image/jpeg",
    )
    assert not thumbnail_path.exists()


@pytest.mark.asyncio
async def test_generate_thumbnail_returns_none_for_failed_process(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    upload = AsyncMock()

    with (
        patch(
            "app.services.media_service.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=_Process(1)),
        ),
        patch("app.services.media_service.storage_service.upload_file", new=upload),
    ):
        result = await MediaService.generate_thumbnail(str(video_path), "raw/source.mp4")

    assert result is None
    upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_thumbnail_cleans_up_when_upload_fails(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    thumbnail_path = Path(f"{video_path}.thumb.jpg")

    async def create_process(*args, **kwargs):
        thumbnail_path.write_bytes(b"jpeg")
        return _Process(0)

    with (
        patch(
            "app.services.media_service.asyncio.create_subprocess_exec",
            side_effect=create_process,
        ),
        patch(
            "app.services.media_service.storage_service.upload_file",
            new=AsyncMock(side_effect=RuntimeError("storage unavailable")),
        ),
    ):
        result = await MediaService.generate_thumbnail(str(video_path), "raw/source.mp4")

    assert result is None
    assert not thumbnail_path.exists()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30000/1001", 29.97),
        ("25/1", 25.0),
        ("29.5", 29.5),
        ("0/0", None),
        ("invalid", None),
    ],
)
def test_calculate_fps_handles_fractional_and_invalid_values(value, expected):
    assert MediaService._calculate_fps(value) == expected


def test_storage_key_discards_directory_and_normalizes_extension():
    key = MediaService.generate_storage_key("../../Conference.MP4", prefix="incoming")

    parts = key.split("/")
    assert parts[0] == "incoming"
    assert len(parts[1]) == 2
    assert len(parts[2]) == 2
    assert len(parts[3]) == 32
    assert parts[4] == "Conference.mp4"
    assert ".." not in key


@pytest.mark.parametrize(
    ("header", "filename", "expected"),
    [
        (b"\x00\x00\x00\x18ftypqt  ", "clip.mov", "video/quicktime"),
        (b"\x00\x00\x00\x18ftypM4A ", "song.m4a", "audio/mp4"),
        (b"\x1a\x45\xdf\xa3" + b"\x00" * 8, "clip.mkv", "video/x-matroska"),
        (b"RIFF1234AVI ", "clip.avi", "video/x-msvideo"),
        (b"\xff\xf3" + b"\x00" * 10, "song.bin", "audio/mpeg"),
        (b"fLaC" + b"\x00" * 8, "song.bin", "audio/flac"),
        (b"OggS" + b"\x00" * 8, "song.bin", "audio/ogg"),
        (b"unknown", "clip.webm", "video/webm"),
        (b"unknown", "no-extension", "application/octet-stream"),
    ],
)
def test_detect_mime_type_covers_magic_and_fallbacks(header, filename, expected):
    assert detect_mime_type_from_header(header, filename) == expected


def test_validation_accepts_limits_and_case_insensitive_codecs(tmp_path):
    validate_file_metadata("clip.mp4", 100, "video/mp4", 100)
    validate_codecs("H264", "AAC", is_video=True)

    payload = b"deterministic media fixture"
    fixture = tmp_path / "fixture.bin"
    fixture.write_bytes(payload)
    assert calculate_sha256(str(fixture), chunk_size=3) == hashlib.sha256(payload).hexdigest()

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.core.config import settings
from app.services.replicate_service import replicate_lipsync
from app.utils.error_codes import ErrorCode, MediaAppException
from app.utils.replicate_utils import replicate_utils


class _Response:
    def __init__(self, status_code=200, content=b"rendered"):
        self.status_code = status_code
        self.content = content


class _FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.requested_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):
        self.requested_urls.append(url)
        return self.response


@pytest.mark.asyncio
async def test_render_segment_lipsync_builds_liveportrait_request_and_downloads_result(tmp_path, monkeypatch):
    monkeypatch.setattr(replicate_lipsync, "api_token", "real-replicate-token")
    monkeypatch.setattr("app.services.replicate_service.uuid.uuid4", lambda: uuid.UUID(int=1))

    video_slice = tmp_path / "slice.mp4"
    audio_segment = tmp_path / "audio.wav"
    output_path = tmp_path / "renders" / "segment.mp4"
    video_slice.write_bytes(b"video")
    audio_segment.write_bytes(b"audio")

    recorded = []

    def fake_run(model, input):
        recorded.append((model, input))
        return "https://replicate.delivery/rendered.mp4"

    fake_client = _FakeAsyncClient(_Response(200, b"rendered-bytes"))
    upload_file = AsyncMock()

    with (
        patch("app.services.replicate_service.asyncio.to_thread", new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs))),
        patch("app.services.replicate_service.replicate.run", side_effect=fake_run),
        patch("app.services.replicate_service.httpx.AsyncClient", return_value=fake_client),
        patch("app.services.replicate_service.storage_service") as storage,
    ):
        storage.upload_file = upload_file
        storage.generate_presigned_download_url.side_effect = [
            "https://presigned.test/audio.wav",
            "https://presigned.test/video.mp4",
        ]
        result = await replicate_lipsync.render_segment_lipsync(
            video_slice_path=str(video_slice),
            audio_segment_path=str(audio_segment),
            duration_sec=3.4567,
            output_rendered_path=str(output_path),
            model_preference="liveportrait",
        )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"rendered-bytes"
    assert storage.upload_file.await_args_list == [
        call(str(audio_segment), "tmp_lipsync/00000000000000000000000000000001_audio.wav", mime_type="audio/wav"),
        call(str(video_slice), "tmp_lipsync/00000000000000000000000000000001_video.mp4", mime_type="video/mp4"),
    ]
    assert storage.generate_presigned_download_url.call_args_list[0].args == ("tmp_lipsync/00000000000000000000000000000001_audio.wav",)
    assert storage.generate_presigned_download_url.call_args_list[1].args == ("tmp_lipsync/00000000000000000000000000000001_video.mp4",)
    assert recorded == [
        (
            replicate_lipsync.liveportrait_model,
            replicate_utils.build_liveportrait_input(
                image_or_video_url="https://presigned.test/video.mp4",
                audio_url="https://presigned.test/audio.wav",
                duration_sec=3.4567,
                face_expand_ratio=settings.LIPSYNC_FACE_EXPAND_RATIO,
            ),
        )
    ]
    assert fake_client.requested_urls == ["https://replicate.delivery/rendered.mp4"]


@pytest.mark.asyncio
async def test_render_segment_lipsync_falls_back_to_wav2lip_when_primary_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(replicate_lipsync, "api_token", "real-replicate-token")
    monkeypatch.setattr("app.services.replicate_service.uuid.uuid4", lambda: uuid.UUID(int=2))

    video_slice = tmp_path / "slice.mp4"
    audio_segment = tmp_path / "audio.wav"
    output_path = tmp_path / "renders" / "fallback.mp4"
    video_slice.write_bytes(b"video")
    audio_segment.write_bytes(b"audio")

    recorded = []

    def fake_run(model, input):
        recorded.append((model, input))
        if len(recorded) == 1:
            raise RuntimeError("primary model unavailable")
        return "https://replicate.delivery/fallback.mp4"

    fake_client = _FakeAsyncClient(_Response(200, b"fallback-bytes"))

    with (
        patch("app.services.replicate_service.asyncio.to_thread", new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs))),
        patch("app.services.replicate_service.replicate.run", side_effect=fake_run),
        patch("app.services.replicate_service.httpx.AsyncClient", return_value=fake_client),
        patch("app.services.replicate_service.storage_service") as storage,
    ):
        storage.upload_file = AsyncMock()
        storage.generate_presigned_download_url.side_effect = [
            "https://presigned.test/audio.wav",
            "https://presigned.test/video.mp4",
        ]
        result = await replicate_lipsync.render_segment_lipsync(
            video_slice_path=str(video_slice),
            audio_segment_path=str(audio_segment),
            duration_sec=1.0,
            output_rendered_path=str(output_path),
            model_preference="liveportrait",
        )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"fallback-bytes"
    assert [model for model, _ in recorded] == [
        replicate_lipsync.liveportrait_model,
        replicate_lipsync.wav2lip_model,
    ]
    assert recorded[1][1] == replicate_utils.build_wav2lip_input(
        face_video_url="https://presigned.test/video.mp4",
        audio_url="https://presigned.test/audio.wav",
        smooth=True,
    )


@pytest.mark.asyncio
async def test_render_segment_lipsync_rejects_unconfigured_token_without_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(replicate_lipsync, "api_token", "test_replicate_token_placeholder")

    video_slice = tmp_path / "slice.mp4"
    audio_segment = tmp_path / "audio.wav"
    output_path = tmp_path / "renders" / "blocked.mp4"
    video_slice.write_bytes(b"video")
    audio_segment.write_bytes(b"audio")

    storage_upload = AsyncMock()

    with patch("app.services.replicate_service.storage_service") as storage:
        storage.upload_file = storage_upload
        with pytest.raises(MediaAppException) as error:
            await replicate_lipsync.render_segment_lipsync(
                video_slice_path=str(video_slice),
                audio_segment_path=str(audio_segment),
                duration_sec=2.0,
                output_rendered_path=str(output_path),
            )

    assert error.value.status_code == 503
    assert error.value.error_code == ErrorCode.LIPSYNC_RENDER_FAILED
    assert "valid REPLICATE_API_TOKEN" in error.value.message
    storage_upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_render_segment_lipsync_raises_when_rendered_download_is_not_successful(tmp_path, monkeypatch):
    monkeypatch.setattr(replicate_lipsync, "api_token", "real-replicate-token")
    monkeypatch.setattr("app.services.replicate_service.uuid.uuid4", lambda: uuid.UUID(int=3))

    video_slice = tmp_path / "slice.mp4"
    audio_segment = tmp_path / "audio.wav"
    output_path = tmp_path / "renders" / "missing-response.mp4"
    video_slice.write_bytes(b"video")
    audio_segment.write_bytes(b"audio")

    def fake_run(model, input):
        return "https://replicate.delivery/rendered.mp4"

    fake_client = _FakeAsyncClient(_Response(502, b"upstream failed"))

    with (
        patch("app.services.replicate_service.asyncio.to_thread", new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs))),
        patch("app.services.replicate_service.replicate.run", side_effect=fake_run),
        patch("app.services.replicate_service.httpx.AsyncClient", return_value=fake_client),
        patch("app.services.replicate_service.storage_service") as storage,
    ):
        storage.upload_file = AsyncMock()
        storage.generate_presigned_download_url.side_effect = [
            "https://presigned.test/audio.wav",
            "https://presigned.test/video.mp4",
        ]
        with pytest.raises(MediaAppException) as error:
            await replicate_lipsync.render_segment_lipsync(
                video_slice_path=str(video_slice),
                audio_segment_path=str(audio_segment),
                duration_sec=2.0,
                output_rendered_path=str(output_path),
            )

    assert error.value.status_code == 500
    assert error.value.error_code == ErrorCode.LIPSYNC_RENDER_FAILED
    assert "Failed to retrieve rendered video stream" in error.value.message
    assert not output_path.exists()

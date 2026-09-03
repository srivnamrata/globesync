import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.auth import get_request_context
from app.core.config import settings
from app.core.database import get_db
from app.routers.upload import router


WORKSPACE_ID = uuid.uuid4()
MEDIA_ID = uuid.uuid4()


api_app = FastAPI()
api_app.include_router(router, prefix="/v1")


async def dummy_request_context():
    return SimpleNamespace(workspace_id=WORKSPACE_ID, user_id=uuid.uuid4(), membership_role="owner")


async def dummy_get_db():
    yield AsyncMock(name="db_session")


api_app.dependency_overrides[get_request_context] = dummy_request_context
api_app.dependency_overrides[get_db] = dummy_get_db


@pytest.mark.asyncio
async def test_media_audio_returns_cached_signed_url():
    media = SimpleNamespace(
        id=MEDIA_ID,
        workspace_id=WORKSPACE_ID,
        project_id=None,
        storage_path="raw/source.mp4",
        storage_bucket="media-bucket",
        original_filename="source.mp4",
        duration_seconds=12.5,
    )
    db = AsyncMock(name="db_session")
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: media)

    async def cached_get_db():
        yield db

    with patch("app.routers.upload.storage_service") as storage, patch("app.routers.upload.audio_extractor") as extractor:
        storage.object_exists.return_value = True
        storage.generate_presigned_download_url.return_value = "https://storage.example/audio.mp3"
        api_app.dependency_overrides[get_db] = cached_get_db

        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/v1/media/{MEDIA_ID}/audio")

    assert response.status_code == 200
    assert response.json() == {
        "media_id": str(MEDIA_ID),
        "audio_url": "https://storage.example/audio.mp3",
        "format": "mp3",
        "duration_seconds": 12.5,
    }
    extractor.extract_audio_for_stt.assert_not_called()
    storage.generate_presigned_download_url.assert_called_once_with(
        f"waveforms/{MEDIA_ID}.mp3",
        expires_in_seconds=7200,
    )
    api_app.dependency_overrides[get_db] = dummy_get_db


@pytest.mark.asyncio
async def test_media_detail_returns_authorized_playback_url():
    media = SimpleNamespace(
        id=MEDIA_ID,
        workspace_id=WORKSPACE_ID,
        project_id=None,
        storage_path="raw/source.mp4",
        thumbnail_path=None,
        original_filename="source.mp4",
        media_type="video",
        mime_type="video/mp4",
        filesize_bytes=2048,
        duration_seconds=12.5,
        video_codec="h264",
        audio_codec="aac",
        frame_rate=30.0,
        resolution_width=1920,
        resolution_height=1080,
        status="ready",
        created_at=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
    )
    db = AsyncMock(name="db_session")
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: media)

    async def media_get_db():
        yield db

    with patch("app.routers.upload.storage_service") as storage:
        storage.generate_presigned_download_url.return_value = "https://storage.example/source.mp4"
        api_app.dependency_overrides[get_db] = media_get_db

        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/v1/media/{MEDIA_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["media_id"] == str(MEDIA_ID)
    assert payload["media_url"] == "https://storage.example/source.mp4"
    storage.generate_presigned_download_url.assert_called_once_with("raw/source.mp4")
    api_app.dependency_overrides[get_db] = dummy_get_db


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["source.webm", "source.mp3"])
async def test_media_audio_extracts_and_caches_on_storage_miss(filename):
    media = SimpleNamespace(
        id=MEDIA_ID,
        workspace_id=WORKSPACE_ID,
        project_id=None,
        storage_path=f"raw/{filename}",
        storage_bucket="media-bucket",
        original_filename=filename,
        duration_seconds=8.0,
    )
    db = AsyncMock(name="db_session")
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: media)

    async def extracting_get_db():
        yield db

    with patch("app.routers.upload.storage_service") as storage, patch("app.routers.upload.audio_extractor") as extractor:
        storage.object_exists.return_value = False
        storage.download_file = AsyncMock()
        storage.upload_file = AsyncMock()
        storage.generate_presigned_download_url.return_value = "https://storage.example/waveform.mp3"
        extractor.extract_audio_for_stt = AsyncMock()
        extractor.convert_to_web_audio = AsyncMock()
        api_app.dependency_overrides[get_db] = extracting_get_db

        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/v1/media/{MEDIA_ID}/audio")

    assert response.status_code == 200
    assert response.json()["audio_url"] == "https://storage.example/waveform.mp3"
    source_path = os.path.join(settings.TEMP_UPLOAD_DIR, f"waveform_{MEDIA_ID}{os.path.splitext(filename)[1]}")
    audio_path = os.path.join(settings.PROCESSED_MEDIA_DIR, f"waveform_{MEDIA_ID}.wav")
    mp3_path = os.path.join(settings.PROCESSED_MEDIA_DIR, f"waveform_{MEDIA_ID}.mp3")
    storage.download_file.assert_awaited_once_with(
        f"raw/{filename}",
        source_path,
        bucket_name="media-bucket",
    )
    extractor.extract_audio_for_stt.assert_awaited_once_with(
        source_path,
        audio_path,
    )
    extractor.convert_to_web_audio.assert_awaited_once_with(
        audio_path,
        mp3_path,
    )
    storage.upload_file.assert_awaited_once_with(
        mp3_path,
        f"waveforms/{MEDIA_ID}.mp3",
        mime_type="audio/mpeg",
    )
    api_app.dependency_overrides[get_db] = dummy_get_db

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.models.media import MediaFile, UploadChunk, UploadSession
from app.routers.upload import (
    abort_resumable_upload,
    complete_resumable_upload,
    get_media_file,
    get_resumable_upload_status,
    init_signed_resumable_upload,
    upload_resumable_chunk,
)
from app.schemas.media_schema import InitSignedUploadRequest
from app.utils.error_codes import (
    ChecksumMismatchException,
    ErrorCode,
    MediaAppException,
    UploadSessionExpiredException,
)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _QueueDatabase:
    def __init__(self, *results):
        self.results = list(results)
        self.added = []
        self.commit_count = 0

    async def execute(self, statement):
        return _Result(self.results.pop(0) if self.results else None)

    def add(self, value):
        self.added.append(value)
        if getattr(value, "id", None) is None:
            value.id = uuid.uuid4()

    async def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, value):
        if getattr(value, "created_at", None) is None:
            value.created_at = datetime.now(timezone.utc)


def _context(workspace_id=None, role="editor"):
    return SimpleNamespace(
        workspace_id=workspace_id or uuid.uuid4(),
        user_id=uuid.uuid4(),
        membership_role=role,
    )


def _request(body=b"", headers=None):
    encoded_headers = [
        (name.lower().encode(), value.encode()) for name, value in (headers or {}).items()
    ]
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/",
            "headers": encoded_headers,
            "query_string": b"",
        },
        receive,
    )


def _session(workspace_id=None, **overrides):
    values = {
        "id": uuid.uuid4(),
        "workspace_id": workspace_id or uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "filename": "clip.mp4",
        "filesize_bytes": 8,
        "mime_type": "video/mp4",
        "total_chunks": 2,
        "chunk_size_bytes": 4,
        "bytes_received": 0,
        "storage_provider": "gcs",
        "storage_bucket": "media",
        "storage_key": "raw/clip.mp4",
        "s3_upload_id": "upload-1",
        "status": "in_progress",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "chunks": [],
        "media_file_id": None,
        "final_checksum_sha256": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _media(workspace_id=None, **overrides):
    values = {
        "id": uuid.uuid4(),
        "project_id": None,
        "workspace_id": workspace_id or uuid.uuid4(),
        "storage_path": "raw/clip.mp4",
        "thumbnail_path": "raw/clip.mp4.thumb.jpg",
        "original_filename": "clip.mp4",
        "media_type": "video",
        "mime_type": "video/mp4",
        "filesize_bytes": 8,
        "duration_seconds": 2.5,
        "video_codec": "h264",
        "audio_codec": "aac",
        "frame_rate": 25,
        "resolution_width": 640,
        "resolution_height": 360,
        "status": "ready",
        "created_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_signed_resumable_initialization_uses_request_origin_and_persists_scope():
    context = _context()
    database = _QueueDatabase()
    request = _request(headers={"origin": "https://studio.example"})
    payload = InitSignedUploadRequest(
        filename="clip.mp4",
        filesize_bytes=1024,
        mime_type="video/mp4",
    )

    with (
        patch(
            "app.routers.upload.media_service.generate_storage_key",
            return_value="raw/generated.mp4",
        ),
        patch(
            "app.routers.upload.storage_service.create_resumable_upload_url",
            return_value="https://storage.example/session",
        ) as create_url,
    ):
        response = await init_signed_resumable_upload(payload, request, context, database)

    assert response.gcs_resumable_url == "https://storage.example/session"
    assert response.upload_mode == "gcs_resumable"
    saved = database.added[0]
    assert saved.workspace_id == context.workspace_id
    assert saved.user_id == context.user_id
    assert saved.s3_upload_id == "gcs-resumable"
    create_url.assert_called_once_with(
        key="raw/generated.mp4",
        mime_type="video/mp4",
        origin="https://studio.example",
        size_bytes=1024,
    )


@pytest.mark.asyncio
async def test_upload_chunk_rejects_missing_expired_empty_and_bad_checksum():
    upload_id = uuid.uuid4()
    context = _context()

    with pytest.raises(MediaAppException) as missing:
        await upload_resumable_chunk(
            upload_id,
            "bytes 0-3/8",
            0,
            None,
            _request(b"data"),
            context,
            _QueueDatabase(None),
        )
    assert missing.value.error_code == ErrorCode.UPLOAD_SESSION_NOT_FOUND

    expired = _session(
        workspace_id=context.workspace_id,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with pytest.raises(UploadSessionExpiredException):
        await upload_resumable_chunk(
            expired.id,
            "bytes 0-3/8",
            0,
            None,
            _request(b"data"),
            context,
            _QueueDatabase(expired),
        )

    active = _session(workspace_id=context.workspace_id)
    with pytest.raises(MediaAppException) as empty:
        await upload_resumable_chunk(
            active.id,
            "bytes 0-0/8",
            0,
            None,
            _request(),
            context,
            _QueueDatabase(active),
        )
    assert empty.value.error_code == ErrorCode.CHUNK_TOO_SMALL

    with pytest.raises(ChecksumMismatchException):
        await upload_resumable_chunk(
            active.id,
            "bytes 0-3/8",
            0,
            "0" * 64,
            _request(b"data"),
            context,
            _QueueDatabase(active),
        )


@pytest.mark.asyncio
async def test_upload_chunk_creates_record_with_range_fallback():
    context = _context()
    session = _session(workspace_id=context.workspace_id)
    database = _QueueDatabase(session, None)

    with patch("app.routers.upload.storage_service.upload_part", return_value="etag") as upload:
        response = await upload_resumable_chunk(
            session.id,
            "invalid",
            1,
            hashlib.sha256(b"data").hexdigest().upper(),
            _request(b"data"),
            context,
            database,
        )

    assert response.bytes_received == 4
    assert response.progress_percent == 50
    assert response.is_completed is False
    chunk = database.added[0]
    assert isinstance(chunk, UploadChunk)
    assert (chunk.byte_start, chunk.byte_end) == (4, 7)
    upload.assert_called_once_with(
        key=session.storage_key,
        upload_id=session.s3_upload_id,
        part_number=2,
        data=b"data",
    )


@pytest.mark.asyncio
async def test_duplicate_chunk_updates_metadata_without_double_counting():
    context = _context()
    existing = SimpleNamespace(etag="old", checksum_sha256="old", size_bytes=4)
    session = _session(workspace_id=context.workspace_id, bytes_received=4)
    database = _QueueDatabase(session, existing)

    with patch("app.routers.upload.storage_service.upload_part", return_value="new-etag"):
        response = await upload_resumable_chunk(
            session.id,
            "bytes 0-3/8",
            0,
            None,
            _request(b"next"),
            context,
            database,
        )

    assert response.bytes_received == 4
    assert database.added == []
    assert existing.etag == "new-etag"
    assert existing.checksum_sha256 == hashlib.sha256(b"next").hexdigest()


@pytest.mark.asyncio
async def test_upload_status_reports_ordered_completed_and_missing_chunks():
    context = _context()
    session = _session(
        workspace_id=context.workspace_id,
        bytes_received=5,
        filesize_bytes=10,
        total_chunks=4,
        chunks=[SimpleNamespace(chunk_index=2), SimpleNamespace(chunk_index=0)],
    )

    response = await get_resumable_upload_status(
        session.id,
        context,
        _QueueDatabase(session),
    )

    assert response.completed_chunks == [0, 2]
    assert response.missing_chunks == [1, 3]
    assert response.progress_percent == 50


@pytest.mark.asyncio
async def test_complete_upload_rejects_missing_chunks_before_storage_side_effects():
    context = _context()
    session = _session(
        workspace_id=context.workspace_id,
        chunks=[SimpleNamespace(chunk_index=0, etag="etag-1")],
    )

    with patch("app.routers.upload.storage_service.complete_multipart_upload") as complete:
        with pytest.raises(MediaAppException) as error:
            await complete_resumable_upload(
                session.id,
                None,
                None,
                context,
                _QueueDatabase(session),
            )

    assert error.value.error_code == ErrorCode.CHUNK_OUT_OF_ORDER
    assert error.value.details["missing_chunks"] == [1]
    complete.assert_not_called()


@pytest.mark.asyncio
async def test_complete_upload_is_idempotent_for_existing_media():
    context = _context()
    media = _media(workspace_id=context.workspace_id)
    session = _session(
        workspace_id=context.workspace_id,
        status="completed",
        media_file_id=media.id,
    )

    with patch(
        "app.routers.upload.storage_service.generate_presigned_download_url",
        side_effect=lambda key: f"https://storage.example/{key}",
    ):
        response = await complete_resumable_upload(
            session.id,
            None,
            None,
            context,
            _QueueDatabase(session, media),
        )

    assert response.media_id == media.id
    assert response.media_url.endswith(media.storage_path)


@pytest.mark.asyncio
async def test_abort_upload_is_idempotent_and_only_mutates_existing_session():
    context = _context()
    session = _session(workspace_id=context.workspace_id)

    with patch("app.routers.upload.storage_service.abort_multipart_upload") as abort:
        database = _QueueDatabase(session)
        await abort_resumable_upload(session.id, context, database)

        missing_database = _QueueDatabase(None)
        await abort_resumable_upload(uuid.uuid4(), context, missing_database)

    assert session.status == "aborted"
    assert database.commit_count == 1
    assert missing_database.commit_count == 0
    abort.assert_called_once_with(session.storage_key, session.s3_upload_id)


@pytest.mark.asyncio
async def test_media_detail_returns_not_found_without_signing_url():
    context = _context()

    with patch("app.routers.upload.storage_service.generate_presigned_download_url") as sign:
        with pytest.raises(HTTPException) as error:
            await get_media_file(uuid.uuid4(), context, _QueueDatabase(None))

    assert error.value.status_code == 404
    sign.assert_not_called()


@pytest.mark.asyncio
async def test_media_detail_formats_optional_fields_and_signed_urls():
    context = _context()
    media = _media(
        workspace_id=context.workspace_id,
        thumbnail_path=None,
        frame_rate=None,
        resolution_width=None,
        resolution_height=None,
    )

    with patch(
        "app.routers.upload.storage_service.generate_presigned_download_url",
        return_value="https://storage.example/media",
    ) as sign:
        response = await get_media_file(media.id, context, _QueueDatabase(media))

    assert response.resolution is None
    assert response.frame_rate is None
    assert response.thumbnail_url is None
    assert response.media_url == "https://storage.example/media"
    sign.assert_called_once_with(media.storage_path)

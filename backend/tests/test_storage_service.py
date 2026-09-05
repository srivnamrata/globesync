from __future__ import annotations

from datetime import timedelta

import pytest

from app.services.storage_service import StorageService
from app.utils.error_codes import ErrorCode, MediaAppException


class FakeCredentials:
    def __init__(self, *, token="fake-token", service_account_email="signed@example.com", expired=False):
        self.token = token
        self.service_account_email = service_account_email
        self.expired = expired
        self.refresh_calls = 0

    def refresh(self, request):
        self.refresh_calls += 1


class FakeBlob:
    def __init__(self, name):
        self.name = name
        self.content_type = None
        self.metadata = None
        self.etag = None
        self.exists_value = False
        self.upload_from_string_calls = []
        self.upload_from_filename_calls = []
        self.download_to_filename_calls = []
        self.generate_signed_url_calls = []
        self.create_resumable_upload_session_calls = []
        self.compose_calls = []
        self.deleted = False
        self.patched = False
        self.download_text = ""
        self.generate_signed_url_result = f"https://storage.example/{name}"
        self.resumable_session_result = f"https://storage.example/resumable/{name}"
        self.raise_on_upload_from_string = None
        self.raise_on_upload_from_filename = None
        self.raise_on_download_to_filename = None
        self.raise_on_download_as_text = None
        self.raise_on_generate_signed_url = None
        self.raise_on_create_resumable_upload_session = None

    def upload_from_string(self, data, content_type=None):
        if self.raise_on_upload_from_string:
            raise self.raise_on_upload_from_string
        self.upload_from_string_calls.append((data, content_type))
        self.content_type = content_type
        self.etag = self.etag or f"etag-{self.name}"

    def upload_from_filename(self, file_path, content_type=None):
        if self.raise_on_upload_from_filename:
            raise self.raise_on_upload_from_filename
        self.upload_from_filename_calls.append((file_path, content_type))
        self.content_type = content_type

    def download_to_filename(self, target_local_path):
        if self.raise_on_download_to_filename:
            raise self.raise_on_download_to_filename
        self.download_to_filename_calls.append(target_local_path)

    def download_as_text(self):
        if self.raise_on_download_as_text:
            raise self.raise_on_download_as_text
        return self.download_text

    def generate_signed_url(self, **kwargs):
        if self.raise_on_generate_signed_url:
            raise self.raise_on_generate_signed_url
        self.generate_signed_url_calls.append(kwargs)
        return self.generate_signed_url_result

    def create_resumable_upload_session(self, **kwargs):
        if self.raise_on_create_resumable_upload_session:
            raise self.raise_on_create_resumable_upload_session
        self.create_resumable_upload_session_calls.append(kwargs)
        return self.resumable_session_result

    def exists(self):
        return self.exists_value

    def delete(self):
        self.deleted = True

    def compose(self, sources):
        self.compose_calls.append([source.name for source in sources])
        return self

    def patch(self):
        self.patched = True


class FakeBucket:
    def __init__(self):
        self.blobs = {}
        self.copy_blob_calls = []
        self.list_blobs_prefixes = []

    def blob(self, name):
        if name not in self.blobs:
            self.blobs[name] = FakeBlob(name)
        return self.blobs[name]

    def list_blobs(self, prefix=None):
        self.list_blobs_prefixes.append(prefix)
        return [blob for name, blob in self.blobs.items() if prefix is None or name.startswith(prefix)]

    def copy_blob(self, source, bucket, destination_name):
        self.copy_blob_calls.append((source.name, destination_name))
        dest = self.blob(destination_name)
        dest.content_type = source.content_type
        return dest


def _service(*, credentials=None):
    service = StorageService()
    bucket = FakeBucket()
    service._bucket = lambda bucket_name=None: bucket
    service._credentials = credentials
    return service, bucket


@pytest.mark.asyncio
async def test_upload_file_and_bytes_call_bucket_blobs():
    service, bucket = _service()
    file_blob = bucket.blob("uploads/video.mp4")
    bytes_blob = bucket.blob("uploads/thumb.jpg")

    upload_path = "backend\\tests\\fixture-media.bin"

    file_result = await service.upload_file(
        file_path=upload_path,
        key="uploads/video.mp4",
        mime_type="video/mp4",
        metadata={"kind": "primary"},
    )
    bytes_result = await service.upload_bytes(
        data=b"thumbnail-bytes",
        key="uploads/thumb.jpg",
        mime_type="image/jpeg",
    )

    assert file_result == "gs://translation-app-media-prod/uploads/video.mp4"
    assert bytes_result == "gs://translation-app-media-prod/uploads/thumb.jpg"
    assert file_blob.upload_from_filename_calls == [(upload_path, "video/mp4")]
    assert file_blob.metadata == {"kind": "primary"}
    assert bytes_blob.upload_from_string_calls == [(b"thumbnail-bytes", "image/jpeg")]


@pytest.mark.asyncio
async def test_download_delete_and_exists_use_bucket_objects_and_map_missing_downloads(
    monkeypatch,
    tmp_path,
):
    service, bucket = _service()
    download_blob = bucket.blob("downloads/final.mp4")
    download_blob.exists_value = True
    missing_blob = bucket.blob("downloads/missing.mp4")
    missing_blob.raise_on_download_to_filename = RuntimeError("No such object: missing.mp4")
    delete_blob = bucket.blob("deletions/existing.txt")
    delete_blob.exists_value = True
    absent_blob = bucket.blob("deletions/absent.txt")
    absent_blob.exists_value = False

    makedirs_calls = []
    monkeypatch.setattr("app.services.storage_service.os.makedirs", lambda path, exist_ok=True: makedirs_calls.append((path, exist_ok)))

    download_path = tmp_path / "downloads" / "final.mp4"
    missing_path = tmp_path / "downloads" / "missing.mp4"
    await service.download_file(
        key="downloads/final.mp4",
        target_local_path=str(download_path),
    )
    assert download_blob.download_to_filename_calls == [str(download_path)]

    with pytest.raises(MediaAppException) as exc_info:
        await service.download_file(
            key="downloads/missing.mp4",
            target_local_path=str(missing_path),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == ErrorCode.STORAGE_UPLOAD_FAILED
    assert exc_info.value.details["key"] == "downloads/missing.mp4"
    assert makedirs_calls[0] == (str(download_path.parent), True)

    await service.delete_object("deletions/existing.txt")
    await service.delete_object("deletions/absent.txt")
    assert delete_blob.deleted is True
    assert absent_blob.deleted is False
    assert service.object_exists("downloads/final.mp4") is True
    assert service.object_exists("deletions/absent.txt") is False


@pytest.mark.asyncio
async def test_signed_upload_and_download_urls_use_service_account_override_and_sanitize_filenames(monkeypatch):
    credentials = FakeCredentials(token="signed-token", service_account_email="fallback@example.iam.gserviceaccount.com")
    service, bucket = _service(credentials=credentials)
    upload_blob = bucket.blob("uploads/signed-video.mp4")
    download_blob = bucket.blob("downloads/signed-video.mp4")
    monkeypatch.setattr("app.services.storage_service.settings.GCS_SIGNING_SERVICE_ACCOUNT", "override@example.iam.gserviceaccount.com")

    upload_url = service.generate_signed_upload_url(
        key="uploads/signed-video.mp4",
        mime_type="video/mp4",
        expires_in_seconds=600,
    )
    download_url = service.generate_presigned_download_url(
        key="downloads/signed-video.mp4",
        expires_in_seconds=900,
        download_filename='nested\\folder\\final"report.mp4',
    )

    assert upload_url == upload_blob.generate_signed_url_result
    assert download_url == download_blob.generate_signed_url_result
    assert upload_blob.generate_signed_url_calls[0]["method"] == "PUT"
    assert upload_blob.generate_signed_url_calls[0]["content_type"] == "video/mp4"
    assert upload_blob.generate_signed_url_calls[0]["service_account_email"] == "override@example.iam.gserviceaccount.com"
    assert upload_blob.generate_signed_url_calls[0]["access_token"] == "signed-token"
    assert upload_blob.generate_signed_url_calls[0]["expiration"] == timedelta(seconds=600)
    assert download_blob.generate_signed_url_calls[0]["method"] == "GET"
    assert download_blob.generate_signed_url_calls[0]["response_disposition"] == 'attachment; filename="finalreport.mp4"'
    assert download_blob.generate_signed_url_calls[0]["service_account_email"] == "override@example.iam.gserviceaccount.com"
    assert download_blob.generate_signed_url_calls[0]["access_token"] == "signed-token"
    assert download_blob.generate_signed_url_calls[0]["expiration"] == timedelta(seconds=900)


@pytest.mark.asyncio
async def test_create_resumable_upload_url_validates_inputs_and_forwards_options():
    service, bucket = _service()
    resumable_blob = bucket.blob("uploads/video.mp4")

    result = service.create_resumable_upload_url(
        key="uploads/video.mp4",
        mime_type="video/mp4",
        origin="https://studio.example",
        size_bytes=1024,
    )

    assert result == resumable_blob.resumable_session_result
    assert resumable_blob.create_resumable_upload_session_calls == [
        {
            "content_type": "video/mp4",
            "size": 1024,
            "origin": "https://studio.example",
        }
    ]

    for key, size_bytes, message in [
        ("", 1024, "key must be a non-empty string."),
        ("uploads/video.mp4", 0, "size_bytes must be a positive integer."),
    ]:
        with pytest.raises(MediaAppException) as exc_info:
            service.create_resumable_upload_url(key=key, mime_type="video/mp4", size_bytes=size_bytes)

        assert exc_info.value.error_code == ErrorCode.STORAGE_UPLOAD_FAILED
        assert message in exc_info.value.message


@pytest.mark.asyncio
async def test_multipart_upload_orders_parts_and_cleans_up_session_objects():
    service, bucket = _service()
    upload_id = service.initiate_multipart_upload(
        key="exports/final.mp4",
        mime_type="video/mp4",
        metadata={"project": "alpha"},
    )

    uploaded_etags = {}
    for part_number in [3, 1, 2]:
        uploaded_etags[part_number] = service.upload_part(
            key="exports/final.mp4",
            upload_id=upload_id,
            part_number=part_number,
            data=f"part-{part_number}".encode(),
        )

    parts = [
        {"PartNumber": 2, "ETag": uploaded_etags[2]},
        {"PartNumber": 3, "ETag": uploaded_etags[3]},
        {"PartNumber": 1, "ETag": uploaded_etags[1]},
    ]
    result = service.complete_multipart_upload(
        key="exports/final.mp4",
        upload_id=upload_id,
        parts=parts,
    )

    final_blob = bucket.blob("exports/final.mp4")
    session_key = f"_multipart/{upload_id}/session.json"
    assert result == f"gs://{service.bucket_name}/exports/final.mp4"
    assert final_blob.compose_calls == [[
        f"_multipart/{upload_id}/part-00001",
        f"_multipart/{upload_id}/part-00002",
        f"_multipart/{upload_id}/part-00003",
    ]]
    assert bucket.blobs[session_key].deleted is True
    assert bucket.blobs[f"_multipart/{upload_id}/part-00001"].deleted is True
    assert bucket.blobs[f"_multipart/{upload_id}/part-00002"].deleted is True
    assert bucket.blobs[f"_multipart/{upload_id}/part-00003"].deleted is True
    assert upload_id not in service._multipart_meta


@pytest.mark.asyncio
async def test_multipart_completion_errors_surface_missing_sessions_and_empty_part_lists():
    service, bucket = _service()

    with pytest.raises(MediaAppException) as missing_session:
        service.complete_multipart_upload(
            key="exports/final.mp4",
            upload_id="missing-upload",
            parts=[{"PartNumber": 1, "ETag": "etag-1"}],
        )

    assert missing_session.value.status_code == 404
    assert missing_session.value.error_code == ErrorCode.STORAGE_UPLOAD_FAILED
    assert missing_session.value.message == "Multipart upload session not found."

    upload_id = service.initiate_multipart_upload(
        key="exports/final.mp4",
        mime_type="video/mp4",
    )

    with pytest.raises(MediaAppException) as empty_parts:
        service.complete_multipart_upload(
            key="exports/final.mp4",
            upload_id=upload_id,
            parts=[],
        )

    assert empty_parts.value.status_code == 500
    assert empty_parts.value.error_code == ErrorCode.STORAGE_UPLOAD_FAILED
    assert "No parts provided" in empty_parts.value.details["error"]

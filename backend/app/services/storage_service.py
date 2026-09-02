"""Native Google Cloud Storage access via Application Default Credentials.

Cloud Run should rely on the attached service identity. Do not set
GOOGLE_APPLICATION_CREDENTIALS in production.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.utils.error_codes import ErrorCode, MediaAppException


class StorageService:
    """GCS object storage with compose-based multipart and IAM-signed URLs."""

    def __init__(self) -> None:
        self.bucket_name = settings.GCS_BUCKET_NAME or "translation-app-media-prod"
        self.exports_bucket = settings.GCS_EXPORTS_BUCKET or "translation-app-media-exports"
        self._client = None
        self._credentials = None
        self._multipart_meta: Dict[str, Dict[str, Any]] = {}

    def _get_client(self):
        if self._client is None:
            try:
                import google.auth
                from google.cloud import storage
            except ImportError as exc:
                raise MediaAppException(
                    status_code=500,
                    error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                    message="google-cloud-storage is not installed.",
                    details={"error": str(exc)},
                ) from exc

            if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(
                settings.GOOGLE_APPLICATION_CREDENTIALS
            ):
                credentials, project = google.auth.load_credentials_from_file(
                    settings.GOOGLE_APPLICATION_CREDENTIALS,
                    scopes=["https://www.googleapis.com/auth/devstorage.full_control"],
                )
                self._credentials = credentials
                self._client = storage.Client(
                    project=settings.GOOGLE_CLOUD_PROJECT or project,
                    credentials=credentials,
                )
            else:
                credentials, project = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                self._credentials = credentials
                self._client = storage.Client(
                    project=settings.GOOGLE_CLOUD_PROJECT or project,
                    credentials=credentials,
                )
        return self._client

    def _bucket(self, bucket_name: Optional[str] = None):
        return self._get_client().bucket(bucket_name or self.bucket_name)

    def _refresh_credentials(self):
        import google.auth.transport.requests

        credentials = self._credentials
        if credentials is None:
            self._get_client()
            credentials = self._credentials
        if credentials and (
            getattr(credentials, "expired", False)
            or not getattr(credentials, "token", None)
        ):
            credentials.refresh(google.auth.transport.requests.Request())
        return credentials

    def _signing_kwargs(self) -> Dict[str, Any]:
        credentials = self._refresh_credentials()
        service_account_email = settings.GCS_SIGNING_SERVICE_ACCOUNT
        if not service_account_email:
            service_account_email = getattr(credentials, "service_account_email", None)

        kwargs: Dict[str, Any] = {"version": "v4"}
        if service_account_email and credentials and getattr(credentials, "token", None):
            kwargs["service_account_email"] = service_account_email
            kwargs["access_token"] = credentials.token
        return kwargs

    # =========================================================================
    # MULTIPART UPLOADS (compose of temporary part objects)
    # =========================================================================
    def initiate_multipart_upload(
        self,
        key: str,
        mime_type: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Starts a compose-based multipart session and returns an upload_id."""
        upload_id = uuid.uuid4().hex
        self._multipart_meta[upload_id] = {
            "key": key,
            "mime_type": mime_type,
            "metadata": metadata or {},
            "parts": {},
        }
        # Persist session metadata so Cloud Run multi-instance deploys can recover.
        meta_blob = self._bucket().blob(self._multipart_meta_key(upload_id))
        meta_blob.upload_from_string(
            json.dumps(
                {
                    "key": key,
                    "mime_type": mime_type,
                    "metadata": metadata or {},
                }
            ),
            content_type="application/json",
        )
        return upload_id

    def _multipart_meta_key(self, upload_id: str) -> str:
        return f"_multipart/{upload_id}/session.json"

    def _multipart_part_key(self, upload_id: str, part_number: int) -> str:
        return f"_multipart/{upload_id}/part-{part_number:05d}"

    def _load_multipart_session(self, upload_id: str) -> Dict[str, Any]:
        if upload_id in self._multipart_meta:
            return self._multipart_meta[upload_id]
        blob = self._bucket().blob(self._multipart_meta_key(upload_id))
        if not blob.exists():
            raise MediaAppException(
                status_code=404,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="Multipart upload session not found.",
                details={"upload_id": upload_id},
            )
        data = json.loads(blob.download_as_text())
        data["parts"] = data.get("parts", {})
        self._multipart_meta[upload_id] = data
        return data

    def upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> str:
        """Uploads one part object and returns a stable ETag-like token."""
        try:
            session = self._load_multipart_session(upload_id)
            part_key = self._multipart_part_key(upload_id, part_number)
            blob = self._bucket().blob(part_key)
            blob.upload_from_string(data, content_type="application/octet-stream")
            etag = blob.etag or f"part-{part_number}"
            session.setdefault("parts", {})[str(part_number)] = {
                "PartNumber": part_number,
                "ETag": etag,
                "part_key": part_key,
            }
            # Keep destination key in sync if caller passes a different key.
            session["key"] = key or session.get("key")
            self._multipart_meta[upload_id] = session
            return etag
        except MediaAppException:
            raise
        except Exception as e:
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message=f"Failed to upload part {part_number} to storage provider.",
                details={"error": str(e), "part_number": part_number, "key": key},
            )

    def complete_multipart_upload(
        self,
        key: str,
        upload_id: str,
        parts: List[Dict[str, Any]],
    ) -> str:
        """Composes uploaded parts into the destination object."""
        try:
            session = self._load_multipart_session(upload_id)
            destination_key = key or session["key"]
            sorted_parts = sorted(parts, key=lambda p: int(p["PartNumber"]))
            if not sorted_parts:
                raise ValueError("No parts provided for multipart completion.")

            bucket = self._bucket()
            source_blobs = []
            for part in sorted_parts:
                part_number = int(part["PartNumber"])
                part_meta = session.get("parts", {}).get(str(part_number), {})
                part_key = part_meta.get("part_key") or self._multipart_part_key(
                    upload_id, part_number
                )
                source_blobs.append(bucket.blob(part_key))

            mime_type = session.get("mime_type", "application/octet-stream")
            current = source_blobs
            round_idx = 0
            while len(current) > 1:
                next_round = []
                for i in range(0, len(current), 32):
                    batch = current[i : i + 32]
                    if len(batch) == 1:
                        next_round.append(batch[0])
                        continue
                    is_final = len(current) <= 32 and i == 0
                    dest_name = (
                        destination_key
                        if is_final
                        else self._multipart_part_key(upload_id, 80000 + round_idx * 100 + i)
                    )
                    dest_blob = bucket.blob(dest_name)
                    dest_blob.content_type = mime_type
                    next_round.append(dest_blob.compose(batch))
                current = next_round
                round_idx += 1

            final_source = current[0]
            if final_source.name != destination_key:
                bucket.copy_blob(final_source, bucket, destination_key)

            final_blob = bucket.blob(destination_key)
            final_blob.content_type = mime_type
            final_blob.patch()

            self.abort_multipart_upload(destination_key, upload_id)
            return f"gs://{self.bucket_name}/{destination_key}"
        except MediaAppException:
            raise
        except Exception as e:
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="Failed to complete multipart assembly in storage provider.",
                details={"error": str(e), "key": key},
            )

    def abort_multipart_upload(
        self,
        key: str,
        upload_id: str,
        delete_destination: bool = True,
    ) -> None:
        """Deletes temporary multipart part objects and session metadata."""
        try:
            bucket = self._bucket()
            prefix = f"_multipart/{upload_id}/"
            for blob in bucket.list_blobs(prefix=prefix):
                blob.delete()
            self._multipart_meta.pop(upload_id, None)
        except Exception:
            pass  # Best-effort cleanup

    # =========================================================================
    # DIRECT BROWSER / SIGNED UPLOADS
    # =========================================================================
    def create_resumable_upload_url(
        self,
        key: str,
        mime_type: str,
        origin: Optional[str] = None,
        size_bytes: Optional[int] = None,
    ) -> str:
        """Issues a GCS resumable upload session URL for direct browser PUT/POST.

        Args:
            key: GCS object path (must be non-empty).
            mime_type: Content-Type of the upload (e.g. "video/mp4").
            origin: If provided, sets the CORS origin header on the session
                so browsers can PUT directly without a preflight rejection.
            size_bytes: Known upload size in bytes. When supplied GCS enforces
                the exact byte count; must be a positive integer.

        Returns:
            The resumable upload session URI as a string.
        """
        if not key or not key.strip():
            raise MediaAppException(
                status_code=400,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="key must be a non-empty string.",
                details={"key": key},
            )
        if size_bytes is not None and size_bytes <= 0:
            raise MediaAppException(
                status_code=400,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="size_bytes must be a positive integer.",
                details={"size_bytes": size_bytes, "key": key},
            )
        try:
            blob = self._bucket().blob(key)
            return blob.create_resumable_upload_session(
                content_type=mime_type,
                size=size_bytes,
                origin=origin,
            )
        except Exception as e:
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="Failed to create GCS resumable upload session.",
                details={"error": str(e), "key": key},
            )

    def generate_signed_upload_url(
        self,
        key: str,
        mime_type: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Issues a V4 signed PUT URL for direct browser uploads."""
        try:
            blob = self._bucket().blob(key)
            return blob.generate_signed_url(
                expiration=timedelta(seconds=expires_in_seconds),
                method="PUT",
                content_type=mime_type,
                **self._signing_kwargs(),
            )
        except Exception as e:
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="Failed to generate signed upload URL.",
                details={"error": str(e), "key": key},
            )

    # =========================================================================
    # SINGLE OBJECT & FILE STREAMING
    # =========================================================================
    async def upload_file(
        self,
        file_path: str,
        key: str,
        mime_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
        bucket_name: Optional[str] = None,
    ) -> str:
        """Uploads a local file to GCS asynchronously."""

        def _upload() -> str:
            blob = self._bucket(bucket_name).blob(key)
            if metadata:
                blob.metadata = metadata
            blob.upload_from_filename(file_path, content_type=mime_type)
            return f"gs://{bucket_name or self.bucket_name}/{key}"

        try:
            return await asyncio.to_thread(_upload)
        except Exception as e:
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="Failed to upload file to Google Cloud Storage.",
                details={"error": str(e), "key": key},
            )

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        mime_type: str = "application/octet-stream",
        bucket_name: Optional[str] = None,
    ) -> str:
        """Uploads in-memory bytes (e.g. thumbnails or extracted clips)."""

        def _upload() -> str:
            blob = self._bucket(bucket_name).blob(key)
            blob.upload_from_string(data, content_type=mime_type)
            return f"gs://{bucket_name or self.bucket_name}/{key}"

        return await asyncio.to_thread(_upload)

    async def download_file(
        self,
        key: str,
        target_local_path: str,
        bucket_name: Optional[str] = None,
    ) -> None:
        """Downloads an object from GCS to a local file path."""

        def _download() -> None:
            os.makedirs(os.path.dirname(target_local_path) or ".", exist_ok=True)
            blob = self._bucket(bucket_name).blob(key)
            blob.download_to_filename(target_local_path)

        try:
            await asyncio.to_thread(_download)
        except Exception as e:
            raise MediaAppException(
                status_code=404 if "No such object" in str(e) else 500,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="Failed to download file from Google Cloud Storage.",
                details={
                    "error": str(e),
                    "key": key,
                    "bucket": bucket_name or self.bucket_name,
                    "target_local_path": target_local_path,
                },
            ) from e

    def generate_presigned_download_url(
        self,
        key: str,
        expires_in_seconds: int = 3600,
        bucket_name: Optional[str] = None,
    ) -> str:
        """Generates an IAM-backed V4 signed GET URL."""
        try:
            blob = self._bucket(bucket_name).blob(key)
            return blob.generate_signed_url(
                expiration=timedelta(seconds=expires_in_seconds),
                method="GET",
                **self._signing_kwargs(),
            )
        except Exception as e:
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
                message="Failed to generate signed download URL.",
                details={"error": str(e)},
            )

    async def delete_object(self, key: str, bucket_name: Optional[str] = None) -> None:
        """Deletes an object from GCS."""

        def _delete() -> None:
            blob = self._bucket(bucket_name).blob(key)
            if blob.exists():
                blob.delete()

        await asyncio.to_thread(_delete)

    def object_exists(self, key: str, bucket_name: Optional[str] = None) -> bool:
        return self._bucket(bucket_name).blob(key).exists()


# Singleton instance for dependency injection
storage_service = StorageService()

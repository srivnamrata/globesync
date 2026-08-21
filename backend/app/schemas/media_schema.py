from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class InitResumableUploadRequest(BaseModel):
    filename: str = Field(..., example="keynote_2026.mp4")
    filesize_bytes: int = Field(..., gt=0, le=4 * 1024 * 1024 * 1024, example=4294967296)
    mime_type: str = Field(..., example="video/mp4")
    chunk_size_bytes: Optional[int] = Field(default=8 * 1024 * 1024, ge=5 * 1024 * 1024, example=8388608)

    @field_validator("filename")
    def sanitize_filename(cls, v: str) -> str:
        clean = v.strip().replace("..", "").replace("/", "").replace("\\", "")
        if not clean:
            raise ValueError("Filename cannot be empty or invalid.")
        return clean


class InitResumableUploadResponse(BaseModel):
    upload_id: UUID
    filename: str
    filesize_bytes: int
    chunk_size_bytes: int
    total_chunks: int
    storage_path: str
    expires_at: datetime
    # When set, the browser should upload directly to GCS and skip chunk proxies.
    gcs_resumable_url: Optional[str] = None
    upload_mode: str = Field(
        default="proxy_chunks",
        description="proxy_chunks | gcs_resumable",
    )


class InitSignedUploadRequest(BaseModel):
    filename: str = Field(..., example="keynote_2026.mp4")
    filesize_bytes: int = Field(..., gt=0, le=4 * 1024 * 1024 * 1024)
    mime_type: str = Field(..., example="video/mp4")
    origin: Optional[str] = Field(
        None,
        description="Browser Origin header value required by GCS resumable sessions.",
    )

    @field_validator("filename")
    def sanitize_filename(cls, v: str) -> str:
        clean = v.strip().replace("..", "").replace("/", "").replace("\\", "")
        if not clean:
            raise ValueError("Filename cannot be empty or invalid.")
        return clean


class InitSignedUploadResponse(BaseModel):
    upload_id: UUID
    filename: str
    filesize_bytes: int
    storage_path: str
    gcs_resumable_url: str
    expires_at: datetime
    upload_mode: str = "gcs_resumable"


class ChunkUploadResponse(BaseModel):
    upload_id: UUID
    chunk_index: int
    bytes_received: int
    total_bytes: int
    progress_percent: float
    is_completed: bool


class UploadStatusResponse(BaseModel):
    upload_id: UUID
    status: str
    filename: str
    bytes_received: int
    total_bytes: int
    total_chunks: int
    completed_chunks: List[int]
    missing_chunks: List[int]
    progress_percent: float
    expires_at: datetime


class CompleteUploadRequest(BaseModel):
    final_checksum_sha256: Optional[str] = Field(
        None,
        min_length=64,
        max_length=64,
        example="8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4",
    )


class MediaStreamInfo(BaseModel):
    codec: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    # Video-specific
    resolution_width: Optional[int] = None
    resolution_height: Optional[int] = None
    frame_rate: Optional[float] = None
    # Audio-specific
    channels: Optional[int] = None
    sample_rate: Optional[int] = None


class MediaMetadata(BaseModel):
    duration_seconds: float
    filesize_bytes: int
    mime_type: str
    media_type: str
    checksum_sha256: Optional[str] = None
    video: Optional[MediaStreamInfo] = None
    audio: Optional[MediaStreamInfo] = None


class MediaFileResponse(BaseModel):
    media_id: UUID
    filename: str
    media_type: str
    mime_type: str
    filesize_bytes: int
    duration_seconds: float
    resolution: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    frame_rate: Optional[float] = None
    storage_path: str
    thumbnail_url: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ErrorDetail(BaseModel):
    error_code: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

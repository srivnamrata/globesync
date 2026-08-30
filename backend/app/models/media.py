import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class MediaFile(Base):
    """SQLAlchemy model representing an ingested raw or processed media file."""
    __tablename__ = "media_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)

    # Storage information
    storage_provider = Column(String(50), default="s3")
    storage_bucket = Column(String(255), nullable=False)
    storage_path = Column(String(1024), nullable=False)
    thumbnail_path = Column(String(1024), nullable=True)

    # File basic metadata
    original_filename = Column(String(255), nullable=False)
    filesize_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    media_type = Column(String(20), nullable=False)  # "video" or "audio"
    checksum_sha256 = Column(String(64), nullable=True)

    # Probed media stream metadata
    duration_seconds = Column(Numeric(10, 3), nullable=False, default=0.0)
    video_codec = Column(String(50), nullable=True)
    audio_codec = Column(String(50), nullable=True)
    frame_rate = Column(Numeric(6, 3), nullable=True)
    resolution_width = Column(Integer, nullable=True)
    resolution_height = Column(Integer, nullable=True)
    audio_channels = Column(SmallInteger, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    bitrate_kbps = Column(Integer, nullable=True)
    raw_probe_metadata = Column(JSONB, nullable=True)

    # Processing status
    status = Column(String(50), default="ready", index=True)  # ready, processing, error, deleted
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UploadSession(Base):
    """Model tracking state of resumable multipart uploads."""
    __tablename__ = "upload_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)

    filename = Column(String(255), nullable=False)
    filesize_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    total_chunks = Column(Integer, nullable=False)
    chunk_size_bytes = Column(Integer, nullable=False)
    bytes_received = Column(BigInteger, default=0, nullable=False)

    # S3 / GCS Multipart Upload ID
    storage_provider = Column(String(50), default="s3")
    storage_bucket = Column(String(255), nullable=False)
    storage_key = Column(String(1024), nullable=False)
    s3_upload_id = Column(String(255), nullable=True)

    # Upload state
    status = Column(String(50), default="in_progress", index=True)  # in_progress, completed, expired, aborted
    final_checksum_sha256 = Column(String(64), nullable=True)
    media_file_id = Column(UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    chunks = relationship("UploadChunk", back_populates="session", cascade="all, delete-orphan")


class UploadChunk(Base):
    """Tracks individual uploaded chunks for an upload session."""
    __tablename__ = "upload_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("upload_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    byte_start = Column(BigInteger, nullable=False)
    byte_end = Column(BigInteger, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    etag = Column(String(255), nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("UploadSession", back_populates="chunks")

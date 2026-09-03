import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
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


class LipSyncJob(Base):
    """SQLAlchemy model tracking end-to-end neural lip-sync rendering pipeline jobs."""
    __tablename__ = "lipsync_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    request_id = Column(String(255), nullable=True, index=True)
    task_id = Column(String(255), nullable=True, index=True)
    idempotency_key = Column(String(255), nullable=True, index=True)
    media_file_id = Column(UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="CASCADE"), nullable=False, index=True)
    transcript_id = Column(UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False)

    target_language = Column(String(10), nullable=False)
    model_name = Column(String(100), default="arc144/liveportrait", nullable=False)
    render_mode = Column(String(32), default="dub_and_lipsync", nullable=False, index=True)  # dub_only, dub_and_lipsync
    status = Column(String(50), default="queued", index=True)  # queued, in_progress, completed, failed
    progress_percent = Column(SmallInteger, default=0, nullable=False)
    current_stage = Column(String(50), default="queued", nullable=False)
    last_successful_stage = Column(String(50), nullable=True)

    total_segments = Column(Integer, default=0, nullable=False)
    completed_segments = Column(Integer, default=0, nullable=False)

    output_video_gcs_path = Column(String(1024), nullable=True)
    output_filesize_bytes = Column(Integer, nullable=True)
    av_sync_error_ms = Column(Numeric(6, 2), default=0.0)
    quality_score = Column(Numeric(5, 4), default=0.9600)
    error_message = Column(Text, nullable=True)
    execution_time_seconds = Column(Numeric(8, 2), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    segments_metadata = relationship("FrameMetadata", back_populates="job", cascade="all, delete-orphan")

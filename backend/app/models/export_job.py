import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.core.database import Base


class ExportJob(Base):
    """SQLAlchemy database model tracking visual export and mux rendering configurations and stages."""
    __tablename__ = "export_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    media_file_id = Column(UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="CASCADE"), nullable=False)
    transcript_id = Column(UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False)

    target_language = Column(String(10), nullable=False)
    format = Column(String(10), default="mp4")  # mp4, webm, avi, mov
    resolution = Column(String(10), default="1080p")  # 720p, 1080p, 2k, 4k
    frame_rate = Column(Integer, default=30)
    codec = Column(String(20), default="h264")  # h264, h265, vp9, av1
    video_quality = Column(String(20), default="normal")  # fast, normal, high
    audio_codec = Column(String(20), default="aac")  # aac, opus

    # Subtitle Overlay Options
    subtitles_enabled = Column(Boolean, default=False)
    subtitles_format = Column(String(20), default="burnt-in")  # burnt-in, srt, vtt
    subtitles_style = Column(JSONB, nullable=True)  # {font, size, color, background_color}

    # Post-Processing
    color_grading = Column(Boolean, default=False)
    watermark_path = Column(String(1024), nullable=True)
    audio_normalization = Column(Boolean, default=True)  # Normalize to -23 LUFS (or -20 LUFS)

    # Job State
    status = Column(String(50), default="queued", index=True)  # queued, processing, completed, failed
    progress_percent = Column(Integer, default=0, nullable=False)
    current_stage = Column(String(100), default="queued")  # encoding_audio, rendering_frames, muxing, uploading
    output_video_gcs_path = Column(String(1024), nullable=True)
    filesize_bytes = Column(Integer, nullable=True)
    rendering_speed_fps = Column(Numeric(5, 2), default=0.0)
    estimated_cost_usd = Column(Numeric(6, 4), default=0.0000)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

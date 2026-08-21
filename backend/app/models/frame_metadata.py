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
from sqlalchemy.orm import relationship
from app.core.database import Base


class FrameMetadata(Base):
    """SQLAlchemy model tracking segment-level face detection, landmark bounding boxes, and model output."""
    __tablename__ = "frame_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lipsync_job_id = Column(UUID(as_uuid=True), ForeignKey("lipsync_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    transcript_segment_id = Column(UUID(as_uuid=True), ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=False, index=True)
    translation_id = Column(UUID(as_uuid=True), ForeignKey("translations.id", ondelete="SET NULL"), nullable=True)

    sequence_order = Column(Integer, nullable=False, default=0)
    start_time_seconds = Column(Numeric(10, 3), nullable=False)
    end_time_seconds = Column(Numeric(10, 3), nullable=False)

    # Face & Visual Landmark Detection
    face_detected = Column(Boolean, default=True, nullable=False)
    face_confidence = Column(Numeric(5, 4), default=0.9500)
    face_bbox = Column(JSONB, nullable=True)  # {"x": 120, "y": 80, "width": 240, "height": 320}
    face_landmarks = Column(JSONB, nullable=True)  # {"nose": [x,y], "mouth": [x,y], "eyes": [x,y]}
    head_rotation_deg = Column(Numeric(5, 2), default=0.0)

    # Replicate Inference
    replicate_prediction_id = Column(String(255), nullable=True)
    segment_rendered_video_path = Column(String(1024), nullable=True)
    render_status = Column(String(50), default="pending", index=True)  # pending, rendering, completed, skipped, failed
    av_sync_offset_ms = Column(Integer, default=0)
    quality_score = Column(Numeric(5, 4), default=0.9600)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    job = relationship("LipSyncJob", back_populates="segments_metadata")
    segment = relationship("TranscriptSegment", backref="frame_metadata")

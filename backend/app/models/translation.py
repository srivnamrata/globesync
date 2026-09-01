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


class Translation(Base):
    """SQLAlchemy model for translated segments with duration matching metrics."""
    __tablename__ = "translations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcript_segment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transcript_segments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    request_id = Column(String(255), nullable=True, index=True)
    task_id = Column(String(255), nullable=True, index=True)
    idempotency_key = Column(String(255), nullable=True, index=True)

    source_language = Column(String(10), nullable=False, default="en")
    target_language = Column(String(10), nullable=False, index=True)
    source_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)

    # Duration Matching Metrics
    original_duration_ms = Column(Integer, nullable=False)
    estimated_duration_ms = Column(Integer, nullable=False)
    duration_ratio = Column(Numeric(5, 3), nullable=False, default=1.000)  # estimated / original
    iterations_count = Column(SmallInteger, nullable=False, default=1)
    confidence_score = Column(Numeric(5, 4), nullable=True, default=0.9500)
    quality_score = Column(Numeric(5, 4), nullable=True, default=0.9500)
    is_cached = Column(Boolean, default=False, nullable=False)
    is_user_edited = Column(Boolean, default=False, nullable=False)

    # Downstream TTS & Retiming fields
    target_audio_gcs_path = Column(String(1024), nullable=True)
    speed_adjustment_factor = Column(Numeric(4, 3), default=1.000)

    # Metadata & iteration history
    iteration_history = Column(JSONB, nullable=True, default=list)
    source_action = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    segment = relationship("TranscriptSegment", backref="translations")

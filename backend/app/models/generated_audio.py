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


class GeneratedAudio(Base):
    """SQLAlchemy model for synthesized, retimed, and post-processed audio speech segments."""
    __tablename__ = "generated_audios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    translation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("translations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    storage_bucket = Column(String(255), nullable=False)
    storage_path = Column(String(1024), nullable=False)

    # Timing and Duration Metrics
    raw_tts_duration_ms = Column(Integer, nullable=False)
    target_duration_ms = Column(Integer, nullable=False)
    retimed_duration_ms = Column(Integer, nullable=False)
    speed_adjustment_factor = Column(Numeric(5, 3), default=1.000, nullable=False)
    pitch_adjustment_semitones = Column(Numeric(4, 2), default=0.00, nullable=False)

    # Quality & Status
    status = Column(String(50), default="ready", index=True)  # ready, processing, failed
    is_retimed = Column(Boolean, default=True, nullable=False)
    quality_score = Column(Numeric(5, 4), default=0.9800, nullable=False)
    metadata_log = Column(JSONB, nullable=True, default=dict)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    translation = relationship("Translation", backref="generated_audio")

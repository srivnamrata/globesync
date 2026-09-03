import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class VoiceProfile(Base):
    """SQLAlchemy model for cloned speaker voice profiles and ElevenLabs voice associations."""
    __tablename__ = "voice_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)

    speaker_name = Column(String(255), nullable=False)
    gender = Column(String(20), nullable=True)
    language = Column(String(10), default="en", nullable=False)

    external_provider = Column(String(50), default="elevenlabs", nullable=False)
    external_voice_id = Column(String(255), nullable=False)  # ElevenLabs generated Voice ID
    reference_sample_gcs_path = Column(String(1024), nullable=True)
    reference_sample_duration_sec = Column(Numeric(8, 2), nullable=True)

    # Acoustic & Prosody Metadata
    embedding_vector = Column(JSONB, nullable=True)
    voice_settings = Column(
        JSONB,
        default={
            "stability": 0.50,
            "similarity_boost": 0.80,
            "style": 0.05,
            "use_speaker_boost": True,
            "warmth": 0.5,
            "depth": 0.5,
        },
        nullable=False,
    )
    confidence_score = Column(Numeric(5, 4), default=0.9500, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

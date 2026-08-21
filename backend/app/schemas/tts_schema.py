from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class VoiceProfileResponse(BaseModel):
    voice_id: UUID
    speaker_name: str
    language: str
    external_voice_id: str
    reference_sample_url: Optional[str] = None
    voice_settings: Dict[str, Any] = Field(default_factory=dict)
    confidence_score: float
    created_at: datetime


class CloneVoiceRequest(BaseModel):
    speaker_name: str = Field(..., example="Speaker 1")
    media_id: UUID
    speaker_tag: str = Field("Speaker 1", example="Speaker 1")
    project_id: Optional[UUID] = None


class SynthesizeProjectTTSRequest(BaseModel):
    transcript_id: UUID
    target_language: str = Field(..., example="es")
    project_id: Optional[UUID] = None


class SynthesizeSegmentTTSRequest(BaseModel):
    translation_id: UUID
    voice_profile_id: Optional[UUID] = None


class GeneratedAudioResponse(BaseModel):
    id: UUID
    translation_id: UUID
    voice_profile_id: Optional[UUID] = None
    audio_url: Optional[str] = None
    storage_path: str
    raw_tts_duration_ms: int
    target_duration_ms: int
    retimed_duration_ms: int
    speed_adjustment_factor: float
    is_retimed: bool
    status: str
    quality_score: float
    created_at: datetime


class MasterDubbedAudioResponse(BaseModel):
    project_id: Optional[UUID] = None
    transcript_id: UUID
    target_language: str
    master_audio_url: Optional[str] = None
    storage_path: str
    status: str = "completed"
    message: str = "Master dubbed audio track assembled."


class TTSJobResponse(BaseModel):
    job_id: str
    transcript_id: UUID
    target_language: str
    status: str = Field(default="queued")
    message: str = Field(default="TTS speech synthesis and audio retiming queued.")

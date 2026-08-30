from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class SynthesizeProjectTTSRequest(BaseModel):
    transcript_id: UUID
    target_language: str = Field(..., examples=["es"])
    project_id: Optional[UUID] = None


class SynthesizeSegmentTTSRequest(BaseModel):
    translation_id: UUID


class GeneratedAudioResponse(BaseModel):
    id: UUID
    translation_id: UUID
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

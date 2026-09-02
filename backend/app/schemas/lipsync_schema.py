from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class RenderLipSyncProjectRequest(BaseModel):
    media_file_id: UUID
    transcript_id: UUID
    target_language: str = Field(..., examples=["es"])
    project_id: Optional[UUID] = None
    model_preference: str = Field("liveportrait", examples=["liveportrait"], description="'liveportrait' or 'wav2lip'")
    burn_in_subtitles: bool = Field(False, description="Burn subtitles directly into video pixels")
    enable_lipsync: bool = Field(True, description="When False, produces a dubbed video with audio replacement only — skips neural face synthesis entirely")


class RenderSegmentLipSyncRequest(BaseModel):
    segment_id: UUID
    translation_id: UUID
    model_preference: str = Field("liveportrait", examples=["liveportrait"])


class FrameMetadataResponse(BaseModel):
    id: UUID
    segment_id: UUID
    sequence_order: int
    start_time_seconds: float
    end_time_seconds: float
    face_detected: bool
    face_confidence: float
    head_rotation_deg: float
    render_status: str
    av_sync_offset_ms: int
    quality_score: float


class LipSyncJobResponse(BaseModel):
    job_id: UUID
    project_id: Optional[UUID] = None
    media_file_id: UUID
    target_language: str
    model_name: str
    status: str
    progress_percent: int
    total_segments: int
    completed_segments: int
    output_video_url: Optional[str] = None
    quality_score: float
    av_sync_error_ms: float
    segments_metadata: List[FrameMetadataResponse] = Field(default_factory=list)
    execution_time_seconds: Optional[float] = None
    created_at: datetime


class LipSyncDispatchResponse(BaseModel):
    job_id: UUID
    status: str = "queued"
    message: str = "Neural lip-sync video rendering pipeline queued."


class ReplicateWebhookPayload(BaseModel):
    id: str
    status: str
    output: Optional[Any] = None
    error: Optional[str] = None

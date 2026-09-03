from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class SubtitleSettings(BaseModel):
    enabled: bool = Field(False)
    format: str = Field("burnt-in", examples=["burnt-in"], description="'burnt-in', 'srt', or 'vtt'")
    appearance: Dict[str, Any] = Field(default_factory=dict)  # {font, size, color, background_color}


class PostProcessingSettings(BaseModel):
    color_grading: bool = Field(False)
    watermark: Optional[str] = Field(None, examples=["watermarks/logo.png"])
    audio_normalization: bool = Field(True)


class ExportRequest(BaseModel):
    media_file_id: UUID
    transcript_id: UUID
    project_id: Optional[UUID] = None
    target_language: str = Field(..., examples=["es"])
    format: str = Field("mp4", examples=["mp4"])
    resolution: str = Field("1080p", examples=["1080p"])
    frame_rate: int = Field(30, examples=[30])
    codec: str = Field("h264", examples=["h264"])
    video_quality: str = Field("normal", examples=["normal"])
    audio_codec: str = Field("aac", examples=["aac"])
    subtitles: SubtitleSettings
    post_processing: PostProcessingSettings


class ExportJobResponse(BaseModel):
    id: UUID
    project_id: Optional[UUID] = None
    media_file_id: UUID
    target_language: str
    format: str
    resolution: str
    frame_rate: int
    codec: str
    status: str
    progress_percent: int
    current_stage: str
    output_video_url: Optional[str] = None
    download_video_url: Optional[str] = None
    filesize_bytes: Optional[int] = None
    estimated_cost_usd: float
    created_at: datetime


class ExportDispatchResponse(BaseModel):
    job_id: UUID
    status: str = "queued"
    message: str = "Asynchronous video export job enqueued."

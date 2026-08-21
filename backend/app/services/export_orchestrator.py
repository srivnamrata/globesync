import logging
import os
import time
import uuid
from typing import Any, Dict, Optional
from app.core.config import settings
from app.services.ffmpeg_service import ffmpeg_service
from app.services.storage_service import storage_service
from app.services.subtitle_generator import subtitle_generator

logger = logging.getLogger("export_orchestrator")


class ExportOrchestrator:
    """Orchestrates subtitle conversions, visual enhancements, and audio/video encoding rendering pipelines."""

    @classmethod
    async def process_export_render(
        cls,
        video_source_path: str,
        audio_dubbed_path: str,
        output_local_path: str,
        job_settings: Dict[str, Any],
        segments_data: Optional[Any] = None,
    ) -> str:
        """
        Runs the full rendering loop:
        1. Compiles subtitles (SRT/VTT) if enabled
        2. Applies watermarks or letterboxes if specified
        3. Invokes FFmpegService to encode video based on format and resolution specifications
        """
        temp_dir = settings.PROCESSED_MEDIA_DIR
        sub_srt_path = None
        
        subtitles_config = job_settings.get("subtitles", {})
        subtitles_enabled = subtitles_config.get("enabled", False)

        # 1. Generate Subtitles if enabled
        if subtitles_enabled and segments_data:
            from app.schemas.transcription_schema import SegmentResponse
            mapped_segs = [
                SegmentResponse(
                    start_time=float(s["start_sec"]),
                    end_time=float(s["end_sec"]),
                    duration=float(s["duration_sec"]),
                    speaker=s.get("speaker_tag", "Speaker 1"),
                    text=s["text"],
                )
                for s in segments_data
            ]
            
            srt_content = subtitle_generator.generate_srt(mapped_segs)
            sub_srt_path = os.path.join(temp_dir, f"sub_export_{uuid.uuid4().hex}.srt")
            with open(sub_srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)

        # 2. Trigger FFmpeg Video Encoding pipeline
        post_proc = job_settings.get("post_processing", {})
        color_grading = post_proc.get("color_grading", False)
        audio_norm = post_proc.get("audio_normalization", True)
        watermark = post_proc.get("watermark", None)

        await ffmpeg_service.render_export_video(
            video_input_path=video_source_path,
            audio_input_path=audio_dubbed_path,
            output_path=output_local_path,
            format=job_settings.get("format", "mp4"),
            resolution=job_settings.get("resolution", "1080p"),
            codec=job_settings.get("codec", "h264"),
            frame_rate=int(job_settings.get("frame_rate", 30)),
            video_quality=job_settings.get("video_quality", "normal"),
            audio_codec=job_settings.get("audio_codec", "aac"),
            color_grading=color_grading,
            watermark_image_path=watermark,
            subtitle_srt_path=sub_srt_path,
            burn_in_subtitles=subtitles_config.get("format") == "burnt-in",
            audio_normalization=audio_norm,
        )

        # Cleanup temporary subtitles
        if sub_srt_path and os.path.exists(sub_srt_path):
            os.remove(sub_srt_path)

        return output_local_path


export_orchestrator = ExportOrchestrator()

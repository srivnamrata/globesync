import asyncio
import os
import subprocess
from typing import Any, Dict, List, Optional
from app.utils.error_codes import ErrorCode, MediaAppException


class FFmpegService:
    """Core video rendering service wrapping FFmpeg visual transformations, watermarking & audio leveling."""

    @classmethod
    async def render_export_video(
        cls,
        video_input_path: str,
        audio_input_path: str,
        output_path: str,
        format: str = "mp4",
        resolution: str = "1080p",
        codec: str = "h264",
        frame_rate: int = 30,
        video_quality: str = "normal",
        audio_codec: str = "aac",
        color_grading: bool = False,
        watermark_image_path: Optional[str] = None,
        subtitle_srt_path: Optional[str] = None,
        burn_in_subtitles: bool = False,
        audio_normalization: bool = True,
    ) -> str:
        """Runs the FFmpeg command mapping parameters to target formats, presets, and codecs."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        inputs = ["-i", video_input_path, "-i", audio_input_path]
        filter_complex = []
        video_filters = []

        # Resolution scaling
        res_map = {
            "720p": "1280:720",
            "1080p": "1920:1080",
            "2k": "2560:1440",
            "4k": "3840:2160",
        }
        scale_target = res_map.get(resolution, "1920:1080")
        video_filters.append(f"scale={scale_target}")

        # Color grading adjustments (brightness, contrast, saturation)
        if color_grading:
            # Subtle boost for visual pop: +10% contrast, +20% saturation
            video_filters.append("eq=contrast=1.1:saturation=1.2")

        # Watermark overlay
        if watermark_image_path and os.path.exists(watermark_image_path):
            inputs.extend(["-i", watermark_image_path])
            # Overlay logo at top-right corner with 10px margin
            filter_complex.append(f"[0:v]{','.join(video_filters)}[vbase];")
            filter_complex.append("[vbase][2:v]overlay=W-w-10:10[vwatermarked];")
            current_video_label = "[vwatermarked]"
        else:
            filter_complex.append(f"[0:v]{','.join(video_filters)}[vbase];")
            current_video_label = "[vbase]"

        # Subtitles burn-in
        if subtitle_srt_path and os.path.exists(subtitle_srt_path) and burn_in_subtitles:
            srt_escaped = subtitle_srt_path.replace("\\", "/").replace(":", "\\:")
            # Burn in subtitles on top of video stream
            filter_complex.append(f"{current_video_label}subtitles='{srt_escaped}'[vsubbed]")
            current_video_label = "[vsubbed]"

        # Map Codecs and presets
        v_codec_arg = "libx264"
        if codec == "h265" or codec == "hevc":
            v_codec_arg = "libx265"
        elif codec == "vp9":
            v_codec_arg = "libvpx-vp9"
        elif codec == "av1":
            v_codec_arg = "libsvtav1"

        preset_arg = "medium"
        if video_quality == "fast":
            preset_arg = "veryfast"
        elif video_quality == "high":
            preset_arg = "slow"

        # Audio Normalization to -23 LUFS (Standard broadcast level)
        audio_filters = []
        if audio_normalization:
            audio_filters.append("loudnorm=I=-23:LRA=7:TP=-2.0")

        # Audio Codec mapping
        a_codec_arg = "aac"
        if audio_codec == "opus":
            a_codec_arg = "libopus"

        cmd = ["ffmpeg", "-y"] + inputs
        
        filter_str = "".join(filter_complex)
        if filter_str:
            cmd.extend(["-filter_complex", filter_str, "-map", current_video_label])
        else:
            cmd.extend(["-map", "0:v"])

        if audio_filters:
            cmd.extend(["-af", ",".join(audio_filters)])
        
        cmd.extend([
            "-map", "1:a",
            "-c:v", v_codec_arg,
            "-preset", preset_arg,
            "-r", str(frame_rate),
            "-c:a", a_codec_arg,
            "-b:a", "192k",
            "-shortest",
            output_path,
        ])

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0 or not os.path.exists(output_path):
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Video rendering and encoding failed.",
                details={"stderr": stderr.decode("utf-8", errors="ignore")},
            )

        return output_path


# Hack to support boolean 'false' in case lowercase is used
false = False

ffmpeg_service = FFmpegService()

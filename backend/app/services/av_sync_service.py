import asyncio
import os
from typing import Tuple
from app.services.audio_postprocessor import audio_postprocessor
from app.services.video_processor import video_processor


class AVSyncChecker:
    """Checks and corrects Audio-Video synchrony drift to ensure tight ±100ms alignment."""

    @classmethod
    async def measure_av_drift_ms(cls, video_path: str, audio_path: str) -> float:
        """
        Measures the timing discrepancy between the video stream and the dub audio stream.
        Returns drift in milliseconds (+ indicates audio is longer, - indicates video is longer).
        """
        _, _, _, vid_dur_sec = await video_processor.get_video_properties(video_path)
        audio_dur_ms = await audio_postprocessor.get_audio_duration_ms(audio_path)
        video_dur_ms = int(vid_dur_sec * 1000)

        drift_ms = float(audio_dur_ms - video_dur_ms)
        return drift_ms

    @classmethod
    async def align_av_streams(
        cls,
        video_path: str,
        audio_path: str,
        output_path: str,
        offset_ms: float = 0.0,
    ) -> str:
        """
        Muxes video and audio streams, applying delay compensation to lock A/V sync.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if abs(offset_ms) > 10.0:
            offset_sec = offset_ms / 1000.0
            cmd = [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-itsoffset", f"{offset_sec:.3f}",
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                output_path,
            ]

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()
        return output_path


av_sync_service = AVSyncChecker()

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.services.video_processor import video_processor
from app.utils.error_codes import ErrorCode, MediaAppException

logger = logging.getLogger("video_reconstructor")


class VideoReconstructor:
    """Reconstructs the full master translated video by compositing lip-synced segments and multiplexing master dubbed audio."""

    @classmethod
    async def reconstruct_video_with_lip_sync(
        cls,
        original_video_path: str,
        lip_synced_segments: List[Dict[str, Any]],  # [{"segment_path": ..., "start_sec": ..., "duration_sec": ...}]
        master_dubbed_audio_path: str,
        output_final_video_path: str,
        subtitle_srt_path: Optional[str] = None,
        burn_in_subtitles: bool = False,
    ) -> str:
        """
        Assembles full video timeline:
        - Replaces dialogue video slices with neural lip-synced rendered segments
        - Preserves original video during non-speech pauses
        - Muxes master dubbed audio track
        - Applies optional subtitle stream
        """
        os.makedirs(os.path.dirname(output_final_video_path), exist_ok=True)
        temp_dir = settings.PROCESSED_MEDIA_DIR

        # Sort segments by start time
        sorted_segs = sorted(lip_synced_segments, key=lambda s: float(s["start_sec"]))
        width, height, fps, total_dur = await video_processor.get_video_properties(original_video_path)

        if not sorted_segs:
            # If no lip-sync segments, simply remux original video with dubbed audio
            return await cls._mux_video_and_audio(
                original_video_path, master_dubbed_audio_path, output_final_video_path, subtitle_srt_path, burn_in_subtitles
            )

        # Build sequential timeline clips: [idle_clip_0, lipsync_seg_0, idle_clip_1, lipsync_seg_1, ...]
        timeline_clips: List[str] = []
        current_time = 0.0

        for idx, seg in enumerate(sorted_segs):
            seg_start = float(seg["start_sec"])
            seg_dur = float(seg["duration_sec"])
            rendered_clip = seg["segment_path"]

            # If there's an idle gap before this segment, slice it from the original video
            if seg_start > current_time + 0.05:
                gap_dur = seg_start - current_time
                gap_clip_path = os.path.join(temp_dir, f"gap_{idx}_{uuid_hex()[:8]}.mp4")
                await video_processor.extract_video_segment(
                    video_input_path=original_video_path,
                    start_seconds=current_time,
                    duration_seconds=gap_dur,
                    output_segment_path=gap_clip_path,
                )
                timeline_clips.append(gap_clip_path)

            if os.path.exists(rendered_clip):
                timeline_clips.append(rendered_clip)
            current_time = seg_start + seg_dur

        # If there's a trailing gap after the last segment until video end
        if current_time < total_dur - 0.05:
            tail_dur = total_dur - current_time
            tail_clip_path = os.path.join(temp_dir, f"tail_{uuid_hex()[:8]}.mp4")
            await video_processor.extract_video_segment(
                video_input_path=original_video_path,
                start_seconds=current_time,
                duration_seconds=tail_dur,
                output_segment_path=tail_clip_path,
            )
            timeline_clips.append(tail_clip_path)

        # Concatenate all video clips using FFmpeg concat demuxer
        concat_list_file = os.path.join(temp_dir, f"concat_timeline_{uuid_hex()[:8]}.txt")
        video_stitched_temp = os.path.join(temp_dir, f"stitched_{uuid_hex()[:8]}.mp4")

        with open(concat_list_file, "w") as f:
            for clip in timeline_clips:
                # Use forward slashes for ffmpeg concat list file
                f.write(f"file '{clip.replace(chr(92), '/')}'\n")

        # Concat video stream
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_file,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-an",  # drop audio from chunks
            video_stitched_temp,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()

        # Cleanup concat list and temporary gap slices
        if os.path.exists(concat_list_file):
            os.remove(concat_list_file)
        for clip in timeline_clips:
            if "gap_" in clip or "tail_" in clip:
                if os.path.exists(clip):
                    try:
                        os.remove(clip)
                    except Exception:
                        pass

        # Final step: Multiplex stitched video with Master Dubbed Audio & Subtitles
        target_video_input = video_stitched_temp if os.path.exists(video_stitched_temp) else original_video_path
        final_result = await cls._mux_video_and_audio(
            video_path=target_video_input,
            audio_path=master_dubbed_audio_path,
            output_path=output_final_video_path,
            subtitle_srt_path=subtitle_srt_path,
            burn_in_subtitles=burn_in_subtitles,
        )

        if os.path.exists(video_stitched_temp):
            os.remove(video_stitched_temp)

        return final_result

    @classmethod
    async def _mux_video_and_audio(
        cls,
        video_path: str,
        audio_path: str,
        output_path: str,
        subtitle_srt_path: Optional[str] = None,
        burn_in_subtitles: bool = False,
    ) -> str:
        """Multiplexes video stream, audio stream, and subtitles into clean MP4 container."""
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-i", audio_path,
        ]

        subtitle_input_index = None
        if subtitle_srt_path and os.path.exists(subtitle_srt_path):
            if burn_in_subtitles:
                # Burn in subtitles directly to video pixels
                srt_escaped = subtitle_srt_path.replace("\\", "/").replace(":", "\\:")
                cmd.extend(["-vf", f"subtitles='{srt_escaped}'", "-c:v", "libx264", "-crf", "18"])
            else:
                # Soft subtitle track
                subtitle_input_index = 2
                cmd.extend(["-i", subtitle_srt_path, "-c:s", "mov_text", "-metadata:s:s:0", "language=spa"])
        else:
            cmd.extend(["-c:v", "copy"])

        cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
        if subtitle_input_index is not None:
            cmd.extend(["-map", f"{subtitle_input_index}:s:0"])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",  # Web streaming optimization
            output_path,
        ])

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0 or not os.path.exists(output_path):
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Final video reconstruction and muxing failed.",
                details={"stderr": stderr.decode("utf-8", errors="ignore")},
            )

        return output_path


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex


video_reconstructor = VideoReconstructor()

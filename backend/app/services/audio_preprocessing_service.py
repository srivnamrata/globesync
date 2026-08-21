import asyncio
import os
import re
from typing import List, Optional, Tuple
from app.core.config import settings
from app.utils.error_codes import ErrorCode, MediaAppException


class AudioPreprocessor:
    """
    Audio preprocessing pipeline providing noise reduction, EBU R128 loudness normalization,
    Voice Activity Detection (VAD), and silence-based chunking for long-form speech.
    """

    @classmethod
    async def preprocess_audio_pipeline(
        cls,
        input_wav_path: str,
        output_processed_path: Optional[str] = None,
        apply_noise_reduction: bool = True,
        apply_loudness_norm: bool = True,
        target_lufs: float = -20.0,
    ) -> str:
        """
        Executes an end-to-end chained FFmpeg audio filtergraph:
        [highpass 80Hz] -> [lowpass 7.5kHz] -> [afftdn noise filter] -> [loudnorm -20 LUFS]
        """
        if not output_processed_path:
            base_name = os.path.splitext(os.path.basename(input_wav_path))[0]
            output_processed_path = os.path.join(
                settings.PROCESSED_MEDIA_DIR, f"{base_name}_preprocessed.wav"
            )

        os.makedirs(os.path.dirname(output_processed_path), exist_ok=True)

        # Build filter chain
        filters: List[str] = []

        if apply_noise_reduction:
            # 1. High-pass filter to remove low-frequency mic rumble / AC hum (<80Hz)
            filters.append("highpass=f=80")
            # 2. Low-pass filter to remove high-frequency hiss (>7500Hz for speech clarity)
            filters.append("lowpass=f=7500")
            # 3. FFT-based adaptive noise reduction
            filters.append("afftdn=nf=-25")

        if apply_loudness_norm:
            # 4. EBU R128 dual-pass or single-pass integrated loudness normalization
            filters.append(f"loudnorm=I={target_lufs}:LRA=11:TP=-1.5")

        filter_str = ",".join(filters) if filters else "anull"

        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_wav_path,
            "-af", filter_str,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_processed_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0 or not os.path.exists(output_processed_path):
            raise MediaAppException(
                status_code=500,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Audio preprocessing pipeline failed during filter execution.",
                details={"stderr": stderr.decode("utf-8", errors="ignore")},
            )

        return output_processed_path

    @classmethod
    async def detect_silence_segments(
        cls,
        input_audio_path: str,
        noise_threshold_db: float = -30.0,
        min_silence_duration_sec: float = 0.5,
    ) -> List[Tuple[float, float]]:
        """
        Runs FFmpeg silencedetect filter to find silence periods:
        Returns a list of (silence_start, silence_end) in seconds.
        """
        cmd = [
            "ffmpeg",
            "-i", input_audio_path,
            "-af", f"silencedetect=noise={noise_threshold_db}dB:d={min_silence_duration_sec}",
            "-f", "null",
            "-",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        stderr_str = stderr.decode("utf-8", errors="ignore")

        silence_starts: List[float] = []
        silence_intervals: List[Tuple[float, float]] = []

        start_pattern = re.compile(r"silence_start: ([\d\.]+)")
        end_pattern = re.compile(r"silence_end: ([\d\.]+) \| silence_duration: ([\d\.]+)")

        for line in stderr_str.splitlines():
            start_match = start_pattern.search(line)
            if start_match:
                silence_starts.append(float(start_match.group(1)))

            end_match = end_pattern.search(line)
            if end_match and silence_starts:
                s_start = silence_starts.pop(0)
                s_end = float(end_match.group(1))
                silence_intervals.append((s_start, s_end))

        return silence_intervals

    @classmethod
    async def split_audio_into_chunks_if_needed(
        cls,
        input_audio_path: str,
        total_duration_sec: float,
        max_chunk_duration_sec: float = 1200.0,  # 20 minutes max chunk
    ) -> List[Tuple[str, float, float]]:
        """
        Splits 60+ minute audio files into speech-boundary chunks for parallel or safe STT processing.
        Returns list of tuples: (chunk_file_path, start_time_offset, duration).
        """
        if total_duration_sec <= max_chunk_duration_sec:
            return [(input_audio_path, 0.0, total_duration_sec)]

        silence_points = await cls.detect_silence_segments(input_audio_path)
        chunks: List[Tuple[str, float, float]] = []

        current_start = 0.0
        base_dir = os.path.dirname(input_audio_path)
        base_name = os.path.splitext(os.path.basename(input_audio_path))[0]
        chunk_idx = 0

        while current_start < total_duration_sec:
            target_end = min(current_start + max_chunk_duration_sec, total_duration_sec)
            
            # If not the last chunk, find the closest silence point near target_end
            split_point = target_end
            if target_end < total_duration_sec and silence_points:
                # Find silence point within [target_end - 60s, target_end + 30s]
                candidates = [
                    (s_start + s_end) / 2.0
                    for s_start, s_end in silence_points
                    if target_end - 60.0 <= s_start <= target_end + 30.0
                ]
                if candidates:
                    split_point = min(candidates, key=lambda c: abs(c - target_end))

            chunk_duration = split_point - current_start
            chunk_path = os.path.join(base_dir, f"{base_name}_chunk_{chunk_idx}.wav")

            # Extract slice
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", f"{current_start:.3f}",
                "-i", input_audio_path,
                "-t", f"{chunk_duration:.3f}",
                "-acodec", "copy",
                chunk_path,
            ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()

            chunks.append((chunk_path, current_start, chunk_duration))
            current_start = split_point
            chunk_idx += 1

        return chunks


audio_preprocessor = AudioPreprocessor()

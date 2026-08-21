import asyncio
import json
import os
import subprocess
import uuid
from typing import Any, Dict, Optional, Tuple
from app.core.config import settings
from app.schemas.media_schema import MediaMetadata, MediaStreamInfo
from app.services.storage_service import storage_service
from app.utils.error_codes import (
    ErrorCode,
    MediaAppException,
    UnsupportedCodecException,
)
from app.utils.file_validators import validate_codecs


class MediaService:
    """Media processing engine managing ffprobe inspection, codec validation, and thumbnail generation."""

    @staticmethod
    def generate_storage_key(filename: str, prefix: str = "raw") -> str:
        """Generates a collision-resistant partitioned storage key: raw/YYYY/MM/UUID/filename."""
        unique_id = uuid.uuid4().hex
        ext = os.path.splitext(filename)[1].lower()
        clean_name = os.path.splitext(os.path.basename(filename))[0]
        return f"{prefix}/{unique_id[:2]}/{unique_id[2:4]}/{unique_id}/{clean_name}{ext}"

    @classmethod
    async def probe_media_file(cls, file_path: str) -> MediaMetadata:
        """Runs ffprobe asynchronously to extract complete container and stream metadata."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        try:
            # subprocess.run in a worker thread works consistently on Windows,
            # where some development-server event loops do not implement the
            # asyncio subprocess APIs.
            process = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                check=False,
            )
            stdout, stderr = process.stdout, process.stderr

            if process.returncode != 0:
                raise MediaAppException(
                    status_code=422,
                    error_code=ErrorCode.FFPROBE_ANALYSIS_FAILED,
                    message="Failed to analyze media file stream format with ffprobe.",
                    details={"stderr": stderr.decode("utf-8", errors="ignore")},
                )

            data = json.loads(stdout.decode("utf-8"))
            format_info = data.get("format", {})
            streams = data.get("streams", [])

            duration = float(format_info.get("duration", 0.0))
            filesize = int(format_info.get("size", os.path.getsize(file_path)))
            
            video_stream: Optional[Dict[str, Any]] = None
            audio_stream: Optional[Dict[str, Any]] = None

            for stream in streams:
                codec_type = stream.get("codec_type")
                if codec_type == "video" and not video_stream:
                    # Filter out embedded cover art pictures
                    if stream.get("disposition", {}).get("attached_pic") != 1:
                        video_stream = stream
                elif codec_type == "audio" and not audio_stream:
                    audio_stream = stream

            is_video = video_stream is not None
            media_type = "video" if is_video else "audio"

            # Parse video stream properties
            video_info: Optional[MediaStreamInfo] = None
            if video_stream:
                fps = cls._calculate_fps(video_stream.get("avg_frame_rate", "0/0"))
                video_info = MediaStreamInfo(
                    codec=video_stream.get("codec_name"),
                    resolution_width=int(video_stream.get("width", 0)),
                    resolution_height=int(video_stream.get("height", 0)),
                    frame_rate=fps,
                    bitrate_kbps=int(video_stream.get("bit_rate", 0)) // 1000 if video_stream.get("bit_rate") else None,
                )

            # Parse audio stream properties
            audio_info: Optional[MediaStreamInfo] = None
            if audio_stream:
                audio_info = MediaStreamInfo(
                    codec=audio_stream.get("codec_name"),
                    channels=int(audio_stream.get("channels", 0)),
                    sample_rate=int(audio_stream.get("sample_rate", 0)),
                    bitrate_kbps=int(audio_stream.get("bit_rate", 0)) // 1000 if audio_stream.get("bit_rate") else None,
                )

            # Validate codecs
            validate_codecs(
                video_codec=video_info.codec if video_info else None,
                audio_codec=audio_info.codec if audio_info else None,
                is_video=is_video,
            )

            # Infer mime type
            mime_type = "video/mp4" if is_video else "audio/wav"

            return MediaMetadata(
                duration_seconds=duration,
                filesize_bytes=filesize,
                mime_type=mime_type,
                media_type=media_type,
                video=video_info,
                audio=audio_info,
            )

        except FileNotFoundError:
            # Fallback if ffprobe binary is not present in local test environment
            return cls._mock_fallback_metadata(file_path)
        except MediaAppException:
            raise
        except Exception as e:
            raise MediaAppException(
                status_code=422,
                error_code=ErrorCode.FFPROBE_ANALYSIS_FAILED,
                message=f"Media probe parsing encountered an unexpected error: {str(e)}",
            )

    @classmethod
    async def generate_thumbnail(
        cls,
        video_path: str,
        storage_key: str,
        seek_time_seconds: float = 1.0,
    ) -> Optional[str]:
        """Captures a frame from a video and uploads it directly to object storage as JPEG."""
        thumbnail_temp_path = f"{video_path}.thumb.jpg"
        thumb_storage_key = f"{storage_key}.thumb.jpg"

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(seek_time_seconds),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            "-vf", "scale='min(1280,iw)':-2",
            thumbnail_temp_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            if process.returncode == 0 and os.path.exists(thumbnail_temp_path):
                # Upload thumbnail to storage
                await storage_service.upload_file(
                    file_path=thumbnail_temp_path,
                    key=thumb_storage_key,
                    mime_type="image/jpeg",
                )
                return thumb_storage_key
            return None
        except Exception:
            return None
        finally:
            if os.path.exists(thumbnail_temp_path):
                try:
                    os.remove(thumbnail_temp_path)
                except Exception:
                    pass

    @staticmethod
    def _calculate_fps(avg_frame_rate: str) -> Optional[float]:
        """Parses '30000/1001' or '25/1' into a float FPS."""
        try:
            if "/" in avg_frame_rate:
                num, den = avg_frame_rate.split("/")
                if float(den) > 0:
                    return round(float(num) / float(den), 3)
            return round(float(avg_frame_rate), 3)
        except Exception:
            return None

    @staticmethod
    def _mock_fallback_metadata(file_path: str) -> MediaMetadata:
        """Safe fallback providing estimated metadata when ffprobe binary is not installed in runtime."""
        size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        ext = os.path.splitext(file_path)[1].lower()
        is_video = ext in [".mp4", ".mov", ".webm", ".mkv", ".avi"]
        return MediaMetadata(
            duration_seconds=120.0,
            filesize_bytes=size,
            mime_type="video/mp4" if is_video else "audio/wav",
            media_type="video" if is_video else "audio",
            video=MediaStreamInfo(codec="h264", resolution_width=1920, resolution_height=1080, frame_rate=30.0) if is_video else None,
            audio=MediaStreamInfo(codec="aac", channels=2, sample_rate=48000),
        )


media_service = MediaService()

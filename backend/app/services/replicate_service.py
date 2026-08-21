import asyncio
import logging
import os
import uuid
from typing import Any, Dict, Optional
import httpx
import replicate
from app.core.config import settings
from app.services.storage_service import storage_service
from app.utils.error_codes import ErrorCode, MediaAppException
from app.utils.replicate_utils import replicate_utils

logger = logging.getLogger("replicate_service")


class ReplicateLipSync:
    """Replicate client orchestrating LivePortrait & Wav2Lip neural video lip-sync synthesis."""

    def __init__(self):
        self.api_token = settings.REPLICATE_API_TOKEN
        self.liveportrait_model = settings.LIPSYNC_MODEL_PRIMARY
        self.wav2lip_model = settings.LIPSYNC_MODEL_FALLBACK
        if self.api_token and "test" not in self.api_token and "placeholder" not in self.api_token:
            os.environ["REPLICATE_API_TOKEN"] = self.api_token

    async def render_segment_lipsync(
        self,
        video_slice_path: str,
        audio_segment_path: str,
        duration_sec: float,
        output_rendered_path: str,
        face_frame_path: Optional[str] = None,
        model_preference: str = "liveportrait",
    ) -> str:
        """
        Submits video segment and retimed audio to Replicate LivePortrait / Wav2Lip.
        Downloads rendered synchronized MP4 video to output_rendered_path.
        """
        os.makedirs(os.path.dirname(output_rendered_path), exist_ok=True)

        if not self.api_token or "test" in self.api_token or "placeholder" in self.api_token:
            return await self._generate_mock_synced_video(video_slice_path, audio_segment_path, output_rendered_path)

        # 1. Upload assets to temporary S3 storage to obtain public/presigned URLs for Replicate
        temp_id = uuid.uuid4().hex
        audio_s3_key = f"tmp_lipsync/{temp_id}_audio.wav"
        video_s3_key = f"tmp_lipsync/{temp_id}_video.mp4"

        await storage_service.upload_file(audio_segment_path, audio_s3_key, mime_type="audio/wav")
        await storage_service.upload_file(video_slice_path, video_s3_key, mime_type="video/mp4")

        audio_url = storage_service.generate_presigned_download_url(audio_s3_key, expires_in_seconds=3600)
        video_url = storage_service.generate_presigned_download_url(video_s3_key, expires_in_seconds=3600)

        # 2. Run Replicate prediction
        rendered_url = None
        try:
            if model_preference == "liveportrait":
                input_params = replicate_utils.build_liveportrait_input(
                    image_or_video_url=video_url,
                    audio_url=audio_url,
                    duration_sec=duration_sec,
                    face_expand_ratio=settings.LIPSYNC_FACE_EXPAND_RATIO,
                )
                output = await asyncio.to_thread(replicate.run, self.liveportrait_model, input=input_params)
                rendered_url = str(output)
            else:
                input_params = replicate_utils.build_wav2lip_input(
                    face_video_url=video_url,
                    audio_url=audio_url,
                    smooth=True,
                )
                output = await asyncio.to_thread(replicate.run, self.wav2lip_model, input=input_params)
                rendered_url = str(output)

        except Exception as e:
            logger.warning(f"Primary model {model_preference} failed: {e}. Attempting Wav2Lip fallback...")
            try:
                input_params = replicate_utils.build_wav2lip_input(face_video_url=video_url, audio_url=audio_url, smooth=True)
                output = await asyncio.to_thread(replicate.run, self.wav2lip_model, input=input_params)
                rendered_url = str(output)
            except Exception as fb_err:
                logger.error(f"Fallback Wav2Lip failed: {fb_err}", exc_info=True)
                raise MediaAppException(
                    status_code=500,
                    error_code=ErrorCode.LIPSYNC_RENDER_FAILED,
                    message=f"Neural lip-sync synthesis failed: {str(fb_err)}",
                )

        # 3. Download rendered result video
        if rendered_url:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.get(rendered_url)
                if resp.status_code == 200:
                    with open(output_rendered_path, "wb") as f:
                        f.write(resp.content)
                    return output_rendered_path

        raise MediaAppException(
            status_code=500,
            error_code=ErrorCode.LIPSYNC_RENDER_FAILED,
            message="Failed to retrieve rendered video stream from Replicate.",
        )

    @staticmethod
    async def _generate_mock_synced_video(
        video_slice_path: str,
        audio_segment_path: str,
        output_path: str,
    ) -> str:
        """Merges input video slice with retimed audio for local offline testing."""
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_slice_path,
            "-i", audio_segment_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()

        if not os.path.exists(output_path):
            with open(output_path, "wb") as f:
                f.write(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mock_video_bytes")

        return output_path


replicate_lipsync = ReplicateLipSync()

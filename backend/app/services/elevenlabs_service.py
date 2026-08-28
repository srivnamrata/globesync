import asyncio
import io
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple
import httpx
from app.core.config import settings
from app.utils.error_codes import ErrorCode, MediaAppException

logger = logging.getLogger("elevenlabs_service")


class ElevenLabsTTS:
    """ElevenLabs Multilingual Voice Cloning & Text-to-Speech API Client."""

    def __init__(self):
        self.api_key = settings.ELEVENLABS_API_KEY
        self.base_url = "https://api.elevenlabs.io/v1"
        self.default_model = settings.ELEVENLABS_MODEL_ID
        self.default_voice_id = settings.ELEVENLABS_DEFAULT_VOICE_ID

    async def create_instant_voice_clone(
        self,
        name: str,
        sample_audio_file_paths: List[str],
        description: str = "Cloned speaker voice for automated dubbing",
        labels: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Creates an instant voice clone via ElevenLabs /v1/voices/add.
        Returns the external elevenlabs voice_id.
        """
        api_key = (self.api_key or "").strip()
        looks_mock = (not api_key) or ("placeholder" in api_key.lower()) or ("test" in api_key.lower())
        if looks_mock:
            if settings.DEPLOYMENT_ENV == "development":
                # Generate deterministic mock voice ID for testing
                return f"mock_voice_{uuid.uuid4().hex[:12]}"
            raise MediaAppException(
                status_code=503,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="ElevenLabs API key is not configured for production voice cloning.",
            )

        url = f"{self.base_url}/voices/add"
        headers = {"xi-api-key": self.api_key}

        # Build multipart files list
        files = []
        try:
            for p in sample_audio_file_paths:
                if os.path.exists(p):
                    files.append(("files", (os.path.basename(p), open(p, "rb"), "audio/wav")))

            data = {
                "name": name[:50],
                "description": description,
                "labels": str(labels or {"source": "translation_platform"}),
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, headers=headers, data=data, files=files)

                if response.status_code != 200:
                    logger.error(f"ElevenLabs voice add failed: {response.text}")
                    raise MediaAppException(
                        status_code=response.status_code,
                        error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                        message="Failed to create ElevenLabs voice clone.",
                        details={"response_text": response.text},
                    )

                result = response.json()
                return result["voice_id"]

        finally:
            for _, f_tuple in files:
                f_tuple[1].close()

    async def synthesize_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        output_file_path: Optional[str] = None,
        model_id: Optional[str] = None,
        voice_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Synthesizes text into multilingual speech audio.
        Saves output audio file to disk and returns its path.
        """
        target_voice = voice_id or self.default_voice_id
        target_model = model_id or self.default_model

        if not output_file_path:
            output_file_path = os.path.join(
                settings.PROCESSED_MEDIA_DIR, f"tts_{uuid.uuid4().hex}.wav"
            )
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

        api_key = (self.api_key or "").strip()
        looks_mock = (not api_key) or ("placeholder" in api_key.lower()) or ("test" in api_key.lower())
        if looks_mock:
            if settings.DEPLOYMENT_ENV == "development":
                # Generate synthetic mock audio using FFmpeg sine wave for testing
                return await self._generate_mock_audio(text, output_file_path)
            raise MediaAppException(
                status_code=503,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="ElevenLabs API key is not configured for production TTS.",
            )

        url = f"{self.base_url}/text-to-speech/{target_voice}?output_format=pcm_24000"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        v_settings = voice_settings or {
            "stability": settings.ELEVENLABS_STABILITY,
            "similarity_boost": settings.ELEVENLABS_SIMILARITY_BOOST,
            "style": settings.ELEVENLABS_STYLE,
            "use_speaker_boost": settings.ELEVENLABS_USE_SPEAKER_BOOST,
        }

        payload = {
            "text": text,
            "model_id": target_model,
            "voice_settings": v_settings,
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                logger.error(f"ElevenLabs TTS failed: {response.text}")
                # Fallback to default voice if custom voice failed
                if target_voice != self.default_voice_id:
                    logger.warning(f"Retrying TTS with default voice {self.default_voice_id}")
                    return await self.synthesize_speech(
                        text=text,
                        voice_id=self.default_voice_id,
                        output_file_path=output_file_path,
                        model_id=target_model,
                    )
                raise MediaAppException(
                    status_code=response.status_code,
                    error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                    message="ElevenLabs TTS synthesis failed.",
                    details={"error": response.text},
                )

            # Write raw PCM audio converted to standard 16kHz WAV
            raw_pcm = response.content
            # Convert raw 24kHz PCM to 16kHz WAV via FFmpeg
            temp_pcm_path = f"{output_file_path}.pcm"
            with open(temp_pcm_path, "wb") as f:
                f.write(raw_pcm)

            cmd = [
                "ffmpeg",
                "-y",
                "-f", "s16le",
                "-ar", "24000",
                "-ac", "1",
                "-i", temp_pcm_path,
                "-ar", "16000",
                output_file_path,
            ]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()

            if os.path.exists(temp_pcm_path):
                os.remove(temp_pcm_path)

            return output_file_path

    @staticmethod
    async def _generate_mock_audio(text: str, output_wav_path: str) -> str:
        """Generates clean test audio of approximate duration based on word count."""
        words = len(text.split())
        duration_sec = max(0.5, round(words * 0.35, 2))

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={duration_sec}",
            "-ar", "16000",
            "-ac", "1",
            output_wav_path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()
        except Exception:
            # If ffmpeg binary missing in test runner, write dummy file
            with open(output_wav_path, "wb") as f:
                f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

        return output_wav_path


elevenlabs_tts = ElevenLabsTTS()

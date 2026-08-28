import asyncio
import logging
import os
import uuid
from typing import Dict, List, Optional
from app.core.config import settings
from app.models.generated_audio import GeneratedAudio
from app.models.translation import Translation
from app.models.voice_profile import VoiceProfile
from app.services.audio_postprocessor import audio_postprocessor
from app.services.elevenlabs_service import elevenlabs_tts
from app.services.google_tts_service import google_tts_service
from app.services.storage_service import storage_service
from app.utils.audio_matcher import audio_matcher

logger = logging.getLogger("tts_orchestrator")


class TTSOrchestrator:
    """Orchestrates TTS speech synthesis, duration retiming, S3 upload, and master audio timeline mixing."""

    @classmethod
    async def synthesize_single_translation(
        cls,
        translation: Translation,
        voice_profile: Optional[VoiceProfile] = None,
    ) -> GeneratedAudio:
        """
        Synthesizes translated speech, retimes audio with FFmpeg to match target duration (±100ms),
        and uploads the final audio snippet to storage.
        """
        temp_dir = settings.PROCESSED_MEDIA_DIR
        raw_tts_path = os.path.join(temp_dir, f"raw_tts_{translation.id.hex}.wav")
        retimed_path = os.path.join(temp_dir, f"retimed_{translation.id.hex}.wav")

        voice_id = voice_profile.external_voice_id if voice_profile else settings.ELEVENLABS_DEFAULT_VOICE_ID
        voice_settings = voice_profile.voice_settings if voice_profile else None

        # 1. Synthesize raw TTS speech
        if settings.TTS_PROVIDER == "google":
            await google_tts_service.synthesize_speech(
                text=translation.translated_text,
                language_code=translation.target_language,
                output_file_path=raw_tts_path,
            )
        else:
            await elevenlabs_tts.synthesize_speech(
                text=translation.translated_text,
                voice_id=voice_id,
                output_file_path=raw_tts_path,
                voice_settings=voice_settings,
            )

        # 2. Measure actual duration
        actual_dur_ms = await audio_postprocessor.get_audio_duration_ms(raw_tts_path)
        target_dur_ms = translation.original_duration_ms

        # 3. Calculate speed adjustment factor
        speed_factor, delta_ms = audio_matcher.calculate_retiming_factor(
            actual_duration_ms=actual_dur_ms,
            target_duration_ms=target_dur_ms,
        )

        # 4. Retime with FFmpeg atempo and normalize to -20 LUFS
        await audio_postprocessor.retime_and_normalize_segment(
            input_audio_path=raw_tts_path,
            output_audio_path=retimed_path,
            speed_factor=speed_factor,
            target_duration_ms=target_dur_ms,
        )

        retimed_dur_ms = await audio_postprocessor.get_audio_duration_ms(retimed_path)

        # 5. Upload to S3 / Object Store
        storage_key = f"tts_segments/{str(translation.project_id or 'default')}/{translation.id.hex}.wav"
        await storage_service.upload_file(
            file_path=retimed_path,
            key=storage_key,
            mime_type="audio/wav",
        )

        # Cleanup local temp files
        for p in [raw_tts_path, retimed_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        return GeneratedAudio(
            translation_id=translation.id,
            voice_profile_id=voice_profile.id if voice_profile else None,
            project_id=translation.project_id,
            storage_bucket=settings.GCS_BUCKET_NAME,
            storage_path=storage_key,
            raw_tts_duration_ms=actual_dur_ms,
            target_duration_ms=target_dur_ms,
            retimed_duration_ms=retimed_dur_ms,
            speed_adjustment_factor=speed_factor,
            pitch_adjustment_semitones=0.00,
            status="ready",
            is_retimed=True,
            quality_score=0.9800,
        )

    @classmethod
    async def synthesize_batch_concurrent(
        cls,
        translations: List[Translation],
        voice_profiles_by_speaker: Dict[str, VoiceProfile],
        concurrency: int = 10,
    ) -> List[GeneratedAudio]:
        """Synthesizes multiple translation segments concurrently using a semaphore."""
        semaphore = asyncio.Semaphore(concurrency)

        async def _worker(t: Translation) -> GeneratedAudio:
            async with semaphore:
                speaker_tag = getattr(t.segment, "speaker_tag", "Speaker 1") if hasattr(t, "segment") and t.segment else "Speaker 1"
                v_profile = voice_profiles_by_speaker.get(speaker_tag)
                return await cls.synthesize_single_translation(t, v_profile)

        tasks = [_worker(t) for t in translations]
        return await asyncio.gather(*tasks)


tts_orchestrator = TTSOrchestrator()

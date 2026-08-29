import asyncio
import os
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.transcript import TranscriptSegment
from app.models.voice_profile import VoiceProfile
from app.services.audio_extraction_service import audio_extractor
from app.services.elevenlabs_service import elevenlabs_tts
from app.services.storage_service import storage_service
from app.utils.prosody_extractor import prosody_extractor


class VoiceCloningService:
    """Extracts speaker audio samples, builds prosody profiles, and creates ElevenLabs voice clones."""

    @classmethod
    async def clone_speaker_from_segments(
        cls,
        master_audio_path: str,
        speaker_tag: str,
        segments: List[TranscriptSegment],
        project_id: Optional[uuid.UUID] = None,
        organization_id: Optional[uuid.UUID] = None,
    ) -> VoiceProfile:
        """
        Gathers 30-90s of speech from the highest confidence segments for a speaker,
        creates an ElevenLabs voice clone, and persists the VoiceProfile record.
        """
        # Filter segments belonging to this speaker with duration >= 1.0s
        speaker_segs = [s for s in segments if s.speaker_tag == speaker_tag and float(s.duration_seconds) >= 1.0]
        # Sort by confidence descending
        speaker_segs.sort(key=lambda s: float(s.confidence or 0.9), reverse=True)

        if not speaker_segs:
            # Fallback to all segments if none strictly matched
            speaker_segs = segments[:3]

        # Accumulate up to 60 seconds of samples
        selected_slices: List[str] = []
        total_duration = 0.0
        temp_dir = settings.PROCESSED_MEDIA_DIR

        for idx, seg in enumerate(speaker_segs):
            if total_duration >= 60.0:
                break
            dur = float(seg.duration_seconds)
            slice_path = os.path.join(temp_dir, f"sample_{uuid.uuid4().hex}_{idx}.wav")
            await audio_extractor.extract_audio_segment(
                audio_input_path=master_audio_path,
                start_seconds=float(seg.start_time_seconds),
                duration_seconds=dur,
                output_segment_path=slice_path,
            )
            selected_slices.append(slice_path)
            total_duration += dur

        # Concatenate into master reference sample
        reference_sample_local = os.path.join(temp_dir, f"voice_ref_{uuid.uuid4().hex}.wav")
        if len(selected_slices) == 1:
            os.replace(selected_slices[0], reference_sample_local)
        elif selected_slices:
            concat_list_file = f"{reference_sample_local}.txt"
            with open(concat_list_file, "w") as f:
                for s in selected_slices:
                    f.write(f"file '{s}'\n")
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_file, "-c", "copy", reference_sample_local]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()
            if os.path.exists(concat_list_file):
                os.remove(concat_list_file)
            for s in selected_slices:
                if os.path.exists(s):
                    os.remove(s)
        else:
            reference_sample_local = master_audio_path

        # Extract Prosody Features
        prosody_data = prosody_extractor.extract_prosody_features(reference_sample_local)
        recommended_settings = prosody_data.get("recommended_voice_settings", {})

        # Upload reference sample to S3/GCS
        sample_storage_key = f"voice_profiles/{uuid.uuid4().hex}/{speaker_tag.lower().replace(' ', '_')}.wav"
        if os.path.exists(reference_sample_local):
            await storage_service.upload_file(
                file_path=reference_sample_local,
                key=sample_storage_key,
                mime_type="audio/wav",
            )

        # Create ElevenLabs Voice Clone
        speaker_display_name = f"{speaker_tag} (Project {str(project_id)[:8] if project_id else 'Default'})"
        external_voice_id = await elevenlabs_tts.create_instant_voice_clone(
            name=speaker_display_name,
            sample_audio_file_paths=[reference_sample_local],
            description=f"Cloned voice profile for {speaker_tag}",
            labels={"speaker": speaker_tag, "project_id": str(project_id or "")},
        )

        voice_profile = VoiceProfile(
            organization_id=organization_id,
            project_id=project_id,
            speaker_name=speaker_tag,
            language="en",
            external_provider="elevenlabs",
            external_voice_id=external_voice_id,
            reference_sample_gcs_path=sample_storage_key,
            reference_sample_duration_sec=round(total_duration, 2),
            embedding_vector=prosody_data,
            voice_settings=recommended_settings,
            confidence_score=0.9600,
            is_active=True,
        )

        return voice_profile


voice_cloning_service = VoiceCloningService()

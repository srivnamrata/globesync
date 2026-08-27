import asyncio
import json
import logging
import os
import time
import uuid
from typing import Optional
from celery import shared_task
import redis
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker, joinedload
from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.generated_audio import GeneratedAudio
from app.models.media import MediaFile
from app.models.transcript import Transcript, TranscriptSegment
from app.models.translation import Translation
from app.models.voice_profile import VoiceProfile
from app.services.audio_postprocessor import audio_postprocessor
from app.services.storage_service import storage_service
from app.services.tts_orchestrator import tts_orchestrator
from app.services.voice_cloning_service import voice_cloning_service

logger = logging.getLogger("tts_tasks")
sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
SyncSession = sessionmaker(bind=sync_engine)


def publish_tts_event(project_id: str, status: str, progress_percent: int, message: str):
    """Broadcasts real-time TTS synthesis and retiming progress to Redis Pub/Sub."""
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        event_payload = json.dumps({
            "project_id": project_id,
            "status": status,
            "progress_percent": progress_percent,
            "message": message,
            "timestamp": time.time(),
        })
        r.publish(f"events:tts:{project_id}", event_payload)
    except Exception as e:
        logger.warning(f"Failed to publish Redis TTS event: {e}")


def run_project_tts_pipeline(
    transcript_id_str: str,
    target_language: str,
    project_id_str: Optional[str] = None,
    task_instance=None,
):
    """
    Asynchronous Celery task:
    1. Loads translated segments
    2. Clones speaker voices from original media if needed
    3. Concurrently synthesizes TTS speech for all segments
    4. Retimes audio segments (atempo) to match exact video timestamps (±100ms)
    5. Assembles master dubbed audio track
    6. Broadcasts real-time progress events
    """
    transcript_id = uuid.UUID(transcript_id_str)
    project_id = uuid.UUID(project_id_str) if project_id_str else None
    start_time = time.time()

    publish_tts_event(project_id_str or transcript_id_str, "in_progress", 10, "Initializing TTS speech synthesis pipeline...")

    db: Session = SyncSession()
    try:
        transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()
        if not transcript:
            raise ValueError("Transcript not found.")

        media_file = db.query(MediaFile).filter(MediaFile.id == transcript.media_file_id).first()
        if not media_file:
            raise ValueError("Associated MediaFile not found.")

        # Load segments with their translations
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.sequence_order)
            .all()
        )

        segment_ids = [s.id for s in segments]
        translations = (
            db.query(Translation)
            .options(joinedload(Translation.segment))
            .filter(
                Translation.transcript_segment_id.in_(segment_ids),
                Translation.target_language == target_language,
            )
            .all()
        )

        if not translations:
            raise ValueError(f"No translations found for target language {target_language}")

        translation_ids = [t.id for t in translations]
        if translation_ids:
            db.query(GeneratedAudio).filter(GeneratedAudio.translation_id.in_(translation_ids)).delete(synchronize_session=False)
            db.commit()

        # Step 1: Voice Cloning / Speaker Profile Association
        publish_tts_event(project_id_str or transcript_id_str, "in_progress", 25, "Extracting speaker embeddings and voice clone profiles...")
        
        # Download master audio for voice sample extraction
        temp_dir = settings.PROCESSED_MEDIA_DIR
        local_master_audio = os.path.join(temp_dir, f"master_{media_file.id.hex}.wav")
        asyncio.run(storage_service.download_file(media_file.storage_path, local_master_audio))

        distinct_speakers = list(set(s.speaker_tag for s in segments))
        voice_profiles_by_speaker = {}

        for spk in distinct_speakers:
            # Check if voice profile already exists
            vp = (
                db.query(VoiceProfile)
                .filter(VoiceProfile.speaker_name == spk, VoiceProfile.project_id == project_id)
                .first()
            )
            if not vp:
                vp = asyncio.run(
                    voice_cloning_service.clone_speaker_from_segments(
                        master_audio_path=local_master_audio,
                        speaker_tag=spk,
                        segments=segments,
                        project_id=project_id,
                    )
                )
                db.add(vp)
                db.commit()
                db.refresh(vp)
            voice_profiles_by_speaker[spk] = vp

        # Step 2: Concurrent TTS Synthesis & Retiming
        publish_tts_event(
            project_id_str or transcript_id_str,
            "in_progress",
            50,
            f"Synthesizing speech and retiming {len(translations)} segments with ElevenLabs...",
        )

        generated_audios = asyncio.run(
            tts_orchestrator.synthesize_batch_concurrent(
                translations=translations,
                voice_profiles_by_speaker=voice_profiles_by_speaker,
                concurrency=10,
            )
        )

        # Persist GeneratedAudio rows
        for ga in generated_audios:
            db.add(ga)
        db.commit()

        # Step 3: Assemble Master Dubbed Timeline Track
        publish_tts_event(
            project_id_str or transcript_id_str,
            "in_progress",
            85,
            "Mixing master dubbed audio timeline...",
        )

        # Download retimed segments to assemble master
        timeline_items = []
        downloaded_local_segments = []
        for ga in generated_audios:
            t = next(tr for tr in translations if tr.id == ga.translation_id)
            seg = t.segment
            local_seg_path = os.path.join(temp_dir, f"loc_{ga.id.hex}.wav")
            asyncio.run(storage_service.download_file(ga.storage_path, local_seg_path))
            downloaded_local_segments.append(local_seg_path)
            timeline_items.append({
                "audio_path": local_seg_path,
                "start_sec": float(seg.start_time_seconds),
            })

        master_dubbed_local = os.path.join(temp_dir, f"master_dubbed_{transcript_id.hex}_{target_language}.wav")
        total_duration = float(media_file.duration_seconds)

        asyncio.run(
            audio_postprocessor.assemble_master_dubbed_timeline(
                segments_data=timeline_items,
                total_duration_sec=total_duration,
                output_master_path=master_dubbed_local,
            )
        )

        # Upload master dubbed track
        master_storage_key = f"master_dubbed/{project_id_str or transcript_id_str}/{target_language}_dubbed.wav"
        asyncio.run(
            storage_service.upload_file(
                file_path=master_dubbed_local,
                key=master_storage_key,
                mime_type="audio/wav",
            )
        )

        # Cleanup local scratch files
        for p in downloaded_local_segments + [local_master_audio, master_dubbed_local]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        execution_dur = round(time.time() - start_time, 2)
        publish_tts_event(
            project_id_str or transcript_id_str,
            "completed",
            100,
            f"Master dubbed audio generated successfully in {execution_dur}s.",
        )

        return {
            "status": "completed",
            "project_id": project_id_str,
            "target_language": target_language,
            "master_audio_path": master_storage_key,
            "segments_synthesized": len(generated_audios),
            "execution_duration_sec": execution_dur,
        }

    except Exception as exc:
        db.rollback()
        logger.error(f"Error in TTS synthesis pipeline: {exc}", exc_info=True)
        publish_tts_event(project_id_str or transcript_id_str, "failed", 0, f"TTS Synthesis failed: {str(exc)}")
        if task_instance is not None:
            raise task_instance.retry(exc=exc)
        raise

    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.tasks.tts_tasks.synthesize_project_tts_task",
    max_retries=3,
    default_retry_delay=10,
)
def synthesize_project_tts_task(
    self,
    transcript_id_str: str,
    target_language: str,
    project_id_str: Optional[str] = None,
):
    """Celery wrapper around the shared project TTS pipeline implementation."""
    return run_project_tts_pipeline(
        transcript_id_str=transcript_id_str,
        target_language=target_language,
        project_id_str=project_id_str,
        task_instance=self,
    )

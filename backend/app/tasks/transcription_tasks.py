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
from sqlalchemy.orm import Session, sessionmaker
from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.media import MediaFile
from app.models.transcript import Transcript, TranscriptSegment
from app.services.audio_extraction_service import audio_extractor
from app.services.audio_preprocessing_service import audio_preprocessor
from app.services.deepgram_service import deepgram_stt
from app.services.google_stt_service import google_stt_service
from app.services.storage_service import storage_service
from app.utils.transcript_parser import transcript_parser

logger = logging.getLogger("transcription_tasks")
sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
SyncSession = sessionmaker(bind=sync_engine)


def publish_progress_event(media_id: str, transcript_id: str, status: str, progress_percent: int, message: str):
    """Broadcasts live progress to Redis Pub/Sub for SSE/WebSocket subscribers."""
    if not settings.REDIS_URL:
        return
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        event_payload = json.dumps({
            "media_id": media_id,
            "transcript_id": transcript_id,
            "status": status,
            "progress_percent": progress_percent,
            "message": message,
            "timestamp": time.time(),
        })
        r.publish(f"events:project:{media_id}", event_payload)
        r.publish(f"events:transcript:{transcript_id}", event_payload)
    except Exception as e:
        logger.warning(f"Failed to publish Redis progress event: {e}")


def run_transcription_pipeline(
    media_id_str: str,
    transcript_id_str: str,
    language: Optional[str] = None,
    max_speakers: Optional[int] = None,
    enable_noise_reduction: bool = True,
    enable_loudness_norm: bool = True,
    request_id: Optional[str] = None,
    task_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    source_action: str = "transcription_pipeline",
):
    """
    Core asynchronous transcription pipeline implementation shared by Celery
    workers and Cloud Tasks-triggered in-process execution.
    """
    media_id = uuid.UUID(media_id_str)
    transcript_id = uuid.UUID(transcript_id_str)
    request_id = request_id or transcript_id_str
    idempotency_key = idempotency_key or f"transcribe:{media_id_str}:{transcript_id_str}"
    start_time = time.time()

    local_temp_video = os.path.join(settings.TEMP_UPLOAD_DIR, f"{media_id.hex}_raw.media")
    extracted_wav = os.path.join(settings.PROCESSED_MEDIA_DIR, f"{media_id.hex}_raw.wav")
    preprocessed_wav = os.path.join(settings.PROCESSED_MEDIA_DIR, f"{media_id.hex}_clean.wav")

    publish_progress_event(media_id_str, transcript_id_str, "in_progress", 10, "Downloading media file from object storage...")

    db: Session = SyncSession()
    try:
        media_file = db.query(MediaFile).filter(MediaFile.id == media_id).first()
        transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()

        if not media_file or not transcript:
            raise ValueError("Media file or transcript record not found in database.")

        transcript.status = "in_progress"
        db.commit()

        # Step 1: Download media file
        asyncio.run(storage_service.download_file(media_file.storage_path, local_temp_video))

        # Step 2: Extract audio
        publish_progress_event(media_id_str, transcript_id_str, "in_progress", 30, "Extracting audio stream with FFmpeg...")
        asyncio.run(audio_extractor.extract_audio_for_stt(local_temp_video, extracted_wav))

        # Step 3: Preprocess audio (Noise reduction + Loudness normalization)
        publish_progress_event(media_id_str, transcript_id_str, "in_progress", 50, "Applying noise reduction and loudness normalization (-20 LUFS)...")
        asyncio.run(
            audio_preprocessor.preprocess_audio_pipeline(
                extracted_wav,
                preprocessed_wav,
                apply_noise_reduction=enable_noise_reduction,
                apply_loudness_norm=enable_loudness_norm,
            )
        )

        # Step 4: Chunking for long files if duration > 20 mins
        duration = float(media_file.duration_seconds)
        chunks = asyncio.run(audio_preprocessor.split_audio_into_chunks_if_needed(preprocessed_wav, duration))

        all_segments = []
        full_transcript_parts = []
        total_word_count = 0
        total_conf_sum = 0.0
        all_speaker_tags = set()
        raw_responses = []

        primary_provider = settings.STT_PRIMARY_PROVIDER.lower().strip()
        fallback_provider = settings.STT_FALLBACK_PROVIDER.lower().strip()
        provider_label = "Google Cloud Speech-to-Text"
        if primary_provider == "deepgram":
            provider_label = "Deepgram Nova-2"
        publish_progress_event(media_id_str, transcript_id_str, "in_progress", 70, f"Executing {provider_label} transcription with fallback protection...")

        for chunk_path, time_offset, chunk_dur in chunks:
            active_provider = primary_provider
            stt_response = None

            try:
                if primary_provider == "google":
                    stt_response = asyncio.run(
                        google_stt_service.transcribe_audio_file(
                            audio_file_path=chunk_path,
                            language=language,
                            max_speakers=max_speakers,
                            duration_seconds=chunk_dur,
                        )
                    )
                elif primary_provider == "deepgram":
                    stt_response = asyncio.run(
                        deepgram_stt.transcribe_audio_file(
                            audio_file_path=chunk_path,
                            language=language,
                            max_speakers=max_speakers,
                        )
                    )
                else:
                    raise ValueError(f"Unsupported STT primary provider: {primary_provider}")
            except Exception as primary_exc:
                if fallback_provider == primary_provider:
                    raise
                logger.warning(
                    "Primary STT provider %s failed for chunk %s; attempting fallback provider %s",
                    primary_provider,
                    chunk_path,
                    fallback_provider,
                    exc_info=True,
                )
                if fallback_provider == "deepgram":
                    stt_response = asyncio.run(
                        deepgram_stt.transcribe_audio_file(
                            audio_file_path=chunk_path,
                            language=language,
                            max_speakers=max_speakers,
                        )
                    )
                    active_provider = "deepgram"
                elif fallback_provider == "google":
                    stt_response = asyncio.run(
                        google_stt_service.transcribe_audio_file(
                            audio_file_path=chunk_path,
                            language=language,
                            max_speakers=max_speakers,
                        )
                    )
                    active_provider = "google"
                else:
                    raise primary_exc

            raw_responses.append({"provider": active_provider, "payload": stt_response})

            if active_provider == "google":
                seg_list, text_part, avg_conf, w_cnt, spk_cnt = transcript_parser.parse_google_response(
                    stt_response, time_offset_seconds=time_offset
                )
            else:
                seg_list, text_part, avg_conf, w_cnt, spk_cnt = transcript_parser.parse_deepgram_response(
                    stt_response, time_offset_seconds=time_offset
                )

            all_segments.extend(seg_list)
            if text_part:
                full_transcript_parts.append(text_part)
            total_word_count += w_cnt
            total_conf_sum += avg_conf * max(1, w_cnt)
            for s in seg_list:
                all_speaker_tags.add(s.speaker)

        overall_avg_conf = (
            round(total_conf_sum / max(1, total_word_count), 4)
            if total_word_count > 0
            else 0.96
        )
        consolidated_text = "\n\n".join(full_transcript_parts)
        speaker_count = len(all_speaker_tags) if all_speaker_tags else 1

        # Step 5: Save Segments and Words to DB
        publish_progress_event(media_id_str, transcript_id_str, "in_progress", 90, "Saving normalized segments and timestamps...")

        # Clear existing segments if any
        db.query(TranscriptSegment).filter(TranscriptSegment.transcript_id == transcript.id).delete()

        for idx, seg in enumerate(all_segments):
            segment_row = TranscriptSegment(
                transcript_id=transcript.id,
                speaker_tag=seg.speaker,
                start_time_seconds=seg.start_time,
                end_time_seconds=seg.end_time,
                duration_seconds=seg.duration,
                text=seg.text,
                confidence=seg.confidence,
                words=[w.model_dump() for w in seg.words],
                sequence_order=idx,
                origin_type="machine_generated",
                source_action=source_action,
            )
            db.add(segment_row)

        transcript.full_text = consolidated_text
        transcript.word_count = total_word_count
        transcript.speaker_count = speaker_count
        transcript.confidence_score = overall_avg_conf
        transcript.detected_language = language or "en"
        transcript.raw_response = {
            "chunks": raw_responses,
            "correlation": {
                "request_id": request_id,
                "task_id": task_id,
                "idempotency_key": idempotency_key,
                "source_action": source_action,
            },
        }
        transcript.status = "completed"
        transcript.processing_duration_seconds = round(time.time() - start_time, 2)
        db.commit()

        publish_progress_event(media_id_str, transcript_id_str, "completed", 100, "Transcription and diarization completed successfully.")
        return {"status": "completed", "transcript_id": transcript_id_str, "segments": len(all_segments)}

    except Exception as exc:
        db.rollback()
        logger.error(f"Error in transcription pipeline for media {media_id_str}: {exc}", exc_info=True)
        if 'transcript' in locals() and transcript:
            transcript.status = "failed"
            transcript.error_message = str(exc)
            db.commit()

        publish_progress_event(media_id_str, transcript_id_str, "failed", 0, f"Transcription failed: {str(exc)}")
        raise

    finally:
        db.close()
        # Clean up local temporary media files
        for p in [local_temp_video, extracted_wav, preprocessed_wav]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@celery_app.task(
    bind=True,
    name="app.tasks.transcription_tasks.preprocess_and_transcribe_pipeline_task",
    max_retries=3,
    default_retry_delay=10,
)
def preprocess_and_transcribe_pipeline_task(
    self,
    media_id_str: str,
    transcript_id_str: str,
    language: Optional[str] = None,
    max_speakers: Optional[int] = None,
    enable_noise_reduction: bool = True,
    enable_loudness_norm: bool = True,
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    source_action: str = "transcription_pipeline_celery",
):
    """Celery wrapper around the shared transcription pipeline implementation."""
    try:
        return run_transcription_pipeline(
            media_id_str=media_id_str,
            transcript_id_str=transcript_id_str,
            language=language,
            max_speakers=max_speakers,
            enable_noise_reduction=enable_noise_reduction,
            enable_loudness_norm=enable_loudness_norm,
            request_id=request_id,
            task_id=self.request.id,
            idempotency_key=idempotency_key,
            source_action=source_action,
        )
    except Exception as exc:
        raise self.retry(exc=exc)

import asyncio
import json
import logging
import time
import uuid
from typing import Optional
from celery import shared_task
import redis
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.transcript import Transcript, TranscriptSegment
from app.models.translation import Translation
from app.services.pipeline_operation_service import checkpoint_operation
from app.services.translation_service import translation_service

logger = logging.getLogger("translation_tasks")
sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
SyncSession = sessionmaker(bind=sync_engine)


def publish_translation_event(transcript_id: str, status: str, progress_percent: int, message: str):
    """Broadcasts live translation progress to Redis Pub/Sub."""
    if not settings.REDIS_URL:
        return
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        event_payload = json.dumps({
            "transcript_id": transcript_id,
            "status": status,
            "progress_percent": progress_percent,
            "message": message,
            "timestamp": time.time(),
        })
        r.publish(f"events:translation:{transcript_id}", event_payload)
    except Exception as e:
        logger.warning(f"Failed to publish Redis translation event: {e}")


@celery_app.task(
    bind=True,
    name="app.tasks.translation_tasks.translate_project_batch_task",
    max_retries=3,
    default_retry_delay=10,
)
def translate_project_batch_task(
    self,
    transcript_id_str: str,
    source_language: str,
    target_language: str,
    project_id_str: Optional[str] = None,
    workspace_id_str: Optional[str] = None,
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    operation_id: Optional[str] = None,
):
    """
    Asynchronous Celery batch task:
    1. Loads transcript segments
    2. Runs parallel GPT-4o translation with ±10% duration matching
    3. Persists Translation records to PostgreSQL
    4. Streams real-time progress events
    """
    transcript_id = uuid.UUID(transcript_id_str)
    project_id = uuid.UUID(project_id_str) if project_id_str else None
    workspace_id = uuid.UUID(workspace_id_str) if workspace_id_str else None
    task_id = getattr(getattr(self, "request", None), "id", None)
    request_id = request_id or task_id or transcript_id_str
    idempotency_key = idempotency_key or f"translate-project:{transcript_id_str}:{target_language}"
    start_time = time.time()

    publish_translation_event(transcript_id_str, "in_progress", 10, "Loading transcript segments for translation...")

    db: Session = SyncSession()
    try:
        checkpoint_operation(db, operation_id, status="in_progress", stage="translate", progress_percent=10, message="Loading transcript segments")
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.sequence_order)
            .all()
        )

        if not segments:
            raise ValueError(f"No transcript segments found for transcript {transcript_id_str}")

        publish_translation_event(
            transcript_id_str,
            "in_progress",
            30,
            f"Translating {len(segments)} segments to {target_language} with duration matching...",
        )
        checkpoint_operation(db, operation_id, status="in_progress", stage="translate", progress_percent=30, message=f"Translating {len(segments)} segments")

        # Run async batch translation
        translated_entities = asyncio.run(
            translation_service.translate_segments_batch_async(
                segments=segments,
                source_language=source_language,
                target_language=target_language,
                project_id=project_id,
                workspace_id=workspace_id,
                request_id=request_id,
                task_id=task_id,
                source_action="translate_project_celery",
                idempotency_key_prefix=idempotency_key,
                concurrency_limit=10,
            )
        )

        publish_translation_event(transcript_id_str, "in_progress", 85, "Saving translated segments to database...")
        checkpoint_operation(db, operation_id, status="in_progress", stage="translate", progress_percent=85, message="Saving translated segments")

        # Delete any existing translations for these segments and target_language to prevent duplicates
        segment_ids = [s.id for s in segments]
        db.query(Translation).filter(
            Translation.transcript_segment_id.in_(segment_ids),
            Translation.target_language == target_language,
        ).delete(synchronize_session=False)

        for trans in translated_entities:
            db.add(trans)

        db.commit()
        checkpoint_operation(db, operation_id, status="completed", stage="translate", progress_percent=100, message=f"Translated {len(translated_entities)} segments", successful_stage="translate")

        duration = round(time.time() - start_time, 2)
        publish_translation_event(
            transcript_id_str,
            "completed",
            100,
            f"Successfully translated {len(translated_entities)} segments to {target_language} in {duration}s.",
        )

        return {
            "status": "completed",
            "transcript_id": transcript_id_str,
            "target_language": target_language,
            "segments_translated": len(translated_entities),
            "execution_duration_sec": duration,
        }

    except Exception as exc:
        db.rollback()
        logger.error(f"Error in batch translation task: {exc}", exc_info=True)
        checkpoint_operation(db, operation_id, status="failed", stage="translate", progress_percent=0, message="Translation failed", error_message=str(exc))
        publish_translation_event(transcript_id_str, "failed", 0, f"Translation failed: {str(exc)}")
        raise self.retry(exc=exc)

    finally:
        db.close()

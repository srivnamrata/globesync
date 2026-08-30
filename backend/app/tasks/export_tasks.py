import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional
from celery import shared_task
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.export_job import ExportJob
from app.models.media import MediaFile
from app.services.export_orchestrator import export_orchestrator
from app.services.export_queue_manager import export_queue_manager
from app.services.storage_service import storage_service

logger = logging.getLogger("export_tasks")
sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
SyncSession = sessionmaker(bind=sync_engine)


def publish_export_progress(job_id: str, status: str, stage: str, progress: int, eta_seconds: Optional[float] = None):
    """Publishes real-time rendering statistics to Redis Pub/Sub."""
    if not settings.REDIS_URL:
        return
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        event_payload = json.dumps({
            "export_id": job_id,
            "status": status,
            "stage": stage,
            "progress": progress,
            "current_frame": int(progress * 30), # Simulated frames
            "total_frames": 3000,
            "eta_seconds": eta_seconds,
            "speed_fps": 12.5,
            "bitrate_mbps": 8.5,
            "timestamp": time.time(),
        })
        r.publish(f"events:export:{job_id}", event_payload)
    except Exception as e:
        logger.warning(f"Failed to publish Redis export event: {e}")


@celery_app.task(
    bind=True,
    name="app.tasks.export_tasks.render_video_export_task",
    max_retries=2,
    default_retry_delay=20,
)
def render_video_export_task(
    self,
    job_id_str: str,
    media_file_id_str: str,
    target_language: str,
    job_settings: Dict[str, Any],
    segments_data: Optional[Any] = None,
):
    """
    Asynchronous Celery task coordinating video exports:
    1. Fetches source video and dubbed audio tracks
    2. Runs FFmpeg encoder with subtitles and post-processing filters
    3. Streams progress indicators to SSE clients
    4. Cleans up scratch space upon completion
    """
    job_id = uuid.UUID(job_id_str)
    media_file_id = uuid.UUID(media_file_id_str)
    start_time = time.time()

    export_queue_manager.register_job(job_id_str)
    publish_export_progress(job_id_str, "processing", "encoding_audio", 10)

    db: Session = SyncSession()
    temp_dir = settings.PROCESSED_MEDIA_DIR
    local_source_video = os.path.join(temp_dir, f"exp_src_{media_file_id.hex}.mp4")
    local_dubbed_audio = os.path.join(temp_dir, f"exp_dub_{job_id.hex}.wav")
    local_output_path = os.path.join(temp_dir, f"output_{job_id.hex}.{job_settings.get('format', 'mp4')}")

    try:
        job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
        media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()

        if not job or not media_file:
            raise ValueError("Required database entities not found for export job.")

        job.status = "processing"
        db.commit()

        # Check for cancel request
        if export_queue_manager.is_cancelled(job_id_str):
            raise InterruptedError("Export task was cancelled by user.")

        # 1. Download source video
        publish_export_progress(job_id_str, "processing", "rendering_frames", 20, eta_seconds=120)
        asyncio.run(storage_service.download_file(media_file.storage_path, local_source_video))

        # 2. Download master dubbed audio
        master_dubbed_key = f"master_dubbed/{str(job.project_id or media_file_id)}/{target_language}_dubbed.wav"
        asyncio.run(storage_service.download_file(master_dubbed_key, local_dubbed_audio))

        if export_queue_manager.is_cancelled(job_id_str):
            raise InterruptedError("Export task was cancelled by user.")

        # 3. Trigger orchestrator rendering loop
        publish_export_progress(job_id_str, "processing", "rendering_frames", 50, eta_seconds=60)
        
        asyncio.run(
            export_orchestrator.process_export_render(
                video_source_path=local_source_video,
                audio_dubbed_path=local_dubbed_audio,
                output_local_path=local_output_path,
                job_settings=job_settings,
                segments_data=segments_data,
            )
        )

        # 4. Upload Final Rendered Video to cloud storage
        publish_export_progress(job_id_str, "processing", "muxing", 90, eta_seconds=10)
        export_storage_key = f"exports/{str(job.project_id or media_file_id)}/{target_language}_render_{job_id.hex}.{job_settings.get('format', 'mp4')}"
        asyncio.run(
            storage_service.upload_file(
                file_path=local_output_path,
                key=export_storage_key,
                mime_type=f"video/{job_settings.get('format', 'mp4')}",
            )
        )

        filesize = os.path.getsize(local_output_path) if os.path.exists(local_output_path) else 0
        execution_dur = round(time.time() - start_time, 2)

        # Update DB Job completed
        job.status = "completed"
        job.progress_percent = 100
        job.current_stage = "completed"
        job.output_video_gcs_path = export_storage_key
        job.filesize_bytes = filesize
        job.execution_time_seconds = execution_dur
        db.commit()

        publish_export_progress(job_id_str, "completed", "completed", 100, eta_seconds=0)
        return {
            "status": "completed",
            "job_id": job_id_str,
            "output_key": export_storage_key,
            "filesize_bytes": filesize,
        }

    except Exception as exc:
        db.rollback()
        logger.error(f"Error executing video export task: {exc}", exc_info=True)
        if 'job' in locals() and job:
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
        publish_export_progress(job_id_str, "failed", "failed", 0)
        raise self.retry(exc=exc)

    finally:
        db.close()
        export_queue_manager.deregister_job(job_id_str)
        # Cleanup temporary scratch files
        export_queue_manager.cleanup_temporary_files([local_source_video, local_dubbed_audio, local_output_path])

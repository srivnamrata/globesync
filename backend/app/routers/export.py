import asyncio
import json
import uuid
from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.models.export_job import ExportJob
from app.models.media import MediaFile
from app.models.transcript import Transcript, TranscriptSegment
from app.schemas.export_schema import (
    ExportDispatchResponse,
    ExportJobResponse,
    ExportRequest,
)
from app.services.storage_service import storage_service
from app.services.pipeline_availability import require_background_pipelines
from app.services.export_queue_manager import export_queue_manager
from app.tasks.export_tasks import render_video_export_task

router = APIRouter(prefix="/export", tags=["Video Export & Rendering Hub"])


@router.post(
    "/render",
    response_model=ExportDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue Multi-Format Video Export Job",
)
async def enqueue_video_export(
    req: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    require_background_pipelines()
    """Enqueues rendering execution including watermarks, custom color-grades, soft/burnt subtitle layouts and audio normalization."""
    stmt = select(MediaFile).where(MediaFile.id == req.media_file_id)
    res = await db.execute(stmt)
    media = res.scalar_one_or_none()

    if not media:
        raise HTTPException(status_code=404, detail="Source media file not found.")

    # Fetch transcript segments to generate subtitles if subtitles enabled
    segments_payload = None
    if req.subtitles.enabled:
        seg_stmt = select(TranscriptSegment).where(TranscriptSegment.transcript_id == req.transcript_id)
        seg_res = await db.execute(seg_stmt)
        segments = seg_res.scalars().all()
        segments_payload = [
            {
                "start_sec": float(s.start_time_seconds),
                "end_sec": float(s.end_time_seconds),
                "duration_sec": float(s.duration_seconds),
                "speaker_tag": s.speaker_tag,
                "text": s.text,
            }
            for s in segments
        ]

    # Create ExportJob record
    job = ExportJob(
        project_id=req.project_id or media.project_id,
        media_file_id=req.media_file_id,
        transcript_id=req.transcript_id,
        target_language=req.target_language,
        format=req.format,
        resolution=req.resolution,
        frame_rate=req.frame_rate,
        codec=req.codec,
        video_quality=req.video_quality,
        audio_codec=req.audio_codec,
        subtitles_enabled=req.subtitles.enabled,
        subtitles_format=req.subtitles.format,
        subtitles_style=req.subtitles.appearance,
        color_grading=req.post_processing.color_grading,
        watermark_path=req.post_processing.watermark,
        audio_normalization=req.post_processing.audio_normalization,
        status="queued",
        progress_percent=0,
        current_stage="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Dispatch Celery render task
    render_video_export_task.apply_async(
        kwargs={
            "job_id_str": str(job.id),
            "media_file_id_str": str(req.media_file_id),
            "target_language": req.target_language,
            "job_settings": req.model_dump(),
            "segments_data": segments_payload,
        },
        queue="mux_export",
    )

    return ExportDispatchResponse(
        job_id=job.id,
        status="queued",
        message="Asynchronous video export job enqueued.",
    )


@router.get(
    "/job/{job_id}",
    response_model=ExportJobResponse,
    summary="Get Video Export Status",
)
async def get_export_job_status(
    job_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves current rendering logs, encoding speeds, ETA estimates, and downloadable visual URLs."""
    stmt = select(ExportJob).where(ExportJob.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Export job not found.")

    output_url = None
    if job.output_video_gcs_path:
        output_url = storage_service.generate_presigned_download_url(
            job.output_video_gcs_path, expires_in_seconds=7200
        )

    return ExportJobResponse(
        id=job.id,
        project_id=job.project_id,
        media_file_id=job.media_file_id,
        target_language=job.target_language,
        format=job.format,
        resolution=job.resolution,
        frame_rate=job.frame_rate,
        codec=job.codec,
        status=job.status,
        progress_percent=job.progress_percent,
        current_stage=job.current_stage,
        output_video_url=output_url,
        filesize_bytes=job.filesize_bytes,
        estimated_cost_usd=float(job.estimated_cost_usd),
        created_at=job.created_at,
    )


@router.post(
    "/job/{job_id}/cancel",
    summary="Cancel Visual Export Rendering Job",
)
async def cancel_export_job(
    job_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Signals cancellation to workers to immediately release GPU resources and clean up temp files."""
    stmt = select(ExportJob).where(ExportJob.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Export job not found.")

    export_queue_manager.cancel_job(str(job_id))
    job.status = "failed"
    job.error_message = "Export cancelled by user."
    await db.commit()

    return {"status": "cancelled", "job_id": job_id, "message": "Render task signal terminated."}


@router.get(
    "/history",
    response_model=List[ExportJobResponse],
    summary="Get Projects Rendering History List",
)
async def get_export_history(
    project_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves last 20 video render job logs and stats."""
    stmt = select(ExportJob).order_by(ExportJob.created_at.desc()).limit(20)
    if project_id:
        stmt = stmt.where(ExportJob.project_id == project_id)

    res = await db.execute(stmt)
    jobs = res.scalars().all()

    results = []
    for job in jobs:
        output_url = None
        if job.output_video_gcs_path:
            output_url = storage_service.generate_presigned_download_url(
                job.output_video_gcs_path, expires_in_seconds=7200
            )
        results.append(
            ExportJobResponse(
                id=job.id,
                project_id=job.project_id,
                media_file_id=job.media_file_id,
                target_language=job.target_language,
                format=job.format,
                resolution=job.resolution,
                frame_rate=job.frame_rate,
                codec=job.codec,
                status=job.status,
                progress_percent=job.progress_percent,
                current_stage=job.current_stage,
                output_video_url=output_url,
                filesize_bytes=job.filesize_bytes,
                estimated_cost_usd=float(job.estimated_cost_usd),
                created_at=job.created_at,
            )
        )
    return results


@router.get(
    "/job/{job_id}/stream",
    summary="Server-Sent Events (SSE) Live Export Progress Feed",
)
async def stream_export_progress(
    job_id: uuid.UUID = Path(...),
    request: Request = None,
):
    """Streams live Redis Pub/Sub export rendering progress events to the frontend."""
    async def event_generator():
        r = aioredis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"events:export:{job_id}")

        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("data"):
                    data = message["data"].decode("utf-8")
                    yield f"event: progress\ndata: {data}\n\n"
                await asyncio.sleep(0.5)
        finally:
            await pubsub.unsubscribe(f"events:export:{job_id}")
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

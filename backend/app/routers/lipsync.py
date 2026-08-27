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
from sqlalchemy.orm import selectinload
from app.core.config import settings
from app.core.database import get_db
from app.models.frame_metadata import FrameMetadata
from app.models.lipsync_job import LipSyncJob
from app.models.media import MediaFile
from app.models.transcript import Transcript
from app.schemas.lipsync_schema import (
    FrameMetadataResponse,
    LipSyncDispatchResponse,
    LipSyncJobResponse,
    RenderLipSyncProjectRequest,
    RenderSegmentLipSyncRequest,
    ReplicateWebhookPayload,
)
from app.services.cloud_tasks_service import cloud_tasks_service
from app.services.storage_service import storage_service
from app.services.pipeline_availability import require_background_pipelines
from app.tasks.lipsync_tasks import render_lipsync_project_task

router = APIRouter(prefix="/lipsync", tags=["Neural Lip-Sync Video Rendering"])


@router.post(
    "/render-project",
    response_model=LipSyncDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Dispatch Full Video Neural Lip-Sync Pipeline",
)
async def render_lipsync_project(
    req: RenderLipSyncProjectRequest,
    db: AsyncSession = Depends(get_db),
):
    """Dispatches asynchronous dubbing + neural lip-sync pipeline to perform TTS, facial synthesis, A/V sync, and video remuxing."""
    stmt = select(MediaFile).where(MediaFile.id == req.media_file_id)
    res = await db.execute(stmt)
    media = res.scalar_one_or_none()

    if not media:
        raise HTTPException(status_code=404, detail="Media file not found.")

    t_stmt = select(Transcript).where(Transcript.id == req.transcript_id)
    t_res = await db.execute(t_stmt)
    transcript = t_res.scalar_one_or_none()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    # Create LipSyncJob entity in database
    job = LipSyncJob(
        project_id=req.project_id or media.project_id,
        media_file_id=req.media_file_id,
        transcript_id=req.transcript_id,
        target_language=req.target_language,
        model_name=req.model_preference,
        status="queued",
        progress_percent=0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    if cloud_tasks_service.enabled:
        cloud_tasks_service.enqueue_http_task(
            relative_handler_path="/v1/internal/tasks/render-lipsync-project",
            payload={
                "job_id": str(job.id),
                "media_file_id": str(req.media_file_id),
                "transcript_id": str(req.transcript_id),
                "target_language": req.target_language,
                "project_id": str(req.project_id) if req.project_id else None,
                "model_preference": req.model_preference,
                "burn_in_subtitles": req.burn_in_subtitles,
            },
            task_name_suffix=f"lipsync-{job.id.hex}-{req.target_language}",
        )
    else:
        require_background_pipelines()
        render_lipsync_project_task.apply_async(
            kwargs={
                "job_id_str": str(job.id),
                "media_file_id_str": str(req.media_file_id),
                "transcript_id_str": str(req.transcript_id),
                "target_language": req.target_language,
                "model_preference": req.model_preference,
                "burn_in_subtitles": req.burn_in_subtitles,
            },
            queue="lipsync_render",
        )

    return LipSyncDispatchResponse(
        job_id=job.id,
        status="queued",
        message="Neural lip-sync video rendering pipeline queued.",
    )


@router.get(
    "/job/{job_id}",
    response_model=LipSyncJobResponse,
    summary="Get Lip-Sync Job Status & Rendered Video URL",
)
async def get_lipsync_job(
    job_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves live job status, progress percentage, segment-by-segment facial detection metadata, and final video streaming URL."""
    stmt = (
        select(LipSyncJob)
        .options(selectinload(LipSyncJob.segments_metadata))
        .where(LipSyncJob.id == job_id)
    )
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Lip-sync job not found.")

    output_url = None
    if job.output_video_gcs_path:
        output_url = storage_service.generate_presigned_download_url(
            job.output_video_gcs_path, expires_in_seconds=7200
        )

    meta_items = []
    for m in sorted(job.segments_metadata, key=lambda s: s.sequence_order):
        meta_items.append(
            FrameMetadataResponse(
                id=m.id,
                segment_id=m.transcript_segment_id,
                sequence_order=m.sequence_order,
                start_time_seconds=float(m.start_time_seconds),
                end_time_seconds=float(m.end_time_seconds),
                face_detected=m.face_detected,
                face_confidence=float(m.face_confidence),
                head_rotation_deg=float(m.head_rotation_deg),
                render_status=m.render_status,
                av_sync_offset_ms=m.av_sync_offset_ms,
                quality_score=float(m.quality_score),
            )
        )

    return LipSyncJobResponse(
        job_id=job.id,
        project_id=job.project_id,
        media_file_id=job.media_file_id,
        target_language=job.target_language,
        model_name=job.model_name,
        status=job.status,
        progress_percent=job.progress_percent,
        total_segments=job.total_segments,
        completed_segments=job.completed_segments,
        output_video_url=output_url,
        quality_score=float(job.quality_score),
        av_sync_error_ms=float(job.av_sync_error_ms),
        segments_metadata=meta_items,
        execution_time_seconds=float(job.execution_time_seconds) if job.execution_time_seconds else None,
        created_at=job.created_at,
    )


@router.get(
    "/job/{job_id}/stream",
    summary="Server-Sent Events (SSE) Real-Time Lip-Sync Progress Feed",
)
async def stream_lipsync_progress(
    job_id: uuid.UUID = Path(...),
    request: Request = None,
):
    """Push-streams live millisecond rendering progress and ETA to frontend via SSE."""
    async def event_generator():
        r = aioredis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"events:lipsync:{job_id}")

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
            await pubsub.unsubscribe(f"events:lipsync:{job_id}")
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


@router.post(
    "/webhooks/replicate",
    status_code=status.HTTP_200_OK,
    summary="Webhook Ingress for Replicate Async Prediction Callbacks",
)
async def replicate_webhook_callback(
    payload: ReplicateWebhookPayload,
):
    """Idempotent callback receiver for Replicate background completions."""
    return {"status": "acknowledged", "prediction_id": payload.id}

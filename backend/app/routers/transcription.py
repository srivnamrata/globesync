import asyncio
import json
import uuid
from typing import Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import PlainTextResponse, StreamingResponse
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.auth import (
    AuthenticatedRequestContext,
    ensure_workspace_resource_access,
    get_request_context,
    require_workspace_write_context,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.media import MediaFile
from app.models.pipeline_operation import PipelineOperation
from app.models.project import Project
from app.models.transcript import Transcript, TranscriptSegment
from app.schemas.transcription_schema import (
    SegmentResponse,
    StartTranscriptionRequest,
    TranscriptionJobResponse,
    TranscriptResponse,
    WordDetail,
)
from app.schemas.projects import PipelineOperationRetryResponse
from app.tasks.transcription_tasks import preprocess_and_transcribe_pipeline_task
from app.services.cloud_tasks_service import cloud_tasks_service
from app.services.pipeline_availability import require_background_pipelines
from app.utils.transcript_parser import transcript_parser

router = APIRouter(prefix="/transcription", tags=["Speech-to-Text & Diarization"])


@router.post(
    "/pipeline-operation/{operation_id}/retry",
    response_model=PipelineOperationRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry Failed Transcription",
)
async def retry_transcription_operation(
    request: Request,
    operation_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    operation = await db.scalar(
        select(PipelineOperation).where(
            PipelineOperation.id == operation_id,
            PipelineOperation.workspace_id == context.workspace_id,
        )
    )
    if operation is None or operation.project_id is None or operation.media_file_id is None or operation.transcript_id is None:
        raise HTTPException(status_code=404, detail="Pipeline operation not found.")
    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=operation.workspace_id,
        project_id=operation.project_id,
        require_write=True,
        not_found_detail="Pipeline operation not found.",
    )
    if operation.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed pipeline operations can be retried.")
    if operation.operation_type != "transcription":
        raise HTTPException(status_code=409, detail="This pipeline operation does not support retry yet.")
    if operation.enable_noise_reduction is None or operation.enable_loudness_norm is None or operation.enable_vad is None:
        raise HTTPException(status_code=409, detail="This transcription operation predates persisted retry options.")

    retry_idempotency_key = f"{operation.idempotency_key or operation.id}:retry:{uuid.uuid4().hex}"
    retry_operation = PipelineOperation(
        project_id=operation.project_id,
        workspace_id=context.workspace_id,
        media_file_id=operation.media_file_id,
        transcript_id=operation.transcript_id,
        operation_type="transcription",
        transcription_language=operation.transcription_language,
        max_speakers=operation.max_speakers,
        enable_noise_reduction=operation.enable_noise_reduction,
        enable_loudness_norm=operation.enable_loudness_norm,
        enable_vad=operation.enable_vad,
        status="queued",
        progress_percent=0,
        current_stage="queued",
        message="Transcription retry queued",
        request_id=request.headers.get("X-Request-ID") or uuid.uuid4().hex,
        idempotency_key=retry_idempotency_key,
    )
    db.add(retry_operation)
    await db.flush()
    project = await db.get(Project, operation.project_id)
    if project:
        project.current_pipeline_operation_id = retry_operation.id
    await db.commit()
    await db.refresh(retry_operation)
    retry_job_id = str(retry_operation.id)

    if cloud_tasks_service.enabled:
        cloud_tasks_service.enqueue_http_task(
            relative_handler_path="/v1/internal/tasks/transcribe",
            payload={
                "media_id": str(operation.media_file_id),
                "transcript_id": str(operation.transcript_id),
                "language": operation.transcription_language,
                "max_speakers": operation.max_speakers,
                "enable_noise_reduction": operation.enable_noise_reduction,
                "enable_loudness_norm": operation.enable_loudness_norm,
                "enable_vad": operation.enable_vad,
                "job_id": retry_job_id,
                "operation_id": retry_job_id,
                "request_id": retry_operation.request_id,
                "idempotency_key": retry_idempotency_key,
                "source_action": "transcription_pipeline_cloud_task_retry",
            },
            task_name_suffix=f"transcribe-retry-{retry_job_id[:24]}",
        )
    else:
        require_background_pipelines()
        task = preprocess_and_transcribe_pipeline_task.apply_async(
            kwargs={
                "media_id_str": str(operation.media_file_id),
                "transcript_id_str": str(operation.transcript_id),
                "language": operation.transcription_language,
                "max_speakers": operation.max_speakers,
                "enable_noise_reduction": operation.enable_noise_reduction,
                "enable_loudness_norm": operation.enable_loudness_norm,
                "request_id": retry_operation.request_id,
                "idempotency_key": retry_idempotency_key,
                "source_action": "transcription_pipeline_celery_retry",
                "operation_id": retry_job_id,
            },
            queue="stt_diarize",
        )
        retry_operation.task_id = task.id
        await db.commit()

    return PipelineOperationRetryResponse(
        operation_id=retry_operation.id,
        operation_type=retry_operation.operation_type,
        status="queued",
        message="Failed transcription retry queued.",
    )


@router.post(
    "/start",
    response_model=TranscriptionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start Audio Extraction, Preprocessing & Diarization Pipeline",
)
async def start_transcription(
    req: StartTranscriptionRequest,
    request: Request,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Dispatches asynchronous transcription work via Cloud Tasks or Celery."""
    stmt = select(MediaFile).where(MediaFile.id == req.media_id)
    res = await db.execute(stmt)
    media = res.scalar_one_or_none()

    if not media:
        raise HTTPException(status_code=404, detail="Media file not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=media.workspace_id,
        project_id=media.project_id,
        require_write=True,
        not_found_detail="Media file not found.",
    )

    # Check for existing transcript or create a new one
    t_stmt = select(Transcript).where(Transcript.media_file_id == req.media_id)
    t_res = await db.execute(t_stmt)
    transcript = t_res.scalar_one_or_none()

    if not transcript:
        transcript = Transcript(
            media_file_id=req.media_id,
            project_id=media.project_id,
            workspace_id=context.workspace_id,
            status="queued",
            detected_language=req.language or "en",
        )
        db.add(transcript)
        await db.commit()
        await db.refresh(transcript)
    else:
        transcript.status = "queued"
        transcript.error_message = None
        await db.commit()

    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    idempotency_key = f"transcribe:{req.media_id}:{transcript.id}"
    operation = PipelineOperation(
        project_id=media.project_id,
        workspace_id=context.workspace_id,
        media_file_id=media.id,
        transcript_id=transcript.id,
        operation_type="transcription",
        status="queued",
        progress_percent=0,
        current_stage="queued",
        message="Transcription queued",
        request_id=request_id,
        idempotency_key=idempotency_key,
        transcription_language=req.language,
        max_speakers=req.max_speakers,
        enable_noise_reduction=req.enable_noise_reduction,
        enable_loudness_norm=req.enable_loudness_norm,
        enable_vad=req.enable_vad,
    )
    db.add(operation)
    await db.flush()
    if media.project_id:
        project = await db.get(Project, media.project_id)
        if project:
            project.current_pipeline_operation_id = operation.id
    await db.commit()
    await db.refresh(operation)
    job_id = str(operation.id)

    if cloud_tasks_service.enabled:
        cloud_tasks_service.enqueue_http_task(
            relative_handler_path="/v1/internal/tasks/transcribe",
            payload={
                "media_id": str(req.media_id),
                "transcript_id": str(transcript.id),
                "language": req.language,
                "max_speakers": req.max_speakers,
                "enable_noise_reduction": req.enable_noise_reduction,
                "enable_loudness_norm": req.enable_loudness_norm,
                "enable_vad": req.enable_vad,
                "job_id": job_id,
                "request_id": request_id,
                "idempotency_key": idempotency_key,
                "source_action": "transcription_pipeline_cloud_task",
            },
            task_name_suffix=f"transcribe-{req.media_id.hex}-{job_id[:12]}",
        )
        return TranscriptionJobResponse(
            job_id=job_id,
            transcript_id=transcript.id,
            media_id=req.media_id,
            status="queued",
            message="Audio extraction, noise reduction, and Deepgram Nova-2 diarization job queued on Cloud Tasks.",
        )

    require_background_pipelines()

    # Dispatch Celery background task
    task = preprocess_and_transcribe_pipeline_task.apply_async(
        kwargs={
            "media_id_str": str(req.media_id),
            "transcript_id_str": str(transcript.id),
            "language": req.language,
            "max_speakers": req.max_speakers,
            "enable_noise_reduction": req.enable_noise_reduction,
            "enable_loudness_norm": req.enable_loudness_norm,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "source_action": "transcription_pipeline_celery",
            "operation_id": job_id,
        },
        queue="stt_diarize",
    )

    return TranscriptionJobResponse(
        job_id=task.id,
        transcript_id=transcript.id,
        media_id=req.media_id,
        status="queued",
        message="Audio extraction, noise reduction, and Deepgram Nova-2 diarization job queued.",
    )


@router.get(
    "/{transcript_id}",
    response_model=TranscriptResponse,
    summary="Get Full Transcript with Speaker Segments & Word Timestamps",
)
async def get_transcript(
    transcript_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves full normalized transcript, confidence scores, and word-level timing details."""
    stmt = (
        select(Transcript)
        .options(selectinload(Transcript.segments))
        .where(Transcript.id == transcript_id)
    )
    res = await db.execute(stmt)
    transcript = res.scalar_one_or_none()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=transcript.workspace_id,
        project_id=transcript.project_id,
        not_found_detail="Transcript not found.",
    )

    segments = []
    for seg in sorted(transcript.segments, key=lambda s: s.sequence_order):
        words = [WordDetail(**w) for w in (seg.words or [])]
        segments.append(
            SegmentResponse(
                id=seg.id,
                start_time=float(seg.start_time_seconds),
                end_time=float(seg.end_time_seconds),
                duration=float(seg.duration_seconds),
                speaker=seg.speaker_tag,
                text=seg.text,
                confidence=float(seg.confidence) if seg.confidence else None,
                words=words,
                sequence_order=seg.sequence_order,
            )
        )

    return TranscriptResponse(
        transcript_id=transcript.id,
        media_id=transcript.media_file_id,
        status=transcript.status,
        language=transcript.detected_language,
        confidence_score=float(transcript.confidence_score) if transcript.confidence_score else None,
        word_count=transcript.word_count,
        speaker_count=transcript.speaker_count,
        full_text=transcript.full_text,
        segments=segments,
        created_at=transcript.created_at,
    )


@router.get(
    "/media/{media_id}",
    response_model=TranscriptResponse,
    summary="Get Transcript by Media File ID",
)
async def get_transcript_by_media(
    media_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Fetches transcript associated with a specific media file ID."""
    stmt = (
        select(Transcript)
        .options(selectinload(Transcript.segments))
        .where(Transcript.media_file_id == media_id)
    )
    res = await db.execute(stmt)
    transcript = res.scalar_one_or_none()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript for media file not found.")

    return await get_transcript(transcript.id, context, db)


@router.get(
    "/{transcript_id}/export/{export_format}",
    summary="Export Transcript (SRT, VTT, Dialogue Script, JSON)",
)
async def export_transcript(
    transcript_id: uuid.UUID = Path(...),
    export_format: str = Path(..., pattern="^(srt|vtt|txt|json)$"),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Exports diarized transcript in subtitle (SRT/VTT) or script format."""
    transcript_data = await get_transcript(transcript_id, context, db)
    segments = transcript_data.segments

    if export_format == "srt":
        content = transcript_parser.export_to_srt(segments)
        return Response(
            content=content,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=transcript_{transcript_id}.srt"},
        )
    elif export_format == "vtt":
        content = transcript_parser.export_to_vtt(segments)
        return Response(
            content=content,
            media_type="text/vtt",
            headers={"Content-Disposition": f"attachment; filename=transcript_{transcript_id}.vtt"},
        )
    elif export_format == "txt":
        content = transcript_parser.export_to_dialogue_format(segments)
        return PlainTextResponse(content=content)
    else:
        return transcript_data


@router.get(
    "/{transcript_id}/stream",
    summary="Server-Sent Events (SSE) Live Progress Feed",
)
async def stream_transcript_progress(
    transcript_id: uuid.UUID = Path(...),
    request: Request = None,
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Streams live Redis Pub/Sub progress events to frontend via SSE."""
    stmt = select(Transcript).where(Transcript.id == transcript_id)
    res = await db.execute(stmt)
    transcript = res.scalar_one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=transcript.workspace_id,
        project_id=transcript.project_id,
        not_found_detail="Transcript not found.",
    )

    async def event_generator():
        r = aioredis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"events:transcript:{transcript_id}")

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
            await pubsub.unsubscribe(f"events:transcript:{transcript_id}")
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

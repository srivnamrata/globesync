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
from app.models.transcript import Transcript, TranscriptSegment
from app.schemas.transcription_schema import (
    SegmentResponse,
    StartTranscriptionRequest,
    TranscriptionJobResponse,
    TranscriptResponse,
    WordDetail,
)
from app.tasks.transcription_tasks import preprocess_and_transcribe_pipeline_task
from app.services.cloud_tasks_service import cloud_tasks_service
from app.services.pipeline_availability import require_background_pipelines
from app.utils.transcript_parser import transcript_parser

router = APIRouter(prefix="/transcription", tags=["Speech-to-Text & Diarization"])


@router.post(
    "/start",
    response_model=TranscriptionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start Audio Extraction, Preprocessing & Diarization Pipeline",
)
async def start_transcription(
    req: StartTranscriptionRequest,
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
        legacy_user_id=media.user_id,
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

    job_id = uuid.uuid4().hex

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
                "job_id": job_id,
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
    export_format: str = Path(..., regex="^(srt|vtt|txt|json)$"),
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

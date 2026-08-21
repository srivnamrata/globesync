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
from app.models.generated_audio import GeneratedAudio
from app.models.media import MediaFile
from app.models.transcript import Transcript, TranscriptSegment
from app.models.translation import Translation
from app.models.voice_profile import VoiceProfile
from app.schemas.tts_schema import (
    CloneVoiceRequest,
    GeneratedAudioResponse,
    MasterDubbedAudioResponse,
    SynthesizeProjectTTSRequest,
    SynthesizeSegmentTTSRequest,
    TTSJobResponse,
    VoiceProfileResponse,
)
from app.services.storage_service import storage_service
from app.services.pipeline_availability import require_background_pipelines
from app.services.tts_orchestrator import tts_orchestrator
from app.services.voice_cloning_service import voice_cloning_service
from app.tasks.tts_tasks import synthesize_project_tts_task

router = APIRouter(prefix="/tts", tags=["Voice Cloning & Text-to-Speech"])


@router.post(
    "/voice-profiles/clone",
    response_model=VoiceProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Clone Speaker Voice from Media Sample",
)
async def clone_speaker_voice(
    req: CloneVoiceRequest,
    db: AsyncSession = Depends(get_db),
):
    """Extracts 30-90s speech sample from media, computes prosody, and creates ElevenLabs voice clone."""
    stmt = select(MediaFile).where(MediaFile.id == req.media_id)
    res = await db.execute(stmt)
    media = res.scalar_one_or_none()

    if not media:
        raise HTTPException(status_code=404, detail="Media file not found.")

    # Fetch transcript segments for speaker
    seg_stmt = select(TranscriptSegment).join(Transcript).where(Transcript.media_file_id == req.media_id)
    s_res = await db.execute(seg_stmt)
    segments = s_res.scalars().all()

    # Download source media locally for sample extraction
    temp_dir = settings.PROCESSED_MEDIA_DIR
    local_media = f"{temp_dir}/clone_src_{media.id.hex}.wav"
    await storage_service.download_file(media.storage_path, local_media)

    voice_profile = await voice_cloning_service.clone_speaker_from_segments(
        master_audio_path=local_media,
        speaker_tag=req.speaker_tag,
        segments=segments,
        project_id=req.project_id or media.project_id,
    )
    db.add(voice_profile)
    await db.commit()
    await db.refresh(voice_profile)

    ref_url = (
        storage_service.generate_presigned_download_url(voice_profile.reference_sample_gcs_path)
        if voice_profile.reference_sample_gcs_path
        else None
    )

    return VoiceProfileResponse(
        voice_id=voice_profile.id,
        speaker_name=voice_profile.speaker_name,
        language=voice_profile.language,
        external_voice_id=voice_profile.external_voice_id,
        reference_sample_url=ref_url,
        voice_settings=voice_profile.voice_settings or {},
        confidence_score=float(voice_profile.confidence_score),
        created_at=voice_profile.created_at,
    )


@router.get(
    "/voice-profiles",
    response_model=List[VoiceProfileResponse],
    summary="List Available Voice Profiles",
)
async def list_voice_profiles(
    project_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Lists cloned voice profiles with acoustic settings and audio sample URLs."""
    stmt = select(VoiceProfile).where(VoiceProfile.is_active == True)
    if project_id:
        stmt = stmt.where(VoiceProfile.project_id == project_id)

    res = await db.execute(stmt)
    profiles = res.scalars().all()

    results = []
    for p in profiles:
        ref_url = (
            storage_service.generate_presigned_download_url(p.reference_sample_gcs_path)
            if p.reference_sample_gcs_path
            else None
        )
        results.append(
            VoiceProfileResponse(
                voice_id=p.id,
                speaker_name=p.speaker_name,
                language=p.language,
                external_voice_id=p.external_voice_id,
                reference_sample_url=ref_url,
                voice_settings=p.voice_settings or {},
                confidence_score=float(p.confidence_score),
                created_at=p.created_at,
            )
        )
    return results


@router.post(
    "/synthesize-project",
    response_model=TTSJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Synthesize Project Dubbing Audio (Batch Celery Task)",
)
async def synthesize_project(
    req: SynthesizeProjectTTSRequest,
    db: AsyncSession = Depends(get_db),
):
    require_background_pipelines()
    """Enqueues async Celery batch TTS generation, duration retiming, and master audio mixing."""
    stmt = select(Transcript).where(Transcript.id == req.transcript_id)
    res = await db.execute(stmt)
    transcript = res.scalar_one_or_none()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    proj_id_str = str(req.project_id or transcript.project_id or "")

    task = synthesize_project_tts_task.apply_async(
        kwargs={
            "transcript_id_str": str(req.transcript_id),
            "target_language": req.target_language,
            "project_id_str": proj_id_str,
        },
        queue="tts_clone",
    )

    return TTSJobResponse(
        job_id=task.id,
        transcript_id=req.transcript_id,
        target_language=req.target_language,
        status="queued",
        message="Voice cloning, parallel TTS speech generation, and retiming task enqueued.",
    )


@router.post(
    "/synthesize-segment",
    response_model=GeneratedAudioResponse,
    summary="Synthesize & Retime Single Translation Segment",
)
async def synthesize_single_segment(
    req: SynthesizeSegmentTTSRequest,
    db: AsyncSession = Depends(get_db),
):
    """Synthesizes a single segment on-demand and applies pitch-preserving time-stretching."""
    stmt = select(Translation).where(Translation.id == req.translation_id)
    res = await db.execute(stmt)
    translation = res.scalar_one_or_none()

    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found.")

    voice_profile = None
    if req.voice_profile_id:
        vp_stmt = select(VoiceProfile).where(VoiceProfile.id == req.voice_profile_id)
        vp_res = await db.execute(vp_stmt)
        voice_profile = vp_res.scalar_one_or_none()

    gen_audio = await tts_orchestrator.synthesize_single_translation(translation, voice_profile)
    db.add(gen_audio)
    await db.commit()
    await db.refresh(gen_audio)

    audio_url = storage_service.generate_presigned_download_url(gen_audio.storage_path)

    return GeneratedAudioResponse(
        id=gen_audio.id,
        translation_id=gen_audio.translation_id,
        voice_profile_id=gen_audio.voice_profile_id,
        audio_url=audio_url,
        storage_path=gen_audio.storage_path,
        raw_tts_duration_ms=gen_audio.raw_tts_duration_ms,
        target_duration_ms=gen_audio.target_duration_ms,
        retimed_duration_ms=gen_audio.retimed_duration_ms,
        speed_adjustment_factor=float(gen_audio.speed_adjustment_factor),
        is_retimed=gen_audio.is_retimed,
        status=gen_audio.status,
        quality_score=float(gen_audio.quality_score),
        created_at=gen_audio.created_at,
    )


@router.get(
    "/project/{project_id}/master-audio",
    response_model=MasterDubbedAudioResponse,
    summary="Get Master Dubbed Audio Streaming URL",
)
async def get_master_audio(
    project_id: uuid.UUID = Path(...),
    target_language: str = Query("es"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves presigned playback URL for the final master dubbed audio track."""
    master_key = f"master_dubbed/{str(project_id)}/{target_language}_dubbed.wav"
    download_url = storage_service.generate_presigned_download_url(master_key, expires_in_seconds=7200)

    return MasterDubbedAudioResponse(
        project_id=project_id,
        transcript_id=project_id,
        target_language=target_language,
        master_audio_url=download_url,
        storage_path=master_key,
        status="ready",
    )


@router.get(
    "/{project_id}/stream",
    summary="Server-Sent Events (SSE) Live TTS Progress Feed",
)
async def stream_tts_progress(
    project_id: uuid.UUID = Path(...),
    request: Request = None,
):
    """Streams live Redis Pub/Sub TTS synthesis progress events to the frontend."""
    async def event_generator():
        r = aioredis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"events:tts:{project_id}")

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
            await pubsub.unsubscribe(f"events:tts:{project_id}")
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

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
from app.models.frame_metadata import FrameMetadata
from app.models.generated_audio import GeneratedAudio
from app.models.lipsync_job import LipSyncJob
from app.models.media import MediaFile
from app.models.project import Project
from app.models.transcript import Transcript, TranscriptSegment
from app.models.translation import Translation
from app.services.av_sync_service import av_sync_service
from app.services.face_detection_service import face_detector
from app.services.replicate_service import replicate_lipsync
from app.services.storage_service import storage_service
from app.services.video_processor import video_processor
from app.services.video_reconstructor import video_reconstructor
from app.tasks.gpu_task_scheduler import gpu_scheduler
from app.tasks.tts_tasks import run_project_tts_pipeline
from app.utils.quality_metrics import quality_metrics
from app.utils.transcript_parser import transcript_parser

logger = logging.getLogger("lipsync_tasks")
sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
SyncSession = sessionmaker(bind=sync_engine)


def publish_lipsync_event(job_id: str, status: str, progress_percent: int, message: str, eta_seconds: Optional[float] = None):
    """Broadcasts real-time lip-sync progress events to Redis Pub/Sub."""
    if not settings.REDIS_URL:
        return
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        event_payload = json.dumps({
            "job_id": job_id,
            "status": status,
            "progress_percent": progress_percent,
            "message": message,
            "eta_seconds": eta_seconds,
            "timestamp": time.time(),
        })
        r.publish(f"events:lipsync:{job_id}", event_payload)
    except Exception as e:
        logger.warning(f"Failed to publish Redis lip-sync event: {e}")


def run_lipsync_project_pipeline(
    job_id_str: str,
    media_file_id_str: str,
    transcript_id_str: str,
    target_language: str,
    model_preference: str = "liveportrait",
    burn_in_subtitles: bool = False,
    enable_lipsync: bool = True,
    request_id: Optional[str] = None,
    task_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    task_instance=None,
):
    """
    End-to-end neural lip-sync rendering pipeline:
    1. Downloads raw video and dubbed audio
    2. Slices speech segments and detects face landmarks
    3. Renders synchronized facial animation via Replicate LivePortrait / Wav2Lip
    4. Evaluates A/V sync drift and quality metrics
    5. Reconstructs and multiplexes final dubbed video with subtitles
    6. Uploads master translated video to Cloud Storage
    """
    job_id = uuid.UUID(job_id_str)
    media_file_id = uuid.UUID(media_file_id_str)
    transcript_id = uuid.UUID(transcript_id_str)
    task_id = task_id or (task_instance.request.id if task_instance is not None else None)
    request_id = request_id or task_id or job_id_str
    idempotency_key = idempotency_key or f"lipsync:{job_id_str}:{target_language}:{model_preference}"
    start_time = time.time()

    publish_lipsync_event(job_id_str, "in_progress", 5, "Initializing neural lip-sync video pipeline...")

    db: Session = SyncSession()
    temp_dir = settings.PROCESSED_MEDIA_DIR
    local_source_video = os.path.join(temp_dir, f"lipsync_src_{media_file_id.hex}.mp4")
    local_master_audio = os.path.join(temp_dir, f"lipsync_master_dub_{job_id.hex}.wav")
    local_rendered_segments = []

    try:
        job = db.query(LipSyncJob).filter(LipSyncJob.id == job_id).first()
        media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
        transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()

        if not job or not media_file or not transcript:
            raise ValueError("Required database records not found for lip-sync task.")

        project = db.query(Project).filter(Project.id == job.project_id).first() if job.project_id else None

        job.status = "in_progress"
        job.request_id = job.request_id or request_id
        job.task_id = job.task_id or task_id
        job.idempotency_key = job.idempotency_key or idempotency_key
        if project is not None:
            project.current_lipsync_job_id = job.id
            project.status = "processing"
        db.commit()

        project_id_str = str(job.project_id or transcript.project_id) if (job.project_id or transcript.project_id) else None
        publish_lipsync_event(job_id_str, "in_progress", 8, "Synthesizing dubbed audio from translated segments...")
        run_project_tts_pipeline(
            transcript_id_str=transcript_id_str,
            target_language=target_language,
            project_id_str=project_id_str,
            request_id=job.request_id,
            task_id=job.task_id,
            idempotency_key=(f"{job.idempotency_key}:tts" if job.idempotency_key else None),
        )

        # 1. Download source video
        publish_lipsync_event(job_id_str, "in_progress", 10, "Downloading high-resolution source video...")
        asyncio.run(
            storage_service.download_file(
                media_file.storage_path,
                local_source_video,
                bucket_name=media_file.storage_bucket,
            )
        )

        # 2. Fetch segment translations and retimed audio
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.sequence_order)
            .all()
        )

        segment_ids = [s.id for s in segments]
        translations = (
            db.query(Translation)
            .options(joinedload(Translation.generated_audio))
            .filter(
                Translation.transcript_segment_id.in_(segment_ids),
                Translation.target_language == target_language,
            )
            .all()
        )

        trans_map = {t.transcript_segment_id: t for t in translations}
        job.total_segments = len(segments)
        db.commit()

        # Step 3: Process Each Speech Segment for Lip-Sync
        rendered_timeline_clips = []
        quality_scores = []

        for idx, seg in enumerate(segments):
            seg_start = float(seg.start_time_seconds)
            seg_dur = float(seg.duration_seconds)
            elapsed = time.time() - start_time
            eta = gpu_scheduler.estimate_eta_seconds(len(segments), idx, elapsed)
            
            pct = 15 + int((idx / max(1, len(segments))) * 65)
            publish_lipsync_event(
                job_id_str,
                "in_progress",
                pct,
                f"Rendering neural lip-sync for segment {idx + 1}/{len(segments)}...",
                eta_seconds=eta,
            )

            # Slice original video segment
            seg_video_slice = os.path.join(temp_dir, f"slice_{seg.id.hex}.mp4")
            asyncio.run(
                video_processor.extract_video_segment(
                    video_input_path=local_source_video,
                    start_seconds=seg_start,
                    duration_seconds=seg_dur,
                    output_segment_path=seg_video_slice,
                )
            )

            # Extract keyframe to detect face
            keyframe_path = os.path.join(temp_dir, f"kf_{seg.id.hex}.jpg")
            asyncio.run(video_processor.extract_frame_at_timestamp(seg_video_slice, seg_dur / 2.0, keyframe_path))
            face_res = face_detector.analyze_frame(keyframe_path)

            # Locate audio segment
            trans = trans_map.get(seg.id)
            gen_audio = trans.generated_audio[0] if trans and trans.generated_audio else None

            local_audio_seg = os.path.join(temp_dir, f"audio_{seg.id.hex}.wav")
            if gen_audio:
                asyncio.run(
                    storage_service.download_file(
                        gen_audio.storage_path,
                        local_audio_seg,
                        bucket_name=gen_audio.storage_bucket,
                    )
                )
            else:
                # Fallback: extract original audio slice
                from app.services.audio_extraction_service import audio_extractor
                asyncio.run(
                    audio_extractor.extract_audio_segment(
                        audio_input_path=local_source_video,
                        start_seconds=seg_start,
                        duration_seconds=seg_dur,
                        output_segment_path=local_audio_seg,
                    )
                )

            rendered_seg_path = os.path.join(temp_dir, f"rendered_{seg.id.hex}.mp4")

            if enable_lipsync and face_res.face_detected and face_res.is_suitable_for_lipsync:
                # Invoke Replicate Neural Lip-Sync
                asyncio.run(
                    replicate_lipsync.render_segment_lipsync(
                        video_slice_path=seg_video_slice,
                        audio_segment_path=local_audio_seg,
                        duration_sec=seg_dur,
                        output_rendered_path=rendered_seg_path,
                        face_frame_path=keyframe_path,
                        model_preference=model_preference,
                    )
                )
                render_status = "completed"
            else:
                # Dub-only mode or no suitable face: mux dubbed audio into original video slice
                asyncio.run(
                    replicate_lipsync._generate_mock_synced_video(
                        video_slice_path=seg_video_slice,
                        audio_segment_path=local_audio_seg,
                        output_path=rendered_seg_path,
                    )
                )
                render_status = "dub_only" if not enable_lipsync else "skipped_no_face"

            # Measure A/V sync drift
            drift_ms = asyncio.run(av_sync_service.measure_av_drift_ms(rendered_seg_path, local_audio_seg))
            dur_ratio = float(trans.duration_ratio) if trans else 1.0
            q_eval = quality_metrics.evaluate_lipsync_quality(
                av_sync_error_ms=drift_ms,
                face_confidence=face_res.confidence,
                duration_ratio=dur_ratio,
            )
            quality_scores.append(q_eval["overall_quality_score"])

            # Save FrameMetadata entity
            meta_record = FrameMetadata(
                lipsync_job_id=job.id,
                transcript_segment_id=seg.id,
                translation_id=trans.id if trans else None,
                sequence_order=idx,
                start_time_seconds=seg_start,
                end_time_seconds=seg_start + seg_dur,
                face_detected=face_res.face_detected,
                face_confidence=face_res.confidence,
                face_bbox=face_res.bbox,
                face_landmarks=face_res.landmarks,
                head_rotation_deg=face_res.head_rotation_deg,
                render_status=render_status,
                av_sync_offset_ms=int(drift_ms),
                quality_score=q_eval["overall_quality_score"],
            )
            db.add(meta_record)

            rendered_timeline_clips.append({
                "segment_path": rendered_seg_path,
                "start_sec": seg_start,
                "duration_sec": seg_dur,
            })
            local_rendered_segments.extend([seg_video_slice, keyframe_path, local_audio_seg, rendered_seg_path])
            job.completed_segments = idx + 1
            db.commit()

        # Step 4: Assemble Master Dubbed Audio for full muxing
        master_dubbed_key = f"master_dubbed/{str(job.project_id or transcript_id)}/{target_language}_dubbed.wav"
        asyncio.run(storage_service.download_file(master_dubbed_key, local_master_audio))

        # Generate temporary subtitles for soft or burned-in muxing
        from app.schemas.transcription_schema import SegmentResponse
        seg_responses = [
            SegmentResponse(
                start_time=float(s.start_time_seconds),
                end_time=float(s.end_time_seconds),
                duration=float(s.duration_seconds),
                speaker=s.speaker_tag,
                text=trans_map[s.id].translated_text if s.id in trans_map else s.text,
            )
            for s in segments
        ]
        srt_content = transcript_parser.export_to_srt(seg_responses)
        local_srt_path = os.path.join(temp_dir, f"sub_{job.id.hex}.srt")
        with open(local_srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        # Step 5: Full Video Reconstruction & Final Encoding
        publish_lipsync_event(job_id_str, "in_progress", 88, "Reconstructing master translated video with H.264 encoding...")
        final_video_local = os.path.join(temp_dir, f"final_translated_{job.id.hex}.mp4")

        asyncio.run(
            video_reconstructor.reconstruct_video_with_lip_sync(
                original_video_path=local_source_video,
                lip_synced_segments=rendered_timeline_clips,
                master_dubbed_audio_path=local_master_audio,
                output_final_video_path=final_video_local,
                subtitle_srt_path=local_srt_path,
                burn_in_subtitles=burn_in_subtitles,
            )
        )

        # Step 6: Upload Final Export Video to Cloud Storage
        publish_lipsync_event(job_id_str, "in_progress", 96, "Uploading final master video to cloud storage...")
        # A job-owned immutable key prevents a later dub mode from replacing an earlier output.
        export_storage_key = (
            f"exports/{str(job.project_id or transcript_id)}/{target_language}/"
            f"{job.id}_{job.render_mode}_translated_master.mp4"
        )
        asyncio.run(
            storage_service.upload_file(
                file_path=final_video_local,
                key=export_storage_key,
                mime_type="video/mp4",
            )
        )

        final_filesize = os.path.getsize(final_video_local) if os.path.exists(final_video_local) else 0
        avg_quality = round(sum(quality_scores) / max(1, len(quality_scores)), 4)
        execution_dur = round(time.time() - start_time, 2)

        job.status = "completed"
        job.progress_percent = 100
        job.output_video_gcs_path = export_storage_key
        job.output_filesize_bytes = final_filesize
        job.quality_score = avg_quality
        job.execution_time_seconds = execution_dur
        if project is not None:
            project.status = "completed"
            project.current_lipsync_job_id = job.id
            project.last_rendered_video_gcs_path = export_storage_key
        db.commit()

        publish_lipsync_event(
            job_id_str,
            "completed",
            100,
            f"Neural lip-sync video rendering completed successfully in {execution_dur}s (Quality Score: {avg_quality * 100:.1f}%).",
        )

        return {
            "status": "completed",
            "job_id": job_id_str,
            "output_video_path": export_storage_key,
            "quality_score": avg_quality,
            "execution_duration_sec": execution_dur,
        }

    except Exception as exc:
        db.rollback()
        logger.error(
            "Error in lip-sync pipeline for job=%s media_file=%s transcript=%s bucket=%s storage_path=%s request_id=%s task_id=%s idempotency_key=%s: %s",
            job_id_str,
            media_file_id_str,
            transcript_id_str,
            getattr(media_file, "storage_bucket", None) if 'media_file' in locals() else None,
            getattr(media_file, "storage_path", None) if 'media_file' in locals() else None,
            request_id,
            task_id,
            idempotency_key,
            exc,
            exc_info=True,
        )
        if 'job' in locals() and job:
            job.status = "failed"
            job.error_message = str(exc)
            if 'project' in locals() and project is not None:
                project.status = "failed"
                project.current_lipsync_job_id = job.id
            db.commit()

        publish_lipsync_event(job_id_str, "failed", 0, f"Lip-sync rendering failed: {str(exc)}")
        if task_instance is not None:
            raise task_instance.retry(exc=exc)
        raise

    finally:
        db.close()
        # Clean up temporary scratch files
        for p in local_rendered_segments + [local_source_video, local_master_audio]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@celery_app.task(
    bind=True,
    name="app.tasks.lipsync_tasks.render_lipsync_project_task",
    max_retries=3,
    default_retry_delay=15,
)
def render_lipsync_project_task(
    self,
    job_id_str: str,
    media_file_id_str: str,
    transcript_id_str: str,
    target_language: str,
    model_preference: str = "liveportrait",
    burn_in_subtitles: bool = False,
    enable_lipsync: bool = True,
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
):
    """Celery wrapper around the shared lip-sync pipeline implementation."""
    return run_lipsync_project_pipeline(
        job_id_str=job_id_str,
        media_file_id_str=media_file_id_str,
        transcript_id_str=transcript_id_str,
        target_language=target_language,
        model_preference=model_preference,
        burn_in_subtitles=burn_in_subtitles,
        enable_lipsync=enable_lipsync,
        request_id=request_id,
        task_id=self.request.id,
        idempotency_key=idempotency_key,
        task_instance=self,
    )

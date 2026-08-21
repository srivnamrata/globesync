from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "translation_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.transcription_tasks",
        "app.tasks.translation_tasks",
        "app.tasks.tts_tasks",
        "app.tasks.lipsync_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_routes={
        "app.tasks.transcription_tasks.extract_audio_task": {"queue": "audio_extract"},
        "app.tasks.transcription_tasks.transcribe_audio_task": {"queue": "stt_diarize"},
        "app.tasks.transcription_tasks.preprocess_and_transcribe_pipeline_task": {"queue": "stt_diarize"},
        "app.tasks.translation_tasks.translate_project_batch_task": {"queue": "translation"},
        "app.tasks.tts_tasks.synthesize_project_tts_task": {"queue": "tts_clone"},
        "app.tasks.tts_tasks.assemble_master_audio_task": {"queue": "audio_retiming"},
        "app.tasks.lipsync_tasks.render_lipsync_project_task": {"queue": "lipsync_render"},
        "app.tasks.lipsync_tasks.reconstruct_and_mux_video_task": {"queue": "mux_export"},
    },
    task_default_queue="default",
)

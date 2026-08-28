import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Audio & Video Translation Platform"
    API_V1_STR: str = "/v1"
    DEBUG: bool = False
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "https://app.translationplatform.io"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres_secure_pass@localhost:5432/translation_db"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgres_secure_pass@localhost:5432/translation_db"

    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Native Google Cloud Storage. Cloud Run uses its service identity (ADC),
    # so no HMAC access keys are needed in production.
    STORAGE_PROVIDER: str = "gcs"
    GCS_BUCKET_NAME: Optional[str] = "translation-app-media-prod"
    GCS_EXPORTS_BUCKET: Optional[str] = "translation-app-media-exports"
    GCS_SIGNING_SERVICE_ACCOUNT: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GOOGLE_CLOUD_PROJECT: Optional[str] = None

    # Runtime deployment controls
    DEPLOYMENT_ENV: str = "development"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 0
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800
    # Celery workers are not part of the two-service Cloud Run launch.
    ENABLE_BACKGROUND_PIPELINES: bool = False
    # Cloud Tasks → private API endpoint for short idempotent jobs.
    CLOUD_TASKS_ENABLED: bool = False
    CLOUD_TASKS_LOCATION: Optional[str] = "us-central1"
    CLOUD_TASKS_QUEUE: Optional[str] = "translation-jobs"
    CLOUD_TASKS_TARGET_URL: Optional[str] = None
    CLOUD_TASKS_OIDC_SERVICE_ACCOUNT: Optional[str] = None
    INTERNAL_TASKS_AUDIENCE: Optional[str] = None
    # When Cloud Tasks is off and Celery is off, run Google text translation inline.
    TRANSLATION_SYNC_FALLBACK: bool = True

    # Media File Handling & Limits
    MAX_FILE_SIZE_BYTES: int = 4 * 1024 * 1024 * 1024  # 4 GB
    MULTIPART_CHUNK_SIZE_BYTES: int = 8 * 1024 * 1024  # 8 MB default chunk size
    MAX_CONCURRENT_UPLOADS: int = 20
    TEMP_UPLOAD_DIR: str = os.path.join(os.getcwd(), "tmp", "uploads")
    PROCESSED_MEDIA_DIR: str = os.path.join(os.getcwd(), "tmp", "processed")

    # AI & Speech-to-Text Services (Deepgram Nova-2)
    DEEPGRAM_API_KEY: Optional[str] = None
    DEEPGRAM_MODEL: str = "nova-2"
    DEEPGRAM_TIER: str = "enhanced"
    DEEPGRAM_SMART_FORMAT: bool = True
    DEEPGRAM_DIARIZE: bool = True
    DEEPGRAM_PUNCTUATE: bool = True
    DEEPGRAM_UTTERANCES: bool = True

    # Translation Engine (Google Cloud Translation or OpenAI GPT-4o)
    # Set TRANSLATION_PROVIDER="google" to use Google Cloud Translation Advanced.
    TRANSLATION_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = "test_openai_api_key_placeholder"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = 0.3
    TRANSLATION_DURATION_TOLERANCE: float = 0.10  # ±10% tolerance
    TRANSLATION_MAX_ITERATIONS: int = 3
    TRANSLATION_CACHE_TTL_SECONDS: int = 2592000  # 30 days

    # Speech Synthesis Provider
    TTS_PROVIDER: str = "google"
    GOOGLE_TTS_LANGUAGE_CODE: str = "en-US"
    GOOGLE_TTS_VOICE_NAME: Optional[str] = None
    GOOGLE_TTS_AUDIO_ENCODING: str = "LINEAR16"
    GOOGLE_TTS_SPEAKING_RATE: float = 1.0
    GOOGLE_TTS_PITCH: float = 0.0

    # Voice Cloning & Text-to-Speech (ElevenLabs)
    ELEVENLABS_API_KEY: str = "test_elevenlabs_api_key_placeholder"
    ELEVENLABS_MODEL_ID: str = "eleven_multilingual_v2"
    ELEVENLABS_DEFAULT_VOICE_ID: str = "0ZQKuoISTwSqUdo1z4fM"  # Default ElevenLabs fallback voice
    ELEVENLABS_STABILITY: float = 0.50
    ELEVENLABS_SIMILARITY_BOOST: float = 0.80
    ELEVENLABS_STYLE: float = 0.05
    ELEVENLABS_USE_SPEAKER_BOOST: bool = True

    # Lip-Sync Engine (Replicate / LivePortrait / Wav2Lip)
    REPLICATE_API_TOKEN: str = "test_replicate_token_placeholder"
    LIPSYNC_MODEL_PRIMARY: str = "arc144/liveportrait:9d19a2b535d4ad784534a7fb9539401217e914022a1bb18b4566ecb75ec58d11"
    LIPSYNC_MODEL_FALLBACK: str = "devxpy/wav2lip:8d65e3f4f4298520e079198b493c25adfc43c058ffec924f204403842630eb68"
    LIPSYNC_SMOOTHING_WINDOW: int = 5
    LIPSYNC_CONFIDENCE_THRESHOLD: float = 0.65
    LIPSYNC_FACE_EXPAND_RATIO: float = 1.25
    LIPSYNC_MAX_AV_DRIFT_MS: int = 100

    # Security
    JWT_SECRET_KEY: str = "replace-with-super-secret-hex-key-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    WEBHOOK_SECRET: str = "shared_webhook_secret_key_32bytes_hex"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow"
    )


settings = Settings()

# Ensure temporary directories exist
os.makedirs(settings.TEMP_UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.PROCESSED_MEDIA_DIR, exist_ok=True)

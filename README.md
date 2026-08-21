# Enterprise Audio & Video Translation Platform

A production-ready, cloud-agnostic platform for automated video translation, speech-to-text, speaker diarization, context-aware translation with duration matching, voice cloning, and audio retiming.

---

## 📁 Repository Directory Structure

```
audio-video-translation-app/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py                 # Pydantic settings, environment configurations, and secrets
│   │   │   ├── database.py               # Async/sync SQLAlchemy PostgreSQL engine & session maker
│   │   │   └── celery_app.py             # Celery broker & queue routing (audio_extract, stt, trans, tts)
│   │   ├── models/
│   │   │   ├── media.py                  # MediaFile, UploadSession, UploadChunk models
│   │   │   ├── transcript.py             # Transcript and TranscriptSegment models
│   │   │   ├── translation.py            # Translation model with duration metrics and iteration history
│   │   │   ├── voice_profile.py          # VoiceProfile model for speaker embeddings & ElevenLabs IDs
│   │   │   └── generated_audio.py        # GeneratedAudio model for retimed TTS audio segments
│   │   ├── schemas/
│   │   │   ├── media_schema.py           # Pydantic v2 schemas for chunked & direct media upload
│   │   │   ├── transcription_schema.py   # Pydantic schemas for STT, diarization & word timestamps
│   │   │   ├── translation_schema.py     # Pydantic schemas for batch translation & duration matching
│   │   │   └── tts_schema.py             # Pydantic schemas for voice cloning & speech synthesis
│   │   ├── services/
│   │   │   ├── storage_service.py        # S3 / MinIO / GCS multipart storage abstraction layer
│   │   │   ├── media_service.py          # FFprobe stream inspector & FFmpeg thumbnail generator
│   │   │   ├── audio_extraction_service.py # 16kHz mono WAV demuxing (<30s for 4GB)
│   │   │   ├── audio_preprocessing_service.py # Noise reduction, -20 LUFS norm & VAD chunking
│   │   │   ├── deepgram_service.py       # Deepgram Nova-2 STT with speaker diarization
│   │   │   ├── openai_service.py         # OpenAI GPT-4o async client with token/cost tracking
│   │   │   ├── duration_matcher.py       # Iterative length matching feedback loop (±10% tolerance)
│   │   │   ├── translation_service.py    # Batch translation orchestrator with sliding context window
│   │   │   ├── elevenlabs_service.py     # ElevenLabs Multilingual v2 & instant voice cloning
│   │   │   ├── voice_cloning_service.py  # 30-90s speaker sample harvester & profile creator
│   │   │   ├── tts_orchestrator.py       # Concurrent TTS speech synthesis & S3 uploader
│   │   │   └── audio_postprocessor.py    # FFmpeg atempo time-stretching, de-clicking & master mixing
│   │   ├── utils/
│   │   │   ├── error_codes.py            # Standardized ErrorCode enums & custom MediaAppException
│   │   │   ├── file_validators.py        # Magic header inspection, MIME detection, SHA-256 calculators
│   │   │   ├── transcript_parser.py      # Normalizer, word timing aggregator & SRT/VTT/TXT exporters
│   │   │   ├── language_configs.py       # 20+ language specs, speech rates, few-shot examples
│   │   │   ├── speech_rate.py            # Syllabic/character rate calculators & punctuation pause model
│   │   │   ├── prompt_templates.py       # Dubbing system prompts, condensation & expansion prompts
│   │   │   ├── prosody_extractor.py      # F0 pitch contour, RMS energy, warmth & depth analyzer
│   │   │   └── audio_matcher.py          # Speed factor calculator (0.75x - 1.35x) & duration error delta
│   │   ├── tasks/
│   │   │   ├── transcription_tasks.py    # Celery tasks for demuxing, preprocessing & STT
│   │   │   ├── translation_tasks.py      # Celery tasks for batch translation & duration matching
│   │   │   └── tts_tasks.py              # Celery tasks for voice cloning, TTS & master audio mixing
│   │   ├── routers/
│   │   │   ├── upload.py                 # Direct & resumable chunked upload endpoints
│   │   │   ├── transcription.py          # Transcription start, lookup, export & SSE stream
│   │   │   ├── translation.py            # Translation batch, segment edit, export & SSE stream
│   │   │   └── tts.py                    # Voice cloning, batch synthesis, master playback & SSE stream
│   │   └── main.py                       # FastAPI application, global exception handlers, CORS, Request ID
│   ├── tests/
│   │   ├── test_upload_pipeline.py       # Tests for chunked upload, magic bytes, and file validators
│   │   ├── test_transcription_pipeline.py# Tests for STT parser, diarization, and subtitle exports
│   │   ├── test_translation_pipeline.py  # Tests for speech rate, duration matching & translation API
│   │   └── test_tts_pipeline.py          # Tests for voice cloning, prosody extraction & retiming
│   ├── .env.example                      # Environment variables template
│   └── requirements.txt                  # Python dependencies
└── README.md
```

---

## ✅ Prerequisites

Before you begin, ensure you have the following installed on your system:
- **Python** (version 3.10 or newer)
- **Docker Desktop**: Required to run the project's backing services (PostgreSQL, Redis, MinIO). Make sure the Docker daemon is running.
- **FFmpeg**: Required for all media processing tasks. Ensure the `ffmpeg` and `ffprobe` commands are available in your system's PATH.

## 🚀 Getting Started

### 1. Environment Setup
```bash
# Navigate to the backend directory
cd backend

# (Recommended) Create and activate a Python virtual environment
# python -m venv venv
# source venv/bin/activate  (or .\venv\Scripts\activate on Windows)

# Install Python dependencies
pip install -r requirements.txt

# Copy the example environment file. The default values are configured
# to work with the docker-compose setup.
cp .env.example .env
```

### Google Cloud Translation

To use Google Cloud Translation Advanced, download a JSON key for the service
account that has the **Cloud Translation API User** role. Save it outside the
repository (or in `backend/`, which is ignored), then add these values to
`backend/.env`:

```env
TRANSLATION_PROVIDER="google"
GOOGLE_CLOUD_PROJECT="your-google-cloud-project-id"
GOOGLE_APPLICATION_CREDENTIALS="C:/absolute/path/to/service-account.json"
```

Install dependencies again after this change: `pip install -r requirements.txt`.
The Google account email is not used by the application; the project ID and
service-account credentials determine access. Google Cloud translations are
measured for duration and then retimed in the media pipeline; duration-guided
text rewriting remains available through the OpenAI provider.

### 2. Start Services
```bash
# Start FastAPI Web Server
# In a separate terminal, start the backing services (PostgreSQL, Redis, MinIO).
# Note: Use 'docker compose' (with a space) for modern Docker versions.
# If you have an older version, you might need 'docker-compose' (with a hyphen).
docker compose up -d

# Start the FastAPI Web Server in your main terminal
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start the Next.js Frontend in new terminal
cd D:\audio-video-translation-app\frontend
npm install
npm run dev

# Start Celery Worker Pools
celery -A app.core.celery_app worker -Q audio_extract,stt_diarize,translation,tts_clone,audio_retiming -c 4 --loglevel=info
```

### 3. Run Test Suite
```bash
pytest tests/ -v
```

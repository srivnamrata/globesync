# GlobeSync Project Submission

**1. Idea Title**
GlobeSync
*Idea One Liner:* An enterprise-grade, cloud-agnostic platform that takes any audio or video file and produces a fully dubbed, lip-synced translation in a target language — automatically.

**2. Idea description**
GlobeSync automates the entire pipeline from raw media to a finished translated MP4. It is designed to be a production-ready platform for automated video translation, speech-to-text, speaker diarization, context-aware translation with duration matching, voice cloning, and audio retiming. 

The platform operates on an 8-stage pipeline:
1. Upload & Validation
2. Audio Extraction & Preprocessing (FFmpeg)
3. STT + Diarization (Deepgram Nova-2)
4. Translation (GPT-4o or Google Cloud Translation, iteratively rewritten for duration matching)
5. Voice Cloning & TTS (ElevenLabs)
6. Audio Retiming (FFmpeg time-stretching)
7. Neural Lip-Sync (Replicate LivePortrait/Wav2Lip)
8. Export (Stitching into final MP4 with subtitles)

**3. Additional details for your idea/ project description**
GlobeSync competes on control, reliability, and operational clarity rather than only on generation quality. Key design decisions include a duration-matching feedback loop (ensuring audio fits within ±10% of the video window), per-speaker voice cloning by harvesting clean speech from the original video, and a graceful lip-sync fallback (skipping neural rendering if no face is detected to avoid blocking). The architecture uses a Next.js frontend, a FastAPI backend, and Celery task dispatching across 7 worker queues.

**4. Google Cloud Services Used**
*   **Google Cloud Storage (GCS):** For media storage (raw video uploads, audio chunks, and finalized exports).
*   **Google Cloud SQL (PostgreSQL):** Fully managed relational database for storing project metadata, user data, and translation states.
*   **Google Cloud Translation Advanced API:** For context-aware text translation.
*   **Google Cloud Speech-to-Text & Text-to-Speech:** Primary engines for transcription and voice synthesis (alongside deepgram/elevenlabs).
*   **Google Identity Platform:** For secure OAuth authentication (Google Sign-In).
*   **Google Cloud Tasks:** For queuing and dispatching short, idempotent backend jobs.
*   **Google Secret Manager:** For securely storing database credentials, JWT secrets, and third-party API keys.
*   **Google Cloud Build & Artifact Registry:** For building Docker images and storing them as part of the CI/CD pipeline.
*   **Google Cloud Run:** Used for hosting the `translation-web` (frontend) and `translation-api` (FastAPI backend) deployments.

**5. AI Details**
*Other:* Google Cloud Translation Advanced API (for translation), Google Cloud Speech-to-Text (STT), and Google Cloud Text-to-Speech (TTS). 
*(Note: OpenAI GPT-4o, Deepgram Nova-2, ElevenLabs, and Replicate LivePortrait/Wav2Lip are also integrated into the pipeline depending on the selected configuration.)*

**6. Tech Stack (other tech details)**
*   **Frontend:** Next.js (React 18), TailwindCSS (Styling), Zustand (State Management), IndexedDB (Local Drafts).
*   **Backend / API:** FastAPI, Python 3.10+, Uvicorn.
*   **Database (SQL):** PostgreSQL (asyncpg driver) with SQLAlchemy (ORM) and Alembic (Database Migrations).
*   **Task Queue & Caching:** Celery (7 Worker Queues) backed by Redis (Pub/Sub Broker).
*   **Media & Audio Processing:** FFmpeg (demuxing, muxing, `atempo` time-stretching), Pydub, Librosa (Audio analysis).
*   **Computer Vision:** OpenCV (headless) and Pillow (Face detection/frame metadata).
*   **AI Services (SDKs):** Deepgram (STT), ElevenLabs (TTS), Replicate (Lip-sync), OpenAI (Translation).
**7. Using any Vibe Coding / Build Tools?**
Yes. Antigravity IDE

**8. Progress Detail on your project delivery**
*   **Phase A (Access & Entry Experience):** Completed. Public landing page and authenticated workspace separated. Google sign-in integrated.
*   **Phase B (Project Browser & Lifecycle):** Completed. Dashboard for project management, search, filters, and status badges.
*   **Phase C-G (Editor, Review, Quality, UI Polish, Global Readiness):** In progress/Completed.
*   **Phase H (Team and Enterprise Workflow Readiness):** In progress. Adding workspace switching, collaborator-aware metadata, and team handoff states.
*   **Planned Completion Date:** *[Please insert your target dates for the final Phase H audit and release validation]*

**9. Have you completed (deployed) your project?**
Yes, the project is deployed (currently undergoing final release validation for the web and API services).
*[Please insert your deployment link here]*

**10. Deployed App Details**
*   **How to access and test:** Go to the deployment link and sign in using Google. You will be provisioned a personal workspace where you can create a new project, upload a video file, and test the translation, voice cloning, and lip-sync pipeline. Progress is streamed live to the browser via Server-Sent Events.
*[Please insert any specific testing credentials or instructions if required]*

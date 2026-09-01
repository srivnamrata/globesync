# GlobeSync Phase 0 Current-State Inventory

This document captures the current known system behavior before tenancy, backend-backed drafts, and multi-user collaboration are introduced.

## Snapshot summary

* Date: 2026-08-29
* Deployment target: GCP-first architecture on Cloud Run, Cloud SQL Postgres, and GCS
* Current editor model: single-user, browser-local draft persistence with backend media-processing APIs
* Current migration objective: replace IndexedDB as the system of record with backend-owned project and draft persistence

## 1. Frontend source of truth today

### Canonical project draft persistence

The editor currently treats IndexedDB as the primary persistence layer for project draft state.

Reviewed files:
* [storageService.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/services/storageService.ts)
* [useProject.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/hooks/useProject.ts)
* [page.tsx](#file-3239543912549008)
* [projectStore.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/store/projectStore.ts)
* [mediaStore.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/store/mediaStore.ts)
* [translationStore.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/store/translationStore.ts)

### IndexedDB draft shape

`frontend/services/storageService.ts` defines a `HeygenXFile` object persisted in IndexedDB object store `project_drafts` with key path `projectMetadata.id`.

Current persisted draft fields:
* `version`
* `projectMetadata.id`
* `projectMetadata.name`
* `projectMetadata.sourceLanguage`
* `projectMetadata.targetLanguage`
* `projectMetadata.createdAt`
* `projectMetadata.updatedAt`
* `mediaReferences.videoFilename`
* `mediaReferences.durationSeconds`
* `mediaReferences.originalTranscriptSegments`
* `mediaReferences.transcriptId`
* `mediaReferences.mediaId`
* `translations`
* optional `timelineState.markers`
* optional `timelineState.zoomLevel`

### Editor hydration and save flow

Current editor behavior in `frontend/app/editor/[projectId]/page.tsx`:
* On page load, the editor calls `storageService.getDraft(projectId)`.
* If no local draft exists, the user is redirected away from the editor.
* Zustand stores are hydrated from the local draft, not from backend project APIs.
* If transcript segments exist locally but translations are incomplete, the editor fetches translations from backend APIs and then writes them back into IndexedDB.
* A local `persistDraft()` helper rewrites the full draft document after edits and pipeline transitions.

Current auto-save behavior in `frontend/hooks/useProject.ts`:
* Auto-save runs every 30 seconds.
* The saved payload is reconstructed from `currentProject`, transcript `segments`, and `translations` in Zustand stores.
* Auto-save updates `projectMetadata.updatedAt` locally before writing to IndexedDB.
* Auto-save failures are only logged to the browser console.

### Frontend in-memory state model

Current project state in `frontend/store/projectStore.ts`:
* `id`
* `name`
* `sourceLanguage`
* `targetLanguage`
* `status`
* `createdAt`
* `updatedAt`
* optional `transcriptId`
* optional `mediaId`
* optional `originalVideoUrl`
* optional `dubbedAudioUrl`

Current transcript segment state in `frontend/store/mediaStore.ts`:
* `id`
* `sequenceOrder`
* `startTimeSeconds`
* `endTimeSeconds`
* `durationSeconds`
* `speakerTag`
* `text`
* `confidence`

Current translation segment state in `frontend/store/translationStore.ts`:
* `id`
* `transcriptSegmentId`
* `translatedText`
* `originalDurationMs`
* `estimatedDurationMs`
* `durationRatio`
* `speedAdjustmentFactor`
* `qualityScore`
* `status`

### Frontend source-of-truth risks

* Browser storage is the canonical project store today.
* Device switching is not safe because project existence depends on a local draft being present.
* Conflict handling does not exist for concurrent editing.
* Auto-save durability is weak because failures are not surfaced to the user.
* Draft persistence currently stores transcript segments inline, duplicating data that also exists in backend transcript tables.

## 2. Frontend-to-backend request path today

Reviewed files:
* [projectService.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/services/projectService.ts)
* [apiClient.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/services/apiClient.ts)
* [main.py](#file-3239543912548896)
* [transcription.py](#file-3239543912548912)
* [tts.py](#file-3239543912548914)

### API client behavior

`frontend/services/apiClient.ts` resolves the API base URL from `NEXT_PUBLIC_API_URL` and ensures the final base path ends with `/v1`.

Current client characteristics:
* JSON-first request wrapper with retry logic for HTTP 429 and 503
* Optional bearer token support exists, but the current editor flow is still effectively unauthenticated in practice
* API failures surface as thrown errors; there is no centralized user-visible session or authorization handling yet

### Editor API calls in use

The editor currently uses these backend calls through `projectService`:
* `POST /media/uploads/direct`
* `POST /transcription/start`
* `GET /transcription/{transcriptId}`
* `POST /translation/translate-project`
* `GET /translation/{transcriptId}?target_language={lang}`
* `PUT /translation/segment/{translationId}`
* `POST /tts/synthesize-project`
* `POST /lipsync/render-project`
* `GET /lipsync/job/{jobId}`

The frontend service also references:
* `GET /projects`
* `GET /projects/{projectId}`
* `GET /transcription/{mediaId}/segments`

### Confirmed route audit

Based on the current backend app wiring in [main.py](#file-3239543912548896), the mounted routers are only:
* `/media/uploads/*`
* `/transcription/*`
* `/translation/*`
* `/lipsync/*`
* `/internal/tasks/*`

Confirmed findings:
* No `/projects` router is mounted in the FastAPI app.
* No backend router file reviewed in `backend/app/routers` defines a `/projects` prefix.
* `projectService.fetchAllProjects()` and `projectService.getProject()` currently point at routes that do not appear to exist in the mounted backend.
* The frontend helper `getTranscript(mediaId)` previously called `GET /transcription/{mediaId}/segments`, but it has now been aligned to the implemented backend route `GET /transcription/media/{media_id}` and maps the transcript response payload back into frontend `TranscriptSegment` objects.
* `POST /tts/synthesize-project` was implemented in [tts.py](#file-3239543912548914) and is now mounted through [main.py](#file-3239543912548896).

Current interpretation:
* `/projects` remains the confirmed missing API surface in the reviewed backend.
* The transcript-by-media route mismatch has been fixed in the frontend service layer.
* The TTS router exposure issue has been fixed in the FastAPI entrypoint.

### Runtime interaction pattern in the editor

Current high-level sequence:
1. Load draft from IndexedDB.
2. Hydrate Zustand stores.
3. Fetch persisted translations only when local translations are incomplete.
4. Write merged state back to IndexedDB.
5. Queue dub/lip-sync work through backend endpoints.
6. Poll job state with repeated `GET /lipsync/job/{jobId}` calls.

Current user experience implication:
* Backend processing exists, but the editor session is still anchored to local draft persistence and polling rather than backend-owned project state and live event streams.

## 3. Backend persistence model today

Reviewed model files:
* [media.py](#file-3239543912548903)
* [transcript.py](#file-3239543912548904)
* [translation.py](#file-3239543912548905)
* [generated_audio.py](#file-3239543912548901)
* [lipsync_job.py](#file-3239543912548902)
* [export_job.py](#file-3239543912548899)

### Existing core tables

| Table | Purpose | Current ownership fields | Notes |
| --- | --- | --- | --- |
| `media_files` | Source or processed uploaded media asset | nullable `project_id`, nullable `organization_id`, nullable `user_id` | Storage defaults still reference `s3` in model defaults even though runtime storage is GCS |
| `upload_sessions` | Resumable upload session tracking | nullable `organization_id`, nullable `user_id`, nullable `media_file_id` | Uses `storage_key` and `s3_upload_id` naming despite GCS compose-based multipart flow |
| `upload_chunks` | Per-chunk upload tracking | inherits ownership through session | Chunk receipt ledger |
| `transcripts` | Full transcript record | nullable `project_id`, `media_file_id` FK | Stores status, full text, language, raw provider response |
| `transcript_segments` | Ordered speaker segments | `transcript_id` FK | Word-level timing JSON, speaker tag, optional voice profile reference |
| `translations` | Per-segment translated text | nullable `project_id`, `transcript_segment_id` FK | Stores duration-matching metrics and user-edit flag |
| `generated_audios` | Per-segment synthesized audio | nullable `project_id`, `translation_id` FK | Stores bucket/path and retiming metrics |
| `lipsync_jobs` | End-to-end dub and lip-sync job | nullable `project_id`, `media_file_id` FK, `transcript_id` FK | Stores progress, output path, error state |
| `export_jobs` | Output render/export job | nullable `project_id`, `media_file_id` FK, `transcript_id` FK | Stores codec/resolution options and output path |

### Persistence observations

* There is no reviewed `projects` table yet backing the editor as a canonical entity.
* Ownership fields exist in several models, but they are nullable and not yet a hard tenancy boundary.
* `organization_id` appears in upload/media models, while the future plan is workspace-based multi-tenancy, so a naming and ownership migration will be needed.
* Transcript segments and translations already have a relational structure suitable for becoming canonical pipeline data.
* The frontend still stores duplicate segment and translation state outside Cloud SQL.

## 4. Backend task and processing topology today

Reviewed router and service files:
* [main.py](#file-3239543912548896)
* [transcription.py](#file-3239543912548912)
* [translation.py](#file-3239543912548913)
* [lipsync.py](#file-3239543912548911)
* [tts.py](#file-3239543912548914)
* [internal_tasks.py](#file-3239543912548910)
* [cloud_tasks_service.py](#file-/Users/roboplaylab@gmail.com/globesync/backend/app/services/cloud_tasks_service.py)

### Public API routers

Current public router responsibilities reviewed in this pass:
* `/transcription/start` creates or re-queues a transcript and dispatches async work
* `/transcription/{transcript_id}` returns normalized transcript data and ordered segments
* `/transcription/media/{media_id}` returns transcript data by media file ID
* `/translation/translate-project` queues batch translation
* `/translation/segment/{translationId}` is used by the editor for persisted text edits
* `/lipsync/render-project` creates a `lipsync_jobs` row and dispatches rendering
* `/lipsync/job/{jobId}` returns status and a signed output URL when available
* Upload endpoints under `/media/uploads/*` register media and resumable upload sessions

Mounted-router observations:
* `tts.py` exists, defines `/tts/*` routes, and is now mounted in the reviewed FastAPI entrypoint.
* No `projects` router is mounted in the reviewed FastAPI entrypoint.

### Cloud Tasks topology

Current GCP async pattern:
* Public endpoints enqueue Cloud Tasks when enabled.
* Cloud Tasks targets private internal handlers under `/v1/internal/tasks/*`.
* Internal handlers verify Cloud Tasks headers before accepting execution.
* Internal handlers call synchronous pipeline functions in worker threads.

Reviewed internal task handlers:
* `POST /v1/internal/tasks/transcribe`
* `POST /v1/internal/tasks/translate-project`
* `POST /v1/internal/tasks/render-lipsync-project`

### Processing observations

* Cloud Tasks is already the preferred production orchestration pattern.
* The backend still contains fallback modes for in-request execution or Celery-style background execution when Cloud Tasks is unavailable.
* Job progress delivery is mixed: SSE endpoints exist for transcript and lip-sync progress, but the editor still relies on polling for lip-sync completion.
* Translation persistence currently replaces existing rows for the same segment and target language during batch runs.

## 5. Storage boundaries today

Reviewed file:
* [storage_service.py](#file-/Users/roboplaylab@gmail.com/globesync/backend/app/services/storage_service.py)

Known storage locations from current implementation and prior environment review:
* Primary raw media bucket is GCS-backed through `settings.GCS_BUCKET_NAME`
* Separate exports bucket is configured through `settings.GCS_EXPORTS_BUCKET`
* Active raw bucket prefixes observed: `_ops/`, `master_dubbed/`, `tts_segments/`, `voice_profiles/`
* `exports/` was not present in the raw bucket when checked
* Configured exports bucket `gs://project-794c406e-c0ab-4a50-8e9-media-exports` was empty when checked
* GCS multipart session metadata is stored under `_multipart/{upload_id}/session.json`
* Multipart upload parts are stored under `_multipart/{upload_id}/part-xxxxx`

### Storage ownership split

| Location | Current role | Current authority |
| --- | --- | --- |
| Browser IndexedDB | Project draft, transcript segment copy, translation copy | Primary editor source of truth |
| Cloud SQL | Media, transcript, translation, audio, lip-sync, export, upload session state | Primary pipeline persistence |
| GCS raw bucket | Uploaded media, operational artifacts, TTS segments, voice assets, rendered assets | Binary/object storage |
| GCS exports bucket | Intended export destination | Presently unused |

### Storage migration observations

* Browser draft persistence currently overlaps with Cloud SQL transcript and translation state.
* Bucket layout reflects operational artifacts but not yet a clear multi-tenant workspace/project namespace.
* Some storage and multipart naming still reflects legacy S3 terminology even though the implementation is now GCS-native.

## 6. Release and deployment guardrails already known

Known deployment guardrails from current repo and prior deployment review:
* `translation-migrate` is the schema migration Cloud Run Job and should run before schema-dependent backend deploys.
* `translation-api` should deploy before `translation-web` when API contracts change.
* Frontend changes in `frontend/services/apiClient.ts` require rebuilding and redeploying `translation-web` before browsers see new API behavior.
* Backend route or internal-task changes require redeploying `translation-api` so task targets like `/v1/transcription/start` and `/v1/internal/tasks/transcribe` are live.

## 7. Gaps to resolve during Phase 0

* Implement or explicitly defer the missing `/projects` API surface currently referenced by the frontend.
* Confirm whether any UI path still expects a bare transcript-segments response instead of the normalized transcript payload returned by `GET /transcription/media/{media_id}`.
* Redeploy `translation-api` so the mounted TTS routes are live in the Cloud Run service.
* Use the completed Phase 0 `/projects` design set and revision-planning artifacts to write the actual Alembic revision, then proceed with backend implementation for tables, router schemas, and service code.
* Normalize legacy naming such as `organization_id`, `storage_provider = s3`, and `s3_upload_id` as part of the tenancy/storage migration plan.
* Confirm whether SSE should replace lip-sync polling first, or only after backend-owned drafts are introduced.

## 8. Phase 0 artifacts now created

The following Phase 0 planning and implementation-prep artifacts now exist:
* [draft-field-mapping.md](#file-2060193141886681)
* [runtime-sequence-diagram.md](#file-2060193141886682)
* [deploy-and-rollback-checklist.md](#file-2060193141886683)
* [validation-checklist.md](#file-2060193141886684)
* [projects-api-examples.md](#file-2060193141886685)
* [projects-router-contract.md](#file-2060193141886686)
* [backend-schema-module-plan.md](#file-2060193141886687)
* [alembic-migration-checklist.md](#file-3212615212764922)
* [alembic-revision-plan.md](#file-3212615212764923)

## 9. Immediate conclusions

* The backend already owns the media-processing pipeline, but not the canonical editor project state.
* The current single biggest migration boundary is moving project and draft persistence out of IndexedDB and into Cloud SQL-backed APIs.
* Existing transcript, translation, generated-audio, and job tables provide a strong relational foundation for Phases 1 through 5.
* The most important unresolved current-state question is the exact boundary between reviewed backend routes and frontend references to project-centric APIs.

## 10. Phase 1 execution update

Phase 1 backend implementation is now in progress and the first project-persistence slice has moved from planning into code.

Completed implementation artifacts:
* Alembic revision `20260829_02_add_projects_and_project_drafts.py` was added under `backend/migrations/versions/`.
* [project.py](#file-/Users/roboplaylab@gmail.com/globesync/backend/app/models/project.py) now defines `Project` and `ProjectDraft` SQLAlchemy models aligned to the approved schema.
* [project_service.py](#file-3264843069231748) now provides workspace-scoped project CRUD, draft save/read flows, optimistic-concurrency conflict handling, and archive behavior.
* [projects.py](#file-3264843069231749) now exposes `GET /projects`, `POST /projects`, `GET /projects/{project_id}`, `PATCH /projects/{project_id}`, `GET /projects/{project_id}/draft`, `PUT /projects/{project_id}/draft`, and `POST /projects/{project_id}/archive`.
* [main.py](#file-3239543912548896) now mounts the `/projects` router under `settings.API_V1_STR`.

Current implementation notes:
* The backend now has a first-class `/projects` API surface instead of only frontend placeholders.
* Service-layer exceptions are kept framework-agnostic and translated into HTTP responses in the router layer.
* `actor_user_id` is currently a required API and service parameter so ownership scoping is explicit now, with a later migration path to replace the query parameter with authenticated request context.
* The draft-save flow now includes version-based conflict detection for `project_drafts` so multi-device and concurrent-edit handling can be enforced at the API boundary.

Next recommended implementation step:
* Add backend API tests for the new `/projects` routes, covering create, list, get, update, draft save, draft conflict (`409`), and archive behavior before wiring the frontend to this contract.

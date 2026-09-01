# GlobeSync Phase 0 Runtime Sequence Diagram

This document captures the current runtime sequence for the GlobeSync editor and media-processing pipeline before backend-owned `projects` and `project_drafts` APIs are introduced.

## Purpose

* Show the current control flow across browser, API, Cloud Tasks, Cloud SQL, and GCS
* Make the IndexedDB-first editor dependency explicit
* Highlight where the backend already owns pipeline execution versus where the browser still owns session state
* Identify sequence gaps that Phase 2 should change during `/projects` cutover

## Scope

This diagram reflects the current reviewed behavior across:

* [page.tsx](#file-3239543912549008)
* [useProject.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/hooks/useProject.ts)
* [projectService.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/services/projectService.ts)
* [apiClient.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/services/apiClient.ts)
* [main.py](#file-3239543912548896)
* [transcription.py](#file-3239543912548912)
* [translation.py](#file-3239543912548913)
* [tts.py](#file-3239543912548914)
* [lipsync.py](#file-3239543912548911)
* [internal_tasks.py](#file-3239543912548910)
* [cloud_tasks_service.py](#file-/Users/roboplaylab@gmail.com/globesync/backend/app/services/cloud_tasks_service.py)
* [current-state-inventory.md](#file-2060193141886680)

## Actors

* Browser editor
* Browser IndexedDB (`project_drafts` object store)
* FastAPI public API (`translation-api`)
* Cloud Tasks
* FastAPI internal task handlers (`/v1/internal/tasks/*`)
* Cloud SQL
* GCS
* External AI providers (Google STT, Deepgram fallback, translation provider, Google TTS, lip-sync provider)

## Current end-to-end sequence

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Editor as Browser editor
    participant IDB as IndexedDB draft store
    participant API as FastAPI public API
    participant DB as Cloud SQL
    participant GCS as GCS buckets
    participant Tasks as Cloud Tasks
    participant Internal as Internal task handlers
    participant Providers as External AI providers

    User->>Editor: Open /editor/[projectId]
    Editor->>IDB: getDraft(projectId)
    alt Draft exists locally
        IDB-->>Editor: HeygenXFile draft payload
        Editor->>Editor: Hydrate Zustand stores
        opt Local transcript segments exist but translations incomplete
            Editor->>API: GET /translation/{transcriptId}?target_language={lang}
            API->>DB: Read persisted translations
            DB-->>API: Translation rows
            API-->>Editor: Translation payload
            Editor->>IDB: Rewrite merged draft payload
        end
    else No local draft
        Editor-->>User: Redirect away from editor
    end

    par Autosave loop
        loop Every 30 seconds
            Editor->>Editor: Rebuild draft from project, segments, translations
            Editor->>IDB: saveDraft(updated payload)
            Note over Editor,IDB: Save failures are logged to console only
        end
    and Upload/transcribe flow
        User->>Editor: Upload source media
        Editor->>API: POST /media/uploads/direct
        API->>DB: Create/update media and upload session rows
        API->>GCS: Register resumable upload target
        API-->>Editor: Upload metadata / target
        Editor->>GCS: Upload media bytes
        User->>Editor: Start transcription
        Editor->>API: POST /transcription/start
        API->>DB: Create or re-queue transcript row
        API->>Tasks: Enqueue transcribe task
        Tasks->>Internal: POST /v1/internal/tasks/transcribe
        Internal->>Internal: Verify Cloud Tasks headers
        Internal->>Providers: Run STT pipeline
        Note over Providers: Google STT primary, Deepgram fallback when no explicit language is provided
        Internal->>GCS: Read staged media as needed
        Internal->>DB: Persist transcript and transcript_segments
        Internal-->>Tasks: Task success/failure
        opt Transcript status refresh
            Editor->>API: GET /transcription/{transcriptId}
            API->>DB: Read transcript and ordered segments
            DB-->>API: Transcript + segments
            API-->>Editor: Normalized transcript payload
            Editor->>IDB: Cache transcript-derived draft state
        end
    end

    User->>Editor: Translate project
    Editor->>API: POST /translation/translate-project
    API->>Tasks: Enqueue translation task
    Tasks->>Internal: POST /v1/internal/tasks/translate-project
    Internal->>Internal: Verify Cloud Tasks headers
    Internal->>DB: Read transcript segments
    Internal->>Providers: Run translation provider
    Internal->>DB: Upsert/replace translation rows per segment and target language
    Internal-->>Tasks: Task success/failure
    Editor->>API: GET /translation/{transcriptId}?target_language={lang}
    API->>DB: Read persisted translations
    DB-->>API: Translation rows
    API-->>Editor: Translation payload
    Editor->>IDB: Cache translated segments in draft

    User->>Editor: Synthesize dubbed audio
    Editor->>API: POST /tts/synthesize-project
    API->>Tasks: Queue TTS work when configured
    Tasks->>Internal: Provider-specific execution path
    Internal->>DB: Read translations
    Internal->>Providers: Google TTS synthesis
    Internal->>GCS: Write segment audio / dubbed artifacts
    Internal->>DB: Persist generated_audios and related output state

    User->>Editor: Start lip-sync render
    Editor->>API: POST /lipsync/render-project
    API->>DB: Create lipsync_jobs row
    API->>Tasks: Enqueue render-lipsync-project task
    Tasks->>Internal: POST /v1/internal/tasks/render-lipsync-project
    Internal->>Internal: Verify Cloud Tasks headers
    Internal->>DB: Read media, transcript, translations, audio references
    Internal->>GCS: Read source media and dubbed assets
    Internal->>Providers: Run lip-sync / render provider
    Internal->>GCS: Write rendered output video
    Internal->>DB: Update lipsync_jobs progress and output path
    loop Poll until complete
        Editor->>API: GET /lipsync/job/{jobId}
        API->>DB: Read current job row
        DB-->>API: Job status, progress, output path
        API-->>Editor: Status + signed output URL when available
    end
    Editor->>IDB: Persist latest local project draft snapshot
```

## Sequence notes by stage

### 1. Editor hydration

* The editor is blocked on local IndexedDB presence rather than backend project existence.
* No reviewed backend `/projects` read occurs during initial page load.
* Device portability is therefore limited to whichever browser has the draft payload.

### 2. Draft persistence

* Draft persistence is full-document rewrite behavior, not patch-based updates.
* `projectMetadata.updatedAt` is updated locally before each save.
* Draft save failures do not currently surface in the user interface.

### 3. Media and transcription

* Backend processing is already async and GCP-native through Cloud Tasks.
* Transcript rows and segment rows are persisted in Cloud SQL and are better positioned than browser state to be canonical.
* The editor still duplicates transcript-derived state back into IndexedDB after retrieval.

### 4. Translation

* Batch translation writes normalized rows to Cloud SQL.
* The editor then rehydrates its own cached translation array from backend results.
* Current batch translation behavior replaces existing rows for the same segment and target language.

### 5. TTS and lip-sync

* Following your GCP-first preference, runtime TTS/STT now centers on Google-managed speech services where possible.
* TTS output and rendered video artifacts land in GCS, while job/output metadata lands in Cloud SQL.
* Lip-sync completion in the editor still depends on polling `GET /lipsync/job/{jobId}` rather than an event-driven project-state channel.

## Current ownership split revealed by the sequence

| Concern | Current authority | Evidence in sequence |
| --- | --- | --- |
| Project/session existence | Browser IndexedDB | Editor load starts with `getDraft(projectId)` and redirects if absent |
| Project metadata | Browser draft mirror | No reviewed `/projects` API on initial load |
| Media binaries | GCS | Upload target and artifact storage are object-backed |
| Pipeline execution | Backend + Cloud Tasks | Async internal task handlers drive processing |
| Transcript segments | Cloud SQL, then cached locally | Persisted in backend, copied back into draft |
| Translation segments | Cloud SQL, then cached locally | Persisted in backend, copied back into draft |
| Lip-sync progress UX | API polling | Repeated `GET /lipsync/job/{jobId}` loop |

## Sequence gaps this artifact makes explicit

* The browser, not Cloud SQL, is still the entrypoint for project existence.
* Canonical project metadata does not yet have a reviewed backend read/write path.
* Transcript and translation state are stored twice: normalized in Cloud SQL and cached inline in drafts.
* Progress delivery is mixed between available SSE endpoints and polling-driven UI behavior.
* There is still no workspace-scoped project container coordinating auth, ownership, draft versioning, and processing pointers.

## What Phase 2 should change

When `/projects` and `/projects/{project_id}/draft` are introduced, the intended sequence shift is:

* page load starts with backend project lookup, not local draft lookup
* server draft payload becomes the primary hydration source
* IndexedDB becomes a cache/fallback layer rather than the system of record
* project metadata stops being browser-authored state
* concurrency moves from silent overwrite to server-enforced draft version checks

## Recommended follow-on artifact

The next useful document after this one is the deployment and rollback checklist, because the runtime sequence now makes it clearer which deploy ordering dependencies matter most:

* `translation-migrate` before schema-dependent API deploys
* `translation-api` before `translation-web` when route contracts change
* frontend cache and local-draft compatibility considerations during cutover

# GlobeSync Phase B/C/D Implementation Guide

Updated: 2026-09-03

## Purpose

This document explains the UI and backend changes made during the Phase B/C/D implementation work. It is intended as a durable reference for what changed, why it changed, how the pieces work together, and what must happen before production rollout.

The detailed issue-by-issue record remains in [ui-compatibility-and-ownership-remediation-log.md](ui-compatibility-and-ownership-remediation-log.md). This guide is the easier starting point for future work.

## Executive Summary

The main goal was to move the editor from frontend-only or placeholder behavior toward backend-owned project persistence without breaking the current editor workflow.

The implementation now:

- Routes project actions through the backend instead of local UI stubs.
- Preserves workspace and authenticated-actor ownership at the backend boundary.
- Keeps mutable editor data in `project_drafts` and immutable checkpoints in `project_versions`.
- Keeps media and rendered-output signed URLs out of project metadata responses.
- Uses dedicated artifact endpoints for playback and waveform audio.
- Prevents unsafe language changes after downstream processing has started.
- Adds cursor pagination, duplicate-project support, version history, risk indicators, and playback synchronization.
- Makes deployment run database migrations before deploying code that depends on them.

## Canonical Ownership Model

| Data or behavior | Canonical owner | Meaning |
| --- | --- | --- |
| Project identity, status, languages, workspace, pipeline pointers | `projects` | Durable project metadata |
| Current mutable editor payload | `project_drafts` | Latest editable state with optimistic versioning |
| Immutable history checkpoints | `project_versions` | Bounded review history and future restore source |
| Media metadata and source playback URL | `media_files` and `/media/{media_id}` | Artifact metadata plus short-lived access URL |
| Transcript segments | Transcript tables | Authoritative transcript data |
| Translations | Translation tables | Authoritative translated segment data |
| Generated audio | Generated-audio records | TTS readiness and audio state |
| Lip-sync and rendered output | Lip-sync/export records | Processing state and output access |
| Offline browser storage | IndexedDB | Cache and fallback only, not canonical state |

This separation prevents expiring URLs, cached arrays, or local editor state from becoming accidental sources of truth.

## What Changed and Why

### 1. Project home actions

Files: [homeShell.tsx](../../frontend/components/homeShell.tsx), [page.tsx](../../frontend/app/page.tsx), [projectService.ts](../../frontend/services/projectService.ts)

The project action menu previously relied on internal handlers or placeholder behavior. Rename, archive, and duplicate now flow through callbacks owned by the page and call the project service.

Impact:

- UI actions now update the canonical backend project.
- Busy and error states remain visible in the home screen.
- The page refreshes project state after mutations.
- Duplicate creates a new independent project shell instead of copying downstream artifacts.

### 2. Status filters and lifecycle wording

The home view includes status filter chips and uses `Planning` for draft projects. This makes project lifecycle state visible without changing the backend status vocabulary.

Backend statuses remain `draft`, `processing`, `completed`, `failed`, and `archived`.

### 3. Project API ownership and pagination

Files: [projects.py](../../backend/app/routers/projects.py), [project_service.py](../../backend/app/services/project_service.py), [projects.py](../../backend/app/schemas/projects.py)

Project reads and writes are workspace-scoped through authenticated request context. Project listing now uses deterministic keyset pagination:

- Sort by `updated_at DESC`, then project UUID descending.
- Return at most `limit` records.
- Fetch one extra record to determine whether another page exists.
- Return an opaque cursor containing the last record's timestamp and UUID.
- Reject malformed cursors with HTTP 422.

This avoids offset drift when projects are updated while a user is paging through the list.

The frontend no longer serializes `workspace_id` or `actor_user_id` into project URLs. Those values are derived from authenticated backend context. The frontend still retains a temporary scope/bootstrap guard for compatibility with the current authentication configuration.

### 4. Draft persistence and optimistic concurrency

The editor saves the current draft through `PUT /v1/projects/{project_id}/draft`.

Each save includes:

- Client draft version.
- Draft schema version.
- Draft payload.
- Optional base project timestamp.
- Optional checkpoint reason.

A stale version returns HTTP 409 with the server version, timestamp, and last-saving actor. This prevents one browser from silently overwriting another browser's edits.

Routine autosave updates `project_drafts` only. Explicit Save and pre-build persistence can create an immutable checkpoint.

### 5. Version history and checkpoint retention

Files: [project.py](../../backend/app/models/project.py), [20260903_09_add_project_versions.py](../../backend/migrations/versions/20260903_09_add_project_versions.py), [20260903_10_bound_project_version_snapshots.py](../../backend/migrations/versions/20260903_10_bound_project_version_snapshots.py), [20260903_11_normalize_project_version_hashes.py](../../backend/migrations/versions/20260903_11_normalize_project_version_hashes.py)

`project_versions` stores immutable draft snapshots. The list endpoint returns metadata only; the detail endpoint returns the full payload when needed.

Checkpoint rules:

- No checkpoint for ordinary autosave.
- Checkpoint reasons are recorded, such as `manual_save` or `pre_build`.
- Payloads are normalized and hashed with SHA-256.
- Equal consecutive payloads are not duplicated.
- Legacy migrated rows are also compared by payload during the transition.
- The latest 50 versions per project are retained.
- Current draft update and checkpoint creation occur in the same database transaction.

The follow-up migration `20260903_11` rewrites old MD5-style hashes using the exact runtime canonical JSON algorithm. Apply revisions `20260903_09`, `20260903_10`, and `20260903_11` in order.

### 6. Read-only history UI

The editor history panel loads version metadata lazily and displays version/timestamp information. It does not restore snapshots yet.

Restore is intentionally deferred because it must define:

- Whether normalized transcript and translation tables are also changed.
- How dirty local edits are preserved.
- How concurrent draft edits are detected.
- How a restore checkpoint and audit record are created.

### 7. Language-pair safety

Files: [page.tsx](../../frontend/app/page.tsx), [page.tsx](../../frontend/app/editor/[projectId]/page.tsx)

Language swapping is allowed for untouched projects. Once media, transcript, translation, or output work exists, the editor blocks an in-place language change and offers a safe new-project fallback.

The duplicate flow creates a new draft shell with the language pair but does not share media, transcript, translation, lip-sync, or export pointers.

A destructive reset endpoint is not implemented. This is intentional: silently clearing downstream work would be unsafe. An in-place reset should only be added if product requirements demand it and must include confirmation, concurrency checks, active-job protection, artifact supersession, pointer clearing, and an atomic audit/checkpoint operation.

### 8. Media playback ownership

Files: [upload.py](../../backend/app/routers/upload.py), [projectService.ts](../../frontend/services/projectService.ts), [page.tsx](../../frontend/app/editor/[projectId]/page.tsx)

Project list/detail responses expose media and output identifiers or storage paths, not signed playback URLs.

Playback flow:

1. Load the canonical project and obtain `media_file_id`.
2. Request media details from `GET /v1/media/{media_id}` when playback is needed.
3. Use the returned short-lived `media_url` for the source player.
4. Request rendered output through the dedicated lip-sync/job endpoint.

This prevents expired signed URLs from being stored as durable project state.

### 9. Waveform audio extraction

Video URLs are not reliable inputs for browser `AudioContext.decodeAudioData()`. The backend now exposes `GET /v1/media/{media_id}/audio`.

On a cache miss, the endpoint:

1. Downloads the source media to temporary storage.
2. Extracts speech audio to WAV with FFmpeg.
3. Converts WAV to browser-compatible MP3.
4. Uploads the MP3 under `waveforms/{media_id}.mp3`.
5. Returns a signed audio URL.

On later requests, the cached MP3 is reused. Tests cover cache hits plus cache-miss extraction for video and audio-only inputs.

### 10. Editor playback and review controls

The editor now supports:

- Up/Down segment navigation.
- Segment looping.
- Pointer scrubbing.
- Active segment selection derived from playback time.
- Auto-scroll to the active segment.
- Original/dubbed comparison controls.
- Missing-audio and failed-lip-sync risk badges.
- Reloading source and rendered URLs through dedicated endpoints.
- Explicit Save and pre-build checkpoint reasons.

These changes keep the visible editor state aligned with canonical playback and processing state.

### 11. Generated-audio compatibility

The single-segment translation query and project translation query eagerly load `Translation.generated_audio` with `selectinload`.

This avoids async SQLAlchemy lazy-loading failures such as `MissingGreenlet` when formatting a translation response. The response exposes `generated_audio_status` as optional so records without audio remain valid.

### 12. Deployment ordering

Files: [deploy-cloudrun.sh](../../deploy/deploy-cloudrun.sh), [deploy-cloudrun.ps1](../../deploy/deploy-cloudrun.ps1), [deploy-api-only.sh](../../deploy/deploy-api-only.sh)

Deployment order is:

1. Build the API image.
2. Run the `translation-migrate` Cloud Run Job with `alembic upgrade head`.
3. Wait for migration completion.
4. Deploy the API.
5. Build and deploy the web application.

The PowerShell deployment now stops if migration job creation or execution returns a non-zero exit code. This prevents the API from deploying against a database missing `project_versions`.

## Process Impact

### Creating or editing a project

The project shell is created first in `projects`. The editor then loads or seeds a draft. Local IndexedDB may be used as a fallback, but backend data is authoritative when available.

### Autosaving

Autosave updates the current draft and advances its optimistic version. It does not create history noise. A conflict produces a structured 409 response that the UI can use to recover safely.

### Explicit Save or Build

Explicit Save and pre-build persistence can create a checkpoint. Repeated saves with the same normalized payload do not create duplicate snapshots. History is automatically bounded at 50 versions per project.

### Playing media

Project metadata is loaded first. Signed media URLs are requested only when playback is needed, reducing expiry-related failures and keeping URL ownership with artifact endpoints.

### Changing languages

Changing languages before downstream work is a normal project update. Changing languages after downstream work is blocked; users must create a new project unless a future destructive reset workflow is explicitly approved.

### Deploying

A migration is a prerequisite for the backend release. The migration job must finish successfully before API instances are updated. If the migration cannot run, do not deploy snapshot-writing backend code.

## Validation Completed

Focused validation completed during the session:

- Project API suite: 14 passed.
- Project/version checkpoint suite: 18 passed in the final hash-compatibility run.
- Media route suite: 4 passed.
- Translation pipeline suite: 13 passed.
- Combined project/version/media suite: 20 passed in an earlier validation run.
- Frontend TypeScript check passed.
- Frontend production build passed.
- Backend compilation passed.
- PowerShell deployment script parse passed.
- Alembic offline SQL generation passed through `20260903_11`.
- Workspace diagnostics reported no errors in touched files.
- `git diff --check` passed; only existing line-ending conversion warnings were reported.

The frontend package does not currently define an npm test runner, so its existing test files are not automatically executed by a package script.

## Known Limitations and Next Actions

1. Run live migrations against a disposable PostgreSQL database and verify upgrade/downgrade behavior.
2. Add database integration tests for draft save, checkpoint creation, deduplication, retention, transaction rollback, and workspace isolation.
3. Remove generated `frontend/tsconfig.tsbuildinfo` from the final source diff if it is not intentionally tracked.
4. Triage the 13 failures in the full backend suite. The observed failures include shared SQLAlchemy mapper/import setup issues, stale direct-route test contracts, and an authentication fixture failure.
5. Run authenticated browser smoke tests for project loading, draft save/conflict recovery, source playback, waveform loading, translation, TTS, lip-sync, and history.
6. Keep destructive language reset and snapshot restore disabled until their lifecycle and concurrency contracts are approved.

## Quick Reference

When changing this system, ask:

- Does this data belong to `projects`, `project_drafts`, `project_versions`, or a normalized pipeline table?
- Is this URL short-lived artifact access or durable project metadata?
- Does this write need optimistic concurrency?
- Should this action create a checkpoint, and what reason should it record?
- Does the action invalidate downstream work?
- Is the request scoped by authenticated workspace context?
- Does deployment apply migrations before code that depends on them?

For the detailed audit trail, see [ui-compatibility-and-ownership-remediation-log.md](ui-compatibility-and-ownership-remediation-log.md).

# GlobeSync Phase 3 Normalization Gap Inventory

This document inventories the remaining gap between editor-shaped draft state and normalized backend workflow state for Phase 3, using the current GlobeSync repo as the source of truth.

## Purpose

* identify which fields still live only in `project_drafts.draft_payload`
* identify which records are already canonical in Cloud SQL pipeline tables
* surface duplicated state that should be removed from draft-only assumptions over time
* define the normalization backlog before additive schema changes begin

## Current context

Following your preferences, this inventory starts from the current GlobeSync state:

* Phase 1 and Phase 2 are complete
* `projects` and `project_drafts` exist and are workspace-scoped
* backend-first draft loading is in place, with IndexedDB retained only as compatibility cache
* media pipeline outputs still live in the existing operational tables and must not be replaced abruptly
* `project_service.py` already merges canonical project data back into draft payload under `projectMetadata` and `mediaReferences`

## Canonical tables already in use

* `projects`
* `project_drafts`
* `media_files`
* `upload_sessions`
* `upload_chunks`
* `transcripts`
* `transcript_segments`
* `translations`
* `generated_audios`
* `lipsync_jobs`
* `export_jobs`

## Current draft payload shape

The current frontend draft shape in [storageService.ts](#file-3239543912549053) is still compact but carries both transient and semi-canonical data:

* `projectMetadata`
* `mediaReferences`
* `translations`
* `timelineState`

Within that shape, the most important duplicated backend-facing sections are:

* `projectMetadata.id`
* `projectMetadata.name`
* `projectMetadata.sourceLanguage`
* `projectMetadata.targetLanguage`
* `projectMetadata.createdAt`
* `projectMetadata.updatedAt`
* `mediaReferences.videoFilename`
* `mediaReferences.durationSeconds`
* `mediaReferences.transcriptId`
* `mediaReferences.mediaId`
* `mediaReferences.originalTranscriptSegments`
* `translations`

## Gap categories with repo findings

### 1. Project metadata and identity

Current canonical source:

* `projects` already owns project identity, owner, creator, status, language pair, active translation language, and current media/transcript/lipsync/export pointers

Current duplication or gap:

* `projectMetadata` in draft payload mirrors project identity fields for frontend convenience
* `last_opened_at` and `archived_at` exist on `projects`, but there is no version history yet
* `projects` has no direct pointer to a current translation grouping or a current generated-audio grouping

Phase 3 direction:

* keep canonical project identity in `projects`
* continue treating `projectMetadata` inside drafts as a compatibility mirror only
* decide whether active translation remains language-based or gains an explicit canonical pointer later

### 2. Media and transcript lineage

Current canonical source:

* `projects.media_file_id` points to the active source media
* `transcripts.media_file_id` is the concrete foreign key from transcript to media
* `projects.transcript_id` points to the active transcript
* `upload_sessions.media_file_id` points to the created media row after upload completion

Current duplication or gap:

* `mediaReferences.mediaId`, `mediaReferences.transcriptId`, `mediaReferences.videoFilename`, and `mediaReferences.durationSeconds` duplicate backend state in draft payload
* `media_files.project_id` and `workspace_id` are nullable and not foreign keyed
* `transcripts.project_id` and `workspace_id` are nullable and not foreign keyed
* `upload_sessions` has `workspace_id` and `user_id`, but no direct `project_id`
* `upload_chunks` inherit scope only through `upload_sessions`

Phase 3 direction:

* preserve the existing `projects -> media_files -> transcripts` chain
* tighten relational integrity around project/workspace scope rather than introducing a new media abstraction
* keep upload-session scope derived through the session unless a concrete project-level need appears

### 3. Transcript state

Current canonical source:

* `transcript_segments` are canonical child rows of `transcripts`
* route reads already order transcript segments by `sequence_order`

Current duplication or gap:

* `mediaReferences.originalTranscriptSegments` in draft payload can carry a cached transcript copy for the editor
* there is no uniqueness constraint on `(transcript_id, sequence_order)`
* transcript segments lack provenance fields for user edits or later correction lineage

Phase 3 direction:

* keep transcript segments canonical in relational storage
* allow cached transcript segments in drafts temporarily for UI hydration and offline recovery
* add uniqueness and provenance in additive schema slices

### 4. Translation state

Current canonical source:

* `translations` are stored per `transcript_segment_id`
* project-wide translation reads currently resolve as transcript segments plus `target_language`
* single-segment translation writes upsert in application code by `(transcript_segment_id, target_language)`

Current duplication or gap:

* draft payload still has a top-level `translations` array for editor consumption
* there is no transcript-level translation-set parent table
* there is no database-level uniqueness constraint enforcing the application's current upsert boundary
* there is no explicit run identity for repeated translation attempts for the same language

Phase 3 direction:

* keep the current canonical grouping at transcript plus target language unless a concrete run-history requirement forces a new parent entity
* after legacy duplicate cleanup, treat one current translation row per `(transcript_segment_id, target_language)` as the intended Phase 3 steady-state model
* treat draft `translations` as a compatibility cache, not the durable source of truth
* add schema support for uniqueness after validating legacy data, and defer supersession metadata or parent-run modeling unless retained run history becomes a confirmed requirement

### 5. Generated audio, lip-sync, and export state

Current canonical source:

* `generated_audios.translation_id` links synthesized audio to translations
* `lipsync_jobs` and `export_jobs` are canonical job rows with concrete media and transcript foreign keys
* `projects.current_lipsync_job_id`, `projects.current_export_job_id`, and `projects.last_rendered_video_gcs_path` already give the project a latest-known rendering path

Current duplication or gap:

* there is no current generated-audio pointer on `projects`
* there is no generated-audio parent set or dubbing-run entity
* master dubbed audio is still addressed by GCS path convention rather than a relational parent record
* job retries can create multiple rows or artifacts without an explicit idempotency key strategy

Phase 3 direction:

* keep generated audio query-derived through `translations -> generated_audios`
* keep current lip-sync and export pointers on `projects`
* add idempotency and correlation support before considering any larger job-parent abstractions

### 6. Draft-only editor state

Current canonical source:

* `timelineState` is currently UI state, not a backend business record
* editor hydration intentionally uses drafts plus canonical project metadata, not pure normalized segment-by-segment reconstruction yet

Current duplication or gap:

* `timelineState` is rightly draft-shaped
* cached transcript and translation arrays in the draft payload still blur the line between UI cache and canonical workflow state
* there is no explicit documentation yet for which draft sections are temporary compatibility copies versus intentionally transient UI state

Phase 3 direction:

* keep `timelineState` and other UI session details in `project_drafts`
* document draft-only versus canonical sections explicitly and reduce duplication only after relational reads are validated

### 7. Integrity and lifecycle gaps

Current canonical source:

* authorization already enforces workspace/project-scoped access across routes
* Phase 2 backfill populated many missing `project_id` and `workspace_id` values across pipeline tables

Current duplication or gap:

* several downstream tables still keep `project_id` and `workspace_id` nullable in the model
* many downstream scope columns are not yet enforced by foreign keys
* there is no `project_versions` table
* there is no `audit_logs` table
* there is no common idempotency or correlation-key foundation across translation, audio, lip-sync, and export writes

Phase 3 direction:

* add integrity protections only after validating current data
* add audit and versioning foundations as append-only structures
* keep draft-save audit capture intentionally narrow in Phase 3, favoring checkpoints, conflicts, and restore-worthy events rather than every autosave heartbeat
* introduce correlation or idempotency support where retries can create duplicate records or ambiguous state

## Working inventory table

| Area | Current canonical source | Draft-only fields still present | Duplicated state | Missing schema or rule | Phase 3 action |
| --- | --- | --- | --- | --- | --- |
| Project metadata | `projects` | none required | `projectMetadata.*` mirror | no project version history; no explicit current translation-set pointer beyond `active_translation_language` | keep `projects` canonical; leave draft mirror temporary |
| Media lineage | `projects.media_file_id`, `media_files`, `upload_sessions.media_file_id` | none required | `mediaReferences.mediaId`, `videoFilename`, `durationSeconds` | nullable `project_id`/`workspace_id`; no FK from media to project | validate and tighten scope consistency |
| Transcript state | `projects.transcript_id`, `transcripts`, `transcript_segments` | cached segment copy may remain | `mediaReferences.transcriptId`, `originalTranscriptSegments` | no uniqueness on `(transcript_id, sequence_order)`; no provenance fields | add ordering integrity and provenance |
| Translation state | `translations` | cached editor translations may remain | draft `translations` array | no DB uniqueness for one current row per `(transcript_segment_id, target_language)`; no translation-set parent; legacy duplicates may need cleanup | formalize grouping, clean duplicates, add uniqueness, and defer supersession fields unless retained history is required |
| Generated audio | `generated_audios` | none required | none in canonical project model | no active-set parent or idempotency key | keep query-derived; add idempotency support |
| Lip-sync jobs | `lipsync_jobs`, `projects.current_lipsync_job_id` | none required | none required | scope columns nullable; no same-scope pointer enforcement | validate and tighten pointer integrity |
| Export jobs | `export_jobs`, `projects.current_export_job_id` | none required | none required | scope columns nullable; no same-scope pointer enforcement | validate and tighten pointer integrity |
| Draft-only UI state | `project_drafts.timelineState` | yes | some cached transcript and translation content | boundary between cache and business state not fully documented | keep UI state in drafts; shrink cache over time |
| Lifecycle and audit | partial on `projects` only | none | none | no `project_versions`, no `audit_logs`, no replay-safe correlation pattern, and no implementation yet for the intended reduced-granularity draft-save audit policy | add append-only foundation with narrow initial audit triggers |

## Prioritized normalization backlog

1. Lock the canonical project-to-media-to-transcript-to-translation-to-generated-audio traversal model.
2. Document the exact draft sections that are cache versus durable business state.
3. Add integrity support for transcript ordering and translation upsert boundaries, targeting one current translation row per segment-language pair after duplicate cleanup.
4. Add correlation and idempotency support for retried workflow writes.
5. Introduce append-only `project_versions` and `audit_logs`, with narrow initial audit triggers rather than per-autosave noise.
6. Tighten nullable ownership and pointer constraints only after data validation confirms safety.

## Expected outputs from this artifact

* a prioritized list of normalization gaps
* a list of fields that remain in `project_drafts` temporarily
* a list of additive schema changes needed next
* a dependency map for the rest of Phase 3

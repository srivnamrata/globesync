# GlobeSync Phase 0 Draft Field Mapping

This document maps the current browser-local `HeygenXFile` draft contract to the planned backend-owned persistence model on GCP.

## Purpose

* Preserve the current editor behavior while moving canonical state to Cloud SQL
* Minimize frontend cutover risk by keeping the first backend draft payload close to the current IndexedDB shape
* Identify which fields should become normalized relational columns versus temporary draft JSON
* Identify where backfill or dual-write will be required during migration

## Source contracts reviewed

* [storageService.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/services/storageService.ts)
* [useProject.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/hooks/useProject.ts)
* [page.tsx](#file-3239543912549008)
* [projectStore.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/store/projectStore.ts)
* [mediaStore.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/store/mediaStore.ts)
* [translationStore.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/store/translationStore.ts)
* [current-state-inventory.md](#file-2060193141886680)
* [GCP_MULTI_TENANT_MIGRATION_PLAN.md](#file-2060193141886677)

## Mapping principles

* Canonical ownership, identity, and status belong in `projects`
* Canonical media, transcript, translation, generated audio, lip-sync, and export state stay in their normalized backend tables
* UI-shaped, high-churn editor session data can remain in `project_drafts.draft_payload` during the transition
* Browser IndexedDB becomes cache-only after backend draft save/load is introduced
* Every canonical row should eventually be scoped by `workspace_id` and linked to `project_id`

## Target persistence buckets

| Target | Role | Examples |
| --- | --- | --- |
| `projects` | Canonical project identity and top-level workflow state | name, language pair, current media/transcript pointers, status |
| `project_drafts.draft_payload` | Editor-session and compatibility payload | timeline state, selected segment, cached segment arrays, UI layout |
| Existing normalized tables | Canonical pipeline records | `media_files`, `transcripts`, `transcript_segments`, `translations`, `generated_audios`, `lipsync_jobs`, `export_jobs` |
| Derived or deprecated | Temporary compatibility-only copies to remove later | inline `originalTranscriptSegments`, inline `translations` copies |

## Current `HeygenXFile` to future model mapping

| Current field | Current meaning | Future canonical home | Migration treatment | Notes |
| --- | --- | --- | --- | --- |
| `version` | Frontend draft format version | `project_drafts.draft_schema_version` and `draft_payload.version` | Dual-write initially | Keep in payload for compatibility; also persist as top-level schema/version metadata |
| `projectMetadata.id` | Project identity used as IndexedDB key | `projects.id` | Backfill and become canonical | This should stop being browser-generated only once `POST /v1/projects` exists |
| `projectMetadata.name` | Project display name | `projects.name` | Canonicalize immediately | Keep mirrored in draft payload during cutover to avoid breaking hydration |
| `projectMetadata.sourceLanguage` | Source language code | `projects.source_language` | Canonicalize immediately | Draft copy can remain as convenience during transition |
| `projectMetadata.targetLanguage` | Active target language code | `projects.target_language` | Canonicalize immediately | If multiple targets are later supported, project default stays here |
| `projectMetadata.createdAt` | Project creation timestamp | `projects.created_at` | Canonicalize immediately | If missing or client-generated, overwrite with server timestamp on first project create |
| `projectMetadata.updatedAt` | Last local draft write time | `projects.updated_at` plus `project_drafts.updated_at` | Split meaning | Project-level updates belong in `projects`; draft save time belongs in `project_drafts` |
| `mediaReferences.videoFilename` | Source video filename or URL-like reference | `media_files.original_filename` and pointer via `projects.media_file_id` | Backfill from linked media | Keep temporary draft copy for editor display if needed |
| `mediaReferences.durationSeconds` | Computed media duration | `media_files.duration_seconds` | Backfill from media row | Do not make draft JSON authoritative for duration once media exists |
| `mediaReferences.originalTranscriptSegments` | Inline cached transcript segment array | `transcript_segments` | Compatibility-only cache | Keep in `draft_payload` initially for low-risk hydration, then remove after backend-first transcript load is stable |
| `mediaReferences.transcriptId` | Transcript pointer | `projects.transcript_id` and `transcripts.id` | Canonicalize immediately | Keep draft copy during compatibility phase |
| `mediaReferences.mediaId` | Media pointer | `projects.media_file_id` and `media_files.id` | Canonicalize immediately | Keep draft copy during compatibility phase |
| `translations` | Inline translated segment array used by editor | `translations` table | Compatibility-only cache | Keep in `draft_payload` during first cut; backend rows remain authoritative |
| `timelineState.markers` | Timeline/editor marker state | `project_drafts.draft_payload.timelineState.markers` | Keep in draft JSON | Normalize later only if collaboration/versioning requires it |
| `timelineState.zoomLevel` | Editor zoom preference | `project_drafts.draft_payload.timelineState.zoomLevel` | Keep in draft JSON | Pure UI state, not a canonical project field |

## Zustand store to backend mapping

### `Project` store fields

| Frontend store field | Future home | Treatment | Notes |
| --- | --- | --- | --- |
| `id` | `projects.id` | Canonicalize immediately | Primary project reference across editor/API |
| `name` | `projects.name` | Canonicalize immediately | Mirror into draft payload only for compatibility |
| `sourceLanguage` | `projects.source_language` | Canonicalize immediately | |
| `targetLanguage` | `projects.target_language` | Canonicalize immediately | |
| `status` | `projects.status` | Canonicalize immediately | Do not let local draft overwrite server pipeline state without explicit rules |
| `createdAt` | `projects.created_at` | Canonicalize immediately | |
| `updatedAt` | `projects.updated_at` | Canonicalize immediately | Distinguish from draft save timestamp |
| `transcriptId` | `projects.transcript_id` | Canonicalize immediately | |
| `mediaId` | `projects.media_file_id` | Canonicalize immediately | |
| `originalVideoUrl` | Derived from `media_files` or signed URL generation | Derive, do not store as canonical project field | Optional cache in draft payload if required for UX |
| `dubbedAudioUrl` | Derived from `generated_audios` or master dubbed output | Derive, do not store as canonical project field | Better exposed by dedicated output endpoints |

### `TranscriptSegment` store fields

| Frontend store field | Future home | Treatment | Notes |
| --- | --- | --- | --- |
| `id` | `transcript_segments.id` | Already canonical | |
| `sequenceOrder` | `transcript_segments.sequence_order` | Already canonical | |
| `startTimeSeconds` | `transcript_segments.start_time_seconds` | Already canonical | |
| `endTimeSeconds` | `transcript_segments.end_time_seconds` | Already canonical | |
| `durationSeconds` | `transcript_segments.duration_seconds` | Already canonical | |
| `speakerTag` | `transcript_segments.speaker_tag` | Already canonical | |
| `text` | `transcript_segments.text` | Already canonical | If the editor later supports transcript edits, update the normalized row rather than draft-only copies |
| `confidence` | `transcript_segments.confidence` | Already canonical | |

### `TranslatedSegment` store fields

| Frontend store field | Future home | Treatment | Notes |
| --- | --- | --- | --- |
| `id` | `translations.id` | Already canonical | |
| `transcriptSegmentId` | `translations.transcript_segment_id` | Already canonical | |
| `translatedText` | `translations.translated_text` | Already canonical | Editor save path should update the normalized row and optionally refresh cached draft payload |
| `originalDurationMs` | `translations.original_duration_ms` | Already canonical | |
| `estimatedDurationMs` | `translations.estimated_duration_ms` | Already canonical | |
| `durationRatio` | `translations.duration_ratio` | Already canonical | |
| `speedAdjustmentFactor` | `translations.speed_adjustment_factor` | Already canonical | |
| `qualityScore` | `translations.quality_score` or `confidence_score` depending API contract | Confirm and align | Frontend currently consumes `confidence_score`; schema design should standardize the returned field |
| `status` | Derived from translation job state or optional row status | Likely derived, not draft-authoritative | Current relational row does not carry the same simple UI status enum |

## What should stay in draft JSON first

These fields should remain in `project_drafts.draft_payload` during the first backend cutover because they are UI-shaped, volatile, or still duplicated for compatibility:

* `version`
* `projectMetadata` mirror block
* `mediaReferences.videoFilename`
* cached `mediaReferences.originalTranscriptSegments`
* cached `translations`
* `timelineState.markers`
* `timelineState.zoomLevel`
* future `uiState` keys such as selection, panel layout, or filters

## What should become canonical immediately

These fields should move behind backend-owned project APIs as soon as `/projects` and `/projects/{projectId}/draft` exist:

* project identity and timestamps
* project name
* source and target language
* project status
* linked `media_file_id`
* linked `transcript_id`
* workspace and owner identity

## Backfill and dual-write rules

### First migration pass

* Create a canonical `projects` row for every active browser-resident draft that is promoted into backend persistence
* Save the original draft payload into `project_drafts.draft_payload` with minimal transformation
* Populate `projects.media_file_id` and `projects.transcript_id` from existing draft references when they point to valid backend rows

### Dual-write period

* Frontend saves should write to backend `PUT /v1/projects/{projectId}/draft`
* The same payload may still be cached in IndexedDB for offline resilience
* Project metadata updates should update both `projects` and the mirrored draft block until the frontend no longer depends on the mirror
* Transcript and translation edits should update normalized tables first, then refresh any cached draft arrays if those arrays are still present

### Backfill constraints to add later

* Make `projects.workspace_id` non-null once auth/workspace bootstrap is complete
* Make dependent pipeline tables carry non-null `project_id` and `workspace_id`
* Remove nullable ownership drift such as legacy `organization_id` once workspace ownership is authoritative

## Known gaps and decisions still needed

* Confirm whether `translations.quality_score` or `translations.confidence_score` should drive the frontend `qualityScore` field consistently
* Decide whether transcript segment arrays should stay in draft JSON for one release or be removed immediately after backend hydration is implemented
* Decide whether project creation happens before upload or is created lazily during the first successful upload/transcription action
* Confirm whether project archive state should live only in `projects.status` or also in a separate `archived_at` timestamp

## Recommended next step

After this mapping, the next artifact should define the exact request and response examples for:
* `POST /v1/projects`
* `GET /v1/projects/{project_id}`
* `GET /v1/projects/{project_id}/draft`
* `PUT /v1/projects/{project_id}/draft`

That API example document will let the frontend cutover proceed without reinterpreting this mapping during implementation.

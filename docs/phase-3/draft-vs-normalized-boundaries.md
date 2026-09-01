# GlobeSync Phase 3 Draft vs Normalized Boundaries

This document defines which editor state should remain in `project_drafts` during Phase 3 and which state should move to normalized backend tables, based on the current GlobeSync frontend and backend payload shape.

## Purpose

* prevent `project_drafts.draft_payload` from remaining the accidental source of truth for stable workflow data
* preserve low-risk editor compatibility while normalization progresses underneath the UI
* give backend and frontend work a shared rule set for what belongs in draft JSON versus relational storage

## Current payload baseline

Following your preferences, the current draft shape in [storageService.ts](#file-3239543912549053) is:

* `projectMetadata`
* `mediaReferences`
* `translations`
* `timelineState`

The current backend draft service in [project_service.py](#file-3264843069231748) explicitly merges canonical project data back into `projectMetadata` and `mediaReferences`, which means those sections are already treated as compatibility mirrors of relational state.

## Boundary principles

Following your preferences, these rules apply:

* stable business records belong in canonical relational tables
* transient, UI-shaped, or conflict-prone session state may stay in `project_drafts`
* draft payload may temporarily cache canonical data for hydration convenience, but that copy is not authoritative
* duplicated state should be removed only after canonical read paths are live and validated

## State that should remain draft-shaped in Phase 3

Repo-specific examples:

* `timelineState.markers`
* `timelineState.zoomLevel`
* selected segment or cursor position if stored later in the draft blob
* panel open or closed state if stored later in the draft blob
* speaker or view filters that are session-specific
* optimistic or temporary UI flags not required for shared backend truth
* offline recovery payload used to restore an in-progress local session

## State that should be normalized or read canonically

Repo-specific examples:

* `projectMetadata.id`, `name`, `sourceLanguage`, `targetLanguage`, `createdAt`, and `updatedAt`
* project owner and workspace scope
* `mediaReferences.mediaId`, `transcriptId`, `videoFilename`, and `durationSeconds`
* transcript segments and their ordering
* translated segment outputs and their canonical grouping
* generated audio metadata in `generated_audios`
* lip-sync job metadata and status in `lipsync_jobs`
* export job metadata and status in `export_jobs`
* archival, provenance, and version-related metadata

## Transitional allowances

These cases may remain in draft payload temporarily during Phase 3:

* `mediaReferences.originalTranscriptSegments` as a cached editor-friendly transcript copy
* top-level `translations` as a cached editor-friendly translation array
* UI-composed structures that merge several backend resources into one editor-friendly blob

Conditions for temporary duplication:

* the canonical backend source must be identified explicitly
* the draft copy must be treated as replaceable cache, not durable truth
* removal should happen only after compatibility testing proves the relational read path works

## Canonical-versus-draft mapping

| Draft payload field or section | Current role | Canonical source | Phase 3 boundary |
| --- | --- | --- | --- |
| `projectMetadata.id` | duplicated identifier | `projects.id` | normalize |
| `projectMetadata.name` | duplicated project label | `projects.name` | normalize |
| `projectMetadata.sourceLanguage` | duplicated project field | `projects.source_language` | normalize |
| `projectMetadata.targetLanguage` | duplicated project field | `projects.target_language` | normalize |
| `projectMetadata.createdAt` | duplicated project field | `projects.created_at` | normalize |
| `projectMetadata.updatedAt` | duplicated project field | `projects.updated_at` | normalize |
| `mediaReferences.mediaId` | duplicated media pointer | `projects.media_file_id` / `media_files.id` | normalize |
| `mediaReferences.transcriptId` | duplicated transcript pointer | `projects.transcript_id` / `transcripts.id` | normalize |
| `mediaReferences.videoFilename` | duplicated media attribute | `media_files.original_filename` | normalize |
| `mediaReferences.durationSeconds` | duplicated media attribute | `media_files.duration_seconds` | normalize |
| `mediaReferences.originalTranscriptSegments` | editor cache of transcript content | `transcript_segments` | temporary cache |
| `translations` | editor cache of translation content | `translations` | temporary cache |
| `timelineState` | UI-only interaction state | none | keep in drafts |

## Boundary table

| State category | Keep in `project_drafts` | Normalize in relational tables | Transitional duplication allowed | Notes |
| --- | --- | --- | --- | --- |
| Project metadata | No | Yes | Limited | already merged from `projects` on draft reads and writes |
| Workspace and owner scope | No | Yes | No | auth root |
| Media identifiers and metadata | No | Yes | Limited | draft may mirror for hydration only |
| Transcript segment cache | Temporary | Yes | Yes | currently represented by `mediaReferences.originalTranscriptSegments` |
| Translation segment cache | Temporary | Yes | Yes | currently represented by top-level `translations` |
| Timeline viewport state | Yes | No | No | UI-only |
| Panel state and filters | Yes | No | No | UI-only even if later added to draft payload |
| Generated audio outputs | No | Yes | Limited | canonical backend record |
| Lip-sync and export jobs | No | Yes | Limited | canonical backend record |
| Audit and version metadata | No | Yes | No | append-only backend tables |

## Recommended removal order for duplicated draft data

1. Keep `projectMetadata` and `mediaReferences` duplicated until every editor read path is confirmed to hydrate from canonical project and media rows first.
2. Reduce reliance on `mediaReferences.originalTranscriptSegments` once transcript reads can be reconstructed cheaply from `transcript_segments`.
3. Reduce reliance on draft `translations` after the transcript-plus-language translation grouping is frozen and validated.
4. Keep `timelineState` in drafts throughout Phase 3.

## Removal triggers for duplicated draft data

A duplicated draft section can be removed when all of the following are true:

* a canonical relational read path exists
* the editor can hydrate successfully from the canonical path first
* regression checks confirm no behavior loss
* offline recovery semantics remain acceptable without making the draft authoritative

## Questions this artifact should answer

* which current draft fields are only UI convenience
* which current draft fields are silently acting like business state
* which duplicated payload sections are safe to remove earliest
* which frontend reads must change before a duplicated section can be removed

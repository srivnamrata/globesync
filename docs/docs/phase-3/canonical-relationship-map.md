# GlobeSync Phase 3 Canonical Relationship Map

This document defines the target relationship model for Phase 3 using the current GlobeSync schema and route behavior as the starting point, without forcing a destructive rewrite of the current pipeline tables.

## Purpose

* define the authoritative project-centric navigation path across normalized workflow records
* document which relationships already exist in the repo and which remain indirect or weakly enforced
* prevent ambiguous ownership or pointer rules during additive schema work
* give backend and frontend changes a common canonical map grounded in the current implementation

## Relationship design principles

Following your preferences, the relationship model for GlobeSync should:

* preserve the existing pipeline tables while improving relational clarity around them
* anchor authorization and data traversal at `workspace_id` and `project_id`
* keep `projects` small and pointer-oriented rather than segment-heavy
* store stable business state canonically in relational tables, while keeping transient UI state in `project_drafts`
* prefer additive pointers and provenance fields before any constraint tightening

## Current repo findings

The current Phase 2 implementation already gives GlobeSync a usable canonical root:

* `projects` now carries direct pointers to `media_files`, `transcripts`, `lipsync_jobs`, and `export_jobs`
* `project_drafts` is a one-row-per-project latest-draft table keyed by `project_id`
* `project_service.py` merges canonical `projects` fields back into `draft_payload.projectMetadata` and `draft_payload.mediaReferences`, so those sections are duplicated convenience views rather than an independent data model
* `translations` are currently addressed operationally as all rows for a transcript's segments plus `target_language`; there is no explicit translation-set parent table yet
* `generated_audios` is the actual table name in the backend model, even though the product language usually says generated audio in the singular
* downstream tables still rely heavily on nullable `project_id` and `workspace_id` columns plus route-time authorization checks, rather than full relational enforcement

## Core canonical entities

### Current implemented entities

* `workspaces`
* `workspace_members`
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

### Phase 3 target additions

* `project_versions`
* `audit_logs`

## Recommended top-level ownership chain

* `workspaces` own `projects`
* `projects` are the canonical root for editor-facing workflow state
* `project_drafts` remains the latest editor-session representation for a project, but not the canonical source for stable workflow records
* downstream pipeline records should be attributable to both `workspace_id` and `project_id`
* request authorization should resolve from project and workspace scope, not from legacy user-only ownership

## Current implemented pointer model

### `projects`

Current direct pointers already present on `projects`:

* `media_file_id`
* `transcript_id`
* `active_translation_language`
* `current_lipsync_job_id`
* `current_export_job_id`
* `last_rendered_video_gcs_path`

Current query-derived relationships:

* translations for a project, resolved through `project.transcript_id -> transcript_segments -> translations`
* generated audio for a project, resolved through `translations -> generated_audios`
* historical lip-sync jobs and export jobs beyond the current pointers
* draft history, versions, and audits

## Recommended canonical traversal path

For Phase 3, the authoritative project-centric traversal should be:

1. `workspaces.id -> projects.workspace_id`
2. `projects.id -> project_drafts.project_id` for the latest editor draft only
3. `projects.media_file_id -> media_files.id` for the primary source media path
4. `projects.transcript_id -> transcripts.id` for the primary transcript path
5. `transcripts.id -> transcript_segments.transcript_id` for ordered segment reads
6. `transcript_segments.id -> translations.transcript_segment_id` for translated outputs
7. `translations.id -> generated_audios.translation_id` for synthesized segment audio
8. `projects.current_lipsync_job_id -> lipsync_jobs.id` for the latest active lip-sync path
9. `projects.current_export_job_id -> export_jobs.id` for the latest active export path

## Recommended downstream relationship rules

### Project to media

Current state:

* `projects.media_file_id` already exists
* `media_files.project_id` and `media_files.workspace_id` exist but are nullable and not foreign keyed
* upload routes can create a `media_files` row with `project_id` when a project is supplied, and always stamp `workspace_id` from request context

Phase 3 rule:

* one project may reference one current primary media file for the editor path
* additional source media, if introduced later, should still remain project-scoped
* `media_files.project_id` and `projects.media_file_id` must stay consistent within the same workspace scope

### Media to transcript

Current state:

* `transcripts.media_file_id` is the concrete foreign key today
* `projects.transcript_id` is the project-facing pointer back to the chosen transcript
* `transcripts.project_id` and `transcripts.workspace_id` exist but remain nullable in the model

Phase 3 rule:

* a primary transcript should be identifiable from the project path
* transcript rows should remain independently queryable for retry, rebuild, or re-ingest flows
* transcript lineage should be recoverable without reading draft JSON

### Transcript to transcript segments

Current state:

* `transcript_segments.transcript_id` is the only hard parent key
* ordering is represented by `sequence_order`
* there is no uniqueness constraint yet on `(transcript_id, sequence_order)`

Phase 3 rule:

* transcript segments should be uniquely ordered within a transcript scope
* segment ordering should not depend on editor draft state
* provenance fields should eventually show whether the segment came from upload, transcription, edit, or later correction

### Transcript to translations

Current state:

* `translations` point to `transcript_segments` rather than directly to `transcripts`
* route reads for project translations query all segment rows for a transcript and then filter `translations.target_language`
* the single-segment translate path upserts by `(transcript_segment_id, target_language)` in code, but that uniqueness is not enforced in the schema

Phase 3 rule:

* translations should keep resolving through transcript segments
* the canonical grouping boundary should remain transcript plus target language unless a concrete run-level need is proven
* Phase 3 should treat one current translation row per `(transcript_segment_id, target_language)` as the intended steady-state model after legacy duplicate cleanup
* if multiple translation runs per language must be preserved later, introduce that as an additive parent construct rather than overloading the current row shape or weakening the Phase 3 current-row rule

### Translation to generated audio

Current state:

* `generated_audios.translation_id` is the hard parent key today
* there is no explicit audio-set or dubbing-run parent entity
* master dubbed audio for a project is currently addressed by a GCS path convention rather than a dedicated relational parent record

Phase 3 rule:

* generated audio should remain attributable to the translation row it was produced from
* the latest active audio for a project can stay query-derived in Phase 3 rather than adding another top-level project pointer immediately
* duplicate outputs caused by retries should be controlled by idempotency keys or equivalent write rules

### Project to lip-sync jobs

Current state:

* `projects.current_lipsync_job_id` already exists
* `lipsync_jobs` already carry `media_file_id` and `transcript_id` foreign keys
* `lipsync_jobs.project_id` and `workspace_id` exist but are nullable and were backfilled through Phase 2

Phase 3 rule:

* lip-sync jobs should be project-scoped and tied to the media and transcript context used for the run
* `projects.current_lipsync_job_id` should continue to point to the latest active or most relevant job for UI hydration
* historical job rows should stay append-friendly and queryable

### Project to export jobs

Current state:

* `projects.current_export_job_id` already exists
* `export_jobs` already carry `media_file_id` and `transcript_id` foreign keys
* `export_jobs.project_id` and `workspace_id` exist but are nullable and were backfilled through Phase 2

Phase 3 rule:

* export jobs should be project-scoped and tied to the source media and transcript context used for rendering
* `projects.current_export_job_id` should continue to serve as the UI pointer for the latest active export operation
* completed exports and artifacts should remain discoverable without copying output metadata into draft JSON

## Relationship decision table

| Relationship | Current implementation | Canonical parent | Direct pointer needed | Query-derived allowed | Phase 3 action |
| --- | --- | --- | --- | --- | --- |
| workspace -> project | fully implemented | `workspaces` | Yes | No | keep as tenancy root |
| project -> draft | fully implemented, one-to-one | `projects` | Yes | No | keep latest-draft model |
| project -> media | pointer exists on `projects`; reverse key on `media_files` is nullable | `projects` | Yes | Limited | tighten consistency and same-scope rules |
| project -> transcript | pointer exists on `projects`; transcript FK to media exists | `projects` | Yes | Limited | keep direct pointer and validate reverse scope |
| transcript -> segments | fully implemented | `transcripts` | No | No | add ordering uniqueness |
| transcript -> translations | indirect through segments | `transcripts` via `transcript_segments` | No new direct pointer required now | Yes | formalize transcript + language grouping |
| translation -> generated audio | fully implemented at row level | `translations` | No new direct pointer required now | Yes | add idempotency and optional active-set rules |
| project -> lip-sync job | current pointer plus historical rows | `projects` | Yes for current | Yes for history | keep pointer and validate same-scope invariants |
| project -> export job | current pointer plus historical rows | `projects` | Yes for current | Yes for history | keep pointer and validate same-scope invariants |
| project -> versions | not implemented | `projects` | No | Yes | add append-only history table |
| project -> audits | not implemented | `projects` | No | Yes | add append-only audit table |

## Invariants to enforce

* no downstream row may point to a `project_id` in a different `workspace_id`
* direct pointers on `projects` must reference records in the same project and workspace scope
* canonical reads must not require unpacking `project_drafts.draft_payload`
* the duplicated `projectMetadata` and `mediaReferences` sections in draft payload must be treated as convenience mirrors of canonical project data
* historical rows should remain queryable even if a project is archived

## Open decisions for Phase 3

* whether the `(transcript_segment_id, target_language)` uniqueness constraint is safe to enforce in the first tightening slice or only after legacy duplicate validation is complete
* whether generated-audio outputs need a later parent table for per-run grouping, or whether row-level linkage to `translations` is sufficient
* whether master dubbed audio should stay path-derived in GCS or gain a canonical relational record later
* whether project versions are snapshot-based, diff-based, or minimal metadata records in Phase 3
* which summary pointers belong on `projects` versus remaining query-derived

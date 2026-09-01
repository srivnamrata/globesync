# GlobeSync Phase 3 Additive Schema Plan

This document defines the additive schema strategy for Phase 3 so GlobeSync can normalize editor and workflow data without breaking the current production pipeline.

## Purpose

* sequence schema changes safely across current Cloud SQL tables
* identify additive migrations before any non-null or destructive tightening
* align backend route changes, backfills, and validation with deploy order on GCP
* keep current transcription, translation, TTS, lip-sync, and export flows operational throughout the phase

## Current schema baseline

Following your preferences, Phase 3 starts from this concrete baseline:

* `projects` and `project_drafts` are already first-class, workspace-scoped tables
* `projects` already has direct pointers for `media_file_id`, `transcript_id`, `current_lipsync_job_id`, and `current_export_job_id`
* `media_files`, `transcripts`, `translations`, `generated_audios`, `lipsync_jobs`, and `export_jobs` already carry `project_id` and `workspace_id` columns in most cases, but several remain nullable and weakly enforced
* `transcripts`, `lipsync_jobs`, and `export_jobs` already have concrete foreign keys to media or transcript tables, while project-scoped reverse integrity is still mostly logical rather than relational
* Phase 2 backfilled many missing scope columns through [20260830_06_backfill_project_scope_on_pipeline_tables.py](#file-840101848495060), which means Phase 3 can focus on validation and tightening rather than first-time propagation

## Change strategy

Following your preferences, Phase 3 schema changes should follow these rules:

* migrations must remain additive first
* `translation-migrate` runs before any backend deploy that depends on new columns or tables
* existing pipeline tables remain in service during the whole phase
* backfills must be validated before any constraint tightening
* deployment order remains migration, then `translation-api`, then `translation-web` if frontend contract changes are introduced

## Planned schema workstreams

### Workstream A — Scope and pointer integrity

Concrete repo-driven focus:

* validate that `media_files.project_id` and `workspace_id` match the `projects.media_file_id` path where that pointer exists
* validate that `transcripts.project_id` and `workspace_id` match both `projects.transcript_id` and `transcripts.media_file_id`
* validate same-scope integrity for `lipsync_jobs` and `export_jobs` against their `projects.current_*` pointers
* decide whether any missing reverse pointers should be added, but avoid introducing new top-level pointers unless they clearly reduce repeated joins

Likely schema actions:

* add foreign keys only after current legacy data passes validation
* keep nullable fields nullable until validation proves tightening is safe
* prefer same-scope check logic plus targeted indexes over broad table redesign

### Workstream B — Ordering and grouping integrity

Concrete repo-driven focus:

* add a uniqueness rule for `transcript_segments` ordering within `transcript_id`
* formalize the current translation grouping boundary of transcript plus target language, which today is enforced only in application logic
* make the Phase 3 default explicit: after legacy duplicate cleanup, one current translation row per `(transcript_segment_id, target_language)` is the intended steady-state model
* decide whether translation supersession or run history needs additive columns before any uniqueness constraint is tightened

Likely schema actions:

* unique index on `(transcript_id, sequence_order)` for `transcript_segments`
* possible unique index or staged uniqueness path on `(transcript_segment_id, target_language)` for `translations` after duplicate validation
* optional supersession fields such as `superseded_at`, `superseded_by_translation_id`, or a future translation-group identifier only if retained history requires them, but not as a substitute for the Phase 3 single-current-row model

### Workstream C — Provenance and idempotency support

Concrete repo-driven focus:

* generated audio, lip-sync, and export writes can be retried through task-based execution paths but currently lack a shared idempotency contract
* there is no common request-correlation field across normalized workflow tables
* transcript segments and translations also lack provenance markers for user-edited versus machine-generated changes

Likely schema actions:

* add nullable `request_id`, `idempotency_key`, `task_id`, or equivalent correlation columns where retries can create duplicate rows or artifacts
* add provenance fields such as `created_by_user_id`, `updated_by_user_id`, `source_action`, or `origin_type` where useful
* keep these nullable and additive in the first rollout slice

### Workstream D — Lifecycle and archival support

Concrete repo-driven focus:

* `projects` already has `archived_at`, but downstream records do not yet have a clear archival or supersession story
* generated outputs and jobs remain historically useful even after a project is archived

Likely schema actions:

* keep project archival as the top-level lifecycle control
* add selective lifecycle metadata such as `superseded_at` or result-status refinement only where it clarifies history or active-record selection
* avoid adding hard-delete semantics in Phase 3

### Workstream E — Versioning and audit foundation

Concrete repo-driven focus:

* there is no `project_versions` table yet
* there is no `audit_logs` table yet
* project and workflow writes therefore have no durable history foundation beyond row timestamps and current-state tables

Likely schema actions:

* create append-only `project_versions`
* create append-only `audit_logs`
* keep the initial write triggers narrow and low-risk

## Per-table candidate change list

| Table | Current state | Phase 3 additive candidate |
| --- | --- | --- |
| `projects` | has direct current pointers and archival fields | keep as root; add no major new pointers unless validation shows repeated join pain |
| `project_drafts` | one latest draft row per project | keep current shape; document cache-versus-canonical boundaries rather than redesigning yet |
| `media_files` | has nullable `project_id`, `workspace_id`, `user_id`; no FK to `projects` | validate backfill; consider FK tightening later; add provenance or correlation fields only if needed |
| `upload_sessions` | scoped by `workspace_id`, `user_id`, `media_file_id`; no `project_id` | keep indirect project linkage unless a real query/use case justifies adding `project_id` |
| `upload_chunks` | child rows under `upload_sessions` | no direct scope columns needed in Phase 3 |
| `transcripts` | FK to `media_files`; nullable `project_id` and `workspace_id` | validate scope backfill; consider FK tightening to project scope later |
| `transcript_segments` | ordered by `sequence_order` only | add uniqueness on `(transcript_id, sequence_order)`; add provenance fields later if needed |
| `translations` | keyed by `transcript_segment_id`; grouped in practice by target language | validate duplicates; target one current row per `(transcript_segment_id, target_language)`; add correlation fields if retry risk warrants; add supersession fields only if retained history is required |
| `generated_audios` | hard FK to `translations`; no run parent | keep row-level linkage; add idempotency/correlation support |
| `lipsync_jobs` | FKs to media and transcript; nullable project/workspace scope | validate backfill; add correlation support; tighten same-scope guarantees later |
| `export_jobs` | FKs to media and transcript; nullable project/workspace scope | validate backfill; add correlation support; tighten same-scope guarantees later |
| `project_versions` | not present | create append-only foundation |
| `audit_logs` | not present | create append-only foundation |

## Recommended migration sequence

1. Validate actual data quality for the Phase 2 backfilled scope columns before adding any new hard constraints.
2. Add low-risk indexes and additive metadata columns such as provenance or correlation fields.
3. Add ordering integrity for `transcript_segments` and validate whether `translations` can safely support a uniqueness rule around one current row per `(transcript_segment_id, target_language)`.
4. Introduce append-only `project_versions` and `audit_logs` tables once the earlier low-risk metadata and integrity groundwork is in place.
5. Tighten only those foreign keys or non-null expectations that are proven safe from validation data.

## Candidate schema decision table

| Area | Candidate additive change | Why it exists | Backfill needed | Constraint later |
| --- | --- | --- | --- | --- |
| Projects | retain current-record pointers; possibly add lightweight translation summary metadata only | fast editor hydration without over-modeling | no | maybe |
| Media/transcript lineage | validate and later tighten project/workspace scope integrity | simpler canonical traversal | yes | yes |
| Transcript segments | uniqueness on `(transcript_id, sequence_order)` | stable normalized reads | validate for duplicates | yes |
| Translations | uniqueness support around `(transcript_segment_id, target_language)` with optional supersession metadata only if needed later | align schema with current upsert behavior while keeping one current row per segment-language pair | likely | yes |
| Generated audio | idempotency or correlation columns | retry-safe output writes | likely | maybe |
| Lip-sync jobs | correlation and same-scope validation support | reliable job reconstruction | likely | maybe |
| Export jobs | correlation and same-scope validation support | reliable render reconstruction | likely | maybe |
| Project versions | new append-only table | history foundation | no | no |
| Audit logs | new append-only table | operational traceability | no | no |

## Backfill rules

* never assume all legacy rows can be fully reconstructed without validation
* backfill from canonical project or media lineage where that lineage is explicit and reliable
* record unresolved cases rather than forcing guessed ownership or pointer values
* do not tighten a field to non-null until unresolved legacy rows are handled or intentionally excluded
* if translation duplicates already exist for the same segment and language, resolve the retention policy before adding uniqueness

## Deployment notes

* deploy migrations in small slices rather than combining every Phase 3 change into one revision
* keep each schema slice paired with matching validation notes and rollback notes
* redeploy `translation-api` after any schema-dependent model or route update
* redeploy `translation-web` only if the frontend starts reading newly canonicalized fields directly
* prefer one integrity theme per migration slice so rollback remains legible

## Outputs expected from this artifact

* a final migration sequence for the phase
* a per-table additive change list
* a backfill and validation dependency list
* the boundary for which constraints can safely tighten in Phase 3 versus later phases

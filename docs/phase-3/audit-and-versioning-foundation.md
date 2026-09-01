# GlobeSync Phase 3 Audit and Versioning Foundation

This document defines the minimum viable audit and versioning foundation to introduce during Phase 3 without jumping ahead to full collaboration features.

## Purpose

* capture enough history to support operational traceability and later restore workflows
* define the minimum viable `project_versions` and `audit_logs` design for this phase
* keep history additive and low-risk while the current editor and pipeline continue to operate

## Current repo baseline

Following your preferences, GlobeSync currently has:

* `projects.updated_at`, `project_drafts.version`, `project_drafts.updated_at`, and row timestamps across pipeline tables
* no durable `project_versions` table
* no durable `audit_logs` table
* no shared correlation or idempotency foundation across translation, TTS, lip-sync, and export job writes

That means the system can tell what the current row state is, but it cannot yet reconstruct why the state changed or what earlier stable project state looked like.

## Design principles

Following your preferences, the Phase 3 foundation should:

* support restore and traceability later without making Phase 3 depend on Phase 7 collaboration features
* remain append-only wherever practical
* avoid blocking primary user workflows if audit capture is delayed or partial
* record workspace and project scope explicitly on every versioning or audit record
* align with the current project-centric root instead of introducing cross-cutting history tables with ambiguous ownership

## `project_versions` foundation

### Purpose

* preserve meaningful restore points for canonical project state
* support future comparison, rollback, or approval workflows
* capture version boundaries without copying every volatile UI field on every save

### Minimum recommended columns

* `id`
* `workspace_id`
* `project_id`
* `version_number`
* `created_by_user_id`
* `source_action`
* `snapshot_payload` or `summary_payload`
* `base_project_updated_at`
* `created_at`

### Recommended Phase 3 payload contents

For Phase 3, the version payload should favor stable, shared state only:

* project identity fields such as name, status, source language, and target language
* current pointers such as `media_file_id`, `transcript_id`, `current_lipsync_job_id`, and `current_export_job_id`
* summary indicators such as `active_translation_language` and `last_rendered_video_gcs_path`
* optional compact summaries of selected transcript or translation state only if needed for restore usefulness

Avoid storing:

* ephemeral `timelineState`
* every draft autosave snapshot
* large duplicated transcript or translation arrays if canonical relational reconstruction is available

### Phase 3 scope decision

Preferred initial behavior:

* create versions only for meaningful project-state transitions, not every keystroke
* treat draft autosave as separate from durable project version history
* allow the payload shape to be minimal if full snapshotting is too expensive initially

## `audit_logs` foundation

### Purpose

* capture who changed what, in which workspace and project scope, and when
* improve debugging, security review, and operational incident analysis
* create the minimum event trail required before more advanced collaboration features exist

### Minimum recommended columns

* `id`
* `workspace_id`
* `project_id`
* `actor_user_id`
* `action_type`
* `target_type`
* `target_id`
* `request_id` or correlation id
* `task_id` where applicable
* `status` or `result`
* `metadata_payload`
* `created_at`

### Recommended action families from the current repo

* project created, updated, archived, restored
* draft checkpoint saved or draft conflict rejected
* media uploaded, attached, or selected on a project
* transcript started, completed, failed, or selected
* translation started, completed, failed, updated, or superseded
* generated audio created
* lip-sync job queued, started, completed, failed, canceled
* export job queued, started, completed, failed, canceled
* cross-scope authorization failure or guarded not-found rejection where security review value is high

## Suggested write policy

### Emit `project_versions` for

* explicit project state transitions
* project metadata changes that affect shared canonical behavior
* transcript or media pointer changes on `projects`
* archival or restore operations
* any later explicit publish or checkpoint action if introduced

### Emit `audit_logs` for

* security-sensitive or ownership-sensitive writes
* background task state transitions
* user-visible changes to project, transcript, translation, audio, lip-sync, or export state
* explicit draft checkpoints, conflict rejections, or other save events that cross a meaningful user-visible boundary
* operationally important failures where a durable record helps later investigation

### Phase 3 default audit granularity for draft saves

For Phase 3, draft-save auditing should stay intentionally narrow:

* do not emit an `audit_logs` row for every autosave heartbeat or keystroke-driven draft update
* do emit audit records for explicit checkpoints, conflict events, restore-worthy transitions, or other draft saves that materially change shared state handling
* if finer-grained draft history is needed later, add it deliberately rather than letting autosave noise define the audit stream

## Recommended integration points in the current codebase

* `project_service.py` for project create, update, archive, and draft put operations
* upload routes when media rows and upload sessions become attached to a project
* transcription, translation, TTS, lip-sync, and export task dispatch or completion handlers
* any future shared write helper that centralizes project-scoped side effects

## Questions to settle in Phase 3

* whether `project_versions` stores full snapshots, summaries, or references to canonical records
* whether any draft-save cases beyond explicit checkpoints, conflicts, and restore-worthy transitions deserve audit coverage in Phase 3
* whether background tasks write directly to `audit_logs` or through a shared service helper
* which existing request IDs, Cloud Tasks identifiers, or Celery task IDs should become the standard correlation fields

## Success criteria for this artifact

* a minimal table design exists for both `project_versions` and `audit_logs`
* the initial write triggers are defined
* history capture stays additive and low-risk
* later collaboration features can build on this foundation without redesigning the ownership model

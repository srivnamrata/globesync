# GlobeSync Phase 3 Rollout Checklist

This checklist tracks the rollout of Phase 3 normalization work for GlobeSync.

## Purpose

* keep Phase 3 deploy slices small and auditable
* preserve the current media pipeline while normalization changes are introduced
* ensure migrations, backend changes, and validation stay aligned on GCP

## Current status

The current status at Phase 3 kickoff is:

* Phase 1 is complete
* Phase 2 is complete
* Phase 3 has started and the first additive schema groundwork revisions are now authored
* the planning artifacts for inventory, canonical relationships, schema planning, draft boundaries, and audit/versioning now exist and are populated with repo-specific findings
* the current operational baseline must remain stable while additive normalization work is introduced

## Rollout rules

* run `translation-migrate` before `translation-api` when schema changes are involved
* deploy `translation-api` before `translation-web` when frontend-visible contracts change
* keep schema changes additive first
* validate backfills before constraint tightening
* do not remove current pipeline tables during this phase
* prefer one integrity theme per deploy slice so rollback remains legible

## Phase 3 rollout slices

### Slice 3.1 — Inventory and relationship decisions

Completion criteria:

* normalization gaps are inventoried
* canonical pointer rules are documented
* draft-versus-normalized boundaries are documented
* repo-specific duplication and weak-integrity gaps are identified

Evidence captured:

* [normalization-gap-inventory.md](#file-4107232751829825)
* [canonical-relationship-map.md](#file-4107232751829826)
* [draft-vs-normalized-boundaries.md](#file-4107232751829828)

Remaining to close slice:

* confirm the translation grouping decision remains transcript plus target language for Phase 3, with one current row per `(transcript_segment_id, target_language)` after duplicate cleanup
* confirm no additional editor-only payload sections need to stay in `project_drafts`

Status:

* in progress, documentation largely prepared

### Slice 3.2 — Additive schema design

Completion criteria:

* additive schema plan is documented
* per-table candidate changes are sequenced
* backfill dependencies and integrity rules are identified

Evidence captured:

* [additive-schema-plan.md](#file-4107232751829827)

Remaining to close slice:

* extend the initial Alembic groundwork into the next schema slices beyond correlation and transcript-ordering setup
* decide which constraints are safe now versus after data validation

Status:

* in progress, initial migration groundwork authored

### Slice 3.3 — First additive migration set

Completion criteria:

* initial additive migration(s) are authored
* migration ordering is validated
* rollback notes are documented

Expected first-slice candidates:

* transcript-segment ordering integrity
* correlation or idempotency support for generated outputs and jobs
* low-risk provenance metadata where route behavior already implies ownership

Evidence to capture:

* [20260901_07_add_workflow_correlation_foundation.py](#file-493542987818579)
* [20260901_08_add_transcript_segment_ordering_index.py](#file-4393033632292541)
* [transcript-segment-ordering-validation-notes.md](#file-3186989309718575)
* model alignment notes for [transcript.py](#file-3239543912548904)
* route and task compatibility notes

Status:

* in progress, additive migrations are authored, transcript-order baseline validation passed cleanly, and route/task correlation wiring is now underway with cross-path validation still pending

### Slice 3.4 — Audit and versioning foundation rollout

Completion criteria:

* `project_versions` and `audit_logs` foundations are documented and introduced safely
* initial write triggers are defined
* history capture does not block primary workflows

Evidence to capture:

* [audit-and-versioning-foundation.md](#file-4107232751829829)
* schema notes for `project_versions` and `audit_logs`
* initial write-path notes and rollback notes

Status:

* in progress, schema not yet introduced

### Slice 3.5 — Compatibility validation and constraint tightening

Completion criteria:

* representative route and task compatibility checks pass
* backfill safety is validated on real data
* only then are any safe constraints tightened

Evidence to capture:

* validation outputs
* unresolved legacy-row notes if any remain
* deploy notes and rollback notes

Status:

* not started

## Deployment checklist per slice

* record the schema changes included
* record the backend files or routes affected
* run migrations before backend deploy
* verify project-scoped reads still work
* verify task-driven writes still work
* verify no cross-workspace pointer mismatch was introduced
* record rollback approach for the slice

## Current post-deploy validation focus

* deploy [translation-api](#file-3239543912548912)-backed route and task changes after the migration job has already succeeded
* validate `/v1/transcription/start` creates transcript work with correlation metadata flowing into the task path
* validate the internal transcription task path persists transcript segment ordering and transcription correlation metadata without breaking existing reads
* validate project translation, TTS, lip-sync, and export flows still write rows successfully with the new request or task or idempotency fields populated where expected
* capture any route-specific gaps before starting the uniqueness-tightening revision for transcript ordering
* record deployment blockers separately when they are unrelated to Phase 3 schema changes, so rollout evidence does not conflate contract regressions with pre-existing storage/data issues
* note that `translation-web` revision `translation-web-00018-mh9` deployed successfully, but the post-deploy CORS allow-list update command failed because `gcloud run services update --update-env-vars` was given JSON-list syntax instead of an escaped env-var string value
* keep the current lip-sync failure recorded as a missing-object storage lookup on `media_file.storage_path` in `translation-api`, not as evidence of a correlation-field regression unless the stored key is shown to be rewritten incorrectly
* use bucket-aware download calls plus enriched lip-sync error logging so current validation can distinguish stale database pointers from wrong-bucket reads and preserve request/task/idempotency evidence in logs

## Immediate next actions

* confirm the Phase 3 target of one current translation row per `(transcript_segment_id, target_language)` after legacy duplicate cleanup
* rerun the `translation-web` post-deploy CORS allow-list update with correctly escaped env-var syntax or an env file so the frontend origin set is applied cleanly
* deploy and validate the current correlation and provenance wiring across translation, TTS, lip-sync, export, and transcription-triggered write paths after the next backend deploy
* redeploy `translation-api` with the bucket-aware download and lip-sync diagnostic logging changes in [storage_service.py](#file-3239543912548943) and [lipsync_tasks.py](#file-3239543912548954)
* inspect the failing `media_file.storage_path` row and the `project-794c406e-c0ab-4a50-8e9-media-raw` bucket contents to determine whether the lip-sync `404` is caused by stale metadata, missing upload persistence, or an object-key mismatch
* treat the current lip-sync `404` on `media_file.storage_path` download as a separate storage/data validation issue unless a route change is shown to be rewriting the object key incorrectly
* continue threading the new correlation and provenance fields through any remaining route and task handlers discovered during validation
* rerun transcript ordering validation after route and task wiring lands, then use the clean baseline to prepare the uniqueness-tightening revision
* define the exact initial schema for `project_versions` and `audit_logs` before final constraint tightening
* keep [normalization-gap-inventory.md](#file-4107232751829825) updated as any newly discovered legacy edge cases appear

## Exit checkpoint for the phase

Mark Phase 3 complete only when:

* normalized workflow data is authoritative and queryable without unpacking the full draft blob
* current transcription, translation, TTS, lip-sync, and export paths still operate correctly
* project-centric pointers and integrity rules are validated
* audit and versioning foundations exist for later phases

# GlobeSync Phase 3 Rollout Checklist

This checklist tracks the rollout of Phase 3 normalization work for GlobeSync.

## Purpose

* keep Phase 3 deploy slices small and auditable
* preserve the current media pipeline while normalization changes are introduced
* ensure migrations, backend changes, and validation stay aligned on GCP

## Current status

Following your preferences, the current status at Phase 3 kickoff is:

* Phase 1 is complete
* Phase 2 is complete
* Phase 3 has started but no schema deploy slice is yet marked complete
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

* translate the documented candidate changes into the first concrete Alembic revision set
* decide which constraints are safe now versus after data validation

Status:

* in progress, migration authoring not started

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

* Alembic revision identifiers
* migration validation notes
* route compatibility notes

Status:

* not started

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

## Immediate next actions

* confirm the Phase 3 target of one current translation row per `(transcript_segment_id, target_language)` after legacy duplicate cleanup
* author the first additive migration slice from [additive-schema-plan.md](#file-4107232751829827)
* define the exact initial schema for `project_versions` and `audit_logs` before final constraint tightening
* capture validation notes for duplicate transcript ordering or translation rows before adding uniqueness
* keep [normalization-gap-inventory.md](#file-4107232751829825) updated as any newly discovered legacy edge cases appear

## Exit checkpoint for the phase

Mark Phase 3 complete only when:

* normalized workflow data is authoritative and queryable without unpacking the full draft blob
* current transcription, translation, TTS, lip-sync, and export paths still operate correctly
* project-centric pointers and integrity rules are validated
* audit and versioning foundations exist for later phases

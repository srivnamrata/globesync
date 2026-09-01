# GlobeSync Phase 2 Canonical Projects and Media Authorization

Following your ordered migration preference, this document tracks the next implementation phase after the Phase 1 identity, tenancy, bootstrap, `/v1/projects` access control, and first-pass downstream `workspace_id` backfill work.

## Objective

Make backend project state canonical and extend authenticated workspace authorization from `/v1/projects` into the media pipeline surfaces that read or mutate project-linked records.

## Why Phase 2 should include media-route role checks

Yes. Phase 2 should extend role checks to media routes.

Phase 1 established the tenancy primitives, authenticated request context, frontend bootstrap call, `/v1/projects` scoping, and initial write-role enforcement. That is enough to start applying the same workspace-aware authorization model to the rest of the API surface.

Without extending role checks, the system would still have a mismatch where project creation is guarded by workspace membership but uploads, transcript access, translation flows, render jobs, or export paths could continue to rely on legacy caller-supplied ownership assumptions. That would leave the tenancy model only partially enforced.

## Phase 2 scope

### 1. Canonical backend project state

Introduce the backend-managed project container that becomes the source of truth for cross-device project access:

* `projects`
* `project_drafts`

These should carry canonical project ownership, language configuration, linked pipeline record pointers, and server-side draft persistence, while allowing IndexedDB to remain only as an optional resilience cache.

### 2. Media-route authorization expansion

Apply reusable authenticated request-context and membership-aware authorization checks to the remaining workspace-scoped routes, including as applicable:

* upload and media fetch flows
* transcript read and mutation flows
* translation read and mutation flows
* generated-audio, lip-sync, and export job routes
* any route that dereferences a project-linked downstream record

Recommended enforcement model:

* `viewer` can read workspace-visible project and media state
* `editor` can create or modify project and media pipeline state
* `owner` retains full workspace control
* route handlers should derive workspace scope from authenticated context and linked records, not from caller-supplied workspace identifiers

### 3. Downstream ownership completion

Continue the staged ownership migration that started in Phase 1:

* backfill `workspace_id` for records that can be resolved safely from linked project or media lineage
* identify unresolved legacy rows explicitly rather than inferring ownership unsafely
* add `project_id` where needed so downstream authorization can anchor on a canonical project root
* make ownership columns non-null only after backfill validation is complete

## Deliverables

* additive schema for `projects` and `project_drafts`
* backend serialization contract for project metadata and draft payloads
* API endpoints for project create, load, update, archive, and draft save/load
* frontend adapter flow that bootstraps auth, reads canonical backend projects, and uses server-side drafts as the source of truth
* reusable media-route authorization helpers for read/write access
* staged backfill documentation for nullable legacy ownership columns that remain unresolved

## Exit criteria

* a project can be created on one device and resumed on another from backend persistence
* every media pipeline route enforces workspace-aware authorization through authenticated context
* downstream project-linked records have validated workspace ownership or are isolated for manual cleanup
* legacy caller-supplied ownership parameters are removed from the active authorization path

## Current implementation status

The Phase 2 backend foundation step is now in place:

* canonical SQLAlchemy models are scaffolded in [project.py](#file-3264843069231746)
* the ordered Alembic migration is rebased in [20260830_05_add_projects_and_project_drafts.py](#file-3212615212764924)
* project request and response contracts are expanded in [projects.py](#file-3264843069231747) for draft metadata, pipeline pointers, and canonical render-path fields
* project persistence logic in [project_service.py](#file-3264843069231748) is now aligned to workspace-scoped canonical access instead of owner-only reads
* the frontend now creates canonical backend drafts first and prefers backend draft persistence before falling back to IndexedDB in [projectService.ts](#file-3239543912549052), [page.tsx](#file-3239543912549011), and [page.tsx](#file-3239543912549008)
* workspace-aware authorization has now been extended across [upload.py](#file-3239543912548915), [transcription.py](#file-3239543912548912), [translation.py](#file-3239543912548913), [tts.py](#file-3239543912548914), [lipsync.py](#file-3239543912548911), [export.py](#file-3239543912548909), and shared helpers in [auth.py](#file-840101848495052)
* media-route authorization still carries a temporary legacy `user_id` fallback when `workspace_id` and `project_id` are both missing, pending downstream ownership completion
* additive lineage-based ownership cleanup is now in place through [20260830_06_backfill_project_scope_on_pipeline_tables.py](#file-840101848495060) to backfill missing project, workspace, and uploader scope from canonical project or media lineage where that linkage is already trustworthy
* focused shared-helper regression coverage now exists in [test_workspace_auth.py](#file-840101848495061), while broader route-level integration coverage still remains for later Phase 2 steps

## Dependencies already satisfied by Phase 1

Phase 2 can proceed because the following prerequisites are already in place:

* identity and tenancy tables exist through [identity.py](#file-2724092822522420) and [20260829_03_add_identity_tenancy_tables.py](#file-2724092822522421)
* auth bootstrap and authenticated context endpoints exist through [auth-bootstrap-layer.md](#file-840101848495055)
* `/v1/projects` already resolves workspace scope from authenticated request context in [projects.py](#file-3264843069231749)
* frontend bootstrap wiring already exists through [authService.ts](#file-840101848495056), [apiClient.ts](#file-3239543912549051), [projectService.ts](#file-3239543912549052), [page.tsx](#file-3239543912549011), and [page.tsx](#file-3239543912549008)
* first-pass additive downstream `workspace_id` columns already exist through [20260830_04_add_workspace_scope_to_pipeline_tables.py](#file-840101848495057)

## Recommended implementation order inside Phase 2

1. add `projects` and `project_drafts` schema and models
2. finish any remaining backend project and draft endpoint alignment on authenticated context
3. continue refining frontend load/save flows so IndexedDB remains recovery-only while backend drafts stay canonical
4. validate the new safe downstream ownership backfill, isolate any unresolved legacy rows, and then remove temporary legacy user fallbacks
5. make validated ownership columns non-null and remove obsolete scope parameters
6. broaden route-level authorization and negative-access integration tests beyond the shared helper coverage already added

## Validation expectations

At minimum, validate:

* backend syntax and migration compilation
* regression tests for shared authorization helpers plus route-level project and media authorization behavior
* frontend project bootstrap, load, create, draft save, and editor resume flows
* negative authorization cases for `viewer`, `editor`, and cross-workspace access

## Rollout note

Keep this phase additive where possible: deploy migrations first, then `translation-api`, then `translation-web`. Preserve compatibility fallbacks until backend project persistence and media-route authorization are verified in a non-production path.

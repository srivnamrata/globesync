# GlobeSync Phase 0 Backend Schema Module Plan

This document turns the `/projects` planning artifacts into a backend implementation plan for models, request/response schemas, service modules, and router wiring.

## Purpose

* Give the backend work a concrete module layout before coding begins
* Keep the first `/projects` implementation aligned with the GCP-first migration plan
* Separate canonical relational state from editor-session compatibility payloads
* Reduce ambiguity around where validation, transactions, and concurrency checks belong

## Related artifacts

* [GCP_MULTI_TENANT_MIGRATION_PLAN.md](#file-2060193141886677)
* [draft-field-mapping.md](#file-2060193141886681)
* [projects-api-examples.md](#file-2060193141886685)
* [projects-router-contract.md](#file-2060193141886686)
* [validation-checklist.md](#file-2060193141886684)

## Implementation goal

Following your preferences, the first backend cut should add server-owned project persistence on top of the existing Cloud SQL, Cloud Run, GCS, and Cloud Tasks architecture without changing the ownership of transcript, translation, TTS, or lip-sync pipeline outputs.

That means:

* `projects` becomes the canonical home for project identity, ownership, status, and pipeline pointers
* `project_drafts` becomes the canonical home for editor-session payloads
* browser IndexedDB remains a compatibility cache during cutover
* existing normalized pipeline tables remain authoritative for transcript segments, translations, generated audio, and jobs

## Recommended backend modules

| Module | Purpose | Notes |
| --- | --- | --- |
| `backend/app/models/project.py` | SQLAlchemy models for `projects` and `project_drafts` | New persistent entities |
| `backend/app/schemas/projects.py` | Pydantic request/response models for `/projects` routes | Keep API shape explicit |
| `backend/app/services/project_service.py` | Project business logic and transaction boundaries | No ORM-heavy route handlers |
| `backend/app/routers/projects.py` | FastAPI endpoints and dependency wiring | Mounted under `/v1/projects` |
| `backend/alembic/versions/<revision>_add_projects_and_project_drafts.py` | Schema migration | Add tables and indexes first |
| `backend/app/models/__init__.py` or equivalent registry | Model import registration | Ensure migrations/runtime metadata see new tables |

## Proposed file responsibilities

### `backend/app/models/project.py`

This module should define the persistent SQLAlchemy models and only model-level helpers that are truly data-shape specific.

Recommended models:

* `Project`
* `ProjectDraft`

Recommended `Project` fields:

* `id`
* `workspace_id`
* `owner_user_id`
* `created_by_user_id`
* `name`
* `slug`
* `status`
* `source_language`
* `target_language`
* `active_translation_language`
* `media_file_id`
* `transcript_id`
* `current_lipsync_job_id`
* `current_export_job_id`
* `last_rendered_video_gcs_path`
* `last_opened_at`
* `archived_at`
* `created_at`
* `updated_at`

Recommended `ProjectDraft` fields:

* `id`
* `project_id`
* `workspace_id`
* `version`
* `draft_schema_version`
* `draft_payload`
* `base_project_updated_at`
* `last_saved_by_user_id`
* `created_at`
* `updated_at`

Recommended relationships:

* `Project.draft` one-to-one with `ProjectDraft`
* optional relationships from `Project` to existing `MediaFile`, `Transcript`, `LipSyncJob`, and `ExportJob` models

Model guidance:

* use raw UUID storage consistent with the rest of the backend schema direction
* prefer server-generated timestamps for `created_at` and `updated_at`
* add a model-level status constraint or enum backing for `draft`, `processing`, `ready`, `failed`, and `archived`
* keep `draft_payload` as JSONB and avoid embedding business logic in model properties

### `backend/app/schemas/projects.py`

This module should own the API contract, not the database schema.

Recommended request models:

* `ProjectListQueryParams`
* `ProjectCreateRequest`
* `ProjectUpdateRequest`
* `ProjectDraftPutRequest`
* `ProjectArchiveRequest` only if archive later needs a body; otherwise skip it

Recommended response models:

* `ProjectSummaryResponse`
* `ProjectListResponse`
* `ProjectDetailResponse`
* `ProjectDraftResponse`
* `ProjectDraftPutResponse`
* `ProjectArchiveResponse`
* `ApiErrorResponse`
* `DraftConflictErrorResponse`

Recommended schema boundaries:

* top-level models use `snake_case`
* nested `draft_payload` remains largely untyped or lightly typed at first to preserve compatibility with the current editor payload
* if typing the draft payload, do it with nested compatibility models instead of flattening it into project metadata models

Suggested `ProjectCreateRequest` fields:

* `name: str`
* `source_language: str`
* `target_language: str`

Suggested `ProjectUpdateRequest` optional fields:

* `name`
* `status`
* `target_language`
* `active_translation_language`

Suggested `ProjectDraftPutRequest` fields:

* `version: int`
* `draft_schema_version: str`
* `base_project_updated_at: datetime | None`
* `draft_payload: dict`

Validation guidance:

* normalize and validate language codes against the backend language config rules already established in the repo
* reject immutable fields in patch operations
* keep status validation centralized so route handlers do not duplicate allowed-value logic
* preserve the draft payload contract closely enough that the current editor can hydrate without broad reshaping

### `backend/app/services/project_service.py`

This module should hold the business logic, lookup rules, and transaction handling.

Recommended service methods:

* `list_projects(session, workspace_id, actor, filters)`
* `create_project(session, workspace_id, actor, payload)`
* `get_project(session, workspace_id, project_id, actor)`
* `update_project(session, workspace_id, project_id, actor, patch_payload)`
* `get_project_draft(session, workspace_id, project_id, actor)`
* `put_project_draft(session, workspace_id, project_id, actor, draft_update)`
* `archive_project(session, workspace_id, project_id, actor)`

Service responsibilities:

* workspace-scoped lookup for every read and write
* project existence and authorization checks
* creation of the first `ProjectDraft` row when needed
* optimistic concurrency enforcement on draft save
* synchronization of `latest_draft_version` semantics between `ProjectDraft.version` and project detail responses
* optional dual-write refresh of mirrored `projectMetadata` inside `draft_payload` during transition
* guardrails so cached arrays in `draft_payload` never override canonical transcript or translation tables

Suggested internal helper functions:

* `build_project_summary(project, draft=None)`
* `build_project_detail(project, draft=None)`
* `build_project_draft_response(project, draft)`
* `normalize_project_languages(payload)`
* `validate_project_patch(payload)`
* `assert_workspace_access(actor, workspace_id)`

### `backend/app/routers/projects.py`

This module should stay thin and delegate business logic.

Recommended route handlers:

* `list_projects`
* `create_project`
* `get_project`
* `update_project`
* `get_project_draft`
* `put_project_draft`
* `archive_project`

Router responsibilities:

* wire request models, response models, auth dependencies, and DB session dependencies
* pass the authenticated actor and resolved workspace context into the service layer
* translate domain errors into stable HTTP responses such as `404`, `409`, and `422`
* avoid inline ORM queries except trivial dependency helpers

## Suggested schema details by module

### Database indexes and constraints

Recommended in the Alembic migration and model metadata:

* primary key on `projects.id`
* primary key on `project_drafts.id`
* foreign key `project_drafts.project_id -> projects.id`
* index on `projects(workspace_id, updated_at desc)`
* secondary index on `projects(workspace_id, owner_user_id, updated_at desc)`
* unique constraint on `project_drafts.project_id` for the first-cut latest-draft model
* check constraint on `projects.status`
* foreign keys for `media_file_id`, `transcript_id`, `current_lipsync_job_id`, and `current_export_job_id`

### Serialization rules

Recommended response behavior:

* `GET /v1/projects` returns summary records only
* `GET /v1/projects/{project_id}` returns canonical project metadata and pointer fields only
* `GET /v1/projects/{project_id}/draft` returns the full draft payload and version metadata
* `PUT /v1/projects/{project_id}/draft` returns updated version metadata, not necessarily the entire draft payload again

### Draft payload typing strategy

For the first cut, prefer a hybrid approach:

* strongly type envelope fields like `version`, `draft_schema_version`, and timestamps
* keep `draft_payload` as a permissive dictionary or lightly typed compatibility object
* validate only the fields the backend truly depends on in early phases

This lowers migration risk while the editor is still close to the IndexedDB contract.

## Transaction and concurrency plan

### Project create

Recommended flow:

1. validate request payload
2. resolve authenticated workspace and user
3. insert `Project`
4. commit and return project detail response

Do not require a draft row at project creation time unless the frontend immediately saves one.

### Project patch

Recommended flow:

1. workspace-scoped lookup
2. validate mutable fields only
3. update canonical project metadata
4. if dual-write mirror is active, update mirrored `projectMetadata` inside `ProjectDraft.draft_payload`
5. commit and return project detail response

### Draft save

Recommended flow:

1. workspace-scoped project lookup
2. load current draft row for update
3. compare client `version` with server `version`
4. if mismatch, raise draft conflict error
5. insert or update `ProjectDraft`
6. increment `version`
7. set `last_saved_by_user_id`, `base_project_updated_at`, and `updated_at`
8. commit and return new version metadata

Concurrency rule:

* stale client writes must return `409 Conflict`
* do not silently merge JSON payloads in the first cut
* multi-device safety is more important than auto-merge behavior in Phase 2

### Project archive

Recommended flow:

1. workspace-scoped lookup
2. set `status = archived`
3. set `archived_at`
4. commit

Do not delete linked transcript, translation, audio, render, or media rows in this phase.

## Cross-module integration points

### `main.py`

Once the router exists, [main.py](#file-3239543912548896) should:

* import the new `projects` router
* mount it under the same API prefix as the other public routers
* keep the existing `/media`, `/transcription`, `/translation`, `/tts`, `/lipsync`, and `/internal/tasks` boundaries unchanged

### Existing pipeline models

The first implementation can leave existing nullable pipeline ownership fields in place, but should prepare for later backfill by:

* allowing `projects.media_file_id` to point at `media_files.id`
* allowing `projects.transcript_id` to point at `transcripts.id`
* planning later non-null `project_id` and `workspace_id` propagation into media, transcript, translation, generated-audio, lip-sync, and export tables

### Frontend cutover support

The backend schema/module plan should support a transition where:

* the frontend loads canonical metadata from `GET /v1/projects/{project_id}`
* the frontend loads editor state from `GET /v1/projects/{project_id}/draft`
* the frontend can still cache the payload locally in IndexedDB
* the frontend can continue reading the familiar nested `projectMetadata`, `mediaReferences`, `translations`, `timelineState`, and `uiState` blocks

## Recommended implementation order

1. Add Alembic migration for `projects` and `project_drafts`
2. Add `backend/app/models/project.py`
3. Register new models in the ORM metadata import path
4. Add `backend/app/schemas/projects.py`
5. Add `backend/app/services/project_service.py`
6. Add `backend/app/routers/projects.py`
7. Mount router in [main.py](#file-3239543912548896)
8. Validate against [projects-api-examples.md](#file-2060193141886685) and [validation-checklist.md](#file-2060193141886684)
9. Only then switch the frontend from IndexedDB-first hydration to backend-first hydration

## Minimum acceptance criteria for backend implementation

* `/v1/projects` routes are mounted and reachable
* project create, read, patch, draft read, draft write, and archive flows work in a workspace-scoped way
* draft saves increment version correctly
* stale draft writes return `409 Conflict`
* current editor draft shape can be returned without destructive reshaping
* no route handler directly reimplements business logic that belongs in `project_service.py`

## Open choices to resolve during coding

* whether to use an enum type or plain text plus check constraint for `projects.status`
* whether to keep `draft_payload` fully untyped in Pydantic at first or lightly type key nested sections
* whether to create a draft row lazily on first save or proactively on project creation
* whether artifact preview URLs should remain fully outside the `/projects` surface in the first implementation
* whether to surface `latest_draft_version` directly from a join, a subquery, or a mirrored field on project reads

## Recommended next step

After this plan, the next useful artifact is a concrete Alembic migration checklist for `projects` and `project_drafts`, including backfill sequencing and downgrade safety notes.

# GlobeSync Phase 0 `/projects` Router Contract

This document defines the backend router contract for the first `/projects` implementation so the FastAPI layer, service layer, and frontend cutover all use the same boundaries.

## Purpose

* Turn the Phase 2 `/projects` design into an implementation-oriented backend contract
* Define what belongs in the router versus services versus normalized tables
* Keep the first backend cutover compatible with the current editor draft shape
* Make workspace scoping and optimistic concurrency explicit

## Related artifacts

* [GCP_MULTI_TENANT_MIGRATION_PLAN.md](#file-2060193141886677)
* [draft-field-mapping.md](#file-2060193141886681)
* [projects-api-examples.md](#file-2060193141886685)
* [validation-checklist.md](#file-2060193141886684)

## Current gap this contract closes

As of the current-state review, `/projects` is still referenced by the frontend but no `/projects` router is mounted in [main.py](#file-3239543912548896). This contract starts the implementation boundary for a new backend router, likely in `backend/app/routers/projects.py`, plus its request/response schemas and service methods.

## Router scope

The `/projects` router should own project-level identity and draft-session APIs only.

It should include:

* `GET /v1/projects`
* `POST /v1/projects`
* `GET /v1/projects/{project_id}`
* `PATCH /v1/projects/{project_id}`
* `GET /v1/projects/{project_id}/draft`
* `PUT /v1/projects/{project_id}/draft`
* `POST /v1/projects/{project_id}/archive`

It should not absorb responsibilities already owned elsewhere:

* media upload stays under `/media/uploads/*`
* transcript processing stays under `/transcription/*`
* translation work stays under `/translation/*`
* TTS stays under `/tts/*`
* lip-sync stays under `/lipsync/*`
* Cloud Tasks private handlers stay under `/v1/internal/tasks/*`

## Router responsibilities

The router should be responsible for:

* request validation and coercion
* authentication and workspace scoping checks
* response serialization
* mapping service-layer errors to stable HTTP responses
* keeping compatibility between canonical project metadata and the current editor draft contract

The router should not be responsible for:

* direct orchestration of transcription, translation, TTS, or lip-sync work
* embedding transcript segment or translation normalization logic in route handlers
* storing long-lived business rules inline in handler functions

## Recommended file structure

A minimal first cut can use:

* `backend/app/routers/projects.py`
* `backend/app/schemas/projects.py`
* `backend/app/services/project_service.py`
* `backend/app/models/project.py`
* Alembic migration for `projects` and `project_drafts`

If the codebase already separates schema modules by endpoint family, keep the same pattern rather than forcing a new structure.

## Request and response model boundaries

### Top-level API style

* top-level request and response bodies should use `snake_case`
* IDs should be raw UUID strings unless the team decides on a public-ID wrapper everywhere
* draft payload content should preserve the current frontend `camelCase` shape inside `draft_payload`

### Canonical project response fields

The router should expose these top-level project fields:

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
* `latest_draft_version`
* `archived_at`
* `created_at`
* `updated_at`

### Draft response fields

The draft endpoint should expose:

* `project_id`
* `workspace_id`
* `version`
* `draft_schema_version`
* `base_project_updated_at`
* `last_saved_by_user_id`
* `created_at`
* `updated_at`
* `draft_payload`

## Endpoint-by-endpoint contract

### `GET /v1/projects`

Responsibilities:

* list projects visible to the current user in the active workspace
* filter by optional fields such as `status` and `updated_after`
* return lightweight records suitable for project list pages

Contract notes:

* exclude archived projects by default unless an explicit query flag is added
* do not inline transcript segments, translation arrays, or signed media URLs
* sort by `updated_at DESC` by default

### `POST /v1/projects`

Responsibilities:

* create the canonical project shell before upload or transcription work begins
* stamp ownership and workspace fields from authenticated context unless an admin-only override exists
* initialize `status = draft`

Contract notes:

* request body should be minimal: `name`, `source_language`, `target_language`
* `workspace_id` should come from auth or request context, not arbitrary client input in the normal path
* return the created project record, not a draft payload

### `GET /v1/projects/{project_id}`

Responsibilities:

* return the canonical project record for editor bootstrap and project list detail views
* expose pointers to media, transcript, and latest workflow jobs

Contract notes:

* this is the canonical metadata endpoint
* it should stay small and stable
* artifact URLs should remain on dedicated endpoints unless the team explicitly chooses otherwise

### `PATCH /v1/projects/{project_id}`

Responsibilities:

* update mutable metadata without rewriting the draft payload
* allow changes such as `name`, `status`, `target_language`, and `active_translation_language`

Contract notes:

* reject immutable-field writes such as `workspace_id`, `owner_user_id`, or `created_at`
* keep validation strict around allowed `status` values
* if the frontend still mirrors `projectMetadata` in `draft_payload`, service code may need to refresh that mirror during the dual-write period

### `GET /v1/projects/{project_id}/draft`

Responsibilities:

* return the latest server-owned editor draft payload
* return version metadata used for optimistic concurrency

Contract notes:

* preserve the current frontend-style nested shape inside `draft_payload`
* allow cached `originalTranscriptSegments` and `translations` during the transition period
* this endpoint is the bridge between IndexedDB-first editor behavior and backend-owned persistence

### `PUT /v1/projects/{project_id}/draft`

Responsibilities:

* replace the current draft payload when the client provides the last seen version
* increment the server draft version on success
* update draft save metadata such as `last_saved_by_user_id` and `updated_at`

Contract notes:

* require the client to send the last seen `version`
* return `409 Conflict` on version divergence
* treat the payload as replaceable editor state, not as authority over normalized transcript, translation, or job tables
* if project metadata is mirrored in the payload, either reconcile or validate it against canonical project fields before save

### `POST /v1/projects/{project_id}/archive`

Responsibilities:

* soft-archive the project by setting archival state on the project row
* keep linked transcript, translation, audio, and render records intact

Contract notes:

* prefer `archived_at` plus `status = archived`
* do not hard-delete rows in the first cut

## Service-layer contract

The router should call a project-focused service layer rather than writing ORM logic inline.

Suggested service methods:

* `list_projects(workspace_id, user_context, filters)`
* `create_project(workspace_id, user_context, payload)`
* `get_project(workspace_id, project_id, user_context)`
* `update_project(workspace_id, project_id, user_context, patch_payload)`
* `get_project_draft(workspace_id, project_id, user_context)`
* `put_project_draft(workspace_id, project_id, user_context, draft_payload, version)`
* `archive_project(workspace_id, project_id, user_context)`

Service responsibilities should include:

* enforcing workspace scope and authorization
* loading and persisting ORM models
* keeping `projects.latest_draft_version` in sync with `project_drafts.version`
* validating references like `media_file_id` or `transcript_id` when present
* handling dual-write refresh of mirrored metadata in `draft_payload` during transition

## Database contract assumptions

### `projects`

The router assumes a canonical `projects` table holding identity, ownership, status, and pointers.

Important constraints for route logic:

* `workspace_id` is the tenancy boundary
* `owner_user_id` and `created_by_user_id` are required
* `status` is constrained to supported values such as `draft`, `processing`, `ready`, `failed`, `archived`
* `media_file_id` and `transcript_id` are optional pointers, not required at creation time

### `project_drafts`

The router assumes a latest-draft table carrying editor-session state.

Important constraints for route logic:

* one current draft per `project_id` is sufficient for the first cut
* `version` must increment on every successful save
* `draft_schema_version` should be explicit and returned on every read
* `draft_payload` can temporarily carry cached transcript and translation arrays for compatibility

## Error contract

The router should map common failures to stable errors.

| Condition | Status | Notes |
| --- | --- | --- |
| unauthenticated request | `401` | no valid session or bearer token |
| wrong workspace or unauthorized project access | `403` or `404` | avoid leaking project existence across workspaces |
| project not found in active workspace | `404` | scoped lookup miss |
| invalid request payload | `422` | schema or field validation failure |
| stale draft version on save | `409` | return server version metadata |
| immutable field patch attempt | `400` or `422` | pick one and keep it consistent |

Recommended draft conflict shape:

* `code = DRAFT_VERSION_CONFLICT`
* include `project_id`
* include `client_version`
* include `server_version`
* include `server_updated_at`
* include `last_saved_by_user_id`

## Dual-write compatibility rules

During the IndexedDB-to-backend cutover:

* canonical project metadata lives in `projects`
* the frontend-facing draft payload may still mirror `projectMetadata`
* transcript segments and translations remain canonical in normalized tables even if cached inside `draft_payload`
* route handlers should never treat cached arrays inside `draft_payload` as the authoritative source for completed processing outputs

## Mounting contract in `main.py`

Once implemented, [main.py](#file-3239543912548896) should:

* import the new `projects` router
* mount it under the same API prefix as the other public routes
* keep `/projects/*` separate from `/internal/tasks/*`

The expected public path family is:

* `/v1/projects/*`

## Rollout notes

Following your preferences, keep the rollout additive and reversible:

* add tables first via `translation-migrate`
* deploy `translation-api` with the mounted router next
* redeploy `translation-web` only after the new routes and response shapes are verified
* leave IndexedDB compatibility in place until backend-first hydration has passed validation in more than one browser context

## Validation hooks

Implementation should be considered incomplete until [validation-checklist.md](#file-2060193141886684) passes the `/projects` checks for:

* project shell creation
* project metadata fetch
* draft fetch
* draft save with version increment
* stale-version `409 Conflict`
* multi-browser or multi-device reopen behavior

## Recommended next step

After this contract, the next useful implementation artifact is a concrete backend schema module plan for `projects.py`, `project_service.py`, and the request/response Pydantic models so coding can start with minimal ambiguity.

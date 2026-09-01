# GlobeSync Phase 0 Alembic Migration Checklist

This document defines the first Alembic migration checklist for introducing `projects` and `project_drafts` into the GlobeSync backend.

## Purpose

* Translate the approved `/projects` design into a safe schema rollout plan
* Keep the first database change aligned with the GCP-first backend cutover
* Separate table creation from later backfill and application logic changes
* Make downgrade and rollback expectations explicit before implementation begins

## Related artifacts

* [GCP_MULTI_TENANT_MIGRATION_PLAN.md](#file-2060193141886677)
* [current-state-inventory.md](#file-2060193141886680)
* [draft-field-mapping.md](#file-2060193141886681)
* [deploy-and-rollback-checklist.md](#file-2060193141886683)
* [validation-checklist.md](#file-2060193141886684)
* [projects-api-examples.md](#file-2060193141886685)
* [projects-router-contract.md](#file-2060193141886686)
* [backend-schema-module-plan.md](#file-2060193141886687)

## Scope of this migration

This migration should cover only the first schema needed to support backend-owned project persistence.

Include in scope:

* create `projects`
* create `project_drafts`
* add required indexes and constraints
* add foreign keys from `projects` to existing media, transcript, lip-sync, and export tables where safe
* establish optimistic concurrency support through `project_drafts.version`

Keep out of scope for this first migration:

* backfilling `project_id` or `workspace_id` into downstream pipeline tables
* renaming legacy columns like `organization_id` or `s3_upload_id`
* dropping any current tables or fields
* making existing nullable relationships non-null
* deleting or restructuring IndexedDB compatibility payloads

## Pre-migration assumptions

Before authoring the revision, confirm these assumptions:

* Cloud SQL Postgres remains the source of truth for normalized backend records
* `workspace_id` is the tenancy boundary for new project persistence
* top-level API identifiers remain raw UUIDs
* the editor draft payload continues to live as JSONB in `project_drafts.draft_payload`
* frontend cutover to backend-first hydration happens after this migration and route implementation, not inside this revision
* `translation-migrate` remains the required deployment path for Alembic upgrades on GCP

## Proposed revision intent

Suggested revision name:

* `add_projects_and_project_drafts`

Suggested migration file target:

* `backend/alembic/versions/<revision>_add_projects_and_project_drafts.py`

## Table creation checklist

### 1. Create `projects`

Checklist:

* add `id UUID` primary key
* add `workspace_id UUID NOT NULL`
* add `owner_user_id UUID NOT NULL`
* add `created_by_user_id UUID NOT NULL`
* add `name TEXT NOT NULL`
* add `slug TEXT NULL`
* add `status TEXT NOT NULL DEFAULT 'draft'`
* add `source_language VARCHAR(16) NULL`
* add `target_language VARCHAR(16) NULL`
* add `active_translation_language VARCHAR(16) NULL`
* add `media_file_id UUID NULL`
* add `transcript_id UUID NULL`
* add `current_lipsync_job_id UUID NULL`
* add `current_export_job_id UUID NULL`
* add `last_rendered_video_gcs_path TEXT NULL`
* add `last_opened_at TIMESTAMPTZ NULL`
* add `archived_at TIMESTAMPTZ NULL`
* add `created_at TIMESTAMPTZ NOT NULL`
* add `updated_at TIMESTAMPTZ NOT NULL`

### 2. Create `project_drafts`

Checklist:

* add `id UUID` primary key
* add `project_id UUID NOT NULL`
* add `workspace_id UUID NOT NULL`
* add `version BIGINT NOT NULL`
* add `draft_schema_version TEXT NOT NULL`
* add `draft_payload JSONB NOT NULL`
* add `base_project_updated_at TIMESTAMPTZ NULL`
* add `last_saved_by_user_id UUID NOT NULL`
* add `created_at TIMESTAMPTZ NOT NULL`
* add `updated_at TIMESTAMPTZ NOT NULL`

## Constraint checklist

### `projects`

* primary key on `id`
* check constraint restricting `status` to the initial allowed set
* foreign key from `media_file_id` to the media table primary key
* foreign key from `transcript_id` to the transcript table primary key
* foreign key from `current_lipsync_job_id` to the lip-sync job table primary key
* foreign key from `current_export_job_id` to the export job table primary key

Recommended initial status set:

* `draft`
* `processing`
* `completed`
* `failed`
* `archived`

Note:

* use the status vocabulary already reflected in the frontend `Project` store unless the team intentionally changes that contract before implementation

### `project_drafts`

* primary key on `id`
* foreign key from `project_id` to `projects.id`
* unique constraint on `project_id` for the first-cut single-current-draft model
* optional check constraint enforcing `version >= 1`

### Referential caution

Before adding each foreign key on `projects`, confirm the target table names in the existing SQLAlchemy models and current Alembic history. If model naming differs from the expected pluralized names, match the actual database table names rather than the Python class names.

## Index checklist

Create these indexes in the first revision:

* `projects(workspace_id, updated_at DESC)`
* `projects(workspace_id, owner_user_id, updated_at DESC)`
* `projects(workspace_id, status, updated_at DESC)` if project-list filtering by status is expected immediately
* `project_drafts(workspace_id, updated_at DESC)`
* unique index or unique constraint on `project_drafts(project_id)`

Index notes:

* keep indexes limited to the first list and access patterns already documented in the router contract
* do not add speculative JSONB indexes on `draft_payload` in the first cut
* only add a `slug` uniqueness rule if slug behavior is actually implemented in the API layer

## Timestamp and default checklist

* use server-side defaults for `created_at` and `updated_at`
* make sure `updated_at` is set on row creation even before application-level update hooks exist
* set `projects.status` default to `draft`
* do not set a database default for `project_drafts.version` unless the application and migration agree that first save starts at `1`

Recommended first-save convention:

* create the initial `project_drafts` row with `version = 1`
* increment on every successful `PUT /v1/projects/{project_id}/draft`

## JSONB payload checklist

For `project_drafts.draft_payload`:

* use `JSONB`, not `TEXT`
* do not try to decompose `projectMetadata`, `mediaReferences`, `translations`, `timelineState`, or `uiState` in this migration
* preserve frontend `camelCase` inside the JSON payload
* treat the payload as compatibility/editor state, not as authority over transcript, translation, audio, or job tables

## Upgrade sequencing checklist

Recommended Alembic `upgrade()` order:

1. create `projects`
2. create `project_drafts`
3. add indexes on `projects`
4. add indexes on `project_drafts`
5. add unique constraint or unique index for `project_drafts.project_id`
6. add foreign keys after confirming referenced table names exist in all target environments
7. validate revision against a staging-like database before deployment through `translation-migrate`

Why this order:

* it keeps the new tables self-contained first
* it isolates naming or foreign-key errors late in the migration instead of blocking basic table creation earlier
* it keeps rollback simpler if a foreign-key detail needs adjustment

## Downgrade checklist

Recommended Alembic `downgrade()` order:

1. drop foreign keys added by the revision
2. drop non-primary indexes on `project_drafts`
3. drop non-primary indexes on `projects`
4. drop `project_drafts`
5. drop `projects`

Downgrade rules:

* downgrade is only safe before application code depends on live `/projects` traffic
* once production data exists in these tables, rollback should prefer application rollback plus forward-fix over destructive downgrade unless explicitly approved
* never assume downgrade is harmless just because the schema change is additive

## Backfill sequencing checklist

Backfill does not belong in this first migration, but the migration should be written so later backfill is straightforward.

Later follow-on sequence should be:

1. ship additive schema revision for `projects` and `project_drafts`
2. ship backend models, schemas, services, and router code
3. switch frontend hydration to backend-first
4. begin writing canonical project rows for all new editor sessions
5. only then plan a separate backfill for nullable downstream `project_id` and `workspace_id` references
6. after backfill validation, consider tightening nullability or relationship constraints in later revisions

Downstream tables called out for later backfill:

* media
* transcript
* translation
* generated audio
* lip-sync jobs
* export jobs

## Application rollout checklist

Before merging the migration:

* confirm the status vocabulary matches the frontend `Project.status` contract
* confirm language field lengths and nullable rules match the API examples
* confirm the router contract still expects raw UUIDs
* confirm there is no hidden dependency on prefixed public IDs
* confirm the migration does not require the frontend to change in the same deploy

Before running `translation-migrate` in staging:

* verify the revision imports correctly in Alembic
* verify target table names for all foreign keys
* verify the migration is additive only
* verify downgrade path syntax even if production rollback will likely use forward-fix

Before production rollout:

* run `translation-migrate`
* deploy `translation-api`
* keep `translation-web` unchanged unless the API rollout is paired with frontend cutover work
* capture evidence required by [validation-checklist.md](#file-2060193141886684)

## Validation checklist for this revision

After upgrade, verify:

* `projects` exists with all planned columns
* `project_drafts` exists with all planned columns
* required indexes were created
* required check constraints and unique rules exist
* foreign keys resolve correctly
* inserting a `projects` row with default status produces `draft`
* inserting a `project_drafts` row with `version = 1` succeeds
* inserting a second `project_drafts` row for the same `project_id` fails under the uniqueness rule
* the migration runs cleanly via `translation-migrate`

If a staging API build exists, also verify:

* `POST /v1/projects` can create a project against the new schema
* `GET /v1/projects/{project_id}/draft` and `PUT /v1/projects/{project_id}/draft` align with the versioning model
* stale draft writes surface `409 Conflict` at the application layer

## Risks to watch

* mismatch between frontend `status` values and database check constraint
* incorrect referenced table names for foreign keys
* premature attempt to backfill downstream tables in the same revision
* over-modeling the draft JSON before the editor cutover is complete
* destructive rollback assumptions once live project records exist

## Recommended implementation notes for the author

* keep the first revision additive and reversible in development
* avoid mixing schema creation with data migration logic in the same revision
* write constraint names explicitly so future revisions can alter them cleanly
* use the same terminology as the Phase 0 docs: `workspace_id` for tenancy, `project_drafts` for editor state, and soft archive instead of delete

## Definition of done

This checklist is satisfied when:

* the Alembic revision for `projects` and `project_drafts` is written
* staging upgrade succeeds through `translation-migrate`
* schema validation evidence is captured
* the backend can proceed to ORM model and router implementation without revisiting table shape decisions

## Recommended next step

After this checklist, the next useful implementation artifact is the actual Alembic revision file or a companion execution runbook that maps each checklist item to concrete Alembic operations.

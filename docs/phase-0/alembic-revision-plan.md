# GlobeSync Phase 0 Actual Alembic Revision Plan

This document translates the Phase 0 migration checklist into the concrete authoring plan for the first Alembic revision that adds `projects` and `project_drafts`.

## Purpose

* Turn the Phase 0 schema checklist into a revision-authoring guide
* Make the first `/projects` schema change concrete enough to implement without reopening table-shape decisions
* Keep the first database change additive and GCP rollout-friendly through `translation-migrate`
* Record the exact operation order, naming targets, and validation checkpoints before Phase 1 coding begins

## Related artifacts

* [current-state-inventory.md](#file-2060193141886680)
* [GCP_MULTI_TENANT_MIGRATION_PLAN.md](#file-2060193141886677)
* [projects-router-contract.md](#file-2060193141886686)
* [backend-schema-module-plan.md](#file-2060193141886687)
* [alembic-migration-checklist.md](#file-3212615212764922)
* [validation-checklist.md](#file-2060193141886684)

## Revision target

Suggested Alembic revision slug:

* `add_projects_and_project_drafts`

Suggested file target:

* `backend/alembic/versions/<revision>_add_projects_and_project_drafts.py`

This should be the first Phase 1 backend schema revision for the `/projects` surface.

## Confirmed existing foreign-key targets

Based on the current backend model files, the revision should target these existing tables:

* [media.py](#file-3239543912548903): `media_files`
* [transcript.py](#file-3239543912548904): `transcripts`
* [lipsync_job.py](#file-3239543912548902): `lipsync_jobs`
* [export_job.py](#file-3239543912548899): `export_jobs`

These names should be used in the foreign-key operations unless the live Alembic history shows a divergent table name in the deployed database.

## Revision scope

In scope for this actual revision:

* create `projects`
* create `project_drafts`
* add project status constraint
* add first-pass list and ownership indexes
* add foreign keys from `projects` to existing pipeline tables
* add uniqueness and concurrency support for one current draft per project

Out of scope for this revision:

* backfilling `project_id` or `workspace_id` into downstream tables
* renaming legacy `organization_id`, `storage_provider`, or `s3_upload_id` columns
* moving transcript segments or translations into new tables
* introducing JSONB indexes on `draft_payload`
* deleting any existing data or tables

## Planned schema objects

### New table: `projects`

Target columns:

* `id UUID PRIMARY KEY`
* `workspace_id UUID NOT NULL`
* `owner_user_id UUID NOT NULL`
* `created_by_user_id UUID NOT NULL`
* `name TEXT NOT NULL`
* `slug TEXT NULL`
* `status TEXT NOT NULL DEFAULT 'draft'`
* `source_language VARCHAR(16) NULL`
* `target_language VARCHAR(16) NULL`
* `active_translation_language VARCHAR(16) NULL`
* `media_file_id UUID NULL`
* `transcript_id UUID NULL`
* `current_lipsync_job_id UUID NULL`
* `current_export_job_id UUID NULL`
* `last_rendered_video_gcs_path TEXT NULL`
* `last_opened_at TIMESTAMPTZ NULL`
* `archived_at TIMESTAMPTZ NULL`
* `created_at TIMESTAMPTZ NOT NULL`
* `updated_at TIMESTAMPTZ NOT NULL`

### New table: `project_drafts`

Target columns:

* `id UUID PRIMARY KEY`
* `project_id UUID NOT NULL`
* `workspace_id UUID NOT NULL`
* `version BIGINT NOT NULL`
* `draft_schema_version TEXT NOT NULL`
* `draft_payload JSONB NOT NULL`
* `base_project_updated_at TIMESTAMPTZ NULL`
* `last_saved_by_user_id UUID NOT NULL`
* `created_at TIMESTAMPTZ NOT NULL`
* `updated_at TIMESTAMPTZ NOT NULL`

## Planned constraints and rules

### `projects`

Constraint plan:

* primary key on `id`
* check constraint on `status`
* foreign key on `media_file_id` to `media_files.id`
* foreign key on `transcript_id` to `transcripts.id`
* foreign key on `current_lipsync_job_id` to `lipsync_jobs.id`
* foreign key on `current_export_job_id` to `export_jobs.id`

Recommended allowed status set for the first revision:

* `draft`
* `processing`
* `completed`
* `failed`
* `archived`

Reasoning:

* this matches the existing frontend `Project.status` contract more closely than introducing a new backend-only `ready` value in the first cut

### `project_drafts`

Constraint plan:

* primary key on `id`
* foreign key on `project_id` to `projects.id`
* unique constraint on `project_id`
* optional check constraint enforcing `version >= 1`

Concurrency rule supported by schema:

* the database enforces one current draft row per project, while the application layer enforces version comparison on update

## Planned indexes

Create the following in the revision:

* `ix_projects_workspace_updated_at` on `projects(workspace_id, updated_at)`
* `ix_projects_workspace_owner_updated_at` on `projects(workspace_id, owner_user_id, updated_at)`
* `ix_projects_workspace_status_updated_at` on `projects(workspace_id, status, updated_at)`
* `ix_project_drafts_workspace_updated_at` on `project_drafts(workspace_id, updated_at)`
* `uq_project_drafts_project_id` as either a named unique constraint or unique index on `project_id`

Naming guidance:

* explicitly name every index and constraint so later revisions can alter them without reverse-engineering generated names
* if the repo already uses a naming convention in older Alembic revisions, keep that convention instead of introducing a new one

## Timestamp and default plan

Use server-side defaults in the revision for:

* `projects.created_at`
* `projects.updated_at`
* `project_drafts.created_at`
* `project_drafts.updated_at`

Use a server-side default for:

* `projects.status = 'draft'`

Do not set a server-side default for:

* `project_drafts.version`

Reasoning:

* the service layer should decide when the first draft row is created and should write `version = 1` explicitly

## Planned Alembic authoring structure

The revision should contain three clear sections in `upgrade()`:

1. create tables
2. add indexes and constraints
3. add foreign keys after tables exist

The `downgrade()` should reverse those sections in the opposite order.

## Planned `upgrade()` sequence

### Step 1: create `projects`

Authoring plan:

* create the `projects` table with all non-derived columns
* include the primary key inline
* include `status` default inline
* include timestamp defaults inline
* do not include application-only concepts such as `latest_draft_version` if that field is not actually being stored in this first revision

### Step 2: create `project_drafts`

Authoring plan:

* create the `project_drafts` table with `draft_payload JSONB`
* include timestamps inline
* keep `version` required but application-managed
* include `project_id` and `workspace_id` as explicit columns even though the project row already has workspace context

Reasoning:

* this preserves direct workspace scoping for draft queries and aligns with the Phase 2 contract

### Step 3: add `projects` status constraint

Authoring plan:

* add an explicitly named check constraint for the allowed status set
* keep the values consistent with the frontend store contract during the initial rollout

### Step 4: add `project_drafts` version constraint

Authoring plan:

* add an explicitly named check constraint for `version >= 1` if the team wants the guardrail at the database layer
* skip only if there is a strong reason to avoid any write restriction during the cutover

### Step 5: add indexes

Authoring plan:

* add the three `projects` list/filter indexes
* add the workspace/time index on `project_drafts`
* add the uniqueness rule on `project_drafts.project_id`

### Step 6: add foreign keys from `projects`

Authoring plan:

* add foreign key from `projects.media_file_id` to `media_files.id`
* add foreign key from `projects.transcript_id` to `transcripts.id`
* add foreign key from `projects.current_lipsync_job_id` to `lipsync_jobs.id`
* add foreign key from `projects.current_export_job_id` to `export_jobs.id`

Delete behavior guidance:

* prefer `SET NULL` on these foreign keys for the first revision unless the repo already has a stronger established lifecycle rule
* avoid `CASCADE` from project pointer fields into shared pipeline artifacts

### Step 7: smoke-validate the schema locally or in staging

Verification plan:

* confirm both tables exist
* confirm indexes and named constraints exist
* confirm the foreign keys resolve against the current deployed schema
* confirm `projects.status` defaults to `draft`
* confirm duplicate `project_drafts.project_id` writes fail as expected

## Planned `downgrade()` sequence

Reverse order:

1. drop `projects` foreign keys
2. drop unique and secondary indexes on `project_drafts`
3. drop secondary indexes on `projects`
4. drop `project_drafts` constraints not removed automatically by table drop, if needed by the dialect strategy used
5. drop `project_drafts`
6. drop `projects`

Downgrade safety notes:

* this downgrade is structurally valid for development and early staging
* once production traffic writes live project data, rollback should generally mean rolling application code back and forward-fixing schema issues rather than dropping populated tables

## Validation plan after authoring

Before merge:

* compare the revision against [alembic-migration-checklist.md](#file-3212615212764922)
* compare column names and nullable rules against [backend-schema-module-plan.md](#file-2060193141886687)
* confirm the status set still matches the frontend project store
* confirm there is still no canonical `projects` table in the deployed schema

Before staging deploy:

* run the revision through `translation-migrate`
* inspect upgrade logs for foreign-key name mismatches
* verify the revision is additive only
* verify downgrade compiles and can run on a non-production database

After staging upgrade:

* create a sample `projects` row
* create a sample `project_drafts` row with `version = 1`
* verify uniqueness on `project_id`
* verify `draft_payload` accepts the current editor-style JSON structure

## Handoff into backend coding

Once this revision plan is accepted, the implementation order should be:

1. write the actual Alembic revision file
2. add `backend/app/models/project.py`
3. register the new models in the ORM metadata path
4. add `backend/app/schemas/projects.py`
5. add `backend/app/services/project_service.py`
6. add `backend/app/routers/projects.py`
7. mount the router in [main.py](#file-3239543912548896)
8. validate against [validation-checklist.md](#file-2060193141886684)

## Open implementation choices still allowed

These choices can still be made during authoring without changing the plan materially:

* named unique constraint versus named unique index for `project_drafts.project_id`
* whether the `version >= 1` rule is enforced in both schema and service layer or only in the service layer
* whether the foreign keys use `SET NULL` or no explicit delete clause, depending on existing backend conventions
* whether `slug` remains nullable and non-unique until the API actually uses it

## Recommended next step

After this plan, the next concrete artifact is the actual Alembic revision file under the backend Alembic versions directory, or a Phase 1 coding checklist that tracks revision, model, schema, service, router, and mount work as executable tasks.

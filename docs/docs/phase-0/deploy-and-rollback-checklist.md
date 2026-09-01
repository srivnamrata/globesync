# GlobeSync Phase 0 Deploy and Rollback Checklist

This checklist defines the deployment order, pre-flight checks, rollback triggers, and rollback actions for the current GlobeSync GCP deployment model.

## Purpose

* Protect production while Phase 0 and Phase 2 migration work changes schemas, routes, and editor persistence behavior
* Make deploy order explicit across `translation-migrate`, `translation-api`, and `translation-web`
* Capture the minimum smoke checks required before and after rollout
* Define rollback behavior before any backend-first project persistence cutover begins

## Deployment assumptions

Following your preferences, this checklist assumes the current GCP-first deployment shape:

* Cloud Run Job: `translation-migrate`
* Cloud Run service: `translation-api`
* Cloud Run service: `translation-web`
* Cloud SQL Postgres is the system of record for backend pipeline data
* GCS stores uploaded media and generated artifacts
* Cloud Tasks drives production async execution for transcription, translation, and lip-sync internal handlers

## Current rollout checkpoint

Following your preferences, the current production rollout checkpoint is:

* Alembic chain continuity has been repaired, including rebasing [20260829_03_add_identity_tenancy_tables.py](#file-2724092822522421) to `20260821_01`
* [20260830_04_add_workspace_scope_to_pipeline_tables.py](#file-840101848495057) was reduced to table-safe backfills only, with project-based backfill deferred until later in the chain
* SQLAlchemy model registration was fixed in [app/models/__init__.py](#file-3239543912548898) and [main.py](#file-3239543912548896) so startup loads all mappers cleanly
* Redis-backed event publishing now no-ops when Redis is not configured, reducing Cloud Run warning noise
* Legacy auth fallback based on `legacy_user_id` has been removed; access is now enforced by workspace or project scope only
* Cloud Run deployment config now preserves multiple allowed CORS origins instead of replacing them with only the current `translation-web` URL
* Post-deploy browser/API smoke checks and Cloud SQL workspace/project coverage checks have been completed successfully
* Phase 0 and the current migration-plan phases are now complete
* No blocking rollout tasks remain from this checklist; only commit, evidence capture, and optional cleanup follow-ups remain

## Change categories this checklist covers

| Change type | Examples | Requires migration job | Requires API deploy | Requires web deploy |
| --- | --- | --- | --- | --- |
| Schema-only | Add `projects` table, add `workspace_id`, new indexes | Yes | Usually yes if code reads new schema | No unless frontend contract changes |
| Backend-only | Mount router, change internal task handler, change request/response validation | No unless schema-dependent | Yes | No unless frontend contract changes |
| Frontend-only | UI text, polling behavior, local hydration logic | No | No unless it depends on new routes | Yes |
| Contract change | New `/projects` endpoints, changed transcript response usage, auth/session behavior | Often yes | Yes | Yes |
| Background task change | Transcription, translation, TTS, lip-sync task payloads or handlers | Possibly | Yes | No unless UX contract changes |

## Golden deployment rule

For schema-dependent releases, deploy in this order:

1. Run `translation-migrate`
2. Deploy `translation-api`
3. Deploy `translation-web`

Do not reverse steps 2 and 3 when request/response contracts change.

## Pre-deploy checklist

### A. Scope and dependency review

* Confirm which of these are changing: schema, API routes, internal task handlers, frontend API calls, frontend hydration/save behavior
* Confirm whether the change touches any currently known fragile areas:
  * missing `/projects` API surface
  * transcript route compatibility
  * mounted TTS routes
  * IndexedDB-first editor hydration
  * Cloud Tasks target paths under `/v1/internal/tasks/*`
* Confirm whether the release is additive, dual-write, or destructive
* Confirm whether any old browser-draft assumption is being removed; if yes, require rollback notes before deploy

### B. Database and migration safety

* Review the Alembic migration for backward compatibility
* Prefer additive schema changes first:
  * add nullable columns
  * add new tables
  * add indexes
  * backfill before tightening constraints
* Do not deploy code that requires non-null `workspace_id` or `project_id` before backfill exists
* Confirm the migration is safe to run exactly once in production
* Confirm the migration can be retried safely or has a clear manual recovery path

### C. API and task-path safety

* Confirm new public routes are mounted in [main.py](#file-3239543912548896)
* Confirm internal handler paths still match Cloud Tasks targets
* Confirm any renamed request or response fields remain backward compatible during the cutover window
* Confirm route changes that affect the editor are reflected in [projectService.ts](#file-/Users/roboplaylab@gmail.com/globesync/frontend/services/projectService.ts)
* Confirm `NEXT_PUBLIC_API_URL` still resolves to a base path ending in `/v1`

### D. Frontend and cache safety

* Confirm whether existing browser drafts will still load after the release
* If payload shape changes, include a compatibility adapter rather than breaking older IndexedDB rows abruptly
* Confirm whether new frontend behavior requires a full `translation-web` rebuild and deploy
* Confirm whether UI still handles missing backend data gracefully during partial rollout

### E. Observability readiness

* Identify the Cloud Run revision currently serving production for `translation-api`
* Identify the Cloud Run revision currently serving production for `translation-web`
* Confirm access to Cloud Run logs for API, web, and migration job
* Confirm access to Cloud Tasks execution logs or task visibility
* Confirm which smoke checks will be run immediately after deploy

## Deployment runbook

### Step 1: Freeze release inputs

* Record the commit SHA or release tag for backend and frontend
* Record the Alembic revision(s) included in this release
* Record whether the release introduces:
  * new schema
  * new routes
  * background-task changes
  * frontend persistence changes

### Step 2: Run schema migration job first

* Execute `translation-migrate`
* Wait for completion and inspect logs before moving on
* If the migration fails, stop the rollout
* Do not deploy schema-dependent API code until the migration job succeeds

### Step 3: Deploy `translation-api`

* Deploy backend changes after successful migration
* Confirm the new revision becomes healthy
* Confirm these route families respond as expected for the release scope:
* Confirm browser preflight requests succeed for public frontend-driven endpoints, especially `OPTIONS /v1/translation/languages`
  * `/media/uploads/*`
  * `/transcription/*`
  * `/translation/*`
  * `/tts/*` when applicable
  * `/lipsync/*`
  * `/internal/tasks/*`
  * `/projects/*` once implemented
* Confirm internal task targets referenced by Cloud Tasks resolve on the new revision

### Step 4: Run backend smoke checks

* Create or fetch a transcript successfully
* Fetch translations for a known transcript and target language
* Confirm `POST /tts/synthesize-project` is live if the release depends on TTS
* Start a lip-sync render and confirm `GET /lipsync/job/{jobId}` returns expected status structure
* If `/projects` is in scope, verify project create/read/draft read-write round trips before frontend rollout

### Step 5: Deploy `translation-web`

* Deploy the frontend only after backend routes and contracts are confirmed live
* Confirm the correct API base path is bundled
* Confirm the editor can still load current draft state without a blank-screen or redirect regression

### Step 6: Run frontend smoke checks

* Open an existing editor session and verify hydration succeeds
* Verify local autosave still writes without immediate console-visible failures
* Verify translation refresh still populates missing local translations
* Verify lip-sync status still updates in the UI
* If `/projects` cutover is in scope, verify backend-first project load and draft save behavior on a second browser/device scenario

## Roll-forward gates

Proceed to full release only if all of these are true:

* `translation-migrate` completed successfully
* `translation-api` health checks pass
* required routes are mounted and reachable
* Cloud Tasks-dispatched handlers accept requests successfully
* no immediate Cloud SQL schema mismatch errors appear in API logs
* the editor can still open and complete a basic translation or render path

## Rollback triggers

Rollback should start immediately if any of these appear after deploy:

* `translation-migrate` succeeded but `translation-api` crashes on startup or returns schema mismatch errors
* Cloud Tasks requests begin failing because `/v1/internal/tasks/*` targets no longer match deployed handlers
* editor load redirects users away because draft hydration assumptions broke unexpectedly
* transcript, translation, TTS, or lip-sync paths return contract-breaking responses to the current frontend
* `/projects` or draft-write rollout causes destructive overwrite, missing project state, or cross-workspace data exposure
* signed artifact URLs, GCS writes, or Cloud SQL writes fail broadly after release

## Rollback strategy by layer

### A. Frontend rollback

Use when the issue is limited to UI behavior, hydration, or contract consumption and the backend is otherwise healthy.

* Roll `translation-web` back to the prior healthy revision
* Keep `translation-api` on the current revision only if the new backend remains backward compatible with the old frontend
* Clear only release-specific browser compatibility assumptions; do not require destructive user-side storage cleanup unless absolutely necessary
* If local draft parsing regressed, restore compatibility code in the next forward fix rather than telling users to delete drafts

### B. Backend rollback

Use when routes, task handlers, or response contracts are broken.

* Roll `translation-api` back to the prior healthy revision
* Confirm Cloud Tasks continues targeting valid `/v1/internal/tasks/*` paths on the restored revision
* Re-run smoke checks for transcription, translation, TTS, and lip-sync status APIs
* If the schema migration was additive, leave the migrated schema in place during API rollback

### C. Schema rollback

Use only when the migration itself is bad and cannot safely remain in place.

* Prefer forward-fix over destructive schema rollback whenever possible
* Only run a down migration if it has been explicitly reviewed for data safety
* Do not drop newly created tables or columns if live traffic may already have written production data into them
* If a new table such as `projects` or `project_drafts` is additive and unused by the restored API, it is usually safer to leave it in place temporarily

### D. Split rollback guidance

| Failure shape | Preferred action |
| --- | --- |
| Migration failed before API deploy | Fix migration, rerun job, no web rollback needed |
| API broken after successful migration | Roll back `translation-api`; usually keep additive schema |
| Web broken after healthy API deploy | Roll back `translation-web` only |
| API and web contract mismatch | Roll back `translation-web` first if old API is backward compatible; otherwise roll back both |
| Cloud Tasks handler mismatch | Roll back `translation-api` to revision with valid internal routes |
| Draft persistence cutover regression | Roll back `translation-web`, and roll back `translation-api` too if new draft endpoints caused data loss or incompatibility |

## Phase 2 specific guardrails for `/projects` cutover

These rules should apply once backend-owned projects and drafts are introduced:

* Keep IndexedDB as cache-only only after server draft read/write is proven stable
* During transition, dual-write project metadata carefully if the frontend still mirrors metadata into the draft payload
* Do not remove support for existing `HeygenXFile` payloads until old browser drafts can be read or migrated safely
* Additive schema first, backfill second, non-null constraints later
* Treat `409 Conflict` responses on draft version mismatch as a launch gate for multi-device safety, not an optional enhancement

## Minimal production smoke checks

* Upload path returns a valid target for media ingestion
* `POST /transcription/start` accepts work and results in transcript persistence
* `GET /transcription/{transcriptId}` returns ordered segments
* `POST /translation/translate-project` completes and `GET /translation/{transcriptId}` returns persisted rows
* `POST /tts/synthesize-project` is reachable when in scope
* `POST /lipsync/render-project` creates a job and `GET /lipsync/job/{jobId}` advances state
* Existing editor drafts still open successfully
* If `/projects` is live, project create/load/draft-save succeeds across at least two browser contexts

## Release sign-off record

Before marking a release complete, capture:

* backend revision deployed
* frontend revision deployed
* migration revision applied
* smoke checks passed
* post-deploy CORS preflight and workspace/project coverage checks passed
* any deferred cleanup or follow-up migration work
* whether rollback remains possible without user-visible data loss

## Post-completion note

This checklist now reflects a completed rollout checkpoint. Keep it as the historical deploy record for this phase set, and track any future cleanup or new rollout work in a separate phase-specific checklist.

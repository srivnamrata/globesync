# GlobeSync Phase 0 Validation Checklist

This checklist defines how to validate GlobeSync changes in staging or an isolated environment before production rollout, and which minimum production smoke checks must pass after deployment.

## Purpose

* Turn the migration plan and deploy guardrails into an executable validation script
* Catch schema, route, task-dispatch, and editor-hydration regressions before production impact
* Keep validation aligned with the current GCP-first deployment shape
* Establish the evidence that should be captured for each release

## Validation assumptions

Following your preferences, this checklist assumes:

* Cloud Run Job: `translation-migrate`
* Cloud Run service: `translation-api`
* Cloud Run service: `translation-web`
* Cloud SQL Postgres is canonical for backend pipeline records
* GCS holds uploaded media and generated artifacts
* Cloud Tasks is the preferred production async path
* Browser IndexedDB is still the current editor source of truth until `/projects` cutover is complete

## Current validation checkpoint

Following your preferences, the current checkpoint before final production sign-off is:

* Migration ordering and continuity issues have been repaired and redeploys now complete successfully
* Workspace/project scoping has been tightened across backend routes and the legacy user fallback has been removed
* SQLAlchemy mapper startup errors and optional Redis runtime warnings have been addressed
* The current blocking production verification item is the API redeploy for the CORS allow-list change before rerunning browser tests
* After that redeploy, the required checks are: `/health`, `/healthz`, `OPTIONS /v1/translation/languages`, representative workspace-scoped API reads/writes, and Cloud SQL workspace/project coverage validation

## When to run this checklist

Run this checklist for any change that affects one or more of:

* Alembic migrations
* backend route wiring
* Cloud Tasks internal handlers
* editor hydration or auto-save behavior
* transcript, translation, TTS, or lip-sync request/response contracts
* the future `/projects` and `/projects/{project_id}/draft` surface

## Validation environments

| Environment | Purpose | Required checks |
| --- | --- | --- |
| Local or isolated backend test path | Fast feedback on route/model logic | basic route health, request validation, migration dry run |
| Staging or production-like GCP path | Full integration with Cloud Run, Cloud SQL, GCS, Cloud Tasks | end-to-end upload, transcription, translation, TTS, lip-sync, draft/editor checks |
| Production post-deploy | Final smoke confirmation | critical path checks only, no destructive experiments |

## Pre-validation setup

### A. Release metadata

* Record backend commit SHA
* Record frontend commit SHA
* Record Alembic revision(s) included
* Record which surfaces changed: schema, API, tasks, frontend, or contract

### B. Test data and accounts

* Identify at least one known-good media file for upload/transcription tests
* Identify at least one existing draft-bearing project for editor hydration checks
* Identify a target language pair that is already supported by backend validation rules
* If `/projects` is in scope, identify a test user and workspace context for create/read/save checks

### C. Operational visibility

* Confirm access to Cloud Run logs for `translation-migrate`, `translation-api`, and `translation-web`
* Confirm access to Cloud Tasks execution visibility
* Confirm access to Cloud SQL query/log visibility as needed
* Confirm GCS object inspection access for raw and generated artifact paths

## Staging validation checklist

### 1. Schema and migration checks

* Run `translation-migrate` in the validation environment before schema-dependent backend deploys
* Confirm the migration completes successfully
* Confirm the API can start against the migrated schema without startup errors
* Confirm additive objects expected by the release now exist
* If backfill is part of the release, confirm representative rows were updated as expected
* If constraints were tightened, confirm older code paths are not still writing null or legacy-shaped values

### 2. Backend route checks

* Confirm [main.py](#file-3239543912548896) mounted routes are live for the release scope
* Verify health or representative requests for:
  * `/media/uploads/*`
  * `/transcription/*`
  * `/translation/*`
  * `/tts/*` when in scope
  * `/lipsync/*`
  * `/internal/tasks/*`
  * `/projects/*` when implemented
* Confirm known route mismatches have not been reintroduced
* Confirm request validation and response payloads match frontend expectations

### 3. Cloud Tasks dispatch checks

* Trigger a transcription request and confirm a Cloud Task is created when tasks are enabled
* Confirm the task reaches the matching `/v1/internal/tasks/*` handler successfully
* Confirm Cloud Tasks header verification passes in the internal handler
* Confirm task failures, if any, are visible in logs with enough context to diagnose
* Confirm no task is targeting an outdated or renamed internal path

### 4. Storage and persistence checks

* Confirm upload registration creates the expected Cloud SQL and GCS metadata
* Confirm source media lands in the expected GCS location
* Confirm transcript rows and `transcript_segments` rows are persisted after transcription
* Confirm translation rows are persisted and are readable by transcript and target language
* Confirm generated audio artifacts are written to GCS when TTS is exercised
* Confirm lip-sync or rendered output writes its artifact path and job metadata successfully

### 5. Editor hydration and cache checks

* Open an existing project/editor session that depends on IndexedDB and confirm it still hydrates correctly
* Confirm the editor still redirects only when the local draft is genuinely absent
* Confirm translation refresh still fills incomplete local translation state from backend data
* Confirm local autosave still writes updated draft payloads without obvious regression
* Confirm older cached drafts are still readable if the release changed draft payload shape

### 6. Runtime behavior checks

* Transcription path completes and returns retrievable transcript data
* Translation path completes and returns persisted translation rows
* TTS path is reachable and produces generated audio records when in scope
* Lip-sync render path creates a job and progresses through status updates
* Signed output URLs are returned when expected for completed render output
* No unexpected fallbacks, timeouts, or contract-shape mismatches appear in logs

## Phase 2 `/projects` cutover checks

Run these when backend-owned project persistence is introduced:

* `POST /v1/projects` creates a project shell successfully
* `GET /v1/projects/{project_id}` returns canonical metadata expected by the editor
* `GET /v1/projects/{project_id}/draft` returns a server draft payload compatible with current hydration logic
* `PUT /v1/projects/{project_id}/draft` saves successfully with the last seen version
* Version mismatch returns `409 Conflict` instead of silent overwrite
* A project created in one browser can be opened in another without depending on prior local IndexedDB state
* IndexedDB acts as cache/fallback and not the only source of truth

## Production smoke checklist

Run these immediately after deploying in this order: `translation-migrate`, then `translation-api`, then `translation-web`.

### Backend smoke checks

* Confirm `OPTIONS /v1/translation/languages` returns a successful preflight response from the active `translation-api` revision

* Confirm the new `translation-api` revision is healthy
* Confirm a representative transcript fetch works
* Confirm a representative translation fetch works
* Confirm `POST /tts/synthesize-project` is reachable when the release depends on TTS
* Confirm `POST /lipsync/render-project` and `GET /lipsync/job/{jobId}` work for a representative request
* Confirm Cloud Tasks-dispatched internal handlers are accepting work

### Frontend smoke checks

* Confirm the new `translation-web` revision is healthy
* Open the editor and verify it does not fail on startup
* Confirm draft hydration still works for an existing project
* Confirm translation status or render status still updates in the UI
* If `/projects` is live, confirm create/load/save works from the browser against backend persistence

## Regression signals to watch

Treat these as release blockers or immediate investigation triggers:

* editor opens but redirects because expected draft state cannot be found
* transcript fetch returns unexpected shape or missing segments
* translation fetch succeeds but the editor fails to map or display results
* TTS route exists in code but is not live in Cloud Run
* Cloud Tasks dispatch succeeds but internal handler requests fail
* lip-sync status never advances or never returns output URLs
* newly created GCS artifacts appear without matching Cloud SQL metadata, or vice versa
* `/projects` saves overwrite newer drafts instead of rejecting stale versions

## Evidence to capture per validation run

* deployed backend revision
* deployed frontend revision
* migration revision applied
* timestamp of validation run
* test media file used
* transcript ID, media ID, job ID, or project ID generated during validation
* links or references to key Cloud Run and Cloud Tasks logs
* pass/fail result for each major validation section
* follow-up defects or deferred items

## Exit criteria for a safe release

A release is ready only when:

* schema changes have been applied successfully
* API revisions start cleanly and expose the expected routes
* Cloud Tasks reaches the correct internal handlers
* transcript and translation persistence behave correctly
* TTS and lip-sync paths work for releases that touch them
* editor hydration and draft save behavior do not regress
* any `/projects` changes pass multi-browser or multi-device validation

## Recommended next step

After this checklist, the next useful implementation artifacts are:

* [projects-api-examples.md](#file-2060193141886685) for concrete `/projects` request and response payloads
* [projects-router-contract.md](#file-2060193141886686) for the FastAPI router, service, and error-boundary implementation contract

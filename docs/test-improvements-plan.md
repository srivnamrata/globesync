# GlobeSync test improvements plan

## Goal
Strengthen test coverage so `globesync` catches runtime, browser, integration, and GCP-specific regressions earlier without making CI too slow or expensive.

## Current confirmed gaps
* Frontend E2E coverage is primarily mock-backed, so it validates UI behavior more than browser-to-real-API compatibility.
* CI currently runs Chromium-only E2E via `frontend/package.json` (`test:e2e`), even though `frontend/playwright.config.ts` defines Firefox and WebKit projects.
* There is no dedicated credentialed staging smoke suite for Google OAuth, GCS uploads, Cloud Tasks delivery, Google STT/TTS, translation, or lip-sync integrations.
* Load, soak, worker saturation, and performance thresholds are not yet covered.
* Security and accessibility automation need broader runtime coverage beyond the existing GitHub scans.
* Router/runtime regression checks should be expanded so mounted API surfaces are asserted explicitly.

## Priority order
1. Backend integration and router/runtime assertions
2. Cross-browser smoke coverage
3. GCP staging smoke coverage
4. Performance and worker stress coverage
5. Security, authorization, fuzz, and accessibility coverage

## Execution status
### Workstream status
* Workstream 1: backend integration and runtime assertions — Completed
* Workstream 2: cross-browser smoke coverage — Completed
* Workstream 3: GCP staging smoke coverage — In progress
* Workstream 4: performance and worker stress — Not started
* Workstream 5: security, authorization, fuzz, and accessibility — Not started

### Immediate step status
1. Stabilize and finish backend router/runtime tests — Completed
2. Add one assembled-app integration suite for critical API paths — Completed
3. Wire a PR-blocking Firefox smoke lane while keeping WebKit in a slower lane first — Completed
4. Define GCP staging resources, secrets, cost caps, and provider-by-provider checks — Completed
5. Add security, accessibility, and performance waves after the above are green — Not started

## Test pyramid and responsibilities
* Unit and component tests should validate isolated logic, state transitions, serializers, and error mapping.
* Integration tests should validate the assembled FastAPI app, database wiring, storage abstractions, and internal task handoffs.
* Mock-backed Playwright tests should continue to cover deterministic UI workflows and editor behavior.
* Staging smoke tests should validate real GCP-managed dependencies and browser-to-deployed-service compatibility.
* Performance and security suites should stay focused on non-functional risk, not duplicate the happy-path coverage above.

## CI lane design
### Pull request blocking lanes
* Backend unit plus integration coverage
* Frontend unit and coverage gate plus production build
* Playwright Chromium critical paths
* Lightweight Firefox smoke coverage
* Router/runtime assertions for mounted backend surfaces

### Nightly or manually triggered lanes
* WebKit smoke coverage
* Credentialed GCP staging smoke suite
* Load, soak, queue, and worker stress tests
* Extended security and fuzz campaigns

## Environment and fixture prerequisites
* Define dedicated GCP staging resources for OAuth, Cloud Run, Cloud Tasks, Cloud SQL, and media buckets.
* Use small, fixed-cost media fixtures for upload, transcript, translation, dubbing, and export checks.
* Add cleanup rules for staging-created projects, drafts, jobs, and exported media.
* Store provider credentials and staging URLs only in CI secrets and environment-specific config.

## Exit criteria for plan completion
* Each critical user journey is covered at the appropriate test layer without overloading PR CI time.
* At least one failing route registration, auth bootstrap, upload, export, or provider wiring regression is caught by assembled-app or staging tests rather than only by manual QA.
* CI clearly separates fast blocking quality gates from slower confidence-building suites.
* Test failures produce enough logs, traces, and artifacts to diagnose issues without rerunning blindly.

## Workstream 1: backend integration and runtime assertions
**Status:** Completed

### Scope
* Add API integration tests that exercise mounted FastAPI routes through the app surface, not only router modules in isolation.
* Add assertions for intended router registration under `settings.API_V1_STR`.
* Add integration coverage for export, auth bootstrap, project, transcription, translation, and internal task entrypoints.

### Acceptance criteria
* Missing or mis-mounted routers fail CI immediately.
* Core API paths are exercised through the assembled application.
* At least one integration suite runs against real backend wiring with database and storage test doubles or emulators.

### Progress notes
* Completed: tightened backend router/runtime assertions around exported router prefixes and mounted registration behavior using the `mount_api_routers` helper.
* Completed: finished Step 1 plan work and handed validation to the normal backend pipeline environment.
* Completed: added an assembled-app integration suite for critical API paths.
* Completed: added an initial assembled-app auth bootstrap integration test to exercise mounted `/v1/auth/bootstrap` wiring through `main.app`, including dependency overrides and global request middleware behavior.
* Completed: added mounted `/v1/translation/languages` coverage through `main.app` to verify assembled routing, middleware headers, and supported-language payload shape.
* Completed: began cross-browser smoke planning with Firefox as the first PR-blocking expansion.

## Workstream 2: cross-browser smoke coverage
**Status:** Completed

### Scope
* Keep Chromium as the main E2E lane.
* Add a concise Firefox smoke suite and a concise WebKit smoke suite covering sign-in shell, workspace load, editor open, save, and one export/build happy path.

### Acceptance criteria
* CI runs a small cross-browser matrix on critical paths.
* Browser-specific selector, media, and layout regressions are caught before merge.

### Progress notes
* Completed: tagged a concise Firefox smoke slice across landing, workspace project creation, editor open/readiness, editor save, and dub export happy-path coverage.
* Completed: added a PR-blocking GitHub Actions Firefox lane that installs Firefox and runs only the `@smoke` Playwright subset.
* Completed: added [webkit-smoke.yml](#file-4494420290882232) plus the `test:e2e:smoke:webkit` frontend script as a slower, non-blocking manual WebKit smoke lane for the same `@smoke` subset.

## Workstream 3: GCP staging smoke coverage
**Status:** In progress

### Scope
* Add credentialed smoke tests against staging resources for Google OAuth, GCS signed/resumable uploads, Cloud Tasks internal callbacks, Google STT/TTS, translation, and render/export flows.
* Use dedicated staging resources, strict timeouts, and cost caps.

### Acceptance criteria
* Deploy-time and environment-level regressions are caught outside mocks.
* Staging smoke tests are safe to rerun and isolated from production data.

### Initial staging definition
* Baseline GCP deployment targets: project `project-794c406e-c0ab-4a50-8e9`, region `asia-south1`, Cloud Run services `translation-api` and `translation-web`, and migration job `translation-migrate`.
* Baseline runtime resources: Cloud SQL instance `translation-pg`, Cloud Tasks queue `translation-jobs`, raw bucket `project-794c406e-c0ab-4a50-8e9-media-raw`, exports bucket `project-794c406e-c0ab-4a50-8e9-media-exports`, and runtime service account `globesync@project-794c406e-c0ab-4a50-8e9.iam.gserviceaccount.com`.
* Baseline required secrets for staging validation: `translation-database-url`, `translation-sync-database-url`, and `translation-jwt-secret`; include `webhook-secret` and `replicate-api-token` only when the exercised path depends on those integrations.
* Baseline provider checks: Google sign-in bootstrap, signed or resumable upload initiation, Cloud Tasks callback reachability for internal handlers, Google STT or fallback transcription dispatch, Google translation response path, Google TTS synthesis path, and at least one dub export completion path.
* Initial cost controls: use one short deterministic media fixture, one workspace/project per run, strict per-step timeouts, zero long soak loops, and explicit cleanup for staging-created drafts and exports.

### Staging smoke execution checklist
1. Verify deployment identity and reachability: confirm `translation-api` responds on `/health`, `translation-web` loads, and the deployed environment still points to the intended project, region, and OAuth client ID.
2. Verify auth bootstrap: sign in through the real Google flow or a staging-approved authenticated path, then confirm the workspace bootstrap response and premium workspace landing behavior.
3. Verify upload initialization: request a signed or resumable upload, upload the short deterministic media fixture, and capture request IDs plus returned storage targets.
4. Verify async orchestration: start transcription or translation, confirm Cloud Tasks dispatch targets the internal handlers, and confirm the queue plus OIDC audience are accepted by the API.
5. Verify provider responses: confirm at least one successful Google translation path, one Google TTS path, and one transcription path with the expected provider or fallback behavior.
6. Verify export completion: run at least one dub-only export end to end and confirm the output artifact is retrievable from the expected staging location.
7. Cleanup aggressively: delete staging-created projects, drafts, queued artifacts, and generated outputs so repeated runs stay low-cost and isolated.

### Required artifacts and failure capture
* Persist Cloud Run revision identifiers, response request IDs, and affected project IDs for every failing step.
* Save Playwright traces or screenshots for browser failures and API response bodies for backend failures.
* Capture Cloud Run logs for `translation-api`, plus Cloud Tasks delivery evidence for async failures, before rerunning.
* Treat missing queue setup, invalid OIDC audience, missing secrets, and storage permission errors as environment failures, not flaky test retries.

### Lane and gating guidance
* Keep Workstream 3 non-blocking until the staging checklist can pass twice consecutively without manual environment fixes.
* Trigger staging smoke on demand for deploy validation before considering any pull-request blocking promotion.
* Do not include lip-sync or webhook-dependent checks in the base staging gate unless `replicate-api-token` or `webhook-secret` is explicitly present for that environment.
* Promote only the lowest-cost stable subset first: health, auth bootstrap, upload initiation, one provider-backed transcription path, and one dub-only export retrieval path.
* Keep authenticated bootstrap optional in CI until `STAGING_AUTH_BEARER_TOKEN` is provisioned and rotated as a deliberate staging-only secret.
* Keep internal-task auth validation optional until the CI principal can impersonate `globesync@project-794c406e-c0ab-4a50-8e9.iam.gserviceaccount.com` or an equivalent allowed Cloud Tasks identity.
* Keep upload-initiation validation optional until the staging bearer token and low-cost fixture metadata are explicitly provisioned for repeatable smoke runs.
* Keep low-cost fixture upload validation optional until the staging bearer token can create and archive dedicated smoke-test projects without operator intervention.
* Keep provider-backed transcription validation optional until the staging environment can complete a short Google STT run within the configured smoke-test timeout budget.
* Keep dub-only export retrieval optional until the staging environment can complete the generated speech fixture, translation, Google TTS-backed dubbing, and signed-download retrieval path within the configured smoke-test timeout budget.
* Keep deployed-browser validation optional until the staging web URL and a reusable staging auth token plus workspace assertion inputs are explicitly provisioned in CI.

### Progress notes
* Completed: added [staging-smoke.sh](#file-1306546793058167) as the first reusable GCP staging preflight runner for service reachability, required secrets, queue and bucket existence, deployed runtime wiring, and `/health` plus `/healthz` checks.
* Completed: wired [staging-smoke.yml](#file-1306546793058168) as a non-blocking manual GitHub Actions path with retained artifacts for the staging preflight runner.
* Completed: extended [staging-smoke.sh](#file-1306546793058167) with an optional authenticated `/v1/auth/bootstrap` validation that reuses a bearer token secret and optional workspace override.
* Completed: added an optional internal-task auth and route-reachability check that uses an impersonated identity token plus a deliberate invalid payload to validate `/v1/internal/tasks/transcribe` without mutating staging data.
* Completed: added an optional signed-resumable upload-initiation validation that captures upload session and GCS target metadata without uploading fixture bytes yet.
* Completed: added [staging-browser.spec.ts](#file-3009620763232243) plus staging workflow wiring for an optional deployed Chromium validation of the signed-out marketing shell and authenticated workspace landing behavior.
* Completed: extended [staging-smoke.sh](#file-1306546793058167) with an optional low-cost fixture upload path that creates a staging project shell, uploads a deterministic silent WAV fixture through the real GCS resumable flow, completes registration with checksum validation, and archives the project for cleanup.
* Completed: extended [staging-smoke.sh](#file-1306546793058167) with an optional provider-backed transcription path that starts real staging transcription on the uploaded fixture, polls `/v1/transcription/{transcript_id}` to terminal state, and captures project pipeline-operation artifacts on timeout, failure, and final success confirmation.
* Completed: extended [staging-smoke.sh](#file-1306546793058167) with an optional dub-only export retrieval path that generates a deterministic spoken MP4 fixture, uploads it into the same staging project, drives transcription plus project translation, runs `/v1/lipsync/render-project` with `enable_lipsync=false`, and downloads the signed dubbed output artifact.
* In progress: stabilize the staging suite so the provider-backed transcription and dub-only export retrieval subset can pass repeatedly within the configured timeout budget before any gating promotion.
* Next: run the expanded staging lane in GitHub Actions with CI-provisioned secrets and capture the first clean consecutive passes for promotion review.

## Workstream 4: performance and worker stress
**Status:** Not started

### Scope
* Add upload concurrency, long transcript, queue backlog, worker saturation, timeout, and memory-bound scenarios.
* Introduce p95 latency and throughput targets for critical API and async processing paths.

### Acceptance criteria
* Regressions in queueing, memory, timeout handling, and concurrency are measurable.
* Worker and API performance thresholds are documented and enforced.

## Workstream 5: security and accessibility
**Status:** Not started

### Scope
* Keep existing CodeQL, dependency review, and secret scanning.
* Add authorization and IDOR regressions, upload fuzzing, malformed payload tests, and container/image scanning.
* Add automated accessibility checks and keyboard-only coverage for core frontend flows.

### Acceptance criteria
* Security-sensitive resource boundaries are regression-tested.
* Core user journeys pass automated accessibility checks.

## Immediate execution sequence
1. Stabilize and finish backend router/runtime tests.
2. Add one assembled-app integration suite for critical API paths.
3. Wire a PR-blocking Firefox smoke lane while keeping WebKit in a slower lane first.
4. Define GCP staging resources, secrets, cost caps, and provider-by-provider checks.
5. Add security, accessibility, and performance waves after the above are green.

## Risks and controls
* Keep PR suites deterministic and cost-bounded; move flaky or provider-dependent checks out of the blocking path until stabilized.
* Prefer emulator or test-double coverage for broad integration, then reserve real-provider checks for concise staging smoke tests.
* Capture Playwright traces, backend logs, and async task diagnostics for every non-local failure path.
* Version test fixtures and expected API contracts so frontend and backend changes fail loudly when they drift.

## Tracking notes
* Treat this as release hygiene and quality hardening, not a rollout blocker.
* Update this plan as each workstream is started, expanded, or completed.

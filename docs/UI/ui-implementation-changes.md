# GlobeSync UI Implementation Changes

## Scope

This document records the UI implementation work completed against `docs/UI/ui-implementation-plan.md`, including backend support added where the UI required an existing authorized contract.

## Phase A: Entry and authentication

- Split the public landing experience from the authenticated workspace home.
- Added explicit auth-loading, signed-out, workspace-loading, empty, and populated states.
- Added user-facing error mapping for authentication, API, project-loading, and project-creation failures.
- Preserved Google Identity Services bootstrap, session restoration, sign-out, and backend-first project loading.
- Fixed the post-sign-in state notification so the page transitions into the authenticated workspace immediately.

## Phase B: Project browser

- Added a product-oriented workspace shell with clearer hierarchy and responsive navigation.
- Added project search, sorting, status filtering, project actions, empty states, and project creation entry points.
- Added responsive project-card presentation with status, language, duration, and update metadata.

## Phase C: Editor workflow

- Improved editor hydration, transcript and translation editing, timeline behavior, upload state, and processing interactions.
- Added responsive layouts, keyboard-accessible dialogs, RTL-aware fields, mixed-script handling, and segment-level quality/action surfaces.
- Preserved canonical project, draft, version, and media ownership boundaries.

## Phase D: Quality and recovery

- Added readiness checks, processing-stage visibility, failed-operation guidance, recovery actions, and export-history surfaces.
- Added version history and export-history dialogs with responsive behavior and Escape/backdrop dismissal.
- Kept retry and recovery actions tied to existing backend lifecycle behavior.

## Phase E: Processing and large files

- Added resumable uploads for files above 100 MB using the existing signed upload and completion endpoints.
- Added upload progress, processing-stage status, output history, preview/download actions, and retry context.
- Preserved checksum validation, media probing, upload expiry, workspace authorization, and the final `MediaFile` persistence boundary.
- Recorded browser QA for authenticated upload and export flows as deployment-dependent follow-up work.

## Phase F: Interaction polish

- Added shared button press feedback, focus treatment, busy states, and pressed-state semantics.
- Improved metadata hierarchy and project-card hover elevation.
- Standardized responsive and accessibility behavior across the touched surfaces.
- Added reduced-motion handling and shared visual tokens.

## Phase G: Global language readiness

- Added explicit document and field language metadata.
- Added RTL/LTR direction handling and mixed-script text wrapping behavior.
- Added native language labels where backend language metadata is available.
- Centralized locale-aware date and time formatting.
- Deferred full static-copy localization until approved translations, target locales, and a persistence strategy exist.

## Phase H: Workspace and enterprise readiness

### Implemented

- Workspace name and membership role are visible on desktop and mobile workspace surfaces.
- Added authorized `GET /v1/auth/workspaces` backed by existing memberships.
- Added workspace switching using the authenticated `X-Workspace-Id` context.
- Added authorized `GET /v1/auth/workspace-members` for the active workspace.
- Added read-only collaborator member-count metadata without exposing invite or permission mutation controls.
- Active workspace selection is stored locally only as request context; sign-out clears it.
- Workspace switching does not copy or mutate projects, drafts, versions, media, signed artifacts, or lifecycle state.

### Explicitly deferred

- Collaborator invite, removal, and role editing require approved mutation and permission contracts.
- Activity and change history require an `audit_logs` model, migration, ownership rules, retention policy, and API.
- Handoff and review states require approved lifecycle statuses, persistence, transitions, and API contracts.

## Backend and deployment changes

- Added workspace and member response schemas, service methods, and authenticated routes.
- Exposed the current pipeline operation pointer in project detail responses and avoided expected status requests when no operation exists.
- Updated Cloud Run deployment scripts for dynamic GCS CORS configuration, idempotent migration jobs, and safer OAuth environment handling.
- Removed `/healthz` from deployment smoke checks while retaining the backend endpoint.
- Preserved the base environment file for JSON-valued OAuth configuration to avoid malformed deployment arguments.

## Validation completed

- `pytest backend/tests/test_auth_api.py -q`: 4 passed.
- `pytest backend/tests/test_auth_api.py backend/tests/test_projects_api.py -q`: 17 passed before the additional route tests; the focused auth suite now reports 4 passed.
- Supported language matrix: 93 passed.
- Combined translation and transcription coverage: 112 passed.
- Frontend TypeScript diagnostics passed for touched files.
- `npm.cmd run build` passed.
- PowerShell deployment script parsing passed.
- `git diff --check` passed with only line-ending warnings.

## Remaining release validation

- Redeploy API and web services with the latest deployment script changes.
- Verify API revision readiness, `/health`, API CORS preflight, and raw/export bucket CORS.
- Complete authenticated browser QA for sign-in, session restore, workspace switching, editor dialogs, resumable upload, processing recovery, export preview/download, and RTL/mixed-script layouts.
- Keep full UI localization, detailed collaboration, activity history, and handoff/review work gated on the required product and backend contracts.

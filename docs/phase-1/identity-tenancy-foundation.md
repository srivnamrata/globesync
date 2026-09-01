# GlobeSync Phase 1 Identity and Tenancy Foundation

This document records the first ordered Phase 1 implementation step after the Phase 0 inventory and guardrail work.

## Objective

Introduce persistent tenant identity primitives in Cloud SQL before wiring authenticated session flows or enforcing project-level authorization.

## What was added

Following your GCP-first preference, this step already completed the Phase 1 table-creation foundation. The backend now has additive schema and model scaffolding for:

* `users`
* `workspaces`
* `workspace_members`

Implemented assets:

* [identity.py](#file-2724092822522420)
* [20260829_03_add_identity_tenancy_tables.py](#file-2724092822522421)
* [env.py](#file-3239543912548973)

## Table intent

### `users`

Stores application-level people identities resolved from Google-based authentication later in Phase 1.

Current columns:

* `id`
* `email`
* `display_name`
* `auth_provider`
* `auth_subject`
* `is_active`
* `last_login_at`
* `created_at`
* `updated_at`

Current constraints:

* primary key on `id`
* unique `email`
* unique `(auth_provider, auth_subject)`

### `workspaces`

Defines the tenant boundary for shared projects and future authorization.

Current columns:

* `id`
* `name`
* `slug`
* `owner_user_id`
* `is_personal`
* `archived_at`
* `created_at`
* `updated_at`

Current constraints:

* primary key on `id`
* unique `slug`
* foreign key `owner_user_id -> users.id`

### `workspace_members`

Represents role-bearing membership between users and workspaces.

Current columns:

* `id`
* `workspace_id`
* `user_id`
* `role`
* `invited_by_user_id`
* `joined_at`
* `created_at`
* `updated_at`

Current constraints:

* primary key on `id`
* unique `(workspace_id, user_id)`
* check constraint restricting `role` to `owner`, `editor`, or `viewer`
* foreign keys to `workspaces.id` and `users.id`

## Why this step comes first

This keeps Phase 1 in order:

1. create persistent identity and tenancy tables
2. bootstrap one default workspace per user
3. add authenticated session and actor resolution
4. move `/projects` from free-form scope parameters to authenticated workspace context
5. add nullable `workspace_id` columns to downstream pipeline tables and backfill what can be derived safely
6. migrate remaining route surfaces and make downstream workspace ownership non-null where validated

## What remains before tenancy is enforced

Not done yet:

* no new tables were required for the `/v1/projects` authenticated-context step; that change was route wiring only
* `/v1/projects` and the backend media pipeline routes are now authenticated and workspace-scoped
* downstream ownership completion is now expanded with additive lineage-based project and workspace backfill, but final legacy fallback removal still depends on post-migration validation
* focused backend authorization regression coverage now exists for the shared workspace-scope helper, but broader route-level integration coverage is still pending

## Next implementation target

The Phase 1 follow-on work described above is now complete enough to hand off to Phase 2.

Phase 2 should:

* make backend project state canonical through `projects` and `project_drafts`
* extend workspace membership role enforcement beyond `/v1/projects` into media pipeline routes
* continue validating the safe downstream ownership backfill until non-null enforcement and legacy fallback removal are justified
* broaden route-level authorization integration coverage now that shared helper regression tests exist

Status:

* Table creation for the Phase 1 identity and tenancy foundation was completed in this step through [identity.py](#file-2724092822522420) and [20260829_03_add_identity_tenancy_tables.py](#file-2724092822522421).
* The later auth bootstrap step was implemented in [auth-bootstrap-layer.md](#file-840101848495055).
* `/v1/projects` has now been moved onto authenticated request context in [projects.py](#file-3264843069231749), without adding new tables.
* The frontend now bootstraps authenticated context before backend-backed project operations through [authService.ts](#file-840101848495056), [apiClient.ts](#file-3239543912549051), [projectService.ts](#file-3239543912549052), [page.tsx](#file-3239543912549011), and [page.tsx](#file-3239543912549008).
* `/v1/projects` write operations now enforce workspace membership roles in [auth.py](#file-840101848495052) and [projects.py](#file-3264843069231749).
* The downstream ownership-backfill step has started with additive nullable `workspace_id` columns in [media.py](#file-3239543912548903), [transcript.py](#file-3239543912548904), [translation.py](#file-3239543912548905), [generated_audio.py](#file-3239543912548901), [lipsync_job.py](#file-3239543912548902), [export_job.py](#file-3239543912548899), and migration [20260830_04_add_workspace_scope_to_pipeline_tables.py](#file-840101848495057).
* Detailed Phase 2 scope and the started backend/frontend project foundation now live in [canonical-projects-and-media-authorization.md](#file-840101848495059), [project.py](#file-3264843069231746), [projects.py](#file-3264843069231747), [project_service.py](#file-3264843069231748), [20260830_05_add_projects_and_project_drafts.py](#file-3212615212764924), [projectService.ts](#file-3239543912549052), [page.tsx](#file-3239543912549011), and [page.tsx](#file-3239543912549008).
* Phase 2 has now also extended authenticated workspace role enforcement across project-linked media routes in [auth.py](#file-840101848495052), [upload.py](#file-3239543912548915), [transcription.py](#file-3239543912548912), [translation.py](#file-3239543912548913), [tts.py](#file-3239543912548914), [lipsync.py](#file-3239543912548911), and [export.py](#file-3239543912548909), while leaving a temporary legacy `user_id` fallback until ownership backfill is finished.
* Safe ownership cleanup has now advanced through [20260830_06_backfill_project_scope_on_pipeline_tables.py](#file-840101848495060), which backfills missing project, workspace, and uploader scope where canonical project or media lineage is available.
* Focused regression coverage for the shared authorization helper now lives in [test_workspace_auth.py](#file-840101848495061), validating workspace matches, project-root lookup, write-role denial, and the temporary legacy-row fallback behavior.

## Rollout note

This change remains additive at the platform level. The schema, auth bootstrap, frontend context wiring, `/projects` role enforcement, and first-pass downstream backfill prepare the system for Phase 2 without yet changing the existing Cloud Run deployment sequence.

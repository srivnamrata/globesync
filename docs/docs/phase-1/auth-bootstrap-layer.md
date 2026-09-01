# GlobeSync Phase 1 Auth Bootstrap Layer

Following your preferences, this document tracks the next ordered Phase 1 implementation step after the identity and tenancy tables were introduced.

## Objective

Bootstrap an authenticated application actor from Google-issued identity claims, persist that actor in Cloud SQL, and guarantee one default workspace exists before workspace-scoped APIs are tightened.

## Implemented assets

* [auth.py](#file-840101848495052)
* [auth_service.py](#file-840101848495051)
* [auth.py](#file-840101848495050)
* [auth.py](#file-840101848495053)
* [main.py](#file-3239543912548896)
* [config.py](#file-3239543912548894)
* [cloudrun.env.yaml](#file-3239543912548995)
* [.env.example](#file-3239543912548886)
* [test_auth_api.py](#file-840101848495054)
* [projects.py](#file-3264843069231749)
* [test_projects_api.py](#file-3791123751647523)
* [apiClient.ts](#file-3239543912549051)
* [projectService.ts](#file-3239543912549052)
* [authService.ts](#file-840101848495056)
* [page.tsx](#file-3239543912549011)
* [page.tsx](#file-3239543912549008)
* [Dockerfile](#file-3239543912549001)
* [deploy-cloudrun.sh](#file-3239543912548998)

## What the bootstrap layer now does

### Verified-identity ingestion

`backend/app/core/auth.py` now:

* reads a bearer token from the `Authorization` header
* verifies Google identity tokens through `google.oauth2.id_token`
* validates required claims such as `sub`, `email`, and `email_verified`
* supports an `X-Workspace-Id` override for future multi-workspace selection
* supports guarded local/dev bootstrap through `ALLOW_INSECURE_DEV_AUTH` plus debug headers

### Persistent actor bootstrap

`backend/app/services/auth_service.py` now:

* upserts a `users` row from verified identity claims
* refreshes profile fields and `last_login_at`
* creates one personal `workspace` for first-time users
* ensures an `owner` row exists in `workspace_members`
* resolves the active workspace and membership for the request context

### API surface

`backend/app/routers/auth.py` now exposes:

* `POST /v1/auth/bootstrap`
* `GET /v1/auth/me`

Both endpoints return the same bootstrapped actor context:

* `user`
* `workspace`
* `membership`
* `bootstrap_completed`

### Frontend bootstrap wiring

The frontend now attempts auth bootstrap before using backend-backed project persistence:

* `frontend/services/authService.ts` initializes bearer-token or guarded debug-header auth configuration
* `frontend/services/projectService.ts` requires a successful `POST /v1/auth/bootstrap` before calling `/v1/projects`
* `frontend/app/page.tsx` and `frontend/app/editor/[projectId]/page.tsx` attempt bootstrap before project list, create, load, and draft-save flows fall back to IndexedDB

This keeps the current editor usable while shifting backend project scope from public env parameters to authenticated context.

### Initial role enforcement

`backend/app/core/auth.py` and `backend/app/routers/projects.py` now enforce `owner` or `editor` membership for `/v1/projects` write operations, while read paths continue to resolve through the shared authenticated request context.

## Configuration added

Runtime configuration now includes:

* `AUTH_PROVIDER`
* `GOOGLE_OAUTH_CLIENT_IDS`
* `ALLOW_INSECURE_DEV_AUTH`

These are documented in [.env.example](#file-3239543912548886). The frontend also now accepts optional debug bootstrap inputs at build time via [Dockerfile](#file-3239543912549001) and [deploy-cloudrun.sh](#file-3239543912548998), while Cloud Run API runtime auth settings remain seeded in [cloudrun.env.yaml](#file-3239543912548995).

## Compatibility note

This bootstrap layer now drives `/v1/projects` through authenticated request context, and the frontend now calls `POST /v1/auth/bootstrap` before backend-backed project operations. Other media pipeline routes still use pre-tenancy patterns and remain to be migrated in later ordered steps.

## Validation status

Completed:

* Python syntax compilation passed for the new auth, config, router, migration, and test files.

Blocked in this workspace environment:

* `pytest` collection could not fully run because the current serverless environment lacks installed backend dependencies such as `sqlalchemy`.

## Next ordered step

With `/v1/projects` now moved onto `get_request_context`, the frontend bootstrap call wired in, and the first downstream `workspace_id` backfill started, the next implementation step moves into Phase 2: canonical backend project state, media-route authorization expansion, and completion of downstream workspace ownership migration.

See [canonical-projects-and-media-authorization.md](#file-840101848495059) for the Phase 2 scope.

## Remaining follow-on work

* replace the interim env/debug bootstrap path with a real Google sign-in UI session flow
* add membership/role checks to upload, transcript, translation, and render flows
* migrate remaining media routes off caller-supplied workspace and actor parameters
* continue the downstream backfill from nullable legacy ownership fields into nullable `workspace_id` columns before making ownership non-nullable

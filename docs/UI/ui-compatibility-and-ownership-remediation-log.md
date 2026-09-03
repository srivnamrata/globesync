# UI Compatibility and Canonical Ownership Remediation Log

## Purpose

Track the UI changes that affect backend contracts, persistence boundaries, signed artifact access, and lifecycle safety. This log is the implementation record for keeping Phases B, C, and D aligned with the repository's canonical ownership rules.

## Governing Principles

1. `projects` owns project identity, lifecycle, language pair, workspace scope, and pointers to canonical pipeline records.
2. `project_drafts` owns the latest mutable editor-session payload and optimistic-concurrency metadata.
3. `project_versions` owns immutable, bounded checkpoints for review and future restore workflows.
4. Normalized tables remain authoritative for media, transcript segments, translations, generated audio, lip-sync jobs, and export jobs.
5. IndexedDB is a cache/fallback layer, never the canonical source once backend project APIs are available.
6. Project list/detail responses expose canonical IDs and metadata, not expiring signed artifact URLs.
7. Signed media and output URLs are issued by dedicated artifact endpoints and are consumed close to playback time.
8. A language-pair change that invalidates downstream work is an explicit lifecycle operation, not an ordinary metadata PATCH.
9. Every read and write is workspace-scoped and uses the authenticated actor context.

## Current Remediation Status

| Area | Status | Required outcome |
| --- | --- | --- |
| Single-segment translation async compatibility | Implemented, tests pending expansion | Every formatter query eagerly loads generated audio |
| Project response signed URL compliance | Implemented, tests pending expansion | Remove signed media/output URLs from project summary/detail responses |
| Version-history migration | Implemented, migration pending deployment | Apply Alembic revision before backend code that writes snapshots |
| Version snapshot frequency and retention | Implemented, database retention tests pending | Snapshot meaningful checkpoints only, deduplicate, and retain a bounded history |
| Existing-project language swap | Safely blocked | Add explicit reset/clone workflow before allowing destructive changes |
| Project duplicate action contract | Implemented, tests passing | Provide a backend duplicate route that creates an independent draft shell |
| Original media playback after reload | Implemented through dedicated endpoint | Fetch playback URLs from the dedicated media endpoint |
| Waveform audio source | Implemented, endpoint test passing | Decode dedicated extracted MP3 audio rather than video containers |
| UI version-history panel | Implemented, metadata-only list/detail tests passing | Do not add restore until conflict-safe restore semantics are defined |

## Remediation Items

### R1. Fix single-segment translation loading

**Problem:** `_format_translation_item()` reads `trans.generated_audio`. The single-segment translation query must eager-load this relationship for async SQLAlchemy compatibility.

**Implementation:**

- Add `selectinload(Translation.generated_audio)` to the `translate-segment` lookup.
- Keep eager loading on the project translation-list query.
- Preserve `generated_audio_status` as an optional response field for old records and translations without audio.

**Done when:**

- `POST /translation/translate-segment` returns successfully when audio exists and when it does not.
- No lazy-load or `MissingGreenlet` error occurs.
- A focused route/service regression test covers both cases.

**Audit result:** Genuine and fixed in code. Both the project translation-list and single-segment translation queries now eager-load generated audio. A dedicated route regression test is still recommended.

### R2. Restore artifact URL ownership boundaries

**Problem:** Signed original-media URLs were added to project summary/detail responses. The project contract requires artifact URLs to remain on dedicated media/output endpoints.

**Implementation:**

- Remove `original_media_url` from project summary/detail schemas and service builders.
- Keep `media_file_id` on canonical project responses.
- Keep `media_url` only on `GET /media/{media_id}` and upload media responses.
- When the editor needs source playback, fetch media details by `media_file_id` through the dedicated media service method.
- Do not generate signed URLs while listing workspace projects.
- Treat signed URLs as short-lived runtime values, not project state.
- Apply the same rule to `last_rendered_video_url`; rendered output URLs are also artifacts and should be served by dedicated output/status endpoints rather than project metadata responses.

**Done when:**

- `GET /projects` and `GET /projects/{project_id}` contain no signed media URL.
- `GET /media/{media_id}` remains workspace-authorized and returns the playback URL.
- The editor can reopen a project and load source playback through the media endpoint.
- Project API tests assert the boundary.

**Audit result:** Genuine and fixed in code. Project summary/detail responses now expose canonical media/output identifiers and paths only; source playback is fetched through `/media/{media_id}`, and rendered output is fetched through `/lipsync/job/{job_id}`. Dedicated response-shape tests are still recommended.

### R3. Apply the project-version migration safely

**Problem:** Draft writes now create `ProjectVersion` rows. The database table must exist before that backend code is deployed.

**Implementation order:**

1. Run and verify `alembic upgrade head` in the migration environment.
2. Confirm `project_versions` exists with project, workspace, actor, version, payload, and timestamp constraints.
3. Deploy the backend.
4. Deploy the frontend that requests version history.
5. Verify draft save, conflict handling, and history listing after deployment.

**Audit result:** Genuine. The migration file exists locally, but deployment status is not verified in this workspace. Backend deployment must not precede the migration.

**Migration note:** Revision `20260903_09` creates the base table. Revision `20260903_10` adds payload hashing and checkpoint reasons with a backfill for existing rows. Revision `20260903_11` normalizes existing hashes to the runtime SHA-256 canonical JSON algorithm. Apply all three in order before deploying snapshot-writing code.

**Hash compatibility note:** The legacy backfill uses PostgreSQL MD5 text hashes, while new checkpoints use SHA-256 over canonical JSON. Checkpoint deduplication compares the normalized payload during the transition, and `20260903_11` permanently normalizes existing hashes once an online migration runs.

**Deployment verification:** `deploy-cloudrun.sh`, `deploy-cloudrun.ps1`, and `deploy-api-only.sh` build the API image, execute the `translation-migrate` Cloud Run Job with `alembic upgrade head` and wait for completion, then deploy the API. The PowerShell path now also fails closed when migration-job creation or execution returns a non-zero exit code. The ordering guard is present; live Cloud SQL execution remains unverified in this workspace.

**Rollback:**

- Roll back frontend use of the history endpoint first if needed.
- Do not downgrade the migration while snapshot-writing backend code is deployed.
- If a database rollback is required, deploy a backend version that no longer writes `ProjectVersion` before downgrading.

### R4. Bound and deduplicate version history

**Problem:** Snapshotting every autosave can produce unbounded full JSONB copies and make version history noisy.

**Target policy:**

- Autosave updates only the current `project_drafts` row.
- Create a version on explicit user Save.
- Create a version before a pipeline build when meaningful edits are present.
- Create a version after conflict recovery or a future restore operation.
- Hash the normalized draft payload and skip a snapshot when the payload is unchanged from the latest checkpoint.
- Retain a bounded history, initially the latest 50 versions per project.
- Record a reason such as `manual_save`, `pre_build`, `conflict_recovery`, or `restore`.

**Required model/API additions:**

- Add a payload hash column with an index or a deterministic comparison strategy.
- Add a checkpoint reason field.
- Add retention cleanup in the same transaction as checkpoint creation.
- Keep snapshot creation and current-draft update in one transaction.

**Done when:**

- Routine autosave does not create a new history row by itself.
- Identical consecutive payloads do not create duplicate checkpoints.
- A project cannot exceed the configured retention limit after cleanup.
- History listing is newest-first and workspace-scoped.

**Audit result:** Fixed in code. Autosave no longer requests a checkpoint; explicit Save and pre-build request checkpoints, and the backend hashes and prunes snapshots. Checkpoint contract tests and router tests pass; database-level retention cleanup and production verification remain.

### R5. Define safe language-pair changes

**Current behavior:** Untouched projects may swap language pair. Projects with media, transcript, translations, or output are blocked with an explanatory message.

**Required product rule:**

- Before downstream work exists: update source and target language normally.
- After downstream work exists: block by default and offer creation of a new project.
- Do not silently clear transcript, translation, audio, lip-sync, or export state.

**Future destructive reset contract:**

```text
POST /v1/projects/{project_id}/language-pair/reset
```

The operation must:

- Require authenticated workspace write access.
- Require an expected project/draft version.
- Reject active processing jobs unless the product explicitly supports cancellation.
- Require explicit confirmation from the client.
- Mark prior pipeline artifacts as superseded or otherwise preserve them; do not hard-delete them by default.
- Clear or replace canonical downstream pointers intentionally.
- Reset lifecycle status to `draft`.
- Update the draft payload and create an audit/version checkpoint atomically.

**Done when:**

- Reset behavior is represented by a dedicated API contract and tests.
- The normal PATCH endpoint cannot accidentally clear references through omitted fields.
- The UI explains what will be invalidated before confirmation.

**Audit result:** Partially implemented. The UI blocks the change after downstream work, but it does not offer a create-new-project action and no reset/clone endpoint exists.

**Update:** The UI now offers a safe new-project fallback through `createProjectShellWithDraft`, and the backend `/projects/{project_id}/duplicate` route now creates an independent draft shell without sharing downstream pointers. A destructive reset remains intentionally unavailable.

### R6. Keep version history read-only until restore is safe

**Current behavior:** The editor History panel lists version number and timestamp but does not restore snapshots.

**Restore prerequisites:**

- Define whether restore replaces only draft UI state or also updates normalized transcript/translation records.
- Require a current draft version or conflict check.
- Preserve dirty local edits until the user confirms replacement.
- Hydrate the selected snapshot fully before replacing visible editor state.
- Create a new checkpoint describing the restore.
- Test restore against concurrent edits and failed hydration.

**Audit result:** Correctly read-only for now. The list endpoint now returns metadata only, and full `draft_payload` values are available through a separate version-detail endpoint. Restore remains intentionally deferred.

### R7. Use a decodable audio source for waveform generation

**Problem:** The editor passes the rendered video URL to `AudioContext.decodeAudioData()`. Browser support for decoding audio from a video container is not reliable, so the waveform can fall back to the placeholder even when video playback works.

**Required outcome:** Use a dedicated audio asset or a backend-generated waveform/peak endpoint. Do not assume a playable video URL is a decodable audio buffer.

**Audit result:** Implemented in code. `GET /media/{media_id}/audio` extracts and caches a browser-compatible MP3 through the existing FFmpeg utilities; the editor fetches and decodes that URL.

**Done when:**

- Waveform generation succeeds for supported video and audio-only media types.
- CORS and signed-URL failures produce an intentional empty/error state.
- The extraction/cache-miss path and cached response are covered for both audio-only and video inputs; CORS and signed-URL failure behavior remains for live/browser validation.

### R8. Synchronize active segment with playback time

**Problem:** The editor previously updated `currentTimeSeconds` during playback but only changed the selected segment on click or seek. Active-row and timeline highlighting did not reliably follow playback as it advanced.

**Required outcome:** Derive the active segment from current playback time, preserve explicit selection when paused, and use the same derived segment for row highlighting, timeline range highlighting, and loop/comparison controls.

**Done when:**

- Playback crossing a segment boundary updates the active segment.
- Auto-scroll follows the active segment without requiring a click.
- Scrubbing and keyboard navigation use the same selection model.

**Audit result:** Fixed in code. Video `timeupdate` now selects the segment containing the current playhead time, reusing the existing highlight and auto-scroll behavior.

### R9. Keep project responses metadata-only

**Problem:** The project service and frontend still carry signed artifact URLs in the canonical `Project` object. This conflicts with the ownership principle even when the URL was obtained from a project response, and causes expiry-sensitive values to be stored as project state.

**Required outcome:** Store only `mediaId` and output identifiers in `Project`; fetch media/output details immediately before playback or download through dedicated services.

**Additional contract checks:**

- The frontend currently sends `workspace_id` and `actor_user_id` query parameters, while the backend resolves authorization from authenticated context. Remove redundant actor-scope query parameters once compatibility clients are migrated.
- The project list now applies an opaque `updated_at`/project-ID cursor with deterministic ordering. Frontend project URLs no longer send redundant `workspace_id` or `actor_user_id` query parameters; scope values remain in typed responses and bootstrap configuration while the auth migration is completed.

**Implementation update:** Canonical frontend `Project` state no longer contains original-media, rendered-video, or dubbed-audio URL fields. The editor stores source and rendered URLs only in component runtime state after calling the dedicated authorized media or lip-sync status endpoints. Draft writes sanitize legacy URL-shaped `videoFilename` values to a filename, so they cannot be written back to IndexedDB or backend drafts. Expired runtime URLs are refreshed through their dedicated endpoint; refresh failure clears only the runtime URL and leaves project, draft, and lifecycle state untouched.

### R10. Keep project action routes contract-complete

**Problem:** The UI called `/projects/{project_id}/duplicate`, but the backend did not previously define that route.

**Resolution:** Added an authenticated duplicate route and service method. It creates a new workspace-scoped project shell with the same language pair and no shared media, transcript, translation, lip-sync, or export pointers. This keeps the original project and its artifacts unchanged.

**Done when:**

- Duplicate action returns a new project ID.
- The new project starts in `draft` status.
- Downstream pointers are empty unless a future explicit copy policy is introduced.
- Viewer/write authorization and workspace scoping are tested.

### R11. Preserve Dub-only and Dub + Lip-Sync outputs independently

**Problem:** Each build correctly created a separate `lipsync_jobs` row, but both modes wrote their final file to the same storage key for a project and language. A later build could therefore replace the object referenced by an earlier job. The editor polling text also identified every in-progress job as “Dub & Lip-Sync”.

**Resolution:** A job now persists its `render_mode` (`dub_only` or `dub_and_lipsync`), and final artifacts use a job-owned storage key. The render-history endpoint is workspace- and project-scoped, generates signed URLs only at request time, and returns each finished job independently. The UI labels the active build correctly and exposes both modes as separate download entries under Project outputs.

**Lifecycle rule:** `projects.current_lipsync_job_id` remains only a pointer to the latest job and must not be treated as a complete render archive. `lipsync_jobs` is the render history; its artifact key is immutable once a job completes.

### R12. Enforce pipeline project ownership in the database

**Problem:** Earlier scope migrations backfilled `project_id` values but did not add foreign keys from pipeline records to `projects`. This left project ownership dependent on application code alone.

**Resolution:** The integrity migration validates every non-null project reference and its workspace before adding nullable `ON DELETE SET NULL` foreign keys for media, transcripts, translations, generated audio, lip-sync jobs, export jobs, and voice profiles. It fails without changing data if historical ownership is inconsistent, so remediation is explicit and auditable.

## Contract Matrix

| Concern | Canonical owner | API surface | UI behavior |
| --- | --- | --- | --- |
| Project identity/status/language | `projects` | `/projects` | Read/update through project service |
| Current editor draft | `project_drafts` | `/projects/{id}/draft` | Autosave with version conflict handling |
| Immutable checkpoints | `project_versions` | `/projects/{id}/versions` | Read-only history until restore is designed |
| Source media metadata/playback URL | `media_files` | `/media/{media_id}` | Fetch when playback is needed |
| Transcript segments | `transcripts`, `transcript_segments` | transcription routes | Hydrate editor cache from backend |
| Translations | `translations` | translation routes | Persist normalized edits, cache in draft during transition |
| Generated segment audio | `generated_audios` | TTS routes/translation metadata | Show readiness risk; do not infer from project output |
| Lip-sync segment state | `lipsync_jobs`, `frame_metadata` | lip-sync job status | Show failed segment risk from metadata |
| Rendered output | `lipsync_jobs` / `export_jobs` | dedicated output/status/history routes | Use short-lived output URLs for playback/download; preserve each job-owned artifact |

## Validation Checklist

### Backend compatibility

- [x] Compile changed backend modules.
- [x] Test single-segment translation with and without generated audio.
- [x] Test project list/detail response shape contains IDs but no signed media URLs.
- [x] Test media detail response returns an authorized playback URL.
- [x] Test cached media-audio endpoint response and signed URL generation.
- [ ] Test draft save creates or updates only the intended current draft and checkpoint behavior.
- [x] Test deterministic checkpoint hashing and optional/meaningful checkpoint reasons.
- [x] Test version listing is workspace-scoped and newest-first.
- [x] Test version listing is metadata-only and version detail returns the full payload.
- [ ] Test migration upgrade and downgrade in an isolated database.
- [ ] Test two builds of different modes create distinct `lipsync_jobs.render_mode` values and distinct output storage keys.
- [ ] Test `/lipsync/history` only returns jobs for the authenticated workspace and requested project.
- [ ] Run integrity migration `20260903_13` against a database snapshot and resolve any reported orphan or cross-workspace records before production rollout.
- [x] Test project responses exclude both original-media and rendered-output signed URLs.

**Migration verification:** Offline Alembic SQL generation completed successfully through revisions `20260903_09` and `20260903_10`. Live upgrade/downgrade verification remains blocked because the local Docker PostgreSQL engine is unavailable and no configured database URL is available in this workspace.

**Fresh development databases:** Do not replay the historical migration chain from an empty database because revision `20260821_01` imports mutable ORM metadata. After recreating a disposable database, run `python scripts/bootstrap_fresh_database.py` from `backend`; it creates the current schema and stamps the database at Alembic head. Existing databases must continue to use the forward migration path and the integrity checks in revisions `20260903_12` and `20260903_13`.

**Scope-parameter cleanup:** Frontend project URLs no longer serialize `workspace_id` or `actor_user_id`. Workspace selection remains owned by authenticated backend context, with the existing `X-Workspace-Id` override handled server-side. The frontend scope bootstrap guard remains temporarily for compatibility with the current auth bootstrap flow.
- [x] Test project list cursor behavior with deterministic ordering and malformed-token rejection.
- [x] Test duplicate-project route authorization scope and independent shell response.

### Frontend compatibility

- [x] Run `npx tsc --noEmit`.
- [ ] Reopen a project and verify source playback URL is fetched through the media service.
- [ ] Verify status filters, project actions, language swap, loop, scrubbing, risk badges, comparison controls, and history panel.
- [ ] Verify controls are disabled or explanatory when required URLs/data are unavailable.
- [ ] Verify dirty/conflicted translations are not replaced before remote draft hydration completes.
- [ ] Verify waveform generation with audio-only and video media.
- [ ] Verify active segment follows playback boundaries and auto-scrolls accordingly.

### Deployment order

1. Apply database migration.
2. Deploy backend API and verify routes/contracts.
3. Deploy frontend.
4. Run smoke tests for project load, draft save, media playback, translation, TTS, lip-sync, and history listing.
5. Monitor API errors and signed-URL failures before enabling destructive reset or restore.

## Decision Log

- **2026-09-03:** Keep project-list cards metadata-only. Do not add presigned thumbnail, media, or output URLs to project summaries; use intentional non-artifact placeholders until a dedicated authorized thumbnail endpoint is designed.
- **2026-09-03:** Keep existing-project language swaps blocked after downstream work until an explicit reset/clone contract exists.
- **2026-09-03:** Keep version history read-only until restore can preserve dirty and conflicted editor state.
- **2026-09-03:** Treat project metadata and artifact playback URLs as separate ownership domains.
- **2026-09-03:** Restore source and rendered preview URLs through dedicated media/job endpoints rather than project metadata responses.
- **2026-09-03:** Treat generated-audio readiness as backend metadata, not as an inference from the final dubbed output.
- **2026-09-03:** Treat each Dub-only or Dub + Lip-Sync job as an independently retained output; never reuse an output storage key across render jobs.

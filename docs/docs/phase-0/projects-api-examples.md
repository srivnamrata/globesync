# GlobeSync Phase 0 `/projects` API Examples

This document provides concrete request and response examples for the first backend-owned `projects` API surface described in [GCP_MULTI_TENANT_MIGRATION_PLAN.md](#file-2060193141886677) and aligned with [draft-field-mapping.md](#file-2060193141886681).

## Purpose

* Give backend and frontend a shared payload contract for the first `/projects` implementation
* Keep canonical project metadata in top-level API fields
* Keep editor-session compatibility data in the draft payload
* Make optimistic concurrency behavior explicit before multi-device cutover

## Conventions used in these examples

* Top-level project API fields use `snake_case`
* The nested `draft_payload` intentionally stays close to the current frontend `HeygenXFile` shape and uses its existing `camelCase` field names
* All responses are scoped to the authenticated user's active `workspace_id`
* `projects` remains a small identity-and-pointers record; transcript segments and translations remain authoritative in their own tables
* Timestamps use ISO 8601 UTC strings

## Example IDs used below

* `workspace_id`: `4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5`
* `project_id`: `6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31`
* `media_file_id`: `7db6c44c-d1ab-4f77-a0ab-f4af5d471a90`
* `transcript_id`: `40f0b93d-ea1a-43ec-83d9-56064d9b8698`
* `lipsync_job_id`: `5d76f2f8-95d0-4f70-b0cf-4f8fb07b4dc0`
* `user_id`: `1c8d8f92-62d1-4619-98d0-45bd63a48617`

## 1. `GET /v1/projects`

Lists projects visible in the current workspace, ordered by recent update time.

### Example request

```http
GET /v1/projects?status=draft&limit=2 HTTP/1.1
Authorization: Bearer <token>
X-Workspace-Id: 4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5
```

### Example response

```json
{
  "items": [
    {
      "id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
      "workspace_id": "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5",
      "owner_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
      "name": "Hindi Product Launch",
      "status": "draft",
      "source_language": "en",
      "target_language": "hi",
      "active_translation_language": "hi",
      "media_file_id": "7db6c44c-d1ab-4f77-a0ab-f4af5d471a90",
      "transcript_id": "40f0b93d-ea1a-43ec-83d9-56064d9b8698",
      "latest_draft_version": 7,
      "last_rendered_video_gcs_path": "gs://project-794c406e-c0ab-4a50-8e9-media/_ops/renders/6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31/output.mp4",
      "created_at": "2026-08-29T07:15:12Z",
      "updated_at": "2026-08-29T09:42:10Z"
    },
    {
      "id": "244ef8fe-49a3-41c3-9866-f8dd270f53a7",
      "workspace_id": "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5",
      "owner_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
      "name": "Spanish Demo Cut",
      "status": "draft",
      "source_language": "en",
      "target_language": "es",
      "active_translation_language": "es",
      "media_file_id": null,
      "transcript_id": null,
      "latest_draft_version": 1,
      "last_rendered_video_gcs_path": null,
      "created_at": "2026-08-28T13:11:03Z",
      "updated_at": "2026-08-28T13:11:03Z"
    }
  ],
  "next_cursor": null
}
```

## 2. `POST /v1/projects`

Creates the canonical project shell before upload, transcription, or translation work begins.

### Example request

```http
POST /v1/projects HTTP/1.1
Authorization: Bearer <token>
X-Workspace-Id: 4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5
Content-Type: application/json
```

```json
{
  "name": "Hindi Product Launch",
  "source_language": "en",
  "target_language": "hi"
}
```

### Example response

```json
{
  "id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
  "workspace_id": "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5",
  "owner_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
  "created_by_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
  "name": "Hindi Product Launch",
  "slug": null,
  "status": "draft",
  "source_language": "en",
  "target_language": "hi",
  "active_translation_language": null,
  "media_file_id": null,
  "transcript_id": null,
  "current_lipsync_job_id": null,
  "current_export_job_id": null,
  "last_rendered_video_gcs_path": null,
  "latest_draft_version": 0,
  "created_at": "2026-08-29T07:15:12Z",
  "updated_at": "2026-08-29T07:15:12Z"
}
```

## 3. `GET /v1/projects/{project_id}`

Returns canonical project metadata and pointers to pipeline-owned records.

### Example request

```http
GET /v1/projects/6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31 HTTP/1.1
Authorization: Bearer <token>
X-Workspace-Id: 4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5
```

### Example response

```json
{
  "id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
  "workspace_id": "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5",
  "owner_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
  "created_by_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
  "name": "Hindi Product Launch",
  "slug": null,
  "status": "processing",
  "source_language": "en",
  "target_language": "hi",
  "active_translation_language": "hi",
  "media_file_id": "7db6c44c-d1ab-4f77-a0ab-f4af5d471a90",
  "transcript_id": "40f0b93d-ea1a-43ec-83d9-56064d9b8698",
  "current_lipsync_job_id": "5d76f2f8-95d0-4f70-b0cf-4f8fb07b4dc0",
  "current_export_job_id": null,
  "last_rendered_video_gcs_path": null,
  "latest_draft_version": 7,
  "created_at": "2026-08-29T07:15:12Z",
  "updated_at": "2026-08-29T09:42:10Z"
}
```

## 4. `PATCH /v1/projects/{project_id}`

Updates mutable project metadata without writing the full editor draft.

### Example request

```http
PATCH /v1/projects/6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31 HTTP/1.1
Authorization: Bearer <token>
X-Workspace-Id: 4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5
Content-Type: application/json
```

```json
{
  "name": "Hindi Product Launch v2",
  "target_language": "hi",
  "active_translation_language": "hi",
  "status": "processing"
}
```

### Example response

```json
{
  "id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
  "workspace_id": "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5",
  "owner_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
  "created_by_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
  "name": "Hindi Product Launch v2",
  "slug": null,
  "status": "processing",
  "source_language": "en",
  "target_language": "hi",
  "active_translation_language": "hi",
  "media_file_id": "7db6c44c-d1ab-4f77-a0ab-f4af5d471a90",
  "transcript_id": "40f0b93d-ea1a-43ec-83d9-56064d9b8698",
  "current_lipsync_job_id": "5d76f2f8-95d0-4f70-b0cf-4f8fb07b4dc0",
  "current_export_job_id": null,
  "last_rendered_video_gcs_path": null,
  "latest_draft_version": 7,
  "created_at": "2026-08-29T07:15:12Z",
  "updated_at": "2026-08-29T09:48:55Z"
}
```

## 5. `GET /v1/projects/{project_id}/draft`

Returns the server-side editor draft plus concurrency metadata.

### Example request

```http
GET /v1/projects/6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31/draft HTTP/1.1
Authorization: Bearer <token>
X-Workspace-Id: 4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5
```

### Example response

```json
{
  "project_id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
  "workspace_id": "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5",
  "version": 7,
  "draft_schema_version": "heygenx/v1",
  "base_project_updated_at": "2026-08-29T09:42:10Z",
  "last_saved_by_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
  "created_at": "2026-08-29T07:16:08Z",
  "updated_at": "2026-08-29T09:42:32Z",
  "draft_payload": {
    "version": "heygenx/v1",
    "projectMetadata": {
      "id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
      "name": "Hindi Product Launch v2",
      "sourceLanguage": "en",
      "targetLanguage": "hi",
      "createdAt": "2026-08-29T07:15:12Z",
      "updatedAt": "2026-08-29T09:42:32Z"
    },
    "mediaReferences": {
      "videoFilename": "product_launch_master.mp4",
      "durationSeconds": 94.2,
      "transcriptId": "40f0b93d-ea1a-43ec-83d9-56064d9b8698",
      "mediaId": "7db6c44c-d1ab-4f77-a0ab-f4af5d471a90",
      "originalTranscriptSegments": [
        {
          "id": "seg_001",
          "sequenceOrder": 1,
          "startTimeSeconds": 0.0,
          "endTimeSeconds": 4.8,
          "durationSeconds": 4.8,
          "speakerTag": "speaker_1",
          "text": "Welcome to GlobeSync.",
          "confidence": 0.98
        }
      ]
    },
    "translations": [
      {
        "id": "txn_001",
        "transcriptSegmentId": "seg_001",
        "translatedText": "ग्लोबसिंक में आपका स्वागत है।",
        "originalDurationMs": 4800,
        "estimatedDurationMs": 4950,
        "durationRatio": 1.03,
        "speedAdjustmentFactor": 0.97,
        "qualityScore": 0.96,
        "status": "completed"
      }
    ],
    "timelineState": {
      "markers": [
        {
          "id": "marker_1",
          "label": "Intro",
          "timeSeconds": 0.0
        }
      ],
      "zoomLevel": 1.5
    },
    "uiState": {
      "selectedSegmentId": "seg_001",
      "activeSpeakerFilters": [
        "speaker_1"
      ],
      "leftPanelOpen": true,
      "renderPreferences": {
        "subtitlesEnabled": false
      }
    }
  }
}
```

## 6. `PUT /v1/projects/{project_id}/draft`

Replaces the latest draft using optimistic concurrency.

### Example request

```http
PUT /v1/projects/6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31/draft HTTP/1.1
Authorization: Bearer <token>
X-Workspace-Id: 4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5
Content-Type: application/json
```

```json
{
  "version": 7,
  "draft_schema_version": "heygenx/v1",
  "base_project_updated_at": "2026-08-29T09:42:10Z",
  "draft_payload": {
    "version": "heygenx/v1",
    "projectMetadata": {
      "id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
      "name": "Hindi Product Launch v2",
      "sourceLanguage": "en",
      "targetLanguage": "hi",
      "createdAt": "2026-08-29T07:15:12Z",
      "updatedAt": "2026-08-29T09:49:30Z"
    },
    "mediaReferences": {
      "videoFilename": "product_launch_master.mp4",
      "durationSeconds": 94.2,
      "transcriptId": "40f0b93d-ea1a-43ec-83d9-56064d9b8698",
      "mediaId": "7db6c44c-d1ab-4f77-a0ab-f4af5d471a90"
    },
    "translations": [
      {
        "id": "txn_001",
        "transcriptSegmentId": "seg_001",
        "translatedText": "ग्लोबसिंक में आपका हार्दिक स्वागत है।",
        "originalDurationMs": 4800,
        "estimatedDurationMs": 5100,
        "durationRatio": 1.06,
        "speedAdjustmentFactor": 0.94,
        "qualityScore": 0.97,
        "status": "completed"
      }
    ],
    "timelineState": {
      "markers": [
        {
          "id": "marker_1",
          "label": "Intro",
          "timeSeconds": 0.0
        }
      ],
      "zoomLevel": 1.75
    },
    "uiState": {
      "selectedSegmentId": "seg_001",
      "activeSpeakerFilters": [
        "speaker_1"
      ],
      "leftPanelOpen": true,
      "renderPreferences": {
        "subtitlesEnabled": false
      }
    }
  }
}
```

### Example success response

```json
{
  "project_id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
  "workspace_id": "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5",
  "version": 8,
  "draft_schema_version": "heygenx/v1",
  "base_project_updated_at": "2026-08-29T09:48:55Z",
  "last_saved_by_user_id": "1c8d8f92-62d1-4619-98d0-45bd63a48617",
  "updated_at": "2026-08-29T09:49:31Z"
}
```

## 7. `PUT /v1/projects/{project_id}/draft` conflict example

If the client submits a stale version, the server should reject the write instead of silently overwriting newer work.

### Example conflict response

```http
HTTP/1.1 409 Conflict
Content-Type: application/json
```

```json
{
  "error": {
    "code": "DRAFT_VERSION_CONFLICT",
    "message": "The draft has been updated by another session. Refresh before saving again.",
    "project_id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
    "client_version": 7,
    "server_version": 8,
    "server_updated_at": "2026-08-29T09:49:31Z",
    "last_saved_by_user_id": "8aa64d12-5ce6-4960-a1fe-2f362727acfe"
  }
}
```

## 8. `POST /v1/projects/{project_id}/archive`

Soft-archives a project without deleting normalized outputs.

### Example request

```http
POST /v1/projects/6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31/archive HTTP/1.1
Authorization: Bearer <token>
X-Workspace-Id: 4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5
```

### Example response

```json
{
  "id": "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31",
  "workspace_id": "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5",
  "status": "archived",
  "archived_at": "2026-08-29T10:02:14Z",
  "updated_at": "2026-08-29T10:02:14Z"
}
```

## Recommended validation points for implementation

When these endpoints are built, validate the following against [validation-checklist.md](#file-2060193141886684):

* `GET /v1/projects` excludes archived projects by default unless explicitly requested
* `POST /v1/projects` creates a shell without requiring transcript or media state
* `GET /v1/projects/{project_id}` returns canonical pointers, not inline transcript/translation arrays
* `GET /v1/projects/{project_id}/draft` returns a payload the current editor can hydrate without reshaping every field
* `PUT /v1/projects/{project_id}/draft` increments the version on every successful save
* stale-version writes return `409 Conflict`
* `POST /v1/projects/{project_id}/archive` does not delete linked transcript, translation, audio, or render rows

## Open design decisions still to confirm

* Whether IDs should be exposed as raw UUID strings like the examples above or wrapped in prefixed public identifiers instead
* Whether `GET /v1/projects` should include archived rows via a query flag or use a separate archive view
* Whether `PATCH /v1/projects/{project_id}` should allow updating `active_translation_language` independently from `target_language`
* Whether `draft_payload.version` should remain a schema label string, an integer, or both
* Whether the API should return a signed preview URL in `GET /v1/projects/{project_id}` or keep all artifact URLs on dedicated pipeline endpoints

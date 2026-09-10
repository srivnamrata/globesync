#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROJECT_ID="${PROJECT_ID:-project-794c406e-c0ab-4a50-8e9}"
REGION="${REGION:-asia-south1}"
API_SERVICE="${API_SERVICE:-translation-api}"
WEB_SERVICE="${WEB_SERVICE:-translation-web}"
CLOUD_TASKS_QUEUE="${CLOUD_TASKS_QUEUE:-translation-jobs}"
RAW_BUCKET="${RAW_BUCKET:-${PROJECT_ID}-media-raw}"
EXPORTS_BUCKET="${EXPORTS_BUCKET:-${PROJECT_ID}-media-exports}"
RUNTIME_SA="${RUNTIME_SA:-globesync@${PROJECT_ID}.iam.gserviceaccount.com}"
GOOGLE_WEB_CLIENT_ID="${GOOGLE_WEB_CLIENT_ID:-164115731533-dmkk078mkekffs11fpj1783no0fm8bsg.apps.googleusercontent.com}"
STAGING_AUTH_BEARER_TOKEN="${STAGING_AUTH_BEARER_TOKEN:-}"
STAGING_WORKSPACE_ID="${STAGING_WORKSPACE_ID:-}"
ENABLE_INTERNAL_TASK_AUTH_CHECK="${ENABLE_INTERNAL_TASK_AUTH_CHECK:-false}"
ENABLE_UPLOAD_INITIATION_CHECK="${ENABLE_UPLOAD_INITIATION_CHECK:-false}"
ENABLE_FIXTURE_UPLOAD_CHECK="${ENABLE_FIXTURE_UPLOAD_CHECK:-false}"
ENABLE_PROVIDER_EXECUTION_CHECK="${ENABLE_PROVIDER_EXECUTION_CHECK:-false}"
ENABLE_DUB_EXPORT_RETRIEVAL_CHECK="${ENABLE_DUB_EXPORT_RETRIEVAL_CHECK:-false}"
STAGING_UPLOAD_FILENAME="${STAGING_UPLOAD_FILENAME:-staging-smoke-sample.mp4}"
STAGING_UPLOAD_MIME_TYPE="${STAGING_UPLOAD_MIME_TYPE:-video/mp4}"
STAGING_UPLOAD_FILESIZE_BYTES="${STAGING_UPLOAD_FILESIZE_BYTES:-1048576}"
STAGING_UPLOAD_ORIGIN="${STAGING_UPLOAD_ORIGIN:-}"
STAGING_FIXTURE_FILENAME="${STAGING_FIXTURE_FILENAME:-staging-smoke-silence.wav}"
STAGING_FIXTURE_MIME_TYPE="${STAGING_FIXTURE_MIME_TYPE:-audio/wav}"
STAGING_DUB_FIXTURE_FILENAME="${STAGING_DUB_FIXTURE_FILENAME:-staging-smoke-spoken.mp4}"
STAGING_DUB_FIXTURE_MIME_TYPE="${STAGING_DUB_FIXTURE_MIME_TYPE:-video/mp4}"
STAGING_FIXTURE_PROJECT_NAME="${STAGING_FIXTURE_PROJECT_NAME:-Staging smoke fixture upload}"
STAGING_FIXTURE_SOURCE_LANGUAGE="${STAGING_FIXTURE_SOURCE_LANGUAGE:-en}"
STAGING_FIXTURE_TARGET_LANGUAGE="${STAGING_FIXTURE_TARGET_LANGUAGE:-es}"
STAGING_TRANSCRIPTION_LANGUAGE="${STAGING_TRANSCRIPTION_LANGUAGE:-en}"
STAGING_PROVIDER_EXECUTION_TIMEOUT_SECONDS="${STAGING_PROVIDER_EXECUTION_TIMEOUT_SECONDS:-180}"
STAGING_PROVIDER_POLL_INTERVAL_SECONDS="${STAGING_PROVIDER_POLL_INTERVAL_SECONDS:-5}"
STAGING_DUB_EXPORT_TIMEOUT_SECONDS="${STAGING_DUB_EXPORT_TIMEOUT_SECONDS:-300}"
STAGING_DUB_EXPORT_POLL_INTERVAL_SECONDS="${STAGING_DUB_EXPORT_POLL_INTERVAL_SECONDS:-5}"
STAGING_TTS_FIXTURE_TEXT="${STAGING_TTS_FIXTURE_TEXT:-GlobeSync staging smoke validates dubbed export retrieval.}"
STAGING_TTS_FIXTURE_LANGUAGE_CODE="${STAGING_TTS_FIXTURE_LANGUAGE_CODE:-en-US}"
INTERNAL_TASK_AUDIENCE="${INTERNAL_TASK_AUDIENCE:-}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-$ROOT_DIR/.artifacts/staging-smoke}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
ARTIFACT_DIR="${ARTIFACT_DIR:-$ARTIFACT_ROOT/$RUN_ID}"
API_URL="${API_URL:-}"
WEB_URL="${WEB_URL:-}"

mkdir -p "$ARTIFACT_DIR"

log() {
  printf '\n==> %s\n' "$1"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: required command '$1' is not installed or not on PATH" >&2
    exit 1
  }
}

assert_file_contains() {
  local file="$1"
  local expected="$2"
  if ! grep -Fq "$expected" "$file"; then
    echo "ERROR: expected '$expected' in $file" >&2
    exit 1
  fi
}

assert_nonempty_file() {
  local file="$1"
  if [[ ! -s "$file" ]]; then
    echo "ERROR: expected non-empty file at $file" >&2
    exit 1
  fi
}

json_field() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
value = payload
for segment in sys.argv[2].split('.'):
    value = value[segment]
if value is None:
    sys.exit(1)
print(value)
PY
}

create_silent_wav_fixture() {
  local target_path="$1"
  python3 - "$target_path" <<'PY'
import struct
import sys
import wave

sample_rate = 8000
sample_count = 8000
with wave.open(sys.argv[1], 'wb') as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    wav_file.writeframes(b''.join(struct.pack('<h', 0) for _ in range(sample_count)))
PY
}

create_spoken_mp4_fixture() {
  local target_path="$1"
  local audio_path="$2"
  local request_path="$ARTIFACT_DIR/spoken-fixture-tts.request.json"
  local response_path="$ARTIFACT_DIR/spoken-fixture-tts.body"
  local headers_path="$ARTIFACT_DIR/spoken-fixture-tts.headers"
  local access_token=""

  require_cmd ffmpeg
  access_token="$(gcloud auth print-access-token)"

  python3 - "$request_path" "$STAGING_TTS_FIXTURE_TEXT" "$STAGING_TTS_FIXTURE_LANGUAGE_CODE" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "input": {"text": sys.argv[2]},
            "voice": {"languageCode": sys.argv[3]},
            "audioConfig": {"audioEncoding": "LINEAR16", "speakingRate": 1.0},
        }
    )
)
PY

  curl -fsSL \
    -X POST \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -D "$headers_path" \
    "https://texttospeech.googleapis.com/v1/text:synthesize" \
    --data-binary @"$request_path" > "$response_path"

  python3 - "$response_path" "$audio_path" <<'PY'
import base64
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
Path(sys.argv[2]).write_bytes(base64.b64decode(payload["audioContent"]))
PY

  ffmpeg -y \
    -f lavfi \
    -i color=c=black:s=640x360:r=24:d=8 \
    -i "$audio_path" \
    -shortest \
    -c:v libx264 \
    -pix_fmt yuv420p \
    -movflags +faststart \
    -c:a aac \
    -b:a 96k \
    "$target_path" > "$ARTIFACT_DIR/spoken-fixture-ffmpeg.log" 2>&1
}

CURRENT_PROJECT_ID=""

archive_fixture_project() {
  if [[ -z "${CURRENT_PROJECT_ID:-}" || -z "$STAGING_AUTH_BEARER_TOKEN" ]]; then
    return 0
  fi

  log "Archiving fixture project"
  cleanup_headers=(
    -H "Authorization: Bearer $STAGING_AUTH_BEARER_TOKEN"
    -H "Content-Type: application/json"
  )
  if [[ -n "$STAGING_WORKSPACE_ID" ]]; then
    cleanup_headers+=( -H "X-Workspace-Id: $STAGING_WORKSPACE_ID" )
  fi

  if ! curl -sS \
    -X POST \
    "${cleanup_headers[@]}" \
    -D "$ARTIFACT_DIR/fixture-project-archive.headers" \
    "$API_URL/v1/projects/$CURRENT_PROJECT_ID/archive" \
    -d '{}' > "$ARTIFACT_DIR/fixture-project-archive.body"; then
    echo "WARNING: failed to archive fixture project $CURRENT_PROJECT_ID" | tee -a "$ARTIFACT_DIR/cleanup-warnings.txt"
  fi

  CURRENT_PROJECT_ID=""
  return 0
}

trap archive_fixture_project EXIT

require_cmd gcloud
require_cmd curl
require_cmd grep
require_cmd mktemp
require_cmd python3

log "Selecting GCP project"
gcloud config set project "$PROJECT_ID" >/dev/null

if [[ -z "$API_URL" ]]; then
  API_URL="$(gcloud run services describe "$API_SERVICE" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
fi
if [[ -z "$WEB_URL" ]]; then
  WEB_URL="$(gcloud run services describe "$WEB_SERVICE" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
fi

if [[ -z "$API_URL" || -z "$WEB_URL" ]]; then
  echo "ERROR: could not resolve deployed service URLs" >&2
  exit 1
fi

if [[ -z "$STAGING_UPLOAD_ORIGIN" ]]; then
  STAGING_UPLOAD_ORIGIN="$WEB_URL"
fi
if [[ -z "$INTERNAL_TASK_AUDIENCE" ]]; then
  INTERNAL_TASK_AUDIENCE="$API_URL"
fi

printf 'run_id=%s\nproject_id=%s\nregion=%s\napi_url=%s\nweb_url=%s\n' \
  "$RUN_ID" "$PROJECT_ID" "$REGION" "$API_URL" "$WEB_URL" \
  | tee "$ARTIFACT_DIR/run-metadata.txt"

log "Capturing deployed service definitions"
gcloud run services describe "$API_SERVICE" --project="$PROJECT_ID" --region="$REGION" --format=json > "$ARTIFACT_DIR/api-service.json"
gcloud run services describe "$WEB_SERVICE" --project="$PROJECT_ID" --region="$REGION" --format=json > "$ARTIFACT_DIR/web-service.json"

log "Checking required secrets"
for secret in translation-database-url translation-sync-database-url translation-jwt-secret; do
  gcloud secrets describe "$secret" --project="$PROJECT_ID" > /dev/null
  echo "$secret" >> "$ARTIFACT_DIR/required-secrets.txt"
done
for optional_secret in webhook-secret replicate-api-token; do
  if gcloud secrets describe "$optional_secret" --project="$PROJECT_ID" > /dev/null 2>&1; then
    echo "$optional_secret=present" >> "$ARTIFACT_DIR/optional-secrets.txt"
  else
    echo "$optional_secret=missing" | tee -a "$ARTIFACT_DIR/optional-secrets.txt"
  fi
done

log "Checking staging infrastructure"
gcloud tasks queues describe "$CLOUD_TASKS_QUEUE" --location="$REGION" --project="$PROJECT_ID" > "$ARTIFACT_DIR/cloud-tasks-queue.txt"
gcloud storage buckets describe "gs://$RAW_BUCKET" --project="$PROJECT_ID" > "$ARTIFACT_DIR/raw-bucket.txt"
gcloud storage buckets describe "gs://$EXPORTS_BUCKET" --project="$PROJECT_ID" > "$ARTIFACT_DIR/exports-bucket.txt"

log "Checking deployed runtime wiring"
assert_file_contains "$ARTIFACT_DIR/api-service.json" "$API_URL"
assert_file_contains "$ARTIFACT_DIR/api-service.json" "$RUNTIME_SA"
assert_file_contains "$ARTIFACT_DIR/api-service.json" "$CLOUD_TASKS_QUEUE"
assert_file_contains "$ARTIFACT_DIR/api-service.json" "$GOOGLE_WEB_CLIENT_ID"

log "Checking API reachability"
curl -fsSL -D "$ARTIFACT_DIR/api-health.headers" "$API_URL/health" > "$ARTIFACT_DIR/api-health.body"
curl -fsSL -D "$ARTIFACT_DIR/api-healthz.headers" "$API_URL/healthz" > "$ARTIFACT_DIR/api-healthz.body"
assert_file_contains "$ARTIFACT_DIR/api-health.body" "healthy"
assert_file_contains "$ARTIFACT_DIR/api-healthz.body" "ready"

log "Checking web reachability"
curl -fsSL -D "$ARTIFACT_DIR/web.headers" "$WEB_URL" > "$ARTIFACT_DIR/web.html"
assert_file_contains "$ARTIFACT_DIR/web.html" "<html"

if [[ -n "$STAGING_AUTH_BEARER_TOKEN" ]]; then
  log "Checking authenticated bootstrap"
  auth_headers=(
    -H "Authorization: Bearer $STAGING_AUTH_BEARER_TOKEN"
    -H "Content-Type: application/json"
  )
  if [[ -n "$STAGING_WORKSPACE_ID" ]]; then
    auth_headers+=( -H "X-Workspace-Id: $STAGING_WORKSPACE_ID" )
  fi
  curl -fsSL \
    -X POST \
    "${auth_headers[@]}" \
    -D "$ARTIFACT_DIR/auth-bootstrap.headers" \
    "$API_URL/v1/auth/bootstrap" \
    -d '{}' > "$ARTIFACT_DIR/auth-bootstrap.body"
  assert_file_contains "$ARTIFACT_DIR/auth-bootstrap.body" '"workspace"'
  assert_file_contains "$ARTIFACT_DIR/auth-bootstrap.body" '"membership"'
else
  log "Skipping authenticated bootstrap"
  echo "STAGING_AUTH_BEARER_TOKEN not set; authenticated bootstrap check skipped." | tee "$ARTIFACT_DIR/auth-bootstrap.skip.txt"
fi

if [[ "$ENABLE_INTERNAL_TASK_AUTH_CHECK" == "true" ]]; then
  log "Checking internal task auth and route reachability"
  internal_task_audience="${INTERNAL_TASK_AUDIENCE:-$API_URL}"
  internal_task_token="$(gcloud auth print-identity-token --impersonate-service-account="$RUNTIME_SA" --audiences="$internal_task_audience")"
  curl -sS \
    -X POST \
    -H "Authorization: Bearer $internal_task_token" \
    -H "Content-Type: application/json" \
    -H "X-CloudTasks-TaskName: staging-smoke-auth-check" \
    -D "$ARTIFACT_DIR/internal-task-auth.headers" \
    "$API_URL/v1/internal/tasks/transcribe" \
    -d '{}' > "$ARTIFACT_DIR/internal-task-auth.body"
  assert_file_contains "$ARTIFACT_DIR/internal-task-auth.body" '"detail"'
  assert_file_contains "$ARTIFACT_DIR/internal-task-auth.body" '"Field required"'
else
  log "Skipping internal task auth check"
  echo "ENABLE_INTERNAL_TASK_AUTH_CHECK is not true; internal task auth check skipped." | tee "$ARTIFACT_DIR/internal-task-auth.skip.txt"
fi

if [[ "$ENABLE_UPLOAD_INITIATION_CHECK" == "true" && -n "$STAGING_AUTH_BEARER_TOKEN" ]]; then
  log "Checking signed resumable upload initiation"
  upload_headers=(
    -H "Authorization: Bearer $STAGING_AUTH_BEARER_TOKEN"
    -H "Content-Type: application/json"
  )
  if [[ -n "$STAGING_WORKSPACE_ID" ]]; then
    upload_headers+=( -H "X-Workspace-Id: $STAGING_WORKSPACE_ID" )
  fi
  curl -fsSL \
    -X POST \
    "${upload_headers[@]}" \
    -D "$ARTIFACT_DIR/upload-initiation.headers" \
    "$API_URL/v1/media/uploads/signed-resumable" \
    -d "{\"filename\":\"$STAGING_UPLOAD_FILENAME\",\"filesize_bytes\":$STAGING_UPLOAD_FILESIZE_BYTES,\"mime_type\":\"$STAGING_UPLOAD_MIME_TYPE\",\"origin\":\"$STAGING_UPLOAD_ORIGIN\"}" > "$ARTIFACT_DIR/upload-initiation.body"
  assert_file_contains "$ARTIFACT_DIR/upload-initiation.body" '"upload_id"'
  assert_file_contains "$ARTIFACT_DIR/upload-initiation.body" '"gcs_resumable_url"'
  assert_file_contains "$ARTIFACT_DIR/upload-initiation.body" '"storage_path"'
else
  log "Skipping upload initiation check"
  echo "ENABLE_UPLOAD_INITIATION_CHECK is not true or STAGING_AUTH_BEARER_TOKEN is absent; upload initiation check skipped." | tee "$ARTIFACT_DIR/upload-initiation.skip.txt"
fi

if [[ "$ENABLE_FIXTURE_UPLOAD_CHECK" == "true" && -n "$STAGING_AUTH_BEARER_TOKEN" ]]; then
  log "Checking low-cost fixture upload and cleanup"
  fixture_headers=(
    -H "Authorization: Bearer $STAGING_AUTH_BEARER_TOKEN"
    -H "Content-Type: application/json"
  )
  if [[ -n "$STAGING_WORKSPACE_ID" ]]; then
    fixture_headers+=( -H "X-Workspace-Id: $STAGING_WORKSPACE_ID" )
  fi

  fixture_path="$ARTIFACT_DIR/$STAGING_FIXTURE_FILENAME"
  create_silent_wav_fixture "$fixture_path"
  fixture_filesize_bytes="$(python3 - "$fixture_path" <<'PY'
import os
import sys
print(os.path.getsize(sys.argv[1]))
PY
)"
  fixture_checksum_sha256="$(python3 - "$fixture_path" <<'PY'
import hashlib
import sys
from pathlib import Path
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"

  curl -fsSL \
    -X POST \
    "${fixture_headers[@]}" \
    -D "$ARTIFACT_DIR/fixture-project-create.headers" \
    "$API_URL/v1/projects" \
    -d "{\"name\":\"$STAGING_FIXTURE_PROJECT_NAME $RUN_ID\",\"source_language\":\"$STAGING_FIXTURE_SOURCE_LANGUAGE\",\"target_language\":\"$STAGING_FIXTURE_TARGET_LANGUAGE\"}" > "$ARTIFACT_DIR/fixture-project-create.body"
  CURRENT_PROJECT_ID="$(json_field "$ARTIFACT_DIR/fixture-project-create.body" "id")"

  curl -fsSL \
    -X POST \
    "${fixture_headers[@]}" \
    -D "$ARTIFACT_DIR/fixture-upload-init.headers" \
    "$API_URL/v1/media/uploads/signed-resumable" \
    -d "{\"filename\":\"$STAGING_FIXTURE_FILENAME\",\"filesize_bytes\":$fixture_filesize_bytes,\"mime_type\":\"$STAGING_FIXTURE_MIME_TYPE\",\"origin\":\"$STAGING_UPLOAD_ORIGIN\"}" > "$ARTIFACT_DIR/fixture-upload-init.body"

  fixture_upload_id="$(json_field "$ARTIFACT_DIR/fixture-upload-init.body" "upload_id")"
  fixture_resumable_url="$(json_field "$ARTIFACT_DIR/fixture-upload-init.body" "gcs_resumable_url")"
  fixture_storage_path="$(json_field "$ARTIFACT_DIR/fixture-upload-init.body" "storage_path")"

  curl -fsSL \
    -X PUT \
    -H "Content-Type: $STAGING_FIXTURE_MIME_TYPE" \
    -H "Content-Length: $fixture_filesize_bytes" \
    --data-binary "@$fixture_path" \
    -D "$ARTIFACT_DIR/fixture-upload-put.headers" \
    "$fixture_resumable_url" > "$ARTIFACT_DIR/fixture-upload-put.body"

  curl -fsSL \
    -X POST \
    "${fixture_headers[@]}" \
    -D "$ARTIFACT_DIR/fixture-upload-complete.headers" \
    "$API_URL/v1/media/uploads/signed-resumable/$fixture_upload_id/complete?project_id=$CURRENT_PROJECT_ID" \
    -d "{\"final_checksum_sha256\":\"$fixture_checksum_sha256\"}" > "$ARTIFACT_DIR/fixture-upload-complete.body"

  assert_file_contains "$ARTIFACT_DIR/fixture-upload-complete.body" '"media_id"'
  assert_file_contains "$ARTIFACT_DIR/fixture-upload-complete.body" '"storage_path"'
  fixture_media_id="$(json_field "$ARTIFACT_DIR/fixture-upload-complete.body" "media_id")"
  printf 'project_id=%s\nupload_id=%s\nmedia_id=%s\nstorage_path=%s\nfixture_path=%s\nfixture_filesize_bytes=%s\nfixture_checksum_sha256=%s\n' \
    "$CURRENT_PROJECT_ID" "$fixture_upload_id" "$fixture_media_id" "$fixture_storage_path" "$fixture_path" "$fixture_filesize_bytes" "$fixture_checksum_sha256" \
    > "$ARTIFACT_DIR/fixture-upload-metadata.txt"

  if [[ "$ENABLE_PROVIDER_EXECUTION_CHECK" == "true" ]]; then
    log "Checking provider-backed transcription execution"
    curl -fsSL \
      -X POST \
      "${fixture_headers[@]}" \
      -D "$ARTIFACT_DIR/provider-transcription-start.headers" \
      "$API_URL/v1/transcription/start" \
      -d "{\"media_id\":\"$fixture_media_id\",\"language\":\"$STAGING_TRANSCRIPTION_LANGUAGE\",\"enable_noise_reduction\":true,\"enable_loudness_norm\":true,\"enable_vad\":true}" > "$ARTIFACT_DIR/provider-transcription-start.body"

    provider_job_id="$(json_field "$ARTIFACT_DIR/provider-transcription-start.body" "job_id")"
    provider_transcript_id="$(json_field "$ARTIFACT_DIR/provider-transcription-start.body" "transcript_id")"
    deadline_epoch="$((SECONDS + STAGING_PROVIDER_EXECUTION_TIMEOUT_SECONDS))"

    while true; do
      curl -fsSL \
        -X GET \
        "${fixture_headers[@]}" \
        -D "$ARTIFACT_DIR/provider-transcript.headers" \
        "$API_URL/v1/transcription/$provider_transcript_id" > "$ARTIFACT_DIR/provider-transcript.body"
      provider_transcript_status="$(json_field "$ARTIFACT_DIR/provider-transcript.body" "status")"
      if [[ "$provider_transcript_status" == "completed" ]]; then
        break
      fi
      if [[ "$provider_transcript_status" == "failed" ]]; then
        curl -fsSL \
          -X GET \
          "${fixture_headers[@]}" \
          -D "$ARTIFACT_DIR/provider-pipeline-operation.headers" \
          "$API_URL/v1/projects/$CURRENT_PROJECT_ID/pipeline-operation" > "$ARTIFACT_DIR/provider-pipeline-operation.body"
        echo "ERROR: provider-backed transcription failed for transcript $provider_transcript_id" >&2
        exit 1
      fi
      if (( SECONDS >= deadline_epoch )); then
        curl -fsSL \
          -X GET \
          "${fixture_headers[@]}" \
          -D "$ARTIFACT_DIR/provider-pipeline-operation.headers" \
          "$API_URL/v1/projects/$CURRENT_PROJECT_ID/pipeline-operation" > "$ARTIFACT_DIR/provider-pipeline-operation.body"
        echo "ERROR: provider-backed transcription did not complete within ${STAGING_PROVIDER_EXECUTION_TIMEOUT_SECONDS}s" >&2
        exit 1
      fi
      sleep "$STAGING_PROVIDER_POLL_INTERVAL_SECONDS"
    done

    curl -fsSL \
      -X GET \
      "${fixture_headers[@]}" \
      -D "$ARTIFACT_DIR/provider-pipeline-operation.headers" \
      "$API_URL/v1/projects/$CURRENT_PROJECT_ID/pipeline-operation" > "$ARTIFACT_DIR/provider-pipeline-operation.body"
    assert_file_contains "$ARTIFACT_DIR/provider-pipeline-operation.body" '"status":"completed"'

    printf 'job_id=%s\ntranscript_id=%s\nstatus=%s\n' \
      "$provider_job_id" "$provider_transcript_id" "$provider_transcript_status" \
      > "$ARTIFACT_DIR/provider-transcription-metadata.txt"

    if [[ "$ENABLE_DUB_EXPORT_RETRIEVAL_CHECK" == "true" ]]; then
      log "Checking dub-only export retrieval"
      spoken_fixture_path="$ARTIFACT_DIR/$STAGING_DUB_FIXTURE_FILENAME"
      spoken_audio_path="$ARTIFACT_DIR/staging-smoke-spoken.wav"
      create_spoken_mp4_fixture "$spoken_fixture_path" "$spoken_audio_path"
      spoken_fixture_filesize_bytes="$(python3 - "$spoken_fixture_path" <<'PY'
import os
import sys
print(os.path.getsize(sys.argv[1]))
PY
)"
      spoken_fixture_checksum_sha256="$(python3 - "$spoken_fixture_path" <<'PY'
import hashlib
import sys
from pathlib import Path
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"

      curl -fsSL \
        -X POST \
        "${fixture_headers[@]}" \
        -D "$ARTIFACT_DIR/dub-fixture-upload-init.headers" \
        "$API_URL/v1/media/uploads/signed-resumable" \
        -d "{\"filename\":\"$STAGING_DUB_FIXTURE_FILENAME\",\"filesize_bytes\":$spoken_fixture_filesize_bytes,\"mime_type\":\"$STAGING_DUB_FIXTURE_MIME_TYPE\",\"origin\":\"$STAGING_UPLOAD_ORIGIN\"}" > "$ARTIFACT_DIR/dub-fixture-upload-init.body"

      dub_fixture_upload_id="$(json_field "$ARTIFACT_DIR/dub-fixture-upload-init.body" "upload_id")"
      dub_fixture_resumable_url="$(json_field "$ARTIFACT_DIR/dub-fixture-upload-init.body" "gcs_resumable_url")"
      dub_fixture_storage_path="$(json_field "$ARTIFACT_DIR/dub-fixture-upload-init.body" "storage_path")"

      curl -fsSL \
        -X PUT \
        -H "Content-Type: $STAGING_DUB_FIXTURE_MIME_TYPE" \
        -H "Content-Length: $spoken_fixture_filesize_bytes" \
        --data-binary "@$spoken_fixture_path" \
        -D "$ARTIFACT_DIR/dub-fixture-upload-put.headers" \
        "$dub_fixture_resumable_url" > "$ARTIFACT_DIR/dub-fixture-upload-put.body"

      curl -fsSL \
        -X POST \
        "${fixture_headers[@]}" \
        -D "$ARTIFACT_DIR/dub-fixture-upload-complete.headers" \
        "$API_URL/v1/media/uploads/signed-resumable/$dub_fixture_upload_id/complete?project_id=$CURRENT_PROJECT_ID" \
        -d "{\"final_checksum_sha256\":\"$spoken_fixture_checksum_sha256\"}" > "$ARTIFACT_DIR/dub-fixture-upload-complete.body"

      assert_file_contains "$ARTIFACT_DIR/dub-fixture-upload-complete.body" '"media_id"'
      assert_file_contains "$ARTIFACT_DIR/dub-fixture-upload-complete.body" '"storage_path"'
      dub_media_id="$(json_field "$ARTIFACT_DIR/dub-fixture-upload-complete.body" "media_id")"

      curl -fsSL \
        -X POST \
        "${fixture_headers[@]}" \
        -D "$ARTIFACT_DIR/dub-transcription-start.headers" \
        "$API_URL/v1/transcription/start" \
        -d "{\"media_id\":\"$dub_media_id\",\"language\":\"$STAGING_TRANSCRIPTION_LANGUAGE\",\"enable_noise_reduction\":true,\"enable_loudness_norm\":true,\"enable_vad\":true}" > "$ARTIFACT_DIR/dub-transcription-start.body"

      dub_transcript_id="$(json_field "$ARTIFACT_DIR/dub-transcription-start.body" "transcript_id")"
      dub_export_deadline_epoch="$((SECONDS + STAGING_DUB_EXPORT_TIMEOUT_SECONDS))"
      while true; do
        curl -fsSL \
          -X GET \
          "${fixture_headers[@]}" \
          -D "$ARTIFACT_DIR/dub-transcript.headers" \
          "$API_URL/v1/transcription/$dub_transcript_id" > "$ARTIFACT_DIR/dub-transcript.body"
        dub_transcript_status="$(json_field "$ARTIFACT_DIR/dub-transcript.body" "status")"
        if [[ "$dub_transcript_status" == "completed" ]]; then
          break
        fi
        if [[ "$dub_transcript_status" == "failed" ]]; then
          curl -fsSL \
            -X GET \
            "${fixture_headers[@]}" \
            -D "$ARTIFACT_DIR/dub-transcription-operation.headers" \
            "$API_URL/v1/projects/$CURRENT_PROJECT_ID/pipeline-operation" > "$ARTIFACT_DIR/dub-transcription-operation.body"
          echo "ERROR: dub export transcription failed for transcript $dub_transcript_id" >&2
          exit 1
        fi
        if (( SECONDS >= dub_export_deadline_epoch )); then
          curl -fsSL \
            -X GET \
            "${fixture_headers[@]}" \
            -D "$ARTIFACT_DIR/dub-transcription-operation.headers" \
            "$API_URL/v1/projects/$CURRENT_PROJECT_ID/pipeline-operation" > "$ARTIFACT_DIR/dub-transcription-operation.body"
          echo "ERROR: dub export transcription did not complete within ${STAGING_DUB_EXPORT_TIMEOUT_SECONDS}s" >&2
          exit 1
        fi
        sleep "$STAGING_DUB_EXPORT_POLL_INTERVAL_SECONDS"
      done

      curl -fsSL \
        -X POST \
        "${fixture_headers[@]}" \
        -D "$ARTIFACT_DIR/dub-translation-start.headers" \
        "$API_URL/v1/translation/translate-project" \
        -d "{\"transcript_id\":\"$dub_transcript_id\",\"source_language\":\"$STAGING_TRANSCRIPTION_LANGUAGE\",\"target_language\":\"$STAGING_FIXTURE_TARGET_LANGUAGE\",\"tone\":\"natural\"}" > "$ARTIFACT_DIR/dub-translation-start.body"

      dub_translation_job_id="$(json_field "$ARTIFACT_DIR/dub-translation-start.body" "job_id")"
      dub_export_deadline_epoch="$((SECONDS + STAGING_DUB_EXPORT_TIMEOUT_SECONDS))"
      while true; do
        curl -fsSL \
          -X GET \
          "${fixture_headers[@]}" \
          -D "$ARTIFACT_DIR/dub-translation-operation.headers" \
          "$API_URL/v1/projects/$CURRENT_PROJECT_ID/pipeline-operation" > "$ARTIFACT_DIR/dub-translation-operation.body"
        dub_translation_operation_type="$(json_field "$ARTIFACT_DIR/dub-translation-operation.body" "operation_type")"
        dub_translation_status="$(json_field "$ARTIFACT_DIR/dub-translation-operation.body" "status")"
        if [[ "$dub_translation_operation_type" == "translation" && "$dub_translation_status" == "completed" ]]; then
          break
        fi
        if [[ "$dub_translation_operation_type" == "translation" && "$dub_translation_status" == "failed" ]]; then
          echo "ERROR: dub export translation failed for transcript $dub_transcript_id" >&2
          exit 1
        fi
        if (( SECONDS >= dub_export_deadline_epoch )); then
          echo "ERROR: dub export translation did not complete within ${STAGING_DUB_EXPORT_TIMEOUT_SECONDS}s" >&2
          exit 1
        fi
        sleep "$STAGING_DUB_EXPORT_POLL_INTERVAL_SECONDS"
      done

      curl -fsSL \
        -X POST \
        "${fixture_headers[@]}" \
        -D "$ARTIFACT_DIR/dub-render-start.headers" \
        "$API_URL/v1/lipsync/render-project" \
        -d "{\"media_file_id\":\"$dub_media_id\",\"transcript_id\":\"$dub_transcript_id\",\"target_language\":\"$STAGING_FIXTURE_TARGET_LANGUAGE\",\"project_id\":\"$CURRENT_PROJECT_ID\",\"burn_in_subtitles\":false,\"enable_lipsync\":false}" > "$ARTIFACT_DIR/dub-render-start.body"

      dub_render_job_id="$(json_field "$ARTIFACT_DIR/dub-render-start.body" "job_id")"
      dub_export_deadline_epoch="$((SECONDS + STAGING_DUB_EXPORT_TIMEOUT_SECONDS))"
      while true; do
        curl -fsSL \
          -X GET \
          "${fixture_headers[@]}" \
          -D "$ARTIFACT_DIR/dub-render.headers" \
          "$API_URL/v1/lipsync/job/$dub_render_job_id" > "$ARTIFACT_DIR/dub-render.body"
        dub_render_status="$(json_field "$ARTIFACT_DIR/dub-render.body" "status")"
        if [[ "$dub_render_status" == "completed" ]]; then
          break
        fi
        if [[ "$dub_render_status" == "failed" ]]; then
          echo "ERROR: dub-only render failed for job $dub_render_job_id" >&2
          exit 1
        fi
        if (( SECONDS >= dub_export_deadline_epoch )); then
          echo "ERROR: dub-only render did not complete within ${STAGING_DUB_EXPORT_TIMEOUT_SECONDS}s" >&2
          exit 1
        fi
        sleep "$STAGING_DUB_EXPORT_POLL_INTERVAL_SECONDS"
      done

      assert_file_contains "$ARTIFACT_DIR/dub-render.body" '"render_mode":"dub_only"'
      assert_file_contains "$ARTIFACT_DIR/dub-render.body" '"download_video_url"'
      dub_download_url="$(json_field "$ARTIFACT_DIR/dub-render.body" "download_video_url")"
      curl -fsSL \
        -D "$ARTIFACT_DIR/dub-download.headers" \
        "$dub_download_url" > "$ARTIFACT_DIR/dub-only-output.mp4"
      assert_nonempty_file "$ARTIFACT_DIR/dub-only-output.mp4"
      dub_output_filesize_bytes="$(python3 - "$ARTIFACT_DIR/dub-only-output.mp4" <<'PY'
import os
import sys
print(os.path.getsize(sys.argv[1]))
PY
)"

      printf 'media_id=%s\ntranscript_id=%s\ntranslation_job_id=%s\nrender_job_id=%s\nrender_status=%s\ndownload_url=%s\noutput_filesize_bytes=%s\n' \
        "$dub_media_id" "$dub_transcript_id" "$dub_translation_job_id" "$dub_render_job_id" "$dub_render_status" "$dub_download_url" "$dub_output_filesize_bytes" \
        > "$ARTIFACT_DIR/dub-export-metadata.txt"
    else
      log "Skipping dub-only export retrieval check"
      echo "ENABLE_DUB_EXPORT_RETRIEVAL_CHECK is not true; dub-only export retrieval check skipped." | tee "$ARTIFACT_DIR/dub-export.skip.txt"
    fi
  else
    log "Skipping provider-backed execution check"
    echo "ENABLE_PROVIDER_EXECUTION_CHECK is not true; provider-backed execution check skipped." | tee "$ARTIFACT_DIR/provider-execution.skip.txt"
    if [[ "$ENABLE_DUB_EXPORT_RETRIEVAL_CHECK" == "true" ]]; then
      log "Skipping dub-only export retrieval check"
      echo "ENABLE_DUB_EXPORT_RETRIEVAL_CHECK requires ENABLE_PROVIDER_EXECUTION_CHECK so dub-only export retrieval was skipped." | tee "$ARTIFACT_DIR/dub-export.skip.txt"
    fi
  fi

  archive_fixture_project
else
  log "Skipping low-cost fixture upload check"
  echo "ENABLE_FIXTURE_UPLOAD_CHECK is not true or STAGING_AUTH_BEARER_TOKEN is absent; fixture upload check skipped." | tee "$ARTIFACT_DIR/fixture-upload.skip.txt"
  if [[ "$ENABLE_DUB_EXPORT_RETRIEVAL_CHECK" == "true" ]]; then
    log "Skipping dub-only export retrieval check"
    echo "ENABLE_DUB_EXPORT_RETRIEVAL_CHECK requires ENABLE_FIXTURE_UPLOAD_CHECK and STAGING_AUTH_BEARER_TOKEN so dub-only export retrieval was skipped." | tee "$ARTIFACT_DIR/dub-export.skip.txt"
  fi
fi

log "Staging smoke preflight passed"
printf 'Artifacts saved to %s\n' "$ARTIFACT_DIR"

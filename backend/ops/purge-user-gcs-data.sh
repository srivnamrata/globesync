#!/usr/bin/env bash
# Reusable GlobeSync GCS cleanup for user-owned media and derived artifacts.
# Usage:
#   DATABASE_URL='postgresql://...' APPLY=1 bash backend/ops/purge-user-gcs-data.sh \
#     srivnamrata@gmail.com roboplaylab@gmail.com
#
# Defaults:
# * With no CLI args, the script targets the two known cleanup emails.
# * With APPLY unset or APPLY=0, the script only previews matching URIs and project IDs.
# * Preview files are persisted under backend/ops/.purge-user-gcs-data/ by default.
#
# Important:
# * Run this before the database purge so the database can still resolve project IDs and object paths.
# * Review the generated object_uris.txt and project_ids.txt files before running with APPLY=1.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ID="${PROJECT_ID:-project-794c406e-c0ab-4a50-8e9}"
RAW_BUCKET_NAME="${RAW_BUCKET_NAME:-${PROJECT_ID}-media-raw}"
EXPORTS_BUCKET_NAME="${EXPORTS_BUCKET_NAME:-${PROJECT_ID}-media-exports}"
RAW_BUCKET_URI="gs://${RAW_BUCKET_NAME}"
EXPORTS_BUCKET_URI="gs://${EXPORTS_BUCKET_NAME}"
DATABASE_URL="${DATABASE_URL:-${SYNC_DATABASE_URL:-}}"
APPLY="${APPLY:-0}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${SCRIPT_DIR}/.purge-user-gcs-data}"
RUN_LABEL="${RUN_LABEL:-$(date +%Y%m%d-%H%M%S)}"
WORK_DIR="${OUTPUT_ROOT}/${RUN_LABEL}"

if [[ $# -gt 0 ]]; then
  EMAIL_1="$1"
  EMAIL_2="${2:-}"
else
  EMAIL_1="${EMAIL_1:-srivnamrata@gmail.com}"
  EMAIL_2="${EMAIL_2:-roboplaylab@gmail.com}"
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  sed -n '1,14p' "$0"
  exit 0
fi

if [[ -z "${DATABASE_URL}" ]]; then
  echo "ERROR: Set DATABASE_URL or SYNC_DATABASE_URL before running this script." >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql is required but was not found on PATH." >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud is required but was not found on PATH." >&2
  exit 1
fi

mkdir -p "$WORK_DIR"
PROJECT_IDS_FILE="$WORK_DIR/project_ids.txt"
OBJECT_URIS_FILE="$WORK_DIR/object_uris.txt"

gcloud config set project "$PROJECT_ID" >/dev/null

PSQL_ARGS=("$DATABASE_URL" -v ON_ERROR_STOP=1 -v email_1="$EMAIL_1")
if [[ -n "$EMAIL_2" ]]; then
  PSQL_ARGS+=(-v email_2="$EMAIL_2")
else
  PSQL_ARGS+=(-v email_2="")
fi

psql "${PSQL_ARGS[@]}" -At <<'SQL' > "$PROJECT_IDS_FILE"
WITH target_users AS (
  SELECT id
  FROM users
  WHERE lower(email) IN (lower(:'email_1'), lower(:'email_2'))
),
target_workspaces AS (
  SELECT DISTINCT w.id
  FROM workspaces w
  WHERE w.owner_user_id IN (SELECT id FROM target_users)
),
target_projects AS (
  SELECT DISTINCT p.id
  FROM projects p
  WHERE p.workspace_id IN (SELECT id FROM target_workspaces)
     OR p.owner_user_id IN (SELECT id FROM target_users)
     OR p.created_by_user_id IN (SELECT id FROM target_users)
)
SELECT id::text
FROM target_projects
ORDER BY 1;
SQL

psql "${PSQL_ARGS[@]}" -v raw_bucket_name="$RAW_BUCKET_NAME" -At <<'SQL' > "$OBJECT_URIS_FILE"
WITH target_users AS (
  SELECT id
  FROM users
  WHERE lower(email) IN (lower(:'email_1'), lower(:'email_2'))
),
target_workspaces AS (
  SELECT DISTINCT w.id
  FROM workspaces w
  WHERE w.owner_user_id IN (SELECT id FROM target_users)
),
target_projects AS (
  SELECT DISTINCT p.id
  FROM projects p
  WHERE p.workspace_id IN (SELECT id FROM target_workspaces)
     OR p.owner_user_id IN (SELECT id FROM target_users)
     OR p.created_by_user_id IN (SELECT id FROM target_users)
),
target_media_files AS (
  SELECT DISTINCT m.*
  FROM media_files m
  WHERE m.project_id IN (SELECT id FROM target_projects)
     OR m.workspace_id IN (SELECT id FROM target_workspaces)
     OR m.user_id IN (SELECT id FROM target_users)
),
target_transcripts AS (
  SELECT DISTINCT t.id
  FROM transcripts t
  WHERE t.project_id IN (SELECT id FROM target_projects)
     OR t.workspace_id IN (SELECT id FROM target_workspaces)
     OR t.media_file_id IN (SELECT id FROM target_media_files)
),
target_segments AS (
  SELECT ts.id
  FROM transcript_segments ts
  WHERE ts.transcript_id IN (SELECT id FROM target_transcripts)
),
target_translations AS (
  SELECT DISTINCT tr.*
  FROM translations tr
  WHERE tr.project_id IN (SELECT id FROM target_projects)
     OR tr.workspace_id IN (SELECT id FROM target_workspaces)
     OR tr.transcript_segment_id IN (SELECT id FROM target_segments)
),
target_lipsync_jobs AS (
  SELECT DISTINCT lj.id
  FROM lipsync_jobs lj
  WHERE lj.project_id IN (SELECT id FROM target_projects)
)
SELECT DISTINCT uri
FROM (
  SELECT 'gs://' || mf.storage_bucket || '/' || mf.storage_path AS uri
  FROM target_media_files mf
  WHERE mf.storage_path IS NOT NULL

  UNION ALL

  SELECT 'gs://' || mf.storage_bucket || '/' || mf.thumbnail_path AS uri
  FROM target_media_files mf
  WHERE mf.thumbnail_path IS NOT NULL

  UNION ALL

  SELECT 'gs://' || ga.storage_bucket || '/' || ga.storage_path AS uri
  FROM generated_audios ga
  WHERE ga.translation_id IN (SELECT id FROM target_translations)

  UNION ALL

  SELECT 'gs://' || :'raw_bucket_name' || '/' || tr.target_audio_gcs_path AS uri
  FROM target_translations tr
  WHERE tr.target_audio_gcs_path IS NOT NULL

  UNION ALL

  SELECT 'gs://' || :'raw_bucket_name' || '/' || ej.output_video_gcs_path AS uri
  FROM export_jobs ej
  WHERE ej.project_id IN (SELECT id FROM target_projects)
    AND ej.output_video_gcs_path IS NOT NULL

  UNION ALL

  SELECT 'gs://' || :'raw_bucket_name' || '/' || lj.output_video_gcs_path AS uri
  FROM lipsync_jobs lj
  WHERE lj.project_id IN (SELECT id FROM target_projects)
    AND lj.output_video_gcs_path IS NOT NULL

  UNION ALL

  SELECT 'gs://' || :'raw_bucket_name' || '/' || fm.segment_rendered_video_path AS uri
  FROM frame_metadata fm
  WHERE fm.lipsync_job_id IN (SELECT id FROM target_lipsync_jobs)
    AND fm.segment_rendered_video_path IS NOT NULL

  UNION ALL

  SELECT vp.reference_sample_gcs_path AS uri
  FROM voice_profiles vp
  WHERE vp.project_id IN (SELECT id FROM target_projects)
    AND vp.reference_sample_gcs_path IS NOT NULL

  UNION ALL

  SELECT 'gs://' || :'raw_bucket_name' || '/' || p.last_rendered_video_gcs_path AS uri
  FROM projects p
  WHERE p.id IN (SELECT id FROM target_projects)
    AND p.last_rendered_video_gcs_path IS NOT NULL
) x
WHERE uri IS NOT NULL
  AND btrim(uri) <> ''
ORDER BY 1;
SQL

PROJECT_COUNT=$(grep -c . "$PROJECT_IDS_FILE" || true)
OBJECT_COUNT=$(grep -c . "$OBJECT_URIS_FILE" || true)

echo "Prepared GlobeSync GCS cleanup inputs"
echo "  Project: ${PROJECT_ID}"
echo "  Email 1: ${EMAIL_1}"
if [[ -n "$EMAIL_2" ]]; then
  echo "  Email 2: ${EMAIL_2}"
fi
echo "  Project IDs file: ${PROJECT_IDS_FILE} (${PROJECT_COUNT} rows)"
echo "  Object URIs file: ${OBJECT_URIS_FILE} (${OBJECT_COUNT} rows)"

if [[ "$PROJECT_COUNT" -eq 0 && "$OBJECT_COUNT" -eq 0 ]]; then
  echo "No matching projects or object URIs were found. Nothing to delete."
  exit 0
fi

echo
echo "Sample object URIs:"
head -n 20 "$OBJECT_URIS_FILE" || true

echo
echo "Project IDs:"
cat "$PROJECT_IDS_FILE" || true

echo
if [[ "$APPLY" != "1" ]]; then
  echo "Dry run only. Re-run with APPLY=1 to delete the listed GCS objects and prefixes."
  echo "Preview files retained under: ${WORK_DIR}"
  exit 0
fi

echo "Deleting exact object URIs..."
while IFS= read -r uri; do
  [[ -n "$uri" ]] || continue
  gcloud storage rm "$uri" || true
done < "$OBJECT_URIS_FILE"

echo "Deleting derived per-project prefixes from ${RAW_BUCKET_URI}..."
while IFS= read -r project_id; do
  [[ -n "$project_id" ]] || continue
  gcloud storage rm --recursive "${RAW_BUCKET_URI}/tts_segments/${project_id}" || true
  gcloud storage rm --recursive "${RAW_BUCKET_URI}/master_dubbed/${project_id}" || true
  gcloud storage rm --recursive "${RAW_BUCKET_URI}/exports/${project_id}" || true
  gcloud storage rm --recursive "${RAW_BUCKET_URI}/voice_profiles/${project_id}" || true
  gcloud storage rm --recursive "${EXPORTS_BUCKET_URI}/exports/${project_id}" || true
done < "$PROJECT_IDS_FILE"

echo "GCS cleanup completed."
echo "Run artifacts retained under: ${WORK_DIR}"

#!/usr/bin/env bash
# Optional foundation provisioning (buckets, Cloud SQL, secrets, queue, IAM).
# Safe to re-run; most steps are idempotent. Does not create or upload SA keys.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-project-794c406e-c0ab-4a50-8e9}"
REGION="${REGION:-asia-south1}"
RUNTIME_SA="${RUNTIME_SA:-globesync@${PROJECT_ID}.iam.gserviceaccount.com}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${RUNTIME_SA%%@*}}"
RAW_BUCKET="${RAW_BUCKET:-${PROJECT_ID}-media-raw}"
EXPORTS_BUCKET="${EXPORTS_BUCKET:-${PROJECT_ID}-media-exports}"
SQL_INSTANCE="${SQL_INSTANCE:-translation-pg}"
SQL_DB="${SQL_DB:-translation_db}"
SQL_USER="${SQL_USER:-translation_app}"
TASKS_QUEUE="${TASKS_QUEUE:-translation-jobs}"

gcloud config set project "$PROJECT_ID"
PROJECT_NUMBER="${PROJECT_NUMBER:-$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')}"
BUILD_SA="${BUILD_SA:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudtasks.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  translate.googleapis.com

echo "==> Runtime service account"
gcloud iam service-accounts describe "$RUNTIME_SA" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
       --display-name="Globesync Cloud Run runtime"

echo "==> Buckets (bucket-scoped IAM, not project-wide)"
for b in "$RAW_BUCKET" "$EXPORTS_BUCKET"; do
  gcloud storage buckets describe "gs://${b}" >/dev/null 2>&1 \
    || gcloud storage buckets create "gs://${b}" --location="$REGION" --uniform-bucket-level-access
  gcloud storage buckets add-iam-policy-binding "gs://${b}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/storage.objectAdmin"
done

echo "==> Cloud SQL (Postgres)"
if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="$REGION" \
    --storage-size=20GB \
    --storage-auto-increase \
    --availability-type=ZONAL \
    --assign-ip
fi
gcloud sql databases describe "$SQL_DB" --instance="$SQL_INSTANCE" >/dev/null 2>&1 \
  || gcloud sql databases create "$SQL_DB" --instance="$SQL_INSTANCE"

SQL_USER_EXISTS=false
gcloud sql users list --instance="$SQL_INSTANCE" --format='value(name)' | grep -qx "$SQL_USER" \
  && SQL_USER_EXISTS=true

if [[ -n "${SQL_PASSWORD:-}" ]]; then
  echo "Using SQL_PASSWORD from environment."
elif [[ "$SQL_USER_EXISTS" == true ]]; then
  if gcloud secrets describe translation-sync-database-url >/dev/null 2>&1; then
    SQL_PASSWORD="$(gcloud secrets versions access latest --secret=translation-sync-database-url | python3 -c 'from urllib.parse import urlparse; import sys; print(urlparse(sys.stdin.read().strip()).password or "")')"
    if [[ -z "$SQL_PASSWORD" ]]; then
      echo "Failed to extract SQL password from translation-sync-database-url." >&2
      echo "Set SQL_PASSWORD explicitly and rerun to repair the DB credentials." >&2
      exit 1
    fi
    echo "Reusing SQL password from existing Secret Manager value."
  else
    echo "Cloud SQL user $SQL_USER already exists, but translation-sync-database-url was not found." >&2
    echo "Set SQL_PASSWORD explicitly and rerun so the DB user and secrets can be aligned." >&2
    exit 1
  fi
else
  SQL_PASSWORD="$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)"
  echo "Generated SQL_PASSWORD for new Cloud SQL user."
fi

if [[ "$SQL_USER_EXISTS" == true ]]; then
  if [[ -n "${SQL_PASSWORD:-}" ]]; then
    gcloud sql users set-password "$SQL_USER" --instance="$SQL_INSTANCE" --password="$SQL_PASSWORD" >/dev/null
  fi
else
  gcloud sql users create "$SQL_USER" --instance="$SQL_INSTANCE" --password="$SQL_PASSWORD"
fi

CONNECTION_NAME="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')"
ASYNC_URL="postgresql+asyncpg://${SQL_USER}:${SQL_PASSWORD}@/${SQL_DB}?host=/cloudsql/${CONNECTION_NAME}"
SYNC_URL="postgresql://${SQL_USER}:${SQL_PASSWORD}@/${SQL_DB}?host=/cloudsql/${CONNECTION_NAME}"

echo "==> Secrets (no GCS HMAC keys)"
printf '%s' "$ASYNC_URL" | gcloud secrets create translation-database-url --data-file=- 2>/dev/null \
  || printf '%s' "$ASYNC_URL" | gcloud secrets versions add translation-database-url --data-file=-
printf '%s' "$SYNC_URL" | gcloud secrets create translation-sync-database-url --data-file=- 2>/dev/null \
  || printf '%s' "$SYNC_URL" | gcloud secrets versions add translation-sync-database-url --data-file=-

if [[ -n "${JWT_SECRET:-}" ]]; then
  printf '%s' "$JWT_SECRET" | gcloud secrets create translation-jwt-secret --data-file=- 2>/dev/null \
    || printf '%s' "$JWT_SECRET" | gcloud secrets versions add translation-jwt-secret --data-file=-
  echo "Updated translation-jwt-secret from environment."
elif gcloud secrets describe translation-jwt-secret >/dev/null 2>&1; then
  echo "Keeping existing translation-jwt-secret value."
else
  JWT_SECRET="$(openssl rand -hex 32)"
  printf '%s' "$JWT_SECRET" | gcloud secrets create translation-jwt-secret --data-file=-
  echo "Generated translation-jwt-secret."
fi

if [[ -n "${DEEPGRAM_API_KEY:-}" ]]; then
  printf '%s' "$DEEPGRAM_API_KEY" | gcloud secrets create transcription-deepgram-api-key --data-file=- 2>/dev/null \
    || printf '%s' "$DEEPGRAM_API_KEY" | gcloud secrets versions add transcription-deepgram-api-key --data-file=-
  echo "Updated transcription-deepgram-api-key from environment."
else
  echo "DEEPGRAM_API_KEY not set; skipping transcription-deepgram-api-key secret update."
fi

for secret in translation-database-url translation-sync-database-url translation-jwt-secret; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
done

if gcloud secrets describe transcription-deepgram-api-key >/dev/null 2>&1; then
  gcloud secrets add-iam-policy-binding transcription-deepgram-api-key \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
fi

echo "==> Runtime service account roles"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudsql.client" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudtranslate.user" >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/iam.serviceAccountTokenCreator" >/dev/null

echo "==> Cloud Build service account roles"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/storage.objectViewer" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/artifactregistry.writer" >/dev/null

echo "==> Cloud Tasks queue"
gcloud tasks queues describe "$TASKS_QUEUE" --location="$REGION" >/dev/null 2>&1 \
  || gcloud tasks queues create "$TASKS_QUEUE" --location="$REGION"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudtasks.enqueuer" >/dev/null

cat <<EOF

Foundation ready.
  CLOUDSQL_INSTANCE=$CONNECTION_NAME
  RAW_BUCKET=$RAW_BUCKET
  EXPORTS_BUCKET=$EXPORTS_BUCKET
  RUNTIME_SA=$RUNTIME_SA
  BUILD_SA=$BUILD_SA
  TASKS_QUEUE=$TASKS_QUEUE

Next:
  export CLOUDSQL_INSTANCE=$CONNECTION_NAME RAW_BUCKET=$RAW_BUCKET EXPORTS_BUCKET=$EXPORTS_BUCKET
  # Verify deploy/cloudrun.env.yaml still matches this project/region/service account if you changed defaults.
  ./deploy/deploy-cloudrun.sh
EOF

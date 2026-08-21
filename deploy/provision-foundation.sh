#!/usr/bin/env bash
# Optional foundation provisioning (buckets, Cloud SQL, secrets, queue, IAM).
# Safe to re-run; most steps are idempotent. Does not create or upload SA keys.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-project-794c406e-c0ab-4a50-8e9}"
REGION="${REGION:-asia-south1}"
RUNTIME_SA="${RUNTIME_SA:-globesync@${PROJECT_ID}.iam.gserviceaccount.com}"
RAW_BUCKET="${RAW_BUCKET:-${PROJECT_ID}-media-raw}"
EXPORTS_BUCKET="${EXPORTS_BUCKET:-${PROJECT_ID}-media-exports}"
SQL_INSTANCE="${SQL_INSTANCE:-translation-pg}"
SQL_DB="${SQL_DB:-translation_db}"
SQL_USER="${SQL_USER:-translation_app}"
TASKS_QUEUE="${TASKS_QUEUE:-translation-jobs}"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudtasks.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com

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

if [[ -z "${SQL_PASSWORD:-}" ]]; then
  SQL_PASSWORD="$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)"
  echo "Generated SQL_PASSWORD (store securely)."
fi
gcloud sql users list --instance="$SQL_INSTANCE" --format='value(name)' | grep -qx "$SQL_USER" \
  || gcloud sql users create "$SQL_USER" --instance="$SQL_INSTANCE" --password="$SQL_PASSWORD"

CONNECTION_NAME="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')"
ASYNC_URL="postgresql+asyncpg://${SQL_USER}:${SQL_PASSWORD}@/${SQL_DB}?host=/cloudsql/${CONNECTION_NAME}"
SYNC_URL="postgresql://${SQL_USER}:${SQL_PASSWORD}@/${SQL_DB}?host=/cloudsql/${CONNECTION_NAME}"

echo "==> Secrets (no GCS HMAC keys)"
printf '%s' "$ASYNC_URL" | gcloud secrets create translation-database-url --data-file=- 2>/dev/null \
  || printf '%s' "$ASYNC_URL" | gcloud secrets versions add translation-database-url --data-file=-
printf '%s' "$SYNC_URL" | gcloud secrets create translation-sync-database-url --data-file=- 2>/dev/null \
  || printf '%s' "$SYNC_URL" | gcloud secrets versions add translation-sync-database-url --data-file=-
JWT_SECRET="$(openssl rand -hex 32)"
printf '%s' "$JWT_SECRET" | gcloud secrets create translation-jwt-secret --data-file=- 2>/dev/null \
  || printf '%s' "$JWT_SECRET" | gcloud secrets versions add translation-jwt-secret --data-file=-

for secret in translation-database-url translation-sync-database-url translation-jwt-secret; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
done

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
  TASKS_QUEUE=$TASKS_QUEUE

Next:
  export CLOUDSQL_INSTANCE=$CONNECTION_NAME RAW_BUCKET=$RAW_BUCKET EXPORTS_BUCKET=$EXPORTS_BUCKET
  # Edit deploy/cloudrun.env.yaml REPLACE_* values, then:
  ./deploy/deploy-cloudrun.sh
EOF

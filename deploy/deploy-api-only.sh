#!/usr/bin/env bash
# Portable Cloud Run deploy for translation-api only.
# Run from repo root in Cloud Shell or any authenticated gcloud environment.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROJECT_ID="${PROJECT_ID:-project-794c406e-c0ab-4a50-8e9}"
REGION="${REGION:-asia-south1}"
REPO="${ARTIFACT_REPO:-translation}"
API_SERVICE="${API_SERVICE:-translation-api}"
RUNTIME_SA="${RUNTIME_SA:-globesync@${PROJECT_ID}.iam.gserviceaccount.com}"
CLOUDSQL_INSTANCE="${CLOUDSQL_INSTANCE:-${PROJECT_ID}:${REGION}:translation-pg}"
RAW_BUCKET="${RAW_BUCKET:-${PROJECT_ID}-media-raw}"
EXPORTS_BUCKET="${EXPORTS_BUCKET:-${PROJECT_ID}-media-exports}"
ENV_FILE="${ENV_FILE:-deploy/cloudrun.env.yaml}"

# Connection budget example: 100 Cloud SQL connections.
# pool_size=5, concurrency=10 → cap max instances near 100/(5*ceil(10/5)) ≈ 10.
API_CONCURRENCY="${API_CONCURRENCY:-10}"
API_MAX_INSTANCES="${API_MAX_INSTANCES:-8}"
API_MIN_INSTANCES="${API_MIN_INSTANCES:-0}"
API_TIMEOUT="${API_TIMEOUT:-300}"

gcloud config set project "$PROJECT_ID"

API_SECRETS="DATABASE_URL=translation-database-url:latest,SYNC_DATABASE_URL=translation-sync-database-url:latest,JWT_SECRET_KEY=translation-jwt-secret:latest"
if gcloud secrets describe transcription-deepgram-api-key >/dev/null 2>&1; then
  API_SECRETS="${API_SECRETS},DEEPGRAM_API_KEY=transcription-deepgram-api-key:latest"
fi

echo "==> Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudtasks.googleapis.com \
  cloudbuild.googleapis.com \
  iamcredentials.googleapis.com

echo "==> Ensuring Artifact Registry repository"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "$REPO" \
       --repository-format=docker \
       --location="$REGION" \
       --description="Translation platform images"

API_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${API_SERVICE}:$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M)"

echo "==> Building API image: $API_IMAGE"
cat > /tmp/translation-api-cloudbuild.yaml <<EOF
steps:
  - name: gcr.io/cloud-builders/docker
    args: ["build", "-t", "${API_IMAGE}", "-f", "backend/Dockerfile", "."]
images:
  - ${API_IMAGE}
EOF
gcloud builds submit --config=/tmp/translation-api-cloudbuild.yaml .

echo "==> Running Alembic migrations (one-off Cloud Run Job)"
JOB_NAME="translation-migrate"
gcloud run jobs delete "$JOB_NAME" --region="$REGION" --quiet >/dev/null 2>&1 || true
gcloud run jobs create "$JOB_NAME" \
  --image="$API_IMAGE" \
  --region="$REGION" \
  --service-account="$RUNTIME_SA" \
  --set-cloudsql-instances="$CLOUDSQL_INSTANCE" \
  --set-secrets="$API_SECRETS" \
  --env-vars-file="$ENV_FILE" \
  --command="alembic" \
  --args="upgrade,head" \
  --max-retries=0 \
  --task-timeout=600
gcloud run jobs execute "$JOB_NAME" --region="$REGION" --wait

echo "==> Deploying $API_SERVICE"
gcloud run deploy "$API_SERVICE" \
  --image="$API_IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --service-account="$RUNTIME_SA" \
  --allow-unauthenticated \
  --port=8080 \
  --timeout="$API_TIMEOUT" \
  --concurrency="$API_CONCURRENCY" \
  --min-instances="$API_MIN_INSTANCES" \
  --max-instances="$API_MAX_INSTANCES" \
  --cpu=1 \
  --memory=1Gi \
  --add-cloudsql-instances="$CLOUDSQL_INSTANCE" \
  --set-secrets="$API_SECRETS" \
  --env-vars-file="$ENV_FILE"

API_URL="$(gcloud run services describe "$API_SERVICE" --region="$REGION" --format='value(status.url)')"
echo "API URL: $API_URL"

echo "==> Updating API runtime variables"
gcloud run services update "$API_SERVICE" \
  --region="$REGION" \
  --update-env-vars="CLOUD_TASKS_TARGET_URL=${API_URL},INTERNAL_TASKS_AUDIENCE=${API_URL},GCS_BUCKET_NAME=${RAW_BUCKET},GCS_EXPORTS_BUCKET=${EXPORTS_BUCKET}"

echo "==> Smoke checks"
curl -fsS "${API_URL}/health"
echo
curl -fsS "${API_URL}/healthz" || true
echo

echo "Deploy complete."
echo "  API: $API_URL"
echo "Create queue '${CLOUD_TASKS_QUEUE:-translation-jobs}' before testing Cloud Tasks-backed routes."

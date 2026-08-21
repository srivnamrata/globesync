# Cloud Run deployment (two HTTP services only)

This deployment creates:

- `translation-api` — FastAPI API (Cloud SQL + GCS + Translation via service identity)
- `translation-web` — Next.js frontend

Cloud Tasks is optional queue infrastructure that POSTs to a private internal API
route. It is **not** a third Cloud Run service. STT / TTS / lip-sync / large exports
remain disabled until Cloud Run Jobs are added later.

## Prerequisites

1. Authenticated `gcloud` (Cloud Shell is fine).
2. Defaults target region **asia-south1** and project buckets/SQL already in use.
3. Create Secret Manager secrets (no storage HMAC keys) via `provision-foundation.sh`, or manually:

   - `translation-database-url` — async SQLAlchemy URL (`postgresql+asyncpg://...`)
   - `translation-sync-database-url` — sync URL for Alembic (`postgresql://...`)
   - `translation-jwt-secret`

4. Grant the API runtime service account (`globesync@…`) only:

   - Cloud Translation user
   - Cloud SQL Client
   - Object Admin (or finer object roles) on the raw + export **buckets**
   - `roles/iam.serviceAccountTokenCreator` on itself (for V4 signed URLs)
   - Cloud Tasks Enqueuer (when enabling the queue)

## One-shot deploy

From the repository root:

```bash
# Optional: provision buckets, Cloud SQL, secrets, IAM, Cloud Tasks queue
chmod +x deploy/provision-foundation.sh deploy/deploy-cloudrun.sh
./deploy/provision-foundation.sh

# Deploy API + web
export CLOUDSQL_INSTANCE=... RAW_BUCKET=... EXPORTS_BUCKET=...
./deploy/deploy-cloudrun.sh
```

```powershell
# Windows PowerShell (requires gcloud)
$env:CLOUDSQL_INSTANCE="..."; $env:RAW_BUCKET="..."; $env:EXPORTS_BUCKET="..."
.\deploy\deploy-cloudrun.ps1
```

The script:

1. Enables required APIs
2. Builds and pushes both images to Artifact Registry
3. Runs `alembic upgrade head` as a one-off Cloud Run Job
4. Deploys `translation-api` with Cloud SQL, secrets, concurrency/max-instance caps
5. Deploys `translation-web` with `NEXT_PUBLIC_API_URL` baked at build time

## Smoke test

```bash
curl -sS "$API_URL/health"
curl -sS "$API_URL/healthz"
```

Then open the web URL and exercise upload → translate-segment / translate-project.

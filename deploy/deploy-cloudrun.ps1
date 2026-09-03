# Portable Cloud Run deploy for translation-api + translation-web (PowerShell).
# Run from repo root in an authenticated gcloud environment.
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$env:CLOUDSDK_CORE_DISABLE_PROMPTS = "1"

$RootDir = Split-Path -Parent $PSScriptRoot
if (-not $RootDir) { $RootDir = (Get-Location).Path }
Set-Location $RootDir

$ProjectId = if ($env:PROJECT_ID) { $env:PROJECT_ID } else { "project-794c406e-c0ab-4a50-8e9" }
$Region = if ($env:REGION) { $env:REGION } else { "asia-south1" }
$Repo = if ($env:ARTIFACT_REPO) { $env:ARTIFACT_REPO } else { "translation" }
$ApiService = if ($env:API_SERVICE) { $env:API_SERVICE } else { "translation-api" }
$WebService = if ($env:WEB_SERVICE) { $env:WEB_SERVICE } else { "translation-web" }
$RuntimeSa = if ($env:RUNTIME_SA) { $env:RUNTIME_SA } else { "globesync@$ProjectId.iam.gserviceaccount.com" }
$CloudSqlInstance = if ($env:CLOUDSQL_INSTANCE) { $env:CLOUDSQL_INSTANCE } else { "${ProjectId}:${Region}:translation-pg" }
$RawBucket = if ($env:RAW_BUCKET) { $env:RAW_BUCKET } else { "${ProjectId}-media-raw" }
$ExportsBucket = if ($env:EXPORTS_BUCKET) { $env:EXPORTS_BUCKET } else { "${ProjectId}-media-exports" }
$EnvFile = if ($env:ENV_FILE) { $env:ENV_FILE } else { "deploy/cloudrun.env.yaml" }

$ApiConcurrency = if ($env:API_CONCURRENCY) { $env:API_CONCURRENCY } else { "10" }
$ApiMaxInstances = if ($env:API_MAX_INSTANCES) { $env:API_MAX_INSTANCES } else { "8" }
$ApiMinInstances = if ($env:API_MIN_INSTANCES) { $env:API_MIN_INSTANCES } else { "0" }
$ApiTimeout = if ($env:API_TIMEOUT) { $env:API_TIMEOUT } else { "300" }

gcloud config set project $ProjectId

Write-Host "==> Enabling APIs"
gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  sqladmin.googleapis.com `
  secretmanager.googleapis.com `
  storage.googleapis.com `
  cloudtasks.googleapis.com `
  cloudbuild.googleapis.com `
  iamcredentials.googleapis.com

Write-Host "==> Ensuring Artifact Registry repository"
$repoExists = $true
try { gcloud artifacts repositories describe $Repo --location=$Region | Out-Null } catch { $repoExists = $false }
if (-not $repoExists) {
    gcloud artifacts repositories create $Repo `
      --repository-format=docker `
      --location=$Region `
      --description="Translation platform images"
}

try {
    $Tag = (git rev-parse --short HEAD).Trim()
} catch {
    $Tag = Get-Date -Format "yyyyMMddHHmm"
}

$ApiImage = "$Region-docker.pkg.dev/$ProjectId/$Repo/${ApiService}:$Tag"
$WebImage = "$Region-docker.pkg.dev/$ProjectId/$Repo/${WebService}:$Tag"

Write-Host "==> Building API image: $ApiImage"
$ApiBuild = @"
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-t', '$ApiImage', '-f', 'backend/Dockerfile', '.']
images:
  - $ApiImage
"@
$TmpApiBuild = Join-Path $env:TEMP "translation-cloudbuild-api.yaml"
[System.IO.File]::WriteAllText($TmpApiBuild, $ApiBuild)
gcloud builds submit --config $TmpApiBuild --timeout=2400s .
if ($LASTEXITCODE -ne 0) { throw "API image build failed with exit $LASTEXITCODE" }

Write-Host "==> Running Alembic migrations (one-off Cloud Run Job)"
$JobName = "translation-migrate"
gcloud run jobs delete $JobName --region=$Region --quiet 2>$null
gcloud run jobs create $JobName `
  --image=$ApiImage `
  --region=$Region `
  --service-account=$RuntimeSa `
  --set-cloudsql-instances=$CloudSqlInstance `
  --set-secrets="DATABASE_URL=translation-database-url:latest,SYNC_DATABASE_URL=translation-sync-database-url:latest,JWT_SECRET_KEY=translation-jwt-secret:latest" `
  --env-vars-file=$EnvFile `
  --command="alembic" `
  --args="upgrade,head" `
  --max-retries=0 `
  --task-timeout=600
if ($LASTEXITCODE -ne 0) { throw "Migration job creation failed with exit $LASTEXITCODE" }
gcloud run jobs execute $JobName --region=$Region --wait
if ($LASTEXITCODE -ne 0) { throw "Alembic migration job failed with exit $LASTEXITCODE" }

Write-Host "==> Deploying $ApiService"
gcloud run deploy $ApiService `
  --image=$ApiImage `
  --region=$Region `
  --platform=managed `
  --service-account=$RuntimeSa `
  --allow-unauthenticated `
  --port=8080 `
  --timeout=$ApiTimeout `
  --concurrency=$ApiConcurrency `
  --min-instances=$ApiMinInstances `
  --max-instances=$ApiMaxInstances `
  --cpu=1 `
  --memory=1Gi `
  --add-cloudsql-instances=$CloudSqlInstance `
  --set-secrets="DATABASE_URL=translation-database-url:latest,SYNC_DATABASE_URL=translation-sync-database-url:latest,JWT_SECRET_KEY=translation-jwt-secret:latest" `
  --env-vars-file=$EnvFile

$ApiUrl = gcloud run services describe $ApiService --region=$Region --format="value(status.url)"
Write-Host "API URL: $ApiUrl"

gcloud run services update $ApiService `
  --region=$Region `
  --update-env-vars="CLOUD_TASKS_TARGET_URL=$ApiUrl,INTERNAL_TASKS_AUDIENCE=$ApiUrl,GCS_BUCKET_NAME=$RawBucket,GCS_EXPORTS_BUCKET=$ExportsBucket"

Write-Host "==> Building web image with NEXT_PUBLIC_API_URL=$ApiUrl"
$Cloudbuild = @"
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '--build-arg', 'NEXT_PUBLIC_API_URL=$ApiUrl', '-t', '$WebImage', '-f', 'frontend/Dockerfile', '.']
images:
  - $WebImage
"@
$TmpBuild = Join-Path $env:TEMP "translation-cloudbuild-web.yaml"
[System.IO.File]::WriteAllText($TmpBuild, $Cloudbuild)
gcloud builds submit --config $TmpBuild --timeout=2400s .
if ($LASTEXITCODE -ne 0) { throw "Web image build failed with exit $LASTEXITCODE" }

Write-Host "==> Deploying $WebService"
gcloud run deploy $WebService `
  --image=$WebImage `
  --region=$Region `
  --platform=managed `
  --allow-unauthenticated `
  --port=8080 `
  --min-instances=0 `
  --max-instances=5 `
  --cpu=1 `
  --memory=512Mi `
  --set-env-vars="NODE_ENV=production"

$WebUrl = gcloud run services describe $WebService --region=$Region --format="value(status.url)"
Write-Host "Web URL: $WebUrl"

Write-Host "==> Updating API CORS allow-list"
gcloud run services update $ApiService `
  --region=$Region `
  --update-env-vars="ALLOWED_ORIGINS=[`"$WebUrl`"]"

Write-Host "==> Smoke checks"
Invoke-RestMethod "$ApiUrl/health" | ConvertTo-Json -Compress
try { Invoke-RestMethod "$ApiUrl/healthz" | ConvertTo-Json -Compress } catch { Write-Warning $_ }

Write-Host "Deploy complete."
Write-Host "  API: $ApiUrl"
Write-Host "  Web: $WebUrl"
Write-Host "Enable CLOUD_TASKS_ENABLED=true after creating the translation-jobs queue."

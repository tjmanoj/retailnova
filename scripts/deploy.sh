#!/usr/bin/env bash
# Deploy RetailNova: backend to Cloud Run (via Cloud Build + Artifact Registry), then the web UI to Firebase Hosting.
# Usage: scripts/deploy.sh [backend|web|all]   (default: all)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh

TARGET="${1:-all}"
ACCOUNT="$(gcloud config get account 2>/dev/null)"
if [[ "$ACCOUNT" != "manojtofficial@gmail.com" ]]; then
  echo "Refusing to deploy: gcloud account is '$ACCOUNT'." >&2
  exit 1
fi

PROJECT="retailnova-ai"
SERVICE="retailnova-api"
IMAGE="asia-south1-docker.pkg.dev/${PROJECT}/retailnova/${SERVICE}:$(git rev-parse --short HEAD)-$(date +%H%M%S)"
SA="retailnova-run@${PROJECT}.iam.gserviceaccount.com"

deploy_backend() {
  echo "==> Building ${IMAGE}"
  gcloud builds submit backend --tag "$IMAGE" --region="$REGION" --project "$PROJECT" --quiet
  echo "==> Deploying Cloud Run service ${SERVICE}"
  gcloud run deploy "$SERVICE" \
    --image="$IMAGE" --region="$REGION" --project "$PROJECT" \
    --service-account="$SA" --allow-unauthenticated \
    --cpu=1 --memory=1Gi --concurrency=40 --max-instances=5 --min-instances=0 \
    --timeout=300 --cpu-boost --session-affinity \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,BQ_DATASET=${BQ_DATASET},DEMO_TODAY=2026-10-18" \
    --quiet
}

deploy_web() {
  echo "==> Building web"
  (cd web && npm ci --no-audit --no-fund && npm run build)
  echo "==> Deploying Firebase Hosting + Firestore rules"
  firebase deploy --only hosting,firestore:rules --project "$PROJECT" --non-interactive
}

case "$TARGET" in
  backend) deploy_backend ;;
  web) deploy_web ;;
  all) deploy_backend; deploy_web ;;
  *) echo "Unknown target: $TARGET" >&2; exit 2 ;;
esac
echo "==> Done: https://${PROJECT}.web.app"

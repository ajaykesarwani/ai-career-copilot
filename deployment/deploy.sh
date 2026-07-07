#!/usr/bin/env bash
# ── Deploy AI Career Copilot to Google Cloud Run ──────────────────────────────
# Prerequisites:
#   gcloud CLI installed and authenticated (gcloud auth login)
#   GEMINI_API_KEY set in project-root .env or exported in your shell
#   Docker is NOT required locally — gcloud builds submit builds it in the cloud
#
# Usage (from anywhere — the script locates the project root itself):
#   chmod +x deployment/deploy.sh
#   ./deployment/deploy.sh

set -euo pipefail

# Resolve paths relative to THIS script, not the caller's working directory,
# so `./deployment/deploy.sh` behaves the same whether run from the project
# root, from inside deployment/, or via an absolute path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE_NAME="ai-career-copilot"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Load .env from the project root if present
if [ -f "$ROOT_DIR/.env" ]; then
  set -a; source "$ROOT_DIR/.env"; set +a
fi

API_KEY="${GEMINI_API_KEY:-}"
if [ -z "$API_KEY" ]; then
  echo "❌ GEMINI_API_KEY is not set. Add it to .env or export it."
  echo "   Get your key at: https://aistudio.google.com/app/apikey"
  exit 1
fi

if [ "$PROJECT_ID" = "your-gcp-project-id" ]; then
  echo "❌ GCP_PROJECT_ID is not set. Export it first:"
  echo "   export GCP_PROJECT_ID=your-actual-project-id"
  exit 1
fi

GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"

echo "✦ AI Career Copilot — Cloud Run Deployment"
echo "  Project:  $PROJECT_ID"
echo "  Region:   $REGION"
echo "  Service:  $SERVICE_NAME"
echo "  Model:    $GEMINI_MODEL"
echo ""

# Step 1: Build frontend (Cloud Build also does this again inside the
# Docker multi-stage build; building it here too lets you catch
# frontend errors immediately instead of waiting on a remote build).
echo "📦 Building frontend..."
(cd "$ROOT_DIR/frontend" && npm install --silent && npm run build --silent)
echo "✅ Frontend built → frontend/dist/"

# Step 2: Build & push Docker image (build context = project root)
echo "🐳 Building Docker image via Cloud Build..."
gcloud builds submit \
  --tag "$IMAGE" \
  --project "$PROJECT_ID" \
  "$ROOT_DIR"
echo "✅ Image pushed → $IMAGE"

# Step 3: Deploy to Cloud Run
# No --port is passed: the container listens on $PORT (Cloud Run injects
# PORT=8080 by default) with a fallback of 8000 for local/docker-compose use.
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --max-instances 10 \
  --timeout 60 \
  --set-env-vars "GEMINI_API_KEY=${API_KEY},GEMINI_MODEL=${GEMINI_MODEL},GROQ_API_KEY=${GROQ_API_KEY:-},GROQ_MODEL=${GROQ_MODEL:-openai/gpt-oss-120b},ADZUNA_APP_ID=${ADZUNA_APP_ID:-},ADZUNA_APP_KEY=${ADZUNA_APP_KEY:-},GITHUB_TOKEN=${GITHUB_TOKEN:-},ALLOWED_ORIGINS=*" \
  --quiet

# Step 4: Get URL
URL=$(gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "value(status.url)")

echo ""
echo "✅ Deployed successfully!"
echo "🌐 URL: $URL"
echo ""
echo "Next steps:"
echo "  • Visit \$URL to test your deployment"
echo "  • ALLOWED_ORIGINS is set to * above for convenience — tighten it to"
echo "    your actual frontend origin once you know it (see backend/main.py)"
echo "  • Set a custom domain in Cloud Run console if desired"

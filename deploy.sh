#!/bin/bash
# Deploy Fleming OMR API para Google Cloud Run
# Uso: bash deploy.sh

set -euo pipefail

PROJECT_ID="corretorflemingv2"
SERVICE_NAME="fleming-omr"
REGION="southamerica-east1"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🔨 Building Docker image..."
gcloud builds submit --tag "${IMAGE}" . --quiet

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --memory 1Gi \
  --cpu 2 \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars "FLEMING_API_TOKEN=fleming-token-2025-acafe" \
  --allow-unauthenticated \
  --quiet

echo ""
echo "✅ Deploy concluído!"
echo "URL: https://${SERVICE_NAME}-661476378860.${REGION}.run.app"
echo ""
echo "Teste rápido:"
echo "  curl https://${SERVICE_NAME}-661476378860.${REGION}.run.app/health"

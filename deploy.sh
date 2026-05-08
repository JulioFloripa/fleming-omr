#!/bin/bash
set -euo pipefail

PROJECT_ID="corretorflemingv2"
SERVICE_NAME="fleming-omr"
REGION="southamerica-east1"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🔨 Building..."
gcloud builds submit --tag "${IMAGE}" . --quiet

echo "🚀 Deploying..."
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

URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format 'value(status.url)')
echo ""
echo "✅ Deploy concluído!"
echo "URL: ${URL}"
echo ""
echo "Teste:"
echo "  curl -s ${URL}/health -H 'X-Fleming-Token: fleming-token-2025-acafe'"

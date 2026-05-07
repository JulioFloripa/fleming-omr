#!/bin/bash
set -e
PROJECT="corretorflemingv2"
REGION="southamerica-east1"
SERVICE="fleming-omr"
IMAGE="gcr.io/${PROJECT}/${SERVICE}"
echo "🚀 Deploy Fleming OMR → Cloud Run"
cd ~/fleming-omr
gcloud config set project "$PROJECT"
echo "🏗️  Build..."
gcloud builds submit --tag "$IMAGE" --timeout=600s --quiet
echo "☁️  Deploy..."
gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" \
  --platform managed --allow-unauthenticated \
  --memory 1Gi --cpu 2 --timeout 120 \
  --max-instances 5 --min-instances 0 --port 8080 --quiet
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format="value(status.url)")
echo ""; echo "✅ Deploy OK!"
echo "   URL:  $URL"
echo "   Docs: $URL/docs"
echo "   Teste: curl -X POST '$URL/api/v1/scan' -F 'file=@samples/julio.jpg'"

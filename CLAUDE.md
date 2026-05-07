# CLAUDE.md — Briefing do Projeto Fleming OMR

## O que é
API Python (FastAPI) de leitura óptica de gabaritos (OMR) para o Colégio Fleming.
Roda no Google Cloud Run. Integra com frontend Lovable (React + Supabase).

## Estrutura
```
scanner/omr_reader.py        → Motor OMR (OpenCV, detecção de bolhas/marcadores)
api/main.py                  → FastAPI endpoints REST
generator/sheet_generator.py → Gerador de PDFs (reportlab + qrcode)
Dockerfile                   → Deploy no Cloud Run
requirements.txt             → Dependências Python
```

## Problema atual
A API lê apenas Q1-Q20 (1º bloco) e ignora Q21-Q63 em imagens de baixa
qualidade (WhatsApp, fotos de celular). Com imagens simuladas (300 DPI,
perfeitas), lê 63/63.

### Causa raiz
O método `_compute_block_boundaries` no `scanner/omr_reader.py` não consegue
detectar os marcadores internos de 4mm em imagens comprimidas/reduzidas,
e o fallback por histograma de bolhas não separa os 4 blocos corretamente.

### O que precisa ser feito
1. Tornar a detecção de blocos robusta para imagens de celular/WhatsApp
2. Adicionar warp de perspectiva usando os 4 fiduciais de canto (corrigir skew)
3. Testar com imagens reais (não simuladas)
4. O gabarito ACAFE tem: 63 questões, 4 alternativas (A,B,C,D), 4 blocos de ~16-20 questões

## Cloud Run
- URL: https://fleming-omr-661476378860.southamerica-east1.run.app
- Token: Header `X-Fleming-Token: fleming-token-2025-acafe`
- Projeto GCP: corretorflemingv2
- Região: southamerica-east1

## Deploy
```bash
gcloud builds submit --tag gcr.io/corretorflemingv2/fleming-omr . --quiet
gcloud run deploy fleming-omr \
  --image gcr.io/corretorflemingv2/fleming-omr \
  --platform managed --region southamerica-east1 \
  --memory 1Gi --cpu 2 --timeout 300 \
  --set-env-vars "FLEMING_API_TOKEN=fleming-token-2025-acafe" \
  --allow-unauthenticated --quiet
```

## Teste
```bash
# Health
curl -s https://fleming-omr-661476378860.southamerica-east1.run.app/health

# Scan com imagem (FormData)
curl -s -X POST \
  -H "X-Fleming-Token: fleming-token-2025-acafe" \
  -F "files=@imagem_teste.jpg" \
  -F 'config={"total_questions":63,"alternatives":["A","B","C","D"]}' \
  https://fleming-omr-661476378860.southamerica-east1.run.app/scan-batch | python3 -m json.tool
```

## Constantes físicas (gerador ↔ scanner)
- FIDUCIAL_SIZE = 8mm (quadrados pretos nos 4 cantos)
- INNER_MARKER_SIZE = 4mm (quadrados de calibração nos blocos)
- BUBBLE_RADIUS = 3.5mm
- BUBBLE_SPACING = 8.5mm horizontal
- ROW_SPACING = 8.0mm vertical
- marker_x = x_col + 14mm + (n_alts-1) * BUBBLE_SPACING / 2

## Convenções
- Python 3.11, type hints, docstrings em português
- Testes locais: `python3 -m pytest tests/`
- O scanner aceita path de arquivo (não bytes direto)
- OMRResult.answers é dict[int, str] → {1: "A", 2: "C", ...}

# CLAUDE.md — Fleming OMR v5

## Resumo
API Python (FastAPI) de leitura óptica de gabaritos (OMR) para o Colégio Fleming.
Template ACAFE: 63 questões (4 alternativas) + língua estrangeira.
Deploy: Google Cloud Run. Frontend: Lovable (React + Supabase).

## Arquitetura — Coordenadas Absolutas + Warp por Fiduciais

```
app/config.py               → Geometria central (mm → px), fonte única de verdade
                             ↙              ↘
generator/sheet_generator.py     scanner/omr_reader.py
(gera PDF com bolhas em X,Y)     (warp por fiduciais + leitura em X,Y)
                             ↘              ↙
                              api/main.py → FastAPI REST
```

## Calibração (valores reais de HoughCircles no PDF renderizado a 300 DPI)
- Q1.A = (442, 1108)px, raio = 41px
- Spacing X = ~100px (8.5mm), Spacing Y = 98px (8.3mm)
- 252 bolhas = 63 × 4

## Constantes (app/config.py)
- PAGE: 210×297mm (A4), DPI referência: 300
- FIDUCIAL_SIZE = 8mm, FIDUCIAL_MARGIN = 5mm
- BUBBLE_RADIUS = 3.5mm (41px), SAMPLE_RADIUS_MULT = 0.85 (35px)
- BUBBLE_SPACING_X = 8.5mm, ROW_SPACING_Y = 8.3mm
- MARGIN_LEFT = 37.5mm, BLOCK_PITCH = 45mm
- HEADER_HEIGHT = 77.5mm, FIRST_ROW_Y = 93.8mm
- Blocos: [20, 20, 20, 3] questões
- Línguas: Inglês, Espanhol (área separada no cabeçalho, y=50mm)
- Thresholds: MIN_FILL=0.08, RELATIVE_RATIO=1.25, AMBIGUOUS=0.88

## Scanner — estratégia de warp (prioridade)
1. Detecta 4 fiduciais (quadrados pretos) → warp preciso
2. Fallback: contorno da página → warp aproximado
3. Último recurso: resize simples

## Deploy
```bash
bash deploy.sh
```

## Teste
```bash
python3 test_reader.py                    # config + gerador
python3 test_reader.py samples/julio.jpg  # scan real
```

## Endpoints
- GET  /health
- GET  /grid
- POST /scan-batch (multipart files)
- POST /scan-batch-url (JSON com URLs)
- POST /generate-batch (JSON com lista de alunos)

## Token
Header: `X-Fleming-Token: fleming-token-2025-acafe`

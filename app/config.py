"""
Config.py — agora apenas re-exporta de layout.py + configs de API.
Geometria centralizada em layout.py.
"""

# Re-exporta tudo de layout para manter compatibilidade
from .layout import *

# ── Configurações da API (não pertencem ao layout) ──
API_HOST = "0.0.0.0"
API_PORT = 8080
MAX_UPLOAD_SIZE_MB = 10
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".pdf"}

# Cloud Run
CLOUD_RUN_URL = "https://fleming-omr-661476378860.southamerica-east1.run.app"
GCP_PROJECT = "corretorflemingv2"
GCP_REGION = "southamerica-east1"
SERVICE_NAME = "fleming-omr"

"""
config.py — Geometria central do gabarito Fleming OMR (template ACAFE).

FONTE ÚNICA DE VERDADE para posições de bolhas.
Valores calibrados a partir de HoughCircles no PDF renderizado a 300 DPI:
  Q1.A = (442, 1108), raio = 41px, spacing_y = 98px

Unidades base: milímetros (mm).
Conversão: px = mm * DPI / 25.4
"""

from typing import Dict, List, Tuple

# =============================================================================
# PÁGINA
# =============================================================================
PAGE_W_MM = 210.0
PAGE_H_MM = 297.0
REFERENCE_DPI = 300

# =============================================================================
# FIDUCIAIS (quadrados pretos nos 4 cantos — âncoras para warp)
# =============================================================================
FIDUCIAL_SIZE_MM = 8.0
FIDUCIAL_MARGIN_MM = 5.0

FIDUCIAL_CENTERS_MM = [
    (FIDUCIAL_MARGIN_MM + FIDUCIAL_SIZE_MM / 2,
     FIDUCIAL_MARGIN_MM + FIDUCIAL_SIZE_MM / 2),
    (PAGE_W_MM - FIDUCIAL_MARGIN_MM - FIDUCIAL_SIZE_MM / 2,
     FIDUCIAL_MARGIN_MM + FIDUCIAL_SIZE_MM / 2),
    (FIDUCIAL_MARGIN_MM + FIDUCIAL_SIZE_MM / 2,
     PAGE_H_MM - FIDUCIAL_MARGIN_MM - FIDUCIAL_SIZE_MM / 2),
    (PAGE_W_MM - FIDUCIAL_MARGIN_MM - FIDUCIAL_SIZE_MM / 2,
     PAGE_H_MM - FIDUCIAL_MARGIN_MM - FIDUCIAL_SIZE_MM / 2),
]

# =============================================================================
# BOLHAS DE RESPOSTA
# =============================================================================
BUBBLE_RADIUS_MM = 3.5       # raio (calibrado: 41px @ 300 DPI)
BUBBLE_SPACING_X_MM = 8.5    # entre centros A→B, B→C, C→D
ROW_SPACING_Y_MM = 8.3       # entre linhas (calibrado: 98px @ 300 DPI)

# =============================================================================
# LAYOUT ACAFE — 63 questões em 4 blocos
# =============================================================================
TOTAL_QUESTIONS = 63
ALTERNATIVES = ["A", "B", "C", "D"]
QUESTIONS_PER_BLOCK = 20

_MARGIN_LEFT_MM = 37.5       # centro da bolha A do bloco 1 (calibrado: 442px)
_BLOCK_PITCH_MM = 45.0       # distância entre blocos

BLOCK_A_X_MM = [_MARGIN_LEFT_MM + i * _BLOCK_PITCH_MM for i in range(4)]
BLOCK_QUESTION_COUNTS = [20, 20, 20, 3]

HEADER_HEIGHT_MM = 77.5      # calibrado para Q1.y = 1108px
FIRST_ROW_Y_MM = HEADER_HEIGHT_MM + FIDUCIAL_SIZE_MM + ROW_SPACING_Y_MM

# =============================================================================
# LÍNGUA ESTRANGEIRA (área separada no cabeçalho)
# =============================================================================
FOREIGN_LANGUAGES = ["Inglês", "Espanhol"]
LANG_AREA_Y_MM = 50.0        # posição Y da linha de língua
LANG_BUBBLE_X_START_MM = 58.0 # X do centro da primeira bolha de língua
LANG_BUBBLE_SPACING_MM = 30.0 # distância entre bolhas de língua
LANG_BUBBLE_RADIUS_MM = 3.0   # raio menor que as bolhas de resposta

# =============================================================================
# THRESHOLDS DE LEITURA (relativos)
# =============================================================================
MIN_FILL_ABSOLUTE = 0.08
RELATIVE_RATIO = 1.25
AMBIGUOUS_THRESHOLD = 0.88
SAMPLE_RADIUS_MULT = 0.85    # fração do raio real para amostragem

# =============================================================================
# CONVERSÕES
# =============================================================================

def mm_to_px(val: float, dpi: int = REFERENCE_DPI) -> float:
    return val * dpi / 25.4

def px_to_mm(val: float, dpi: int = REFERENCE_DPI) -> float:
    return val * 25.4 / dpi

# =============================================================================
# COORDENADAS DE BOLHAS — RESPOSTAS
# =============================================================================

def get_all_bubble_centers_mm() -> Dict[int, Dict[str, Tuple[float, float]]]:
    centers: Dict[int, Dict[str, Tuple[float, float]]] = {}
    q = 1
    for bi, count in enumerate(BLOCK_QUESTION_COUNTS):
        bx = BLOCK_A_X_MM[bi]
        for row in range(count):
            y = FIRST_ROW_Y_MM + row * ROW_SPACING_Y_MM
            alts = {}
            for ai, alt in enumerate(ALTERNATIVES):
                x = bx + ai * BUBBLE_SPACING_X_MM
                alts[alt] = (round(x, 2), round(y, 2))
            centers[q] = alts
            q += 1
    return centers

def get_all_bubble_centers_px(dpi: int = REFERENCE_DPI) -> Dict[int, Dict[str, Tuple[int, int]]]:
    mm = get_all_bubble_centers_mm()
    return {
        q: {a: (int(mm_to_px(x, dpi)), int(mm_to_px(y, dpi)))
            for a, (x, y) in alts.items()}
        for q, alts in mm.items()
    }

# =============================================================================
# COORDENADAS DE BOLHAS — LÍNGUA ESTRANGEIRA
# =============================================================================

def get_language_centers_mm() -> Dict[str, Tuple[float, float]]:
    return {
        lang: (
            round(LANG_BUBBLE_X_START_MM + i * LANG_BUBBLE_SPACING_MM, 2),
            round(LANG_AREA_Y_MM, 2),
        )
        for i, lang in enumerate(FOREIGN_LANGUAGES)
    }

def get_language_centers_px(dpi: int = REFERENCE_DPI) -> Dict[str, Tuple[int, int]]:
    mm = get_language_centers_mm()
    return {
        lang: (int(mm_to_px(x, dpi)), int(mm_to_px(y, dpi)))
        for lang, (x, y) in mm.items()
    }

# =============================================================================
# UTILIDADES
# =============================================================================

def get_warp_dimensions(dpi: int = REFERENCE_DPI) -> Tuple[int, int]:
    return (int(mm_to_px(PAGE_W_MM, dpi)), int(mm_to_px(PAGE_H_MM, dpi)))

def get_fiducial_corners_px(dpi: int = REFERENCE_DPI) -> List[Tuple[int, int]]:
    return [(int(mm_to_px(x, dpi)), int(mm_to_px(y, dpi)))
            for x, y in FIDUCIAL_CENTERS_MM]

def export_grid_json(dpi: int = REFERENCE_DPI) -> dict:
    return {
        "dpi": dpi,
        "page_size_px": list(get_warp_dimensions(dpi)),
        "total_questions": TOTAL_QUESTIONS,
        "alternatives": ALTERNATIVES,
        "bubble_radius_px": int(mm_to_px(BUBBLE_RADIUS_MM, dpi)),
        "sample_radius_px": int(mm_to_px(BUBBLE_RADIUS_MM, dpi) * SAMPLE_RADIUS_MULT),
        "fiducials_px": get_fiducial_corners_px(dpi),
        "languages": get_language_centers_px(dpi),
        "questions": {
            str(q): {a: list(p) for a, p in alts.items()}
            for q, alts in get_all_bubble_centers_px(dpi).items()
        },
    }


if __name__ == "__main__":
    c = get_all_bubble_centers_px()
    print(f"Questões: {len(c)}")
    for q in [1, 21, 41, 61, 63]:
        if q in c: print(f"  Q{q}: {c[q]}")
    l = get_language_centers_px()
    print(f"Línguas: {l}")
    print(f"Raio amostragem: {int(mm_to_px(BUBBLE_RADIUS_MM) * SAMPLE_RADIUS_MULT)}px")
    import json
    print(f"Grid JSON: {len(json.dumps(export_grid_json()))} bytes")

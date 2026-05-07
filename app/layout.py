"""
Módulo centralizado de geometria do gabarito Fleming.
Fonte única de verdade — tanto o generator quanto o reader importam daqui.

Derivado diretamente do sheet_generator.py:
  HEADER_HEIGHT = 75mm
  ROW_SPACING = 8.0mm
  grid_top_y = page_h - HEADER_HEIGHT
  row_y = grid_top_y - (q_offset + 1) * ROW_SPACING
  → primeira bolha: 297 - 75 - 8 = 214mm do fundo = 83mm do topo
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

# ── Constantes de página ──
DPI = 300
MM_TO_PX = DPI / 25.4   # 11.811 px/mm
PAGE_W_MM = 210
PAGE_H_MM = 297
PAGE_W_PX = int(PAGE_W_MM * MM_TO_PX)   # 2480
PAGE_H_PX = int(PAGE_H_MM * MM_TO_PX)   # 3507

# ── Geometria derivada do generator ──
HEADER_HEIGHT_MM = 75.0
ROW_SPACING_MM = 8.0       # espaçamento real entre linhas de bolhas
START_Y_MM = 83.0           # Y da Q1 (topo da página) = HEADER_HEIGHT + ROW_SPACING

# ── Bolhas ──
BUBBLE_RADIUS_MM = 2.0      # raio da bolha (diâmetro ~4mm)
BUBBLE_GAP_H_MM = 6.5       # espaçamento horizontal entre centros A→B→C→D
BUBBLE_GAP_V_MM = 8.0       # espaçamento vertical entre questões (= ROW_SPACING)

# ── Fiduciais de canto ──
FIDUCIAL_SIZE_MM = 8
FIDUCIAL_INSET_MM = 10
FIDUCIALS_MM = [
    (FIDUCIAL_INSET_MM + FIDUCIAL_SIZE_MM/2,
     FIDUCIAL_INSET_MM + FIDUCIAL_SIZE_MM/2),                                    # TL
    (PAGE_W_MM - FIDUCIAL_INSET_MM - FIDUCIAL_SIZE_MM/2,
     FIDUCIAL_INSET_MM + FIDUCIAL_SIZE_MM/2),                                    # TR
    (FIDUCIAL_INSET_MM + FIDUCIAL_SIZE_MM/2,
     PAGE_H_MM - FIDUCIAL_INSET_MM - FIDUCIAL_SIZE_MM/2),                        # BL
    (PAGE_W_MM - FIDUCIAL_INSET_MM - FIDUCIAL_SIZE_MM/2,
     PAGE_H_MM - FIDUCIAL_INSET_MM - FIDUCIAL_SIZE_MM/2),                        # BR
]

# ── Alternativas ──
ALTERNATIVES = ["A", "B", "C", "D"]
NUM_ALTERNATIVES = len(ALTERNATIVES)

# ── Blocos de questões ──
# Cada bloco: (nome, q_inicio, q_fim, origin_x_mm do centro da bolha A)
# origin_x derivado dos dados do scan: bloco1 em x~508px = 43.0mm
@dataclass
class BlockLayout:
    name: str
    start_q: int
    end_q: int
    origin_x_mm: float      # X do centro da bolha A

    @property
    def num_questions(self) -> int:
        return self.end_q - self.start_q + 1

    @property
    def labels(self) -> List[str]:
        return [f"q{i}" for i in range(self.start_q, self.end_q + 1)]

# origin_x calibrado pelo scan: [508, 1027, 1548, 2069] px
# = [43.0, 86.9, 131.1, 175.1] mm
BLOCKS = [
    BlockLayout("Block1_Q1_Q20",   1, 20, origin_x_mm=43.0),
    BlockLayout("Block2_Q21_Q40", 21, 40, origin_x_mm=87.0),
    BlockLayout("Block3_Q41_Q60", 41, 60, origin_x_mm=131.0),
    BlockLayout("Block4_Q61_Q63", 61, 63, origin_x_mm=175.0),
]

# ── Marcadores internos (por bloco) ──
# Quadrados pretos pequenos no eixo de cada bloco
# Usados para interpolação vertical e eliminação de drift
# Posições em mm do topo da página (estimadas do layout)
INTERNAL_MARKER_SIZE_MM = 3.0

# Cada bloco tem 3 anchors verticais: topo, meio, base
# As Y dos anchors correspondem a linhas específicas de questões
ANCHOR_ROWS = {
    "top":    0,    # alinha com Q1 do bloco
    "mid":   10,    # alinha com Q11 do bloco (meio)
    "bottom": 19,   # alinha com Q20 do bloco (última de 20)
}

def get_anchor_y_mm(anchor_name: str) -> float:
    """Retorna Y esperado (mm) de um anchor baseado na geometria do generator."""
    row = ANCHOR_ROWS[anchor_name]
    return START_Y_MM + row * BUBBLE_GAP_V_MM

# ── Thresholds de leitura ──
FILLED_THRESHOLD = 0.35
AMBIGUOUS_THRESHOLD = 0.25

# ── Funções de conversão ──
def mm_to_px(v: float) -> int:
    return int(round(v * MM_TO_PX))

def px_to_mm(v: float) -> float:
    return v / MM_TO_PX

# ── Cálculo de centros das bolhas (sem interpolação) ──
def get_bubble_center_px(block: BlockLayout, q_index: int, alt_index: int) -> Tuple[int, int]:
    """Centro (x, y) em pixels. q_index é 0-based dentro do bloco."""
    x_mm = block.origin_x_mm + alt_index * BUBBLE_GAP_H_MM
    y_mm = START_Y_MM + q_index * BUBBLE_GAP_V_MM
    return (mm_to_px(x_mm), mm_to_px(y_mm))

def get_all_bubble_centers_px() -> Dict[str, Dict[str, Tuple[int, int]]]:
    """Retorna {label: {alt: (cx, cy)}} para todas as 63 questões."""
    result = {}
    for block in BLOCKS:
        for qi in range(block.num_questions):
            label = f"q{block.start_q + qi}"
            result[label] = {}
            for ai, alt in enumerate(ALTERNATIVES):
                result[label][alt] = get_bubble_center_px(block, qi, ai)
    return result

# ── Centros com interpolação (usando anchors detectados) ──
def interpolate_y(q_index: int, anchors_detected: Dict[str, int],
                  num_questions: int = 20) -> int:
    """
    Interpola Y de uma questão usando anchors detectados.
    anchors_detected: {"top": y_px, "mid": y_px, "bottom": y_px}
    q_index: 0-based dentro do bloco

    Estratégia:
    - Q0-Q10: interpola entre top e mid
    - Q10-Q19: interpola entre mid e bottom
    - Blocos com < 20 questões: usa apenas top e ajuste proporcional
    """
    top_y = anchors_detected.get("top")
    mid_y = anchors_detected.get("mid")
    bot_y = anchors_detected.get("bottom")

    top_row = ANCHOR_ROWS["top"]       # 0
    mid_row = ANCHOR_ROWS["mid"]       # 10
    bot_row = ANCHOR_ROWS["bottom"]    # 19

    # Se temos top e mid e bottom, interpola por segmento
    if top_y is not None and mid_y is not None and bot_y is not None:
        if q_index <= mid_row:
            # Interpola entre top e mid
            t = (q_index - top_row) / (mid_row - top_row) if mid_row != top_row else 0
            return int(round(top_y + t * (mid_y - top_y)))
        else:
            # Interpola entre mid e bottom
            t = (q_index - mid_row) / (bot_row - mid_row) if bot_row != mid_row else 0
            return int(round(mid_y + t * (bot_y - mid_y)))

    # Se temos apenas top e bottom
    elif top_y is not None and bot_y is not None:
        t = (q_index - top_row) / (bot_row - top_row) if bot_row != top_row else 0
        return int(round(top_y + t * (bot_y - top_y)))

    # Se temos apenas top
    elif top_y is not None:
        return int(round(top_y + q_index * mm_to_px(BUBBLE_GAP_V_MM)))

    # Fallback: geometria pura
    return mm_to_px(START_Y_MM + q_index * BUBBLE_GAP_V_MM)

def get_all_centers_interpolated(
    block: BlockLayout,
    anchors: Dict[str, int]
) -> Dict[str, Dict[str, Tuple[int, int]]]:
    """
    Centros de bolhas para um bloco, usando interpolação vertical.
    anchors: {"top": y_px, "mid": y_px, "bottom": y_px}
    """
    result = {}
    for qi in range(block.num_questions):
        label = f"q{block.start_q + qi}"
        y_px = interpolate_y(qi, anchors, block.num_questions)
        result[label] = {}
        for ai, alt in enumerate(ALTERNATIVES):
            x_px = mm_to_px(block.origin_x_mm + ai * BUBBLE_GAP_H_MM)
            result[label][alt] = (x_px, y_px)
    return result

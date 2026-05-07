"""
Motor OMR com interpolação por anchors internos.
Elimina drift vertical usando marcadores detectados por bloco.
"""
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

from .layout import (
    BLOCKS, ALTERNATIVES, FIDUCIALS_MM, FIDUCIAL_SIZE_MM,
    PAGE_W_PX, PAGE_H_PX, BUBBLE_RADIUS_MM, BUBBLE_GAP_V_MM,
    START_Y_MM, BUBBLE_GAP_H_MM, INTERNAL_MARKER_SIZE_MM,
    mm_to_px, px_to_mm,
    get_all_bubble_centers_px, get_all_centers_interpolated,
    interpolate_y, ANCHOR_ROWS,
    FILLED_THRESHOLD, AMBIGUOUS_THRESHOLD,
    BlockLayout,
)

logger = logging.getLogger(__name__)


@dataclass
class BubbleResult:
    question: str
    alternatives: Dict[str, float]
    selected: Optional[str]
    confidence: float
    status: str  # "ok", "blank", "multiple", "ambiguous"


@dataclass
class OMRResult:
    success: bool
    student_id: Optional[str]
    answers: Dict[str, Optional[str]]
    details: List[BubbleResult]
    warnings: List[str]
    stats: Dict[str, int]
    debug_info: Optional[Dict] = None


# ── Detecção de fiduciais de canto ──

def find_fiducials(gray: np.ndarray) -> Optional[np.ndarray]:
    h, w = gray.shape[:2]
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 51, 15
    )
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    min_area, max_area = (w * 0.01)**2, (w * 0.06)**2

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) < 4 or len(approx) > 6:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = bw / max(bh, 1)
        if aspect < 0.6 or aspect > 1.6:
            continue
        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        if area / max(hull_area, 1) < 0.75:
            continue
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        candidates.append((int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"]), area))

    if len(candidates) < 4:
        return None

    corners = [(0,0), (w,0), (0,h), (w,h)]
    fiducials, used = [], set()
    for corner in corners:
        best_dist, best_idx = float('inf'), -1
        for i, (cx, cy, _) in enumerate(candidates):
            if i in used:
                continue
            dist = np.sqrt((cx-corner[0])**2 + (cy-corner[1])**2)
            if dist < best_dist:
                best_dist, best_idx = dist, i
        if best_idx >= 0:
            fiducials.append(candidates[best_idx][:2])
            used.add(best_idx)

    return np.array(fiducials, dtype=np.float32) if len(fiducials) == 4 else None


def align_image(image: np.ndarray, fiducials: np.ndarray) -> np.ndarray:
    dst = np.array([
        [mm_to_px(FIDUCIALS_MM[0][0]), mm_to_px(FIDUCIALS_MM[0][1])],
        [mm_to_px(FIDUCIALS_MM[1][0]), mm_to_px(FIDUCIALS_MM[1][1])],
        [mm_to_px(FIDUCIALS_MM[2][0]), mm_to_px(FIDUCIALS_MM[2][1])],
        [mm_to_px(FIDUCIALS_MM[3][0]), mm_to_px(FIDUCIALS_MM[3][1])],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(fiducials, dst)
    return cv2.warpPerspective(image, M, (PAGE_W_PX, PAGE_H_PX),
                                flags=cv2.INTER_LINEAR,
                                borderValue=(255, 255, 255))


# ── Detecção de marcadores internos ──

def detect_internal_markers(
    gray: np.ndarray,
    block: BlockLayout
) -> Dict[str, int]:
    """
    Detecta marcadores internos (quadrados pretos pequenos) ao longo
    do eixo vertical de um bloco. Retorna {"top": y_px, "mid": y_px, "bottom": y_px}.

    Estratégia: busca regiões escuras densas em uma coluna estreita
    à esquerda do bloco, nas Y esperadas dos anchors.
    """
    h, w = gray.shape[:2]
    marker_r = mm_to_px(INTERNAL_MARKER_SIZE_MM)
    search_margin_y = mm_to_px(5.0)  # ±5mm de tolerância

    # X de busca: à esquerda das bolhas do bloco
    search_x = mm_to_px(block.origin_x_mm) - mm_to_px(10.0)
    search_x = max(marker_r, min(search_x, w - marker_r))

    anchors = {}

    for anchor_name, anchor_row in ANCHOR_ROWS.items():
        if anchor_row >= block.num_questions:
            continue  # bloco com < 20 questões

        expected_y = mm_to_px(START_Y_MM + anchor_row * BUBBLE_GAP_V_MM)

        # Região de busca vertical
        y1 = max(0, expected_y - search_margin_y)
        y2 = min(h, expected_y + search_margin_y)

        # Busca na faixa estreita
        roi = gray[y1:y2, max(0, search_x-marker_r):min(w, search_x+marker_r)]

        if roi.size == 0:
            continue

        # Binariza
        _, bw = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Perfil vertical (média horizontal)
        v_profile = np.mean(bw, axis=1)

        # Encontra pico de escuridão
        if len(v_profile) > 0:
            peak_local = int(np.argmax(v_profile))
            peak_y = y1 + peak_local

            # Só aceita se o pico é suficientemente escuro
            if v_profile[peak_local] > 100:
                anchors[anchor_name] = peak_y
            else:
                # Fallback: usa posição esperada
                anchors[anchor_name] = expected_y
        else:
            anchors[anchor_name] = expected_y

    return anchors


# ── QR Code ──

def read_qr_code(image: np.ndarray) -> Optional[str]:
    try:
        det = cv2.QRCodeDetector()
        data, _, _ = det.detectAndDecode(image)
        if data:
            return data
        h, w = image.shape[:2]
        roi = image[0:int(h*0.2), int(w*0.55):w]
        data, _, _ = det.detectAndDecode(roi)
        if data:
            return data
        try:
            from pyzbar import pyzbar
            for obj in pyzbar.decode(image):
                if obj.type in ('QRCODE', 'QR_CODE'):
                    return obj.data.decode('utf-8')
        except ImportError:
            pass
    except Exception as e:
        logger.error(f"Erro QR: {e}")
    return None


# ── Análise de bolhas ──

def analyze_bubble(gray: np.ndarray, center: Tuple[int, int], radius_px: int) -> float:
    cx, cy = center
    h, w = gray.shape[:2]
    x1, y1 = max(0, cx - radius_px), max(0, cy - radius_px)
    x2, y2 = min(w, cx + radius_px), min(h, cy + radius_px)
    if x2 <= x1 or y2 <= y1:
        return 0.0

    roi = gray[y1:y2, x1:x2]
    rh, rw = roi.shape
    mask = np.zeros((rh, rw), dtype=np.uint8)
    cv2.circle(mask, (rw//2, rh//2), min(rw, rh)//2, 255, -1)
    _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    masked = cv2.bitwise_and(binary, binary, mask=mask)
    total = cv2.countNonZero(mask)
    return cv2.countNonZero(masked) / total if total > 0 else 0.0


def analyze_question(
    gray: np.ndarray,
    question_label: str,
    bubble_centers: Dict[str, Tuple[int, int]]
) -> BubbleResult:
    radius_px = mm_to_px(BUBBLE_RADIUS_MM * 1.1)
    fills = {alt: analyze_bubble(gray, bubble_centers[alt], radius_px)
             for alt in ALTERNATIVES}

    marked = [a for a, v in fills.items() if v >= FILLED_THRESHOLD]
    near = [a for a, v in fills.items() if AMBIGUOUS_THRESHOLD <= v < FILLED_THRESHOLD]

    if len(marked) == 0:
        status = "ambiguous" if near else "blank"
        return BubbleResult(question_label, fills, None,
                            1.0 - max(fills.values()), status)
    elif len(marked) == 1:
        sv = sorted(fills.values(), reverse=True)
        gap = sv[0] - sv[1] if len(sv) > 1 else sv[0]
        return BubbleResult(question_label, fills, marked[0],
                            min(1.0, gap / 0.3 + 0.5), "ok")
    else:
        return BubbleResult(question_label, fills, None, 0.0, "multiple")


# ── Pipeline principal ──

def process_image(image_path: str, debug: bool = False) -> OMRResult:
    warnings = []
    debug_info = {} if debug else None

    # Carrega
    image = cv2.imread(image_path)
    if image is None:
        return OMRResult(False, None, {}, [], ["Não foi possível carregar a imagem"],
                         {"answered": 0, "blank": 0, "multiple": 0, "ambiguous": 0})

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Fiduciais
    fiducials = find_fiducials(gray)
    if fiducials is not None:
        aligned = align_image(image, fiducials)
        gray_aligned = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    else:
        warnings.append("Fiduciais não detectados — usando imagem redimensionada")
        gray_aligned = cv2.resize(gray, (PAGE_W_PX, PAGE_H_PX))
        aligned = cv2.resize(image, (PAGE_W_PX, PAGE_H_PX))

    # QR Code
    student_id = read_qr_code(aligned)
    if not student_id:
        warnings.append("QR Code não detectado")

    # Processa cada bloco com interpolação
    details = []
    answers = {}
    all_anchors = {}

    for block in BLOCKS:
        # Detecta anchors internos para este bloco
        anchors = detect_internal_markers(gray_aligned, block)
        all_anchors[block.name] = anchors

        # Calcula centros com interpolação
        centers = get_all_centers_interpolated(block, anchors)

        # Analisa cada questão
        for qi in range(block.num_questions):
            label = f"q{block.start_q + qi}"
            r = analyze_question(gray_aligned, label, centers[label])
            details.append(r)
            answers[label] = r.selected

    # Stats
    stats = {
        "answered": sum(1 for d in details if d.status == "ok"),
        "blank": sum(1 for d in details if d.status == "blank"),
        "multiple": sum(1 for d in details if d.status == "multiple"),
        "ambiguous": sum(1 for d in details if d.status == "ambiguous"),
    }

    if debug:
        debug_info["fiducials"] = fiducials.tolist() if fiducials is not None else None
        debug_info["anchors"] = {k: v for k, v in all_anchors.items()}
        debug_info["image_shape"] = list(gray_aligned.shape)

    return OMRResult(
        success=stats["answered"] > 0,
        student_id=student_id,
        answers=answers,
        details=details,
        warnings=warnings,
        stats=stats,
        debug_info=debug_info,
    )


def process_image_bytes(image_bytes: bytes, debug: bool = False) -> OMRResult:
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        return process_image(tmp_path, debug)
    finally:
        os.unlink(tmp_path)


def grade_answers(detected: Dict[str, Optional[str]],
                  answer_key: Dict[str, str]) -> Dict:
    correct = [q for q, a in answer_key.items() if detected.get(q) == a]
    blank = [q for q in answer_key if detected.get(q) is None]
    wrong = [q for q in answer_key if q not in correct and q not in blank]
    total = len(answer_key)
    return {
        "score": len(correct), "total": total,
        "percentage": round(len(correct)/total*100, 2) if total else 0,
        "correct": correct, "wrong": wrong, "blank": blank,
    }

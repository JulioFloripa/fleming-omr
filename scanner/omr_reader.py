"""
omr_reader.py — Leitor OMR por coordenadas absolutas.

Fluxo:
  1. QR Code → identifica template + aluno
  2. Detecta 4 fiduciais (quadrados pretos nos cantos)
  3. Warp de perspectiva usando fiduciais como âncora
  4. Leitura direta nas coordenadas do config (threshold relativo)
  5. Leitura da língua estrangeira

Zero HoughCircles. Zero detecção de bolhas.
"""

import json
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

import cv2
import numpy as np

from app.config import (
    ALTERNATIVES,
    AMBIGUOUS_THRESHOLD,
    BUBBLE_RADIUS_MM,
    FIDUCIAL_SIZE_MM,
    FOREIGN_LANGUAGES,
    LANG_BUBBLE_RADIUS_MM,
    MIN_FILL_ABSOLUTE,
    RELATIVE_RATIO,
    SAMPLE_RADIUS_MULT,
    TOTAL_QUESTIONS,
    get_all_bubble_centers_px,
    get_fiducial_corners_px,
    get_language_centers_px,
    get_warp_dimensions,
    mm_to_px,
)


@dataclass
class OMRResult:
    success: bool
    template_id: Optional[str] = None
    student_id: Optional[str] = None
    template_type: Optional[str] = None
    answers: dict = field(default_factory=dict)
    language: Optional[str] = None
    errors: list = field(default_factory=list)
    raw_data: Optional[str] = None
    fill_details: dict = field(default_factory=dict)


# =============================================================================
# QR CODE
# =============================================================================

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    _PYZBAR_OK = True
except ImportError:
    _PYZBAR_OK = False


def decode_qr(gray: np.ndarray) -> Optional[dict]:
    if _PYZBAR_OK:
        for obj in pyzbar_decode(gray):
            try:
                return json.loads(obj.data.decode())
            except Exception:
                pass
    det = cv2.QRCodeDetector()
    ok, info, _, _ = det.detectAndDecodeMulti(gray)
    if ok:
        for s in info:
            if s:
                try:
                    return json.loads(s)
                except Exception:
                    pass
    return None


# =============================================================================
# DETECÇÃO DE FIDUCIAIS (quadrados pretos nos cantos)
# =============================================================================


def _find_fiducials(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    Encontra os 4 quadrados pretos de canto na imagem.
    Busca APENAS nas regioes de canto (20% de cada borda).
    Se 1 canto faltante, estima dos outros 3.
    """
    h, w = gray.shape
    _, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((3, 3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_side = int(min(w, h) * 0.01)
    max_side = int(min(w, h) * 0.06)
    candidates = []
    for cnt in cnts:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw < min_side or ch < min_side: continue
        if cw > max_side or ch > max_side: continue
        aspect = cw / ch
        if aspect < 0.5 or aspect > 2.0: continue
        area = cv2.contourArea(cnt)
        if area < cw * ch * 0.6: continue
        cx = x + cw // 2
        cy = y + ch // 2
        candidates.append((cx, cy, area))
    margin_x = int(w * 0.20)
    margin_y = int(h * 0.20)
    corner_regions = {
        "TL": (0, 0, margin_x, margin_y),
        "TR": (w - margin_x, 0, w, margin_y),
        "BL": (0, h - margin_y, margin_x, h),
        "BR": (w - margin_x, h - margin_y, w, h),
    }
    found = {}
    for name, (x1, y1, x2, y2) in corner_regions.items():
        best = None
        best_area = 0
        for cx, cy, area in candidates:
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                if area > best_area:
                    best = (cx, cy)
                    best_area = area
        if best is not None:
            found[name] = best
    if len(found) < 3: return None
    if len(found) == 3:
        missing = [k for k in ["TL", "TR", "BL", "BR"] if k not in found][0]
        if missing == "TL": found["TL"] = (found["BL"][0], found["TR"][1])
        elif missing == "TR": found["TR"] = (found["BR"][0], found["TL"][1])
        elif missing == "BL": found["BL"] = (found["TL"][0], found["BR"][1])
        elif missing == "BR": found["BR"] = (found["TR"][0], found["BL"][1])
    return np.array([found["TL"], found["TR"], found["BL"], found["BR"]], dtype=np.float32)


# =============================================================================
# WARP DE PERSPECTIVA
# =============================================================================


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 pontos: TL, TR, BR, BL."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1).flatten()
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect


def _find_page_contour(gray: np.ndarray) -> Optional[np.ndarray]:
    """Fallback: encontra contorno retangular da folha."""
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    for lo, hi in [(30, 100), (50, 150), (20, 80)]:
        edges = cv2.Canny(blurred, lo, hi)
        edges = cv2.dilate(edges, None, iterations=2)
        cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
        for cnt in cnts[:10]:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) != 4:
                continue
            if cv2.contourArea(approx) < h * w * 0.15:
                continue
            return approx.reshape(4, 2)
    return None


def warp_to_standard(img: np.ndarray, gray: np.ndarray) -> np.ndarray:
    """
    Warp de perspectiva. Prioridade:
    1. Fiduciais (quadrados pretos) → mais preciso
    2. Contorno da página → fallback
    3. Resize simples → último recurso
    """
    warp_w, warp_h = get_warp_dimensions()
    fid_cfg = get_fiducial_corners_px()

    # Destino: posições dos fiduciais no espaço normalizado
    dst = np.float32([
        fid_cfg[0],  # TL
        fid_cfg[1],  # TR
        fid_cfg[3],  # BR
        fid_cfg[2],  # BL
    ])

    # Tentar fiduciais primeiro
    fid_pts = _find_fiducials(gray)
    if fid_pts is not None:
        src = _order_points(fid_pts)
        M = cv2.getPerspectiveTransform(src, dst)
        return cv2.warpPerspective(img, M, (warp_w, warp_h))

    # Fallback: contorno da página
    page_pts = _find_page_contour(gray)
    if page_pts is not None:
        src = _order_points(page_pts.astype(np.float32))
        dst_page = np.float32([[0, 0], [warp_w, 0], [warp_w, warp_h], [0, warp_h]])
        M = cv2.getPerspectiveTransform(src, dst_page)
        return cv2.warpPerspective(img, M, (warp_w, warp_h))

    # Último recurso: resize
    return cv2.resize(img, (warp_w, warp_h))


# =============================================================================
# LEITOR PRINCIPAL
# =============================================================================


class OMRReader:

    def __init__(
        self,
        min_fill: float = MIN_FILL_ABSOLUTE,
        relative_ratio: float = RELATIVE_RATIO,
        ambiguous_ratio: float = AMBIGUOUS_THRESHOLD,
    ):
        self.min_fill = min_fill
        self.relative_ratio = relative_ratio
        self.ambiguous_ratio = ambiguous_ratio
        self.radius_px = int(mm_to_px(BUBBLE_RADIUS_MM) * SAMPLE_RADIUS_MULT)
        self.lang_radius_px = int(mm_to_px(LANG_BUBBLE_RADIUS_MM) * SAMPLE_RADIUS_MULT)
        self.centers = get_all_bubble_centers_px()
        self.lang_centers = get_language_centers_px()

    def read(self, image_path: str, debug_path: Optional[str] = None) -> OMRResult:
        img = cv2.imread(str(image_path))
        if img is None:
            return OMRResult(success=False, errors=[f"Nao abriu: {image_path}"])

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. QR Code (imagem original = mais resolução)
        qr = decode_qr(gray)
        tid = (qr.get("tid") or qr.get("template_id")) if qr else None
        sid = (qr.get("sid") or qr.get("student_id")) if qr else None
        tpl = (qr.get("tpl") or qr.get("template_type")) if qr else None

        # 2. Warp (prioriza fiduciais)
        warped = warp_to_standard(img, gray)
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

        # 3. Threshold adaptativo
        blurred = cv2.GaussianBlur(warped_gray, (3, 3), 0)
        thresh = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31, 8,
        )
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        # 4. Leitura das respostas
        answers = {}
        errors = []
        fill_details = {}
        dbg = warped.copy() if debug_path else None

        for q_num, alts in self.centers.items():
            fills = {}
            for alt, (cx, cy) in alts.items():
                fills[alt] = self._sample_fill(thresh, cx, cy, self.radius_px)
            fill_details[q_num] = fills

            sf = sorted(fills.items(), key=lambda x: x[1], reverse=True)
            best_alt, best_fill = sf[0]
            second_alt, second_fill = sf[1]
            others = [f for _, f in sf[1:]]
            avg_others = sum(others) / len(others) if others else 0

            # Debug
            if dbg is not None:
                for alt, (cx, cy) in alts.items():
                    is_best = (
                        alt == best_alt
                        and best_fill >= self.min_fill
                        and best_fill > avg_others * self.relative_ratio
                        and second_fill <= best_fill * self.ambiguous_ratio
                    )
                    color = (0, 0, 255) if is_best else (0, 200, 0)
                    cv2.circle(dbg, (cx, cy), self.radius_px, color, 2)
                    cv2.putText(
                        dbg, f"{fills[alt]:.2f}",
                        (cx - 15, cy - self.radius_px - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1,
                    )

            # Em branco
            if best_fill < self.min_fill:
                continue
            if avg_others > 0 and best_fill < avg_others * self.relative_ratio:
                continue

            # Dupla marcação
            if second_fill > best_fill * self.ambiguous_ratio:
                errors.append(
                    f"Q{q_num}: dupla ({best_alt}={best_fill:.3f}, "
                    f"{second_alt}={second_fill:.3f})"
                )
                continue

            answers[q_num] = best_alt

        # 5. Leitura da língua estrangeira
        language = self._read_language(thresh, dbg)

        # 6. Debug output
        if dbg is not None and debug_path:
            cv2.imwrite(str(debug_path), dbg)

        return OMRResult(
            success=len(answers) > 0,
            template_id=tid,
            student_id=sid,
            template_type=tpl,
            answers=answers,
            language=language,
            errors=errors,
            raw_data=json.dumps(qr) if qr else None,
            fill_details=fill_details,
        )

    def _read_language(
        self,
        thresh: np.ndarray,
        dbg: Optional[np.ndarray],
    ) -> Optional[str]:
        """Lê qual língua estrangeira foi marcada."""
        fills = {}
        for lang, (cx, cy) in self.lang_centers.items():
            fills[lang] = self._sample_fill(thresh, cx, cy, self.lang_radius_px)

            if dbg is not None:
                cv2.circle(dbg, (cx, cy), self.lang_radius_px, (255, 165, 0), 2)
                cv2.putText(
                    dbg, f"{fills[lang]:.2f}",
                    (cx - 10, cy - self.lang_radius_px - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 165, 0), 1,
                )

        if not fills:
            return None

        best_lang = max(fills, key=fills.get)
        best_fill = fills[best_lang]
        others = [f for l, f in fills.items() if l != best_lang]
        avg_others = sum(others) / len(others) if others else 0

        if best_fill < self.min_fill:
            return None
        if avg_others > 0 and best_fill < avg_others * self.relative_ratio:
            return None

        return best_lang

    def _sample_fill(self, thresh: np.ndarray, cx: int, cy: int, radius: int) -> float:
        """Fração de pixels marcados numa máscara circular."""
        h, w = thresh.shape
        if cx < 0 or cy < 0 or cx >= w or cy >= h:
            return 0.0
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(mask, (cx, cy), radius, 255, -1)
        masked = cv2.bitwise_and(thresh, thresh, mask=mask)
        return cv2.countNonZero(masked) / max(cv2.countNonZero(mask), 1)

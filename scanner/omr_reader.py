# reader_geom.py — Reader geométrico baseado no template Fleming
"""
Este reader abandona completamente:

* grouping heurístico
* clustering X/Y
* detecção automática de linhas
* detecção automática de colunas

E utiliza diretamente:

```python
get_all_bubble_centers_px()
```

do módulo de geometria.

Arquitetura:

text
imagem
→ warp
→ threshold
→ coordenadas conhecidas
→ leitura direta das bolhas
"""

# Código completo

import json
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from app.config import (
    get_all_bubble_centers_px,
    FILLED_THRESHOLD,
    AMBIGUOUS_THRESHOLD,
    BUBBLE_RADIUS_MM,
    mm_to_px,
)


# =============================================================================
# MODELS
# =============================================================================

@dataclass
class OMRResult:
    success: bool
    template_id: Optional[str] = None
    student_id: Optional[str] = None
    answers: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    raw_data: Optional[str] = None


# =============================================================================
# QR
# =============================================================================

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_OK = True
except ImportError:
    PYZBAR_OK = False


def decode_qr(gray):

    if PYZBAR_OK:
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
# WARP
# =============================================================================

def order_points(pts):

    rect = np.zeros((4, 2), dtype=np.float32)

    s = pts.sum(axis=1)

    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    d = np.diff(pts, axis=1)

    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]

    return rect


# =============================================================================

def find_and_warp(img, gray):

    h, w = gray.shape

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    warp_w = 2480
    warp_h = 3507

    for canny_lo, canny_hi in [(30, 100), (50, 150), (75, 200)]:

        edges = cv2.Canny(blurred, canny_lo, canny_hi)

        edges = cv2.dilate(edges, None, iterations=2)

        cnts, _ = cv2.findContours(
            edges,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

        for cnt in cnts[:10]:

            peri = cv2.arcLength(cnt, True)

            approx = cv2.approxPolyDP(
                cnt,
                0.02 * peri,
                True
            )

            if len(approx) != 4:
                continue

            area = cv2.contourArea(approx)

            if area < h * w * 0.2:
                continue

            pts = order_points(approx.reshape(4, 2))

            dst = np.float32([
                [0, 0],
                [warp_w, 0],
                [warp_w, warp_h],
                [0, warp_h]
            ])

            M = cv2.getPerspectiveTransform(pts, dst)

            warped = cv2.warpPerspective(
                img,
                M,
                (warp_w, warp_h)
            )

            return warped

    return cv2.resize(img, (warp_w, warp_h))


# =============================================================================
# READER
# =============================================================================

class OMRReader:

    def __init__(self):

        self.radius_px = int(mm_to_px(BUBBLE_RADIUS_MM) * 1.6)

        self.centers = get_all_bubble_centers_px()

    # =========================================================================

    def read(self, image_path, debug_path=None):

        img = cv2.imread(str(image_path))

        if img is None:
            return OMRResult(
                success=False,
                errors=[f"Não abriu imagem: {image_path}"]
            )

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # =========================================================================
        # QR
        # =========================================================================

        qr = decode_qr(gray)

        # =========================================================================
        # WARP
        # =========================================================================

        warped = find_and_warp(img, gray)

        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

        # =========================================================================
        # THRESHOLD
        # =========================================================================

        blurred = cv2.GaussianBlur(warped_gray, (3, 3), 0)

        thresh = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            8
        )

        kernel = np.ones((3, 3), np.uint8)

        thresh = cv2.morphologyEx(
            thresh,
            cv2.MORPH_OPEN,
            kernel
        )

        # =========================================================================
        # LEITURA DIRETA
        # =========================================================================

        answers = {}
        errors = []

        dbg = warped.copy()

        for q_label, alts in self.centers.items():

            fills = {}

            for alt, (cx, cy) in alts.items():

                mask = np.zeros(thresh.shape, dtype="uint8")

                cv2.circle(
                    mask,
                    (cx, cy),
                    self.radius_px,
                    255,
                    -1
                )

                masked = cv2.bitwise_and(
                    thresh,
                    thresh,
                    mask=mask
                )

                total = cv2.countNonZero(masked)

                area = cv2.countNonZero(mask)

                fill_ratio = total / float(area)

                fills[alt] = fill_ratio
                cv2.circle(
                    dbg,
                    (cx, cy),
                    3,
                    (255, 0, 0),
                    -1
                )
                # =============================================================
                # DEBUG
                # =============================================================

                color = (0, 255, 0)

                if fill_ratio > FILLED_THRESHOLD:
                    color = (0, 0, 255)

                cv2.circle(
                    dbg,
                    (cx, cy),
                    self.radius_px,
                    color,
                    2
                )

                cv2.putText(
                    dbg,
                    f"{fill_ratio:.2f}",
                    (cx - 15, cy - 12),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    color,
                    1
                )

            # =============================================================
            # DECISÃO
            # =============================================================

            sorted_fills = sorted(
                fills.items(),
                key=lambda x: x[1],
                reverse=True
            )

            best_alt, best_fill = sorted_fills[0]

            second_fill = sorted_fills[1][1]

            # questão em branco
            if best_fill < FILLED_THRESHOLD:
                continue

            # dupla marcação
            if second_fill > best_fill * 0.80:

                errors.append(
                    f"{q_label}: possível dupla marcação"
                )

                continue

            answers[q_label] = best_alt

        # =========================================================================
        # DEBUG
        # =========================================================================

        if debug_path:
            cv2.imwrite(str(debug_path), dbg)

        return OMRResult(
            success=len(answers) > 0,
            template_id=qr.get("tid") if qr else None,
            student_id=qr.get("sid") if qr else None,
            answers=answers,
            errors=errors,
            raw_data=json.dumps(qr) if qr else None,
        )

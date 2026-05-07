"""
omr_reader.py — Leitor OMR v6
Melhorias: este código faz detecção dos círculos e faz a leitura das marcações. vamos para de usar em 07/05/26, vamos adotar um modelo fico de template para cada simulado
  ✅ Warp fixo
  ✅ Adaptive Threshold
  ✅ Morphological Opening
  ✅ RETR_LIST
  ✅ Filtro de circularidade
  ✅ Máscara circular interna
  ✅ Leitura por taxa de preenchimento interno
  ✅ Melhor separação de dupla marcação
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_OK = True
except ImportError:
    PYZBAR_OK = False


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
# QR CODE
# =============================================================================

def _decode_qr(gray):

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
# PERSPECTIVE WARP
# =============================================================================

def _order_points(pts):

    rect = np.zeros((4, 2), dtype=np.float32)

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]

    return rect


def _find_and_warp_paper(img, gray):

    h, w = gray.shape

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    warp_w = 1600
    warp_h = 2260

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

            pts = _order_points(approx.reshape(4, 2))

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
# BUBBLE DETECTION
# =============================================================================

def _find_bubble_contours(thresh, warped_h, warped_w, header_fraction=0.25):

    cnts, _ = cv2.findContours(
        thresh,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE
    )

    bubbles = []

    header_y = int(warped_h * header_fraction)

    min_size = int(warped_w * 0.010)
    max_size = int(warped_w * 0.040)

    for c in cnts:

        x, y, w, h = cv2.boundingRect(c)

        # abaixo do cabeçalho
        if y < header_y:
            continue

        # tamanho
        if w < min_size or h < min_size:
            continue

        if w > max_size or h > max_size:
            continue

        # aspect ratio
        ar = w / float(h)

        if ar < 0.85 or ar > 1.15:
            continue

        # circularidade
        area = cv2.contourArea(c)

        peri = cv2.arcLength(c, True)

        if peri == 0:
            continue

        circularity = 4 * np.pi * area / (peri * peri)

        if circularity < 0.65:
            continue

        bubbles.append(c)

    return bubbles


# =============================================================================
# HELPERS
# =============================================================================

def _group_by_proximity(values, gap):

    if not values:
        return []

    values = sorted(values)

    groups = [[values[0]]]

    for v in values[1:]:

        if v - groups[-1][-1] < gap:
            groups[-1].append(v)
        else:
            groups.append([v])

    return groups


# =============================================================================
# OMR READER
# =============================================================================

class OMRReader:

    def __init__(
        self,
        fill_threshold=0.32,
        header_fraction=0.25,
        alternatives=None,
        cols_per_block=20,
        total_questions=63,
    ):

        self.fill_threshold = fill_threshold
        self.header_fraction = header_fraction
        self.alternatives = alternatives or ["A", "B", "C", "D"]
        self.cols_per_block = cols_per_block
        self.total_questions = total_questions

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

        qr = _decode_qr(gray)

        tid = (qr.get("tid") or qr.get("template_id")) if qr else None
        sid = (qr.get("sid") or qr.get("student_id")) if qr else None

        # =========================================================================
        # WARP
        # =========================================================================

        warped = _find_and_warp_paper(img, gray)

        wh, ww = warped.shape[:2]

        # =========================================================================
        # ÁREA VÁLIDA DAS RESPOSTAS
        # =========================================================================

        ANSWER_X1 = int(ww * 0.06)
        ANSWER_X2 = int(ww * 0.92)

        ANSWER_Y1 = int(wh * 0.18)
        ANSWER_Y2 = int(wh * 0.88)

        self.answer_area = (
            ANSWER_X1,
            ANSWER_Y1,
            ANSWER_X2,
            ANSWER_Y2
        )

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

        # remove ruído
        kernel = np.ones((3, 3), np.uint8)

        thresh = cv2.morphologyEx(
            thresh,
            cv2.MORPH_OPEN,
            kernel
        )

        # =========================================================================
        # BOLHAS
        # =========================================================================

        bubble_cnts = _find_bubble_contours(
            thresh,
            wh,
            ww,
            self.header_fraction
        )

        if len(bubble_cnts) < 10:

            return OMRResult(
                success=False,
                template_id=tid,
                student_id=sid,
                errors=[f"Poucas bolhas detectadas: {len(bubble_cnts)}"]
            )

        # =========================================================================
        # CENTROS
        # =========================================================================

        bubble_data = []

        for c in bubble_cnts:

            x, y, w, h = cv2.boundingRect(c)

            cx = x + w // 2
            cy = y + h // 2

            # =========================================================================
            # IGNORAR ELEMENTOS FORA DA ÁREA DE RESPOSTAS
            # =========================================================================

            if not (
                ANSWER_X1 <= cx <= ANSWER_X2 and
                ANSWER_Y1 <= cy <= ANSWER_Y2
            ):
                continue

            bubble_data.append((cx, cy, c))

        # =========================================================================
        # AGRUPAR COLUNAS
        # =========================================================================

        x_gap = ww * 0.03

        all_x = [b[0] for b in bubble_data]

        x_groups = _group_by_proximity(all_x, x_gap)

        col_centers = [
            sum(g) / len(g)
            for g in x_groups
        ]

        col_centers = sorted(col_centers)

        n_alts = len(self.alternatives)

        # gaps
        diffs = [
            col_centers[i + 1] - col_centers[i]
            for i in range(len(col_centers) - 1)
        ]

        block_groups = []

        if diffs:

            med = np.median(diffs)

            block_gap = med * 1.8

            current = [col_centers[0]]

            for i, d in enumerate(diffs):

                if d > block_gap:
                    block_groups.append(current)
                    current = [col_centers[i + 1]]
                else:
                    current.append(col_centers[i + 1])

            block_groups.append(current)

        else:
            block_groups = [col_centers]

        # =========================================================================
        # LEITURA
        # =========================================================================

        answers = {}
        errors = []

        q_num = 1

        for block_cols in block_groups:

            if len(block_cols) < n_alts:
                continue

            if len(block_cols) > n_alts:
                block_cols = block_cols[-n_alts:]

            block_x_min = block_cols[0] - x_gap * 2
            block_x_max = block_cols[-1] + x_gap * 2

            block_bubbles = [
                (cx, cy, c)
                for cx, cy, c in bubble_data
                if block_x_min <= cx <= block_x_max
            ]

            if not block_bubbles:
                continue

            # =========================================================================
            # LINHAS
            # =========================================================================

            y_gap = wh * 0.015

            ys = [b[1] for b in block_bubbles]

            y_groups = _group_by_proximity(ys, y_gap)

            for row in sorted(y_groups, key=lambda g: np.mean(g)):
            
                print(f"\n===== QUESTÃO {q_num} =====")

                if q_num > self.total_questions:
                    break

                row_y = np.mean(row)

                row_bubbles = [
                    (cx, cy, c)
                    for cx, cy, c in block_bubbles
                    if abs(cy - row_y) < y_gap
                ]

                row_bubbles.sort(key=lambda b: b[0])
                print("Bolhas:", len(row_bubbles))
                if len(row_bubbles) > n_alts:
                    row_bubbles = row_bubbles[-n_alts:]

                if len(row_bubbles) != n_alts:
                    q_num += 1
                    continue

                # =========================================================================
                # MEDIR PREENCHIMENTO
                # =========================================================================

                totals = []

                for cx, cy, c in row_bubbles:

                    x, y, w, h = cv2.boundingRect(c)

                    center_x = x + w // 2
                    center_y = y + h // 2

                    # máscara circular interna
                    radius = int(min(w, h) * 0.32)

                    mask = np.zeros(thresh.shape, dtype="uint8")

                    cv2.circle(
                        mask,
                        (center_x, center_y),
                        radius,
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

                    totals.append(fill_ratio)
                print(f"Fill ratio: {fill_ratio:.2f}")
                # =========================================================================
                # DECISÃO
                # =========================================================================

                max_total = max(totals)

                best_idx = totals.index(max_total)

                if max_total < self.fill_threshold:
                    q_num += 1
                    continue

                sorted_totals = sorted(totals, reverse=True)

                if len(sorted_totals) > 1:

                    second = sorted_totals[1]

                    # dupla marcação
                    if second > max_total * 0.60:

                        errors.append(
                            f"Q{q_num}: possível dupla marcação"
                        )

                        q_num += 1
                        continue
                        print(
                    f"SALVANDO Q{q_num}: "
                    f"{self.alternatives[best_idx]}"
                )
                answers[q_num] = self.alternatives[best_idx]

                q_num += 1

        # =========================================================================
        # DEBUG
        # =========================================================================

        if debug_path:
            self._save_debug(
                warped,
                thresh,
                bubble_cnts,
                answers,
                debug_path
            )

        return OMRResult(
            success=len(answers) > 0,
            template_id=tid,
            student_id=sid,
            answers=answers,
            errors=errors,
            raw_data=json.dumps(qr) if qr else None,
        )

    # =========================================================================

    def _save_debug(self, warped, thresh, bubble_cnts, answers, path):

        dbg = warped.copy()

        # =========================================================================
        # DESENHAR ÁREA VÁLIDA
        # =========================================================================

        ax1, ay1, ax2, ay2 = self.answer_area

        cv2.rectangle(
            dbg,
            (ax1, ay1),
            (ax2, ay2),
            (255, 0, 0),
            2
        )

        for c in bubble_cnts:

            x, y, w, h = cv2.boundingRect(c)

            center_x = x + w // 2
            center_y = y + h // 2

            radius = int(min(w, h) * 0.32)

            mask = np.zeros(thresh.shape, dtype="uint8")

            cv2.circle(
                mask,
                (center_x, center_y),
                radius,
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

            color = (0, 255, 0)

            if fill_ratio > self.fill_threshold:
                color = (0, 0, 255)

            cv2.circle(
                dbg,
                (center_x, center_y),
                radius,
                color,
                2
            )

            cv2.putText(
                dbg,
                f"{fill_ratio:.2f}",
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1
            )

        cv2.imwrite(str(path), dbg)
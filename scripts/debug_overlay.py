"""
Debug overlay: gera imagem com centros previstos, fiduciais e anchors.
Uso: python3 scripts/debug_overlay.py [imagem]
"""
import cv2, numpy as np, sys, os
sys.path.insert(0, os.path.expanduser("~/fleming-omr"))

from app.layout import (
    BLOCKS, ALTERNATIVES, FIDUCIALS_MM, FIDUCIAL_SIZE_MM,
    PAGE_W_PX, PAGE_H_PX, BUBBLE_RADIUS_MM, BUBBLE_GAP_V_MM,
    START_Y_MM, BUBBLE_GAP_H_MM,
    mm_to_px, get_all_bubble_centers_px, get_all_centers_interpolated,
    FILLED_THRESHOLD, ANCHOR_ROWS,
)
from app.omr_engine import (
    find_fiducials, align_image, analyze_bubble,
    detect_internal_markers,
)

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/fleming-omr/samples/julio.jpg")
img = cv2.imread(path)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

fids = find_fiducials(gray)
if fids is not None:
    aligned = align_image(img, fids)
    print(f"Fiduciais: {fids.tolist()}")
else:
    aligned = cv2.resize(img, (PAGE_W_PX, PAGE_H_PX))
    print("SEM FIDUCIAIS")

ga = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
debug = aligned.copy()

# 1. Fiduciais (retângulos azuis)
for i, (fx, fy) in enumerate(FIDUCIALS_MM):
    px, py = mm_to_px(fx), mm_to_px(fy)
    h = mm_to_px(FIDUCIAL_SIZE_MM / 2)
    cv2.rectangle(debug, (px-h, py-h), (px+h, py+h), (255, 0, 0), 2)
    cv2.putText(debug, f"F{i}", (px-h, py-h-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)

r = mm_to_px(BUBBLE_RADIUS_MM * 1.1)

print()
print("QUESTAO |  A     B     C     D   | RESULT | Y_px")
print("-" * 60)

for block in BLOCKS:
    # Detecta anchors internos
    anchors = detect_internal_markers(ga, block)
    
    # Desenha anchors (cruzes amarelas)
    for aname, ay in anchors.items():
        ax = mm_to_px(block.origin_x_mm) - mm_to_px(8)
        cv2.drawMarker(debug, (ax, ay), (0, 255, 255),
                       cv2.MARKER_CROSS, 20, 2)
        cv2.putText(debug, f"{aname}", (ax+12, ay+4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)

    # Centros interpolados
    centers = get_all_centers_interpolated(block, anchors)

    for qi in range(block.num_questions):
        label = f"q{block.start_q + qi}"
        fills = {}

        for alt in ALTERNATIVES:
            cx, cy = centers[label][alt]
            fill = analyze_bubble(ga, (cx, cy), r)
            fills[alt] = fill

            # Cor: verde=marcada, cinza=vazia, amarelo=ambígua
            if fill >= FILLED_THRESHOLD:
                color = (0, 200, 0)
                thick = 3
            elif fill >= 0.25:
                color = (0, 200, 255)
                thick = 2
            else:
                color = (180, 180, 180)
                thick = 1

            cv2.circle(debug, (cx, cy), r, color, thick)
            # Pequeno ponto central
            cv2.circle(debug, (cx, cy), 2, color, -1)

        best = max(fills, key=fills.get)
        mark = best if fills[best] >= FILLED_THRESHOLD else "-"
        _, y_px = centers[label]["A"]
        print(f"  {label:>4}  | {fills['A']:.2f}  {fills['B']:.2f}  {fills['C']:.2f}  {fills['D']:.2f} | {mark:>3}    | {y_px}")

    # Label do bloco
    ox = mm_to_px(block.origin_x_mm) - 10
    oy = mm_to_px(START_Y_MM) - 40
    cv2.putText(debug, f"Q{block.start_q}-Q{block.end_q}", (ox, oy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 200), 1)

# Salva
out = path.replace(".jpg", "_debug_v6.png").replace(".png", "_debug_v6.png")
cv2.imwrite(out, debug)
small = cv2.resize(debug, (800, int(800 * debug.shape[0] / debug.shape[1])))
small_path = out.replace(".png", "_small.png")
cv2.imwrite(small_path, small)

print()
print(f"Debug salvo: {out}")
print(f"Versão pequena: {small_path}")
print(f"Download: cloudshell download {small_path}")

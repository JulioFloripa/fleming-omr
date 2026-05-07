"""
sheet_generator.py — Gerador de gabaritos OMR em PDF.

Gera folhas de respostas com:
  - QR Code (template_id + student_id)
  - Fiduciais de canto (quadrados 8mm pretos nos 4 cantos)
  - Marcadores internos (quadrados 4mm pretos no topo/meio/base de cada bloco)
  - Grade de bolhas organizadas em blocos/colunas
  - Cabeçalho com dados do aluno e nome da prova

Templates suportados:
  - ACAFE: 63 questões, 4 alternativas (A, B, C, D), 4 blocos de ~16q
  - UFSC:  82 questões, 5 alternativas somatório (01, 02, 04, 08, 16)
  - ENEM:  180 questões, 5 alternativas (A, B, C, D, E)
"""

from __future__ import annotations

import io
import json
import math
from typing import Optional

import qrcode
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


# ─── Constantes de layout ─────────────────────────────────────────────────────
# Devem bater com omr_reader.py
FIDUCIAL_SIZE = 8 * mm        # Quadrado preto nos cantos (referência geométrica)
INNER_MARKER_SIZE = 4 * mm    # Quadrado preto de calibração nos blocos

BUBBLE_RADIUS = 3.5 * mm      # Raio das bolhas
BUBBLE_SPACING = 8.5 * mm     # Espaçamento horizontal entre centros de bolhas
ROW_SPACING = 8.0 * mm        # Espaçamento vertical entre linhas de questões

PAGE_MARGIN = 15 * mm          # Margem da página
HEADER_HEIGHT = 75 * mm        # Altura reservada para cabeçalho + QR

QUESTIONS_PER_BLOCK = 20       # Máximo de questões por coluna/bloco


# ─── Função principal ─────────────────────────────────────────────────────────

def generate_sheet_for_student(
    template_id: str,
    template_name: str,
    exam_type: str,
    total_questions: int,
    alternatives: list[str],
    student: dict,
    questions_meta: Optional[list[dict]] = None,
) -> bytes:
    """
    Gera o PDF do gabarito OMR para um estudante.

    Retorna os bytes do PDF.
    """
    buf = io.BytesIO()
    page_w, page_h = A4  # 210mm × 297mm

    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Gabarito {template_name} - {student.get('name', 'Aluno')}")

    # ── Fiduciais de canto (4 quadrados pretos nos cantos) ────────────────────
    _draw_fiducials(c, page_w, page_h)

    # ── QR Code ───────────────────────────────────────────────────────────────
    qr_data = json.dumps({
        "tid": template_id,
        "sid": student.get("student_id") or student.get("id", ""),
        "et": exam_type,
    }, separators=(",", ":"))
    _draw_qr_code(c, qr_data, page_w)

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    _draw_header(c, page_w, page_h, template_name, exam_type, student)

    # ── Grade de bolhas ───────────────────────────────────────────────────────
    n_blocks = math.ceil(total_questions / QUESTIONS_PER_BLOCK)
    usable_width = page_w - 2 * PAGE_MARGIN - FIDUCIAL_SIZE
    block_width = usable_width / n_blocks

    # Origem Y da grade (abaixo do header)
    grid_top_y = page_h - HEADER_HEIGHT

    for block_idx in range(n_blocks):
        x_col = PAGE_MARGIN + FIDUCIAL_SIZE / 2 + block_idx * block_width

        # Marcador interno de TOPO (centro horizontal do bloco)
        marker_x = x_col + 14 * mm + (len(alternatives) - 1) * BUBBLE_SPACING / 2
        marker_y_top = grid_top_y + INNER_MARKER_SIZE / 2 + 2 * mm
        c.setFillColorRGB(0, 0, 0)
        c.rect(
            marker_x - INNER_MARKER_SIZE / 2,
            marker_y_top - INNER_MARKER_SIZE / 2,
            INNER_MARKER_SIZE,
            INNER_MARKER_SIZE,
            fill=1, stroke=0,
        )

        # Questões deste bloco
        q_start = block_idx * QUESTIONS_PER_BLOCK + 1
        q_end = min(q_start + QUESTIONS_PER_BLOCK - 1, total_questions)

        for q_offset, q_num in enumerate(range(q_start, q_end + 1)):
            row_y = grid_top_y - (q_offset + 1) * ROW_SPACING

            # Número da questão
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica", 7)
            q_label = f"{q_num:02d}"
            c.drawRightString(x_col + 10 * mm, row_y - 2, q_label)

            # Bolhas
            for alt_idx, alt_label in enumerate(alternatives):
                bx = x_col + 14 * mm + alt_idx * BUBBLE_SPACING
                by = row_y

                # Bolha vazia (círculo cinza claro)
                c.setStrokeColorRGB(0.3, 0.3, 0.3)
                c.setFillColorRGB(1, 1, 1)
                c.circle(bx, by, BUBBLE_RADIUS, fill=1, stroke=1)

                # Letra da alternativa dentro da bolha
                c.setFillColorRGB(0.5, 0.5, 0.5)
                c.setFont("Helvetica", 6)
                c.drawCentredString(bx, by - 2, alt_label)

        # Marcador interno de MEIO (se bloco tem ≥10 questões)
        if q_end - q_start + 1 >= 10:
            mid_row = (q_end - q_start) // 2
            marker_y_mid = grid_top_y - (mid_row + 1) * ROW_SPACING
            c.setFillColorRGB(0, 0, 0)
            c.rect(
                marker_x - INNER_MARKER_SIZE / 2,
                marker_y_mid - INNER_MARKER_SIZE / 2,
                INNER_MARKER_SIZE,
                INNER_MARKER_SIZE,
                fill=1, stroke=0,
            )

        # Marcador interno de BASE
        last_row_y = grid_top_y - (q_end - q_start + 1) * ROW_SPACING
        marker_y_bot = last_row_y - ROW_SPACING / 2
        c.setFillColorRGB(0, 0, 0)
        c.rect(
            marker_x - INNER_MARKER_SIZE / 2,
            marker_y_bot - INNER_MARKER_SIZE / 2,
            INNER_MARKER_SIZE,
            INNER_MARKER_SIZE,
            fill=1, stroke=0,
        )

    # ── Rodapé ────────────────────────────────────────────────────────────────
    c.setFont("Helvetica", 6)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(page_w / 2, 10 * mm,
                        f"Colégio Fleming — {template_name} — Preencha com caneta preta")

    c.save()
    return buf.getvalue()


# ─── Fiduciais de canto ───────────────────────────────────────────────────────

def _draw_fiducials(c: canvas.Canvas, page_w: float, page_h: float):
    """Desenha 4 quadrados pretos nos cantos como referência geométrica."""
    margin = PAGE_MARGIN / 2
    positions = [
        (margin, page_h - margin - FIDUCIAL_SIZE),                          # top-left
        (page_w - margin - FIDUCIAL_SIZE, page_h - margin - FIDUCIAL_SIZE), # top-right
        (margin, margin),                                                    # bottom-left
        (page_w - margin - FIDUCIAL_SIZE, margin),                          # bottom-right
    ]
    c.setFillColorRGB(0, 0, 0)
    for x, y in positions:
        c.rect(x, y, FIDUCIAL_SIZE, FIDUCIAL_SIZE, fill=1, stroke=0)


# ─── QR Code ──────────────────────────────────────────────────────────────────

def _draw_qr_code(c: canvas.Canvas, data: str, page_w: float):
    """Gera e desenha o QR Code no canto superior direito."""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")

    # Converter para bytes
    img_buf = io.BytesIO()
    qr_img.save(img_buf, format="PNG")
    img_buf.seek(0)

    from reportlab.lib.utils import ImageReader
    qr_size = 30 * mm
    x = page_w - PAGE_MARGIN - qr_size - FIDUCIAL_SIZE
    y = A4[1] - PAGE_MARGIN - FIDUCIAL_SIZE - qr_size - 5 * mm
    c.drawImage(ImageReader(img_buf), x, y, width=qr_size, height=qr_size)


# ─── Cabeçalho ────────────────────────────────────────────────────────────────

def _draw_header(
    c: canvas.Canvas,
    page_w: float,
    page_h: float,
    template_name: str,
    exam_type: str,
    student: dict,
):
    """Desenha o cabeçalho com título da prova e dados do aluno."""
    x_start = PAGE_MARGIN + FIDUCIAL_SIZE + 5 * mm
    y_top = page_h - PAGE_MARGIN - FIDUCIAL_SIZE - 8 * mm

    # Título
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(x_start, y_top, f"GABARITO — {template_name}")

    # Tipo de prova
    c.setFont("Helvetica", 9)
    c.drawString(x_start, y_top - 16, f"Tipo: {exam_type}")

    # Dados do aluno
    name = student.get("name", "—")
    sid = student.get("student_id") or student.get("id", "—")
    campus = student.get("campus", "")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_start, y_top - 35, f"Aluno: {name}")

    c.setFont("Helvetica", 9)
    c.drawString(x_start, y_top - 50, f"Matrícula: {sid}")
    if campus:
        c.drawString(x_start + 80 * mm, y_top - 50, f"Campus: {campus}")

    # Linha separadora
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.setLineWidth(0.5)
    sep_y = y_top - 60
    c.line(PAGE_MARGIN, sep_y, page_w - PAGE_MARGIN, sep_y)

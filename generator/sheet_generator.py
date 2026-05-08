"""
sheet_generator.py — Gerador de gabaritos PDF template ACAFE.

Usa coordenadas exatas de app.config.
ReportLab: pontos (1pt = 1/72 in), origem BOTTOM-LEFT.
config: mm, origem TOP-LEFT.
"""

import io
import json
from typing import Optional

import qrcode
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from app.config import (
    ALTERNATIVES,
    BLOCK_A_X_MM,
    BLOCK_QUESTION_COUNTS,
    BUBBLE_RADIUS_MM,
    BUBBLE_SPACING_X_MM,
    FIDUCIAL_CENTERS_MM,
    FIDUCIAL_SIZE_MM,
    FIRST_ROW_Y_MM,
    FOREIGN_LANGUAGES,
    LANG_AREA_Y_MM,
    LANG_BUBBLE_RADIUS_MM,
    LANG_BUBBLE_SPACING_MM,
    LANG_BUBBLE_X_START_MM,
    PAGE_H_MM,
    PAGE_W_MM,
    ROW_SPACING_Y_MM,
    get_all_bubble_centers_mm,
    get_language_centers_mm,
)

# Conversão mm → pontos ReportLab
_PT = 72.0 / 25.4


def _pt(v):
    """mm para pontos."""
    return v * _PT


def _y(y_mm):
    """Flip Y: top-left (config) → bottom-left (ReportLab), em mm."""
    return PAGE_H_MM - y_mm


def generate_sheet_for_student(
    template_type: str = "ACAFE",
    student_id: str = "",
    student_name: str = "",
    student_sede: str = "",
    template_id: Optional[str] = None,
) -> bytes:
    """Gera PDF de gabarito. Retorna bytes."""

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_pt(PAGE_W_MM), _pt(PAGE_H_MM)))

    # =================================================================
    # 1. FIDUCIAIS — 4 quadrados pretos nos cantos
    # =================================================================
    half = FIDUCIAL_SIZE_MM / 2
    c.setFillColorRGB(0, 0, 0)
    for fx, fy in FIDUCIAL_CENTERS_MM:
        c.rect(
            _pt(fx - half), _pt(_y(fy) - half),
            _pt(FIDUCIAL_SIZE_MM), _pt(FIDUCIAL_SIZE_MM),
            stroke=0, fill=1,
        )

    # =================================================================
    # 2. CABEÇALHO
    # =================================================================
    # Título
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(_pt(15), _pt(_y(15)), f"{template_type}")

    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(_pt(15), _pt(_y(21)), f"Tipo: {template_type}")
    c.setFillColorRGB(0, 0, 0)

    # Dados do aluno
    c.setFont("Helvetica-Bold", 11)
    c.drawString(_pt(15), _pt(_y(30)), "Nome:")
    c.setFont("Helvetica", 11)
    c.drawString(_pt(32), _pt(_y(30)), student_name)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(_pt(15), _pt(_y(36)), "Matrícula:")
    c.setFont("Helvetica", 11)
    c.drawString(_pt(42), _pt(_y(36)), student_id)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(_pt(90), _pt(_y(36)), "Sede:")
    c.setFont("Helvetica", 11)
    c.drawString(_pt(103), _pt(_y(36)), student_sede)

    # =================================================================
    # 3. QR CODE (canto superior direito)
    # =================================================================
    qr_data = json.dumps({
        "tid": template_id or f"{template_type}_default",
        "sid": student_id,
        "tpl": template_type,
    })
    qr_img = qrcode.make(qr_data, box_size=3, border=1)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    qr_size = 22  # mm
    qr_x = PAGE_W_MM - 15 - qr_size
    qr_y = 10
    c.drawImage(
        ImageReader(qr_buf),
        _pt(qr_x), _pt(_y(qr_y) - qr_size),
        width=_pt(qr_size), height=_pt(qr_size),
    )
    c.setFont("Helvetica", 6)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(
        _pt(qr_x + qr_size / 2),
        _pt(_y(qr_y + qr_size + 2)),
        "Gabarito OMR",
    )
    c.setFillColorRGB(0, 0, 0)

    # =================================================================
    # 4. LÍNGUA ESTRANGEIRA (área separada, abaixo dos dados do aluno)
    # =================================================================
    # Linha separadora fina
    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.setLineWidth(0.4)
    c.line(_pt(15), _pt(_y(44)), _pt(PAGE_W_MM - 15), _pt(_y(44)))

    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(_pt(15), _pt(_y(LANG_AREA_Y_MM)), "Língua Estrangeira:")

    lang_centers = get_language_centers_mm()
    for lang, (lx, ly) in lang_centers.items():
        # Bolha
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.6)
        c.setFillColorRGB(1, 1, 1)
        c.circle(_pt(lx), _pt(_y(ly)), _pt(LANG_BUBBLE_RADIUS_MM), stroke=1, fill=1)
        # Label ao lado
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 8.5)
        c.drawString(
            _pt(lx + LANG_BUBBLE_RADIUS_MM + 2),
            _pt(_y(ly)) - 3,
            lang,
        )

    # =================================================================
    # 5. INSTRUÇÕES
    # =================================================================
    inst_y = 57.0
    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.setLineWidth(0.4)
    c.line(_pt(15), _pt(_y(inst_y)), _pt(PAGE_W_MM - 15), _pt(_y(inst_y)))

    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(_pt(15), _pt(_y(inst_y + 5)), "INSTRUÇÕES:")

    c.setFont("Helvetica", 7.5)
    instrucoes = [
        "Use caneta esferográfica azul ou preta.",
        "Preencha completamente a bolha correspondente à sua resposta.",
        "Não rasure. Em caso de erro, solicite uma nova folha ao aplicador.",
        "Preencha apenas UMA bolha por questão.",
    ]
    for i, txt in enumerate(instrucoes):
        c.drawString(_pt(17), _pt(_y(inst_y + 10 + i * 4)), f"• {txt}")

    # =================================================================
    # 6. CABEÇALHOS DOS BLOCOS (Q, A, B, C, D)
    # =================================================================
    label_y = FIRST_ROW_Y_MM - ROW_SPACING_Y_MM * 0.6

    for block_idx in range(len(BLOCK_QUESTION_COUNTS)):
        base_x = BLOCK_A_X_MM[block_idx]

        # "Q"
        c.setFont("Helvetica-Bold", 6)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawRightString(_pt(base_x - 4), _pt(_y(label_y)), "Q")

        # Letras A B C D
        c.setFont("Helvetica-Bold", 7)
        c.setFillColorRGB(0, 0, 0)
        for ai, alt in enumerate(ALTERNATIVES):
            x = base_x + ai * BUBBLE_SPACING_X_MM
            c.drawCentredString(_pt(x), _pt(_y(label_y)), alt)

    # =================================================================
    # 7. NÚMEROS DAS QUESTÕES
    # =================================================================
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    q_num = 1
    for bi, count in enumerate(BLOCK_QUESTION_COUNTS):
        base_x = BLOCK_A_X_MM[bi]
        for row in range(count):
            y_mm = FIRST_ROW_Y_MM + row * ROW_SPACING_Y_MM
            c.drawRightString(_pt(base_x - 4), _pt(_y(y_mm)) - 2, str(q_num))
            q_num += 1

    # =================================================================
    # 8. BOLHAS DE RESPOSTA (posições exatas do config)
    # =================================================================
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.6)
    c.setFillColorRGB(1, 1, 1)

    for q, alts in get_all_bubble_centers_mm().items():
        for alt, (x_mm, y_mm) in alts.items():
            c.circle(
                _pt(x_mm), _pt(_y(y_mm)),
                _pt(BUBBLE_RADIUS_MM),
                stroke=1, fill=1,
            )

    # =================================================================
    # 9. SEPARADORES VERTICAIS ENTRE BLOCOS
    # =================================================================
    c.setStrokeColorRGB(0.85, 0.85, 0.85)
    c.setLineWidth(0.3)
    for bi in range(1, len(BLOCK_QUESTION_COUNTS)):
        sep_x = (
            BLOCK_A_X_MM[bi - 1]
            + (len(ALTERNATIVES) - 1) * BUBBLE_SPACING_X_MM
            + BLOCK_A_X_MM[bi]
        ) / 2
        y_top = FIRST_ROW_Y_MM - ROW_SPACING_Y_MM
        y_bot = FIRST_ROW_Y_MM + 19 * ROW_SPACING_Y_MM + ROW_SPACING_Y_MM * 0.5
        c.line(_pt(sep_x), _pt(_y(y_top)), _pt(sep_x), _pt(_y(y_bot)))

    # =================================================================
    # FINALIZAR
    # =================================================================
    c.showPage()
    c.save()
    return buf.getvalue()

"""Gera PDF do gabarito com reportlab."""
import io, os, json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import black, white, HexColor
from reportlab.pdfgen import canvas
from .config import (BLOCKS, ALTERNATIVES, FIDUCIAL_SIZE_MM, FIDUCIALS_MM,
    QR_SIZE_MM, QR_X_MM, QR_Y_MM, BUBBLE_RADIUS_MM,
    BUBBLE_GAP_H_MM, BUBBLE_GAP_V_MM, LABEL_WIDTH_MM,
    MARGIN_LEFT_MM, MARGIN_TOP_MM, PAGE_W_MM, PAGE_H_MM,
    STUDENT_NAME_FIELD, STUDENT_CLASS_FIELD, STUDENT_DATE_FIELD)

BLUE = HexColor("#1a3a6b")
GRAY = HexColor("#666666")
LIGHT = HexColor("#e8edf3")

def _fiducials(c):
    c.setFillColor(black); c.setStrokeColor(black)
    for cx, cy in FIDUCIALS_MM:
        x = (cx - FIDUCIAL_SIZE_MM/2) * mm
        y = (PAGE_H_MM - cy - FIDUCIAL_SIZE_MM/2) * mm
        c.rect(x, y, FIDUCIAL_SIZE_MM*mm, FIDUCIAL_SIZE_MM*mm, fill=1)

def _qr(c, data):
    try:
        import qrcode
        from reportlab.lib.utils import ImageReader
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(data); qr.make(fit=True)
        buf = io.BytesIO(); qr.make_image(fill_color="black", back_color="white").save(buf, format='PNG'); buf.seek(0)
        c.drawImage(ImageReader(buf), QR_X_MM*mm, (PAGE_H_MM-QR_Y_MM-QR_SIZE_MM)*mm, QR_SIZE_MM*mm, QR_SIZE_MM*mm)
    except ImportError:
        x, y = QR_X_MM*mm, (PAGE_H_MM-QR_Y_MM-QR_SIZE_MM)*mm
        c.setStrokeColor(GRAY); c.setFillColor(LIGHT)
        c.rect(x, y, QR_SIZE_MM*mm, QR_SIZE_MM*mm, fill=1, stroke=1)
        c.setFillColor(GRAY); c.setFont("Helvetica", 6)
        c.drawCentredString(x+QR_SIZE_MM/2*mm, y+QR_SIZE_MM/2*mm, "QR CODE")

def _header(c, title, subtitle):
    ty = PAGE_H_MM - MARGIN_TOP_MM - 8
    c.setFillColor(BLUE); c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN_LEFT_MM*mm, ty*mm, "COLÉGIO FLEMING")
    c.setFont("Helvetica", 10); c.setFillColor(GRAY)
    c.drawString(MARGIN_LEFT_MM*mm, (ty-6)*mm, title)
    if subtitle: c.drawString(MARGIN_LEFT_MM*mm, (ty-11)*mm, subtitle)
    c.setStrokeColor(BLUE); c.setLineWidth(1.5)
    ly = PAGE_H_MM - MARGIN_TOP_MM - 18
    c.line(MARGIN_LEFT_MM*mm, ly*mm, (PAGE_W_MM-MARGIN_LEFT_MM)*mm, ly*mm)
    for label, field in [("Nome:", STUDENT_NAME_FIELD), ("Turma:", STUDENT_CLASS_FIELD), ("Data:", STUDENT_DATE_FIELD)]:
        x, yt, w, h = field["x_mm"], field["y_mm"], field["w_mm"], field["h_mm"]
        yr = PAGE_H_MM - yt - h
        c.setFont("Helvetica", 8); c.setFillColor(GRAY)
        c.drawString(x*mm, (yr+h-2)*mm, label)
        c.setStrokeColor(GRAY); c.setLineWidth(0.5)
        c.line((x+len(label)*2.5+2)*mm, yr*mm, (x+w)*mm, yr*mm)

def _blocks(c):
    for block in BLOCKS:
        hy = block.start_y_mm - 6
        c.setFont("Helvetica-Bold", 7); c.setFillColor(BLUE)
        c.drawString(block.col_x_mm*mm, (PAGE_H_MM-hy)*mm, f"Q{block.start_q}-Q{block.end_q}")
        c.setFont("Helvetica-Bold", 6); c.setFillColor(GRAY)
        for ai, alt in enumerate(ALTERNATIVES):
            ax = block.bubble_origin_x_mm + ai * BUBBLE_GAP_H_MM
            c.drawCentredString(ax*mm, (PAGE_H_MM-hy+4)*mm, alt)
        for qi in range(block.num_questions):
            qn = block.start_q + qi
            qy = block.start_y_mm + qi * BUBBLE_GAP_V_MM
            c.setFont("Helvetica", 7); c.setFillColor(black)
            c.drawRightString((block.col_x_mm+LABEL_WIDTH_MM-2)*mm, (PAGE_H_MM-qy-1.5)*mm, f"{qn:02d}")
            for ai in range(len(ALTERNATIVES)):
                bx = block.bubble_origin_x_mm + ai * BUBBLE_GAP_H_MM
                c.setStrokeColor(black); c.setLineWidth(0.6); c.setFillColor(white)
                c.circle(bx*mm, (PAGE_H_MM-qy)*mm, BUBBLE_RADIUS_MM*mm, fill=0, stroke=1)

def _footer(c):
    c.setFont("Helvetica", 6); c.setFillColor(GRAY)
    c.drawString(MARGIN_LEFT_MM*mm, 18*mm,
        "INSTRUÇÕES: Preencha completamente a bolha da alternativa escolhida com caneta preta ou azul escura.")
    c.drawString(MARGIN_LEFT_MM*mm, 14*mm,
        "Não use corretivo. Em caso de erro, solicite novo gabarito. Apenas UMA alternativa por questão.")

def generate_sheet(sheet_id, output_path, exam_title="GABARITO", exam_subtitle=""):
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    c = canvas.Canvas(output_path, pagesize=A4)
    c.setTitle(f"Gabarito Fleming - {sheet_id}")
    _fiducials(c)
    _qr(c, json.dumps({"id": sheet_id, "type": "gabarito_fleming", "v": 1}))
    _header(c, exam_title, exam_subtitle)
    _blocks(c)
    _footer(c)
    c.save()
    return output_path

def generate_sheet_bytes(sheet_id, exam_title="GABARITO", exam_subtitle=""):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _fiducials(c)
    _qr(c, json.dumps({"id": sheet_id, "type": "gabarito_fleming", "v": 1}))
    _header(c, exam_title, exam_subtitle)
    _blocks(c)
    _footer(c)
    c.save(); buf.seek(0)
    return buf.read()

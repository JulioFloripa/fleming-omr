"""
main.py — API REST Fleming OMR.

Endpoints:
  GET  /health           → status
  POST /scan-batch       → leitura de gabaritos (multipart files)
  POST /scan-batch-url   → leitura de gabaritos (URLs)
  POST /generate-batch   → geração de PDFs (JSON)
  GET  /grid             → grid de coordenadas (debug)
"""

import io
import json
import os
import tempfile
import zipfile
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.config import TOTAL_QUESTIONS, ALTERNATIVES, FOREIGN_LANGUAGES, export_grid_json
from scanner.omr_reader import OMRReader

app = FastAPI(
    title="Fleming OMR API",
    version="5.0.0",
    description="Leitura e geração de gabaritos ACAFE — Colégio Fleming",
)

API_TOKEN = os.environ.get("FLEMING_API_TOKEN", "fleming-token-2025-acafe")


def _check_token(token: Optional[str]):
    if not token or token != API_TOKEN:
        raise HTTPException(401, "Token inválido")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "5.0.0",
        "approach": "fiducial-warp + position-based reading",
        "total_questions": TOTAL_QUESTIONS,
        "alternatives": ALTERNATIVES,
        "languages": FOREIGN_LANGUAGES,
    }


@app.get("/grid")
async def grid(x_fleming_token: Optional[str] = Header(None)):
    _check_token(x_fleming_token)
    return export_grid_json()


@app.post("/scan-batch")
async def scan_batch(
    files: list[UploadFile] = File(...),
    config: str = Form("{}"),
    x_fleming_token: Optional[str] = Header(None),
):
    _check_token(x_fleming_token)
    try:
        cfg = json.loads(config) if config else {}
    except json.JSONDecodeError:
        cfg = {}

    reader = OMRReader(
        min_fill=cfg.get("min_fill", 0.08),
        relative_ratio=cfg.get("relative_ratio", 1.25),
    )

    results = []
    for f in files:
        data = await f.read()
        if not data:
            results.append({"scan_id": f.filename, "success": False, "errors": ["Arquivo vazio"]})
            continue

        actual = data
        if f.filename and f.filename.lower().endswith(".pdf"):
            actual = _pdf_to_png(data)
            if actual is None:
                results.append({"scan_id": f.filename, "success": False, "errors": ["Falha PDF→imagem"]})
                continue

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(actual)
            tmp_path = tmp.name

        try:
            result = reader.read(tmp_path)
            results.append({
                "scan_id": f.filename,
                "success": result.success,
                "template_id": result.template_id,
                "student_id": result.student_id,
                "template_type": result.template_type,
                "detected_answers": {str(k): v for k, v in result.answers.items()},
                "language": result.language,
                "total_detected": len(result.answers),
                "total_expected": TOTAL_QUESTIONS,
                "errors": result.errors,
            })
        finally:
            _rm(tmp_path)

    return {"results": results}


class ScanURLItem(BaseModel):
    scan_id: str
    image_url: str

class ScanURLRequest(BaseModel):
    template: dict = {}
    scans: list[ScanURLItem] = []

@app.post("/scan-batch-url")
async def scan_batch_url(
    body: ScanURLRequest,
    x_fleming_token: Optional[str] = Header(None),
):
    _check_token(x_fleming_token)
    import httpx
    reader = OMRReader()
    results = []

    async with httpx.AsyncClient(timeout=30) as client:
        for scan in body.scans:
            try:
                resp = await client.get(scan.image_url)
                resp.raise_for_status()
            except Exception as e:
                results.append({"scan_id": scan.scan_id, "success": False, "errors": [str(e)]})
                continue

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name
            try:
                result = reader.read(tmp_path)
                results.append({
                    "scan_id": scan.scan_id,
                    "success": result.success,
                    "template_id": result.template_id,
                    "student_id": result.student_id,
                    "template_type": result.template_type,
                    "detected_answers": {str(k): v for k, v in result.answers.items()},
                    "language": result.language,
                    "total_detected": len(result.answers),
                    "total_expected": TOTAL_QUESTIONS,
                    "errors": result.errors,
                })
            finally:
                _rm(tmp_path)

    return {"results": results}


class StudentInfo(BaseModel):
    id: str
    name: str
    sede: str = ""

class GenerateBatchRequest(BaseModel):
    template_type: str = "ACAFE"
    students: list[StudentInfo] = []

@app.post("/generate-batch")
async def generate_batch(
    body: GenerateBatchRequest,
    x_fleming_token: Optional[str] = Header(None),
):
    _check_token(x_fleming_token)
    from generator.sheet_generator import generate_sheet_for_student

    if not body.students:
        raise HTTPException(400, "Lista vazia")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for s in body.students:
            pdf = generate_sheet_for_student(
                template_type=body.template_type,
                student_id=s.id,
                student_name=s.name,
                student_sede=s.sede,
            )
            zf.writestr(f"gabarito_{s.id}_{s.name.replace(' ', '_')}.pdf", pdf)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=gabaritos.zip"},
    )


def _pdf_to_png(data: bytes) -> Optional[bytes]:
    try:
        from pdf2image import convert_from_bytes
        imgs = convert_from_bytes(data, dpi=300, first_page=1, last_page=1)
        if not imgs:
            return None
        buf = io.BytesIO()
        imgs[0].save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None

def _rm(path: str):
    try:
        os.unlink(path)
    except OSError:
        pass

"""
Fleming Corrector — API OMR  (v3)
==================================
API REST (FastAPI) para integração do módulo OMR com o frontend Lovable.

Endpoints:
  GET  /health           → Status da API
  POST /generate-sheet   → Gera PDF do gabarito OMR para 1 estudante (base64)
  POST /generate-batch   → Gera PDFs em lote (ZIP)
  POST /scan             → Processa 1 imagem escaneada
  POST /scan-batch       → Processa múltiplas imagens (JSON **ou** FormData)
  POST /scan-batch-url   → Processa scans via URLs assinadas (JSON)

Segurança:
  Token fixo via header X-Fleming-Token.
"""

import io
import json
import os
import sys
import tempfile
import zipfile
import base64
from typing import Optional, List

import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from generator.sheet_generator import generate_sheet_for_student
from scanner.omr_reader import OMRReader


# ─── Inicialização ─────────────────────────────────────────────────────────────

EXPECTED_TOKEN = os.environ.get("FLEMING_API_TOKEN", "fleming-token-2025-acafe")

app = FastAPI(
    title="Fleming Corrector — OMR API",
    description="API para geração e leitura de gabaritos OMR com QR Code.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Middleware de autenticação ────────────────────────────────────────────────

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)
    token = request.headers.get("X-Fleming-Token", "")
    if token != EXPECTED_TOKEN:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Token inválido"})
    return await call_next(request)


# ─── Schemas ───────────────────────────────────────────────────────────────────

class StudentData(BaseModel):
    id: str
    student_id: Optional[str] = None
    name: str
    campus: Optional[str] = ""
    foreign_language: Optional[str] = ""


class QuestionMeta(BaseModel):
    question_number: int
    question_type: str = "objective"
    subject: Optional[str] = None


class GenerateSheetRequest(BaseModel):
    template_id: str
    template_name: str
    exam_type: str
    total_questions: int
    alternatives: List[str]
    student: StudentData
    questions_meta: Optional[List[QuestionMeta]] = None


class GenerateBatchRequest(BaseModel):
    template_id: str
    template_name: str
    exam_type: str
    total_questions: int
    alternatives: List[str]
    students: List[StudentData]
    questions_meta: Optional[List[QuestionMeta]] = None


class ScanConfig(BaseModel):
    total_questions: int = 63
    alternatives: List[str] = ["A", "B", "C", "D"]
    cols_per_block: int = 20
    fill_threshold: float = 0.40
    header_fraction: float = 0.28


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "Fleming OMR API", "version": "3.0.0"}


@app.post("/generate-sheet")
def generate_sheet(req: GenerateSheetRequest):
    """Gera o PDF do gabarito OMR para um único estudante (base64)."""
    try:
        pdf_bytes = generate_sheet_for_student(
            template_id=req.template_id,
            template_name=req.template_name,
            exam_type=req.exam_type,
            total_questions=req.total_questions,
            alternatives=req.alternatives,
            student=req.student.model_dump(),
            questions_meta=[q.model_dump() for q in req.questions_meta] if req.questions_meta else None,
        )
        return {
            "success": True,
            "student_id": req.student.student_id or req.student.id,
            "student_name": req.student.name,
            "pdf_base64": base64.b64encode(pdf_bytes).decode(),
            "pdf_size_bytes": len(pdf_bytes),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-batch")
def generate_batch(req: GenerateBatchRequest):
    """Gera PDFs em lote para múltiplos estudantes (ZIP)."""
    try:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for student in req.students:
                pdf_bytes = generate_sheet_for_student(
                    template_id=req.template_id,
                    template_name=req.template_name,
                    exam_type=req.exam_type,
                    total_questions=req.total_questions,
                    alternatives=req.alternatives,
                    student=student.model_dump(),
                    questions_meta=[q.model_dump() for q in req.questions_meta] if req.questions_meta else None,
                )
                sid = student.student_id or student.id
                safe_name = student.name.replace(" ", "_").replace("/", "-")
                filename = f"gabarito_{sid}_{safe_name}.pdf"
                zf.writestr(filename, pdf_bytes)

        zip_buf.seek(0)
        template_safe = req.template_name.replace(" ", "_").replace("/", "-")
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="gabaritos_{template_safe}.zip"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scan")
async def scan_sheet(
    file: UploadFile = File(...),
    config: str = Form(...),
):
    """Processa uma imagem de gabarito escaneado."""
    try:
        cfg_data = json.loads(config)
        scan_cfg = ScanConfig(**cfg_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Config inválida: {e}")

    try:
        img_bytes = await file.read()
        img_bytes = _maybe_convert_pdf(img_bytes, file.filename)
        result = _scan_image(img_bytes, scan_cfg)
        return _result_to_dict(result, filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scan-batch")
async def scan_batch(request: Request):
    """
    Processa múltiplas imagens em lote.

    Aceita DOIS formatos:
      1. JSON: { template: {...}, scans: [{scan_id, image_url}] }  ← edge function
      2. FormData: files + config  ← legado / curl
    """
    content_type = request.headers.get("content-type", "")

    # ── Formato JSON (edge function do Lovable) ───────────────────────────────
    if "application/json" in content_type:
        body = await request.json()
        template = body.get("template", {})
        scans = body.get("scans", [])

        exam_type = str(template.get("exam_type", "ACAFE")).upper()
        alternatives = {
            "UFSC": ["01", "02", "04", "08", "16"],
            "ENEM": ["A", "B", "C", "D", "E"],
        }.get(exam_type, ["A", "B", "C", "D"])

        scan_cfg = ScanConfig(
            total_questions=template.get("total_questions", 63),
            alternatives=alternatives,
        )

        results = []
        async with httpx.AsyncClient(timeout=60) as client:
            for scan in scans:
                scan_id = scan.get("scan_id", "unknown")
                try:
                    r = await client.get(scan["image_url"])
                    r.raise_for_status()
                    img_bytes = _maybe_convert_pdf(r.content, f"{scan_id}.png")
                    result = _scan_image(img_bytes, scan_cfg)
                    entry = _result_to_dict(result, filename=scan_id)
                    entry["scan_id"] = scan_id
                    results.append(entry)
                except Exception as e:
                    results.append({"scan_id": scan_id, "success": False, "error": str(e)})

        return {"results": results}

    # ── Formato FormData (legado / curl) ──────────────────────────────────────
    form = await request.form()
    files = form.getlist("files")
    config_str = form.get("config", "{}")
    try:
        cfg_data = json.loads(config_str) if isinstance(config_str, str) else {}
        scan_cfg = ScanConfig(**cfg_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Config inválida: {e}")

    results = []
    summary = {"total": len(files), "success": 0, "with_errors": 0, "failed": 0}

    for f in files:
        try:
            img_bytes = await f.read()
            img_bytes = _maybe_convert_pdf(img_bytes, f.filename)
            result = _scan_image(img_bytes, scan_cfg)
            entry = _result_to_dict(result, filename=f.filename)
            results.append(entry)

            if result.success:
                summary["success"] += 1
            elif result.errors:
                summary["with_errors"] += 1
            else:
                summary["failed"] += 1
        except Exception as e:
            results.append({"filename": f.filename, "success": False, "error": str(e)})
            summary["failed"] += 1

    return {"summary": summary, "results": results}


@app.post("/scan-batch-url")
async def scan_batch_url(request: Request):
    """
    Processa scans via URLs assinadas do Supabase Storage.
    Formato: { template: {...}, scans: [{scan_id, image_url}] }
    """
    body = await request.json()
    template = body.get("template", {})
    scans = body.get("scans", [])

    exam_type = str(template.get("exam_type", "ACAFE")).upper()
    alternatives = {
        "UFSC": ["01", "02", "04", "08", "16"],
        "ENEM": ["A", "B", "C", "D", "E"],
    }.get(exam_type, ["A", "B", "C", "D"])

    scan_cfg = ScanConfig(
        total_questions=template.get("total_questions", 63),
        alternatives=alternatives,
    )

    results = []
    async with httpx.AsyncClient(timeout=60) as client:
        for scan in scans:
            scan_id = scan.get("scan_id", "unknown")
            try:
                r = await client.get(scan["image_url"])
                r.raise_for_status()
                img_bytes = _maybe_convert_pdf(r.content, f"{scan_id}.png")
                result = _scan_image(img_bytes, scan_cfg)
                entry = _result_to_dict(result, filename=scan_id)
                entry["scan_id"] = scan_id
                results.append(entry)
            except Exception as e:
                results.append({"scan_id": scan_id, "success": False, "error": str(e)})

    return {"results": results}


# ─── Utilitários ──────────────────────────────────────────────────────────────

def _scan_image(img_bytes: bytes, scan_cfg: ScanConfig):
    """Salva bytes em arquivo temporário (OMRReader espera path) e processa."""
    reader = OMRReader(
        fill_threshold=scan_cfg.fill_threshold,
        header_fraction=scan_cfg.header_fraction,
        alternatives=scan_cfg.alternatives,
        cols_per_block=scan_cfg.cols_per_block,
        total_questions=scan_cfg.total_questions,
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tf.write(img_bytes)
        tmp_path = tf.name
    try:
        return reader.read(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _result_to_dict(result, filename: str | None = None) -> dict:
    """Serializa OMRResult para resposta JSON da API."""
    # Gerar detected_answers no formato legado {Q1: "A", Q2: "C"}
    detected_answers = {f"Q{q}": a for q, a in sorted(result.answers.items())}

    entry = {
        "success": result.success,
        "template_id": result.template_id,
        "student_id": result.student_id,
        "detected_answers": detected_answers,
        "answers": [
            {"question_number": q, "answer": a}
            for q, a in sorted(result.answers.items())
        ],
        "total_detected": len(result.answers),
        "errors": result.errors,
        "warnings": [],
        "qr_data": result.raw_data,
    }
    if filename is not None:
        entry["filename"] = filename
    return entry


def _maybe_convert_pdf(data: bytes, filename: Optional[str]) -> bytes:
    """Se o arquivo for PDF, converte a primeira página em PNG."""
    if filename and filename.lower().endswith(".pdf"):
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(data, dpi=300, first_page=1, last_page=1)
        if not images:
            raise ValueError("Não foi possível converter o PDF para imagem.")
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return buf.getvalue()
    return data

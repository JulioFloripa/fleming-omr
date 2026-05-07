"""API FastAPI para correção de gabaritos — Colégio Fleming."""
import io, os, uuid, time, logging, json
from typing import Dict, List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .omr_engine import process_image_bytes, grade_answers
from .sheet_generator import generate_sheet_bytes
from .config import MAX_UPLOAD_SIZE_MB, ALLOWED_EXTENSIONS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fleming-omr")

app = FastAPI(title="Fleming OMR API", description="Correção automática de gabaritos — Colégio Fleming", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ScanResponse(BaseModel):
    success: bool
    student_id: Optional[str] = None
    answers: Dict[str, Optional[str]]
    stats: Dict[str, int]
    warnings: List[str] = []
    processing_time_ms: float = 0

class GenerateSheetRequest(BaseModel):
    sheet_id: Optional[str] = None
    exam_title: str = "GABARITO"
    exam_subtitle: str = ""

@app.get("/")
async def root():
    return {"service": "Fleming OMR API", "version": "1.0.0", "docs": "/docs"}

@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "fleming-omr"}

@app.post("/api/v1/scan", response_model=ScanResponse)
async def scan(file: UploadFile = File(...), debug: bool = Query(False)):
    """Envia imagem do gabarito → recebe respostas detectadas."""
    start = time.time()
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"Máximo {MAX_UPLOAD_SIZE_MB}MB")
    if not contents:
        raise HTTPException(400, "Arquivo vazio")
    try:
        r = process_image_bytes(contents, debug)
    except Exception as e:
        raise HTTPException(500, str(e))
    return ScanResponse(success=r.success, student_id=r.student_id, answers=r.answers,
                        stats=r.stats, warnings=r.warnings,
                        processing_time_ms=round((time.time()-start)*1000, 2))

@app.post("/api/v1/generate-sheet")
async def gen_sheet(req: GenerateSheetRequest):
    """Gera PDF do gabarito em branco."""
    sid = req.sheet_id or str(uuid.uuid4())[:8].upper()
    pdf = generate_sheet_bytes(sid, req.exam_title, req.exam_subtitle)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="gabarito_{sid}.pdf"'})

@app.post("/api/v1/scan-and-grade")
async def scan_and_grade(file: UploadFile = File(...),
                         answer_key: str = Form(...)):
    """Escaneia + corrige com gabarito oficial (JSON)."""
    try: key = json.loads(answer_key)
    except: raise HTTPException(400, "answer_key deve ser JSON válido")
    start = time.time()
    r = process_image_bytes(await file.read())
    grade = grade_answers(r.answers, key)
    return {"success": r.success, "student_id": r.student_id,
            "answers": r.answers, "grade": grade,
            "processing_time_ms": round((time.time()-start)*1000, 2)}

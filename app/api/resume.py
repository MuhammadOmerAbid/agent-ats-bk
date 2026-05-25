import inspect
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.docx_generator import generate_ats_docx
from app.pdf_generator import generate_ats_pdf, generate_europass_pdf, generate_modern_pdf
from app.resume_builder import generate_resume_draft

router = APIRouter(prefix="/api/resume", tags=["resume"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_FORMATS: dict[str, tuple[Any, str, str]] = {
    "ats": (generate_ats_pdf, "resume_ats.pdf", "application/pdf"),
    "modern": (generate_modern_pdf, "resume_modern.pdf", "application/pdf"),
    "europass": (generate_europass_pdf, "resume_europass.pdf", "application/pdf"),
    "docx": (generate_ats_docx, "resume.docx", _DOCX_MIME),
}


@router.post("/draft")
async def create_draft(request: Request) -> dict[str, Any]:
    body = await request.json()
    resume_text = str(body.get("resume_text") or "")
    jd_skills = body.get("jd_skills") or {}
    gap_analysis = body.get("gap_analysis") or {}
    user_info = body.get("user_info") or {}

    if not isinstance(jd_skills, dict) or not isinstance(gap_analysis, dict) or not isinstance(user_info, dict):
        raise HTTPException(status_code=400, detail="Invalid draft payload.")

    return generate_resume_draft(
        original_resume=resume_text,
        jd_skills=jd_skills,
        gap_analysis=gap_analysis,
        user_info=user_info,
    )


@router.post("/export/{format_name}")
async def export_resume(format_name: str, request: Request) -> Response:
    body = await request.json()
    approved = body.get("approved_resume")
    if not isinstance(approved, dict):
        raise HTTPException(status_code=400, detail="approved_resume is required.")

    if format_name not in _FORMATS:
        raise HTTPException(status_code=400, detail="Invalid format. Use: ats | modern | europass | docx")

    generator, filename, media_type = _FORMATS[format_name]
    content = generator(approved)
    if inspect.isawaitable(content):
        content = await content
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

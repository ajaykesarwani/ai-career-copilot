"""
Applications router — document generation + layout-aware export.
The export endpoint now passes the candidate's resume_layout to doc_export
so PDF/DOCX output reproduces the detected visual style of the original.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from models.schemas import (
    GenerateDocsRequest, GenerateDocsResponse, ApplicationDocs,
    ExportDocRequest, ResumeLayout,
)
from agents import DocumentGeneratorAgent
from utils import doc_export

router  = APIRouter()
_doc_gen = DocumentGeneratorAgent()


@router.post("/generate", response_model=GenerateDocsResponse)
async def generate_docs(req: GenerateDocsRequest):
    job     = req.job.model_dump()
    profile = req.profile.model_dump()
    docs_dict = await _doc_gen.generate(job, profile)
    return GenerateDocsResponse(job_id=req.job.id, docs=ApplicationDocs(**docs_dict))


@router.post("/export")
async def export_doc(req: ExportDocRequest):
    """
    Render generated text as a formatted PDF or DOCX.
    Uses the candidate's detected resume_layout to reproduce their style.
    """
    if req.doc_type not in ("resume", "cover"):
        raise HTTPException(400, "doc_type must be 'resume' or 'cover'")
    if req.format not in ("pdf", "docx"):
        raise HTTPException(400, "format must be 'pdf' or 'docx'")

    profile = req.profile.model_dump()
    job     = req.job.model_dump() if req.job else None

    # Extract layout dict — use provided layout, or fall back to profile's stored layout
    layout: dict | None = None
    if req.resume_layout:
        layout = req.resume_layout.model_dump()
    elif req.profile.resume_layout:
        layout = req.profile.resume_layout.model_dump()

    try:
        if req.doc_type == "resume":
            content = (
                doc_export.render_resume_pdf(req.content, profile, layout)
                if req.format == "pdf"
                else doc_export.render_resume_docx(req.content, profile, layout)
            )
            filename_base = "Resume"
        else:
            content = (
                doc_export.render_cover_letter_pdf(req.content, profile, job)
                if req.format == "pdf"
                else doc_export.render_cover_letter_docx(req.content, profile, job)
            )
            filename_base = "Cover_Letter"
    except Exception as e:
        raise HTTPException(500, f"Document rendering failed: {e}")

    name_part    = (profile.get("name") or "Candidate").replace(" ", "_")
    company_part = f"_{job['company'].replace(' ','_')}" if job and job.get("company") else ""
    filename     = f"{name_part}_{filename_base}{company_part}.{req.format}"
    media_type   = (
        "application/pdf" if req.format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

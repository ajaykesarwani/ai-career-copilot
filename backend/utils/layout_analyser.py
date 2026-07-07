"""
Resume Layout Analyser
=======================
Uses Gemini Vision to analyse the visual layout of the candidate's uploaded
resume so that the generated documents can reproduce the same structure and
style rather than always using a generic template.

What it detects:
  - Single column vs. two-column layout
  - Section order (e.g. CONTACT → SUMMARY → EXPERIENCE → SKILLS)
  - Header style (centred name, left-aligned, banner with photo)
  - Accent colour (the dominant non-black colour used for headings/lines)
  - Font personality (modern sans-serif, classic serif, creative/colourful)
  - Whether the resume uses sidebar panels, icons, horizontal dividers

The result (ResumeLayout) is stored on the CandidateProfile and passed to
doc_export.py which uses it to select the right rendering template.
"""

from __future__ import annotations
import io
import os
import re
import json
import asyncio
from typing import Optional


async def analyse_layout(file_bytes: bytes, filename: str) -> dict:
    """
    Analyse the visual layout of an uploaded resume file.
    Returns a dict that maps to ResumeLayout fields.
    Falls back to safe defaults if analysis fails.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return _default_layout()

    # Convert first page to image for vision analysis
    image_bytes = _first_page_image(file_bytes, filename)
    if not image_bytes:
        return _default_layout()

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

        prompt = """Analyse this resume image and return ONLY a JSON object describing its visual layout.

Return exactly these keys:
{
  "columns": 1,
  "has_sidebar": false,
  "section_order": ["CONTACT","SUMMARY","EXPERIENCE","EDUCATION","SKILLS"],
  "accent_color": "2C3E50",
  "font_style": "modern",
  "header_style": "centered",
  "uses_icons": false,
  "uses_dividers": true,
  "raw_description": "One sentence describing the overall visual style"
}

Rules:
- columns: 1 if single column layout, 2 if two-column or sidebar layout
- has_sidebar: true if there is a sidebar panel (usually left, with skills/contact)
- section_order: list the section headings in the order they appear, using these labels:
  CONTACT, SUMMARY, OBJECTIVE, EXPERIENCE, EDUCATION, SKILLS, PROJECTS, CERTIFICATIONS, AWARDS, LANGUAGES, INTERESTS
- accent_color: 6-digit hex of the main non-black color used for headings or lines (no # prefix).
  If the resume is entirely black-and-white, use "2C3E50"
- font_style: "modern" (sans-serif, clean), "classic" (serif, formal), or "creative" (colourful, graphic)
- header_style: "centered" (name centered at top), "left-aligned" (name left), or "banner" (colored header band)
- uses_icons: true if phone/email/LinkedIn icons are visible
- uses_dividers: true if horizontal lines separate sections
- raw_description: plain English description of the resume's visual style in one sentence

Return ONLY the JSON, no markdown fences, no extra text."""

        parts = [prompt, {"mime_type": "image/png", "data": image_bytes}]
        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: model.generate_content(parts)
        )
        raw = response.text or ""
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(cleaned)
        return _validate(data)

    except Exception:
        return _default_layout()


def _first_page_image(file_bytes: bytes, filename: str) -> Optional[bytes]:
    """Render the first page of a PDF or the first image of a DOCX to PNG bytes."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext == "pdf":
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
            doc.close()
            return pix.tobytes("png")
        except Exception:
            return None

    if ext in ("docx", "doc"):
        try:
            # Convert DOCX first page to PDF via python-docx extract + fitz fallback
            # Simpler: just rasterise the docx thumbnail via LibreOffice if available
            import subprocess, tempfile, os as _os
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
                f.write(file_bytes)
                tmp_docx = f.name
            try:
                tmp_dir = tempfile.mkdtemp()
                result = subprocess.run(
                    ["libreoffice", "--headless", "--convert-to", "pdf",
                     "--outdir", tmp_dir, tmp_docx],
                    capture_output=True, timeout=20
                )
                pdf_path = _os.path.join(tmp_dir, _os.path.basename(tmp_docx).replace(".docx", ".pdf"))
                if _os.path.exists(pdf_path):
                    import fitz
                    doc = fitz.open(pdf_path)
                    pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
                    doc.close()
                    return pix.tobytes("png")
            except Exception:
                pass
            finally:
                try:
                    _os.unlink(tmp_docx)
                except Exception:
                    pass
        except Exception:
            pass

    return None


def _validate(data: dict) -> dict:
    """Ensure all required keys are present with safe types."""
    defaults = _default_layout()
    result = {}
    result["columns"]          = int(data.get("columns", 1)) if str(data.get("columns","1")).isdigit() else 1
    result["has_sidebar"]      = bool(data.get("has_sidebar", False))
    result["section_order"]    = data.get("section_order", defaults["section_order"])
    if not isinstance(result["section_order"], list):
        result["section_order"] = defaults["section_order"]
    result["accent_color"]     = str(data.get("accent_color", "2C3E50")).strip("#").upper()[:6] or "2C3E50"
    result["font_style"]       = str(data.get("font_style", "modern")) if data.get("font_style") in ("modern","classic","creative") else "modern"
    result["header_style"]     = str(data.get("header_style", "centered")) if data.get("header_style") in ("centered","left-aligned","banner") else "centered"
    result["uses_icons"]       = bool(data.get("uses_icons", False))
    result["uses_dividers"]    = bool(data.get("uses_dividers", True))
    result["raw_description"]  = str(data.get("raw_description", ""))[:300]
    return result


def _default_layout() -> dict:
    return {
        "columns": 1,
        "has_sidebar": False,
        "section_order": ["CONTACT","SUMMARY","EXPERIENCE","EDUCATION","SKILLS","PROJECTS","CERTIFICATIONS"],
        "accent_color": "6C5CE7",
        "font_style": "modern",
        "header_style": "centered",
        "uses_icons": False,
        "uses_dividers": True,
        "raw_description": "Clean single-column professional resume.",
    }

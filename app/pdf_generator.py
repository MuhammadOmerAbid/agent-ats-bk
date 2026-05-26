import asyncio
import io
import os
from typing import Any

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.resume_schema import ApprovedResume

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)
_PLAYWRIGHT_TIMEOUT_SECONDS = 45


async def generate_ats_pdf(approved: dict[str, Any]) -> bytes:
    return await _render("ats.html", approved, "ats")


async def generate_modern_pdf(approved: dict[str, Any]) -> bytes:
    return await _render("modern.html", approved, "modern")


async def generate_europass_pdf(approved: dict[str, Any]) -> bytes:
    return await _render("europass.html", approved, "europass")


async def _render(template_name: str, approved: dict[str, Any], style_name: str) -> bytes:
    data = _normalize(approved)
    html_str = _env.get_template(template_name).render(**data)
    try:
        if os.name == "nt":
            return await asyncio.wait_for(
                asyncio.to_thread(_render_playwright_sync, html_str),
                timeout=_PLAYWRIGHT_TIMEOUT_SECONDS,
            )
        return await asyncio.wait_for(
            _render_playwright_async(html_str),
            timeout=_PLAYWRIGHT_TIMEOUT_SECONDS,
        )
    except Exception as error:
        print(f"[PDF] Playwright render failed, using ReportLab fallback: {error}")
        return _render_reportlab(data, style_name)


async def _render_playwright_async(html_str: str) -> bytes:
    browser = None
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_str, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
        )
        await browser.close()
    return pdf_bytes


def _render_playwright_sync(html_str: str) -> bytes:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(html_str, wait_until="networkidle")
        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
        )
        browser.close()
    return pdf_bytes


def _render_reportlab(data: dict[str, Any], style_name: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.7 * cm,
        leftMargin=1.7 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"{data['name']} Resume",
    )
    story: list[Any] = []
    styles = _pdf_styles(style_name)

    contact = " | ".join(
        part for part in [data["email"], data["phone"], data["location"], data["linkedin"], data["github"]] if part
    )
    story.append(Paragraph(_esc(data["name"]), styles["name"]))
    if contact:
        story.append(Paragraph(_esc(contact), styles["contact"]))
    story.append(Spacer(1, 10))

    if data["summary"]:
        _section(story, "Professional Summary", styles)
        story.append(Paragraph(_esc(data["summary"]), styles["body"]))

    if data["experience"]:
        _section(story, "Experience", styles)
        for item in data["experience"]:
            heading = " | ".join(part for part in [item["title"], item["company"]] if part)
            meta = " | ".join(part for part in [item["location"], item["date"]] if part)
            if heading:
                story.append(Paragraph(_esc(heading), styles["item"]))
            if meta:
                story.append(Paragraph(_esc(meta), styles["meta"]))
            for bullet in item["bullets"]:
                story.append(Paragraph(_esc(bullet), styles["bullet"], bulletText="-"))

    if data["projects"]:
        _section(story, "Projects", styles)
        for project in data["projects"]:
            tech = ", ".join(project["technologies"])
            heading = f"{project['name']} | {tech}" if tech else project["name"]
            if heading:
                story.append(Paragraph(_esc(heading), styles["item"]))
            if project["description"]:
                story.append(Paragraph(_esc(project["description"]), styles["body"]))
            for bullet in project["bullets"]:
                story.append(Paragraph(_esc(bullet), styles["bullet"], bulletText="-"))

    if data["education"]:
        _section(story, "Education", styles)
        for edu in data["education"]:
            text = " | ".join(part for part in [edu["degree"], edu["institution"], edu["location"], edu["year"]] if part)
            if text:
                story.append(Paragraph(_esc(text), styles["body"]))

    if data["certifications"]:
        _section(story, "Certifications", styles)
        for cert in data["certifications"]:
            text = " | ".join(part for part in [cert["name"], cert["issuer"], cert["year"]] if part)
            if text:
                story.append(Paragraph(_esc(text), styles["body"]))

    if data["skills"]:
        _section(story, "Skills", styles)
        story.append(Paragraph(_esc(", ".join(data["skills"])), styles["body"]))

    doc.build(story)
    return buffer.getvalue()


def _pdf_styles(style_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    accent = {
        "ats": colors.HexColor("#111827"),
        "modern": colors.HexColor("#2563eb"),
        "europass": colors.HexColor("#1d4ed8"),
    }.get(style_name, colors.HexColor("#111827"))

    return {
        "name": ParagraphStyle(
            "ResumeName",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            textColor=accent,
            spaceAfter=4,
        ),
        "contact": ParagraphStyle(
            "ResumeContact",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475569"),
        ),
        "section": ParagraphStyle(
            "ResumeSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=accent,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "item": ParagraphStyle(
            "ResumeItem",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            spaceBefore=4,
            spaceAfter=1,
        ),
        "meta": ParagraphStyle(
            "ResumeMeta",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "ResumeBody",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "ResumeBullet",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            leftIndent=12,
            bulletIndent=3,
            spaceAfter=2,
        ),
    }


def _section(story: list[Any], title: str, styles: dict[str, ParagraphStyle]) -> None:
    story.append(Paragraph(title.upper(), styles["section"]))


def _esc(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten ApprovedResume (nested contact) into template-ready scalars."""
    contact = raw.get("contact") or {}
    if not isinstance(contact, dict):
        contact = {}

    def _c(field: str) -> str:
        return str(contact.get(field) or raw.get(field) or "").strip()

    # Experience — compute date string from start/end dates
    experience = []
    for job in raw.get("experience") or []:
        start = str(job.get("start_date") or "").strip()
        end = str(job.get("end_date") or "").strip()
        duration = str(job.get("duration") or "").strip()
        if start and end:
            date_str = f"{start} – {end}"
        elif start:
            date_str = f"{start} – Present"
        else:
            date_str = duration
        bullets = [str(b).strip() for b in (job.get("bullets") or []) if str(b).strip()]
        experience.append({
            "title": str(job.get("title") or "").strip(),
            "company": str(job.get("company") or "").strip(),
            "location": str(job.get("location") or "").strip(),
            "date": date_str,
            "bullets": bullets,
        })

    # Projects
    projects = []
    for proj in raw.get("projects") or []:
        bullets = [str(b).strip() for b in (proj.get("bullets") or []) if str(b).strip()]
        techs = [str(t).strip() for t in (proj.get("technologies") or []) if str(t).strip()]
        projects.append({
            "name": str(proj.get("name") or "").strip(),
            "description": str(proj.get("description") or "").strip(),
            "technologies": techs,
            "bullets": bullets,
        })

    # Education
    education = []
    for edu in raw.get("education") or []:
        education.append({
            "degree": str(edu.get("degree") or "").strip(),
            "institution": str(edu.get("institution") or "").strip(),
            "location": str(edu.get("location") or "").strip(),
            "year": str(edu.get("year") or "").strip(),
        })

    # Certifications
    certifications = []
    for cert in raw.get("certifications") or []:
        certifications.append({
            "name": str(cert.get("name") or "").strip(),
            "issuer": str(cert.get("issuer") or "").strip(),
            "year": str(cert.get("year") or "").strip(),
        })

    # Skills — accept list or comma-separated string
    raw_skills = raw.get("skills") or []
    if isinstance(raw_skills, str):
        raw_skills = raw_skills.split(",")
    skills = [str(s).strip() for s in raw_skills if str(s).strip()]

    return {
        "name": _c("name") or "Your Name",
        "email": _c("email"),
        "phone": _c("phone"),
        "linkedin": _c("linkedin"),
        "github": _c("github"),
        "location": _c("location"),
        "role_title": str(raw.get("role_title") or "").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "experience": experience,
        "projects": projects,
        "skills": skills,
        "education": education,
        "certifications": certifications,
    }

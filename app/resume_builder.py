import json
import re
from typing import Any

from app.llm_client import call_llm
from app.llm_extractor import extract_user_info
from app.resume_schema import ResumeDraft
from app.services.extractors import extract_bullets, extract_skills, has_metrics


def generate_resume_draft(
    original_resume: str,
    jd_skills: dict[str, Any],
    gap_analysis: dict[str, Any],
    user_info: dict[str, Any],
) -> dict[str, Any]:
    source_resume = original_resume.strip() or _resume_from_match_result(gap_analysis)
    matched = _string_list(gap_analysis.get("matched_required") or gap_analysis.get("matchedRequired"))
    missing = _string_list(gap_analysis.get("missing_required") or gap_analysis.get("missingRequired"))
    role = str(jd_skills.get("role_title") or user_info.get("target_role") or "the target role")

    prompt = f"""You are an expert resume writer. Extract ALL information from the candidate's original resume and reformat it into a professional, ATS-optimized resume.

CRITICAL RULES — never break these:
1. Do NOT invent any information not in the original resume (no fake employers, dates, degrees, projects, or certifications).
2. Extract EVERY work experience entry — do not skip older or shorter roles.
3. For each experience entry, extract ALL bullet points from the original (up to 8 per entry).
4. Extract start_date and end_date as separate fields (e.g., "Jan 2021" and "Dec 2023" or "Present").
5. Extract the city/country location for each experience entry if mentioned anywhere in the resume.
6. Extract ALL projects, education entries, and certifications that appear in the resume.
7. Keep the candidate's actual company names, job titles, and dates exactly as stated.
8. Improve bullet wording using strong action verbs and quantified impact only where the original text provides real evidence.
9. Weave in ATS keywords from the job skills list only where truthfully applicable to the candidate's actual work.

TARGET ROLE: {role}
SKILLS THE CANDIDATE HAS: {matched}
SKILLS THE CANDIDATE IS MISSING (do NOT add these unless already in resume): {missing}
JD SKILLS FOR ATS KEYWORDS: {jd_skills}

ORIGINAL RESUME (extract every section — do not skip any experience, project, or education):
{source_resume[:8000]}

Return ONLY valid JSON with this exact shape:
{{
  "contact": {{
    "name": "candidate name from resume or empty string",
    "email": "email from resume or empty string",
    "phone": "phone from resume or empty string",
    "linkedin": "linkedin url from resume or empty string",
    "github": "github url from resume or empty string",
    "location": "location from resume or empty string"
  }},
  "summary": "specific 2-3 sentence professional summary based on the candidate's real background",
  "experience": [
    {{
      "title": "real title",
      "company": "real company or empty string",
      "location": "real location or empty string",
      "start_date": "real start date or empty string",
      "end_date": "real end date or empty string",
      "duration": "real duration or empty string",
      "bullets": [
        {{
          "original": "original resume bullet",
          "suggested": "improved bullet using only truthful evidence",
          "change_reason": "short reason"
        }}
      ]
    }}
  ],
  "projects": [
    {{
      "name": "real project name",
      "description": "brief truthful project description",
      "technologies": ["tech1"],
      "bullets": [
        {{
          "original": "original project bullet or description",
          "suggested": "improved truthful project bullet",
          "change_reason": "short reason"
        }}
      ]
    }}
  ],
  "education": [
    {{
      "degree": "real degree",
      "institution": "real institution",
      "location": "location or empty string",
      "year": "year or empty string",
      "details": ["relevant coursework or honors only if present"]
    }}
  ],
  "certifications": [
    {{
      "name": "real certification",
      "issuer": "issuer or empty string",
      "year": "year or empty string"
    }}
  ],
  "skills": ["only skills present in the resume, ordered by target role relevance"],
  "ats_improvements": ["specific improvement made"]
}}
"""

    try:
        draft = _parse_json(call_llm(prompt, prefer_fast=False, max_tokens=4000))
    except Exception as error:
        print(f"[Draft] LLM structured draft failed, using deterministic fallback: {error}")
        draft = _fallback_draft(source_resume, matched, jd_skills)

    normalized = _normalize_draft(draft, source_resume, user_info, matched, jd_skills)
    return ResumeDraft.model_validate(normalized).model_dump(by_alias=True)


def _normalize_draft(
    draft: dict[str, Any],
    original_resume: str,
    user_info: dict[str, Any],
    matched: list[str],
    jd_skills: dict[str, Any],
) -> dict[str, Any]:
    fallback = _fallback_draft(original_resume, matched, jd_skills)
    contact = draft.get("contact") if isinstance(draft.get("contact"), dict) else {}
    fallback_contact = fallback["contact"]

    normalized = {
        "contact": {
            "name": str(user_info.get("name") or contact.get("name") or fallback_contact["name"]),
            "email": str(user_info.get("email") or contact.get("email") or fallback_contact["email"]),
            "phone": str(user_info.get("phone") or contact.get("phone") or fallback_contact["phone"]),
            "linkedin": str(user_info.get("linkedin") or contact.get("linkedin") or fallback_contact["linkedin"]),
            "github": str(user_info.get("github") or contact.get("github") or fallback_contact["github"]),
            "location": str(user_info.get("location") or contact.get("location") or fallback_contact["location"]),
        },
        "summary": str(draft.get("summary") or fallback["summary"]),
        "experience": _normalize_experience(draft.get("experience")) or fallback["experience"],
        "projects": _normalize_projects(draft.get("projects")) or fallback["projects"],
        "education": _normalize_education(draft.get("education")) or fallback["education"],
        "certifications": _normalize_certifications(draft.get("certifications")) or fallback["certifications"],
        "skills": _string_list(draft.get("skills")) or fallback["skills"],
        "ats_improvements": _string_list(draft.get("ats_improvements")) or fallback["ats_improvements"],
    }
    return normalized


def _fallback_draft(original_resume: str, matched: list[str], jd_skills: dict[str, Any]) -> dict[str, Any]:
    # Try LLM-powered contact extraction first, fall back to regex
    try:
        raw_info = extract_user_info(original_resume)
        contact = {
            "name": str(raw_info.get("name") or ""),
            "email": str(raw_info.get("email") or ""),
            "phone": str(raw_info.get("phone") or ""),
            "linkedin": str(raw_info.get("linkedin") or ""),
            "github": str(raw_info.get("github") or ""),
            "location": str(raw_info.get("location") or ""),
        }
    except Exception:
        contact = _extract_contact(original_resume)
    bullets = extract_bullets(original_resume)
    resume_skills = extract_skills(original_resume)
    skills = _dedupe([*matched, *resume_skills, *_string_list(jd_skills.get("preferred"))])
    title = _guess_title(original_resume)

    return {
        "contact": contact,
        "summary": _fallback_summary(title, skills, original_resume),
        "experience": [
            {
                "title": title,
                "company": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "duration": "",
                "bullets": [
                    {
                        "original": bullet,
                        "suggested": _improve_bullet(bullet),
                        "change_reason": "Improved for action, clarity, and ATS readability without adding unsupported claims.",
                    }
                    for bullet in bullets[:6]
                ],
            }
        ]
        if bullets
        else [],
        "projects": [],
        "education": _extract_education(original_resume),
        "certifications": [],
        "skills": skills,
        "ats_improvements": [
            "Preserved candidate-specific details from the uploaded resume.",
            "Grouped content into standard resume sections for ATS and recruiter readability.",
        ],
    }


def _normalize_experience(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "title": str(item.get("title") or ""),
                "company": str(item.get("company") or ""),
                "location": str(item.get("location") or ""),
                "start_date": str(item.get("start_date") or ""),
                "end_date": str(item.get("end_date") or ""),
                "duration": str(item.get("duration") or ""),
                "bullets": _normalize_draft_bullets(item.get("bullets")),
            }
        )
    return [item for item in result if item["title"] or item["company"] or item["bullets"]]


def _normalize_projects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                "technologies": _string_list(item.get("technologies")),
                "bullets": _normalize_draft_bullets(item.get("bullets")),
            }
        )
    return [item for item in result if item["name"] or item["description"] or item["bullets"]]


def _normalize_education(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "degree": str(item.get("degree") or ""),
                "institution": str(item.get("institution") or ""),
                "location": str(item.get("location") or ""),
                "year": str(item.get("year") or ""),
                "details": _string_list(item.get("details")),
            }
        )
    return [item for item in result if item["degree"] or item["institution"]]


def _normalize_certifications(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            result.append(
                {
                    "name": str(item.get("name") or ""),
                    "issuer": str(item.get("issuer") or ""),
                    "year": str(item.get("year") or ""),
                }
            )
        elif str(item).strip():
            result.append({"name": str(item).strip(), "issuer": "", "year": ""})
    return [item for item in result if item["name"]]


def _normalize_draft_bullets(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            original = str(item.get("original") or item.get("suggested") or "").strip()
            suggested = str(item.get("suggested") or original).strip()
            reason = str(item.get("change_reason") or "Improved resume impact and clarity.").strip()
        else:
            original = str(item).strip()
            suggested = original
            reason = "Kept from the original resume."
        if suggested:
            result.append({"original": original or suggested, "suggested": suggested, "change_reason": reason})
    return result


def _extract_contact(text: str) -> dict[str, str]:
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(\+?\d[\d\s().-]{7,}\d)", text)
    linkedin = re.search(r"https?://(?:www\.)?linkedin\.com/[^\s]+", text, re.I)
    github = re.search(r"https?://(?:www\.)?github\.com/[^\s]+", text, re.I)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    likely_name = first_line if 1 < len(first_line.split()) <= 5 and "@" not in first_line else ""
    return {
        "name": likely_name,
        "email": email.group(0) if email else "",
        "phone": phone.group(1).strip() if phone else "",
        "linkedin": linkedin.group(0) if linkedin else "",
        "github": github.group(0) if github else "",
        "location": "",
    }


def _extract_education(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    education = []
    degree_pattern = re.compile(r"\b(bachelor|master|bs|ms|bsc|msc|phd|degree|university|college)\b", re.I)
    for line in lines:
        if degree_pattern.search(line):
            education.append({"degree": line, "institution": "", "location": "", "year": "", "details": []})
    return education[:3]


def _fallback_summary(title: str, skills: list[str], original_resume: str) -> str:
    focus = ", ".join(skills[:4]) if skills else "the candidate's core technical skills"
    metric_phrase = " with measurable delivery impact" if has_metrics(original_resume) else ""
    return f"{title or 'Candidate'} with hands-on experience in {focus}{metric_phrase}. Skilled at turning requirements into practical, maintainable work while preserving the candidate's verified background."


def _guess_title(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip(" -•\t")
        if re.search(r"\b(engineer|developer|analyst|designer|manager|intern|specialist|consultant)\b", cleaned, re.I):
            return cleaned[:80]
    return "Professional"


def _improve_bullet(bullet: str) -> str:
    cleaned = bullet.strip().rstrip(".")
    if _starts_with_action_verb(cleaned):
        return f"{cleaned}."
    return f"Delivered {cleaned[0].lower() + cleaned[1:] if cleaned else 'role-relevant work'}."


def _resume_from_match_result(gap_analysis: dict[str, Any]) -> str:
    optimized = gap_analysis.get("optimizedResume") or gap_analysis.get("optimized_resume") or {}
    if not isinstance(optimized, dict):
        return ""
    return "\n".join(
        part
        for part in [
            str(optimized.get("summary", "")),
            "\n".join(str(bullet) for bullet in optimized.get("bullets", [])),
            ", ".join(str(skill) for skill in optimized.get("skills", [])),
        ]
        if part.strip()
    )


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("Draft generation failed")
        parsed = json.loads(match.group())
    if not isinstance(parsed, dict):
        raise ValueError("Draft generation returned non-object JSON")
    return parsed


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _starts_with_action_verb(bullet: str) -> bool:
    verbs = {"built", "created", "developed", "designed", "implemented", "optimized", "led", "automated", "delivered"}
    first = bullet.strip().split(" ", 1)[0].lower()
    return first in verbs

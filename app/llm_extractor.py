import json
import re
from typing import Any

from app.llm_client import call_llm
from app.services.extractors import extract_bullets, has_metrics


def extract_user_info(resume_text: str) -> dict[str, Any]:
    """Dedicated contact extraction — always copies phone exactly as written, never reformats."""
    prompt = f"""Extract contact information from this resume.
Return ONLY valid JSON with these exact keys:
{{
  "name": "Full Name (almost always the very first line of a resume)",
  "email": "email address or null",
  "phone": "phone number exactly as written in the resume, or null",
  "linkedin": "LinkedIn URL or null",
  "github": "GitHub URL or null",
  "location": "City, Country or null"
}}

Rules:
- name: use the first capitalized full name — usually the largest text at the very top
- phone: copy character-for-character from the resume — do NOT change format, country code, or add anything
- Return null for missing fields, never an empty string
- Return ONLY the JSON object, no explanation, no markdown

Resume (first 800 chars matter most):
{resume_text[:800]}
"""
    raw = call_llm(prompt, prefer_fast=False)
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        return {"name": None, "email": None, "phone": None, "linkedin": None, "github": None, "location": None}


def extract_skills_llm(text: str, source: str = "jd") -> dict[str, Any]:
    """
    source='jd' extracts job requirements.
    source='resume' extracts candidate profile signals.
    """
    prompt = _jd_prompt(text) if source == "jd" else _resume_prompt(text)
    raw = call_llm(prompt, prefer_fast=False)
    return _parse_json(raw)


def to_rule_based_jd_shape(jd_data: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "required": _string_list(jd_data.get("required_skills")),
        "preferred": _string_list(jd_data.get("preferred_skills")),
        "soft": _string_list(jd_data.get("soft_skills")),
    }


def to_resume_profile_shape(resume_data: dict[str, Any], resume_text: str) -> dict[str, object]:
    bullets = _experience_bullets(resume_data) or extract_bullets(resume_text)
    return {
        "text": resume_text,
        "skills": _string_list(resume_data.get("skills")),
        "bullets": bullets,
        "has_metrics": bool(resume_data.get("has_metrics")) or has_metrics(resume_text),
        "word_count": len(resume_text.split()),
        "parsed": {
            "name": resume_data.get("name"),
            "email": resume_data.get("email"),
            "phone": resume_data.get("phone"),
            "experience": resume_data.get("experience") if isinstance(resume_data.get("experience"), list) else [],
            "education": resume_data.get("education") if isinstance(resume_data.get("education"), list) else [],
            "summary": resume_data.get("summary"),
        },
    }


def _jd_prompt(text: str) -> str:
    return f"""
You are an ATS expert. Analyze this job description carefully.

Extract and return ONLY a valid JSON object with these exact keys:
{{
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill1", "skill2"],
  "soft_skills": ["skill1", "skill2"],
  "role_title": "exact job title",
  "experience_years": 2,
  "role_level": "junior|mid|senior|lead",
  "industry_keywords": ["keyword1", "keyword2"]
}}

Rules:
- required_skills = must-have, non-negotiable skills
- preferred_skills = nice-to-have, bonus skills
- Keep skill names short and exact, for example "React.js" not "experience with React.js"
- experience_years = integer or null
- Return ONLY the JSON, no explanation, no markdown

Job Description:
{text[:3500]}
"""


def _resume_prompt(text: str) -> str:
    return f"""
You are a resume parser. Extract all skills from this resume.

Return ONLY a valid JSON object:
{{
  "name": "candidate name or null",
  "email": "email or null",
  "phone": "phone or null",
  "skills": ["skill1", "skill2"],
  "experience_titles": ["title1", "title2"],
  "experience": [
    {{
      "title": "job title",
      "company": "company name or null",
      "duration": "duration or null",
      "bullets": ["bullet1", "bullet2"]
    }}
  ],
  "education": [
    {{
      "degree": "degree or null",
      "institution": "institution or null",
      "year": "year or null"
    }}
  ],
  "summary": "existing summary/objective or null",
  "total_experience_years": 3,
  "education_level": "bachelors|masters|phd|other",
  "has_github": true,
  "has_linkedin": true,
  "bullet_count": 12,
  "has_metrics": true
}}

Rules:
- skills = every technical + tool skill mentioned anywhere
- has_metrics = true if any bullet has numbers/percentages
- Return ONLY the JSON, no explanation, no markdown

Resume:
{text[:3500]}
"""


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"```json|```", "", raw).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"LLM returned invalid JSON: {cleaned[:200]}")
        parsed = json.loads(match.group())

    if not isinstance(parsed, dict):
        raise ValueError("LLM returned JSON, but it was not an object.")
    return parsed


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _experience_bullets(resume_data: dict[str, Any]) -> list[str]:
    experience = resume_data.get("experience")
    if not isinstance(experience, list):
        return []

    bullets: list[str] = []
    for item in experience:
        if not isinstance(item, dict):
            continue
        for bullet in item.get("bullets", []):
            text = str(bullet).strip()
            if text:
                bullets.append(text)
    return bullets[:8]

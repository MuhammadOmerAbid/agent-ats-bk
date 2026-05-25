import json
import re
from typing import Any

from app.llm_client import call_llm


def optimize_resume_llm(
    resume_text: str,
    jd_skills: dict[str, list[str]],
    gap_analysis: dict[str, Any],
    role_title: str = "",
) -> dict[str, object]:
    missing = gap_analysis.get("missing_required", [])
    matched = gap_analysis.get("matched_required", [])
    before_score = gap_analysis.get("before_score", 0)

    prompt = f"""
You are an expert resume writer specializing in ATS optimization.

TARGET ROLE: {role_title}
CURRENT ATS SCORE: {before_score}%
MISSING REQUIRED SKILLS: {missing}
MATCHED SKILLS: {matched}
JOB SKILLS: {jd_skills}

ORIGINAL RESUME:
{resume_text[:3000]}

YOUR TASK:
1. Write a powerful 2-3 sentence professional summary targeting this exact role
2. Rewrite 4-6 experience bullet points to:
   - Naturally include missing skills where truthful/relevant
   - Add quantified impact only when it is realistic and clearly phrased
   - Start with strong action verbs like Built, Developed, Optimized, Led
3. Suggest a skills section order with required skills first

STRICT RULES:
- Never fabricate experience, companies, degrees, or certifications
- Only add skills that could realistically apply to existing work
- Keep wording professional and natural, not keyword-stuffed

Return ONLY valid JSON:
{{
  "optimized_summary": "2-3 sentence summary here",
  "rewritten_bullets": [
    "Bullet 1 with action verb and impact",
    "Bullet 2 with action verb and impact"
  ],
  "skills_order": ["skill1", "skill2"],
  "keywords_added": ["keyword1", "keyword2"],
  "optimization_notes": "Brief explanation of what was changed and why"
}}
"""

    raw = call_llm(prompt, prefer_fast=True)
    result = _parse_json(raw, matched, missing, role_title)

    return {
        "summary": str(result.get("optimized_summary") or f"Results-driven professional targeting {role_title} role."),
        "skills": _string_list(result.get("skills_order"))[:18],
        "bullets": _string_list(result.get("rewritten_bullets")),
        "truthful_framing_notes": [
            str(result.get("optimization_notes") or "LLM optimized this draft for ATS alignment."),
            "Review every added keyword for truthfulness before applying.",
        ],
    }


def _parse_json(raw: str, matched: Any, missing: Any, role_title: str) -> dict[str, Any]:
    cleaned = re.sub(r"```json|```", "", raw).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
        else:
            parsed = {
                "optimized_summary": f"Results-driven professional targeting {role_title} role.",
                "rewritten_bullets": [],
                "skills_order": [*list(matched or []), *list(missing or [])],
                "keywords_added": [],
                "optimization_notes": "LLM optimization unavailable, showing rule-based-compatible result.",
            }

    if not isinstance(parsed, dict):
        raise ValueError("LLM returned JSON, but it was not an object.")
    return parsed


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]

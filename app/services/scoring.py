import re


def calculate_match_score(jd_skills: dict[str, list[str]], resume_profile: dict[str, object]) -> dict[str, object]:
    resume_skills = [str(skill) for skill in resume_profile.get("skills", [])]
    normalized_resume_skills = {_normalize_skill(skill) for skill in resume_skills}
    required = jd_skills.get("required", [])
    preferred = jd_skills.get("preferred", [])

    matched_required = [skill for skill in required if _normalize_skill(skill) in normalized_resume_skills]
    missing_required = [skill for skill in required if _normalize_skill(skill) not in normalized_resume_skills]
    matched_preferred = [skill for skill in preferred if _normalize_skill(skill) in normalized_resume_skills]
    missing_preferred = [skill for skill in preferred if _normalize_skill(skill) not in normalized_resume_skills]

    required_score = _weighted_score(len(matched_required), len(required), 70)
    preferred_score = _weighted_score(len(matched_preferred), len(preferred), 20)
    quality_score = _quality_score(resume_profile)
    final_score = min(100, required_score + preferred_score + quality_score)

    return {
        "before_score": final_score,
        "after_score_estimate": _estimate_after_score(final_score, missing_required, missing_preferred),
        "risk_level": _risk_level(final_score, missing_required),
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_preferred": matched_preferred,
        "missing_preferred": missing_preferred,
        "keyword_density": keyword_density(str(resume_profile.get("text", "")), required + preferred),
        "score_breakdown": {
            "required_score": required_score,
            "preferred_score": preferred_score,
            "quality_score": quality_score,
            "final_score": final_score,
        },
        "recommendations": build_recommendations(missing_required, missing_preferred, resume_profile),
    }


def keyword_density(text: str, skills: list[str]) -> list[dict[str, object]]:
    words = max(1, len(text.split()))
    lowered = text.lower()
    results = []

    for skill in skills:
        count = len(re.findall(rf"(?<![a-z0-9]){re.escape(skill.lower())}(?![a-z0-9])", lowered))
        results.append({"skill": skill, "count": count, "density": round((count / words) * 100, 2)})

    return sorted(results, key=lambda item: (-int(item["count"]), str(item["skill"])))


def build_recommendations(
    missing_required: list[str],
    missing_preferred: list[str],
    resume_profile: dict[str, object],
) -> list[str]:
    recommendations: list[str] = []
    if missing_required:
        recommendations.append(
            "Add truthful evidence for required skills: " + ", ".join(missing_required[:5]) + "."
        )
    if missing_preferred:
        recommendations.append(
            "Preferred skills can improve ranking: " + ", ".join(missing_preferred[:4]) + "."
        )
    if not resume_profile.get("has_metrics"):
        recommendations.append("Add measurable outcomes such as performance gains, users served, or time saved.")
    if len(resume_profile.get("bullets", [])) < 3:
        recommendations.append("Use concise achievement bullets so ATS and recruiters can scan impact quickly.")

    return recommendations or ["Resume already covers the key ATS signals for this job."]


def _weighted_score(matched: int, total: int, weight: int) -> int:
    if total == 0:
        return weight
    return round((matched / total) * weight)


def _quality_score(resume_profile: dict[str, object]) -> int:
    score = 0
    bullets = [str(bullet) for bullet in resume_profile.get("bullets", [])]

    if resume_profile.get("has_metrics"):
        score += 4
    if len(bullets) >= 3:
        score += 3
    if any(_starts_with_action_verb(bullet) for bullet in bullets):
        score += 3

    return min(score, 10)


def _starts_with_action_verb(bullet: str) -> bool:
    action_verbs = {
        "built",
        "created",
        "developed",
        "designed",
        "implemented",
        "improved",
        "optimized",
        "led",
        "launched",
        "automated",
    }
    first_word = bullet.strip().split(" ", 1)[0].lower()
    return first_word in action_verbs


def _estimate_after_score(current_score: int, missing_required: list[str], missing_preferred: list[str]) -> int:
    possible_gain = min(22, len(missing_required) * 5 + len(missing_preferred) * 2 + 6)
    return min(97, current_score + possible_gain)


def _risk_level(score: int, missing_required: list[str]) -> str:
    if score < 55 or len(missing_required) >= 4:
        return "high"
    if score < 75 or missing_required:
        return "medium"
    return "low"


def _normalize_skill(skill: str) -> str:
    aliases = {
        "react.js": "react",
        "reactjs": "react",
        "next.js": "react",
        "nextjs": "react",
        "node": "nodejs",
        "node.js": "nodejs",
        "postgres": "postgresql",
        "postgresql": "postgresql",
        "rest api": "restapis",
        "rest apis": "restapis",
        "restful api": "restapis",
        "github actions": "cicd",
        "ci/cd": "cicd",
        "cicd": "cicd",
    }
    cleaned = re.sub(r"[^a-z0-9+#.]+", " ", skill.lower()).strip()
    compact = cleaned.replace(" ", "")
    return aliases.get(cleaned, aliases.get(compact, compact))

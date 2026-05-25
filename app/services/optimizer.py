import os


ACTION_VERBS = ["Developed", "Implemented", "Optimized", "Built", "Automated", "Designed"]


def optimize_resume(
    resume_profile: dict[str, object],
    jd_skills: dict[str, list[str]],
    score: dict[str, object],
    target_role: str | None = None,
) -> dict[str, object]:
    resume_skills = [str(skill) for skill in resume_profile.get("skills", [])]
    priority_skills = _dedupe(
        [*jd_skills.get("required", []), *resume_skills, *jd_skills.get("preferred", [])]
    )

    notes = [
        "Only add missing skills if you have real coursework, projects, or work evidence for them.",
        "Use project links or GitHub proof when a required skill is not from professional experience.",
    ]
    if os.getenv("OPENAI_API_KEY"):
        notes.append("OPENAI_API_KEY detected; wire the provider call here for LLM rewriting.")

    return {
        "summary": _build_summary(priority_skills, score, target_role),
        "skills": priority_skills[:18],
        "bullets": _rewrite_bullets([str(bullet) for bullet in resume_profile.get("bullets", [])], priority_skills),
        "truthful_framing_notes": notes,
    }


def _build_summary(priority_skills: list[str], score: dict[str, object], target_role: str | None) -> str:
    role = target_role or "target role"
    matched = [str(skill) for skill in score.get("matched_required", [])][:4]
    missing = [str(skill) for skill in score.get("missing_required", [])][:3]
    strongest = ", ".join(matched or priority_skills[:4] or ["relevant technical skills"])

    summary = (
        f"Results-driven candidate for the {role} with hands-on experience across {strongest}. "
        "Focused on building reliable, user-centered solutions and translating job requirements into measurable outcomes."
    )
    if missing:
        summary += f" Add truthful project evidence for {', '.join(missing)} to strengthen ATS alignment."
    return summary


def _rewrite_bullets(bullets: list[str], priority_skills: list[str]) -> list[str]:
    if not bullets:
        return [
            f"Developed a portfolio-ready project demonstrating {', '.join(priority_skills[:3] or ['role-relevant skills'])} with clear documentation and measurable outcomes."
        ]

    rewritten = []
    for index, bullet in enumerate(bullets[:5]):
        verb = ACTION_VERBS[index % len(ACTION_VERBS)]
        clean = bullet.strip().rstrip(".")
        if clean.split(" ", 1)[0].lower() in {action.lower() for action in ACTION_VERBS}:
            rewritten.append(f"{clean}.")
            continue

        skill_hint = priority_skills[index % len(priority_skills)] if priority_skills else "role-relevant tools"
        rewritten.append(f"{verb} {clean} using {skill_hint}, improving clarity, delivery quality, and ATS keyword alignment.")

    return rewritten


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

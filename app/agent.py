from __future__ import annotations

import os

from app.llm_client import GROQ_FREE_MODELS, call_llm, groq_client
from app.services.extractors import extract_jd_skills, extract_resume_profile
from app.services.optimizer import optimize_resume
from app.services.scoring import calculate_match_score

SYSTEM_PROMPT = """
You are an AI Career Copilot. You think like:
- An ATS system (keyword matching, formatting rules)
- A senior recruiter (what makes candidates stand out)
- A hiring manager (what problems does this person solve)
- An interview coach (how to prepare, what to expect)
- A career mentor (long-term growth, skill gaps)

You have 5 capabilities:
1. ANALYZE   - parse and score a resume
2. CRITIQUE  - find specific weaknesses with examples
3. ENHANCE   - rewrite and optimize with user approval
4. INTERVIEW - generate questions, run mock interview
5. ROADMAP   - suggest career path and skill gaps

Current conversation state is passed to you each time.
Always be specific. Never give generic advice.
When you find a problem, show the exact line that has the problem.
When you suggest improvement, show before AND after.
If an AUTHORITATIVE ATS MATCH RESULT is available, use only that score. Never recalculate or invent a different ATS score.
Format responses in clear Markdown with short ATX headings like ## ATS Score, bullets, and bold labels where useful.
"""


def chat_with_agent(
    messages: list[dict[str, str]],
    resume_text: str = "",
    jd_text: str = "",
    match_result: dict | None = None,
) -> str:
    safe_messages = _sanitize_messages(messages)
    context = _build_context(resume_text, jd_text, safe_messages, match_result)

    full_messages: list[dict[str, str]] = [
        {"role": "user", "content": SYSTEM_PROMPT + context + "\n\nConversation starts now."},
        {"role": "assistant", "content": "Understood. I'm ready to help as your AI Career Copilot."},
        *safe_messages,
    ]
    return call_llm_chat(full_messages)


def call_llm_chat(messages: list[dict[str, str]], max_tokens: int = 2000) -> str:
    if groq_client:
        for model in _candidate_chat_models():
            try:
                response = groq_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.4,
                )
                text = (response.choices[0].message.content or "").strip()
                if text:
                    return text
            except Exception as error:
                print(f"[Agent] Groq chat failed on {model}: {error}")

    prompt = _messages_to_prompt(messages)
    return call_llm(prompt, prefer_fast=False, max_tokens=max_tokens)


def _build_context(
    resume_text: str,
    jd_text: str,
    messages: list[dict[str, str]],
    match_result: dict | None = None,
) -> str:
    parts: list[str] = []
    if resume_text:
        parts.append(f"CANDIDATE RESUME:\n{resume_text[:4500]}")
    if jd_text:
        parts.append(f"TARGET JOB DESCRIPTION:\n{jd_text[:3000]}")

    latest_user_message = ""
    for message in reversed(messages):
        if message["role"] == "user":
            latest_user_message = message["content"]
            break

    score_snapshot = _build_authoritative_score_snapshot(match_result)
    if not score_snapshot:
        score_snapshot = _maybe_build_score_snapshot(latest_user_message, resume_text, jd_text)
    if score_snapshot:
        parts.append("ATS SNAPSHOT:\n" + score_snapshot)

    optimize_snapshot = _maybe_build_optimizer_snapshot(latest_user_message, resume_text, jd_text)
    if optimize_snapshot:
        parts.append("OPTIMIZER SNAPSHOT:\n" + optimize_snapshot)

    if not parts:
        return ""
    return "\n\n" + "\n\n".join(parts)


def _build_authoritative_score_snapshot(match_result: dict | None) -> str:
    if not isinstance(match_result, dict):
        return ""

    before_score = match_result.get("beforeScore", match_result.get("before_score"))
    after_score = match_result.get("afterScoreEstimate", match_result.get("after_score_estimate"))
    if before_score is None:
        return ""

    return (
        "AUTHORITATIVE ATS MATCH RESULT - use these exact scores in chat.\n"
        f"before_score={before_score}\n"
        f"after_score_estimate={after_score if after_score is not None else 'unknown'}\n"
        f"risk_level={match_result.get('riskLevel', match_result.get('risk_level', 'unknown'))}\n"
        f"matched_required={', '.join(_string_list(match_result.get('matchedRequired', match_result.get('matched_required')))[:8]) or 'None'}\n"
        f"missing_required={', '.join(_string_list(match_result.get('missingRequired', match_result.get('missing_required')))[:8]) or 'None'}\n"
        f"matched_preferred={', '.join(_string_list(match_result.get('matchedPreferred', match_result.get('matched_preferred')))[:8]) or 'None'}\n"
        f"missing_preferred={', '.join(_string_list(match_result.get('missingPreferred', match_result.get('missing_preferred')))[:8]) or 'None'}\n"
        f"recommendations={'; '.join(_string_list(match_result.get('recommendations'))[:4]) or 'None'}"
    )


def _maybe_build_score_snapshot(last_user_message: str, resume_text: str, jd_text: str) -> str:
    if not resume_text or not jd_text or not _looks_like_score_request(last_user_message):
        return ""

    try:
        jd_skills = extract_jd_skills(jd_text)
        resume_profile = extract_resume_profile(resume_text)
        score = calculate_match_score(jd_skills, resume_profile)
    except Exception as error:
        print(f"[Agent] Score snapshot failed: {error}")
        return ""

    return (
        f"before_score={score.get('before_score', 0)}\n"
        f"risk_level={score.get('risk_level', 'unknown')}\n"
        f"matched_required={', '.join(score.get('matched_required', [])[:8]) or 'None'}\n"
        f"missing_required={', '.join(score.get('missing_required', [])[:8]) or 'None'}\n"
        f"matched_preferred={', '.join(score.get('matched_preferred', [])[:8]) or 'None'}\n"
        f"missing_preferred={', '.join(score.get('missing_preferred', [])[:8]) or 'None'}\n"
        f"recommendations={'; '.join(score.get('recommendations', [])[:4])}"
    )


def _looks_like_score_request(text: str) -> bool:
    lowered = text.lower()
    triggers = [
        "ats score",
        "score",
        "fit",
        "match",
        "how good is my resume",
        "resume score",
    ]
    return any(trigger in lowered for trigger in triggers)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _maybe_build_optimizer_snapshot(last_user_message: str, resume_text: str, jd_text: str) -> str:
    if not resume_text or not jd_text or not _looks_like_optimize_request(last_user_message):
        return ""

    try:
        jd_skills = extract_jd_skills(jd_text)
        resume_profile = extract_resume_profile(resume_text)
        score = calculate_match_score(jd_skills, resume_profile)
        optimized = optimize_resume(resume_profile, jd_skills, score, target_role=None)
    except Exception as error:
        print(f"[Agent] Optimizer snapshot failed: {error}")
        return ""

    bullets = [str(bullet) for bullet in optimized.get("bullets", [])[:3]]
    skills = [str(skill) for skill in optimized.get("skills", [])[:10]]
    notes = [str(note) for note in optimized.get("truthful_framing_notes", [])[:2]]
    return (
        f"draft_summary={optimized.get('summary', '')}\n"
        f"suggested_skills={', '.join(skills) or 'None'}\n"
        f"suggested_bullets={' | '.join(bullets) or 'None'}\n"
        f"truthfulness_notes={'; '.join(notes) or 'None'}"
    )


def _looks_like_optimize_request(text: str) -> bool:
    lowered = text.lower()
    triggers = [
        "optimize",
        "improve",
        "rewrite",
        "enhance",
        "fix my resume",
    ]
    return any(trigger in lowered for trigger in triggers)


def _sanitize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    safe_messages: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "")).strip().lower()
        content = str(message.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        safe_messages.append({"role": role, "content": content})
    return safe_messages[-20:]


def _candidate_chat_models() -> list[str]:
    preferred = os.getenv("GROQ_CHAT_MODEL", "").strip()
    models = [preferred, *GROQ_FREE_MODELS]
    seen: set[str] = set()
    unique: list[str] = []
    for model in models:
        if not model or model in seen:
            continue
        seen.add(model)
        unique.append(model)
    return unique


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message["role"].capitalize()
        lines.append(f"{role}: {message['content']}")
    lines.append("Assistant:")
    return "\n".join(lines)

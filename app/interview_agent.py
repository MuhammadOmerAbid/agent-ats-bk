from __future__ import annotations

import json
import os
import re

from groq import Groq

from app.llm_client import call_llm


def generate_interview_questions(resume_text: str, jd_text: str = "") -> dict[str, object]:
    prompt = f"""
You are a senior technical interviewer. Based on this resume and job description,
generate a complete interview question set.

RESUME:
{resume_text[:3000]}

JOB DESCRIPTION:
{jd_text[:1500] if jd_text else "Not provided - generate based on resume skills"}

Generate questions across all rounds. Return ONLY valid JSON:
{{
  "role_detected": "e.g. Frontend Developer",
  "seniority": "junior | mid | senior",
  "rounds": [
    {{
      "round": "HR / Behavioural",
      "questions": [
        {{
          "question": "Tell me about yourself.",
          "type": "behavioural",
          "difficulty": "easy",
          "what_interviewer_wants": "Communication skills, career narrative",
          "strong_answer_tip": "Use Present-Past-Future structure. Keep under 2 minutes."
        }}
      ]
    }},
    {{
      "round": "Technical",
      "questions": [
        {{
          "question": "Explain how React reconciliation works.",
          "type": "conceptual",
          "difficulty": "medium",
          "what_interviewer_wants": "Deep understanding of React internals",
          "strong_answer_tip": "Mention virtual DOM, diffing algorithm, fiber architecture."
        }}
      ]
    }},
    {{
      "round": "Problem Solving",
      "questions": [
        {{
          "question": "How would you optimize a slow database query?",
          "type": "problem_solving",
          "difficulty": "hard",
          "what_interviewer_wants": "Systematic debugging approach",
          "strong_answer_tip": "Start with EXPLAIN, mention indexing, query structure, caching."
        }}
      ]
    }},
    {{
      "round": "Resume Deep Dive",
      "questions": [
        {{
          "question": "Walk me through your most complex project.",
          "type": "experience",
          "difficulty": "medium",
          "what_interviewer_wants": "Technical depth, ownership, problem solving",
          "strong_answer_tip": "Use STAR method. Focus on YOUR contribution specifically."
        }}
      ]
    }}
  ],
  "weak_areas_detected": [
    "No quantified achievements - prepare numbers for every project",
    "Gap in cloud experience - brush up on basic AWS/GCP concepts"
  ],
  "preparation_tips": [
    "Research the company product before the interview",
    "Prepare 3 examples of handling technical challenges"
  ]
}}

Return ONLY valid JSON, no explanation.
"""
    raw = call_llm(prompt, prefer_fast=False)
    parsed = _parse_json_object(raw)
    return _normalize_question_bank(parsed)


def evaluate_answer(
    question: str,
    user_answer: str,
    role: str,
    what_interviewer_wants: str,
) -> dict[str, object]:
    prompt = f"""
You are a strict but fair interviewer evaluating a candidate's answer.

ROLE: {role}
QUESTION: {question}
WHAT INTERVIEWER WANTS: {what_interviewer_wants}

CANDIDATE ANSWER:
{user_answer}

Evaluate honestly. Return ONLY valid JSON:
{{
  "score": 7,
  "score_out_of": 10,
  "verdict": "Good | Needs Work | Excellent | Poor",
  "strengths": ["mentioned specific technology", "used concrete example"],
  "weaknesses": ["answer too vague", "no quantified impact mentioned"],
  "ideal_answer_structure": "Start with X, then mention Y, close with Z",
  "follow_up_question": "Can you elaborate on how you handled the performance issue?",
  "confidence_tip": "Speak slower on technical terms - it signals mastery not uncertainty"
}}

Be specific. Reference the actual answer text in your feedback.
Return ONLY valid JSON.
"""
    raw = call_llm(prompt, prefer_fast=True)
    try:
        parsed = _parse_json_object(raw)
        return _normalize_evaluation(parsed)
    except Exception:
        return {
            "score": 5,
            "score_out_of": 10,
            "verdict": "Needs Work",
            "strengths": [],
            "weaknesses": ["Could not evaluate properly"],
            "ideal_answer_structure": "Try again with more detail",
            "follow_up_question": question,
            "confidence_tip": "",
        }


def run_mock_interview_turn(conversation: list[dict[str, str]], resume_text: str, role: str) -> str:
    system = f"""
You are conducting a real job interview for the role of {role}.
You have read the candidate's resume. Ask one question at a time.
After each answer, give brief feedback (1-2 lines) then ask the next question.
Be professional but conversational. Vary question types: HR, technical, situational.
Do NOT give away answers. Push back if answers are vague.
If candidate says "end interview" or "stop", give a final overall assessment.

CANDIDATE RESUME SUMMARY:
{resume_text[:1500]}
"""
    messages = [
        {"role": "user", "content": system},
        {
            "role": "assistant",
            "content": (
                f"Great, let's begin your interview for the {role} position. "
                "I've reviewed your background. Let's start - tell me about yourself and why you're interested in this role."
            ),
        },
    ]
    messages.extend(_sanitize_conversation(conversation))
    return call_llm_chat(messages)


def call_llm_chat(messages: list[dict[str, str]], max_tokens: int = 1000) -> str:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        client = Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model=os.getenv("GROQ_INTERVIEW_MODEL", "llama-3.1-8b-instant"),
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.5,
        )
        return (response.choices[0].message.content or "").strip()

    prompt = "\n".join([f"{message['role'].capitalize()}: {message['content']}" for message in messages]) + "\nAssistant:"
    return call_llm(prompt, prefer_fast=False, max_tokens=max_tokens)


def _parse_json_object(raw: str) -> dict[str, object]:
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        loaded = json.loads(cleaned)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("JSON object not found in model output")
    loaded = json.loads(match.group())
    if not isinstance(loaded, dict):
        raise ValueError("Parsed JSON is not an object")
    return loaded


def _sanitize_conversation(conversation: list[dict[str, str]]) -> list[dict[str, str]]:
    sanitized: list[dict[str, str]] = []
    for message in conversation:
        role = str(message.get("role", "")).strip().lower()
        content = str(message.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        sanitized.append({"role": role, "content": content})
    return sanitized[-30:]


def _normalize_question_bank(payload: dict[str, object]) -> dict[str, object]:
    payload.setdefault("role_detected", "General Software Role")
    payload.setdefault("seniority", "mid")
    rounds = payload.get("rounds")
    if not isinstance(rounds, list):
        payload["rounds"] = []
    payload.setdefault("weak_areas_detected", [])
    payload.setdefault("preparation_tips", [])
    return payload


def _normalize_evaluation(payload: dict[str, object]) -> dict[str, object]:
    payload.setdefault("score", 5)
    payload.setdefault("score_out_of", 10)
    payload.setdefault("verdict", "Needs Work")
    payload.setdefault("strengths", [])
    payload.setdefault("weaknesses", [])
    payload.setdefault("ideal_answer_structure", "")
    payload.setdefault("follow_up_question", "")
    payload.setdefault("confidence_tip", "")
    return payload

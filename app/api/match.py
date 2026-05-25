import copy
import hashlib
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.llm_client import has_llm_keys
from app.llm_extractor import extract_skills_llm, to_resume_profile_shape, to_rule_based_jd_shape
from app.llm_optimizer import optimize_resume_llm
from app.schemas import MatchRequest, MatchResponse
from app.services.extractors import (
    extract_jd_skills,
    extract_jd_text,
    extract_resume_profile,
    extract_text_from_upload,
    has_metrics,
    is_probably_job_description,
    is_url,
)
from app.services.optimizer import optimize_resume
from app.services.scoring import calculate_match_score

router = APIRouter(prefix="/api", tags=["matching"])
MATCH_CACHE: dict[str, dict[str, object]] = {}


@router.post("/match", response_model=MatchResponse)
async def match_resume(payload: MatchRequest) -> MatchResponse:
    return _build_match_response(payload.jd_text, payload.resume_text, payload.target_role)


@router.post("/match/upload", response_model=MatchResponse)
async def match_resume_upload(
    jd_text: str = Form(default=""),
    resume_text: str = Form(default=""),
    target_role: str | None = Form(default=None),
    jd_file: UploadFile | None = File(default=None),
    resume_file: UploadFile | None = File(default=None),
) -> MatchResponse:
    if jd_file:
        try:
            jd_content = await jd_file.read()
            jd_text = await extract_text_from_upload(jd_file.filename or "job-description.txt", jd_content)
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"Could not extract text from JD file/image: {error}") from error
    if len(jd_text.strip()) < 5:
        raise HTTPException(status_code=400, detail="Paste a job description, URL, or upload a JD image/file.")

    if resume_file:
        try:
            content = await resume_file.read()
            resume_text = await extract_text_from_upload(resume_file.filename or "resume.txt", content)
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"Could not extract text from resume file/image: {error}") from error
    if len(resume_text.strip()) < 40:
        raise HTTPException(status_code=400, detail="Paste resume text or upload a readable resume file/image.")

    return _build_match_response(jd_text, resume_text, target_role)


def _build_match_response(jd_text: str, resume_text: str, target_role: str | None) -> MatchResponse:
    original_jd_source = jd_text
    try:
        jd_text = extract_jd_text(jd_text)
    except Exception as error:
        if is_url(original_jd_source):
            raise HTTPException(
                status_code=400,
                detail="Could not read this URL. Please enter a public and relevant job description URL.",
            ) from error
        print(f"[JD] URL extraction failed, using original input: {error}")

    if is_url(original_jd_source) and not is_probably_job_description(jd_text):
        raise HTTPException(
            status_code=400,
            detail="This URL does not look like a relevant job description. Please enter a valid job post URL or paste the JD text.",
        )

    cache_key = _cache_key(jd_text, resume_text, target_role)
    if cache_key in MATCH_CACHE:
        return MatchResponse(**copy.deepcopy(MATCH_CACHE[cache_key]))

    llm_powered = has_llm_keys()
    role_title = target_role or ""

    if llm_powered:
        try:
            jd_data = extract_skills_llm(jd_text, source="jd")
            resume_data = extract_skills_llm(resume_text, source="resume")
            jd_skills = to_rule_based_jd_shape(jd_data)
            resume_profile = to_resume_profile_shape(resume_data, resume_text)
            role_title = str(jd_data.get("role_title") or target_role or "")
        except Exception as error:
            print(f"[LLM] Extraction failed, using rule-based fallback: {error}")
            llm_powered = False
            jd_skills = extract_jd_skills(jd_text)
            resume_profile = extract_resume_profile(resume_text)
    else:
        jd_skills = extract_jd_skills(jd_text)
        resume_profile = extract_resume_profile(resume_text)

    score = calculate_match_score(jd_skills, resume_profile)

    if llm_powered:
        try:
            optimized = optimize_resume_llm(resume_text, jd_skills, score, role_title)
        except Exception as error:
            print(f"[LLM] Optimization failed, using rule-based fallback: {error}")
            llm_powered = False
            optimized = optimize_resume(resume_profile, jd_skills, score, target_role)
    else:
        optimized = optimize_resume(resume_profile, jd_skills, score, target_role)

    score["after_score_estimate"] = _calculate_after_score(jd_skills, optimized, score)

    response = MatchResponse(
        llm_powered=llm_powered,
        before_score=score["before_score"],
        after_score_estimate=score["after_score_estimate"],
        risk_level=score["risk_level"],
        jd_skills=jd_skills,
        resume_skills=resume_profile["skills"],
        matched_required=score["matched_required"],
        missing_required=score["missing_required"],
        matched_preferred=score["matched_preferred"],
        missing_preferred=score["missing_preferred"],
        keyword_density=score["keyword_density"],
        score_breakdown=score["score_breakdown"],
        recommendations=score["recommendations"],
        optimized_resume=optimized,
    )
    MATCH_CACHE[cache_key] = response.model_dump(by_alias=True)
    return response


def _calculate_after_score(
    jd_skills: dict[str, list[str]],
    optimized: dict[str, object],
    original_score: dict[str, object],
) -> int:
    optimized_text = "\n".join(
        [
            str(optimized.get("summary", "")),
            " ".join(str(skill) for skill in optimized.get("skills", [])),
            "\n".join(str(bullet) for bullet in optimized.get("bullets", [])),
        ]
    )
    optimized_profile = {
        "text": optimized_text,
        "skills": [str(skill) for skill in optimized.get("skills", [])],
        "bullets": [str(bullet) for bullet in optimized.get("bullets", [])],
        "has_metrics": has_metrics(optimized_text),
        "word_count": len(optimized_text.split()),
    }
    optimized_score = calculate_match_score(jd_skills, optimized_profile)
    return max(int(original_score["before_score"]), int(optimized_score["before_score"]))


def _cache_key(jd_text: str, resume_text: str, target_role: str | None) -> str:
    payload = {
        "jd_text": " ".join(jd_text.split()).lower(),
        "resume_text": " ".join(resume_text.split()).lower(),
        "target_role": (target_role or "").strip().lower(),
        "llm_powered": has_llm_keys(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

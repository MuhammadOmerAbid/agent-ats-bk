from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MatchRequest(BaseModel):
    jd_text: str = Field(..., min_length=5, alias="jdText")
    resume_text: str = Field(..., min_length=40, alias="resumeText")
    target_role: str | None = Field(default=None, alias="targetRole")

    model_config = ConfigDict(populate_by_name=True)


class SkillBreakdown(BaseModel):
    required: list[str]
    preferred: list[str]
    soft: list[str]


class KeywordDensity(BaseModel):
    skill: str
    count: int
    density: float


class ScoreBreakdown(BaseModel):
    required_score: int = Field(alias="requiredScore")
    preferred_score: int = Field(alias="preferredScore")
    quality_score: int = Field(alias="qualityScore")
    final_score: int = Field(alias="finalScore")

    model_config = ConfigDict(populate_by_name=True)


class OptimizedResume(BaseModel):
    summary: str
    skills: list[str]
    bullets: list[str]
    truthful_framing_notes: list[str] = Field(alias="truthfulFramingNotes")

    model_config = ConfigDict(populate_by_name=True)


class MatchResponse(BaseModel):
    llm_powered: bool = Field(alias="llmPowered")
    before_score: int = Field(alias="beforeScore")
    after_score_estimate: int = Field(alias="afterScoreEstimate")
    risk_level: Literal["low", "medium", "high"] = Field(alias="riskLevel")
    jd_skills: SkillBreakdown = Field(alias="jdSkills")
    resume_skills: list[str] = Field(alias="resumeSkills")
    matched_required: list[str] = Field(alias="matchedRequired")
    missing_required: list[str] = Field(alias="missingRequired")
    matched_preferred: list[str] = Field(alias="matchedPreferred")
    missing_preferred: list[str] = Field(alias="missingPreferred")
    keyword_density: list[KeywordDensity] = Field(alias="keywordDensity")
    score_breakdown: ScoreBreakdown = Field(alias="scoreBreakdown")
    recommendations: list[str]
    optimized_resume: OptimizedResume = Field(alias="optimizedResume")

    model_config = ConfigDict(populate_by_name=True)

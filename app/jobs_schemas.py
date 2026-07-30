from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class JobSummary(BaseModel):
    id: str
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    remote_type: Optional[str] = Field(default=None, alias="remoteType")
    tags: list[str] = []
    salary_min_usd: Optional[int] = Field(default=None, alias="salaryMinUsd")
    salary_max_usd: Optional[int] = Field(default=None, alias="salaryMaxUsd")
    fit_score: Optional[int] = Field(default=None, alias="fitScore")
    red_flags: list[str] = Field(default=[], alias="redFlags")
    source: str
    posted_at: Optional[str] = Field(default=None, alias="postedAt")
    selected_status: Optional[str] = Field(default=None, alias="selectedStatus")
    applied_status: Optional[str] = Field(default=None, alias="appliedStatus")

    model_config = ConfigDict(populate_by_name=True)


class ApplicationHistoryEntry(BaseModel):
    status: str
    applied_at: str = Field(alias="appliedAt")
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class JobDetail(JobSummary):
    jd_text: str = Field(alias="jdText")
    apply_url: str = Field(alias="applyUrl")
    reasons: list[str] = []
    llm_powered: bool = Field(default=False, alias="llmPowered")
    application_history: list[ApplicationHistoryEntry] = Field(default=[], alias="applicationHistory")

    model_config = ConfigDict(populate_by_name=True)


class SelectRequest(BaseModel):
    status: str  # "selected" | "dismissed"


class AppliedRequest(BaseModel):
    status: str  # "applied" | "interviewing" | "rejected" | "offer" | "withdrawn"
    notes: str = ""

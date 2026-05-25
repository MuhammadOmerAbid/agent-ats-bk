from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    location: str = ""


class DraftBullet(BaseModel):
    original: str = ""
    suggested: str = ""
    change_reason: str = Field(default="", alias="change_reason")


class ExperienceItem(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    start_date: str = Field(default="", alias="start_date")
    end_date: str = Field(default="", alias="end_date")
    duration: str = ""
    bullets: list[DraftBullet] = []


class ProjectItem(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = []
    bullets: list[DraftBullet] = []


class EducationItem(BaseModel):
    degree: str = ""
    institution: str = ""
    location: str = ""
    year: str = ""
    details: list[str] = []


class CertificationItem(BaseModel):
    name: str = ""
    issuer: str = ""
    year: str = ""


class ResumeDraft(BaseModel):
    contact: ContactInfo = ContactInfo()
    summary: str = ""
    experience: list[ExperienceItem] = []
    projects: list[ProjectItem] = []
    education: list[EducationItem] = []
    certifications: list[CertificationItem] = []
    skills: list[str] = []
    ats_improvements: list[str] = Field(default=[], alias="ats_improvements")


class ApprovedExperienceItem(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    start_date: str = Field(default="", alias="start_date")
    end_date: str = Field(default="", alias="end_date")
    duration: str = ""
    bullets: list[str] = []


class ApprovedProjectItem(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = []
    bullets: list[str] = []


class ApprovedResume(BaseModel):
    contact: ContactInfo = ContactInfo()
    summary: str = ""
    experience: list[ApprovedExperienceItem] = []
    projects: list[ApprovedProjectItem] = []
    education: list[EducationItem] = []
    certifications: list[CertificationItem] = []
    skills: list[str] = []

from fastapi import APIRouter, HTTPException

from app import jobs_db
from app.jobs_schemas import AppliedRequest, JobDetail, JobSummary, SelectRequest

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobSummary])
async def list_jobs_endpoint(
    status: str | None = None,
    min_fit_score: int | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[JobSummary]:
    rows = jobs_db.list_jobs(status=status, min_fit_score=min_fit_score, source=source, limit=limit, offset=offset)
    return [JobSummary(**row) for row in rows]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job_endpoint(job_id: str) -> JobDetail:
    job = jobs_db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDetail(**job)


@router.post("/{job_id}/select")
async def select_job_endpoint(job_id: str, payload: SelectRequest) -> dict[str, str]:
    if jobs_db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    jobs_db.mark_selected(job_id, payload.status)
    return {"status": "ok"}


@router.post("/{job_id}/applied")
async def mark_applied_endpoint(job_id: str, payload: AppliedRequest) -> dict[str, str]:
    if jobs_db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    jobs_db.mark_applied(job_id, payload.status, payload.notes)
    return {"status": "ok"}

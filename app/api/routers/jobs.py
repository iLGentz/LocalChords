from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import QueueDep
from app.api.errors import ApiError, not_found
from app.api.schemas import JobOut
from app.db.models import JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    queue: QueueDep,
    status: Annotated[list[JobStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[JobOut]:
    return [JobOut.from_job(j) for j in queue.list_jobs(set(status) if status else None, limit)]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, queue: QueueDep) -> JobOut:
    job = queue.get(job_id)
    if job is None:
        raise not_found("job", job_id)
    return JobOut.from_job(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, queue: QueueDep) -> JobOut:
    job = queue.get(job_id)
    if job is None:
        raise not_found("job", job_id)
    if job.status in (JobStatus.READY, JobStatus.FAILED):
        raise ApiError(
            409,
            "job_finished",
            "Il job è già terminato e non può essere annullato",
            {"status": job.status.value},
        )
    updated = queue.request_cancel(job_id)
    assert updated is not None
    return JobOut.from_job(updated)

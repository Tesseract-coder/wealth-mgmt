import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from app.core.db import get_session
from app.jobs.runner import ACTIVE, get_runner
from app.models.schemas import JobOut
from app.models.tables import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def job_out(job: Job) -> JobOut:
    assert job.id is not None
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        trigger=job.trigger,
        params=json.loads(job.params) if job.params else {},
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        done=job.done,
        total=job.total,
        message=job.message,
        errors=json.loads(job.errors) if job.errors else [],
    )


@router.get("", response_model=list[JobOut])
def list_jobs(
    limit: int = Query(20, ge=1, le=200), session: Session = Depends(get_session)
) -> list[JobOut]:
    jobs = session.exec(select(Job).order_by(col(Job.id).desc()).limit(limit)).all()
    return [job_out(j) for j in jobs]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    return job_out(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    """Stop a running job after the item it is working on. Finished work is kept."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    if job.status not in ACTIVE:
        raise HTTPException(409, f"Job {job_id} has already finished ({job.status})")
    if not get_runner().cancel(job_id):
        raise HTTPException(409, "This job isn't running in this backend process")
    return job_out(job)

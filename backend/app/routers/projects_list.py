from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import Project, MatchResult, MatchRun
from ..schemas import ProjectResponse

router = APIRouter()


@router.get("/projects/list", response_model=list[ProjectResponse])
def list_projects(session: Session = Depends(get_session)) -> list[ProjectResponse]:
    ps = session.exec(select(Project).order_by(Project.created_at.desc())).all()
    print(f"DEBUG: list_projects - Found {len(ps)} projects")
    print(f"DEBUG: Project names: {[p.name for p in ps]}")
    result = [ProjectResponse(id=p.id, name=p.name, status=p.status, active_database_id=p.active_database_id, active_import_id=p.active_import_id) for p in ps]
    print(f"DEBUG: Returning {len(result)} projects")
    return result


@router.get("/projects/{project_id}/stats")
def get_project_stats(project_id: int, session: Session = Depends(get_session)) -> dict:
    """Get matching statistics for a project."""
    
    # Get the latest match run for this project
    latest_run = session.exec(
        select(MatchRun)
        .where(MatchRun.project_id == project_id)
        .order_by(MatchRun.started_at.desc())
    ).first()
    
    if not latest_run:
        return {
            "total_products": 0,
            "status_breakdown": {
                "pending": 0,
                "auto_approved": 0,
                "approved": 0,
                "not_approved": 0,
                "sent_to_ai": 0,
                "ai_auto_approved": 0
            }
        }
    
    # Get all match results for the latest run
    results = session.exec(
        select(MatchResult)
        .where(MatchResult.match_run_id == latest_run.id)
    ).all()
    
    # Count by status
    status_counts = {}
    for result in results:
        status = result.decision
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Ensure all statuses are present
    all_statuses = ["pending", "auto_approved", "approved", "not_approved", "auto_not_approved", "sent_to_ai", "ai_auto_approved"]
    status_breakdown = {status: status_counts.get(status, 0) for status in all_statuses}
    
    return {
        "total_products": len(results),
        "status_breakdown": status_breakdown
    }

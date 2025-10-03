from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import Project, MatchResult, MatchRun, RejectedProductData
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
                "ai_auto_approved": 0,
                "worklist": 0
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
    
    # Map rejected statuses to not_approved for frontend compatibility
    not_approved_count = status_counts.get("rejected", 0) + status_counts.get("auto_rejected", 0)
    
    # Get worklist count from RejectedProductData
    worklist_count = session.exec(
        select(RejectedProductData)
        .where(RejectedProductData.project_id == project_id)
        .where(RejectedProductData.status == "request_worklist")
    ).count()
    
    # Ensure all statuses are present with mapping
    status_breakdown = {
        "pending": status_counts.get("pending", 0),
        "auto_approved": status_counts.get("auto_approved", 0),
        "approved": status_counts.get("approved", 0),
        "not_approved": not_approved_count,  # Maps rejected + auto_rejected
        "sent_to_ai": status_counts.get("sent_to_ai", 0),
        "ai_auto_approved": status_counts.get("ai_auto_approved", 0),
        "worklist": worklist_count
    }
    
    return {
        "total_products": len(results),
        "status_breakdown": status_breakdown
    }

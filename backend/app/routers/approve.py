from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import MatchResult, MatchRun, AiSuggestion
from ..schemas import ApproveRequest, ApproveAIRequest

router = APIRouter()


@router.post("/projects/{project_id}/approve")
def approve_results(project_id: int, req: ApproveRequest, session: Session = Depends(get_session)):
    if not req.ids and not req.customer_row_indices:
        raise HTTPException(status_code=400, detail="Inga resultat angivna.")
    q = select(MatchResult).where(MatchResult.decision != "approved")
    results = session.exec(q).all()
    count = 0
    for r in results:
        if r.id in set(req.ids) or r.customer_row_index in set(req.customer_row_indices):
            r.decision = "approved"
            session.add(r)
            count += 1
    session.commit()
    return {"updated": count}


@router.post("/projects/{project_id}/approve-ai")
def approve_ai_suggestion(project_id: int, req: ApproveAIRequest, session: Session = Depends(get_session)):
    """Approve a specific AI suggestion and update the match result"""
    # Get the AI suggestion
    ai_suggestion = session.get(AiSuggestion, req.ai_suggestion_id)
    if not ai_suggestion:
        raise HTTPException(status_code=404, detail="AI suggestion not found.")
    
    # Get the latest match run for this project
    latest_run = session.exec(
        select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
    ).first()
    
    if not latest_run:
        raise HTTPException(status_code=404, detail="No match run found.")
    
    # Find the match result for this customer row
    match_result = session.exec(
        select(MatchResult).where(
            MatchResult.customer_row_index == req.customer_row_index,
            MatchResult.match_run_id == latest_run.id
        )
    ).first()
    
    if not match_result:
        raise HTTPException(status_code=404, detail="Match result not found.")
    
    # Update the match result with the approved AI suggestion
    match_result.decision = "approved"
    match_result.approved_ai_suggestion_id = req.ai_suggestion_id
    match_result.db_fields_json = ai_suggestion.database_fields_json
    match_result.ai_status = "approved"
    match_result.ai_summary = f"AI approved: {ai_suggestion.rationale}"
    
    session.add(match_result)
    session.commit()
    
    return {"updated": 1, "ai_confidence": ai_suggestion.confidence}


@router.post("/projects/{project_id}/reject")
def reject_results(project_id: int, req: ApproveRequest, session: Session = Depends(get_session)):
    """Mark results as not approved"""
    if not req.ids and not req.customer_row_indices:
        raise HTTPException(status_code=400, detail="Inga resultat angivna.")
    q = select(MatchResult).where(MatchResult.decision.in_(["pending", "auto_approved", "approved", "sent_to_ai", "ai_auto_approved"]))
    results = session.exec(q).all()
    count = 0
    for r in results:
        if r.id in set(req.ids) or r.customer_row_index in set(req.customer_row_indices):
            # Store original decision before changing it
            old_decision = r.decision
            r.decision = "rejected"
            # If this was an AI-related decision, set ai_status too
            if old_decision in ["sent_to_ai", "ai_auto_approved"] or r.ai_status is not None:
                r.ai_status = "rejected"
            session.add(r)
            count += 1
    session.commit()
    return {"updated": count}


@router.post("/projects/{project_id}/send-to-ai")
def send_to_ai(project_id: int, req: ApproveRequest, session: Session = Depends(get_session)):
    """Mark results as sent to AI"""
    if not req.ids and not req.customer_row_indices:
        raise HTTPException(status_code=400, detail="Inga resultat angivna.")
    q = select(MatchResult).where(MatchResult.decision.in_(["pending", "auto_approved", "approved", "rejected", "ai_auto_approved"]))
    results = session.exec(q).all()
    count = 0
    for r in results:
        if r.id in set(req.ids) or r.customer_row_index in set(req.customer_row_indices):
            r.decision = "sent_to_ai"
            r.ai_status = "queued"  # Add to AI queue
            session.add(r)
            count += 1
    session.commit()
    
    # Start AI processing for manually sent products
    if count > 0:
        from .ai import auto_queue_ai_analysis
        try:
            auto_queue_ai_analysis(project_id, session)
        except Exception as e:
            # Log error but don't fail the request
            import logging
            logging.getLogger("app.ai").error(f"Failed to start AI queue for manual products: {e}")
    
    return {"updated": count}

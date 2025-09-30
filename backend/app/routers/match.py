from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import DatabaseCatalog, ImportFile, MatchResult, MatchRun, Project, AiSuggestion
from ..schemas import MatchRequest, MatchRunResponse, MatchResultItem
from ..match_engine import run_match, Thresholds

router = APIRouter()
log = logging.getLogger("app.match")


@router.post("/projects/{project_id}/match", response_model=MatchRunResponse)
def run_matching(project_id: int, req: MatchRequest, session: Session = Depends(get_session)) -> MatchRunResponse:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    if not p.active_database_id:
        raise HTTPException(status_code=400, detail="Ingen aktiv databas vald.")
    if not p.active_import_id:
        raise HTTPException(status_code=400, detail="Ingen aktiv importfil vald.")
    db = session.get(DatabaseCatalog, p.active_database_id)
    imp = session.get(ImportFile, p.active_import_id)
    if not imp:
        raise HTTPException(status_code=400, detail="Aktiv importfil saknas.")

    thr_json = (req.thresholds.model_dump() if req and req.thresholds else settings.DEFAULT_THRESHOLDS)
    thr = Thresholds(
        vendor_min=thr_json.get("vendor_min", 80),
        product_min=thr_json.get("product_min", 75),
        overall_accept=thr_json.get("overall_accept", 85),
        weight_vendor=thr_json.get("weights", {}).get("vendor", 0.6),
        weight_product=thr_json.get("weights", {}).get("product", 0.4),
        sku_exact_boost=thr_json.get("sku_exact_boost", 10),
        numeric_mismatch_penalty=thr_json.get("numeric_mismatch_penalty", 8),
    )
    run = MatchRun(project_id=project_id, thresholds_json=thr_json, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)

    db_csv = Path(settings.DATABASES_DIR) / db.filename  # type: ignore
    cust_csv = Path(settings.IMPORTS_DIR) / imp.filename

    created = 0
    try:
        for row_index, crow, dbrow, meta in run_match(cust_csv, db_csv, imp.columns_map_json, thr):
            mr = MatchResult(
                match_run_id=run.id,
                customer_row_index=row_index,
                decision=meta["decision"],
                overall_score=meta["overall"],
                reason=meta["reason"],
                exact_match=meta["exact"],
                customer_fields_json=crow,
                db_fields_json=dbrow,
            )
            session.add(mr)
            created += 1
            if created % 1000 == 0:
                session.commit()
        run.status = "finished"
        run.finished_at = datetime.utcnow()
        session.add(run)
        session.commit()
    except Exception as e:
        log.exception(f"Match run failed: {str(e)}")
        run.status = "failed"
        session.add(run)
        session.commit()
        raise HTTPException(status_code=500, detail=f"Matchning misslyckades: {str(e)}")

    return MatchRunResponse(match_run_id=run.id, status=run.status)


@router.get("/projects/{project_id}/match/status")
def get_match_status(project_id: int, session: Session = Depends(get_session)) -> dict:
    """Get current match status and progress."""
    run = session.exec(select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())).first()
    if not run:
        return {"status": "not_started", "progress": 0, "message": "Ingen matchning påbörjad"}
    
    if run.status == "running":
        # Simulate progress based on time elapsed
        import time
        elapsed = time.time() - run.started_at.timestamp() if run.started_at else 0
        progress = min(int(elapsed * 10), 90)  # 10% per second, max 90%
        return {"status": "running", "progress": progress, "message": "Matchar produkter..."}
    elif run.status == "finished":
        return {"status": "finished", "progress": 100, "message": "Matchning klar!"}
    elif run.status == "failed":
        return {"status": "failed", "progress": 0, "message": "Matchning misslyckades"}
    else:
        return {"status": run.status, "progress": 0, "message": f"Status: {run.status}"}


@router.get("/projects/{project_id}/results", response_model=list[MatchResultItem])
def list_results(project_id: int, session: Session = Depends(get_session)) -> list[MatchResultItem]:
    run = session.exec(select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())).first()
    if not run:
        return []
    results = session.exec(select(MatchResult).where(MatchResult.match_run_id == run.id)).all()
    items: list[MatchResultItem] = []
    for r in results:
        # Get AI confidence for this customer row
        # First check if there's an approved AI suggestion, otherwise use rank 1
        ai_suggestion = None
        if r.approved_ai_suggestion_id:
            ai_suggestion = session.get(AiSuggestion, r.approved_ai_suggestion_id)
        else:
            # Fallback to rank 1 (recommended match)
            ai_suggestion = session.exec(
                select(AiSuggestion).where(
                    AiSuggestion.customer_row_index == r.customer_row_index,
                    AiSuggestion.rank == 1
                ).order_by(AiSuggestion.created_at.desc())
            ).first()
        
        # Handle different field name formats from PDF imports vs CSV imports
        cust_preview = {
            "Product": (r.customer_fields_json.get("Product_name") or 
                       r.customer_fields_json.get("product") or 
                       r.customer_fields_json.get("product_name") or ""),
            "Supplier": (r.customer_fields_json.get("Supplier_name") or 
                        r.customer_fields_json.get("vendor") or 
                        r.customer_fields_json.get("company_name") or ""),
            "Art.no": (r.customer_fields_json.get("Article_number") or 
                      r.customer_fields_json.get("sku") or 
                      r.customer_fields_json.get("article_number") or ""),
            "Market": (r.customer_fields_json.get("Market") or 
                      r.customer_fields_json.get("market") or 
                      r.customer_fields_json.get("authored_market") or ""),
            "Legislation": (r.customer_fields_json.get("Legislation") or 
                           r.customer_fields_json.get("legislation") or ""),
            "Language": (r.customer_fields_json.get("Language") or 
                        r.customer_fields_json.get("language") or ""),
        }
        db_preview = None
        if r.db_fields_json:
            db_preview = {
                "Product": r.db_fields_json.get("Product_name") or "",
                "Supplier": r.db_fields_json.get("Supplier_name") or "",
                "Art.no": r.db_fields_json.get("Article_number") or "",
                "Market": r.db_fields_json.get("Market") or "",
                "Language": r.db_fields_json.get("Language") or "",
            }
        items.append(MatchResultItem(
            id=r.id,
            customer_row_index=r.customer_row_index,
            decision=r.decision,
            overall_score=r.overall_score,
            reason=r.reason,
            exact_match=r.exact_match,
            customer_preview=cust_preview,
            db_preview=db_preview,
            ai_confidence=ai_suggestion.confidence if ai_suggestion else None,
        ))
    return items

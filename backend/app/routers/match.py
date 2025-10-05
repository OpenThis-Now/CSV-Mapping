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
from .ai import auto_queue_ai_analysis

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
    # If match_new_only is True, try to use existing run, otherwise create new
    if req and req.match_new_only:
        # Try to find the latest match run for this project
        existing_run = session.exec(
            select(MatchRun)
            .where(MatchRun.project_id == project_id)
            .order_by(MatchRun.started_at.desc())
        ).first()
        
        if existing_run and existing_run.status == "finished":
            # Use existing run
            run = existing_run
            run.status = "running"
            run.finished_at = None  # Clear finished_at since we're running again
            session.add(run)
            session.commit()
            log.info(f"Reusing existing match run {run.id} for new products")
        else:
            # Create new run if no existing run found
            run = MatchRun(project_id=project_id, thresholds_json=thr_json, status="running")
            session.add(run)
            session.commit()
            session.refresh(run)
            log.info(f"Created new match run {run.id}")
    else:
        # Always create new run for full matching
        run = MatchRun(project_id=project_id, thresholds_json=thr_json, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        log.info(f"Created new match run {run.id} for full matching")

    db_csv = Path(settings.DATABASES_DIR) / db.filename  # type: ignore
    cust_csv = Path(settings.IMPORTS_DIR) / imp.filename

    created = 0
    try:
        log.info(f"Starting match run for project {project_id}, import {imp.id}, database {db.id}")
        log.info(f"Customer CSV: {cust_csv}, exists: {cust_csv.exists()}")
        log.info(f"Database CSV: {db_csv}, exists: {db_csv.exists()}")
        log.info(f"Mapping: {imp.columns_map_json}")
        log.info(f"Match new only: {req.match_new_only if req else False}")
        
        # Debug: Check if mapping has the required fields
        required_fields = ["vendor", "product", "sku", "market", "language"]
        for field in required_fields:
            if field not in imp.columns_map_json:
                log.warning(f"Missing mapping for field '{field}' in import {imp.id}")
            else:
                log.info(f"Customer field '{field}' mapped to column '{imp.columns_map_json[field]}'")
        
        for field in required_fields:
            if field not in db.columns_map_json:
                log.warning(f"Missing mapping for field '{field}' in database {db.id}")
            else:
                log.info(f"Database field '{field}' mapped to column '{db.columns_map_json[field]}'")
        
        # If match_new_only is True, get existing customer_row_indexes to skip them
        existing_row_indexes = set()
        if req and req.match_new_only:
            # Get existing results from the current match run
            existing_results = session.exec(
                select(MatchResult.customer_row_index)
                .where(MatchResult.match_run_id == run.id)
            ).all()
            existing_row_indexes = set(existing_results)
            log.info(f"Found {len(existing_row_indexes)} existing matches in current run, will skip these rows")
        
        for row_index, crow, dbrow, meta in run_match(cust_csv, db_csv, imp.columns_map_json, db.columns_map_json, thr):
            # Skip existing rows if match_new_only is True
            if req and req.match_new_only and row_index in existing_row_indexes:
                log.debug(f"Skipping existing row {row_index}")
                continue
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
                log.info(f"Processed {created} rows")
        
        log.info(f"Match run completed, created {created} results")
        run.status = "finished"
        run.finished_at = datetime.utcnow()
        session.add(run)
        session.commit()
        
        # Automatically queue products with scores 70-95 for AI analysis
        try:
            log.info(f"Starting automatic AI queue for project {project_id}")
            auto_queue_ai_analysis(project_id, session)
        except Exception as e:
            log.error(f"Failed to start automatic AI queue: {e}")
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
    results = session.exec(select(MatchResult).where(MatchResult.match_run_id == run.id).order_by(MatchResult.customer_row_index, MatchResult.id)).all()
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
        
        # Get mappings from the latest run's import and database
        customer_mapping = {}
        db_mapping = {}
        if run:
            # Get import file mapping
            import_file = session.exec(
                select(ImportFile).where(ImportFile.project_id == project_id).order_by(ImportFile.created_at.desc())
            ).first()
            if import_file:
                customer_mapping = import_file.columns_map_json or {}
            
            # Get database mapping
            project = session.get(Project, project_id)
            if project and project.active_database_id:
                database = session.get(DatabaseCatalog, project.active_database_id)
                if database:
                    db_mapping = database.columns_map_json or {}
        
        # Use mappings to get the correct field names, with fallbacks for compatibility
        cust_preview = {
            "Product": (r.customer_fields_json.get(customer_mapping.get("product", "product")) or 
                       r.customer_fields_json.get("Product_name") or 
                       r.customer_fields_json.get("product") or 
                       r.customer_fields_json.get("product_name") or ""),
            "Supplier": (r.customer_fields_json.get(customer_mapping.get("vendor", "vendor")) or 
                        r.customer_fields_json.get("Supplier_name") or 
                        r.customer_fields_json.get("vendor") or 
                        r.customer_fields_json.get("company_name") or ""),
            "Art.no": (r.customer_fields_json.get(customer_mapping.get("sku", "sku")) or 
                      r.customer_fields_json.get("Article_number") or 
                      r.customer_fields_json.get("sku") or 
                      r.customer_fields_json.get("article_number") or ""),
            "Market": (r.customer_fields_json.get(customer_mapping.get("market", "market")) or 
                      r.customer_fields_json.get("Market") or 
                      r.customer_fields_json.get("market") or 
                      r.customer_fields_json.get("authored_market") or ""),
            "Legislation": (r.customer_fields_json.get("Legislation") or 
                           r.customer_fields_json.get("legislation") or ""),
            "Language": (r.customer_fields_json.get(customer_mapping.get("language", "language")) or 
                        r.customer_fields_json.get("Language") or 
                        r.customer_fields_json.get("language") or ""),
        }
        db_preview = None
        if r.db_fields_json:
            db_preview = {
                "Product": (r.db_fields_json.get(db_mapping.get("product", "Product_name")) or 
                          r.db_fields_json.get("Product_name") or ""),
                "Supplier": (r.db_fields_json.get(db_mapping.get("vendor", "Supplier_name")) or 
                            r.db_fields_json.get("Supplier_name") or ""),
                "Art.no": (r.db_fields_json.get(db_mapping.get("sku", "Article_number")) or 
                          r.db_fields_json.get("Article_number") or ""),
                "Market": (r.db_fields_json.get(db_mapping.get("market", "Market")) or 
                          r.db_fields_json.get("Market") or ""),
                "Language": (r.db_fields_json.get(db_mapping.get("language", "Language")) or 
                            r.db_fields_json.get("Language") or ""),
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

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

    # Check if customer CSV file exists
    if not cust_csv.exists():
        raise HTTPException(status_code=404, detail=f"Customer CSV file not found: {cust_csv}")
    
    if not db_csv.exists():
        raise HTTPException(status_code=404, detail=f"Database CSV file not found: {db_csv}")

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
        
        # If match_new_only is True, get existing product combinations to skip them
        existing_products = set()
        if req and req.match_new_only:
            # Get existing results from the current match run and create a set of product combinations
            existing_results = session.exec(
                select(MatchResult.customer_fields_json)
                .where(MatchResult.match_run_id == run.id)
            ).all()
            
            for result in existing_results:
                # Create a unique key based on product data (not row index)
                if result and isinstance(result, dict):
                    product_key = f"{result.get('product', '')}_{result.get('vendor', '')}_{result.get('sku', '')}"
                    existing_products.add(product_key)
            
            log.info(f"Found {len(existing_products)} existing product combinations, will skip these")
        
        # Add file_hash to customer data before running match
        import pandas as pd
        from ..services.files import detect_csv_separator
        
        # Read customer CSV and add file_hash
        customer_separator = detect_csv_separator(cust_csv)
        log.info(f"Customer CSV separator detected: '{customer_separator}'")
        
        # Try to read with detected separator first
        try:
            customer_df = pd.read_csv(cust_csv, dtype=str, keep_default_na=False, sep=customer_separator, encoding='utf-8')
            log.info(f"Customer CSV read successfully with separator '{customer_separator}': {customer_df.shape}")
        except Exception as e:
            log.warning(f"Failed to read customer CSV with separator '{customer_separator}': {e}")
            # Try with open_text_stream approach like in imports.py
            from ..services.files import open_text_stream
            import csv
            with open_text_stream(cust_csv) as f:
                reader = csv.DictReader(f, delimiter=customer_separator)
                headers = reader.fieldnames or []
                rows = list(reader)
                customer_df = pd.DataFrame(rows)
                log.info(f"Customer CSV read with open_text_stream: {customer_df.shape}")
        
        # For URL enhanced files, try to get PDF hashes from ImportedPdf records
        if "enhanced" in imp.filename.lower():
            log.info("URL enhanced file detected - looking up PDF hashes from ImportedPdf records")
            
            # Look up ImportedPdf records for this project
            from ..models import ImportedPdf
            imported_pdfs = session.exec(
                select(ImportedPdf)
                .where(ImportedPdf.project_id == project_id)
                .where(ImportedPdf.customer_row_index.is_(None))  # Not yet processed
            ).all()
            
            if imported_pdfs:
                log.info(f"Found {len(imported_pdfs)} ImportedPdf records with PDF hashes")
                # Create a mapping from product info to PDF hash
                pdf_hash_map = {}
                for pdf_record in imported_pdfs:
                    # Create key from product info
                    if pdf_record.product_name and pdf_record.supplier_name and pdf_record.article_number:
                        key = f"{pdf_record.product_name}|{pdf_record.supplier_name}|{pdf_record.article_number}"
                        pdf_hash_map[key] = pdf_record.file_hash
                        log.info(f"Mapped {key} -> {pdf_record.file_hash[:16]}...")
                
                # Apply PDF hashes to customer data
                customer_df['file_hash'] = imp.file_hash  # Default fallback
                for idx, row in customer_df.iterrows():
                    product_key = f"{row.get('Product_name', '')}|{row.get('Supplier_name', '')}|{row.get('Article_number', '')}"
                    if product_key in pdf_hash_map:
                        customer_df.at[idx, 'file_hash'] = pdf_hash_map[product_key]
                        log.info(f"Applied PDF hash to row {idx}: {pdf_hash_map[product_key][:16]}...")
                
                log.info(f"Applied PDF hashes to {len(customer_df[customer_df['file_hash'] != imp.file_hash])} rows")
            else:
                log.info("No ImportedPdf records found - using enhanced file hash")
                customer_df['file_hash'] = imp.file_hash
        else:
            # For regular files, use the same file hash for all rows
            customer_df['file_hash'] = imp.file_hash
        
        # Read database CSV and add file_hash
        db_separator = detect_csv_separator(db_csv)
        log.info(f"Detected separators - Customer: '{customer_separator}', Database: '{db_separator}'")
        db_df = pd.read_csv(db_csv, dtype=str, keep_default_na=False, sep=db_separator, encoding='utf-8')
        log.info(f"Original database CSV columns after reading: {list(db_df.columns)}")
        log.info(f"Original database CSV shape: {db_df.shape}")
        
        # Use existing File_hash column if it exists, otherwise use db.file_hash
        if 'File_hash' in db_df.columns:
            log.info("Using existing File_hash column from database CSV")
            db_df['file_hash'] = db_df['File_hash']
        else:
            log.info("No File_hash column found, using database file hash for all rows")
            db_df['file_hash'] = db.file_hash
        
        # Debug: Log file hash information
        log.info(f"Customer file hash: {imp.file_hash[:16] if imp.file_hash else 'None'}...")
        log.info(f"Database file hash: {db.file_hash[:16] if db.file_hash else 'None'}...")
        log.info(f"Customer CSV columns: {list(customer_df.columns)}")
        log.info(f"Database CSV columns: {list(db_df.columns)}")
        log.info(f"Customer CSV shape: {customer_df.shape}")
        log.info(f"Database CSV shape: {db_df.shape}")
        
        # Save modified CSVs temporarily
        temp_cust_csv = cust_csv.parent / f"temp_{cust_csv.name}"
        temp_db_csv = db_csv.parent / f"temp_{db_csv.name}"
        customer_df.to_csv(temp_cust_csv, index=False, encoding='utf-8')
        db_df.to_csv(temp_db_csv, index=False, encoding='utf-8')
        
        # Debug: Verify temp files have file_hash column
        temp_cust_df = pd.read_csv(temp_cust_csv, dtype=str, keep_default_na=False, sep=customer_separator, encoding='utf-8')
        temp_db_df = pd.read_csv(temp_db_csv, dtype=str, keep_default_na=False, sep=db_separator, encoding='utf-8')
        log.info(f"Temp customer CSV columns: {list(temp_cust_df.columns)}")
        log.info(f"Temp database CSV columns: {list(temp_db_df.columns)}")
        log.info(f"Temp customer file_hash sample: {temp_cust_df['file_hash'].iloc[0][:16] if len(temp_cust_df) > 0 and 'file_hash' in temp_cust_df.columns else 'Empty'}")
        log.info(f"Temp database file_hash sample: {temp_db_df['file_hash'].iloc[0][:16] if len(temp_db_df) > 0 and 'file_hash' in temp_db_df.columns else 'Empty'}")
        
        # Check if file_hash column exists in temp files
        if 'file_hash' not in temp_cust_df.columns:
            log.error(f"file_hash column missing from temp customer CSV! Columns: {list(temp_cust_df.columns)}")
        if 'file_hash' not in temp_db_df.columns:
            log.error(f"file_hash column missing from temp database CSV! Columns: {list(temp_db_df.columns)}")
            # Try to fix by re-reading with different separators
            log.info("Attempting to fix database CSV separator issue...")
            
            # Try different separators in order of preference
            separators_to_try = [';', ',', '\t', '|']
            fixed = False
            
            for sep in separators_to_try:
                try:
                    log.info(f"Trying separator: '{sep}'")
                    temp_db_df = pd.read_csv(temp_db_csv, dtype=str, keep_default_na=False, sep=sep, encoding='utf-8')
                    if len(temp_db_df.columns) > 1 and 'file_hash' in temp_db_df.columns:
                        log.info(f"Successfully fixed with separator '{sep}': {list(temp_db_df.columns)}")
                        # Add file_hash back since it might have been lost
                        if 'File_hash' in temp_db_df.columns:
                            temp_db_df['file_hash'] = temp_db_df['File_hash']
                        else:
                            temp_db_df['file_hash'] = db.file_hash
                        # Save the fixed version
                        temp_db_df.to_csv(temp_db_csv, index=False, encoding='utf-8')
                        fixed = True
                        break
                    else:
                        log.info(f"Separator '{sep}' didn't work - columns: {list(temp_db_df.columns)}")
                except Exception as e:
                    log.info(f"Separator '{sep}' failed: {e}")
                    continue
            
            if not fixed:
                log.error("Failed to fix database CSV with any separator!")
                # Create a minimal fallback with just the file_hash
                log.info("Creating fallback database CSV with file_hash only...")
                fallback_df = pd.DataFrame({'file_hash': [db.file_hash]})
                fallback_df.to_csv(temp_db_csv, index=False, encoding='utf-8')
        
        try:
            for row_index, crow, dbrow, meta in run_match(temp_cust_csv, temp_db_csv, imp.columns_map_json, db.columns_map_json, thr):
                # Skip existing products if match_new_only is True
                if req and req.match_new_only:
                    # Create product key from current row data
                    product_key = f"{crow.get('product', '')}_{crow.get('vendor', '')}_{crow.get('sku', '')}"
                    if product_key in existing_products:
                        log.debug(f"Skipping existing product: {product_key}")
                        continue
                
                # file_hash is already in crow and dbrow from the temporary CSVs
                customer_fields_with_hash = crow.copy()
                db_fields_with_hash = dbrow.copy() if dbrow else {}
                
                mr = MatchResult(
                    match_run_id=run.id,
                    customer_row_index=row_index,
                    decision=meta["decision"],
                    overall_score=meta["overall"],
                    reason=meta["reason"],
                    exact_match=meta["exact"],
                    customer_fields_json=customer_fields_with_hash,
                    db_fields_json=db_fields_with_hash,
                )
                session.add(mr)
                created += 1
                if created % 1000 == 0:
                    session.commit()
                    log.info(f"Processed {created} rows")
        finally:
            # Clean up temporary files
            try:
                temp_cust_csv.unlink()
            except:
                pass
            try:
                temp_db_csv.unlink()
            except:
                pass
        
        log.info(f"Match run completed, created {created} results")
        
        # Debug: Show some results and their decisions
        sample_results = session.exec(
            select(MatchResult).where(MatchResult.match_run_id == run.id).limit(5)
        ).all()
        for result in sample_results:
            log.info(f"Result {result.customer_row_index}: score={result.overall_score}, decision={result.decision}, reason={result.reason}")
            # Debug: Show file hash information
            customer_hash = result.customer_fields_json.get("file_hash", "")
            db_hash = result.db_fields_json.get("file_hash", "") if result.db_fields_json else ""
            log.info(f"  Customer hash: {customer_hash[:16] if customer_hash else 'None'}...")
            log.info(f"  Database hash: {db_hash[:16] if db_hash else 'None'}...")
            log.info(f"  Hash match: {customer_hash == db_hash and customer_hash != ''}")
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

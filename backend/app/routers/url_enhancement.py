from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any
import requests
import tempfile
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import ImportFile, Project, URLEnhancementRun
from ..schemas import ImportUploadResponse
from ..services.files import detect_csv_separator, open_text_stream
from ..services.pdf_processor import extract_pdf_data_with_ai, separate_market_and_legislation, adjust_market_by_language
from ..services.parallel_url_processor import process_urls_optimized

router = APIRouter()
log = logging.getLogger("app.url_enhancement")


def _process_urls_in_background_optimized(project_id: int, import_id: int, enhancement_run_id: int):
    """Optimized background task to process URLs in parallel."""
    from ..db import get_session
    
    session = next(get_session())
    try:
        enhancement_run = session.get(URLEnhancementRun, enhancement_run_id)
        imp = session.get(ImportFile, import_id)
        
        if not enhancement_run or not imp:
            return
        
        csv_path = Path(settings.IMPORTS_DIR) / imp.filename
        separator = detect_csv_separator(csv_path)
        
        with open_text_stream(csv_path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            headers = reader.fieldnames or []
            rows = list(reader)
        
        # Get column mappings
        url_column = imp.columns_map_json["url"]
        product_column = imp.columns_map_json.get("product", "product")
        vendor_column = imp.columns_map_json.get("vendor", "vendor")
        sku_column = imp.columns_map_json.get("sku", "sku")
        market_column = imp.columns_map_json.get("market", "market")
        language_column = imp.columns_map_json.get("language", "language")
        
        # Extract URLs for parallel processing
        urls_to_process = []
        url_row_indices = []
        
        for row_idx, row in enumerate(rows):
            url = row.get(url_column, "").strip()
            if url and url.startswith(("http://", "https://")):
                urls_to_process.append(url)
                url_row_indices.append(row_idx)
        
        log.info(f"Found {len(urls_to_process)} URLs to process in parallel")
        
        # Process URLs in parallel with progress tracking
        start_time = datetime.now()
        
        # Initialize counters
        enhancement_run.processed_urls = 0
        enhancement_run.successful_urls = 0
        enhancement_run.failed_urls = 0
        session.add(enhancement_run)
        session.commit()
        
        # Process URLs in batches to update progress
        batch_size = 5  # Process 5 URLs at a time
        pdf_data_results = []
        
        for i in range(0, len(urls_to_process), batch_size):
            # Check if process was cancelled
            session.refresh(enhancement_run)
            if enhancement_run.status != "running":
                log.info(f"URL enhancement cancelled, stopping at batch {i//batch_size + 1}")
                break
                
            batch_urls = urls_to_process[i:i + batch_size]
            log.info(f"Processing batch {i//batch_size + 1}: {len(batch_urls)} URLs")
            
            # Process this batch
            batch_results = process_urls_optimized(batch_urls)
            pdf_data_results.extend(batch_results)
            
            # Update progress
            enhancement_run.processed_urls = len(pdf_data_results)
            enhancement_run.successful_urls = sum(1 for result in pdf_data_results if result is not None)
            enhancement_run.failed_urls = len(pdf_data_results) - enhancement_run.successful_urls
            
            session.add(enhancement_run)
            session.commit()
            
            log.info(f"Progress: {enhancement_run.processed_urls}/{len(urls_to_process)} URLs processed")
        
        end_time = datetime.now()
        log.info(f"Parallel URL processing completed in {(end_time - start_time).total_seconds():.2f} seconds")
        
        # Check if process was cancelled
        session.refresh(enhancement_run)
        if enhancement_run.status != "running":
            log.info(f"URL enhancement was cancelled, not creating enhanced CSV")
            return
        
        # Process results and update rows
        enhanced_rows = []
        url_result_index = 0
        
        for row_idx, row in enumerate(rows):
            enhanced_row = row.copy()
            
            # Check if this row had a URL
            url = row.get(url_column, "").strip()
            if url and url.startswith(("http://", "https://")):
                if url_result_index < len(pdf_data_results):
                    pdf_item = pdf_data_results[url_result_index]
                    
                    if pdf_item:
                        # Update fields based on extracted data
                        if pdf_item.get("product_name", {}).get("value"):
                            enhanced_row[product_column] = pdf_item["product_name"]["value"]
                        
                        if pdf_item.get("company_name", {}).get("value"):
                            enhanced_row[vendor_column] = pdf_item["company_name"]["value"]
                        
                        if pdf_item.get("article_number", {}).get("value"):
                            enhanced_row[sku_column] = pdf_item["article_number"]["value"]
                        
                        if pdf_item.get("authored_market", {}).get("value"):
                            market_value = pdf_item["authored_market"]["value"]
                            market, legislation = separate_market_and_legislation(market_value)
                            
                            language_value = pdf_item.get("language", {}).get("value")
                            if language_value:
                                adjusted_market = adjust_market_by_language(market, language_value)
                                if adjusted_market != market:
                                    market = adjusted_market
                            
                            enhanced_row[market_column] = market
                        
                        if pdf_item.get("language", {}).get("value"):
                            enhanced_row[language_column] = pdf_item["language"]["value"]
                    
                    url_result_index += 1
            
            enhanced_rows.append(enhanced_row)
        
        # Create enhanced CSV file
        enhanced_filename = f"enhanced_{imp.filename}"
        enhanced_path = Path(settings.IMPORTS_DIR) / enhanced_filename
        
        log.info(f"Creating enhanced CSV file: {enhanced_path}")
        with open(enhanced_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(enhanced_rows)
        
        log.info(f"Enhanced CSV file created successfully")
        
        # Create new ImportFile entry
        log.info(f"Creating new ImportFile entry")
        enhanced_import = ImportFile(
            project_id=project_id,
            original_name=f"Enhanced {imp.original_name} (URL data)",
            filename=enhanced_filename,
            columns_map_json=imp.columns_map_json,
            row_count=len(enhanced_rows)
        )
        session.add(enhanced_import)
        log.info(f"ImportFile entry added to session")
        
        # Mark enhancement run as completed
        log.info(f"Marking enhancement run as completed")
        enhancement_run.status = "completed"
        enhancement_run.finished_at = datetime.utcnow()
        session.add(enhancement_run)
        
        log.info(f"Committing session changes")
        session.commit()
        
        log.info(f"URL enhancement completed: {enhancement_run.successful_urls} successful, {enhancement_run.failed_urls} failed")
        log.info(f"Enhanced CSV created: {enhanced_path}")
        log.info(f"New ImportFile created with ID: {enhanced_import.id}")
        
        # Verify the enhanced file exists
        if enhanced_path.exists():
            log.info(f"Enhanced file exists: {enhanced_path.stat().st_size} bytes")
        else:
            log.error(f"Enhanced file does not exist: {enhanced_path}")
        
    except Exception as e:
        log.error(f"Error in background URL processing: {str(e)}")
        import traceback
        log.error(f"Traceback: {traceback.format_exc()}")
        try:
            enhancement_run.status = "failed"
            enhancement_run.error_message = str(e)
            enhancement_run.finished_at = datetime.utcnow()
            session.add(enhancement_run)
            session.commit()
            log.info(f"Marked enhancement run {enhancement_run_id} as failed")
        except Exception as session_error:
            log.error(f"Failed to update enhancement run status: {session_error}")
    finally:
        try:
            session.close()
        except:
            pass


@router.post("/projects/{project_id}/enhance-with-urls")
def start_url_enhancement(project_id: int, session: Session = Depends(get_session)) -> dict:
    """Start URL enhancement process in the background."""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    if not p.active_import_id:
        raise HTTPException(status_code=400, detail="Ingen aktiv importfil vald.")
    
    imp = session.get(ImportFile, p.active_import_id)
    if not imp:
        raise HTTPException(status_code=400, detail="Aktiv importfil saknas.")
    
    if "url" not in imp.columns_map_json:
        raise HTTPException(status_code=400, detail="Ingen URL-kolumn hittades i importfilen.")
    
    csv_path = Path(settings.IMPORTS_DIR) / imp.filename
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="Importfil hittades inte.")
    
    # Check if there's already a running enhancement for this import
    existing_run = session.exec(
        select(URLEnhancementRun)
        .where(URLEnhancementRun.import_file_id == imp.id)
        .where(URLEnhancementRun.status == "running")
    ).first()
    
    if existing_run:
        raise HTTPException(status_code=400, detail="URL-förbättring pågår redan för denna importfil.")
    
    try:
        # Count URLs in the CSV
        separator = detect_csv_separator(csv_path)
        url_column = imp.columns_map_json["url"]
        total_urls = 0
        
        with open_text_stream(csv_path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            for row in reader:
                url = row.get(url_column, "").strip()
                if url and url.startswith(("http://", "https://")):
                    total_urls += 1
        
        if total_urls == 0:
            raise HTTPException(status_code=400, detail="Inga giltiga URL:er hittades i importfilen.")
        
        # Create enhancement run record
        enhancement_run = URLEnhancementRun(
            project_id=project_id,
            import_file_id=imp.id,
            total_urls=total_urls,
            status="running"
        )
        session.add(enhancement_run)
        session.commit()
        session.refresh(enhancement_run)
        
        # Start optimized background processing
        thread = threading.Thread(
            target=_process_urls_in_background_optimized,
            args=(project_id, imp.id, enhancement_run.id)
        )
        thread.daemon = True
        thread.start()
        
        return {
            "enhancement_run_id": enhancement_run.id,
            "total_urls": total_urls,
            "status": "started",
            "message": f"URL-förbättring startad för {total_urls} URL:er"
        }
        
    except Exception as e:
        log.error(f"Error starting URL enhancement: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Kunde inte starta URL-förbättring: {str(e)}")


@router.get("/projects/{project_id}/url-enhancement/status")
def get_url_enhancement_status(project_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Get status of URL enhancement for the project."""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    if not p.active_import_id:
        return {"has_active_enhancement": False}
    
    # Find the most recent enhancement run for the active import
    enhancement_run = session.exec(
        select(URLEnhancementRun)
        .where(URLEnhancementRun.project_id == project_id)
        .where(URLEnhancementRun.import_file_id == p.active_import_id)
        .order_by(URLEnhancementRun.started_at.desc())
    ).first()
    
    if not enhancement_run:
        return {"has_active_enhancement": False}
    
    if enhancement_run.status != "running":
        return {
            "has_active_enhancement": False,
            "status": enhancement_run.status,
            "message": f"Enhancement {enhancement_run.status}"
        }
    
    # Calculate stats
    queued = max(0, enhancement_run.total_urls - enhancement_run.processed_urls)
    processing = 1 if enhancement_run.processed_urls < enhancement_run.total_urls and enhancement_run.status == "running" else 0
    
    return {
        "has_active_enhancement": True,
        "enhancement_run_id": enhancement_run.id,
        "status": enhancement_run.status,
        "stats": {
            "totalUrls": enhancement_run.total_urls,
            "queued": queued,
            "processing": processing,
            "completed": enhancement_run.successful_urls,
            "errors": enhancement_run.failed_urls
        }
    }


@router.post("/projects/{project_id}/url-enhancement/cancel")
def cancel_url_enhancement(project_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Cancel a running URL enhancement process."""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    if not p.active_import_id:
        raise HTTPException(status_code=400, detail="Ingen aktiv importfil vald.")
    
    # Find the most recent running enhancement run
    enhancement_run = session.exec(
        select(URLEnhancementRun)
        .where(URLEnhancementRun.project_id == project_id)
        .where(URLEnhancementRun.import_file_id == p.active_import_id)
        .where(URLEnhancementRun.status == "running")
        .order_by(URLEnhancementRun.started_at.desc())
    ).first()
    
    if not enhancement_run:
        raise HTTPException(status_code=400, detail="Ingen pågående URL-förbättring hittades.")
    
    # Mark as cancelled
    enhancement_run.status = "cancelled"
    enhancement_run.finished_at = datetime.utcnow()
    session.add(enhancement_run)
    session.commit()
    
    return {
        "status": "cancelled",
        "message": "URL-förbättring avbruten",
        "enhancement_run_id": enhancement_run.id
    }


@router.get("/projects/{project_id}/import/has-urls")
def check_import_has_urls(project_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Check if the active import file has URL column."""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    if not p.active_import_id:
        return {"has_urls": False, "message": "Ingen aktiv importfil vald."}
    
    imp = session.get(ImportFile, p.active_import_id)
    if not imp:
        return {"has_urls": False, "message": "Aktiv importfil saknas."}
    
    has_urls = "url" in imp.columns_map_json
    url_column = imp.columns_map_json.get("url", "")
    
    return {
        "has_urls": has_urls,
        "url_column": url_column,
        "message": f"URL-kolumn hittades: {url_column}" if has_urls else "Ingen URL-kolumn hittades."
    }

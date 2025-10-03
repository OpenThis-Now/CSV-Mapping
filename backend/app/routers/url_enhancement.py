from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any
import requests
import tempfile
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import ImportFile, Project, URLEnhancementRun
from ..schemas import ImportUploadResponse
from ..services.files import detect_csv_separator, open_text_stream
from ..services.pdf_processor import extract_pdf_data_with_ai, separate_market_and_legislation, adjust_market_by_language

router = APIRouter()
log = logging.getLogger("app.url_enhancement")


def _process_urls_in_background(project_id: int, import_id: int, enhancement_run_id: int):
    """Background task to process URLs and update enhancement run status."""
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
        
        enhanced_rows = []
        
        for row_idx, row in enumerate(rows):
            enhanced_row = row.copy()
            
            # Check if this row has a URL
            url = row.get(url_column, "").strip()
            if url and url.startswith(("http://", "https://")):
                try:
                    log.info(f"Processing URL {row_idx + 1}/{enhancement_run.total_urls}: {url}")
                    
                    # Extract PDF data with timeout protection
                    pdf_data = extract_pdf_data_with_ai(url)
                    
                    if pdf_data and len(pdf_data) > 0:
                        pdf_item = pdf_data[0]
                        
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
                        
                        enhancement_run.successful_urls += 1
                        log.info(f"Successfully processed URL {row_idx + 1}: {url}")
                    else:
                        enhancement_run.failed_urls += 1
                        log.warning(f"No data extracted from URL {row_idx + 1}: {url}")
                        
                except Exception as e:
                    log.error(f"Error processing URL {url}: {str(e)}")
                    enhancement_run.failed_urls += 1
                    
                enhancement_run.processed_urls += 1
                session.add(enhancement_run)
                session.commit()
                
                # Add small delay to prevent overwhelming the server
                import time
                time.sleep(0.5)
            
            enhanced_rows.append(enhanced_row)
        
        # Create enhanced CSV file
        enhanced_filename = f"enhanced_{imp.filename}"
        enhanced_path = Path(settings.IMPORTS_DIR) / enhanced_filename
        
        with open(enhanced_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(enhanced_rows)
        
        # Create new ImportFile entry
        enhanced_import = ImportFile(
            project_id=project_id,
            original_name=f"Enhanced {imp.original_name} (URL data)",
            filename=enhanced_filename,
            columns_map_json=imp.columns_map_json,
            row_count=len(enhanced_rows)
        )
        session.add(enhanced_import)
        
        # Mark enhancement run as completed
        enhancement_run.status = "completed"
        enhancement_run.finished_at = datetime.utcnow()
        session.add(enhancement_run)
        session.commit()
        
        log.info(f"URL enhancement completed: {enhancement_run.successful_urls} successful, {enhancement_run.failed_urls} failed")
        
    except Exception as e:
        log.error(f"Error in background URL processing: {str(e)}")
        try:
            enhancement_run.status = "failed"
            enhancement_run.error_message = str(e)
            enhancement_run.finished_at = datetime.utcnow()
            session.add(enhancement_run)
            session.commit()
        except:
            pass  # If we can't update the status, just log it
    finally:
        session.close()


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
        
        # Start background processing
        thread = threading.Thread(
            target=_process_urls_in_background,
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
    processing = 1 if enhancement_run.processed_urls < enhancement_run.total_urls else 0
    
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

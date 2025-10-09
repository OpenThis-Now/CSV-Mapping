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
from ..models import ImportFile, Project, URLEnhancementRun, ImportedPdf
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
        
        # Log available API keys for debugging
        from ..services.parallel_url_processor import get_available_api_keys
        available_keys = get_available_api_keys()
        log.info(f"Available API keys for parallel processing: {available_keys}")
        
        # Process URLs in parallel with progress tracking
        start_time = datetime.now()
        
        # Initialize counters
        enhancement_run.processed_urls = 0
        enhancement_run.successful_urls = 0
        enhancement_run.failed_urls = 0
        session.add(enhancement_run)
        session.commit()
        
        # Process all URLs at once to maintain order
        log.info(f"Processing all {len(urls_to_process)} URLs in parallel")
        pdf_data_results = process_urls_optimized(urls_to_process)
        
        # Create ImportedPdf records for each successfully processed PDF
        log.info(f"Creating ImportedPdf records for processed PDFs")
        for i, (url, pdf_data) in enumerate(zip(urls_to_process, pdf_data_results)):
            if pdf_data and pdf_data.get("original_pdf_hash"):
                # Extract product info from PDF data
                product_name = None
                supplier_name = None
                article_number = None
                
                if pdf_data.get("product_name", {}).get("value"):
                    product_name = pdf_data["product_name"]["value"]
                if pdf_data.get("company_name", {}).get("value"):
                    supplier_name = pdf_data["company_name"]["value"]
                if pdf_data.get("article_number", {}).get("value"):
                    article_number = pdf_data["article_number"]["value"]
                
                # Create ImportedPdf record
                imported_pdf = ImportedPdf(
                    project_id=project_id,
                    filename=Path(url).name,
                    stored_filename=f"url_enhanced_{project_id}_{i}_{Path(url).name}",
                    file_hash=pdf_data["original_pdf_hash"],
                    product_name=product_name,
                    supplier_name=supplier_name,
                    article_number=article_number,
                    customer_row_index=None  # Will be set during matching
                )
                session.add(imported_pdf)
                log.info(f"Created ImportedPdf record for URL {i}: {pdf_data['original_pdf_hash'][:16]}...")
        
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
        
        # Add original_pdf_hash column to headers if it doesn't exist
        if "original_pdf_hash" not in headers:
            headers.append("original_pdf_hash")
        
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
                        
                        # Add original PDF hash to the enhanced row
                        original_pdf_hash = pdf_item.get("original_pdf_hash", "")
                        enhanced_row["original_pdf_hash"] = original_pdf_hash
                        if original_pdf_hash:
                            log.info(f"Added original PDF hash for row {row_idx}: {original_pdf_hash[:16]}...")
                    
                    url_result_index += 1
                else:
                    # No PDF data for this URL
                    enhanced_row["original_pdf_hash"] = ""
            else:
                # No URL for this row
                enhanced_row["original_pdf_hash"] = ""
            
            enhanced_rows.append(enhanced_row)
        
        # Create enhanced CSV file
        enhanced_filename = f"enhanced_{imp.filename}"
        enhanced_path = Path(settings.IMPORTS_DIR) / enhanced_filename
        
        log.info(f"Creating enhanced CSV file: {enhanced_path}")
        log.info(f"Enhanced rows count: {len(enhanced_rows)}")
        log.info(f"Headers: {headers}")
        
        # Write CSV file with consistent encoding and settings
        with open(enhanced_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(enhanced_rows)
        
        # Verify file was created and get file size
        if enhanced_path.exists():
            file_size = enhanced_path.stat().st_size
            log.info(f"Enhanced CSV file created successfully: {file_size} bytes")
        else:
            log.error(f"Enhanced CSV file was not created!")
            raise Exception("Failed to create enhanced CSV file")
        
        # Compute SHA-512 hash of the enhanced file
        import hashlib
        enhanced_file_hash = ""
        try:
            with open(enhanced_path, 'rb') as f:
                file_content = f.read()
                enhanced_file_hash = hashlib.sha512(file_content).hexdigest()
            log.info(f"Enhanced CSV SHA-512 hash computed successfully: {enhanced_file_hash[:16]}...")
            log.info(f"Enhanced CSV full hash: {enhanced_file_hash}")
        except Exception as hash_error:
            log.error(f"Failed to compute SHA-512 hash: {hash_error}")
            raise Exception(f"Failed to compute file hash: {hash_error}")
        
        # Create a unique hash for this enhancement run by combining:
        # 1. Original file hash
        # 2. Enhancement timestamp
        # 3. Number of URLs processed
        # 4. Enhancement run ID
        original_hash = imp.file_hash if imp.file_hash else ""
        enhancement_timestamp = enhancement_run.started_at.isoformat() if enhancement_run.started_at else ""
        urls_processed = enhancement_run.successful_urls if enhancement_run.successful_urls else 0
        run_id = enhancement_run.id if enhancement_run.id else 0
        
        # Create unique hash by combining all these elements
        unique_hash_input = f"{original_hash}|{enhancement_timestamp}|{urls_processed}|{run_id}|{enhanced_file_hash}"
        unique_enhancement_hash = hashlib.sha512(unique_hash_input.encode('utf-8')).hexdigest()
        
        log.info(f"Original file hash: {original_hash[:16] if original_hash else 'None'}...")
        log.info(f"Enhanced CSV hash: {enhanced_file_hash[:16]}...")
        log.info(f"Unique enhancement hash: {unique_enhancement_hash[:16]}...")
        log.info(f"Hash components: original={original_hash[:8] if original_hash else 'None'}, timestamp={enhancement_timestamp[:19] if enhancement_timestamp else 'None'}, urls={urls_processed}, run_id={run_id}")
        log.info(f"Hash comparison - Enhanced vs Original: {enhanced_file_hash == original_hash}")
        
        # Use the unique enhancement hash for the ImportFile record
        final_hash = unique_enhancement_hash
        
        # Create new ImportFile entry
        log.info(f"Creating new ImportFile entry with unique hash")
        enhanced_import = ImportFile(
            project_id=project_id,
            original_name=f"Enhanced {imp.original_name} (URL data)",
            filename=enhanced_filename,
            file_hash=final_hash,  # Use the unique enhancement hash
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
    
    # Calculate actual processing count based on parallel processing
    if enhancement_run.processed_urls < enhancement_run.total_urls and enhancement_run.status == "running":
        # Calculate how many are currently being processed in parallel
        # Based on the parallel processor logic: up to 10 workers, or 3 per API key
        from ..services.parallel_url_processor import get_available_api_keys
        available_keys = get_available_api_keys()
        max_workers = min(available_keys * 3, 30)  # Same logic as in parallel_url_processor.py
        
        # Estimate current processing: min of remaining URLs and max workers
        remaining_urls = enhancement_run.total_urls - enhancement_run.processed_urls
        processing = min(remaining_urls, max_workers)
    else:
        processing = 0
    
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

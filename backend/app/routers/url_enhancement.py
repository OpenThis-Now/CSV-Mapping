from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any
import requests
import tempfile

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import ImportFile, Project
from ..schemas import ImportUploadResponse
from ..services.files import detect_csv_separator, open_text_stream
from ..services.pdf_processor import extract_pdf_data_with_ai

router = APIRouter()
log = logging.getLogger("app.url_enhancement")


@router.post("/projects/{project_id}/enhance-with-urls", response_model=ImportUploadResponse)
def enhance_csv_with_urls(project_id: int, session: Session = Depends(get_session)) -> ImportUploadResponse:
    """Enhance CSV data by extracting information from PDF URLs."""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    if not p.active_import_id:
        raise HTTPException(status_code=400, detail="Ingen aktiv importfil vald.")
    
    imp = session.get(ImportFile, p.active_import_id)
    if not imp:
        raise HTTPException(status_code=400, detail="Aktiv importfil saknas.")
    
    # Check if the import file has URL mapping
    if "url" not in imp.columns_map_json:
        raise HTTPException(status_code=400, detail="Ingen URL-kolumn hittades i importfilen.")
    
    csv_path = Path(settings.IMPORTS_DIR) / imp.filename
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="Importfil hittades inte.")
    
    try:
        # Read the original CSV
        separator = detect_csv_separator(csv_path)
        with open_text_stream(csv_path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            headers = reader.fieldnames or []
            rows = list(reader)
        
        if not rows:
            raise HTTPException(status_code=400, detail="Inga rader att bearbeta.")
        
        # Get URL column name from mapping
        url_column = imp.columns_map_json["url"]
        product_column = imp.columns_map_json.get("product", "product")
        vendor_column = imp.columns_map_json.get("vendor", "vendor")
        sku_column = imp.columns_map_json.get("sku", "sku")
        market_column = imp.columns_map_json.get("market", "market")
        language_column = imp.columns_map_json.get("language", "language")
        
        enhanced_rows = []
        processed_count = 0
        error_count = 0
        
        for row in rows:
            enhanced_row = row.copy()  # Keep all original data
            
            # Check if this row has a URL
            url = row.get(url_column, "").strip()
            if url and url.startswith(("http://", "https://")):
                try:
                    log.info(f"Processing URL: {url}")
                    
                    # Download and process PDF
                    pdf_data = extract_pdf_data_with_ai(url)
                    log.info(f"PDF data extracted: {pdf_data}")
                    
                    if pdf_data and len(pdf_data) > 0:
                        # Extract data from first result
                        pdf_item = pdf_data[0]
                        
                        # Update only specific fields, preserve all others
                        if pdf_item.get("product_name", {}).get("value"):
                            enhanced_row[product_column] = pdf_item["product_name"]["value"]
                            log.info(f"Updated product: {enhanced_row[product_column]}")
                        
                        if pdf_item.get("company_name", {}).get("value"):
                            enhanced_row[vendor_column] = pdf_item["company_name"]["value"]
                            log.info(f"Updated vendor: {enhanced_row[vendor_column]}")
                        
                        if pdf_item.get("article_number", {}).get("value"):
                            enhanced_row[sku_column] = pdf_item["article_number"]["value"]
                            log.info(f"Updated SKU: {enhanced_row[sku_column]}")
                        
                        if pdf_item.get("authored_market", {}).get("value"):
                            enhanced_row[market_column] = pdf_item["authored_market"]["value"]
                            log.info(f"Updated market: {enhanced_row[market_column]}")
                        
                        if pdf_item.get("language", {}).get("value"):
                            enhanced_row[language_column] = pdf_item["language"]["value"]
                            log.info(f"Updated language: {enhanced_row[language_column]}")
                        
                        processed_count += 1
                        log.info(f"Successfully enhanced row with URL: {url}")
                    else:
                        log.warning(f"No data extracted from URL: {url}")
                        error_count += 1
                        
                except Exception as e:
                    log.error(f"Error processing URL {url}: {str(e)}")
                    error_count += 1
                    # Keep original row data if processing fails
            
            enhanced_rows.append(enhanced_row)
        
        # Create new enhanced CSV file
        enhanced_filename = f"enhanced_{imp.filename}"
        enhanced_path = Path(settings.IMPORTS_DIR) / enhanced_filename
        
        with open(enhanced_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(enhanced_rows)
        
        # Create new ImportFile entry for the enhanced version
        enhanced_import = ImportFile(
            project_id=project_id,
            original_name=f"Enhanced {imp.original_name} (URL data)",
            filename=enhanced_filename,
            columns_map_json=imp.columns_map_json,  # Keep same mapping
            row_count=len(enhanced_rows)
        )
        session.add(enhanced_import)
        session.commit()
        session.refresh(enhanced_import)
        
        log.info(f"Enhanced CSV created: {processed_count} rows processed, {error_count} errors")
        
        return ImportUploadResponse(
            import_file_id=enhanced_import.id,
            filename=enhanced_import.filename,
            row_count=enhanced_import.row_count,
            columns_map_json=enhanced_import.columns_map_json
        )
        
    except Exception as e:
        log.error(f"Error enhancing CSV with URLs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"URL-förbättring misslyckades: {str(e)}")


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

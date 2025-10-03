from __future__ import annotations

import csv
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import MatchResult, Project, RejectedProductData, RejectedExport, DatabaseCatalog
from ..services.files import detect_csv_separator, open_text_stream
from ..services.mapping import auto_map_headers
from rapidfuzz import fuzz

router = APIRouter()


@router.get("/projects/{project_id}/rejected-products")
def get_rejected_products(project_id: int, session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    """Get all rejected products for a project"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Get rejected match results
    rejected_results = session.exec(
        select(MatchResult)
        .where(MatchResult.match_run_id.in_(
            select(MatchResult.match_run_id).where(MatchResult.decision.in_(["rejected", "auto_rejected"]))
        ))
        .where(MatchResult.decision.in_(["rejected", "auto_rejected"]))
    ).all()
    
    # Get or create RejectedProductData entries
    products = []
    for result in rejected_results:
        # Check if we already have RejectedProductData for this match result
        existing_data = session.exec(
            select(RejectedProductData).where(RejectedProductData.match_result_id == result.id)
        ).first()
        
        if not existing_data:
            # Create new RejectedProductData entry
            existing_data = RejectedProductData(
                project_id=project_id,
                match_result_id=result.id,
                status="needs_data"
            )
            session.add(existing_data)
            session.commit()
            session.refresh(existing_data)
        
        # Try to auto-match company ID from database
        company_id = existing_data.company_id
        if not company_id:
            company_id = _auto_match_company_id(result, session)
            if company_id:
                existing_data.company_id = company_id
                session.add(existing_data)
                session.commit()
        
        # Debug logging
        print(f"DEBUG: MatchResult {result.id} customer_fields_json: {result.customer_fields_json}")
        
        # Try different field names for product name (case sensitive!)
        product_name = (
            result.customer_fields_json.get("Product_name") or 
            result.customer_fields_json.get("product") or 
            result.customer_fields_json.get("product_name") or 
            result.customer_fields_json.get("name") or 
            result.customer_fields_json.get("title") or 
            ""
        )
        
        # Try different field names for supplier (case sensitive!)
        supplier = (
            result.customer_fields_json.get("Supplier_name") or 
            result.customer_fields_json.get("vendor") or 
            result.customer_fields_json.get("supplier") or 
            result.customer_fields_json.get("company") or 
            result.customer_fields_json.get("manufacturer") or 
            ""
        )
        
        # Try different field names for article number (case sensitive!)
        article_number = (
            result.customer_fields_json.get("Article_number") or 
            result.customer_fields_json.get("article_number") or 
            result.customer_fields_json.get("sku") or 
            result.customer_fields_json.get("product_id") or 
            result.customer_fields_json.get("part_number") or 
            result.customer_fields_json.get("item_number") or 
            ""
        )
        
        print(f"DEBUG: Extracted - product_name: '{product_name}', supplier: '{supplier}', article_number: '{article_number}'")
        
        products.append({
            "id": existing_data.id,
            "match_result_id": result.id,
            "product_name": product_name,
            "supplier": supplier,
            "article_number": article_number,
            "company_id": company_id,
            "pdf_filename": existing_data.pdf_filename,
            "pdf_source": existing_data.pdf_source,
            "status": existing_data.status,
            "created_at": existing_data.created_at,
            "completed_at": existing_data.completed_at,
            "notes": existing_data.notes,
            "customer_data": result.customer_fields_json,
            "reason": result.reason
        })
    
    return products


def _auto_match_company_id(match_result: MatchResult, session: Session) -> Optional[str]:
    """Try to auto-match company ID from database based on supplier name"""
    # Try different field names for supplier (same as in main function)
    supplier_name = (
        match_result.customer_fields_json.get("Supplier_name", "").strip() or
        match_result.customer_fields_json.get("vendor", "").strip() or
        match_result.customer_fields_json.get("supplier", "").strip() or
        match_result.customer_fields_json.get("company", "").strip() or
        match_result.customer_fields_json.get("manufacturer", "").strip()
    )
    
    if not supplier_name:
        print(f"DEBUG: No supplier name found for auto-matching")
        return None
    
    print(f"DEBUG: Trying to auto-match supplier: '{supplier_name}'")
    
    # Get the active database for this project
    try:
        # Get database file path (this is a simplified approach)
        db_files = list(Path(settings.STORAGE_DIR).glob("databases/*.csv"))
        if not db_files:
            print(f"DEBUG: No database files found")
            return None
        
        print(f"DEBUG: Found {len(db_files)} database files")
        
        # Try to find matching supplier in database
        for db_file in db_files:
            try:
                separator = detect_csv_separator(db_file)
                with open_text_stream(db_file) as f:
                    reader = csv.DictReader(f, delimiter=separator)
                    for row in reader:
                        # Try different field names for supplier in database
                        db_supplier = (
                            row.get("supplier", "").strip() or
                            row.get("vendor", "").strip() or
                            row.get("company", "").strip() or
                            row.get("manufacturer", "").strip()
                        )
                        
                        if db_supplier:
                            # Try multiple matching strategies
                            simple_ratio = fuzz.ratio(supplier_name.lower(), db_supplier.lower())
                            partial_ratio = fuzz.partial_ratio(supplier_name.lower(), db_supplier.lower())
                            token_sort_ratio = fuzz.token_sort_ratio(supplier_name.lower(), db_supplier.lower())
                            token_set_ratio = fuzz.token_set_ratio(supplier_name.lower(), db_supplier.lower())
                            
                            # Use the best match
                            best_match = max(simple_ratio, partial_ratio, token_sort_ratio, token_set_ratio)
                            
                            print(f"DEBUG: Comparing '{supplier_name}' vs '{db_supplier}'")
                            print(f"  Simple ratio: {simple_ratio}%")
                            print(f"  Partial ratio: {partial_ratio}%")
                            print(f"  Token sort ratio: {token_sort_ratio}%")
                            print(f"  Token set ratio: {token_set_ratio}%")
                            print(f"  Best match: {best_match}%")
                            
                            if best_match > 80:
                                # Found a match, return company ID if available
                                company_id = (
                                    row.get("company_id", "").strip() or 
                                    row.get("companyid", "").strip() or
                                    row.get("Company_ID", "").strip()
                                )
                                print(f"DEBUG: Found match! Company ID: '{company_id}'")
                                return company_id
            except Exception as e:
                print(f"DEBUG: Error reading database file {db_file}: {e}")
                continue
    except Exception as e:
        print(f"DEBUG: Error in auto-match: {e}")
        pass
    
    print(f"DEBUG: No match found for supplier: '{supplier_name}'")
    return None


@router.post("/projects/{project_id}/rejected-products/{product_id}/auto-match")
def auto_match_company_id(
    project_id: int,
    product_id: int,
    session: Session = Depends(get_session)
) -> Dict[str, str]:
    """Trigger auto-matching for a specific rejected product"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    product = session.get(RejectedProductData, product_id)
    if not product or product.project_id != project_id:
        raise HTTPException(status_code=404, detail="Rejected product saknas.")
    
    # Get the match result
    match_result = session.get(MatchResult, product.match_result_id)
    if not match_result:
        raise HTTPException(status_code=404, detail="Match result saknas.")
    
    # Try to auto-match company ID
    company_id = _auto_match_company_id(match_result, session)
    if company_id:
        product.company_id = company_id
        session.add(product)
        session.commit()
        return {"message": f"Company ID matched: {company_id}"}
    else:
        return {"message": "No matching company ID found"}


@router.put("/projects/{project_id}/rejected-products/{product_id}")
def update_rejected_product(
    project_id: int, 
    product_id: int, 
    data: Dict[str, Any], 
    session: Session = Depends(get_session)
) -> Dict[str, str]:
    """Update rejected product data"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    product = session.get(RejectedProductData, product_id)
    if not product or product.project_id != project_id:
        raise HTTPException(status_code=404, detail="Rejected product saknas.")
    
    # Update fields
    if "company_id" in data:
        product.company_id = data["company_id"]
    if "pdf_filename" in data:
        product.pdf_filename = data["pdf_filename"]
    if "pdf_source" in data:
        product.pdf_source = data["pdf_source"]
    if "notes" in data:
        product.notes = data["notes"]
    
    # Update status
    if "status" in data:
        product.status = data["status"]
        if data["status"] == "complete":
            product.completed_at = datetime.utcnow()
    
    session.add(product)
    session.commit()
    
    return {"message": "Rejected product updated successfully."}


@router.post("/projects/{project_id}/rejected-products/{product_id}/upload-pdf")
def upload_pdf_for_product(
    project_id: int,
    product_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
) -> Dict[str, str]:
    """Upload PDF for a specific rejected product"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    product = session.get(RejectedProductData, product_id)
    if not product or product.project_id != project_id:
        raise HTTPException(status_code=404, detail="Rejected product saknas.")
    
    # Save PDF file
    pdf_dir = Path(settings.STORAGE_DIR) / "rejected_exports" / f"project_{project_id}"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    
    pdf_filename = f"{product_id}_{file.filename}"
    pdf_path = pdf_dir / pdf_filename
    
    with open(pdf_path, "wb") as f:
        f.write(file.file.read())
    
    # Update product data
    product.pdf_filename = pdf_filename
    product.pdf_source = "uploaded"
    session.add(product)
    session.commit()
    
    return {"message": "PDF uploaded successfully.", "filename": pdf_filename}


@router.post("/projects/{project_id}/rejected-products/upload-zip")
def upload_zip_with_pdfs(
    project_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
) -> Dict[str, str]:
    """Upload ZIP file with PDFs and auto-assign to products"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Create export directory
    export_dir = Path(settings.STORAGE_DIR) / "rejected_exports" / f"project_{project_id}"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    # Save ZIP file
    zip_filename = f"pdfs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = export_dir / zip_filename
    
    with open(zip_path, "wb") as f:
        f.write(file.file.read())
    
    # Extract PDFs and try to auto-assign
    extracted_dir = export_dir / "extracted"
    extracted_dir.mkdir(exist_ok=True)
    
    assigned_count = 0
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for pdf_file in zip_ref.namelist():
            if pdf_file.lower().endswith('.pdf'):
                # Extract PDF
                zip_ref.extract(pdf_file, extracted_dir)
                extracted_path = extracted_dir / pdf_file
                
                # Try to auto-assign to product based on filename
                product_id = _auto_assign_pdf_to_product(pdf_file, project_id, session)
                if product_id:
                    # Move to final location
                    final_filename = f"{product_id}_{Path(pdf_file).name}"
                    final_path = export_dir / final_filename
                    extracted_path.rename(final_path)
                    
                    # Update product data
                    product = session.get(RejectedProductData, product_id)
                    if product:
                        product.pdf_filename = final_filename
                        product.pdf_source = "zip_extracted"
                        session.add(product)
                        assigned_count += 1
    
    session.commit()
    
    return {
        "message": f"ZIP uploaded and processed. {assigned_count} PDFs auto-assigned.",
        "filename": zip_filename,
        "assigned_count": assigned_count
    }


def _auto_assign_pdf_to_product(pdf_filename: str, project_id: int, session: Session) -> Optional[int]:
    """Try to auto-assign PDF to product based on filename"""
    # Get all rejected products for this project
    products = session.exec(
        select(RejectedProductData).where(RejectedProductData.project_id == project_id)
    ).all()
    
    # Try to match PDF filename with product names
    pdf_name_lower = Path(pdf_filename).stem.lower()
    
    for product in products:
        # Get product name from match result
        match_result = session.get(MatchResult, product.match_result_id)
        if match_result:
            product_name = match_result.customer_fields_json.get("product", "").lower()
            if product_name and fuzz.ratio(pdf_name_lower, product_name) > 70:
                return product.id
    
    return None


@router.get("/projects/{project_id}/rejected-products/export")
def export_rejected_products(project_id: int, session: Session = Depends(get_session)) -> Dict[str, str]:
    """Export completed rejected products data"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Get completed products
    completed_products = session.exec(
        select(RejectedProductData).where(
            RejectedProductData.project_id == project_id,
            RejectedProductData.status == "complete"
        )
    ).all()
    
    if not completed_products:
        raise HTTPException(status_code=404, detail="Inga completed products att exportera.")
    
    # Create export directory
    export_dir = Path(settings.STORAGE_DIR) / "rejected_exports" / f"project_{project_id}"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    # Create CSV export
    csv_filename = f"rejected_products_complete_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = export_dir / csv_filename
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Product Name", "Supplier", "Company ID", "PDF Filename", 
            "Status", "Completed At", "Notes"
        ])
        
        for product in completed_products:
            match_result = session.get(MatchResult, product.match_result_id)
            if match_result:
                writer.writerow([
                    match_result.customer_fields_json.get("product", ""),
                    match_result.customer_fields_json.get("vendor", ""),
                    product.company_id or "",
                    product.pdf_filename or "",
                    product.status,
                    product.completed_at.isoformat() if product.completed_at else "",
                    product.notes or ""
                ])
    
    # Create export record
    export_record = RejectedExport(
        project_id=project_id,
        export_type="complete_data",
        filename=csv_filename,
        file_path=str(csv_path),
        status="completed"
    )
    session.add(export_record)
    session.commit()
    
    return {
        "message": "Export completed successfully.",
        "filename": csv_filename,
        "file_path": str(csv_path),
        "count": len(completed_products)
    }

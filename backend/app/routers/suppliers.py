from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import Project, SupplierData, MatchResult, RejectedProductData
from ..services.files import check_upload, compute_hash_and_save, open_text_stream, detect_csv_separator
from ..services.mapping import auto_map_headers

router = APIRouter()


@router.post("/projects/{project_id}/suppliers/upload")
def upload_suppliers_csv(project_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Upload suppliers CSV file for a project"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    check_upload(file)
    _, path = compute_hash_and_save(Path(settings.IMPORTS_DIR), file)

    separator = detect_csv_separator(path)
    
    with open_text_stream(path) as f:
        reader = csv.DictReader(f, delimiter=separator)
        headers = reader.fieldnames or []
        if not headers:
            raise HTTPException(status_code=400, detail="CSV saknar rubriker.")
        
        # Clear existing supplier data for this project
        existing_suppliers = session.exec(
            select(SupplierData).where(SupplierData.project_id == project_id)
        ).all()
        for supplier in existing_suppliers:
            session.delete(supplier)
        session.commit()
        
        # Process CSV rows
        suppliers_added = 0
        for row in reader:
            supplier_name = row.get("Supplier name", "").strip()
            company_id = row.get("CompanyID", "").strip()
            country = row.get("Country", "").strip()
            total = int(row.get("Total", "0") or "0")
            
            if supplier_name and company_id and country:
                supplier = SupplierData(
                    project_id=project_id,
                    supplier_name=supplier_name,
                    company_id=company_id,
                    country=country,
                    total=total
                )
                session.add(supplier)
                suppliers_added += 1
        
        session.commit()
    
    return {
        "message": f"Suppliers CSV uploaded successfully. {suppliers_added} suppliers added.",
        "suppliers_count": suppliers_added
    }


@router.get("/projects/{project_id}/suppliers")
def get_suppliers(project_id: int, session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    """Get all suppliers for a project"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    suppliers = session.exec(
        select(SupplierData).where(SupplierData.project_id == project_id)
    ).all()
    
    return [
        {
            "id": supplier.id,
            "supplier_name": supplier.supplier_name,
            "company_id": supplier.company_id,
            "country": supplier.country,
            "total": supplier.total,
            "created_at": supplier.created_at
        }
        for supplier in suppliers
    ]


@router.get("/projects/{project_id}/supplier-mapping")
def get_supplier_mapping(project_id: int, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Get supplier mapping summary for rejected products"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Get all rejected products that have supplier names
    rejected_results = session.exec(
        select(MatchResult)
        .where(MatchResult.match_run_id.in_(
            select(MatchResult.match_run_id).where(MatchResult.decision.in_(["rejected", "auto_rejected", "ai_auto_rejected"]))
        ))
        .where(MatchResult.decision.in_(["rejected", "auto_rejected", "ai_auto_rejected"]))
    ).all()
    
    # Group by supplier name and country
    supplier_summary = {}
    unmatched_suppliers = []
    
    for result in rejected_results:
        # Try different field names for supplier
        supplier_name = (
            result.customer_fields_json.get("Supplier_name", "").strip() or
            result.customer_fields_json.get("vendor", "").strip() or
            result.customer_fields_json.get("supplier", "").strip() or
            result.customer_fields_json.get("company", "").strip() or
            result.customer_fields_json.get("manufacturer", "").strip()
        )
        
        # Try different field names for country/market
        country = (
            result.customer_fields_json.get("Country", "").strip() or
            result.customer_fields_json.get("Market", "").strip() or
            result.customer_fields_json.get("country", "").strip() or
            result.customer_fields_json.get("market", "").strip()
        )
        
        if supplier_name and country:
            key = f"{supplier_name}|{country}"
            if key not in supplier_summary:
                supplier_summary[key] = {
                    "supplier_name": supplier_name,
                    "country": country,
                    "product_count": 0,
                    "products": []
                }
            
            supplier_summary[key]["product_count"] += 1
            supplier_summary[key]["products"].append({
                "id": result.id,
                "customer_row_index": result.customer_row_index,
                "decision": result.decision,
                "reason": result.reason
            })
        elif supplier_name:
            unmatched_suppliers.append({
                "supplier_name": supplier_name,
                "product_count": 1,
                "products": [{
                    "id": result.id,
                    "customer_row_index": result.customer_row_index,
                    "decision": result.decision,
                    "reason": result.reason
                }]
            })
    
    return {
        "supplier_summary": list(supplier_summary.values()),
        "unmatched_suppliers": unmatched_suppliers,
        "total_unmatched_products": len(rejected_results)
    }


@router.post("/projects/{project_id}/suppliers/ai-match")
def ai_match_suppliers(project_id: int, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Use AI to match suppliers from rejected products with supplier CSV data"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Get all suppliers from CSV
    suppliers = session.exec(
        select(SupplierData).where(SupplierData.project_id == project_id)
    ).all()
    
    if not suppliers:
        raise HTTPException(status_code=400, detail="Inga suppliers laddade upp. Ladda upp suppliers CSV först.")
    
    # Get supplier mapping summary
    mapping_data = get_supplier_mapping(project_id, session)
    supplier_summary = mapping_data["supplier_summary"]
    
    matched_results = []
    new_country_needed = []
    new_supplier_needed = []
    
    for supplier_group in supplier_summary:
        supplier_name = supplier_group["supplier_name"]
        country = supplier_group["country"]
        
        # Look for exact match: Country + Supplier name
        exact_matches = [
            s for s in suppliers 
            if s.country.lower() == country.lower() and s.supplier_name.lower() == supplier_name.lower()
        ]
        
        if exact_matches:
            # If multiple matches, prioritize by highest total
            best_match = max(exact_matches, key=lambda x: x.total)
            matched_results.append({
                "supplier_name": supplier_name,
                "country": country,
                "matched_supplier": best_match,
                "match_type": "exact_match",
                "products_affected": len(supplier_group["products"])
            })
        else:
            # Look for supplier name match only (new country needed)
            supplier_matches = [
                s for s in suppliers 
                if s.supplier_name.lower() == supplier_name.lower()
            ]
            
            if supplier_matches:
                # If multiple matches, prioritize by highest total
                best_match = max(supplier_matches, key=lambda x: x.total)
                new_country_needed.append({
                    "supplier_name": supplier_name,
                    "current_country": country,
                    "matched_supplier": best_match,
                    "products_affected": len(supplier_group["products"])
                })
            else:
                new_supplier_needed.append({
                    "supplier_name": supplier_name,
                    "country": country,
                    "products_affected": len(supplier_group["products"])
                })
    
    return {
        "matched_suppliers": matched_results,
        "new_country_needed": new_country_needed,
        "new_supplier_needed": new_supplier_needed,
        "summary": {
            "total_matched": len(matched_results),
            "new_country_needed": len(new_country_needed),
            "new_supplier_needed": len(new_supplier_needed)
        }
    }


@router.post("/projects/{project_id}/suppliers/apply-matches")
def apply_supplier_matches(project_id: int, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Apply supplier matches to rejected products"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Get AI matching results
    ai_results = ai_match_suppliers(project_id, session)
    matched_results = ai_results["matched_suppliers"]
    
    updated_products = 0
    
    for match in matched_results:
        supplier_name = match["supplier_name"]
        country = match["country"]
        matched_supplier = match["matched_supplier"]
        
        # Find rejected products with this supplier and country
        rejected_results = session.exec(
            select(MatchResult)
            .where(MatchResult.match_run_id.in_(
                select(MatchResult.match_run_id).where(MatchResult.decision.in_(["rejected", "auto_rejected", "ai_auto_rejected"]))
            ))
            .where(MatchResult.decision.in_(["rejected", "auto_rejected", "ai_auto_rejected"]))
        ).all()
        
        for result in rejected_results:
            # Check if this result matches the supplier and country
            result_supplier = (
                result.customer_fields_json.get("Supplier_name", "").strip() or
                result.customer_fields_json.get("vendor", "").strip() or
                result.customer_fields_json.get("supplier", "").strip() or
                result.customer_fields_json.get("company", "").strip() or
                result.customer_fields_json.get("manufacturer", "").strip()
            )
            
            result_country = (
                result.customer_fields_json.get("Country", "").strip() or
                result.customer_fields_json.get("Market", "").strip() or
                result.customer_fields_json.get("country", "").strip() or
                result.customer_fields_json.get("market", "").strip()
            )
            
            if (result_supplier.lower() == supplier_name.lower() and 
                result_country.lower() == country.lower()):
                
                # Update or create RejectedProductData
                existing_data = session.exec(
                    select(RejectedProductData).where(RejectedProductData.match_result_id == result.id)
                ).first()
                
                if not existing_data:
                    existing_data = RejectedProductData(
                        project_id=project_id,
                        match_result_id=result.id,
                        status="needs_data"
                    )
                    session.add(existing_data)
                
                # Update with matched supplier information
                existing_data.company_id = matched_supplier.company_id
                session.add(existing_data)
                updated_products += 1
    
    session.commit()
    
    return {
        "message": f"Applied supplier matches to {updated_products} products.",
        "updated_products": updated_products
    }

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select
from rapidfuzz import fuzz

from ..config import settings
from ..db import get_session
from ..models import Project, SupplierData, MatchResult, RejectedProductData
from .rejected_products import update_product_status_based_on_data
from ..services.files import check_upload, compute_hash_and_save, open_text_stream, detect_csv_separator
from ..services.mapping import auto_map_headers

router = APIRouter()


def normalize_supplier_name(name: str) -> str:
    """Normalize supplier name for better matching"""
    if not name:
        return ""
    
    # Convert to lowercase
    normalized = name.lower().strip()
    
    # Remove common company suffixes and legal terms
    suffixes_to_remove = [
        r'\b(pty\s+)?ltd\.?\b',
        r'\b(pty\s+)?limited\.?\b', 
        r'\binc\.?\b',
        r'\bincorporated\.?\b',
        r'\bcorp\.?\b',
        r'\bcorporation\.?\b',
        r'\bco\.?\b',
        r'\bcompany\.?\b',
        r'\bgmbh\.?\b',
        r'\bag\.?\b',
        r'\bs\.?a\.?\b',
        r'\bs\.?r\.?l\.?\b',
        r'\bllc\.?\b',
        r'\bllp\.?\b',
        r'\bplc\.?\b',
        r'\bthe\b',  # Remove "The" at the beginning
        r'\btrading\b',  # Remove generic "trading" terms
        r'\bgroup\b',    # Remove generic "group" terms
        r'\bholdings\b', # Remove generic "holdings" terms
        r'\binternational\b', # Remove generic "international" terms
    ]
    
    for suffix in suffixes_to_remove:
        normalized = re.sub(suffix, '', normalized)
    
    # Remove extra whitespace and punctuation
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def calculate_supplier_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two supplier names"""
    if not name1 or not name2:
        return 0.0
    
    # Normalize both names
    norm1 = normalize_supplier_name(name1)
    norm2 = normalize_supplier_name(name2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # Check if they have any meaningful words in common
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    # Remove very common words that don't indicate company identity
    common_words = {'australia', 'international', 'global', 'worldwide', 'europe', 'america', 'asia', 'pacific', 'north', 'south', 'east', 'west', 'central', 'solutions', 'services', 'systems', 'technologies', 'industries'}
    words1 = words1 - common_words
    words2 = words2 - common_words
    
    # If no meaningful words in common, similarity should be very low
    if not words1 or not words2:
        return 0.0
    
    common_meaningful_words = words1.intersection(words2)
    if not common_meaningful_words:
        return 0.0  # No meaningful words in common = very different companies
    
    # Calculate multiple similarity metrics
    ratio = fuzz.ratio(norm1, norm2)
    token_sort_ratio = fuzz.token_sort_ratio(norm1, norm2)
    token_set_ratio = fuzz.token_set_ratio(norm1, norm2)
    
    # Use the highest score
    max_score = max(ratio, token_sort_ratio, token_set_ratio)
    
    # Apply penalty if very few meaningful words in common
    meaningful_word_ratio = len(common_meaningful_words) / max(len(words1), len(words2))
    if meaningful_word_ratio < 0.3:  # Less than 30% of meaningful words in common
        max_score *= 0.7  # Apply 30% penalty
    
    return max_score / 100.0  # Convert to 0-1 scale


def find_best_supplier_match(target_name: str, suppliers: List[SupplierData], 
                           country: str = None, min_similarity: float = 0.8, require_country_match: bool = True) -> Optional[SupplierData]:
    """Find the best matching supplier using fuzzy matching"""
    best_match = None
    best_score = 0.0
    
    for supplier in suppliers:
        # If country matching is required and countries don't match, skip this supplier entirely
        if require_country_match and country and supplier.country.lower() != country.lower():
            continue  # Skip suppliers from different countries
        
        # If country is specified but not required, apply penalty
        country_penalty = 0.0
        if not require_country_match and country and supplier.country.lower() != country.lower():
            country_penalty = 0.3  # Larger penalty for different countries when not required
        
        # Calculate similarity score
        similarity = calculate_supplier_similarity(target_name, supplier.supplier_name)
        adjusted_score = similarity - country_penalty
        
        # Apply total-based bonus (prefer suppliers with more products)
        total_bonus = min(supplier.total / 10000.0, 0.05)  # Max 5% bonus for high-volume suppliers
        adjusted_score += total_bonus
        
        if adjusted_score >= min_similarity and adjusted_score > best_score:
            best_score = adjusted_score
            best_match = supplier
    
    return best_match


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
        
        # Debug: Log available headers
        # print(f"DEBUG: Available CSV headers: {headers}")
        
        # Clear existing supplier data for this project
        existing_suppliers = session.exec(
            select(SupplierData).where(SupplierData.project_id == project_id)
        ).all()
        for supplier in existing_suppliers:
            session.delete(supplier)
        session.commit()
        
        # Process CSV rows
        suppliers_added = 0
        skipped_rows = 0
        
        for row_num, row in enumerate(reader, start=2):  # Start at 2 since header is row 1
            # Try different possible column names (case insensitive)
            supplier_name = (
                row.get("Supplier name", "").strip() or
                row.get("supplier_name", "").strip() or
                row.get("Supplier", "").strip() or
                row.get("supplier", "").strip() or
                row.get("Supplier Name", "").strip() or
                row.get("SUPPLIER NAME", "").strip()
            )
            
            company_id = (
                row.get("CompanyID", "").strip() or
                row.get("company_id", "").strip() or
                row.get("Company ID", "").strip() or
                row.get("companyid", "").strip() or
                row.get("COMPANY_ID", "").strip()
            )
            
            country = (
                row.get("Country", "").strip() or
                row.get("country", "").strip() or
                row.get("COUNTRY", "").strip() or
                row.get("Market", "").strip() or
                row.get("market", "").strip()
            )
            
            total_str = (
                row.get("Total", "0") or
                row.get("total", "0") or
                row.get("TOTAL", "0") or
                row.get("Count", "0") or
                row.get("count", "0") or
                "0"
            )
            
            try:
                total = int(total_str)
            except (ValueError, TypeError):
                total = 0
            
            # print(f"DEBUG: Row {row_num}: supplier_name='{supplier_name}', company_id='{company_id}', country='{country}', total={total}")
            
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
                # print(f"DEBUG: Added supplier: {supplier_name} ({country})")
            else:
                skipped_rows += 1
                # print(f"DEBUG: Skipped row {row_num} - missing required fields")
        
        session.commit()
        # print(f"DEBUG: Processing complete. Added: {suppliers_added}, Skipped: {skipped_rows}")
    
    return {
        "message": f"Suppliers CSV uploaded successfully. {suppliers_added} suppliers added.",
        "suppliers_count": suppliers_added
    }


@router.get("/projects/{project_id}/suppliers")
def get_suppliers(project_id: int, session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    """Get all suppliers for a project"""
    try:
        p = session.get(Project, project_id)
        if not p:
            raise HTTPException(status_code=404, detail="Projekt saknas.")
        
        suppliers = session.exec(
            select(SupplierData).where(SupplierData.project_id == project_id)
        ).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load suppliers: {str(e)}")
    
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
    
    # Perform AI matching on the supplier summary
    supplier_list = list(supplier_summary.values())
    
    # Get all suppliers from CSV for matching
    csv_suppliers = session.exec(
        select(SupplierData).where(SupplierData.project_id == project_id)
    ).all()
    
    matched_results = []
    new_country_needed = []
    new_supplier_needed = []
    
    if csv_suppliers:
        # Prepare supplier data for AI - LIMIT to avoid rate limits
        # Only send max 100 suppliers to avoid token limits
        supplier_data_text = "\n".join([
            f"- {supplier.supplier_name} ({supplier.country}) - CompanyID: {supplier.company_id}"
            for supplier in csv_suppliers[:100]  # LIMIT to first 100
        ])
        
        # Filter out suppliers that have already been matched in previous runs
        # by checking if any of their products have been approved
        already_matched_suppliers = set()
        for supplier_group in supplier_list:
            supplier_name = supplier_group["supplier_name"]
            country = supplier_group["country"]
            
            # Check if any products from this supplier have been approved
            has_approved_products = any(
                product.get("decision") in ["approved", "auto_approved", "ai_auto_approved"]
                for product in supplier_group["products"]
            )
            
            if has_approved_products:
                already_matched_suppliers.add(f"{supplier_name}|{country}")
                print(f"DEBUG: Skipping already matched supplier: '{supplier_name}' ({country})")
        
        # Filter supplier list to only include unmatched suppliers
        unmatched_supplier_list = [
            supplier for supplier in supplier_list
            if f"{supplier['supplier_name']}|{supplier['country']}" not in already_matched_suppliers
        ]
        
        print(f"DEBUG: Total suppliers: {len(supplier_list)}, Already matched: {len(already_matched_suppliers)}, Unmatched: {len(unmatched_supplier_list)}")
        
        for supplier_group in unmatched_supplier_list:
            supplier_name = supplier_group["supplier_name"]
            country = supplier_group["country"]
            products_affected = supplier_group["product_count"]
            
            print(f"DEBUG: AI matching supplier: '{supplier_name}' in country: '{country}'")
            
            # First try exact match
            exact_matches = [
                s for s in csv_suppliers 
                if s.country.lower() == country.lower() and s.supplier_name.lower() == supplier_name.lower()
            ]
            
            if exact_matches:
                best_match = max(exact_matches, key=lambda x: x.total)
                matched_results.append({
                    "supplier_name": supplier_name,
                    "country": country,
                    "matched_supplier": best_match,
                    "match_type": "exact_match",
                    "products_affected": products_affected
                })
                print(f"DEBUG: Exact match found: {best_match.supplier_name}")
            else:
                # Use AI to find the best match
                # Create a more targeted prompt for Castrol specifically
                if 'castrol' in supplier_name.lower():
                    castrol_suppliers = [s for s in csv_suppliers if 'castrol' in s.supplier_name.lower()]
                    castrol_text = "\n".join([
                        f"- {supplier.supplier_name} ({supplier.country}) - CompanyID: {supplier.company_id}"
                        for supplier in castrol_suppliers
                    ])
                    ai_prompt = f"""
You are matching this CASTROL supplier to the best match in our database.

Target: "{supplier_name}" in {country}

Available Castrol suppliers in database:
{castrol_text}

**CRITICAL:** "Castrol AB Tel 08-4411100" should match with "Castrol AB" or similar Castrol variant.

Response format:
MATCH_TYPE: [EXACT_MATCH/SIMILAR_SAME_COUNTRY/SIMILAR_DIFFERENT_COUNTRY/NO_MATCH]
COMPANY_ID: [CompanyID if match found]
REASONING: [Brief explanation]
"""
                else:
                    ai_prompt = f"""
You are a supplier matching expert. Find the best match for this supplier.

Target: "{supplier_name}" in {country}

Available suppliers (showing first 100):
{supplier_data_text}

**Matching rules:**
1. EXACT_MATCH: Same name, same country
2. SIMILAR_SAME_COUNTRY: Similar name, same country (ignore phone numbers/addresses)
3. SIMILAR_DIFFERENT_COUNTRY: Similar name, different country
4. NO_MATCH: No similar company found

Response format:
MATCH_TYPE: [EXACT_MATCH/SIMILAR_SAME_COUNTRY/SIMILAR_DIFFERENT_COUNTRY/NO_MATCH]
COMPANY_ID: [CompanyID if match found]
REASONING: [Brief explanation]
"""
                
                try:
                    from ..openai_client import suggest_with_openai
                    print(f"DEBUG: Sending to AI - Target: '{supplier_name}' ({country})")
                    print(f"DEBUG: Available suppliers count: {len(csv_suppliers)}")
                    # Show first few suppliers for debugging
                    castrol_suppliers = [s for s in csv_suppliers if 'castrol' in s.supplier_name.lower()]
                    print(f"DEBUG: Castrol suppliers found: {len(castrol_suppliers)}")
                    for cs in castrol_suppliers[:5]:  # Show first 5
                        print(f"DEBUG:   - {cs.supplier_name} ({cs.country}) - ID: {cs.company_id}")
                    
                    ai_response = suggest_with_openai(ai_prompt, api_key_index=0)
                    print(f"DEBUG: AI response for {supplier_name}: {ai_response}")
                    
                    if "EXACT_MATCH" in ai_response:
                        company_id_match = re.search(r'COMPANY_ID:\s*(\d+)', ai_response)
                        if company_id_match:
                            company_id = int(company_id_match.group(1))
                            matched_supplier = next((s for s in csv_suppliers if s.company_id == company_id), None)
                            if matched_supplier:
                                matched_results.append({
                                    "supplier_name": supplier_name,
                                    "country": country,
                                    "matched_supplier": matched_supplier,
                                    "match_type": "ai_exact_match",
                                    "products_affected": products_affected
                                })
                                print(f"DEBUG: AI exact match found: {matched_supplier.supplier_name}")
                                continue
                    
                    elif "SIMILAR_SAME_COUNTRY" in ai_response:
                        company_id_match = re.search(r'COMPANY_ID:\s*(\d+)', ai_response)
                        if company_id_match:
                            company_id = int(company_id_match.group(1))
                            matched_supplier = next((s for s in csv_suppliers if s.company_id == company_id), None)
                            if matched_supplier:
                                matched_results.append({
                                    "supplier_name": supplier_name,
                                    "country": country,
                                    "matched_supplier": matched_supplier,
                                    "match_type": "ai_similar_same_country",
                                    "products_affected": products_affected
                                })
                                print(f"DEBUG: AI similar match (same country): {matched_supplier.supplier_name}")
                                continue
                    
                    elif "SIMILAR_DIFFERENT_COUNTRY" in ai_response:
                        company_id_match = re.search(r'COMPANY_ID:\s*(\d+)', ai_response)
                        if company_id_match:
                            company_id = int(company_id_match.group(1))
                            matched_supplier = next((s for s in csv_suppliers if s.company_id == company_id), None)
                            if matched_supplier:
                                new_country_needed.append({
                                    "supplier_name": supplier_name,
                                    "country": country,
                                    "matched_supplier": matched_supplier,
                                    "products_affected": products_affected
                                })
                                print(f"DEBUG: AI similar match (different country): {matched_supplier.supplier_name}")
                                continue
                    
                    # If AI says NO_MATCH or couldn't find a match
                    new_supplier_needed.append({
                        "supplier_name": supplier_name,
                        "country": country,
                        "products_affected": products_affected
                    })
                    print(f"DEBUG: AI found no match for: {supplier_name}")
                    
                except Exception as e:
                    print(f"DEBUG: AI matching failed for {supplier_name}: {e}")
                    new_supplier_needed.append({
                        "supplier_name": supplier_name,
                        "country": country,
                        "products_affected": products_affected
                    })
    else:
        # No CSV suppliers uploaded, all are new supplier needed
        for supplier_group in supplier_list:
            new_supplier_needed.append({
                "supplier_name": supplier_group["supplier_name"],
                "country": supplier_group["country"],
                "products_affected": supplier_group["product_count"]
            })
    
    return {
        "supplier_summary": supplier_list,
        "unmatched_suppliers": unmatched_suppliers,
        "total_unmatched_products": len(rejected_results),
        "matched_suppliers": matched_results,
        "new_country_needed": new_country_needed,
        "new_supplier_needed": new_supplier_needed
    }


@router.post("/projects/{project_id}/suppliers/ai-match")
def ai_match_suppliers(project_id: int, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Use AI to match suppliers from rejected products with supplier CSV data"""
    from ..openai_client import suggest_with_openai
    
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
    
    # Prepare supplier data for AI
    supplier_list = []
    for supplier in suppliers:
        supplier_list.append(f"- {supplier.supplier_name} ({supplier.country}) - CompanyID: {supplier.company_id}")
    
    supplier_data_text = "\n".join(supplier_list)
    
    for supplier_group in supplier_summary:
        supplier_name = supplier_group["supplier_name"]
        country = supplier_group["country"]
        products_affected = len(supplier_group["products"])
        
        print(f"DEBUG: AI matching supplier: '{supplier_name}' in country: '{country}'")
        
        # First try exact match: Country + Supplier name
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
                "products_affected": products_affected
            })
            print(f"DEBUG: Exact match found: {best_match.supplier_name}")
        else:
            # Use AI to find the best match
            ai_prompt = f"""
You are a supplier matching expert. I need you to find the best match for this supplier in our database.

Target supplier to match: "{supplier_name}" in country: "{country}"

Available suppliers in database:
{supplier_data_text}

Please analyze and respond with ONE of these options:

1. EXACT_MATCH: If you find an exact match (same name, same country)
2. SIMILAR_DIFFERENT_COUNTRY: If you find a very similar company name but in a different country
3. NO_MATCH: If no similar company is found

For EXACT_MATCH or SIMILAR_DIFFERENT_COUNTRY, also provide the CompanyID of the matched supplier.

Response format:
MATCH_TYPE: [EXACT_MATCH/SIMILAR_DIFFERENT_COUNTRY/NO_MATCH]
COMPANY_ID: [CompanyID if match found]
REASONING: [Brief explanation of your decision]
"""
            
            try:
                ai_response = suggest_with_openai(ai_prompt, api_key_index=0)
                print(f"DEBUG: AI response for {supplier_name}: {ai_response}")
                
                if "EXACT_MATCH" in ai_response:
                    # Extract CompanyID and find the supplier
                    company_id_match = re.search(r'COMPANY_ID:\s*(\d+)', ai_response)
                    if company_id_match:
                        company_id = int(company_id_match.group(1))
                        matched_supplier = next((s for s in suppliers if s.company_id == company_id), None)
                        if matched_supplier:
                            matched_results.append({
                                "supplier_name": supplier_name,
                                "country": country,
                                "matched_supplier": matched_supplier,
                                "match_type": "ai_exact_match",
                                "products_affected": products_affected
                            })
                            print(f"DEBUG: AI exact match found: {matched_supplier.supplier_name}")
                            continue
                
                elif "SIMILAR_DIFFERENT_COUNTRY" in ai_response:
                    # Extract CompanyID and find the supplier
                    company_id_match = re.search(r'COMPANY_ID:\s*(\d+)', ai_response)
                    if company_id_match:
                        company_id = int(company_id_match.group(1))
                        matched_supplier = next((s for s in suppliers if s.company_id == company_id), None)
                        if matched_supplier:
                            new_country_needed.append({
                                "supplier_name": supplier_name,
                                "country": country,
                                "matched_supplier": matched_supplier,
                                "products_affected": products_affected
                            })
                            print(f"DEBUG: AI similar match (different country): {matched_supplier.supplier_name}")
                            continue
                
                # If AI says NO_MATCH or couldn't find a match, add to new_supplier_needed
                new_supplier_needed.append({
                    "supplier_name": supplier_name,
                    "country": country,
                    "products_affected": products_affected
                })
                print(f"DEBUG: AI found no match for: {supplier_name}")
                
            except Exception as e:
                print(f"DEBUG: AI matching failed for {supplier_name}: {e}")
                # Fallback to new_supplier_needed
                new_supplier_needed.append({
                    "supplier_name": supplier_name,
                    "country": country,
                    "products_affected": products_affected
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


@router.get("/projects/{project_id}/suppliers/test-matching")
def test_supplier_matching(project_id: int, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Test the supplier matching logic with sample data"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Test cases
    test_cases = [
        ("AMPOL AUSTRALIA PETROLEUM PTY LTD", "AMPOL AUSTRALIA PTY LTD"),
        ("Microsoft Corporation", "Microsoft Inc."),
        ("Apple Inc.", "Apple Computer Inc."),
        ("Google LLC", "Google Inc."),
        ("3M Company", "Minnesota Mining and Manufacturing Company"),
        ("Adventure Trading Australia Pty Ltd", "3M Australia"),  # Should NOT match
        ("Adventure Trading Australia Pty Ltd", "Adventure Group Australia"),  # Should match
        ("BP Australia", "British Petroleum Australia"),  # Should match
        ("Shell Australia", "Shell International"),  # Should match
        ("Chevron Australia", "Exxon Australia"),  # Should NOT match
    ]
    
    results = []
    
    for name1, name2 in test_cases:
        similarity = calculate_supplier_similarity(name1, name2)
        norm1 = normalize_supplier_name(name1)
        norm2 = normalize_supplier_name(name2)
        
        results.append({
            "name1": name1,
            "name2": name2,
            "normalized1": norm1,
            "normalized2": norm2,
            "similarity": similarity,
            "would_match_exact": similarity >= 0.95,  # New stricter threshold
            "would_match_country_needed": similarity >= 0.90,
            "would_match_old": similarity >= 0.8  # Old threshold for comparison
        })
    
    return {
        "test_results": results,
        "normalization_examples": {
            "original": "AMPOL AUSTRALIA PETROLEUM PTY LTD",
            "normalized": normalize_supplier_name("AMPOL AUSTRALIA PETROLEUM PTY LTD")
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
                    # Create RejectedProductData with auto-determined status
                    temp_product = RejectedProductData(
                        project_id=project_id,
                        match_result_id=result.id,
                        company_id=None,
                        pdf_filename=None
                    )
                    status = update_product_status_based_on_data(temp_product)
                    
                    existing_data = RejectedProductData(
                        project_id=project_id,
                        match_result_id=result.id,
                        status=status
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

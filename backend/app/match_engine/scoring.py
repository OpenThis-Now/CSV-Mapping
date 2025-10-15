from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from .normalize import normalize_text, extract_numbers
from .thresholds import Thresholds


def score_fields(customer: str, db: str) -> int:
    a, b = normalize_text(customer), normalize_text(db)
    
    # Handle products with multiple names separated by commas
    # Split by comma and test each part, return the highest score
    if ',' in db:
        db_parts = [part.strip() for part in db.split(',')]
        max_score = 0
        for db_part in db_parts:
            if db_part:  # Skip empty parts
                part_a, part_b = normalize_text(customer), normalize_text(db_part)
                part_score = int(fuzz.token_sort_ratio(part_a, part_b))
                # Apply chemical penalty for this part
                chemical_penalty = calculate_chemical_penalty(customer, db_part)
                final_score = max(0, part_score - chemical_penalty)
                max_score = max(max_score, final_score)
        return max_score
    
    # Original logic for single product names
    base_score = int(fuzz.token_sort_ratio(a, b))
    
    # Apply chemical name penalty for significant chemical differences
    chemical_penalty = calculate_chemical_penalty(customer, db)
    return max(0, base_score - chemical_penalty)


def calculate_chemical_penalty(customer: str, db: str) -> int:
    """Calculate penalty for chemical name mismatches"""
    if not customer or not db:
        return 0
    
    customer_lower = customer.lower()
    db_lower = db.lower()
    
    # List of important chemical prefixes/suffixes that should match exactly
    chemical_indicators = [
        # Acids
        ('acid', 'syra'), ('syra', 'acid'),
        # Specific acids (major chemical differences)
        ('folsyra', 'folic acid'), ('folic acid', 'folsyra'),
        ('oljesyra', 'oleic acid'), ('oleic acid', 'oljesyra'),
        ('citronsyra', 'citric acid'), ('citric acid', 'citronsyra'),
        ('metylsyra', 'formic acid'), ('formic acid', 'metylsyra'),
        ('etylsyra', 'acetic acid'), ('acetic acid', 'etylsyra'),
        
        # Swedish vs Swedish acid differences
        ('folsyra', 'oljesyra'), ('oljesyra', 'folsyra'),
        ('folsyra', 'citronsyra'), ('citronsyra', 'folsyra'),
        ('oljesyra', 'citronsyra'), ('citronsyra', 'oljesyra'),
        
        # Chemical compounds
        ('dextran', 'cefoxitin'), ('cefoxitin', 'dextran'),
        ('calcium', 'sodium'), ('sodium', 'calcium'),
        ('chloride', 'sulfate'), ('sulfate', 'chloride'),
        
        # Major chemical class differences
        ('pantothenic', 'oleic'), ('oleic', 'pantothenic'),
        ('folic', 'oleic'), ('oleic', 'folic'),
    ]
    
    # Check for major chemical differences
    for indicator1, indicator2 in chemical_indicators:
        if indicator1 in customer_lower and indicator2 in db_lower:
            return 40  # High penalty for major chemical differences
        if indicator2 in customer_lower and indicator1 in db_lower:
            return 40
    
    # Check for completely different chemical classes
    # If both contain "acid" but are different types of acids
    if 'acid' in customer_lower and 'acid' in db_lower:
        # Extract the main chemical name before "acid"
        customer_parts = customer_lower.split('acid')[0].strip().split()
        db_parts = db_lower.split('acid')[0].strip().split()
        
        customer_chemical = customer_parts[-1] if customer_parts else ''
        db_chemical = db_parts[-1] if db_parts else ''
        
        if customer_chemical and db_chemical and customer_chemical != db_chemical:
            # Check if they are in the same chemical family
            if not are_similar_acids(customer_chemical, db_chemical):
                return 30  # Penalty for different acid types
    
    return 0


def are_similar_acids(chem1: str, chem2: str) -> bool:
    """Check if two acid names are chemically similar"""
    # Map common acid variations
    acid_families = {
        'folic': ['fol', 'folate'],
        'oleic': ['ole', 'oleat'],
        'citric': ['cit', 'citrat'],
        'acetic': ['acet', 'acetat'],
        'formic': ['form', 'format'],
        'pantothenic': ['panto', 'pantothenat'],
    }
    
    for family, variations in acid_families.items():
        if (chem1 in variations or chem2 in variations) and (chem1 == family or chem2 == family):
            return True
        if chem1 in variations and chem2 in variations:
            return True
    
    return False


def sku_exact(customer_sku: str | None, db_sku: str | None) -> bool:
    if not customer_sku or not db_sku:
        return False
    return normalize_text(customer_sku) == normalize_text(db_sku)


def numeric_penalty(customer_text: str, db_text: str, penalty: int) -> int:
    cn, dn = set(extract_numbers(customer_text)), set(extract_numbers(db_text))
    if not cn or not dn:
        return 0
    if cn.isdisjoint(dn):
        return penalty
    return 0


def score_pair(customer_row: dict[str, Any], db_row: dict[str, Any], customer_mapping: dict[str, str], db_mapping: dict[str, str], thr: Thresholds) -> dict[str, Any]:
    cv, cp, cs = (customer_row.get(customer_mapping["vendor"], ""), customer_row.get(customer_mapping["product"], ""), customer_row.get(customer_mapping["sku"], ""))
    dv, dp, ds = db_row.get(db_mapping["vendor"], ""), db_row.get(db_mapping["product"], ""), db_row.get(db_mapping["sku"], "")

    # Check for file hash match first - if hashes match, auto-approve immediately
    customer_file_hash = customer_row.get("file_hash", "").strip()
    db_file_hash = db_row.get("file_hash", "").strip()
    
    # Debug: Log file hash comparison
    import logging
    log = logging.getLogger("app.match_engine.scoring")
    log.info(f"File hash comparison - Customer: {customer_file_hash[:16] if customer_file_hash else 'None'}...")
    log.info(f"File hash comparison - Database: {db_file_hash[:16] if db_file_hash else 'None'}...")
    log.info(f"File hash match: {customer_file_hash == db_file_hash and customer_file_hash != ''}")
    
    if customer_file_hash and db_file_hash and customer_file_hash == db_file_hash:
        log.info(f"FILE HASH MATCH FOUND! Auto-approving with 100% score")
        return {
            "vendor_score": 100,
            "product_score": 100,
            "overall": 100,
            "exact": True,
            "reason": "Filehash-match",
            "decision": "auto_approved",
        }

    # Check if customer data is missing - if so, reject immediately
    if not cv.strip() and not cp.strip() and not cs.strip():
        return {
            "vendor_score": 0,
            "product_score": 0,
            "overall": 0,
            "exact": False,
            "reason": "Poor data - No customer data available for matching",
            "decision": "auto_rejected",
        }

    # Auto-reject if essential data is missing (supplier name or product name)
    if not cv.strip() or not cp.strip():
        missing_fields = []
        if not cv.strip():
            missing_fields.append("supplier name")
        if not cp.strip():
            missing_fields.append("product name")
        
        return {
            "vendor_score": 0,
            "product_score": 0,
            "overall": 0,
            "exact": False,
            "reason": f"Poor data - Missing {', '.join(missing_fields)}",
            "decision": "auto_rejected",
        }

    # Check market and language compatibility
    customer_market = customer_row.get(customer_mapping.get("market", "Market"), "").strip()
    customer_language = customer_row.get(customer_mapping.get("language", "Language"), "").strip()
    db_market = db_row.get(db_mapping.get("market", "Market"), "").strip()
    db_language = db_row.get(db_mapping.get("language", "Language"), "").strip()


    # Track market and language mismatches for scoring and comments
    market_mismatch = False
    language_mismatch = False
    
    # Normalize market names for better matching
    def normalize_market(market):
        if not market:
            return ""
        market_lower = market.lower().strip()
        # Map common variations to standard names
        if market_lower in ['eu', 'eu (clp/reach)', 'europe', 'european union']:
            return 'eu'
        elif market_lower in ['australia', 'au', 'australian']:
            return 'australia'
        elif market_lower in ['canada', 'ca', 'canadian']:
            return 'canada'
        elif market_lower in ['sweden', 'se', 'swedish']:
            return 'sweden'
        elif market_lower in ['usa', 'us', 'united states', 'american']:
            return 'usa'
        elif market_lower in ['germany', 'de', 'german']:
            return 'germany'
        return market_lower
    
    customer_market_norm = normalize_market(customer_market)
    db_market_norm = normalize_market(db_market)
    
    if customer_market_norm and db_market_norm and customer_market_norm != db_market_norm:
        market_mismatch = True
    
    if customer_language and db_language and customer_language.lower() != db_language.lower():
        language_mismatch = True
    

    # Only score fields that have customer data
    vendor_score = score_fields(cv, dv) if cv.strip() else 0
    product_score = score_fields(cp, dp) if cp.strip() else 0

    overall = int(thr.weight_vendor * vendor_score + thr.weight_product * product_score)

    if sku_exact(cs, ds):
        overall = min(100, overall + thr.sku_exact_boost)
    elif cs.strip() and ds.strip():
        # Apply penalty for SKU mismatch when both SKUs are present
        overall -= 15  # Penalty for different SKUs

    overall -= numeric_penalty(cp, dp, thr.numeric_mismatch_penalty)
    
    # Enforce strict language matching - language must always match
    if language_mismatch:
        # Language mismatch is a hard requirement - auto-reject
        return {
            "vendor_score": vendor_score,
            "product_score": product_score,
            "overall": 0,
            "exact": False,
            "reason": "No match found on market lang",
            "decision": "auto_rejected",
        }
    
    # Handle market mismatches (less strict than language)
    if market_mismatch:
        # Cap score at 70% for market mismatches
        overall = min(70, overall)

    exact = vendor_score >= 95 and product_score >= 95 or sku_exact(cs, ds)

    reason = []
    if sku_exact(cs, ds):
        reason.append("Exact SKU match")
    elif cs.strip() and ds.strip():
        reason.append("Different SKUs")
    if market_mismatch:
        reason.append("Other market")
    
    # Smart recommendation logic - only suggest reviewing fields that actually need review
    review_fields = []
    if vendor_score < thr.vendor_min:
        review_fields.append("supplier")
    if product_score < thr.product_min:
        review_fields.append("product name")
    if cs.strip() and ds.strip() and not sku_exact(cs, ds):
        review_fields.append("article number")
    
    if review_fields:
        if len(review_fields) == 1:
            reason.append(f"Review match - review {review_fields[0]}")
        else:
            reason.append(f"Review match - review {' and '.join(review_fields)}")
    elif vendor_score < thr.vendor_min:
        reason.append("Low vendor match")
    elif product_score < thr.product_min:
        reason.append("Low product match")

    decision = "pending"
    if overall < 30:
        decision = "auto_rejected"
        reason.append("Score too low (< 30)")
    elif overall >= thr.overall_accept and vendor_score >= thr.vendor_min and product_score >= thr.product_min:
        # Check for chemical differences before auto-approving
        chemical_penalty = calculate_chemical_penalty(cp, dp)
        if chemical_penalty >= 30:
            decision = "pending"
            reason.append("Potential chemical difference - requires manual review")
        else:
            decision = "auto_approved"
    # Note: Missing essential data is now handled early in the function with auto_rejected decision

    return {
        "vendor_score": vendor_score,
        "product_score": product_score,
        "overall": overall,
        "exact": bool(exact),
        "reason": ", ".join(reason) or "Good match",
        "decision": decision,
    }


def compute_overall(v: int, p: int, thr: Thresholds) -> int:
    return int(thr.weight_vendor * v + thr.weight_product * p)

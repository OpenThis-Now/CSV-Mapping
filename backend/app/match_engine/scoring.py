from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from .normalize import normalize_text, extract_numbers
from .thresholds import Thresholds


def score_fields(customer: str, db: str) -> int:
    a, b = normalize_text(customer), normalize_text(db)
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

    # Debug logging for market/language detection
    print(f"DEBUG: customer_mapping keys: {list(customer_mapping.keys())}")
    print(f"DEBUG: db_mapping keys: {list(db_mapping.keys())}")
    print(f"DEBUG: customer_market='{customer_market}', db_market='{db_market}'")
    print(f"DEBUG: customer_language='{customer_language}', db_language='{db_language}'")
    print(f"DEBUG: customer_row keys: {list(customer_row.keys())}")
    print(f"DEBUG: db_row keys: {list(db_row.keys())}")
    
    # Show the actual values being compared
    print(f"DEBUG: Customer market value: '{customer_market}' (repr: {repr(customer_market)})")
    print(f"DEBUG: DB market value: '{db_market}' (repr: {repr(db_market)})")
    print(f"DEBUG: Customer language value: '{customer_language}' (repr: {repr(customer_language)})")
    print(f"DEBUG: DB language value: '{db_language}' (repr: {repr(db_language)})")
    
    # Show character codes for comparison
    if customer_market and db_market:
        customer_market_codes = [ord(c) for c in customer_market]
        db_market_codes = [ord(c) for c in db_market]
        print(f"DEBUG: Customer market char codes: {customer_market_codes}")
        print(f"DEBUG: DB market char codes: {db_market_codes}")
    
    if customer_language and db_language:
        customer_language_codes = [ord(c) for c in customer_language]
        db_language_codes = [ord(c) for c in db_language]
        print(f"DEBUG: Customer language char codes: {customer_language_codes}")
        print(f"DEBUG: DB language char codes: {db_language_codes}")

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
        print(f"DEBUG: Market mismatch detected: '{customer_market}' (normalized: '{customer_market_norm}') != '{db_market}' (normalized: '{db_market_norm}')")
        print(f"DEBUG: Market comparison: '{customer_market_norm}' != '{db_market_norm}' -> {customer_market_norm != db_market_norm}")
    else:
        print(f"DEBUG: Market match: '{customer_market}' (normalized: '{customer_market_norm}') == '{db_market}' (normalized: '{db_market_norm}')")
    
    if customer_language and db_language and customer_language.lower() != db_language.lower():
        language_mismatch = True
        print(f"DEBUG: Language mismatch detected: '{customer_language}' != '{db_language}'")
        print(f"DEBUG: Language comparison: '{customer_language.lower()}' != '{db_language.lower()}' -> {customer_language.lower() != db_language.lower()}")
    else:
        print(f"DEBUG: Language match: '{customer_language}' == '{db_language}'")
    
    print(f"DEBUG: market_mismatch={market_mismatch}, language_mismatch={language_mismatch}")

    # Only score fields that have customer data
    vendor_score = score_fields(cv, dv) if cv.strip() else 0
    product_score = score_fields(cp, dp) if cp.strip() else 0

    print(f"DEBUG: Vendor score: {vendor_score} (customer: '{cv}', db: '{dv}')")
    print(f"DEBUG: Product score: {product_score} (customer: '{cp}', db: '{dp}')")

    overall = int(thr.weight_vendor * vendor_score + thr.weight_product * product_score)
    print(f"DEBUG: Initial overall score: {overall}")

    if sku_exact(cs, ds):
        overall = min(100, overall + thr.sku_exact_boost)
        print(f"DEBUG: SKU exact match, boosted score to {overall}")
    elif cs.strip() and ds.strip():
        # Apply penalty for SKU mismatch when both SKUs are present
        overall -= 15  # Penalty for different SKUs
        print(f"DEBUG: SKU mismatch penalty, reduced score to {overall}")

    numeric_pen = numeric_penalty(cp, dp, thr.numeric_mismatch_penalty)
    overall -= numeric_pen
    if numeric_pen > 0:
        print(f"DEBUG: Numeric penalty {numeric_pen}, reduced score to {overall}")
    
    # Be less strict about market/language mismatches - focus on product matching
    if market_mismatch and language_mismatch:
        # Only set to 0 if it's a very poor match anyway
        if overall < 20:
            print(f"DEBUG: Setting score to 0 due to very poor match with market and language mismatch")
            overall = 0
        else:
            # Reduce score but don't eliminate completely - be more lenient
            old_score = overall
            overall = max(15, overall * 0.5)  # Increased from 0.3 to 0.5 and min from 10 to 15
            print(f"DEBUG: Reduced score from {old_score} to {overall} due to market and language mismatch")
    else:
        # Cap score at 80% for market mismatches, 70% for language mismatches (less strict)
        if market_mismatch:
            old_score = overall
            overall = min(80, overall)  # Increased from 70 to 80
            print(f"DEBUG: Capped score from {old_score} to {overall} due to market mismatch")
        if language_mismatch:
            old_score = overall
            overall = min(70, overall)  # Increased from 60 to 70
            print(f"DEBUG: Capped score from {old_score} to {overall} due to language mismatch")
    
    print(f"DEBUG: Final overall score: {overall}")

    exact = vendor_score >= 95 and product_score >= 95 or sku_exact(cs, ds)

    reason = []
    if sku_exact(cs, ds):
        reason.append("Exact SKU match")
    elif cs.strip() and ds.strip():
        reason.append("Different SKUs")
    if market_mismatch and language_mismatch:
        reason.append("Wrong market & language")
    elif market_mismatch:
        reason.append("Other market")
    elif language_mismatch:
        reason.append("Language mismatch")
    if vendor_score < thr.vendor_min:
        reason.append("Low vendor match")
    if product_score < thr.product_min:
        reason.append("Low product match")
    
    print(f"DEBUG: Reasons: {reason}")

    decision = "pending"
    print(f"DEBUG: Decision logic: overall={overall}, vendor_score={vendor_score}, product_score={product_score}")
    print(f"DEBUG: Thresholds: overall_accept={thr.overall_accept}, vendor_min={thr.vendor_min}, product_min={thr.product_min}")
    
    if overall < 30:
        decision = "auto_rejected"
        reason.append("Score too low (< 30)")
        print(f"DEBUG: Decision: {decision} (score too low)")
    elif overall >= thr.overall_accept and vendor_score >= thr.vendor_min and product_score >= thr.product_min:
        # Check for chemical differences before auto-approving
        chemical_penalty = calculate_chemical_penalty(cp, dp)
        print(f"DEBUG: Chemical penalty: {chemical_penalty}")
        if chemical_penalty >= 30:
            decision = "pending"
            reason.append("Potential chemical difference - requires manual review")
            print(f"DEBUG: Decision: {decision} (chemical difference)")
        else:
            decision = "auto_approved"
            print(f"DEBUG: Decision: {decision} (auto-approved)")
    else:
        print(f"DEBUG: Decision: {decision} (pending - thresholds not met)")
    # Note: Missing essential data is now handled early in the function with auto_rejected decision

    result = {
        "vendor_score": vendor_score,
        "product_score": product_score,
        "overall": overall,
        "exact": bool(exact),
        "reason": ", ".join(reason) or "Good match",
        "decision": decision,
    }
    
    print(f"DEBUG: Returning result: {result}")
    return result


def compute_overall(v: int, p: int, thr: Thresholds) -> int:
    return int(thr.weight_vendor * v + thr.weight_product * p)

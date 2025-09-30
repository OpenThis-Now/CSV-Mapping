from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from .normalize import normalize_text, extract_numbers
from .thresholds import Thresholds


def score_fields(customer: str, db: str) -> int:
    a, b = normalize_text(customer), normalize_text(db)
    return int(fuzz.token_sort_ratio(a, b))


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


def score_pair(customer_row: dict[str, Any], db_row: dict[str, Any], mapping: dict[str, str], thr: Thresholds) -> dict[str, Any]:
    cv, cp, cs = (customer_row.get(mapping["vendor"], ""), customer_row.get(mapping["product"], ""), customer_row.get(mapping["sku"], ""))
    dv, dp, ds = db_row.get(mapping["vendor"], ""), db_row.get(mapping["product"], ""), db_row.get(mapping["sku"], "")

    # Check market and language compatibility
    customer_market = customer_row.get(mapping.get("market", "Market"), "").strip()
    customer_language = customer_row.get(mapping.get("language", "Language"), "").strip()
    db_market = db_row.get(mapping.get("market", "Market"), "").strip()
    db_language = db_row.get(mapping.get("language", "Language"), "").strip()

    # If market or language don't match, reject the match completely
    if customer_market and db_market and customer_market.lower() != db_market.lower():
        return {
            "vendor_score": 0,
            "product_score": 0,
            "overall": 0,
            "exact": False,
            "reason": f"Market mismatch: {customer_market} vs {db_market}",
            "decision": "not_approved",
        }
    
    if customer_language and db_language and customer_language.lower() != db_language.lower():
        return {
            "vendor_score": 0,
            "product_score": 0,
            "overall": 0,
            "exact": False,
            "reason": f"Language mismatch: {customer_language} vs {db_language}",
            "decision": "not_approved",
        }

    vendor_score = score_fields(cv, dv)
    product_score = score_fields(cp, dp)

    overall = int(thr.weight_vendor * vendor_score + thr.weight_product * product_score)

    if sku_exact(cs, ds):
        overall = min(100, overall + thr.sku_exact_boost)

    overall -= numeric_penalty(cp, dp, thr.numeric_mismatch_penalty)

    exact = vendor_score >= 95 and product_score >= 95 or sku_exact(cs, ds)

    reason = []
    if sku_exact(cs, ds):
        reason.append("Exact SKU match")
    if vendor_score < thr.vendor_min:
        reason.append("Low vendor match")
    if product_score < thr.product_min:
        reason.append("Low product match")

    decision = "pending"
    if overall < 30:
        decision = "auto_not_approved"
        reason.append("Score too low (< 30)")
    elif overall >= thr.overall_accept and vendor_score >= thr.vendor_min and product_score >= thr.product_min:
        decision = "auto_approved"

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

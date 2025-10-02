from __future__ import annotations

import re
from typing import Iterable


P_CANDIDATES = ["produkt", "product", "product_name", "name", "artikel", "artikelbenämning", "benämning", "title"]
V_CANDIDATES = ["leverantör", "leverantor", "vendor", "supplier", "supplier_name", "brand", "manufacturer", "fabrik", "tillverkare", "company_name"]
S_CANDIDATES = ["sku", "artikelnummer", "artnr", "art_nr", "article_number", "item_no", "item", "partno", "part_no", "gtin", "ean"]
M_CANDIDATES = ["market", "country", "land", "region", "marketplace", "territory"]
L_CANDIDATES = ["language", "lang", "språk", "locale", "tongue"]
U_CANDIDATES = ["sds-url", "sds_url", "sds url", "pdf-url", "pdf_url", "pdf url", "url", "link", "document_url"]
# New field candidates for updated requirements
LOC_ID_CANDIDATES = ["location_id", "location", "loc_id", "site_id", "facility_id", "warehouse_id"]
PROD_ID_CANDIDATES = ["product_id", "prod_id", "item_id", "product_code", "internal_id"]
DESC_CANDIDATES = ["description", "desc", "beskrivning", "details", "notes", "comment"]
# Database-specific candidates
UNIQUE_ID_CANDIDATES = ["unique_id", "company_id", "id", "uid", "identifier", "company_identifier"]
MSDS_KEY_CANDIDATES = ["msdskey", "msds_key", "sds_key", "safety_key", "document_key"]
REV_DATE_CANDIDATES = ["revision_date", "rev_date", "revised", "updated", "last_modified"]
EXP_DATE_CANDIDATES = ["expire_date", "expiry_date", "expiration_date", "valid_until", "expires"]

def normalize_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.strip().lower())


def auto_map_headers(headers: Iterable[str]) -> dict[str, str]:
    norm_map = {normalize_header(h): h for h in headers}

    def pick(cands: list[str]) -> str | None:
        # First try exact matches
        for c in cands:
            if c in norm_map:
                return norm_map[c]
        # Then try partial matches
        for n, original in norm_map.items():
            if any(c in n for c in cands):
                return original
        # Finally try case-insensitive partial matches
        for n, original in norm_map.items():
            if any(c.lower() in n.lower() for c in cands):
                return original
        return None

    product = pick([normalize_header(c) for c in P_CANDIDATES])
    vendor = pick([normalize_header(c) for c in V_CANDIDATES])
    sku = pick([normalize_header(c) for c in S_CANDIDATES])
    market = pick([normalize_header(c) for c in M_CANDIDATES])
    language = pick([normalize_header(c) for c in L_CANDIDATES])
    url = pick([normalize_header(c) for c in U_CANDIDATES])
    
    # New fields for updated requirements
    location_id = pick([normalize_header(c) for c in LOC_ID_CANDIDATES])
    product_id = pick([normalize_header(c) for c in PROD_ID_CANDIDATES])
    description = pick([normalize_header(c) for c in DESC_CANDIDATES])
    
    # Database-specific fields
    unique_id = pick([normalize_header(c) for c in UNIQUE_ID_CANDIDATES])
    msds_key = pick([normalize_header(c) for c in MSDS_KEY_CANDIDATES])
    revision_date = pick([normalize_header(c) for c in REV_DATE_CANDIDATES])
    expire_date = pick([normalize_header(c) for c in EXP_DATE_CANDIDATES])

    headers_list = list(headers)
    return {
        # Required fields (same for both input and database)
        "product": product or headers_list[0],
        "vendor": vendor or headers_list[0],
        "sku": sku or headers_list[0],
        "market": market or "Market",
        "language": language or "Language",
        
        # Optional fields - Input CSV
        "location_id": location_id,
        "product_id": product_id,
        "description": description,
        "url": url,
        
        # Optional fields - Database CSV
        "unique_id": unique_id,
        "msds_key": msds_key,
        "revision_date": revision_date,
        "expire_date": expire_date
    }

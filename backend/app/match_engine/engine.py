from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from .scoring import score_pair
from .thresholds import Thresholds
from ..services.mapping import auto_map_headers


def run_match(customer_csv: Path, db_csv: Path, customer_mapping: dict[str, str] | None, db_mapping: dict[str, str] | None, thresholds: Thresholds, limit: int | None = None) -> Iterator[tuple[int, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    from ..services.files import detect_csv_separator
    
    # Detect separators
    db_separator = detect_csv_separator(db_csv)
    customer_separator = detect_csv_separator(customer_csv)
    
    # Read CSV with error handling for inconsistent columns and encoding
    db_df = None
    used_encoding = None
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            db_df = pd.read_csv(db_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=db_separator, encoding=encoding)
            used_encoding = encoding
            print(f"DEBUG: Successfully read database CSV with encoding: {encoding}")
            break
        except (UnicodeDecodeError, UnicodeError) as e:
            print(f"DEBUG: Failed to read database CSV with encoding {encoding}: {e}")
            continue
        except Exception as e:
            print(f"DEBUG: Failed to read database CSV with encoding {encoding}: {e}")
            # Try with different parameters
            try:
                db_df = pd.read_csv(db_csv, dtype=str, keep_default_na=False, sep=db_separator, quotechar='"', on_bad_lines='skip', encoding=encoding)
                used_encoding = encoding
                print(f"DEBUG: Successfully read database CSV with encoding: {encoding} (with quotechar)")
                break
            except Exception as e2:
                print(f"DEBUG: Failed to read database CSV with encoding {encoding} (with quotechar): {e2}")
                continue
    
    if db_df is None:
        # Final fallback with error replacement
        try:
            db_df = pd.read_csv(db_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=db_separator, encoding='utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"Kunde inte läsa databasfilen: {str(e)}")
    
    # Read customer CSV with encoding handling
    customer_df = None
    customer_used_encoding = None
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            customer_df = pd.read_csv(customer_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=customer_separator, encoding=encoding)
            customer_used_encoding = encoding
            print(f"DEBUG: Successfully read customer CSV with encoding: {encoding}")
            break
        except (UnicodeDecodeError, UnicodeError) as e:
            print(f"DEBUG: Failed to read customer CSV with encoding {encoding}: {e}")
            continue
        except Exception as e:
            print(f"DEBUG: Failed to read customer CSV with encoding {encoding}: {e}")
            # Try with different parameters
            try:
                customer_df = pd.read_csv(customer_csv, dtype=str, keep_default_na=False, sep=customer_separator, quotechar='"', on_bad_lines='skip', encoding=encoding)
                customer_used_encoding = encoding
                print(f"DEBUG: Successfully read customer CSV with encoding: {encoding} (with quotechar)")
                break
            except Exception as e2:
                print(f"DEBUG: Failed to read customer CSV with encoding {encoding} (with quotechar): {e2}")
                continue
    
    if customer_df is None:
        # Final fallback with error replacement
        try:
            customer_df = pd.read_csv(customer_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=customer_separator, encoding='utf-8', errors='replace')
            customer_used_encoding = 'utf-8 (with errors=replace)'
            print(f"DEBUG: Successfully read customer CSV with fallback encoding: utf-8 (with errors=replace)")
        except Exception as e:
            raise Exception(f"Kunde inte läsa kundfilen: {str(e)}")
    
    # Debug: Show what columns were actually read
    print(f"DEBUG: Database CSV columns ({used_encoding}): {list(db_df.columns)}")
    print(f"DEBUG: Customer CSV columns ({customer_used_encoding}): {list(customer_df.columns)}")
    print(f"DEBUG: Database CSV shape: {db_df.shape}")
    print(f"DEBUG: Customer CSV shape: {customer_df.shape}")

    # Use database mapping if provided, otherwise auto-map
    if db_mapping is None:
        db_mapping = auto_map_headers(db_df.columns)
        print(f"DEBUG: Auto-mapped database headers: {db_mapping}")
        print(f"DEBUG: Database columns: {list(db_df.columns)}")
    
    # Use customer mapping if provided, otherwise auto-map
    if customer_mapping is None:
        customer_mapping = auto_map_headers(customer_df.columns)
        print(f"DEBUG: Auto-mapped customer headers: {customer_mapping}")
        print(f"DEBUG: Customer columns: {list(customer_df.columns)}")
    
    db_records = db_df.to_dict(orient="records")
    
    # Sort database records to prioritize matching market/language
    # This helps when database contains multiple markets
    def sort_key(record):
        market = record.get(db_mapping.get("market", "Market"), "").strip()
        language = record.get(db_mapping.get("language", "Language"), "").strip()
        # Prioritize records that match customer market/language
        return (market, language)
    
    # Get customer market/language for comparison
    if customer_df.shape[0] > 0:
        first_customer = customer_df.iloc[0].to_dict()
        customer_market = first_customer.get(customer_mapping.get("market", "Market"), "").strip()
        customer_language = first_customer.get(customer_mapping.get("language", "Language"), "").strip()
        
        # Sort to put matching market/language first
        db_records.sort(key=lambda r: (
            r.get(db_mapping.get("market", "Market"), "").strip() != customer_market,
            r.get(db_mapping.get("language", "Language"), "").strip() != customer_language
        ))
        
        print(f"DEBUG: Sorted database records to prioritize market='{customer_market}', language='{customer_language}'")
        print(f"DEBUG: First few database records after sorting:")
        for i, record in enumerate(db_records[:3]):
            market = record.get(db_mapping.get("market", "Market"), "").strip()
            language = record.get(db_mapping.get("language", "Language"), "").strip()
            product = record.get(db_mapping.get("product", "Product_name"), "").strip()
            print(f"  {i}: {product} (Market: {market}, Language: {language})")

    for idx, crow in enumerate(customer_df.to_dict(orient="records")):
        if limit is not None and idx >= limit:
            break
        best_meta = None
        best_db = None
        best_score = -1
        
        # Debug: Log customer row data
        print(f"Processing customer row {idx}: {crow}")
        print(f"DEBUG: Starting scoring loop for customer row {idx}")
        
        print(f"DEBUG: About to compare against {len(db_records)} database records")
        for db_idx, db_row in enumerate(db_records):
            try:
                meta = score_pair(crow, db_row, customer_mapping, db_mapping, thresholds)
                print(f"DEBUG: Scored DB product {db_idx}: score={meta['overall']}")
                
                if meta["overall"] > best_score:
                    best_score = meta["overall"]
                    best_meta, best_db = meta, db_row
                    # Use mapped field names for display
                    product_field = db_mapping.get("product", "Product_name")
                    vendor_field = db_mapping.get("vendor", "Supplier_name")
                    print(f"  New best match (score {best_score}): {db_row.get(product_field, 'N/A')} from {db_row.get(vendor_field, 'N/A')}")
                
                # Debug: Show first few database products being compared
                if db_idx < 3:
                    product_field = db_mapping.get("product", "Product_name")
                    vendor_field = db_mapping.get("vendor", "Supplier_name")
                    print(f"  DB product {db_idx}: {db_row.get(product_field, 'N/A')} from {db_row.get(vendor_field, 'N/A')} (score: {meta['overall']})")
            except Exception as e:
                print(f"DEBUG: Error scoring DB product {db_idx}: {e}")
                continue
        
        assert best_meta is not None and best_db is not None
        # Use mapped field names for display
        product_field = db_mapping.get("product", "Product_name")
        print(f"Final match for row {idx}: {best_db.get(product_field, 'N/A')} (score: {best_score})")
        yield idx, crow, best_db, best_meta

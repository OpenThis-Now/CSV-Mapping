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
            break
        except (UnicodeDecodeError, UnicodeError) as e:
            continue
        except Exception as e:
            # Try with different parameters
            try:
                db_df = pd.read_csv(db_csv, dtype=str, keep_default_na=False, sep=db_separator, quotechar='"', on_bad_lines='skip', encoding=encoding)
                used_encoding = encoding
                break
            except Exception as e2:
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
            break
        except (UnicodeDecodeError, UnicodeError) as e:
            continue
        except Exception as e:
            # Try with different parameters
            try:
                customer_df = pd.read_csv(customer_csv, dtype=str, keep_default_na=False, sep=customer_separator, quotechar='"', on_bad_lines='skip', encoding=encoding)
                customer_used_encoding = encoding
                break
            except Exception as e2:
                continue
    
    if customer_df is None:
        # Final fallback with error replacement
        try:
            customer_df = pd.read_csv(customer_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=customer_separator, encoding='utf-8', errors='replace')
            customer_used_encoding = 'utf-8 (with errors=replace)'
        except Exception as e:
            raise Exception(f"Kunde inte läsa kundfilen: {str(e)}")
    
    # Strip BOM (Byte Order Mark) from column names if present
    if used_encoding and 'utf-8' in used_encoding:
        db_df.columns = [col.lstrip('\ufeff') if col.startswith('\ufeff') else col for col in db_df.columns]
    
    if customer_used_encoding and 'utf-8' in customer_used_encoding:
        customer_df.columns = [col.lstrip('\ufeff') if col.startswith('\ufeff') else col for col in customer_df.columns]
    

    # Use database mapping if provided, otherwise auto-map
    if db_mapping is None:
        db_mapping = auto_map_headers(db_df.columns)
    
    # Use customer mapping if provided, otherwise auto-map
    if customer_mapping is None:
        customer_mapping = auto_map_headers(customer_df.columns)
    
    db_records = db_df.to_dict(orient="records")

    for idx, crow in enumerate(customer_df.to_dict(orient="records")):
        if limit is not None and idx >= limit:
            break
        best_meta = None
        best_db = None
        best_score = -1
        
        # Get current customer's market/language and file hash
        current_customer_market = crow.get(customer_mapping.get("market", "Market"), "").strip()
        current_customer_language = crow.get(customer_mapping.get("language", "Language"), "").strip()
        current_customer_file_hash = crow.get("file_hash", "").strip()
        
        # Sort database records with priority:
        # 1. File hash matches (highest priority)
        # 2. Revision date (newest first for same hash)
        # 3. Market/language matches
        def sort_key(r):
            db_file_hash = r.get("file_hash", "").strip()
            db_revision_date = r.get(db_mapping.get("revision_date", "Revision_date"), "").strip()
            db_market = r.get(db_mapping.get("market", "Market"), "").strip()
            db_language = r.get(db_mapping.get("language", "Language"), "").strip()
            
            # Priority 1: File hash match (0 = match, 1 = no match)
            hash_match = 0 if (current_customer_file_hash and db_file_hash and current_customer_file_hash == db_file_hash) else 1
            
            # Priority 2: Revision date (newest first) - convert to sortable format
            try:
                if db_revision_date:
                    # Parse date and use negative for descending order (newest first)
                    from datetime import datetime
                    parsed_date = datetime.strptime(db_revision_date, "%Y-%m-%d")
                    revision_priority = -parsed_date.timestamp()  # Negative for newest first
                else:
                    revision_priority = 0  # No date = lowest priority
            except:
                revision_priority = 0  # Invalid date = lowest priority
            
            # Priority 3: Market/language match
            market_match = db_market != current_customer_market
            language_match = db_language != current_customer_language
            
            return (hash_match, revision_priority, market_match, language_match)
        
        db_records_sorted = sorted(db_records, key=sort_key)
        
        # Debug: Log sorting information
        import logging
        log = logging.getLogger("app.match_engine.engine")
        log.info(f"Customer row {idx}: file_hash={current_customer_file_hash[:16] if current_customer_file_hash else 'None'}...")
        log.info(f"Database records sorted by priority:")
        for i, record in enumerate(db_records_sorted[:3]):  # Show first 3
            db_hash = record.get("file_hash", "").strip()
            db_product = record.get(db_mapping.get("product", "Product_name"), "")
            hash_match = current_customer_file_hash == db_hash and current_customer_file_hash != ""
            log.info(f"  {i+1}. Product: {db_product}, Hash: {db_hash[:16] if db_hash else 'None'}..., Hash match: {hash_match}")
        
        for db_idx, db_row in enumerate(db_records_sorted):
            try:
                meta = score_pair(crow, db_row, customer_mapping, db_mapping, thresholds)
                
                if meta["overall"] > best_score:
                    best_score = meta["overall"]
                    best_meta, best_db = meta, db_row
                    # Use mapped field names for display
                    product_field = db_mapping.get("product", "Product_name")
                    vendor_field = db_mapping.get("vendor", "Supplier_name")
                
            except Exception as e:
                continue
        
        assert best_meta is not None and best_db is not None
        # Use mapped field names for display
        product_field = db_mapping.get("product", "Product_name")
        yield idx, crow, best_db, best_meta

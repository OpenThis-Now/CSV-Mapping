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
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            db_df = pd.read_csv(db_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=db_separator, encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            # Try with different parameters
            try:
                db_df = pd.read_csv(db_csv, dtype=str, keep_default_na=False, sep=db_separator, quotechar='"', on_bad_lines='skip', encoding=encoding)
                break
            except Exception:
                continue
    
    if db_df is None:
        # Final fallback with error replacement
        try:
            db_df = pd.read_csv(db_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=db_separator, encoding='utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"Kunde inte läsa databasfilen: {str(e)}")
    
    # Read customer CSV with encoding handling
    customer_df = None
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            customer_df = pd.read_csv(customer_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=customer_separator, encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            # Try with different parameters
            try:
                customer_df = pd.read_csv(customer_csv, dtype=str, keep_default_na=False, sep=customer_separator, quotechar='"', on_bad_lines='skip', encoding=encoding)
                break
            except Exception:
                continue
    
    if customer_df is None:
        # Final fallback with error replacement
        try:
            customer_df = pd.read_csv(customer_csv, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=customer_separator, encoding='utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"Kunde inte läsa kundfilen: {str(e)}")

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
        
        # Debug: Log customer row data
        print(f"Processing customer row {idx}: {crow}")
        
        for db_idx, db_row in enumerate(db_records):
            meta = score_pair(crow, db_row, customer_mapping, db_mapping, thresholds)
            if meta["overall"] > best_score:
                best_score = meta["overall"]
                best_meta, best_db = meta, db_row
                print(f"  New best match (score {best_score}): {db_row.get('product', 'N/A')} from {db_row.get('vendor', 'N/A')}")
        
        assert best_meta is not None and best_db is not None
        print(f"Final match for row {idx}: {best_db.get('product', 'N/A')} (score: {best_score})")
        yield idx, crow, best_db, best_meta

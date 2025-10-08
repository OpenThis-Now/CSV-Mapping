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
    print(f"DEBUG: Detected separators - Database: '{db_separator}', Customer: '{customer_separator}'")
    
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
    
    # Strip BOM (Byte Order Mark) from column names if present
    import re
    def strip_bom_from_columns(columns):
        cleaned_columns = []
        for col in columns:
            # Remove ALL invisible characters at the start of column names
            # This includes BOM, zero-width characters, and other invisible Unicode
            cleaned_col = re.sub(r'^[\s\ufeff\ufeff\ufeff\u200b\u200c\u200d\ufeff\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000]+', '', col)
            cleaned_columns.append(cleaned_col)
        return cleaned_columns
    
    if used_encoding and 'utf-8' in used_encoding:
        original_columns = list(db_df.columns)
        print(f"DEBUG: Database columns before BOM stripping: {[repr(col) for col in original_columns]}")
        db_df.columns = strip_bom_from_columns(db_df.columns)
        cleaned_columns = list(db_df.columns)
        print(f"DEBUG: Database columns after BOM stripping: {[repr(col) for col in cleaned_columns]}")
        if original_columns != cleaned_columns:
            print(f"DEBUG: Stripped BOM from database columns")
            print(f"DEBUG: Original: {original_columns}")
            print(f"DEBUG: Cleaned: {cleaned_columns}")
        else:
            print(f"DEBUG: No BOM found in database columns")
    
    if customer_used_encoding and 'utf-8' in customer_used_encoding:
        original_columns = list(customer_df.columns)
        print(f"DEBUG: Customer columns before BOM stripping: {[repr(col) for col in original_columns]}")
        customer_df.columns = strip_bom_from_columns(customer_df.columns)
        cleaned_columns = list(customer_df.columns)
        print(f"DEBUG: Customer columns after BOM stripping: {[repr(col) for col in cleaned_columns]}")
        if original_columns != cleaned_columns:
            print(f"DEBUG: Stripped BOM from customer columns")
            print(f"DEBUG: Original: {original_columns}")
            print(f"DEBUG: Cleaned: {cleaned_columns}")
        else:
            print(f"DEBUG: No BOM found in customer columns")
    
    # Debug: Show what columns were actually read
    print(f"DEBUG: Database CSV columns ({used_encoding}): {list(db_df.columns)}")
    print(f"DEBUG: Customer CSV columns ({customer_used_encoding}): {list(customer_df.columns)}")
    print(f"DEBUG: Database CSV shape: {db_df.shape}")
    print(f"DEBUG: Customer CSV shape: {customer_df.shape}")
    
    # Debug: Compare column names character by character
    print(f"DEBUG: Database column names with character codes:")
    for i, col in enumerate(db_df.columns):
        char_codes = [ord(c) for c in col]
        print(f"  {i}: '{col}' -> {char_codes}")
    
    print(f"DEBUG: Customer column names with character codes:")
    for i, col in enumerate(customer_df.columns):
        char_codes = [ord(c) for c in col]
        print(f"  {i}: '{col}' -> {char_codes}")
    
    # Debug: Show first few rows of data to see what's actually read
    if len(db_df) > 0:
        first_db_row = db_df.iloc[0].to_dict()
        print(f"DEBUG: First database row: {first_db_row}")
        print(f"DEBUG: First database row repr: {[(k, repr(v)) for k, v in first_db_row.items()]}")
        
        # Show character codes for key fields
        for key in ['Market', 'Language', 'Product_name', 'Supplier_name']:
            if key in first_db_row:
                value = first_db_row[key]
                char_codes = [ord(c) for c in str(value)]
                print(f"DEBUG: DB {key}='{value}' -> {char_codes}")
    else:
        print(f"DEBUG: No database data")
    
    if len(customer_df) > 0:
        first_customer_row = customer_df.iloc[0].to_dict()
        print(f"DEBUG: First customer row: {first_customer_row}")
        print(f"DEBUG: First customer row repr: {[(k, repr(v)) for k, v in first_customer_row.items()]}")
        
        # Show character codes for key fields
        for key in ['Market', 'Language', 'Product_name', 'Supplier_name']:
            if key in first_customer_row:
                value = first_customer_row[key]
                char_codes = [ord(c) for c in str(value)]
                print(f"DEBUG: Customer {key}='{value}' -> {char_codes}")
    else:
        print(f"DEBUG: No customer data")
    
    # Compare key fields between database and customer
    if len(db_df) > 0 and len(customer_df) > 0:
        print(f"DEBUG: Comparing key fields between database and customer:")
        for key in ['Market', 'Language', 'Product_name', 'Supplier_name']:
            if key in first_db_row and key in first_customer_row:
                db_value = first_db_row[key]
                customer_value = first_customer_row[key]
                print(f"DEBUG: {key}: DB='{db_value}' vs Customer='{customer_value}'")
                print(f"DEBUG: {key}: DB repr='{repr(db_value)}' vs Customer repr='{repr(customer_value)}'")
                print(f"DEBUG: {key}: DB type='{type(db_value)}' vs Customer type='{type(customer_value)}'")
                if str(db_value) != str(customer_value):
                    print(f"DEBUG: {key}: VALUES DIFFER!")
                else:
                    print(f"DEBUG: {key}: VALUES MATCH")

    # Use database mapping if provided, otherwise auto-map
    if db_mapping is None:
        print(f"DEBUG: Database columns before mapping: {list(db_df.columns)}")
        print(f"DEBUG: Database column types: {[type(col).__name__ for col in db_df.columns]}")
        print(f"DEBUG: Database column repr: {[repr(col) for col in db_df.columns]}")
        db_mapping = auto_map_headers(db_df.columns)
        print(f"DEBUG: Auto-mapped database headers: {db_mapping}")
        print(f"DEBUG: Database columns: {list(db_df.columns)}")
        
        # Show what each key maps to
        for key, value in db_mapping.items():
            print(f"DEBUG: DB mapping '{key}' -> '{value}'")
    
    # Use customer mapping if provided, otherwise auto-map
    if customer_mapping is None:
        print(f"DEBUG: Customer columns before mapping: {list(customer_df.columns)}")
        print(f"DEBUG: Customer column types: {[type(col).__name__ for col in customer_df.columns]}")
        print(f"DEBUG: Customer column repr: {[repr(col) for col in customer_df.columns]}")
        customer_mapping = auto_map_headers(customer_df.columns)
        print(f"DEBUG: Auto-mapped customer headers: {customer_mapping}")
        print(f"DEBUG: Customer columns: {list(customer_df.columns)}")
        
        # Show what each key maps to
        for key, value in customer_mapping.items():
            print(f"DEBUG: Customer mapping '{key}' -> '{value}'")
    
    # Compare mappings between database and customer
    print(f"DEBUG: Comparing mappings between database and customer:")
    for key in ['product', 'vendor', 'sku', 'market', 'language']:
        db_mapped = db_mapping.get(key, 'NOT_FOUND')
        customer_mapped = customer_mapping.get(key, 'NOT_FOUND')
        print(f"DEBUG: {key}: DB='{db_mapped}' vs Customer='{customer_mapped}'")
        if db_mapped != customer_mapped:
            print(f"DEBUG: {key}: MAPPINGS DIFFER!")
        else:
            print(f"DEBUG: {key}: MAPPINGS MATCH")
    
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
        
        print(f"DEBUG: Customer market/language from first row: '{customer_market}' / '{customer_language}'")
        print(f"DEBUG: Database mapping for market: '{db_mapping.get('market', 'Market')}'")
        print(f"DEBUG: Database mapping for language: '{db_mapping.get('language', 'Language')}'")
        
        # Show some database records before sorting
        print(f"DEBUG: First few database records BEFORE sorting:")
        for i, record in enumerate(db_records[:5]):
            market = record.get(db_mapping.get("market", "Market"), "").strip()
            language = record.get(db_mapping.get("language", "Language"), "").strip()
            product = record.get(db_mapping.get("product", "Product_name"), "").strip()
            vendor = record.get(db_mapping.get("vendor", "Supplier_name"), "").strip()
            print(f"  {i}: {product} from {vendor} (Market: '{market}', Language: '{language}')")
        
        # Sort to put matching market/language first
        # True = mismatch (comes later), False = match (comes first)
        db_records.sort(key=lambda r: (
            r.get(db_mapping.get("market", "Market"), "").strip() != customer_market,
            r.get(db_mapping.get("language", "Language"), "").strip() != customer_language
        ))
        
        print(f"DEBUG: Sorted database records to prioritize market='{customer_market}', language='{customer_language}'")
        print(f"DEBUG: First few database records AFTER sorting:")
        for i, record in enumerate(db_records[:5]):
            market = record.get(db_mapping.get("market", "Market"), "").strip()
            language = record.get(db_mapping.get("language", "Language"), "").strip()
            product = record.get(db_mapping.get("product", "Product_name"), "").strip()
            vendor = record.get(db_mapping.get("vendor", "Supplier_name"), "").strip()
            print(f"  {i}: {product} from {vendor} (Market: '{market}', Language: '{language}')")
        
        # Count how many records match customer market/language
        matching_records = [r for r in db_records if 
                           r.get(db_mapping.get("market", "Market"), "").strip() == customer_market and
                           r.get(db_mapping.get("language", "Language"), "").strip() == customer_language]
        print(f"DEBUG: Found {len(matching_records)} records matching market='{customer_market}', language='{customer_language}' out of {len(db_records)} total")
        
        # Show some examples of matching records
        if matching_records:
            print(f"DEBUG: Examples of matching records:")
            for i, record in enumerate(matching_records[:3]):
                product = record.get(db_mapping.get("product", "Product_name"), "").strip()
                vendor = record.get(db_mapping.get("vendor", "Supplier_name"), "").strip()
                print(f"  {i}: {product} from {vendor}")
        else:
            print(f"DEBUG: No matching records found - this explains the low scores!")
            
            # Show what markets/languages are actually available in the database
            available_markets = set()
            available_languages = set()
            for record in db_records:
                market = record.get(db_mapping.get("market", "Market"), "").strip()
                language = record.get(db_mapping.get("language", "Language"), "").strip()
                if market:
                    available_markets.add(market)
                if language:
                    available_languages.add(language)
            
            print(f"DEBUG: Available markets in database: {sorted(available_markets)}")
            print(f"DEBUG: Available languages in database: {sorted(available_languages)}")
            print(f"DEBUG: Customer is looking for market='{customer_market}', language='{customer_language}'")

    for idx, crow in enumerate(customer_df.to_dict(orient="records")):
        if limit is not None and idx >= limit:
            break
        best_meta = None
        best_db = None
        best_score = -1
        
        # Debug: Log customer row data
        print(f"Processing customer row {idx}: {crow}")
        print(f"DEBUG: Starting scoring loop for customer row {idx}")
        
        # Get market/language for this specific customer row
        current_customer_market = crow.get(customer_mapping.get("market", "Market"), "").strip()
        current_customer_language = crow.get(customer_mapping.get("language", "Language"), "").strip()
        print(f"DEBUG: Current customer row market/language: '{current_customer_market}' / '{current_customer_language}'")
        
        # Show the actual values being used for comparison
        market_key = customer_mapping.get("market", "Market")
        language_key = customer_mapping.get("language", "Language")
        print(f"DEBUG: Using keys: market='{market_key}', language='{language_key}'")
        print(f"DEBUG: Raw values: market='{crow.get(market_key, 'NOT_FOUND')}', language='{crow.get(language_key, 'NOT_FOUND')}'")
        print(f"DEBUG: Raw values repr: market='{repr(crow.get(market_key, 'NOT_FOUND'))}', language='{repr(crow.get(language_key, 'NOT_FOUND'))}'")
        
        # Re-sort database records for this specific customer row to prioritize matching market/language
        # This ensures we always prioritize the right market/language for each customer row
        db_records_sorted = sorted(db_records, key=lambda r: (
            r.get(db_mapping.get("market", "Market"), "").strip() != current_customer_market,
            r.get(db_mapping.get("language", "Language"), "").strip() != current_customer_language
        ))
        
        # Count matching records for this customer row
        matching_records_for_row = [r for r in db_records_sorted if 
                                   r.get(db_mapping.get("market", "Market"), "").strip() == current_customer_market and
                                   r.get(db_mapping.get("language", "Language"), "").strip() == current_customer_language]
        print(f"DEBUG: For customer row {idx}, found {len(matching_records_for_row)} matching market/language records out of {len(db_records_sorted)} total")
        
        # Show detailed comparison for first few records
        print(f"DEBUG: Detailed comparison for first few records:")
        for i, record in enumerate(db_records_sorted[:3]):
            db_market = record.get(db_mapping.get("market", "Market"), "").strip()
            db_language = record.get(db_mapping.get("language", "Language"), "").strip()
            market_match = db_market == current_customer_market
            language_match = db_language == current_customer_language
            print(f"  Record {i}: DB market='{db_market}' vs Customer market='{current_customer_market}' -> {market_match}")
            print(f"  Record {i}: DB language='{db_language}' vs Customer language='{current_customer_language}' -> {language_match}")
            print(f"  Record {i}: Overall match: {market_match and language_match}")
        
        # Show first few database records that will be processed for this customer row
        print(f"DEBUG: First few database records for customer row {idx}:")
        for i, record in enumerate(db_records_sorted[:3]):
            market = record.get(db_mapping.get("market", "Market"), "").strip()
            language = record.get(db_mapping.get("language", "Language"), "").strip()
            product = record.get(db_mapping.get("product", "Product_name"), "").strip()
            vendor = record.get(db_mapping.get("vendor", "Supplier_name"), "").strip()
            print(f"  {i}: {product} from {vendor} (Market: '{market}', Language: '{language}')")
            
            # Show raw values and their repr
            market_key = db_mapping.get("market", "Market")
            language_key = db_mapping.get("language", "Language")
            raw_market = record.get(market_key, 'NOT_FOUND')
            raw_language = record.get(language_key, 'NOT_FOUND')
            print(f"    Raw values: market='{raw_market}', language='{raw_language}'")
            print(f"    Raw values repr: market='{repr(raw_market)}', language='{repr(raw_language)}'")
        
        print(f"DEBUG: About to compare against {len(db_records_sorted)} database records")
        for db_idx, db_row in enumerate(db_records_sorted):
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
                    print(f"  Best match details: {meta}")
                
                # Debug: Show first few database products being compared
                if db_idx < 3:
                    product_field = db_mapping.get("product", "Product_name")
                    vendor_field = db_mapping.get("vendor", "Supplier_name")
                    print(f"  DB product {db_idx}: {db_row.get(product_field, 'N/A')} from {db_row.get(vendor_field, 'N/A')} (score: {meta['overall']})")
                    print(f"  DB product {db_idx} details: {meta}")
            except Exception as e:
                print(f"DEBUG: Error scoring DB product {db_idx}: {e}")
                continue
        
        assert best_meta is not None and best_db is not None
        # Use mapped field names for display
        product_field = db_mapping.get("product", "Product_name")
        print(f"Final match for row {idx}: {best_db.get(product_field, 'N/A')} (score: {best_score})")
        print(f"Final match details: {best_meta}")
        print(f"Final match decision: {best_meta.get('decision', 'unknown')}")
        print(f"Final match reason: {best_meta.get('reason', 'unknown')}")
        yield idx, crow, best_db, best_meta

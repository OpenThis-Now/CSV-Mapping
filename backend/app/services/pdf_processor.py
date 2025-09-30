from __future__ import annotations

import fitz  # PyMuPDF
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

from ..openai_client import suggest_with_openai


def extract_pdf_text(pdf_path: Path, max_pages: int = 3) -> Optional[str]:
    """Extrahera text från första 3 sidorna av PDF"""
    # Try PyMuPDF first
    try:
        import fitz
        print(f"Using PyMuPDF for {pdf_path}")
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            print(f"PDF {pdf_path} is empty")
            return None
            
        text = ""
        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            page_text = page.get_text()
            if page_text.strip():  # Bara lägg till icke-tomma sidor
                text += page_text + "\n"
        
        doc.close()
        result = text.strip() if text.strip() else None
        if result:
            print(f"PyMuPDF: Successfully extracted {len(result)} characters from PDF {pdf_path}")
            return result
        else:
            print(f"PyMuPDF: No text found in PDF {pdf_path}")
            
    except ImportError as e:
        print(f"PyMuPDF not available: {e}")
    except Exception as e:
        print(f"PyMuPDF error reading PDF {pdf_path}: {e}")
    
    # Fallback to pdfplumber
    try:
        import pdfplumber
        print(f"Using pdfplumber for {pdf_path}")
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page_num in range(min(max_pages, len(pdf.pages))):
                page = pdf.pages[page_num]
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text += page_text + "\n"
        
        result = text.strip() if text.strip() else None
        if result:
            print(f"pdfplumber: Successfully extracted {len(result)} characters from PDF {pdf_path}")
            return result
        else:
            print(f"pdfplumber: No text found in PDF {pdf_path}")
            
    except ImportError as e:
        print(f"pdfplumber not available: {e}")
    except Exception as e:
        print(f"pdfplumber error reading PDF {pdf_path}: {e}")
    
    print(f"All PDF extraction methods failed for {pdf_path}")
    return None


def build_pdf_extraction_prompt(pdf_text: str, filename: str) -> str:
    """Bygg AI-prompt för PDF-extraktion"""
    # Replace Swedish characters with ASCII equivalents
    pdf_text_clean = pdf_text.replace('ä', 'a').replace('ö', 'o').replace('å', 'a')
    
    prompt = f"""
Extract product information from this document. Return ONLY a valid JSON object with these fields:

{{
  "product_name": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "text fragment"}}}},
  "article_number": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "text fragment"}}}},
  "company_name": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "text fragment"}}}},
  "authored_market": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "text fragment"}}}},
  "language": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "text fragment"}}}},
  "filename": "{filename}",
  "extraction_status": "success"
}}

Look for:
- Product name: "Product name", "Trade name", "Commercial name", etc.
- Article number: "Article No", "Part No", "Item No", "Product code", etc.
- Company: "Manufacturer", "Supplier", "Company", etc.
- Market: "EU", "US", "Canada", "CLP", "REACH", "OSHA", "WHMIS", etc.
- Language: Detect from content ("Hazard statements"=English, "Gefahrhinweise"=German, etc.)

If you find any of these fields, set extraction_status to "success". If none found, set to "partial".

Document text:
{pdf_text_clean[:3000] if pdf_text_clean else "PDF could not be read"}
"""
    
    # Clean the entire prompt of non-ASCII characters
    return prompt.replace('ä', 'a').replace('ö', 'o').replace('å', 'a').replace('–', '-').replace('—', '-').replace('…', '...').replace('•', '*').replace('≤', '<=').replace('≥', '>=').replace('é', 'e').replace('ó', 'o').replace('í', 'i')


def extract_product_info_with_ai(text: str, filename: str) -> Dict[str, Any]:
    """Använd AI för att extrahera produktinformation från PDF-text"""
    if not text or len(text.strip()) < 50:
        print(f"Text too short or empty for {filename}: {len(text) if text else 0} characters")
        return create_fallback_entry(filename)
    
    try:
        # Check if we have a valid OpenAI API key
        from ..config import settings
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "din_api_nyckel_här":
            print(f"No valid OpenAI API key found, using fallback extraction for {filename}")
            # Fallback to simple text parsing when no valid API key
            return simple_text_extraction(text, filename)
        
        print(f"Using AI extraction for {filename} with {len(text)} characters")
        prompt = build_pdf_extraction_prompt(text, filename)
        # Ensure prompt is properly encoded
        prompt = prompt.encode('utf-8').decode('utf-8')
        print(f"Calling OpenAI API for {filename}...")
        result = suggest_with_openai(prompt, max_items=1)
        
        print(f"AI API response for {filename}: {result}")
        
        if result and len(result) > 0:
            print(f"AI extraction successful for {filename}")
            return result[0]
        else:
            print(f"AI extraction returned empty result for {filename}, using fallback extraction")
            # Use simple text extraction as fallback instead of creating empty entry
            return simple_text_extraction(text, filename)
            
    except Exception as e:
        print(f"AI extraction failed for {filename}: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to simple text parsing
        return simple_text_extraction(text, filename)


def simple_text_extraction(text: str, filename: str) -> Dict[str, Any]:
    """Enkel text-extraktion som fallback när AI inte är tillgänglig"""
    import re
    
    print(f"Using simple text extraction for {filename}")
    
    # Simple regex patterns for common SDS fields
    product_name = None
    article_number = None
    company_name = None
    authored_market = None
    language = None
    
    # Look for product name patterns (more comprehensive)
    product_patterns = [
        r'(?:Product name|Trade name|Commercial name|Product identifier|Handelsname)[:\s]+([^\n\r]+)',
        r'(?:Produktnamn|Produktbezeichnung|Nom du produit|Nombre del producto)[:\s]+([^\n\r]+)',
        r'^([A-Z][A-Z\s\-0-9]+(?:[A-Z][A-Z\s\-0-9]+)*)',  # All caps product names at start of line
    ]
    
    for pattern in product_patterns:
        product_match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if product_match:
            product_name = product_match.group(1).strip()
            break
    
    # Look for article number patterns (more comprehensive)
    article_patterns = [
        r'(?:Article number|Article No|Artikelnummer|Artikel-Nr|Art.-Nr|Part No|Item No|Product code)[:\s]+([^\n\r\s]+)',
        r'(?:Kat\.\s*nr|Varenummer|Tuotenumero|Référence|Código de artículo)[:\s]+([^\n\r\s]+)',
        r'\b([A-Z0-9]{3,}-[A-Z0-9]{3,})\b',  # Pattern like ABC-123
        r'\b([0-9]{4,})\b',  # Long numeric codes
    ]
    
    for pattern in article_patterns:
        article_match = re.search(pattern, text, re.IGNORECASE)
        if article_match:
            article_number = article_match.group(1).strip()
            break
    
    # Look for manufacturer/supplier patterns (more comprehensive)
    company_patterns = [
        r'(?:Manufacturer|Supplier|Company|Responsible person|Importeur|Importer|Distributör|Distributor)[:\s]+([^\n\r]+)',
        r'(?:Hersteller|Lieferant|Unternehmen|Verantwortliche Person)[:\s]+([^\n\r]+)',
        r'(?:Fabricant|Fournisseur|Société|Personne responsable)[:\s]+([^\n\r]+)',
    ]
    
    for pattern in company_patterns:
        company_match = re.search(pattern, text, re.IGNORECASE)
        if company_match:
            company_name = company_match.group(1).strip()
            break
    
    # Look for market patterns (more comprehensive)
    market_patterns = [
        r'(?:Market|Region|Regulatory market)[:\s]+([^\n\r]+)',
        r'(?:CLP|REACH|OSHA|WHMIS|GHS)[\s\w]*',  # Regulatory frameworks
        r'(?:EU|USA|US|Canada|UK|Australia)[\s\w]*',  # Regions
    ]
    
    for pattern in market_patterns:
        market_match = re.search(pattern, text, re.IGNORECASE)
        if market_match:
            authored_market = market_match.group(0).strip()
            break
    
    # Detect language from content
    if re.search(r'(?:Faraoangivelser|Gefahrhinweise|H-Sätze)', text, re.IGNORECASE):
        language = "German"
    elif re.search(r'(?:Déclarations de danger|Phrases de risque)', text, re.IGNORECASE):
        language = "French"
    elif re.search(r'(?:Hazard statements|Danger statements)', text, re.IGNORECASE):
        language = "English"
    elif re.search(r'(?:Faraangivelser|Riskfraser)', text, re.IGNORECASE):
        language = "Swedish"
    
    # If no specific language detected, default to English
    if not language:
        language = "English"
    
    # Determine extraction status
    extracted_fields = [product_name, article_number, company_name]
    status = "success" if any(extracted_fields) else "partial"
    
    print(f"Simple extraction results for {filename}: product={product_name}, article={article_number}, company={company_name}, status={status}")
    
    return {
        "product_name": {"value": product_name, "confidence": 0.8 if product_name else 0.0, "evidence": {"snippet": f"Found in text: {product_name or 'not found'}"}},
        "article_number": {"value": article_number, "confidence": 0.8 if article_number else 0.0, "evidence": {"snippet": f"Found in text: {article_number or 'not found'}"}},
        "company_name": {"value": company_name, "confidence": 0.8 if company_name else 0.0, "evidence": {"snippet": f"Found in text: {company_name or 'not found'}"}},
        "authored_market": {"value": authored_market, "confidence": 0.8 if authored_market else 0.0, "evidence": {"snippet": f"Found in text: {authored_market or 'not found'}"}},
        "language": {"value": language, "confidence": 0.8 if language else 0.0, "evidence": {"snippet": f"Detected from content: {language}"}},
        "filename": filename,
        "extraction_status": status
    }


def create_fallback_entry(filename: str) -> Dict[str, Any]:
    """Skapa fallback-entry för oläsbara PDF:er"""
    return {
        "product_name": {"value": None, "confidence": 0.0, "evidence": {"snippet": "PDF unreadable"}},
        "article_number": {"value": None, "confidence": 0.0, "evidence": {"snippet": "PDF unreadable"}},
        "company_name": {"value": None, "confidence": 0.0, "evidence": {"snippet": "PDF unreadable"}},
        "authored_market": {"value": None, "confidence": 0.0, "evidence": {"snippet": "PDF unreadable"}},
        "language": {"value": None, "confidence": 0.0, "evidence": {"snippet": "PDF unreadable"}},
        "filename": filename,
        "extraction_status": "failed"
    }


def create_csv_from_pdf_data(pdf_data: List[Dict[str, Any]], output_path: Path) -> Path:
    """Skapa CSV från extraherade PDF-data"""
    # Använd kolumnnamn som matchar auto_map_headers förväntningar
    fieldnames = [
        "product", "vendor", "sku", "market", "language", "filename", "extraction_status"
    ]
    
    print(f"Creating CSV with {len(pdf_data)} items at {output_path}")
    
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for i, item in enumerate(pdf_data):
            # Extrahera värden från nested structure och mappa till rätt kolumnnamn
            row = {
                "product": item.get("product_name", {}).get("value", ""),
                "vendor": item.get("company_name", {}).get("value", ""),
                "sku": item.get("article_number", {}).get("value", ""),
                "market": item.get("authored_market", {}).get("value", ""),
                "language": item.get("language", {}).get("value", ""),
                "filename": item.get("filename", ""),
                "extraction_status": item.get("extraction_status", "unknown")
            }
            
            # Log each row for debugging
            print(f"Row {i+1}: {row}")
            writer.writerow(row)
    
    print(f"CSV created successfully with {len(pdf_data)} rows")
    return output_path


def process_pdf_files(pdf_files: List[Path]) -> List[Dict[str, Any]]:
    """Bearbeta flera PDF-filer och returnera extraherade data"""
    all_products = []
    
    print(f"Starting to process {len(pdf_files)} PDF files...")
    
    for pdf_path in pdf_files:
        filename = pdf_path.name
        print(f"Processing PDF: {filename}")
        
        try:
            # Extrahera text från PDF
            text = extract_pdf_text(pdf_path)
            
            if not text:
                print(f"No text extracted from {filename} - creating fallback entry")
                product_info = create_fallback_entry(filename)
            else:
                print(f"Extracted {len(text)} characters from {filename}")
                # Använd AI för att extrahera produktinformation
                product_info = extract_product_info_with_ai(text, filename)
            
            all_products.append(product_info)
            print(f"Processed {filename}: status = {product_info.get('extraction_status', 'unknown')}")
            
            # Log extracted data for debugging
            if product_info.get('extraction_status') == 'success':
                print(f"Successfully extracted: product={product_info.get('product_name', {}).get('value')}, vendor={product_info.get('company_name', {}).get('value')}, sku={product_info.get('article_number', {}).get('value')}")
            else:
                print(f"Extraction failed or partial for {filename}")
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            # Create fallback entry for this file
            fallback_info = create_fallback_entry(filename)
            all_products.append(fallback_info)
    
    print(f"Completed processing {len(pdf_files)} PDF files, got {len(all_products)} results")
    return all_products

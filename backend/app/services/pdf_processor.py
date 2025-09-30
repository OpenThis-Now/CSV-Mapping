from __future__ import annotations

import fitz  # PyMuPDF
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

from ..openai_client import suggest_with_openai


def extract_pdf_text(pdf_path: Path, max_pages: int = 3) -> Optional[str]:
    """Extrahera text från första 3 sidorna av PDF"""
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            return None
            
        text = ""
        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            page_text = page.get_text()
            if page_text.strip():  # Bara lägg till icke-tomma sidor
                text += page_text + "\n"
        
        doc.close()
        return text.strip() if text.strip() else None
        
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
        return None


def build_pdf_extraction_prompt(pdf_text: str, filename: str) -> str:
    """Bygg AI-prompt för PDF-extraktion"""
    # Replace Swedish characters with ASCII equivalents
    pdf_text_clean = pdf_text.replace('ä', 'a').replace('ö', 'o').replace('å', 'a')
    
    prompt = f"""
You are a meticulous SDS (Safety Data Sheet) parser.

TASK
Read ONLY the FIRST THREE (3) PAGES of the provided SDS and extract:
1) product_name
2) article_number  
3) company_name
4) authored_market (which regulatory market/region the SDS is authored for)
5) language (the primary language the SDS text is written in)

FILENAME: {filename}

SCOPE & RULES
- Use only content from pages 1–3. Ignore all other pages, metadata, or prior knowledge.
- Prefer Section 1 ("Identification") and headers/footers on p.1 for product & supplier fields.
- If a field is not present in pages 1–3, set its "value" to null and include a brief reason in the evidence snippet (e.g., "not on p1–3").
- Do NOT guess or hallucinate. Lower confidence if inference is needed.
- Evidence.snippet should be a SHORT, verbatim fragment (≤200 characters) containing the cue that justified the value.

DEFINITIONS & SIGNALS
A) product_name
   - Synonyms/labels: "Product name", "Trade name", "Commercial name", "Product identifier", "Productnaam", "Nom du produit", "Nombre del producto", "Handelsname", "Produktnamn", "Nazwa produktu".
   - Exclude generic class names (e.g., "Epoxy resin, mixture" unless that is the stated trade name). Prefer bold title on the front page or Section 1.1.

B) article_number
   - Synonyms: "Article No.", "Artikelnummer/Artikel-Nr./Art.-Nr.", "Item No.", "Part No.", "Product code", "Kat. nr.", "Varenummer", "Tuotenumero", "Référence", "Código de artículo".
   - Usually alphanumeric (e.g., 12345, AB-1234, 100-200-300).
   - DO NOT return CAS numbers, REACH registration numbers, UFI codes, or batch/lot numbers as the article number unless the text explicitly labels them as such.

C) company_name
   - Synonyms: "Manufacturer", "Supplier", "Responsible person", "Importeur/Importer", "Distributör/Distributor".
   - Prefer the legal entity name listed in Section 1.3 (EU) or Section 1 "Supplier/Manufacturer" block (US/CA).

D) authored_market (regulatory market the SDS was authored for)
   - Determine using explicit regulatory references first. Examples (non-exhaustive):
     • EU/EEA (CLP/REACH): "Regulation (EC) No 1272/2008 (CLP)", "Regulation (EC) No 1907/2006 (REACH)", "UFI", "EUH0xx", "GB-CLP" (UK).
     • USA (OSHA HazCom 2012): "29 CFR 1910.1200", "Hazard(s) Identification" wording, NFPA/HMIS tables.
     • Canada (WHMIS): "WHMIS", "HPR", "SOR/2015-17", bilingual EN/FR with Canadian supplier.
     • Australia/NZ: "GHS Revision x (AU)", "SUSMP/Poisons Standard", "HSNO".
     • Other regions (JP/KR/CN/BR/…): cite their GHS/industrial safety laws if mentioned.
   - If no explicit citation, use weaker signals (lower confidence): address/country of supplier, emergency phone country code, label element styles (e.g., EUH statements).
   - Output a concise region string such as: "EU (CLP/REACH)", "US (OSHA HazCom 2012)", "Canada (WHMIS)", "UK (GB-CLP)", "Australia (GHS AU)", etc.

E) language
   - Detect by the dominant language of pages 1–3 (not the company location).
   - Example cues: "Faraoangivelser" (SV), "Gefahrhinweise/H-Sätze" (DE), "Hazard statements" (EN), "Déclarations de danger" (FR), etc.
   - If clearly bilingual, choose the primary/most complete language on p.1–3 and mention "bilingual" in evidence.

PROCESS
1. Scan pages 1-3 for the required information
2. If PDF is unreadable, corrupted, or contains no text, return a single entry with all fields null
3. Extract information using the definitions above
4. Provide evidence snippets for each field
5. Assign confidence scores (0.0-1.0) based on clarity of extraction

QUALITY BAR
- Confidence ≥0.8: Clear, unambiguous extraction with strong evidence
- Confidence 0.5-0.7: Reasonable inference with some uncertainty
- Confidence <0.5: Weak evidence or significant uncertainty
- Confidence 0.0: Field not found or PDF unreadable

EDGE CASES TO HANDLE
- Multilingual SDS (e.g., EN/FR for Canada; EN/SE for Nordics).
- Front pages that list multiple trade names or a product family: choose the exact trade name for THIS SDS if clearly indicated; otherwise return null with a short explanation.
- If the SDS states "for industrial use only" etc., that is NOT the authored market—look for regulatory frameworks/region.
- If PDF is corrupted, password-protected, or contains only images without OCR text: return single entry with all null values and confidence 0.0

OUTPUT FORMAT
Return a JSON array with exactly ONE object containing:
{{
  "product_name": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "short text fragment"}}}},
  "article_number": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "short text fragment"}}}},
  "company_name": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "short text fragment"}}}},
  "authored_market": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "short text fragment"}}}},
  "language": {{"value": "string or null", "confidence": 0.0-1.0, "evidence": {{"snippet": "short text fragment"}}}},
  "filename": "{filename}",
  "extraction_status": "success|failed|partial"
}}

PDF TEXT TO ANALYZE:
{pdf_text_clean[:4000] if pdf_text_clean else "PDF could not be read or contains no text"}
"""
    
    # Clean the entire prompt of non-ASCII characters
    return prompt.replace('ä', 'a').replace('ö', 'o').replace('å', 'a').replace('–', '-').replace('—', '-').replace('…', '...').replace('•', '*').replace('≤', '<=').replace('≥', '>=').replace('é', 'e').replace('ó', 'o').replace('í', 'i')


def extract_product_info_with_ai(text: str, filename: str) -> Dict[str, Any]:
    """Använd AI för att extrahera produktinformation från PDF-text"""
    if not text or len(text.strip()) < 50:
        return create_fallback_entry(filename)
    
    try:
        # Check if we have a valid OpenAI API key
        from ..config import settings
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "din_api_nyckel_här":
            # Fallback to simple text parsing when no valid API key
            return simple_text_extraction(text, filename)
        
        prompt = build_pdf_extraction_prompt(text, filename)
        # Ensure prompt is properly encoded
        prompt = prompt.encode('utf-8').decode('utf-8')
        result = suggest_with_openai(prompt, max_items=1)
        
        if result and len(result) > 0:
            return result[0]
        else:
            return create_fallback_entry(filename)
            
    except Exception as e:
        print(f"AI extraction failed for {filename}: {e}")
        # Fallback to simple text parsing
        return simple_text_extraction(text, filename)


def simple_text_extraction(text: str, filename: str) -> Dict[str, Any]:
    """Enkel text-extraktion som fallback när AI inte är tillgänglig"""
    import re
    
    # Simple regex patterns for common SDS fields
    product_name = None
    article_number = None
    company_name = None
    authored_market = None
    language = None
    
    # Look for product name patterns
    product_match = re.search(r'(?:Product name|Trade name|Commercial name)[:\s]+([^\n\r]+)', text, re.IGNORECASE)
    if product_match:
        product_name = product_match.group(1).strip()
    
    # Look for article number patterns
    article_match = re.search(r'(?:Article number|Article No|Part No|Item No)[:\s]+([^\n\r]+)', text, re.IGNORECASE)
    if article_match:
        article_number = article_match.group(1).strip()
    
    # Look for manufacturer/supplier patterns
    company_match = re.search(r'(?:Manufacturer|Supplier|Company)[:\s]+([^\n\r]+)', text, re.IGNORECASE)
    if company_match:
        company_name = company_match.group(1).strip()
    
    # Look for market patterns
    market_match = re.search(r'(?:Market|Region)[:\s]+([^\n\r]+)', text, re.IGNORECASE)
    if market_match:
        authored_market = market_match.group(1).strip()
    
    # Look for language patterns
    language_match = re.search(r'(?:Language)[:\s]+([^\n\r]+)', text, re.IGNORECASE)
    if language_match:
        language = language_match.group(1).strip()
    
    return {
        "product_name": {"value": product_name, "confidence": 0.8 if product_name else 0.0, "evidence": {"snippet": f"Found in text: {product_name or 'not found'}"}},
        "article_number": {"value": article_number, "confidence": 0.8 if article_number else 0.0, "evidence": {"snippet": f"Found in text: {article_number or 'not found'}"}},
        "company_name": {"value": company_name, "confidence": 0.8 if company_name else 0.0, "evidence": {"snippet": f"Found in text: {company_name or 'not found'}"}},
        "authored_market": {"value": authored_market, "confidence": 0.8 if authored_market else 0.0, "evidence": {"snippet": f"Found in text: {authored_market or 'not found'}"}},
        "language": {"value": language, "confidence": 0.8 if language else 0.0, "evidence": {"snippet": f"Found in text: {language or 'not found'}"}},
        "filename": filename,
        "extraction_status": "success" if any([product_name, article_number, company_name]) else "partial"
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
    # Definiera kolumner baserat på din befintliga mapping
    fieldnames = [
        "product_name", "article_number", "company_name", 
        "authored_market", "language", "filename", "extraction_status"
    ]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in pdf_data:
            # Extrahera värden från nested structure
            row = {
                "product_name": item.get("product_name", {}).get("value", ""),
                "article_number": item.get("article_number", {}).get("value", ""),
                "company_name": item.get("company_name", {}).get("value", ""),
                "authored_market": item.get("authored_market", {}).get("value", ""),
                "language": item.get("language", {}).get("value", ""),
                "filename": item.get("filename", ""),
                "extraction_status": item.get("extraction_status", "unknown")
            }
            writer.writerow(row)
    
    return output_path


def process_pdf_files(pdf_files: List[Path]) -> List[Dict[str, Any]]:
    """Bearbeta flera PDF-filer och returnera extraherade data"""
    all_products = []
    
    for pdf_path in pdf_files:
        filename = pdf_path.name
        print(f"Processing PDF: {filename}")
        
        # Extrahera text från PDF
        text = extract_pdf_text(pdf_path)
        
        # Använd AI för att extrahera produktinformation
        product_info = extract_product_info_with_ai(text, filename)
        all_products.append(product_info)
    
    return all_products

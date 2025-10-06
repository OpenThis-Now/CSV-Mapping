from __future__ import annotations

import fitz  # PyMuPDF
import csv
import requests
import tempfile
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
- IMPORTANT: Use filename patterns to help determine market (e.g., "sweden_ab" = Swedish market, "germany" = German market).

DEFINITIONS & SIGNALS
A) product_name
   - Synonyms/labels: "Product name", "Trade name", "Commercial name", "Product identifier", "Productnaam", "Nom du produit", "Nombre del producto", "Handelsname", "Produktnamn", "Nazwa produktu".
   - Exclude generic class names (e.g., "Epoxy resin, mixture" unless that is the stated trade name). Prefer bold title on the front page or Section 1.1.

B) article_number
   - Synonyms: "Article No.", "Artikelnummer/Artikel-Nr./Art.-Nr.", "Item No.", "Part No.", "Product code", "Kat. nr.", "Varenummer", "Tuotenumero", "Référence", "Código de artículo".
   - Usually alphanumeric (e.g., 12345, AB-1234, 100-200-300).
   - DO NOT return CAS numbers, REACH registration numbers, UFI codes, or batch/lot numbers as the article number unless the text explicitly labels them as such.

C) company_name
   - Synonyms: "Manufacturer", "Supplier", "Responsible person", "Importeur/Importer", "Distributör/Distributor", "Company", "Företag", "Unternehmen".
   - Prefer the legal entity name listed in Section 1.3 (EU) or Section 1 "Supplier/Manufacturer" block (US/CA).
   - Look for company names in headers, footers, and Section 1 "Details of the supplier" blocks.
   - Common patterns: "Company Name Ltd", "Company Name GmbH", "Company Name AB", "Company Name SE & Co. KG".
   - If multiple company names appear, prefer the main manufacturer/supplier (usually the first or most prominent one).

D) authored_market (regulatory market the SDS was authored for)
   - CRITICAL: Focus on regulatory framework and market indicators, NOT supplier location. A German supplier can write SDS for US market.
   - PRIORITY ORDER for market detection:
     1. Regulatory framework references (CLP, REACH, OSHA, WHMIS, WHS, etc.)
     2. Language of the document (Swedish = Sweden, German = Germany, etc.)
     3. Emergency phone numbers and addresses (country codes, postal codes)
     4. Company subsidiary location (e.g., "Merck Life Science AB" = Swedish subsidiary)
     5. URL patterns (e.g., "sweden_ab" in filename = Swedish market)
   - CRITICAL: Focus on REGULATORY FRAMEWORK, not supplier location. A German company can make SDS for Australian market.
   - Determine using explicit regulatory references and market indicators:
     • EU/EEA countries: Look for regulatory framework + market language/emergency numbers:
       - Sweden: "Regulation (EC) No 1272/2008 (CLP)" + Swedish language + Swedish emergency numbers + "SE-" postal codes + "sweden_ab" in URL
       - Germany: "Regulation (EC) No 1272/2008 (CLP)" + German language sections + German emergency numbers + "DE-" postal codes
       - France: "Regulation (EC) No 1272/2008 (CLP)" + French language sections + French emergency numbers + "FR-" postal codes
       - Netherlands: "Regulation (EC) No 1272/2008 (CLP)" + Dutch language sections + Dutch emergency numbers + "NL-" postal codes
       - UK: "GB-CLP" or "Regulation (EC) No 1272/2008 (CLP)" + English language + UK emergency numbers + "GB-" postal codes
     • USA (OSHA HazCom 2012): "29 CFR 1910.1200", "Hazard(s) Identification" wording, NFPA/HMIS tables, US emergency numbers.
     • Canada (WHMIS): "WHMIS", "HPR", "SOR/2015-17", bilingual EN/FR sections, Canadian emergency numbers.
     • Australia/NZ: "GHS Revision x (AU)", "SUSMP/Poisons Standard", "HSNO", "WHS Regulations", "Work Health and Safety", Australian/NZ emergency numbers.
   - Key indicators (in order of importance):
     1. Regulatory citations (CLP/REACH, OSHA, WHMIS, etc.)
     2. Emergency contact numbers (country codes indicate target market)
     3. Language of safety sections (hazard statements, first aid, etc.)
     4. Label elements and signal words
   - IGNORE supplier address/phone - focus on emergency numbers and regulatory framework for the target market.
   - If no specific country indicators found, use "EU (CLP/REACH)" as fallback for EU regulatory framework.
   - Output format: "Germany (GHS DE)", "France (GHS FR)", "Sweden (GHS SE)", "US (OSHA HazCom 2012)", "Canada (WHMIS)", "Australia (GHS AU)", etc.

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
Return ONLY a valid JSON object (no markdown, no extra text) with exactly these fields:
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


def extract_product_info_with_ai(text: str, filename: str, api_key_index: int = 0) -> Dict[str, Any]:
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
        result = suggest_with_openai(prompt, max_items=1, api_key_index=api_key_index)
        
        print(f"AI API response for {filename}: {result}")
        
        if result and len(result) > 0:
            print(f"AI extraction successful for {filename}")
            ai_result = result[0]
            
            # Justera marknad baserat på språk och filename (t.ex. EU + Swedish -> Sweden)
            if ai_result.get("authored_market", {}).get("value") and ai_result.get("language", {}).get("value"):
                market_value = ai_result["authored_market"]["value"]
                language_value = ai_result["language"]["value"]
                adjusted_market = adjust_market_by_language(market_value, language_value, filename)
                if adjusted_market != market_value:
                    print(f"AI: Adjusted market from '{market_value}' to '{adjusted_market}' based on language '{language_value}' and filename '{filename}'")
                    ai_result["authored_market"]["value"] = adjusted_market
            
            return ai_result
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
    
    # Look for product name patterns (more comprehensive and specific)
    product_patterns = [
        r'(?:Product name|Trade name|Commercial name|Product identifier|Handelsname)[:\s]+([^\n\r]+?)(?:\n|$)',
        r'(?:Produktnamn|Produktbezeichnung|Nom du produit|Nombre del producto)[:\s]+([^\n\r]+?)(?:\n|$)',
        r'^([A-Z][A-Z\s\-0-9\(\)]+(?:[A-Z][A-Z\s\-0-9\(\)]+)*)\s*$',  # All caps product names at start of line
        r'^([A-Z][A-Za-z\s\-0-9\(\)]{3,50})\s*$',  # Mixed case product names
    ]
    
    # First, try to find explicit product name labels
    for pattern in product_patterns[:2]:
        product_match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if product_match:
            candidate = product_match.group(1).strip()
            # Filter out section headers and generic terms
            if not any(skip in candidate.lower() for skip in ['section', 'identification', 'uses', 'composition', 'hazards', 'first aid']):
                product_name = candidate
                break
    
    # If no explicit product name found, try to find the main product title
    if not product_name:
        lines = text.split('\n')
        for line in lines[:20]:  # Check first 20 lines
            line = line.strip()
            if len(line) > 10 and len(line) < 100:
                # Look for lines that look like product names
                if (re.match(r'^[A-Z][A-Za-z\s\-0-9\(\)]+$', line) and 
                    not any(skip in line.lower() for skip in ['section', 'page', 'date', 'revision', 'version', 'company', 'address'])):
                    product_name = line
                    break
    
    # Look for article number patterns (more comprehensive)
    article_patterns = [
        r'(?:Article number|Article No|Artikelnummer|Artikel-Nr|Art\.-Nr|Part No|Item No|Product code|Product Code)[:\s]+([^\n\r\s]+)',
        r'(?:Kat\.\s*nr|Varenummer|Tuotenumero|Référence|Código de artículo)[:\s]+([^\n\r\s]+)',
        r'\b(DS\d+)\b',  # Pattern like DS025
        r'\b(CCS\d+)\b',  # Pattern like CCS10019
        r'\b([A-Z0-9]{2,}-[A-Z0-9]{2,})\b',  # Pattern like ABC-123
        r'\b([A-Z]{2,}[0-9]{3,})\b',  # Pattern like ABC123
        r'\b([0-9]{3,6})\b',  # Numeric codes (3-6 digits)
    ]
    
    for pattern in article_patterns:
        article_match = re.search(pattern, text, re.IGNORECASE)
        if article_match:
            candidate = article_match.group(1).strip()
            # Filter out common false positives
            if not any(skip in candidate.lower() for skip in ['well-ventilated', 'fire-fighters', 'children', 'pressure']):
                article_number = candidate
                break
    
    # Look for manufacturer/supplier patterns (more comprehensive)
    company_patterns = [
        r'(?:Manufacturer|Supplier|Company|Responsible person|Importeur|Importer|Distributör|Distributor)[:\s]+([^\n\r]+?)(?:\n|$)',
        r'(?:Hersteller|Lieferant|Unternehmen|Verantwortliche Person)[:\s]+([^\n\r]+?)(?:\n|$)',
        r'(?:Fabricant|Fournisseur|Société|Personne responsable)[:\s]+([^\n\r]+?)(?:\n|$)',
        r'^([A-Z][A-Za-z\s&]+(?:Inc|Ltd|AB|GmbH|Co|Corp|Company|Limited|SE\s*&\s*Co\.\s*KG))',  # Company names at start of line
        r'(?:CRC|3M|BASF|Dow|DuPont|Henkel|AkzoNobel|Kärcher|Karcher)\s+([A-Za-z\s&\.]+)',  # Known manufacturers including Kärcher
        r'([A-Z][A-Za-z\s&\.]+(?:SE\s*&\s*Co\.\s*KG|GmbH|AB|Ltd|Inc|Corp))',  # German company patterns like "Alfred Kärcher SE & Co. KG"
        r'([A-Z][A-Za-z\s\-]+(?:Str\.|Street|Avenue|Road)[\s\w\-,]+)',  # Company with address pattern
    ]
    
    for pattern in company_patterns:
        company_match = re.search(pattern, text, re.IGNORECASE)
        if company_match:
            candidate = company_match.group(1).strip()
            # Filter out common false positives and section headers, but be less restrictive
            if (not any(skip in candidate.lower() for skip in ['section', 'identification', 'safety', 'data', 'sheet', 'page', 'revision']) and
                len(candidate) > 3 and  # Must be at least 3 characters
                not candidate.isdigit()):  # Not just numbers
                company_name = candidate
                break
    
    # Först försök hitta länder från regulatoriska ramverk (högsta prioritet)
    if re.search(r'WHS\s+Regulations|Work\s+Health\s+and\s+Safety', text, re.IGNORECASE):
        authored_market = "Australia"
    elif re.search(r'WHMIS|HPR|SOR/2015-17', text, re.IGNORECASE):
        authored_market = "Canada"
    elif re.search(r'OSHA|29\s+CFR\s+1910\.1200|Hazard\(s\)\s+Identification', text, re.IGNORECASE):
        authored_market = "USA"
    elif re.search(r'Regulation\s+\(EC\)\s+No\s+1272/2008|CLP|REACH', text, re.IGNORECASE):
        # EU regulatory framework - determine specific country
        if re.search(r'Sweden|Sverige|SE-', text, re.IGNORECASE):
            authored_market = "Sweden"
        elif re.search(r'Germany|Deutschland|DE-', text, re.IGNORECASE):
            authored_market = "Germany"
        elif re.search(r'France|Français|FR-', text, re.IGNORECASE):
            authored_market = "France"
        else:
            authored_market = "EU (CLP/REACH)"
    # Fallback to country names if no regulatory framework found
    elif re.search(r'Sweden|Sverige', text, re.IGNORECASE):
        authored_market = "Sweden"
    elif re.search(r'Germany|Deutschland', text, re.IGNORECASE):
        authored_market = "Germany"
    elif re.search(r'France|Français', text, re.IGNORECASE):
        authored_market = "France"
    elif re.search(r'Canada|Canadian', text, re.IGNORECASE):
        authored_market = "Canada"
    elif re.search(r'USA|United States|American', text, re.IGNORECASE):
        authored_market = "USA"
    elif re.search(r'Australia|Australian', text, re.IGNORECASE):
        authored_market = "Australia"
    else:
        # Om inget land hittats, leta efter andra marknad patterns
        market_patterns = [
            r'(?:Market|Region|Regulatory market)[:\s]+([^\n\r]+)',
            r'\bEU\b',  # EU som separat ord
            r'(?:USA|US|Canada|UK|Australia)[\s\w]*',  # Andra regions
            r'(?:CLP|REACH|OSHA|WHMIS|GHS)[\s\w]*',  # Regulatory frameworks sist
        ]
        
        for pattern in market_patterns:
            market_match = re.search(pattern, text, re.IGNORECASE)
            if market_match:
                authored_market = market_match.group(0).strip()
                break
    
    # Separera marknad och lagstiftning även för simple text extraction
    if authored_market:
        market, legislation = separate_market_and_legislation(authored_market)
        authored_market = market  # Använd bara marknaden
    
    # Detect language from content - förbättrad språkdetektering
    if re.search(r'(?:Faraangivelser|Riskfraser|Produktnamn|Leverantör|Företag|Sverige|Swedish|svenska|Svenska)', text, re.IGNORECASE):
        language = "Swedish"
    elif re.search(r'(?:Faraoangivelser|Gefahrhinweise|H-Sätze|deutsch|Deutsch)', text, re.IGNORECASE):
        language = "German"
    elif re.search(r'(?:Déclarations de danger|Phrases de risque|français|Français)', text, re.IGNORECASE):
        language = "French"
    elif re.search(r'(?:Hazard statements|Danger statements|english|English)', text, re.IGNORECASE):
        language = "English"
    
    # If no specific language detected, default to English
    if not language:
        language = "English"
    
    # Justera marknad baserat på språk och filename (t.ex. EU + Swedish -> Sweden)
    if authored_market and language:
        adjusted_market = adjust_market_by_language(authored_market, language, filename)
        if adjusted_market != authored_market:
            print(f"Adjusted market from '{authored_market}' to '{adjusted_market}' based on language '{language}' and filename '{filename}'")
            authored_market = adjusted_market
    
    # Determine extraction status
    extracted_fields = [product_name, article_number, company_name]
    status = "success" if any(extracted_fields) else "partial"
    
    print(f"Simple extraction results for {filename}: product={product_name}, article={article_number}, company={company_name}, market={authored_market}, language={language}, status={status}")
    
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


def adjust_market_by_language(market: str, language: str, filename: str = "") -> str:
    """Justera marknad baserat på språk och filename - t.ex. EU + Swedish -> Sweden"""
    if not market or not language:
        return market
    
    # Språk-till-land mapping
    language_to_country = {
        "Swedish": "Sweden",
        "German": "Germany", 
        "French": "France",
        "Spanish": "Spain",
        "Italian": "Italy",
        "Dutch": "Netherlands",
        "Danish": "Denmark",
        "Norwegian": "Norway",
        "Finnish": "Finland",
        "Polish": "Poland",
        "Czech": "Czech Republic",
        "Hungarian": "Hungary",
        "Portuguese": "Portugal",
        "Greek": "Greece",
        "Slovak": "Slovakia",
        "Slovenian": "Slovenia",
        "Croatian": "Croatia",
        "Romanian": "Romania",
        "Bulgarian": "Bulgaria",
        "Estonian": "Estonia",
        "Latvian": "Latvia",
        "Lithuanian": "Lithuania",
    }
    
    # Check filename patterns first (highest priority)
    if filename:
        filename_lower = filename.lower()
        if "sweden_ab" in filename_lower or "swedish" in filename_lower:
            return "Sweden"
        elif "germany" in filename_lower or "german" in filename_lower:
            return "Germany"
        elif "france" in filename_lower or "french" in filename_lower:
            return "France"
        elif "canada" in filename_lower or "canadian" in filename_lower:
            return "Canada"
        elif "usa" in filename_lower or "us_" in filename_lower:
            return "USA"
    
    # Om marknaden innehåller EU eller är EU och språket matchar ett EU-land, ändra till det specifika landet
    if ("EU" in market.upper() or market.upper() == "EU") and language in language_to_country:
        return language_to_country[language]
    
    # Om marknaden är otydlig (t.ex. "us Chemicals Code of Practice") men språket är Swedish, ändra till Sweden
    if language == "Swedish" and any(indicator in market.lower() for indicator in ["chemical", "code", "practice", "regulation", "clp", "reach"]):
        return "Sweden"
    
    # Special case: If language is Swedish but market is Germany/Canada, likely wrong - should be Sweden
    if language == "Swedish" and market in ["Germany", "Canada", "USA"]:
        return "Sweden"
    
    return market


def separate_market_and_legislation(market_value: str) -> tuple[str, str]:
    """Separera marknad och lagstiftning från authored_market fält"""
    if not market_value:
        return "", ""
    
    # Mappa från AI:s format till specifika länder och lagstiftning
    market_mapping = {
        "EU (CLP/REACH)": ("EU", "CLP/REACH"),  # Fallback för EU om inget specifikt land hittas
        "US (OSHA HazCom 2012)": ("USA", "OSHA HazCom 2012"),
        "Canada (WHMIS)": ("Canada", "WHMIS"),
        "UK (GB-CLP)": ("UK", "GB-CLP"),
        "Australia (GHS AU)": ("Australia", "GHS AU"),
        "Germany (GHS DE)": ("Germany", "GHS DE"),
        "France (GHS FR)": ("France", "GHS FR"),
        "Sweden (GHS SE)": ("Sweden", "GHS SE"),
        "Norway (GHS NO)": ("Norway", "GHS NO"),
        "Denmark (GHS DK)": ("Denmark", "GHS DK"),
        "Finland (GHS FI)": ("Finland", "GHS FI"),
        "Netherlands (GHS NL)": ("Netherlands", "GHS NL"),
        "Belgium (GHS BE)": ("Belgium", "GHS BE"),
        "Austria (GHS AT)": ("Austria", "GHS AT"),
        "Switzerland (GHS CH)": ("Switzerland", "GHS CH"),
        "Italy (GHS IT)": ("Italy", "GHS IT"),
        "Spain (GHS ES)": ("Spain", "GHS ES"),
        "Poland (GHS PL)": ("Poland", "GHS PL"),
        "Czech Republic (GHS CZ)": ("Czech Republic", "GHS CZ"),
        "Hungary (GHS HU)": ("Hungary", "GHS HU"),
        "Japan (GHS JP)": ("Japan", "GHS JP"),
        "Korea (GHS KR)": ("Korea", "GHS KR"),
        "China (GHS CN)": ("China", "GHS CN"),
        "Brazil (GHS BR)": ("Brazil", "GHS BR"),
        "India (GHS IN)": ("India", "GHS IN"),
        "Mexico (GHS MX)": ("Mexico", "GHS MX"),
        "South Africa (GHS ZA)": ("South Africa", "GHS ZA"),
    }
    
    # Kontrollera exakt match först
    if market_value in market_mapping:
        return market_mapping[market_value]
    
    # Fallback: försök extrahera marknad från format "Marknad (Lagstiftning)"
    import re
    match = re.match(r'^([^(]+)\s*\(([^)]+)\)$', market_value.strip())
    if match:
        market = match.group(1).strip()
        legislation = match.group(2).strip()
        return market, legislation
    
    # Om inget matchar, returnera som marknad
    return market_value, ""


def create_csv_from_pdf_data(pdf_data: List[Dict[str, Any]], output_path: Path) -> Path:
    """Skapa CSV från extraherade PDF-data"""
    # Använd kolumnnamn som matchar auto_map_headers förväntningar
    fieldnames = [
        "product", "vendor", "sku", "market", "legislation", "language", "filename", "extraction_status"
    ]
    
    print(f"Creating CSV with {len(pdf_data)} items at {output_path}")
    
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for i, item in enumerate(pdf_data):
            # Extrahera värden från nested structure och mappa till rätt kolumnnamn
            market_value = item.get("authored_market", {}).get("value", "")
            
            # Separera marknad och lagstiftning
            market, legislation = separate_market_and_legislation(market_value)
            
            row = {
                "product": item.get("product_name", {}).get("value", ""),
                "vendor": item.get("company_name", {}).get("value", ""),
                "sku": item.get("article_number", {}).get("value", ""),
                "market": market,
                "legislation": legislation,
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


def extract_pdf_data_with_ai(url: str, api_key_index: int = 0) -> List[Dict[str, Any]]:
    """Download PDF from URL and extract data using AI."""
    try:
        # Download PDF from URL with shorter timeout and better error handling
        print(f"Downloading PDF from URL: {url}")
        response = requests.get(url, timeout=10, stream=True)
        response.raise_for_status()
        
        # Check if content is actually a PDF
        content_type = response.headers.get('content-type', '').lower()
        if 'pdf' not in content_type and not url.lower().endswith('.pdf'):
            print(f"URL does not appear to be a PDF (content-type: {content_type}): {url}")
            return []
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(response.content)
            temp_path = Path(temp_file.name)
        
        try:
            # Extract text from PDF
            text = extract_pdf_text(temp_path)
            if not text:
                print(f"No text extracted from URL: {url}")
                return []
            
            # Use AI to extract structured data
            ai_result = extract_product_info_with_ai(text, Path(url).name, api_key_index)
            if not ai_result:
                print(f"AI extraction failed for URL: {url}")
                return []
            
            # Convert to the expected format
            return [ai_result]
            
        finally:
            # Clean up temporary file
            temp_path.unlink(missing_ok=True)
            
    except requests.RequestException as e:
        print(f"Error downloading PDF from URL {url}: {str(e)}")
        return []
    except Exception as e:
        print(f"Error processing PDF from URL {url}: {str(e)}")
        return []

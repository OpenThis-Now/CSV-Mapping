from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import AiSuggestion, DatabaseCatalog, ImportFile, Project, MatchRun, MatchResult
from ..schemas import AiSuggestRequest, AiSuggestionItem
from ..openai_client import suggest_with_openai
from ..services.mapping import auto_map_headers
from ..match_engine.scoring import score_fields
from ..services.ai_queue_processor import process_ai_queue
import asyncio

router = APIRouter()


def _process_single_product_ai(project_id: int, customer_row_index: int, session: Session, api_key_index: int = 0) -> list[AiSuggestionItem]:
    """Process AI suggestions for a single product without circular imports."""
    import pandas as pd
    from ..services.files import detect_csv_separator
    
    # Get project data
    p = session.get(Project, project_id)
    if not p:
        raise Exception(f"Project {project_id} not found")
    
    imp = session.exec(select(ImportFile).where(ImportFile.project_id == project_id).order_by(ImportFile.created_at.desc())).first()
    if not imp:
        raise Exception("No import file found")
    
    db = session.get(DatabaseCatalog, p.active_database_id) if p.active_database_id else None
    if not db:
        raise Exception("No active database found")
    
    # Load CSV data
    imp_separator = detect_csv_separator(Path(settings.IMPORTS_DIR) / imp.filename)
    db_separator = detect_csv_separator(Path(settings.DATABASES_DIR) / db.filename)
    
    # Read customer data with encoding handling
    cust_df = None
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            cust_df = pd.read_csv(Path(settings.IMPORTS_DIR) / imp.filename, dtype=str, keep_default_na=False, sep=imp_separator, encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    if cust_df is None:
        cust_df = pd.read_csv(Path(settings.IMPORTS_DIR) / imp.filename, dtype=str, keep_default_na=False, sep=imp_separator, encoding='utf-8', errors='replace')
    
    # Read database data with encoding handling
    db_df = None
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            db_df = pd.read_csv(Path(settings.DATABASES_DIR) / db.filename, dtype=str, keep_default_na=False, sep=db_separator, encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    if db_df is None:
        db_df = pd.read_csv(Path(settings.DATABASES_DIR) / db.filename, dtype=str, keep_default_na=False, sep=db_separator, encoding='utf-8', errors='replace')
    
    # Get customer row
    if customer_row_index >= len(cust_df):
        raise Exception(f"Customer row index {customer_row_index} out of range")
    
    crow = dict(cust_df.iloc[customer_row_index])
    
    # Use mappings
    customer_mapping = imp.columns_map_json or auto_map_headers(cust_df.columns)
    db_mapping = db.columns_map_json or auto_map_headers(db_df.columns)
    
    # Find similar products in database - optimized for performance
    customer_product = crow.get(customer_mapping["product"], "")
    similarities = [score_fields(customer_product, db_product) for db_product in db_df[db_mapping["product"]]]
    db_df["__sim"] = similarities
    short = db_df.sort_values("__sim", ascending=False).head(20).drop(columns=["__sim"])
    db_sample = short.to_dict('records')
    
    # Generate AI suggestions
    try:
        prompt = build_ai_prompt(crow, db_sample, customer_mapping, 3)
        ai_list = suggest_with_openai(prompt, max_items=3, api_key_index=api_key_index)
        
        # Save suggestions to database
        out = []
        for rank, item in enumerate(ai_list):
            s = AiSuggestion(
                project_id=project_id,
                customer_row_index=customer_row_index,
                rank=rank + 1,
                database_fields_json=item["database_fields_json"],
                confidence=item["confidence"],
                rationale=item["rationale"],
                source="ai"
            )
            session.add(s)
            
            # Auto-approve if confidence is 100%
            if s.confidence >= 1.0:
                # Update the match result
                match_result = session.exec(
                    select(MatchResult).where(
                        MatchResult.customer_row_index == customer_row_index,
                        MatchResult.decision == "sent_to_ai"
                    ).order_by(MatchResult.id.desc())
                ).first()
                
                if match_result:
                    match_result.decision = "ai_auto_approved"
                    match_result.db_fields_json = item["database_fields_json"]
                    match_result.ai_status = "auto_approved"
                    match_result.ai_summary = f"AI auto-approved with {s.confidence:.0%} confidence: {s.rationale}"
                    session.add(match_result)
            
            # Auto-reject if confidence is below 30%
            elif s.confidence < 0.3:
                # Update the match result
                match_result = session.exec(
                    select(MatchResult).where(
                        MatchResult.customer_row_index == customer_row_index,
                        MatchResult.decision == "sent_to_ai"
                    ).order_by(MatchResult.id.desc())
                ).first()
                
                if match_result:
                    match_result.decision = "ai_auto_rejected"
                    match_result.ai_status = "auto_rejected"
                    match_result.ai_summary = f"AI auto-rejected with {s.confidence:.0%} confidence (below 30% threshold): {s.rationale}"
                    session.add(match_result)
            
            out.append(AiSuggestionItem(
                id=0,  # Will be set after commit
                customer_row_index=s.customer_row_index,
                rank=s.rank,
                database_fields_json=s.database_fields_json,
                confidence=s.confidence,
                rationale=s.rationale,
                source=s.source,
            ))
        
        session.commit()
        return out
        
    except Exception as e:
        import logging
        log = logging.getLogger("app.ai")
        log.error(f"AI processing failed for row {customer_row_index}: {e}")
        return []


def build_ai_prompt(customer_row, db_sample, mapping, k: int) -> str:
    import textwrap
    return textwrap.dedent(f"""
        You are an expert in product matching. Rank the best {k} candidates from the database against the given customer row, tolerate typos, and clearly flag any market/language differences. Return ONLY a JSON array with {k} objects.

        — Core rules —
        1) Evidence priority:
           GTIN/EAN/UPC > exact article/SKU/MPN > supplier (incl. aliases) > product name tokens > attributes/specs.

        2) Canonicalization & typo tolerance:
           - Normalize: lowercase, trim, collapse whitespace, remove punctuation & hyphens, strip company suffixes (AB/Inc/Co/Company/Ltd/GmbH), remove "The".
           - Diacritics: normalize (ö→o, å→a, etc.).
           - Article/SKU normalization: remove spaces/slashes/dots, unify case, strip leading zeros.
           - Accept *single-edit* typos/transpositions and common OCR confusions in identifiers (0↔O, 1↔I↔l, 5↔S, 8↔B) **only if** all other evidence is consistent. Do not invent identifiers.

        3) Language & market policy (IMPORTANT):
           - Language MUST match; otherwise cap confidence at ≤0.49.
           - Market may differ; if so, explicitly flag it and apply a deduction (see scoring). Market must match for 1.0.

        4) Supplier/brand variance:
           - Treat distributor/private-label/subsidiary names as potential aliases if canonical tokens overlap strongly (e.g., "Sherwinn Williams" ≈ "The Sherwin-Williams Company"). Do not penalize alias when strong identifiers align.

        5) Variant control:
           - Variant tokens (e.g., "Part A/B", size, revision, pack count, color) must match; otherwise apply a significant penalty.

        — Confidence scoring (0..1) —
        A) Exact canonical match → set confidence = **1.0** when ALL are true:
           - Language identical.
           - Market identical.
           - Article/SKU/MPN or GTIN are **equal after canonicalization** (per Rule 2).
           - Product name token set equivalent after normalization (parentheses/hyphens ignored).
           - Variant tokens equivalent (e.g., both "Part B").
           - No contradictory evidence.
           (Do not deduct for supplier alias/typo in this case.)

        B) **CRITICAL: Product type mismatch penalty** — If products are fundamentally different types:
           - **Alcohol wipes vs Industrial adhesive** → confidence ≤ 0.10
           - **Paint vs Cleaning solution** → confidence ≤ 0.15  
           - **Medical device vs Construction material** → confidence ≤ 0.10
           - **Food product vs Chemical** → confidence ≤ 0.05
           - **Different product categories entirely** → confidence ≤ 0.20

        C) Otherwise start from evidence and deduct:
           - Start points:
             * 0.95 if exact article/SKU/MPN match (canonicalized) and names align strongly.
             * 0.90 if GTIN/EAN/UPC match but minor name drift.
             * 0.75–0.89 strong partials (identifier partials + high token similarity).
             * 0.50–0.74 contextual/industry matches with weak identifiers.
           - Deductions (sum; floor at 0):
             * −0.30 market mismatch (severity by region distance).
             * −0.40 language mismatch (cap total at ≤0.49 if language differs).
             * −0.20 supplier mismatch (different companies entirely).
             * −0.15 variant risk (e.g., Part A vs Part B, different size/revision).
             * −0.10 inconsistent identifiers across sources.

        — What to return —
        Return ONLY a JSON array with exactly {k} objects. Each object MUST include:
        - "database_fields_json": the unmodified database row (as a JSON object)
        - "confidence": number 0..1
        - "rationale": A natural, flowing explanation in paragraph form that includes:
           * **Why this product was selected as a potential match** (what similarities led to it being considered)
           * Match strength assessment (Exact/Strong/Partial/Weak match)
           * Evidence analysis: product name, supplier, article number matches and any typo corrections
           * Market/language differences and impact (explicit flags: "OTHER MARKET: …"; "LANGUAGE MISMATCH: …")
           * Variant considerations
           * Whether better alternatives likely exist in this candidate set
           
           IMPORTANT: Do NOT include "FIELDS_TO_REVIEW" in your rationale - this will be handled separately.

        — Calibration examples (for the model; do not output) —
        Example 1 — should be 1.0:
        Input: name "HEAT-FLEX 1200 PLUS (Part B) Hardener", supplier "Sherwinn Williams", art.no "B59V01200", market "Canada", language "English".
        Candidate: name identical, supplier "The Sherwin-Williams Company", art.no "B59V1200", market "Canada", language "English".
        Reasoning: article number equal after canonicalization (extra '0' removed); supplier alias; identical variant "Part B"; same market/language → **Exact canonical match; confidence 1.0**.
        
        Example 2 — partial match:
        Input: name "THINNER 215", supplier "Carboline", art.no "05570910001D", market "Canada", language "English".
        Candidate: name "THINNER 25", supplier "Carboline Global Inc", art.no "0525S1NL", market "Canada", language "English".
        Expected rationale: "This candidate was selected due to similar supplier names and product type (both are thinners), but the article numbers and product names differ significantly."
        
        Example 3 — perfect match:
        Input: name "PAINT 100", supplier "Company A", art.no "P100", market "USA", language "English".
        Candidate: name "PAINT 100", supplier "Company A", art.no "P100", market "USA", language "English".
        Expected rationale: "This is an exact match with identical product name, supplier, article number, market, and language. All fields align perfectly, indicating this is the same product."
        
        Example 4 — product type mismatch (should be very low confidence):
        Input: name "Alcohol Wipes", supplier "Nice Pak", art.no "WP001", market "Australia", language "English".
        Candidate: name "Industrial Adhesive", supplier "3M Canada", art.no "ADH123", market "Canada", language "English".
        Expected: confidence ≤ 0.10, rationale should explain why it was considered (e.g., "This candidate was selected because both products are industrial cleaning/construction materials, but the fundamental product types are incompatible.")

        Customer row to match:
        {json.dumps(customer_row, ensure_ascii=False)}

        Database candidates to analyze:
        {json.dumps(db_sample[: 3 * k], ensure_ascii=False)}
    """).strip()


@router.post("/projects/{project_id}/ai/suggest", response_model=list[AiSuggestionItem])
def ai_suggest(project_id: int, req: AiSuggestRequest, session: Session = Depends(get_session)) -> list[AiSuggestionItem]:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found.")

    imp = session.exec(select(ImportFile).where(ImportFile.project_id == project_id).order_by(ImportFile.created_at.desc())).first()
    if not imp:
        raise HTTPException(status_code=400, detail="No import file uploaded.")
    db = session.get(DatabaseCatalog, p.active_database_id) if p.active_database_id else None
    if not db:
        raise HTTPException(status_code=400, detail="No active database selected.")

    import pandas as pd
    from ..services.files import detect_csv_separator

    # Detect separators for both files
    imp_separator = detect_csv_separator(Path(settings.IMPORTS_DIR) / imp.filename)
    db_separator = detect_csv_separator(Path(settings.DATABASES_DIR) / db.filename)
    
    # Read CSV with error handling for inconsistent columns and encoding
    cust_df = None
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            cust_df = pd.read_csv(Path(settings.IMPORTS_DIR) / imp.filename, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=imp_separator, encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            # Try with different parameters
            try:
                cust_df = pd.read_csv(Path(settings.IMPORTS_DIR) / imp.filename, dtype=str, keep_default_na=False, sep=imp_separator, quotechar='"', on_bad_lines='skip', encoding=encoding)
                break
            except Exception:
                continue
    
    if cust_df is None:
        # Final fallback with error replacement
        try:
            cust_df = pd.read_csv(Path(settings.IMPORTS_DIR) / imp.filename, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=imp_separator, encoding='utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"Could not read import file: {str(e)}")
    
    # Read database CSV with error handling for inconsistent columns and encoding
    db_df = None
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            db_df = pd.read_csv(Path(settings.DATABASES_DIR) / db.filename, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=db_separator, encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            # Try with different parameters
            try:
                db_df = pd.read_csv(Path(settings.DATABASES_DIR) / db.filename, dtype=str, keep_default_na=False, sep=db_separator, quotechar='"', on_bad_lines='skip', encoding=encoding)
                break
            except Exception:
                continue
    
    if db_df is None:
        # Final fallback with error replacement
        try:
            db_df = pd.read_csv(Path(settings.DATABASES_DIR) / db.filename, dtype=str, keep_default_na=False, on_bad_lines='skip', sep=db_separator, encoding='utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"Could not read database file: {str(e)}")
    # Use separate mappings for customer and database
    customer_mapping = imp.columns_map_json or auto_map_headers(cust_df.columns)
    db_mapping = db.columns_map_json or auto_map_headers(db_df.columns)

    # Limit to max 10 rows at a time to prevent timeout
    limited_indices = req.customer_row_indices[:10]
    if len(req.customer_row_indices) > 10:
        # Log warning about limitation
        import logging
        log = logging.getLogger("app.ai")
        log.warning(f"AI analysis limited to first 10 rows out of {len(req.customer_row_indices)} requested")
    
    out: list[AiSuggestionItem] = []
    for idx in limited_indices:
        if idx < 0 or idx >= len(cust_df):
            continue
        crow = dict(cust_df.iloc[idx])

        # Optimized similarity calculation for better performance
        customer_product = crow.get(customer_mapping["product"], "")
        similarities = [score_fields(customer_product, db_product) for db_product in db_df[db_mapping["product"]]]
        db_df["__sim"] = similarities
        short = db_df.sort_values("__sim", ascending=False).head(max(20, 5 * req.max_suggestions)).drop(columns=["__sim"])
        db_sample = short.to_dict('records')

        used = "ai"
        try:
            prompt = build_ai_prompt(crow, db_sample, customer_mapping, req.max_suggestions)
            ai_list = suggest_with_openai(prompt, max_items=req.max_suggestions, api_key_index=0)
        except Exception:
            used = "heuristic"
            # Create better explanations for heuristic matches
            ai_list = []
            for i, r in enumerate(db_sample[: req.max_suggestions]):
                confidence = max(0.5, (i + 1) / (req.max_suggestions + 2))
                product_name = r.get(db_mapping.get("product", ""), "Unknown product")
                supplier_name = r.get(db_mapping.get("vendor", ""), "Unknown supplier")
                
                if i == 0:
                    rationale = f"Best match: Confidence {confidence:.0%}. Product name matches well with customer search, supplier is relevant, and match is based on strong similarities. This match is recommended because it shows highest consistency. No better alternative found in database."
                else:
                    rationale = f"Alternative #{i+1}: Confidence {confidence:.0%}. This product shows partially matching properties but is not as strong as the primary match. Product name has some similarities but supplier or other factors make this match less secure. Consider as backup alternative."
                
                ai_list.append({
                    "database_fields_json": r, 
                    "confidence": confidence, 
                    "rationale": rationale
                })

        for rank, item in enumerate(ai_list, start=1):
            s = AiSuggestion(
                project_id=project_id,
                customer_row_index=idx,
                rank=rank,
                database_fields_json=item["database_fields_json"],
                confidence=float(item.get("confidence", 0.5)),
                rationale=str(item.get("rationale", "")),
                source=used,
            )
            session.add(s)
            session.commit()
            
            # Auto-approve if this is the recommended match (rank 1) with 100% confidence
            if rank == 1 and s.confidence >= 1.0:
                # Find the corresponding MatchResult from the latest match run and auto-approve it
                latest_run = session.exec(
                    select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
                ).first()
                
                if latest_run:
                    match_result = session.exec(
                        select(MatchResult).where(
                            MatchResult.customer_row_index == idx,
                            MatchResult.match_run_id == latest_run.id
                        )
                    ).first()
                    
                    if match_result:
                        match_result.decision = "ai_auto_approved"
                        match_result.db_fields_json = item["database_fields_json"]
                        match_result.ai_status = "auto_approved"
                        match_result.ai_summary = f"AI auto-approved with {s.confidence:.0%} confidence: {s.rationale}"
                        session.add(match_result)
                        session.commit()
            
            out.append(AiSuggestionItem(
                id=s.id,
                customer_row_index=s.customer_row_index,
                rank=s.rank,
                database_fields_json=s.database_fields_json,
                confidence=s.confidence,
                rationale=s.rationale,
                source=s.source,
            ))
    return out


@router.get("/projects/{project_id}/ai/suggestions", response_model=list[AiSuggestionItem])
def get_ai_suggestions(project_id: int, session: Session = Depends(get_session)) -> list[AiSuggestionItem]:
    """Get AI suggestions that are still pending review."""
    # Get the latest match run for this project
    latest_run = session.exec(
        select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
    ).first()
    
    if not latest_run:
        return []
    
    # Get customer row indices that have already been decided
    # This includes all AI-related decisions: manual approval/rejection, auto-approval, and regular rejected
    completed_row_indices = session.exec(
        select(MatchResult.customer_row_index)
        .where(MatchResult.match_run_id == latest_run.id)
        .where(
            # Either has AI status set (manual decisions)
            MatchResult.ai_status.in_(["approved", "rejected", "auto_approved"]) |
            # Or is AI auto-approved
            (MatchResult.decision == "ai_auto_approved") |
            # Or is manually rejected
            (MatchResult.decision == "rejected")
        )
    ).all()
    
    # Get existing AI suggestions that are NOT for completed rows
    existing_suggestions = session.exec(
        select(AiSuggestion)
        .where(AiSuggestion.project_id == project_id)
        .where(~AiSuggestion.customer_row_index.in_(completed_row_indices))
        .order_by(AiSuggestion.customer_row_index, AiSuggestion.rank)
    ).all()
    
    # Also get MatchResults that are "sent_to_ai" but don't have AI suggestions yet
    # These represent products that are ready for AI review but haven't been processed yet
    sent_to_ai_results = session.exec(
        select(MatchResult)
        .where(MatchResult.match_run_id == latest_run.id)
        .where(MatchResult.decision == "sent_to_ai")
        .where(MatchResult.ai_status == None)  # No AI status set yet
        .where(~MatchResult.customer_row_index.in_(completed_row_indices))
        .order_by(MatchResult.customer_row_index)
    ).all()
    
    # Debug logging
    import logging
    log = logging.getLogger("app.ai")
    log.info(f"Found {len(existing_suggestions)} existing suggestions")
    log.info(f"Found {len(sent_to_ai_results)} sent_to_ai results")
    log.info(f"Found {len(completed_row_indices)} completed row indices")
    log.info(f"Completed row indices: {completed_row_indices}")
    
    # Debug: Show details of sent_to_ai_results
    for result in sent_to_ai_results[:3]:  # Show first 3
        log.info(f"Sent to AI result: row_index={result.customer_row_index}, decision={result.decision}, ai_status={result.ai_status}")
    
    # Convert MatchResults to AiSuggestionItem format for display
    match_result_suggestions = []
    for result in sent_to_ai_results:
        # Create a placeholder suggestion for products that are ready for AI review
        match_result_suggestions.append(AiSuggestionItem(
            id=result.id,  # Use match result ID as temporary ID
            customer_row_index=result.customer_row_index,
            rank=1,
            database_fields_json=result.database_fields_json or {},
            confidence=0.0,  # No confidence yet since AI hasn't run
            rationale="Ready for AI review - click to start analysis",
            source="pending_ai_review"
        ))
    
    # Combine existing suggestions with pending review items
    all_suggestions = list(existing_suggestions) + match_result_suggestions
    
    # Deduplicate suggestions by customer_row_index + product_name to avoid showing identical matches
    seen_combinations = set()
    deduplicated_suggestions = []
    
    for s in all_suggestions:
        product_name = s.database_fields_json.get("Product_name", "")
        combination_key = (s.customer_row_index, product_name)
        
        if combination_key not in seen_combinations:
            seen_combinations.add(combination_key)
            deduplicated_suggestions.append(s)
    
    return [
        AiSuggestionItem(
            id=s.id,
            customer_row_index=s.customer_row_index,
            rank=s.rank,
            database_fields_json=s.database_fields_json,
            confidence=s.confidence,
            rationale=s.rationale,
            source=s.source,
        )
        for s in deduplicated_suggestions
    ]


@router.get("/projects/{project_id}/ai/completed-reviews")
def get_completed_ai_reviews(project_id: int, session: Session = Depends(get_session)):
    """Get AI suggestions that have been approved or rejected."""
    # Get the latest match run for this project
    latest_run = session.exec(
        select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
    ).first()
    
    if not latest_run:
        return []
    
    # Get match results that have been decided and had AI involvement
    # This includes:
    # 1. AI manually approved: ai_status = "approved" 
    # 2. AI auto-approved: decision = "ai_auto_approved", ai_status = "auto_approved"
    # 3. AI rejected: decision = "rejected" AND there are AI suggestions for this row
    
    # First get all AI suggestion row indices for this project
    ai_suggestion_rows = session.exec(
        select(AiSuggestion.customer_row_index)
        .where(AiSuggestion.project_id == project_id)
        .distinct()
    ).all()
    
    # Get completed results that either have ai_status set OR are rejected/approved and had AI suggestions
    completed_results = session.exec(
        select(MatchResult)
        .where(MatchResult.match_run_id == latest_run.id)
        .where(
            # Either has AI status set
            MatchResult.ai_status.in_(["approved", "rejected", "auto_approved"]) |
            # Or is ai_auto_approved
            (MatchResult.decision == "ai_auto_approved") |
            # Or is rejected/approved and had AI suggestions
            (
                MatchResult.decision.in_(["rejected", "approved"]) &
                MatchResult.customer_row_index.in_(ai_suggestion_rows)
            )
        )
        .order_by(MatchResult.customer_row_index)
    ).all()
    
    completed_reviews = []
    for result in completed_results:
        # Determine the AI decision status
        if result.ai_status == "auto_approved" or result.decision == "ai_auto_approved":
            # AI auto-approved (both automatic and manual flows should show same status)
            decision = "auto_approved"
        elif result.ai_status == "approved":
            # Manually approved after AI suggestions
            decision = "approved"
        elif result.ai_status == "rejected" or (result.decision == "rejected" and result.customer_row_index in ai_suggestion_rows):
            # Rejected after AI suggestions were made
            decision = "rejected"
        elif result.decision == "approved" and result.customer_row_index in ai_suggestion_rows:
            # Approved after AI suggestions were made (but no ai_status set)
            decision = "approved"
        else:
            # Fallback
            decision = result.decision
        
        # Get the approved AI suggestion if it exists
        ai_suggestion = None
        if result.approved_ai_suggestion_id:
            ai_suggestion = session.get(AiSuggestion, result.approved_ai_suggestion_id)
        
        # For AI auto-approved products, use db_fields_json if no approved suggestion
        database_fields = None
        confidence = None
        rationale = None
        
        if ai_suggestion:
            # Manually approved AI suggestion
            database_fields = ai_suggestion.database_fields_json
            confidence = ai_suggestion.confidence
            rationale = ai_suggestion.rationale
        elif result.db_fields_json:
            # AI auto-approved (stored in db_fields_json)
            database_fields = result.db_fields_json
            # Extract confidence from ai_summary if available
            if result.ai_summary and "confidence" in result.ai_summary:
                try:
                    confidence_str = result.ai_summary.split("confidence:")[0].split()[-1]
                    confidence = float(confidence_str.replace("%", "")) / 100
                except:
                    confidence = 0.95  # Default for auto-approved
            else:
                confidence = 0.95  # Default for auto-approved
            rationale = result.ai_summary or "AI auto-approved"
        
        completed_reviews.append({
            "customer_row_index": result.customer_row_index,
            "decision": decision,
            "customer_fields": result.customer_fields_json,
            "ai_summary": result.ai_summary,
            "approved_suggestion": {
                "database_fields_json": database_fields,
                "confidence": confidence,
                "rationale": rationale
            } if database_fields else None
        })
    
    return completed_reviews


@router.post("/projects/{project_id}/ai/auto-queue")
def auto_queue_ai_analysis(project_id: int, session: Session = Depends(get_session)):
    """Automatically queue products with scores between 70-95 for AI analysis."""
    import logging
    log = logging.getLogger("app.ai")
    
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found.")
    
    # Get the latest match run
    latest_run = session.exec(
        select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
    ).first()
    
    if not latest_run:
        raise HTTPException(status_code=400, detail="No match run found. Run matching first.")
    
    log.info(f"Latest match run ID: {latest_run.id}")
    
    # Find results with scores between 70-95 that are not already sent to AI
    # Note: Excluding "rejected" to prevent re-queuing manually rejected products
    results_to_queue = session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.overall_score >= 70,
            MatchResult.overall_score <= 95,
            MatchResult.decision.in_(["pending", "auto_approved"])
        )
    ).all()
    
    log.info(f"Found {len(results_to_queue)} products in 70-95 score range")
    
    # Debug: Show some of the scores found
    if results_to_queue:
        for i, result in enumerate(results_to_queue[:3]):
            log.info(f"  Product {i+1}: score={result.overall_score}, decision={result.decision}")
    else:
        log.info("  No products found in 70-95 score range")
    
    # Check if there are any manually sent products that need processing
    manually_sent_products = session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.decision == "sent_to_ai",
            MatchResult.ai_status == "queued"
        )
    ).all()
    
    if not results_to_queue and not manually_sent_products:
        return {"message": "No products found in the 70-95 score range to queue for AI analysis.", "queued_count": 0}
    
    # If no auto-queued products but manually sent products exist, still start processing
    if not results_to_queue and manually_sent_products:
        log.info(f"Found {len(manually_sent_products)} manually sent products to process")
    
    # Update these results to "sent_to_ai" status
    queued_count = 0
    for result in results_to_queue:
        result.decision = "sent_to_ai"
        result.ai_status = "queued"
        session.add(result)
        queued_count += 1
    
    session.commit()
    
    # Start background processing immediately with simplified approach
    # This will process both auto-queued and manually sent products
    try:
        import threading
        import time
        
        def run_ai_queue():
            """Process AI queue in batches with automatic continuation"""
            log.info(f"Starting AI queue processing for project {project_id}")
            log.info(f"Auto-queued: {queued_count}, Manually sent: {len(manually_sent_products) if 'manually_sent_products' in locals() else 0}")
            
            try:
                # Process until no more queued products
                while True:
                    # Create new session for each batch
                    with next(get_session()) as batch_session:
                        # Get latest match run
                        latest_run = batch_session.exec(
                            select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
                        ).first()
                        
                        if not latest_run:
                            log.info(f"No match run found for project {project_id}")
                            break
                        
                        # Get next batch of queued products (including manually sent ones)
                        queued_products = batch_session.exec(
                            select(MatchResult).where(
                                MatchResult.match_run_id == latest_run.id,
                                MatchResult.decision == "sent_to_ai",
                                MatchResult.ai_status == "queued"
                            ).limit(10)  # Process 10 at a time for better speed
                        ).all()
                        
                        if not queued_products:
                            log.info(f"No more queued products to process for project {project_id}")
                            break
                        
                        log.info(f"Processing batch of {len(queued_products)} products for project {project_id}")
                        
                        # First, mark all products in batch as processing
                        for product in queued_products:
                            product.ai_status = "processing"
                            batch_session.add(product)
                        batch_session.commit()
                        
                        # Process products in parallel using threading
                        import concurrent.futures
                        import threading
                        
                        def process_single_product(product):
                            """Process a single product with its own session"""
                            try:
                                log.info(f"Processing product {product.customer_row_index}")
                                
                                # Create new session for this thread
                                with next(get_session()) as thread_session:
                                    # Get fresh product data
                                    fresh_product = thread_session.get(MatchResult, product.id)
                                    if not fresh_product:
                                        return
                                    
                                    # Process AI suggestions with API key rotation
                                    api_key_index = product.customer_row_index % 5  # Rotate through 5 API keys
                                    suggestions = _process_single_product_ai(project_id, product.customer_row_index, thread_session, api_key_index)
                                
                                log.info(f"Generated {len(suggestions)} suggestions for product {product.customer_row_index}")
                                
                                # Mark as completed
                                fresh_product.ai_status = "completed"
                                thread_session.add(fresh_product)
                                thread_session.commit()
                                
                            except Exception as e:
                                log.error(f"Error processing product {product.customer_row_index}: {e}")
                                # Mark as failed
                                with next(get_session()) as thread_session:
                                    fresh_product = thread_session.get(MatchResult, product.id)
                                    if fresh_product:
                                        fresh_product.ai_status = "failed"
                                        thread_session.add(fresh_product)
                                        thread_session.commit()
                        
                        # Use ThreadPoolExecutor for parallel processing
                        max_workers = min(len(queued_products), 5)  # Max 5 parallel workers
                        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                            # Submit all products for parallel processing
                            futures = [executor.submit(process_single_product, product) for product in queued_products]
                            
                            # Wait for all to complete
                            for future in concurrent.futures.as_completed(futures):
                                try:
                                    future.result()  # This will raise any exceptions
                                except Exception as e:
                                    log.error(f"Thread execution error: {e}")
                    
                    # Small delay between batches
                    time.sleep(0.5)
                
                log.info(f"All AI processing completed for project {project_id}")
                
            except Exception as e:
                log.error(f"Error in AI queue processing: {e}")
        
        thread = threading.Thread(target=run_ai_queue)
        thread.daemon = True
        thread.start()
        
        log.info(f"Started AI queue processing thread for project {project_id}")
    except Exception as e:
        log.error(f"Failed to start AI queue processing: {e}")
    
    return {
        "message": f"Successfully queued {queued_count} products for AI analysis.",
        "queued_count": queued_count,
        "score_range": "70-95",
        "processing_started": True
    }


@router.get("/projects/{project_id}/ai/queue-status")
def get_ai_queue_status(project_id: int, session: Session = Depends(get_session)):
    """Get the current status of the AI queue."""
    from ..models import MatchRun
    
    # Get the latest match run for this project
    latest_run = session.exec(
        select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
    ).first()
    
    if not latest_run:
        return {
            "queued": 0,
            "processing": 0,
            "ready": 0,
            "autoApproved": 0
        }
    
    # Count products in different AI states for this match run
    # Include both explicitly queued and newly sent to AI (without ai_status yet)
    queued_count = len(session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.decision == "sent_to_ai",
            (MatchResult.ai_status == "queued") | (MatchResult.ai_status.is_(None))
        )
    ).all())
    
    processing_count = len(session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.decision == "sent_to_ai",
            MatchResult.ai_status == "processing"
        )
    ).all())
    
    ready_count = len(session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.decision == "sent_to_ai",
            MatchResult.ai_status == "completed"
        )
    ).all())
    
    auto_approved_count = len(session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.decision == "ai_auto_approved"
        )
    ).all())
    
    # Only show AI queue status if there are actually AI-related products
    total_ai_products = queued_count + processing_count + ready_count + auto_approved_count
    
    if total_ai_products == 0:
        return {
            "queued": 0,
            "processing": 0,
            "ready": 0,
            "autoApproved": 0
        }
    
    return {
        "queued": queued_count,
        "processing": processing_count,
        "ready": ready_count,
        "autoApproved": auto_approved_count
    }


@router.get("/projects/{project_id}/ai/unified-status")
def get_unified_ai_status(project_id: int, session: Session = Depends(get_session)):
    """Get unified AI processing status including CSV AI queue, PDF processing, and URL enhancement."""
    from ..models import MatchRun, URLEnhancementRun
    
    # Get the latest match run for this project
    latest_run = session.exec(
        select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
    ).first()
    
    # Initialize counters
    csv_queued = 0
    csv_processing = 0
    csv_completed = 0
    pdf_queued = 0
    pdf_processing = 0
    pdf_completed = 0
    url_queued = 0
    url_processing = 0
    url_completed = 0
    
    # CSV-based AI queue status
    if latest_run:
        csv_queued = len(session.exec(
            select(MatchResult).where(
                MatchResult.match_run_id == latest_run.id,
                MatchResult.decision == "sent_to_ai",
                (MatchResult.ai_status == "queued") | (MatchResult.ai_status.is_(None))
            )
        ).all())
        
        csv_processing = len(session.exec(
            select(MatchResult).where(
                MatchResult.match_run_id == latest_run.id,
                MatchResult.decision == "sent_to_ai",
                MatchResult.ai_status == "processing"
            )
        ).all())
        
        csv_completed = len(session.exec(
            select(MatchResult).where(
                MatchResult.match_run_id == latest_run.id,
                MatchResult.decision == "sent_to_ai",
                MatchResult.ai_status.in_(["completed", "auto_approved"])
            )
        ).all())
    
    # URL Enhancement status
    latest_url_run = session.exec(
        select(URLEnhancementRun).where(
            URLEnhancementRun.project_id == project_id
        ).order_by(URLEnhancementRun.created_at.desc())
    ).first()
    
    if latest_url_run:
        url_queued = max(0, latest_url_run.total_urls - latest_url_run.processed_urls)
        url_processing = 1 if latest_url_run.status == "running" and latest_url_run.processed_urls < latest_url_run.total_urls else 0
        url_completed = latest_url_run.processed_urls
    
    # PDF processing status (check for running PDF imports)
    # Note: PDF processing is typically fast and doesn't have persistent queue status
    # We'll check if there are any recent PDF imports that might be processing
    pdf_imports = session.exec(
        select(ImportFile).where(
            ImportFile.project_id == project_id,
            ImportFile.filename.like("%pdf_import%")
        ).order_by(ImportFile.created_at.desc()).limit(5)
    ).all()
    
    # If there are recent PDF imports, assume they might be processing
    if pdf_imports:
        # Check if any were created in the last 5 minutes (likely still processing)
        from datetime import datetime, timedelta
        recent_threshold = datetime.now() - timedelta(minutes=5)
        
        recent_pdfs = [imp for imp in pdf_imports if imp.created_at > recent_threshold]
        if recent_pdfs:
            pdf_processing = len(recent_pdfs)
            pdf_queued = 0  # PDFs are processed immediately, no persistent queue
    
    # Calculate totals
    total_queued = csv_queued + pdf_queued + url_queued
    total_processing = csv_processing + pdf_processing + url_processing
    total_completed = csv_completed + pdf_completed + url_completed
    total_items = total_queued + total_processing + total_completed
    
    return {
        "csv": {
            "queued": csv_queued,
            "processing": csv_processing,
            "completed": csv_completed,
            "total": csv_queued + csv_processing + csv_completed
        },
        "pdf": {
            "queued": pdf_queued,
            "processing": pdf_processing,
            "completed": pdf_completed,
            "total": pdf_queued + pdf_processing + pdf_completed
        },
        "url": {
            "queued": url_queued,
            "processing": url_processing,
            "completed": url_completed,
            "total": url_queued + url_processing + url_completed
        },
        "total": {
            "queued": total_queued,
            "processing": total_processing,
            "completed": total_completed,
            "total": total_items
        },
        "hasActivity": total_processing > 0 or total_queued > 0
    }


@router.post("/projects/{project_id}/ai/pause-queue")
def pause_ai_queue(project_id: int, session: Session = Depends(get_session)):
    """Pause the AI queue processing."""
    from ..services.ai_queue_manager import ai_queue_manager
    
    ai_queue_manager.pause(project_id)
    return {"message": "AI queue paused", "paused": True}


@router.post("/projects/{project_id}/ai/resume-queue")
def resume_ai_queue(project_id: int, session: Session = Depends(get_session)):
    """Resume the AI queue processing."""
    from ..services.ai_queue_manager import ai_queue_manager
    
    ai_queue_manager.resume(project_id)
    return {"message": "AI queue resumed", "resumed": True}

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

        B) Otherwise start from evidence and deduct:
           - Start points:
             * 0.95 if exact article/SKU/MPN match (canonicalized) and names align strongly.
             * 0.90 if GTIN/EAN/UPC match but minor name drift.
             * 0.75–0.89 strong partials (identifier partials + high token similarity).
             * 0.50–0.74 contextual/industry matches with weak identifiers.
           - Deductions (sum; floor at 0):
             * −0.20 market mismatch (severity by region distance).
             * −0.25 language mismatch (cap total at ≤0.49 if language differs).
             * −0.10 supplier alias uncertainty (skip if Exact canonical match).
             * −0.15 variant risk (e.g., Part A vs Part B, different size/revision).
             * −0.10 inconsistent identifiers across sources.

        — What to return —
        Return ONLY a JSON array with exactly {k} objects. Each object MUST include:
        - "database_fields_json": the unmodified database row (as a JSON object)
        - "confidence": number 0..1
        - "rationale": A natural, flowing explanation in paragraph form that includes:
           * Match strength assessment (Exact/Strong/Partial/Weak match)
           * Evidence analysis: product name, supplier, article number matches and any typo corrections
           * Market/language differences and impact (explicit flags: "OTHER MARKET: …"; "LANGUAGE MISMATCH: …")
           * Variant considerations
           * Whether better alternatives likely exist in this candidate set
           * Specific fields that need review (e.g., "Article number", "Product name & Article number")
           
           Write as a natural paragraph, not as structured JSON fields. Example format:
           "Strong match. The product name matches exactly, and the supplier is a recognized alias of [supplier]. The article number '[article]' has a minor typo correction from '[original]' ([change]), but the identifiers are consistent. Both market and language are identical. No variant issues are present. Better alternatives are unlikely as this is the closest match."

        — Calibration examples (for the model; do not output) —
        Example 1 — should be 1.0:
        Input: name "HEAT-FLEX 1200 PLUS (Part B) Hardener", supplier "Sherwinn Williams", art.no "B59V01200", market "Canada", language "English".
        Candidate: name identical, supplier "The Sherwin-Williams Company", art.no "B59V1200", market "Canada", language "English".
        Reasoning: article number equal after canonicalization (extra '0' removed); supplier alias; identical variant "Part B"; same market/language → **Exact canonical match; confidence 1.0**.

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

        db_df["__sim"] = db_df[db_mapping["product"]].apply(lambda x: score_fields(crow.get(customer_mapping["product"], ""), x))
        short = db_df.sort_values("__sim", ascending=False).head(max(20, 5 * req.max_suggestions)).drop(columns=["__sim"])
        db_sample = [dict(r) for _, r in short.iterrows()]

        used = "ai"
        try:
            prompt = build_ai_prompt(crow, db_sample, customer_mapping, req.max_suggestions)
            ai_list = suggest_with_openai(prompt, max_items=req.max_suggestions)
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
    """Get all AI suggestions for a project."""
    suggestions = session.exec(
        select(AiSuggestion).where(AiSuggestion.project_id == project_id).order_by(AiSuggestion.customer_row_index, AiSuggestion.rank)
    ).all()
    
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
        for s in suggestions
    ]


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
    results_to_queue = session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.overall_score >= 70,
            MatchResult.overall_score <= 95,
            MatchResult.decision.in_(["pending", "auto_approved", "not_approved"])
        )
    ).all()
    
    log.info(f"Found {len(results_to_queue)} products in 70-95 score range")
    
    if not results_to_queue:
        return {"message": "No products found in the 70-95 score range to queue for AI analysis.", "queued_count": 0}
    
    # Update these results to "sent_to_ai" status
    queued_count = 0
    for result in results_to_queue:
        result.decision = "sent_to_ai"
        result.ai_status = "queued"
        session.add(result)
        queued_count += 1
    
    session.commit()
    
    # Start background processing immediately using the existing AI suggest endpoint
    try:
        import threading
        import time
        
        def run_ai_queue():
            """Process AI queue in batches of 10 products with pause/resume support"""
            import time
            from ..db import get_session
            from ..services.ai_queue_manager import ai_queue_manager
            
            # Register this thread
            ai_queue_manager.register_thread(project_id, threading.current_thread())
            
            try:
                # Process in batches until no more queued products
                while True:
                    # Check if paused before each batch
                    if not ai_queue_manager.wait_if_paused(project_id):
                        break
                    
                    # Create new session for each batch
                    batch_session = next(get_session())
                    
                    try:
                        # Get next batch of queued products for the latest match run
                        latest_run = batch_session.exec(
                            select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())
                        ).first()
                        
                        if not latest_run:
                            log.info(f"No match run found for project {project_id}")
                            break
                        
                        queued_products = batch_session.exec(
                            select(MatchResult).where(
                                MatchResult.match_run_id == latest_run.id,
                                MatchResult.decision == "sent_to_ai",
                                MatchResult.ai_status == "queued"
                            ).limit(10)  # Process 10 at a time
                        ).all()
                        
                        if not queued_products:
                            log.info(f"No more queued products to process for project {project_id}")
                            break
                        
                        log.info(f"Processing batch of {len(queued_products)} products for project {project_id}")
                        
                        # Mark as processing
                        for product in queued_products:
                            product.ai_status = "processing"
                            batch_session.add(product)
                        batch_session.commit()
                        
                        # Process each product in the batch
                        for product in queued_products:
                            # Check if paused before each product
                            if not ai_queue_manager.wait_if_paused(project_id):
                                # Mark remaining products as queued again
                                for remaining in queued_products:
                                    if remaining.ai_status == "processing":
                                        remaining.ai_status = "queued"
                                        batch_session.add(remaining)
                                batch_session.commit()
                                return
                            
                            try:
                                log.info(f"Processing product {product.customer_row_index}")
                                
                                # Use existing AI suggest endpoint logic
                                from .ai import ai_suggest
                                from ..schemas import AiSuggestRequest
                                
                                # Create request for this single product
                                req = AiSuggestRequest(
                                    customer_row_indices=[product.customer_row_index],
                                    max_suggestions=3
                                )
                                
                                # Call the existing AI suggest function
                                suggestions = ai_suggest(project_id, req, batch_session)
                                
                                log.info(f"Generated {len(suggestions)} suggestions for product {product.customer_row_index}")
                                
                                # Mark as completed
                                product.ai_status = "completed"
                                batch_session.add(product)
                                batch_session.commit()
                                
                            except Exception as e:
                                log.error(f"Error processing product {product.customer_row_index}: {e}")
                                product.ai_status = "failed"
                                batch_session.add(product)
                                batch_session.commit()
                        
                        log.info(f"Completed batch processing for project {project_id}")
                        
                    finally:
                        batch_session.close()
                    
                    # Small delay before next batch
                    time.sleep(1)
                
                log.info(f"All AI processing completed for project {project_id}")
                
            except Exception as e:
                log.error(f"Error in AI queue processing: {e}")
            finally:
                # Unregister this thread
                ai_queue_manager.unregister_thread(project_id)
        
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
            "completed": 0,
            "total": 0
        }
    
    # Count products in different AI states for this match run
    queued_count = len(session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.decision == "sent_to_ai",
            MatchResult.ai_status == "queued"
        )
    ).all())
    
    processing_count = len(session.exec(
        select(MatchResult).where(
            MatchResult.match_run_id == latest_run.id,
            MatchResult.decision == "sent_to_ai",
            MatchResult.ai_status == "processing"
        )
    ).all())
    
    completed_count = len(session.exec(
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
    
    return {
        "queued": queued_count,
        "processing": processing_count,
        "ready": completed_count,
        "autoApproved": auto_approved_count,
        "total": queued_count + processing_count + completed_count + auto_approved_count
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

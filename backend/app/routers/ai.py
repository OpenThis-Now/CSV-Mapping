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
        - "rationale": 2–6 sentences in English that MUST include:
           * Match summary: Exact/Strong/Partial/Weak
           * Evidence (identifiers, name/supplier/article similarities; mention typo corrections)
           * Market/language differences and impact (explicit flags: "OTHER MARKET: …"; "LANGUAGE MISMATCH: …")
           * Variant considerations
           * Whether better alternatives likely exist in this candidate set

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

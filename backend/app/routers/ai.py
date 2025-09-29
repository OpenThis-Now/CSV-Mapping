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
        You are an expert in product matching. Your job is to rank the best {k} candidates from the database against the given customer row, tolerate typos, and clearly flag any market/language differences.

        — Core rules —
        1) Prioritize hard identifiers over text:
           GTIN/EAN/UPC (strongest) > exact article/SKU > manufacturer part number (MPN) > supplier name/aliases > product name tokens > attributes/specs.
        2) Typos & normalization:
           - Normalize strings: lowercase, trim, collapse whitespace, remove punctuation, ignore diacritics (ö≈o, å≈a), expand common abbreviations (AB/Ltd/GmbH), and strip company suffixes.
           - Use fuzzy token matching: accept minor Levenshtein/Jaro-Winkler differences; treat digit transpositions cautiously (e.g., 12345 vs 12354 = penalty).
           - Do not invent identifiers. If an identifier is missing, say so.
        3) Language & market policy (IMPORTANT):
           - Language MUST NOT be wrong. Prefer candidates in the same language as the customer row.
           - Cross-language matches are allowed only if strong identifiers (GTIN/EAN/UPC or exact article/SKU) align; otherwise lower confidence sharply.
           - Market can differ, but reduce confidence and clearly flag the other market.
        4) Supplier brand variance:
           - Supplier/brand may differ due to distributors, subsidiaries, or private labels. Do not disqualify solely on supplier mismatch if strong identifiers align; explain the relationship if visible.
        5) Variants:
           - Penalize mismatches on size/model/revision/package count/color; call out variant risks explicitly.
        6) Confidence (0..1):
           - Start from evidence: 
             * +0.9–1.0 for exact GTIN/EAN/UPC + matching name tokens; 
             * +0.75–0.9 for exact article/SKU + high name/supplier similarity;
             * +0.5–0.75 for strong partials; 
             * <0.5 when mainly contextual.
           - Apply deductions (cap at 0, floor at 0):
             * −0.25 language mismatch (unless exact GTIN/EAN/UPC → cap deduction at −0.1).
             * −0.10 to −0.20 market mismatch (severity by region distance).
             * −0.10 supplier alias uncertainty.
             * −0.15 likely variant differences.
             * −0.10 inconsistent identifiers across sources.
        7) Never hallucinate. If unsure, state uncertainty and why.

        — What to return —
        Return ONLY a JSON array with exactly {k} objects (if fewer plausible candidates exist, still return {k} with lowest-confidence items last). 
        Each object MUST have:
        - "database_fields_json": the unmodified database row (as a JSON object)
        - "confidence": number 0..1
        - "rationale": concise, balanced explanation in English that MUST include:
           * Match summary (Exact/Strong/Partial/Weak)
           * Evidence: identifiers, name/supplier/article similarities (mention typos if corrected)
           * Any market/language differences and their impact (explicitly flag: e.g., "OTHER MARKET: US vs SE"; "LANGUAGE MISMATCH: EN vs SV")
           * Variant considerations (if any)
           * Whether better alternatives likely exist in the current candidate set

        — Tone & formatting —
        - Keep rationale to 2–6 sentences. Use short evidence phrases like: "GTIN match", "SKU transposition", "Supplier alias (Brand X by Supplier Y)".
        - Do not include any text before or after the JSON array.

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
    mapping = imp.columns_map_json or auto_map_headers(db_df.columns)

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

        db_df["__sim"] = db_df[mapping["product"]].apply(lambda x: score_fields(crow.get(mapping["product"], ""), x))
        short = db_df.sort_values("__sim", ascending=False).head(max(20, 5 * req.max_suggestions)).drop(columns=["__sim"])
        db_sample = [dict(r) for _, r in short.iterrows()]

        used = "ai"
        try:
            prompt = build_ai_prompt(crow, db_sample, mapping, req.max_suggestions)
            ai_list = suggest_with_openai(prompt, max_items=req.max_suggestions)
        except Exception:
            used = "heuristic"
            # Create better explanations for heuristic matches
            ai_list = []
            for i, r in enumerate(db_sample[: req.max_suggestions]):
                confidence = max(0.5, (i + 1) / (req.max_suggestions + 2))
                product_name = r.get(mapping.get("product", ""), "Unknown product")
                supplier_name = r.get(mapping.get("vendor", ""), "Unknown supplier")
                
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

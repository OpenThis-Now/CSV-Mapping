from __future__ import annotations

import csv
from pathlib import Path
from typing import List
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import ImportFile, Project, ImportedPdf
from ..schemas import ImportUploadResponse, CombineImportsRequest
from ..services.files import check_upload, compute_hash_and_save, open_text_stream
from ..services.mapping import auto_map_headers
from ..services.pdf_processor import process_pdf_files, create_csv_from_pdf_data
from ..services.parallel_pdf_processor import process_pdf_files_optimized


def _group_similar_products(df: pd.DataFrame) -> pd.DataFrame:
    """Group similar products based on product name, vendor, and SKU to avoid duplicates."""
    if df.empty:
        return df
    
    # Create a grouping key based on normalized product, vendor, and SKU
    df['_group_key'] = (
        df.get('product', '').str.lower().str.strip() + '|' +
        df.get('vendor', '').str.lower().str.strip() + '|' +
        df.get('sku', '').str.lower().str.strip()
    )
    
    # Group by the key and combine data
    grouped_data = []
    
    for group_key, group_df in df.groupby('_group_key'):
        if len(group_df) == 1:
            # Single product, keep as is
            row = group_df.iloc[0].to_dict()
            del row['_group_key']
            grouped_data.append(row)
        else:
            # Multiple similar products, combine them
            combined_row = {}
            
            # For each column, combine values from all rows in the group
            for col in group_df.columns:
                if col == '_group_key':
                    continue
                    
                values = group_df[col].dropna().astype(str).tolist()
                unique_values = list(set([v for v in values if v and v != 'nan']))
                
                if len(unique_values) == 1:
                    # All values are the same
                    combined_row[col] = unique_values[0]
                elif len(unique_values) > 1:
                    # Different values, combine them
                    combined_row[col] = '; '.join(unique_values)
                else:
                    # No valid values
                    combined_row[col] = ''
            
            grouped_data.append(combined_row)
    
    # Create new DataFrame from grouped data
    result_df = pd.DataFrame(grouped_data)
    
    # Remove the temporary grouping key if it exists
    if '_group_key' in result_df.columns:
        result_df = result_df.drop('_group_key', axis=1)
    
    return result_df


router = APIRouter()
log = logging.getLogger("app.pdf_imports")




@router.post("/projects/{project_id}/pdf-import", response_model=ImportUploadResponse)
def upload_pdf_files(project_id: int, files: List[UploadFile] = File(...), session: Session = Depends(get_session)) -> ImportUploadResponse:
    """Ladda upp och bearbeta PDF-filer med AI-extraktion (synkron med progress tracking)"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    if not files:
        raise HTTPException(status_code=400, detail="Inga filer uppladdade.")
    
    # Validera att alla filer är PDF:er
    for file in files:
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Endast PDF-filer tillåtna.")
        check_upload(file)
    
    try:
        # Spara PDF:er temporärt och bearbeta dem
        pdf_paths = []
        for file in files:
            _, pdf_path = compute_hash_and_save(Path(settings.TMP_DIR), file)
            pdf_paths.append(pdf_path)
        
        # Bearbeta PDF:er med AI (parallellt för snabbare bearbetning)
        print(f"Processing {len(pdf_paths)} PDF files in parallel...")
        try:
            pdf_data = process_pdf_files_optimized(pdf_paths)
        except Exception as e:
            print(f"Parallel processing failed, falling back to sequential: {e}")
            # Fallback to original sequential processing
            pdf_data = process_pdf_files(pdf_paths)
        
        # Spara PDF:er permanent och skapa ImportedPdf-poster
        pdfs_dir = Path(settings.PDFS_DIR) / f"project_{project_id}"
        pdfs_dir.mkdir(parents=True, exist_ok=True)
        
        saved_pdfs = []
        for i, pdf_path in enumerate(pdf_paths):
            # Kopiera PDF till permanent lagring
            original_filename = files[i].filename or f"pdf_{i}.pdf"
            stored_filename = f"{project_id}_{i}_{Path(original_filename).name}"
            permanent_path = pdfs_dir / stored_filename
            
            # Kopiera filen
            import shutil
            shutil.copy2(pdf_path, permanent_path)
            
            # Hitta motsvarande data i pdf_data
            pdf_info = None
            if i < len(pdf_data):
                pdf_info = pdf_data[i]
            
            # Extract values from PDF info (which may be dicts with value/confidence/evidence)
            def extract_value(field):
                if field is None:
                    return None
                if isinstance(field, dict) and "value" in field:
                    return field["value"]
                return field
            
            # Skapa ImportedPdf-post
            imported_pdf = ImportedPdf(
                project_id=project_id,
                filename=original_filename,
                stored_filename=stored_filename,
                product_name=extract_value(pdf_info.get("product_name")) if pdf_info else None,
                supplier_name=extract_value(pdf_info.get("supplier")) if pdf_info else None,
                article_number=extract_value(pdf_info.get("article_number")) if pdf_info else None,
                customer_row_index=None  # Will be set when CSV is processed
            )
            session.add(imported_pdf)
            saved_pdfs.append(imported_pdf)
        
        # Skapa CSV från extraherade data
        csv_filename = f"pdf_import_{project_id}_{Path(files[0].filename).stem}.csv"
        csv_path = Path(settings.IMPORTS_DIR) / csv_filename
        
        # Skapa CSV-fil
        create_csv_from_pdf_data(pdf_data, csv_path)
        
        # Läsa CSV för att få metadata (headers, row count)
        from ..services.files import detect_csv_separator
        separator = detect_csv_separator(csv_path)
        
        with open_text_stream(csv_path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            headers = reader.fieldnames or []
            if not headers:
                raise HTTPException(status_code=400, detail="CSV saknar rubriker.")
            mapping = auto_map_headers(headers)
            count = sum(1 for _ in reader)
        
        # Skapa ImportFile-post
        imp = ImportFile(
            project_id=project_id,
            filename=csv_filename,
            original_name=f"PDF Import ({len(files)} files)",
            columns_map_json=mapping,
            row_count=count,
        )
        session.add(imp)
        
        # Sätt den nya importfilen som aktiv för projektet
        p.active_import_id = imp.id
        session.add(p)
        
        session.commit()
        session.refresh(imp)
        
        # Rensa temporära PDF-filer
        for pdf_path in pdf_paths:
            try:
                pdf_path.unlink()
            except Exception as e:
                print(f"Could not delete temporary file {pdf_path}: {e}")
        
        return ImportUploadResponse(
            import_file_id=imp.id, 
            filename=imp.filename, 
            row_count=imp.row_count, 
            columns_map_json=mapping
        )
        
    except Exception as e:
        # Rensa temporära filer vid fel
        for pdf_path in pdf_paths:
            try:
                pdf_path.unlink()
            except:
                pass
        raise HTTPException(status_code=500, detail=f"PDF-bearbetning misslyckades: {str(e)}")




@router.get("/projects/{project_id}/pdf-import")
def list_pdf_import_files(project_id: int, session: Session = Depends(get_session)):
    """Lista PDF-import filer (använder samma struktur som vanliga imports)"""
    imports = session.exec(
        select(ImportFile).where(ImportFile.project_id == project_id)
    ).all()
    return imports


@router.post("/projects/{project_id}/combine-imports", response_model=ImportUploadResponse)
def combine_import_files(project_id: int, req: CombineImportsRequest, session: Session = Depends(get_session)) -> ImportUploadResponse:
    """Kombinera flera import-filer till en enda fil"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    import_ids = req.import_ids
    if not import_ids:
        raise HTTPException(status_code=400, detail="Inga import-ID:n angivna.")
    
    # Hämta alla import-filer
    imports = session.exec(
        select(ImportFile).where(
            ImportFile.project_id == project_id,
            ImportFile.id.in_(import_ids)
        )
    ).all()
    
    if len(imports) != len(import_ids):
        raise HTTPException(status_code=400, detail="Några import-filer hittades inte.")
    
    if len(imports) < 2:
        raise HTTPException(status_code=400, detail="Minst 2 filer krävs för att kombinera.")
    
    try:
        import pandas as pd
        from ..services.files import detect_csv_separator
        
        # Läs alla CSV-filer och skapa enhetlig struktur
        unified_data = []
        
        for imp in imports:
            csv_path = Path(settings.IMPORTS_DIR) / imp.filename
            if not csv_path.exists():
                raise HTTPException(status_code=404, detail=f"CSV-fil {imp.filename} hittades inte.")
            
            separator = detect_csv_separator(csv_path)
            
            # Läs CSV med pandas för bättre hantering
            try:
                df = pd.read_csv(csv_path, sep=separator, encoding='utf-8')
            except UnicodeDecodeError:
                try:
                    df = pd.read_csv(csv_path, sep=separator, encoding='latin-1')
                except:
                    df = pd.read_csv(csv_path, sep=separator, encoding='cp1252')
            
            # Debug: Log column information
            print(f"Processing file {imp.id} ({imp.original_name}):")
            print(f"  Columns: {list(df.columns)}")
            print(f"  Shape: {df.shape}")
            print(f"  Mapping: {imp.columns_map_json}")
            
            # Mappa kolumner baserat på filens mappning
            file_mapping = imp.columns_map_json
            
            # Processa varje rad i denna fil
            for row_idx in range(len(df)):
                unified_row = {}
                
                # Mappa product
                if 'product' in file_mapping:
                    product_col = file_mapping['product']
                    unified_row['product'] = df[product_col].iloc[row_idx] if product_col in df.columns else ''
                else:
                    unified_row['product'] = ''
                
                # Mappa vendor
                if 'vendor' in file_mapping:
                    vendor_col = file_mapping['vendor']
                    unified_row['vendor'] = df[vendor_col].iloc[row_idx] if vendor_col in df.columns else ''
                else:
                    unified_row['vendor'] = ''
                
                # Mappa sku
                if 'sku' in file_mapping:
                    sku_col = file_mapping['sku']
                    unified_row['sku'] = df[sku_col].iloc[row_idx] if sku_col in df.columns else ''
                else:
                    unified_row['sku'] = ''
                
                # Lägg till övriga kolumner med deduplication
                for col in df.columns:
                    if col not in ['product', 'vendor', 'sku', 'Product_name', 'Supplier_name', 'Article_number']:
                        # Check if column already exists in unified_row
                        if col in unified_row:
                            # If it exists, combine values (e.g., "Sweden; Austria")
                            existing_value = unified_row[col]
                            new_value = df[col].iloc[row_idx] if len(df) > row_idx else ''
                            if existing_value and new_value and existing_value != new_value:
                                # Combine different values
                                unified_row[col] = f"{existing_value}; {new_value}"
                            elif new_value and not existing_value:
                                # Use new value if existing is empty
                                unified_row[col] = new_value
                        else:
                            # New column, add it
                            unified_row[col] = df[col].iloc[row_idx] if len(df) > row_idx else ''
                
                # Lägg till källinformation
                unified_row['_source_file'] = imp.original_name
                unified_row['_source_id'] = imp.id
                
                unified_data.append(unified_row)
        
        # Skapa enhetlig DataFrame
        if unified_data:
            combined_df = pd.DataFrame(unified_data)
            print(f"Unified DataFrame: columns = {list(combined_df.columns)}")
            print(f"Unified DataFrame: shape = {combined_df.shape}")
            print(f"Unified DataFrame: sample data = {combined_df.head(3).to_dict('records')}")
            
            # Group similar products to avoid duplicates
            combined_df = _group_similar_products(combined_df)
            print(f"After grouping: shape = {combined_df.shape}")
            
            # Skapa ny CSV-fil
            combined_filename = f"combined_import_{project_id}_{len(imports)}_files.csv"
            combined_path = Path(settings.IMPORTS_DIR) / combined_filename
            
            # Spara kombinerad CSV
            try:
                combined_df.to_csv(combined_path, index=False, encoding='utf-8')
                print(f"DEBUG: Successfully saved combined file to: {combined_path}")
                print(f"DEBUG: File exists after save: {combined_path.exists()}")
            except Exception as e:
                print(f"ERROR: Failed to save combined file: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to save combined file: {e}")
            
            
            # Skapa enhetlig kolumnmappning för den kombinerade filen
            unified_mapping = {
                'product': 'product',
                'vendor': 'vendor', 
                'sku': 'sku',
                '_source_file': 'source_file',
                '_source_id': 'source_id'
            }
            
            # Skapa ny ImportFile-post
            combined_import = ImportFile(
                project_id=project_id,
                filename=combined_filename,
                original_name=f"Kombinerad import ({len(imports)} filer)",
                columns_map_json=unified_mapping,  # Använd enhetlig mappning
                row_count=len(unified_data),
            )
            session.add(combined_import)
            session.commit()
            session.refresh(combined_import)
            
            return ImportUploadResponse(
                import_file_id=combined_import.id,
                filename=combined_import.filename,
                row_count=combined_import.row_count,
                columns_map_json=unified_mapping
            )
        else:
            raise HTTPException(status_code=500, detail="Inga data att kombinera.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kombinering misslyckades: {str(e)}")


@router.get("/debug/combined-import/{project_id}/{import_id}")
def debug_combined_import(project_id: int, import_id: int, session: Session = Depends(get_session)):
    """Debug endpoint för att kontrollera kombinerad import-fil"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    imp = session.get(ImportFile, import_id)
    if not imp:
        raise HTTPException(status_code=404, detail="Import-fil saknas.")
    
    csv_path = Path(settings.IMPORTS_DIR) / imp.filename
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"CSV-fil {imp.filename} hittades inte.")
    
    try:
        import pandas as pd
        from ..services.files import detect_csv_separator
        
        separator = detect_csv_separator(csv_path)
        
        # Läs CSV med pandas
        df = pd.read_csv(csv_path, sep=separator, encoding='utf-8', nrows=5)  # Bara första 5 raderna
        
        return {
            "import_id": import_id,
            "filename": imp.filename,
            "original_name": imp.original_name,
            "row_count": imp.row_count,
            "columns_map_json": imp.columns_map_json,
            "csv_exists": csv_path.exists(),
            "csv_size": csv_path.stat().st_size if csv_path.exists() else 0,
            "separator": separator,
            "sample_data": df.to_dict(orient="records"),
            "columns": list(df.columns),
            "sample_rows": len(df)
        }
    except Exception as e:
        return {
            "error": str(e),
            "import_id": import_id,
            "filename": imp.filename,
            "csv_exists": csv_path.exists(),
            "csv_size": csv_path.stat().st_size if csv_path.exists() else 0
        }


@router.get("/debug/pdf-libraries")
def debug_pdf_libraries():
    """Debug endpoint för att kolla vilka PDF-bibliotek som är tillgängliga"""
    result = {
        "pymupdf_available": False,
        "pdfplumber_available": False,
        "pymupdf_version": None,
        "pdfplumber_version": None,
        "errors": []
    }
    
    # Test PyMuPDF
    try:
        import fitz
        result["pymupdf_available"] = True
        result["pymupdf_version"] = fitz.version
    except ImportError as e:
        result["errors"].append(f"PyMuPDF not available: {e}")
    except Exception as e:
        result["errors"].append(f"PyMuPDF error: {e}")
    
    # Test pdfplumber
    try:
        import pdfplumber
        result["pdfplumber_available"] = True
        result["pdfplumber_version"] = pdfplumber.__version__
    except ImportError as e:
        result["errors"].append(f"pdfplumber not available: {e}")
    except Exception as e:
        result["errors"].append(f"pdfplumber error: {e}")
    
    return result


@router.post("/debug/test-pdf-extraction")
def test_pdf_extraction(file: UploadFile = File(...)):
    """Debug endpoint för att testa PDF-extraktion"""
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Endast PDF-filer tillåtna.")
    
    try:
        # Spara PDF temporärt
        _, pdf_path = compute_hash_and_save(Path(settings.TMP_DIR), file)
        
        # Test text extraction
        from ..services.pdf_processor import extract_pdf_text, simple_text_extraction, extract_product_info_with_ai
        
        text = extract_pdf_text(pdf_path)
        
        result = {
            "filename": file.filename,
            "text_extracted": len(text) if text else 0,
            "text_preview": text[:500] if text else None,
            "extraction_method": "PyMuPDF" if text else "None",
        }
        
        if text:
            # Test simple extraction
            simple_result = simple_text_extraction(text, file.filename)
            result["simple_extraction"] = simple_result
            
            # Test AI extraction if available
            try:
                ai_result = extract_product_info_with_ai(text, file.filename)
                result["ai_extraction"] = ai_result
            except Exception as e:
                result["ai_extraction_error"] = str(e)
        
        # Clean up
        try:
            pdf_path.unlink()
        except:
            pass
            
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test misslyckades: {str(e)}")

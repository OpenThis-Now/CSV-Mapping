from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import ImportFile, Project
from ..schemas import ImportUploadResponse
from ..services.files import check_upload, compute_hash_and_save, open_text_stream
from ..services.mapping import auto_map_headers
from ..services.pdf_processor import process_pdf_files, create_csv_from_pdf_data

router = APIRouter()


@router.post("/projects/{project_id}/pdf-import", response_model=ImportUploadResponse)
def upload_pdf_files(project_id: int, files: List[UploadFile] = File(...), session: Session = Depends(get_session)) -> ImportUploadResponse:
    """Ladda upp och bearbeta PDF-filer med AI-extraktion"""
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
        
        # Bearbeta PDF:er med AI
        print(f"Processing {len(pdf_paths)} PDF files...")
        pdf_data = process_pdf_files(pdf_paths)
        
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
def combine_import_files(project_id: int, import_ids: List[int], session: Session = Depends(get_session)) -> ImportUploadResponse:
    """Kombinera flera import-filer till en enda fil"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
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
        
        # Läs alla CSV-filer och kombinera dem
        combined_data = []
        total_rows = 0
        
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
            
            # Lägg till källinformation
            df['_source_file'] = imp.original_name
            df['_source_id'] = imp.id
            
            combined_data.append(df)
            total_rows += len(df)
        
        # Kombinera alla dataframes
        if combined_data:
            combined_df = pd.concat(combined_data, ignore_index=True)
            
            # Skapa ny CSV-fil
            combined_filename = f"combined_import_{project_id}_{len(imports)}_files.csv"
            combined_path = Path(settings.IMPORTS_DIR) / combined_filename
            
            # Spara kombinerad CSV
            combined_df.to_csv(combined_path, index=False, encoding='utf-8')
            
            # Skapa mapping för kolumner (använd första filens mapping som bas)
            base_mapping = imports[0].columns_map_json
            for imp in imports[1:]:
                # Lägg till eventuella nya kolumner från andra filer
                for key, value in imp.columns_map_json.items():
                    if key not in base_mapping:
                        base_mapping[key] = value
            
            # Lägg till mapping för de nya kolumnerna
            base_mapping['_source_file'] = 'source_file'
            base_mapping['_source_id'] = 'source_id'
            
            # Skapa ny ImportFile-post
            combined_import = ImportFile(
                project_id=project_id,
                filename=combined_filename,
                original_name=f"Kombinerad import ({len(imports)} filer)",
                columns_map_json=base_mapping,
                row_count=total_rows,
            )
            session.add(combined_import)
            session.commit()
            session.refresh(combined_import)
            
            return ImportUploadResponse(
                import_file_id=combined_import.id,
                filename=combined_import.filename,
                row_count=combined_import.row_count,
                columns_map_json=base_mapping
            )
        else:
            raise HTTPException(status_code=500, detail="Inga data att kombinera.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kombinering misslyckades: {str(e)}")


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

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

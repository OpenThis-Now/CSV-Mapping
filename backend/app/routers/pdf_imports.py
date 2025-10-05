from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import List
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, BackgroundTasks
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import ImportFile, Project, PDFProcessingRun
from ..schemas import ImportUploadResponse, CombineImportsRequest
from ..services.files import check_upload, compute_hash_and_save, open_text_stream
from ..services.mapping import auto_map_headers
from ..services.pdf_processor import process_pdf_files, create_csv_from_pdf_data

router = APIRouter()
log = logging.getLogger("app.pdf_imports")


async def process_pdf_files_background(
    processing_run_id: int, 
    project_id: int, 
    pdf_paths: List[Path], 
    csv_filename: str
):
    """Background task to process PDF files with progress tracking"""
    from ..db import get_session
    
    # Get a new database session for background processing
    session = next(get_session())
    
    try:
        # Update status to processing
        processing_run = session.get(PDFProcessingRun, processing_run_id)
        if not processing_run:
            log.error(f"Processing run {processing_run_id} not found")
            return
        
        processing_run.status = "running"
        processing_run.total_files = len(pdf_paths)
        session.commit()
        
        log.info(f"Starting background PDF processing for {len(pdf_paths)} files")
        
        all_products = []
        successful_files = 0
        failed_files = 0
        
        for i, pdf_path in enumerate(pdf_paths):
            filename = pdf_path.name
            log.info(f"Processing PDF {i+1}/{len(pdf_paths)}: {filename}")
            
            # Update current file being processed
            processing_run.current_file = filename
            processing_run.processed_files = i
            session.commit()
            
            try:
                # Extract text from PDF
                from ..services.pdf_processor import extract_pdf_text, extract_product_info_with_ai, create_fallback_entry
                
                text = extract_pdf_text(pdf_path)
                
                if not text:
                    log.warning(f"No text extracted from {filename} - creating fallback entry")
                    product_info = create_fallback_entry(filename)
                    failed_files += 1
                else:
                    log.info(f"Extracted {len(text)} characters from {filename}")
                    # Use AI to extract product information
                    product_info = extract_product_info_with_ai(text, filename)
                    successful_files += 1
                
                all_products.append(product_info)
                log.info(f"Processed {filename}: status = {product_info.get('extraction_status', 'unknown')}")
                
            except Exception as e:
                log.error(f"Error processing {filename}: {e}")
                # Create fallback entry for this file
                from ..services.pdf_processor import create_fallback_entry
                fallback_info = create_fallback_entry(filename)
                all_products.append(fallback_info)
                failed_files += 1
            
            # Clean up temporary PDF file
            try:
                pdf_path.unlink()
            except Exception as e:
                log.warning(f"Could not delete temporary file {pdf_path}: {e}")
        
        # Create CSV from extracted data
        csv_path = Path(settings.IMPORTS_DIR) / csv_filename
        from ..services.pdf_processor import create_csv_from_pdf_data
        create_csv_from_pdf_data(all_products, csv_path)
        
        # Read CSV for metadata
        from ..services.files import detect_csv_separator
        separator = detect_csv_separator(csv_path)
        
        with open_text_stream(csv_path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            headers = reader.fieldnames or []
            if not headers:
                raise Exception("CSV saknar rubriker.")
            mapping = auto_map_headers(headers)
            count = sum(1 for _ in reader)
        
        # Create ImportFile record
        imp = ImportFile(
            project_id=project_id,
            filename=csv_filename,
            original_name=f"PDF Import ({len(pdf_paths)} files)",
            columns_map_json=mapping,
            row_count=count,
        )
        session.add(imp)
        
        # Set the new import file as active for the project
        project = session.get(Project, project_id)
        if project:
            project.active_import_id = imp.id
            session.add(project)
        
        # Update processing run status
        processing_run.status = "completed"
        processing_run.finished_at = datetime.utcnow()
        processing_run.successful_files = successful_files
        processing_run.failed_files = failed_files
        processing_run.processed_files = len(pdf_paths)
        session.commit()
        
        log.info(f"Completed PDF processing: {successful_files} successful, {failed_files} failed, {count} products extracted")
        
    except Exception as e:
        log.error(f"PDF processing failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Update processing run status to failed
        processing_run = session.get(PDFProcessingRun, processing_run_id)
        if processing_run:
            processing_run.status = "failed"
            processing_run.finished_at = datetime.utcnow()
            processing_run.error_message = str(e)
            session.commit()
        
        # Clean up temporary files
        for pdf_path in pdf_paths:
            try:
                pdf_path.unlink()
            except:
                pass
    finally:
        session.close()


@router.post("/projects/{project_id}/pdf-import")
async def upload_pdf_files(
    project_id: int, 
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...), 
    session: Session = Depends(get_session)
):
    """Ladda upp och bearbeta PDF-filer med AI-extraktion (asynkron med progress tracking)"""
    from datetime import datetime
    
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
        # Create processing run record
        processing_run = PDFProcessingRun(
            project_id=project_id,
            total_files=len(files),
            status="uploading"
        )
        session.add(processing_run)
        session.commit()
        session.refresh(processing_run)
        
        # Spara PDF:er temporärt
        pdf_paths = []
        for file in files:
            _, pdf_path = compute_hash_and_save(Path(settings.TMP_DIR), file)
            pdf_paths.append(pdf_path)
        
        # Skapa CSV-filnamn
        csv_filename = f"pdf_import_{project_id}_{Path(files[0].filename).stem}.csv"
        
        # Start background processing
        background_tasks.add_task(
            process_pdf_files_background,
            processing_run.id,
            project_id,
            pdf_paths,
            csv_filename
        )
        
        return {
            "processing_run_id": processing_run.id,
            "status": "processing_started",
            "total_files": len(files),
            "message": f"PDF processing started for {len(files)} files"
        }
        
    except Exception as e:
        log.error(f"Failed to start PDF processing: {e}")
        raise HTTPException(status_code=500, detail=f"PDF-bearbetning misslyckades: {str(e)}")


@router.get("/projects/{project_id}/pdf-import/status")
def get_pdf_processing_status(project_id: int, session: Session = Depends(get_session)):
    """Get current PDF processing status for a project"""
    # Find the most recent processing run for this project
    processing_run = session.exec(
        select(PDFProcessingRun)
        .where(PDFProcessingRun.project_id == project_id)
        .order_by(PDFProcessingRun.started_at.desc())
        .limit(1)
    ).first()
    
    if not processing_run:
        return {
            "has_active_processing": False,
            "status": None
        }
    
    return {
        "has_active_processing": processing_run.status in ["uploading", "running"],
        "processing_run_id": processing_run.id,
        "status": processing_run.status,
        "total_files": processing_run.total_files,
        "processed_files": processing_run.processed_files,
        "successful_files": processing_run.successful_files,
        "failed_files": processing_run.failed_files,
        "current_file": processing_run.current_file,
        "progress_percentage": round((processing_run.processed_files / processing_run.total_files * 100) if processing_run.total_files > 0 else 0, 1),
        "started_at": processing_run.started_at.isoformat() if processing_run.started_at else None,
        "finished_at": processing_run.finished_at.isoformat() if processing_run.finished_at else None,
        "error_message": processing_run.error_message
    }


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
                
                # Lägg till övriga kolumner
                for col in df.columns:
                    if col not in ['product', 'vendor', 'sku', 'Product_name', 'Supplier_name', 'Article_number']:
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

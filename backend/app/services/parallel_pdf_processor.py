from __future__ import annotations

import asyncio
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from ..openai_client import suggest_with_openai
from .pdf_processor import extract_pdf_text, simple_text_extraction, extract_product_info_with_ai

log = logging.getLogger("app.parallel_pdf_processor")


def process_single_pdf_with_ai(pdf_path: Path, api_key_index: int = 0) -> Dict[str, Any]:
    """Process a single PDF with AI using a specific API key"""
    try:
        # Extract text from PDF
        text = extract_pdf_text(pdf_path)
        if not text:
            return {
                "filename": pdf_path.name,
                "success": False,
                "error": "No text extracted from PDF",
                "api_key_index": api_key_index
            }
        
        # Try simple extraction first
        simple_result = simple_text_extraction(text, pdf_path.name)
        
        # Try AI extraction with specific API key
        try:
            ai_result = extract_product_info_with_ai(text, pdf_path.name, api_key_index)
            # Return in the format expected by create_csv_from_pdf_data
            return ai_result
        except Exception as ai_error:
            log.warning(f"AI extraction failed for {pdf_path.name} with key {api_key_index}: {ai_error}")
            # Return simple extraction result in the expected format
            return simple_result
            
    except Exception as e:
        log.error(f"Error processing PDF {pdf_path.name}: {e}")
        # Return a fallback result in the expected format
        return {
            "filename": pdf_path.name,
            "product_name": {"value": ""},
            "company_name": {"value": ""},
            "article_number": {"value": ""},
            "authored_market": {"value": ""},
            "language": {"value": ""},
            "extraction_status": "failed",
            "error": str(e)
        }


def process_pdf_files_parallel(pdf_paths: List[Path], max_workers: int = 10) -> List[Dict[str, Any]]:
    """Process multiple PDF files in parallel using multiple API keys"""
    log.info(f"Starting parallel processing of {len(pdf_paths)} PDF files with {max_workers} workers")
    
    # Create tasks with round-robin API key assignment
    tasks = []
    for i, pdf_path in enumerate(pdf_paths):
        api_key_index = i % max_workers  # Distribute across available API keys
        tasks.append((pdf_path, api_key_index))
    
    # Process in parallel using ThreadPoolExecutor
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(process_single_pdf_with_ai, pdf_path, api_key_index): (pdf_path, api_key_index)
            for pdf_path, api_key_index in tasks
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_task):
            pdf_path, api_key_index = future_to_task[future]
            try:
                result = future.result()
                results.append(result)
                
                if result.get("extraction_status") != "failed":
                    log.info(f"Completed: {result['filename']} (API key {api_key_index})")
                else:
                    log.error(f"Failed: {result['filename']} - {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                log.error(f"Exception processing {pdf_path.name}: {e}")
                results.append({
                    "filename": pdf_path.name,
                    "product_name": {"value": ""},
                    "company_name": {"value": ""},
                    "article_number": {"value": ""},
                    "authored_market": {"value": ""},
                    "language": {"value": ""},
                    "extraction_status": "failed",
                    "error": f"Exception: {str(e)}"
                })
    
    # Sort results by original order
    results.sort(key=lambda x: pdf_paths.index(Path(x["filename"])) if Path(x["filename"]) in pdf_paths else 999)
    
    successful = sum(1 for r in results if r.get("extraction_status") != "failed")
    failed = len(results) - successful
    
    log.info(f"Parallel PDF processing completed: {successful} successful, {failed} failed")
    
    return results


async def process_pdf_files_async(pdf_paths: List[Path], max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """Process multiple PDF files asynchronously"""
    log.info(f"Starting async processing of {len(pdf_paths)} PDF files with max {max_concurrent} concurrent")
    
    # Create semaphore to limit concurrent processing
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_semaphore(pdf_path: Path, api_key_index: int) -> Dict[str, Any]:
        async with semaphore:
            # Run the synchronous processing in a thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, 
                process_single_pdf_with_ai, 
                pdf_path, 
                api_key_index
            )
    
    # Create tasks with round-robin API key assignment
    tasks = []
    for i, pdf_path in enumerate(pdf_paths):
        api_key_index = i % max_concurrent
        task = process_with_semaphore(pdf_path, api_key_index)
        tasks.append(task)
    
    # Process all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle exceptions
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "filename": pdf_paths[i].name,
                "success": False,
                "error": f"Exception: {str(result)}",
                "api_key_index": i % max_concurrent
            })
        else:
            processed_results.append(result)
    
    successful = sum(1 for r in processed_results if r.get("extraction_status") != "failed")
    failed = len(processed_results) - successful
    
    log.info(f"Async PDF processing completed: {successful} successful, {failed} failed")
    
    return processed_results


def get_available_api_keys() -> int:
    """Get the number of available API keys"""
    from ..config import settings
    
    api_keys = [
        settings.OPENAI_API_KEY,
        getattr(settings, 'OPENAI_API_KEY_2', None),
        getattr(settings, 'OPENAI_API_KEY_3', None),
        getattr(settings, 'OPENAI_API_KEY_4', None),
        getattr(settings, 'OPENAI_API_KEY_5', None),
        getattr(settings, 'OPENAI_API_KEY_6', None),
        getattr(settings, 'OPENAI_API_KEY_7', None),
        getattr(settings, 'OPENAI_API_KEY_8', None),
        getattr(settings, 'OPENAI_API_KEY_9', None),
        getattr(settings, 'OPENAI_API_KEY_10', None),
    ]
    
    available_keys = [key for key in api_keys if key]
    return len(available_keys)


def process_pdf_files_optimized(pdf_paths: List[Path]) -> List[Dict[str, Any]]:
    """Optimized PDF processing that automatically determines the best approach"""
    available_keys = get_available_api_keys()
    
    if available_keys == 0:
        raise RuntimeError("No API keys available")
    
    # Use parallel processing with available API keys
    max_workers = min(available_keys, len(pdf_paths), 10)  # Cap at 10 workers
    
    log.info(f"Processing {len(pdf_paths)} PDFs with {max_workers} workers using {available_keys} API keys")
    
    start_time = datetime.now()
    results = process_pdf_files_parallel(pdf_paths, max_workers)
    end_time = datetime.now()
    
    duration = (end_time - start_time).total_seconds()
    log.info(f"PDF processing completed in {duration:.2f} seconds")
    
    # Debug: Log sample results
    for i, result in enumerate(results[:3]):  # Log first 3 results
        log.info(f"Sample result {i+1}: {result.get('filename', 'unknown')} - status: {result.get('extraction_status', 'unknown')}")
        if result.get('product_name', {}).get('value'):
            log.info(f"  Product: {result['product_name']['value']}")
        if result.get('company_name', {}).get('value'):
            log.info(f"  Company: {result['company_name']['value']}")
        if result.get('article_number', {}).get('value'):
            log.info(f"  Article: {result['article_number']['value']}")
    
    return results

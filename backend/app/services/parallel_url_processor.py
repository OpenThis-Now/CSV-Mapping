from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..openai_client import suggest_with_openai
from .pdf_processor import extract_pdf_data_with_ai

log = logging.getLogger("app.parallel_url_processor")


def process_single_url_with_ai(url: str, api_key_index: int = 0) -> Optional[Dict[str, Any]]:
    """Process a single URL with AI using a specific API key"""
    try:
        # Extract PDF data with timeout protection
        pdf_data = extract_pdf_data_with_ai(url, api_key_index)
        
        if pdf_data and len(pdf_data) > 0:
            return pdf_data[0]
        else:
            log.warning(f"No data extracted from URL: {url}")
            return None
            
    except Exception as e:
        log.error(f"Error processing URL {url}: {str(e)}")
        return None


def process_urls_parallel(urls: List[str], max_workers: int = 10) -> List[Optional[Dict[str, Any]]]:
    """Process multiple URLs in parallel using multiple API keys"""
    # If we have fewer API keys than workers, use more workers per API key
    available_keys = get_available_api_keys()
    if available_keys < max_workers:
        # Use fewer workers per API key for better quality (reduce from 10 to 3)
        # With multiple API keys, use up to 3 workers per API key for better quality
        max_workers = min(available_keys * 3, len(urls), 30)  # Up to 3 workers per API key, max 30 total
    
    log.info(f"Starting parallel processing of {len(urls)} URLs with {max_workers} workers using {available_keys} API keys")
    
    # Create tasks with round-robin API key assignment
    tasks = []
    api_key_usage = {}
    for i, url in enumerate(urls):
        api_key_index = i % available_keys  # Distribute across available API keys
        tasks.append((url, api_key_index))
        api_key_usage[api_key_index] = api_key_usage.get(api_key_index, 0) + 1
    
    log.info(f"API key distribution: {api_key_usage}")
    
    # Process in parallel using ThreadPoolExecutor
    results = []
    log.info(f"Submitting {len(tasks)} tasks to ThreadPoolExecutor with {max_workers} workers")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(process_single_url_with_ai, url, api_key_index): (url, api_key_index)
            for url, api_key_index in tasks
        }
        
        log.info(f"All {len(future_to_task)} tasks submitted, waiting for completion...")
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_task):
            url, api_key_index = future_to_task[future]
            try:
                result = future.result()
                results.append(result)
                
                if result:
                    log.info(f"Completed: {url} (API key {api_key_index})")
                else:
                    log.warning(f"No data from: {url}")
                    
            except Exception as e:
                log.error(f"Exception processing {url}: {e}")
                results.append(None)
    
    # Sort results by original order
    results.sort(key=lambda x: urls.index(x["url"]) if x and "url" in x else 999)
    
    successful = sum(1 for r in results if r is not None)
    failed = len(results) - successful
    
    log.info(f"Parallel URL processing completed: {successful} successful, {failed} failed")
    
    return results


async def process_urls_async(urls: List[str], max_concurrent: int = 10) -> List[Optional[Dict[str, Any]]]:
    """Process multiple URLs asynchronously"""
    log.info(f"Starting async processing of {len(urls)} URLs with max {max_concurrent} concurrent")
    
    # Create semaphore to limit concurrent processing
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_semaphore(url: str, api_key_index: int) -> Optional[Dict[str, Any]]:
        async with semaphore:
            # Run the synchronous processing in a thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, 
                process_single_url_with_ai, 
                url, 
                api_key_index
            )
    
    # Create tasks with round-robin API key assignment
    tasks = []
    for i, url in enumerate(urls):
        api_key_index = i % max_concurrent
        task = process_with_semaphore(url, api_key_index)
        tasks.append(task)
    
    # Process all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle exceptions
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            log.error(f"Exception processing URL {urls[i]}: {result}")
            processed_results.append(None)
        else:
            processed_results.append(result)
    
    successful = sum(1 for r in processed_results if r is not None)
    failed = len(processed_results) - successful
    
    log.info(f"Async URL processing completed: {successful} successful, {failed} failed")
    
    return processed_results


def get_available_api_keys() -> int:
    """Get the number of available API keys"""
    from ..config import settings
    
    api_keys = [
        settings.OPENAI_API_KEY,
        getattr(settings, 'OPENAI_API_KEY2', None),
        getattr(settings, 'OPENAI_API_KEY3', None),
        getattr(settings, 'OPENAI_API_KEY4', None),
        getattr(settings, 'OPENAI_API_KEY5', None),
        getattr(settings, 'OPENAI_API_KEY6', None),
        getattr(settings, 'OPENAI_API_KEY7', None),
        getattr(settings, 'OPENAI_API_KEY8', None),
        getattr(settings, 'OPENAI_API_KEY9', None),
        getattr(settings, 'OPENAI_API_KEY10', None),
    ]
    
    available_keys = [key for key in api_keys if key]
    return len(available_keys)


def process_urls_optimized(urls: List[str]) -> List[Optional[Dict[str, Any]]]:
    """Optimized URL processing that automatically determines the best approach"""
    available_keys = get_available_api_keys()
    
    if available_keys == 0:
        raise RuntimeError("No API keys available")
    
    # Use parallel processing with available API keys - prioritize quality over speed
    max_workers = min(available_keys * 2, len(urls), 20)  # Up to 2 workers per API key, max 20 total
    
    log.info(f"Processing {len(urls)} URLs with {max_workers} workers using {available_keys} API keys")
    
    start_time = datetime.now()
    results = process_urls_parallel(urls, max_workers)
    end_time = datetime.now()
    
    duration = (end_time - start_time).total_seconds()
    log.info(f"URL processing completed in {duration:.2f} seconds")
    
    return results

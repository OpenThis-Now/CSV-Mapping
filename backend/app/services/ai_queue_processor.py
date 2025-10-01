"""
AI Queue Processor - Background task processor for AI analysis queue
"""
import asyncio
import logging
from typing import List, Optional
from sqlmodel import Session, select
from ..db import get_session
from ..models import MatchResult, AiSuggestion, Project
from ..openai_client import suggest_with_openai
from ..services.mapping import auto_map_headers
from ..match_engine.scoring import score_fields
from ..config import settings
import pandas as pd
from pathlib import Path

log = logging.getLogger("app.ai_queue")


class AIQueueProcessor:
    def __init__(self):
        self.is_processing = False
        self.current_batch = []
        self.max_concurrent = 10  # Process max 10 products at once (increased from 3)
        
    async def start_processing(self, project_id: int):
        """Start processing the AI queue for a project."""
        if self.is_processing:
            log.info(f"AI queue processor already running for project {project_id}")
            return
            
        self.is_processing = True
        log.info(f"Starting AI queue processing for project {project_id}")
        
        try:
            await self._process_queue(project_id)
        except Exception as e:
            log.error(f"Error in AI queue processing: {e}")
        finally:
            self.is_processing = False
            log.info(f"AI queue processing completed for project {project_id}")
    
    async def _process_queue(self, project_id: int):
        """Process the AI queue for a project."""
        import asyncio
        
        # Keep processing until no more queued products
        while True:
            session = next(get_session())
            
            try:
                # Get queued products
                queued_products = session.exec(
                    select(MatchResult).where(
                        MatchResult.project_id == project_id,
                        MatchResult.decision == "sent_to_ai",
                        MatchResult.ai_status == "queued"
                    ).limit(self.max_concurrent)
                ).all()
                
                if not queued_products:
                    log.info(f"No more queued products found for project {project_id}")
                    break
                
                log.info(f"Processing {len(queued_products)} products for project {project_id}")
                
                # Mark as processing
                for product in queued_products:
                    product.ai_status = "processing"
                    session.add(product)
                session.commit()
                
                # Process products in parallel using asyncio.gather
                tasks = []
                for product in queued_products:
                    task = asyncio.create_task(self._process_single_product(product, session))
                    tasks.append(task)
                
                # Wait for all tasks to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log results
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        log.error(f"Error processing product {queued_products[i].customer_row_index}: {result}")
                        queued_products[i].ai_status = "failed"
                        session.add(queued_products[i])
                    else:
                        log.info(f"Successfully processed product {queued_products[i].customer_row_index}")
                
                session.commit()
                
            finally:
                session.close()
            
            # Small delay before checking for more products
            await asyncio.sleep(1)
    
    async def _process_single_product(self, product: MatchResult, session: Session):
        """Process a single product through AI analysis."""
        log.info(f"Processing product {product.customer_row_index} for project {product.match_run_id}")
        
        try:
            # Get project and database info
            project = session.get(Project, product.match_run.project_id)
            if not project or not project.active_database_id:
                raise Exception("No active database found")
            
            # Load customer and database data
            customer_data, database_data = await self._load_data(project, session)
            
            # Get customer row
            customer_row = customer_data.iloc[product.customer_row_index].to_dict()
            
            # Find best database matches
            database_matches = await self._find_database_matches(
                customer_row, database_data, product.customer_row_index
            )
            
            # Generate AI suggestions
            suggestions = await self._generate_ai_suggestions(
                customer_row, database_matches, product.customer_row_index, project.id
            )
            
            # Save suggestions to database
            for suggestion in suggestions:
                ai_suggestion = AiSuggestion(
                    project_id=project.id,
                    customer_row_index=product.customer_row_index,
                    rank=suggestion["rank"],
                    database_fields_json=suggestion["database_fields_json"],
                    confidence=suggestion["confidence"],
                    rationale=suggestion["rationale"],
                    source="ai"
                )
                session.add(ai_suggestion)
            
            # Update product status
            product.ai_status = "completed"
            session.add(product)
            session.commit()
            
            log.info(f"Completed AI analysis for product {product.customer_row_index}")
            
        except Exception as e:
            log.error(f"Error in AI analysis for product {product.customer_row_index}: {e}")
            product.ai_status = "failed"
            session.add(product)
            session.commit()
            raise
    
    async def _load_data(self, project: Project, session: Session):
        """Load customer and database data."""
        from ..models import ImportFile, DatabaseCatalog
        
        # Get import file
        imp = session.exec(
            select(ImportFile).where(ImportFile.project_id == project.id).order_by(ImportFile.created_at.desc())
        ).first()
        
        if not imp:
            raise Exception("No import file found")
        
        # Get database
        db = session.get(DatabaseCatalog, project.active_database_id)
        if not db:
            raise Exception("No active database found")
        
        # Load CSV files
        import pandas as pd
        from ..services.files import detect_csv_separator
        
        # Detect separators
        imp_separator = detect_csv_separator(Path(settings.IMPORTS_DIR) / imp.filename)
        db_separator = detect_csv_separator(Path(settings.DATABASES_DIR) / db.filename)
        
        # Read customer data
        customer_data = pd.read_csv(
            Path(settings.IMPORTS_DIR) / imp.filename, 
            dtype=str, 
            keep_default_na=False, 
            sep=imp_separator
        )
        
        # Read database data
        database_data = pd.read_csv(
            Path(settings.DATABASES_DIR) / db.filename, 
            dtype=str, 
            keep_default_na=False, 
            sep=db_separator
        )
        
        return customer_data, database_data
    
    async def _find_database_matches(self, customer_row: dict, database_data, customer_row_index: int):
        """Find the best database matches for a customer row."""
        # Use the same logic as the existing AI suggest endpoint
        from ..services.mapping import auto_map_headers
        
        # Auto-map headers
        db_mapping = auto_map_headers(database_data.columns)
        
        # Score products
        database_data["__sim"] = database_data[db_mapping["product"]].apply(
            lambda x: score_fields(customer_row.get("Product_name", ""), x)
        )
        
        # Get top matches
        top_matches = database_data.sort_values("__sim", ascending=False).head(20).drop(columns=["__sim"])
        
        return [dict(row) for _, row in top_matches.iterrows()]
    
    async def _generate_ai_suggestions(self, customer_row: dict, database_matches: List[dict], 
                                     customer_row_index: int, project_id: int):
        """Generate AI suggestions for a customer row."""
        from ..routers.ai import build_ai_prompt
        from ..services.mapping import auto_map_headers
        
        # Use the same AI logic as the existing endpoint
        try:
            prompt = build_ai_prompt(customer_row, database_matches, {}, 3)
            ai_suggestions = suggest_with_openai(prompt, max_items=3)
            
            return ai_suggestions
        except Exception as e:
            log.error(f"AI suggestion failed for row {customer_row_index}: {e}")
            # Fallback to heuristic suggestions
            suggestions = []
            for i, match in enumerate(database_matches[:3]):
                confidence = max(0.5, (i + 1) / 4)
                suggestions.append({
                    "database_fields_json": match,
                    "confidence": confidence,
                    "rationale": f"Heuristic match #{i+1} with {confidence:.0%} confidence"
                })
            return suggestions


# Global processor instance
ai_processor = AIQueueProcessor()


async def process_ai_queue(project_id: int):
    """Process the AI queue for a project."""
    await ai_processor.start_processing(project_id)

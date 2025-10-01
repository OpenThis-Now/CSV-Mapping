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
        self.max_concurrent = 3  # Process max 3 products at once
        
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
                log.info(f"No queued products found for project {project_id}")
                return
            
            log.info(f"Processing {len(queued_products)} products for project {project_id}")
            
            # Mark as processing
            for product in queued_products:
                product.ai_status = "processing"
                session.add(product)
            session.commit()
            
            # Process each product
            for product in queued_products:
                try:
                    await self._process_single_product(product, session)
                except Exception as e:
                    log.error(f"Error processing product {product.customer_row_index}: {e}")
                    product.ai_status = "failed"
                    session.add(product)
                    session.commit()
            
        finally:
            session.close()
    
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
        # This is a simplified version - you'd need to implement the full data loading logic
        # from the existing AI suggest endpoint
        pass
    
    async def _find_database_matches(self, customer_row: dict, database_data, customer_row_index: int):
        """Find the best database matches for a customer row."""
        # This is a simplified version - you'd need to implement the full matching logic
        pass
    
    async def _generate_ai_suggestions(self, customer_row: dict, database_matches: List[dict], 
                                     customer_row_index: int, project_id: int):
        """Generate AI suggestions for a customer row."""
        # This is a simplified version - you'd need to implement the full AI logic
        pass


# Global processor instance
ai_processor = AIQueueProcessor()


async def process_ai_queue(project_id: int):
    """Process the AI queue for a project."""
    await ai_processor.start_processing(project_id)

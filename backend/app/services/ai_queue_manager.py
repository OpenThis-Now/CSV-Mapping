"""
AI Queue Manager for handling pause/resume functionality
"""
import threading
import time
import logging
from typing import Dict, Optional
from sqlmodel import Session, select
from ..models import MatchResult, MatchRun
from ..db import get_session

log = logging.getLogger("app.ai_queue_manager")

class AIQueueManager:
    """Global AI queue manager for pause/resume functionality"""
    
    def __init__(self):
        self.active_threads: Dict[int, threading.Thread] = {}
        self.paused_projects: set = set()
        self.lock = threading.Lock()
    
    def is_paused(self, project_id: int) -> bool:
        """Check if AI queue is paused for a project"""
        with self.lock:
            return project_id in self.paused_projects
    
    def pause(self, project_id: int):
        """Pause AI queue for a project"""
        with self.lock:
            self.paused_projects.add(project_id)
            log.info(f"AI queue paused for project {project_id}")
    
    def resume(self, project_id: int):
        """Resume AI queue for a project"""
        with self.lock:
            self.paused_projects.discard(project_id)
            log.info(f"AI queue resumed for project {project_id}")
    
    def register_thread(self, project_id: int, thread: threading.Thread):
        """Register an active AI processing thread"""
        with self.lock:
            self.active_threads[project_id] = thread
    
    def unregister_thread(self, project_id: int):
        """Unregister an active AI processing thread"""
        with self.lock:
            self.active_threads.pop(project_id, None)
    
    def wait_if_paused(self, project_id: int):
        """Wait if project is paused, return True if should continue"""
        while self.is_paused(project_id):
            time.sleep(1)
        return True

# Global instance
ai_queue_manager = AIQueueManager()

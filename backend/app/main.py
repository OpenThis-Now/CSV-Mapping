from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings, ensure_storage_dirs
from .db import create_db_and_tables
from .utils.logging import install_logging, RequestIDMiddleware
from .routers import databases, projects, imports, match, approve, ai, export, projects_list, project_databases, pdf_imports, url_enhancement, rejected_products, suppliers
from .version import __version__


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    install_logging()
    ensure_storage_dirs()
    create_db_and_tables()
    logging.getLogger("app").info(
        "Mapping Bridge starting", extra={"event": "startup", "version": __version__}
    )
    yield
    # Shutdown
    logging.getLogger("app").info("Mapping Bridge shutdown", extra={"event": "shutdown"})


app = FastAPI(
    title="Mapping Bridge",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# Middlewares
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(databases.router, prefix="/api", tags=["databases"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(imports.router, prefix="/api", tags=["imports"])
app.include_router(match.router, prefix="/api", tags=["match"])
app.include_router(approve.router, prefix="/api", tags=["approve"])
app.include_router(ai.router, prefix="/api", tags=["ai"])
app.include_router(export.router, prefix="/api", tags=["export"])
app.include_router(projects_list.router, prefix="/api", tags=["projects"])
app.include_router(project_databases.router, prefix="/api", tags=["project-databases"])
app.include_router(pdf_imports.router, prefix="/api", tags=["pdf-imports"])
app.include_router(url_enhancement.router, prefix="/api", tags=["url-enhancement"])
app.include_router(rejected_products.router, prefix="/api", tags=["rejected-products"])
app.include_router(suppliers.router, prefix="/api", tags=["suppliers"])


@app.get("/api/health")
def health() -> dict[str, str]:
    """Basic health check."""
    return {"status": "ok", "version": __version__}

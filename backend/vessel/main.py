"""FastAPI application entrypoint for Hermes."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vessel.api.routes.definitions import router as definitions_router
from vessel.api.routes.instances import router as instances_router
from vessel.api.routes.pipelines import router as pipelines_router
from vessel.api.routes.system import router as system_router
from vessel.api.routes.work_items import router as work_items_router
from vessel.api.websocket import router as websocket_router
from vessel.domain.models.base import Base
from vessel.infrastructure.database.session import async_engine, async_session_factory
from vessel.workers.monitoring_worker import MonitoringWorker
from vessel.workers.processing_worker import ProcessingWorker

logger = logging.getLogger(__name__)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Background workers
_monitoring_worker: MonitoringWorker | None = None
_processing_worker: ProcessingWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    global _monitoring_worker, _processing_worker

    # Startup
    logger.info("Hermes starting up...")

    # Initialize database tables
    async with async_engine.begin() as conn:
        # Import all models so they are registered with Base
        import vessel.domain.models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")

    # Start background workers
    _monitoring_worker = MonitoringWorker(async_session_factory)
    _processing_worker = ProcessingWorker(async_session_factory)

    await _monitoring_worker.start()
    await _processing_worker.start()
    logger.info("Background workers started")

    yield

    # Shutdown
    logger.info("Hermes shutting down...")
    if _monitoring_worker:
        await _monitoring_worker.stop()
    if _processing_worker:
        await _processing_worker.stop()
    await async_engine.dispose()
    logger.info("Hermes shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Hermes",
        description="Lightweight data processing platform with per-job tracking",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(definitions_router)
    app.include_router(instances_router)
    app.include_router(pipelines_router)
    app.include_router(work_items_router)
    app.include_router(system_router)
    app.include_router(websocket_router)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": "Hermes",
            "tagline": "The messenger for your data.",
            "version": "0.1.0",
            "docs": "/docs",
        }

    return app


# Application instance for uvicorn
app = create_app()

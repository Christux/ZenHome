"""FastAPI entry point for ZenHome.

This module configures the application lifecycle, registers the Vue/JS frontend
routes, and starts the background daemon that creates scheduled occurrences and
notifications.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .database import initialize_database
from .daemon import daemon_loop
from .globals import PROJECT_DIR
from .logging_config import configure_logging
from .web_routes import public_router, router as web_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize the app services at startup and shut them down cleanly.

    The function configures structured logging, ensures the SQLite schema and demo
    data exist, starts the background daemon, and then stops that worker during
    application shutdown.
    """
    configure_logging()
    logger.info("Starting ZenHome")
    initialize_database()
    logger.info("Database initialized")
    stop_event = asyncio.Event()
    daemon_task = asyncio.create_task(daemon_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await daemon_task
        logger.info("Stopping ZenHome")


logger = logging.getLogger(__name__)


app = FastAPI(
    title="ZenHome",
    description="Notes, checklists and tasks.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(web_router)
app.include_router(public_router)
app.mount("/static", StaticFiles(directory=PROJECT_DIR / "static"), name="static")

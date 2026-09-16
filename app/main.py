"""Point d'entrée FastAPI pour ZenHome."""

from __future__ import annotations

import asyncio
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
async def lifespan(_: FastAPI):
    configure_logging()
    logger.info("Démarrage de ZenHome")
    initialize_database()
    logger.info("Base de données initialisée")
    stop_event = asyncio.Event()
    daemon_task = asyncio.create_task(daemon_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await daemon_task
        logger.info("Arrêt de ZenHome")


logger = logging.getLogger(__name__)


app = FastAPI(
    title="ZenHome",
    description="Notes, checklists et tâches.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(web_router)
app.include_router(public_router)
app.mount("/static", StaticFiles(directory=PROJECT_DIR / "static"), name="static")

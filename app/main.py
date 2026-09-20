"""FastAPI entrypoint. Registers routers and validates configuration."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api import dashboard, webhook
from app.config import get_settings
from app.core.orchestrator import get_orchestrator
from app.services.poller import SessionPoller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("Configuration loaded: %s", settings.describe())
    poller = SessionPoller(get_orchestrator())
    poller.start()
    app.state.poller = poller
    try:
        yield
    finally:
        await poller.stop()


app = FastAPI(
    title="Devin Remediation Bot",
    description="Event-driven remediation of GitHub issues using the Devin API.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook.router)
app.include_router(dashboard.router)

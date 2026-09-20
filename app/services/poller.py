"""Background polling of in-flight Devin sessions."""

from __future__ import annotations

import asyncio
import logging

from app.core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30.0


class SessionPoller:
    """Periodically refreshes non-terminal runs through the orchestrator."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._orchestrator = orchestrator
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def poll_once(self) -> int:
        """Refresh every open run and return how many were polled."""
        return len(self._orchestrator.refresh_open_runs())

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.poll_once)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop must survive transient errors
                logger.exception("Session polling cycle failed")
            await asyncio.sleep(self._interval_seconds)

    def start(self) -> None:
        """Start the polling loop on the running event loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the polling loop and wait for it to unwind."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

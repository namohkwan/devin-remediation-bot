"""Dashboard endpoints: HTML status page and JSON polling."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_settings
from app.core.orchestrator import Orchestrator, get_orchestrator
from app.services.reporting import build_dashboard_report

router = APIRouter(tags=["dashboard"])

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/status", response_class=HTMLResponse)
def status_page(
    request: Request,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render the remediation dashboard."""
    report = build_dashboard_report(orchestrator.list_runs())
    return templates.TemplateResponse(
        request=request,
        name="status.html",
        context={"report": report, "target_repo": settings.target_repo},
    )


@router.get("/poll")
def poll(
    refresh: bool = True,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, object]:
    """Refresh in-flight sessions and return the current report as JSON."""
    if refresh:
        orchestrator.refresh_open_runs()
    return build_dashboard_report(orchestrator.list_runs())


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}

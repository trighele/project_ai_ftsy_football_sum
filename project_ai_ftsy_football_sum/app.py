"""The FastAPI application.

`create_app` is the only entry point. It takes an optional `Container` so that
tests can hand in one whose network edges are fakes; production callers let it
build its own.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from project_ai_ftsy_football_sum.container import EDGES, Container, get_container

PACKAGE_ROOT = Path(__file__).parent
STATIC_DIR = PACKAGE_ROOT / "static"
TEMPLATES_DIR = PACKAGE_ROOT / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _unavailable_edges(container: Container) -> list[str]:
    """The network edges that cannot currently be resolved.

    Any failure to build an edge — not wired yet, missing credentials, a bad
    endpoint — means the app cannot do a run, so the whole exception surface is
    treated the same way here.
    """
    unavailable = []
    for edge in EDGES:
        try:
            container.resolve(edge)
        except Exception:  # noqa: BLE001 — readiness, not error handling
            unavailable.append(edge)
    return unavailable


def create_app(*, container: Container | None = None) -> FastAPI:
    app = FastAPI(title="Fantasy Football Podcast Summarizer")
    app.state.container = container if container is not None else Container()

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "home.html", {"nav_active": "home"})

    @app.get("/fragments/status", response_class=HTMLResponse)
    def status_fragment(request: Request) -> HTMLResponse:
        """The readiness pill the home page swaps in over HTMX on load."""
        return templates.TemplateResponse(
            request,
            "fragments/status.html",
            {"unavailable_edges": _unavailable_edges(get_container(request))},
        )

    return app


app = create_app()

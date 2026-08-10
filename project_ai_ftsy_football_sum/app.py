"""The FastAPI application.

`create_app` is the only entry point. It takes an optional `Container` so that
tests can hand in one whose network edges are fakes; production callers let it
build its own.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from project_ai_ftsy_football_sum.container import EDGES, Container, get_container
from project_ai_ftsy_football_sum.services.transcripts import (
    InvalidUrlError,
    load_episode,
)

PACKAGE_ROOT = Path(__file__).parent
STATIC_DIR = PACKAGE_ROOT / "static"
TEMPLATES_DIR = PACKAGE_ROOT / "templates"

#: Stand-in until ticket 09 gives each failure kind its own message.
GENERIC_FAILURE = (
    "Something went wrong retrieving this episode from YouTube. "
    "Check the link and try again."
)

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

    @app.post("/fragments/episode", response_class=HTMLResponse)
    def episode_fragment(
        request: Request, youtube_url: str = Form(default="")
    ) -> HTMLResponse:
        """Resolve a pasted URL into a transcript and render it.

        A failure renders as a fragment with a 200, because HTMX swaps the
        response body only on a 2xx and the message *is* the response the user
        asked for. Ticket 09 replaces the generic message with typed kinds.
        """
        source = get_container(request).resolve("captions")
        try:
            episode = load_episode(source, youtube_url)
        except InvalidUrlError as error:
            return templates.TemplateResponse(
                request, "fragments/failure.html", {"message": str(error)}
            )
        except Exception:  # noqa: BLE001 — typed error kinds arrive in ticket 09
            return templates.TemplateResponse(
                request, "fragments/failure.html", {"message": GENERIC_FAILURE}
            )
        return templates.TemplateResponse(
            request, "fragments/episode.html", {"episode": episode}
        )

    return app


app = create_app()

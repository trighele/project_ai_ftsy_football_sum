"""The FastAPI application.

`create_app` is the only entry point. It takes an optional `Container` so that
tests can hand in one whose network edges are fakes, and an optional `RunStore`
so they can point it at a temporary database; production callers let it build
both from configuration.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from project_ai_ftsy_football_sum.config import database_path
from project_ai_ftsy_football_sum.container import EDGES, Container, get_container
from project_ai_ftsy_football_sum.services.store import Run, RunStore
from project_ai_ftsy_football_sum.services.transcripts import (
    InvalidUrlError,
    load_episode,
)

PACKAGE_ROOT = Path(__file__).parent
STATIC_DIR = PACKAGE_ROOT / "static"
TEMPLATES_DIR = PACKAGE_ROOT / "templates"

#: How many past runs the home page offers for one-click reopening.
RECENT_RUN_LIMIT = 5

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


def get_store(request: Request) -> RunStore:
    """The run store for the running app. Usable as a FastAPI dependency."""
    return request.app.state.store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the database and its schema before the first request.

    Doing it here rather than when the store is constructed keeps importing
    the module free of side effects — nothing touches disk until the app is
    actually served.
    """
    app.state.store.initialize()
    yield


def create_app(
    *, container: Container | None = None, store: RunStore | None = None
) -> FastAPI:
    app = FastAPI(title="Fantasy Football Podcast Summarizer", lifespan=lifespan)
    app.state.container = container if container is not None else Container()
    app.state.store = store if store is not None else RunStore(database_path())

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "nav_active": "home",
                "recent_runs": get_store(request).recent(RECENT_RUN_LIMIT),
            },
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(request: Request, run_id: int) -> HTMLResponse:
        """Reopen a saved run: the episode it was, and what we made of it."""
        run = get_store(request).get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run.")
        return templates.TemplateResponse(request, "run.html", {"run": run})

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
        def failure(message: str) -> HTMLResponse:
            return templates.TemplateResponse(
                request, "fragments/failure.html", {"message": message}
            )

        source = get_container(request).resolve("captions")
        started = time.perf_counter()
        try:
            episode = load_episode(source, youtube_url)
        except InvalidUrlError as error:
            return failure(str(error))
        except Exception:  # noqa: BLE001 — typed error kinds arrive in ticket 09
            return failure(GENERIC_FAILURE)

        store = get_store(request)
        store.save(Run.of(episode, duration_seconds=time.perf_counter() - started))
        return templates.TemplateResponse(
            request,
            "fragments/episode_result.html",
            {"episode": episode, "recent_runs": store.recent(RECENT_RUN_LIMIT)},
        )

    return app


app = create_app()

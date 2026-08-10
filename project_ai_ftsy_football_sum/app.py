"""The FastAPI application.

`create_app` is the only entry point. It takes an optional `Container` so that
tests can hand in one whose network edges are fakes, and an optional `RunStore`
so they can point it at a temporary database; production callers let it build
both from configuration.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from project_ai_ftsy_football_sum.config import claude_model, database_path
from project_ai_ftsy_football_sum.container import EDGES, Container, get_container
from project_ai_ftsy_football_sum.services.runs import (
    Event,
    LiveRuns,
    lost_event,
    perform,
)
from project_ai_ftsy_football_sum.services.store import RunStore
from project_ai_ftsy_football_sum.templating import templates

PACKAGE_ROOT = Path(__file__).parent
STATIC_DIR = PACKAGE_ROOT / "static"

#: How many past runs the home page offers for one-click reopening.
RECENT_RUN_LIMIT = 5


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
    app.state.runs = LiveRuns()

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

    @app.post("/runs", response_class=HTMLResponse)
    async def start_run(
        request: Request, youtube_url: str = Form(default="")
    ) -> HTMLResponse:
        """Start a run and return at once with the panel that follows it.

        Nothing about the episode is known yet — not even whether the URL is
        usable. Every outcome, a rejected URL included, arrives on the event
        stream, so the browser has one path to render rather than two.
        """
        live = request.app.state.runs.start()
        container = get_container(request)
        store = get_store(request)
        loop = asyncio.get_running_loop()

        def publish(event: Event) -> None:
            """Hand an event from the worker thread back to the event loop."""
            try:
                loop.call_soon_threadsafe(live.publish, event)
            except RuntimeError:
                pass  # The loop is closing: nobody is left to tell.

        live.task = asyncio.create_task(
            asyncio.to_thread(
                perform,
                url=youtube_url,
                container=container,
                store=store,
                model=claude_model(),
                publish=publish,
            )
        )
        # A run that died without reporting anything would leave its stream
        # open for as long as the browser is prepared to wait. `publish` is a
        # no-op once the run has already ended, so this only fires when it has
        # not.
        live.task.add_done_callback(lambda _task: live.publish(lost_event()))
        return templates.TemplateResponse(
            request, "fragments/run.html", {"run": live}, status_code=202
        )

    @app.get("/runs/{token}/events")
    def run_events(request: Request, token: str) -> StreamingResponse:
        """Follow a run: everything it has emitted, then everything it emits.

        The response ends when the run does. A client that reconnects gets the
        whole run again from the beginning, which is cheap and is why the
        events are buffered.
        """
        live = request.app.state.runs.get(token)
        if live is None:
            raise HTTPException(status_code=404, detail="No such run.")

        return StreamingResponse(
            live.frames(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    @app.get("/fragments/status", response_class=HTMLResponse)
    def status_fragment(request: Request) -> HTMLResponse:
        """The readiness pill the home page swaps in over HTMX on load."""
        return templates.TemplateResponse(
            request,
            "fragments/status.html",
            {"unavailable_edges": _unavailable_edges(get_container(request))},
        )

    @app.get("/fragments/recent-runs", response_class=HTMLResponse)
    def recent_runs_fragment(request: Request) -> HTMLResponse:
        """The recent-runs list, re-fetched once a run has made it stale."""
        return templates.TemplateResponse(
            request,
            "fragments/recent_runs.html",
            {"recent_runs": get_store(request).recent(RECENT_RUN_LIMIT)},
        )

    return app


app = create_app()

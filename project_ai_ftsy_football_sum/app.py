"""The FastAPI application.

`create_app` is the only entry point. It takes an optional `Container` so that
tests can hand in one whose network edges are fakes, and an optional `RunStore`
so they can point it at a temporary database; production callers let it build
both from configuration.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from project_ai_ftsy_football_sum.config import claude_model, database_path
from project_ai_ftsy_football_sum.container import EDGES, Container, get_container
from project_ai_ftsy_football_sum.services import batches
from project_ai_ftsy_football_sum.services.download import (
    download_filename,
    markdown_document,
)
from project_ai_ftsy_football_sum.services.failures import error_detail
from project_ai_ftsy_football_sum.services.markdown import render_markdown
from project_ai_ftsy_football_sum.services.player_cache import PlayerCache
from project_ai_ftsy_football_sum.services.players import (
    NflverseUnavailableError,
    ensure_reference,
    sync_reference,
)
from project_ai_ftsy_football_sum.services.runs import (
    Event,
    LiveRun,
    LiveRuns,
    Publish,
    lost_event,
    perform,
)
from project_ai_ftsy_football_sum.services.store import Run, RunStore
from project_ai_ftsy_football_sum.services.summarize import (
    MAX_CONTEXT_NOTE_LENGTH,
    context_note_from,
)
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


def get_players(request: Request) -> PlayerCache:
    """The cached player reference. Usable as a FastAPI dependency."""
    return request.app.state.players


def _player_reference(request: Request, *, sync: bool) -> dict[str, object]:
    """What the Players page and its fragment both render from.

    A sync that could not be done is reported rather than swallowed — whether
    the reader pressed **Sync now** or merely opened a page whose reference had
    gone stale — but whatever was cached is still shown beneath it, because an
    older reference beats an error page.
    """
    cache = get_players(request)
    container = get_container(request)
    try:
        if sync:
            return {"reference": sync_reference(container, cache)}
        outcome = ensure_reference(container, cache)
    except NflverseUnavailableError as error:
        return {
            "reference": cache.load(),
            "unavailable": str(error),
            "unavailable_detail": error_detail(error),
        }
    return {
        "reference": outcome.reference,
        "unavailable": outcome.sync_error,
        "unavailable_detail": outcome.sync_detail,
    }


def _in_background(
    live: LiveRun, work: Callable[[Publish], None], *, lost: Callable[[], Event]
) -> None:
    """Do blocking work on a worker thread, with its events reaching the loop.

    The same arrangement for a run and for a batch, because it is the same
    arrangement: the request returns at once, the work happens on a thread
    since every edge it touches is a blocking library, and whatever it
    publishes is handed back across to the loop its followers are on.

    `lost` is the terminal event for work that ended without reporting
    anything. It is published unconditionally when the task finishes, which is
    safe because publishing to a stream that has already ended does nothing —
    so it only lands when the work really did die.
    """
    loop = asyncio.get_running_loop()

    def publish(event: Event) -> None:
        """Hand an event from the worker thread back to the event loop."""
        try:
            loop.call_soon_threadsafe(live.publish, event)
        except RuntimeError:
            pass  # The loop is closing: nobody is left to tell.

    live.task = asyncio.create_task(asyncio.to_thread(work, publish))
    live.task.add_done_callback(lambda _task: live.publish(lost()))


def _event_stream(live: LiveRun | None, *, missing: str) -> StreamingResponse:
    """Follow work: everything it has emitted, then everything it emits.

    The response ends when the work does. A client that reconnects gets the
    whole of it again from the beginning, which is cheap and is why the events
    are buffered.
    """
    if live is None:
        raise HTTPException(status_code=404, detail=missing)
    return StreamingResponse(
        live.frames(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


def _saved_run(request: Request, run_id: int) -> Run:
    """The run with that identifier, or a 404 for the reader who asked."""
    run = get_store(request).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No such run.")
    return run


def _history_list_response(request: Request, query: str) -> HTMLResponse:
    """The history list rendered on its own — after a search, or a delete."""
    return templates.TemplateResponse(
        request,
        "fragments/history_list.html",
        {"query": query, "runs": get_store(request).search(query)},
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the database and its schema before the first request.

    Doing it here rather than when the store is constructed keeps importing
    the module free of side effects — nothing touches disk until the app is
    actually served.
    """
    app.state.store.initialize()
    app.state.players.initialize()
    yield


def create_app(
    *, container: Container | None = None, store: RunStore | None = None
) -> FastAPI:
    app = FastAPI(title="Fantasy Football Podcast Summarizer", lifespan=lifespan)
    app.state.container = container if container is not None else Container()
    app.state.store = store if store is not None else RunStore(database_path())
    # The same file the runs are in: one volume holds everything the app must
    # not lose, which is the whole reason the data directory is a directory.
    app.state.players = PlayerCache(app.state.store.path)
    app.state.runs = LiveRuns()
    # The same registry type under the batch's own terminal event names, so a
    # batch is started, followed, and aged out exactly as a run is.
    app.state.batches = LiveRuns(terminal=batches.TERMINAL_EVENTS)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "nav_active": "home",
                "recent_runs": get_store(request).recent(RECENT_RUN_LIMIT),
                # The form's own cap, so the length a note is cut to is stated
                # once and the field cannot drift from the server that trims it.
                "max_context_note_length": MAX_CONTEXT_NOTE_LENGTH,
                # And the batch's, for the same reason: the number the reader
                # is told is the number the submission is measured against.
                "max_batch_episodes": batches.MAX_BATCH_EPISODES,
            },
        )

    @app.get("/players", response_class=HTMLResponse)
    def players(request: Request) -> HTMLResponse:
        """The player reference Claude works from, as the reader can check it."""
        return templates.TemplateResponse(
            request,
            "players.html",
            {"nav_active": "players", **_player_reference(request, sync=False)},
        )

    @app.post("/players/sync", response_class=HTMLResponse)
    def players_sync(request: Request) -> HTMLResponse:
        """Sync now: fetch the reference again whatever the cache says."""
        return templates.TemplateResponse(
            request,
            "fragments/player_reference.html",
            _player_reference(request, sync=True),
        )

    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request, q: str = Query(default="")) -> HTMLResponse:
        """Every saved run, newest episode first, narrowed by the search term."""
        return templates.TemplateResponse(
            request,
            "history.html",
            {
                "nav_active": "history",
                "query": q,
                "runs": get_store(request).search(q),
            },
        )

    @app.get("/fragments/history", response_class=HTMLResponse)
    def history_fragment(request: Request, q: str = Query(default="")) -> HTMLResponse:
        """The list on its own, so the search box filters without a reload."""
        return _history_list_response(request, q)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(request: Request, run_id: int) -> HTMLResponse:
        """Reopen a saved run: the episode it was, and what we made of it.

        The summary is rendered here rather than stored rendered, so a change
        to how prose is produced reaches every run already saved.
        """
        run = _saved_run(request, run_id)
        return templates.TemplateResponse(
            request,
            "run.html",
            {"run": run, "summary_html": render_markdown(run.summary or "")},
        )

    @app.get("/runs/{run_id}/download", response_class=PlainTextResponse)
    def run_download(request: Request, run_id: int) -> PlainTextResponse:
        """The run as a Markdown file, named after the episode."""
        run = _saved_run(request, run_id)
        return PlainTextResponse(
            markdown_document(run),
            media_type="text/markdown; charset=utf-8",
            headers={
                "content-disposition": (
                    f'attachment; filename="{download_filename(run)}"'
                )
            },
        )

    @app.delete("/runs/{run_id}", response_class=HTMLResponse)
    def run_delete(
        request: Request, run_id: int, q: str = Query(default="")
    ) -> HTMLResponse:
        """Delete a run and hand back the list it has just left.

        No confirmation step: the reader deleting a junk run should not have to
        say so twice. The search term comes along so that deleting a result
        returns the rest of that search rather than the whole history.
        """
        if not get_store(request).delete(run_id):
            raise HTTPException(status_code=404, detail="No such run.")
        return _history_list_response(request, q)

    @app.post("/runs", response_class=HTMLResponse)
    async def start_run(
        request: Request,
        youtube_url: str = Form(default=""),
        context_note: str = Form(default=""),
    ) -> HTMLResponse:
        """Start a run and return at once with the panel that follows it.

        Nothing about the episode is known yet — not even whether the URL is
        usable. Every outcome, a rejected URL included, arrives on the event
        stream, so the browser has one path to render rather than two.
        """
        live = request.app.state.runs.start()
        # Made sense of once, here, and handed to both the run and the panel
        # that shows it back: a note displayed differently from the one sent
        # and kept would misrepresent what was asked for.
        note = context_note_from(context_note)
        container = get_container(request)
        store = get_store(request)
        players = get_players(request)
        model = claude_model()

        _in_background(
            live,
            lambda publish: perform(
                url=youtube_url,
                container=container,
                store=store,
                players=players,
                model=model,
                publish=publish,
                context_note=note,
            ),
            lost=lost_event,
        )
        return templates.TemplateResponse(
            request,
            "fragments/run.html",
            {"run": live, "context_note": note},
            status_code=202,
        )

    @app.get("/runs/{token}/events")
    def run_events(request: Request, token: str) -> StreamingResponse:
        """Follow a run to its one terminal event."""
        return _event_stream(
            request.app.state.runs.get(token), missing="No such run."
        )

    @app.post("/batches", response_class=HTMLResponse)
    async def start_batch(
        request: Request, youtube_urls: str = Form(default="")
    ) -> HTMLResponse:
        """Start a batch and return at once with the queue that follows it.

        The queue is the receipt for what was pasted, so it is rendered whole
        before any work starts and every row of it is on the page from the
        moment it arrives — the failed rows included, since a line that names
        no episode is failed while the submission is being made sense of and
        never asked about. What happens to the rest arrives on the event
        stream the queue names.

        A submission that is not a batch at all — nothing pasted, or more
        episodes than one takes — is answered with the panel saying so and
        no stream, because there is nothing to follow. It is a rejected
        request rather than a run of no episodes, and it says so with its
        status.
        """
        try:
            batch = batches.batch_from(youtube_urls)
        except batches.BatchRejected as rejected:
            return templates.TemplateResponse(
                request,
                "fragments/failure.html",
                {"heading": "Batch not started", "message": str(rejected)},
                status_code=400,
            )

        live = request.app.state.batches.start()
        container = get_container(request)
        store = get_store(request)
        players = get_players(request)
        model = claude_model()

        _in_background(
            live,
            lambda publish: batches.perform_batch(
                batch=batch,
                container=container,
                store=store,
                players=players,
                model=model,
                publish=publish,
            ),
            lost=batches.lost_event,
        )
        return templates.TemplateResponse(
            request,
            "fragments/batch.html",
            {"token": live.token, "batch": batch},
            status_code=202,
        )

    @app.get("/batches/{token}/events")
    def batch_events(request: Request, token: str) -> StreamingResponse:
        """Follow a batch to its one terminal event."""
        return _event_stream(
            request.app.state.batches.get(token), missing="No such batch."
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

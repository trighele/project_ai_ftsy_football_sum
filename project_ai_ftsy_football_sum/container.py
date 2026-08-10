"""Resolution of the application's three network edges.

The app talks to exactly three things outside itself: YouTube's captions, the
nflverse data source, and the Claude API. Each is resolved through this
container instead of being constructed where it is used, so that tests can
substitute a fake without production code knowing about it.

That is the entire justification for the indirection. It is not a service
locator and nothing that is not a network edge belongs in it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, get_args

from fastapi import Request

Edge = Literal["captions", "nflverse", "claude"]

#: The three edges, and what supplies each one for real. Until an edge has an
#: implementation, resolving it raises. This mapping is the single place the
#: set of edges is written down.
EDGE_SOURCES: Mapping[Edge, str] = {
    "captions": "the episode source (youtube-transcript-api, yt-dlp)",
    "nflverse": "the nflverse source (nflreadpy)",
    "claude": "the Claude client (anthropic)",
}

EDGES: tuple[Edge, ...] = get_args(Edge)


class EdgeNotWiredError(RuntimeError):
    """Raised when an edge with no real implementation yet is resolved."""


def _unwired(edge: Edge) -> Callable[[], Any]:
    def factory() -> Any:
        raise EdgeNotWiredError(
            f"No implementation is registered for the {edge!r} edge: "
            f"{EDGE_SOURCES[edge]} is not built yet. Override it to supply one."
        )

    return factory


def _captions() -> Any:
    """Imported here so nothing outside a real run pays for the libraries."""
    from project_ai_ftsy_football_sum.services.youtube import YouTubeSource

    return YouTubeSource()


#: The real factory for each edge that has an implementation. The rest raise
#: until their ticket lands.
DEFAULT_FACTORIES: Mapping[Edge, Callable[[], Any]] = {"captions": _captions}

#: The edges still waiting for an implementation.
UNWIRED_EDGES: tuple[Edge, ...] = tuple(
    edge for edge in EDGES if edge not in DEFAULT_FACTORIES
)


class Container:
    """Lazily resolves each network edge, once, and lets tests override it.

    Each edge is built on first use and memoised, so importing or starting the
    application never opens a connection. An override registered before the
    first resolution is handed out in place of the real implementation, and the
    real factory is never called.
    """

    def __init__(
        self, *, factories: Mapping[Edge, Callable[[], Any]] | None = None
    ) -> None:
        self._factories: dict[Edge, Callable[[], Any]] = {
            edge: DEFAULT_FACTORIES.get(edge, _unwired(edge)) for edge in EDGES
        }
        for edge, factory in (factories or {}).items():
            self._factories[self._checked(edge)] = factory
        self._instances: dict[Edge, Any] = {}

    def override(self, **instances: Any) -> None:
        """Register a ready-made instance for one or more edges by name."""
        for edge, instance in instances.items():
            self._instances[self._checked(edge)] = instance

    def resolve(self, edge: Edge) -> Any:
        """Return the instance for `edge`, building it on first use."""
        self._checked(edge)
        if edge not in self._instances:
            self._instances[edge] = self._factories[edge]()
        return self._instances[edge]

    @staticmethod
    def _checked(edge: str) -> Edge:
        if edge not in EDGE_SOURCES:
            raise KeyError(f"Unknown edge {edge!r}; expected one of {EDGES}")
        return edge  # type: ignore[return-value]


def get_container(request: Request) -> Container:
    """The container for the running app. Usable as a FastAPI dependency."""
    return request.app.state.container

"""The one Jinja environment, shared by the pages and by a run's events.

Most of this application's markup is rendered as the response to a request.
A run's progress is not: it is rendered on a worker thread and pushed down an
already-open event stream. So the environment lives here rather than in the
application module, which the run engine would otherwise have to import back
into to reach it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def fragment(name: str, **context: Any) -> str:
    """Render a fragment with no request behind it.

    Only for fragments that ask nothing of the request — the ones a run emits.
    Anything reached by a URL should be rendered as a `TemplateResponse`.
    """
    return templates.get_template(name).render(context)

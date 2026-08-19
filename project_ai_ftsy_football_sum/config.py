"""Everything the environment gets to decide, and the defaults when it doesn't.

The data directory holds what the application would rather not lose on a
restart: the saved runs and the cached player reference, which it must not
lose, and the nflverse tables already downloaded, which it would only have to
fetch again. It is a directory rather
than a file path so that a deployment mounts a single volume here and the
application needs no further configuration to put a second thing on it.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The environment variable naming the data directory.
DATA_DIR_VARIABLE = "FFSUM_DATA_DIR"

#: Where the data lives when nothing says otherwise: alongside the working
#: directory, which is the repository root when the app is run locally.
DEFAULT_DATA_DIR = Path("data")

#: The single SQLite file inside that directory.
DATABASE_FILENAME = "ffsum.db"


def data_dir() -> Path:
    """The configured data directory. Not created here — see `RunStore`."""
    configured = os.environ.get(DATA_DIR_VARIABLE, "").strip()
    return Path(configured) if configured else DEFAULT_DATA_DIR


def database_path() -> Path:
    """The SQLite file the application reads and writes."""
    return data_dir() / DATABASE_FILENAME


#: The subdirectory holding the nflverse tables already downloaded. A directory
#: of its own inside the data directory, because it is a cache of somebody
#: else's files rather than anything the application wrote: it can be emptied
#: without losing a saved run.
NFLVERSE_CACHE_DIRNAME = "nflverse-cache"


def nflverse_cache_dir() -> Path:
    """Where nflreadpy keeps the tables it has already downloaded.

    Not created here — nflreadpy creates it when it first writes to it.
    """
    return data_dir() / NFLVERSE_CACHE_DIRNAME


#: The environment variable naming the model. Kept from the Gradio app, so an
#: existing deployment's configuration still means what it used to.
MODEL_VARIABLE = "CLAUDE_MODEL"

#: What summaries are written with unless the environment says otherwise.
DEFAULT_MODEL = "claude-sonnet-5"


def claude_model() -> str:
    """The model every summary is written with."""
    configured = os.environ.get(MODEL_VARIABLE, "").strip()
    return configured or DEFAULT_MODEL

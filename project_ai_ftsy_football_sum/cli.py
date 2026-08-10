"""Console entry point: `ffsum`.

A thin wrapper over `uvicorn.run` so starting the app is one word rather than a
module path. Everything it can do, `uv run uvicorn project_ai_ftsy_football_sum.app:app`
can do too.
"""

from __future__ import annotations

import argparse
import os

import uvicorn

APP = "project_ai_ftsy_football_sum.app:app"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ffsum", description="Run the fantasy football podcast summarizer."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="interface to bind (default: %(default)s; 0.0.0.0 in a container)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="port to bind (default: %(default)s)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="restart on code and template changes, for local development",
    )
    args = parser.parse_args()

    uvicorn.run(APP, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

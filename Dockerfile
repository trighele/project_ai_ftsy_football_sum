# The application is a web server and nothing else: no audio, no ffmpeg, no
# compiler. Everything it needs is a pure-Python wheel or a manylinux one, so a
# slim base with uv on it is the whole image.
FROM python:3.14-slim-bookworm

# uv comes from its own published image rather than an install script, pinned so
# a rebuild resolves the same way the lockfile expects.
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, from the lockfile alone, so editing application code does
# not re-resolve or re-download anything. `--frozen` fails rather than silently
# relocking if uv.lock has drifted from pyproject.toml.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY project_ai_ftsy_football_sum ./project_ai_ftsy_football_sum
RUN uv sync --frozen --no-dev

# Where saved runs and the cached player reference live. Compose and the
# Unraid template both mount a volume here; without one the data is still
# written, it just does not survive the container.
ENV FFSUM_DATA_DIR=/data
VOLUME ["/data"]

# Bound to every interface because the process is alone in the container, and
# to the same port the Service and Compose expect.
ENV HOST=0.0.0.0 \
    PORT=8000
EXPOSE 8000

CMD ["ffsum"]

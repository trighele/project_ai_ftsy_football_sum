# Ubuntu, matching every other machine this container is opened on. The
# production image (../Dockerfile) is python:3.14-slim and stays that way; this
# one is a development environment and shares nothing with it but uv.
FROM mcr.microsoft.com/devcontainers/base:ubuntu

# Same source and same pin as the production image, so a dependency resolves
# here the way it resolves in the image that ships.
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /usr/local/bin/

# Git parity with the host. All three are system-wide so they apply on every
# rebuild and to every user in the container:
#   safe.directory  - the workspace is owned by the host UID, not by vscode, and
#                     without this git refuses the repo and prints nothing
#                     useful for it.
#   core.filemode   - Windows has no permission bits, so a bind-mounted tree
#                     reports modes the index never recorded.
#   core.autocrlf   - the host checks out CRLF; without `input` the entire tree
#                     reads as rewritten in `git status`.
RUN git config --system --add safe.directory '*' \
    && git config --system core.filemode false \
    && git config --system core.autocrlf input

# uv fetches the interpreter named in .python-version; putting its store on the
# image rather than in $HOME keeps it out of the mounted volumes.
ENV UV_PYTHON_INSTALL_DIR=/usr/local/share/uv/python
RUN mkdir -p "$UV_PYTHON_INSTALL_DIR" \
    && uv python install 3.14 \
    && chmod -R a+rX "$UV_PYTHON_INSTALL_DIR"

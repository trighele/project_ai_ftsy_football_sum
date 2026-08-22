#!/usr/bin/env bash
# Runs once per container create, as vscode, with the workspace as cwd.
set -euo pipefail

echo "==> ownership of mounted volumes"
# A fresh named volume is created root-owned. Failure is fine and expected on
# the bind mount - on some Docker backends a bind mount ignores chown, which
# just means the uids already lined up.
sudo chown -R vscode:vscode "$PWD/.venv" 2>/dev/null || true
sudo chown -R vscode:vscode "$HOME/.cache/uv" 2>/dev/null || true
sudo chown -R vscode:vscode "$HOME/.claude" 2>/dev/null || true
sudo chown -R vscode:vscode /data 2>/dev/null || true

echo "==> git identity"
# Read on the host by bootstrap.mjs. Copying only the identity is deliberate:
# inheriting the host's whole .gitconfig would name Windows credential helpers
# that do not exist in here.
if [ -n "${GIT_USER_NAME:-}" ]; then git config --global user.name "$GIT_USER_NAME"; fi
if [ -n "${GIT_USER_EMAIL:-}" ]; then git config --global user.email "$GIT_USER_EMAIL"; fi
echo "    $(git config --get user.name || echo '(unset)') <$(git config --get user.email || echo '(unset)')>"

# Mounted from the host so the same personal ignore rules apply here; without
# it `git status` in the container lists files the host quietly ignores.
if [ -f "$HOME/.gitignore-global" ]; then
    git config --global core.excludesFile "$HOME/.gitignore-global"
fi

echo "==> claude code"
if [ "${HOST_HAS_CLAUDE:-0}" != "1" ]; then
    # Informational, not a warning. Someone without Claude Code on the host is
    # not in a broken state; ~/.claude here is just an empty placeholder.
    echo "    host has no ~/.claude - the mount is a placeholder, so no shared skills or auth."
fi
if ! command -v claude >/dev/null 2>&1; then
    # Never fatal: a registry problem should cost the CLI, not the container.
    npm install -g @anthropic-ai/claude-code \
        || echo "    WARN: claude code install failed - install it by hand later"
fi
if command -v claude >/dev/null 2>&1; then echo "    $(claude --version)"; fi

echo "==> uv sync"
uv sync

echo
echo "==> ready"
echo "    tests:   uv run pytest"
echo "    the app: uv run --env-file .env ffsum --reload --host 0.0.0.0"

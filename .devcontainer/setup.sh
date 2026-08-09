#!/bin/bash
set -e

apt-get update
apt-get install -y git curl

git config --global --add safe.directory /home/build/app

# Install uv if not already present
if ! command -v uv &> /dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Install dependencies via uv
cd /home/build/app
uv sync

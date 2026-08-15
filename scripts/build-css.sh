#!/usr/bin/env bash
# Compile the Tailwind source to the stylesheet the app serves.
#
# The compiled output is committed, so neither the Docker image nor a plain
# `uv run` needs a Node toolchain. Run this after editing the Tailwind source
# or any template, and commit the result.
set -euo pipefail

VERSION="v4.1.11"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/project_ai_ftsy_football_sum"
BIN="$ROOT/.tools/tailwindcss-$VERSION"

if [[ ! -x "$BIN" ]]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) ASSET="tailwindcss-linux-x64" ;;
    Linux-aarch64) ASSET="tailwindcss-linux-arm64" ;;
    Darwin-x86_64) ASSET="tailwindcss-macos-x64" ;;
    Darwin-arm64) ASSET="tailwindcss-macos-arm64" ;;
    *) echo "No Tailwind standalone build for $(uname -s)-$(uname -m)" >&2; exit 1 ;;
  esac
  echo "Fetching Tailwind $VERSION standalone CLI…"
  mkdir -p "$ROOT/.tools"
  curl -sSfL -o "$BIN" \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/$VERSION/$ASSET"
  chmod +x "$BIN"
fi

"$BIN" \
  --input "$PKG/assets/tailwind.css" \
  --output "$PKG/static/css/app.css" \
  --minify \
  "$@"

echo "Wrote $PKG/static/css/app.css"

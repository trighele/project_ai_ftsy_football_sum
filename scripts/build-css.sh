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

# Which release asset this platform needs. Git Bash, MSYS2, and Cygwin all
# report `<environment>_NT-<windows version>` from `uname -s` — MINGW64_NT-10.0,
# UCRT64_NT-10.0, MSYS_NT-10.0, CYGWIN_NT-10.0 — so they are matched by the
# shape they share rather than by naming each shell that exists. An unmatched
# platform leaves this empty and is only an error if a download is needed.
ASSET=""
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) ASSET="tailwindcss-linux-x64" ;;
  Linux-aarch64) ASSET="tailwindcss-linux-arm64" ;;
  Darwin-x86_64) ASSET="tailwindcss-macos-x64" ;;
  Darwin-arm64) ASSET="tailwindcss-macos-arm64" ;;
  *_NT-*-x86_64) ASSET="tailwindcss-windows-x64.exe" ;;
  *_NT-*-aarch64) ASSET="tailwindcss-windows-arm64.exe" ;;
esac

# Only the Windows asset is an .exe, so the asset name is the one place that
# decides which platform this is — the binary's own name and the form of the
# paths it is handed both come off it.
WINDOWS=""
case "$ASSET" in *.exe) WINDOWS="yes" ;; esac

BIN="$ROOT/.tools/tailwindcss-$VERSION"
if [[ -n "$WINDOWS" ]]; then
  BIN="$BIN.exe"
fi

if [[ ! -x "$BIN" ]]; then
  if [[ -z "$ASSET" ]]; then
    echo "No Tailwind standalone build for $(uname -s)-$(uname -m)" >&2
    exit 1
  fi
  echo "Fetching Tailwind $VERSION standalone CLI…"
  mkdir -p "$ROOT/.tools"
  curl -sSfL -o "$BIN" \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/$VERSION/$ASSET"
  chmod +x "$BIN"
fi

# The Windows build is a native binary under a POSIX shell: it cannot open a
# path like /c/Users/…, and the rewriting the MSYS runtime normally does to
# arguments on the way through is off whenever MSYS_NO_PATHCONV is set. Convert
# here rather than depend on it — as mixed form (C:/Users/…), because the input
# path is also what Tailwind resolves this file's @source globs against, and
# backslashes there are an escape character rather than a separator.
INPUT="$PKG/assets/tailwind.css"
OUTPUT="$PKG/static/css/app.css"
if [[ -n "$WINDOWS" ]]; then
  INPUT="$(cygpath -m "$INPUT")"
  OUTPUT="$(cygpath -m "$OUTPUT")"
fi

"$BIN" \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --minify \
  "$@"

echo "Wrote $PKG/static/css/app.css"

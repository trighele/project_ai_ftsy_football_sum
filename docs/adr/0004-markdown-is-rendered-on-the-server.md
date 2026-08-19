# The summary's Markdown is rendered to HTML on the server

A summary is Markdown, and is now shown as formatted prose with its source available beneath it. The rendering is done in Python (`markdown-it-py`, raw HTML escaped rather than sanitized) and reaches the browser as server-rendered HTML — on the saved run page directly, and on a live run in the terminal `done` event, which the run script swaps in over the raw text it has been streaming.

## Considered Options

- **Vendoring a JavaScript Markdown renderer and rendering incrementally as the summary streams.** Rejected: it would put ~100KB of third-party JS into `static/`, make the summary the only part of the page the server does not render, and hide the rendered output from a test suite that drives every other page through `TestClient`. The one thing it buys — formatting appearing word by word — is worth less than that.

## Consequences

- A live run shows raw Markdown for as long as Claude is writing, and formats when it finishes. This is deliberate and is the whole cost of the decision.
- Prose styling is hand-written CSS in the Tailwind source: the standalone Tailwind CLI this repo builds with does not bundle `@tailwindcss/typography`.
- The Copy control hands over the same document the download does, front matter included, and falls back to a hidden-textarea copy where `navigator.clipboard` is unavailable — the deployment is served over plain HTTP, which is not a secure context.

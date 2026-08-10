# 01 — App skeleton, theme, and test harness

**What to build:** A running FastAPI application that serves a styled home page. Someone starting the app locally lands on a dark, deliberately-designed page with a YouTube URL input and a Summarize button that does nothing yet. This is the walking skeleton every later ticket builds on: it establishes the rendering stack, the visual theme, the dependency container that makes the three network edges swappable, and the first test.

The three network edges — the captions source, the nflverse source, and the Claude client — are resolved through a small application-level dependency container rather than constructed inline. Nothing uses them yet; the container exists so that later tickets can substitute fakes in tests without touching production code paths. This indirection has exactly one justification and should not grow beyond it.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] The application starts under uvicorn and serves a home page.
- [x] Tailwind is compiled to a stylesheet committed to the repo; the page references no CDN and the Docker image needs no Node toolchain.
- [x] The theme is established and applied: near-black surfaces, a single saturated accent, condensed uppercase headings, tabular numerals available for data tables.
- [x] Base template and page layout exist with navigation placeholders for the Players and History pages.
- [x] HTMX is loaded from the committed static assets and confirmed working on at least one trivial interaction.
- [x] A dependency container resolves the captions source, nflverse source, and Claude client, and allows each to be overridden.
- [x] A pytest suite exists, driving the app through its test client, with at least one test asserting the home page renders and one asserting an overridden dependency is used in place of the real one.
- [x] The new FastAPI, uvicorn, and Jinja dependencies are added to the project's dependency declaration. Removing Gradio is not part of this ticket.
- [x] No test in the suite makes a network call.

## Comments

**Implemented.** `uv run pytest` is green (22 tests) and the app serves under uvicorn.

- `project_ai_ftsy_football_sum/app.py` (`create_app`), `container.py`, `templates/`, `static/`, `assets/tailwind.css`, `scripts/build-css.sh`, `tests/`.
- Tailwind v4 compiles to the committed `static/css/app.css`; the build script fetches the standalone CLI into the gitignored `.tools/`, so nothing needs Node. htmx 2.0.4 and the Oswald latin subset (SIL OFL, licence committed alongside) are vendored under `static/`. No CDN reference in any template or in the stylesheet.
- Theme: near-black surfaces, one saturated accent (`#00e07a`), Oswald for condensed uppercase headings via the `heading` utility, and `tabular-nums` applied to `table` in the base layer so data tables get lining figures for free.
- HTMX interaction: the footer readiness pill `hx-get`s `/fragments/status` on load. It reports "Ready" only when all three edges resolve, so it is a real check rather than a hardcoded label — today it correctly reads "Not ready", since no edge has an implementation yet.
- That readiness endpoint is also how the override is asserted over HTTP: with fakes registered on the container the pill reads "Ready"; with the real (unwired) implementations it reads "Not ready" and names the missing edges.
- Edges are resolved lazily and memoised. Until the tickets that supply them (02 captions, 06 nflverse, 08 Claude), resolving one raises `EdgeNotWiredError`.
- An autouse fixture in `tests/conftest.py` blocks sockets, so "no test makes a network call" is enforced rather than assumed.

**Caveat:** the HTMX interaction is verified at the HTTP level (endpoint response, wiring attributes, and the vendored `htmx.min.js` served by a live uvicorn). No headless browser was available in this environment, so nothing exercised the swap in a real DOM.

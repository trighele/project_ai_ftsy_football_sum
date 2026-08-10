# 01 — App skeleton, theme, and test harness

**What to build:** A running FastAPI application that serves a styled home page. Someone starting the app locally lands on a dark, deliberately-designed page with a YouTube URL input and a Summarize button that does nothing yet. This is the walking skeleton every later ticket builds on: it establishes the rendering stack, the visual theme, the dependency container that makes the three network edges swappable, and the first test.

The three network edges — the captions source, the nflverse source, and the Claude client — are resolved through a small application-level dependency container rather than constructed inline. Nothing uses them yet; the container exists so that later tickets can substitute fakes in tests without touching production code paths. This indirection has exactly one justification and should not grow beyond it.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The application starts under uvicorn and serves a home page.
- [ ] Tailwind is compiled to a stylesheet committed to the repo; the page references no CDN and the Docker image needs no Node toolchain.
- [ ] The theme is established and applied: near-black surfaces, a single saturated accent, condensed uppercase headings, tabular numerals available for data tables.
- [ ] Base template and page layout exist with navigation placeholders for the Players and History pages.
- [ ] HTMX is loaded from the committed static assets and confirmed working on at least one trivial interaction.
- [ ] A dependency container resolves the captions source, nflverse source, and Claude client, and allows each to be overridden.
- [ ] A pytest suite exists, driving the app through its test client, with at least one test asserting the home page renders and one asserting an overridden dependency is used in place of the real one.
- [ ] The new FastAPI, uvicorn, and Jinja dependencies are added to the project's dependency declaration. Removing Gradio is not part of this ticket.
- [ ] No test in the suite makes a network call.

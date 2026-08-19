---
title: Read a summary as formatted prose, and copy it as Markdown
labels: [ready-for-agent]
created: 2026-08-18
---

## Problem Statement

A summary is Markdown and is shown as Markdown source: hashes, asterisks, and pipes, in a pre-wrapped block. It is the right thing to paste elsewhere and the wrong thing to read. The reader who wants to read the summary has to mentally render it, and the reader who wants to take it somewhere else has to download a file or select the text by hand — there is no copy control anywhere in the application.

## Solution

The summary is shown as formatted prose — headings, bullets, bold, tables — with its Markdown source available underneath in a disclosure, exactly the gesture the application already uses for "show me what actually happened" on an error. A **Copy** button beside the existing Download hands over the same document the download does, so what lands on the clipboard is what lands in the file.

A live run keeps streaming plain text as Claude writes it, and formats when it finishes. That is the visible cost of rendering on the server, and it is accepted: see ADR-0004.

## User Stories

1. As a reader, I want a saved summary shown as formatted prose, so that I can read it instead of decoding it.
2. As a reader, I want headings, lists, bold, and tables rendered, so that the structure the summary was asked to produce is visible.
3. As a reader, I want the Markdown source still available on the page, so that I can check exactly what was written.
4. As a reader, I want the source collapsed by default, so that the page opens on the readable version.
5. As a reader, I want a Copy button, so that I can take a summary elsewhere without downloading a file.
6. As a reader, I want Copy to hand over the same document as Download, front matter included, so that the two never disagree and the source of the summary travels with it.
7. As a reader, I want Copy to work on the deployed box over plain HTTP, so that the button is not decorative outside local development.
8. As a reader, I want the button to confirm it copied, so that I am not left pressing it twice.
9. As a reader watching a live run, I want the summary to appear as it is written, so that I can see progress.
10. As a reader, I want a finished live run to format itself without a reload, so that the run I just watched reads like a saved one.
11. As a reader, I want the rendered prose to match the rest of the application, so that it does not look like a different page.
12. As a reader, I want long tables in a summary to scroll rather than break the layout, so that a wide table does not push the page sideways.
13. As a maintainer, I want any HTML inside a summary rendered as text, so that model output cannot inject markup into the page.
14. As a maintainer, I want the rendering done where the tests can see it, so that the summary is not the one part of the page the suite cannot assert on.
15. As a maintainer, I want the stylesheet buildable on the machine I work on, so that a styling change is not blocked by the build script.

## Implementation Decisions

- **Rendering happens on the server**, in Python, and reaches the browser as HTML. See ADR-0004 for the alternative considered and why it was rejected.
- **The renderer is a small module of its own**: Markdown in, HTML out, raw HTML escaped rather than sanitized, tables enabled, link auto-detection and typographic substitution off. Nothing configurable and nothing conditional — deterministic output for the same input.
- **Raw HTML is escaped, not filtered.** There is no allowlist to maintain and no case where Claude has a legitimate reason to emit markup.
- **Two places render it**: the saved run page, directly; and the terminal event of a live run, which gains the rendered HTML in its payload so the run script can swap it in over the streamed text. No extra request, and the browser still never builds markup — the same rule the whole application follows.
- **The source disclosure** reuses the existing collapsed-details pattern used for underlying errors, so "show me the raw thing" is one gesture everywhere.
- **Copy fetches the download URL and copies the response body.** The document is built in one place already; copying it means asking for it, not rebuilding it in the browser. For a live run the identifier arrives in the terminal event, so the same URL exists by the time the button appears.
- **Clipboard access is feature-detected with a fallback.** The modern clipboard API is a secure-context feature and is absent over plain HTTP, which is how the deployment is served — so the button falls back to a hidden textarea and the legacy copy command. Without this the button works in development and silently fails in production.
- **Prose styling is hand-written** in the Tailwind source as a utility applied to the rendered container, because the standalone Tailwind CLI this repository builds with does not bundle the typography plugin. It covers headings, paragraphs, lists, bold and italic, links, inline and block code, blockquotes, horizontal rules, and tables, in the existing palette. Tables scroll inside their own container.
- **The stylesheet build script gains a Windows branch.** It currently branches on Linux and macOS only and exits on anything else, so the compiled stylesheet cannot be rebuilt on the maintainer's machine at all. This is a prerequisite, not a nicety: every other decision here needs a stylesheet rebuild.
- **History rows get no Copy button.** Copying is something you do having read a summary, not while scanning a list.

## Testing Decisions

A good test asserts that the rendered output is present and correct in the response, and that dangerous input came out inert — never that a particular tag has a particular class.

- **Through the HTTP seam**: a saved run's page contains the rendered structure of its summary rather than the raw source; the raw source is present in the collapsed disclosure; a summary containing HTML renders that HTML escaped; the Copy control is present and points at the download URL.
- **Through the event stream**: the terminal event of a run carries the rendered summary, and the rendered text matches what the streamed pieces assembled to.
- **Directly on the renderer**, if anything warrants it: that headings, lists, and tables convert, and that raw HTML does not survive as markup.
- **Not tested**: the clipboard fallback and the prose CSS. Both are browser behaviour the suite has never driven, and a test of either would restate the implementation.
- **Prior art**: the existing saved-run and summary-stream tests, which already assert on page content and on event payloads.

## Out of Scope

- Incremental rendering while the summary streams.
- Editing a summary, or re-rendering an old one differently.
- Printing, PDF export, or any format other than Markdown.
- Serving the application over HTTPS, which would make the clipboard fallback unnecessary but is a separate piece of work.
- Rendering the transcript, which stays plain text.

## Further Notes

The dependency is the first in this repository whose only job is presentation. It is small, pure, and has no network behaviour, so it is not a container edge and is not faked in tests.

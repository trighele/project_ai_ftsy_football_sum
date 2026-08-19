# 07 — Read a summary as prose, and copy it as Markdown

**What to build:** A summary is shown as formatted prose — headings, bullets, bold, tables — instead of as Markdown source. The source is still there, one click away in a collapsed disclosure, the same gesture the application already uses for showing an underlying error. A **Copy** button beside the existing Download hands over exactly the document the download hands over, front matter included, and works on the deployed box over plain HTTP.

A live run keeps streaming plain text as Claude writes it and formats itself when it finishes, without a reload — the terminal event carries the rendered summary the way it already carries the run's identifier. That a live run reads raw until it ends is the accepted cost of rendering on the server (ADR-0004).

**Blocked by:** 06 — Build the stylesheet on Windows.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] A saved run's page shows its summary rendered: headings, lists, emphasis, links, code, and tables
- [ ] Raw HTML in a summary is rendered as visible text, never as markup
- [ ] The Markdown source is present on the page in a disclosure, collapsed by default
- [ ] A live run streams plain text, then swaps in the rendered summary when it ends, with no reload and no extra request
- [ ] The rendered summary matches what the streamed pieces assembled to
- [ ] A **Copy** control sits beside Download on the run page and on a finished live run, and hands over the same document as the download
- [ ] Copy works where the modern clipboard API is unavailable, which is how the deployment is served
- [ ] The button confirms it copied
- [ ] Prose styling matches the existing palette, and a wide table scrolls inside its own container rather than pushing the page sideways
- [ ] History rows gain no Copy control
- [ ] The stylesheet is rebuilt and committed

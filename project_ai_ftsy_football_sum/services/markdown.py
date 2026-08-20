"""The summary's Markdown, as the HTML the reader actually reads.

Markdown in, HTML out, and nothing else: no options, no branches, no state, so
the same summary renders to the same page every time. That matters more here
than it looks — the rendered prose and the document the download and the
clipboard hand over are two views of one summary, and prose that says something
its source does not is a lie about what Claude wrote.

Raw HTML is **escaped rather than filtered**. There is no allowlist to keep
correct and no case where Claude has a legitimate reason to emit markup, so
model output that looks like a tag arrives as the text it is. `markdown-it-py`
with `html` off does that for HTML blocks and inline tags, and validates link
and image targets against its own scheme list, which is what keeps a
`javascript:` destination out of an `href`.

This is the first dependency in the application whose only job is presentation.
It is pure and touches no network, so it is not a container edge and is not
faked anywhere — a test asserts on the HTML it produced.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

#: The renderer, built once. CommonMark, plus tables, because the output
#: contract asks for them; auto-linking and typographic substitution stay off
#: so that nothing appears in the prose that is not in the source.
_RENDERER = MarkdownIt(
    "commonmark", {"html": False, "linkify": False, "typographer": False}
).enable("table")


def render_markdown(text: str) -> str:
    """`text` as HTML, ready to be placed in a page.

    The result is markup and is inserted unescaped, which is safe only because
    of what the renderer above does *not* do. Nothing else may render a summary.
    """
    return _RENDERER.render(text)

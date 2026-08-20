"""A saved run as a Markdown file somebody can keep.

The file has to stand on its own once it is out of the browser: opened in a
notes app a week later, it must say which episode it is, when that episode went
up, and where it came from. So the document carries its own front matter rather
than relying on whatever Claude happened to write at the top of the summary.
"""

from __future__ import annotations

import re

from project_ai_ftsy_football_sum.services.store import Run

#: Used when a title is all punctuation, or empty, and slugifies to nothing.
_FALLBACK_SLUG = "episode-summary"

#: Enough of a title to recognise the file by, without an unwieldy name.
_MAX_SLUG_LENGTH = 60

_NOT_SLUGGABLE = re.compile(r"[^a-z0-9]+")

#: How a context note is written into the front matter: YAML's block-scalar
#: indicator, then every line indented under it. A note can contain newlines,
#: and an inline value would end at the first of them. Two-space indentation
#: would not do either — under a list item that is a lazy continuation, and a
#: reader would get the whole note run into one paragraph. Six spaces is four
#: past the item's own content, which is a literal block in Markdown as well as
#: in YAML, so the note's lines survive being read *and* being rendered.
_NOTE_SCALAR = "|"
_NOTE_INDENT = " " * 6


def markdown_document(run: Run) -> str:
    """The whole downloadable file for a run."""
    facts = [f"- **Uploaded:** {run.upload_date_label}"]
    if run.channel:
        facts.insert(0, f"- **Channel:** {run.channel}")
    facts.append(f"- **Summarized:** {run.created_at_label}")
    # Which season's players it was written against is part of what it says: in
    # the preseason that is last autumn's depth charts, and the file is read
    # somewhere the app's own warnings cannot follow it.
    if run.season:
        facts.append(f"- **Player reference:** {run.season} season")
    facts.append(f"- **Source:** {run.url}")
    # Last, because it is the one field that runs to several lines. What was
    # asked for shaped what came back, and a file that hides that is misleading
    # a month later.
    if run.context_note:
        facts.append(
            f"- **Context note:** {_NOTE_SCALAR}\n{_indented(run.context_note)}"
        )

    summary = (run.summary or "").strip()
    return "\n".join([f"# {run.title}", "", *facts, "", "---", "", summary, ""])


def _indented(note: str) -> str:
    """A note as the block that sits under its label, every line indented."""
    return "\n".join(f"{_NOTE_INDENT}{line}".rstrip() for line in note.splitlines())


def download_filename(run: Run) -> str:
    """What the file is called once it lands in somebody's downloads.

    Dated first where the date is known, so a folder of these sorts into the
    order the episodes were published.
    """
    parts = [run.upload_date.isoformat()] if run.upload_date else []
    parts.append(_slug(run.title))
    return f"{'-'.join(parts)}.md"


def _slug(title: str) -> str:
    slug = _NOT_SLUGGABLE.sub("-", title.lower()).strip("-")
    return slug[:_MAX_SLUG_LENGTH].strip("-") or _FALLBACK_SLUG

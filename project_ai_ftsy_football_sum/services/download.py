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


def markdown_document(run: Run) -> str:
    """The whole downloadable file for a run."""
    facts = [f"- **Uploaded:** {run.upload_date_label}"]
    if run.channel:
        facts.insert(0, f"- **Channel:** {run.channel}")
    facts.append(f"- **Summarized:** {run.created_at_label}")
    facts.append(f"- **Source:** {run.url}")

    summary = (run.summary or "").strip()
    return "\n".join([f"# {run.title}", "", *facts, "", "---", "", summary, ""])


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

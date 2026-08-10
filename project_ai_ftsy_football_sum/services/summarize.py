"""What Claude is asked for, and what it is handed to answer with.

The prompt is built here and nowhere else, so that the one thing a summary's
accuracy depends on lives in a single file. `SummaryRequest` is deliberately
the whole of what the Claude edge receives: a fake can record it and a test
can assert on every byte that reached the model, which is what the player
reference ticket needs and what a return value would not give it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from project_ai_ftsy_football_sum.services.transcripts import Episode

#: The output contract, carried over from the Gradio app unchanged: news items
#: naming a player or team with a description and a fantasy sentiment, then the
#: analysis sections. Editing this edits every summary the app writes.
SUMMARY_INSTRUCTIONS = """\
You are an assistant that analyzes and summarizes fantasy football podcast \
transcripts. Your goal is to produce a structured Markdown summary.

Rules:
- Always respond in Markdown format.
- Include the episode's title and upload date at the top of the summary.
- Start with a `## News Section` heading.
    - Use bullet points (`-`) for each piece of news.
    - For each item, include:
        - **Player/Team**: Name
        - **News**: Short description
        - **Sentiment**: Positive / Negative / Neutral (fantasy football \
perspective)
- After the news, create sections for:
    - `## Matchup Analysis`
    - `## Player Debates`
    - `## Waiver Wire Suggestions`
    - (Other relevant sections depending on content)
- Use concise bullet points for each insight.
- Keep tone professional, clear, and concise.
- The transcript comes from automatic captions, so names may be misspelled. \
Attribute a mention to the player the hosts clearly meant, and leave out \
anything you cannot place.\
"""


@dataclass(frozen=True)
class SummaryRequest:
    """Everything handed to the Claude edge to write one summary.

    `system` is a sequence of content blocks rather than one string because the
    player reference arrives as a block of its own, marked for caching. The
    transcript sits in the user turn, after that cached prefix.
    """

    model: str
    system: tuple[Mapping[str, Any], ...]
    user: str


class SummaryClient(Protocol):
    """The `claude` container edge: one summary, streamed as it is written."""

    def stream(self, request: SummaryRequest) -> Iterator[str]:
        """Yield the summary's text in the order Claude writes it."""


def system_blocks() -> tuple[Mapping[str, Any], ...]:
    """The system prompt, as the blocks it is sent in."""
    return ({"type": "text", "text": SUMMARY_INSTRUCTIONS},)


def user_turn(episode: Episode) -> str:
    """The turn carrying the episode itself.

    Title and upload date travel with the transcript rather than in the system
    prompt: they change every run, and everything above them is meant to stay
    byte-identical so the player reference block can be cached.
    """
    return (
        "Here is the transcript of a fantasy football podcast episode. "
        "Summarize it using the structure described above.\n\n"
        f"Title: {episode.title}\n"
        f"Upload date: {episode.upload_date_label}\n\n"
        f"Transcript:\n\n{episode.transcript}"
    )


def summary_request(episode: Episode, *, model: str) -> SummaryRequest:
    """The request that summarizes one episode."""
    return SummaryRequest(
        model=model, system=system_blocks(), user=user_turn(episode)
    )

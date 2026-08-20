"""What Claude is asked for, and what it is handed to answer with.

The prompt is built here and nowhere else, so that the one thing a summary's
accuracy depends on lives in a single file. `SummaryRequest` is deliberately
the whole of what the Claude edge receives: a fake can record it and a test
can assert on every byte that reached the model, which is what the player
reference ticket needs and what a return value would not give it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from project_ai_ftsy_football_sum.services.players import (
    FANTASY_POSITIONS,
    TIER_SIZE,
    PlayerReference,
    PlayerRow,
)
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
anything you cannot place.
- A player reference follows, for the season it names. Use it to place a \
surname-only mention on the right player and to state a player's team and \
position; do not contradict it.\
"""

#: How far down each position's depth chart the reference goes. Below the
#: third string a player is not being discussed on a fantasy podcast, and the
#: cut is what takes the reference from ~2,800 rows to ~700.
DEPTH_RANK_LIMIT = 3

#: The reference table's columns, in the order they are written. Depth rank and
#: ECR tier are two columns with two names on purpose — see ADR-0002.
REFERENCE_COLUMNS = ("Player", "Team", "Position", "Depth rank", "ECR tier", "ECR rank")

#: What a column holds nothing for. A visible gap rather than a blank cell, so
#: that a row with no ranking cannot be misread as a row with a ranking of zero.
MISSING = "-"

#: How the reader's own instruction is introduced in the user turn. Named as
#: theirs rather than as further context, so that Claude reads it as something
#: asked about this episode and not as another table it was handed — the player
#: reference is context too, and the two must not blur into one another.
CONTEXT_NOTE_LABEL = (
    "Context note from the reader — what they want this summary to pay "
    "attention to:"
)

#: How much of a context note is sent and kept. Room for a few sentences and a
#: roster; past it the note is cut rather than the run refused, because losing
#: the tail of a note is a smaller harm than losing the summary it asked for.
MAX_CONTEXT_NOTE_LENGTH = 2000

#: How the reference block is marked for prompt caching. Everything above and
#: including it is a cached prefix, which is why nothing that varies between
#: runs — no timestamp, no run identifier, no transcript — may appear in it.
CACHE_CONTROL: Mapping[str, Any] = {"type": "ephemeral"}

#: What the table is and how to read it. The two-numbers paragraph is the point
#: of the whole block: the old app handed Claude a depth-chart string and called
#: it a fantasy tier, and every summary it wrote inherited that mistake.
REFERENCE_INTRODUCTION = """\
Here is the player reference for the {season} NFL season — every player at a \
fantasy-relevant position sitting at depth rank {limit} or better on their \
team's depth chart, with their expert consensus ranking.

Each player carries two numbers and they mean different things:

- **Depth rank** is where the player sits on their own team's depth chart at \
their position. 1 is the starter. It describes who is on the field.
- **ECR tier** is which band of {tier_size} players their expert consensus \
ranking falls in. Tier 1 is a first-round pick. It describes fantasy value.
- **ECR rank** is that consensus ranking itself, for telling players within a \
tier apart. Lower is better.

Depth rank and ECR tier are independent and neither implies the other. A \
team's starting kicker is depth rank 1 and one of the lowest tiers; a backup \
running back behind a fragile starter can be depth rank 2 and worth more than \
somebody else's starter. Never describe a depth rank as a tier, or a tier as a \
position on a depth chart.

A player who is not listed here is not unknown — the table stops at depth rank \
{limit} and at fantasy positions. Report what the hosts said about them \
without asserting a team, position, or ranking you cannot see here.\
"""


def context_note_from(submitted: str | None) -> str | None:
    """The note as it will be sent, shown, and kept — or `None` for no note.

    Trimmed, because a stray space a reader cannot see should not change what
    is asked of Claude, and whitespace alone is not an instruction. Cut to
    length rather than refused: a wall of pasted text should cost its own tail
    and nothing else.
    """
    note = (submitted or "").strip()
    if not note:
        return None
    return note[:MAX_CONTEXT_NOTE_LENGTH].rstrip()


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


def prompt_rows(reference: PlayerReference) -> tuple[PlayerRow, ...]:
    """The slice of the reference Claude is given.

    Deliberately narrower than the Players page, which shows everything: the
    page is for exploring and the prompt is for accuracy per token. A row with
    no depth rank is left out rather than guessed at — being on a roster is
    not the same as being on the field, and the table's whole claim is the
    latter.
    """
    return tuple(
        row
        for row in reference.rows
        if row.position in FANTASY_POSITIONS
        and row.depth_rank is not None
        and row.depth_rank <= DEPTH_RANK_LIMIT
    )


def reference_table(reference: PlayerReference) -> str:
    """The narrowed reference as the Markdown table Claude reads.

    The row order is the reference's own, which is sorted once when it is
    assembled — so this comes out the same way every time, which is what the
    cached prefix depends on.
    """
    return "\n".join(
        (
            _table_row(REFERENCE_COLUMNS),
            _table_row(("---",) * len(REFERENCE_COLUMNS)),
            *(_table_row(_cells(row)) for row in prompt_rows(reference)),
        )
    )


def _cells(row: PlayerRow) -> tuple[str, ...]:
    # `prompt_rows` has already dropped every row without a position or a
    # depth rank, so the ranking columns are the only ones that can be absent.
    return (
        row.player_name,
        row.team,
        str(row.position),
        str(row.depth_rank),
        MISSING if row.ecr_tier is None else str(row.ecr_tier),
        MISSING if row.ecr_rank is None else f"{row.ecr_rank:.1f}",
    )


def _table_row(cells: Sequence[str]) -> str:
    return f"| {' | '.join(cells)} |"


def reference_block(reference: PlayerReference) -> Mapping[str, Any]:
    """The player reference, as the cached block of the system prompt.

    Everything in here has to be byte-stable between runs: the block is the
    cached prefix, and a single byte that moves invalidates the cache silently,
    with a full-price run and no error to say why. So the season goes in — it
    is a fact about the data, and it changes only when the data does — and the
    sync time stays out.
    """
    introduction = REFERENCE_INTRODUCTION.format(
        season=reference.season, limit=DEPTH_RANK_LIMIT, tier_size=TIER_SIZE
    )
    return {
        "type": "text",
        "text": f"{introduction}\n\n{reference_table(reference)}",
        "cache_control": CACHE_CONTROL,
    }


def system_blocks(reference: PlayerReference) -> tuple[Mapping[str, Any], ...]:
    """The system prompt, as the blocks it is sent in.

    Instructions first, then the reference: both are the same between runs, so
    marking the last of them for caching caches the pair.
    """
    return (
        {"type": "text", "text": SUMMARY_INSTRUCTIONS},
        reference_block(reference),
    )


def user_turn(episode: Episode) -> str:
    """The turn carrying the episode itself.

    Title, upload date, and the reader's context note travel with the
    transcript rather than in the system prompt: they change every run, and
    everything above them is meant to stay byte-identical so the player
    reference block can be cached. A note in the system prompt would invalidate
    that cache on every episode, silently, at full price.

    An episode with no note produces exactly the turn it produced before notes
    existed — no empty label and no stray blank line — so that the ordinary
    case is not paying for the feature in tokens or in noise.
    """
    parts = [
        "Here is the transcript of a fantasy football podcast episode. "
        "Summarize it using the structure described above.\n\n",
        f"Title: {episode.title}\n",
        f"Upload date: {episode.upload_date_label}\n",
    ]
    if episode.context_note:
        parts.append(f"\n{CONTEXT_NOTE_LABEL}\n{episode.context_note}\n")
    parts.append(f"\nTranscript:\n\n{episode.transcript}")
    return "".join(parts)


def summary_request(
    episode: Episode, reference: PlayerReference, *, model: str
) -> SummaryRequest:
    """The request that summarizes one episode against one player reference."""
    return SummaryRequest(
        model=model, system=system_blocks(reference), user=user_turn(episode)
    )

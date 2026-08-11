"""What Claude is told about players, asserted on the fake it was told it to.

This is the file the test seam exists for. A player reference that is plausible
and wrong — the season before last, depth rank read as a fantasy tier, the
narrowing filter dropping the wrong rows — produces a summary that reads
perfectly and is wrong, and nothing downstream of the prompt can catch it. So
what is asserted here is the bytes the Claude edge received.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator, Mapping
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import create_app
from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.players import CACHE_TTL, calendar_season
from project_ai_ftsy_football_sum.services.store import RunStore
from project_ai_ftsy_football_sum.services.summarize import CACHE_CONTROL
from tests.events import run_episode
from tests.fakes import FakeClaudeClient, FakeNflverseSource, FakeYouTubeSource
from tests.test_players_page import age_the_cache, page

#: The columns Claude is given, written out rather than read off the
#: implementation: what they are *called* is half of what this file defends.
#: A reference whose columns were renamed to `Tier` would be the exact defect
#: ADR-0002 exists to correct, and it has to fail here.
REFERENCE_COLUMNS = ("Player", "Team", "Position", "Depth rank", "ECR tier", "ECR rank")

#: The header row of the reference table, as the prompt writes it.
HEADER = "| Player | Team | Position | Depth rank | ECR tier | ECR rank |"

#: The positions a fantasy manager can start, and how far down a depth chart
#: the reference goes. Also written out: the narrowing is the requirement, so
#: reading the implementation's own filter back would assert nothing.
STARTABLE_POSITIONS = frozenset({"QB", "RB", "FB", "WR", "TE", "K"})
DEPTH_CUTOFF = 3


def reference_block(claude: FakeClaudeClient) -> Mapping[str, Any]:
    """The one system block carrying the player reference."""
    blocks = [block for block in claude.request.system if HEADER in block["text"]]
    assert len(blocks) == 1, claude.request.system
    return blocks[0]


def reference_text(claude: FakeClaudeClient) -> str:
    return str(reference_block(claude)["text"])


def listed(claude: FakeClaudeClient) -> list[list[str]]:
    """Every player row of the table, as its cells."""
    rows = []
    for line in reference_text(claude).splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == len(REFERENCE_COLUMNS) and cells != list(REFERENCE_COLUMNS):
            rows.append(cells)
    return [cells for cells in rows if not all(set(cell) <= {"-"} for cell in cells)]


def row_for(claude: FakeClaudeClient, player: str) -> list[str]:
    matching = [cells for cells in listed(claude) if cells[0] == player]
    assert len(matching) == 1, f"{player} is not in the reference"
    return matching[0]


def system_text(claude: FakeClaudeClient) -> str:
    return "".join(block["text"] for block in claude.request.system)


@pytest.fixture
def last_season_app(
    youtube: FakeYouTubeSource, claude: FakeClaudeClient, app_store: RunStore
) -> Iterator[TestClient]:
    """An app whose nflverse holds nothing for the current calendar season.

    The preseason, which is where the app stands at the time of writing: the
    season the reference actually describes is the one before this one.
    """
    container = Container()
    container.override(
        captions=youtube,
        nflverse=FakeNflverseSource(seasons=[calendar_season() - 1]),
        claude=claude,
    )
    with TestClient(create_app(container=container, store=app_store)) as client:
        yield client


# --- The reference in the prompt ------------------------------------------


def test_the_system_prompt_carries_the_player_reference_as_a_table(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    assert HEADER in reference_text(claude)
    assert row_for(claude, "Bijan Robinson")


def test_depth_rank_and_ecr_tier_are_two_separately_labelled_columns(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """The conflation ADR-0002 exists to correct, pinned in the prompt.

    The header is asserted as the literal line it has to be: a column labelled
    `Tier` alone is the defect, and would read as an implementation detail if
    the expectation were built from the implementation's own constant.
    """
    run_episode(client)

    text = reference_text(claude)
    assert HEADER in text
    assert "| Tier |" not in text
    assert "| Rank |" not in text


def test_the_prompt_explains_that_the_two_numbers_are_independent(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """Two labelled columns are no use if Claude reads one as the other."""
    run_episode(client)

    text = reference_text(claude).lower()
    assert "depth chart" in text
    assert "fantasy value" in text
    assert "neither implies the other" in text


def test_a_starting_kicker_is_depth_rank_one_and_a_bottom_ecr_tier(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """On the field every week, and not worth starting. The whole row is
    pinned, because a transposition is what this file exists to catch."""
    run_episode(client)

    assert row_for(claude, "Younghoe Koo") == [
        "Younghoe Koo",
        "ATL",
        "K",
        "1",
        "12",
        "140.0",
    ]


def test_a_first_round_running_back_is_depth_rank_one_and_the_top_ecr_tier(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    assert row_for(claude, "Bijan Robinson") == [
        "Bijan Robinson",
        "ATL",
        "RB",
        "1",
        "1",
        "3.3",
    ]


def test_a_player_with_no_ranking_still_carries_their_depth_rank(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """An absent tier is written as absent rather than left out or made up."""
    run_episode(client)

    assert row_for(claude, "Casey Washington") == [
        "Casey Washington",
        "ATL",
        "WR",
        "3",
        "-",
        "-",
    ]


# --- What the narrowing leaves out ----------------------------------------


def test_players_below_the_depth_cutoff_are_left_out(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """A fourth-string receiver is not who the hosts are talking about."""
    run_episode(client)

    assert "Ray-Ray McCloud" in page(client)
    assert "Ray-Ray McCloud" not in reference_text(claude)


def test_positions_nobody_starts_in_fantasy_are_left_out(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    body = page(client)
    for player in ("Kaden Elliss", "Bradley Pinion"):
        assert player in body
        assert player not in reference_text(claude)


def test_every_listed_player_is_a_startable_position_at_the_cutoff_or_better(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    rows = listed(claude)
    assert rows
    for cells in rows:
        assert cells[REFERENCE_COLUMNS.index("Position")] in STARTABLE_POSITIONS
        assert int(cells[REFERENCE_COLUMNS.index("Depth rank")]) <= DEPTH_CUTOFF


def test_the_prompt_says_the_table_is_a_slice_rather_than_the_whole_league(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """Otherwise an absent name reads as a player who does not exist."""
    run_episode(client)

    assert "not listed" in reference_text(claude)


# --- The cached prefix ----------------------------------------------------


def test_the_reference_block_is_marked_for_caching(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    assert reference_block(claude)["cache_control"] == CACHE_CONTROL


def test_two_consecutive_runs_produce_a_byte_identical_reference_block(
    client: TestClient,
    app: FastAPI,
    claude: FakeClaudeClient,
    nflverse: FakeNflverseSource,
) -> None:
    """A single varying byte costs the cache with nothing to say it did.

    Both ways a second run can get its reference are covered, because they are
    different code paths and either could drift: the second run reads the
    cached reference back out of SQLite, and the third re-syncs it from
    nflverse. A sync time or a round-tripped float that moved would show up
    here rather than on a bill.
    """
    run_episode(client)
    run_episode(client)
    age_the_cache(app, CACHE_TTL + timedelta(minutes=1))
    run_episode(client)

    blocks = [str(request.system[-1]["text"]) for request in claude.requests]
    assert nflverse.syncs == 2, "the middle run should have read the cache"
    assert len(blocks) == 3
    assert blocks[1] == blocks[0]
    assert blocks[2] == blocks[0]


def test_nothing_that_changes_between_runs_sits_inside_the_cached_prefix(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    system = system_text(claude)
    assert "Week 1 Waiver Wire Targets" not in system
    assert "7 August 2026" not in system
    assert "Welcome back to the Fantasy Fallout podcast." not in system
    assert not re.search(r"\d{4}-\d{2}-\d{2}T", system)


def test_the_episode_travels_in_the_user_turn_after_the_reference(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    user = claude.request.user
    assert "Week 1 Waiver Wire Targets" in user
    assert "7 August 2026" in user
    assert "Welcome back to the Fantasy Fallout podcast." in user


# --- The season the run used ----------------------------------------------


def test_the_reference_names_the_season_it_describes(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    run_episode(client)

    assert f"{calendar_season()} NFL season" in reference_text(claude)


def test_the_run_detail_view_shows_the_season_the_reference_came_from(
    client: TestClient, app_store: RunStore
) -> None:
    run_episode(client)

    body = html.unescape(client.get(f"/runs/{app_store.recent(1)[0].id}").text)

    assert f"{calendar_season()} player reference" in body


def test_a_run_behind_the_calendar_season_uses_and_records_that_season(
    last_season_app: TestClient, claude: FakeClaudeClient, app_store: RunStore
) -> None:
    """The preseason case: last year's depth charts, said out loud everywhere.

    Silently summarizing against nothing, or against a season the run does not
    admit to, is the failure this defends — both read perfectly.
    """
    resolved = calendar_season() - 1

    run_episode(last_season_app)

    saved = app_store.recent(1)[0]
    assert saved.season == resolved
    assert f"{resolved} NFL season" in reference_text(claude)
    assert row_for(claude, "Bijan Robinson")

    body = html.unescape(last_season_app.get(f"/runs/{saved.id}").text)
    assert f"{resolved} player reference" in body

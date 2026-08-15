"""The Players page: the reference, the season it belongs to, and its age.

Driven through the HTTP boundary like the rest of the suite. The nflverse edge
is replaced with fixture Polars frames, so what is under test is the whole path
from the frames nflreadpy would return to the row a reader sees.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from dataclasses import astuple, replace
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import create_app
from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.players import (
    CACHE_TTL,
    PlayerRow,
    calendar_season,
)
from project_ai_ftsy_football_sum.services.store import RunStore
from tests import events as sse
from tests.events import run_episode
from tests.fakes import FakeClaudeClient, FakeNflverseSource, FakeYouTubeSource

#: Every cell of the table, in the order they are written in the template.
COLUMNS = (
    "Player",
    "Team",
    "Position",
    "Depth rank",
    "ECR tier",
    "ECR rank",
    "Bye",
    "Injury status",
)


def page(client: TestClient, path: str = "/players") -> str:
    """The page as a reader sees it, entities resolved back to characters."""
    response = client.get(path)
    assert response.status_code == 200, response.text
    return html.unescape(response.text)


def row_for(body: str, player: str) -> list[str]:
    """The table cells for one player, as text."""
    found = re.search(
        rf"<tr[^>]*>(?:(?!</tr>).)*?{re.escape(player)}.*?</tr>", body, re.S
    )
    assert found is not None, f"{player} is not in the table"
    cells = re.findall(r"<t[dh].*?</t[dh]>", found.group(0), re.S)
    return [" ".join(re.sub(r"<[^>]+>", " ", cell).split()) for cell in cells]


def age_the_cache(app: FastAPI, age: timedelta) -> None:
    """Push the cached reference's sync time into the past."""
    cache = app.state.players
    reference = cache.load()
    assert reference is not None, "nothing has been cached yet"
    cache.save(replace(reference, synced_at=reference.synced_at - age))


@pytest.fixture
def last_season_client(
    youtube: FakeYouTubeSource, claude: FakeClaudeClient, app_store: RunStore
) -> Iterator[TestClient]:
    """An app whose nflverse holds nothing for the current calendar season.

    Preseason, before the new year's depth charts are published — which is
    where the app stands at the time of writing, not a rare edge case.
    """
    container = Container()
    container.override(
        captions=youtube,
        nflverse=FakeNflverseSource(seasons=[calendar_season() - 1]),
        claude=claude,
    )
    with TestClient(create_app(container=container, store=app_store)) as client:
        yield client


# --- The page -------------------------------------------------------------


def test_the_page_renders_the_whole_player_reference(
    client: TestClient, nflverse: FakeNflverseSource
) -> None:
    body = page(client)

    assert nflverse.syncs == 1
    for player in (
        "Bijan Robinson",
        "Tyler Allgeier",
        "Drake London",
        "Michael Penix Jr.",
        "Younghoe Koo",
        "Casey Washington",
        "Ja'Marr Chase",
        "Joe Burrow",
        "Chase Brown",
    ):
        assert player in body


def test_depth_rank_and_ecr_tier_are_distinct_columns(client: TestClient) -> None:
    """The conflation ADR-0002 exists to correct, pinned as a column set."""
    body = page(client)

    for column in COLUMNS:
        assert column in body
    assert ">Tier<" not in body
    assert ">Rank<" not in body


def test_a_starting_kicker_is_depth_rank_one_and_a_bottom_ecr_tier(
    client: TestClient,
) -> None:
    """The example from CONTEXT.md: on the field, not worth starting.

    Reading this row as a fantasy tier is exactly the defect being fixed, so
    the whole row is pinned rather than the two numbers separately.
    """
    assert row_for(page(client), "Younghoe Koo") == [
        "Younghoe Koo",
        "ATL",
        "K",
        "1",
        "12",
        "140.0",
        "11",
        "—",
    ]


def test_a_first_round_running_back_is_depth_rank_one_and_the_top_ecr_tier(
    client: TestClient,
) -> None:
    assert row_for(page(client), "Bijan Robinson") == [
        "Bijan Robinson",
        "ATL",
        "RB",
        "1",
        "1",
        "3.3",
        "11",
        "—",
    ]


def test_a_players_depth_rank_comes_from_their_own_unit_not_special_teams(
    client: TestClient,
) -> None:
    """Drake London returns punts first-string and lines up as the second WR."""
    cells = row_for(page(client), "Drake London")

    assert cells[COLUMNS.index("Depth rank")] == "2"


def test_only_the_most_recent_depth_chart_snapshot_counts(client: TestClient) -> None:
    """nflverse keeps every scrape of the season; only the last one is current."""
    assert "Preseason Placeholder" not in page(client)


def test_injury_status_comes_from_the_current_week_only(client: TestClient) -> None:
    """A designation from an earlier week is worse than none: it gets acted on."""
    body = page(client)

    assert row_for(body, "Joe Burrow")[COLUMNS.index("Injury status")] == "Questionable"
    assert row_for(body, "Chase Brown")[COLUMNS.index("Injury status")] == "—"


def test_a_missing_injury_feed_leaves_the_column_blank_rather_than_failing(
    youtube: FakeYouTubeSource, claude: FakeClaudeClient, app_store: RunStore
) -> None:
    """nflverse refuses a season that has not kicked off yet — which in the
    preseason is the season whose depth charts we are reading."""
    container = Container()
    container.override(
        captions=youtube,
        nflverse=FakeNflverseSource(
            injuries_error=ValueError("Season must be between 2009 and 2025")
        ),
        claude=claude,
    )

    with TestClient(create_app(container=container, store=app_store)) as client:
        body = page(client)

    assert "Bijan Robinson" in body
    assert row_for(body, "Joe Burrow")[COLUMNS.index("Injury status")] == "—"


def test_an_unranked_player_still_gets_their_teams_bye_week(
    client: TestClient,
) -> None:
    cells = row_for(page(client), "Casey Washington")

    assert cells[COLUMNS.index("Bye")] == "11"
    assert cells[COLUMNS.index("ECR tier")] == "—"


def test_the_navigation_links_to_the_players_page(client: TestClient) -> None:
    assert 'href="/players"' in client.get("/").text


# --- The header strip -----------------------------------------------------


def test_the_header_strip_states_the_season_and_how_long_ago_it_synced(
    client: TestClient,
) -> None:
    body = page(client)

    assert f"{calendar_season()} season" in body
    assert "Synced just now" in body


def test_no_warning_when_the_reference_is_the_current_calendar_season(
    client: TestClient,
) -> None:
    assert "season behind" not in page(client)


def test_the_page_offers_sync_now(client: TestClient) -> None:
    body = page(client)

    assert "Sync now" in body
    assert 'hx-post="/players/sync"' in body


def test_sync_now_refreshes_the_reference_and_the_synced_time(
    client: TestClient, app: FastAPI, nflverse: FakeNflverseSource
) -> None:
    page(client)
    age_the_cache(app, timedelta(hours=5))
    assert "5 hours ago" in page(client)

    body = html.unescape(client.post("/players/sync").text)

    assert nflverse.syncs == 2
    assert "Synced just now" in body
    assert "5 hours ago" not in body
    assert "Bijan Robinson" in body


def test_a_sync_that_fails_says_so_and_keeps_what_was_there(
    client: TestClient, app: FastAPI, nflverse: FakeNflverseSource
) -> None:
    """Handing back the same strip would be a refusal dressed as a refresh."""
    page(client)
    age_the_cache(app, timedelta(hours=5))
    nflverse.error = RuntimeError("nflverse is unreachable")

    body = html.unescape(client.post("/players/sync").text)

    assert "Sync failed" in body
    assert "5 hours ago" in body
    assert "Bijan Robinson" in body


def test_a_page_with_nothing_cached_and_nflverse_down_still_renders(
    youtube: FakeYouTubeSource, claude: FakeClaudeClient, app_store: RunStore
) -> None:
    container = Container()
    container.override(
        captions=youtube,
        nflverse=FakeNflverseSource(error=RuntimeError("nflverse is unreachable")),
        claude=claude,
    )

    with TestClient(create_app(container=container, store=app_store)) as client:
        body = page(client)

    assert "Sync failed" in body
    assert "Sync now" in body


# --- The cache ------------------------------------------------------------


def test_a_fresh_cache_is_read_rather_than_synced_again(
    client: TestClient, nflverse: FakeNflverseSource
) -> None:
    page(client)
    body = page(client)

    assert nflverse.syncs == 1
    assert "Bijan Robinson" in body


def test_a_stale_cache_is_synced_again(
    client: TestClient, app: FastAPI, nflverse: FakeNflverseSource
) -> None:
    page(client)
    age_the_cache(app, CACHE_TTL + timedelta(minutes=1))

    page(client)

    assert nflverse.syncs == 2


def test_the_cached_reference_survives_a_restart(
    client: TestClient, app_store: RunStore, container: Container
) -> None:
    """The cache is on the same volume as the runs, so a redeploy keeps it."""
    page(client)

    with TestClient(create_app(container=container, store=app_store)) as restarted:
        assert "Bijan Robinson" in page(restarted)


def test_polars_frames_do_not_escape_the_player_service(
    client: TestClient, app: FastAPI
) -> None:
    page(client)

    reference = app.state.players.load()
    assert reference.rows
    for row in reference.rows:
        assert isinstance(row, PlayerRow)
        for value in astuple(row):
            assert value is None or isinstance(value, str | int | float)


# --- Season fallback ------------------------------------------------------


def test_with_no_data_for_this_season_the_most_recent_one_is_used(
    last_season_client: TestClient,
) -> None:
    body = page(last_season_client)

    assert f"{calendar_season() - 1} season" in body
    assert "Bijan Robinson" in body


def test_a_season_behind_the_calendar_season_is_warned_about(
    last_season_client: TestClient,
) -> None:
    body = page(last_season_client)

    assert "season behind" in body
    assert str(calendar_season()) in body


# --- What a run does with it ----------------------------------------------


def test_a_run_announces_that_it_loaded_the_player_reference(
    client: TestClient,
) -> None:
    assert sse.outline(run_episode(client)) == [
        "stage:captions",
        "stage:metadata",
        "transcript",
        "stage:players",
        "stage:summarizing",
        "summary",
        "done",
    ]


def test_a_run_records_the_season_its_player_reference_came_from(
    client: TestClient, app_store: RunStore
) -> None:
    run_episode(client)

    assert app_store.recent(1)[0].season == calendar_season()


def test_a_run_syncs_a_stale_reference_before_summarizing(
    client: TestClient, app: FastAPI, nflverse: FakeNflverseSource
) -> None:
    page(client)
    age_the_cache(app, CACHE_TTL + timedelta(minutes=1))

    run_episode(client)

    assert nflverse.syncs == 2


def test_a_run_leaves_a_fresh_reference_alone(
    client: TestClient, nflverse: FakeNflverseSource
) -> None:
    page(client)

    run_episode(client)

    assert nflverse.syncs == 1


def test_a_run_falls_back_to_the_cached_reference_when_nflverse_is_down(
    client: TestClient, app: FastAPI, nflverse: FakeNflverseSource
) -> None:
    """An upstream outage costs accuracy, not the whole summary."""
    page(client)
    age_the_cache(app, CACHE_TTL + timedelta(minutes=1))
    nflverse.error = RuntimeError("nflverse is unreachable")

    events = run_episode(client)

    assert sse.terminal(events).name == "done"


def test_a_run_fails_with_the_nflverse_kind_when_there_is_no_cache_at_all(
    client: TestClient, nflverse: FakeNflverseSource, app_store: RunStore
) -> None:
    nflverse.error = RuntimeError("nflverse is unreachable")

    failure = sse.terminal(run_episode(client))

    assert failure.name == "failed"
    assert failure.data["kind"] == "nflverse"
    assert app_store.recent(1) == []

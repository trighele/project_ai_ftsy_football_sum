"""Exploring the player reference: sorting, filtering, and searching it.

The whole reference is in the page and every control acts on it in the browser,
so what can be asserted from here is the contract between the two: that every
row is present, that each one carries the values the controls read, and that
nothing about exploring the table asks the server for anything.

The behaviour itself lives in `static/js/players.js`, which is why that contract
is pinned this precisely — it is the only thing holding the two halves together.
"""

from __future__ import annotations

import html
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_players_page import COLUMNS, page

#: The columns whose values are numbers, and so sort as numbers rather than as
#: the text of a number — where "10" would come before "9".
NUMERIC_COLUMNS = ("Depth rank", "ECR tier", "ECR rank", "Bye")


def row_tag(body: str, player: str) -> str:
    """The opening `<tr>` of one player's row, where its values are carried."""
    found = re.search(
        rf"(<tr[^>]*>)(?:(?!</tr>).)*?{re.escape(player)}", body, re.S
    )
    assert found is not None, f"{player} is not in the table"
    return found.group(1)


def filter_values(body: str, facet: str) -> list[str]:
    """The values offered by one multi-select filter, in the order shown."""
    return re.findall(
        rf'data-player-filter="{facet}"[^>]*?value="([^"]*)"',
        body,
    )


def controls(body: str) -> str:
    """The filter strip on its own."""
    found = re.search(r"<section[^>]*data-player-filters.*?</section>", body, re.S)
    assert found is not None, "the page has no filter strip"
    return found.group(0)


def header_for(body: str, column: str) -> str:
    """One column's header cell, and no part of any other."""
    found = re.search(rf"<th(?:(?!<th).)*?{re.escape(column)}\s*<", body, re.S)
    assert found is not None, f"there is no {column} column"
    return found.group(0)


# --- What the browser is given ---------------------------------------------


def test_the_page_ships_every_row_of_the_reference(
    client: TestClient, app: FastAPI
) -> None:
    """Filtering client-side is only honest if nothing was filtered out first."""
    body = page(client)
    reference = app.state.players.load()

    assert len(re.findall(r"data-player-row", body)) == len(reference.rows)


def test_every_row_carries_the_values_the_filters_read(client: TestClient) -> None:
    tag = row_tag(page(client), "Younghoe Koo")

    assert 'data-player-name="younghoe koo"' in tag
    assert 'data-team="ATL"' in tag
    assert 'data-position="K"' in tag
    assert 'data-depth-rank="1"' in tag
    assert 'data-ecr-tier="12"' in tag
    assert 'data-bye-week="11"' in tag


def test_a_row_missing_a_value_carries_no_attribute_for_it(
    client: TestClient,
) -> None:
    """An absent value sorts and filters as absent, not as zero or as "—"."""
    tag = row_tag(page(client), "Casey Washington")

    assert "data-ecr-tier" not in tag
    assert "data-ecr-rank" not in tag
    assert 'data-bye-week="11"' in tag


# --- Sorting ---------------------------------------------------------------


def test_every_column_sorts(client: TestClient) -> None:
    body = page(client)

    for column in COLUMNS:
        assert re.search(
            rf'<th[^>]*>\s*<button[^>]*data-player-sort="[^"]+"[^>]*>\s*{column}',
            body,
        ), f"the {column} column has no sort control"


def test_the_number_columns_sort_as_numbers(client: TestClient) -> None:
    """Sorted as text, depth rank 10 would come before depth rank 9."""
    body = page(client)

    for column in COLUMNS:
        numeric = "data-player-sort-numeric" in header_for(body, column)
        assert numeric == (column in NUMERIC_COLUMNS), column


def test_the_sort_state_is_announced(client: TestClient) -> None:
    """A column that can be sorted says which way it currently is."""
    assert len(re.findall(r'aria-sort="none"', page(client))) == len(COLUMNS)


def test_number_columns_use_tabular_numerals(client: TestClient) -> None:
    """So that a column of ranks reads as a column."""
    body = page(client)
    row = re.search(r"<tr[^>]*>(?:(?!</tr>).)*?Younghoe Koo.*?</tr>", body, re.S)
    assert row is not None

    assert len(re.findall(r"tabular-nums", row.group(0))) == len(NUMERIC_COLUMNS)


# --- Filtering -------------------------------------------------------------


def test_teams_filter_as_a_multi_select(client: TestClient, app: FastAPI) -> None:
    body = page(client)
    teams = sorted({row.team for row in app.state.players.load().rows})

    assert filter_values(body, "team") == teams
    assert "ATL" in teams and "CIN" in teams


def test_positions_filter_as_a_multi_select(client: TestClient, app: FastAPI) -> None:
    body = page(client)
    positions = sorted(
        {row.position for row in app.state.players.load().rows if row.position}
    )

    assert filter_values(body, "position") == positions
    assert "RB" in positions and "K" in positions


def test_the_filters_are_checkboxes_so_they_combine(client: TestClient) -> None:
    """Combining rather than replacing is what makes them worth having."""
    strip = controls(page(client))

    for facet in ("team", "position"):
        for offered in re.findall(rf'<input[^>]*data-player-filter="{facet}"[^>]*>', strip):
            assert 'type="checkbox"' in offered


def test_a_depth_rank_cutoff_is_offered(client: TestClient) -> None:
    strip = controls(page(client))

    assert "data-player-depth" in strip
    for cutoff in ("1", "2", "3"):
        assert f'value="{cutoff}"' in strip


def test_a_name_search_narrows_the_table(client: TestClient) -> None:
    strip = controls(page(client))

    assert 'type="search"' in strip
    assert "data-player-search" in strip


def test_the_count_of_what_is_showing_is_on_the_page(
    client: TestClient, app: FastAPI
) -> None:
    body = page(client)
    total = len(app.state.players.load().rows)

    assert re.search(rf"data-player-shown[^>]*>\s*{total}\s*<", body)


def test_the_filters_can_be_cleared(client: TestClient) -> None:
    assert "data-player-reset" in controls(page(client))


# --- No round trip ---------------------------------------------------------


def test_exploring_the_table_asks_the_server_for_nothing(client: TestClient) -> None:
    """The reference is already here; a filter that fetched would be a form."""
    strip = controls(page(client))

    assert "hx-" not in strip
    assert "<form" not in strip


def test_the_only_request_the_page_itself_makes_is_sync_now(
    client: TestClient,
) -> None:
    """Everything else the reader can do to the table happens in the browser."""
    main = re.search(r"<main.*?</main>", page(client), re.S)
    assert main is not None

    assert re.findall(r'hx-(?:get|post|delete)="([^"]*)"', main.group(0)) == [
        "/players/sync"
    ]


def test_the_page_loads_the_script_that_does_the_exploring(
    client: TestClient,
) -> None:
    assert "/static/js/players.js" in page(client)


def test_a_synced_reference_comes_back_with_its_controls(client: TestClient) -> None:
    """**Sync now** replaces the whole section, table and controls together."""
    page(client)

    body = html.unescape(client.post("/players/sync").text)

    assert "data-player-search" in body
    assert 'data-player-filter="team"' in body
    assert "data-player-row" in body

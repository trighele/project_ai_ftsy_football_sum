"""Every run is findable afterwards, downloadable, and deletable.

The home page keeps the last five runs; this is the page that keeps the rest.
Driven through the HTTP boundary against a real SQLite store, like the saved-run
tests it follows on from.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.app import RECENT_RUN_LIMIT
from project_ai_ftsy_football_sum.services.players import calendar_season
from tests.events import EPISODE_URL, run_episode, run_titled
from tests.fakes import FakeYouTubeSource

EPISODE_TITLE = "Week 1 Waiver Wire Targets"
TRANSCRIPT_OPENING = "Welcome back to the Fantasy Fallout podcast."
SUMMARY_LINE = "The Falcons are talking about a bigger role."


def run_ids(body: str) -> list[int]:
    """The identifiers of the runs a page links to, in the order they appear."""
    return [int(found) for found in re.findall(r'href="/runs/(\d+)"', body)]


def only_run_id(client: TestClient) -> int:
    (run_id,) = run_ids(client.get("/history").text)
    return run_id


def test_history_lists_every_saved_run_not_just_the_recent_few(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """The point of the page: the run from weeks ago is still here."""
    total = RECENT_RUN_LIMIT + 3
    for number in range(1, total + 1):
        run_titled(client, youtube, f"Episode {number}")

    body = client.get("/history").text

    assert len(run_ids(body)) == total
    for number in range(1, total + 1):
        assert f"Episode {number}" in body


def test_history_lists_the_most_recent_run_first(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    for number in (1, 2, 3):
        run_titled(client, youtube, f"Episode {number}")

    body = client.get("/history").text

    assert body.index("Episode 3") < body.index("Episode 2") < body.index("Episode 1")


def test_history_orders_by_the_episodes_own_date_not_the_day_it_was_summarized(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """Catching up on a backlog out of order must not scramble the list."""
    run_titled(client, youtube, "July Episode", uploaded="20260703")
    run_titled(client, youtube, "August Episode", uploaded="20260812")
    run_titled(client, youtube, "June Episode", uploaded="20260619")

    body = client.get("/history").text

    assert (
        body.index("August Episode")
        < body.index("July Episode")
        < body.index("June Episode")
    )


def test_a_run_whose_upload_date_never_resolved_sorts_to_the_bottom(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """An unknown date is not a recent one, whenever the run happened."""
    run_titled(client, youtube, "June Episode", uploaded="20260619")
    run_titled(client, youtube, "Undated Episode", uploaded="")

    body = client.get("/history").text

    assert body.index("June Episode") < body.index("Undated Episode")


def test_two_episodes_uploaded_the_same_day_fall_back_to_the_order_they_were_run(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    run_titled(client, youtube, "Morning Show", uploaded="20260812")
    run_titled(client, youtube, "Evening Show", uploaded="20260812")

    body = client.get("/history").text

    assert body.index("Evening Show") < body.index("Morning Show")


def test_a_search_returns_its_matches_in_episode_order(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """Search is a filter over the list, not a differently ordered list."""
    run_titled(client, youtube, "Waiver Wire July", uploaded="20260703")
    run_titled(client, youtube, "Injury Report August", uploaded="20260812")
    run_titled(client, youtube, "Waiver Wire August", uploaded="20260814")
    run_titled(client, youtube, "Waiver Wire June", uploaded="20260619")

    body = client.get("/history", params={"q": "waiver"}).text

    assert "Injury Report August" not in body
    assert (
        body.index("Waiver Wire August")
        < body.index("Waiver Wire July")
        < body.index("Waiver Wire June")
    )


def test_deleting_a_run_returns_the_rest_in_episode_order(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """A delete must not reshuffle the list the reader was looking at."""
    run_titled(client, youtube, "July Episode", uploaded="20260703")
    run_titled(client, youtube, "August Episode", uploaded="20260812")
    run_titled(client, youtube, "June Episode", uploaded="20260619")
    doomed = run_ids(client.get("/history").text)[1]

    body = client.delete(f"/runs/{doomed}").text

    assert "July Episode" not in body
    assert body.index("August Episode") < body.index("June Episode")


def test_a_history_row_says_what_the_episode_was_and_when_it_was_summarized(
    client: TestClient,
) -> None:
    run_episode(client)

    body = client.get("/history").text

    assert EPISODE_TITLE in body
    assert "Fantasy Fallout" in body
    assert "7 August 2026" in body  # the episode's upload date
    assert "Summarized" in body


def test_history_says_so_when_nothing_has_been_run_yet(client: TestClient) -> None:
    body = client.get("/history").text

    assert run_ids(body) == []
    assert "No runs yet" in body


def test_searching_by_title_narrows_the_list(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    run_titled(client, youtube, "Waiver Wire Week 1")
    run_titled(client, youtube, "Injury Report Week 2")

    body = client.get("/history", params={"q": "waiver"}).text

    assert "Waiver Wire Week 1" in body
    assert "Injury Report Week 2" not in body
    assert len(run_ids(body)) == 1


def test_a_search_matching_nothing_says_so_rather_than_looking_empty(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    run_titled(client, youtube, "Waiver Wire Week 1")

    body = client.get("/history", params={"q": "kickers"}).text

    assert run_ids(body) == []
    assert "kickers" in body
    assert "No runs match" in body


def test_a_search_keeps_its_term_in_the_box(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    run_titled(client, youtube, "Waiver Wire Week 1")

    body = client.get("/history", params={"q": "waiver"}).text

    assert 'value="waiver"' in body


def test_search_wildcards_are_matched_as_typed(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """`%` is a SQL wildcard, and a title with one in it is a title."""
    run_titled(client, youtube, "100% Start Em Sit Em")
    run_titled(client, youtube, "Injury Report Week 2")

    body = client.get("/history", params={"q": "100%"}).text

    assert "100% Start Em Sit Em" in body
    assert "Injury Report Week 2" not in body


def test_the_history_list_is_fetchable_on_its_own_for_live_search(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """The search box swaps this fragment in as it is typed into."""
    run_titled(client, youtube, "Waiver Wire Week 1")
    run_titled(client, youtube, "Injury Report Week 2")

    response = client.get("/fragments/history", params={"q": "injury"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert 'id="history-list"' in body
    assert "Injury Report Week 2" in body
    assert "Waiver Wire Week 1" not in body
    # A fragment, not a whole document.
    assert "<html" not in body


def test_opening_a_run_from_history_shows_its_transcript_and_summary(
    client: TestClient,
) -> None:
    run_episode(client)
    run_id = only_run_id(client)

    body = client.get(f"/runs/{run_id}").text

    assert TRANSCRIPT_OPENING in body
    assert SUMMARY_LINE in body


def test_downloading_a_run_hands_over_a_markdown_file(client: TestClient) -> None:
    run_episode(client)
    run_id = only_run_id(client)

    response = client.get(f"/runs/{run_id}/download")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert 'filename="2026-08-07-week-1-waiver-wire-targets.md"' in disposition


def test_the_downloaded_markdown_stands_on_its_own(client: TestClient) -> None:
    """Opened in a notes app, it says which episode it is and when it went up."""
    run_episode(client)
    run_id = only_run_id(client)

    document = client.get(f"/runs/{run_id}/download").text

    assert document.startswith(f"# {EPISODE_TITLE}")
    assert "7 August 2026" in document
    assert "Fantasy Fallout" in document
    assert EPISODE_URL in document
    assert SUMMARY_LINE in document
    # Which season's players it was summarized against travels with the file:
    # nothing else out here says so.
    assert f"{calendar_season()} season" in document


def test_a_download_says_the_upload_date_is_unknown_rather_than_omitting_it(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    youtube.metadata_error = RuntimeError("Sign in to confirm you are not a bot")

    run_episode(client)
    run_id = only_run_id(client)
    document = client.get(f"/runs/{run_id}/download").text

    assert "Upload date unknown" in document


def test_history_offers_the_download_for_each_run(client: TestClient) -> None:
    run_episode(client)
    run_id = only_run_id(client)

    body = client.get("/history").text

    assert f'href="/runs/{run_id}/download"' in body


def test_downloading_a_run_that_does_not_exist_is_a_404(client: TestClient) -> None:
    assert client.get("/runs/404404/download").status_code == 404


def test_deleting_a_run_takes_one_request_and_returns_the_list_without_it(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """No confirmation dance: the button deletes, and the list comes back."""
    run_titled(client, youtube, "Waiver Wire Week 1")
    run_titled(client, youtube, "Injury Report Week 2")
    doomed = run_ids(client.get("/history").text)[0]

    response = client.delete(f"/runs/{doomed}")

    assert response.status_code == 200
    body = response.text
    assert 'id="history-list"' in body
    assert "Injury Report Week 2" not in body
    assert "Waiver Wire Week 1" in body


def test_a_deleted_run_is_gone_from_history(client: TestClient) -> None:
    run_episode(client)
    run_id = only_run_id(client)

    client.delete(f"/runs/{run_id}")

    body = client.get("/history").text
    assert run_ids(body) == []
    assert EPISODE_TITLE not in body


def test_a_deleted_run_is_gone_from_the_home_pages_recent_list(
    client: TestClient,
) -> None:
    run_episode(client)
    run_id = only_run_id(client)

    client.delete(f"/runs/{run_id}")

    body = client.get("/").text
    assert run_ids(body) == []
    assert "No runs yet" in body


def test_a_deleted_run_can_no_longer_be_reopened(client: TestClient) -> None:
    run_episode(client)
    run_id = only_run_id(client)

    client.delete(f"/runs/{run_id}")

    assert client.get(f"/runs/{run_id}").status_code == 404
    assert client.get(f"/runs/{run_id}/download").status_code == 404


def test_deleting_from_a_search_comes_back_to_that_search(
    client: TestClient, youtube: FakeYouTubeSource
) -> None:
    """Delete one of the results and the other results are still the ones shown."""
    run_titled(client, youtube, "Waiver Wire Week 1")
    run_titled(client, youtube, "Waiver Wire Week 2")
    run_titled(client, youtube, "Injury Report Week 2")
    doomed = run_ids(client.get("/history", params={"q": "waiver"}).text)[0]

    body = client.delete(f"/runs/{doomed}", params={"q": "waiver"}).text

    assert "Waiver Wire Week 1" in body
    assert "Waiver Wire Week 2" not in body
    assert "Injury Report Week 2" not in body


def test_deleting_a_run_that_does_not_exist_is_a_404(client: TestClient) -> None:
    assert client.delete("/runs/404404").status_code == 404


def test_history_wires_delete_to_the_row_it_deletes(client: TestClient) -> None:
    run_episode(client)
    run_id = only_run_id(client)

    body = client.get("/history").text

    assert f'hx-delete="/runs/{run_id}' in body
    assert 'hx-target="#history-list"' in body


def test_the_search_box_filters_without_a_page_reload(client: TestClient) -> None:
    body = client.get("/history").text

    assert 'hx-get="/fragments/history"' in body
    assert 'name="q"' in body
    # Still a form, so a browser without JavaScript can search too.
    assert 'action="/history"' in body


def test_every_page_navigates_to_home_players_and_history(client: TestClient) -> None:
    run_episode(client)
    run_id = only_run_id(client)

    for path in ("/", "/history", f"/runs/{run_id}"):
        body = client.get(path).text
        assert 'href="/history"' in body, path
        assert 'href="/"' in body, path
        assert "Players" in body, path


def test_history_marks_itself_as_the_current_page(client: TestClient) -> None:
    body = client.get("/history").text

    assert 'aria-current="page"' in body

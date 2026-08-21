"""A summary is read as prose, and copied as the Markdown it was written in.

Rendering happens on the server (ADR-0004), so the suite can see it the way it
sees every other page. What is asserted here is that the structure a summary
was asked to produce is in the response, that the source is still on the page
under it, and that anything that looks like markup in Claude's output came out
as text. Nothing here asserts on a class name: how the prose is styled is not
what makes it correct.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from project_ai_ftsy_football_sum.services.markdown import render_markdown
from project_ai_ftsy_football_sum.services.store import RunStore
from tests import events as sse
from tests.events import EPISODE_URL, run_episode
from tests.fakes import FakeClaudeClient
from tests.test_history import only_run_id

#: A summary using every construction the prose styling has to cover.
STRUCTURED_SUMMARY = (
    "## News Section\n\n"
    "- **Player/Team**: Bijan Robinson (ATL, RB)\n"
    "  - **News**: A *bigger* role.\n\n"
    "| Player | Team |\n| --- | --- |\n| Robinson | ATL |\n\n"
    "See [the depth chart](https://example.test/depth) and `RB1`.\n"
)


def summarized(client: TestClient, claude: FakeClaudeClient, summary: str) -> str:
    """Run one episode whose summary is `summary`; hand back its saved page."""
    claude.chunks = (summary,)
    run_episode(client)
    return client.get(f"/runs/{only_run_id(client)}").text


# --- The renderer itself --------------------------------------------------


def test_headings_lists_emphasis_links_code_and_tables_all_convert() -> None:
    html = render_markdown(STRUCTURED_SUMMARY)

    assert "<h2>News Section</h2>" in html
    assert "<ul>" in html and "<li>" in html
    assert "<strong>Player/Team</strong>" in html
    assert "<em>bigger</em>" in html
    assert '<a href="https://example.test/depth">the depth chart</a>' in html
    assert "<code>RB1</code>" in html
    assert "<table>" in html and "<td>Robinson</td>" in html


def test_raw_html_in_a_summary_comes_out_as_text_rather_than_markup() -> None:
    """Escaped, not filtered: there is no allowlist here to get wrong."""
    html = render_markdown("<script>alert(1)</script>\n\nA <b>bold</b> claim.\n")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>" not in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_a_link_or_an_image_cannot_carry_a_script_destination() -> None:
    """Markdown's own syntax is markup that escaping raw HTML does not cover."""
    html = render_markdown("[click](javascript:alert) ![alt](vbscript:alert)\n")

    assert "<a " not in html and "<img" not in html
    assert "[click](javascript:alert) ![alt](vbscript:alert)" in html


def test_a_bare_url_and_a_pair_of_hyphens_are_left_exactly_as_written() -> None:
    """Auto-linking and typographic substitution are both off.

    The summary is the document the download and the clipboard hand over, so
    the prose must not say something the source does not.
    """
    html = render_markdown("Ask https://example.test -- it knows.\n")

    assert "<a " not in html
    assert "https://example.test -- it knows." in html


def test_the_same_summary_renders_to_the_same_html_every_time() -> None:
    assert render_markdown(STRUCTURED_SUMMARY) == render_markdown(STRUCTURED_SUMMARY)


def test_a_summary_that_is_empty_renders_to_nothing_at_all() -> None:
    assert render_markdown("") == ""


# --- A saved run's page ---------------------------------------------------


def test_a_saved_runs_page_shows_its_summary_as_prose(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    body = summarized(client, claude, STRUCTURED_SUMMARY)

    assert "<h2>News Section</h2>" in body
    assert "<strong>Player/Team</strong>" in body
    assert "<em>bigger</em>" in body
    assert "<code>RB1</code>" in body
    assert "<td>Robinson</td>" in body


def test_the_markdown_source_is_still_on_the_page_in_a_collapsed_disclosure(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """The same gesture as "show me the underlying error": available, not open."""
    body = summarized(client, claude, STRUCTURED_SUMMARY)

    disclosure = body[body.index("<details") : body.index("</details>")]
    assert "open" not in disclosure.split(">", 1)[0]
    assert "## News Section" in disclosure
    assert "| Player | Team |" in disclosure


def test_html_in_a_summary_is_visible_text_on_the_page_and_never_markup(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    body = summarized(client, claude, "Beware <script>alert(1)</script>.\n")

    assert "<script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_the_run_page_offers_copy_beside_download_pointing_at_one_document(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """Copy asks for the download rather than rebuilding the document here."""
    run_episode(client)
    run_id = only_run_id(client)

    body = client.get(f"/runs/{run_id}").text

    assert f'data-copy-url="/runs/{run_id}/download"' in body
    assert f'href="/runs/{run_id}/download"' in body
    assert "/static/js/copy.js" in body


def test_a_run_whose_summary_came_back_empty_can_still_be_copied(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """The panel hides an empty *live* run, not a saved run's own controls.

    There is still a document to hand over — the front matter alone says which
    episode produced nothing — so hiding the panel would take Copy and Download
    away with it.
    """
    body = summarized(client, claude, "")

    assert "data-run-summary-panel" in body
    panel = body[body.index("data-run-summary-panel") :]
    assert "hidden" not in panel[: panel.index(">")]
    assert "data-copy-url" in panel


def test_history_rows_gain_no_copy_control(client: TestClient) -> None:
    """Copying is something you do having read a summary, not while scanning.

    Nor the handles a live run's panel is filled in through: nothing on this
    page fills anything in.
    """
    run_episode(client)

    body = client.get("/history").text

    assert "data-copy-url" not in body
    assert "data-run-download" not in body
    assert f'href="/runs/{only_run_id(client)}/download"' in body


# --- A live run -----------------------------------------------------------


def test_the_terminal_event_carries_the_summary_rendered(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    """No extra request: the run script swaps this in over the streamed text."""
    claude.chunks = (STRUCTURED_SUMMARY,)

    done = sse.terminal(run_episode(client))

    assert done.name == "done"
    assert "<h2>News Section</h2>" in done.data["summary_html"]


def test_the_rendered_summary_matches_what_the_streamed_pieces_assembled_to(
    client: TestClient,
) -> None:
    """The prose that lands must be the prose for the text that was watched."""
    events = run_episode(client)

    assert sse.terminal(events).data["summary_html"] == render_markdown(
        sse.summary_text(events)
    )


def test_the_terminal_event_says_where_the_finished_runs_document_lives(
    client: TestClient, app_store: RunStore
) -> None:
    """Copy and Download are handed the URL rather than each building one."""
    done = sse.terminal(run_episode(client))

    assert done.data["download_href"] == f"/runs/{app_store.recent(1)[0].id}/download"


def test_a_failed_run_carries_no_rendered_summary(
    client: TestClient, claude: FakeClaudeClient
) -> None:
    claude.error = RuntimeError("rate limited")

    failed = sse.terminal(run_episode(client))

    assert failed.name == "failed"
    assert "summary_html" not in failed.data


def test_a_live_runs_panel_carries_the_controls_the_terminal_event_fills_in(
    client: TestClient,
) -> None:
    """Copy and Download exist before the run they point at does.

    The run has no identifier yet, so the panel arrives with the controls in
    it and no URL on them — which is what `run.js` writes when `done` lands.
    """
    panel = client.post("/runs", data={"youtube_url": EPISODE_URL}).text

    assert "data-run-copy" in panel
    assert "data-run-download" in panel
    assert "data-copy-url" not in panel
    assert "/runs//download" not in panel
    assert "/static/js/copy.js" in client.get("/").text

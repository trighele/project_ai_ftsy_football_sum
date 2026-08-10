from fastapi.testclient import TestClient


def test_home_page_renders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Fantasy Football Podcast Summarizer" in body
    assert 'name="youtube_url"' in body
    assert "Summarize" in body


def test_home_page_uses_only_committed_static_assets(client: TestClient) -> None:
    body = client.get("/").text

    assert "/static/css/app.css" in body
    assert "/static/js/htmx.min.js" in body
    assert "cdn." not in body
    assert "unpkg" not in body
    assert "jsdelivr" not in body


def test_navigation_placeholders_for_players_and_history(client: TestClient) -> None:
    body = client.get("/").text

    assert "Players" in body
    assert "History" in body


def test_stylesheet_and_htmx_are_served(client: TestClient) -> None:
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert len(css.content) > 1000

    htmx = client.get("/static/js/htmx.min.js")
    assert htmx.status_code == 200
    assert b"htmx" in htmx.content


def test_condensed_heading_font_is_vendored_and_served(client: TestClient) -> None:
    """A missing font file degrades silently to a non-condensed fallback."""
    css = client.get("/static/css/app.css").text
    assert "@font-face" in css
    assert "/static/fonts/oswald-latin-var.woff2" in css

    font = client.get("/static/fonts/oswald-latin-var.woff2")
    assert font.status_code == 200
    assert font.content[:4] == b"wOF2"


def test_htmx_status_fragment_returns_a_html_partial(client: TestClient) -> None:
    """The home page's status pill swaps in this fragment via hx-get."""
    response = client.get("/fragments/status", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Ready" in response.text
    # A fragment, not a whole document.
    assert "<html" not in response.text


def test_home_page_wires_the_status_pill_to_the_fragment(client: TestClient) -> None:
    body = client.get("/").text

    assert 'hx-get="/fragments/status"' in body

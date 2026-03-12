"""
Unit tests for libs.scraper_client.ScraperClient.

HTTP calls are intercepted with requests-mock so no real network traffic is made.
HTMLHelper.parse_html_content is patched where we want to test ScraperClient in
isolation from the HTML parsing logic.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
import requests
import requests_mock as req_mock

from libs.scraper_client import ScraperClient


DUMMY_HTML = "<html><body><p>Hello</p></body></html>"
DUMMY_URL = "https://example.com/team/test/"


@pytest.fixture
def scraper() -> ScraperClient:
    return ScraperClient("TestScraper", default_timeout=5)


# ---------------------------------------------------------------------------
# get_html
# ---------------------------------------------------------------------------

class TestGetHtml:

    def test_returns_response_text(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, text=DUMMY_HTML)
        result = scraper.get_html(DUMMY_URL)
        assert result == DUMMY_HTML

    def test_raises_on_http_error(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, status_code=404)
        with pytest.raises(requests.HTTPError):
            scraper.get_html(DUMMY_URL)

    def test_raises_on_500_server_error(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, status_code=500)
        with pytest.raises(requests.HTTPError):
            scraper.get_html(DUMMY_URL)

    def test_uses_configured_timeout(self, scraper, requests_mock):
        """Verify the timeout is passed through to requests.get."""
        requests_mock.get(DUMMY_URL, text=DUMMY_HTML)
        with patch("libs.scraper_client.requests.get", wraps=requests.get) as mock_get:
            scraper.get_html(DUMMY_URL)
            _, kwargs = mock_get.call_args
            assert kwargs.get("timeout") == 5


# ---------------------------------------------------------------------------
# scrape_events
# ---------------------------------------------------------------------------

class TestScrapeEvents:

    def test_delegates_to_html_helper(self, scraper):
        fake_games = [{"round": "Round 1: Rivals", "start": None, "end": None}]
        with patch("libs.scraper_client.HTMLHelper.parse_html_content", return_value=fake_games) as mock_parse:
            result = scraper.scrape_events(DUMMY_HTML, parse_type="ssb")
            mock_parse.assert_called_once_with(html_content=DUMMY_HTML, parse_type="ssb")
            assert result is fake_games

    def test_returns_list(self, scraper):
        with patch("libs.scraper_client.HTMLHelper.parse_html_content", return_value=[]):
            result = scraper.scrape_events(DUMMY_HTML, parse_type="ssb")
            assert isinstance(result, list)

    def test_propagates_value_error_for_unknown_parse_type(self, scraper):
        with pytest.raises(ValueError, match="Unknown parse_type"):
            scraper.scrape_events(DUMMY_HTML, parse_type="nonexistent")


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:

    def test_name_stored(self):
        s = ScraperClient("MyBot")
        assert s.name == "MyBot"

    def test_default_timeout(self):
        s = ScraperClient("Bot")
        assert s.default_timeout == 30

    def test_custom_timeout(self):
        s = ScraperClient("Bot", default_timeout=60)
        assert s.default_timeout == 60

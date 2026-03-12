"""
Unit tests for libs.scraper_client.ScraperClient.

HTTP calls are intercepted with requests-mock. HTMLHelper.parse_html_content
is patched where we test ScraperClient in isolation from parsing logic.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from libs.scraper_client import ScraperClient

DUMMY_HTML = "<html><body><p>Hello</p></body></html>"
DUMMY_URL = "https://example.com/team/test/"


@pytest.fixture
def scraper() -> ScraperClient:
    return ScraperClient("TestScraper", default_timeout=5)


# ---------------------------------------------------------------------------
# get_html — success
# ---------------------------------------------------------------------------

class TestGetHtmlSuccess:

    def test_returns_response_text(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, text=DUMMY_HTML)
        assert scraper.get_html(DUMMY_URL) == DUMMY_HTML

    def test_uses_configured_timeout(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, text=DUMMY_HTML)
        with patch.object(scraper._session, "get", wraps=scraper._session.get) as mock_get:
            scraper.get_html(DUMMY_URL)
            _, kwargs = mock_get.call_args
            assert kwargs.get("timeout") == 5


# ---------------------------------------------------------------------------
# get_html — non-retryable errors (4xx)
# ---------------------------------------------------------------------------

class TestGetHtmlNonRetryableErrors:

    def test_raises_immediately_on_404(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, status_code=404)
        with pytest.raises(requests.HTTPError):
            scraper.get_html(DUMMY_URL)

    def test_404_does_not_retry(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, status_code=404)
        with pytest.raises(requests.HTTPError):
            scraper.get_html(DUMMY_URL)
        assert requests_mock.call_count == 1

    def test_raises_immediately_on_403(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, status_code=403)
        with pytest.raises(requests.HTTPError):
            scraper.get_html(DUMMY_URL)
        assert requests_mock.call_count == 1


# ---------------------------------------------------------------------------
# get_html — retryable errors (5xx)
# ---------------------------------------------------------------------------

class TestGetHtmlRetryable:

    def test_retries_on_503(self, requests_mock):
        """503 is retryable — should attempt MAX_ATTEMPTS times then raise."""
        scraper = ScraperClient("Bot", default_timeout=5)
        requests_mock.get(DUMMY_URL, status_code=503)
        with pytest.raises(requests.HTTPError):
            scraper.get_html(DUMMY_URL)
        # 3 attempts total
        assert requests_mock.call_count == 3

    def test_retries_on_500(self, requests_mock):
        scraper = ScraperClient("Bot", default_timeout=5)
        requests_mock.get(DUMMY_URL, status_code=500)
        with pytest.raises(requests.HTTPError):
            scraper.get_html(DUMMY_URL)
        assert requests_mock.call_count == 3

    def test_succeeds_after_one_failure(self, requests_mock):
        """First request fails with 503, second succeeds — should return HTML."""
        scraper = ScraperClient("Bot", default_timeout=5)
        requests_mock.get(
            DUMMY_URL,
            [
                {"status_code": 503},
                {"text": DUMMY_HTML, "status_code": 200},
            ],
        )
        result = scraper.get_html(DUMMY_URL)
        assert result == DUMMY_HTML
        assert requests_mock.call_count == 2

    def test_retries_on_timeout(self, requests_mock):
        """Timeouts should trigger retry up to MAX_ATTEMPTS times."""
        scraper = ScraperClient("Bot", default_timeout=5)
        requests_mock.get(DUMMY_URL, exc=requests.Timeout)
        with pytest.raises(requests.Timeout):
            scraper.get_html(DUMMY_URL)
        assert requests_mock.call_count == 3

    def test_retries_on_connection_error(self, requests_mock):
        scraper = ScraperClient("Bot", default_timeout=5)
        requests_mock.get(DUMMY_URL, exc=requests.ConnectionError)
        with pytest.raises(requests.ConnectionError):
            scraper.get_html(DUMMY_URL)
        assert requests_mock.call_count == 3


# ---------------------------------------------------------------------------
# scrape_events
# ---------------------------------------------------------------------------

class TestScrapeEvents:

    def test_delegates_to_html_helper(self, scraper):
        fake_games = [{"round": "Round 1: Rivals"}]
        with patch(
            "libs.scraper_client.HTMLHelper.parse_html_content",
            return_value=fake_games,
        ) as mock_parse:
            result = scraper.scrape_events(DUMMY_HTML, parse_type="ssb")
            mock_parse.assert_called_once_with(
                html_content=DUMMY_HTML, parse_type="ssb"
            )
            assert result is fake_games

    def test_propagates_value_error_for_unknown_parse_type(self, scraper):
        with pytest.raises(ValueError, match="Unknown parse_type"):
            scraper.scrape_events(DUMMY_HTML, parse_type="nonexistent")


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:

    def test_name_stored(self):
        assert ScraperClient("MyBot").name == "MyBot"

    def test_default_timeout(self):
        assert ScraperClient("Bot").default_timeout == 30

    def test_custom_timeout(self):
        assert ScraperClient("Bot", default_timeout=60).default_timeout == 60

    def test_session_created(self):
        assert ScraperClient("Bot")._session is not None

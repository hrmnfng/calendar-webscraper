"""
HTTP client that fetches raw HTML with automatic retry, and delegates parsing
to HTMLHelper.
"""

from __future__ import annotations

import requests
from loguru import logger
from requests.adapters import HTTPAdapter
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging

from helpers.html_parser import HTMLHelper

# Retry on connection/timeout errors or 5xx server errors.
# 4xx errors (bad URL, auth failure) are not transient — don't retry them.
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}

_MAX_ATTEMPTS = 3
_WAIT_MIN_SECONDS = 2
_WAIT_MAX_SECONDS = 10


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying."""
    if isinstance(exc, requests.Timeout):
        return True
    if isinstance(exc, requests.ConnectionError):
        return True
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        return response is not None and response.status_code in _RETRYABLE_STATUS_CODES
    return False


class ScraperClient:
    """
    Thin HTTP wrapper that fetches a URL (with retry) and parses game schedules.

    Attributes:
        name: Identifier for this client instance (used in log messages).
        default_timeout: Request timeout in seconds.
    """

    def __init__(self, name: str, default_timeout: int = 30) -> None:
        self.name = name
        self.default_timeout = default_timeout
        self._session = requests.Session()
        logger.debug(f"Created scraper client '{name}' (timeout={default_timeout}s)")

    def get_html(self, address: str) -> str:
        """
        Fetch the raw HTML from *address*, retrying up to
        ``_MAX_ATTEMPTS`` times on transient errors.

        Retries are triggered by:
        - :class:`requests.Timeout`
        - :class:`requests.ConnectionError`
        - :class:`requests.HTTPError` with a 5xx status code

        4xx responses (e.g. 404, 403) are **not** retried and raise
        immediately.

        Args:
            address: URL to fetch.

        Returns:
            Response body as a string.

        Raises:
            requests.HTTPError: On a non-retryable HTTP error (4xx), or if all
                retry attempts for a 5xx error are exhausted.
            requests.Timeout: If all retry attempts time out.
            requests.ConnectionError: If all retry attempts fail to connect.
        """
        return self._get_with_retry(address)

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=_WAIT_MIN_SECONDS, max=_WAIT_MAX_SECONDS),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
        reraise=True,
    )
    def _get_with_retry(self, address: str) -> str:
        """Internal method that tenacity decorates for retry logic."""
        logger.debug(f"Fetching HTML from '{address}'")
        response = self._session.get(address, timeout=self.default_timeout)
        response.raise_for_status()
        return response.text

    def scrape_events(self, html_content: str, parse_type: str) -> list[dict]:
        """
        Parse game schedule events out of *html_content*.

        Args:
            html_content: Raw HTML string fetched via :meth:`get_html`.
            parse_type: Parsing strategy — see
                :meth:`HTMLHelper.parse_html_content`.

        Returns:
            List of game dicts with keys ``round``, ``start``, ``end``,
            ``location``, and ``details_url``.
        """
        logger.debug(f"Scraping events using parse type '{parse_type}'")
        return HTMLHelper.parse_html_content(
            html_content=html_content, parse_type=parse_type
        )

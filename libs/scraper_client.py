"""
HTTP client that fetches raw HTML and delegates parsing to HTMLHelper.
"""

from __future__ import annotations

import requests
from loguru import logger

from helpers.html_parser import HTMLHelper


class ScraperClient:
    """
    Thin HTTP wrapper that fetches a URL and parses game schedules from the HTML.

    Attributes:
        name: Identifier for this client instance (used in log messages).
        default_timeout: Request timeout in seconds.
    """

    def __init__(self, name: str, default_timeout: int = 30) -> None:
        self.name = name
        self.default_timeout = default_timeout
        logger.debug(f"Created scraper client '{name}' (timeout={default_timeout}s)")

    def get_html(self, address: str) -> str:
        """
        Fetch the raw HTML content from *address*.

        Args:
            address: URL to fetch.

        Returns:
            Response body as a string.

        Raises:
            requests.HTTPError: If the server returns a 4xx/5xx status.
            requests.Timeout: If the request exceeds *default_timeout* seconds.
        """
        logger.debug(f"Fetching HTML from '{address}'")
        response = requests.get(address, timeout=self.default_timeout)
        response.raise_for_status()
        return response.text

    def scrape_events(self, html_content: str, parse_type: str) -> list[dict]:
        """
        Parse game schedule events out of *html_content*.

        Args:
            html_content: Raw HTML string previously fetched via :meth:`get_html`.
            parse_type: Parsing strategy — see :meth:`HTMLHelper.parse_html_content`.

        Returns:
            List of game dicts with keys ``round``, ``start``, ``end``,
            ``location``, and ``details_url``.
        """
        logger.debug(f"Scraping events using parse type '{parse_type}'")
        return HTMLHelper.parse_html_content(html_content=html_content, parse_type=parse_type)

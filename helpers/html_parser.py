"""
Parses different types of HTML pages and extracts structured game data.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from loguru import logger


class HTMLHelper:

    @staticmethod
    def parse_html_content(
        html_content: str,
        parse_type: str,
        custom_parse: dict | None = None,
    ) -> list[dict]:
        """
        Route HTML content to the appropriate parser.

        Args:
            html_content: Raw HTML string to parse.
            parse_type: Selects the parsing strategy. Supported values:
                ``"ssb"`` — Sydney Social Basketball pages.
            custom_parse: Reserved for future custom parsing config.

        Returns:
            List of game dicts, each containing ``round``, ``start``, ``end``,
            ``location``, and ``details_url``.

        Raises:
            NotImplementedError: If *parse_type* is ``"custom"`` (not yet implemented).
            ValueError: If an unknown *parse_type* is passed.
        """
        match parse_type:
            case "ssb":
                return HTMLHelper._parse_ssb_content(html_content)
            case "custom":
                raise NotImplementedError(
                    "Custom parse type has not been implemented yet. "
                    "Please use 'ssb' or contribute a custom parser."
                )
            case _:
                raise ValueError(f"Unknown parse_type: {parse_type!r}")

    @staticmethod
    def _parse_ssb_content(html_content: str) -> list[dict]:
        """
        Parse a Sydney Social Basketball (SSB) schedule page.

        Expects one ``<div class="grid">`` per game, each containing labelled
        fields for Round, Opponent, Date, Time, Court, and Score.

        Args:
            html_content: Raw HTML string of an SSB team schedule page.

        Returns:
            List of dicts with keys: ``round``, ``start`` (:class:`~datetime.datetime`),
            ``end`` (:class:`~datetime.datetime`), ``location``, ``details_url``.
        """
        logger.debug("Parsing SSB content")
        soup = BeautifulSoup(html_content, "html.parser")
        games = soup.find_all("div", class_="grid")
        game_schedules: list[dict] = []

        for element in games:
            game_round = element.find(string=re.compile("Round")).find_parent().find_next_sibling(string=True).strip()
            opponent = element.find(string=re.compile("Opponent")).find_next("a").get_text(strip=True)
            date = element.find(string=re.compile("Date")).find_parent().find_next_sibling(string=True).strip()
            time = element.find(string=re.compile("Time")).find_parent().find_next_sibling(string=True).strip()
            location = element.find(string=re.compile("Court")).find_parent().find_next_sibling(string=True).strip()
            details = element.find(string=re.compile("Score")).find_next("a", href=True).get("href")

            game_start = datetime.strptime(f"{date} {time}", "%d/%m/%Y %I:%M%p")
            game_end = game_start + timedelta(hours=1)

            game_schedules.append(
                {
                    "round": f"{game_round}: {opponent}",
                    "start": game_start,
                    "end": game_end,
                    "location": location,
                    "details_url": details,
                }
            )

        return game_schedules

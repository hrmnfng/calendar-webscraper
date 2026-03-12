"""
Parses HTML schedule pages and extracts structured game data.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup, Tag
from loguru import logger

# Labels used to locate field values inside each game element.
# Exact strings are preferred over regex to avoid false-matching opponent names
# that happen to contain words like "Round" or "Court".
_LABEL_ROUND = "Round"
_LABEL_OPPONENT = "Opponent"
_LABEL_DATE = "Date"
_LABEL_TIME = "Time"
_LABEL_COURT = "Court"
_LABEL_SCORE = "Score"

# The datetime format used by the SSB website, e.g. "10/08/2025 10:00AM"
_SSB_DATETIME_FORMAT = "%d/%m/%Y %I:%M%p"


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
            parse_type: Selects the parsing strategy. Currently only ``"ssb"``
                (Sydney Social Basketball) is supported.
            custom_parse: Reserved for future custom parsing config.

        Returns:
            List of game dicts, each containing ``round``, ``start``, ``end``,
            ``location``, and ``details_url``.

        Raises:
            NotImplementedError: If *parse_type* is ``"custom"``.
            ValueError: If an unknown *parse_type* is passed.
        """
        match parse_type:
            case "ssb":
                return HTMLHelper._parse_ssb_content(html_content)
            case "custom":
                raise NotImplementedError(
                    "Custom parse type has not been implemented yet."
                )
            case _:
                raise ValueError(f"Unknown parse_type: {parse_type!r}")

    @staticmethod
    def _parse_ssb_content(html_content: str) -> list[dict]:
        """
        Parse a Sydney Social Basketball (SSB) schedule page.

        Each ``<div class="grid">`` is treated as one game. Fields are located
        by their exact label text rather than broad regex patterns, reducing the
        risk of false matches against team names.

        Individual games that are missing a required field or have an
        unparseable date/time are skipped with a warning; the rest of the
        schedule is still returned.

        Args:
            html_content: Raw HTML of an SSB team schedule page.

        Returns:
            List of game dicts with keys ``round``, ``start``
            (:class:`~datetime.datetime`), ``end``, ``location``,
            ``details_url``.  May be empty if the page contains no game
            elements or all elements fail to parse.
        """
        logger.debug("Parsing SSB content")
        soup = BeautifulSoup(html_content, "html.parser")
        game_elements = soup.find_all("div", class_="grid")

        if not game_elements:
            logger.warning(
                "No game elements found on page. The page structure may have "
                "changed, or no games are currently scheduled."
            )
            return []

        game_schedules: list[dict] = []

        for element in game_elements:
            game = _parse_ssb_game_element(element)
            if game is not None:
                game_schedules.append(game)

        parsed = len(game_schedules)
        total = len(game_elements)

        if parsed == 0:
            logger.warning(
                f"Found {total} game element(s) but could not parse any of them. "
                "The page structure may have changed."
            )
        elif parsed < total:
            logger.warning(
                f"Parsed {parsed}/{total} game elements — "
                f"{total - parsed} were skipped due to missing or invalid fields."
            )
        else:
            logger.debug(f"Successfully parsed {parsed}/{total} game elements")

        return game_schedules


def _extract_label_sibling(element: Tag, label: str) -> str | None:
    """
    Find an exact-text label inside *element* and return the text of its next
    sibling node.

    Exact matching (``string=label``) is used instead of a regex so that
    opponent names containing the same words (e.g. "Round Hill FC") are not
    mistakenly treated as labels.

    Returns ``None`` if the label or its sibling cannot be found.
    """
    label_node = element.find(string=label)
    if label_node is None:
        return None
    sibling = label_node.find_parent().find_next_sibling(string=True)
    if sibling is None:
        return None
    return sibling.strip() or None


def _extract_label_link(element: Tag, label: str) -> str | None:
    """
    Find an exact-text label inside *element* and return the text of the first
    ``<a>`` tag that follows it.

    Returns ``None`` if the label or a following anchor cannot be found.
    """
    label_node = element.find(string=label)
    if label_node is None:
        return None
    anchor = label_node.find_next("a")
    return anchor.get_text(strip=True) if anchor else None


def _extract_label_href(element: Tag, label: str) -> str | None:
    """
    Find an exact-text label inside *element* and return the ``href`` of the
    first ``<a>`` tag that follows it.

    Returns ``None`` if the label or a following anchor cannot be found.
    """
    label_node = element.find(string=label)
    if label_node is None:
        return None
    anchor = label_node.find_next("a", href=True)
    return anchor.get("href") if anchor else None


def _parse_ssb_game_element(element: Tag) -> dict | None:
    """
    Extract all fields from a single SSB game ``<div class="grid">`` element.

    Returns a game dict on success, or ``None`` if any required field is
    missing or the datetime cannot be parsed — in both cases a warning is
    logged with enough context to diagnose the issue.
    """
    # --- Extract raw field values ---
    game_round = _extract_label_sibling(element, _LABEL_ROUND)
    opponent = _extract_label_link(element, _LABEL_OPPONENT)
    date_str = _extract_label_sibling(element, _LABEL_DATE)
    time_str = _extract_label_sibling(element, _LABEL_TIME)
    location = _extract_label_sibling(element, _LABEL_COURT)
    details_url = _extract_label_href(element, _LABEL_SCORE)

    # --- Validate required fields ---
    missing = [
        name for name, value in {
            "Round": game_round,
            "Opponent": opponent,
            "Date": date_str,
            "Time": time_str,
            "Court": location,
            "Score": details_url,
        }.items()
        if value is None
    ]

    if missing:
        # Truncate raw HTML to keep logs readable
        raw = element.get_text(separator=" ", strip=True)[:200]
        logger.warning(
            f"Skipping game element — missing field(s): {missing}. "
            f"Element text: {raw!r}"
        )
        return None

    # --- Parse datetime ---
    try:
        game_start = datetime.strptime(f"{date_str} {time_str}", _SSB_DATETIME_FORMAT)
    except ValueError:
        logger.warning(
            f"Skipping game element — could not parse datetime from "
            f"date={date_str!r} time={time_str!r}. "
            f"Expected format: '{_SSB_DATETIME_FORMAT}'"
        )
        return None

    game_end = game_start + timedelta(hours=1)

    return {
        "round": f"{game_round}: {opponent}",
        "start": game_start,
        "end": game_end,
        "location": location,
        "details_url": details_url,
    }

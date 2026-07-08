"""
Game sources: fetch a schedule for a CalendarConfig and normalize it into
Game objects.

Two sources exist:

* ``ssb-api``  — the SSB WordPress REST API (primary; structured JSON).
* ``ssb-html`` — the original BeautifulSoup page parser (fallback).

Both produce identical Game titles and keys, so calendars stay consistent
regardless of which source produced an event.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from loguru import logger

from helpers.config_loader import CalendarConfig
from helpers.html_parser import HTMLHelper
from helpers.models import Game, ScrapeError
from libs.scraper_client import ScraperClient

SYDNEY = ZoneInfo("Australia/Sydney")
GAME_DURATION = timedelta(hours=1)

# WordPress REST API caps per_page at 100.
_WP_PAGE_SIZE = 100


def normalize_round_key(label: str) -> str:
    """
    Normalize a round label into a stable event key.

    ``"Round 1"`` → ``"round1"``; ``"SEMI FINALS"`` and ``"Semi Finals"``
    both → ``"semifinals"``. The key only needs to be unique within one
    schedule (one game per round).
    """
    return re.sub(r"[^a-z0-9]", "", label.lower())


def round_label_from_slug(slug: str) -> str | None:
    """
    Derive a human-readable round label from a WP match post slug.

    ``"...-2025-s4-r1"`` → ``"Round 1"``; ``"...-semi-finals"`` →
    ``"Semi Finals"``; ``"...-grand-final"`` → ``"Grand Final"``.
    Returns ``None`` if no round marker is recognized.
    """
    m = re.search(r"-r(\d+)$", slug)
    if m:
        return f"Round {m.group(1)}"
    if slug.endswith("semi-finals") or slug.endswith("semi-final"):
        return "Semi Finals"
    if slug.endswith("grand-final") or slug.endswith("grand-finals"):
        return "Grand Final"
    return None

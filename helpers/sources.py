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

import requests
from loguru import logger

from helpers.config_loader import CalendarConfig
from helpers.html_parser import HTMLHelper
from helpers.models import Game, ScrapeError
from libs.scraper_client import ScraperClient

SYDNEY = ZoneInfo("Australia/Sydney")
GAME_DURATION = timedelta(hours=1)

# WordPress REST API caps per_page at 100.
_WP_PAGE_SIZE = 100
_WP_MAX_PAGES = 50


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


def _wp_api_base(config_url: str) -> str:
    parts = urlparse(config_url)
    return f"{parts.scheme}://{parts.netloc}/wp-json/wp/v2"


def _team_slug(config_url: str) -> str:
    return urlparse(config_url).path.rstrip("/").rsplit("/", 1)[-1]


def _get_all_pages(client: ScraperClient, url: str, params: dict) -> list[dict]:
    """Fetch every page of a WP REST collection (100 items per page)."""
    results: list[dict] = []
    page = 1
    while True:
        if page > _WP_MAX_PAGES:
            raise ScrapeError(
                f"WP API pagination exceeded {_WP_MAX_PAGES} pages for {url}"
                " — search term too broad?"
            )
        try:
            batch = client.get_json(
                url, params={**params, "per_page": _WP_PAGE_SIZE, "page": page}
            )
        except requests.HTTPError as exc:
            # WP returns 400 rest_post_invalid_page_number one page past the
            # end when the total is an exact multiple of per_page.
            if page > 1 and exc.response is not None and exc.response.status_code == 400:
                return results
            raise
        results.extend(batch)
        if len(batch) < _WP_PAGE_SIZE:
            return results
        page += 1


def fetch_games_ssb_api(client: ScraperClient, config: CalendarConfig) -> list[Game]:
    """
    Fetch the schedule via the SSB WordPress REST API.

    Resolves the team post from the config URL slug, searches match posts by
    the team's full title, then keeps only matches where this team is the
    home or away side (search alone is fuzzy).
    """
    base = _wp_api_base(config.url)
    slug = _team_slug(config.url)

    teams = client.get_json(f"{base}/team", params={"slug": slug})
    if not teams:
        raise ScrapeError(f"No WP team post found for slug {slug!r}")
    team = teams[0]
    team_id = team["id"]
    team_title = html.unescape(team["title"]["rendered"])
    logger.debug(f"Resolved team slug {slug!r} to post {team_id} ({team_title!r})")

    matches = _get_all_pages(client, f"{base}/match", params={"search": team_title})

    games: list[Game] = []
    for match in matches:
        try:
            acf = match["acf"]
            home, away = acf["home_team"], acf["away_team"]
            if team_id not in (home["ID"], away["ID"]):
                continue
            opponent = away["post_title"] if home["ID"] == team_id else home["post_title"]
            round_label = round_label_from_slug(match["slug"]) or match["slug"]
            # acf.time is Sydney wall-clock encoded as a UTC epoch: decode as UTC,
            # keep the wall-clock digits, and re-label the zone as Sydney.
            time_val = acf["time"]
            if not time_val:
                logger.warning(
                    f"Match {match.get('id')} ({match.get('slug')!r}) has no scheduled"
                    " time (TBD) — skipping"
                )
                continue
            start = datetime.fromtimestamp(time_val, tz=timezone.utc).replace(
                tzinfo=SYDNEY
            )
            games.append(
                Game(
                    key=normalize_round_key(round_label),
                    title=f"{round_label}: {opponent}",
                    start=start,
                    end=start + GAME_DURATION,
                    venue=acf["venue"]["post_title"],
                    details_url=match["link"],
                )
            )
        except (KeyError, TypeError):
            logger.warning(
                f"Match {match.get('id')} ({match.get('slug')!r}) is malformed"
                " — skipping"
            )
            continue

    # Warn about duplicate round keys — one game per round is a load-bearing
    # assumption for identity-based calendar sync.
    seen_keys: dict[str, int] = {}
    for game in games:
        seen_keys[game.key] = seen_keys.get(game.key, 0) + 1
    duplicates = [k for k, count in seen_keys.items() if count > 1]
    if duplicates:
        logger.warning(
            f"Duplicate round keys detected for team {team_title!r}: {duplicates}"
            " — only the last game per key will survive identity-based sync"
        )

    if not games:
        raise ScrapeError(
            f"No games found via API for team {team_title!r} "
            f"({len(matches)} search results, none matched team id {team_id})"
        )
    games.sort(key=lambda g: g.start)
    logger.info(f"API source: {len(games)} games for {team_title!r}")
    return games


def fetch_games_ssb_html(client: ScraperClient, config: CalendarConfig) -> list[Game]:
    """Fetch the schedule by scraping the team's HTML page (fallback path)."""
    html_content = client.get_html(config.url)
    raw_games = HTMLHelper.parse_html_content(
        html_content=html_content, parse_type="ssb"
    )
    if not raw_games:
        raise ScrapeError(f"HTML source parsed no games from {config.url}")

    games = [
        Game(
            key=normalize_round_key(raw["round_label"]),
            title=raw["round"],
            start=raw["start"].replace(tzinfo=SYDNEY),
            end=raw["end"].replace(tzinfo=SYDNEY),
            venue=raw["location"],
            details_url=raw["details_url"],
        )
        for raw in raw_games
    ]
    logger.info(f"HTML source: {len(games)} games from {config.url}")
    return games


SOURCES = {
    "ssb-api": fetch_games_ssb_api,
    "ssb-html": fetch_games_ssb_html,
}


def fetch_games(client: ScraperClient, config: CalendarConfig) -> list[Game]:
    """
    Fetch games using the config's source; if the API source fails for any
    reason, automatically fall back to HTML scraping.
    """
    fetch = SOURCES[config.source]
    try:
        return fetch(client, config)
    except Exception:
        if config.source != "ssb-api":
            raise
        logger.exception(
            f"API source failed for '{config.name}' — falling back to HTML scraping"
        )
        # Look up via the registry (not a direct call) so tests can stub it.
        return SOURCES["ssb-html"](client, config)

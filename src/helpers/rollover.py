"""
Season-rollover detection for calendar configs.

Each SSB team gets a new WordPress team post every season (slug ``leteam-12``
→ ``leteam-14``); preseason and grading posts also appear as their own team
posts and count as newer versions. These helpers detect when a config's team
URL points at an outdated post and rewrite the config file in place.

Pure logic lives here; ``src/check_rollover.py`` is the CLI entry point.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# Reuse the WP-API plumbing from the game sources module (same app, shared
# conventions — pagination and URL derivation must not drift between them).
from helpers.sources import _get_all_pages, _team_slug, _wp_api_base
from libs.scraper_client import ScraperClient

# Matches season suffixes: "LeTeam 2025 s4", "LeTeam 2026 s1 preseason",
# "LeTeam 2023 s3 grading" — everything from " <year> s<N>" onward.
_SEASON_SUFFIX = re.compile(r"\s+\d{4}\s+s\d+\b.*$", re.IGNORECASE)


@dataclass(frozen=True)
class RolloverResult:
    """Outcome of checking one config file."""

    config_file: str
    status: str  # "updated" | "unchanged" | "skipped"
    detail: str


def base_team_name(title: str) -> str | None:
    """
    Strip the season suffix from a team post title.

    ``"LeTeam 2025 s4"`` → ``"LeTeam"``; ``"LeTeam 2026 s1 preseason"`` →
    ``"LeTeam"``. Returns ``None`` when the title has no recognizable season
    suffix (nothing was stripped), since a prefix search on it would be
    meaningless.
    """
    unescaped = html.unescape(title).strip()
    stripped = _SEASON_SUFFIX.sub("", unescaped).strip()
    if not stripped or stripped == unescaped:
        return None
    return stripped


def find_newest_team_post(posts: list[dict], base_name: str) -> dict | None:
    """
    Return the newest (by post ``date``) team post whose unescaped title
    starts with ``"<base_name> "``.

    Prefix matching excludes fuzzy WP-search hits like "The LeTeam ..." when
    looking for "LeTeam". Slugs are never compared for ordering — their
    numbering is not clean (``leteam-8-2``, ``the-leteam``).
    """
    prefix = f"{base_name.lower()} "
    candidates = [
        post
        for post in posts
        if html.unescape(post.get("title", {}).get("rendered", ""))
        .lower()
        .startswith(prefix)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda post: post.get("date", ""))


def rewrite_config_url(config_path: Path, new_url: str) -> None:
    """Replace the value of the first ``url:`` line, leaving all other lines verbatim."""
    text = config_path.read_text(encoding="utf-8")
    new_text = re.sub(
        r"(?m)^(url:\s*).*$",
        lambda m: f'{m.group(1)}"{new_url}"',
        text,
        count=1,
    )
    config_path.write_text(new_text, encoding="utf-8")


def build_summary(results: list[RolloverResult]) -> str:
    """Render the markdown summary used as the rollover PR body."""
    lines = [
        "## Config season rollover",
        "",
        "Automated weekly check of team pages on the SSB site.",
        "",
        "| Config | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            f"| `{result.config_file}` | {result.status} | {result.detail} |"
        )
    lines.append("")
    return "\n".join(lines)

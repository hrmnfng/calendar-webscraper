# WordPress API Migration + Reliability Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragile HTML scraping with the SSB WordPress REST API (keeping HTML as automatic fallback), fix event-matching/pagination/observability reliability bugs, and restructure the pipeline around a typed `Game` model with identity-based diffing.

**Architecture:** A `Game` dataclass becomes the single currency between "sources" (fetchers) and the sync engine. Two sources — `ssb-api` (primary, WordPress `/wp-json/wp/v2/` endpoints) and `ssb-html` (the existing BeautifulSoup parser, kept as fallback) — both emit `Game` objects with a stable per-round key. The sync engine matches scraped games to calendar events by that key (stored in `extendedProperties.private.gameKey`) instead of by start-time heuristics, with a one-time legacy fallback that adopts old keyless events. `main()` aggregates per-calendar failures and exits non-zero so the GitHub Actions run goes red on failure.

**Tech Stack:** Python 3.12, requests + tenacity (existing), BeautifulSoup (fallback parser only), zoneinfo + tzdata, pytest + requests-mock, uv.

---

## Verified facts about the SSB site (researched live, 2026-07-08)

These were confirmed by hitting the production site — do not re-derive them:

1. **The API exists.** `https://sydneysocialbasketball.com.au/wp-json/wp/v2/` exposes public post types `team`, `match`, `round`.
2. **Team lookup:** `GET /wp/v2/team?slug=leteam-12` → `[{"id": 519104, "title": {"rendered": "LeTeam 2025 s4"}, ...}]`. The slug is the last path segment of the config `url`. Team posts are **per-season** (same as the HTML page).
3. **Match search:** `GET /wp/v2/match?search=<team title>&per_page=100` returns matches whose title contains all search words. Search is fuzzy — **must filter client-side** by `acf.home_team.ID == team_id or acf.away_team.ID == team_id`. Rendered titles contain HTML entities (`&#038;`) — unescape before using as a search term.
4. **Match fields:** `acf.home_team` / `acf.away_team` / `acf.venue` are embedded post objects (use `post_title`); `acf.time` is a unix timestamp; `link` is the match page URL; `slug` ends in `-r<N>`, `-semi-finals`, or `-grand-final`.
5. **`acf.time` is Sydney wall-clock encoded as UTC.** A 9:10 PM Sydney game decodes to `21:10 UTC`. Correct decode: `datetime.fromtimestamp(t, tz=timezone.utc).replace(tzinfo=ZoneInfo("Australia/Sydney"))` (keeps the wall-clock digits, swaps the zone).
6. **HTML page parity:** the HTML `Round` field is `"Round 1"`, `"Round 2"`, …; `Opponent` is the team `post_title` including season suffix (e.g. `"baby dragons 2025 s4"`); the `Score` href equals the API match `link`. So both sources can produce identical event titles (`"Round 1: baby dragons 2025 s4"`) and identical keys.
7. **WP REST pagination:** max `per_page=100`; requesting a page past the last returns HTTP 400 (`rest_post_invalid_page_number`). A page shorter than `per_page` means done.

## CLAUDE.md compliance note

The repo's CLAUDE.md requires GitNexus impact analysis before editing symbols and `gitnexus_detect_changes()` before commits. If the GitNexus MCP tools are available in your session, run `gitnexus_impact({target: "<symbol>", direction: "upstream"})` before modifying each listed symbol and `gitnexus_detect_changes()` before each commit (run `npx gitnexus analyze` first if the index is stale). If the tools are not available, note that in the commit process and proceed.

## Out of scope (deliberate, YAGNI)

- Deleting cancelled games from calendars (identity keys make this possible later; not doing it now).
- `timeMin` filtering of calendar events (dangerous until scraped past-games are also filtered; pagination alone fixes the correctness bug).
- Renaming `ScraperClient` (it gains `get_json` but keeps its name to avoid churn).

## File structure

| File | Action | Responsibility |
|---|---|---|
| `helpers/models.py` | Create | `Game`, `ExistingEvent` dataclasses, `ScrapeError` |
| `helpers/sources.py` | Create | Key normalization, WP API source, HTML source wrapper, `SOURCES` registry, `fetch_games` with fallback |
| `libs/scraper_client.py` | Modify | Add `User-Agent` header, add `get_json` with same retry policy |
| `helpers/config_loader.py` | Modify | Add optional `source` field (default `"ssb-api"`) |
| `helpers/html_parser.py` | Modify | Also return `round_label` per game (needed for key derivation) |
| `libs/google_cal_client.py` | Modify | Paginate `list_events`, return `list` instead of raw dict |
| `helpers/event_sync.py` | Modify | New identity-based functions (additive in Task 7; legacy functions deleted in Task 9) |
| `main.py` | Modify | Rewire to sources + new sync engine; exit non-zero on failure |
| `pyproject.toml` | Modify | Add `tzdata` dependency |
| `calendar-configs/_config-template.yaml` | Modify | Document `source` field |
| `.github/README.md` | Modify | Update project structure + config docs |
| `tests/test_models.py` | — | Not needed (dataclasses have no logic) |
| `tests/test_sources.py` | Create | Key normalization, slug→round, API mapping, pagination, fallback |
| `tests/test_scraper_client.py` | Modify | `get_json`, User-Agent |
| `tests/test_config_loader.py` | Modify | `source` field validation |
| `tests/test_google_cal_client.py` | Modify | Pagination |
| `tests/test_html_parser.py` | Modify | `round_label` field |
| `tests/test_event_sync.py` | Modify | New function tests (Task 7); legacy tests deleted (Task 9) |

Every task leaves the app runnable and the test suite green — new sync functions are **added** alongside the old ones, and `main.py` switches over (and old code is deleted) only in Task 9.

All test commands are run from the repo root: `C:\Dev\coding\calendar-webscraper`.

---

### Task 1: `Game` model, `ScrapeError`, and tzdata dependency

**Files:**
- Create: `helpers/models.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add tzdata dependency** (zoneinfo has no bundled tz database on Windows)

In `pyproject.toml`, add to the `dependencies` list after `"tenacity>=8.0",`:

```toml
    "tzdata>=2024.1",
```

Run: `uv sync`
Expected: resolves and installs `tzdata` without error.

- [ ] **Step 2: Create the models module**

Create `helpers/models.py`:

```python
"""
Shared data models for the scrape → sync pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class ScrapeError(RuntimeError):
    """Raised when a source cannot produce any games for a config."""


@dataclass(frozen=True)
class Game:
    """A single scheduled game, normalized from any source."""

    key: str            # stable identity within one schedule, e.g. "round1"
    title: str          # event summary, e.g. "Round 1: baby dragons 2025 s4"
    start: datetime     # timezone-aware (Australia/Sydney)
    end: datetime       # timezone-aware
    venue: str
    details_url: str


@dataclass(frozen=True)
class ExistingEvent:
    """A lightweight view of a Google Calendar event for diffing."""

    id: str
    key: str | None     # gameKey extended property; None for legacy events
    start: datetime     # timezone-aware
```

- [ ] **Step 3: Sanity-check import and run suite**

Run: `uv run python -c "from helpers.models import Game, ExistingEvent, ScrapeError; print('ok')"`
Expected: `ok`

Run: `uv run pytest`
Expected: all existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add helpers/models.py pyproject.toml uv.lock
git commit -m "feat: add Game/ExistingEvent models and tzdata dependency"
```

---

### Task 2: ScraperClient — User-Agent header and `get_json`

**Files:**
- Modify: `libs/scraper_client.py`
- Test: `tests/test_scraper_client.py`

GitNexus symbols touched: `ScraperClient.__init__` (adds header; no signature change).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scraper_client.py`:

```python
# ---------------------------------------------------------------------------
# User-Agent
# ---------------------------------------------------------------------------

class TestUserAgent:

    def test_session_has_custom_user_agent(self):
        scraper = ScraperClient("Bot")
        ua = scraper._session.headers["User-Agent"]
        assert ua.startswith("calendar-webscraper/")
        assert "python-requests" not in ua

    def test_requests_send_the_user_agent(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, text=DUMMY_HTML)
        scraper.get_html(DUMMY_URL)
        assert requests_mock.last_request.headers["User-Agent"].startswith(
            "calendar-webscraper/"
        )


# ---------------------------------------------------------------------------
# get_json
# ---------------------------------------------------------------------------

class TestGetJson:

    def test_returns_parsed_json(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, json=[{"id": 1}])
        assert scraper.get_json(DUMMY_URL) == [{"id": 1}]

    def test_passes_query_params(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, json=[])
        scraper.get_json(DUMMY_URL, params={"slug": "leteam-12"})
        assert requests_mock.last_request.qs == {"slug": ["leteam-12"]}

    def test_retries_on_503(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, status_code=503)
        with pytest.raises(requests.HTTPError):
            scraper.get_json(DUMMY_URL)
        assert requests_mock.call_count == 3

    def test_raises_immediately_on_404(self, scraper, requests_mock):
        requests_mock.get(DUMMY_URL, status_code=404)
        with pytest.raises(requests.HTTPError):
            scraper.get_json(DUMMY_URL)
        assert requests_mock.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scraper_client.py -v`
Expected: the 6 new tests FAIL (`KeyError: 'User-Agent'` mismatch / `AttributeError: ... has no attribute 'get_json'`); all pre-existing tests still PASS.

- [ ] **Step 3: Implement**

In `libs/scraper_client.py`, add to `__init__` after `self._session = requests.Session()`:

```python
        self._session.headers["User-Agent"] = f"calendar-webscraper/1.0 ({name})"
```

Add these methods after `_get_with_retry`:

```python
    def get_json(self, address: str, params: dict | None = None):
        """
        Fetch and parse JSON from *address*, retrying on the same transient
        errors as :meth:`get_html`.

        Args:
            address: URL to fetch.
            params: Optional query parameters.

        Returns:
            The parsed JSON body (list or dict).
        """
        return self._get_json_with_retry(address, params)

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=_WAIT_MIN_SECONDS, max=_WAIT_MAX_SECONDS),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
        reraise=True,
    )
    def _get_json_with_retry(self, address: str, params: dict | None):
        """Internal method that tenacity decorates for retry logic."""
        logger.debug(f"Fetching JSON from '{address}' (params={params})")
        response = self._session.get(address, params=params, timeout=self.default_timeout)
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scraper_client.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add libs/scraper_client.py tests/test_scraper_client.py
git commit -m "feat: set User-Agent and add get_json with retry to ScraperClient"
```

---

### Task 3: Config loader — optional `source` field

**Files:**
- Modify: `helpers/config_loader.py`
- Modify: `calendar-configs/_config-template.yaml`
- Test: `tests/test_config_loader.py`

GitNexus symbols touched: `CalendarConfig`, `_iter_configs`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_loader.py` (follow the file's existing fixture style for writing temp YAML files; if it uses a `tmp_path` helper, reuse it):

```python
class TestSourceField:

    def test_source_defaults_to_ssb_api(self):
        config = CalendarConfig(name="T", url="https://x/team/t/", color_id=5)
        assert config.source == "ssb-api"

    def test_explicit_source_accepted(self):
        config = CalendarConfig(
            name="T", url="https://x/team/t/", color_id=5, source="ssb-html"
        )
        assert config.source == "ssb-html"

    def test_unknown_source_rejected(self):
        with pytest.raises(ValueError, match="source"):
            CalendarConfig(
                name="T", url="https://x/team/t/", color_id=5, source="magic"
            )

    def test_source_read_from_yaml(self, tmp_path):
        (tmp_path / "config-t.yaml").write_text(
            'name: "T"\nurl: "https://x/team/t/"\ncolor_id: 5\nsource: "ssb-html"\n'
        )
        configs = load_configs(str(tmp_path))
        assert configs[0].source == "ssb-html"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: new tests FAIL (`TypeError: unexpected keyword argument 'source'` / `AttributeError`).

- [ ] **Step 3: Implement**

In `helpers/config_loader.py`, add a module-level constant below the imports:

```python
VALID_SOURCES = ("ssb-api", "ssb-html")
```

Add the field to `CalendarConfig`:

```python
    name: str
    url: str
    color_id: int
    source: str = "ssb-api"
```

Add to the end of `__post_init__`:

```python
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"Calendar config 'source' must be one of {VALID_SOURCES}, "
                f"got {self.source!r}"
            )
```

In `_iter_configs`, add `source` to the constructor call:

```python
            config = CalendarConfig(
                name=raw.get("name", ""),
                url=raw.get("url", ""),
                color_id=int(raw.get("color_id", 0)),
                source=raw.get("source", "ssb-api"),
            )
```

Update `calendar-configs/_config-template.yaml` — add below the existing fields:

```yaml
# Optional: where to fetch the schedule from.
#   ssb-api  (default) — WordPress JSON API; falls back to HTML automatically
#   ssb-html           — force HTML page scraping
# source: "ssb-api"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add helpers/config_loader.py calendar-configs/_config-template.yaml tests/test_config_loader.py
git commit -m "feat: add optional 'source' field to calendar configs"
```

---

### Task 4: HTML parser — expose `round_label`

The key scheme needs the round string on its own; the parser currently only returns the combined `"Round 1: opponent"` string.

**Files:**
- Modify: `helpers/html_parser.py`
- Test: `tests/test_html_parser.py`

GitNexus symbols touched: `_parse_ssb_game_element`.

- [ ] **Step 1: Write the failing test**

In `tests/test_html_parser.py`, find an existing happy-path test that asserts on a parsed game dict (one that checks `game["round"]`). Add alongside it:

```python
    def test_game_includes_round_label(self):
        # Reuse whatever valid-HTML fixture the neighbouring tests use
        games = HTMLHelper.parse_html_content(VALID_HTML, parse_type="ssb")
        assert games[0]["round_label"] == "Round 1"
```

(Adjust `VALID_HTML` and the expected value `"Round 1"` to match the fixture actually used in that file — the round label is whatever the fixture's `Round` field contains.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_html_parser.py -v -k round_label`
Expected: FAIL with `KeyError: 'round_label'`.

- [ ] **Step 3: Implement**

In `helpers/html_parser.py`, `_parse_ssb_game_element`, add `round_label` to the returned dict:

```python
    return {
        "round": f"{game_round}: {opponent}",
        "round_label": game_round,
        "start": game_start,
        "end": game_end,
        "location": location,
        "details_url": details_url,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_html_parser.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add helpers/html_parser.py tests/test_html_parser.py
git commit -m "feat: expose round_label from SSB HTML parser"
```

---

### Task 5: Sources module — key normalization and slug→round derivation

**Files:**
- Create: `helpers/sources.py`
- Create: `tests/test_sources.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sources.py`:

```python
"""
Unit tests for helpers.sources — key normalization, WP API source,
HTML source wrapper, and fallback behaviour.
"""

from __future__ import annotations

import pytest

from helpers.sources import normalize_round_key, round_label_from_slug


class TestNormalizeRoundKey:

    def test_round_number(self):
        assert normalize_round_key("Round 1") == "round1"

    def test_case_and_spacing_insensitive(self):
        assert normalize_round_key("SEMI FINALS") == normalize_round_key("Semi Finals")

    def test_strips_non_alphanumerics(self):
        assert normalize_round_key("Grand-Final!") == "grandfinal"


class TestRoundLabelFromSlug:

    def test_numbered_round(self):
        slug = "leteam-vs-baby-dragons-2025-s4-r1"
        assert round_label_from_slug(slug) == "Round 1"

    def test_double_digit_round(self):
        slug = "arn2-denver-chicken-nuggets-vs-leteam-2026-s1-r10"
        assert round_label_from_slug(slug) == "Round 10"

    def test_semi_finals(self):
        slug = "shake-shaq-vs-leteam-2025-s4-semi-finals"
        assert round_label_from_slug(slug) == "Semi Finals"

    def test_grand_final(self):
        slug = "untouchaballs-vs-leteam-2026-s1-grand-final"
        assert round_label_from_slug(slug) == "Grand Final"

    def test_unrecognized_slug_returns_none(self):
        assert round_label_from_slug("some-random-page") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'helpers.sources'`.

- [ ] **Step 3: Implement the pure helpers**

Create `helpers/sources.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sources.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add helpers/sources.py tests/test_sources.py
git commit -m "feat: add sources module with round key normalization"
```

---

### Task 6: Sources module — WP API source, HTML source, registry, fallback

**Files:**
- Modify: `helpers/sources.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources.py`:

```python
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from helpers.config_loader import CalendarConfig
from helpers.models import Game, ScrapeError
from helpers.sources import SOURCES, fetch_games, fetch_games_ssb_api, fetch_games_ssb_html

SYDNEY = ZoneInfo("Australia/Sydney")

TEAM_URL = "https://sydneysocialbasketball.com.au/team/leteam-12/"
CONFIG = CalendarConfig(name="LeTeam", url=TEAM_URL, color_id=9)

TEAM_POST = {"id": 519104, "title": {"rendered": "LeTeam 2025 s4"}}

def _match(match_id, slug, home_id, home_title, away_id, away_title, ts):
    return {
        "id": match_id,
        "slug": slug,
        "link": f"https://sydneysocialbasketball.com.au/match/{slug}/",
        "acf": {
            "home_team": {"ID": home_id, "post_title": home_title},
            "away_team": {"ID": away_id, "post_title": away_title},
            "venue": {"post_title": "Arncliffe Youth Centre #1"},
            # 2026-01-15 21:10 Sydney wall clock, encoded as UTC epoch
            "time": ts,
            "ended": False,
            "forfeit": False,
        },
    }

# 2026-01-15T21:10:00 as a UTC epoch (wall-clock encoding used by the site)
TS_R1 = int(datetime(2026, 1, 15, 21, 10, tzinfo=ZoneInfo("UTC")).timestamp())

OUR_MATCH = _match(
    531001, "leteam-vs-baby-dragons-2025-s4-r1",
    519104, "LeTeam 2025 s4", 519200, "baby dragons 2025 s4", TS_R1,
)
OTHER_MATCH = _match(
    531002, "pilgrims-vs-tigers-2025-s4-r1",
    600001, "Pilgrims 2025 s4", 600002, "Tigers 2025 s4", TS_R1,
)


class TestFetchGamesSsbApi:

    def _client(self, team_response, match_pages):
        """Fake ScraperClient whose get_json returns canned responses."""
        client = MagicMock()
        responses = [team_response] + match_pages
        client.get_json.side_effect = responses
        return client

    def test_maps_match_to_game(self):
        client = self._client([TEAM_POST], [[OUR_MATCH]])
        games = fetch_games_ssb_api(client, CONFIG)
        assert games == [
            Game(
                key="round1",
                title="Round 1: baby dragons 2025 s4",
                start=datetime(2026, 1, 15, 21, 10, tzinfo=SYDNEY),
                end=datetime(2026, 1, 15, 22, 10, tzinfo=SYDNEY),
                venue="Arncliffe Youth Centre #1",
                details_url="https://sydneysocialbasketball.com.au/match/leteam-vs-baby-dragons-2025-s4-r1/",
            )
        ]

    def test_team_endpoint_called_with_slug_from_config_url(self):
        client = self._client([TEAM_POST], [[OUR_MATCH]])
        fetch_games_ssb_api(client, CONFIG)
        first_call = client.get_json.call_args_list[0]
        assert first_call.args[0].endswith("/wp-json/wp/v2/team")
        assert first_call.kwargs["params"] == {"slug": "leteam-12"}

    def test_filters_out_other_teams_matches(self):
        client = self._client([TEAM_POST], [[OUR_MATCH, OTHER_MATCH]])
        games = fetch_games_ssb_api(client, CONFIG)
        assert len(games) == 1
        assert games[0].key == "round1"

    def test_raises_when_team_not_found(self):
        client = self._client([], [])
        with pytest.raises(ScrapeError, match="leteam-12"):
            fetch_games_ssb_api(client, CONFIG)

    def test_raises_when_no_games_after_filtering(self):
        client = self._client([TEAM_POST], [[OTHER_MATCH]])
        with pytest.raises(ScrapeError, match="No games"):
            fetch_games_ssb_api(client, CONFIG)

    def test_paginates_until_short_page(self):
        full_page = [OTHER_MATCH] * 100
        client = self._client([TEAM_POST], [full_page, [OUR_MATCH]])
        games = fetch_games_ssb_api(client, CONFIG)
        assert len(games) == 1
        # 1 team call + 2 match pages
        assert client.get_json.call_count == 3


class TestFetchGamesSsbHtml:

    def test_wraps_parser_output_into_games(self, monkeypatch):
        raw = [{
            "round": "Round 1: baby dragons 2025 s4",
            "round_label": "Round 1",
            "start": datetime(2026, 1, 15, 21, 10),
            "end": datetime(2026, 1, 15, 22, 10),
            "location": "Arncliffe Youth Centre #1",
            "details_url": "https://sydneysocialbasketball.com.au/match/x/",
        }]
        monkeypatch.setattr(
            "helpers.sources.HTMLHelper.parse_html_content", lambda **kw: raw
        )
        client = MagicMock()
        client.get_html.return_value = "<html></html>"
        games = fetch_games_ssb_html(client, CONFIG)
        assert games[0].key == "round1"
        assert games[0].start == datetime(2026, 1, 15, 21, 10, tzinfo=SYDNEY)

    def test_raises_on_empty_parse(self, monkeypatch):
        monkeypatch.setattr(
            "helpers.sources.HTMLHelper.parse_html_content", lambda **kw: []
        )
        client = MagicMock()
        client.get_html.return_value = "<html></html>"
        with pytest.raises(ScrapeError):
            fetch_games_ssb_html(client, CONFIG)


class TestFetchGamesFallback:

    def test_registry_contains_both_sources(self):
        assert set(SOURCES) == {"ssb-api", "ssb-html"}

    def test_api_failure_falls_back_to_html(self, monkeypatch):
        api = MagicMock(side_effect=ScrapeError("api down"))
        game = Game(
            key="round1", title="Round 1: x",
            start=datetime(2026, 1, 15, 21, 10, tzinfo=SYDNEY),
            end=datetime(2026, 1, 15, 22, 10, tzinfo=SYDNEY),
            venue="V", details_url="https://x/",
        )
        html_src = MagicMock(return_value=[game])
        monkeypatch.setitem(SOURCES, "ssb-api", api)
        monkeypatch.setitem(SOURCES, "ssb-html", html_src)
        assert fetch_games(MagicMock(), CONFIG) == [game]

    def test_html_source_failure_does_not_fall_back(self, monkeypatch):
        html_src = MagicMock(side_effect=ScrapeError("bad page"))
        monkeypatch.setitem(SOURCES, "ssb-html", html_src)
        config = CalendarConfig(
            name="T", url=TEAM_URL, color_id=9, source="ssb-html"
        )
        with pytest.raises(ScrapeError):
            fetch_games(MagicMock(), config)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sources.py -v`
Expected: new tests FAIL with `ImportError` (names don't exist yet); Task 5 tests still PASS.

- [ ] **Step 3: Implement**

Append to `helpers/sources.py`:

```python
def _wp_api_base(config_url: str) -> str:
    parts = urlparse(config_url)
    return f"{parts.scheme}://{parts.netloc}/wp-json/wp/v2"


def _team_slug(config_url: str) -> str:
    return urlparse(config_url).path.rstrip("/").rsplit("/", 1)[-1]


def _get_all_pages(client: ScraperClient, url: str, params: dict) -> list[dict]:
    """Fetch every page of a WP REST collection (100 items per page)."""
    import requests

    results: list[dict] = []
    page = 1
    while True:
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
        acf = match["acf"]
        home, away = acf["home_team"], acf["away_team"]
        if team_id not in (home["ID"], away["ID"]):
            continue
        opponent = away["post_title"] if home["ID"] == team_id else home["post_title"]
        round_label = round_label_from_slug(match["slug"]) or match["slug"]
        # acf.time is Sydney wall-clock encoded as a UTC epoch: decode as UTC,
        # keep the wall-clock digits, and re-label the zone as Sydney.
        start = datetime.fromtimestamp(acf["time"], tz=timezone.utc).replace(
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
```

Move the `import requests` from inside `_get_all_pages` to the top of the file with the other imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sources.py -v`
Expected: all PASS.

Run: `uv run pytest`
Expected: full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add helpers/sources.py tests/test_sources.py
git commit -m "feat: add WP API game source with HTML fallback"
```

---

### Task 7: Identity-based sync functions (additive — old functions untouched)

**Files:**
- Modify: `helpers/event_sync.py`
- Test: `tests/test_event_sync.py`

GitNexus symbols touched: none modified — only new symbols added (`parse_existing_events`, `match_game_to_event`, `build_reschedule_patch`, `build_field_patch`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_event_sync.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from helpers.event_sync import (
    build_field_patch,
    build_reschedule_patch,
    match_game_to_event,
    parse_existing_events,
)
from helpers.models import ExistingEvent, Game

SYDNEY = ZoneInfo("Australia/Sydney")


def _game(key="round1", start=None, title="Round 1: baby dragons 2025 s4"):
    start = start or datetime(2026, 1, 15, 21, 10, tzinfo=SYDNEY)
    return Game(
        key=key, title=title, start=start,
        end=start.replace(hour=start.hour + 1),
        venue="Arncliffe Youth Centre #1",
        details_url="https://x/match/r1/",
    )


class TestParseExistingEvents:

    def test_parses_key_and_aware_start(self):
        events = [{
            "id": "abc",
            "start": {"dateTime": "2026-01-15T21:10:00+11:00"},
            "extendedProperties": {"private": {"schedule": "u", "gameKey": "round1"}},
        }]
        parsed = parse_existing_events(events)
        assert parsed == [
            ExistingEvent(
                id="abc", key="round1",
                start=datetime.fromisoformat("2026-01-15T21:10:00+11:00"),
            )
        ]

    def test_legacy_event_without_key(self):
        events = [{
            "id": "abc",
            "start": {"dateTime": "2026-01-15T21:10:00+11:00"},
            "extendedProperties": {"private": {"schedule": "u"}},
        }]
        assert parse_existing_events(events)[0].key is None

    def test_z_suffix_datetime_parses(self):
        events = [{
            "id": "abc",
            "start": {"dateTime": "2026-01-15T10:10:00Z"},
            "extendedProperties": {"private": {}},
        }]
        parsed = parse_existing_events(events)
        assert parsed[0].start.utcoffset().total_seconds() == 0

    def test_all_day_event_skipped_with_warning(self, loguru_messages):
        events = [{"id": "abc", "start": {"date": "2026-01-15"}}]
        assert parse_existing_events(events) == []
        assert any("all-day" in m for m in loguru_messages)


class TestMatchGameToEvent:

    def test_key_match_same_time_is_exact(self):
        game = _game()
        ev = ExistingEvent(id="e1", key="round1", start=game.start)
        assert match_game_to_event(game, [ev]) == ("exact", ev)

    def test_key_match_equal_instant_different_offset_is_exact(self):
        game = _game()  # 21:10 +11:00
        utc_same_instant = game.start.astimezone(ZoneInfo("UTC"))
        ev = ExistingEvent(id="e1", key="round1", start=utc_same_instant)
        assert match_game_to_event(game, [ev]) == ("exact", ev)

    def test_key_match_different_time_is_reschedule(self):
        game = _game()
        ev = ExistingEvent(
            id="e1", key="round1",
            start=datetime(2026, 1, 16, 20, 30, tzinfo=SYDNEY),
        )
        assert match_game_to_event(game, [ev]) == ("reschedule", ev)

    def test_legacy_exact_time_match(self):
        game = _game()
        ev = ExistingEvent(id="e1", key=None, start=game.start)
        assert match_game_to_event(game, [ev]) == ("exact", ev)

    def test_legacy_same_date_is_reschedule(self):
        game = _game()
        ev = ExistingEvent(
            id="e1", key=None,
            start=datetime(2026, 1, 15, 19, 0, tzinfo=SYDNEY),
        )
        assert match_game_to_event(game, [ev]) == ("reschedule", ev)

    def test_no_match_is_create(self):
        game = _game()
        assert match_game_to_event(game, []) == ("create", None)

    def test_different_keys_same_day_do_not_collide(self):
        """Double-header: a keyed event for another game must not be matched."""
        game = _game(key="round2")
        ev = ExistingEvent(
            id="e1", key="round1",
            start=datetime(2026, 1, 15, 19, 0, tzinfo=SYDNEY),
        )
        assert match_game_to_event(game, [ev]) == ("create", None)


class TestBuildReschedulePatch:

    def test_full_patch_payload(self):
        game = _game()
        patch = build_reschedule_patch(game, color_id=9)
        assert patch == {
            "summary": game.title,
            "start": {"dateTime": "2026-01-15T21:10:00+11:00"},
            "end": {"dateTime": "2026-01-15T22:10:00+11:00"},
            "location": game.venue,
            "colorId": "9",
            "description": game.details_url,
            "extendedProperties": {"private": {"gameKey": "round1"}},
        }


class TestBuildFieldPatch:

    def _details(self, game, color_id=9):
        return {
            "summary": game.title,
            "colorId": str(color_id),
            "description": game.details_url,
            "location": game.venue,
            "extendedProperties": {"private": {"gameKey": game.key}},
        }

    def test_no_drift_returns_empty_patch(self):
        game = _game()
        assert build_field_patch(self._details(game), game, color_id=9) == {}

    def test_drifted_summary_patched(self):
        game = _game()
        details = self._details(game)
        details["summary"] = "old name"
        assert build_field_patch(details, game, color_id=9) == {"summary": game.title}

    def test_missing_key_is_adopted(self):
        game = _game()
        details = self._details(game)
        details["extendedProperties"] = {"private": {"schedule": "u"}}
        patch = build_field_patch(details, game, color_id=9)
        assert patch == {"extendedProperties": {"private": {"gameKey": "round1"}}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_event_sync.py -v`
Expected: new tests FAIL with `ImportError`; all pre-existing tests still PASS.

- [ ] **Step 3: Implement**

Append to `helpers/event_sync.py` (keep all existing functions — they are removed in Task 9):

```python
from datetime import datetime

from helpers.models import ExistingEvent, Game


def parse_existing_events(events: list[dict]) -> list[ExistingEvent]:
    """
    Convert raw GCal event dicts into :class:`ExistingEvent` records with
    timezone-aware start datetimes and the ``gameKey`` extended property.

    All-day events (``start.date`` instead of ``start.dateTime``) are skipped
    with a warning — they cannot have been created by this tool.
    """
    parsed: list[ExistingEvent] = []
    for event in events:
        dt_str = event.get("start", {}).get("dateTime")
        if not dt_str:
            logger.warning(
                f"Skipping all-day or malformed event [{event.get('id')}] "
                "— no start.dateTime"
            )
            continue
        start = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        key = (
            event.get("extendedProperties", {})
            .get("private", {})
            .get("gameKey")
        )
        parsed.append(ExistingEvent(id=event["id"], key=key, start=start))
    return parsed


def match_game_to_event(
    game: Game, existing: list[ExistingEvent]
) -> tuple[str, ExistingEvent | None]:
    """
    Match a scraped game against existing calendar events.

    Matching order:

    1. **By key** — an event with the same ``gameKey``: ``exact`` if the start
       instant is unchanged, else ``reschedule``.
    2. **Legacy fallback** — only events *without* a key (created before key
       tracking) are considered: exact start-instant match → ``exact``; same
       calendar date → ``reschedule``. Keyed events for other games are never
       matched, so double-headers cannot collide.
    3. Otherwise ``("create", None)``.

    The caller should remove a returned event from *existing* so it cannot be
    matched twice in one run.
    """
    by_key = {e.key: e for e in existing if e.key}
    if game.key in by_key:
        event = by_key[game.key]
        action = "exact" if event.start == game.start else "reschedule"
        return action, event

    legacy = [e for e in existing if e.key is None]
    for event in legacy:
        if event.start == game.start:
            return "exact", event
    for event in legacy:
        if event.start.date() == game.start.date():
            return "reschedule", event

    return "create", None


def build_reschedule_patch(game: Game, color_id: int | str) -> dict:
    """Build the full patch payload for a rescheduled (or adopted) event."""
    return {
        "summary": game.title,
        "start": {"dateTime": game.start.isoformat()},
        "end": {"dateTime": game.end.isoformat()},
        "location": game.venue,
        "colorId": str(color_id),
        "description": game.details_url,
        "extendedProperties": {"private": {"gameKey": game.key}},
    }


def build_field_patch(event_details: dict, game: Game, color_id: int | str) -> dict:
    """
    Compare an existing event's fields against the scraped game and return a
    single patch dict containing only drifted fields (empty if none).

    Also adds the ``gameKey`` extended property when missing, which migrates
    legacy events to identity-based matching. GCal merges extended property
    keys on patch, so other private properties (``schedule``) are preserved.
    """
    patch: dict = {}
    if event_details.get("summary") != game.title:
        patch["summary"] = game.title
    if event_details.get("colorId") != str(color_id):
        patch["colorId"] = str(color_id)
    if event_details.get("description") != game.details_url:
        patch["description"] = game.details_url
    if event_details.get("location") != game.venue:
        patch["location"] = game.venue
    existing_key = (
        event_details.get("extendedProperties", {}).get("private", {}).get("gameKey")
    )
    if existing_key != game.key:
        patch["extendedProperties"] = {"private": {"gameKey": game.key}}
    return patch
```

Place the `from datetime import datetime` and `from helpers.models import ...` imports at the top of the file with the existing imports (not mid-file).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_event_sync.py -v`
Expected: all PASS (new and old).

- [ ] **Step 5: Commit**

```bash
git add helpers/event_sync.py tests/test_event_sync.py
git commit -m "feat: add identity-based event matching and single-patch diffing"
```

---

### Task 8: Google Calendar client — paginate `list_events`

**Files:**
- Modify: `libs/google_cal_client.py`
- Modify: `helpers/event_sync.py` (`filter_events_by_schedule` signature)
- Modify: `main.py` (one line — `list_events` result is now a list)
- Test: `tests/test_google_cal_client.py`, `tests/test_event_sync.py`

GitNexus symbols touched: `GoogleCalClient.list_events`, `filter_events_by_schedule`, `main.sync_calendar`. Run impact analysis on all three before editing.

- [ ] **Step 1: Write the failing tests**

In `tests/test_google_cal_client.py`, add (adapt the service-mocking style already used in that file — the existing tests mock `build`/`self.service`; follow the same pattern to construct a client with a fake service):

```python
class TestListEventsPagination:

    def _client_with_pages(self, pages):
        """Build a GoogleCalClient with a stubbed events().list() chain."""
        client = object.__new__(GoogleCalClient)  # skip __init__ (no creds)
        service = MagicMock()
        executes = [
            {"items": items, **({"nextPageToken": tok} if tok else {})}
            for items, tok in pages
        ]
        service.events.return_value.list.return_value.execute.side_effect = executes
        client.service = service
        return client, service

    def test_single_page_returns_items_list(self):
        client, _ = self._client_with_pages([([{"id": "a"}], None)])
        assert client.list_events(calendar_id="cal") == [{"id": "a"}]

    def test_follows_next_page_token(self):
        client, service = self._client_with_pages(
            [([{"id": "a"}], "tok1"), ([{"id": "b"}], None)]
        )
        events = client.list_events(calendar_id="cal")
        assert [e["id"] for e in events] == ["a", "b"]
        second_call = service.events.return_value.list.call_args_list[1]
        assert second_call.kwargs["pageToken"] == "tok1"
```

In `tests/test_event_sync.py`, update every existing `filter_events_by_schedule` test to pass a plain list instead of `{"items": [...]}` — e.g. change `filter_events_by_schedule({"items": [ev1, ev2]}, url)` to `filter_events_by_schedule([ev1, ev2], url)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_google_cal_client.py tests/test_event_sync.py -v`
Expected: new pagination tests FAIL (list_events returns a dict / makes one call); updated filter tests FAIL (function still expects a dict).

- [ ] **Step 3: Implement**

Replace `GoogleCalClient.list_events` in `libs/google_cal_client.py`:

```python
    def list_events(self, calendar_id: str = "primary") -> list[dict]:
        """
        Return **all** events for *calendar_id*, following pagination.

        The Calendar API returns at most 250 events per page; without
        pagination, events beyond the first page would be silently missed
        and re-created as duplicates.
        """
        events: list[dict] = []
        page_token: str | None = None
        while True:
            response = self.service.events().list(
                calendarId=calendar_id, pageToken=page_token
            ).execute()
            events.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return events
```

Replace `filter_events_by_schedule` in `helpers/event_sync.py`:

```python
def filter_events_by_schedule(events: list[dict], schedule_url: str) -> list[dict]:
    """
    Return only the events whose ``extendedProperties.private.schedule``
    matches *schedule_url*.
    """
    return [
        event
        for event in events
        if event.get("extendedProperties", {})
           .get("private", {})
           .get("schedule") == schedule_url
    ]
```

No change needed in `main.py` — `sync_calendar` passes `list_events`' result straight into `filter_events_by_schedule`, and both sides changed consistently. Verify by reading `main.py:102-103`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest`
Expected: full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add libs/google_cal_client.py helpers/event_sync.py tests/test_google_cal_client.py tests/test_event_sync.py
git commit -m "fix: paginate Google Calendar event listing"
```

---

### Task 9: Rewire `main.py`, exit non-zero on failure, delete legacy code

**Files:**
- Modify: `main.py`
- Modify: `helpers/event_sync.py` (delete legacy functions)
- Test: `tests/test_event_sync.py` (delete legacy tests)

GitNexus symbols touched: `sync_calendar`, `_create_event`, `main`; deleted: `simplify_existing_events`, `determine_sync_action`, `build_patch_payload`, `apply_field_patches`, `get_game_details`, `format_game_times`. Run impact analysis on the deletions — the only expected upstream caller is `main.py` (and tests).

- [ ] **Step 1: Rewrite `sync_calendar`, `_create_event`, and `main` in `main.py`**

Replace the imports from `helpers.event_sync` and add the new ones:

```python
from helpers.ascii_strings import IMPORTANT_STUFF_1, IMPORTANT_STUFF_2, IMPORTANT_STUFF_3
from helpers.config_loader import CalendarConfig, load_configs
from helpers.event_sync import (
    build_field_patch,
    build_reschedule_patch,
    filter_events_by_schedule,
    match_game_to_event,
    parse_existing_events,
)
from helpers.models import Game
from helpers.sources import fetch_games
from libs.google_cal_client import GoogleCalClient
from libs.scraper_client import ScraperClient
```

Replace `sync_calendar` and `_create_event`:

```python
def sync_calendar(
    gclient: GoogleCalClient,
    scraper: ScraperClient,
    config: CalendarConfig,
) -> None:
    """
    Fetch the schedule for *config* and sync it into Google Calendar.

    Games are matched to existing events by their stable ``gameKey``
    (extended property); legacy keyless events are matched by start time
    once and adopt a key via the field patch. For each game:

    * **exact** — event exists at the right time; drifted fields are patched.
    * **reschedule** — event exists but the time changed; fully re-patched.
    * **create** — no matching event; a new one is inserted.
    """
    games = fetch_games(scraper, config)

    logger.log("MAJOR", IMPORTANT_STUFF_1)
    calendar_id = get_or_create_calendar(gclient, config.name, config.url)

    logger.log("MAJOR", IMPORTANT_STUFF_2)
    all_events = gclient.list_events(calendar_id=calendar_id)
    schedule_events = filter_events_by_schedule(all_events, config.url)
    existing = parse_existing_events(schedule_events)

    for game in games:
        action, matched = match_game_to_event(game, existing)
        if matched is not None:
            existing.remove(matched)  # an event can only be matched once per run

        if action == "exact":
            logger.info(f"[{game.title}] already exists — checking for stale fields...")
            event_details = gclient.get_event_details(
                calendar_id=calendar_id, event_id=matched.id
            )
            patch = build_field_patch(event_details, game, config.color_id)
            if patch:
                gclient.patch_event(
                    calendar_id=calendar_id, event_id=matched.id, patched_fields=patch
                )
                logger.info(f"\tPatched {sorted(patch)} for [{game.title}]")

        elif action == "reschedule":
            logger.info(f"[{game.title}] has been rescheduled — patching...")
            patch = build_reschedule_patch(game, config.color_id)
            gclient.patch_event(
                calendar_id=calendar_id, event_id=matched.id, patched_fields=patch
            )
            logger.info(
                f"\tEvent [{game.title}] updated to [{game.start.isoformat()}] "
                f"- id [{matched.id}]"
            )

        else:  # "create"
            _create_event(gclient, calendar_id, game, config)

    logger.success(f"Finished syncing '{config.name}'")


def _create_event(
    gclient: GoogleCalClient,
    calendar_id: str,
    game: Game,
    config: CalendarConfig,
) -> None:
    """Insert a new Google Calendar event and log the result."""
    logger.info(f"[{game.title}] is a new event — creating...")
    event_id = gclient.create_event(
        calendar_id=calendar_id,
        event_name=game.title,
        start_time=game.start.isoformat(),
        end_time=game.end.isoformat(),
        location=game.venue,
        private_properties={"schedule": config.url, "gameKey": game.key},
        color_id=config.color_id,
        description=game.details_url,
    )
    logger.success(f"\tEvent [{event_id}] created for [{game.title}]")
```

Replace the config loop at the end of `main()`:

```python
    configs = load_configs(CONFIG_DIR)

    failures: list[str] = []
    for config in configs:
        try:
            sync_calendar(gclient=gclient, scraper=scraper, config=config)
        except Exception:
            logger.exception(f"Failed to sync calendar '{config.name}'")
            failures.append(config.name)

    logger.log("MAJOR", IMPORTANT_STUFF_3)

    if failures:
        logger.error(
            f"{len(failures)}/{len(configs)} calendar(s) failed to sync: {failures}"
        )
        sys.exit(1)
```

- [ ] **Step 2: Delete legacy functions and their tests**

From `helpers/event_sync.py` delete: `format_game_times`, `get_game_details`, `simplify_existing_events`, `build_patch_payload`, `determine_sync_action`, `apply_field_patches` (and the now-unused `TYPE_CHECKING` import block for `GoogleCalClient` if nothing else uses it).

From `tests/test_event_sync.py` delete every test class/function that exercises those six functions.

- [ ] **Step 3: Verify nothing still references deleted symbols**

Run: `uv run python -c "import main; print('ok')"`
Expected: `ok`

Run: `grep -rn "get_game_details\|simplify_existing_events\|determine_sync_action\|build_patch_payload\|apply_field_patches\|format_game_times" --include="*.py" .`
Expected: no matches (outside `.venv`).

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest`
Expected: all PASS.

- [ ] **Step 5: Smoke-test the real pipeline (requires `.env` credentials)**

Run: `uv run python main.py`
Expected: for each active config — API source logs `API source: N games`, existing events are matched (`already exists — checking for stale fields`), legacy events get a one-time `Patched ['extendedProperties'] ...` adoption patch, **no duplicate events are created** (verify in Google Calendar UI), and exit code is 0 (`echo $?` / `$LASTEXITCODE`).

If this smoke test cannot be run (no credentials), state that explicitly rather than claiming it passed.

- [ ] **Step 6: Commit**

```bash
git add main.py helpers/event_sync.py tests/test_event_sync.py
git commit -m "feat: switch pipeline to API source with identity matching, fail loudly"
```

---

### Task 10: Documentation updates

**Files:**
- Modify: `.github/README.md`

- [ ] **Step 1: Update the project-structure block**

In `.github/README.md`, replace the `helpers/`/`libs/` entries of the structure diagram with:

```
├── helpers/
│   ├── ascii_strings.py        # ASCII art banners used in log output
│   ├── config_loader.py        # Loads and validates calendar-configs/*.yaml files
│   ├── event_sync.py           # Pure functions: identity-based event matching and diffing
│   ├── html_parser.py          # BeautifulSoup HTML parsing (fallback source)
│   ├── models.py               # Game / ExistingEvent dataclasses
│   └── sources.py              # Schedule sources: WordPress JSON API (primary) + HTML fallback
├── libs/
│   ├── google_cal_client.py    # Google Calendar API client (OAuth2)
│   └── scraper_client.py       # HTTP client with retry — HTML and JSON fetching
```

- [ ] **Step 2: Document the source behaviour and exit code**

In the "Adding a new team calendar" section, extend the YAML example:

```yaml
name: My Team Name        # Must be unique across all your calendars
url: https://sydneysocialbasketball.com.au/team/<slug>/
color_id: 5               # Integer 1–11 (see colors.yaml for reference)
source: ssb-api           # Optional: "ssb-api" (default, JSON API with HTML fallback) or "ssb-html"
```

Below the intro paragraph ("A Python script that scrapes…"), update the first sentence to mention the API:

> Fetches schedules from the SSB WordPress JSON API (falling back to HTML scraping if the API is unavailable) and syncs them into Google Calendar — creating new events, updating reschedules, and patching stale fields automatically. The run exits non-zero if any calendar fails to sync, so the GitHub Actions badge and email notifications surface failures.

- [ ] **Step 3: Run the suite one last time and commit**

Run: `uv run pytest`
Expected: all PASS.

```bash
git add .github/README.md
git commit -m "docs: document API source, fallback, and failure behaviour"
```

---

## Post-plan follow-ups (not part of this plan)

- Delete events for cancelled games (now possible via `gameKey`).
- Per-season config rollover is still manual (team posts are per-season) — a future source could auto-discover the newest team post by name.
- The committed `logs/` directory contents are stale local artifacts (gitignored going forward, but old files can be cleaned up).

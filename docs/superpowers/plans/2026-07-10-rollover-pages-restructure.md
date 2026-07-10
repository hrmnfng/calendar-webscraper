# src Restructure + Season Rollover + Calendar Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the repo under `src/`, add a weekly GitHub Actions job that PRs season rollovers of `calendar-configs/*.yaml`, and auto-publicize calendars + deploy a GitHub Pages site of subscribe links on every successful sync run.

**Architecture:** Part 0 is a mechanical `git mv` into `src/` (imports unchanged — bare `helpers`/`libs` packages). Part 1 adds pure rollover-detection logic in `helpers/rollover.py` driven by a thin CLI (`src/check_rollover.py`) and a weekly workflow that commits changes to a fixed branch and opens/updates one PR via `gh` (no third-party actions). Part 2 adds `GoogleCalClient.ensure_calendar_public` (ACL insert), a pure `helpers/site_builder.py` HTML renderer, and a Pages deploy job on the daily workflow.

**Tech Stack:** Python 3.13, requests + tenacity (existing `ScraperClient`), Google Calendar API ACL, pytest, uv, GitHub Actions (`gh` CLI, `actions/upload-pages-artifact`, `actions/deploy-pages`).

**Spec:** `docs/superpowers/specs/2026-07-10-rollover-pages-restructure-design.md`

---

## Verified facts (researched live, 2026-07-10 — do not re-derive)

1. Team posts are per-season: `leteam-12` = "LeTeam 2025 s4", `leteam-14` = "LeTeam 2026 s1". **The LeTeam config is stale today** — the first real rollover run should update it.
2. Preseason/grading posts interleave by date ("LeTeam 2026 s1 preseason" = `leteam-13`) and **count as newer versions** (user decision).
3. Slugs are not ordered cleanly (`leteam-8-2`, `the-leteam`) — order candidates by the post `date` field, never by slug.
4. WP search is fuzzy: `team?search=LeTeam` also returns "The LeTeam 2025 s2". Filter candidates to unescaped titles starting with `"<base name> "`.
5. Making a calendar public via API works: `acl().insert(calendarId=..., body={"role": "reader", "scope": {"type": "default"}})` is exactly what the UI's "Make available to public" toggle does. A `freeBusyReader` default rule does NOT count as public for our purposes.
6. `.gitignore` already ignores `/site` (line 143, originally for mkdocs) — the generated `site/index.html` needs no gitignore change.

## CLAUDE.md compliance note

If the GitNexus MCP tools are available, run `gitnexus_impact` before modifying listed symbols and `gitnexus_detect_changes()` before commits. If not available (as in the planning session), note that when committing, grep for callers of changed symbols, and rely on the full test suite — per the AGENTS.md fallback section.

## One-time repo settings (user actions, not code)

- Settings → Actions → General → **"Allow GitHub Actions to create and approve pull requests"** (needed before Task 4's workflow can open PRs).
- Settings → Pages → Source: **"GitHub Actions"** (needed before Task 8's deploy job can run).
- After the first successful Pages deploy: edit issue #13 to link the page URL, then close it.

## File structure

| File | Action | Responsibility |
|---|---|---|
| `src/main.py`, `src/helpers/*`, `src/libs/*` | Move | Unchanged modules under `src/` |
| `pyproject.toml` | Modify | pytest `pythonpath`, hatch packages, coverage source, drop unused console script |
| `src/helpers/rollover.py` | Create | Pure rollover detection + config rewrite + PR-body summary |
| `src/check_rollover.py` | Create | CLI entry: iterate configs, write `rollover-summary.md` |
| `.github/workflows/config-rollover.yml` | Create | Weekly check → branch → PR via `gh` |
| `src/libs/google_cal_client.py` | Modify | `ensure_calendar_public` |
| `src/helpers/site_builder.py` | Create | Pure HTML page renderer |
| `src/main.py` | Modify | Call `ensure_calendar_public`; collect synced calendars; write `site/index.html` |
| `.github/workflows/execute-script.yml` | Modify | `src/` path; upload artifact + deploy-pages job |
| `.gitignore` | Modify | Ignore `rollover-summary.md` |
| `.github/README.md` | Modify | Structure, run commands, remove manual-publicize note, document new automation |
| `tests/test_rollover.py` | Create | Rollover unit tests |
| `tests/test_site_builder.py` | Create | Page renderer unit tests |
| `tests/test_google_cal_client.py` | Modify | `ensure_calendar_public` tests |

All commands run from the repo root. Every task leaves the suite green.

---

### Task 0: Feature branch

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feat/season-rollover-and-pages
```

---

### Task 1: Restructure to `src/` (mechanical, no behaviour change)

**Files:**
- Move: `main.py` → `src/main.py`, `helpers/` → `src/helpers/`, `libs/` → `src/libs/`
- Modify: `pyproject.toml`, `src/libs/google_cal_client.py` (one error-message path), `.github/workflows/execute-script.yml` (run command)

- [ ] **Step 1: Move the files with git mv**

```bash
mkdir src
git mv main.py src/main.py
git mv helpers src/helpers
git mv libs src/libs
```

- [ ] **Step 2: Update `pyproject.toml`**

Replace these sections (leave `[project]` dependencies and `[dependency-groups]` untouched):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--tb=short"
pythonpath = ["src"]

[tool.coverage.run]
source = ["src"]
omit = ["tests/*"]

[tool.hatch.build.targets.wheel]
packages = ["src/helpers", "src/libs"]
```

Delete the `[project.scripts]` block entirely — `calendar-webscraper = "main:main"` cannot resolve once `main.py` lives outside the installed packages, and nothing (workflows, README) uses the console script; the documented run command is `python src/main.py`.

- [ ] **Step 3: Fix the credential-hint path in `src/libs/google_cal_client.py`**

In `__init__`, change the `sys.exit` message:

```python
                sys.exit(
                    'Credentials are invalid. Please generate a new refresh token '
                    'by running `uv run python src/libs/google_cal_client.py`.'
                )
```

- [ ] **Step 4: Update the run command in `.github/workflows/execute-script.yml`**

Change the last step:

```yaml
      - name: Run script
        run: uv run python src/main.py
```

- [ ] **Step 5: Re-sync and verify everything still works**

```bash
uv sync
uv run pytest
uv run python -c "import helpers.models, libs.scraper_client; print('imports ok')"
```

Expected: `uv sync` rebuilds the editable install against `src/`; all 132 tests pass (pytest resolves `helpers`/`libs` via `pythonpath`); import check prints `imports ok`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move application code under src/"
```

---

### Task 2: Rollover pure helpers — `base_team_name`, `find_newest_team_post`, `rewrite_config_url`, `build_summary`

**Files:**
- Create: `src/helpers/rollover.py`
- Create: `tests/test_rollover.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rollover.py`:

```python
"""
Unit tests for helpers.rollover — season rollover detection and config rewrite.
"""

from __future__ import annotations

from helpers.rollover import (
    RolloverResult,
    base_team_name,
    build_summary,
    find_newest_team_post,
    rewrite_config_url,
)


def _post(slug: str, title: str, date: str) -> dict:
    return {"slug": slug, "title": {"rendered": title}, "date": date}


CONFIG_TEXT = (
    'name: "LeTeam"\n'
    'url: "https://sydneysocialbasketball.com.au/team/leteam-12/"\n'
    "color_id: 9\n"
)


class TestBaseTeamName:
    def test_strips_regular_season(self):
        assert base_team_name("LeTeam 2025 s4") == "LeTeam"

    def test_strips_preseason_suffix(self):
        assert base_team_name("LeTeam 2026 s1 preseason") == "LeTeam"

    def test_unescapes_entities(self):
        assert base_team_name("40s &amp; Shorties 2025 s4") == "40s & Shorties"

    def test_no_season_suffix_returns_none(self):
        assert base_team_name("The LeTeam") is None


class TestFindNewestTeamPost:
    def test_picks_newest_by_date(self):
        posts = [
            _post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04"),
            _post("leteam-14", "LeTeam 2026 s1", "2026-04-13T11:16:45"),
        ]
        assert find_newest_team_post(posts, "LeTeam")["slug"] == "leteam-14"

    def test_preseason_posts_count_as_newer(self):
        posts = [
            _post("leteam-14", "LeTeam 2026 s1", "2026-04-13T11:16:45"),
            _post("leteam-15", "LeTeam 2026 s2 preseason", "2026-07-01T09:00:00"),
        ]
        assert find_newest_team_post(posts, "LeTeam")["slug"] == "leteam-15"

    def test_fuzzy_search_hits_excluded_by_prefix(self):
        posts = [_post("the-leteam", "The LeTeam 2025 s2", "2025-04-02T08:43:50")]
        assert find_newest_team_post(posts, "LeTeam") is None

    def test_empty_returns_none(self):
        assert find_newest_team_post([], "LeTeam") is None


class TestRewriteConfigUrl:
    def test_replaces_url_preserving_other_lines(self, tmp_path):
        path = tmp_path / "config-leteam.yaml"
        path.write_text(CONFIG_TEXT)
        rewrite_config_url(
            path, "https://sydneysocialbasketball.com.au/team/leteam-14/"
        )
        text = path.read_text()
        assert 'url: "https://sydneysocialbasketball.com.au/team/leteam-14/"' in text
        assert 'name: "LeTeam"' in text
        assert "color_id: 9" in text


class TestBuildSummary:
    def test_renders_table_row_per_result(self):
        results = [
            RolloverResult("config-leteam.yaml", "updated", "leteam-12 → leteam-14"),
            RolloverResult("config-shake-shaq.yaml", "unchanged", "already newest"),
        ]
        summary = build_summary(results)
        assert "| `config-leteam.yaml` | updated | leteam-12 → leteam-14 |" in summary
        assert "| `config-shake-shaq.yaml` | unchanged | already newest |" in summary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rollover.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'helpers.rollover'`.

- [ ] **Step 3: Implement**

Create `src/helpers/rollover.py`:

```python
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
```

(`yaml`, `_get_all_pages`, `_team_slug`, `_wp_api_base`, and `ScraperClient` are used by `check_config_rollover` in Task 3 — the imports land now so the module is complete in one shape.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rollover.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/helpers/rollover.py tests/test_rollover.py
git commit -m "feat: add season rollover detection helpers"
```

---

### Task 3: `check_config_rollover` + CLI entry point

**Files:**
- Modify: `src/helpers/rollover.py`
- Create: `src/check_rollover.py`
- Test: `tests/test_rollover.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rollover.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

from helpers.rollover import check_config_rollover


class TestCheckConfigRollover:
    def _client(self, current_posts: list, search_pages: list[list]) -> MagicMock:
        """Fake ScraperClient: first get_json call resolves the current slug,
        subsequent calls are the paginated search pages."""
        client = MagicMock()
        client.get_json.side_effect = [current_posts] + search_pages
        return client

    def _config(self, tmp_path) -> Path:
        path = tmp_path / "config-leteam.yaml"
        path.write_text(CONFIG_TEXT)
        return path

    def test_updates_stale_config(self, tmp_path):
        path = self._config(tmp_path)
        client = self._client(
            [_post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04")],
            [[
                _post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04"),
                _post("leteam-14", "LeTeam 2026 s1", "2026-04-13T11:16:45"),
            ]],
        )
        result = check_config_rollover(client, path)
        assert result.status == "updated"
        assert "leteam-12" in result.detail and "leteam-14" in result.detail
        assert "team/leteam-14/" in path.read_text()

    def test_unchanged_when_already_newest(self, tmp_path):
        path = self._config(tmp_path)
        client = self._client(
            [_post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04")],
            [[_post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04")]],
        )
        result = check_config_rollover(client, path)
        assert result.status == "unchanged"
        assert "team/leteam-12/" in path.read_text()  # file untouched

    def test_skips_when_slug_not_found_on_site(self, tmp_path):
        path = self._config(tmp_path)
        client = self._client([], [])
        result = check_config_rollover(client, path)
        assert result.status == "skipped"
        assert "leteam-12" in result.detail

    def test_skips_when_title_has_no_season_suffix(self, tmp_path):
        path = self._config(tmp_path)
        client = self._client(
            [_post("leteam-12", "Some Oddball Title", "2025-12-12T11:19:04")], []
        )
        result = check_config_rollover(client, path)
        assert result.status == "skipped"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rollover.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'check_config_rollover'`; Task 2 tests still PASS.

- [ ] **Step 3: Implement**

Append to `src/helpers/rollover.py`:

```python
def check_config_rollover(client: ScraperClient, config_path: Path) -> RolloverResult:
    """
    Check one config file against the site; rewrite its ``url:`` line if a
    newer season post exists for the team.
    """
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    url = (raw or {}).get("url", "")
    if not url:
        return RolloverResult(config_path.name, "skipped", "no url field")

    api_base = _wp_api_base(url)
    slug = _team_slug(url)

    current_posts = client.get_json(f"{api_base}/team", params={"slug": slug})
    if not current_posts:
        return RolloverResult(
            config_path.name, "skipped", f"slug {slug!r} not found on site"
        )

    current_title = html.unescape(current_posts[0]["title"]["rendered"])
    base_name = base_team_name(current_title)
    if base_name is None:
        return RolloverResult(
            config_path.name,
            "skipped",
            f"no season suffix in title {current_title!r}",
        )

    posts = _get_all_pages(client, f"{api_base}/team", params={"search": base_name})
    newest = find_newest_team_post(posts, base_name)
    if newest is None:
        return RolloverResult(
            config_path.name, "skipped", f"no posts match {base_name!r}"
        )

    if newest["slug"] == slug:
        return RolloverResult(config_path.name, "unchanged", f"already on {slug!r}")

    new_url = url.rstrip("/").rsplit("/", 1)[0] + f"/{newest['slug']}/"
    rewrite_config_url(config_path, new_url)
    newest_title = html.unescape(newest["title"]["rendered"])
    return RolloverResult(
        config_path.name,
        "updated",
        f"{slug} → {newest['slug']} ({newest_title!r})",
    )
```

Create `src/check_rollover.py`:

```python
"""
CLI: check every active calendar config for a newer season team post and
rewrite stale URLs in place, writing a markdown summary for the PR body.

Run from the repo root: ``uv run python src/check_rollover.py``.

Always exits 0 when the check ran to completion — the workflow detects
changes via ``git diff``, not the exit code. Per-config errors are logged
and reported as "skipped"; they never abort the other configs. Needs no
Google credentials (public WP API only).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from helpers.rollover import RolloverResult, build_summary, check_config_rollover
from libs.scraper_client import ScraperClient

CONFIG_DIR = Path("./calendar-configs")
SUMMARY_PATH = Path("rollover-summary.md")


def main() -> None:
    client = ScraperClient("Season Checker")
    results: list[RolloverResult] = []

    for config_path in sorted(CONFIG_DIR.glob("config-*.yaml")):
        try:
            result = check_config_rollover(client, config_path)
        except Exception as exc:
            logger.exception(f"Rollover check failed for {config_path.name}")
            result = RolloverResult(config_path.name, "skipped", f"error: {exc}")
        results.append(result)
        logger.info(f"{result.config_file}: {result.status} — {result.detail}")

    SUMMARY_PATH.write_text(build_summary(results), encoding="utf-8")
    updated = [r for r in results if r.status == "updated"]
    logger.info(f"{len(updated)}/{len(results)} config(s) updated")


if __name__ == "__main__":
    main()
```

(`CONFIG_DIR.glob("config-*.yaml")` naturally excludes `.yaml.disable` files.)

- [ ] **Step 4: Run tests, then a live smoke test**

Run: `uv run pytest`
Expected: full suite PASS.

Run: `uv run python src/check_rollover.py`
Expected: LeTeam reports `updated` (`leteam-12 → leteam-14 ('LeTeam 2026 s1')` or newer), the other configs report `updated` or `unchanged` per current site state, `rollover-summary.md` is written, exit 0.

Then **revert the live changes** — the real update must arrive via the workflow PR:

```bash
git checkout -- calendar-configs
rm rollover-summary.md
```

- [ ] **Step 5: Add `rollover-summary.md` to `.gitignore`**

Append to `.gitignore`:

```
# generated by src/check_rollover.py
rollover-summary.md
```

- [ ] **Step 6: Commit**

```bash
git add src/helpers/rollover.py src/check_rollover.py tests/test_rollover.py .gitignore
git commit -m "feat: add config season rollover checker CLI"
```

---

### Task 4: Weekly rollover workflow

**Files:**
- Create: `.github/workflows/config-rollover.yml`

- [ ] **Step 1: Create the workflow**

```yaml
# Weekly check for newer per-season team pages on the SSB site.
# Rewrites stale calendar-configs/*.yaml URLs and raises a single combined PR.
# Runs Monday 6am AEST (UTC+10), or on manual dispatch.

name: Config Season Rollover

on:
  workflow_dispatch:

  schedule:
    - cron: '0 20 * * 0' # Monday 6am AEST (Sunday 20:00 UTC)

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: true

jobs:
  check-rollover:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version-file: ".python-version"

      - name: Install dependencies
        run: uv sync --no-dev

      - name: Check for newer team pages
        run: uv run python src/check_rollover.py

      - name: Create or update rollover PR
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          if git diff --quiet -- calendar-configs; then
            echo "All configs are on the newest season pages — nothing to do."
            exit 0
          fi
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git checkout -B chore/config-rollover
          git add calendar-configs
          git commit -m "chore: roll calendar configs to newest season pages"
          git push --force origin chore/config-rollover
          if [ "$(gh pr list --head chore/config-rollover --state open --json number --jq length)" = "0" ]; then
            gh pr create \
              --title "chore: config season rollover" \
              --body-file rollover-summary.md \
              --base main
          else
            gh pr edit chore/config-rollover --body-file rollover-summary.md
          fi
```

Notes baked into the design: the branch is force-pushed each run (its history is disposable — each run reflects current site state); `gh pr edit` refreshes the body when a PR is already open so re-runs never duplicate; `GH_TOKEN` is the built-in token — no new secrets.

- [ ] **Step 2: Validate the YAML parses**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/config-rollover.yml')); print('workflow yaml ok')"`
Expected: `workflow yaml ok`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/config-rollover.yml
git commit -m "ci: add weekly config season rollover workflow"
```

(The end-to-end proof is a manual `workflow_dispatch` after merge — LeTeam is genuinely stale, so the first run should open a real PR. Requires the "Allow GitHub Actions to create and approve pull requests" repo setting.)

---

### Task 5: `GoogleCalClient.ensure_calendar_public`

**Files:**
- Modify: `src/libs/google_cal_client.py`
- Test: `tests/test_google_cal_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_google_cal_client.py` (same `object.__new__` service-stub style as `TestListEventsPagination` in that file):

```python
class TestEnsureCalendarPublic:
    def _client_with_acl(self, items):
        """Build a GoogleCalClient with a stubbed acl() chain."""
        client = object.__new__(GoogleCalClient)  # skip __init__ (no creds)
        service = MagicMock()
        service.acl.return_value.list.return_value.execute.return_value = {
            "items": items
        }
        client.service = service
        return client, service

    def test_inserts_default_reader_rule_when_not_public(self):
        client, service = self._client_with_acl(
            [{"role": "owner", "scope": {"type": "user", "value": "me@example.com"}}]
        )
        client.ensure_calendar_public("cal-1")
        service.acl.return_value.insert.assert_called_once_with(
            calendarId="cal-1",
            body={"role": "reader", "scope": {"type": "default"}},
        )

    def test_noop_when_already_public(self):
        client, service = self._client_with_acl(
            [{"role": "reader", "scope": {"type": "default"}}]
        )
        client.ensure_calendar_public("cal-1")
        service.acl.return_value.insert.assert_not_called()

    def test_freebusy_only_rule_does_not_count_as_public(self):
        client, service = self._client_with_acl(
            [{"role": "freeBusyReader", "scope": {"type": "default"}}]
        )
        client.ensure_calendar_public("cal-1")
        service.acl.return_value.insert.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_google_cal_client.py -v`
Expected: 3 new tests FAIL with `AttributeError: ... has no attribute 'ensure_calendar_public'`; existing tests PASS.

- [ ] **Step 3: Implement**

Add to `src/libs/google_cal_client.py` after `patch_calendar`:

```python
    def ensure_calendar_public(self, calendar_id: str) -> None:
        """
        Make the calendar publicly readable if it isn't already.

        Inserts an ACL rule with the ``default`` scope and ``reader`` role —
        the exact grant the Google Calendar UI's "Make available to public"
        toggle creates. A ``freeBusyReader`` default rule does not count:
        event details must be visible for the shared links to be useful.
        Idempotent; safe to call on every sync run.
        """
        rules = self.service.acl().list(calendarId=calendar_id).execute()
        for rule in rules.get("items", []):
            if (
                rule.get("scope", {}).get("type") == "default"
                and rule.get("role") == "reader"
            ):
                logger.debug(f"Calendar [{calendar_id}] is already public")
                return
        self.service.acl().insert(
            calendarId=calendar_id,
            body={"role": "reader", "scope": {"type": "default"}},
        ).execute()
        logger.info(f"Calendar [{calendar_id}] made publicly readable")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_google_cal_client.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/libs/google_cal_client.py tests/test_google_cal_client.py
git commit -m "feat: auto-publicize calendars via ACL default reader rule"
```

---

### Task 6: `helpers/site_builder.py` — the calendar links page

**Files:**
- Create: `src/helpers/site_builder.py`
- Create: `tests/test_site_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_site_builder.py`:

```python
"""
Unit tests for helpers.site_builder — pure HTML rendering.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from helpers.site_builder import build_site

SYDNEY = ZoneInfo("Australia/Sydney")
UPDATED = datetime(2026, 7, 10, 6, 0, tzinfo=SYDNEY)
CAL_ID = "abc123@group.calendar.google.com"


class TestBuildSite:
    def test_contains_team_name_and_encoded_calendar_id(self):
        page = build_site([("LeTeam", CAL_ID)], updated=UPDATED)
        assert "LeTeam" in page
        assert "abc123%40group.calendar.google.com" in page

    def test_contains_all_three_link_kinds(self):
        page = build_site([("LeTeam", CAL_ID)], updated=UPDATED)
        assert "calendar.google.com/calendar/embed?src=" in page
        assert "ctz=Australia%2FSydney" in page
        assert "/public/basic.ics" in page
        assert "outlook.live.com/calendar/0/addfromweb" in page

    def test_outlook_link_wraps_encoded_ics_url(self):
        page = build_site([("LeTeam", CAL_ID)], updated=UPDATED)
        assert (
            "addfromweb?url=https%3A%2F%2Fcalendar.google.com%2Fcalendar%2Fical"
            in page
        )

    def test_escapes_html_in_team_names(self):
        page = build_site([("40s & Shorties", CAL_ID)], updated=UPDATED)
        assert "40s &amp; Shorties" in page

    def test_footer_contains_updated_timestamp(self):
        page = build_site([], updated=UPDATED)
        assert "2026-07-10" in page

    def test_subscribe_hint_present(self):
        page = build_site([], updated=UPDATED)
        assert "subscribe" in page.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_site_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'helpers.site_builder'`.

- [ ] **Step 3: Implement**

Create `src/helpers/site_builder.py`:

```python
"""
Renders the public GitHub Pages site listing calendar subscribe links.

Pure function: no I/O. main.py writes the result to site/index.html after a
fully successful sync run, and the workflow deploys that directory to Pages.
"""

from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import quote


def _row(name: str, calendar_id: str) -> str:
    cid = quote(calendar_id, safe="")
    ics_url = f"https://calendar.google.com/calendar/ical/{cid}/public/basic.ics"
    google_url = (
        f"https://calendar.google.com/calendar/embed?src={cid}"
        "&ctz=Australia%2FSydney"
    )
    outlook_url = (
        "https://outlook.live.com/calendar/0/addfromweb"
        f"?url={quote(ics_url, safe='')}&name={quote(name)}"
    )
    safe_name = html.escape(name)
    return (
        "      <tr>\n"
        f"        <td><strong>{safe_name}</strong></td>\n"
        f'        <td><a href="{google_url}">Google Calendar</a></td>\n'
        f'        <td><a href="{outlook_url}">Outlook</a></td>\n'
        f'        <td><a href="{ics_url}">ICS (Apple / other)</a></td>\n'
        "      </tr>"
    )


def build_site(entries: list[tuple[str, str]], updated: datetime) -> str:
    """
    Render the full HTML page for ``[(team_name, calendar_id), ...]``.

    ``updated`` is injected (not read from the clock) so rendering stays pure
    and testable; the caller passes Sydney "now".
    """
    rows = "\n".join(_row(name, calendar_id) for name, calendar_id in entries)
    timestamp = updated.strftime("%Y-%m-%d %H:%M %Z")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SSB Team Calendars</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd; text-align: left; }}
    footer {{ margin-top: 2rem; color: #666; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <h1>SSB Team Calendars</h1>
  <p>Public Google Calendars for each team's schedule, updated automatically
     every morning. Pick your calendar app's link below.</p>
  <table>
    <thead>
      <tr><th>Team</th><th colspan="3">Add to your calendar</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <p><em>Tip: <strong>subscribe</strong> to the ICS link (Outlook: "Add calendar
     &rarr; Subscribe from web"; Apple: "File &rarr; New Calendar Subscription")
     rather than downloading it &mdash; subscribed calendars update automatically,
     a downloaded file is a one-off snapshot.</em></p>
  <footer>Last updated {timestamp} &middot;
    <a href="https://github.com/hrmnfng/calendar-webscraper">calendar-webscraper</a>
  </footer>
</body>
</html>
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_site_builder.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/helpers/site_builder.py tests/test_site_builder.py
git commit -m "feat: add calendar links page renderer"
```

---

### Task 7: Wire publicize + page build into `main.py`

**Files:**
- Modify: `src/main.py`

GitNexus symbols touched: `sync_calendar`, `main`.

- [ ] **Step 1: Update imports and `sync_calendar`**

In `src/main.py`, add to the imports:

```python
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from helpers.site_builder import build_site
```

In `sync_calendar`, change the signature's return annotation from `-> None` to `-> str`, add the publicize call right after `get_or_create_calendar`, and return the calendar ID at the end:

```python
    logger.log("MAJOR", IMPORTANT_STUFF_1)
    calendar_id = get_or_create_calendar(gclient, config.name, config.url)
    gclient.ensure_calendar_public(calendar_id)
```

```python
    logger.success(f"Finished syncing '{config.name}'")
    return calendar_id
```

- [ ] **Step 2: Collect synced calendars and write the site in `main()`**

Replace the config loop and failure handling at the end of `main()`:

```python
    configs = load_configs(CONFIG_DIR)

    failures: list[str] = []
    synced: list[tuple[str, str]] = []
    for config in configs:
        try:
            calendar_id = sync_calendar(gclient=gclient, scraper=scraper, config=config)
            synced.append((config.name, calendar_id))
        except Exception:
            logger.exception(f"Failed to sync calendar '{config.name}'")
            failures.append(config.name)

    logger.log("MAJOR", IMPORTANT_STUFF_3)

    if failures:
        logger.error(
            f"{len(failures)}/{len(configs)} calendar(s) failed to sync: {failures}"
        )
        sys.exit(1)

    # Only written on a fully successful run — a failed run leaves the
    # previously deployed page in place rather than publishing a partial list.
    site_path = Path("site/index.html")
    site_path.parent.mkdir(exist_ok=True)
    site_path.write_text(
        build_site(synced, updated=datetime.now(tz=ZoneInfo("Australia/Sydney"))),
        encoding="utf-8",
    )
    logger.success(f"Wrote calendar links page to {site_path}")
```

- [ ] **Step 3: Run the suite, then smoke-test the real pipeline (requires `.env` credentials)**

Run: `uv run pytest`
Expected: all PASS.

Run: `uv run python src/main.py`
Expected: each calendar logs either `already public` (debug) or `made publicly readable`; run finishes exit 0; `site/index.html` exists and contains one row per active config with the real calendar IDs. Open it and spot-check a link.

If credentials are unavailable, state that explicitly rather than claiming the smoke test passed.

- [ ] **Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat: publicize calendars and write links page on successful runs"
```

---

### Task 8: Pages deploy in `execute-script.yml`

**Files:**
- Modify: `.github/workflows/execute-script.yml`

- [ ] **Step 1: Rewrite the workflow with the deploy job**

Full new content of `.github/workflows/execute-script.yml`:

```yaml
# Fetches basketball schedules (WP API with HTML fallback) and syncs them to
# Google Calendar, then deploys the public calendar-links page to GitHub Pages.
# Runs daily at 6am AEST (UTC+10), or on manual dispatch.

name: Schedule to Calendar

on:
  workflow_dispatch:
    inputs:
      log-level:
        description: "Log level for action run"
        default: 'INFO'
        type: choice
        options:
          - MAJOR
          - INFO
          - DEBUG

  schedule:
    - cron: '0 20 * * *' # 6am AEST (UTC+10)

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  run-script:
    runs-on: ubuntu-latest
    env:
      GCAL_CLIENT_ID: ${{ secrets.GCAL_CLIENT_ID }}
      GCAL_CLIENT_SECRET: ${{ secrets.GCAL_CLIENT_SECRET }}
      GCAL_REFRESH_TOKEN: ${{ secrets.GCAL_REFRESH_TOKEN }}
      LOG_LEVEL: INFO

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version-file: ".python-version"

      - name: Install dependencies
        run: uv sync --no-dev

      - name: Set log level
        run: |
          if [[ "${{ inputs.log-level }}" != "" ]]; then
            echo "LOG_LEVEL=${{ inputs.log-level }}" >> $GITHUB_ENV
          fi
          if [[ "${{ runner.debug }}" == "1" ]]; then
            echo "LOG_LEVEL=DEBUG" >> $GITHUB_ENV
          fi

      - name: Run script
        run: uv run python src/main.py

      - name: Upload calendar links page
        uses: actions/upload-pages-artifact@v3
        with:
          path: site

  deploy-pages:
    needs: run-script
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

(A failed `Run script` step means the upload never happens and `deploy-pages` is skipped — the published page stays at its last good state. Both Pages actions are GitHub-official.)

- [ ] **Step 2: Validate the YAML parses**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/execute-script.yml')); print('workflow yaml ok')"`
Expected: `workflow yaml ok`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/execute-script.yml
git commit -m "ci: deploy calendar links page to GitHub Pages after successful syncs"
```

---

### Task 9: Documentation

**Files:**
- Modify: `.github/README.md`

- [ ] **Step 1: Update the project structure block**

Replace the structure diagram's code entries with:

```
calendar-webscraper/
├── src/
│   ├── main.py                 # Entry point — orchestrates the full sync pipeline
│   ├── check_rollover.py       # Weekly season-rollover checker (rewrites stale config URLs)
│   ├── helpers/
│   │   ├── ascii_strings.py    # ASCII art banners used in log output
│   │   ├── config_loader.py    # Loads and validates calendar-configs/*.yaml files
│   │   ├── event_sync.py       # Pure functions: identity-based event matching and diffing
│   │   ├── html_parser.py      # BeautifulSoup HTML parsing (fallback source)
│   │   ├── models.py           # Game / ExistingEvent dataclasses
│   │   ├── rollover.py         # Season rollover detection for calendar configs
│   │   ├── site_builder.py     # Renders the public calendar-links page
│   │   └── sources.py          # Schedule sources: WordPress JSON API (primary) + HTML fallback
│   └── libs/
│       ├── google_cal_client.py # Google Calendar API client (OAuth2)
│       └── scraper_client.py    # HTTP client with retry — HTML and JSON fetching
├── calendar-configs/
│   ├── _config-template.yaml   # Template for adding new team calendars
│   └── config-*.yaml           # Active team configs (files ending .yaml.disable are ignored)
├── tests/                      # pytest unit tests (no network/credentials required)
├── pyproject.toml              # Project metadata and dependencies (uv)
└── .python-version             # Python version pin for uv and CI
```

- [ ] **Step 2: Update run commands and remove the manual-publicize note**

- Change both `uv run python main.py` occurrences to `uv run python src/main.py`.
- Change the credential-helper command to `uv run python src/libs/google_cal_client.py`.
- Delete the blockquote at the end of "Adding a new team calendar" ("After creating a new calendar, it must be manually set to **public**...") and replace it with:

```markdown
> New calendars are made public automatically on the next sync run and appear
> on the [published calendar page](https://hrmnfng.github.io/calendar-webscraper/).
```

- [ ] **Step 3: Document the two automations**

Add a section after "Adding a new team calendar":

```markdown
---

## Automation

- **Daily sync** (`execute-script.yml`, 6am AEST): syncs every active config to
  Google Calendar and, when fully successful, deploys the public
  [calendar links page](https://hrmnfng.github.io/calendar-webscraper/) to
  GitHub Pages. A failed run leaves the previously published page untouched.
- **Weekly season rollover** (`config-rollover.yml`, Monday 6am AEST): checks
  whether each team has a newer per-season page on the SSB site and, if so,
  opens (or refreshes) a single `chore/config-rollover` PR updating the
  affected `calendar-configs/*.yaml` URLs. Merge it to roll the calendar over
  to the new season; the calendar itself is reused, so subscribers keep working.
```

- [ ] **Step 4: Run the suite one last time and commit**

Run: `uv run pytest`
Expected: all PASS.

```bash
git add .github/README.md
git commit -m "docs: document src layout, rollover automation, and calendar page"
```

---

### Task 10: Post-merge verification checklist (user-assisted)

These need repo settings and run on GitHub, not locally:

- [ ] Flip the two one-time settings: Actions may create PRs; Pages source = "GitHub Actions".
- [ ] Merge the feature PR, then `workflow_dispatch` **Schedule to Calendar** — expect a green run and the page live at `https://hrmnfng.github.io/calendar-webscraper/`.
- [ ] `workflow_dispatch` **Config Season Rollover** — expect a real PR rolling LeTeam to the newest season post.
- [ ] Edit issue #13 to link the page URL, then close it.

---

## Post-plan follow-ups (not part of this plan)

- Old-season events accumulate in each calendar after rollover; `gameKey` identity makes cleanup possible later.
- The rollover PR does not auto-merge; that's deliberate — season rollovers deserve a human glance.

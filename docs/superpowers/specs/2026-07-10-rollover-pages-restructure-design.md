# Design: src restructure, weekly config-rollover PRs, and auto-published calendar page

**Date:** 2026-07-10
**Status:** Approved pending user review

## Goal

Three related improvements, implemented in this order:

1. **Repo restructure** — move application code under a conventional `src/` directory (mechanical, no behaviour change), so the new features land in the new layout.
2. **Weekly config rollover** — a Monday-morning GitHub Actions job that detects when a team has a newer per-season page on the SSB site and raises a single combined PR updating the affected `calendar-configs/*.yaml` files.
3. **Auto-published calendar page** — calendars are made public automatically via the Calendar ACL API (replacing the manual publicize step), and every successful daily sync run deploys a GitHub Pages site listing subscribe links (replacing manual sharing via pinned issue #13).

## Decisions already made (with the user)

- Rollover considers **any newer team post** — preseason and grading posts included, accepting ~2 PRs per season per team.
- **One combined PR** for all stale configs, not per-team PRs.
- **No third-party actions** — PR creation uses plain `git` + the preinstalled `gh` CLI with `GITHUB_TOKEN`. No composite action (single workflow, no reuse to justify it).
- Issue #13 is **retired**: the user edits it once to link to the Pages site and closes it. No issue-update automation.
- Calendars are **auto-publicized** via ACL insert; the page lists every synced calendar (no publicness filtering needed).
- **src layout: bare packages** — `helpers/` and `libs/` move under `src/` unchanged; imports stay `helpers.x` / `libs.y`; entry points live at `src/main.py` and `src/check_rollover.py`.

## Part 0: src restructure

Move, without renaming any module or symbol:

```
calendar-webscraper/
├── src/
│   ├── main.py
│   ├── check_rollover.py      (new, Part 1)
│   ├── helpers/               (config_loader, event_sync, html_parser, models,
│   │                           sources, ascii_strings + new rollover, site_builder)
│   └── libs/                  (google_cal_client, scraper_client)
├── tests/                     (stays at root)
├── calendar-configs/
└── pyproject.toml
```

Required follow-through:

- `pyproject.toml`: add `pythonpath = ["src"]` to `[tool.pytest.ini_options]` so tests resolve `helpers`/`libs` from `src/`.
- Run command becomes `uv run python src/main.py` — update `.github/workflows/execute-script.yml`, `.github/README.md`, and the credential-helper instruction (`uv run python src/libs/google_cal_client.py`).
- Verify `main.py`'s `CONFIG_DIR` and log-directory resolution are CWD-independent (anchor on `Path(__file__)` if they are not already); the smoke test is running from the repo root exactly as CI does.
- Pure move first, config fixes second, full suite green before anything else builds on top.

## Part 1: weekly config rollover

### Verified facts about season rollover (live API, 2026-07-10)

- Each season a team gets a **new team post**: `leteam-12` ("LeTeam 2025 s4") → `leteam-14` ("LeTeam 2026 s1"). The LeTeam config is stale today, so the first run has a real fixture.
- **Newest-by-date alone is a trap**: preseason/grading posts interleave ("LeTeam 2026 s1 preseason" = `leteam-13`) — but per the user's decision these DO count as newer versions.
- Slug numbering is not clean (`leteam-8-2`, one season used `the-leteam`), so slugs are never parsed for ordering — the post `date` field orders candidates.
- WP search is fuzzy: `search=LeTeam` also returns "The LeTeam 2025 s2". Candidates are filtered to titles starting with `"<base name> "` (HTML-unescaped, exact prefix).

### Detection logic — `helpers/rollover.py` (pure) + `src/check_rollover.py` (CLI)

Per active config (`.yaml.disable` files are never touched):

1. Slug from `config.url` → `GET /wp/v2/team?slug=<slug>` → current post. If not found: warn and skip this config.
2. Base name = current post title with the season suffix stripped: regex `\s+\d{4}\s+s\d.*$` removed from the unescaped title ("LeTeam 2025 s4" → "LeTeam"; suffix-eating `.*` also handles "… preseason" / "… grading" titles).
3. `GET /wp/v2/team?search=<base>&per_page=100` (paginated, same short-page/HTTP-400 termination as `helpers/sources.py`); keep posts whose unescaped title starts with `"<base> "`; pick newest by `date`.
4. If the newest post's slug differs from the current slug: rewrite the `url:` line of that config file in place (line-level replacement preserving the rest of the file verbatim).

The script prints a per-team summary (`LeTeam: leteam-12 → leteam-14 ("LeTeam 2026 s1")` / `unchanged` / `skipped: <reason>`), continues past per-config errors, and always exits 0 when it ran to completion — "changes exist" is detected by the workflow via `git diff`, not exit codes. It needs **no Google credentials** (public WP API only, via `ScraperClient.get_json` retries).

### Workflow — `.github/workflows/config-rollover.yml`

- Triggers: `schedule: cron '0 20 * * 0'` (Monday 6am AEST = Sunday 20:00 UTC) + `workflow_dispatch`.
- Permissions: `contents: write`, `pull-requests: write`.
- Steps: checkout → uv + Python (same pattern as execute-script.yml) → `uv run python src/check_rollover.py` → if `git diff --quiet -- calendar-configs` reports changes:
  - commit to a fixed branch `chore/config-rollover` and force-push (each run reflects current reality; history on that branch is disposable),
  - `gh pr create` with a body listing each team's old → new slug and post title; if a PR for the branch already exists, fall back to `gh pr edit` to refresh the body (re-runs update, never duplicate).
- **One-time repo setting:** Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests".

## Part 2: auto-publicize + GitHub Pages

### ACL auto-publicize — `libs/google_cal_client.py`

New method `ensure_calendar_public(calendar_id)`:

- `acl().list(calendarId)` → look for a rule with `scope.type == "default"` and `role == "reader"` (the exact grant the UI's "Make available to public" toggle creates; a `freeBusyReader`-only rule does not count — event details must be visible).
- If absent: `acl().insert(calendarId, body={"role": "reader", "scope": {"type": "default"}})` and log that the calendar was made public.
- Idempotent; called in `sync_calendar` immediately after `get_or_create_calendar`. A failure here counts as a sync failure for that calendar (loud, feeds the non-zero exit).

This replaces the manual "set to public in the UI" step; the README note saying the API cannot do this is removed (it is outdated — ACL insert with the `default` scope is exactly what the UI toggle does).

### Page build — `helpers/site_builder.py` (pure)

`build_site(entries) -> str` renders a static, dependency-free HTML page from `[(team_name, calendar_id), ...]`:

- Table per team with three links:
  - **Google Calendar**: `https://calendar.google.com/calendar/embed?src=<id>&ctz=Australia%2FSydney`
  - **Outlook**: `https://outlook.live.com/calendar/0/addfromweb?url=<ics-url>&name=<team>` (opens Outlook.com's subscribe dialog pre-filled)
  - **ICS (Apple / other)**: `https://calendar.google.com/calendar/ical/<id>/public/basic.ics`
- A one-line hint that the ICS URL should be **subscribed to**, not downloaded — subscribed feeds update automatically (Outlook/Apple poll on their own schedule, roughly hours to a day); a downloaded file is a static snapshot.
- Calendar IDs and team names are URL-encoded / HTML-escaped in the template.
- "Last updated" timestamp (Sydney time) in the footer.

`main()` collects `(config.name, calendar_id)` for each successfully synced calendar and, **only when there were no failures**, writes `site/index.html` (directory gitignored). On any failure the run exits 1 before writing, so a stale-but-correct page is never replaced by a partial one.

### Deploy — `execute-script.yml` changes

- Job 1 (`run-script`), after a successful script run: `actions/upload-pages-artifact` with `path: site`.
- New job 2 (`deploy-pages`): `needs: run-script`, `permissions: pages: write, id-token: write`, `environment: github-pages`, single `actions/deploy-pages` step. (Both are GitHub-official actions, satisfying the no-third-party constraint.)
- A failed sync run never reaches upload/deploy — the page stays at its last good state, which is the "on each successful run" requirement.
- **One-time repo settings:** Settings → Pages → Source: "GitHub Actions". Afterwards the user edits issue #13 once to link the page URL and closes it.

## Error handling summary

| Failure | Behaviour |
|---|---|
| WP API error for one config during rollover check | Warn, skip that config, continue with the rest |
| Current team slug not found on site | Warn and skip (config may be hand-rolled or site changed) |
| `ensure_calendar_public` API error | That calendar's sync fails loudly; run exits non-zero |
| Any calendar fails to sync | `site/index.html` not written; Pages deploy skipped; page stays at last good version |
| Rollover PR already open | Branch force-pushed, PR body refreshed via `gh pr edit` — no duplicates |

## Testing

- `tests/test_rollover.py` — base-name derivation, prefix filtering (excludes "The LeTeam"), newest-by-date selection (preseason counts), URL line rewrite preserves file contents, skip-on-missing-slug. Canned WP JSON + `MagicMock` client, same style as `test_sources.py`.
- `tests/test_site_builder.py` — pure HTML assertions: links contain encoded calendar IDs, teams appear, HTML-escaping of names.
- `tests/test_google_cal_client.py` — `ensure_calendar_public`: inserts when no default rule, no-ops when present (mocked service chain, same style as the pagination tests).
- Restructure has no new tests — the existing 132 passing unchanged is the acceptance bar.
- Workflows are exercised by manual `workflow_dispatch` runs after merge (rollover: LeTeam is genuinely stale today, so the first run should produce a real PR).

## Out of scope (deliberate)

- Auto-closing/reopening rollover PRs when a merge conflicts with manual config edits — force-push + review covers it.
- Deleting events from previous seasons when a config rolls over (same calendar keeps accumulating; identity keys make cleanup possible later).
- Custom domain / styling for the Pages site beyond a clean static table.
- Any Outlook integration beyond the subscribe deep link (no Microsoft Graph push).
- Auto-editing or auto-closing issue #13.

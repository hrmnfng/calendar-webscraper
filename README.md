# calendar-webscraper [![Schedule to Calendar](https://github.com/hrmnfng/calendar-webscraper/actions/workflows/execute-script.yml/badge.svg?branch=main)](https://github.com/hrmnfng/calendar-webscraper/actions/workflows/execute-script.yml?query=branch%3Amain)

A Python script that scrapes basketball schedule pages and syncs them into Google Calendar — creating new events, updating reschedules, and patching stale fields automatically.

Runs daily at 6am AEST via GitHub Actions, and can also be triggered manually or run locally.

## Adding the created calendars to your personal calendar

See the [pinned issue](https://github.com/hrmnfng/calendar-webscraper/issues/13) for links to the available calendars.

---

## Project structure

```
calendar-webscraper/
├── main.py                     # Entry point — orchestrates the full sync pipeline
├── helpers/
│   ├── ascii_strings.py        # ASCII art banners used in log output
│   ├── config_loader.py        # Loads and validates calendar-configs/*.yaml files
│   ├── event_sync.py           # Pure functions: event matching, patching, diffing
│   └── html_parser.py          # BeautifulSoup HTML parsing for SSB schedule pages
├── libs/
│   ├── google_cal_client.py    # Google Calendar API client (OAuth2)
│   └── scraper_client.py       # HTTP client — fetches HTML and delegates to HTMLHelper
├── calendar-configs/
│   ├── _config-template.yaml   # Template for adding new team calendars
│   └── config-*.yaml           # Active team configs (files ending .yaml.disable are ignored)
├── tests/                      # pytest unit tests (no network/credentials required)
├── pyproject.toml              # Project metadata and dependencies (uv)
└── .python-version             # Python version pin for uv and CI
```

---

## Running locally

### Prerequisites

- [pyenv-win](https://github.com/pyenv-win/pyenv-win) (or any Python 3.12+ install)
- [uv](https://docs.astral.sh/uv/) — install with `pip install uv` or via the [standalone installer](https://docs.astral.sh/uv/getting-started/installation/)

### Setup

```shell
# Install dependencies (creates .venv automatically)
uv sync

# Run the script
uv run python main.py
```

### Environment variables

The script loads a `.env` file from the project root automatically if one is present (values already set in the shell environment take precedence). Copy the example below to `.env` and fill in your values:

```dotenv
GCAL_CLIENT_ID=
GCAL_CLIENT_SECRET=
GCAL_REFRESH_TOKEN=
LOG_LEVEL=INFO
```

| Variable             | Description                                                                         |
| -------------------- | ----------------------------------------------------------------------------------- |
| `GCAL_CLIENT_ID`     | OAuth2 client ID from Google Cloud Console                                          |
| `GCAL_CLIENT_SECRET` | OAuth2 client secret                                                                |
| `GCAL_REFRESH_TOKEN` | Long-lived refresh token (see [Generating credentials](#generating-credentials))    |
| `LOG_LEVEL`          | Log verbosity — `MAJOR` (milestones only), `INFO`, or `DEBUG`. Defaults to `INFO`.  |

<details>
<summary>Generating credentials</summary>

1. Clone this repository.
2. Create (or reuse) a project in the [Google Cloud Console](https://console.cloud.google.com/).
3. Navigate to **APIs & Services → Credentials** and click **CREATE CREDENTIALS → OAuth Client ID**.
   - Application type: **Desktop app**
4. Download the JSON file, rename it to `credentials.json`, and place it in the repository root.
5. Run the auth helper to generate your refresh token:
   ```shell
   uv run python libs/google_cal_client.py
   ```
6. Copy the printed `client_id`, `client_secret`, and `refresh_token` values into your environment variables.
7. Delete `credentials.json` — it is no longer needed.

> **Note:** Refresh tokens for projects with publishing status `Testing` expire after 7 days.

</details>

> These credentials grant access to the Google account associated with your Cloud Console project — keep them secret.

---

## Running tests

```shell
uv run pytest
```

To include a coverage report:

```shell
uv run pytest --cov
```

---

## Adding a new team calendar

1. Copy `calendar-configs/_config-template.yaml` to `calendar-configs/config-<your-team>.yaml`.
2. Fill in the three fields:

```yaml
name: My Team Name        # Must be unique across all your calendars
url: https://sydneysocialbasketball.com.au/team/<slug>/
color_id: 5               # Integer 1–11 (see colors.yaml for reference)
```

3. To temporarily disable a calendar without deleting it, rename the file to end in `.yaml.disable`.

> After creating a new calendar, it must be manually set to **public** in Google Calendar before sharing. This cannot be done via the API.

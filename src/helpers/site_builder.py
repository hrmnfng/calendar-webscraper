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

"""
Renders the public GitHub Pages site listing calendar subscribe links.

Pure function: no I/O. main.py writes the result to site/index.html after a
fully successful sync run, and the workflow deploys that directory to Pages.
"""

from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import quote

# Single embedded stylesheet keeps the page a self-contained HTML file.
# Colours live in custom properties so the dark scheme is just a variable swap.
_STYLE = """\
    :root {
      --bg: #f4f5f7;
      --surface: #ffffff;
      --text: #1a1d21;
      --muted: #5c636e;
      --accent: #2563eb;
      --accent-contrast: #ffffff;
      --border: #e2e5ea;
      --shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
      --shadow-hover: 0 4px 14px rgba(15, 23, 42, 0.14);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #111418;
        --surface: #1b2027;
        --text: #e7eaee;
        --muted: #9aa3af;
        --accent: #60a5fa;
        --accent-contrast: #0b1220;
        --border: #2a303a;
        --shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
        --shadow-hover: 0 4px 14px rgba(0, 0, 0, 0.5);
      }
    }
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      max-width: 44rem;
      margin: 0 auto;
      padding: 2.5rem 1.25rem 3rem;
      line-height: 1.55;
    }
    h1 {
      font-size: 1.75rem;
      letter-spacing: -0.02em;
      margin: 0 0 0.35rem;
    }
    .subtitle { color: var(--muted); margin: 0 0 1.75rem; }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      box-shadow: var(--shadow);
      padding: 1.1rem 1.25rem 1.25rem;
      margin: 1rem 0;
      transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .card:hover { transform: translateY(-2px); box-shadow: var(--shadow-hover); }
    .card h2 { margin: 0 0 0.75rem; font-size: 1.15rem; }
    .links { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    .pill {
      display: inline-block;
      padding: 0.4rem 0.95rem;
      border: 1px solid var(--accent);
      border-radius: 999px;
      color: var(--accent);
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 500;
      transition: background 0.12s ease, color 0.12s ease;
    }
    .pill:hover { background: var(--accent); color: var(--accent-contrast); }
    .tip {
      background: var(--surface);
      border: 1px solid var(--border);
      border-left: 3px solid var(--accent);
      border-radius: 0.5rem;
      padding: 0.8rem 1rem;
      color: var(--muted);
      font-size: 0.9rem;
      margin-top: 1.75rem;
    }
    footer { margin-top: 2rem; color: var(--muted); font-size: 0.85rem; }
    footer a { color: var(--muted); }"""


def _card(name: str, calendar_id: str) -> str:
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
        '  <article class="card">\n'
        f"    <h2>{safe_name}</h2>\n"
        '    <div class="links">\n'
        f'      <a class="pill" href="{html.escape(google_url)}">Google Calendar</a>\n'
        f'      <a class="pill" href="{html.escape(outlook_url)}">Outlook</a>\n'
        f'      <a class="pill" href="{ics_url}">ICS (Apple / other)</a>\n'
        "    </div>\n"
        "  </article>"
    )


def build_site(entries: list[tuple[str, str]], updated: datetime) -> str:
    """
    Render the full HTML page for ``[(team_name, calendar_id), ...]``.

    ``updated`` is injected (not read from the clock) so rendering stays pure
    and testable; the caller passes Sydney "now".
    """
    cards = "\n".join(_card(name, calendar_id) for name, calendar_id in entries)
    timestamp = updated.strftime("%Y-%m-%d %H:%M %Z")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>SSB Team Calendars</title>
  <style>
{_STYLE}
  </style>
</head>
<body>
  <h1>SSB Team Calendars</h1>
  <p class="subtitle">Public Google Calendars for each team's schedule, updated
     automatically every morning. Pick your calendar app's link below.</p>
{cards}
  <p class="tip"><strong>Tip:</strong> <strong>subscribe</strong> to the ICS link
     (Outlook: "Add calendar &rarr; Subscribe from web"; Apple: "File &rarr; New
     Calendar Subscription") rather than downloading it &mdash; subscribed
     calendars update automatically, a downloaded file is a one-off snapshot.</p>
  <footer>Last updated {timestamp} &middot;
    <a href="https://github.com/hrmnfng/calendar-webscraper">calendar-webscraper</a>
  </footer>
</body>
</html>
"""

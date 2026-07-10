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
        assert "2026-07-10 06:00" in page

    def test_ampersands_in_hrefs_are_escaped(self):
        page = build_site([("LeTeam", CAL_ID)], updated=UPDATED)
        assert "&ctz=" not in page
        assert "&amp;ctz=" in page

    def test_subscribe_hint_present(self):
        page = build_site([], updated=UPDATED)
        assert "subscribe" in page.lower()

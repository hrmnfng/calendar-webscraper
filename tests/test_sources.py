"""
Unit tests for helpers.sources — key normalization, WP API source,
HTML source wrapper, and fallback behaviour.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from helpers.config_loader import CalendarConfig
from helpers.models import Game, ScrapeError
from helpers.sources import SOURCES, fetch_games, fetch_games_ssb_api, fetch_games_ssb_html, normalize_round_key, round_label_from_slug

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

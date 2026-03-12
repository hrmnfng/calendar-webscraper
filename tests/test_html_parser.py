"""
Unit tests for helpers.html_parser.HTMLHelper.

All tests are pure (no network, no filesystem) — BeautifulSoup is invoked on
inline HTML fixture strings.
"""

from __future__ import annotations

from datetime import datetime
from textwrap import dedent

import pytest

from helpers.html_parser import HTMLHelper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_game_html(
    round_num: str = "5",
    opponent: str = "The Rivals",
    date: str = "10/08/2025",
    time: str = "10:00AM",
    court: str = "Court 3",
    score_url: str = "https://example.com/score/123",
) -> str:
    """Return a minimal SSB-style HTML snippet for a single game."""
    return dedent(f"""
        <div class="grid">
            <div><h5>Round</h5>Round {round_num}</div>
            <div><h5>Opponent</h5><a href="#">{opponent}</a></div>
            <div><h5>Date</h5>{date}</div>
            <div><h5>Time</h5>{time}</div>
            <div><h5>Court</h5>{court}</div>
            <div><h5>Score</h5><a href="{score_url}">View</a></div>
        </div>
    """)


def _make_page_html(*game_snippets: str) -> str:
    """Wrap one or more game snippets in a minimal HTML page."""
    body = "\n".join(game_snippets)
    return f"<html><body>{body}</body></html>"


# ---------------------------------------------------------------------------
# parse_html_content — routing
# ---------------------------------------------------------------------------

class TestParseHtmlContentRouting:

    def test_ssb_routes_to_ssb_parser(self):
        html = _make_page_html(_make_game_html())
        result = HTMLHelper.parse_html_content(html, parse_type="ssb")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_unknown_parse_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown parse_type"):
            HTMLHelper.parse_html_content("<html/>", parse_type="unknown")

    def test_custom_parse_type_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            HTMLHelper.parse_html_content("<html/>", parse_type="custom")


# ---------------------------------------------------------------------------
# _parse_ssb_content — single game
# ---------------------------------------------------------------------------

class TestParseSsbContentSingleGame:

    def setup_method(self):
        html = _make_page_html(
            _make_game_html(
                round_num="7",
                opponent="Space Jam FC",
                date="15/09/2025",
                time="08:30PM",
                court="Court 1",
                score_url="https://ssb.com/score/42",
            )
        )
        self.result = HTMLHelper._parse_ssb_content(html)

    def test_returns_one_game(self):
        assert len(self.result) == 1

    def test_round_field_includes_round_number_and_opponent(self):
        assert self.result[0]["round"] == "Round 7: Space Jam FC"

    def test_start_datetime_parsed_correctly(self):
        expected = datetime(2025, 9, 15, 20, 30)
        assert self.result[0]["start"] == expected

    def test_end_is_one_hour_after_start(self):
        assert self.result[0]["end"] == self.result[0]["start"].replace(hour=21, minute=30)

    def test_location_extracted(self):
        assert self.result[0]["location"] == "Court 1"

    def test_details_url_extracted(self):
        assert self.result[0]["details_url"] == "https://ssb.com/score/42"


# ---------------------------------------------------------------------------
# _parse_ssb_content — multiple games
# ---------------------------------------------------------------------------

class TestParseSsbContentMultipleGames:

    def test_returns_correct_count(self):
        html = _make_page_html(
            _make_game_html(round_num="1", date="01/08/2025"),
            _make_game_html(round_num="2", date="08/08/2025"),
            _make_game_html(round_num="3", date="15/08/2025"),
        )
        result = HTMLHelper._parse_ssb_content(html)
        assert len(result) == 3

    def test_games_are_in_document_order(self):
        html = _make_page_html(
            _make_game_html(round_num="1", date="01/08/2025"),
            _make_game_html(round_num="2", date="08/08/2025"),
        )
        result = HTMLHelper._parse_ssb_content(html)
        assert result[0]["start"] < result[1]["start"]


# ---------------------------------------------------------------------------
# _parse_ssb_content — AM/PM time parsing
# ---------------------------------------------------------------------------

class TestParseSsbContentTimeParsing:

    @pytest.mark.parametrize("time_str, expected_hour", [
        ("08:00AM", 8),
        ("12:00PM", 12),
        ("06:30PM", 18),
        ("11:59PM", 23),
        ("12:00AM", 0),
    ])
    def test_time_parses_correctly(self, time_str, expected_hour):
        html = _make_page_html(_make_game_html(time=time_str))
        result = HTMLHelper._parse_ssb_content(html)
        assert result[0]["start"].hour == expected_hour


# ---------------------------------------------------------------------------
# _parse_ssb_content — empty page
# ---------------------------------------------------------------------------

class TestParseSsbContentEmptyPage:

    def test_no_grid_divs_returns_empty_list(self):
        html = "<html><body><p>No games scheduled.</p></body></html>"
        result = HTMLHelper._parse_ssb_content(html)
        assert result == []

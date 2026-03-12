"""
Unit tests for helpers.html_parser.HTMLHelper and the private parsing helpers.

All tests are pure (no network, no filesystem). BeautifulSoup is invoked on
inline HTML fixture strings to keep tests fast and self-contained.
"""

from __future__ import annotations

from datetime import datetime
from textwrap import dedent

import pytest

from helpers.html_parser import (
    HTMLHelper,
    _extract_label_href,
    _extract_label_link,
    _extract_label_sibling,
    _parse_ssb_game_element,
)
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# HTML fixture helpers
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


def _make_page(*game_snippets: str) -> str:
    return f"<html><body>{''.join(game_snippets)}</body></html>"


def _game_element(html: str):
    """Return the first .grid element from an HTML string as a BS4 Tag."""
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("div", class_="grid")


# ---------------------------------------------------------------------------
# parse_html_content — routing
# ---------------------------------------------------------------------------

class TestParseHtmlContentRouting:

    def test_ssb_routes_correctly(self):
        result = HTMLHelper.parse_html_content(_make_page(_make_game_html()), "ssb")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown parse_type"):
            HTMLHelper.parse_html_content("<html/>", "unknown")

    def test_custom_type_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            HTMLHelper.parse_html_content("<html/>", "custom")


# ---------------------------------------------------------------------------
# _parse_ssb_content — happy path
# ---------------------------------------------------------------------------

class TestParseSsbContentHappyPath:

    def setup_method(self):
        html = _make_page(_make_game_html(
            round_num="7", opponent="Space Jam FC",
            date="15/09/2025", time="08:30PM",
            court="Court 1", score_url="https://ssb.com/score/42",
        ))
        self.result = HTMLHelper._parse_ssb_content(html)

    def test_returns_one_game(self):
        assert len(self.result) == 1

    def test_round_field(self):
        assert self.result[0]["round"] == "Round 7: Space Jam FC"

    def test_start_datetime(self):
        assert self.result[0]["start"] == datetime(2025, 9, 15, 20, 30)

    def test_end_is_one_hour_after_start(self):
        assert self.result[0]["end"] == datetime(2025, 9, 15, 21, 30)

    def test_location(self):
        assert self.result[0]["location"] == "Court 1"

    def test_details_url(self):
        assert self.result[0]["details_url"] == "https://ssb.com/score/42"

    def test_multiple_games_returns_correct_count(self):
        html = _make_page(
            _make_game_html(round_num="1", date="01/08/2025"),
            _make_game_html(round_num="2", date="08/08/2025"),
            _make_game_html(round_num="3", date="15/08/2025"),
        )
        assert len(HTMLHelper._parse_ssb_content(html)) == 3

    def test_games_in_document_order(self):
        html = _make_page(
            _make_game_html(round_num="1", date="01/08/2025"),
            _make_game_html(round_num="2", date="08/08/2025"),
        )
        result = HTMLHelper._parse_ssb_content(html)
        assert result[0]["start"] < result[1]["start"]


# ---------------------------------------------------------------------------
# _parse_ssb_content — AM/PM time parsing
# ---------------------------------------------------------------------------

class TestParseSsbTimeParsing:

    @pytest.mark.parametrize("time_str, expected_hour", [
        ("08:00AM", 8),
        ("12:00PM", 12),
        ("06:30PM", 18),
        ("11:59PM", 23),
        ("12:00AM", 0),
    ])
    def test_time_parses_correctly(self, time_str, expected_hour):
        html = _make_page(_make_game_html(time=time_str))
        result = HTMLHelper._parse_ssb_content(html)
        assert result[0]["start"].hour == expected_hour


# ---------------------------------------------------------------------------
# _parse_ssb_content — robustness: zero games / missing fields / bad datetime
# ---------------------------------------------------------------------------

class TestParseSsbRobustness:

    def test_empty_page_returns_empty_list(self):
        result = HTMLHelper._parse_ssb_content("<html><body><p>No games.</p></body></html>")
        assert result == []

    def test_empty_page_emits_warning(self, loguru_messages):
        HTMLHelper._parse_ssb_content("<html><body></body></html>")
        assert any("No game elements found" in m for m in loguru_messages)

    def test_missing_field_skips_game_and_warns(self, loguru_messages):
        """A game element missing the 'Score' label should be skipped with a warning."""
        html = dedent("""
            <html><body>
            <div class="grid">
                <div><h5>Round</h5>Round 1</div>
                <div><h5>Opponent</h5><a href="#">Team B</a></div>
                <div><h5>Date</h5>10/08/2025</div>
                <div><h5>Time</h5>10:00AM</div>
                <div><h5>Court</h5>Court 1</div>
                <!-- Score label deliberately omitted -->
            </div>
            </body></html>
        """)
        result = HTMLHelper._parse_ssb_content(html)
        assert result == []
        assert any("missing field" in m for m in loguru_messages)

    def test_missing_field_only_skips_affected_game(self, caplog):
        """Only the broken element is skipped; valid sibling elements still parse."""
        import logging
        broken = dedent("""
            <div class="grid">
                <div><h5>Round</h5>Round 1</div>
                <div><h5>Opponent</h5><a href="#">Bad Team</a></div>
                <div><h5>Date</h5>10/08/2025</div>
                <div><h5>Time</h5>10:00AM</div>
                <div><h5>Court</h5>Court 1</div>
                <!-- no Score -->
            </div>
        """)
        good = _make_game_html(round_num="2", date="17/08/2025")
        html = _make_page(broken, good)
        with caplog.at_level(logging.WARNING):
            result = HTMLHelper._parse_ssb_content(html)
        assert len(result) == 1
        assert result[0]["round"] == "Round 2: The Rivals"

    def test_unparseable_datetime_skips_game_and_warns(self, loguru_messages):
        """A game with 'TBC' as its time value should be skipped with a warning."""
        html = _make_page(_make_game_html(time="TBC"))
        result = HTMLHelper._parse_ssb_content(html)
        assert result == []
        assert any("could not parse datetime" in m for m in loguru_messages)

    def test_all_invalid_games_emits_structural_warning(self, loguru_messages):
        """When ALL games fail to parse, a summary warning is emitted."""
        html = _make_page(
            _make_game_html(time="TBC"),
            _make_game_html(time="TBC"),
        )
        result = HTMLHelper._parse_ssb_content(html)
        assert result == []
        assert any(
            "could not parse any" in m or "were skipped" in m
            for m in loguru_messages
        )

    def test_partial_failure_emits_warning_with_counts(self, loguru_messages):
        """When some games fail and some succeed, a partial-failure warning is emitted."""
        html = _make_page(
            _make_game_html(time="TBC"),          # bad
            _make_game_html(date="10/08/2025"),   # good
        )
        result = HTMLHelper._parse_ssb_content(html)
        assert len(result) == 1
        assert any("were skipped" in m for m in loguru_messages)

    def test_opponent_name_containing_label_word_does_not_false_match(self):
        """
        An opponent named 'Round Hill FC' must not cause the 'Round' label
        extraction to return their name instead of the actual round number.
        """
        html = _make_page(_make_game_html(round_num="3", opponent="Round Hill FC"))
        result = HTMLHelper._parse_ssb_content(html)
        assert len(result) == 1
        assert result[0]["round"] == "Round 3: Round Hill FC"
        # The round prefix must contain the actual round number, not the opponent name
        assert result[0]["round"].startswith("Round 3:")


# ---------------------------------------------------------------------------
# Low-level extraction helpers
# ---------------------------------------------------------------------------

class TestExtractHelpers:

    def _element(self, html: str):
        return BeautifulSoup(html, "html.parser")

    def test_extract_label_sibling_returns_value(self):
        el = self._element("<div><h5>Date</h5>10/08/2025</div>")
        assert _extract_label_sibling(el, "Date") == "10/08/2025"

    def test_extract_label_sibling_returns_none_when_label_missing(self):
        el = self._element("<div><h5>Other</h5>value</div>")
        assert _extract_label_sibling(el, "Date") is None

    def test_extract_label_link_returns_text(self):
        el = self._element('<div><h5>Opponent</h5><a href="#">Team B</a></div>')
        assert _extract_label_link(el, "Opponent") == "Team B"

    def test_extract_label_link_returns_none_when_missing(self):
        el = self._element("<div><h5>Other</h5>value</div>")
        assert _extract_label_link(el, "Opponent") is None

    def test_extract_label_href_returns_url(self):
        el = self._element('<div><h5>Score</h5><a href="https://ssb.com/1">View</a></div>')
        assert _extract_label_href(el, "Score") == "https://ssb.com/1"

    def test_extract_label_href_returns_none_when_missing(self):
        el = self._element("<div><h5>Other</h5>value</div>")
        assert _extract_label_href(el, "Score") is None

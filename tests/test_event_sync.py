"""
Unit tests for helpers.event_sync — all pure functions, no I/O.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from helpers.event_sync import (
    build_field_patch,
    build_reschedule_patch,
    filter_events_by_schedule,
    match_game_to_event,
    parse_existing_events,
)
from helpers.models import ExistingEvent, Game

SCHEDULE_URL = "https://ssb.com/team/test/"


def _gcal_event(event_id: str, start_dt: str, schedule_url: str = SCHEDULE_URL) -> dict:
    return {
        "id": event_id,
        "start": {"dateTime": f"{start_dt}+10:00"},
        "extendedProperties": {"private": {"schedule": schedule_url}},
    }


class TestFilterEventsBySchedule:
    def test_returns_matching_events(self):
        e1 = _gcal_event("id1", "2025-08-10T10:00:00", SCHEDULE_URL)
        e2 = _gcal_event("id2", "2025-08-17T10:00:00", "https://other.com/")
        result = filter_events_by_schedule([e1, e2], SCHEDULE_URL)
        assert len(result) == 1 and result[0]["id"] == "id1"

    def test_empty_list_returns_empty(self):
        assert filter_events_by_schedule([], SCHEDULE_URL) == []

    def test_no_matching_schedule_returns_empty(self):
        e1 = _gcal_event("id1", "2025-08-10T10:00:00", "https://other.com/")
        assert filter_events_by_schedule([e1], SCHEDULE_URL) == []


# ---------------------------------------------------------------------------
# Identity-based sync functions
# ---------------------------------------------------------------------------

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

    def test_legacy_same_sydney_date_matches_across_utc_offset(self):
        """A keyless event returned by GCal in UTC must still match by Sydney date."""
        game = _game()  # 2026-01-15 21:10 Sydney
        # 2026-01-14 20:00 UTC == 2026-01-15 07:00 Sydney: same Sydney date as
        # the game, but a different UTC calendar date.
        events = [{
            "id": "e1",
            "start": {"dateTime": "2026-01-14T20:00:00Z"},
            "extendedProperties": {"private": {}},
        }]
        legacy = parse_existing_events(events)
        action, matched = match_game_to_event(game, legacy)
        assert action == "reschedule"
        assert matched.id == "e1"


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

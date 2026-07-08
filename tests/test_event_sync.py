"""
Unit tests for helpers.event_sync — all pure functions, no I/O.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from helpers.event_sync import (
    apply_field_patches,
    build_field_patch,
    build_patch_payload,
    build_reschedule_patch,
    determine_sync_action,
    filter_events_by_schedule,
    format_game_times,
    get_game_details,
    match_game_to_event,
    parse_existing_events,
    simplify_existing_events,
)
from helpers.models import ExistingEvent, Game

SCHEDULE_URL = "https://ssb.com/team/test/"


def _make_game(
    round_name: str = "Round 1: Opponents",
    start: datetime = datetime(2025, 8, 10, 10, 0),
    location: str = "Court 3",
    details_url: str = "https://ssb.com/score/1",
) -> dict:
    return {
        "round": round_name,
        "start": start,
        "end": start + timedelta(hours=1),
        "location": location,
        "details_url": details_url,
    }


def _gcal_event(event_id: str, start_dt: str, schedule_url: str = SCHEDULE_URL) -> dict:
    return {
        "id": event_id,
        "start": {"dateTime": f"{start_dt}+10:00"},
        "extendedProperties": {"private": {"schedule": schedule_url}},
    }


class TestFormatGameTimes:
    def test_returns_iso_strings(self):
        tip_off, finish = format_game_times(_make_game(start=datetime(2025, 8, 10, 10, 0)))
        assert tip_off == "2025-08-10T10:00:00"
        assert finish == "2025-08-10T11:00:00"


class TestGetGameDetails:
    def test_unpacks_all_fields(self):
        game = _make_game(
            round_name="Round 5: Rivals",
            start=datetime(2025, 8, 10, 10, 0),
            location="Court 1",
            details_url="https://ssb.com/score/99",
        )
        round_name, tip_off, finish, venue, details_url = get_game_details(game)
        assert round_name == "Round 5: Rivals"
        assert tip_off == "2025-08-10T10:00:00"
        assert finish == "2025-08-10T11:00:00"
        assert venue == "Court 1"
        assert details_url == "https://ssb.com/score/99"


class TestSimplifyExistingEvents:
    def test_strips_utc_offset(self):
        result = simplify_existing_events([_gcal_event("id1", "2025-08-10T10:00:00")])
        assert "2025-08-10T10:00:00" in result

    def test_preserves_id_and_url(self):
        result = simplify_existing_events([_gcal_event("abc", "2025-08-10T10:00:00")])
        assert result["2025-08-10T10:00:00"]["id"] == "abc"
        assert result["2025-08-10T10:00:00"]["url"] == SCHEDULE_URL

    def test_empty_returns_empty_dict(self):
        assert simplify_existing_events([]) == {}


class TestFilterEventsBySchedule:
    def test_returns_matching_events(self):
        e1 = _gcal_event("id1", "2025-08-10T10:00:00", SCHEDULE_URL)
        e2 = _gcal_event("id2", "2025-08-17T10:00:00", "https://other.com/")
        result = filter_events_by_schedule({"items": [e1, e2]}, SCHEDULE_URL)
        assert len(result) == 1 and result[0]["id"] == "id1"

    def test_empty_items_returns_empty(self):
        assert filter_events_by_schedule({"items": []}, SCHEDULE_URL) == []

    def test_missing_items_key_returns_empty(self):
        assert filter_events_by_schedule({}, SCHEDULE_URL) == []


class TestBuildPatchPayload:
    def test_basic_fields(self):
        payload = build_patch_payload("R1", "2025-08-10T10:00:00", "2025-08-10T11:00:00", 5)
        assert payload["summary"] == "R1"
        assert payload["colorId"] == 5

    def test_description_included_when_provided(self):
        payload = build_patch_payload("R1", "2025-08-10T10:00:00", "2025-08-10T11:00:00", 1, "https://url")
        assert payload["description"] == "https://url"

    def test_description_omitted_when_empty(self):
        payload = build_patch_payload("R1", "2025-08-10T10:00:00", "2025-08-10T11:00:00", 1)
        assert "description" not in payload


class TestDetermineSyncAction:
    def _events(self, time: str, url: str = SCHEDULE_URL) -> dict:
        return {time: {"url": url, "id": "evt-1"}}

    def test_exact_match(self):
        action, eid = determine_sync_action("2025-08-10T10:00:00", SCHEDULE_URL, self._events("2025-08-10T10:00:00"))
        assert action == "exact" and eid == "evt-1"

    def test_exact_match_wrong_url_does_not_match(self):
        events = self._events("2025-08-10T10:00:00", "https://other.com/")
        action, _ = determine_sync_action("2025-08-10T10:00:00", SCHEDULE_URL, events)
        assert action != "exact"

    def test_same_date_different_time_is_reschedule(self):
        action, eid = determine_sync_action("2025-08-10T20:00:00", SCHEDULE_URL, self._events("2025-08-10T10:00:00"))
        assert action == "reschedule" and eid == "evt-1"

    def test_no_match_is_create(self):
        action, eid = determine_sync_action("2025-08-10T10:00:00", SCHEDULE_URL, self._events("2025-08-17T10:00:00"))
        assert action == "create" and eid == ""

    def test_empty_events_is_create(self):
        action, eid = determine_sync_action("2025-08-10T10:00:00", SCHEDULE_URL, {})
        assert action == "create" and eid == ""

    def test_same_date_different_url_is_create(self):
        events = {"2025-08-10T10:00:00": {"url": "https://other.com/", "id": "x"}}
        action, _ = determine_sync_action("2025-08-10T20:00:00", SCHEDULE_URL, events)
        assert action == "create"


class TestApplyFieldPatches:
    def _call(self, gclient, event_details: dict, **overrides):
        defaults = dict(
            calendar_id="cal-1", event_id="evt-1",
            round_name="Round 1: Team", color_id=5,
            details_url="https://ssb.com/score/1", venue="Court 3",
        )
        defaults.update(overrides)
        apply_field_patches(gclient=gclient, event_details=event_details, **defaults)

    def test_no_patches_when_all_match(self):
        gclient = MagicMock()
        self._call(gclient, {
            "summary": "Round 1: Team", "colorId": "5",
            "description": "https://ssb.com/score/1", "location": "Court 3",
        })
        gclient.patch_event.assert_not_called()

    def test_patches_stale_summary(self):
        gclient = MagicMock()
        self._call(gclient, {"summary": "Old", "colorId": "5", "description": "https://ssb.com/score/1", "location": "Court 3"})
        gclient.patch_event.assert_any_call(calendar_id="cal-1", event_id="evt-1", patched_fields={"summary": "Round 1: Team"})

    def test_patches_stale_color(self):
        gclient = MagicMock()
        self._call(gclient, {"summary": "Round 1: Team", "colorId": "99", "description": "https://ssb.com/score/1", "location": "Court 3"})
        gclient.patch_event.assert_any_call(calendar_id="cal-1", event_id="evt-1", patched_fields={"colorId": 5})

    def test_patches_missing_description(self):
        gclient = MagicMock()
        self._call(gclient, {"summary": "Round 1: Team", "colorId": "5", "location": "Court 3"})
        gclient.patch_event.assert_any_call(calendar_id="cal-1", event_id="evt-1", patched_fields={"description": "https://ssb.com/score/1"})

    def test_patches_stale_location(self):
        gclient = MagicMock()
        self._call(gclient, {"summary": "Round 1: Team", "colorId": "5", "description": "https://ssb.com/score/1", "location": "Old Court"})
        gclient.patch_event.assert_any_call(calendar_id="cal-1", event_id="evt-1", patched_fields={"location": "Court 3"})

    def test_patches_all_stale_fields(self):
        gclient = MagicMock()
        self._call(gclient, {"summary": "Old", "colorId": "1", "description": "https://old.com/", "location": "Old Court"})
        assert gclient.patch_event.call_count == 4


# ---------------------------------------------------------------------------
# Identity-based sync functions (Task 7)
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

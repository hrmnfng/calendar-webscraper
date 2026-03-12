"""
Unit tests for helpers.event_sync.

All functions under test are pure (no I/O, no API calls), so no mocking is
needed beyond constructing the input dicts.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, call

import pytest

from helpers.event_sync import (
    apply_field_patches,
    build_patch_payload,
    determine_sync_action,
    filter_events_by_schedule,
    format_game_times,
    get_game_details,
    simplify_existing_events,
)

SCHEDULE_URL = "https://ssb.com/team/test-team/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(
    round_name: str = "Round 1: Opponents",
    start: datetime = datetime(2025, 8, 10, 10, 0),
    location: str = "Court 3",
    details_url: str = "https://ssb.com/score/1",
) -> dict:
    from datetime import timedelta
    return {
        "round": round_name,
        "start": start,
        "end": start + timedelta(hours=1),
        "location": location,
        "details_url": details_url,
    }


def _make_gcal_event(
    event_id: str,
    start_dt: str,
    schedule_url: str = SCHEDULE_URL,
) -> dict:
    """Minimal GCal event dict with the fields used by the sync helpers."""
    return {
        "id": event_id,
        "start": {"dateTime": f"{start_dt}+10:00"},
        "extendedProperties": {"private": {"schedule": schedule_url}},
    }


# ---------------------------------------------------------------------------
# format_game_times
# ---------------------------------------------------------------------------

class TestFormatGameTimes:

    def test_returns_iso_strings(self):
        game = _make_game(start=datetime(2025, 8, 10, 10, 0))
        tip_off, finish = format_game_times(game)
        assert tip_off == "2025-08-10T10:00:00"
        assert finish == "2025-08-10T11:00:00"

    def test_tip_off_and_finish_differ_by_one_hour(self):
        game = _make_game(start=datetime(2025, 9, 1, 20, 30))
        tip_off, finish = format_game_times(game)
        assert tip_off == "2025-09-01T20:30:00"
        assert finish == "2025-09-01T21:30:00"


# ---------------------------------------------------------------------------
# get_game_details
# ---------------------------------------------------------------------------

class TestGetGameDetails:

    def test_unpacks_all_fields(self):
        game = _make_game(
            round_name="Round 5: The Rivals",
            start=datetime(2025, 8, 10, 10, 0),
            location="Court 1",
            details_url="https://ssb.com/score/99",
        )
        round_name, tip_off, finish, venue, details_url = get_game_details(game)

        assert round_name == "Round 5: The Rivals"
        assert tip_off == "2025-08-10T10:00:00"
        assert finish == "2025-08-10T11:00:00"
        assert venue == "Court 1"
        assert details_url == "https://ssb.com/score/99"


# ---------------------------------------------------------------------------
# simplify_existing_events
# ---------------------------------------------------------------------------

class TestSimplifyExistingEvents:

    def test_strips_utc_offset_from_datetime(self):
        events = [_make_gcal_event("id1", "2025-08-10T10:00:00")]
        result = simplify_existing_events(events)
        assert "2025-08-10T10:00:00" in result

    def test_preserves_event_id(self):
        events = [_make_gcal_event("abc123", "2025-08-10T10:00:00")]
        result = simplify_existing_events(events)
        assert result["2025-08-10T10:00:00"]["id"] == "abc123"

    def test_preserves_schedule_url(self):
        events = [_make_gcal_event("id1", "2025-08-10T10:00:00", schedule_url="https://example.com/")]
        result = simplify_existing_events(events)
        assert result["2025-08-10T10:00:00"]["url"] == "https://example.com/"

    def test_multiple_events(self):
        events = [
            _make_gcal_event("id1", "2025-08-10T10:00:00"),
            _make_gcal_event("id2", "2025-08-17T10:00:00"),
        ]
        result = simplify_existing_events(events)
        assert len(result) == 2

    def test_empty_list_returns_empty_dict(self):
        assert simplify_existing_events([]) == {}


# ---------------------------------------------------------------------------
# filter_events_by_schedule
# ---------------------------------------------------------------------------

class TestFilterEventsBySchedule:

    def _make_events_list(self, events: list[dict]) -> dict:
        return {"items": events}

    def test_returns_matching_events(self):
        e1 = _make_gcal_event("id1", "2025-08-10T10:00:00", schedule_url=SCHEDULE_URL)
        e2 = _make_gcal_event("id2", "2025-08-17T10:00:00", schedule_url="https://other.com/")
        result = filter_events_by_schedule(self._make_events_list([e1, e2]), SCHEDULE_URL)
        assert len(result) == 1
        assert result[0]["id"] == "id1"

    def test_returns_empty_list_when_no_match(self):
        e1 = _make_gcal_event("id1", "2025-08-10T10:00:00", schedule_url="https://other.com/")
        result = filter_events_by_schedule(self._make_events_list([e1]), SCHEDULE_URL)
        assert result == []

    def test_handles_empty_items_list(self):
        result = filter_events_by_schedule({"items": []}, SCHEDULE_URL)
        assert result == []

    def test_handles_missing_items_key(self):
        result = filter_events_by_schedule({}, SCHEDULE_URL)
        assert result == []


# ---------------------------------------------------------------------------
# build_patch_payload
# ---------------------------------------------------------------------------

class TestBuildPatchPayload:

    def test_basic_fields_present(self):
        payload = build_patch_payload("Round 1: Team", "2025-08-10T10:00:00", "2025-08-10T11:00:00", 5)
        assert payload["summary"] == "Round 1: Team"
        assert payload["start"]["dateTime"] == "2025-08-10T10:00:00"
        assert payload["end"]["dateTime"] == "2025-08-10T11:00:00"
        assert payload["colorId"] == 5

    def test_description_included_when_provided(self):
        payload = build_patch_payload("R1", "2025-08-10T10:00:00", "2025-08-10T11:00:00", 1, "https://url")
        assert payload["description"] == "https://url"

    def test_description_omitted_when_empty(self):
        payload = build_patch_payload("R1", "2025-08-10T10:00:00", "2025-08-10T11:00:00", 1)
        assert "description" not in payload


# ---------------------------------------------------------------------------
# determine_sync_action
# ---------------------------------------------------------------------------

class TestDetermineSyncAction:

    def _make_events(self, time: str, url: str = SCHEDULE_URL) -> dict:
        return {time: {"url": url, "id": "event-id-1"}}

    def test_exact_match_returns_exact(self):
        events = self._make_events("2025-08-10T10:00:00")
        action, event_id = determine_sync_action("2025-08-10T10:00:00", SCHEDULE_URL, events)
        assert action == "exact"
        assert event_id == "event-id-1"

    def test_exact_match_wrong_url_falls_through(self):
        events = self._make_events("2025-08-10T10:00:00", url="https://different.com/")
        action, _ = determine_sync_action("2025-08-10T10:00:00", SCHEDULE_URL, events)
        assert action != "exact"

    def test_same_date_different_time_returns_reschedule(self):
        events = self._make_events("2025-08-10T10:00:00")  # existing event at 10:00
        action, event_id = determine_sync_action("2025-08-10T20:00:00", SCHEDULE_URL, events)
        assert action == "reschedule"
        assert event_id == "event-id-1"

    def test_no_match_returns_create(self):
        events = self._make_events("2025-08-17T10:00:00")  # completely different date
        action, event_id = determine_sync_action("2025-08-10T10:00:00", SCHEDULE_URL, events)
        assert action == "create"
        assert event_id == ""

    def test_empty_events_returns_create(self):
        action, event_id = determine_sync_action("2025-08-10T10:00:00", SCHEDULE_URL, {})
        assert action == "create"
        assert event_id == ""

    def test_same_date_different_url_returns_create(self):
        """Same date but belonging to a different schedule → create, not reschedule."""
        events = {"2025-08-10T10:00:00": {"url": "https://other.com/", "id": "other-id"}}
        action, _ = determine_sync_action("2025-08-10T20:00:00", SCHEDULE_URL, events)
        assert action == "create"


# ---------------------------------------------------------------------------
# apply_field_patches
# ---------------------------------------------------------------------------

class TestApplyFieldPatches:

    def _make_gclient(self):
        return MagicMock()

    def _call(self, gclient, event_details: dict, **overrides):
        defaults = dict(
            calendar_id="cal-1",
            event_id="evt-1",
            round_name="Round 1: Team",
            color_id=5,
            details_url="https://ssb.com/score/1",
            venue="Court 3",
        )
        defaults.update(overrides)
        apply_field_patches(gclient=gclient, event_details=event_details, **defaults)

    def test_no_patches_when_all_fields_match(self):
        gclient = self._make_gclient()
        event_details = {
            "summary": "Round 1: Team",
            "colorId": "5",
            "description": "https://ssb.com/score/1",
            "location": "Court 3",
        }
        self._call(gclient, event_details)
        gclient.patch_event.assert_not_called()

    def test_patches_stale_summary(self):
        gclient = self._make_gclient()
        event_details = {
            "summary": "Old Name",
            "colorId": "5",
            "description": "https://ssb.com/score/1",
            "location": "Court 3",
        }
        self._call(gclient, event_details)
        gclient.patch_event.assert_any_call(
            calendar_id="cal-1",
            event_id="evt-1",
            patched_fields={"summary": "Round 1: Team"},
        )

    def test_patches_stale_color(self):
        gclient = self._make_gclient()
        event_details = {
            "summary": "Round 1: Team",
            "colorId": "99",
            "description": "https://ssb.com/score/1",
            "location": "Court 3",
        }
        self._call(gclient, event_details)
        gclient.patch_event.assert_any_call(
            calendar_id="cal-1",
            event_id="evt-1",
            patched_fields={"colorId": 5},
        )

    def test_patches_missing_description(self):
        """An event with no description key should get one patched in."""
        gclient = self._make_gclient()
        event_details = {
            "summary": "Round 1: Team",
            "colorId": "5",
            # no "description" key
            "location": "Court 3",
        }
        self._call(gclient, event_details)
        gclient.patch_event.assert_any_call(
            calendar_id="cal-1",
            event_id="evt-1",
            patched_fields={"description": "https://ssb.com/score/1"},
        )

    def test_patches_stale_location(self):
        gclient = self._make_gclient()
        event_details = {
            "summary": "Round 1: Team",
            "colorId": "5",
            "description": "https://ssb.com/score/1",
            "location": "Old Court",
        }
        self._call(gclient, event_details)
        gclient.patch_event.assert_any_call(
            calendar_id="cal-1",
            event_id="evt-1",
            patched_fields={"location": "Court 3"},
        )

    def test_patches_all_stale_fields(self):
        gclient = self._make_gclient()
        event_details = {
            "summary": "Old",
            "colorId": "1",
            "description": "https://old.com/",
            "location": "Old Court",
        }
        self._call(gclient, event_details)
        assert gclient.patch_event.call_count == 4

"""
Unit tests for helpers.event_sync — all pure functions, no I/O.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

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

"""
Unit tests for libs.google_cal_client.GoogleCalClient.

The Google API service is fully mocked via unittest.mock so no real OAuth
credentials or network calls are needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# We patch the heavy Google auth/build machinery before importing the module
# under test, so the import itself doesn't fail in a credentialless environment.
with patch("libs.google_cal_client.build"), \
     patch("libs.google_cal_client.Credentials"):
    from libs.google_cal_client import GoogleCalClient


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def gclient():
    """
    Return a GoogleCalClient instance with a fully mocked Google API service.

    Credentials validation is bypassed by patching both Credentials and build.
    """
    with patch("libs.google_cal_client.Credentials") as mock_creds_cls, \
         patch("libs.google_cal_client.build") as mock_build:

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.from_authorized_user_info.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        client = GoogleCalClient("TestClient", "client_id", "client_secret", "refresh_token")
        client.service = mock_service  # expose for test assertions
        return client


# ---------------------------------------------------------------------------
# get_calendar_list
# ---------------------------------------------------------------------------

class TestGetCalendarList:

    def test_calls_calendar_list(self, gclient):
        gclient.service.calendarList().list().execute.return_value = {"items": []}
        result = gclient.get_calendar_list()
        assert "items" in result

    def test_returns_items(self, gclient):
        fake = {"items": [{"id": "cal1", "summary": "My Cal"}]}
        gclient.service.calendarList().list().execute.return_value = fake
        assert gclient.get_calendar_list() == fake


# ---------------------------------------------------------------------------
# insert_calendar
# ---------------------------------------------------------------------------

class TestInsertCalendar:

    def test_returns_calendar_id(self, gclient):
        gclient.service.calendars().insert().execute.return_value = {"id": "new-cal-id"}
        result = gclient.insert_calendar("Test Calendar", "A description")
        assert result == "new-cal-id"

    def test_passes_correct_body(self, gclient):
        gclient.service.calendars().insert().execute.return_value = {"id": "x"}
        gclient.insert_calendar("My Cal", "Desc", time_zone="Australia/Sydney")
        call_kwargs = gclient.service.calendars().insert.call_args
        body = call_kwargs.kwargs.get("body") or call_kwargs.args[0]
        assert body["summary"] == "My Cal"
        assert body["timeZone"] == "Australia/Sydney"


# ---------------------------------------------------------------------------
# create_event
# ---------------------------------------------------------------------------

class TestCreateEvent:

    def test_returns_event_id(self, gclient):
        gclient.service.events().insert().execute.return_value = {"id": "evt-abc"}
        result = gclient.create_event(
            event_name="Round 1",
            start_time="2025-08-10T10:00:00",
            end_time="2025-08-10T11:00:00",
            location="Court 1",
            private_properties={"schedule": "https://example.com"},
            calendar_id="cal-1",
        )
        assert result == "evt-abc"

    def test_event_body_contains_private_properties(self, gclient):
        gclient.service.events().insert().execute.return_value = {"id": "x"}
        gclient.create_event(
            event_name="Round 1",
            start_time="2025-08-10T10:00:00",
            end_time="2025-08-10T11:00:00",
            location="Court 1",
            private_properties={"schedule": "https://example.com"},
            calendar_id="cal-1",
        )
        insert_call = gclient.service.events().insert.call_args
        body = insert_call.kwargs.get("body") or insert_call.args[0]
        assert body["extendedProperties"]["private"]["schedule"] == "https://example.com"

    def test_description_included_in_body(self, gclient):
        gclient.service.events().insert().execute.return_value = {"id": "x"}
        gclient.create_event(
            event_name="R1",
            start_time="2025-08-10T10:00:00",
            end_time="2025-08-10T11:00:00",
            location="Court 1",
            private_properties={},
            description="https://score.url",
            calendar_id="cal-1",
        )
        insert_call = gclient.service.events().insert.call_args
        body = insert_call.kwargs.get("body") or insert_call.args[0]
        assert body["description"] == "https://score.url"


# ---------------------------------------------------------------------------
# patch_event
# ---------------------------------------------------------------------------

class TestPatchEvent:

    def test_returns_event_id(self, gclient):
        gclient.service.events().patch().execute.return_value = {"id": "patched-id"}
        result = gclient.patch_event(
            event_id="evt-1",
            patched_fields={"summary": "New Name"},
            calendar_id="cal-1",
        )
        assert result == "patched-id"


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------

class TestListEvents:

    def test_returns_events_dict(self, gclient):
        fake = {"items": [{"id": "e1"}, {"id": "e2"}]}
        gclient.service.events().list().execute.return_value = fake
        result = gclient.list_events(calendar_id="cal-1")
        assert result == fake


# ---------------------------------------------------------------------------
# get_event_details
# ---------------------------------------------------------------------------

class TestGetEventDetails:

    def test_returns_event_dict(self, gclient):
        fake = {"id": "e1", "summary": "Round 1"}
        gclient.service.events().get().execute.return_value = fake
        result = gclient.get_event_details(event_id="e1", calendar_id="cal-1")
        assert result == fake

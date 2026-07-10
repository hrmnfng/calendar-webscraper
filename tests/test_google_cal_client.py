"""
Unit tests for libs.google_cal_client.GoogleCalClient.

The Google API service and credentials are fully mocked — no real OAuth
credentials or network calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

with patch("libs.google_cal_client.build"), \
     patch("libs.google_cal_client.Credentials"):
    from libs.google_cal_client import GoogleCalClient


@pytest.fixture
def gclient():
    with patch("libs.google_cal_client.Credentials") as mock_creds_cls, \
         patch("libs.google_cal_client.build") as mock_build:

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.from_authorized_user_info.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        client = GoogleCalClient("Test", "cid", "csecret", "rtoken")
        client.service = mock_service
        return client


class TestGetCalendarList:
    def test_returns_items(self, gclient):
        fake = {"items": [{"id": "cal1"}]}
        gclient.service.calendarList().list().execute.return_value = fake
        assert gclient.get_calendar_list() == fake


class TestInsertCalendar:
    def test_returns_calendar_id(self, gclient):
        gclient.service.calendars().insert().execute.return_value = {"id": "new-cal"}
        assert gclient.insert_calendar("My Cal", "Desc") == "new-cal"

    def test_body_contains_summary_and_timezone(self, gclient):
        gclient.service.calendars().insert().execute.return_value = {"id": "x"}
        gclient.insert_calendar("My Cal", "Desc", time_zone="Australia/Sydney")
        body = gclient.service.calendars().insert.call_args.kwargs.get("body") \
               or gclient.service.calendars().insert.call_args.args[0]
        assert body["summary"] == "My Cal"
        assert body["timeZone"] == "Australia/Sydney"


class TestCreateEvent:
    def test_returns_event_id(self, gclient):
        gclient.service.events().insert().execute.return_value = {"id": "evt-abc"}
        result = gclient.create_event(
            event_name="Round 1", start_time="2025-08-10T10:00:00",
            end_time="2025-08-10T11:00:00", location="Court 1",
            private_properties={"schedule": "https://example.com"}, calendar_id="cal-1",
        )
        assert result == "evt-abc"

    def test_private_properties_in_body(self, gclient):
        gclient.service.events().insert().execute.return_value = {"id": "x"}
        gclient.create_event(
            event_name="R1", start_time="2025-08-10T10:00:00",
            end_time="2025-08-10T11:00:00", location="Court 1",
            private_properties={"schedule": "https://example.com"}, calendar_id="cal-1",
        )
        body = gclient.service.events().insert.call_args.kwargs.get("body") \
               or gclient.service.events().insert.call_args.args[0]
        assert body["extendedProperties"]["private"]["schedule"] == "https://example.com"

    def test_description_included_when_provided(self, gclient):
        gclient.service.events().insert().execute.return_value = {"id": "x"}
        gclient.create_event(
            event_name="R1", start_time="2025-08-10T10:00:00",
            end_time="2025-08-10T11:00:00", location="Court 1",
            private_properties={}, description="https://score.url", calendar_id="cal-1",
        )
        body = gclient.service.events().insert.call_args.kwargs.get("body") \
               or gclient.service.events().insert.call_args.args[0]
        assert body["description"] == "https://score.url"

    def test_description_omitted_when_empty(self, gclient):
        gclient.service.events().insert().execute.return_value = {"id": "x"}
        gclient.create_event(
            event_name="R1", start_time="2025-08-10T10:00:00",
            end_time="2025-08-10T11:00:00", location="Court 1",
            private_properties={}, calendar_id="cal-1",
        )
        body = gclient.service.events().insert.call_args.kwargs.get("body") \
               or gclient.service.events().insert.call_args.args[0]
        assert "description" not in body


class TestPatchEvent:
    def test_returns_event_id(self, gclient):
        gclient.service.events().patch().execute.return_value = {"id": "patched"}
        result = gclient.patch_event("evt-1", {"summary": "New"}, "cal-1")
        assert result == "patched"


class TestListEvents:
    def test_returns_events_list(self, gclient):
        fake = {"items": [{"id": "e1"}]}
        gclient.service.events().list().execute.return_value = fake
        assert gclient.list_events("cal-1") == [{"id": "e1"}]


class TestListEventsPagination:

    def _client_with_pages(self, pages):
        """Build a GoogleCalClient with a stubbed events().list() chain."""
        client = object.__new__(GoogleCalClient)  # skip __init__ (no creds)
        service = MagicMock()
        executes = [
            {"items": items, **({"nextPageToken": tok} if tok else {})}
            for items, tok in pages
        ]
        service.events.return_value.list.return_value.execute.side_effect = executes
        client.service = service
        return client, service

    def test_single_page_returns_items_list(self):
        client, _ = self._client_with_pages([([{"id": "a"}], None)])
        assert client.list_events(calendar_id="cal") == [{"id": "a"}]

    def test_follows_next_page_token(self):
        client, service = self._client_with_pages(
            [([{"id": "a"}], "tok1"), ([{"id": "b"}], None)]
        )
        events = client.list_events(calendar_id="cal")
        assert [e["id"] for e in events] == ["a", "b"]
        second_call = service.events.return_value.list.call_args_list[1]
        assert second_call.kwargs["pageToken"] == "tok1"


class TestGetEventDetails:
    def test_returns_event_dict(self, gclient):
        fake = {"id": "e1", "summary": "Round 1"}
        gclient.service.events().get().execute.return_value = fake
        assert gclient.get_event_details("e1", "cal-1") == fake


class TestEnsureCalendarPublic:
    def _client_with_acl(self, items):
        """Build a GoogleCalClient with a stubbed acl() chain."""
        client = object.__new__(GoogleCalClient)  # skip __init__ (no creds)
        service = MagicMock()
        service.acl.return_value.list.return_value.execute.return_value = {
            "items": items
        }
        client.service = service
        return client, service

    def test_inserts_default_reader_rule_when_not_public(self):
        client, service = self._client_with_acl(
            [{"role": "owner", "scope": {"type": "user", "value": "me@example.com"}}]
        )
        client.ensure_calendar_public("cal-1")
        service.acl.return_value.insert.assert_called_once_with(
            calendarId="cal-1",
            body={"role": "reader", "scope": {"type": "default"}},
        )
        service.acl.return_value.insert.return_value.execute.assert_called_once()

    def test_noop_when_already_public(self):
        client, service = self._client_with_acl(
            [{"role": "reader", "scope": {"type": "default"}}]
        )
        client.ensure_calendar_public("cal-1")
        service.acl.return_value.insert.assert_not_called()

    def test_freebusy_only_rule_does_not_count_as_public(self):
        client, service = self._client_with_acl(
            [{"role": "freeBusyReader", "scope": {"type": "default"}}]
        )
        client.ensure_calendar_public("cal-1")
        service.acl.return_value.insert.assert_called_once()

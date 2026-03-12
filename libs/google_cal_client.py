"""
Google Calendar API client using OAuth2 credentials.
"""

from __future__ import annotations

import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from loguru import logger

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalClient:
    """
    Google Calendar API client authenticated via OAuth2 refresh token.

    Attributes:
        name: Identifier for this client instance (used in log messages).
    """

    def __init__(
        self,
        name: str,
        gcal_client_id: str,
        gcal_client_secret: str,
        gcal_refresh_token: str,
    ) -> None:
        self.name = name

        self.creds = Credentials.from_authorized_user_info(
            {
                "client_id": gcal_client_id,
                "client_secret": gcal_client_secret,
                "refresh_token": gcal_refresh_token,
            },
            scopes=SCOPES,
        )

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                sys.exit(
                    'Credentials are invalid. Please generate a new refresh token '
                    'by running `uv run python libs/google_cal_client.py`.'
                )

        self.service = build("calendar", "v3", credentials=self.creds)
        logger.debug(f"Created GCal client '{name}'")

    def get_calendar_list(self) -> dict:
        """Return the authenticated user's full calendar list."""
        return self.service.calendarList().list().execute()

    def insert_calendar(
        self,
        calendar_name: str,
        description: str,
        time_zone: str = "Australia/Sydney",
    ) -> str:
        """Create a new calendar and return its ID."""
        body = {
            "summary": calendar_name,
            "description": description,
            "timeZone": time_zone,
        }
        created = self.service.calendars().insert(body=body).execute()
        return created["id"]

    def patch_calendar(self, calendar_id: str, patched_fields: dict) -> str:
        """Patch calendar metadata fields and return the calendar ID."""
        response = self.service.calendars().patch(
            calendarId=calendar_id, body=patched_fields
        ).execute()
        return response.get("id")

    def create_event(
        self,
        event_name: str,
        start_time: str,
        end_time: str,
        location: str,
        private_properties: dict,
        description: str = "",
        calendar_id: str = "primary",
        visible_attendees: bool = False,
        time_zone: str = "Australia/Sydney",
        color_id: int = 1,
        attendees: list = [],
    ) -> str:
        """
        Insert a new Google Calendar event and return its ID.

        Args:
            event_name: Event title/summary.
            start_time: Start datetime string ``"%Y-%m-%dT%H:%M:%S"``.
            end_time: End datetime string ``"%Y-%m-%dT%H:%M:%S"``.
            location: Event location string.
            private_properties: Key-value pairs stored as private extended properties.
            description: Optional event description.
            calendar_id: Target calendar (default ``"primary"``).
            visible_attendees: Whether attendees can see each other.
            time_zone: IANA timezone name (default ``"Australia/Sydney"``).
            color_id: Google Calendar event color ID 1–11.
            attendees: List of attendee dicts e.g. ``[{"email": "..."}]``.

        Returns:
            The created event's ID.
        """
        body: dict = {
            "summary": event_name,
            "start": {"dateTime": start_time, "timeZone": time_zone},
            "end": {"dateTime": end_time, "timeZone": time_zone},
            "attendees": attendees,
            "location": location,
            "extendedProperties": {"private": private_properties},
            "guestsCanSeeOtherGuests": visible_attendees,
            "colorId": color_id,
        }
        if description:
            body["description"] = description

        response = self.service.events().insert(
            calendarId=calendar_id, body=body
        ).execute()
        return response.get("id")

    def patch_event(
        self,
        event_id: str,
        patched_fields: dict,
        calendar_id: str = "primary",
    ) -> str:
        """Patch specific fields on an existing event and return the event ID."""
        response = self.service.events().patch(
            calendarId=calendar_id, eventId=event_id, body=patched_fields
        ).execute()
        return response.get("id")

    def update_event(
        self,
        event_id: str,
        updated_event: dict,
        calendar_id: str = "primary",
    ) -> dict:
        """Full PUT-style replacement of an event. Returns the updated event dict."""
        return self.service.events().update(
            calendarId=calendar_id, eventId=event_id, body=updated_event
        ).execute()

    def list_events(self, calendar_id: str = "primary") -> dict:
        """Return the events list dict for *calendar_id*."""
        return self.service.events().list(calendarId=calendar_id).execute()

    def get_event_details(self, event_id: str, calendar_id: str = "primary") -> dict:
        """Return the full event dict for *event_id*."""
        return self.service.events().get(
            calendarId=calendar_id, eventId=event_id
        ).execute()


# Running this module directly triggers the one-time OAuth flow used to
# generate the refresh token that is stored as an environment variable.
if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)
    print(f"Client ID:     {creds.client_id}")
    print(f"Client Secret: {creds.client_secret}")
    print(f"Refresh Token: {creds.refresh_token}")

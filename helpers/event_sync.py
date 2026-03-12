"""
Utility functions for comparing scraped game data against existing Google Calendar
events and determining what needs to be created, patched, or left unchanged.

These are pure functions (no I/O, no API calls) so they are straightforward to
unit test and can be reused independently of any particular calendar client.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from libs.google_cal_client import GoogleCalClient


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def format_game_times(game: dict) -> tuple[str, str]:
    """
    Format a game's start and end datetimes as ISO-8601 strings.

    Args:
        game: A game dict as returned by :meth:`ScraperClient.scrape_events`,
              containing ``"start"`` and ``"end"`` :class:`~datetime.datetime`
              values.

    Returns:
        A ``(tip_off, finish)`` tuple, both formatted as
        ``"%Y-%m-%dT%H:%M:%S"``.
    """
    tip_off = game["start"].strftime("%Y-%m-%dT%H:%M:%S")
    finish = game["end"].strftime("%Y-%m-%dT%H:%M:%S")
    return tip_off, finish


def get_game_details(game: dict) -> tuple[str, str, str, str, str]:
    """
    Unpack all relevant fields from a scraped game dict.

    Args:
        game: A game dict as returned by :meth:`ScraperClient.scrape_events`.

    Returns:
        ``(round_name, tip_off, finish, venue, details_url)``
    """
    tip_off, finish = format_game_times(game)
    return game["round"], tip_off, finish, game["location"], game["details_url"]


def simplify_existing_events(existing_events: list[dict]) -> dict[str, dict]:
    """
    Convert a raw Google Calendar events list into a lightweight lookup dict.

    The returned dict is keyed by the event's start datetime string (with the
    UTC offset suffix stripped) so it can be compared directly against
    ``tip_off`` strings produced by :func:`format_game_times`.

    Args:
        existing_events: The ``["items"]`` list from a
            :meth:`GoogleCalClient.list_events` response, pre-filtered to the
            relevant schedule URL.

    Returns:
        ``{ "2025-08-10T10:00:00": {"url": "https://...", "id": "<gcal_id>"} }``
    """
    logger.debug(f"Simplifying event list of length '{len(existing_events)}'")
    events_simple: dict[str, dict] = {}

    for event in existing_events:
        # GCal returns times like "2025-08-10T10:00:00+10:00" — strip the offset
        time = event["start"]["dateTime"][:-6]
        url = event["extendedProperties"]["private"]["schedule"]
        events_simple[time] = {"url": url, "id": event["id"]}

    return events_simple


def filter_events_by_schedule(events_list: dict, schedule_url: str) -> list[dict]:
    """
    Return only the events whose ``extendedProperties.private.schedule``
    matches *schedule_url*.

    Args:
        events_list: The full dict returned by :meth:`GoogleCalClient.list_events`.
        schedule_url: The schedule URL to filter by.

    Returns:
        Filtered list of event dicts.
    """
    return [
        event
        for event in events_list.get("items", [])
        if event.get("extendedProperties", {}).get("private", {}).get("schedule") == schedule_url
    ]


def build_patch_payload(
    round_name: str,
    tip_off: str,
    finish: str,
    color_id: int | str,
    description: str = "",
) -> dict:
    """
    Build a minimal patch payload for updating an existing Google Calendar event.

    Args:
        round_name: The event summary/title.
        tip_off: New start datetime string (``"%Y-%m-%dT%H:%M:%S"``).
        finish: New end datetime string (``"%Y-%m-%dT%H:%M:%S"``).
        color_id: Google Calendar color ID.
        description: Optional event description.

    Returns:
        Dict suitable for passing to :meth:`GoogleCalClient.patch_event`.
    """
    payload: dict = {
        "summary": round_name,
        "start": {"dateTime": tip_off},
        "end": {"dateTime": finish},
        "colorId": color_id,
    }
    if description:
        payload["description"] = description
    return payload


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def determine_sync_action(
    tip_off: str,
    schedule_url: str,
    events_simple: dict[str, dict],
) -> tuple[str, str]:
    """
    Decide what action to take for a single scraped game.

    The three possible outcomes mirror the original matching logic:

    * ``"exact"``   — a GCal event already exists at exactly the same time
      and belongs to the same schedule.  The event ID is returned so the
      caller can check whether any fields need patching.
    * ``"reschedule"`` — an event exists on the same date but at a different
      time (i.e. the game has been moved).  The existing event ID is returned
      so it can be patched with the new time.
    * ``"create"``  — no matching event found; a new one must be inserted.

    Args:
        tip_off: The scraped start datetime string (``"%Y-%m-%dT%H:%M:%S"``).
        schedule_url: The schedule URL for the current team/calendar.
        events_simple: Simplified existing events dict from
            :func:`simplify_existing_events`.

    Returns:
        ``(action, event_id)`` where *event_id* is an empty string for ``"create"``.
    """
    # Exact time + schedule match
    if tip_off in events_simple and events_simple[tip_off]["url"] == schedule_url:
        return "exact", events_simple[tip_off]["id"]

    # Same date, different time — find events on the same date that belong to
    # this schedule
    date_prefix = tip_off[:-9]  # "YYYY-MM-DD"
    for existing_time, meta in events_simple.items():
        if date_prefix in existing_time and meta["url"] == schedule_url:
            return "reschedule", meta["id"]

    return "create", ""


def apply_field_patches(
    gclient: "GoogleCalClient",
    calendar_id: str,
    event_id: str,
    event_details: dict,
    round_name: str,
    color_id: int | str,
    details_url: str,
    venue: str,
) -> None:
    """
    Compare each patchable field on an existing event against the scraped values
    and issue individual PATCH calls for any that have drifted.

    Args:
        gclient: Authenticated :class:`~libs.google_cal_client.GoogleCalClient`.
        calendar_id: ID of the calendar containing the event.
        event_id: ID of the event to inspect and potentially patch.
        event_details: Full event dict from :meth:`GoogleCalClient.get_event_details`.
        round_name: Expected event summary.
        color_id: Expected color ID.
        details_url: Expected description / score link.
        venue: Expected location string.
    """
    if event_details.get("summary") != round_name:
        gclient.patch_event(calendar_id=calendar_id, event_id=event_id, patched_fields={"summary": round_name})
        logger.info(f"\tPatched the name for [{round_name}] - id [{event_id}]")

    if event_details.get("colorId") != str(color_id):
        gclient.patch_event(calendar_id=calendar_id, event_id=event_id, patched_fields={"colorId": color_id})
        logger.info(f"\tPatched the color for [{round_name}] - id [{event_id}]")

    # description may be absent on older events — treat a missing key the same
    # as a mismatch and patch it in
    existing_description = event_details.get("description")
    if existing_description != details_url:
        gclient.patch_event(calendar_id=calendar_id, event_id=event_id, patched_fields={"description": details_url})
        logger.info(f"\tPatched the description for [{round_name}] - id [{event_id}]")

    if event_details.get("location") != venue:
        gclient.patch_event(calendar_id=calendar_id, event_id=event_id, patched_fields={"location": venue})
        logger.info(f"\tPatched the location for [{round_name}] - id [{event_id}]")

    logger.debug(f"[{round_name}] field check complete")

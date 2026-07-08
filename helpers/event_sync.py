"""
Pure utility functions for comparing scraped game data against existing Google
Calendar events and determining what action to take (create, patch time,
or update stale fields).

These functions have no I/O or API calls, making them straightforward to unit test.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from helpers.models import ExistingEvent, Game

if TYPE_CHECKING:
    from libs.google_cal_client import GoogleCalClient


def format_game_times(game: dict) -> tuple[str, str]:
    """
    Format a game's start/end datetimes as ISO-8601 strings.

    Args:
        game: Game dict from :meth:`ScraperClient.scrape_events` with
              ``"start"`` and ``"end"`` :class:`~datetime.datetime` values.

    Returns:
        ``(tip_off, finish)`` both formatted as ``"%Y-%m-%dT%H:%M:%S"``.
    """
    return (
        game["start"].strftime("%Y-%m-%dT%H:%M:%S"),
        game["end"].strftime("%Y-%m-%dT%H:%M:%S"),
    )


def get_game_details(game: dict) -> tuple[str, str, str, str, str]:
    """
    Unpack all relevant fields from a scraped game dict.

    Returns:
        ``(round_name, tip_off, finish, venue, details_url)``
    """
    tip_off, finish = format_game_times(game)
    return game["round"], tip_off, finish, game["location"], game["details_url"]


def simplify_existing_events(existing_events: list[dict]) -> dict[str, dict]:
    """
    Convert a raw GCal events list into a lightweight start-time-keyed dict.

    The UTC offset suffix is stripped from GCal's dateTime strings so they
    compare directly against ``tip_off`` strings from :func:`format_game_times`.

    Args:
        existing_events: The ``["items"]`` list from
            :meth:`GoogleCalClient.list_events`, pre-filtered to the relevant
            schedule URL.

    Returns:
        ``{ "2025-08-10T10:00:00": {"url": "https://...", "id": "<gcal_id>"} }``
    """
    logger.debug(f"Simplifying event list of length '{len(existing_events)}'")
    events_simple: dict[str, dict] = {}
    for event in existing_events:
        time = event["start"]["dateTime"][:-6]  # strip "+10:00" offset
        url = event["extendedProperties"]["private"]["schedule"]
        events_simple[time] = {"url": url, "id": event["id"]}
    return events_simple


def filter_events_by_schedule(events_list: dict, schedule_url: str) -> list[dict]:
    """
    Return only the events whose ``extendedProperties.private.schedule``
    matches *schedule_url*.
    """
    return [
        event
        for event in events_list.get("items", [])
        if event.get("extendedProperties", {})
           .get("private", {})
           .get("schedule") == schedule_url
    ]


def build_patch_payload(
    round_name: str,
    tip_off: str,
    finish: str,
    color_id: int | str,
    description: str = "",
) -> dict:
    """
    Build a minimal patch payload for updating an existing GCal event's time.

    Args:
        round_name: Event summary/title.
        tip_off: New start datetime string (``"%Y-%m-%dT%H:%M:%S"``).
        finish: New end datetime string.
        color_id: Google Calendar color ID.
        description: Optional event description.

    Returns:
        Dict suitable for :meth:`GoogleCalClient.patch_event`.
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


def determine_sync_action(
    tip_off: str,
    schedule_url: str,
    events_simple: dict[str, dict],
) -> tuple[str, str]:
    """
    Decide what action to take for a single scraped game.

    Returns one of three ``(action, event_id)`` pairs:

    * ``("exact", id)``      — event exists at exactly this time for this schedule.
    * ``("reschedule", id)`` — event exists on the same date but different time.
    * ``("create", "")``     — no matching event found; insert a new one.
    """
    # Exact time + schedule match
    if tip_off in events_simple and events_simple[tip_off]["url"] == schedule_url:
        return "exact", events_simple[tip_off]["id"]

    # Same date, different time — find events on the same date for this schedule
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
    Issue individual PATCH calls for any fields that have drifted from the
    scraped values. Fields that already match are left untouched.
    """
    if event_details.get("summary") != round_name:
        gclient.patch_event(
            calendar_id=calendar_id, event_id=event_id,
            patched_fields={"summary": round_name},
        )
        logger.info(f"\tPatched name for [{round_name}]")

    if event_details.get("colorId") != str(color_id):
        gclient.patch_event(
            calendar_id=calendar_id, event_id=event_id,
            patched_fields={"colorId": color_id},
        )
        logger.info(f"\tPatched color for [{round_name}]")

    # A missing description key is treated the same as a mismatch
    if event_details.get("description") != details_url:
        gclient.patch_event(
            calendar_id=calendar_id, event_id=event_id,
            patched_fields={"description": details_url},
        )
        logger.info(f"\tPatched description for [{round_name}]")

    if event_details.get("location") != venue:
        gclient.patch_event(
            calendar_id=calendar_id, event_id=event_id,
            patched_fields={"location": venue},
        )
        logger.info(f"\tPatched location for [{round_name}]")

    logger.debug(f"[{round_name}] field check complete")


# ---------------------------------------------------------------------------
# Identity-based sync functions (Task 7) — additive; legacy functions above
# are kept intact until main.py is rewired in Task 9.
# ---------------------------------------------------------------------------


def parse_existing_events(events: list[dict]) -> list[ExistingEvent]:
    """
    Convert raw GCal event dicts into :class:`ExistingEvent` records with
    timezone-aware start datetimes and the ``gameKey`` extended property.

    All-day events (``start.date`` instead of ``start.dateTime``) are skipped
    with a warning — they cannot have been created by this tool.
    """
    parsed: list[ExistingEvent] = []
    for event in events:
        dt_str = event.get("start", {}).get("dateTime")
        if not dt_str:
            logger.warning(
                f"Skipping all-day or malformed event [{event.get('id')}] "
                "— no start.dateTime"
            )
            continue
        start = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        key = (
            event.get("extendedProperties", {})
            .get("private", {})
            .get("gameKey")
        )
        parsed.append(ExistingEvent(id=event["id"], key=key, start=start))
    return parsed


def match_game_to_event(
    game: Game, existing: list[ExistingEvent]
) -> tuple[str, ExistingEvent | None]:
    """
    Match a scraped game against existing calendar events.

    Matching order:

    1. **By key** — an event with the same ``gameKey``: ``exact`` if the start
       instant is unchanged, else ``reschedule``.
    2. **Legacy fallback** — only events *without* a key (created before key
       tracking) are considered: exact start-instant match → ``exact``; same
       calendar date → ``reschedule``. Keyed events for other games are never
       matched, so double-headers cannot collide.
    3. Otherwise ``("create", None)``.

    The caller should remove a returned event from *existing* so it cannot be
    matched twice in one run.
    """
    by_key = {e.key: e for e in existing if e.key}
    if game.key in by_key:
        event = by_key[game.key]
        action = "exact" if event.start == game.start else "reschedule"
        return action, event

    legacy = [e for e in existing if e.key is None]
    for event in legacy:
        if event.start == game.start:
            return "exact", event
    for event in legacy:
        if event.start.date() == game.start.date():
            return "reschedule", event

    return "create", None


def build_reschedule_patch(game: Game, color_id: int | str) -> dict:
    """Build the full patch payload for a rescheduled (or adopted) event."""
    return {
        "summary": game.title,
        "start": {"dateTime": game.start.isoformat()},
        "end": {"dateTime": game.end.isoformat()},
        "location": game.venue,
        "colorId": str(color_id),
        "description": game.details_url,
        "extendedProperties": {"private": {"gameKey": game.key}},
    }


def build_field_patch(event_details: dict, game: Game, color_id: int | str) -> dict:
    """
    Compare an existing event's fields against the scraped game and return a
    single patch dict containing only drifted fields (empty if none).

    Also adds the ``gameKey`` extended property when missing, which migrates
    legacy events to identity-based matching. GCal merges extended property
    keys on patch, so other private properties (``schedule``) are preserved.
    """
    patch: dict = {}
    if event_details.get("summary") != game.title:
        patch["summary"] = game.title
    if event_details.get("colorId") != str(color_id):
        patch["colorId"] = str(color_id)
    if event_details.get("description") != game.details_url:
        patch["description"] = game.details_url
    if event_details.get("location") != game.venue:
        patch["location"] = game.venue
    existing_key = (
        event_details.get("extendedProperties", {}).get("private", {}).get("gameKey")
    )
    if existing_key != game.key:
        patch["extendedProperties"] = {"private": {"gameKey": game.key}}
    return patch

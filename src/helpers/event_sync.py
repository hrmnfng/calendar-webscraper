"""
Pure utility functions for comparing scraped game data against existing Google
Calendar events and determining what action to take (create, patch time,
or update stale fields).

These functions have no I/O or API calls, making them straightforward to unit test.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from helpers.models import ExistingEvent, Game


def filter_events_by_schedule(events: list[dict], schedule_url: str) -> list[dict]:
    """
    Return only the events whose ``extendedProperties.private.schedule``
    matches *schedule_url*.
    """
    return [
        event
        for event in events
        if event.get("extendedProperties", {})
           .get("private", {})
           .get("schedule") == schedule_url
    ]


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
       calendar date (compared in the game's timezone) → ``reschedule``. Keyed events for other games are never
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
        if event.start.astimezone(game.start.tzinfo).date() == game.start.date():
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

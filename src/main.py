"""
Main entry point for the calendar-webscraper pipeline.

Reads all active ``calendar-configs/config-*.yaml`` files, fetches the
corresponding basketball schedule pages (WordPress API with HTML fallback),
and syncs the results into Google Calendar (creating new events, patching
reschedules, and updating stale fields).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from loguru import logger

from helpers.ascii_strings import IMPORTANT_STUFF_1, IMPORTANT_STUFF_2, IMPORTANT_STUFF_3
from helpers.config_loader import CalendarConfig, load_configs
from helpers.event_sync import (
    build_field_patch,
    build_reschedule_patch,
    filter_events_by_schedule,
    match_game_to_event,
    parse_existing_events,
)
from helpers.models import Game
from helpers.sources import fetch_games
from libs.google_cal_client import GoogleCalClient
from libs.scraper_client import ScraperClient

CONFIG_DIR = "./calendar-configs"


def configure_logging(log_level: str) -> None:
    """Set up loguru sinks (file + stderr) with a custom MAJOR level."""
    logger.remove()
    logger.add("logs/cal_run_{time}.log")
    logger.level("MAJOR", no=21, color="<yellow>")
    logger.add(
        sink=sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{file}</cyan>:<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "- <level>{message}</level>"
        ),
        level=log_level,
        backtrace=True,
        diagnose=True,
    )
    logger.info(f"Log level: {log_level}")


def get_or_create_calendar(gclient: GoogleCalClient, name: str, source_url: str) -> str:
    """
    Return the calendar ID for *name*, creating it if it doesn't exist.

    Args:
        gclient: Authenticated Google Calendar client.
        name: Display name of the calendar.
        source_url: Schedule URL used in the calendar description.

    Returns:
        Google Calendar ID string.
    """
    calendar_list = gclient.get_calendar_list()

    for calendar in calendar_list.get("items", []):
        if calendar["summary"] == name:
            calendar_id = calendar["id"]
            logger.info(f"Calendar [{name}] already exists with id [{calendar_id}]")
            return calendar_id

    description = f'This calendar has been extracted from "{source_url}"'
    logger.info(f"Calendar [{name}] does not yet exist - Creating:")
    calendar_id = gclient.insert_calendar(calendar_name=name, description=description)
    logger.info(f" -> Calendar [{name}] created with id [{calendar_id}]")
    return calendar_id


def sync_calendar(
    gclient: GoogleCalClient,
    scraper: ScraperClient,
    config: CalendarConfig,
) -> None:
    """
    Fetch the schedule for *config* and sync it into Google Calendar.

    Games are matched to existing events by their stable ``gameKey``
    (extended property); legacy keyless events are matched by start time
    once and adopt a key via the field patch. For each game:

    * **exact** — event exists at the right time; drifted fields are patched.
    * **reschedule** — event exists but the time changed; fully re-patched.
    * **create** — no matching event; a new one is inserted.
    """
    games = fetch_games(scraper, config)

    logger.log("MAJOR", IMPORTANT_STUFF_1)
    calendar_id = get_or_create_calendar(gclient, config.name, config.url)

    logger.log("MAJOR", IMPORTANT_STUFF_2)
    all_events = gclient.list_events(calendar_id=calendar_id)
    schedule_events = filter_events_by_schedule(all_events, config.url)
    existing = parse_existing_events(schedule_events)

    for game in games:
        action, matched = match_game_to_event(game, existing)
        if matched is not None:
            existing.remove(matched)  # an event can only be matched once per run

        if action == "exact":
            logger.info(f"[{game.title}] already exists — checking for stale fields...")
            event_details = gclient.get_event_details(
                calendar_id=calendar_id, event_id=matched.id
            )
            patch = build_field_patch(event_details, game, config.color_id)
            if patch:
                gclient.patch_event(
                    calendar_id=calendar_id, event_id=matched.id, patched_fields=patch
                )
                logger.info(f"\tPatched {sorted(patch)} for [{game.title}]")

        elif action == "reschedule":
            logger.info(f"[{game.title}] has been rescheduled — patching...")
            patch = build_reschedule_patch(game, config.color_id)
            gclient.patch_event(
                calendar_id=calendar_id, event_id=matched.id, patched_fields=patch
            )
            logger.info(
                f"\tEvent [{game.title}] updated to [{game.start.isoformat()}] "
                f"- id [{matched.id}]"
            )

        else:  # "create"
            _create_event(gclient, calendar_id, game, config)

    logger.success(f"Finished syncing '{config.name}'")


def _create_event(
    gclient: GoogleCalClient,
    calendar_id: str,
    game: Game,
    config: CalendarConfig,
) -> None:
    """Insert a new Google Calendar event and log the result."""
    logger.info(f"[{game.title}] is a new event — creating...")
    event_id = gclient.create_event(
        calendar_id=calendar_id,
        event_name=game.title,
        start_time=game.start.isoformat(),
        end_time=game.end.isoformat(),
        location=game.venue,
        private_properties={"schedule": config.url, "gameKey": game.key},
        color_id=config.color_id,
        description=game.details_url,
    )
    logger.success(f"\tEvent [{event_id}] created for [{game.title}]")


def main() -> None:
    """Entry point: load .env, configure logging, build clients, sync calendars."""
    # Load .env if present — values already in the environment take precedence
    load_dotenv(override=False)

    log_level = os.environ.get("LOG_LEVEL", "INFO")
    configure_logging(log_level)

    scraper = ScraperClient("Peter Parker")
    gclient = GoogleCalClient(
        "Cal.Endar",
        os.environ["GCAL_CLIENT_ID"],
        os.environ["GCAL_CLIENT_SECRET"],
        os.environ["GCAL_REFRESH_TOKEN"],
    )

    configs = load_configs(CONFIG_DIR)

    failures: list[str] = []
    for config in configs:
        try:
            sync_calendar(gclient=gclient, scraper=scraper, config=config)
        except Exception:
            logger.exception(f"Failed to sync calendar '{config.name}'")
            failures.append(config.name)

    logger.log("MAJOR", IMPORTANT_STUFF_3)

    if failures:
        logger.error(
            f"{len(failures)}/{len(configs)} calendar(s) failed to sync: {failures}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

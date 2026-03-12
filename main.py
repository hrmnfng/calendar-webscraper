"""
Main entry point for the calendar-webscraper pipeline.

Reads all active ``calendar-configs/config-*.yaml`` files, scrapes the
corresponding basketball schedule pages, and syncs the results into Google
Calendar (creating new events, patching reschedules, and updating stale fields).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from loguru import logger

from helpers.ascii_strings import IMPORTANT_STUFF_1, IMPORTANT_STUFF_2, IMPORTANT_STUFF_3
from helpers.config_loader import CalendarConfig, load_configs
from helpers.event_sync import (
    apply_field_patches,
    build_patch_payload,
    determine_sync_action,
    filter_events_by_schedule,
    get_game_details,
    simplify_existing_events,
)
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
    Return the calendar ID for *name*, creating the calendar if it doesn't exist.

    Args:
        gclient: Authenticated Google Calendar client.
        name: Display name of the calendar.
        source_url: The schedule URL — used in the calendar description.

    Returns:
        The Google Calendar ID string.
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
    Scrape the schedule for *config* and sync the results into Google Calendar.

    For each scraped game one of three actions is taken:

    * **exact match** — the event already exists at the correct time; individual
      fields (name, color, description, location) are patched if they have drifted.
    * **reschedule** — an event exists on the same date but at a different time;
      the existing event is patched with the new time and other details.
    * **create** — no matching event found; a new event is inserted.

    Args:
        gclient: Authenticated Google Calendar client.
        scraper: HTTP scraper client.
        config: Calendar configuration (name, URL, color ID).
    """
    # --- Scrape ---
    html_content = scraper.get_html(config.url)
    game_data = scraper.scrape_events(html_content=html_content, parse_type="ssb")

    # --- Part 1: find or create the calendar ---
    logger.log("MAJOR", IMPORTANT_STUFF_1)
    calendar_id = get_or_create_calendar(gclient, config.name, config.url)

    # --- Part 2: compare scraped games against existing calendar events ---
    logger.log("MAJOR", IMPORTANT_STUFF_2)

    all_events = gclient.list_events(calendar_id=calendar_id)
    schedule_events = filter_events_by_schedule(all_events, config.url)

    if not schedule_events:
        logger.debug("Calendar is empty — inserting all scraped games")
        for game in game_data:
            round_name, tip_off, finish, venue, details_url = get_game_details(game)
            _create_event(gclient, calendar_id, round_name, tip_off, finish, venue, config.url, config.color_id)
        logger.success(f"Finished syncing '{config.name}'")
        return

    logger.debug("Calendar not empty — diffing scraped games against existing events")
    events_simple = simplify_existing_events(schedule_events)

    for game in game_data:
        round_name, tip_off, finish, venue, details_url = get_game_details(game)
        action, event_id = determine_sync_action(tip_off, config.url, events_simple)

        if action == "exact":
            logger.info(f"[{round_name}] already exists — checking for stale fields...")
            event_details = gclient.get_event_details(calendar_id=calendar_id, event_id=event_id)
            apply_field_patches(
                gclient=gclient,
                calendar_id=calendar_id,
                event_id=event_id,
                event_details=event_details,
                round_name=round_name,
                color_id=config.color_id,
                details_url=details_url,
                venue=venue,
            )

        elif action == "reschedule":
            logger.info(f"[{round_name}] has been rescheduled — patching time...")
            patch = build_patch_payload(round_name, tip_off, finish, config.color_id, details_url)
            gclient.patch_event(calendar_id=calendar_id, event_id=event_id, patched_fields=patch)
            logger.info(f"\tEvent [{round_name}] updated to new time [{tip_off}] - id [{event_id}]")

        else:  # "create"
            _create_event(
                gclient, calendar_id, round_name, tip_off, finish, venue,
                config.url, config.color_id, details_url,
            )

    logger.success(f"Finished syncing '{config.name}'")


def _create_event(
    gclient: GoogleCalClient,
    calendar_id: str,
    round_name: str,
    tip_off: str,
    finish: str,
    venue: str,
    schedule_url: str,
    color_id: int,
    description: str = "",
) -> None:
    """Insert a new Google Calendar event and log the result."""
    logger.info(f"[{round_name}] is a new event — creating...")
    event_id = gclient.create_event(
        calendar_id=calendar_id,
        event_name=round_name,
        start_time=tip_off,
        end_time=finish,
        location=venue,
        private_properties={"schedule": schedule_url},
        color_id=color_id,
        description=description,
    )
    logger.success(f"\tEvent [{event_id}] created for [{round_name}]")


def main() -> None:
    """Entry point: load .env, configure logging, build clients, load configs, and run sync."""
    # Load .env if present — values already set in the environment take precedence
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

    for config in configs:
        try:
            sync_calendar(gclient=gclient, scraper=scraper, config=config)
        except Exception:
            logger.exception(f"Failed to sync calendar '{config.name}'")

    logger.log("MAJOR", IMPORTANT_STUFF_3)


if __name__ == "__main__":
    main()

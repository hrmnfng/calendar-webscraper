"""
Shared data models for the scrape → sync pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class ScrapeError(RuntimeError):
    """Raised when a source cannot produce any games for a config."""


@dataclass(frozen=True)
class Game:
    """A single scheduled game, normalized from any source."""

    key: str            # stable identity within one schedule, e.g. "round1"
    title: str          # event summary, e.g. "Round 1: baby dragons 2025 s4"
    start: datetime     # timezone-aware (Australia/Sydney)
    end: datetime       # timezone-aware
    venue: str
    details_url: str

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Game.start and Game.end must be timezone-aware datetimes")


@dataclass(frozen=True)
class ExistingEvent:
    """A lightweight view of a Google Calendar event for diffing."""

    id: str
    key: str | None     # gameKey extended property; None for legacy events
    start: datetime     # timezone-aware (offset as returned by GCal; may differ from Game.start's zone — aware datetime equality still compares instants)

    def __post_init__(self) -> None:
        if self.start.tzinfo is None:
            raise ValueError("ExistingEvent.start must be a timezone-aware datetime")

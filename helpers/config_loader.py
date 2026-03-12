"""
Loads and validates YAML calendar configuration files from a directory.

Active configs must be named ``config-*.yaml``. Files ending in
``.yaml.disable`` are silently skipped, making it easy to toggle calendars
without deleting files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator

import yaml
from loguru import logger


@dataclass
class CalendarConfig:
    """Represents a single calendar configuration entry."""

    name: str
    url: str
    color_id: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Calendar config 'name' must not be empty")
        if not self.url:
            raise ValueError("Calendar config 'url' must not be empty")
        if not isinstance(self.color_id, int) or not (1 <= self.color_id <= 11):
            raise ValueError(
                f"Calendar config 'color_id' must be an integer between 1 and 11, "
                f"got {self.color_id!r}"
            )


def load_configs(config_dir: str) -> list[CalendarConfig]:
    """
    Load all active calendar configs from *config_dir*.

    A file is active when its name matches ``config-*.yaml`` (files ending in
    ``.yaml.disable`` are ignored).

    Args:
        config_dir: Path to the directory containing ``config-*.yaml`` files.

    Returns:
        List of :class:`CalendarConfig` objects, one per active config file.

    Raises:
        FileNotFoundError: If *config_dir* does not exist.
        SystemExit: If no active config files are found.
    """
    if not os.path.isdir(config_dir):
        raise FileNotFoundError(
            f'Config directory not found: "{config_dir}". '
            'Please ensure the "calendar-configs" folder exists in the root directory.'
        )

    configs = list(_iter_configs(config_dir))

    if not configs:
        raise SystemExit(
            f'No active config files found in "{config_dir}". '
            'Please add at least one "config-*.yaml" file.'
        )

    return configs


def _iter_configs(config_dir: str) -> Iterator[CalendarConfig]:
    """Yield a :class:`CalendarConfig` for every active file in *config_dir*."""
    for filename in sorted(os.listdir(config_dir)):
        if not (filename.startswith("config-") and filename.endswith(".yaml")):
            continue

        file_path = os.path.join(config_dir, filename)
        logger.debug(f"Loading config file: {file_path}")

        with open(file_path, "r") as fh:
            raw = yaml.safe_load(fh)

        if not isinstance(raw, dict):
            logger.warning(
                f"Skipping {filename}: expected a YAML mapping, got {type(raw).__name__}"
            )
            continue

        try:
            config = CalendarConfig(
                name=raw.get("name", ""),
                url=raw.get("url", ""),
                color_id=int(raw.get("color_id", 0)),
            )
        except (ValueError, TypeError) as exc:
            logger.warning(f"Skipping {filename}: {exc}")
            continue

        logger.info(f"Loaded config: [{config.name}] from {filename}")
        yield config

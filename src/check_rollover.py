"""
CLI: check every active calendar config for a newer season team post and
rewrite stale URLs in place, writing a markdown summary for the PR body.

Run from the repo root: ``uv run python src/check_rollover.py``.

Always exits 0 when the check ran to completion — the workflow detects
changes via ``git diff``, not the exit code. Per-config errors are logged
and reported as "skipped"; they never abort the other configs. Needs no
Google credentials (public WP API only).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from helpers.rollover import RolloverResult, build_summary, check_config_rollover
from libs.scraper_client import ScraperClient

CONFIG_DIR = Path("./calendar-configs")
SUMMARY_PATH = Path("rollover-summary.md")


def main() -> None:
    client = ScraperClient("Season Checker")
    results: list[RolloverResult] = []

    for config_path in sorted(CONFIG_DIR.glob("config-*.yaml")):
        try:
            result = check_config_rollover(client, config_path)
        except Exception as exc:
            logger.exception(f"Rollover check failed for {config_path.name}")
            result = RolloverResult(config_path.name, "skipped", f"error: {exc}")
        results.append(result)
        logger.info(f"{result.config_file}: {result.status} — {result.detail}")

    SUMMARY_PATH.write_text(build_summary(results), encoding="utf-8")
    updated = [r for r in results if r.status == "updated"]
    logger.info(f"{len(updated)}/{len(results)} config(s) updated")


if __name__ == "__main__":
    main()

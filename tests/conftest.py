"""
pytest configuration for the calendar-webscraper test suite.

Loguru writes to the real stderr file descriptor by default, which bypasses
pytest's capsys capture.  This module provides a ``loguru_messages`` fixture
that collects loguru log records into a list so tests can assert on warning
output without relying on capsys or caplog.
"""

from __future__ import annotations

import sys
from typing import Generator

import pytest
from loguru import logger


@pytest.fixture()
def loguru_messages() -> Generator[list[str], None, None]:
    """
    Collect all loguru messages emitted during a test into a list of strings.

    Usage::

        def test_something(loguru_messages):
            some_function_that_logs()
            assert any("expected text" in m for m in loguru_messages)
    """
    messages: list[str] = []

    def _sink(message) -> None:
        messages.append(message)

    sink_id = logger.add(_sink, format="{message}", level="WARNING")
    yield messages
    logger.remove(sink_id)

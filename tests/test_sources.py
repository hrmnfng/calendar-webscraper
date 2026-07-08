"""
Unit tests for helpers.sources — key normalization, WP API source,
HTML source wrapper, and fallback behaviour.
"""

from __future__ import annotations

import pytest

from helpers.sources import normalize_round_key, round_label_from_slug


class TestNormalizeRoundKey:

    def test_round_number(self):
        assert normalize_round_key("Round 1") == "round1"

    def test_case_and_spacing_insensitive(self):
        assert normalize_round_key("SEMI FINALS") == normalize_round_key("Semi Finals")

    def test_strips_non_alphanumerics(self):
        assert normalize_round_key("Grand-Final!") == "grandfinal"


class TestRoundLabelFromSlug:

    def test_numbered_round(self):
        slug = "leteam-vs-baby-dragons-2025-s4-r1"
        assert round_label_from_slug(slug) == "Round 1"

    def test_double_digit_round(self):
        slug = "arn2-denver-chicken-nuggets-vs-leteam-2026-s1-r10"
        assert round_label_from_slug(slug) == "Round 10"

    def test_semi_finals(self):
        slug = "shake-shaq-vs-leteam-2025-s4-semi-finals"
        assert round_label_from_slug(slug) == "Semi Finals"

    def test_grand_final(self):
        slug = "untouchaballs-vs-leteam-2026-s1-grand-final"
        assert round_label_from_slug(slug) == "Grand Final"

    def test_unrecognized_slug_returns_none(self):
        assert round_label_from_slug("some-random-page") is None

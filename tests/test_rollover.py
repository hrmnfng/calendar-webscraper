"""
Unit tests for helpers.rollover — season rollover detection and config rewrite.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from helpers.rollover import (
    RolloverResult,
    base_team_name,
    build_summary,
    check_config_rollover,
    find_newest_team_post,
    rewrite_config_url,
)


def _post(slug: str, title: str, date: str) -> dict:
    return {"slug": slug, "title": {"rendered": title}, "date": date}


CONFIG_TEXT = (
    'name: "LeTeam"\n'
    'url: "https://sydneysocialbasketball.com.au/team/leteam-12/"\n'
    "color_id: 9\n"
)


class TestBaseTeamName:
    def test_strips_regular_season(self):
        assert base_team_name("LeTeam 2025 s4") == "LeTeam"

    def test_strips_preseason_suffix(self):
        assert base_team_name("LeTeam 2026 s1 preseason") == "LeTeam"

    def test_unescapes_entities(self):
        assert base_team_name("40s &amp; Shorties 2025 s4") == "40s & Shorties"

    def test_no_season_suffix_returns_none(self):
        assert base_team_name("The LeTeam") is None


class TestFindNewestTeamPost:
    def test_picks_newest_by_date(self):
        posts = [
            _post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04"),
            _post("leteam-14", "LeTeam 2026 s1", "2026-04-13T11:16:45"),
        ]
        assert find_newest_team_post(posts, "LeTeam")["slug"] == "leteam-14"

    def test_preseason_posts_count_as_newer(self):
        posts = [
            _post("leteam-14", "LeTeam 2026 s1", "2026-04-13T11:16:45"),
            _post("leteam-15", "LeTeam 2026 s2 preseason", "2026-07-01T09:00:00"),
        ]
        assert find_newest_team_post(posts, "LeTeam")["slug"] == "leteam-15"

    def test_fuzzy_search_hits_excluded_by_prefix(self):
        posts = [_post("the-leteam", "The LeTeam 2025 s2", "2025-04-02T08:43:50")]
        assert find_newest_team_post(posts, "LeTeam") is None

    def test_empty_returns_none(self):
        assert find_newest_team_post([], "LeTeam") is None

    def test_name_with_ampersand_matches_prefix(self):
        posts = [
            _post("40s-shorties-9", "40s &amp; Shorties 2025 s4", "2025-12-12T11:19:04"),
        ]
        assert find_newest_team_post(posts, "40s & Shorties")["slug"] == "40s-shorties-9"


class TestRewriteConfigUrl:
    def test_replaces_url_preserving_other_lines(self, tmp_path):
        path = tmp_path / "config-leteam.yaml"
        path.write_text(CONFIG_TEXT)
        rewrite_config_url(
            path, "https://sydneysocialbasketball.com.au/team/leteam-14/"
        )
        text = path.read_text()
        assert 'url: "https://sydneysocialbasketball.com.au/team/leteam-14/"' in text
        assert 'name: "LeTeam"' in text
        assert "color_id: 9" in text


class TestBuildSummary:
    def test_renders_table_row_per_result(self):
        results = [
            RolloverResult("config-leteam.yaml", "updated", "leteam-12 → leteam-14"),
            RolloverResult("config-shake-shaq.yaml", "unchanged", "already newest"),
        ]
        summary = build_summary(results)
        assert "| `config-leteam.yaml` | updated | leteam-12 → leteam-14 |" in summary
        assert "| `config-shake-shaq.yaml` | unchanged | already newest |" in summary

    def test_pipe_in_detail_is_escaped(self):
        results = [RolloverResult("config-x.yaml", "skipped", "weird | title")]
        assert "weird \\| title" in build_summary(results)


class TestCheckConfigRollover:
    def _client(self, current_posts: list, search_pages: list[list]) -> MagicMock:
        """Fake ScraperClient: first get_json call resolves the current slug,
        subsequent calls are the paginated search pages."""
        client = MagicMock()
        client.get_json.side_effect = [current_posts] + search_pages
        return client

    def _config(self, tmp_path) -> Path:
        path = tmp_path / "config-leteam.yaml"
        path.write_text(CONFIG_TEXT)
        return path

    def test_updates_stale_config(self, tmp_path):
        path = self._config(tmp_path)
        client = self._client(
            [_post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04")],
            [[
                _post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04"),
                _post("leteam-14", "LeTeam 2026 s1", "2026-04-13T11:16:45"),
            ]],
        )
        result = check_config_rollover(client, path)
        assert result.status == "updated"
        assert "leteam-12" in result.detail and "leteam-14" in result.detail
        assert "team/leteam-14/" in path.read_text()

    def test_unchanged_when_already_newest(self, tmp_path):
        path = self._config(tmp_path)
        client = self._client(
            [_post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04")],
            [[_post("leteam-12", "LeTeam 2025 s4", "2025-12-12T11:19:04")]],
        )
        result = check_config_rollover(client, path)
        assert result.status == "unchanged"
        assert "team/leteam-12/" in path.read_text()  # file untouched

    def test_skips_when_slug_not_found_on_site(self, tmp_path):
        path = self._config(tmp_path)
        client = self._client([], [])
        result = check_config_rollover(client, path)
        assert result.status == "skipped"
        assert "leteam-12" in result.detail

    def test_skips_when_title_has_no_season_suffix(self, tmp_path):
        path = self._config(tmp_path)
        client = self._client(
            [_post("leteam-12", "Some Oddball Title", "2025-12-12T11:19:04")], []
        )
        result = check_config_rollover(client, path)
        assert result.status == "skipped"

"""
Unit tests for helpers.config_loader.

Uses tmp_path (pytest built-in) to write real YAML files into a temp directory,
keeping tests hermetic without touching the real calendar-configs/ folder.
"""

from __future__ import annotations

import os

import pytest
import yaml

from helpers.config_loader import CalendarConfig, load_configs

VALID_CONFIG = {
    "name": "Test Calendar",
    "url": "https://ssb.com/team/test/",
    "color_id": 5,
}


def _write_yaml(directory: str, filename: str, data: dict) -> str:
    path = os.path.join(directory, filename)
    with open(path, "w") as fh:
        yaml.dump(data, fh)
    return path


# ---------------------------------------------------------------------------
# CalendarConfig dataclass validation
# ---------------------------------------------------------------------------

class TestCalendarConfig:
    def test_valid_config(self):
        cfg = CalendarConfig(name="Cal", url="https://example.com", color_id=3)
        assert cfg.name == "Cal"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            CalendarConfig(name="", url="https://example.com", color_id=1)

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="url"):
            CalendarConfig(name="Cal", url="", color_id=1)

    def test_color_id_zero_raises(self):
        with pytest.raises(ValueError, match="color_id"):
            CalendarConfig(name="Cal", url="https://example.com", color_id=0)

    def test_color_id_twelve_raises(self):
        with pytest.raises(ValueError, match="color_id"):
            CalendarConfig(name="Cal", url="https://example.com", color_id=12)

    @pytest.mark.parametrize("color_id", [1, 5, 11])
    def test_valid_color_ids(self, color_id):
        cfg = CalendarConfig(name="Cal", url="https://example.com", color_id=color_id)
        assert cfg.color_id == color_id


# ---------------------------------------------------------------------------
# load_configs — directory errors
# ---------------------------------------------------------------------------

class TestLoadConfigsDirectoryErrors:
    def test_missing_directory_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Config directory not found"):
            load_configs(str(tmp_path / "nonexistent"))

    def test_empty_directory_raises_system_exit(self, tmp_path):
        with pytest.raises(SystemExit):
            load_configs(str(tmp_path))


# ---------------------------------------------------------------------------
# load_configs — file filtering
# ---------------------------------------------------------------------------

class TestLoadConfigsFileFiltering:
    def test_loads_valid_yaml(self, tmp_path):
        _write_yaml(str(tmp_path), "config-test.yaml", VALID_CONFIG)
        configs = load_configs(str(tmp_path))
        assert len(configs) == 1
        assert configs[0].name == "Test Calendar"

    def test_skips_disabled_files(self, tmp_path):
        _write_yaml(str(tmp_path), "config-active.yaml", VALID_CONFIG)
        _write_yaml(str(tmp_path), "config-disabled.yaml.disable", VALID_CONFIG)
        assert len(load_configs(str(tmp_path))) == 1

    def test_skips_template_file(self, tmp_path):
        _write_yaml(str(tmp_path), "_config-template.yaml", VALID_CONFIG)
        _write_yaml(str(tmp_path), "config-real.yaml", VALID_CONFIG)
        assert len(load_configs(str(tmp_path))) == 1

    def test_skips_non_yaml_files(self, tmp_path):
        _write_yaml(str(tmp_path), "config-valid.yaml", VALID_CONFIG)
        (tmp_path / "README.md").write_text("hello")
        assert len(load_configs(str(tmp_path))) == 1

    def test_loads_multiple_active_configs(self, tmp_path):
        for i in range(3):
            _write_yaml(
                str(tmp_path), f"config-team-{i}.yaml",
                {"name": f"Team {i}", "url": f"https://example.com/{i}", "color_id": i + 1},
            )
        assert len(load_configs(str(tmp_path))) == 3

    def test_sorted_filename_order(self, tmp_path):
        _write_yaml(str(tmp_path), "config-zzz.yaml", {**VALID_CONFIG, "name": "ZZZ"})
        _write_yaml(str(tmp_path), "config-aaa.yaml", {**VALID_CONFIG, "name": "AAA"})
        configs = load_configs(str(tmp_path))
        assert configs[0].name == "AAA"
        assert configs[1].name == "ZZZ"


# ---------------------------------------------------------------------------
# load_configs — malformed files skipped gracefully
# ---------------------------------------------------------------------------

class TestLoadConfigsMalformedFiles:
    def test_skips_invalid_color_id(self, tmp_path):
        _write_yaml(str(tmp_path), "config-bad.yaml", {"name": "Bad", "url": "https://x.com", "color_id": 99})
        _write_yaml(str(tmp_path), "config-good.yaml", VALID_CONFIG)
        configs = load_configs(str(tmp_path))
        assert len(configs) == 1
        assert configs[0].name == "Test Calendar"

    def test_skips_file_missing_name(self, tmp_path):
        _write_yaml(str(tmp_path), "config-bad.yaml", {"url": "https://x.com", "color_id": 3})
        _write_yaml(str(tmp_path), "config-good.yaml", VALID_CONFIG)
        assert len(load_configs(str(tmp_path))) == 1

    def test_all_bad_files_raises_system_exit(self, tmp_path):
        _write_yaml(str(tmp_path), "config-bad.yaml", {"url": "https://x.com", "color_id": 99})
        with pytest.raises(SystemExit):
            load_configs(str(tmp_path))

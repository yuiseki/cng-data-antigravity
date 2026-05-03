from __future__ import annotations

from pathlib import Path

import pytest

from cng_data_antigravity.config import DEFAULT_CONFIG_NAME, resolve_config_path


def test_resolve_config_path_defaults_to_escape_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / DEFAULT_CONFIG_NAME
    config_path.write_text("aoi:\n  bbox: [0, 0, 1, 1]\nextracts: []\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path(None) == config_path.resolve()


def test_resolve_config_path_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        resolve_config_path(None)

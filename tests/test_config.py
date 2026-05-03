from __future__ import annotations

from pathlib import Path

import pytest

from cng_data_antigravity.config import DEFAULT_CONFIG_NAME, default_outputs, resolve_config_path


def test_resolve_config_path_defaults_to_escape_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / DEFAULT_CONFIG_NAME
    config_path.write_text("aoi:\n  bbox: [0, 0, 1, 1]\nextracts: []\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path(None) == config_path.resolve()


def test_resolve_config_path_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        resolve_config_path(None)


def test_default_outputs_pmtiles():
    outputs = default_outputs({"type": "pmtiles", "url": "https://example.com/x.pmtiles"}, "osm-jp")
    assert len(outputs) == 1
    assert outputs[0].format == "pmtiles"
    assert outputs[0].path == "osm-jp.pmtiles"


def test_default_outputs_geofabrik():
    outputs = default_outputs({"type": "geofabrik", "region": "kanto"}, "kanto")
    assert len(outputs) == 1
    assert outputs[0].format == "osm.pbf"
    assert outputs[0].path == "kanto.osm.pbf"


def test_default_outputs_stac_cog():
    outputs = default_outputs({"type": "stac-cog"}, "sentinel2-tokyo")
    assert len(outputs) == 1
    assert outputs[0].format == "geotiff"
    assert outputs[0].path == "sentinel2-tokyo.tif"


def test_default_outputs_overture_single_type():
    outputs = default_outputs({"type": "overture", "overtureType": "building"}, "tokyo-buildings")
    assert len(outputs) == 1
    assert outputs[0].format == "geoparquet"
    assert outputs[0].path == "tokyo-buildings.parquet"


def test_default_outputs_overture_multi_type():
    outputs = default_outputs(
        {"type": "overture", "overtureTypes": ["building", "place", "segment"]},
        "overture-tokyo",
    )
    assert len(outputs) == 1
    assert outputs[0].format == "geoparquet"
    # extract_id is the directory; path is relative to output_dir, so just {type}.parquet
    assert outputs[0].path == "{type}.parquet"

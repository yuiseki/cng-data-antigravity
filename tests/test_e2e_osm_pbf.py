"""E2E tests for the osm-pbf adapter using small Geofabrik regions.

Monaco (~663 KB PBF) and Niue (~412 KB PBF) are the smallest regions
available on Geofabrik, making them suitable for fast end-to-end tests
that exercise the full download → bbox extract pipeline.

These tests make real network requests and are skipped when the
SKIP_NETWORK_TESTS environment variable is set.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from cng_data_antigravity.adapters.osm_pbf import run_osm_pbf_extract
from cng_data_antigravity.config import AOIConfig, OutputConfig, load_config
from cng_data_antigravity.runner import run_escape
from cng_data_antigravity.sources import BUILTIN_SOURCES

network = pytest.mark.skipif(
    os.environ.get("SKIP_NETWORK_TESTS") == "1",
    reason="SKIP_NETWORK_TESTS=1",
)

# Monaco bbox (entire principality, ~2 km²)
_MONACO_BBOX = [7.39, 43.72, 7.44, 43.76]
# Niue bbox (entire island, ~260 km²)
_NIUE_BBOX = [-169.97, -19.18, -169.78, -18.93]


@network
def test_osm_pbf_monaco_downloads_and_extracts(tmp_path: Path) -> None:
    """Full pipeline: resolve Geofabrik index → download Monaco PBF → bbox extract."""
    source = {
        "type": "osm-pbf",
        "indexUrl": "https://download.geofabrik.de/index-v1.json",
        "region": "monaco",
    }
    output_path = tmp_path / "monaco.osm.pbf"

    source_info, _ = run_osm_pbf_extract(
        source,
        AOIConfig(bbox=_MONACO_BBOX),
        OutputConfig(format="osm.pbf", path="monaco.osm.pbf"),
        output_path,
        force=False,
        prev_meta=None,
        work_dir=tmp_path,
    )

    assert output_path.exists(), "output file was not created"
    assert output_path.stat().st_size > 0, "output file is empty"
    assert source_info["type"] == "osm-pbf"
    assert source_info["region"] == "monaco"
    assert "pbfUrl" in source_info
    assert "monaco" in source_info["pbfUrl"]
    # Cache file must also exist
    cache = tmp_path / ".cache" / "osm-pbf" / "monaco-latest.osm.pbf"
    assert cache.exists()


@network
def test_osm_pbf_niue_downloads_and_extracts(tmp_path: Path) -> None:
    """Full pipeline for Niue — smallest available Geofabrik region (~412 KB)."""
    source = {
        "type": "osm-pbf",
        "indexUrl": "https://download.geofabrik.de/index-v1.json",
        "region": "niue",
    }
    output_path = tmp_path / "niue.osm.pbf"

    source_info, _ = run_osm_pbf_extract(
        source,
        AOIConfig(bbox=_NIUE_BBOX),
        OutputConfig(format="osm.pbf", path="niue.osm.pbf"),
        output_path,
        force=False,
        prev_meta=None,
        work_dir=tmp_path,
    )

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert source_info["region"] == "niue"


@network
def test_osm_pbf_skips_download_when_source_unchanged(tmp_path: Path) -> None:
    """Second run with unchanged source must not re-download the PBF."""
    source = {
        "type": "osm-pbf",
        "indexUrl": "https://download.geofabrik.de/index-v1.json",
        "region": "monaco",
    }
    aoi = AOIConfig(bbox=_MONACO_BBOX)
    output_cfg = OutputConfig(format="osm.pbf", path="monaco.osm.pbf")
    output_path = tmp_path / "monaco.osm.pbf"

    # First run — downloads
    source_info, _ = run_osm_pbf_extract(
        source, aoi, output_cfg, output_path, force=False, prev_meta=None, work_dir=tmp_path,
    )
    cache = tmp_path / ".cache" / "osm-pbf" / "monaco-latest.osm.pbf"
    mtime_after_first = cache.stat().st_mtime_ns

    # Second run — same etag/lastModified → must skip download
    run_osm_pbf_extract(
        source, aoi, output_cfg, output_path, force=False, prev_meta={"sourceInfo": source_info}, work_dir=tmp_path,
    )
    assert cache.stat().st_mtime_ns == mtime_after_first, "cache file was re-downloaded on second run"


@network
def test_builtin_source_osm_monaco_is_registered() -> None:
    """osm-monaco must be in BUILTIN_SOURCES and resolve to osm-pbf adapter."""
    assert "osm-monaco" in BUILTIN_SOURCES
    src = BUILTIN_SOURCES["osm-monaco"]
    assert src.adapter == "osm-pbf"
    assert src.config["region"] == "monaco"


@network
def test_builtin_source_osm_niue_is_registered() -> None:
    assert "osm-niue" in BUILTIN_SOURCES
    src = BUILTIN_SOURCES["osm-niue"]
    assert src.adapter == "osm-pbf"
    assert src.config["region"] == "niue"


@network
def test_e2e_monaco_via_escape_yaml(tmp_path: Path) -> None:
    """Full escape.yaml → run_escape pipeline for Monaco."""
    escape_yaml = tmp_path / "escape.yaml"
    escape_yaml.write_text(
        "aoi:\n"
        f"  bbox: {_MONACO_BBOX}\n"
        "extracts:\n"
        "  - source: osm-monaco\n",
        encoding="utf-8",
    )

    config = load_config(escape_yaml)
    run_escape(config, config_path=escape_yaml)

    output = tmp_path / "output" / "osm-monaco" / "osm-monaco.osm.pbf"
    metadata = tmp_path / "output" / "osm-monaco" / "metadata.json"
    assert output.exists(), f"output not found: {output}"
    assert output.stat().st_size > 0
    assert metadata.exists()

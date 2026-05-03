"""True E2E tests for the osm-pbf adapter.

Each network test writes an escape.yaml, invokes the CLI as a subprocess
(`cng-data-antigravity run <escape.yaml>`), and asserts on the resulting
output files and metadata.json — no Python API is called directly.

Monaco (~663 KB PBF) and Niue (~412 KB PBF) are the smallest regions on
Geofabrik, keeping download time short.

Note: freshness-skip behaviour (second run does not re-download when source
is unchanged) is covered by unit tests in test_osm_pbf_adapter.py, not here,
because it requires mocking HEAD responses to guarantee stable server state.

Skip all network tests with:  SKIP_NETWORK_TESTS=1 pytest
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cng_data_antigravity.sources import BUILTIN_SOURCES

_CLI = Path(sys.executable).parent / "cng-data-antigravity"

network = pytest.mark.skipif(
    os.environ.get("SKIP_NETWORK_TESTS") == "1",
    reason="SKIP_NETWORK_TESTS=1",
)

_MONACO_BBOX = [7.39, 43.72, 7.44, 43.76]
_NIUE_BBOX = [-169.97, -19.18, -169.78, -18.93]


def _run_cli(escape_yaml: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_CLI, "run", str(escape_yaml)],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Built-in source registration (no network needed)
# ---------------------------------------------------------------------------

def test_builtin_source_osm_monaco_is_registered() -> None:
    assert "osm-monaco" in BUILTIN_SOURCES
    src = BUILTIN_SOURCES["osm-monaco"]
    assert src.adapter == "osm-pbf"
    assert src.config["region"] == "monaco"


def test_builtin_source_osm_niue_is_registered() -> None:
    assert "osm-niue" in BUILTIN_SOURCES
    src = BUILTIN_SOURCES["osm-niue"]
    assert src.adapter == "osm-pbf"
    assert src.config["region"] == "niue"


# ---------------------------------------------------------------------------
# True E2E: CLI subprocess → escape.yaml → output files
# ---------------------------------------------------------------------------

@network
def test_e2e_cli_monaco(tmp_path: Path) -> None:
    """cng-data-antigravity run escape.yaml → output/osm-monaco/ for Monaco."""
    escape_yaml = tmp_path / "escape.yaml"
    escape_yaml.write_text(
        f"aoi:\n  bbox: {_MONACO_BBOX}\nextracts:\n  - source: osm-monaco\n",
        encoding="utf-8",
    )

    result = _run_cli(escape_yaml)
    assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

    output = tmp_path / "output" / "osm-monaco" / "osm-monaco.osm.pbf"
    metadata_path = tmp_path / "output" / "osm-monaco" / "metadata.json"
    assert output.exists(), f"output not found: {output}"
    assert output.stat().st_size > 0

    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert meta["id"] == "osm-monaco"
    assert meta["source"]["type"] == "osm-pbf"
    assert meta["source"]["region"] == "monaco"
    assert len(meta["outputs"]) == 1
    assert meta["outputs"][0]["format"] == "osm.pbf"
    assert meta["sourceInfo"]["pbfUrl"].endswith("monaco-latest.osm.pbf")


@network
def test_e2e_cli_niue(tmp_path: Path) -> None:
    """cng-data-antigravity run escape.yaml → output/osm-niue/ for Niue."""
    escape_yaml = tmp_path / "escape.yaml"
    escape_yaml.write_text(
        f"aoi:\n  bbox: {_NIUE_BBOX}\nextracts:\n  - source: osm-niue\n",
        encoding="utf-8",
    )

    result = _run_cli(escape_yaml)
    assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

    output = tmp_path / "output" / "osm-niue" / "osm-niue.osm.pbf"
    metadata_path = tmp_path / "output" / "osm-niue" / "metadata.json"
    assert output.exists()
    assert output.stat().st_size > 0

    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert meta["id"] == "osm-niue"
    assert meta["source"]["region"] == "niue"
    assert meta["sourceInfo"]["pbfUrl"].endswith("niue-latest.osm.pbf")


@network
def test_e2e_cli_second_run_is_idempotent(tmp_path: Path) -> None:
    """Second CLI run exits 0 and produces the same output file."""
    escape_yaml = tmp_path / "escape.yaml"
    escape_yaml.write_text(
        f"aoi:\n  bbox: {_MONACO_BBOX}\nextracts:\n  - source: osm-monaco\n",
        encoding="utf-8",
    )

    result1 = _run_cli(escape_yaml)
    assert result1.returncode == 0, result1.stderr

    output = tmp_path / "output" / "osm-monaco" / "osm-monaco.osm.pbf"
    size_after_first = output.stat().st_size

    result2 = _run_cli(escape_yaml)
    assert result2.returncode == 0, result2.stderr
    assert output.stat().st_size == size_after_first

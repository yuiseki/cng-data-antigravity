"""Unit tests for the osm-pbf adapter.

All tests are network-free (HEAD and download are monkeypatched).
Freshness-skip behaviour is tested here; the true E2E (CLI subprocess)
is in test_e2e_osm_pbf.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from cng_data_antigravity.adapters import osm_pbf as osm_pbf_adapter
from cng_data_antigravity.adapters.osm_pbf import run_osm_pbf_extract
from cng_data_antigravity.config import AOIConfig, OutputConfig

_AOI = AOIConfig(bbox=[7.39, 43.72, 7.44, 43.76])
_OUTPUT_CFG = OutputConfig(format="osm.pbf", path="out.osm.pbf")

# Simulated HTTP response headers (keys match urllib's lowercased header names)
_FAKE_HEADERS = {
    "etag": '"abc123"',
    "last-modified": "Sat, 01 Jan 2026 00:00:00 GMT",
    "content-length": "12345",
}
_SOURCE = {
    "type": "osm-pbf",
    "indexUrl": "https://download.geofabrik.de/index-v1.json",
    "region": "monaco",
}
_RESOLVED_URL = "https://download.geofabrik.de/europe/monaco-latest.osm.pbf"
# sourceInfo as written to metadata.json by the adapter (camelCase keys)
_FAKE_SOURCE_INFO = {
    "type": "osm-pbf",
    "pbfUrl": _RESOLVED_URL,
    "lastModified": "Sat, 01 Jan 2026 00:00:00 GMT",
    "etag": '"abc123"',
    "contentLength": "12345",
    "region": "monaco",
}


def _make_fake_pbf(path: Path) -> None:
    """Write a minimal valid-looking file so osmium doesn't get called."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 64)


@pytest.fixture()
def stub_network(monkeypatch, tmp_path):
    """Stub out all network calls and osmium extraction."""
    monkeypatch.setattr(osm_pbf_adapter, "_resolve_pbf_url", lambda _: _RESOLVED_URL)
    monkeypatch.setattr(osm_pbf_adapter, "head", lambda _: _FAKE_HEADERS)

    def fake_download(url, dest):
        _make_fake_pbf(dest)

    monkeypatch.setattr(osm_pbf_adapter, "_download_pbf", fake_download)
    monkeypatch.setattr(osm_pbf_adapter, "_osmium_extract", lambda src, dst, bbox: _make_fake_pbf(dst))
    return tmp_path


def test_osm_pbf_downloads_and_extracts_on_first_run(stub_network, tmp_path):
    output_path = tmp_path / "out.osm.pbf"

    source_info, _ = run_osm_pbf_extract(
        _SOURCE, _AOI, _OUTPUT_CFG, output_path,
        force=False, prev_meta=None, work_dir=tmp_path,
    )

    assert output_path.exists()
    assert source_info["type"] == "osm-pbf"
    assert source_info["region"] == "monaco"
    assert source_info["pbfUrl"] == _RESOLVED_URL
    assert source_info["etag"] == _FAKE_HEADERS["etag"]


def test_osm_pbf_skips_download_when_etag_unchanged(stub_network, tmp_path, monkeypatch):
    """Second call with same etag must not trigger _download_pbf."""
    # Pre-populate the cache file
    cache = tmp_path / ".cache" / "osm-pbf" / "monaco-latest.osm.pbf"
    _make_fake_pbf(cache)
    output_path = tmp_path / "out.osm.pbf"
    _make_fake_pbf(output_path)

    download_calls: list[str] = []
    extract_calls: list[str] = []
    monkeypatch.setattr(osm_pbf_adapter, "_download_pbf", lambda u, d: download_calls.append(u))
    monkeypatch.setattr(osm_pbf_adapter, "_osmium_extract", lambda s, d, b: extract_calls.append(str(d)))

    prev_meta = {"sourceInfo": _FAKE_SOURCE_INFO}

    run_osm_pbf_extract(
        _SOURCE, _AOI, _OUTPUT_CFG, output_path,
        force=False, prev_meta=prev_meta, work_dir=tmp_path,
    )

    assert download_calls == [], "re-downloaded despite same etag"
    assert extract_calls == [], "re-extracted despite unchanged source"


def test_osm_pbf_redownloads_when_etag_changed(stub_network, tmp_path, monkeypatch):
    """Changed etag must trigger re-download and re-extract."""
    cache = tmp_path / ".cache" / "osm-pbf" / "monaco-latest.osm.pbf"
    _make_fake_pbf(cache)
    output_path = tmp_path / "out.osm.pbf"
    _make_fake_pbf(output_path)

    download_calls: list[str] = []
    extract_calls: list[str] = []
    monkeypatch.setattr(osm_pbf_adapter, "_download_pbf", lambda u, d: download_calls.append(u))
    monkeypatch.setattr(osm_pbf_adapter, "_osmium_extract", lambda s, d, b: extract_calls.append(str(d)))

    # prev_meta has a different etag → source changed
    prev_meta = {"sourceInfo": {"etag": '"old-etag"', "lastModified": "", "contentLength": ""}}

    run_osm_pbf_extract(
        _SOURCE, _AOI, _OUTPUT_CFG, output_path,
        force=False, prev_meta=prev_meta, work_dir=tmp_path,
    )

    assert download_calls != [], "expected re-download when etag changed"
    assert extract_calls != [], "expected re-extract when etag changed"


def test_osm_pbf_force_flag_redownloads_always(stub_network, tmp_path, monkeypatch):
    """--force must re-download and re-extract even when etag is unchanged."""
    cache = tmp_path / ".cache" / "osm-pbf" / "monaco-latest.osm.pbf"
    _make_fake_pbf(cache)
    output_path = tmp_path / "out.osm.pbf"
    _make_fake_pbf(output_path)

    download_calls: list[str] = []
    extract_calls: list[str] = []
    monkeypatch.setattr(osm_pbf_adapter, "_download_pbf", lambda u, d: download_calls.append(u))
    monkeypatch.setattr(osm_pbf_adapter, "_osmium_extract", lambda s, d, b: extract_calls.append(str(d)))

    prev_meta = {"sourceInfo": _FAKE_SOURCE_INFO}

    run_osm_pbf_extract(
        _SOURCE, _AOI, _OUTPUT_CFG, output_path,
        force=True, prev_meta=prev_meta, work_dir=tmp_path,
    )

    assert download_calls != [], "force flag did not trigger re-download"
    assert extract_calls != [], "force flag did not trigger re-extract"

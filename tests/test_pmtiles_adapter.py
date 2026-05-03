from __future__ import annotations

from pathlib import Path

from pmtiles.reader import MmapSource, Reader
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import write

from cng_data_antigravity.adapters import pmtiles as pmtiles_adapter
from cng_data_antigravity.config import AOIConfig, OutputConfig


def _create_fixture_pmtiles(path: Path) -> None:
    header = {
        "tile_type": TileType.MVT,
        "tile_compression": Compression.NONE,
        "min_lon_e7": int(-180 * 1e7),
        "min_lat_e7": int(-85 * 1e7),
        "max_lon_e7": int(180 * 1e7),
        "max_lat_e7": int(85 * 1e7),
        "center_zoom": 0,
        "center_lon_e7": 0,
        "center_lat_e7": 0,
        "min_zoom": 0,
        "max_zoom": 1,
    }
    metadata = {
        "name": "fixture",
        "format": "pbf",
        "bounds": "-180,-85,180,85",
        "center": "0,0,0",
        "minzoom": "0",
        "maxzoom": "1",
    }
    with write(path) as writer:
        writer.write_tile(zxy_to_tileid(0, 0, 0), b"root")
        writer.write_tile(zxy_to_tileid(1, 0, 0), b"nw")
        writer.write_tile(zxy_to_tileid(1, 1, 0), b"ne")
        writer.write_tile(zxy_to_tileid(1, 0, 1), b"sw")
        writer.write_tile(zxy_to_tileid(1, 1, 1), b"se")
        writer.finalize(header, metadata)


def _read_pmtiles(path: Path) -> Reader:
    file_obj = path.open("rb")
    try:
        return Reader(MmapSource(file_obj))
    finally:
        file_obj.close()


def test_run_pmtiles_extract_uses_python_api_for_local_file(tmp_path: Path) -> None:
    source_path = tmp_path / "source.pmtiles"
    _create_fixture_pmtiles(source_path)
    output_path = tmp_path / "subset.pmtiles"

    source_info, _ = pmtiles_adapter.run_pmtiles_extract(
        {"type": "pmtiles", "url": str(source_path)},
        AOIConfig(bbox=[-180.0, 1.0, -1.0, 85.0]),
        OutputConfig(format="pmtiles", path="subset.pmtiles"),
        output_path,
        False,
        None,
    )

    assert source_info["type"] == "pmtiles"
    assert output_path.exists()

    output_file = output_path.open("rb")
    try:
        reader = Reader(MmapSource(output_file))
        assert reader.get(0, 0, 0) == b"root"
        assert reader.get(1, 0, 0) == b"nw"
        assert reader.get(1, 1, 0) is None
        assert reader.get(1, 0, 1) is None
        assert reader.get(1, 1, 1) is None
    finally:
        output_file.close()


def test_run_pmtiles_extract_skips_unchanged_local_source(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "source.pmtiles"
    _create_fixture_pmtiles(source_path)
    output_path = tmp_path / "subset.pmtiles"
    output_path.write_bytes(b"already-here")

    calls: list[str] = []

    def fake_extract(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append("extract")

    monkeypatch.setattr(pmtiles_adapter, "_extract_pmtiles_subset", fake_extract)

    prev_meta = {
        "sourceInfo": {
            "fileSize": source_path.stat().st_size,
            "mtimeNs": source_path.stat().st_mtime_ns,
        }
    }
    source_info, _ = pmtiles_adapter.run_pmtiles_extract(
        {"type": "pmtiles", "url": str(source_path)},
        AOIConfig(bbox=[-180.0, 1.0, -1.0, 85.0]),
        OutputConfig(format="pmtiles", path="subset.pmtiles"),
        output_path,
        False,
        prev_meta,
    )

    assert source_info["fileSize"] == source_path.stat().st_size
    assert calls == []
    assert output_path.read_bytes() == b"already-here"

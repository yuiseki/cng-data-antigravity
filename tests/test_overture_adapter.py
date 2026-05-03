from __future__ import annotations

from pathlib import Path

from cng_data_antigravity.adapters import overture as overture_adapter
from cng_data_antigravity.config import AOIConfig, OutputConfig


def test_overture_adapter_uses_python_api_and_writes_state(tmp_path: Path, monkeypatch):
    calls: list[tuple[str, object]] = []

    class DummyReader:
        schema = "dummy-schema"

    class DummyWriter:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyState:
        def __init__(self, **kwargs):
            self._data = kwargs
            self.last_release = kwargs["last_release"]
            self.type = kwargs["type"]
            self.output = kwargs["output"]

        def as_dict(self):
            return dict(self._data)

    monkeypatch.setattr(overture_adapter, "get_latest_release", lambda: "2026-05-01.0")
    monkeypatch.setattr(
        overture_adapter,
        "record_batch_reader",
        lambda overture_type, bbox=None, release=None, stac=False: calls.append(
            ("record_batch_reader", (overture_type, bbox, release, stac))
        )
        or DummyReader(),
    )
    monkeypatch.setattr(
        overture_adapter,
        "get_writer",
        lambda output_format, path, schema: calls.append(("get_writer", (output_format, path, schema))) or DummyWriter(),
    )
    monkeypatch.setattr(
        overture_adapter,
        "copy",
        lambda reader, writer: calls.append(("copy", (reader, writer))),
    )
    monkeypatch.setattr(overture_adapter, "get_state_path", lambda output: Path(f"{output}.state"))
    monkeypatch.setattr(overture_adapter, "load_state", lambda path: None)
    monkeypatch.setattr(overture_adapter, "PipelineState", DummyState)
    saved: dict[str, object] = {}

    def fake_save_state(state, path):
        saved["state"] = state.as_dict()
        saved["path"] = str(path)

    monkeypatch.setattr(overture_adapter, "save_state", fake_save_state)

    source_info, source_state = overture_adapter.run_overture_extract(
        {"type": "overture", "overtureType": "building"},
        AOIConfig(bbox=[139.0, 35.0, 140.0, 36.0]),
        OutputConfig(format="geoparquet", path="buildings.parquet"),
        tmp_path / "buildings.parquet",
        force=False,
    )

    assert source_info == {"type": "overture", "release": "2026-05-01.0"}
    assert source_state is not None
    assert saved["state"]["type"] == "building"
    assert saved["state"]["theme"] == "buildings"
    assert calls[0][0] == "record_batch_reader"
    assert calls[1][0] == "get_writer"
    assert calls[2][0] == "copy"

from __future__ import annotations

from pathlib import Path

import pytest
from overturemaps.models import BBox, PipelineState

from cng_data_antigravity.adapters import overture as overture_adapter
from cng_data_antigravity.config import ALL_OVERTURE_TYPES, AOIConfig, OutputConfig

_AOI = AOIConfig(bbox=[139.0, 35.0, 140.0, 36.0])


def _make_stubs(monkeypatch, called_types=None):
    """Patch out all overturemaps I/O; return a list that records called types."""
    if called_types is None:
        called_types = []

    class DummyReader:
        schema = "dummy-schema"

    class DummyWriter:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(overture_adapter, "get_latest_release", lambda: "2026-05-01.0")
    monkeypatch.setattr(
        overture_adapter,
        "record_batch_reader",
        lambda overture_type, **kw: called_types.append(overture_type) or DummyReader(),
    )
    monkeypatch.setattr(
        overture_adapter, "get_writer",
        lambda *a, **kw: DummyWriter(),
    )
    monkeypatch.setattr(overture_adapter, "copy", lambda *a: None)
    monkeypatch.setattr(overture_adapter, "get_state_path", lambda p: Path(f"{p}.state"))
    monkeypatch.setattr(overture_adapter, "load_state", lambda p: None)
    return called_types


def test_overture_adapter_uses_python_api_and_writes_state(tmp_path: Path, monkeypatch):
    calls: list[str] = []
    _make_stubs(monkeypatch)

    saved: dict = {}

    def fake_save_state(state, path):
        calls.append("save_state")
        saved["state"] = state
        saved["path"] = str(path)

    monkeypatch.setattr(overture_adapter, "save_state", fake_save_state)

    source_info, source_state = overture_adapter.run_overture_extract(
        {"type": "overture", "overtureType": "building"},
        _AOI,
        OutputConfig(format="geoparquet", path="buildings.parquet"),
        tmp_path / "buildings.parquet",
        force=False,
    )

    assert source_info == {"type": "overture", "release": "2026-05-01.0"}
    assert source_state is not None
    assert source_state["type"] == "building"
    assert source_state["theme"] == "buildings"
    assert "save_state" in calls


def test_overture_adapter_bbox_is_dataclass_not_dict(tmp_path: Path, monkeypatch):
    """Regression: PipelineState.bbox must be BBox, not a plain dict.

    Previously the adapter passed a dict literal for bbox, causing:
        AttributeError: 'dict' object has no attribute 'as_dict'
    when save_state (or state.as_dict()) was called.
    """
    _make_stubs(monkeypatch)

    captured_states: list[PipelineState] = []

    def fake_save_state(state, path):
        captured_states.append(state)

    monkeypatch.setattr(overture_adapter, "save_state", fake_save_state)

    overture_adapter.run_overture_extract(
        {"type": "overture", "overtureType": "building"},
        _AOI,
        OutputConfig(format="geoparquet", path="out.parquet"),
        tmp_path / "out.parquet",
        force=False,
    )

    assert len(captured_states) == 1
    state = captured_states[0]
    # bbox must be the BBox dataclass so as_dict() doesn't raise AttributeError
    assert isinstance(state.bbox, BBox), f"expected BBox, got {type(state.bbox)}"
    # as_dict() must not raise — this was the original crash
    result = state.as_dict()
    assert result["bbox"] == {"xmin": 139.0, "ymin": 35.0, "xmax": 140.0, "ymax": 36.0}


def test_overture_adapter_falls_back_to_all_types_when_none_specified(tmp_path: Path, monkeypatch):
    """Regression: no overtureType/overtureTypes should use ALL_OVERTURE_TYPES, not raise.

    Previously the adapter raised:
        ValueError: overture source requires overtureType or overtureTypes
    when neither key was present in the source config.
    """
    called_types: list[str] = []
    _make_stubs(monkeypatch, called_types)
    monkeypatch.setattr(overture_adapter, "save_state", lambda *a: None)

    # No type specified → must not raise
    overture_adapter.run_overture_extract(
        {"type": "overture"},
        _AOI,
        OutputConfig(format="geoparquet", path="{type}.parquet"),
        tmp_path / "{type}.parquet",
        force=False,
    )

    assert set(called_types) == set(ALL_OVERTURE_TYPES)


def test_overture_adapter_overtureTypes_list(tmp_path: Path, monkeypatch):
    """overtureTypes list processes exactly the requested types."""
    called_types: list[str] = []
    _make_stubs(monkeypatch, called_types)
    monkeypatch.setattr(overture_adapter, "save_state", lambda *a: None)

    overture_adapter.run_overture_extract(
        {"type": "overture", "overtureTypes": ["building", "place"]},
        _AOI,
        OutputConfig(format="geoparquet", path="{type}.parquet"),
        tmp_path / "{type}.parquet",
        force=False,
    )

    assert called_types == ["building", "place"]

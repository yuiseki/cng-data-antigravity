from __future__ import annotations

import json
from pathlib import Path

from cng_data_antigravity.cli import main
from cng_data_antigravity.runner import SOURCE_HANDLERS


def test_run_uses_default_escape_yaml_and_writes_metadata(tmp_path: Path, monkeypatch):
    (tmp_path / "escape.yaml").write_text(
        """
aoi:
  bbox: [139.0, 35.0, 140.0, 36.0]
extracts:
  - id: demo
    source:
      type: dummy
    outputs:
      - format: geoparquet
        path: demo.parquet
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def dummy_handler(source, aoi, output, output_path, force):  # noqa: ANN001
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("dummy", encoding="utf-8")
        return {"type": "dummy", "checkedAt": "now"}, {"ok": True}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(SOURCE_HANDLERS, "dummy", dummy_handler)
    try:
        assert main(["run"]) == 0
    finally:
        SOURCE_HANDLERS.pop("dummy", None)

    # Convention: output/{extract.id}/ for both data and metadata
    output_file = tmp_path / "output" / "demo" / "demo.parquet"
    metadata_file = tmp_path / "output" / "demo" / "metadata.json"
    assert output_file.exists()
    assert metadata_file.exists()
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["id"] == "demo"
    assert metadata["source"]["type"] == "dummy"
    assert metadata["sourceState"] == {"ok": True}

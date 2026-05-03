from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cng_data_antigravity.config import AOIConfig, ExtractConfig

DEFAULT_ATTRIBUTION: dict[str, str] = {
    "overture": "© Overture Maps Foundation contributors, available under CDLA Permissive 2.0",
    "pmtiles": "© OpenStreetMap contributors, available under ODbL",
    "geofabrik": "© OpenStreetMap contributors, available under ODbL. Data provided by Geofabrik GmbH.",
    "stac-cog": "Contains modified Copernicus Sentinel data. Accessed via Microsoft Planetary Computer.",
}


def read_prev_metadata(output_dir: Path) -> dict[str, Any] | None:
    meta_path = output_dir / "metadata.json"
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_metadata(
    *,
    extract: ExtractConfig,
    aoi: AOIConfig,
    output_dir: Path,
    resolved_output_paths: list[str],
    started_at: datetime,
    completed_at: datetime,
    source_info: dict[str, Any] | None = None,
    source_state: dict[str, Any] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": extract.id,
        "extractedAt": completed_at.astimezone(timezone.utc).isoformat(),
        "durationSeconds": round((completed_at - started_at).total_seconds(), 3),
        "source": extract.source,
        "sourceInfo": source_info,
        "sourceState": source_state,
        "aoi": asdict(aoi),
        "outputs": [
            {"format": output.format, "path": path}
            for output, path in zip(extract.outputs, resolved_output_paths, strict=False)
        ],
        "attribution": extract.attribution or DEFAULT_ATTRIBUTION.get(extract.source["type"], ""),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

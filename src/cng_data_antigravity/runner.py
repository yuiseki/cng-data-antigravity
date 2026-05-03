from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cng_data_antigravity.adapters import (
    run_geofabrik_extract,
    run_overture_extract,
    run_pmtiles_extract,
    run_stac_cog_extract,
)
from cng_data_antigravity.config import EscapeConfig, default_outputs
from cng_data_antigravity.metadata import read_prev_metadata, write_metadata

Handler = Callable[..., tuple[dict[str, Any] | None, dict[str, Any] | None]]

SOURCE_HANDLERS: dict[str, Handler] = {
    "overture": run_overture_extract,
    "pmtiles": run_pmtiles_extract,
    "geofabrik": run_geofabrik_extract,
    "stac-cog": run_stac_cog_extract,
}


def run_escape(config: EscapeConfig, *, config_path: Path, force: bool = False) -> None:
    work_dir = config_path.parent
    for extract in config.extracts:
        source_type = extract.source["type"]
        started_at = datetime.now(timezone.utc)

        # Convention: metadata always lives at output/{source_type}/{id}/metadata.json
        output_dir = work_dir / "output" / source_type / extract.id
        output_dir.mkdir(parents=True, exist_ok=True)

        prev_meta = read_prev_metadata(output_dir)
        handler = SOURCE_HANDLERS.get(source_type)
        if handler is None:
            raise ValueError(f"unknown source type: {source_type!r}")

        # Use explicitly declared outputs, or fall back to convention defaults
        outputs = extract.outputs or default_outputs(extract.source, extract.id)

        resolved_output_paths: list[str] = []
        source_info: dict[str, Any] | None = None
        source_state: dict[str, Any] | None = None

        for output in outputs:
            if extract.outputs is not None:
                # Explicit: path is relative to output_dir (backward-compatible)
                output_path = output_dir / output.path
            else:
                # Convention: path is relative to output/{source_type}/
                output_path = work_dir / "output" / source_type / output.path
            resolved_output_paths.append(str(output_path))

            if source_type == "overture":
                source_info, source_state = handler(
                    extract.source, config.aoi, output, output_path, force,
                )
            elif source_type == "pmtiles":
                source_info, source_state = handler(
                    extract.source, config.aoi, output, output_path, force, prev_meta,
                )
            elif source_type == "geofabrik":
                source_info, source_state = handler(
                    extract.source, config.aoi, output, output_path, force, prev_meta, work_dir,
                )
            elif source_type == "stac-cog":
                source_info, source_state = handler(
                    extract.source, config.aoi, output, output_path, force, prev_meta,
                )
            else:
                source_info, source_state = handler(
                    extract.source, config.aoi, output, output_path, force,
                )

        completed_at = datetime.now(timezone.utc)
        write_metadata(
            extract=extract,
            aoi=config.aoi,
            output_dir=output_dir,
            resolved_output_paths=resolved_output_paths,
            started_at=started_at,
            completed_at=completed_at,
            source_info=source_info,
            source_state=source_state,
        )

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
from cng_data_antigravity.config import EscapeConfig
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
        started_at = datetime.now(timezone.utc)
        output_dir = work_dir / "output" / extract.id
        output_dir.mkdir(parents=True, exist_ok=True)
        prev_meta = read_prev_metadata(output_dir)
        handler = SOURCE_HANDLERS.get(extract.source["type"])
        if handler is None:
            raise ValueError(f'unknown source type: {extract.source["type"]}')

        resolved_output_paths: list[str] = []
        source_info: dict[str, Any] | None = None
        source_state: dict[str, Any] | None = None

        for output in extract.outputs:
            output_path = output_dir / output.path
            resolved_output_paths.append(str(output_path))
            if extract.source["type"] == "overture":
                source_info, source_state = handler(
                    extract.source,
                    config.aoi,
                    output,
                    output_path,
                    force,
                )
            elif extract.source["type"] == "pmtiles":
                source_info, source_state = handler(
                    extract.source,
                    config.aoi,
                    output,
                    output_path,
                    force,
                    prev_meta,
                )
            elif extract.source["type"] == "geofabrik":
                source_info, source_state = handler(
                    extract.source,
                    config.aoi,
                    output,
                    output_path,
                    force,
                    prev_meta,
                    work_dir,
                )
            elif extract.source["type"] == "stac-cog":
                source_info, source_state = handler(
                    extract.source,
                    config.aoi,
                    output,
                    output_path,
                    force,
                    prev_meta,
                )
            else:
                source_info, source_state = handler(
                    extract.source,
                    config.aoi,
                    output,
                    output_path,
                    force,
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

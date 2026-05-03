from __future__ import annotations

from pathlib import Path
from typing import Any

from overturemaps import record_batch_reader
from overturemaps.cli import type_theme_map
from overturemaps.models import Backend, PipelineState
from overturemaps.releases import get_latest_release
from overturemaps.state import get_state_path, load_state, save_state
from overturemaps.writers import copy, get_writer

from cng_data_antigravity.adapters.common import utc_now
from cng_data_antigravity.config import AOIConfig, OutputConfig

def run_overture_extract(
    source: dict[str, Any],
    aoi: AOIConfig,
    output: OutputConfig,
    output_path: Path,
    force: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if output.format != "geoparquet":
        raise ValueError("overture source only supports geoparquet output")

    overture_types = source.get("overtureTypes") or ([source["overtureType"]] if source.get("overtureType") else [])
    if not overture_types:
        raise ValueError("overture source requires overtureType or overtureTypes")

    release = source.get("release") or get_latest_release()
    source_state: dict[str, Any] | None = None

    for overture_type in overture_types:
        theme = type_theme_map.get(overture_type)
        if theme is None:
            raise ValueError(f"unknown Overture type: {overture_type}")
        typed_path = Path(str(output_path).replace("{type}", overture_type))
        typed_path.parent.mkdir(parents=True, exist_ok=True)
        state_path = get_state_path(str(typed_path))
        prev_state = load_state(state_path) if typed_path.exists() and not force else None
        if (
            prev_state is not None
            and prev_state.last_release == release
            and prev_state.type == overture_type
            and prev_state.output == str(typed_path)
        ):
            source_state = prev_state.as_dict()
            continue

        reader = record_batch_reader(
            overture_type,
            bbox=tuple(aoi.bbox),
            release=source.get("release"),
            stac=True,
        )
        if reader is None:
            raise ValueError(f"no Overture rows found for type={overture_type} bbox={aoi.bbox}")

        with get_writer("geoparquet", str(typed_path), schema=reader.schema) as writer:
            copy(reader, writer)

        state = PipelineState(
            last_release=release,
            last_run=utc_now(),
            theme=theme,
            type=overture_type,
            bbox={
                "xmin": aoi.bbox[0],
                "ymin": aoi.bbox[1],
                "xmax": aoi.bbox[2],
                "ymax": aoi.bbox[3],
            },
            backend=Backend.geoparquet,
            output=str(typed_path),
        )
        save_state(state, state_path)
        source_state = state.as_dict()

    return {"type": "overture", "release": release}, source_state

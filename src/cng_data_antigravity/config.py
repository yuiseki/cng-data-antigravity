from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_NAME = "escape.yaml"

# Convention: default format per source type
_DEFAULT_FORMAT: dict[str, str] = {
    "overture": "geoparquet",
    "pmtiles": "pmtiles",
    "geofabrik": "osm.pbf",
    "stac-cog": "geotiff",
}

# Convention: file extension per format
_FORMAT_EXT: dict[str, str] = {
    "geoparquet": ".parquet",
    "pmtiles": ".pmtiles",
    "osm.pbf": ".osm.pbf",
    "geotiff": ".tif",
}


@dataclass(slots=True)
class AOIConfig:
    bbox: list[float]


@dataclass(slots=True)
class OutputConfig:
    format: str
    path: str


@dataclass(slots=True)
class ExtractConfig:
    id: str
    source: dict[str, Any]
    outputs: list[OutputConfig] | None = None  # None → use convention defaults
    attribution: str | None = None


@dataclass(slots=True)
class EscapeConfig:
    aoi: AOIConfig
    extracts: list[ExtractConfig]


def default_outputs(source: dict[str, Any], extract_id: str) -> list[OutputConfig]:
    """Return convention-based outputs when none are specified in escape.yaml."""
    source_type = source["type"]
    fmt = _DEFAULT_FORMAT.get(source_type)
    if fmt is None:
        raise ValueError(f"unknown source type: {source_type!r}")
    ext = _FORMAT_EXT[fmt]

    if source_type == "overture":
        overture_types = source.get("overtureTypes") or (
            [source["overtureType"]] if source.get("overtureType") else []
        )
        if len(overture_types) > 1:
            # Multi-type: one file per type under {id}/ subdir using {type} template
            return [OutputConfig(format=fmt, path=f"{extract_id}/{{type}}{ext}")]
        # Single type: flat file
        return [OutputConfig(format=fmt, path=f"{extract_id}{ext}")]

    return [OutputConfig(format=fmt, path=f"{extract_id}{ext}")]


def resolve_config_path(config_path: str | None, cwd: Path | None = None) -> Path:
    base = cwd or Path.cwd()
    resolved = (base / DEFAULT_CONFIG_NAME) if config_path is None else Path(config_path)
    resolved = resolved.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"escape config not found: {resolved}")
    return resolved


def load_config(config_path: Path) -> EscapeConfig:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("escape config must be a mapping")
    aoi = data.get("aoi")
    extracts = data.get("extracts")
    if not isinstance(aoi, dict) or not isinstance(aoi.get("bbox"), list) or len(aoi["bbox"]) != 4:
        raise ValueError("aoi.bbox must be a 4-number list")
    if not isinstance(extracts, list) or not extracts:
        raise ValueError("extracts must be a non-empty list")

    parsed_extracts: list[ExtractConfig] = []
    for item in extracts:
        if not isinstance(item, dict):
            raise ValueError("extract entry must be a mapping")
        outputs_raw = item.get("outputs")
        outputs: list[OutputConfig] | None = None
        if outputs_raw is not None:
            if not isinstance(outputs_raw, list) or not outputs_raw:
                raise ValueError("extract.outputs must be a non-empty list when specified")
            outputs = [OutputConfig(format=o["format"], path=o["path"]) for o in outputs_raw]
        parsed_extracts.append(
            ExtractConfig(
                id=item["id"],
                source=item["source"],
                outputs=outputs,
                attribution=item.get("attribution"),
            )
        )
    return EscapeConfig(aoi=AOIConfig(bbox=aoi["bbox"]), extracts=parsed_extracts)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_NAME = "escape.yaml"

# Convention: default format per adapter
_DEFAULT_FORMAT: dict[str, str] = {
    "overture": "geoparquet",
    "pmtiles": "pmtiles",
    "osm-pbf": "osm.pbf",
    "stac-cog": "geotiff",
    "stac-static-cog": "stac-catalog",
}

# Convention: file extension per format
_FORMAT_EXT: dict[str, str] = {
    "geoparquet": ".parquet",
    "pmtiles": ".pmtiles",
    "osm.pbf": ".osm.pbf",
    "geotiff": ".tif",
    "stac-catalog": ".json",
}

# Default Overture types when overtureTypes is not specified
ALL_OVERTURE_TYPES: list[str] = [
    "address",
    "bathymetry",
    "building",
    "building_part",
    "division",
    "division_area",
    "division_boundary",
    "place",
    "segment",
    "connector",
    "infrastructure",
    "land",
    "land_cover",
    "land_use",
    "water",
]


@dataclass(slots=True)
class AOIConfig:
    bbox: list[float]


@dataclass(slots=True)
class OutputConfig:
    format: str
    path: str


@dataclass(slots=True)
class SourceDef:
    """Named source definition from the sources: section."""
    adapter: str           # adapter type: "pmtiles", "geofabrik", "overture", "stac-cog"
    config: dict[str, Any]  # adapter-specific config (url, region, stacApiUrl, etc.)


@dataclass(slots=True)
class ExtractConfig:
    source: str             # source name (key in EscapeConfig.sources) or adapter type for inline
    id: str                 # output id; defaults to source name
    overrides: dict[str, Any]  # per-extract overrides (e.g. datetime, maxCloudCover for stac-cog)
    inline_source: dict[str, Any] | None  # set when source is inline dict (legacy/explicit)
    outputs: list[OutputConfig] | None   # None → convention defaults
    attribution: str | None


@dataclass(slots=True)
class EscapeConfig:
    aoi: AOIConfig
    sources: dict[str, SourceDef]
    extracts: list[ExtractConfig]


def resolve_source(extract: ExtractConfig, sources: dict[str, SourceDef]) -> dict[str, Any]:
    """Return the effective source dict for an extract (adapter type + merged config).

    Resolution order:
    1. Inline source dict (legacy explicit form)
    2. Built-in source registry (cng_data_antigravity.sources)
    3. User-defined sources section in escape.yaml
    """
    if extract.inline_source is not None:
        # Legacy inline form: source: {type: ..., ...}
        return {**extract.inline_source, **extract.overrides}

    # Import here to avoid circular imports; BUILTIN_SOURCES is populated on import
    from cng_data_antigravity.sources import BUILTIN_SOURCES

    source_def = BUILTIN_SOURCES.get(extract.source) or sources.get(extract.source)
    if source_def is None:
        raise ValueError(
            f"source {extract.source!r} not found. "
            f"Built-in sources: {sorted(BUILTIN_SOURCES)}. "
            f"Defined in escape.yaml sources section: {sorted(sources)}."
        )
    return {"type": source_def.adapter, **source_def.config, **extract.overrides}


def default_outputs(effective_source: dict[str, Any], extract_id: str) -> list[OutputConfig]:
    """Return convention-based outputs for the given adapter type and extract id."""
    adapter = effective_source["type"]

    if adapter == "stac-static-cog":
        # Output is a self-describing static STAC catalog directory; the
        # catalog.json is its canonical entry point (COGs live alongside it).
        return [OutputConfig(format="stac-catalog", path="catalog.json")]

    fmt = _DEFAULT_FORMAT.get(adapter)
    if fmt is None:
        raise ValueError(f"unknown adapter type: {adapter!r}")
    ext = _FORMAT_EXT[fmt]

    if adapter == "overture":
        overture_types = (
            effective_source.get("overtureTypes")
            or ([effective_source["overtureType"]] if effective_source.get("overtureType") else [])
            or ALL_OVERTURE_TYPES
        )
        if len(overture_types) > 1:
            return [OutputConfig(format=fmt, path=f"{{type}}{ext}")]
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

    aoi_raw = data.get("aoi")
    if not isinstance(aoi_raw, dict) or not isinstance(aoi_raw.get("bbox"), list) or len(aoi_raw["bbox"]) != 4:
        raise ValueError("aoi.bbox must be a 4-element list")

    # Parse named sources (optional section)
    sources: dict[str, SourceDef] = {}
    for name, src_raw in (data.get("sources") or {}).items():
        if not isinstance(src_raw, dict) or "adapter" not in src_raw:
            raise ValueError(f"sources.{name} must have an 'adapter' key")
        adapter = src_raw["adapter"]
        cfg = {k: v for k, v in src_raw.items() if k != "adapter"}
        sources[name] = SourceDef(adapter=adapter, config=cfg)

    extracts_raw = data.get("extracts")
    if not isinstance(extracts_raw, list) or not extracts_raw:
        raise ValueError("extracts must be a non-empty list")

    parsed_extracts: list[ExtractConfig] = []
    for item in extracts_raw:
        if not isinstance(item, dict):
            raise ValueError("extract entry must be a mapping")

        source_raw = item.get("source")
        if source_raw is None:
            raise ValueError("extract entry must have a 'source' key")

        inline_source: dict[str, Any] | None = None
        source_name: str

        if isinstance(source_raw, dict):
            # Inline form: source: {type: pmtiles, url: ...}
            inline_source = source_raw
            source_name = source_raw.get("type", "unknown")
        elif isinstance(source_raw, str):
            # Named reference: source: osm-jp
            source_name = source_raw
        else:
            raise ValueError("extract.source must be a string (source name) or a mapping")

        # id defaults to source name
        extract_id = item.get("id") or source_name

        # Everything else in the extract dict (except known keys) is an override
        known_keys = {"id", "source", "outputs", "attribution"}
        overrides = {k: v for k, v in item.items() if k not in known_keys}

        outputs_raw = item.get("outputs")
        outputs: list[OutputConfig] | None = None
        if outputs_raw is not None:
            if not isinstance(outputs_raw, list) or not outputs_raw:
                raise ValueError("extract.outputs must be a non-empty list when specified")
            outputs = [OutputConfig(format=o["format"], path=o["path"]) for o in outputs_raw]

        parsed_extracts.append(ExtractConfig(
            source=source_name,
            id=extract_id,
            overrides=overrides,
            inline_source=inline_source,
            outputs=outputs,
            attribution=item.get("attribution"),
        ))

    return EscapeConfig(
        aoi=AOIConfig(bbox=aoi_raw["bbox"]),
        sources=sources,
        extracts=parsed_extracts,
    )

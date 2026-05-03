from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_NAME = "escape.yaml"


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
    outputs: list[OutputConfig]
    attribution: str | None = None


@dataclass(slots=True)
class EscapeConfig:
    aoi: AOIConfig
    extracts: list[ExtractConfig]


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
        if not isinstance(outputs_raw, list) or not outputs_raw:
            raise ValueError("extract.outputs must be a non-empty list")
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

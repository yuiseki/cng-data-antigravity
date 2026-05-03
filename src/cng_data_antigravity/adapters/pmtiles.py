from __future__ import annotations

from pathlib import Path
from typing import Any

from cng_data_antigravity.adapters.common import head, run_subprocess, utc_now
from cng_data_antigravity.config import AOIConfig, OutputConfig


def run_pmtiles_extract(
    source: dict[str, Any],
    aoi: AOIConfig,
    output: OutputConfig,
    output_path: Path,
    force: bool,
    prev_meta: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if output.format != "pmtiles":
        raise ValueError("pmtiles source only supports pmtiles output")
    headers = head(source["url"])
    source_info = {
        "type": "pmtiles",
        "url": source["url"],
        "lastModified": headers.get("last-modified", ""),
        "etag": headers.get("etag", ""),
        "contentLength": headers.get("content-length", ""),
        "checkedAt": utc_now(),
    }
    prev_info = (prev_meta or {}).get("sourceInfo") or {}
    unchanged = (
        output_path.exists()
        and not force
        and (
            (source_info["etag"] and source_info["etag"] == prev_info.get("etag"))
            or (source_info["lastModified"] and source_info["lastModified"] == prev_info.get("lastModified"))
            or (source_info["contentLength"] and source_info["contentLength"] == prev_info.get("contentLength"))
        )
    )
    if not unchanged:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["pmtiles", "extract", source["url"], str(output_path), f"--bbox={','.join(str(v) for v in aoi.bbox)}"]
        if source.get("minzoom") is not None:
            cmd.append(f"--minzoom={source['minzoom']}")
        if source.get("maxzoom") is not None:
            cmd.append(f"--maxzoom={source['maxzoom']}")
        run_subprocess(cmd)
    return source_info, None

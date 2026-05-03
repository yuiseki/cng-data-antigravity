from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from cng_data_antigravity.adapters.common import head, run_subprocess, utc_now
from cng_data_antigravity.config import AOIConfig, OutputConfig

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"


def _fetch_pbf_url(region: str) -> str:
    with urlopen(GEOFABRIK_INDEX_URL, timeout=30) as response:
        index = json.load(response)
    feature = next((f for f in index["features"] if f["properties"]["id"] == region), None)
    if feature is None:
        raise ValueError(f'Geofabrik region "{region}" not found')
    return feature["properties"]["urls"]["pbf"]


def run_geofabrik_extract(
    source: dict[str, Any],
    aoi: AOIConfig,
    output: OutputConfig,
    output_path: Path,
    force: bool,
    prev_meta: dict[str, Any] | None,
    work_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if output.format != "osm.pbf":
        raise ValueError("geofabrik source only supports osm.pbf output")
    pbf_url = _fetch_pbf_url(source["region"])
    headers = head(pbf_url)
    source_info = {
        "type": "geofabrik",
        "region": source["region"],
        "pbfUrl": pbf_url,
        "lastModified": headers.get("last-modified", ""),
        "etag": headers.get("etag", ""),
        "contentLength": headers.get("content-length", ""),
        "checkedAt": utc_now(),
    }
    cache_dir = work_dir / ".cache" / "geofabrik"
    cache_dir.mkdir(parents=True, exist_ok=True)
    intermediate = cache_dir / f'{source["region"]}-latest.osm.pbf'
    prev_info = (prev_meta or {}).get("sourceInfo") or {}
    changed = force or not intermediate.exists() or (
        source_info["etag"] and source_info["etag"] != prev_info.get("etag")
    ) or (
        source_info["lastModified"] and source_info["lastModified"] != prev_info.get("lastModified")
    ) or (
        source_info["contentLength"] and source_info["contentLength"] != prev_info.get("contentLength")
    )
    if changed:
        run_subprocess(["curl", "-L", "-C", "-", "--fail", "-o", str(intermediate), pbf_url])
    if force or changed or not output_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        west, south, east, north = aoi.bbox
        run_subprocess([
            "osmium",
            "extract",
            "--bbox",
            f"{west},{south},{east},{north}",
            "--strategy",
            "complete_ways",
            "--overwrite",
            str(intermediate),
            "-o",
            str(output_path),
        ])
    return source_info, None

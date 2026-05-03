from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import osmium
import osmium.osm

from cng_data_antigravity.adapters.common import head, utc_now
from cng_data_antigravity.config import AOIConfig, OutputConfig

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"


def _fetch_pbf_url(region: str) -> str:
    with urlopen(GEOFABRIK_INDEX_URL, timeout=30) as response:
        index = json.load(response)
    feature = next((f for f in index["features"] if f["properties"]["id"] == region), None)
    if feature is None:
        raise ValueError(f'Geofabrik region "{region}" not found')
    return feature["properties"]["urls"]["pbf"]


def _download_pbf(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(".tmp")
    with urllib.request.urlopen(url) as response, tmp.open("wb") as out:
        shutil.copyfileobj(response, out)
    tmp.rename(dest)


def _osmium_extract(src: Path, dest: Path, bbox: list[float]) -> None:
    """Extract OSM data within bbox using BackReferenceWriter (complete_ways equivalent)."""
    west, south, east, north = bbox
    box = osmium.osm.Box(west, south, east, north)

    with osmium.BackReferenceWriter(dest, ref_src=src, overwrite=True) as writer:
        for obj in osmium.FileProcessor(src):
            if isinstance(obj, osmium.osm.Node):
                loc = obj.location
                if loc.valid() and box.contains(loc):
                    writer.add(obj)


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
    changed = (
        force
        or not intermediate.exists()
        or (source_info["etag"] and source_info["etag"] != prev_info.get("etag"))
        or (source_info["lastModified"] and source_info["lastModified"] != prev_info.get("lastModified"))
        or (source_info["contentLength"] and source_info["contentLength"] != prev_info.get("contentLength"))
    )

    if changed:
        print(f"  [geofabrik] downloading {pbf_url} -> {intermediate}")
        _download_pbf(pbf_url, intermediate)

    if force or changed or not output_path.exists():
        print(f"  [geofabrik] extracting bbox={aoi.bbox} -> {output_path}")
        _osmium_extract(intermediate, output_path, aoi.bbox)

    return source_info, None

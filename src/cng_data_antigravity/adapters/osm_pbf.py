"""osm-pbf adapter: download an OSM PBF file and extract a bbox subset with osmium.

Source config accepts either:
  url       — direct URL to a .osm.pbf file
  indexUrl + region — resolve URL via a GeoJSON index (Geofabrik style)
"""
from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import osmium
import osmium.osm

from cng_data_antigravity.adapters.common import head, make_request, utc_now
from cng_data_antigravity.config import AOIConfig, OutputConfig


def _resolve_pbf_url(source: dict[str, Any]) -> str:
    if "url" in source:
        return source["url"]
    index_url = source["indexUrl"]
    region = source["region"]
    with urlopen(make_request(index_url), timeout=30) as response:
        index = json.load(response)
    feature = next((f for f in index["features"] if f["properties"]["id"] == region), None)
    if feature is None:
        raise ValueError(f'region "{region}" not found in {index_url}')
    return feature["properties"]["urls"]["pbf"]


def _cache_key(source: dict[str, Any]) -> str:
    if "url" in source:
        # Derive a filename from the URL path
        return Path(urllib.parse.urlparse(source["url"]).path).stem
    return source["region"]


def _download_pbf(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(".tmp")
    with urllib.request.urlopen(make_request(url), timeout=3600) as response, tmp.open("wb") as out:
        shutil.copyfileobj(response, out)
    tmp.rename(dest)


def _osmium_extract(src: Path, dest: Path, bbox: list[float]) -> None:
    """Extract OSM data within bbox (complete_ways equivalent via BackReferenceWriter)."""
    west, south, east, north = bbox
    box = osmium.osm.Box(west, south, east, north)
    with osmium.BackReferenceWriter(dest, ref_src=src, overwrite=True) as writer:
        for obj in osmium.FileProcessor(src):
            if isinstance(obj, osmium.osm.Node):
                loc = obj.location
                if loc.valid() and box.contains(loc):
                    writer.add(obj)


def run_osm_pbf_extract(
    source: dict[str, Any],
    aoi: AOIConfig,
    output: OutputConfig,
    output_path: Path,
    force: bool,
    prev_meta: dict[str, Any] | None,
    work_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if output.format != "osm.pbf":
        raise ValueError("osm-pbf adapter only supports osm.pbf output")

    pbf_url = _resolve_pbf_url(source)
    headers = head(pbf_url)
    source_info: dict[str, Any] = {
        "type": "osm-pbf",
        "pbfUrl": pbf_url,
        "lastModified": headers.get("last-modified", ""),
        "etag": headers.get("etag", ""),
        "contentLength": headers.get("content-length", ""),
        "checkedAt": utc_now(),
    }
    if "region" in source:
        source_info["region"] = source["region"]

    cache_key = _cache_key(source)
    cache_dir = work_dir / ".cache" / "osm-pbf"
    cache_dir.mkdir(parents=True, exist_ok=True)
    intermediate = cache_dir / f"{cache_key}-latest.osm.pbf"

    prev_info = (prev_meta or {}).get("sourceInfo") or {}
    changed = (
        force
        or not intermediate.exists()
        or (source_info["etag"] and source_info["etag"] != prev_info.get("etag"))
        or (source_info["lastModified"] and source_info["lastModified"] != prev_info.get("lastModified"))
        or (source_info["contentLength"] and source_info["contentLength"] != prev_info.get("contentLength"))
    )

    if changed:
        print(f"  [osm-pbf] downloading {pbf_url} -> {intermediate}")
        _download_pbf(pbf_url, intermediate)

    if force or changed or not output_path.exists():
        print(f"  [osm-pbf] extracting bbox={aoi.bbox} -> {output_path}")
        _osmium_extract(intermediate, output_path, aoi.bbox)

    return source_info, None

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cng_data_antigravity.config import AOIConfig, OutputConfig


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _head(url: str) -> dict[str, str]:
    request = Request(url, method="HEAD")
    with urlopen(request, timeout=30) as response:
        return {k.lower(): v for k, v in response.headers.items()}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


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
    source_state: dict[str, Any] | None = None
    for overture_type in overture_types:
        typed_path = Path(str(output_path).replace("{type}", overture_type))
        typed_path.parent.mkdir(parents=True, exist_ok=True)
        if not force and typed_path.exists():
            result = subprocess.run(
                ["uvx", "overturemaps", "releases", "check", "-o", str(typed_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                continue
        cmd = [
            "uvx",
            "overturemaps",
            "download",
            "--bbox",
            ",".join(str(v) for v in aoi.bbox),
            "-f",
            "geoparquet",
            "-t",
            overture_type,
            "-o",
            str(typed_path),
        ]
        if source.get("release"):
            cmd.extend(["-r", source["release"]])
        _run(cmd)
        state_path = Path(f"{typed_path}.state")
        if state_path.exists():
            source_state = json.loads(state_path.read_text(encoding="utf-8"))
    return None, source_state


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
    headers = _head(source["url"])
    source_info = {
        "type": "pmtiles",
        "url": source["url"],
        "lastModified": headers.get("last-modified", ""),
        "etag": headers.get("etag", ""),
        "contentLength": headers.get("content-length", ""),
        "checkedAt": _utc_now(),
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
        _run(cmd)
    return source_info, None


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
    with urlopen("https://download.geofabrik.de/index-v1.json", timeout=30) as response:
        index = json.load(response)
    feature = next((f for f in index["features"] if f["properties"]["id"] == source["region"]), None)
    if feature is None:
        raise ValueError(f'Geofabrik region "{source["region"]}" not found')
    pbf_url = feature["properties"]["urls"]["pbf"]
    headers = _head(pbf_url)
    source_info = {
        "type": "geofabrik",
        "region": source["region"],
        "pbfUrl": pbf_url,
        "lastModified": headers.get("last-modified", ""),
        "etag": headers.get("etag", ""),
        "contentLength": headers.get("content-length", ""),
        "checkedAt": _utc_now(),
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
        _run(["curl", "-L", "-C", "-", "--fail", "-o", str(intermediate), pbf_url])
    if force or changed or not output_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        west, south, east, north = aoi.bbox
        _run([
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


def run_stac_cog_extract(
    source: dict[str, Any],
    aoi: AOIConfig,
    output: OutputConfig,
    output_path: Path,
    force: bool,
    prev_meta: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if output.format != "geotiff":
        raise ValueError("stac-cog source only supports geotiff output")
    west, south, east, north = aoi.bbox
    result = subprocess.run(
        [
            "uvx",
            "--from",
            "pystac-client",
            "stac-client",
            "search",
            source["stacApiUrl"],
            "--collections",
            source["collection"],
            "--bbox",
            str(west),
            str(south),
            str(east),
            str(north),
            "--datetime",
            source["datetime"],
            "--max-items",
            "20",
            "--sortby",
            "properties.eo:cloud_cover",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    features = json.loads(result.stdout)["features"]
    max_cloud = source.get("maxCloudCover", 100)
    item = next((f for f in features if (f["properties"].get("eo:cloud_cover", 0) <= max_cloud)), None)
    if item is None:
        raise ValueError("No STAC item matched maxCloudCover")
    asset_href = item["assets"][source["asset"]]["href"]
    source_info = {
        "type": "stac-cog",
        "itemId": item["id"],
        "itemDatetime": item["properties"]["datetime"],
        "cloudCover": item["properties"].get("eo:cloud_cover"),
        "assetHref": asset_href,
        "checkedAt": _utc_now(),
    }
    prev_info = (prev_meta or {}).get("sourceInfo") or {}
    if output_path.exists() and not force and source_info["itemId"] == prev_info.get("itemId"):
        return source_info, None
    if "planetarycomputer.microsoft.com" in source["stacApiUrl"]:
        with urlopen(
            f"https://planetarycomputer.microsoft.com/api/sas/v1/sign?{urlencode({'href': asset_href})}",
            timeout=30,
        ) as response:
            asset_href = json.load(response)["href"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "gdal_translate",
        f"/vsicurl/{asset_href}",
        str(output_path),
        "-projwin",
        str(west),
        str(north),
        str(east),
        str(south),
        "-projwin_srs",
        "EPSG:4326",
        "-of",
        "GTiff",
        "-co",
        "COMPRESS=LZW",
        "-co",
        "TILED=YES",
    ])
    return source_info, None

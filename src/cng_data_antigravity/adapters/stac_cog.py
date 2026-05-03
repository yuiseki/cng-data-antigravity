from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from cng_data_antigravity.adapters.common import run_subprocess, utc_now
from cng_data_antigravity.config import AOIConfig, OutputConfig


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
        "checkedAt": utc_now(),
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
    run_subprocess([
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

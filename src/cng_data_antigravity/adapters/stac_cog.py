from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import pystac_client
from osgeo import gdal

from cng_data_antigravity.adapters.common import utc_now
from cng_data_antigravity.config import AOIConfig, OutputConfig

gdal.UseExceptions()


def _search_stac(source: dict[str, Any], aoi: AOIConfig) -> Any:
    west, south, east, north = aoi.bbox
    client = pystac_client.Client.open(source["stacApiUrl"])
    results = client.search(
        collections=[source["collection"]],
        bbox=[west, south, east, north],
        datetime=source["datetime"],
        max_items=20,
        sortby=[{"field": "properties.eo:cloud_cover", "direction": "asc"}],
    )
    max_cloud = source.get("maxCloudCover", 100)
    for item in results.items():
        cloud = item.properties.get("eo:cloud_cover", 0)
        if cloud <= max_cloud:
            return item
    raise ValueError("No STAC item matched maxCloudCover")


def _sign_href(href: str, stac_api_url: str) -> str:
    if "planetarycomputer.microsoft.com" not in stac_api_url:
        return href
    with urlopen(
        f"https://planetarycomputer.microsoft.com/api/sas/v1/sign?{urlencode({'href': href})}",
        timeout=30,
    ) as response:
        return json.load(response)["href"]


def _gdal_translate_bbox(src_href: str, dest: Path, bbox: list[float]) -> None:
    west, south, east, north = bbox
    opts = gdal.TranslateOptions(
        format="GTiff",
        projWin=[west, north, east, south],
        projWinSRS="EPSG:4326",
        creationOptions=["COMPRESS=LZW", "TILED=YES"],
    )
    gdal.Translate(str(dest), f"/vsicurl/{src_href}", options=opts)


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

    item = _search_stac(source, aoi)
    asset_href = item.assets[source["asset"]].href
    source_info = {
        "type": "stac-cog",
        "itemId": item.id,
        "itemDatetime": item.properties.get("datetime"),
        "cloudCover": item.properties.get("eo:cloud_cover"),
        "assetHref": asset_href,
        "checkedAt": utc_now(),
    }

    prev_info = (prev_meta or {}).get("sourceInfo") or {}
    if output_path.exists() and not force and source_info["itemId"] == prev_info.get("itemId"):
        return source_info, None

    signed_href = _sign_href(asset_href, source["stacApiUrl"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [stac-cog] gdal_translate {item.id} -> {output_path}")
    _gdal_translate_bbox(signed_href, output_path, aoi.bbox)
    return source_info, None

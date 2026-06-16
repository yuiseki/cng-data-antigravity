"""Adapter for static STAC catalogs of COGs (no /search endpoint).

Unlike the ``stac-cog`` adapter, which queries a STAC *API* via
``pystac_client.search``, this adapter walks a static STAC catalog tree
(root Catalog -> child Collections -> ... -> Items) hosted as plain JSON
files, pruning whole subtrees by their spatial extent so only the
Collections that intersect the AOI are fetched.

Convention over configuration: by default it covers the AOI **MECE**
(mutually exclusive, collectively exhaustive). Items sharing the same
ground tile (non-overlapping grid cell) are deduplicated to the most
recent acquisition, and every ground tile intersecting the AOI is
included. The selected ``visual`` COGs are mosaicked into a single
GeoTIFF clipped to the AOI bbox.

Used by the Maxar Open Data catalog:
https://maxar-opendata.s3.amazonaws.com/events/catalog.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin
from urllib.request import urlopen

from cng_data_antigravity.adapters.common import (
    gdal_warp_mosaic_bbox,
    make_request,
    utc_now,
)
from cng_data_antigravity.config import AOIConfig, OutputConfig

Bbox = list[float]
FetchFn = Callable[[str], dict[str, Any]]


def _fetch_json(url: str) -> dict[str, Any]:
    with urlopen(make_request(url), timeout=60) as response:
        return json.load(response)


def _bbox_intersects(a: Bbox, b: Bbox) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _overall_bbox(node: dict[str, Any]) -> Bbox | None:
    """The overall spatial extent of a Collection (STAC: first bbox), if any."""
    try:
        return node["extent"]["spatial"]["bbox"][0]
    except (KeyError, IndexError, TypeError):
        return None


def _collection_id_from_href(href: str) -> str:
    parts = [p for p in href.replace("./", "").split("/") if p and not p.endswith(".json")]
    return parts[0] if parts else ""


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None


def _within_interval(item_dt: str | None, interval: str | None) -> bool:
    if not interval:
        return True
    item = _parse_dt(item_dt)
    if item is None:
        return True

    def _aware(dt: datetime) -> datetime:
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    item = _aware(item)
    start_s, _, end_s = interval.partition("/")
    start = _parse_dt(start_s)
    end = _parse_dt(end_s)
    if start and item < _aware(start):
        return False
    if end and item > _aware(end):
        return False
    return True


def _collect_items(
    node: dict[str, Any],
    node_url: str,
    aoi_bbox: Bbox,
    fetch: FetchFn,
    out: list[tuple[dict[str, Any], str]],
) -> None:
    """Recurse a Catalog/Collection, pruning subtrees that miss the AOI."""
    bbox = _overall_bbox(node)
    if bbox is not None and not _bbox_intersects(bbox, aoi_bbox):
        return
    for link in node.get("links", []):
        rel = link.get("rel")
        href = link.get("href")
        if not href:
            continue
        url = urljoin(node_url, href)
        if rel == "child":
            _collect_items(fetch(url), url, aoi_bbox, fetch, out)
        elif rel == "item":
            item = fetch(url)
            item_bbox = item.get("bbox")
            if item_bbox and _bbox_intersects(item_bbox, aoi_bbox):
                out.append((item, url))


def find_aoi_items(
    catalog_url: str,
    aoi_bbox: Bbox,
    *,
    collection: str | None = None,
    datetime_filter: str | None = None,
    fetch: FetchFn = _fetch_json,
) -> list[tuple[dict[str, Any], str]]:
    """Find all items in a static STAC catalog whose bbox intersects the AOI.

    ``collection`` restricts the walk to a single top-level child collection
    (matched by the directory segment of its href). ``datetime_filter`` is an
    ISO 8601 interval (``start/end``) applied to each item's datetime.
    """
    root = fetch(catalog_url)
    found: list[tuple[dict[str, Any], str]] = []
    for link in root.get("links", []):
        if link.get("rel") != "child":
            continue
        href = link.get("href")
        if not href:
            continue
        if collection and _collection_id_from_href(href) != collection:
            continue
        url = urljoin(catalog_url, href)
        _collect_items(fetch(url), url, aoi_bbox, fetch, found)

    if datetime_filter:
        found = [
            (item, url)
            for item, url in found
            if _within_interval((item.get("properties") or {}).get("datetime"), datetime_filter)
        ]
    return found


def _ground_tile_key(item: dict[str, Any]) -> str:
    """Identify the fixed ground tile an item covers (grid cell, sans acquisition).

    Maxar ARD item ids look like ``{utm}/{quadkey}/{acquisition}``; the leading
    components identify the non-overlapping ground cell, so two items with the
    same key are different captures of the same footprint.
    """
    item_id = item.get("id", "")
    parts = item_id.split("/")
    return "/".join(parts[:-1]) if len(parts) >= 2 else item_id


def select_mece_items(
    items: list[tuple[dict[str, Any], str]],
) -> list[tuple[dict[str, Any], str]]:
    """Pick one item per ground tile (most recent), covering the AOI MECE.

    Mutually exclusive: one image per non-overlapping ground cell.
    Collectively exhaustive: every intersecting ground cell is kept.
    """
    best: dict[str, tuple[str, dict[str, Any], str]] = {}
    for item, url in items:
        key = _ground_tile_key(item)
        dt = (item.get("properties") or {}).get("datetime") or ""
        current = best.get(key)
        if current is None or dt > current[0]:
            best[key] = (dt, item, url)
    return [(item, url) for _, (_, item, url) in sorted(best.items())]


def run_stac_static_cog_extract(
    source: dict[str, Any],
    aoi: AOIConfig,
    output: OutputConfig,
    output_path: Path,
    force: bool,
    prev_meta: dict[str, Any] | None,
    fetch: FetchFn = _fetch_json,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if output.format != "geotiff":
        raise ValueError("stac-static-cog source only supports geotiff output")

    asset_key = source.get("asset", "visual")
    items = find_aoi_items(
        source["catalogUrl"],
        aoi.bbox,
        collection=source.get("collection"),
        datetime_filter=source.get("datetime"),
        fetch=fetch,
    )
    selected = select_mece_items(items)
    if not selected:
        raise ValueError("No STAC item found intersecting the AOI in the static catalog")

    asset_hrefs: list[str] = []
    item_ids: list[str] = []
    datetimes: list[str] = []
    for item, item_url in selected:
        asset = (item.get("assets") or {}).get(asset_key)
        if not asset or not asset.get("href"):
            continue
        asset_hrefs.append(urljoin(item_url, asset["href"]))
        item_ids.append(item.get("id"))
        dt = (item.get("properties") or {}).get("datetime")
        if dt:
            datetimes.append(dt)

    if not asset_hrefs:
        raise ValueError(f"No {asset_key!r} asset found in the selected items")

    source_info: dict[str, Any] = {
        "type": "stac-static-cog",
        "catalogUrl": source["catalogUrl"],
        "collection": source.get("collection"),
        "asset": asset_key,
        "itemCount": len(item_ids),
        "itemIds": item_ids,
        "datetimeRange": [min(datetimes), max(datetimes)] if datetimes else None,
        "checkedAt": utc_now(),
    }

    prev_info = (prev_meta or {}).get("sourceInfo") or {}
    if output_path.exists() and not force and source_info["itemIds"] == prev_info.get("itemIds"):
        return source_info, None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [stac-static-cog] gdalwarp mosaic {len(asset_hrefs)} item(s) -> {output_path}")
    gdal_warp_mosaic_bbox(asset_hrefs, output_path, aoi.bbox)
    return source_info, None

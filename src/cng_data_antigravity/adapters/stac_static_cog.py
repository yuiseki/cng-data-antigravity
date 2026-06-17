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
included. Each selected ``visual`` COG is clipped to the AOI and saved
as its own GeoTIFF, and a local static STAC ``catalog.json`` (plus one
Item per tile) is written so the output directory is itself a valid,
self-describing static STAC catalog of the escaped raw data.

Used by the Maxar Open Data catalog:
https://maxar-opendata.s3.amazonaws.com/events/catalog.json
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin
from urllib.request import urlopen

# Default number of tiles clipped concurrently. Each tile's gdal.Translate
# already issues several range requests, so a small fan-out is plenty; the
# real defence against S3 throttling is GDAL's HTTP retry/backoff below.
_DEFAULT_CONCURRENCY = 4

from cng_data_antigravity.adapters.common import (
    gdal_translate_bbox,
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


_COG_MEDIA_TYPE = "image/tiff; application=geotiff; profile=cloud-optimized"


def _safe_id(item_id: str) -> str:
    """Filesystem-safe stem for an item id like ``53/120020323222/1030...``."""
    return item_id.replace("/", "_").replace("\\", "_")


def _bbox_intersection(a: Bbox, b: Bbox) -> Bbox:
    return [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]


def _bbox_polygon(bbox: Bbox) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south], [east, south], [east, north], [west, north], [west, south],
        ]],
    }


def _build_stac_item(item: dict[str, Any], clipped_bbox: Bbox, cog_filename: str) -> dict[str, Any]:
    """A static STAC Item describing one escaped, AOI-clipped COG."""
    item_id = item.get("id", "")
    stem = _safe_id(item_id)
    return {
        "stac_version": "1.0.0",
        "type": "Feature",
        "id": item_id,
        "bbox": clipped_bbox,
        "geometry": _bbox_polygon(clipped_bbox),
        "properties": {"datetime": (item.get("properties") or {}).get("datetime")},
        "assets": {
            "visual": {
                "href": f"./{cog_filename}",
                "type": _COG_MEDIA_TYPE,
                "roles": ["data", "visual"],
            }
        },
        "links": [
            {"rel": "root", "href": "./catalog.json", "type": "application/json"},
            {"rel": "parent", "href": "./catalog.json", "type": "application/json"},
            {"rel": "self", "href": f"./{stem}.json", "type": "application/json"},
        ],
    }


def _build_catalog(catalog_id: str, source: dict[str, Any], item_stems: list[str]) -> dict[str, Any]:
    """A static STAC Catalog linking to every escaped Item."""
    links = [{"rel": "root", "href": "./catalog.json", "type": "application/json"}]
    links += [
        {"rel": "item", "href": f"./{stem}.json", "type": "application/json"}
        for stem in item_stems
    ]
    return {
        "stac_version": "1.0.0",
        "type": "Catalog",
        "id": catalog_id,
        "description": (
            f"AOI escape of {source.get('collection') or 'Maxar Open Data'} "
            f"from {source['catalogUrl']}"
        ),
        "links": links,
    }


def run_stac_static_cog_extract(
    source: dict[str, Any],
    aoi: AOIConfig,
    output: OutputConfig,
    output_path: Path,
    force: bool,
    prev_meta: dict[str, Any] | None,
    fetch: FetchFn = _fetch_json,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if output.format != "stac-catalog":
        raise ValueError("stac-static-cog source only supports stac-catalog output")

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

    # Resolve the escapable set (items that actually carry the requested asset).
    escapable: list[tuple[dict[str, Any], str]] = []
    item_ids: list[str] = []
    datetimes: list[str] = []
    for item, item_url in selected:
        asset = (item.get("assets") or {}).get(asset_key)
        if not asset or not asset.get("href"):
            continue
        escapable.append((item, urljoin(item_url, asset["href"])))
        item_ids.append(item.get("id"))
        dt = (item.get("properties") or {}).get("datetime")
        if dt:
            datetimes.append(dt)

    if not escapable:
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

    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Let GDAL absorb transient S3 throttling (503 SlowDown) with backoff rather
    # than failing. setdefault so an operator's own env still wins.
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
    os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "1")
    os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")  # anonymous public bucket

    def _escape_tile(entry: tuple[dict[str, Any], str]) -> str:
        item, asset_href = entry
        stem = _safe_id(item.get("id", ""))
        cog_filename = f"{stem}.tif"
        clipped_bbox = _bbox_intersection(item["bbox"], aoi.bbox)
        print(f"  [stac-static-cog] clip {item.get('id')} -> {output_dir / cog_filename}")
        gdal_translate_bbox(asset_href, output_dir / cog_filename, aoi.bbox)
        stac_item = _build_stac_item(item, clipped_bbox, cog_filename)
        (output_dir / f"{stem}.json").write_text(
            json.dumps(stac_item, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return stem

    concurrency = max(1, int(source.get("concurrency", _DEFAULT_CONCURRENCY)))
    if concurrency == 1:
        item_stems = [_escape_tile(entry) for entry in escapable]
    else:
        # ex.map preserves input order, so the catalog stays deterministic
        # regardless of which tile finishes first.
        with ThreadPoolExecutor(max_workers=min(concurrency, len(escapable))) as pool:
            item_stems = list(pool.map(_escape_tile, escapable))

    catalog = _build_catalog(output_dir.name, source, item_stems)
    output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return source_info, None

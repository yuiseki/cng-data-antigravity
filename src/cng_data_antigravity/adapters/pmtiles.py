from __future__ import annotations

import math
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pmtiles.reader import MmapSource, Reader
from pmtiles.tile import zxy_to_tileid
from pmtiles.writer import write

from cng_data_antigravity.adapters.common import head, make_request, utc_now
from cng_data_antigravity.config import AOIConfig, OutputConfig

MAX_WEB_MERCATOR_LAT = 85.05112878


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

    source_info = _build_source_info(source["url"])
    prev_info = (prev_meta or {}).get("sourceInfo") or {}
    unchanged = (
        output_path.exists()
        and not force
        and (
            (
                source_info.get("etag")
                and source_info["etag"] == prev_info.get("etag")
            )
            or (
                source_info.get("lastModified")
                and source_info["lastModified"] == prev_info.get("lastModified")
            )
            or (
                source_info.get("contentLength")
                and source_info["contentLength"] == prev_info.get("contentLength")
            )
            or (
                source_info.get("fileSize") is not None
                and source_info["fileSize"] == prev_info.get("fileSize")
                and source_info.get("mtimeNs") == prev_info.get("mtimeNs")
            )
        )
    )
    if unchanged:
        return source_info, None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _extract_pmtiles_subset(source, aoi.bbox, output_path)
    return source_info, None


def _extract_pmtiles_subset(source: dict[str, Any], bbox: list[float], output_path: Path) -> None:
    with _open_pmtiles_reader(source["url"]) as reader:
        source_header = reader.header()
        source_metadata = reader.metadata()

        min_zoom = int(source.get("minzoom", source_header["min_zoom"]))
        max_zoom = int(source.get("maxzoom", source_header["max_zoom"]))
        tile_requests = _tile_requests_for_bbox(bbox, min_zoom=min_zoom, max_zoom=max_zoom)

        extracted_tiles: list[tuple[int, bytes]] = []
        for tile_id, z, x, y in tile_requests:
            tile_data = reader.get(z, x, y)
            if tile_data is not None:
                extracted_tiles.append((tile_id, tile_data))

        if not extracted_tiles:
            raise ValueError("pmtiles extract produced no tiles for the requested bbox")

        output_header = _build_output_header(source_header, bbox, min_zoom=min_zoom)
        output_metadata = _build_output_metadata(source_metadata, bbox, min_zoom=min_zoom, max_zoom=max_zoom)

        with write(output_path) as writer:
            for tile_id, tile_data in extracted_tiles:
                writer.write_tile(tile_id, tile_data)
            writer.finalize(output_header, output_metadata)


def _build_source_info(source_url: str) -> dict[str, Any]:
    if _is_http_url(source_url):
        headers = head(source_url)
        return {
            "type": "pmtiles",
            "url": source_url,
            "lastModified": headers.get("last-modified", ""),
            "etag": headers.get("etag", ""),
            "contentLength": headers.get("content-length", ""),
            "checkedAt": utc_now(),
        }

    source_path = _as_local_path(source_url)
    stat = source_path.stat()
    return {
        "type": "pmtiles",
        "url": str(source_path),
        "fileSize": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
        "checkedAt": utc_now(),
    }


@contextmanager
def _open_pmtiles_reader(source_url: str):
    stack = ExitStack()
    try:
        if _is_http_url(source_url):
            reader = Reader(_http_range_source(source_url))
        else:
            file_obj = stack.enter_context(_as_local_path(source_url).open("rb"))
            reader = Reader(MmapSource(file_obj))
        yield reader
    finally:
        stack.close()


def _http_range_source(source_url: str):
    def get_bytes(offset: int, length: int) -> bytes:
        end = offset + length - 1
        request = make_request(source_url, extra_headers={"Range": f"bytes={offset}-{end}"})
        with urlopen(request, timeout=30) as response:
            return response.read()

    return get_bytes


def _tile_requests_for_bbox(bbox: list[float], *, min_zoom: int, max_zoom: int) -> list[tuple[int, int, int, int]]:
    west, south, east, north = bbox
    if west >= east:
        raise ValueError("bbox crossing the antimeridian is not supported yet")

    tile_requests: list[tuple[int, int, int, int]] = []
    for zoom in range(min_zoom, max_zoom + 1):
        x_min = _lon_to_tile_x(west, zoom)
        x_max = _lon_to_tile_x(math.nextafter(east, west), zoom)
        y_min = _lat_to_tile_y(north, zoom)
        y_max = _lat_to_tile_y(math.nextafter(south, north), zoom)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tile_id = zxy_to_tileid(zoom, x, y)
                tile_requests.append((tile_id, zoom, x, y))
    tile_requests.sort(key=lambda item: item[0])
    return tile_requests


def _lon_to_tile_x(lon: float, zoom: int) -> int:
    n = 1 << zoom
    clamped_lon = min(max(lon, -180.0), math.nextafter(180.0, -180.0))
    tile_x = math.floor((clamped_lon + 180.0) / 360.0 * n)
    return max(0, min(tile_x, n - 1))


def _lat_to_tile_y(lat: float, zoom: int) -> int:
    n = 1 << zoom
    clamped_lat = min(max(lat, -MAX_WEB_MERCATOR_LAT), MAX_WEB_MERCATOR_LAT)
    lat_rad = math.radians(clamped_lat)
    mercator = math.asinh(math.tan(lat_rad))
    tile_y = math.floor((1.0 - mercator / math.pi) / 2.0 * n)
    return max(0, min(tile_y, n - 1))


def _build_output_header(source_header: dict[str, Any], bbox: list[float], *, min_zoom: int) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "tile_type": source_header["tile_type"],
        "tile_compression": source_header["tile_compression"],
        "min_lon_e7": int(west * 1e7),
        "min_lat_e7": int(south * 1e7),
        "max_lon_e7": int(east * 1e7),
        "max_lat_e7": int(north * 1e7),
        "center_zoom": min_zoom,
        "center_lon_e7": int(((west + east) / 2.0) * 1e7),
        "center_lat_e7": int(((south + north) / 2.0) * 1e7),
        "min_zoom": min_zoom,
        "max_zoom": source_header["max_zoom"],
    }


def _build_output_metadata(
    source_metadata: dict[str, Any],
    bbox: list[float],
    *,
    min_zoom: int,
    max_zoom: int,
) -> dict[str, Any]:
    west, south, east, north = bbox
    output_metadata = dict(source_metadata)
    output_metadata["bounds"] = f"{west},{south},{east},{north}"
    output_metadata["center"] = f"{(west + east) / 2.0},{(south + north) / 2.0},{min_zoom}"
    output_metadata["minzoom"] = str(min_zoom)
    output_metadata["maxzoom"] = str(max_zoom)
    return output_metadata


def _is_http_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


def _as_local_path(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return Path(parsed.path)
    return Path(value)

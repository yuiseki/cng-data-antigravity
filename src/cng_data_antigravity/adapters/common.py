from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

_USER_AGENT = "cng-data-antigravity/0.1 (+https://github.com/yuiseki/cng-data-antigravity)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _import_gdal():
    try:
        from osgeo import gdal  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "osgeo.gdal is required for STAC COG adapters. "
            "Install it with: pip install \"GDAL==$(gdal-config --version)\""
        ) from exc
    gdal.UseExceptions()
    return gdal


def gdal_translate_bbox(src_href: str, dest: Path, bbox: list[float]) -> None:
    """Clip a single (remote) COG to the AOI bbox, writing a GeoTIFF."""
    gdal = _import_gdal()
    west, south, east, north = bbox
    opts = gdal.TranslateOptions(
        format="GTiff",
        projWin=[west, north, east, south],
        projWinSRS="EPSG:4326",
        creationOptions=["COMPRESS=LZW", "TILED=YES"],
    )
    gdal.Translate(str(dest), f"/vsicurl/{src_href}", options=opts)


def make_request(url: str, *, method: str = "GET", extra_headers: dict[str, str] | None = None) -> Request:
    headers = {"User-Agent": _USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    return Request(url, method=method, headers=headers)


def head(url: str) -> dict[str, str]:
    request = make_request(url, method="HEAD")
    with urlopen(request, timeout=30) as response:
        return {k.lower(): v for k, v in response.headers.items()}

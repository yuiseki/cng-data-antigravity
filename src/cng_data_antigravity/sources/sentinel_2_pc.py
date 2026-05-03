"""Built-in source: Sentinel-2 L2A via Microsoft Planetary Computer.

Extracts a cloud-optimized GeoTIFF for the AOI using the STAC API.
Requires per-extract overrides: datetime (ISO 8601 interval), maxCloudCover.
Output: output/sentinel-2-pc/sentinel-2-pc.tif

https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a
"""
from cng_data_antigravity.config import SourceDef
from cng_data_antigravity.sources import BUILTIN_SOURCES

BUILTIN_SOURCES["sentinel-2-pc"] = SourceDef(
    adapter="stac-cog",
    config={
        "stacApiUrl": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "collection": "sentinel-2-l2a",
        "asset": "visual",
    },
)

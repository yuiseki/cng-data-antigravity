"""Built-in source: Mapterhorn planet PMTiles.

Global OSM-based vector tiles (zoom 0-12) distributed by Mapterhorn.
Extracts a bbox subset from planet.pmtiles.
Output: output/mapterhorn-pmtiles/mapterhorn-pmtiles.pmtiles

https://download.mapterhorn.com/

The download_urls.json index is used to resolve the current planet URL and
expose its md5sum / size for freshness checking by the pmtiles adapter.

https://download.mapterhorn.com/download_urls.json
"""
from __future__ import annotations

import json
from typing import Any
from urllib.request import urlopen

from cng_data_antigravity.adapters.common import make_request

from cng_data_antigravity.config import SourceDef
from cng_data_antigravity.sources import BUILTIN_SOURCES

_INDEX_URL = "https://download.mapterhorn.com/download_urls.json"
_PLANET_NAME = "planet.pmtiles"
_FALLBACK_URL = "https://download.mapterhorn.com/planet.pmtiles"


def fetch_planet_entry() -> dict[str, Any]:
    """Return the planet.pmtiles entry from download_urls.json."""
    with urlopen(make_request(_INDEX_URL), timeout=30) as response:
        index = json.load(response)
    entry = next((item for item in index["items"] if item["name"] == _PLANET_NAME), None)
    if entry is None:
        raise ValueError(f"{_PLANET_NAME} not found in {_INDEX_URL}")
    return entry


BUILTIN_SOURCES["mapterhorn-pmtiles"] = SourceDef(
    adapter="pmtiles",
    config={"url": _FALLBACK_URL},
)

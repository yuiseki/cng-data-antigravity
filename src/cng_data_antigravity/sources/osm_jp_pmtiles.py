"""Built-in source: OpenStreetMap Japan — PMTiles.

Extracts a bbox subset from the OpenStreetMap Japan planet PMTiles archive.
Output: output/osm-jp-pmtiles/osm-jp-pmtiles.pmtiles

https://tile.openstreetmap.jp/
"""
from cng_data_antigravity.config import SourceDef
from cng_data_antigravity.sources import BUILTIN_SOURCES

BUILTIN_SOURCES["osm-jp-pmtiles"] = SourceDef(
    adapter="pmtiles",
    config={"url": "https://tile.openstreetmap.jp/static/planet.pmtiles"},
)

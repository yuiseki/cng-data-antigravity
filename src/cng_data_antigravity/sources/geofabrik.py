"""Built-in sources: Geofabrik OSM PBF extracts.

Uses the osm-pbf adapter with Geofabrik's GeoJSON index for region URL resolution.
Output: output/{source-name}/{source-name}.osm.pbf

Available regions: https://download.geofabrik.de/index-v1.json

To use a region not listed here, add it to the sources: section of escape.yaml:

  sources:
    osm-europe:
      adapter: osm-pbf
      indexUrl: https://download.geofabrik.de/index-v1.json
      region: europe
"""
from __future__ import annotations

from cng_data_antigravity.config import SourceDef
from cng_data_antigravity.sources import BUILTIN_SOURCES

_INDEX_URL = "https://download.geofabrik.de/index-v1.json"


def _geofabrik(region: str) -> SourceDef:
    return SourceDef(
        adapter="osm-pbf",
        config={"indexUrl": _INDEX_URL, "region": region},
    )


# Japan
BUILTIN_SOURCES["osm-japan"] = _geofabrik("japan")
BUILTIN_SOURCES["osm-kanto"] = _geofabrik("kanto")
BUILTIN_SOURCES["osm-kansai"] = _geofabrik("kansai")
BUILTIN_SOURCES["osm-chubu"] = _geofabrik("chubu")
BUILTIN_SOURCES["osm-kyushu"] = _geofabrik("kyushu")
BUILTIN_SOURCES["osm-tohoku"] = _geofabrik("tohoku")
BUILTIN_SOURCES["osm-hokkaido"] = _geofabrik("hokkaido")

# Major continents / countries
BUILTIN_SOURCES["osm-asia"] = _geofabrik("asia")
BUILTIN_SOURCES["osm-europe"] = _geofabrik("europe")
BUILTIN_SOURCES["osm-north-america"] = _geofabrik("north-america")
BUILTIN_SOURCES["osm-germany"] = _geofabrik("germany")
BUILTIN_SOURCES["osm-france"] = _geofabrik("france")
BUILTIN_SOURCES["osm-great-britain"] = _geofabrik("great-britain")

# Small territories — suitable for E2E testing (~400–700 KB PBF)
BUILTIN_SOURCES["osm-monaco"] = _geofabrik("monaco")
BUILTIN_SOURCES["osm-niue"] = _geofabrik("niue")

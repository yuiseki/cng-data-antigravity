"""Built-in sources: HOTOSM OpenAerialMap (OAM) STAC API.

Three collections are available at https://api.imagery.hotosm.org/stac:

  hotosm-oam       OpenAerialMap community imagery     CC-BY-4.0
  hotosm-maxar     Maxar ARD Open Data                 CC-BY-NC-4.0
  hotosm-noaa      NOAA Emergency Response Imagery     public domain

Each source returns the most recent visual (RGB COG) asset that intersects
the AOI. Override ``datetime`` in the extract to restrict the time window.

https://api.imagery.hotosm.org/stac
"""
from cng_data_antigravity.config import SourceDef
from cng_data_antigravity.sources import BUILTIN_SOURCES

_STAC_API_URL = "https://api.imagery.hotosm.org/stac"

# Sort by most recent first (aerial imagery has no cloud-cover property).
_SORTBY_DATETIME_DESC = [{"field": "properties.datetime", "direction": "desc"}]


def _oam_source(collection: str) -> SourceDef:
    return SourceDef(
        adapter="stac-cog",
        config={
            "stacApiUrl": _STAC_API_URL,
            "collection": collection,
            "asset": "visual",
            "sortby": _SORTBY_DATETIME_DESC,
        },
    )


BUILTIN_SOURCES["hotosm-oam"] = _oam_source("openaerialmap")
BUILTIN_SOURCES["hotosm-maxar"] = _oam_source("maxar-opendata")
BUILTIN_SOURCES["hotosm-noaa"] = _oam_source("noaa-emergency-response")

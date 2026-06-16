"""Built-in source: Maxar Open Data (static STAC catalog).

Maxar publishes ARD Open Data for disaster events as a *static* STAC catalog
(plain JSON files on S3, no /search endpoint), organized by event:

    events/catalog.json                         root Catalog
      -> {event}/collection.json                Collection per disaster event
        -> .../acquisition_collections/*.json   Collection per acquisition
          -> items -> assets.visual             RGB COG per ground tile

By default this source covers the AOI **MECE** (mutually exclusive, collectively
exhaustive): the most recent acquisition is selected for every ground tile that
intersects the AOI, and all selected ``visual`` COGs are mosaicked into a single
GeoTIFF clipped to the AOI.

Override ``collection`` to restrict the walk to one event (e.g.
``Hurricane-Melissa-Oct-2025``) and ``datetime`` (ISO 8601 interval) to narrow
the time window.

License: CC-BY-NC-4.0
https://maxar-opendata.s3.amazonaws.com/events/catalog.json
"""
from cng_data_antigravity.config import SourceDef
from cng_data_antigravity.sources import BUILTIN_SOURCES

BUILTIN_SOURCES["maxar-opendata"] = SourceDef(
    adapter="stac-static-cog",
    config={
        "catalogUrl": "https://maxar-opendata.s3.amazonaws.com/events/catalog.json",
        "asset": "visual",
    },
)

"""Built-in source: Overture Maps (all themes).

Downloads all available Overture themes for the AOI.
Output: output/overture/{type}.parquet per theme.

https://overturemaps.org/
"""
from cng_data_antigravity.config import SourceDef
from cng_data_antigravity.sources import BUILTIN_SOURCES

BUILTIN_SOURCES["overture"] = SourceDef(
    adapter="overture",
    config={},
)

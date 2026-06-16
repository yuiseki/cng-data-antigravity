from __future__ import annotations

from cng_data_antigravity.config import SourceDef

# Built-in source registry: source name → SourceDef
# Populated by importing each source module below.
BUILTIN_SOURCES: dict[str, SourceDef] = {}


def _load() -> None:
    from cng_data_antigravity.sources import (  # noqa: F401
        geofabrik,
        hotosm_oam,
        mapterhorn_pmtiles,
        maxar_opendata,
        osm_jp_pmtiles,
        overture,
        sentinel_2_pc,
    )


_load()

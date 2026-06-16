# cng-data-antigravity

> **Data has gravity.**  
> It accumulates in the cloud, massive and immovable.
>
> **But Cloud-Native Geospatial data also has antigravity.**  
> Declare your area of interest. Escape only what you need.

`cng-data-antigravity` implements **data antigravity** for Cloud-Native Geospatial (CNG) sources.

An `escape.yaml` file describes what to extract and from where. The tool checks source freshness, downloads only what changed, extracts an AOI-sized subset, and writes reproducible local outputs alongside a `metadata.json`.

## Key concepts

### Data gravity

Large datasets attract applications, pipelines, and compute toward the cloud where they reside. Moving data out is expensive:

- bandwidth
- time
- tooling

This pull is **data gravity**. Geospatial data is especially heavy. Planet-scale vector tiles, global OSM extracts, and satellite imagery archives can run into hundreds of gigabytes. Gravity keeps them in the cloud.

### CNG Data antigravity

Cloud-Native Geospatial (CNG) data sources provide mechanisms that counteract data gravity, and they carry the hidden properties of data antigravity.

Not all sources use the same mechanism:

- **HTTP range requests**: PMTiles and COG expose internal tile indexes, while GeoParquet can use partitioning, row-group metadata, and spatially sorted layouts to avoid scanning unrelated bytes. Together, these mechanisms let a client fetch or scan only the portions relevant to a specific AOI instead of downloading the whole dataset.
- **Spatiotemporal catalogs**: STAC (SpatioTemporal Asset Catalog) lets you search by bbox, datetime, and cloud cover to discover exactly which assets are relevant, then download only those. Even a *static* STAC catalog (plain JSON files, no search endpoint) carries this property: each collection declares a spatial extent, so whole subtrees that miss the AOI can be pruned without fetching their items.
- **Regional extracts**: OSM PBF files must be downloaded in full, but Geofabrik publishes pre-split regional extracts (country, prefecture, ...) that already reduce the scope before a local bbox clip.

Each mechanism gives you a way to pull **only what you need** out of a planet-scale dataset.

`cng-data-antigravity` abstracts over all of them. You declare an area of interest (AOI) and a list of sources. The tool:

1. checks source freshness
2. fetches only what changed
3. clips to your bbox
4. writes reproducible local outputs

The data escapes the cloud, without pulling the whole planet down with it.

## Naming contract

| | |
|---|---|
| Repository | `cng-data-antigravity` |
| PyPI | `cng-data-antigravity` |
| Import | `cng_data_antigravity` |
| CLI | `cng-data-antigravity` |
| Default config | `escape.yaml` |

## Installation

> Not yet published to PyPI. Install from source:

```bash
git clone https://github.com/yuiseki/cng-data-antigravity
cd cng-data-antigravity
uv sync
```

Dependencies: `overturemaps`, `pmtiles`, `PyYAML`, `osmium`, `pystac-client`

**STAC COG support** requires GDAL, which must match your system's `libgdal` version exactly. Pre-built wheels are not available on PyPI, so install it separately after `uv sync`:

```bash
sudo apt-get install libgdal-dev gdal-bin   # or equivalent for your OS
uv pip install "GDAL==$(gdal-config --version)"
```

## Usage

```bash
# reads escape.yaml in the current directory
cng-data-antigravity run

# explicit path
cng-data-antigravity run /path/to/escape.yaml

# force re-download even if source is unchanged
cng-data-antigravity run --force
```

## escape.yaml

### Minimal example

```yaml
aoi:
  bbox: [139.56, 35.52, 139.92, 35.82]  # [west, south, east, north]

extracts:
  - source: overture
  - source: osm-jp-pmtiles
  - source: osm-kanto
  - source: sentinel-2-pc
    datetime: "2025-09-01/2025-11-30"
    maxCloudCover: 20
```

### Convention over configuration

- `outputs` is optional. Defaults: `output/{id}/{id}.{ext}`, or `output/{id}/{type}.parquet` for multi-type Overture extracts.
- `id` is optional. Defaults to the source name.
- Per-extract overrides (e.g. `datetime`, `maxCloudCover`, `overtureType`) are written directly under the extract (no nesting required).

### Custom sources

Add a `sources:` section for sources not in the built-in registry:

```yaml
sources:
  osm-europe-custom:
    adapter: osm-pbf
    indexUrl: https://download.geofabrik.de/index-v1.json
    region: europe

extracts:
  - source: osm-europe-custom
```

## Architecture

### Sources vs. adapters

| Layer | Role |
|---|---|
| **Source** | Named data source definition (adapter + config). Registered in `BUILTIN_SOURCES` or defined in `sources:`. |
| **Adapter** | Technical driver that performs the actual download, freshness check, and bbox extraction. |

### Built-in sources

| Source name | Adapter | Provider | Region / Notes |
|---|---|---|---|
| `overture` | `overture` | Overture Maps | all themes → `{type}.parquet` |
| `osm-jp-pmtiles` | `pmtiles` | tile.openstreetmap.jp | Japan planet PMTiles |
| `mapterhorn-pmtiles` | `pmtiles` | Mapterhorn | global planet PMTiles (zoom 0–12) |
| `sentinel-2-pc` | `stac-cog` | Microsoft Planetary Computer | Sentinel-2 L2A |
| `hotosm-oam` | `stac-cog` | HOTOSM OpenAerialMap | OpenAerialMap community imagery (CC-BY-4.0) |
| `hotosm-maxar` | `stac-cog` | HOTOSM OpenAerialMap | Maxar ARD Open Data (CC-BY-NC-4.0) |
| `hotosm-noaa` | `stac-cog` | HOTOSM OpenAerialMap | NOAA Emergency Response Imagery (public domain) |
| `maxar-opendata` | `stac-static-cog` | Maxar Open Data | ARD disaster imagery, static STAC catalog (CC-BY-NC-4.0) |
| `osm-japan` | `osm-pbf` | Geofabrik | Japan |
| `osm-kanto` | `osm-pbf` | Geofabrik | Kanto |
| `osm-kansai` | `osm-pbf` | Geofabrik | Kansai |
| `osm-chubu` | `osm-pbf` | Geofabrik | Chubu |
| `osm-kyushu` | `osm-pbf` | Geofabrik | Kyushu |
| `osm-tohoku` | `osm-pbf` | Geofabrik | Tohoku |
| `osm-hokkaido` | `osm-pbf` | Geofabrik | Hokkaido |
| `osm-asia` | `osm-pbf` | Geofabrik | Asia |
| `osm-europe` | `osm-pbf` | Geofabrik | Europe |
| `osm-north-america` | `osm-pbf` | Geofabrik | North America |
| `osm-germany` | `osm-pbf` | Geofabrik | Germany |
| `osm-france` | `osm-pbf` | Geofabrik | France |
| `osm-great-britain` | `osm-pbf` | Geofabrik | Great Britain |
| `osm-monaco` | `osm-pbf` | Geofabrik | Monaco (~663 KB, good for E2E testing) |
| `osm-niue` | `osm-pbf` | Geofabrik | Niue (~412 KB, good for E2E testing) |

### Adapters

| Adapter | Output format | Python library | Freshness check |
|---|---|---|---|
| `overture` | GeoParquet | `overturemaps` | release tag + bbox state file |
| `pmtiles` | PMTiles | `pmtiles` | ETag / Last-Modified / Content-Length |
| `osm-pbf` | OSM PBF | `osmium` | ETag / Last-Modified / Content-Length |
| `stac-cog` | GeoTIFF | `pystac_client` + `osgeo.gdal` | STAC item ID |
| `stac-static-cog` | clipped COGs + static STAC `catalog.json` | `osgeo.gdal` | selected STAC item IDs |

### Output layout

```
output/
  {extract-id}/
    {extract-id}.{ext}      # extracted data file
    metadata.json           # provenance, timing, source state
.cache/
  osm-pbf/
    {region}-latest.osm.pbf  # full PBF cached locally (osm-pbf adapter only)
```

### metadata.json

```json
{
  "id": "osm-monaco",
  "extractedAt": "2026-05-03T11:00:00+00:00",
  "durationSeconds": 45.123,
  "source": { "type": "osm-pbf", "region": "monaco", ... },
  "sourceInfo": { "pbfUrl": "...", "etag": "...", "lastModified": "...", "checkedAt": "..." },
  "sourceState": null,
  "aoi": { "bbox": [7.39, 43.72, 7.44, 43.76] },
  "outputs": [{ "format": "osm.pbf", "path": "..." }],
  "attribution": "© OpenStreetMap contributors, available under ODbL"
}
```

## Overture-specific options

```yaml
extracts:
  # Single type
  - source: overture
    overtureType: building

  # Multiple types
  - source: overture
    overtureTypes: [building, place, segment]

  # All types (default when neither is specified)
  - source: overture

  # Specific release
  - source: overture
    release: "2025-07-23.0"
    overtureType: place
```

## Sentinel-2 options

```yaml
extracts:
  - source: sentinel-2-pc
    datetime: "2025-09-01/2025-11-30"   # ISO 8601 interval (required)
    maxCloudCover: 20                    # 0–100, default 100

  # Multiple windows with explicit ids
  - id: sentinel-2-winter
    source: sentinel-2-pc
    datetime: "2026-01-01/2026-03-31"
    maxCloudCover: 30
```

## HOTOSM OpenAerialMap options

```yaml
extracts:
  # Most recent community imagery over the AOI (no datetime required)
  - source: hotosm-oam

  # Restrict to a specific time window
  - source: hotosm-oam
    datetime: "2024-01-01/2025-12-31"

  # Maxar ARD Open Data (CC-BY-NC-4.0)
  - source: hotosm-maxar

  # NOAA Emergency Response Imagery (public domain)
  - source: hotosm-noaa
```

STAC API: <https://api.imagery.hotosm.org/stac>  
All three sources return the most recent `visual` (RGB COG) asset intersecting the AOI.
Override `datetime` per-extract to narrow the search window.

## Maxar Open Data options

Maxar publishes ARD disaster imagery as a **static STAC catalog** (plain JSON on S3, no `/search` endpoint), organized by event. The `stac-static-cog` adapter walks the catalog tree, prunes whole events/acquisitions by their spatial extent, and—by convention—covers the AOI **MECE** (mutually exclusive, collectively exhaustive): the most recent acquisition is selected for every ground tile intersecting the AOI. Each selected `visual` COG is clipped to the AOI and saved as its own GeoTIFF, and a local static STAC `catalog.json` (plus one Item per tile) is written so the output directory is itself a valid, self-describing static STAC catalog of the escaped raw data:

```
output/maxar-opendata/
  catalog.json                 # static STAC Catalog linking every escaped Item
  {tile-id}.json               # STAC Item per ground tile
  {tile-id}.tif                # AOI-clipped COG per ground tile
  metadata.json                # provenance (selected item IDs, timing, ...)
```

```yaml
extracts:
  # Cover the AOI across all events (auto-discovers intersecting imagery)
  - source: maxar-opendata

  # Restrict to a single event (much faster: skips walking every other event)
  - source: maxar-opendata
    collection: Hurricane-Melissa-Oct-2025

  # Narrow the time window (ISO 8601 interval)
  - source: maxar-opendata
    collection: Hurricane-Melissa-Oct-2025
    datetime: "2025-10-01/2025-12-31"
```

Static catalog: <https://maxar-opendata.s3.amazonaws.com/events/catalog.json>  
License: CC-BY-NC-4.0. Without `collection`, the tool fetches every event's `collection.json` to read its extent (there is no search endpoint), so scoping to a `collection` is recommended when you know the event.

## Development

```bash
uv sync
SKIP_NETWORK_TESTS=1 uv run pytest tests/    # unit tests only (network-free)
uv run pytest tests/test_e2e_osm_pbf.py      # E2E tests (real network, Monaco/Niue)
uv run pytest tests/                          # all tests
```

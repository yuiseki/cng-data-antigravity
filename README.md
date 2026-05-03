# cng-data-antigravity

> **Data has gravity.**
> It accumulates in the cloud, massive and immovable.
>
> **But Cloud-Native Geospatial data also has antigravity.**
> Declare your area of interest. Escape only what you need.

`cng-data-antigravity` implements **data antigravity** for Cloud-Native Geospatial (CNG) sources.

An `escape.yaml` file describes what to extract and from where. The tool checks source freshness, downloads only what changed, extracts an AOI-sized subset, and writes reproducible local outputs alongside a `metadata.json`.

## Naming contract

| | |
|---|---|
| Repository | `cng-data-antigravity` |
| PyPI | `cng-data-antigravity` |
| Import | `cng_data_antigravity` |
| CLI | `cng-data-antigravity` |
| Default config | `escape.yaml` |

## Installation

```bash
pip install cng-data-antigravity
```

Dependencies: `overturemaps`, `pmtiles`, `PyYAML`, `osmium`, `pystac-client`, `gdal`

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
- Per-extract overrides (e.g. `datetime`, `maxCloudCover`, `overtureType`) are written directly under the extract — no nesting required.

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

| Source name | Adapter | Description |
|---|---|---|
| `overture` | `overture` | Overture Maps — all themes → `{type}.parquet` |
| `osm-jp-pmtiles` | `pmtiles` | OSM Japan PMTiles (tile.openstreetmap.jp) |
| `mapterhorn-pmtiles` | `pmtiles` | Global OSM vector tiles (Mapterhorn planet.pmtiles, zoom 0–12) |
| `sentinel-2-pc` | `stac-cog` | Sentinel-2 L2A via Microsoft Planetary Computer |
| `osm-japan` | `osm-pbf` | Geofabrik — Japan |
| `osm-kanto` | `osm-pbf` | Geofabrik — Kanto |
| `osm-kansai` | `osm-pbf` | Geofabrik — Kansai |
| `osm-chubu` | `osm-pbf` | Geofabrik — Chubu |
| `osm-kyushu` | `osm-pbf` | Geofabrik — Kyushu |
| `osm-tohoku` | `osm-pbf` | Geofabrik — Tohoku |
| `osm-hokkaido` | `osm-pbf` | Geofabrik — Hokkaido |
| `osm-asia` | `osm-pbf` | Geofabrik — Asia |
| `osm-europe` | `osm-pbf` | Geofabrik — Europe |
| `osm-north-america` | `osm-pbf` | Geofabrik — North America |
| `osm-germany` | `osm-pbf` | Geofabrik — Germany |
| `osm-france` | `osm-pbf` | Geofabrik — France |
| `osm-great-britain` | `osm-pbf` | Geofabrik — Great Britain |
| `osm-monaco` | `osm-pbf` | Geofabrik — Monaco (~663 KB, suitable for E2E testing) |
| `osm-niue` | `osm-pbf` | Geofabrik — Niue (~412 KB, suitable for E2E testing) |

### Adapters

| Adapter | Output format | Python library | Freshness check |
|---|---|---|---|
| `overture` | GeoParquet | `overturemaps` | release tag + bbox state file |
| `pmtiles` | PMTiles | `pmtiles` | ETag / Last-Modified / Content-Length |
| `osm-pbf` | OSM PBF | `osmium` | ETag / Last-Modified / Content-Length |
| `stac-cog` | GeoTIFF | `pystac_client` + `osgeo.gdal` | STAC item ID |

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

## Development

```bash
uv sync
uv run pytest tests/                          # unit tests (network-free)
uv run pytest tests/test_e2e_osm_pbf.py      # E2E tests (real network, Monaco/Niue)
SKIP_NETWORK_TESTS=1 uv run pytest tests/    # skip E2E
```

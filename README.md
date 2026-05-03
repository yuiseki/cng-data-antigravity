# cng-data-antigravity

cng-data-antigravity implements data antigravity for Cloud-Native Geospatial data sources.

An escape.yaml file describes how to discover, check freshness, extract, and repackage AOI-sized local outputs from heterogeneous CNG sources. cng-data-antigravity escaping only the geospatial data you need from cloud-native sources into reproducible local outputs.

## Naming contract

- Repository: `cng-data-antigravity`
- PyPI: `cng-data-antigravity`
- Import: `cng_data_antigravity`
- CLI: `cng-data-antigravity`
- Default config name: `escape.yaml`

## Invocation

```bash
cng-data-antigravity run
cng-data-antigravity run escape.yaml
cng-data-antigravity run /path/to/escape.yaml
```

If the config path is omitted, `cng-data-antigravity` looks for `escape.yaml` in the current working directory.

## First pass behavior

- reads `escape.yaml`
- iterates `extracts`
- runs a source-specific freshness check and extract step
- writes outputs under `output/<extract-id>/`
- writes `metadata.json` beside the extracted outputs

## Supported source types in the first pass

- `overture`
- `pmtiles`
- `geofabrik`
- `stac-cog`

## Status

This is the Python rewrite of the original PoC. It is intentionally still early:

- source adapters are thin wrappers around existing external tools and APIs
- the Overture adapter already uses the `overturemaps` Python API instead of shelling out to the CLI
- the PMTiles adapter now uses the `pmtiles` Python package for local and HTTP-backed bbox extraction
- packaging and portable output conventions are not finalized yet
- the current focus is establishing a clean Python core and stable `escape.yaml` contract

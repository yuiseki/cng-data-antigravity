from __future__ import annotations

from pathlib import Path

import pytest

from cng_data_antigravity.adapters import stac_static_cog as adapter
from cng_data_antigravity.config import AOIConfig, OutputConfig

# AOI used throughout: a small box around (10, 10).
_AOI = AOIConfig(bbox=[10.0, 10.0, 11.0, 11.0])

# A fake static STAC catalog tree. EventA intersects the AOI; EventB does not.
# Within EventA, acq1 intersects (and has items) while acq2 is pruned by extent.
# Items A1/A2 share a ground tile ("19/aaa"); B1 is a separate ground tile.
_CATALOG = "https://x/events/catalog.json"


def _item(item_id: str, bbox: list[float], dt: str, visual_href: str) -> dict:
    return {
        "type": "Feature",
        "id": item_id,
        "bbox": bbox,
        "properties": {"datetime": dt},
        "assets": {
            "visual": {
                "href": visual_href,
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "roles": ["visual"],
            }
        },
    }


_FAKE: dict[str, dict] = {
    _CATALOG: {
        "type": "Catalog",
        "links": [
            {"rel": "child", "href": "./EventA/collection.json"},
            {"rel": "child", "href": "./EventB/collection.json"},
        ],
    },
    "https://x/events/EventA/collection.json": {
        "type": "Collection",
        "id": "EventA",
        "extent": {"spatial": {"bbox": [[9.0, 9.0, 12.0, 12.0]]}},
        "links": [
            {"rel": "child", "href": "./ard/acq1_collection.json"},
            {"rel": "child", "href": "./ard/acq2_collection.json"},
        ],
    },
    "https://x/events/EventB/collection.json": {
        "type": "Collection",
        "id": "EventB",
        # Far from the AOI -> entire subtree must be pruned (and never fetched).
        "extent": {"spatial": {"bbox": [[50.0, 50.0, 51.0, 51.0]]}},
        "links": [{"rel": "child", "href": "./ard/acqX_collection.json"}],
    },
    "https://x/events/EventA/ard/acq1_collection.json": {
        "type": "Collection",
        "id": "acq1",
        "extent": {"spatial": {"bbox": [[9.5, 9.5, 11.5, 11.5]]}},
        "links": [
            {"rel": "item", "href": "./19/aaa/2024/strip1.json"},
            {"rel": "item", "href": "./19/aaa/2025/strip2.json"},
            {"rel": "item", "href": "./19/bbb/2023/strip1.json"},
        ],
    },
    "https://x/events/EventA/ard/acq2_collection.json": {
        "type": "Collection",
        "id": "acq2",
        # Outside the AOI -> pruned, its items never fetched.
        "extent": {"spatial": {"bbox": [[40.0, 40.0, 41.0, 41.0]]}},
        "links": [{"rel": "item", "href": "./should/not/fetch.json"}],
    },
    "https://x/events/EventA/ard/19/aaa/2024/strip1.json": _item(
        "19/aaa/strip1", [10.0, 10.0, 10.5, 10.5], "2024-01-01 00:00:00Z", "./strip1-visual.tif"
    ),
    "https://x/events/EventA/ard/19/aaa/2025/strip2.json": _item(
        "19/aaa/strip2", [10.0, 10.0, 10.5, 10.5], "2025-01-01 00:00:00Z", "./strip2-visual.tif"
    ),
    "https://x/events/EventA/ard/19/bbb/2023/strip1.json": _item(
        "19/bbb/strip1", [10.6, 10.6, 10.9, 10.9], "2023-01-01 00:00:00Z", "./strip1-visual.tif"
    ),
}


def _fetch(url: str) -> dict:
    if url not in _FAKE:
        raise AssertionError(f"unexpected fetch of pruned/unknown url: {url}")
    return _FAKE[url]


def test_bbox_intersects():
    assert adapter._bbox_intersects([10, 10, 11, 11], [10.5, 10.5, 12, 12])
    assert not adapter._bbox_intersects([10, 10, 11, 11], [11.1, 10, 12, 11])
    # touching edges count as intersecting
    assert adapter._bbox_intersects([10, 10, 11, 11], [11, 11, 12, 12])


def test_find_aoi_items_prunes_non_intersecting_subtrees():
    items = adapter.find_aoi_items(_CATALOG, _AOI.bbox, fetch=_fetch)
    ids = sorted(item["id"] for item, _ in items)
    # EventB (far away) and acq2 (far away) are pruned; their items never fetched.
    assert ids == ["19/aaa/strip1", "19/aaa/strip2", "19/bbb/strip1"]


def test_select_mece_dedupes_ground_tile_to_most_recent():
    items = adapter.find_aoi_items(_CATALOG, _AOI.bbox, fetch=_fetch)
    selected = adapter.select_mece_items(items)
    ids = sorted(item["id"] for item, _ in selected)
    # One image per ground tile: aaa -> newest (2025/strip2), bbb -> strip1.
    assert ids == ["19/aaa/strip2", "19/bbb/strip1"]


def test_collection_filter_restricts_to_one_event():
    items = adapter.find_aoi_items(_CATALOG, _AOI.bbox, collection="EventA", fetch=_fetch)
    assert len(items) == 3
    assert adapter.find_aoi_items(_CATALOG, _AOI.bbox, collection="EventB", fetch=_fetch) == []


def test_datetime_filter_narrows_window():
    items = adapter.find_aoi_items(
        _CATALOG, _AOI.bbox, datetime_filter="2024-06-01/2025-12-31", fetch=_fetch
    )
    ids = sorted(item["id"] for item, _ in items)
    # Only the 2025 acquisition falls inside the window.
    assert ids == ["19/aaa/strip2"]


def test_run_extract_writes_clipped_cogs_and_static_catalog(tmp_path: Path, monkeypatch):
    import json

    clips: list[tuple[str, str]] = []

    def fake_translate(src_href, dest, bbox):
        clips.append((src_href, Path(dest).name))
        assert bbox == _AOI.bbox
        Path(dest).write_bytes(b"fake-cog")

    monkeypatch.setattr(adapter, "gdal_translate_bbox", fake_translate)

    out = tmp_path / "maxar-opendata" / "catalog.json"
    source_info, source_state = adapter.run_stac_static_cog_extract(
        {"type": "stac-static-cog", "catalogUrl": _CATALOG, "asset": "visual"},
        _AOI,
        OutputConfig(format="stac-catalog", path="catalog.json"),
        out,
        force=False,
        prev_meta=None,
        fetch=_fetch,
    )

    assert source_state is None
    assert source_info["itemCount"] == 2
    assert source_info["itemIds"] == ["19/aaa/strip2", "19/bbb/strip1"]
    assert source_info["datetimeRange"] == ["2023-01-01 00:00:00Z", "2025-01-01 00:00:00Z"]

    # One clipped COG per MECE tile, sourced from the resolved asset href.
    assert clips == [
        ("https://x/events/EventA/ard/19/aaa/2025/strip2-visual.tif", "19_aaa_strip2.tif"),
        ("https://x/events/EventA/ard/19/bbb/2023/strip1-visual.tif", "19_bbb_strip1.tif"),
    ]
    out_dir = out.parent
    assert (out_dir / "19_aaa_strip2.tif").read_bytes() == b"fake-cog"
    assert (out_dir / "19_bbb_strip1.tif").exists()

    # A valid static STAC catalog linking to one Item per tile.
    catalog = json.loads(out.read_text())
    assert catalog["type"] == "Catalog"
    item_hrefs = sorted(l["href"] for l in catalog["links"] if l["rel"] == "item")
    assert item_hrefs == ["./19_aaa_strip2.json", "./19_bbb_strip1.json"]

    # Each Item points at its local clipped COG and carries a clipped bbox.
    stac_item = json.loads((out_dir / "19_aaa_strip2.json").read_text())
    assert stac_item["type"] == "Feature"
    assert stac_item["id"] == "19/aaa/strip2"
    assert stac_item["assets"]["visual"]["href"] == "./19_aaa_strip2.tif"
    # clipped bbox = intersection of item bbox [10,10,10.5,10.5] and AOI [10,10,11,11]
    assert stac_item["bbox"] == [10.0, 10.0, 10.5, 10.5]


def test_run_extract_skips_when_unchanged(tmp_path: Path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        adapter, "gdal_translate_bbox", lambda *a, **k: calls.append("clip")
    )

    out = tmp_path / "maxar-opendata" / "catalog.json"
    out.parent.mkdir(parents=True)
    out.write_text('{"type": "Catalog"}', encoding="utf-8")
    prev_meta = {"sourceInfo": {"itemIds": ["19/aaa/strip2", "19/bbb/strip1"]}}

    source_info, _ = adapter.run_stac_static_cog_extract(
        {"type": "stac-static-cog", "catalogUrl": _CATALOG, "asset": "visual"},
        _AOI,
        OutputConfig(format="stac-catalog", path="catalog.json"),
        out,
        force=False,
        prev_meta=prev_meta,
        fetch=_fetch,
    )

    assert calls == []
    assert out.read_text() == '{"type": "Catalog"}'
    assert source_info["itemIds"] == ["19/aaa/strip2", "19/bbb/strip1"]


def test_run_extract_raises_when_no_items(tmp_path: Path):
    far_aoi = AOIConfig(bbox=[100.0, 100.0, 101.0, 101.0])
    with pytest.raises(ValueError, match="No STAC item"):
        adapter.run_stac_static_cog_extract(
            {"type": "stac-static-cog", "catalogUrl": _CATALOG, "asset": "visual"},
            far_aoi,
            OutputConfig(format="stac-catalog", path="catalog.json"),
            tmp_path / "catalog.json",
            force=False,
            prev_meta=None,
            fetch=_fetch,
        )

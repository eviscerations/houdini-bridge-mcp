"""acquire_terrain — name a place, get Houdini-ready terrain.

One entry for the whole "place -> scene data" path: pick a trusted source (auto = US -> 3DEP, else
Copernicus GLO-30), fetch the covering DEM tiles into the working directory (skipping any already
present), then prep them to Houdini-ready tiles — either flat metric heightfields (`--mode flat`,
for a local scene via import_heightfield) or ECEF globe tiles (`--mode globe`, for assembly on
build_globe). Prints a JSON result the gateway relays to the AI client.

    python -m downloader.acquire --dest OUT --lat 47.6 --lon -122.3 --radius-m 8000 --mode flat
    python -m downloader.acquire --dest OUT --bbox -123 47 -117 49 --source 3dep --product 13 --mode globe

Egress is confined to the allowlisted source hosts (sources.py); no arbitrary URLs.
"""

import argparse
import json
import math
import os
import re

from . import global_dem, national_dem, opentopo, usgs_3dep
from .net import download
from .sources import USGS_3DEP_HOSTS

# CONUS-ish envelope for source auto-selection (3DEP is US-only; elsewhere fall back to global).
US_BBOX = (-125.0, 24.0, -66.5, 49.5)

# Tileset scale: a coarse->fine detail knob. (source, product) — "auto" lets pick_source choose
# US 3DEP vs global by location; product applies to 3DEP only. Adjustable in one place.
SCALE_TIERS = {
    "small": ("auto", "1"),    # ~30 m (3DEP 1 arc-second, or global Copernicus/SRTM)
    "med":   ("auto", "13"),   # ~10 m (3DEP 1/3 arc-second, or global)
    "large": ("1m", None),     # ~1 m  (3DEP 1 m lidar via TNM Access; US only)
}

# Authorization gate: high-res tiles (1 m DEM, Montana full-delivery quads) are large (~0.3–2 GB
# each). A typical 1 m environment is ~6–9 tiles (a square, ± peripheral). Beyond this the tool
# REFUSES rather than silently trimming or pulling many GB — the caller must narrow the area or
# explicitly raise max_tiles to authorize the larger download.
MAX_HIRES_TILES = 9
_TILE_KEY = re.compile(r"(x\d+y\d+)")


def _authorize_tile_count(count, kind, max_tiles):
    """Raise if `count` high-res tiles exceeds the authorized cap, with actionable guidance."""
    if count > max_tiles:
        raise SystemExit(
            f"[{kind}] {count} tiles cover this area — over the {max_tiles}-tile high-res limit "
            f"(large files). Narrow the bbox/radius, or re-run with a higher max_tiles to authorize."
        )


def bbox_from_point(lat, lon, radius_m):
    """A lat/lon bbox around a point given a radius in metres (approximate, WGS84 degrees)."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def _overlaps_us(bbox):
    return not (bbox[2] < US_BBOX[0] or bbox[0] > US_BBOX[2] or bbox[3] < US_BBOX[1] or bbox[1] > US_BBOX[3])


def pick_source(bbox, requested):
    if requested and requested != "auto":
        return requested
    return "3dep" if _overlaps_us(bbox) else "copernicus"


def fetch_1m_tiles(bbox, dest, max_tiles=MAX_HIRES_TILES, on_progress=None):
    """Fetch 3DEP 1 m tiles covering the bbox via TNM Access. TNM returns the same 10 km tile from
    several overlapping projects — dedupe by tile grid key (x{X}y{Y}), prefer the SMALLEST version
    (fastest download, full 1 m coverage either way), and skip a tile if ANY project's version is
    already on disk. Refuses if the count exceeds the authorized high-res cap. Returns [] if the
    bbox has no 1 m coverage (caller may fall back)."""
    import glob
    from . import usgs_1m
    items = usgs_1m.query(bbox, max_results=200)
    by_tile = {}
    for it in items:
        m = _TILE_KEY.search(it["url"])
        if not m:
            continue
        key = m.group(1)
        size = it.get("size") or float("inf")
        if key not in by_tile or size < (by_tile[key].get("size") or float("inf")):
            by_tile[key] = it

    chosen = list(by_tile.items())  # (key, item)
    _authorize_tile_count(len(chosen), "1m", max_tiles)

    paths = []
    for key, it in chosen:
        # Any project's version of this tile already on disk? Then use it — don't re-download.
        existing = glob.glob(os.path.join(dest, f"USGS_1M_*_{key}_*.tif"))
        if existing:
            paths.append(existing[0])
            continue
        paths.append(usgs_1m.fetch(it, dest, on_progress=on_progress))
    return paths


def find_quad_product(quad_dir, product):
    """Locate a product GeoTIFF inside an extracted quad delivery ({quad}/{project}/{PRODUCT}/*.tif).
    Prefers a file whose name ends `_{PRODUCT}.tif`. Returns the path or None."""
    import glob
    cands = glob.glob(os.path.join(quad_dir, "*", product, "*.tif"))
    cands = [c for c in cands if not c.lower().endswith((".aux.xml", ".ovr", ".xml"))]
    if not cands:
        return None
    exact = [c for c in cands if c.lower().endswith("_%s.tif" % product.lower())]
    return (exact or cands)[0]


def fetch_mt_lidar(bbox, dest, max_tiles=MAX_HIRES_TILES, on_progress=None):
    """Fetch full Montana lidar quad deliveries covering the bbox (extracting each quad tree) and
    return the bare-earth DEM tif per quad (for prep). Hillshades ride along in the extracted tree.
    Refuses if the quad count exceeds the authorized high-res cap (these are ~2 GB each)."""
    from . import montana_lidar
    quads = montana_lidar.quads_for_bbox(*bbox)
    _authorize_tile_count(len(quads), "mt_lidar", max_tiles)
    dems = []
    for quad in quads:
        qdir = montana_lidar.fetch_quad(quad, dest, on_progress=on_progress)
        dem = find_quad_product(qdir, "HFDEM") or find_quad_product(qdir, "DTM") or find_quad_product(qdir, "DSM")
        if dem:
            dems.append(dem)
        else:
            print(f"[mt_lidar] {quad}: no DEM product found under {qdir}")
    return dems


def fetch_tiles(source, bbox, dest, product="13", max_tiles=MAX_HIRES_TILES, on_progress=None):
    """Fetch every tile covering the bbox from `source` into `dest`; return the local file paths."""
    paths = []
    if source == "mt_lidar":
        return fetch_mt_lidar(bbox, dest, max_tiles=max_tiles, on_progress=on_progress)
    if source == "wa_lidar":
        # Washington DNR: DTM datasets intersecting the AOI (excluding the hillshade variants) ->
        # one clipped package. VERIFY-ON-FIRST-FETCH: extract layout / dataset selection.
        import glob
        from . import washington
        ds = [d for d in washington.datasets_for_bbox(bbox, want=("dtm",))
              if "hill" not in washington._norm(d["name"])]
        if not ds:
            return []
        outdir = washington.download_aoi(bbox, [d["id"] for d in ds][:max_tiles], dest, on_progress=on_progress)
        return sorted(t for t in glob.glob(os.path.join(outdir, "**", "*.tif"), recursive=True)
                      if "hill" not in t.lower())
    if source == "id_lidar":
        from . import idaho
        return [idaho.export_bbox(bbox, dest, on_progress=on_progress)]
    if source == "3dep":
        for tile in usgs_3dep.tiles_for_bbox(*bbox):
            existing = usgs_3dep.have_tile(dest, tile, product)
            if existing:
                paths.append(existing)
                continue
            url = usgs_3dep.url_for(tile, product)
            out = os.path.join(dest, usgs_3dep.filename_for(tile, product))
            download(url, out, USGS_3DEP_HOSTS, timeout=120, on_progress=on_progress)
            paths.append(out)
    elif source == "1m":
        paths = fetch_1m_tiles(bbox, dest, max_tiles=max_tiles, on_progress=on_progress)
    elif source in global_dem.SOURCES:
        fetch = global_dem.SOURCES[source]["fetch"]
        for lat, lon in global_dem.tiles_for_bbox(*bbox):
            paths.append(fetch(lat, lon, dest, on_progress=on_progress))
    elif source in national_dem.SOURCES:
        # National hi-res portals server-side-clip the WHOLE bbox to one GeoTIFF (WCS/WMS), so there is
        # no per-tile loop; the download() byte cap + WMS pixel clamp bound the size.
        paths.append(national_dem.SOURCES[source]["fetch"](bbox, dest, on_progress=on_progress))
    elif source in opentopo.DEMTYPES:
        # Keyed OpenTopography global lane (opt-in; only reached when HMCP_OPENTOPO_KEY is set). One
        # server-clipped GeoTIFF per bbox.
        paths.append(opentopo.fetch_globaldem(source, bbox, dest, on_progress=on_progress))
    else:
        raise SystemExit(f"unknown source '{source}'")
    return paths


def run(dest, bbox, source="auto", product="13", mode="flat", res=None, max_side=800, scale=None,
        max_tiles=MAX_HIRES_TILES):
    os.makedirs(dest, exist_ok=True)

    # A scale tier presets source/product; an explicit source still wins over the tier's source.
    if scale:
        tier_source, tier_product = SCALE_TIERS[scale]
        if source in (None, "auto"):
            source = tier_source
        if tier_product is not None:
            product = tier_product

    src = pick_source(bbox, source)
    tifs = fetch_tiles(src, bbox, dest, product, max_tiles=max_tiles)

    # 1 m is US-only (3DEP/TNM). Outside the US, first try a national hi-res portal that WHOLLY contains
    # the bbox (NL/UK/FR/ES/AU at 0.5-5 m); otherwise fall back to global Copernicus GLO-30 so a "large"
    # request still returns terrain everywhere.
    if src == "1m" and not tifs:
        natl = national_dem.pick_national(bbox)
        if natl:
            print(f"[1m] no US 1 m coverage — using national hi-res source '{natl}'.")
            src = natl
        else:
            print("[1m] no 1 m coverage for this bbox — falling back to Copernicus GLO-30.")
            src = "copernicus"
        tifs = fetch_tiles(src, bbox, dest, product, max_tiles=max_tiles)

    if mode == "globe":
        from . import prep_ecef
        prep_ecef.run(dest, tifs, max_side=max_side)
        outs = [os.path.join(dest, os.path.splitext(os.path.basename(t))[0] + "_ecef.npy") for t in tifs]
    else:
        from . import prep_flat
        prep_flat.run(dest, tifs, res=res)
        outs = [os.path.join(dest, os.path.splitext(os.path.basename(t))[0] + ".npy") for t in tifs]

    result = {"source": src, "mode": mode, "bbox": list(bbox), "tile_count": len(outs), "tiles": outs}

    # Full-delivery quads carry hillshades (+ other products); surface the hillshade per DEM as a
    # ready texture overlay for high-res renders.
    if src == "mt_lidar":
        textures = []
        for dem in tifs:
            quad_dir = os.path.dirname(os.path.dirname(os.path.dirname(dem)))
            hs = find_quad_product(quad_dir, "Hillshade")
            if hs:
                textures.append(hs)
        result["textures"] = textures
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch + prep real-world terrain for a place.")
    ap.add_argument("--dest", required=True, help="working directory (created if missing)")
    ap.add_argument("--lat", type=float, help="centre latitude (with --lon, --radius-m)")
    ap.add_argument("--lon", type=float, help="centre longitude")
    ap.add_argument("--radius-m", type=float, default=10_000, help="half-extent in metres around lat/lon")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"))
    # Built from the live registries so a newly-added source is selectable without editing this list.
    source_choices = (["auto", "3dep", "1m", "mt_lidar", "wa_lidar", "id_lidar"]
                      + list(global_dem.SOURCES) + list(national_dem.SOURCES) + list(opentopo.DEMTYPES))
    ap.add_argument("--source", default="auto", choices=source_choices,
                    help="auto (US->3DEP, else global), a global source (copernicus/srtm/aw3d30), a national "
                         "hi-res portal (nl_ahn/uk_dtm1/fr_rgealti/fr_lidarhd/es_mdt5/au_dem5), or a keyed "
                         "OpenTopography demtype (needs HMCP_OPENTOPO_KEY)")
    ap.add_argument("--product", default="13", choices=["1", "13"], help="3DEP product: 1 (~30m) or 13 (~10m)")
    ap.add_argument("--scale", default=None, choices=["small", "med", "large"],
                    help="detail tier: small ~30m, med ~10m, large ~1m (presets source/product)")
    ap.add_argument("--mode", default="flat", choices=["flat", "globe"])
    ap.add_argument("--res", type=float, default=None, help="flat: target metres (omit = native)")
    ap.add_argument("--max-side", type=int, default=800, help="globe: decimate each tile to this longest side")
    ap.add_argument("--max-tiles", type=int, default=MAX_HIRES_TILES,
                    help=f"high-res (1m/quad) tile cap before refusing (default {MAX_HIRES_TILES}); raise to authorize")
    a = ap.parse_args(argv)

    if a.bbox:
        bbox = tuple(a.bbox)
    elif a.lat is not None and a.lon is not None:
        bbox = bbox_from_point(a.lat, a.lon, a.radius_m)
    else:
        raise SystemExit("provide --bbox or --lat/--lon")

    result = run(a.dest, bbox, a.source, a.product, a.mode, a.res, a.max_side, a.scale, a.max_tiles)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

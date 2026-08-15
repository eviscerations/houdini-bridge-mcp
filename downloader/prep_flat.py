"""Prep DEM GeoTIFF tiles into flat metric heightfields for a local scene.

Turns each DEM GeoTIFF into a 2D float32 elevation `.npy` + a `.json` sidecar carrying exactly the
keys `import_heightfield` reads (cols, rows, res_m, houdini_center_x, houdini_center_z, nodata), so a
tile drops into Houdini at true elevation and true position. This is the FLAT path (a single local
region on the ground plane) — the first-light target. For continental assembly across UTM zones use
`prep_ecef` (the globe) instead.

Coordinate model: reproject to a project-local UTM zone (chosen from the first tile's centre), hold
ONE origin per project (the first tile's centre in that CRS), and place every later tile relative to
it → successive tiles share a frame and align. 1 unit = 1 m; the executor negates Z (north = -Z).

Reads GeoTIFFs at native resolution, or downsamples via the overview pyramid with --res (a coarser
target reads the .ovr, never a naive crush). Needs a rasterio-capable interpreter. No hardcoded
paths — dest + inputs are supplied by the caller.

    python -m downloader.prep_flat --dest OUT tileA.tif tileB.tif ...
    # --res 10  (target metres; omit = native) · --crs EPSG:XXXXX  (override the auto UTM zone)
"""

import argparse
import glob
import json
import os

import numpy as np

PROJECT_FILE = "hmcp_terrain_project.json"  # holds the shared CRS + origin for a dest folder


def utm_epsg(lat, lon):
    """EPSG code of the UTM zone containing (lat, lon)."""
    zone = int((lon + 180.0) / 6.0) % 60 + 1
    return (32600 if lat >= 0 else 32700) + zone


def _open_to_crs(path, dst_crs, target_res):
    """Read a GeoTIFF into `dst_crs`; return (data(rows,cols) f32, transform, res_m, nodata, src_crs)."""
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    with rasterio.open(path) as src:
        src_crs = src.crs.to_string() if src.crs else "unknown"
        nodata = src.nodata
        # native metres-per-pixel estimate for choosing overview reads (src may be in degrees)
        transform, w, h = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds,
            resolution=(target_res, target_res) if target_res else None,
        )
        dst = np.empty((h, w), dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=transform, dst_crs=dst_crs,
            resampling=Resampling.bilinear, src_nodata=nodata, dst_nodata=nodata,
        )
        res_m = float(transform.a)  # metric pixel size in the projected CRS
        return dst, transform, res_m, nodata, src_crs


def _center_lonlat(path):
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import transform as warp_transform
    with rasterio.open(path) as src:
        b = src.bounds
        cx = (b.left + b.right) / 2.0
        cz = (b.top + b.bottom) / 2.0
        lon, lat = warp_transform(src.crs, CRS.from_epsg(4326), [cx], [cz])
    return float(lon[0]), float(lat[0])


def _projected_extent(path, dst_crs, target_res):
    """The projected grid (transform, width, height, res) WITHOUT reading pixels — cheap enough to
    derive the project origin from the first tile's centre."""
    import rasterio
    from rasterio.warp import calculate_default_transform
    with rasterio.open(path) as src:
        tfm, w, h = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds,
            resolution=(target_res, target_res) if target_res else None,
        )
    return tfm, int(w), int(h), float(tfm.a)


def resolve_project(dest, inputs, cli_crs, target_res=None):
    """One CRS + origin per dest: persisted project > CLI CRS + first-tile origin > auto UTM."""
    proj_path = os.path.join(dest, PROJECT_FILE)
    if os.path.exists(proj_path):
        p = json.load(open(proj_path))
        return p["crs"], float(p["origin_x"]), float(p["origin_z"])

    lon, lat = _center_lonlat(inputs[0])
    crs = cli_crs or f"EPSG:{utm_epsg(lat, lon)}"
    tfm, w, h, res = _projected_extent(inputs[0], crs, target_res)
    ox = float(tfm.c) + (w * res) / 2.0    # first tile's centre in the chosen CRS
    oz = float(tfm.f) - (h * res) / 2.0
    os.makedirs(dest, exist_ok=True)
    json.dump({"crs": crs, "origin_x": ox, "origin_z": oz}, open(proj_path, "w"), indent=2)
    return crs, ox, oz


def prep_tile(path, dest, crs, origin_x, origin_z, target_res=None, make_hillshade=True):
    data, tfm, res, nodata, src_crs = _open_to_crs(path, crs, target_res)
    rows, cols = data.shape
    left = float(tfm.c); top = float(tfm.f)
    cx = left + (cols * res) / 2.0
    cz = top - (rows * res) / 2.0
    hc_x = cx - origin_x            # scene placement (NOT Z-negated; the executor negates Z)
    hc_z = cz - origin_z

    if nodata is not None:
        valid = data[data != nodata]
    else:
        valid = data[np.isfinite(data)]
    e_min = float(valid.min()) if valid.size else 0.0
    e_max = float(valid.max()) if valid.size else 0.0

    base = os.path.splitext(os.path.basename(path))[0]
    out_npy = os.path.join(dest, base + ".npy")
    np.save(out_npy, data)

    # Universal texture overlay: a hillshade GeoTIFF on this DEM's grid, derived from the elevation
    # itself — so the overlay works on any source, not only where a state ships a native hillshade.
    hs_path = None
    if make_hillshade:
        from . import hillshade
        elev = np.where(data == nodata, np.nan, data) if nodata is not None else data
        hs_path = os.path.join(dest, base + "_hillshade.tif")
        hillshade.write_geotiff(hillshade.compute(elev, res), hs_path, tfm, crs)

    sidecar = {
        "source": os.path.basename(path), "src_crs": src_crs, "dst_crs": crs,
        "cols": int(cols), "rows": int(rows), "res_m": float(res),
        "nodata": (None if nodata is None else float(nodata)),
        "houdini_center_x": hc_x, "houdini_center_z": hc_z,
        "origin_x": origin_x, "origin_z": origin_z,
        "elev_min": e_min, "elev_max": e_max,
        "hillshade": hs_path,
    }
    json.dump(sidecar, open(out_npy + ".json", "w"), indent=2)
    return out_npy, sidecar


def run(dest, inputs, res=None, crs=None, make_hillshade=True):
    expanded = []
    for item in inputs:
        if os.path.isdir(item):
            expanded += sorted(glob.glob(os.path.join(item, "*.tif")) + glob.glob(os.path.join(item, "*.tiff")))
        else:
            expanded += sorted(glob.glob(item)) or [item]
    if not expanded:
        raise SystemExit("no input GeoTIFFs matched")

    os.makedirs(dest, exist_ok=True)
    pcrs, ox, oz = resolve_project(dest, expanded, crs)
    print(f"[flat] {len(expanded)} tiles -> {dest}  CRS={pcrs}  origin=({ox:.1f},{oz:.1f})  res={res or 'native'}")
    for i, path in enumerate(expanded, 1):
        out, sc = prep_tile(path, dest, pcrs, ox, oz, res, make_hillshade)
        print(f"   [{i}/{len(expanded)}] {os.path.basename(path)} -> {os.path.basename(out)}  "
              f"{sc['cols']}x{sc['rows']} @ {sc['res_m']:.1f} m  center=({sc['houdini_center_x']:.0f},{sc['houdini_center_z']:.0f})  "
              f"elev {sc['elev_min']:.0f}..{sc['elev_max']:.0f} m")
    print(f"[flat] done - import each .npy with import_heightfield; all share origin ({ox:.1f},{oz:.1f}).")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prep DEM GeoTIFFs into flat metric heightfields.")
    ap.add_argument("inputs", nargs="+", help="GeoTIFF files, globs, or a directory")
    ap.add_argument("--dest", required=True, help="output directory for the .npy tiles")
    ap.add_argument("--res", type=float, default=None, help="target resolution in metres (omit = native)")
    ap.add_argument("--crs", default=None, help="override the auto UTM CRS, e.g. EPSG:32611")
    a = ap.parse_args(argv)
    run(a.dest, a.inputs, a.res, a.crs)


if __name__ == "__main__":
    main()

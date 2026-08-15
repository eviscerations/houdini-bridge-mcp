"""Prep DEM GeoTIFF tiles into ECEF-Houdini point grids for the geodetic globe.

Turns each 3DEP (or any-CRS) GeoTIFF into an (H,W,3) float32 `.npy` of Houdini-frame positions,
pinned to the WGS84 ellipsoid at true lon/lat/elevation, so tiles drape onto `build_globe` at their
correct place on Earth. Every tile in a run shares ONE anchor (persisted per project) → the whole
region assembles into a single, aligned frame — the "assemble the PNW on the globe" path.

The math matches the executor's `build_globe` helpers exactly (WGS84 `_geodetic_to_ecef`,
`_ecef_to_hou = (x,z,-y)`, `_enu_basis`), so a prepped tile and the globe register by construction.

Reads GeoTIFFs directly and decimates via rasterio overviews (low memory, any tile count). Needs a
rasterio-capable interpreter. No hardcoded paths — dest + inputs are supplied by the caller.

    python -m downloader.prep_ecef --dest OUT --max-side 800 tileA.tif tileB.tif ...
    # options: --anchor LON LAT (else the region centroid) · --level (ENU sit-flat) · --scale · --geoid
"""

import argparse
import glob
import json
import os

import numpy as np

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)

PROJECT_FILE = "hmcp_globe_project.json"  # holds the shared anchor for a dest folder


def geodetic_to_ecef(lon_deg, lat_deg, h):
    lon = np.radians(lon_deg)
    lat = np.radians(lat_deg)
    sl = np.sin(lat)
    cl = np.cos(lat)
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sl * sl)
    x = (n + h) * cl * np.cos(lon)
    y = (n + h) * cl * np.sin(lon)
    z = (n * (1.0 - WGS84_E2) + h) * sl
    return x, y, z


def ecef_to_hou(x, y, z):
    return x, z, -y  # north(+Z) -> +Y up, right-handed — matches the executor


def enu_basis(lon_deg, lat_deg):
    lo = np.radians(lon_deg)
    la = np.radians(lat_deg)
    sl = np.sin(la)
    cl = np.cos(la)
    so = np.sin(lo)
    co = np.cos(lo)
    e = (-so, 0.0, -co)
    u = (cl * co, sl, -cl * so)
    n = (-sl * co, cl, sl * so)
    return e, u, n


def _read_decimated(path, max_side):
    """Read a GeoTIFF decimated so its longest side <= max_side; return (elev, lons, lats, meta)."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.warp import transform as warp_transform

    with rasterio.open(path) as src:
        scale = max(src.width, src.height) / float(max_side)
        w = max(1, int(round(src.width / scale)))
        h = max(1, int(round(src.height / scale)))
        elev = src.read(1, out_shape=(h, w), resampling=Resampling.bilinear).astype(np.float64)
        tfm = src.transform * src.transform.scale(src.width / w, src.height / h)
        src_crs = src.crs
        nodata = src.nodata

    east = tfm.c + (np.arange(w) + 0.5) * tfm.a
    north = tfm.f + (np.arange(h) + 0.5) * tfm.e
    east_g, north_g = np.meshgrid(east, north)
    if nodata is not None:
        elev = np.where(elev == nodata, np.nan, elev)
    fill = float(np.nanmin(elev)) if np.isfinite(elev).any() else 0.0
    elev = np.nan_to_num(elev, nan=fill)

    lons, lats = warp_transform(src_crs, CRS.from_epsg(4326), east_g.ravel().tolist(), north_g.ravel().tolist())
    lons = np.asarray(lons).reshape(h, w)
    lats = np.asarray(lats).reshape(h, w)
    return elev, lons, lats, {"step": int(round(scale)), "src_crs": src_crs.to_string() if src_crs else "unknown"}


def _tile_center_lonlat(path):
    """Cheap lon/lat of a tile's center (for computing a shared anchor)."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import transform as warp_transform

    with rasterio.open(path) as src:
        b = src.bounds
        cx = (b.left + b.right) / 2.0
        cz = (b.top + b.bottom) / 2.0
        lon, lat = warp_transform(src.crs, CRS.from_epsg(4326), [cx], [cz])
    return float(lon[0]), float(lat[0])


def resolve_anchor(dest, inputs, cli_anchor):
    """One shared anchor per dest: CLI override > persisted project anchor > region centroid."""
    proj_path = os.path.join(dest, PROJECT_FILE)
    if cli_anchor is not None:
        anchor = (float(cli_anchor[0]), float(cli_anchor[1]))
    elif os.path.exists(proj_path):
        p = json.load(open(proj_path))
        anchor = (float(p["anchor_lon"]), float(p["anchor_lat"]))
    else:
        centers = [_tile_center_lonlat(p) for p in inputs]
        anchor = (sum(c[0] for c in centers) / len(centers), sum(c[1] for c in centers) / len(centers))
    # Persist so later runs (more tiles) share the exact frame.
    if not os.path.exists(proj_path):
        os.makedirs(dest, exist_ok=True)
        json.dump({"anchor_lon": anchor[0], "anchor_lat": anchor[1]}, open(proj_path, "w"), indent=2)
    return anchor


def prep_tile(path, dest, anchor, scale=1.0, level=False, geoid=0.0, max_side=800):
    elev, lons, lats, meta = _read_decimated(path, max_side)
    h, w = elev.shape

    alon, alat = anchor
    ax, ay, az = geodetic_to_ecef(np.array(alon), np.array(alat), np.array(0.0))
    ahx, ahy, ahz = ecef_to_hou(ax, ay, az)
    ahx, ahy, ahz = ahx * scale, ahy * scale, ahz * scale

    ex, ey, ez = geodetic_to_ecef(lons, lats, elev + geoid)
    hx, hy, hz = ecef_to_hou(ex, ey, ez)
    dx = hx * scale - ahx
    dy = hy * scale - ahy
    dz = hz * scale - ahz

    if level:
        e, u, n = enu_basis(alon, alat)
        dx, dy, dz = (
            dx * e[0] + dy * e[1] + dz * e[2],
            dx * u[0] + dy * u[1] + dz * u[2],
            -(dx * n[0] + dy * n[1] + dz * n[2]),
        )

    positions = np.stack([dx, dy, dz], axis=-1).astype(np.float32)  # (H,W,3) Houdini positions
    base = os.path.splitext(os.path.basename(path))[0]
    out_npy = os.path.join(dest, base + "_ecef.npy")
    np.save(out_npy, positions)
    sidecar = {
        "source": os.path.basename(path), "rows": int(h), "cols": int(w), "step": meta["step"],
        "src_crs": meta["src_crs"], "scale": scale, "level": bool(level), "geoid": geoid,
        "anchor": [alon, alat], "elev_min": float(elev.min()), "elev_max": float(elev.max()),
    }
    json.dump(sidecar, open(out_npy + ".json", "w"), indent=2)
    return out_npy, sidecar


def run(dest, inputs, anchor=None, scale=1.0, level=False, geoid=0.0, max_side=800):
    # Expand any globs/dirs the caller passed.
    expanded = []
    for item in inputs:
        if os.path.isdir(item):
            expanded += sorted(glob.glob(os.path.join(item, "*.tif")) + glob.glob(os.path.join(item, "*.tiff")))
        else:
            expanded += sorted(glob.glob(item)) or [item]
    if not expanded:
        raise SystemExit("no input GeoTIFFs matched")

    os.makedirs(dest, exist_ok=True)
    shared = resolve_anchor(dest, expanded, anchor)
    print(f"[ecef] {len(expanded)} tiles -> {dest}  shared anchor=({shared[0]:.4f},{shared[1]:.4f}) "
          f"scale={scale} level={level} max_side={max_side}")
    for i, path in enumerate(expanded, 1):
        out, sc = prep_tile(path, dest, shared, scale, level, geoid, max_side)
        print(f"   [{i}/{len(expanded)}] {os.path.basename(path)} -> {os.path.basename(out)}  "
              f"{sc['cols']}x{sc['rows']} (step {sc['step']}) elev {sc['elev_min']:.0f}..{sc['elev_max']:.0f} m")
    print(f"[ecef] done — {len(expanded)} tiles share anchor ({shared[0]:.4f},{shared[1]:.4f}); "
          f"build_globe with the same anchor to pin them.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prep DEM GeoTIFFs into ECEF-Houdini globe tiles.")
    ap.add_argument("inputs", nargs="+", help="GeoTIFF files, globs, or a directory")
    ap.add_argument("--dest", required=True, help="output directory for the _ecef.npy tiles")
    ap.add_argument("--anchor", nargs=2, type=float, metavar=("LON", "LAT"), help="shared anchor (default: region centroid)")
    ap.add_argument("--scale", type=float, default=1.0, help="1.0 = real metres; smaller = globe-overview units")
    ap.add_argument("--level", action="store_true", help="ENU sit-flat at the anchor (else pure ECEF curvature)")
    ap.add_argument("--geoid", type=float, default=0.0, help="geoid separation N (m) to add (PNW ~ -18 for NAVD88->ellipsoidal)")
    ap.add_argument("--max-side", type=int, default=800, help="decimate so the longest side <= this")
    a = ap.parse_args(argv)
    run(a.dest, a.inputs, a.anchor, a.scale, a.level, a.geoid, a.max_side)


if __name__ == "__main__":
    main()

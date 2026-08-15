"""Montana full-delivery lidar quads (Montana State Library, ftpgeoinfo.msl.mt.gov).

Each USGS 7.5' quad is a single `.zip` holding the COMPLETE delivery — DSM, HFDEM (bare earth),
Hillshade (+ .jpg), Intensity, CHM — in the project's subdir tree. Downloading + extracting a quad
preserves that structure locally (hillshades included, for texture overlays on high-res renders),
matching how the data ships.

Quad codes: `{lat_south}{lon_east}{row}{col}` — the 1°×1° cell named by its SE corner, subdivided
into an 8×8 grid of 7.5' quads; row = a..h SOUTH->north, col = 1..8 EAST->west. Verified against a
known tile (47115e2 spans lon -115.26..-115.11, lat 47.49..47.63).

This is a REGIONAL source (Montana). Other states publish equivalent portals under their own hosts;
add them to the registry + allowlist as they're found. Elsewhere the tool falls back to TNM 1 m DEM.
"""

import math
import os

from .net import download, safe_extractall
from .sources import STATE_LIDAR_HOSTS

MT_HOST = "ftpgeoinfo.msl.mt.gov"
MT_BASE = "https://ftpgeoinfo.msl.mt.gov/Data/Spatial/MSDI/Elevation/Lidar/Quads"
_ROWS = "abcdefgh"


def quad_for(lat, lon):
    """The 7.5' quad code covering (lat, lon)."""
    lat_s = int(math.floor(lat))              # cell south edge
    lon_e = int(-math.ceil(lon))              # cell east-edge magnitude (e.g. -115.2 -> 115)
    row = min(7, max(0, int((lat - lat_s) / 0.125)))          # a..h, south->north
    col = min(8, max(1, int(((-lon_e) - lon) / 0.125) + 1))   # 1..8, east->west
    return f"{lat_s}{lon_e:03d}{_ROWS[row]}{col}"


def quads_for_bbox(min_lon, min_lat, max_lon, max_lat):
    """Every quad whose 7.5' cell overlaps the bbox (stepped finer than a quad to miss none)."""
    quads = set()
    lat = min_lat
    while lat <= max_lat + 1e-9:
        lon = min_lon
        while lon <= max_lon + 1e-9:
            quads.add(quad_for(lat, lon))
            lon += 0.0625
        lat += 0.0625
    return sorted(quads)


def quad_url(quad):
    return f"{MT_BASE}/{quad}.zip"


def fetch_quad(quad, dest_dir, extract=True, max_bytes=4_000_000_000, timeout=1800, on_progress=None):
    """Download `{quad}.zip` into dest_dir and (default) extract to `dest_dir/{quad}/`, preserving
    the delivery tree. Skips work if the quad dir already exists. Returns the quad dir (or zip path
    when extract=False)."""
    out_dir = os.path.join(dest_dir, quad)
    if os.path.isdir(out_dir):
        return out_dir  # already have it
    zip_path = os.path.join(dest_dir, f"{quad}.zip")
    download(quad_url(quad), zip_path, STATE_LIDAR_HOSTS, max_bytes=max_bytes, timeout=timeout, on_progress=on_progress)
    if not extract:
        return zip_path
    safe_extractall(zip_path, out_dir)  # zip-slip-guarded (validates every member first)
    os.remove(zip_path)
    return out_dir

"""Global DEM sources — Copernicus GLO-30 and SRTM (both 30 m, anonymous S3, no key).

Tile naming uses the SW-corner (floor) convention, VERIFIED against live tile bounds: the Copernicus
`N47_00_W123_00` tile spans lon [-123, -122), i.e. the west label = -floor(lon). The same convention
holds for SRTM skadi tiles. So a point at (47.6, -122.3) is in tile N47 / W123 for both.

Copernicus tiles are prep-ready float32 GeoTIFF COGs. SRTM ships gzipped `.hgt`, which we decompress
to `.hgt` (rasterio reads it natively). These extend the tool's coverage beyond the US (3DEP) to
anywhere on Earth. Egress is confined to the allowlisted hosts in `sources.py`.
"""

import gzip
import math
import os
import shutil

from .net import download
from .sources import COPERNICUS_HOSTS, OPENTOPO_S3_HOSTS, SRTM_HOSTS

COPERNICUS_HOST = "copernicus-dem-30m.s3.amazonaws.com"
SRTM_HOST = "elevation-tiles-prod.s3.amazonaws.com"
AW3D30_HOST = "opentopography.s3.sdsc.edu"


def tile_labels(lat, lon):
    """(NS, EW) labels for the 1° tile containing (lat, lon), SW-corner/floor convention."""
    la = math.floor(lat)
    lo = math.floor(lon)
    ns = ("N" if la >= 0 else "S") + "%02d" % abs(la)
    ew = ("E" if lo >= 0 else "W") + "%03d" % abs(lo)
    return ns, ew


def tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
    """Interior points (lat, lon) — one per 1° tile — covering the bbox."""
    pts = []
    for la in range(int(math.floor(min_lat)), int(math.floor(max_lat)) + 1):
        for lo in range(int(math.floor(min_lon)), int(math.floor(max_lon)) + 1):
            pts.append((la + 0.5, lo + 0.5))
    return pts


# ---- Copernicus GLO-30 (global 30 m DSM, GeoTIFF COG) ----------------------------------------

def copernicus_tile(lat, lon):
    ns, ew = tile_labels(lat, lon)
    return "Copernicus_DSM_COG_10_%s_00_%s_00_DEM" % (ns, ew)


def copernicus_url(lat, lon):
    t = copernicus_tile(lat, lon)
    return "https://%s/%s/%s.tif" % (COPERNICUS_HOST, t, t)


def fetch_copernicus(lat, lon, dest_dir, max_bytes=500_000_000, timeout=120, on_progress=None):
    """Download the Copernicus GLO-30 tile for (lat, lon) into dest_dir; return the .tif path."""
    url = copernicus_url(lat, lon)
    path = os.path.join(dest_dir, copernicus_tile(lat, lon) + ".tif")
    download(url, path, COPERNICUS_HOSTS, max_bytes=max_bytes, timeout=timeout, on_progress=on_progress)
    return path


# ---- SRTM (global ~30 m, skadi .hgt.gz -> decompressed .hgt) ----------------------------------

def srtm_url(lat, lon):
    ns, ew = tile_labels(lat, lon)
    return "https://%s/skadi/%s/%s%s.hgt.gz" % (SRTM_HOST, ns, ns, ew)


def fetch_srtm(lat, lon, dest_dir, max_bytes=100_000_000, timeout=120, on_progress=None):
    """Download the SRTM skadi tile for (lat, lon), decompress to .hgt, return the .hgt path."""
    ns, ew = tile_labels(lat, lon)
    url = srtm_url(lat, lon)
    gz_path = os.path.join(dest_dir, "%s%s.hgt.gz" % (ns, ew))
    download(url, gz_path, SRTM_HOSTS, max_bytes=max_bytes, timeout=timeout, on_progress=on_progress)
    hgt_path = gz_path[:-3]  # drop .gz
    with gzip.open(gz_path, "rb") as src, open(hgt_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.remove(gz_path)
    return hgt_path


# ---- AW3D30 (ALOS World 3D 30 m, JAXA) via the anonymous OpenTopography mirror -----------------
# The same v3.2 tiles JAXA distributes behind its account-gated grid portal, served no-key over https
# from OpenTopography's public bucket. We use the GEOID (orthometric) tree `raster/AW3D30/`, so heights
# are datum-consistent with Copernicus GLO-30 (the ellipsoidal `AW3D30_E/` tree is deliberately NOT used).
# Tiles are 1-degree, SW-corner named with a 3-digit latitude: ALPSMLC30_N047W123_DSM.tif.

def aw3d30_tile(lat, lon):
    la = math.floor(lat)
    lo = math.floor(lon)
    ns = ("N" if la >= 0 else "S") + "%03d" % abs(la)
    ew = ("E" if lo >= 0 else "W") + "%03d" % abs(lo)
    return "ALPSMLC30_%s%s" % (ns, ew)


def aw3d30_url(lat, lon):
    return "https://%s/raster/AW3D30/AW3D30_global/%s_DSM.tif" % (AW3D30_HOST, aw3d30_tile(lat, lon))


def fetch_aw3d30(lat, lon, dest_dir, max_bytes=100_000_000, timeout=120, on_progress=None):
    """Download the AW3D30 (geoid) 30 m tile for (lat, lon) into dest_dir; return the .tif path.
    No key/login. Ocean-only cells have no tile (the source 404s) — the caller falls back like any tile."""
    url = aw3d30_url(lat, lon)
    path = os.path.join(dest_dir, aw3d30_tile(lat, lon) + "_DSM.tif")
    download(url, path, OPENTOPO_S3_HOSTS, max_bytes=max_bytes, timeout=timeout, on_progress=on_progress)
    return path


# ---- source registry (used by the top-level acquire dispatcher) ------------------------------

SOURCES = {
    "copernicus": {"label": "Copernicus GLO-30 (global 30 m)", "url": copernicus_url, "fetch": fetch_copernicus},
    "srtm": {"label": "SRTM (global ~30 m)", "url": srtm_url, "fetch": fetch_srtm},
    "aw3d30": {"label": "ALOS AW3D30 (global 30 m, JAXA via OpenTopography, no key)",
               "url": aw3d30_url, "fetch": fetch_aw3d30},
}

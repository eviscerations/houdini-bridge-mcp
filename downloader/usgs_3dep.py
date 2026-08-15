"""USGS 3DEP staged-products tile math + URL builder (no auth, from prd-tnm S3).

3DEP publishes seamless DEMs as 1°×1° GeoTIFF tiles named by their NORTHWEST corner: a tile
`nYYwXXX` covers latitude [YY-1, YY] and longitude [-XXX, -XXX+1]. e.g. `n48w123` covers
47–48°N, 123–122°W (contains Seattle). The `current` staged path serves the latest version of
each tile without needing the dated filename:

    https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/{P}/TIFF/current/{tile}/USGS_{P}_{tile}.tif

where P = 1 (1 arc-second, ~30 m) or 13 (1/3 arc-second, ~10 m). Building URLs from tile math
(rather than the TNM product list) sidesteps the TNM UI's 500-item export cap entirely.
"""

import glob
import math
import os

HOST = "prd-tnm.s3.amazonaws.com"

# product code -> (filename prefix, human label)
PRODUCTS = {
    "1": ("USGS_1", "1 arc-second (~30 m)"),
    "13": ("USGS_13", "1/3 arc-second (~10 m)"),
}


def tile_name(lat_nw, lon_w):
    """Tile id from its NW-corner latitude (int) and west-edge longitude magnitude (int)."""
    return f"n{lat_nw:02d}w{lon_w:03d}"


def url_for(tile, product="13"):
    prefix, _ = PRODUCTS[product]
    return f"https://{HOST}/StagedProducts/Elevation/{product}/TIFF/current/{tile}/{prefix}_{tile}.tif"


def filename_for(tile, product="13"):
    prefix, _ = PRODUCTS[product]
    return f"{prefix}_{tile}.tif"


def tiles_for_bbox(min_lon, min_lat, max_lon, max_lat):
    """Every 1° tile whose extent overlaps the bbox, as `nYYwXXX` ids.

    A tile with NW latitude L covers [L-1, L]; a tile with west label W covers lon [-W, -W+1].
    Longitudes are negative in the western hemisphere (min_lon < max_lon <= 0).
    """
    lat_start = int(math.floor(min_lat)) + 1      # smallest NW-lat covering the band
    lat_end = int(math.ceil(max_lat))
    lon_start = int(math.floor(-max_lon)) + 1      # smallest west label (eastmost tile)
    lon_end = int(math.ceil(-min_lon))             # largest west label (westmost tile)
    tiles = []
    for lat_nw in range(lat_start, lat_end + 1):
        for lon_w in range(lon_start, lon_end + 1):
            tiles.append(tile_name(lat_nw, lon_w))
    return tiles


def have_tile(dest_dir, tile, product="13"):
    """True if the destination already holds this tile in ANY version.

    Downloaded `current` files are `USGS_13_n48w118.tif`; TNM-portal files carry a date suffix
    (`USGS_13_n48w118_20260116.tif`). Match on the tile id so either counts as present.
    """
    prefix, _ = PRODUCTS[product]
    hits = glob.glob(os.path.join(dest_dir, f"{prefix}_{tile}*.tif"))
    return hits[0] if hits else None

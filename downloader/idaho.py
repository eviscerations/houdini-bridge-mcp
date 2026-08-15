"""Idaho lidar DTM (ISU GIS TReC / Idaho Lidar Consortium).

Two backends exist: a bulk per-quad zip index (giscenter-sl.isu.edu/AOC/AOC_DEM/Idaho/LidarDTM/)
and a statewide 1 m ArcGIS ImageServer mosaic. We use the ImageServer's `exportImage` for bbox
fetches — it returns a clipped GeoTIFF directly, with no fragile quad-name→bbox mapping. 1 m
bare-earth DTM; no auth.
"""

import math
import os
import urllib.parse

from .net import download
from .sources import STATE_LIDAR_HOSTS

ID_IMAGESERVER = "https://giscenter.rdc.isu.edu/server/rest/services/Lidar/Lidar_Idaho/ImageServer"


def export_bbox(bbox, dest_dir, out_name="id_lidar", target_res_m=1.0, max_px=4096, timeout=600, on_progress=None):
    """exportImage a lon/lat bbox as a float32 GeoTIFF, sized to ~target_res_m and capped at max_px
    per side (ArcGIS request limit). Returns the .tif path. prep reprojects it like any DEM."""
    min_lon, min_lat, max_lon, max_lat = bbox
    clat = (min_lat + max_lat) / 2.0
    w_m = (max_lon - min_lon) * 111_320.0 * math.cos(math.radians(clat))
    h_m = (max_lat - min_lat) * 111_320.0
    w = min(max_px, max(1, int(w_m / target_res_m)))
    h = min(max_px, max(1, int(h_m / target_res_m)))

    params = urllib.parse.urlencode({
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "bboxSR": "4326", "imageSR": "4326",
        "size": f"{w},{h}", "format": "tiff", "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation", "f": "image",
    })
    url = ID_IMAGESERVER + "/exportImage?" + params
    out = os.path.join(dest_dir, out_name + ".tif")
    download(url, out, STATE_LIDAR_HOSTS, max_bytes=1_000_000_000, timeout=timeout, on_progress=on_progress)
    return out

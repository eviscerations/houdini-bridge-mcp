"""Washington DNR Lidar Portal (lidarportal.dnr.wa.gov) — native full-delivery source.

A catalog endpoint (`/project`) lists projects, each with datasets carrying a lon/lat bbox and a
product `name` ("DTM", "DSM", "DTM Hillshade", "DSM Hillshade", "Point Cloud"; note occasional
data-entry typos, matched fuzzily). A `/download?geojson=<AOI>&ids=<dataset ids>` endpoint builds a
clipped zip of the requested products for an AOI — bare-earth DTM + native hillshade included. No
auth. This gives WA the same premium (DEM + native texture) tier as Montana.
"""

import json
import os
import urllib.parse

from .net import download, get_json, safe_extractall
from .sources import STATE_LIDAR_HOSTS

WA_BASE = "https://lidarportal.dnr.wa.gov"


def _norm(name):
    """Normalize a product name for fuzzy matching (the catalog has typos: 'Hillsahde', 'Cluod')."""
    return (name or "").lower().replace(" ", "")


def catalog(timeout=60):
    return get_json(WA_BASE + "/project", STATE_LIDAR_HOSTS, timeout=timeout)


def _intersects(ds, bbox):
    return not (ds["XMax"] < bbox[0] or ds["XMin"] > bbox[2] or ds["YMax"] < bbox[1] or ds["YMin"] > bbox[3])


def datasets_for_bbox(bbox, want=("dtm",), projects=None):
    """Datasets intersecting bbox whose normalized name contains any token in `want` (e.g. 'dtm',
    'dtmhillshade'). Excludes the hillshade variants when want=('dtm',) by checking 'hill' absence."""
    out = []
    for proj in (projects if projects is not None else catalog()):
        for ds in (proj.get("datasets") or []):
            if any(ds.get(k) is None for k in ("XMin", "YMin", "XMax", "YMax")):
                continue
            n = _norm(ds.get("name"))
            if _intersects(ds, bbox) and any(w in n for w in want):
                out.append({"id": ds["ID"], "name": ds.get("name"), "project": proj.get("name"),
                            "bbox": [ds["XMin"], ds["YMin"], ds["XMax"], ds["YMax"]]})
    return out


def download_aoi(bbox, ids, dest_dir, out_name="wa_lidar", max_bytes=4_000_000_000, timeout=1800, on_progress=None):
    """Download + extract the WA package (clipped to the bbox AOI) for the given dataset ids."""
    poly = {"type": "Polygon", "coordinates": [[
        [bbox[0], bbox[1]], [bbox[0], bbox[3]], [bbox[2], bbox[3]], [bbox[2], bbox[1]], [bbox[0], bbox[1]],
    ]]}
    query = urllib.parse.urlencode({"geojson": json.dumps(poly), "ids": ",".join(str(i) for i in ids)})
    url = WA_BASE + "/download?" + query
    zip_path = os.path.join(dest_dir, out_name + ".zip")
    download(url, zip_path, STATE_LIDAR_HOSTS, max_bytes=max_bytes, timeout=timeout, on_progress=on_progress)
    out_dir = os.path.join(dest_dir, out_name)
    safe_extractall(zip_path, out_dir)  # zip-slip-guarded (validates every member first)
    os.remove(zip_path)
    return out_dir

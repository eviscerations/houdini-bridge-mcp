"""USGS 1-meter DEM via the TNM Access API.

Unlike the seamless 1/3" and 1" products, 1 m DEM is delivered as project-based 10 km UTM tiles
(`USGS_1M_{zone}_x{X}y{Y}_{Project}.tif`) with no predictable path, so we discover them through the
TNM Access API and download the staged GeoTIFF. Both hosts (the API and the S3 bucket) are on the
egress allowlist. The prep pipeline (`prep_flat`/`prep_ecef`) already handles these GeoTIFFs — this
module only adds discovery + fetch.
"""

import os
import urllib.parse

from .net import download, get_json
from .sources import USGS_3DEP_HOSTS

TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"
DATASET_1M = "Digital Elevation Model (DEM) 1 meter"


def _project_of(url):
    return url.split("/Projects/")[1].split("/")[0] if "/Projects/" in url else ""


def query(bbox, max_results=50, project_contains=None):
    """Query TNM for 1 m DEM tiles overlapping bbox (min_lon,min_lat,max_lon,max_lat).

    Returns a list of {title, url, project, bbox:[minX,minY,maxX,maxY], size} dicts, optionally
    filtered to projects whose name contains `project_contains` (case-insensitive).
    """
    params = urllib.parse.urlencode({
        "datasets": DATASET_1M,
        "bbox": ",".join(str(x) for x in bbox),
        "prodFormats": "GeoTIFF",
        "outputFormat": "JSON",
        "max": max_results,
    })
    data = get_json(f"{TNM_API}?{params}", USGS_3DEP_HOSTS, timeout=60)

    items = []
    for it in data.get("items", []):
        url = it.get("downloadURL", "")
        if not url.endswith(".tif"):
            continue
        project = _project_of(url)
        if project_contains and project_contains.lower() not in project.lower():
            continue
        bb = it.get("boundingBox", {})
        items.append({
            "title": it.get("title"),
            "url": url,
            "project": project,
            "bbox": [bb.get("minX"), bb.get("minY"), bb.get("maxX"), bb.get("maxY")],
            "size": it.get("sizeInBytes"),
        })
    return items


def fetch(item_or_url, dest_dir, max_bytes=2_000_000_000, timeout=300, on_progress=None):
    """Download a 1 m tile (an item dict from `query` or a downloadURL) into dest_dir; return path."""
    url = item_or_url if isinstance(item_or_url, str) else item_or_url["url"]
    path = os.path.join(dest_dir, url.rsplit("/", 1)[-1])
    download(url, path, USGS_3DEP_HOSTS, max_bytes=max_bytes, timeout=timeout, on_progress=on_progress)
    return path

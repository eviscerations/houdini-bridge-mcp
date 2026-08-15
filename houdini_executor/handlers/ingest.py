"""Ingestion handlers -- native survey/GIS delivery formats (the geospatial moat). Params verified
against live H21.0.671. Each is a fresh-/obj generator that
FAILS on name collision (never destroys existing user work). Read paths are confinement-checked.
"""

import hou
from houdini_executor.server import endpoint, clamp, confined_path
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set






def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("geo", name)


_LAS_PREC = ("32", "64")  # lidarimport `precision` menu (live-probed) offers ONLY 32/64-bit
_LAS_LOAD = ("points", "infobbox", "info")
_LAS_COLOR = ("none", "from_ptcloud", "from_images")


@endpoint("las_import")
def las_import(params):
    """Native LAS/LAZ/E57 LIDAR ingestion (Houdini lidarimport SOP) -- the real survey/aerial delivery
    format (we otherwise only take .ply/.bgeo). name = new /obj geo (fails on collision). file =
    read-confined. max_points caps the load (0 = all). color: none|from_ptcloud|from_images.
    Optional attribute toggles: intensity, normals, classification, return_data, point_source.
    scale + centroid (metadata|calculated) handle georeferenced coordinates. Does NOT force the cook
    (heavy) -- set display=true or read it downstream to load points."""
    name = params["name"]
    path = confined_path(params["file"])
    geo = _fresh_geo(name)
    n = geo.createNode("lidarimport")
    n.parm("filename").set(path)
    prec = str(params.get("precision", "32"))
    if prec in _LAS_PREC:
        _try_set(n, "precision", prec)
    _menu_set(n, "loadtype", str(params.get("loadtype", "points")), _LAS_LOAD)
    if "max_points" in params:
        _try_set(n, "filter_type", 2)  # max_filter
        _try_set(n, "max_points", int(clamp(int(params["max_points"]), 0, 2_000_000_000)))
    _menu_set(n, "color", str(params.get("color", "none")), _LAS_COLOR)
    for key, parm in (("intensity", "intensity"), ("normals", "normals"),
                      ("classification", "classindex"), ("return_data", "ret_data"),
                      ("point_source", "pointsourceid")):
        if params.get(key):
            _try_set(n, parm, True)
    if params.get("delete_invalid"):
        _try_set(n, "delete_invalid", True)
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-9, 1e9))
    _menu_set(n, "centroid", str(params.get("centroid", "metadata")), ("metadata", "calculated"))
    disp = bool(params.get("display", False))
    n.setDisplayFlag(disp)
    n.setRenderFlag(True)
    geo.setDisplayFlag(disp)
    geo.layoutChildren()
    return {"node": geo.path(), "sop": n.path(), "file": path}


@endpoint("osm_import")
def osm_import(params):
    """Import OpenStreetMap roads/buildings/footprints for a site (Labs OSM Import) -- venue-context
    geometry (stadium/campus/street network). name = new /obj geo (fails on collision). file = .osm
    (read-confined). build_nodes extrudes 3D buildings; building_colors reads OSM building colors;
    close_only limits to closed building ways (default true)."""
    name = params["name"]
    path = confined_path(params["file"])
    geo = _fresh_geo(name)
    n = geo.createNode("labs::osm_import")
    _try_set(n, "osm_file", path)
    if params.get("build_nodes"):
        _try_set(n, "build_nodes", True)
    if params.get("building_colors"):
        _try_set(n, "read_building_colors", True)
    if "close_only" in params:
        _try_set(n, "only_close_buildings", bool(params["close_only"]))
    disp = bool(params.get("display", False))
    n.setDisplayFlag(disp)
    geo.setDisplayFlag(disp)
    geo.layoutChildren()
    return {"node": geo.path(), "sop": n.path(), "file": path}

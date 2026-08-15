"""Acquire / import handlers. Ported from proven logic; params verified against live H21.0.671.

Creators FAIL on name collision (never destroy existing user work).
"""

import json
import math
import hou
from houdini_executor.server import endpoint, confined_path, clamp
from houdini_executor.handlers._parmutil import _try_set


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)




# Alembic SOP authoring menus — live-probed on H21.0.671. Both are ordered menus (stored value is
# the index); accept a friendly token OR a raw int index for back-compat.
_ABC_GROUPNAMES = ("none", "shape", "xform", "basename", "xformbase")  # groupnames
_ABC_POLYSOUP = ("none", "polymesh", "subd")                          # polysoup (NOT a toggle)


@endpoint("create_geo")
def create_geo(params):
    """Empty geo object with an optional starting primitive SOP (box/sphere/grid/...)."""
    geo = _fresh_geo(params["name"])
    sop = None
    prim = params.get("prim")
    if prim:
        sop = geo.createNode(prim)
        sop.setDisplayFlag(True)
        sop.setRenderFlag(True)
        geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    return {"node": geo.path(), "sop": sop.path() if sop else None}


@endpoint("import_pointcloud")
def import_pointcloud(params):
    """Load / import a .ply or .bgeo point cloud (LIDAR/photogrammetry/scan points) through a File
    SOP (read-confined). up_axis 'z_up' -> a -90deg X rotation to bring Z-up survey data into
    Houdini's Y-up. Optional vectorized-VEX downsample (keep every Nth point) to lighten a heavy
    cloud; optional recenter to the origin. Returns point count + whether a Cd colour attribute is
    present. (LAS/LAZ/E57 go through las_import instead.)"""
    path = confined_path(params["path"])
    geo = _fresh_geo(params["name"])
    fsop = geo.createNode("file")
    fsop.parm("file").set(path)
    last = fsop
    if params.get("up_axis") == "z_up":
        rot = geo.createNode("xform")
        rot.setFirstInput(last)
        rot.parmTuple("r").set((-90.0, 0.0, 0.0))
        last = rot
    ds = int(params.get("downsample", 0) or 0)
    if ds > 1:
        dec = geo.createNode("attribwrangle")
        dec.parm("class").set(2)  # Points
        dec.setFirstInput(last)
        dec.parm("snippet").set(f"if (@ptnum % {ds} != 0) removepoint(0, @ptnum);")
        last = dec
    if params.get("recenter"):
        c = last.geometry().boundingBox().center()
        ctr = geo.createNode("xform")
        ctr.setFirstInput(last)
        ctr.parmTuple("t").set((-c[0], -c[1], -c[2]))
        last = ctr
    last.setDisplayFlag(True)
    last.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = last.geometry()
    return {"node": geo.path(), "sop": last.path(),
            "points": g.intrinsicValue("pointcount"),
            "has_color": g.findPointAttrib("Cd") is not None}


@endpoint("import_heightfield")
def import_heightfield(params):
    """DEM `.npy` + sidecar -> a real Houdini heightfield volume, placed at the tile's scene
    position (Z-negated). Elevation is injected by a SERVER-AUTHORED python SOP (fixed template;
    only the read-confined `.npy` path is interpolated via repr). Display OFF by default — a heavy
    heightfield tessellates hundreds of millions of voxels on the GPU and hangs the viewport.
    HARDENING NOTE: this is the one server-authored python SOP; the hardening pass considers
    replacing it with a cached-volume load to remove embedded code entirely.
    """
    npy = confined_path(params["npy"])
    meta = json.load(open(npy + ".json"))
    cols = int(meta["cols"])
    rows = int(meta["rows"])
    res = float(meta["res_m"])
    hcx = float(meta.get("houdini_center_x", 0.0))
    hcz = float(meta.get("houdini_center_z", 0.0))
    geo = _fresh_geo(params["name"])
    hf = geo.createNode("heightfield")
    for pn, pv in (("gridspacing", res), ("sizex", float(cols) * res), ("sizey", float(rows) * res),
                   ("gridsamples", int(max(cols, rows)))):
        p = hf.parm(pn)
        if p is not None:
            try:
                p.set(pv)
            except Exception:
                pass
    inj = geo.createNode("python", "inject")
    inj.setFirstInput(hf)
    inner = '''
import json, numpy as np, hou
node = hou.pwd(); geo = node.geometry()
NPY = %r
meta = json.load(open(NPY + ".json"))
arr = np.load(NPY).astype(np.float32)
nodata = meta.get("nodata")
if nodata is not None:
    arr = np.where(arr == nodata, np.nan, arr)
fill = float(np.nanmin(arr)) if np.isfinite(arr).any() else 0.0
arr = np.nan_to_num(arr, nan=fill)
hv = None
for p in geo.prims():
    if p.type() == hou.primType.Volume and geo.findPrimAttrib("name") and p.attribValue("name") == "height":
        hv = p; break
if hv is not None:
    rx, ry, rz = hv.resolution()
    a = arr
    if a.shape == (rx, ry) and rx != ry:
        a = a.T
    if a.size != rx * ry:
        ys = (np.arange(ry) * (a.shape[0] / float(ry))).astype(np.int64).clip(0, a.shape[0] - 1)
        xs = (np.arange(rx) * (a.shape[1] / float(rx))).astype(np.int64).clip(0, a.shape[1] - 1)
        a = a[ys][:, xs]
    hv.setAllVoxels(tuple(a.ravel().tolist()))
''' % npy.replace("\\", "/")
    inj.parm("python").set(inner)
    last = inj
    if hcx or hcz:
        x = geo.createNode("xform", "place")
        x.setFirstInput(inj)
        x.parmTuple("t").set((hcx, 0.0, -hcz))
        last = x
    display = bool(params.get("display", False))
    last.setDisplayFlag(display)
    last.setRenderFlag(True)
    geo.setDisplayFlag(display)
    geo.layoutChildren()
    last.cook(force=True)  # force: Manual mode defers node.geometry()
    og = last.geometry()
    hgt = None
    for pr in og.prims():
        if pr.type() == hou.primType.Volume and og.findPrimAttrib("name") and pr.attribValue("name") == "height":
            hgt = pr; break
    height_res = list(hgt.resolution()) if hgt is not None else None
    inject_errors = [str(e) for e in list(inj.errors())[:2]]
    return {"node": geo.path(), "output": last.path(),
            "cols": cols, "rows": rows, "res_m": res, "displayed": display,
            "height_res": height_res, "inject_errors": inject_errors}


@endpoint("import_geo")
def import_geo(params):
    """Load / import a mesh geometry file -- .obj, .bgeo/.bgeo.sc, .fbx, .stl, .ply, .geo and other
    File-SOP formats (read-confined). include_prim_types loads as packed geometry (flat-memory for
    heavy assets). Returns point + primitive counts. (Alembic .abc -> import_alembic; point clouds
    -> import_pointcloud; LAS/LAZ -> las_import.)"""
    path = confined_path(params["path"])
    geo = _fresh_geo(params["name"])
    f = geo.createNode("file")
    f.parm("file").set(path)
    if params.get("include_prim_types"):
        _try_set(f, "loadtype", "packedgeo")
    f.setDisplayFlag(True)
    f.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = f.geometry()
    return {"node": geo.path(), "sop": f.path(),
            "points": g.intrinsicValue("pointcount"),
            "prims": g.intrinsicValue("primitivecount")}


@endpoint("import_alembic")
def import_alembic(params):
    """Load / import an Alembic archive (.abc) -- animated/cached meshes, cameras and transforms --
    through an Alembic SOP (read-confined). groupnames controls how archive paths become primitive
    groups (none|shape|xform|basename|xformbase). polysoup loads polygons as memory-light polygon-soup
    primitives (none|polymesh|subd). Returns point + primitive counts."""
    path = confined_path(params["path"])
    geo = _fresh_geo(params["name"])
    a = geo.createNode("alembic")
    # SOP alembic path parm is `fileName`; fall back to `filename` across builds.
    if not _try_set(a, "fileName", path):
        _try_set(a, "filename", path)
    if "groupnames" in params:
        gv = params["groupnames"]
        if isinstance(gv, str) and gv in _ABC_GROUPNAMES:
            _try_set(a, "groupnames", _ABC_GROUPNAMES.index(gv))
        else:
            _try_set(a, "groupnames", int(gv))
    if "polysoup" in params:
        pv = params["polysoup"]
        if isinstance(pv, str) and pv in _ABC_POLYSOUP:
            _try_set(a, "polysoup", _ABC_POLYSOUP.index(pv))
        else:
            _try_set(a, "polysoup", int(bool(pv)) if isinstance(pv, bool) else int(pv))
    a.setDisplayFlag(True)
    a.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = a.geometry()
    return {"node": geo.path(), "sop": a.path(),
            "points": g.intrinsicValue("pointcount"),
            "prims": g.intrinsicValue("primitivecount")}


@endpoint("trace_raster")
def trace_raster(params):
    """Trace / vectorize an image raster (.png/.jpg/.tif, read-confined) into 2D outline curves via
    the Trace SOP -- turn a logo, silhouette, mask or map into polygon curves for extrude/sweep.
    threshold = brightness cutoff (0..1, real parm `thresh`); step = curve resample step (float,
    0.001..10; smaller = finer, more points). Returns the primitive (curve) count."""
    path = confined_path(params["file"])
    geo = _fresh_geo(params["name"])
    t = geo.createNode("trace")
    _try_set(t, "file", path)
    if "threshold" in params:
        _try_set(t, "thresh", clamp(float(params["threshold"]), 0.0, 1.0))  # real parm is `thresh`
    if "step" in params:
        _try_set(t, "step", clamp(float(params["step"]), 0.001, 10.0))  # `step` is a FLOAT resample step
    t.setDisplayFlag(True)
    t.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = t.geometry()
    return {"node": geo.path(), "sop": t.path(), "prims": g.intrinsicValue("primitivecount")}


# ── geodetic helpers (WGS84) for build_globe ─────────────────────────────────
def _geodetic_to_ecef(lon_deg, lat_deg, h=0.0):
    a_ = 6378137.0
    f_ = 1.0 / 298.257223563
    e2 = f_ * (2.0 - f_)  # WGS84
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    sl = math.sin(lat)
    cl = math.cos(lat)
    n = a_ / math.sqrt(1.0 - e2 * sl * sl)
    return ((n + h) * cl * math.cos(lon), (n + h) * cl * math.sin(lon), (n * (1.0 - e2) + h) * sl)


def _ecef_to_hou(x, y, z):
    return (x, z, -y)  # north(+Z) -> +Y up, right-handed (det +1)


def _enu_basis(lon_deg, lat_deg):
    """East/North/Up unit vectors at (lon,lat) in the Houdini frame (post ecef_to_hou)."""
    lo = math.radians(lon_deg)
    la = math.radians(lat_deg)
    sl = math.sin(la)
    cl = math.cos(la)
    so = math.sin(lo)
    co = math.cos(lo)
    e = (-so, 0.0, -co)
    u = (cl * co, sl, -cl * so)
    n = (-sl * co, cl, sl * so)
    return e, u, n


def _globe_material(name, texture, bump=None):
    """A /mat principledshader: equirectangular drape as base color + optional elevation bump."""
    mat = hou.node("/mat") or hou.node("/").createNode("mat")
    shn = name + "_drape"
    sh = mat.node(shn) or mat.createNode("principledshader::2.0", shn)
    if texture and sh.parm("basecolor_useTexture") is not None:
        sh.parm("basecolor_useTexture").set(1)
        sh.parm("basecolor_texture").set(texture)
    if bump and sh.parm("baseBump_bumpTexture") is not None:
        _try_set(sh, "baseBumpAndNormal_enable", 1)
        _try_set(sh, "baseBump_useTexture", 1)
        sh.parm("baseBump_bumpTexture").set(bump)
    return sh.path()


@endpoint("build_globe")
def build_globe(params):
    """Server-templated WGS84-ellipsoid globe (a=equatorial, b=polar) with an analytic lon/lat UV
    drape so an equirectangular texture registers with ECEF-pinned tiles by construction.

    anchor=[lon,lat] subtracts that surface point so local scene coords stay float-safe; with
    level=True the region is rotated into its East-North-Up frame to sit flat on the ground plane.
    texture/bump are read-confined. Display OFF by default (a dense sphere is heavy).
    """
    name = params["name"]
    a = float(params.get("a", 6378137.0))
    b = float(params.get("b", 6356752.314245))
    rows = int(clamp(int(params.get("rows", 180)), 4, 4000))
    cols = int(clamp(int(params.get("cols", 360)), 4, 4000))
    scale = float(params.get("scale", 1.0))
    uv = bool(params.get("uv", True))
    level = bool(params.get("level", False))
    display = bool(params.get("display", False))
    displace_amp = float(params.get("displace_amp", 0.0) or 0.0)
    texture = confined_path(params["texture"]) if params.get("texture") else None
    bump = confined_path(params["bump"]) if params.get("bump") else None
    anchor = params.get("anchor")

    anchor_ecef = None
    anchor_hou = None
    alon = alat = None
    if anchor is not None:
        alon, alat = float(anchor[0]), float(anchor[1])
        anchor_ecef = _geodetic_to_ecef(alon, alat, 0.0)
        h0 = _ecef_to_hou(*anchor_ecef)
        anchor_hou = (h0[0] * scale, h0[1] * scale, h0[2] * scale)

    geo = _fresh_geo(name)
    sph = geo.createNode("sphere")
    sph.parm("type").set("polymesh")
    _try_set(sph, "orient", "y")  # poles along Y = ECEF-Z (north)
    sph.parmTuple("rad").set((a * scale, b * scale, a * scale))
    sph.parm("rows").set(rows)
    sph.parm("cols").set(cols)
    last = sph
    if uv:
        # Analytic lon/lat UV from each point's own position (same ECEF frame as the pins), so an
        # equirectangular map registers with pinned tiles rather than following an arbitrary seam.
        w = geo.createNode("attribwrangle", "uv")
        w.setFirstInput(sph)
        w.parm("class").set(2)  # Points
        w.parm("snippet").set(
            'float lat = atan2(@P.y, sqrt(@P.x*@P.x + @P.z*@P.z));\n'
            'float lon = atan2(-@P.z, @P.x);\n'
            'v@uv = set(lon/(2.0*3.14159265358979)+0.5, lat/3.14159265358979+0.5, 0);')
        last = w
    if bump and displace_amp > 0:
        # Radial displacement from the elevation sampled at each point's uv (true relief is tiny;
        # displace_amp exaggerates it into a readable globe).
        dsp = geo.createNode("attribwrangle", "displace")
        dsp.setFirstInput(last)
        dsp.parm("class").set(2)
        dsp.parm("snippet").set(
            ('vector c = colormap(%r, v@uv.x, v@uv.y);\n'
             '@P += normalize(@P) * c.x * %r;') % (bump.replace("\\", "/"), displace_amp))
        last = dsp
    if texture or bump:
        sh = _globe_material(name, texture or "", bump)
        msop = geo.createNode("material", "drape")
        msop.setFirstInput(last)
        msop.parm("shop_materialpath1").set(sh)
        last = msop
    if anchor_hou is not None:
        if level:
            e, u, n = _enu_basis(alon, alat)
            wl = geo.createNode("attribwrangle", "level")
            wl.setFirstInput(last)
            wl.parm("class").set(2)
            wl.parm("snippet").set(
                ('vector E=set(%r,%r,%r); vector U=set(%r,%r,%r); vector N=set(%r,%r,%r);\n'
                 'vector AH=set(%r,%r,%r); vector d=@P-AH;\n'
                 '@P=set(dot(d,E),dot(d,U),-dot(d,N));') %
                (e[0], e[1], e[2], u[0], u[1], u[2], n[0], n[1], n[2],
                 anchor_hou[0], anchor_hou[1], anchor_hou[2]))
            last = wl
        else:
            xf = geo.createNode("xform", "anchor")
            xf.setFirstInput(last)
            xf.parmTuple("t").set((-anchor_hou[0], -anchor_hou[1], -anchor_hou[2]))
            last = xf
    last.setDisplayFlag(display)
    last.setRenderFlag(True)
    geo.setDisplayFlag(display)
    geo.layoutChildren()
    last.cook(force=True)
    og = last.geometry()
    bb = og.boundingBox()
    return {"node": geo.path(), "sop": last.path(), "a": a, "b": b, "scale": scale,
            "rows": rows, "cols": cols, "uv": uv, "anchor": anchor, "anchor_ecef": anchor_ecef,
            "level": level, "npts": len(og.points()), "nprims": len(og.prims()),
            "bbox": {"min": list(bb.minvec()), "max": list(bb.maxvec())}}


@endpoint("import_ecef_tile")
def import_ecef_tile(params):
    """Pin a prepped DEM tile onto the geodetic globe as a curved quad mesh at its TRUE position.

    Input is a prep_ecef `.npy` of shape (H,W,3): per-vertex Houdini-frame positions in the SAME
    ECEF frame as `build_globe`. Pair with a `build_globe` using the SAME anchor and every tile
    lands in registration on the ellipsoid. Topology comes from a native Grid SOP (rows=H, cols=W);
    a SERVER-AUTHORED python SOP overwrites P from the confined array in one bulk call (data-only —
    only the read-confined `.npy` path is interpolated, via repr). Display OFF by default.

    VERIFY-ON-ARM: grid rows/cols <-> array (H,W) point ordering — if the mesh looks transposed or
    shredded, swap rows<->cols (Houdini Grid numbers points row-major).
    """
    npy = confined_path(params["npy"])
    meta = json.load(open(npy + ".json"))
    rows = int(meta["rows"])
    cols = int(meta["cols"])
    geo = _fresh_geo(params["name"])
    grid = geo.createNode("grid")
    _try_set(grid, "orient", "zx")
    _try_set(grid, "rows", rows)
    _try_set(grid, "cols", cols)
    inj = geo.createNode("python", "pin")
    inj.setFirstInput(grid)
    inner = '''
import numpy as np, hou
node = hou.pwd(); geo = node.geometry()
P = np.load(%r).astype(np.float32).reshape(-1, 3)
if geo.intrinsicValue("pointcount") == int(P.shape[0]):
    geo.setPointFloatAttribValues("P", P.ravel().tolist())
''' % npy.replace("\\", "/")
    inj.parm("python").set(inner)
    display = bool(params.get("display", False))
    inj.setDisplayFlag(display)
    inj.setRenderFlag(True)
    geo.setDisplayFlag(display)
    geo.layoutChildren()
    inj.cook(force=True)  # force: Manual mode defers node.geometry()
    og = inj.geometry()
    return {"node": geo.path(), "output": inj.path(), "rows": rows, "cols": cols,
            "npts": len(og.points()), "nprims": len(og.prims()), "displayed": display}


# NOT REGISTERED in the public build. import_osm is the one network-egress endpoint: the Labs OSM
# Import SOP fetches from OSM/Overpass. Its egress gate (domain allowlist + rate-limit + size cap)
# lives on the gateway side and has NOT been built, and the executor registry — not the gateway
# catalog — is the real boundary once the loopback port is reachable. Registering it here would
# expose an uncapped, non-allowlisted fetch from inside Houdini (SSRF/egress + large-response DoS)
# to any token-bearing caller. Re-add the @endpoint("import_osm") decorator ONLY once the gateway
# egress gate exists and the tool is in the vetted catalog. (Security audit M1.)
def import_osm(params):
    """[+net] Import OpenStreetMap features into scene geometry via the Labs OSM Import SOP.

    HELD OUT of the public profile — see the block comment above. `bbox` = [min_lon, min_lat,
    max_lon, max_lat]. The gateway MUST domain-gate the fetch to an OSM/Overpass allowlist,
    rate-limit it, and cap the response size before this handler is ever registered.
    """
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::osm_import")
    bbox = params.get("bbox")
    if bbox and len(bbox) == 4:
        # osm_import was not in the parm probe; set through the probe-safe helper so an absent
        # parm is skipped rather than guessed. Confirm exact names on the next parm probe.
        vals = [float(x) for x in bbox]
        for pn, pv in (("minlong", vals[0]), ("minlat", vals[1]),
                       ("maxlong", vals[2]), ("maxlat", vals[3])):
            _try_set(n, pn, pv)
    if params.get("feature_class"):
        _try_set(n, "feature_class", str(params["feature_class"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    return {"node": geo.path(), "sop": n.path(), "bbox": bbox,
            "note": "network fetch is gateway-gated (OSM/Overpass allowlist + rate + size cap)"}

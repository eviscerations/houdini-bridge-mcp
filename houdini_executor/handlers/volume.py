"""SOP Volume / VDB lane — the Houdini 21 fog/SDF/VDB authoring & processing toolset:
create volumes and VDB grids, rasterize/convert/surface them, merge & composite, filter (feather /
ramp / noise / adjust), resample/resize/reduce/bound, build SDFs and velocity fields, and analyse.
Data-only handlers, params + menu tokens verified against live H21.0.671 via hython probe.

Input dialect (probe-confirmed):
  * GENERATORS — `volume_create` and `vdb_create` build a fresh volume/VDB primitive in a new /obj geo
    (like feather_template): they take a required `name` (the geo name) and no primary `input`.
  * Every other handler is an OPERATOR: `input` is input 0 (the volume/VDB/geometry to process),
    created with child_after; the node-specific extra inputs (point clouds, reference VDBs, curves,
    brushes, masks, cameras) are exposed as optional NodePath params named for their spec label and
    wired at the exact index with bridge_input. `_finish_op` reports counts once cooked and returns
    cooked:false + the node's errors when a node needs more of the network wired, so the AI can keep
    assembling instead of crashing.

SECURITY: NO file-path parm and NO code/callback parm is exposed by ANY handler in this lane. The
probe found the hidden `vex_cwdpath` file parm on the three factory-HDA noise/adjust nodes
(volumenoisefog / volumenoisesdf / volumeadjustfog) — their internal VEX is fixed and the user sets
only noise/adjust data params, so `vex_cwdpath` is EXCLUDED entirely. `volumerasterize` (which carries
vexsrc/script/shoppath code params) is deliberately NOT wrapped in this lane. `camera` parms
(volume_create, vdb_occlusion_mask) are NodePath scene references to a camera object — NOT files — and
are exposed as NodePath (set as an op-path string), never as a filesystem surface.
"""

import hou
from houdini_executor.server import (
    endpoint, child_after, clamp, resolve_node, bridge_input,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared helpers (probe-safe: never invent a parm) ──────────────────────────────────────────────
def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)






def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token: set the token directly (validated against the live token set)."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  m=index-menu(tokens)  ms=string-menu(tokens)."""
    for key, parm, kind, extra in spec:
        if key not in params:
            continue
        v = params[key]
        if kind == "f":
            _try_set(node, parm, clamp(float(v), extra[0], extra[1]))
        elif kind == "i":
            _try_set(node, parm, int(clamp(int(v), extra[0], extra[1])))
        elif kind == "b":
            _try_set(node, parm, bool(v))
        elif kind == "s":
            _try_set(node, parm, str(v))
        elif kind == "m":
            _menu_set(node, parm, str(v), extra)
        elif kind == "ms":
            _str_menu_set(node, parm, str(v), extra)


def _geo_or_none(n):
    """Return the node's geometry, or None if it hasn't cooked / errored (never raises opaquely)."""
    try:
        return n.geometry()
    except Exception:  # noqa: BLE001 — a cook error surfaces via n.errors() below, not a crash
        return None


def _finish_geo(geo, n):
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)
    geo.layoutChildren()
    g = _geo_or_none(n)
    if g is None:  # the generator MUST cook — surface the real diagnostic, not an opaque NoneType
        raise RuntimeError(f"{n.path()} failed to cook: " + "; ".join(n.errors()) or "no geometry")
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


def _finish_op(n, **extra):
    """child_after already set the display/render flags + showed the object. Report counts when the
    node has cooked; when it hasn't (a volume op that needs more of the network wired — e.g. a paint /
    velocity / rasterize node fed a bare volume), return cooked:false + the node's errors instead of
    crashing, so the AI can keep assembling the network and see what's missing."""
    r = {"node": n.path()}
    g = _geo_or_none(n)
    if g is None:
        r["cooked"] = False
        e = [str(x) for x in (n.errors() or [])]
        if e:
            r["errors"] = e
    else:
        r["cooked"] = True
        r["points"] = len(g.points())
        r["prims"] = len(g.prims())
    r.update(extra)
    return r


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GENERATORS — create fresh volume / VDB primitives (lane entry)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_create")
def volume_create(params):
    """Volume (volume) — GENERATOR: create a fresh Houdini scalar/vector volume primitive in a new /obj
    geo (a fog/density authoring source). type float/int; rank scalar/vector/matrix + components size
    the volume; volume_name names the grid; initialalpha the fill; zmin/zmax + use_cam_window/camera
    set a camera-frustum volume (camera is a NodePath scene reference, not a file). Fails on name
    collision. Feed the result as `input` to the other volume_* tools."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("volume", "volume")
    _apply(n, params, [
        ("type", "type", "m", ("float", "int")),
        ("rank", "rank", "m", ("scalar", "vector", "matrix")),
        ("components", "components", "i", (1, 4)),
        ("volume_name", "name", "s", None),
        ("initialalpha", "initialalpha", "f", (0.0, 10.0)),
        ("zmin", "zmin", "f", (0.0, 10.0)),
        ("zmax", "zmax", "f", (0.0, 10.0)),
        ("use_cam_window", "usecamwindow", "b", None),
        ("camera", "camera", "s", None),  # camera object path (NodePath scene ref), NOT a file
    ])
    return _finish_geo(geo, n)


@endpoint("vdb_create")
def vdb_create(params):
    """VDB (vdb) — GENERATOR: create a fresh empty typed VDB grid (level-set / fog / vector) in a new
    /obj geo — the VDB authoring source. grid_class picks the grid interpretation; grid_type the voxel
    type; grid_precision single/double; grid_name names the grid. Fails on name collision. NOTE: the
    node stores grids in a multiparm — this handler creates the first grid instance before setting its
    values, so a single call yields a usable VDB."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("vdb", "vdb")
    # The VDB SOP holds its grids in a multiparm; create the first instance so the grid params exist.
    for mp in ("numvdbs", "numgrids"):
        if _try_set(n, mp, 1):
            break
    _apply(n, params, [
        ("grid_class", "class1", "m", ("unknown", "level set", "fog volume", "staggered")),
        ("grid_type", "type1", "m", ("float", "int", "bool", "vecfloat", "vecint")),
        ("grid_precision", "precision1", "m", ("single", "double")),
    ])
    if "grid_name" in params:
        _try_set(n, "name1", str(params["grid_name"]))
    return _finish_geo(geo, n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RASTERIZE / SAMPLE — attrib->volume, volume->points, curves/paint->volume
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_from_attrib")
def volume_from_attrib(params):
    """Volume from Attribute (volumefromattrib) — rasterize a point/vertex attribute into a volume.
    `input` (input 0) is the Volume; `point_cloud` (input 1) the points carrying the attribute. attrib
    + useattrib pick the source attribute; calculationtype how samples combine; accumulate/extrapolate/
    maxextrapolate/threshold/bandwidth shape the deposit."""
    n = child_after(params["input"], "volumefromattrib", params.get("name"))
    if params.get("point_cloud"):
        bridge_input(n, params["point_cloud"], index=1, name_hint="point_cloud")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("pointgrp", "pointgrp", "s", None),
        ("useattrib", "useattrib", "b", None),
        ("attrib", "attrib", "s", None),
        ("disableonmissing", "disableonmissing", "b", None),
        ("accumulate", "accumulate", "b", None),
        ("extrapolate", "extrapolate", "b", None),
        ("usemaxextrapolate", "usemaxextrapolate", "b", None),
        ("maxextrapolate", "maxextrapolate", "f", (0.0, 10.0)),
        ("threshold", "threshold", "f", (0.0, 10.0)),
        ("bandwidth", "bandwidth", "f", (0.0, 10.0)),
        ("calculationtype", "calculationtype", "m",
         ("copy", "add", "sub", "mul", "div", "max", "min", "average")),
    ])
    return _finish_op(n)


@endpoint("points_from_volume")
def points_from_volume(params):
    """Points from Volume (pointsfromvolume) — scatter points inside a fog/SDF volume. `input` (input 0)
    is the geometry to fill. source auto/geometry/fog/sdf picks what defines the interior; pointmethod
    dense/sparse; particlesep the spacing; iso the surface level; invert flips inside/out;
    jitterseed/jitterscale randomize; converttofog + radiusscale finish the sampling."""
    n = child_after(params["input"], "pointsfromvolume", params.get("name"))
    _apply(n, params, [
        ("source", "source", "m", ("auto", "geometry", "fog", "sdf")),
        ("pointmethod", "pointmethod", "m", ("dense", "sparse")),
        ("invert", "invert", "b", None),
        ("inittype", "inittype", "m", ("grid", "tetrahedral")),
        ("particlesep", "particlesep", "f", (0.0, 10.0)),
        ("iso", "iso", "f", (-10.0, 10.0)),
        ("dominiso", "dominiso", "b", None),
        ("miniso", "miniso", "f", (-10.0, 10.0)),
        ("jitterseed", "jitterseed", "f", (0.0, 10.0)),
        ("jitterscale", "jitterscale", "f", (0.0, 10.0)),
        ("converttofog", "converttofog", "b", None),
        ("radiusscale", "radiusscale", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("paint_fog_volume")
def paint_fog_volume(params):
    """Volume Paint Fog (paintfogvolume) — procedurally deposit density into a fog volume. `input`
    (input 0) is the Projection Surface; `volume` (input 1) an existing volume to add to; `brush`
    (input 2) brush geometry. voxelsize the resolution; densityscale/stroke_opacity/flowrate the amount
    laid down; stroke_radius the footprint; mergemethod how it composites; reprojection where strokes
    land. NOTE: designed as a viewport brush — headless it deposits along its stroke settings."""
    n = child_after(params["input"], "paintfogvolume", params.get("name"))
    if params.get("volume"):
        bridge_input(n, params["volume"], index=1, name_hint="volume")
    if params.get("brush"):
        bridge_input(n, params["brush"], index=2, name_hint="brush")
    _apply(n, params, [
        ("voxelsize", "voxelsize", "f", (0.0, 10.0)),
        ("densityscale", "densityscale", "f", (0.0, 10.0)),
        ("fastrasterize", "fastrasterize", "b", None),
        ("stroke_opacity", "stroke_opacity", "f", (0.0, 10.0)),
        ("samplerate", "samplerate", "f", (0.0, 5.0)),
        ("stroke_radius", "stroke_radius", "f", (0.0, 1.0)),
        ("fade", "fade", "f", (0.0, 1.0)),
        ("useflow", "useflow", "b", None),
        ("flowrate", "flowrate", "f", (0.0, 10.0)),
        ("mergemethod", "mergemethod", "m", ("add", "max", "min", "mul")),
        ("reprojection", "reprojection", "m", ("none", "ray", "primuv")),
        ("stroke_projtype", "stroke_projtype", "m", ("xy", "yz", "zx", "screen", "geometry")),
    ])
    return _finish_op(n)


@endpoint("volume_rasterize_curve")
def volume_rasterize_curve(params):
    """Volume Rasterize Curve (volumerasterizecurve) — rasterize curves into a fog volume (density laid
    along the curves). `input` (input 0) is the base Volume; `curve` (input 1) the curves to rasterize;
    `brush` (input 2) brush geometry. voxelsize the resolution; widthscale/densityscale/flowrate the
    deposited amount; samplerate the sampling; mergemethod how it composites; output picks the output
    slot."""
    n = child_after(params["input"], "volumerasterizecurve", params.get("name"))
    if params.get("curve"):
        bridge_input(n, params["curve"], index=1, name_hint="curve")
    if params.get("brush"):
        bridge_input(n, params["brush"], index=2, name_hint="brush")
    _apply(n, params, [
        ("output", "output", "m", ("0", "1", "2")),
        ("voxelsize", "voxelsize", "f", (0.0, 10.0)),
        ("widthscale", "widthscale", "f", (0.0, 10.0)),
        ("fastcomposite", "fastcomposite", "b", None),
        ("fastrasterize", "fastrasterize", "b", None),
        ("densityscale", "densityscale", "f", (0.0, 10.0)),
        ("samplerate", "samplerate", "f", (0.0, 5.0)),
        ("fade", "fade", "f", (0.0, 10.0)),
        ("useflow", "useflow", "b", None),
        ("flowrate", "flowrate", "f", (0.0, 10.0)),
        ("mergemethod", "mergemethod", "m", ("add", "max", "min", "mul")),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# CONVERT / SURFACE
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_convert")
def volume_convert(params):
    """Convert Volume (convertvolume) — convert a VDB/volume to a polygonal surface via marching cubes.
    `input` (input 0) is the geometry to surface. iso the surface level; invert flips inside/out; lod
    the polygon density; computenml adds normals; buildpolysoup emits a lighter polygon-soup mesh.
    (Endpoint named volume_convert to avoid the existing convert_volume tool.)"""
    n = child_after(params["input"], "convertvolume", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("iso", "iso", "f", (0.0, 10.0)),
        ("invert", "invert", "b", None),
        ("lod", "lod", "f", (0.0, 10.0)),
        ("computenml", "computenml", "b", None),
        ("buildpolysoup", "buildpolysoup", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_surface")
def volume_surface(params):
    """Volume Surface (volumesurface) — build a polygon surface from a fog/SDF volume hierarchy with
    adaptive edge length. `input` (input 0) is the volume hierarchy to surface; `edge_length_volume`
    (input 1) an optional volume driving local edge length. offset the iso offset; invert flips
    inside/out; overlap/tol/curvaturedist/edgescale/minedge/maxedge/maxchange control the adaptive
    tessellation; closegap seals boundary holes."""
    n = child_after(params["input"], "volumesurface", params.get("name"))
    if params.get("edge_length_volume"):
        bridge_input(n, params["edge_length_volume"], index=1, name_hint="edge_length_volume")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("offset", "offset", "f", (0.0, 10.0)),
        ("invert", "invert", "b", None),
        ("finestres", "finestres", "b", None),
        ("overlap", "overlap", "f", (0.0, 0.5)),
        ("strictbounds", "strictbounds", "b", None),
        ("tol", "tol", "f", (0.0, 10.0)),
        ("curvaturedist", "curvaturedist", "f", (0.0, 10.0)),
        ("edgescale", "edgescale", "f", (0.0, 10.0)),
        ("minedge", "minedge", "f", (0.0, 10.0)),
        ("maxedge", "maxedge", "f", (0.0, 10.0)),
        ("maxchange", "maxchange", "f", (0.0, 1.0)),
        ("closegap", "closegap", "b", None),
    ])
    return _finish_op(n)


@endpoint("extrude_volume")
def extrude_volume(params):
    """Extrude Volume (extrudevolume) — extrude polygons into a solid volume along the base normal.
    `input` (input 0) is the polygons to extrude. depth the extrusion depth (negative); flat keeps a
    flat base; basepadding/baselift shape the base; the output*grp toggles + *grp names emit
    top/base/side groups on the result."""
    n = child_after(params["input"], "extrudevolume", params.get("name"))
    _apply(n, params, [
        ("depth", "depth", "f", (-10.0, 0.0)),
        ("flat", "flat", "b", None),
        ("basepadding", "basepadding", "f", (0.0, 1.0)),
        ("baselift", "baselift", "f", (0.0, 10.0)),
        ("outputtopgrp", "outputtopgrp", "b", None),
        ("topgrp", "topgrp", "s", None),
        ("outputbasegrp", "outputbasegrp", "b", None),
        ("basegrp", "basegrp", "s", None),
        ("outputsidegrp", "outputsidegrp", "b", None),
        ("sidegrp", "sidegrp", "s", None),
    ])
    return _finish_op(n)


@endpoint("convert_vdb_points")
def convert_vdb_points(params):
    """Convert VDB Points (convertvdbpoints) — convert between point clouds and VDB Points grids.
    `input` (input 0) is the points to convert; `ref_vdb` (input 1) an optional reference VDB supplying
    the transform. conversion vdb/hdk/mask/count picks the direction; transform how the output voxel
    layout is chosen; voxelsize/pointspervoxel size the grid; poscompression the position storage;
    output_grid_name names the output grid."""
    n = child_after(params["input"], "convertvdbpoints", params.get("name"))
    if params.get("ref_vdb"):
        bridge_input(n, params["ref_vdb"], index=1, name_hint="ref_vdb")
    _apply(n, params, [
        ("conversion", "conversion", "m", ("vdb", "hdk", "mask", "count")),
        ("group", "group", "s", None),
        ("vdbpointsgroup", "vdbpointsgroup", "s", None),
        ("output_grid_name", "name", "s", None),
        ("outputname", "outputname", "ms", ("keep", "append", "replace")),
        ("countname", "countname", "s", None),
        ("maskname", "maskname", "s", None),
        ("keep", "keep", "b", None),
        ("transform", "transform", "m", ("targetpointspervoxel", "voxelsizeonly", "userefvdb")),
        ("voxelsize", "voxelsize", "f", (1e-05, 5.0)),
        ("pointspervoxel", "pointspervoxel", "i", (1, 16)),
        ("poscompression", "poscompression", "m", ("none", "int16", "int8")),
        ("mode", "mode", "m", ("all", "spec")),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# MERGE / COMPOSITE
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_merge")
def volume_merge(params):
    """Volume Merge (volumemerge) — merge/composite volumes with a full pre/post add-mul stack. `input`
    (input 0) is the Base Volume; `merge_volumes` (input 1) the volumes to merge in. mergemethod
    copy/add/mul/max/min/average; dstpreadd/dstpremul & srcpreadd/srcpremul pre-scale each side;
    postadd/postmul scale the result; doclampmin/clampmin & doclampmax/clampmax clamp it; clampvolume
    clamps to the base bounds."""
    n = child_after(params["input"], "volumemerge", params.get("name"))
    if params.get("merge_volumes"):
        bridge_input(n, params["merge_volumes"], index=1, name_hint="merge_volumes")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("mergegrp", "mergegrp", "s", None),
        ("mergemethod", "mergemethod", "m", ("copy", "add", "mul", "max", "min", "average")),
        ("clampvolume", "clampvolume", "b", None),
        ("dstpreadd", "dstpreadd", "f", (0.0, 10.0)),
        ("dstpremul", "dstpremul", "f", (0.0, 10.0)),
        ("srcpreadd", "srcpreadd", "f", (0.0, 10.0)),
        ("srcpremul", "srcpremul", "f", (0.0, 10.0)),
        ("postadd", "postadd", "f", (0.0, 10.0)),
        ("postmul", "postmul", "f", (0.0, 10.0)),
        ("doclampmin", "doclampmin", "b", None),
        ("clampmin", "clampmin", "f", (0.0, 10.0)),
        ("doclampmax", "doclampmax", "b", None),
        ("clampmax", "clampmax", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("vdb_merge")
def vdb_merge(params):
    """VDB Merge (vdbmerge) — merge multiple VDB grids of matching name into one. `input` (input 0) is
    the VDBs to merge. collation picks how grids are grouped (by name / primitive number / all);
    resampleinterp the resampling when transforms differ; op_fog how fog grids combine (none/add);
    op_sdf how SDF grids combine (none/union/intersect)."""
    n = child_after(params["input"], "vdbmerge", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("collation", "collation", "ms", ("name", "primitive_number", "all")),
        ("resampleinterp", "resampleinterp", "m", ("point", "linear", "quadratic")),
        ("op_fog", "op_fog", "ms", ("none", "add")),
        ("op_sdf", "op_sdf", "ms", ("none", "sdfunion", "sdfintersect")),
    ])
    return _finish_op(n)


@endpoint("volume_vector_join")
def volume_vector_join(params):
    """Volume Vector Join (volumevectorjoin) — join three (or four) scalar volumes into one vector
    volume. `input` (input 0) is the volumes to join. xgroup/ygroup/zgroup/wgroup name the component
    volumes (default @name=*.x etc); setcomponents + components force the output vector size; keep
    retains the source scalar volumes."""
    n = child_after(params["input"], "volumevectorjoin", params.get("name"))
    _apply(n, params, [
        ("setcomponents", "setcomponents", "b", None),
        ("components", "components", "i", (1, 4)),
        ("xgroup", "xgroup", "s", None),
        ("ygroup", "ygroup", "s", None),
        ("zgroup", "zgroup", "s", None),
        ("wgroup", "wgroup", "s", None),
        ("keep", "keep", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_vector_split")
def volume_vector_split(params):
    """Volume Vector Split (volumevectorsplit) — split a vector volume into three scalar volumes.
    `input` (input 0) is the volumes to split. group restricts which volumes are split; keep retains
    the source vector volume alongside the scalar outputs."""
    n = child_after(params["input"], "volumevectorsplit", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("keep", "keep", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# FILTER / LOOK — feather, ramp, noise, adjust
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_feather")
def volume_feather(params):
    """Volume Feather (volumefeather) — soften (feather) a volume's values near its border. `input`
    (input 0) is the volume. decaymode picks how the feather falls off (decay / decayvoxel / unitdist /
    unitvoxel / angle) with the matching decay/decayvoxel/unitdist/unitvoxel/angle amount; outside
    feathers outward; detect2d treats flat volumes as 2D; bordertype + borderval define the edge
    condition."""
    n = child_after(params["input"], "volumefeather", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("decaymode", "decaymode", "m", ("decay", "decayvoxel", "unitdist", "unitvoxel", "angle")),
        ("decay", "decay", "f", (0.0, 10.0)),
        ("decayvoxel", "decayvoxel", "f", (0.0, 10.0)),
        ("unitdist", "unitdist", "f", (0.0, 10.0)),
        ("unitvoxel", "unitvoxel", "f", (0.0, 10.0)),
        ("angle", "angle", "f", (0.0, 90.0)),
        ("outside", "outside", "b", None),
        ("detect2d", "detect2d", "b", None),
        ("bordertype", "bordertype", "m", ("none", "constant", "repeat", "streak")),
        ("borderval", "borderval", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("volume_ramp")
def volume_ramp(params):
    """Volume Ramp (volumeramp) — remap a volume's values through a source->dest range. `input` (input 0)
    is the volume to remap. volume_name selects which grid; primitive the primitive number; srcmin/srcmax
    the input range read; destmin/destmax the output range written; usecolor switches to a colour
    remap. (The interactive ramp curves are left at their node defaults.)"""
    n = child_after(params["input"], "volumeramp", params.get("name"))
    _apply(n, params, [
        ("primitive", "primitive", "i", (0, 10)),
        ("volume_name", "name", "s", None),
        ("srcmin", "srcmin", "f", (0.0, 1.0)),
        ("srcmax", "srcmax", "f", (0.0, 1.0)),
        ("destmin", "destmin", "f", (0.0, 1.0)),
        ("destmax", "destmax", "f", (0.0, 1.0)),
        ("usecolor", "usecolor", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_noise_fog")
def volume_noise_fog(params):
    """Volume Noise Fog (volumenoisefog) — add layered noise to a fog volume for density detailing.
    `input` (input 0) is the fog volume. vol names the grid; operation how the noise combines
    (set/add/sub/mult/min/max); amplitude the strength; rangemethod + minvalue/maxvalue/midvalue/
    rangevalue remap the noise range; usealphamask/maskweight/invertmask/maskvolumename gate it by a
    mask; outputraw writes the raw noise. SECURITY: the hidden vex_cwdpath file parm is NOT exposed."""
    n = child_after(params["input"], "volumenoisefog", params.get("name"))
    _apply(n, params, [
        ("usealphamask", "usealphamask", "b", None),
        ("maskweight", "maskweight", "f", (0.0, 1.0)),
        ("invertmask", "invertmask", "b", None),
        ("maskvolumename", "maskvolumename", "s", None),
        ("vol", "vol", "s", None),
        ("operation", "operation", "m", ("set", "add", "sub", "mult", "min", "max")),
        ("rangemethod", "rangemethod", "m",
         ("positive", "negative", "zcentered", "minmax", "minplusrange", "midplusminusrange")),
        ("amplitude", "amplitude", "f", (0.0, 10.0)),
        ("minvalue", "minvalue", "f", (0.0, 1.0)),
        ("maxvalue", "maxvalue", "f", (0.0, 1.0)),
        ("midvalue", "midvalue", "f", (0.0, 10.0)),
        ("rangevalue", "rangevalue", "f", (0.0, 10.0)),
        ("outputraw", "outputraw", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_noise_sdf")
def volume_noise_sdf(params):
    """Volume Noise SDF (volumenoisesdf) — add layered noise to an SDF volume for surface detailing.
    `input` (input 0) is the SDF volume. vol names the grid; displacement how the surface is pushed
    (normal / closestpoint / vector); amplitude/amplitudev the strength; banding + halfwidth/
    halfwidthworld rebuild the narrow band; rangemethod remaps the noise; doblend/blendweight/blendmode/
    blendvol blend it back. SECURITY: the hidden vex_cwdpath file parm is NOT exposed."""
    n = child_after(params["input"], "volumenoisesdf", params.get("name"))
    _apply(n, params, [
        ("doblend", "doblend", "b", None),
        ("blendweight", "blendweight", "f", (0.0, 1.0)),
        ("blendmode", "blendmode", "m", ("value", "vol")),
        ("blendvol", "blendvol", "s", None),
        ("vol", "vol", "s", None),
        ("displacement", "displacement", "m", ("normal", "closestpoint", "vector")),
        ("banding", "banding", "m", ("none", "auto", "manual")),
        ("useworldspaceunits", "useworldspaceunits", "b", None),
        ("halfwidth", "halfwidth", "i", (1, 10)),
        ("halfwidthworld", "halfwidthworld", "f", (1e-05, 10.0)),
        ("rangemethod", "rangemethod", "m",
         ("positive", "negative", "zcentered", "minmax", "minplusrange", "midplusminusrange")),
        ("amplitude", "amplitude", "f", (0.0, 10.0)),
        ("amplitudev", "amplitudev", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("volume_adjust_fog")
def volume_adjust_fog(params):
    """Volume Adjust Fog (volumeadjustfog) — adjust a fog volume's look (init / remap combo). `input`
    (input 0) is the fog volume. vol names the grid; adjustvalue + operation apply the value change;
    doinitvalue/initvaluefrom/initvalue/initvol (re)initialize the field; enable_preprocess runs the
    preprocess pass; doblend/blendweight/blendmode/blendvol blend the result. SECURITY: the hidden
    vex_cwdpath file parm is NOT exposed."""
    n = child_after(params["input"], "volumeadjustfog", params.get("name"))
    _apply(n, params, [
        ("doblend", "doblend", "b", None),
        ("blendweight", "blendweight", "f", (0.0, 1.0)),
        ("blendmode", "blendmode", "m", ("value", "vol")),
        ("blendvol", "blendvol", "s", None),
        ("vol", "vol", "s", None),
        ("enable_preprocess", "enable_preprocess", "b", None),
        ("doinitvalue", "doinitvalue", "b", None),
        ("initvaluefrom", "initvaluefrom", "m", ("uniform", "vol")),
        ("initvalue", "initvalue", "f", (0.0, 1.0)),
        ("initvol", "initvol", "s", None),
        ("adjustvalue", "adjustvalue", "b", None),
        ("operation", "operation", "m", ("set", "add", "sub", "mult", "min", "max")),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RESAMPLE / RESIZE / REDUCE / BOUND
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_resample")
def volume_resample(params):
    """Volume Resample (volumeresample) — resample a volume to a new voxel resolution. `input` (input 0)
    is the volume. filter + filterscale pick the resampling kernel; fixedresample toggles a fixed
    output; uniformsamples + samplediv/divsize/scale set the target resolution; detect2d treats flat
    volumes as 2D."""
    n = child_after(params["input"], "volumeresample", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("filter", "filter", "s", None),
        ("filterscale", "filterscale", "f", (0.0, 5.0)),
        ("fixedresample", "fixedresample", "b", None),
        ("uniformsamples", "uniformsamples", "m", ("nonsquare", "x", "y", "z", "max", "size")),
        ("samplediv", "samplediv", "i", (1, 50)),
        ("divsize", "divsize", "f", (0.0, 10.0)),
        ("scale", "scale", "f", (0.0, 10.0)),
        ("detect2d", "detect2d", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_resize")
def volume_resize(params):
    """Volume Resize (volumeresize) — resize / re-bound a volume's grid extents. `input` (input 0) is
    the volume; `input2` (input 1) an optional second volume driving the new bounds. combine
    replace/union/intersect how the new region is formed; extracttile + tilenum extract a single tile;
    usepoints bounds to input points; keepdata preserves values; allowextrap/useclipplane control the
    edges."""
    n = child_after(params["input"], "volumeresize", params.get("name"))
    if params.get("input2"):
        bridge_input(n, params["input2"], index=1, name_hint="input2")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("extracttile", "extracttile", "b", None),
        ("tilenum", "tilenum", "i", (0, 10)),
        ("combine", "combine", "m", ("replace", "union", "intersect")),
        ("usepoints", "usepoints", "b", None),
        ("keepdata", "keepdata", "b", None),
        ("allowextrap", "allowextrap", "b", None),
        ("useclipplane", "useclipplane", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_reduce")
def volume_reduce(params):
    """Volume Reduce (volumereduce) — reduce a volume to an aggregate value (max/min/average/median/
    sum/rms...). `input` (input 0) is the volume. reduction picks the statistic; percentile drives the
    median/percentile; scaleby weights by length/area/volume; result + resultattrib choose where the
    value is written (volume/vertex/point/prim/detail attribute); createvarmap emits a local variable."""
    n = child_after(params["input"], "volumereduce", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("reduction", "reduction", "m",
         ("max", "min", "maxabs", "minabs", "average", "median", "sum", "sumabs", "sumsquare", "rms")),
        ("percentile", "percentile", "f", (0.0, 100.0)),
        ("scaleby", "scaleby", "m", ("none", "length", "area", "volume")),
        ("result", "result", "m", ("volume", "vertex", "point", "prim", "detail")),
        ("resultattrib", "resultattrib", "s", None),
        ("createvarmap", "createvarmap", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_bound")
def volume_bound(params):
    """Volume Bound (volumebound) — rebuild the active/bounding region of a volume by thresholding.
    `input` (input 0) is the volume. comp picks the comparison (greater / less / strict variants) and
    value the threshold that decides which voxels stay active."""
    n = child_after(params["input"], "volumebound", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("comp", "comp", "m", ("greater", "less", "greater_strict", "less_strict")),
        ("value", "value", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SDF / VDB TOPOLOGY / OCCLUSION
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_sdf")
def volume_sdf(params):
    """Volume SDF (volumesdf) — compute a signed-distance field from a fog/mask volume. `input`
    (input 0) is the source volume. iso the surface level; invert flips inside/out; usemaxdist +
    maxdist cap the computed distance; rebuildwithfim + fimtolerance/fimiterations use the fast
    iterative method for the rebuild."""
    n = child_after(params["input"], "volumesdf", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("iso", "iso", "f", (0.0, 10.0)),
        ("invert", "invert", "b", None),
        ("usemaxdist", "usemaxdist", "b", None),
        ("maxdist", "maxdist", "f", (0.0, 10.0)),
        ("rebuildwithfim", "rebuildwithfim", "b", None),
        ("fimtolerance", "fimtolerance", "f", (0.0, 10.0)),
        ("fimiterations", "fimiterations", "i", (0, 100)),  # probe range [0,10] clips default 100; widened
    ])
    return _finish_op(n)


@endpoint("vdb_activate_sdf")
def vdb_activate_sdf(params):
    """VDB Activate SDF (vdbactivatesdf) — activate / expand the narrow band of an SDF VDB. `input`
    (input 0) is the VDBs to process. radius/radiusworld + useworldspaceunits set the dilation range;
    iterations the passes; halfwidth/halfwidthworld the rebuilt band; voxeloffset the iso shift;
    accuracy the renormalization scheme; invert/minmask/maxmask/trim gate and trim the result."""
    n = child_after(params["input"], "vdbactivatesdf", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("assumeuniformscale", "assumeuniformscale", "b", None),
        ("useworldspaceunits", "useworldspaceunits", "b", None),
        ("radius", "radius", "i", (1, 5)),
        ("radiusworld", "radiusworld", "f", (1e-05, 10.0)),
        ("iterations", "iterations", "i", (0, 10)),
        ("halfwidth", "halfwidth", "i", (1, 10)),
        ("halfwidthworld", "halfwidthworld", "f", (1e-05, 10.0)),
        ("voxeloffset", "voxeloffset", "f", (0.0, 10.0)),
        ("accuracy", "accuracy", "ms", ("upwind first", "upwind second", "hj weno")),
        ("invert", "invert", "b", None),
        ("minmask", "minmask", "f", (0.0, 1.0)),
        ("maxmask", "maxmask", "f", (0.0, 1.0)),
        ("trim", "trim", "ms", ("none", "interior", "exterior", "all")),
    ])
    return _finish_op(n)


@endpoint("vdb_topology_to_sdf")
def vdb_topology_to_sdf(params):
    """VDB Topology to SDF (vdbtopologytosdf) — build an SDF from a VDB's active-voxel topology.
    `input` (input 0) is the VDB grids. outputname keep/append/replace + customname name the result;
    worldspaceunits + bandwidth/bandwidthws set the SDF band; dilation grows the topology first;
    closingwidth fills gaps; smoothingsteps smooths the result."""
    n = child_after(params["input"], "vdbtopologytosdf", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("outputname", "outputname", "ms", ("keep", "append", "replace")),
        ("customname", "customname", "s", None),
        ("worldspaceunits", "worldspaceunits", "b", None),
        ("bandwidth", "bandwidth", "i", (1, 10)),
        ("bandwidthws", "bandwidthws", "f", (1e-05, 10.0)),
        ("dilation", "dilation", "i", (0, 10)),
        ("closingwidth", "closingwidth", "i", (1, 10)),
        ("smoothingsteps", "smoothingsteps", "i", (0, 10)),
    ])
    return _finish_op(n)


@endpoint("vdb_occlusion_mask")
def vdb_occlusion_mask(params):
    """VDB Occlusion Mask (vdbocclusionmask) — build a camera-facing occlusion mask VDB behind the
    input VDBs. `input` (input 0) is the VDBs; `camera` is a NodePath scene reference to the camera
    object (NOT a file). voxelcount/voxeldepthsize/depth size the mask frustum; erode shrinks the mask;
    zoffset shifts it along the view."""
    n = child_after(params["input"], "vdbocclusionmask", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("camera", "camera", "s", None),  # camera object path (NodePath scene ref), NOT a file
        ("voxelcount", "voxelcount", "i", (1, 200)),
        ("voxeldepthsize", "voxeldepthsize", "f", (1e-05, 5.0)),
        ("depth", "depth", "f", (0.0, 1000.0)),
        ("erode", "erode", "i", (0, 10)),
        ("zoffset", "zoffset", "i", (-10, 10)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ANALYSIS / VELOCITY
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_analysis")
def volume_analysis(params):
    """Volume Analysis (volumeanalysis) — compute a differential quantity of a volume. `input` (input 0)
    is the volume. analysis picks curvature / gradient / laplacian / edgedetect; edgedetectmode chooses
    the sobel or prewitt kernel for edge detection."""
    n = child_after(params["input"], "volumeanalysis", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("analysis", "analysis", "m", ("curvature", "gradient", "laplacian", "edgedetect")),
        ("edgedetectmode", "edgedetectmode", "m", ("sobel", "prewitt")),
    ])
    return _finish_op(n)


@endpoint("volume_velocity_from_curves")
def volume_velocity_from_curves(params):
    """Volume Velocity from Curves (volumevelocityfromcurves) — build a velocity volume that flows along
    curves. `input` (input 0) is the Curves; `surface` (input 1) an optional bounding surface; `volumes`
    (input 2) an optional reference volume. voxelsize the resolution; smooth/smoothradius/bluriterations
    smooth the field; refvol/createfromrefvol/matchrefvol source the transform from a reference volume;
    voxelsizefromsurface/surfacevoxelscale/createfromsurface/surfaceextband/surfaceintband source it
    from the surface."""
    n = child_after(params["input"], "volumevelocityfromcurves", params.get("name"))
    if params.get("surface"):
        bridge_input(n, params["surface"], index=1, name_hint="surface")
    if params.get("volumes"):
        bridge_input(n, params["volumes"], index=2, name_hint="volumes")
    _apply(n, params, [
        ("hasvolumeinput", "hasvolumeinput", "b", None),
        ("hassurfaceinput", "hassurfaceinput", "b", None),
        ("voxelsize", "voxelsize", "f", (1e-05, 0.1)),
        ("smooth", "smooth", "b", None),
        ("smoothradius", "smoothradius", "i", (1, 5)),
        ("bluriterations", "bluriterations", "i", (0, 10)),
        ("refvol", "refvol", "s", None),
        ("createfromrefvol", "createfromrefvol", "b", None),
        ("matchrefvol", "matchrefvol", "b", None),
        ("voxelsizefromsurface", "voxelsizefromsurface", "b", None),
        ("surfacevoxelscale", "surfacevoxelscale", "f", (0.1, 4.0)),
        ("createfromsurface", "createfromsurface", "b", None),
        ("surfaceextband", "surfaceextband", "f", (1e-05, 1.0)),
        ("surfaceintband", "surfaceintband", "f", (1e-05, 1.0)),
    ])
    return _finish_op(n)


@endpoint("volume_velocity_from_surface")
def volume_velocity_from_surface(params):
    """Volume Velocity from Surface (volumevelocityfromsurface) — build a velocity (+ collision) volume
    from a surface's motion. `input` (input 0) is the surface. opencl toggles the GPU solve; voxelsize
    the resolution; exteriorband the band width; pressureiters the divergence-free solve iterations;
    velname/divattrib name the outputs; outputcoll + collname emit a collision volume."""
    n = child_after(params["input"], "volumevelocityfromsurface", params.get("name"))
    _apply(n, params, [
        ("opencl", "opencl", "b", None),
        ("voxelsize", "voxelsize", "f", (1e-05, 1.0)),
        ("exteriorband", "exteriorband", "f", (1e-05, 10.0)),
        ("pressureiters", "pressureiters", "i", (1, 100)),
        ("velname", "velname", "s", None),
        ("outputcoll", "outputcoll", "b", None),
        ("collname", "collname", "s", None),
        ("divattrib", "divattrib", "s", None),
    ])
    return _finish_op(n)

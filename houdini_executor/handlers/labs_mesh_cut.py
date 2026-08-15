"""SideFX Labs — Mesh: Cut lane (data-only chain handlers). Params verified against live
H21.0.671 (menu tokens/labels + input/output counts +
headless cook). Category wrapped: "Labs/Geometry/Mesh: Cut", deduped to the highest version per
base name (polyslice::1.2, boxcutter::1.0, polyscalpel::1.0, split_prim_by_normal::1.0, and the
unversioned box_clip / mesh_slice / boxcutter_subutil).

Archetypes:
  * Archetype-B single-input CHAIN nodes (child_after auto-wires input 0): box_clip, boxcutter,
    boxcutter_subutil, mesh_slice, polyslice, split_prim_by_normal.
  * polyscalpel is a TWO-input chain: source mesh (input 0, via child_after) + a required cutting
    geometry (input 1, bridged in). It slices the source where the cutter crosses it.

SECURITY: this lane is fully data-only — none of these nodes carry a file/path surface. Every
exposed parm is a scalar / toggle / ordered-menu / vec3 / geometry-group-or-attribute NAME string
(never a path, never code). The interactive draw tools (boxcutter / boxcutter_subutil / polyscalpel)
have NO code/callback parms; their draw-mode buttons, geometry-stash Data parm and `opShape`
custom-shape reference are left untouched. Nothing to confine, nothing to force off.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────


def _menu_idx_set(node, parm, token, tokens):
    """Ordered/Int menu stored as an INDEX (native tokens are '0','1',...): set index =
    tokens.index(token), where `tokens` is our human-label enum aligned to the native menu order."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(tokens.index(token))
        return True
    except Exception:
        return False


def _menu_tok_set(node, parm, token, tokens):
    """Menu whose native tokens are meaningful strings: set by the token string directly."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _set_vec3(node, parm, params, kx, ky, kz, lo=-1e6, hi=1e6):
    """Set a vec3 tuple parm from optional per-component params (read-modify: unset components keep
    the current value). No-op if none supplied or the tuple parm is absent."""
    vals = [params.get(kx), params.get(ky), params.get(kz)]
    if all(v is None for v in vals):
        return
    pt = node.parmTuple(parm)
    if pt is None:
        return
    try:
        cur = list(pt.eval())
    except Exception:
        cur = [0.0, 0.0, 0.0]
    for i, v in enumerate(vals):
        if v is not None:
            cur[i] = clamp(float(v), lo, hi)
    try:
        pt.set(tuple(cur))
    except Exception:
        pass


# ── enum token tuples ─────────────────────────────────────────────────────────────────────────────
_PS_INPUTGEO = ("polylines", "polygon_surfaces")                   # inputGeoType idx 0,1
_PS_CUTGEO = ("points", "polylines", "polygon_surfaces")          # cuttingGeoType idx 0,1,2
_PS_SURFOUT = ("points_on_edges", "slice_surfaces")               # surfaceOutput idx 0,1
_PS_SLICEMETHOD = ("polysplit", "boolean_shatter")                # surfaceCuttingMethod idx 0,1
_BOOL_OP_IDX = ("subtract", "shatter", "union")                   # boxcutter sBooleanOperation idx
_BOOL_OP_TOK = ("subtract", "shatter", "union")                   # subutil booleanop string tokens
_PSL_MODE = ("poly", "polyline")                                  # polyslice Mode string tokens
_PSL_CONN = ("skip_connecting", "slices_together", "slice_separate")  # connectivitymode idx 0,1,2
_SPN_AXIS = ("x", "y", "z")                                       # split axis idx 0,1,2
_SPN_DIR = ("positive", "negative", "both")                       # split direction idx 0,1,2


# ── 1. box_clip (chain; clip a mesh to an axis-aligned box) ──────────────────────────────────────
@endpoint("box_clip")
def box_clip(params):
    """Labs Box Clip (labs::box_clip) — clips `input` (input 0) against an axis-aligned box, keeping
    the geometry that survives the enabled side planes (each `neg*`/`pos*` toggle turns one of the
    six clip planes on; all six default ON). `size`/`center` (vec3) and `scale` size and place the
    clip box — make it LARGER than the geometry to keep everything, smaller to trim. `fillholes` caps
    the cut. Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::box_clip", params.get("name"))
    if "disable" in params:
        _try_set(n, "disable", bool(params["disable"]))
    _set_vec3(n, "size", params, "size_x", "size_y", "size_z", 1e-4, 1e6)
    _set_vec3(n, "center", params, "center_x", "center_y", "center_z", -1e6, 1e6)
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e4))
    for tog in ("negx", "posx", "negy", "posy", "negz", "posz"):
        if tog in params:
            _try_set(n, tog, bool(params[tog]))
    if "fillholes" in params:
        _try_set(n, "fillholes", bool(params["fillholes"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. boxcutter (chain; boolean box cutter) ─────────────────────────────────────────────────────
@endpoint("boxcutter")
def boxcutter(params):
    """Labs BoxCutter (labs::boxcutter::1.0) — a boolean box cutter for `input` (input 0): subtracts,
    shatters or unions a transformable box against the mesh. `boolean_op` picks the operation;
    `bevel_divisions`/`bevel_distance` round the cutting box; `translate`/`rotate`/`scale` (vec3)
    place and size it; `copies` (+ `copy_translate`/`copy_rotate` vec3) arrays the cut. Primarily an
    interactive draw tool — with no box placed it passes the mesh through. Data-only: the draw-mode
    buttons, geometry-stash and custom-shape reference (`opShape`) are left untouched (no file/code)."""
    n = child_after(params["input"], "labs::boxcutter::1.0", params.get("name"))
    if "boolean_op" in params:
        _menu_idx_set(n, "sBooleanOperation", str(params["boolean_op"]), _BOOL_OP_IDX)
    if "bevel_divisions" in params:
        _try_set(n, "iBevelDivisions", int(clamp(int(params["bevel_divisions"]), 0, 100)))
    if "bevel_distance" in params:
        _try_set(n, "fBevelDistance", clamp(float(params["bevel_distance"]), 0.0, 1e4))
    if "copies" in params:
        _try_set(n, "iNumCopies", int(clamp(int(params["copies"]), 1, 500)))
    _set_vec3(n, "vTranslate", params, "translate_x", "translate_y", "translate_z")
    _set_vec3(n, "vRotate", params, "rotate_x", "rotate_y", "rotate_z", -3600.0, 3600.0)
    _set_vec3(n, "vScale", params, "scale_x", "scale_y", "scale_z", 1e-4, 1e6)
    _set_vec3(n, "vCopyTranslate", params, "copy_translate_x", "copy_translate_y", "copy_translate_z")
    _set_vec3(n, "vRotCopy", params, "copy_rotate_x", "copy_rotate_y", "copy_rotate_z", -3600.0, 3600.0)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. boxcutter_subutil (chain; single-shape boolean box sub-utility) ────────────────────────────
@endpoint("boxcutter_subutil")
def boxcutter_subutil(params):
    """Labs BoxCutter Sub-Utility (labs::boxcutter_subutil) — the single-shape boolean box cutter
    underlying boxcutter, usable standalone on `input` (input 0). `operation` picks subtract/shatter/
    union; `translate`/`rotate`/`scale` (vec3) place the box; `distance` extrudes the cut, `divisions`
    beveks its corners; `copies` (+ `copy_translate`/`copy_rotate` vec3) array it. `active` toggles it.
    Passes the mesh through when inactive. Data-only: the custom-shape reference (`opShape`) and raw
    draw-mode int are left untouched (no file/code surface)."""
    n = child_after(params["input"], "labs::boxcutter_subutil", params.get("name"))
    if "active" in params:
        _try_set(n, "bActive", bool(params["active"]))
    if "operation" in params:
        _menu_tok_set(n, "booleanop", str(params["operation"]), _BOOL_OP_TOK)
    if "distance" in params:
        _try_set(n, "offset", clamp(float(params["distance"]), -1e4, 1e4))
    if "divisions" in params:
        _try_set(n, "divisions", int(clamp(int(params["divisions"]), 0, 100)))
    if "copies" in params:
        _try_set(n, "ncy", int(clamp(int(params["copies"]), 1, 500)))
    _set_vec3(n, "t", params, "translate_x", "translate_y", "translate_z")
    _set_vec3(n, "r", params, "rotate_x", "rotate_y", "rotate_z", -3600.0, 3600.0)
    _set_vec3(n, "s", params, "scale_x", "scale_y", "scale_z", 1e-4, 1e6)
    _set_vec3(n, "tcopy", params, "copy_translate_x", "copy_translate_y", "copy_translate_z")
    _set_vec3(n, "rcopy", params, "copy_rotate_x", "copy_rotate_y", "copy_rotate_z", -3600.0, 3600.0)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. mesh_slice (chain; slice a mesh into a grid of pieces) ─────────────────────────────────────
@endpoint("mesh_slice")
def mesh_slice(params):
    """Labs Mesh Slice (labs::mesh_slice) — slices `input` (input 0) with an axis-aligned grid of
    cutting planes (`divisions_x`/`_y`/`_z` planes per axis) and (with `fill_holes`) caps the cuts,
    producing separable pieces. `isolate_index` + `index` keep only one piece. NOTE: planes exactly
    coincident with flat faces produce nothing — slice curved / non-axis-aligned meshes. Data-only."""
    n = child_after(params["input"], "labs::mesh_slice", params.get("name"))
    if "divisions_x" in params:
        _try_set(n, "divisionsx", int(clamp(int(params["divisions_x"]), 0, 1000)))
    if "divisions_y" in params:
        _try_set(n, "divisionsy", int(clamp(int(params["divisions_y"]), 0, 1000)))
    if "divisions_z" in params:
        _try_set(n, "divisionsz", int(clamp(int(params["divisions_z"]), 0, 1000)))
    if "fill_holes" in params:
        _try_set(n, "cap", bool(params["fill_holes"]))
    if "isolate_index" in params:
        _try_set(n, "isolate_index", bool(params["isolate_index"]))
    if "index" in params:
        _try_set(n, "index", int(clamp(int(params["index"]), 0, 1_000_000)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. polyslice (chain; parallel plane slices along an axis) ─────────────────────────────────────
@endpoint("polyslice")
def polyslice(params):
    """Labs PolySlice (labs::polyslice::1.2) — slices `input` (input 0) with `num_slices` parallel
    planes, positioned/oriented by `center` (vec3), `size` (vec3), `scale` and `rotate` (vec3).
    `mode` outputs sliced polys or polyline cross-sections. `connectivity` decides how sliced pieces
    are grouped; `divide_convex` triangulates resulting non-convex faces. Optional slice-ID and
    slice-group attributes are written under the given attribute/group NAMES. `group` limits the
    sliced region. Data-only (all strings are attribute/group names, never paths; no code surface)."""
    n = child_after(params["input"], "labs::polyslice::1.2", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))            # geometry group NAME
    if "mode" in params:
        _menu_tok_set(n, "Mode", str(params["mode"]), _PSL_MODE)
    if "num_slices" in params:
        _try_set(n, "numslices", int(clamp(int(params["num_slices"]), 1, 10000)))
    if "followbbox" in params:
        _try_set(n, "followbbox", bool(params["followbbox"]))
    _set_vec3(n, "t2", params, "center_x", "center_y", "center_z")
    _set_vec3(n, "size", params, "size_x", "size_y", "size_z", 1e-4, 1e6)
    if "scale" in params:
        _try_set(n, "scale2", clamp(float(params["scale"]), 1e-4, 1e4))
    _set_vec3(n, "r2", params, "rotate_x", "rotate_y", "rotate_z", -3600.0, 3600.0)
    if "divide_convex" in params:
        _try_set(n, "divideconvex", bool(params["divide_convex"]))
    if "connectivity" in params:
        _menu_idx_set(n, "connectivitymode", str(params["connectivity"]), _PSL_CONN)
    if "slice_border_edge" in params:
        _try_set(n, "sliceborderedge", bool(params["slice_border_edge"]))
    if "connect_border_edge" in params:
        _try_set(n, "connectborderedge", bool(params["connect_border_edge"]))
    if "export_slice_id" in params:
        _try_set(n, "exportsliceid", bool(params["export_slice_id"]))
    if "slice_id_name" in params:
        _try_set(n, "sliceidname", str(params["slice_id_name"]))     # attribute NAME
    if "export_slice_group" in params:
        _try_set(n, "exportslicegroup", bool(params["export_slice_group"]))
    if "slice_group_name" in params:
        _try_set(n, "slicegroup", str(params["slice_group_name"]))   # group NAME
    if "slice_threshold" in params:
        _try_set(n, "slicethreshold", clamp(float(params["slice_threshold"]), 0.0, 1e6))
    if "fuse_threshold" in params:
        _try_set(n, "tol3d", clamp(float(params["fuse_threshold"]), 0.0, 1e6))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. split_prim_by_normal (chain; group/split faces by normal direction) ────────────────────────
@endpoint("split_prim_by_normal")
def split_prim_by_normal(params):
    """Labs Split Prim by Normal (labs::split_prim_by_normal::1.0) — selects the primitives of
    `input` (input 0) whose normal points along `axis` in the chosen `direction`, within
    `spread_angle` degrees; `invert` flips the selection. Output 0 carries the matching faces (the
    node also exposes a second output for the remainder). Requires a normal (N) attribute on the
    input. Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::split_prim_by_normal::1.0", params.get("name"))
    if "axis" in params:
        _menu_idx_set(n, "axis", str(params["axis"]), _SPN_AXIS)
    if "direction" in params:
        _menu_idx_set(n, "direction", str(params["direction"]), _SPN_DIR)
    if "spread_angle" in params:
        _try_set(n, "spreadangle", clamp(float(params["spread_angle"]), 0.0, 180.0))
    if "invert" in params:
        _try_set(n, "negate", bool(params["invert"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. polyscalpel (TWO-input chain; slice a mesh with a cutting geometry) ────────────────────────
@endpoint("polyscalpel")
def polyscalpel(params):
    """Labs PolyScalpel (Labs::polyscalpel::1.0) — slices the source mesh `input` (input 0) wherever
    the required `cutter` geometry (input 1) crosses it. `cutting_geo_type` MUST match the cutter's
    type (points / polylines / polygon_surfaces); `input_geo_type` matches the source. `surface_output`
    picks points-on-edges vs sliced surfaces; `slicing_method` picks the exact PolySplit or the faster
    Boolean-Shatter path. `source_group`/`cutting_group` are geometry-group NAMES limiting each side.
    Data-only: no file/code surface; the compile toggle and viewport guide parms are left untouched."""
    n = child_after(params["input"], "Labs::polyscalpel::1.0", params.get("name"))
    bridge_input(n, params["cutter"], index=1, name_hint="cutter")   # required cutting geo -> input 1
    if "input_geo_type" in params:
        _menu_idx_set(n, "inputGeoType", str(params["input_geo_type"]), _PS_INPUTGEO)
    if "cutting_geo_type" in params:
        _menu_idx_set(n, "cuttingGeoType", str(params["cutting_geo_type"]), _PS_CUTGEO)
    if "surface_output" in params:
        _menu_idx_set(n, "surfaceOutput", str(params["surface_output"]), _PS_SURFOUT)
    if "slicing_method" in params:
        _menu_idx_set(n, "surfaceCuttingMethod", str(params["slicing_method"]), _PS_SLICEMETHOD)
    if "use_connectivity" in params:
        _try_set(n, "useConnectivity", bool(params["use_connectivity"]))
    if "cross_cut_surface" in params:
        _try_set(n, "crossCutSurface", bool(params["cross_cut_surface"]))
    if "cross_cut_depth" in params:
        _try_set(n, "crossCutDepth", clamp(float(params["cross_cut_depth"]), 0.0, 1e6))
    if "source_group" in params:
        _try_set(n, "sourceGroup", str(params["source_group"]))      # geometry group NAME
    if "cutting_group" in params:
        _try_set(n, "cuttingGroup", str(params["cutting_group"]))    # geometry group NAME
    if "output_edge_group" in params:
        _try_set(n, "edgeGroupTgl", bool(params["output_edge_group"]))
    if "cut_edge_group_name" in params:
        _try_set(n, "prim_Group_Name", str(params["cut_edge_group_name"]))  # group NAME
    if "recompute_normals" in params:
        _try_set(n, "recomputeNormals", bool(params["recompute_normals"]))
    if "sort_by_connectivity" in params:
        _try_set(n, "sortByConnectivityID", bool(params["sort_by_connectivity"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

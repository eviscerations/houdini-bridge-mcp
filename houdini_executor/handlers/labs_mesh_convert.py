"""SideFX Labs — Mesh Convert lane (data-only chain handlers). Params verified against live
H21.0.671 (menu tokens/labels + input/output counts +
headless cook). Categories wrapped: "Labs/Geometry/Mesh/Convert" + "Labs/Geometry/Mesh: Convert",
deduped to the highest version per base name.

All seven are Archetype-B CHAIN nodes: exactly 1 input (a mesh / edge-group carrying geo) and 1
output. Each is built with child_after(input, ntype) which auto-wires setInput(0).

SECURITY: this lane is fully data-only — none of these nodes carry a file/path surface or a
code/callback parm. Every exposed parm is a scalar / toggle / ordered-menu / geometry-group-name or
attribute-name string (never a path, never code). Nothing to confine, nothing to force off.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────


def _try_set_tuple(node, parm, values):
    """Set a tuple parm (vec3 etc.) only if it exists."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(values))
        return True
    except Exception:
        return False


def _menu_idx_set(node, parm, token, tokens):
    """Ordered Menu stored as an INDEX (menuItems are '0','1',...): set index = tokens.index(token),
    where `tokens` is our human-label enum aligned to the native menu order."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(tokens.index(token))
        return True
    except Exception:
        return False


def _menu_tok_set(node, parm, token, tokens):
    """Ordered Menu whose native tokens are meaningful strings: set by the token string directly."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


# ── enum token tuples (index-stored menus use position == native index) ──────────────────────────
_QUAD_METHOD = ("vertex_order", "longest_edge")                       # method idx 0,1
_QUAD_REFINE = ("polyfill", "iterative_divide")                       # refinemethod idx 0,1
_QUAD_EDGE = ("smallest_edge", "longest_edge", "first_edge")          # edgemethod idx 0,1,2
_QUAD_FILL = ("none", "tris", "trifan", "quadfan", "quads", "gridquads")  # fillmode string tokens
_CPN_OUTPUT = ("centroids_only", "centroids_and_connections")        # outputmode idx 0,1
_THICK_GRPTYPE = ("guess", "breakpoints", "edges", "points", "prims")     # grouptype string tokens
_THICK_EXTRUDE = ("primnormal", "pointnormal")                       # extrusionmode string tokens
_THICK_NORMAL = ("typepoint", "typevertex", "typeprim", "typedetail")     # type string tokens


# ── 1. quadrangulate::2.0 (tri -> quad merge) ────────────────────────────────────────────────────
@endpoint("quadrangulate")
def quadrangulate(params):
    """Labs Quadrangulate (labs::quadrangulate::2.0) — converts a triangulated mesh into quads by
    merging triangle pairs (topology-preserving; NOT a full remesh like quad_remesh). `input`
    (input 0) = the triangle mesh. `method` picks the pairing heuristic; `fillmode` decides how
    leftover n-gons are filled. Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::quadrangulate::2.0", params.get("name"))
    if "method" in params:
        _menu_idx_set(n, "method", str(params["method"]), _QUAD_METHOD)
    if "edgetocollapse" in params:
        _try_set(n, "edgetocollapse", int(clamp(int(params["edgetocollapse"]), 0, 1_000_000)))
    if "protectsilhouette" in params:
        _try_set(n, "protectsilhouette", bool(params["protectsilhouette"]))
    if "normalangle" in params:
        _try_set(n, "normalangle", clamp(float(params["normalangle"]), 0.0, 180.0))
    if "refinemethod" in params:
        _menu_idx_set(n, "refinemethod", str(params["refinemethod"]), _QUAD_REFINE)
    if "fillmode" in params:
        _menu_tok_set(n, "fillmode", str(params["fillmode"]), _QUAD_FILL)
    if "edgemethod" in params:
        _menu_idx_set(n, "edgemethod", str(params["edgemethod"]), _QUAD_EDGE)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. voxelmesh::2.0 (VDB voxel remesh — watertight) ─────────────────────────────────────────────
@endpoint("voxelmesh")
def voxelmesh(params):
    """Labs VoxelMesh (labs::voxelmesh::2.0) — rebuilds `input` (input 0) into a watertight mesh by
    rasterizing it to a VDB at `resolution` voxels across the longest axis, then meshing the surface
    (a volume-based remesh, distinct from the native surface `remesh`). `resolution` is CUBIC in cost
    and hard-clamped to <=512 (200 already yields ~185k prims). Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::voxelmesh::2.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))  # geometry group NAME (not a path)
    if "resolution" in params:
        _try_set(n, "resolution", int(clamp(int(params["resolution"]), 10, 512)))  # CUBIC cost cap
    if "dilateerode" in params:
        _try_set(n, "dilateerode", clamp(float(params["dilateerode"]), -10.0, 10.0))
    if "smoothingiterations" in params:
        _try_set(n, "smoothingiterations", int(clamp(int(params["smoothingiterations"]), 0, 50)))
    if "adaptivity" in params:
        _try_set(n, "adaptivity", clamp(float(params["adaptivity"]), 0.0, 1.0))
    if "transferattributes" in params:
        _try_set(n, "transferattributes", bool(params["transferattributes"]))
    if "sharpenfeatures" in params:
        _try_set(n, "sharpenfeatures", bool(params["sharpenfeatures"]))
    if "edgetolerance" in params:
        _try_set(n, "edgetolerance", clamp(float(params["edgetolerance"]), 0.0, 1.0))
    if "project" in params:
        _try_set(n, "project", bool(params["project"]))
    if "postsmooth" in params:
        _try_set(n, "postsmooth", int(clamp(int(params["postsmooth"]), 0, 50)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. connect_polygon_neighbours::1.0 (centroid adjacency graph) ─────────────────────────────────
@endpoint("connect_polygon_neighbours")
def connect_polygon_neighbours(params):
    """Labs Connect Polygon Neighbours (labs::connect_polygon_neighbours::1.0) — emits a point at
    each polygon centroid of `input` (input 0) and (in the default mode) polyline edges linking
    face-adjacent neighbours — the dual/adjacency graph of the mesh. `attribstocopy`/`groupstocopy`
    are space-separated attribute / group NAME patterns (not paths). Data-only."""
    n = child_after(params["input"], "labs::connect_polygon_neighbours::1.0", params.get("name"))
    if "outputmode" in params:
        _menu_idx_set(n, "outputmode", str(params["outputmode"]), _CPN_OUTPUT)
    if "copyattrib" in params:
        _try_set(n, "copyattrib", bool(params["copyattrib"]))
    if "attribstocopy" in params:
        _try_set(n, "attribstocopy", str(params["attribstocopy"]))  # attribute-name pattern
    if "copygroup" in params:
        _try_set(n, "copygroup", bool(params["copygroup"]))
    if "groupstocopy" in params:
        _try_set(n, "groupstocopy", str(params["groupstocopy"]))    # group-name pattern
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. edge_group_to_polylines::1.0 (edge group -> polylines) ─────────────────────────────────────
@endpoint("edge_group_to_polylines")
def edge_group_to_polylines(params):
    """Labs Edge Group to Polylines (labs::edge_group_to_polylines::1.0) — extracts the edges named
    by `edgegroup` from `input` (input 0) as individual polyline primitives. `edgegroup` is an edge
    GROUP name that must exist on the incoming geometry (leave empty = no-op pass-through).
    Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::edge_group_to_polylines::1.0", params.get("name"))
    if "edgegroup" in params:
        _try_set(n, "edgegroup", str(params["edgegroup"]))  # edge-group NAME
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. edgegroup_to_curve::1.1 (edge group -> connected curves) ───────────────────────────────────
@endpoint("edgegroup_to_curve")
def edgegroup_to_curve(params):
    """Labs Edge Group to Curve (labs::edgegroup_to_curve::1.1) — like edge_group_to_polylines but
    stitches the edges named by `group` into connected, ordered curves (chains the shared endpoints).
    `connectends` closes loops. `group` is an edge-GROUP name on `input` (input 0). The `*attribs`
    strings are attribute-NAME lists transferred onto the curves. Data-only."""
    n = child_after(params["input"], "labs::edgegroup_to_curve::1.1", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))  # edge-group NAME
    if "connectends" in params:
        _try_set(n, "connectends", bool(params["connectends"]))
    if "transferattr" in params:
        _try_set(n, "transferattr", bool(params["transferattr"]))
    if "pointattribs" in params:
        _try_set(n, "pointattribs", str(params["pointattribs"]))    # attribute-name lists
    if "vertattribs" in params:
        _try_set(n, "vertattribs", str(params["vertattribs"]))
    if "primattribs" in params:
        _try_set(n, "primattribs", str(params["primattribs"]))
    if "detailattribs" in params:
        _try_set(n, "detailattribs", str(params["detailattribs"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. symmetrize (mirror + weld across a plane) ──────────────────────────────────────────────────
@endpoint("symmetrize")
def symmetrize(params):
    """Labs Symmetrize (labs::symmetrize) — mirrors `input` (input 0) across the plane defined by
    `origin` + `direction` (normal) and welds the halves into a symmetric mesh. `group` limits the
    source side. `dissolve` removes the seam edge after welding. Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::symmetrize", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))  # geometry group NAME
    dvec = [params.get("dir_x"), params.get("dir_y"), params.get("dir_z")]
    if any(v is not None for v in dvec):
        cur = n.parmTuple("direction").eval() if n.parmTuple("direction") else (0.0, 1.0, 0.0)
        vec = [float(dvec[i]) if dvec[i] is not None else cur[i] for i in range(3)]
        _try_set_tuple(n, "direction", [clamp(v, -1e6, 1e6) for v in vec])
    ovec = [params.get("origin_x"), params.get("origin_y"), params.get("origin_z")]
    if any(v is not None for v in ovec):
        cur = n.parmTuple("origin").eval() if n.parmTuple("origin") else (0.0, 0.0, 0.0)
        vec = [float(ovec[i]) if ovec[i] is not None else cur[i] for i in range(3)]
        _try_set_tuple(n, "origin", [clamp(v, -1e6, 1e6) for v in vec])
    if "dissolve" in params:
        _try_set(n, "dissolve", bool(params["dissolve"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. thicken::1.1 (shell / solidify a surface) ──────────────────────────────────────────────────
@endpoint("thicken")
def thicken(params):
    """Labs Thicken (labs::thicken::1.1) — gives a surface / open shell thickness by extruding it
    along its normals by `depth` and bridging the walls (solidify). `input` (input 0) = the surface.
    `both_directions` thickens symmetrically about the surface; `extrusionmode`/`type` choose the
    normal basis. `group`+`grouptype` limit the thickened region. Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::thicken::1.1", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))  # geometry group NAME
    if "grouptype" in params:
        _menu_tok_set(n, "grouptype", str(params["grouptype"]), _THICK_GRPTYPE)
    if "negate" in params:
        _try_set(n, "negate", bool(params["negate"]))
    if "extrusionmode" in params:
        _menu_tok_set(n, "extrusionmode", str(params["extrusionmode"]), _THICK_EXTRUDE)
    if "depth" in params:
        _try_set(n, "depth", clamp(float(params["depth"]), -100.0, 100.0))
    if "both_directions" in params:
        _try_set(n, "both_directions", bool(params["both_directions"]))
    if "dissolve_middle_edge" in params:
        _try_set(n, "dissolve_middle_edge", bool(params["dissolve_middle_edge"]))
    if "type" in params:
        _menu_tok_set(n, "type", str(params["type"]), _THICK_NORMAL)
    if "cuspangle" in params:
        _try_set(n, "cuspangle", clamp(float(params["cuspangle"]), 0.0, 180.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

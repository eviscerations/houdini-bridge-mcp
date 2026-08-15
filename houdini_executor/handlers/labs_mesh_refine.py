"""SideFX Labs — Mesh: Refine / Extract / Remove chain tools (data-only handlers).

Params verified against live H21.0.671. Every node in this
wave is a pure chain SOP filter (Archetype B): it takes an upstream mesh on input 0 and returns a
refined / extracted / reduced mesh. None carries a file surface, a ROP writer, or a code/callback
parm — so there is nothing to confine or force off; the security posture here is simply that we never
expose an arbitrary-code parm and never invent a parm (probe-safe _try_set).

Covered (highest version of each base name):
  Refine : cluster_refine, edge_damage, edge_smooth, mesh_sharpen, soften_normals
  Extract: extract_borders, extract_silhouette, straight_skeleton_2d, straight_skeleton_3d
  Remove : dissolve_flat_edges, remove_inside_faces
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set






def _result(n):
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── label-bearing ordered-menu token tuples (position == the stored index) ───────────────────────
_SHARPEN_CURV = ("gaussian", "mean", "principal", "curvedness")   # mesh_sharpen curvaturetype
_SHARPEN_PRINCIPAL = ("min", "max")                               # mesh_sharpen principaltype
_SHARPEN_SIGN = ("signed", "absolute")                            # mesh_sharpen principalsign


# ════════════════════════════════════════════════ REFINE ════════════════════════════════════════

@endpoint("cluster_refine")
def cluster_refine(params):
    """SideFX Labs Cluster Refine (labs::cluster_refine::1.0) — refines a mesh into welded islands by
    clustering connected regions, smoothing/relaxing the cluster boundaries so seams read cleanly.
    `input` (input 0) = the mesh to refine. `clustertype`/`depth` are ordered-menu index selectors
    (0-based). Data-only chain filter (no file surface)."""
    n = child_after(params["input"], "labs::cluster_refine::1.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "clustertype" in params:
        _try_set(n, "clustertype", int(clamp(int(params["clustertype"]), 0, 2)))
    if "clusterattrib" in params:
        _try_set(n, "clusterattrib", str(params["clusterattrib"]))
    if "depth" in params:
        _try_set(n, "depth", int(clamp(int(params["depth"]), 0, 1)))
    if "extweight" in params:
        _try_set(n, "extweight", clamp(float(params["extweight"]), 0.0, 1000.0))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 50)))
    if "edgelen" in params:
        _try_set(n, "edgelen", bool(params["edgelen"]))
    return _result(n)


@endpoint("edge_damage")
def edge_damage(params):
    """SideFX Labs Edge Damage (labs::edge_damage::2.1) — chips/erodes hard edges to add procedural
    wear, driven by a VDB pass; produces a damaged mesh (all displacement is procedural along normals,
    NOT from a disk image). `input` (input 0) = the mesh. `damagemode` is an ordered-menu index
    (0-based). COST: `voxel_res` is a relative voxel size — SMALLER = finer = far more expensive; it is
    clamped to >=1e-3. Data-only chain filter (no file surface). Ramp / folder / raw-value parms are
    left at their HDA defaults."""
    n = child_after(params["input"], "labs::edge_damage::2.1", params.get("name"))
    if "damagemode" in params:
        _try_set(n, "damagemode", int(clamp(int(params["damagemode"]), 0, 2)))
    if "seed" in params:
        _try_set(n, "seed", clamp(float(params["seed"]), -1e9, 1e9))
    if "mask_attribute" in params:
        _try_set(n, "mask_attribute", str(params["mask_attribute"]))
    if "amount_damage" in params:
        _try_set(n, "amount_damage", clamp(float(params["amount_damage"]), 0.0, 50.0))
    if "vdb_damage_quality" in params:
        _try_set(n, "vdb_damage_quality", clamp(float(params["vdb_damage_quality"]), 0.0, 1.0))
    if "vdb_direction" in params:
        _try_set(n, "vdb_direction", clamp(float(params["vdb_direction"]), -1.0, 1.0))
    if "vdb_mask_amount" in params:
        _try_set(n, "vdb_mask_amount", clamp(float(params["vdb_mask_amount"]), 0.0, 2.0))
    if "enable_voxel" in params:
        _try_set(n, "enable_voxel", bool(params["enable_voxel"]))
    if "voxel_res" in params:
        _try_set(n, "voxel_res", clamp(float(params["voxel_res"]), 1e-3, 1.0))  # COST: smaller = finer
    if "voxel_smooth" in params:
        _try_set(n, "voxel_smooth", int(clamp(int(params["voxel_smooth"]), 0, 20)))
    if "enable_displace" in params:
        _try_set(n, "enable_displace", bool(params["enable_displace"]))
    if "displace" in params:
        _try_set(n, "displace", clamp(float(params["displace"]), -5.0, 5.0))
    if "blur" in params:
        _try_set(n, "blur", int(clamp(int(params["blur"]), 0, 200)))
    return _result(n)


@endpoint("edge_smooth")
def edge_smooth(params):
    """SideFX Labs Edge Smooth (labs::edge_smooth::1.0) — relaxes/smooths mesh edges (optionally only
    unshared/boundary edges), useful for cleaning faceting on beveled or booleaned geometry. `input`
    (input 0) = the mesh; `group` restricts to an edge/primitive group. Data-only chain filter."""
    n = child_after(params["input"], "labs::edge_smooth::1.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "includeunshared" in params:
        _try_set(n, "includeunshared", bool(params["includeunshared"]))
    if "smoothstrength" in params:
        _try_set(n, "smoothstrength", clamp(float(params["smoothstrength"]), 0.0, 1000.0))
    if "filterquality" in params:
        _try_set(n, "filterquality", int(clamp(int(params["filterquality"]), 0, 4)))
    if "nbrrange" in params:
        _try_set(n, "nbrrange", int(clamp(int(params["nbrrange"]), 0, 10)))
    if "smoothsteps" in params:
        _try_set(n, "smoothsteps", int(clamp(int(params["smoothsteps"]), 0, 100)))
    return _result(n)


@endpoint("mesh_sharpen")
def mesh_sharpen(params):
    """SideFX Labs Mesh Sharpen (labs::mesh_sharpen) — sharpens surface features by pushing points
    along a curvature field, with an optional smoothing pass; good for accentuating scanned/soft
    geometry. `input` (input 0) = the mesh. COST: `iterations` (sharpen) and `iterations2` (smooth)
    are per-point solves, hard-clamped to <=2000. `curvaturetype`/`principaltype`/`principalsign` are
    label menus. Data-only chain filter."""
    n = child_after(params["input"], "labs::mesh_sharpen", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "step" in params:
        _try_set(n, "step", clamp(float(params["step"]), 0.0, 5.0))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 2000)))  # COST
    if "pin_borders" in params:
        _try_set(n, "pin_borders", bool(params["pin_borders"]))
    if "iterations2" in params:
        _try_set(n, "iterations2", int(clamp(int(params["iterations2"]), 0, 2000)))  # COST
    if "stepsize" in params:
        _try_set(n, "stepsize", clamp(float(params["stepsize"]), 0.0, 5.0))
    if "curvaturetype" in params:
        _menu_set(n, "curvaturetype", str(params["curvaturetype"]), _SHARPEN_CURV)
    if "principaltype" in params:
        _menu_set(n, "principaltype", str(params["principaltype"]), _SHARPEN_PRINCIPAL)
    if "principalsign" in params:
        _menu_set(n, "principalsign", str(params["principalsign"]), _SHARPEN_SIGN)
    if "scalenormalize" in params:
        _try_set(n, "scalenormalize", bool(params["scalenormalize"]))
    if "exponet" in params:
        _try_set(n, "exponet", clamp(float(params["exponet"]), 0.0, 10.0))
    return _result(n)


@endpoint("soften_normals")
def soften_normals(params):
    """SideFX Labs Soften Normals (labs::soften_normals) — recomputes vertex normals with a cusp
    angle so shared edges below the angle read smooth and sharper edges stay hard; can additionally
    harden normals across UV seams. `input` (input 0) = the mesh. `cuspangle` in degrees (180 = all
    smooth). Data-only chain filter."""
    n = child_after(params["input"], "labs::soften_normals", params.get("name"))
    if "cuspangle" in params:
        _try_set(n, "cuspangle", clamp(float(params["cuspangle"]), 0.0, 180.0))
    if "harden_uv_seams" in params:
        _try_set(n, "harden_uv_seams", bool(params["harden_uv_seams"]))
    return _result(n)


# ════════════════════════════════════════════════ EXTRACT ═══════════════════════════════════════

@endpoint("extract_borders")
def extract_borders(params):
    """SideFX Labs Extract Borders (labs::extract_borders) — extracts the open boundary edges of a
    mesh (and optionally the UV-island borders) as polylines or curves. `input` (input 0) = the mesh.
    `as_curves` emits NURBS/poly curves; `uv_borders` also traces UV-seam borders. Data-only chain
    filter."""
    n = child_after(params["input"], "labs::extract_borders", params.get("name"))
    if "as_curves" in params:
        _try_set(n, "as_curves", bool(params["as_curves"]))
    if "uv_borders" in params:
        _try_set(n, "uv_borders", bool(params["uv_borders"]))
    if "split_vertices" in params:
        _try_set(n, "split_vertices", bool(params["split_vertices"]))
    return _result(n)


@endpoint("extract_silhouette")
def extract_silhouette(params):
    """SideFX Labs Extract Silhouette (labs::extract_silhouette::1.0) — traces the outer silhouette of
    a mesh along a view axis and emits it as a curve (handy for cutout cards / trim shapes). `input`
    (input 0) = the mesh. `mTraceAxis` and `iExtractMode` are ordered-menu index selectors (0-based).
    The optional scene-camera picker (`campath`) is NOT exposed — the axis-based trace is used.
    Data-only chain filter."""
    n = child_after(params["input"], "labs::extract_silhouette::1.0", params.get("name"))
    if "iExtractMode" in params:
        _try_set(n, "iExtractMode", int(clamp(int(params["iExtractMode"]), 0, 1)))
    if "mTraceAxis" in params:
        _try_set(n, "mTraceAxis", int(clamp(int(params["mTraceAxis"]), 0, 4)))
    if "removeoutsidesilhouette" in params:
        _try_set(n, "removeoutsidesilhouette", bool(params["removeoutsidesilhouette"]))
    if "bResample" in params:
        _try_set(n, "bResample", bool(params["bResample"]))
    if "length" in params:
        _try_set(n, "length", clamp(float(params["length"]), 1e-3, 10.0))
    return _result(n)


@endpoint("straight_skeleton_2d")
def straight_skeleton_2d(params):
    """SideFX Labs Straight Skeleton 2D (labs::straight_skeleton_2D) — computes the 2D straight
    skeleton (medial-axis-like topological spine) of a planar polygon/curve, useful for roof/insetting
    and shape analysis. `input` (input 0) = a planar polygon or closed curve. `normal_menu` is an
    ordered-menu index selector (0-based). Data-only chain filter."""
    n = child_after(params["input"], "labs::straight_skeleton_2D", params.get("name"))
    if "resample_res" in params:
        _try_set(n, "resample_res", clamp(float(params["resample_res"]), 1e-4, 1.0))
    if "trim_ends" in params:
        _try_set(n, "trim_ends", bool(params["trim_ends"]))
    if "threshold" in params:
        _try_set(n, "threshold", clamp(float(params["threshold"]), 0.0, 1.0))
    if "fit_to_shape" in params:
        _try_set(n, "fit_to_shape", bool(params["fit_to_shape"]))
    if "recalculate_normal" in params:
        _try_set(n, "recalculate_normal", bool(params["recalculate_normal"]))
    if "normal_menu" in params:
        _try_set(n, "normal_menu", int(clamp(int(params["normal_menu"]), 0, 5)))
    return _result(n)


@endpoint("straight_skeleton_3d")
def straight_skeleton_3d(params):
    """SideFX Labs Straight Skeleton 3D (labs::straight_skeleton_3d) — extracts a 3D straight-skeleton
    / medial curve network of a closed mesh via a voxelized solve. `input` (input 0) = a closed mesh.
    COST: `voxel_size` is a relative voxel size — SMALLER = finer = far more expensive (clamped
    >=1e-3); `iterations` clamped <=200. Data-only chain filter."""
    n = child_after(params["input"], "labs::straight_skeleton_3d", params.get("name"))
    if "voxel_size" in params:
        _try_set(n, "voxel_size", clamp(float(params["voxel_size"]), 1e-3, 1.0))  # COST
    if "accuracy" in params:
        _try_set(n, "accuracy", clamp(float(params["accuracy"]), 0.0, 1.0))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 200)))
    if "fuse_distance" in params:
        _try_set(n, "fuse_distance", clamp(float(params["fuse_distance"]), 1e-4, 1.0))
    return _result(n)


# ════════════════════════════════════════════════ REMOVE ════════════════════════════════════════

@endpoint("dissolve_flat_edges")
def dissolve_flat_edges(params):
    """SideFX Labs Dissolve Flat Edges (labs::dissolve_flat_edges::1.0) — removes edges between
    (near-)coplanar faces to simplify a mesh without changing its silhouette, and optionally removes
    inline (colinear) points. `input` (input 0) = the mesh. `coltol` = the coplanarity angle
    tolerance (deg). Distinct from the native `dissolve` (which dissolves a specified edge group);
    this auto-detects flat edges by angle. Data-only chain filter."""
    n = child_after(params["input"], "labs::dissolve_flat_edges::1.0", params.get("name"))
    if "basegroup" in params:
        _try_set(n, "basegroup", str(params["basegroup"]))
    if "maxedgeangle" in params:
        _try_set(n, "maxedgeangle", clamp(float(params["maxedgeangle"]), 0.0, 180.0))
    if "coltol" in params:
        _try_set(n, "coltol", clamp(float(params["coltol"]), 0.0, 180.0))
    if "removeinline" in params:
        _try_set(n, "removeinline", bool(params["removeinline"]))
    if "inlinedist" in params:
        _try_set(n, "inlinedist", clamp(float(params["inlinedist"]), 0.0, 10.0))
    if "useattribute" in params:
        _try_set(n, "useattribute", bool(params["useattribute"]))
    if "attrib" in params:
        _try_set(n, "attrib", str(params["attrib"]))
    return _result(n)


@endpoint("remove_inside_faces")
def remove_inside_faces(params):
    """SideFX Labs Remove Inside Faces (labs::remove_inside_faces) — deletes interior/occluded faces
    that are never visible from outside (e.g. overlapping booleaned kit-bash geometry), reducing poly
    count. `input` (input 0) = the mesh; optional `clip` (input 1) = a clipping surface used when
    `bClipSurface` is on. `fPrecision`/`fCleaningThreshold` tune the visibility test. Data-only chain
    filter."""
    n = child_after(params["input"], "labs::remove_inside_faces", params.get("name"))
    if params.get("clip"):
        bridge_input(n, params["clip"], index=1, name_hint="clip")
    if "bRemoveInside" in params:
        _try_set(n, "bRemoveInside", bool(params["bRemoveInside"]))
    if "fPrecision" in params:
        _try_set(n, "fPrecision", clamp(float(params["fPrecision"]), 1e-4, 1.0))
    if "fCleaningThreshold" in params:
        _try_set(n, "fCleaningThreshold", clamp(float(params["fCleaningThreshold"]), 0.0, 1.0))
    if "bClipSurface" in params:
        _try_set(n, "bClipSurface", bool(params["bClipSurface"]))
    return _result(n)

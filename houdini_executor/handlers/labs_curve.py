"""SideFX Labs — Geometry/Curve tools (data-only handlers). Params verified against a live
H21.0.671 headless probe. Each Labs curve HDA is wrapped as a
typed handler exposing a curated scalar/enum subset; ramps, folder headers, string/attribute-name
and vector params that have no scalar tool-kind stay at HDA default.

The batch (highest version of each base name):
  boolean_curve::1.0            chain  in0=A curve, in1=B curve  -> curve boolean (subtract/intersect/shatter)
  curve_branches                chain  in0=curve                 -> scatter child branch curves
  curve_resample_by_density::1.0 chain in0=curve                 -> density/curvature-driven resample
  curve_sweep                   chain  in0=backbone curve        -> swept tube/ribbon
  merge_splines::1.0            chain  in0=curves                -> fuse/merge overlapping splines
  polywire_uv::1.1              chain  in0=edge network/curve    -> UV'd polywire tubes
  progressive_resample          chain  in0=curve                 -> even progressive resample
  spiral::1.1                   SOURCE (0 inputs)                -> fresh /obj geo holding a spiral/helix curve
  sweep_geometry                chain  in0=cross-section, in1=curve -> instance geometry along a curve
  view_vertex_order::1.0        chain  in0=geo                   -> vertex-order visualization (Cd/arrows, pass-through)

SECURITY: data-only. No code/callback/file parms are exposed — none of these nodes carry a file
surface. String parms that name an *attribute/group* (weightAttribute, groupname, ...) are left at
default unless explicitly a safe data name; no path or code is ever accepted.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)




def _idx_menu_set(node, parm, value, choices):
    """Ordered menu whose stored value is an INDEX (numeric tokens '0','1',...). Map a friendly
    token to its position and set the index."""
    if value in choices:
        return _try_set(node, parm, choices.index(value))
    return False


def _tok_menu_set(node, parm, token, tokens):
    """String-token menu (stored value is the token). Set by token; fall back to index."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        try:
            p.set(tokens.index(token))
            return True
        except Exception:
            return False


def _set_tuple_component(node, parm_tuple, index, value):
    """Set one component of a multi-float parm (e.g. spiral radius vec2) without disturbing the rest."""
    pt = node.parmTuple(parm_tuple)
    if pt is None or index >= len(pt):
        return False
    try:
        vals = list(pt.eval())
        vals[index] = value
        pt.set(tuple(vals))
        return True
    except Exception:
        return False


# ── ordered-menu friendly-token tuples (position == stored index) ────────────────────────────────
_BOOL_OP = ("subtract", "intersect", "shatter")               # boolean_curve operation 0/1/2
_RESAMPLE_BY = ("ramp", "attribute", "curvature")             # curve_resample_by_density resampleby 0/1/2
_SWEEP_MESH = ("circle", "line")                              # curve_sweep mesh_type 0/1
_FUSE_TARGETS = ("any_point", "endpoints_and_intersections", "endpoints")  # merge_splines fuseTargets 0/1/2
_ENDS_METHOD = ("none", "clip", "groups")                     # sweep_geometry ends_method 0/1/2
# string-token menus
_UVMODE = ("Normalized", "WidthRelative", "TexelArea")        # polywire_uv uvmode
_DIVIDEMODE = ("straight", "subd", "interp")                  # polywire_uv dividemode
_OUTCLASS = ("primitive", "point", "vertex")                  # view_vertex_order outclass


# ── 1. boolean_curve (chain; in0 = A curve, in1 = B curve) ───────────────────────────────────────
@endpoint("boolean_curve")
def boolean_curve(params):
    """Labs Boolean Curve (labs::boolean_curve::1.0) — 2D/curve boolean of two curve inputs.
    `input` (input 0) = curve A; `input_b` (input 1) = curve B. `operation`: subtract (A minus B),
    intersect (A ∩ B), or shatter (split A at B). `threshold` snaps near-coincident intersections when
    `enablethreshold` is on. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::boolean_curve::1.0", params.get("name"))
    if params.get("input_b"):
        bridge_input(n, params["input_b"], index=1, name_hint="curve_b")
    if "operation" in params:
        _idx_menu_set(n, "operation", str(params["operation"]), _BOOL_OP)
    if "enablethreshold" in params:
        _try_set(n, "enablethreshold", bool(params["enablethreshold"]))
    if "threshold" in params:
        _try_set(n, "threshold", clamp(float(params["threshold"]), 0.0, 10.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. curve_branches (chain; in0 = curve) ───────────────────────────────────────────────────────
@endpoint("curve_branches")
def curve_branches(params):
    """Labs Curve Branches (labs::curve_branches) — scatters child branch curves along the input
    curve(s) (input 0). `npts` = points per branch; `dist` = branch length; `spread`/`curl` shape the
    branch; the `*_variation` params add per-branch randomness; `domainu1..2` restrict the parent span
    the branches grow from. `vertical_offset` lifts branches along the growth axis. Data-only; the
    origin/direction/color VECTOR params and the noise ramp stay at HDA default."""
    n = child_after(params["input"], "labs::curve_branches", params.get("name"))
    if "domainu1" in params:
        _try_set(n, "domainu1", clamp(float(params["domainu1"]), 0.0, 1.0))
    if "domainu2" in params:
        _try_set(n, "domainu2", clamp(float(params["domainu2"]), 0.0, 1.0))
    if "npts" in params:
        _try_set(n, "npts", int(clamp(int(params["npts"]), 2, 200)))
    if "count_variation" in params:
        _try_set(n, "count_variation", int(clamp(int(params["count_variation"]), 0, 200)))
    if "dist" in params:
        _try_set(n, "dist", clamp(float(params["dist"]), 0.0, 100.0))
    if "dist_variation" in params:
        _try_set(n, "dist_variation", clamp(float(params["dist_variation"]), 0.0, 100.0))
    if "vertical_offset" in params:
        _try_set(n, "vertical_offset", clamp(float(params["vertical_offset"]), -100.0, 100.0))
    if "vertical_offset_variation" in params:
        _try_set(n, "vertical_offset_variation", clamp(float(params["vertical_offset_variation"]), 0.0, 100.0))
    if "mirror_x" in params:
        _try_set(n, "mirror_x", bool(params["mirror_x"]))
    if "spread" in params:
        _try_set(n, "spread", clamp(float(params["spread"]), -10.0, 10.0))
    if "spread_variation" in params:
        _try_set(n, "spread_variation", clamp(float(params["spread_variation"]), 0.0, 10.0))
    if "curl" in params:
        _try_set(n, "curl", clamp(float(params["curl"]), -10.0, 10.0))
    if "amp" in params:
        _try_set(n, "amp", clamp(float(params["amp"]), 0.0, 10.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. curve_resample_by_density (chain; in0 = curve) ────────────────────────────────────────────
@endpoint("curve_resample_by_density")
def curve_resample_by_density(params):
    """Labs Curve Resample by Density (labs::curve_resample_by_density::1.0) — resamples the input
    curve (input 0) with a non-uniform point density. `resampleby`: ramp (density ramp along the
    curve), attribute (a per-point weight attribute), or curvature (denser in tight bends).
    `maxsegments` caps the segment count to `segments`; `rampsamples` is the ramp lookup resolution.
    Data-only; the density ramp and the weight-attribute NAME stay at HDA default."""
    n = child_after(params["input"], "labs::curve_resample_by_density::1.0", params.get("name"))
    if "resampleby" in params:
        _idx_menu_set(n, "resampleby", str(params["resampleby"]), _RESAMPLE_BY)
    if "maxsegments" in params:
        _try_set(n, "maxsegments", bool(params["maxsegments"]))
    if "segments" in params:
        _try_set(n, "segments", int(clamp(int(params["segments"]), 1, 100000)))
    if "rampsamples" in params:
        _try_set(n, "rampsamples", int(clamp(int(params["rampsamples"]), 2, 10000)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. curve_sweep (chain; in0 = backbone curve, in1/in2 optional) ───────────────────────────────
@endpoint("curve_sweep")
def curve_sweep(params):
    """Labs Curve Sweep (labs::curve_sweep) — sweeps a cross-section along the backbone curve
    (input 0) to build a tube/ribbon. `mesh_type`: circle (tube) or line (ribbon); `divs` = radial
    divisions; `scale` = cross-section radius; `cuspangle` controls hard/soft edges; `cap_ends` closes
    a circle sweep. Data-only; the scale ramp and up_vector VECTOR stay at HDA default."""
    n = child_after(params["input"], "labs::curve_sweep", params.get("name"))
    if "mesh_type" in params:
        _idx_menu_set(n, "mesh_type", str(params["mesh_type"]), _SWEEP_MESH)
    if "divs" in params:
        _try_set(n, "divs", int(clamp(int(params["divs"]), 2, 512)))
    if "cap_ends" in params:
        _try_set(n, "cap_ends", bool(params["cap_ends"]))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 100.0))
    if "cuspangle" in params:
        _try_set(n, "cuspangle", clamp(float(params["cuspangle"]), 0.0, 180.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. merge_splines (chain; in0 = curves) ───────────────────────────────────────────────────────
@endpoint("merge_splines")
def merge_splines(params):
    """Labs Merge Splines (labs::merge_splines::1.0) — fuses/merges overlapping spline curves into a
    connected network. `input` (input 0) = the merged spline soup. `fuseDistance` = the snap radius;
    `fuseTargets` restricts what may fuse (any_point | endpoints_and_intersections | endpoints);
    `limitMergeOperations` and `onlyMergeIfMatching` gate the merge. Data-only; the attribute-name and
    group-name string parms + the visual-feedback controls stay at HDA default."""
    n = child_after(params["input"], "labs::merge_splines::1.0", params.get("name"))
    if "fuseDistance" in params:
        _try_set(n, "fuseDistance", clamp(float(params["fuseDistance"]), 0.0, 100.0))
    if "fuseTargets" in params:
        _idx_menu_set(n, "fuseTargets", str(params["fuseTargets"]), _FUSE_TARGETS)
    if "limitMergeOperations" in params:
        _try_set(n, "limitMergeOperations", bool(params["limitMergeOperations"]))
    if "onlyMergeIfMatching" in params:
        _try_set(n, "onlyMergeIfMatching", bool(params["onlyMergeIfMatching"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. polywire_uv (chain; in0 = edge network / curve) ───────────────────────────────────────────
@endpoint("polywire_uv")
def polywire_uv(params):
    """Labs PolyWire UV (labs::polywire_uv::1.1) — builds UV'd polywire tubes around an edge network
    or curve (input 0). `width` = tube radius; `div` = radial divisions; `cuspangle` = edge cusp;
    `uvmode` (Normalized | WidthRelative | TexelArea) + `texelscale` drive UV layout; `resamplecurve`
    with `length` pre-resamples the wire; `dividemode` (straight | subd | interp) sets the join style.
    Data-only; capture/attribute/group NAME strings stay at HDA default."""
    n = child_after(params["input"], "labs::polywire_uv::1.1", params.get("name"))
    if "width" in params:
        _try_set(n, "width", clamp(float(params["width"]), 1e-4, 100.0))
    if "maxscale" in params:
        _try_set(n, "maxscale", clamp(float(params["maxscale"]), 1.0, 100.0))
    if "maxvalence" in params:
        _try_set(n, "maxvalence", int(clamp(int(params["maxvalence"]), 1, 200)))
    if "div" in params:
        _try_set(n, "div", int(clamp(int(params["div"]), 2, 256)))
    if "cuspangle" in params:
        _try_set(n, "cuspangle", clamp(float(params["cuspangle"]), 0.0, 180.0))
    if "uvmode" in params:
        _tok_menu_set(n, "uvmode", str(params["uvmode"]), _UVMODE)
    if "texelscale" in params:
        _try_set(n, "texelscale", clamp(float(params["texelscale"]), 1e-4, 1000.0))
    if "resamplecurve" in params:
        _try_set(n, "resamplecurve", bool(params["resamplecurve"]))
    if "length" in params:
        _try_set(n, "length", clamp(float(params["length"]), 1e-4, 100.0))
    if "dividemode" in params:
        _tok_menu_set(n, "dividemode", str(params["dividemode"]), _DIVIDEMODE)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. progressive_resample (chain; in0 = curve) ─────────────────────────────────────────────────
@endpoint("progressive_resample")
def progressive_resample(params):
    """Labs Progressive Resample (labs::progressive_resample) — evenly resamples the input curve
    (input 0) with a progressive segment length driven by a per-point `pscale` attribute (the input
    MUST carry `pscale`, e.g. from a resample/attrib node, or the node fails to cook). `length` =
    target edge length (smaller = denser); `resolutionscale` scales the density; `maxpoints` hard-caps
    the output point count (cost governor); `preprocess` cleans the curve first. Data-only."""
    n = child_after(params["input"], "labs::progressive_resample", params.get("name"))
    if "resolutionscale" in params:
        _try_set(n, "resolutionscale", clamp(float(params["resolutionscale"]), 1e-3, 100.0))
    if "maxpoints" in params:
        _try_set(n, "maxpoints", int(clamp(int(params["maxpoints"]), 1, 1000000)))
    if "preprocess" in params:
        _try_set(n, "preprocess", bool(params["preprocess"]))
    if "length" in params:
        _try_set(n, "length", clamp(float(params["length"]), 1e-4, 100.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 8. spiral (SOURCE; 0 inputs) — fresh /obj geo ────────────────────────────────────────────────
@endpoint("spiral")
def spiral(params):
    """Labs Spiral (labs::spiral::1.1) — a SOURCE node (0 inputs): builds a fresh /obj geo holding a
    spiral / helix curve. `radius` = start radius, `radius_end` = end radius (a value differing from
    `radius` makes a logarithmic spiral); `loops` = turn count; `height` extrudes it into a helix;
    `points` = resolution; `helix_count` = number of interleaved strands. Fails on name collision.
    Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::spiral::1.1")
    if "radius" in params:
        _set_tuple_component(n, "radius", 0, clamp(float(params["radius"]), 0.0, 1000.0))
    if "radius_end" in params:
        _set_tuple_component(n, "radius", 1, clamp(float(params["radius_end"]), 0.0, 1000.0))
    if "height" in params:
        _try_set(n, "height", clamp(float(params["height"]), -1000.0, 1000.0))
    if "loops" in params:
        _try_set(n, "loops", clamp(float(params["loops"]), 0.0, 1000.0))
    if "rotation" in params:
        _try_set(n, "rotation", clamp(float(params["rotation"]), -3600.0, 3600.0))
    if "points" in params:
        _try_set(n, "points", int(clamp(int(params["points"]), 2, 100000)))
    if "helix_count" in params:
        _try_set(n, "helix_count", int(clamp(int(params["helix_count"]), 1, 100)))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


# ── 9. sweep_geometry (chain; in0 = cross-section geo, in1 = backbone curve — both required) ──────
@endpoint("sweep_geometry")
def sweep_geometry(params):
    """Labs Sweep Geometry (labs::sweep_geometry) — instances/sweeps a cross-section MESH along a
    backbone curve. `input` (input 0) = the cross-section geometry; `curve` (input 1) = the backbone
    curve (BOTH required). `middle_instances` repeats the mid section; `curve_slice`/`curve_offset`
    trim the span used; `twist` spins the section along the curve; `ends_method` (none | clip | groups)
    handles the caps. Data-only; group-NAME strings stay at HDA default."""
    n = child_after(params["input"], "labs::sweep_geometry", params.get("name"))
    bridge_input(n, params["curve"], index=1, name_hint="curve")
    if "auto_calculate_middle" in params:
        _try_set(n, "auto_calculate_middle", bool(params["auto_calculate_middle"]))
    if "middle_multiplier" in params:
        _try_set(n, "middle_multiplier", clamp(float(params["middle_multiplier"]), 0.0, 100.0))
    if "middle_instances" in params:
        _try_set(n, "middle_instances", int(clamp(int(params["middle_instances"]), 0, 10000)))
    if "curve_slice" in params:
        _try_set(n, "curve_slice", clamp(float(params["curve_slice"]), 0.0, 1.0))
    if "curve_offset" in params:
        _try_set(n, "curve_offset", clamp(float(params["curve_offset"]), 0.0, 1.0))
    if "twist" in params:
        _try_set(n, "twist", clamp(float(params["twist"]), -3600.0, 3600.0))
    if "curve_resolution" in params:
        _try_set(n, "curve_resolution", clamp(float(params["curve_resolution"]), 1e-3, 100.0))
    if "ends_method" in params:
        _idx_menu_set(n, "ends_method", str(params["ends_method"]), _ENDS_METHOD)
    if "mesh_min" in params:
        _try_set(n, "mesh_min", clamp(float(params["mesh_min"]), 0.0, 1.0))
    if "mesh_max" in params:
        _try_set(n, "mesh_max", clamp(float(params["mesh_max"]), 0.0, 1.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 10. view_vertex_order (chain; in0 = geo) — vertex-order visualization pass-through ────────────
@endpoint("view_vertex_order")
def view_vertex_order(params):
    """Labs View Vertex Order (labs::view_vertex_order::1.0) — annotates the input geometry (input 0)
    with a vertex-order visualization: per-element color plus optional order arrows, passing the
    source geometry through. `arrowScale` sizes the arrows; `outclass` (primitive | point | vertex)
    picks the color class; `includeSourceGeometry` merges the original geo with the guide;
    `outputPrimNumberTgl` writes a prim-number group. Data-only."""
    n = child_after(params["input"], "labs::view_vertex_order::1.0", params.get("name"))
    if "arrowScale" in params:
        _try_set(n, "arrowScale", clamp(float(params["arrowScale"]), 0.0, 100.0))
    if "outclass" in params:
        _tok_menu_set(n, "outclass", str(params["outclass"]), _OUTCLASS)
    if "includeSourceGeometry" in params:
        _try_set(n, "includeSourceGeometry", bool(params["includeSourceGeometry"]))
    if "outputPrimNumberTgl" in params:
        _try_set(n, "outputPrimNumberTgl", bool(params["outputPrimNumberTgl"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

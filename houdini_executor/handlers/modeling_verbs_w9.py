"""SOP modeling-verbs lane — curve/surface construction + polygon-topology verbs for
building and re-shaping geometry: loft/patch/spline surfaces from curves, cap/fillet/stitch/join
edges & hulls, and topology utilities (polysoup, polycut, polypath, polyhinge, polystitch,
convertline, circlespline, circlefromedges, orientalongcurve).

All params + menu tokens verified against live H21.0.671 via hython probe. Archetypes:
  * Every tool is an OPERATOR on upstream geometry: `input` is input 0 (wired by child_after).
  * A few carry a SECOND operand wired via bridge_input: poly_loft (`rest`, in1), fillet (`aux`, in1),
    stitch (`aux`, in1), orient_along_curve (`banking_curve`, in1). Each degrades to cooked:false
    gracefully (via _finish_op) if a genuinely-required operand is missing — never crashes.

Not wrapped (already covered): bridge -> tool `bridge` = polybridge; polywire ->
already wrapped (tool `polywire`). DEFERRED (interactive / not data-cookable headless): polyknit
(needs a hand-authored ordered point list), drawcurve (interactive stroke tool, pts=0, carries a
file-stash parm), curveclay (legacy spline-clay; needs rest+deformed 3D face inputs to cook).

SECURITY: the curated param sets below expose ONLY data params (counts, distances, divisions, menu
tokens, booleans, group/attribute-name strings, vec3s). No file-path, VEX/expression, python, or
callback parm is exposed anywhere in this lane (probe-confirmed).
"""

import hou
from houdini_executor.server import (
    endpoint, child_after, clamp, resolve_node, bridge_input,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared helpers (copied from the feather lane idiom; probe-safe: never invent a parm) ─────────────




def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token: set the token directly (validated against the live token set)."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _vec_set(node, parm, values):
    """Set a multi-component (tuple) parm — vec3 floats or an int pair (e.g. polypatch divisions)."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set([float(x) for x in values])
        return True
    except Exception:  # noqa: BLE001
        try:
            pt.set([int(x) for x in values])
            return True
        except Exception:  # noqa: BLE001
            return False


def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  m=index-menu(tokens)
       ms=string-menu(tokens)  v=vec/tuple (extra ignored)."""
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
        elif kind == "v":
            _vec_set(node, parm, v)


def _geo_or_none(n):
    """Return the node's geometry, or None if it hasn't cooked / errored (never raises opaquely)."""
    try:
        return n.geometry()
    except Exception:  # noqa: BLE001
        return None


def _finish_op(n, **extra):
    """Report counts when the node cooked; otherwise cooked:false + errors (never crash on a
    not-yet-cooked / input-starved node — guards BOTH the cook and the geometry readback)."""
    r = {"node": n.path()}
    try:
        n.cook()
    except Exception:  # noqa: BLE001 — surfaced via n.errors() below
        pass
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


# menu token tuples reused across tools
_CLOSEU = ("nonewu", "wu", "ifprimwu")
_CLOSEV = ("nonewv", "wv", "ifprimwv")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SURFACE CONSTRUCTION FROM CURVES
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("poly_patch")
def poly_patch(params):
    """Poly Patch — build a smooth polygon patch surface across a hull/cage of curves or a mesh
    (polypatch). `input` (hull curves / mesh) is input 0. basis picks the smoothing basis
    (cardinal | bspline); connectivity how the hull rows/cols are connected into the patch; divisions
    [u,v] the output resolution; close_u/close_v wrap the patch; output_polygons emits polys instead
    of a mesh primitive. Great for tidying a rough curve cage into a clean subdiv-ready surface."""
    n = child_after(params["input"], "polypatch", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("basis", "basis", "m", ("cardinal", "bspline")),
        ("connectivity", "connecttype", "m",
         ("rows", "cols", "rowcol", "triangles", "quads", "alttriangles", "revtriangles", "inheritconnect")),
        ("close_u", "closeu", "m", _CLOSEU),
        ("close_v", "closev", "m", _CLOSEV),
        ("divisions", "divisions", "v", None),
        ("output_polygons", "polys", "b", None),
    ])
    return _finish_op(n)


@endpoint("poly_loft")
def poly_loft(params):
    """Poly Loft — skin a polygon surface across a sequence of cross-section curves (polyloft). `input`
    (input 0) carries the ordered cross-sections MERGED into one stream (e.g. merge two circles);
    optional `rest` (input 1) supplies rest geometry. connect_closest_ends auto-orders open curves;
    consolidate + dist weld near-coincident points; minimize picks the triangulation cost metric;
    close_u/close_v wrap the surface; create_group + group_name tag the new polys. Classic tube /
    ribbon / skinned-surface builder from profile curves."""
    n = child_after(params["input"], "polyloft", params.get("name"))
    if params.get("rest"):
        bridge_input(n, params["rest"], index=1, name_hint="rest")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("connect_closest_ends", "proximity", "b", None),
        ("consolidate", "consolidate", "b", None),
        ("dist", "dist", "f", (0.0, 1000.0)),
        ("minimize", "minimize", "m", ("point2", "point3")),
        ("close_u", "closeu", "m", _CLOSEU),
        ("close_v", "closev", "m", _CLOSEV),
        ("create_group", "creategroup", "b", None),
        ("group_name", "polygroup", "s", None),
    ])
    return _finish_op(n)


@endpoint("poly_spline")
def poly_spline(params):
    """Poly Spline — fit a smooth spline curve through a polyline's points and re-output it as a
    resampled polygon curve (polyspline). `input` (a polyline / face) is input 0. spline_type picks
    the interpolation basis; closure whether to close the curve; division_method how sample density is
    distributed (standard | even length | even x/y/z); segment_length / divisions / sample_divisions
    the output resolution; tension the CV tension. Turns a coarse control polygon into a smooth curve."""
    n = child_after(params["input"], "polyspline", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("spline_type", "basis", "m",
         ("bezier", "sbezier", "c1bezier", "degree2", "bspline", "cardinal", "linear")),
        ("closure", "closure", "m", ("cnone", "calways", "cifpoly")),
        ("division_method", "divide", "m", ("standard", "evenlen", "evenx", "eveny", "evenz")),
        ("segment_length", "segsize", "f", (0.0001, 1000.0)),
        ("divisions", "polydivs", "i", (1, 1000)),
        ("sample_divisions", "edgedivs", "i", (1, 1000)),
        ("tension", "tension", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("circle_spline")
def circle_spline(params):
    """Circle Spline — fit circular-arc / ellipse / helix splines through a control polygon
    (circlespline), giving perfectly round curvature that a freeform spline can't. `input` (control
    polygon) is input 0. spline_type (hybrid | circle | ellipse | helix); helix_type the helix
    winding style; reparm_strength re-parametrizes for even spacing; segment_divisions the output
    resolution; output_tangent + tangent_attrib write a tangent attribute along the curve."""
    n = child_after(params["input"], "circlespline", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("spline_type", "splinetype", "m", ("hybrid", "circle", "ellipse", "helix")),
        ("helix_type", "helixtype", "m", ("directional", "balanced", "blended")),
        ("reparm_strength", "reparmstrength", "f", (0.0, 1.0)),
        ("segment_divisions", "segmentdivision", "i", (1, 1000)),
        ("output_tangent", "outputtangent", "b", None),
        ("tangent_attrib", "tangentattrib", "s", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# EDGE / SURFACE JOINING (caps, fillets, stitches, joins)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("poly_cap")
def poly_cap(params):
    """Poly Cap — fill open polygon boundaries (unshared edges) with cap polygons (polycap) to close a
    shell — the fast way to seal a tube/extrusion end or a hole ring. `input` is input 0. Without a
    `group`, cap_all seals EVERY unshared-edge loop; reverse flips cap orientation; triangulate fans
    the cap into triangles; unique un-shares cap points; update_normals recomputes point normals."""
    n = child_after(params["input"], "polycap", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("cap_all", "capall", "b", None),
        ("reverse", "reverse", "b", None),
        ("triangulate", "triangulate", "b", None),
        ("unique", "unique", "b", None),
        ("update_normals", "updatenorms", "b", None),
    ])
    return _finish_op(n)


@endpoint("cap")
def cap(params):
    """Cap — add end/pole caps to NURBS/mesh surfaces and open curves, per U/V boundary (cap). `input`
    is input 0. first_u_cap / last_u_cap / first_v_cap / last_v_cap each pick a cap style
    (none | facet | share | round | tangent); divisions_u / divisions_v the rounded-cap resolution;
    scale_u / scale_v bulge the caps. Use on tubes/spheres/revolved surfaces to close their ends."""
    n = child_after(params["input"], "cap", params.get("name"))
    _CAPS = ("none", "facet", "share", "round", "tangent")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("first_u_cap", "firstu", "m", _CAPS),
        ("last_u_cap", "lastu", "m", _CAPS),
        ("first_v_cap", "firstv", "m", _CAPS),
        ("last_v_cap", "lastv", "m", _CAPS),
        ("divisions_u", "divsu1", "i", (0, 100)),
        ("divisions_v", "divsv1", "i", (0, 100)),
        ("scale_u", "scaleu1", "f", (0.0, 100.0)),
        ("scale_v", "scalev1", "f", (0.0, 100.0)),
    ])
    return _finish_op(n)


@endpoint("fillet")
def fillet(params):
    """Fillet — build a smooth transition surface between adjacent primitives / two curves (fillet).
    `input` (the primitives to fillet, input 0) plus optional `aux` (auxiliary source, input 1).
    fillet: which prims (all | group | skip); inc how many prims each fillet spans; loop wraps last to
    first; direction (ujoin | vjoin) the join direction; fillet_type the transition shape
    (freeform | convex | circular); order the surface order; cut trims the originals; seamless matches
    the input to the fillets. Rounds hard junctions between surfaces."""
    n = child_after(params["input"], "fillet", params.get("name"))
    if params.get("aux"):
        bridge_input(n, params["aux"], index=1, name_hint="aux")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("fillet", "fillet", "m", ("all", "group", "skip")),
        ("inc", "inc", "i", (1, 100)),
        ("loop", "loop", "b", None),
        ("direction", "dir", "m", ("ujoin", "vjoin")),
        ("fillet_type", "fillettype", "m", ("freeform", "convex", "circular")),
        ("order", "order", "i", (2, 11)),
        ("seamless", "seamless", "b", None),
        ("cut", "cut", "b", None),
    ])
    return _finish_op(n)


@endpoint("stitch")
def stitch(params):
    """Stitch — blend/stitch two adjacent surface hulls together along shared boundaries (stitch).
    `input` (the surface hulls to stitch, input 0, e.g. two merged NURBS/mesh grids) plus optional
    `aux` (auxiliary hull, input 1). stitch: which prims (all | group | skip); inc the span; loop
    wraps; direction (ujoin | vjoin); tolerance / bias the blend; do_stitch / tangent / sharp the
    continuity. Note: input must be surface HULLS (open polylines error 'must be a hull')."""
    n = child_after(params["input"], "stitch", params.get("name"))
    if params.get("aux"):
        bridge_input(n, params["aux"], index=1, name_hint="aux")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("stitch", "stitchop", "m", ("all", "group", "skip")),
        ("inc", "inc", "i", (1, 100)),
        ("loop", "loop", "b", None),
        ("direction", "dir", "m", ("ujoin", "vjoin")),
        ("tolerance", "tolerance", "f", (0.0, 100.0)),
        ("bias", "bias", "f", (0.0, 1.0)),
        ("do_stitch", "dostitch", "b", None),
        ("tangent", "dotangent", "b", None),
        ("sharp", "sharp", "b", None),
    ])
    return _finish_op(n)


@endpoint("join")
def join(params):
    """Join — connect a sequence of separate primitives (curves or surfaces) end-to-end into a single
    continuous primitive (join). `input` is input 0 (the prims to join, merged into one stream).
    join_op: which prims (all | group | skip); inc the span; direction (ujoin | vjoin); blend +
    tolerance + bias control the seam; loop wraps last to first; only_connected joins just topological
    neighbours. Turns many little curve/surface pieces into one long primitive."""
    n = child_after(params["input"], "join", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("join_op", "joinop", "m", ("all", "group", "skip")),
        ("inc", "inc", "i", (1, 100)),
        ("direction", "dir", "m", ("ujoin", "vjoin")),
        ("blend", "blend", "b", None),
        ("tolerance", "tolerance", "f", (0.0, 100.0)),
        ("bias", "bias", "f", (0.0, 1.0)),
        ("loop", "loop", "b", None),
        ("only_connected", "onlyconnected", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# POLYGON TOPOLOGY VERBS
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("poly_hinge")
def poly_hinge(params):
    """Poly Hinge — fold/rotate polygons about a hinge edge or axis, subdividing the crease into
    segments (polyhinge) — the tool for opening panels, petals, pop-up folds. `input` is input 0.
    group + group_type (primitive | edge) pick what folds; pivot_mode how the hinge line is defined;
    hinge_edge the edge to hinge on; hinge_angle the fold angle; divisions the crease segments;
    enable_inset + inset add a bevel; output_front / output_back / output_side toggle the result
    shells. Point-position based; no code parm."""
    n = child_after(params["input"], "polyhinge", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("group_type", "grouptype", "m", ("primitive", "edge")),
        ("pivot_mode", "pivotmode", "m", ("edge", "posanddir", "attribute")),
        ("hinge_edge", "hingeedge", "s", None),
        ("pivot_pos", "hingepivotpos", "v", None),
        ("pivot_dir", "hingepivotdir", "v", None),
        ("hinge_angle", "hingeangle", "f", (-360.0, 360.0)),
        ("max_division_angle", "maxdivisionangle", "f", (0.1, 180.0)),
        ("divisions", "divisions", "i", (1, 100)),
        ("enable_inset", "enableinset", "b", None),
        ("inset", "inset", "f", (0.0, 100.0)),
        ("output_front", "outputfront", "b", None),
        ("output_back", "outputback", "b", None),
        ("output_side", "outputside", "b", None),
    ])
    return _finish_op(n)


@endpoint("poly_stitch")
def poly_stitch(params):
    """Poly Stitch — weld the boundaries of two polygon shells together, filling the gap with bridging
    polygons (polystitch) — repair seams / join separately-modeled halves. `input` is input 0.
    stitch_group / corners restrict which boundary polys/points are stitched; tolerance the max
    stitch distance; consolidate fuses coincident points; find_corners + corner_angle auto-detect
    corner points. Topology repair, point-position driven."""
    n = child_after(params["input"], "polystitch", params.get("name"))
    _apply(n, params, [
        ("stitch_group", "stitch", "s", None),
        ("corners", "corners", "s", None),
        ("tolerance", "tol3d", "f", (0.0, 100.0)),
        ("consolidate", "consolidate", "b", None),
        ("find_corners", "findcorner", "b", None),
        ("corner_angle", "angle", "f", (0.0, 180.0)),
    ])
    return _finish_op(n)


@endpoint("poly_soup")
def poly_soup(params):
    """Poly Soup — collapse many polygons into a single lightweight 'polysoup' primitive (polysoup),
    cutting memory + node overhead for dense static meshes. `input` is input 0. group restricts the
    source; min_polys the size threshold; convex triangulates to convex polys; use_max_sides +
    max_sides cap polygon sides; merge_vertices welds identical verts; ignore_attribs / ignore_groups
    drop per-prim data for a lighter soup. Great before instancing / heavy scatter targets."""
    n = child_after(params["input"], "polysoup", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("ignore_attribs", "ignoreattribs", "b", None),
        ("ignore_groups", "ignoregroups", "b", None),
        ("min_polys", "minpolys", "i", (1, 1000000)),
        ("convex", "convex", "b", None),
        ("use_max_sides", "usemaxsides", "b", None),
        ("max_sides", "maxsides", "i", (3, 100)),
        ("merge_vertices", "mergeverts", "b", None),
    ])
    return _finish_op(n)


@endpoint("poly_cut")
def poly_cut(params):
    """Poly Cut — cut/split polygons along points, edges, or an attribute-crossing, optionally removing
    the cut region (polycut). `input` is input 0. group restricts affected polys; type (points | edges)
    the cut primitive; cut_points / cut_edges name the cut locations; strategy (remove | cut) whether
    to delete or just split; cut_attrib + cut_value + cut_threshold cut where an attribute crosses a
    value (an isocut); keep_closed re-closes the result. Data-driven cutting; no code parm."""
    n = child_after(params["input"], "polycut", params.get("name"))
    _apply(n, params, [
        ("group", "polygons", "s", None),
        ("type", "type", "m", ("points", "edges")),
        ("cut_points", "cutpoints", "s", None),
        ("cut_edges", "cutedges", "s", None),
        ("strategy", "strategy", "m", ("remove", "cut")),
        ("cut_attrib", "cutattrib", "s", None),
        ("cut_value", "cutvalue", "f", (-1000000.0, 1000000.0)),
        ("cut_threshold", "cutthreshold", "f", (0.0, 1000000.0)),
        ("keep_closed", "keepclosed", "b", None),
    ])
    return _finish_op(n)


@endpoint("poly_path")
def poly_path(params):
    """Poly Path — reconnect loose edges / open polylines into clean continuous paths (polypath),
    tidying edge extractions and boundary curves for downstream sweep/resample. `input` is input 0.
    connect_ends joins nearby endpoints (within max_end_dist); connect_only_to_ends restricts joins to
    other endpoints (no mid-curve T-junctions); close_loops closes isolated rings. Curve cleanup verb."""
    n = child_after(params["input"], "polypath", params.get("name"))
    _apply(n, params, [
        ("connect_ends", "connectends", "b", None),
        ("max_end_dist", "maxendptdist", "f", (0.0, 1000.0)),
        ("connect_only_to_ends", "connectonlytoends", "b", None),
        ("close_loops", "closeloops", "b", None),
    ])
    return _finish_op(n)


@endpoint("convert_line")
def convert_line(params):
    """Convert Line — convert geometry edges into polyline curves (convertline) — extract a wireframe
    / edge-curves from a mesh for polywire, resample, or sweep. `input` is input 0. group restricts
    the source; connect_path chains edges into continuous paths; keep_order preserves group order;
    close_loops closes isolated rings; remove_unused drops orphaned points; compute_length +
    length_name write a per-primitive rest-length attribute. Emits polyline curves."""
    n = child_after(params["input"], "convertline", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("keep_order", "keeporder", "b", None),
        ("connect_path", "connectpath", "b", None),
        ("close_loops", "closeloops", "b", None),
        ("remove_unused", "remove", "b", None),
        ("compute_length", "computelength", "b", None),
        ("length_name", "lengthname", "s", None),
    ])
    return _finish_op(n)


@endpoint("circle_from_edges")
def circle_from_edges(params):
    """Circle From Edges — snap a ring of points/edges onto a best-fit circle (circlefromedges) — make
    a bolt-hole, pipe end, or wheel arch perfectly round. `input` is input 0. group + group_type pick
    the ring; only_boundary uses just the group boundary; explicit_radius + radius force a radius
    (else best-fit); scale grows/shrinks the fitted circle; output_edge_group names the result edges.
    Point-position based."""
    n = child_after(params["input"], "circlefromedges", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("group_type", "grouptype", "m", ("auto", "vertices", "edges", "points", "prims")),
        ("only_boundary", "getboundary", "b", None),
        ("explicit_radius", "explicitradius", "b", None),
        ("radius", "radius", "f", (0.0, 1000000.0)),
        ("scale", "scale", "f", (0.0, 1000.0)),
        ("output_edge_group", "outputedgegroup", "s", None),
    ])
    return _finish_op(n)


@endpoint("orient_along_curve")
def orient_along_curve(params):
    """Orient Along Curve — compute per-point orientation frames (tangent/up + rotations) along curves
    (orientalongcurve) — the rig for sweeping, copy-to-curve, or ribbon twist. `input` (curves) is
    input 0; optional `banking_curve` (input 1) drives banking. tangent_type how tangents are derived;
    up_vector_type + up_vector the reference up; apply_roll/roll, apply_yaw/yaw, apply_pitch/pitch add
    twist; scale sizes the frames; class (point | vertex); output_quaternion + quaternion_name write
    an `orient` quaternion for copy-to-points. Attribute-name / vec params only; no code parm."""
    n = child_after(params["input"], "orientalongcurve", params.get("name"))
    if params.get("banking_curve"):
        bridge_input(n, params["banking_curve"], index=1, name_hint="banking_curve")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("tangent_type", "tangenttype", "m", ("avgdir", "diff", "prev", "next", "none")),
        ("up_vector_type", "upvectortype", "m", ("normal", "x", "y", "z", "attrib", "custom")),
        ("up_vector", "upvector", "v", None),
        ("rotate_order", "rOrd", "m", ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")),
        ("apply_roll", "applyroll", "b", None),
        ("roll", "roll", "f", (-360000.0, 360000.0)),
        ("apply_yaw", "applyyaw", "b", None),
        ("yaw", "yaw", "f", (-360000.0, 360000.0)),
        ("apply_pitch", "applypitch", "b", None),
        ("pitch", "pitch", "f", (-360000.0, 360000.0)),
        ("scale", "scale", "f", (0.0, 1000.0)),
        ("class", "class", "m", ("point", "vertex")),
        ("output_quaternion", "outputquaternion", "b", None),
        ("quaternion_name", "quaternionname", "s", None),
    ])
    return _finish_op(n)

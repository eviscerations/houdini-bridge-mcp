"""Model / geometry construction handlers. Params verified against live H21.0.671 nodes.

All operators take a scene-graph SOP path (`input`) and wire a new node after it (the
scene-construction primitive), except `create_primitive`, which builds a fresh /obj geo and
FAILS on name collision (never destroys existing user work).
"""

import json

import hou
from houdini_executor.server import endpoint, child_after, clamp, resolve_node, bridge_into, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set

try:
    from houdini_executor.governor import governor_gate, advise, magnitude_advice
except Exception:  # noqa: BLE001 — governor is advisory telemetry; must never block handler import
    def governor_gate(op_label):  # fail-soft stub
        return {"band": "unknown"}

    def advise(result, node=None):  # fail-soft stub
        return result

    def magnitude_advice(op_label, params):  # fail-soft stub
        return {"level": "ok", "note": "governor unavailable"}






def _set_literal(node, parm, value):
    """Pin a literal value on a parm that may carry a channel expression (e.g. timeshift's $F/$T):
    clear any expression/keyframes first so the literal wins on eval. Probe-safe (no-op if absent)."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.deleteAllKeyframes()
    except Exception:
        pass
    try:
        p.set(value)
        return True
    except Exception:
        return False


_BOOL_OPS = {"union": "union", "intersect": "intersect", "subtract": "subtract"}


@endpoint("boolean")
def boolean(params):
    """Boolean (mesh CSG) of A (input0) against B (input1). operation: union|intersect|subtract.
    subtract_side (aminusb|bminusa|both) picks the kept side for subtract. a_type/b_type (solid|
    surface) tell the node whether each operand is a closed solid (default) or an open shell — set
    surface for scan tiles / single-sided meshes or the result is empty/inverted. detriangulate
    (none|unchanged|all) merges the boolean-cut triangles back into n-gons."""
    op = str(params.get("operation", "union"))
    if op not in _BOOL_OPS:
        raise ValueError("operation must be union|intersect|subtract")
    governor_gate("boolean")  # advisory; refuses only in the catastrophic band
    n = child_after(params["input"], "boolean::2.0", params.get("name"))
    if params.get("input_b"):
        bridge_input(n, params["input_b"], index=1, name_hint="input_b")
    _try_set(n, "booleanop", _BOOL_OPS[op])
    if "subtract_side" in params:
        _menu_set(n, "subtractchoices", str(params["subtract_side"]), ("aminusb", "bminusa", "both"))
    if "a_type" in params:
        _menu_set(n, "asurface", str(params["a_type"]), ("solid", "surface"))
    if "b_type" in params:
        _menu_set(n, "bsurface", str(params["b_type"]), ("solid", "surface"))
    if "detriangulate" in params:
        _menu_set(n, "detriangulate", str(params["detriangulate"]), ("none", "unchanged", "all"))
    g = n.geometry()
    result = advise({"node": n.path(), "operation": op, "prims": len(g.prims())}, n)
    result["magnitude"] = magnitude_advice("boolean", params)
    return result


_PE_XFORMSPACE = ("local", "global")
_PE_SPLITTYPE = ("elements", "components")


@endpoint("polyextrude")
def polyextrude(params):
    """Extrude polygon faces along their normals. distance = push depth, inset = shrink the cap
    (NEGATIVE inset = grow it, the concentric-ring trick), divisions = side-wall loops, twist =
    rotate the cap (deg). `group` restricts to a face group. front_group / side_group name output
    prim groups tagging the new cap / wall faces for the next op. distance_attrib scales height per
    face from a PRIMITIVE attribute (facet first).
    OUTPUT CAPS: output_front/output_side (bool) toggle those caps — set output_front=false for an
    OPEN shell; back_group names a back-cap prim group (double-sided extrude).
    TRANSFORM EXTRUDED FRONT: set cap_translate/cap_rotate/cap_scale ([x,y,z]) to move/spin/shrink
    the extruded cap after extrusion, in xform_space=local (per-face) or global. This is the
    inset+shift-in-one-op idiom (rib/boss detailing).
    SPLIT: split_type=components extrudes each connected piece independently (instead of the whole
    group as one); split_group names the group to split by."""
    n = child_after(params["input"], "polyextrude::2.0", params.get("name"))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if "distance" in params:
        n.parm("dist").set(clamp(float(params["distance"]), -1e6, 1e6))
    if "inset" in params:
        n.parm("inset").set(clamp(float(params["inset"]), -1e6, 1e6))
    if "divisions" in params:
        n.parm("divs").set(int(clamp(int(params["divisions"]), 1, 200)))
    if "twist" in params:
        _try_set(n, "twist", clamp(float(params["twist"]), -180.0, 180.0))
    if "output_front" in params:
        _try_set(n, "outputfront", bool(params["output_front"]))
    if "output_side" in params:
        _try_set(n, "outputside", bool(params["output_side"]))
    if params.get("front_group"):
        _try_set(n, "outputfront", True)
        _try_set(n, "outputfrontgrp", True)
        _try_set(n, "frontgrp", str(params["front_group"]))
    if params.get("side_group"):
        _try_set(n, "outputside", True)
        _try_set(n, "outputsidegrp", True)
        _try_set(n, "sidegrp", str(params["side_group"]))
    if params.get("back_group") or params.get("output_back"):
        _try_set(n, "outputback", True)
        if params.get("back_group"):
            _try_set(n, "outputbackgrp", True)
            _try_set(n, "backgrp", str(params["back_group"]))
    # Transform Extruded Front — move/rotate/scale the extruded cap (local per-face or global space).
    if (params.get("xform_front") or "xform_space" in params
            or any(k in params for k in ("cap_translate", "cap_rotate", "cap_scale"))):
        _try_set(n, "xformfront", True)
        if "xform_space" in params:
            _menu_set(n, "xformspace", str(params["xform_space"]), _PE_XFORMSPACE)
        if "cap_translate" in params and len(params["cap_translate"]) == 3:
            for pn, v in zip(("translatex", "translatey", "translatez"), params["cap_translate"]):
                _try_set(n, pn, float(v))
        if "cap_rotate" in params and len(params["cap_rotate"]) == 3:
            for pn, v in zip(("rotatex", "rotatey", "rotatez"), params["cap_rotate"]):
                _try_set(n, pn, float(v))
        if "cap_scale" in params and len(params["cap_scale"]) == 3:
            for pn, v in zip(("scalex", "scaley", "scalez"), params["cap_scale"]):
                _try_set(n, pn, float(v))
    # Split-Group — extrude each connected piece / element independently in one op.
    if "split_type" in params:
        _menu_set(n, "splittype", str(params["split_type"]), _PE_SPLITTYPE)
    if params.get("split_group"):
        _try_set(n, "usesplitgroup", True)
        _try_set(n, "splitgroup", str(params["split_group"]))
    # Per-face extrusion depth from a PRIMITIVE float attribute (multiplies `dist`): variable-height
    # buildings / greebles from a single node. polyextrude::2.0 reads a prim attr, not a point attr.
    if params.get("distance_attrib"):
        p = n.parm("uselocalzscaleattrib")
        if p is not None:
            p.set(1)
            n.parm("localzscaleattrib").set(str(params["distance_attrib"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims())}


_BEVEL_GROUPTYPE = ("prims", "points", "edges", "guess")
_BEVEL_SHAPE = ("none", "solid", "crease", "chamfer", "round")
_BEVEL_LIMIT = ("never", "individually", "simultaneously")


@endpoint("polybevel")
def polybevel(params):
    """Bevel/round edges or points. offset = fillet size, divisions = round segments (1 = flat
    chamfer). `group` (+ group_type=edges) restricts to specific edges — WITHOUT a group EVERY edge
    is beveled. `shape` picks the fillet profile (round|chamfer|crease|solid). On tight hard-surface
    geometry beveled loops can overrun and self-intersect: stop_loops (never|individually|
    simultaneously) halts loops before they collide, and detect_collisions=true adds the
    self-intersection / pinch guards — the difference between a clean bevel and a tangled one."""
    n = child_after(params["input"], "polybevel::3.0", params.get("name"))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _BEVEL_GROUPTYPE)
    if "shape" in params:
        _menu_set(n, "filletshape", str(params["shape"]), _BEVEL_SHAPE)
    if "offset" in params:
        n.parm("offset").set(clamp(float(params["offset"]), 0.0, 1e6))
    if "divisions" in params:
        n.parm("divisions").set(int(clamp(int(params["divisions"]), 1, 100)))
    if "stop_loops" in params:
        _menu_set(n, "limit", str(params["stop_loops"]), _BEVEL_LIMIT)
    if "detect_collisions" in params:
        on = bool(params["detect_collisions"])
        _try_set(n, "detectcollisions", on)
        _try_set(n, "stopatcollisions", on)
        _try_set(n, "stopatpinches", on)
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims())}


# ── sweep (curve -> surface): the keystone generative op ─────────────────────────────────────────────
# Verified sweep::2.0 contract (H21.0.671): input0 = backbone/spine curve, input1 = optional cross
# section (only read when surfaceshape='input'). Built-in profiles: tube (radius+cols), square/ribbon
# (width). Orientation is a stable auto-frame (equivalent to Orientation-Along-Curve) — no polyframe
# prerequisite; upstream N/up on the spine is honored (transformbyattribs defaults on). Data-only:
# every param is a typed scalar / enum / vector; no code path. Polycount ~= spine_points x cols.
_SWEEP_SHAPE = ("input", "tube", "square", "ribbon")
_SWEEP_SURFTYPE = ("points", "rows", "cols", "rowcol", "tris", "quads", "alttris", "revtris")
_SWEEP_ENDCAP = ("none", "single", "grid", "sidesingle")
_SWEEP_PRIMTYPE = ("auto", "poly", "mesh", "nurbs", "bezier", "polysoup")
_SWEEP_UPTYPE = ("normal", "x", "y", "z", "attrib", "custom")


@endpoint("sweep")
def sweep(params):
    """Sweep a cross-section along a backbone curve -> surface (the curve->geometry op: pipes, cables,
    rails, ropes, road/river ribbons, architectural trim). `input` = backbone/spine SOP (input 0).
    `shape`:
      tube   -> built-in round tube (uses `radius`; `cols` = sides)
      square -> built-in square tube (uses `width`; `cols` = subdivs)
      ribbon -> built-in flat ribbon (uses `width`)
      input  -> your own profile: wire a cross-section SOP via `cross_section` (input 1)
    Orientation uses a stable auto-frame (no polyframe needed); pass `up_vector`/`up_axis` to force it,
    or stamp N/up on the spine upstream (honored automatically). `roll`/`full_twists` add twist;
    `end_cap` caps open tube ends; `output_type` overrides the primitive type. Polycount ~= spine points
    x `cols` — governor-advised (down-scale cols or the spine density if flagged)."""
    shape = str(params.get("shape", "tube"))
    if shape not in _SWEEP_SHAPE:
        raise ValueError("shape must be one of %s" % "|".join(_SWEEP_SHAPE))
    if shape == "input" and not params.get("cross_section"):
        raise ValueError("shape='input' requires a `cross_section` SOP (wired to input 1)")
    governor_gate("sweep")  # advisory; refuses only in the catastrophic VRAM/RAM band
    n = child_after(params["input"], "sweep::2.0", params.get("name"))
    if params.get("cross_section"):
        bridge_input(n, params["cross_section"], index=1, name_hint="cross_section")
    _menu_set(n, "surfaceshape", shape, _SWEEP_SHAPE)
    if "surface_type" in params:
        _menu_set(n, "surfacetype", str(params["surface_type"]), _SWEEP_SURFTYPE)
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-6, 1e6))
    if "width" in params:
        _try_set(n, "width", clamp(float(params["width"]), 1e-6, 1e6))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-6, 1e6))
    if "cols" in params:
        _try_set(n, "cols", int(clamp(int(params["cols"]), 2, 256)))
    # twist / roll
    if "roll" in params:
        _try_set(n, "applyroll", True)
        _try_set(n, "roll", clamp(float(params["roll"]), -1e5, 1e5))
    if "full_twists" in params:
        _try_set(n, "applyroll", True)
        _try_set(n, "fulltwists", int(clamp(int(params["full_twists"]), -1000, 1000)))
    # orientation: forced up-vector (custom) or a fixed axis; else the stable auto-frame
    up = params.get("up_vector")
    if isinstance(up, (list, tuple)) and len(up) == 3:
        _menu_set(n, "upvectortype", "custom", _SWEEP_UPTYPE)
        try:
            n.parmTuple("upvector").set(tuple(float(v) for v in up))
        except Exception:  # noqa: BLE001
            pass
    elif "up_axis" in params and str(params["up_axis"]) in _SWEEP_UPTYPE:
        _menu_set(n, "upvectortype", str(params["up_axis"]), _SWEEP_UPTYPE)
    # end caps + output type + uvs
    if "end_cap" in params:
        _menu_set(n, "endcaptype", str(params["end_cap"]), _SWEEP_ENDCAP)
    if "output_type" in params:
        _menu_set(n, "primtype", str(params["output_type"]), _SWEEP_PRIMTYPE)
    if params.get("compute_uvs"):
        _try_set(n, "computeuvs", True)
    g = n.geometry()
    return advise({"node": n.path(), "shape": shape,
                   "points": len(g.points()), "prims": len(g.prims())}, n)


_DEFORM_TYPES = ("bend", "twist", "mountain", "attribnoise", "lattice", "peak")


@endpoint("deform")
def deform(params):
    """Deformer via `op`: bend | twist | mountain | attribnoise | lattice | peak. Numeric amount /
    frequency are clamped; each op exposes only its own probe-verified parms."""
    op = str(params.get("op", "mountain"))
    if op not in _DEFORM_TYPES:
        raise ValueError("op must be one of " + "|".join(_DEFORM_TYPES))
    n = child_after(params["input"], op, params.get("name"))
    amt = params.get("amount")
    freq = params.get("frequency")
    if op == "bend":
        if amt is not None:
            _try_set(n, "bend", clamp(float(amt), -3600.0, 3600.0))
    elif op == "twist":
        if amt is not None:
            _try_set(n, "strength", clamp(float(amt), -3600.0, 3600.0))
    elif op == "mountain":
        if amt is not None:
            _try_set(n, "height", clamp(float(amt), -1e6, 1e6))
        if freq is not None:
            _try_set(n, "elementsize", clamp(float(freq), 1e-4, 1e6))
    elif op == "attribnoise":
        if amt is not None:
            _try_set(n, "amplitude", clamp(float(amt), -1e6, 1e6))
        if freq is not None:
            _try_set(n, "elementsize", clamp(float(freq), 1e-4, 1e6))
    elif op == "lattice":
        for pn in ("divsx", "divsy", "divsz"):
            if pn in params:
                _try_set(n, pn, int(clamp(int(params[pn]), 2, 100)))
    elif op == "peak":
        if amt is not None:
            _try_set(n, "dist", clamp(float(amt), -1e6, 1e6))
    g = n.geometry()
    return {"node": n.path(), "op": op, "points": len(g.points())}


_DRAPE_DIRS = {
    "down": (0.0, -1.0, 0.0), "up": (0.0, 1.0, 0.0),
    "north": (0.0, 0.0, -1.0), "south": (0.0, 0.0, 1.0),
    "east": (1.0, 0.0, 0.0), "west": (-1.0, 0.0, 0.0),
}


@endpoint("drape")
def drape(params):
    """Drape the input geometry onto a collision surface. mode: ray (default) or project.
    For ray, `collision` (input1) is the surface and `direction` is the cast direction."""
    mode = str(params.get("mode", "ray"))
    if mode == "ray":
        n = child_after(params["input"], "ray", params.get("name"))
        if params.get("collision"):
            bridge_input(n, params["collision"], index=1, name_hint="collision")
        d = _DRAPE_DIRS.get(str(params.get("direction", "down")), (0.0, -1.0, 0.0))
        _try_set(n, "dirmethod", 1)  # cast along a fixed direction vector
        _try_set(n, "dirx", d[0])
        _try_set(n, "diry", d[1])
        _try_set(n, "dirz", d[2])
        if "distance" in params:
            _try_set(n, "scale", clamp(float(params["distance"]), 0.0, 1e6))
    elif mode == "project":
        n = child_after(params["input"], "project", params.get("name"))
        if params.get("collision"):
            bridge_input(n, params["collision"], index=1, name_hint="collision")
    else:
        raise ValueError("mode must be ray|project")
    g = n.geometry()
    return {"node": n.path(), "mode": mode, "points": len(g.points())}


# xform SOP menu tokens (live-probed H21.0.671, ordered menus = index-set).
_XFORM_GROUPTYPE = ("guess", "breakpoints", "edges", "points", "prims")
_XFORM_XORD = ("srt", "str", "rst", "rts", "tsr", "trs")            # transform order
_XFORM_RORD = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")            # rotate order


@endpoint("transform")
def transform(params):
    """Transform SOP (xform). tx/ty/tz translate, rx/ry/rz rotate (deg), scale = uniform scale.

    EXTEND (all optional, back-compat preserved): per-axis scale `s`=[sx,sy,sz]; pivot `p`=[px,py,pz]
    and pivot-rotate `pr`=[prx,pry,prz]; `group` + `grouptype` (guess|breakpoints|edges|points|prims)
    to transform only a named group; transform order `xOrd` (srt|str|rst|rts|tsr|trs) and rotate order
    `rOrd` (xyz|xzy|yxz|yzx|zxy|zyx)."""
    n = child_after(params["input"], "xform", params.get("name"))
    # group restriction (transform only part of the geometry)
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if "grouptype" in params:
        _menu_set(n, "grouptype", str(params["grouptype"]), _XFORM_GROUPTYPE)
    # transform / rotate order menus
    if "xOrd" in params:
        _menu_set(n, "xOrd", str(params["xOrd"]), _XFORM_XORD)
    if "rOrd" in params:
        _menu_set(n, "rOrd", str(params["rOrd"]), _XFORM_RORD)
    for k in ("tx", "ty", "tz"):
        if k in params:
            n.parm(k).set(clamp(float(params[k]), -1e9, 1e9))
    for k in ("rx", "ry", "rz"):
        if k in params:
            n.parm(k).set(clamp(float(params[k]), -36000.0, 36000.0))
    if "scale" in params:
        n.parm("scale").set(clamp(float(params["scale"]), 1e-6, 1e6))
    # per-axis scale s=[sx,sy,sz]
    s = params.get("s")
    if s and len(s) == 3:
        for pn, v in zip(("sx", "sy", "sz"), s):
            _try_set(n, pn, clamp(float(v), 1e-6, 1e6))
    # pivot p=[px,py,pz]
    p = params.get("p")
    if p and len(p) == 3:
        for pn, v in zip(("px", "py", "pz"), p):
            _try_set(n, pn, clamp(float(v), -1e9, 1e9))
    # pivot-rotate pr=[prx,pry,prz]
    pr = params.get("pr")
    if pr and len(pr) == 3:
        for pn, v in zip(("prx", "pry", "prz"), pr):
            _try_set(n, pn, clamp(float(v), -36000.0, 36000.0))
    n.geometry()
    return {"node": n.path()}


@endpoint("select_group")
def select_group(params):
    """Bounded selection then delete-inverse. bbox=[minx,miny,minz,maxx,maxy,maxz] keeps geometry
    inside the box; else `pattern` selects a named group. `keep` (default True) keeps the selection.
    """
    src = resolve_node(params["input"])
    parent = src.parent()
    keep = bool(params.get("keep", True))
    bbox = params.get("bbox")
    if bbox and len(bbox) == 6:
        gc = parent.createNode("groupcreate", params.get("name"))
        gc.setFirstInput(src)
        gc.parm("groupname").set("sel")
        _try_set(gc, "groupbounding", True)
        _try_set(gc, "boundtype", 0)  # bounding box
        cx = (float(bbox[0]) + float(bbox[3])) / 2.0
        cy = (float(bbox[1]) + float(bbox[4])) / 2.0
        cz = (float(bbox[2]) + float(bbox[5])) / 2.0
        sx = abs(float(bbox[3]) - float(bbox[0]))
        sy = abs(float(bbox[4]) - float(bbox[1]))
        sz = abs(float(bbox[5]) - float(bbox[2]))
        _try_set(gc, "sizex", sx)
        _try_set(gc, "sizey", sy)
        _try_set(gc, "sizez", sz)
        _try_set(gc, "tx", cx)
        _try_set(gc, "ty", cy)
        _try_set(gc, "tz", cz)
        bl = parent.createNode("blast", (params.get("name") or "sel") + "_blast")
        bl.setFirstInput(gc)
        bl.parm("group").set("sel")
        bl.parm("negate").set(keep)  # negate => keep the group
        bl.moveToGoodPosition()
        g = bl.geometry()
        return {"node": bl.path(), "group": "sel", "prims": len(g.prims())}
    pattern = str(params.get("pattern", ""))
    bl = parent.createNode("blast", params.get("name"))
    bl.setFirstInput(src)
    bl.parm("group").set(pattern)
    bl.parm("negate").set(keep)
    bl.moveToGoodPosition()
    g = bl.geometry()
    return {"node": bl.path(), "pattern": pattern, "prims": len(g.prims())}


_GROUP_TYPES = ("primitive", "point", "edge", "vertex")


_GROUP_MERGEOP = ("replace", "union", "intersect", "subtract")


@endpoint("group_create")
def group_create(params):
    """Create a NAMED, persistent group on `input` (unlike select_group's blunt delete-inverse),
    for later targeted ops. group_type: primitive|point|edge|vertex. Optional selectors, combinable:
    base_group (a source group/pattern), bbox=[minx,miny,minz,maxx,maxy,maxz] (bounding box),
    normal_axis=[x,y,z] + normal_angle (deg, by-normal). EDGE-ANGLE (the crease-seam idiom, forces
    edge type): edge_angle_min / edge_angle_max (deg between adjacent faces — e.g. min 55 max 180
    selects only sharp structural seams for creasing) and unshared_edges=true (boundary/open edges,
    the loop-selection idiom for bridge/polyfill). merge_op combines with the base group
    (replace|union|intersect|subtract). With no selector, an empty named group."""
    gtype = str(params.get("group_type", "point"))
    if gtype not in _GROUP_TYPES:
        raise ValueError("group_type must be one of " + "|".join(_GROUP_TYPES))
    gname = str(params.get("group_name", "group1"))
    n = child_after(params["input"], "groupcreate", params.get("name"))
    n.parm("groupname").set(gname)
    # Edge-angle / unshared selectors are edge-only — force edge type when they're requested.
    _edge_sel = ("edge_angle_min" in params or "edge_angle_max" in params
                 or bool(params.get("unshared_edges")))
    if _edge_sel:
        gtype = "edge"
    n.parm("grouptype").set(_GROUP_TYPES.index(gtype))  # menu index (primitive|point|edge|vertex)
    if _edge_sel:
        _try_set(n, "groupedges", True)
        if "edge_angle_min" in params:
            _try_set(n, "dominedgeangle", True)
            _try_set(n, "minedgeangle", clamp(float(params["edge_angle_min"]), 0.0, 180.0))
        if "edge_angle_max" in params:
            _try_set(n, "domaxedgeangle", True)
            _try_set(n, "maxedgeangle", clamp(float(params["edge_angle_max"]), 0.0, 180.0))
        if params.get("unshared_edges"):
            _try_set(n, "unshared", True)
    if "merge_op" in params:
        _menu_set(n, "mergeop", str(params["merge_op"]), _GROUP_MERGEOP)
    base = params.get("base_group")
    if base:
        _try_set(n, "groupbase", True)
        _try_set(n, "basegroup", str(base))
    bbox = params.get("bbox")
    if bbox and len(bbox) == 6:
        b = [float(x) for x in bbox]
        _try_set(n, "groupbounding", True)
        _try_set(n, "boundtype", 0)  # usebbox
        for pn, v in (("sizex", abs(b[3] - b[0])), ("sizey", abs(b[4] - b[1])),
                      ("sizez", abs(b[5] - b[2])),
                      ("tx", (b[0] + b[3]) / 2.0), ("ty", (b[1] + b[4]) / 2.0),
                      ("tz", (b[2] + b[5]) / 2.0)):
            _try_set(n, pn, v)
    naxis = params.get("normal_axis")
    if naxis and len(naxis) == 3:
        _try_set(n, "groupnormal", True)
        for pn, v in zip(("dirx", "diry", "dirz"), naxis):
            _try_set(n, pn, float(v))
        if "normal_angle" in params:
            _try_set(n, "angle", clamp(float(params["normal_angle"]), 0.0, 180.0))
    g = n.geometry()
    cnt = None
    try:
        if gtype == "point":
            grp = g.findPointGroup(gname); cnt = len(grp.points()) if grp else 0
        elif gtype == "primitive":
            grp = g.findPrimGroup(gname); cnt = len(grp.prims()) if grp else 0
    except Exception:
        cnt = None
    return {"node": n.path(), "group_name": gname, "group_type": gtype, "count": cnt}


_BLAST_TYPES = ("guess", "breakpoints", "edges", "points", "prims")


@endpoint("blast")
def blast(params):
    """Delete geometry by group -- the fundamental targeted-delete primitive. group = group
    name/pattern; group_type guides interpretation (guess|breakpoints|edges|points|prims).
    delete_non_selected=True keeps ONLY the group (deletes everything else). fill_hole caps
    the holes left by deleted prims; remove_group drops the group afterward."""
    n = child_after(params["input"], "blast", params.get("name"))
    n.parm("group").set(str(params.get("group", "")))
    gt = str(params.get("group_type", "guess"))
    if gt in _BLAST_TYPES:
        n.parm("grouptype").set(_BLAST_TYPES.index(gt))
    _try_set(n, "negate", bool(params.get("delete_non_selected", False)))
    _try_set(n, "fillhole", bool(params.get("fill_hole", False)))
    _try_set(n, "removegrp", bool(params.get("remove_group", False)))
    g = n.geometry()
    return {"node": n.path(), "group": str(params.get("group", "")),
            "points": len(g.points()), "prims": len(g.prims())}


@endpoint("attribute_transfer")
def attribute_transfer(params):
    """Transfer point/prim attributes from a `source` SOP (input1) onto `input` (input0) by
    proximity -- the LIDAR-color / GIS-attribute workhorse. point_attribs / prim_attribs are
    space-separated attribute-name patterns (e.g. "Cd N"). distance = search radius."""
    n = child_after(params["input"], "attribtransfer", params.get("name"))
    if params.get("source"):
        bridge_input(n, params["source"], index=1, name_hint="source")
    pa = params.get("point_attribs")
    if pa:
        _try_set(n, "pointattribs", True)
        _try_set(n, "pointattriblist", str(pa))
    ra = params.get("prim_attribs")
    if ra:
        _try_set(n, "primitiveattribs", True)
        _try_set(n, "primattriblist", str(ra))
    if "distance" in params:
        _try_set(n, "kernelradius", clamp(float(params["distance"]), 0.0, 1e9))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


@endpoint("merge")
def merge(params):
    """Merge several SOPs into one stream. inputs = list of SOP paths."""
    inputs = params.get("inputs") or []
    if isinstance(inputs, str):
        # The catalog has no list Kind, so `inputs` arrives as a string -- accept either a
        # JSON array or a comma-separated list of SOP paths (iterating the raw string would
        # walk it character-by-character).
        s = inputs.strip()
        try:
            parsed = json.loads(s)
            inputs = parsed if isinstance(parsed, list) else [str(parsed)]
        except Exception:
            inputs = [p.strip() for p in s.split(",") if p.strip()]
    if not inputs:
        raise ValueError("merge needs a non-empty 'inputs' list of SOP paths")
    nodes = [resolve_node(p) for p in inputs]
    parent = nodes[0].parent()
    m = parent.createNode("merge", params.get("name"))
    for i, nd in enumerate(nodes):
        # setInput cannot cross /obj networks: bridge any foreign input in with an object_merge
        # (xformtype="Into This Object" -> world-correct placement for scene assembly).
        m.setInput(i, bridge_into(nd, parent, xformtype=1, name_hint=nd.name()))
    m.moveToGoodPosition()
    g = m.geometry()
    return {"node": m.path(), "merged": len(nodes), "prims": len(g.prims())}


@endpoint("set_color")
def set_color(params):
    """Assign a constant color. class: point|prim. color = [r,g,b] in 0..1."""
    n = child_after(params["input"], "color", params.get("name"))
    cls = str(params.get("class", "point"))
    _try_set(n, "class", {"point": 0, "prim": 1, "vertex": 2, "detail": 3}.get(cls, 0))
    c = params.get("color")
    if c and len(c) == 3:
        n.parm("colorr").set(clamp(float(c[0]), 0.0, 1.0))
        n.parm("colorg").set(clamp(float(c[1]), 0.0, 1.0))
        n.parm("colorb").set(clamp(float(c[2]), 0.0, 1.0))
    n.geometry()
    return {"node": n.path(), "class": cls}


# uvlayout::3.0 menus (live-probed): axisalignislands + resolution are ordered menus (index-set).
_UVLAYOUT_AXISALIGN = ("none", "intrinsic", "extrinsic")
_UVLAYOUT_RES = ("res1", "res2", "res3", "res4", "res5", "custom")  # 256/512/1024/2048/4096/custom


@endpoint("uv")
def uv(params):
    """UV via `mode`:
      project (default, uvproject): planar projection; `scale` sets sx/sy/sz.
      unwrap (uvunwrap): auto-unwrap; `scale` (menu no-op guard) kept for back-compat.
      layout (uvlayout::3.0): pack UV islands into one atlas (bake / single-material prep).
        `correctareas` (bool), `axisalign` (none|intrinsic|extrinsic), `scale` (0..2 island scale),
        `padding` (0..20 texel), `iterations` (1..100), `resolution` (res1|res2|res3|res4|res5|custom
        = 256|512|1024|2048|4096|custom) + `customresolution` (128..32768 when resolution=custom).
      transform (uvtransform): scale/rotate/translate an existing UV set. `t`/`r`/`s`=[x,y,z] on the
        UV attrib, `uvattrib` (default 'uv'), `group`."""
    mode = str(params.get("mode", "project"))
    if mode == "project":
        n = child_after(params["input"], "uvproject", params.get("name"))
        if "scale" in params:
            s = clamp(float(params["scale"]), 1e-4, 1e6)
            for pn in ("sx", "sy", "sz"):
                _try_set(n, pn, s)
    elif mode == "unwrap":
        n = child_after(params["input"], "uvunwrap", params.get("name"))
        if "scale" in params:
            _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e6))
    elif mode == "layout":
        n = child_after(params["input"], "uvlayout::3.0", params.get("name"))
        if "correctareas" in params:
            _try_set(n, "correctareas", bool(params["correctareas"]))
        if "axisalign" in params:
            _menu_set(n, "axisalignislands", str(params["axisalign"]), _UVLAYOUT_AXISALIGN)
        if "scale" in params:
            _try_set(n, "scale", clamp(float(params["scale"]), 0.0, 2.0))
        if "padding" in params:
            _try_set(n, "padding", int(clamp(int(params["padding"]), 0, 20)))
        if "iterations" in params:
            _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 100)))
        if "resolution" in params:
            _menu_set(n, "resolution", str(params["resolution"]), _UVLAYOUT_RES)
        if "customresolution" in params:
            _try_set(n, "customresolution", int(clamp(int(params["customresolution"]), 128, 32768)))
    elif mode == "transform":
        n = child_after(params["input"], "uvtransform", params.get("name"))
        if params.get("group"):
            _try_set(n, "group", str(params["group"]))
        if params.get("uvattrib"):
            _try_set(n, "uvattrib", str(params["uvattrib"]))
        for key, comps in (("t", ("tx", "ty", "tz")), ("r", ("rx", "ry", "rz")),
                           ("s", ("sx", "sy", "sz"))):
            v = params.get(key)
            if v and len(v) == 3:
                for pn, val in zip(comps, v):
                    _try_set(n, pn, clamp(float(val), -1e6, 1e6))
    elif mode == "flatten":
        # seam-DRIVEN flatten: unlike unwrap (auto-only), uvflatten::3.0 takes an explicit seam edge
        # group so YOU control where the UVs cut (the pro path for clean scan/asset layouts).
        n = child_after(params["input"], "uvflatten::3.0", params.get("name"))
        if params.get("seam_group"):
            _try_set(n, "seamgroup", str(params["seam_group"]))
        if "pin_boundaries" in params:
            _try_set(n, "pinboundaries", bool(params["pin_boundaries"]))
        if "use_pins" in params:
            _try_set(n, "usepins", bool(params["use_pins"]))
    else:
        raise ValueError("mode must be project|unwrap|layout|transform|flatten")
    n.geometry()
    return {"node": n.path(), "mode": mode}


@endpoint("uv_transfer")
def uv_transfer(params):
    """Transfer a UV set from a SOURCE mesh onto the input geometry — restore UVs a topology change
    (remesh/quad_remesh/polyreduce) destroyed. Input 0 = the geo needing UVs; `source` = the original
    UV'd mesh (wired to input 1). Prefers SideFX Labs UV Transfer (labs::uv_transfer::1.1 — border
    fuse + material transfer) and FALLS BACK to the native attribtransfer (transfers the `uv`
    point/vertex attribute by proximity) when Labs is not installed — so it never hard-depends on
    Labs. Chains after `input`. BUILT."""
    uv_attr = str(params.get("uv_attribute", "uv"))
    try:
        n = child_after(params["input"], "labs::uv_transfer::1.1", params.get("name"))
        backend = "labs"
    except Exception:
        n = child_after(params["input"], "attribtransfer", params.get("name"))
        backend = "native"
    src = resolve_node(params["source"])
    n.setInput(1, bridge_into(src, n.parent(), xformtype=0, name_hint="uv_src"))
    applied = {}
    if backend == "labs":
        applied["uv_attribute"] = _try_set(n, "uvattribute", uv_attr)
        if "border_tolerance" in params:
            applied["border_tolerance"] = _try_set(n, "borderfusetolerance", clamp(float(params["border_tolerance"]), 0.0, 1e4))
        if "transfer_material" in params:
            applied["transfer_material"] = _try_set(n, "transfermaterial", bool(params["transfer_material"]))
    else:
        # native attribtransfer: move ONLY the uv attribute (point + vertex classes), by proximity.
        _try_set(n, "primitiveattribs", 0)
        _try_set(n, "pointattribs", 1)
        _try_set(n, "pointattriblist", uv_attr)
        _try_set(n, "vertexattribs", 1)
        applied["uv_attribute"] = _try_set(n, "vertexattriblist", uv_attr)
        if "distance" in params:
            _try_set(n, "threshold", 1)
            applied["distance"] = _try_set(n, "thresholddist", clamp(float(params["distance"]), 0.0, 1e6))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    n.parent().layoutChildren()
    return {"node": n.path(), "backend": backend, "applied": applied}


_PRIMS = ("box", "grid", "sphere", "tube", "line", "circle", "platonic", "torus")
# platonic solids: name -> the platonic SOP's ordered `type` index (H21.0.671 order, probe-verified).
_PLATONIC = ("tetrahedron", "cube", "octahedron", "icosahedron", "dodecahedron", "soccerball", "teapot")


@endpoint("create_primitive")
def create_primitive(params):
    """Create a fresh /obj geo containing a primitive SOP. type: box|grid|sphere|tube|line|circle|
    platonic|torus. For platonic, `solid` picks the solid (tetrahedron..teapot); for torus, `radius`=
    major and `minor_radius`=minor (rows/cols set resolution). Creator: FAILS on name collision (never
    destroys existing user work)."""
    ptype = str(params.get("type", "box"))
    if ptype not in _PRIMS:
        raise ValueError("type must be one of " + "|".join(_PRIMS))
    name = params["name"]
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    geo = obj.createNode("geo", name)
    sop = geo.createNode(ptype)
    # ANALYTIC-VS-POLY TRAP (consumer-review P0): sphere/tube/circle default to a single ANALYTIC
    # primitive (1 prim / 1 pt) with no polygon topology, so downstream boolean/remesh/scatter/
    # displace silently misbehave. Default them to real polygons (`as_polygons`, default True); pass
    # as_polygons=false to keep the analytic primitive. box/grid/torus/platonic are already polygonal.
    if ptype in ("sphere", "tube", "circle") and params.get("as_polygons", True):
        _try_set(sop, "type", "poly")
    size = params.get("size")
    if ptype == "box" and size and len(size) == 3:
        for pn, v in zip(("sizex", "sizey", "sizez"), size):
            _try_set(sop, pn, clamp(float(v), 1e-6, 1e9))
    elif ptype == "grid":
        if size and len(size) == 2:
            _try_set(sop, "sizex", clamp(float(size[0]), 1e-6, 1e9))
            _try_set(sop, "sizey", clamp(float(size[1]), 1e-6, 1e9))
        if "rows" in params:
            _try_set(sop, "rows", int(clamp(int(params["rows"]), 2, 10000)))
        if "cols" in params:
            _try_set(sop, "cols", int(clamp(int(params["cols"]), 2, 10000)))
    elif ptype == "sphere":
        r = params.get("radius", 1.0)
        for pn in ("radx", "rady", "radz"):
            _try_set(sop, pn, clamp(float(r), 1e-6, 1e9))
    elif ptype == "tube":
        if "radius" in params:
            _try_set(sop, "rad1", clamp(float(params["radius"]), 1e-6, 1e9))
            _try_set(sop, "rad2", clamp(float(params["radius"]), 1e-6, 1e9))
        if "height" in params:
            _try_set(sop, "height", clamp(float(params["height"]), 1e-6, 1e9))
    elif ptype == "line":
        if "points" in params:
            _try_set(sop, "points", int(clamp(int(params["points"]), 2, 100000)))
    elif ptype == "circle":
        r = params.get("radius", 1.0)
        _try_set(sop, "radx", clamp(float(r), 1e-6, 1e9))
        _try_set(sop, "rady", clamp(float(r), 1e-6, 1e9))
    elif ptype == "platonic":
        solid = str(params.get("solid", "icosahedron"))
        if solid in _PLATONIC:
            _try_set(sop, "type", _PLATONIC.index(solid))  # ordered menu — set by index
        if "radius" in params:
            _try_set(sop, "radius", clamp(float(params["radius"]), 1e-6, 1e9))
    elif ptype == "torus":
        major = clamp(float(params.get("radius", 1.0)), 1e-6, 1e9)
        minor = clamp(float(params.get("minor_radius", 0.5)), 1e-6, 1e9)
        try:
            sop.parmTuple("rad").set((major, minor))   # rad = (major, minor)
        except Exception:  # noqa: BLE001
            pass
        if "rows" in params:
            _try_set(sop, "rows", int(clamp(int(params["rows"]), 3, 10000)))
        if "cols" in params:
            _try_set(sop, "cols", int(clamp(int(params["cols"]), 3, 10000)))
    sop.setDisplayFlag(True)
    sop.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = sop.geometry()
    return {"node": geo.path(), "sop": sop.path(), "type": ptype,
            "points": len(g.points()), "prims": len(g.prims())}


_CURVE_TYPES = ("polyline", "nurbs", "bezier")

# FIXED server-authored template (mirrors import_heightfield): the ONLY thing interpolated is the
# json-dumped numeric coordinate list — never any caller string. curve_type / closed / order are
# passed as node userData (data, not code) and read back inside the SOP. Coords are re-parsed with
# json.loads, so nothing here is exec/eval of caller input.
_CURVE_TEMPLATE = '''
import json, hou
node = hou.pwd(); geo = node.geometry()
geo.clear()
PTS = json.loads(%r)
ctype = node.userData("curve_type") or "polyline"
closed = node.userData("closed") == "1"
try:
    order = int(node.userData("order") or "4")
except Exception:
    order = 4
n = len(PTS)
if n >= 2 and ctype in ("nurbs", "bezier"):
    o = max(2, min(order, n))
    if ctype == "nurbs":
        face = geo.createNURBSCurve(n, closed, o)
    else:
        face = geo.createBezierCurve(n, closed, o)
    for vtx, xyz in zip(face.vertices(), PTS):
        vtx.point().setPosition(hou.Vector3(float(xyz[0]), float(xyz[1]), float(xyz[2])))
else:
    pts = [geo.createPoint() for _ in PTS]
    for p, xyz in zip(pts, PTS):
        p.setPosition(hou.Vector3(float(xyz[0]), float(xyz[1]), float(xyz[2])))
    if n >= 2:
        poly = geo.createPolygon()
        poly.setIsClosed(closed)
        for p in pts:
            poly.addVertex(p)
'''


@endpoint("create_curve")
def create_curve(params):
    """Create a fresh /obj geo holding a curve built from caller-supplied points.
    curve_type: polyline|nurbs|bezier. closed: bool. order: 2..11 (nurbs/bezier).
    Creator: FAILS on name collision (never destroys existing user work).
    Data-only: `points` is a JSON array of [x,y,z] numeric triples, validated here; a fixed
    server-authored python SOP builds the curve, interpolating ONLY the json-dumped coords."""
    name = params["name"]
    ctype = str(params.get("curve_type", "polyline"))
    if ctype not in _CURVE_TYPES:
        raise ValueError("curve_type must be one of " + "|".join(_CURVE_TYPES))

    # Parse + validate the points JSON: a list of at least two [x,y,z] numeric triples.
    raw = params["points"]
    try:
        pts = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        raise ValueError("points must be a JSON array of [x,y,z] triples: %s" % e)
    if not isinstance(pts, list) or len(pts) < 2:
        raise ValueError("points must be a JSON array of at least 2 [x,y,z] triples")
    clean = []
    for i, pt in enumerate(pts):
        if not isinstance(pt, (list, tuple)) or len(pt) != 3:
            raise ValueError("point %d must be an array of 3 numbers [x,y,z]" % i)
        for c in pt:
            if isinstance(c, bool) or not isinstance(c, (int, float)):
                raise ValueError("point %d coords must be numbers" % i)
        clean.append([float(pt[0]), float(pt[1]), float(pt[2])])

    closed = bool(params.get("closed", False))
    order = int(clamp(int(params.get("order", 4)), 2, 11))

    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    geo = obj.createNode("geo", name)
    sop = geo.createNode("python", "build_curve")
    sop.setUserData("curve_type", ctype)
    sop.setUserData("closed", "1" if closed else "0")
    sop.setUserData("order", str(order))
    sop.parm("python").set(_CURVE_TEMPLATE % json.dumps(clean))
    sop.setDisplayFlag(True)
    sop.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    return {"node": geo.path(), "sop": sop.path(), "points": len(clean),
            "closed": closed, "curve_type": ctype}


# ── SOP utilities (curve resample / motion trail / time sample / tangent frames) ──────────────
# Menu tokens below are the EXACT live-probed ordered-menu items for H21.0.671 (index-set).

_RESAMPLE_METHOD = ("dist", "x", "y", "z")
_RESAMPLE_MEASURE = ("arc", "chord")
_RESAMPLE_TREATAS = ("straight", "subd", "interp")


@endpoint("resample")
def resample(params):
    """Resample curves/polylines to even segments (resample SOP). Length mode sets a max segment
    `length`; segment mode sets a max segment count `segments` (either enables its own toggle).
    method: dist|x|y|z (even length / even X|Y|Z). measure: arc|chord. treat_polys_as:
    straight|subd|interp. Optional group; lod, edge (resample by polygon edge), only_points,
    maintain_last, even_last_equal, create_tangent (tangentu), create_curveu."""
    n = child_after(params["input"], "resample", params.get("name"))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    _menu_set(n, "method", str(params.get("method", "dist")), _RESAMPLE_METHOD)
    _menu_set(n, "measure", str(params.get("measure", "arc")), _RESAMPLE_MEASURE)
    _menu_set(n, "treatpolysas", str(params.get("treat_polys_as", "straight")), _RESAMPLE_TREATAS)
    if "length" in params:
        _try_set(n, "dolength", True)
        _try_set(n, "length", clamp(float(params["length"]), 0.0, 1e9))
    if "segments" in params:
        _try_set(n, "dosegs", True)
        _try_set(n, "segs", int(clamp(int(params["segments"]), 1, 10_000_000)))
    if "lod" in params:
        _try_set(n, "lod", clamp(float(params["lod"]), 0.001, 1e6))
    if "edge" in params:
        _try_set(n, "edge", bool(params["edge"]))
    if "only_points" in params:
        _try_set(n, "onlypoints", bool(params["only_points"]))
    if "maintain_last" in params:
        _try_set(n, "last", bool(params["maintain_last"]))
    if "even_last_equal" in params:
        _try_set(n, "allequal", bool(params["even_last_equal"]))
    if params.get("create_tangent"):
        _try_set(n, "dotangentattr", True)
    if params.get("create_curveu"):
        _try_set(n, "docurveuattr", True)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


_TRAIL_RESULT = ("preserve", "mesh", "poly", "velocity")
_TRAIL_CONNECT = ("rows", "cols", "rowcol", "triangles", "quads", "alttriangles", "revtriangles")
_TRAIL_VELAPPROX = ("Backward Difference", "Central Difference", "Forward Difference")


@endpoint("trail")
def trail(params):
    """Motion trail / connectivity over time (trail SOP). result: preserve|mesh|poly|velocity
    (Preserve Original | Connect as Mesh | Connect as Polygons | Compute Velocity). length =
    trail length (frames), increment (frame step), cache size. For mesh/poly: connectivity
    (rows|cols|rowcol|triangles|quads|alttriangles|revtriangles) + close_rows. For velocity:
    velocity_scale, velocity_approximation (Backward|Central|Forward Difference), compute_accel,
    compute_angular. eval_frame_range; match_by_attribute + attribute_to_match."""
    n = child_after(params["input"], "trail", params.get("name"))
    _menu_set(n, "result", str(params.get("result", "preserve")), _TRAIL_RESULT)
    if "length" in params:
        _try_set(n, "length", int(clamp(int(params["length"]), 1, 100000)))
    if "increment" in params:
        _try_set(n, "inc", clamp(float(params["increment"]), 0.0, 1e6))
    if "cache" in params:
        _try_set(n, "cache", int(clamp(int(params["cache"]), 1, 100000)))
    if "connectivity" in params:
        _menu_set(n, "surftype", str(params["connectivity"]), _TRAIL_CONNECT)
    if "close_rows" in params:
        _try_set(n, "close", bool(params["close_rows"]))
    if "velocity_scale" in params:
        _try_set(n, "velscale", clamp(float(params["velocity_scale"]), -1e6, 1e6))
    if "velocity_approximation" in params:
        _menu_set(n, "velapproximation", str(params["velocity_approximation"]), _TRAIL_VELAPPROX)
    if "compute_accel" in params:
        _try_set(n, "computeaccel", bool(params["compute_accel"]))
    if "compute_angular" in params:
        _try_set(n, "computeangular", bool(params["compute_angular"]))
    if "eval_frame_range" in params:
        _try_set(n, "evalframe", bool(params["eval_frame_range"]))
    if params.get("match_by_attribute"):
        _try_set(n, "matchbyattribute", True)
        if params.get("attribute_to_match"):
            _try_set(n, "attributetomatch", str(params["attribute_to_match"]))
    g = n.geometry()
    return {"node": n.path(), "result": str(params.get("result", "preserve")),
            "points": len(g.points()), "prims": len(g.prims())}


_TIMESHIFT_METHOD = ("byframe", "bytime")
_TIMESHIFT_CLAMP = ("none", "first", "last", "both")


@endpoint("timeshift")
def timeshift(params):
    """Sample the input geometry at a different frame/time (timeshift SOP). method: byframe|bytime.
    For byframe: `frame` (+ integer_frames toggle). For bytime: `time` (seconds). clamp:
    none|first|last|both (clamp the sampled frame/time to a range)."""
    n = child_after(params["input"], "timeshift", params.get("name"))
    method = str(params.get("method", "byframe"))
    _menu_set(n, "method", method, _TIMESHIFT_METHOD)
    # timeshift's frame/time parms SHIP with `$F`/`$T` channel expressions; a plain .set() leaves
    # the expression in place (it wins on eval), so clear it first to pin a literal frame/time.
    if "frame" in params:
        _set_literal(n, "frame", clamp(float(params["frame"]), -1e7, 1e7))
    if "time" in params:
        _set_literal(n, "time", clamp(float(params["time"]), -1e7, 1e7))
    if "integer_frames" in params:
        _try_set(n, "integerframe", bool(params["integer_frames"]))
    if "clamp" in params:
        _menu_set(n, "rangeclamp", str(params["clamp"]), _TIMESHIFT_CLAMP)
    g = n.geometry()
    return {"node": n.path(), "method": method,
            "points": len(g.points()), "prims": len(g.prims())}


_POLYFRAME_ENTITY = ("primitive", "point")
# `style` is a STRING-menu parm: the token itself is stored (set directly, NOT by index).
_POLYFRAME_STYLE = ("edge1", "edge2", "primC", "texuv", "tex", "attrib", "mikkt")


@endpoint("polyframe")
def polyframe(params):
    """Build a tangent/normal/bitangent frame as point/prim attributes (polyframe SOP). entity:
    primitive|point. style: edge1|edge2|primC|texuv|tex|attrib|mikkt (First Edge | Two Edges |
    Primitive Centroid | Texture UV | Texture UV Gradient | Attribute Gradient | MikkT). Toggle +
    name each output: normal (N), tangent (tangentu), bitangent (tangentv). orthogonal makes the
    frame orthonormal; left_handed flips handedness. attrib_name feeds style=attrib. Optional group."""
    n = child_after(params["input"], "polyframe", params.get("name"))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    _menu_set(n, "entity", str(params.get("entity", "primitive")), _POLYFRAME_ENTITY)
    style = str(params.get("style", "edge2"))
    if style in _POLYFRAME_STYLE:
        _try_set(n, "style", style)  # string-menu: set the token, not an index
    if params.get("attrib_name"):
        _try_set(n, "attribname", str(params["attrib_name"]))
    if "enable_normal" in params:
        _try_set(n, "Non", bool(params["enable_normal"]))
    if params.get("normal_name"):
        _try_set(n, "N", str(params["normal_name"]))
    if "enable_tangent" in params:
        _try_set(n, "tangentuon", bool(params["enable_tangent"]))
    if params.get("tangent_name"):
        _try_set(n, "tangentu", str(params["tangent_name"]))
    if "enable_bitangent" in params:
        _try_set(n, "tangentvon", bool(params["enable_bitangent"]))
    if params.get("bitangent_name"):
        _try_set(n, "tangentv", str(params["bitangent_name"]))
    if "orthogonal" in params:
        _try_set(n, "ortho", bool(params["orthogonal"]))
    if "left_handed" in params:
        _try_set(n, "lefthanded", bool(params["left_handed"]))
    g = n.geometry()
    return {"node": n.path(), "entity": str(params.get("entity", "primitive")), "style": style,
            "points": len(g.points()), "prims": len(g.prims())}


# ── skin (loft a surface across ordered profile curves) ──────────────────────────────────────────────
# Verified sweep-sibling (H21.0.671): node `skin`, ONE merged input holding N profile primitives; lofts
# across them in prim order. surftype=quads default; polys=False -> spline Mesh surface. Data-only.
_SKIN_SURFTYPE = ("rows", "cols", "rowcol", "triangles", "quads", "alttriangles", "revtriangles")
_SKIN_VWRAP = ("nonewv", "wv", "ifprimwv")
_SKIN_MODE = ("all", "group", "skip")


@endpoint("skin")
def skin(params):
    """Loft/skin a surface across ordered profile curves. `input` = a SOP whose geometry holds several
    profile primitives (merge parallel curves first); skin lofts across them in prim order.
    `connectivity` sets the polygon pattern; `output_polygons`=false yields a spline mesh surface;
    `v_wrap`=wv closes the loft into a loop. Polycount ~= (num_profiles-1) x points_per_profile —
    governor-advised."""
    governor_gate("skin")
    n = child_after(params["input"], "skin", params.get("name"))
    if "connectivity" in params:
        _menu_set(n, "surftype", str(params["connectivity"]), _SKIN_SURFTYPE)
    if "output_polygons" in params:
        _try_set(n, "polys", bool(params["output_polygons"]))
    if "v_wrap" in params:
        _menu_set(n, "closev", str(params["v_wrap"]), _SKIN_VWRAP)
    if params.get("keep_shape"):
        _try_set(n, "keepshape", True)
    if params.get("keep_primitives"):
        _try_set(n, "prim", True)
    if "skin_mode" in params:
        _menu_set(n, "skinops", str(params["skin_mode"]), _SKIN_MODE)
    if "increment" in params:
        _try_set(n, "inc", int(clamp(int(params["increment"]), 1, 100000)))
    if params.get("u_sections"):
        _try_set(n, "uprims", str(params["u_sections"]))
    if params.get("v_sections"):
        _try_set(n, "vprims", str(params["v_sections"]))
    g = n.geometry()
    return advise({"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}, n)


# ── revolve (lathe a profile curve around an axis) ───────────────────────────────────────────────────
# Verified (H21.0.671): node `revolve::2.0`, single input profile; origin+dir = spin axis; divs = sides.
_REV_TYPE = ("closed", "openarc", "closedarc")
_REV_SURFTYPE = ("points", "rows", "cols", "rowcol", "tris", "quads", "alttris", "revtris")
_REV_PRIMTYPE = ("auto", "poly", "mesh", "nurbs", "bezier", "polysoup")


@endpoint("revolve")
def revolve(params):
    """Lathe a profile curve around an axis -> a surface of revolution (vase, tube, bottle, wheel,
    lampshade). `input` = a profile SOP (points offset from the axis). `axis`+`origin` define the spin
    axis (default Y through the origin); `divisions` = sides around; `revolve_type`=openarc|closedarc +
    `angle`=[start,end] make a partial arc; `caps` closes the ends; `output_type` overrides the prim
    type. Polycount ~= (profile_points-1) x divisions — governor-advised."""
    governor_gate("revolve")
    n = child_after(params["input"], "revolve::2.0", params.get("name"))
    o = params.get("origin")
    if isinstance(o, (list, tuple)) and len(o) == 3:
        try:
            n.parmTuple("origin").set(tuple(float(v) for v in o))
        except Exception:  # noqa: BLE001
            pass
    ax = params.get("axis")
    if isinstance(ax, (list, tuple)) and len(ax) == 3:
        try:
            n.parmTuple("dir").set(tuple(float(v) for v in ax))
        except Exception:  # noqa: BLE001
            pass
    if "divisions" in params:
        _try_set(n, "divs", int(clamp(int(params["divisions"]), 3, 512)))
    if "revolve_type" in params:
        _menu_set(n, "type", str(params["revolve_type"]), _REV_TYPE)
    a = params.get("angle")
    if isinstance(a, (list, tuple)) and len(a) == 2:
        try:
            n.parmTuple("angle").set((float(a[0]), float(a[1])))
        except Exception:  # noqa: BLE001
            pass
    if "surface_type" in params:
        _menu_set(n, "surftype", str(params["surface_type"]), _REV_SURFTYPE)
    if "output_type" in params:
        _menu_set(n, "primtype", str(params["output_type"]), _REV_PRIMTYPE)
    if params.get("caps"):
        _try_set(n, "cap", True)
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if "compute_uvs" in params:
        _try_set(n, "computeuvs", bool(params["compute_uvs"]))
    g = n.geometry()
    return advise({"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}, n)


# ── polyexpand2d (offset 2D curves -> ribbons/roads) ─────────────────────────────────────────────────
# Verified (H21.0.671): node `polyexpand2d`, single input 2D curve stream. Data-only: typed scalars/
# enums; local-scale params take an attribute NAME (not code).
_PE2D_OUTPUT = ("curves", "surfaces")
_PE2D_SIDE = ("vertexorder", "simplereach", "altreach", "altreachpermeable")


@endpoint("polyexpand2d")
def polyexpand2d(params):
    """Offset 2D curves into variable-width outlines/ribbons -- roads from OSM curves, panel lines,
    insets. `input` = a 2D curve SOP. `offset` = half-width; `output`=curves|surfaces; `inside`/
    `outside` pick which side(s) to emit; `divisions` = rounded-corner divisions; `width_attrib` names
    a per-point attribute for variable width. Data-only (no code param)."""
    n = child_after(params["input"], "polyexpand2d", params.get("name"))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if "offset" in params:
        _try_set(n, "offset", clamp(float(params["offset"]), 0.0, 1e6))
    if "divisions" in params:
        _try_set(n, "divs", int(clamp(int(params["divisions"]), 0, 1000)))
    _menu_set(n, "output", str(params.get("output", "surfaces")), _PE2D_OUTPUT)
    if "inside" in params:
        _try_set(n, "outputinside", bool(params["inside"]))
    if "outside" in params:
        _try_set(n, "outputoutside", bool(params["outside"]))
    if "side_determination" in params:
        _menu_set(n, "sidedetermination", str(params["side_determination"]), _PE2D_SIDE)
    if "keep_input" in params:
        _try_set(n, "keepinput", bool(params["keep_input"]))
    if params.get("width_attrib"):
        _try_set(n, "uselocaloutsidescale", True)
        _try_set(n, "localoutsidescale", str(params["width_attrib"]))
        _try_set(n, "uselocalinsidescale", True)
        _try_set(n, "localinsidescale", str(params["width_attrib"]))
    g = n.geometry()
    return advise({"node": n.path(), "output": str(params.get("output", "surfaces")),
                   "points": len(g.points()), "prims": len(g.prims())}, n)


# ── lsystem (procedural branching curves/tubes from an inert turtle grammar) ─────────────────────────
# DATA-ONLY VERDICT (probe-verified): premise/rule* are a formal turtle-grammar STRING (F + - [ ] / ...),
# NOT executable code — no python/VEX/expression parm on the node. The ONLY code-adjacent surfaces are
# the file-path params (usefile/rulefile/colorMap/picfile) which we FORCE OFF and never expose, so the
# grammar cannot read arbitrary files. Exposing premise/rules/generations/angle/step/thickness is safe.
_LSYS_TYPE = ("skel", "tube")


@endpoint("lsystem")
def lsystem(params):
    """Create a fresh /obj geo with an L-system (procedural branching curves or swept tubes). `premise`
    = the axiom string; `rules` = a list (or JSON array) of 'A=...' production strings (an inert turtle
    grammar, NOT code); `generations`/`angle`/`step`/`thickness` are typed scalars; `output`=skel|tube.
    Creator: FAILS on name collision. Data-only: the grammar is inert; file-read params are forced off."""
    name = params["name"]
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    geo = obj.createNode("geo", name)
    n = geo.createNode("lsystem")
    _try_set(n, "usefile", False)   # never read rules/images from disk (data-only)
    if params.get("premise"):
        _try_set(n, "premise", str(params["premise"]))
    rules = params.get("rules") or []
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except Exception:  # noqa: BLE001
            rules = [rules]
    if not isinstance(rules, (list, tuple)):
        rules = [str(rules)]
    for i, r in enumerate(rules[:25], start=1):
        _try_set(n, "userule%d" % i, True)
        _try_set(n, "rule%d" % i, str(r))
    if "generations" in params:
        # generations is EXPONENTIAL in polycount (branching rules); cap well below the old 20.
        _try_set(n, "generations", clamp(float(params["generations"]), 0.0, 12.0))
    if "angle" in params:
        _try_set(n, "angleinit", clamp(float(params["angle"]), -360.0, 360.0))
    if "step" in params:
        _try_set(n, "stepinit", clamp(float(params["step"]), 1e-4, 1e6))
    if "thickness" in params:
        _try_set(n, "thickinit", clamp(float(params["thickness"]), 1e-5, 1e6))
    output = str(params.get("output", "skel"))
    _menu_set(n, "type", output, _LSYS_TYPE)
    if output == "tube":
        if "rows" in params:
            _try_set(n, "rows", int(clamp(int(params["rows"]), 2, 1000)))
        if "cols" in params:
            _try_set(n, "cols", int(clamp(int(params["cols"]), 3, 1000)))
    if "seed" in params:
        _try_set(n, "randseed", int(params["seed"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "output": output,
            "points": len(g.points()), "prims": len(g.prims())}


# ── pointdeform (cage-driven wrap deform) ────────────────────────────────────────────────────────────
# THREE inputs (verified): in0 = geo to deform, in1 = rest cage, in2 = deformed cage. `radius` (capture
# radius) MUST roughly match cage point spacing (the 0.1 default binds ~nothing on a metric-scale mesh).
_PD_MODE = ("capturedeform", "capture", "deform")


@endpoint("pointdeform")
def pointdeform(params):
    """Wrap-deform `input` (in0) by the motion of a cage: `rest_cage` (in1) -> `deformed_cage` (in2).
    The dense mesh follows the low-res cage delta. `radius` (capture radius) must roughly match the
    cage point spacing, or little/nothing binds. `capture_attribs` picks which attrs deform-carry."""
    n = child_after(params["input"], "pointdeform", params.get("name"))
    if params.get("rest_cage"):
        bridge_input(n, params["rest_cage"], index=1, name_hint="rest_cage")
    if params.get("deformed_cage"):
        bridge_input(n, params["deformed_cage"], index=2, name_hint="deformed_cage")
    _menu_set(n, "mode", str(params.get("mode", "capturedeform")), _PD_MODE)
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-4, 1e6))
    if "min_points" in params:
        _try_set(n, "minpt", int(clamp(int(params["min_points"]), 1, 1000)))
    if "max_points" in params:
        _try_set(n, "maxpt", int(clamp(int(params["max_points"]), 1, 10000)))
    if params.get("capture_attribs"):
        _try_set(n, "attribs", str(params["capture_attribs"]))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points())}


# ── crease (subdivision crease weights) ──────────────────────────────────────────────────────────────
# Writes `creaseweight` (a VERTEX attribute, verified) on an edge group so a downstream `subdivide` keeps
# those edges sharp. op menu is addto|set|delete (we default to set).
_CREASE_OP = ("addto", "set", "delete")


@endpoint("crease")
def crease(params):
    """Write `creaseweight` on an edge group so a downstream subdivide (facet_smooth_subdiv op=subdivide)
    keeps those edges SHARP. `group` = edge group, `weight` = crease value (0..10), `op` = addto|set|
    delete. The weight lands on vertices and is consumed by subdivide automatically."""
    n = child_after(params["input"], "crease", params.get("name"))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    _menu_set(n, "op", str(params.get("op", "set")), _CREASE_OP)
    if "weight" in params:
        _try_set(n, "crease", clamp(float(params["weight"]), 0.0, 10.0))
    if params.get("attrib_name"):
        _try_set(n, "creaseattrib", str(params["attrib_name"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims())}


# ── divide (triangulate / brick / add resolution) ────────────────────────────────────────────────────
# `convex` (triangulate) defaults ON, so a bare divide already triangulates. brick tiling + dual optional.
@endpoint("divide")
def divide(params):
    """Divide/triangulate polygons. `triangulate` (convex, default on) with `max_sides`; `smooth` (a
    Catmull-style subdivide) with `divisions`; `brick`=true + `brick_size`=[x,y,z] tiles the mesh;
    `compute_dual` builds the dual mesh; `remove_shared_edges` merges. A bare call triangulates."""
    n = child_after(params["input"], "divide", params.get("name"))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if "triangulate" in params:
        _try_set(n, "convex", bool(params["triangulate"]))
    if "max_sides" in params:
        _try_set(n, "usemaxsides", True)
        _try_set(n, "numsides", int(clamp(int(params["max_sides"]), 3, 100)))
    if "smooth" in params:
        _try_set(n, "smooth", bool(params["smooth"]))
    if "divisions" in params:
        # each smooth-subdivide level ~4x polycount; cap at 6 (node soft-max 5).
        _try_set(n, "divs", int(clamp(int(params["divisions"]), 1, 6)))
    if "brick" in params:
        _try_set(n, "brick", bool(params["brick"]))
    bs = params.get("brick_size")
    if isinstance(bs, (list, tuple)) and len(bs) == 3:
        for pn, v in zip(("sizex", "sizey", "sizez"), bs):
            _try_set(n, pn, clamp(float(v), 1e-6, 1e6))
    if "compute_dual" in params:
        _try_set(n, "dual", bool(params["compute_dual"]))
    if "remove_shared_edges" in params:
        _try_set(n, "removesh", bool(params["remove_shared_edges"]))
    g = n.geometry()
    return advise({"node": n.path(), "prims": len(g.prims())}, n)


# ── mirror (reflect across a plane + optional weld) ──────────────────────────────────────────────────
_MIRROR_AXIS = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_MIRROR_OP = ("all", "clip")
_MIRROR_REVNML = ("noreverse", "reverse", "reverseu", "reversev")


@endpoint("mirror")
def mirror(params):
    """Reflect geometry across a plane and (by default) weld the seam. `axis`=x|y|z is a shortcut for
    the plane normal (or give dirx/diry/dirz + originx/originy/originz); `dist` offsets the plane.
    `keep_original`=false replaces with only the mirror; `weld` fuses the coincident seam; `flip_normals`
    reverses normals on the copy. `operation`=clip cuts at the plane instead of reflecting."""
    n = child_after(params["input"], "mirror", params.get("name"))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if "operation" in params:
        _menu_set(n, "operation", str(params["operation"]), _MIRROR_OP)
    axis = params.get("axis")
    if axis in _MIRROR_AXIS:
        for pn, v in zip(("dirx", "diry", "dirz"), _MIRROR_AXIS[axis]):
            _try_set(n, pn, v)
    else:
        for pn in ("dirx", "diry", "dirz"):
            if pn in params:
                _try_set(n, pn, float(params[pn]))
    for pn in ("originx", "originy", "originz", "dist"):
        if pn in params:
            _try_set(n, pn, float(params[pn]))
    if "keep_original" in params:
        _try_set(n, "keepOriginal", bool(params["keep_original"]))
    if "weld" in params:
        _try_set(n, "consolidatepts", bool(params["weld"]))
    if "weld_tol" in params:
        _try_set(n, "consolidatetol", clamp(float(params["weld_tol"]), 0.0, 1e6))
    if "flip_normals" in params:
        _menu_set(n, "reversenml", "reverse" if params["flip_normals"] else "noreverse", _MIRROR_REVNML)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── dissolve (remove edges/points, MERGE adjacent faces — vs blast which deletes) ────────────────────
_DISSOLVE_INVERT = ("delete", "keep")
_DISSOLVE_BRIDGE = ("bridge", "disjoint", "delete")


@endpoint("dissolve")
def dissolve(params):
    """Dissolve an edge (or point) group, MERGING the adjacent faces (topology simplification — unlike
    blast, which deletes and leaves a hole). `group` = the edge/point group (built via the group tools);
    the component kind is inferred from the group. `invert`=keep dissolves everything EXCEPT the group;
    `bridge_mode` controls leftover 2-edge points; `remove_inline_points` cleans redundant colinear pts."""
    n = child_after(params["input"], "dissolve", params.get("name"))
    _try_set(n, "group", str(params.get("group", "")))
    if "invert" in params:
        _menu_set(n, "invertsel", str(params["invert"]), _DISSOLVE_INVERT)
    if "bridge_mode" in params:
        _menu_set(n, "bridge", str(params["bridge_mode"]), _DISSOLVE_BRIDGE)
    if "remove_inline_points" in params:
        _try_set(n, "reminlinepts", bool(params["remove_inline_points"]))
    if "colinear_tol" in params:
        _try_set(n, "coltol", clamp(float(params["colinear_tol"]), 0.0, 180.0))
    if "remove_unused_points" in params:
        _try_set(n, "remunusedpts", bool(params["remove_unused_points"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── bridge (connect two edge loops -> tube/skirt). Uses `polybridge` (NOT the legacy `bridge` SOP). ──
# KEY: polybridge reads TWO edge groups on a SINGLE input (srcgroup/dstgroup), not two inputs — the AI
# builds both loops into one stream + names two edge groups via the group tools.
_PBRIDGE_SPINE = ("straight", "curved", "external")
_PBRIDGE_PAIRING = ("length", "edgecount")
_PBRIDGE_DIRMODE = ("normal", "explicit")


@endpoint("bridge")
def bridge(params):
    """Bridge two edge loops into a connecting tube/skirt (polybridge). BOTH loops must live on ONE
    input as two edge groups (`src_group` / `dst_group`, built via the group tools + merged into one
    stream) — polybridge is NOT two-input. `divisions` subdivides the skirt; `twists`/`pairing_shift`/
    `reverse_src`/`reverse_dst` fix twisting or inside-out pairing; `thickness` shells it. `pairing`
    controls how the two loops' points are matched: length (relative edge lengths) or edgecount (loops
    with equal counts). depart_dir / arrive_dir ([x,y,z]) force the skirt to leave / land along an
    EXPLICIT direction (a curved footing perpendicular to a face) instead of the surface normal."""
    if not params.get("src_group") or not params.get("dst_group"):
        raise ValueError("bridge needs src_group and dst_group (two edge groups on input 0)")
    n = child_after(params["input"], "polybridge", params.get("name"))
    _try_set(n, "srcgroup", str(params["src_group"]))
    _try_set(n, "dstgroup", str(params["dst_group"]))
    if "divisions" in params:
        _try_set(n, "divisions", int(clamp(int(params["divisions"]), 1, 1000)))
    if "twists" in params:
        _try_set(n, "twists", int(clamp(int(params["twists"]), -100, 100)))
    if "thickness" in params:
        _try_set(n, "thicknessscale", clamp(float(params["thickness"]), 0.0, 1e6))
    if "pairing_shift" in params:
        _try_set(n, "pairingshift", int(params["pairing_shift"]))
    if "pairing" in params:
        _menu_set(n, "implcitpairing", str(params["pairing"]), _PBRIDGE_PAIRING)
    if "spine" in params:
        _menu_set(n, "spinetype", str(params["spine"]), _PBRIDGE_SPINE)
    if "depart_dir" in params and len(params["depart_dir"]) == 3:
        _menu_set(n, "usesrcdir", "explicit", _PBRIDGE_DIRMODE)
        for pn, v in zip(("srcdirx", "srcdiry", "srcdirz"), params["depart_dir"]):
            _try_set(n, pn, float(v))
    if "arrive_dir" in params and len(params["arrive_dir"]) == 3:
        _menu_set(n, "usedstdir", "explicit", _PBRIDGE_DIRMODE)
        for pn, v in zip(("dstdirx", "dstdiry", "dstdirz"), params["arrive_dir"]):
            _try_set(n, pn, float(v))
    if "reverse_src" in params:
        _try_set(n, "srcrevwinding", bool(params["reverse_src"]))
    if "reverse_dst" in params:
        _try_set(n, "dstrevwinding", bool(params["reverse_dst"]))
    if "keep_loops" in params:
        _try_set(n, "deletesrc", not bool(params["keep_loops"]))
        _try_set(n, "deletedst", not bool(params["keep_loops"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── structural: switch / null / sort ──────────────────────────────────────────────────────────────
# Sort menu tokens exposed (data-only subset): the `expression` mode is DELIBERATELY excluded --
# it evaluates a user expression to order elements, which would be a code path. Everything here is
# a fixed reordering rule or an attribute/vector reference.
_SORT_MODE = ("none", "byx", "byy", "byz", "rev", "seed", "prox", "vector", "spatial", "attribute", "reorder")


@endpoint("switch")
def switch(params):
    """Output ONE of several inputs, selected by an integer index -- variant / LOD assembly and
    A/B toggles. inputs = list of SOP paths (JSON array or comma list). Foreign-network inputs are
    auto-bridged (world-correct, like merge)."""
    inputs = params.get("inputs") or []
    if isinstance(inputs, str):
        s = inputs.strip()
        try:
            parsed = json.loads(s)
            inputs = parsed if isinstance(parsed, list) else [str(parsed)]
        except Exception:
            inputs = [p.strip() for p in s.split(",") if p.strip()]
    if not inputs:
        raise ValueError("switch needs a non-empty 'inputs' list of SOP paths")
    nodes = [resolve_node(p) for p in inputs]
    parent = nodes[0].parent()
    n = parent.createNode("switch", params.get("name"))
    for i, nd in enumerate(nodes):
        n.setInput(i, bridge_into(nd, parent, xformtype=1, name_hint=nd.name()))
    idx = int(clamp(int(params.get("index", 0)), 0, len(nodes) - 1))
    _try_set(n, "input", idx)
    n.moveToGoodPosition()
    g = n.geometry()
    return {"node": n.path(), "inputs": len(nodes), "selected": idx,
            "points": len(g.points()), "prims": len(g.prims())}


@endpoint("null")
def null(params):
    """No-op passthrough / named waypoint -- the Houdini idiom for a clean, stable downstream handle
    to reference geometry (the `name` is the whole point)."""
    n = child_after(params["input"], "null", params.get("name"))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


@endpoint("sort")
def sort(params):
    """Deterministically reorder points and/or prims (stable ids for copy-stamp / instancing
    determinism). point_sort / prim_sort pick the ordering rule; attribute + direction feed the
    attribute / vector modes."""
    n = child_after(params["input"], "sort", params.get("name"))
    if params.get("point_sort"):
        _try_set(n, "ptsort", str(params["point_sort"]))
    if params.get("prim_sort"):
        _try_set(n, "primsort", str(params["prim_sort"]))
    if "seed" in params:
        _try_set(n, "pointseed", int(params["seed"]))
        _try_set(n, "primseed", int(params["seed"]))
    if params.get("attribute"):
        _try_set(n, "pointattrib", str(params["attribute"]))
        _try_set(n, "primattrib", str(params["attribute"]))
    d = params.get("direction")
    if isinstance(d, (list, tuple)) and len(d) == 3:
        for axis, val in zip(("x", "y", "z"), d):
            _try_set(n, "pointdir" + axis, float(val))
            _try_set(n, "primdir" + axis, float(val))
    if "reverse" in params:
        _try_set(n, "pointreverse", bool(params["reverse"]))
        _try_set(n, "primreverse", bool(params["reverse"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


@endpoint("polysplit_loop")
def polysplit_loop(params):
    """Insert parametric edge LOOP(s) with polysplit::2.0 (Edge-Loop mode is the internal `quadcut`
    pathtype — hard-wired). seed_edge = a single '{prim}e{edge}' token (e.g. '0e1'); loops = number of
    evenly spaced loops; position = crossing location 0..1. Keeps quads; the interactive free-cut path
    is NOT exposed."""
    n = child_after(params["input"], "polysplit::2.0", params.get("name"))
    _try_set(n, "pathtype", "quadcut")   # 'quadcut' == "Edge Loop" (label/token are deceptively named)
    seed = str(params["seed_edge"])
    parts = seed.split("e")
    if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        raise ValueError("seed_edge must be a single '{prim}e{edge}' token, e.g. '0e1'")
    _try_set(n, "splitloc", seed)
    if "loops" in params:
        _try_set(n, "numloops", int(clamp(int(params["loops"]), 1, 256)))
    if "position" in params:
        _try_set(n, "edgepercenttoggle", 1)
        _try_set(n, "edgepercent", clamp(float(params["position"]), 0.0, 1.0))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()), "points": len(g.points())}


@endpoint("poly_split")
def poly_split(params):
    """Cut a FREEFORM edge path across faces with polysplit::2.0 (Shortest-Distance mode) — the
    mechanical-retopo primitive that routes a new edge run across n-gons / boolean seams "up and
    over", distinct from polysplit_loop (parallel edge loops). `path` = the ordered Split-Locations
    string, EDGE-CROSSING tokens separated by spaces (Houdini snaps the cut to the shortest path
    between successive tokens):
      • 'AeB'    — midpoint of edge B of primitive A (e.g. '0e3')
      • 'AeB:t'  — t (0..1) along edge B of primitive A (e.g. '0e3:0.7')
      • 'pA-B'   — midpoint of the edge between points A and B (e.g. 'p1-3')
      • 'pA-B:t' — t (0..1) along that edge (e.g. 'p1-3:0.7')
    (Bare point numbers are NOT accepted — the tokens are edge crossings; interior/mid-face cuts
    need allow_faces=true and an initial edge token.) close = extra cut from the last token back to
    the first (loop); quad_complete = auto-insert edges so the cut doesn't leave an N-gon."""
    n = child_after(params["input"], "polysplit::2.0", params.get("name"))
    _try_set(n, "pathtype", "shortest")   # 'shortest' == "Shortest Distance" (the freeform path; 'quadcut'=edge loop)
    _try_set(n, "splitloc", str(params["path"]))
    if "close" in params:
        _try_set(n, "close", 1 if params["close"] else 0)
    if "allow_faces" in params:
        _try_set(n, "allowfaces", 1 if params["allow_faces"] else 0)
    if "quad_complete" in params:
        _try_set(n, "quadcomplete", 1 if params["quad_complete"] else 0)
    if "tolerance" in params:
        _try_set(n, "tolerance", clamp(float(params["tolerance"]), 0.0, 1e9))
    if "update_normals" in params:
        _try_set(n, "updatenorms", 1 if params["update_normals"] else 0)
    g = n.geometry()
    if g is None:  # invalid split path → surface the node's cook error instead of an opaque None
        errs = "; ".join(n.errors()) or "cook produced no geometry"
        raise ValueError("poly_split path '%s' failed: %s" % (params["path"], errs))
    return {"node": n.path(), "prims": len(g.prims()), "points": len(g.points())}


def _set_vec3(node, name, vals):
    """Set a len-3 parmTuple from a [x,y,z] sequence (probe-safe: no-op if the tuple is absent
    or the input isn't length 3)."""
    pt = node.parmTuple(name)
    if pt is None:
        return False
    v = list(vals)
    if len(v) != 3:
        return False
    try:
        pt.set(tuple(float(x) for x in v))
        return True
    except Exception:
        return False


@endpoint("copy_transform")
def copy_transform(params):
    """Copy-and-Transform (copyxform): make N copies of the input geometry, each carrying a
    CUMULATIVE incremental transform — copy i gets i× the translate/rotate/scale. This is the
    rotational-ARRAY primitive: rotate=[0,60,0] with copies=6 lays 6 parts evenly around Y (e.g. a
    revolver cylinder's 6 chambers); a straight linear array is translate=[dx,0,0]. `copies` INCLUDES
    the original (copies=6 → 6 total). pivot='origin'|'centroid'; for an off-axis rotation centre set
    pivot_t (pivot translate) / pivot_r. pack=pack each copy as a packed primitive/instance (cheap
    display + instancing). copy_attrib names a per-copy index attribute stamped on the output."""
    n = child_after(params["input"], "copyxform", params.get("name"))
    if "copies" in params:
        _try_set(n, "ncy", int(clamp(int(params["copies"]), 1, 100000)))
    if "translate" in params:
        _set_vec3(n, "t", params["translate"])
    if "rotate" in params:
        _set_vec3(n, "r", params["rotate"])
    if "scale" in params:
        _set_vec3(n, "s", params["scale"])
    if "uniform_scale" in params:
        _try_set(n, "scale", float(params["uniform_scale"]))
    if "pivot" in params:
        _try_set(n, "pivot", str(params["pivot"]))       # string-token menu: origin | centroid
    if "pivot_t" in params:
        _set_vec3(n, "p", params["pivot_t"])
    if "pivot_r" in params:
        _set_vec3(n, "pr", params["pivot_r"])
    if "transform_order" in params:
        _try_set(n, "xOrd", str(params["transform_order"]))
    if "rotate_order" in params:
        _try_set(n, "rOrd", str(params["rotate_order"]))
    if "pack" in params:
        _try_set(n, "pack", 1 if params["pack"] else 0)
    if "source_group" in params:
        _try_set(n, "sourcegroup", str(params["source_group"]))
    if "copy_attrib" in params:
        _try_set(n, "docopyattrib", 1)
        _try_set(n, "copyattrib", str(params["copy_attrib"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()), "points": len(g.points())}


@endpoint("helix")
def helix(params):
    """Create a fresh /obj geo containing a helix / coil curve (spiral SOP). The spring / coil /
    thread / screw generator — an ejector-rod spring, a bolt thread, a DNA strand, a spiral staircase
    guide. turns = number of revolutions; height = total rise along the axis (height=0 gives a flat
    Archimedean spiral); start_radius / end_radius taper the coil (equal = a cylindrical helix,
    end<start = a conical coil). divs_per_turn = smoothness. as_polygons=true (default) makes a
    polyline ready for `polywire`; false = a NURBS curve. rotate=[x,y,z] orients the whole coil.
    Creator: FAILS on name collision (never destroys existing work). Surface it with `polywire`."""
    name = params["name"]
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    geo = obj.createNode("geo", name)
    sop = geo.createNode("spiral")
    _try_set(sop, "type", "poly" if params.get("as_polygons", True) else "nurbs")  # string-token menu
    _try_set(sop, "mode", "turns")  # drive by turns + height (vs height+pitch); string-token menu
    if "turns" in params:
        _try_set(sop, "turns", clamp(float(params["turns"]), 0.0, 100000.0))
    if "height" in params:
        _try_set(sop, "height", clamp(float(params["height"]), 0.0, 1e9))
    if "start_radius" in params or "end_radius" in params:
        _try_set(sop, "radiusmode", "endradius")  # explicit start/end (string-token menu)
    if "start_radius" in params:
        _try_set(sop, "startradius", clamp(float(params["start_radius"]), 1e-6, 1e9))
    if "end_radius" in params:
        _try_set(sop, "endradius", clamp(float(params["end_radius"]), 1e-6, 1e9))
    if "divs_per_turn" in params:
        _try_set(sop, "divsmode", "divsperturn")  # string-token menu
        _try_set(sop, "divsperturn", clamp(float(params["divs_per_turn"]), 3.0, 1000.0))
    if "direction" in params and str(params["direction"]) in ("cw", "ccw"):
        _try_set(sop, "direction", str(params["direction"]))
    if "rotate" in params and len(params["rotate"]) == 3:
        for pn, v in zip(("rx", "ry", "rz"), params["rotate"]):  # spiral uses individual rx/ry/rz
            _try_set(sop, pn, float(v))
    g = sop.geometry()
    return {"node": geo.path(), "sop": sop.path(), "points": len(g.points()), "prims": len(g.prims())}


@endpoint("polywire")
def polywire(params):
    """Surface a curve / wire into solid tube geometry (polywire) — turn a helix, a curve network, or
    any polyline into renderable tubes: springs, cables, pipes, ropes, wireframe renders, neurons,
    branches. radius = tube radius; divisions = cross-section sides (min 3, e.g. 6 = hex tube);
    segments = subdivisions along each wire span; smooth rounds the joints; joint_correct prevents
    buckling where wires meet at sharp angles (max_scale caps the joint fattening). scale_attrib names
    a per-point float attribute to vary the tube radius along the wire (tapering). Accepts polygon OR
    spline (NURBS/Bezier) input curves -- splines are auto-tessellated to polygons first so the tube
    is never silently empty (so helix(as_polygons=false) and create_curve nurbs both work here)."""
    # polywire only surfaces POLYGON wires: a NURBS/Bezier spline curve passes straight through with
    # ZERO faces (a silent empty result -- e.g. create_curve(curve_type='nurbs') or helix(as_polygons=
    # false)). If the input carries spline curves, tessellate them to polygons first via a `convert`
    # (totype='poly') so polywire always produces a tube. Polygon input is untouched (no convert added).
    src = resolve_node(params["input"])
    try:
        if isinstance(src, hou.ObjNode):
            disp = src.displayNode() or src.renderNode()
            if disp is not None:
                src = disp
    except Exception:
        pass
    tail_path = params["input"]
    try:
        gin = src.geometry()
        spline = (hou.primType.NURBSCurve, hou.primType.BezierCurve)
        if gin is not None and any(pr.type() in spline for pr in gin.prims()):
            conv = src.parent().createNode("convert", "wire_to_poly")
            conv.setInput(0, src)
            _try_set(conv, "totype", "poly")
            conv.moveToGoodPosition()
            tail_path = conv.path()
    except Exception:
        pass
    n = child_after(tail_path, "polywire", params.get("name"))
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-6, 1e9))
    if "divisions" in params:
        _try_set(n, "div", int(clamp(int(params["divisions"]), 3, 1000)))
    if "segments" in params:
        _try_set(n, "segs", int(clamp(int(params["segments"]), 1, 1000)))
    if "smooth" in params:
        _try_set(n, "smooth", int(clamp(int(params["smooth"]), 0, 100)))
    if "joint_correct" in params:
        _try_set(n, "jointcorrect", 1 if params["joint_correct"] else 0)
    if "max_scale" in params:
        _try_set(n, "maxscale", clamp(float(params["max_scale"]), 1.0, 1e6))
    if "max_valence" in params:
        _try_set(n, "maxvalence", int(clamp(int(params["max_valence"]), 2, 100)))
    if "scale_attrib" in params:
        _try_set(n, "usescaleattrib", "attrib")  # string-token menu: constant | attrib
        _try_set(n, "scaleattrib", str(params["scale_attrib"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()), "points": len(g.points())}


_CVXDECOMP_OUTPUT = ("hulls", "segments")


@endpoint("convex_decompose")
def convex_decompose(params):
    """Approximate CONVEX DECOMPOSITION (convexdecomposition) — break a concave mesh into a set of
    convex hull pieces, the standard way to make cheap RBD/physics COLLISION PROXIES (a convex hull
    is far cheaper to collide against than a concave mesh, and most solvers want convex colliders).
    max_concavity (0..1) trades fit vs piece count: lower = tighter to the surface + MORE hulls,
    higher = fewer/looser hulls. output: hulls (the convex pieces, default) | segments (the original
    surface partitioned + tagged with the `segment` attribute). per_piece decomposes each island of
    `piece_attrib` (e.g. `name`) independently — the norm after a fracture. treat_as_solid fills the
    interior before decomposing (for watertight solids); merge_segments removes sliver hulls."""
    n = child_after(params["input"], "convexdecomposition", params.get("name"))
    if "max_concavity" in params:
        _try_set(n, "maxconcavity", clamp(float(params["max_concavity"]), 0.0, 1.0))
    if params.get("output"):
        _menu_set(n, "geometryoutput", str(params["output"]), _CVXDECOMP_OUTPUT)
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if params.get("per_piece"):
        _try_set(n, "usepieceattrib", 1)
        _try_set(n, "pieceattrib", str(params.get("piece_attrib", "name")))
    if "treat_as_solid" in params:
        _try_set(n, "treatassolid", 1 if params["treat_as_solid"] else 0)
    if "merge_segments" in params:
        _try_set(n, "mergesegments", 1 if params["merge_segments"] else 0)
    if params.get("segment_attrib"):
        _try_set(n, "outputsegmentattrib", 1)
        _try_set(n, "segmentattrib", str(params["segment_attrib"]))
    if params.get("interior_group"):
        _try_set(n, "outputinteriorgroup", 1)
        _try_set(n, "interiorgroupname", str(params["interior_group"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()),
            "hulls": len({p.attribValue("segment") for p in g.prims()}) if g.findPrimAttrib("segment") else None}

"""Attribute-ops + piece-identity / sim round-trip handlers (SOP).

The plumbing a real destruction / particle / sim setup is ~60% made of: carrying attributes
through topology changes (interpolate), sampling volumes onto points (from_volume), smoothing
masks/velocity fields (blur), moving/labelling attributes, and — the broken seam — turning loose
fragments into named packed pieces (name/assemble) and applying a sim result back onto those packed
pieces (transform_pieces).

Every parm name + menu token below was live-probed on Houdini 21.0.671; nothing is guessed. All nodetypes are UNVERSIONED on
this build. Style mirrors handlers/sim.py + handlers/attrib.py: typed, clamped, probe-safe
(`_try_set` skips absent parms, never invents one), creators FAIL on name collision (child_after ->
createNode(type, name) raises rather than clobber existing user work). Data-only: no wrangle / VEX /
exec — these are pure typed node wrappers.
"""

import json

import hou
from houdini_executor.server import endpoint, child_after, clamp, resolve_node
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe setters (same contract as attrib.py / sim.py) ─────────────────




def _str_menu_set(node, parm, token, tokens):
    """String-type menu parm: the TOKEN itself is the stored value."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _set_vec(node, parm, values, n):
    """Set an n-tuple float parm from a list (pads/truncates). Probe-safe."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    vals = [float(x) for x in list(values)[:n]] + [0.0] * (n - min(len(values), n))
    try:
        pt.set(tuple(vals))
        return True
    except Exception:
        return False


# ── data-only ramp / discrete / blend multiparm setters (json.loads-tolerant) ─
# Every value below is a literal float or an enum token selected from a fixed live-probed set — no
# expression, no VEX, no code path. The MCP param Kind for these list/ramp params is Str, so each
# setter accepts either a JSON string (decoded with json.loads) or a native list, mirroring
# _set_color_ramp / rbd_constraints_from_lines elsewhere.
_RAMP_INTERP = ("constant", "linear", "catmull-rom", "monotonecubic", "bezier", "bspline", "hermite")
# interp token -> hou.rampBasis member NAME (resolved via getattr so a build missing a member can't
# break module import); every name below was live-probed present on 21.0.671.
_RAMP_BASIS_NAME = {
    "constant": "Constant", "linear": "Linear", "catmull-rom": "CatmullRom",
    "monotonecubic": "MonotoneCubic", "bezier": "Bezier", "bspline": "BSpline", "hermite": "Hermite",
}


def _set_float_ramp(node, parm, entries):
    """Set a FLOAT `hou.Ramp` parm (e.g. attribrandomize `ramp`) from typed entries
    [{"pos":f,"value":f,"interp":"linear"}, ...]. interp is one of _RAMP_INTERP (per-key basis;
    defaults to linear on absent/unknown token). Writes the ramp#pos/ramp#value/ramp#interp triples.
    Accepts a JSON string or a native list. Floats + enum tokens ONLY. Probe-safe (returns bool)."""
    p = node.parm(parm)
    if isinstance(entries, str):
        try:
            entries = json.loads(entries)
        except Exception:
            return False
    if p is None or not isinstance(entries, (list, tuple)) or not entries:
        return False
    try:
        pts = []
        for e in entries:
            pos = float(e["pos"])
            val = float(e["value"])
            token = str(e.get("interp", "linear")).lower()
            basis_name = _RAMP_BASIS_NAME.get(token, "Linear")
            basis = getattr(hou.rampBasis, basis_name, hou.rampBasis.Linear)
            pts.append((pos, val, basis))
        pts.sort(key=lambda x: x[0])
        keys = tuple(pt[0] for pt in pts)
        vals = tuple(pt[1] for pt in pts)
        bases = tuple(pt[2] for pt in pts)
        p.set(hou.Ramp(bases, keys, vals))
        return True
    except Exception:
        return False


def _set_discrete_values(node, entries):
    """Set the attribrandomize `values` multiparm (value#/weight#/strvalue#, 0-based) that drives the
    `discrete` distribution. entries = [{"value":f (or "strvalue":s), "weight":f}, ...]. If ANY entry
    carries a strvalue the value type is switched to string; strings are plain literal labels (never
    evaluated). Accepts a JSON string or native list. Probe-safe (returns bool)."""
    if isinstance(entries, str):
        try:
            entries = json.loads(entries)
        except Exception:
            return False
    if not isinstance(entries, (list, tuple)) or not entries:
        return False
    countp = node.parm("values")
    if countp is None:
        return False
    use_str = any(isinstance(e, dict) and "strvalue" in e for e in entries)
    try:
        _try_set(node, "valuetype", 1 if use_str else 0)   # menu ('float','string')
        countp.set(len(entries))
        for i, e in enumerate(entries):
            if not isinstance(e, dict):
                continue
            if "strvalue" in e:
                _try_set(node, "strvalue%d" % i, str(e["strvalue"]))
            if "value" in e:
                _try_set(node, "value%d" % i, float(e["value"]))
            if "weight" in e:
                _try_set(node, "weight%d" % i, float(e["weight"]))
        return True
    except Exception:
        return False


def _set_blend_weights(node, weights):
    """Set the attribcomposite `nblends` multiparm count + per-layer `blend#` floats (0-based) for
    layered blending. weights = a numeric list [w0, w1, ...] or a JSON-encoded such list. Floats
    ONLY. Probe-safe (returns bool)."""
    if isinstance(weights, str):
        try:
            weights = json.loads(weights)
        except Exception:
            return False
    if not isinstance(weights, (list, tuple)) or not weights:
        return False
    countp = node.parm("nblends")
    if countp is None:
        return False
    try:
        countp.set(len(weights))
        for i, w in enumerate(weights):
            _try_set(node, "blend%d" % i, float(w))
        return True
    except Exception:
        return False


def _sop_of(path):
    """Resolve a node path to the SOP a second input should read (an /obj geo -> its display SOP),
    mirroring child_after's ObjNode unwrap so callers can pass either a SOP or the containing geo."""
    n = resolve_node(path)
    try:
        if isinstance(n, hou.ObjNode):
            disp = n.displayNode() or n.renderNode()
            if disp is not None:
                return disp
    except Exception:
        pass
    return n


def _cook(n):
    """Force a cook so readback reflects the op; guarded so a missing required 2nd input (the node
    can't cook yet) leaves the built node in place rather than failing the build. Returns cook OK."""
    try:
        n.geometry()
        return True
    except Exception:
        return False


def _norm_class(c, allowed):
    """Map friendly class aliases onto a node's own tokens (prim->primitive/prims, point->points…)."""
    c = str(c)
    if c == "prim" and "primitive" in allowed:
        return "primitive"
    if c == "prim" and "prims" in allowed:
        return "prims"
    if c == "point" and "points" in allowed:
        return "points"
    if c == "vertex" and "vertices" in allowed:
        return "vertices"
    return c


# ══════════════════════════════════════════════════════════════════════════════
# ATTRIBUTE OPS
# ══════════════════════════════════════════════════════════════════════════════
_AI_TOTYPE = ("points", "vertices", "prims", "detail")
_AI_INTERPBY = ("primuvw", "pointweights", "vertweights", "primweights")


@endpoint("attribute_interpolate")
def attribute_interpolate(params):
    """Interpolate attributes from a source surface onto destination points via barycentric prim/uv
    or explicit point/vertex weights — how you carry `v`/`Cd`/materials back onto geometry after a
    topology change (fracture, scatter, remesh). input=destination points; source=NodePath of the
    surface to sample. to_class: points|vertices|prims|detail. interp_by: primuvw|pointweights|
    vertweights|primweights. point_attribs/prim_attribs/vertex_attribs/detail_attribs = space-sep
    name patterns to carry (point default '*'). number_attrib/weights_attrib name the source-prim /
    barycentric attribs on the destination. match_groups (default True) only interpolates between
    matching-named groups. normalize/threshold/blend/prescale tune the blend."""
    n = child_after(params["input"], "attribinterpolate", params.get("name"))
    if params.get("source"):
        n.setInput(1, _sop_of(params["source"]))
    applied = {}
    if "match_groups" in params:
        _try_set(n, "matchgroups", bool(params["match_groups"]))
    applied["to_class"] = _menu_set(n, "totype", _norm_class(params.get("to_class", "points"), _AI_TOTYPE), _AI_TOTYPE)
    applied["interp_by"] = _menu_set(n, "interpby", str(params.get("interp_by", "primuvw")), _AI_INTERPBY)
    if params.get("number_attrib") is not None:
        _try_set(n, "numberattrib", str(params["number_attrib"]))
    if params.get("weights_attrib") is not None:
        _try_set(n, "weightsattrib", str(params["weights_attrib"]))
    if "point_attribs" in params:
        _try_set(n, "pointattribs", str(params["point_attribs"]))
    if "vertex_attribs" in params:
        _try_set(n, "vertattribs", str(params["vertex_attribs"]))
    if "prim_attribs" in params:
        _try_set(n, "primattribs", str(params["prim_attribs"]))
    if "detail_attribs" in params:
        _try_set(n, "detailattribs", str(params["detail_attribs"]))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if "prescale" in params:
        _try_set(n, "prescale", clamp(float(params["prescale"]), -1e6, 1e6))
    if "normalize" in params:
        _try_set(n, "normalize", bool(params["normalize"]))
    if "threshold" in params:
        _try_set(n, "threshold", clamp(float(params["threshold"]), 0.0, 1e6))
    if "blend" in params:
        _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


_AFV_TYPE = ("float", "int", "vector")


@endpoint("attribute_from_volume")
def attribute_from_volume(params):
    """Sample a volume / VDB into a point attribute — seed point `v` from a velocity field, read a
    density/temperature mask off pyro, or bake a collision SDF distance onto points. input=points;
    volume=NodePath of the geometry holding the volume(s). field = volume primitive name(s) to
    read; attrib_name = output attribute (default 'Cd'); attrib_type: float|int|vector; size = tuple
    size (1..4). remap_in/remap_out ([min,max] each) rescale the sampled value; default_value
    ([x,y,z,w]) is used where no volume covers a point."""
    n = child_after(params["input"], "attribfromvolume", params.get("name"))
    if params.get("volume"):
        n.setInput(1, _sop_of(params["volume"]))
    applied = {}
    if params.get("field") is not None:
        applied["field"] = _try_set(n, "field", str(params["field"]))
    _try_set(n, "name", str(params.get("attrib_name", "Cd")))
    applied["attrib_type"] = _menu_set(n, "type", str(params.get("attrib_type", "float")), _AFV_TYPE)
    if "size" in params:
        _try_set(n, "size", int(clamp(int(params["size"]), 1, 4)))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    if isinstance(params.get("default_value"), (list, tuple)):
        applied["default_value"] = _set_vec(n, "default", params["default_value"], 4)
    if isinstance(params.get("remap_in"), (list, tuple)):
        applied["remap_in"] = _set_vec(n, "rangein", params["remap_in"], 2)
    if isinstance(params.get("remap_out"), (list, tuple)):
        applied["remap_out"] = _set_vec(n, "rangeout", params["remap_out"], 2)
    return {"node": n.path(), "attrib": str(params.get("attrib_name", "Cd")),
            "cooked": _cook(n), "applied": applied}


_AB_METHOD = ("uniform", "edgelength")
_AB_MODE = ("laplacian", "volpreserving", "custom")
_AB_INFLUENCE = ("connectivity", "proximity")


@endpoint("attribute_blur")
def attribute_blur(params):
    """Smooth / diffuse an attribute over the connectivity (or proximity) neighbourhood — soften
    masks, relax velocity or constraint-strength fields, blur `Cd`, kill hard seams. attributes =
    space-sep names (default 'Cd'; note blurring 'P' relaxes the mesh itself). iterations = passes;
    mode: laplacian|volpreserving|custom; step_size 0..1; method: uniform|edgelength; influence:
    connectivity|proximity (proximity uses prox_radius + max_neighbours); weight_attrib scales the
    per-point blur; alpha_attrib is a per-point 0..1 mask gating where blurring applies; pin_border
    holds open edges. original_blend mixes the pre-blur value back in and blur_blend scales the
    blurred contribution."""
    n = child_after(params["input"], "attribblur", params.get("name"))
    applied = {}
    _try_set(n, "attributes", str(params.get("attributes", "Cd")))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 10000)))
    applied["mode"] = _menu_set(n, "mode", str(params.get("mode", "laplacian")), _AB_MODE)
    applied["method"] = _menu_set(n, "method", str(params.get("method", "uniform")), _AB_METHOD)
    if "step_size" in params:
        _try_set(n, "stepsize", clamp(float(params["step_size"]), 0.0, 1.0))
    if params.get("influence"):
        applied["influence"] = _menu_set(n, "influencetype", str(params["influence"]), _AB_INFLUENCE)
    if "prox_radius" in params:
        _try_set(n, "proxrad", clamp(float(params["prox_radius"]), 0.0, 1e9))
    if "max_neighbours" in params:
        _try_set(n, "maxneigh", int(clamp(int(params["max_neighbours"]), 1, 100000)))
    if params.get("weight_attrib"):
        _try_set(n, "weightattrib", str(params["weight_attrib"]))
    if params.get("alpha_attrib"):
        _try_set(n, "enablealpha", True)
        _try_set(n, "alphaattrib", str(params["alpha_attrib"]))
    if "pin_border" in params:
        _try_set(n, "pinborder", bool(params["pin_border"]))
    if "original_blend" in params:
        _try_set(n, "enableblending", True)
        _try_set(n, "originalblend", clamp(float(params["original_blend"]), 0.0, 10.0))
    if "blur_blend" in params:
        _try_set(n, "enableblending", True)
        _try_set(n, "blurblend", clamp(float(params["blur_blend"]), 0.0, 10.0))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


_ACOPY_CLASS = ("guess", "sameasgroup", "vertices", "points", "prims", "detail")
_ACOPY_MATCHMETHOD = ("byvalues", "toelement")
_ACOPY_GRPTYPE = ("vertices", "points", "prims")


@endpoint("attribute_copy")
def attribute_copy(params):
    """Copy attribute values from a second geometry onto this one, matched by element index or by a
    shared id attribute — the standard non-wrangle way to move a computed `Cd`/`pscale`/`v`/material
    onto matching geometry. input=destination; source=NodePath to copy from. attribs = space-sep
    attribute name(s) to copy (default 'Cd'); class: guess|sameasgroup|vertices|points|prims|detail.
    match_by_attribute + match_attrib (default 'piece') matches elements by a shared value instead of
    by index (match_method: byvalues|toelement). copy_p also copies P; new_name renames the copied
    attribute. src_group/dest_group restrict the transfer (with src_group_type/dest_group_type)."""
    n = child_after(params["input"], "attribcopy", params.get("name"))
    if params.get("source"):
        n.setInput(1, _sop_of(params["source"]))
    applied = {}
    # 'attrib' menu selects which family; 'otherattrib' + attribname is the general path.
    _menu_set(n, "attrib", "otherattrib", ("colorattrib", "uvattrib", "otherattrib"))
    _try_set(n, "attribname", str(params.get("attribs", "Cd")))
    applied["class"] = _menu_set(n, "class", str(params.get("class", "guess")), _ACOPY_CLASS)
    if "copy_p" in params:
        _try_set(n, "copyp", bool(params["copy_p"]))
    if params.get("match_by_attribute"):
        _try_set(n, "matchbyattribute", True)
        _try_set(n, "attributetomatch", str(params.get("match_attrib", "piece")))
        _menu_set(n, "matchbyattributemethod", str(params.get("match_method", "byvalues")), _ACOPY_MATCHMETHOD)
    if params.get("new_name"):
        _try_set(n, "usenewname", True)
        _try_set(n, "newname", str(params["new_name"]))
    if params.get("src_group"):
        _try_set(n, "srcgroup", str(params["src_group"]))
        _menu_set(n, "srcgrouptype", str(params.get("src_group_type", "points")), _ACOPY_GRPTYPE)
    if params.get("dest_group"):
        _try_set(n, "destgroup", str(params["dest_group"]))
        _menu_set(n, "destgrouptype", str(params.get("dest_group_type", "points")), _ACOPY_GRPTYPE)
    return {"node": n.path(), "attribs": str(params.get("attribs", "Cd")),
            "cooked": _cook(n), "applied": applied}


_AR_CLASS = ("detail", "primitive", "point", "vertex")
_AR_OP = ("set", "add", "min", "max", "mult")
_AR_DIST = ("constant", "bernoulli", "uniform", "uniformdiscrete", "uniformorient", "uniformball",
            "normal", "exponential", "lognormal", "cauchy", "ramp", "discrete")


@endpoint("attribute_randomize")
def attribute_randomize(params):
    """Write a per-element random attribute with a chosen distribution — piece strength variance,
    initial velocity jitter, scatter attrs, destruction seeds. attrib_name = output (default 'Cd');
    class: detail|primitive|point|vertex; distribution: uniform|normal|bernoulli|uniformorient|
    uniformball|exponential|lognormal|cauchy|constant|... ; operation: set|add|min|max|mult (how the
    random value combines with the existing attr); dimensions 1..4; scale multiplies the result;
    seed. For uniform: min_value/max_value ([x,y,z,w]). For bernoulli: value_a/value_b + prob_b. For
    constant: const_value ([x,y,z,w]). For normal/lognormal/cauchy: mean_value (center) + std_dev
    (spread), each [x,y,z,w]. For uniformorient: cone_angle + direction ([x,y,z]) + power_bias
    (bias toward the cone axis). For ramp (distribution='ramp'): ramp = a list of
    {"pos":f,"value":f,"interp":constant|linear|catmull-rom|monotonecubic|bezier|bspline|hermite}. For
    discrete (distribution='discrete'): discrete_values = a list of {"value":f (or "strvalue":s),
    "weight":f}. For uniformdiscrete: min_discrete/max_discrete ([x,y,z,w] integer bounds). Optional
    clamps min_limit/max_limit ([x,y,z,w], each auto-enables its toggle). group/group_type restrict."""
    n = child_after(params["input"], "attribrandomize", params.get("name"))
    applied = {}
    _try_set(n, "name", str(params.get("attrib_name", "Cd")))
    applied["class"] = _menu_set(n, "class", str(params.get("class", "point")), _AR_CLASS)
    applied["distribution"] = _str_menu_set(n, "distribution", str(params.get("distribution", "uniform")), _AR_DIST)
    applied["operation"] = _str_menu_set(n, "operation", str(params.get("operation", "set")), _AR_OP)
    if "dimensions" in params:
        _try_set(n, "dimensions", int(clamp(int(params["dimensions"]), 1, 4)))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), -1e9, 1e9))
    if "seed" in params:
        _try_set(n, "seed", clamp(float(params["seed"]), 0.0, 1e12))
    if isinstance(params.get("min_value"), (list, tuple)):
        applied["min_value"] = _set_vec(n, "min", params["min_value"], 4)
    if isinstance(params.get("max_value"), (list, tuple)):
        applied["max_value"] = _set_vec(n, "max", params["max_value"], 4)
    if isinstance(params.get("value_a"), (list, tuple)):
        _set_vec(n, "valuea", params["value_a"], 4)
    if isinstance(params.get("value_b"), (list, tuple)):
        _set_vec(n, "valueb", params["value_b"], 4)
    if "prob_b" in params:
        _try_set(n, "probvalueb", clamp(float(params["prob_b"]), 0.0, 1.0))
    if "cone_angle" in params:
        _try_set(n, "useconeangle", True)
        _try_set(n, "coneangle", clamp(float(params["cone_angle"]), 0.0, 360.0))
    if "power_bias" in params:
        _try_set(n, "usepowerbias", True)
        _try_set(n, "powerbias", clamp(float(params["power_bias"]), -1.0, 20.0))
    if isinstance(params.get("direction"), (list, tuple)):
        _set_vec(n, "direction", params["direction"], 4)
    # constant distribution value; normal/lognormal/cauchy center (median) + spread (std_dev).
    if isinstance(params.get("const_value"), (list, tuple)):
        applied["const_value"] = _set_vec(n, "constvalue", params["const_value"], 4)
    if isinstance(params.get("mean_value"), (list, tuple)):
        applied["mean_value"] = _set_vec(n, "median", params["mean_value"], 4)
    if isinstance(params.get("std_dev"), (list, tuple)):
        applied["std_dev"] = _set_vec(n, "stddev", params["std_dev"], 4)
    # ── extended distributions (all data-only; distribution token already gated by _AR_DIST) ──
    # ramp: drives distribution='ramp' — a float Ramp of {pos,value,interp} triples.
    if params.get("ramp") is not None:
        applied["ramp"] = _set_float_ramp(n, "ramp", params["ramp"])
    # discrete_values: drives distribution='discrete' — the `values` multiparm (value/weight/strvalue).
    if params.get("discrete_values") is not None:
        applied["discrete_values"] = _set_discrete_values(n, params["discrete_values"])
    # uniformdiscrete: integer bounds as vec4 (x used for 1-D).
    if isinstance(params.get("min_discrete"), (list, tuple)):
        applied["min_discrete"] = _set_vec(n, "mindiscrete", params["min_discrete"], 4)
    if isinstance(params.get("max_discrete"), (list, tuple)):
        applied["max_discrete"] = _set_vec(n, "maxdiscrete", params["max_discrete"], 4)
    # optional clamps (vec4; enabling toggle auto-set) — live-confirmed parms.
    if isinstance(params.get("min_limit"), (list, tuple)):
        _try_set(n, "useminlimit", True)
        applied["min_limit"] = _set_vec(n, "minlimit", params["min_limit"], 4)
    if isinstance(params.get("max_limit"), (list, tuple)):
        _try_set(n, "usemaxlimit", True)
        applied["max_limit"] = _set_vec(n, "maxlimit", params["max_limit"], 4)
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    return {"node": n.path(), "attrib": str(params.get("attrib_name", "Cd")),
            "cooked": _cook(n), "applied": applied}


_ACOMP_OP = ("opmean", "opmax", "opmin", "opover", "opunder")


@endpoint("attribute_composite")
def attribute_composite(params):
    """Layer/combine same-named attributes from stacked (merged) geometry into one result — merging
    mask layers, combining force fields. input = the merged stream to composite over (matched by
    point number, or by position with match_by_position). operation: opmean|opmax|opmin|opover|
    opunder. point_attribs/prim_attribs/vertex_attribs/detail_attribs = space-sep name lists to
    composite (enabling a family sets its toggle). alpha_attrib drives over/under blending.
    blend_weights = a numeric list [w0,w1,...] (or JSON) setting the per-input-layer blend multiparm
    (nblends count + blend#)."""
    n = child_after(params["input"], "attribcomposite", params.get("name"))
    applied = {}
    applied["operation"] = _menu_set(n, "compop", str(params.get("operation", "opover")), _ACOMP_OP)
    if params.get("blend_weights") is not None:
        applied["blend_weights"] = _set_blend_weights(n, params["blend_weights"])
    if "point_attribs" in params:
        _try_set(n, "pointattribs", True)
        _try_set(n, "pointattriblist", str(params["point_attribs"]))
    if "prim_attribs" in params:
        _try_set(n, "primitiveattribs", True)
        _try_set(n, "primattriblist", str(params["prim_attribs"]))
    if "vertex_attribs" in params:
        _try_set(n, "vertexattribs", True)
        _try_set(n, "vertexattriblist", str(params["vertex_attribs"]))
    if "detail_attribs" in params:
        _try_set(n, "detailattribs", True)
        _try_set(n, "detailattriblist", str(params["detail_attribs"]))
    if "match_by_position" in params:
        _try_set(n, "matchpattrib", bool(params["match_by_position"]))
    if params.get("alpha_attrib"):
        _try_set(n, "alphaattrib", str(params["alpha_attrib"]))
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


@endpoint("attribute_reorient")
def attribute_reorient(params):
    """Reorient vector / quaternion attributes (`N`,`v`,`orient`,`up`) to follow the deformation
    between a rest reference and the live geometry — keeps instanced / oriented geo correct after a
    deform. input = live (deformed) geometry; reference = NodePath of the rest geometry (same point
    count). vector_attribs = space-sep vector attrs to rotate (e.g. 'N v'); quat_attribs = space-sep
    quaternion/orient attrs; use_normal builds the frame from the point normal. group restricts."""
    n = child_after(params["input"], "attribreorient", params.get("name"))
    if params.get("reference"):
        n.setInput(1, _sop_of(params["reference"]))
    if params.get("vector_attribs") is not None:
        _try_set(n, "vattribs", str(params["vector_attribs"]))
    if params.get("quat_attribs") is not None:
        _try_set(n, "qattribs", str(params["quat_attribs"]))
    if "use_normal" in params:
        _try_set(n, "usenormalattrib", bool(params["use_normal"]))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    return {"node": n.path(), "cooked": _cook(n)}


_ASWAP_METHOD = ("swap", "copy", "move")
_ASWAP_CLASS = ("detail", "primitive", "point", "vertex")
_ASWAP_TYPEINFO = ("source", "dest")


@endpoint("attribute_swap")
def attribute_swap(params):
    """Copy / move / swap / rename an attribute in one node (the common `v`<->`velocity` rename
    before a solver, or duplicating an attr under a new name). method: copy|move|swap (copy keeps
    the source, move renames, swap exchanges two); class: point|prim|vertex|detail; src = source
    attribute name(s); dst = destination attribute name(s); keep_type: source (copy source's type
    info) | dest (preserve destination's type info)."""
    n = child_after(params["input"], "attribswap", params.get("name"))
    applied = {}
    _try_set(n, "numswaps", 1)
    _try_set(n, "enable1", True)
    applied["method"] = _menu_set(n, "method1", str(params.get("method", "copy")), _ASWAP_METHOD)
    applied["class"] = _menu_set(n, "class1", _norm_class(params.get("class", "point"), _ASWAP_CLASS), _ASWAP_CLASS)
    if params.get("src") is not None:
        _try_set(n, "srcattribs1", str(params["src"]))
    if params.get("dst") is not None:
        _try_set(n, "dstattribs1", str(params["dst"]))
    if params.get("keep_type"):
        _menu_set(n, "typeinfo1", str(params["keep_type"]), _ASWAP_TYPEINFO)
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


# ══════════════════════════════════════════════════════════════════════════════
# PIECE IDENTITY + ROUND-TRIP
# ══════════════════════════════════════════════════════════════════════════════
_NAME_CLASS = ("primitive", "point", "vertex")


@endpoint("assign_name")
def assign_name(params):
    """Assign the `name` string attribute that defines packed-piece identity — required to prep
    imported / modelled fragments (that our fracture tools didn't create) for RBD/destruction, and
    the partner of `assemble`/`transform_pieces`. name_value = the name to write (e.g. 'piece'); if a
    group is given, only its elements get the name (leave empty to name everything). class:
    primitive|point|vertex (packed pieces read the PRIMITIVE name). attrib_name overrides the output
    attribute (default 'name'). from_group=True derives per-element names from group membership
    using group_mask (e.g. 'piece*') instead of a literal name_value."""
    n = child_after(params["input"], "name", params.get("name"))
    applied = {}
    _try_set(n, "attribname", str(params.get("attrib_name", "name")))
    applied["class"] = _menu_set(n, "class", _norm_class(params.get("class", "primitive"), _NAME_CLASS), _NAME_CLASS)
    if params.get("from_group"):
        _try_set(n, "donamefromgroup", True)
        _try_set(n, "namefromgroupmask", str(params.get("group_mask", "piece*")))
    else:
        _try_set(n, "numnames", 1)
        _try_set(n, "group1", str(params.get("group", "")))
        _try_set(n, "name1", str(params.get("name_value", "piece")))
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


_ENUM_CLASS = ("primitive", "point", "vertex")
_ENUM_MODE = ("elements", "pieces")
_ENUM_TYPE = ("int", "string")


@endpoint("enumerate")
def enumerate_attrib(params):
    """Stamp a per-element running index attribute — piece ids, cluster ids, constraint ordering.
    attrib_name = output (default 'index'); class: primitive|point|vertex; attrib_type: int|string
    (string uses prefix, e.g. 'piece_0'); mode: elements (index every element) | pieces (one index
    per `name`/piece — set piece_attrib). prefix (default 'piece') prepends when attrib_type=string.
    group restricts."""
    n = child_after(params["input"], "enumerate", params.get("name"))
    applied = {}
    _try_set(n, "attribname", str(params.get("attrib_name", "index")))
    applied["class"] = _menu_set(n, "grouptype", _norm_class(params.get("class", "point"), _ENUM_CLASS), _ENUM_CLASS)
    applied["attrib_type"] = _menu_set(n, "attribtype", str(params.get("attrib_type", "int")), _ENUM_TYPE)
    mode = str(params.get("mode", "elements"))
    applied["mode"] = _menu_set(n, "piecemode", mode, _ENUM_MODE)
    if mode == "pieces" or params.get("piece_attrib"):
        _try_set(n, "usepieceattrib", True)
        _try_set(n, "pieceattrib", str(params.get("piece_attrib", "name")))
    if params.get("prefix") is not None:
        _try_set(n, "prefix", str(params["prefix"]))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


_ASSEMBLE_PIVOT = ("origin", "centroid")
_ASSEMBLE_LOD = ("full", "points", "box", "centroid", "hidden")


@endpoint("assemble")
def assemble(params):
    """Turn loose fragments (imported, boolean-cut, or scattered) into sim-ready NAMED packed pieces
    — the canonical pre-sim step, partner of `assign_name`. Names each connected piece into
    piece_group (default 'piece') and, by default, PACKS them (pack=True -> one PackedFragment prim
    per piece, the RBD-ready form). packed_fragments=True (default) packs as fragments;
    packed_fragments=False packs each piece as standalone packed geometry. pack=False leaves loose
    named polygons. piece_attrib names an EXISTING per-prim identity attribute to assemble by (turns
    off Create-Name so it reads that attribute rather than recreating one; default derives from
    connectivity). pivot: origin|centroid (packed piece pivot); do_cusp hardens
    shared edges; new_name auto-numbers piece names; create_groups emits a primitive group per piece;
    connect groups by connectivity. transfer_attributes / transfer_groups = space-sep names to carry
    onto the pieces. viewport_lod: full|points|box|centroid|hidden. group restricts which prims are
    assembled."""
    n = child_after(params["input"], "assemble", params.get("name"))
    applied = {}
    if params.get("piece_group") is not None:
        _try_set(n, "outside_group", str(params["piece_group"]))
    if params.get("piece_attrib") is not None:
        # Assemble BY an existing identity attribute: name it and turn OFF 'Create Name Attribute'
        # (newname) so assemble reads the existing attr instead of recreating a colliding one.
        _try_set(n, "pieceattrib", str(params["piece_attrib"]))
        _try_set(n, "newname", False)
    if "create_groups" in params:
        _try_set(n, "newgroups", bool(params["create_groups"]))
    # In H21 `pack_geo` is the master pack toggle (emits PackedFragment prims); createpackedfragments
    # only selects fragment-vs-standalone packing WHEN pack_geo is on. Default both on so assemble
    # yields sim-ready packed pieces out of the box.
    applied["packed"] = _try_set(n, "pack_geo", bool(params.get("pack", True)))
    _try_set(n, "createpackedfragments", bool(params.get("packed_fragments", True)))
    if "do_cusp" in params:
        _try_set(n, "doCusp", bool(params["do_cusp"]))
    if "new_name" in params:
        _try_set(n, "newname", bool(params["new_name"]))
    if "connect" in params:
        _try_set(n, "connect", bool(params["connect"]))
    applied["pivot"] = _menu_set(n, "pivot", str(params.get("pivot", "centroid")), _ASSEMBLE_PIVOT)
    if params.get("transfer_attributes") is not None:
        _try_set(n, "transfer_attributes", str(params["transfer_attributes"]))
    if params.get("transfer_groups") is not None:
        _try_set(n, "transfer_groups", str(params["transfer_groups"]))
    if params.get("viewport_lod"):
        applied["viewport_lod"] = _menu_set(n, "viewportlod", str(params["viewport_lod"]), _ASSEMBLE_LOD)
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


_XP_MATCHMODE = ("index", "match")           # attribmode: 0=Index by Attribute, 1=Match by Attribute
_XP_POINTVELS = ("none", "instantaneous", "integrated")  # pointvels: 0/1/2


@endpoint("transform_pieces")
def transform_pieces(params):
    """Apply per-piece transforms from a template point cloud onto packed pieces — THE sim-result ->
    packed-pieces round-trip: input=packed pieces, template=NodePath of the simulated points (each
    carrying `name` + P + `orient`), rest=optional NodePath of the rest points. Pieces are matched to
    template points by the `attrib` id (default 'name'). match_mode: match (match by attribute value,
    default) | index (index by attribute). invert reverses the transform. attribs_to_transform =
    space-sep vector/normal attrs to also rotate (default '*'). point_velocities: none|instantaneous|
    integrated (writes `v` from the piece motion for motion blur; integrate_over_time scales that
    integration window). copy_attribs = space-sep template attrs to copy onto the transformed pieces;
    copy_groups = space-sep template groups to copy. source_group/template_group restrict."""
    n = child_after(params["input"], "xformpieces", params.get("name"))
    if params.get("template"):
        n.setInput(1, _sop_of(params["template"]))
    if params.get("rest"):
        n.setInput(2, _sop_of(params["rest"]))
    applied = {}
    _try_set(n, "attrib", str(params.get("attrib", "name")))
    applied["match_mode"] = _menu_set(n, "attribmode", str(params.get("match_mode", "match")), _XP_MATCHMODE)
    if "invert" in params:
        _try_set(n, "invertxform", bool(params["invert"]))
    if params.get("attribs_to_transform") is not None:
        _try_set(n, "attribstotransform", str(params["attribs_to_transform"]))
    if params.get("point_velocities"):
        pv = str(params["point_velocities"])
        if pv in _XP_POINTVELS:
            _try_set(n, "pointvels", _XP_POINTVELS.index(pv))
            applied["point_velocities"] = pv
    if "integrate_over_time" in params:
        # integrateovertime ships with a default channel expression (1/$FPS); a plain set() leaves the
        # expression in charge, so clear it first, then set the literal window.
        pio = n.parm("integrateovertime")
        if pio is not None:
            try:
                pio.deleteAllKeyframes()
            except Exception:
                pass
        _try_set(n, "integrateovertime", clamp(float(params["integrate_over_time"]), 0.0, 1e6))
    if params.get("copy_attribs") is not None:
        _try_set(n, "docopyattribs", True)
        _try_set(n, "attribstocopy", str(params["copy_attribs"]))
    if params.get("copy_groups") is not None:
        _try_set(n, "docopygroups", True)
        _try_set(n, "groupstocopy", str(params["copy_groups"]))
    if params.get("source_group"):
        _try_set(n, "sourcegroup", str(params["source_group"]))
    if params.get("template_group"):
        _try_set(n, "templategroup", str(params["template_group"]))
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}

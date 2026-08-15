"""SOP Feather lane — the H20+ feather/plumage toolset for wings, birds and plumage.
Data-only handlers, params + menu tokens verified against live H21.0.671 via hython probe.
This is the entire creative feather surface: build a feather
template, groom it across a skin, then style (clump/noise/width/resample/deintersect), deform to an
animated skin, and convert to renderable curves/surface.

Archetypes:
  * `feather_template` is the lane ENTRY / bootstrap — a generator that builds the SideFX authoring
    chain (file default_feather_curves -> feathershapeorg -> feathertemplatefromshape) in a fresh /obj
    geo, so a chat user gets a real feather to style with one call.
  * Every other tool is an OPERATOR: `input` is the feather geometry (input 0); `skin` (input 1) and
    the node-specific extra inputs (templates / target / deformers / ray-geo) are wired cross-network
    via bridge_input.

SECURITY: none of these nodes carry a VEX/Python/callback/command parm (probe-confirmed). The only
file parms present anywhere are optional `*texture` mask overrides — the curated param sets below
deliberately expose NONE of them, so no filesystem surface is reachable through this lane. The one
handler-internal file read is Houdini's own bundled `$HH/geo/default_feather_curves.bgeo` (a trusted
install asset, not user input) used to bootstrap `feather_template`.
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
    if g is None:  # the bootstrap MUST cook — surface the real diagnostic, not an opaque NoneType
        raise RuntimeError(f"{n.path()} failed to cook: " + "; ".join(n.errors()) or "no geometry")
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


def _finish_op(n, **extra):
    """child_after already set the display/render flags + showed the object. Report counts when the
    node has cooked; when it hasn't (a feather op that needs more of the authoring/animation graph
    wired — e.g. template_interpolate / deform / attrib_interpolate), return cooked:false + the node's
    errors instead of crashing, so the AI can keep assembling the network and see what's missing."""
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
# ENTRY / BOOTSTRAP
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("feather_template")
def feather_template(params):
    """Feather Template from Shape — the feather lane's ENTRY point. Builds a single feather template
    in a fresh /obj geo from SideFX's bundled default feather-shape curves (file ->
    feathershapeorg -> feathertemplatefromshape), giving you a ready-to-style condensed feather.
    shaftdensity/barbdensity set how many barbs are generated along the shaft; barbsegs the barb
    resolution; rachiswidthroot/rachiswidthtip taper the central shaft; shapebarbstart where barbs
    begin along the shaft; side (c/l/r) tags the feather side. Feed the result as `input` to the other
    feather_* tools, or scatter it across a skin (scatter -> copy_to_points) for a groom. Fails on
    name collision. Data-only (the shape source is Houdini's own bundled asset)."""
    geo = _fresh_geo(params["name"])
    fsrc = geo.createNode("file", "default_feather_curves")
    fsrc.parm("file").set(hou.expandString("$HH/geo/default_feather_curves.bgeo"))
    org = geo.createNode("feathershapeorg", "shapeorg")
    org.setInput(0, fsrc)
    n = geo.createNode("feathertemplatefromshape", "template")
    n.setInput(0, org)
    _apply(n, params, [
        ("normalize", "normalize", "b", None),
        ("move_to_origin", "movetoorigin", "b", None),
        ("rachis_width_root", "rachiswidthroot", "f", (0.0, 0.1)),
        ("rachis_width_tip", "rachiswidthtip", "f", (0.0, 0.1)),
        ("shape_barb_start", "shapebarbstart", "f", (0.0, 1.0)),
        ("shaft_density", "shaftdensity", "f", (0.0, 1000.0)),
        ("barb_density", "barbdensity", "f", (0.0, 1000.0)),
        ("barb_segs", "barbsegs", "i", (1, 9)),
        ("add_barb_uv", "addbarbuv", "b", None),
    ])
    if "side" in params:
        _try_set(n, "setside", True)
        _str_menu_set(n, "side", str(params["side"]), ("c", "l", "r"))
    return _finish_geo(geo, n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# AUTHORING / GROOM
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("feather_template_assign")
def feather_template_assign(params):
    """Feather Template Assign — assign feather templates onto skin points to seed a groom. `input`
    (curves/feathers) is input 0; `skin` (input 1) carries the points feathers are placed on;
    `templates` (input 3) supplies the feather templates to choose from. seed + use_seed_attrib vary
    which template each point gets; sample_from_weights picks by weight arrays instead of randomly."""
    n = child_after(params["input"], "feathertemplateassign", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("templates"):
        bridge_input(n, params["templates"], index=3, name_hint="templates")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("sample_from_weights", "samplefromweights", "b", None),
        ("seed", "seed", "f", (0.0, 10.0)),
        ("use_seed_attrib", "useseedattrib", "b", None),
    ])
    return _finish_op(n)


@endpoint("feather_template_interpolate")
def feather_template_interpolate(params):
    """Feather Template Interpolate — grow a full groom by interpolating feathers across a skin from a
    sparse set of guide feathers + templates. `input` (guide feathers) is input 0; `skin` (input 1);
    `templates` (input 3). blend controls interpolation strength; lookup_method (group/matchbyattrib/
    weightarrays) how source guides are found; res_mode (constant/adaptive/template) + shaft/barb seg
    controls the output resolution. NOTE: requires a full assign->interpolate authoring graph as
    input (guide source-distribution attribs) — build the groom upstream first."""
    n = child_after(params["input"], "feathertemplateinterpolate", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("templates"):
        bridge_input(n, params["templates"], index=3, name_hint="templates")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("lookup_method", "lookupmethod", "m", ("group", "matchbyattrib", "weightarrays")),
        ("resample", "resample", "b", None),
        ("redistribute", "redistribute", "b", None),
        ("res_mode", "resmode", "m", ("constant", "adaptive", "template")),
        ("shaft_barb_segs", "shaftbarbsegs", "i", (1, 50)),
        ("seg_length", "seglength", "f", (0.0, 1.0)),
        ("res_mult", "resmult", "f", (0.0, 1.0)),
        ("barb_seg_mode", "barbsegmode", "m", ("constant", "template")),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# STYLING
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("feather_clump")
def feather_clump(params):
    """Feather Clump — split and clump barbs to give feathers their characteristic separated, matted
    look. `input` (feathers) is input 0; `skin` optional on input 1. splitfreq/splitjitter/seed
    control where the vane splits; amount (0..1) how strongly barbs pull together; falloff the clump
    profile; splitdepth how far down the shaft splits reach; shift offsets the clump centre."""
    n = child_after(params["input"], "featherclump", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("split_mode", "splitlocmode", "m", ("parms", "attrib")),
        ("split_freq", "splitfreq", "f", (0.0, 100.0)),
        ("split_jitter", "splitjitter", "f", (0.0, 1.0)),
        ("seed", "seed", "f", (0.0, 10.0)),
        ("do_clump", "doclump", "b", None),
        ("amount", "amount", "f", (0.0, 1.0)),
        ("falloff", "falloff", "f", (0.0, 5.0)),
        ("split_depth", "splitdepth", "f", (0.0, 1.0)),
        ("shift", "shift", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("feather_noise")
def feather_noise(params):
    """Feather Noise — add natural noise/break-up to feathers so a groom isn't uniform. `input`
    (feathers) input 0; `skin` optional input 1. amplitude is the master strength; amplitude_normal/
    tangent/bitangent weight the three directions; shaft_offset displaces along the shaft; falloff
    shapes the effect from root to tip; shaft_freq/barb_freq set the noise frequency along shaft/barbs."""
    n = child_after(params["input"], "feathernoise", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("amplitude", "amplitude", "f", (0.0, 0.1)),
        ("amplitude_normal", "amplitudenormal", "f", (0.0, 1.0)),
        ("amplitude_tangent", "amplitudetangent", "f", (0.0, 1.0)),
        ("amplitude_bitangent", "amplitudebitangent", "f", (0.0, 1.0)),
        ("shaft_offset", "shaftoffset", "f", (0.0, 10.0)),
        ("falloff", "falloff", "f", (0.0, 10.0)),
        ("shaft_freq", "shaftfreq", "f", (0.0, 10.0)),
        ("barb_freq", "barbfreq", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("feather_width")
def feather_width(params):
    """Feather Width — set the shaft and barb widths that drive the rendered feather thickness.
    `input` (feathers) input 0; `skin` optional input 1. create_shaft_width + shaft_width control the
    central rachis thickness; create_barb_width + barb_width the individual barb thickness."""
    n = child_after(params["input"], "featherwidth", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("create_shaft_width", "createshaftwidth", "b", None),
        ("shaft_width", "shaftwidth", "f", (0.0, 0.1)),
        ("create_barb_width", "createbarbwidth", "b", None),
        ("barb_width", "barbwidth", "f", (0.0, 0.1)),
    ])
    return _finish_op(n)


@endpoint("feather_resample")
def feather_resample(params):
    """Feather Resample — change the point resolution of feather shafts and barbs (up-res for smooth
    render curves, down-res for a light groom). `input` (feathers) input 0; `skin` optional input 1.
    shaft_resample + shaft_mode (count/length) + shaft_length/shaft_maxsegs resample the shaft;
    resample_barbs + barb_segs the barbs; shaftbase_resample handles the feather base separately."""
    n = child_after(params["input"], "featherresample", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("shaftbase_resample", "shaftbase_resample", "b", None),
        ("shaftbase_mode", "shaftbase_mode", "m", ("count", "length")),
        ("shaftbase_length", "shaftbase_length", "f", (0.0, 5.0)),
        ("shaftbase_maxsegs", "shaftbase_maxsegs", "i", (1, 10)),
        ("shaft_resample", "shaft_resample", "b", None),
        ("shaft_mode", "shaft_mode", "m", ("count", "length")),
        ("shaft_length", "shaft_length", "f", (0.0, 5.0)),
        ("shaft_maxsegs", "shaft_maxsegs", "i", (1, 1000)),
        ("resample_barbs", "resamplebarbs", "b", None),
        ("barb_segs", "barbsegs", "i", (1, 9)),
    ])
    return _finish_op(n)


@endpoint("feather_deintersect")
def feather_deintersect(params):
    """Feather Deintersect — push overlapping feathers apart so a dense groom reads cleanly. `input`
    (feathers) input 0; `skin` optional input 1. iterations + relax/relaxiters + smoothdeform/
    smoothiters drive the separation solve; neighbor_radius the search range; side_cone_angle the
    layering cone; thickness the target gap kept between feathers."""
    n = child_after(params["input"], "featherdeintersect", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("order_mode", "ordermode", "m", ("findneighbors", "layerattrib", "neighborarrays")),
        ("iterations", "iterations", "i", (0, 10)),
        ("smooth_deform", "smoothdeform", "b", None),
        ("smooth_iters", "smoothiters", "i", (0, 20)),
        ("relax", "relax", "b", None),
        ("relax_iters", "relaxiters", "i", (0, 20)),
        ("neighbor_radius", "neighborradius", "f", (0.0, 1.0)),
        ("side_cone_angle", "sideconeangle", "f", (0.0, 90.0)),
        ("thickness", "thickness", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("feather_normalize")
def feather_normalize(params):
    """Feather Normalize — normalize feather attributes into a canonical rest form (move to origin,
    unit length, flatten). `input` (feathers) input 0; `skin` optional input 1. Useful before
    retemplating or attribute transfer."""
    n = child_after(params["input"], "feathernormalize", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("move_to_origin", "movetoorigin", "b", None),
        ("normalize_length", "normalizelength", "b", None),
        ("flatten", "flatten", "b", None),
    ])
    return _finish_op(n)


@endpoint("feather_barb_transform")
def feather_barb_transform(params):
    """Feather Barb Transform — convert barb positions between feather-local space and object space.
    `input` (feathers) input 0; `skin` optional input 1. direction: feathertoobj (bake feather-space
    barbs into world) or objtofeather (recover feather-space from world)."""
    n = child_after(params["input"], "featherbarbxform", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if "direction" in params:
        _menu_set(n, "xform", str(params["direction"]), ("feathertoobj", "objtofeather"))
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFORM / ANIMATE
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("feather_deform")
def feather_deform(params):
    """Feather Deform — capture feathers to a skin and deform them along with an animated skin. `input`
    (geometry to deform) input 0; `skin` (input 1); `rest_deformers` (input 3) + `anim_deformers`
    (input 4) drive the deformation. deformer_type (curve/feather/surface); mode (capturedeform/
    capture/deform); deform_barbs weights how much barbs follow. NOTE: mode capture/deform needs
    matching rest + animated deformer feathers wired — build the rest/anim pair upstream."""
    n = child_after(params["input"], "featherdeform", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("rest_deformers"):
        bridge_input(n, params["rest_deformers"], index=3, name_hint="rest_deformers")
    if params.get("anim_deformers"):
        bridge_input(n, params["anim_deformers"], index=4, name_hint="anim_deformers")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("deformer_type", "deformertype", "m", ("curve", "feather", "surface")),
        ("mode", "mode", "m", ("capturedeform", "capture", "deform")),
        ("treat_deformer_as_subd", "treatdeformerassubd", "b", None),
        ("deform_barbs", "deformbarbs", "f", (0.0, 1.0)),
        ("attribs", "attribs", "s", None),
        ("transfer_vel", "transfervel", "b", None),
        ("rigid_xform", "rigidxform", "b", None),
    ])
    return _finish_op(n)


@endpoint("feather_attrib_interpolate")
def feather_attrib_interpolate(params):
    """Feather Attrib Interpolate — interpolate barb attributes onto feathers from a set of source
    feathers. `input` (feathers) input 0; `source` (source feathers) input 1. barb_attribs names the
    attributes carried over; barb_seg_mode (constant/matchsource) + barb_segs the output barb
    resolution; barb_mirror mirrors left/right barbs. NOTE: needs templatenames/templateweights
    attribs (from feather_template_assign) on the input."""
    n = child_after(params["input"], "featherattribinterpolate", params.get("name"))
    if params.get("source"):
        bridge_input(n, params["source"], index=1, name_hint="source")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("barb_attribs", "barbattribs", "s", None),
        ("shaft_subd", "shaftsubd", "b", None),
        ("shaft_base_segs", "shaftbasesegs", "i", (0, 10)),
        ("barb_seg_mode", "barbsegmode", "m", ("constant", "matchsource")),
        ("barb_segs", "barbsegs", "i", (1, 9)),
        ("barb_mirror", "barbmirror", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# OUTPUT / CONVERT
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("feather_surface")
def feather_surface(params):
    """Feather Surface — build a renderable polygon surface mesh from condensed feathers. `input`
    (feathers) input 0; `skin` optional input 1. shaft_output (none/curve/surface) + shaft_width
    control the central quill; barb_segs_reduce + amount/bias thin distant barb geometry for a lighter
    mesh; create_norm_uv adds normals + UVs. This is the render-ready output of a feather groom."""
    n = child_after(params["input"], "feathersurface", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("create_norm_uv", "createnormuv", "b", None),
        ("shaft_output", "shaftoutput", "m", ("none", "curve", "surface")),
        ("shaft_width", "shaftwidth", "f", (0.0, 1.0)),
        ("shaft_max_width_segments", "shaftmaxwidthsegments", "i", (1, 10)),
        ("barb_segs_reduce", "barbsegsreduce", "b", None),
        ("barb_segs_reduce_amount", "barbsegsreduceamount", "f", (0.0, 1.0)),
        ("barb_segs_reduce_bias", "barbsegsreducebias", "f", (0.0, 3.0)),
    ])
    return _finish_op(n)


@endpoint("feather_surface_blend")
def feather_surface_blend(params):
    """Feather Surface Blend — blend a feather surface toward a target surface (e.g. flatten a wing's
    feathers toward a folded pose). `input` (feathers) input 0; `skin` optional input 1; `target`
    (target surface) input 3. blend (0..1) is the blend weight; iterations the solve passes;
    skin_amount how much the skin constrains the result; resample_shaft/barbs + segs control output res."""
    n = child_after(params["input"], "feathersurfaceblend", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("target"):
        bridge_input(n, params["target"], index=3, name_hint="target")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("iterations", "iterations", "i", (1, 10)),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("skin_amount", "skinamount", "f", (0.0, 1.0)),
        ("resample_shaft", "resampleshaft", "b", None),
        ("shaft_segs", "shaftsegs", "i", (1, 50)),
        ("shaft_barb_segs", "shaftbarbsegs", "i", (1, 50)),
        ("resample_barbs", "resamplebarbs", "b", None),
        ("barb_segs", "barbsegs", "i", (1, 9)),
        ("remesh", "remesh", "b", None),
    ])
    return _finish_op(n)


@endpoint("feather_convert")
def feather_convert(params):
    """Feather Convert — convert condensed feathers into explicit curve or surface geometry. `input`
    (feathers) input 0; `skin` optional input 1. output_type (curves/surface) picks the representation;
    shaft_output (none/curve/surface) + shaft_width the quill; create_norm_uv adds normals + UVs;
    skip_first_n_barb_points trims the barb roots. Lighter-weight than feather_surface for curve output."""
    n = child_after(params["input"], "featherconvert", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("output_type", "outputtype", "m", ("curves", "surface")),
        ("create_norm_uv", "createnormuv", "b", None),
        ("skip_first_n_barb_points", "skipfirstnbarbpoints", "i", (0, 10)),
        ("shaft_output", "shaftoutput", "m", ("none", "curve", "surface")),
        ("shaft_width", "shaftwidth", "f", (0.0, 1.0)),
        ("shaft_max_width_segments", "shaftmaxwidthsegments", "i", (1, 10)),
    ])
    return _finish_op(n)


@endpoint("feather_uncondense")
def feather_uncondense(params):
    """Feather Uncondense — expand a condensed feather (one prim per feather) into full per-barb curve
    geometry. `input` (feathers) input 0; `skin` optional input 1. create_norm_uv adds normals + UVs;
    barb_attrib_sets names attributes promoted to the barbs; create_id tags each barb. Use before ops
    that need explicit per-barb curves."""
    n = child_after(params["input"], "featheruncondense", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("create_norm_uv", "createnormuv", "b", None),
        ("barb_attrib_sets", "barbattribsets", "s", None),
        ("create_shaft_pt_attrib", "createshaftptattrib", "b", None),
        ("create_id", "createid", "b", None),
    ])
    return _finish_op(n)


@endpoint("feather_primitive")
def feather_primitive(params):
    """Feather Primitive — edit the condensed feather primitive representation (resolution + naming).
    `input` (feathers) input 0. shaft_segs/shaft_barb_segs/barb_segs set the stored resolution;
    create_barb_joints adds barb joint points; fallback_name/basename_with_id control feather naming."""
    n = child_after(params["input"], "featherprimitive", params.get("name"))
    _apply(n, params, [
        ("shaft_segs", "shaftsegs", "i", (1, 10)),
        ("shaft_barb_segs", "shaftbarbsegs", "i", (1, 10)),
        ("create_barb_joints", "createbarbjoints", "b", None),
        ("barb_segs", "barbsegs", "i", (1, 9)),
        ("use_basename", "usebasename", "b", None),
        ("fallback_name", "fallbackname", "s", None),
        ("basename_with_id", "basenamewithid", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# UTILITY / ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("feather_barb_tangents")
def feather_barb_tangents(params):
    """Feather Barb Tangents — compute per-barb tangent attributes on feathers (needed by some barb
    styling / shading ops). `input` (feathers) input 0. No parameters — a pure attribute utility."""
    n = child_after(params["input"], "featherbarbtangents", params.get("name"))
    return _finish_op(n)


@endpoint("feather_min_dist")
def feather_min_dist(params):
    """Feather Minimum Distance — compute a minimum-distance attribute between feathers (input 0) and a
    set of target feathers (input 3). `input` (feathers) input 0; `skin` optional input 1; `target`
    (target feathers) input 3. Useful for collision/spacing masks feeding deintersect or scatter."""
    n = child_after(params["input"], "feathermindist", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("target"):
        bridge_input(n, params["target"], index=3, name_hint="target")
    return _finish_op(n)


@endpoint("feather_ray")
def feather_ray(params):
    """Feather Ray — project/ray feathers onto skin or a target geometry, optionally sampling primnum/
    primuv attributes at the hit. `input` (feathers) input 0; `skin` optional input 1; `ray_geo`
    (target geometry) input 3. create_prim_num_attribs/create_prim_uv_attribs record the hit location;
    sample_tex + tex_uv sample a texture-primitive value at the hit (tex_prim names it)."""
    n = child_after(params["input"], "featherray", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("ray_geo"):
        bridge_input(n, params["ray_geo"], index=3, name_hint="ray_geo")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("create_prim_num_attribs", "createprimnumattribs", "b", None),
        ("create_prim_uv_attribs", "createprimuvattribs", "b", None),
        ("sample_tex", "sampletex", "b", None),
        ("tex_uv", "texuv", "s", None),
        ("tex_type", "textype", "m", ("tex", "texprim")),
        ("tex_prim", "texprim", "s", None),
    ])
    return _finish_op(n)


@endpoint("feather_visualize")
def feather_visualize(params):
    """Feather Visualize — generate viewport visualization geometry for feathers (barbs shown as
    curves or a surface). `input` (feathers) input 0; `skin` optional input 1. barb_mode:
    hide/curve/surface. A display aid — does not alter the feather data downstream of it."""
    n = child_after(params["input"], "feathervisualize", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if "barb_mode" in params:
        _menu_set(n, "barbmode", str(params["barb_mode"]), ("hide", "curve", "surface"))
    return _finish_op(n)

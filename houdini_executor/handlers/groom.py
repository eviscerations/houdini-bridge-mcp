"""SOP Groom / Hair / Guide lane — the H20+ hair & fur grooming toolset for skins, guides
and hair curves. Data-only handlers, params + menu tokens verified against live H21.0.671 via hython
probe. This is the scriptable groom surface: generate guides/hairs
on a skin, initialize + style + clump + partition + deform them, build interpolation meshes and
volumes, transfer grooms between skins, and rasterize/hair-card the result for render or realtime.

Input dialect (probe-confirmed, DIFFERS by node):
  * GUIDE OPERATORS take input 0 = Guides, input 1 = Skin (+ node-specific extra inputs).
  * GENERATORS (hairgen, fur) take input 0 = Skin, input 1 = Guides. The primary `input` param always
    maps to whatever the spec calls input 0; the other inputs are exposed as optional NodePath params
    named for what they carry (`skin` / `guides` / `skin_vdb` / `collision_vdb` / `interp_mesh` / ...)
    and bridged at the correct index via bridge_input.
Every handler is an OPERATOR: `input` is input 0, created with child_after; the cross-network extra
inputs are wired with bridge_input. `_finish_op` reports counts once cooked and returns
cooked:false + the node's errors when a node needs more of the network wired (fur / guideadvect /
guidesurface / hairgrowthfield / fibergroom), so the AI can keep assembling instead of crashing.

SECURITY: no VEX/Python/callback/command parm and no file-path parm is exposed by ANY handler in this
lane. The probe found `*texture` mask-override file parms on several nodes (hairgen, guideprocess,
hairclump, guidemask, guidepartition, guidegrowtosurface, guideinterpolationmesh, groomblend,
guidecollidevdb, guideadvect), a `uvreffile` on haircardgen and a `bitmap` on comb — the curated param
tables below deliberately expose NONE of them, so no filesystem surface is reachable. guidegroom::2.0
carries four Python stroke callbacks (callback_startstroke / callback_move / callback_endstroke /
callbacks_enable) — these are EXCLUDED entirely; only its data params are wrapped.
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
    node has cooked; when it hasn't (a groom op that needs more of the guide/skin/VDB network wired —
    e.g. fur / guideadvect / guidesurface / hairgrowthfield / fibergroom), return cooked:false + the
    node's errors instead of crashing, so the AI can keep assembling the network and see what's
    missing."""
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
# GENERATE — scatter + grow guides / hairs on a skin (lane entry)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("hair_generate")
def hair_generate(params):
    """Hair Generate (hairgen::2.0) — THE scriptable hair/guide GENERATOR and lane entry: scatter roots
    on a skin and grow curves, optionally interpolated from a guide set. `input` (input 0) is the Rest
    Skin or Points; `guides` (input 1) an existing guide set to interpolate from; `anim_skin` (input 2)
    an animated skin; `volumes` (input 3); `interp_mesh` (input 4) a guide interpolation mesh. Fed just
    a skin it produces a sparse guide set (lower `density`); fed skin + guides with useguides on it
    grows the dense groom. mode surface/points; count forces an exact hair count when forcecount is on."""
    n = child_after(params["input"], "hairgen::2.0", params.get("name"))
    if params.get("guides"):
        bridge_input(n, params["guides"], index=1, name_hint="guides")
    if params.get("anim_skin"):
        bridge_input(n, params["anim_skin"], index=2, name_hint="anim_skin")
    if params.get("volumes"):
        bridge_input(n, params["volumes"], index=3, name_hint="volumes")
    if params.get("interp_mesh"):
        bridge_input(n, params["interp_mesh"], index=4, name_hint="interp_mesh")
    _apply(n, params, [
        ("mode", "mode", "m", ("surface", "points")),
        ("density", "density", "f", (0.0, 100000.0)),
        ("forcecount", "forcecount", "b", None),
        ("count", "count", "i", (1, 10_000_000)),  # probe range [0,10] is bogus; real default ~100000
        ("useguides", "useguides", "b", None),
        ("influenceradius", "influenceradius", "f", (0.0, 0.2)),
        ("scatterseed", "scatterseed", "f", (0.0, 10.0)),
        ("uniformguidesegments", "uniformguidesegments", "b", None),
        ("skinguidemode", "skinguidemode", "m", ("matchbyguideid", "weightarrays")),
        ("guideblendmethod", "guideblendmethod", "m", ("linearblend", "extrudeblend")),
        ("prune", "prune", "b", None),
        ("pruningratio", "pruningratio", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("fur_setup")
def fur_setup(params):
    """Fur (fur) — the all-in-one legacy Fur generator: generate + clump + part hairs from a skin and
    guides in one node. `input` (input 0) is the Skin; `guides` (input 1) the guide geometry;
    `clump_geo` (input 2) clump geometry; `parting_lines` (input 3) parting-line geometry. segs/length/
    density/seed shape the hairs; guideradius/clumpradius the guide+clump influence; partingradius the
    part width. NOTE: needs matching skin + guide inputs to cook — wire both before expecting geometry."""
    n = child_after(params["input"], "fur", params.get("name"))
    if params.get("guides"):
        bridge_input(n, params["guides"], index=1, name_hint="guides")
    if params.get("clump_geo"):
        bridge_input(n, params["clump_geo"], index=2, name_hint="clump_geo")
    if params.get("parting_lines"):
        bridge_input(n, params["parting_lines"], index=3, name_hint="parting_lines")
    _apply(n, params, [
        ("type", "type", "m", ("poly", "nurbs")),
        ("segs", "segs", "i", (1, 10)),
        ("length", "length", "f", (0.0, 10.0)),
        ("seed", "seed", "i", (0, 10)),
        ("density", "density", "f", (0.0, 1000.0)),
        ("guideradius", "guideradius", "f", (0.0, 10.0)),
        ("clumpradius", "clumpradius", "f", (0.0, 10.0)),
        ("useclosestclump", "useclosestclump", "b", None),
        ("removeunclumpedhairs", "removeunclumpedhairs", "b", None),
        ("removeunguidedhairs", "removeunguidedhairs", "b", None),
        ("partingradius", "partingradius", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("hair_growth_field")
def hair_growth_field(params):
    """Hair Growth Field (hairgrowthfield) — build a hair growth field / scatter guide roots from a
    scalp. `input` (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2); `hair_mask`
    (input 3). guidespacing/guidedensityscale/npts set how densely roots are scattered; relaxiterations
    relaxes them; guideadvectiontype + guideadvectionlength grow the guide curves; outputsegs the
    output resolution. NOTE: its internal foreach needs a Skin VDB to cook — wire `skin_vdb` first."""
    n = child_after(params["input"], "hairgrowthfield", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    if params.get("hair_mask"):
        bridge_input(n, params["hair_mask"], index=3, name_hint="hair_mask")
    _apply(n, params, [
        ("guidespacing", "guidespacing", "f", (0.0, 1.0)),
        ("guidedensityscale", "guidedensityscale", "f", (0.0, 10.0)),
        ("npts", "npts", "i", (1, 100000)),
        ("forcetotal", "forcetotal", "b", None),
        ("relaxiterations", "relaxiterations", "i", (0, 100)),
        ("guideradius", "guideradius", "f", (0.0, 10.0)),
        ("scalpnormalforce", "scalpnormalforce", "f", (0.0, 1.0)),
        ("guideadvectiontype", "guideadvectiontype", "ms",
         ("fwd euler", "2nd rk", "3rd rk", "4th rk")),  # menu stored by STRING token
        ("guideadvectionlength", "guideadvectionlength", "f", (0.0, 10.0)),
        ("outputsegs", "outputsegs", "i", (1, 50)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GUIDE INITIALIZE / RESAMPLE / FILL
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("guide_initialize")
def guide_initialize(params):
    """Guide Initialize (guideinit) — orient freshly-created guides (wind shape, lift, along-skin
    blend). `input` (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2). windamount +
    winddirx/y/z bend the guides like wind; alongskin blends them along the skin; uvblend/uvrot align
    to skin UVs; lift raises them off the surface."""
    n = child_after(params["input"], "guideinit", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    _apply(n, params, [
        ("windamount", "windamount", "f", (0.0, 5.0)),
        ("winddirx", "winddirx", "f", (-1.0, 1.0)),
        ("winddiry", "winddiry", "f", (-1.0, 1.0)),
        ("winddirz", "winddirz", "f", (-1.0, 1.0)),
        ("alongskin", "alongskin", "f", (0.0, 1.0)),
        ("uvblend", "uvblend", "f", (0.0, 1.0)),
        ("uvrot", "uvrot", "f", (-180.0, 180.0)),
        ("lift", "lift", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("guide_reguide")
def guide_reguide(params):
    """Reguide (reguide) — redistribute / resample the guide set (change guide density and segment
    count). `input` (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2). densityscale
    scales the guide count; segments the per-guide resolution; relaxpoints + relaxiterations even out
    the roots; maxsourceguides + bias control how source guides are blended into the new ones."""
    n = child_after(params["input"], "reguide", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    _apply(n, params, [
        ("densityscale", "densityscale", "f", (0.1, 1000.0)),
        ("segments", "segments", "i", (0, 10)),
        ("usedensityattrib", "usedensityattrib", "b", None),
        ("relaxpoints", "relaxpoints", "b", None),
        ("relaxiterations", "relaxiterations", "i", (0, 100)),
        ("rootsonly", "rootsonly", "b", None),
        ("maxsourceguides", "maxsourceguides", "i", (1, 20)),
        ("bias", "bias", "f", (0.0, 5.0)),
    ])
    return _finish_op(n)


@endpoint("guide_fill")
def guide_fill(params):
    """Guide Fill (guidefill) — fill gaps in a sparse guide set using a guide interpolation mesh.
    `input` (input 0) is the Guides; `interp_mesh` (input 1) the guide interpolation mesh. indexattrib/
    weightattrib name the interpolation arrays; boostlong + boostlongbias bias the fill toward longer
    guides. Pair with guide_interpolation_mesh upstream."""
    n = child_after(params["input"], "guidefill", params.get("name"))
    if params.get("interp_mesh"):
        bridge_input(n, params["interp_mesh"], index=1, name_hint="interp_mesh")
    _apply(n, params, [
        ("guidepointsgroup", "guidepointsgroup", "s", None),
        ("indexattrib", "indexattrib", "s", None),
        ("weightattrib", "weightattrib", "s", None),
        ("boostlong", "boostlong", "f", (0.0, 1.0)),
        ("boostlongbias", "boostlongbias", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("guide_grow_to_surface")
def guide_grow_to_surface(params):
    """Guide Grow to Surface (guidegrowtosurface) — grow guide roots out to a target surface (advect
    source points onto a mesh). `input` (input 0) is the Source Points; `target_surface` (input 1) the
    mesh to grow onto. iterations/stepsize/threshold/tolerance drive the advection solve; blend the
    result strength; length the grown guide length; advectalongsurface hugs the surface, flipvel
    reverses the direction."""
    n = child_after(params["input"], "guidegrowtosurface", params.get("name"))
    if params.get("target_surface"):
        bridge_input(n, params["target_surface"], index=1, name_hint="target_surface")
    _apply(n, params, [
        ("iterations", "iterations", "i", (1, 100)),
        ("stepsize", "stepsize", "f", (0.0, 1.0)),
        ("threshold", "threshold", "f", (0.0, 1.0)),
        ("tolerance", "tolerance", "f", (0.0, 1.0)),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("length", "length", "f", (0.0, 1.0)),
        ("advectalongsurface", "advectalongsurface", "b", None),
        ("flipvel", "flipvel", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GUIDE STYLE / CLUMP / PARTITION
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("guide_process")
def guide_process(params):
    """Guide Process (guideprocess) — the primary guide STYLING op-stack: pick a single operation with
    `op1` (set direction/lift/length, displace, make wavy, straighten, smooth, frizz, bend, sim attrib).
    `input` (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2). geotype1 curves/barbs;
    blend the op strength; seed for randomized ops; grouptype+group restrict it; the useskinmask/
    usecurvemask/usenoisemask toggles gate the effect by mask (noisemaskamount weights the noise mask)."""
    n = child_after(params["input"], "guideprocess", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    _apply(n, params, [
        ("op1", "op1", "m", ("setdirvec", "setlift", "setlength", "displace", "makewavy",
                             "straighten", "smooth", "frizz", "bend", "simattrib")),
        ("geotype1", "geotype1", "m", ("curves", "barbs")),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("seed", "seed", "f", (0.0, 10.0)),
        ("grouptype", "grouptype", "m", ("primitive", "point", "edge")),
        ("group", "group", "s", None),
        ("curveperskinpoint", "curveperskinpoint", "b", None),
        ("useskinmask", "useskinmask", "b", None),
        ("usecurvemask", "usecurvemask", "b", None),
        ("usenoisemask", "usenoisemask", "b", None),
        ("noisemaskamount", "noisemaskamount", "f", (0.0, 1.0)),
        ("legacymasking", "legacymasking", "b", None),
    ])
    return _finish_op(n)


@endpoint("hair_clump")
def hair_clump(params):
    """Hair Clump (hairclump::2.0) — clump hairs/guides into strands (the signature hair look). `input`
    (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2); `clump_curves` (input 3) optional
    custom clump curves. blend the clump strength; clumpsize the clump radius; crossoverrate lets hairs
    hop between clumps; seed randomizes membership; method the blend model; clumpwithinclumps nests
    sub-clumps; extendtomatch lengthens hairs to reach the clump tip."""
    n = child_after(params["input"], "hairclump::2.0", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    if params.get("clump_curves"):
        bridge_input(n, params["clump_curves"], index=3, name_hint="clump_curves")
    _apply(n, params, [
        ("blend", "blend", "f", (0.0, 1.0)),
        ("blendoptions", "blendoptions", "m", ("fit", "ramp")),
        ("clumpsize", "clumpsize", "f", (0.0, 1.0)),  # probe max 0.1 clips the 0.15 default; widened
        ("clumpsizeoptions", "clumpsizeoptions", "m", ("fit", "ramp")),
        ("crossoverrate", "crossoverrate", "f", (0.0, 1.0)),
        ("seed", "seed", "f", (0.0, 10.0)),
        ("method", "method", "m", ("linearblend", "extrudeblend")),
        ("preservelength", "preservelength", "b", None),
        ("searchbeyondradius", "searchbeyondradius", "b", None),
        ("clumpwithinclumps", "clumpwithinclumps", "b", None),
        ("extendtomatch", "extendtomatch", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("guide_clump_center")
def guide_clump_center(params):
    """Guide Clump Center (guideclumpcenter) — compute clump-center guides/attribs that feed hair_clump.
    `input` (input 0) is the Guides. outputnormalattrib + normalattrib author a per-center normal;
    outputradiusattrib + radiusattrib a per-center radius (pscale). A pre-pass for custom clumping."""
    n = child_after(params["input"], "guideclumpcenter", params.get("name"))
    _apply(n, params, [
        ("outputnormalattrib", "outputnormalattrib", "b", None),
        ("normalattrib", "normalattrib", "s", None),
        ("outputradiusattrib", "outputradiusattrib", "b", None),
        ("radiusattrib", "radiusattrib", "s", None),
    ])
    return _finish_op(n)


@endpoint("guide_partition")
def guide_partition(params):
    """Guide Partition (guidepartition) — create parting lines that split the groom into partition
    regions. `input` (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2); `parting_lines`
    (input 3) optional explicit parting-line geometry. partingradius the part width; partingstrength
    how hard the part pushes; the *override menus pick where radius/strength come from (none/skinattrib/
    texture — texture override NOT exposed as a file here); resample + resampleseglength retessellate."""
    n = child_after(params["input"], "guidepartition", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    if params.get("parting_lines"):
        bridge_input(n, params["parting_lines"], index=3, name_hint="parting_lines")
    _apply(n, params, [
        ("partingradius", "partingradius", "f", (0.0, 1.0)),
        ("partingradiusoverride", "partingradiusoverride", "m", ("none", "skinattrib", "texture")),
        ("partingstrength", "partingstrength", "f", (0.0, 1.0)),
        ("partingstrengthoverride", "partingstrengthoverride", "m", ("none", "skinattrib", "texture")),
        ("resample", "resample", "b", None),
        ("resampleseglength", "resampleseglength", "f", (0.01, 0.1)),
    ])
    return _finish_op(n)


@endpoint("guide_groom")
def guide_groom(params):
    """Guide Groom (guidegroom::2.0) — the brush groomer's data node. Headless it applies its
    straighten/relax/smooth/lift settings across the groom (no interactive strokes). `input` (input 0)
    is the Guides; `skin` (input 1); `skin_vdb` (input 2). strandmode grooms strands vs curves;
    collidewithskin keeps hairs off the surface; usemask gates by mask; the *strength params weight
    each brush op and liftangle sets the lift target. SECURITY: its Python stroke callbacks are NOT
    exposed."""
    n = child_after(params["input"], "guidegroom::2.0", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("strandmode", "strandmode", "b", None),
        ("collidewithskin", "collidewithskin", "b", None),
        ("usemask", "usemask", "b", None),
        ("straightenstrength", "straightenstrength", "f", (0.0, 1.0)),
        ("relaxstrength", "relaxstrength", "f", (0.0, 1.0)),
        ("smoothstrength", "smoothstrength", "f", (0.0, 1.0)),
        ("liftstrength", "liftstrength", "f", (0.0, 1.0)),
        ("liftangle", "liftangle", "f", (0.0, 90.0)),
        ("spacing", "spacing", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("hair_comb")
def hair_comb(params):
    """Comb (comb) — comb fur/hair direction. Designed as a viewport brush, headless it applies its
    op/lift settings globally. `input` (input 0) is the geometry to comb. op picks the action
    (comb/smoothnml/erase/lift/rotate); lift raises the hairs; preservenml/ovrnml + nmlname control
    the normal it writes; rad/opacity/softedge shape the brush footprint. SECURITY: the `bitmap` file
    parm is NOT exposed."""
    n = child_after(params["input"], "comb", params.get("name"))
    _apply(n, params, [
        ("op", "op", "m", ("comb", "smoothnml", "erase", "lift", "rotate")),
        ("lift", "lift", "f", (-1.0, 1.0)),
        ("preservenml", "preservenml", "b", None),
        ("ovrnml", "ovrnml", "b", None),
        ("nmlname", "nmlname", "s", None),
        ("rad", "rad", "f", (0.0, 1.0)),
        ("opacity", "opacity", "f", (0.0, 1.0)),
        ("softedge", "softedge", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GUIDE MASK / GROUP / STRAYS / LOOKUP / TANGENT SPACE
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("guide_mask")
def guide_mask(params):
    """Guide Mask (guidemask) — author masks (attrib/group) on guides/skin that every other groom op
    reads. `input` (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2); `masking_geo`
    (input 3) optional geometry to mask from. inputmask the base value; outattribtype prim/point +
    outattrib name the output; zeroungrouped clears ungrouped elements; grouptype + createprimgroup
    emit a group; the noisemask* params add a procedural noise mask. SECURITY: no texture file parm."""
    n = child_after(params["input"], "guidemask", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    if params.get("masking_geo"):
        bridge_input(n, params["masking_geo"], index=3, name_hint="masking_geo")
    _apply(n, params, [
        ("inputmask", "inputmask", "f", (0.0, 1.0)),
        ("outattribtype", "outattribtype", "m", ("prim", "point")),
        ("outattrib", "outattrib", "s", None),
        ("zeroungrouped", "zeroungrouped", "b", None),
        ("grouptype", "grouptype", "m", ("primitive", "point", "edge")),
        ("createprimgroup", "createprimgroup", "b", None),
        ("usenoisemask", "usenoisemask", "b", None),
        ("noisemaskamount", "noisemaskamount", "f", (0.0, 1.0)),
        ("noisemaskfreq", "noisemaskfreq", "f", (0.0, 100.0)),
        ("noisemaskgain", "noisemaskgain", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("guide_group")
def guide_group(params):
    """Guide Group (guidegroup) — create guide / parting-line groups by naming convention. `input`
    (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2). guidesgroup names the group for
    the guides; partinglinesgroup the group for parting lines."""
    n = child_after(params["input"], "guidegroup", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    _apply(n, params, [
        ("guidesgroup", "guidesgroup", "s", None),
        ("partinglinesgroup", "partinglinesgroup", "s", None),
    ])
    return _finish_op(n)


@endpoint("guide_find_strays")
def guide_find_strays(params):
    """Guide Find Strays (guidefindstrays) — detect stray/outlier guides and tag them in a group/attrib.
    `input` (input 0) is the Guides. refdist_mode individual/percentile picks the reference distance;
    rootdistpercentile/mindistmult/maxdistmult/thresh set the outlier thresholds; createprimgroup +
    outprimgroup emit the strays group; propagate + propagation spread the tag along guides."""
    n = child_after(params["input"], "guidefindstrays", params.get("name"))
    _apply(n, params, [
        ("refdist_mode", "refdist_mode", "m", ("individual", "percentile")),
        ("rootdistpercentile", "rootdistpercentile", "f", (0.0, 1.0)),
        ("mindistmult", "mindistmult", "f", (1.0, 10.0)),
        ("maxdistmult", "maxdistmult", "f", (1.0, 10.0)),
        ("thresh", "thresh", "f", (0.0, 1.0)),
        ("createprimgroup", "createprimgroup", "b", None),
        ("outprimgroup", "outprimgroup", "s", None),
        ("propagate", "propagate", "b", None),
        ("propagation", "propagation", "m",
         ("forwardmin", "forwardmax", "backwardmin", "backwardmax")),
    ])
    return _finish_op(n)


@endpoint("guide_skin_attrib_lookup")
def guide_skin_attrib_lookup(params):
    """Guide Skin Attribute Lookup (guideskinattriblookup) — copy skin attributes onto guides via the
    stored skinprim/skinprimuv rooting. `input` (input 0) is the Guides; `skin` (input 1). primnumattrib
    /primuvwattrib name the rooting attribs; userest looks up on the rest skin; pointattribs/vertattribs
    /primattribs/detailattribs name the skin attributes copied onto each guide."""
    n = child_after(params["input"], "guideskinattriblookup", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("primnumattrib", "primnumattrib", "s", None),
        ("primuvwattrib", "primuvwattrib", "s", None),
        ("userest", "userest", "b", None),
        ("pointattribs", "pointattribs", "s", None),
        ("vertattribs", "vertattribs", "s", None),
        ("primattribs", "primattribs", "s", None),
        ("detailattribs", "detailattribs", "s", None),
    ])
    return _finish_op(n)


@endpoint("guide_tangent_space")
def guide_tangent_space(params):
    """Guide Tangent Space (guidetangentspace) — compute per-guide tangent/normal/bitangent/orient
    frames needed by the direction ops. `input` (input 0) is the Guides; `skin` (input 1). normalmode
    picks the up-vector source (guidenormal/skintangent/skinuv/vector); userest works in rest space;
    skintangentattrib/skinuvattrib name the skin inputs; the output* toggles + *name params choose which
    frames are written."""
    n = child_after(params["input"], "guidetangentspace", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("normalmode", "normalmode", "m", ("guidenormal", "skintangent", "skinuv", "vector")),
        ("userest", "userest", "b", None),
        ("skintangentattrib", "skintangentattrib", "s", None),
        ("skinuvattrib", "skinuvattrib", "s", None),
        ("outputnormal", "outputnormal", "b", None),
        ("normalname", "normalname", "s", None),
        ("outputtangent", "outputtangent", "b", None),
        ("tangentname", "tangentname", "s", None),
        ("outputbitangent", "outputbitangent", "b", None),
        ("outputorient", "outputorient", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# GUIDE INTERPOLATION MESH / VOLUME / SURFACE
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("guide_interpolation_mesh")
def guide_interpolation_mesh(params):
    """Guide Interpolation Mesh (guideinterpolationmesh) — build the interpolation mesh (remeshed skin +
    guide weights) that hair_generate uses to interpolate guides. `input` (input 0) is the Guides;
    `skin` (input 1); `masks` (input 3). remesh + remeshmode/remeshiterations/relmeshsize retessellate
    the skin; useminsize/minsize + usemaxsize/maxsize clamp the mesh size; computeweights + maxiter/
    solvetol solve the per-point guide weights. SECURITY: the masktexture file parm is NOT exposed."""
    n = child_after(params["input"], "guideinterpolationmesh", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("masks"):
        bridge_input(n, params["masks"], index=3, name_hint="masks")
    _apply(n, params, [
        ("remesh", "remesh", "b", None),
        ("remeshmode", "remeshmode", "m", ("uniform", "adaptive")),
        ("remeshiterations", "remeshiterations", "i", (0, 10)),
        ("relmeshsize", "relmeshsize", "f", (0.0, 2.0)),
        ("useminsize", "useminsize", "b", None),
        ("minsize", "minsize", "f", (0.0, 0.1)),
        ("usemaxsize", "usemaxsize", "b", None),
        ("maxsize", "maxsize", "f", (0.0, 0.1)),
        ("computeweights", "computeweights", "b", None),
        ("maxiter", "maxiter", "i", (0, 30)),
        ("solvetol", "solvetol", "f", (0.0, 0.1)),
    ])
    return _finish_op(n)


@endpoint("guide_volume")
def guide_volume(params):
    """Guide Volume (guidevolume) — build the guide/skin volume representation (cross-sections / shell /
    remesh / tets, optional VDB) that many groom ops consume. `input` (input 0) is the Guides; `skin`
    (input 1). output picks the representation; resamplecurves + curveseglength resample the guides;
    minradius/iterations/flattencs/smoothcs shape the cross-sections; vdb + vdbrelvoxelsize emit a VDB;
    tettargetsize the tet size."""
    n = child_after(params["input"], "guidevolume", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    _apply(n, params, [
        ("output", "output", "m", ("crosssections", "shell", "remesh", "tets")),
        ("resamplecurves", "resamplecurves", "b", None),
        ("curveseglength", "curveseglength", "f", (0.0, 10.0)),
        ("minradius", "minradius", "f", (0.0, 10.0)),
        ("iterations", "iterations", "i", (0, 10)),
        ("flattencs", "flattencs", "f", (0.0, 1.0)),
        ("smoothcs", "smoothcs", "b", None),
        ("vdb", "vdb", "b", None),
        ("vdbrelvoxelsize", "vdbrelvoxelsize", "f", (0.0, 10.0)),
        ("tettargetsize", "tettargetsize", "f", (0.0, 0.1)),
    ])
    return _finish_op(n)


@endpoint("guide_surface")
def guide_surface(params):
    """Guide Surface (guidesurface) — move/build a surface from guides along a guide interpolation mesh.
    `input` (input 0) is the Guides; `interp_mesh` (input 1) the guide interpolation mesh (needed to
    cook). movemode absolute/relative/xform; curveloc + usecurvelocattrib/curvelocattrib/
    normalizecurveloc pick the along-curve sample; indexattrib/weightattrib name the interpolation
    arrays."""
    n = child_after(params["input"], "guidesurface", params.get("name"))
    if params.get("interp_mesh"):
        bridge_input(n, params["interp_mesh"], index=1, name_hint="interp_mesh")
    _apply(n, params, [
        ("movemode", "movemode", "m", ("absolute", "relative", "xform")),
        ("curveloc", "curveloc", "f", (0.0, 1.0)),
        ("usecurvelocattrib", "usecurvelocattrib", "b", None),
        ("curvelocattrib", "curvelocattrib", "s", None),
        ("normalizecurveloc", "normalizecurveloc", "b", None),
        ("indexattrib", "indexattrib", "s", None),
        ("weightattrib", "weightattrib", "s", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFORM / TRANSFER / BLEND / COLLIDE / ADVECT
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("guide_deform")
def guide_deform(params):
    """Guide Deform (guidedeform) — capture guides to a skin and deform them with an animated skin.
    `input` (input 0) is the Geometry to Deform; `rest_skin` (input 1); `anim_skin` (input 2);
    `rest_guides` (input 3); `anim_guides` (input 4). mode skin/capturedeform/capture/deform; method
    the weighting scheme; guidecoverage how many guides drive each point; computeradius/radius the
    capture range; limitguidesegs/maxguidesegs cap the guide influence; inputtype hair/geo;
    rigidtransform keeps captured geo rigid."""
    n = child_after(params["input"], "guidedeform", params.get("name"))
    if params.get("rest_skin"):
        bridge_input(n, params["rest_skin"], index=1, name_hint="rest_skin")
    if params.get("anim_skin"):
        bridge_input(n, params["anim_skin"], index=2, name_hint="anim_skin")
    if params.get("rest_guides"):
        bridge_input(n, params["rest_guides"], index=3, name_hint="rest_guides")
    if params.get("anim_guides"):
        bridge_input(n, params["anim_guides"], index=4, name_hint="anim_guides")
    _apply(n, params, [
        ("mode", "mode", "m", ("skin", "capturedeform", "capture", "deform")),
        ("method", "method", "m", ("pointweights", "existingweights", "barycentricweights")),
        ("splitclumps", "splitclumps", "b", None),
        ("singleguide", "singleguide", "b", None),
        ("guidecoverage", "guidecoverage", "i", (1, 10)),
        ("computeradius", "computeradius", "b", None),
        ("radius", "radius", "f", (0.0, 10.0)),
        ("limitguidesegs", "limitguidesegs", "b", None),
        ("maxguidesegs", "maxguidesegs", "i", (1, 10)),
        ("inputtype", "inputtype", "m", ("hair", "geo")),
        ("rigidtransform", "rigidtransform", "b", None),
    ])
    return _finish_op(n)


@endpoint("guide_transfer")
def guide_transfer(params):
    """Guide Transfer (guidetransfer) — transfer a groom from a source skin to a target skin. `input`
    (input 0) is the Guides; `source_skin` (input 1); `target_skin` (input 2). matchmethod direct/uv;
    uvattribclass + uvattrib name the UV to match by; setguideorigin re-roots the guides; doxformattribs
    + xformattribs transform vector attributes; deform + pointdeform_radius blend a point-deform onto
    the target."""
    n = child_after(params["input"], "guidetransfer", params.get("name"))
    if params.get("source_skin"):
        bridge_input(n, params["source_skin"], index=1, name_hint="source_skin")
    if params.get("target_skin"):
        bridge_input(n, params["target_skin"], index=2, name_hint="target_skin")
    _apply(n, params, [
        ("matchmethod", "matchmethod", "m", ("direct", "uv")),
        ("uvattribclass", "uvattribclass", "m", ("point", "vertex")),
        ("uvattrib", "uvattrib", "s", None),
        ("setguideorigin", "setguideorigin", "b", None),
        ("doxformattribs", "doxformattribs", "b", None),
        ("xformattribs", "xformattribs", "s", None),
        ("deform", "deform", "f", (0.0, 1.0)),
        ("pointdeform_radius", "pointdeform_radius", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("groom_blend")
def groom_blend(params):
    """Groom Blend (groomblend) — blend two full grooms (guides A vs guides B) by weight/mask. `input`
    (input 0) is Guides A; `skin_a` (input 1); `skin_vdb` (input 2); `guides_b` (input 3); `skin_b`
    (input 4). blend the A->B weight; blendoverride where the weight comes from (none/curveattrib/
    skinattrib/texture — texture file NOT exposed); matchprimsbyattrib + matchprimsattrib pair up
    guides; pointinterp + guidepointattribs/guideprimattribs pick which attributes blend."""
    n = child_after(params["input"], "groomblend", params.get("name"))
    if params.get("skin_a"):
        bridge_input(n, params["skin_a"], index=1, name_hint="skin_a")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    if params.get("guides_b"):
        bridge_input(n, params["guides_b"], index=3, name_hint="guides_b")
    if params.get("skin_b"):
        bridge_input(n, params["skin_b"], index=4, name_hint="skin_b")
    _apply(n, params, [
        ("grouptype", "grouptype", "m", ("primitive", "point", "edge")),
        ("group", "group", "s", None),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("blendoverride", "blendoverride", "m", ("none", "curveattrib", "skinattrib", "texture")),
        ("matchprimsbyattrib", "matchprimsbyattrib", "b", None),
        ("matchprimsattrib", "matchprimsattrib", "s", None),
        ("pointinterp", "pointinterp", "b", None),
        ("guidepointattribs", "guidepointattribs", "s", None),
        ("guideprimattribs", "guideprimattribs", "s", None),
    ])
    return _finish_op(n)


@endpoint("guide_collide_vdb")
def guide_collide_vdb(params):
    """Guide Collide With VDB (guidecollidevdb) — push guides out of a collision VDB. `input` (input 0)
    is the Guides; `skin` (input 1); `skin_vdb` (input 2); `collision_vdb` (input 3) the additional
    collision VDBs. blend the correction strength; collidewithskin also pushes off the skin; isooffset
    the collision iso; pushrange/pushamount the push; useskinmask/usecurvemask gate it by mask.
    SECURITY: the skinmasktexture file parm is NOT exposed."""
    n = child_after(params["input"], "guidecollidevdb", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    if params.get("collision_vdb"):
        bridge_input(n, params["collision_vdb"], index=3, name_hint="collision_vdb")
    _apply(n, params, [
        ("blend", "blend", "f", (0.0, 1.0)),
        ("collidewithskin", "collidewithskin", "b", None),
        ("isooffset", "isooffset", "f", (0.0, 1.0)),
        ("pushrange", "pushrange", "f", (0.0, 1.0)),
        ("pushamount", "pushamount", "f", (0.0, 1.0)),
        ("useskinmask", "useskinmask", "b", None),
        ("usecurvemask", "usecurvemask", "b", None),
    ])
    return _finish_op(n)


@endpoint("guide_advect")
def guide_advect(params):
    """Guide Advect (guideadvect) — advect guides through a velocity VDB or fill collisions. `input`
    (input 0) is the Guides; `skin` (input 1); `skin_vdb` (input 2); `velocity_vdb` (input 3) the
    velocity & collision VDB (REQUIRED to cook). operation advect/fillcoll/fillvel; blend the strength;
    followskin keeps roots on the skin; samplingquality the VDB sample rate; segmode/seglength the
    output resolution; stoponcoll/limitlength/length bound the advection. SECURITY: no texture file
    parm exposed."""
    n = child_after(params["input"], "guideadvect", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("skin_vdb"):
        bridge_input(n, params["skin_vdb"], index=2, name_hint="skin_vdb")
    if params.get("velocity_vdb"):
        bridge_input(n, params["velocity_vdb"], index=3, name_hint="velocity_vdb")
    _apply(n, params, [
        ("operation", "operation", "m", ("advect", "fillcoll", "fillvel")),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("followskin", "followskin", "b", None),
        ("samplingquality", "samplingquality", "f", (0.1, 2.0)),
        ("segmode", "segmode", "m", ("input", "adaptive")),
        ("seglength", "seglength", "f", (0.0, 0.1)),
        ("stoponcoll", "stoponcoll", "b", None),
        ("limitlength", "limitlength", "b", None),
        ("length", "length", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# OUTPUT / CONVERT — hair cards + VDB rasterize
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("hair_card_generate")
def hair_card_generate(params):
    """Hair Card Generate (haircardgen) — generate textured hair CARDS (game / realtime output) from
    hair curves. `input` (input 0) is the Hair Curves; `skin` (input 1); `cluster_points` (input 2);
    `normal_override` (input 3). numcards + clusterseed cluster the curves into cards; width/widthmethod
    /widthscale/widthdivs size the cards; lengthdivmethod + lengthuniformdivs the lengthwise
    resolution; uvenable/snaproots/orientsmooth/mincurvelength finish them. SECURITY: uvreffile NOT
    exposed."""
    n = child_after(params["input"], "haircardgen", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("cluster_points"):
        bridge_input(n, params["cluster_points"], index=2, name_hint="cluster_points")
    if params.get("normal_override"):
        bridge_input(n, params["normal_override"], index=3, name_hint="normal_override")
    _apply(n, params, [
        ("numcards", "numcards", "i", (1, 1000)),
        ("clusterseed", "clusterseed", "i", (0, 200)),
        ("width", "width", "f", (0.0, 1.0)),
        ("widthmethod", "widthmethod", "m", ("specify", "compute")),
        ("widthscale", "widthscale", "f", (0.1, 3.0)),
        ("widthdivs", "widthdivs", "i", (0, 50)),
        ("lengthdivmethod", "lengthdivmethod", "m", ("uniform", "seglength", "refine")),
        ("lengthuniformdivs", "lengthuniformdivs", "i", (1, 50)),
        ("uvenable", "uvenable", "b", None),
        ("snaproots", "snaproots", "b", None),
        ("orientsmooth", "orientsmooth", "b", None),
        ("mincurvelength", "mincurvelength", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("hair_volume_rasterize")
def hair_volume_rasterize(params):
    """Volume Rasterize Hair (volumerasterizehair) — rasterize hair curves into a density/color/tangent
    VDB (render / sim prep). `input` (input 0) is the Curves to Rasterize. voxelsize the VDB resolution;
    samplingquality the sample rate; densityscale/widthscale scale the deposited density; rasterizetangent
    + tangentvoxelscale and rasterizecolor + colorvoxelscale add tangent/color VDBs; velocityblur
    none/field/rasterize adds motion blur."""
    n = child_after(params["input"], "volumerasterizehair", params.get("name"))
    _apply(n, params, [
        ("voxelsize", "voxelsize", "f", (0.0, 1.0)),
        ("samplingquality", "samplingquality", "f", (0.0, 10.0)),
        ("densityscale", "densityscale", "f", (0.0, 10.0)),
        ("widthscale", "widthscale", "f", (0.0, 10.0)),
        ("rasterizetangent", "rasterizetangent", "b", None),
        ("tangentvoxelscale", "tangentvoxelscale", "f", (1.0, 10.0)),
        ("rasterizecolor", "rasterizecolor", "b", None),
        ("colorvoxelscale", "colorvoxelscale", "f", (1.0, 10.0)),
        ("velocityblur", "velocityblur", "m", ("none", "field", "rasterize")),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SEPARATE LANE — muscle-fiber grooming (KineFX)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("fiber_groom")
def fiber_groom(params):
    """Fiber Groom (fibergroom) — muscle-FIBER grooming (KineFX muscle lane, not hair). `input`
    (input 0) is the Muscles; `curves` (input 1) optional guide curves. group restricts it; pieceid
    names the muscle pieces; fiberflow + fiberguidescale shape the fiber flow; enableaxialcorrection
    aligns fibers to the muscle axis; usesymmetry mirrors the groom. NOTE: needs a Muscles input to
    cook (belongs to the muscle lane)."""
    n = child_after(params["input"], "fibergroom", params.get("name"))
    if params.get("curves"):
        bridge_input(n, params["curves"], index=1, name_hint="curves")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("pieceid", "pieceid", "s", None),
        ("fiberflow", "fiberflow", "b", None),
        ("fiberguidescale", "fiberguidescale", "f", (0.0, 1.0)),
        ("enableaxialcorrection", "enableaxialcorrection", "b", None),
        ("usesymmetry", "usesymmetry", "b", None),
    ])
    return _finish_op(n)

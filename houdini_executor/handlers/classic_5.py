"""KineFX / Classic muscle-skin finish — data-only handlers.

Most of the remaining ClassicRig nodes are
redundant with a tool already shipped elsewhere (skin loft, pointdeform, path_deform, the
pose-space combine/configure halves, straight_skeleton_2d/3d, the DemBones writers, the biharmonic
capture lane) or are out-of-lane shader VOPs / uncookable-without-authored-assets. Only three nodes are a
genuinely-new, safe, cookable data-only capability and are wrapped here:

  * skin_properties (skinproperties)   — B chain, in0 = skin geo. Authors per-point muscle/skin SOLVER
        property attributes (surface / solid stiffness, damping, mass-density, sliding-rate ...) plus a
        `preset`. Pure attribute authoring; cooks green and writes the enabled property attribs.
  * skin_solidify  (skinsolidify::2.0) — B chain, in0 = skin surface. Builds a layered solid tet shell
        (thickness / layers / element-sizing / density) around a skin mesh for FEM/cloth-style skin sim.
        Distinct from `bone_solidify` (bonesolidify, single-solid bone-FEM tet). Sizing levers clamped.
  * skin_deform    (skindeform)        — B chain, in0 = skin. Muscle-aware skin finishing: muscle-blur
        weight smoothing + skin-sliding relaxation over a reference frame. Distinct from the
        bone/joint/skeleton deform lane.

Verified against live H21.0.671; every endpoint proven with a headless
cook over the reusable fixture.

SECURITY (data-only): no code/callback parm is ever set or exposed. These three nodes carry NO code parm
and NO file parm (all controls are attribute names / numeric values / benign ordered menus), so there is
no `confined_path` surface in this lane. The `kerneltype` "code"-keyword hits elsewhere in the tail are
benign RBF-kernel ordered MENUS on nodes that are not wrapped anyway, and are never referenced here. The
cost-exponential skin_solidify element-sizing / iteration levers are hard-clamped.
"""

import hou
from houdini_executor.server import clamp, child_after, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────




def _cooked(n):
    n.cook(force=True)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "errors": [str(e) for e in n.errors()]}


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_GROUP_TYPE = ("guess", "vertices", "edges", "points", "prims")
_SKIN_PRESET = ("none", "weak", "blubber", "sponge", "firm")

# skin_properties: user-facing float param -> (enable-toggle parm, value parm). Providing the float
# enables the property and sets its value; unprovided properties stay disabled (node default).
_SKIN_PROP_MAP = {
    "surface_stiffness":       ("enablesurfacestiffness", "surfacestiffness"),
    "surface_damping":         ("enablesurfacedamping", "surfacedamping"),
    "surface_bend_stiffness":  ("enablesurfacebendstiffness", "surfacebendstiffness"),
    "surface_mass_density":    ("enablesurfacemassdensity", "surfacemassdensity"),
    "solid_shape_stiffness":   ("enablesolidshapestiffness", "solidshapestiffness"),
    "solid_volume_stiffness":  ("enablesolidvolumestiffness", "solidvolumestiffness"),
    "solid_mass_density":      ("enablesolidmassdensity", "solidmassdensity"),
    "sliding_rate":            ("enableslidingrate", "slidingrate"),
}


# ── 1. skin_properties (skinproperties) — B chain: in0 = skin geo, authors sim-property attribs ───
@endpoint("skin_properties")
def skin_properties(params):
    """KineFX Skin Properties (skinproperties) — authors per-point muscle/skin SOLVER property
    attributes on the input skin (input 0): surface & solid stiffness / damping / bend-stiffness /
    mass-density / sliding-rate, optionally masked and blended, with a material `preset`. Pure
    attribute authoring — cooks green and writes only the properties you enable. SECURITY: attribute
    names + numeric values + benign ordered menus only; no file/code surface."""
    n = child_after(params["geometry"], "skinproperties", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUP_TYPE)
    if "preset" in params:
        _menu_set(n, "presetproperties", str(params["preset"]), _SKIN_PRESET)
    if "mask" in params:
        _try_set(n, "mask", str(params["mask"]))
    if "invert_mask" in params:
        _try_set(n, "invertmask", bool(params["invert_mask"]))
    if "mask_blend" in params:
        _try_set(n, "maskblend", clamp(float(params["mask_blend"]), 0.0, 1.0))
    for key, (enable_parm, value_parm) in _SKIN_PROP_MAP.items():
        if key in params:
            _try_set(n, enable_parm, True)
            _try_set(n, value_parm, clamp(float(params[key]), 0.0, 1e9))
    return _cooked(n)


# ── 2. skin_solidify (skinsolidify::2.0) — B chain: in0 = skin surface -> layered solid tet shell ─
@endpoint("skin_solidify")
def skin_solidify(params):
    """KineFX Skin Solidify (skinsolidify::2.0) — builds a layered SOLID tet shell around an input skin
    surface (input 0) for FEM / cloth-style skin simulation: `skin_thickness` + `num_layers` set the
    shell depth, the element-sizing levers (`min_size`/`max_size`/`rel_density`/`gradation`) drive tet
    density, and a smoothing relaxation (`iterations`/`step_size`) cleans interior weights. Distinct
    from `bone_solidify` (single-solid bone-FEM tet). SECURITY: numeric values + attribute names only;
    no file/code surface. The cost-exponential sizing / iteration levers are hard-clamped."""
    n = child_after(params["geometry"], "skinsolidify::2.0", params.get("name"))
    if "skin_thickness" in params:
        _try_set(n, "skinthickness", clamp(float(params["skin_thickness"]), 1e-5, 1e4))
    if "use_thickness_attrib" in params:
        _try_set(n, "usethicknessattrib", bool(params["use_thickness_attrib"]))
    if "thickness_attrib" in params:
        _try_set(n, "thicknessattrib", str(params["thickness_attrib"]))
    if "num_layers" in params:
        _try_set(n, "numlayers", int(clamp(int(params["num_layers"]), 1, 32)))
    if "remesh_surface" in params:
        _try_set(n, "remeshsurface", bool(params["remesh_surface"]))
    if "min_size" in params:
        _try_set(n, "minsize", clamp(float(params["min_size"]), 1e-4, 1e4))
    if "max_size" in params:
        _try_set(n, "maxsize", clamp(float(params["max_size"]), 1e-4, 1e4))
    if "rel_density" in params:
        _try_set(n, "reldensity", clamp(float(params["rel_density"]), 1e-3, 100.0))
    if "gradation" in params:
        _try_set(n, "gradation", clamp(float(params["gradation"]), 0.0, 10.0))
    if "blur_weight_attrib" in params:
        _try_set(n, "blurweightattrib", str(params["blur_weight_attrib"]))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 500)))
    if "step_size" in params:
        _try_set(n, "stepsize", clamp(float(params["step_size"]), 0.0, 1.0))
    if "enable_surface" in params:
        _try_set(n, "enablesurface", bool(params["enable_surface"]))
    if "enable_interior" in params:
        _try_set(n, "enableinterior", bool(params["enable_interior"]))
    return _cooked(n)


# ── 3. skin_deform (skindeform) — B chain: in0 = skin, muscle-blur + skin-sliding finishing ───────
@endpoint("skin_deform")
def skin_deform(params):
    """KineFX Skin Deform (skindeform) — muscle-aware skin finishing over an input skin (input 0):
    a muscle-blur pass that smooths skin weights toward the underlying muscle motion, plus an optional
    skin-sliding relaxation that lets the skin slide over the muscles, resolved against a reference
    frame. Distinct from the bone/joint/skeleton deform lane. SECURITY: attribute names + numeric
    values only; no file/code surface. The iteration levers are hard-clamped."""
    n = child_after(params["geometry"], "skindeform", params.get("name"))
    if "ref_frame" in params:
        _try_set(n, "refframe", int(clamp(int(params["ref_frame"]), -100000, 100000)))
    if "use_mask" in params:
        _try_set(n, "usemask", bool(params["use_mask"]))
    if "mask_attrib" in params:
        _try_set(n, "maskattrib", str(params["mask_attrib"]))
    if "muscle_blur" in params:
        _try_set(n, "muscleblur", bool(params["muscle_blur"]))
    if "muscle_blur_iterations" in params:
        _try_set(n, "muscleblur_skiniterations",
                 int(clamp(int(params["muscle_blur_iterations"]), 0, 1000)))
    if "muscle_blur_mask_attrib" in params:
        _try_set(n, "muscleblur_maskattrib", str(params["muscle_blur_mask_attrib"]))
    if "skin_sliding" in params:
        _try_set(n, "skinsliding", bool(params["skin_sliding"]))
    if "skin_sliding_tension" in params:
        _try_set(n, "skinsliding_tension", clamp(float(params["skin_sliding_tension"]), 0.0, 1.0))
    if "skin_sliding_lowres" in params:
        _try_set(n, "skinsliding_lowresenable", bool(params["skin_sliding_lowres"]))
    if "skin_sliding_relax_iterations" in params:
        _try_set(n, "skinsliding_relaxiterations",
                 int(clamp(int(params["skin_sliding_relax_iterations"]), 0, 1000)))
    if "skin_sliding_slide_iterations" in params:
        _try_set(n, "skinsliding_slideiterations",
                 int(clamp(int(params["skin_sliding_slide_iterations"]), 0, 1000)))
    return _cooked(n)

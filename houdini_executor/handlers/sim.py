"""Simulation handlers — recipe-templated DOP wrappers + FLIP surfacing.

Networks are BUILT, never auto-simulated: stepping frames on the executor's main thread would
overwhelm the UI. The caller scrubs the timeline to run the sim. Every numeric parm is clamped and
set through a probe-safe helper (absent parms are skipped, never guessed). Creators FAIL on name
collision (never destroy existing user work).
"""

import json

try:
    from houdini_executor.governor import governor_gate
except Exception:  # noqa: BLE001 -- governor is optional; fail-soft to a no-op
    def governor_gate(op_label):  # fail-soft stub
        return None

import hou
from houdini_executor.server import endpoint, clamp, child_after, confined_path, resolve_node, bridge_into, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set




def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)




def _set_indep(node, parm, value):
    """Set a parm to an independent literal, dropping any channel-reference/expression first (probe-
    safe). Needed where parms ship linked by default expressions (e.g. erode = ch(dilate)); a plain
    .set() on the linked parm would push the value into its reference target instead."""
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


def _src_node(g, source_geo, default_type, default_setup):
    """Object-merge an existing /obj geo, else build a default primitive emitter."""
    if source_geo:
        om = g.createNode("object_merge", "src")
        _try_set(om, "objpath1", str(source_geo))
        return om
    n = g.createNode(default_type, "src")
    if default_setup:
        default_setup(n)
    return n


# ── RBD / destruction (Phase-1): rbdmaterialfracture::3.0 -> rbdbulletsolver, with the modern
# SOP-level Bullet lane. Live-probed on H21.0.671. Two dataflow findings that drove
# the wiring:
#   • rbdmaterialfracture::3.0 outputs (0=Geometry, 1=Constraint Geometry, 2=Proxy Geometry); the
#     Constraint Geometry (the glue network it emits) rides on OUTPUT 1.
#   • rbdbulletsolver inputs (0=Geometry, 1=Constraint Geometry, 2=Proxy, 3=Collision, 4=Guide Sim).
#     The old sim_rbd only wired input 0 — the entire glue network (the point of destruction) was
#     silently dropped. Fixed here: solver.setInput(1, fracture, 1).
# rbdmaterialfracture params are MATERIAL-PREFIXED (concrete_*/glass_*/wood_*/custom_*), NOT the flat
# names the spec guessed; generic keys are routed to the chosen material's prefix (absent -> skipped).
# rbdconstraintproperties::2.0 gates every value behind a do* toggle (like the FLIP/pyro enable knobs).
_RBD_MATERIALTYPE = ("concrete", "glass", "wood", "custom")       # rbdmaterialfracture materialtype (Menu=index)
_RBD_CTYPE = ("glue", "hard", "soft")                             # rbdconstraintproperties constrainttype (glue/hard/soft ONLY)
_RBD_DOF = ("all", "position", "rotation")                        # rbdconstraintproperties constraintdof (NOT position/orientation/both)
_RBD_ACTION = ("off", "on")                                       # rbdconstraintproperties action (default on)
_RBD_GEOREP = ("convexhull", "concave", "box", "capsule", "cylinder", "compound", "sphere", "plane")  # collision_bullet_georep (String menu)
_RBD_INITIALSTATE = ("static", "animatedstatic", "deformingstatic")  # collision_initialstate (Menu=index)
_RBD_SOLVERTYPE = ("gaussseidelisland", "gaussseidelcolor")       # constraintsolvertype (Menu=index)
# primary breaking-strength parm differs per material (custom has only a chipping strength).
_FRAC_PRIMARY_STRENGTH = {"concrete": "concrete_primarystrength", "glass": "glass_radialstrength",
                          "wood": "wood_cutstrength", "custom": "custom_chippingstrength"}
_FRAC_DETAILSIZE = {"concrete": "concrete_detailsize", "glass": "glass_detailsize",
                    "wood": "wood_graindetailsize", "custom": "custom_detailsize"}
# piece-count / scatter dial per material (wood is spacing-driven, not count-driven -> no entry).
_FRAC_SCATTER_PARM = {"concrete": "concrete_scatterpts1", "glass": "glass_impactscatterpoints",
                      "custom": "custom_scatterpts"}
_FRAC_SCATTER_SEED = {"concrete": "concrete_scatterseed1", "glass": "glass_impactscatterseed",
                      "custom": "custom_scatterseed"}
# scatter-count scaling menu — forced to 0 (No Scaling) when `pieces` is given so the count is LITERAL
# (the default scales by volume, so `pieces` wouldn't mean a fragment count).
_FRAC_SCATTER_SCALING = {"concrete": "concrete_scatterptsscaling1", "glass": "glass_impactscatterpointsscaling"}
_FRAC_NOISETYPE = ("value_fast", "sparse", "alligator", "perlin", "flow", "simplex",
                   "worleyFA", "worleyFB", "mworleyFA", "mworleyFB", "cworleyFA", "cworleyFB")  # {mat}_interiornoisetype (String menu)
_FRAC_PROXY = ("default", "convex", "spheres")   # {mat}_proxygeometry (Menu=index; concrete/custom only)


def _str_menu_set(node, parm, token, tokens):
    """Set a STRING-type menu parm by its token string directly (the token IS the stored value —
    unlike an ordered Menu parm, where the index is stored). Probe-safe."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _set_gated(node, gate, parm, value):
    """Flip a do* gate toggle on, then set the value (the rbdconstraintproperties pattern: a bare
    .set() on a gated parm is ignored by the node's edit logic). Probe-safe."""
    if node.parm(gate) is not None:
        _try_set(node, gate, 1)
    return _try_set(node, parm, value)


def _apply_rbd_fracture(frac, mat, params, applied):
    """rbdmaterialfracture::3.0 material params, routed to the chosen material's prefix (probe-verified;
    absent-for-this-material parms skip). Covers detail/chipping + the built-in constraint (glue)
    emission — `strength` is the primary breaking strength of the emitted network."""
    if "detailsize" in params:
        applied["detailsize"] = _try_set(frac, _FRAC_DETAILSIZE.get(mat, mat + "_detailsize"),
                                         clamp(float(params["detailsize"]), 1e-4, 1e4))
    if "voxelsize" in params:
        applied["voxelsize"] = _try_set(frac, mat + "_voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "maxconcavity" in params:
        applied["maxconcavity"] = _try_set(frac, mat + "_maxconcavity", clamp(float(params["maxconcavity"]), 0.0, 1e4))
    if "edgedetail" in params:
        applied["edgedetail"] = _try_set(frac, mat + "_edgedetail", bool(params["edgedetail"]))
    if "interiordetail" in params:
        applied["interiordetail"] = _try_set(frac, mat + "_interiordetail", bool(params["interiordetail"]))
    if "interiornoiseamp" in params:
        applied["interiornoiseamp"] = _try_set(frac, mat + "_interiornoiseamp", clamp(float(params["interiornoiseamp"]), 0.0, 1e4))
    # -- chipping (concrete/glass/custom; passing a magnitude enables it) --
    if "enablechipping" in params:
        applied["enablechipping"] = _try_set(frac, mat + "_enablechipping", bool(params["enablechipping"]))
    if "chipping_ratio" in params:
        _try_set(frac, mat + "_enablechipping", 1)
        applied["chipping_ratio"] = _try_set(frac, mat + "_chippingratio", clamp(float(params["chipping_ratio"]), 0.0, 1.0))
    if "chipping_seed" in params:
        applied["chipping_seed"] = _try_set(frac, mat + "_chippingseed", clamp(float(params["chipping_seed"]), 0.0, 1e9))
    if "chipping_randomness" in params:
        applied["chipping_randomness"] = _try_set(frac, mat + "_chippingrandomness", clamp(float(params["chipping_randomness"]), 0.0, 1.0))
    # -- constraint (glue-network) emission: strength = the breaking threshold baked at fracture time --
    if "applyconstraints" in params:
        applied["applyconstraints"] = _try_set(frac, mat + "_applyconstraints", bool(params["applyconstraints"]))
    if "strength" in params:
        applied["strength"] = _try_set(frac, _FRAC_PRIMARY_STRENGTH.get(mat, mat + "_primarystrength"),
                                       clamp(float(params["strength"]), 0.0, 1e12))
    if "chipping_strength" in params:
        applied["chipping_strength"] = _try_set(frac, mat + "_chippingstrength", clamp(float(params["chipping_strength"]), 0.0, 1e12))
    if "strengthvariance" in params:
        applied["strengthvariance"] = _try_set(frac, mat + "_strengthvariance", clamp(float(params["strengthvariance"]), 0.0, 1e4))
    if "nextconstraint" in params:
        applied["nextconstraint"] = _try_set(frac, mat + "_nextconstraint", bool(params["nextconstraint"]))
    # -- glass-specific --
    if "cracks" in params:
        applied["cracks"] = _try_set(frac, "glass_radialcracknum", int(clamp(int(params["cracks"]), 0, 100000)))
    if "impactpoints" in params:
        applied["impactpoints"] = _try_set(frac, "glass_impactscatterpoints", int(clamp(int(params["impactpoints"]), 1, 100000)))
    if "convexdecomposition" in params:
        applied["convexdecomposition"] = _try_set(frac, "glass_enableconvexdecomposition", bool(params["convexdecomposition"]))
    # -- wood-specific --
    if "grainspacing" in params:
        applied["grainspacing"] = _try_set(frac, "wood_grainspacing", clamp(float(params["grainspacing"]), 1e-4, 1e4))
    if "cutspacing" in params:
        applied["cutspacing"] = _try_set(frac, "wood_cutspacing", clamp(float(params["cutspacing"]), 1e-4, 1e4))
    if "splinterdensity" in params:
        applied["splinterdensity"] = _try_set(frac, "wood_splinterdensity", clamp(float(params["splinterdensity"]), 0.0, 1e6))
    if "cluster" in params:
        applied["cluster"] = _try_set(frac, "wood_enablecluster", bool(params["cluster"]))
    return applied


def _apply_rbd_solver(sim, params, applied):
    """Deep rbdbulletsolver (SOP) param sets (all probe-verified on H21.0.671). Gravity/ground/guide
    magnitudes flip their enabling toggle. NOTE the probe-corrected shapes: collision is `usecollisions`
    (toggle) + `collision_bullet_georep` (STRING menu) + `collision_initialstate` (menu), NOT a single
    collision menu; there is NO `niter` parm on this solver (constraint iterations aren't exposed here —
    substeps + constraintsolvertolerance are the knobs)."""
    # -- setup --
    if "startframe" in params:
        applied["startframe"] = _try_set(sim, "startframe", int(clamp(int(params["startframe"]), -100000, 100000)))
    if "substeps" in params:
        applied["substeps"] = _try_set(sim, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "timescale" in params:
        applied["timescale"] = _try_set(sim, "timescale", clamp(float(params["timescale"]), 1e-4, 1e4))
    if "density" in params:
        applied["density"] = _try_set(sim, "density", clamp(float(params["density"]), 1e-3, 1e9))
    if "bounce" in params:
        applied["bounce"] = _try_set(sim, "bounce", clamp(float(params["bounce"]), 0.0, 1e4))
    if "friction" in params:
        applied["friction"] = _try_set(sim, "friction", clamp(float(params["friction"]), 0.0, 1e4))
    if "overwriteattributes" in params:
        applied["overwriteattributes"] = _try_set(sim, "overwriteattributes", str(params["overwriteattributes"]))
    # -- forces (gravity vec OR scalar magnitude; drag) --
    if "gravity" in params:
        _try_set(sim, "addgravity", 1)
        applied["gravity"] = _set_grav(sim, "gravity", params["gravity"], True)
    if "drag" in params:
        _try_set(sim, "adddrag", 1)
        applied["drag"] = _try_set(sim, "drag_airresist", clamp(float(params["drag"]), 0.0, 1e6))
    if "windvelocity" in params:
        _try_set(sim, "adddrag", 1)
        applied["windvelocity"] = _set_vec(sim, "drag_windvelocity", params["windvelocity"])
    # -- collision (the terrain bridge is Phase-2; these tune the response) --
    if "usecollisions" in params:
        applied["usecollisions"] = _try_set(sim, "usecollisions", bool(params["usecollisions"]))
    if "georep" in params:
        applied["georep"] = _str_menu_set(sim, "collision_bullet_georep", str(params["georep"]), _RBD_GEOREP)
    if "collision_initialstate" in params:
        applied["collision_initialstate"] = _menu_set(sim, "collision_initialstate", str(params["collision_initialstate"]), _RBD_INITIALSTATE)
    if "collision_margin" in params:
        applied["collision_margin"] = _try_set(sim, "collision_margin", clamp(float(params["collision_margin"]), 0.0, 1e4))
    if "collision_bounce" in params:
        applied["collision_bounce"] = _try_set(sim, "collision_bounce", clamp(float(params["collision_bounce"]), 0.0, 1e4))
    if "collision_friction" in params:
        applied["collision_friction"] = _try_set(sim, "collision_friction", clamp(float(params["collision_friction"]), 0.0, 1e4))
    # -- ground plane --
    if "useground" in params:
        applied["useground"] = _try_set(sim, "useground", int(clamp(int(params["useground"]), 0, 2)))
    if "ground_pos" in params:
        _try_set(sim, "useground", 1)
        applied["ground_pos"] = _set_vec(sim, "ground_pos", params["ground_pos"])
    if "ground_bounce" in params:
        applied["ground_bounce"] = _try_set(sim, "ground_bounce", clamp(float(params["ground_bounce"]), 0.0, 1e4))
    if "ground_friction" in params:
        applied["ground_friction"] = _try_set(sim, "ground_friction", clamp(float(params["ground_friction"]), 0.0, 1e4))
    # -- constraint breaking / updates --
    if "enable_constraintbreaks" in params:
        applied["enable_constraintbreaks"] = _try_set(sim, "enable_constraintbreaks", bool(params["enable_constraintbreaks"]))
    if "enable_constraintupdates" in params:
        applied["enable_constraintupdates"] = _try_set(sim, "enable_constraintupdates", bool(params["enable_constraintupdates"]))
    if "constraint_keepbroken" in params:
        applied["constraint_keepbroken"] = _try_set(sim, "constraint_keepbroken", bool(params["constraint_keepbroken"]))
    if "glue_propagationiterations" in params:
        applied["glue_propagationiterations"] = _try_set(sim, "glue_propagationiterations", int(clamp(int(params["glue_propagationiterations"]), 0, 100000)))
    # -- explicit BREAK RULE (rbdbulletsolver `breaks` multiparm, rule 1) — the pro destruction dial:
    #    break constraints when a per-constraint attribute (angle/distance/force/torque/impact/plastic
    #    flow) exceeds a threshold; variance makes the break read naturally; group/names target which
    #    constraints; atframe/fromframe do timed collapses. Thresholds are SCENE-SCALE-RELATIVE. --
    _break_keys = ("break_condition", "break_threshold", "break_variance", "break_attrib",
                   "break_group", "break_names", "break_atframe", "break_fromframe", "break_scale_by_attrib")
    if any(k in params for k in _break_keys):
        bp = sim.parm("breaks")
        if bp is not None and bp.eval() < 1:
            _try_set(sim, "breaks", 1)                       # ensure at least one break rule exists
        _try_set(sim, "enable_constraintbreaks", 1)          # master enable
        bc = str(params.get("break_condition", "")).lower()
        if bc in ("force", "impact", "angle", "distance", "torque", "plasticflow"):
            _try_set(sim, "constraint_use%s1" % bc, 1)
            applied["break_condition"] = bc
            if "break_threshold" in params:
                applied["break_threshold"] = _try_set(sim, "constraint_%sthreshold1" % bc, float(params["break_threshold"]))
            if "break_variance" in params:
                _try_set(sim, "constraint_use%svar1" % bc, 1)
                applied["break_variance"] = _try_set(sim, "constraint_%svar1" % bc, clamp(float(params["break_variance"]), 0.0, 1.0))
            if "break_attrib" in params:
                applied["break_attrib"] = _try_set(sim, "constraint_%sattrib1" % bc, str(params["break_attrib"]))
            if "break_scale_by_attrib" in params:
                applied["break_scale_by_attrib"] = _try_set(sim, "constraint_scale%s1" % bc, 1 if params["break_scale_by_attrib"] else 0)
        if "break_group" in params:
            applied["break_group"] = _try_set(sim, "constraint_group1", str(params["break_group"]))
        if "break_names" in params:
            applied["break_names"] = _try_set(sim, "constraint_names1", str(params["break_names"]))
        if "break_atframe" in params:
            _try_set(sim, "constraint_useatframe1", 1)
            applied["break_atframe"] = _try_set(sim, "constraint_atframe1", float(params["break_atframe"]))
        if "break_fromframe" in params:
            _try_set(sim, "constraint_usefromframe1", 1)
            applied["break_fromframe"] = _try_set(sim, "constraint_fromframe1", float(params["break_fromframe"]))
    # -- glue constraint BEHAVIOUR (brittle strength + crack propagation). glue_strength: NO clamp —
    #    -1 is an overloaded cluster sentinel and the range is scene-scale (wide). --
    if "glue_strength" in params:
        applied["glue_strength"] = _try_set(sim, "glue_strength", float(params["glue_strength"]))
    if "glue_impulse_halflife" in params:
        applied["glue_impulse_halflife"] = _try_set(sim, "glue_impulse_halflife", clamp(float(params["glue_impulse_halflife"]), 0.0, 1e6))
    if "glue_propagate_rate" in params:
        applied["glue_propagate_rate"] = _try_set(sim, "glue_propagate_rate", clamp(float(params["glue_propagate_rate"]), 0.0, 1e6))
    # -- sleeping / deactivation --
    if "sleepingtime" in params:
        applied["sleepingtime"] = _try_set(sim, "sleepingtime", clamp(float(params["sleepingtime"]), 0.0, 1e6))
    # -- guide sim (blend the Bullet solve toward a guide) --
    if "useguides" in params:
        applied["useguides"] = _try_set(sim, "useguides", bool(params["useguides"]))
    if "guide_method" in params:
        _try_set(sim, "useguides", 1)
        applied["guide_method"] = _try_set(sim, "guide_method", int(clamp(int(params["guide_method"]), 0, 1)))
    if "guide_blend" in params:
        applied["guide_blend"] = _try_set(sim, "guide_blend", clamp(float(params["guide_blend"]), 0.0, 1.0))
    if "guide_linearthreshold" in params:
        _try_set(sim, "guide_uselinearthreshold", 1)
        applied["guide_linearthreshold"] = _try_set(sim, "guide_linearthreshold", clamp(float(params["guide_linearthreshold"]), 0.0, 1e6))
    if "guide_angularthreshold" in params:
        _try_set(sim, "guide_useangularthreshold", 1)
        applied["guide_angularthreshold"] = _try_set(sim, "guide_angularthreshold", clamp(float(params["guide_angularthreshold"]), 0.0, 1e6))
    if "guide_distancethreshold" in params:
        _try_set(sim, "guide_usedistancethreshold", 1)
        applied["guide_distancethreshold"] = _try_set(sim, "guide_distancethreshold", clamp(float(params["guide_distancethreshold"]), 0.0, 1e6))
    # -- advanced Bullet --
    if "contactbreakingthreshold" in params:
        applied["contactbreakingthreshold"] = _try_set(sim, "contactbreakingthreshold", clamp(float(params["contactbreakingthreshold"]), 0.0, 1e4))
    if "implicitdrag" in params:
        applied["implicitdrag"] = _try_set(sim, "implicitdrag", bool(params["implicitdrag"]))
    if "splitimpulse" in params:
        applied["splitimpulse"] = _try_set(sim, "splitimpulse", bool(params["splitimpulse"]))
    if "penetrationthreshold" in params:
        applied["penetrationthreshold"] = _try_set(sim, "penetrationthreshold", clamp(float(params["penetrationthreshold"]), -1e4, 1e4))
    if "splitimpulseerp" in params:
        applied["splitimpulseerp"] = _try_set(sim, "splitimpulseerp", clamp(float(params["splitimpulseerp"]), 0.0, 1.0))
    if "constraintsolvertype" in params:
        applied["constraintsolvertype"] = _menu_set(sim, "constraintsolvertype", str(params["constraintsolvertype"]), _RBD_SOLVERTYPE)
    if "constraintsolvertolerance" in params:
        applied["constraintsolvertolerance"] = _try_set(sim, "constraintsolvertolerance", clamp(float(params["constraintsolvertolerance"]), 0.0, 1e4))
    if "globalcfm" in params:
        applied["globalcfm"] = _try_set(sim, "globalcfm", clamp(float(params["globalcfm"]), 0.0, 1e4))
    if "globalerp" in params:
        applied["globalerp"] = _try_set(sim, "globalerp", clamp(float(params["globalerp"]), 0.0, 1.0))
    if "randomize_order" in params:
        applied["randomize_order"] = _try_set(sim, "randomize_order", bool(params["randomize_order"]))
    if "ensureindependentislands" in params:
        applied["ensureindependentislands"] = _try_set(sim, "ensureindependentislands", bool(params["ensureindependentislands"]))
    return applied


@endpoint("sim_rbd")
def sim_rbd(params):
    """Rigid-body destruction (SOP Bullet lane): source -> rbdmaterialfracture::3.0 -> rbdbulletsolver.
    The fracture emits both the broken pieces (out0) AND its glue-constraint network (out1); BOTH are
    wired into the solver (Geometry in0 + Constraint Geometry in1 — the old build dropped the constraint
    wiring). Cooks the fracture only; the Bullet solve is left for the caller to scrub (heavy-op rule).

    Fracture (rbdmaterialfracture::3.0): materialtype (concrete|glass|wood|custom), seed. Material params
    are routed to the chosen material's prefix (probe-real names): detailsize, voxelsize, maxconcavity,
    edgedetail, interiordetail, interiornoiseamp; chipping via enablechipping/chipping_ratio/chipping_seed/
    chipping_randomness. Built-in glue emission: applyconstraints, strength (the primary breaking strength
    baked into the network), chipping_strength, strengthvariance, nextconstraint (break-to-next). Glass:
    cracks, impactpoints, convexdecomposition. Wood: grainspacing, cutspacing, splinterdensity, cluster.

    Solver (rbdbulletsolver): startframe, substeps, timescale, density, bounce, friction,
    overwriteattributes; gravity[x,y,z] (or scalar), drag(+windvelocity); collision response
    usecollisions/georep(convexhull|concave|box|capsule|cylinder|compound|sphere|plane)/
    collision_initialstate(static|animatedstatic|deformingstatic)/collision_margin/collision_bounce/
    collision_friction; useground(0|1|2)+ground_pos/ground_bounce/ground_friction; constraint breaking
    enable_constraintbreaks/enable_constraintupdates/constraint_keepbroken/glue_propagationiterations;
    sleepingtime; guide sim useguides/guide_method/guide_blend/guide_linearthreshold/guide_angularthreshold/
    guide_distancethreshold; advanced contactbreakingthreshold/implicitdrag/splitimpulse/penetrationthreshold/
    splitimpulseerp/constraintsolvertype(gaussseidelisland|gaussseidelcolor)/constraintsolvertolerance/
    globalcfm/globalerp/randomize_order/ensureindependentislands. BUILT, never auto-simulated."""
    name = params["name"]
    frames = int(clamp(int(params.get("frames", 120)), 1, 10000))
    seed = float(params.get("seed", 0))
    display = bool(params.get("display", False))
    mat = str(params.get("materialtype", "concrete"))
    if mat not in _RBD_MATERIALTYPE:
        mat = "concrete"
    g = _fresh_geo(name)
    src = _src_node(g, params.get("source_geo"), "box",
                    lambda n: n.parmTuple("size").set((10.0, 3.0, 10.0)))
    frac = g.createNode("rbdmaterialfracture::3.0")
    frac.setFirstInput(src)
    applied = {}
    applied["materialtype"] = _menu_set(frac, "materialtype", mat, _RBD_MATERIALTYPE)
    _try_set(frac, "randomseed", seed)
    _apply_rbd_fracture(frac, mat, params, applied)
    sim = g.createNode("rbdbulletsolver")
    sim.setInput(0, frac, 0)           # Geometry (fractured pieces)
    sim.setInput(1, frac, 1)           # Constraint Geometry (the emitted glue network) — was dropped before
    # legacy defaults (startframe=1, substeps=1) preserved, then deep solver params applied
    sp = dict(params)
    sp.setdefault("startframe", int(params.get("startframe", 1)))
    sp.setdefault("substeps", int(clamp(int(params.get("substeps", 1)), 1, 100)))
    _apply_rbd_solver(sim, sp, applied)
    sim.setDisplayFlag(display)
    sim.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    governor_gate("sim_rbd")  # advisory heavy-cook gate; refuses only in the catastrophic band
    frac.cook(force=True)
    return {"node": g.path(), "fracture": frac.path(), "solver": sim.path(),
            "frames": frames, "materialtype": mat,
            "fracture_prims": len(frac.geometry().prims()),
            "constraints_wired": sim.input(1) is not None, "applied": applied}


@endpoint("rbd_material_fracture")
def rbd_material_fracture(params):
    """Pre-fracture geometry by MATERIAL TYPE with rbdmaterialfracture::3.0 — the modern one-node
    destruction fracture (concrete | glass | wood | custom presets), WITHOUT running a solver. The node
    emits THREE streams: broken PIECES (out0), the glue CONSTRAINT network (out1), and a collision
    PROXY (out2). Unlike sim_rbd (which buries this inside a Bullet solve), this stops at the fracture so
    you can INSPECT the pieces / place-and-verify / retexture before simming — and feed pieces+constraints
    to a solver later. Named-null LANDMARKS (default on) plant `OUT_pieces` / `OUT_constraints` /
    `OUT_proxy` on the three outputs so downstream references stay stable and the network is legible.

    `pieces` = fragment count — THE headline dial (concrete/custom scatter points, glass impact points;
    wood is spacing-driven, use grainspacing/cutspacing instead). materialtype swaps which prefixed param
    family is active. Material params (routed to the chosen prefix): detailsize, voxelsize, maxconcavity,
    edgedetail, interiordetail + interiornoiseamp + interior_noise_type (value_fast|perlin|worleyFA|… ) +
    interior_noise_freq[x,y,z]; chipping (enablechipping / chipping_ratio / chipping_seed /
    chipping_randomness / chipping_strength); glue emission applyconstraints + strength (breaking
    threshold baked in) + strengthvariance + nextconstraint. Constraint network master: constraints_enable
    + constraint_search_radius. proxy_mode (default|convex|spheres, concrete/custom). Glass: cracks,
    impactpoints, convexdecomposition. Wood: grainspacing, cutspacing, splinterdensity, cluster.
    Cooks the fracture (SOP, no sim) and reports per-stream prim/point counts."""
    mat = str(params.get("materialtype", "concrete"))
    if mat not in _RBD_MATERIALTYPE:
        mat = "concrete"
    frac = child_after(params["input"], "rbdmaterialfracture::3.0", params.get("name"))
    applied = {}
    applied["materialtype"] = _menu_set(frac, "materialtype", mat, _RBD_MATERIALTYPE)
    if "seed" in params:
        s = float(params["seed"])                       # randomseed is a 0..1 float — normalize larger/int seeds
        if s < 0.0 or s > 1.0:
            s = (abs(s) % 1000.0) / 1000.0
        applied["seed"] = _try_set(frac, "randomseed", s)
    # piece count / scatter density — the headline gap (wood has none: spacing-driven).
    if "pieces" in params and mat in _FRAC_SCATTER_PARM:
        if mat in _FRAC_SCATTER_SCALING:
            _try_set(frac, _FRAC_SCATTER_SCALING[mat], 0)   # No Scaling -> `pieces` is a literal count, not a density
        if mat == "concrete":
            _try_set(frac, "concrete_fracturelevel", 1)     # single level so pieces == scatter count (default 2 levels multiply)
        applied["pieces"] = _try_set(frac, _FRAC_SCATTER_PARM[mat], int(clamp(int(params["pieces"]), 0, 100000)))
    if "scatter_seed" in params and mat in _FRAC_SCATTER_SEED:
        applied["scatter_seed"] = _try_set(frac, _FRAC_SCATTER_SEED[mat], clamp(float(params["scatter_seed"]), 0.0, 1e9))
    # shared material-param router (detail/chipping/strength/glass/wood) — same as sim_rbd.
    _apply_rbd_fracture(frac, mat, params, applied)
    # interior noise TYPE + per-axis frequency (sim_rbd exposes only amplitude).
    if "interior_noise_type" in params:
        _try_set(frac, mat + "_interiordetail", 1)
        applied["interior_noise_type"] = _str_menu_set(frac, mat + "_interiornoisetype",
                                                       str(params["interior_noise_type"]), _FRAC_NOISETYPE)
    if "interior_noise_freq" in params and len(params["interior_noise_freq"]) == 3:
        _try_set(frac, mat + "_interiordetail", 1)
        for i, v in enumerate(params["interior_noise_freq"], start=1):
            _try_set(frac, "%s_interiornoisefreq%d" % (mat, i), clamp(float(v), 1e-4, 1e4))
        applied["interior_noise_freq"] = True
    # constraint-network master controls (global, not prefixed).
    if "constraints_enable" in params:
        applied["constraints_enable"] = _try_set(frac, "constraintsenable", bool(params["constraints_enable"]))
    if "constraint_search_radius" in params:
        applied["constraint_search_radius"] = _try_set(frac, "constraintsearchradius",
                                                       clamp(float(params["constraint_search_radius"]), 0.0, 1e6))
    # proxy geometry mode (concrete/custom expose a menu; glass/wood use convexdecomposition instead).
    if "proxy_mode" in params and mat in ("concrete", "custom"):
        applied["proxy_mode"] = _menu_set(frac, mat + "_proxygeometry", str(params["proxy_mode"]), _FRAC_PROXY)
    governor_gate("rbd_material_fracture")  # advisory heavy-cook gate; refuses only in the catastrophic band
    frac.cook(force=True)
    # named-null landmarks on each output (the OUT_* legibility idiom).
    parent = frac.parent()
    landmarks = {}
    if params.get("landmarks", True):
        base = frac.name()
        for idx, tag in ((0, "pieces"), (1, "constraints"), (2, "proxy")):
            nl = parent.createNode("null", "OUT_%s_%s" % (base, tag))
            nl.setInput(0, frac, idx)
            landmarks[tag] = nl.path()
        parent.layoutChildren()

    def _count(oi):
        try:
            gg = frac.geometry(oi)
            return (len(gg.prims()), len(gg.points())) if gg else (0, 0)
        except Exception:
            return (0, 0)
    p0, pt0 = _count(0)
    c1, _ = _count(1)
    x2, _ = _count(2)
    # True fracture-piece count = distinct `name` values (each chunk is a multi-face polyhedron, so
    # pieces_prims is a POLYGON count, not the piece count the `pieces` dial targets). Surface it so a
    # caller can verify the literal-count request without re-deriving it from the geometry.
    def _piece_count():
        try:
            gg = frac.geometry(0)
            if gg is None:
                return None
            attr = gg.findPrimAttrib("name")
            if attr is None:
                return None
            return len({p.attribValue("name") for p in gg.prims()})
        except Exception:
            return None
    return {"node": frac.path(), "materialtype": mat, "pieces": _piece_count(),
            "pieces_prims": p0, "pieces_points": pt0,
            "constraint_prims": c1, "proxy_prims": x2, "landmarks": landmarks, "applied": applied}


_FLIP_RES = ("lr", "hr")   # flipvolumecombine field_*res menus (ordered Menu, tokens lr|hr -> set by index)


@endpoint("flip_volume_combine")
def flip_volume_combine(params):
    """Combine a LOW-resolution FLIP sim's fields with HIGH-resolution detail for UP-RESSING
    (flipvolumecombine) — the H20 SOP up-res workflow: run the sim cheap at low res, then blend in
    high-frequency surface/velocity detail only where it matters (big splashes at low cost). `input` =
    the low-resolution fields (input 0); high_res = the high-resolution fields SOP (input 1,
    cross-network auto-bridged); container = the high-res reference container (input 2); clip_bbox = a
    clipping bounding box to limit the combine region (input 3). Per-field resolution pick:
    surface_res / velocity_res / pressure_res = lr|hr (which input each field takes). blend_range =
    [inner, outer] low->high transition width; extrapolate (+ extrapolate_distance) extends surfaces
    past the high-res boundary; smooth_seams (+ smooth_band / smooth_radius / smooth_iterations)
    filters the inner blend seam. BUILT (wired + configured), not auto-cooked (needs real FLIP fields)."""
    n = child_after(params["input"], "flipvolumecombine", params.get("name"))
    applied = {}
    for key, idx in (("high_res", 1), ("container", 2), ("clip_bbox", 3)):
        if params.get(key):
            src = resolve_node(params[key])
            sop = bridge_into(src, n.parent(), 0, key)
            n.setInput(idx, sop, 0)
            applied[key] = sop.path()
    if "surface_res" in params:
        applied["surface_res"] = _menu_set(n, "field_surfaceres", str(params["surface_res"]), _FLIP_RES)
    if "velocity_res" in params:
        applied["velocity_res"] = _menu_set(n, "field_velres", str(params["velocity_res"]), _FLIP_RES)
    if "pressure_res" in params:
        applied["pressure_res"] = _menu_set(n, "field_presres", str(params["pressure_res"]), _FLIP_RES)
    if "blend_range" in params and len(params["blend_range"]) == 2:
        _try_set(n, "field_blendrangex", float(params["blend_range"][0]))
        _try_set(n, "field_blendrangey", float(params["blend_range"][1]))
        applied["blend_range"] = True
    if "extrapolate" in params:
        applied["extrapolate"] = _try_set(n, "extrapolate_enable", bool(params["extrapolate"]))
    if "extrapolate_distance" in params:
        _try_set(n, "extrapolate_enable", 1)
        applied["extrapolate_distance"] = _try_set(n, "extrapolate_halfwidthworld", clamp(float(params["extrapolate_distance"]), 0.0, 1e6))
    if "smooth_seams" in params:
        applied["smooth_seams"] = _try_set(n, "field_surfblur", bool(params["smooth_seams"]))
    if "smooth_band" in params:
        _try_set(n, "field_surfblur", 1)
        applied["smooth_band"] = _try_set(n, "field_surfmaskwidth", clamp(float(params["smooth_band"]), 0.0, 1e6))
    if "smooth_radius" in params:
        _try_set(n, "field_surfblur", 1)
        applied["smooth_radius"] = _try_set(n, "field_surfblursize", clamp(float(params["smooth_radius"]), 0.0, 1e6))
    if "smooth_iterations" in params:
        _try_set(n, "field_surfblur", 1)
        applied["smooth_iterations"] = _try_set(n, "field_surfbluriter", int(clamp(int(params["smooth_iterations"]), 0, 100)))
    return {"node": n.path(), "applied": applied}


@endpoint("rbd_constraint_properties")
def rbd_constraint_properties(params):
    """Author the RBD constraint PHYSICS (the breaking dial) on an existing solver's glue/constraint
    network via rbdconstraintproperties::2.0. Given a `solver` (rbdbulletsolver from sim_rbd), inserts
    the node on the constraint line: input0 = the solver's fractured Geometry, input1 = the solver's
    current Constraint Geometry (falling back to the fracture node's out1 if the solver's constraint
    input wasn't wired), then rewires the solver to read the authored constraints (input 1). This is
    the dial that turns a rigid wall into one that shatters at a chosen force.

    Every value is gated behind its do* toggle (flipped automatically). ctype (glue|hard|soft — the ONLY
    three types; the spec's cone-twist/hinge/spring do NOT exist on this node), dof (all|position|rotation),
    constraintgroup, action (off|on, default on). Glue (breakable): strength (**the breaking threshold**),
    strengthvariance, halflife, propagationrate, propagationiterations (crack propagation). Hard: hard_cfm,
    hard_erp. Soft: stiffness, dampingratio, angularstiffness, angulardampingratio. Break-to-next
    (glue -> soft on break): nextconstraint (bool) + next_ctype (glue|hard|soft). Cooks the constraint
    geometry only (never the sim)."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "rbdbulletsolver":
        raise ValueError("`solver` must be an rbdbulletsolver SOP (got %s)" % solv.type().name())
    parent = solv.parent()
    conns = {c.inputIndex(): c for c in solv.inputConnections()}
    geo_c = conns.get(0)
    if geo_c is None:
        raise ValueError("solver input 0 (fractured geometry) is not connected")
    geo_node, geo_out = geo_c.inputNode(), geo_c.outputIndex()
    con_c = conns.get(1)
    if con_c is not None:
        con_node, con_out = con_c.inputNode(), con_c.outputIndex()
    else:
        con_node, con_out = geo_node, 1          # fall back to the fracture's Constraint Geometry (out1)
    cp = parent.createNode("rbdconstraintproperties::2.0", params.get("name") or "constraint_props")
    cp.setInput(0, geo_node, geo_out)            # Geometry
    cp.setInput(1, con_node, con_out)            # Constraint Geometry
    applied = {}
    _try_set(cp, "action", 1)                    # ensure edits are applied
    if "action" in params:
        applied["action"] = _menu_set(cp, "action", str(params["action"]), _RBD_ACTION)
    if "constraintgroup" in params:
        applied["constraintgroup"] = _try_set(cp, "constraintgroup", str(params["constraintgroup"]))
    if "ctype" in params:
        _try_set(cp, "doconstrainttype", 1)
        applied["ctype"] = _menu_set(cp, "constrainttype", str(params["ctype"]), _RBD_CTYPE)
    if "dof" in params:
        _try_set(cp, "doconstraintdof", 1)
        applied["dof"] = _menu_set(cp, "constraintdof", str(params["dof"]), _RBD_DOF)
    # -- glue (the breaking threshold + crack propagation) --
    if "strength" in params:
        applied["strength"] = _set_gated(cp, "doglue_strength", "glue_strength", clamp(float(params["strength"]), 0.0, 1e12))
    if "strengthvariance" in params:
        _try_set(cp, "glue_randomizestrength", 1)
        applied["strengthvariance"] = _try_set(cp, "glue_strengthvariance", clamp(float(params["strengthvariance"]), 0.0, 1e4))
    if "halflife" in params:
        applied["halflife"] = _set_gated(cp, "doglue_halflife", "glue_halflife", clamp(float(params["halflife"]), 0.0, 1e6))
    if "propagationrate" in params:
        applied["propagationrate"] = _set_gated(cp, "doglue_propagationrate", "glue_propagationrate", clamp(float(params["propagationrate"]), 0.0, 1e6))
    if "propagationiterations" in params:
        applied["propagationiterations"] = _set_gated(cp, "doglue_propagationiterations", "glue_propagationiterations",
                                                      int(clamp(int(params["propagationiterations"]), 0, 100000)))
    # -- hard --
    if "hard_cfm" in params:
        applied["hard_cfm"] = _set_gated(cp, "dohard_cfm", "hard_cfm", clamp(float(params["hard_cfm"]), 0.0, 1e6))
    if "hard_erp" in params:
        applied["hard_erp"] = _set_gated(cp, "dohard_erp", "hard_erp", clamp(float(params["hard_erp"]), 0.0, 1.0))
    # -- soft --
    if "stiffness" in params:
        applied["stiffness"] = _set_gated(cp, "dosoft_stiffness", "soft_stiffness", clamp(float(params["stiffness"]), 0.0, 1e9))
    if "dampingratio" in params:
        applied["dampingratio"] = _set_gated(cp, "dosoft_dampingratio", "soft_dampingratio", clamp(float(params["dampingratio"]), 0.0, 1e4))
    if "angularstiffness" in params:
        applied["angularstiffness"] = _set_gated(cp, "dosoft_angularstiffness", "soft_angularstiffness", clamp(float(params["angularstiffness"]), 0.0, 1e9))
    if "angulardampingratio" in params:
        applied["angulardampingratio"] = _set_gated(cp, "dosoft_angulardampingratio", "soft_angulardampingratio", clamp(float(params["angulardampingratio"]), 0.0, 1e4))
    # -- break-to-next (glue shatters into a soft/hard constraint) --
    if params.get("nextconstraint"):
        _try_set(cp, "dousenextconstraint", 1)
        applied["nextconstraint"] = _try_set(cp, "usenextconstraint", 1)
    if "next_ctype" in params:
        _try_set(cp, "dousenextconstraint", 1)
        _try_set(cp, "usenextconstraint", 1)
        _try_set(cp, "donext_constrainttype", 1)
        applied["next_ctype"] = _menu_set(cp, "next_constrainttype", str(params["next_ctype"]), _RBD_CTYPE)
    solv.setInput(1, cp, 1)                       # solver now reads the authored constraints
    cp.cook(force=True)                           # cook the constraint authoring only — never the sim
    try:
        parent.layoutChildren()
    except Exception:
        pass
    con_prims = 0
    try:
        cg = cp.geometry(1)
        con_prims = len(cg.prims()) if cg is not None else 0
    except Exception:
        pass
    return {"node": cp.path(), "constraintproperties": cp.path(), "solver": solv.path(),
            "authored_from": con_node.path(), "constraint_prims": con_prims, "applied": applied}


# ── RBD Phase-2+ (T2/T3/T4/T6/T8/T9/T10/T11/T12) — all live-probed on H21.0.671 (probe_rbd_p2*.py).
# PROBE CORRECTIONS baked in below (correcting earlier guessed names):
#   • voronoifracture is `voronoifracture::2.0` (out0=Fractured Geometry, out1=Constraint Geometry;
#     in0=Geometry, in1=Points for Voronoi Cells). `computeexteriornormals` is a MENU
#     (preserve/recompute/none), NOT a toggle; `triangulation` = autodetect/2d/3d/useexisting (NOT
#     none/2d/3d); interior/exterior groups gate on output*group toggles; no `cut` parm (`cutplaneoffset`).
#   • voronoisplit (unversioned): the "method" is `weightmethod` (power|ratio); + `offset`/`pieceattrib`.
#   • rbdinteriordetail (unversioned, 3+1 inputs): `noisetype`/`fractal` are STRING menus (token stored
#     directly); fractal tokens = none|fBm|mfT|hmfT (fBm capitalization matters — NOT standard/terrain/
#     hybrid); noisefreq/noiseoffset are vec3; depthmethod = mindist|sdf (index menu).
#   • rbdconstraintsfromrules (unversioned): `connectiontype` (surface|hinge|centroid) is the "mode";
#     the rule knobs are `rule_searchradius`/`rule_maxsearchpoints`/`rule_maxconnections`/
#     `rule_constraintsperpiece`/`rule_pieceattrib`; groupname/tag both default 'connectors'.
#   • connectadjacentpieces (unversioned, single 'Pieces' input): connecttype (points|pieces|pointcloud),
#     searchradius, coneangle (gated useconeangle), mindist (gated usemindist), maxconnections.
#   • rbdconfigure (unversioned): per-piece dynamics live in a TabbedMultiparmBlock `attributes`
#     (defaults to 1 instance); each attr rides an add<name>1 gate — group1, addactive1/active1,
#     adduserdensity1/userdensity1, adduserbounce1/userbounce1, adduserfriction1/userfriction1,
#     addminactivationimpulse1/minactivationimpulse1, addallowinitialoverlap1/allowinitialoverlap1,
#     type1 (0-3 density preset), pintype1 (0-2). `visualize` (0-10) is top-level.
#   • rbdexplodedview (unversioned): the spread dial is `scale` (gated doscale) + `offset`; showproxy,
#     modifyproxy (0/1/2 index), group. No deform/centroids/volume parms.
#   • rbdbulletsolver (SOP) inputs = 0 Geometry, 1 Constraint, 2 Proxy, 3 COLLISION, 4 Guide Sim.
#   • DOP forces: popexplosion does NOT exist — the blast force is `popaxisforce` (sphere, innerstrength
#     outward). uniformforce/pointforce use `force` vec3; windforce uses `vel`+`scaleforce`.
_VORO_NAMEMETHOD = ("overwrite", "append")                           # voronoifracture::2.0 namemethod (Menu=idx)
_VORO_EXTNORMALS = ("preserve", "recompute", "none")                 # computeexteriornormals (Menu=idx)
_VORO_TRIANGULATION = ("autodetect", "2d", "3d", "useexisting")      # triangulation (Menu=idx)
_VOROSPLIT_WEIGHT = ("power", "ratio")                               # voronoisplit weightmethod (Menu=idx)
_INTERIOR_NOISETYPE = ("value_fast", "sparse", "alligator", "perlin", "flow", "simplex",
                       "worleyFA", "worleyFB", "mworleyFA", "mworleyFB", "cworleyFA", "cworleyFB")  # STRING menu
_INTERIOR_FRACTAL = ("none", "fBm", "mfT", "hmfT")                   # rbdinteriordetail fractal (STRING menu)
_INTERIOR_DEPTHMETHOD = ("mindist", "sdf")                           # depthmethod (Menu=idx)
_CFR_CONNTYPE = ("surface", "hinge", "centroid")                     # rbdconstraintsfromrules connectiontype (Menu=idx)
_CAP_CONNTYPE = ("points", "pieces", "pointcloud")                   # connectadjacentpieces connecttype (Menu=idx)


@endpoint("rbd_voronoi")
def rbd_voronoi(params):
    """Raw (non-material) Voronoi fracture for art-directed control: source -> scatter -> voronoifracture
    ::2.0 (Geometry in0, cell Points in1). Unlike rbdmaterialfracture this has no material presets — just
    cell fracture with explicit interior/exterior surfacing. Fresh /obj geo `name`. Emits Fractured
    Geometry (out0) + a Constraint Geometry stub (out1). Optional voronoisplit progressive cut.

    pieces (scatter point count = #cells, default 25), seed, namemethod (overwrite|append), nameprefix,
    createinteriorsurfaces, computeinteriornormals(+interiorcuspangle), computeexteriornormals
    (preserve|recompute|none)(+exteriorcuspangle), triangulation (autodetect|2d|3d|useexisting),
    interiorgroup/exteriorgroup (names; enable their output*group toggle), cutplaneoffset. Progressive
    cut: split=true -> a voronoisplit after the fracture (weightmethod power|ratio, split_offset). Cooks
    the terminal fracture (a mesh op, safe); the Bullet solve is a separate call."""
    name = params["name"]
    display = bool(params.get("display", False))
    pieces = int(clamp(int(params.get("pieces", 25)), 1, 1000000))
    seed = float(params.get("seed", 0.0))
    g = _fresh_geo(name)
    src = _src_node(g, params.get("source_geo"), "box",
                    lambda n: n.parmTuple("size").set((10.0, 3.0, 10.0)))
    sc = g.createNode("scatter::2.0", "cells")
    sc.setFirstInput(src)
    _try_set(sc, "forcetotal", 1)
    _try_set(sc, "npts", pieces)
    _try_set(sc, "seed", seed)
    frac = g.createNode("voronoifracture::2.0", "voronoi")
    frac.setInput(0, src)
    frac.setInput(1, sc)
    applied = {}
    if "namemethod" in params:
        applied["namemethod"] = _menu_set(frac, "namemethod", str(params["namemethod"]), _VORO_NAMEMETHOD)
    if "nameprefix" in params:
        applied["nameprefix"] = _try_set(frac, "nameprefix", str(params["nameprefix"]))
    if "createinteriorsurfaces" in params:
        applied["createinteriorsurfaces"] = _try_set(frac, "createinteriorsurfaces", bool(params["createinteriorsurfaces"]))
    if "computeinteriornormals" in params:
        applied["computeinteriornormals"] = _try_set(frac, "computeinteriornormals", bool(params["computeinteriornormals"]))
    if "interiorcuspangle" in params:
        applied["interiorcuspangle"] = _try_set(frac, "interiorcuspangle", clamp(float(params["interiorcuspangle"]), 0.0, 180.0))
    if "computeexteriornormals" in params:
        applied["computeexteriornormals"] = _menu_set(frac, "computeexteriornormals", str(params["computeexteriornormals"]), _VORO_EXTNORMALS)
    if "exteriorcuspangle" in params:
        applied["exteriorcuspangle"] = _try_set(frac, "exteriorcuspangle", clamp(float(params["exteriorcuspangle"]), 0.0, 180.0))
    if "triangulation" in params:
        applied["triangulation"] = _menu_set(frac, "triangulation", str(params["triangulation"]), _VORO_TRIANGULATION)
    if "interiorgroup" in params:
        _try_set(frac, "outputinteriorgroup", 1)
        applied["interiorgroup"] = _try_set(frac, "interiorgroup", str(params["interiorgroup"]))
    if "exteriorgroup" in params:
        _try_set(frac, "outputexteriorgroup", 1)
        applied["exteriorgroup"] = _try_set(frac, "exteriorgroup", str(params["exteriorgroup"]))
    if "cutplaneoffset" in params:
        applied["cutplaneoffset"] = _try_set(frac, "cutplaneoffset", clamp(float(params["cutplaneoffset"]), -1e6, 1e6))
    terminal = frac
    split = None
    if params.get("split"):
        split = g.createNode("voronoisplit", "voronoi_split")
        split.setInput(0, frac, 0)
        split.setInput(1, sc)
        if "weightmethod" in params:
            applied["weightmethod"] = _menu_set(split, "weightmethod", str(params["weightmethod"]), _VOROSPLIT_WEIGHT)
        if "split_offset" in params:
            applied["split_offset"] = _try_set(split, "offset", clamp(float(params["split_offset"]), -1e6, 1e6))
        terminal = split
    terminal.setDisplayFlag(display)
    terminal.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    governor_gate("rbd_voronoi")  # advisory heavy-cook gate; refuses only in the catastrophic band
    frac.cook(force=True)
    result = {"node": g.path(), "scatter": sc.path(), "fracture": frac.path(), "terminal": terminal.path(),
              "pieces_requested": pieces, "fracture_prims": len(frac.geometry().prims()), "applied": applied}
    if split is not None:
        result["split"] = split.path()
    return result


@endpoint("rbd_interior")
def rbd_interior(params):
    """Interior-face detail on already-fractured geometry (rbdinteriordetail SOP): displaces the interior
    (`inside` group) crack faces with noise so broken concrete/rock reads as real inside, not flat cuts.
    `input` = a fractured-geo SOP (e.g. sim_rbd's fracture, rbd_voronoi); the node is wired after it
    (Geometry in0). Cooks once (a mesh displacement, safe).

    interiorgroup (default 'inside'), noiseamp, noisetype (value_fast|sparse|alligator|perlin|flow|
    simplex|worleyFA|worleyFB|mworleyFA|mworleyFB|cworleyFA|cworleyFB — STRING menu), noisefreq [x,y,z],
    noiseoffset [x,y,z], fractal (none|fBm|mfT|hmfT — STRING menu, fBm capitalization matters), oct, lac,
    rough, dispfreq, dolwarp(+accuml), dogwarp(+accumg), depthmethod (mindist|sdf), depthsamplediv,
    pointdepthattrib (str: outputs a per-point depth attr). BUILT (one cook)."""
    n = child_after(params["input"], "rbdinteriordetail", params.get("name"))
    applied = {}
    if "interiorgroup" in params:
        applied["interiorgroup"] = _try_set(n, "interiorgroup", str(params["interiorgroup"]))
    if "noiseamp" in params:
        applied["noiseamp"] = _try_set(n, "noiseamp", clamp(float(params["noiseamp"]), 0.0, 1e6))
    if "noisetype" in params:
        applied["noisetype"] = _str_menu_set(n, "noisetype", str(params["noisetype"]), _INTERIOR_NOISETYPE)
    if "noisefreq" in params:
        applied["noisefreq"] = _set_vec(n, "noisefreq", params["noisefreq"])
    if "noiseoffset" in params:
        applied["noiseoffset"] = _set_vec(n, "noiseoffset", params["noiseoffset"])
    if "fractal" in params:
        applied["fractal"] = _str_menu_set(n, "fractal", str(params["fractal"]), _INTERIOR_FRACTAL)
    if "oct" in params:
        applied["oct"] = _try_set(n, "oct", clamp(float(params["oct"]), 1.0, 20.0))
    if "lac" in params:
        applied["lac"] = _try_set(n, "lac", clamp(float(params["lac"]), 0.0, 1e4))
    if "rough" in params:
        applied["rough"] = _try_set(n, "rough", clamp(float(params["rough"]), 0.0, 1e4))
    if "dispfreq" in params:
        applied["dispfreq"] = _try_set(n, "dispfreq", clamp(float(params["dispfreq"]), 0.0, 1e6))
    if "dolwarp" in params:
        applied["dolwarp"] = _try_set(n, "dolwarp", bool(params["dolwarp"]))
    if "accuml" in params:
        applied["accuml"] = _try_set(n, "accuml", bool(params["accuml"]))
    if "dogwarp" in params:
        applied["dogwarp"] = _try_set(n, "dogwarp", bool(params["dogwarp"]))
    if "accumg" in params:
        applied["accumg"] = _try_set(n, "accumg", bool(params["accumg"]))
    if "depthmethod" in params:
        applied["depthmethod"] = _menu_set(n, "depthmethod", str(params["depthmethod"]), _INTERIOR_DEPTHMETHOD)
    if "depthsamplediv" in params:
        applied["depthsamplediv"] = _try_set(n, "depthsamplediv", int(clamp(int(params["depthsamplediv"]), 1, 100000)))
    if "pointdepthattrib" in params:
        _try_set(n, "outputpointdepthattrib", 1)
        applied["pointdepthattrib"] = _try_set(n, "pointdepthattrib", str(params["pointdepthattrib"]))
    n.cook(force=True)
    return {"node": n.path(), "rbdinteriordetail": n.path(), "applied": applied}


@endpoint("rbd_constraints")
def rbd_constraints(params):
    """Build the constraint NETWORK GEOMETRY (the bond graph the solver reads) from fractured pieces.
    `input` = a fractured-geo SOP (pieces named per-piece). Two methods:
      method=rules (default) -> rbdconstraintsfromrules: rich rule-based connections. connectiontype
        (surface|hinge|centroid), searchradius, maxsearchpoints, maxconnections, constraintsperpiece
        (-1 = unlimited), pieceattribute (default 'name'), groupname, tag.
      method=adjacency -> connectadjacentpieces: pure adjacency lines. searchradius, coneangle (gated),
        mindist (gated), maxconnections, connecttype (points|pieces|pointcloud).
    Output constraint prims are polylines connecting piece centroids; pair with rbd_constraint_properties
    to author the breaking physics, then wire into a solver. BUILT (one cook)."""
    method = str(params.get("method", "rules"))
    if method == "adjacency":
        n = child_after(params["input"], "connectadjacentpieces", params.get("name"))
        applied = {}
        if "connecttype" in params:
            applied["connecttype"] = _menu_set(n, "connecttype", str(params["connecttype"]), _CAP_CONNTYPE)
        if "searchradius" in params:
            applied["searchradius"] = _try_set(n, "searchradius", clamp(float(params["searchradius"]), 0.0, 1e6))
        if "maxsearchpoints" in params:
            applied["maxsearchpoints"] = _try_set(n, "maxsearchpoints", int(clamp(int(params["maxsearchpoints"]), 1, 1000000)))
        if "coneangle" in params:
            _try_set(n, "useconeangle", 1)
            applied["coneangle"] = _try_set(n, "coneangle", clamp(float(params["coneangle"]), 0.0, 180.0))
        if "mindist" in params:
            _try_set(n, "usemindist", 1)
            applied["mindist"] = _try_set(n, "mindist", clamp(float(params["mindist"]), 0.0, 1e6))
        if "maxconnections" in params:
            applied["maxconnections"] = _try_set(n, "maxconnections", int(clamp(int(params["maxconnections"]), 1, 1000000)))
    else:
        n = child_after(params["input"], "rbdconstraintsfromrules", params.get("name"))
        applied = {}
        if "connectiontype" in params:
            applied["connectiontype"] = _menu_set(n, "connectiontype", str(params["connectiontype"]), _CFR_CONNTYPE)
        if "searchradius" in params:
            applied["searchradius"] = _try_set(n, "rule_searchradius", clamp(float(params["searchradius"]), 0.0, 1e6))
        if "maxsearchpoints" in params:
            applied["maxsearchpoints"] = _try_set(n, "rule_maxsearchpoints", int(clamp(int(params["maxsearchpoints"]), 1, 1000000)))
        if "maxconnections" in params:
            applied["maxconnections"] = _try_set(n, "rule_maxconnections", int(clamp(int(params["maxconnections"]), 1, 1000000)))
        if "constraintsperpiece" in params:
            applied["constraintsperpiece"] = _try_set(n, "rule_constraintsperpiece", int(clamp(int(params["constraintsperpiece"]), -1, 1000000)))
        if "pieceattribute" in params:
            applied["pieceattribute"] = _try_set(n, "rule_pieceattrib", str(params["pieceattribute"]))
        if "groupname" in params:
            applied["groupname"] = _try_set(n, "groupname", str(params["groupname"]))
        if "tag" in params:
            applied["tag"] = _try_set(n, "tag", str(params["tag"]))
    n.cook(force=True)
    con_prims = 0
    try:
        cg = n.geometry(1)
        con_prims = len(cg.prims()) if cg is not None else 0
    except Exception:
        pass
    return {"node": n.path(), "constraints": n.path(), "method": method,
            "constraint_prims": con_prims, "applied": applied}


@endpoint("rbd_configure")
def rbd_configure(params):
    """Per-piece dynamics + activation on fractured pieces (rbdconfigure SOP). `input` = a fractured-geo
    SOP; the node is wired after it (Geometry in0). Writes attributes the solver honours, via the node's
    `attributes` multiparm (instance 1). Each value rides an add-gate flipped automatically.

    group (piece group to target; '' = all), active (0/1 static-vs-dynamic), animated (0/1), density,
    bounce, friction, minactivationimpulse (**animated-static -> dynamic on impact trigger**),
    allowinitialoverlap (0/1), type (0-3 density-preset menu), pintype (0-2), visualize (0-10 viewport
    colour-by menu), stickyimpulse (min sticky-collision impulse). BUILT (one cook)."""
    n = child_after(params["input"], "rbdconfigure", params.get("name"))
    _try_set(n, "attributes", 1)     # ensure one attribute rule instance exists
    applied = {}
    if "visualize" in params:
        applied["visualize"] = _try_set(n, "visualize", int(clamp(int(params["visualize"]), 0, 10)))
    if "group" in params:
        applied["group"] = _try_set(n, "group1", str(params["group"]))
    if "active" in params:
        applied["active"] = _set_gated(n, "addactive1", "active1", int(clamp(int(params["active"]), 0, 1)))
    if "animated" in params:
        applied["animated"] = _set_gated(n, "addanimated1", "animated1", int(clamp(int(params["animated"]), 0, 1)))
    if "density" in params:
        applied["density"] = _set_gated(n, "adduserdensity1", "userdensity1", clamp(float(params["density"]), 1e-3, 1e9))
    if "bounce" in params:
        applied["bounce"] = _set_gated(n, "adduserbounce1", "userbounce1", clamp(float(params["bounce"]), 0.0, 1e4))
    if "friction" in params:
        applied["friction"] = _set_gated(n, "adduserfriction1", "userfriction1", clamp(float(params["friction"]), 0.0, 1e4))
    if "minactivationimpulse" in params:
        applied["minactivationimpulse"] = _set_gated(n, "addminactivationimpulse1", "minactivationimpulse1",
                                                     clamp(float(params["minactivationimpulse"]), 0.0, 1e12))
    if "allowinitialoverlap" in params:
        applied["allowinitialoverlap"] = _set_gated(n, "addallowinitialoverlap1", "allowinitialoverlap1",
                                                    int(clamp(int(params["allowinitialoverlap"]), 0, 1)))
    if "stickyimpulse" in params:
        applied["stickyimpulse"] = _set_gated(n, "addminstickycollisionimpulse1", "minstickycollisionimpulse1",
                                              clamp(float(params["stickyimpulse"]), -1e12, 1e12))
    if "type" in params:
        applied["type"] = _try_set(n, "type1", int(clamp(int(params["type"]), 0, 3)))
    if "pintype" in params:
        applied["pintype"] = _try_set(n, "pintype1", int(clamp(int(params["pintype"]), 0, 2)))
    # activation region: wire a bounds SOP into the Static Bounds Geometry input (index 3) + gate it —
    # pieces inside the bounds become active (region-driven activation). Cross-network -> object_merge.
    if params.get("bounds"):
        b = resolve_node(str(params["bounds"]))
        if b.parent() == n.parent():
            n.setInput(3, b, 0)
        else:
            om = n.parent().createNode("object_merge", "active_bounds")
            _try_set(om, "objpath1", b.path())
            try:
                om.cook(force=True)
            except Exception:  # noqa: BLE001
                pass
            n.setInput(3, om, 0)
        applied["bounds"] = _try_set(n, "useactivebounds1", 1)
    n.cook(force=True)
    return {"node": n.path(), "rbdconfigure": n.path(), "applied": applied}


@endpoint("rbd_collision")
def rbd_collision(params):
    """The TERRAIN BRIDGE: wire a mesh/heightfield collider into an existing rbdbulletsolver's Collision
    Geometry input (index 3) so debris settles on real captured terrain. `solver` = the rbdbulletsolver
    SOP (from sim_rbd); `collider` = a DEM heightfield or mesh SOP. The collider is object-merged into
    the solver's parent, converted to polys if a heightfield, and wired to input 3; the solver's collision
    response is tuned (georep, initial state, bounce/friction).

    heightfield (bool, default true -> convertheightfield; false = mesh collider used directly), lod
    (heightfield decimation), georep (convexhull|concave|box|capsule|cylinder|compound|sphere|plane;
    concave = true DEM surface), collision_initialstate (static|animatedstatic|deformingstatic),
    collision_margin/collision_bounce/collision_friction, useground (0|1|2 static plane) + ground_pos.
    Cooks the heightfield conversion only (a mesh; never a sim). BUILT — the caller scrubs to run."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "rbdbulletsolver":
        raise ValueError("`solver` must be an rbdbulletsolver SOP (got %s)" % solv.type().name())
    parent = solv.parent()
    om = parent.createNode("object_merge", params.get("name") or "rbd_collider")
    _try_set(om, "objpath1", str(params["collider"]))
    node, out = om, 0
    conv = None
    cooked = False
    if bool(params.get("heightfield", True)):
        conv = parent.createNode("convertheightfield", "collider_polys")
        conv.setFirstInput(om)
        _try_set(conv, "lod", clamp(float(params.get("lod", 1.0)), 0.01, 1.0))
        conv.cook(force=True)     # single safe mesh cook
        node, out, cooked = conv, 0, True
    solv.setInput(3, node, out)
    _try_set(solv, "usecollisions", 1)
    applied = {"usecollisions": True}
    georep = str(params.get("georep", "concave"))
    applied["georep"] = _str_menu_set(solv, "collision_bullet_georep", georep, _RBD_GEOREP)
    if "collision_initialstate" in params:
        applied["collision_initialstate"] = _menu_set(solv, "collision_initialstate",
                                                      str(params["collision_initialstate"]), _RBD_INITIALSTATE)
    if "collision_margin" in params:
        applied["collision_margin"] = _try_set(solv, "collision_margin", clamp(float(params["collision_margin"]), 0.0, 1e4))
    if "collision_bounce" in params:
        applied["collision_bounce"] = _try_set(solv, "collision_bounce", clamp(float(params["collision_bounce"]), 0.0, 1e4))
    if "collision_friction" in params:
        applied["collision_friction"] = _try_set(solv, "collision_friction", clamp(float(params["collision_friction"]), 0.0, 1e4))
    if "useground" in params:
        applied["useground"] = _try_set(solv, "useground", int(clamp(int(params["useground"]), 0, 2)))
    if "ground_pos" in params:
        _try_set(solv, "useground", 1)
        applied["ground_pos"] = _set_vec(solv, "ground_pos", params["ground_pos"])
    try:
        parent.layoutChildren()
    except Exception:
        pass
    result = {"node": solv.path(), "solver": solv.path(), "collider_merge": om.path(),
              "collider_wired": solv.input(3) is not None, "converted": cooked, "applied": applied}
    if conv is not None:
        result["convert"] = conv.path()
    return result


# ftype -> live DOP force node for the RBD lane (popexplosion does NOT exist; blast = popaxisforce).
_RBD_FORCE_MAP = {"wind": "windforce", "uniform": "uniformforce", "current": "uniformforce",
                  "point": "pointforce", "vortex": "vortexforce", "explosion": "popaxisforce",
                  "blast": "popaxisforce", "fan": "fan", "drag": "drag"}
_RBD_FORCE_DIR = {"wind": (0.0, 0.0, 1.0), "uniform": (0.0, -1.0, 0.0), "current": (1.0, 0.0, 0.0),
                  "explosion": (0.0, 1.0, 0.0), "blast": (0.0, 1.0, 0.0), "fan": (0.0, 0.0, 1.0),
                  "point": (1.0, 0.0, 0.0)}


@endpoint("rbd_force")
def rbd_force(params):
    """Richer forces than the solver's built-in gravity+drag, as a typed DOP force node (NO VEX):
    ftype -> node -- wind->windforce, uniform/current->uniformforce, point->pointforce, vortex->
    vortexforce, fan->fan, drag->drag, explosion/blast->popaxisforce (radial sphere shockwave — the
    destruction force; popexplosion does NOT exist in H21). Built inside an existing `dopnet` if given,
    else a fresh /obj geo `name` holding a dopnet. The force is BUILT, not auto-wired (merge it into the
    RBD solver's forces / DOP network to apply).

    Common: strength, direction [x,y,z], center [x,y,z] (point/fan/explosion). explosion/blast:
    innerstrength=strength (outward), outerstrength, orbitspeed, radius. BUILT."""
    ftype = str(params.get("ftype", "explosion"))
    if ftype not in _RBD_FORCE_MAP:
        raise ValueError("unknown ftype: %s (want %s)" % (ftype, "/".join(sorted(_RBD_FORCE_MAP))))
    ntype = _RBD_FORCE_MAP[ftype]
    g = None
    if params.get("dopnet"):
        dn = hou.node(str(params["dopnet"]))
        if dn is None:
            raise ValueError("no such dopnet: %s" % params["dopnet"])
    else:
        if not params.get("name"):
            raise ValueError("rbd_force needs `name` (for a fresh holder) or `dopnet`")
        g = _fresh_geo(params["name"])
        dn = g.createNode("dopnet", "forces")
    force = dn.createNode(ntype, params.get("node_name") or ftype)
    strength = float(params["strength"]) if "strength" in params else 1.0
    direction = params.get("direction") or _RBD_FORCE_DIR.get(ftype, (0.0, 1.0, 0.0))
    direction = tuple(float(x) for x in direction)
    applied = {}
    if ntype == "uniformforce":
        applied["force"] = _set_vec(force, "force", tuple(d * strength for d in direction))
    elif ntype == "pointforce":
        applied["force"] = _set_vec(force, "force", tuple(d * strength for d in direction))
        if "center" in params:
            applied["center"] = _set_vec(force, "t", params["center"])
    elif ntype == "windforce":
        applied["direction"] = _set_vec(force, "vel", direction)
        applied["strength"] = _try_set(force, "scaleforce", clamp(strength, 0.0, 1e9))
    elif ntype == "drag":
        applied["strength"] = _try_set(force, "forcescale", clamp(strength, 0.0, 1e9))
    elif ntype == "vortexforce":
        applied["falloff"] = _try_set(force, "falloff", clamp(float(params.get("falloff", 1.0)), 0.0, 1e4))
        if "strength" in params:
            applied["strength"] = _try_set(force, "dragconstant", clamp(strength, 0.0, 1e9))
    elif ntype == "fan":
        applied["direction"] = _set_vec(force, "direction", direction)
        applied["strength"] = _try_set(force, "flux", clamp(strength if "strength" in params else 1e6, 0.0, 1e12))
        if "center" in params:
            applied["center"] = _set_vec(force, "t", params["center"])
    elif ntype == "popaxisforce":            # explosion / blast — radial sphere shockwave
        _try_set(force, "type", 0)           # sphere
        applied["direction"] = _set_vec(force, "dir", direction)
        applied["innerstrength"] = _try_set(force, "innerstrength", clamp(strength, -1e9, 1e9))
        _try_set(force, "outerstrength", clamp(float(params.get("outerstrength", 0.0)), -1e9, 1e9))
        if "orbitspeed" in params:
            _try_set(force, "orbitspeed", clamp(float(params["orbitspeed"]), -1e9, 1e9))
        if "radius" in params:
            _try_set(force, "r", clamp(float(params["radius"]), 0.0, 1e9))
        if "center" in params:
            applied["center"] = _set_vec(force, "t", params["center"])
    try:
        dn.layoutChildren()
    except Exception:
        pass
    result = {"node": force.path(), "force": force.path(), "dopnet": dn.path(),
              "ftype": ftype, "node_type": ntype, "applied": applied}
    if g is not None:
        display = bool(params.get("display", False))
        dn.setDisplayFlag(display)
        g.setDisplayFlag(display)
        g.layoutChildren()
        result["geo"] = g.path()
    return result


@endpoint("rbd_cache")
def rbd_cache(params):
    """BUILD (never write) a File Cache 2.0 SOP after an RBD sim to cache it to disk. `input` = the SOP to
    cache (e.g. an rbdbulletsolver). Same confined write contract as flip_cache/pyro_cache (FsPath
    write:true): `file` = the explicit output path (filemethod=explicit), confined to the working dir.

    HEAVY-OP GUARDRAIL: this ONLY builds and configures the filecache node -- it NEVER presses Save to
    Disk / executes the cook. Writing a multi-frame Bullet cache on the executor main thread would block
    the session, so the caller/operator triggers the write (the node's 'Save to Disk' button or a ROP).

    trange (single|range -> `trange` off|normal), frames [start, end], substeps, filetype (.bgeo.sc|.vdb),
    basename, loadfromdisk. Returns node + write_path + trange + frames (written=false)."""
    out_path = confined_path(params["file"])
    n = child_after(params["input"], "filecache::2.0", params.get("name"))
    applied = {}
    _menu_set(n, "filemethod", "explicit", _FC_FILEMETHOD)
    applied["file"] = _try_set(n, "file", out_path)
    _try_set(n, "mkpath", True)
    if "filetype" in params:
        applied["filetype"] = _menu_set(n, "filetype", str(params["filetype"]), _FC_FILETYPE)
    if "basename" in params:
        _try_set(n, "basename", str(params["basename"]))
    trange_tok = None
    if "trange" in params:
        trange_tok = "normal" if str(params["trange"]) in ("range", "normal") else "off"
    frames = params.get("frames")
    if frames and len(frames) >= 2:
        trange_tok = "normal"
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        ft = n.parmTuple("f")
        if ft is not None and len(ft) >= 2:
            for idx, val in ((0, float(f1)), (1, float(f2))):
                try:
                    ft[idx].deleteAllKeyframes()
                except Exception:
                    pass
                try:
                    ft[idx].set(val)
                except Exception:
                    pass
            applied["frames"] = [f1, f2]
    if trange_tok is not None:
        applied["trange"] = _menu_set(n, "trange", trange_tok, _FC_TRANGE)
    if "substeps" in params:
        applied["substeps"] = _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "loadfromdisk" in params:
        applied["loadfromdisk"] = _try_set(n, "loadfromdisk", bool(params["loadfromdisk"]))
    # NO n.render()/execute — the write is the caller's job (heavy-op guardrail).
    return {"node": n.path(), "filecache": n.path(), "write_path": out_path,
            "trange": (n.parm("trange").evalAsString() if n.parm("trange") else None),
            "frames": applied.get("frames"), "written": False, "applied": applied,
            "note": "filecache BUILT + configured; press Save to Disk / trigger the write yourself"}


@endpoint("rbd_exploded")
def rbd_exploded(params):
    """Debug/inspection: spread fractured pieces apart along their normals for a clear look at the break
    (rbdexplodedview SOP). `input` = a fractured/simulated RBD SOP; wired after it. Read-only display
    layer — no sim change. Cooks once (a cheap transform).

    scale (spread amount; gated by doscale), offset (small gap), showproxy (show proxy geo), modifyproxy
    (0 none|1 ..|2 .. index), group (piece group to explode; '' = all). BUILT."""
    n = child_after(params["input"], "rbdexplodedview", params.get("name"))
    applied = {}
    if "scale" in params:
        _try_set(n, "doscale", 1)
        applied["scale"] = _try_set(n, "scale", clamp(float(params["scale"]), 0.0, 1e6))
    if "offset" in params:
        applied["offset"] = _try_set(n, "offset", clamp(float(params["offset"]), -1e6, 1e6))
    if "showproxy" in params:
        applied["showproxy"] = _try_set(n, "showproxy", bool(params["showproxy"]))
    if "modifyproxy" in params:
        applied["modifyproxy"] = _try_set(n, "modifyproxy", int(clamp(int(params["modifyproxy"]), 0, 2)))
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    n.cook(force=True)
    return {"node": n.path(), "rbdexplodedview": n.path(), "applied": applied}


@endpoint("rbd_destruction")
def rbd_destruction(params):
    """THE TERRAIN DESTRUCTION MACRO (the moat): fracture a reconstructed asset and collapse it onto real
    captured terrain, end-to-end in one call. Fresh /obj geo `name` holding:
      building (object_merge `building_geo`/`source_geo`, else a default box)
        -> rbdmaterialfracture::3.0 (material preset + glue-constraint emission, `strength` = breaking
           threshold baked at fracture)
        -> [optional rbdconstraintproperties::2.0 if `glue_strength` given -> re-author the breaking dial]
        -> rbdbulletsolver: Geometry(in0) + Constraint Geometry(in1) + Collision Geometry(in3) =
           the terrain DEM (object_merge `terrain_geo` -> convertheightfield when a heightfield),
           gravity + georep=concave + optional ground plane.
    Only the fracture + the terrain conversion are cooked (mesh ops, safe); the Bullet solve is BUILT,
    never auto-simulated (the caller scrubs). Unlocks: a reconstructed building shattering onto a scanned
    slope, a rockslide down a real hillside, debris settling into a captured valley.

    building_geo/source_geo (the asset; else default box), terrain_geo (the DEM/mesh collider),
    terrain_heightfield (bool, default true -> convertheightfield), lod. Fracture: materialtype
    (concrete|glass|wood|custom), seed, strength, + any rbd_fracture key. Constraints: glue_strength
    (re-author via rbdconstraintproperties), strengthvariance. Solver: density, friction, bounce,
    substeps, gravity [x,y,z] (default [0,-9.8,0]), georep (default concave), useground (0|1|2),
    ground_pos. Returns the full node set + fracture prims + collider_wired."""
    name = params["name"]
    display = bool(params.get("display", False))
    mat = str(params.get("materialtype", "concrete"))
    if mat not in _RBD_MATERIALTYPE:
        mat = "concrete"
    seed = float(params.get("seed", 0.0))
    g = _fresh_geo(name)
    # -- building asset --
    src = _src_node(g, params.get("building_geo") or params.get("source_geo"), "box",
                    lambda n: n.parmTuple("size").set((6.0, 12.0, 6.0)))
    # -- fracture (+ built-in glue emission) --
    frac = g.createNode("rbdmaterialfracture::3.0", "fracture")
    frac.setFirstInput(src)
    applied = {}
    applied["materialtype"] = _menu_set(frac, "materialtype", mat, _RBD_MATERIALTYPE)
    _try_set(frac, "randomseed", seed)
    fp = dict(params)
    fp.setdefault("applyconstraints", True)
    _apply_rbd_fracture(frac, mat, fp, applied)
    governor_gate("rbd_destruction")  # advisory heavy-cook gate; refuses only in the catastrophic band
    frac.cook(force=True)
    # -- solver --
    sim = g.createNode("rbdbulletsolver", "solver")
    sim.setInput(0, frac, 0)
    sim.setInput(1, frac, 1)
    con_source = (frac, 1)
    # -- optional re-author the breaking dial on the emitted network --
    cp = None
    if "glue_strength" in params:
        cp = g.createNode("rbdconstraintproperties::2.0", "glue")
        cp.setInput(0, frac, 0)
        cp.setInput(1, frac, 1)
        _try_set(cp, "action", 1)
        _try_set(cp, "doconstrainttype", 1)
        _menu_set(cp, "constrainttype", "glue", _RBD_CTYPE)
        applied["glue_strength"] = _set_gated(cp, "doglue_strength", "glue_strength",
                                              clamp(float(params["glue_strength"]), 0.0, 1e12))
        if "strengthvariance" in params:
            _try_set(cp, "glue_randomizestrength", 1)
            applied["strengthvariance"] = _try_set(cp, "glue_strengthvariance",
                                                   clamp(float(params["strengthvariance"]), 0.0, 1e4))
        cp.cook(force=True)
        sim.setInput(1, cp, 1)
        con_source = (cp, 1)
    # -- terrain collider -> solver Collision Geometry (input 3) --
    conv = None
    om = None
    collider_wired = False
    if params.get("terrain_geo"):
        om = g.createNode("object_merge", "terrain")
        _try_set(om, "objpath1", str(params["terrain_geo"]))
        coll_node, coll_out = om, 0
        if bool(params.get("terrain_heightfield", True)):
            conv = g.createNode("convertheightfield", "terrain_polys")
            conv.setFirstInput(om)
            _try_set(conv, "lod", clamp(float(params.get("lod", 1.0)), 0.01, 1.0))
            conv.cook(force=True)      # single safe mesh cook
            coll_node, coll_out = conv, 0
        sim.setInput(3, coll_node, coll_out)
        _try_set(sim, "usecollisions", 1)
        applied["georep"] = _str_menu_set(sim, "collision_bullet_georep",
                                          str(params.get("georep", "concave")), _RBD_GEOREP)
        collider_wired = sim.input(3) is not None
    # -- solver physics --
    sp = dict(params)
    sp.setdefault("startframe", int(params.get("startframe", 1)))
    sp.setdefault("substeps", int(clamp(int(params.get("substeps", 4)), 1, 100)))
    sp.setdefault("gravity", params.get("gravity", [0.0, -9.8, 0.0]))
    sp.setdefault("enable_constraintbreaks", True)
    _apply_rbd_solver(sim, sp, applied)
    sim.setDisplayFlag(display)
    sim.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    result = {"node": g.path(), "fracture": frac.path(), "solver": sim.path(),
              "materialtype": mat, "fracture_prims": len(frac.geometry().prims()),
              "constraints_wired": sim.input(1) is not None,
              "constraint_source": con_source[0].path(),
              "collider_wired": collider_wired, "applied": applied}
    if cp is not None:
        result["constraintproperties"] = cp.path()
    if om is not None:
        result["terrain_merge"] = om.path()
    if conv is not None:
        result["terrain_convert"] = conv.path()
    return result


def _menu_idx(node, parm, token, mapping):
    """Set an ordered-menu parm by a friendly token mapped to its live menu index (probe-safe)."""
    p = node.parm(parm)
    if p is None or token not in mapping:
        return False
    try:
        p.set(mapping[token])
        return True
    except Exception:
        return False


# Live menu tokens (probed on H21.0.671 — capitalization/order matter).
_VELTRANSFER = ("flip", "apic")                       # flipsolver.veltransfer
_FLIP_COLLISION = ("none", "particle", "movetoiso")   # flipsolver.collision


def _apply_flip_container(cont, params):
    """Deep flipcontainer param sets (all probe-verified). Returns dict of what applied."""
    a = {}
    if "particlesep" in params:
        a["particlesep"] = _try_set(cont, "particlesep", clamp(float(params["particlesep"]), 1e-3, 1e4))
    if "gridscale" in params:
        # gridscale = grid voxels per particle-separation (finer grid = MUCH more RAM: scale^3 the
        # voxel count). Live UI cap is ~2.0; clamp to a cost-sane 4.0 (32 would be catastrophic).
        a["gridscale"] = _try_set(cont, "gridscale", clamp(float(params["gridscale"]), 1.0, 4.0))
    if "density" in params:
        a["density"] = _try_set(cont, "density", clamp(float(params["density"]), 1e-3, 1e9))
    if "gravity" in params:
        a["gravity"] = _try_set(cont, "gravity", clamp(float(params["gravity"]), 0.0, 1e6))
    if "gravitydir" in params and cont.parmTuple("gravitydir") is not None:
        v = params["gravitydir"]
        try:
            cont.parmTuple("gravitydir").set((float(v[0]), float(v[1]), float(v[2])))
            a["gravitydir"] = True
        except Exception:
            a["gravitydir"] = False
    if "surfacetension" in params:
        _try_set(cont, "dosurfacetension", 1)
        a["surfacetension"] = _try_set(cont, "surfacetension", clamp(float(params["surfacetension"]), 0.0, 1e6))
    # viscosity: container `viscosity` is an ENABLE toggle; magnitude is `default_viscosity`.
    if "viscosity" in params:
        val = clamp(float(params["viscosity"]), 0.0, 1e6)
        _try_set(cont, "viscosity", 1 if val > 0 else 0)
        a["viscosity"] = _try_set(cont, "default_viscosity", val)
        if params.get("varyingviscosity"):
            _try_set(cont, "dovaryingviscosity", 1)
    if "vorticity" in params:
        _try_set(cont, "dovorticity", 1)
        a["vorticity"] = _try_set(cont, "vorticitypreserve", clamp(float(params["vorticity"]), 0.0, 1.0))
    if "slip" in params:
        _try_set(cont, "enableslip", 1)
        a["slip"] = _try_set(cont, "slipscale", clamp(float(params["slip"]), 0.0, 1e4))
    return a


def _apply_flip_solver(fsolve, params):
    """Deep flipsolver param sets (all probe-verified). Returns dict of what applied."""
    a = {}
    if "startframe" in params:
        _try_set(fsolve, "startframe", int(params["startframe"]))
    if "substeps" in params:
        _try_set(fsolve, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    # adaptive-substep throttle (probe-verified H21: flipsolver has NO CFL parm — the bound is min/max/
    # global substeps only). `substeps` parm = "Max Substeps"; `minimumsubsteps` = Min; `substep` = Global
    # (fixed). Set min==max for a fixed substep count.
    if "min_substeps" in params:
        a["min_substeps"] = _try_set(fsolve, "minimumsubsteps", int(clamp(int(params["min_substeps"]), 1, 100)))
    if "max_substeps" in params:
        a["max_substeps"] = _try_set(fsolve, "substeps", int(clamp(int(params["max_substeps"]), 1, 100)))
    if "global_substeps" in params:
        a["global_substeps"] = _try_set(fsolve, "substep", int(clamp(int(params["global_substeps"]), 1, 100)))
    if "timescale" in params:
        a["timescale"] = _try_set(fsolve, "timescale", clamp(float(params["timescale"]), 1e-4, 1e4))
    # velocity smoothing / bands (probe-verified real; H21 has NO velocity-advection substep parm — the
    # advection bound is min/max/global substeps only, already above).
    if "smoothing" in params:
        a["smoothing"] = _try_set(fsolve, "smoothing", clamp(float(params["smoothing"]), 0.0, 1e4))
    if "velocity_band" in params:
        a["velocity_band"] = _try_set(fsolve, "velocityband", clamp(float(params["velocity_band"]), 0.0, 1e4))
    if "source_band" in params:
        a["source_band"] = _try_set(fsolve, "sourceband", clamp(float(params["source_band"]), 0.0, 1e4))
    if "veltransfer" in params:
        a["veltransfer"] = _menu_set(fsolve, "veltransfer", str(params["veltransfer"]), _VELTRANSFER)
    if "collision" in params:
        a["collision"] = _menu_set(fsolve, "collision", str(params["collision"]), _FLIP_COLLISION)
    if "narrowband" in params:
        a["narrowband"] = _try_set(fsolve, "donarrowband", bool(params["narrowband"]))
    if "mgpreconditioner" in params:
        _try_set(fsolve, "usemgpreconditioner", bool(params["mgpreconditioner"]))
    if "adaptivepressure" in params:
        _try_set(fsolve, "useadaptivepressure", bool(params["adaptivepressure"]))
    if "reseeding" in params:
        _try_set(fsolve, "doreseeding", bool(params["reseeding"]))
    if "birththreshold" in params:
        _try_set(fsolve, "birththreshold", clamp(float(params["birththreshold"]), 0.0, 1e4))
    if "deaththreshold" in params:
        _try_set(fsolve, "deaththreshold", clamp(float(params["deaththreshold"]), 0.0, 1e4))
    if "oversampling" in params:
        _try_set(fsolve, "oversampling", clamp(float(params["oversampling"]), 0.0, 1e3))
    if "oversamplingbandwidth" in params:
        _try_set(fsolve, "oversamplingbandwidth", clamp(float(params["oversamplingbandwidth"]), 0.0, 1e3))
    if "seed" in params:
        _try_set(fsolve, "seed", clamp(float(params["seed"]), 0.0, 1e9))
    if "separation" in params and bool(params["separation"]):
        _try_set(fsolve, "partsep", 1)
        if "separation_iter" in params:
            _try_set(fsolve, "partsepiter", int(clamp(int(params["separation_iter"]), 1, 100)))
        if "separation_amount" in params:
            _try_set(fsolve, "partsepamount", clamp(float(params["separation_amount"]), 0.0, 1e4))
        if "separation_scale" in params:
            _try_set(fsolve, "partsepscale", clamp(float(params["separation_scale"]), 0.0, 1e4))
    if "stick" in params:
        _try_set(fsolve, "enablestick", 1)
        a["stick"] = _try_set(fsolve, "stickscale", clamp(float(params["stick"]), 0.0, 1e4))
    if "applycollisiontoair" in params:
        _try_set(fsolve, "applycollisionstoair", bool(params["applycollisiontoair"]))
    # waterline fill (the flood primitive; lives on the SOLVER, not the container)
    if "dowaterline" in params or "waterline" in params:
        _try_set(fsolve, "dowaterline", 1)
        if "waterline" in params:
            a["waterline"] = _try_set(fsolve, "waterline", clamp(float(params["waterline"]), -1e7, 1e7))
        if "waterorigin" in params and fsolve.parmTuple("waterorigin") is not None:
            v = params["waterorigin"]
            try:
                fsolve.parmTuple("waterorigin").set((float(v[0]), float(v[1]), float(v[2])))
                a["waterorigin"] = True
            except Exception:
                a["waterorigin"] = False
    return a


@endpoint("sim_flip")
def sim_flip(params):
    """FLIP fluid (deep container + solver): flipcontainer + flipsolver fed by a source primitive.

    Container (flipcontainer): particlesep, gridscale, density, gravity(+gravitydir), surfacetension,
    viscosity(+varyingviscosity), vorticity, slip. Solver (flipsolver): startframe, substeps, veltransfer
    (flip|apic), collision (none|particle|movetoiso), narrowband, mgpreconditioner, adaptivepressure,
    reseeding, birth/deaththreshold, oversampling(+bandwidth), seed, separation(+iter/amount/scale),
    stick, applycollisiontoair, and waterline fill (dowaterline/waterline/waterorigin). BUILT, not
    auto-simulated. Wiring is label-correct: source->Sources(0), container->Container(1)."""
    name = params["name"]
    frames = int(clamp(int(params.get("frames", 120)), 1, 10000))
    display = bool(params.get("display", False))
    # keep legacy startframe/substeps defaults working even when the caller omits them
    if "startframe" not in params:
        params = dict(params, startframe=1)
    if "substeps" not in params:
        params = dict(params, substeps=int(clamp(int(params.get("substeps", 1)), 1, 100)))
    g = _fresh_geo(name)
    src = _src_node(g, params.get("source_geo"), "box",
                    lambda n: (n.parmTuple("size").set((6.0, 6.0, 6.0)),
                               n.parmTuple("t").set((0.0, 8.0, 0.0)) if n.parmTuple("t") else None))
    cont = g.createNode("flipcontainer")
    fsolve = g.createNode("flipsolver")
    # flipsolver SOP inputs = (Sources=0, Container=1, Collisions=2, Boundary Flow=3);
    # flipcontainer outputs = (Sources=0, Container=1, Collisions=2).
    fsolve.setInput(1, cont, 1)   # Container -> Container
    try:
        fsolve.setInput(0, src)   # source geo -> Sources
    except Exception:
        pass
    applied = {}
    applied.update(_apply_flip_container(cont, params))
    # container bounds (flipcontainer: parmTuple "size" = extents, "t" = center; verified — "center" is None)
    if "size" in params:
        applied["size"] = _set_vec(cont, "size", params["size"])
    if "center" in params:
        applied["center"] = _set_vec(cont, "t", params["center"])
    applied.update(_apply_flip_solver(fsolve, params))
    fsolve.setDisplayFlag(display)
    fsolve.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "container": cont.path(), "solver": fsolve.path(),
            "frames": frames, "applied": applied}


_COLL_APPROX = {"none": 0, "backward": 1, "central": 2, "forward": 3}  # collisionsource::2.0 velapproximation


@endpoint("flip_collision")
def flip_collision(params):
    """Terrain/geometry -> FLIP collision volume via Collision Source 2.0 SOP. The terrain-collision
    bridge: feed its output into a flipsolver's Collisions input (see flip_flood). approximation
    (none|backward|central|forward = velapproximation), velscale, bandwidth, voxelsize, volumename,
    group, computeangular, points, fillinterior, worldspaceunits. Optional flipcollide companion
    (dovolume/dosurface/computevel/velscale). BUILT only (no sim)."""
    n = child_after(params["input"], "collisionsource::2.0", params.get("name"))
    applied = {}
    if "approximation" in params:
        applied["approximation"] = _menu_idx(n, "velapproximation", str(params["approximation"]), _COLL_APPROX)
    if "velscale" in params:
        applied["velscale"] = _try_set(n, "velscale", clamp(float(params["velscale"]), 0.0, 1e6))
    if "bandwidth" in params:
        applied["bandwidth"] = _try_set(n, "bandwidth", clamp(float(params["bandwidth"]), 0.0, 1e4))
    if "voxelsize" in params:
        applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "volumename" in params:
        applied["volumename"] = _try_set(n, "volumename", str(params["volumename"]))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "computeangular" in params:
        _try_set(n, "computeangular", bool(params["computeangular"]))
    if "points" in params:
        _try_set(n, "points", bool(params["points"]))
    if "fillinterior" in params:
        _try_set(n, "fillinterior", bool(params["fillinterior"]))
    if "worldspaceunits" in params:
        _try_set(n, "useworldspaceunits", bool(params["worldspaceunits"]))
    result = {"node": n.path(), "collisionsource": n.path(), "applied": applied}
    if params.get("flipcollide"):
        fc = n.parent().createNode("flipcollide")
        try:
            fc.setFirstInput(n)
        except Exception:
            pass
        _try_set(fc, "dovolume", bool(params.get("dovolume", True)))
        _try_set(fc, "dosurface", bool(params.get("dosurface", True)))
        _try_set(fc, "computevel", bool(params.get("computevel", True)))
        if "velscale" in params:
            _try_set(fc, "velscale", clamp(float(params["velscale"]), 0.0, 1e6))
        n.parent().layoutChildren()
        result["flipcollide"] = fc.path()
    # Wire this collider into an EXISTING flipsolver's Collisions input (index 2) — mirrors
    # rbd_collision's "wire into a live solver" mode. Closes the FLIP collider-into-solver gap: a splash
    # against an arbitrary mesh obstacle, not just terrain (which flip_flood auto-wires). One safe volume
    # cook of the collisionsource (not a sim), then setInput(2).
    if params.get("solver"):
        solv = resolve_node(str(params["solver"]))
        if solv.type().name() != "flipsolver":
            raise ValueError("`solver` must be a flipsolver SOP (got %s)" % solv.type().name())
        try:
            governor_gate("flip_collision")  # advisory heavy-cook gate; refuses only in the catastrophic band
            n.cook(force=True)   # one safe volume cook (not a sim)
        except Exception:  # noqa: BLE001
            pass
        # setInput can't cross SOP networks — if the collisionsource lives in a different network than
        # the solver, bridge it with an object_merge in the solver's parent (the rbd_collision pattern).
        if n.parent() == solv.parent():
            solv.setInput(2, n, 0)                        # Collisions input, same network
        else:
            om = solv.parent().createNode("object_merge", "flip_collider")
            _try_set(om, "objpath1", n.path())
            try:
                om.cook(force=True)
            except Exception:  # noqa: BLE001
                pass
            solv.setInput(2, om, 0)
            solv.parent().layoutChildren()
        result["solver"] = solv.path()
        result["collider_wired"] = solv.input(2) is not None
    return result


@endpoint("flip_flood")
def flip_flood(params):
    """Terrain flood macro: DEM/heightfield -> convertheightfield -> collisionsource::2.0 collider ->
    sized flipcontainer -> flipsolver, with the collider wired into the solver's Collisions input.
    Water via mode a (dowaterline + waterlevel) and/or mode b (a box source over `source_region`).
    The container is auto-sized to the DEM bbox (+padding, +headroom above the waterline). BUILT, never
    auto-simulated (the caller scrubs). One cook of the heightfield conversion only — no sim on the
    main thread. `input` = the DEM heightfield SOP; `waterlevel` = absolute fill height (up axis)."""
    name = params["name"]
    display = bool(params.get("display", False))
    pad = clamp(float(params.get("padding", 1.05)), 1.0, 4.0)
    headroom = clamp(float(params.get("headroom", 10.0)), 0.0, 1e6)
    g = _fresh_geo(name)
    # bring the DEM heightfield in
    om = g.createNode("object_merge", "dem")
    _try_set(om, "objpath1", str(params["input"]))
    conv = g.createNode("convertheightfield", "dem_polys")
    conv.setFirstInput(om)
    _try_set(conv, "lod", clamp(float(params.get("lod", 1.0)), 0.01, 1.0))
    geo = conv.geometry()  # single cook of the conversion (safe: mesh, not a sim)
    bbox = geo.boundingBox()
    smin, smax = bbox.minvec(), bbox.maxvec()
    cx, cz = (smin[0] + smax[0]) * 0.5, (smin[2] + smax[2]) * 0.5
    dx, dz = (smax[0] - smin[0]) * pad, (smax[2] - smin[2]) * pad
    terr_min_y, terr_max_y = smin[1], smax[1]
    waterlevel = float(params.get("waterlevel", terr_min_y + (terr_max_y - terr_min_y) * 0.5))
    top = max(waterlevel, terr_max_y) + headroom
    height = max(top - terr_min_y, 1e-3)
    # collider
    coll = g.createNode("collisionsource::2.0", "collider")
    coll.setFirstInput(conv)
    _try_set(coll, "velapproximation", 0)  # static terrain -> no collider velocity
    if "bandwidth" in params:
        _try_set(coll, "bandwidth", clamp(float(params["bandwidth"]), 0.0, 1e4))
    if "voxelsize" in params:
        _try_set(coll, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    # sized container
    cont = g.createNode("flipcontainer", "container")
    if cont.parmTuple("size") is not None:
        cont.parmTuple("size").set((dx, height, dz))
    if cont.parmTuple("t") is not None:
        cont.parmTuple("t").set((cx, terr_min_y + height * 0.5, cz))
    _apply_flip_container(cont, params)
    # solver + wiring: Container(1), Collisions(2), Sources(0)
    fsolve = g.createNode("flipsolver", "solver")
    fsolve.setInput(1, cont, 1)      # Container
    fsolve.setInput(2, coll, 0)      # collisionsource Geometry -> Collisions
    mode = None
    src = None
    region = params.get("source_region")
    if region and len(region) >= 6:
        rx0, ry0, rz0, rx1, ry1, rz1 = [float(v) for v in region[:6]]
        src = g.createNode("box", "source")
        if src.parmTuple("size") is not None:
            src.parmTuple("size").set((abs(rx1 - rx0), abs(ry1 - ry0), abs(rz1 - rz0)))
        if src.parmTuple("t") is not None:
            src.parmTuple("t").set(((rx0 + rx1) * 0.5, (ry0 + ry1) * 0.5, (rz0 + rz1) * 0.5))
        fsolve.setInput(0, src)      # Sources
        mode = "source_region"
    if region is None or "waterlevel" in params or params.get("dowaterline"):
        _try_set(fsolve, "dowaterline", 1)
        _try_set(fsolve, "waterline", clamp(waterlevel, -1e7, 1e7))
        if fsolve.parmTuple("waterorigin") is not None:
            fsolve.parmTuple("waterorigin").set((cx, 0.0, cz))
        mode = "waterline" if mode is None else "waterline+source_region"
    _apply_flip_solver(fsolve, params)
    fsolve.setDisplayFlag(display)
    fsolve.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "dem_merge": om.path(), "convert": conv.path(),
            "collider": coll.path(), "container": cont.path(), "solver": fsolve.path(),
            "container_size": [round(dx, 3), round(height, 3), round(dz, 3)],
            "water_level": round(waterlevel, 3), "mode": mode,
            "collider_wired": fsolve.input(2) is not None}


def _set_vec(node, parm, vec):
    """Set a vector parm-tuple probe-safely (skips if the parm/len doesn't match)."""
    t = node.parmTuple(parm)
    if t is None:
        return False
    try:
        vals = tuple(float(x) for x in vec)
        if len(vals) != len(t):
            return False
        t.set(vals)
        return True
    except Exception:
        return False


# Live-probed menu tokens (H21.0.671 — capitalization/order matter).
_FLIPSOURCE_MODE = ("sourceflip", "sink", "sinkfluid", "collision", "pump", "expand")  # flipsource.initialize


@endpoint("flip_source")
def flip_source(params):
    """Geometry -> FLIP particles via the Flip Source SOP (initial fill and/or continuous emit).
    `input` = the geo SOP; the flipsource is wired after it, feeding a flipsolver Sources input.
    mode (sourceflip|sink|sinkfluid|collision|pump|expand -> `initialize`), createparticles,
    particlesep, voxelsize, outputfog, particlegroup, oversampling(+bandwidth), jitterseed/jitterscale,
    enablerest, velocity [x,y,z] (initial velocity / pump direction, enables addvelocity),
    shellthickness (emit a thin surface shell, enables shell). BUILT only (no sim)."""
    n = child_after(params["input"], "flipsource", params.get("name"))
    applied = {}
    if "mode" in params:
        applied["mode"] = _menu_set(n, "initialize", str(params["mode"]), _FLIPSOURCE_MODE)
    if "createparticles" in params:
        applied["createparticles"] = _try_set(n, "createparticles", bool(params["createparticles"]))
    if "particlesep" in params:
        applied["particlesep"] = _try_set(n, "particlesep", clamp(float(params["particlesep"]), 1e-3, 1e4))
    if "voxelsize" in params:
        applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "outputfog" in params:
        applied["outputfog"] = _try_set(n, "outputfog", bool(params["outputfog"]))
    if "particlegroup" in params:
        applied["particlegroup"] = _try_set(n, "particlegroup", str(params["particlegroup"]))
    if "oversampling" in params:
        _try_set(n, "dooversampling", 1)
        applied["oversampling"] = _try_set(n, "oversampling", clamp(float(params["oversampling"]), 0.0, 1e3))
    if "oversamplingbandwidth" in params:
        applied["oversamplingbandwidth"] = _try_set(n, "oversamplingbandwidth",
                                                    clamp(float(params["oversamplingbandwidth"]), 0.0, 1e3))
    if "jitterseed" in params:
        applied["jitterseed"] = _try_set(n, "jitterseed", clamp(float(params["jitterseed"]), 0.0, 1e9))
    if "jitterscale" in params:
        applied["jitterscale"] = _try_set(n, "jitterscale", clamp(float(params["jitterscale"]), 0.0, 1e4))
    if "enablerest" in params:
        applied["enablerest"] = _try_set(n, "enablerest", bool(params["enablerest"]))
    # initial velocity imparted to the sourced fluid (a jet/pump direction); enables addvelocity.
    if "velocity" in params:
        _try_set(n, "addvelocity", 1)
        applied["velocity"] = _set_vec(n, "velocity", params["velocity"])
    # source only a shell of the input surface (thin emit band) instead of the solid interior.
    if "shellthickness" in params:
        _try_set(n, "shell", 1)
        applied["shellthickness"] = _try_set(n, "shellthickness", clamp(float(params["shellthickness"]), 0.0, 1e4))
    result = {"node": n.path(), "flipsource": n.path(), "applied": applied}
    # Wire this source into an EXISTING flipsolver's Sources input (index 0) — mirrors flip_collision's
    # `solver=` mode (the flipsolver SOP has NO source-path param; a source is fed purely by wiring).
    # ADDS emission to a live sim: empty input 0 -> wire directly; occupied -> merge so we ADD not replace.
    # Cross-network -> object_merge bridge in the solver's parent.
    if params.get("solver"):
        solv = resolve_node(str(params["solver"]))
        if solv.type().name() != "flipsolver":
            raise ValueError("`solver` must be a flipsolver SOP (got %s)" % solv.type().name())
        if n.parent() == solv.parent():
            src_in = n
        else:
            om = solv.parent().createNode("object_merge", "flip_emitter")
            _try_set(om, "objpath1", n.path())
            try:
                governor_gate("flip_source")  # advisory heavy-cook gate; refuses only in the catastrophic band
                om.cook(force=True)
            except Exception:  # noqa: BLE001
                pass
            src_in = om
        existing = solv.input(0)
        if existing is None:
            solv.setInput(0, src_in, 0)
        else:
            mrg = solv.parent().createNode("merge", "flip_sources")
            mrg.setInput(0, existing)
            mrg.setInput(1, src_in)
            solv.setInput(0, mrg, 0)
        solv.parent().layoutChildren()
        result["solver"] = solv.path()
        result["source_wired"] = solv.input(0) is not None
    return result


_FLIPBOUND_TYPE = ("source", "sink")                 # flipboundary.type
_FLIPBOUND_BTYPE = ("none", "vel", "pressure")       # flipboundary.boundarytype (live tokens)
# Friendly enum -> live token. `hydro_pressure` = a Pressure boundary configured hydrostatically
# (the live menu has NO hydro token; the hydro_* float parms drive the hydrostatic behaviour).
_FLIPBOUND_BTYPE_ALIAS = {"none": "none", "velocity": "vel", "vel": "vel",
                          "pressure": "pressure", "hydro_pressure": "pressure"}


@endpoint("flip_boundary")
def flip_boundary(params):
    """Open-boundary source/sink for a FLIP container via the Flip Boundary SOP. `input` = the SOP
    defining the boundary region. boundary (source|sink -> `type`), boundarytype (none|velocity|
    pressure|hydro_pressure). `hydro_pressure` routes to a Pressure boundary; set the hydrostatic
    level with hydro_pressure/hydro_offset/hydro_waterpos (coastal surge / flood waterline). Also
    velocity [x,y,z], scalevel, normalvel, pressure, computevel. BUILT only (no sim)."""
    n = child_after(params["input"], "flipboundary", params.get("name"))
    applied = {}
    if "boundary" in params:
        applied["boundary"] = _menu_set(n, "type", str(params["boundary"]), _FLIPBOUND_TYPE)
    if "boundarytype" in params:
        key = str(params["boundarytype"])
        tok = _FLIPBOUND_BTYPE_ALIAS.get(key)
        if tok is not None:
            applied["boundarytype"] = _menu_set(n, "boundarytype", tok, _FLIPBOUND_BTYPE)
            applied["hydro"] = (key == "hydro_pressure")
    if "pressure" in params:
        applied["pressure"] = _try_set(n, "pressure", clamp(float(params["pressure"]), -1e9, 1e9))
    if "hydro_pressure" in params:
        applied["hydro_pressure"] = _try_set(n, "hydro_pressure", clamp(float(params["hydro_pressure"]), -1e9, 1e9))
    if "hydro_offset" in params:
        applied["hydro_offset"] = _try_set(n, "hydro_offset", clamp(float(params["hydro_offset"]), -1e9, 1e9))
    if "hydro_waterpos" in params:
        applied["hydro_waterpos"] = _set_vec(n, "hydro_waterpos", params["hydro_waterpos"])
    if "velocity" in params:
        applied["velocity"] = _set_vec(n, "velocity", params["velocity"])
    if "scalevel" in params:
        applied["scalevel"] = _try_set(n, "scalevel", clamp(float(params["scalevel"]), -1e6, 1e6))
    if "normalvel" in params:
        applied["normalvel"] = _try_set(n, "normalvel", clamp(float(params["normalvel"]), -1e6, 1e6))
    if "computevel" in params:
        applied["computevel"] = _try_set(n, "computevel", bool(params["computevel"]))
    return {"node": n.path(), "flipboundary": n.path(), "applied": applied}


_FLIPTANK_SHAPE = ("grid", "tetrahedral")   # particlefluidtank.inittype
_FLIPTANK_UPAXIS = ("x", "y", "z")          # particlefluidtank.upaxis


@endpoint("flip_tank")
def flip_tank(params):
    """Pre-filled pool of FLIP particles via the Particle Fluid Tank SOP (pool / harbor / reservoir
    that starts already full). Generator (no input) placed in a fresh /obj geo `name`. shape
    (grid|tetrahedral -> `inittype`), size [x,y,z], center [x,y,z] (-> `t`), upaxis (x|y|z),
    particlesep, oversampling, viscosity, density, waterlevel (partial fill level along the up axis),
    jitterscale (break the regular lattice). BUILT only (no sim)."""
    name = params["name"]
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    tank = g.createNode("particlefluidtank", "tank")
    applied = {}
    if "shape" in params:
        applied["shape"] = _menu_set(tank, "inittype", str(params["shape"]), _FLIPTANK_SHAPE)
    if "size" in params:
        applied["size"] = _set_vec(tank, "size", params["size"])
    if "center" in params:
        applied["center"] = _set_vec(tank, "t", params["center"])
    if "upaxis" in params:
        applied["upaxis"] = _menu_set(tank, "upaxis", str(params["upaxis"]), _FLIPTANK_UPAXIS)
    if "particlesep" in params:
        applied["particlesep"] = _try_set(tank, "particlesep", clamp(float(params["particlesep"]), 1e-3, 1e4))
    if "oversampling" in params:
        _try_set(tank, "dooversampling", 1)
        applied["oversampling"] = _try_set(tank, "oversampling", clamp(float(params["oversampling"]), 0.0, 1e3))
    if "viscosity" in params:
        _try_set(tank, "addviscosity", 1)
        applied["viscosity"] = _try_set(tank, "viscosity", clamp(float(params["viscosity"]), 0.0, 1e6))
    if "density" in params:
        _try_set(tank, "adddensity", 1)
        applied["density"] = _try_set(tank, "density", clamp(float(params["density"]), 1e-3, 1e9))
    # partial fill: waterlevel = fluid surface height inside the tank box (up axis); a half-full pool.
    if "waterlevel" in params:
        applied["waterlevel"] = _try_set(tank, "waterlevel", clamp(float(params["waterlevel"]), -1e7, 1e7))
    # break the regular lattice so the surface is not perfectly flat (0 = perfectly gridded).
    if "jitterscale" in params:
        applied["jitterscale"] = _try_set(tank, "jitterscale", clamp(float(params["jitterscale"]), 0.0, 1e4))
    tank.setDisplayFlag(display)
    tank.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "tank": tank.path(), "applied": applied}


# ftype -> live typed force node (all no-VEX typed forces).
_FORCE_MAP = {"gravity": "uniformforce", "current": "uniformforce", "vortex": "vortexforce",
              "wind": "windforce", "drag": "drag", "point": "pointforce", "fan": "fan",
              "axis": "popaxisforce"}
_FORCE_DEFAULT_DIR = {"gravity": (0.0, -1.0, 0.0), "current": (1.0, 0.0, 0.0), "wind": (0.0, 0.0, 1.0),
                      "fan": (0.0, 0.0, 1.0), "axis": (0.0, 1.0, 0.0), "point": (1.0, 0.0, 0.0)}
_FORCE_DEFAULT_STR = {"gravity": 9.81, "current": 5.0}


@endpoint("flip_force")
def flip_force(params):
    """Typed force node (NO VEX) for a FLIP/DOP sim. ftype -> node: gravity/current -> uniformforce,
    vortex -> vortexforce, wind -> windforce, drag -> drag, point -> pointforce, fan -> fan,
    axis -> popaxisforce. Common: strength, direction [x,y,z], center [x,y,z] (point/fan/axis).
    Created inside an existing `dopnet` if given, else a fresh /obj geo `name` holding a dopnet.
    The force node is BUILT (not auto-wired into a solver — merge it into the solver's Forces input)."""
    ftype = str(params.get("ftype", "gravity"))
    if ftype not in _FORCE_MAP:
        raise ValueError("unknown ftype: %s (want %s)" % (ftype, "/".join(sorted(_FORCE_MAP))))
    ntype = _FORCE_MAP[ftype]
    g = None
    if params.get("dopnet"):
        dn = hou.node(str(params["dopnet"]))
        if dn is None:
            raise ValueError("no such dopnet: %s" % params["dopnet"])
    else:
        if not params.get("name"):
            raise ValueError("flip_force needs `name` (for a fresh holder) or `dopnet`")
        g = _fresh_geo(params["name"])
        dn = g.createNode("dopnet", "forces")
    force = dn.createNode(ntype, params.get("node_name") or ftype)
    strength = float(params["strength"]) if "strength" in params else _FORCE_DEFAULT_STR.get(ftype, 1.0)
    direction = params.get("direction") or _FORCE_DEFAULT_DIR.get(ftype, (0.0, 1.0, 0.0))
    direction = tuple(float(x) for x in direction)
    applied = {}
    if ntype == "uniformforce":
        applied["force"] = _set_vec(force, "force", tuple(d * strength for d in direction))
    elif ntype == "pointforce":
        applied["force"] = _set_vec(force, "force", tuple(d * strength for d in direction))
        if "center" in params:
            applied["center"] = _set_vec(force, "t", params["center"])
    elif ntype == "windforce":
        applied["direction"] = _set_vec(force, "vel", direction)
        applied["strength"] = _try_set(force, "scaleforce", clamp(strength, 0.0, 1e9))
    elif ntype == "drag":
        applied["strength"] = _try_set(force, "forcescale", clamp(strength, 0.0, 1e9))
    elif ntype == "vortexforce":
        applied["falloff"] = _try_set(force, "falloff", clamp(float(params.get("falloff", 1.0)), 0.0, 1e4))
        if "strength" in params:
            applied["strength"] = _try_set(force, "dragconstant", clamp(strength, 0.0, 1e9))
    elif ntype == "fan":
        applied["direction"] = _set_vec(force, "direction", direction)
        applied["strength"] = _try_set(force, "flux",
                                       clamp(strength if "strength" in params else 1e6, 0.0, 1e12))
        if "center" in params:
            applied["center"] = _set_vec(force, "t", params["center"])
        if "coneangle" in params:
            _try_set(force, "coneangle", clamp(float(params["coneangle"]), 0.0, 180.0))
        if "maxdistance" in params:
            _try_set(force, "maxdistance", clamp(float(params["maxdistance"]), 0.0, 1e9))
    elif ntype == "popaxisforce":
        applied["direction"] = _set_vec(force, "dir", direction)
        applied["strength"] = _try_set(force, "innerstrength", clamp(strength, -1e9, 1e9))
        _try_set(force, "outerstrength", clamp(float(params.get("outerstrength", strength)), -1e9, 1e9))
        if "orbitspeed" in params:
            _try_set(force, "orbitspeed", clamp(float(params["orbitspeed"]), -1e9, 1e9))
        if "center" in params:
            applied["center"] = _set_vec(force, "t", params["center"])
    try:
        dn.layoutChildren()
    except Exception:
        pass
    result = {"node": force.path(), "force": force.path(), "dopnet": dn.path(),
              "ftype": ftype, "node_type": ntype, "applied": applied}
    if g is not None:
        display = bool(params.get("display", False))
        dn.setDisplayFlag(display)
        g.setDisplayFlag(display)
        g.layoutChildren()
        result["geo"] = g.path()
    return result


# ── PARTICLES / POP lane (Phase 1) — the DOP-net pattern, cook-verified on H21.0.671.
# Architecture (probe + COOK-proven, spec v2):
#   A SOP `dopnet` (input0 = emit geometry) wraps a DOP POP graph:
#     popobject          -> popsolver::2.0 input 0 ('Object')
#     source chain       -> popsolver::2.0 input 2 ('Sources (post-solve)')      [popsource::2.0 …]
#     force/behaviour chain -> popsolver::2.0 input 1 ('Pre-Solve')              [popforce … typed]
#   and `dopimport::2.0` (SOP) pulls the simulated particles back to SOP.
# COOK VERDICT (frames 1–12, headless):
#   • usecontextgeo=2 ('first') on popsource::2.0 emits the dopnet's input0 geometry — BORN & growing
#     (13 → 155 pts). usecontextgeo=1 ('dop') does NOT (the old sim_pop bug).
#   • The SOURCE must feed input 2. Chaining the source INTO the force stream that feeds input 1 yields
#     ZERO births. (The old sim_pop also had the inputs reversed: src on in1, gravity on in2 — fixed.)
#   • FORCES CHAIN: force nodes have one stream input ('Stream to Apply Forces to') + one output; wiring
#     Output→next Input and the chain tail → solver input 1 STACKS every force (two popforces: particles
#     both FELL to minY −1.123 AND DRIFTED to maxX 5.553; a single-force control stayed pinned at 4.980).
#     A parallel merge→in1 cooks identically, but chaining matches the singular 'Pre-Solve' input and the
#     stream-in/stream-out node shape, so chaining is the canonical topology.
#   • `uniformforce` (generic DOP force) does NOT couple to POP particles — POP gravity is a `popforce`
#     with a downward force vector (so the default gravity here is a popforce, not `gravity`/`uniformforce`).
#   • Import: `dopimport::2.0` (importstyle=fetch, objpattern=*) returns the points headless. `dopio`'s
#     `presets='particles'` menu is a UI callback that does NOT populate its object multiparm under hython
#     (returns 0 pts), so the data-only importer is dopimport::2.0.
# NO auto-cook of a multi-frame sim on the executor thread — handlers BUILD only; the caller scrubs.
_POPSRC_USECTX = ("none", "dop", "first", "second", "third", "fourth")   # popsource/popattract usecontextgeo
_POPSRC_EMITTYPE = ("allpoint", "allgeo", "point", "surface")            # popsource emittype
_POPSRC_INITVEL = ("use", "add", "set")                                  # popsource initvel
_POPSRC_JITTERBIRTH = ("none", "negative", "positive")                   # popsource jitterbirthtime
_POPSOLVER_COLLRESP = ("none", "die", "stopped", "stuck", "slide")       # popsolver collisionresponse
_POPAXIS_TYPE = ("sphere", "torus")                                      # popaxisforce type
_POPATTRACT_TYPE = ("position", "particles", "points", "surface")        # popattract attracttype
_POPATTRACT_METHOD = ("accel", "follow")                                 # popattract forcemethod
_POPCURVE_CTX = ("soppath", "doppath", "first", "second", "third", "fourth")  # popcurveforce usecontextgeo
_POPADVECT_VELSRC = ("sop", "dopdata", "first", "second", "third", "fourth")  # popadvectbyvolumes velsource
_POPADVECT_TYPE = ("force", "vel", "pos")                                # popadvectbyvolumes advecttype
_POPADVECT_METHOD = ("single", "trace", "midpoint", "rk3", "rk4")        # popadvectbyvolumes advectmethod
_DOPIMPORT_STYLE = ("fetch", "points")                                   # dopimport::2.0 importstyle
_DOPIMPORT_POINTVELS = ("none", "instant", "integrate")                  # dopimport::2.0 pointvels
_DOPIMPORT_PIVOT = ("origin", "centroid")                                # dopimport::2.0 pivot
# Phase-2 interaction nodes (collision / grouping / killing) — live-probed on H21.0.671.
# Menu tokens are exact; capitalization/order matter.
_POPCOLL_COLLIDER = ("relationship", "dopobjects", "soppath", "first", "second", "third", "fourth")  # popcollisiondetect collider
_POPCOLL_RESPONSE = ("none", "die", "stopped", "stuck", "slide")         # popcollisiondetect/popcollisionbehavior response
_POPBOUND_TYPE = ("box", "sphere", "geometry", "volume")                 # popgroup/popstream/popkill boundtype
_POPBOUND_SOURCE = ("sop", "dopdata", "first", "second", "third", "fourth")  # popgroup boundsource (geometry/volume bound)
_POPRAND_BEHAVIOR = ("add", "remove")                                    # popgroup/popstream randbehavior + popkill randombehavior
_POPCOMBINE_OP = ("none", "or", "and", "xor", "sub")                     # popgroup combine_op1..4
_POPLIMIT_BEHAVIOUR = ("none", "clamp", "bounce", "wrap")               # poplimit behaviour (British spelling)
_POPLIMIT_VELBEHAVIOUR = ("none", "clamp", "bounce")                     # poplimit velbehaviour
_POPSOFTLIMIT_TYPE = ("box", "sphere")                                   # popsoftlimit type
# Phase-3 look/output nodes (properties / instancing / cache) — live-probed on H21.0.671.
# Menu tokens are exact (index, token) triples from the probe.
_POPCOLOR_TYPE = ("constant", "random", "ramp", "blend")                 # popcolor colortype
_POPCOLOR_ALPHATYPE = ("constant", "ramp")                              # popcolor/popsprite alphatype
_POPSPRITE_CROP = ("offset", "spritesheet")                            # popsprite cropmode
_POPLOOKAT_MODE = ("point", "dir")                                     # poplookat mode (Target is Point|Direction)
_POPLOOKAT_METHOD = ("immediate", "turn", "spin")                      # poplookat method
_POPREPL_SHAPE = ("box", "sphere", "cylinder", "cone", "grid", "circle", "line", "point")  # popreplicate shape
_POPREPL_PLANE = {"xy": 0, "yz": 1, "zx": 2}                            # popreplicate orientation (Menu index; tokens '0'/'1'/'2')
# Phase-4 flocking/steering + grains — live-probed on H21.0.671.
# behavior -> the ONE boids/steering DOP node it builds (all category=Dop, all create OK).
# popsteercustom is EXCLUDED (VEX behaviour node) — never in this map.
_POP_FLOCK_MAP = {
    "flock": "popflock", "interact": "popinteract", "seek": "popsteerseek",
    "avoid": "popsteeravoid::2.0", "wander": "popsteerwander", "separate": "popsteerseparate",
    "cohesion": "popsteercohesion", "align": "popsteeralign", "obstacle": "popsteerobstacle::2.0",
    "proximity": "popproximity",
}
# The steer nodes carry an `output` MENU whose tokens are literally '0'/'1' (NOT the labels) —
# index0='Crowds steerforce', index1='POP force'. Default is 1 (POP force) so the steer force bites in
# a plain POP solver. We expose friendly tokens crowds|pop and set the integer index.
_POPSTEER_OUTPUT = {"crowds": 0, "pop": 1, "0": 0, "1": 1}
_POPSTEER_ATTRACT = ("position", "particles", "points", "surface")  # popsteerseek attracttype (index menu)
_POPSTEERSEEK_CTX = ("none", "dop", "first", "second", "third", "fourth")  # popsteerseek usecontextgeo
# popgrains domassshock MENU: index0='off'(Off) 1='on'(Global) 2='local'(Local); default 2 ('local').
_POPGRAINS_MASSSHOCK = ("off", "on", "local")
# pop_scatter_sim (T13) force presets: gravity magnitude + a directional/turbulent popwind-style force
# (built as a popforce: force vector + built-in noise amp/swirlsize/turb) + a default particle life.
_SCATTER_PRESETS = {
    "sparks": dict(gravity=3.0,  wind=(0.0, 4.0, 0.0),  amp=6.0, swirlsize=1.0, turb=3, life=1.5),
    "embers": dict(gravity=1.5,  wind=(0.0, 3.0, 0.0),  amp=4.0, swirlsize=1.5, turb=3, life=3.0),
    "leaves": dict(gravity=2.0,  wind=(4.0, 0.0, 1.0),  amp=4.0, swirlsize=2.0, turb=2, life=8.0),
    "debris": dict(gravity=6.0,  wind=(5.0, 0.0, 0.0),  amp=3.0, swirlsize=1.0, turb=2, life=6.0),
    "dust":   dict(gravity=0.2,  wind=(1.0, 0.5, 0.0),  amp=6.0, swirlsize=2.5, turb=3, life=5.0),
    "rain":   dict(gravity=30.0, wind=(0.0, 0.0, 0.0),  amp=0.0, swirlsize=0.0, turb=0, life=4.0),
    "snow":   dict(gravity=1.0,  wind=(0.0, 0.0, 0.0),  amp=2.0, swirlsize=2.0, turb=2, life=10.0),
}


def _pop_dopnet_and_solver(params):
    """Resolve an existing dopnet (`dopnet`) + its popsolver (`solver` or auto-found) for the composable
    T2/T3 handlers. Returns (dopnet, solver_or_None). Raises if the dopnet is missing/not a dopnet."""
    dn = resolve_node(str(params["dopnet"]))
    if dn.type().name() != "dopnet":
        raise ValueError("`dopnet` must be a SOP dopnet (got %s)" % dn.type().name())
    solv = None
    if params.get("solver"):
        solv = resolve_node(str(params["solver"]))
    else:
        cand = [c for c in dn.children() if c.type().name() in ("popsolver::2.0", "popsolver")]
        if cand:
            solv = cand[0]
    return dn, solv


def _chain_presolve(solv, node):
    """Append a force/behaviour node to the tail of the Pre-Solve chain feeding popsolver input 1."""
    existing = solv.input(1)
    if existing is not None:
        try:
            node.setInput(0, existing, 0)
        except Exception:
            pass
    solv.setInput(1, node, 0)


def _add_source(solv, dn, node):
    """Add a source to popsolver input 2 (Sources post-solve). popsource has no input, so multiple
    sources are combined with a DOP `merge` rather than chained."""
    existing = solv.input(2)
    if existing is None:
        solv.setInput(2, node, 0)
        return
    if existing.type().name() == "merge":
        existing.setInput(len(existing.inputs()), node, 0)
    else:
        mrg = dn.createNode("merge")
        mrg.setInput(0, existing, 0)
        mrg.setInput(1, node, 0)
        solv.setInput(2, mrg, 0)


def _apply_dopnet(dn, params, applied):
    if "startframe" in params:
        applied["startframe"] = _set_indep(dn, "startframe", int(clamp(int(params["startframe"]), 1, 1000000)))
    if "substep" in params:
        applied["substep"] = _try_set(dn, "substep", int(clamp(int(params["substep"]), 1, 100)))
    if "timestep" in params:
        applied["timestep"] = _try_set(dn, "timestep", clamp(float(params["timestep"]), 1e-5, 1.0))
    if "timescale" in params:
        applied["dopnet_timescale"] = _try_set(dn, "timescale", clamp(float(params["timescale"]), 1e-3, 1e4))
    if "cacheenabled" in params:
        applied["cacheenabled"] = _try_set(dn, "cacheenabled", bool(params["cacheenabled"]))


def _apply_popobject(po, params, applied):
    for k in ("bounce", "bounceforward", "friction", "dynamicfriction"):
        if k in params:
            applied[k] = _try_set(po, k, clamp(float(params[k]), 0.0, 1e4))
    if "temperature" in params:
        applied["temperature"] = _try_set(po, "temperature", clamp(float(params["temperature"]), 0.0, 1e6))
    if "initial_geo" in params:
        applied["initial_geo"] = _try_set(po, "initial_geo", str(params["initial_geo"]))
    if "solvefirstframe" in params:
        applied["solvefirstframe"] = _try_set(po, "solvefirstframe", bool(params["solvefirstframe"]))


def _apply_popsolver(solv, params, applied):
    if "substeps" in params:
        applied["substeps"] = _try_set(solv, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "minimumsubsteps" in params:
        applied["minimumsubsteps"] = _try_set(solv, "minimumsubsteps", int(clamp(int(params["minimumsubsteps"]), 0, 100)))
    if "timescale" in params:
        applied["timescale"] = _try_set(solv, "timescale", clamp(float(params["timescale"]), 0.0, 1e4))
    if "cflcond" in params:
        applied["cflcond"] = _try_set(solv, "cflcond", clamp(float(params["cflcond"]), 0.0, 1e4))
    for k in ("doage", "doreapparticles", "reapatend", "docollision",
              "integratevel", "integratepos", "usemass", "externalforce", "implicitdrag"):
        if k in params:
            applied[k] = _try_set(solv, k, bool(params[k]))
    if "dragexp" in params:
        applied["dragexp"] = _try_set(solv, "dragexp", clamp(float(params["dragexp"]), 1.0, 2.0))
    if "collisionresponse" in params:
        applied["collisionresponse"] = _menu_set(solv, "collisionresponse", str(params["collisionresponse"]), _POPSOLVER_COLLRESP)
    if "doautosleep" in params:
        applied["doautosleep"] = _try_set(solv, "doautosleep", bool(params["doautosleep"]))
    if "sleep_startasleep" in params:
        applied["sleep_startasleep"] = _try_set(solv, "sleep_startasleep", bool(params["sleep_startasleep"]))
    if "sleep_velocitythreshold" in params:
        applied["sleep_velocitythreshold"] = _try_set(solv, "sleep_velocitythreshold", clamp(float(params["sleep_velocitythreshold"]), 0.0, 1e6))
    if "sleep_delay" in params:
        applied["sleep_delay"] = _try_set(solv, "sleep_delay", clamp(float(params["sleep_delay"]), 0.0, 1e6))


def _config_popsource(src, params, applied):
    """Configure a popsource::2.0 from typed params (probe-confirmed names; VEX/uselocal* left untouched)."""
    # emission geometry
    if "mode" in params:
        applied["mode"] = _menu_set(src, "emittype", str(params["mode"]), _POPSRC_EMITTYPE)
    # context-geo vs explicit SOP: an explicit soppath -> usecontextgeo='none'; else default 'first'
    if params.get("source_sop"):
        _menu_set(src, "usecontextgeo", "none", _POPSRC_USECTX)
        applied["source_sop"] = _try_set(src, "soppath", str(params["source_sop"]))
    else:
        applied["usecontextgeo"] = _menu_set(src, "usecontextgeo", str(params.get("usecontextgeo", "first")), _POPSRC_USECTX)
    if "sourcegroup" in params:
        applied["sourcegroup"] = _try_set(src, "group", str(params["sourcegroup"]))
    if "emitattrib" in params:
        applied["emitattrib"] = _try_set(src, "emitattrib", str(params["emitattrib"]))
    # emission model — const-rate stream + impulse burst (note SideFX's literal misspellings)
    if "constantrate" in params:
        _try_set(src, "constantactivate", 1.0)
        applied["constantrate"] = _try_set(src, "constantrate", clamp(float(params["constantrate"]), 0.0, 1e9))
    if "impulsecount" in params:
        _try_set(src, "impulseactiveate", 1.0)
        applied["impulsecount"] = _try_set(src, "impulserate", clamp(float(params["impulsecount"]), 0.0, 1e9))
    if params.get("burst"):        # burst = impulse only, no constant stream
        _try_set(src, "constantactivate", 0.0)
        _try_set(src, "impulseactiveate", 1.0)
        applied["burst"] = True
    # limits
    if "framepointlimit" in params:
        _try_set(src, "useframepointlimit", 1)
        applied["framepointlimit"] = _try_set(src, "framepointlimit", int(clamp(int(params["framepointlimit"]), 1, 100000000)))
    if "simpointlimit" in params:
        _try_set(src, "usesimpointlimit", 1)
        applied["simpointlimit"] = _try_set(src, "simpointlimit", int(clamp(int(params["simpointlimit"]), 1, 100000000)))
    # birth
    if "life" in params:
        applied["life"] = _try_set(src, "life", clamp(float(params["life"]), 0.0, 1e6))
    if "lifevar" in params:
        applied["lifevar"] = _try_set(src, "lifevar", clamp(float(params["lifevar"]), 0.0, 1e6))
    if "seed" in params:
        applied["seed"] = _try_set(src, "seed", clamp(float(params["seed"]), 0.0, 1e9))
    if "jitterbirth" in params:
        applied["jitterbirth"] = _menu_set(src, "jitterbirthtime", str(params["jitterbirth"]), _POPSRC_JITTERBIRTH)
    # velocity
    if "initvel" in params:
        applied["initvel"] = _menu_set(src, "initvel", str(params["initvel"]), _POPSRC_INITVEL)
    if "inheritvel" in params:
        applied["inheritvel"] = _try_set(src, "inheritvel", clamp(float(params["inheritvel"]), -1e6, 1e6))
    if "velocity" in params:
        applied["velocity"] = _set_vec(src, "vel", params["velocity"])
    if "velvar" in params:
        applied["velvar"] = _set_vec(src, "var", params["velvar"])
    # stream identity
    if "streamname" in params:
        applied["streamname"] = _try_set(src, "streamname", str(params["streamname"]))
    if "doid" in params:
        applied["doid"] = _try_set(src, "doid", bool(params["doid"]))


@endpoint("sim_pop")
def sim_pop(params):
    """POP particles (master): a SOP `dopnet` (input0 = emit geometry) wrapping popobject -> popsolver::2.0
    with a source on the Sources input and a default popforce gravity on the Pre-Solve input. The
    cook-verified DOP-net pattern (see the module header): usecontextgeo=2 ('first') so the emit geo
    actually sources, source -> solver input 2, forces chain -> solver input 1. BUILT only, never
    auto-simulated (the caller scrubs the timeline).

    Setup: name (fresh /obj geo), source_geo (emit geo path; else a default grid), source_sop (explicit
    SOP the popsource reads instead of the context geo), display. Emission: constantrate, life, gravity
    (magnitude of the default downward popforce; 0 = none). dopnet: startframe, substep, timestep,
    timescale, cacheenabled. popobject: bounce, bounceforward, friction, dynamicfriction, temperature,
    initial_geo, solvefirstframe. popsolver::2.0: substeps, minimumsubsteps, timescale, cflcond, doage,
    doreapparticles, reapatend, docollision, collisionresponse(none|die|stopped|stuck|slide),
    integratevel, integratepos, usemass, externalforce, implicitdrag, dragexp, doautosleep,
    sleep_startasleep, sleep_velocitythreshold, sleep_delay. Composition: forces (list of force-node
    paths inside this dopnet to chain onto Pre-Solve) and sources (list of source-node paths to add onto
    Sources). Returns the dopnet + popobject/popsource/popsolver paths so T2/T3/T11 compose onto it."""
    name = params["name"]
    frames = int(clamp(int(params.get("frames", 120)), 1, 10000))
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    emit = _src_node(g, params.get("source_geo"), "grid",
                     lambda n: n.parmTuple("size").set((10.0, 10.0)) if n.parmTuple("size") else None)
    dn = g.createNode("dopnet", "particles")
    dn.setFirstInput(emit)
    applied = {}
    _set_indep(dn, "startframe", int(clamp(int(params.get("startframe", 1)), 1, 1000000)))
    _apply_dopnet(dn, params, applied)
    po = dn.createNode("popobject")
    _apply_popobject(po, params, applied)
    src = dn.createNode("popsource")
    # THE T1 FIX: emit the dopnet's input0 context geometry via usecontextgeo=2 ('first'), unless an
    # explicit SOP is given. (The old build set usecontextgeo=1 = 'dop' -> zero births.)
    _config_popsource(src, {"constantrate": float(params.get("constantrate", 400.0)),
                            "usecontextgeo": params.get("usecontextgeo", "first"),
                            **({"source_sop": params["source_sop"]} if params.get("source_sop") else {}),
                            **({"life": params["life"]} if "life" in params else {})}, applied)
    solv = dn.createNode("popsolver")
    solv.setInput(0, po, 0)               # Object
    solv.setInput(2, src, 0)              # Sources (post-solve) — NOT input 1 (the old build reversed these)
    _try_set(solv, "substeps", int(clamp(int(params.get("substeps", 1)), 1, 100)))
    _apply_popsolver(solv, params, applied)
    # default gravity = a downward popforce (uniformforce does NOT couple to POP particles), chained to
    # Pre-Solve. gravity=0 suppresses it.
    gmag = float(params.get("gravity", 9.8))
    grav = None
    if gmag != 0.0:
        grav = dn.createNode("popforce", "gravity")
        grav.parmTuple("force").set((0.0, -abs(gmag), 0.0))
        _chain_presolve(solv, grav)
        applied["gravity"] = gmag
    # compose any pre-built nodes living inside this dopnet
    for fp in (params.get("forces") or []):
        fn = hou.node(str(fp))
        if fn is not None and fn.parent() == dn:
            _chain_presolve(solv, fn)
    for sp in (params.get("sources") or []):
        sn = hou.node(str(sp))
        if sn is not None and sn.parent() == dn:
            _add_source(solv, dn, sn)
    solv.setDisplayFlag(True)
    try:
        dn.layoutChildren()
    except Exception:
        pass
    dn.setDisplayFlag(display)
    dn.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "dopnet": dn.path(), "popobject": po.path(), "popsource": src.path(),
            "popsolver": solv.path(), "gravity": grav.path() if grav else None,
            "frames": frames, "applied": applied}


@endpoint("pop_source")
def pop_source(params):
    """Add a typed particle emitter (popsource::2.0) into an existing POP `dopnet` and (optionally) wire
    it onto the popsolver's Sources input. Emits the dopnet's input0 context geometry by default
    (usecontextgeo='first' — the cook-verified emit path) or an explicit `source_sop`. Data-only: every
    uselocal*/local*expression VEX field is left at its default 0.

    dopnet (required), solver (else auto-found in the dopnet), name. mode (allpoint|allgeo|point|surface
    -> emittype), usecontextgeo (none|dop|first|second|third|fourth), source_sop (explicit SOP path),
    sourcegroup, emitattrib. Emission: constantrate (const stream), impulsecount (birth burst), burst
    (impulse-only). Limits: framepointlimit, simpointlimit. Birth: life, lifevar, seed,
    jitterbirth(none|negative|positive). Velocity: initvel(use|add|set), inheritvel, velocity[x,y,z],
    velvar[x,y,z]. Stream: streamname, doid. BUILT only."""
    dn, solv = _pop_dopnet_and_solver(params)
    src = dn.createNode("popsource", params.get("name") or "pop_source")
    applied = {}
    _config_popsource(src, params, applied)
    wired = False
    if solv is not None and bool(params.get("wire", True)):
        _add_source(solv, dn, src)
        wired = True
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return {"node": src.path(), "popsource": src.path(), "dopnet": dn.path(),
            "solver": solv.path() if solv else None, "wired_to_sources": wired, "applied": applied}


# ftype -> the typed POP force node it builds (all DOP, all probe-confirmed; NO VEX/wrangle).
_POP_FORCE_MAP = {
    "force": "popforce", "wind": "popwind", "vortex": "popaxisforce", "attract": "popattract",
    "curve": "popcurveforce", "drag": "popdrag", "spin": "popspin", "fan": "popfan",
    "advect": "popadvectbyvolumes", "gravity": "popforce", "uniform": "popforce",
}


def _config_pop_force(ftype, node, params, applied):
    """Set the typed parms for one POP force node (probe-confirmed). Never touches uselocal*/local*expr."""
    if "activate" in params:
        applied["activate"] = _try_set(node, "activate", clamp(float(params["activate"]), 0.0, 1e4))
    if "group" in params:
        _try_set(node, "usegroup", 1)
        applied["group"] = _try_set(node, "partgroup", str(params["group"]))
    strength = float(params["strength"]) if "strength" in params else None
    direction = params.get("direction")

    if ftype in ("force", "gravity", "uniform"):          # popforce — directional + built-in noise
        if ftype == "gravity" and "force" not in params and direction is None:
            applied["force"] = _set_vec(node, "force", (0.0, -abs(strength if strength is not None else 9.8), 0.0))
        else:
            vec = params.get("force")
            if vec is None and direction is not None:
                s = strength if strength is not None else 1.0
                vec = tuple(float(d) * s for d in direction)
            if vec is not None:
                applied["force"] = _set_vec(node, "force", vec)
        for k in ("amp", "swirlsize", "swirlscale", "pulselength", "rough", "atten", "offset"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), -1e6, 1e6))
        if "turb" in params:
            applied["turb"] = _try_set(node, "turb", int(clamp(int(params["turb"]), 0, 100)))
        if "ignoremass" in params:
            applied["ignoremass"] = _try_set(node, "ignoremass", bool(params["ignoremass"]))

    elif ftype == "wind":                                 # popwind
        if "wind" in params or direction is not None:
            applied["wind"] = _set_vec(node, "wind", params.get("wind") or direction)
        if "windspeed" in params:
            applied["windspeed"] = _try_set(node, "windspeed", clamp(float(params["windspeed"]), 0.0, 1e9))
        if "airresist" in params:
            applied["airresist"] = _try_set(node, "airresist", clamp(float(params["airresist"]), 0.0, 1e6))
        for k in ("amp", "swirlsize", "swirlscale", "rough", "atten"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), -1e6, 1e6))

    elif ftype == "vortex":                               # popaxisforce (tornado / whirlpool / orbit)
        if "shape" in params:
            applied["shape"] = _menu_set(node, "type", str(params["shape"]), _POPAXIS_TYPE)
        if "center" in params:
            applied["center"] = _set_vec(node, "t", params["center"])
        if direction is not None:
            applied["axis"] = _set_vec(node, "dir", direction)
        if "radius" in params:
            applied["radius"] = _try_set(node, "r", clamp(float(params["radius"]), 0.0, 1e9))
        if "height" in params:
            applied["height"] = _try_set(node, "height", clamp(float(params["height"]), 0.0, 1e9))
        for k in ("orbitspeed", "liftspeed", "suctionspeed", "innerstrength", "outerstrength", "softedge"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), -1e9, 1e9))
        if "treataswind" in params:
            applied["treataswind"] = _try_set(node, "treataswind", bool(params["treataswind"]))
        if "airresist" in params:
            applied["airresist"] = _try_set(node, "airresist", clamp(float(params["airresist"]), 0.0, 1e6))

    elif ftype == "attract":                              # popattract
        if "attracttype" in params:
            applied["attracttype"] = _menu_set(node, "attracttype", str(params["attracttype"]), _POPATTRACT_TYPE)
        if "goal" in params:
            applied["goal"] = _set_vec(node, "goal", params["goal"])
        if params.get("source_sop"):
            _menu_set(node, "usecontextgeo", "none", _POPSRC_USECTX)
            applied["source_sop"] = _try_set(node, "soppath", str(params["source_sop"]))
        if "forcemethod" in params:
            applied["forcemethod"] = _menu_set(node, "forcemethod", str(params["forcemethod"]), _POPATTRACT_METHOD)
        for k in ("forcescale", "mindist", "maxdist", "peakdist"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), -1e9, 1e9))
        if "predictintercept" in params:
            applied["predictintercept"] = _try_set(node, "predictintercept", bool(params["predictintercept"]))

    elif ftype == "curve":                                # popcurveforce (flow along a guide curve)
        if params.get("source_sop"):
            _menu_set(node, "usecontextgeo", "soppath", _POPCURVE_CTX)
            applied["source_sop"] = _try_set(node, "soppath", str(params["source_sop"]))
        if "maxradius" in params:
            applied["maxradius"] = _try_set(node, "maxradius", clamp(float(params["maxradius"]), 0.0, 1e9))
        for k in ("scalefollow", "scalesuction", "scaleorbit"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), -1e6, 1e6))
        if "airresist" in params:
            applied["airresist"] = _try_set(node, "airresist", clamp(float(params["airresist"]), 0.0, 1e6))
        if "treataswind" in params:
            applied["treataswind"] = _try_set(node, "treataswind", bool(params["treataswind"]))

    elif ftype == "drag":                                 # popdrag
        if "windvelocity" in params or direction is not None:
            applied["windvelocity"] = _set_vec(node, "windvelocity", params.get("windvelocity") or direction)
        if "airresist" in params:
            applied["airresist"] = _try_set(node, "airresist", clamp(float(params["airresist"]), 0.0, 1e6))

    elif ftype == "spin":                                 # popspin
        if direction is not None:
            applied["axis"] = _set_vec(node, "axis", direction)
        if "spinspeed" in params:
            applied["spinspeed"] = _try_set(node, "spinspeed", clamp(float(params["spinspeed"]), -1e9, 1e9))

    elif ftype == "fan":                                  # popfan
        if "center" in params:
            applied["center"] = _set_vec(node, "t", params["center"])
        if direction is not None:
            applied["dir"] = _set_vec(node, "dir", direction)
        if "cone" in params:
            applied["cone"] = _try_set(node, "cone", clamp(float(params["cone"]), 0.0, 180.0))
        if "windspeed" in params:
            applied["windspeed"] = _try_set(node, "windspeed", clamp(float(params["windspeed"]), 0.0, 1e9))
        if "airresist" in params:
            applied["airresist"] = _try_set(node, "airresist", clamp(float(params["airresist"]), 0.0, 1e6))

    elif ftype == "advect":                               # popadvectbyvolumes (pyro/FLIP velocity bridge)
        if "velsource" in params:
            applied["velsource"] = _menu_set(node, "velsource", str(params["velsource"]), _POPADVECT_VELSRC)
        if params.get("source_sop"):
            _menu_set(node, "velsource", "sop", _POPADVECT_VELSRC)
            applied["source_sop"] = _try_set(node, "soppath", str(params["source_sop"]))
        if "fieldname" in params:
            applied["fieldname"] = _try_set(node, "fieldname", str(params["fieldname"]))
        if "velscale" in params:
            applied["velscale"] = _try_set(node, "velscale", clamp(float(params["velscale"]), -1e6, 1e6))
        if "advecttype" in params:
            applied["advecttype"] = _menu_set(node, "advecttype", str(params["advecttype"]), _POPADVECT_TYPE)
        if "advectmethod" in params:
            applied["advectmethod"] = _menu_set(node, "advectmethod", str(params["advectmethod"]), _POPADVECT_METHOD)
        if "cfl" in params:
            applied["cfl"] = _try_set(node, "cfl", clamp(float(params["cfl"]), 0.0, 1e4))
        if "treataswind" in params:
            applied["treataswind"] = _try_set(node, "treataswind", bool(params["treataswind"]))
        if "airresist" in params:
            applied["airresist"] = _try_set(node, "airresist", clamp(float(params["airresist"]), 0.0, 1e6))


@endpoint("pop_force")
def pop_force(params):
    """Add ONE typed POP force into an existing POP `dopnet` and chain it onto the popsolver's Pre-Solve
    input (the cook-verified force topology — forces chain, stacking cleanly). The popwrangle-free force
    set; every uselocal*/local*expression VEX field is left at its default 0.

    dopnet (required), solver (else auto-found), name, wire (default true). ftype selects the node:
      force/gravity/uniform -> popforce  (force[x,y,z] or strength+direction; built-in noise amp,
        swirlsize, swirlscale, pulselength, rough, atten, offset, turb; ignoremass). gravity defaults to
        a downward vector.
      wind -> popwind  (wind[x,y,z] or direction, windspeed, airresist, + noise).
      vortex -> popaxisforce  (shape(sphere|torus), center[x,y,z], direction=axis, radius, height,
        orbitspeed, liftspeed, suctionspeed, innerstrength, outerstrength, softedge, treataswind, airresist).
      attract -> popattract  (attracttype(position|particles|points|surface), goal[x,y,z], source_sop,
        forcemethod(accel|follow), forcescale, mindist, maxdist, peakdist, predictintercept).
      curve -> popcurveforce  (source_sop guide curve, maxradius, scalefollow, scalesuction, scaleorbit,
        airresist, treataswind).
      drag -> popdrag  (windvelocity[x,y,z] or direction, airresist).
      spin -> popspin  (direction=axis, spinspeed).
      fan -> popfan  (center[x,y,z], direction=dir, cone deg, windspeed, airresist).
      advect -> popadvectbyvolumes  (velsource(sop|dopdata|first…), source_sop, fieldname, velscale,
        advecttype(force|vel|pos), advectmethod(single|trace|midpoint|rk3|rk4), cfl, treataswind, airresist).
    Common: activate, group (limits to a particle group). BUILT only."""
    ftype = str(params.get("ftype", "force"))
    if ftype not in _POP_FORCE_MAP:
        raise ValueError("unknown ftype: %s (want %s)" % (ftype, "/".join(sorted(_POP_FORCE_MAP))))
    dn, solv = _pop_dopnet_and_solver(params)
    ntype = _POP_FORCE_MAP[ftype]
    node = dn.createNode(ntype, params.get("name") or ("pop_" + ftype))
    applied = {}
    _config_pop_force(ftype, node, params, applied)
    wired = False
    if solv is not None and bool(params.get("wire", True)):
        _chain_presolve(solv, node)
        wired = True
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return {"node": node.path(), "force": node.path(), "dopnet": dn.path(), "ftype": ftype,
            "node_type": ntype, "solver": solv.path() if solv else None,
            "wired_to_presolve": wired, "applied": applied}


@endpoint("pop_import")
def pop_import(params):
    """Pull simulated POP particles from a `dopnet` back to SOP via `dopimport::2.0` (the cook-verified
    data-only importer — `dopio`'s presets menu is a UI callback that does not populate headless).
    Placed in the dopnet's parent geo (or a fresh /obj geo `name`).

    dopnet (required), name (geo to build into, if not the dopnet's parent), objpattern (default '*'),
    importstyle (fetch|points), pointvels (none|instant|integrate), pack, pivot (origin|centroid),
    viewportlod, display. HEAVY-OP GUARDRAIL: builds the import node ONLY — it does NOT cook a frame
    range; the caller scrubs the timeline to populate it. Returns the import node for the render/color/
    copy_to_points/export/cache handoff."""
    dn = resolve_node(str(params["dopnet"]))
    if dn.type().name() != "dopnet":
        raise ValueError("`dopnet` must be a SOP dopnet (got %s)" % dn.type().name())
    if params.get("name"):
        g = _fresh_geo(params["name"])
        obj_merge_dn = None  # imported by doppath, no wiring needed
    else:
        g = dn.parent()
    imp = g.createNode("dopimport::2.0", "pop_import")
    applied = {}
    _try_set(imp, "doppath", dn.path())
    applied["objpattern"] = _try_set(imp, "objpattern", str(params.get("objpattern", "*")))
    if "importstyle" in params:
        applied["importstyle"] = _menu_set(imp, "importstyle", str(params["importstyle"]), _DOPIMPORT_STYLE)
    if "pointvels" in params:
        applied["pointvels"] = _menu_set(imp, "pointvels", str(params["pointvels"]), _DOPIMPORT_POINTVELS)
    if "pack" in params:
        applied["pack"] = _try_set(imp, "pack", bool(params["pack"]))
    if "pivot" in params:
        applied["pivot"] = _menu_set(imp, "pivot", str(params["pivot"]), _DOPIMPORT_PIVOT)
    display = bool(params.get("display", False))
    imp.setDisplayFlag(display)
    imp.setRenderFlag(True)
    try:
        g.layoutChildren()
    except Exception:
        pass
    return {"node": imp.path(), "dopimport": imp.path(), "dopnet": dn.path(),
            "geo": g.path(), "applied": applied}


# ── Phase-2 interaction: collisions / grouping-streaming / killing-limiting ──
# All DOP POP micro-solvers; each has 1 stream input + 1 output, so they CHAIN onto the popsolver
# Pre-Solve input (input 1) via _chain_presolve exactly like the forces. DATA-ONLY: the per-node VEX
# gates (enablerule/rulecode, userandomexpression/randomcode, uselocal/localexpression) are NEVER
# touched and stay at their default 0 — we drive ONLY the parallel typed toggles enablebounding /
# enablerandom / docombine (probe-confirmed these reach the full typed selection with no expression).

def _set_pop_vec3(node, base, vec):
    """Set a 3-component POP parm exposed either as a parmTuple (`t`/`size`) or as scalar components
    (`tx`/`ty`/`tz`, `sizex`/`sizey`/`sizez`). Probe-safe (skips missing parms)."""
    t = node.parmTuple(base)
    if t is not None and len(t) == 3:
        try:
            t.set(tuple(float(x) for x in vec))
            return True
        except Exception:
            pass
    ok = False
    for comp, val in zip(("x", "y", "z"), vec):
        ok = _try_set(node, base + comp, float(val)) or ok
    return ok


def _config_pop_common(node, params, applied):
    """activate + optional partgroup limiting, shared by the Phase-2 stream nodes."""
    if "activate" in params:
        applied["activate"] = _try_set(node, "activate", clamp(float(params["activate"]), 0.0, 1e4))
    if params.get("group"):
        _try_set(node, "usegroup", 1)
        applied["group"] = _try_set(node, "partgroup", str(params["group"]))


def _config_pop_bound_random(node, params, applied, rand_parm):
    """Shared TYPED bounding-region + random-selection rules for popgroup / popstream / popkill.
    Enables the parallel typed toggles only; never enablerule/userandomexpression. `rand_parm` is
    'randbehavior' (group/stream) or 'randombehavior' (kill) — the two nodes name it differently."""
    want_bound = ("boundtype" in params or params.get("size") is not None
                  or params.get("center") is not None or params.get("boundsop")
                  or bool(params.get("enablebounding")))
    if want_bound:
        _try_set(node, "enablebounding", 1)
        applied["enablebounding"] = True
        if "boundtype" in params:
            applied["boundtype"] = _menu_set(node, "boundtype", str(params["boundtype"]), _POPBOUND_TYPE)
        if params.get("size") is not None:
            applied["size"] = _set_pop_vec3(node, "size", params["size"])
        if params.get("center") is not None:
            applied["center"] = _set_pop_vec3(node, "t", params["center"])
        if "boundinvert" in params:
            applied["boundinvert"] = _try_set(node, "boundinvert", bool(params["boundinvert"]))
        if params.get("boundsop"):
            applied["boundsop"] = _try_set(node, "boundsop", str(params["boundsop"]))
        if "boundsource" in params:
            applied["boundsource"] = _menu_set(node, "boundsource", str(params["boundsource"]), _POPBOUND_SOURCE)
        if "boundiso" in params:
            applied["boundiso"] = _try_set(node, "boundiso", clamp(float(params["boundiso"]), -1e9, 1e9))
    want_random = ("chance" in params or "randbehavior" in params
                   or "seed" in params or bool(params.get("enablerandom")))
    if want_random:
        _try_set(node, "enablerandom", 1)
        applied["enablerandom"] = True
        if "randbehavior" in params:
            applied["randbehavior"] = _menu_set(node, rand_parm, str(params["randbehavior"]), _POPRAND_BEHAVIOR)
        if "chance" in params:
            applied["chance"] = _try_set(node, "chance", clamp(float(params["chance"]), 0.0, 1.0))
        if "seed" in params:
            applied["seed"] = _try_set(node, "seed", clamp(float(params["seed"]), 0.0, 1e9))


@endpoint("pop_collision")
def pop_collision(params):
    """Collide particles against a SOP/terrain collider (popcollisiondetect) inside an existing POP
    `dopnet`, chaining onto the popsolver Pre-Solve input. THE TERRAIN BRIDGE: feed a
    `convert_heightfield`/scanned mesh as `source_sop` and particles die/stop/stick/slide on the real
    DEM. Data-only: no VEX/expression fields are touched.

    LIMIT (baked from the node's own behaviour): POP collision does NOT bounce — its responses are
    die/stop/stick/slide only. For restitution/bounce use popobject.bounce (restitution on the object)
    or a Static/RBD object, not this node.

    dopnet (required), solver (else auto-found), name, wire (default true). Collider:
    source_sop (SOP collider path -> collider='soppath'+soppath), or collider
    (relationship|dopobjects|soppath|first|second|third|fourth) + soppath. response
    (none|die|stopped|stuck|slide), defaultpscale (collision radius when no pscale attr), movetohit,
    animategeo. Optional sub-nodes chained UPSTREAM of the detect (so it reads their attached data):
    behavior_response (+behavior_group) builds a popcollisionbehavior per-group response remap;
    ignore_group builds a popcollisionignore (collisionignore group). Common: activate, group. BUILT
    only (caller scrubs the timeline)."""
    dn, solv = _pop_dopnet_and_solver(params)
    node = dn.createNode("popcollisiondetect", params.get("name") or "pop_collision")
    applied = {}
    _config_pop_common(node, params, applied)
    if params.get("source_sop"):
        applied["collider"] = "soppath" if _menu_set(node, "collider", "soppath", _POPCOLL_COLLIDER) else applied.get("collider")
        applied["soppath"] = _try_set(node, "soppath", str(params["source_sop"]))
    else:
        if "collider" in params:
            applied["collider"] = _menu_set(node, "collider", str(params["collider"]), _POPCOLL_COLLIDER)
        if params.get("soppath"):
            applied["soppath"] = _try_set(node, "soppath", str(params["soppath"]))
    if "response" in params:
        applied["response"] = _menu_set(node, "response", str(params["response"]), _POPCOLL_RESPONSE)
    if "defaultpscale" in params:
        applied["defaultpscale"] = _try_set(node, "defaultpscale", clamp(float(params["defaultpscale"]), 0.0, 1e9))
    if "movetohit" in params:
        applied["movetohit"] = _try_set(node, "movetohit", bool(params["movetohit"]))
    if "animategeo" in params:
        applied["animategeo"] = _try_set(node, "animategeo", bool(params["animategeo"]))
    base = params.get("name") or "pop_collision"
    subnodes = {}
    ignore = None
    if params.get("ignore_group"):
        ignore = dn.createNode("popcollisionignore", base + "_ignore")
        _try_set(ignore, "collisionignore", str(params["ignore_group"]))
        subnodes["ignore"] = ignore.path()
    behavior = None
    if "behavior_response" in params or params.get("behavior_group"):
        behavior = dn.createNode("popcollisionbehavior", base + "_behavior")
        if params.get("behavior_group"):
            _try_set(behavior, "usegroup", 1)
            _try_set(behavior, "partgroup", str(params["behavior_group"]))
        if "behavior_response" in params:
            _menu_set(behavior, "response", str(params["behavior_response"]), _POPCOLL_RESPONSE)
        subnodes["behavior"] = behavior.path()
    # stream order: existing pre-solve tail -> ignore -> behavior -> detect -> solver (detect last so
    # it reads the attached ignore/behavior data).
    chain = [n for n in (ignore, behavior, node) if n is not None]
    wired = False
    if solv is not None and bool(params.get("wire", True)):
        for n in chain:
            _chain_presolve(solv, n)
        wired = True
    else:
        for i in range(1, len(chain)):
            chain[i].setInput(0, chain[i - 1], 0)
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return {"node": node.path(), "popcollisiondetect": node.path(), "subnodes": subnodes,
            "dopnet": dn.path(), "solver": solv.path() if solv else None,
            "wired_to_presolve": wired, "no_bounce": True, "applied": applied}


@endpoint("pop_group")
def pop_group(params):
    """Group or split a particle stream by TYPED rules (no VEX), chaining onto the popsolver Pre-Solve
    input of an existing POP `dopnet`. `op` selects the node:
      group  -> popgroup  — tag particles into `groupname`; typed bounding region
        (enablebounding auto-on when boundtype/size/center/boundsop given: boundtype
        box|sphere|geometry|volume, size[x,y,z], center[x,y,z], boundinvert, boundsource
        sop|dopdata|first…, boundsop, boundiso), typed random subset (enablerandom auto-on when
        chance/randbehavior/seed given: randbehavior add|remove, chance 0..1, seed), and boolean
        combination (docombine + combinegroup + combine_op1..4 none|or|and|xor|sub with combine_grp1..4).
      stream -> popstream — split a named sub-stream `streamname` by the SAME typed bounding/random
        rules. Its default enablerule preset (split dead particles) is LEFT UNTOUCHED — pass typed
        bounding/random params to override by region/chance instead.
    The VEX gates (enablerule/rulecode, userandomexpression/randomcode) are never set. dopnet
    (required), solver (else auto-found), name, wire (default true), activate, group (partgroup limit).
    BUILT only."""
    op = str(params.get("op", "group"))
    dn, solv = _pop_dopnet_and_solver(params)
    applied = {}
    if op == "group":
        node = dn.createNode("popgroup", params.get("name") or "pop_group")
        _config_pop_common(node, params, applied)
        if params.get("groupname"):
            applied["groupname"] = _try_set(node, "groupname", str(params["groupname"]))
        _config_pop_bound_random(node, params, applied, "randbehavior")
        if params.get("docombine") or "combine_op1" in params:
            _try_set(node, "docombine", 1)
            applied["docombine"] = True
            if params.get("combinegroup"):
                applied["combinegroup"] = _try_set(node, "combinegroup", str(params["combinegroup"]))
            for i in (1, 2, 3, 4):
                opk = "combine_op%d" % i
                grpk = "combine_grp%d" % i
                if opk in params:
                    applied[opk] = _menu_set(node, opk, str(params[opk]), _POPCOMBINE_OP)
                if params.get(grpk):
                    applied[grpk] = _try_set(node, grpk, str(params[grpk]))
    elif op == "stream":
        node = dn.createNode("popstream", params.get("name") or "pop_stream")
        _config_pop_common(node, params, applied)
        if params.get("streamname"):
            applied["streamname"] = _try_set(node, "streamname", str(params["streamname"]))
        _config_pop_bound_random(node, params, applied, "randbehavior")
    else:
        raise ValueError("unknown op: %s (want group|stream)" % op)
    wired = False
    if solv is not None and bool(params.get("wire", True)):
        _chain_presolve(solv, node)
        wired = True
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return {"node": node.path(), "dopnet": dn.path(), "op": op, "node_type": node.type().name(),
            "solver": solv.path() if solv else None, "wired_to_presolve": wired, "applied": applied}


@endpoint("pop_kill")
def pop_kill(params):
    """Kill / limit / clamp particles by TYPED rules (no VEX), chaining onto the popsolver Pre-Solve
    input of an existing POP `dopnet`. `op` selects the node:
      kill       -> popkill      — typed bounding region (enablebounding auto-on: boundtype
        box|sphere|geometry|volume, size[x,y,z], center[x,y,z], boundinvert, boundsop, boundiso) and
        typed random subset (enablerandom auto-on: randbehavior add|remove, chance 0..1, seed). (Age
        death = life on pop_source + doreapparticles on the solver.) enablerule/randomcode never set.
      limit      -> poplimit     — hard domain box: behaviour none|clamp|bounce|wrap +
        velbehaviour none|clamp|bounce at center[x,y,z]+size[x,y,z]; killoutside; closedends and
        per-face closexneg/closexpos/closeyneg/closeypos/closezneg/closezpos.
      softlimit  -> popsoftlimit — soft push-back region: shape box|sphere (->type), center[x,y,z],
        size[x,y,z], invert, force, vscale, ignoremass.
      speedlimit -> popspeedlimit — clamp motion: speedmin/speedmax (do* auto-on), spinmin/spinmax.
    dopnet (required), solver (else auto-found), name, wire (default true), activate, group. BUILT
    only."""
    op = str(params.get("op", "kill"))
    dn, solv = _pop_dopnet_and_solver(params)
    applied = {}
    if op == "kill":
        node = dn.createNode("popkill", params.get("name") or "pop_kill")
        _config_pop_common(node, params, applied)
        _config_pop_bound_random(node, params, applied, "randombehavior")
    elif op == "limit":
        node = dn.createNode("poplimit", params.get("name") or "pop_limit")
        _config_pop_common(node, params, applied)
        if "behaviour" in params:
            applied["behaviour"] = _menu_set(node, "behaviour", str(params["behaviour"]), _POPLIMIT_BEHAVIOUR)
        if "velbehaviour" in params:
            applied["velbehaviour"] = _menu_set(node, "velbehaviour", str(params["velbehaviour"]), _POPLIMIT_VELBEHAVIOUR)
        if params.get("center") is not None:
            applied["center"] = _set_pop_vec3(node, "t", params["center"])
        if params.get("size") is not None:
            applied["size"] = _set_pop_vec3(node, "size", params["size"])
        if "killoutside" in params:
            applied["killoutside"] = _try_set(node, "killoutside", bool(params["killoutside"]))
        if "closedends" in params:
            applied["closedends"] = _try_set(node, "closedends", bool(params["closedends"]))
        for f in ("closexneg", "closexpos", "closeyneg", "closeypos", "closezneg", "closezpos"):
            if f in params:
                applied[f] = _try_set(node, f, bool(params[f]))
    elif op == "softlimit":
        node = dn.createNode("popsoftlimit", params.get("name") or "pop_softlimit")
        _config_pop_common(node, params, applied)
        if "shape" in params:
            applied["shape"] = _menu_set(node, "type", str(params["shape"]), _POPSOFTLIMIT_TYPE)
        if params.get("center") is not None:
            applied["center"] = _set_pop_vec3(node, "t", params["center"])
        if params.get("size") is not None:
            applied["size"] = _set_pop_vec3(node, "size", params["size"])
        if "invert" in params:
            applied["invert"] = _try_set(node, "invert", bool(params["invert"]))
        if "force" in params:
            applied["force"] = _try_set(node, "force", clamp(float(params["force"]), 0.0, 1e9))
        if "vscale" in params:
            applied["vscale"] = _try_set(node, "vscale", clamp(float(params["vscale"]), 0.0, 1e9))
        if "ignoremass" in params:
            applied["ignoremass"] = _try_set(node, "ignoremass", bool(params["ignoremass"]))
    elif op == "speedlimit":
        node = dn.createNode("popspeedlimit", params.get("name") or "pop_speedlimit")
        _config_pop_common(node, params, applied)
        for tog, val in (("dospeedmin", "speedmin"), ("dospeedmax", "speedmax"),
                         ("dospinmin", "spinmin"), ("dospinmax", "spinmax")):
            if val in params:
                _try_set(node, tog, 1)
                applied[val] = _try_set(node, val, clamp(float(params[val]), 0.0, 1e12))
    else:
        raise ValueError("unknown op: %s (want kill|limit|softlimit|speedlimit)" % op)
    wired = False
    if solv is not None and bool(params.get("wire", True)):
        _chain_presolve(solv, node)
        wired = True
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return {"node": node.path(), "dopnet": dn.path(), "op": op, "node_type": node.type().name(),
            "solver": solv.path() if solv else None, "wired_to_presolve": wired, "applied": applied}


# ── Phase-3 look + output: per-particle properties / instancing-replicate / cache ──
# popproperty/popcolor/popsprite/popvelocity/poplookat/poptorque/popinstance each have 1 stream input
# + 1 output, so they CHAIN onto the popsolver Pre-Solve input (input 1) via _chain_presolve exactly
# like the forces/Phase-2 nodes (cook-verified: pscale/Cd land on the imported points). popreplicate is
# a SOURCE (input 0 = 'Points to Replicate') and wires onto the Sources input (input 2) via _add_source.
# DATA-ONLY: every VEX/expression gate on these nodes (uselocal/localexpression, localconstant,
# localrandom, localramp/localblendramp, uselocaltarget+`code`, uselocaltorque+localforce) is NEVER
# touched and stays at its default 0 — we drive ONLY the typed do*/update* toggles + typed values.

def _set_rgb(node, base, vec):
    """Set an r/g/b color parm exposed as scalar components (`colorr`/`colorg`/`colorb`). Probe-safe."""
    ok = False
    for comp, val in zip(("r", "g", "b"), vec):
        ok = _try_set(node, base + comp, float(val)) or ok
    return ok


def _set_num3(node, base, vec):
    """Set a 3-vector parm exposed as numeric-suffixed components (`target1`/`target2`/`target3`)."""
    ok = False
    for i, val in zip((1, 2, 3), vec):
        ok = _try_set(node, "%s%d" % (base, i), float(val)) or ok
    return ok


def _set_color_ramp(node, parm, entries):
    """Set a `hou.Ramp` color/value parm from typed entries [[pos,[r,g,b]], ...] (Linear basis).
    Probe-confirmed setter path: node.parm(parm).set(hou.Ramp(basis, keys, vals)). Probe-safe."""
    p = node.parm(parm)
    if isinstance(entries, str):        # accept a JSON-encoded ramp (the MCP param Kind is Str)
        try:
            entries = json.loads(entries)
        except Exception:
            return False
    if p is None or not entries:
        return False
    try:
        pts = sorted(([float(e[0]), tuple(float(c) for c in e[1])] for e in entries), key=lambda x: x[0])
        basis = tuple(hou.rampBasis.Linear for _ in pts)
        keys = tuple(pt[0] for pt in pts)
        vals = tuple(pt[1] for pt in pts)
        p.set(hou.Ramp(basis, keys, vals))
        return True
    except Exception:
        return False


def _config_pop_property(node, params, applied):
    """popproperty — physical per-particle attributes; each value is gated by its do* toggle set first."""
    for tog, parm, lo, hi in (
        ("dopscale", "pscale", 0.0, 1e9), ("domass", "mass", 0.0, 1e12),
        ("dobounce", "bounce", 0.0, 1e4), ("dobounceforward", "bounceforward", 0.0, 1e4),
        ("dofriction", "friction", 0.0, 1e4), ("dodynamicfriction", "dynamicfriction", 0.0, 1e4),
        ("dodrag", "drag", 0.0, 1e6), ("dodragexp", "dragexp", 0.0, 4.0),
        ("docling", "cling", 0.0, 1e6),
    ):
        if parm in params:
            _try_set(node, tog, 1)
            applied[parm] = _try_set(node, parm, clamp(float(params[parm]), lo, hi))


def _config_pop_color(node, params, applied):
    """popcolor — Cd/Alpha shaping. updatecolor/updatealpha gate the color/alpha edits; the local*
    VEX string fields (localconstant/localrandom/localramp/localblendramp/localalpha*) stay default."""
    want_color = ("colortype" in params or params.get("color") is not None or "seed" in params
                  or params.get("ramp") is not None or params.get("startcolor") is not None
                  or params.get("endcolor") is not None)
    if want_color:
        _try_set(node, "updatecolor", 1)
        applied["updatecolor"] = True
        if "colortype" in params:
            applied["colortype"] = _menu_set(node, "colortype", str(params["colortype"]), _POPCOLOR_TYPE)
        if params.get("color") is not None:
            applied["color"] = _set_rgb(node, "color", params["color"])
        if "seed" in params:
            applied["seed"] = _try_set(node, "seed", clamp(float(params["seed"]), 0.0, 1e9))
        if params.get("ramp") is not None:
            applied["ramp"] = _set_color_ramp(node, "ramp", params["ramp"])
        if params.get("startcolor") is not None:
            applied["startcolor"] = _set_rgb(node, "startcolor", params["startcolor"])
        if params.get("endcolor") is not None:
            applied["endcolor"] = _set_rgb(node, "endcolor", params["endcolor"])
        if params.get("blendramp") is not None:
            applied["blendramp"] = _set_color_ramp(node, "blendramp", params["blendramp"])
        if params.get("ramprange") is not None and len(params["ramprange"]) >= 2:
            applied["ramprange"] = [_try_set(node, "ramprange1", float(params["ramprange"][0])),
                                    _try_set(node, "ramprange2", float(params["ramprange"][1]))]
    want_alpha = ("alpha" in params or "alphatype" in params or bool(params.get("updatealpha")))
    if want_alpha:
        _try_set(node, "updatealpha", 1)
        applied["updatealpha"] = True
        if "alphatype" in params:
            applied["alphatype"] = _menu_set(node, "alphatype", str(params["alphatype"]), _POPCOLOR_ALPHATYPE)
        if "alpha" in params:
            applied["alpha"] = _try_set(node, "alpha", clamp(float(params["alpha"]), 0.0, 1.0))


def _config_pop_sprite(node, params, applied):
    """popsprite — camera-facing cards. spritemap texture + typed crop/rot/scale/alpha."""
    if params.get("spritemap"):
        applied["spritemap"] = _try_set(node, "spritemap", str(params["spritemap"]))
    if "cropmode" in params:
        _try_set(node, "dotexturecrop", 1)
        applied["cropmode"] = _menu_set(node, "cropmode", str(params["cropmode"]), _POPSPRITE_CROP)
    if "textureindex" in params:
        applied["textureindex"] = _try_set(node, "textureindex", int(clamp(int(params["textureindex"]), 0, 1000000)))
    if "spriterot" in params:
        _try_set(node, "dospriterot", 1)
        applied["spriterot"] = _try_set(node, "spriterot", clamp(float(params["spriterot"]), -1e6, 1e6))
    if params.get("spritescale") is not None:
        _try_set(node, "dospritescale", 1)
        sc = params["spritescale"]
        sc = (sc, sc) if not isinstance(sc, (list, tuple)) else sc
        applied["spritescale"] = [_try_set(node, "spritescalex", clamp(float(sc[0]), 0.0, 1e9)),
                                  _try_set(node, "spritescaley", clamp(float(sc[1] if len(sc) > 1 else sc[0]), 0.0, 1e9))]
    want_alpha = ("alpha" in params or "alphatype" in params or bool(params.get("updatealpha")))
    if want_alpha:
        _try_set(node, "updatealpha", 1)
        applied["updatealpha"] = True
        if "alphatype" in params:
            applied["alphatype"] = _menu_set(node, "alphatype", str(params["alphatype"]), _POPCOLOR_ALPHATYPE)
        if "alpha" in params:
            applied["alpha"] = _try_set(node, "alpha", clamp(float(params["alpha"]), 0.0, 1.0))


@endpoint("pop_property")
def pop_property(params):
    """Shape per-particle attributes with TYPED POP property nodes (no VEX), chaining onto the popsolver
    Pre-Solve input of an existing POP `dopnet`. `op` selects the node (each value's do*/update* gate is
    set before the value so it lands). Data-only: every uselocal*/local*expression/`code` field is left
    at its default 0.

      physical -> popproperty — pscale, mass, bounce, bounceforward, friction, dynamicfriction, drag,
        dragexp, cling (each auto-enables its do* toggle).
      color    -> popcolor — colortype(constant|random|ramp|blend), color[r,g,b], seed, ramp
        ([[pos,[r,g,b]],...] via hou.Ramp), startcolor[r,g,b]/endcolor[r,g,b]/blendramp/ramprange[a,b]
        (blend); alpha via updatealpha+alphatype(constant|ramp)+alpha. updatecolor/updatealpha auto-on.
      sprite   -> popsprite — spritemap (texture), cropmode(offset|spritesheet), textureindex,
        spriterot, spritescale (scalar or [x,y]), alpha+alphatype (do* gates auto-on).
      velocity -> popvelocity — set/scale velocity: velocity[x,y,z] (-> vx/vy/vz), scale.
      lookat   -> poplookat — orient along a goal: mode(point|dir), target[x,y,z], method(immediate|
        turn|spin), dps (deg/sec for turn/spin).
      torque   -> poptorque — spin oriented particles: amount, axis[x,y,z].
    dopnet (required), solver (else auto-found), name, wire (default true), activate, group (partgroup
    limit). BUILT only (caller scrubs the timeline)."""
    op = str(params.get("op", "physical"))
    dn, solv = _pop_dopnet_and_solver(params)
    applied = {}
    if op == "physical":
        node = dn.createNode("popproperty", params.get("name") or "pop_property")
        _config_pop_common(node, params, applied)
        _config_pop_property(node, params, applied)
    elif op == "color":
        node = dn.createNode("popcolor", params.get("name") or "pop_color")
        _config_pop_common(node, params, applied)
        _config_pop_color(node, params, applied)
    elif op == "sprite":
        node = dn.createNode("popsprite", params.get("name") or "pop_sprite")
        _config_pop_common(node, params, applied)
        _config_pop_sprite(node, params, applied)
    elif op == "velocity":
        node = dn.createNode("popvelocity", params.get("name") or "pop_velocity")
        _config_pop_common(node, params, applied)
        if params.get("velocity") is not None:
            applied["velocity"] = _set_pop_vec3(node, "v", params["velocity"])
        if "scale" in params:
            applied["scale"] = _try_set(node, "scale", clamp(float(params["scale"]), -1e9, 1e9))
    elif op == "lookat":
        node = dn.createNode("poplookat", params.get("name") or "pop_lookat")
        _config_pop_common(node, params, applied)
        if "mode" in params:
            applied["mode"] = _menu_set(node, "mode", str(params["mode"]), _POPLOOKAT_MODE)
        if params.get("target") is not None:
            applied["target"] = _set_num3(node, "target", params["target"])
        if "method" in params:
            applied["method"] = _menu_set(node, "method", str(params["method"]), _POPLOOKAT_METHOD)
        if "dps" in params:
            applied["dps"] = _try_set(node, "dps", clamp(float(params["dps"]), 0.0, 1e6))
    elif op == "torque":
        node = dn.createNode("poptorque", params.get("name") or "pop_torque")
        _config_pop_common(node, params, applied)
        if "amount" in params:
            applied["amount"] = _try_set(node, "amount", clamp(float(params["amount"]), -1e9, 1e9))
        if params.get("axis") is not None:
            applied["axis"] = _set_pop_vec3(node, "axis", params["axis"])
    else:
        raise ValueError("unknown op: %s (want physical|color|sprite|velocity|lookat|torque)" % op)
    wired = False
    if solv is not None and bool(params.get("wire", True)):
        _chain_presolve(solv, node)
        wired = True
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return {"node": node.path(), "dopnet": dn.path(), "op": op, "node_type": node.type().name(),
            "solver": solv.path() if solv else None, "wired_to_presolve": wired, "applied": applied}


def _config_pop_replicate(node, params, applied):
    """popreplicate — birth children per parent. Typed emission/shape/birth/noise/velocity; the
    localexpression bind fields (none present as gates here) stay default."""
    if "constantrate" in params:
        _try_set(node, "constantactivate", 1.0)
        applied["constantrate"] = _try_set(node, "constantrate", clamp(float(params["constantrate"]), 0.0, 1e9))
    if "impulserate" in params:
        _try_set(node, "impulseactiveate", 1.0)     # SideFX literal misspelling (probe-confirmed)
        applied["impulserate"] = _try_set(node, "impulserate", clamp(float(params["impulserate"]), 0.0, 1e9))
    if params.get("burst"):
        _try_set(node, "constantactivate", 0.0)
        _try_set(node, "impulseactiveate", 1.0)
        applied["burst"] = True
    if "shape" in params:
        applied["shape"] = _menu_set(node, "shape", str(params["shape"]), _POPREPL_SHAPE)
    if "plane" in params and str(params["plane"]) in _POPREPL_PLANE:
        applied["plane"] = _try_set(node, "orientation", _POPREPL_PLANE[str(params["plane"])])
    if params.get("center") is not None:
        applied["center"] = _set_pop_vec3(node, "t", params["center"])
    if params.get("size") is not None:
        applied["size"] = _set_pop_vec3(node, "size", params["size"])
    if "scale" in params:
        applied["scale"] = _try_set(node, "scale", clamp(float(params["scale"]), 0.0, 1e9))
    if "life" in params:
        applied["life"] = _try_set(node, "life", clamp(float(params["life"]), 0.0, 1e6))
    if "lifevar" in params:
        applied["lifevar"] = _try_set(node, "lifevar", clamp(float(params["lifevar"]), 0.0, 1e6))
    if "seed" in params:
        applied["seed"] = _try_set(node, "seed", clamp(float(params["seed"]), 0.0, 1e9))
    if "killorig" in params:
        applied["killorig"] = _try_set(node, "killorig", bool(params["killorig"]))
    # built-in noise (typed; `type` is a noise-name string, NOT a VEX expression)
    if params.get("noisetype") is not None or "noiseamp" in params:
        _try_set(node, "donoise", 1)
        applied["donoise"] = True
        if params.get("noisetype") is not None:
            applied["noisetype"] = _try_set(node, "type", str(params["noisetype"]))
        if "noiseamp" in params:
            applied["noiseamp"] = _try_set(node, "amp", clamp(float(params["noiseamp"]), -1e6, 1e6))
    # velocity
    if "initvel" in params:
        applied["initvel"] = _menu_set(node, "initvel", str(params["initvel"]), _POPSRC_INITVEL)
    if "inheritvel" in params:
        applied["inheritvel"] = _try_set(node, "inheritvel", clamp(float(params["inheritvel"]), -1e6, 1e6))
    if params.get("velocity") is not None:
        applied["velocity"] = _set_pop_vec3(node, "vel", params["velocity"])
    if "streamname" in params:
        applied["streamname"] = _try_set(node, "streamname", str(params["streamname"]))


@endpoint("pop_instance")
def pop_instance(params):
    """Instancing / render handoff for a POP `dopnet` (no VEX). `op` selects the node:
      instance  -> popinstance — write `instancepath` (+ dopscale+pscale) so the points instance a SOP
        at render time (cheap, no geometry expansion). CHAINS onto the popsolver Pre-Solve input
        (cook-verified: the instancepath string attribute lands on the imported points).
      replicate -> popreplicate — birth children per parent (secondary sprays). Wires onto the
        popsolver Sources input (input 0 = 'Points to Replicate' => it is a SOURCE, not a stream
        modifier). constantrate / impulserate / burst; shape(box|sphere|cylinder|cone|grid|circle|line|
        point); plane(xy|yz|zx); center[x,y,z]; size[x,y,z]; scale; life, lifevar, seed; killorig; noise
        noisetype+noiseamp (donoise auto-on); initvel(use|add|set), inheritvel, velocity[x,y,z];
        streamname.
    dopnet (required), solver (else auto-found), name, wire (default true), activate, group. BUILT
    only (caller scrubs the timeline)."""
    op = str(params.get("op", "instance"))
    dn, solv = _pop_dopnet_and_solver(params)
    applied = {}
    if op == "instance":
        node = dn.createNode("popinstance", params.get("name") or "pop_instance")
        _config_pop_common(node, params, applied)
        if params.get("instancepath"):
            applied["instancepath"] = _try_set(node, "instancepath", str(params["instancepath"]))
        if "pscale" in params:
            _try_set(node, "dopscale", 1)
            applied["pscale"] = _try_set(node, "pscale", clamp(float(params["pscale"]), 0.0, 1e9))
        wired = False
        if solv is not None and bool(params.get("wire", True)):
            _chain_presolve(solv, node)
            wired = True
        wire_key = "wired_to_presolve"
    elif op == "replicate":
        node = dn.createNode("popreplicate", params.get("name") or "pop_replicate")
        _config_pop_common(node, params, applied)
        _config_pop_replicate(node, params, applied)
        wired = False
        if solv is not None and bool(params.get("wire", True)):
            _add_source(solv, dn, node)     # SOURCE node -> solver input 2 (Sources post-solve)
            wired = True
        wire_key = "wired_to_sources"
    else:
        raise ValueError("unknown op: %s (want instance|replicate)" % op)
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return {"node": node.path(), "dopnet": dn.path(), "op": op, "node_type": node.type().name(),
            "solver": solv.path() if solv else None, wire_key: wired, "applied": applied}


@endpoint("pop_cache")
def pop_cache(params):
    """BUILD (never write) a File Cache 2.0 SOP AFTER a pop_import node to cache simulated particles to
    disk. Same confined-write contract as flip_cache/pyro_cache (basedir is FsPath write:true). Resolve
    the SOP to cache from `import_node` (a dopimport/pop_import path), else `input` (any SOP), else
    auto-find a dopimport::2.0 inside `dopnet`'s parent geo.

    HEAVY-OP GUARDRAIL: this ONLY builds and configures the filecache node -- it NEVER presses Save to
    Disk / executes the cook. Writing a multi-frame particle cache on the executor main thread would
    block the session, so the caller/operator triggers the write (the node's 'Save to Disk' button or a
    ROP). The returned `write_path` is where frames WILL land once the human fires it.

    basedir (CONFINED write dir, FsPath write:true), basename, filemethod(constructed|explicit),
    filetype(.bgeo.sc|.vdb), trange(off|normal or single|range), frames [start, end], substeps,
    loadfromdisk (switch to reading the cache). BUILT only. Returns node + write_path + trange +
    frames."""
    # resolve the SOP to cache after
    if params.get("import_node"):
        src = resolve_node(str(params["import_node"]))
    elif params.get("input"):
        src = resolve_node(str(params["input"]))
    elif params.get("dopnet"):
        dn = resolve_node(str(params["dopnet"]))
        geo = dn.parent()
        cand = [c for c in geo.children() if c.type().name() in ("dopimport::2.0", "dopimport", "dopio")]
        if not cand:
            raise ValueError("no dopimport/pop_import node found in %s — pass import_node explicitly" % geo.path())
        src = cand[-1]
    else:
        raise ValueError("pop_cache needs import_node, input, or dopnet to locate the SOP to cache")

    n = src.parent().createNode("filecache::2.0", params.get("name") or "pop_cache")
    n.setInput(0, src)
    n.moveToGoodPosition()
    applied = {}
    # filemethod: default 'constructed' (basedir+basename) so basedir is the confined write root.
    filemethod = str(params.get("filemethod", "constructed"))
    applied["filemethod"] = _menu_set(n, "filemethod", filemethod, _FC_FILEMETHOD)
    # basedir = the CONFINED write root (FsPath write:true), set literally after confinement check.
    write_path = None
    if params.get("basedir"):
        write_path = confined_path(str(params["basedir"]))
        applied["basedir"] = _try_set(n, "basedir", write_path)
    _try_set(n, "mkpath", True)                      # create dirs at write-time (still not now)
    if "basename" in params:
        applied["basename"] = _try_set(n, "basename", str(params["basename"]))
    if "filetype" in params:
        tok = ".vdb" if str(params["filetype"]) in (".vdb", "vdb") else ".bgeo.sc"
        applied["filetype"] = _menu_set(n, "filetype", tok, _FC_FILETYPE)
    # time range
    trange_tok = None
    if "trange" in params:
        trange_tok = "normal" if str(params["trange"]) in ("range", "normal") else "off"
    frames = params.get("frames")
    if frames and len(frames) >= 2:
        trange_tok = "normal"
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        ft = n.parmTuple("f")
        if ft is not None and len(ft) >= 2:
            for idx, val in ((0, float(f1)), (1, float(f2))):
                try:
                    ft[idx].deleteAllKeyframes()
                except Exception:
                    pass
                try:
                    ft[idx].set(val)
                except Exception:
                    pass
            applied["frames"] = [f1, f2]
    if trange_tok is not None:
        applied["trange"] = _menu_set(n, "trange", trange_tok, _FC_TRANGE)
    if "substeps" in params:
        applied["substeps"] = _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "loadfromdisk" in params:
        applied["loadfromdisk"] = _try_set(n, "loadfromdisk", bool(params["loadfromdisk"]))
    # NO n.render()/execute — the write is the caller's job (heavy-op guardrail).
    return {"node": n.path(), "filecache": n.path(), "write_path": write_path,
            "input": src.path(),
            "trange": (n.parm("trange").evalAsString() if n.parm("trange") else None),
            "frames": applied.get("frames"), "written": False, "applied": applied,
            "note": "filecache BUILT + configured; press Save to Disk / trigger the write yourself"}


# ── Phase-4 flocking/steering (T8): boids without VEX ──
# Every popflock/popinteract/popsteer* node has ONE stream input ('Stream to Flock'/'Stream to Interact')
# + 1 output (popproximity's input reads 'Sub-Network Input #1' but is likewise 1-in/1-out), so they
# CHAIN onto the popsolver Pre-Solve input (input 1) via _chain_presolve exactly like the forces.
# DATA-ONLY: every uselocalforce/localforceexpression, uselocalgoal/localgoalexpression,
# uselocalprimuv/primuvcode, uselocal/localexpression is left at its default 0, and popsteerwander's
# uselocalnoise preset (default-on with a fixed benign noise) is left UNTOUCHED — we never author or
# accept an expression string. popsteercustom (VEX behaviour) is excluded from _POP_FLOCK_MAP entirely.

def _config_flock(behavior, node, params, applied):
    """Set the typed parms for one flocking/steering node (probe-confirmed names). Never touches any
    uselocal*/local*expression/*code field. Steer-common (output/weight/forcescale) is attempted on all
    and probe-safely skips the nodes (flock/interact/proximity) that lack them."""
    # steer-common: output menu (crowds|pop -> index), weight, forcescale
    if "output" in params:
        idx = _POPSTEER_OUTPUT.get(str(params["output"]))
        if idx is not None:
            applied["output"] = _try_set(node, "output", idx)
    if "weight" in params:
        applied["weight"] = _try_set(node, "weight", clamp(float(params["weight"]), 0.0, 1e6))
    if "forcescale" in params:
        applied["forcescale"] = _try_set(node, "forcescale", clamp(float(params["forcescale"]), 0.0, 1e9))

    if behavior == "flock":                                   # popflock (bundle) — fully typed, no VEX
        if "numcenters" in params:
            applied["numcenters"] = _try_set(node, "numcenters", int(clamp(int(params["numcenters"]), 1, 100000)))
        for k in ("centralforce", "centerpeakdist", "centermaxdist", "interactionforce",
                  "maxinteract", "velmatchforce", "maxvel"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), -1e9, 1e9))

    elif behavior == "interact":                              # popinteract
        for k in ("positionforce", "velforce", "coreradius", "falloffradius"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), -1e9, 1e9))

    elif behavior == "seek":                                  # popsteerseek (goal is goalx/goaly/goalz)
        if "attracttype" in params:
            applied["attracttype"] = _menu_set(node, "attracttype", str(params["attracttype"]), _POPSTEER_ATTRACT)
        if params.get("goal") is not None:
            applied["goal"] = _set_pop_vec3(node, "goal", params["goal"])
        if params.get("source_sop"):
            _menu_set(node, "usecontextgeo", "none", _POPSTEERSEEK_CTX)
            applied["source_sop"] = _try_set(node, "soppath", str(params["source_sop"]))
        elif "usecontextgeo" in params:
            applied["usecontextgeo"] = _menu_set(node, "usecontextgeo", str(params["usecontextgeo"]), _POPSTEERSEEK_CTX)
        if "arrival" in params:
            applied["arrival"] = _try_set(node, "arrival", bool(params["arrival"]))
        if "brakingdist" in params:
            applied["brakingdist"] = _try_set(node, "brakingdist", clamp(float(params["brakingdist"]), 0.0, 1e9))
        if "pursuit" in params:
            applied["pursuit"] = _try_set(node, "pursuit", bool(params["pursuit"]))
        if "maxdist" in params:
            applied["maxdist"] = _try_set(node, "maxdist", clamp(float(params["maxdist"]), 0.0, 1e12))

    elif behavior == "avoid":                                 # popsteeravoid::2.0
        for k in ("particlescale", "lookaheadtime", "ndist"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), 0.0, 1e9))
        if "maxneighbors" in params:
            applied["maxneighbors"] = _try_set(node, "maxneighbors", int(clamp(int(params["maxneighbors"]), 1, 100000)))

    elif behavior == "wander":                                # popsteerwander (leave uselocalnoise preset)
        for k in ("amp", "swirlsize", "rough"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), -1e9, 1e9))
        if "turb" in params:
            applied["turb"] = _try_set(node, "turb", int(clamp(int(params["turb"]), 0, 100)))

    elif behavior in ("separate", "cohesion", "align"):       # popsteerseparate/cohesion/align
        if "usefov" in params:
            applied["usefov"] = _try_set(node, "usefov", bool(params["usefov"]))
        if "fov" in params:
            applied["fov"] = _try_set(node, "fov", clamp(float(params["fov"]), 0.0, 360.0))
        if "searchradius" in params:
            applied["searchradius"] = _try_set(node, "searchradius", clamp(float(params["searchradius"]), 0.0, 1e9))

    elif behavior == "obstacle":                              # popsteerobstacle::2.0
        for k in ("collisionpadding", "particlescale", "avoidanceforcescale"):
            if k in params:
                applied[k] = _try_set(node, k, clamp(float(params[k]), 0.0, 1e9))

    elif behavior == "proximity":                            # popproximity (typed nearest-neighbour query)
        if "distance" in params:
            applied["distance"] = _try_set(node, "distance", clamp(float(params["distance"]), 0.0, 1e9))
        if "maxcount" in params:
            applied["maxcount"] = _try_set(node, "maxcount", int(clamp(int(params["maxcount"]), 1, 1000000)))


@endpoint("pop_flock")
def pop_flock(params):
    """Boids / steering for a POP `dopnet` (no VEX), chaining ONE behaviour node onto the popsolver
    Pre-Solve input. `behavior` selects the node: flock(popflock) | interact(popinteract) |
    seek(popsteerseek) | avoid(popsteeravoid::2.0) | wander(popsteerwander) | separate(popsteerseparate)
    | cohesion(popsteercohesion) | align(popsteeralign) | obstacle(popsteerobstacle::2.0) |
    proximity(popproximity). popsteercustom (VEX) is excluded. Data-only: every uselocal*/local*
    expression field (incl. wander's uselocalnoise preset) is left at its default and never authored.

    dopnet (required), solver (else auto-found in the dopnet), name, wire (default true). Steering common
    (seek/avoid/wander/separate/cohesion/align/obstacle): output(crowds|pop; default node=POP force so
    the force bites), weight, forcescale. Common: activate, group.
      flock:   numcenters, centralforce, centerpeakdist, centermaxdist, interactionforce, maxinteract,
               velmatchforce, maxvel.
      interact: positionforce, velforce, coreradius, falloffradius.
      seek:    attracttype(position|particles|points|surface), goal[x,y,z], source_sop (explicit goal
               SOP; else usecontextgeo none|dop|first|...), arrival, brakingdist, pursuit, maxdist.
      avoid:   particlescale, lookaheadtime, ndist, maxneighbors.
      wander:  amp, swirlsize, rough, turb.
      separate/cohesion/align: usefov, fov, searchradius (+ forcescale/weight).
      obstacle: collisionpadding, particlescale, avoidanceforcescale.
      proximity: distance, maxcount.
    BUILT only (the caller scrubs the timeline). Returns node path + node_type + applied."""
    behavior = str(params["behavior"])
    if behavior not in _POP_FLOCK_MAP:
        raise ValueError("unknown behavior: %s (want %s)" % (behavior, "/".join(sorted(_POP_FLOCK_MAP))))
    dn, solv = _pop_dopnet_and_solver(params)
    ntype = _POP_FLOCK_MAP[behavior]
    node = dn.createNode(ntype, params.get("name") or ("pop_" + behavior))
    applied = {}
    _config_pop_common(node, params, applied)
    _config_flock(behavior, node, params, applied)
    wired = False
    if solv is not None and bool(params.get("wire", True)):
        _chain_presolve(solv, node)
        wired = True
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return {"node": node.path(), "dopnet": dn.path(), "behavior": behavior,
            "node_type": node.type().name(), "solver": solv.path() if solv else None,
            "wired_to_presolve": wired, "applied": applied}


@endpoint("pop_scatter_sim")
def pop_scatter_sim(params):
    """Terrain/scan particle-scatter MACRO (the FLIP-`flip_flood` analogue): ONE call composes the whole
    POP lane end-to-end into a fresh /obj geo and BUILDS it (never cooks a range). Sparks/embers over a
    scanned building, leaves/debris blown across a DEM valley, dust off terrain, rain/snow over a venue.

    Assembles: emit geo (source_geo SOP, else a default grid) -> dopnet(popobject + popsource emitting
    the emit geo via usecontextgeo='first') -> popsolver::2.0 -> a typed force PRESET (gravity popforce +
    a directional/turbulent popforce) chained onto Pre-Solve -> optional pop_collision against a terrain
    `collider_sop` (convert_heightfield / scanned mesh; die/stop/stick/slide, NO bounce) -> dopimport::2.0
    back to SOP -> optional copy_to_points render handoff (render_geo instanced onto the imported points).

    name (required; fresh /obj geo). Source/emit: source_geo (emit-region SOP; else default grid),
    source_sop (explicit SOP the popsource reads). Emission: preset (sparks|embers|leaves|debris|dust|
    rain|snow; default sparks), count/constantrate (birth rate/sec), life (override preset), gravity
    (override preset magnitude). Collider: collider_sop (terrain/scan SOP), response (none|die|stopped|
    stuck|slide; default slide). Render: render_geo (SOP copied onto imported points via copytopoints).
    dopnet: startframe. display. HEAVY-OP GUARDRAIL: BUILDS + wires only; NEVER cooks a frame range.
    Returns every node path in the assembled lane + applied."""
    name = params["name"]
    preset = str(params.get("preset", "sparks"))
    if preset not in _SCATTER_PRESETS:
        raise ValueError("unknown preset: %s (want %s)" % (preset, "/".join(sorted(_SCATTER_PRESETS))))
    pre = _SCATTER_PRESETS[preset]
    display = bool(params.get("display", False))
    applied = {"preset": preset}

    g = _fresh_geo(name)
    emit = _src_node(g, params.get("source_geo"), "grid",
                     lambda n: n.parmTuple("size").set((10.0, 10.0)) if n.parmTuple("size") else None)
    dn = g.createNode("dopnet", "particles")
    dn.setFirstInput(emit)
    _set_indep(dn, "startframe", int(clamp(int(params.get("startframe", 1)), 1, 1000000)))

    po = dn.createNode("popobject")
    src = dn.createNode("popsource")
    rate = float(params.get("count", params.get("constantrate", 500.0)))
    life = float(params.get("life", pre["life"]))
    _config_popsource(src, {"constantrate": rate, "life": life,
                            "usecontextgeo": params.get("usecontextgeo", "first"),
                            **({"source_sop": params["source_sop"]} if params.get("source_sop") else {})},
                      applied)

    solv = dn.createNode("popsolver")
    solv.setInput(0, po, 0)               # Object
    solv.setInput(2, src, 0)              # Sources (post-solve)

    # gravity = a downward popforce (uniformforce does NOT couple to POP particles)
    gmag = float(params.get("gravity", pre["gravity"]))
    grav = None
    if gmag != 0.0:
        grav = dn.createNode("popforce", "gravity")
        grav.parmTuple("force").set((0.0, -abs(gmag), 0.0))
        _chain_presolve(solv, grav)
        applied["gravity"] = gmag

    # preset wind/turbulence = a second popforce (directional force vec + built-in noise, no VEX)
    wind = None
    wvec = params.get("wind", pre["wind"])
    if any(float(c) != 0.0 for c in wvec) or float(pre["amp"]) != 0.0:
        wind = dn.createNode("popforce", "wind")
        _set_vec(wind, "force", wvec)
        _try_set(wind, "amp", float(pre["amp"]))
        _try_set(wind, "swirlsize", float(pre["swirlsize"]))
        _try_set(wind, "turb", int(pre["turb"]))
        _chain_presolve(solv, wind)
        applied["wind"] = list(wvec)

    # optional terrain collider (the terrain bridge) — popcollisiondetect against a SOP collider
    coll = None
    collider_sop = params.get("collider_sop") or params.get("terrain_sop")
    if collider_sop:
        coll = dn.createNode("popcollisiondetect", "terrain_collision")
        _menu_set(coll, "collider", "soppath", _POPCOLL_COLLIDER)
        _try_set(coll, "soppath", str(collider_sop))
        resp = str(params.get("response", "slide"))
        applied["response"] = _menu_set(coll, "response", resp, _POPCOLL_RESPONSE)
        _chain_presolve(solv, coll)
        applied["collider_sop"] = str(collider_sop)

    solv.setDisplayFlag(True)
    try:
        dn.layoutChildren()
    except Exception:
        pass
    dn.setDisplayFlag(False)
    dn.setRenderFlag(True)

    # DOP -> SOP result import (BUILD only; caller scrubs to populate it)
    imp = g.createNode("dopimport::2.0", "pop_import")
    _try_set(imp, "doppath", dn.path())
    _try_set(imp, "objpattern", "*")

    # optional render handoff: copy render_geo onto the imported points
    cpy = None
    if params.get("render_geo"):
        rgeo = g.createNode("object_merge", "render_proto")
        _try_set(rgeo, "objpath1", str(params["render_geo"]))
        cpy = g.createNode("copytopoints::2.0", "scatter_copy")
        cpy.setInput(0, rgeo, 0)          # Geometry to copy
        cpy.setInput(1, imp, 0)           # Target points
        cpy.setDisplayFlag(display)
        cpy.setRenderFlag(True)
        applied["render_geo"] = str(params["render_geo"])
    else:
        imp.setDisplayFlag(display)
        imp.setRenderFlag(True)

    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "dopnet": dn.path(), "popobject": po.path(), "popsource": src.path(),
            "popsolver": solv.path(), "gravity": grav.path() if grav else None,
            "wind": wind.path() if wind else None,
            "collision": coll.path() if coll else None, "dopimport": imp.path(),
            "copy_to_points": cpy.path() if cpy else None, "preset": preset,
            "built_not_cooked": True, "applied": applied}


# ── Pyro (fire/smoke): modern SOP lane pyrosource -> pyrosolver (SOP) + collisionsource::2.0 ──
# Live-probed on H21.0.671 (menu order/spelling matter). The SOP pyrosolver self-bounds its own
# container (there is NO separate smokeobject at SOP level); combustion is reframed as field
# transforms driven by the source's fuel/burn fields (soot/temperature/div adds), each gated by a
# *_doemit / *_doadd / enable_* toggle. The classic explicit combustion knobs live only on the DOP
# pyrosolver::2.0 and are reached via the optional `legacy_dop` flag.
_PYRO_SOLVER_MENU = ("sparse", "dense", "gpu")            # pyrosolver.solver
_PYRO_COL_TYPE = ("pointvel", "volumevel")                # pyrosolver.col_type
_PYRO_SOOT_MERGE = ("max", "add")                         # pyrosolver.soot_mergemethod (NOT the long list)
_PYRO_TEMP_MERGE = ("pull", "add")                        # pyrosolver.temperature_mergemethod
_PYRO_DISTURB_MODE = ("cont", "blocks")                   # pyrosolver.disturbance_mode
_PYROSOURCE_INIT = ("none", "sourceburn", "source", "sourcecolor", "sourcefuel")  # pyrosource.initialize
_VOLVIS_MODE = ("none", "smoke", "heightfield")           # volumevisualization.vismode (no 'fire' token)
_PYRO_GROUND_TYPES = ("wildfire", "ground_smoke", "volcanic")


def _apply_pyro_source(n, params, applied):
    """pyrosource SOP field-emission params (all probe-verified). `initialize` selects which source
    fields are written; `mode` is an ordered menu whose tokens are literally '0'/'1'/'2'."""
    if "initialize" in params:
        applied["initialize"] = _menu_set(n, "initialize", str(params["initialize"]), _PYROSOURCE_INIT)
    if "mode" in params:
        applied["mode"] = _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 2)))
    if "particlesep" in params:
        applied["particlesep"] = _try_set(n, "particlesep", clamp(float(params["particlesep"]), 1e-3, 1e4))
    if "particlescale" in params:
        applied["particlescale"] = _try_set(n, "particlescale", clamp(float(params["particlescale"]), 0.0, 1e4))
    if "radius" in params:
        applied["radius"] = _try_set(n, "radius", clamp(float(params["radius"]), 1e-4, 1e4))
    if "minpt" in params:
        applied["minpt"] = _try_set(n, "minpt", int(clamp(int(params["minpt"]), 1, 100000)))
    if "maxpt" in params:
        applied["maxpt"] = _try_set(n, "maxpt", int(clamp(int(params["maxpt"]), 1, 1000000)))
    if "densityattrib" in params:
        _try_set(n, "usedensityattrib", 1)
        applied["densityattrib"] = _try_set(n, "densityattrib", str(params["densityattrib"]))
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    return applied


def _apply_collisionsource(n, params, applied):
    """collisionsource::2.0 SOP params (probe-verified). velapproximation is set by INDEX via the same
    friendly->index map FLIP uses (its live menu items are labels with spaces). `points` toggles the
    points-vs-solid-volume approximation."""
    if "approximation" in params:
        applied["approximation"] = _menu_idx(n, "velapproximation", str(params["approximation"]), _COLL_APPROX)
    if "velscale" in params:
        applied["velscale"] = _try_set(n, "velscale", clamp(float(params["velscale"]), 0.0, 1e6))
    if "bandwidth" in params:
        applied["bandwidth"] = _try_set(n, "bandwidth", clamp(float(params["bandwidth"]), 0.0, 1e4))
    if "voxelsize" in params:
        applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "volumename" in params:
        applied["volumename"] = _try_set(n, "volumename", str(params["volumename"]))
    if "points" in params:
        applied["points"] = _try_set(n, "points", bool(params["points"]))
    if "fillinterior" in params:
        applied["fillinterior"] = _try_set(n, "fillinterior", bool(params["fillinterior"]))
    if "computeangular" in params:
        applied["computeangular"] = _try_set(n, "computeangular", bool(params["computeangular"]))
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    return applied


def _apply_pyro_solver(solv, params, applied):
    """SOP pyrosolver deep param sets (all probe-verified on H21.0.671). Enable-toggle gated like the
    FLIP/whitewater helpers: passing a magnitude flips its *_doemit/*_doadd/enable_* toggle on so the
    value actually lands (a bare .set() on a gated parm would silently no-op). Returns `applied`."""
    # -- container / solve --
    if "divsize" in params:
        applied["divsize"] = _try_set(solv, "divsize", clamp(float(params["divsize"]), 1e-4, 1e4))
    if "timescale" in params:
        applied["timescale"] = _try_set(solv, "timescale", clamp(float(params["timescale"]), 1e-4, 1e4))
    if "startframe" in params:
        applied["startframe"] = _try_set(solv, "startframe", int(clamp(int(params["startframe"]), -100000, 100000)))
    if "substeps" in params:
        applied["substeps"] = _try_set(solv, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "minimumsubsteps" in params:
        applied["minimumsubsteps"] = _try_set(solv, "minimumsubsteps",
                                               int(clamp(int(params["minimumsubsteps"]), 1, 100)))
    if "cflcond" in params:
        applied["cflcond"] = _try_set(solv, "cflcond", clamp(float(params["cflcond"]), 0.0, 1e4))
    if "solver" in params:
        applied["solver"] = _menu_set(solv, "solver", str(params["solver"]), _PYRO_SOLVER_MENU)
    if "cacheenabled" in params:
        applied["cacheenabled"] = _try_set(solv, "cacheenabled", bool(params["cacheenabled"]))
    if "cachemaxsize" in params:
        applied["cachemaxsize"] = _try_set(solv, "cachemaxsize", int(clamp(int(params["cachemaxsize"]), 0, 1000000000)))
    if "clampsize" in params:
        applied["clampsize"] = _try_set(solv, "clampsize", bool(params["clampsize"]))
    if "resize_padding" in params:
        applied["resize_padding"] = _try_set(solv, "resize_padding", clamp(float(params["resize_padding"]), 0.0, 1e4))
    # -- combustion / emission (modern reframe) --
    if "soot_amount" in params:
        _try_set(solv, "soot_doemit", 1)
        applied["soot_amount"] = _try_set(solv, "soot_amount", clamp(float(params["soot_amount"]), 0.0, 1e6))
    if "soot_mergemethod" in params:
        applied["soot_mergemethod"] = _menu_set(solv, "soot_mergemethod", str(params["soot_mergemethod"]), _PYRO_SOOT_MERGE)
    if "temperature_amount" in params:
        _try_set(solv, "temperature_doadd", 1)
        applied["temperature_amount"] = _try_set(solv, "temperature_amount",
                                                 clamp(float(params["temperature_amount"]), 0.0, 1e6))
    if "temperature_pullstrength" in params:
        applied["temperature_pullstrength"] = _try_set(solv, "temperature_pullstrength",
                                                       clamp(float(params["temperature_pullstrength"]), 0.0, 1e6))
    if "temperature_mergemethod" in params:
        applied["temperature_mergemethod"] = _menu_set(solv, "temperature_mergemethod",
                                                       str(params["temperature_mergemethod"]), _PYRO_TEMP_MERGE)
    # NOTE: `tempdiffusion` is the REAL SOP temperature-diffusion parm. The old sim_pyro set
    # `temp_diffusion` (a DOP-only name) on this lane, which silently no-oped — fixed here.
    if "tempdiffusion" in params:
        applied["tempdiffusion"] = _try_set(solv, "tempdiffusion", clamp(float(params["tempdiffusion"]), 0.0, 1e6))
    if "tempcooling" in params:
        applied["tempcooling"] = _try_set(solv, "tempcooling", clamp(float(params["tempcooling"]), 0.0, 1e6))
    if "flames_lifespan" in params:
        _try_set(solv, "addflamefield", 1)
        applied["flames_lifespan"] = _try_set(solv, "flames_lifespan", clamp(float(params["flames_lifespan"]), 0.0, 1e6))
    if "addflamefield" in params:
        applied["addflamefield"] = _try_set(solv, "addflamefield", bool(params["addflamefield"]))
    if "div_amount" in params:   # gas expansion ("gas released")
        _try_set(solv, "div_doadd", 1)
        applied["div_amount"] = _try_set(solv, "div_amount", clamp(float(params["div_amount"]), 0.0, 1e6))
    # -- dissipation --
    if "dissipation" in params:
        _try_set(solv, "enable_dissipation", 1)
        applied["dissipation"] = _try_set(solv, "dissipation", clamp(float(params["dissipation"]), 0.0, 1e6))
    if "dissipation_clampbelow" in params:
        applied["dissipation_clampbelow"] = _try_set(solv, "dissipation_clampbelow",
                                                     clamp(float(params["dissipation_clampbelow"]), 0.0, 1e6))
    # -- buoyancy / forces --
    if "buoyancylift" in params:
        _try_set(solv, "enable_buoyancy", 1)
        applied["buoyancylift"] = _try_set(solv, "buoyancylift", clamp(float(params["buoyancylift"]), -1e6, 1e6))
    if "temperature0" in params:
        applied["temperature0"] = _try_set(solv, "temperature0", clamp(float(params["temperature0"]), 0.0, 1e9))
    if "temperature1" in params:
        applied["temperature1"] = _try_set(solv, "temperature1", clamp(float(params["temperature1"]), 0.0, 1e9))
    if "gravaccel" in params:
        applied["gravaccel"] = _try_set(solv, "gravaccel", clamp(float(params["gravaccel"]), -1e6, 1e6))
    if "gravdir" in params:
        applied["gravdir"] = _set_vec(solv, "gravdir", params["gravdir"])
    if "density_gravity_scale" in params:
        _try_set(solv, "enable_density_gravity", 1)
        applied["density_gravity_scale"] = _try_set(solv, "density_gravity_scale",
                                                    clamp(float(params["density_gravity_scale"]), 0.0, 1e6))
    if "terminal_velocity" in params:
        _try_set(solv, "enable_terminal_velocity", 1)
        applied["terminal_velocity"] = _try_set(solv, "terminal_velocity",
                                               clamp(float(params["terminal_velocity"]), 0.0, 1e6))
    if "wind_strength" in params or "wind_direction" in params:
        _try_set(solv, "enable_wind", 1)
        if "wind_strength" in params:
            applied["wind_strength"] = _try_set(solv, "wind_strength", clamp(float(params["wind_strength"]), 0.0, 1e6))
        if "wind_direction" in params:
            applied["wind_direction"] = _set_vec(solv, "wind_direction", params["wind_direction"])
    # -- shape / detail (all typed, no VEX) --
    if "disturbance" in params:
        _try_set(solv, "enable_disturbance", 1)
        applied["disturbance"] = _try_set(solv, "disturbance", clamp(float(params["disturbance"]), 0.0, 1e4))
        for k in ("disturbance_blocksize", "disturbance_rough", "disturbance_pulselength", "disturbance_lacunarity"):
            if k in params:
                _try_set(solv, k, clamp(float(params[k]), 0.0, 1e4))
        if "disturbance_maxoct" in params:
            _try_set(solv, "disturbance_maxoct", int(clamp(int(params["disturbance_maxoct"]), 1, 20)))
        if "disturbance_mode" in params:
            applied["disturbance_mode"] = _menu_set(solv, "disturbance_mode",
                                                   str(params["disturbance_mode"]), _PYRO_DISTURB_MODE)
    if "turbulence" in params:
        _try_set(solv, "enable_turbulence", 1)
        applied["turbulence"] = _try_set(solv, "turbulence", clamp(float(params["turbulence"]), 0.0, 1e4))
        for k in ("turbulence_swirlsize", "turbulence_grain", "turbulence_pulselength", "turbulence_seed"):
            if k in params:
                _try_set(solv, k, clamp(float(params[k]), 0.0, 1e9))
        if "turbulence_levels" in params:
            _try_set(solv, "turbulence_levels", int(clamp(int(params["turbulence_levels"]), 1, 20)))
    if "shredding" in params:   # NOTE: the SOP has no `shredding_mode` parm (spec guess); dropped.
        _try_set(solv, "enable_shredding", 1)
        applied["shredding"] = _try_set(solv, "shredding", clamp(float(params["shredding"]), 0.0, 1e4))
        for k in ("shredding_blocksize", "shredding_rough", "shredding_pulselength", "shredding_lacunarity"):
            if k in params:
                _try_set(solv, k, clamp(float(params[k]), 0.0, 1e4))
        if "shredding_maxoct" in params:
            _try_set(solv, "shredding_maxoct", int(clamp(int(params["shredding_maxoct"]), 1, 20)))
    # -- viscosity --
    if "viscosity" in params:
        _try_set(solv, "enable_viscosity", 1)
        applied["viscosity"] = _try_set(solv, "viscosity", clamp(float(params["viscosity"]), 0.0, 1e6))
    # -- collision behaviour --
    if "col_type" in params:
        applied["col_type"] = _menu_set(solv, "col_type", str(params["col_type"]), _PYRO_COL_TYPE)
    if "col_bandwidth" in params:
        applied["col_bandwidth"] = _try_set(solv, "col_bandwidth", clamp(float(params["col_bandwidth"]), 0.0, 1e4))
    if "col_velscale" in params:
        applied["col_velscale"] = _try_set(solv, "col_velscale", clamp(float(params["col_velscale"]), 0.0, 1e6))
    return applied


def _apply_pyro_dop(solv, params, applied):
    """Legacy DOP pyrosolver::2.0 explicit-combustion params (probe-verified). Combustion is enabled by
    default (`enable_combustion`); these are the classic Ignition/Burn/Heat/Gas knobs. Here the
    temperature-diffusion parm really IS `temp_diffusion` (default 0.5) — the opposite of the SOP lane."""
    _try_set(solv, "enable_combustion", 1)
    for key, parm, lo, hi in (
        ("ignitiontemp", "ignitiontemp", 0.0, 1e6),
        ("burnrate", "burnrate", 0.0, 1e6),
        ("fuelinefficiency", "fuelinefficiency", 0.0, 1e6),
        ("heatoutput", "heatoutput", 0.0, 1e6),
        ("gasrelease", "gasrelease", 0.0, 1e6),
        ("tempdiffusion", "temp_diffusion", 0.0, 1e6),
        ("tempcooling", "cooling_rate", 0.0, 1e6),
    ):
        if key in params:
            applied[key] = _try_set(solv, parm, clamp(float(params[key]), lo, hi))
    if "confinement" in params:
        _try_set(solv, "enable_confinement", 1)
        applied["confinement"] = _try_set(solv, "confinementscale", clamp(float(params["confinement"]), 0.0, 1e6))
    return applied


@endpoint("sim_pyro")
def sim_pyro(params):
    """Pyro (fire/smoke). MIGRATED off the legacy DOP scaffold to the modern SOP lane: a fresh /obj geo
    holding source geo -> pyrosource -> SOP pyrosolver (input0 = Sources), with an optional
    collisionsource::2.0 collider on input1 (`collision_geo`). The SOP pyrosolver self-bounds its
    container (divsize is the #1 cost/detail knob); combustion is reframed as field transforms.

    Container/solve: divsize, timescale, startframe, substeps(+minimumsubsteps), cflcond, solver
    (sparse|dense|gpu), cacheenabled, cachemaxsize, clampsize, resize_padding. Combustion/emission:
    soot_amount(+soot_mergemethod max|add) = burn->smoke, temperature_amount(+temperature_pullstrength,
    temperature_mergemethod pull|add), tempdiffusion, tempcooling, flames_lifespan(+addflamefield),
    div_amount = gas expansion. Source emission (pyrosource, applied to the built source): particlesep
    (emission resolution/detail — the source-side counterpart to the solver divsize), particlescale,
    radius, mode(0|1|2), minpt/maxpt, densityattrib (enables usedensityattrib), group. Dissipation:
    dissipation(+dissipation_clampbelow). Buoyancy/forces:
    buoyancylift(+temperature0/temperature1), gravaccel(+gravdir), density_gravity_scale,
    terminal_velocity, wind_strength(+wind_direction). Shape/detail: disturbance(+mode/blocksize/rough/
    pulselength/maxoct/lacunarity), turbulence(+swirlsize/grain/pulselength/levels/seed), shredding
    (+blocksize/rough/pulselength/maxoct/lacunarity). viscosity. Collision: col_type (pointvel|volumevel),
    col_bandwidth, col_velscale. `source_field` picks the pyrosource `initialize` preset (default source).

    Set `legacy_dop`=true to build the DOP pyrosolver::2.0 lane instead (smokeobject + pyrosolver::2.0),
    exposing the explicit combustion knobs ignitiontemp/burnrate/fuelinefficiency/heatoutput/gasrelease/
    confinement (+tempdiffusion=temp_diffusion, tempcooling=cooling_rate). BUILT, never auto-simulated
    (the caller scrubs the timeline). No solver cook on the main thread (heavy-op rule)."""
    name = params["name"]
    frames = int(clamp(int(params.get("frames", 120)), 1, 10000))
    display = bool(params.get("display", False))
    legacy = bool(params.get("legacy_dop", False))
    p = dict(params)
    if "startframe" not in p:
        p["startframe"] = 1
    g = _fresh_geo(name)
    src = _src_node(g, params.get("source_geo"), "sphere", None)
    if legacy:
        dn = g.createNode("dopnet", "pyro")
        dn.setFirstInput(src)
        obj = dn.createNode("smokeobject")
        solv = dn.createNode("pyrosolver::2.0")
        solv.setFirstInput(obj)
        applied = {}
        _apply_pyro_dop(solv, p, applied)
        if "divsize" in p:
            applied["divsize"] = _try_set(obj, "divsize", clamp(float(p["divsize"]), 1e-4, 1e4))
        _try_set(dn, "startframe", int(p["startframe"]))
        if "substeps" in p:
            _try_set(dn, "substep", int(clamp(int(p["substeps"]), 1, 100)))
        solv.setDisplayFlag(True)
        try:
            dn.layoutChildren()
        except Exception:
            pass
        dn.setDisplayFlag(display)
        dn.setRenderFlag(True)
        g.setDisplayFlag(display)
        g.layoutChildren()
        return {"node": g.path(), "dopnet": dn.path(), "smokeobject": obj.path(),
                "solver": solv.path(), "lane": "legacy_dop", "frames": frames, "applied": applied}
    # modern SOP lane
    psrc = g.createNode("pyrosource", "source")
    psrc.setFirstInput(src)
    _menu_set(psrc, "initialize", str(params.get("source_field", "source")), _PYROSOURCE_INIT)
    _apply_pyro_source(psrc, params, {})
    solv = g.createNode("pyrosolver", "solver")
    solv.setInput(0, psrc)                       # Sources
    coll = None
    if params.get("collision_geo"):
        om = g.createNode("object_merge", "collider_geo")
        _try_set(om, "objpath1", str(params["collision_geo"]))
        coll = g.createNode("collisionsource::2.0", "collider")
        coll.setFirstInput(om)
        _try_set(coll, "velapproximation", 0)    # static collider by default
        if "divsize" in params:
            _try_set(coll, "voxelsize", clamp(float(params["divsize"]), 1e-4, 1e4))
        solv.setInput(1, coll)                   # Collision Geometry/Volumes
    applied = {}
    _apply_pyro_solver(solv, p, applied)
    solv.setDisplayFlag(display)
    solv.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    result = {"node": g.path(), "source": psrc.path(), "solver": solv.path(),
              "lane": "sop", "migrated": True, "frames": frames, "applied": applied}
    if coll is not None:
        result["collider"] = coll.path()
    return result


@endpoint("pyro_source")
def pyro_source(params):
    """Pyro emission source (pyrosource SOP): rasterizes geometry/points into source fields (density/
    temperature/fuel/burn/vel) that feed a pyrosolver's Sources input. `input` = the geo SOP; the
    pyrosource is wired after it. initialize (none|sourceburn|source|sourcecolor|sourcefuel — which
    fields get written), mode (0|1|2 ordered menu), particlesep, particlescale, radius, minpt/maxpt,
    densityattrib (enables usedensityattrib), group. Continuous-emit vs one-shot depends on whether the
    upstream geo is time-dependent. BUILT only (no cook — a bare cook here just rasterizes the source)."""
    n = child_after(params["input"], "pyrosource", params.get("name"))
    applied = {}
    _apply_pyro_source(n, params, applied)
    return {"node": n.path(), "pyrosource": n.path(), "applied": applied}


@endpoint("pyro_collision")
def pyro_collision(params):
    """Geometry/terrain -> pyro collision volume (Collision Source 2.0 SOP). The scene-collision bridge:
    feed its output into a pyrosolver's Collision input (input 1) so smoke deflects off a DEM ground,
    buildings, or RBD debris. `input` = the collider geo SOP. approximation (none|backward|central|
    forward = velapproximation, for moving colliders), velscale, bandwidth, voxelsize (match the solver
    divsize), volumename, points (points vs solid-volume), fillinterior, computeangular, group. BUILT
    only (a bare cook just builds the collision VDB — never a sim)."""
    n = child_after(params["input"], "collisionsource::2.0", params.get("name"))
    applied = {}
    _apply_collisionsource(n, params, applied)
    return {"node": n.path(), "collisionsource": n.path(), "applied": applied}


def _pyro_ground_tuning(kind):
    """Per-type default SOP pyrosolver params for the ground macro (caller params override these)."""
    if kind == "wildfire":
        return {"temperature_amount": 2.0, "soot_amount": 1.0, "flames_lifespan": 1.5,
                "buoyancylift": 1.0, "dissipation": 0.15, "div_amount": 0.5}
    if kind == "volcanic":
        return {"temperature_amount": 4.0, "soot_amount": 2.0, "flames_lifespan": 1.0,
                "buoyancylift": 4.0, "dissipation": 0.05, "div_amount": 2.0}
    # ground_smoke: cool, heavy, rolls along the ground
    return {"temperature_amount": 0.2, "soot_amount": 1.5, "buoyancylift": 0.1,
            "dissipation": 0.2, "tempcooling": 1.0}


@endpoint("pyro_ground")
def pyro_ground(params):
    """Ground/wildfire macro (the flagship "fire/smoke over a real DEM" workflow, mirrors flip_flood).
    One call: DEM heightfield -> convertheightfield -> collisionsource::2.0 collider (static, volume) +
    a pyrosource over an emission region -> SOP pyrosolver (tuned per `type` + wind) -> volumevisualization.

    `input` = the DEM heightfield SOP. type (wildfire|ground_smoke|volcanic) picks combustion tuning and
    the pyrosource preset (sourceburn for fire types, source for smoke). Emission region: `fire_line` = a
    curve/line SOP path (fire creeping along a ridge), else `source_region` [minx,miny,minz,maxx,maxy,maxz]
    box, else a default box at the DEM centre on the ground. divsize (voxel size, also the collider
    voxelsize + source particlesep), wind_strength(+wind_direction), lod (heightfield->poly decimation),
    densityscale (viewport). Any solver knob (temperature_amount/soot_amount/flames_lifespan/buoyancylift/
    dissipation/div_amount/tempcooling/disturbance/turbulence) overrides the per-type default. Collider
    tuning (bandwidth/points) also accepted. Only the heightfield conversion is cooked (a mesh, never a
    sim); BUILT, the caller scrubs the timeline to run it."""
    name = params["name"]
    display = bool(params.get("display", False))
    kind = str(params.get("type", "wildfire"))
    if kind not in _PYRO_GROUND_TYPES:
        raise ValueError("unknown type: %s (want %s)" % (kind, "/".join(_PYRO_GROUND_TYPES)))
    divsize = clamp(float(params.get("divsize", 1.0)), 1e-3, 1e5)
    g = _fresh_geo(name)
    # DEM in + polys (single safe mesh cook to size the emission region)
    om = g.createNode("object_merge", "dem")
    _try_set(om, "objpath1", str(params["input"]))
    conv = g.createNode("convertheightfield", "dem_polys")
    conv.setFirstInput(om)
    _try_set(conv, "lod", clamp(float(params.get("lod", 1.0)), 0.01, 1.0))
    geo = conv.geometry()
    bbox = geo.boundingBox()
    smin, smax = bbox.minvec(), bbox.maxvec()
    cx, cz = (smin[0] + smax[0]) * 0.5, (smin[2] + smax[2]) * 0.5
    ground_y = smax[1]
    # collider from the DEM
    coll = g.createNode("collisionsource::2.0", "collider")
    coll.setFirstInput(conv)
    _try_set(coll, "velapproximation", 0)   # static terrain -> no collider velocity
    _try_set(coll, "voxelsize", divsize)
    _apply_collisionsource(coll, params, {})
    # emission geometry
    mode = None
    if params.get("fire_line"):
        emit_geo = g.createNode("object_merge", "fire_line")
        _try_set(emit_geo, "objpath1", str(params["fire_line"]))
        mode = "fire_line"
    else:
        emit_geo = g.createNode("box", "emit")
        region = params.get("source_region")
        if region and len(region) >= 6:
            rx0, ry0, rz0, rx1, ry1, rz1 = [float(v) for v in region[:6]]
            if emit_geo.parmTuple("size") is not None:
                emit_geo.parmTuple("size").set((abs(rx1 - rx0), max(abs(ry1 - ry0), divsize), abs(rz1 - rz0)))
            if emit_geo.parmTuple("t") is not None:
                emit_geo.parmTuple("t").set(((rx0 + rx1) * 0.5, (ry0 + ry1) * 0.5, (rz0 + rz1) * 0.5))
            mode = "source_region"
        else:
            span_x = max((smax[0] - smin[0]) * 0.25, divsize)
            span_z = max((smax[2] - smin[2]) * 0.25, divsize)
            span_y = max((smax[1] - smin[1]) * 0.1, divsize)
            if emit_geo.parmTuple("size") is not None:
                emit_geo.parmTuple("size").set((span_x, span_y, span_z))
            if emit_geo.parmTuple("t") is not None:
                emit_geo.parmTuple("t").set((cx, ground_y, cz))
            mode = "center_default"
    psrc = g.createNode("pyrosource", "source")
    psrc.setFirstInput(emit_geo)
    _menu_set(psrc, "initialize", "source" if kind == "ground_smoke" else "sourceburn", _PYROSOURCE_INIT)
    _try_set(psrc, "particlesep", divsize)
    _apply_pyro_source(psrc, params, {})
    # solver tuned by type + wind + caller overrides
    solv = g.createNode("pyrosolver", "solver")
    solv.setInput(0, psrc)
    solv.setInput(1, coll)
    tuning = _pyro_ground_tuning(kind)
    tuning["divsize"] = divsize
    if "wind_strength" in params or "wind_direction" in params:
        tuning["wind_strength"] = params.get("wind_strength", 1.0)
        if "wind_direction" in params:
            tuning["wind_direction"] = params["wind_direction"]
    for k in ("temperature_amount", "soot_amount", "flames_lifespan", "buoyancylift", "dissipation",
              "div_amount", "tempcooling", "disturbance", "turbulence", "startframe", "substeps"):
        if k in params:
            tuning[k] = params[k]
    applied = {}
    _apply_pyro_solver(solv, tuning, applied)
    # viewport viz
    vis = g.createNode("volumevisualization", "viz")
    vis.setFirstInput(solv)
    _menu_set(vis, "vismode", "smoke", _VOLVIS_MODE)
    if "densityscale" in params:
        _try_set(vis, "densityscale", clamp(float(params["densityscale"]), 0.0, 1e6))
    vis.setDisplayFlag(display)
    vis.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "dem_merge": om.path(), "convert": conv.path(), "collider": coll.path(),
            "source": psrc.path(), "solver": solv.path(), "visualize": vis.path(),
            "type": kind, "divsize": round(divsize, 4), "mode": mode,
            "collider_wired": solv.input(1) is not None, "applied": applied}


# ── Pyro Phase-2 (explosions): pyroburstsource (SOP) -> pyrosolver -> volumevisualization (+RBD) ──
# Live-probed on H21.0.671. `pyroburstsource` shapetype has FOUR tokens (spec listed only two):
# explosion/muzzle/shockwave/rings. It emits one burst per input point ("Points for Pyro Bursts").
# pscale/vscale are gated by createpscaleattrib/createvattrib (both default ON); noiseshape_amp/_size/
# _rough are gated by noiseshape_enable. Ramp parms (expramp/intexpramp/extexpramp/…) are NOT exposed.
_PYROBURST_SHAPE = ("explosion", "muzzle", "shockwave", "rings")   # pyroburstsource.shapetype


def _apply_pyroburst(n, params, applied):
    """pyroburstsource SOP param sets (all probe-verified on H21.0.671). Gated params flip their
    enable toggle when a magnitude is passed so the value actually lands. Returns `applied`."""
    if "shapetype" in params:
        applied["shapetype"] = _menu_set(n, "shapetype", str(params["shapetype"]), _PYROBURST_SHAPE)
    if "size" in params:
        applied["size"] = _try_set(n, "size", clamp(float(params["size"]), 1e-4, 1e6))
    if "sizescale" in params:
        applied["sizescale"] = _try_set(n, "sizescale", clamp(float(params["sizescale"]), 0.0, 1e6))
    if "size_var" in params:
        applied["size_var"] = _try_set(n, "size_var", clamp(float(params["size_var"]), 0.0, 1e6))
    if "dir" in params:
        applied["dir"] = _set_vec(n, "dir", params["dir"])
    if "dir_var" in params:
        applied["dir_var"] = _try_set(n, "dir_var", clamp(float(params["dir_var"]), 0.0, 360.0))
    if "expdur" in params:
        applied["expdur"] = _try_set(n, "expdur", int(clamp(int(params["expdur"]), 0, 100000)))
    # out / inner / outer / directional expansion scales
    for k, parm in (("outexpscale", "outexpscale"), ("outintexpscale", "outintexpscale"),
                    ("outextexpscale", "outextexpscale"), ("direxpscale", "direxpscale")):
        if k in params:
            applied[k] = _try_set(n, parm, clamp(float(params[k]), 0.0, 1e6))
    # trailing embers / sparks
    if "trailingnum" in params:
        applied["trailingnum"] = _try_set(n, "trailingnum", int(clamp(int(params["trailingnum"]), 0, 10000000)))
    if "trailinglen" in params:
        applied["trailinglen"] = _try_set(n, "trailinglen", clamp(float(params["trailinglen"]), 0.0, 1e6))
    if "trailingthickness" in params:
        applied["trailingthickness"] = _try_set(n, "trailingthickness", clamp(float(params["trailingthickness"]), 0.0, 1e6))
    if "trailingsep" in params:
        applied["trailingsep"] = _try_set(n, "trailingsep", clamp(float(params["trailingsep"]), 1e-4, 1e4))
    # copies per burst (rings/shockwave shells)
    if "copynum" in params:
        applied["copynum"] = _try_set(n, "copynum", int(clamp(int(params["copynum"]), 1, 100000)))
    # shape noise (gated by noiseshape_enable)
    if any(k in params for k in ("noiseshape", "noiseshape_amp", "noiseshape_size", "noiseshape_rough")):
        _try_set(n, "noiseshape_enable", 1)
        applied["noiseshape"] = True
        if "noiseshape_amp" in params:
            applied["noiseshape_amp"] = _try_set(n, "noiseshape_amp", clamp(float(params["noiseshape_amp"]), 0.0, 1e4))
        if "noiseshape_size" in params:
            applied["noiseshape_size"] = _try_set(n, "noiseshape_size", clamp(float(params["noiseshape_size"]), 1e-4, 1e4))
        if "noiseshape_rough" in params:
            applied["noiseshape_rough"] = _try_set(n, "noiseshape_rough", clamp(float(params["noiseshape_rough"]), 0.0, 1e4))
    # timing
    if "startframe" in params:
        applied["startframe"] = _try_set(n, "startframe", clamp(float(params["startframe"]), -1e6, 1e6))
    if "startframe_offset" in params:
        applied["startframe_offset"] = _try_set(n, "startframe_offset", clamp(float(params["startframe_offset"]), -1e6, 1e6))
    # per-point scale / velocity (createpscaleattrib/createvattrib default ON; force to be safe)
    if "pscale" in params:
        _try_set(n, "createpscaleattrib", 1)
        applied["pscale"] = _try_set(n, "pscale", clamp(float(params["pscale"]), 0.0, 1e6))
    if "vscale" in params:
        _try_set(n, "createvattrib", 1)
        applied["vscale"] = _try_set(n, "vscale", clamp(float(params["vscale"]), 0.0, 1e6))
    return applied


@endpoint("pyro_burst")
def pyro_burst(params):
    """Pyro explosion/fireball source (pyroburstsource SOP): the modern burst emitter that turns input
    points into an explosion/shockwave/muzzle/ring shell plus trailing embers, feeding a pyrosolver's
    Sources input. `input` = the points SOP ("Points for Pyro Bursts" — one burst per point); the
    pyroburstsource is wired after it.

    shapetype (explosion|muzzle|shockwave|rings — PROBE CORRECTION: the live menu has FOUR tokens, not
    the two the spec listed), size(+sizescale/size_var), dir [x,y,z](+dir_var degrees), expdur
    (explosion duration frames), outexpscale/outintexpscale/outextexpscale (out/inner/outer expansion),
    direxpscale (directional expansion), trailingnum/trailinglen/trailingthickness/trailingsep (ember
    trails), copynum (shell copies per burst), noiseshape(+_amp/_size/_rough, enables noiseshape_enable),
    startframe(+startframe_offset), pscale/vscale (per-point scale/velocity). Ramp parms are not exposed.
    BUILT only (a bare cook just rasterizes the burst points at the current frame — no sim)."""
    n = child_after(params["input"], "pyroburstsource", params.get("name"))
    applied = {}
    _apply_pyroburst(n, params, applied)
    return {"node": n.path(), "pyroburstsource": n.path(), "applied": applied}


def _pyro_explosion_tuning():
    """Default SOP pyrosolver params for the explosion macro (caller params override these): hot, fast-
    expanding fireball with a short flame lifespan and heavy smoke."""
    return {"temperature_amount": 4.0, "soot_amount": 2.0, "flames_lifespan": 0.8,
            "div_amount": 3.0, "buoyancylift": 2.0, "dissipation": 0.1}


@endpoint("pyro_explosion")
def pyro_explosion(params):
    """Explosion macro (the destruction-shot one-call). Fresh /obj geo holding a single burst point at
    `center` -> pyroburstsource (shapetype=explosion + trailing embers) -> SOP pyrosolver (hot fireball:
    high temperature_amount + div_amount expansion + soot_amount smoke, short flames_lifespan) ->
    volumevisualization. If `debris_geo` is given, a parallel Bullet RBD net (object_merge -> rbd
    material fracture -> rbdbulletsolver) is built in the same geo so one call yields fireball + flying
    debris (the RBD<->pyro synergy).

    center [x,y,z] (burst origin), size (burst size), divsize (voxel size = #1 cost/detail knob, also
    the solver container detail), dir [x,y,z](+dir_var), expdur, trailing embers (trailingnum/trailinglen/
    trailingthickness/trailingsep), startframe, pscale/vscale. Solver overrides: temperature_amount,
    soot_amount, flames_lifespan, div_amount, buoyancylift, dissipation, substeps, disturbance,
    turbulence, wind_strength(+wind_direction). RBD: debris_geo (SOP/obj path), materialtype, seed,
    fracture (default true — fracture the debris; false = leave intact). densityscale (viewport). Only
    the RBD fracture is cooked (a mesh op, like sim_rbd); the pyro solver is BUILT, never auto-simulated
    (the caller scrubs the timeline). No solver cook on the main thread (heavy-op rule)."""
    name = params["name"]
    display = bool(params.get("display", False))
    divsize = clamp(float(params.get("divsize", 0.5)), 1e-3, 1e5)
    center = params.get("center", [0.0, 0.0, 0.0])
    g = _fresh_geo(name)
    # single burst point at the explosion center (grid 1x1 = exactly one point, cheap + no multiparm)
    pt = g.createNode("grid", "burst_point")
    _try_set(pt, "rows", 1)
    _try_set(pt, "cols", 1)
    _set_vec(pt, "t", center)
    # burst source
    burst = g.createNode("pyroburstsource", "burst")
    burst.setFirstInput(pt)
    bparams = {"shapetype": "explosion"}
    for k in ("size", "sizescale", "size_var", "dir", "dir_var", "expdur", "outexpscale",
              "outintexpscale", "outextexpscale", "direxpscale", "trailingnum", "trailinglen",
              "trailingthickness", "trailingsep", "copynum", "noiseshape", "noiseshape_amp",
              "noiseshape_size", "noiseshape_rough", "startframe", "startframe_offset",
              "pscale", "vscale"):
        if k in params:
            bparams[k] = params[k]
    burst_applied = {}
    _apply_pyroburst(burst, bparams, burst_applied)
    # solver tuned for a fireball + caller overrides
    solv = g.createNode("pyrosolver", "solver")
    solv.setInput(0, burst)
    tuning = _pyro_explosion_tuning()
    tuning["divsize"] = divsize
    if "wind_strength" in params or "wind_direction" in params:
        tuning["wind_strength"] = params.get("wind_strength", 1.0)
        if "wind_direction" in params:
            tuning["wind_direction"] = params["wind_direction"]
    for k in ("temperature_amount", "soot_amount", "flames_lifespan", "div_amount", "buoyancylift",
              "dissipation", "disturbance", "turbulence", "startframe", "substeps"):
        if k in params:
            tuning[k] = params[k]
    solver_applied = {}
    _apply_pyro_solver(solv, tuning, solver_applied)
    # viewport viz
    vis = g.createNode("volumevisualization", "viz")
    vis.setFirstInput(solv)
    _menu_set(vis, "vismode", "smoke", _VOLVIS_MODE)
    if "densityscale" in params:
        _try_set(vis, "densityscale", clamp(float(params["densityscale"]), 0.0, 1e6))
    vis.setDisplayFlag(display)
    vis.setRenderFlag(True)
    result = {"node": g.path(), "burst_point": pt.path(), "burst": burst.path(),
              "solver": solv.path(), "visualize": vis.path(),
              "center": [round(float(c), 4) for c in center], "divsize": round(divsize, 4),
              "burst_applied": burst_applied, "solver_applied": solver_applied}
    # optional RBD debris (the destruction-shot synergy) — parallel chain in the same geo
    if params.get("debris_geo"):
        dg = g.createNode("object_merge", "debris_in")
        _try_set(dg, "objpath1", str(params["debris_geo"]))
        do_fracture = bool(params.get("fracture", True))
        if do_fracture:
            frac = g.createNode("rbdmaterialfracture", "debris_fracture")
            frac.setFirstInput(dg)
            if params.get("materialtype"):
                _try_set(frac, "materialtype", str(params["materialtype"]))
            _try_set(frac, "randomseed", int(params.get("seed", 0)))
            rbd_in = frac
            result["fracture"] = frac.path()
        else:
            rbd_in = dg
        rbd = g.createNode("rbdbulletsolver", "debris_solver")
        rbd.setFirstInput(rbd_in)
        if "startframe" in params:
            _try_set(rbd, "startframe", float(params["startframe"]))
        if "substeps" in params:
            _try_set(rbd, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
        rbd.setRenderFlag(True)
        result["debris_merge"] = dg.path()
        result["debris_solver"] = rbd.path()
        result["debris_wired"] = rbd.input(0) is not None
    g.setDisplayFlag(display)
    g.layoutChildren()
    return result


# ── Pyro Phase-3 (look + delivery): volumevisualization / pyrobakevolume / pyropostprocess::2.0 / ──
# filecache::2.0. Live-probed on H21.0.671. PROBE CORRECTIONS vs spec:
#   * volumevisualization: vismode = none|smoke|heightfield (NO 'fire'/'both'/'off' tokens, and NO
#     top-level `adaptation` parm — both spec guesses). 'emission' is the scalar `emitscale` (0 = off,
#     no separate toggle). shadowcolor/ambientshadows/maxres each ride a `set*` gate toggle.
#   * pyrobakevolume: firecolormode/scattercolormode = ramp|blackbody|planck; smokecolormode = const|ramp.
#     Ramp parms (smokecolorramp/firecolorramp/...) are NOT exposed (typed handlers don't set ramps).
#   * pyropostprocess::2.0: conv_cullvolumenames rides conv_docull; conv_scalevolumenames/conv_scale ride
#     conv_doscale; flamedensity rides doflamedensity (gate flipped when a value is passed).
#   * filecache::2.0: identical write contract to flip_cache (+ optional filetype bgeo|vdb for VDB delivery).
_VOLVIS_RAMPMODE = ("none", "clamp", "periodic")         # volumevisualization.*rampmode
_PYROBAKE_SMOKECOLORMODE = ("const", "ramp")             # pyrobakevolume.smokecolormode
_PYROBAKE_FIRECOLORMODE = ("ramp", "blackbody", "planck")  # pyrobakevolume.firecolormode/scattercolormode
_FC_FILETYPE = (".bgeo.sc", ".vdb")                      # filecache::2.0.filetype


@endpoint("pyro_visualize")
def pyro_visualize(params):
    """Viewport look for a pyro/volume field (volumevisualization SOP): CHEAP viewport shading only, NOT
    a render (that is pyro_shade -> Karma). `input` = the solver (or any volume SOP); the
    volumevisualization is wired after it.

    vismode (none|smoke|heightfield -- PROBE CORRECTION: the live menu has NO 'fire'/'both'/'off' token,
    only these three), densityscale, shadowscale, densityfield (density volume name), cdfield (color
    volume name), rangemin/rangemax (density remap), emitscale (emission intensity; 0 = off -- there is
    no separate emission toggle), emitfield/emitcdfield (emission + emission-color volume names),
    ambientshadows (rides setambientshadows), shadowcolor [r,g,b] (rides setshadowcolor), maxres (rides
    setmaxres). PROBE CORRECTION: there is no top-level `adaptation` parm. BUILT only (a bare cook just
    re-derives the viewport visualization -- no sim)."""
    n = child_after(params["input"], "volumevisualization", params.get("name"))
    applied = {}
    if "vismode" in params:
        applied["vismode"] = _menu_set(n, "vismode", str(params["vismode"]), _VOLVIS_MODE)
    if "densityscale" in params:
        applied["densityscale"] = _try_set(n, "densityscale", clamp(float(params["densityscale"]), 0.0, 1e6))
    if "shadowscale" in params:
        applied["shadowscale"] = _try_set(n, "shadowscale", clamp(float(params["shadowscale"]), 0.0, 1e6))
    if "densityfield" in params:
        applied["densityfield"] = _try_set(n, "densityfield", str(params["densityfield"]))
    if "cdfield" in params:
        applied["cdfield"] = _try_set(n, "cdfield", str(params["cdfield"]))
    if "rangemin" in params:
        applied["rangemin"] = _try_set(n, "rangemin", clamp(float(params["rangemin"]), -1e9, 1e9))
    if "rangemax" in params:
        applied["rangemax"] = _try_set(n, "rangemax", clamp(float(params["rangemax"]), -1e9, 1e9))
    if "emitscale" in params:
        applied["emitscale"] = _try_set(n, "emitscale", clamp(float(params["emitscale"]), 0.0, 1e6))
    if "emitfield" in params:
        applied["emitfield"] = _try_set(n, "emitfield", str(params["emitfield"]))
    if "emitcdfield" in params:
        applied["emitcdfield"] = _try_set(n, "emitcdfield", str(params["emitcdfield"]))
    if "ambientshadows" in params:
        _try_set(n, "setambientshadows", 1)
        applied["ambientshadows"] = _try_set(n, "ambientshadows", clamp(float(params["ambientshadows"]), 0.0, 1e6))
    if "shadowcolor" in params:
        _try_set(n, "setshadowcolor", 1)
        applied["shadowcolor"] = _set_vec(n, "shadowcolor", params["shadowcolor"])
    if "maxres" in params:
        _try_set(n, "setmaxres", 1)
        applied["maxres"] = _try_set(n, "maxres", int(clamp(int(params["maxres"]), 1, 100000)))
    return {"node": n.path(), "volumevisualization": n.path(), "applied": applied}


@endpoint("pyro_shade")
def pyro_shade(params):
    """Render-ready shading fields for a pyro volume (pyrobakevolume SOP), the KARMA render-prep node:
    bakes smoke/fire/scatter look into shading volumes + assigns a Pyro material. `input` = the solver
    (or pyro_post output); the pyrobakevolume is wired after it. Pairs with setup_karma/add_light.

    Material: assignmaterial, shop_materialpath. Smoke: enablesmoke, densityscale, smokecolor [r,g,b],
    smokecolormode (const|ramp), shadowint, ambientshadows. Fire: enablefire, kfire (fire intensity),
    firecolormode (ramp|blackbody|planck -- PROBE tokens), firetempscale, firetemp0/firetemp1 (temp
    remap), fireadapt (tone-map adaptation). Scatter (fireball hot-core): enablescatter, kscatter,
    khotcore, scattertempscale, scattercolormode (ramp|blackbody|planck). Blur: enableblur, blurstepping,
    nblursteps. maxres (rides setmaxres). Ramp parms are NOT exposed. BUILT only (a bare cook just bakes
    the shading fields at the current frame -- no sim)."""
    n = child_after(params["input"], "pyrobakevolume", params.get("name"))
    applied = {}
    # material
    if "assignmaterial" in params:
        applied["assignmaterial"] = _try_set(n, "assignmaterial", bool(params["assignmaterial"]))
    if "shop_materialpath" in params:
        applied["shop_materialpath"] = _try_set(n, "shop_materialpath", str(params["shop_materialpath"]))
    # smoke
    if "enablesmoke" in params:
        applied["enablesmoke"] = _try_set(n, "enablesmoke", bool(params["enablesmoke"]))
    if "densityscale" in params:
        applied["densityscale"] = _try_set(n, "densityscale", clamp(float(params["densityscale"]), 0.0, 1e6))
    if "smokecolor" in params:
        applied["smokecolor"] = _set_vec(n, "smokecolor", params["smokecolor"])
    if "smokecolormode" in params:
        applied["smokecolormode"] = _menu_set(n, "smokecolormode", str(params["smokecolormode"]), _PYROBAKE_SMOKECOLORMODE)
    if "shadowint" in params:
        applied["shadowint"] = _try_set(n, "shadowint", clamp(float(params["shadowint"]), 0.0, 1e6))
    if "ambientshadows" in params:
        applied["ambientshadows"] = _try_set(n, "ambientshadows", clamp(float(params["ambientshadows"]), 0.0, 1e6))
    # fire
    if "enablefire" in params:
        applied["enablefire"] = _try_set(n, "enablefire", bool(params["enablefire"]))
    if "kfire" in params:
        _try_set(n, "enablefire", 1)
        applied["kfire"] = _try_set(n, "kfire", clamp(float(params["kfire"]), 0.0, 1e6))
    if "firecolormode" in params:
        applied["firecolormode"] = _menu_set(n, "firecolormode", str(params["firecolormode"]), _PYROBAKE_FIRECOLORMODE)
    if "firetempscale" in params:
        applied["firetempscale"] = _try_set(n, "firetempscale", clamp(float(params["firetempscale"]), 0.0, 1e6))
    if "firetemp0" in params:
        applied["firetemp0"] = _try_set(n, "firetemp0", clamp(float(params["firetemp0"]), 0.0, 1e9))
    if "firetemp1" in params:
        applied["firetemp1"] = _try_set(n, "firetemp1", clamp(float(params["firetemp1"]), 0.0, 1e9))
    if "fireadapt" in params:
        applied["fireadapt"] = _try_set(n, "fireadapt", clamp(float(params["fireadapt"]), 0.0, 1e6))
    # scatter (hot core)
    if "enablescatter" in params:
        applied["enablescatter"] = _try_set(n, "enablescatter", bool(params["enablescatter"]))
    if "kscatter" in params:
        _try_set(n, "enablescatter", 1)
        applied["kscatter"] = _try_set(n, "kscatter", clamp(float(params["kscatter"]), 0.0, 1e6))
    if "khotcore" in params:
        applied["khotcore"] = _try_set(n, "khotcore", clamp(float(params["khotcore"]), 0.0, 1e6))
    if "scattertempscale" in params:
        applied["scattertempscale"] = _try_set(n, "scattertempscale", clamp(float(params["scattertempscale"]), 0.0, 1e6))
    if "scattercolormode" in params:
        applied["scattercolormode"] = _menu_set(n, "scattercolormode", str(params["scattercolormode"]), _PYROBAKE_FIRECOLORMODE)
    # blur
    if "enableblur" in params:
        applied["enableblur"] = _try_set(n, "enableblur", bool(params["enableblur"]))
    if "blurstepping" in params:
        applied["blurstepping"] = _try_set(n, "blurstepping", bool(params["blurstepping"]))
    if "nblursteps" in params:
        applied["nblursteps"] = _try_set(n, "nblursteps", int(clamp(int(params["nblursteps"]), 1, 100000)))
    if "maxres" in params:
        _try_set(n, "setmaxres", 1)
        applied["maxres"] = _try_set(n, "maxres", int(clamp(int(params["maxres"]), 1, 100000)))
    return {"node": n.path(), "pyrobakevolume": n.path(), "applied": applied}


@endpoint("pyro_post")
def pyro_post(params):
    """Export/render prep for a pyro sim (pyropostprocess::2.0 SOP): computes temperature/field min/max
    (Karma needs them) and optionally converts native volumes to VDB for a .vdb sequence. `input` = the
    solver; hand its output to export_cache/vdb_convert/pyro_cache for delivery.

    computeminmax (compute field min/max, default on), conv_vdb (convert native volumes -> VDB),
    conv_combine (combine into one VDB stream), conv_usefp16 (half-float VDB), conv_cullvolumenames
    (space-sep volume names to drop -- rides conv_docull), conv_scalevolumenames (volume names to scale --
    rides conv_doscale) + conv_scale, flamedensity (bind a flame->density scalar -- rides doflamedensity),
    bind_density/bind_flame (source volume-name bindings). BUILT only (a bare cook just post-processes the
    current frame -- no sim; multi-frame VDB export is pyro_cache/export_cache's job)."""
    n = child_after(params["input"], "pyropostprocess::2.0", params.get("name"))
    applied = {}
    if "computeminmax" in params:
        applied["computeminmax"] = _try_set(n, "computeminmax", bool(params["computeminmax"]))
    if "conv_vdb" in params:
        applied["conv_vdb"] = _try_set(n, "conv_vdb", bool(params["conv_vdb"]))
    if "conv_combine" in params:
        applied["conv_combine"] = _try_set(n, "conv_combine", bool(params["conv_combine"]))
    if "conv_usefp16" in params:
        applied["conv_usefp16"] = _try_set(n, "conv_usefp16", bool(params["conv_usefp16"]))
    if "conv_cullvolumenames" in params:
        _try_set(n, "conv_docull", 1)
        applied["conv_cullvolumenames"] = _try_set(n, "conv_cullvolumenames", str(params["conv_cullvolumenames"]))
    if "conv_scalevolumenames" in params or "conv_scale" in params:
        _try_set(n, "conv_doscale", 1)
        if "conv_scalevolumenames" in params:
            applied["conv_scalevolumenames"] = _try_set(n, "conv_scalevolumenames", str(params["conv_scalevolumenames"]))
        if "conv_scale" in params:
            applied["conv_scale"] = _try_set(n, "conv_scale", clamp(float(params["conv_scale"]), 0.0, 1e6))
    if "flamedensity" in params:
        _try_set(n, "doflamedensity", 1)
        applied["flamedensity"] = _try_set(n, "flamedensity", clamp(float(params["flamedensity"]), 0.0, 1e6))
    if "bind_density" in params:
        applied["bind_density"] = _try_set(n, "bind_density", str(params["bind_density"]))
    if "bind_flame" in params:
        applied["bind_flame"] = _try_set(n, "bind_flame", str(params["bind_flame"]))
    return {"node": n.path(), "pyropostprocess": n.path(), "applied": applied}


@endpoint("pyro_cache")
def pyro_cache(params):
    """BUILD (never write) a File Cache 2.0 SOP after a pyro sim to cache it to disk. `input` = the SOP
    to cache (the solver, or a pyro_post output for a VDB sequence). Same confined write contract as
    flip_cache/flipbook/export_* (FsPath write:true): `file` = the explicit output path (filemethod=
    explicit); `filetype` (bgeo|vdb) picks the format for a native vs VDB pyro cache.

    HEAVY-OP GUARDRAIL: this ONLY builds and configures the filecache node -- it NEVER presses Save to
    Disk / executes the cook. Writing a multi-frame volume cache on the executor main thread would block
    the session, so the caller/operator triggers the write (the node's 'Save to Disk' button or a ROP). The
    returned `write_path` is where frames WILL land once the human fires it.

    trange (single|range -> `trange` off|normal), frames [start, end], substeps, loadfromdisk. The
    filecache's own 'execute' button is left untouched. Returns node + write_path + trange + frames."""
    out_path = confined_path(params["file"])
    n = child_after(params["input"], "filecache::2.0", params.get("name"))
    applied = {}
    # explicit, confined write target (never the node's default unconfined basedir)
    _menu_set(n, "filemethod", "explicit", _FC_FILEMETHOD)
    applied["file"] = _try_set(n, "file", out_path)
    _try_set(n, "mkpath", True)                     # create dirs at write-time (still not now)
    if "filetype" in params:
        tok = ".vdb" if str(params["filetype"]) in (".vdb", "vdb") else ".bgeo.sc"
        applied["filetype"] = _menu_set(n, "filetype", tok, _FC_FILETYPE)
    if "basename" in params:
        _try_set(n, "basename", str(params["basename"]))
    # time range
    trange_tok = None
    if "trange" in params:
        trange_tok = "normal" if str(params["trange"]) in ("range", "normal") else "off"
    frames = params.get("frames")
    if frames and len(frames) >= 2:
        trange_tok = "normal"
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        ft = n.parmTuple("f")
        if ft is not None and len(ft) >= 2:
            # f1/f2 default to $FSTART/$FEND expressions which ignore a plain .set();
            # drop the expression on each component, then set the literal frame.
            for idx, val in ((0, float(f1)), (1, float(f2))):
                try:
                    ft[idx].deleteAllKeyframes()
                except Exception:
                    pass
                try:
                    ft[idx].set(val)
                except Exception:
                    pass
            applied["frames"] = [f1, f2]
    if trange_tok is not None:
        applied["trange"] = _menu_set(n, "trange", trange_tok, _FC_TRANGE)
    if "substeps" in params:
        applied["substeps"] = _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "loadfromdisk" in params:
        applied["loadfromdisk"] = _try_set(n, "loadfromdisk", bool(params["loadfromdisk"]))
    # NO n.render()/execute — the write is the caller's job (heavy-op guardrail).
    return {"node": n.path(), "filecache": n.path(), "write_path": out_path,
            "trange": (n.parm("trange").evalAsString() if n.parm("trange") else None),
            "frames": applied.get("frames"), "written": False, "applied": applied,
            "note": "filecache BUILT + configured; press Save to Disk / trigger the write yourself"}


# ── Whitewater (Phase 4): modern SOP lane whitewatersource::3.0 -> whitewatersolver (SOP) -> post ──
# Live-probed on H21.0.671. The legacy DOP nodes (whitewaterobject::2.0/whitewatersolver::2.0) are DOP-
# only and cannot be created as SOPs; the SOP `whitewatersolver` (unversioned) IS the modern wrapper.
_WW_MERGE = {"add": 0, "maximum": 1, "override": 2}      # whitewatersource::3.0 mergemethod (Add/Maximum/Override)
_WW_OUTPUT = {"particles": 0, "fog": 1, "mesh": 2}       # whitewaterpostprocess output (Particles/Fog Volume/Mesh)


def _set_grav(node, parm, val, downward):
    """Set a gravity/buoyancy vec parm from either a 3-vec or a scalar magnitude (down/up axis)."""
    t = node.parmTuple(parm)
    if t is None:
        return False
    try:
        if isinstance(val, (list, tuple)):
            vec = tuple(float(x) for x in val)[:3]
            if len(vec) != len(t):
                return False
        else:
            m = float(val)
            vec = (0.0, -m, 0.0) if downward else (0.0, m, 0.0)
        t.set(vec)
        return True
    except Exception:
        return False


def _apply_ww_source(n, params):
    """Whitewater Source 3.0 emission masks (all probe-verified). Returns what applied."""
    a = {}
    if "voxelsize" in params:
        _try_set(n, "usevoxelsize", 1)
        a["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "emissionamount" in params:
        a["emissionamount"] = _try_set(n, "emissionamount", clamp(float(params["emissionamount"]), 0.0, 1e6))
    if "mergemethod" in params:
        a["mergemethod"] = _menu_idx(n, "mergemethod", str(params["mergemethod"]), _WW_MERGE)
    # depth limiting (limitbydepth on by default; maxhalfwidth caps the band, depthrange = [near,far])
    if "limitbydepth" in params:
        a["limitbydepth"] = _try_set(n, "limitbydepth", bool(params["limitbydepth"]))
    if "maxhalfwidth" in params:
        _try_set(n, "limitbydepth", 1)
        a["maxhalfwidth"] = _try_set(n, "maxhalfwidth", int(clamp(int(params["maxhalfwidth"]), 1, 1000)))
    if "depthrange" in params:
        a["depthrange"] = _set_vec(n, "depthrange", params["depthrange"])
    # emission masks: each toggle (+ optional [lo,hi] range or scale)
    if "remapspeed" in params:
        a["remapspeed"] = _try_set(n, "remapspeed", bool(params["remapspeed"]))
    if "speedrange" in params:
        a["speedrange"] = _set_vec(n, "speedrange", params["speedrange"])
    if "curvature" in params:
        a["curvature"] = _try_set(n, "enablecurvature", bool(params["curvature"]))
    if "curvaturerange" in params:
        a["curvaturerange"] = _set_vec(n, "curvaturerange", params["curvaturerange"])
    if "acceleration" in params:
        a["acceleration"] = _try_set(n, "enableacceleration", bool(params["acceleration"]))
    if "accelerationrange" in params:
        a["accelerationrange"] = _set_vec(n, "accelerationrange", params["accelerationrange"])
    if "vorticity" in params:
        a["vorticity"] = _try_set(n, "enablevorticity", bool(params["vorticity"]))
    if "vorticityrange" in params:
        a["vorticityrange"] = _set_vec(n, "vorticityrange", params["vorticityrange"])
    if "splash" in params:
        _try_set(n, "enablesplash", 1)
        a["splash"] = _try_set(n, "splashscale", clamp(float(params["splash"]), 0.0, 1e6))
    if "pressure" in params:
        a["pressure"] = _try_set(n, "enablepressure", bool(params["pressure"]))
    # deformation (squish/stretch share the enabledeformation toggle; both strict [0,1] on the node)
    if "squish" in params or "stretch" in params:
        _try_set(n, "enabledeformation", 1)
        if "squish" in params:
            a["squish"] = _try_set(n, "squishscale", clamp(float(params["squish"]), 0.0, 1.0))
        if "stretch" in params:
            a["stretch"] = _try_set(n, "stretchscale", clamp(float(params["stretch"]), 0.0, 1.0))
    return a


def _apply_ww_solver(n, params):
    """Whitewater Solver (SOP) params (all probe-verified). Returns what applied."""
    a = {}
    for key, parm, lo, hi in (
        ("scale", "scale", 0.0, 1e6),
        ("voxelsize", "voxelsize", 1e-4, 1e4),
        ("goaldepth", "goaldepth", 0.0, 1e6),
        ("bounce", "bounce", 0.0, 1e4),
        ("bounceforward", "bounceforward", 0.0, 1e4),
        ("friction", "friction", 0.0, 1e4),
        ("dynamicfriction", "dynamicfriction", 0.0, 1e4),
        ("lifespan", "lifespan", 0.0, 1e6),
        ("seed", "seed", 0.0, 1e9),
        ("emissionamount", "emissionamount", 0.0, 1e6),
    ):
        if key in params:
            a[key] = _try_set(n, parm, clamp(float(params[key]), lo, hi))
    if "substep" in params:
        a["substep"] = _try_set(n, "substep", int(clamp(int(params["substep"]), 1, 100)))
    if "cacheenabled" in params:
        a["cacheenabled"] = _try_set(n, "cacheenabled", bool(params["cacheenabled"]))
    if "gravity" in params:
        a["gravity"] = _set_grav(n, "gravity", params["gravity"], downward=True)
    if "buoyancy" in params:
        a["buoyancy"] = _set_grav(n, "buoyancy", params["buoyancy"], downward=False)
    if "windspeed" in params or "wind" in params or "airresist" in params:
        _try_set(n, "enable_wind", 1)
        if "wind" in params:
            a["wind"] = _set_vec(n, "wind", params["wind"])
        if "windspeed" in params:
            a["windspeed"] = _try_set(n, "windspeed", clamp(float(params["windspeed"]), 0.0, 1e6))
        if "airresist" in params:
            a["airresist"] = _try_set(n, "airresist", clamp(float(params["airresist"]), 0.0, 1e6))
    # clumping = the PBF density control; defstiffness = its stiffness magnitude
    if "clumping" in params:
        a["clumping"] = _try_set(n, "enabledensitycontrol", bool(params["clumping"]))
    if "defstiffness" in params:
        a["defstiffness"] = _try_set(n, "defstiffness", clamp(float(params["defstiffness"]), 0.0, 1e6))
    if "viscosity" in params:
        _try_set(n, "enableviscosity", 1)
        a["viscosity"] = _try_set(n, "viscosityc", clamp(float(params["viscosity"]), 0.0, 1e6))
    elif "enableviscosity" in params:
        a["enableviscosity"] = _try_set(n, "enableviscosity", bool(params["enableviscosity"]))
    if "erosion" in params:
        _try_set(n, "enableerosion", 1)
        a["erosion"] = _try_set(n, "erosionstrength", clamp(float(params["erosion"]), 0.0, 1e4))
    elif "enableerosion" in params:
        a["enableerosion"] = _try_set(n, "enableerosion", bool(params["enableerosion"]))
    return a


def _apply_ww_post(n, params):
    """Whitewater Post Process params (all probe-verified). Returns what applied."""
    a = {}
    if "output" in params:
        a["output"] = _menu_idx(n, "output", str(params["output"]), _WW_OUTPUT)
    if "displayassphere" in params:
        a["displayassphere"] = _try_set(n, "displayassphere", bool(params["displayassphere"]))
    if "voxelsize" in params:
        a["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "adaptivity" in params:
        a["adaptivity"] = _try_set(n, "adaptivity", clamp(float(params["adaptivity"]), 0.0, 1e4))
    # density ramps: range (enables density_set), by-depth, by-age
    if "density_range" in params:
        _try_set(n, "density_set", 1)
        a["density_range"] = _set_vec(n, "density_range", params["density_range"])
    if "density_bydepth" in params:
        a["density_bydepth"] = _try_set(n, "density_bydepth", bool(params["density_bydepth"]))
    if "density_depthrange" in params:
        _try_set(n, "density_bydepth", 1)
        a["density_depthrange"] = _set_vec(n, "density_depthrange", params["density_depthrange"])
    if "density_byage" in params:
        a["density_byage"] = _try_set(n, "density_byage", bool(params["density_byage"]))
    if "density_agerange" in params:
        _try_set(n, "density_byage", 1)
        a["density_agerange"] = _set_vec(n, "density_agerange", params["density_agerange"])
    # pscale ramps
    if "pscale_range" in params:
        _try_set(n, "pscale_set", 1)
        a["pscale_range"] = _set_vec(n, "pscale_range", params["pscale_range"])
    if "pscale_bydepth" in params:
        a["pscale_bydepth"] = _try_set(n, "pscale_bydepth", bool(params["pscale_bydepth"]))
    if "pscale_depthrange" in params:
        _try_set(n, "pscale_bydepth", 1)
        a["pscale_depthrange"] = _set_vec(n, "pscale_depthrange", params["pscale_depthrange"])
    if "pscale_byage" in params:
        a["pscale_byage"] = _try_set(n, "pscale_byage", bool(params["pscale_byage"]))
    # clip container (size/center imply the clip)
    if "clipcontainer" in params:
        a["clipcontainer"] = _try_set(n, "clipcontainer", bool(params["clipcontainer"]))
    if "size" in params:
        _try_set(n, "clipcontainer", 1)
        a["size"] = _set_vec(n, "size", params["size"])
    if "center" in params:
        _try_set(n, "clipcontainer", 1)
        a["center"] = _set_vec(n, "t", params["center"])
    return a


def _wire_ww_inputs(node, params, wired):
    """Wire optional container(1)/collisions(2) SOP paths into a whitewater source/solver."""
    if params.get("container"):
        c = hou.node(str(params["container"]))
        if c is not None:
            try:
                node.setInput(1, c)
                wired["container"] = True
            except Exception:
                pass
    if params.get("collisions"):
        x = hou.node(str(params["collisions"]))
        if x is not None:
            try:
                node.setInput(2, x)
                wired["collisions"] = True
            except Exception:
                pass


@endpoint("whitewater_source")
def whitewater_source(params):
    """Whitewater emission source (Whitewater Source 3.0 SOP): builds the emission masks that decide
    where foam/spray/bubbles are born from a FLIP liquid sim. `input` = the FLIP liquid particles SOP
    (input 0 = Liquid Simulation). Optional `container`/`collisions` SOP paths wire inputs 1/2.

    Masks: remapspeed (+speedrange [lo,hi]), curvature (+curvaturerange), acceleration
    (+accelerationrange), vorticity (+vorticityrange), splash (scale, enables splash), pressure,
    squish/stretch (share enabledeformation), limitbydepth (+maxhalfwidth) + depthrange, voxelsize
    (enables usevoxelsize), emissionamount, mergemethod (add|maximum|override). BUILT only (no cook —
    cooking would step the upstream FLIP sim)."""
    n = child_after(params["input"], "whitewatersource::3.0", params.get("name"))
    wired = {}
    _wire_ww_inputs(n, params, wired)
    applied = _apply_ww_source(n, params)
    return {"node": n.path(), "whitewatersource": n.path(), "applied": applied, "wired": wired}


@endpoint("sim_whitewater")
def sim_whitewater(params):
    """Whitewater (foam/spray/bubble). MIGRATED off the legacy DOP scaffold (whitewaterobject::2.0/
    whitewatersolver::2.0) to the modern SOP lane: whitewatersource::3.0 -> whitewatersolver (SOP) ->
    optional whitewaterpostprocess.

    `input` = the FLIP liquid sim SOP (particles) that drives emission; if omitted, a fresh /obj geo
    `name` with a placeholder grid source is built (structural). Optional `container`/`collisions` SOP
    paths wire the source+solver Container/Collisions inputs. Source masks accept the whitewater_source
    params; solver params: scale, voxelsize, goaldepth, bounce(+bounceforward), friction/dynamicfriction,
    gravity/buoyancy (scalar or vec), wind (windspeed/airresist), clumping/defstiffness, viscosity
    (enableviscosity+magnitude), erosion (enableerosion+strength), lifespan, substep, cacheenabled, seed,
    emissionamount. Set `post`=true to also append a whitewaterpostprocess. BUILT, never auto-simulated
    (the caller scrubs to run it)."""
    frames = int(clamp(int(params.get("frames", 120)), 1, 10000))
    display = bool(params.get("display", False))
    build_post = bool(params.get("post", False))
    g = None
    if params.get("input"):
        wsrc = child_after(params["input"], "whitewatersource::3.0", params.get("name"))
        parent = wsrc.parent()
    else:
        name = params["name"]
        g = _fresh_geo(name)
        src = _src_node(g, params.get("source_geo"), "grid", None)
        wsrc = g.createNode("whitewatersource::3.0", "wwsource")
        try:
            wsrc.setInput(0, src)
        except Exception:
            pass
        parent = g
    wired = {}
    _wire_ww_inputs(wsrc, params, wired)
    solver = parent.createNode("whitewatersolver")
    solver.setInput(0, wsrc)                 # Emission and Fluid Fields <- source
    _wire_ww_inputs(solver, params, {})      # Container(1)/Collisions(2) also feed the solver
    applied_source = _apply_ww_source(wsrc, params)
    applied_solver = _apply_ww_solver(solver, params)
    post = None
    if build_post:
        post = parent.createNode("whitewaterpostprocess")
        post.setInput(0, solver)
        _apply_ww_post(post, params)
    terminal = post or solver
    terminal.setDisplayFlag(display)
    terminal.setRenderFlag(True)
    try:
        parent.layoutChildren()
    except Exception:
        pass
    if g is not None:
        g.setDisplayFlag(display)
        g.layoutChildren()
    result = {"node": (g.path() if g is not None else terminal.path()),
              "source": wsrc.path(), "solver": solver.path(), "migrated": True,
              "frames": frames, "wired": wired,
              "applied_source": applied_source, "applied_solver": applied_solver}
    if post is not None:
        result["post"] = post.path()
    return result


@endpoint("whitewater_post")
def whitewater_post(params):
    """Whitewater post-process (Whitewater Post Process SOP): shapes the solved foam/spray/bubble for
    render. `input` = the whitewater solver SOP. output (particles|fog|mesh -> `output`), displayassphere,
    voxelsize + adaptivity (for the mesh/fog output), density ramps (density_range enables density_set;
    density_bydepth + density_depthrange; density_byage + density_agerange), pscale ramps (pscale_range,
    pscale_bydepth + pscale_depthrange, pscale_byage), clipcontainer (+ size/center imply the clip). The
    foam/spray/bubble split rides the solver's own bubble/foam/spray attributes. BUILT only (no cook —
    cooking would step the upstream whitewater sim)."""
    n = child_after(params["input"], "whitewaterpostprocess", params.get("name"))
    applied = _apply_ww_post(n, params)
    return {"node": n.path(), "whitewaterpostprocess": n.path(), "applied": applied}


# Particle Fluid Surface 3.0 live menu tokens (probed H21.0.671 — order/spelling matter).
_SURF_METHOD = ("particlefluid", "particles", "nps")                    # particlefluidsurface::3.0 surfmethod
_SURF_MODEL = ("balanced", "smooth", "liquid", "granular", "custom")    # ...model
_SURF_CONVERSION = ("particles", "particlesurf", "surf", "vdb", "poly", "polysoup")  # ...conversion (output type)


@endpoint("fluid_surface")
def fluid_surface(params):
    """Mesh FLIP particles into a fluid surface (Particle Fluid Surface 3.0 SOP). `input` = the
    particle SOP.

    Method/model: method (particlefluid|particles|nps -> `surfmethod`), model (balanced|smooth|
    liquid|granular|custom), conversion (particles|particlesurf|surf|vdb|poly|polysoup = output type).
    Surfacing: particlesep, voxelsize, influence (-> influenceradius), surfacedistance, isovalue,
    adaptivity, minvoxelradius, limitrefinement (TOGGLE -> limititerations; caps refinement iters
    on/off), resampling (-> resamplingiterations), droplet (-> preservebubbles). Filtering: dilate (enables
    dodilate + dilateoffset), erode (enables doerode + erodeoffset), smooth (enables dosmooth +
    smoothiterations). Collision clip: docollisions + collisionoffset (clip the mesh to a collider).
    Set model first so the preset applies, then explicit parms win. NON-BREAKING: the original
    particlesep/voxelsize/influence/droplet params and the {node, prims} return keys still work.
    Cooks the mesh once (a single conversion, never a sim)."""
    n = child_after(params["input"], "particlefluidsurface::3.0", params.get("name"))
    applied = {}
    # model preset first (drives voxelsize/influence defaults), then explicit parms override.
    if "model" in params:
        applied["model"] = _menu_set(n, "model", str(params["model"]), _SURF_MODEL)
    if "method" in params:
        applied["method"] = _menu_set(n, "surfmethod", str(params["method"]), _SURF_METHOD)
    # output conversion: what the surfacer emits (poly mesh vs a VDB SDF vs raw particles).
    if "conversion" in params:
        applied["conversion"] = _menu_set(n, "conversion", str(params["conversion"]), _SURF_CONVERSION)
    if "particlesep" in params:
        applied["particlesep"] = _try_set(n, "particlesep", clamp(float(params["particlesep"]), 1e-3, 1e4))
    if "voxelsize" in params:
        applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "influence" in params:
        applied["influence"] = _try_set(n, "influenceradius", clamp(float(params["influence"]), 1e-3, 1e4))
    if "surfacedistance" in params:
        applied["surfacedistance"] = _try_set(n, "surfacedistance", clamp(float(params["surfacedistance"]), 0.0, 1e4))
    if "isovalue" in params:
        applied["isovalue"] = _try_set(n, "isovalue", clamp(float(params["isovalue"]), -1e4, 1e4))
    if "adaptivity" in params:
        applied["adaptivity"] = _try_set(n, "adaptivity", clamp(float(params["adaptivity"]), 0.0, 1e4))
    if "minvoxelradius" in params:
        applied["minvoxelradius"] = _try_set(n, "minvoxelradius", clamp(float(params["minvoxelradius"]), 0.0, 1e4))
    # `limititerations` is a live TOGGLE on particlefluidsurface::3.0 (cap refinement iterations on/off),
    # NOT an int count — the old int write silently coerced to a bool. Set it honestly as a toggle.
    if "limitrefinement" in params:
        applied["limitrefinement"] = _try_set(n, "limititerations", bool(params["limitrefinement"]))
    if "resampling" in params:
        applied["resampling"] = _try_set(n, "resamplingiterations",
                                         int(clamp(int(params["resampling"]), 0, 1000)))
    if "droplet" in params:
        applied["droplet"] = _try_set(n, "preservebubbles", bool(params["droplet"]))
    # filtering: each enables its toggle then sets the offset/iteration magnitude. On this node
    # doerode/erodeoffset default to channel expressions ch("dodilate")/ch("dilateoffset") (erode is
    # linked to dilate), so a plain .set() on erode would push its value back into dilate. Break the
    # link first (_set_indep drops the expression) so dilate and erode are set independently.
    if "dilate" in params:
        _set_indep(n, "dodilate", 1)
        applied["dilate"] = _set_indep(n, "dilateoffset", clamp(float(params["dilate"]), 0.0, 1e4))
    if "erode" in params:
        _set_indep(n, "doerode", 1)
        applied["erode"] = _set_indep(n, "erodeoffset", clamp(float(params["erode"]), 0.0, 1e4))
    if "smooth" in params:
        _set_indep(n, "dosmooth", 1)
        applied["smooth"] = _set_indep(n, "smoothiterations", int(clamp(int(params["smooth"]), 0, 1000)))
    # collision clip (clip the mesh to a collider fed on the collision input)
    if "docollisions" in params:
        applied["docollisions"] = _try_set(n, "docollisions", bool(params["docollisions"]))
    if "collisionoffset" in params:
        _try_set(n, "docollisions", 1)
        applied["collisionoffset"] = _try_set(n, "collisionoffset",
                                              clamp(float(params["collisionoffset"]), -1e4, 1e4))
    g = n.geometry()  # single mesh cook (never a sim); tolerate an empty/uncooked output
    prims = len(g.prims()) if g is not None else 0
    return {"node": n.path(), "prims": prims, "applied": applied}


_FC_FILEMETHOD = ("constructed", "explicit")   # filecache::2.0 filemethod
_FC_TRANGE = ("off", "normal")                  # filecache::2.0 trange (Single Frame | Frame Range)


@endpoint("flip_cache")
def flip_cache(params):
    """BUILD (never write) a File Cache 2.0 SOP after a sim to cache it to disk. `input` = the SOP to
    cache (e.g. a flipsolver). The write path is CONFINED to the working directory (FsPath write:true,
    same contract as flipbook/export_*): `file` = the explicit output path (filemethod=explicit).

    HEAVY-OP GUARDRAIL: this ONLY builds and configures the filecache node -- it NEVER presses Save to
    Disk / executes the cook. Writing a multi-frame cache on the executor main thread would block the
    session, so the caller/operator triggers the write (the node's 'Save to Disk' button or a ROP). The
    returned `write_path` is where frames WILL land once the human fires it.

    trange (single|range -> `trange` off|normal), frames [start, end], substeps, loadfromdisk. The
    filecache's own 'execute' button is left untouched. Returns node + write_path + trange + frames."""
    out_path = confined_path(params["file"])
    n = child_after(params["input"], "filecache::2.0", params.get("name"))
    applied = {}
    # explicit, confined write target (never the node's default unconfined basedir)
    _menu_set(n, "filemethod", "explicit", _FC_FILEMETHOD)
    applied["file"] = _try_set(n, "file", out_path)
    _try_set(n, "mkpath", True)                     # create dirs at write-time (still not now)
    if "basename" in params:
        _try_set(n, "basename", str(params["basename"]))
    # time range
    trange_tok = None
    if "trange" in params:
        trange_tok = "normal" if str(params["trange"]) in ("range", "normal") else "off"
    frames = params.get("frames")
    if frames and len(frames) >= 2:
        trange_tok = "normal"
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        ft = n.parmTuple("f")
        if ft is not None and len(ft) >= 2:
            # f1/f2 default to $FSTART/$FEND expressions which ignore a plain .set();
            # drop the expression on each component, then set the literal frame.
            for idx, val in ((0, float(f1)), (1, float(f2))):
                try:
                    ft[idx].deleteAllKeyframes()
                except Exception:
                    pass
                try:
                    ft[idx].set(val)
                except Exception:
                    pass
            applied["frames"] = [f1, f2]
    if trange_tok is not None:
        applied["trange"] = _menu_set(n, "trange", trange_tok, _FC_TRANGE)
    if "substeps" in params:
        applied["substeps"] = _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "loadfromdisk" in params:
        applied["loadfromdisk"] = _try_set(n, "loadfromdisk", bool(params["loadfromdisk"]))
    # NO n.render()/execute — the write is the caller's job (heavy-op guardrail).
    return {"node": n.path(), "filecache": n.path(), "write_path": out_path,
            "trange": (n.parm("trange").evalAsString() if n.parm("trange") else None),
            "frames": applied.get("frames"), "written": False, "applied": applied,
            "note": "filecache BUILT + configured; press Save to Disk / trigger the write yourself"}


@endpoint("sim_ripple")
def sim_ripple(params):
    """Cheap surface waves via the Ripple Solver SOP on a grid (rest geometry -> input 0). The ripple
    deform solver actually ripples the DISPLACED geometry on input 1 and reacts to colliders on input 2;
    this builds the minimal rest-only scaffold, so wire a displaced/deformed copy or a collider yourself
    to drive waves. BUILT, not auto-simulated.

    BUG FIX (probe-proven): the old handler set `speed`/`damping`, NEITHER of which exists on ripplesolver
    (silent no-ops). The real parms are wavespeed and conservation. `speed` -> wavespeed; `damping` ->
    conservation as (1 - damping) (higher damping = less energy conserved = waves die faster). Also
    restspring (return-to-rest stiffness), cfl (advective stability), substeps (min==max fixed count),
    startframe."""
    name = params["name"]
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    grid = _src_node(g, params.get("source_geo"), "grid",
                     lambda n: n.parmTuple("size").set((10.0, 10.0)) if n.parmTuple("size") else None)
    rip = g.createNode("ripplesolver")
    rip.setFirstInput(grid)
    applied = {}
    if "speed" in params:
        applied["speed"] = _try_set(rip, "wavespeed", clamp(float(params["speed"]), 0.0, 1e4))
    if "damping" in params:
        d = clamp(float(params["damping"]), 0.0, 1.0)
        applied["damping"] = _try_set(rip, "conservation", clamp(1.0 - d, 0.0, 1.0))
    if "restspring" in params:
        applied["restspring"] = _try_set(rip, "restspring", clamp(float(params["restspring"]), 0.0, 1e4))
    if "cfl" in params:
        applied["cfl"] = _try_set(rip, "cfl", clamp(float(params["cfl"]), 0.0, 1.0))
    if "substeps" in params:
        s = int(clamp(int(params["substeps"]), 1, 100))
        _try_set(rip, "minsubstep", s)
        applied["substeps"] = _try_set(rip, "maxsubstep", s)
    if "startframe" in params:
        applied["startframe"] = _try_set(rip, "startframe", int(params["startframe"]))
    rip.setDisplayFlag(display)
    rip.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "solver": rip.path(), "applied": applied}


def _config_popgrains(grains, params, applied):
    """Set the real, probe-confirmed popgrains knobs (H21.0.671). NEVER sets `stiffness` (no such parm).
    do*/toggle knobs are booled; float knobs clamped; domassshock is an off|on|local menu."""
    if "particlesep" in params:
        applied["particlesep"] = _try_set(grains, "particlesep", clamp(float(params["particlesep"]), 1e-6, 1e9))
    if "iterations" in params:
        applied["iterations"] = _try_set(grains, "iterations", int(clamp(int(params["iterations"]), 1, 10000)))
    for k in ("collisionfriction", "particlefriction", "static_threshold", "kinetic_scale",
              "repulsionweight", "repulsionstiffness", "massshockpower", "attractionweight",
              "attractionstiffness", "constraintweight", "constraintstiffness", "constraintbreakthresh",
              "targetweight", "targetstiffness", "maxspeed", "maxaccel"):
        if k in params:
            applied[k] = _try_set(grains, k, clamp(float(params[k]), 0.0, 1e12))
    for k in ("jacobifriction", "enablerigids", "constraintbreak", "dospeedlimit", "domaxaccel", "opencl"):
        if k in params:
            applied[k] = _try_set(grains, k, bool(params[k]))
    if "massshock" in params:
        applied["massshock"] = _menu_set(grains, "domassshock", str(params["massshock"]), _POPGRAINS_MASSSHOCK)
    if "maxneighbors" in params:
        applied["maxneighbors"] = _try_set(grains, "maxneighbors", int(clamp(int(params["maxneighbors"]), 1, 100000)))


@endpoint("sim_grains")
def sim_grains(params):
    """Granular PBD (sand/snow/wet-sand/debris) network: a SOP `dopnet` (input0 = emit geo) wrapping
    popobject -> popsolver::2.0, a popsource emitting the input0 geometry, and a `popgrains` PBD solver
    ATTACHED onto the popsolver via its 'Solvers to be attached' input (popsolver -> popgrains input0;
    popgrains carries the display flag). A default downward-gravity popforce lets grains pile. BUILT
    only — the caller scrubs the timeline.

    BUG FIX (probe-proven): the old handler set `stiffness` on popgrains, which HAS NO SUCH PARM — a
    silent no-op. It is dropped; the real probe-confirmed grain knobs are driven instead.

    Setup: name (fresh /obj geo), source_geo (emit geo path; else a default box), source_sop (explicit
    SOP the popsource reads), constantrate (birth rate; default 0 = seed the input geo once), impulsecount
    (birth burst), life, gravity (magnitude of the default downward popforce; 0 = none), display.
    Grain knobs (popgrains): particlesep, iterations, collisionfriction, particlefriction, jacobifriction
    (toggle), static_threshold, kinetic_scale, repulsionweight, repulsionstiffness,
    massshock(off|on|local)+massshockpower, attractionweight/attractionstiffness,
    constraintweight/constraintstiffness, constraintbreak(toggle)+constraintbreakthresh, enablerigids
    (toggle), targetweight/targetstiffness, maxneighbors, dospeedlimit(toggle)+maxspeed,
    domaxaccel(toggle)+maxaccel, opencl(toggle). Returns the dopnet + popobject/popsource/popsolver/
    popgrains paths + applied."""
    name = params["name"]
    frames = int(clamp(int(params.get("frames", 120)), 1, 10000))
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    src_geo = _src_node(g, params.get("source_geo"), "box",
                        lambda n: n.parmTuple("size").set((5.0, 5.0, 5.0)))
    dn = g.createNode("dopnet", "grains")
    dn.setFirstInput(src_geo)
    applied = {}
    po = dn.createNode("popobject")

    # popsource emits the dopnet's input0 emit geometry (usecontextgeo='first'), or an explicit SOP.
    src = dn.createNode("popsource")
    _config_popsource(src, {"usecontextgeo": params.get("usecontextgeo", "first"),
                            **({"source_sop": params["source_sop"]} if params.get("source_sop") else {}),
                            **({"constantrate": params["constantrate"]} if "constantrate" in params else {}),
                            **({"impulsecount": params["impulsecount"]} if "impulsecount" in params else {}),
                            **({"life": params["life"]} if "life" in params else {})}, applied)

    solv = dn.createNode("popsolver")
    solv.setInput(0, po, 0)               # Object
    solv.setInput(2, src, 0)              # Sources (post-solve)

    # popgrains ATTACHES onto the solver via its 'Solvers to be attached' input (NOT a stream): the
    # popsolver plugs into popgrains input 0, and popgrains becomes the terminal display node.
    grains = dn.createNode("popgrains")
    grains.setInput(0, solv, 0)
    _config_popgrains(grains, params, applied)

    # default gravity so grains pile (a downward popforce chained to Pre-Solve; gravity=0 suppresses it)
    gmag = float(params.get("gravity", 9.8))
    grav = None
    if gmag != 0.0:
        grav = dn.createNode("popforce", "gravity")
        grav.parmTuple("force").set((0.0, -abs(gmag), 0.0))
        _chain_presolve(solv, grav)
        applied["gravity"] = gmag

    grains.setDisplayFlag(True)
    try:
        dn.layoutChildren()
    except Exception:
        pass
    dn.setDisplayFlag(display)
    dn.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "dopnet": dn.path(), "popobject": po.path(), "popsource": src.path(),
            "popsolver": solv.path(), "popgrains": grains.path(),
            "gravity": grav.path() if grav else None, "frames": frames, "applied": applied}


@endpoint("sim_viscosity")
def sim_viscosity(params):
    """Viscous FLIP scaffold (slushy / meltwater / honey / lava): flipcontainer + flipsolver with
    viscosity force-enabled. `viscosity` = the magnitude (container default_viscosity); `adaptive`
    toggles the solver's adaptive-viscosity solve. Extra container knobs: particlesep (the RAM driver —
    halving it ~8x the particle count), gravity, density, size [x,y,z], center [x,y,z], and solver
    substeps. BUILT, not auto-simulated. For the full FLIP knob set use sim_flip with viscosity set."""
    name = params["name"]
    frames = int(clamp(int(params.get("frames", 120)), 1, 10000))
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    src = _src_node(g, params.get("source_geo"), "box",
                    lambda n: (n.parmTuple("size").set((6.0, 6.0, 6.0)),
                               n.parmTuple("t").set((0.0, 8.0, 0.0)) if n.parmTuple("t") else None))
    cont = g.createNode("flipcontainer")
    fsolve = g.createNode("flipsolver")
    # flipsolver SOP inputs = (Sources=0, Container=1, Collisions=2, Boundary Flow=3);
    # flipcontainer outputs = (Sources=0, Container=1, Collisions=2). Wire label-correctly
    # (was: container->input0, source->input1 — both wrong, and viscosity was set on the
    # solver which has no such parm, so it silently no-oped).
    fsolve.setInput(1, cont, 1)   # Container -> Container
    try:
        fsolve.setInput(0, src)   # source geo -> Sources
    except Exception:
        pass
    # Viscosity lives on the CONTAINER: `viscosity` is the enable toggle, `default_viscosity`
    # the magnitude. Adaptive viscosity is the solver's `useadaptiveviscosity` toggle.
    _try_set(cont, "viscosity", 1)
    applied = {}
    if "viscosity" in params:
        applied["viscosity"] = _try_set(cont, "default_viscosity", clamp(float(params["viscosity"]), 0.0, 1e6))
    if "adaptive" in params:
        applied["adaptive"] = _try_set(fsolve, "useadaptiveviscosity", bool(params["adaptive"]))
    # a modest slice of the container/solver knobs so the scaffold is tunable without sim_flip.
    if "particlesep" in params:
        applied["particlesep"] = _try_set(cont, "particlesep", clamp(float(params["particlesep"]), 1e-3, 1e4))
    if "gravity" in params:
        applied["gravity"] = _try_set(cont, "gravity", clamp(float(params["gravity"]), 0.0, 1e6))
    if "density" in params:
        applied["density"] = _try_set(cont, "density", clamp(float(params["density"]), 1e-3, 1e9))
    if "size" in params:
        applied["size"] = _set_vec(cont, "size", params["size"])
    if "center" in params:
        applied["center"] = _set_vec(cont, "t", params["center"])
    if "substeps" in params:
        applied["substeps"] = _try_set(fsolve, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    fsolve.setDisplayFlag(display)
    fsolve.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "container": cont.path(), "solver": fsolve.path(),
            "frames": frames, "applied": applied}


@endpoint("solver")
def solver(params):
    """Generic SOP feedback / time-loop solver -- the general-purpose ITERATIVE primitive (accumulative
    erosion, growth, cellular automata, any per-frame feedback), distinct from the DOP sim_* family.
    Wires a `solver` SOP after `input`; build the per-frame network inside its sub-network (the
    Prev_Frame node feeds the previous result back, Input_1 holds the original geometry).

    start_frame = the loop start (geometry is empty before it); substeps = how many sub-iterations to
    break each frame into (finer feedback, higher cost); cache toggles the in-memory sim cache (needed
    for scrubbing); cache_to_disk spills old cache entries to disk instead of discarding them when the
    memory cap is hit (full history, slower); cache_memory = the in-memory cache cap in MB. BUILT."""
    n = child_after(params["input"], "solver", params.get("name"))
    applied = {}
    if "start_frame" in params:
        applied["start_frame"] = _try_set(n, "startframe", int(clamp(int(params["start_frame"]), -100000, 100000)))
    if "substeps" in params:
        applied["substeps"] = _try_set(n, "substep", int(clamp(int(params["substeps"]), 1, 100)))
    if "cache" in params:
        applied["cache"] = _try_set(n, "cacheenabled", bool(params["cache"]))
    if "cache_to_disk" in params:
        applied["cache_to_disk"] = _try_set(n, "cachetodisk", bool(params["cache_to_disk"]))
    if "cache_memory" in params:
        applied["cache_memory"] = _try_set(n, "cachemaxsize", int(clamp(int(params["cache_memory"]), 1, 10000000)))
    n.geometry()
    return {"node": n.path(), "loop_subnet": n.path(), "applied": applied,
            "note": "build the per-frame network inside this solver's sub-network (Prev_Frame feeds back)"}


# ── Vellum (XPBD cloth/hair/softbody/grain): SOP vellumconstraints -> vellumsolver ──
# Live-probed on H21.0.671 (menu order/spelling matter). vellumconstraints & vellumsolver both carry
# 3 inputs/outputs, labelled ('Vellum Geometry'=0, 'Constraint Geometry'=1, 'Collision Geometry'=2):
# THE COLLIDER WIRES INTO SOLVER INPUT 2 (probe-confirmed — resolves the spec's input-order flag).
# The material node (vellumconstraints) `constrainttype` menu is INDEX-based (set(3)->'cloth'), so
# _menu_set works. But the *stiffnessexp menus are VALUE-TOKEN menus (set('6')->value 6, NOT an
# index — set-by-index would store a bogus raw int); they MUST be set via _set_exp below.
_VC_TYPES = ("none", "distance", "bend", "cloth", "hair", "string", "pin", "attach", "stitch",
             "pressure", "tetvolume", "weld", "glue", "struts", "tetfiber", "tristretch",
             "tetstretch", "shapematch", "surfacestruts")   # constrainttype (19, default 1=distance)
_VELLUM = {"cloth": "cloth", "hair": "hair", "softbody": "tetvolume", "pressure": "pressure",
           "balloon": "pressure", "string": "string", "shapematch": "shapematch",
           "tristretch": "tristretch", "struts": "struts"}  # 'grain' -> vellumconstraints_grain node
_VC_DOMASS = ("off", "on", "calcuniform", "calcvarying")     # vellumconstraints.domass/dothickness
_VC_BENDTYPE = ("angle", "distance")                          # vellumconstraints.bendtype
_VC_STRETCHTYPE = ("distance", "tristretch")                  # vellumconstraints.stretchtype
_VC_TRIANGULATION = ("none", "regular", "alternating")        # vellumconstraints.triangulation
_VS_SOLVERMODE = ("full", "minimal")                          # vellumsolver.solvermode
_VS_SIMTYPE = ("quasistatic", "dynamic")                      # vellumsolver.simulationtype (default 1)
_VS_INTEGRATION = ("firstorder", "secondorder")              # vellumsolver.integration (default 1)
_VS_WINDSHADOW = ("none", "ray")                              # vellumsolver.windshadow_type
_VS_SLIDINGMETHOD = ("closest", "traverse", "traversetris")  # vellumsolver.slidingmethod
_GRAIN_DOMASS = ("on", "calcuniform")                         # vellumconstraints_grain.domass (2 tokens!)


def _set_exp(node, parm, token):
    """Set a *stiffnessexp VALUE-TOKEN menu by its integer token (10..-10), clamped. These menus
    store the exponent VALUE, not the list index — a plain _menu_set (index) would write a bogus int
    (probe-verified: set('6')->6 good; set(index 13 of '-3')->13 bad)."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        iv = int(clamp(int(round(float(token))), -10, 10))
        p.set(str(iv))
        return True
    except Exception:
        return False


def _apply_vellum_constraints(con, params, applied):
    """Deep vellumconstraints material param sets (all probe-verified on H21.0.671). Plasticity /
    compress magnitudes flip their enabling toggle so the value lands. exp menus via _set_exp."""
    if "domass" in params:
        applied["domass"] = _menu_set(con, "domass", str(params["domass"]), _VC_DOMASS)
    if "mass" in params:
        applied["mass"] = _try_set(con, "mass", clamp(float(params["mass"]), 0.0, 1e6))
    if "density" in params:
        applied["density"] = _try_set(con, "density", clamp(float(params["density"]), 1e-5, 1e9))
    if "dothickness" in params:
        applied["dothickness"] = _menu_set(con, "dothickness", str(params["dothickness"]), _VC_DOMASS)
    if "thickness" in params:
        applied["thickness"] = _try_set(con, "thickness", clamp(float(params["thickness"]), 0.0, 1e4))
    if "thicknessscale" in params:
        applied["thicknessscale"] = _try_set(con, "thicknessscale", clamp(float(params["thicknessscale"]), 0.0, 1e4))
    if "triangulation" in params:
        applied["triangulation"] = _menu_set(con, "triangulation", str(params["triangulation"]), _VC_TRIANGULATION)
    if "stretchtype" in params:
        applied["stretchtype"] = _menu_set(con, "stretchtype", str(params["stretchtype"]), _VC_STRETCHTYPE)
    if "preservevol" in params:
        applied["preservevol"] = _try_set(con, "preservevol", bool(params["preservevol"]))
    # -- stretch --
    if "stretchstiffness" in params:
        applied["stretchstiffness"] = _try_set(con, "stretchstiffness", clamp(float(params["stretchstiffness"]), 0.0, 1e4))
    if "stretchstiffnessexp" in params:
        applied["stretchstiffnessexp"] = _set_exp(con, "stretchstiffnessexp", params["stretchstiffnessexp"])
    if "stretchdampingratio" in params:
        applied["stretchdampingratio"] = _try_set(con, "stretchdampingratio", clamp(float(params["stretchdampingratio"]), 0.0, 1.0))
    # -- compress (softbody/thick cloth) --
    if "compressstiffness" in params:
        _try_set(con, "docompress", 1)
        applied["compressstiffness"] = _try_set(con, "compressstiffness", clamp(float(params["compressstiffness"]), 0.0, 1e4))
    if "compressstiffnessexp" in params:
        _try_set(con, "docompress", 1)
        applied["compressstiffnessexp"] = _set_exp(con, "compressstiffnessexp", params["compressstiffnessexp"])
    # -- bend --
    if "bendtype" in params:
        applied["bendtype"] = _menu_set(con, "bendtype", str(params["bendtype"]), _VC_BENDTYPE)
    if "bendstiffness" in params:
        applied["bendstiffness"] = _try_set(con, "bendstiffness", clamp(float(params["bendstiffness"]), 0.0, 1e4))
    if "bendstiffnessexp" in params:
        applied["bendstiffnessexp"] = _set_exp(con, "bendstiffnessexp", params["bendstiffnessexp"])
    if "benddampingratio" in params:
        applied["benddampingratio"] = _try_set(con, "benddampingratio", clamp(float(params["benddampingratio"]), 0.0, 1.0))
    # -- plasticity (permanent deformation / crumpling) --
    if "stretchplasticity" in params:
        applied["stretchplasticity"] = _try_set(con, "stretchplasticity", bool(params["stretchplasticity"]))
    if "stretchplasticthreshold" in params:
        _try_set(con, "stretchplasticity", 1)
        applied["stretchplasticthreshold"] = _try_set(con, "stretchplasticthreshold", clamp(float(params["stretchplasticthreshold"]), 0.0, 1e4))
    if "stretchplasticrate" in params:
        _try_set(con, "stretchplasticity", 1)
        applied["stretchplasticrate"] = _try_set(con, "stretchplasticrate", clamp(float(params["stretchplasticrate"]), 0.0, 1e4))
    if "stretchplastichardening" in params:
        applied["stretchplastichardening"] = _try_set(con, "stretchplastichardening", clamp(float(params["stretchplastichardening"]), 0.0, 1e4))
    if "bendplasticity" in params:
        applied["bendplasticity"] = _try_set(con, "bendplasticity", bool(params["bendplasticity"]))
    if "bendplasticthreshold" in params:
        _try_set(con, "bendplasticity", 1)
        applied["bendplasticthreshold"] = _try_set(con, "bendplasticthreshold", clamp(float(params["bendplasticthreshold"]), 0.0, 1e4))
    if "bendplasticrate" in params:
        _try_set(con, "bendplasticity", 1)
        applied["bendplasticrate"] = _try_set(con, "bendplasticrate", clamp(float(params["bendplasticrate"]), 0.0, 1e4))
    if "bendplastichardening" in params:
        applied["bendplastichardening"] = _try_set(con, "bendplastichardening", clamp(float(params["bendplastichardening"]), 0.0, 1e4))
    return applied


def _apply_vellum_grain(con, params, applied):
    """vellumconstraints_grain preset params (probe-verified; domass menu differs: only on|calcuniform,
    friction is dofriction+float not a toggle)."""
    if "grainsize" in params:
        applied["grainsize"] = _try_set(con, "grainsize", clamp(float(params["grainsize"]), 1e-4, 1e4))
    if "packingdensity" in params:
        applied["packingdensity"] = _try_set(con, "packingdensity", clamp(float(params["packingdensity"]), 1.0, 2.0))
    if "density" in params:
        applied["density"] = _try_set(con, "density", clamp(float(params["density"]), 1e-3, 1e9))
    if "mass" in params:
        _menu_set(con, "domass", "on", _GRAIN_DOMASS)
        applied["mass"] = _try_set(con, "mass", clamp(float(params["mass"]), 0.0, 1e6))
    if "grain_friction" in params:
        _try_set(con, "dofriction", 1)
        applied["grain_friction"] = _try_set(con, "friction", clamp(float(params["grain_friction"]), 0.0, 1e4))
    if "grain_dynamicfriction" in params:
        _try_set(con, "dodynamicfriction", 1)
        applied["grain_dynamicfriction"] = _try_set(con, "dynamicfriction", clamp(float(params["grain_dynamicfriction"]), 0.0, 1e4))
    return applied


def _apply_vellum_solver(solv, params, applied):
    """Deep vellumsolver param sets (all probe-verified on H21.0.671). Wind/ground magnitudes flip
    their enabling toggle. Menus are INDEX-based (unlike the constraint exp menus)."""
    if "startframe" in params:
        applied["startframe"] = _try_set(solv, "startframe", int(clamp(int(params["startframe"]), -100000, 100000)))
    if "substeps" in params:
        applied["substeps"] = _try_set(solv, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "timescale" in params:
        applied["timescale"] = _try_set(solv, "timescale", clamp(float(params["timescale"]), 0.0, 100.0))
    if "niter" in params:   # Constraint Iterations
        applied["niter"] = _try_set(solv, "niter", int(clamp(int(params["niter"]), 0, 100000)))
    if "smoothiter" in params:
        applied["smoothiter"] = _try_set(solv, "smoothiter", int(clamp(int(params["smoothiter"]), 0, 10000)))
    if "solvermode" in params:
        applied["solvermode"] = _menu_set(solv, "solvermode", str(params["solvermode"]), _VS_SOLVERMODE)
    if "simulationtype" in params:
        applied["simulationtype"] = _menu_set(solv, "simulationtype", str(params["simulationtype"]), _VS_SIMTYPE)
    if "quasistaticframes" in params:
        applied["quasistaticframes"] = _try_set(solv, "quasistaticframes", int(clamp(int(params["quasistaticframes"]), 0, 100000)))
    if "integration" in params:
        applied["integration"] = _menu_set(solv, "integration", str(params["integration"]), _VS_INTEGRATION)
    if "gravity" in params:
        applied["gravity"] = _set_vec(solv, "gravity", params["gravity"])
    if "solver_thickness" in params:   # solver collision thickness (distinct from constraint thickness)
        applied["solver_thickness"] = _try_set(solv, "thickness", clamp(float(params["solver_thickness"]), 0.0, 1e4))
    # -- collisions --
    if "enablecollisions" in params:
        applied["enablecollisions"] = _try_set(solv, "enablecollisions", bool(params["enablecollisions"]))
    if "doselfcollisions" in params:
        applied["doselfcollisions"] = _try_set(solv, "doselfcollisions", bool(params["doselfcollisions"]))
    if "useground" in params:
        applied["useground"] = _try_set(solv, "useground", bool(params["useground"]))
    if "groundpos" in params:
        _try_set(solv, "useground", 1)
        applied["groundpos"] = _set_vec(solv, "groundpos", params["groundpos"])
    if "collisionsiter" in params:
        applied["collisionsiter"] = _try_set(solv, "collisionsiter", int(clamp(int(params["collisionsiter"]), 0, 10000)))
    if "postcollisioniter" in params:
        applied["postcollisioniter"] = _try_set(solv, "postcollisioniter", int(clamp(int(params["postcollisioniter"]), 0, 10000)))
    if "layershock" in params:
        applied["layershock"] = _try_set(solv, "layershock", clamp(float(params["layershock"]), 0.0, 1e4))
    if "friction" in params:
        applied["friction"] = _try_set(solv, "friction", bool(params["friction"]))
    if "selffriction" in params:
        applied["selffriction"] = _try_set(solv, "selffriction", bool(params["selffriction"]))
    if "static_threshold" in params:
        applied["static_threshold"] = _try_set(solv, "static_threshold", clamp(float(params["static_threshold"]), 0.0, 1e4))
    if "dynamic_scale" in params:
        applied["dynamic_scale"] = _try_set(solv, "dynamic_scale", clamp(float(params["dynamic_scale"]), 0.0, 1e4))
    if "static_sdfscale" in params:
        applied["static_sdfscale"] = _try_set(solv, "static_sdfscale", clamp(float(params["static_sdfscale"]), 0.0, 1e4))
    if "dynamic_sdfscale" in params:
        applied["dynamic_sdfscale"] = _try_set(solv, "dynamic_sdfscale", clamp(float(params["dynamic_sdfscale"]), 0.0, 1e4))
    if "veldamping" in params:
        applied["veldamping"] = _try_set(solv, "veldamping", clamp(float(params["veldamping"]), 0.0, 1.0))
    # -- wind --
    if "dowind" in params:
        applied["dowind"] = _try_set(solv, "dowind", bool(params["dowind"]))
    if "wind" in params:
        _try_set(solv, "dowind", 1)
        applied["wind"] = _set_vec(solv, "wind", params["wind"])
    if "windspeed" in params:
        _try_set(solv, "dowind", 1)
        applied["windspeed"] = _try_set(solv, "windspeed", clamp(float(params["windspeed"]), 0.0, 1e6))
    if "winddrag" in params:
        applied["winddrag"] = _try_set(solv, "winddrag", clamp(float(params["winddrag"]), 0.0, 1e6))
    if "windshadow_type" in params:
        applied["windshadow_type"] = _menu_set(solv, "windshadow_type", str(params["windshadow_type"]), _VS_WINDSHADOW)
    if "slidingmethod" in params:
        applied["slidingmethod"] = _menu_set(solv, "slidingmethod", str(params["slidingmethod"]), _VS_SLIDINGMETHOD)
    return applied


@endpoint("vellum_attach")
def vellum_attach(params):
    """Attach Vellum cloth/geometry to a (moving) RIG — the dedicated Vellum Attach Constraints SOP.
    Wire the vellum geometry on input 0 and the rest/target rig via `rig` (input 1); it pins the
    nearest vellum points to the rig, generating attach constraints to feed a Vellum solver. Distinct
    from vellum_constraint (which layers an attach INTO an existing solver via a path string): this
    authors attach constraints UP FRONT with the rig WIRED in — the standard cloth-to-rig setup (sail
    to track, cape to shoulders, flag to pole). Optional collision input, sliding, rest-length hold,
    and breaking. Feed the result to sim_vellum's constraints. Chains after `input`. BUILT."""
    n = child_after(params["input"], "vellumattachconstraints", params.get("name"))
    rig = resolve_node(params["rig"])
    n.setInput(1, bridge_into(rig, n.parent(), xformtype=1, name_hint="rig"))
    if params.get("collision"):
        col = resolve_node(params["collision"])
        n.setInput(2, bridge_into(col, n.parent(), xformtype=1, name_hint="collision"))
    applied = {}
    if "target_group" in params:
        applied["target_group"] = _try_set(n, "targetgroup", str(params["target_group"]))
    if "sliding" in params:
        applied["sliding"] = _try_set(n, "dosliding", bool(params["sliding"]))
    if "sliding_rate" in params:
        _try_set(n, "dosliding", True)
        applied["sliding_rate"] = _try_set(n, "slidingrate", clamp(float(params["sliding_rate"]), 0.0, 1.0))
    if "keep_rest_length" in params:
        applied["keep_rest_length"] = _try_set(n, "keeprestlength", bool(params["keep_rest_length"]))
    if "stiffness" in params:
        applied["stiffness"] = _try_set(n, "stretchstiffness", clamp(float(params["stiffness"]), 0.0, 1e4))
    if "breaking" in params:
        applied["breaking"] = _try_set(n, "dobreaking", bool(params["breaking"]))
    if "break_threshold" in params:
        _try_set(n, "dobreaking", True)
        applied["break_threshold"] = _try_set(n, "breakthreshold", clamp(float(params["break_threshold"]), 0.0, 1e6))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    n.parent().layoutChildren()
    return {"node": n.path(), "applied": applied, "rig_wired": n.input(1) is not None}


@endpoint("sim_vellum")
def sim_vellum(params):
    """Vellum (XPBD) master builder (SOP): source geo -> Vellum Constraints -> Vellum Solver. The
    material node carries the type + full stiffness/damping/mass/thickness/plasticity; the solver
    enforces it. BUILT, never auto-simulated (scrub the timeline to run it); only the constraints are
    cooked here (heavy-op guardrail).

    vtype -> constrainttype: cloth, hair, softbody(=tetvolume), pressure, balloon(=pressure), string,
    shapematch, tristretch, struts, and grain (routes to the vellumconstraints_grain preset). Any raw
    constrainttype token is also accepted.

    Constraints (probe-real names): domass(off|on|calcuniform|calcvarying), mass, density,
    dothickness(same menu), thickness, thicknessscale, triangulation(none|regular|alternating),
    stretchtype(distance|tristretch), preservevol (softbody). Stretch: stretchstiffness +
    stretchstiffnessexp (VALUE-token menu 10..-10 = the real magnitude), stretchdampingratio. Compress:
    compressstiffness(+exp). Bend: bendtype(angle|distance), bendstiffness(+bendstiffnessexp),
    benddampingratio. Plasticity (permanent crumpling): stretchplasticity + stretchplasticthreshold/
    rate/hardening; bendplasticity + bendplasticthreshold/rate/hardening. Grain: grainsize,
    packingdensity, density, mass, grain_friction, grain_dynamicfriction.

    Solver (probe-real names): startframe, substeps, timescale, niter(=Constraint Iterations),
    smoothiter, solvermode(full|minimal), simulationtype(quasistatic|dynamic), quasistaticframes,
    integration(firstorder|secondorder), gravity[x,y,z], solver_thickness, enablecollisions,
    doselfcollisions, useground(+groundpos[x,y,z]), collisionsiter, postcollisioniter, layershock,
    friction, selffriction, static_threshold, dynamic_scale, static_sdfscale, dynamic_sdfscale,
    veldamping, dowind, wind[x,y,z], windspeed, winddrag, windshadow_type(none|ray), slidingmethod
    (closest|traverse|traversetris). Wire a scene/terrain collider into the solver's Collision
    Geometry input (index 2) with vellum_collision."""
    name = params["name"]
    vtype = str(params.get("vtype", "cloth"))
    display = bool(params.get("display", False))
    # legacy aliases kept working
    p = dict(params)
    if "substeps" not in p:
        p["substeps"] = 5
    if "startframe" not in p:
        p["startframe"] = int(p.get("start_frame", 1))
    g = _fresh_geo(name)
    if vtype in ("softbody", "grain"):
        src = _src_node(g, params.get("source_geo"), "box",
                        lambda n: n.parmTuple("size").set((3.0, 3.0, 3.0)) if n.parmTuple("size") else None)
    else:
        src = _src_node(g, params.get("source_geo"), "grid",
                        lambda n: n.parmTuple("size").set((10.0, 10.0)) if n.parmTuple("size") else None)
    applied = {}
    if vtype == "grain":
        con = g.createNode("vellumconstraints_grain", "constraints")
        con.setFirstInput(src)
        _apply_vellum_grain(con, p, applied)
        ctype = "grain"
    else:
        con = g.createNode("vellumconstraints", "constraints")
        con.setFirstInput(src)
        ctype = _VELLUM.get(vtype, vtype if vtype in _VC_TYPES else "cloth")
        applied["constrainttype"] = _menu_set(con, "constrainttype", ctype, _VC_TYPES)
        _apply_vellum_constraints(con, p, applied)
    solv = g.createNode("vellumsolver", "solver")
    solv.setFirstInput(con)                 # Vellum Geometry(out0) -> Vellum Geometry(in0) [proven]
    # The CONSTRAINT geometry rides on vellumconstraints OUTPUT 1 and the solver requires it on INPUT
    # 1; without this wire the solver errors "Not enough sources specified." and outputs nothing the
    # instant the user scrubs a frame -- i.e. every vellum net (cloth/hair/softbody/pressure/string/
    # grain) was built DOA. Verified: adding it flips error+empty -> clean solve with real motion.
    solv.setInput(1, con, 1)                # Constraints(out1) -> Constraints(in1)
    _apply_vellum_solver(solv, p, applied)
    solv.setDisplayFlag(display)
    solv.setRenderFlag(True)
    g.setDisplayFlag(display)
    con.cook(force=True)                    # cook constraints only — never step the sim
    g.layoutChildren()
    return {"node": g.path(), "constraints": con.path(), "solver": solv.path(),
            "vtype": vtype, "constrainttype": ctype, "applied": applied}


@endpoint("vellum_collision")
def vellum_collision(params):
    """Wire an external/terrain collider into a Vellum solver's Collision Geometry input (index 2 —
    probe-confirmed) and tune the solver's collision response. THE terrain/scene collider bridge:
    DEM heightfield -> convert_heightfield (set convert_heightfield=true, or pass an already-poly geo)
    -> this tool -> cloth/softbody/grain settles on real terrain.

    `solver` = the vellumsolver SOP path (from sim_vellum). `collider` = an /obj geo (or SOP) to
    object_merge as the collider; `convert_heightfield`=true inserts a convertheightfield (heightfield
    -> polys) after the merge. mode: static (default; velapproximation off) | deforming (rely on the
    collider's own point velocity). Solver-side (set on the passed solver): enablecollisions, friction,
    selffriction, static_threshold, dynamic_scale, static_sdfscale, dynamic_sdfscale, collisionsiter,
    postcollisioniter, layershock. One cook of the heightfield conversion only (never the sim)."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "vellumsolver":
        raise ValueError("`solver` must be a vellumsolver SOP (got %s)" % solv.type().name())
    parent = solv.parent()
    mode = str(params.get("mode", "static"))
    om = parent.createNode("object_merge", params.get("name") or "collider")
    _try_set(om, "objpath1", str(params["collider"]))
    coll_out = om
    converted = False
    if params.get("convert_heightfield"):
        conv = parent.createNode("convertheightfield", "collider_polys")
        conv.setFirstInput(om)
        _try_set(conv, "lod", clamp(float(params.get("lod", 1.0)), 0.01, 1.0))
        conv.geometry()                      # single safe cook of the mesh conversion (not a sim)
        coll_out = conv
        converted = True
    solv.setInput(2, coll_out, 0)            # -> Collision Geometry (input index 2)
    applied = {}
    # static terrain -> no collider velocity; deforming -> let the solver read point velocity
    _try_set(solv, "enablecollisions", 1)
    if "enablecollisions" in params:
        applied["enablecollisions"] = _try_set(solv, "enablecollisions", bool(params["enablecollisions"]))
    if "friction" in params:
        applied["friction"] = _try_set(solv, "friction", bool(params["friction"]))
    if "selffriction" in params:
        applied["selffriction"] = _try_set(solv, "selffriction", bool(params["selffriction"]))
    if "static_threshold" in params:
        applied["static_threshold"] = _try_set(solv, "static_threshold", clamp(float(params["static_threshold"]), 0.0, 1e4))
    if "dynamic_scale" in params:
        applied["dynamic_scale"] = _try_set(solv, "dynamic_scale", clamp(float(params["dynamic_scale"]), 0.0, 1e4))
    if "static_sdfscale" in params:
        applied["static_sdfscale"] = _try_set(solv, "static_sdfscale", clamp(float(params["static_sdfscale"]), 0.0, 1e4))
    if "dynamic_sdfscale" in params:
        applied["dynamic_sdfscale"] = _try_set(solv, "dynamic_sdfscale", clamp(float(params["dynamic_sdfscale"]), 0.0, 1e4))
    if "collisionsiter" in params:
        applied["collisionsiter"] = _try_set(solv, "collisionsiter", int(clamp(int(params["collisionsiter"]), 0, 10000)))
    if "postcollisioniter" in params:
        applied["postcollisioniter"] = _try_set(solv, "postcollisioniter", int(clamp(int(params["postcollisioniter"]), 0, 10000)))
    if "layershock" in params:
        applied["layershock"] = _try_set(solv, "layershock", clamp(float(params["layershock"]), 0.0, 1e4))
    try:
        parent.layoutChildren()
    except Exception:
        pass
    return {"collider": coll_out.path(), "object_merge": om.path(), "solver": solv.path(),
            "mode": mode, "converted": converted,
            "collider_wired": solv.input(2) is not None, "applied": applied}


# ── Vellum Phase-2 (layered constraints / forces / drape / emission / post / cache) ──────────────
# Live-probed on H21.0.671 (probe_vellum_p2*.py). Key dataflow finding: vellumconstraints carries the
# constraint PRIMS ONLY on OUTPUT 1 (Constraint Geometry) — out0 is the bare geometry. So a solver (or
# a layered constraints node) must read the constraint geometry on its INPUT 1 for constraints to take
# effect. The append/layering is exactly this: a 2nd vellumconstraints with input0=vellum geo and
# input1=the prior Constraint Geometry (out1) ADDS its constraints to the incoming set. All the
# per-type params below are probe-verified (menus are simple INDEX menus unless noted).
_VC_PINTYPE = ("hard", "stopped", "soft")                         # vellumconstraints.pintype
_VC_PINROTATION = ("none", "same", "soft")                        # vellumconstraints.pinrotation (default 1)
_VC_TARGETGROUPTYPE = ("prims", "points", "edges")                # vellumconstraints.targetgrouptype
_VRB_BLENDMODE = ("blend", "distance")                            # vellumrestblend.blendmode
_VRB_MASKMODE = ("none", "setfromattrib", "scalefromattrib")      # vellumrestblend.maskmode
_VPP_SUBDIVIDE = ("none", "catmull", "loop")                      # vellumpostprocess.subdivide
_VPP_VISMODE = ("none", "stretchstress", "bendstress", "stretchdistance", "stretchratio", "bendangle",
                "stretchplasticflow", "bendplasticflow", "volumestress", "volumedistance", "volumeratio")
_VSRC_EMITTYPE = ("once", "continuous", "persubstep", "points")   # vellumsource.emittype (DOP)
_VSRC_IMPORTXFORM = ("none", "local")                             # vellumsource.importxform
_VFORCE_MAP = {"wind": "windforce", "vortex": "vortexforce", "point": "pointforce",
               "fan": "fan", "uniform": "uniformforce"}           # 'drag' -> on-solver winddrag/veldamping


def _apply_vellum_layer(con, params, applied):
    """Type-specific append-constraint params (pin/attach/glue/weld/struts) on a layered
    vellumconstraints (all probe-verified on H21.0.671). Magnitudes flip the relevant enable toggle."""
    # -- pin --
    if "pintype" in params:
        applied["pintype"] = _menu_set(con, "pintype", str(params["pintype"]), _VC_PINTYPE)
    if "pinrotation" in params:
        applied["pinrotation"] = _menu_set(con, "pinrotation", str(params["pinrotation"]), _VC_PINROTATION)
    if "pingroup" in params:
        applied["pingroup"] = _try_set(con, "pingroup", str(params["pingroup"]))
    if "matchanimation" in params:
        applied["matchanimation"] = _try_set(con, "matchanimation", bool(params["matchanimation"]))
    if "useclosestpt" in params:
        applied["useclosestpt"] = _try_set(con, "useclosestpt", bool(params["useclosestpt"]))
    if "maxdist" in params:
        _try_set(con, "maxdistcheck", 1)
        applied["maxdist"] = _try_set(con, "maxdist", clamp(float(params["maxdist"]), 0.0, 1e9))
    if "dosliding" in params:
        applied["dosliding"] = _try_set(con, "dosliding", bool(params["dosliding"]))
    if "slidingrate" in params:
        _try_set(con, "dosliding", 1)
        applied["slidingrate"] = _try_set(con, "slidingrate", clamp(float(params["slidingrate"]), 0.0, 1e4))
    # -- attach (attach-to-geometry / pin-to-target) --
    if "targetpath" in params:
        applied["targetpath"] = _try_set(con, "targetpath", str(params["targetpath"]))
    if "targetgrouptype" in params:
        applied["targetgrouptype"] = _menu_set(con, "targetgrouptype", str(params["targetgrouptype"]), _VC_TARGETGROUPTYPE)
    if "targetgroup" in params:
        applied["targetgroup"] = _try_set(con, "targetgroup", str(params["targetgroup"]))
    if "attachframe" in params:
        _try_set(con, "doattachframe", 1)
        applied["attachframe"] = _try_set(con, "attachframe", int(clamp(int(params["attachframe"]), -100000, 100000)))
    if "dragnormal" in params:
        applied["dragnormal"] = _try_set(con, "dragnormal", clamp(float(params["dragnormal"]), 0.0, 1e6))
    if "dragtangent" in params:
        applied["dragtangent"] = _try_set(con, "dragtangent", clamp(float(params["dragtangent"]), 0.0, 1e6))
    # -- glue (breakable via detach chance) --
    if "glue_usecluster" in params:
        applied["glue_usecluster"] = _try_set(con, "glue_usecluster", bool(params["glue_usecluster"]))
    if "glue_clusterattrib" in params:
        applied["glue_clusterattrib"] = _try_set(con, "glue_clusterattrib", str(params["glue_clusterattrib"]))
    if "glue_radius" in params:
        applied["glue_radius"] = _try_set(con, "glue_radius", clamp(float(params["glue_radius"]), 0.0, 1e6))
    if "glue_minradius" in params:
        applied["glue_minradius"] = _try_set(con, "glue_minradius", clamp(float(params["glue_minradius"]), 0.0, 1e6))
    if "glue_numpt" in params:
        applied["glue_numpt"] = _try_set(con, "glue_numpt", int(clamp(int(params["glue_numpt"]), 1, 1000000)))
    if "glue_constraintsperpt" in params:
        applied["glue_constraintsperpt"] = _try_set(con, "glue_constraintsperpt", int(clamp(int(params["glue_constraintsperpt"]), 1, 1000000)))
    if "glue_detach_chance" in params:
        applied["glue_detach_chance"] = _try_set(con, "glue_detach_chance", clamp(float(params["glue_detach_chance"]), 0.0, 1.0))
    if "glue_point_chance" in params:
        applied["glue_point_chance"] = _try_set(con, "glue_point_chance", clamp(float(params["glue_point_chance"]), 0.0, 1.0))
    if "glue_seed" in params:
        applied["glue_seed"] = _try_set(con, "glue_seed", clamp(float(params["glue_seed"]), 0.0, 1e9))
    # -- weld --
    if "bendweld" in params:
        applied["bendweld"] = _try_set(con, "bendweld", bool(params["bendweld"]))
    # -- struts / surfacestruts (softbody rigidity) --
    if "strut_maxlen" in params:
        applied["strut_maxlen"] = _try_set(con, "strut_maxlen", clamp(float(params["strut_maxlen"]), 0.0, 1e9))
    if "strut_constraintsperpt" in params:
        applied["strut_constraintsperpt"] = _try_set(con, "strut_constraintsperpt", int(clamp(int(params["strut_constraintsperpt"]), 1, 1000000)))
    if "strut_jitter" in params:
        applied["strut_jitter"] = _try_set(con, "strut_jitter", clamp(float(params["strut_jitter"]), 0.0, 1e4))
    if "strut_testnormals" in params:
        applied["strut_testnormals"] = _try_set(con, "strut_testnormals", bool(params["strut_testnormals"]))
    if "strut_seed" in params:
        applied["strut_seed"] = _try_set(con, "strut_seed", clamp(float(params["strut_seed"]), 0.0, 1e9))
    if "strut_rayoff" in params:
        applied["strut_rayoff"] = _try_set(con, "strut_rayoff", clamp(float(params["strut_rayoff"]), 0.0, 1e4))
    return applied


@endpoint("vellum_constraint")
def vellum_constraint(params):
    """Layer an ADDITIONAL Vellum constraint onto an existing chain (welds/glue/pins/attach/stitch/
    struts) — the second-input append. Given a `solver` (from sim_vellum), inserts a new
    vellumconstraints between the solver's upstream constraints node and the solver, wiring
    input0 = prior Vellum Geometry (out0) and input1 = prior Constraint Geometry (out1 — probe-
    confirmed the constraint prims ride here), so the new constraints ADD to the incoming set. The
    solver is rewired to read the layered geometry (in0) AND constraints (in1).

    `solver` = the vellumsolver SOP path. ctype -> constrainttype: weld, glue, pin, attach, stitch,
    struts, surfacestruts, distance, bend, shapematch. Base stiffness/damping (stretchstiffness/
    stretchstiffnessexp/bendstiffness/... via the same names as sim_vellum) also apply to the layer.
    Type-specific (probe-real names): pin -> pintype(hard|stopped|soft), pinrotation(none|same|soft),
    pingroup, matchanimation, useclosestpt, maxdist(enables maxdistcheck), dosliding(+slidingrate).
    attach -> targetpath, targetgrouptype(prims|points|edges), targetgroup, attachframe(enables
    doattachframe), dragnormal, dragtangent. glue -> glue_usecluster(+glue_clusterattrib), glue_radius/
    glue_minradius, glue_numpt, glue_constraintsperpt, glue_detach_chance/glue_point_chance/glue_seed
    (breakable glue). weld -> bendweld. struts/surfacestruts -> strut_maxlen, strut_constraintsperpt,
    strut_jitter, strut_testnormals, strut_seed, strut_rayoff. (stitch has no extra params — it uses the
    base stretch/bend stiffness.) Cooks the layered constraints only (never the sim)."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "vellumsolver":
        raise ValueError("`solver` must be a vellumsolver SOP (got %s)" % solv.type().name())
    prev = solv.input(0)
    if prev is None:
        raise ValueError("solver input 0 (upstream constraints) is not connected")
    parent = solv.parent()
    ctype = str(params.get("ctype", "pin"))
    con = parent.createNode("vellumconstraints", params.get("name") or ("layer_" + ctype))
    con.setInput(0, prev, 0)                                 # Vellum Geometry passthrough
    try:
        con.setInput(1, prev, 1)                            # existing Constraint Geometry -> APPEND
    except Exception:
        pass
    applied = {}
    applied["constrainttype"] = _menu_set(con, "constrainttype",
                                          ctype if ctype in _VC_TYPES else "pin", _VC_TYPES)
    _apply_vellum_constraints(con, params, applied)          # base stiffness/damping (only if passed)
    _apply_vellum_layer(con, params, applied)                # type-specific append params
    solv.setInput(0, con, 0)                                 # solver reads layered geometry
    try:
        solv.setInput(1, con, 1)                            # ...and the full (appended) constraints
    except Exception:
        pass
    con.cook(force=True)                                     # cook constraints only — never the sim
    try:
        parent.layoutChildren()
    except Exception:
        pass
    con_prims = 0
    try:
        cg = con.geometry(1)
        con_prims = len(cg.prims()) if cg is not None else 0
    except Exception:
        pass
    return {"node": con.path(), "constraints": con.path(), "solver": solv.path(),
            "layered_onto": prev.path(), "ctype": ctype, "constraint_prims": con_prims,
            "applied": applied}


def _apply_vellum_solver_wind(solv, params, applied):
    """On-solver wind / drag / windshadow / damping (the wired, effective force path for a SOP Vellum
    solver — probe-confirmed the solver has NO external-force input, only 3 geometry inputs)."""
    if "dowind" in params:
        applied["dowind"] = _try_set(solv, "dowind", bool(params["dowind"]))
    if "wind" in params:
        _try_set(solv, "dowind", 1)
        applied["wind"] = _set_vec(solv, "wind", params["wind"])
    if "windspeed" in params:
        _try_set(solv, "dowind", 1)
        applied["windspeed"] = _try_set(solv, "windspeed", clamp(float(params["windspeed"]), 0.0, 1e6))
    if "winddrag" in params:
        applied["winddrag"] = _try_set(solv, "winddrag", clamp(float(params["winddrag"]), 0.0, 1e6))
    if "veldamping" in params:
        applied["veldamping"] = _try_set(solv, "veldamping", clamp(float(params["veldamping"]), 0.0, 1.0))
    if "windshadow_type" in params:
        applied["windshadow_type"] = _menu_set(solv, "windshadow_type", str(params["windshadow_type"]), _VS_WINDSHADOW)
    if "windshadow_doexternal" in params:
        applied["windshadow_doexternal"] = _try_set(solv, "windshadow_doexternal", bool(params["windshadow_doexternal"]))
    if "windshadow_doself" in params:
        applied["windshadow_doself"] = _try_set(solv, "windshadow_doself", bool(params["windshadow_doself"]))
    if "windshadow_maxdistance" in params:
        applied["windshadow_maxdistance"] = _try_set(solv, "windshadow_maxdistance", clamp(float(params["windshadow_maxdistance"]), 0.0, 1e9))
    if "windshadow_coneangle" in params:
        applied["windshadow_coneangle"] = _try_set(solv, "windshadow_coneangle", clamp(float(params["windshadow_coneangle"]), 0.0, 180.0))
    if "windshadow_samples" in params:
        applied["windshadow_samples"] = _try_set(solv, "windshadow_samples", int(clamp(int(params["windshadow_samples"]), 1, 100000)))
    return applied


def _build_vellum_force_node(dn, ftype, params, applied):
    """Build a typed force DOP node (reuses the flip_force approach) for manual merge into a DOP
    Vellum force network (the SOP solver has no direct force input)."""
    ntype = _VFORCE_MAP[ftype]
    force = dn.createNode(ntype, params.get("node_name") or ftype)
    strength = float(params["strength"]) if "strength" in params else 1.0
    direction = tuple(float(x) for x in (params.get("direction") or (0.0, 0.0, 1.0)))
    if ntype == "windforce":
        applied["direction"] = _set_vec(force, "vel", direction)
        applied["strength"] = _try_set(force, "scaleforce", clamp(strength, 0.0, 1e9))
        if "turbulence" in params:      # windforce turbulence = fractaldepth + roughness
            _try_set(force, "fractaldepth", int(clamp(int(params.get("fractaldepth", 3)), 0, 10)))
            applied["turbulence"] = _try_set(force, "roughness", clamp(float(params["turbulence"]), 0.0, 1e4))
        if "amplitude" in params:
            applied["amplitude"] = _set_vec(force, "amplitude", params["amplitude"])
    elif ntype == "uniformforce":
        applied["force"] = _set_vec(force, "force", tuple(d * strength for d in direction))
    elif ntype == "pointforce":
        applied["force"] = _set_vec(force, "force", tuple(d * strength for d in direction))
        if "center" in params:
            applied["center"] = _set_vec(force, "t", params["center"])
    elif ntype == "vortexforce":
        applied["falloff"] = _try_set(force, "falloff", clamp(float(params.get("falloff", 1.0)), 0.0, 1e4))
        if "strength" in params:
            applied["strength"] = _try_set(force, "dragconstant", clamp(strength, 0.0, 1e9))
    elif ntype == "fan":
        applied["direction"] = _set_vec(force, "direction", direction)
        applied["strength"] = _try_set(force, "flux", clamp(strength if "strength" in params else 1e6, 0.0, 1e12))
        if "center" in params:
            applied["center"] = _set_vec(force, "t", params["center"])
        if "coneangle" in params:
            _try_set(force, "coneangle", clamp(float(params["coneangle"]), 0.0, 180.0))
    return force


@endpoint("vellum_force")
def vellum_force(params):
    """External forces on a Vellum solve. Two independent responsibilities (pass either or both):

    (1) ON-SOLVER wind/drag/windshadow (the wired, effective path — PROBE CORRECTION: the SOP
    vellumsolver has NO external-force input, only 3 geometry inputs, so wind/drag live on the solver
    itself). Pass `solver` (a vellumsolver path) with: dowind, wind[x,y,z], windspeed, winddrag,
    veldamping, windshadow_type(none|ray), windshadow_doexternal, windshadow_doself,
    windshadow_maxdistance, windshadow_coneangle, windshadow_samples (flags/banners occluding each
    other). ftype=drag maps `strength` -> solver winddrag.

    (2) A standalone typed force DOP node (reuses flip_force's approach) for manual merge into a DOP
    Vellum force network. ftype -> node: wind->windforce(+turbulence/amplitude), vortex->vortexforce,
    point->pointforce, fan->fan, uniform->uniformforce. Common: strength, direction[x,y,z], center
    (point/fan). Built in an existing `dopnet` or a fresh /obj geo `name`; BUILT (not auto-wired)."""
    result = {"applied": {}}
    applied = result["applied"]
    solv = None
    if params.get("solver"):
        solv = resolve_node(str(params["solver"]))
        if solv.type().name() != "vellumsolver":
            raise ValueError("`solver` must be a vellumsolver SOP (got %s)" % solv.type().name())
        _apply_vellum_solver_wind(solv, params, applied)
        result["solver"] = solv.path()
    ftype = params.get("ftype")
    if ftype == "drag":
        if solv is None:
            raise ValueError("ftype=drag sets solver winddrag; pass `solver`")
        if "strength" in params:
            applied["winddrag"] = _try_set(solv, "winddrag", clamp(float(params["strength"]), 0.0, 1e6))
        result["ftype"] = "drag"
    elif ftype:
        if ftype not in _VFORCE_MAP:
            raise ValueError("unknown ftype: %s (want %s or drag)" % (ftype, "/".join(sorted(_VFORCE_MAP))))
        g = None
        if params.get("dopnet"):
            dn = resolve_node(str(params["dopnet"]))
        else:
            if not params.get("name"):
                raise ValueError("vellum_force needs `name` (fresh holder) or `dopnet` to build a force node")
            g = _fresh_geo(params["name"])
            dn = g.createNode("dopnet", "forces")
        force = _build_vellum_force_node(dn, ftype, params, applied)
        try:
            dn.layoutChildren()
        except Exception:
            pass
        result["force"] = force.path()
        result["dopnet"] = dn.path()
        result["ftype"] = ftype
        result["node_type"] = _VFORCE_MAP[ftype]
        if g is not None:
            g.setDisplayFlag(bool(params.get("display", False)))
            g.layoutChildren()
            result["geo"] = g.path()
    if "solver" not in result and "force" not in result:
        raise ValueError("vellum_force: pass `solver` (on-solver wind/drag/windshadow) and/or `ftype`")
    return result


def _apply_vellum_drape(n, params, applied):
    """vellumdrape pre-roll settle params (all probe-verified on H21.0.671)."""
    for key, parm, lo, hi in (("substeps", "substeps", 1, 100), ("niter", "niter", 0, 100000),
                              ("smoothiter", "smoothiter", 0, 10000),
                              ("collision_frames", "collision_frames", 1, 100000),
                              ("collisionsiter", "collisionsiter", 0, 10000),
                              ("postcollisioniter", "postcollisioniter", 0, 10000),
                              ("startframe", "startframe", -100000, 100000)):
        if key in params:
            applied[key] = _try_set(n, parm, int(clamp(int(params[key]), lo, hi)))
    for key, parm, lo, hi in (("timescale", "timescale", 0.0, 100.0), ("layershock", "layershock", 0.0, 1e4),
                              ("static_threshold", "static_threshold", 0.0, 1e4),
                              ("dynamic_scale", "dynamic_scale", 0.0, 1e4),
                              ("veldamping", "veldamping", 0.0, 1.0), ("airdrag", "airdrag", 0.0, 1e6),
                              ("stretchstiffness", "stretchstiffness", 0.0, 1e9)):
        if key in params:
            applied[key] = _try_set(n, parm, clamp(float(params[key]), lo, hi))
    if "enablecollisions" in params:
        applied["enablecollisions"] = _try_set(n, "enablecollisions", bool(params["enablecollisions"]))
    if "doselfcollisions" in params:
        applied["doselfcollisions"] = _try_set(n, "doselfcollisions", bool(params["doselfcollisions"]))
    if "useground" in params:
        applied["useground"] = _try_set(n, "useground", bool(params["useground"]))
    if "groundpos" in params:
        _try_set(n, "useground", 1)
        applied["groundpos"] = _set_vec(n, "groundpos", params["groundpos"])
    if "gravity" in params:
        applied["gravity"] = _set_grav(n, "gravity", params["gravity"], downward=True)
    return applied


def _apply_vellum_restblend(n, params, applied):
    """vellumrestblend params (probe-verified). PROBE CORRECTIONS vs spec: constraint group = `congroup`,
    blend has a `blendmode`(blend|distance), masking = `maskmode`(none|setfromattrib|scalefromattrib) +
    `maskattrib` (not `blendmasking`/`blendmaskattrib`)."""
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    if "congroup" in params:
        applied["congroup"] = _try_set(n, "congroup", str(params["congroup"]))
    if "blendmode" in params:
        applied["blendmode"] = _menu_set(n, "blendmode", str(params["blendmode"]), _VRB_BLENDMODE)
    if "blend" in params:
        applied["blend"] = _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    if "distance" in params:
        applied["distance"] = _try_set(n, "distance", clamp(float(params["distance"]), 0.0, 1e6))
    if "maskmode" in params:
        applied["maskmode"] = _menu_set(n, "maskmode", str(params["maskmode"]), _VRB_MASKMODE)
    if "maskattrib" in params:
        applied["maskattrib"] = _try_set(n, "maskattrib", str(params["maskattrib"]))
    return applied


@endpoint("vellum_drape")
def vellum_drape(params):
    """Rest state / pre-roll settle. Inserts a node between the solver's upstream constraints and the
    solver (rewiring solver in0=geometry, in1=constraints), then leaves it BUILT — never cooked (both
    modes are mini-sims that would settle on the main thread).

    `solver` = the vellumsolver SOP path. mode:
    - drape (default): a `vellumdrape` (a pre-roll vellumsolver) relaxes flat cloth onto a collider
      under gravity before the shot and writes a new rest. `collider` = an /obj geo (or SOP) merged
      onto its Collision Geometry input. Params: substeps, niter, smoothiter, collision_frames
      (collision passes), collisionsiter, postcollisioniter, timescale, layershock, static_threshold,
      dynamic_scale, veldamping, airdrag, stretchstiffness, enablecollisions, doselfcollisions,
      useground(+groundpos), gravity (scalar down or [x,y,z]). (PROBE CORRECTION: vellumdrape has no
      explicit Target Group parm; collision passes = `collision_frames`.)
    - restblend: a `vellumrestblend` blends the constraint rest toward external geometry (animated
      stiffening / target morph). `rest_geo` = the external target geo merged onto input 3 (Rest
      Geometry). Params: group, congroup, blendmode(blend|distance), blend(0..1), distance,
      maskmode(none|setfromattrib|scalefromattrib), maskattrib."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "vellumsolver":
        raise ValueError("`solver` must be a vellumsolver SOP (got %s)" % solv.type().name())
    prev = solv.input(0)
    if prev is None:
        raise ValueError("solver input 0 (upstream constraints) is not connected")
    parent = solv.parent()
    mode = str(params.get("mode", "drape"))
    applied = {}
    if mode == "restblend":
        n = parent.createNode("vellumrestblend", params.get("name") or "restblend")
        n.setInput(0, prev, 0)
        try:
            n.setInput(1, prev, 1)
        except Exception:
            pass
        rest_wired = False
        if params.get("rest_geo"):
            om = parent.createNode("object_merge", "rest_geo")
            _try_set(om, "objpath1", str(params["rest_geo"]))
            try:
                n.setInput(3, om)
                rest_wired = True
            except Exception:
                pass
        _apply_vellum_restblend(n, params, applied)
        solv.setInput(0, n, 0)
        try:
            solv.setInput(1, n, 1)
        except Exception:
            pass
        try:
            parent.layoutChildren()
        except Exception:
            pass
        return {"node": n.path(), "mode": "restblend", "layered_onto": prev.path(),
                "rest_wired": rest_wired, "applied": applied,
                "note": "vellumrestblend BUILT (blends rest toward input-3 geo); never cooked"}
    n = parent.createNode("vellumdrape", params.get("name") or "drape")
    n.setInput(0, prev, 0)
    try:
        n.setInput(1, prev, 1)
    except Exception:
        pass
    coll_wired = False
    if params.get("collider"):
        om = parent.createNode("object_merge", "drape_collider")
        _try_set(om, "objpath1", str(params["collider"]))
        try:
            n.setInput(2, om)
            coll_wired = True
        except Exception:
            pass
    _apply_vellum_drape(n, params, applied)
    solv.setInput(0, n, 0)
    try:
        solv.setInput(1, n, 1)
    except Exception:
        pass
    try:
        parent.layoutChildren()
    except Exception:
        pass
    return {"node": n.path(), "mode": "drape", "layered_onto": prev.path(),
            "collider_wired": coll_wired, "applied": applied,
            "note": "vellumdrape BUILT; it is a pre-roll MINI-SIM — scrub/Resimulate to settle (never cooked here)"}


@endpoint("vellum_source")
def vellum_source(params):
    """Continuous emission / add constraint patches mid-sim (DOP-scoped, advanced — the only Vellum
    tool that drops to DOP). Builds a `vellumsource` DOP microsolver inside a fresh /obj geo `name` (or
    an existing `dopnet`) for growing hair, streaming cloth confetti, or glue-on repair patches.

    PROBE-real parms (vellumsource is DOP-only — no SOP variant): emittype(once|continuous|persubstep|
    points), activate(0..1), particledensity, soppath (Source SOP path), targetpath (Target Path),
    constraintpath (Constraint SOP Path), importxform(none|local), vellumname. It has no inputs and one
    output; merge it into a DOP Vellum solver. BUILT only."""
    g = None
    if params.get("dopnet"):
        dn = resolve_node(str(params["dopnet"]))
    else:
        if not params.get("name"):
            raise ValueError("vellum_source needs `name` (fresh holder) or `dopnet`")
        g = _fresh_geo(params["name"])
        dn = g.createNode("dopnet", "vellum_emit")
    src = dn.createNode("vellumsource", params.get("node_name") or "vellumsource")
    applied = {}
    if "emittype" in params:
        applied["emittype"] = _menu_set(src, "emittype", str(params["emittype"]), _VSRC_EMITTYPE)
    if "activate" in params:
        applied["activate"] = _try_set(src, "activate", clamp(float(params["activate"]), 0.0, 1.0))
    if "particledensity" in params:
        applied["particledensity"] = _try_set(src, "particledensity", clamp(float(params["particledensity"]), 0.0, 1e6))
    if "soppath" in params:
        applied["soppath"] = _try_set(src, "soppath", str(params["soppath"]))
    if "targetpath" in params:
        applied["targetpath"] = _try_set(src, "targetpath", str(params["targetpath"]))
    if "constraintpath" in params:
        applied["constraintpath"] = _try_set(src, "constraintpath", str(params["constraintpath"]))
    if "importxform" in params:
        applied["importxform"] = _menu_set(src, "importxform", str(params["importxform"]), _VSRC_IMPORTXFORM)
    if "vellumname" in params:
        applied["vellumname"] = _try_set(src, "vellumname", str(params["vellumname"]))
    try:
        dn.layoutChildren()
    except Exception:
        pass
    result = {"node": src.path(), "source": src.path(), "dopnet": dn.path(), "applied": applied,
              "note": "vellumsource is a DOP microsolver; merge into a DOP Vellum solver (advanced)"}
    if g is not None:
        g.setDisplayFlag(bool(params.get("display", False)))
        g.layoutChildren()
        result["geo"] = g.path()
    return result


@endpoint("vellum_post")
def vellum_post(params):
    """Render prep for a Vellum sim (vellumpostprocess SOP): hair-tube generation, smoothing, detangle,
    thickness. `input` = the solver output; if it exposes a Constraint Geometry output (out1) it is
    wired into the postprocess's input 1 so welds/detangle see the constraints.

    PROBE CORRECTIONS vs spec (no plain smooth/thickness/thicknessscale parms): smoothing = subdivide
    (none|catmull|loop) + depth (rounds); `smooth` is a friendly alias (catmull + depth). Collision
    correction (detangle) = detangle (enables dodetangle) + detangle_pass + detangle_thickness.
    Hair-tube generation (guide curves -> rendered polygon tubes) = extrude (enables doextrude) +
    extrude_scale + wire_div (tube divisions). Also spatialblur(+blurgroup), rigidity (enables
    dorigidity), doweld, vis_mode (stress visualization: none|stretchstress|bendstress|...). BUILT
    only — NOT cooked (its upstream is a solver; cooking would step the sim)."""
    n = child_after(params["input"], "vellumpostprocess", params.get("name"))
    src = n.input(0)
    if src is not None:
        try:
            if len(src.outputLabels()) >= 2:
                n.setInput(1, src, 1)               # Constraint Geometry -> in1 (welds/detangle need it)
        except Exception:
            pass
    applied = {}
    if "subdivide" in params:
        applied["subdivide"] = _menu_set(n, "subdivide", str(params["subdivide"]), _VPP_SUBDIVIDE)
    if "smooth" in params:                          # friendly alias: subdiv rounds via catmull
        _menu_set(n, "subdivide", "catmull", _VPP_SUBDIVIDE)
        applied["smooth"] = _try_set(n, "depth", int(clamp(int(params["smooth"]), 0, 10)))
    if "depth" in params:
        applied["depth"] = _try_set(n, "depth", int(clamp(int(params["depth"]), 0, 10)))
    if "spatialblur" in params:
        applied["spatialblur"] = _try_set(n, "spatialblur", clamp(float(params["spatialblur"]), 0.0, 1e4))
    if "blurgroup" in params:
        applied["blurgroup"] = _try_set(n, "blurgroup", str(params["blurgroup"]))
    if "detangle" in params or "detangle_pass" in params or "detangle_thickness" in params:
        _try_set(n, "dodetangle", 1)
        applied["dodetangle"] = True
        if "detangle_pass" in params:
            applied["detangle_pass"] = _try_set(n, "detangle_pass", int(clamp(int(params["detangle_pass"]), 1, 100000)))
        if "detangle_thickness" in params:
            applied["detangle_thickness"] = _try_set(n, "detangle_thickness", clamp(float(params["detangle_thickness"]), 0.0, 1e4))
    if "extrude" in params or "extrude_scale" in params or "wire_div" in params:
        _try_set(n, "doextrude", 1)
        applied["doextrude"] = True
        if "extrude_scale" in params:
            applied["extrude_scale"] = _try_set(n, "extrude_scale", clamp(float(params["extrude_scale"]), 0.0, 1e6))
        if "wire_div" in params:
            applied["wire_div"] = _try_set(n, "wire_div", int(clamp(int(params["wire_div"]), 2, 1000)))
    if "rigidity" in params:
        _try_set(n, "dorigidity", 1)
        applied["rigidity"] = _try_set(n, "rigidity", clamp(float(params["rigidity"]), 0.0, 1e6))
    if "doweld" in params:
        applied["doweld"] = _try_set(n, "doweld", bool(params["doweld"]))
    if "vis_mode" in params:
        applied["vis_mode"] = _menu_set(n, "vis_mode", str(params["vis_mode"]), _VPP_VISMODE)
    return {"node": n.path(), "vellumpostprocess": n.path(), "applied": applied,
            "note": "BUILT only; not cooked (upstream solver — cooking would step the sim)"}


@endpoint("vellum_cache")
def vellum_cache(params):
    """BUILD (never write) a File Cache 2.0 SOP after a Vellum sim to cache it to disk. `input` = the
    SOP to cache (the solver, or a vellum_post output). Optional `pack`=true inserts a `vellumpack`
    first (geometry in0 + constraints in1 -> one packed stream) so the cache round-trips constraints.
    Same confined write contract as flip_cache/pyro_cache (FsPath write:true): `file` = the explicit
    output path (filemethod=explicit); `filetype` (bgeo|vdb) picks the format.

    HEAVY-OP GUARDRAIL: this ONLY builds and configures the filecache node — it NEVER presses Save to
    Disk / executes the cook. The caller/operator triggers the write. trange (single|range), frames
    [start,end], substeps, loadfromdisk. Returns node + write_path + trange + frames + written=False."""
    out_path = confined_path(params["file"])
    pack = None
    if params.get("pack"):
        innode = resolve_node(str(params["input"]))
        if isinstance(innode, hou.ObjNode):
            disp = innode.displayNode() or innode.renderNode()
            if disp is not None:
                innode = disp
        parent = innode.parent()
        pack = parent.createNode("vellumpack", "vellum_pack")
        pack.setInput(0, innode, 0)
        try:
            pack.setInput(1, innode, 1)
        except Exception:
            pass
        n = parent.createNode("filecache::2.0", params.get("name") or "vellum_cache")
        n.setInput(0, pack, 0)
        n.moveToGoodPosition()
    else:
        n = child_after(params["input"], "filecache::2.0", params.get("name"))
    applied = {}
    _menu_set(n, "filemethod", "explicit", _FC_FILEMETHOD)
    applied["file"] = _try_set(n, "file", out_path)
    _try_set(n, "mkpath", True)                          # create dirs at write-time (still not now)
    if "filetype" in params:
        tok = ".vdb" if str(params["filetype"]) in (".vdb", "vdb") else ".bgeo.sc"
        applied["filetype"] = _menu_set(n, "filetype", tok, _FC_FILETYPE)
    if "basename" in params:
        _try_set(n, "basename", str(params["basename"]))
    trange_tok = None
    if "trange" in params:
        trange_tok = "normal" if str(params["trange"]) in ("range", "normal") else "off"
    frames = params.get("frames")
    if frames and len(frames) >= 2:
        trange_tok = "normal"
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        ft = n.parmTuple("f")
        if ft is not None and len(ft) >= 2:
            for idx, val in ((0, float(f1)), (1, float(f2))):
                try:
                    ft[idx].deleteAllKeyframes()
                except Exception:
                    pass
                try:
                    ft[idx].set(val)
                except Exception:
                    pass
            applied["frames"] = [f1, f2]
    if trange_tok is not None:
        applied["trange"] = _menu_set(n, "trange", trange_tok, _FC_TRANGE)
    if "substeps" in params:
        applied["substeps"] = _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "loadfromdisk" in params:
        applied["loadfromdisk"] = _try_set(n, "loadfromdisk", bool(params["loadfromdisk"]))
    # NO n.render()/execute — the write is the caller's job (heavy-op guardrail).
    result = {"node": n.path(), "filecache": n.path(), "write_path": out_path,
              "trange": (n.parm("trange").evalAsString() if n.parm("trange") else None),
              "frames": applied.get("frames"), "written": False, "applied": applied,
              "note": "filecache BUILT + configured; press Save to Disk / trigger the write yourself"}
    if pack is not None:
        result["vellumpack"] = pack.path()
    return result


_MPM_MAT = ("elastic", "chunky", "liquid", "viscous", "sandy")
_MPM_EMISSION = ("once", "continuous")          # mpmsource emissiontype


@endpoint("sim_mpm")
def sim_mpm(params):
    """MPM (Material Point Method) network (SOP): source geo -> `mpmsource` -> `mpmsolver`. Great for
    terrain + destruction: jello / snow / mud / slurry / sand. BUILT only — the caller scrubs the
    timeline; this cooks the source scaffold, never the solve.

    BUG FIXES (probe-proven, H21.0.671): the old handler set `substeps` and `startframe` on mpmsolver —
    NEITHER parm exists, so both were silent no-ops. `substeps` is REMAPPED to the real
    `globalsubsteps` (1..10) and auto-enables its `doglobalsubsteps` gate. `start_frame` has NO live
    target (MPM begins at the playbar start) — it is retained probe-safely for compatibility but does not
    land. `particlesep` now auto-enables `particlesepoverride` so it actually controls resolution
    (previously gated off).

    Setup: name (fresh /obj geo), source_geo (else a default box), display.
    mpmsource material: material(elastic|chunky|liquid|viscous|sandy); density; particlesep (grain size,
    auto-enables the override); e (Young's modulus / stiffness), nu (Poisson ratio), viscosity,
    sandfrictionangle (sandy repose); initialvelocity[x,y,z]; emissiontype(once|continuous).
    mpmsolver: substeps (-> globalsubsteps), timescale, cflcondition, gravity[x,y,z] (default (0,-9.81,0)).
    Returns the geo + source + solver paths + applied."""
    name = params["name"]
    mat = str(params.get("material", "sandy"))
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    src_geo = _src_node(g, params.get("source_geo"), "box",
                        lambda n: n.parmTuple("size").set((3.0, 3.0, 3.0)) if n.parmTuple("size") else None)
    applied = {}
    msrc = g.createNode("mpmsource", "source")
    msrc.setFirstInput(src_geo)
    applied["material"] = _menu_set(msrc, "materialtype", mat, _MPM_MAT)
    if "density" in params:
        applied["density"] = _try_set(msrc, "density", clamp(float(params["density"]), 1e-3, 1e6))
    if "particlesep" in params:
        # particlesep is gated behind particlesepoverride — enable it so the value lands (else no-op).
        _try_set(msrc, "particlesepoverride", 1)
        applied["particlesep"] = _try_set(msrc, "particlesep", clamp(float(params["particlesep"]), 1e-4, 10.0))
    if "e" in params:               # Young's modulus (stiffness)
        applied["e"] = _try_set(msrc, "e", clamp(float(params["e"]), 0.0, 10.0))
    if "nu" in params:              # Poisson ratio (incompressibility)
        applied["nu"] = _try_set(msrc, "nu", clamp(float(params["nu"]), 0.0, 0.4999))
    if "viscosity" in params:
        applied["viscosity"] = _try_set(msrc, "viscosity", clamp(float(params["viscosity"]), 0.0, 1.0))
    if "sandfrictionangle" in params:
        applied["sandfrictionangle"] = _try_set(msrc, "sandfrictionangle",
                                                clamp(float(params["sandfrictionangle"]), 0.0, 90.0))
    if params.get("initialvelocity") is not None:
        applied["initialvelocity"] = _set_vec(msrc, "initialvelocity", params["initialvelocity"])
    if "emissiontype" in params:
        applied["emissiontype"] = _menu_set(msrc, "emissiontype", str(params["emissiontype"]), _MPM_EMISSION)

    solv = g.createNode("mpmsolver", "solver")
    solv.setFirstInput(msrc)
    # THE FIX: real substep control is globalsubsteps (1..10), gated by doglobalsubsteps — NOT `substeps`.
    if "substeps" in params:
        _try_set(solv, "doglobalsubsteps", 1)
        applied["substeps"] = _try_set(solv, "globalsubsteps", int(clamp(int(params["substeps"]), 1, 10)))
    if "timescale" in params:
        applied["timescale"] = _try_set(solv, "timescale", clamp(float(params["timescale"]), 1e-3, 10.0))
    if "cflcondition" in params:
        applied["cflcondition"] = _try_set(solv, "cflcondition", clamp(float(params["cflcondition"]), 0.0, 1.0))
    if params.get("gravity") is not None:
        applied["gravity"] = _set_vec(solv, "gravity", params["gravity"])
    # solver behaviour (probe-proven present on mpmsolver H21.0.671): surface tension, auto-sleep,
    # particle-level collisions, and the built-in ground plane.
    if "surface_tension" in params:
        applied["surface_tension"] = _try_set(solv, "surfacetension", clamp(float(params["surface_tension"]), 0.0, 1e4))
    if "auto_sleep" in params:
        applied["auto_sleep"] = _try_set(solv, "enablesleep", bool(params["auto_sleep"]))
    if "particle_collisions" in params:
        applied["particle_collisions"] = _try_set(solv, "particlelevelcollisions", bool(params["particle_collisions"]))
    if "move_outside_colliders" in params:
        applied["move_outside_colliders"] = _str_menu_set(solv, "moveoutsidecolliders", str(params["move_outside_colliders"]), ("none", "pos", "vel"))
    if "ground" in params:
        applied["ground"] = _try_set(solv, "groundactive", bool(params["ground"]))
    if "ground_friction" in params:
        _try_set(solv, "groundactive", 1)
        applied["ground_friction"] = _try_set(solv, "groundfriction", clamp(float(params["ground_friction"]), 0.0, 1e4))
    if "ground_sticky" in params:
        _try_set(solv, "groundactive", 1)
        applied["ground_sticky"] = _try_set(solv, "groundsticky", clamp(float(params["ground_sticky"]), 0.0, 1e4))
    if "ground_response" in params:
        applied["ground_response"] = _str_menu_set(solv, "groundresponse", str(params["ground_response"]), ("bounce", "kill"))
    # start_frame retained for compatibility but MPM has NO solver start-frame parm (playbar-driven);
    # probe-safe attempt never lands — see the docstring bug-fix note.
    if "start_frame" in params:
        applied["start_frame"] = _try_set(solv, "startframe", int(params["start_frame"]))
    solv.setDisplayFlag(display)
    solv.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "source": msrc.path(), "solver": solv.path(), "material": mat,
            "applied": applied}


# MPM interaction P0 (probe-proven H21.0.671): mpmsolver inputs = 0 Sources / 1 Colliders / 2 Container.
_MPM_COLLIDER_TYPE = {"static": 0, "animated": 1, "deforming": 2}   # mpmcollider `type` (ordered menu)
_MPM_COLLIDER_RESPONSE = ("bounce", "kill")                          # string-token menu (kill = delete)
_MPM_CONTAINER_GEOTYPE = {"bbox": 0, "convex": 1}                    # mpmcontainer `geotype` (ordered)
_MPM_CONTAINER_BOUNDS = ("opened", "closed", "kill")                # string-token menu (per-wall)


@endpoint("mpm_collider")
def mpm_collider(params):
    """Wire a collider into an existing mpmsolver's MPM Colliders input (index 1) so an MPM sim can
    actually INTERACT with geometry (the ground / props / a character it hits) — without this the solve
    ignores everything. `solver` = the mpmsolver (from sim_mpm); `collider` = a mesh / heightfield /
    animated SOP or OBJ. The collider is object-merged into the solver's parent, fed through an
    `mpmcollider` (which VDB-izes it), and wired to input 1.

    type (static|animated|deforming -> Static / Animated Rigid / Animated Deforming); response
    (bounce|kill, kill = delete material on contact); friction; sticky; expand_to_velocity (dilate the
    collider SDF+velocity to catch FAST or deforming colliders — the 'extend to cover velocity' trick);
    voxelsize (override the collider VDB resolution); fill_interior; invert_sdf (collide from the inside,
    e.g. a container shell); friction_from_attrib / sticky_from_attrib (author a per-point
    `friction`/`stickiness` attribute -> per-voxel VDB, the varying-friction/stickiness feature).
    BUILT — the caller scrubs the timeline (never a sim here)."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "mpmsolver":
        raise ValueError("`solver` must be an mpmsolver SOP (got %s)" % solv.type().name())
    parent = solv.parent()
    om = parent.createNode("object_merge", params.get("name") or "mpm_collider_in")
    _try_set(om, "objpath1", str(params["collider"]))
    mc = parent.createNode("mpmcollider", "mpm_collider")
    mc.setFirstInput(om)
    applied = {}
    if "type" in params:
        applied["type"] = _menu_idx(mc, "type", str(params["type"]), _MPM_COLLIDER_TYPE)
    if "response" in params:
        applied["response"] = _str_menu_set(mc, "response", str(params["response"]), _MPM_COLLIDER_RESPONSE)
    if "friction" in params:
        applied["friction"] = _try_set(mc, "friction", clamp(float(params["friction"]), 0.0, 1e4))
    if "sticky" in params:
        applied["sticky"] = _try_set(mc, "sticky", clamp(float(params["sticky"]), 0.0, 1e4))
    if "expand_to_velocity" in params:
        applied["expand_to_velocity"] = _try_set(mc, "expandtovol", bool(params["expand_to_velocity"]))
    if "voxelsize" in params:
        _try_set(mc, "voxelsizeoverride", 1)
        applied["voxelsize"] = _try_set(mc, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "fill_interior" in params:
        applied["fill_interior"] = _try_set(mc, "fillinterior", bool(params["fill_interior"]))
    if "invert_sdf" in params:
        applied["invert_sdf"] = _try_set(mc, "invertsdf", bool(params["invert_sdf"]))
    if "friction_from_attrib" in params:
        applied["friction_from_attrib"] = _try_set(mc, "createfrictiongrid", bool(params["friction_from_attrib"]))
    if "sticky_from_attrib" in params:
        applied["sticky_from_attrib"] = _try_set(mc, "createstickygrid", bool(params["sticky_from_attrib"]))
    solv.setInput(1, mc, 0)
    try:
        parent.layoutChildren()
    except Exception:
        pass
    return {"node": solv.path(), "solver": solv.path(), "collider": mc.path(),
            "collider_merge": om.path(), "wired": solv.input(1) is not None, "applied": applied}


@endpoint("mpm_container")
def mpm_container(params):
    """Wire an `mpmcontainer` into an existing mpmsolver's MPM Container input (index 2) — bounds the sim
    DOMAIN and sets the MASTER particle separation / voxel resolution (needed for closed-domain sims and
    to control solve cost). `solver` = the mpmsolver (from sim_mpm).

    geotype (bbox|convex = axis-aligned bounding box vs a convex hull of the domain); particlesep
    (MASTER particle separation — the sim-resolution dial); gridscale; size [x,y,z] + center [x,y,z]
    (explicit domain box); friction; sticky (container-wall response); bounds (opened|closed|kill,
    applied to all 6 walls: opened = open domain, closed = solid wall, kill = delete material that
    exits). BUILT — the caller scrubs the timeline."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "mpmsolver":
        raise ValueError("`solver` must be an mpmsolver SOP (got %s)" % solv.type().name())
    parent = solv.parent()
    cont = parent.createNode("mpmcontainer", params.get("name") or "mpm_container")
    applied = {}
    if "geotype" in params:
        applied["geotype"] = _menu_idx(cont, "geotype", str(params["geotype"]), _MPM_CONTAINER_GEOTYPE)
    if "particlesep" in params:
        applied["particlesep"] = _try_set(cont, "particlesep", clamp(float(params["particlesep"]), 1e-3, 1e4))
    if "gridscale" in params:
        applied["gridscale"] = _try_set(cont, "gridscale", clamp(float(params["gridscale"]), 1e-3, 1e3))
    if params.get("size") is not None:
        s = params["size"]
        for pn, v in zip(("sizex", "sizey", "sizez"), s):
            _try_set(cont, pn, clamp(float(v), 1e-4, 1e9))
        applied["size"] = [float(x) for x in list(s)[:3]]
    if params.get("center") is not None:
        c = params["center"]
        for pn, v in zip(("centerx", "centery", "centerz"), c):
            _try_set(cont, pn, float(v))
        applied["center"] = [float(x) for x in list(c)[:3]]
    if "friction" in params:
        applied["friction"] = _try_set(cont, "friction", clamp(float(params["friction"]), 0.0, 1e4))
    if "sticky" in params:
        applied["sticky"] = _try_set(cont, "sticky", clamp(float(params["sticky"]), 0.0, 1e4))
    if "bounds" in params:
        _try_set(cont, "allboundsoverride", 1)
        applied["bounds"] = _str_menu_set(cont, "allbounds", str(params["bounds"]), _MPM_CONTAINER_BOUNDS)
    solv.setInput(2, cont, 0)
    try:
        parent.layoutChildren()
    except Exception:
        pass
    return {"node": solv.path(), "solver": solv.path(), "container": cont.path(),
            "wired": solv.input(2) is not None, "applied": applied}


_MPM_SURF_OUTPUT = ("surface", "density", "polygonmesh")
_MPM_SURF_METHOD = ("vdbfromparticles", "neuralpointsurfacing")
_MPM_SURF_MODEL = ("balanced", "smooth", "liquid", "granular", "custom")


@endpoint("mpm_surface")
def mpm_surface(params):
    """Mesh / surface an MPM sim so it is RENDERABLE — build an `mpmsurface` after the sim particles
    (an MPM solve alone is just particles; this turns them into a surface). `input` = the MPM particle
    SOP (the mpmsolver output, or a cached sim). Emits a Surface VDB, a Density VDB, or a Polygon Mesh.

    output (surface|density|polygonmesh); method (vdbfromparticles = classic particle-fluid surfacing |
    neuralpointsurfacing = the H21 ML surfacer); model (neural model balanced|smooth|liquid|granular|
    custom, used when method=neuralpointsurfacing); voxelsize (surface resolution; auto-enables the
    override); particle_scale (per-particle surface radius); smooth (smoothing iterations); dilate;
    erode; adaptivity (polygon-mesh decimation, 0..1); fill_interior; close_sdf (force a closed SDF);
    convert_polysoup; transfer_attribs (comma list of MPM point attributes to carry onto the surface,
    e.g. `Cd,v`). BUILT — no sim runs here (the caller scrubs the timeline)."""
    n = child_after(params["input"], "mpmsurface", params.get("name"))
    applied = {}
    if "output" in params:
        applied["output"] = _str_menu_set(n, "outputtype", str(params["output"]), _MPM_SURF_OUTPUT)
    if "method" in params:
        applied["method"] = _str_menu_set(n, "surfacingmethod", str(params["method"]), _MPM_SURF_METHOD)
    if "model" in params:
        applied["model"] = _str_menu_set(n, "model", str(params["model"]), _MPM_SURF_MODEL)
    if "voxelsize" in params:
        _try_set(n, "enablevoxelsizeoverwrite", 1)
        applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e4))
    if "particle_scale" in params:
        applied["particle_scale"] = _try_set(n, "surfacepscalemult", clamp(float(params["particle_scale"]), 0.0, 1e3))
    if "smooth" in params:
        _try_set(n, "enablesmooth", 1)
        applied["smooth"] = _try_set(n, "iterations", int(clamp(int(params["smooth"]), 0, 1000)))
    if "dilate" in params:
        _try_set(n, "enabledilate", 1)
        applied["dilate"] = _try_set(n, "sdfdilate", clamp(float(params["dilate"]), 0.0, 1e4))
    if "erode" in params:
        _try_set(n, "enableerode", 1)
        applied["erode"] = _try_set(n, "sdferode", clamp(float(params["erode"]), 0.0, 1e4))
    if "adaptivity" in params:
        applied["adaptivity"] = _try_set(n, "adaptivity", clamp(float(params["adaptivity"]), 0.0, 1.0))
    if "fill_interior" in params:
        applied["fill_interior"] = _try_set(n, "fillinterior", bool(params["fill_interior"]))
    if "close_sdf" in params:
        applied["close_sdf"] = _try_set(n, "closesdf", bool(params["close_sdf"]))
    if "convert_polysoup" in params:
        applied["convert_polysoup"] = _try_set(n, "converttopolysoup", bool(params["convert_polysoup"]))
    if params.get("transfer_attribs"):
        _try_set(n, "enabletransferfrommpm", 1)
        applied["transfer_attribs"] = _try_set(n, "transferattrib", str(params["transfer_attribs"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    try:
        n.parent().layoutChildren()
    except Exception:
        pass
    return {"node": n.path(), "applied": applied}


def _mpm_geo_and_particles(params, ntype, name):
    """Shared wiring for the MPM post-sim destruction nodes: input 0 = geometry (built in its parent),
    input 1 = the MPM particles (object-merged in, world-correct). Returns (node, particles_merge)."""
    geo = resolve_node(str(params["geo"] if "geo" in params else params["pieces"]))
    if isinstance(geo, hou.ObjNode):
        geo = geo.displayNode()
    parent = geo.parent()
    n = parent.createNode(ntype, name)
    n.setInput(0, geo, 0)
    pm = parent.createNode("object_merge", "mpm_particles_in")
    _try_set(pm, "objpath1", str(params["particles"]))
    n.setInput(1, pm, 0)
    return n, pm


@endpoint("mpm_postfracture")
def mpm_postfracture(params):
    """Sim-THEN-fracture an MPM shot — fracture hi-res geometry driven by where the MPM sim actually
    stretched/broke it (unlike pre-fracturing, the cracks follow the real deformation). `geo` = the
    hi-res geometry to fracture (input 0); `particles` = the MPM sim particles (input 1). Emits fractured
    pieces with interior faces.

    cutter (boolean|voronoi = cutter method); geotype (solid|surface); perform_fracture (do the cut);
    global_scale; align_to_stretch (align crack pieces to the sim's stretch points); interior_detail
    (add noised interior faces) + noise_amplitude; fuse_distance; start_frame / end_frame (fracture
    window). BUILT — no sim runs here."""
    n, pm = _mpm_geo_and_particles(params, "mpmpostfracture", params.get("name") or "mpm_postfracture")
    applied = {}
    if "cutter" in params:
        applied["cutter"] = _str_menu_set(n, "cutteralgo", str(params["cutter"]), ("boolean", "voronoi"))
    if "geotype" in params:
        applied["geotype"] = _str_menu_set(n, "geotype", str(params["geotype"]), ("solid", "surface"))
    if "perform_fracture" in params:
        applied["perform_fracture"] = _try_set(n, "dofracture", bool(params["perform_fracture"]))
    if "global_scale" in params:
        applied["global_scale"] = _try_set(n, "globalscale", clamp(float(params["global_scale"]), 1e-4, 1e4))
    if "align_to_stretch" in params:
        applied["align_to_stretch"] = _try_set(n, "alignfractures", bool(params["align_to_stretch"]))
    if "interior_detail" in params:
        applied["interior_detail"] = _try_set(n, "enableintdetails", bool(params["interior_detail"]))
    if "noise_amplitude" in params:
        _try_set(n, "enableintdetails", 1)
        applied["noise_amplitude"] = _try_set(n, "amplitude", clamp(float(params["noise_amplitude"]), 0.0, 1e4))
    if "fuse_distance" in params:
        applied["fuse_distance"] = _try_set(n, "snapdist", clamp(float(params["fuse_distance"]), 0.0, 1e4))
    if "start_frame" in params:
        _try_set(n, "overwritestartframe", 1)
        applied["start_frame"] = _try_set(n, "startframe", int(params["start_frame"]))
    if "end_frame" in params:
        applied["end_frame"] = _try_set(n, "endframe", int(params["end_frame"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    try:
        n.parent().layoutChildren()
    except Exception:
        pass
    return {"node": n.path(), "particles_merge": pm.path(), "applied": applied}


@endpoint("mpm_deformpieces")
def mpm_deformpieces(params):
    """Retarget an MPM sim onto pre-fractured NAMED pieces — drive rigid/hi-res chunks by a (cheaper)
    MPM sim so the render geo deforms/moves with the solve. `pieces` = named pre-fractured pieces
    (input 0); `particles` = the MPM sim particles (input 1).

    type (both|piece|point = per-piece rigid transform | per-point deform | both); rigid (orthogonalize
    to rigid transforms); compute_velocity (for motion blur); stretch_tolerance; close_gaps (weld cracks
    that opened); polysoup (lighter output); transfer_attribs (comma list carried from the sim, e.g.
    `Cd,v`). BUILT — no sim runs here."""
    n, pm = _mpm_geo_and_particles(params, "mpmdeformpieces", params.get("name") or "mpm_deformpieces")
    applied = {}
    if "type" in params:
        applied["type"] = _str_menu_set(n, "type", str(params["type"]), ("both", "piece", "point"))
    if "rigid" in params:
        applied["rigid"] = _try_set(n, "orthogonalize", bool(params["rigid"]))
    if "polysoup" in params:
        applied["polysoup"] = _try_set(n, "polysoup", bool(params["polysoup"]))
    if "compute_velocity" in params:
        applied["compute_velocity"] = _try_set(n, "computevel", bool(params["compute_velocity"]))
    if "stretch_tolerance" in params:
        applied["stretch_tolerance"] = _try_set(n, "stretchtol", clamp(float(params["stretch_tolerance"]), 0.0, 1e4))
    if "close_gaps" in params:
        applied["close_gaps"] = _try_set(n, "enableclosegaps", bool(params["close_gaps"]))
    if params.get("transfer_attribs"):
        _try_set(n, "enableattribtransfer", 1)
        applied["transfer_attribs"] = _try_set(n, "attriblist", str(params["transfer_attribs"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    try:
        n.parent().layoutChildren()
    except Exception:
        pass
    return {"node": n.path(), "particles_merge": pm.path(), "applied": applied}


@endpoint("mpm_debrissource")
def mpm_debrissource(params):
    """Emit SECONDARY debris from an MPM sim — spawn extra chunks/particles where the material stretches
    hard, moves fast, or is near the surface (the shrapnel / spray / spark pass). `input` = the MPM sim
    particles. Filters choose WHERE debris is born; replicate multiplies it.

    min_stretch (only emit where stretching exceeds this — the Djp filter); min_speed (only where fast);
    max_dist (only within this distance of the surface); ratio_to_keep (thin to this fraction 0..1);
    stretch_replicate / speed_replicate (points-per-source-point, driven by stretch / speed);
    spread_along_velocity (streak the debris along its velocity); particle_scale; random_orient
    (randomize per-piece orientation). BUILT — no sim runs here."""
    n = child_after(params["input"], "mpmdebrissource", params.get("name"))
    applied = {}
    if "min_stretch" in params:
        _try_set(n, "djpfilter", 1)
        applied["min_stretch"] = _try_set(n, "mindjp", clamp(float(params["min_stretch"]), 0.0, 1e4))
    if "min_speed" in params:
        _try_set(n, "speedfilter", 1)
        applied["min_speed"] = _try_set(n, "minspeed", clamp(float(params["min_speed"]), 0.0, 1e6))
    if "max_dist" in params:
        _try_set(n, "distfilter", 1)
        applied["max_dist"] = _try_set(n, "maxdist", clamp(float(params["max_dist"]), 0.0, 1e4))
    if "ratio_to_keep" in params:
        _try_set(n, "enableratiotokeep", 1)
        applied["ratio_to_keep"] = _try_set(n, "ratiotokeep", clamp(float(params["ratio_to_keep"]), 0.0, 1.0))
    if "stretch_replicate" in params:
        _try_set(n, "djpreplicate", 1)
        applied["stretch_replicate"] = _try_set(n, "stretchnptsperpt", clamp(float(params["stretch_replicate"]), 0.0, 1e4))
    if "speed_replicate" in params:
        _try_set(n, "speedreplicate", 1)
        applied["speed_replicate"] = _try_set(n, "speednptsperpt", clamp(float(params["speed_replicate"]), 0.0, 1e4))
    if "spread_along_velocity" in params:
        applied["spread_along_velocity"] = _try_set(n, "spreadacrossvel", bool(params["spread_along_velocity"]))
    if "particle_scale" in params:
        applied["particle_scale"] = _try_set(n, "pscalemult", clamp(float(params["particle_scale"]), 0.0, 1e3))
    if "random_orient" in params:
        applied["random_orient"] = _try_set(n, "initorient", bool(params["random_orient"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    try:
        n.parent().layoutChildren()
    except Exception:
        pass
    return {"node": n.path(), "applied": applied}


@endpoint("rbd_solver")
def rbd_solver(params):
    """Bare Bullet solver for ALREADY-fractured pieces + an arbitrary constraint network — the missing
    link that lets the granular fracture lane (rbd_voronoi / vdb_shatter / rbd_constraints /
    set_constraint_field / rbd_group_constraints) actually be SIMULATED, without re-fracturing (unlike
    sim_rbd / rbd_destruction which always rebuild a material fracture).

    `pieces` = a SOP of packed fractured pieces (Geometry, input 0). `constraints` = an optional
    constraint-network SOP (Constraint Geometry, input 1). `collider` = an optional mesh/heightfield
    collider (Collision Geometry, input 3). All the deep rbdbulletsolver params (substeps, gravity,
    ground, density/friction/bounce, sleeping, constraint-break settings) are shared with sim_rbd.
    BUILT, never auto-simulated — the caller scrubs the timeline (heavy solves stay wire-only)."""
    pieces = resolve_node(str(params["pieces"]))
    if isinstance(pieces, hou.ObjNode):        # accept an OBJ geo -> use its display SOP
        pieces = pieces.displayNode()
    parent = pieces.parent()
    sim = parent.createNode("rbdbulletsolver", params.get("name") or "rbd_solver")
    sim.setInput(0, pieces, 0)                 # Geometry (packed pieces)
    if params.get("constraints"):
        con = resolve_node(str(params["constraints"]))
        if isinstance(con, hou.ObjNode):
            con = con.displayNode()
        sim.setInput(1, con, int(params.get("constraints_output", 0)))   # Constraint Geometry
    applied = {}
    if params.get("collider"):                 # optional collider -> input 3 (mirror rbd_collision)
        om = parent.createNode("object_merge", "rbd_collider")
        _try_set(om, "objpath1", str(params["collider"]))
        node, out = om, 0
        if bool(params.get("heightfield", False)):
            conv = parent.createNode("convertheightfield", "collider_polys")
            conv.setFirstInput(om)
            _try_set(conv, "lod", clamp(float(params.get("lod", 1.0)), 0.01, 1.0))
            try:
                conv.cook(force=True)
            except Exception:  # noqa: BLE001
                pass
            node, out = conv, 0
        sim.setInput(3, node, out)
        _try_set(sim, "usecollisions", 1)
    _apply_rbd_solver(sim, params, applied)    # REUSE the deep solver param block (shared with sim_rbd)
    sim.setDisplayFlag(bool(params.get("display", False)))
    sim.setRenderFlag(True)
    parent.layoutChildren()
    return {"node": sim.path(), "solver": sim.path(),
            "constraints_wired": sim.input(1) is not None,
            "collider_wired": sim.input(3) is not None, "applied": applied}


@endpoint("rbd_guide")
def rbd_guide(params):
    """Wire a guide-geometry SOP into an EXISTING rbdbulletsolver's Guide Sim input (index 4) for a
    guided / art-directed RBD sim (the solver's guide_* params drive the blend; this plumbs the geo +
    flips useguides). `solver` = the rbdbulletsolver (from sim_rbd); `guide` = the guide SOP. Cross-
    network is object-merged into the solver's parent. BUILT — the caller scrubs to run."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "rbdbulletsolver":
        raise ValueError("`solver` must be an rbdbulletsolver SOP (got %s)" % solv.type().name())
    parent = solv.parent()
    om = parent.createNode("object_merge", params.get("name") or "rbd_guide")
    _try_set(om, "objpath1", str(params["guide"]))
    try:
        om.cook(force=True)
    except Exception:  # noqa: BLE001
        pass
    solv.setInput(4, om, 0)
    _try_set(solv, "useguides", 1)
    try:
        parent.layoutChildren()
    except Exception:  # noqa: BLE001
        pass
    return {"node": solv.path(), "solver": solv.path(), "guide_merge": om.path(),
            "guide_wired": solv.input(4) is not None}


@endpoint("rbd_attach_constraints")
def rbd_attach_constraints(params):
    """Feed an authored constraint network into an EXISTING rbdbulletsolver's Constraint input (index 1)
    — attach glue_cluster / rbd_constraints / set_constraint_field to a live sim_rbd solver (whose welded
    build otherwise can't be re-fed). `solver` = the rbdbulletsolver; `constraints` = the constraint SOP.
    `constraints_output`: 0 = glue/field networks; 1 = rbdconstraintsfrom*/rbdgroupconstraints 2nd output
    (output-index selection needs the source in the SAME network as the solver). BUILT."""
    solv = resolve_node(str(params["solver"]))
    if solv.type().name() != "rbdbulletsolver":
        raise ValueError("`solver` must be an rbdbulletsolver SOP (got %s)" % solv.type().name())
    parent = solv.parent()
    src = resolve_node(str(params["constraints"]))
    out = int(clamp(int(params.get("constraints_output", 0)), 0, 1))
    if src.parent() == parent:
        solv.setInput(1, src, out)          # same network: exact output-index selection
        merged = None
    else:
        om = parent.createNode("object_merge", params.get("name") or "rbd_constraints")
        _try_set(om, "objpath1", src.path())   # cross-network: pulls the source's display output
        try:
            om.cook(force=True)
        except Exception:  # noqa: BLE001
            pass
        solv.setInput(1, om, 0)
        merged = om.path()
    # NOTE: rbdbulletsolver has NO top-level constraint-enable toggle (probe-verified H21.0.671) —
    # the Constraint Geometry (input 1) is honoured whenever it is wired. Constraint BREAKING is the
    # separate `enable_constraintbreaks` dial (on by default). (A prior build set a phantom
    # `useconstraints` parm here — a silent no-op, now removed.)
    try:
        parent.layoutChildren()
    except Exception:  # noqa: BLE001
        pass
    return {"node": solv.path(), "solver": solv.path(), "constraints_merge": merged,
            "constraints_wired": solv.input(1) is not None}


# ── FX velocity-authoring SOPs (probe-confirmed pointvelocity / volumevelocity / debrissource::2.0) ──
_PV_INIT = ("trail", "keep", "reset", "attrib")            # pointvelocity.init (Menu=index)
_PV_MERGE = ("replace", "add", "multiply")                 # pointvelocity.mergemode (Menu=index)
_DEBRIS_LIFETYPE = ("time", "frame")                       # debrissource.lifespantype (Menu=index)
_DEBRIS_DISTMODE = ("uniform", "attrib")                   # debrissource.distthreshold_mode (Menu=index)


@endpoint("point_velocity")
def point_velocity(params):
    """Author the point velocity attribute `v` (Point Velocity SOP) — the FX seed-velocity workhorse.
    `mode` picks how v is computed: compute (from deformation/trail), keep (keep incoming), set (to a
    value), attrib (from an attribute). Optionally ADD a constant velocity and/or layer CURL NOISE
    (the coherent-gust breakup used on splashes/spray/rain). BUILT (one cook)."""
    n = child_after(params["input"], "pointvelocity", params.get("name"))
    applied = {}
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    _MODEMAP = {"compute": "trail", "keep": "keep", "set": "reset", "attrib": "attrib"}
    if "mode" in params:
        applied["mode"] = _menu_set(n, "init", _MODEMAP.get(str(params["mode"]), "keep"), _PV_INIT)
    if "value" in params:                                   # constvel (when add) OR defval (when mode=set)
        if bool(params.get("add", False)):
            _try_set(n, "addvel", True)
            applied["add_value"] = _set_vec(n, "constvel", params["value"])
        else:
            applied["value"] = _set_vec(n, "defval", params["value"])
    elif bool(params.get("add", False)) and "add_velocity" in params:
        _try_set(n, "addvel", True)
        applied["add_value"] = _set_vec(n, "constvel", params["add_velocity"])
    if "merge" in params:
        applied["merge"] = _menu_set(n, "mergemode", str(params["merge"]), _PV_MERGE)
    if bool(params.get("noise", False)):
        _try_set(n, "addcurlnoise", True)
        applied["noise"] = True
        if "noise_scale" in params:
            applied["noise_scale"] = _try_set(n, "cnscale", clamp(float(params["noise_scale"]), 0.0, 1e6))
        if "noise_swirl" in params:
            applied["noise_swirl"] = _try_set(n, "cnswirlsize", clamp(float(params["noise_swirl"]), 0.0, 1e6))
        if "noise_turb" in params:
            applied["noise_turb"] = _try_set(n, "cnturbulence", int(clamp(int(params["noise_turb"]), 0, 20)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "applied": applied}


@endpoint("volume_velocity")
def volume_velocity(params):
    """Author a VELOCITY VOLUME (Volume Velocity SOP) — the non-simulated 'wind tunnel' velocity field
    that recurs across the FX (drives crest-spray / snow / rain pop_advect). input0 = the volume/VDB to
    write velocity into (e.g. from a box -> vdb_from_polygons); optional input1 (`points`) rasterizes
    `v` from points. Sources are additive toggles: a uniform wind vector + CURL NOISE (big coherent
    swirls) + point velocities. BUILT (one cook)."""
    n = child_after(params["input"], "volumevelocity", params.get("name"))
    applied = {}
    if "uniform_vel" in params:
        _try_set(n, "add_uniform_vel", True)
        applied["uniform_vel"] = _set_vec(n, "uniformvel", params["uniform_vel"])
    if bool(params.get("curl", False)):
        _try_set(n, "add_curl_noise", True)
        applied["curl"] = True
        if "curl_scale" in params:
            applied["curl_scale"] = _try_set(n, "turbscale", clamp(float(params["curl_scale"]), 0.0, 1e6))
        if "curl_swirl" in params:
            applied["curl_swirl"] = _try_set(n, "turbswirl", clamp(float(params["curl_swirl"]), 0.0, 1e6))
        if "curl_octaves" in params:
            applied["curl_octaves"] = _try_set(n, "turboctaves", int(clamp(int(params["curl_octaves"]), 0, 20)))
    if params.get("points"):
        _try_set(n, "pointapply", True)
        bridge_input(n, params["points"], index=1, name_hint="points")
        applied["points"] = str(params["points"])
        if "point_attr" in params:
            applied["point_attr"] = _try_set(n, "pointattribute", str(params["point_attr"]))
        if "point_scale" in params:
            applied["point_scale"] = _try_set(n, "pointscale", clamp(float(params["point_scale"]), -1e6, 1e6))
    return {"node": n.path(), "applied": applied}


@endpoint("debris_source")
def debris_source(params):
    """Emit a secondary-DEBRIS source (Debris Source SOP) off a fractured/static piece surface — the
    per-frame emission map (density/age/distance attribs) that feeds an emit-RBD or POP secondary sim
    (the 'juice' layer). input0 = the source geometry. Density is per-area (`density`), emission gated
    by a distance threshold; lifespan in time or frames. BUILT (one cook)."""
    n = child_after(params["input"], "debrissource::2.0", params.get("name"))
    applied = {}
    if "density" in params:
        applied["density"] = _try_set(n, "scatter_densityscale", clamp(float(params["density"]), 0.0, 1e9))
    if "dist_threshold" in params:
        applied["dist_threshold"] = _try_set(n, "distthreshold", clamp(float(params["dist_threshold"]), 0.0, 1e6))
    if "lifespan" in params:
        applied["lifespan"] = _try_set(n, "lifespan", clamp(float(params["lifespan"]), 0.0, 1e6))
    if "lifespan_type" in params:
        applied["lifespan_type"] = _menu_set(n, "lifespantype", str(params["lifespan_type"]), _DEBRIS_LIFETYPE)
    if "remove_unreleased" in params:
        applied["remove_unreleased"] = _try_set(n, "removeunreleased", bool(params["remove_unreleased"]))
    if "remove_at_life" in params:
        applied["remove_at_life"] = _try_set(n, "removeatlife", bool(params["remove_at_life"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "applied": applied}

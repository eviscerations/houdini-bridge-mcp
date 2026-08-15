"""Character / creature dynamics — WIRE-ONLY DOP object/solver cluster.

The DOP counterpart to the SOP-solver lane (`char_dynamics_w11.py`). Each builder mirrors
`handlers/sim.py`'s sim_pop/sim_rbd master-builders: it creates a fresh /obj `geo` holder, builds a
`dopnet` inside it wired to a source SOP on input 0, then places a DOP OBJECT node + a DOP SOLVER node
+ a DOP `merge` and WIRES them in DOP dataflow (object -> solver input 0 -> merge input 0). The typed
params are set and the whole structure is RETURNED — the sim is NEVER run here (a DOP solve steps every
frame over the timeline; cooking that on the executor's main thread would overwhelm the UI, exactly as
sim.py documents). The user scrubs the timeline / hits Resimulate to run it.

Live-probed on Houdini 21.0.671; every menu Enum uses
the EXACT probe tokens. Security / data-only: every exposed param is a typed scalar / enum / bool. The
DOP OBJECTS take their geometry via a `soppath` / `initial_geo` / `initialgeometry` STRING that is a SOP
NODE PATH (not a filesystem path) — exposed as an optional data-only Str, defaulted to the built source
SOP so the network is wired end-to-end. By design, only the PRIMARY geometry-path string is
exposed; the object's extra rest/target/embedded/collider geometry-path strings and any velocity-field /
clip-graph strings are deliberately omitted. NO file / stash / code / VEXpression / callback parm is
exposed anywhere.

EXCLUDED: `gasdsdsolver` — it is a gas* microsolver (Divergence/DSD source field), on the project's
out-of-scope list (gas*/pop* microsolvers); not wrapped.
"""

import hou
from houdini_executor.server import endpoint, clamp  # noqa: F401
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe setters (local copies; mirror char_dynamics_w11.py / sim.py) ───────────────────────




def _str_menu_set(node, parm, token, tokens):
    """Set a STRING-type Menu parm (the token IS the stored value) directly (probe-safe)."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:  # noqa: BLE001
        return False


def _apply(node, params, spec, applied):
    """Table-driven setter. spec: {param_key: (parm_name, kind[, tokens])} with kind in
    i(int)/f(float)/b(bool 0-1)/s(str)/m(ordered-menu-by-token-index)/sm(string-menu-by-token)."""
    for key, entry in spec.items():
        if key not in params:
            continue
        parm, kind = entry[0], entry[1]
        v = params[key]
        try:
            if kind == "i":
                applied[key] = _try_set(node, parm, int(v))
            elif kind == "f":
                applied[key] = _try_set(node, parm, float(v))
            elif kind == "b":
                applied[key] = _try_set(node, parm, 1 if v else 0)
            elif kind == "s":
                applied[key] = _try_set(node, parm, str(v))
            elif kind == "m":
                applied[key] = _menu_set(node, parm, str(v), entry[2])
            elif kind == "sm":
                applied[key] = _str_menu_set(node, parm, str(v), entry[2])
        except Exception:  # noqa: BLE001
            applied[key] = False


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("geo", name)


def _src_node(g, source_geo, default_type, default_setup):
    """object_merge an existing /obj geo, else build a default primitive source (WIRE-ONLY structural
    input — the sim is never cooked here, so a box is a valid structural source)."""
    if source_geo:
        om = g.createNode("object_merge", "src")
        _try_set(om, "objpath1", str(source_geo))
        return om
    n = g.createNode(default_type, "src")
    if default_setup:
        default_setup(n)
    return n


_NOTE = ("dopnet + DOP object + DOP solver + merge BUILT and WIRED (object -> solver -> merge; source "
         "SOP on dopnet input 0); WIRE-ONLY — the tool never runs the sim. Scrub the timeline (or press "
         "the dopnet's Resimulate) to simulate.")


# ── shared menu token tuples (EXACT probe tokens) ─────────────────────────────────────────────────
_SOLVEMETHOD = ("gsl", "gnl")                                   # femsolver solvemethod (Menu=index)
_SIMTYPE = ("quasistatic", "dynamic")                           # femsolver simulationtype
_INTEGRATOR = ("implicit", "implicit2")                         # femsolver integratortype (1st/2nd order)
_FLOATPREC = ("f32b", "f64b")                                   # femsolver floatprecision
_FEM_INIT = ("none", "rubber", "organicmass", "cork")           # femsolidobject initializebehavior
_FEM_MATMODEL = ("stableneohookean", "corotatedlinear")         # femsolidobject materialmodel
_STRAINMODEL = ("small", "large")                               # femsolidobject strainmodel
_CROWD_GEOSRC = ("sop", "first", "second", "third", "fourth")   # crowdobject initialgeometrysource (Menu=index)
_CROWD_PACKTYPE = ("useexisting", "packbyname")                 # crowdobject packtype (STRING menu)
_GEOREP = ("convexhull", "concave", "box", "capsule", "cylinder", "compound", "sphere", "plane")  # crowdobject bullet_georep (STRING menu)


def _build_dop_cluster(params, obj_type, obj_spec, solver_type, solver_spec, defname,
                       geo_hook, default_src="box", src_setup=None):
    """Create /obj geo holder -> dopnet (source SOP on input 0) -> DOP object -> DOP solver -> merge,
    wired in DOP dataflow. Sets the typed object + solver params. Returns the structure WITHOUT cooking
    a simulation. `geo_hook` in {"soppath","initial_geo","crowd"} selects how the object references the
    source geometry (all data-only SOP-path strings)."""
    name = params["name"]
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    src = _src_node(g, params.get("source_geo"), default_src, src_setup)
    dn = g.createNode("dopnet", defname)
    dn.setFirstInput(src)
    applied = {}
    _try_set(dn, "startframe", int(clamp(int(params.get("start_frame", 1)), -100000, 100000)))
    if "substeps" in params:
        applied["dopnet_substeps"] = _try_set(dn, "substep", int(clamp(int(params["substeps"]), 1, 1000)))

    # ── DOP object (maxinputs 0 — geometry is referenced by a data-only SOP path string) ──
    obj = dn.createNode(obj_type)
    if geo_hook == "soppath":
        applied["soppath"] = _try_set(obj, "soppath", str(params.get("soppath") or src.path()))
    elif geo_hook == "initial_geo":
        applied["initial_geo"] = _try_set(obj, "initial_geo", str(params.get("initial_geo") or src.path()))
    elif geo_hook == "crowd":
        if params.get("initial_geo"):
            _menu_set(obj, "initialgeometrysource", "sop", _CROWD_GEOSRC)
            applied["initial_geo"] = _try_set(obj, "initialgeometry", str(params["initial_geo"]))
        else:
            # read the dopnet's first context geometry (the wired source SOP) — mirrors sim_pop
            applied["geo_source"] = _menu_set(obj, "initialgeometrysource", "first", _CROWD_GEOSRC)
    _apply(obj, params, obj_spec, applied)

    # ── DOP solver — object feeds solver input 0 (DOP dataflow) ──
    solv = dn.createNode(solver_type)
    solv.setInput(0, obj)
    _apply(solv, params, solver_spec, applied)

    # ── DOP merge — solver feeds merge input 0; merge is the dopnet's display node ──
    mrg = dn.createNode("merge")
    mrg.setInput(0, solv)
    try:
        mrg.setDisplayFlag(True)
    except Exception:  # noqa: BLE001
        pass
    try:
        dn.layoutChildren()
    except Exception:  # noqa: BLE001
        pass
    dn.setDisplayFlag(display)
    try:
        dn.setRenderFlag(True)
    except Exception:  # noqa: BLE001
        pass
    g.setDisplayFlag(display)
    g.layoutChildren()

    obj_to_solver = solv.input(0) is not None
    solver_to_merge = mrg.input(0) is not None
    dopnet_input = dn.input(0) is not None
    return {"node": g.path(), "dopnet": dn.path(), "object": obj.path(), "solver": solv.path(),
            "merge": mrg.path(), "object_type": obj.type().name(), "solver_type": solv.type().name(),
            "wired": bool(obj_to_solver and solver_to_merge and dopnet_input),
            "object_to_solver": obj_to_solver, "solver_to_merge": solver_to_merge,
            "dopnet_input": dopnet_input, "applied": applied, "note": _NOTE}


# ── FEM solid / soft-body (femsolidobject -> femsolver) ───────────────────────────────────────────
_FEMSOLIDOBJECT = {
    "initialize_behavior": ("initializebehavior", "m", _FEM_INIT),
    "stiffness": ("stiffness", "f"), "damping_ratio": ("dampingratio", "f"),
    "mass_density": ("massdensity", "f"),
    "material_model": ("materialmodel", "m", _FEM_MATMODEL),
    "shape_stiffness": ("shapestiffness", "f"), "volume_stiffness": ("volumestiffness", "f"),
    "enable_aniso": ("enableaniso", "b"), "repulsion": ("repulsion", "f"), "friction": ("friction", "f"),
    "collide_independent": ("collideindependent", "b"),
    "collide_codependent": ("collidecodependent", "b"),
    "collide_self": ("collideself", "b"),
    "enable_fracturing": ("enablefracturing", "b"), "fracture_threshold": ("fracturethreshold", "f"),
    "strain_model": ("strainmodel", "m", _STRAINMODEL),
    "normal_drag": ("normaldrag", "f"), "tangent_drag": ("tangentdrag", "f"),
    "solve_first_frame": ("solvefirstframe", "b"),
}
_FEMSOLVER = {
    "solve_method": ("solvemethod", "m", _SOLVEMETHOD),
    "simulation_type": ("simulationtype", "m", _SIMTYPE),
    "integrator": ("integratortype", "m", _INTEGRATOR),
    "solver_substeps": ("substeps", "i"),
    "max_collision_passes": ("maxglobalcollisionpasses", "i"),
    "enable_collisions": ("enablecollisions", "b"),
    "float_precision": ("floatprecision", "m", _FLOATPREC),
    "unit_length": ("unitlength", "f"), "unit_mass": ("unitmass", "f"),
}


@endpoint("fem_solver")
def fem_solver(params):
    return _build_dop_cluster(params, "femsolidobject", _FEMSOLIDOBJECT, "femsolver", _FEMSOLVER,
                              "fem", geo_hook="soppath")


# ── Solid object (legacy FEM solid/cloth: solidobject -> femsolver) ───────────────────────────────
_SOLIDOBJECT = {
    "overall_stiffness": ("overallstiffness", "f"),
    "overall_damping_ratio": ("overalldampingratio", "f"),
    "volume_mass_density": ("volumemassdensity", "f"),
    "collide_independent": ("collideindependent", "b"),
    "collide_codependent": ("collidecodependent", "b"),
    "collide_self": ("collideself", "b"),
    "enable_fracturing": ("fractureenable", "b"), "fracture_threshold": ("fracturethreshold", "f"),
    "thickness": ("thickness", "f"), "friction": ("friction", "f"),
    "target_stiffness": ("targetstiffness", "f"), "target_damping": ("targetdamping", "f"),
    "normal_drag": ("normaldrag", "f"), "tangent_drag": ("tangentdrag", "f"),
    "solve_first_frame": ("solvefirstframe", "b"),
}


@endpoint("solid_object_solver")
def solid_object_solver(params):
    return _build_dop_cluster(params, "solidobject", _SOLIDOBJECT, "femsolver", _FEMSOLVER,
                              "solid", geo_hook="soppath")


# ── Filament dynamics (filamentobject -> filamentsolver) ──────────────────────────────────────────
_FILAMENTOBJECT = {
    "strength_scale": ("strengthscale", "f"), "thickness_scale": ("thicknessscale", "f"),
    "animate_geo": ("animategeo", "b"), "use_transform": ("usetransform", "b"),
    "display_object": ("display", "b"), "solve_first_frame": ("solvefirstframe", "b"),
}
_FILAMENTSOLVER = {
    "active": ("activate", "b"),
    "reconnect_dist": ("reconnectdist", "f"),
    "min_edge_length": ("minedgelen", "f"), "max_edge_length": ("maxedgelen", "f"),
    "enable_speed_cap": ("dospeedcap", "b"), "speed_cap": ("speedcap", "f"),
    "time_scale": ("timescale", "f"), "solver_per_object": ("solverperobject", "b"),
}


@endpoint("filament_solver")
def filament_solver(params):
    # filamentsolver input labels: Object / Pre-Solve / Post-Solve — object -> input 0
    return _build_dop_cluster(params, "filamentobject", _FILAMENTOBJECT, "filamentsolver",
                              _FILAMENTSOLVER, "filament", geo_hook="initial_geo")


# ── Crowd / creature agents (crowdobject -> crowdsolver::3.0) ─────────────────────────────────────
_CROWDOBJECT = {
    "active": ("active", "b"), "enable_ragdoll": ("enableragdoll", "b"),
    "pack_type": ("packtype", "sm", _CROWD_PACKTYPE),
    "life": ("life", "f"), "density": ("density", "f"),
    "bounce": ("bounce", "f"), "friction": ("friction", "f"),
    "inertial_tensor_stiffness": ("inertialtensorstiffness", "f"),
    "collision_shape": ("bullet_georep", "sm", _GEOREP),
    "collision_margin": ("bullet_collision_margin", "f"),
    "triangulate": ("geo_triangulate", "b"), "do_id": ("doid", "b"),
    "solve_first_frame": ("solvefirstframe", "b"),
}
_CROWDSOLVER = {
    "solver_substeps": ("substeps", "i"), "minimum_substeps": ("minimumsubsteps", "i"),
    "time_scale": ("timescale", "f"), "cfl_condition": ("cflcond", "f"),
    "max_force": ("maxforce", "f"), "air_resist": ("airresist", "f"),
    "max_turn_rate": ("maxturnrate", "f"), "turn_stiffness": ("turnstiffness", "f"),
    "turn_damping": ("turndamping", "f"),
    "max_tilt_rate": ("maxtiltrate", "f"), "tilt_stiffness": ("tiltstiffness", "f"),
    "tilt_damping": ("tiltdamping", "f"),
    "avoidance": ("avoidance", "b"), "lookahead_time": ("lookaheadtime", "f"),
    "neighbor_dist": ("ndist", "f"), "max_neighbors": ("maxneighbors", "i"),
    "locomotion_strength": ("locomotionstrength", "f"), "sim_influence": ("siminfluence", "f"),
    "look_at": ("lookat", "b"), "enable_foot_locking": ("enablefootlocking", "b"),
    "terrain_projection": ("terrainprojection", "b"),
}


@endpoint("crowd_solver")
def crowd_solver(params):
    return _build_dop_cluster(params, "crowdobject", _CROWDOBJECT, "crowdsolver::3.0", _CROWDSOLVER,
                              "crowd", geo_hook="crowd")

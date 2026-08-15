"""Character / creature dynamics — WIRE-ONLY SOP solvers. ragdoll + muscle (x3) + tissue
(x2) + skin + armature deform. Each is a single SOP solver wired to the character/muscle/skin geometry
on input 0; the node is BUILT + WIRED + its typed params set, and RETURNED — it is NEVER simulated here
(these run a sim over the timeline; stepping frames on the executor's main thread would overwhelm the
UI, exactly as `handlers/sim.py` documents). The caller scrubs the timeline to run it.

Live-probed on Houdini 21.0.671; menu Enum tokens are the
exact probe tokens. Security: every param is a typed scalar/enum/bool/attribute-name; NO file / stash /
code / VEXpression / callback parm is exposed (tissuesolver's file/stash/loadfromdisk surface is
deliberately omitted). Deferred to the DOP cluster lane (char_dynamics_dop_w11b.py): the DOP object/solver
cluster (femsolver + femsolidobject/solidobject/filament*/gasdsd + crowdsolver) which needs
dopnet+object+solver scaffolding; and the fixture-gated capture nodes (armaturecapture/musclecapture/
muscletransfer/posespacedeform/extractlocomotion). Excluded: apex::configureragdoll (APEX graph —
separate deferred lane).
"""

import hou
from houdini_executor.server import endpoint, child_after, clamp  # noqa: F401
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set






def _apply(node, params, spec, applied):
    """Table-driven setter. spec: {param_key: (parm_name, kind[, tokens])} with kind in
    i(int)/f(float)/b(bool 0-1)/s(str)/m(ordered-menu-by-token)."""
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
        except Exception:  # noqa: BLE001
            applied[key] = False


_NOTE = ("BUILT + wired to input 0; WIRE-ONLY — the tool never runs the sim. Scrub the timeline "
         "(or press the solver's Resimulate) to simulate.")


def _build(params, nodetype, defname, spec):
    """child_after the solver onto the caller's input geometry (input 0), apply the typed params, and
    return the network structure WITHOUT cooking a simulation."""
    node = child_after(params["input"], nodetype, params.get("name") or defname)
    applied = {}
    _apply(node, params, spec, applied)
    wired = bool(node.inputs()) and node.inputs()[0] is not None
    return {"node": node.path(), "solver": node.path(), "node_type": node.type().name(),
            "wired": wired, "applied": applied, "note": _NOTE}


# ── ragdoll (KineFX) ────────────────────────────────────────────────────────────────────────────
_RAGDOLL = {
    "start_frame": ("startframe", "i"), "substeps": ("substeps", "i"),
    "iterations": ("numiteration", "i"), "time_scale": ("timescale", "f"),
    "enable_gravity": ("enablegravity", "b"), "gravity": ("gravity", "f"),
    "ground": ("useground", "m", ("none", "plane", "hf")),
    "ground_bounce": ("ground_bounce", "f"), "ground_friction": ("ground_friction", "f"),
    "collision_bounce": ("collision_bounce", "f"), "collision_friction": ("collision_friction", "f"),
    "collision_density": ("collision_density", "f"),
    "pin_root": ("pinroot", "b"),
    "enable_stiffness": ("enablestiffness", "b"), "stiffness": ("stiffness", "f"),
}


@endpoint("ragdoll_solver")
def ragdoll_solver(params):
    return _build(params, "kinefx::ragdollsolver", "ragdoll_solver", _RAGDOLL)


# ── muscle (Bullet/mixed) ───────────────────────────────────────────────────────────────────────
_MUSCLE = {
    "start_frame": ("startframe", "i"), "substeps": ("substeps", "i"),
    "vellum_integrator": ("vellumintegratortype", "m", ("firstorder", "secondorder")),
    "fem_integrator": ("femintegratortype", "m", ("implicit", "implicit2")),
    "gravity": ("gravity", "f"), "vel_damping": ("veldamping", "f"),
    "enable_self_collisions": ("enableselfcollisions", "b"),
    "enable_muscle_collisions": ("enablemusclecollisions", "b"),
    "enable_bone_collisions": ("enablebonecollisions", "b"),
    "bone_collision_radius": ("bonecollisionradius", "f"),
    "collision_detection": ("collisiondetection", "m", ("default", "volume", "surface")),
    "use_ground_plane": ("usegroundplane", "b"), "ground_pos": ("groundpos", "f"),
    "unit_length": ("unitlength", "f"), "unit_mass": ("unitmass", "f"),
}


@endpoint("muscle_solver")
def muscle_solver(params):
    return _build(params, "musclesolver", "muscle_solver", _MUSCLE)


# ── muscle FEM ──────────────────────────────────────────────────────────────────────────────────
_MUSCLE_FEM = {
    "start_frame": ("startframe", "i"), "substeps": ("substeps", "i"),
    "fem_integrator": ("femintegratortype", "m", ("implicit", "implicit2")),
    "simulation_type": ("simulationtype", "m", ("quasistatic", "dynamic")),
    "gravity": ("gravity", "f"), "vel_damping": ("veldamping", "f"),
    "enable_self_collisions": ("enableselfcollisions", "b"),
    "enable_muscle_collisions": ("enablemusclecollisions", "b"),
    "enable_bone_collisions": ("enablebonecollisions", "b"),
    "bone_collision_radius": ("bonecollisionradius", "f"),
    "collision_detection": ("collisiondetection", "m", ("default", "volume", "surface")),
    "use_ground_plane": ("usegroundplane", "b"), "ground_pos": ("groundpos", "f"),
    "unit_length": ("unitlength", "f"), "unit_mass": ("unitmass", "f"),
}


@endpoint("muscle_solver_fem")
def muscle_solver_fem(params):
    return _build(params, "musclesolverfem", "muscle_solver_fem", _MUSCLE_FEM)


# ── muscle Vellum ───────────────────────────────────────────────────────────────────────────────
_MUSCLE_VELLUM = {
    "start_frame": ("startframe", "i"),
    "vellum_integrator": ("vellumintegratortype", "m", ("firstorder", "secondorder")),
    "vellum_substeps": ("vellumsubsteps", "i"), "vellum_iterations": ("vellumniter", "i"),
    "gravity": ("gravity", "f"), "drag": ("drag", "f"), "vel_damping": ("veldamping", "f"),
    "enable_self_collisions": ("enableselfcollisions", "b"),
    "enable_muscle_collisions": ("enablemusclecollisions", "b"),
    "enable_bone_collisions": ("enablebonecollisions", "b"),
    "bone_collision_radius": ("bonecollisionradius", "f"),
    "use_ground_plane": ("usegroundplane", "b"), "ground_pos": ("groundpos", "f"),
    "unit_length": ("unitlength", "f"), "unit_mass": ("unitmass", "f"),
}


@endpoint("muscle_solver_vellum")
def muscle_solver_vellum(params):
    return _build(params, "musclesolvervellum", "muscle_solver_vellum", _MUSCLE_VELLUM)


# ── tissue (FEM) — file/stash surface deliberately omitted ──────────────────────────────────────
_TISSUE = {
    "start_frame": ("startframe", "i"),
    "integrator": ("integratortype", "m", ("implicit", "implicit2")),
    "shell_shape_stiffness": ("shellshapestiffness", "f"),
    "shell_damping": ("shelldampingratio", "f"),
    "shell_mass_density": ("shellmassdensity", "f"),
    "shell_thickness": ("shellthickness", "f"),
    "solid_shape_stiffness": ("solidshapestiffness", "f"),
    "solid_volume_stiffness": ("solidvolumestiffness", "f"),
    "solid_damping": ("soliddampingratio", "f"),
    "solid_mass_density": ("solidmassdensity", "f"),
    "collision_detection": ("collisiondetection", "m", ("default", "volume", "surface")),
}


@endpoint("tissue_solver")
def tissue_solver(params):
    return _build(params, "tissuesolver", "tissue_solver", _TISSUE)


# ── tissue Vellum ───────────────────────────────────────────────────────────────────────────────
_TISSUE_VELLUM = {
    "init_frame": ("initframe", "f"),
    "vellum_integrator": ("vellumintegratortype", "m", ("firstorder", "secondorder")),
    "vellum_substeps": ("vellumsubsteps", "i"), "vellum_iterations": ("vellumiterations", "i"),
    "gravity": ("gravity", "f"), "drag": ("drag", "f"),
    "enable_collisions": ("enablecollisions", "b"),
    "tissue_collision_radius": ("tissuecollisionradius", "f"),
    "enable_ground_plane": ("enablegroundplane", "b"), "ground_pos": ("groundpos", "f"),
    "collider": ("collidersoppath", "s"), "collider_group": ("collidergroup", "s"),
    "unit_length": ("unitlength", "f"), "unit_mass": ("unitmass", "f"),
}


@endpoint("tissue_solver_vellum")
def tissue_solver_vellum(params):
    return _build(params, "tissuesolvervellum", "tissue_solver_vellum", _TISSUE_VELLUM)


# ── skin Vellum ─────────────────────────────────────────────────────────────────────────────────
_SKIN_VELLUM = {
    "init_frame": ("initframe", "f"),
    "simulation_type": ("simulationtype", "m", ("quasistatic", "dynamic")),
    "vellum_integrator": ("vellumintegratortype", "m", ("firstorder", "secondorder")),
    "vellum_substeps": ("vellumsubsteps", "i"), "vellum_iterations": ("vellumiterations", "i"),
    "gravity": ("gravity", "f"), "drag": ("drag", "f"),
    "enable_collisions": ("enablecollisions", "b"),
    "tissue_collision_radius": ("tissuecollisionradius", "f"),
    "enable_ground_plane": ("enablegroundplane", "b"), "ground_pos": ("groundpos", "f"),
    "collider": ("collidersoppath", "s"), "collider_group": ("collidergroup", "s"),
    "unit_length": ("unitlength", "f"), "unit_mass": ("unitmass", "f"),
}


@endpoint("skin_solver_vellum")
def skin_solver_vellum(params):
    return _build(params, "skinsolvervellum", "skin_solver_vellum", _SKIN_VELLUM)


# ── armature deform (muscle/skin quasistatic deformer) ──────────────────────────────────────────
_ARMATURE = {
    "steps": ("steps", "i"), "iterations": ("iter", "i"),
    "solve_type": ("solvetype", "m", ("quasistatic", "predictivequasistatic")),
    "shape_stiffness": ("shapestiffness", "f"), "volume_stiffness": ("volumestiffness", "f"),
    "skin_stretch_stiffness": ("skinstretchstiffness", "f"),
    "bone_target_strength": ("bonetargetstrength", "f"),
    "skin_target_strength": ("skintargetstrength", "f"),
    "apply_gravity": ("applygravity", "b"), "gravity": ("gravity", "f"),
    "enable_self_collisions": ("enableselfcollisions", "b"),
    "subdivision_depth": ("subdivisiondepth", "i"),
}


@endpoint("armature_deform")
def armature_deform(params):
    return _build(params, "armaturedeform", "armature_deform", _ARMATURE)

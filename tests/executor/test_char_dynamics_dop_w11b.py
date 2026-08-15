"""MAIN regression: WS5 W11b character/creature dynamics — WIRE-ONLY DOP object/solver cluster, via
the REAL _REGISTRY dispatch. These solvers step a DOP sim over the timeline; the tool only BUILDS +
WIRES (dopnet + DOP object + DOP solver + merge) + sets params, so this test asserts the NETWORK
STRUCTURE (dopnet + object + solver + merge created, correct types, object->solver->merge wired,
dopnet input wired, params applied) — it NEVER simulates. Exit 1 on any failure.
Run: hython test_char_dynamics_dop_w11b.py"""
import sys
import hou
import houdini_executor.server as srv
# import the handler module directly (NOT yet registered in __init__.py — MAIN wires that)
from houdini_executor.handlers import char_dynamics_dop_w11b  # noqa: F401  (registers the endpoints)

R = srv._REGISTRY
OK, FAIL = [], []


def check(cond, msg):
    (OK if cond else FAIL).append(msg)
    print(("ok   " if cond else "FAIL ") + msg)


def call(name, params):
    return R[name]["fn"](params)


geo = hou.node("/obj").createNode("geo", "w11b_test")
box = geo.createNode("box", "src")  # generic structural upstream geo (WIRE-ONLY: never cooked)

# (tool, object_type, solver_type, params-to-bite)
CASES = [
    ("fem_solver", "femsolidobject", "femsolver",
     {"name": "w11b_fem", "stiffness": 2500.0, "material_model": "corotatedlinear",
      "simulation_type": "dynamic", "solver_substeps": 3}),
    ("solid_object_solver", "solidobject", "femsolver",
     {"name": "w11b_solid", "overall_stiffness": 50000.0, "thickness": 0.01,
      "integrator": "implicit2", "solver_substeps": 2}),
    ("filament_solver", "filamentobject", "filamentsolver",
     {"name": "w11b_fil", "strength_scale": 8.0, "max_edge_length": 0.75,
      "enable_speed_cap": True, "time_scale": 0.5}),
    ("crowd_solver", "crowdobject", "crowdsolver::3.0",
     {"name": "w11b_crowd", "max_turn_rate": 120.0, "avoidance": True,
      "collision_shape": "capsule", "max_neighbors": 50}),
]

for tool, obj_type, solver_type, params in CASES:
    try:
        res = call(tool, dict({"source_geo": box.path()}, **params))
    except Exception as ex:  # noqa: BLE001
        check(False, "%s raised: %s" % (tool, str(ex).splitlines()[0][:100]))
        continue

    dn = hou.node(res.get("dopnet", ""))
    check(dn is not None and dn.type().name() == "dopnet", "%s dopnet created" % tool)
    check(res.get("dopnet_input") and dn is not None and dn.input(0) is not None,
          "%s dopnet input 0 wired to source" % tool)

    obj = hou.node(res.get("object", ""))
    ot = obj.type().name() if obj is not None else ""
    check(obj is not None and (ot == obj_type or ot.startswith(obj_type + "::")),
          "%s DOP object == %s (got %s)" % (tool, obj_type, ot))

    solv = hou.node(res.get("solver", ""))
    st = solv.type().name() if solv is not None else ""
    check(solv is not None and (st == solver_type or st.startswith(solver_type.split("::")[0] + "::")),
          "%s DOP solver == %s (got %s)" % (tool, solver_type, st))

    mrg = hou.node(res.get("merge", ""))
    check(mrg is not None and mrg.type().name() == "merge", "%s DOP merge created" % tool)

    # DOP dataflow: object -> solver input 0 -> merge input 0
    check(res.get("object_to_solver") and solv is not None and solv.input(0) is not None
          and solv.input(0).path() == res.get("object"),
          "%s object -> solver input 0 wired" % tool)
    check(res.get("solver_to_merge") and mrg is not None and mrg.input(0) is not None
          and mrg.input(0).path() == res.get("solver"),
          "%s solver -> merge input 0 wired" % tool)
    check(bool(res.get("wired")), "%s fully wired (object->solver->merge + dopnet input)" % tool)

    applied = res.get("applied", {})
    tuned = {k: v for k, v in params.items() if k != "name"}
    check(any(applied.get(k) for k in tuned), "%s params applied (%s)"
          % (tool, {k: applied.get(k) for k in tuned}))
    check("WIRE-ONLY" in (res.get("note") or ""), "%s returns WIRE-ONLY note (not simulated)" % tool)

geo.destroy()
print("\n==== %d ok / %d FAIL ====" % (len(OK), len(FAIL)))
sys.exit(1 if FAIL else 0)

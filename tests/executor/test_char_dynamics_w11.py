"""MAIN regression: WS5 W11a character/creature dynamics — WIRE-ONLY SOP solvers, via the REAL
_REGISTRY dispatch. These solvers run a sim over the timeline; the tool only BUILDS + WIRES + sets
params, so this test asserts the NETWORK STRUCTURE (node created, correct type, input 0 wired, params
applied) — it never simulates. Exit 1 on any failure.  Run: hython test_char_dynamics_w11.py"""
import sys
import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  (registers the endpoints)
from houdini_executor.handlers import char_dynamics_w11  # noqa: F401  (belt-and-suspenders)

R = srv._REGISTRY
OK, FAIL = [], []


def check(cond, msg):
    (OK if cond else FAIL).append(msg)
    print(("ok   " if cond else "FAIL ") + msg)


def call(name, params):
    return R[name]["fn"](params)


geo = hou.node("/obj").createNode("geo", "w11_test")
# generic upstream geometry (WIRE-ONLY: we never cook a sim, so a box is a valid structural input)
box = geo.createNode("box", "src")

# (tool, node_type, a param to bite + its check)
CASES = [
    ("ragdoll_solver", "kinefx::ragdollsolver", {"substeps": 5, "gravity": -9.8, "ground": "plane"}),
    ("muscle_solver", "musclesolver", {"substeps": 4, "vellum_integrator": "secondorder", "gravity": -9.8}),
    ("muscle_solver_fem", "musclesolverfem", {"simulation_type": "dynamic", "fem_integrator": "implicit2"}),
    ("muscle_solver_vellum", "musclesolvervellum", {"vellum_substeps": 6, "drag": 0.1}),
    ("tissue_solver", "tissuesolver", {"integrator": "implicit2", "shell_thickness": 0.05}),
    ("tissue_solver_vellum", "tissuesolvervellum", {"vellum_iterations": 200, "enable_collisions": True}),
    ("skin_solver_vellum", "skinsolvervellum", {"simulation_type": "dynamic", "vellum_substeps": 4}),
    ("armature_deform", "armaturedeform", {"steps": 3, "solve_type": "predictivequasistatic", "shape_stiffness": 100.0}),
]

for tool, ntype, extra in CASES:
    try:
        res = call(tool, dict({"input": box.path()}, **extra))
    except Exception as ex:  # noqa: BLE001
        check(False, "%s raised: %s" % (tool, str(ex).splitlines()[0][:80]))
        continue
    n = hou.node(res["node"])
    check(n is not None, "%s node created" % tool)
    tn = n.type().name() if n is not None else ""
    check(tn == ntype or tn.startswith(ntype + "::"), "%s type == %s (got %s)" % (tool, ntype, tn))
    check(bool(res.get("wired")) and n is not None and n.inputs() and n.inputs()[0] is not None,
          "%s wired to input 0" % tool)
    applied = res.get("applied", {})
    check(any(applied.get(k) for k in extra), "%s params applied (%s)"
          % (tool, {k: applied.get(k) for k in extra}))
    check("WIRE-ONLY" in (res.get("note") or ""), "%s returns WIRE-ONLY note (not simulated)" % tool)

geo.destroy()
print("\n==== %d ok / %d FAIL ====" % (len(OK), len(FAIL)))
sys.exit(1 if FAIL else 0)

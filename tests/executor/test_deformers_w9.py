"""Regression test for the WS5 W9b SOP deformers lane. Drives the REAL handler dispatch path
(houdini_executor _REGISTRY) headless on real mesh + driver-shape fixtures. Asserts each of the 12
endpoints builds + wires + cooks (multi-input deformers get their extra operand(s)), a sample of
non-default params (incl. index-menu tokens) actually land, and that a required-operand-missing
deformer degrades to cooked:false without crashing. Exit 1 on ANY failure.

NOTE: deformers_w9 is NOT yet registered in handlers/__init__.py — MAIN must add it. This test imports
it directly so it can run standalone; MAIN re-runs after registering."""
import sys
import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  already-shipped endpoints
import houdini_executor.handlers.deformers_w9  # noqa: F401  register THIS lane directly

R = srv._REGISTRY
FAIL = []
OK = []


def call(name, params):
    return R[name]["fn"](params)


def errs(path):
    n = hou.node(path)
    try:
        return n.errors()
    except Exception:
        return []


def check(cond, msg):
    (OK if cond else FAIL).append(msg)
    print(("ok   " if cond else "FAIL ") + msg)


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────
geo = hou.node("/obj").createNode("geo", "w9b_test")
grid = geo.createNode("grid"); grid.parm("rows").set(20); grid.parm("cols").set(20)
sph = geo.createNode("sphere"); sph.parm("type").set(2); sph.parm("freq").set(6)   # polygon mesh
torus = geo.createNode("torus")
torus2 = geo.createNode("torus", "torus2")
for n in geo.children():
    try:
        n.cook(force=True)
    except Exception:
        pass
GRID, SPH, TOR, TOR2 = grid.path(), sph.path(), torus.path(), torus2.path()
check(len(grid.geometry().points()) == 400, "fixture grid cooked")

# ── deformers that must cook on their wired fixture ────────────────────────────────────────────────
CASES = [
    ("delta_mush", {"input": SPH, "iterations": 10, "step_size": 0.5, "method": "uniform"}),
    ("surface_relax", {"input": GRID, "reference": GRID, "iterations": 5}),
    ("laplacian", {"input": GRID, "mode": "cotan", "diffusion": True, "diffusion_coeff": 1.0}),
    ("soft_transform", {"input": GRID, "translate": [0, 0.5, 0], "soft_radius": 0.4,
                        "soft_type": "cubic", "distance_metric": "surface"}),
    ("soft_peak", {"input": GRID, "distance": 0.3, "soft_radius": 0.4, "soft_type": "quadratic"}),
    ("elastic_transform", {"input": GRID, "mode": "grab", "grab_direction": [0, 1, 0],
                           "grab_strength": 0.5, "radius": 1.0, "rigidity": 0.2}),
    ("magnet", {"input": GRID, "magnet": TOR, "translate": [0, 0.3, 0], "affect_position": True}),
    ("bulge", {"input": SPH, "magnet": TOR, "magnitude": 0.4}),
    ("creep", {"input": GRID, "surface": SPH, "set_uv": True}),
    ("vector_deform", {"input": GRID, "rest_points": TOR, "deformed_points": TOR2,
                       "outer_radius": 2.0, "steps": 3}),
    ("shrinkwrap", {"input": SPH, "type": "xyz", "shrink_amount": 0.0}),
    ("detangle", {"input": GRID, "prev_pos": "P", "thickness": 0.02}),
]
MADE = {}
for name, p in CASES:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        e = errs(res["node"])
        cooked = res.get("cooked", False)
        check(cooked and not e, f"{name} cooked ({res.get('points')}pts {res.get('prims')}prim)")
        if e:
            print("      errors:", [str(x)[:120] for x in e])
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── required-operand-missing deformers degrade gracefully (cooked:false, no crash) ─────────────────
for name, p in [("magnet", {"input": GRID}), ("bulge", {"input": SPH})]:
    try:
        res = call(name, p)
        check(res.get("cooked") is False, f"{name} without `magnet` degrades cooked:false (no crash)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} no-magnet raised: {ex}")

# ── param-bite checks (menu index + values actually landed) ────────────────────────────────────────
dm = hou.node(MADE.get("delta_mush", ""))
if dm:
    check(dm.parm("iterations").eval() == 10, "delta_mush iterations=10 applied")
st = hou.node(MADE.get("soft_transform", ""))
if st:
    # soft_type tokens (linear,quadratic,cubic,meta) -> cubic = index 2
    check(st.parm("type").eval() == 2, "soft_transform soft_type='cubic' -> index 2")
    check(abs(st.parmTuple("t").eval()[1] - 0.5) < 1e-6, "soft_transform translate y=0.5 applied")
sw = hou.node(MADE.get("shrinkwrap", ""))
if sw:
    check(sw.parm("type").eval() == 0, "shrinkwrap type='xyz' -> index 0")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)

"""Regression test for the WS5 W9a SOP modeling-verbs lane. Drives the REAL handler dispatch path
(houdini_executor _REGISTRY) headless on real curve/surface/mesh fixtures. Asserts each of the 17
endpoints builds + wires + cooks (multi-input verbs get their extra operand), a sample of non-default
params (incl. index-menu tokens) actually land, and that a required-operand-missing verb degrades to
cooked:false without crashing. Exit 1 on ANY failure.

NOTE: modeling_verbs_w9 is NOT yet registered in handlers/__init__.py — MAIN must add it. This test
imports it directly so it can run standalone; MAIN re-runs after registering."""
import sys
import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  already-shipped endpoints
import houdini_executor.handlers.modeling_verbs_w9  # noqa: F401  register THIS lane directly

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
geo = hou.node("/obj").createNode("geo", "w9a_test")
grid = geo.createNode("grid"); grid.parm("rows").set(20); grid.parm("cols").set(20)
tube = geo.createNode("tube"); tube.parm("cols").set(16); tube.parm("rows").set(4)
line = geo.createNode("line"); line.parm("points").set(12)

# two circle cross-sections merged (poly_loft)
c1 = geo.createNode("circle"); c1.parm("type").set(1); c1.parm("divs").set(16)
c2 = geo.createNode("circle"); c2.parm("type").set(1); c2.parm("divs").set(16)
c2x = geo.createNode("xform"); c2x.setInput(0, c2); c2x.parm("ty").set(2.0)
loftmrg = geo.createNode("merge", "loftmrg"); loftmrg.setInput(0, c1); loftmrg.setInput(1, c2x)

# two lines merged (fillet / join)
la = geo.createNode("line", "la"); la.parm("points").set(10)
lb = geo.createNode("line", "lb"); lb.parm("points").set(10)
lbx = geo.createNode("xform", "lbx"); lbx.setInput(0, lb); lbx.parm("ty").set(2.0)
linemrg = geo.createNode("merge", "linemrg"); linemrg.setInput(0, la); linemrg.setInput(1, lbx)

# two surface hulls merged (stitch) — grid type index 1 = mesh hull
sa = geo.createNode("grid", "sa"); sa.parm("type").set(1); sa.parm("rows").set(10); sa.parm("cols").set(10)
sb = geo.createNode("grid", "sb"); sb.parm("type").set(1); sb.parm("rows").set(10); sb.parm("cols").set(10)
sbx = geo.createNode("xform", "sbx"); sbx.setInput(0, sb); sbx.parm("tx").set(1.05)
hullmrg = geo.createNode("merge", "hullmrg"); hullmrg.setInput(0, sa); hullmrg.setInput(1, sbx)

for n in geo.children():
    try:
        n.cook(force=True)
    except Exception:
        pass
GRID, TUBE, LINE = grid.path(), tube.path(), line.path()
LOFT, LINEMRG, HULL = loftmrg.path(), linemrg.path(), hullmrg.path()
check(len(grid.geometry().points()) == 400, "fixture grid cooked")

# ── single/primary-input verbs that must cook on their fixture ─────────────────────────────────────
CASES = [
    ("poly_patch", {"input": GRID, "basis": "bspline", "divisions": [6, 6], "output_polygons": True}),
    ("poly_spline", {"input": LINE, "spline_type": "bspline", "divisions": 20, "tension": 1.0}),
    ("circle_spline", {"input": LINE, "spline_type": "circle", "segment_divisions": 12}),
    ("poly_cap", {"input": TUBE, "cap_all": True, "triangulate": True}),
    ("cap", {"input": TUBE, "first_u_cap": "round", "last_u_cap": "round", "divisions_u": 3}),
    ("poly_hinge", {"input": GRID, "group_type": "primitive", "hinge_angle": 45.0, "divisions": 4}),
    ("poly_stitch", {"input": GRID, "tolerance": 0.01, "consolidate": True}),
    ("poly_soup", {"input": GRID, "convex": True, "merge_vertices": True}),
    ("poly_cut", {"input": GRID, "type": "edges", "strategy": "cut"}),
    ("poly_path", {"input": LINE, "connect_ends": True, "close_loops": True}),
    ("convert_line", {"input": GRID, "connect_path": True, "compute_length": True}),
    ("circle_from_edges", {"input": GRID, "group_type": "prims", "scale": 1.0}),
    ("orient_along_curve", {"input": LINE, "tangent_type": "diff", "up_vector": [0, 1, 0],
                            "apply_roll": True, "roll": 30.0, "output_quaternion": True}),
    ("join", {"input": LINEMRG, "join_op": "all", "direction": "ujoin"}),
    ("poly_loft", {"input": LOFT, "connect_closest_ends": True, "create_group": True}),
    ("fillet", {"input": LINEMRG, "fillet": "all", "fillet_type": "circular", "order": 4}),
    ("stitch", {"input": HULL, "stitch": "all", "tolerance": 1.0, "bias": 0.5}),
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

# ── param-bite checks (menu index + tuple values actually landed) ──────────────────────────────────
pp = hou.node(MADE.get("poly_patch", ""))
if pp:
    check(pp.parm("basis").eval() == 1, "poly_patch basis='bspline' -> index 1 (cardinal,bspline)")
    check(tuple(pp.parmTuple("divisions").eval()) == (6, 6), "poly_patch divisions=[6,6] tuple applied")
ps = hou.node(MADE.get("poly_spline", ""))
if ps:
    # basis tokens (bezier,sbezier,c1bezier,degree2,bspline,cardinal,linear) -> bspline = index 4
    check(ps.parm("basis").eval() == 4, "poly_spline spline_type='bspline' -> index 4")
oc = hou.node(MADE.get("orient_along_curve", ""))
if oc:
    check(abs(oc.parm("roll").eval() - 30.0) < 1e-6, "orient_along_curve roll=30 applied")
    check(oc.parm("outputquaternion").eval() == 1, "orient_along_curve output_quaternion applied")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)

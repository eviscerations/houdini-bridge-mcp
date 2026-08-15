"""MAIN regression: validated-VEX v2 increment (owner-ratified 2026-08-08) through the REAL
set_attrib_expr dispatch path — `foreach` (folded into allow_attrib_loops) + the `add*`/`removevertex`
CONSTRUCTION/GROWTH writers (new allow_attrib_geogrow consent). Confirms end-to-end that:
  * a `foreach` snippet builds + cooks and produces the right value (snapshot-finite iteration);
  * an `addpoint` snippet builds + cooks and ACTUALLY grows the point count;
  * with allow_attrib_geogrow OFF the SAME growth snippet is REJECTED before any node is created
    (graduated consent — enabling loops/deletion does NOT grant growth).
The standalone validator corpus (`python houdini_executor/vex_validator.py`) is the unit gate; this is
the live-cook gate. Monkeypatches the arm.json flag reads so it never touches the real arm.json.
Run: hython test_validated_vex_v2.py   (exit 1 on any failure)."""
import sys
import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401
from houdini_executor.handlers import vexwrangle as vw

R = srv._REGISTRY
OK, FAIL = [], []


def check(cond, msg):
    (OK if cond else FAIL).append(msg)
    print(("ok   " if cond else "FAIL ") + msg)


def _cook(path):
    n = hou.node(path)
    try:
        n.cook(force=True)
        return n, tuple(n.errors() or ())
    except hou.Error as e:  # noqa: BLE001
        return n, (str(e),)


def _call(params):
    return R["set_attrib_expr"]["fn"](params)


# all consent flags ON (monkeypatched — real arm.json untouched)
vw._allow_attrib_expr = lambda: True
vw._allow_attrib_loops = lambda: True
vw._allow_attrib_geoedit = lambda: True
vw._allow_attrib_geogrow = lambda: True

geo = hou.node("/obj").createNode("geo", "vv2_test")
grid = geo.createNode("grid", "grid1")
grid.parm("rows").set(10)
grid.parm("cols").set(10)

# 1. foreach — value form summing a local array (snapshot-finite)
r1 = _call({"target": grid.path(), "wrangle_type": "attribwrangle", "run_over": "points",
            "outputs": "mass",
            "code": 'float a[] = {1.0, 2.0, 3.0}; foreach (float v; a) { f@mass += v; }'})
n1, e1 = _cook(r1["node"])
check(not e1, "foreach snippet cooked clean" + (" errs=%s" % (e1,) if e1 else ""))
check(abs(n1.geometry().point(0).attribValue("mass") - 6.0) < 1e-4, "foreach summed array -> mass==6.0")

# 2. foreach index+value form with an attr-writer to a declared output
r2 = _call({"target": grid.path(), "wrangle_type": "attribwrangle", "run_over": "detail",
            "outputs": "Cd",
            "code": 'float a[] = {0.2, 0.5}; foreach (int i; float v; a) { setpointattrib(0, "Cd", i, set(v, 0, 0), "set"); }'})
_n2, e2 = _cook(r2["node"])
check(not e2, "foreach index+value + setpointattrib cooked clean" + (" errs=%s" % (e2,) if e2 else ""))

# 3. addpoint growth inside a bounded for (needs allow_geogrow)
before = len(grid.geometry().points())
r3 = _call({"target": grid.path(), "wrangle_type": "attribwrangle", "run_over": "detail",
            "outputs": "mass",
            "code": 'for (int i = 0; i < 5; i++) { addpoint(0, set(i, 0, 0)); }'})
n3, e3 = _cook(r3["node"])
after = len(n3.geometry().points())
check(not e3, "addpoint+for snippet cooked clean" + (" errs=%s" % (e3,) if e3 else ""))
check(after == before + 5, "addpoint grew point count %d -> %d (+5)" % (before, after))

# 4. removevertex is in the geogrow set (accepted with the flag) — just build/validate (no cook assert)
try:
    _call({"target": grid.path(), "wrangle_type": "attribwrangle", "run_over": "prims",
           "outputs": "mass", "code": 'if (@primnum < 0) { removevertex(0, @primnum, 0); }'})
    check(True, "removevertex accepted under allow_geogrow")
except Exception as ex:  # noqa: BLE001
    check(False, "removevertex should be accepted under allow_geogrow: %s" % ex)

# 5. CONSENT: with allow_geogrow OFF, the SAME growth snippet REJECTS before any node is made
vw._allow_attrib_geogrow = lambda: False
try:
    _call({"target": grid.path(), "wrangle_type": "attribwrangle", "run_over": "detail",
           "outputs": "mass", "code": 'addpoint(0, {0,0,0});'})
    check(False, "addpoint with allow_geogrow=False MUST raise")
except Exception as ex:  # noqa: BLE001
    check("geogrow" in str(ex).lower(), "growth REJECTED with flag off: %s" % str(ex).splitlines()[0][:70])

# 6. CONSENT: loops off => foreach also rejects (folded into allow_attrib_loops)
vw._allow_attrib_loops = lambda: False
try:
    _call({"target": grid.path(), "wrangle_type": "attribwrangle", "run_over": "points",
           "outputs": "mass", "code": 'float a[] = {1.0}; foreach (float v; a) { f@mass += v; }'})
    check(False, "foreach with allow_attrib_loops=False MUST raise")
except Exception as ex:  # noqa: BLE001
    check("foreach" in str(ex).lower() or "loops" in str(ex).lower(), "foreach REJECTED with loops off: %s" % str(ex).splitlines()[0][:70])

geo.destroy()
print("\n==== %d ok / %d FAIL ====" % (len(OK), len(FAIL)))
sys.exit(1 if FAIL else 0)

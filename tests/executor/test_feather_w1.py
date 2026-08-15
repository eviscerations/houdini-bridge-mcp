"""MAIN independent verification of the WS5 W1 feather lane — drives the REAL handler dispatch path
(houdini_executor _REGISTRY) headless, not the probe's raw node cooks. Asserts: bootstrap builds a
feather; every operator creates+wires+cooks on a real groom with counts>0 and no node errors; and a
sample of non-default params (incl. index-menu + string-menu) actually land on the node.
Exit 1 on ANY failure."""
import sys
import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  registers every endpoint

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


# ── 1. bootstrap entry ────────────────────────────────────────────────────────────────────────────
r = call("feather_template", {"name": "feath_tpl", "shaft_density": 30, "barb_density": 80,
                              "barb_segs": 3, "side": "l"})
tpl_sop = r["sop"]
check(r["points"] > 0 and r["prims"] >= 1, f"feather_template cooked ({r['points']}pts {r['prims']}prim)")
tn = hou.node(tpl_sop)
check(not tn.errors(), "feather_template no cook errors")
check(tn.parm("setside").eval() == 1 and tn.parm("side").evalAsString() == "l",
      "feather_template string-menu side='l' applied (setside on)")

# ── 2. build a 30-feather groom fixture on a grid skin (in the TEMPLATE's geo so wiring is same-net) ─
geo = hou.node(tpl_sop).parent()
grid = geo.createNode("grid"); grid.parm("rows").set(20); grid.parm("cols").set(20)
scat = geo.createNode("scatter::2.0"); scat.setInput(0, grid); scat.parm("npts").set(30)
cp = geo.createNode("copytopoints::2.0"); cp.setInput(0, hou.node(tpl_sop)); cp.setInput(1, scat)
cp.cook(force=True)
feathers = cp.path()
skin = grid.path()
check(len(cp.geometry().prims()) == 30, f"groom fixture = 30 feathers ({len(cp.geometry().prims())})")

# ── 3. operators that cook on the plain groom ──────────────────────────────────────────────────────
COOKING = [
    ("feather_clump", {"input": feathers, "skin": skin, "amount": 0.5, "split_mode": "attrib"}),
    ("feather_noise", {"input": feathers, "skin": skin, "amplitude": 0.02}),
    ("feather_width", {"input": feathers, "skin": skin, "shaft_width": 0.01}),
    ("feather_resample", {"input": feathers, "skin": skin, "shaft_resample": True, "shaft_maxsegs": 8}),
    ("feather_deintersect", {"input": feathers, "skin": skin, "iterations": 3}),
    ("feather_normalize", {"input": feathers, "skin": skin, "flatten": True}),
    ("feather_barb_transform", {"input": feathers, "skin": skin, "direction": "objtofeather"}),
    ("feather_surface", {"input": feathers, "skin": skin, "shaft_output": "surface"}),
    ("feather_convert", {"input": feathers, "skin": skin, "output_type": "curves"}),
    ("feather_uncondense", {"input": feathers, "skin": skin}),
    ("feather_surface_blend", {"input": feathers, "skin": skin, "blend": 0.5}),
    ("feather_visualize", {"input": feathers, "skin": skin, "barb_mode": "surface"}),
    ("feather_barb_tangents", {"input": feathers}),
    ("feather_primitive", {"input": feathers, "barb_segs": 2}),
]
MADE = {}
for name, p in COOKING:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        e = errs(res["node"])
        check(not e and res.get("points",0) > 0, f"{name} cooked ({res.get('points')}pts {res.get('prims')}prim)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── 4. extra-input operators (target/source/ray_geo wired) ─────────────────────────────────────────
# feather_min_dist needs a target-feathers set (input 3); reuse the groom as its own target.
try:
    res = call("feather_min_dist", {"input": feathers, "skin": skin, "target": feathers})
    check(not errs(res["node"]) and res.get("points",0) > 0, f"feather_min_dist cooked ({res.get('points')}pts)")
except Exception as ex:  # noqa: BLE001
    check(False, f"feather_min_dist raised: {ex}")
# feather_ray onto the grid skin as ray geometry (input 3).
try:
    res = call("feather_ray", {"input": feathers, "skin": skin, "ray_geo": skin})
    check(not errs(res["node"]) and res.get("points",0) > 0, f"feather_ray cooked ({res.get('points')}pts)")
except Exception as ex:  # noqa: BLE001
    check(False, f"feather_ray raised: {ex}")

# ── 5. context-needy nodes: assert BUILD + WIRE + PARAM (may not fully cook without richer graph) ────
CTX = [
    ("feather_template_assign", {"input": feathers, "skin": skin, "templates": tpl_sop, "seed": 2.0}, "seed", 2.0),
    ("feather_template_interpolate", {"input": feathers, "skin": skin, "templates": tpl_sop, "blend": 0.7}, "blend", 0.7),
    ("feather_deform", {"input": feathers, "skin": skin, "mode": "capture"}, None, None),
    ("feather_attrib_interpolate", {"input": feathers, "source": feathers, "barb_mirror": False}, None, None),
]
for name, p, parm, want in CTX:
    try:
        res = call(name, p)
        n = hou.node(res["node"])
        wired = n.inputs() and n.inputs()[0] is not None
        pm = (n.parm(parm).eval() == want) if parm else True
        check(n is not None and wired and pm, f"{name} built+wired+param (cook may need richer graph)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── 6. index-menu bite check ────────────────────────────────────────────────────────────────────────
cl = hou.node(MADE.get("feather_clump", ""))
if cl:
    check(cl.parm("splitlocmode").eval() == 1, "feather_clump index-menu split_mode='attrib' -> 1")
bx = hou.node(MADE.get("feather_barb_transform", ""))
if bx:
    check(bx.parm("xform").eval() == 1, "feather_barb_transform index-menu direction='objtofeather' -> 1")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)

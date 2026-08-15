"""Regression test for the WS5 W6 SOP attribute-ops lane. Drives the REAL handler dispatch path
(houdini_executor _REGISTRY) headless on a fixture seeded with real float/int/vector/color/string
attributes. Asserts each of the 18 endpoints builds + wires + cooks (two-input ops get their second
input), and that a sample of non-default params (incl. index-menu tokens) actually land on the node.
Exit 1 on ANY failure.

NOTE: the handler module (attribute_ops_w6) is NOT yet registered in handlers/__init__.py — MAIN will
add it. This test imports it directly so it can run standalone; MAIN re-runs after registering."""
import sys
import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  registers the already-shipped endpoints
import houdini_executor.handlers.attribute_ops_w6  # noqa: F401  register THIS lane directly

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


# ── fixture: a grid with real attributes seeded by NATIVE nodes ─────────────────────────────────────
geo = hou.node("/obj").createNode("geo", "w6_test")
grid = geo.createNode("grid"); grid.parm("rows").set(20); grid.parm("cols").set(20)
col = geo.createNode("color"); col.setInput(0, grid); col.parm("class").set(2)        # Cd
nrm = geo.createNode("normal"); nrm.setInput(0, col)                                   # N
meas = geo.createNode("measure"); meas.setInput(0, nrm)                                # area (float prim)
# attribcreate::2.0 class menu order is (detail, primitive, point, vertex) -> point = index 2
acf = geo.createNode("attribcreate::2.0"); acf.setInput(0, meas)
acf.parm("name1").set("mass"); acf.parm("class1").set(2); acf.parm("type1").set(0); acf.parm("value1v1").set(1.5)
aci = geo.createNode("attribcreate::2.0"); aci.setInput(0, acf)
aci.parm("name1").set("idx"); aci.parm("class1").set(2); aci.parm("type1").set(2)
nm = geo.createNode("name"); nm.setInput(0, aci); nm.parm("name1").set("piece0")       # string 'name'
nm.cook(force=True)
FIX = nm.path()
check(len(nm.geometry().points()) == 400, f"fixture cooked ({len(nm.geometry().points())} pts)")

# ── 1. single-input ops that must cook on the seeded fixture ─────────────────────────────────────────
SINGLE = [
    ("attrib_adjust_float", {"input": FIX, "attrib": "mass", "attrib_class": "point",
                             "operation": "mult", "single_value": 2.0}),
    ("attrib_adjust_integer", {"input": FIX, "attrib": "idx", "attrib_class": "point",
                               "operation": "add", "single_value": 5}),
    ("attrib_adjust_vector", {"input": FIX, "attrib": "N", "attrib_class": "point",
                              "adjust_quantity": "len", "value": [2.0, 2.0, 2.0]}),
    ("attrib_adjust_color", {"input": FIX, "attrib": "Cd", "attrib_class": "point",
                             "operation": "mult", "color": [0.5, 0.2, 0.1]}),
    ("attrib_adjust_array", {"input": FIX, "attrib": "tags", "attrib_class": "detail",
                             "array_type": "string", "sort": True}),
    ("attrib_adjust_dict", {"input": FIX, "attrib": "parms", "attrib_class": "detail",
                            "remove_keys": True, "keys": "tmp*"}),
    ("attrib_fill", {"input": FIX, "mode": "poisson", "attrib": "mass"}),
    ("attrib_fade", {"input": FIX, "fade_attrib": "fade", "fade_in": 4, "fade_out": 6}),
    ("attrib_remap", {"input": FIX, "attrib_class": "point", "in_name": "mass",
                      "input_min": 0.0, "input_max": 2.0, "output_max": 10.0}),
    ("attrib_sort", {"input": FIX, "attrib_class": "point", "attrib": "mass", "order": "descending"}),
    ("attrib_from_map", {"input": FIX, "map_source": "off", "export_attribute": "Cd2",
                         "attrib_type": "vector"}),
    ("attrib_from_parm", {"input": FIX, "method": "single", "attrib": "parms"}),
    ("attrib_mirror", {"input": FIX, "attrib": "colorattrib", "mirror_method": "plane",
                       "direction": [1.0, 0.0, 0.0]}),
    ("attrib_paint", {"input": FIX, "attrib": "mask", "attrib_type": "float", "fg_float": 1.0}),
    ("attrib_string_edit", {"input": FIX, "prims": True, "prim_list": "name",
                            "find": "piece", "replace": "chunk"}),
    ("attrib_combine", {"input": FIX, "attrib_class": "primitive", "dst_attrib": "area2",
                        "src_attrib": "area", "operation": "copy", "create_missing": True}),
]
MADE = {}
for name, p in SINGLE:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        e = errs(res["node"])
        cooked = res.get("cooked", False)
        check(cooked and not e, f"{name} cooked ({res.get('points')}pts {res.get('prims')}prim)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── 2. two-input ops (need a second source wired) ────────────────────────────────────────────────────
TWO = [
    ("attrib_find", {"input": FIX, "search": FIX, "query_attrib": "P",
                     "search_in_attrib": "P", "mode": "first"}),
    ("attrib_from_pieces", {"input": FIX, "pieces": FIX, "piece_attrib": "name",
                            "attrib": "pscale", "mode": "random", "seed": 3}),
]
for name, p in TWO:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        e = errs(res["node"])
        check(res.get("cooked", False) and not e, f"{name} cooked ({res.get('points')}pts {res.get('prims')}prim)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── 3. two-input ops WITHOUT the second input must degrade gracefully (cooked:false, no crash) ────────
try:
    res = call("attrib_find", {"input": FIX, "query_attrib": "P", "search_in_attrib": "P"})
    check(res.get("cooked") is False, "attrib_find without `search` degrades cooked:false (no crash)")
except Exception as ex:  # noqa: BLE001
    check(False, f"attrib_find no-second-input raised: {ex}")

# ── 4. param-bite checks (menu index + values actually landed) ────────────────────────────────────────
af = hou.node(MADE.get("attrib_adjust_float", ""))
if af:
    # 'mult' is index 4 in (init,set,add,sub,mult,min,max)
    check(af.parm("operation").eval() == 4, "attrib_adjust_float operation='mult' -> 4")
    check(abs(af.parm("singlevalue").eval() - 2.0) < 1e-6, "attrib_adjust_float single_value=2.0 applied")
so = hou.node(MADE.get("attrib_sort", ""))
if so:
    check(so.parm("order").eval() == 1, "attrib_sort order='descending' -> 1")
    check(so.parm("attrib").evalAsString() == "mass", "attrib_sort attrib='mass' applied")
cb = hou.node(MADE.get("attrib_combine", ""))
if cb:
    # class tokens (detail, primitive, point, vertex) -> primitive = index 1
    check(cb.parm("class").eval() == 1, "attrib_combine class='primitive' -> 1 (detail,prim,point,vertex)")
se = hou.node(MADE.get("attrib_string_edit", ""))
if se:
    fp = se.parm("from0") or se.parm("from1")
    check(fp is not None and fp.evalAsString() == "piece",
          "attrib_string_edit find->from# multiparm pair applied")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)

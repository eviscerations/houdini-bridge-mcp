"""Regression test for the WS5 W10 SOP tet/topo + SOP<->USD-bridge lane. Drives the REAL handler
dispatch path (houdini_executor _REGISTRY) headless on real mesh/tet/USD fixtures. Asserts each of the
17 endpoints builds + wires + cooks (multi-input verbs get their extra operand; the USD read/write
round-trips through a confined temp working dir), the created node is the expected type (version-
tolerant), a sample of non-default params actually land, and that a required-operand-missing verb
degrades to cooked:false without crashing. Exit 1 on ANY failure.

NOTE: tet_topo_usd_w10 is NOT yet registered in handlers/__init__.py — MAIN must add it. This test
imports it directly so it can run standalone; MAIN re-runs after registering. HMCP_WORKING_DIR is set
to a fresh temp dir BEFORE importing server so the W10c USD read/write confinement is exercised."""
import os
import sys
import tempfile

# Confined working dir for the USD file round-trip — MUST be set before importing server.
os.environ.setdefault("HMCP_WORKING_DIR", os.path.realpath(tempfile.mkdtemp(prefix="hmcp_w10_")))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  already-shipped endpoints
import houdini_executor.handlers.tet_topo_usd_w10  # noqa: F401  register THIS lane directly

R = srv._REGISTRY
WD = os.path.realpath(srv._effective_working_dir())
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


def type_ok(path, ntype):
    n = hou.node(path)
    if n is None:
        return False
    tn = n.type().name()
    return tn == ntype or tn.startswith(ntype + "::")


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────
geo = hou.node("/obj").createNode("geo", "w10_test")
box = geo.createNode("box")  # closed watertight mesh (tet input)
sph = geo.createNode("sphere"); sph.parm("type").set(2); sph.parm("rows").set(20); sph.parm("cols").set(20)
sph2 = geo.createNode("sphere", "sph2"); sph2.parm("type").set(2); sph2.parm("rows").set(16); sph2.parm("cols").set(16)
sphx = geo.createNode("xform", "sphx"); sphx.setInput(0, sph2); sphx.parm("scale").set(1.3)
pts = geo.createNode("scatter", "pts"); pts.setInput(0, sph)
if pts.parm("npts"):
    pts.parm("npts").set(50)

# a real TET mesh for tet_surface / tet_partition / tet_fracture
tet = geo.createNode("tetrahedralize", "tetfix"); tet.setInput(0, box)
tet.parm("mode").set(0)      # conform
tet.parm("output").set(1)    # tetrahedra

for n in geo.children():
    try:
        n.cook(force=True)
    except Exception:
        pass
BOX, SPH, SPHX, PTS, TET = box.path(), sph.path(), sphx.path(), pts.path(), tet.path()
check(len(box.geometry().points()) == 8, "fixture box cooked")
check(len(tet.geometry().prims()) > 0, "fixture tet mesh cooked (%d prims)" % len(tet.geometry().prims()))

# ── W10a/W10b operator verbs: build + wire + cook + correct type ───────────────────────────────────
# (name, params, expected_node_type)
CASES = [
    ("tetrahedralize", {"input": BOX, "mode": "conform", "output": "tetrahedra", "use_quality": True}, "tetrahedralize"),
    ("tet_conform", {"input": BOX, "use_base_size": True, "base_size": 0.5, "local_scaling": "constant"}, "tetconform"),
    ("tet_embed", {"input": BOX, "use_base_size": True, "base_size": 0.5}, "tetembed"),
    ("tet_layer", {"input": BOX, "direction": "interior", "thickness": 0.1, "create_tets": True}, "tetlayer"),
    ("tet_partition", {"input": TET, "boundaries": BOX, "piece_attrib": "piece"}, "tetpartition"),
    ("tet_surface", {"input": TET, "keep_points": False, "build_polysoup": False}, "tetrasurface"),
    ("tet_strata", {"input": BOX, "create_exterior_layers": True, "exterior_tet_layers": 2}, "tetstrata"),
    ("tet_fracture", {"input": TET, "voronoi": True, "visualize_pieces": True}, "tetfracture"),
    ("solid_embed", {"input": BOX, "element_scale": 0.5}, "solidembed"),
    ("topo_transfer", {"input": SPH, "target": BOX, "constraint_selection": "auto", "iterations": 2}, "topotransfer"),
    ("topo_slide", {"input": BOX, "reference_geo": SPH, "solve_mode": "slide", "blend": 0.5}, "toposlidebycurverefs"),
]
MADE = {}
for name, p, ntype in CASES:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        e = errs(res["node"])
        cooked = res.get("cooked", False)
        check(type_ok(res["node"], ntype), "%s built as %s" % (name, ntype))
        check(cooked and not e, "%s cooked (%spts %sprim)" % (name, res.get("points"), res.get("prims")))
        if e:
            print("      errors:", [str(x)[:120] for x in e])
    except Exception as ex:  # noqa: BLE001
        check(False, "%s raised: %s" % (name, ex))

# ── W10c: USD write -> read -> unpack round-trip through the confined working dir ────────────────────
usd_out = os.path.join(WD, "w10_roundtrip.usd")
written_path = None
try:
    res = call("usd_export_sop", {"input": BOX, "output": usd_out, "transform": "world",
                                  "kind_authoring": "component"})
    check(type_ok(res["node"], "usdexport"), "usd_export_sop built as usdexport")
    written_path = res.get("output")
    check(bool(res.get("written")) and written_path and os.path.exists(written_path),
          "usd_export_sop wrote a USD file (%s)" % (os.path.basename(written_path or "")))
    check(os.path.realpath(written_path).startswith(WD), "usd_export_sop output is confined to WD")
except Exception as ex:  # noqa: BLE001
    check(False, "usd_export_sop raised: %s" % ex)

# usd_import_sop: read the file back into a fresh /obj geo (unpack to polygons)
if written_path and os.path.exists(written_path):
    try:
        res = call("usd_import_sop", {"file": written_path, "name": "w10_usdin", "unpack": True,
                                      "geometry_type": "polygons", "traversal": "std:components"})
        check(type_ok(res["sop"], "usdimport"), "usd_import_sop built as usdimport")
        e = errs(res["sop"])
        cooked = hou.node(res["sop"]).geometry() is not None
        check(cooked and not e, "usd_import_sop cooked from the written file")
        if e:
            print("      errors:", [str(x)[:120] for x in e])
    except Exception as ex:  # noqa: BLE001
        check(False, "usd_import_sop raised: %s" % ex)

    # packed import -> unpack_usd
    try:
        resp = call("usd_import_sop", {"file": written_path, "name": "w10_usdin_packed", "unpack": False})
        packed_sop = resp["sop"]
        res = call("unpack_usd", {"input": packed_sop, "output": "polygons", "delete_original": False})
        check(type_ok(res["node"], "unpackusd"), "unpack_usd built as unpackusd")
        check(res.get("cooked", False) and not errs(res["node"]),
              "unpack_usd cooked (%spts %sprim)" % (res.get("points"), res.get("prims")))
    except Exception as ex:  # noqa: BLE001
        check(False, "unpack_usd raised: %s" % ex)
else:
    check(False, "usd_import_sop / unpack_usd SKIPPED — no USD file was written")

# usd_configure_* operators (pure operators, no file write)
CONF = [
    ("usd_configure_sop", {"input": BOX, "path_prefix": "/geo", "kind_authoring": "component",
                           "topology": "static"}, "usdconfigure"),
    ("usd_configure_geometry", {"input": BOX, "prim_path": "/geo/box", "subdivision_scheme": "catmullClark",
                                "visibility": "inherit"}, "usdconfiguregeometry"),
    ("usd_configure_prims_from_points", {"input": PTS, "prim_type": "Sphere", "prim_path": "/pts",
                                         "color": [1.0, 0.5, 0.0], "radius": 0.1}, "usdconfigureprimsfrompoints"),
]
for name, p, ntype in CONF:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        e = errs(res["node"])
        check(type_ok(res["node"], ntype), "%s built as %s" % (name, ntype))
        check(res.get("cooked", False) and not e, "%s cooked (%spts %sprim)" %
              (name, res.get("points"), res.get("prims")))
        if e:
            print("      errors:", [str(x)[:120] for x in e])
    except Exception as ex:  # noqa: BLE001
        check(False, "%s raised: %s" % (name, ex))

# ── param-bite checks (values actually landed) ─────────────────────────────────────────────────────
th = hou.node(MADE.get("tetrahedralize", ""))
if th:
    # mode menu (conform,refine,convexhull,detect) -> conform = index 0; output tetrahedra = index 1
    check(th.parm("mode").eval() == 0, "tetrahedralize mode='conform' -> index 0")
    check(th.parm("output").eval() == 1, "tetrahedralize output='tetrahedra' -> index 1")
tl = hou.node(MADE.get("tet_layer", ""))
if tl:
    check(tl.parm("direction").eval() == 0, "tet_layer direction='interior' -> index 0")
    check(abs(tl.parm("thickness").eval() - 0.1) < 1e-6, "tet_layer thickness=0.1 applied")
tt = hou.node(MADE.get("topo_transfer", ""))
if tt:
    check(tt.parm("constraintselection").eval() == 0, "topo_transfer constraint_selection='auto' -> index 0")
uc = hou.node(MADE.get("usd_configure_sop", ""))
if uc:
    check(uc.parm("kindschema").eval() == "component", "usd_configure_sop kind_authoring='component' (string token)")
    check(uc.parm("enable_kindschema").eval() == 1, "usd_configure_sop enable_kindschema flipped on")
up = hou.node(MADE.get("usd_configure_prims_from_points", ""))
if up:
    check(abs(up.parm("colorr").eval() - 1.0) < 1e-6 and abs(up.parm("colorg").eval() - 0.5) < 1e-6,
          "usd_configure_prims_from_points color=[1,0.5,0] applied")

# ── graceful degradation: tet_partition with NO boundaries operand must not crash ───────────────────
try:
    res = call("tet_partition", {"input": TET})  # missing required `boundaries`
    check(res.get("node") is not None, "tet_partition without boundaries returned a node (no crash)")
except Exception as ex:  # noqa: BLE001
    check(False, "tet_partition without boundaries raised: %s" % ex)

print("\n==== %d ok / %d FAIL ====" % (len(OK), len(FAIL)))
sys.exit(1 if FAIL else 0)

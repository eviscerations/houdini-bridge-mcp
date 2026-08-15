"""Locked-in regression tests for the bugs the A1 long-chain hunt found + fixed.
Each block reproduces the exact failing condition and asserts the fix holds, so none can silently
regress. Run under hython."""
import os
import sys
import tempfile

os.environ.setdefault("HMCP_WORKING_DIR", os.path.realpath(tempfile.mkdtemp(prefix="hmcp_a1reg_")))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
import hou  # noqa: E402,F401
from houdini_executor import server  # noqa: E402,F401
from houdini_executor.handlers import model as MODEL  # noqa: E402
from houdini_executor.handlers import instance as INST  # noqa: E402
from houdini_executor.handlers import weather as WX  # noqa: E402
from houdini_executor.handlers import material as MAT  # noqa: E402
from houdini_executor.handlers import sim as SIM  # noqa: E402

FAIL = []


def chk(label, cond):
    print(("  OK  " if cond else " FAIL ") + label)
    if not cond:
        FAIL.append(label)


# FIX 1 — bridge_input: a two-input op accepts a cross-network second operand (boolean subtract).
A = MODEL.create_primitive({"shape": "box", "size": [2, 2, 2], "name": "reg_A"})
B = MODEL.create_primitive({"shape": "box", "size": [1, 1, 3], "name": "reg_B"})
try:
    rb = MODEL.boolean({"input": A.get("sop") or A["node"], "operation": "subtract",
                        "input_b": B.get("sop") or B["node"], "name": "reg_bool"})
    bn = hou.node(rb["node"]); bn.cook(force=True)
    chk("FIX1 boolean cross-net operand cooks non-empty", not bn.errors() and len(bn.geometry().prims()) > 0)
except Exception as e:  # noqa: BLE001
    chk("FIX1 boolean cross-net operand did not raise (%r)" % e, False)

# FIX 2 — cloud_shape voxelsize actually changes resolution (was inert).
def _cloud_voxels(vs):
    r = WX.cloud_shape({"name": "reg_cv%s" % str(vs).replace(".", "_"), "voxelsize": vs, "rasterize": True})
    n = hou.node(r["output"]); n.cook(force=True)
    v = [p for p in n.geometry().prims() if p.type() == hou.primType.VDB][0]
    return v.intrinsicValue("activevoxelcount")
chk("FIX2 cloud_shape voxelsize bites (fine>coarse active voxels)", _cloud_voxels(0.1) > _cloud_voxels(1.0))

# FIX 5 — shader_set_param scalar on a color3 param broadcasts to the active tuple.
lib = MAT.material_graph_create({"name": "reg_lib"})
rmp = MAT.shader_node_add({"library": lib["library"], "node_type": "mtlxramplr", "signature": "color3", "name": "reg_rmp"})
sp = MAT.shader_set_param({"node": rmp["node"], "param": "valuel", "value": 0.42})
chk("FIX5 scalar-on-color3 broadcasts to _color3 tuple", sp.get("param") == "valuel_color3" and sp.get("broadcast") is True)

# FIX 8 — instance.py surfaces a real cook error instead of an opaque NoneType crash.
grid = MODEL.create_primitive({"shape": "grid", "name": "reg_grid"})
box = MODEL.create_primitive({"shape": "box", "name": "reg_cpsrc"})
cp = INST.copy_to_points({"source": box.get("sop") or box["node"], "target": grid.get("sop") or grid["node"]})
raised = None
try:
    INST.pack({"input": cp["node"], "pack_by_name": True})
except Exception as e:  # noqa: BLE001
    raised = repr(e)
chk("FIX8 pack surfaces node error (not opaque NoneType)",
    raised is not None and "failed to cook" in raised and "NoneType" not in raised)

# FIX 9 — rbd_material_fracture returns a true `pieces` count.
wall = MODEL.create_primitive({"shape": "box", "size": [6, 4, 1], "name": "reg_wall"})
fr = SIM.rbd_material_fracture({"input": wall.get("sop") or wall["node"], "materialtype": "concrete",
                               "pieces": 12, "seed": 3, "name": "reg_frac"})
chk("FIX9 rbd_material_fracture returns literal pieces==12", fr.get("pieces") == 12)

# FIX 10 — polywire auto-tessellates a NURBS curve into a real tube.
nc = MODEL.create_curve({"points": [[0, 0, 0], [1, 1, 0], [2, 0, 0], [3, 1, 0]], "curve_type": "nurbs", "name": "reg_nc"})
pw = MODEL.polywire({"input": nc.get("sop") or nc["node"], "radius": 0.1, "divisions": 6})
faces = len([p for p in hou.node(pw["node"]).geometry().prims() if p.type() == hou.primType.Polygon])
chk("FIX10 polywire on NURBS produces a tube (faces>0)", faces > 0)

# FIX 11 — copy_to_points carries a target POINT attribute (Cd) onto the copies (Attributes-from-
# Target multiparm; row created before the pattern is set, non-empty pattern). Target Cd must be a
# POINT attr (class=2) — the original mis-diagnosis used a detail Cd which correctly transfers nothing.
_g = hou.node((MODEL.create_primitive({"shape": "grid", "name": "reg_ctp_tgt"}).get("sop")))
_wr = _g.parent().createNode("attribwrangle", "reg_ctp_cd"); _wr.setInput(0, _g)
_wr.parm("class").set(2); _wr.parm("snippet").set("@Cd = set(1,0,0);")
_bx = MODEL.create_primitive({"shape": "box", "name": "reg_ctp_src"})
_r = INST.copy_to_points({"source": _bx.get("sop") or _bx["node"], "target": _wr.path()})
chk("FIX11 copy_to_points transfers target Cd onto copies", hou.node(_r["node"]).geometry().findPointAttrib("Cd") is not None)

# FIX 7 — sim_vellum built net actually solves (constraint geometry on solver input 1).
vel = SIM.sim_vellum({"name": "reg_cloth", "vtype": "cloth", "substeps": 3})
solv = hou.node(vel["solver"])
try:
    for f in range(1, 6):
        hou.setFrame(f)
        solv.cook(force=True)
    ys = [p.position()[1] for p in solv.geometry().points()]
    cy = sum(ys) / len(ys) if ys else None
    chk("FIX7 sim_vellum solves + cloth falls", not solv.errors() and cy is not None and cy < -0.01)
except Exception as e:  # noqa: BLE001
    chk("FIX7 sim_vellum solves (raised %r)" % e, False)

print("\nRESULT:", "ALL PASS" if not FAIL else ("FAILURES: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)

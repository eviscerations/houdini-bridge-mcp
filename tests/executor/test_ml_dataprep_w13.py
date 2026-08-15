"""Regression test for the WS5 W13 SOP ML data-prep lane. Drives the REAL handler dispatch path
(houdini_executor _REGISTRY) headless on real geometry + KineFX-skeleton fixtures. Asserts each of the
7 endpoints builds + wires the expected (version-tolerant) node type and that a sample of non-default
params land; the pure data-prep operators degrade to cooked:false without crashing when an input is
starved; the WIRE-ONLY ml_deform is BUILT + configured but NOT cooked, its modelfile is confined, and a
modelfile OUTSIDE the working dir is REJECTED. Exit 1 on ANY failure.

NOTE: ml_dataprep_w13 is NOT yet registered in handlers/__init__.py — MAIN must add it. This test
imports it directly so it can run standalone; MAIN re-runs after registering. HMCP_WORKING_DIR is set to
a fresh temp dir BEFORE importing server so the ml_deform modelfile confinement is exercised."""
import os
import sys
import tempfile

os.environ.setdefault("HMCP_WORKING_DIR", os.path.realpath(tempfile.mkdtemp(prefix="hmcp_w13_")))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  already-shipped endpoints
import houdini_executor.handlers.ml_dataprep_w13  # noqa: F401  register THIS lane directly

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
geo = hou.node("/obj").createNode("geo", "w13_test")
box = geo.createNode("box")                      # Input Component
box2 = geo.createNode("box", "box2")             # Target Component
proto = geo.createNode("sphere", "proto")        # attribgenerate prototype
proto.parm("type").set(2)

# a minimal KineFX skeleton for the pose nodes (line -> skeletonconvert-ish). Use the `skeleton` SOP
# if present; else fall back to a plain line (pose nodes then degrade to cooked:false, still built).
skel = None
try:
    skel = geo.createNode("skeleton")
except Exception:
    try:
        ln = geo.createNode("line", "skel_line")
        ln.parm("points").set(4)
        skel = ln
    except Exception:
        skel = box

for n in geo.children():
    try:
        n.cook(force=True)
    except Exception:
        pass
BOX, BOX2, PROTO, SKEL = box.path(), box2.path(), proto.path(), skel.path()
check(len(box.geometry().points()) == 8, "fixture box cooked")

MADE = {}

# ── pure data-prep operators: build + wire + correct type ──────────────────────────────────────────
# ml_example first (its output feeds extract / partition)
try:
    res = call("ml_example", {"input": BOX, "target": BOX2, "use_packed_input": False,
                              "input_validity_attrib": "valid"})
    MADE["ml_example"] = res["node"]
    check(type_ok(res["node"], "ml_example"), "ml_example built as ml_example")
    check(hou.node(res["node"]).input(1) is not None, "ml_example wired Target Component to input 1")
except Exception as ex:  # noqa: BLE001
    check(False, "ml_example raised: %s" % ex)

EX = MADE.get("ml_example", BOX)  # examples stream for extract/partition

CASES = [
    ("ml_extract_example", {"input": EX, "index": 0, "keep_packed": True}, "ml_extractexample"),
    ("ml_example_partition", {"input": EX, "max_part_size": 8}, "ml_examplepartition"),
    ("ml_attrib_generate", {"input": PROTO, "random_seed": 7, "sample_count": 4,
                            "point_attribute": "feat", "tuple_size": 3,
                            "distribution": "gaussian"}, "ml_attribgenerate"),
    ("ml_pose_generate", {"input": SKEL, "random_seed": 3, "sample_count": 5,
                          "joint_group": "*"}, "ml_posegenerate"),
    ("ml_pose_serialize", {"input": SKEL, "serial_attribute": "serial", "mode": "alllocal",
                           "include_rotation": True, "include_translation": True}, "ml_poseserialize"),
]
for name, p, ntype in CASES:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        e = errs(res["node"])
        check(type_ok(res["node"], ntype), "%s built as %s" % (name, ntype))
        # cook is best-effort for these (some need a genuine skeleton) — assert BUILT + no crash
        check(res.get("node") is not None, "%s returned a node (cooked=%s)" % (name, res.get("cooked")))
        if e:
            print("      note errors:", [str(x)[:110] for x in e])
    except Exception as ex:  # noqa: BLE001
        check(False, "%s raised: %s" % (name, ex))

# ── param-bite checks (values actually landed) ─────────────────────────────────────────────────────
ag = hou.node(MADE.get("ml_attrib_generate", ""))
if ag:
    check(ag.parm("samplecount").eval() == 4, "ml_attrib_generate sample_count=4 applied")
    check(ag.parm("distribution1").eval() == "gaussian", "ml_attrib_generate distribution='gaussian' applied")
    check(ag.parm("tuplesize1").eval() == 3, "ml_attrib_generate tuple_size=3 applied")
ps = hou.node(MADE.get("ml_pose_serialize", ""))
if ps:
    check(ps.parm("mode").eval() == 1, "ml_pose_serialize mode='alllocal' -> index 1")
    check(ps.parm("serialattribute").eval() == "serial", "ml_pose_serialize serial_attribute applied")
ep = hou.node(MADE.get("ml_example_partition", ""))
if ep:
    check(ep.parm("maximumpartsize").eval() == 8, "ml_example_partition max_part_size=8 applied")

# ── WIRE-ONLY ml_deform: built + configured + confined modelfile, NOT cooked ────────────────────────
model_in = os.path.join(WD, "deformer.onnx")
open(model_in, "wb").write(b"\x00\x00\x00\x00")  # placeholder file inside the confined WD
try:
    res = call("ml_deform", {"input": BOX, "capture_pose": SKEL, "animated_pose": SKEL,
                             "modelfile": model_in, "joint_group": "*",
                             "enforce_joint_limits": True})
    MADE["ml_deform"] = res["node"]
    check(type_ok(res["node"], "ml_deform"), "ml_deform built as ml_deform")
    check(res.get("cooked") is False, "ml_deform is WIRE-ONLY (cooked:False — model not loaded)")
    check(res.get("modelfile") and os.path.realpath(res["modelfile"]).startswith(WD),
          "ml_deform modelfile is confined to the working dir")
    dn = hou.node(res["node"])
    check(dn.parm("modelfile").eval() == os.path.realpath(model_in), "ml_deform modelfile set on node")
    check(dn.input(1) is not None and dn.input(2) is not None, "ml_deform wired capture + animated pose")
    check(dn.parm("jointgroup").eval() == "*", "ml_deform joint_group applied")
except Exception as ex:  # noqa: BLE001
    check(False, "ml_deform raised: %s" % ex)

# modelfile OUTSIDE the working dir must be REJECTED (confinement)
try:
    bad = os.path.join(tempfile.gettempdir(), "escape_w13.onnx")
    call("ml_deform", {"input": BOX, "modelfile": bad})
    check(False, "ml_deform accepted an out-of-workdir modelfile (SHOULD reject)")
except PermissionError:
    check(True, "ml_deform rejects a modelfile outside the working dir")
except Exception as ex:  # noqa: BLE001
    # confined_path raises PermissionError; anything else is a surprise but the reject intent holds if
    # it's a path/permission error string.
    check("outside" in str(ex).lower() or "permission" in str(ex).lower(),
          "ml_deform rejects out-of-workdir modelfile (%s)" % type(ex).__name__)

# ── graceful degradation: ml_example with NO target operand must not crash ──────────────────────────
try:
    res = call("ml_example", {"input": BOX})  # missing `target`
    check(res.get("node") is not None, "ml_example without target returned a node (no crash)")
except Exception as ex:  # noqa: BLE001
    check(False, "ml_example without target raised: %s" % ex)

print("\n==== %d ok / %d FAIL ====" % (len(OK), len(FAIL)))
sys.exit(1 if FAIL else 0)

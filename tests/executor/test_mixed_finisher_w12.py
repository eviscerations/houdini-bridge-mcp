"""Regression test for the WS5 W12 mixed-finisher lane. Drives the REAL handler dispatch path
(houdini_executor _REGISTRY) headless in the correct context for each of the four sub-lanes:

  W12a — 11 /obj objects (rivet/sticky/lights/cameras): build + version-tolerant type + a param bite.
  W12b — 3 /out USD utility ROPs (usdstitch/usdstitchclips/usdzip): build + confined output param set,
         and ASSERT the node was NOT executed (the output file must NOT exist) — WIRE-ONLY.
  W12c — 12 /stage LOPs (shot editorial + sequence I/O + USD constraints): build + type; constraints
         degrade to cooked:false gracefully when a referenced prim is absent (no crash). shot_output is
         WIRE-ONLY (built, not executed).
  W12d — 9 CHOPs (anim utilities): build + type; generators cook standalone, operators chain onto an
         input CHOP; each degrades to cooked:false gracefully without crashing.

NOTE: mixed_finisher_w12 is NOT yet registered in handlers/__init__.py — MAIN adds it. This test imports
it directly so it can run standalone. HMCP_WORKING_DIR is a fresh temp dir set BEFORE importing server so
the confined file surfaces are exercised. Exit 1 on ANY failure."""
import os
import sys
import tempfile

os.environ.setdefault("HMCP_WORKING_DIR", os.path.realpath(tempfile.mkdtemp(prefix="hmcp_w12_")))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  already-shipped endpoints
import houdini_executor.handlers.mixed_finisher_w12  # noqa: F401  register THIS lane directly

R = srv._REGISTRY
WD = os.path.realpath(srv._effective_working_dir())
FAIL = []
OK = []


def call(name, params):
    return R[name]["fn"](params)


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
geo = hou.node("/obj").createNode("geo", "w12_geo")
grid = geo.createNode("grid")
grid.cook(force=True)
GRID = grid.path()

stage = hou.node("/stage") or hou.node("/").createNode("lopnet", "stage")
base_sphere = stage.createNode("sphere", "w12_base")
base_sphere.cook(force=True)
BASE = base_sphere.path()

chnet = hou.node("/obj").createNode("chopnet", "w12_chops")
wave = chnet.createNode("wave")   # a real generator CHOP to feed the operator CHOPs
wave.cook(force=True)
WAVE = wave.path()

check(hou.node(GRID) is not None, "fixture grid SOP built")
check(hou.node(BASE) is not None, "fixture /stage sphere built")
check(hou.node(WAVE) is not None, "fixture wave CHOP built")


# ── W12a — /obj objects ────────────────────────────────────────────────────────────────────────────
# (endpoint, params, expected_type)
W12A = [
    ("rivet", {"name": "w12_rivet", "rivet_geo": GRID, "t": [1, 0, 0]}, "rivet"),
    ("sticky", {"name": "w12_sticky", "sticky_geo": GRID, "uv": [0.5, 0.5]}, "sticky"),
    ("blend_sticky", {"name": "w12_blendsticky", "orient": True}, "blendsticky"),
    ("three_point_light", {"name": "w12_3pt", "key_intensity": 2.0,
                           "look_at_target": [0, 1, 0]}, "three_point_light"),
    ("indirect_light", {"name": "w12_indirect", "dimmer": 0.5}, "indirectlight"),
    ("ambient_light", {"name": "w12_ambient", "color": [0.2, 0.2, 0.3], "intensity": 0.5}, "ambient"),
    ("environment_fog", {"name": "w12_fog", "scale": 2.0}, "fog"),
    ("reference_image", {"name": "w12_refimg", "image_file": os.path.join(WD, "ref.pic"),
                         "orient": "front", "alpha": 0.5}, "refimage"),
    ("stereo_camera", {"name": "w12_stereo", "left_cam": "/obj/camL"}, "stereocam"),
    ("stereo_camera_rig", {"name": "w12_stereorig", "interaxial": 0.06, "focal": 50}, "stereocamrig"),
    ("vr_camera", {"name": "w12_vr", "projection": "sphere", "eye_separation": 0.065}, "vrcam"),
]
MADE = {}
for name, p, ntype in W12A:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        check(type_ok(res["node"], ntype), "W12a %s built as %s" % (name, ntype))
    except Exception as ex:  # noqa: BLE001
        check(False, "W12a %s raised: %s" % (name, ex))

# param bites (W12a)
r = hou.node(MADE.get("rivet", ""))
if r:
    check(r.parm("rivetsop").eval() == GRID, "rivet rivet_geo landed")
    check(abs(r.parmTuple("t").eval()[0] - 1.0) < 1e-6, "rivet t=[1,0,0] landed")
amb = hou.node(MADE.get("ambient_light", ""))
if amb:
    check(abs(amb.parm("light_intensity").eval() - 0.5) < 1e-6, "ambient_light intensity landed")
ref = hou.node(MADE.get("reference_image", ""))
if ref:
    check(os.path.realpath(ref.parm("copfile").eval()).startswith(WD),
          "reference_image image_file confined to WD")


# ── W12b — /out USD utility ROPs (WIRE-ONLY: built, NOT executed) ────────────────────────────────────
stitch_out = os.path.join(WD, "w12_stitch_out.usd")
zip_out = os.path.join(WD, "w12_pkg.usdz")
tmpl_out = os.path.join(WD, "w12_clip.topology.usd")
in_a = os.path.join(WD, "clip_a.usd")
in_b = os.path.join(WD, "clip_b.usd")

W12B = [
    ("usd_stitch", {"name": "w12_stitch", "input_files": [in_a, in_b], "output": stitch_out},
     "usdstitch", "outfile1", stitch_out),
    ("usd_stitch_clips", {"name": "w12_stitchclips", "input_files": [in_a, in_b],
                          "output_template": tmpl_out, "clip_path": "/clip"},
     "usdstitchclips", "outtemplatefile1", tmpl_out),
    ("usd_zip", {"name": "w12_zip", "input_files": [in_a, in_b], "output": zip_out,
                 "arkit_asset": True}, "usdzip", "outfile1", zip_out),
]
for name, p, ntype, outparm, outval in W12B:
    try:
        res = call(name, p)
        node = hou.node(res["node"])
        check(type_ok(res["node"], ntype), "W12b %s built as %s" % (name, ntype))
        check(node.parm("infile1").eval().startswith(WD) if node.parm("infile1") else False,
              "W12b %s infile1 confined to WD" % name)
        op = node.parm(outparm)
        check(op is not None and os.path.realpath(op.eval()) == os.path.realpath(outval),
              "W12b %s %s set to the confined output" % (name, outparm))
        check(res.get("rendered") is False, "W12b %s returned rendered:False (WIRE-ONLY)" % name)
        check(not os.path.exists(outval), "W12b %s did NOT execute (output absent)" % name)
    except Exception as ex:  # noqa: BLE001
        check(False, "W12b %s raised: %s" % (name, ex))


# ── W12c — /stage LOPs ───────────────────────────────────────────────────────────────────────────
shot_out = os.path.join(WD, "w12_shot.usd")
clip_load = os.path.join(WD, "seq_$F.usd")
geo_seq = os.path.join(WD, "geo_$F.bgeo.sc")
W12C = [
    ("shot_load", {"name": "w12_shotload", "active_shots": "*"}, "shotload", None),
    ("shot_output", {"name": "w12_shotout", "input": BASE, "output": shot_out,
                     "output_mode": "render", "save_style": "flattenalllayers"}, "shotoutput", None),
    ("shot_layer_edit", {"name": "w12_shotlayer", "input": BASE, "target_layer": "shot",
                         "create_new_layer": True, "new_layer": "edit"}, "shotlayeredit", None),
    ("usd_value_clip", {"name": "w12_valueclip", "input": BASE, "primpath": "/clip",
                        "clip_files": [in_a, in_b], "clip_set": "default"}, "valueclip", None),
    ("usd_geometry_sequence", {"name": "w12_geoseq", "input": BASE, "file": geo_seq,
                               "primpath": "/geo", "missing_frame": "empty"}, "geometrysequence", None),
    ("usd_geo_clip_sequence", {"name": "w12_geoclip", "input": BASE, "primpath": "/geo",
                               "load_clip_file": clip_load, "sample_behavior": "single"},
     "geoclipsequence", None),
    ("usd_blend_constraint", {"name": "w12_blendc", "input": BASE, "source": "/w12_base",
                              "target": "/w12_base", "method": 0}, "blendconstraint", None),
    ("usd_followpath_constraint", {"name": "w12_fpc", "input": BASE, "source": "/w12_base",
                                   "pos": 0.5, "doposition": True}, "followpathconstraint", None),
    ("usd_lookat_constraint", {"name": "w12_lac", "input": BASE, "source": "/w12_base",
                               "target_pos": [0, 5, 0], "up": "yaxis"}, "lookatconstraint", None),
    ("usd_parent_constraint", {"name": "w12_pac", "input": BASE, "source": "/w12_base",
                               "target": "/w12_base", "position": True, "method": "byframe"},
     "parentconstraint", None),
    ("usd_points_constraint", {"name": "w12_ptc", "input": BASE, "source": "/w12_base",
                               "target": "/w12_base", "mode": 0}, "pointsconstraint", None),
    ("usd_surface_constraint", {"name": "w12_sfc", "input": BASE, "source": "/w12_base",
                                "target": "/w12_base", "uv": [0.5, 0.5], "mode": 0},
     "surfaceconstraint", None),
]
for name, p, ntype, _x in W12C:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        check(type_ok(res["node"], ntype), "W12c %s built as %s" % (name, ntype))
    except Exception as ex:  # noqa: BLE001
        check(False, "W12c %s raised: %s" % (name, ex))

# W12c param bites + WIRE-ONLY assertion
so = hou.node(MADE.get("shot_output", ""))
if so:
    check(os.path.realpath(so.parm("lopoutput").eval()) == os.path.realpath(shot_out),
          "shot_output lopoutput confined to the requested path")
    check(not os.path.exists(shot_out), "shot_output did NOT execute (output absent) — WIRE-ONLY")
vc = hou.node(MADE.get("usd_value_clip", ""))
if vc and vc.parm("clipfile1") is not None:
    check(vc.parm("clipfile1").eval().startswith(WD), "usd_value_clip clip_files confined to WD")
gs = hou.node(MADE.get("usd_geometry_sequence", ""))
if gs:
    check(gs.parm("file").eval().replace("\\", "/").startswith(WD.replace("\\", "/")),
          "usd_geometry_sequence file confined to WD")
# snippet params must NOT be enabled (DEFERRED — data-only guarantee)
for cname, snip in [("usd_followpath_constraint", "usepositionsnippet"),
                    ("usd_points_constraint", "useweightssnippet"),
                    ("usd_surface_constraint", "usepositionsnippet")]:
    cn = hou.node(MADE.get(cname, ""))
    if cn and cn.parm(snip) is not None:
        check(cn.parm(snip).eval() == 0, "%s left %s OFF (VEX snippet deferred)" % (cname, snip))


# ── W12d — CHOPs ───────────────────────────────────────────────────────────────────────────────────
W12D_OPS = [   # operators: chained onto the WAVE input CHOP
    ("chop_footplant", {"name": "w12_footplant", "input": WAVE, "method": "speed",
                        "speed_threshold": 0.1}, "footplant"),
    ("chop_iksolver", {"name": "w12_iksolver", "input": WAVE, "solver_type": "inverse",
                       "ik_dampen": 0.1}, "iksolver"),
    ("chop_transform_chain", {"name": "w12_xchain", "input": WAVE, "in_rord": "xyz"},
     "transformchain"),
    ("chop_export_transforms", {"name": "w12_exportxf", "input": WAVE, "mode": "xform"},
     "exporttransforms"),
    ("chop_blendpose", {"name": "w12_blendpose", "input": WAVE, "interp": "rbf",
                        "kernel": "gaussian"}, "blendpose"),
    ("chop_stashpose", {"name": "w12_stashpose", "input": WAVE, "srselect": "first"}, "stashpose"),
]
W12D_GEN = [   # generators: fresh chopnet
    ("chop_inversekin", {"name": "w12_ik", "solver_type": "rest", "ik_dampen": 0.2}, "inversekin"),
    ("chop_extract_bone_transforms", {"name": "w12_ebt", "world_transforms": True,
                                      "range": "full"}, "extractbonetransforms"),
    ("chop_extract_pose_drivers", {"name": "w12_epd", "channel_prefix": "drv_",
                                   "range": "full"}, "extractposedrivers"),
]
for name, p, ntype in W12D_OPS + W12D_GEN:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        check(type_ok(res["node"], ntype), "W12d %s built as %s" % (name, ntype))
    except Exception as ex:  # noqa: BLE001
        check(False, "W12d %s raised: %s" % (name, ex))

# W12d param bite
xc = hou.node(MADE.get("chop_transform_chain", ""))
if xc:
    check(xc.parm("inrOrd").eval() == 0, "chop_transform_chain in_rord='xyz' -> index 0")


print("\n==== %d ok / %d FAIL ====" % (len(OK), len(FAIL)))
sys.exit(1 if FAIL else 0)

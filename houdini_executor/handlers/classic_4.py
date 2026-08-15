"""KineFX / Classic deformation-finish & mocap-source — data-only handlers. Params
verified against live H21.0.671; every non-WIRE-ONLY endpoint proven
with a headless cook over the reusable fixture (a 4-joint skeleton + a
proximity-captured tube).

Archetypes (mirror the Labs A/B/C mapping):
  A source  : neuron_mocap (labs::neuron_mocap) + rokoko_mocap (labs::rokoko_mocap) — 0-input live-mocap
              SOURCE nodes. They CONFIGURE a mocap stream/recording (IP / port / actor / recording file)
              as DATA; the connect / record / calibrate BUTTONS are NEVER pressed, so cooking one opens
              no socket and writes no file — it emits the (empty, until a human connects) skeleton stream.
  B chain   : post_anim_deform (labs::post_anim_deform) — in0=deforming, in1=rest, in2=deformed geometry.
              The correct input index is wired explicitly (child_after for input0, bridge_input(index=..)
              for the operands). A cook that "succeeds" with the wrong input wired is WRONG. (`deformmeta`
              and `capturepaintcore` are SKIPPED.)
  WIRE-ONLY : dembones_skinning_bake (dembones_skinningconverter::1.0, the native SOP DemBones writer) +
              dembones_skinning_external (labs::dembones_skinningconverter, the SideFX Labs external-
              executable variant) — each built + wired + confined + clamped but NEVER executed (mirrors
              tree.py maps_baker / classic_1 dembones_skinning_export). exported=False.

SECURITY (data-only):
  * No code/callback parm is ever set or exposed.
  * `rokoko_mocap`'s `api_key` is a CREDENTIAL/secret parm — it is NEVER set or exposed. Its
    `commands_folder` is a UI parm-FOLDER (FolderSet), not a code parm (enumerate keyword false-positive)
    and carries no value.
  * The only real file surfaces — DemBones' `sAnimatedCache`/`sBindPoseFBX` (reads), `sOutputFile`/
    `sExportFile` (writes) and `executablecache` (the external DemBones binary directory), and rokoko's
    `recording_filename` — are each routed through confined_path() so I/O stays inside the working dir.
  * mocap `neuron_ip`/`neuron_port`/`rokoko_ip`/`rokoko_port` are network-address DATA strings; no socket
    is opened on cook (the connect buttons are never pressed).
  * cost-exponential DemBones levers (bone / iteration counts) are hard-clamped.
"""

import hou
from houdini_executor.server import clamp, child_after, bridge_input, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────




def _cooked(n):
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


def _fresh_geo(name):
    """Create a fresh /obj geo to host a 0-input SOURCE SOP (fails on name collision, mirroring the
    capture_region source pattern)."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("geo", name)


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_NEURON_FORMAT = ("0", "1", "2")


# NOTE: `capturepaintcore` ("Capture Paint Core") is SKIPPED. It is the low-level
# internal of the interactive Capture Paint tool (its user-facing HDA `kinefx::jointcapturepaint` is
# ALREADY wrapped as `joint_capture_paint`). Cooked headless it REQUIRES input 0 point normals + input 1
# rest skeleton + input 2 animated pose + a valid `cregion` target, and with all of those supplied it
# hard-CRASHES hython (segfault, H21.0.671) — a crash cannot be certified as a green cook (mirrors the
# poseweightinterp SKIP). Redundant + uncookable -> not shipped.


# NOTE: `deformmeta` (type `deformmeta`, "Deform Metaball") is SKIPPED. It deforms
# geometry captured with the legacy metaball-skinning workflow and errors ("Input ... is missing the
# 'metaCaptGroups' detail attribute") when cooked over the wave fixture. A valid input requires a
# metaball-capture fixture (metaball OBJs referenced by `capturemeta`'s `captobjects` path pattern, then
# `metagroups`) that the shared wave fixture (bone-capture only) does not provide. No green cook -> not
# shipped; revivable once a metaball-capture fixture exists.


# ── 2. post_anim_deform (labs::post_anim_deform::1.0) — B chain: in0=deforming,in1=rest,in2=deformed ─
@endpoint("post_anim_deform")
def post_anim_deform(params):
    """Labs Post Animation Deform (labs::post_anim_deform) — applies the deformation delta between a rest
    mesh (input 1) and its deformed version (input 2) onto a matching `deforming` mesh (input 0),
    optionally transferring an orientation/transform attribute. Used to bake sim/anim deltas back onto a
    detailed mesh. SECURITY: attribute names only; no file/code surface."""
    n = child_after(params["deforming"], "labs::post_anim_deform::1.0", params.get("name"))
    bridge_input(n, params["rest"], index=1, name_hint="rest")
    bridge_input(n, params["deformed"], index=2, name_hint="deformed")
    if "normal_attrib" in params:
        _try_set(n, "normal", str(params["normal_attrib"]))
    if "attrib_to_transform" in params:
        _try_set(n, "attribtotrans", str(params["attrib_to_transform"]))
    if "do_transform" in params:
        _try_set(n, "dotransform", bool(params["do_transform"]))
    if "transform_attrib" in params:
        _try_set(n, "xform", str(params["transform_attrib"]))
    if "delete_transform_attrib" in params:
        _try_set(n, "deletexform", bool(params["delete_transform_attrib"]))
    return _cooked(n)


# ── 4. neuron_mocap (labs::neuron_mocap) — A source: 0-input Perception-Neuron stream config ──────
@endpoint("neuron_mocap")
def neuron_mocap(params):
    """Labs Neuron Mocap (labs::neuron_mocap) — a 0-input SOURCE that configures a Perception Neuron
    live-mocap stream (character name / IP / port / data format / actor index) and emits the received
    skeleton. This data-only endpoint sets the stream configuration only; the `connect_server` /
    `disconnect_server` buttons are NEVER pressed, so cooking opens no socket (empty until a human
    connects). SECURITY: IP/port are network-address DATA strings; no file/code surface."""
    geo = _fresh_geo(params.get("name"))
    n = geo.createNode("labs::neuron_mocap")
    if "character_name" in params:
        _try_set(n, "charactername", str(params["character_name"]))
    if "ip" in params:
        _try_set(n, "neuron_ip", str(params["ip"]))
    if "port" in params:
        _try_set(n, "neuron_port", str(params["port"]))
    if "data_format" in params:
        _menu_set(n, "neuron_data_format", str(params["data_format"]), _NEURON_FORMAT)
    if "actor_index" in params:
        _try_set(n, "neuron_actor_index", int(clamp(int(params["actor_index"]), 0, 64)))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. rokoko_mocap (labs::rokoko_mocap) — A source: 0-input Rokoko Smartsuit stream config ───────
@endpoint("rokoko_mocap")
def rokoko_mocap(params):
    """Labs Rokoko Mocap (labs::rokoko_mocap) — a 0-input SOURCE that configures a Rokoko Smartsuit
    live-mocap stream (IP / port / actor / suit name) and optional recording file, and emits the received
    skeleton. This data-only endpoint sets configuration only; the connect / calibrate / record / unicast
    BUTTONS are NEVER pressed, so cooking opens no socket and writes no file. SECURITY: the `api_key`
    credential parm is NEVER set or exposed; `recording_filename` is confined to the working dir; IP/port
    are network-address DATA strings; no code parm."""
    geo = _fresh_geo(params.get("name"))
    n = geo.createNode("labs::rokoko_mocap")
    if "ip" in params:
        _try_set(n, "rokoko_ip", str(params["ip"]))
    if "port" in params:
        _try_set(n, "rokoko_port", str(params["port"]))
    if "actor_index" in params:
        # NOTE: "rokoko_actor_indexxx" is the real parm name on SideFX's Labs Rokoko Mocap HDA
        # (their own typo, confirmed against the live-node probe) — do NOT "correct" the spelling.
        _try_set(n, "rokoko_actor_indexxx", int(clamp(int(params["actor_index"]), 0, 64)))
    if "suit_name" in params:
        _try_set(n, "smartsuit_name", str(params["suit_name"]))
    if "countdown_delay" in params:
        _try_set(n, "countdown_delay", str(params["countdown_delay"]))
    rec = None
    if params.get("recording_filename"):
        rec = confined_path(params["recording_filename"])
        _try_set(n, "recording_filename", rec)
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "points": len(g.points()),
            "prims": len(g.prims()), "recording_filename": rec}


# ── 6. dembones_skinning_external (labs::dembones_skinningconverter) — C WIRE-ONLY external solve ──
@endpoint("dembones_skinning_external")
def dembones_skinning_external(params):
    """Labs DemBones Skinning Converter (labs::dembones_skinningconverter) — WIRE-ONLY. Builds + wires +
    configures the SideFX Labs DemBones solve, which drives an EXTERNAL DemBones executable to convert an
    animated mesh (input 0) into a skeleton + skin weights and write an FBX, but NEVER executes it
    (mirrors tree.py maps_baker / classic_1 dembones_skinning_export: a heavy external solve is fired by
    the human, not on cook). Returns exported=False.
    SECURITY:
      * `animated_cache`/`bind_pose_fbx` (reads), `export_file` (write) and `executable_dir` (the external
        DemBones binary directory) are each realpath-confined to the working directory.
      * the `execute` (Save to Disk) button is never pressed — no external process is launched.
      * the DemBones iteration / bone counts (the solve-cost levers) are hard-clamped."""
    n = child_after(params["geometry"], "labs::dembones_skinningconverter", params.get("name"))

    cache_path = fbx_in = out_path = exe_dir = None
    if params.get("animated_cache"):
        cache_path = confined_path(params["animated_cache"])
        _try_set(n, "sAnimatedCache", cache_path)
    if params.get("bind_pose_fbx"):
        fbx_in = confined_path(params["bind_pose_fbx"])
        _try_set(n, "sBindPoseFBX", fbx_in)
    if params.get("export_file"):
        out_path = confined_path(params["export_file"])
        _try_set(n, "sExportFile", out_path)
    if params.get("executable_dir"):
        exe_dir = confined_path(params["executable_dir"])
        _try_set(n, "executablecache", exe_dir)

    if "bindpose_frame" in params:
        _try_set(n, "iBindposeFrame", int(clamp(int(params["bindpose_frame"]), -100000, 100000)))
    if "create_root" in params:
        _try_set(n, "createroot", bool(params["create_root"]))
    if "hide_shell" in params:
        _try_set(n, "bHideShell", bool(params["hide_shell"]))
    if "num_bones" in params:
        _try_set(n, "nBones", int(clamp(int(params["num_bones"]), 1, 512)))
    if "num_iters" in params:
        _try_set(n, "nIters", int(clamp(int(params["num_iters"]), 1, 200)))
    if "tolerance" in params:
        _try_set(n, "tolerance", clamp(float(params["tolerance"]), 0.0, 1.0))
    if "patience" in params:
        _try_set(n, "patience", int(clamp(int(params["patience"]), 0, 100)))
    if "num_init_iters" in params:
        _try_set(n, "nInitIters", int(clamp(int(params["num_init_iters"]), 1, 100)))
    if "num_trans_iters" in params:
        _try_set(n, "nTransIters", int(clamp(int(params["num_trans_iters"]), 1, 100)))
    if "trans_affine" in params:
        _try_set(n, "transAffine", clamp(float(params["trans_affine"]), 0.0, 1e4))
    if "trans_affine_norm" in params:
        _try_set(n, "transAffineNorm", clamp(float(params["trans_affine_norm"]), 0.0, 1e4))
    if "num_weights_iters" in params:
        _try_set(n, "nWeightsIters", int(clamp(int(params["num_weights_iters"]), 1, 100)))
    if "weights_smooth" in params:
        _try_set(n, "weightsSmooth", clamp(float(params["weights_smooth"]), 0.0, 1e4))
    if "weights_smooth_step" in params:
        _try_set(n, "weightsSmoothStep", clamp(float(params["weights_smooth_step"]), 0.0, 1e4))
    if "max_nonzero" in params:
        _try_set(n, "nnz", int(clamp(int(params["max_nonzero"]), 1, 16)))

    n.moveToGoodPosition()
    return {"node": n.path(), "export_file": out_path, "animated_cache": cache_path,
            "bind_pose_fbx": fbx_in, "executable_dir": exe_dir, "exported": False,
            "note": "Labs DemBones graph wired (WIRE-ONLY); start the external solve yourself"}


# ── 5. dembones_skinning_bake (dembones_skinningconverter::1.0) — C WIRE-ONLY native SOP writer ────
@endpoint("dembones_skinning_bake")
def dembones_skinning_bake(params):
    """DemBones Skinning Converter, native SOP writer (dembones_skinningconverter::1.0) — WIRE-ONLY.
    Builds + wires + configures the built-in SOP-embedded DemBones solve that converts an animated mesh
    (input 0) into a skeleton + skin weights and writes them to `output_file`, but NEVER executes it
    (mirrors tree.py maps_baker / classic_1 dembones_skinning_export). This is the SOP-context sibling of
    the `/out` `dembones_skinning_export` ROP and the Labs `dembones_skinning_external`. Returns
    exported=False.
    SECURITY:
      * `output_file` (write), `animated_cache`/`bind_pose_fbx` (reads) are each realpath-confined.
      * the `execute` (Save to Disk) button is never pressed — no external process is launched.
      * the DemBones iteration / bone counts (the solve-cost levers) are hard-clamped."""
    n = child_after(params["geometry"], "dembones_skinningconverter::1.0", params.get("name"))

    cache_path = fbx_in = out_path = None
    if params.get("output_file"):
        out_path = confined_path(params["output_file"])
        _try_set(n, "sOutputFile", out_path)
    if params.get("animated_cache"):
        cache_path = confined_path(params["animated_cache"])
        _try_set(n, "sAnimatedCache", cache_path)
    if params.get("bind_pose_fbx"):
        fbx_in = confined_path(params["bind_pose_fbx"])
        _try_set(n, "sBindPoseFBX", fbx_in)

    if "make_output_path" in params:
        _try_set(n, "mkpath", bool(params["make_output_path"]))
    if "frame_start" in params or "frame_end" in params:
        fs = int(clamp(int(params.get("frame_start", 1)), -100000, 100000))
        fe = int(clamp(int(params.get("frame_end", fs)), fs, fs + 20000))
        pt = n.parmTuple("f")
        if pt is not None:
            try:
                pt.set((fs, fe, 1))
            except Exception:
                try:
                    pt.set((fs, fe))
                except Exception:
                    pass
    if "bindpose_frame" in params:
        _try_set(n, "iBindposeFrame", int(clamp(int(params["bindpose_frame"]), -100000, 100000)))
    if "create_root" in params:
        _try_set(n, "createroot", bool(params["create_root"]))
    if "num_bones" in params:
        _try_set(n, "nBones", int(clamp(int(params["num_bones"]), 1, 512)))
    if "num_iters" in params:
        _try_set(n, "nIters", int(clamp(int(params["num_iters"]), 1, 200)))
    if "tolerance" in params:
        _try_set(n, "tolerance", clamp(float(params["tolerance"]), 0.0, 1.0))
    if "patience" in params:
        _try_set(n, "patience", int(clamp(int(params["patience"]), 0, 100)))
    if "num_init_iters" in params:
        _try_set(n, "nInitIters", int(clamp(int(params["num_init_iters"]), 1, 100)))
    if "num_trans_iters" in params:
        _try_set(n, "nTransIters", int(clamp(int(params["num_trans_iters"]), 1, 100)))
    if "trans_affine" in params:
        _try_set(n, "transAffine", clamp(float(params["trans_affine"]), 0.0, 1e4))
    if "trans_affine_norm" in params:
        _try_set(n, "transAffineNorm", clamp(float(params["trans_affine_norm"]), 0.0, 1e4))
    if "num_weights_iters" in params:
        _try_set(n, "nWeightsIters", int(clamp(int(params["num_weights_iters"]), 1, 100)))
    if "weights_smooth" in params:
        _try_set(n, "weightsSmooth", clamp(float(params["weights_smooth"]), 0.0, 1e4))
    if "weights_smooth_step" in params:
        _try_set(n, "weightsSmoothStep", clamp(float(params["weights_smooth_step"]), 0.0, 1e4))
    if "max_nonzero" in params:
        _try_set(n, "nnz", int(clamp(int(params["max_nonzero"]), 1, 16)))

    n.moveToGoodPosition()
    return {"node": n.path(), "output_file": out_path, "animated_cache": cache_path,
            "bind_pose_fbx": fbx_in, "exported": False,
            "note": "Native SOP DemBones writer wired (WIRE-ONLY); start the external solve yourself"}

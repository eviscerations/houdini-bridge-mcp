"""Classic Rigging (legacy KineFX lineage) — data-only handlers. Params verified
against live H21.0.671; every non-WIRE-ONLY
endpoint is proven with a headless cook (errors empty + bone geometry aggregated).

These are OBJECT-context classic rig nodes (the pre-KineFX bone-rig lineage), not SOPs:
  A source (OBJ)   : classic_bone (the classic Bone object) + the twelve deform_bone_rig_* preset
                     rig assets (biped/quadruped body-part deformation bone rigs). Each is a 0/1-input
                     OBJ instantiated in /obj; cooking it builds the bone hierarchy (child `bone`
                     objects carrying bonelink + capture-region geometry). The E2E cook aggregates the
                     descendant bone geometry (points/prims) and confirms errors are empty.
  C wire-only ROP  : dembones_skinning_export (the /out `dembones_skinningconverter` Driver) — an
                     external DemBones solve/writer. Built + configured + confined but NEVER executed
                     (mirrors tree.py maps_baker); returns exported=False.

SECURITY (data-only): only geometric / display / solver-scalar params are surfaced. The classic OBJ
nodes carry a `pickscript`/`callback` code surface (the interactive rig-authoring hooks) — those are
NEVER set or exposed. The DemBones ROP's `sAnimatedCache` (Alembic read) / `sBindPoseFBX` (FBX read) /
`sOutputFile` (FBX write) file parms are all routed through confined_path(); its `execute` (Save to
Disk) button is never pressed and its solver-cost levers (bone/iteration counts) are hard-clamped.
No arbitrary-code / callback parm is ever set anywhere in this file.
"""

import hou
from houdini_executor.server import clamp, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _new_obj(ntype, name):
    """Create an OBJ-context node in /obj (Houdini auto-uniquifies the name)."""
    return hou.node("/obj").createNode(ntype, name)


def _agg_bone_geo(objnode):
    """Cook `objnode` and aggregate geometry across its descendant classic `bone` objects (each bone
    carries a bonelink + capture-region SOP on its display flag). Returns (bones, points, prims)."""
    objnode.cook(force=True)
    bones = pts = prims = 0
    candidates = list(objnode.allSubChildren()) if objnode.children() else []
    # include the node itself if it is a bone (classic_bone case)
    if objnode.type().name() == "bone":
        candidates = [objnode] + candidates
    for ch in candidates:
        if isinstance(ch, hou.ObjNode) and ch.type().name() == "bone":
            bones += 1
            d = ch.displayNode()
            if d is not None:
                try:
                    d.cook(force=True)
                    g = d.geometry()
                    pts += len(g.points())
                    prims += len(g.prims())
                except Exception:
                    pass
    return bones, pts, prims


def _obj_cooked(objnode):
    bones, pts, prims = _agg_bone_geo(objnode)
    return {"node": objnode.path(), "bones": bones, "points": pts, "prims": prims,
            "errors": bool(objnode.errors())}


# ── OBJ transform / display curation shared by classic_bone + deform_bone_rig_* ───────────────────
def _apply_obj_transform(n, params):
    if "translate" in params:
        _try_set_tuple(n, "t", params["translate"])
    if "rotate" in params:
        _try_set_tuple(n, "r", params["rotate"])
    if "uniform_scale" in params:
        _try_set(n, "scale", clamp(float(params["uniform_scale"]), 1e-4, 1e4))
    if "pre_scale" in params:
        _try_set_tuple(n, "s", params["pre_scale"])
    if "set_wireframe_color" in params:
        _try_set(n, "use_dcolor", bool(params["set_wireframe_color"]))
    if "wireframe_color" in params:
        _try_set(n, "use_dcolor", True)
        _try_set_tuple(n, "dcolor", params["wireframe_color"])


# ── 1. classic_bone (bone, OBJ) — A source: one classic Bone object ──────────────────────────────
@endpoint("classic_bone")
def classic_bone(params):
    """Classic Bone (OBJ `bone`) — creates one classic Bone object: a length-parameterized bone with a
    bonelink display and adjustable capture / deform capture-region cylinders (the pre-KineFX skinning
    primitive). Named `classic_bone` to avoid colliding with the `bone_deform` / `bone_capture` tools.
    Cooks to the bonelink + capture-region geometry. SECURITY: geometric/display values only; the OBJ
    `pickscript` code hook is never set or exposed."""
    n = _new_obj("bone", params.get("name"))
    _apply_obj_transform(n, params)
    if "bone_length" in params:
        _try_set(n, "length", clamp(float(params["bone_length"]), 1e-4, 1e6))
    if "display_link" in params:
        _try_set(n, "displaylink", bool(params["display_link"]))
    if "display_capture_region" in params:
        _try_set(n, "displaycapture", bool(params["display_capture_region"]))
    if "capture_top_height" in params:
        _try_set(n, "ccrtopheight", clamp(float(params["capture_top_height"]), -1e6, 1e6))
    if "capture_bottom_height" in params:
        _try_set(n, "ccrbotheight", clamp(float(params["capture_bottom_height"]), -1e6, 1e6))
    if "deform_top_height" in params:
        _try_set(n, "crtopheight", clamp(float(params["deform_top_height"]), -1e6, 1e6))
    if "deform_bottom_height" in params:
        _try_set(n, "crbotheight", clamp(float(params["deform_bottom_height"]), -1e6, 1e6))
    return _obj_cooked(n)


# ── 2-13. deform_bone_rig_* (OBJ preset rig assets) — A source: instantiate a body-part bone rig ──
def _build_bone_rig(params, ntype):
    n = _new_obj(ntype, params.get("name"))
    _apply_obj_transform(n, params)
    if "display_bones" in params:
        _try_set(n, "display_bones", bool(params["display_bones"]))
    if "display_capture_geometry" in params:
        _try_set(n, "display_capture_geometry", bool(params["display_capture_geometry"]))
    return _obj_cooked(n)


@endpoint("deform_bone_rig_biped_arm")
def deform_bone_rig_biped_arm(params):
    """Classic Deform Bone Rig — Biped Arm (OBJ `deform_bone_rig_biped_arm`) — instantiates a ready-made
    classic bone deformation rig for a biped arm (collarbone / upper-arm / forearm / wrist bones with
    capture regions). A 0-input preset asset dropped into /obj. `display_bones` /
    `display_capture_geometry` toggle the rig's bone vs capture-region visualization. SECURITY:
    transform/display values only; per-joint region multiparms and OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_biped_arm")


@endpoint("deform_bone_rig_biped_hand_4f_2s")
def deform_bone_rig_biped_hand_4f_2s(params):
    """Classic Deform Bone Rig — Biped Hand, 4 Fingers / 2 Segments (OBJ
    `deform_bone_rig_biped_hand_4f_2s`) — a ready-made classic bone deformation rig for a 4-finger,
    2-segment hand. 0-input preset asset. `display_bones` / `display_capture_geometry` toggle the
    visualization. SECURITY: transform/display values only; per-joint multiparms + code hooks untouched."""
    return _build_bone_rig(params, "deform_bone_rig_biped_hand_4f_2s")


@endpoint("deform_bone_rig_biped_hand_4f_3s")
def deform_bone_rig_biped_hand_4f_3s(params):
    """Classic Deform Bone Rig — Biped Hand, 4 Fingers / 3 Segments (OBJ
    `deform_bone_rig_biped_hand_4f_3s`) — a ready-made classic bone deformation rig for a 4-finger,
    3-segment hand. 0-input preset asset. `display_bones` / `display_capture_geometry` toggle the
    visualization. SECURITY: transform/display values only; per-joint multiparms + code hooks untouched."""
    return _build_bone_rig(params, "deform_bone_rig_biped_hand_4f_3s")


@endpoint("deform_bone_rig_biped_hand_5f_3s")
def deform_bone_rig_biped_hand_5f_3s(params):
    """Classic Deform Bone Rig — Biped Hand, 5 Fingers / 3 Segments (OBJ
    `deform_bone_rig_biped_hand_5f_3s`) — a ready-made classic bone deformation rig for a full 5-finger,
    3-segment hand. 0-input preset asset. `display_bones` / `display_capture_geometry` toggle the
    visualization. SECURITY: transform/display values only; per-joint multiparms + code hooks untouched."""
    return _build_bone_rig(params, "deform_bone_rig_biped_hand_5f_3s")


@endpoint("deform_bone_rig_biped_head_and_neck")
def deform_bone_rig_biped_head_and_neck(params):
    """Classic Deform Bone Rig — Biped Head and Neck (OBJ `deform_bone_rig_biped_head_and_neck`) — a
    ready-made classic bone deformation rig for a biped head + neck chain. 0-input preset asset.
    `display_bones` / `display_capture_geometry` toggle the visualization. SECURITY: transform/display
    values only; per-joint multiparms + OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_biped_head_and_neck")


@endpoint("deform_bone_rig_biped_leg")
def deform_bone_rig_biped_leg(params):
    """Classic Deform Bone Rig — Biped Leg (OBJ `deform_bone_rig_biped_leg`) — a ready-made classic bone
    deformation rig for a biped leg (thigh / shin / foot bones with capture regions). 0-input preset
    asset. `display_bones` / `display_capture_geometry` toggle the visualization. SECURITY:
    transform/display values only; per-joint multiparms + OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_biped_leg")


@endpoint("deform_bone_rig_biped_spine_3pc")
def deform_bone_rig_biped_spine_3pc(params):
    """Classic Deform Bone Rig — Biped Spine, 3 Pieces (OBJ `deform_bone_rig_biped_spine_3pc`) — a
    ready-made 3-segment classic bone deformation rig for a biped spine. 0-input preset asset.
    `display_bones` / `display_capture_geometry` toggle the visualization. SECURITY: transform/display
    values only; per-joint multiparms + OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_biped_spine_3pc")


@endpoint("deform_bone_rig_biped_spine_5pc")
def deform_bone_rig_biped_spine_5pc(params):
    """Classic Deform Bone Rig — Biped Spine, 5 Pieces (OBJ `deform_bone_rig_biped_spine_5pc`) — a
    ready-made 5-segment classic bone deformation rig for a biped spine. 0-input preset asset.
    `display_bones` / `display_capture_geometry` toggle the visualization. SECURITY: transform/display
    values only; per-joint multiparms + OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_biped_spine_5pc")


@endpoint("deform_bone_rig_quadruped_back_leg")
def deform_bone_rig_quadruped_back_leg(params):
    """Classic Deform Bone Rig — Quadruped Back Leg (OBJ `deform_bone_rig_quadruped_back_leg`) — a
    ready-made classic bone deformation rig for a quadruped hind leg. 0-input preset asset.
    `display_bones` / `display_capture_geometry` toggle the visualization. SECURITY: transform/display
    values only; per-joint multiparms + OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_quadruped_back_leg")


@endpoint("deform_bone_rig_quadruped_front_leg")
def deform_bone_rig_quadruped_front_leg(params):
    """Classic Deform Bone Rig — Quadruped Front Leg (OBJ `deform_bone_rig_quadruped_front_leg`) — a
    ready-made classic bone deformation rig for a quadruped front leg. 0-input preset asset.
    `display_bones` / `display_capture_geometry` toggle the visualization. SECURITY: transform/display
    values only; per-joint multiparms + OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_quadruped_front_leg")


@endpoint("deform_bone_rig_quadruped_head_and_neck")
def deform_bone_rig_quadruped_head_and_neck(params):
    """Classic Deform Bone Rig — Quadruped Head and Neck (OBJ `deform_bone_rig_quadruped_head_and_neck`)
    — a ready-made classic bone deformation rig for a quadruped head + neck chain. 0-input preset asset.
    `display_bones` / `display_capture_geometry` toggle the visualization. SECURITY: transform/display
    values only; per-joint multiparms + OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_quadruped_head_and_neck")


@endpoint("deform_bone_rig_quadruped_ik_spine")
def deform_bone_rig_quadruped_ik_spine(params):
    """Classic Deform Bone Rig — Quadruped IK Spine (OBJ `deform_bone_rig_quadruped_ik_spine`) — a
    ready-made classic bone deformation rig for a quadruped IK spine chain. 0-input preset asset.
    `display_bones` / `display_capture_geometry` toggle the visualization. SECURITY: transform/display
    values only; per-joint multiparms + OBJ code hooks are never touched."""
    return _build_bone_rig(params, "deform_bone_rig_quadruped_ik_spine")


# ── 14. dembones_skinning_export (dembones_skinningconverter, /out Driver) — C WIRE-ONLY ──────────
_TRANGE = ("off", "normal", "on")


@endpoint("dembones_skinning_export")
def dembones_skinning_export(params):
    """Classic DemBones Skinning Converter ROP (/out `dembones_skinningconverter`) — WIRE-ONLY. Builds +
    configures the DemBones external solve that converts an animated Alembic cache (+ optional bind-pose
    FBX) into a skeleton + skin-weighted FBX, but NEVER executes it (mirrors tree.py maps_baker — the
    heavy external solve is fired by the human, not on cook). Named `dembones_skinning_export` to avoid
    colliding with the KineFX SOP `dembones_skinning_converter`. Returns exported=False.
    SECURITY:
      * `animated_cache` (Alembic read), `bind_pose_fbx` (FBX read) and `output_file` (FBX write) are
        each realpath-confined to the working directory.
      * the `execute` (Save to Disk) button is never pressed — no external process is launched.
      * the DemBones iteration / bone counts (the solve-cost levers) are hard-clamped."""
    n = hou.node("/out").createNode("dembones_skinningconverter", params.get("name"))

    cache_path = fbx_in = out_path = None
    if params.get("animated_cache"):
        cache_path = confined_path(params["animated_cache"])
        _try_set(n, "sAnimatedCache", cache_path)
    if params.get("bind_pose_fbx"):
        fbx_in = confined_path(params["bind_pose_fbx"])
        _try_set(n, "sBindPoseFBX", fbx_in)
    if params.get("output_file"):
        out_path = confined_path(params["output_file"])
        _try_set(n, "sOutputFile", out_path)

    if "frame_start" in params or "frame_end" in params:
        _menu_set(n, "trange", "normal", _TRANGE)
        fs = int(clamp(int(params.get("frame_start", 1)), -100000, 100000))
        fe = int(clamp(int(params.get("frame_end", fs)), fs, fs + 20000))
        pt = n.parmTuple("f")
        if pt is not None:
            try:
                pt.set((fs, fe))
            except Exception:
                pass
    if "create_root" in params:
        _try_set(n, "createroot", bool(params["create_root"]))
    if "num_bones" in params:
        _try_set(n, "nBones", int(clamp(int(params["num_bones"]), 1, 512)))
    if "global_iters" in params:
        _try_set(n, "nIters", int(clamp(int(params["global_iters"]), 1, 200)))
    if "tolerance" in params:
        _try_set(n, "tolerance", clamp(float(params["tolerance"]), 0.0, 1.0))
    if "patience" in params:
        _try_set(n, "patience", int(clamp(int(params["patience"]), 0, 100)))
    if "splitting_iters" in params:
        _try_set(n, "nInitIters", int(clamp(int(params["splitting_iters"]), 1, 100)))
    if "transform_iters" in params:
        _try_set(n, "nTransIters", int(clamp(int(params["transform_iters"]), 1, 100)))
    if "translations_affinity" in params:
        _try_set(n, "transAffine", clamp(float(params["translations_affinity"]), 0.0, 1e4))
    if "p_norm" in params:
        _try_set(n, "transAffineNorm", clamp(float(params["p_norm"]), 0.0, 1e4))
    if "weights_iters" in params:
        _try_set(n, "nWeightsIters", int(clamp(int(params["weights_iters"]), 1, 100)))
    if "smoothness" in params:
        _try_set(n, "weightsSmooth", clamp(float(params["smoothness"]), 0.0, 1e4))
    if "step_size" in params:
        _try_set(n, "weightsSmoothStep", clamp(float(params["step_size"]), 0.0, 1e4))
    if "min_nonzero" in params:
        _try_set(n, "nnz", int(clamp(int(params["min_nonzero"]), 1, 16)))

    n.moveToGoodPosition()
    return {"node": n.path(), "output_file": out_path, "animated_cache": cache_path,
            "bind_pose_fbx": fbx_in, "exported": False,
            "note": "DemBones ROP configured (WIRE-ONLY); start the external solve yourself"}

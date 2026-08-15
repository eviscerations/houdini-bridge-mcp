"""KineFX MotionClip & Motion-Mixer — data-only handlers. Params verified against live H21.0.671; every endpoint proven with a headless cook over an ANIMATED
skeleton packed into a motionclip.

A MotionClip is a single-frame PACKED representation of an animated skeleton (channel primitives).
The lane's shape: an animated skeleton -> `motion_clip` (PACK) -> the motionclip operators
(retime / cycle / blend / sequence / extract / unpack ...) -> `motion_clip_unpack` /
`motion_clip_evaluate` back to a live skeleton.

Archetypes (mirror the Labs A/B/C mapping):
  A source  : motion_clip_compute_create, motion_clip_create, motion_clip_info, motion_clip_merge
              (0..2 inputs; build/import a clip).
  B chain   : the bulk — input0 = a motionclip (or, for `motion_clip`, an animated skeleton). A few
              take a semantic input1 wired explicitly (blend Layer, sequence Second clip, pose to add,
              rest frame, pose/joint-list stream). The correct input index is always wired explicitly.

SECURITY (data-only):
  * No code/callback parm is ever set or exposed (none of these nodes carries one — scout + probe
    confirm has_code_parm=false).
  * FILE parms are routed through confined_path(): `motion_clip_create` (`file` .bgeo clip + `fbxfile`
    mocap import) — set only when the caller supplies a path, realpath-confined to the working dir.
  * `sop`/`soppath`/`source_sop` are Houdini NODE PATHS (a SOP to sample), NOT filesystem paths — set
    verbatim (same class as object_merge's objpath), never confined/opened as files.
  * SKIPPED: the interactive `kinefx::motionmixer` (track/fx multiparm UI +
    per-instance `fxfile#` file multiparm, APEX-Scene authoring — no data-only scalar surface),
    `motionmixerfetch` / `motionmixerfx` (companion fetch / subnet-internal FX, empty standalone),
    `motionmixersetup` (APEX rig-pattern `%callback(...)` authoring — belongs to the deferred APEX pass).
"""

import hou
from houdini_executor.server import clamp, child_after, bridge_input, endpoint, confined_path
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _set_range(node, parm, start=None, end=None, inc=None):
    """Set only the supplied components of a Float2/Float3/Int2 range parmTuple, in place. Preserves
    the parm's own component type (int vs float)."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    given = (start, end, inc)
    ok = False
    for i, v in enumerate(given):
        if v is None or i >= len(pt):
            continue
        try:
            pt[i].set(v)
            ok = True
        except Exception:
            pass
    return ok


def _int_menu(node, parm, value, lo, hi):
    """Set an index-token ordered menu (menuItems() == ['0','1','2',...]) by clamped integer index."""
    return _try_set(node, parm, int(clamp(int(value), lo, hi)))


def _cooked(n):
    # A file-reader node (e.g. motion_clip_create pointed at a not-yet-present clip) can yield a None
    # geometry without raising — report it rather than 500-crashing on g.points().
    g = n.geometry()
    if g is None:
        return {"node": n.path(), "points": 0, "prims": 0, "cooked": False}
    out = {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}
    # Honest-return coverage: a motionclip packs sampled frames, so points/prims is only an indirect
    # proxy for the clip length a recipe pass_if actually reads. The clip carries a per-sample `time`
    # prim attribute (the same source motion_clip_info builds `clipinfo` from) — surface the real range +
    # sample count. Guarded so a non-clip stream in this family simply omits the fields.
    try:
        if g.findPrimAttrib("time") is not None:
            t = g.primFloatAttribValues("time")
            if t:
                out["frame_range"] = [min(t), max(t)]
                out["samples"] = len(t)
    except Exception:  # noqa: BLE001 - readback convenience must never break a good cook
        pass
    return out


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_END = ("clamp", "loop", "mirror")
_INTERP = ("linear", "constant")
_RETIME_EVAL = ("shift", "time", "frame", "speed")
_ROT_ORDER = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")
_XORD = ("srt", "str", "rst", "rts", "tsr", "trs")
_LOCO_SRC = ("joint", "com")
_SHAPE = ("linear", "cosine", "easein", "easeout")
_EVAL_MODE = ("current", "custom")
_EXTRACT_MODE = ("frames", "trails")
_CLIP_RANGE2 = ("clipinfo", "custom")
_CLIP_RANGE3 = ("clipinfo", "custom", "all")
_CYCLE_SEQ = ("shift", "velocity", "mirror")
_SEQ_SEQ = ("shift", "velocity")
_SEQ_METHOD = ("preserve", "overlap", "insert")
_POSE_OVERLAP = ("replace", "skip", "update", "error")
_UPDATE_OVERLAP = ("replace", "remove", "keep", "replacerange")
_UPDATE_NEW = ("add", "skip")
_UPDATE_BLENDJOINTS = ("replace", "new", "both")
_UPDATE_WEIGHT = ("group", "attribute")
_KEYPOSE_OUTPUT = ("extract", "identify")
_KEYPOSE_METHOD = ("minpose", "minjoint", "minavg")
_KEYPOSE_TARGET = ("percentage", "count")
_POSEDELETE_SEL = ("framerange", "framepattern", "poserange", "posegroup")
_CREATE_MODE = ("fetchsop", "single", "library", "fbx", "apexscene")
_CREATE_OUTPUT = ("animation", "rest")
_RELOAD = ("auto", "manual")
_SAMPLE_MODE = ("single", "range", "current")
_MIXER_RETIME_MODE = ("frame", "time", "speed", "hold")
_FILTER = ("butter",)
_LOCO_INPUT = ("compute", "prim", "joint")
_LOCO_OUTPUT = ("prim", "joint")


# ── 1. motion_clip (kinefx::motionclip) — PACK: animated skeleton -> single-frame motionclip ─────
@endpoint("motion_clip")
def motion_clip(params):
    """KineFX MotionClip (kinefx::motionclip) — PACKS an ANIMATED skeleton (input 0) sampled across a
    frame range into a single-frame packed motionclip (channel primitives). Extra inputs pack more
    skeletons. The root of the MotionClip lane; everything else consumes its output. SECURITY: attribute
    names only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::motionclip", params.get("name"))
    if "pack_inputs" in params:
        _try_set(n, "packinputs", bool(params["pack_inputs"]))
    if "rest_frame" in params:
        _try_set(n, "restframe", clamp(float(params["rest_frame"]), -1e6, 1e6))
    if "use_sample_rate" in params:
        _try_set(n, "usesamplerate", bool(params["use_sample_rate"]))
    if "sample_rate" in params:
        _try_set(n, "samplerate", clamp(float(params["sample_rate"]), 0.0, 1e4))
    if "use_frame_range" in params:
        _try_set(n, "useframerange", bool(params["use_frame_range"]))
    if "frame_start" in params or "frame_end" in params:
        _set_range(n, "framerange", params.get("frame_start"), params.get("frame_end"))
    if "use_left_end_behavior" in params:
        _try_set(n, "useleftendbehavior", bool(params["use_left_end_behavior"]))
    if "left_end_behavior" in params:
        _menu_set(n, "leftendbehavior", str(params["left_end_behavior"]), _END)
    if "use_right_end_behavior" in params:
        _try_set(n, "userightendbehavior", bool(params["use_right_end_behavior"]))
    if "right_end_behavior" in params:
        _menu_set(n, "rightendbehavior", str(params["right_end_behavior"]), _END)
    if "reload_method" in params:
        _menu_set(n, "reloadmethod", str(params["reload_method"]), _RELOAD)
    if "attribs" in params:
        _try_set(n, "attribs", str(params["attribs"]))
    if "recompute_locals" in params:
        _try_set(n, "recomputelocals", bool(params["recompute_locals"]))
    if "use_first_frame" in params:
        _try_set(n, "usefirstframe", bool(params["use_first_frame"]))
    if "isolate_key_poses" in params:
        _try_set(n, "isolatekeyposes", bool(params["isolate_key_poses"]))
    return _cooked(n)


# ── 2. motion_clip_create (kinefx::motionclipcreate) — A source; file import CONFINED ─────────────
@endpoint("motion_clip_create")
def motion_clip_create(params):
    """KineFX MotionClip Create (kinefx::motionclipcreate) — builds a motionclip from a live SOP
    (`mode=single`/`fetchsop`, `source_sop`), a clip library, or an imported `.bgeo`/FBX clip. Optional
    `input` (input 0) supplies source clips. SECURITY: `file` (.bgeo clip) and `fbx_file` (mocap import)
    are realpath-confined to the working directory and set only when supplied; `source_sop` is a Houdini
    NODE PATH (a SOP to sample), not a filesystem path. No code parm exposed."""
    if params.get("input"):
        n = child_after(params["input"], "kinefx::motionclipcreate", params.get("name"))
    else:
        parent = hou.node(params["parent"]) if params.get("parent") else None
        if parent is None:
            raise ValueError("motion_clip_create requires `input` (a source SOP) or `parent` (a geo net)")
        n = parent.createNode("kinefx::motionclipcreate", params.get("name"))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _CREATE_MODE)
    if "source_sop" in params:
        _try_set(n, "sop", str(params["source_sop"]))     # NODE path, not a file
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "use_sample_rate" in params:
        _try_set(n, "usesamplerate", bool(params["use_sample_rate"]))
    if "sample_rate" in params:
        _try_set(n, "samplerate", clamp(float(params["sample_rate"]), 0.0, 1e4))
    if "use_frame_range" in params:
        _try_set(n, "useframerange", bool(params["use_frame_range"]))
    if "frame_start" in params or "frame_end" in params:
        _set_range(n, "framerange", params.get("frame_start"), params.get("frame_end"))
    if params.get("file"):
        _try_set(n, "file", confined_path(params["file"]))
    if params.get("fbx_file"):
        _try_set(n, "fbxfile", confined_path(params["fbx_file"]))
    if "clip_name2" in params:
        _try_set(n, "clipname2", str(params["clip_name2"]))
    if "root_node" in params:
        _try_set(n, "rootnode", str(params["root_node"]))
    if "convert_units" in params:
        _try_set(n, "convertunits", bool(params["convert_units"]))
    if "import_userdef_attribs" in params:
        _try_set(n, "importuserdefattrib", bool(params["import_userdef_attribs"]))
    if "output" in params:
        _menu_set(n, "output", str(params["output"]), _CREATE_OUTPUT)
    n.moveToGoodPosition()
    return _cooked(n)


# ── 3. motion_clip_compute_create (kinefx::computemotionclipcreate) — A source from a SOP path ────
@endpoint("motion_clip_compute_create")
def motion_clip_compute_create(params):
    """KineFX Compute MotionClip Create (kinefx::computemotionclipcreate) — packs the animated skeleton
    at `source_sop` (a Houdini NODE PATH) over a frame range into a motionclip, using the compute engine
    (0 geometry inputs). SECURITY: `source_sop` is a node path, not a file; no file/code surface."""
    parent = hou.node(params["parent"]) if params.get("parent") else None
    if parent is None:
        raise ValueError("motion_clip_compute_create requires `parent` (a geo network path)")
    n = parent.createNode("kinefx::computemotionclipcreate", params.get("name"))
    if "source_sop" in params:
        _try_set(n, "soppath", str(params["source_sop"]))   # NODE path, not a file
    if "sample_rate" in params:
        _try_set(n, "samplerate", clamp(float(params["sample_rate"]), 0.0, 1e4))
    if "frame_start" in params or "frame_end" in params:
        _set_range(n, "framerange", params.get("frame_start"), params.get("frame_end"))
    n.moveToGoodPosition()
    return _cooked(n)


# ── 4. motion_clip_compute_retime (kinefx::computemotionclipretime) — B chain, in0=motionclip ─────
@endpoint("motion_clip_compute_retime")
def motion_clip_compute_retime(params):
    """KineFX Compute MotionClip Retime (kinefx::computemotionclipretime) — retimes a motionclip
    (input 0) via the compute engine: shift / absolute time / frame / speed, with optional trim and
    output range/sample-rate resampling. SECURITY: attribute names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::computemotionclipretime", params.get("name"))
    _apply_retime_common(n, params)
    return _cooked(n)


# ── 5. motion_clip_retime (kinefx::motionclipretime) — B chain, in0=motionclip ───────────────────
@endpoint("motion_clip_retime")
def motion_clip_retime(params):
    """KineFX MotionClip Retime (kinefx::motionclipretime) — retimes a motionclip (input 0): shift /
    absolute time / frame / speed, with optional trim, per-frame time/frame/speed overrides, and output
    range/sample-rate resampling. SECURITY: attribute names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipretime", params.get("name"))
    _apply_retime_common(n, params)
    if "use_time" in params:
        _try_set(n, "usetime", bool(params["use_time"]))
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "use_frame" in params:
        _try_set(n, "useframe", bool(params["use_frame"]))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "use_speed_anim" in params:
        _try_set(n, "usespeedanim", bool(params["use_speed_anim"]))
    return _cooked(n)


def _apply_retime_common(n, params):
    """Shared retime scalar surface for motion_clip_retime / motion_clip_compute_retime."""
    if "eval_mode" in params:
        _menu_set(n, "evalmode", str(params["eval_mode"]), _RETIME_EVAL)
    if "trim" in params:
        _try_set(n, "trim", bool(params["trim"]))
    if "set_anim_start" in params:
        _try_set(n, "setanimstart", bool(params["set_anim_start"]))
    if "anim_start" in params:
        _try_set(n, "animstart", clamp(float(params["anim_start"]), -1e6, 1e6))
    if "set_anim_end" in params:
        _try_set(n, "setanimend", bool(params["set_anim_end"]))
    if "anim_end" in params:
        _try_set(n, "animend", clamp(float(params["anim_end"]), -1e6, 1e6))
    if "set_shift" in params:
        _try_set(n, "setshift", bool(params["set_shift"]))
    if "shift" in params:
        _try_set(n, "shift", clamp(float(params["shift"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), -1e3, 1e3))
    if "use_output_range" in params:
        _try_set(n, "useoutputrange", bool(params["use_output_range"]))
    if "output_start" in params or "output_end" in params:
        _set_range(n, "outputrange", params.get("output_start"), params.get("output_end"))
    if "use_output_sample_rate" in params:
        _try_set(n, "useoutputsamplerate", bool(params["use_output_sample_rate"]))
    if "output_sample_rate" in params:
        _try_set(n, "outputsamplerate", clamp(float(params["output_sample_rate"]), 0.0, 1e4))
    if "repack_attribs" in params:
        _try_set(n, "repackattribs", bool(params["repack_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "anim_attribs" in params:
        _try_set(n, "animattribs", str(params["anim_attribs"]))
    if "set_left_end_behavior" in params:
        _try_set(n, "setleftendbehavior", bool(params["set_left_end_behavior"]))
    if "left_end_behavior" in params:
        _menu_set(n, "leftendbehavior", str(params["left_end_behavior"]), _END)
    if "set_right_end_behavior" in params:
        _try_set(n, "setrightendbehavior", bool(params["set_right_end_behavior"]))
    if "right_end_behavior" in params:
        _menu_set(n, "rightendbehavior", str(params["right_end_behavior"]), _END)


# ── 6. motion_clip_velocity (kinefx::motionclipcomputevelocity) — in0=clip, in1 opt rest frame ────
@endpoint("motion_clip_velocity")
def motion_clip_velocity(params):
    """KineFX MotionClip Compute Velocity (kinefx::motionclipcomputevelocity) — computes per-joint
    velocities on a motionclip (input 0); optional `rest_frame` (input 1) supplies the rest pose.
    Handles locomotion source (joint/COM) and translation/orientation extraction. SECURITY: attribute
    names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipcomputevelocity", params.get("name"))
    if params.get("rest_frame"):
        bridge_input(n, params["rest_frame"], index=1, name_hint="rest_frame")
    if "locomotion" in params:
        _int_menu(n, "locomotion", params["locomotion"], 0, 2)
    if "locomotion_source" in params:
        _menu_set(n, "locomotionsource", str(params["locomotion_source"]), _LOCO_SRC)
    if "locomotion_joint" in params:
        _try_set(n, "locomotionjoint", str(params["locomotion_joint"]))
    if "keep_com_point" in params:
        _try_set(n, "keepcompoint", bool(params["keep_com_point"]))
    if "com_name" in params:
        _try_set(n, "comtargetname", str(params["com_name"]))
    if "match_translation" in params:
        _int_menu(n, "matchtranslation", params["match_translation"], 0, 2)
    if "orientation_method" in params:
        _int_menu(n, "orientationmethod", params["orientation_method"], 0, 3)
    if "rotation_order" in params:
        _int_menu(n, "rotationorder", params["rotation_order"], 0, 5)
    if "repack_attribs" in params:
        _try_set(n, "repackattribs", bool(params["repack_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "anim_attribs" in params:
        _try_set(n, "animattribs", str(params["anim_attribs"]))
    return _cooked(n)


# ── 7. motion_clip_cycle (kinefx::motionclipcycle::2.0) — B chain, in0=motionclip ────────────────
@endpoint("motion_clip_cycle")
def motion_clip_cycle(params):
    """KineFX MotionClip Cycle (kinefx::motionclipcycle::2.0) — repeats a motionclip (input 0) before/
    after itself to build a loop, with locomotion continuity (shift/velocity/mirror) and pose blending
    at the seam. SECURITY: attribute names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipcycle::2.0", params.get("name"))
    if "set_frame_range" in params:
        _try_set(n, "setframerange", bool(params["set_frame_range"]))
    if "frame_start" in params or "frame_end" in params:
        _set_range(n, "framerange", params.get("frame_start"), params.get("frame_end"))
    if "cycles_before" in params:
        _try_set(n, "cyclesbefore", clamp(float(params["cycles_before"]), 0.0, 1e4))
    if "cycles_after" in params:
        _try_set(n, "cyclesafter", clamp(float(params["cycles_after"]), 0.0, 1e4))
    if "sequence_type" in params:
        _menu_set(n, "sequencetype", str(params["sequence_type"]), _CYCLE_SEQ)
    if "locomotion" in params:
        _int_menu(n, "locomotion", params["locomotion"], 0, 2)
    if "locomotion_source" in params:
        _menu_set(n, "locomotionsource", str(params["locomotion_source"]), _LOCO_SRC)
    if "locomotion_joint" in params:
        _try_set(n, "locomotionjoint", str(params["locomotion_joint"]))
    if "apply_locomotion" in params:
        _try_set(n, "applylocomotion", bool(params["apply_locomotion"]))
    if "loop" in params:
        _try_set(n, "loop", bool(params["loop"]))
    if "blend_mode" in params:
        _int_menu(n, "blendmode", params["blend_mode"], 0, 2)
    if "shape" in params:
        _menu_set(n, "shape", str(params["shape"]), _SHAPE)
    if "bias" in params:
        _try_set(n, "bias", clamp(float(params["bias"]), 0.0, 1.0))
    if "repack_attribs" in params:
        _try_set(n, "repackattribs", bool(params["repack_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "anim_attribs" in params:
        _try_set(n, "animattribs", str(params["anim_attribs"]))
    return _cooked(n)


# ── 8. motion_clip_evaluate (kinefx::motionclipevaluate) — B chain, in0=motionclip -> live pose ───
@endpoint("motion_clip_evaluate")
def motion_clip_evaluate(params):
    """KineFX MotionClip Evaluate (kinefx::motionclipevaluate) — samples a motionclip (input 0) at a
    frame back to a LIVE skeleton pose (current frame or a custom frame), with optional COM output and
    end-behavior. SECURITY: attribute names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipevaluate", params.get("name"))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _EVAL_MODE)
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "interp" in params:
        _menu_set(n, "interp", str(params["interp"]), _INTERP)
    if "use_end_behavior" in params:
        _try_set(n, "useendbehavior", bool(params["use_end_behavior"]))
    if "end_behavior" in params:
        _menu_set(n, "endbehavior", str(params["end_behavior"]), _END)
    if "output_com" in params:
        _try_set(n, "outputcom", bool(params["output_com"]))
    if "isolate_com" in params:
        _try_set(n, "isolatecom", bool(params["isolate_com"]))
    if "com_name" in params:
        _try_set(n, "comname", str(params["com_name"]))
    if "use_config_attrib" in params:
        _try_set(n, "useconfigattrib", bool(params["use_config_attrib"]))
    if "config_attrib" in params:
        _try_set(n, "configattrib", str(params["config_attrib"]))
    if "use_attribs" in params:
        _try_set(n, "useattribs", bool(params["use_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "attribs" in params:
        _try_set(n, "attribs", str(params["attribs"]))
    return _cooked(n)


# ── 9. motion_clip_extract (kinefx::motionclipextract) — B chain, in0=motionclip ─────────────────
@endpoint("motion_clip_extract")
def motion_clip_extract(params):
    """KineFX MotionClip Extract (kinefx::motionclipextract) — extracts poses from a motionclip
    (input 0) as per-frame skeletons or motion trails over a frame range. SECURITY: attribute/group
    names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipextract", params.get("name"))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _EXTRACT_MODE)
    if "joint_names" in params:
        _try_set(n, "jointnames", str(params["joint_names"]))
    if "unpack_existing" in params:
        _try_set(n, "unpackexisting", bool(params["unpack_existing"]))
    if "clip_range_mode" in params:
        _menu_set(n, "cliprangemode", str(params["clip_range_mode"]), _CLIP_RANGE2)
    if "frame_start" in params or "frame_end" in params or "frame_inc" in params:
        _set_range(n, "framerange", params.get("frame_start"), params.get("frame_end"),
                   params.get("frame_inc"))
    if "use_end_behavior" in params:
        _try_set(n, "useendbehavior", bool(params["use_end_behavior"]))
    if "end_behavior" in params:
        _menu_set(n, "endbehavior", str(params["end_behavior"]), _END)
    if "output_com" in params:
        _try_set(n, "outputcom", bool(params["output_com"]))
    if "isolate_com" in params:
        _try_set(n, "isolatecom", bool(params["isolate_com"]))
    if "com_name" in params:
        _try_set(n, "comname", str(params["com_name"]))
    if "use_attribs" in params:
        _try_set(n, "useattribs", bool(params["use_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "attribs" in params:
        _try_set(n, "attribs", str(params["attribs"]))
    return _cooked(n)


# ── 10. motion_clip_key_poses (kinefx::motionclipextractkeyposes) — B chain, in0=motionclip ───────
@endpoint("motion_clip_key_poses")
def motion_clip_key_poses(params):
    """KineFX MotionClip Extract Key Poses (kinefx::motionclipextractkeyposes) — reduces a motionclip
    (input 0) to its key poses (by percentage or count), either extracting them or tagging them.
    SECURITY: attribute names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipextractkeyposes", params.get("name"))
    if "output_method" in params:
        _menu_set(n, "outputmethod", str(params["output_method"]), _KEYPOSE_OUTPUT)
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _KEYPOSE_METHOD)
    if "target" in params:
        _menu_set(n, "target", str(params["target"]), _KEYPOSE_TARGET)
    if "percentage" in params:
        _try_set(n, "percentage", clamp(float(params["percentage"]), 0.0, 100.0))
    if "key_poses" in params:
        _try_set(n, "keyposes", int(clamp(int(params["key_poses"]), 1, 100000)))
    if "reduce_past_target" in params:
        _try_set(n, "reducepasttarget", bool(params["reduce_past_target"]))
    if "tolerance" in params:
        _try_set(n, "tolerance", clamp(float(params["tolerance"]), 0.0, 1e6))
    if "use_max_step" in params:
        _try_set(n, "usemaxstep", bool(params["use_max_step"]))
    if "max_step" in params:
        _try_set(n, "maxstep", int(clamp(int(params["max_step"]), 1, 1000000)))
    if "trim" in params:
        _try_set(n, "trim", bool(params["trim"]))
    if "use_range" in params:
        _try_set(n, "userange", bool(params["use_range"]))
    if "range_start" in params or "range_end" in params:
        _set_range(n, "range", params.get("range_start"), params.get("range_end"))
    if "repack_attribs" in params:
        _try_set(n, "repackattribs", bool(params["repack_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "anim_attribs" in params:
        _try_set(n, "animattribs", str(params["anim_attribs"]))
    return _cooked(n)


# ── 11. motion_clip_locomotion (kinefx::motionclipextractlocomotion) — B chain, in0=motionclip ────
@endpoint("motion_clip_locomotion")
def motion_clip_locomotion(params):
    """KineFX MotionClip Extract Locomotion (kinefx::motionclipextractlocomotion) — separates a
    motionclip's (input 0) root locomotion from its in-place motion (compute / prim / joint source),
    optionally extracting the ground trajectory or flattening the clip in place. SECURITY: attribute/
    joint names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipextractlocomotion", params.get("name"))
    if "input" in params:
        _menu_set(n, "input", str(params["input"]), _LOCO_INPUT)
    if "extract" in params:
        _try_set(n, "extract", bool(params["extract"]))
    if "output" in params:
        _menu_set(n, "output", str(params["output"]), _LOCO_OUTPUT)
    if "apply" in params:
        _try_set(n, "apply", bool(params["apply"]))
    if "use_rest" in params:
        _try_set(n, "userest", bool(params["use_rest"]))
    if "locomotion_source" in params:
        _menu_set(n, "locomotionsource", str(params["locomotion_source"]), _LOCO_SRC)
    if "locomotion_joint" in params:
        _try_set(n, "locomotionjoint", str(params["locomotion_joint"]))
    if "com_name" in params:
        _try_set(n, "comtargetname", str(params["com_name"]))
    if "translation_method" in params:
        _int_menu(n, "translationmethod", params["translation_method"], 0, 1)
    if "ground_plane" in params:
        _int_menu(n, "groundplane", params["ground_plane"], 0, 2)
    if "to_origin" in params:
        _try_set(n, "toorigin", bool(params["to_origin"]))
    if "in_place" in params:
        _try_set(n, "inplace", bool(params["in_place"]))
    if "orientation_method" in params:
        _int_menu(n, "orientationmethod", params["orientation_method"], 0, 3)
    if "rotation_order" in params:
        _int_menu(n, "rotationorder", params["rotation_order"], 0, 5)
    return _cooked(n)


# ── 12. motion_clip_merge (kinefx::motionclipmerge) — A source, 0..2 motionclips ─────────────────
@endpoint("motion_clip_merge")
def motion_clip_merge(params):
    """KineFX MotionClip Merge (kinefx::motionclipmerge) — merges two motionclips (input 0 + optional
    `merge_clip` on input 1) into one clip stream. SECURITY: clip name only; no file/code surface."""
    n = child_after(params["input"], "kinefx::motionclipmerge", params.get("name"))
    if params.get("merge_clip"):
        bridge_input(n, params["merge_clip"], index=1, name_hint="merge_clip")
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "merge_input1" in params:
        _try_set(n, "merge1", bool(params["merge_input1"]))
    if "merge_input2" in params:
        _try_set(n, "merge2", bool(params["merge_input2"]))
    return _cooked(n)


# ── 13. motion_clip_pose_delete (kinefx::motionclipposedelete::2.0) — B chain, in0=motionclip ─────
@endpoint("motion_clip_pose_delete")
def motion_clip_pose_delete(params):
    """KineFX MotionClip Pose Delete (kinefx::motionclipposedelete::2.0) — deletes poses (and/or joints)
    from a motionclip (input 0) by frame range, frame pattern, pose range, or pose group. SECURITY:
    group/pattern names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipposedelete::2.0", params.get("name"))
    if "joint_group" in params:
        _try_set(n, "jointgroup", str(params["joint_group"]))
    if "negate_joints" in params:
        _try_set(n, "negatejoints", bool(params["negate_joints"]))
    if "selection_mode" in params:
        _menu_set(n, "selectionmode", str(params["selection_mode"]), _POSEDELETE_SEL)
    if "clip_range_mode" in params:
        _menu_set(n, "cliprangemode", str(params["clip_range_mode"]), _CLIP_RANGE3)
    if "frame_start" in params or "frame_end" in params:
        _set_range(n, "framerange", params.get("frame_start"), params.get("frame_end"))
    if "select_outside_frames" in params:
        _try_set(n, "selectoutsideframes", bool(params["select_outside_frames"]))
    if "select_nth_frame" in params:
        _try_set(n, "selectnthframe", bool(params["select_nth_frame"]))
    if "frame_step" in params:
        _try_set(n, "framestep", int(clamp(int(params["frame_step"]), 1, 1000000)))
    if "frame_offset" in params:
        _try_set(n, "frameoff", int(clamp(int(params["frame_offset"]), -1000000, 1000000)))
    if "frame_pattern" in params:
        _try_set(n, "framepattern", str(params["frame_pattern"]))
    if "pose_group" in params:
        _try_set(n, "posegroup", str(params["pose_group"]))
    return _cooked(n)


# ── 14. motion_clip_pose_insert (kinefx::motionclipposeinsert) — 2 inputs (clip, pose to add) ─────
@endpoint("motion_clip_pose_insert")
def motion_clip_pose_insert(params):
    """KineFX MotionClip Pose Insert (kinefx::motionclipposeinsert) — inserts a single skeleton pose
    (`pose`, input 1) into a motionclip (input 0) at a frame. SECURITY: no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipposeinsert", params.get("name"))
    bridge_input(n, params["pose"], index=1, name_hint="pose")
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "overlap_mode" in params:
        _menu_set(n, "overlapmode", str(params["overlap_mode"]), _POSE_OVERLAP)
    return _cooked(n)


# ── 15. motion_clip_sequence (kinefx::motionclipsequence::2.0) — 2 inputs (first, second clip) ────
@endpoint("motion_clip_sequence")
def motion_clip_sequence(params):
    """KineFX MotionClip Sequence (kinefx::motionclipsequence::2.0) — concatenates two motionclips end
    to end: `first` (input 0) then `second` (input 1), with locomotion continuity and a blended seam.
    SECURITY: attribute/joint names only; no file/code surface."""
    n = child_after(params["first"], "kinefx::motionclipsequence::2.0", params.get("name"))
    bridge_input(n, params["second"], index=1, name_hint="second")
    if "joints" in params:
        _try_set(n, "joints", str(params["joints"]))
    if "sequence_type" in params:
        _menu_set(n, "sequencetype", str(params["sequence_type"]), _SEQ_SEQ)
    if "locomotion" in params:
        _int_menu(n, "locomotion", params["locomotion"], 0, 2)
    if "locomotion_source" in params:
        _menu_set(n, "locomotionsource", str(params["locomotion_source"]), _LOCO_SRC)
    if "locomotion_joint" in params:
        _try_set(n, "locomotionjoint", str(params["locomotion_joint"]))
    if "apply_locomotion" in params:
        _try_set(n, "applylocomotion", bool(params["apply_locomotion"]))
    if "shift_sequence" in params:
        _try_set(n, "shiftsequence", clamp(float(params["shift_sequence"]), -1e6, 1e6))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _SEQ_METHOD)
    if "region" in params:
        _try_set(n, "region", clamp(float(params["region"]), 0.0, 1e6))
    if "set_inc" in params:
        _try_set(n, "setinc", bool(params["set_inc"]))
    if "inc" in params:
        _try_set(n, "inc", clamp(float(params["inc"]), -1e6, 1e6))
    if "blend_mode" in params:
        _int_menu(n, "blendmode", params["blend_mode"], 0, 2)
    if "shape" in params:
        _menu_set(n, "shape", str(params["shape"]), _SHAPE)
    if "bias" in params:
        _try_set(n, "bias", clamp(float(params["bias"]), 0.0, 1.0))
    if "repack_attribs" in params:
        _try_set(n, "repackattribs", bool(params["repack_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "anim_attribs" in params:
        _try_set(n, "animattribs", str(params["anim_attribs"]))
    return _cooked(n)


# ── 16. motion_clip_blend (kinefx::motionclipblend::2.0) — 2 inputs (base, layer) ────────────────
@endpoint("motion_clip_blend")
def motion_clip_blend(params):
    """KineFX MotionClip Blend (kinefx::motionclipblend::2.0) — layers a `layer` motionclip (input 1)
    over a `base` motionclip (input 0) with fade-in/fade-out envelopes and a per-joint blend effect.
    SECURITY: attribute/joint names only; no file/code surface."""
    n = child_after(params["base"], "kinefx::motionclipblend::2.0", params.get("name"))
    bridge_input(n, params["layer"], index=1, name_hint="layer")
    if "joint_names" in params:
        _try_set(n, "jointnames", str(params["joint_names"]))
    if "set_inc" in params:
        _try_set(n, "setinc", bool(params["set_inc"]))
    if "inc" in params:
        _try_set(n, "inc", clamp(float(params["inc"]), -1e6, 1e6))
    if "fade_in" in params:
        _try_set(n, "fadein", bool(params["fade_in"]))
    if "fade_in_start" in params:
        _try_set(n, "start", clamp(float(params["fade_in_start"]), -1e6, 1e6))
    if "fade_in_peak" in params:
        _try_set(n, "peak", clamp(float(params["fade_in_peak"]), -1e6, 1e6))
    if "fade_out" in params:
        _try_set(n, "fadeout", bool(params["fade_out"]))
    if "fade_out_release" in params:
        _try_set(n, "release", clamp(float(params["fade_out_release"]), -1e6, 1e6))
    if "fade_out_end" in params:
        _try_set(n, "end", clamp(float(params["fade_out_end"]), -1e6, 1e6))
    if "locomotion_source" in params:
        _menu_set(n, "locomotionsource", str(params["locomotion_source"]), _LOCO_SRC)
    if "apply_locomotion" in params:
        _try_set(n, "applylocomotion", bool(params["apply_locomotion"]))
    if "blend_mode" in params:
        _int_menu(n, "blendmode", params["blend_mode"], 0, 2)
    if "effect" in params:
        _try_set(n, "effect", clamp(float(params["effect"]), 0.0, 1.0))
    if "blend_shape" in params:
        _menu_set(n, "blend_shape", str(params["blend_shape"]), _SHAPE)
    if "bias" in params:
        _try_set(n, "bias", clamp(float(params["bias"]), 0.0, 1.0))
    if "repack_attribs" in params:
        _try_set(n, "repackattribs", bool(params["repack_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "anim_attribs" in params:
        _try_set(n, "animattribs", str(params["anim_attribs"]))
    return _cooked(n)


# ── 17. motion_clip_unpack (kinefx::motionclipunpack) — B chain, in0=motionclip -> skeleton(s) ────
@endpoint("motion_clip_unpack")
def motion_clip_unpack(params):
    """KineFX MotionClip Unpack (kinefx::motionclipunpack) — unpacks a motionclip (input 0) back to a
    live animated skeleton (single frame / range / current frame), or motion trails, carrying a `time`
    point attribute. SECURITY: attribute names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipunpack", params.get("name"))
    if "joint_names" in params:
        _try_set(n, "jointnames", str(params["joint_names"]))
    if "sample_mode" in params:
        _menu_set(n, "samplemode", str(params["sample_mode"]), _SAMPLE_MODE)
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "interp" in params:
        _menu_set(n, "interp", str(params["interp"]), _INTERP)
    if "output_mode" in params:
        _menu_set(n, "outputmode", str(params["output_mode"]), _EXTRACT_MODE)
    if "unpack_existing" in params:
        _try_set(n, "unpackexisting", bool(params["unpack_existing"]))
    if "clip_range_mode" in params:
        _menu_set(n, "cliprangemode", str(params["clip_range_mode"]), _CLIP_RANGE2)
    if "frame_start" in params or "frame_end" in params or "frame_inc" in params:
        _set_range(n, "framerange", params.get("frame_start"), params.get("frame_end"),
                   params.get("frame_inc"))
    if "use_end_behavior" in params:
        _try_set(n, "useendbehavior", bool(params["use_end_behavior"]))
    if "end_behavior" in params:
        _menu_set(n, "endbehavior", str(params["end_behavior"]), _END)
    if "output_com" in params:
        _try_set(n, "outputcom", bool(params["output_com"]))
    if "isolate_com" in params:
        _try_set(n, "isolatecom", bool(params["isolate_com"]))
    if "com_name" in params:
        _try_set(n, "comname", str(params["com_name"]))
    if "use_attribs" in params:
        _try_set(n, "useattribs", bool(params["use_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "attribs" in params:
        _try_set(n, "attribs", str(params["attribs"]))
    if "output_time" in params:
        _try_set(n, "outputtime", bool(params["output_time"]))
    return _cooked(n)


# ── 18. motion_clip_update (kinefx::motionclipupdate) — 2 inputs (clip, pose stream with `time`) ──
@endpoint("motion_clip_update")
def motion_clip_update(params):
    """KineFX MotionClip Update (kinefx::motionclipupdate) — updates a motionclip (input 0) with new
    poses from `poses` (input 1) — an unpacked skeleton STREAM that MUST carry a `time` point attribute
    (e.g. a motion_clip_unpack output). Adds/replaces joints and poses per the overlap/new modes.
    SECURITY: attribute/joint names only; no file/code surface."""
    n = child_after(params["motionclip"], "kinefx::motionclipupdate", params.get("name"))
    bridge_input(n, params["poses"], index=1, name_hint="poses")
    if "overlap_mode" in params:
        _menu_set(n, "overlapmode", str(params["overlap_mode"]), _UPDATE_OVERLAP)
    if "new_mode" in params:
        _menu_set(n, "newmode", str(params["new_mode"]), _UPDATE_NEW)
    if "use_locals" in params:
        _try_set(n, "uselocals", bool(params["use_locals"]))
    if "repack_attribs" in params:
        _try_set(n, "repackattribs", bool(params["repack_attribs"]))
    if "rest_attribs" in params:
        _try_set(n, "restattribs", str(params["rest_attribs"]))
    if "anim_attribs" in params:
        _try_set(n, "animattribs", str(params["anim_attribs"]))
    if "blend_joints" in params:
        _menu_set(n, "blendjoints", str(params["blend_joints"]), _UPDATE_BLENDJOINTS)
    if "weight_method" in params:
        _menu_set(n, "weightmethod", str(params["weight_method"]), _UPDATE_WEIGHT)
    return _cooked(n)


# ── 19. motion_clip_info (kinefx::motionclipcreateclipinfo) — A source, 0..1 in ──────────────────
@endpoint("motion_clip_info")
def motion_clip_info(params):
    """KineFX MotionClip Create Clip Info (kinefx::motionclipcreateclipinfo) — ensures a motionclip
    (optional input 0) carries a `clipinfo` detail attribute, deriving it from the clip's `time` prim
    attribute when missing. SECURITY: no file/code surface."""
    if params.get("input"):
        n = child_after(params["input"], "kinefx::motionclipcreateclipinfo", params.get("name"))
    else:
        parent = hou.node(params["parent"]) if params.get("parent") else None
        if parent is None:
            raise ValueError("motion_clip_info requires `input` (a motionclip) or `parent` (a geo net)")
        n = parent.createNode("kinefx::motionclipcreateclipinfo", params.get("name"))
        n.moveToGoodPosition()
    return _cooked(n)


# ── 20. motion_mixer_retime (kinefx::motionmixerretime) — B chain, in0=APEX/motionclip scene ──────
@endpoint("motion_mixer_retime")
def motion_mixer_retime(params):
    """KineFX Motion Mixer Retime (kinefx::motionmixerretime) — retimes a motion-mixer / motionclip
    scene (input 0) by absolute frame, time, playback speed, or hold. SECURITY: numeric controls only;
    no file/code surface."""
    n = child_after(params["input"], "kinefx::motionmixerretime", params.get("name"))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _MIXER_RETIME_MODE)
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), -1e3, 1e3))
    if "hold" in params:
        _try_set(n, "hold", int(clamp(int(params["hold"]), -1000000, 1000000)))
    if "frame_start" in params or "frame_end" in params:
        _set_range(n, "frange", params.get("frame_start"), params.get("frame_end"))
    if "rate" in params:
        _try_set(n, "rate", int(clamp(int(params["rate"]), 0, 100000)))
    return _cooked(n)


# ── 21. motion_mixer_smooth (kinefx::motionmixersmooth) — B chain, in0=APEX/motionclip scene ──────
@endpoint("motion_mixer_smooth")
def motion_mixer_smooth(params):
    """KineFX Motion Mixer Smooth (kinefx::motionmixersmooth) — Butterworth-filters the channels of a
    motion-mixer / motionclip scene (input 0) selected by `pattern`, over the t/r/s components.
    SECURITY: channel-name pattern only; no file/code surface."""
    n = child_after(params["input"], "kinefx::motionmixersmooth", params.get("name"))
    if "pattern" in params:
        _try_set(n, "pattern", str(params["pattern"]))
    if "filter_type" in params:
        _menu_set(n, "filtertype", str(params["filter_type"]), _FILTER)
    if "order" in params:
        _try_set(n, "order", int(clamp(int(params["order"]), 1, 12)))
    if "cutoff" in params:
        _try_set(n, "cutoff", clamp(float(params["cutoff"]), 1e-3, 1e4))
    if "components" in params:
        _int_menu(n, "components", params["components"], 0, 7)
    if "rotation_order" in params:
        _menu_set(n, "rord", str(params["rotation_order"]), _ROT_ORDER)
    if "window" in params:
        _try_set(n, "window", int(clamp(int(params["window"]), 0, 100000)))
    if "rate" in params:
        _try_set(n, "rate", clamp(float(params["rate"]), 1e-3, 1e4))
    return _cooked(n)


# ── 22. motion_mixer_transform (kinefx::motionmixertransform) — B chain, in0=APEX/motionclip ──────
@endpoint("motion_mixer_transform")
def motion_mixer_transform(params):
    """KineFX Motion Mixer Transform (kinefx::motionmixertransform) — applies a TRS(+shear/pivot)
    transform to the channels of a motion-mixer / motionclip scene (input 0) selected by `group`.
    SECURITY: group name + numeric transform only; no file/code surface."""
    n = child_after(params["input"], "kinefx::motionmixertransform", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "transform_order" in params:
        _menu_set(n, "xord", str(params["transform_order"]), _XORD)
    if "rotation_order" in params:
        _menu_set(n, "rord", str(params["rotation_order"]), _ROT_ORDER)
    if "translate" in params:
        _try_set_tuple(n, "t", params["translate"])
    if "rotate" in params:
        _try_set_tuple(n, "r", params["rotate"])
    if "scale" in params:
        _try_set_tuple(n, "s", params["scale"])
    if "shear" in params:
        _try_set_tuple(n, "sh", params["shear"])
    if "pivot" in params:
        _try_set_tuple(n, "p", params["pivot"])
    if "pivot_rotate" in params:
        _try_set_tuple(n, "pr", params["pivot_rotate"])
    return _cooked(n)

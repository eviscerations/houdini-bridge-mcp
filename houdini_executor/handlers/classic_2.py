"""Classic rigging — data-only handlers for the SideFX Classic/KineFX **deform-rig** HDA library
(H21.0.671). Params verified live; every endpoint proven with a
headless cook. Category: "KineFX".

Archetype: **A_source (Object-level)**. Every node is an /obj-context rig HDA with 0 inputs and
one object-level output (minNumInputs == maxNumInputs == 0). They are created fresh directly in /obj
(literal `createNode("<exact type>")` per node, so scripts/derive_tool_nodes.py maps tool -> nodetype),
then COOK GREEN bare — the HDA generates a default guide/hook rig internally. There is no single
top-level SOP output on these subnet objects, so the pass criterion is a clean cook (no errors); the
report also counts the populated child guide/hook SOPs (`child_geo`).

Two families:
  * deform_rig_*        — MUSCLE-deform rigs (control_scale / muscle_scale + muscle-display toggles).
  * deform_bone_rig_*   — BONE-deform rigs (display_bones / display_capture_geometry toggles).
Both share the standard Object transform block (translate / rotate / scale / order / keep-position) and
an in-scene `rig_path` reference to the matching animation rig.

SECURITY (data-only):
  * `pickscript` is Houdini's benign viewport pick expression on every Object node — a keyword
    false-positive, NOT a code-entry surface. It is NEVER exposed and left at its HDA default.
  * `rig_path` and the custom-eye scene-object paths are IN-SCENE op/node references, not filesystem
    paths — plain strings, no confinement needed.
  * The ONLY real file surface is the per-eye "From File" eye-geometry path on the two *_head_and_neck
    nodes (`{left,right}_eye_file__eye_from_file_file`). It is routed through `confined_path(...)` so a
    read can never escape the working directory.
  * No node here carries a python/vex/snippet/opencl/callback parm; scale controls are clamped.
"""

import hou
from houdini_executor.server import clamp, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_XFORM_ORDER = ("srt", "str", "rst", "rts", "tsr", "trs")
_ROT_ORDER = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")
_EYE_MODE = ("none", "scene", "file")  # left/right_eye_use_custom_eye: 0=None 1=From Scene 2=From File

_S_LO, _S_HI = 1e-4, 1e4          # scale clamp
_T_LO, _T_HI = -1e6, 1e6          # translate / rotate clamp


def _fresh_obj(name):
    """The /obj container + a fail-on-collision guard (mirrors tree.py `_fresh_geo`). A named rig must
    not silently auto-number onto an existing object — that would make the build non-reproducible."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj


def _obj_cooked(n):
    """Force-cook an Object rig and report the pass criterion (clean cook). These subnet objects have
    no single top-level SOP output, so we also count the populated child guide/hook SOPs."""
    n.cook(force=True)
    errs = n.errors()
    if errs:
        raise RuntimeError("cook errors: %s" % (errs,))
    child_geo = 0
    for c in n.allSubChildren():
        try:
            if isinstance(c, hou.SopNode) and c.isDisplayFlagSet():
                g = c.geometry()
                if g is not None and (len(g.points()) or len(g.prims())):
                    child_geo += 1
        except Exception:
            pass
    return {"node": n.path(), "type": n.type().name(), "cooked": True,
            "errors": [], "child_geo": child_geo}


def _apply_transform(n, params):
    """The standard Object transform block, shared by every rig HDA."""
    if "translate" in params:
        _try_set_tuple(n, "t", [clamp(float(v), _T_LO, _T_HI) for v in params["translate"]])
    if "rotate" in params:
        _try_set_tuple(n, "r", [clamp(float(v), _T_LO, _T_HI) for v in params["rotate"]])
    if "scale_xyz" in params:
        _try_set_tuple(n, "s", [clamp(float(v), _S_LO, _S_HI) for v in params["scale_xyz"]])
    if "uniform_scale" in params:
        _try_set(n, "scale", clamp(float(params["uniform_scale"]), _S_LO, _S_HI))
    if "transform_order" in params:
        _menu_set(n, "xOrd", str(params["transform_order"]), _XFORM_ORDER)
    if "rotation_order" in params:
        _menu_set(n, "rOrd", str(params["rotation_order"]), _ROT_ORDER)
    if "keep_position" in params:
        _try_set(n, "keeppos", bool(params["keep_position"]))
    if "rig_path" in params:
        _try_set(n, "rig_path", str(params["rig_path"]))  # in-scene node ref, not a file


def _apply_eyes(n, params):
    """The per-eye custom-eye controls on the two *_head_and_neck rigs. `*_eye_file` is the ONLY real
    file surface in this lane -> confined_path; the scene-object path is an in-scene node ref."""
    if "display_eyes" in params:
        _try_set(n, "display_eyes", bool(params["display_eyes"]))
    for side in ("left", "right"):
        mode_key = "%s_eye_mode" % side
        scene_key = "%s_eye_scene_object" % side
        file_key = "%s_eye_file" % side
        use_parm = "%s_eye_use_custom_eye" % side
        if mode_key in params:
            _menu_set(n, use_parm, str(params[mode_key]), _EYE_MODE)
        if params.get(scene_key):
            _menu_set(n, use_parm, "scene", _EYE_MODE)
            _try_set(n, "%s_eye_merge__custom_eye_objpath1" % side, str(params[scene_key]))
        if params.get(file_key):
            _menu_set(n, use_parm, "file", _EYE_MODE)
            _try_set(n, "%s_eye_file__eye_from_file_file" % side,
                     confined_path(str(params[file_key])))


def _apply_muscle(n, params):
    """Muscle-deform-rig controls (deform_rig_*)."""
    _apply_transform(n, params)
    if "control_scale" in params:
        _try_set(n, "control_scale", clamp(float(params["control_scale"]), _S_LO, _S_HI))
    if "muscle_scale" in params:
        _try_set(n, "muscle_scale", clamp(float(params["muscle_scale"]), _S_LO, _S_HI))
    if "display_muscles" in params:
        _try_set(n, "display_muscles", bool(params["display_muscles"]))
    if "display_muscle_controls" in params:
        _try_set(n, "display_muscle_controls", bool(params["display_muscle_controls"]))
    if "display_guides" in params:
        _try_set(n, "display_guides", bool(params["display_guides"]))


def _apply_bone(n, params):
    """Bone-deform-rig controls (deform_bone_rig_*)."""
    _apply_transform(n, params)
    if "display_bones" in params:
        _try_set(n, "display_bones", bool(params["display_bones"]))
    if "display_capture_geometry" in params:
        _try_set(n, "display_capture_geometry", bool(params["display_capture_geometry"]))


# ══ BONE-DEFORM RIGS (deform_bone_rig_*) ═════════════════════════════════════════════════════════

@endpoint("deform_bone_rig_quadruped_tail")
def deform_bone_rig_quadruped_tail(params):
    """KineFX Deform Bone Rig Quadruped Tail — an /obj bone-deform rig HDA for a quadruped tail chain
    (A_source: 0 inputs, cooks a default guide/hook rig). `rig_path` references the matching animation
    rig in-scene. SECURITY: data-only; no file/code surface (`pickscript` is Houdini's benign pick
    expression, never exposed)."""
    n = _fresh_obj(params.get("name")).createNode("deform_bone_rig_quadruped_tail", params.get("name"))
    _apply_bone(n, params)
    return _obj_cooked(n)


@endpoint("deform_bone_rig_quadruped_toes_4f")
def deform_bone_rig_quadruped_toes_4f(params):
    """KineFX Deform Bone Rig Quadruped Toes (4 Fingers) — an /obj bone-deform rig HDA for a 4-toe
    quadruped foot (A_source: 0 inputs). `rig_path` references the matching animation rig in-scene.
    SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_bone_rig_quadruped_toes_4f", params.get("name"))
    _apply_bone(n, params)
    return _obj_cooked(n)


@endpoint("deform_bone_rig_quadruped_toes_5f")
def deform_bone_rig_quadruped_toes_5f(params):
    """KineFX Deform Bone Rig Quadruped Toes (5 Fingers) — an /obj bone-deform rig HDA for a 5-toe
    quadruped foot (A_source: 0 inputs). `rig_path` references the matching animation rig in-scene.
    SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_bone_rig_quadruped_toes_5f", params.get("name"))
    _apply_bone(n, params)
    return _obj_cooked(n)


# ══ MUSCLE-DEFORM RIGS (deform_rig_*) ════════════════════════════════════════════════════════════

@endpoint("deform_rig_biped_arm")
def deform_rig_biped_arm(params):
    """KineFX Deform Rig Biped Arm — an /obj muscle-deform rig HDA for a biped arm (A_source: 0 inputs,
    cooks a default muscle/guide rig). `control_scale`/`muscle_scale` size the controls & muscles;
    `rig_path` references the matching animation rig in-scene. SECURITY: data-only; no file/code
    surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_biped_arm", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_biped_hand_4f_2s")
def deform_rig_biped_hand_4f_2s(params):
    """KineFX Deform Rig Biped Hand (4 Fingers, 2 Segments) — an /obj muscle-deform rig HDA for a biped
    hand (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path`
    references the matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_biped_hand_4f_2s", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_biped_hand_4f_3s")
def deform_rig_biped_hand_4f_3s(params):
    """KineFX Deform Rig Biped Hand (4 Fingers, 3 Segments) — an /obj muscle-deform rig HDA for a biped
    hand (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path`
    references the matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_biped_hand_4f_3s", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_biped_hand_5f_3s")
def deform_rig_biped_hand_5f_3s(params):
    """KineFX Deform Rig Biped Hand (5 Fingers, 3 Segments) — an /obj muscle-deform rig HDA for a biped
    hand (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path`
    references the matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_biped_hand_5f_3s", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_biped_head_and_neck")
def deform_rig_biped_head_and_neck(params):
    """KineFX Deform Rig Biped Head and Neck — an /obj muscle-deform rig HDA for a biped head+neck
    (A_source: 0 inputs). Optional per-eye custom eyes: `{left,right}_eye_mode` (none/scene/file);
    `*_eye_scene_object` is an in-scene node ref; `*_eye_file` loads an eye mesh from a file and is the
    ONLY file surface here — confined to the working directory. `rig_path` references the matching
    animation rig in-scene. SECURITY: data-only; eye files confined; no code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_biped_head_and_neck", params.get("name"))
    _apply_muscle(n, params)
    _apply_eyes(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_biped_leg")
def deform_rig_biped_leg(params):
    """KineFX Deform Rig Biped Leg — an /obj muscle-deform rig HDA for a biped leg (A_source: 0 inputs).
    `control_scale`/`muscle_scale` size the controls & muscles; `rig_path` references the matching
    animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_biped_leg", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_biped_spine_3pc")
def deform_rig_biped_spine_3pc(params):
    """KineFX Deform Rig Biped Spine (3 Pieces) — an /obj muscle-deform rig HDA for a 3-piece biped
    spine (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path`
    references the matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_biped_spine_3pc", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_biped_spine_5pc")
def deform_rig_biped_spine_5pc(params):
    """KineFX Deform Rig Biped Spine (5 Pieces) — an /obj muscle-deform rig HDA for a 5-piece biped
    spine (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path`
    references the matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_biped_spine_5pc", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_quadruped_back_leg")
def deform_rig_quadruped_back_leg(params):
    """KineFX Deform Rig Quadruped Back Leg — an /obj muscle-deform rig HDA for a quadruped back leg
    (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path`
    references the matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_quadruped_back_leg", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_quadruped_front_leg")
def deform_rig_quadruped_front_leg(params):
    """KineFX Deform Rig Quadruped Front Leg — an /obj muscle-deform rig HDA for a quadruped front leg
    (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path`
    references the matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_quadruped_front_leg", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_quadruped_head_and_neck")
def deform_rig_quadruped_head_and_neck(params):
    """KineFX Deform Rig Quadruped Head and Neck — an /obj muscle-deform rig HDA for a quadruped
    head+neck (A_source: 0 inputs). Optional per-eye custom eyes: `{left,right}_eye_mode`
    (none/scene/file); `*_eye_scene_object` is an in-scene node ref; `*_eye_file` loads an eye mesh from
    a file and is the ONLY file surface here — confined to the working directory. `rig_path` references
    the matching animation rig in-scene. SECURITY: data-only; eye files confined; no code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_quadruped_head_and_neck", params.get("name"))
    _apply_muscle(n, params)
    _apply_eyes(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_quadruped_ik_spine")
def deform_rig_quadruped_ik_spine(params):
    """KineFX Deform Rig Quadruped IK Spine — an /obj muscle-deform rig HDA for a quadruped IK spine
    (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path`
    references the matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_quadruped_ik_spine", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_quadruped_tail")
def deform_rig_quadruped_tail(params):
    """KineFX Deform Rig Quadruped Tail — an /obj muscle-deform rig HDA for a quadruped tail (A_source:
    0 inputs). `control_scale`/`muscle_scale` size the controls & muscles; `rig_path` references the
    matching animation rig in-scene. SECURITY: data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_quadruped_tail", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_quadruped_toes_4f")
def deform_rig_quadruped_toes_4f(params):
    """KineFX Deform Rig Quadruped Toes (4 Fingers) — an /obj muscle-deform rig HDA for a 4-toe
    quadruped foot (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles;
    `rig_path` references the matching animation rig in-scene. SECURITY: data-only; no file/code
    surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_quadruped_toes_4f", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)


@endpoint("deform_rig_quadruped_toes_5f")
def deform_rig_quadruped_toes_5f(params):
    """KineFX Deform Rig Quadruped Toes (5 Fingers) — an /obj muscle-deform rig HDA for a 5-toe
    quadruped foot (A_source: 0 inputs). `control_scale`/`muscle_scale` size the controls & muscles;
    `rig_path` references the matching animation rig in-scene. SECURITY: data-only; no file/code
    surface."""
    n = _fresh_obj(params.get("name")).createNode("deform_rig_quadruped_toes_5f", params.get("name"))
    _apply_muscle(n, params)
    return _obj_cooked(n)

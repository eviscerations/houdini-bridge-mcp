"""other-anim auto-rig — data-only handlers for the SideFX KineFX **auto-rig / animation-rig
preset** HDA library (H21.0.671). Params verified live; every
endpoint proven with a headless cook. Category: "KineFX".

Archetype: **A_source (Object-level)**. Every node is an /obj-context auto-rig preset HDA with
0 inputs and one object-level output (minNumInputs == maxNumInputs == 0). They are created fresh
directly in /obj (literal `createNode("<exact type>")` per node, so scripts/derive_tool_nodes.py maps
tool -> nodetype), then COOK GREEN bare — the HDA assembles a default control/guide rig internally.
These subnet objects have no single top-level SOP output, so the pass criterion is a clean cook (no
errors); the report also counts the populated child control/guide SOPs (`child_geo`).

Two families (identical control surface):
  * animation_rig_*  — the animation (control) rig presets: biped/quadruped limbs, hands, spine,
    head+neck, tail, toes, plus the character_placer root.
  * auto_rig_*       — the auto-rig builder presets (this lane: biped arm + biped hand 4f/2s).
All share the standard Object transform block (translate / rotate / scale / order / keep-position) and
the KineFX rig control block (control_scale / control_lod / control_color / display toggles). The
`hook_object` and `rig_path` references are IN-SCENE op/node paths, not filesystem paths.

SECURITY (data-only):
  * `pickscript` is Houdini's benign viewport pick expression on every Object node — a keyword
    false-positive, NOT a code-entry surface. It is NEVER exposed and left at its HDA default.
  * `hook_object` / `rig_path` are IN-SCENE node references (op paths), not files — plain strings, no
    confinement needed.
  * No node in this lane carries a python/vex/snippet/opencl/callback/file parm; scale/LOD controls are
    clamped. There is NO filesystem surface in this lane, so `confined_path` is not needed here.
"""

import hou
from houdini_executor.server import clamp, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_XFORM_ORDER = ("srt", "str", "rst", "rts", "tsr", "trs")
_ROT_ORDER = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")

_S_LO, _S_HI = 1e-4, 1e4          # scale clamp
_T_LO, _T_HI = -1e6, 1e6          # translate / rotate clamp
_LOD_LO, _LOD_HI = 0, 32          # control-LOD clamp (cost-linear geo detail)


def _fresh_obj(name):
    """The /obj container + a fail-on-collision guard (mirrors tree.py `_fresh_geo`). A named rig must
    not silently auto-number onto an existing object — that would make the build non-reproducible."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj


def _obj_cooked(n):
    """Force-cook an Object rig and report the pass criterion (clean cook). These subnet objects have
    no single top-level SOP output, so we also count the populated child control/guide SOPs."""
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


def _apply_rig(n, params):
    """Standard transform block + the KineFX auto-rig control block shared by every node.
    All setters are probe-safe (skip a parm the specific preset does not carry)."""
    _apply_transform(n, params)
    if "control_scale" in params:
        _try_set(n, "control_scale", clamp(float(params["control_scale"]), _S_LO, _S_HI))
    if "control_lod" in params:
        _try_set(n, "control_lod", int(clamp(int(params["control_lod"]), _LOD_LO, _LOD_HI)))
    if "control_color" in params:
        _try_set_tuple(n, "control_color", [clamp(float(v), 0.0, 1.0) for v in params["control_color"]])
    if "display_controls" in params:
        _try_set(n, "display_controls", bool(params["display_controls"]))
    if "display_bodypart" in params:
        _try_set(n, "display_bodypart", bool(params["display_bodypart"]))
    if "hook_object" in params:
        _try_set(n, "hook_object", str(params["hook_object"]))   # in-scene node ref, not a file
    if "rig_path" in params:
        _try_set(n, "rig_path", str(params["rig_path"]))         # in-scene node ref, not a file


def _build(type_name, params):
    """Shared A_source build: fresh /obj rig HDA, apply the control block, cook green bare."""
    n = _fresh_obj(params.get("name")).createNode(type_name, params.get("name"))
    _apply_rig(n, params)
    return _obj_cooked(n)


# ══ ANIMATION RIG PRESETS (animation_rig_*) ══════════════════════════════════════════════════════

@endpoint("animation_rig_biped_arm")
def animation_rig_biped_arm(params):
    """KineFX Animation Rig Biped Arm — an /obj animation (control) rig HDA for a biped arm (A_source:
    0 inputs, cooks a default FK/IK control rig). `control_scale`/`control_lod`/`control_color` size &
    style the controls; `hook_object` references a parent object in-scene. SECURITY: data-only; no
    file/code surface (`pickscript` is Houdini's benign pick expression, never exposed)."""
    return _build("animation_rig_biped_arm", params)


@endpoint("animation_rig_biped_hand_4f_2s")
def animation_rig_biped_hand_4f_2s(params):
    """KineFX Animation Rig Biped Hand (4 Fingers, 2 Segments) — an /obj animation rig HDA for a biped
    hand (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_biped_hand_4f_2s", params)


@endpoint("animation_rig_biped_hand_4f_3s")
def animation_rig_biped_hand_4f_3s(params):
    """KineFX Animation Rig Biped Hand (4 Fingers, 3 Segments) — an /obj animation rig HDA for a biped
    hand (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_biped_hand_4f_3s", params)


@endpoint("animation_rig_biped_hand_5f_3s")
def animation_rig_biped_hand_5f_3s(params):
    """KineFX Animation Rig Biped Hand (5 Fingers, 3 Segments) — an /obj animation rig HDA for a biped
    hand (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_biped_hand_5f_3s", params)


@endpoint("animation_rig_biped_head_and_neck")
def animation_rig_biped_head_and_neck(params):
    """KineFX Animation Rig Biped Head and Neck — an /obj animation rig HDA for a biped head+neck
    (A_source: 0 inputs, cooks head/neck/jaw/eye look-at controls). `control_scale`/`control_lod`/
    `control_color` size & style the controls; `hook_object` references a parent object in-scene.
    SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_biped_head_and_neck", params)


@endpoint("animation_rig_biped_leg")
def animation_rig_biped_leg(params):
    """KineFX Animation Rig Biped Leg — an /obj animation rig HDA for a biped leg (A_source: 0 inputs,
    cooks a default FK/IK control rig). `control_scale`/`control_lod`/`control_color` size & style the
    controls; `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code
    surface."""
    return _build("animation_rig_biped_leg", params)


@endpoint("animation_rig_biped_spine_3pc")
def animation_rig_biped_spine_3pc(params):
    """KineFX Animation Rig Biped Spine (3 Pieces) — an /obj animation rig HDA for a 3-piece biped spine
    (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_biped_spine_3pc", params)


@endpoint("animation_rig_biped_spine_5pc")
def animation_rig_biped_spine_5pc(params):
    """KineFX Animation Rig Biped Spine (5 Pieces) — an /obj animation rig HDA for a 5-piece biped spine
    (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_biped_spine_5pc", params)


@endpoint("animation_rig_character_placer")
def animation_rig_character_placer(params):
    """KineFX Animation Rig Character Placer — the /obj root placement rig HDA that positions a whole
    character (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the
    placement controls; `hook_object` references a parent object in-scene. SECURITY: data-only; no
    file/code surface."""
    return _build("animation_rig_character_placer", params)


@endpoint("animation_rig_quadruped_back_leg")
def animation_rig_quadruped_back_leg(params):
    """KineFX Animation Rig Quadruped Back Leg — an /obj animation rig HDA for a quadruped back leg
    (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_quadruped_back_leg", params)


@endpoint("animation_rig_quadruped_front_leg")
def animation_rig_quadruped_front_leg(params):
    """KineFX Animation Rig Quadruped Front Leg — an /obj animation rig HDA for a quadruped front leg
    (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_quadruped_front_leg", params)


@endpoint("animation_rig_quadruped_head_and_neck")
def animation_rig_quadruped_head_and_neck(params):
    """KineFX Animation Rig Quadruped Head and Neck — an /obj animation rig HDA for a quadruped
    head+neck (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the
    controls; `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code
    surface."""
    return _build("animation_rig_quadruped_head_and_neck", params)


@endpoint("animation_rig_quadruped_ik_spine")
def animation_rig_quadruped_ik_spine(params):
    """KineFX Animation Rig Quadruped IK Spine — an /obj animation rig HDA for a quadruped IK spine
    (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_quadruped_ik_spine", params)


@endpoint("animation_rig_quadruped_tail")
def animation_rig_quadruped_tail(params):
    """KineFX Animation Rig Quadruped Tail — an /obj animation rig HDA for a quadruped tail (A_source:
    0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls; `hook_object`
    references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_quadruped_tail", params)


@endpoint("animation_rig_quadruped_toes_4f")
def animation_rig_quadruped_toes_4f(params):
    """KineFX Animation Rig Quadruped Toes (4 Fingers) — an /obj animation rig HDA for a 4-toe quadruped
    foot (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_quadruped_toes_4f", params)


@endpoint("animation_rig_quadruped_toes_5f")
def animation_rig_quadruped_toes_5f(params):
    """KineFX Animation Rig Quadruped Toes (5 Fingers) — an /obj animation rig HDA for a 5-toe quadruped
    foot (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style the controls;
    `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code surface."""
    return _build("animation_rig_quadruped_toes_5f", params)


# ══ AUTO RIG BUILDER PRESETS (auto_rig_*) ════════════════════════════════════════════════════════

@endpoint("auto_rig_biped_arm")
def auto_rig_biped_arm(params):
    """KineFX Auto Rig Biped Arm — an /obj auto-rig builder HDA that assembles a full biped-arm control
    rig from defaults (A_source: 0 inputs). `control_scale`/`control_lod`/`control_color` size & style
    the controls; `hook_object` references a parent object in-scene. SECURITY: data-only; no file/code
    surface (`pickscript` is Houdini's benign pick expression, never exposed)."""
    return _build("auto_rig_biped_arm", params)


@endpoint("auto_rig_biped_hand_4f_2s")
def auto_rig_biped_hand_4f_2s(params):
    """KineFX Auto Rig Biped Hand (4 Fingers, 2 Segments) — an /obj auto-rig builder HDA that assembles
    a full biped-hand control rig from defaults (A_source: 0 inputs). `control_scale`/`control_lod`/
    `control_color` size & style the controls; `hook_object` references a parent object in-scene.
    SECURITY: data-only; no file/code surface."""
    return _build("auto_rig_biped_hand_4f_2s", params)

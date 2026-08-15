"""other-anim auto-rig — data-only handlers for the SideFX KineFX **mocap-rig / mocap-biped /
quadruped-auto-rig / toon-character** Object HDA library (H21.0.671). Params verified live; every
endpoint proven with a headless cook. Category: "KineFX".

Archetype: **A_source (Object-level)**. Every node is an /obj-context HDA. The mocap-rig / quad-rig /
toon nodes take 0 inputs; the mocapbiped test characters take an OPTIONAL 0..1 input (a custom skin /
skeleton) but are BUILT BARE here (0 inputs wired). All are created fresh directly in /obj via a
LITERAL `createNode("<exact type>")` per node (so scripts/derive_tool_nodes.py maps tool -> nodetype
and tag_kinefx_category can allowlist the type), then COOK GREEN — the HDA assembles its default
retarget/character rig internally. These subnet objects have no single top-level SOP output, so the
pass criterion is a clean cook (no errors); the report also counts the populated child guide/control
SOPs (`child_geo`).

Families:
  * mocap_rig_biped_* (arm / head_and_neck / leg / spine_3pc / spine_5pc) — the KineFX mocap-retarget
    rig components. They connect a mocap skeleton to an animation rig: `animation_rig_path` and
    `mocap_skeleton_path` are IN-SCENE node references (op paths, not files); each `*_targetpath` is
    likewise an in-scene target-object reference; `*_bone_length` floats size the default skeleton;
    `side` (arm/leg) picks left/right; `control_scale` sizes the controls.
  * mocap_biped_1 / mocap_biped_2 / mocap_biped_3 (mocapbiped1/2/3) — the pre-built MoCap Biped test
    characters with baked animation clips. `animation`/`anim_types` picks the baked clip; `speed`/
    `frameoffset`/`inplaceanim` retime it; transform + `texture`/`geo_type`/`deform_method` shape the
    output character. No file/code surface (clip selection is a built-in menu, not a path).
  * quadruped_auto_rig_4f / quadruped_auto_rig_5f — the one-call quadruped auto-rig builders (mirror of
    biped_auto_rig). `source_from_scene`/`rig_path` are in-scene refs; `source_from_file`/`library_path`/
    `proxy_file` are the ONLY file surfaces → confined. The `set_rig` Button is NEVER pressed.
  * toon_character — a full pre-built toon character (auto-rig + face + mocap). `source_file`/`save_file`
    and the two eye files are file surfaces → confined; the Read/Write/Match/Generate Buttons are NEVER
    pressed, so nothing is read/written during a cook. The 60+ facial-pose / FK-IK-blend controls are
    ANIMATION-time controls and are intentionally not exposed by this build-time endpoint.

SECURITY (data-only):
  * `pickscript` is Houdini's benign viewport pick expression on every Object node — a keyword
    false-positive flagged in the enumerate, NEVER exposed, left at HDA default.
  * `animation_rig_path`, `mocap_skeleton_path`, every `*_targetpath`, `rig_path`, `source_from_scene`
    are IN-SCENE op/node references (plain strings), not filesystem paths — no confinement needed.
  * The ONLY real file surfaces are: quad-rig `library_path`/`source_from_file`/`proxy_file`; toon
    `source_file`/`save_file`/`left_eye_file`/`right_eye_file`. Every one is routed through
    `confined_path(...)` so a read/write can never escape the working directory.
  * All Buttons (`set_rig`, `generate_mocap`, `read_autorig_data`, `save_autorig_data`, match FK/IK …)
    are NEVER pressed; no node in this lane auto-executes on cook.
"""

import hou
from houdini_executor.server import clamp, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────




def _menu_int(node, parm, value, lo, hi):
    """Set a numeric-token ordered menu by clamped integer index (side / eye_symmetry …)."""
    return _try_set(node, parm, int(clamp(int(value), lo, hi)))


def _menu_token(node, parm, token, tokens):
    """Set a menu parm by token — handles both string-valued menus (set the token) and ordered int
    menus (set the token's index). Probe-safe: unknown token or absent parm is a no-op."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(token)                       # string-valued menu
        return True
    except Exception:
        pass
    if token in tokens:
        try:
            p.set(tokens.index(token))     # ordered int menu
            return True
        except Exception:
            return False
    return False


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_XFORM_ORDER = ("srt", "str", "rst", "rts", "tsr", "trs")
_ROT_ORDER = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")

_S_LO, _S_HI = 1e-4, 1e4          # scale clamp
_T_LO, _T_HI = -1e6, 1e6          # translate / rotate clamp
_LEN_LO, _LEN_HI = 0.0, 1e4       # bone-length clamp (non-negative)
_LOD_LO, _LOD_HI = 0, 32          # control-LOD clamp


def _fresh_obj(name):
    """The /obj container + a fail-on-collision guard (mirrors otheranim_ar2 `_fresh_obj`). A named rig
    must not silently auto-number onto an existing object — that would make the build non-reproducible."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj


def _obj_cooked(n):
    """Force-cook an Object rig and report the pass criterion (clean cook). These subnet objects have
    no single top-level SOP output, so we also count the populated child guide/control SOPs."""
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
    """The standard Object transform block, shared by the mocap-rig / quad-rig / toon nodes."""
    if "translate" in params:
        _try_set_tuple(n, "t", [clamp(float(v), _T_LO, _T_HI) for v in params["translate"]])
    if "rotate" in params:
        _try_set_tuple(n, "r", [clamp(float(v), _T_LO, _T_HI) for v in params["rotate"]])
    if "scale_xyz" in params:
        _try_set_tuple(n, "s", [clamp(float(v), _S_LO, _S_HI) for v in params["scale_xyz"]])
    if "uniform_scale" in params:
        _try_set(n, "scale", clamp(float(params["uniform_scale"]), _S_LO, _S_HI))
    if "transform_order" in params:
        _menu_token(n, "xOrd", str(params["transform_order"]), _XFORM_ORDER)
    if "rotation_order" in params:
        _menu_token(n, "rOrd", str(params["rotation_order"]), _ROT_ORDER)


# ══ MOCAP RETARGET RIG COMPONENTS (mocap_rig_biped_*) ════════════════════════════════════════════

def _build_mocap_rig(ntype, params, has_side=False):
    """Create + configure + cook a KineFX mocap-retarget rig component. Every string ref is an IN-SCENE
    op path (never a file); every `*_bone_length` / `*_reference_r` / `control_scale` is a clamped float.
    Generic + probe-safe: keys the specific component doesn't carry are silently skipped."""
    n = _fresh_obj(params.get("name")).createNode(ntype, params.get("name"))
    _apply_transform(n, params)
    if "animation_rig_path" in params:
        _try_set(n, "animation_rig_path", str(params["animation_rig_path"]))    # in-scene node ref
    if "mocap_skeleton_path" in params:
        _try_set(n, "mocap_skeleton_path", str(params["mocap_skeleton_path"]))  # in-scene node ref
    if has_side and "side" in params:
        _menu_int(n, "side", 1 if str(params["side"]).lower() in ("1", "right", "r") else 0, 0, 1)
    if "control_scale" in params:
        _try_set(n, "control_scale", clamp(float(params["control_scale"]), _S_LO, _S_HI))
    for k, v in params.items():
        if k.endswith("_targetpath"):
            _try_set(n, k, str(v))                                              # in-scene node ref
        elif k.endswith("_bone_length"):
            _try_set(n, k, clamp(float(v), _LEN_LO, _LEN_HI))
        elif k == "ankle_reference_r":
            _try_set_tuple(n, k, [clamp(float(x), _T_LO, _T_HI) for x in v])
    return _obj_cooked(n)


@endpoint("mocap_rig_biped_arm")
def mocap_rig_biped_arm(params):
    """KineFX Mocap Rig Biped Arm — an /obj mocap-retarget rig HDA that drives a biped-arm animation rig
    from a mocap skeleton (A_source: 0 inputs). `animation_rig_path`/`mocap_skeleton_path` and every
    `*_targetpath` are IN-SCENE node refs (not files); `side` picks left/right; `*_bone_length` size the
    default skeleton. Data-only; no file/code surface."""
    return _build_mocap_rig("mocap_rig_biped_arm", params, has_side=True)


@endpoint("mocap_rig_biped_head_and_neck")
def mocap_rig_biped_head_and_neck(params):
    """KineFX Mocap Rig Biped Head and Neck — an /obj mocap-retarget rig HDA that drives a biped
    head+neck animation rig from a mocap skeleton (A_source: 0 inputs). `animation_rig_path`/
    `mocap_skeleton_path` and every `*_targetpath` are IN-SCENE node refs; `*_bone_length` size the
    default skeleton. Data-only; no file/code surface."""
    return _build_mocap_rig("mocap_rig_biped_head_and_neck", params)


@endpoint("mocap_rig_biped_leg")
def mocap_rig_biped_leg(params):
    """KineFX Mocap Rig Biped Leg — an /obj mocap-retarget rig HDA that drives a biped-leg animation rig
    from a mocap skeleton (A_source: 0 inputs). `animation_rig_path`/`mocap_skeleton_path` and every
    `*_targetpath` are IN-SCENE node refs; `side` picks left/right; `ankle_reference_r` and the
    `*_bone_length` floats shape the default skeleton. Data-only; no file/code surface."""
    return _build_mocap_rig("mocap_rig_biped_leg", params, has_side=True)


@endpoint("mocap_rig_biped_spine_3pc")
def mocap_rig_biped_spine_3pc(params):
    """KineFX Mocap Rig Biped Spine (3 Pieces) — an /obj mocap-retarget rig HDA that drives a 3-piece
    biped spine animation rig from a mocap skeleton (A_source: 0 inputs). `animation_rig_path`/
    `mocap_skeleton_path` and every `*_targetpath` are IN-SCENE node refs; `*_bone_length` size the
    default skeleton. Data-only; no file/code surface."""
    return _build_mocap_rig("mocap_rig_biped_spine_3pc", params)


@endpoint("mocap_rig_biped_spine_5pc")
def mocap_rig_biped_spine_5pc(params):
    """KineFX Mocap Rig Biped Spine (5 Pieces) — an /obj mocap-retarget rig HDA that drives a 5-piece
    biped spine animation rig from a mocap skeleton (A_source: 0 inputs). `animation_rig_path`/
    `mocap_skeleton_path` and every `*_targetpath` are IN-SCENE node refs; `*_bone_length` size the
    default skeleton. Data-only; no file/code surface."""
    return _build_mocap_rig("mocap_rig_biped_spine_5pc", params)


# ══ MOCAP BIPED TEST CHARACTERS (mocapbiped1/2/3) ════════════════════════════════════════════════

def _apply_mocapbiped_common(n, params):
    """Shared retime/style controls for the mocap-biped test characters."""
    if "inplace_animation" in params:
        _try_set(n, "inplaceanim", bool(params["inplace_animation"]))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e3))
    if "frame_offset" in params:
        _try_set(n, "frameoffset", clamp(float(params["frame_offset"]), -1e5, 1e5))
    if "texture" in params:
        _try_set(n, "texture", int(clamp(int(params["texture"]), 0, 64)))
    if "geo_type" in params:
        _try_set(n, "geoType", int(clamp(int(params["geo_type"]), 0, 8)))


_MB1_ANIM = ("walk", "run", "wait", "standing", "zombie", "rest")
_MB2_ANIM = ("jogging", "running", "sitcheer", "sitinteract", "sittostandcheer", "sittostand",
             "standcheer", "standinteract", "standlook", "standtalk", "standtositclap", "standtowalk",
             "walkfast", "walknormal", "rest")


@endpoint("mocap_biped_1")
def mocap_biped_1(params):
    """KineFX MoCap Biped 1 — a pre-built MoCap Biped test character with baked locomotion clips
    (A_source: built bare, 0 inputs wired). `animation` picks the baked clip (walk/run/wait/standing/
    zombie/rest); `speed`/`frame_offset`/`inplace_animation` retime it; `translate`/`rotate`/`scale`
    place the character; `texture`/`geo_type` style it. Data-only; clip selection is a built-in menu,
    no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("mocapbiped1", params.get("name"))
    _try_set_tuple(n, "t2", params["translate"]) if "translate" in params else None
    _try_set_tuple(n, "r2", params["rotate"]) if "rotate" in params else None
    _try_set_tuple(n, "s2", params["scale_xyz"]) if "scale_xyz" in params else None
    if "animation" in params:
        _menu_token(n, "animation", str(params["animation"]), _MB1_ANIM)
    _apply_mocapbiped_common(n, params)
    return _obj_cooked(n)


@endpoint("mocap_biped_2")
def mocap_biped_2(params):
    """KineFX MoCap Biped 2 — a pre-built MoCap Biped test character with a large baked clip library
    (A_source: built bare, 0 inputs wired). `animation` picks the baked clip (jogging/running/
    sit*/stand*/walk* … rest); `speed`/`frame_offset`/`inplace_animation` retime it; `translate`/
    `rotate`/`scale` place it; `texture`/`geo_type` style it. Data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("mocapbiped2", params.get("name"))
    _try_set_tuple(n, "t2", params["translate"]) if "translate" in params else None
    _try_set_tuple(n, "r2", params["rotate"]) if "rotate" in params else None
    _try_set_tuple(n, "s2", params["scale_xyz"]) if "scale_xyz" in params else None
    if "animation" in params:
        _menu_token(n, "animation", str(params["animation"]), _MB2_ANIM)
    _apply_mocapbiped_common(n, params)
    return _obj_cooked(n)


_MB3_ANIMTYPES = ("walks_and_turns", "runs", "stadium", "zombie", "inclines", "injured", "steps",
                  "poses")
_MB3_DEFORM = ("linear", "dualquat")
_MB3_TEXTURES = ("casual", "military", "zombie")


@endpoint("mocap_biped_3")
def mocap_biped_3(params):
    """KineFX MoCap Biped 3 — the advanced pre-built MoCap Biped test character with a categorized clip
    library and motion-matching (A_source: built bare, 0 inputs wired). `animation_type` picks the clip
    category (walks_and_turns/runs/stadium/zombie/inclines/injured/steps/poses); `speed`/`frame_offset`/
    `n_frames`/`inplace_animation`/`extend_match` control playback; `deform_method` (linear/dualquat)
    and `texture_set` (casual/military/zombie) style the output; `master_translate`/`master_rotate`/
    `uniform_scale` place it. Data-only; clip selection is a built-in menu, no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("mocapbiped3", params.get("name"))
    _try_set_tuple(n, "master_trans", params["master_translate"]) if "master_translate" in params else None
    _try_set_tuple(n, "master_rotate", params["master_rotate"]) if "master_rotate" in params else None
    if "uniform_scale" in params:
        _try_set(n, "uniform_scale", clamp(float(params["uniform_scale"]), _S_LO, _S_HI))
    if "animation_type" in params:
        _menu_token(n, "anim_types", str(params["animation_type"]), _MB3_ANIMTYPES)
    if "deform_method" in params:
        _menu_token(n, "deformmethod", str(params["deform_method"]), _MB3_DEFORM)
    if "texture_set" in params:
        _menu_token(n, "textures", str(params["texture_set"]), _MB3_TEXTURES)
    if "n_frames" in params:
        _try_set(n, "nFrames", int(clamp(int(params["n_frames"]), 1, 100000)))
    if "extend_match" in params:
        _try_set(n, "extendMatch", bool(params["extend_match"]))
    _apply_mocapbiped_common(n, params)
    return _obj_cooked(n)


# ══ QUADRUPED AUTO-RIG BUILDERS (quadruped_auto_rig_4f/5f) ═══════════════════════════════════════

def _build_quad_autorig(ntype, params):
    """Create + configure + cook a one-call quadruped auto-rig (mirror of biped_auto_rig). The source is
    EITHER an in-scene object OR a confined on-disk file/library; the `set_rig` Button is NEVER pressed."""
    n = _fresh_obj(params.get("name")).createNode(ntype, params.get("name"))
    _apply_transform(n, params)
    if "character_name" in params:
        _try_set(n, "character_name", str(params["character_name"]))
    if "character_scale" in params:
        _try_set(n, "character_scale", clamp(float(params["character_scale"]), _S_LO, _S_HI))
    if "symmetry" in params:
        _try_set(n, "symmetry", int(bool(params["symmetry"])))
    if "source_geometry" in params:
        _try_set(n, "source_geometry", int(bool(params["source_geometry"])))
    if "source_from_scene" in params:
        _try_set(n, "source_from_scene", str(params["source_from_scene"]))   # in-scene node ref
    if params.get("source_from_file"):
        _try_set(n, "source_from_file", confined_path(str(params["source_from_file"])))
    if params.get("library_path"):
        _try_set(n, "library_path", confined_path(str(params["library_path"])))
    if params.get("proxy_file"):
        _try_set(n, "proxy_file", confined_path(str(params["proxy_file"])))
    if "deform_type" in params:
        _try_set(n, "deform_type", int(clamp(int(params["deform_type"]), 0, 8)))
    if "mode" in params:
        _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 8)))
    if "layout" in params:
        _try_set(n, "layout", int(clamp(int(params["layout"]), 0, 8)))
    if "rig_path" in params:
        _try_set(n, "rig_path", str(params["rig_path"]))                     # in-scene node ref
    if "eye_symmetry" in params:
        _menu_int(n, "head_and_neck_eye_symmetry", params["eye_symmetry"], 0, 1)
    for k in ("front_left_leg_disable_toe", "back_left_leg_disable_toe",
              "front_right_leg_disable_toe", "back_right_leg_disable_toe"):
        if k in params:
            _try_set(n, k, bool(params[k]))
    if "display_controls" in params:
        _try_set(n, "display_controls", bool(params["display_controls"]))
    if "display_proxy_controls" in params:
        _try_set(n, "display_proxy_controls", bool(params["display_proxy_controls"]))
    if "display_wire" in params:
        _try_set(n, "display_wire", bool(params["display_wire"]))
    if "control_scale" in params:
        _try_set(n, "control_scale", clamp(float(params["control_scale"]), _S_LO, _S_HI))
    return _obj_cooked(n)


@endpoint("quadruped_auto_rig_4f")
def quadruped_auto_rig_4f(params):
    """KineFX Quadruped Auto Rig (4 Toes) — an /obj one-call HDA that builds a full default 4-toe
    quadruped control rig (A_source: 0 inputs). `deform_type`/`mode`/`layout` pick deform style / build
    mode / anim-parm layout; `source_from_scene`/`rig_path` are in-scene refs; `source_from_file`/
    `library_path`/`proxy_file` are the ONLY file surfaces → confined; the per-leg `*_disable_toe`
    toggles drop toe joints. The `set_rig` Button is never pressed. Data-only; no code surface."""
    return _build_quad_autorig("quadruped_auto_rig_4f", params)


@endpoint("quadruped_auto_rig_5f")
def quadruped_auto_rig_5f(params):
    """KineFX Quadruped Auto Rig (5 Toes) — an /obj one-call HDA that builds a full default 5-toe
    quadruped control rig (A_source: 0 inputs). `deform_type`/`mode`/`layout` pick deform style / build
    mode / anim-parm layout; `source_from_scene`/`rig_path` are in-scene refs; `source_from_file`/
    `library_path`/`proxy_file` are the ONLY file surfaces → confined; the per-leg `*_disable_toe`
    toggles drop toe joints. The `set_rig` Button is never pressed. Data-only; no code surface."""
    return _build_quad_autorig("quadruped_auto_rig_5f", params)


# ══ TOON CHARACTER (toon_character) ══════════════════════════════════════════════════════════════

_TOON_LEFT_EYE = "toon_character_deform_rig_head_and_neck_left_eye_file__eye_from_file_file"
_TOON_RIGHT_EYE = "toon_character_deform_rig_head_and_neck_right_eye_file__eye_from_file_file"


@endpoint("toon_character")
def toon_character(params):
    """KineFX Toon Character — an /obj HDA that builds a full pre-rigged toon character (auto-rig + face
    + mocap) from defaults (A_source: 0 inputs). `rig_scale`/`control_lod` size the controls;
    `display_bones`/`refit_tolerance` and the character-placer transform tune the build. `source_file`/
    `save_file`/`left_eye_file`/`right_eye_file` are the ONLY file surfaces → confined; the Read/Write/
    Generate-Mocap/Match-FK-IK Buttons are NEVER pressed, so nothing is read or written on cook. The
    facial-pose / FK-IK-blend controls are animation-time controls and are not exposed here. Data-only;
    no code surface."""
    n = _fresh_obj(params.get("name")).createNode("toon_character", params.get("name"))
    _apply_transform(n, params)
    if "rig_scale" in params:
        _try_set(n, "rig_scale", clamp(float(params["rig_scale"]), _S_LO, _S_HI))
    if "control_lod" in params:
        _try_set(n, "control_lod", int(clamp(int(params["control_lod"]), _LOD_LO, _LOD_HI)))
    if "display_bones" in params:
        _try_set(n, "display_bones", bool(params["display_bones"]))
    if "refit_tolerance" in params:
        _try_set(n, "refit_tolerance", clamp(float(params["refit_tolerance"]), 0.0, 1e3))
    # character-placer transform (the placer sub-block, distinct from the Object transform)
    if "placer_translate" in params:
        _try_set_tuple(n, "character_placer_character_placer_translate", params["placer_translate"])
    if "placer_rotate" in params:
        _try_set_tuple(n, "character_placer_character_rotate", params["placer_rotate"])
    if "placer_scale" in params:
        _try_set(n, "character_placer_character_scale",
                 clamp(float(params["placer_scale"]), _S_LO, _S_HI))
    # file surfaces — confined, never auto-read/written (the driving Buttons are never pressed)
    if params.get("source_file"):
        _try_set(n, "source_file_path", confined_path(str(params["source_file"])))
    if params.get("save_file"):
        _try_set(n, "save_file_path", confined_path(str(params["save_file"])))
    if params.get("left_eye_file"):
        _try_set(n, _TOON_LEFT_EYE, confined_path(str(params["left_eye_file"])))
    if params.get("right_eye_file"):
        _try_set(n, _TOON_RIGHT_EYE, confined_path(str(params["right_eye_file"])))
    return _obj_cooked(n)

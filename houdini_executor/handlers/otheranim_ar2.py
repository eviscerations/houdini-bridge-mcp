"""other-anim auto-rig — data-only handlers for the SideFX KineFX/Classic **auto-rig HDA**
library (H21.0.671). Params verified live; every endpoint proven
with a headless cook. Category: "KineFX".

Archetype: **A_source (Object-level)**. Every node here is an /obj-context auto-rig HDA. All create with
0 inputs (`auto_rig_eye` accepts an optional 0..1 skin input but is built bare) and one object-level
output; they are created fresh directly in /obj via a LITERAL `createNode("<exact type>")` per node (so
scripts/derive_tool_nodes.py maps tool -> nodetype and tag_kinefx_category can allowlist the type), then
COOK GREEN bare — the HDA generates a default guide/control rig internally. These subnet objects have no
single top-level SOP output, so the pass criterion is a clean cook (no errors); the report also counts
the populated child guide/control SOPs (`child_geo`).

Families (all share the standard Object transform block):
  * auto_rig_<limb/spine/tail> — a rig COMPONENT (hand/leg/spine/head/tail/toes). Shared controls:
    `hook_object`/`rig_path` (in-scene node refs), `control_scale`, display toggles, `layer`; the
    left/right components add `side` + `symmetry_override`; legs add a `character_placer` ref +
    `disable_toe`; head/neck adds `eye_symmetry`; the quad spine/head add an extra bone-display toggle.
  * auto_rig_character_placer / biped_auto_rig — the PLACER + one-call biped rig: `character_name`,
    `character_scale`, `symmetry`, and a source (scene object OR a confined `source_from_file`/
    `library_path`/`proxy_file` on disk).
  * auto_rig_eye — a single eye rig; optional custom eye from an in-scene object or a confined file.
  * labs::impostor_camera_rig — an impostor camera rig referencing an in-scene Impostor ROP.
  * mcacclaim (Mocap Acclaim) — an ASF/AMC mocap-import Object; the .asf skeleton, .amc motion clips and
    output folder are the file surfaces (all confined); the auto-load toggle is forced OFF and the
    Load/Clear buttons are NEVER pressed (data-only, no read on cook).

SECURITY (data-only):
  * `pickscript` is Houdini's benign viewport pick expression on every Object node — a keyword
    false-positive flagged in the enumerate, NEVER exposed, left at HDA default.
  * `rig_path`, `hook_object`, `character_placer`, `source_from_scene`, the eye scene object,
    `impostor_rop`, `shop_materialpath` are IN-SCENE op/node references (plain strings), not filesystem
    paths — no confinement needed.
  * The ONLY real file surfaces are: character_placer/biped_auto_rig `library_path`/`source_from_file`/
    `proxy_file`; auto_rig_eye `file__eye_from_file_file`; mcacclaim `asf`/`outdir`/`motion#`. Every one
    is routed through `confined_path(...)` so a read/write can never escape the working directory.
  * mcacclaim `cmdout`/`ikchainslist` (code parms) are NEVER set/exposed; `autoloadmotions` is forced
    OFF so no file is read during a cook. `set_rig`/`load`/`clear`/`load_amc` are Buttons — never pressed.
"""

import hou
from houdini_executor.server import clamp, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _menu_int(node, parm, value, lo, hi):
    """Set a numeric-token menu parm by clamped integer index (side/ikmode/bonelen/eye_symmetry…)."""
    return _try_set(node, parm, int(clamp(int(value), lo, hi)))


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_XFORM_ORDER = ("srt", "str", "rst", "rts", "tsr", "trs")
_ROT_ORDER = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")

_S_LO, _S_HI = 1e-4, 1e4          # scale clamp
_T_LO, _T_HI = -1e6, 1e6          # translate / rotate clamp
_LAYER_LO, _LAYER_HI = 0, 64      # animation-layer index clamp


def _fresh_obj(name):
    """The /obj container + a fail-on-collision guard (mirrors classic_2.py `_fresh_obj`). A named rig
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
    """The standard Object transform block, shared by every wave node."""
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


def _apply_rig_common(n, params):
    """Shared auto-rig-component controls (in-scene refs + display toggles + control scale + layer)."""
    if "hook_object" in params:
        _try_set(n, "hook_object", str(params["hook_object"]))      # in-scene node ref
    if "rig_path" in params:
        _try_set(n, "rig_path", str(params["rig_path"]))            # in-scene node ref
    if "layer" in params:
        _try_set(n, "layer", int(clamp(int(params["layer"]), _LAYER_LO, _LAYER_HI)))
    if "display_controls" in params:
        _try_set(n, "display_controls", bool(params["display_controls"]))
    if "display_proxy_controls" in params:
        _try_set(n, "display_proxy_controls", bool(params["display_proxy_controls"]))
    if "display_wire" in params:
        _try_set(n, "display_wire", bool(params["display_wire"]))
    if "control_scale" in params:
        _try_set(n, "control_scale", clamp(float(params["control_scale"]), _S_LO, _S_HI))


def _apply_side(n, params):
    """Left/right side selector + symmetry override (hands, legs, quad legs, quad toes)."""
    if "side" in params:
        _menu_int(n, "side", params["side"], 0, 1)                  # 0=left 1=right
    if "symmetry_override" in params:
        _try_set(n, "symmetry_override", bool(params["symmetry_override"]))


def _build_component(ntype, params, side=False, extra=None):
    """Create + configure + cook a standard auto-rig COMPONENT HDA (the common code path for the 15
    auto_rig_* limb/spine/tail/head nodes)."""
    n = _fresh_obj(params.get("name")).createNode(ntype, params.get("name"))
    _apply_transform(n, params)
    _apply_rig_common(n, params)
    if side:
        _apply_side(n, params)
    if extra:
        extra(n, params)
    return _obj_cooked(n)


# ══ BIPED COMPONENTS ═════════════════════════════════════════════════════════════════════════════

@endpoint("auto_rig_biped_hand_4f_3s")
def auto_rig_biped_hand_4f_3s(params):
    """KineFX Auto Rig Biped Hand (4 Fingers, 3 Segments) — an /obj auto-rig HDA that builds a default
    4-finger biped hand control rig (A_source: 0 inputs). `side` picks left/right; `rig_path`/
    `hook_object` are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_biped_hand_4f_3s", params, side=True)


@endpoint("auto_rig_biped_hand_5f_3s")
def auto_rig_biped_hand_5f_3s(params):
    """KineFX Auto Rig Biped Hand (5 Fingers, 3 Segments) — an /obj auto-rig HDA that builds a default
    5-finger biped hand control rig (A_source: 0 inputs). `side` picks left/right; `rig_path`/
    `hook_object` are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_biped_hand_5f_3s", params, side=True)


def _extra_head_neck(n, params):
    if "eye_symmetry" in params:
        _menu_int(n, "eye_symmetry", params["eye_symmetry"], 0, 1)


@endpoint("auto_rig_biped_head_and_neck")
def auto_rig_biped_head_and_neck(params):
    """KineFX Auto Rig Biped Head and Neck — an /obj auto-rig HDA that builds a default biped head+neck
    control rig (A_source: 0 inputs). `eye_symmetry` toggles mirrored eyes; `rig_path`/`hook_object`
    are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_biped_head_and_neck", params, side=False, extra=_extra_head_neck)


def _extra_disable_toe(n, params):
    if "character_placer" in params:
        _try_set(n, "character_placer", str(params["character_placer"]))   # in-scene node ref
    if "disable_toe" in params:
        _try_set(n, "disable_toe", bool(params["disable_toe"]))


@endpoint("auto_rig_biped_leg")
def auto_rig_biped_leg(params):
    """KineFX Auto Rig Biped Leg — an /obj auto-rig HDA that builds a default biped leg control rig
    (A_source: 0 inputs). `side` picks left/right; `disable_toe` drops the toe joint; `character_placer`/
    `rig_path`/`hook_object` are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_biped_leg", params, side=True, extra=_extra_disable_toe)


@endpoint("auto_rig_biped_spine_3pc")
def auto_rig_biped_spine_3pc(params):
    """KineFX Auto Rig Biped Spine (3 Pieces) — an /obj auto-rig HDA that builds a default 3-piece biped
    spine control rig (A_source: 0 inputs). `rig_path`/`hook_object` are in-scene node refs. Data-only;
    no file/code surface."""
    return _build_component("auto_rig_biped_spine_3pc", params)


@endpoint("auto_rig_biped_spine_5pc")
def auto_rig_biped_spine_5pc(params):
    """KineFX Auto Rig Biped Spine (5 Pieces) — an /obj auto-rig HDA that builds a default 5-piece biped
    spine control rig (A_source: 0 inputs). `rig_path`/`hook_object` are in-scene node refs. Data-only;
    no file/code surface."""
    return _build_component("auto_rig_biped_spine_5pc", params)


# ══ QUADRUPED COMPONENTS ═════════════════════════════════════════════════════════════════════════

@endpoint("auto_rig_quadruped_back_leg")
def auto_rig_quadruped_back_leg(params):
    """KineFX Auto Rig Quadruped Back Leg — an /obj auto-rig HDA that builds a default quadruped back-leg
    control rig (A_source: 0 inputs). `side` picks left/right; `disable_toe` drops the toe;
    `character_placer`/`rig_path`/`hook_object` are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_quadruped_back_leg", params, side=True, extra=_extra_disable_toe)


@endpoint("auto_rig_quadruped_front_leg")
def auto_rig_quadruped_front_leg(params):
    """KineFX Auto Rig Quadruped Front Leg — an /obj auto-rig HDA that builds a default quadruped
    front-leg control rig (A_source: 0 inputs). `side` picks left/right; `disable_toe` drops the toe;
    `character_placer`/`rig_path`/`hook_object` are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_quadruped_front_leg", params, side=True, extra=_extra_disable_toe)


def _extra_quad_head_neck(n, params):
    if "character_placer" in params:
        _try_set(n, "character_placer", str(params["character_placer"]))   # in-scene node ref
    if "display_neck_bone_controls" in params:
        _try_set(n, "display_neck_bone_controls", bool(params["display_neck_bone_controls"]))
    if "eye_symmetry" in params:
        _menu_int(n, "eye_symmetry", params["eye_symmetry"], 0, 1)


@endpoint("auto_rig_quadruped_head_and_neck")
def auto_rig_quadruped_head_and_neck(params):
    """KineFX Auto Rig Quadruped Head and Neck — an /obj auto-rig HDA that builds a default quadruped
    head+neck control rig (A_source: 0 inputs). `display_neck_bone_controls` shows per-bone neck
    controls; `eye_symmetry` mirrors eyes; `character_placer`/`rig_path`/`hook_object` are in-scene node
    refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_quadruped_head_and_neck", params, extra=_extra_quad_head_neck)


def _extra_quad_ik_spine(n, params):
    if "display_spine_bone_controls" in params:
        _try_set(n, "display_spine_bone_controls", bool(params["display_spine_bone_controls"]))


@endpoint("auto_rig_quadruped_ik_spine")
def auto_rig_quadruped_ik_spine(params):
    """KineFX Auto Rig Quadruped IK Spine — an /obj auto-rig HDA that builds a default quadruped IK-spine
    control rig (A_source: 0 inputs). `display_spine_bone_controls` shows per-bone spine controls;
    `rig_path`/`hook_object` are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_quadruped_ik_spine", params, extra=_extra_quad_ik_spine)


@endpoint("auto_rig_quadruped_tail")
def auto_rig_quadruped_tail(params):
    """KineFX Auto Rig Quadruped Tail — an /obj auto-rig HDA that builds a default quadruped tail control
    rig (A_source: 0 inputs). `rig_path`/`hook_object` are in-scene node refs. Data-only; no file/code
    surface."""
    return _build_component("auto_rig_quadruped_tail", params)


def _extra_quad_toes(n, params):
    """Quad toe rigs use two hook refs (thumb + toe) instead of the single `hook_object`, plus side."""
    if "thumb_hook_object" in params:
        _try_set(n, "thumb_hook_object", str(params["thumb_hook_object"]))   # in-scene node ref
    if "toe_hook_object" in params:
        _try_set(n, "toe_hook_object", str(params["toe_hook_object"]))       # in-scene node ref
    _apply_side(n, params)


@endpoint("auto_rig_quadruped_toes_4f")
def auto_rig_quadruped_toes_4f(params):
    """KineFX Auto Rig Quadruped Toes (4 Fingers) — an /obj auto-rig HDA that builds a default 4-toe
    quadruped foot control rig (A_source: 0 inputs). `side` picks left/right; `thumb_hook_object`/
    `toe_hook_object`/`rig_path` are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_quadruped_toes_4f", params, extra=_extra_quad_toes)


@endpoint("auto_rig_quadruped_toes_5f")
def auto_rig_quadruped_toes_5f(params):
    """KineFX Auto Rig Quadruped Toes (5 Fingers) — an /obj auto-rig HDA that builds a default 5-toe
    quadruped foot control rig (A_source: 0 inputs). `side` picks left/right; `thumb_hook_object`/
    `toe_hook_object`/`rig_path` are in-scene node refs. Data-only; no file/code surface."""
    return _build_component("auto_rig_quadruped_toes_5f", params, extra=_extra_quad_toes)


# ══ PLACER / ONE-CALL RIG / EYE ══════════════════════════════════════════════════════════════════

def _apply_source(n, params):
    """Shared source block for the placer + one-call biped rig: character name/scale/symmetry and a
    source that is EITHER an in-scene scene object OR a confined on-disk file/library."""
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


@endpoint("auto_rig_character_placer")
def auto_rig_character_placer(params):
    """KineFX Auto Rig Character Placer — an /obj auto-rig HDA that lays out the placement guides a rig is
    built from (A_source: 0 inputs). `source_from_scene` is an in-scene object; `source_from_file`/
    `library_path` are the ONLY file surfaces → confined to the working directory. Data-only; no code
    surface."""
    n = _fresh_obj(params.get("name")).createNode("auto_rig_character_placer", params.get("name"))
    _apply_transform(n, params)
    _apply_source(n, params)
    if "layer" in params:
        _try_set(n, "layer", int(clamp(int(params["layer"]), _LAYER_LO, _LAYER_HI)))
    if "display_controls" in params:
        _try_set(n, "display_controls", bool(params["display_controls"]))
    if "control_scale" in params:
        _try_set(n, "control_scale", clamp(float(params["control_scale"]), _S_LO, _S_HI))
    return _obj_cooked(n)


@endpoint("biped_auto_rig")
def biped_auto_rig(params):
    """KineFX Biped Auto Rig — an /obj one-call HDA that builds a full default biped control rig
    (A_source: 0 inputs). `deform_type`/`mode`/`layout` pick the deform style / build mode / anim-parm
    layout; `source_from_scene` is an in-scene object; `source_from_file`/`library_path`/`proxy_file` are
    the ONLY file surfaces → confined. `rig_path` is an in-scene node ref. Data-only; no code surface."""
    n = _fresh_obj(params.get("name")).createNode("biped_auto_rig", params.get("name"))
    _apply_transform(n, params)
    _apply_source(n, params)
    if params.get("proxy_file"):
        _try_set(n, "proxy_file", confined_path(str(params["proxy_file"])))
    if "deform_type" in params:
        _try_set(n, "deform_type", int(clamp(int(params["deform_type"]), 0, 8)))
    if "mode" in params:
        _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 8)))
    if "layout" in params:
        _try_set(n, "layout", int(clamp(int(params["layout"]), 0, 8)))
    if "rig_path" in params:
        _try_set(n, "rig_path", str(params["rig_path"]))            # in-scene node ref
    if "display_controls" in params:
        _try_set(n, "display_controls", bool(params["display_controls"]))
    if "display_proxy_controls" in params:
        _try_set(n, "display_proxy_controls", bool(params["display_proxy_controls"]))
    if "display_wire" in params:
        _try_set(n, "display_wire", bool(params["display_wire"]))
    if "control_scale" in params:
        _try_set(n, "control_scale", clamp(float(params["control_scale"]), _S_LO, _S_HI))
    return _obj_cooked(n)


@endpoint("auto_rig_eye")
def auto_rig_eye(params):
    """KineFX Auto Rig Eye — an /obj auto-rig HDA that builds a single eye rig (A_source: 0 inputs).
    `use_custom_eye` (0=none, 1=from scene, 2=from file): `eye_scene_object` is an in-scene object;
    `eye_file` loads an eye mesh from disk and is the ONLY file surface → confined. `material` is an
    in-scene material ref. Data-only; no code surface."""
    n = _fresh_obj(params.get("name")).createNode("auto_rig_eye", params.get("name"))
    _apply_transform(n, params)
    if "use_custom_eye" in params:
        _menu_int(n, "use_custom_eye", params["use_custom_eye"], 0, 2)
    if params.get("eye_scene_object"):
        _menu_int(n, "use_custom_eye", 1, 0, 2)
        _try_set(n, "merge__custom_eye_objpath1", str(params["eye_scene_object"]))  # in-scene ref
    if params.get("eye_file"):
        _menu_int(n, "use_custom_eye", 2, 0, 2)
        _try_set(n, "file__eye_from_file_file", confined_path(str(params["eye_file"])))
    if "material" in params:
        _try_set(n, "shop_materialpath", str(params["material"]))   # in-scene material ref
    if "display_eye" in params:
        _try_set(n, "display_eye", bool(params["display_eye"]))
    if "renderable" in params:
        _try_set(n, "renderable", bool(params["renderable"]))
    return _obj_cooked(n)


# ══ IMPOSTOR CAMERA RIG (Labs) ═══════════════════════════════════════════════════════════════════

@endpoint("impostor_camera_rig")
def impostor_camera_rig(params):
    """KineFX Labs Impostor Camera Rig — an /obj rig HDA that builds the multi-view camera rig an
    impostor bake shoots from (A_source: 0 inputs). `impostor_rop` references the in-scene Impostor ROP
    (a node path, not a file); the ROP is NEVER executed. Data-only; no file/code surface."""
    n = _fresh_obj(params.get("name")).createNode("labs::impostor_camera_rig", params.get("name"))
    _apply_transform(n, params)
    if "impostor_rop" in params:
        _try_set(n, "impostor_rop", str(params["impostor_rop"]))   # in-scene ROP ref
    return _obj_cooked(n)


# ══ MOCAP ACCLAIM (ASF/AMC import) ═══════════════════════════════════════════════════════════════

@endpoint("mocap_acclaim")
def mocap_acclaim(params):
    """KineFX Mocap Acclaim — an /obj mocap-import HDA for Acclaim ASF/AMC motion capture (A_source: 0
    inputs, cooks green empty until a skeleton is set). `asf` (skeleton), `motion_file` (AMC clip) and
    `output_folder` are file surfaces → all confined to the working directory. `autoloadmotions` is
    FORCED OFF and the Load/Clear buttons are NEVER pressed, so nothing is read on cook (data-only).
    `ikmode`/`bonelen`/`dualchains`/`ikchains` shape the imported skeleton; code parms are never set."""
    n = _fresh_obj(params.get("name")).createNode("mcacclaim", params.get("name"))
    _apply_transform(n, params)
    _try_set(n, "autoloadmotions", False)   # security: never auto-read files during a cook
    if params.get("asf"):
        _try_set(n, "asf", confined_path(str(params["asf"])))
    if params.get("output_folder"):
        _try_set(n, "outdir", confined_path(str(params["output_folder"])))
    # `motions` = optional list (internal/recipe use); `motion_file` = single clip (MCP schema surface).
    mots = list(params["motions"]) if params.get("motions") else []
    if params.get("motion_file"):
        mots.append(str(params["motion_file"]))
    if mots:
        mots = mots[:64]
        _try_set(n, "motionnum", len(mots))
        for i, m in enumerate(mots, start=1):
            _try_set(n, "motion%d" % i, confined_path(str(m)))
    if "framerate" in params:
        _try_set(n, "framerate", int(clamp(int(params["framerate"]), 1, 1000)))
    if "ik_mode" in params:
        _menu_int(n, "ikmode", params["ik_mode"], 0, 1)
    if "bone_length" in params:
        _menu_int(n, "bonelen", params["bone_length"], 0, 2)
    if "dual_chains" in params:
        _try_set(n, "dualchains", bool(params["dual_chains"]))
    if "ik_chains" in params:
        _try_set(n, "ikchains", bool(params["ik_chains"]))
    if "keep_temp_files" in params:
        _try_set(n, "keeptmp", bool(params["keep_temp_files"]))
    return _obj_cooked(n)

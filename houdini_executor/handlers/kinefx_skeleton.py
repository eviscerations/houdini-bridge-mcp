"""KineFX Skeleton authoring & joint ops — data-only handlers. Params verified against live
H21.0.671; every endpoint proven with a headless cook over the
reusable fixture (a 4-joint skeleton + proximity-captured tube).

Archetypes (mirror the Labs A/B/C mapping):
  A source  : character_skeleton (kinefx::skeleton) — passthrough/animation-transfer container.
  B chain   : the rest — input0 = the skeleton/rig; a few take an optional input1 (reference geo /
              skin / blend target / motionclip). Correct input index is wired explicitly.

SECURITY (KineFX lane, data-only): none of these nodes carries a file or code/callback parm
(scout-confirmed file_parms=[] / has_code_parm=false for all twelve). So there is NO file surface to
confine and NO code parm is ever set/exposed here. String params surfaced are attribute / group /
token NAMES (Regular strings), never paths or code. configurerigvis is SKIPPED (only an interactive
`configurations` multiparm — no data-only scalar surface).
"""

import hou
from houdini_executor.server import clamp, child_after, bridge_input, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _cooked(n):
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_ROT_ORDER = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")
_CJ_MODE = ("fbik", "rlimits", "limits")               # Full Body IK / Ragdoll / Rig Pose
_CJ_INPUTTYPE = ("skin", "shapes")
_DEL_OP = ("dele", "keep")                             # Delete Selected / Delete Non-Selected
_GRP_MERGE = ("replace", "union", "intersect", "subtract")
_GRP_OP = ("dele", "keep")                             # Selected / Non-Selected
_SB_MASKMODE = ("none", "setfromattrib", "scalefromattrib")
_SB_MASKATTRIBMODE = ("each", "first")
_SM_TOKENPOS = ("start", "middle", "end")
_SM_STYLE = ("byrotation", "byscale")
_SM_REFLECT = ("mirrorplane", "mirrorpoint")
_AXIS = ("x", "y", "z")
_RD_METHOD = ("stash", "timeshift")
_RD_ONFAIL = ("warning", "error")
_JOINT_STYLE = ("gnomon", "hats")
_VR_DISPLAY = ("output", "rig_vis")


# ── 1. character_skeleton (kinefx::skeleton) — A source / passthrough container ───────────────────
@endpoint("character_skeleton")
def character_skeleton(params):
    """KineFX Skeleton (kinefx::skeleton) — the skeleton authoring container. Wraps an existing
    skeleton on `skeleton` (input 0): optionally transfers the input's animation onto the rest pose and
    caches the output. (Named `character_skeleton` to avoid colliding with the Labs `straight_skeleton`
    medial-axis tools.) SECURITY: no file/code surface; the interactive joint-stash is not touched."""
    n = child_after(params["skeleton"], "kinefx::skeleton", params.get("name"))
    if "transfer_animation" in params:
        _try_set(n, "transferanimation", bool(params["transfer_animation"]))
    if "cache_output" in params:
        _try_set(n, "cacheoutput", bool(params["cache_output"]))
    if "joint_color" in params:
        _try_set_tuple(n, "jointcolor", params["joint_color"])
    return _cooked(n)


# ── 2. configure_joints (kinefx::configurejoints) — B chain, input0=skeleton ─────────────────────
@endpoint("configure_joints")
def configure_joints(params):
    """KineFX Configure Joints (kinefx::configurejoints) — writes solver-configuration attributes onto
    a skeleton (input 0) for Full Body IK / Ragdoll / Rig Pose. Optional `skin` (input 1) supplies mass
    / center-of-mass geometry; optional `motionclip` (input 2) supplies joint-limit ranges. SECURITY:
    string params are attribute names only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::configurejoints", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if params.get("motionclip"):
        bridge_input(n, params["motionclip"], index=2, name_hint="motionclip")
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _CJ_MODE)
    if "rotation_order" in params:
        _menu_set(n, "rOrd", str(params["rotation_order"]), _ROT_ORDER)
    if "output_attrib" in params:
        _try_set(n, "outputconfigurationattrib", str(params["output_attrib"]))
    if "use_rest_pose" in params:
        _try_set(n, "userestposeattrib", bool(params["use_rest_pose"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "add_com_point" in params:
        _try_set(n, "addcompoint", bool(params["add_com_point"]))
    if "com_point_name" in params:
        _try_set(n, "comtargetname", str(params["com_point_name"]))
    if "compute_com" in params:
        _try_set(n, "computelocalcom", bool(params["compute_com"]))
    if "input_type" in params:
        _menu_set(n, "inputtype", str(params["input_type"]), _CJ_INPUTTYPE)
    if "compute_limits" in params:
        _try_set(n, "computelimits", bool(params["compute_limits"]))
    if "rotation_limits" in params:
        _try_set(n, "computerlimits", bool(params["rotation_limits"]))
    if "translation_limits" in params:
        _try_set(n, "computetlimits", bool(params["translation_limits"]))
    return _cooked(n)


# ── 3. configure_joint_limits (kinefx::configurejointlimits) — B chain, input0=skeleton ──────────
@endpoint("configure_joint_limits")
def configure_joint_limits(params):
    """KineFX Configure Joint Limits (kinefx::configurejointlimits) — sets rotation/translation joint
    limits + limit-guide display on a skeleton (input 0). Optional `motionclip` (input 1) auto-computes
    limit ranges from a captured motion. SECURITY: attribute/group names only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::configurejointlimits", params.get("name"))
    if params.get("motionclip"):
        bridge_input(n, params["motionclip"], index=1, name_hint="motionclip")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "output_attrib" in params:
        _try_set(n, "outputconfigurationattrib", str(params["output_attrib"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "init_from_rig" in params:
        _try_set(n, "initlimitsfromrig", bool(params["init_from_rig"]))
    if "compute_limits" in params:
        _try_set(n, "computelimits", bool(params["compute_limits"]))
    if "limits_group" in params:
        _try_set(n, "limitsjointgrp", str(params["limits_group"]))
    if "rotation_order" in params:
        _menu_set(n, "rOrd", str(params["rotation_order"]), _ROT_ORDER)
    if "rotation_limits" in params:
        _try_set(n, "computerlimits", bool(params["rotation_limits"]))
    if "translation_limits" in params:
        _try_set(n, "computetlimits", bool(params["translation_limits"]))
    if "display_rotation_limits" in params:
        _try_set(n, "displayrotationlimits", bool(params["display_rotation_limits"]))
    if "display_translation_limits" in params:
        _try_set(n, "displaytranslationlimits", bool(params["display_translation_limits"]))
    if "guide_scale" in params:
        _try_set(n, "guidegeoscale", clamp(float(params["guide_scale"]), 1e-3, 1e3))
    return _cooked(n)


# ── 4. orient_joints (kinefx::orientjoints) — B chain, input0=skeleton, input1=opt lookat geo ────
@endpoint("orient_joints")
def orient_joints(params):
    """KineFX Orient Joints (kinefx::orientjoints) — recomputes joint orientations (the `transform`
    point attrib) for a skeleton (input 0), aiming each joint at its child with a reference/up vector.
    Optional `lookat` (input 1) supplies per-joint look-at target geometry. SECURITY: group/attribute
    names only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::orientjoints", params.get("name"))
    if params.get("lookat"):
        bridge_input(n, params["lookat"], index=1, name_hint="lookat")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "targets" in params:
        _try_set(n, "targets", str(params["targets"]))
    if "use_reference_vector" in params:
        _try_set(n, "use_ref_vector", bool(params["use_reference_vector"]))
    if "reference_vector" in params:
        _try_set_tuple(n, "ref_vector", params["reference_vector"])
    if "use_up_vector" in params:
        _try_set(n, "use_up_vector", bool(params["use_up_vector"]))
    if "up_vector" in params:
        _try_set_tuple(n, "up_vector", params["up_vector"])
    if "use_parent_for_leaf" in params:
        _try_set(n, "use_parent_for_leaf", bool(params["use_parent_for_leaf"]))
    if "orient_overlapping" in params:
        _try_set(n, "orientoverlapping", bool(params["orient_overlapping"]))
    return _cooked(n)


# ── 5. parent_joints (kinefx::parentjoints) — B chain, input0=skeleton ───────────────────────────
@endpoint("parent_joints")
def parent_joints(params):
    """KineFX Parent Joints (kinefx::parentjoints) — reparents joints in a skeleton hierarchy (input 0).
    The parent/child assignments themselves are an interactive multiparm (not data-only settable), so
    this endpoint exposes the one scalar control, `unparent_on_cycle`, and passes the rig through when
    no assignments are set. SECURITY: no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::parentjoints", params.get("name"))
    if "unparent_on_cycle" in params:
        _try_set(n, "unparentoncycle", bool(params["unparent_on_cycle"]))
    return _cooked(n)


# ── 6. delete_joints (kinefx::deletejoints) — B chain, input0=skeleton ───────────────────────────
@endpoint("delete_joints")
def delete_joints(params):
    """KineFX Delete Joints (kinefx::deletejoints) — deletes (or keeps only) the joints named by
    `group` from a skeleton (input 0), optionally cascading to their children. SECURITY: group name
    only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::deletejoints", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "operation" in params:
        _menu_set(n, "negate", str(params["operation"]), _DEL_OP)
    if "delete_selected" in params:
        _try_set(n, "delete", bool(params["delete_selected"]))
    if "delete_children" in params:
        _try_set(n, "children", bool(params["delete_children"]))
    return _cooked(n)


# ── 7. group_joints (kinefx::groupjoints) — B chain, input0=skeleton ─────────────────────────────
@endpoint("group_joints")
def group_joints(params):
    """KineFX Group Joints (kinefx::groupjoints) — creates/updates a named point group of joints on a
    skeleton (input 0) from a selection expression, with a boolean merge against any existing group.
    SECURITY: group names only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::groupjoints", params.get("name"))
    if "group_name" in params:
        _try_set(n, "groupname", str(params["group_name"]))
    if "merge_op" in params:
        _menu_set(n, "mergeop", str(params["merge_op"]), _GRP_MERGE)
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "operation" in params:
        _menu_set(n, "negate", str(params["operation"]), _GRP_OP)
    if "select_joints" in params:
        _try_set(n, "delete", bool(params["select_joints"]))
    if "select_children" in params:
        _try_set(n, "children", bool(params["select_children"]))
    return _cooked(n)


# ── 8. skeleton_blend (kinefx::skeletonblend::3.0) — B chain, input0=base, input1+=blend targets ─
@endpoint("skeleton_blend")
def skeleton_blend(params):
    """KineFX Skeleton Blend (kinefx::skeletonblend::3.0) — blends the pose of one or more skeletons
    into a base skeleton. `skeleton` (input 0) = the base rig; `blend_skeleton` (input 1) = the target
    rig; `weight` sets the second input's blend amount. Supports difference/world-space blending and
    attribute-mask weighting. SECURITY: attribute/group names only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::skeletonblend::3.0", params.get("name"))
    if params.get("blend_skeleton"):
        bridge_input(n, params["blend_skeleton"], index=1, name_hint="blend_skeleton")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "match_by_attrib" in params:
        _try_set(n, "matchattrib", bool(params["match_by_attrib"]))
    if "attrib_to_match" in params:
        _try_set(n, "attribtomatch", str(params["attrib_to_match"]))
    if "blend_to_pose" in params:
        _try_set(n, "blendtopose", bool(params["blend_to_pose"]))
    if "pose_attrib" in params:
        _try_set(n, "poseattrib", str(params["pose_attrib"]))
    if "pose_weight" in params:
        _try_set(n, "poseweight", clamp(float(params["pose_weight"]), 0.0, 1.0))
    if "difference_blend" in params:
        _try_set(n, "differenceblend", bool(params["difference_blend"]))
    if "world_space" in params:
        _try_set(n, "worldspace", bool(params["world_space"]))
    if "mask_mode" in params:
        _menu_set(n, "maskmode", str(params["mask_mode"]), _SB_MASKMODE)
    if "mask_attrib" in params:
        _try_set(n, "maskattrib", str(params["mask_attrib"]))
    if "mask_source" in params:
        _menu_set(n, "maskattribmode", str(params["mask_source"]), _SB_MASKATTRIBMODE)
    if "weight" in params:
        _try_set(n, "weight1", clamp(float(params["weight"]), 0.0, 1.0))
    return _cooked(n)


# ── 9. skeleton_mirror (kinefx::skeletonmirror) — B chain, input0=skeleton ───────────────────────
@endpoint("skeleton_mirror")
def skeleton_mirror(params):
    """KineFX Skeleton Mirror (kinefx::skeletonmirror) — mirrors joints of a skeleton (input 0) across a
    plane or point, renaming mirrored joints via find/replace tokens (e.g. `_l` -> `_r`). Named
    `skeleton_mirror` to avoid colliding with the generic `mirror` tool. SECURITY: attribute/group/
    token names only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::skeletonmirror", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "transform_attribs" in params:
        _try_set(n, "transformattribs", str(params["transform_attribs"]))
    if "mirror_groups" in params:
        _try_set(n, "domirrorgroups", bool(params["mirror_groups"]))
    if "mirror_style" in params:
        _menu_set(n, "mirroringstyle", str(params["mirror_style"]), _SM_STYLE)
    if "reflect_using" in params:
        _menu_set(n, "reflectusing", str(params["reflect_using"]), _SM_REFLECT)
    if "direction" in params:
        _try_set_tuple(n, "dir", params["direction"])
    if "origin" in params:
        _try_set_tuple(n, "origin", params["origin"])
    if "token_position" in params:
        _menu_set(n, "tokenpos", str(params["token_position"]), _SM_TOKENPOS)
    if "find_tokens" in params:
        _try_set(n, "findtokens", str(params["find_tokens"]))
    if "replace_tokens" in params:
        _try_set(n, "replacetokens", str(params["replace_tokens"]))
    if "reference_point" in params:
        _try_set(n, "refpoint", str(params["reference_point"]))
    if "reference_point_axis" in params:
        _menu_set(n, "refpointaxis", str(params["reference_point_axis"]), _AXIS)
    return _cooked(n)


# ── 10. rig_doctor (kinefx::rigdoctor) — B chain, input0=skeleton ────────────────────────────────
@endpoint("rig_doctor")
def rig_doctor(params):
    """KineFX Rig Doctor (kinefx::rigdoctor) — validates & repairs a skeleton: initializes missing
    joint names / transforms, sanitizes names, and outputs hierarchy attributes (parent index, child
    indices, evaluation order) from a rig on input 0. The standard rig-cleanup / debug tool. SECURITY:
    attribute/name strings only; no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::rigdoctor", params.get("name"))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _RD_METHOD)
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "init_missing_names" in params:
        _try_set(n, "initmissingnames", bool(params["init_missing_names"]))
    if "name_prefix" in params:
        _try_set(n, "nameprefix", str(params["name_prefix"]))
    if "sanitize_names" in params:
        _try_set(n, "sanitizenames", bool(params["sanitize_names"]))
    if "store_input_name" in params:
        _try_set(n, "storeinputname", bool(params["store_input_name"]))
    if "on_failure" in params:
        _menu_set(n, "onfailure", str(params["on_failure"]), _RD_ONFAIL)
    if "init_transforms" in params:
        _try_set(n, "inittransforms", bool(params["init_transforms"]))
    if "convert_instance_attribs" in params:
        _try_set(n, "convertinstanceattribs", bool(params["convert_instance_attribs"]))
    if "reorient_to_child" in params:
        _try_set(n, "reorienttochild", bool(params["reorient_to_child"]))
    if "vector_to_child" in params:
        _try_set_tuple(n, "ref_vector", params["vector_to_child"])
    if "output_parent_index" in params:
        _try_set(n, "outputparentidx", bool(params["output_parent_index"]))
    if "output_child_indices" in params:
        _try_set(n, "outputchildindices", bool(params["output_child_indices"]))
    if "output_eval_order" in params:
        _try_set(n, "outputevalord", bool(params["output_eval_order"]))
    if "joint_scale" in params:
        _try_set(n, "jointscale", clamp(float(params["joint_scale"]), 1e-3, 1e4))
    return _cooked(n)


# ── 11. visualize_rig (kinefx::visrig) — B chain, input0=skeleton ────────────────────────────────
@endpoint("visualize_rig")
def visualize_rig(params):
    """KineFX Visualize Rig (kinefx::visrig) — generates rig-visualization geometry (joint gnomons /
    bone links, styled by color/scale) from a skeleton on input 0. `display` picks passthrough
    (`output`) vs the generated visualization (`rig_vis`). SECURITY: color/scale values only; no
    file/code surface."""
    n = child_after(params["skeleton"], "kinefx::visrig", params.get("name"))
    if "display" in params:
        _menu_set(n, "display", str(params["display"]), _VR_DISPLAY)
    if "joint_style" in params:
        _menu_set(n, "jointstyle", str(params["joint_style"]), _JOINT_STYLE)
    if "show_direction" in params:
        _try_set(n, "showdirection", bool(params["show_direction"]))
    if "override_joint_color" in params:
        _try_set(n, "usejointcolor", bool(params["override_joint_color"]))
    if "joint_color" in params:
        _try_set_tuple(n, "jointcolor", params["joint_color"])
    if "override_link_color" in params:
        _try_set(n, "uselinkcolor", bool(params["override_link_color"]))
    if "link_color" in params:
        _try_set_tuple(n, "linkcolor", params["link_color"])
    if "use_lighting" in params:
        _try_set(n, "uselighting", bool(params["use_lighting"]))
    if "ignore_scales" in params:
        _try_set(n, "ignorescales", bool(params["ignore_scales"]))
    if "joint_scale" in params:
        _try_set(n, "jointscale", clamp(float(params["joint_scale"]), 1e-3, 1e4))
    return _cooked(n)

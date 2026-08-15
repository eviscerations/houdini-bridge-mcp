"""KineFX Rig pose / IK-FK — data-only handlers. Params verified against live H21.0.671; every endpoint proven with a headless cook over the reusable fixture
(a 4-joint skeleton; two-input nodes wired to a second fixture skeleton).

Archetype: all B_chain (input0 = a skeleton/rig). Four nodes REQUIRE a second input (min 2):
  rig_match_pose (in1=source skeleton), rig_copy_transforms (in1=source skeleton),
  ik_chains (in1=IK targets), pose_difference (in1=reference pose). The correct input index is wired
  explicitly (child_after -> input0; bridge_input(index=1) -> input1). The rest take input0 only, with
  a few carrying an OPTIONAL input1/2 (rig_stash_pose, full_body_ik, fbik_configure_targets,
  reverse_foot, stabilize_joint).

SECURITY (KineFX lane, data-only): live probe confirms file_parms=[] for every node here — there is NO
file surface to confine. Two nodes carry a scout-flagged has_code_parm and it is NEVER exposed or set:
  * kinefx::rigpose `commands` (an interactive pose-edit command FolderSet) — left at default;
  * kinefx::fullbodyik `mappings` (target->joint mapping payload) — left at default.
All surfaced string params are attribute / group / joint-name tokens (Regular strings), never paths or
code. Interactive multiparms (the IK-chain list, FBIK target `configurations`, reverse-foot per-foot
entries) are not data-only settable, so those nodes pass the rig through and expose only their safe
scalar controls (mirrors `parent_joints`).
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
_OUT_PASS = ("passthrough", "matchedpose")
_GLOBALXFORM = ("targetskeleton", "sourceskeleton")
_CLIPINFO = ("clipinfo", "custom")
_MIRROR_OP = ("mirrorpose", "computemirroring")
_RESTPOSE_SRC = ("restframe", "restattrib")
_SYMAXIS = ("X", "Y", "Z")
_MIRROR_METHOD = ("fromnames", "levenstein")
_TOKENPOS = ("start", "middle", "end")
_REFLECT = ("mirrorplane", "mirrorpoint")
_AXIS = ("x", "y", "z")
_FLIPFROM = ("user", "restpose")
_STASH_MODE = ("store", "restore")
_STASH_METHOD = ("timeshift", "stash")
_MAPUSING = ("mappingattrib", "matchattrib")
_SOLVER = ("solvefbik", "solvephysfbik")
_NEGATE = ("dele", "keep")
_SPLINE_TOTYPE = ("bezCurve", "nurbCurve")
_SPLINE_MODE = ("secondaryaxis", "slideframe")
_SPLINE_AXIS6 = ("negx", "negy", "negz", "x", "y", "z")
_SPLINE_AXIS4 = ("negx", "negy", "x", "y")
_PD_MAPUSING = ("mappingattrib", "matchattrib", "ptnum")
_PD_USETRANSFORM = ("transform", "localtransform", "custom")
_PD_STORECOMP = ("position", "rotation", "scale")


# ── 1. rig_pose (kinefx::rigpose) — B chain, input0=skeleton ─────────────────────────────────────
@endpoint("rig_pose")
def rig_pose(params):
    """KineFX Rig Pose (kinefx::rigpose) — the interactive FK/IK posing SOP on a skeleton (input 0).
    The pose itself is authored through interactive handles (the `commands` FolderSet — a code-shaped
    payload that is NEVER touched here), so data-only this node passes the input pose through and
    exposes its safe evaluation + output-attribute controls (world-space, rest-pose bake, which
    transform attributes to write). SECURITY: no file surface; `commands` left at default."""
    n = child_after(params["skeleton"], "kinefx::rigpose", params.get("name"))
    if "world_space" in params:
        _try_set(n, "worldspace", bool(params["world_space"]))
    if "bake_from_rest_pose" in params:
        _try_set(n, "bakefromrestpose", bool(params["bake_from_rest_pose"]))
    if "rest_attrib" in params:
        _try_set(n, "restattrib", str(params["rest_attrib"]))
    if "multithread" in params:
        _try_set(n, "multithread", bool(params["multithread"]))
    if "preserve_shears" in params:
        _try_set(n, "preserveshears", bool(params["preserve_shears"]))
    if "output_parm_attribs" in params:
        _try_set(n, "outputparmattribs", bool(params["output_parm_attribs"]))
    if "output_translate" in params:
        _try_set(n, "outputparmt", bool(params["output_translate"]))
    if "output_rotate" in params:
        _try_set(n, "outputparmr", bool(params["output_rotate"]))
    if "output_scale" in params:
        _try_set(n, "outputparms", bool(params["output_scale"]))
    if "output_pivot" in params:
        _try_set(n, "outputparmp", bool(params["output_pivot"]))
    if "output_pivot_rotate" in params:
        _try_set(n, "outputparmpr", bool(params["output_pivot_rotate"]))
    if "output_internal_attribs" in params:
        _try_set(n, "outputinternalattribs", bool(params["output_internal_attribs"]))
    if "output_local_transform" in params:
        _try_set(n, "outputlocaltransform", bool(params["output_local_transform"]))
    if "output_input_local_transform" in params:
        _try_set(n, "outputinputlocaltransform", bool(params["output_input_local_transform"]))
    if "output_effective_local_transform" in params:
        _try_set(n, "outputeffectivelocaltransform",
                 bool(params["output_effective_local_transform"]))
    return _cooked(n)


# ── 2. compute_rig_pose (kinefx::computerigpose) — B chain, input0=skeleton ──────────────────────
@endpoint("compute_rig_pose")
def compute_rig_pose(params):
    """KineFX Compute Rig Pose (kinefx::computerigpose) — evaluates a rig pose from a skeleton (input 0)
    and bakes the resulting transforms/parameter attributes back onto the geometry. The headless twin
    of rig_pose (no interactive handles): use it to resolve a pose in a graph. SECURITY: no file/code
    surface; string params are attribute names only."""
    n = child_after(params["skeleton"], "kinefx::computerigpose", params.get("name"))
    if "rest_attrib" in params:
        _try_set(n, "restattrib", str(params["rest_attrib"]))
    if "world_space" in params:
        _try_set(n, "worldspace", bool(params["world_space"]))
    if "multithread" in params:
        _try_set(n, "multithread", bool(params["multithread"]))
    if "preserve_shears" in params:
        _try_set(n, "preserveshears", bool(params["preserve_shears"]))
    if "output_parm_attribs" in params:
        _try_set(n, "outputparmattribs", bool(params["output_parm_attribs"]))
    if "output_translate" in params:
        _try_set(n, "outputparmt", bool(params["output_translate"]))
    if "output_rotate" in params:
        _try_set(n, "outputparmr", bool(params["output_rotate"]))
    if "output_scale" in params:
        _try_set(n, "outputparms", bool(params["output_scale"]))
    if "output_pivot" in params:
        _try_set(n, "outputparmp", bool(params["output_pivot"]))
    if "output_pivot_rotate" in params:
        _try_set(n, "outputparmpr", bool(params["output_pivot_rotate"]))
    if "output_internal_attribs" in params:
        _try_set(n, "outputinternalattribs", bool(params["output_internal_attribs"]))
    if "output_local_transform" in params:
        _try_set(n, "outputlocaltransform", bool(params["output_local_transform"]))
    if "output_input_local_transform" in params:
        _try_set(n, "outputinputlocaltransform", bool(params["output_input_local_transform"]))
    if "output_effective_local_transform" in params:
        _try_set(n, "outputeffectivelocaltransform",
                 bool(params["output_effective_local_transform"]))
    return _cooked(n)


# ── 3. rig_match_pose (kinefx::rigmatchpose) — B chain, input0=target, input1=source (required) ──
@endpoint("rig_match_pose")
def rig_match_pose(params):
    """KineFX Rig Match Pose (kinefx::rigmatchpose) — poses the `skeleton` (input 0, the target rig) to
    match the pose of `source` (input 1, the source rig), optionally aligning by bounding box and a
    reference frame. Both inputs are required. SECURITY: no file/code surface; string params are
    attribute / point-group names only."""
    n = child_after(params["skeleton"], "kinefx::rigmatchpose", params.get("name"))
    bridge_input(n, params["source"], index=1, name_hint="source")
    if "joint_scale" in params:
        _try_set(n, "joint_scale", clamp(float(params["joint_scale"]), 1e-3, 1e4))
    if "pose_attrib" in params:
        _try_set(n, "poseattrib", str(params["pose_attrib"]))
    if "store_ref_pose" in params:
        _try_set(n, "storerefpose", bool(params["store_ref_pose"]))
    if "first_output" in params:
        _menu_set(n, "firstoutput", str(params["first_output"]), _OUT_PASS)
    if "second_output" in params:
        _menu_set(n, "secondoutput", str(params["second_output"]), _OUT_PASS)
    if "global_xform_skeleton" in params:
        _menu_set(n, "globalxformskel", str(params["global_xform_skeleton"]), _GLOBALXFORM)
    if "stash_attrib" in params:
        _try_set(n, "stashattrib", str(params["stash_attrib"]))
    if "bbox_match" in params:
        _try_set(n, "bboxmatch", bool(params["bbox_match"]))
    if "set_pivot_from_bbox" in params:
        _try_set(n, "setpivotfrombbox", bool(params["set_pivot_from_bbox"]))
    if "target_points" in params:
        _try_set(n, "targetpoints", str(params["target_points"]))
    if "ref_points" in params:
        _try_set(n, "refpoints", str(params["ref_points"]))
    if "rest_frame_target" in params:
        _menu_set(n, "restframetarget", str(params["rest_frame_target"]), _CLIPINFO)
    if "ref_frame" in params:
        _try_set(n, "refframe", int(clamp(int(params["ref_frame"]), -1000000, 1000000)))
    if "rest_frame_source" in params:
        _menu_set(n, "restframesource", str(params["rest_frame_source"]), _CLIPINFO)
    if "ref_frame_source" in params:
        _try_set(n, "refframesource", int(clamp(int(params["ref_frame_source"]), -1000000, 1000000)))
    if "scene_scale" in params:
        _try_set(n, "scene_scale", clamp(float(params["scene_scale"]), 1e-6, 1e6))
    if "preserve_shears" in params:
        _try_set(n, "preserveshears", bool(params["preserve_shears"]))
    return _cooked(n)


# ── 4. rig_mirror_pose (kinefx::rigmirrorpose) — B chain, input0=skeleton ────────────────────────
@endpoint("rig_mirror_pose")
def rig_mirror_pose(params):
    """KineFX Rig Mirror Pose (kinefx::rigmirrorpose) — mirrors the animated POSE of a skeleton (input 0)
    across a symmetry axis/plane, matching left/right joints by name tokens (e.g. `_l`<->`_r`) or edit
    distance. `operation` picks applying the mirror vs only computing the joint-mirroring attribute.
    SECURITY: no file/code surface; token/attribute/group names only."""
    n = child_after(params["skeleton"], "kinefx::rigmirrorpose", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "operation" in params:
        _menu_set(n, "operation", str(params["operation"]), _MIRROR_OP)
    if "mirror_point_attrib" in params:
        _try_set(n, "mirrorptattrib", str(params["mirror_point_attrib"]))
    if "compute_mirroring" in params:
        _try_set(n, "computemirroring", bool(params["compute_mirroring"]))
    if "ref_attrib" in params:
        _try_set(n, "refattrib", str(params["ref_attrib"]))
    if "rest_pose_source" in params:
        _menu_set(n, "restposesrc", str(params["rest_pose_source"]), _RESTPOSE_SRC)
    if "rest_frame" in params:
        _try_set(n, "restframe", clamp(float(params["rest_frame"]), -1e6, 1e6))
    if "rest_attrib" in params:
        _try_set(n, "restattrib", str(params["rest_attrib"]))
    if "symmetry_axis" in params:
        _menu_set(n, "symmetryaxis", str(params["symmetry_axis"]), _SYMAXIS)
    if "match_method" in params:
        _menu_set(n, "method", str(params["match_method"]), _MIRROR_METHOD)
    if "token_position" in params:
        _menu_set(n, "tokenpos", str(params["token_position"]), _TOKENPOS)
    if "match_tokens" in params:
        _try_set(n, "matchtokens", str(params["match_tokens"]))
    if "mirrored_tokens" in params:
        _try_set(n, "mirroredtokens", str(params["mirrored_tokens"]))
    if "max_name_dist" in params:
        _try_set(n, "maxnamedist", clamp(float(params["max_name_dist"]), 0.0, 1e6))
    if "max_pos_dist" in params:
        _try_set(n, "maxposdist", clamp(float(params["max_pos_dist"]), 0.0, 1e6))
    if "reflect_using" in params:
        _menu_set(n, "reflectusing", str(params["reflect_using"]), _REFLECT)
    if "direction" in params:
        _try_set_tuple(n, "dir", params["direction"])
    if "origin" in params:
        _try_set_tuple(n, "origin", params["origin"])
    if "reference_point" in params:
        _try_set(n, "refpoint", str(params["reference_point"]))
    if "reference_point_axis" in params:
        _menu_set(n, "refpointaxis", str(params["reference_point_axis"]), _AXIS)
    return _cooked(n)


# ── 5. rig_stash_pose (kinefx::rigstashpose) — B chain, input0=skeleton, input1=opt pose ─────────
@endpoint("rig_stash_pose")
def rig_stash_pose(params):
    """KineFX Rig Stash Pose (kinefx::rigstashpose) — stores the current pose of a skeleton (input 0)
    into a point attribute (`mode`=store) or restores a previously stashed pose (`mode`=restore).
    Optional `pose` (input 1) supplies the pose to stash. SECURITY: no file surface; the interactive
    `stash` data blob is never touched; string params are attribute names only."""
    n = child_after(params["skeleton"], "kinefx::rigstashpose", params.get("name"))
    if params.get("pose"):
        bridge_input(n, params["pose"], index=1, name_hint="pose")
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _STASH_MODE)
    if "attrib_name" in params:
        _try_set(n, "attrib_name", str(params["attrib_name"]))
    if "clear_attrib" in params:
        _try_set(n, "attrib_clear", bool(params["clear_attrib"]))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _STASH_METHOD)
    if "match_by_attribute" in params:
        _try_set(n, "matchbyattribute", bool(params["match_by_attribute"]))
    if "attribute_to_match" in params:
        _try_set(n, "attributetomatch", str(params["attribute_to_match"]))
    if "frame_source" in params:
        _menu_set(n, "framesource", str(params["frame_source"]), _CLIPINFO)
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "preserve_shears" in params:
        _try_set(n, "preserveshears", bool(params["preserve_shears"]))
    if "joint_scale" in params:
        _try_set(n, "joint_scale", clamp(float(params["joint_scale"]), 1e-3, 1e4))
    return _cooked(n)


# ── 6. rig_copy_transforms (kinefx::rigcopytransforms) — B chain, in0=dest, in1=source (required) ─
@endpoint("rig_copy_transforms")
def rig_copy_transforms(params):
    """KineFX Rig Copy Transforms (kinefx::rigcopytransforms) — copies joint transforms from `source`
    (input 1) onto the `skeleton` (input 0, the destination rig), pairing joints by a mapping attribute
    or a match attribute. Both inputs are required. SECURITY: no file/code surface; string params are
    attribute / point-group names only."""
    n = child_after(params["skeleton"], "kinefx::rigcopytransforms", params.get("name"))
    bridge_input(n, params["source"], index=1, name_hint="source")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "map_using" in params:
        _menu_set(n, "mapusing", str(params["map_using"]), _MAPUSING)
    if "attrib_to_match" in params:
        _try_set(n, "attribtomatch", str(params["attrib_to_match"]))
    if "mapping_attrib_name" in params:
        _try_set(n, "mappingattribname", str(params["mapping_attrib_name"]))
    if "rest_attrib" in params:
        _try_set(n, "restattrib", str(params["rest_attrib"]))
    return _cooked(n)


# ── 7. ik_chains (kinefx::ikchains::2.0) — B chain, input0=skeleton, input1=targets (required) ───
@endpoint("ik_chains")
def ik_chains(params):
    """KineFX IK Chains (kinefx::ikchains::2.0) — solves one or more two-bone IK chains on a skeleton
    (input 0) toward goal positions supplied as `targets` (input 1). Both inputs are required. The
    per-chain definitions (root/mid/tip joints, twist, blend) are an interactive multiparm, not
    data-only settable, so this endpoint wires the inputs, exposes `multithread`, and passes the rig
    through when no chains are defined. SECURITY: no file/code surface."""
    n = child_after(params["skeleton"], "kinefx::ikchains::2.0", params.get("name"))
    bridge_input(n, params["targets"], index=1, name_hint="targets")
    if "multithread" in params:
        _try_set(n, "multithread", bool(params["multithread"]))
    return _cooked(n)


# ── 8. full_body_ik (kinefx::fullbodyik) — B chain, input0=skeleton, input1=opt targets ──────────
@endpoint("full_body_ik")
def full_body_ik(params):
    """KineFX Full Body IK (kinefx::fullbodyik) — solves a whole-skeleton IK pose on `skeleton`
    (input 0) so the configured effector joints reach their targets; optional `targets` (input 1)
    supplies goal geometry. `solver` picks the standard or physically-based FBIK solver. SECURITY: no
    file surface; the `mappings` target-map payload is scout-flagged and NEVER set/exposed; string
    params are attribute / joint-group names only."""
    n = child_after(params["skeleton"], "kinefx::fullbodyik", params.get("name"))
    if params.get("targets"):
        bridge_input(n, params["targets"], index=1, name_hint="targets")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "constrain_root" in params:
        _try_set(n, "constrainroot", bool(params["constrain_root"]))
    if "root" in params:
        _try_set(n, "root", str(params["root"]))
    if "solver" in params:
        _menu_set(n, "solver", str(params["solver"]), _SOLVER)
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 5000)))
    if "damping" in params:
        _try_set(n, "damping", clamp(float(params["damping"]), 0.0, 1e6))
    if "tolerance" in params:
        _try_set(n, "tolerance", clamp(float(params["tolerance"]), 0.0, 1e6))
    if "pin_root" in params:
        _try_set(n, "pinroot", bool(params["pin_root"]))
    if "operation" in params:
        _menu_set(n, "negate", str(params["operation"]), _NEGATE)
    if "map_using" in params:
        _menu_set(n, "mapusing", str(params["map_using"]), _MAPUSING)
    if "mapping_attrib_name" in params:
        _try_set(n, "mappingattribname", str(params["mapping_attrib_name"]))
    if "attrib_to_match" in params:
        _try_set(n, "attribtomatch", str(params["attrib_to_match"]))
    if "delete_attribs" in params:
        _try_set(n, "deleteattribs", bool(params["delete_attribs"]))
    if "compute_local_transform" in params:
        _try_set(n, "computelocaltransform", bool(params["compute_local_transform"]))
    if "configuration_attrib" in params:
        _try_set(n, "configurationattrib", str(params["configuration_attrib"]))
    if "compute_offsets" in params:
        _try_set(n, "computeoffsets", bool(params["compute_offsets"]))
    if "use_rest_pose" in params:
        _try_set(n, "userestpose", bool(params["use_rest_pose"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "src_rest_frame" in params:
        _try_set(n, "srcrestframe", clamp(float(params["src_rest_frame"]), -1e6, 1e6))
    if "add_com_target" in params:
        _try_set(n, "addcomtarget", bool(params["add_com_target"]))
    if "com_target_name" in params:
        _try_set(n, "comtargetname", str(params["com_target_name"]))
    if "com_weight" in params:
        _try_set(n, "comweight", clamp(float(params["com_weight"]), 0.0, 1e6))
    if "com_priority" in params:
        _try_set(n, "compriority", int(clamp(int(params["com_priority"]), 0, 1000000)))
    return _cooked(n)


# ── 9. fbik_configure_targets (kinefx::fbikconfiguretargets) — B chain, in0=skel, in1=opt ────────
@endpoint("fbik_configure_targets")
def fbik_configure_targets(params):
    """KineFX Full Body IK Configure Targets (kinefx::fbikconfiguretargets) — writes the FBIK target
    configuration (per-joint offsets, rest-pose reference, center-of-mass target) onto a skeleton
    (input 0); optional input 1 supplies target geometry. Feeds full_body_ik. SECURITY: no file/code
    surface; string params are attribute / joint-name tokens only."""
    n = child_after(params["skeleton"], "kinefx::fbikconfiguretargets", params.get("name"))
    if params.get("targets"):
        bridge_input(n, params["targets"], index=1, name_hint="targets")
    if "compute_offsets" in params:
        _try_set(n, "computeoffsets", bool(params["compute_offsets"]))
    if "use_rest_pose" in params:
        _try_set(n, "userestpose", bool(params["use_rest_pose"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "src_rest_frame" in params:
        _try_set(n, "srcrestframe", clamp(float(params["src_rest_frame"]), -1e6, 1e6))
    if "map_using" in params:
        _menu_set(n, "mapusing", str(params["map_using"]), _MAPUSING)
    if "mapping_attrib_name" in params:
        _try_set(n, "mappingattribname", str(params["mapping_attrib_name"]))
    if "attrib_to_match" in params:
        _try_set(n, "attribtomatch", str(params["attrib_to_match"]))
    if "add_com_target" in params:
        _try_set(n, "addcomtarget", bool(params["add_com_target"]))
    if "com_target_name" in params:
        _try_set(n, "comtargetname", str(params["com_target_name"]))
    if "com_weight" in params:
        _try_set(n, "comweight", clamp(float(params["com_weight"]), 0.0, 1e6))
    if "com_priority" in params:
        _try_set(n, "compriority", int(clamp(int(params["com_priority"]), 0, 1000000)))
    return _cooked(n)


# ── 10. spline_ik (kinefx::splineik) — B chain, input0=skeleton ──────────────────────────────────
@endpoint("spline_ik")
def spline_ik(params):
    """KineFX Spline IK (kinefx::splineik) — drives a joint chain of a skeleton (input 0) along a spline
    fitted through the joints, giving smooth curve-based control (spines, tails, tentacles). `to_type`
    picks the curve basis; primary/secondary axes control the twist frame. SECURITY: no file/code
    surface; string params are attribute-name tokens only."""
    n = child_after(params["skeleton"], "kinefx::splineik", params.get("name"))
    if "multi_curve" in params:
        _try_set(n, "multicurve", bool(params["multi_curve"]))
    if "piece_attrib" in params:
        _try_set(n, "pieceattrib", str(params["piece_attrib"]))
    if "to_type" in params:
        _menu_set(n, "totype", str(params["to_type"]), _SPLINE_TOTYPE)
    if "order_u" in params:
        _try_set(n, "orderu", int(clamp(int(params["order_u"]), 2, 11)))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _SPLINE_MODE)
    if "ref_axis" in params:
        _menu_set(n, "refaxis", str(params["ref_axis"]), _SPLINE_AXIS6)
    if "primary_axis" in params:
        _menu_set(n, "primaryaxis", str(params["primary_axis"]), _SPLINE_AXIS6)
    if "secondary_axis" in params:
        _menu_set(n, "secondaryaxisz", str(params["secondary_axis"]), _SPLINE_AXIS4)
    if "do_length" in params:
        _try_set(n, "dolength", bool(params["do_length"]))
    if "length" in params:
        _try_set(n, "length", clamp(float(params["length"]), 0.0, 1e6))
    if "do_segments" in params:
        _try_set(n, "dosegs", bool(params["do_segments"]))
    if "segments" in params:
        _try_set(n, "segs", int(clamp(int(params["segments"]), 1, 100000)))
    if "extrapolate" in params:
        _try_set(n, "extrapolate", bool(params["extrapolate"]))
    if "extrapolate_axis" in params:
        _menu_set(n, "extrapolateaxis", str(params["extrapolate_axis"]), _SPLINE_AXIS6)
    if "sticky" in params:
        _try_set(n, "sticky", bool(params["sticky"]))
    if "name_prefix" in params:
        _try_set(n, "nameprefix", str(params["name_prefix"]))
    return _cooked(n)


# ── 11. reverse_foot (kinefx::reversefoot) — B chain, input0=skeleton, input1/2=opt ──────────────
@endpoint("reverse_foot")
def reverse_foot(params):
    """KineFX Reverse Foot (kinefx::reversefoot) — builds a reverse-foot roll setup on a skeleton
    (input 0), adding heel/ball/toe pivot markers so a foot can roll and pivot. The per-foot joint
    assignments (upper-leg/knee/ankle/ball/toe) are an interactive numbered multiparm, not data-only
    settable, so this endpoint exposes the global controls and passes the rig through. SECURITY: no
    file/code surface; string params are joint-name / attribute tokens only."""
    n = child_after(params["skeleton"], "kinefx::reversefoot", params.get("name"))
    if "mode" in params:
        _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 2)))
    if "keep_markers" in params:
        _try_set(n, "keepmarkers", bool(params["keep_markers"]))
    if "apply_delta" in params:
        _try_set(n, "applydelta", bool(params["apply_delta"]))
    if "use_rest_pose_attrib" in params:
        _try_set(n, "userestposeattrib", bool(params["use_rest_pose_attrib"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "attrib_name" in params:
        _try_set(n, "attribname", str(params["attrib_name"]))
    if "pelvis_joint" in params:
        _try_set(n, "pelvisjoint", str(params["pelvis_joint"]))
    return _cooked(n)


# ── 12. stabilize_joint (kinefx::stabilizejoint) — B chain, input0=skeleton, input1/2=opt ────────
@endpoint("stabilize_joint")
def stabilize_joint(params):
    """KineFX Stabilize Joint (kinefx::stabilizejoint) — removes jitter / locks a joint of an animated
    skeleton (input 0) in place over a frame range, with position/angle change limits and blend
    in/out. Optional inputs 1/2 supply geometry to stick to. SECURITY: no file/code surface; string
    params are joint-group / attribute names only; the interactive guide Ramp is not exposed."""
    n = child_after(params["skeleton"], "kinefx::stabilizejoint", params.get("name"))
    if "joint_group" in params:
        _try_set(n, "jointgroup", str(params["joint_group"]))
    if "mode" in params:
        _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 2)))
    if "modify_transform" in params:
        _try_set(n, "modifytransform", int(clamp(int(params["modify_transform"]), 0, 2)))
    if "update_children_transforms" in params:
        _try_set(n, "updatechildrentransforms", bool(params["update_children_transforms"]))
    if "apply_only_to_range" in params:
        _try_set(n, "applyeffectonlytorange", bool(params["apply_only_to_range"]))
    if "clip_range_mode" in params:
        _menu_set(n, "cliprangemode", str(params["clip_range_mode"]), _CLIPINFO)
    if "position_attrib" in params:
        _try_set(n, "pattribname", str(params["position_attrib"]))
    if "rotation_attrib" in params:
        _try_set(n, "rattribname", str(params["rotation_attrib"]))
    if "enable_max_position_change" in params:
        _try_set(n, "enablemaxpositionchange", bool(params["enable_max_position_change"]))
    if "max_position_change" in params:
        _try_set(n, "maxpositionchange", clamp(float(params["max_position_change"]), 0.0, 1e6))
    if "enable_max_angle_change" in params:
        _try_set(n, "enablemaxanglechange", bool(params["enable_max_angle_change"]))
    if "max_angle_change" in params:
        _try_set(n, "maxanglechange", clamp(float(params["max_angle_change"]), 0.0, 360.0))
    if "enable_geometry_distance" in params:
        _try_set(n, "enablegeometrydistance", bool(params["enable_geometry_distance"]))
    if "geometry_distance" in params:
        _try_set(n, "geometrydistance", clamp(float(params["geometry_distance"]), 0.0, 1e6))
    if "blend_in_frames" in params:
        _try_set(n, "blendinframes", int(clamp(int(params["blend_in_frames"]), 0, 100000)))
    if "blend_out_frames" in params:
        _try_set(n, "blendoutframes", int(clamp(int(params["blend_out_frames"]), 0, 100000)))
    if "enable_min_lock_frames" in params:
        _try_set(n, "enableminlockframes", bool(params["enable_min_lock_frames"]))
    if "min_lock_frames" in params:
        _try_set(n, "minlockframes", int(clamp(int(params["min_lock_frames"]), 0, 100000)))
    if "enable_loosen" in params:
        _try_set(n, "enableloosen", bool(params["enable_loosen"]))
    if "loosen" in params:
        _try_set(n, "loosen", clamp(float(params["loosen"]), 0.0, 1e6))
    return _cooked(n)


# ── 13. pose_difference (kinefx::posedifference) — B chain, in0=pose, in1=reference (required) ───
@endpoint("pose_difference")
def pose_difference(params):
    """KineFX Pose Difference (kinefx::posedifference) — computes the per-joint difference between the
    pose on `skeleton` (input 0) and the `reference` pose (input 1), storing it in an output attribute
    (optionally as position/rotation/scale only, inverted, or applied as an offset). Both inputs are
    required. SECURITY: no file/code surface; string params are attribute names only."""
    n = child_after(params["skeleton"], "kinefx::posedifference", params.get("name"))
    bridge_input(n, params["reference"], index=1, name_hint="reference")
    if "use_frame" in params:
        _try_set(n, "useframe", bool(params["use_frame"]))
    if "frame" in params:
        _try_set(n, "frame", int(clamp(int(params["frame"]), -1000000, 1000000)))
    if "map_using" in params:
        _menu_set(n, "mapusing", str(params["map_using"]), _PD_MAPUSING)
    if "mapping_attrib_name" in params:
        _try_set(n, "mappingattribname", str(params["mapping_attrib_name"]))
    if "attrib_to_match" in params:
        _try_set(n, "attribtomatch", str(params["attrib_to_match"]))
    if "use_transform" in params:
        _menu_set(n, "usetransform", str(params["use_transform"]), _PD_USETRANSFORM)
    if "input_attrib" in params:
        _try_set(n, "inputattrib", str(params["input_attrib"]))
    if "output_attrib" in params:
        _try_set(n, "outputattrib", str(params["output_attrib"]))
    if "store_component" in params:
        _menu_set(n, "storecomp", str(params["store_component"]), _PD_STORECOMP)
    if "invert" in params:
        _try_set(n, "invert", bool(params["invert"]))
    if "apply_offset" in params:
        _try_set(n, "applyoffset", bool(params["apply_offset"]))
    return _cooked(n)

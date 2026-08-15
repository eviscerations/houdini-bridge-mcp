"""KineFX Deformation & blendshapes — data-only handlers. Params verified against live
H21.0.671; every endpoint proven with a headless cook over the
reusable fixture (a 4-joint skeleton + a proximity-captured tube).

Archetype (mirror the Labs A/B/C mapping): every node here is **B chain** with SEMANTIC inputs.
The deformers take the skin geometry on **input0 = captured skin** and the pose on
**input1/2 = skeleton (rest / deform)** — the correct index is wired explicitly (`child_after` for
input0, `bridge_input(index=…)` for the operands). A cook that "succeeds" with the wrong input wired
is WRONG, so the E2E log records exactly which input carried which stream.

SECURITY (KineFX lane, data-only): none of these nodes carries a file or code/callback parm. The
enumerate flags `useopencl` / `openclmode` / `kerneltype` on a few nodes, but those are a GPU-accel
toggle / a compute-mode enum / an RBF kernel-shape enum — NOT code parms (keyword false-positives);
no OpenCL/VEX/python snippet parm exists on any node in this lane and none is set or exposed. Surfaced string
params are attribute / group / node-path NAMES only (Regular strings), never file paths or code.
`skelrootpath` on the classic deformers is an in-scene op/node reference, not a filesystem path.
Interactive multiparms (transform lists, per-channel blend folders), Buttons and Folder headers are
never touched.
"""

import json

import hou
from houdini_executor.server import clamp, child_after, bridge_input, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _cooked(n):
    g = n.geometry()
    out = {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}
    # Honest-return coverage: deformation is topology-invariant, so points/prims can't prove the skin
    # actually MOVED. A bounding box (cheap cached intrinsic) lets a recipe pass_if compare the deformed
    # bbox against the rest pose. Guarded so a null/edge cook simply omits it.
    try:
        out["bbox"] = list(g.intrinsicValue("bounds"))   # (xmin,xmax,ymin,ymax,zmin,zmax)
    except Exception:  # noqa: BLE001 - readback convenience must never break a good cook
        pass
    return out


def _as_pathlist(value):
    """Normalize a variadic node-path param to a list. The catalog has no list Kind, so it arrives as
    a Str (JSON array or comma-separated); a native list is also accepted (direct-call / tests)."""
    if not value:
        return []
    if isinstance(value, str):
        s = value.strip()
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except Exception:
            return [p.strip() for p in s.split(",") if p.strip()]
    return list(value)


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_DEFORM_METHOD = ("linear", "dualquat", "blenddualquat", "frominputgeo")
_PSEC_DIFFMETHOD = ("predeform", "postdeform", "postdeform_orient")
_PSEC_BONEMETHOD = ("linear", "dualquat", "blenddualquat")
_GROUPTYPE = ("guess", "vertices", "edges", "points", "prims")
_OPENCLMODE = ("dense", "sparse")
_SM_CLIPRANGE = ("clipinfo", "custom")
_SM_MODE = ("local", "attrib")
_SM_EFFECT = ("lagovershoot", "jiggle", "spring")
_ROT_ORDER = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")
_XFORM_ORDER = ("srt", "str", "rst", "rts", "tsr", "trs")
_SM_BLENDSHAPE = ("linear", "cosine", "easein", "easeout")
_DW_MAPPING = ("mappingattrib", "matchattrib")
_DW_WARP = ("synchronize", "createsimilar")
_DW_OUTLEN = ("time", "frame", "scale", "optimal")
_BS_VOXEL = ("none", "bygridindex", "byvoxelpos")
_BS_MASKMODE = ("none", "setfromattrib", "scalefromattrib")
_BS_MASKATTRIBMODE = ("each", "first")


# ── 1. joint_deform (kinefx::jointdeform) — B chain: in0=skin, in1=rest skel, in2=deform skel ────
@endpoint("joint_deform")
def joint_deform(params):
    """KineFX Joint Deform (kinefx::jointdeform) — deforms captured skin by joint transforms. Input 0 =
    captured skin geometry (`boneCapture` weights), input 1 = rest-pose skeleton, input 2 = deform
    (animated) skeleton; the skin follows the delta between the two skeletons. SECURITY: attribute/group
    names only; no file/code surface."""
    n = child_after(params["skin"], "kinefx::jointdeform", params.get("name"))
    bridge_input(n, params["rest_skeleton"], index=1, name_hint="rest_skel")
    bridge_input(n, params["deform_skeleton"], index=2, name_hint="deform_skel")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _DEFORM_METHOD)
    if "dq_blend_attrib" in params:
        _try_set(n, "dqblendattrib", str(params["dq_blend_attrib"]))
    if "other_attribs" in params:
        _try_set(n, "otherattribs", str(params["other_attribs"]))
    if "deform_normals" in params:
        _try_set(n, "donormal", bool(params["deform_normals"]))
    if "delete_capture_attrib" in params:
        _try_set(n, "deletecaptureattrib", bool(params["delete_capture_attrib"]))
    if "delete_point_colors" in params:
        _try_set(n, "deletepointtcolors", bool(params["delete_point_colors"]))
    return _cooked(n)


# ── 2. bone_deform (bonedeform) — B chain: in0=skin, in1=rest skel, in2=deform skel ──────────────
@endpoint("bone_deform")
def bone_deform(params):
    """KineFX Bone Deform (bonedeform) — deforms captured geometry using bone/joint capture attributes.
    Input 0 = captured skin, input 1 = rest-pose skeleton, input 2 = deform (animated) skeleton. Both
    KineFX and legacy bone-capture skins are supported. SECURITY: `skel_root_path` is an in-scene node
    reference, not a file; `use_opencl` is a GPU-accel toggle (no OpenCL code parm exists/is exposed)."""
    n = child_after(params["skin"], "bonedeform", params.get("name"))
    if params.get("rest_skeleton"):
        bridge_input(n, params["rest_skeleton"], index=1, name_hint="rest_skel")
    if params.get("deform_skeleton"):
        bridge_input(n, params["deform_skeleton"], index=2, name_hint="deform_skel")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "skel_root_path" in params:
        _try_set(n, "skelrootpath", str(params["skel_root_path"]))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _DEFORM_METHOD)
    if "dq_blend_attrib" in params:
        _try_set(n, "dqblendattrib", str(params["dq_blend_attrib"]))
    if "other_attribs" in params:
        _try_set(n, "otherattribs", str(params["other_attribs"]))
    if "deform_normals" in params:
        _try_set(n, "donormal", bool(params["deform_normals"]))
    if "delete_capture_attrib" in params:
        _try_set(n, "deletecaptureattrib", bool(params["delete_capture_attrib"]))
    if "delete_point_colors" in params:
        _try_set(n, "deletepointtcolors", bool(params["delete_point_colors"]))
    if "use_opencl" in params:
        _try_set(n, "useopencl", bool(params["use_opencl"]))
    return _cooked(n)


# ── 3. deform_skeleton_skin (kinefx::deformskelskin) — B chain: in0=skeleton, in1=opt skin ───────
@endpoint("deform_skeleton_skin")
def deform_skeleton_skin(params):
    """KineFX Deform Skeleton/Skin (kinefx::deformskelskin) — poses a skeleton (input 0) and deforms the
    bound skin (optional input 1) together, then outputs the transformed rig/skin. The per-joint
    transform edits are an interactive multiparm; this endpoint exposes the data-only output/behaviour
    toggles and passes the rig through when no edits are set. SECURITY: attribute names only; no
    file/code surface. Bake buttons are never pressed."""
    n = child_after(params["skeleton"], "kinefx::deformskelskin", params.get("name"))
    if params.get("skin"):
        bridge_input(n, params["skin"], index=1, name_hint="skin")
    if "world_space" in params:
        _try_set(n, "worldspace", bool(params["world_space"]))
    if "update_rest" in params:
        _try_set(n, "updaterest", bool(params["update_rest"]))
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
    if "output_local_transform" in params:
        _try_set(n, "outputlocaltransform", bool(params["output_local_transform"]))
    if "output_input_local_transform" in params:
        _try_set(n, "outputinputlocaltransform", bool(params["output_input_local_transform"]))
    if "output_effective_local_transform" in params:
        _try_set(n, "outputeffectivelocaltransform", bool(params["output_effective_local_transform"]))
    return _cooked(n)


# NOTE: `posespacedeform` (type `posespacedeform`) is SKIPPED. Its cook requires
# a genuinely sculpted pose-shape example package (packed pose examples carrying the detail attribute
# `poseShapeExamplePath` produced by an interactive Pose-Space Edit sculpt), which cannot be
# synthesized headless with the wave fixture. No green cook -> not shipped.


# ── 4. pose_space_deform_combine (posespacedeformcombine) — B chain variadic: in0..N PSD outputs ─
@endpoint("pose_space_deform_combine")
def pose_space_deform_combine(params):
    """KineFX Pose-Space Deform Combine (posespacedeformcombine) — merges multiple Pose-Space Deform
    outputs (input 0..N) into a single corrective result. Additional operands beyond input 0 are wired
    from `extra_inputs`. SECURITY: no file/code surface (one orientation toggle)."""
    n = child_after(params["geometry"], "posespacedeformcombine", params.get("name"))
    for i, p in enumerate(_as_pathlist(params.get("extra_inputs")), start=1):
        bridge_input(n, p, index=i, name_hint="psd_%d" % i)
    if "use_orient" in params:
        _try_set(n, "useorient", bool(params["use_orient"]))
    return _cooked(n)


# NOTE: `posespaceedit` (type `posespaceedit`) is SKIPPED. It is the interactive
# pose-sculpt tool; its internal bone-deform requires a bound classic-capture rig (`boneCapt`) plus a
# live stash + skeleton reference. It errors ("Missing boneCapt attribute") when cooked headless over
# the wave fixture. No green cook -> not shipped.


# ── 5. pose_space_edit_configure (posespaceeditconfigure) — B chain: in0=geo ─────────────────────
@endpoint("pose_space_edit_configure")
def pose_space_edit_configure(params):
    """KineFX Pose-Space Edit Configure (posespaceeditconfigure) — sets how Pose-Space Edit computes
    shape differences (pre/post-deform, orient) on geometry (input 0), optionally re-deforming with bone
    capture. SECURITY: `skel_root_path` is an in-scene node reference, not a file; attribute/enum values
    only."""
    n = child_after(params["geometry"], "posespaceeditconfigure", params.get("name"))
    if "shape_diff_method" in params:
        _menu_set(n, "shapediffmethod", str(params["shape_diff_method"]), _PSEC_DIFFMETHOD)
    if "orient_attrib" in params:
        _try_set(n, "orientattrib", str(params["orient_attrib"]))
    if "use_bone_deform" in params:
        _try_set(n, "usebonedeform", bool(params["use_bone_deform"]))
    if "skel_root_path" in params:
        _try_set(n, "skelrootpath", str(params["skel_root_path"]))
    if "bone_deform_method" in params:
        _menu_set(n, "bonedeformmethod", str(params["bone_deform_method"]), _PSEC_BONEMETHOD)
    if "dq_blend_attrib" in params:
        _try_set(n, "dqblendattrib", str(params["dq_blend_attrib"]))
    return _cooked(n)


# ── 8. character_blend_shapes (kinefx::characterblendshapes) — B chain: in0=mesh,in1=shapes,in2=ch ─
@endpoint("character_blend_shapes")
def character_blend_shapes(params):
    """KineFX Character Blend Shapes (kinefx::characterblendshapes) — the all-in-one blendshape node:
    input 0 = base mesh, input 1 = blend-shape meshes, input 2 = channel definitions; applies the
    weighted blends. SECURITY: attribute/group names only; no file/code surface."""
    n = child_after(params["mesh"], "kinefx::characterblendshapes", params.get("name"))
    bridge_input(n, params["blend_shapes"], index=1, name_hint="blend_shapes")
    bridge_input(n, params["channels"], index=2, name_hint="channels")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "attribs" in params:
        _try_set(n, "attribs", str(params["attribs"]))
    return _cooked(n)


# ── 9. character_blend_shapes_add (kinefx::characterblendshapesadd) — B chain: in0=base,in1=shape ─
@endpoint("character_blend_shapes_add")
def character_blend_shapes_add(params):
    """KineFX Character Blend Shapes Add (kinefx::characterblendshapesadd) — packs a new blend-shape (or
    in-between) target (input 1) onto a base mesh (input 0). SECURITY: attribute/shape names only; no
    file/code surface."""
    n = child_after(params["base"], "kinefx::characterblendshapesadd", params.get("name"))
    if params.get("shape"):
        bridge_input(n, params["shape"], index=1, name_hint="shape")
    if "skin_name" in params:
        _try_set(n, "skin", str(params["skin_name"]))
    if "remove_unchanged" in params:
        _try_set(n, "removeunchanged", bool(params["remove_unchanged"]))
    if "unpacked" in params:
        _try_set(n, "unpacked", bool(params["unpacked"]))
    if "unpacked_name" in params:
        _try_set(n, "unpackedname", str(params["unpacked_name"]))
    if "in_between" in params:
        _try_set(n, "inbetween", bool(params["in_between"]))
    if "hero_shape_name" in params:
        _try_set(n, "heroshapename", str(params["hero_shape_name"]))
    if "weight_attrib" in params:
        _try_set(n, "weightattrib", str(params["weight_attrib"]))
    if "in_between_weight" in params:
        _try_set(n, "weightunpacked", float(params["in_between_weight"]))
    return _cooked(n)


# ── 10. character_blend_shapes_core (kinefx::characterblendshapescore) — B chain: in0/in1 ────────
@endpoint("character_blend_shapes_core")
def character_blend_shapes_core(params):
    """KineFX Character Blend Shapes Core (kinefx::characterblendshapescore) — the low-level weighted
    blend evaluator: input 0 = base mesh, input 1 = packed blend targets + weights. SECURITY:
    attribute/group names only; `use_opencl` is a GPU-accel toggle (no OpenCL code parm)."""
    n = child_after(params["base"], "kinefx::characterblendshapescore", params.get("name"))
    bridge_input(n, params["blend_targets"], index=1, name_hint="blend_targets")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "attribs" in params:
        _try_set(n, "attribs", str(params["attribs"]))
    if "use_opencl" in params:
        _try_set(n, "useopencl", bool(params["use_opencl"]))
    if "opencl_mode" in params:
        _menu_set(n, "openclmode", str(params["opencl_mode"]), _OPENCLMODE)
    return _cooked(n)


# ── 11. character_blend_shapes_extract (kinefx::characterblendshapesextract) — B chain: in0 ──────
@endpoint("character_blend_shapes_extract")
def character_blend_shapes_extract(params):
    """KineFX Character Blend Shapes Extract (kinefx::characterblendshapesextract) — extracts a single
    named blend-shape (or in-between) target mesh out of a packed blendshape input (input 0). SECURITY:
    shape names only; no file/code surface."""
    n = child_after(params["blendshape_geo"], "kinefx::characterblendshapesextract", params.get("name"))
    if "blendshape" in params:
        _try_set(n, "blendshape", str(params["blendshape"]))
    if "in_between" in params:
        _try_set(n, "inbetween", bool(params["in_between"]))
    if "in_between_name" in params:
        _try_set(n, "inbetweenname", str(params["in_between_name"]))
    if "raw" in params:
        _try_set(n, "raw", bool(params["raw"]))
    return _cooked(n)


# ── 12. character_blend_shape_channels (kinefx::characterblendshapechannels) — B chain: in0/in1 ──
@endpoint("character_blend_shape_channels")
def character_blend_shape_channels(params):
    """KineFX Character Blend Shape Channels (kinefx::characterblendshapechannels) — defines/updates the
    blend-shape channel table (weights) for a mesh (input 0), optionally seeded from a second input. The
    per-channel weights are an interactive multiparm; this endpoint exposes the data-only seeding toggle
    and passes through otherwise. SECURITY: no file/code surface; Buttons are never pressed."""
    n = child_after(params["mesh"], "kinefx::characterblendshapechannels", params.get("name"))
    if params.get("channel_source"):
        bridge_input(n, params["channel_source"], index=1, name_hint="channel_source")
    if "create_attributes_from_mesh" in params:
        _try_set(n, "createattributesfrommesh", bool(params["create_attributes_from_mesh"]))
    return _cooked(n)


# ── 13. secondary_motion (kinefx::secondarymotion) — B chain: in0=animated skeleton, in1=opt ─────
@endpoint("secondary_motion")
def secondary_motion(params):
    """KineFX Secondary Motion (kinefx::secondarymotion) — adds overlapping/jiggle/spring follow-through
    to an animated skeleton (input 0). `effect` picks the model (lag+overshoot / jiggle / spring) and
    the matching controls tune it. SECURITY: attribute/group names only; no file/code surface. Cost
    knobs (spring constant) are clamped."""
    n = child_after(params["skeleton"], "kinefx::secondarymotion", params.get("name"))
    if params.get("collider"):
        bridge_input(n, params["collider"], index=1, name_hint="collider")
    if "active_points" in params:
        _try_set(n, "activepoints", str(params["active_points"]))
    if "joint_group" in params:
        _try_set(n, "jointgroup", str(params["joint_group"]))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _SM_MODE)
    if "effect" in params:
        _menu_set(n, "effect", str(params["effect"]), _SM_EFFECT)
    if "effect_multiplier" in params:
        _try_set(n, "effectmult", float(params["effect_multiplier"]))
    if "blend" in params:
        _try_set(n, "blend", float(params["blend"]))
    # lag + overshoot model
    if "lag" in params:
        _try_set(n, "lag", float(params["lag"]))
    if "overshoot" in params:
        _try_set(n, "overshoot", float(params["overshoot"]))
    # jiggle model
    if "stiffness" in params:
        _try_set(n, "stiffness", float(params["stiffness"]))
    if "jiggle_damping" in params:
        _try_set(n, "jiggledamping", float(params["jiggle_damping"]))
    if "limit" in params:
        _try_set(n, "limit", float(params["limit"]))
    if "flex" in params:
        _try_set(n, "flex", float(params["flex"]))
    if "multiplier" in params:
        _try_set(n, "multiplier", float(params["multiplier"]))
    # spring model
    if "spring_constant" in params:
        _try_set(n, "springconstant", int(clamp(int(params["spring_constant"]), 1, 100000)))
    if "mass" in params:
        _try_set(n, "mass", float(params["mass"]))
    if "damping" in params:
        _try_set(n, "damping", float(params["damping"]))
    if "use_gravity" in params:
        _try_set(n, "usegravity", bool(params["use_gravity"]))
    if "gravity_force_dir" in params:
        _try_set_tuple(n, "gravityforcedir", params["gravity_force_dir"])
    if "rest_pose_attrib" in params:
        _try_set(n, "userestposeattrib", True)
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    return _cooked(n)


# ── 14. dynamic_warp (kinefx::dynamicwarp) — B chain: in0=reference motion, in1=source motion ────
@endpoint("dynamic_warp")
def dynamic_warp(params):
    """KineFX Dynamic Warp (kinefx::dynamicwarp) — time-warps a source animation (input 1) to align with
    a reference animation (input 0) using dynamic time warping over matched attributes. SECURITY:
    attribute names only; no file/code surface. Search knobs (KNN, max step/stall) are clamped."""
    n = child_after(params["reference_motion"], "kinefx::dynamicwarp", params.get("name"))
    bridge_input(n, params["source_motion"], index=1, name_hint="source_motion")
    if "mapping_method" in params:
        _menu_set(n, "mappingmethod", str(params["mapping_method"]), _DW_MAPPING)
    if "mapping_attrib" in params:
        _try_set(n, "mappingattrib", str(params["mapping_attrib"]))
    if "attrib_to_match" in params:
        _try_set(n, "attribtomatch", str(params["attrib_to_match"]))
    if "sample_rate" in params:
        _try_set(n, "samplerate", float(params["sample_rate"]))
    if "warp_method" in params:
        _menu_set(n, "warpmethod", str(params["warp_method"]), _DW_WARP)
    if "max_step" in params:
        _try_set(n, "maxstep", int(clamp(int(params["max_step"]), 1, 1000)))
    if "max_stall" in params:
        _try_set(n, "maxstall", int(clamp(int(params["max_stall"]), 0, 1000)))
    if "scale_source_length" in params:
        _try_set(n, "scalesourcelength", float(params["scale_source_length"]))
    if "knn" in params:
        _try_set(n, "knn", int(clamp(int(params["knn"]), 1, 100)))
    if "output_length_type" in params:
        _menu_set(n, "outputlengthtype", str(params["output_length_type"]), _DW_OUTLEN)
    if "length_scale" in params:
        _try_set(n, "lengthscale", float(params["length_scale"]))
    return _cooked(n)


# NOTE: `poseweightinterp` (type `kinefx::poseweightinterp`) is SKIPPED. The node
# segfaults hython (H21.0.671) when cooked over a skeleton with no valid pose-weight example set, under
# both the default and RBF smoothing modes — a crash cannot be certified as a green cook, so it is not
# shipped. The wrapper (data-only) can be revived once a valid pose-weight-example fixture exists.


# ── skeleton_deform (deform, classic Sop) — B chain: in0=captured skin ────────────────────────────
@endpoint("skeleton_deform")
def skeleton_deform(params):
    """KineFX/Classic Deform (SOP `deform`) — deforms capture-weighted geometry (input 0) by a skeleton
    referenced through `skel_root_path` (an in-scene node reference). Named `skeleton_deform` because
    the bare name `deform` collides with the existing generic bend/twist/lattice `deform` tool.
    SECURITY: `skel_root_path`/`bone_transform_path` are in-scene node references, not files; attribute
    names only; no code surface."""
    n = child_after(params["skin"], "deform", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "skel_root_path" in params:
        _try_set(n, "skelrootpath", str(params["skel_root_path"]))
    if "bone_transform_path" in params:
        _try_set(n, "bonetransformpath", str(params["bone_transform_path"]))
    if "delete_capture_attrib" in params:
        _try_set(n, "delCaptAtr", bool(params["delete_capture_attrib"]))
    if "delete_color_attrib" in params:
        _try_set(n, "delColAtr", bool(params["delete_color_attrib"]))
    if "deform_normals" in params:
        _try_set(n, "donormal", bool(params["deform_normals"]))
    if "normalize_weights" in params:
        _try_set(n, "normalize", bool(params["normalize_weights"]))
    if "fast" in params:
        _try_set(n, "fast", bool(params["fast"]))
    if "use_dual_quat" in params:
        _try_set(n, "usedqskin", bool(params["use_dual_quat"]))
    if "dq_blend_attrib" in params:
        _try_set(n, "dodqblendattrib", True)
        _try_set(n, "dqblendattrib", str(params["dq_blend_attrib"]))
    if "deform_vector_attribs" in params:
        _try_set(n, "dovattribs", bool(params["deform_vector_attribs"]))
    if "vector_attribs" in params:
        _try_set(n, "vattribs", str(params["vector_attribs"]))
    if "deform_quaternion_attribs" in params:
        _try_set(n, "doqattribs", bool(params["deform_quaternion_attribs"]))
    if "quaternion_attribs" in params:
        _try_set(n, "qattribs", str(params["quaternion_attribs"]))
    return _cooked(n)


# ── 17. blend_shapes (blendshapes::2.0, classic Sop) — B chain: in0=base, in1..N=targets ─────────
@endpoint("blend_shapes")
def blend_shapes(params):
    """Classic Blend Shapes (SOP `blendshapes::2.0`) — weighted morph of a base mesh (input 0) toward one
    or more target shapes (input 1..N). `first_blend_weight` sets the first target's weight; extra
    targets are wired from `target_shapes`. Named `blend_shapes` (distinct from the KineFX
    `character_blend_shapes` node). SECURITY: attribute/group names only; no file/code surface."""
    n = child_after(params["base"], "blendshapes::2.0", params.get("name"))
    for i, p in enumerate(_as_pathlist(params.get("target_shapes")), start=1):
        bridge_input(n, p, index=i, name_hint="target_%d" % i)
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "difference" in params:
        _try_set(n, "diff", bool(params["difference"]))
    if "cache_deltas" in params:
        _try_set(n, "cachedeltas", bool(params["cache_deltas"]))
    if "pack" in params:
        _try_set(n, "pack", bool(params["pack"]))
    if "attribs" in params:
        _try_set(n, "attribs", str(params["attribs"]))
    if "slerp" in params:
        _try_set(n, "doslerp", bool(params["slerp"]))
    if "voxel_blend" in params:
        _menu_set(n, "voxelblend", str(params["voxel_blend"]), _BS_VOXEL)
    if "mask_mode" in params:
        _menu_set(n, "maskmode", str(params["mask_mode"]), _BS_MASKMODE)
    if "mask_attrib" in params:
        _try_set(n, "maskattrib", str(params["mask_attrib"]))
    if "mask_source" in params:
        _menu_set(n, "maskattribmode", str(params["mask_source"]), _BS_MASKATTRIBMODE)
    if "first_blend_weight" in params:
        _try_set(n, "blend0", float(params["first_blend_weight"]))
    return _cooked(n)

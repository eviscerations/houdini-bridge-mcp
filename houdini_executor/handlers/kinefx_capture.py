"""KineFX + Classic Capture & skinning-weights — data-only handlers. Params verified against live
H21.0.671; every endpoint proven with a headless cook over the
reusable fixture (a 4-joint skeleton + a proximity-captured tube).

Archetypes (mirror the Labs A/B/C mapping):
  A source  : capture_region (cregion) — a 0-input capture-region source in a fresh /obj geo.
  B chain   : the bulk. Capture nodes take TWO inputs with SEMANTICS —
                input0 = the geometry/skin to capture, input1 = the skeleton (KineFX skeleton, whose
                per-point `transform` Matrix3 the classic capture nodes also accept as capture regions).
              Correct index is wired explicitly: child_after() for input0 (geometry), bridge_input(..,
              index=1) for input1 (skeleton). A cook that "succeeds" with the inputs swapped is WRONG.
              The capture editors (mirror/correct/override/name-from-weight) take a single already-
              captured input0.
  WIRE-ONLY : dembones_skinning_converter (kinefx::dembones_skinningconverter) — an EXTERNAL DemBones
              solve driven off an Alembic cache; built + wired + confined + clamped but NEVER executed
              (mirrors tree.py maps_baker). Returns solved=False.

SECURITY (data-only):
  * No code/callback parm is ever set or exposed (jointcapturepaint's interactive `strokesfilepath`
    stroke-cache and the classic `capture` node's `captfile`/`savefile` capture-I/O file parms are left
    at default and never surfaced — this lane exposes NO paint/capture disk surface).
  * The one real file surface, dembones' `sAnimatedCache` (Alembic read), is routed through
    confined_path() so the read stays inside the working dir.
  * classic `rootpath`/`skelrootpath`/`cregions` are in-scene OP-path / region-name strings (not files
    and not code) — surfaced as plain strings.
  * cost-exponential solver levers (biharmonic maxiter, DemBones iteration/bone counts, skinning-
    converter frame-range/bone counts) are hard-clamped.
"""

import hou
from houdini_executor.server import clamp, child_after, bridge_input, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _try_set_int_tuple(node, parm, values):
    """Set an int-vector parmTuple only if it exists (probe-safe)."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(int(v) for v in values))
        return True
    except Exception:
        return False


def _cooked(n):
    g = n.geometry()
    res = {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}
    # Honest-return coverage: a capture step's recipe verify reads whether boneCapture landed (and on how
    # many regions). Cheap + guarded, so non-capture ops in this family just omit the fields.
    try:
        if g.findPointAttrib("boneCapture") is not None:
            res["boneCapture_written"] = True
            if g.findGlobalAttrib("boneCapture_pCaptPaths") is not None:
                res["capture_regions"] = len(g.attribValue("boneCapture_pCaptPaths"))
    except Exception:  # noqa: BLE001 - a readback convenience must never break a good cook
        pass
    return res


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("geo", name)


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_TETMETHOD = ("adaptive", "uniform", "exact", "embed")
_RESAMPLE = ("off", "maxaxis", "maxlength")
_ROLE = ("capture", "control")
_WEIGHTMETHOD = ("weightClosestRegionObject", "weightClosestConnectingRegionObject")
_WEIGHTFROM = ("cv", "surface")                        # kinefx/captureproximity order
_WEIGHTFROM_CAP = ("surface", "cv")                    # classic `capture` node order (reversed!)
_CAPT_GEOM = ("capt_geom_surface", "capt_geom_tet_mesh")
_COLOR = ("colDefault", "colRegion")
_GROUPTYPE = ("guess", "breakpoints", "edges", "points", "prims")
_NORMALIZATION = ("interactive", "post")
_REGIONSOP = ("display", "render", "capture")
_COOKAT = ("captureframe", "everyframe")
_AXIS = ("x", "y", "z")
_USEGROUPAS = ("source", "destination")
_MIRROR_CAPTYPE = ("bonecapture", "metacapture", "muscle")
_CORRECT_CAPTYPE = ("bonecapture", "metacapture")
_MIRROROP = ("copy", "leave", "average")
_OVERRIDE_OP = ("none", "replace", "add", "create", "remove", "normalize")
_SC_ERRORMETHOD = ("0", "1")
_SC_CAPTUREMETHOD = ("0", "1")
_SC_BONEPLACEMENT = ("0", "1")
_SC_METHOD = ("1", "0", "2")


# ── 1. joint_capture_biharmonic (kinefx::jointcapturebiharmonic) — in0=geometry, in1=skeleton ────
@endpoint("joint_capture_biharmonic")
def joint_capture_biharmonic(params):
    """KineFX Joint Capture Biharmonic (kinefx::jointcapturebiharmonic) — computes smooth `boneCapture`
    skinning weights by solving biharmonic functions over an internally-tetrahedralized `geometry`
    (input 0), using the `skeleton` (input 1) as the influence rig. The high-quality skinning-weight
    solver. SECURITY: attribute/group names only; no file/code surface."""
    n = child_after(params["geometry"], "kinefx::jointcapturebiharmonic", params.get("name"))
    bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")
    if "skin_group" in params:
        _try_set(n, "skingroup", str(params["skin_group"]))
    if "skel_group" in params:
        _try_set(n, "skelgroup", str(params["skel_group"]))
    if "max_iter" in params:
        _try_set(n, "maxiter", int(clamp(int(params["max_iter"]), 1, 2000)))
    if "tet_method" in params:
        _menu_set(n, "tetmethod", str(params["tet_method"]), _TETMETHOD)
    if "use_scale_attrib" in params:
        _try_set(n, "usescaleattrib", bool(params["use_scale_attrib"]))
    if "scale_attrib" in params:
        _try_set(n, "scaleattrib", str(params["scale_attrib"]))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e4))
    if "use_enlarge_offset" in params:
        _try_set(n, "useenlargeoffset", bool(params["use_enlarge_offset"]))
    if "enlarge_offset" in params:
        _try_set(n, "enlargeoffset", clamp(float(params["enlarge_offset"]), 0.0, 1e3))
    if "max_tet_scale" in params:
        _try_set(n, "maxtetscale", clamp(float(params["max_tet_scale"]), 1e-3, 1e3))
    if "max_tri_scale" in params:
        _try_set(n, "maxtriscale", clamp(float(params["max_tri_scale"]), 1e-3, 1e3))
    if "min_tri_scale" in params:
        _try_set(n, "mintriscale", clamp(float(params["min_tri_scale"]), 1e-3, 1e3))
    if "do_blend" in params:
        _try_set(n, "doblend", bool(params["do_blend"]))
    if "blend_factor" in params:
        _try_set(n, "blendfactor", clamp(float(params["blend_factor"]), 0.0, 1.0))
    if "resample" in params:
        _menu_set(n, "resample", str(params["resample"]), _RESAMPLE)
    if "max_axis_fraction" in params:
        _try_set(n, "maxaxisfraction", clamp(float(params["max_axis_fraction"]), 0.0, 1.0))
    if "max_length" in params:
        _try_set(n, "maxlength", clamp(float(params["max_length"]), 1e-4, 1e4))
    if "exclude_short_bones" in params:
        _try_set(n, "excludeshortbones", bool(params["exclude_short_bones"]))
    if "exclude_threshold" in params:
        _try_set(n, "excludethreshold", clamp(float(params["exclude_threshold"]), 0.0, 1e4))
    if "fuse_threshold" in params:
        _try_set(n, "fusethreshold", clamp(float(params["fuse_threshold"]), 0.0, 1e4))
    if "role" in params:
        _menu_set(n, "role", str(params["role"]), _ROLE)
    return _cooked(n)


# ── 2. joint_capture_proximity (kinefx::jointcaptureproximity) — in0=geometry, in1=skeleton ──────
@endpoint("joint_capture_proximity")
def joint_capture_proximity(params):
    """KineFX Joint Capture Proximity (kinefx::jointcaptureproximity) — assigns `boneCapture` skinning
    weights to `geometry` (input 0) by proximity to the `skeleton` (input 1) bones. The fast default
    skinning-weight tool (the fixture's own capture node). SECURITY: attribute/group names only; no
    file/code surface."""
    n = child_after(params["geometry"], "kinefx::jointcaptureproximity", params.get("name"))
    bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "capture_group" in params:
        _try_set(n, "capturegroup", str(params["capture_group"]))
    if "weight_method" in params:
        _menu_set(n, "weightmethod", str(params["weight_method"]), _WEIGHTMETHOD)
    if "weight_from" in params:
        _menu_set(n, "weightfrom", str(params["weight_from"]), _WEIGHTFROM)
    if "dropoff" in params:
        _try_set(n, "dropoff", clamp(float(params["dropoff"]), 0.0, 100.0))
    if "max_influences" in params:
        _try_set(n, "maxinfluences", int(clamp(int(params["max_influences"]), 1, 64)))
    if "do_blend" in params:
        _try_set(n, "doblend", bool(params["do_blend"]))
    if "blend_factor" in params:
        _try_set(n, "blendfactor", clamp(float(params["blend_factor"]), 0.0, 1.0))
    if "norm_weights" in params:
        _try_set(n, "normweights", bool(params["norm_weights"]))
    if "ignore_skeleton_connectivity" in params:
        _try_set(n, "ignoreskeletonconnectivity", bool(params["ignore_skeleton_connectivity"]))
    return _cooked(n)


# ── 3. point_capture_biharmonic (kinefx::pointcapturebiharmonic) — in0=geometry, in1=skeleton ────
@endpoint("point_capture_biharmonic")
def point_capture_biharmonic(params):
    """KineFX Point Capture Biharmonic (kinefx::pointcapturebiharmonic) — biharmonic point-cloud capture
    of `geometry` (input 0) to the `skeleton` (input 1). `capture_geometry_type` selects a surface solve
    (needs pre-seeded capture data on the input) vs a self-contained tetrahedral-mesh solve. SECURITY:
    no file/code surface."""
    n = child_after(params["geometry"], "kinefx::pointcapturebiharmonic", params.get("name"))
    bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")
    if "capture_geometry_type" in params:
        _menu_set(n, "capture_geometry_type", str(params["capture_geometry_type"]), _CAPT_GEOM)
    if "color" in params:
        _menu_set(n, "color", str(params["color"]), _COLOR)
    return _cooked(n)


# ── 4. joint_capture_paint (kinefx::jointcapturepaint) — in0=geometry, in1=skeleton ──────────────
@endpoint("joint_capture_paint")
def joint_capture_paint(params):
    """KineFX Joint Capture Paint (kinefx::jointcapturepaint) — initializes / normalizes `boneCapture`
    weights on `geometry` (input 0) against the `skeleton` (input 1); the interactive brush is a viewport
    tool, so this data-only endpoint exposes only the weight-init controls (group / normalization / region
    filter) and passes the initialized rig through. SECURITY: the interactive `strokesfilepath` stroke
    cache is NEVER set or exposed; no code parm."""
    n = child_after(params["geometry"], "kinefx::jointcapturepaint", params.get("name"))
    bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "normalization" in params:
        _menu_set(n, "normalization", str(params["normalization"]), _NORMALIZATION)
    if "cregion" in params:
        _try_set(n, "cregion", str(params["cregion"]))
    return _cooked(n)


# ── 5. capture_packed_geo (kinefx::capturepackedgeo) — in0=geometry, in1=skeleton ────────────────
@endpoint("capture_packed_geo")
def capture_packed_geo(params):
    """KineFX Capture Packed Geo (kinefx::capturepackedgeo) — transfers/packs the capture on `geometry`
    (input 0) against the `skeleton` (input 1), optionally packing the input, matching by name, and
    unpacking the result. Useful for capturing instanced/packed character parts. SECURITY: attribute/
    group names only; no file/code surface."""
    n = child_after(params["geometry"], "kinefx::capturepackedgeo", params.get("name"))
    bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")
    if "active_pt" in params:
        _try_set(n, "activept", str(params["active_pt"]))
    if "pack_input" in params:
        _try_set(n, "packinput", bool(params["pack_input"]))
    if "use_connectivity" in params:
        _try_set(n, "useconnectivity", bool(params["use_connectivity"]))
    if "name_attribute" in params:
        _try_set(n, "nameattribute", str(params["name_attribute"]))
    if "unpack_output" in params:
        _try_set(n, "unpackoutput", bool(params["unpack_output"]))
    if "transfer_attributes" in params:
        _try_set(n, "transferattributes", str(params["transfer_attributes"]))
    if "transfer_groups" in params:
        _try_set(n, "transfergroups", str(params["transfer_groups"]))
    if "capture_by_name" in params:
        _try_set(n, "capturebyname", bool(params["capture_by_name"]))
    if "skin_attr" in params:
        _try_set(n, "skinattr", str(params["skin_attr"]))
    if "skel_attr" in params:
        _try_set(n, "skelattr", str(params["skel_attr"]))
    if "create_captured_group" in params:
        _try_set(n, "createcapturedgrp", bool(params["create_captured_group"]))
    if "captured_group_name" in params:
        _try_set(n, "capturedgrpname", str(params["captured_group_name"]))
    return _cooked(n)


# ── 6. capture_proximity (captureproximity, classic) — in0=geometry, in1=skeleton/regions ────────
@endpoint("capture_proximity")
def capture_proximity(params):
    """Classic Capture Proximity (captureproximity) — proximity capture of `geometry` (input 0) to the
    capture regions on `skeleton` (input 1; a KineFX skeleton whose per-point `transform` supplies the
    regions). Named `capture_proximity` (vs KineFX `joint_capture_proximity`). SECURITY: `root_path` is
    an in-scene OP path (not a file); no file/code surface."""
    n = child_after(params["geometry"], "captureproximity", params.get("name"))
    bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "capture_group" in params:
        _try_set(n, "capturegroup", str(params["capture_group"]))
    if "root_path" in params:
        _try_set(n, "rootpath", str(params["root_path"]))
    if "extra_regions" in params:
        _try_set(n, "extraregions", str(params["extra_regions"]))
    if "region_source" in params:
        _menu_set(n, "captureregionsop", str(params["region_source"]), _REGIONSOP)
    if "do_subnets" in params:
        _try_set(n, "dosubnets", bool(params["do_subnets"]))
    if "relative_skel" in params:
        _try_set(n, "relativeskel", bool(params["relative_skel"]))
    if "use_capture_pose" in params:
        _try_set(n, "usecaptpose", bool(params["use_capture_pose"]))
    if "cook_at" in params:
        _menu_set(n, "cookat", str(params["cook_at"]), _COOKAT)
    if "capture_frame" in params:
        _try_set(n, "captframe", clamp(float(params["capture_frame"]), -1e6, 1e6))
    if "weight_method" in params:
        _menu_set(n, "weightmethod", str(params["weight_method"]), _WEIGHTMETHOD)
    if "weight_from" in params:
        _menu_set(n, "weightFrom", str(params["weight_from"]), _WEIGHTFROM)
    if "dropoff" in params:
        _try_set(n, "dropoff", clamp(float(params["dropoff"]), 0.0, 100.0))
    if "max_influences" in params:
        _try_set(n, "maxinfluences", int(clamp(int(params["max_influences"]), 1, 64)))
    if "norm_weights" in params:
        _try_set(n, "normweights", bool(params["norm_weights"]))
    if "destroy_weights" in params:
        _try_set(n, "destroyweights", bool(params["destroy_weights"]))
    if "blend_factor" in params:
        _try_set(n, "blendfactor", clamp(float(params["blend_factor"]), 0.0, 1.0))
    return _cooked(n)


# ── 7. bone_capture (capture, classic) — in0=geometry, in1=skeleton/regions ──────────────────────
@endpoint("bone_capture")
def bone_capture(params):
    """Classic Capture (capture) — assigns capture weights to `geometry` (input 0) from the capture
    regions on `skeleton` (input 1). Named `bone_capture` (the bare `capture` node) to avoid a generic
    name collision. SECURITY: `root_path` is an in-scene OP path; the node's `captfile`/`savefile`
    capture-I/O file parms are NEVER set or exposed (no disk surface); no code parm."""
    n = child_after(params["geometry"], "capture", params.get("name"))
    bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "root_path" in params:
        _try_set(n, "rootpath", str(params["root_path"]))
    if "extra_regions" in params:
        _try_set(n, "extraregions", str(params["extra_regions"]))
    if "region_source" in params:
        _menu_set(n, "captregionsop", str(params["region_source"]), _REGIONSOP)
    if "do_subnets" in params:
        _try_set(n, "dosubnets", bool(params["do_subnets"]))
    if "relative_skel" in params:
        _try_set(n, "relativeskel", bool(params["relative_skel"]))
    if "use_capture_pose" in params:
        _try_set(n, "usecaptpose", bool(params["use_capture_pose"]))
    if "capture_frame" in params:
        _try_set(n, "captframe", clamp(float(params["capture_frame"]), -1e6, 1e6))
    if "weight_from" in params:
        _menu_set(n, "weightFrom", str(params["weight_from"]), _WEIGHTFROM_CAP)
    if "norm_weights" in params:
        _try_set(n, "normweights", bool(params["norm_weights"]))
    if "destroy_weights" in params:
        _try_set(n, "destroyweights", bool(params["destroy_weights"]))
    if "blend_factor" in params:
        _try_set(n, "blendfactor", clamp(float(params["blend_factor"]), 0.0, 1.0))
    return _cooked(n)


# ── 8. bone_capture_lines (bonecapturelines, classic) — in0=skeleton (optional) ──────────────────
@endpoint("bone_capture_lines")
def bone_capture_lines(params):
    """Classic Bone Capture Lines (bonecapturelines) — generates classic capture-region line geometry
    (carrying `boneCapture`) from the `skeleton` (input 0), for feeding classic capture solvers.
    SECURITY: `root_path` is an in-scene OP path; no file/code surface."""
    n = child_after(params["skeleton"], "bonecapturelines", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "root_path" in params:
        _try_set(n, "rootpath", str(params["root_path"]))
    if "extra_regions" in params:
        _try_set(n, "extraregions", str(params["extra_regions"]))
    if "resample" in params:
        _menu_set(n, "resample", str(params["resample"]), _RESAMPLE)
    if "max_axis_fraction" in params:
        _try_set(n, "maxaxisfraction", clamp(float(params["max_axis_fraction"]), 0.0, 1.0))
    if "max_length" in params:
        _try_set(n, "maxlength", clamp(float(params["max_length"]), 1e-4, 1e4))
    if "exclude_short_bones" in params:
        _try_set(n, "excludeshortbones", bool(params["exclude_short_bones"]))
    if "exclude_threshold" in params:
        _try_set(n, "excludethreshold", clamp(float(params["exclude_threshold"]), 0.0, 1e4))
    if "fuse_threshold" in params:
        _try_set(n, "fusethreshold", clamp(float(params["fuse_threshold"]), 0.0, 1e4))
    if "use_bone_link" in params:
        _try_set(n, "usebonelink", bool(params["use_bone_link"]))
    if "use_capture_pose" in params:
        _try_set(n, "usecaptpose", bool(params["use_capture_pose"]))
    if "cook_at" in params:
        _menu_set(n, "cookat", str(params["cook_at"]), _COOKAT)
    if "capture_frame" in params:
        _try_set(n, "captframe", clamp(float(params["capture_frame"]), -1e6, 1e6))
    if "region_source" in params:
        _menu_set(n, "captureregionsop", str(params["region_source"]), _REGIONSOP)
    if "do_subnets" in params:
        _try_set(n, "dosubnets", bool(params["do_subnets"]))
    if "relative_skel" in params:
        _try_set(n, "relativeskel", bool(params["relative_skel"]))
    return _cooked(n)


# ── 9. capture_region (cregion, classic) — 0-input SOURCE in a fresh /obj geo ─────────────────────
@endpoint("capture_region")
def capture_region(params):
    """Classic Capture Region (cregion) — a 0-input SOURCE that emits one capture-region primitive (a
    tube with a `transform`) inside a fresh /obj geo. The classic building block for hand-authored
    capture regions. Fails on name collision. SECURITY: geometric values only; no file/code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("cregion")
    if "orient" in params:
        _menu_set(n, "orient", str(params["orient"]), _AXIS)
    if "center" in params:
        _try_set_tuple(n, "center", params["center"])
    if "radius" in params:
        _try_set_tuple(n, "r", params["radius"])
    if "squash" in params:
        _try_set_tuple(n, "squash", params["squash"])
    if "top_height" in params:
        _try_set(n, "topheight", clamp(float(params["top_height"]), -1e4, 1e4))
    if "bottom_height" in params:
        _try_set(n, "botheight", clamp(float(params["bottom_height"]), -1e4, 1e4))
    if "z_factor" in params:
        _try_set(n, "zfactor", clamp(float(params["z_factor"]), 0.0, 1e3))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 10. capture_mirror (capturemirror, classic) — in0=captured geometry ──────────────────────────
@endpoint("capture_mirror")
def capture_mirror(params):
    """Classic Capture Mirror (capturemirror) — mirrors capture weights on already-captured `geometry`
    (input 0) across a plane, renaming mirrored regions via find/replace tokens. Named `capture_mirror`
    to avoid colliding with the generic `mirror` tool. SECURITY: attribute/token names only; no
    file/code surface."""
    n = child_after(params["geometry"], "capturemirror", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "use_group_as" in params:
        _menu_set(n, "usegroupas", str(params["use_group_as"]), _USEGROUPAS)
    if "capture_type" in params:
        _menu_set(n, "capturetype", str(params["capture_type"]), _MIRROR_CAPTYPE)
    if "mirror_op" in params:
        _menu_set(n, "mirrorop", str(params["mirror_op"]), _MIRROROP)
    if "origin" in params:
        _try_set_tuple(n, "origin", params["origin"])
    if "distance" in params:
        _try_set(n, "dist", clamp(float(params["distance"]), -1e6, 1e6))
    if "direction" in params:
        _try_set_tuple(n, "dir", params["direction"])
    if "find" in params:
        _try_set(n, "from", str(params["find"]))
    if "replace" in params:
        _try_set(n, "to", str(params["replace"]))
    return _cooked(n)


# ── 11. capture_correct (capturecorrect, classic) — in0=captured geometry ────────────────────────
@endpoint("capture_correct")
def capture_correct(params):
    """Classic Capture Correct (capturecorrect) — cleans up capture weights on already-captured
    `geometry` (input 0): update/remove stale regions, clamp negative/positive weights, limit the
    influence count per point, and renormalize. SECURITY: region-name strings only; no file/code
    surface."""
    n = child_after(params["geometry"], "capturecorrect", params.get("name"))
    if "capture_type" in params:
        _menu_set(n, "capturetype", str(params["capture_type"]), _CORRECT_CAPTYPE)
    if "update_regions" in params:
        _try_set(n, "updateregions", bool(params["update_regions"]))
    if "regions_to_update" in params:
        _try_set(n, "regionstoupdate", str(params["regions_to_update"]))
    if "del_stale_regions" in params:
        _try_set(n, "delstaleregions", bool(params["del_stale_regions"]))
    if "regions_to_del" in params:
        _try_set(n, "regionstodel", str(params["regions_to_del"]))
    if "clamp_negative" in params:
        _try_set(n, "clampnegative", bool(params["clamp_negative"]))
    if "negative_threshold" in params:
        _try_set(n, "negativethreshold", clamp(float(params["negative_threshold"]), -1e6, 1e6))
    if "clamp_positive" in params:
        _try_set(n, "clamppositive", bool(params["clamp_positive"]))
    if "positive_threshold" in params:
        _try_set(n, "positivethreshold", clamp(float(params["positive_threshold"]), -1e6, 1e6))
    if "limit_regions" in params:
        _try_set(n, "limitregions", bool(params["limit_regions"]))
    if "max_regions" in params:
        _try_set(n, "maxregions", int(clamp(int(params["max_regions"]), 1, 64)))
    if "renormalize" in params:
        _try_set(n, "renormalize", bool(params["renormalize"]))
    if "renormalize_tolerance" in params:
        _try_set(n, "renormalizetolerance", clamp(float(params["renormalize_tolerance"]), 0.0, 1.0))
    return _cooked(n)


# ── 12. capture_override (captureoverride, classic) — in0=captured geometry ──────────────────────
@endpoint("capture_override")
def capture_override(params):
    """Classic Capture Override (captureoverride) — overrides capture weights on already-captured
    `geometry` (input 0) for the named `cregions`, applying an operation (replace/add/create/remove/
    normalize) at a set weight. SECURITY: `skel_root_path`/`cregions` are in-scene OP-path / region
    strings; no file/code surface."""
    n = child_after(params["geometry"], "captureoverride", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "cregions" in params:
        _try_set(n, "cregions", str(params["cregions"]))
    if "skel_root_path" in params:
        _try_set(n, "skelrootpath", str(params["skel_root_path"]))
    if "operation" in params:
        _menu_set(n, "op", str(params["operation"]), _OVERRIDE_OP)
    if "weight" in params:
        _try_set(n, "weight", clamp(float(params["weight"]), -1e6, 1e6))
    if "clamp_negative" in params:
        _try_set(n, "clampneg", bool(params["clamp_negative"]))
    if "normalize_weight" in params:
        _try_set(n, "normalizeweight", bool(params["normalize_weight"]))
    return _cooked(n)


# ── 13. name_from_capture_weight (labs::name_from_capture_weight::1.0) — in0=captured geometry ───
@endpoint("name_from_capture_weight")
def name_from_capture_weight(params):
    """Labs Name From Capture Weight (labs::name_from_capture_weight::1.0) — writes a point `name`
    attribute on already-captured `geometry` (input 0) from each point's dominant capture region (its
    heaviest boneCapture weight). Wrapped in the KineFX capture lane. SECURITY: attribute names only;
    no file/code surface."""
    n = child_after(params["geometry"], "labs::name_from_capture_weight::1.0", params.get("name"))
    if "name_attrib" in params:
        _try_set(n, "name", str(params["name_attrib"]))
    if "index_attrib" in params:
        _try_set(n, "index", str(params["index_attrib"]))
    return _cooked(n)


# ── 14. skinning_converter (labs::skinning_converter::3.0) — in0=animated geo, in1=opt reference ─
@endpoint("skinning_converter")
def skinning_converter(params):
    """Labs Skinning Converter (labs::skinning_converter::3.0) — converts a vertex-animated / deforming
    `geometry` (input 0, time-dependent) into a skeleton + `boneCapture` skinning weights (a DemBones-
    family solve over `frame_start..frame_end`). Optional `reference` (input 1) supplies drawn/input
    bones. Wrapped in the KineFX capture lane. SECURITY: no file/code surface; the frame range and bone
    counts (the solve-cost levers) are hard-clamped."""
    n = child_after(params["geometry"], "labs::skinning_converter::3.0", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    if "static_group" in params:
        _try_set(n, "sStaticGroup", str(params["static_group"]))
    if "use_mesh_connectivity" in params:
        _try_set(n, "bUseMeshConnectivity", bool(params["use_mesh_connectivity"]))
    if "error_method" in params:
        _menu_set(n, "lErrorMethod", str(params["error_method"]), _SC_ERRORMETHOD)
    if "frame_start" in params or "frame_end" in params:
        fs = int(clamp(int(params.get("frame_start", 1)), -100000, 100000))
        fe = int(clamp(int(params.get("frame_end", fs)), fs, fs + 2000))  # clamp span <= 2000 frames
        _try_set_int_tuple(n, "i2FrameRange", (fs, fe))
    if "capture_method" in params:
        _menu_set(n, "lCaptureMethod", str(params["capture_method"]), _SC_CAPTUREMETHOD)
    if "capture_frame" in params:
        _try_set(n, "iCaptureFrame", int(clamp(int(params["capture_frame"]), -100000, 100000)))
    if "bone_influences" in params:
        _try_set(n, "iBoneInfluences", int(clamp(int(params["bone_influences"]), 1, 16)))
    if "bone_placement_mode" in params:
        _menu_set(n, "boneplacementmode", str(params["bone_placement_mode"]), _SC_BONEPLACEMENT)
    if "method" in params:
        _menu_set(n, "lMethod", str(params["method"]), _SC_METHOD)
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e4))
    if "uniform_bones" in params:
        _try_set(n, "iUnifBones", int(clamp(int(params["uniform_bones"]), 1, 512)))
    if "uniform_seed" in params:
        _try_set(n, "fUnifSeed", clamp(float(params["uniform_seed"]), 0.0, 1e6))
    if "uniform_influence" in params:
        _try_set(n, "fUnifInfl", clamp(float(params["uniform_influence"]), 0.0, 1.0))
    if "secondary_bones" in params:
        _try_set(n, "fSecondaryBones", clamp(float(params["secondary_bones"]), 0.0, 512.0))
    if "use_input_bones" in params:
        _try_set(n, "bUseInputBones", bool(params["use_input_bones"]))
    return _cooked(n)


# ── 15. dembones_skinning_converter (kinefx::dembones_skinningconverter) — WIRE-ONLY external solve ─
@endpoint("dembones_skinning_converter")
def dembones_skinning_converter(params):
    """KineFX DemBones Skinning Converter (kinefx::dembones_skinningconverter) — WIRE-ONLY. Builds +
    wires + configures the DemBones external solve that converts an Alembic-cached deforming mesh into a
    skeleton + skin weights, but NEVER executes it (mirrors tree.py maps_baker: an external/heavy solve
    is fired by the human, not on cook). `geometry` (input 0) = the rest/reference mesh; optional
    `skeleton` (input 1). Returns solved=False.
    SECURITY:
      * `animated_cache` (the Alembic read) is realpath-confined to the working directory.
      * the DemBones iteration / bone counts (the solve-cost levers) are hard-clamped.
      * no cook is triggered — no external process is launched by this endpoint."""
    n = child_after(params["geometry"], "kinefx::dembones_skinningconverter", params.get("name"))
    if params.get("skeleton"):
        bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")

    cache_path = None
    if params.get("animated_cache"):
        cache_path = confined_path(params["animated_cache"])
        _try_set(n, "sAnimatedCache", cache_path)

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
    return {"node": n.path(), "cache": cache_path, "solved": False,
            "note": "DemBones graph wired (WIRE-ONLY); start the external solve yourself"}

"""CHOP-anim — the FINAL CHOP animation set (data-only handlers). Mirrors the chop_anim_1
pilot exactly: nodes live in a CHOP network (`chopnet`), SOURCE nodes are built in a fresh/reused
chopnet, CHAIN nodes use child_after on input 0 with extra CHOP inputs wired by direct setInput
(same-network — object_merge/bridge_input is SOP-only and must NOT be used for CHOP inputs).
Verification is by TRACK/SAMPLE counts (n.cook(); n.tracks(); tracks[0].allSamples()), never
prims/points. Params verified against live H21.0.671; every
endpoint proven with a headless CHOP cook (9 transform tracks, empty errors) over the reusable CHOP
fixture (a /obj null + a constraintobject transform source + a chopnet).

SECURITY (data-only): the `vex_*` code parms the scout flagged on constraintsurface / constrainttransform
/ pose are the standard VEX/VEXpression tab that EVERY CHOP carries — verified FALSE POSITIVES, never a
node's core; they are never set/exposed here (left at default). No node has a file parm. The string
params surfaced (soppath / geoobjpath / *_attribute / group / reference / channelname) are SCENE-GRAPH
node paths and attribute/channel NAMES — never filesystem paths, never code — so there is no file
surface to confine and nothing forced off. Nodes whose core is a legacy crowd-agent / bone-object rig
(extractbonetransforms, extractposedrivers, extractlocomotion) or a UI script-button sink (stashpose)
are SKIPPED.
"""

import hou
from houdini_executor.server import clamp, child_after, resolve_node, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────




def _set_int(node, parm, value, lo, hi):
    """Set an Int / numeric-token-menu parm (for these CHOPs the menu tokens ARE the numeric index —
    e.g. lookataxis tokens '0'..'5' — so setting the clamped int is the value)."""
    return _try_set(node, parm, int(clamp(int(value), lo, hi)))


def _set_float(node, parm, value, lo, hi):
    return _try_set(node, parm, clamp(float(value), lo, hi))




def _fresh_chopnet(name):
    """Create a fresh /obj chopnet (the CHOP-network container). Fails on name collision."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("chopnet", name) if name else obj.createNode("chopnet")


def _source_net(params):
    """Container for a SOURCE CHOP: reuse the `chopnet` path if given (so multiple sources + a chain
    can share one network), else create a fresh chopnet from `name`."""
    if params.get("chopnet"):
        net = resolve_node(params["chopnet"])
        if not isinstance(net, hou.ChopNode) and net.childTypeCategory() != hou.chopNodeTypeCategory():
            raise ValueError(f"chopnet is not a CHOP network: {params['chopnet']}")
        return net
    return _fresh_chopnet(params.get("name"))


def _chop_input(node, path, index):
    """Wire a sibling CHOP (same chopnet) into `node`'s input `index` by direct setInput. CHOP inputs
    are same-network — the SOP object_merge bridge does NOT apply here."""
    src = resolve_node(path)
    node.setInput(index, src)
    return src


def _cooked(n):
    """Cook the CHOP and report track/sample counts + errors (the CHOP analogue of prims/points)."""
    try:
        n.cook(force=True)
    except hou.OperationFailed:
        pass  # surface the error text below rather than raising
    tracks = n.tracks()
    samples = len(tracks[0].allSamples()) if tracks else 0
    return {
        "node": n.path(),
        "chopnet": n.parent().path(),
        "tracks": len(tracks),
        "samples": samples,
        "errors": list(n.errors()),
    }


# ── named ordered-menu token tuples ──────────────────────────────────────────────────────────────
_LAG_METHOD = ("value", "amp", "mag")
_SPRING_METHOD = ("disp", "force")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  SOURCE constraint CHOPs — emit transform tracks (fresh/reused chopnet); optional CHOP overrides
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ── 1. constraint_surface (constraintsurface) — attach-to-SOP-surface transform source ──────────
@endpoint("constraint_surface")
def constraint_surface(params):
    """KineFX Constraint Surface (constraintsurface) — emits a transform stuck to the SURFACE of the
    SOP at `sop_path`: located by a UV coordinate (`uv` on `uv_attribute`), a position (`p` on
    `position_attribute`) or the nearest point within `search_distance`/`search_max_points`, and
    oriented by the look-at / look-up settings. Up to four optional constraint inputs
    (`input`..`input3`) override placement / orientation. SECURITY: sop_path is a scene SOP node path
    and *_attribute are attribute NAMES; no file/code surface."""
    net = _source_net(params)
    n = net.createNode("constraintsurface")
    for i, key in enumerate(("input", "input1", "input2", "input3")):
        if params.get(key):
            _chop_input(n, params[key], i)
    if "sop_path" in params:
        _try_set(n, "soppath", str(params["sop_path"]))
    if "subdivide" in params:
        _try_set(n, "subdi", bool(params["subdivide"]))
    if "mode" in params:
        _set_int(n, "mode", params["mode"], 0, 4)
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "uv_attribute" in params:
        _try_set(n, "uvattribute", str(params["uv_attribute"]))
    if "uv" in params:
        _try_set_tuple(n, "uv", params["uv"])
    if "position_attribute" in params:
        _try_set(n, "pattribute", str(params["position_attribute"]))
    if "position" in params:
        _try_set_tuple(n, "p", params["position"])
    if "search_distance" in params:
        _set_float(n, "searchdist", params["search_distance"], 0.0, 1e6)
    if "search_max_points" in params:
        _set_int(n, "searchmaxpnt", params["search_max_points"], 0, 100000)
    if "look_at_mode" in params:
        _set_int(n, "lookatmode", params["look_at_mode"], 0, 3)
    if "look_up_mode" in params:
        _set_int(n, "lookupmode", params["look_up_mode"], 0, 3)
    if "look_at_axis" in params:
        _set_int(n, "lookataxis", params["look_at_axis"], 0, 5)
    if "look_up_axis_x" in params:
        _set_int(n, "lookupaxisx", params["look_up_axis_x"], 0, 3)
    if "look_up_axis_y" in params:
        _set_int(n, "lookupaxisy", params["look_up_axis_y"], 0, 3)
    if "look_up_axis_z" in params:
        _set_int(n, "lookupaxisz", params["look_up_axis_z"], 0, 3)
    if "direction_attribute" in params:
        _try_set(n, "dirattribute", str(params["direction_attribute"]))
    if "up_attribute" in params:
        _try_set(n, "upattribute", str(params["up_attribute"]))
    if "up_vector" in params:
        _try_set_tuple(n, "upvector", params["up_vector"])
    if "roll" in params:
        _set_float(n, "roll", params["roll"], -360.0, 360.0)
    return _cooked(n)


# ── 2. constraint_transform (constrainttransform) — an explicit TRS transform source ─────────────
@endpoint("constraint_transform")
def constraint_transform(params):
    """KineFX Constraint Transform (constrainttransform) — emits an explicit transform built from
    `translate`/`rotate`/`scale` (with `transform_order`/`rotation_order`), a pivot (`pivot` /
    `pivot_rotate`), and `mode`/`pivot_mode`; `invert` inverts the result. Up to three optional
    constraint inputs (`input`..`input2`) supply a transform to combine with. SECURITY: numeric
    transform values / scene semantics only; no file/code surface."""
    net = _source_net(params)
    n = net.createNode("constrainttransform")
    for i, key in enumerate(("input", "input1", "input2")):
        if params.get(key):
            _chop_input(n, params[key], i)
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    if "translate" in params:
        _try_set_tuple(n, "t", params["translate"])
    if "rotate" in params:
        _try_set_tuple(n, "r", params["rotate"])
    if "scale" in params:
        _try_set_tuple(n, "s", params["scale"])
    if "pivot" in params:
        _try_set_tuple(n, "p", params["pivot"])
    if "pivot_rotate" in params:
        _try_set_tuple(n, "pr", params["pivot_rotate"])
    if "mode" in params:
        _set_int(n, "mode", params["mode"], 0, 3)
    if "pivot_mode" in params:
        _set_int(n, "pmode", params["pivot_mode"], 0, 2)
    if "invert" in params:
        _try_set(n, "invert", bool(params["invert"]))
    return _cooked(n)


# ── 3. constraint_pose (pose) — a stored static pose (TRS) transform source ──────────────────────
@endpoint("constraint_pose")
def constraint_pose(params):
    """KineFX Pose (pose) — a Constraints-tab CHOP that emits a stored static pose as t/r/s transform
    tracks (built from `translate`/`rotate`/`scale` with `transform_order`/`rotation_order`). An
    optional constraint `input` (input 0) supplies a pose to pass through. Named `constraint_pose` to
    group with the constraint family and avoid a collision with the KineFX rig `rig_pose`. SECURITY:
    numeric pose values only; no file/code surface. (The `update`/`clear` capture BUTTONS are UI
    callbacks — never pressed/exposed.)"""
    net = _source_net(params)
    n = net.createNode("pose")
    if params.get("input"):
        _chop_input(n, params["input"], 0)
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    if "translate" in params:
        _try_set_tuple(n, "t", params["translate"])
    if "rotate" in params:
        _try_set_tuple(n, "r", params["rotate"])
    if "scale" in params:
        _try_set_tuple(n, "s", params["scale"])
    return _cooked(n)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  CHAIN CHOPs — process an upstream channel/transform stream (child_after on input 0)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ── 4. jiggle (jiggle) — secondary-motion jiggle on a transform stream ───────────────────────────
@endpoint("jiggle")
def jiggle(params):
    """KineFX Jiggle (jiggle) — adds secondary jiggle motion to the transform stream on `input`
    (input 0, which MUST carry tx/ty/tz channels). `stiffness` and `damping` shape the spring,
    `limit` caps the displacement, `flex` the flexibility, and `mult` (a 3-vector) scales the per-axis
    response; `reference` names an optional reference channel. SECURITY: numeric values + a channel
    NAME; no file/code surface."""
    n = child_after(params["input"], "jiggle", params.get("name"))
    if "stiffness" in params:
        _set_float(n, "stiff", params["stiffness"], 0.0, 1e6)
    if "damping" in params:
        _set_float(n, "damp", params["damping"], 0.0, 1e6)
    if "limit" in params:
        _set_float(n, "limit", params["limit"], 0.0, 1e6)
    if "flex" in params:
        _set_float(n, "flex", params["flex"], 0.0, 1e6)
    if "mult" in params:
        _try_set_tuple(n, "mult", params["mult"])
    if "reference" in params:
        _try_set(n, "reference", str(params["reference"]))
    return _cooked(n)


# ── 5. lag (lag) — lag / smoothing / overshoot on a channel stream ───────────────────────────────
@endpoint("lag")
def lag(params):
    """KineFX Lag (lag) — smooths / delays the channel stream on `input` (input 0). `method` picks the
    lag model (value / amp / mag); `lag` and `overshoot` are 2-vectors (rise, fall); `slope` and
    `accel` are 2-vectors clamped by the `clamp_slope` / `clamp_accel` toggles. SECURITY: numeric
    values only; no file/code surface."""
    n = child_after(params["input"], "lag", params.get("name"))
    if "method" in params:
        _menu_set(n, "lagmethod", str(params["method"]), _LAG_METHOD)
    if "lag" in params:
        _try_set_tuple(n, "lag", params["lag"])
    if "overshoot" in params:
        _try_set_tuple(n, "overshoot", params["overshoot"])
    if "clamp_slope" in params:
        _try_set(n, "clamp", bool(params["clamp_slope"]))
    if "slope" in params:
        _try_set_tuple(n, "slope", params["slope"])
    if "clamp_accel" in params:
        _try_set(n, "aclamp", bool(params["clamp_accel"]))
    if "accel" in params:
        _try_set_tuple(n, "accel", params["accel"])
    return _cooked(n)


# ── 6. channel_spring (spring) — spring dynamics on a channel stream ──────────────────────────────
@endpoint("channel_spring")
def channel_spring(params):
    """KineFX Spring (spring, CHOP) — drives the channel stream on `input` (input 0) with a mass-spring
    system: `spring_constant`, `mass`, `damping`, `method` (disp / force), initial `position` /
    `speed`, and `use_channel_condition` to seed the initial state from the input. Named
    `channel_spring` to disambiguate from the SOP spring deformer. SECURITY: numeric values only; no
    file/code surface."""
    n = child_after(params["input"], "spring", params.get("name"))
    if "spring_constant" in params:
        _set_float(n, "springk", params["spring_constant"], 0.0, 1e6)
    if "mass" in params:
        _set_float(n, "mass", params["mass"], 1e-6, 1e6)
    if "damping" in params:
        _set_float(n, "dampingk", params["damping"], 0.0, 1e6)
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _SPRING_METHOD)
    if "use_channel_condition" in params:
        _try_set(n, "condfromchan", bool(params["use_channel_condition"]))
    if "position" in params:
        _set_float(n, "initpos", params["position"], -1e6, 1e6)
    if "speed" in params:
        _set_float(n, "initspeed", params["speed"], -1e6, 1e6)
    return _cooked(n)


# ── 7. channel_pose_difference (posedifference) — difference of two pose streams ─────────────────
@endpoint("channel_pose_difference")
def channel_pose_difference(params):
    """KineFX Pose Difference (posedifference, CHOP) — computes the difference between the pose stream
    on `input` (input 0) and a reference pose. `input1` (input 1) optionally supplies the reference
    pose stream; `reference_pose` sets the reference pose value when no second input is wired. Named
    `channel_pose_difference` to avoid a collision with the existing KineFX SOP `pose_difference`.
    SECURITY: numeric values only; no file/code surface."""
    n = child_after(params["input"], "posedifference", params.get("name"))
    if params.get("input1"):
        _chop_input(n, params["input1"], 1)
    if "reference_pose" in params:
        _set_float(n, "referencepose", params["reference_pose"], -1e6, 1e6)
    return _cooked(n)

"""CHOP-anim — the pre-KineFX CHOP constraint network (data-only handlers) for the
CHOP animation/constraints sub-lane. Params verified against live H21.0.671; every endpoint proven with a headless CHOP cook (track/sample
counts + empty errors) over the reusable CHOP fixture (two /obj nulls + a line-SOP geo + a chopnet).

CHOP COOK PATTERN (the base pattern for later lanes):
  These nodes live in a CHOP network (`chopnet`), NOT a SOP geo. A "source" constraint CHOP reads an
  object's / SOP's transform by scene PATH (obj_path / soppath) and emits transform tracks; a "chain"
  constraint CHOP combines upstream constraint tracks wired on its inputs. So:
    * SOURCE handlers create (or reuse) a chopnet under /obj and build the node inside it.
    * CHAIN handlers use child_after(input, ...) to build the node in the SAME chopnet wired to
      input 0; extra constraint inputs (input1..input3) are sibling CHOPs wired by direct setInput
      (same-network — object_merge/bridge_input is SOP-only and must NOT be used for CHOP inputs).
  Verification is by TRACK/SAMPLE counts (n.cook(); n.tracks(); tracks[0].allSamples()), never
  prims/points. A transform source emits 9 tracks (t/r/s * xyz), 1 sample at a static frame.

SECURITY (data-only): the `code_parms` the scout flagged on every node (`vex_align`, `vex_name`,
`vex_start/end/rate`, `vex_edit`, `vex_reload`, `vex_num_threads`, `vex_precision`) are the standard
VEX/VEXpression tab that EVERY CHOP carries — verified FALSE POSITIVES, never the node's core. They are
never set/exposed here (left at default). No node has a file parm (file_parms=[] for all 18). The
string params surfaced (obj_path / ref_path / soppath / constraints_path / parent_bone / group /
*_attribute) are SCENE-GRAPH node paths and attribute NAMES — never filesystem paths, never code — so
there is no file surface to confine and nothing forced off.
"""

import hou
from houdini_executor.server import clamp, child_after, resolve_node, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────




def _set_int(node, parm, value, lo, hi):
    """Set an Int / numeric-token-menu parm (for these constraint CHOPs the menu tokens ARE the
    numeric index — e.g. lookataxis tokens '0'..'5' — so setting the clamped int is the value)."""
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
    """Container for a SOURCE constraint CHOP: reuse the `chopnet` path if given (so multiple
    sources + a chain can share one constraint network), else create a fresh chopnet from `name`."""
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


# ── named ordered-menu token tuples (for the few NAMED menus; numeric-token menus use _set_int) ───
_UNITS = ("frames", "samples", "seconds")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  SOURCE constraint CHOPs — read a scene object/SOP by path, emit transform tracks (fresh chopnet)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ── 1. constraint_begin (constraintbegin) — network start / object transform source ──────────────
@endpoint("constraint_begin")
def constraint_begin(params):
    """KineFX Constraint Get World Space Begin (constraintbegin) — the START of a CHOP constraint
    network: emits the world transform of `object` as t/r/s tracks that downstream constraint CHOPs
    combine. Built in a fresh chopnet (or an existing `chopnet`). SECURITY: object is a scene node
    path; no file/code surface."""
    n = _source_net(params).createNode("constraintbegin")
    if "object" in params:
        _try_set(n, "obj_path", str(params["object"]))
    if "mode" in params:
        _set_int(n, "mode", params["mode"], 0, 3)
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    return _cooked(n)


# ── 2. constraint_object (constraintobject) — world transform of a target (opt relative to ref) ──
@endpoint("constraint_object")
def constraint_object(params):
    """KineFX Constraint Object (constraintobject) — emits the world transform of `target` as t/r/s
    tracks, optionally expressed relative to `reference`. The basic object-transform source of a CHOP
    constraint network. SECURITY: target/reference are scene node paths; no file/code surface."""
    n = _source_net(params).createNode("constraintobject")
    if "target" in params:
        _try_set(n, "obj_path", str(params["target"]))
    if "reference" in params:
        _try_set(n, "ref_path", str(params["reference"]))
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    return _cooked(n)


# ── 3. constraint_object_pretransform (constraintobjectpretransform) — target's pre-transform ────
@endpoint("constraint_object_pretransform")
def constraint_object_pretransform(params):
    """KineFX Constraint Object Pretransform (constraintobjectpretransform) — emits the pre-transform
    (the object's rest/pivot offset) of `target` as t/r/s tracks. SECURITY: target is a scene node
    path; no file/code surface."""
    n = _source_net(params).createNode("constraintobjectpretransform")
    if "target" in params:
        _try_set(n, "obj_path", str(params["target"]))
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    return _cooked(n)


# ── 4. constraint_object_offset (constraintobjectoffset) — target-vs-reference offset transform ──
@endpoint("constraint_object_offset")
def constraint_object_offset(params):
    """KineFX Constraint Object Offset (constraintobjectoffset) — emits the offset transform of
    `target` relative to `reference` as t/r/s tracks, masked by `channel_mask`. Optional constraint
    input (`input`) supplies an existing offset stream. SECURITY: target/reference are scene node
    paths; no file/code surface."""
    net = _source_net(params)
    n = net.createNode("constraintobjectoffset")
    if params.get("input"):
        _chop_input(n, params["input"], 0)
    if "target" in params:
        _try_set(n, "obj_path", str(params["target"]))
    if "reference" in params:
        _try_set(n, "ref_path", str(params["reference"]))
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    if "channel_mask" in params:
        _set_int(n, "mask", params["channel_mask"], 0, 511)
    if "units" in params:
        _menu_set(n, "units2", str(params["units"]), _UNITS)
    return _cooked(n)


# ── 5. constraint_get_world_space (constraintgetworldspace) — object world-space transform ───────
@endpoint("constraint_get_world_space")
def constraint_get_world_space(params):
    """KineFX Constraint Get World Space (constraintgetworldspace) — emits the WORLD-space transform of
    `object` as t/r/s tracks. SECURITY: object is a scene node path; no file/code surface."""
    n = _source_net(params).createNode("constraintgetworldspace")
    if "object" in params:
        _try_set(n, "obj_path", str(params["object"]))
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    return _cooked(n)


# ── 6. constraint_get_parent_space (constraintgetparentspace) — object parent-space transform ────
@endpoint("constraint_get_parent_space")
def constraint_get_parent_space(params):
    """KineFX Constraint Get Parent Space (constraintgetparentspace) — emits the PARENT-space transform
    of `object` as t/r/s tracks; `parent_bone` selects the parent-bone convention. SECURITY: object is
    a scene node path; no file/code surface."""
    n = _source_net(params).createNode("constraintgetparentspace")
    if "object" in params:
        _try_set(n, "obj_path", str(params["object"]))
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    if "parent_bone" in params:
        _set_int(n, "parent_bone", params["parent_bone"], 0, 1)
    return _cooked(n)


# ── 7. constraint_get_local_space (constraintgetlocalspace) — object local-space transform ───────
@endpoint("constraint_get_local_space")
def constraint_get_local_space(params):
    """KineFX Constraint Get Local Space (constraintgetlocalspace) — emits the LOCAL-space transform of
    `object` as t/r/s tracks; `mode` picks the local-space convention. SECURITY: object is a scene node
    path; no file/code surface."""
    n = _source_net(params).createNode("constraintgetlocalspace")
    if "object" in params:
        _try_set(n, "obj_path", str(params["object"]))
    if "mode" in params:
        _set_int(n, "mode", params["mode"], 0, 1)
    if "transform_order" in params:
        _set_int(n, "trs", params["transform_order"], 0, 5)
    if "rotation_order" in params:
        _set_int(n, "xyz", params["rotation_order"], 0, 5)
    return _cooked(n)


# ── 8. constraint_look_at (constraintlookat) — aim/look-at rotation source ───────────────────────
@endpoint("constraint_look_at")
def constraint_look_at(params):
    """KineFX Constraint Look At (constraintlookat) — emits a rotation that aims `look_at_axis` at a
    look-at position, keeping `look_up_axis_*` toward an up target. Optional constraint inputs supply
    the driven / target / up transforms. SECURITY: axis/vector values only; no file/code surface."""
    net = _source_net(params)
    n = net.createNode("constraintlookat")
    for i, key in enumerate(("input", "input1", "input2", "input3")):
        if params.get(key):
            _chop_input(n, params[key], i)
    if "look_at_axis" in params:
        _set_int(n, "lookataxis", params["look_at_axis"], 0, 5)
    if "look_up_axis_x" in params:
        _set_int(n, "lookupaxisx", params["look_up_axis_x"], 0, 3)
    if "look_up_axis_y" in params:
        _set_int(n, "lookupaxisy", params["look_up_axis_y"], 0, 3)
    if "look_up_axis_z" in params:
        _set_int(n, "lookupaxisz", params["look_up_axis_z"], 0, 3)
    if "look_at" in params:
        _try_set_tuple(n, "lookat", params["look_at"])
    if "look_up_mode" in params:
        _set_int(n, "mode", params["look_up_mode"], 0, 2)
    if "up_position" in params:
        _try_set_tuple(n, "uppos", params["up_position"])
    if "up_vector" in params:
        _try_set_tuple(n, "upvec", params["up_vector"])
    if "twist" in params:
        _set_float(n, "twist", params["twist"], -360.0, 360.0)
    return _cooked(n)


# ── 9. constraint_path (constraintpath) — follow-a-SOP-curve transform source ────────────────────
@endpoint("constraint_path")
def constraint_path(params):
    """KineFX Constraint Path (constraintpath) — emits a transform that rides along the curve at
    `sop_path` at parametric `position`, oriented by the look-at / look-up settings. Optional
    constraint inputs override the position / orientation. SECURITY: sop_path is a scene SOP node path
    and *_attribute are attribute names; no file/code surface."""
    net = _source_net(params)
    n = net.createNode("constraintpath")
    for i, key in enumerate(("input", "input1", "input2", "input3")):
        if params.get(key):
            _chop_input(n, params[key], i)
    if "sop_path" in params:
        _try_set(n, "soppath", str(params["sop_path"]))
    if "parametrization" in params:
        _set_int(n, "uparmtype", params["parametrization"], 0, 4)
    if "distance_attribute" in params:
        _try_set(n, "distattribute", str(params["distance_attribute"]))
    if "position" in params:
        _set_float(n, "pos", params["position"], -1e6, 1e6)
    if "look_at_mode" in params:
        _set_int(n, "lookatmode", params["look_at_mode"], 0, 2)
    if "look_up_mode" in params:
        _set_int(n, "lookupmode", params["look_up_mode"], 0, 2)
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
    if "tolerance" in params:
        _set_float(n, "tolerance", params["tolerance"], 0.0, 1e6)
    return _cooked(n)


# ── 10. constraint_points (constraintpoints) — attach-to-SOP-points transform source ────────────
@endpoint("constraint_points")
def constraint_points(params):
    """KineFX Constraint Points (constraintpoints) — emits a transform attached to point(s) of the SOP
    at `sop_path` (a `group`, or the nearest within `search_distance`/`search_max_points`), oriented by
    the look-at / look-up settings. Optional constraint inputs override placement. SECURITY: sop_path
    is a scene SOP path, group/*_attribute are names; no file/code surface."""
    net = _source_net(params)
    n = net.createNode("constraintpoints")
    for i, key in enumerate(("input", "input1", "input2", "input3")):
        if params.get(key):
            _chop_input(n, params[key], i)
    if "sop_path" in params:
        _try_set(n, "soppath", str(params["sop_path"]))
    if "mode" in params:
        _set_int(n, "mode", params["mode"], 0, 1)
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "weights" in params:
        _try_set_tuple(n, "weights", params["weights"])
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


# ── 11. constraint_export (constraintexport) — write combined constraint back to a network ───────
@endpoint("constraint_export")
def constraint_export(params):
    """KineFX Constraint Export (constraintexport) — terminates a constraint network by exporting the
    combined transform to the constraint object at `constraints_path`. `enable_constraints` toggles the
    export live. WIRE-ONLY writeback of transform DATA (no file / no render); it references a scene node
    by path, never a filesystem path. SECURITY: constraints_path is a scene node path; no file/code
    surface."""
    n = _source_net(params).createNode("constraintexport")
    if "enable_constraints" in params:
        _try_set(n, "constraints_on", bool(params["enable_constraints"]))
    if "constraints_path" in params:
        _try_set(n, "constraints_path", str(params["constraints_path"]))
    return _cooked(n)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
#  CHAIN constraint CHOPs — combine upstream constraint tracks (child_after on input 0)
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# ── 12. constraint_blend (constraintblend) — weighted blend of constraint streams ────────────────
@endpoint("constraint_blend")
def constraint_blend(params):
    """KineFX Constraint Blend (constraintblend) — blends two or more constraint transform streams.
    `input` (input 0) = the base stream; `input1` (input 1) = the blend target; `method` picks the
    blend math, `rotation_blending` the rotation interpolation, `write_mask` the channels written
    (int bitmask of TX..SZ, default 511=all). SECURITY: no file/code surface."""
    n = child_after(params["input"], "constraintblend", params.get("name"))
    if params.get("input1"):
        _chop_input(n, params["input1"], 1)
    if "method" in params:
        _set_int(n, "method", params["method"], 0, 3)
    if "rotation_blending" in params:
        _set_int(n, "rotblend", params["rotation_blending"], 0, 2)
    if "write_mask" in params:
        _set_int(n, "writemask", params["write_mask"], 0, 511)
    return _cooked(n)


# ── 13. constraint_sequence (constraintsequence) — sequential blend of constraint streams ────────
@endpoint("constraint_sequence")
def constraint_sequence(params):
    """KineFX Constraint Sequence (constraintsequence) — sequentially blends a chain of constraint
    streams by `blend` amount. `input` (input 0) = base; `input1` (input 1) = next stream.
    `write_mask` = channels written (int bitmask, default 511). SECURITY: no file/code surface."""
    n = child_after(params["input"], "constraintsequence", params.get("name"))
    if params.get("input1"):
        _chop_input(n, params["input1"], 1)
    if "blend" in params:
        _set_float(n, "blend", params["blend"], 0.0, 1.0)
    if "rotation_blending" in params:
        _set_int(n, "rotblend", params["rotation_blending"], 0, 2)
    if "write_mask" in params:
        _set_int(n, "writemask", params["write_mask"], 0, 511)
    return _cooked(n)


# ── 14. constraint_offset (constraintoffset) — apply an offset stream to a base stream ───────────
@endpoint("constraint_offset")
def constraint_offset(params):
    """KineFX Constraint Offset (constraintoffset) — applies the offset transform on `input1` (input 1)
    to the base transform on `input` (input 0), by `blend`. `write_mask` = blended channels,
    `offset_mask` = which channels the offset affects (both int bitmasks, default 511). Requires BOTH
    inputs. SECURITY: no file/code surface."""
    n = child_after(params["input"], "constraintoffset", params.get("name"))
    _chop_input(n, params["input1"], 1)  # required second input
    if "blend" in params:
        _set_float(n, "blend", params["blend"], 0.0, 1.0)
    if "rotation_blending" in params:
        _set_int(n, "rotblend", params["rotation_blending"], 0, 2)
    if "write_mask" in params:
        _set_int(n, "writemask", params["write_mask"], 0, 511)
    if "offset_mask" in params:
        _set_int(n, "mask", params["offset_mask"], 0, 511)
    if "units" in params:
        _menu_set(n, "units2", str(params["units"]), _UNITS)
    return _cooked(n)


# ── 15. constraint_parent (constraintparent) — compose child-in-parent transform ─────────────────
@endpoint("constraint_parent")
def constraint_parent(params):
    """KineFX Constraint Parent (constraintparent) — composes a child transform under a parent
    transform (the CHOP parenting primitive). `input` (input 0) = child; `input1` (input 1) = parent;
    optional `input2` (input 2). Combine-only (no scalar parms). SECURITY: no file/code surface."""
    n = child_after(params["input"], "constraintparent", params.get("name"))
    if params.get("input1"):
        _chop_input(n, params["input1"], 1)
    if params.get("input2"):
        _chop_input(n, params["input2"], 2)
    return _cooked(n)


# ── 16. constraint_parent_extended (constraintparentx) — parenting with a channel mask ───────────
@endpoint("constraint_parent_extended")
def constraint_parent_extended(params):
    """KineFX Constraint Parent (Extended) (constraintparentx) — parenting with a `write_mask`
    (int bitmask of channels written, default 511). `input` (input 0) = child (required — this node
    errors with no source); optional `input1`/`input2` = parent / extra. Named `_extended` to avoid a
    collision with constraint_parent. SECURITY: no file/code surface."""
    n = child_after(params["input"], "constraintparentx", params.get("name"))
    if params.get("input1"):
        _chop_input(n, params["input1"], 1)
    if params.get("input2"):
        _chop_input(n, params["input2"], 2)
    if "write_mask" in params:
        _set_int(n, "writemask", params["write_mask"], 0, 511)
    return _cooked(n)


# ── 17. constraint_simple_blend (constraintsimpleblend) — simple two-stream blend ────────────────
@endpoint("constraint_simple_blend")
def constraint_simple_blend(params):
    """KineFX Constraint Simple Blend (constraintsimpleblend) — a lightweight blend of two constraint
    streams by `blend`. `input` (input 0) = A; `input1` (input 1) = B. `write_mask` = channels written
    (int bitmask, default 511). SECURITY: no file/code surface."""
    n = child_after(params["input"], "constraintsimpleblend", params.get("name"))
    if params.get("input1"):
        _chop_input(n, params["input1"], 1)
    if "blend" in params:
        _set_float(n, "blend", params["blend"], 0.0, 1.0)
    if "rotation_blending" in params:
        _set_int(n, "rotblend", params["rotation_blending"], 0, 2)
    if "write_mask" in params:
        _set_int(n, "writemask", params["write_mask"], 0, 511)
    return _cooked(n)


# ── 18. constraint_offset_blend (constraintoffsetblend) — blend an offset across streams ─────────
@endpoint("constraint_offset_blend")
def constraint_offset_blend(params):
    """KineFX Constraint Offset Blend (constraintoffsetblend) — blends an offset across up to four
    constraint streams by `blend`. `input` (input 0) = base; `input1`..`input3` = additional streams.
    `write_mask` = channels written (int bitmask, default 511). SECURITY: no file/code surface."""
    n = child_after(params["input"], "constraintoffsetblend", params.get("name"))
    for i, key in enumerate(("input1", "input2", "input3"), start=1):
        if params.get(key):
            _chop_input(n, params[key], i)
    if "blend" in params:
        _set_float(n, "blend", params["blend"], 0.0, 1.0)
    if "rotation_blending" in params:
        _set_int(n, "rotblend", params["rotation_blending"], 0, 2)
    if "write_mask" in params:
        _set_int(n, "writemask", params["write_mask"], 0, 511)
    return _cooked(n)

"""SOP ML data-prep lane — the data-preparation front end to Houdini 21's native ML SOPs:
build training EXAMPLES from geometry, augment/partition them, generate + serialize skeleton POSES,
and wire the learned character DEFORMER. All params + menu tokens + input roles verified against live
H21.0.671 via hython probes.

Wrapped (7 node types, all net-new — none wrapped elsewhere):
  ml_example (ml_example)              — pair an Input Component (in0) + Target Component (in1) into a
                                         training example. Pure operator.
  ml_extract_example (ml_extractexample) — pull one example (by index) back out of an example stream.
  ml_attrib_generate (ml_attribgenerate) — synthesise randomised attributes on a prototype (data
                                         augmentation for training sets). distribution is a bounded
                                         distribution-TOKEN string ('uniform'/'gaussian'/... — probe-
                                         confirmed a data token, NOT a VEX/python/expression surface).
  ml_pose_generate (ml_posegenerate)  — sample randomised skeleton poses off a Pose Prototype (in0) —
                                         pose-space training data. Pure generator (bounded by
                                         sample_count).
  ml_pose_serialize (ml_poseserialize)— flatten a skeleton pose into a serial point ATTRIBUTE
                                         (serial_attribute) — NO file param despite the name.
  ml_example_partition (ml_examplepartition) — split an Examples stream into <= max_part_size parts
                                         (training-batch prep). Pure operator.
  ml_deform (ml_deform)               — WIRE-ONLY: the learned character deformer (inference). Loads a
                                         trained .onnx-style model from a confined `modelfile` and
                                         applies it to the Skin-to-Deform (in0) driven by a Capture Pose
                                         (in1) + Animated Pose (in2) [+ Residual Blend Shapes (in3)].

Not wrapped: ml_regressionlinear / ml_regressionproximity / ml_regressionkernel — already covered by
  the shipped `ml_regression` tool. The existing `ml_regression`
  handler (handlers/ml.py) ALREADY creates these exact three node types (method=linear|kernel|proximity)
  and wires Labeled Examples -> in0 / Input Component -> in1, setting kernel/width/weightdecay/input+
  output attributes. Wrapping the raw regression SOPs again would be duplicate NODE-TYPE coverage with
  no security gain (these nodes carry NO file/code param). The probe DID reveal a richer surface on the
  raw nodes (batch mode, error_threshold, volume I/O, polynomial/sigmoid kernel knobs, multi input/
  output) — noted as a future ENHANCEMENT to `ml_regression`, not a parallel tool.

SECURITY (data-only):
  * FsPath surfaces: exactly ONE — ml_deform.modelfile (READ, realpath-confined via confined_path).
    ml_poseserialize / ml_exampleserialize* write to a point ATTRIBUTE, not a file (the file-writing
    ML-example ROPs — ml_exampleoutput/ml_exampleraw/rop_ml_exampleraw — are already shipped as the
    WIRE-ONLY export_ml_example_* tools; NOT re-wrapped here).
  * WIRE-ONLY: ml_deform. It loads a trained model on cook, and a malformed model file can crash
    Houdini on load (same failure mode documented for onnx_inference/ml_volume_upres in ml.py), so the
    handler BUILDS + wires + sets typed params + sets the confined modelfile, then RETURNS UNCOOKED —
    it NEVER presses `reload` and NEVER cooks the node (the USER fires the deform with a hash-pinned
    model). provider (Execution Provider) menu is left unset; the `reload` button is never pressed.
  * NO VEX / python / hscript / expression / snippet / callback param is exposed anywhere (probe-
    confirmed). ml_attribgenerate.distribution is a bounded distribution-name token, not code.
"""

import hou
from houdini_executor.server import (
    endpoint, child_after, clamp, bridge_input, confined_path,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set

try:
    from houdini_executor.governor import governor_gate
except Exception:  # noqa: BLE001 — governor is advisory telemetry; never block handler import
    def governor_gate(op_label):
        return {"band": "unknown"}


# ── shared probe-safe helpers (house idiom: never invent a parm) ─────────────────────────────────




def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  m=index-menu(tokens)."""
    for key, parm, kind, extra in spec:
        if key not in params:
            continue
        v = params[key]
        if kind == "f":
            _try_set(node, parm, clamp(float(v), extra[0], extra[1]))
        elif kind == "i":
            _try_set(node, parm, int(clamp(int(v), extra[0], extra[1])))
        elif kind == "b":
            _try_set(node, parm, bool(v))
        elif kind == "s":
            _try_set(node, parm, str(v))
        elif kind == "m":
            _menu_set(node, parm, str(v), extra)


def _geo_or_none(n):
    try:
        return n.geometry()
    except Exception:  # noqa: BLE001
        return None


def _finish_op(n, **extra):
    """Cook + report counts; degrade to cooked:false + errors on an input-starved / not-yet-cooked
    node (never crash). Used ONLY by the pure data-prep operators (no model file)."""
    r = {"node": n.path()}
    try:
        n.cook()
    except Exception:  # noqa: BLE001 — surfaced via n.errors() below
        pass
    g = _geo_or_none(n)
    if g is None:
        r["cooked"] = False
        e = [str(x) for x in (n.errors() or [])]
        if e:
            r["errors"] = e
    else:
        r["cooked"] = True
        r["points"] = len(g.points())
        r["prims"] = len(g.prims())
    r.update(extra)
    return r


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Pure data-prep operators (no file, no training solve — cooked-readback)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("ml_example")
def ml_example(params):
    """ML Example — pair an Input Component with a Target Component into a single training EXAMPLE
    (ml_example) — the atom of a supervised ML dataset (input features -> target values). `input` (the
    Input Component) is input 0; `target` (the Target Component) is input 1 and is REQUIRED to form a
    complete example. use_packed_input / use_packed_target treat each side as a packed component;
    input_validity_attrib / target_validity_attrib name per-point validity masks. Feed the result to
    ml_example_partition / ml_extract_example or the shipped export_ml_example_* writers."""
    governor_gate("ml_example")
    n = child_after(params["input"], "ml_example", params.get("name"))
    if params.get("target"):
        bridge_input(n, params["target"], index=1, name_hint="target")
    _apply(n, params, [
        ("use_packed_input", "usepackedinputcomponent", "b", None),
        ("use_packed_target", "usepackedtargetcomponent", "b", None),
        ("input_validity_attrib", "inputvalidityattribute", "s", None),
        ("target_validity_attrib", "targetvalidityattribute", "s", None),
    ])
    return _finish_op(n)


@endpoint("ml_extract_example")
def ml_extract_example(params):
    """ML Extract Example — pull a single example (by index) back out of an Examples stream
    (ml_extractexample) — inspect / preview one training sample. `input` (an Examples stream, e.g. from
    ml_example) is input 0. index selects which example; keep_packed keeps the extracted component
    packed rather than unpacking it to native geometry."""
    governor_gate("ml_extract_example")
    n = child_after(params["input"], "ml_extractexample", params.get("name"))
    _apply(n, params, [
        ("index", "index", "i", (0, 100000000)),
        ("keep_packed", "keeppacked", "b", None),
    ])
    return _finish_op(n)


@endpoint("ml_attrib_generate")
def ml_attrib_generate(params):
    """ML Attribute Generate — synthesise randomised attribute values on a prototype
    (ml_attribgenerate) — data-augment a training set with controlled random inputs. `input` (the
    Prototype geometry) is input 0. random_seed / sample_count drive the augmentation; the first
    contribution is configured by point_attribute (the attribute to write), tuple_size (its component
    count), and distribution (a bounded distribution-name TOKEN: 'uniform' | 'gaussian' | 'normal' |
    'poisson' | ... — a data token, NOT a code/expression surface). Multi-contribution multiparm rows
    beyond the first are left at default."""
    governor_gate("ml_attrib_generate")
    n = child_after(params["input"], "ml_attribgenerate", params.get("name"))
    _apply(n, params, [
        ("random_seed", "randomseed", "i", (0, 1000000000)),
        ("sample_count", "samplecount", "i", (1, 1000000)),
        ("point_attribute", "pointattribute1", "s", None),
        ("tuple_size", "tuplesize1", "i", (1, 256)),
        ("distribution", "distribution1", "s", None),
    ])
    return _finish_op(n)


@endpoint("ml_pose_generate")
def ml_pose_generate(params):
    """ML Pose Generate — sample randomised skeleton poses from a Pose Prototype (ml_posegenerate) — the
    training-data generator for pose-space / ML deformers (produces sample_count varied poses of the
    rig). `input` (the Pose Prototype — a KineFX skeleton) is input 0. random_seed seeds the sampling;
    sample_count how many poses to generate (bounded); joint_group restricts which joints are varied.
    Pure generator (no model file, no training)."""
    governor_gate("ml_pose_generate")
    n = child_after(params["input"], "ml_posegenerate", params.get("name"))
    _apply(n, params, [
        ("random_seed", "randomseed", "i", (0, 1000000000)),
        ("sample_count", "samplecount", "i", (1, 1000000)),
        ("joint_group", "jointgroup", "s", None),
    ])
    return _finish_op(n)


@endpoint("ml_pose_serialize")
def ml_pose_serialize(params):
    """ML Pose Serialize — flatten a skeleton pose into a serial point ATTRIBUTE (ml_poseserialize) —
    turn a rig pose into the fixed-length feature vector an ML model consumes. `input` (the Pose — a
    KineFX skeleton) is input 0. serial_attribute names the output attribute; mode = subskeleton |
    alllocal picks the serialization scheme; for subskeleton, include_world_rotation adds the root world
    rotation; for alllocal, include_rotation / include_translation (+ local_rotation_group /
    local_translation_group) select which local channels are written. NO file param (writes an
    attribute, not a file)."""
    governor_gate("ml_pose_serialize")
    n = child_after(params["input"], "ml_poseserialize", params.get("name"))
    _apply(n, params, [
        ("joint_group", "jointgroup", "s", None),
        ("serial_attribute", "serialattribute", "s", None),
        ("mode", "mode", "m", ("subskeleton", "alllocal")),
        ("include_world_rotation", "subskeletonincludeworldrotation", "b", None),
        ("include_rotation", "alllocalrotation", "b", None),
        ("local_rotation_group", "localrotationgroup", "s", None),
        ("include_translation", "alllocaltranslation", "b", None),
        ("local_translation_group", "localtranslationgroup", "s", None),
    ])
    return _finish_op(n)


@endpoint("ml_example_partition")
def ml_example_partition(params):
    """ML Example Partition — split an Examples stream into parts no larger than max_part_size
    (ml_examplepartition) — batch a large training set into manageable chunks. `input` (an Examples
    stream) is input 0. max_part_size caps the number of examples per part. Pure operator."""
    governor_gate("ml_example_partition")
    n = child_after(params["input"], "ml_examplepartition", params.get("name"))
    _apply(n, params, [
        ("max_part_size", "maximumpartsize", "i", (1, 100000000)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# WIRE-ONLY inference (loads a trained model on cook — BUILT + wired + configured, NEVER cooked here)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("ml_deform")
def ml_deform(params):
    """WIRE-ONLY: build the learned character deformer (ml_deform) — apply a TRAINED model to deform a
    skin, driven by a skeleton pose. Configured but NEVER cooked here (a malformed model file can crash
    Houdini on load — same safety posture as onnx_inference / ml_volume_upres; the USER fires the deform
    with a hash-pinned model). Inputs: `input` = Skin to Deform (input 0); `capture_pose` = Capture Pose
    (input 1); `animated_pose` = Animated Pose (input 2); `residual_blend_shapes` = Residual Blend Shapes
    (input 3, optional). modelfile = the trained model (realpath READ-confined to the working dir);
    joint_group restricts the driving joints; enforce_joint_limits + joint_limits clamp the pose. The
    `reload` button is NEVER pressed and the node is NEVER cooked. Returns {node, built:True,
    cooked:False}."""
    governor_gate("ml_deform")
    n = child_after(params["input"], "ml_deform", params.get("name"))
    if params.get("capture_pose"):
        bridge_input(n, params["capture_pose"], index=1, name_hint="capture_pose")
    if params.get("animated_pose"):
        bridge_input(n, params["animated_pose"], index=2, name_hint="animated_pose")
    if params.get("residual_blend_shapes"):
        bridge_input(n, params["residual_blend_shapes"], index=3, name_hint="residual_blend_shapes")
    modelfile = None
    if params.get("modelfile"):
        modelfile = confined_path(str(params["modelfile"]))  # realpath READ-confined
        _try_set(n, "modelfile", modelfile)
    _apply(n, params, [
        ("joint_group", "jointgroup", "s", None),
        ("enforce_joint_limits", "enforcejointlimits", "b", None),
        ("joint_limits", "jointlimits", "s", None),
    ])
    # NEVER press `reload` and NEVER cook — loading an unvalidated model can segfault Houdini (see
    # ml.py onnx_inference). Return the wired-but-uncooked structure; the USER fires the deform.
    return {"node": n.path(), "built": True, "cooked": False, "modelfile": modelfile,
            "note": "ML deformer wired; model resolves on downstream cook — pass a hash-pinned model"}

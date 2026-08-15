"""Crowd / Agent — data-only handlers. Params verified against live H21.0.671; every endpoint proven with a headless cook
over the reusable agent fixture (build_test_agent) plus the SOP->USD
crowd bridge it feeds.

This wave spans FIVE Houdini contexts (the Crowd/Agent domain is not single-context):
  SOP (cooks to agent geometry over the fixture):
    agent_clip            agentclip::2.0 — bakes a MotionClip (input1) onto Agents (input0) as a clip.
  DOP crowd nodes (BUILT inside a dopnet, WIRE-ONLY like crowd_1 / sim.py `rbd_force`; they only run
  inside a crowdsolver, so the handler creates + configures + returns the node, never runs the sim):
    crowd_trigger         crowdtrigger::2.0    — a per-agent trigger condition (0 inputs).
    crowd_trigger_logic   crowdtriggerlogic::2.0 — boolean combine of up to 2 trigger streams.
    crowd_transition      crowdtransition::3.0 — a state transition (input0 = a trigger/triggerlogic).
  LOP crowd nodes (BUILT in /stage, cooked onto the USD stage; the SOP->Solaris crowd render path):
    crowd_sop_import      sopcrowdimport — import a SOP crowd (agents) onto the USD stage.
    crowd_render_procedural houdinicrowdprocedural — a render-time crowd delayed-load procedural.
    bake_skinning         bakeskinning — bake UsdSkel skinning to deformed point positions on a stage.
  CHOP (reads an agent SOP, emits transform channels):
    agent_channels        agent (CHOP) — evaluate an agent's clip/pose transforms into CHOP tracks.
  Object (a scene camera mounted on a crowd agent):
    agent_camera          agentcam — an OBJ camera driven by an agent's camera definition.

SECURITY (data-only): NO code/callback/VEX/expression parm is ever set or exposed —
  * crowd_transition   leaves localexpression / transitiondescription at default;
  * crowd_trigger      leaves custom_snippet / vex_cwdpath at default;
  * agent_camera       leaves the viewport pickscript callback at default.
File surface: agent_clip's per-clip fbx/usd source files (file1 / usdfile1) are routed through
confined_path(); crowd_sop_import's agent cache-SAVE writer paths (animsavepath / geosavepath) are
NOT exposed (left disabled) so a cook never writes. All other string params surfaced are attribute /
group / clip / state / object-NAMES or scene-graph node PATHS — never filesystem paths, never code.
The DOP crowd SOLVERS (crowdsolver, ragdollsolver, ...) are excluded from this slice (waveplan
solvers_defer) and are NOT wrapped here.
"""

import hou
from houdini_executor.server import (
    clamp, child_after, confined_path, resolve_node, stage_context, endpoint,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────


def _menu_set(node, parm, token, tokens):
    """Set a menu parm by its token. H21 crowd/agent menus accept the token string directly
    (verified live); fall back to the ordered-menu index if a string set is rejected."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(str(token))
        return True
    except Exception:
        pass
    if token in tokens:
        try:
            p.set(tokens.index(token))
            return True
        except Exception:
            return False
    return False




def _fresh_geo(name):
    return hou.node("/obj").createNode("geo", name or "crowd")


def _cooked(n):
    """Cook a SOP and report point/prim + agent-prim counts (the SOP greenness proof)."""
    n.cook(force=True)
    g = n.geometry()
    ap = [p for p in g.prims() if p.type() == hou.primType.Agent]
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "agentprims": len(ap)}


# ── DOP builder (mirrors crowd_1 / sim.py rbd_force) ──────────────────────────────────────────────
def _dop_build(params, ntype):
    """Create `ntype` inside a dopnet and return (node, dopnet, holder_geo_or_None).
      * params["dopnet"] -> an existing dopnet path; create the node inside it.
      * else             -> a fresh /obj geo (`name`) holding a new dopnet.
    Optional params["input"] wires an upstream DOP node (a path inside the same dopnet) into input 0
    (e.g. a crowd trigger stream). The node is BUILT, never cooked-as-sim here."""
    holder = None
    if params.get("dopnet"):
        dn = resolve_node(str(params["dopnet"]))
        if not isinstance(dn, hou.Node):
            raise ValueError("no such dopnet: %s" % params["dopnet"])
    else:
        holder = _fresh_geo(params.get("name"))
        dn = holder.createNode("dopnet", "crowd_dop")
    n = dn.createNode(ntype, params.get("node_name"))
    if params.get("input"):
        n.setInput(0, resolve_node(str(params["input"])))
    n.moveToGoodPosition()
    try:
        dn.layoutChildren()
    except Exception:
        pass
    return n, dn, holder


def _dop_result(n, dn, holder, extra=None):
    res = {"node": n.path(), "dopnet": dn.path(), "node_type": n.type().name(), "built": True}
    if holder is not None:
        holder.setDisplayFlag(False)
        holder.layoutChildren()
        res["geo"] = holder.path()
    if extra:
        res.update(extra)
    return res


# ── LOP builder (mirrors usd.py _stage_node) ──────────────────────────────────────────────────────
def _stage_build(params, ntype):
    """Create a LOP `ntype`; wire after params["input"] (an existing LOP path) if given, else a fresh
    generator in /stage. Returns the node."""
    if params.get("input"):
        src = resolve_node(str(params["input"]))
        parent = src.parent()
        nm = params.get("name")
        n = parent.createNode(ntype, nm) if nm else parent.createNode(ntype)
        n.setInput(0, src)
    else:
        stage = stage_context()
        nm = params.get("name")
        n = stage.createNode(ntype, nm) if nm else stage.createNode(ntype)
    n.moveToGoodPosition()
    return n


def _lop_result(n):
    n.cook(force=True)
    prims = 0
    try:
        stg = n.stage()
        if stg is not None:
            prims = sum(1 for _ in stg.Traverse())
    except Exception:
        pass
    return {"node": n.path(), "node_type": n.type().name(), "stage_prims": prims,
            "errors": list(n.errors())}


# ── CHOP builder (mirrors chop_anim_1 _source_net) ────────────────────────────────────────────────
def _fresh_chopnet(name):
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("chopnet", name) if name else obj.createNode("chopnet")


def _chop_net(params):
    if params.get("chopnet"):
        net = resolve_node(str(params["chopnet"]))
        if net.childTypeCategory() != hou.chopNodeTypeCategory():
            raise ValueError("chopnet is not a CHOP network: %s" % params["chopnet"])
        return net
    return _fresh_chopnet(params.get("name"))


# ── ordered-menu token tuples (position == the stored index for the index-fallback path) ──────────
_CLIP_SOURCE = ("subnet", "fbx", "file", "chop", "usd", "sop")
_TRIGGER_TYPE = tuple(str(i) for i in range(14))       # crowdtrigger `type` menu 0..13
_TRIGGER_SOURCE = ("sop", "dopdata")
_COND3 = ("0", "1", "2")                                # generic 3-way comparison menus
_LOGIC_OP = ("AND", "OR", "NOT1", "NOT2", "XOR", "NAND", "NOR")
_VIS_ENABLE = ("viewport", "always")
_CHOP_FETCH = ("clip", "pose")
_CHOP_SPACE = ("local", "world")
_CHOP_RANGE = ("full", "frame", "user")
_CHOP_UNITS = ("frames", "samples", "seconds")


# ── 1. agentclip::2.0 (SOP) — B chain, input0=Agents, input1=MotionClip ───────────────────────────
@endpoint("agent_clip")
def agent_clip(params):
    """Crowd Agent Clip (agentclip::2.0) — bakes a motion source onto agent primitives as a named
    clip. `agents` (input 0) = the agent primitives; `motion_clip` (input 1) = a KineFX MotionClip
    to bake (used when source=sop/chop). `source` picks where clip #1's animation comes from.
    SECURITY: the per-clip fbx/file (`file1`) and usd (`usd_file`) source paths are confined to the
    working dir; string params surfaced are clip/attribute/pattern NAMES only; no code surface."""
    n = child_after(params["agents"], "agentclip::2.0", params.get("name"))
    if params.get("motion_clip"):
        n.setInput(1, resolve_node(str(params["motion_clip"])))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "set_current_clip" in params:
        _try_set(n, "setcurrentclip", bool(params["set_current_clip"]))
    if "current_clip" in params:
        _try_set(n, "currentclip", str(params["current_clip"]))
    if "set_clip_time" in params:
        _try_set(n, "setcliptime", bool(params["set_clip_time"]))
    if "clip_time" in params:
        _try_set(n, "cliptime", clamp(float(params["clip_time"]), -1e9, 1e9))
    if "apply_locomotion" in params:
        _try_set(n, "applylocomotion", bool(params["apply_locomotion"]))
    if "create_locomotion_joint" in params:
        _try_set(n, "createlocomotionjoint", bool(params["create_locomotion_joint"]))
    if "locomotion_node" in params:
        _try_set(n, "locomotionnode", str(params["locomotion_node"]))
    if "clip_name" in params:
        _try_set(n, "name1", str(params["clip_name"]))
    if "source" in params:
        _menu_set(n, "source1", str(params["source"]), _CLIP_SOURCE)
    if "prim_pattern" in params:
        _try_set(n, "primpattern1", str(params["prim_pattern"]))
    if "clip_file" in params:
        _try_set(n, "file1", confined_path(str(params["clip_file"])))
    if "usd_file" in params:
        _try_set(n, "usdfile1", confined_path(str(params["usd_file"])))
    if "keep_ref" in params:
        _try_set(n, "keepref1", bool(params["keep_ref"]))
    return _cooked(n)


# ── 2. crowdtrigger::2.0 (DOP) — a per-agent trigger condition ─────────────────────────────────────
@endpoint("crowd_trigger")
def crowd_trigger(params):
    """Crowd Trigger (crowdtrigger::2.0) — evaluates a per-agent condition (proximity, attribute,
    speed, distance, …) and writes a trigger attribute; feeds a crowd_transition / crowd_trigger_logic.
    BUILT inside a dopnet (WIRE-ONLY; no inputs). `type` selects the condition family (0..13).
    SECURITY: the `custom_snippet` / `vex_cwdpath` VEX parms are LEFT AT DEFAULT (never exposed);
    string params surfaced are trigger/attribute/object NAMES only; no file/code surface."""
    params = dict(params)
    params.pop("input", None)  # crowdtrigger takes no inputs
    n, dn, holder = _dop_build(params, "crowdtrigger::2.0")
    if "use_group" in params:
        _try_set(n, "usegroup", bool(params["use_group"]))
    if "part_group" in params:
        _try_set(n, "partgroup", str(params["part_group"]))
    if "type" in params:
        _menu_set(n, "type", str(params["type"]), _TRIGGER_TYPE)
    if "trigger_name" in params:
        _try_set(n, "triggername", str(params["trigger_name"]))
    if "trigger_attrib" in params:
        _try_set(n, "triggerattrib", str(params["trigger_attrib"]))
    if "fuzzy_output" in params:
        _try_set(n, "fuzzyoutput", bool(params["fuzzy_output"]))
    if "trigger_source" in params:
        _menu_set(n, "triggersource", str(params["trigger_source"]), _TRIGGER_SOURCE)
    if "bounding_object" in params:
        _try_set(n, "boundingobject", str(params["bounding_object"]))
    if "bounds_condition" in params:
        _menu_set(n, "boundscondition", str(params["bounds_condition"]), _COND3)
    if "attribute_name" in params:
        _try_set(n, "attributename", str(params["attribute_name"]))
    if "attribute_condition" in params:
        _menu_set(n, "attributecondition", str(params["attribute_condition"]), _COND3)
    if "attribute_comparison_value" in params:
        _try_set(n, "attributecomparisonvalue",
                 clamp(float(params["attribute_comparison_value"]), -1e12, 1e12))
    if "distance_condition" in params:
        _menu_set(n, "distancecondition", str(params["distance_condition"]), _COND3)
    if "distance" in params:
        _try_set(n, "distance", clamp(float(params["distance"]), 0.0, 1e12))
    if "speed_condition" in params:
        _menu_set(n, "speedcondition", str(params["speed_condition"]), _COND3)
    if "particle_speed" in params:
        _try_set(n, "particlespeed", clamp(float(params["particle_speed"]), 0.0, 1e12))
    return _dop_result(n, dn, holder)


# ── 3. crowdtriggerlogic::2.0 (DOP) — boolean combine of trigger streams ──────────────────────────
@endpoint("crowd_trigger_logic")
def crowd_trigger_logic(params):
    """Crowd Trigger Logic (crowdtriggerlogic::2.0) — combines up to two trigger streams with a
    boolean `operation` and writes a trigger attribute. BUILT inside a dopnet (WIRE-ONLY). `input`
    = trigger stream 1 (input 0); `input2` = trigger stream 2 (input 1). SECURITY: attribute-NAME
    string only; no file/code surface."""
    n, dn, holder = _dop_build(params, "crowdtriggerlogic::2.0")
    if params.get("input2"):
        n.setInput(1, resolve_node(str(params["input2"])))
    if "operation" in params:
        _menu_set(n, "operation", str(params["operation"]), _LOGIC_OP)
    if "trigger_attrib" in params:
        _try_set(n, "triggerattrib", str(params["trigger_attrib"]))
    return _dop_result(n, dn, holder)


# ── 4. crowdtransition::3.0 (DOP) — a state transition ────────────────────────────────────────────
@endpoint("crowd_transition")
def crowd_transition(params):
    """Crowd Transition (crowdtransition::3.0) — defines a transition between two crowd states, fired
    by a trigger. BUILT inside a dopnet (WIRE-ONLY). `input` (input 0, REQUIRED to cook) = a crowd
    trigger / trigger-logic stream. SECURITY: the `localexpression` and `transitiondescription`
    VEX/expression parms are LEFT AT DEFAULT (never exposed); string params surfaced are state/clip/
    group NAMES only; no file/code surface."""
    n, dn, holder = _dop_build(params, "crowdtransition::3.0")
    if "use_group" in params:
        _try_set(n, "usegroup", bool(params["use_group"]))
    if "part_group" in params:
        _try_set(n, "partgroup", str(params["part_group"]))
    if "in_state" in params:
        _try_set(n, "instate", str(params["in_state"]))
    if "out_state" in params:
        _try_set(n, "outstate", str(params["out_state"]))
    if "use_out_clip" in params:
        _try_set(n, "useoutclip", bool(params["use_out_clip"]))
    if "out_clip" in params:
        _try_set(n, "outclip", str(params["out_clip"]))
    if "duration" in params:
        _try_set(n, "duration", clamp(float(params["duration"]), 0.0, 1e6))
    if "random_start" in params:
        _try_set(n, "randomstart", bool(params["random_start"]))
    if "random_start_offset" in params:
        _try_set(n, "randomstartoffset", clamp(float(params["random_start_offset"]), -1e6, 1e6))
    if "random_start_seed" in params:
        _try_set(n, "randomstartseed", clamp(float(params["random_start_seed"]), 0.0, 1e9))
    if "enable_interrupt" in params:
        _try_set(n, "enableinterrupt", bool(params["enable_interrupt"]))
    if "detach_from_parent" in params:
        _try_set(n, "detachfromparent", bool(params["detach_from_parent"]))
    if "animation_match" in params:
        _try_set(n, "animationmatch", bool(params["animation_match"]))
    if "max_animation_time" in params:
        _try_set(n, "maxanimationtime", clamp(float(params["max_animation_time"]), 0.0, 1e6))
    return _dop_result(n, dn, holder)


# ── 5. sopcrowdimport (LOP) — import a SOP crowd onto the USD stage ───────────────────────────────
@endpoint("crowd_sop_import")
def crowd_sop_import(params):
    """Crowd SOP Import (sopcrowdimport) — imports a SOP crowd (agent primitives) onto the USD stage
    as UsdSkel characters. `sop_path` = the SOP carrying the agents (a scene-graph node path);
    optional `input` = a LOP to layer onto. BUILT + cooked in /stage. SECURITY: the agent cache-SAVE
    writer paths (animsavepath / geosavepath) are NOT exposed and left disabled, so a cook never
    writes to disk; `sop_path` is a scene-graph node PATH, not a filesystem path. No code surface."""
    src = resolve_node(str(params["sop_path"]))
    n = _stage_build(params, "sopcrowdimport")
    _try_set(n, "soppath", src.path())
    if "behavior" in params:
        _try_set(n, "behavior", str(params["behavior"]))
    if "enable_emission" in params:
        _try_set(n, "enableemission", bool(params["enable_emission"]))
    if "agent_geometry" in params:
        _try_set(n, "agentgeometry", str(params["agent_geometry"]))
    if "path_prefix" in params:
        _try_set(n, "enable_pathprefix", True)
        _try_set(n, "pathprefix", str(params["path_prefix"]))
    if "bind_materials" in params:
        _try_set(n, "bindmaterials", str(params["bind_materials"]))
    res = _lop_result(n)
    res["sop_path"] = src.path()
    return res


# ── 6. houdinicrowdprocedural (LOP) — render-time crowd delayed-load procedural ───────────────────
@endpoint("crowd_render_procedural")
def crowd_render_procedural(params):
    """Crowd Render Procedural (houdinicrowdprocedural) — sets up a render-time (Karma) crowd
    delayed-load procedural on the USD stage so agents are expanded at render, not baked. `input`
    (opt) = a LOP stage carrying the crowd; `proc_prim` / `prim_pattern` target the agent prims.
    BUILT + cooked in /stage. SECURITY: prim-path / camera-path scene strings only; no file/code
    surface."""
    n = _stage_build(params, "houdinicrowdprocedural")
    if "proc_prim" in params:
        _try_set(n, "procprim", str(params["proc_prim"]))
    if "prim_pattern" in params:
        _try_set(n, "primpattern", str(params["prim_pattern"]))
    if "use_lod_camera" in params:
        _try_set(n, "uselodcamera", bool(params["use_lod_camera"]))
    if "lod_camera" in params:
        _try_set(n, "lodcamera", str(params["lod_camera"]))
    if "lod_threshold" in params:
        _try_set(n, "lodthreshold", clamp(float(params["lod_threshold"]), 0.0, 1e9))
    if "optimize_identical_poses" in params:
        _try_set(n, "optimizeidenticalposes", bool(params["optimize_identical_poses"]))
    if "offscreen_quality" in params:
        _try_set(n, "offscreenquality", clamp(float(params["offscreen_quality"]), 0.0, 1e6))
    if "bake_prototype_agents" in params:
        _try_set(n, "bakeprototypeagents", bool(params["bake_prototype_agents"]))
    if "bake_all_agents" in params:
        _try_set(n, "bakeallagents", bool(params["bake_all_agents"]))
    if "visualize_instances" in params:
        _try_set(n, "visualizeinstances", bool(params["visualize_instances"]))
    if "enable_visualization" in params:
        _menu_set(n, "enablevisualization", str(params["enable_visualization"]), _VIS_ENABLE)
    return _lop_result(n)


# ── 7. bakeskinning (LOP) — bake UsdSkel skinning to deformed positions ───────────────────────────
@endpoint("bake_skinning")
def bake_skinning(params):
    """Crowd Bake Skinning (bakeskinning) — bakes UsdSkel skinning on an input stage down to deformed
    point positions (the crowd render-prep step after crowd_sop_import). `input` (REQUIRED) = the LOP
    stage carrying skinned characters/agents. BUILT + cooked in /stage. Pure stage operation — no data
    params, no file/code surface."""
    if not params.get("input"):
        raise ValueError("bake_skinning requires `input` (a LOP stage with skinned characters)")
    n = _stage_build(params, "bakeskinning")
    return _lop_result(n)


# ── 8. agent (CHOP) — evaluate an agent's clip/pose transforms into channels ──────────────────────
@endpoint("agent_channels")
def agent_channels(params):
    """Crowd Agent Channels (agent CHOP) — evaluates an agent primitive's clip or pose transforms
    into CHOP tracks (drive rigs/lights/objects from crowd animation). `sop_path` = the SOP carrying
    the agent; `fetch_mode` = clip|pose. Built in a fresh chopnet (or an existing `chopnet`).
    Verification is by track/sample counts. SECURITY: `sop_path` is a scene-graph node PATH; group/
    clip strings are NAMES; no file/code surface."""
    net = _chop_net(params)
    src = resolve_node(str(params["sop_path"]))
    n = net.createNode("agent", params.get("node_name"))
    _try_set(n, "soppath", src.path())
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "fetch_mode" in params:
        _menu_set(n, "fetchmode", str(params["fetch_mode"]), _CHOP_FETCH)
    if "in_place" in params:
        _try_set(n, "inplace", bool(params["in_place"]))
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "space" in params:
        _menu_set(n, "space", str(params["space"]), _CHOP_SPACE)
    if "range" in params:
        _menu_set(n, "range", str(params["range"]), _CHOP_RANGE)
    if "start" in params:
        _try_set(n, "start", clamp(float(params["start"]), -1e6, 1e6))
    if "end" in params:
        _try_set(n, "end", clamp(float(params["end"]), -1e6, 1e6))
    if "rate" in params:
        _try_set(n, "rate", clamp(float(params["rate"]), 0.0, 1e6))
    if "units" in params:
        _menu_set(n, "units", str(params["units"]), _CHOP_UNITS)
    n.moveToGoodPosition()
    try:
        n.cook(force=True)
    except hou.OperationFailed:
        pass  # surface via errors below rather than raising
    tracks = n.tracks()
    samples = len(tracks[0].allSamples()) if tracks else 0
    return {"node": n.path(), "chopnet": net.path(), "tracks": len(tracks),
            "samples": samples, "errors": list(n.errors())}


# ── 9. agentcam (Object) — an OBJ camera mounted on a crowd agent ─────────────────────────────────
@endpoint("agent_camera")
def agent_camera(params):
    """Crowd Agent Cam (agentcam) — an /obj camera driven by a crowd agent's own camera definition
    (render through an agent's eyes). `agent_source` = the SOP carrying the agent. BUILT in /obj and
    cooked (its transform), never rendered. SECURITY: the viewport `pickscript` callback is LEFT AT
    DEFAULT (never exposed); `agent_source` / constraint / look-at strings are scene-graph node PATHS;
    no file/code surface."""
    obj = hou.node("/obj")
    name = params.get("name")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    n = obj.createNode("agentcam", name) if name else obj.createNode("agentcam")
    if "agent_source" in params:
        src = resolve_node(str(params["agent_source"]))
        _try_set(n, "agentsource", src.path())
    if "translate" in params:
        _try_set_tuple(n, "t", params["translate"])
    if "rotate" in params:
        _try_set_tuple(n, "r", params["rotate"])
    if "scale_xyz" in params:
        _try_set_tuple(n, "s", params["scale_xyz"])
    if "uniform_scale" in params:
        _try_set(n, "scale", clamp(float(params["uniform_scale"]), 0.0, 1e6))
    if "constraints_on" in params:
        _try_set(n, "constraints_on", bool(params["constraints_on"]))
    if "constraints_path" in params:
        _try_set(n, "constraints_path", str(params["constraints_path"]))
    if "look_at_path" in params:
        _try_set(n, "lookatpath", str(params["look_at_path"]))
    n.moveToGoodPosition()
    try:
        n.cook(force=True)
    except hou.OperationFailed:
        pass
    return {"node": n.path(), "node_type": n.type().name(), "built": True,
            "errors": list(n.errors())}

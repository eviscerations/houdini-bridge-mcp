"""Crowd / Agent — data-only handlers (crowd-source + KineFX agent<->rig bridges). Params
verified against live H21.0.671; every endpoint proven with a
headless cook over the reusable fixtures (build_test_agent  and  build_test_skeleton). Mirrors the Crowd pilot
(crowd_1.py) and the agent-authoring wave (crowd_3.py).

All 6 wrapped nodes are SOP context (they cook to agent / skeleton / point geometry over the fixture).
Input semantics (from the live probe + cook proof):
  crowd_source            crowdsource::3.0            0..2 in — A source; cooks bare to a crowd point
                          stream (formation/scatter). Optional in0 = geometry to scatter agents on.
  crowd_motion_path_trigger crowdmotionpathtrigger    in0 = crowd motion-path points/geometry;
                          optional in1 = a collider/bounding object. Writes a per-agent trigger.
  agent_animation_unpack  kinefx::agentanimationunpack in0 = Agents -> unpacks agent animation to a
                          skeleton pose / rest pose / motion clip.
  agent_character_unpack  kinefx::agentcharacterunpack in0 = Agents -> 3 outputs (out0 = skin shapes,
                          out1 = skeleton, out2 = capture pose).
  agent_from_rig          kinefx::agentfromrig        in0 = a KineFX rig/skeleton -> one Agent prim.
  agent_pose_from_rig     kinefx::agentposefromrig    in0 = Agents, in1 = a rig/skeleton pose ->
                          drives the agent pose from the rig (2 inputs REQUIRED to cook).

SECURITY (data-only): NONE of the 6 wrapped nodes has a file or code/callback/VEX parm (verified:
file_parms == [] and has_code_parm == False for every type). Every string param surfaced is an
attribute / group / joint / clip / state NAME — never a filesystem path, never code. No Button
(crowdmotionpathtrigger `initbounds`) is ever pressed. No confined_path surface exists in this lane.

SKIPPED here:
  * crowdsource, crowdsource::2.0                 — lower versions (highest ::3.0 wrapped).
  * kinefx::adapttoterrain                        — lower version.
  * kinefx::adapttoterrain::2.0                   — no headless green cook: its `configurefbik_joints`
    COM/rest computation fails "No transform attribute exists" and its `defaultconfigs` setup button
    needs interactive viewer-selection state (verified across 5 wiring permutations + Electra biped).
  * testsim_crowdtransition                       — packaged demo/example asset embedding a crowd sim
    (resimulate Button + solver microsolvers); a demo, not a data op (mirrors the *crowdsexample
    nodes not wrapped in crowd_1-4).
  * agentaddclip, agentclipcatalog, agentcliplength, agentclipnames, agentclipsample,
    agentclipsamplerate, agentcliptimes           — Vop-category VEX/VOP graph-authoring building
    blocks; cannot even be created in a SOP network ("Invalid node type name") — they only compile
    inside a rigvop/attribvop VEX graph, exactly the SKIP category. Not cookable standalone.
"""

import hou
from houdini_executor.server import clamp, child_after, bridge_input, endpoint
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────


def _menu_set(node, parm, token, tokens):
    """Set a menu parm by its token. H21 crowd/agent menus accept the token string directly (verified
    live); fall back to the ordered-menu index if a string set is rejected."""
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


def _try_set_tuple(node, parm3, values):
    """Set a 3 scalar-component vector (r/g/b or x/y/z) named parm3 = (a,b,c) suffixes, probe-safe."""
    ok = False
    for comp, v in zip(parm3, values):
        if _try_set(node, comp, float(v)):
            ok = True
    return ok


def _fresh_geo(name):
    return hou.node("/obj").createNode("geo", name or "crowd")


def _cooked(n):
    """Cook a SOP and report point/prim + agent-prim counts on output 0 (the greenness proof)."""
    n.cook(force=True)
    g = n.geometry()
    ap = [p for p in g.prims() if p.type() == hou.primType.Agent]
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "agentprims": len(ap)}


def _cooked_multi(n):
    """Cook a multi-output SOP; report per-output point/prim counts (out0 may be empty by design)."""
    n.cook(force=True)
    outs = {}
    for i in range(n.type().maxNumOutputs()):
        try:
            g = n.geometry(i)
            outs["out%d" % i] = {"points": len(g.points()), "prims": len(g.prims())}
        except Exception:
            outs["out%d" % i] = {"points": -1, "prims": -1}
    g0 = n.geometry(0)
    return {"node": n.path(), "points": len(g0.points()), "prims": len(g0.prims()),
            "outputs": outs}


# ── ordered-menu token tuples (position == the stored index for the index-fallback path) ─────────
_LAYOUT = ("0", "1")
_LAYOUTORIENT = ("xy", "yz", "zx")
_RANDMETHOD = ("customdiscrete", "bynumber")
_VIEWPORTLOD = ("full", "points", "box", "centroid", "hidden")
_CLIPTIMEUNITS = ("seconds", "phase")
_TRIGGERTYPE = ("time", "bounds", "objectdist", "raycast", "neighbordist", "clip")
_BOUNDTYPE = ("usebbox", "usebsphere", "usebobject", "usebvolume", "usebconvex")
_DIRMODE = ("orient", "vel", "attrib")
_DISTOBJTYPE = ("surface", "pointcloud")
_BOUNDCOMP = ("inside", "outside", "incoming", "outgoing")
_TIMECOMP = ("lessthan", "lessthanequal", "equal", "greaterthanequal", "greaterthan")
_RAYCOMP = ("hit", "nohit")
_GROUPTYPE = ("guess", "points", "prims")
_ANIM_OUTPUT = ("pose", "agentclippose", "restpose", "motionclip", "packedmotionclips")
_CHAR_OUTPUT = ("pose", "agentclippose")
_TIMESHIFT = ("byframe", "bytime")
_ROOTMODE = ("updateprimxform", "applytojoint", "ignore")


# ── 1. crowdsource::3.0 (SOP) — A source: a crowd point/agent-spawn stream ────────────────────────
@endpoint("crowd_source")
def crowd_source(params):
    """Crowd Source (crowdsource::3.0) — generates the crowd point stream (formation grid or scatter)
    that seeds a crowd sim: each point spawns an agent with an initial state / clip / heading. Cooks
    bare (0 inputs); optional `points` (input 0) = geometry to scatter agents on. SECURITY: state /
    clip / group NAME strings only; no file/code surface."""
    if params.get("points"):
        n = child_after(params["points"], "crowdsource::3.0", params.get("name"))
    else:
        g = _fresh_geo(params.get("name"))
        n = g.createNode("crowdsource::3.0", "crowd_source")
        g.setDisplayFlag(False)
    if "layout" in params:
        _menu_set(n, "layout", str(params["layout"]), _LAYOUT)
    if "layout_orient" in params:
        _menu_set(n, "layoutorient", str(params["layout_orient"]), _LAYOUTORIENT)
    if "size_x" in params:
        _try_set(n, "sizex", clamp(float(params["size_x"]), 0.0, 1e9))
    if "size_y" in params:
        _try_set(n, "sizey", clamp(float(params["size_y"]), 0.0, 1e9))
    if "formation_rows" in params:
        _try_set(n, "formationrows", int(clamp(int(params["formation_rows"]), 0, 1000000)))
    if "formation_cols" in params:
        _try_set(n, "formationcols", int(clamp(int(params["formation_cols"]), 0, 1000000)))
    if "formation_spacing" in params:
        _try_set(n, "formationspacing", clamp(float(params["formation_spacing"]), 0.0, 1e6))
    if "density_per_area" in params:
        _try_set(n, "densityperarea", bool(params["density_per_area"]))
    if "scatter_agents" in params:
        _try_set(n, "scatteragent", int(clamp(int(params["scatter_agents"]), 0, 10000000)))
    if "scatter_agents_per_area" in params:
        _try_set(n, "scatteragentperarea", clamp(float(params["scatter_agents_per_area"]), 0.0, 1e9))
    if "scatter_seed" in params:
        _try_set(n, "scatterseed", clamp(float(params["scatter_seed"]), 0.0, 1e9))
    if "max_iterations" in params:
        _try_set(n, "maxiterations", int(clamp(int(params["max_iterations"]), 0, 1000000)))
    if "pscale_multiplier" in params:
        _try_set(n, "pscalemultiplier", clamp(float(params["pscale_multiplier"]), 0.0, 1e6))
    if "state" in params:
        _try_set(n, "state", str(params["state"]))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 0.0, 1e6))
    if "set_heading_from_velocity" in params:
        _try_set(n, "setheadingfromvelocity", bool(params["set_heading_from_velocity"]))
    if "create_group" in params:
        _try_set(n, "creategroup", bool(params["create_group"]))
    if "agent_group" in params:
        _try_set(n, "agentgroup", str(params["agent_group"]))
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "clip_time" in params:
        _try_set(n, "cliptime", clamp(float(params["clip_time"]), -1e9, 1e9))
    if "randomize_agent" in params:
        _try_set(n, "randomizeagent", bool(params["randomize_agent"]))
    if "randomize_agent_method" in params:
        _menu_set(n, "randomizeagentmethod", str(params["randomize_agent_method"]), _RANDMETHOD)
    if "randomize_agent_seed" in params:
        _try_set(n, "randomizeagentseed", clamp(float(params["randomize_agent_seed"]), 0.0, 1e9))
    if "viewport_lod" in params:
        _menu_set(n, "viewportlod", str(params["viewport_lod"]), _VIEWPORTLOD)
    if "show_id" in params:
        _try_set(n, "showid", bool(params["show_id"]))
    return _cooked(n)


# ── 2. crowdmotionpathtrigger (SOP) — B chain, in0 = crowd motion-path geometry ───────────────────
@endpoint("crowd_motion_path_trigger")
def crowd_motion_path_trigger(params):
    """Crowd Motion Path Trigger (crowdmotionpathtrigger) — evaluates a trigger condition (time /
    bounds / object-distance / raycast / neighbor-distance / clip) along crowd motion paths and writes
    a named trigger used by transitions. `motion_paths` (input 0) = the crowd motion-path geometry;
    optional `collider` (input 1) = a bounding/collider object. SECURITY: trigger/attribute/clip NAME
    strings only; the `initbounds` Button is never pressed; no file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpathtrigger", params.get("name"))
    if params.get("collider"):
        bridge_input(n, str(params["collider"]), index=1)
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "trigger_name" in params:
        _try_set(n, "triggername", str(params["trigger_name"]))
    if "trigger_type" in params:
        _menu_set(n, "triggertype", str(params["trigger_type"]), _TRIGGERTYPE)
    if "time_dep_collider" in params:
        _try_set(n, "timedepcollider", bool(params["time_dep_collider"]))
    if "random_start" in params:
        _try_set(n, "randomstart", bool(params["random_start"]))
    if "random_start_offset" in params:
        _try_set(n, "randomstartoffset", clamp(float(params["random_start_offset"]), -1e6, 1e6))
    if "random_start_seed" in params:
        _try_set(n, "randomstartseed", clamp(float(params["random_start_seed"]), 0.0, 1e9))
    if "match_parent_agent" in params:
        _try_set(n, "matchparentagent", bool(params["match_parent_agent"]))
    if "trigger_frame" in params:
        _try_set(n, "triggerframe", clamp(float(params["trigger_frame"]), -1e9, 1e9))
    if "bound_type" in params:
        _menu_set(n, "boundtype", str(params["bound_type"]), _BOUNDTYPE)
    if "bound_size" in params:
        _try_set_tuple(n, ("boundsizex", "boundsizey", "boundsizez"), params["bound_size"])
    if "bound_translate" in params:
        _try_set_tuple(n, ("boundtx", "boundty", "boundtz"), params["bound_translate"])
    if "enable_fov_angle" in params:
        _try_set(n, "enablefovangle", bool(params["enable_fov_angle"]))
    if "fov_angle" in params:
        _try_set(n, "fovangle", clamp(float(params["fov_angle"]), 0.0, 360.0))
    if "time_threshold" in params:
        _try_set(n, "timethreshold", clamp(float(params["time_threshold"]), -1e9, 1e9))
    if "dir_mode" in params:
        _menu_set(n, "dirmode", str(params["dir_mode"]), _DIRMODE)
    if "dir_attrib" in params:
        _try_set(n, "dirattrib", str(params["dir_attrib"]))
    if "distance_obj_type" in params:
        _menu_set(n, "distanceobjtype", str(params["distance_obj_type"]), _DISTOBJTYPE)
    if "distance" in params:
        _try_set(n, "distance", clamp(float(params["distance"]), 0.0, 1e12))
    if "bound_comparison" in params:
        _menu_set(n, "boundcomparison", str(params["bound_comparison"]), _BOUNDCOMP)
    if "clip_name" in params:
        _try_set(n, "enableclipname", True)
        _try_set(n, "clipname", str(params["clip_name"]))
    if "clip_time" in params:
        _try_set(n, "enablecliptime", True)
        _try_set(n, "cliptime", clamp(float(params["clip_time"]), -1e9, 1e9))
    if "clip_time_units" in params:
        _menu_set(n, "cliptimeunits", str(params["clip_time_units"]), _CLIPTIMEUNITS)
    if "time_comparison" in params:
        _menu_set(n, "timecomparison", str(params["time_comparison"]), _TIMECOMP)
    if "num_loops" in params:
        _try_set(n, "enablenumloops", True)
        _try_set(n, "numloops", int(clamp(int(params["num_loops"]), 0, 1000000)))
    if "ray_distance" in params:
        _try_set(n, "raydist", clamp(float(params["ray_distance"]), 0.0, 1e12))
    if "ray_comparison" in params:
        _menu_set(n, "raycomparison", str(params["ray_comparison"]), _RAYCOMP)
    return _cooked(n)


# ── 3. kinefx::agentanimationunpack (SOP) — B chain, in0 = Agents ─────────────────────────────────
@endpoint("agent_animation_unpack")
def agent_animation_unpack(params):
    """Agent Animation Unpack (kinefx::agentanimationunpack) — unpacks an agent's animation into a
    KineFX skeleton `output`: pose / agent-clip pose / rest pose / motion clip / packed motion clips.
    `agents` (input 0) = agent primitives. SECURITY: clip/attribute/group NAME strings only; no file/
    code surface."""
    n = child_after(params["agents"], "kinefx::agentanimationunpack", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "output" in params:
        _menu_set(n, "output", str(params["output"]), _ANIM_OUTPUT)
    if "agent_clip_name" in params:
        _try_set(n, "agentclipname", str(params["agent_clip_name"]))
    if "agent_clip_pattern" in params:
        _try_set(n, "agentclippattern", str(params["agent_clip_pattern"]))
    if "set_new_clip_name" in params:
        _try_set(n, "setnewclipname", bool(params["set_new_clip_name"]))
    if "new_clip_name" in params:
        _try_set(n, "clipname", str(params["new_clip_name"]))
    if "transfer_attributes" in params:
        _try_set(n, "transferattributes", str(params["transfer_attributes"]))
    if "transfer_groups" in params:
        _try_set(n, "transfergroups", str(params["transfer_groups"]))
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e9, 1e9))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e9, 1e9))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e6))
    return _cooked(n)


# ── 4. kinefx::agentcharacterunpack (SOP) — B chain, in0 = Agents, 3 outputs ──────────────────────
@endpoint("agent_character_unpack")
def agent_character_unpack(params):
    """Agent Character Unpack (kinefx::agentcharacterunpack) — unpacks an agent into its component
    geometry: output 0 = skin shapes, output 1 = skeleton, output 2 = capture pose. `agents`
    (input 0) = agent primitives. `shape_filter` picks which current-layer shapes to extract (out 0 is
    empty if the agent carries no skin layer). SECURITY: shape/clip/attribute NAME strings only; no
    file/code surface."""
    n = child_after(params["agents"], "kinefx::agentcharacterunpack", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "shape_filter" in params:
        _try_set(n, "shapefilter", str(params["shape_filter"]))
    if "shape_attrib" in params:
        _try_set(n, "shapeattrib", str(params["shape_attrib"]))
    if "geo_transfer_attributes" in params:
        _try_set(n, "geo_transferattributes", str(params["geo_transfer_attributes"]))
    if "geo_transfer_groups" in params:
        _try_set(n, "geo_transfergroups", str(params["geo_transfer_groups"]))
    if "output" in params:
        _menu_set(n, "output", str(params["output"]), _CHAR_OUTPUT)
    if "agent_clip_name" in params:
        _try_set(n, "agentclipname", str(params["agent_clip_name"]))
    if "set_new_clip_name" in params:
        _try_set(n, "setnewclipname", bool(params["set_new_clip_name"]))
    if "new_clip_name" in params:
        _try_set(n, "clipname", str(params["new_clip_name"]))
    if "skel_transfer_attributes" in params:
        _try_set(n, "skel_transferattributes", str(params["skel_transfer_attributes"]))
    if "skel_transfer_groups" in params:
        _try_set(n, "skel_transfergroups", str(params["skel_transfer_groups"]))
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e9, 1e9))
    return _cooked_multi(n)


# ── 5. kinefx::agentfromrig (SOP) — B chain, in0 = a KineFX rig/skeleton ──────────────────────────
@endpoint("agent_from_rig")
def agent_from_rig(params):
    """Agent From Rig (kinefx::agentfromrig) — converts a KineFX rig/skeleton into a single Agent
    primitive (rest pose, no clips). `rig` (input 0) = the skeleton. SECURITY: agent-name / rest-pose-
    attribute / group / attribute NAME strings only; no file/code surface."""
    n = child_after(params["rig"], "kinefx::agentfromrig", params.get("name"))
    if "create_agent_name" in params:
        _try_set(n, "createagentname", bool(params["create_agent_name"]))
    if "agent_name" in params:
        _try_set(n, "createagentname", True)
        _try_set(n, "agentname", str(params["agent_name"]))
    if "use_rest_frame" in params:
        _try_set(n, "userestframe", bool(params["use_rest_frame"]))
    if "rest_frame" in params:
        _try_set(n, "userestframe", True)
        _try_set(n, "restframe", int(clamp(int(params["rest_frame"]), -100000, 100000)))
    if "use_rest_pose_attrib" in params:
        _try_set(n, "userestposeattrib", bool(params["use_rest_pose_attrib"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "userestposeattrib", True)
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "create_locomotion_joint" in params:
        _try_set(n, "createlocomotionjoint", bool(params["create_locomotion_joint"]))
    if "point_groups" in params:
        _try_set(n, "pointgroups", str(params["point_groups"]))
    if "point_attribs" in params:
        _try_set(n, "pointattribs", str(params["point_attribs"]))
    return _cooked(n)


# ── 6. kinefx::agentposefromrig (SOP) — B chain, in0 = Agents, in1 = rig pose (2 inputs) ──────────
@endpoint("agent_pose_from_rig")
def agent_pose_from_rig(params):
    """Agent Pose From Rig (kinefx::agentposefromrig) — drives an agent's pose from a KineFX rig/
    skeleton pose (both inputs REQUIRED). `agents` (input 0) = agent primitives; `rig` (input 1) = the
    skeleton whose joint transforms pose the agent. Optional `channels` limits which joints/channels
    are transferred. SECURITY: joint / group / channel NAME strings only; no file/code surface."""
    n = child_after(params["agents"], "kinefx::agentposefromrig", params.get("name"))
    bridge_input(n, str(params["rig"]), index=1)
    if params.get("rest_input"):
        bridge_input(n, str(params["rest_input"]), index=2)
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "joints" in params:
        _try_set(n, "joints", str(params["joints"]))
    if "root_transform_mode" in params:
        _menu_set(n, "roottransformmode", str(params["root_transform_mode"]), _ROOTMODE)
    if "root_joint" in params:
        _try_set(n, "rootjoint", str(params["root_joint"]))
    if "channels" in params:
        _try_set(n, "channels", str(params["channels"]))
    return _cooked(n)

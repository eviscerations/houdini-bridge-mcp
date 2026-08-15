"""Crowd / Agent — data-only handlers (Crowd domain). Params verified against
live H21.0.671; every endpoint proven with a headless cook over the
reusable agent fixture (build_test_agent = a skeleton -> motionclip ->
agentfromrig -> agentclip agent carrying one clip).

Two archetypes are wrapped here (the Crowd/Agent domain spans SOP and DOP):
  SOP nodes (cook to geometry over the agent fixture):
    agent_source     kinefx `agent` SOP — the agent-primitive source/importer (input=scene/disk/fbx/
                     usd). Creates agents; optional input0 = points to spawn on.
    agent_look_at    agentlookat::3.0 — input0 = Agents, input1 = target points.
  DOP crowd nodes (BUILT inside a dopnet, WIRE-ONLY like sim.py `rbd_force`; they only run inside a
  crowdsolver, so the handler creates + configures + returns the node — it never runs the crowd sim):
    agent_terrain_adaptation, agent_terrain_projection, agent_look_at_apply, agent_clip_layer,
    agent_arcing_clip_layer, crowd_fuzzy_logic, crowd_object, crowd_state.

SECURITY (data-only): the only file surface in this lane is the `agent` SOP's fbx/usd/cache paths —
each routed through confined_path(). NO code/callback/VEX/expression parm is ever set or exposed:
  * agent_clip_layer  leaves localweightexpression / vex_cwdpath / localexpression_1 at default;
  * crowd_state       leaves localexpression at default;
  * crowd_fuzzy_logic leaves thresholdtest (a comparison expression) at default.
All other string params surfaced are attribute / group / clip / object NAMES, never paths or code.
The DOP crowd SOLVERS (crowdsolver, ragdollsolver, ...) are excluded from this slice (see waveplan
solvers_defer) and are NOT wrapped here.
"""

import hou
from houdini_executor.server import clamp, child_after, confined_path, resolve_node, endpoint
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
    g = n.geometry()
    res = {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}
    # Honest-return coverage: a crowd-source recipe verify reads how many agents were seeded. Count the
    # packed-agent prims (guarded, so it is simply omitted for a non-agent geo in this family).
    try:
        agent_t = hou.primType.Agent
        res["agentprims"] = sum(1 for p in g.iterPrims() if p.type() == agent_t)
    except Exception:  # noqa: BLE001 - readback convenience must never break a good cook
        pass
    return res


def _dop_build(params, ntype):
    """Create `ntype` inside a dopnet and return (node, dopnet, holder_geo_or_None).

    Resolution mirrors sim.py `rbd_force`:
      * params["dopnet"]  -> an existing dopnet path; create the node inside it.
      * else              -> a fresh /obj geo (`name`) holding a new dopnet.
    Optional params["input"] wires an upstream DOP node (a path inside the same dopnet) into input 0
    — the crowd-stream source (e.g. a crowdsource / another agent microsolver). The node is BUILT,
    never cooked-as-sim here; the caller wires it into their crowdsolver network."""
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


# ── ordered-menu token tuples (position == the stored index for the index-fallback path) ─────────
_AGENT_INPUT = ("scene", "disk", "fbx", "usd")
_LA_TARGETTYPE = ("position", "object", "points", "agents")
_LA_LIMITMODE = ("none", "attrib", "scale")
_TERRAINSOURCE = ("sop", "dopdata", "first", "second", "third", "fourth")
_INITGEO_SOURCE = ("sop", "first", "second", "third", "fourth")
_BLENDMODE = ("interpolate", "additive")
_PROJ_MODE = ("direction", "attrib")
_SAMPLING = ("particle", "foot")
_OUTPUTTYPE = ("0", "1")
_RBD_RAGDOLL = ("active", "static", "ignore")
_CLIP_ASSIGN = ("none", "single", "random")


# ── 1. agent (SOP) — the agent-primitive source/importer ─────────────────────────────────────────
@endpoint("agent_source")
def agent_source(params):
    """Crowd Agent (agent SOP) — creates/imports agent primitives. `input` picks the definition
    source: scene (an /obj bone subnet named by `obj_subnet`), disk (agent cache under `cache_dir`),
    fbx (`fbx_file`) or usd (`usd_file`). Optional `points` (input 0) = points to spawn agents on.
    SECURITY: fbx_file / usd_file / cache_dir are confined to the working dir; the disk-mode
    sub-cache filename parms are left at default (not exposed). No code/callback surface."""
    if params.get("points"):
        n = child_after(params["points"], "agent", params.get("name"))
    else:
        g = _fresh_geo(params.get("name"))
        n = g.createNode("agent", "agent")
        g.setDisplayFlag(False)
    if "input" in params:
        _menu_set(n, "input", str(params["input"]), _AGENT_INPUT)
    if "agent_name" in params:
        _try_set(n, "agentname", str(params["agent_name"]))
    if "current_layer" in params:
        _try_set(n, "currentlayer", str(params["current_layer"]))
    if "collision_layer" in params:
        _try_set(n, "collisionlayer", str(params["collision_layer"]))
    if "current_clip" in params:
        _try_set(n, "currentclip", str(params["current_clip"]))
    if "clip_offset" in params:
        _try_set(n, "clipoffset", float(params["clip_offset"]))
    if "apply_locomotion" in params:
        _try_set(n, "applylocomotion", bool(params["apply_locomotion"]))
    if "keep_primitives" in params:
        _try_set(n, "keepprimitives", bool(params["keep_primitives"]))
    if "obj_subnet" in params:
        _try_set(n, "objsubnet", str(params["obj_subnet"]))
    if "fbx_file" in params:
        _try_set(n, "fbxfile", confined_path(str(params["fbx_file"])))
    if "usd_file" in params:
        _try_set(n, "usdfile", confined_path(str(params["usd_file"])))
    if "cache_dir" in params:
        _try_set(n, "cachedir", confined_path(str(params["cache_dir"])))
    if "generate_collision" in params:
        _try_set(n, "generatecollision", bool(params["generate_collision"]))
    if "collision_name" in params:
        _try_set(n, "collisionname", str(params["collision_name"]))
    return _cooked(n)


# ── 2. agentlookat::3.0 (SOP) — B chain, input0=agents, input1=target points ─────────────────────
@endpoint("agent_look_at")
def agent_look_at(params):
    """Crowd Agent Look At (agentlookat::3.0) — orients agent head/eye joints toward a target.
    `agents` (input 0) = the agent primitives; optional `targets` (input 1) = target points (used
    when target_type=points). SECURITY: attribute/group/object-name strings only; no file/code
    surface."""
    n = child_after(params["agents"], "agentlookat::3.0", params.get("name"))
    if params.get("targets"):
        n.setInput(1, resolve_node(str(params["targets"])))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "target_type" in params:
        _menu_set(n, "targettype", str(params["target_type"]), _LA_TARGETTYPE)
    if "position" in params:
        _try_set_tuple(n, "position", params["position"])
    if "object_path" in params:
        _try_set(n, "objectpath", str(params["object_path"]))
    if "search_group" in params:
        _try_set(n, "searchgroup", str(params["search_group"]))
    if "max_search_points" in params:
        _try_set(n, "maxsearchpts", int(clamp(int(params["max_search_points"]), 0, 100000)))
    if "max_neighbors" in params:
        _try_set(n, "maxneighbors", int(clamp(int(params["max_neighbors"]), 0, 100000)))
    if "horizontal_limit_angle" in params:
        _try_set(n, "hozlimitangle", clamp(float(params["horizontal_limit_angle"]), 0.0, 360.0))
    if "horizontal_limit_mode" in params:
        _menu_set(n, "hozlimitmode", str(params["horizontal_limit_mode"]), _LA_LIMITMODE)
    if "vertical_limit_angle" in params:
        _try_set(n, "vertlimitangle", clamp(float(params["vertical_limit_angle"]), 0.0, 360.0))
    if "vertical_limit_mode" in params:
        _menu_set(n, "vertlimitmode", str(params["vertical_limit_mode"]), _LA_LIMITMODE)
    if "distance_range" in params:
        _try_set(n, "distancerange", clamp(float(params["distance_range"]), 0.0, 1e9))
    if "set_num_joints" in params:
        _try_set(n, "setnumjoints", bool(params["set_num_joints"]))
    if "num_joints" in params:
        _try_set(n, "numjoints", int(clamp(int(params["num_joints"]), 0, 1000)))
    if "head_turn_stiffness" in params:
        _try_set(n, "headturnstiffness", clamp(float(params["head_turn_stiffness"]), 0.0, 1e6))
    if "eye_turn_stiffness" in params:
        _try_set(n, "eyeturnstiffness", clamp(float(params["eye_turn_stiffness"]), 0.0, 1e6))
    if "output_target_position" in params:
        _try_set(n, "outputtargetposattrib", bool(params["output_target_position"]))
    return _cooked(n)


# ── 3. agentterrainadaptation::3.0 (DOP) — foot-locking / hip-adjust terrain adaptation ──────────
@endpoint("agent_terrain_adaptation")
def agent_terrain_adaptation(params):
    """Crowd Agent Terrain Adaptation (agentterrainadaptation::3.0) — DOP crowd microsolver that
    foot-locks and hip-adjusts agents to a terrain. BUILT inside a dopnet (WIRE-ONLY; runs inside a
    crowdsolver). `dopnet` = existing dopnet, else a fresh geo `name`; optional `input` = upstream
    DOP crowd stream. SECURITY: attribute/group/object-name strings only; no file/code surface."""
    n, dn, holder = _dop_build(params, "agentterrainadaptation::3.0")
    if "bind_group" in params:
        _try_set(n, "bindgroup", str(params["bind_group"]))
    if "terrain_source" in params:
        _menu_set(n, "terrainsource", str(params["terrain_source"]), _TERRAINSOURCE)
    if "terrain_object" in params:
        _try_set(n, "terrainobject", str(params["terrain_object"]))
    if "terrain_sop_path" in params:
        _try_set(n, "terrainsoppath", str(params["terrain_sop_path"]))
    if "terrain_group" in params:
        _try_set(n, "terraingroup", str(params["terrain_group"]))
    if "enable_foot_locking" in params:
        _try_set(n, "enablefootlocking", bool(params["enable_foot_locking"]))
    if "adjust_hips" in params:
        _try_set(n, "adjusthips", bool(params["adjust_hips"]))
    if "hip_offset" in params:
        _try_set(n, "hipoffset", clamp(float(params["hip_offset"]), -1e6, 1e6))
    if "enable_knee_damping" in params:
        _try_set(n, "enablekneedamping", bool(params["enable_knee_damping"]))
    if "enable_terrain_adaptation" in params:
        _try_set(n, "enableterrainadaptation", bool(params["enable_terrain_adaptation"]))
    if "enable_leaning" in params:
        _try_set(n, "enableleaning", bool(params["enable_leaning"]))
    if "min_tilt" in params:
        _try_set(n, "mintilt", clamp(float(params["min_tilt"]), -180.0, 180.0))
    if "max_tilt" in params:
        _try_set(n, "maxtilt", clamp(float(params["max_tilt"]), -180.0, 180.0))
    return _dop_result(n, dn, holder)


# ── 4. agentterrainprojection (DOP) — project agents onto terrain ────────────────────────────────
@endpoint("agent_terrain_projection")
def agent_terrain_projection(params):
    """Crowd Agent Terrain Projection (agentterrainprojection) — DOP crowd microsolver projecting
    agent particles/feet onto a terrain surface. BUILT inside a dopnet (WIRE-ONLY). `dopnet`/`name`/
    `input` as in agent_terrain_adaptation. SECURITY: attribute/group-name strings only; no file/code
    surface."""
    n, dn, holder = _dop_build(params, "agentterrainprojection")
    if "use_group" in params:
        _try_set(n, "usegroup", bool(params["use_group"]))
    if "part_group" in params:
        _try_set(n, "partgroup", str(params["part_group"]))
    if "terrain_source" in params:
        _menu_set(n, "terrainsource", str(params["terrain_source"]), _TERRAINSOURCE)
    if "terrain_group" in params:
        _try_set(n, "terraingroup", str(params["terrain_group"]))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _PROJ_MODE)
    if "projection_dir" in params:
        _try_set_tuple(n, "projectiondir", params["projection_dir"])
    if "sampling_method" in params:
        _menu_set(n, "samplingmethod", str(params["sampling_method"]), _SAMPLING)
    if "project_samples" in params:
        _try_set(n, "projectsamples", bool(params["project_samples"]))
    if "offset" in params:
        _try_set(n, "offset", clamp(float(params["offset"]), -1e6, 1e6))
    if "project_forces" in params:
        _try_set(n, "projectforces", bool(params["project_forces"]))
    return _dop_result(n, dn, holder)


# ── 5. agentlookatapply::3.0 (DOP) — apply look-at targeting inside the sim ───────────────────────
@endpoint("agent_look_at_apply")
def agent_look_at_apply(params):
    """Crowd Agent Look At Apply (agentlookatapply::3.0) — DOP crowd microsolver applying head/eye
    look-at targeting to agents each sim step. BUILT inside a dopnet (WIRE-ONLY). SECURITY:
    attribute/group-name strings only; no file/code surface."""
    n, dn, holder = _dop_build(params, "agentlookatapply::3.0")
    if "use_group" in params:
        _try_set(n, "usegroup", bool(params["use_group"]))
    if "part_group" in params:
        _try_set(n, "partgroup", str(params["part_group"]))
    if "min_target_score" in params:
        _try_set(n, "mintargetscore", clamp(float(params["min_target_score"]), -1e6, 1e6))
    if "min_target_score_mode" in params:
        _menu_set(n, "mintargetscoremode", str(params["min_target_score_mode"]), _LA_LIMITMODE)
    if "set_num_joints" in params:
        _try_set(n, "setnumjoints", bool(params["set_num_joints"]))
    if "num_joints" in params:
        _try_set(n, "numjoints", int(clamp(int(params["num_joints"]), 0, 1000)))
    if "head_turn_stiffness" in params:
        _try_set(n, "headturnstiffness", clamp(float(params["head_turn_stiffness"]), 0.0, 1e6))
    if "eye_turn_stiffness" in params:
        _try_set(n, "eyeturnstiffness", clamp(float(params["eye_turn_stiffness"]), 0.0, 1e6))
    if "output_target_position" in params:
        _try_set(n, "outputtargetposattrib", bool(params["output_target_position"]))
    if "output_target_score" in params:
        _try_set(n, "outputtargetscoreattrib", bool(params["output_target_score"]))
    return _dop_result(n, dn, holder)


# ── 6. agentcliplayer (DOP) — layer/blend animation clips onto agents ────────────────────────────
@endpoint("agent_clip_layer")
def agent_clip_layer(params):
    """Crowd Agent Clip Layer (agentcliplayer) — DOP crowd microsolver that layers/blends animation
    clips onto agents. BUILT inside a dopnet (WIRE-ONLY). The first clip-layer's data params are
    exposed. SECURITY: the localweightexpression / vex_cwdpath / localexpression_1 VEX/expression
    parms are LEFT AT DEFAULT (never exposed); string params surfaced are clip/group NAMES only."""
    n, dn, holder = _dop_build(params, "agentcliplayer")
    if "use_group" in params:
        _try_set(n, "usegroup", bool(params["use_group"]))
    if "part_group" in params:
        _try_set(n, "partgroup", str(params["part_group"]))
    if "blend_mode" in params:
        _menu_set(n, "blendmode", str(params["blend_mode"]), _BLENDMODE)
    if "clip_name" in params:
        _try_set(n, "clipname_1", str(params["clip_name"]))
    if "weight" in params:
        _try_set(n, "weight_1", clamp(float(params["weight"]), 0.0, 1.0))
    if "blend_ratio" in params:
        _try_set(n, "blendratio_1", clamp(float(params["blend_ratio"]), 0.0, 1.0))
    if "blend_in_frames" in params:
        _try_set(n, "blendinframes_1", int(clamp(int(params["blend_in_frames"]), 0, 100000)))
    if "blend_out_frames" in params:
        _try_set(n, "blendoutframes_1", int(clamp(int(params["blend_out_frames"]), 0, 100000)))
    if "clip_speed_multiplier" in params:
        _try_set(n, "clipspeedmultiplier_1", clamp(float(params["clip_speed_multiplier"]), 0.0, 1e4))
    if "randomize_clips" in params:
        _try_set(n, "randomizeclips_1", bool(params["randomize_clips"]))
    if "random_clip_seed" in params:
        _try_set(n, "randomclipseed_1", clamp(float(params["random_clip_seed"]), 0.0, 1e9))
    return _dop_result(n, dn, holder)


# ── 7. agentarcingcliplayer (DOP) — arcing (turn) clip layer ─────────────────────────────────────
@endpoint("agent_arcing_clip_layer")
def agent_arcing_clip_layer(params):
    """Crowd Agent Arcing Clip Layer (agentarcingcliplayer) — DOP crowd microsolver that layers an
    arcing/turning clip onto agents. BUILT inside a dopnet (WIRE-ONLY). SECURITY: group-name strings
    only; no file/code surface."""
    n, dn, holder = _dop_build(params, "agentarcingcliplayer")
    if "use_group" in params:
        _try_set(n, "usegroup", bool(params["use_group"]))
    if "part_group" in params:
        _try_set(n, "partgroup", str(params["part_group"]))
    return _dop_result(n, dn, holder)


# ── 8. crowdfuzzylogic (DOP) — fuzzy-logic trigger combiner ──────────────────────────────────────
@endpoint("crowd_fuzzy_logic")
def crowd_fuzzy_logic(params):
    """Crowd Fuzzy Logic (crowdfuzzylogic) — DOP node combining trigger inputs via fuzzy logic and
    writing a trigger attribute. BUILT inside a dopnet (WIRE-ONLY; up to 10 trigger inputs wired by
    the crowd network). SECURITY: the `thresholdtest` comparison-expression parm is LEFT AT DEFAULT
    (never exposed); only the output type / threshold / trigger-attribute NAME are surfaced."""
    n, dn, holder = _dop_build(params, "crowdfuzzylogic")
    if "output_type" in params:
        _menu_set(n, "outputtype", str(params["output_type"]), _OUTPUTTYPE)
    if "boolean_threshold" in params:
        _try_set(n, "booleanthreshold", clamp(float(params["boolean_threshold"]), 0.0, 1.0))
    if "trigger_attrib" in params:
        _try_set(n, "triggerattrib", str(params["trigger_attrib"]))
    return _dop_result(n, dn, holder)


# ── 9. crowdobject (DOP) — the crowd simulation object ───────────────────────────────────────────
@endpoint("crowd_object")
def crowd_object(params):
    """Crowd Object (crowdobject) — the DOP object that holds the agent crowd in a crowd sim. BUILT
    inside a dopnet (WIRE-ONLY; no inputs). Exposes the object/geometry-source/bullet-collision data
    controls. NOTE: bullet_geoconvexhull is a Toggle (a convex-hull collision-shape switch), NOT a
    code parm (waveplan code-flag false positive). SECURITY: object/geometry-name strings only; no
    file/code surface."""
    params = dict(params)
    params.pop("input", None)  # crowdobject takes no inputs
    n, dn, holder = _dop_build(params, "crowdobject")
    if "object_name" in params:
        _try_set(n, "object_name", str(params["object_name"]))
    if "active" in params:
        _try_set(n, "active", bool(params["active"]))
    if "enable_ragdoll" in params:
        _try_set(n, "enableragdoll", bool(params["enable_ragdoll"]))
    if "initial_geometry_source" in params:
        _menu_set(n, "initialgeometrysource", str(params["initial_geometry_source"]), _INITGEO_SOURCE)
    if "initial_geometry" in params:
        _try_set(n, "initialgeometry", str(params["initial_geometry"]))
    if "use_transform" in params:
        _try_set(n, "usetransform", bool(params["use_transform"]))
    if "life" in params:
        _try_set(n, "life", clamp(float(params["life"]), 0.0, 1e9))
    if "convex_hull" in params:
        _try_set(n, "bullet_geoconvexhull", bool(params["convex_hull"]))
    if "triangulate" in params:
        _try_set(n, "geo_triangulate", bool(params["triangulate"]))
    if "density" in params:
        _try_set(n, "density", clamp(float(params["density"]), 0.0, 1e9))
    if "bounce" in params:
        _try_set(n, "bounce", clamp(float(params["bounce"]), 0.0, 1e6))
    if "friction" in params:
        _try_set(n, "friction", clamp(float(params["friction"]), 0.0, 1e6))
    if "collision_margin" in params:
        _try_set(n, "bullet_collision_margin", clamp(float(params["collision_margin"]), 0.0, 1e6))
    return _dop_result(n, dn, holder)


# ── 10. crowdstate::3.0 (DOP) — a crowd behaviour state ──────────────────────────────────────────
@endpoint("crowd_state")
def crowd_state(params):
    """Crowd State (crowdstate::3.0) — defines a named behaviour state (clip assignment, gait,
    ragdoll mode) in a crowd state machine. BUILT inside a dopnet (WIRE-ONLY; no inputs). SECURITY:
    the `localexpression` VEX parm is LEFT AT DEFAULT (never exposed); string params surfaced are
    state/stream/clip NAMES only."""
    params = dict(params)
    params.pop("input", None)  # crowdstate takes no inputs
    n, dn, holder = _dop_build(params, "crowdstate::3.0")
    if "stream_name" in params:
        _try_set(n, "streamname", str(params["stream_name"]))
    if "state_name" in params:
        _try_set(n, "statename", str(params["state_name"]))
    if "rbd_ragdoll" in params:
        _menu_set(n, "rbdragdoll", str(params["rbd_ragdoll"]), _RBD_RAGDOLL)
    if "clip_assignment" in params:
        _menu_set(n, "clipassignment", str(params["clip_assignment"]), _CLIP_ASSIGN)
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "gait_speed" in params:
        _try_set(n, "gaitspeed", clamp(float(params["gait_speed"]), 0.0, 1e6))
    if "speed_variance" in params:
        _try_set(n, "speedvariance", clamp(float(params["speed_variance"]), 0.0, 1e6))
    if "enable_looping" in params:
        _try_set(n, "enablelooping", bool(params["enable_looping"]))
    if "clip_speed_multiplier" in params:
        _try_set(n, "clipspeedmultiplier", clamp(float(params["clip_speed_multiplier"]), 0.0, 1e4))
    if "apply_locomotion_orient" in params:
        _try_set(n, "applylocomotionorient", bool(params["apply_locomotion_orient"]))
    return _dop_result(n, dn, holder)

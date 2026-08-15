"""Crowd / Agent — data-only handlers (agent unpack + the crowd MOTION-PATH lane). Params
verified against live H21.0.671; every endpoint proven with a headless
cook over the reusable agent fixture (build_test_agent) extended to a crowd: build_test_agent -> crowdsource::3.0 (a 3x3 formation crowd) ->
crowdmotionpath (motion-path geometry). Mirrors the Crowd pilot (crowd_1.py / crowd_2.py / crowd_3.py).

All 16 wrapped nodes are SOP context (they cook to agent / motion-path geometry over the fixture — no
DOP wire-only in this lane). Input semantics per node (from live inputLabels):
  agent_transform_group          in0=Agents
  agent_unpack                   in0=Agents
  agent_vellum_unpack            in0=Agents
  crowd_assign_layers            in0=Agents
  crowd_motion_path              in0=Agents (a crowd) -> Motion Paths (+ child paths)
  crowd_motion_path_apply_relationship  in0=Motion Paths, in1=Agents
  crowd_motion_path_arcing_layer in0=Motion Paths, in1=Agents
  crowd_motion_path_avoid        in0=Motion Paths, in1=Agents, in2=Obstacles (in1/in2 optional)
  crowd_motion_path_edit         in0=Motion Paths, in1=Agents
  crowd_motion_path_edit_core    in0=Motion Paths
  crowd_motion_path_evaluate     in0=Motion Paths, in1=Agents
  crowd_motion_path_evaluate_core in0=Agents, in1=Motion Paths, in2=Clip Properties (in2 optional)
  crowd_motion_path_follow       in0=Motion Paths, in1=Agents, in2=Curves to Follow (in1/in2 optional)
  crowd_motion_path_layer        in0=Motion Paths, in1=Agents
  crowd_motion_path_retime       in0=Motion Paths, in1=Agents (in1 optional)
  crowd_motion_path_transition   in0=Motion Paths, in1=Agents

SECURITY (data-only): this lane exposes NO file parm (the motion-path lane has none) — so no path
surface at all. NO code/callback/VEX/expression parm is ever set or exposed:
  * agent_transform_group leaves the `descriptiveparm` (node-label expression) and the per-instance
    weight Ramp at default (never exposed);
  * every motion-path node's ordered menus are set by token; all string params surfaced are attribute
    / group / layer / clip / transform-group NAMES — never filesystem paths, never code.

SKIPPED here:
  * agentterrainadaptation (SOP, bare) — the base name `agentterrainadaptation` is ALREADY wrapped by
    crowd_1 as `agent_terrain_adaptation` (the DOP `agentterrainadaptation::3.0`); one tool per base
    name (house rule), so the SOP variant is not re-wrapped.
  * crowdmotionpathavoidcore — an INTERNAL implementation "core" node that reads a partitioned
    detail-attribute scaffold (numpartitions / mintime / maxtime / intervallength / interval / …) which
    only its parent HDA (crowdmotionpathavoid, which IS wrapped here and cooks green) sets up; it cannot
    cook green standalone, so it is not wrapped. Its user-facing wrapper covers the functionality.
"""

import hou
from houdini_executor.server import clamp, child_after, resolve_node, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _try_set_tuple


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




def _cooked(n):
    n.cook(force=True)
    g = n.geometry()
    ap = [p for p in g.prims() if p.type() == hou.primType.Agent]
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "agentprims": len(ap)}


def _wire1(n, params, key):
    """Wire the geometry at params[key] into input 1 if present (same-network operand)."""
    if params.get(key):
        n.setInput(1, resolve_node(str(params[key])))


def _wire2(n, params, key):
    if params.get(key):
        n.setInput(2, resolve_node(str(params[key])))


# ── ordered-menu token tuples (position == the stored index for the index-fallback path) ─────────
_GROUPTYPE = ("guess", "points", "prims")
_UNPACK_OUTPUT = ("deformed", "rest", "joints", "skeleton", "motionclips")
_UNPACK_RESTFROM = ("currentlayers", "collisionlayers", "alllayers", "shapelib")
_VELLUM_SELMETHOD = ("group", "agentlayer")
_VELLUM_GROUPTYPE = ("guess", "breakpoints", "edges", "points", "prims")
_VELLUM_SIMSEL = ("layer", "shape")
_ASSIGN_LAYERLIST = ("currentlayers", "collisionlayers")
_ASSIGN_SELECTBY = ("group", "layerpattern", "collisionlayerpattern")
_MP_SOURCEMODE = ("clip", "sim")
_MP_CLIPTIMEUNITS = ("seconds", "phase")
_MP_CLIPSPEEDMODE = ("uniform", "varying", "attrib")
_MP_TURNDIR = ("left", "right")
_MP_STEERING = ("xy", "xyz")
_MP_GOALPOS = ("origendpos", "origpath")
_MP_UPVEC = ("normal", "x", "y", "z")
_MP_TRIGOP = ("none", "or", "and", "xor", "sub")
_MP_NEGATE = ("off", "on")
_MP_BLENDMODE = ("interpolate", "additive")
_MP_BLENDRATIOMODE = ("uniform", "varying", "attrib")


# ── 1. agenttransformgroup (SOP) — B chain, in0=Agents ────────────────────────────────────────────
@endpoint("agent_transform_group")
def agent_transform_group(params):
    """Crowd Agent Transform Group (agenttransformgroup) — defines named transform (joint) groups on
    agents for weighted deformation/blending. `agents` (input 0). Exposes the first transform-group
    definition. SECURITY: the `descriptiveparm` node-label expression and the per-instance weight Ramp
    are LEFT AT DEFAULT (never exposed); all strings are group/joint/transform NAMES; no file/code
    surface."""
    n = child_after(params["agents"], "agenttransformgroup", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "guide_scale" in params:
        _try_set(n, "guidescale", clamp(float(params["guide_scale"]), 0.0, 1e6))
    if "transform_group_name" in params:
        _try_set(n, "enable_0", True)
        _try_set(n, "name_0", str(params["transform_group_name"]))
    if "source_groups" in params:
        _try_set(n, "srcgroups_0", str(params["source_groups"]))
    if "root_transforms" in params:
        _try_set(n, "root_transforms_0", str(params["root_transforms"]))
    if "leaf_transforms" in params:
        _try_set(n, "leaftransforms_0", str(params["leaf_transforms"]))
    if "blend_depth" in params:
        _try_set(n, "blenddepth_0", int(clamp(int(params["blend_depth"]), 0, 100000)))
    if "transforms" in params:
        _try_set(n, "transforms_0", str(params["transforms"]))
    if "channels" in params:
        _try_set(n, "channels_0", str(params["channels"]))
    return _cooked(n)


# ── 2. agentunpack (SOP) — B chain, in0=Agents ────────────────────────────────────────────────────
@endpoint("agent_unpack")
def agent_unpack(params):
    """Crowd Agent Unpack (agentunpack) — unpacks agent primitives into their underlying geometry:
    `output` = deformed | rest | joints | skeleton | motionclips. `agents` (input 0). SECURITY:
    layer/shape/attribute NAME strings only; no file/code surface."""
    n = child_after(params["agents"], "agentunpack", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "output" in params:
        _menu_set(n, "output", str(params["output"]), _UNPACK_OUTPUT)
    if "unique_agent_definitions" in params:
        _try_set(n, "uniqueagentdefinitions", bool(params["unique_agent_definitions"]))
    if "apply_agent_xform" in params:
        _try_set(n, "applyagentxform", bool(params["apply_agent_xform"]))
    if "apply_joint_xforms" in params:
        _try_set(n, "applyjointxforms", bool(params["apply_joint_xforms"]))
    if "unpack_rest_shapes_from" in params:
        _menu_set(n, "unpackrestshapesfrom", str(params["unpack_rest_shapes_from"]), _UNPACK_RESTFROM)
    if "layer_filter" in params:
        _try_set(n, "layerfilter", str(params["layer_filter"]))
    if "shape_filter" in params:
        _try_set(n, "shapefilter", str(params["shape_filter"]))
    if "limit_iterations" in params:
        _try_set(n, "limititerations", bool(params["limit_iterations"]))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 10000)))
    if "clip_names" in params:
        _try_set(n, "clipnames", str(params["clip_names"]))
    if "transfer_attributes" in params:
        _try_set(n, "transferattributes", str(params["transfer_attributes"]))
    if "transfer_groups" in params:
        _try_set(n, "transfergroups", str(params["transfer_groups"]))
    return _cooked(n)


# ── 3. agentvellumunpack (SOP) — B chain, in0=Agents ──────────────────────────────────────────────
@endpoint("agent_vellum_unpack")
def agent_vellum_unpack(params):
    """Crowd Agent Vellum Unpack (agentvellumunpack) — unpacks agents into sim (Vellum) + rest
    geometry for cloth/soft-body crowd setups. `agents` (input 0). SECURITY: layer/shape/attribute
    NAME strings only; no file/code surface."""
    n = child_after(params["agents"], "agentvellumunpack", params.get("name"))
    if "selection_method" in params:
        _menu_set(n, "selectionmethod", str(params["selection_method"]), _VELLUM_SELMETHOD)
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _VELLUM_GROUPTYPE)
    if "layer_filter" in params:
        _try_set(n, "layerfilter", str(params["layer_filter"]))
    if "sim_selection_method" in params:
        _menu_set(n, "simselectionmethod", str(params["sim_selection_method"]), _VELLUM_SIMSEL)
    if "sim_layer_filter" in params:
        _try_set(n, "simlayerfilter", str(params["sim_layer_filter"]))
    if "shape_filter" in params:
        _try_set(n, "shapefilter", str(params["shape_filter"]))
    if "delete_attributes" in params:
        _try_set(n, "deleteattributes", str(params["delete_attributes"]))
    if "transfer_attributes" in params:
        _try_set(n, "transferattributes", str(params["transfer_attributes"]))
    if "transfer_groups" in params:
        _try_set(n, "transfergroups", str(params["transfer_groups"]))
    if "start_frame" in params:
        _try_set(n, "startframe", int(clamp(int(params["start_frame"]), -100000, 100000)))
    if "crowd_start_frame" in params:
        _try_set(n, "crowdstartframe", int(clamp(int(params["crowd_start_frame"]), -100000, 100000)))
    if "use_rest_clip" in params:
        _try_set(n, "userestclip", bool(params["use_rest_clip"]))
    if "rest_clip" in params:
        _try_set(n, "restclip", str(params["rest_clip"]))
    if "rest_clip_time" in params:
        _try_set(n, "restcliptime", clamp(float(params["rest_clip_time"]), -1e6, 1e6))
    return _cooked(n)


# ── 4. crowdassignlayers (SOP) — B chain, in0=Agents ──────────────────────────────────────────────
@endpoint("crowd_assign_layers")
def crowd_assign_layers(params):
    """Crowd Assign Layers (crowdassignlayers) — assigns / randomizes current & collision layers on a
    crowd of agents by group / layer-pattern / percentage. `agents` (input 0). Exposes the first
    selection rule's first layer entry. SECURITY: layer/group NAME strings only; no file/code surface."""
    n = child_after(params["agents"], "crowdassignlayers", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "layer_list" in params:
        _menu_set(n, "layerlist", str(params["layer_list"]), _ASSIGN_LAYERLIST)
    if "remove_layers" in params:
        _try_set(n, "removelayers", bool(params["remove_layers"]))
    if "remove_layers_pattern" in params:
        _try_set(n, "removelayerspattern", str(params["remove_layers_pattern"]))
    if "select_by" in params:
        _try_set(n, "enable1", True)
        _menu_set(n, "selectby1", str(params["select_by"]), _ASSIGN_SELECTBY)
    if "select_group" in params:
        _try_set(n, "group1", str(params["select_group"]))
    if "select_layer_pattern" in params:
        _try_set(n, "selectlayerpattern1", str(params["select_layer_pattern"]))
    if "enable_percentage" in params:
        _try_set(n, "enablepercentage1", bool(params["enable_percentage"]))
    if "percentage" in params:
        _try_set(n, "percentage1", clamp(float(params["percentage"]), 0.0, 100.0))
    if "seed" in params:
        _try_set(n, "seed1", clamp(float(params["seed"]), 0.0, 1e9))
    if "layer_pattern" in params:
        _try_set(n, "layerpattern1_1", str(params["layer_pattern"]))
    if "layer_weight" in params:
        _try_set(n, "layerweight1_1", clamp(float(params["layer_weight"]), 0.0, 1e6))
    return _cooked(n)


# ── 5. crowdmotionpath (SOP) — B chain, in0=Agents (a crowd) ──────────────────────────────────────
@endpoint("crowd_motion_path")
def crowd_motion_path(params):
    """Crowd Motion Path (crowdmotionpath) — generates editable motion-path curves for a crowd by
    evaluating each agent's assigned clips (or a cached sim) over a frame range. `agents` (input 0) =
    a crowd (points carrying agent prims). Exposes the transfer sets + the first clip-assignment rule.
    SECURITY: clip/attribute/group NAME strings only; no file/code surface."""
    n = child_after(params["agents"], "crowdmotionpath", params.get("name"))
    if "source_mode" in params:
        _menu_set(n, "sourcemode", str(params["source_mode"]), _MP_SOURCEMODE)
    if "frame_range" in params:
        _try_set_tuple(n, "framerange", params["frame_range"])
    if "transfer_attribs" in params:
        _try_set(n, "transferattribs", str(params["transfer_attribs"]))
    if "transfer_groups" in params:
        _try_set(n, "transfergroups", str(params["transfer_groups"]))
    if "hide_child_paths" in params:
        _try_set(n, "hidechildpaths", bool(params["hide_child_paths"]))
    if "assign_group" in params:
        _try_set(n, "group1", str(params["assign_group"]))
    if "assign_group_type" in params:
        _menu_set(n, "grouptype1", str(params["assign_group_type"]), _GROUPTYPE)
    if "set_initial_clip_time" in params:
        _try_set(n, "setinitialcliptime1", bool(params["set_initial_clip_time"]))
    if "initial_clip_time" in params:
        _try_set(n, "initialcliptime1", clamp(float(params["initial_clip_time"]), -1e6, 1e6))
    if "clip_time_units" in params:
        _menu_set(n, "cliptimeunits1", str(params["clip_time_units"]), _MP_CLIPTIMEUNITS)
    if "clip_speed" in params:
        _try_set(n, "clipspeed1", clamp(float(params["clip_speed"]), 0.0, 1e4))
    if "clip_speed_mode" in params:
        _menu_set(n, "clipspeedmode1", str(params["clip_speed_mode"]), _MP_CLIPSPEEDMODE)
    if "clip_pattern" in params:
        _try_set(n, "clippattern1_1", str(params["clip_pattern"]))
    if "clip_weight" in params:
        _try_set(n, "clipweight1_1", clamp(float(params["clip_weight"]), 0.0, 1e6))
    return _cooked(n)


# ── 6. crowdmotionpathapplyrel (SOP) — B chain, in0=Motion Paths, in1=Agents ──────────────────────
@endpoint("crowd_motion_path_apply_relationship")
def crowd_motion_path_apply_relationship(params):
    """Crowd Motion Path Apply Relationship (crowdmotionpathapplyrel) — applies agent parent/child
    relationships onto motion paths. `motion_paths` (input 0); `agents` (input 1). SECURITY: group
    NAME string only; no file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpathapplyrel", params.get("name"))
    _wire1(n, params, "agents")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    return _cooked(n)


# ── 7. crowdmotionpatharcinglayer (SOP) — B chain, in0=Motion Paths, in1=Agents ───────────────────
@endpoint("crowd_motion_path_arcing_layer")
def crowd_motion_path_arcing_layer(params):
    """Crowd Motion Path Arcing Layer (crowdmotionpatharcinglayer) — layers turn (arcing) clips onto a
    motion path based on turn rate. `motion_paths` (input 0); `agents` (input 1). Exposes smoothing +
    the first arcing-clip entry. SECURITY: clip/attribute NAME strings only; no file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpatharcinglayer", params.get("name"))
    _wire1(n, params, "agents")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "smoothing_strength" in params:
        _try_set(n, "smoothingstrength", clamp(float(params["smoothing_strength"]), 0.0, 1e6))
    if "filter_quality" in params:
        _try_set(n, "filterquality", int(clamp(int(params["filter_quality"]), 0, 1000)))
    if "output_turn_rate_attrib" in params:
        _try_set(n, "outputturnrateattrib", bool(params["output_turn_rate_attrib"]))
    if "turn_rate_attrib" in params:
        _try_set(n, "turnrateattrib", str(params["turn_rate_attrib"]))
    if "base_clip_name" in params:
        _try_set(n, "baseclipname1", str(params["base_clip_name"]))
    if "arcing_clip_name" in params:
        _try_set(n, "clipname1_1", str(params["arcing_clip_name"]))
    if "turn_direction" in params:
        _menu_set(n, "turndirection1_1", str(params["turn_direction"]), _MP_TURNDIR)
    if "turn_radius" in params:
        _try_set(n, "radius1_1", clamp(float(params["turn_radius"]), 0.0, 1e6))
    return _cooked(n)


# ── 8. crowdmotionpathavoid (SOP) — B chain, in0=Motion Paths, in1=Agents, in2=Obstacles ──────────
@endpoint("crowd_motion_path_avoid")
def crowd_motion_path_avoid(params):
    """Crowd Motion Path Avoid (crowdmotionpathavoid) — steers motion paths to avoid collisions,
    neighbors and obstacles. `motion_paths` (input 0); optional `agents` (input 1); optional
    `obstacles` (input 2). Cost-exponential controls (iterations / substeps / fov samples) are clamped.
    SECURITY: group NAME strings only; no file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpathavoid", params.get("name"))
    _wire1(n, params, "agents")
    _wire2(n, params, "obstacles")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "enable_avoidance" in params:
        _try_set(n, "enableavoidance", bool(params["enable_avoidance"]))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 200)))
    if "max_collision_time" in params:
        _try_set(n, "maxcollisiontime", clamp(float(params["max_collision_time"]), 0.0, 1e6))
    if "enable_neighbors" in params:
        _try_set(n, "enableneighbors", bool(params["enable_neighbors"]))
    if "neighbor_distance" in params:
        _try_set(n, "neighbordistance", clamp(float(params["neighbor_distance"]), 0.0, 1e6))
    if "max_neighbors" in params:
        _try_set(n, "maxneighbors", int(clamp(int(params["max_neighbors"]), 0, 10000)))
    if "enable_obstacles" in params:
        _try_set(n, "enableobstacles", bool(params["enable_obstacles"]))
    if "obstacle_distance" in params:
        _try_set(n, "obstacledistance", clamp(float(params["obstacle_distance"]), 0.0, 1e6))
    if "obstacle_padding" in params:
        _try_set(n, "obstaclepadding", clamp(float(params["obstacle_padding"]), 0.0, 1e6))
    if "steering_mode" in params:
        _menu_set(n, "steeringmode", str(params["steering_mode"]), _MP_STEERING)
    if "max_turn_rate" in params:
        _try_set(n, "maxturnrate", clamp(float(params["max_turn_rate"]), 0.0, 1e6))
    if "goal_pos" in params:
        _menu_set(n, "goalpos", str(params["goal_pos"]), _MP_GOALPOS)
    if "goal_pos_weight" in params:
        _try_set(n, "goalposweight", clamp(float(params["goal_pos_weight"]), 0.0, 1e6))
    if "substeps" in params:
        _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    return _cooked(n)


# ── 9. crowdmotionpathedit (SOP) — B chain, in0=Motion Paths, in1=Agents ──────────────────────────
@endpoint("crowd_motion_path_edit")
def crowd_motion_path_edit(params):
    """Crowd Motion Path Edit (crowdmotionpathedit) — pin-weight / scale-adjustment editing of motion
    paths (the non-interactive data controls). `motion_paths` (input 0); `agents` (input 1). SECURITY:
    the interactive selection state (`activepoints` / handle transforms) and the `reset` Button and
    cached-geo Data parm are LEFT AT DEFAULT (never pressed / exposed); numeric weights only; no
    file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpathedit", params.get("name"))
    _wire1(n, params, "agents")
    if "default_pin_weight" in params:
        _try_set(n, "defaultpinweight", clamp(float(params["default_pin_weight"]), 0.0, 1e6))
    if "start_pin_weight" in params:
        _try_set(n, "startpinweight", clamp(float(params["start_pin_weight"]), 0.0, 1e6))
    if "enable_scale_adjustment" in params:
        _try_set(n, "enablescaleadjustment", bool(params["enable_scale_adjustment"]))
    if "scale_adjustment_weight" in params:
        _try_set(n, "scaleadjustmentweight", clamp(float(params["scale_adjustment_weight"]), 0.0, 1e6))
    return _cooked(n)


# ── 10. crowdmotionpatheditcore (SOP) — B chain, in0=Motion Paths ─────────────────────────────────
@endpoint("crowd_motion_path_edit_core")
def crowd_motion_path_edit_core(params):
    """Crowd Motion Path Edit Core (crowdmotionpatheditcore) — the data core of the motion-path edit:
    applies pin-weight / scale-adjustment attributes to motion paths. `motion_paths` (input 0).
    SECURITY: attribute/group NAME strings only; no file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpatheditcore", params.get("name"))
    if "rest_attrib" in params:
        _try_set(n, "restattrib", str(params["rest_attrib"]))
    if "pin_group" in params:
        _try_set(n, "pingroup", str(params["pin_group"]))
    if "pin_weight_attrib" in params:
        _try_set(n, "pinweightattrib", str(params["pin_weight_attrib"]))
    if "pin_scale_weight_attrib" in params:
        _try_set(n, "pinscaleweightattrib", str(params["pin_scale_weight_attrib"]))
    if "scale_adjustment" in params:
        _try_set(n, "scaleadjustment", bool(params["scale_adjustment"]))
    if "scale_adjustment_weight" in params:
        _try_set(n, "scaleadjustmentweight", clamp(float(params["scale_adjustment_weight"]), 0.0, 1e6))
    if "add_edited_path_group" in params:
        _try_set(n, "addeditedpathgroup", bool(params["add_edited_path_group"]))
    if "edited_path_group" in params:
        _try_set(n, "editedpathgroup", str(params["edited_path_group"]))
    return _cooked(n)


# ── 11. crowdmotionpathevaluate (SOP) — B chain, in0=Motion Paths, in1=Agents ─────────────────────
@endpoint("crowd_motion_path_evaluate")
def crowd_motion_path_evaluate(params):
    """Crowd Motion Path Evaluate (crowdmotionpathevaluate) — samples a crowd's motion paths at a given
    `frame`, producing the posed crowd points. `motion_paths` (input 0); `agents` (input 1). SECURITY:
    no string/file/code surface — a single frame control."""
    n = child_after(params["motion_paths"], "crowdmotionpathevaluate", params.get("name"))
    _wire1(n, params, "agents")
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    return _cooked(n)


# ── 12. crowdmotionpathevaluatecore (SOP) — B chain, in0=Agents, in1=Motion Paths, in2=Clip Props ─
@endpoint("crowd_motion_path_evaluate_core")
def crowd_motion_path_evaluate_core(params):
    """Crowd Motion Path Evaluate Core (crowdmotionpathevaluatecore) — the data core of the motion-path
    evaluate: poses agents from motion paths at a given `time`. NOTE the input order — `agents`
    (input 0); `motion_paths` (input 1); optional `clip_properties` (input 2). SECURITY: no string/
    file/code surface — a single time control."""
    n = child_after(params["agents"], "crowdmotionpathevaluatecore", params.get("name"))
    _wire1(n, params, "motion_paths")
    _wire2(n, params, "clip_properties")
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    return _cooked(n)


# ── 13. crowdmotionpathfollow (SOP) — B chain, in0=Motion Paths, in1=Agents, in2=Curves ───────────
@endpoint("crowd_motion_path_follow")
def crowd_motion_path_follow(params):
    """Crowd Motion Path Follow (crowdmotionpathfollow) — deforms motion paths to follow guide curves.
    `motion_paths` (input 0); optional `agents` (input 1); optional `curves` (input 2) = curves to
    follow. SECURITY: attribute/group NAME strings only; no file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpathfollow", params.get("name"))
    _wire1(n, params, "agents")
    _wire2(n, params, "curves")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "curve_group" in params:
        _try_set(n, "curvegroup", str(params["curve_group"]))
    if "match_by_attrib" in params:
        _try_set(n, "matchbyattrib", bool(params["match_by_attrib"]))
    if "agent_attrib" in params:
        _try_set(n, "agentattrib", str(params["agent_attrib"]))
    if "use_curve_attrib" in params:
        _try_set(n, "usecurveattrib", bool(params["use_curve_attrib"]))
    if "curve_attrib" in params:
        _try_set(n, "curveattrib", str(params["curve_attrib"]))
    if "up_vector_type" in params:
        _menu_set(n, "upvectortype", str(params["up_vector_type"]), _MP_UPVEC)
    if "curve_lod" in params:
        _try_set(n, "curvelod", clamp(float(params["curve_lod"]), 0.0, 1e6))
    if "distance_variance" in params:
        _try_set(n, "distancevariance", clamp(float(params["distance_variance"]), 0.0, 1e6))
    if "smoothing_radius" in params:
        _try_set(n, "smoothingradius", clamp(float(params["smoothing_radius"]), 0.0, 1e6))
    if "max_search_points" in params:
        _try_set(n, "maxsearchpoints", int(clamp(int(params["max_search_points"]), 0, 100000)))
    return _cooked(n)


# ── 14. crowdmotionpathlayer (SOP) — B chain, in0=Motion Paths, in1=Agents ────────────────────────
@endpoint("crowd_motion_path_layer")
def crowd_motion_path_layer(params):
    """Crowd Motion Path Layer (crowdmotionpathlayer) — layers an animation clip onto a motion path
    when triggered (via trigger groups). `motion_paths` (input 0); `agents` (input 1). Exposes the
    trigger / blend / clip data controls. SECURITY: clip/group/attribute NAME strings only; no
    file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpathlayer", params.get("name"))
    _wire1(n, params, "agents")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "trigger_group" in params:
        _try_set(n, "triggergroup", str(params["trigger_group"]))
    if "random_start" in params:
        _try_set(n, "randomstart", bool(params["random_start"]))
    if "random_start_offset" in params:
        _try_set(n, "randomstartoffset", clamp(float(params["random_start_offset"]), -1e6, 1e6))
    if "set_num_loops" in params:
        _try_set(n, "setnumloops", bool(params["set_num_loops"]))
    if "num_loops" in params:
        _try_set(n, "numloops", int(clamp(int(params["num_loops"]), 0, 100000)))
    if "blend_in_frames" in params:
        _try_set(n, "blendinframes", int(clamp(int(params["blend_in_frames"]), 0, 100000)))
    if "blend_out_frames" in params:
        _try_set(n, "blendoutframes", int(clamp(int(params["blend_out_frames"]), 0, 100000)))
    if "blend_mode" in params:
        _menu_set(n, "blendmode", str(params["blend_mode"]), _MP_BLENDMODE)
    if "blend_ratio" in params:
        _try_set(n, "blendratio", clamp(float(params["blend_ratio"]), 0.0, 1.0))
    if "transform_group" in params:
        _try_set(n, "transformgroup", str(params["transform_group"]))
    if "randomize_clips" in params:
        _try_set(n, "randomizeclips", bool(params["randomize_clips"]))
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "clip_time_units" in params:
        _menu_set(n, "cliptimeunits", str(params["clip_time_units"]), _MP_CLIPTIMEUNITS)
    if "clip_speed" in params:
        _try_set(n, "setclipspeed", True)
        _try_set(n, "clipspeed", clamp(float(params["clip_speed"]), 0.0, 1e4))
    if "clip_pattern" in params:
        _try_set(n, "clippattern_1", str(params["clip_pattern"]))
    if "clip_weight" in params:
        _try_set(n, "clipweight_1", clamp(float(params["clip_weight"]), 0.0, 1e6))
    return _cooked(n)


# ── 15. crowdmotionpathretime (SOP) — B chain, in0=Motion Paths, in1=Agents (opt) ─────────────────
@endpoint("crowd_motion_path_retime")
def crowd_motion_path_retime(params):
    """Crowd Motion Path Retime (crowdmotionpathretime) — retimes / clips a motion path's frame range
    and playback speed. `motion_paths` (input 0); optional `agents` (input 1). SECURITY: group NAME
    string + numeric controls only; no file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpathretime", params.get("name"))
    _wire1(n, params, "agents")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "start_frame" in params:
        _try_set(n, "setstartframe", True)
        _try_set(n, "startframe", clamp(float(params["start_frame"]), -1e6, 1e6))
    if "end_frame" in params:
        _try_set(n, "setendframe", True)
        _try_set(n, "endframe", clamp(float(params["end_frame"]), -1e6, 1e6))
    if "set_playback" in params:
        _try_set(n, "setplayback", bool(params["set_playback"]))
    if "playback_start" in params:
        _try_set(n, "playbackstart", clamp(float(params["playback_start"]), -1e6, 1e6))
    if "speed_factor" in params:
        _try_set(n, "speedfactor", clamp(float(params["speed_factor"]), 0.0, 1e4))
    return _cooked(n)


# ── 16. crowdmotionpathtransition (SOP) — B chain, in0=Motion Paths, in1=Agents ───────────────────
@endpoint("crowd_motion_path_transition")
def crowd_motion_path_transition(params):
    """Crowd Motion Path Transition (crowdmotionpathtransition) — transitions a motion path from its
    current clip to a new clip when triggered. `motion_paths` (input 0); `agents` (input 1). Exposes
    the trigger / clip / blend data controls. SECURITY: clip/group/state/attribute NAME strings only;
    no file/code surface."""
    n = child_after(params["motion_paths"], "crowdmotionpathtransition", params.get("name"))
    _wire1(n, params, "agents")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "trigger_group" in params:
        _try_set(n, "triggergroup", str(params["trigger_group"]))
    if "random_start" in params:
        _try_set(n, "randomstart", bool(params["random_start"]))
    if "random_start_offset" in params:
        _try_set(n, "randomstartoffset", clamp(float(params["random_start_offset"]), -1e6, 1e6))
    if "randomize_clips" in params:
        _try_set(n, "randomizeclips", bool(params["randomize_clips"]))
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "use_clip_transition_graph" in params:
        _try_set(n, "usecliptransitiongraph", bool(params["use_clip_transition_graph"]))
    if "blend_frames" in params:
        _try_set(n, "blendframes", int(clamp(int(params["blend_frames"]), 0, 100000)))
    if "initial_clip_time" in params:
        _try_set(n, "initialcliptime", clamp(float(params["initial_clip_time"]), -1e6, 1e6))
    if "clip_time_units" in params:
        _menu_set(n, "cliptimeunits", str(params["clip_time_units"]), _MP_CLIPTIMEUNITS)
    if "clip_speed" in params:
        _try_set(n, "clipspeed", clamp(float(params["clip_speed"]), 0.0, 1e4))
    if "clip_speed_mode" in params:
        _menu_set(n, "clipspeedmode", str(params["clip_speed_mode"]), _MP_CLIPSPEEDMODE)
    if "set_state_attrib" in params:
        _try_set(n, "setstateattrib", bool(params["set_state_attrib"]))
    if "state_attrib" in params:
        _try_set(n, "stateattrib", str(params["state_attrib"]))
    if "output_state" in params:
        _try_set(n, "outputstate", str(params["output_state"]))
    if "clip_pattern" in params:
        _try_set(n, "clippattern_1", str(params["clip_pattern"]))
    if "clip_weight" in params:
        _try_set(n, "clipweight_1", clamp(float(params["clip_weight"]), 0.0, 1e6))
    return _cooked(n)

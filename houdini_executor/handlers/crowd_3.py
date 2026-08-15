"""Crowd / Agent — data-only handlers (agent-authoring SOPs). Params verified against live
H21.0.671; every endpoint proven with a headless cook over the
reusable agent fixture (build_test_agent = a skeleton -> motionclip ->
agentfromrig -> agentclip agent carrying one clip). Mirrors the Crowd pilot (crowd_1.py).

All 12 wrapped nodes are SOP agent-authoring nodes (they cook to agent/point geometry over the
fixture — no DOP wire-only in this lane). Input semantics per node (from live inputLabels):
  agent_clip_properties       in0=Agent
  agent_clip_transition_graph in0=Agent, in1=Existing Clip Transition Graph, in2=Clip Properties
  agent_collision_layer       in0=Agents
  agent_configure_joints      in0=Agents
  agent_constraint_network    in0=Agents
  agent_definition_cache      in0=Agent (optional; 0..1) — cache LOADER/writer, WRITE never triggered
  agent_edit                  in0=Agents
  agent_layer                 in0=Agents, in1=Shape Geometry, in2=Capture Pose
  agent_metadata              in0=Agents
  agent_prep                  in0=Agents
  agent_proxy                 in0=Points (points carrying agent prims)
  agent_relationship          in0=Agents, in1=Child Agents

SECURITY (data-only):
  * agent_definition_cache — cachedir routed through confined_path(); the per-file sub-path params
    (rig/layers/shapelib/clips/transformgroups/metadata/attributes) are LEFT AT DEFAULT (not exposed);
    the `execute`/`reload` write Buttons are NEVER pressed (returns rendered/exported semantics implied
    by cook-only). loadfromdisk defaults OFF so the node cooks as an agent pass-through.
  * agent_prep — cachedir + clippaths routed through confined_path(); the createchopnet / reloadclips /
    saveclips Buttons are NEVER pressed; choppaths is a node-path string (not code).
  * agent_edit — the localadjustexpression# / localchanneladjustexpression# VEX/expression multiparm
    parms are LEFT AT DEFAULT (never exposed); only data (layer/clip/time) params are surfaced.
  * All other string params surfaced are attribute / group / layer / clip / joint NAMES, never paths
    or code. No Button/code/callback parm is ever pressed or set.

SKIPPED here:
  * agentlookat / agentlookat::2.0 / agentlookat::3.0 — the highest version (agentlookat::3.0) is
    ALREADY wrapped by crowd_1 as `agent_look_at`; wrapping it here would collide. Not re-wrapped.
"""

import hou
from houdini_executor.server import clamp, child_after, confined_path, resolve_node, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────


def _menu_set(node, parm, token, tokens):
    """Set a menu parm by its token. H21 agent menus accept the token string directly (verified live);
    fall back to the ordered-menu index if a string set is rejected."""
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
    n.cook(force=True)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── ordered-menu token tuples (position == the stored index for the index-fallback path) ─────────
_UNITS = ("frames", "samples")
_RANGETYPE = ("inclusive", "exclusive")
_SCALEMODE = ("none", "attrib", "scale")
_NAMEMODE = ("none", "attrib")
_META_TYPE = ("int", "float", "vector2", "vector", "vector4", "string")
_CLIPSOURCE = ("chop", "file")
_VIEWPORTLOD = ("full", "points", "box", "centroid", "hidden")
_CONSTRAINTTYPE = ("position", "rotation", "all")


# ── 1. agentclipproperties (SOP) — B chain, in0=Agent ─────────────────────────────────────────────
@endpoint("agent_clip_properties")
def agent_clip_properties(params):
    """Crowd Agent Clip Properties (agentclipproperties) — authors per-clip metadata (frame range,
    sample units, previewed clip) on an agent's clip catalog. `agents` (input 0) = agent primitives.
    SECURITY: clip-name/attribute strings only; no file/code surface."""
    n = child_after(params["agents"], "agentclipproperties", params.get("name"))
    if "units" in params:
        _menu_set(n, "units", str(params["units"]), _UNITS)
    if "range_type" in params:
        _menu_set(n, "rangetype", str(params["range_type"]), _RANGETYPE)
    if "enable_clip_preview" in params:
        _try_set(n, "enableclippreview", bool(params["enable_clip_preview"]))
    if "clip_preview" in params:
        _try_set(n, "clippreview", str(params["clip_preview"]))
    return _cooked(n)


# ── 2. agentcliptransitiongraph (SOP) — B chain, in0=Agent, in1=graph, in2=clip properties ───────
@endpoint("agent_clip_transition_graph")
def agent_clip_transition_graph(params):
    """Crowd Agent Clip Transition Graph (agentcliptransitiongraph) — computes clip-to-clip transition
    blends for an agent. `agents` (input 0); optional `existing_graph` (input 1) = an existing
    transition graph; optional `clip_properties` (input 2) = clip-properties geometry. SECURITY:
    transform-group / attribute name strings only; no file/code surface."""
    n = child_after(params["agents"], "agentcliptransitiongraph", params.get("name"))
    if params.get("existing_graph"):
        n.setInput(1, resolve_node(str(params["existing_graph"])))
    if params.get("clip_properties"):
        n.setInput(2, resolve_node(str(params["clip_properties"])))
    if "units" in params:
        _menu_set(n, "units", str(params["units"]), _UNITS)
    if "compute_transition_graph" in params:
        _try_set(n, "computetransitiongraph", bool(params["compute_transition_graph"]))
    if "pose_tolerance" in params:
        _try_set(n, "posetolerance", clamp(float(params["pose_tolerance"]), 0.0, 1e6))
    if "blend_frames" in params:
        _try_set(n, "blendframes", int(clamp(int(params["blend_frames"]), 0, 100000)))
    if "transform_group" in params:
        _try_set(n, "transformgroup", str(params["transform_group"]))
    return _cooked(n)


# ── 3. agentcollisionlayer (SOP) — B chain, in0=Agents ────────────────────────────────────────────
@endpoint("agent_collision_layer")
def agent_collision_layer(params):
    """Crowd Agent Collision Layer (agentcollisionlayer) — builds/marks a collision layer on agents
    (used for ragdoll/bullet collision shapes). `agents` (input 0). SECURITY: layer/group name strings
    only; no file/code surface."""
    n = child_after(params["agents"], "agentcollisionlayer", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "layer_name" in params:
        _try_set(n, "layername", str(params["layer_name"]))
    if "source_copy" in params:
        _try_set(n, "sourcecopy", bool(params["source_copy"]))
    if "source_layer" in params:
        _try_set(n, "srclayer", str(params["source_layer"]))
    if "keep_external_ref" in params:
        _try_set(n, "keepexternalref", bool(params["keep_external_ref"]))
    if "set_as_current_layer" in params:
        _try_set(n, "setascurrentlayer", bool(params["set_as_current_layer"]))
    if "set_as_collision_layer" in params:
        _try_set(n, "setascollisionlayer", bool(params["set_as_collision_layer"]))
    if "configure_rbd_attribs" in params:
        _try_set(n, "configurerbdattribs", bool(params["configure_rbd_attribs"]))
    return _cooked(n)


# ── 4. agentconfigurejoints (SOP) — B chain, in0=Agents ───────────────────────────────────────────
@endpoint("agent_configure_joints")
def agent_configure_joints(params):
    """Crowd Agent Configure Joints (agentconfigurejoints) — configures per-joint ragdoll limits and
    guide display on agents. `agents` (input 0). SECURITY: group/clip-name strings only; the
    create-for-collision-layer / reset-limits Buttons are NEVER pressed; no file/code surface."""
    n = child_after(params["agents"], "agentconfigurejoints", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "clip_names" in params:
        _try_set(n, "clip_names", str(params["clip_names"]))
    if "guide_scale" in params:
        _try_set(n, "guide_scale", clamp(float(params["guide_scale"]), 0.0, 1e6))
    return _cooked(n)


# ── 5. agentconstraintnetwork (SOP) — B chain, in0=Agents ─────────────────────────────────────────
@endpoint("agent_constraint_network")
def agent_constraint_network(params):
    """Crowd Agent Constraint Network (agentconstraintnetwork) — builds the ragdoll constraint network
    (softness / ERP / CFM / bias tuning) for agents. `agents` (input 0). SECURITY: numeric tuning +
    group strings only; no file/code surface."""
    n = child_after(params["agents"], "agentconstraintnetwork", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "pin_root_shapes" in params:
        _try_set(n, "pinrootshapes", bool(params["pin_root_shapes"]))
    if "pin_unconfigured_shapes" in params:
        _try_set(n, "pinunconfiguredshapes", bool(params["pin_unconfigured_shapes"]))
    if "seed" in params:
        _try_set(n, "seed", clamp(float(params["seed"]), 0.0, 1e9))
    if "softness" in params:
        _try_set(n, "softness", clamp(float(params["softness"]), 0.0, 1e6))
    if "softness_randomness" in params:
        _try_set(n, "softnessrandomness", clamp(float(params["softness_randomness"]), 0.0, 1e6))
    if "constraint_force_mixing" in params:
        _try_set(n, "constraintforcemixing", clamp(float(params["constraint_force_mixing"]), 0.0, 1e6))
    if "bias_factor" in params:
        _try_set(n, "biasfactor", clamp(float(params["bias_factor"]), 0.0, 1e6))
    if "relaxation_factor" in params:
        _try_set(n, "relaxationfactor", clamp(float(params["relaxation_factor"]), 0.0, 1e6))
    if "position_cfm" in params:
        _try_set(n, "positioncfm", clamp(float(params["position_cfm"]), 0.0, 1e6))
    if "position_erp" in params:
        _try_set(n, "positionerp", clamp(float(params["position_erp"]), 0.0, 1e6))
    return _cooked(n)


# ── 6. agentdefinitioncache (SOP) — A source / cache loader, in0=Agent (0..1) ─────────────────────
@endpoint("agent_definition_cache")
def agent_definition_cache(params):
    """Crowd Agent Definition Cache (agentdefinitioncache) — loads (or, when explicitly executed in
    the UI, writes) a cached agent definition. Optional `agents` (input 0) = agent primitives to
    cache; without it a fresh /obj geo holds the node as a disk loader. SECURITY: cachedir is confined
    to the working dir; the per-file sub-path params are LEFT AT DEFAULT; the `execute`/`reload` write
    Buttons are NEVER pressed (this handler only builds + cooks — it does not write the cache).
    `load_from_disk` defaults OFF so the node cooks as an agent pass-through."""
    if params.get("agents"):
        n = child_after(params["agents"], "agentdefinitioncache", params.get("name"))
    else:
        g = _fresh_geo(params.get("name"))
        n = g.createNode("agentdefinitioncache", "agentdefinitioncache")
        g.setDisplayFlag(False)
    if "load_from_disk" in params:
        _try_set(n, "loadfromdisk", bool(params["load_from_disk"]))
    if "keep_external_ref" in params:
        _try_set(n, "keepexternalref", bool(params["keep_external_ref"]))
    if "rest_frame" in params:
        _try_set(n, "restframe", int(clamp(int(params["rest_frame"]), -100000, 100000)))
    if "agent_name" in params:
        _try_set(n, "agentname", str(params["agent_name"]))
    if "cache_dir" in params:
        _try_set(n, "cachedir", confined_path(str(params["cache_dir"])))
    if "bake_rig" in params:
        _try_set(n, "bakerig", bool(params["bake_rig"]))
    if "bake_layers" in params:
        _try_set(n, "bakelayers", bool(params["bake_layers"]))
    if "bake_shapes" in params:
        _try_set(n, "bakeshapes", bool(params["bake_shapes"]))
    if "bake_clip" in params:
        _try_set(n, "bakeclip", bool(params["bake_clip"]))
    if "bake_transform_groups" in params:
        _try_set(n, "baketransformgroups", bool(params["bake_transform_groups"]))
    if "bake_metadata" in params:
        _try_set(n, "bakemetadata", bool(params["bake_metadata"]))
    if "bake_attributes" in params:
        _try_set(n, "bakeattributes", bool(params["bake_attributes"]))
    if "current_layers" in params:
        _try_set(n, "currentlayers", str(params["current_layers"]))
    if "collision_layers" in params:
        _try_set(n, "collisionlayers", str(params["collision_layers"]))
    if "current_clip" in params:
        _try_set(n, "currentclip", str(params["current_clip"]))
    if "clip_offset" in params:
        _try_set(n, "setclipoffset", True)
        _try_set(n, "clipoffset", clamp(float(params["clip_offset"]), -1e6, 1e6))
    if "apply_locomotion" in params:
        _try_set(n, "applylocomotion", bool(params["apply_locomotion"]))
    res = _cooked(n)
    res["exported"] = False
    return res


# ── 7. agentedit (SOP) — B chain, in0=Agents ──────────────────────────────────────────────────────
@endpoint("agent_edit")
def agent_edit(params):
    """Crowd Agent Edit (agentedit) — overrides an agent's current/collision layer, current clip and
    clip time. `agents` (input 0). SECURITY: the localadjustexpression# / localchanneladjustexpression#
    VEX/expression multiparm parms are LEFT AT DEFAULT (never exposed); only layer/clip/time DATA
    params are surfaced."""
    n = child_after(params["agents"], "agentedit", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "current_layer" in params:
        _try_set(n, "enablecurrentlayer", True)
        _try_set(n, "currentlayer", str(params["current_layer"]))
    if "collision_layer" in params:
        _try_set(n, "enablecollisionlayer", True)
        _try_set(n, "collisionlayer", str(params["collision_layer"]))
    if "current_clip" in params:
        _try_set(n, "enablecurrentclip", True)
        _try_set(n, "currentclip", str(params["current_clip"]))
    if "clip_time" in params:
        _try_set(n, "enablecliptime", True)
        _try_set(n, "cliptime", clamp(float(params["clip_time"]), -1e6, 1e6))
    if "clip_index" in params:
        _try_set(n, "clipindex", int(clamp(int(params["clip_index"]), 0, 100000)))
    return _cooked(n)


# ── 8. agentlayer::2.0 (SOP) — B chain, in0=Agents, in1=shape geo, in2=capture pose ──────────────
@endpoint("agent_layer")
def agent_layer(params):
    """Crowd Agent Layer (agentlayer::2.0) — adds/assigns shape layers to agents and sets the current
    and collision layers. `agents` (input 0); optional `shapes` (input 1) = shape geometry to add;
    optional `capture_pose` (input 2) = capture pose. SECURITY: shape/layer/attribute name strings
    only; no file/code surface."""
    n = child_after(params["agents"], "agentlayer::2.0", params.get("name"))
    if params.get("shapes"):
        n.setInput(1, resolve_node(str(params["shapes"])))
    if params.get("capture_pose"):
        n.setInput(2, resolve_node(str(params["capture_pose"])))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "add_shapes" in params:
        _try_set(n, "addshapes", bool(params["add_shapes"]))
    if "shape_name_attrib" in params:
        _try_set(n, "shapenameattrib", str(params["shape_name_attrib"]))
    if "keep_external_ref" in params:
        _try_set(n, "keepexternalref", bool(params["keep_external_ref"]))
    if "bounds_scale" in params:
        _try_set(n, "boundsscale", clamp(float(params["bounds_scale"]), 0.0, 1e6))
    if "bounds_scale_mode" in params:
        _menu_set(n, "boundsscalemode", str(params["bounds_scale_mode"]), _SCALEMODE)
    if "shape_deformer" in params:
        _try_set(n, "shapedeformer", str(params["shape_deformer"]))
    if "transform_name" in params:
        _try_set(n, "transformname", str(params["transform_name"]))
    if "set_current_layers" in params:
        _try_set(n, "setcurrentlayers", bool(params["set_current_layers"]))
    if "current_layers" in params:
        _try_set(n, "currentlayers", str(params["current_layers"]))
    if "set_collision_layers" in params:
        _try_set(n, "setcollisionlayers", bool(params["set_collision_layers"]))
    if "collision_layers" in params:
        _try_set(n, "collisionlayers", str(params["collision_layers"]))
    if "use_layer_name_attrib" in params:
        _try_set(n, "uselayernameattrib", bool(params["use_layer_name_attrib"]))
    if "layer_name_attrib" in params:
        _try_set(n, "layernameattrib", str(params["layer_name_attrib"]))
    return _cooked(n)


# ── 9. agentmetadata (SOP) — B chain, in0=Agents ──────────────────────────────────────────────────
@endpoint("agent_metadata")
def agent_metadata(params):
    """Crowd Agent Metadata (agentmetadata) — reads/merges/sets typed metadata dictionaries on agents.
    `agents` (input 0). Exposes the preprocess (remove/merge/import) toggles and the first metadata
    entry (key/type/value). SECURITY: key/attribute name strings only; no file/code surface."""
    n = child_after(params["agents"], "agentmetadata", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "remove_keys" in params:
        _try_set(n, "doremovekeys", True)
        _try_set(n, "removekeys", str(params["remove_keys"]))
    if "merge_dicts" in params:
        _try_set(n, "domergedicts", True)
        _try_set(n, "mergedicts", str(params["merge_dicts"]))
    if "import_attribs" in params:
        _try_set(n, "doimportattribs", True)
        _try_set(n, "importattribs", str(params["import_attribs"]))
    if "key" in params:
        _try_set(n, "enable1", True)
        _try_set(n, "key1", str(params["key"]))
    if "value_type" in params:
        _menu_set(n, "type1", str(params["value_type"]), _META_TYPE)
    if "value_string" in params:
        _try_set(n, "vals1", str(params["value_string"]))
    if "value_int" in params:
        _try_set(n, "vali1", int(params["value_int"]))
    if "value_float" in params:
        _try_set(n, "valf1", float(params["value_float"]))
    return _cooked(n)


# ── 10. agentprep::3.0 (SOP) — B chain, in0=Agents ────────────────────────────────────────────────
@endpoint("agent_prep")
def agent_prep(params):
    """Crowd Agent Prep (agentprep::3.0) — prepares agents for crowd sim (rest clip, limb setup, clip
    loading). `agents` (input 0). SECURITY: cachedir + clippaths are confined to the working dir;
    choppaths is a node-path string (not code); the create-chopnet / reload-clips / save-clips Buttons
    are NEVER pressed; group/agent/clip name strings only."""
    n = child_after(params["agents"], "agentprep::3.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "rest_clip" in params:
        _try_set(n, "restclip", str(params["rest_clip"]))
    if "chop_paths" in params:
        _try_set(n, "choppaths", str(params["chop_paths"]))
    if "load_clips" in params:
        _try_set(n, "loadclips", bool(params["load_clips"]))
    if "clip_source" in params:
        _menu_set(n, "clipsource", str(params["clip_source"]), _CLIPSOURCE)
    if "keep_external_ref" in params:
        _try_set(n, "keepexternalref", bool(params["keep_external_ref"]))
    if "agent_name" in params:
        _try_set(n, "agentname", str(params["agent_name"]))
    if "cache_dir" in params:
        _try_set(n, "cachedir", confined_path(str(params["cache_dir"])))
    if "clip_paths" in params:
        _try_set(n, "clippaths", confined_path(str(params["clip_paths"])))
    if "guide_scale" in params:
        _try_set(n, "guidescale", clamp(float(params["guide_scale"]), 0.0, 1e6))
    return _cooked(n)


# ── 11. agentproxy (SOP) — B chain, in0=Points (carrying agent prims) ─────────────────────────────
@endpoint("agent_proxy")
def agent_proxy(params):
    """Crowd Agent Proxy (agentproxy) — sets viewport proxy display (LOD / id / color) for agent
    points, for fast crowd previews. `agents` (input 0) = points carrying agent primitives. SECURITY:
    display-only toggles and enums; no file/code surface."""
    n = child_after(params["agents"], "agentproxy", params.get("name"))
    if "viewport_lod" in params:
        _menu_set(n, "viewportlod", str(params["viewport_lod"]), _VIEWPORTLOD)
    if "show_id" in params:
        _try_set(n, "showid", bool(params["show_id"]))
    if "use_custom_color" in params:
        _try_set(n, "usecustomcolor", bool(params["use_custom_color"]))
    if "custom_color" in params:
        _try_set_tuple(n, "customcolor", params["custom_color"])
    if "random_color" in params:
        _try_set(n, "randomcolor", bool(params["random_color"]))
    return _cooked(n)


# ── 12. agentrelationship (SOP) — B chain, in0=Agents, in1=Child Agents ───────────────────────────
@endpoint("agent_relationship")
def agent_relationship(params):
    """Crowd Agent Relationship (agentrelationship) — parents child agents to a parent agent (optionally
    to a specific joint) with a position/rotation/all constraint. `agents` (input 0) = parent agents;
    optional `child_agents` (input 1) = child agents. SECURITY: group/joint/transform-group name
    strings only; no file/code surface."""
    n = child_after(params["agents"], "agentrelationship", params.get("name"))
    if params.get("child_agents"):
        n.setInput(1, resolve_node(str(params["child_agents"])))
    if "parent_group" in params:
        _try_set(n, "parentgroup", str(params["parent_group"]))
    if "match_parent_scale" in params:
        _try_set(n, "matchparentscale", bool(params["match_parent_scale"]))
    if "use_joint" in params:
        _try_set(n, "usejoint", bool(params["use_joint"]))
    if "parent_joint" in params:
        _try_set(n, "parentjoint", str(params["parent_joint"]))
    if "child_joint" in params:
        _try_set(n, "childjoint", str(params["child_joint"]))
    if "constraint_type" in params:
        _menu_set(n, "constrainttype", str(params["constraint_type"]), _CONSTRAINTTYPE)
    if "apply_transform" in params:
        _try_set(n, "applytransform", bool(params["apply_transform"]))
    if "transform_group" in params:
        _try_set(n, "transformgroup", str(params["transform_group"]))
    return _cooked(n)

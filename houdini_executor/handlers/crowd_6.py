"""Crowd / Agent — data-only handlers (agent data-provider VOP nodes). Params verified against
live H21.0.671; every endpoint proven with a headless cook of an
attribvop container built over the reusable agent fixture (build_test_agent = a skeleton -> motionclip -> agentfromrig -> agentclip agent carrying one clip).
Mirrors the Crowd pilot (crowd_1.py) container-build/WIRE pattern.

Unlike the earlier crowd lanes (SOP + DOP), ALL 12 nodes in this lane are VOP nodes (category Vop, sub_lane
Crowd/Agent): agent-INSPECTION data providers that read agent data inside a Geometry VOP network —
agent transform matrices/names/count, rig hierarchy (children/parent/find), clip weights, layers /
layer names / layer bindings / layer shapes, and transform-space conversion. A VOP node cannot cook to
geometry by itself, so each handler BUILDS the VOP inside a container Geometry VOP network — an
`attribvop` (Attribute VOP) SOP — exactly as crowd_1 builds DOP microsolvers inside a dopnet:
  * `vop_network`  -> an existing attribvop / VOP-network path; the VOP is created inside it and the
                     node is returned WIRE-ONLY (the caller cooks their own network).
  * `agents`       -> a new `attribvop` is built as a SIBLING of the agents SOP, wired after it
                     (child_after — a plain setInput cannot wire across /obj networks), so the
                     data-provider VOP reads the agent geometry; the container is force-cooked here
                     (the green proof) — an unwired data-provider VOP is inert, so it cooks clean.
  * else           -> a fresh /obj geo holds a new inputless `attribvop`, force-cooked to empty geo.

SECURITY (data-only): these are PURE typed data reads — has_code_parm=False verified for every node.
No snippet / VEX / callback parm exists or is exposed. The ONLY file surface is each VOP's `filename`
(the optional agent-definition Geometry File input), routed through confined_path(). Every other param
is agent DATA: a primitive number (prim), a transform index/name, a layer name, a shape-type filter, a
transform space token, or a convert token — never a path or code. The per-node `signature` (VOP
return-type variant) and `shapetype_i` (menu backing int) parms are LEFT AT DEFAULT (not exposed).
"""

import hou
from houdini_executor.server import clamp, child_after, confined_path, resolve_node, endpoint
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────


def _fresh_geo(name):
    return hou.node("/obj").createNode("geo", name or "crowd")


def _vop_build(params, vtype):
    """Create `vtype` (a VOP node) inside a Geometry VOP network and return (vop, container, holder,
    fresh). `fresh` = we built the container (so _vop_result may cook it as the green proof).

    Resolution mirrors crowd_1 `_dop_build`:
      * params["vop_network"] -> an existing attribvop / VOP-network path; create the VOP inside it
        (WIRE-ONLY: fresh=False, the container is NOT cooked here — the caller drives their network).
      * params["agents"]      -> build a new `attribvop` as a SIBLING of the agents SOP wired after it
        (via child_after — a plain setInput cannot wire across /obj networks), so the data-provider
        VOP reads the agent geometry. fresh=True.
      * else                  -> a fresh /obj geo (`name`) holding a new inputless `attribvop`.
        fresh=True (cooks to empty geometry — still a valid green build).
    Common data params (filename -> confined_path, prim) are applied here."""
    holder = None
    fresh = True
    if params.get("vop_network"):
        container = resolve_node(str(params["vop_network"]))
        if not isinstance(container, hou.Node):
            raise ValueError("no such vop_network: %s" % params["vop_network"])
        fresh = False
    elif params.get("agents"):
        container = child_after(str(params["agents"]), "attribvop", params.get("name"))
    else:
        holder = _fresh_geo(params.get("name"))
        container = holder.createNode("attribvop", "agent_vop")
    v = container.createNode(vtype, params.get("node_name"))
    if "agent_file" in params:
        _try_set(v, "filename", confined_path(str(params["agent_file"])))
    if "prim" in params:
        _try_set(v, "prim", int(clamp(int(params["prim"]), 0, 10_000_000)))
    try:
        v.moveToGoodPosition()
        container.layoutChildren()
    except Exception:
        pass
    return v, container, holder, fresh


def _vop_result(v, container, holder, fresh):
    """Return the built VOP + container. A container WE built (fresh=True) is force-cooked here as the
    green proof; a caller-supplied vop_network is returned WIRE-ONLY (not cooked)."""
    res = {"node": v.path(), "container": container.path(),
           "node_type": v.type().name(), "built": True}
    if fresh:
        try:
            container.cook(force=True)
            g = container.geometry()
            res["points"] = len(g.points())
            res["prims"] = len(g.prims())
            res["errors"] = [str(e) for e in container.errors()]
        except Exception as e:
            res["cook_error"] = str(e)
    if holder is not None:
        holder.setDisplayFlag(False)
        try:
            holder.layoutChildren()
        except Exception:
            pass
        res["geo"] = holder.path()
    return res


# ── 1. agenttransforms (VOP) — read agent transform matrices ─────────────────────────────────────
@endpoint("agent_transforms")
def agent_transforms(params):
    """Crowd Agent Transforms (agenttransforms) — data-provider VOP that reads an agent primitive's
    transform matrices. Built inside a Geometry VOP network (attribvop): `agents` (input 0) = agent
    geometry, else `vop_network` = an existing VOP network. `space` selects the transform space
    (e.g. world / local / agentdefinition). SECURITY: `agent_file` (Geometry File) confined; prim /
    space are data only; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agenttransforms")
    if "space" in params:
        _try_set(v, "space", str(params["space"]))
    return _vop_result(v, container, holder, fresh)


# ── 2. agenttransformnames (VOP) — read agent transform (joint) names ────────────────────────────
@endpoint("agent_transform_names")
def agent_transform_names(params):
    """Crowd Agent Transform Names (agenttransformnames) — data-provider VOP that reads the ordered
    transform (joint) names of an agent's rig. Built inside a Geometry VOP network (attribvop):
    `agents` (input 0) or `vop_network`. SECURITY: `agent_file` confined; prim data only; no code
    surface."""
    v, container, holder, fresh = _vop_build(params, "agenttransformnames")
    return _vop_result(v, container, holder, fresh)


# ── 3. agenttransformcount (VOP) — count agent transforms (joints) ───────────────────────────────
@endpoint("agent_transform_count")
def agent_transform_count(params):
    """Crowd Agent Transform Count (agenttransformcount) — data-provider VOP that outputs the number
    of transforms (joints) in an agent's rig. Built inside a Geometry VOP network (attribvop):
    `agents` (input 0) or `vop_network`. SECURITY: `agent_file` confined; prim data only; no code
    surface."""
    v, container, holder, fresh = _vop_build(params, "agenttransformcount")
    return _vop_result(v, container, holder, fresh)


# ── 4. agentrigfind (VOP) — find a transform index by name ───────────────────────────────────────
@endpoint("agent_rig_find")
def agent_rig_find(params):
    """Crowd Agent Rig Find (agentrigfind) — data-provider VOP that returns the transform index of a
    named joint in an agent's rig. Built inside a Geometry VOP network (attribvop): `agents` (input 0)
    or `vop_network`. `transform_name` = the joint name to look up. SECURITY: `agent_file` confined;
    prim / transform_name are data only; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentrigfind")
    if "transform_name" in params:
        _try_set(v, "transformname", str(params["transform_name"]))
    return _vop_result(v, container, holder, fresh)


# ── 5. agentrigchildren (VOP) — child transforms of a joint ──────────────────────────────────────
@endpoint("agent_rig_children")
def agent_rig_children(params):
    """Crowd Agent Rig Children (agentrigchildren) — data-provider VOP that returns the child
    transform indices of a given joint in an agent's rig hierarchy. Built inside a Geometry VOP
    network (attribvop): `agents` (input 0) or `vop_network`. `transform` = the parent joint index.
    SECURITY: `agent_file` confined; prim / transform are data only; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentrigchildren")
    if "transform" in params:
        _try_set(v, "transform", int(clamp(int(params["transform"]), -1, 10_000_000)))
    return _vop_result(v, container, holder, fresh)


# ── 6. agentrigparent (VOP) — parent transform of a joint ────────────────────────────────────────
@endpoint("agent_rig_parent")
def agent_rig_parent(params):
    """Crowd Agent Rig Parent (agentrigparent) — data-provider VOP that returns the parent transform
    index of a given joint in an agent's rig hierarchy. Built inside a Geometry VOP network
    (attribvop): `agents` (input 0) or `vop_network`. `transform` = the child joint index. SECURITY:
    `agent_file` confined; prim / transform are data only; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentrigparent")
    if "transform" in params:
        _try_set(v, "transform", int(clamp(int(params["transform"]), -1, 10_000_000)))
    return _vop_result(v, container, holder, fresh)


# ── 7. agentclipweights (VOP) — per-clip blend weights ───────────────────────────────────────────
@endpoint("agent_clip_weights")
def agent_clip_weights(params):
    """Crowd Agent Clip Weights (agentclipweights) — data-provider VOP that reads the active per-clip
    blend weights of an agent. Built inside a Geometry VOP network (attribvop): `agents` (input 0) or
    `vop_network`. SECURITY: `agent_file` confined; prim data only; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentclipweights")
    return _vop_result(v, container, holder, fresh)


# ── 8. agentlayers (VOP) — layer names of an agent ───────────────────────────────────────────────
@endpoint("agent_layers")
def agent_layers(params):
    """Crowd Agent Layers (agentlayers) — data-provider VOP that reads the list of layer names on an
    agent definition. Built inside a Geometry VOP network (attribvop): `agents` (input 0) or
    `vop_network`. SECURITY: `agent_file` confined; prim data only; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentlayers")
    return _vop_result(v, container, holder, fresh)


# ── 9. agentlayername (VOP) — resolve an agent's current/collision layer name ────────────────────
@endpoint("agent_layer_name")
def agent_layer_name(params):
    """Crowd Agent Layer Name (agentlayername) — data-provider VOP that resolves a layer name for an
    agent (e.g. current / collision layer). Built inside a Geometry VOP network (attribvop): `agents`
    (input 0) or `vop_network`. `layer` = the layer selector/name. SECURITY: `agent_file` confined;
    prim / layer are data only; the `signature` variant parm is left at default; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentlayername")
    if "layer" in params:
        _try_set(v, "layer", str(params["layer"]))
    return _vop_result(v, container, holder, fresh)


# ── 10. agentlayerbindings (VOP) — shape->transform bindings of a layer ──────────────────────────
@endpoint("agent_layer_bindings")
def agent_layer_bindings(params):
    """Crowd Agent Layer Bindings (agentlayerbindings) — data-provider VOP that reads the shape ->
    transform bindings of a named agent layer. Built inside a Geometry VOP network (attribvop):
    `agents` (input 0) or `vop_network`. `layer` = the layer name; `shape_type` = a shape-type filter.
    SECURITY: `agent_file` confined; prim / layer / shape_type are data only; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentlayerbindings")
    if "layer" in params:
        _try_set(v, "layer", str(params["layer"]))
    if "shape_type" in params:
        _try_set(v, "shapetype", str(params["shape_type"]))
    return _vop_result(v, container, holder, fresh)


# ── 11. agentlayershapes (VOP) — shape names of a layer ──────────────────────────────────────────
@endpoint("agent_layer_shapes")
def agent_layer_shapes(params):
    """Crowd Agent Layer Shapes (agentlayershapes) — data-provider VOP that reads the shape names in a
    named agent layer, optionally filtered by shape type. Built inside a Geometry VOP network
    (attribvop): `agents` (input 0) or `vop_network`. `layer` = the layer name; `shape_type` = a
    shape-type filter. SECURITY: `agent_file` confined; prim / layer / shape_type are data only; the
    `signature` / `shapetype_i` variant parms are left at default; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentlayershapes")
    if "layer" in params:
        _try_set(v, "layer", str(params["layer"]))
    if "shape_type" in params:
        _try_set(v, "shapetype", str(params["shape_type"]))
    return _vop_result(v, container, holder, fresh)


# ── 12. agentconverttransforms (VOP) — convert a transforms array between spaces ─────────────────
@endpoint("agent_convert_transforms")
def agent_convert_transforms(params):
    """Crowd Agent Convert Transforms (agentconverttransforms) — data-provider VOP that converts an
    agent's transforms array between spaces (e.g. local <-> world). Built inside a Geometry VOP
    network (attribvop): `agents` (input 0) or `vop_network`. `convert` = the conversion selector.
    SECURITY: `agent_file` confined; prim / convert are data only; no code surface."""
    v, container, holder, fresh = _vop_build(params, "agentconverttransforms")
    if "convert" in params:
        _try_set(v, "convert", str(params["convert"]))
    return _vop_result(v, container, holder, fresh)

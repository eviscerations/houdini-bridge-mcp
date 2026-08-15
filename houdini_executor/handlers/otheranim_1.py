"""other-anim — DOP dynamics constraint & constraint-relationship nodes (data-only).

This module covers the "other-anim" DOP-category constraint family (not the Object-context auto-rig
HDAs): constraint
RELATIONSHIP nodes (glue/hard/no/cone-twist/bullet-soft), the constraint applicators
(constraint / constraint-network-relationship), FEM & cloth & soft-body constraints, and the DOP Motion
data node. Params verified against live H21.0.671; every endpoint
proven with a headless cook inside a fresh /obj/dopnet.

DOP-node cook pattern (establishes the pattern for later DOP-heavy lanes):
  DOP nodes cannot live in a SOP `geo`; they cook inside a `dopnet`. Each endpoint resolves a dopnet
  (either an existing `dopnet` path the caller passes, or a fresh /obj geo `name` holding a dopnet) and
  createNode()s the constraint node INSIDE it via a LITERAL versioned type string (for the type-tag
  allowlist). The node is BUILT + cooked (errors verified empty) but the sim is never stepped — mirrors
  sim.py's "networks are BUILT, never auto-simulated" rule. Optional `input` wires a sibling DOP data
  node to input 0; min inputs is 0 so a bare cook is valid.

SECURITY (data-only): scout + live probe confirm NO file parm and NO code/callback parm on any of these
16 nodes (file_parms=[] / has_code_parm=False). So there is no path to confine and no code parm is ever
set/exposed. Every string param surfaced is a sim-object / point-group / attribute / data NAME (Regular
string), never a path or code. The DOP data-flow control menus (parmop_*/sharedata/activationrules) and
pure guide/visualize toggles are deliberately NOT exposed. gasconvexclipsdf (a gas/fluid microsolver —
false match) and constraintnetworkvisualization (pure visualization) are SKIPPED.
"""

import hou
from houdini_executor.server import clamp, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)


def _dopnet(params, holder="constraints"):
    """Resolve the dopnet these DOP nodes cook inside: an existing `dopnet` path, else a fresh /obj geo
    `name` holding a dopnet. Mirrors sim.py rbd_force/flip_force."""
    if params.get("dopnet"):
        dn = hou.node(str(params["dopnet"]))
        if dn is None or dn.type().name() != "dopnet":
            raise ValueError("`dopnet` must be an existing SOP dopnet: %s" % params.get("dopnet"))
        return dn
    if not params.get("name"):
        raise ValueError("needs `name` (for a fresh /obj holder) or `dopnet` (an existing one)")
    return _fresh_geo(params["name"]).createNode("dopnet", holder)


def _build(params, ntype, holder="constraints"):
    """Create `ntype` inside the resolved dopnet, wiring an optional sibling DOP node to input 0."""
    dn = _dopnet(params, holder)
    n = dn.createNode(ntype)
    if params.get("input"):
        up = hou.node(str(params["input"]))
        if up is None or up.parent().path() != dn.path():
            raise ValueError("`input` must be a DOP node inside the same dopnet: %s" % params.get("input"))
        n.setInput(0, up)
    n.moveToGoodPosition()
    return dn, n


def _result(dn, n):
    n.cook(force=True)
    return {"node": n.path(), "dopnet": dn.path(), "type": n.type().name(),
            "cooked": True, "errors": list(n.errors())}


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_REST_INIT = ("zero", "reference", "absolute")
_MATCH_METHOD = ("orderedpointgroup", "identifierpointattribute")
_CONN_MODEL = ("attractandrepel", "onlyrepel", "onlyattract")


def _common_constraint_parms(n, params):
    """Shared DOP-data controls present on most of these nodes (all optional / probe-safe)."""
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "data_name" in params:
        _try_set(n, "dataname", str(params["data_name"]))
    if "activation" in params:
        _try_set(n, "activation", int(params["activation"]))


# ── 1. glue_constraint (glueconrel) — glue relationship ──────────────────────────────────────────
@endpoint("glue_constraint")
def glue_constraint(params):
    """KineFX Glue Constraint Relationship (glueconrel) — a DOP constraint-relationship data node that
    glues bound objects until an impulse exceeding `strength` breaks the bond, then propagates the break
    through the network. BUILT + cooked inside a dopnet, never auto-simulated. SECURITY: names only; no
    file/code surface."""
    dn, n = _build(params, "glueconrel")
    if "strength" in params:
        _try_set(n, "strength", clamp(float(params["strength"]), 0.0, 1e12))
    if "impulse_halflife" in params:
        _try_set(n, "impulse_halflife", clamp(float(params["impulse_halflife"]), 0.0, 1e6))
    if "propagate_rate" in params:
        _try_set(n, "propagate_rate", clamp(float(params["propagate_rate"]), 0.0, 1.0))
    if "propagation_iterations" in params:
        _try_set(n, "propagationiterations", int(clamp(int(params["propagation_iterations"]), 0, 1000)))
    _common_constraint_parms(n, params)
    return _result(dn, n)


# ── 2. hard_constraint (hardconrel) — hard/pin relationship ──────────────────────────────────────
@endpoint("hard_constraint")
def hard_constraint(params):
    """KineFX Hard Constraint Relationship (hardconrel) — a stiff DOP constraint relationship pinning
    bound objects to a rest length, with optional angular motors and solver stiffness (CFM/ERP). BUILT +
    cooked inside a dopnet. SECURITY: names only; no file/code surface."""
    dn, n = _build(params, "hardconrel")
    if "rest_length" in params:
        _try_set(n, "restlength", clamp(float(params["rest_length"]), 0.0, 1e9))
    if "cfm" in params:
        _try_set(n, "cfm", clamp(float(params["cfm"]), 0.0, 1e6))
    if "erp" in params:
        _try_set(n, "erp", clamp(float(params["erp"]), 0.0, 1.0))
    if "num_angular_motors" in params:
        _try_set(n, "numangularmotors", int(clamp(int(params["num_angular_motors"]), 0, 3)))
    if "target_angular_velocity" in params:
        _try_set(n, "targetw", clamp(float(params["target_angular_velocity"]), -1e6, 1e6))
    if "max_angular_impulse" in params:
        _try_set(n, "maxangularimpulse", clamp(float(params["max_angular_impulse"]), 0.0, 1e12))
    if "num_iterations" in params:
        _try_set(n, "numiterations", int(clamp(int(params["num_iterations"]), 1, 1000)))
    if "disable_collisions" in params:
        _try_set(n, "disablecollisions", bool(params["disable_collisions"]))
    _common_constraint_parms(n, params)
    return _result(dn, n)


# ── 3. no_constraint (noconrel) — null/collision-only relationship ───────────────────────────────
@endpoint("no_constraint")
def no_constraint(params):
    """KineFX No Constraint Relationship (noconrel) — a DOP relationship that establishes bound objects
    as mutual affectors WITHOUT any constraint force (collision-only / relationship placeholder).
    `radius` sizes the guide only. BUILT + cooked inside a dopnet. SECURITY: names only; no file/code."""
    dn, n = _build(params, "noconrel")
    if "radius" in params:
        _try_set(n, "rad", clamp(float(params["radius"]), 0.0, 1e6))
    _common_constraint_parms(n, params)
    return _result(dn, n)


# ── 4. bullet_soft_constraint (bulletsoftconrel) — soft spring relationship ──────────────────────
@endpoint("bullet_soft_constraint")
def bullet_soft_constraint(params):
    """KineFX Bullet Soft Constraint Relationship (bulletsoftconrel) — a springy Bullet constraint
    relationship with linear + optional angular stiffness/damping and optional plasticity (permanent
    deformation past a threshold). BUILT + cooked inside a dopnet. SECURITY: names only; no file/code."""
    dn, n = _build(params, "bulletsoftconrel")
    if "rest_length" in params:
        _try_set(n, "restlength", clamp(float(params["rest_length"]), 0.0, 1e9))
    if "stiffness" in params:
        _try_set(n, "stiffness", clamp(float(params["stiffness"]), 0.0, 1e12))
    if "damping_ratio" in params:
        _try_set(n, "dampingratio", clamp(float(params["damping_ratio"]), 0.0, 1e6))
    if "enable_angular" in params:
        _try_set(n, "enableangular", bool(params["enable_angular"]))
    if "angular_stiffness" in params:
        _try_set(n, "angularstiffness", clamp(float(params["angular_stiffness"]), 0.0, 1e12))
    if "angular_damping_ratio" in params:
        _try_set(n, "angulardampingratio", clamp(float(params["angular_damping_ratio"]), 0.0, 1e6))
    if "enable_plasticity" in params:
        _try_set(n, "enableplasticity", bool(params["enable_plasticity"]))
    if "plastic_rate" in params:
        _try_set(n, "plasticrate", clamp(float(params["plastic_rate"]), 0.0, 1e6))
    if "plastic_threshold" in params:
        _try_set(n, "plasticthreshold", clamp(float(params["plastic_threshold"]), 0.0, 1e9))
    if "plastic_hardening" in params:
        _try_set(n, "plastichardening", clamp(float(params["plastic_hardening"]), 0.0, 1e6))
    if "num_iterations" in params:
        _try_set(n, "numiterations", int(clamp(int(params["num_iterations"]), 1, 1000)))
    if "disable_collisions" in params:
        _try_set(n, "disablecollisions", bool(params["disable_collisions"]))
    _common_constraint_parms(n, params)
    return _result(dn, n)


# ── 5. cone_twist_constraint (conetwistconrel) — angular-limit relationship ──────────────────────
@endpoint("cone_twist_constraint")
def cone_twist_constraint(params):
    """KineFX Cone Twist Constraint Relationship (conetwistconrel) — a Bullet cone-twist joint limiting
    twist/out/up rotation within a cone, with an optional soft limit and an optional motor. BUILT +
    cooked inside a dopnet. SECURITY: names only; no file/code surface."""
    dn, n = _build(params, "conetwistconrel")
    if "enable_soft" in params:
        _try_set(n, "enablesoft", bool(params["enable_soft"]))
    if "max_twist" in params:
        _try_set(n, "max_twist", clamp(float(params["max_twist"]), 0.0, 360.0))
    if "max_out_rotation" in params:
        _try_set(n, "max_out_rotation", clamp(float(params["max_out_rotation"]), 0.0, 360.0))
    if "max_up_rotation" in params:
        _try_set(n, "max_up_rotation", clamp(float(params["max_up_rotation"]), 0.0, 360.0))
    if "softness" in params:
        _try_set(n, "softness", clamp(float(params["softness"]), 0.0, 1.0))
    if "angular_limit_stiffness" in params:
        _try_set(n, "angularlimitstiffness", clamp(float(params["angular_limit_stiffness"]), 0.0, 1e12))
    if "angular_limit_damping_ratio" in params:
        _try_set(n, "angularlimitdampingratio", clamp(float(params["angular_limit_damping_ratio"]), 0.0, 1e6))
    if "cfm" in params:
        _try_set(n, "cfm", clamp(float(params["cfm"]), 0.0, 1e6))
    if "twist_translation_range" in params:
        _try_set(n, "twisttranslationrange", clamp(float(params["twist_translation_range"]), 0.0, 1e6))
    if "out_translation_range" in params:
        _try_set(n, "outtranslationrange", clamp(float(params["out_translation_range"]), 0.0, 1e6))
    if "up_translation_range" in params:
        _try_set(n, "uptranslationrange", clamp(float(params["up_translation_range"]), 0.0, 1e6))
    if "num_iterations" in params:
        _try_set(n, "numiterations", int(clamp(int(params["num_iterations"]), 1, 1000)))
    if "disable_collisions" in params:
        _try_set(n, "disablecollisions", bool(params["disable_collisions"]))
    if "motor_enabled" in params:
        _try_set(n, "motor_enabled", bool(params["motor_enabled"]))
    _common_constraint_parms(n, params)
    return _result(dn, n)


# ── 6. constraint_relationship (conrelationship) — generic relationship (0 inputs, 4 outputs) ────
@endpoint("constraint_relationship")
def constraint_relationship(params):
    """KineFX Constraint Relationship (conrelationship) — the generic relationship data node defining how
    two bound objects relate (type + two-state break / spring parameters). A pure source (0 inputs, 4
    outputs) referenced by a constraint applicator. BUILT + cooked inside a dopnet. SECURITY: numeric
    values only; no file/code surface."""
    dn, n = _build(params, "conrelationship")
    if "relationship_type" in params:
        _try_set(n, "reltype", int(clamp(int(params["relationship_type"]), 0, 8)))
    if "two_state_initial" in params:
        _try_set(n, "twostateinitial", int(clamp(int(params["two_state_initial"]), 0, 1)))
    if "two_state_force" in params:
        _try_set(n, "twostateforce", clamp(float(params["two_state_force"]), 0.0, 1e12))
    if "two_state_min_distance" in params:
        _try_set(n, "twostatemindistance", clamp(float(params["two_state_min_distance"]), 0.0, 1e9))
    if "spring_strength" in params:
        _try_set(n, "springstrength", clamp(float(params["spring_strength"]), 0.0, 1e12))
    if "spring_damping" in params:
        _try_set(n, "springdamping", clamp(float(params["spring_damping"]), 0.0, 1e9))
    if "spring_rest_length" in params:
        _try_set(n, "springrestlength", clamp(float(params["spring_rest_length"]), 0.0, 1e9))
    if "radius" in params:
        _try_set(n, "guiderad", clamp(float(params["radius"]), 0.0, 1e6))
    return _result(dn, n)


# ── 7. apply_constraint (constraint) — applies a relationship to affected/affector objects ───────
@endpoint("apply_constraint")
def apply_constraint(params):
    """KineFX Constraint (constraint) — applies a named constraint relationship between `affected` and
    `affector` sim objects (the DOP node that actually binds a relationship to objects). BUILT + cooked
    inside a dopnet. SECURITY: object/relationship NAMES only; no file/code surface."""
    dn, n = _build(params, "constraint")
    if "affected" in params:
        _try_set(n, "affected", str(params["affected"]))
    if "affectors" in params:
        _try_set(n, "affectors", str(params["affectors"]))
    if "relationship_name" in params:
        _try_set(n, "relname", str(params["relationship_name"]))
    if "unique_relationship_name" in params:
        _try_set(n, "uniquerelname", bool(params["unique_relationship_name"]))
    if "make_mutual" in params:
        _try_set(n, "makemutual", bool(params["make_mutual"]))
    _common_constraint_parms(n, params)
    return _result(dn, n)


# ── 8. constraint_network_relationship (constraintnetworkrelationship) ───────────────────────────
@endpoint("constraint_network_relationship")
def constraint_network_relationship(params):
    """KineFX Constraint Network Relationship (constraintnetworkrelationship) — applies a relationship to
    a constraint NETWORK, optionally matching affected/affector objects by a point attribute. BUILT +
    cooked inside a dopnet. SECURITY: object/attribute NAMES only; no file/code surface."""
    dn, n = _build(params, "constraintnetworkrelationship")
    if "enable_match_by_attrib" in params:
        _try_set(n, "enablematchbyattrib", bool(params["enable_match_by_attrib"]))
    if "match_by_attrib" in params:
        _try_set(n, "matchbyattrib", str(params["match_by_attrib"]))
    if "affected" in params:
        _try_set(n, "affected", str(params["affected"]))
    if "affectors" in params:
        _try_set(n, "affectors", str(params["affectors"]))
    if "relationship_name" in params:
        _try_set(n, "relname", str(params["relationship_name"]))
    if "make_mutual" in params:
        _try_set(n, "makemutual", bool(params["make_mutual"]))
    _common_constraint_parms(n, params)
    return _result(dn, n)


# ── 9. motion_data (motion) — initial-state DOP Motion data ──────────────────────────────────────
@endpoint("motion_data")
def motion_data(params):
    """KineFX Motion (motion) — the DOP Motion data node carrying an object's position / pivot / rotation
    and linear + angular velocity (the initial-state / target motion for an RBD or agent object). BUILT +
    cooked inside a dopnet. SECURITY: numeric values + names only; no file/code surface."""
    dn, n = _build(params, "motion")
    if "position" in params:
        _try_set_tuple(n, "t", params["position"])
    if "pivot" in params:
        _try_set_tuple(n, "p", params["pivot"])
    if "rotation" in params:
        _try_set_tuple(n, "r", params["rotation"])
    if "velocity" in params:
        _try_set_tuple(n, "vel", params["velocity"])
    if "angular_velocity" in params:
        _try_set_tuple(n, "angvel", params["angular_velocity"])
    _common_constraint_parms(n, params)
    return _result(dn, n)


# ── 10. softbody_constraint (sbdconstraint) — soft-body pin/spring constraint ────────────────────
@endpoint("softbody_constraint")
def softbody_constraint(params):
    """KineFX SBD Constraint (sbdconstraint) — a soft-body-dynamics constraint pinning (`type` 0) or
    spring-linking (`type` 1) constrained points of an object to a goal object/points/location, with
    optional force & length limits. BUILT + cooked inside a dopnet. SECURITY: object/point-group NAMES
    only; no file/code surface."""
    dn, n = _build(params, "sbdconstraint")
    if "type" in params:
        _try_set(n, "type", int(clamp(int(params["type"]), 0, 1)))
    if "constrained_object" in params:
        _try_set(n, "group", str(params["constrained_object"]))
    if "constrained_points" in params:
        _try_set(n, "ptgroup", str(params["constrained_points"]))
    if "use_animation" in params:
        _try_set(n, "useanimation", bool(params["use_animation"]))
    if "goal_object" in params:
        _try_set(n, "goalgroup", str(params["goal_object"]))
    if "goal_points" in params:
        _try_set(n, "goalpts", str(params["goal_points"]))
    if "goal_position" in params:
        _try_set_tuple(n, "goalpos", params["goal_position"])
    if "mirror" in params:
        _try_set(n, "mirror", bool(params["mirror"]))
    if "strength" in params:
        _try_set(n, "strength", clamp(float(params["strength"]), 0.0, 1e12))
    if "rest_length" in params:
        _try_set(n, "restlength", clamp(float(params["rest_length"]), 0.0, 1e9))
    if "damping" in params:
        _try_set(n, "damping", clamp(float(params["damping"]), 0.0, 1e9))
    if "limit_force" in params:
        _try_set(n, "limitforce", bool(params["limit_force"]))
    if "max_force" in params:
        _try_set(n, "maxforce", clamp(float(params["max_force"]), 0.0, 1e12))
    if "limit_length" in params:
        _try_set(n, "limitlength", bool(params["limit_length"]))
    if "max_length" in params:
        _try_set(n, "maxlength", clamp(float(params["max_length"]), 0.0, 1e9))
    if "activation" in params:
        _try_set(n, "activation", int(params["activation"]))
    return _result(dn, n)


# ── 11. cloth_stitch_constraint (clothstitchconstraint) ──────────────────────────────────────────
@endpoint("cloth_stitch_constraint")
def cloth_stitch_constraint(params):
    """KineFX Cloth Stitch Constraint (clothstitchconstraint) — stitches constrained points of a cloth
    object to a goal object/points with a given stiffness & damping (`type` 0=stitch to points, 1=to
    object). BUILT + cooked inside a dopnet. SECURITY: object/point NAMES only; no file/code surface."""
    dn, n = _build(params, "clothstitchconstraint")
    if "type" in params:
        _try_set(n, "type", int(clamp(int(params["type"]), 0, 1)))
    if "stiffness" in params:
        _try_set(n, "stiffness", clamp(float(params["stiffness"]), 0.0, 1e12))
    if "damping" in params:
        _try_set(n, "damping", clamp(float(params["damping"]), 0.0, 1e9))
    if "constrained_object" in params:
        _try_set(n, "constrainedobject", str(params["constrained_object"]))
    if "constrained_points" in params:
        _try_set(n, "constrainedpoints", str(params["constrained_points"]))
    if "goal_object" in params:
        _try_set(n, "goalobject", str(params["goal_object"]))
    if "goal_points" in params:
        _try_set(n, "goalpoints", str(params["goal_points"]))
    if "activation" in params:
        _try_set(n, "activation", int(params["activation"]))
    return _result(dn, n)


# ── 12. fem_attach_constraint (femattachconstraint) ──────────────────────────────────────────────
@endpoint("fem_attach_constraint")
def fem_attach_constraint(params):
    """KineFX FEM Attach Constraint (femattachconstraint) — attaches points of a constrained FEM object
    to a goal object at a rest offset, with optional distance-threshold filtering. BUILT + cooked inside
    a dopnet. SECURITY: object/attribute NAMES only; no file/code surface."""
    dn, n = _build(params, "femattachconstraint")
    if "strength" in params:
        _try_set(n, "strength", clamp(float(params["strength"]), 0.0, 1e12))
    if "damping" in params:
        _try_set(n, "damping", clamp(float(params["damping"]), 0.0, 1e9))
    if "constrained_object" in params:
        _try_set(n, "constrainedobject", str(params["constrained_object"]))
    if "goal_object" in params:
        _try_set(n, "goalobject", str(params["goal_object"]))
    if "constrained_points" in params:
        _try_set(n, "constrainedpoints", str(params["constrained_points"]))
    if "use_distance_threshold" in params:
        _try_set(n, "usedistancethreshold", bool(params["use_distance_threshold"]))
    if "distance_threshold" in params:
        _try_set(n, "distancethreshold", clamp(float(params["distance_threshold"]), 0.0, 1e9))
    if "rest_initialization" in params:
        _menu_set(n, "restinitialization", str(params["rest_initialization"]), _REST_INIT)
    if "rest_distance" in params:
        _try_set(n, "restdistance", clamp(float(params["rest_distance"]), 0.0, 1e9))
    if "activation" in params:
        _try_set(n, "activation", int(params["activation"]))
    return _result(dn, n)


# ── 13. fem_fuse_constraint (femfuseconstraint) ──────────────────────────────────────────────────
@endpoint("fem_fuse_constraint")
def fem_fuse_constraint(params):
    """KineFX FEM Fuse Constraint (femfuseconstraint) — fuses matched points of two FEM objects (matched
    by ordered point group or by an identifier attribute) into a shared boundary. BUILT + cooked inside a
    dopnet. SECURITY: object/attribute NAMES only; no file/code surface."""
    dn, n = _build(params, "femfuseconstraint")
    if "type" in params:
        _try_set(n, "type", int(clamp(int(params["type"]), 0, 1)))
    if "strength" in params:
        _try_set(n, "strength", clamp(float(params["strength"]), 0.0, 1e12))
    if "damping" in params:
        _try_set(n, "damping", clamp(float(params["damping"]), 0.0, 1e9))
    if "match_method" in params:
        _menu_set(n, "matchmethod", str(params["match_method"]), _MATCH_METHOD)
    if "constrained_object" in params:
        _try_set(n, "constrainedobject", str(params["constrained_object"]))
    if "constrained_points" in params:
        _try_set(n, "constrainedpoints", str(params["constrained_points"]))
    if "goal_object" in params:
        _try_set(n, "goalobject", str(params["goal_object"]))
    if "goal_points" in params:
        _try_set(n, "goalpoints", str(params["goal_points"]))
    if "activation" in params:
        _try_set(n, "activation", int(params["activation"]))
    return _result(dn, n)


# ── 14. fem_region_constraint (femregionconstraint) ──────────────────────────────────────────────
@endpoint("fem_region_constraint")
def fem_region_constraint(params):
    """KineFX FEM Region Constraint (femregionconstraint) — constrains overlapping tetrahedral regions of
    two FEM objects together, optionally matching parts by an identifier attribute. BUILT + cooked inside
    a dopnet. SECURITY: object/attribute NAMES only; no file/code surface."""
    dn, n = _build(params, "femregionconstraint")
    if "strength" in params:
        _try_set(n, "targetstrength", clamp(float(params["strength"]), 0.0, 1e12))
    if "damping" in params:
        _try_set(n, "targetdamping", clamp(float(params["damping"]), 0.0, 1e9))
    if "constrained_object" in params:
        _try_set(n, "constrainedobject", str(params["constrained_object"]))
    if "goal_object" in params:
        _try_set(n, "goalobject", str(params["goal_object"]))
    if "enable_matching" in params:
        _try_set(n, "enablematching", bool(params["enable_matching"]))
    if "identifier_attribute" in params:
        _try_set(n, "identifierattribute", str(params["identifier_attribute"]))
    if "activation" in params:
        _try_set(n, "activation", int(params["activation"]))
    return _result(dn, n)


# ── 15. fem_slide_constraint (femslideconstraint) ────────────────────────────────────────────────
@endpoint("fem_slide_constraint")
def fem_slide_constraint(params):
    """KineFX FEM Slide Constraint (femslideconstraint) — constrains points of a FEM object to slide
    along the surface of a goal object (connection model: attract/repel), with optional distance-
    threshold filtering. BUILT + cooked inside a dopnet. SECURITY: object/attribute NAMES only; no
    file/code surface."""
    dn, n = _build(params, "femslideconstraint")
    if "strength" in params:
        _try_set(n, "strength", clamp(float(params["strength"]), 0.0, 1e12))
    if "damping" in params:
        _try_set(n, "damping", clamp(float(params["damping"]), 0.0, 1e9))
    if "constrained_object" in params:
        _try_set(n, "constrainedobject", str(params["constrained_object"]))
    if "goal_object" in params:
        _try_set(n, "goalobject", str(params["goal_object"]))
    if "constrained_points" in params:
        _try_set(n, "constrainedpoints", str(params["constrained_points"]))
    if "use_distance_threshold" in params:
        _try_set(n, "usedistancethreshold", bool(params["use_distance_threshold"]))
    if "distance_threshold" in params:
        _try_set(n, "distancethreshold", clamp(float(params["distance_threshold"]), 0.0, 1e9))
    if "connection_model" in params:
        _menu_set(n, "connectionmodel", str(params["connection_model"]), _CONN_MODEL)
    if "rest_initialization" in params:
        _menu_set(n, "restinitialization", str(params["rest_initialization"]), _REST_INIT)
    if "rest_distance" in params:
        _try_set(n, "restdistance", clamp(float(params["rest_distance"]), 0.0, 1e9))
    if "activation" in params:
        _try_set(n, "activation", int(params["activation"]))
    return _result(dn, n)


# ── 16. fem_target_constraint (femtargetconstraint) ──────────────────────────────────────────────
@endpoint("fem_target_constraint")
def fem_target_constraint(params):
    """KineFX FEM Target Constraint (femtargetconstraint) — softly pulls constrained points of a FEM
    object toward their animated target positions with a given stiffness & damping (`type` 0/1). BUILT +
    cooked inside a dopnet. SECURITY: object/point NAMES only; no file/code surface."""
    dn, n = _build(params, "femtargetconstraint")
    if "type" in params:
        _try_set(n, "type", int(clamp(int(params["type"]), 0, 1)))
    if "stiffness" in params:
        _try_set(n, "stiffness", clamp(float(params["stiffness"]), 0.0, 1e12))
    if "damping" in params:
        _try_set(n, "damping", clamp(float(params["damping"]), 0.0, 1e9))
    if "constrained_object" in params:
        _try_set(n, "constrainedobject", str(params["constrained_object"]))
    if "constrained_points" in params:
        _try_set(n, "constrainedpoints", str(params["constrained_points"]))
    if "activation" in params:
        _try_set(n, "activation", int(params["activation"]))
    return _result(dn, n)

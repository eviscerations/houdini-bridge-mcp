"""RBD constraint-lane handlers (Lane E: constraint deepening + destruction art-direction).

Data-only, typed node wrappers — NO exec/wrangle/VEX authoring. Complements the RBD tools in
`sim.py` (rbd_constraints / rbd_constraint_properties / rbd_voronoi / ...). Every node type, parm
name, and menu token below was live-probed on H21.0.671 and each
op is cook-verified. Networks are BUILT and cooked once (a graph/
attribute op — safe), never simulated. Creators wire after the input; params via _try_set/_menu_set
with clamped numerics; absent parms are skipped, never guessed.

Scope (Family 3 / Lane E):
  • set_constraint_field  — the ZERO-VEX constraint control: typed LITERAL assignment of the RBD
    constraint-network prim attributes (constraint_name / next_constraint_name / strength /
    restlength / broken) by group, via a single attribcreate::2.0 (the typed answer to the RBD
    "name/break constraints by attribute" wrangle pattern). constraint_name is ALSO the type-naming
    control (Glue/Hard/Soft or a custom relationship the solver maps).
  • glue_cluster          — gluecluster: chunk-based glue clustering (building collapses in slabs,
    not per-shard) — the single most-used destruction art-direction control (P0).
  • rbd_constraints_from_curves — rbdconstraintsfromcurves: route the constraint network along user
    curves (rebar / cables / custom bond routing), incl. the SOP-reachable HINGE connection type.

Probe verdict on "constraint TYPE deepening": rbdconstraintproperties::2.0 `constrainttype` is
`glue|hard|soft` ONLY (confirmed) and is already deep in sim.py's rbd_constraint_properties. The
mechanical pin/spring/slider/cone-twist types are DOP-only (rbdpinconstraint / rbdspringconstraint /
rbdsliderconstraint / rbdconetwistconstraint + the *conrel relationships) — legacy DOP workflow the
audit rules OUT OF SCOPE. The only SOP-reachable mechanical behaviour is HINGE (connectiontype on the
curve/line builders) — delivered here via rbd_constraints_from_curves. Custom typing beyond the three
built-ins = write constraint_name literally with set_constraint_field.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, resolve_node
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set






def _set_vec(node, parm, value):
    """Set a vector parmTuple from a list/tuple (probe-safe)."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        vals = [float(v) for v in value]
        vals = (vals + [0.0, 0.0, 0.0])[: len(pt)]
        pt.set(tuple(vals))
        return True
    except Exception:
        return False


def _child_after_out(input_path, ntype, name, out_index):
    """Like server.child_after, but wire from a chosen OUTPUT of the source node. RBD constraint
    geometry rides on different outputs per source (connectadjacentpieces = out0, rbdconstraintsfrom*
    = out1), so the caller may point us at either via `output`."""
    src = resolve_node(input_path)
    try:
        if isinstance(src, hou.ObjNode):
            disp = src.displayNode() or src.renderNode()
            if disp is not None:
                src = disp
    except Exception:
        pass
    parent = src.parent()
    n = parent.createNode(ntype, name) if name else parent.createNode(ntype)
    n.setInput(0, src, int(out_index))
    n.moveToGoodPosition()
    return n


def _con_prim_count(node):
    """Constraint-prim count on output 0 (probe-safe)."""
    try:
        geo = node.geometry()
        return len(geo.prims()) if geo is not None else 0
    except Exception:
        return 0


# ── set_constraint_field — typed LITERAL constraint-attribute assignment ───────
# attribcreate::2.0 multiparm (live-probed): grouptype MENU ['guess','vertices','edges','points',
# 'prims'] (prims=4); per-instance name#/class#/type#/size#/writevalues#/value#v(len-4 float)/string#.
# class# MENU ['detail','primitive','point','vertex'] (primitive=1). type# MENU ['float','int',
# 'vector','index',...] where 'index' (label "String", idx 3) is the STRING type. Scalar value rides
# on value#v1; string value on string#. Cook-verified: constraint_name/strength/broken read back.
_CLASS_PRIMITIVE = 1
_TYPE_FLOAT = 0
_TYPE_INT = 1
_TYPE_STRING = 3
# field -> (kind, clamp_lo, clamp_hi) ; kind in {"str","float","int"}
_FIELD_SPECS = {
    "constraint_name":      ("str",   None, None),
    "next_constraint_name": ("str",   None, None),
    "strength":             ("float", 0.0,  1e12),
    "restlength":           ("float", 0.0,  1e6),
    "broken":               ("int",   0,    1),
}
_FIELD_ORDER = ("constraint_name", "next_constraint_name", "strength", "restlength", "broken")


@endpoint("set_constraint_field")
def set_constraint_field(params):
    """Typed, LITERAL assignment of RBD constraint-network prim attributes by group — the zero-VEX
    answer to naming/breaking constraints by attribute. `input` = a constraint-network SOP (e.g. the
    node from rbd_constraints, or any geo whose output carries the constraint lines). A single
    attribcreate::2.0 is wired after it and writes each supplied field as a PRIMITIVE attribute,
    scoped to an optional prim `group`.

    Fields (supply one or more): constraint_name (str — the type the solver maps: Glue/Hard/Soft or a
    custom relationship name), next_constraint_name (str — what it becomes when it breaks), strength
    (float — the breaking threshold), restlength (float — soft/spring rest length), broken (int 0|1 —
    pre-broken flag). group (prim group/pattern; '' = all constraints). output (which output of
    `input` carries the constraint geometry: 0 for connectadjacentpieces, 1 for rbdconstraintsfrom*;
    default 0). NO wrangle — pure typed attribcreate. Cooks once (an attribute op, safe)."""
    requested = [f for f in _FIELD_ORDER if f in params]
    if not requested:
        raise ValueError("set_constraint_field: supply at least one of %s" % (", ".join(_FIELD_ORDER),))
    out_index = int(params.get("output", 0))
    n = _child_after_out(params["input"], "attribcreate::2.0", params.get("name"), out_index)
    applied = {}
    # scope
    _try_set(n, "grouptype", 4)                       # prims
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    _try_set(n, "encodenames", 0)
    n.parm("numattr").set(len(requested))
    for i, field in enumerate(requested, start=1):
        kind, lo, hi = _FIELD_SPECS[field]
        _try_set(n, "name%d" % i, field)
        _try_set(n, "class%d" % i, _CLASS_PRIMITIVE)
        _try_set(n, "writevalues%d" % i, 1)
        if kind == "str":
            _try_set(n, "type%d" % i, _TYPE_STRING)
            applied[field] = _try_set(n, "string%d" % i, str(params[field]))
        elif kind == "float":
            _try_set(n, "type%d" % i, _TYPE_FLOAT)
            _try_set(n, "size%d" % i, 1)
            applied[field] = _try_set(n, "value%dv1" % i, clamp(float(params[field]), lo, hi))
        else:  # int
            _try_set(n, "type%d" % i, _TYPE_INT)
            _try_set(n, "size%d" % i, 1)
            applied[field] = _try_set(n, "value%dv1" % i, int(clamp(int(params[field]), lo, hi)))
    n.cook(force=True)
    return {"node": n.path(), "attribcreate": n.path(), "fields": requested,
            "constraint_prims": _con_prim_count(n), "applied": applied}


# ── glue_cluster — chunk-based glue clustering (destruction art-direction) ─────
# gluecluster (unversioned, live-probed): input 'Glue Network'. attribname, intracluster (default -1
# = keep original within-cluster strength), intercluster (default 1), propagate_iteration, boundary
# noise (addclusternoise + clusteroffset/clusterjitter/clustersize vec3), randomdetach + detachseed/
# detachratio, visualizecluster.
@endpoint("glue_cluster")
def glue_cluster(params):
    """Chunk-based glue clustering (gluecluster SOP) — group fractured pieces into clusters so the
    structure breaks in CHUNKS/slabs, not per-shard: the top destruction art-direction control.
    `input` = a glue/constraint-network SOP (the bond graph, e.g. from rbd_constraints); the node is
    wired after it (Glue Network in0). Weakens inter-cluster bonds and (optionally) keeps intra-cluster
    bonds strong so clusters stay coherent until impact.

    attribname (cluster id attr, default 'cluster'), intracluster (within-cluster strength mult,
    default -1 = unchanged/strongest), intercluster (between-cluster strength mult, default 1),
    propagate_iteration (cluster growth iterations), addclusternoise (bool), clusteroffset [x,y,z],
    clusterjitter [x,y,z], clustersize [x,y,z], randomdetach (bool), detachseed, detachratio (0..1
    fraction detached), visualizecluster (bool colour-by-cluster). output (which output of `input`
    carries the glue network: 0 default). Cooks once (a graph op, safe)."""
    out_index = int(params.get("output", 0))
    n = _child_after_out(params["input"], "gluecluster", params.get("name"), out_index)
    applied = {}
    if "attribname" in params:
        applied["attribname"] = _try_set(n, "attribname", str(params["attribname"]))
    if "intracluster" in params:
        applied["intracluster"] = _try_set(n, "intracluster", clamp(float(params["intracluster"]), -1.0, 1e9))
    if "intercluster" in params:
        applied["intercluster"] = _try_set(n, "intercluster", clamp(float(params["intercluster"]), -1.0, 1e9))
    if "propagate_iteration" in params:
        applied["propagate_iteration"] = _try_set(n, "propagate_iteration",
                                                  int(clamp(int(params["propagate_iteration"]), 0, 100000)))
    if "addclusternoise" in params:
        applied["addclusternoise"] = _try_set(n, "addclusternoise", bool(params["addclusternoise"]))
    if "clusteroffset" in params:
        applied["clusteroffset"] = _set_vec(n, "clusteroffset", params["clusteroffset"])
    if "clusterjitter" in params:
        applied["clusterjitter"] = _set_vec(n, "clusterjitter", params["clusterjitter"])
    if "clustersize" in params:
        applied["clustersize"] = _set_vec(n, "clustersize", params["clustersize"])
    if "randomdetach" in params:
        applied["randomdetach"] = _try_set(n, "randomdetach", bool(params["randomdetach"]))
    if "detachseed" in params:
        applied["detachseed"] = _try_set(n, "detachseed", clamp(float(params["detachseed"]), 0.0, 1e9))
    if "detachratio" in params:
        applied["detachratio"] = _try_set(n, "detachratio", clamp(float(params["detachratio"]), 0.0, 1.0))
    if "visualizecluster" in params:
        applied["visualizecluster"] = _try_set(n, "visualizecluster", bool(params["visualizecluster"]))
    n.cook(force=True)
    return {"node": n.path(), "gluecluster": n.path(),
            "constraint_prims": _con_prim_count(n), "applied": applied}


# ── rbd_constraints_from_curves — route constraints along user curves ─────────
# rbdconstraintsfromcurves (unversioned, live-probed): inputs 0 Geometry(pieces), 1 Constraint, 2
# Proxy, 3 Curves. connectiontype MENU ['surface','hinge','centroid'] (default centroid=1). Rule
# knobs are curve_* prefixed: curve_nptsperarea, curve_pieceattrib, curve_searchradius,
# curve_maxsearchpoints, curve_maxconnections, curve_constraintsperpiece, curve_createcluster,
# curve_usecurvegeo. groupname default 'connectors'.
_CFC_CONNTYPE = ("surface", "hinge", "centroid")


@endpoint("rbd_constraints_from_curves")
def rbd_constraints_from_curves(params):
    """Build the RBD constraint network ALONG user curves (rbdconstraintsfromcurves SOP) — custom bond
    routing for rebar, cables, chains, or hand-drawn break lines, and the SOP-reachable HINGE
    connection type. `input` = the fractured-pieces SOP (wired to Geometry in0); `curves` = a curve
    SOP whose curves route the constraints (object-merged into the same network and wired to Curves
    in3). Output constraint prims are polylines following the curves.

    connectiontype (surface|hinge|centroid — centroid default; hinge = the mechanical hinge bond),
    groupname (constraint group, default 'connectors'), pieceattribute (curve_pieceattrib, default
    'name'), nptsperarea, searchradius, maxsearchpoints, maxconnections, constraintsperpiece (-1 =
    unlimited), createcluster (bool), usecurvegeo (bool — use the curve geometry directly as the bond
    geometry). Pair with set_constraint_field / rbd_constraint_properties to author the physics, then
    wire into a solver. Cooks once (a graph op, safe)."""
    n = child_after(params["input"], "rbdconstraintsfromcurves", params.get("name"))
    applied = {}
    # wire the curves to input 3
    curves_wired = False
    if params.get("curves"):
        cur = resolve_node(str(params["curves"]))
        try:
            if isinstance(cur, hou.ObjNode):
                disp = cur.displayNode() or cur.renderNode()
                if disp is not None:
                    cur = disp
        except Exception:
            pass
        om = n.parent().createNode("object_merge", "curves_src")
        _try_set(om, "objpath1", cur.path())
        om.moveToGoodPosition()
        n.setInput(3, om)
        curves_wired = True
        applied["curves"] = True
    if "connectiontype" in params:
        applied["connectiontype"] = _menu_set(n, "connectiontype", str(params["connectiontype"]), _CFC_CONNTYPE)
    if "groupname" in params:
        applied["groupname"] = _try_set(n, "groupname", str(params["groupname"]))
    if "pieceattribute" in params:
        applied["pieceattribute"] = _try_set(n, "curve_pieceattrib", str(params["pieceattribute"]))
    if "nptsperarea" in params:
        applied["nptsperarea"] = _try_set(n, "curve_nptsperarea", clamp(float(params["nptsperarea"]), 0.0, 1e9))
    if "searchradius" in params:
        applied["searchradius"] = _try_set(n, "curve_searchradius", clamp(float(params["searchradius"]), 0.0, 1e6))
    if "maxsearchpoints" in params:
        applied["maxsearchpoints"] = _try_set(n, "curve_maxsearchpoints", int(clamp(int(params["maxsearchpoints"]), 1, 1000000)))
    if "maxconnections" in params:
        applied["maxconnections"] = _try_set(n, "curve_maxconnections", int(clamp(int(params["maxconnections"]), 1, 1000000)))
    if "constraintsperpiece" in params:
        applied["constraintsperpiece"] = _try_set(n, "curve_constraintsperpiece", int(clamp(int(params["constraintsperpiece"]), -1, 1000000)))
    if "createcluster" in params:
        applied["createcluster"] = _try_set(n, "curve_createcluster", bool(params["createcluster"]))
    if "usecurvegeo" in params:
        applied["usecurvegeo"] = _try_set(n, "curve_usecurvegeo", bool(params["usecurvegeo"]))
    n.cook(force=True)
    con_prims = 0
    try:
        cg = n.geometry(1)
        con_prims = len(cg.prims()) if cg is not None else 0
    except Exception:
        pass
    return {"node": n.path(), "constraints": n.path(), "curves_wired": curves_wired,
            "constraint_prims": con_prims, "applied": applied}


def _con_prims_out1(node):
    """Constraint-prim count on output 1 (the constraint-network output on rbdconstraintsfrom*/
    rbdgroupconstraints — probe-confirmed). Probe-safe."""
    try:
        g = node.geometry(1)
        return len(g.prims()) if g is not None else 0
    except Exception:
        return 0


def _sop_disp(path):
    """Resolve a node path to its displayed SOP (unwrap an ObjNode to its display/render node)."""
    src = resolve_node(str(path))
    try:
        if isinstance(src, hou.ObjNode):
            disp = src.displayNode() or src.renderNode()
            if disp is not None:
                src = disp
    except Exception:
        pass
    return src


# ── rbd_constraints_from_lines — route constraints along explicit line segments ─
# rbdconstraintsfromlines (unversioned, live-probed): inputs 0 Geometry(pieces), 1 Constraint
# Geometry, 2 Proxy Geometry — NO curves/lines input; lines are the `lines` MULTIPARM of literal
# point-pairs (the data-only form of the handle-drawn tool). Multiparm count parm = 'lines'; per
# instance line_useline# (bool) / line_pt1# (vec3) / line_pt2# (vec3) / line_usehingepos# /
# line_hingepos# (vec3) / line_hingerot# (vec3). connectiontype MENU ['surface','hinge','centroid']
# (default hinge=1). grouptype = 'group' Int-menu ['0','1','2']=['None','Primitive Group','Tag'].
# groupname/tag default 'connectors'. Constraint lines ride on OUTPUT 1 (probe-confirmed). The
# 'descriptiveparm' label carries an ifs()/ch() display expression — NOT exposed (read-only label).
_CFL_CONNTYPE = ("surface", "hinge", "centroid")


def _set_lines(node, segments):
    """Populate the `lines` multiparm with literal point-pair segments (data-only). Each segment is
    {"pt1":[x,y,z],"pt2":[x,y,z]} or [[x,y,z],[x,y,z]], optional "hinge":[x,y,z] + "hingerot":[x,y,z]
    for the hinge connection type. Returns the count written."""
    node.parm("lines").set(len(segments))
    for i, seg in enumerate(segments, start=1):
        if isinstance(seg, dict):
            p1 = seg.get("pt1")
            p2 = seg.get("pt2")
            hpos = seg.get("hinge")
            hrot = seg.get("hingerot")
        else:
            p1, p2 = seg[0], seg[1]
            hpos = seg[2] if len(seg) > 2 else None
            hrot = seg[3] if len(seg) > 3 else None
        _try_set(node, "line_useline%d" % i, True)
        if isinstance(p1, (list, tuple)):
            _set_vec(node, "line_pt1%d" % i, p1)
        if isinstance(p2, (list, tuple)):
            _set_vec(node, "line_pt2%d" % i, p2)
        if isinstance(hpos, (list, tuple)):
            _try_set(node, "line_usehingepos%d" % i, True)
            _set_vec(node, "line_hingepos%d" % i, hpos)
        if isinstance(hrot, (list, tuple)):
            _set_vec(node, "line_hingerot%d" % i, hrot)
    return len(segments)


@endpoint("rbd_constraints_from_lines")
def rbd_constraints_from_lines(params):
    """Build an RBD constraint network from explicit LINE SEGMENTS (rbdconstraintsfromlines SOP) — the
    data-only form of the handle-drawn line tool: each line, given as a literal point-pair, routes a
    bond between the fractured pieces it crosses. `input` = the fractured-pieces SOP (wired to Geometry
    in0); the node is created after it. `lines` = a list of segments, each {"pt1":[x,y,z],"pt2":
    [x,y,z]} (or [[x,y,z],[x,y,z]]); add "hinge":[x,y,z] (+ optional "hingerot":[x,y,z]) to place a
    hinge pivot for the hinge connection type. Output constraint prims are the polylines on OUTPUT 1.

    connectiontype (surface|hinge|centroid — how the bond attaches; hinge = mechanical hinge bond),
    hingelength (float, hinge span), grouptype (int 0|1|2 = None|Primitive Group|Tag — how the output
    is grouped), groupname (str, default 'connectors'), tag (str, default 'connectors'), usepointname
    (bool — take the piece name from points). Geometry culling: cull (bool enable), cullsize [x,y,z],
    cullcenter [x,y,z], cullrotation [x,y,z], cullpieces (bool), cullinvert (bool). Pair with
    set_constraint_field / rbd_constraint_properties to author the physics. Cooks once (a graph op,
    safe). NO wrangle/expression — literal typed params only."""
    n = child_after(params["input"], "rbdconstraintsfromlines", params.get("name"))
    applied = {}
    lines = params.get("lines")
    # The gateway has no structured-list Kind, so `lines` rides as a JSON string over MCP; tolerate
    # both that and a native list (like _set_color_ramp elsewhere). Floats-only — no code path.
    if isinstance(lines, str):
        import json as _json
        try:
            lines = _json.loads(lines)
        except Exception:
            raise ValueError('`lines` must be a JSON array of segments, e.g. '
                             '[{"pt1":[0,0,0],"pt2":[1,0,0]}]')
    if isinstance(lines, (list, tuple)) and lines:
        applied["lines"] = _set_lines(n, lines)
    if "connectiontype" in params:
        applied["connectiontype"] = _menu_set(n, "connectiontype", str(params["connectiontype"]), _CFL_CONNTYPE)
    if "hingelength" in params:
        applied["hingelength"] = _try_set(n, "hingelength", clamp(float(params["hingelength"]), 0.0, 1e6))
    if "grouptype" in params:
        applied["grouptype"] = _try_set(n, "group", int(clamp(int(params["grouptype"]), 0, 2)))
    if "groupname" in params:
        applied["groupname"] = _try_set(n, "groupname", str(params["groupname"]))
    if "tag" in params:
        applied["tag"] = _try_set(n, "tag", str(params["tag"]))
    if "usepointname" in params:
        applied["usepointname"] = _try_set(n, "usepointname", bool(params["usepointname"]))
    if "cull" in params:
        applied["cull"] = _try_set(n, "cull", bool(params["cull"]))
    if "cullsize" in params:
        applied["cullsize"] = _set_vec(n, "cullsize", params["cullsize"])
    if "cullcenter" in params:
        applied["cullcenter"] = _set_vec(n, "cullcenter", params["cullcenter"])
    if "cullrotation" in params:
        applied["cullrotation"] = _set_vec(n, "cullrotation", params["cullrotation"])
    if "cullpieces" in params:
        applied["cullpieces"] = _try_set(n, "cullpieces", bool(params["cullpieces"]))
    if "cullinvert" in params:
        applied["cullinvert"] = _try_set(n, "cullinvert", bool(params["cullinvert"]))
    n.cook(force=True)
    return {"node": n.path(), "constraints": n.path(),
            "constraint_prims": _con_prims_out1(n), "applied": applied}


# ── rbd_group_constraints — name/group an RBD constraint network ───────────────
# rbdgroupconstraints (unversioned, live-probed): inputs 0 Geometry(pieces, REQUIRED — grouping needs
# the piece geometry), 1 Constraint Geometry (the network to group). group=output Group Name (default
# 'connectors'); usegroups Int-menu ['0','1']=['All to Group','Group to Group']; inputgroup (input
# constraint sub-group), group1/group2 (the two piece groups a Group-to-Group bond spans). Grouped
# constraints ride on OUTPUT 1. Probe-confirmed: with pieces on in0 + network on in1, the named group
# appears on all constraint prims of out1; wiring the network to in0 ERRORS (expects pieces).
_RGC_USEGROUPS = 2  # valid int range 0..1


@endpoint("rbd_group_constraints")
def rbd_group_constraints(params):
    """Name / organize an RBD constraint network (rbdgroupconstraints SOP) — assign the bonds to a
    named primitive group so a solver, set_constraint_field, or rbd_constraint_properties can target
    them. `input` = the fractured-pieces SOP (wired to Geometry in0, REQUIRED — grouping is resolved
    against the pieces). `constraints` = a NodePath whose output carries the constraint network
    (object-merged and wired to Constraint Geometry in1, REQUIRED). Grouped constraints ride on OUTPUT
    1.

    group (str — output group name applied to the constraints, default 'connectors'), usegroups (int
    0|1 = All to Group | Group to Group — 'All' tags every bond, 'Group to Group' tags only bonds
    spanning group1↔group2), inputgroup (str — restrict to an existing constraint sub-group), group1
    (str — first piece group, for Group to Group), group2 (str — second piece group). All typed
    scalars/strings; no code. Cooks once (a graph op, safe)."""
    n = child_after(params["input"], "rbdgroupconstraints", params.get("name"))
    applied = {}
    net_wired = False
    if params.get("constraints"):
        net = _sop_disp(params["constraints"])
        om = n.parent().createNode("object_merge", "constraint_src")
        _try_set(om, "objpath1", net.path())
        om.moveToGoodPosition()
        n.setInput(1, om)
        net_wired = True
        applied["constraints"] = True
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    if "usegroups" in params:
        applied["usegroups"] = _try_set(n, "usegroups", int(clamp(int(params["usegroups"]), 0, _RGC_USEGROUPS - 1)))
    if "inputgroup" in params:
        applied["inputgroup"] = _try_set(n, "inputgroup", str(params["inputgroup"]))
    if "group1" in params:
        applied["group1"] = _try_set(n, "group1", str(params["group1"]))
    if "group2" in params:
        applied["group2"] = _try_set(n, "group2", str(params["group2"]))
    n.cook(force=True)
    return {"node": n.path(), "constraints": n.path(), "constraint_network_wired": net_wired,
            "constraint_prims": _con_prims_out1(n), "applied": applied}


# ── voronoi_adjacency — piece-adjacency graph from voronoi cells ───────────────
# voronoiadjacency (unversioned, live-probed): input 0 'Input Points'; ZERO exposed parameters — a
# pure graph op that builds the piece-adjacency network (the bonds used to route constraints) from the
# voronoi cell points/pieces. Cook-verified error-free on both fractured-piece geometry and a
# connectadjacentpieces network. Adjacency lines ride on OUTPUT 0.
@endpoint("voronoi_adjacency")
def voronoi_adjacency(params):
    """Build the piece-ADJACENCY graph from a voronoi fracture (voronoiadjacency SOP) — the bond
    topology (which pieces touch which) that constraint networks are routed along. `input` = the
    voronoi cell points / fractured-piece geometry (wired to Input Points in0); the node is created
    after it. Output is the adjacency network (polylines between adjacent pieces) on OUTPUT 0. Feed it
    into set_constraint_field / rbd_constraint_properties to author bond physics, or into a solver.
    The node exposes NO parameters — it is a pure, deterministic graph op. Cooks once (safe)."""
    n = child_after(params["input"], "voronoiadjacency", params.get("name"))
    n.cook(force=True)
    return {"node": n.path(), "adjacency": n.path(), "adjacency_prims": _con_prim_count(n)}

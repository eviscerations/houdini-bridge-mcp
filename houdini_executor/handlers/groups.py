"""Group-lane handlers (SOP) — the grouping plumbing a real destruction / sim / cleanup setup
leans on constantly: promoting a group between point/prim/edge/vertex classes, selecting numeric
index ranges / every-Nth, growing or shrinking a group by edges, transferring groups between
geometries by proximity, housekeeping (delete/rename), and the deep geometric-selection modes
(bounding sphere/object, backface-by-camera, edge-angle, open/unshared edges, keep-not-wholly-
contained) that the existing shallow `group_create` (bbox + by-normal only) doesn't reach.

Every parm name + menu token + multiparm-folder name below was live-probed on Houdini 21.0.671; nothing is guessed. All group nodetypes are UNVERSIONED on
this build. Style mirrors handlers/attribops.py + handlers/sim.py: typed, clamped, probe-safe
(`_try_set` skips absent parms, never invents one), creators FAIL on name collision (child_after ->
createNode(type, name) raises rather than clobber existing user work).

DATA-ONLY boundary: these are pure typed node wrappers. `groupexpression` is DELIBERATELY NOT
exposed — its rule is a raw VEX `snippet` string (identical RCE profile to the omitted wrangle
endpoint); it belongs to the user-mediated safe-VEX lane, not here.
"""

import hou
from houdini_executor.server import endpoint, child_after, clamp, resolve_node
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe setters (same contract as attribops.py / sim.py) ──────────────




def _str_menu_set(node, parm, token, tokens):
    """String-type menu parm: the TOKEN itself is the stored value."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _set_vec(node, parm, values, n):
    """Set an n-tuple float parm from a list (pads/truncates). Probe-safe."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    vals = [float(x) for x in list(values)[:n]] + [0.0] * (n - min(len(values), n))
    try:
        pt.set(tuple(vals))
        return True
    except Exception:
        return False


def _sop_of(path):
    """Resolve a node path to the SOP a second input should read (an /obj geo -> its display SOP),
    mirroring child_after's ObjNode unwrap so callers can pass either a SOP or the containing geo."""
    n = resolve_node(path)
    try:
        if isinstance(n, hou.ObjNode):
            disp = n.displayNode() or n.renderNode()
            if disp is not None:
                return disp
    except Exception:
        pass
    return n


def _cook(n):
    """Force a cook so readback reflects the op; guarded so a missing required 2nd input leaves the
    built node in place rather than failing the build. Returns cook OK."""
    try:
        n.geometry()
        return True
    except Exception:
        return False


def _norm_class(c, allowed):
    """Map friendly class aliases (point/prim/vertex) onto a node's own plural/singular tokens."""
    c = str(c)
    if c in allowed:
        return c
    if c == "prim":
        for t in ("prims", "primitive"):
            if t in allowed:
                return t
    if c == "primitive" and "prims" in allowed:
        return "prims"
    if c == "prims" and "primitive" in allowed:
        return "primitive"
    if c == "point":
        for t in ("points", "point"):
            if t in allowed:
                return t
    if c == "points" and "point" in allowed:
        return "point"
    if c == "vertex" and "vertices" in allowed:
        return "vertices"
    if c == "vertices" and "vertex" in allowed:
        return "vertex"
    if c == "edge" and "edges" in allowed:
        return "edges"
    if c == "edges" and "edge" in allowed:
        return "edge"
    return c


def _grp_counts(g, gname):
    """Best-effort count of a named group across classes (for readback)."""
    out = {}
    try:
        pg = g.findPointGroup(gname)
        if pg is not None:
            out["points"] = len(pg.points())
    except Exception:
        pass
    try:
        prg = g.findPrimGroup(gname)
        if prg is not None:
            out["prims"] = len(prg.prims())
    except Exception:
        pass
    try:
        eg = g.findEdgeGroup(gname)
        if eg is not None:
            out["edges"] = len(eg.edges())
    except Exception:
        pass
    return out


# ══════════════════════════════════════════════════════════════════════════════
# GROUP PROMOTE  (grouppromote — multiparm folder 'promotions')
# ══════════════════════════════════════════════════════════════════════════════
_PROMOTE_FROM = ("auto", "prims", "points", "edges", "vertices")
_PROMOTE_TO = ("prims", "points", "edges", "vertices")


@endpoint("group_promote")
def group_promote(params):
    """Convert a group between element classes (point<->prim<->vertex<->edge) — the constant
    fracture/constraint move (e.g. a point group promoted to prims to select whole pieces, then back).
    group = the existing group name/pattern to promote; from_class: auto|points|prims|edges|vertices
    (auto detects); to_class: points|prims|edges|vertices. new_name renames the promoted group (else
    it keeps `group`'s name). only_boundary keeps only boundary elements when promoting down;
    include_unshared includes unshared edges; preserve keeps the original group as well."""
    n = child_after(params["input"], "grouppromote", params.get("name"))
    applied = {}
    _try_set(n, "promotions", 1)
    _try_set(n, "enable1", True)
    _try_set(n, "group1", str(params.get("group", "")))
    applied["from_class"] = _menu_set(n, "fromtype1",
                                      _norm_class(params.get("from_class", "auto"), _PROMOTE_FROM),
                                      _PROMOTE_FROM)
    applied["to_class"] = _menu_set(n, "totype1",
                                    _norm_class(params.get("to_class", "points"), _PROMOTE_TO),
                                    _PROMOTE_TO)
    if params.get("new_name"):
        _try_set(n, "newname1", str(params["new_name"]))
    if "only_boundary" in params:
        _try_set(n, "onlyboundary1", bool(params["only_boundary"]))
    if "include_unshared" in params:
        _try_set(n, "includeunshared1", bool(params["include_unshared"]))
    if "preserve" in params:
        _try_set(n, "preserve1", bool(params["preserve"]))
    cooked = _cook(n)
    out = {"node": n.path(), "cooked": cooked, "applied": applied}
    if cooked:
        result_name = str(params.get("new_name") or params.get("group", ""))
        if result_name:
            out["counts"] = _grp_counts(n.geometry(), result_name)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# GROUP RANGE  (grouprange — multiparm folder 'numrange')
# ══════════════════════════════════════════════════════════════════════════════
_RANGE_TYPE = ("points", "prims", "vertices")
_RANGE_METHOD = ("absolute", "relative", "length", "partition")
_RANGE_MERGE = ("replace", "union", "intersect", "subtract")


@endpoint("group_range")
def group_range(params):
    """Group elements by numeric index range and/or every-Nth stride — select piece-id subsets,
    alternate rows, deterministic slices. group_name = the group to create (default 'range'); class:
    points|prims|vertices; method: absolute (index start..end) | relative (fractional 0..1 of the
    total) | length | partition. start/end bound the index (or fraction) window. select_amount ('of')
    + select_total ('every') + select_offset stride within the window (e.g. of=1 every=3 => every 3rd
    element). num_partitions sets the partition count when method='partition' (splits the elements
    into N even blocks). invert flips membership. merge: replace|union|intersect|subtract combine
    with an existing same-named group."""
    n = child_after(params["input"], "grouprange", params.get("name"))
    applied = {}
    _try_set(n, "numrange", 1)
    _try_set(n, "enable1", True)
    gname = str(params.get("group_name", "range"))
    _try_set(n, "groupname1", gname)
    applied["class"] = _menu_set(n, "grouptype1",
                                 _norm_class(params.get("class", "points"), _RANGE_TYPE), _RANGE_TYPE)
    applied["method"] = _menu_set(n, "method1", str(params.get("method", "absolute")), _RANGE_METHOD)
    applied["merge"] = _menu_set(n, "mergeop1", str(params.get("merge", "replace")), _RANGE_MERGE)
    if "start" in params:
        _try_set(n, "start1", int(clamp(int(params["start"]), 0, 2000000000)))
    if "end" in params:
        _try_set(n, "end1", int(clamp(int(params["end"]), 0, 2000000000)))
    elif "select_total" in params or "select_amount" in params:
        # every-Nth stride with no explicit window: the absolute range defaults to 0..0 (a single
        # element), which would defeat the stride. Extend the window to cover all elements.
        _try_set(n, "end1", 2000000000)
    if "length" in params:
        _try_set(n, "length1", int(clamp(int(params["length"]), 0, 2000000000)))
    if "num_partitions" in params:
        _try_set(n, "numpartition1", int(clamp(int(params["num_partitions"]), 1, 2000000000)))
    if "select_amount" in params:
        _try_set(n, "selectamount1", int(clamp(int(params["select_amount"]), 0, 2000000000)))
    if "select_total" in params:
        _try_set(n, "selecttotal1", int(clamp(int(params["select_total"]), 1, 2000000000)))
    if "select_offset" in params:
        _try_set(n, "selectoffset1", int(clamp(int(params["select_offset"]), 0, 2000000000)))
    if "invert" in params:
        _try_set(n, "invert1", bool(params["invert"]))
    cooked = _cook(n)
    out = {"node": n.path(), "group_name": gname, "cooked": cooked, "applied": applied}
    if cooked:
        out["counts"] = _grp_counts(n.geometry(), gname)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# GROUP EXPAND / SHRINK  (groupexpand — single-parm, clean)
# ══════════════════════════════════════════════════════════════════════════════
_EXPAND_TYPE = ("auto", "vertices", "edges", "points", "prims")


@endpoint("group_expand")
def group_expand(params):
    """Grow or shrink a group by N edge steps over the connectivity — constraint anchor bands,
    collision skins, cleaning ragged selections. group = the group to modify; steps = number of edge
    steps (POSITIVE grows, NEGATIVE shrinks); class: auto|points|prims|edges|vertices. output_group
    names the result (default reuses `group`). by_normal + normal_angle (deg) stop the spread at a
    normal-angle discontinuity (don't grow across a hard edge). flood_fill grows unbounded until it
    hits a barrier. prim_share_edge requires prims to share an edge (not just a point) to be included."""
    n = child_after(params["input"], "groupexpand", params.get("name"))
    applied = {}
    _try_set(n, "group", str(params.get("group", "")))
    out_g = str(params.get("output_group", params.get("group", "")))
    _try_set(n, "outputgroup", out_g)
    applied["class"] = _menu_set(n, "grouptype",
                                 _norm_class(params.get("class", "auto"), _EXPAND_TYPE), _EXPAND_TYPE)
    if "steps" in params:
        _try_set(n, "numsteps", int(clamp(int(params["steps"]), -100000, 100000)))
    if "flood_fill" in params:
        _try_set(n, "floodfill", bool(params["flood_fill"]))
    if "prim_share_edge" in params:
        _try_set(n, "primshareedge", bool(params["prim_share_edge"]))
    if "by_normal" in params:
        _try_set(n, "bynormal", bool(params["by_normal"]))
    if "normal_angle" in params:
        _try_set(n, "bynormal", True)
        _try_set(n, "normalangle", clamp(float(params["normal_angle"]), 0.0, 180.0))
    cooked = _cook(n)
    out = {"node": n.path(), "output_group": out_g, "cooked": cooked, "applied": applied}
    if cooked:
        out["counts"] = _grp_counts(n.geometry(), out_g)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# GROUP TRANSFER  (grouptransfer — 2 inputs, single-parm)
# ══════════════════════════════════════════════════════════════════════════════
_TRANSFER_CONFLICT = ("skipgroup", "overwrite", "addsuffix")


@endpoint("group_transfer")
def group_transfer(params):
    """Transfer group membership from one geometry onto another by proximity — carry a hand-authored
    selection (floor/anchor/paint groups) onto resimulated or remeshed geometry. input = geometry to
    transfer groups ONTO (destination); source = NodePath of the geometry to transfer FROM. Toggle
    which classes move: do_points/do_prims/do_edges (all default on). point_groups/prim_groups/
    edge_groups = space-sep group name patterns to limit the transfer (empty = all of that class).
    max_distance caps the proximity search (set use_threshold False to transfer regardless of
    distance). on_conflict: skipgroup|overwrite|addsuffix when a same-named group already exists."""
    n = child_after(params["input"], "grouptransfer", params.get("name"))
    if params.get("source"):
        n.setInput(1, _sop_of(params["source"]))
    applied = {}
    if "do_points" in params:
        _try_set(n, "points", bool(params["do_points"]))
    if "do_prims" in params:
        _try_set(n, "primitives", bool(params["do_prims"]))
    if "do_edges" in params:
        _try_set(n, "edges", bool(params["do_edges"]))
    if params.get("point_groups") is not None:
        _try_set(n, "pointgroups", str(params["point_groups"]))
    if params.get("prim_groups") is not None:
        _try_set(n, "primgroups", str(params["prim_groups"]))
    if params.get("edge_groups") is not None:
        _try_set(n, "edgegroups", str(params["edge_groups"]))
    if "use_threshold" in params:
        _try_set(n, "threshold", bool(params["use_threshold"]))
    if "max_distance" in params:
        _try_set(n, "threshold", True)
        _try_set(n, "thresholddist", clamp(float(params["max_distance"]), 0.0, 1e9))
    if params.get("on_conflict"):
        applied["on_conflict"] = _str_menu_set(n, "groupnameconflict",
                                               str(params["on_conflict"]), _TRANSFER_CONFLICT)
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


# ══════════════════════════════════════════════════════════════════════════════
# GROUP DELETE  (groupdelete — multiparm folder 'deletions')
# ══════════════════════════════════════════════════════════════════════════════
_DELETE_TYPE = ("any", "points", "prims", "edges", "vertices")


@endpoint("group_delete")
def group_delete(params):
    """Delete group DEFINITIONS (not geometry) by name/pattern — housekeeping to keep piece geo clean
    before pack/sim, or drop temporary selection groups. group = group name or pattern to remove
    (wildcards ok, e.g. 'tmp_*'); class: any|points|prims|edges|vertices (default any). To delete
    several patterns, pass a space-separated pattern in `group`. NOTE: this removes the group, the
    geometry is untouched — use `blast` to delete geometry by group."""
    n = child_after(params["input"], "groupdelete", params.get("name"))
    applied = {}
    _try_set(n, "deletions", 1)
    _try_set(n, "enable1", True)
    _try_set(n, "group1", str(params.get("group", "")))
    applied["class"] = _menu_set(n, "grouptype1",
                                 _norm_class(params.get("class", "any"), _DELETE_TYPE), _DELETE_TYPE)
    return {"node": n.path(), "cooked": _cook(n), "applied": applied}


# ══════════════════════════════════════════════════════════════════════════════
# GROUP RENAME  (grouprename — multiparm folder 'renames')
# ══════════════════════════════════════════════════════════════════════════════
_RENAME_TYPE = ("any", "points", "prims", "edges", "vertices")


@endpoint("group_rename")
def group_rename(params):
    """Rename a group (housekeeping / conforming names before a solver that expects a fixed group
    name). group = existing group name/pattern; new_name = the new name; class: any|points|prims|
    edges|vertices (default any)."""
    n = child_after(params["input"], "grouprename", params.get("name"))
    applied = {}
    _try_set(n, "renames", 1)
    _try_set(n, "enable1", True)
    _try_set(n, "group1", str(params.get("group", "")))
    _try_set(n, "newname1", str(params.get("new_name", "")))
    applied["class"] = _menu_set(n, "grouptype1",
                                 _norm_class(params.get("class", "any"), _RENAME_TYPE), _RENAME_TYPE)
    return {"node": n.path(), "new_name": str(params.get("new_name", "")),
            "cooked": _cook(n), "applied": applied}


# ══════════════════════════════════════════════════════════════════════════════
# GROUP GEO  (groupcreate — the DEEP geometric-selection modes group_create omits)
# ══════════════════════════════════════════════════════════════════════════════
_GEO_TYPE = ("primitive", "point", "edge", "vertex")
_GEO_BOUND = ("usebbox", "usebsphere", "usebobject", "usebvolume", "usebconvex")
_GEO_MERGE = ("replace", "union", "intersect", "subtract")
# geotype is an ordered menu; set by string TOKEN (order-independent, verified) so a curated subset
# can't desync from the node's full menu order. Curated to the useful primitive-type filters.
_GEO_GEOTYPE = ("all", "poly", "polysoup", "mesh", "sphere", "tube", "vdb", "volume",
                "PackedFragment", "PackedGeometry", "PackedDisk", "PackedUSD", "PackedAgent")


@endpoint("group_geo")
def group_geo(params):
    """Create a named group by DEEP geometric selection — the modes the shallow `group_create` (bbox
    + by-normal only) doesn't reach: bounding SPHERE / bounding OBJECT (a second geometry), backface
    (by-normal vs a camera), edge-angle, open/unshared edges, and keep-not-wholly-contained.

    group_name = group to create (default 'group1'); class: primitive|point|edge|vertex.
    base_group = seed from an existing group/pattern. merge: replace|union|intersect|subtract.

    BOUNDING (enable_bounding): bound_type = usebbox | usebsphere | usebobject | usebvolume |
      usebconvex. bbox=[minx,miny,minz,maxx,maxy,maxz] sets a box centre/size; bound_size=[x,y,z] +
      bound_center=[x,y,z] set a box/sphere directly; bound_object = NodePath of a 2nd geometry to
      bound by (usebobject). keep_partial (includenotwhollycontained) keeps elements only partly
      inside. invert_volume flips the region.

    NORMAL (enable_normal): normal_axis=[x,y,z] + normal_angle (deg) group by facing direction;
      camera = camera NodePath for a view-relative (backface) test; opposite_normals also grabs the
      back-facing set.

    EDGE (enable_edges): min_edge_angle / max_edge_angle (deg) select creased edges; min_edge_len /
      max_edge_len select by edge length; unshared groups open boundary (unshared) edges. Requires
      class=edge.

    geo_type filters to a single primitive type (all|poly|polysoup|mesh|sphere|tube|vdb|volume|
      PackedFragment|PackedGeometry|PackedDisk|PackedUSD|PackedAgent) — e.g. group only the packed
      fragments, or only the vdb prims. random_percent (0..100) groups a random subset of that size;
      random_seed varies the draw.

    Selectors combine (AND) when multiple are enabled."""
    gtype = str(params.get("class", "point"))
    gtype = _norm_class(gtype, _GEO_TYPE)
    gname = str(params.get("group_name", "group1"))
    n = child_after(params["input"], "groupcreate", params.get("name"))
    applied = {}
    _try_set(n, "groupname", gname)
    applied["class"] = _menu_set(n, "grouptype", gtype, _GEO_TYPE)
    _menu_set(n, "mergeop", str(params.get("merge", "replace")), _GEO_MERGE)
    if params.get("base_group"):
        _try_set(n, "groupbase", True)
        _try_set(n, "basegroup", str(params["base_group"]))
    if params.get("geo_type") and str(params["geo_type"]) in _GEO_GEOTYPE:
        applied["geo_type"] = _try_set(n, "geotype", str(params["geo_type"]))

    # ── bounding ──────────────────────────────────────────────────────────────
    bbox = params.get("bbox")
    want_bounding = bool(params.get("enable_bounding")) or bbox is not None \
        or params.get("bound_object") is not None or params.get("bound_size") is not None
    if want_bounding:
        _try_set(n, "groupbounding", True)
        applied["bound_type"] = _menu_set(n, "boundtype",
                                          str(params.get("bound_type", "usebbox")), _GEO_BOUND)
        if bbox is not None and len(bbox) == 6:
            b = [float(x) for x in bbox]
            _set_vec(n, "size", [abs(b[3] - b[0]), abs(b[4] - b[1]), abs(b[5] - b[2])], 3)
            _set_vec(n, "t", [(b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0, (b[2] + b[5]) / 2.0], 3)
        if isinstance(params.get("bound_size"), (list, tuple)):
            _set_vec(n, "size", params["bound_size"], 3)
        if isinstance(params.get("bound_center"), (list, tuple)):
            _set_vec(n, "t", params["bound_center"], 3)
        if params.get("bound_object"):
            n.setInput(1, _sop_of(params["bound_object"]))
        if "keep_partial" in params:
            _try_set(n, "includenotwhollycontained", bool(params["keep_partial"]))
        if "invert_volume" in params:
            _try_set(n, "invertvolume", bool(params["invert_volume"]))

    # ── normal / backface ───────────────────────────────────────────────────────
    naxis = params.get("normal_axis")
    want_normal = bool(params.get("enable_normal")) or naxis is not None or params.get("camera")
    if want_normal:
        _try_set(n, "groupnormal", True)
        if naxis is not None and len(naxis) == 3:
            _set_vec(n, "dir", naxis, 3)
        if "normal_angle" in params:
            _try_set(n, "angle", clamp(float(params["normal_angle"]), 0.0, 180.0))
        if params.get("camera"):
            _try_set(n, "camerapath", str(params["camera"]))
        if "opposite_normals" in params:
            _try_set(n, "oppositenormals", bool(params["opposite_normals"]))

    # ── edge-angle / unshared ──────────────────────────────────────────────────
    want_edges = bool(params.get("enable_edges")) or "min_edge_angle" in params \
        or "max_edge_angle" in params or "min_edge_len" in params \
        or "max_edge_len" in params or params.get("unshared")
    if want_edges:
        _try_set(n, "groupedges", True)
        if "min_edge_angle" in params:
            _try_set(n, "dominedgeangle", True)
            _try_set(n, "minedgeangle", clamp(float(params["min_edge_angle"]), 0.0, 360.0))
        if "max_edge_angle" in params:
            _try_set(n, "domaxedgeangle", True)
            _try_set(n, "maxedgeangle", clamp(float(params["max_edge_angle"]), 0.0, 360.0))
        if "min_edge_len" in params:
            _try_set(n, "dominedgelen", True)
            _try_set(n, "minedgelen", clamp(float(params["min_edge_len"]), 0.0, 1e9))
        if "max_edge_len" in params:
            _try_set(n, "domaxedgelen", True)
            _try_set(n, "maxedgelen", clamp(float(params["max_edge_len"]), 0.0, 1e9))
        if params.get("unshared"):
            _try_set(n, "unshared", True)

    # ── random subset ──────────────────────────────────────────────────────────
    if "random_percent" in params or "random_seed" in params:
        _try_set(n, "grouprandom", True)
        if "random_percent" in params:
            _try_set(n, "percent", clamp(float(params["random_percent"]), 0.0, 100.0))
        if "random_seed" in params:
            _try_set(n, "globalseed", clamp(float(params["random_seed"]), 0.0, 1e12))

    cooked = _cook(n)
    out = {"node": n.path(), "group_name": gname, "class": gtype,
           "cooked": cooked, "applied": applied}
    if cooked:
        out["counts"] = _grp_counts(n.geometry(), gname)
    return out

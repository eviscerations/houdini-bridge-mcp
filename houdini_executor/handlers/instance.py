"""Instance / scatter handlers. Ported from proven logic; params verified against live H21.0.671."""

import hou
from houdini_executor.server import endpoint, resolve_node, clamp, child_after, bridge_into
from houdini_executor.handlers._parmutil import _try_set

try:
    from houdini_executor.governor import governor_gate, advise, magnitude_advice
except Exception:  # noqa: BLE001 — governor is advisory telemetry; must never block handler import
    def governor_gate(op_label):  # fail-soft stub
        return {"band": "unknown"}

    def advise(result, node=None):  # fail-soft stub
        return result

    def magnitude_advice(op_label, params):  # fail-soft stub
        return {"level": "ok", "note": "governor unavailable"}




def _geo_or_raise(node):
    """Return node.geometry(), or raise with the node's ACTUAL cook errors if it is None.
    hou.SopNode.geometry() returns None when the node is in a cook-error state; the callers below
    then do len(g.prims()/points()) and would otherwise blow up with an opaque
    'NoneType has no attribute ...' that hides the real Houdini diagnostic. Surface it instead."""
    g = node.geometry()
    if g is None:
        errs = "; ".join(node.errors()) or "unknown cook error (geometry is None)"
        raise ValueError("%s failed to cook: %s" % (node.path(), errs))
    return g


def _set_scatter_count(scat, count):
    """Set the total-point count on a Scatter SOP robustly.

    Trap: on the plain `scatter` SOP `forcetotal` is a TOGGLE ("Force Total Count") and `npts` is
    the integer count — writing the count to `forcetotal` reads as truthy (toggle on) and leaves
    `npts` at its 1000 default. Detect the parm template type: enable any toggle named forcetotal,
    then write the count to the first INTEGER count parm. Returns the parm name used, or None."""
    count = int(count)
    # Enable the force-total-count toggle if this build exposes it as a toggle.
    tp = scat.parm("forcetotal")
    if tp is not None and isinstance(tp.parmTemplate(), hou.ToggleParmTemplate):
        try:
            tp.set(1)
        except Exception:
            pass
    for cand in ("npts", "forcetotal", "forcetotalcount", "npoints"):
        p = scat.parm(cand)
        if p is None:
            continue
        if isinstance(p.parmTemplate(), hou.ToggleParmTemplate):
            continue  # never write the count into a toggle
        try:
            p.set(count)
            return cand
        except Exception:
            pass
    return None


@endpoint("scatter_copy")
def scatter_copy(params):
    """Scatter points on a target surface and copy a primitive/object onto them (instancing:
    foliage, rocks, ice chunks). target: an existing SOP path, else a default 100x100 grid.
    source: a primitive keyword (box/sphere/tube/torus/grid/circle) or an existing node path.
    """
    name = params["name"]
    count = int(clamp(int(params.get("count", 100)), 1, 10_000_000))
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    g = obj.createNode("geo", name)

    tgt = params.get("target")
    if tgt:
        surf = g.createNode("object_merge", "target")
        surf.parm("objpath1").set(resolve_node(tgt).path())
    else:
        surf = g.createNode("grid")
        if surf.parmTuple("size"):
            surf.parmTuple("size").set((100.0, 100.0))

    scat = g.createNode("scatter")
    scat.setFirstInput(surf)
    count_parm = _set_scatter_count(scat, count)
    # Mask-driven density: weight scatter by a point attribute (e.g. a heightfield mask sampled
    # onto the surface) so foliage grows only where the mask allows — bare-earth LIDAR procgen.
    if params.get("density_attrib"):
        _try_set(scat, "usedensityattrib", True)
        _try_set(scat, "densityattrib", str(params["density_attrib"]))
    if "seed" in params:
        _try_set(scat, "seed", int(params["seed"]))

    src = str(params.get("source", "sphere"))
    if src in ("box", "sphere", "tube", "torus", "grid", "circle"):
        cg = g.createNode(src, "copysrc")
        sp = cg.parm("scale")
        if sp is not None:
            try:
                sp.set(float(params.get("scale", 1.0)))
            except Exception:
                pass
    else:
        cg = g.createNode("object_merge", "copysrc")
        cg.parm("objpath1").set(resolve_node(src).path())

    cp = g.createNode("copytopoints")
    cp.setInput(0, cg)
    cp.setInput(1, scat)
    cp.setDisplayFlag(True)
    cp.setRenderFlag(True)
    g.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    g.layoutChildren()
    cp.cook(force=True)
    return {"node": g.path(), "copy": cp.path(),
            "scattered": len(_geo_or_raise(scat).points()),
            "copied_prims": len(_geo_or_raise(cp).prims()), "count_parm": count_parm}


@endpoint("copy_to_points")
def copy_to_points(params):
    """Copy/instance the `source` SOP onto the points of the `target` SOP (copytopoints::2.0). Each
    copy is transformed by the target point's N/up (orient), pscale (scale), orient (rotate), Cd
    (color). `pack` outputs packed prims (light memory). `id_attrib` = variant/piece matching.
    `target_group`/`source_group` restrict to a named group. Cost = source prims x target points."""
    src = resolve_node(params["source"])
    tgt = resolve_node(params["target"])
    governor_gate("copy_to_points")  # advisory; refuses only in the catastrophic band
    cp = tgt.parent().createNode("copytopoints::2.0")
    # A plain setInput cannot cross /obj networks: if the source template lives in a different
    # geo, bridge it in with an object_merge (xformtype=none -> the template's own local space,
    # the correct stamp semantics). Same-scene path reference, no copy, no exec.
    src_in = bridge_into(src, tgt.parent(), xformtype=0, name_hint=src.name())
    cp.setInput(0, src_in)
    cp.setInput(1, tgt)
    if "pack" in params:
        cp.parm("pack").set(bool(params["pack"]))
    # Variant / piece matching: one attribute name matched on BOTH sides -- the source is split into
    # pieces by `id_attrib` and each target point receives only the piece whose value equals its own
    # `id_attrib` value (id-based multi-asset instancing: e.g. a `variant` attr picking among assets).
    if params.get("id_attrib"):
        p = cp.parm("useidattrib")
        if p is not None:
            p.set(1)
            cp.parm("idattrib").set(str(params["id_attrib"]))
    # Group restriction: copy onto only a named target point group / from a named source prim group.
    if params.get("target_group"):
        _try_set(cp, "targetgroup", str(params["target_group"]))
    if params.get("source_group"):
        _try_set(cp, "sourcegroup", str(params["source_group"]))
    # Carry NON-transform target point attributes (Cd colour by default; custom via `target_attribs`)
    # onto the copies. N/up/pscale/orient are always consumed as transforms; other attrs need the
    # "Attributes from Target" multiparm. ORDER IS LOAD-BEARING: the row's instance parms
    # (applyattribs1/useapply1/...) do NOT exist until the row is created with targetattribs.set(1),
    # and an EMPTY applyattribs pattern silently matches nothing -- so create the row, THEN set a
    # NON-empty glob pattern. (Verified H21.0.671; an empty pattern is the silent no-op trap.)
    attribs = str(params.get("target_attribs", "Cd")).strip()
    if attribs:
        cp.parm("targetattribs").set(1)               # create row 1 -> instance parms materialize
        _try_set(cp, "applyattribs1", attribs)        # glob pattern (Cd | "Cd N" | *); empty = no-op
        _try_set(cp, "useapply1", 1)                  # enable this row (default already 1)
        _try_set(cp, "applyto1", 0)                   # 0=points 1=verts 2=prims
        _try_set(cp, "applymethod1", 0)               # 0=copy 1=none 2=mult 3=add 4=sub
    cp.moveToGoodPosition()
    result = advise({"node": cp.path(), "prims": len(_geo_or_raise(cp).prims())}, cp)
    result["magnitude"] = magnitude_advice("copy_to_points", params)
    return result


@endpoint("scatter")
def scatter(params):
    """Scatter points on the input surface (standalone Scatter 2.0). count clamped; relax optional."""
    governor_gate("scatter")  # advisory; refuses only in the catastrophic band
    n = child_after(params["input"], "scatter::2.0", params.get("name"))
    count = int(clamp(int(params.get("count", 1000)), 1, 10_000_000))
    _set_scatter_count(n, count)
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    # Density-driven scatter: bias where points land by a point float attribute (e.g. a heightfield
    # mask / occlusion / slope), with an optional global multiplier -- procedural placement control.
    if params.get("density_attrib"):
        _try_set(n, "usedensityattrib", True)
        _try_set(n, "densityattrib", str(params["density_attrib"]))
    if "density_scale" in params:
        _try_set(n, "densityscale", clamp(float(params["density_scale"]), 0.0, 1e6))
    if "relax_iterations" in params:
        _try_set(n, "relaxpoints", True)
        _try_set(n, "relaxiterations", int(clamp(int(params["relax_iterations"]), 0, 100)))
    g = _geo_or_raise(n)
    result = advise({"node": n.path(), "points": len(g.points())}, n)
    result["magnitude"] = magnitude_advice("scatter", params)
    return result


_PACK_LOD = ("full", "points", "box", "centroid", "hidden")


@endpoint("pack")
def pack(params):
    """Pack the input geometry into packed primitives (flat-memory lane). `pack_by_name` = one packed
    prim per unique name value; `viewportlod` (full|points|box|centroid|hidden) sets the packed
    viewport draw level to keep huge instance counts interactive."""
    n = child_after(params["input"], "pack", params.get("name"))
    if "pack_by_name" in params:
        _try_set(n, "packbyname", bool(params["pack_by_name"]))
    if params.get("transfer_attributes"):
        _try_set(n, "transfer_attributes", str(params["transfer_attributes"]))
    lod = params.get("viewportlod")
    if lod in _PACK_LOD:
        _menu_by_token(n, "viewportlod", lod)
    g = _geo_or_raise(n)
    return {"node": n.path(), "prims": len(g.prims())}


@endpoint("unpack")
def unpack(params):
    """Unpack packed primitives back to raw geometry."""
    n = child_after(params["input"], "unpack", params.get("name"))
    if params.get("transfer_attributes"):
        _try_set(n, "transfer_attributes", str(params["transfer_attributes"]))
    g = _geo_or_raise(n)
    return {"node": n.path(), "prims": len(g.prims())}


@endpoint("instance")
def instance(params):
    """Instance SOP: tag input points for deferred point-instancing / packed expansion at render
    time. `instance_attrib` = string point attribute holding the per-point geometry path to instance;
    `pack` outputs the expanded instances as packed prims."""
    n = child_after(params["input"], "instance", params.get("name"))
    if "pack" in params:
        _try_set(n, "packexpanded", bool(params["pack"]))
    if params.get("instance_attrib"):
        _try_set(n, "instanceattrib", str(params["instance_attrib"]))
    g = _geo_or_raise(n)
    return {"node": n.path(), "points": len(g.points())}


@endpoint("biome_scatter")
def biome_scatter(params):
    """Vegetation dressing via Labs Biome Plant Scatter (density/seed on the input terrain)."""
    n = child_after(params["input"], "labs::biome_plant_scatter::1.0", params.get("name"))
    if "density" in params:
        _try_set(n, "densitymultiplier", clamp(float(params["density"]), 0.0, 100.0))
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    if "spacing" in params:
        _try_set(n, "spacing", clamp(float(params["spacing"]), 0.01, 1e5))
    n.geometry()
    return {"node": n.path()}


def _menu_by_token(node, parm, token):
    """Set an ordered-menu parm by its live token (robust: reads menuItems() at runtime)."""
    p = node.parm(parm)
    if p is None:
        return None
    try:
        items = p.menuItems()
        if token in items:
            p.set(items.index(token))
            return token
    except Exception:
        pass
    return None


@endpoint("point_replicate")
def point_replicate(params):
    """Replicate N jittered points per input point (Point Replicate SOP) — fuller emission from sparse
    points (spray/mist), scatter-in-a-shape. input0 = the source points. `count` per point, `shape`
    (box|sphere|cylinder|cone|grid|circle|line), `size`, optional noise, and copy_attribs (+ optional
    attribstocopy list) to carry source attributes onto the replicas. BUILT (one cook)."""
    n = child_after(params["input"], "pointreplicate", params.get("name"))
    applied = {}
    if "count" in params:
        applied["count"] = _try_set(n, "nptsperpt", int(clamp(int(params["count"]), 1, 100000)))
    if "shape" in params:
        applied["shape"] = _menu_by_token(n, "shape", str(params["shape"]))
    if "size" in params:
        s = clamp(float(params["size"]), 0.0, 1e6)
        for ax in ("sizex", "sizey", "sizez"):
            _try_set(n, ax, s)
        applied["size"] = s
    if "noise" in params:
        applied["noise"] = _try_set(n, "donoise", bool(params["noise"]))
    if "seed" in params:
        applied["seed"] = _try_set(n, "seed", clamp(float(params["seed"]), 0.0, 1e7))
    if "copy_attribs" in params:
        applied["copy_attribs"] = _try_set(n, "docopyattribs", bool(params["copy_attribs"]))
    if params.get("attribstocopy"):
        applied["attribstocopy"] = _try_set(n, "attribstocopy", str(params["attribstocopy"]))
    g = _geo_or_raise(n)
    return {"node": n.path(), "points": len(g.points()), "applied": applied}

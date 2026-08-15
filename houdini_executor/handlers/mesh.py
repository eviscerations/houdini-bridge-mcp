"""Cleanup / mesh handlers. Params verified against live H21.0.671 nodes."""

import hou
from houdini_executor.server import endpoint, child_after, clamp, resolve_node, confined_path, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set

try:
    from houdini_executor.governor import governor_gate, advise, magnitude_advice
except Exception:  # noqa: BLE001 — governor is advisory telemetry; must never block handler import
    def governor_gate(op_label):  # fail-soft stub
        return {"band": "unknown"}

    def advise(result, node=None):  # fail-soft stub
        return result

    def magnitude_advice(op_label, params):  # fail-soft stub
        return {"level": "ok", "note": "governor unavailable"}






def _str_menu_set(node, parm, token, tokens):
    """Set a STRING-type menu parm by its token string directly (the token IS the stored value —
    unlike an ordered Menu parm, where the index is stored). Probe-safe."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _set_vec(node, parm, vec):
    """Set a vector parm-tuple probe-safely (skips if the parm/len doesn't match)."""
    t = node.parmTuple(parm)
    if t is None:
        return False
    try:
        vals = tuple(float(x) for x in vec)
        if len(vals) != len(t):
            return False
        t.set(vals)
        return True
    except Exception:
        return False


# ── VOLUME lane Phase 2 (T1/T2/T4/T5 build+convert depth) — all live-probed on H21.0.671.
# PROBE CORRECTIONS baked in (correcting earlier guesses):
#   • convertvdb.conversion menu is (volume:0, vdb:1, poly:2, polysoup:3) — there is NO "points" target
#     (the old target_map {points:0} silently selected Volume — a latent bug). Fixed to real tokens.
#   • convertvdb.vdbprecision tokens are "32"/"64" (STRING menu), NOT the spec's float/half. vdbtype is
#     a STRING menu (none/float/int/bool/vec3f/vec3i). vdbclass is an ordered Menu (none/sdf/fog=idx).
#   • isooffset.output tokens are isosurface/fogvolume/sdfvolume/tetramesh (spec said tetra/fog/sdf).
#     isooffset has its OWN internal `mode` (the sampling method) which collides with the handler-level
#     `mode` switch → exposed as `sample_mode`. `uniformsamples` is a Menu (axis selector), and the
#     actual sample count is the Int `samplediv`.
#   • VDB builders' attribute-transfer multiparm count parm = `numattrib` (MultiparmBlock; .set(N)
#     spawns attribute1..N / attributevdbname1..N / vectype1..N instances).
#   • vdbfromparticles velocity: footprint Menu (sphere/trail); velscale/velspace are Floats. buildmask
#     + maskname write the mask VDB. bandwidth (world) + bandwidthvoxels both exist. vdbfromparticlefluid
#     EXISTS (FLIP particles->surface VDB) with a distinct parm set (particlesep/influenceradius/…).
_CONVERTVDB_TARGET = {"volume": 0, "vdb": 1, "polygons": 2, "poly": 2, "polysoup": 3}  # conversion (Menu=idx)
_CONVERTVDB_CLASS = ("none", "sdf", "fog")                                 # vdbclass (Menu=idx)
_CONVERTVDB_TYPE = ("none", "float", "int", "bool", "vec3f", "vec3i")      # vdbtype (STRING menu)
_CONVERTVDB_PRECISION = ("none", "32", "64")                               # vdbprecision (STRING menu)
_ISOOFFSET_OUTPUT = ("isosurface", "fogvolume", "sdfvolume", "tetramesh")  # output (Menu=idx)
_ISOOFFSET_SAMPLE_MODE = ("rayintersect", "metafield", "minimum", "pointcloud", "implicitbox",
                          "implicitsphere", "implicitplane", "volume", "volumerebuild")  # mode (Menu=idx)
_ISOOFFSET_UNIFORMSAMPLES = ("nonsquare", "x", "y", "z", "max", "size")    # uniformsamples (Menu=idx)
_CONVERT_TOTYPE = {"polygons": 0, "poly": 0, "vdb": 13, "volume": 12}      # convert.totype (Menu=idx)
_VDBBUILD_VECTYPE = ("invariant", "covariant", "covariant normalize",
                     "contravariant relative", "contravariant absolute")   # vectype# (Menu=idx)
_VDBFROMPARTICLES_FOOTPRINT = ("sphere", "trail")                          # footprint (Menu=idx)


def _set_attrib_transfer(node, attrs):
    """Wire point-attribute -> VDB transfer via the `numattrib` MultiparmBlock (probe-safe).
    `attrs` is a list of names OR a comma/space-separated string; sets numattrib=len then
    attribute{i} per instance."""
    p = node.parm("numattrib")
    if p is None:
        return False
    if isinstance(attrs, str):
        attrs = [a for a in attrs.replace(",", " ").split() if a]
    if not isinstance(attrs, (list, tuple)):
        return False
    names = [str(a) for a in attrs if str(a)]
    try:
        p.set(len(names))
    except Exception:
        return False
    for i, nm in enumerate(names, start=1):
        _try_set(node, "attribute%d" % i, nm)
    return True


_REMESH_SIZING = ("uniform", "adaptive")  # sizing (ordered Menu = index; live-probed remesh::2.0)


@endpoint("remesh")
def remesh(params):
    """Even-triangulation remesh (remesh::2.0). targetsize = target edge length (world units).
    sizing (uniform|adaptive) + density drive adaptive sizing; smoothing/iterations relax the mesh;
    min_edge/max_edge clamp the produced edge length; gradation biases uniform<->adaptive. Feature
    preservation via hard_edges/hard_points/harden_uv_seams. Live-probed ranges."""
    governor_gate("remesh")  # advisory; refuses only in the catastrophic band
    n = child_after(params["input"], "remesh::2.0", params.get("name"))
    if "targetsize" in params:
        n.parm("targetsize").set(clamp(float(params["targetsize"]), 1e-4, 1e6))
    if "iterations" in params:
        n.parm("iterations").set(int(clamp(int(params["iterations"]), 0, 50)))
    if "sizing" in params:
        _menu_set(n, "sizing", str(params["sizing"]), _REMESH_SIZING)
    if "density" in params:  # adaptive target-density multiplier (node range 1..10 soft)
        _try_set(n, "density", clamp(float(params["density"]), 1.0, 10.0))
    if "smoothing" in params:  # per-pass point relaxation (node 0..1)
        _try_set(n, "smoothing", clamp(float(params["smoothing"]), 0.0, 1.0))
    if "min_edge" in params:  # gate + value (useminsize/minsize)
        _try_set(n, "useminsize", True)
        _try_set(n, "minsize", clamp(float(params["min_edge"]), 0.0, 1e6))
    if "max_edge" in params:  # gate + value (usemaxsize/maxsize)
        _try_set(n, "usemaxsize", True)
        _try_set(n, "maxsize", clamp(float(params["max_edge"]), 0.0, 1e6))
    # feature/attribute preservation (verified: adaptivity control is `gradation`, NOT `adaptivity`).
    if "gradation" in params:
        _try_set(n, "gradation", clamp(float(params["gradation"]), 0.0, 1.0))
    if params.get("hard_edges"):
        _try_set(n, "hard_edges", str(params["hard_edges"]))
    if params.get("hard_points"):
        _try_set(n, "hard_points", str(params["hard_points"]))
    if "harden_uv_seams" in params:
        _try_set(n, "hardenuvseams", bool(params["harden_uv_seams"]))
        if params.get("uv_attrib"):
            _try_set(n, "uvattriv", str(params["uv_attrib"]))
    g = n.geometry()
    result = advise({"node": n.path(), "prims": len(g.prims())}, n)
    result["magnitude"] = magnitude_advice("remesh", params)
    return result


_POLYREDUCE_TARGET = ("poly_percent", "pt_percent", "poly_count", "pt_count")  # target (Menu=idx; live-probed)


@endpoint("polyreduce")
def polyreduce(params):
    """Decimate to a percentage (or absolute count) of the input polycount (LOD). target selects the
    reduction target (poly_percent/pt_percent -> percentage; poly_count/pt_count -> finalcount).
    qualitytolerance trades quality for speed. Live-probed parm names/ranges."""
    n = child_after(params["input"], "polyreduce::2.0", params.get("name"))
    if "target" in params:
        _menu_set(n, "target", str(params["target"]), _POLYREDUCE_TARGET)
    if "percentage" in params:
        n.parm("percentage").set(clamp(float(params["percentage"]), 0.1, 100.0))
    if "finalcount" in params:  # absolute poly/point-count target
        _try_set(n, "finalcount", int(clamp(int(params["finalcount"]), 1, 100_000_000)))
    if "qualitytolerance" in params:
        _try_set(n, "qualitytolerance", clamp(float(params["qualitytolerance"]), 0.0, 1.0))
    # preservation — keep scan borders / quads / UV seams intact during decimation (verified names).
    if "preserve_quads" in params:
        _try_set(n, "preservequads", bool(params["preserve_quads"]))
    if params.get("hard_edges"):
        _try_set(n, "hardfeatureedges", str(params["hard_edges"]))
    if params.get("hard_points"):
        _try_set(n, "hardfeaturepoints", str(params["hard_points"]))
    if "boundary_weight" in params:
        _try_set(n, "boundaryweight", clamp(float(params["boundary_weight"]), 0.0, 1e4))
    if "seam_weight" in params:
        _try_set(n, "vattribseamweight", clamp(float(params["seam_weight"]), 0.0, 1e4))
    if params.get("retain_attrib"):
        _try_set(n, "useretainattrib", True)
        _try_set(n, "retainattrib", str(params["retain_attrib"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims())}


@endpoint("vdb_from_particles")
def vdb_from_particles(params):
    """Points/particles -> VDB. `op=particles` (default, vdbfromparticles) builds SDF/fog/mask/velocity
    grids; `op=fluid` (vdbfromparticlefluid) surfaces FLIP particles into a fluid-density VDB.

    op=particles: voxelsize, radiusscale, minvoxelradius, builddistance(SDF)+distancename,
      buildfog+fogname, buildmask+maskname+maskwidth, useworldspaceunits, bandwidth (world) /
      bandwidthvoxels, prune, footprint (sphere|trail), velscale/velspace (velocity trail),
      attributes [names] (point attribs -> VDBs via the numattrib multiparm).
    op=fluid: voxelsize, particlesep, influenceradius, surfacedistance, bandwidthvoxels, outputname,
      resamplingiterations, rebuildsdf. BUILT (one cook)."""
    op = str(params.get("op", "particles"))
    applied = {}
    if op == "fluid":
        n = child_after(params["input"], "vdbfromparticlefluid", params.get("name"))
        if "voxelsize" in params:
            applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e5))
        if "particlesep" in params:
            applied["particlesep"] = _try_set(n, "particlesep", clamp(float(params["particlesep"]), 1e-4, 1e5))
        if "influenceradius" in params:
            applied["influenceradius"] = _try_set(n, "influenceradius", clamp(float(params["influenceradius"]), 0.0, 1e5))
        if "surfacedistance" in params:
            applied["surfacedistance"] = _try_set(n, "surfacedistance", clamp(float(params["surfacedistance"]), 0.0, 1e5))
        if "bandwidthvoxels" in params:
            applied["bandwidthvoxels"] = _try_set(n, "bandwidthvoxels", clamp(float(params["bandwidthvoxels"]), 0.0, 1e4))
        if "outputname" in params:
            applied["outputname"] = _try_set(n, "outputname", str(params["outputname"]))
        if "resamplingiterations" in params:
            applied["resamplingiterations"] = _try_set(n, "resamplingiterations", int(clamp(int(params["resamplingiterations"]), 0, 50)))
        if "rebuildsdf" in params:
            applied["rebuildsdf"] = _try_set(n, "rebuildsdf", bool(params["rebuildsdf"]))
        n.geometry()
        return {"node": n.path(), "op": op, "applied": applied}
    if op != "particles":
        raise ValueError("op must be particles|fluid")
    n = child_after(params["input"], "vdbfromparticles", params.get("name"))
    if "voxelsize" in params:
        applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e5))
    if "radiusscale" in params:
        applied["radiusscale"] = _try_set(n, "radiusscale", clamp(float(params["radiusscale"]), 0.01, 100.0))
    if "minvoxelradius" in params:
        applied["minvoxelradius"] = _try_set(n, "minvoxelradius", clamp(float(params["minvoxelradius"]), 0.0, 1e4))
    if "builddistance" in params:
        applied["builddistance"] = _try_set(n, "builddistance", bool(params["builddistance"]))
    if "distancename" in params:
        applied["distancename"] = _try_set(n, "distancename", str(params["distancename"]))
    if "buildfog" in params:
        applied["buildfog"] = _try_set(n, "buildfog", bool(params["buildfog"]))
    if "fogname" in params:
        applied["fogname"] = _try_set(n, "fogname", str(params["fogname"]))
    if "buildmask" in params:
        applied["buildmask"] = _try_set(n, "buildmask", bool(params["buildmask"]))
    if "maskname" in params:
        applied["maskname"] = _try_set(n, "maskname", str(params["maskname"]))
    if "maskwidth" in params:
        applied["maskwidth"] = _try_set(n, "maskwidth", clamp(float(params["maskwidth"]), 0.0, 1e4))
    if "useworldspaceunits" in params:
        applied["useworldspaceunits"] = _try_set(n, "useworldspaceunits", bool(params["useworldspaceunits"]))
    if "bandwidth" in params:
        applied["bandwidth"] = _try_set(n, "bandwidth", clamp(float(params["bandwidth"]), 0.0, 1e5))
    if "bandwidthvoxels" in params:
        applied["bandwidthvoxels"] = _try_set(n, "bandwidthvoxels", clamp(float(params["bandwidthvoxels"]), 0.0, 1e4))
    if "prune" in params:
        applied["prune"] = _try_set(n, "prune", bool(params["prune"]))
    if "footprint" in params:
        applied["footprint"] = _menu_set(n, "footprint", str(params["footprint"]), _VDBFROMPARTICLES_FOOTPRINT)
    if "velscale" in params:
        applied["velscale"] = _try_set(n, "velscale", clamp(float(params["velscale"]), 0.0, 1e6))
    if "velspace" in params:
        applied["velspace"] = _try_set(n, "velspace", clamp(float(params["velspace"]), 0.0, 1e6))
    if "attributes" in params:
        applied["attributes"] = _set_attrib_transfer(n, params["attributes"])
    n.geometry()
    return {"node": n.path(), "op": op, "applied": applied}


_FUSE_SNAPTYPE = ("distancesnap", "gridsnap", "specified")  # snaptype (Menu=idx; live-probed fuse::2.0)


@endpoint("fuse")
def fuse(params):
    """Weld / snap coincident points (seam cleanup after tiling). distance = 3D snap tolerance
    (world; auto-enables usetol3d). snap_type selects the snapping method; delete_degenerate /
    delete_unused / consolidate clean up after welding. Live-probed parm names/ranges."""
    n = child_after(params["input"], "fuse::2.0", params.get("name"))
    if "distance" in params:  # snap tolerance (gate + value)
        _try_set(n, "usetol3d", True)
        _try_set(n, "tol3d", clamp(float(params["distance"]), 0.0, 1e3))
    if "snap_type" in params:
        _menu_set(n, "snaptype", str(params["snap_type"]), _FUSE_SNAPTYPE)
    if "delete_degenerate" in params:
        _try_set(n, "deldegen", bool(params["delete_degenerate"]))
    if "delete_unused" in params:
        _try_set(n, "delunusedpoints", bool(params["delete_unused"]))
    if "consolidate" in params:
        _try_set(n, "consolidatesnappedpoints", bool(params["consolidate"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points())}


_POLYDOCTOR_ACTION = ("ignore", "mark", "repair")  # per-defect Menu (idx; live-probed polydoctor)


@endpoint("polydoctor")
def polydoctor(params):
    """Diagnose and repair non-manifold / ill-formed polygons. Toggles/menus are opt-in. Per-defect
    handling (repair_nonmanifold/repair_intersections) is ignore|mark|repair; smallmanifoldsize gates
    the tiny-shell delete; max_passes caps the repair loop. Live-probed parm names/ranges."""
    n = child_after(params["input"], "polydoctor", params.get("name"))
    if "repair_windings" in params:
        _try_set(n, "fixwindings", bool(params["repair_windings"]))
    if "delete_small_manifolds" in params:
        _try_set(n, "deletesmallmanifolds", bool(params["delete_small_manifolds"]))
    if "smallmanifoldsize" in params:
        _try_set(n, "smallmanifoldsize", int(clamp(int(params["smallmanifoldsize"]), 0, 1000)))
    if "repair_nonmanifold" in params:
        _menu_set(n, "nonmanifoldpt", str(params["repair_nonmanifold"]), _POLYDOCTOR_ACTION)
    if "repair_intersections" in params:
        _menu_set(n, "intersect", str(params["repair_intersections"]), _POLYDOCTOR_ACTION)
    if "max_passes" in params:
        _try_set(n, "maxpasses", int(clamp(int(params["max_passes"]), 1, 100)))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims())}


_POLYFILL_MODE = ("none", "tris", "trifan", "quadfan", "quads", "gridquads")  # fillmode (Menu=idx; live-probed)


@endpoint("polyfill")
def polyfill(params):
    """Fill holes (LIDAR/scan dropouts) with patch polygons; fillmode picks the patch topology.
    Optional smoothing of the patch. smoothstrength is a 0..50 parm (default 50) —
    the old 0..1 clamp silently capped it at 1. tangent_strength (0..2) sets border-tangent follow;
    patch_group tags the created patch polys. Live-probed parm names/ranges."""
    n = child_after(params["input"], "polyfill", params.get("name"))
    if "fillmode" in params:
        _menu_set(n, "fillmode", str(params["fillmode"]), _POLYFILL_MODE)
    if params.get("smooth"):
        _try_set(n, "smoothtoggle", True)
        if "smooth_strength" in params:
            _try_set(n, "smoothstrength", clamp(float(params["smooth_strength"]), 0.0, 50.0))
    if "tangent_strength" in params:
        _try_set(n, "tangentstrength", clamp(float(params["tangent_strength"]), 0.0, 2.0))
    # corner_offset rotates which corners the Quadrilateral-Grid fill assigns — controls grid quality
    # / alignment of a quads patch (the fillmode='gridquads' quad routing over an N-gon hole).
    if "corner_offset" in params:
        _try_set(n, "corneroffset", int(params["corner_offset"]))
    if params.get("patch_group"):
        _try_set(n, "patchgrouptoggle", True)
        _try_set(n, "patchgroup", str(params["patch_group"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims())}


@endpoint("normals")
def normals(params):
    """Recompute (or reverse) normals via the Normal SOP. mode: point|vertex|prim|detail (node `type`
    menu index, verified). cusp_angle in degrees. reverse flips direction; normalize forces unit
    length; weighting = adjacent-face averaging method (node `method` 0..2). Live-probed."""
    n = child_after(params["input"], "normal", params.get("name"))
    mode_map = {"point": 0, "vertex": 1, "prim": 2, "detail": 3}
    if params.get("mode") in mode_map:
        _try_set(n, "type", mode_map[params["mode"]])
    if "cusp_angle" in params:
        _try_set(n, "cuspangle", clamp(float(params["cusp_angle"]), 0.0, 180.0))
    if "reverse" in params:
        _try_set(n, "reverse", bool(params["reverse"]))
    if "normalize" in params:
        _try_set(n, "normalize", bool(params["normalize"]))
    if "weighting" in params:
        _try_set(n, "method", int(clamp(int(params["weighting"]), 0, 2)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points())}


_FSS_OPS = {"facet": "facet", "smooth": "smooth::2.0", "subdivide": "subdivide"}
_SMOOTH_METHOD = ("uniform", "scaledominant", "curvaturedominant")           # smooth::2.0 method (Menu=idx)
_SUBDIV_ALGO = ("houdini", "mantra", "osdcc", "osdloop", "osdbilinear")      # subdivide algorithm (Menu=idx)
_SUBDIV_CLOSEHOLES = ("noclose", "pull", "stitch")                          # subdivide closeholes (Menu=idx)


@endpoint("facet_smooth_subdiv")
def facet_smooth_subdiv(params):
    """One of facet | smooth | subdivide via `op`. facet: cusp_angle + unique_points/make_planar.
    smooth: strength (node 0..50, NOT 0..1000) + method + filter_quality. subdivide: iterations
    (each level ~4x polys — node soft-max 3; capped at 6 here) + algorithm + close_holes. Live-probed
    ranges/menus."""
    op = str(params.get("op", "smooth"))
    if op not in _FSS_OPS:
        raise ValueError("op must be facet|smooth|subdivide")
    governor_gate("facet_smooth_subdiv")  # advisory; refuses only in the catastrophic band
    n = child_after(params["input"], _FSS_OPS[op], params.get("name"))
    if op == "facet":
        if "cusp_angle" in params:
            _try_set(n, "cusp", True)
            _try_set(n, "angle", clamp(float(params["cusp_angle"]), 0.0, 180.0))
        if "unique_points" in params:
            _try_set(n, "unique", bool(params["unique_points"]))
        if "make_planar" in params:
            _try_set(n, "mkplanar", bool(params["make_planar"]))
    elif op == "smooth":
        if "strength" in params:  # node range 0..50 (soft), default 10
            _try_set(n, "strength", clamp(float(params["strength"]), 0.0, 50.0))
        if "method" in params:
            _menu_set(n, "method", str(params["method"]), _SMOOTH_METHOD)
        if "filter_quality" in params:
            _try_set(n, "filterquality", int(clamp(int(params["filter_quality"]), 1, 5)))
    else:  # subdivide — 4^n polycount growth; node soft-max 3, capped at 6 here
        if "iterations" in params:
            _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 6)))
        if "algorithm" in params:
            _menu_set(n, "algorithm", str(params["algorithm"]), _SUBDIV_ALGO)
        if "close_holes" in params:
            _menu_set(n, "closeholes", str(params["close_holes"]), _SUBDIV_CLOSEHOLES)
    g = n.geometry()
    result = advise({"node": n.path(), "op": op, "prims": len(g.prims())}, n)
    result["magnitude"] = magnitude_advice("facet_smooth_subdiv", params)
    return result


_REPAIR_OPS = {
    "repair": "labs::repair",
    "delete_small_parts": "labs::delete_small_parts",
    "clean_seams": "labs::clean_seams::1.0",
    "fast_remesh": "labs::fast_remesh::1.1",
}


_REPAIR_FILLMODE = ("none", "tris", "trifan", "quadfan", "quads", "gridquads")  # labs::repair fillmode (Menu=idx)
_DSP_MODE = ("perimeter", "area")                                             # labs::delete_small_parts mode (Menu=idx)


@endpoint("mesh_repair")
def mesh_repair(params):
    """Labs repair toolkit via `op`: repair | delete_small_parts | clean_seams | fast_remesh.
    repair: fillmode (hole-patch topology) + iterations. delete_small_parts: threshold + mode
    (perimeter|area) + extract_largest (keep only the biggest piece). fast_remesh: target_polycount
    (output size) + iterations. Live-probed parm names/ranges."""
    op = str(params.get("op", "repair"))
    if op not in _REPAIR_OPS:
        raise ValueError("op must be repair|delete_small_parts|clean_seams|fast_remesh")
    n = child_after(params["input"], _REPAIR_OPS[op], params.get("name"))
    if op == "delete_small_parts":
        if "threshold" in params:
            _try_set(n, "threshold", clamp(float(params["threshold"]), 0.0, 1e9))
        if "mode" in params:
            _menu_set(n, "mode", str(params["mode"]), _DSP_MODE)
        if "extract_largest" in params:
            _try_set(n, "extractlargest", bool(params["extract_largest"]))
    elif op == "repair":
        if "fillmode" in params:
            _menu_set(n, "fillmode", str(params["fillmode"]), _REPAIR_FILLMODE)
        if "iterations" in params:
            _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 100)))
    elif op == "fast_remesh":
        if "target_polycount" in params:
            _try_set(n, "targetpolycount", int(clamp(int(params["target_polycount"]), 0, 2_000_000)))
        if "iterations" in params:
            _try_set(n, "remeshiterations", int(clamp(int(params["iterations"]), 0, 50)))
    g = n.geometry()
    return {"node": n.path(), "op": op, "prims": len(g.prims())}


# pack/file SOP viewport-LOD token set (live-probed H21.0.671, ordered menu = index-set).
_VIEWPORTLOD = ("full", "points", "box", "centroid", "hidden")
_PACK_PIVOT = ("origin", "centroid")  # pack.pivot (Menu=idx; live-probed)


@endpoint("lod_create")
def lod_create(params):
    """Level-of-detail / packed-primitive staging via `op` (default 'lod' = back-compat):
      lod (labs::lod_create): a LOD chain. `levels` = number of LODs (1..8).
      pack (pack SOP): pack the input into packed primitives (flat memory). `packbyname` (bool),
        `transfer_attributes` (space-separated attrib patterns), optional `lod` viewport-LOD token.
      proxy (pack SOP): stage heavy geo as a cheap viewport proxy — sets packed-prim `viewportlod`
        = `lod` token (full|points|box|centroid|hidden; default box), the general-geometry analog of
        the terrain-tile set_tile_lod. `packbyname`/`transfer_attributes` also honored."""
    op = str(params.get("op", "lod"))
    if op == "lod":
        n = child_after(params["input"], "labs::lod_create", params.get("name"))
        if "levels" in params:
            _try_set(n, "lods", int(clamp(int(params["levels"]), 1, 8)))
        n.geometry()
        return {"node": n.path(), "op": op}
    if op in ("pack", "proxy"):
        n = child_after(params["input"], "pack", params.get("name"))
        if "packbyname" in params:
            _try_set(n, "packbyname", bool(params["packbyname"]))
        if params.get("transfer_attributes"):
            _try_set(n, "transfer_attributes", str(params["transfer_attributes"]))
        if params.get("transfer_groups"):
            _try_set(n, "transfer_groups", str(params["transfer_groups"]))
        if "pivot" in params:
            _menu_set(n, "pivot", str(params["pivot"]), _PACK_PIVOT)
        lod = params.get("lod")
        if op == "proxy" and lod is None:
            lod = "box"
        applied_lod = None
        if lod is not None and _menu_set(n, "viewportlod", str(lod), _VIEWPORTLOD):
            applied_lod = str(lod)
        n.geometry()
        return {"node": n.path(), "op": op, "lod": applied_lod}
    raise ValueError("op must be lod|pack|proxy")


@endpoint("vdb_from_polygons")
def vdb_from_polygons(params):
    """Polygons -> VDB (round-trip meshing / collision / atmospherics). Builds an SDF and/or fog grid
    with narrow-band control and optional point-attribute transfer. Params: voxelsize,
    builddistance(SDF)+distancename, buildfog(fog)+fogname, useworldspaceunits, exteriorbandvoxels/
    interiorbandvoxels (voxel-unit bands) or exteriorband/interiorband (world-unit bands, with
    useworldspaceunits), fill_interior/fillinterior, unsigneddist, preserveholes, attributes [names]
    (point attribs -> VDBs via the numattrib multiparm). BUILT (one cook)."""
    governor_gate("vdb_from_polygons")  # advisory; refuses only in the catastrophic band
    n = child_after(params["input"], "vdbfrompolygons", params.get("name"))
    applied = {}
    if "voxelsize" in params:
        applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e5))
    if "builddistance" in params:
        applied["builddistance"] = _try_set(n, "builddistance", bool(params["builddistance"]))
    if "distancename" in params:
        applied["distancename"] = _try_set(n, "distancename", str(params["distancename"]))
    if "buildfog" in params:
        applied["buildfog"] = _try_set(n, "buildfog", bool(params["buildfog"]))
    if "fogname" in params:
        applied["fogname"] = _try_set(n, "fogname", str(params["fogname"]))
    if "useworldspaceunits" in params:
        applied["useworldspaceunits"] = _try_set(n, "useworldspaceunits", bool(params["useworldspaceunits"]))
    if "exteriorbandvoxels" in params:
        applied["exteriorbandvoxels"] = _try_set(n, "exteriorbandvoxels", int(clamp(int(params["exteriorbandvoxels"]), 1, 100000)))
    if "interiorbandvoxels" in params:
        applied["interiorbandvoxels"] = _try_set(n, "interiorbandvoxels", int(clamp(int(params["interiorbandvoxels"]), 1, 100000)))
    if "exteriorband" in params:
        applied["exteriorband"] = _try_set(n, "exteriorband", clamp(float(params["exteriorband"]), 0.0, 1e6))
    if "interiorband" in params:
        applied["interiorband"] = _try_set(n, "interiorband", clamp(float(params["interiorband"]), 0.0, 1e6))
    # fill_interior (legacy) and fillinterior both accepted
    if "fill_interior" in params:
        applied["fillinterior"] = _try_set(n, "fillinterior", bool(params["fill_interior"]))
    if "fillinterior" in params:
        applied["fillinterior"] = _try_set(n, "fillinterior", bool(params["fillinterior"]))
    if "unsigneddist" in params:
        applied["unsigneddist"] = _try_set(n, "unsigneddist", bool(params["unsigneddist"]))
    if "preserveholes" in params:
        applied["preserveholes"] = _try_set(n, "preserveholes", bool(params["preserveholes"]))
    if "attributes" in params:
        applied["attributes"] = _set_attrib_transfer(n, params["attributes"])
    n.geometry()
    result = advise({"node": n.path(), "applied": applied}, n)
    result["magnitude"] = magnitude_advice("vdb_from_polygons", params)
    return result


@endpoint("vdb_convert")
def vdb_convert(params):
    """Convert VDB (the round-trip hub) via `target`: polygons | polysoup | vdb | volume (native).
    NOTE: convertvdb has NO points target (the old {points:0} silently selected Volume — removed).
    Adds SDF<->fog reclass, precision/type change, iso control, attribute transfer and feature
    sharpening. Params: target, adaptivity, iso (SDF isovalue) / fogisovalue, vdbclass (none|sdf|fog:
    convert fog->SDF or SDF->fog), vdbtype (none|float|int|bool|vec3f|vec3i), vdbprecision (none|32|64),
    computenormals, transferattributes, sharpenfeatures+edgetolerance (need input_b reference surface),
    prune, splitdisjointvolumes, input_b (optional reference surface on input1). BUILT (one cook)."""
    n = child_after(params["input"], "convertvdb", params.get("name"))
    applied = {}
    if params.get("input_b"):
        bridge_input(n, params["input_b"], index=1, name_hint="input_b")
        applied["reference_input"] = True
    tgt = params.get("target")
    if tgt in _CONVERTVDB_TARGET:
        applied["target"] = _try_set(n, "conversion", _CONVERTVDB_TARGET[tgt])
    if "adaptivity" in params:
        applied["adaptivity"] = _try_set(n, "adaptivity", clamp(float(params["adaptivity"]), 0.0, 1.0))
    if "iso" in params:
        applied["isovalue"] = _try_set(n, "isovalue", clamp(float(params["iso"]), -1e6, 1e6))
    if "fogisovalue" in params:
        applied["fogisovalue"] = _try_set(n, "fogisovalue", clamp(float(params["fogisovalue"]), -1e6, 1e6))
    if "vdbclass" in params:
        applied["vdbclass"] = _menu_set(n, "vdbclass", str(params["vdbclass"]), _CONVERTVDB_CLASS)
    if "vdbtype" in params:
        applied["vdbtype"] = _str_menu_set(n, "vdbtype", str(params["vdbtype"]), _CONVERTVDB_TYPE)
    if "vdbprecision" in params:
        applied["vdbprecision"] = _str_menu_set(n, "vdbprecision", str(params["vdbprecision"]), _CONVERTVDB_PRECISION)
    if "computenormals" in params:
        applied["computenormals"] = _try_set(n, "computenormals", bool(params["computenormals"]))
    if "transferattributes" in params:
        applied["transferattributes"] = _try_set(n, "transferattributes", bool(params["transferattributes"]))
    if "sharpenfeatures" in params:
        applied["sharpenfeatures"] = _try_set(n, "sharpenfeatures", bool(params["sharpenfeatures"]))
    if "edgetolerance" in params:
        applied["edgetolerance"] = _try_set(n, "edgetolerance", clamp(float(params["edgetolerance"]), 0.0, 1.0))
    if "prune" in params:
        applied["prune"] = _try_set(n, "prune", bool(params["prune"]))
    if "splitdisjointvolumes" in params:
        applied["splitdisjointvolumes"] = _try_set(n, "splitdisjointvolumes", bool(params["splitdisjointvolumes"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()), "applied": applied}


# ── VOLUME lane Phase 3 (T6 vdb_filter refactor / T3 volume_rasterize) — all live-probed on
# H21.0.671. PROBE CORRECTIONS baked in below (correcting several
# earlier guessed tokens/parms):
#   • vdb_filter loses `combine` entirely (CSG now lives in the separate `vdb_combine` tool). `smooth`
#     migrates from the shallow `vdbsmooth` to the SDF-aware `vdbsmoothsdf`; `vdbsmooth` is kept as a
#     distinct op `smoothfog` (fog/legacy smooth path). Existing callers passing op=smooth + iterations/
#     radius stay valid — both parms exist on vdbsmoothsdf (Int).
#   • vdbsmoothsdf.operation is a STRING menu; tokens = meanvalue/gaussian/medianvalue/meancurvature/
#     laplacianflow (spec said mean/gaussian/median/mean-curvature — only `gaussian` matched).
#   • vdbreshapesdf has NO `offset` parm (spec guessed one). The dilate/erode distance is `radius`
#     (Int voxels) / `radiusworld` (world, with useworldspaceunits) + `voxeloffset`. `accuracy`/`trim`
#     are STRING menus (tokens carry spaces: "upwind first"/"upwind second"/"hj weno").
#   • volumeblur.reduction is an ordered Menu (idx), default `average`(4); tokens = max/min/maxabs/
#     minabs/average/median/sum/sumabs/sumsquare/rms — there is NO `gaussian` token (spec wrong).
#   • vdbextrapolate.mode is a STRING menu: dilate/mask/convert/renormalize/fogext/sdfext. input1 =
#     mask VDB. convertorrenormalize/sweeps/dilate all present as spec'd; pattern is a STRING menu.
#   • volumerasterizepoints/particles both take Base Volume on input0 and Points/Particles on input1
#     (so `input` = base volume, `points`/`particles` = the point source wired to input1). There is NO
#     `destination` parm (destination = the input0 base volume defines resolution/transform).
#     compositing→`mergemethod` (Menu idx add/max/min/mul); displacement+amplitude→`enable_displace`+
#     `displace_amp`; noise/gain/bias→`enable_modulate`+`modulate_gain`+`modulate_bias`.
#   • volumerasterizeparticles attribute transfer = the `attribrules` MultiparmBlock (.set(N) spawns
#     attribute1..N / rule1..N); rule# is a Menu (idx) wavg/threshold/accumulated/stochastic (the
#     spec's method/accumulated/stochastic are rule tokens, not separate parms). `filter` is a plain
#     String (kernel name, default "gauss"), NOT a menu.
_VDBSMOOTHSDF_OP = ("meanvalue", "gaussian", "medianvalue", "meancurvature", "laplacianflow")  # operation (STRING menu)
_VDBSMOOTH_OP = ("mean", "gauss", "median")                              # operation (STRING menu, fog node)
_VDBRESHAPE_OP = ("dilate", "erode", "open", "close")                    # operation (STRING menu)
_SDF_ACCURACY = ("upwind first", "upwind second", "hj weno")             # accuracy (STRING menu)
_SDF_TRIM = ("none", "interior", "exterior", "all")                      # trim (STRING menu)
_VOLUMEBLUR_REDUCTION = ("max", "min", "maxabs", "minabs", "average", "median",
                         "sum", "sumabs", "sumsquare", "rms")            # reduction (Menu=idx)
_VOLUMEBLUR_BORDER = ("none", "constant", "repeat", "streak")            # bordertype (Menu=idx)
_VDBEXTRAPOLATE_MODE = ("dilate", "mask", "convert", "renormalize", "fogext", "sdfext")  # mode (STRING menu)
_VDBEXTRAPOLATE_PATTERN = ("NN6", "NN18", "NN26")                        # pattern (STRING menu)
_RASTERPOINTS_MERGE = ("add", "max", "min", "mul")                       # mergemethod (Menu=idx)
_RASTERPARTICLES_RULE = ("wavg", "threshold", "accumulated", "stochastic")  # rule# (Menu=idx)


def _set_raster_attribs(node, attrs, method=None):
    """Wire the volumerasterizeparticles `attribrules` MultiparmBlock (probe-safe): set the count then
    attribute{i} (name) and, if `method` is a valid rule token, rule{i} per instance."""
    p = node.parm("attribrules")
    if p is None:
        return False
    if isinstance(attrs, str):
        attrs = [a for a in attrs.replace(",", " ").split() if a]
    if not isinstance(attrs, (list, tuple)):
        return False
    names = [str(a) for a in attrs if str(a)]
    try:
        p.set(len(names))
    except Exception:
        return False
    for i, nm in enumerate(names, start=1):
        _try_set(node, "attribute%d" % i, nm)
        if method is not None:
            _menu_set(node, "rule%d" % i, str(method), _RASTERPARTICLES_RULE)
    return True


@endpoint("vdb_filter")
def vdb_filter(params):
    """Single-input field filter on a VDB / native volume via `op` — NO VEX. (CSG/two-input combine
    moved to the separate `vdb_combine` tool.)
      smooth -> vdbsmoothsdf: SDF-aware smoothing. operation (meanvalue|gaussian|medianvalue|
        meancurvature|laplacianflow), iterations, radius (voxels) / radiusworld (world, with
        useworldspaceunits), maskname, minmask/maxmask, invert, accuracy (upwind first|upwind second|
        hj weno), trim (none|interior|exterior|all). Optional VDB alpha mask on input1 (input_b).
      smoothfog -> vdbsmooth: the plain (fog/legacy) smoother. operation (mean|gauss|median),
        iterations, radius / worldradius (with worldunits), maskname, minmask/maxmask, invert.
      reshape -> vdbreshapesdf: SDF morphology. operation (dilate|erode|open|close). Distance is
        radius (voxels) / radiusworld (world, with useworldspaceunits) + voxeloffset (NO `offset`
        parm). iterations, accuracy, trim, maskname, minmask/maxmask, invert.
      renormalize -> vdbrenormalizesdf: restore a proper distance field. iterations, accuracy,
        assumeuniformscale, radius, voxeloffset, trim.
      blur -> volumeblur: native-fog blur. reduction (max|min|maxabs|minabs|average|median|sum|
        sumabs|sumsquare|rms), radius / voxelradius (with usevoxelradius), passes, bordertype
        (none|constant|repeat|streak).
      extrapolate -> vdbextrapolate: extend a field off its surface / fog<->sdf. mode (dilate|mask|
        convert|renormalize|fogext|sdfext), convertorrenormalize, sweeps, dilate, pattern (NN6|NN18|
        NN26). Optional mask VDB on input1 (input_b).
    BUILT (one cook)."""
    op = str(params.get("op", "smooth"))
    applied = {}
    if op == "smooth":
        n = child_after(params["input"], "vdbsmoothsdf", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
            applied["mask_input"] = True
        if "operation" in params:
            applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _VDBSMOOTHSDF_OP)
        if "iterations" in params:
            applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 10)))
        if "radius" in params:
            applied["radius"] = _try_set(n, "radius", int(clamp(int(params["radius"]), 1, 5)))
        if "useworldspaceunits" in params:
            applied["useworldspaceunits"] = _try_set(n, "useworldspaceunits", bool(params["useworldspaceunits"]))
        if "radiusworld" in params:
            applied["radiusworld"] = _try_set(n, "radiusworld", clamp(float(params["radiusworld"]), 1e-5, 1e5))
        if "maskname" in params:
            applied["maskname"] = _try_set(n, "maskname", str(params["maskname"]))
        if "minmask" in params:
            applied["minmask"] = _try_set(n, "minmask", clamp(float(params["minmask"]), 0.0, 1.0))
        if "maxmask" in params:
            applied["maxmask"] = _try_set(n, "maxmask", clamp(float(params["maxmask"]), 0.0, 1.0))
        if "invert" in params:
            applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
        if "accuracy" in params:
            applied["accuracy"] = _str_menu_set(n, "accuracy", str(params["accuracy"]), _SDF_ACCURACY)
        if "trim" in params:
            applied["trim"] = _str_menu_set(n, "trim", str(params["trim"]), _SDF_TRIM)
    elif op == "smoothfog":
        n = child_after(params["input"], "vdbsmooth", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
            applied["mask_input"] = True
        if "operation" in params:
            applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _VDBSMOOTH_OP)
        if "iterations" in params:
            applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 10)))
        if "radius" in params:
            applied["radius"] = _try_set(n, "radius", int(clamp(int(params["radius"]), 1, 5)))
        if "worldunits" in params:
            applied["worldunits"] = _try_set(n, "worldunits", bool(params["worldunits"]))
        if "worldradius" in params:
            applied["worldradius"] = _try_set(n, "worldradius", clamp(float(params["worldradius"]), 1e-5, 1e5))
        if "maskname" in params:
            applied["maskname"] = _try_set(n, "maskname", str(params["maskname"]))
        if "minmask" in params:
            applied["minmask"] = _try_set(n, "minmask", clamp(float(params["minmask"]), 0.0, 1.0))
        if "maxmask" in params:
            applied["maxmask"] = _try_set(n, "maxmask", clamp(float(params["maxmask"]), 0.0, 1.0))
        if "invert" in params:
            applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
    elif op == "reshape":
        n = child_after(params["input"], "vdbreshapesdf", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
            applied["mask_input"] = True
        if "operation" in params:
            applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _VDBRESHAPE_OP)
        if "iterations" in params:
            applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 10)))
        if "useworldspaceunits" in params:
            applied["useworldspaceunits"] = _try_set(n, "useworldspaceunits", bool(params["useworldspaceunits"]))
        if "radius" in params:
            applied["radius"] = _try_set(n, "radius", int(clamp(int(params["radius"]), 1, 5)))
        if "radiusworld" in params:
            applied["radiusworld"] = _try_set(n, "radiusworld", clamp(float(params["radiusworld"]), 1e-5, 1e5))
        if "voxeloffset" in params:
            applied["voxeloffset"] = _try_set(n, "voxeloffset", clamp(float(params["voxeloffset"]), 0.0, 10.0))
        if "accuracy" in params:
            applied["accuracy"] = _str_menu_set(n, "accuracy", str(params["accuracy"]), _SDF_ACCURACY)
        if "trim" in params:
            applied["trim"] = _str_menu_set(n, "trim", str(params["trim"]), _SDF_TRIM)
        if "maskname" in params:
            applied["maskname"] = _try_set(n, "maskname", str(params["maskname"]))
        if "minmask" in params:
            applied["minmask"] = _try_set(n, "minmask", clamp(float(params["minmask"]), 0.0, 1.0))
        if "maxmask" in params:
            applied["maxmask"] = _try_set(n, "maxmask", clamp(float(params["maxmask"]), 0.0, 1.0))
        if "invert" in params:
            applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
    elif op == "renormalize":
        n = child_after(params["input"], "vdbrenormalizesdf", params.get("name"))
        if "iterations" in params:
            applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 10)))
        if "accuracy" in params:
            applied["accuracy"] = _str_menu_set(n, "accuracy", str(params["accuracy"]), _SDF_ACCURACY)
        if "assumeuniformscale" in params:
            applied["assumeuniformscale"] = _try_set(n, "assumeuniformscale", bool(params["assumeuniformscale"]))
        if "radius" in params:
            applied["radius"] = _try_set(n, "radius", int(clamp(int(params["radius"]), 1, 5)))
        if "voxeloffset" in params:
            applied["voxeloffset"] = _try_set(n, "voxeloffset", clamp(float(params["voxeloffset"]), 0.0, 10.0))
        if "trim" in params:
            applied["trim"] = _str_menu_set(n, "trim", str(params["trim"]), _SDF_TRIM)
    elif op == "blur":
        n = child_after(params["input"], "volumeblur", params.get("name"))
        if "reduction" in params:
            applied["reduction"] = _menu_set(n, "reduction", str(params["reduction"]), _VOLUMEBLUR_REDUCTION)
        if "usevoxelradius" in params:
            applied["usevoxelradius"] = _try_set(n, "usevoxelradius", bool(params["usevoxelradius"]))
        if "radius" in params:
            applied["radius"] = _try_set(n, "radius", clamp(float(params["radius"]), 0.0, 1e5))
        if "voxelradius" in params:
            # voxelradius is a per-axis vec3 tuple (NOT a scalar) — broadcast a scalar to all 3.
            vr = params["voxelradius"]
            vr = [float(x) for x in vr] if isinstance(vr, (list, tuple)) else [float(vr)] * 3
            applied["voxelradius"] = _set_vec(n, "voxelradius", vr)
        if "passes" in params:
            applied["passes"] = _try_set(n, "passes", int(clamp(int(params["passes"]), 1, 5)))
        if "bordertype" in params:
            applied["bordertype"] = _menu_set(n, "bordertype", str(params["bordertype"]), _VOLUMEBLUR_BORDER)
    elif op == "extrapolate":
        n = child_after(params["input"], "vdbextrapolate", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
            applied["mask_input"] = True
        if "mode" in params:
            applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _VDBEXTRAPOLATE_MODE)
        if "convertorrenormalize" in params:
            applied["convertorrenormalize"] = _try_set(n, "convertorrenormalize", bool(params["convertorrenormalize"]))
        if "sweeps" in params:
            applied["sweeps"] = _try_set(n, "sweeps", int(clamp(int(params["sweeps"]), 1, 5)))
        if "dilate" in params:
            applied["dilate"] = _try_set(n, "dilate", int(clamp(int(params["dilate"]), 0, 10)))
        if "pattern" in params:
            applied["pattern"] = _str_menu_set(n, "pattern", str(params["pattern"]), _VDBEXTRAPOLATE_PATTERN)
    else:
        raise ValueError("op must be smooth|smoothfog|reshape|renormalize|blur|extrapolate")
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    n.geometry()
    return {"node": n.path(), "op": op, "applied": applied}


_VOLCOMBINE_OP = ("copy", "add", "sub", "mul", "div", "max", "min")
_VOLCOMBINE_ADJUST = ("none", "scale", "scaleadd", "scaleaddprocess")


@endpoint("volume_combine")
def volume_combine(params):
    """Combine named VOLUME fields carried on ONE input by an operation (volumecombine) —
    dest = op(dest, source) across volumes matched by NAME: add two density fields, multiply a mask
    into temperature, max two smoke sims, copy one field over another. Single input carrying the named
    volumes. `dest` = destination volume name (receives the result); `source` = source volume name;
    `operation` = copy | add | sub | mul | div | max | min. scale / add pre-adjust the source before
    the op; postscale scales the output; threshold / clamp_min / clamp_max post-process; create_missing
    makes the destination if absent. Distinct from vdb_combine (two VDB INPUTS A op B) — this is
    name-matched native-volume field math on one stream."""
    n = child_after(params["input"], "volumecombine", params.get("name"))
    if "dest" in params:
        _try_set(n, "dstvolume", str(params["dest"]))
    if "source" in params:
        _try_set(n, "srcvolume1", str(params["source"]))
    if "operation" in params:
        _menu_set(n, "combine1", str(params["operation"]), _VOLCOMBINE_OP)
    if "scale" in params or "add" in params:
        if "add" in params:
            _try_set(n, "adjust1", _VOLCOMBINE_ADJUST.index("scaleadd"))
            _try_set(n, "add1", float(params["add"]))
        else:
            _try_set(n, "adjust1", _VOLCOMBINE_ADJUST.index("scale"))
        if "scale" in params:
            _try_set(n, "scale1", float(params["scale"]))
    if "postscale" in params:
        _try_set(n, "postscale", float(params["postscale"]))
    if "threshold" in params:
        _try_set(n, "dothreshold", 1)
        _try_set(n, "threshold", float(params["threshold"]))
    if "clamp_min" in params:
        _try_set(n, "doclampmin", 1)
        _try_set(n, "clampmin", float(params["clamp_min"]))
    if "clamp_max" in params:
        _try_set(n, "doclampmax", 1)
        _try_set(n, "clampmax", float(params["clamp_max"]))
    if "create_missing" in params:
        _try_set(n, "createmissing", bool(params["create_missing"]))
    if "delete_source" in params:
        _try_set(n, "deletesource", bool(params["delete_source"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()) if g else 0}


@endpoint("volume_rasterize_attributes")
def volume_rasterize_attributes(params):
    """Rasterize point ATTRIBUTES into named fog VOLUMES (volumerasterizeattributes) — turn a point
    cloud carrying density / temperature / v / Cd into the matching volume FIELDS in ONE node (a pyro
    or smoke source, or baking a point sim into renderable volumes). Single input (the points to
    rasterize); each listed attribute becomes a volume named after it (v -> a vel.x/y/z vector volume).
    `attributes` = space-separated point-attribute names (e.g. 'density temperature v Cd'). voxel_size
    = resolution (cost driver); particle_scale = each point's footprint; filter = reconstruction kernel
    (e.g. gaussian); coverage_attrib + coverage_scale weight the accumulation; normalize divides by
    clamped coverage; velocity_blur smears each point along its `v` across the shutter. BUILT (one
    cook). Distinct from volume_rasterize (which needs a base volume + wraps the points/particles
    nodes) — this is the single-input attributes->fields path."""
    n = child_after(params["input"], "volumerasterizeattributes", params.get("name"))
    if "attributes" in params:
        _try_set(n, "attributes", str(params["attributes"]))
    if "group" in params:
        _try_set(n, "points", str(params["group"]))
    if "voxel_size" in params:
        _try_set(n, "voxelsize", clamp(float(params["voxel_size"]), 1e-5, 1e6))
    if "particle_scale" in params:
        _try_set(n, "particlescale", clamp(float(params["particle_scale"]), 0.0, 1e6))
    if "filter" in params:
        _try_set(n, "filter", str(params["filter"]))
    if "min_filter" in params:
        _try_set(n, "minfilter", clamp(float(params["min_filter"]), 0.0, 1e6))
    if "coverage_attrib" in params:
        _try_set(n, "densityattrib", str(params["coverage_attrib"]))
    if "coverage_scale" in params:
        _try_set(n, "densityscale", clamp(float(params["coverage_scale"]), 0.0, 1e6))
    if "normalize" in params:
        _try_set(n, "normalize", bool(params["normalize"]))
    if params.get("velocity_blur"):
        _try_set(n, "velocityblur", 1)
        if "shutter" in params:
            _try_set(n, "shutter", clamp(float(params["shutter"]), 0.0, 10.0))
        if "shutter_offset" in params:
            _try_set(n, "shutteroffset", clamp(float(params["shutter_offset"]), -10.0, 10.0))
        if "blur_samples" in params:
            _try_set(n, "blursamples", int(clamp(int(params["blur_samples"]), 1, 100)))
    g = n.geometry()
    vols = []
    if g is not None:
        for p in g.prims():
            if p.type() in (hou.primType.Volume, hou.primType.VDB):
                try:
                    vols.append(p.attribValue("name"))
                except Exception:
                    pass
    return {"node": n.path(), "prims": len(g.prims()) if g else 0, "volumes": sorted(set(vols))}


@endpoint("volume_rasterize")
def volume_rasterize(params):
    """Rasterize points/particles into a density/attribute FOG volume (distinct from an SDF build) via
    `op` — NO VEX. `input` = the Base Volume (input0; defines voxel resolution/transform); the point
    source is wired to input1:
      points -> volumerasterizepoints: `points` (node path -> input1). densityscale, mergemethod
        (add|max|min|mul), samples, seed, scalarattrib/vectorattrib/intattrib (attr names to
        rasterize), smoothfalloff, solidratio, exteriorpad; displacement: enable_displace +
        displace_amp + displace_elementsize; modulation/noise: enable_modulate + modulate_gain +
        modulate_bias + modulate_elementsize; rastergrp (point group).
      particles -> volumerasterizeparticles: `particles` (node path -> input1). filter (kernel name,
        e.g. gauss), densityattrib, densityscale, particlescale, minfilter, velocityblur + shutter +
        shutteroffset + blursamples, normalize; attributes [names] + method (wavg|threshold|
        accumulated|stochastic) via the attribrules multiparm; points (point group).
    BUILT (one cook)."""
    op = str(params.get("op", "points"))
    applied = {}
    if op == "points":
        n = child_after(params["input"], "volumerasterizepoints", params.get("name"))
        if params.get("points"):
            bridge_input(n, params["points"], index=1, name_hint="points")
            applied["points_input"] = True
        if "densityscale" in params:
            applied["densityscale"] = _try_set(n, "densityscale", clamp(float(params["densityscale"]), 0.0, 1e5))
        if "mergemethod" in params:
            applied["mergemethod"] = _menu_set(n, "mergemethod", str(params["mergemethod"]), _RASTERPOINTS_MERGE)
        if "samples" in params:
            applied["samples"] = _try_set(n, "samples", int(clamp(int(params["samples"]), 1, 10)))
        if "seed" in params:
            applied["seed"] = _try_set(n, "seed", clamp(float(params["seed"]), 0.0, 1e6))
        if "scalarattrib" in params:
            applied["scalarattrib"] = _try_set(n, "scalarattrib", str(params["scalarattrib"]))
        if "vectorattrib" in params:
            applied["vectorattrib"] = _try_set(n, "vectorattrib", str(params["vectorattrib"]))
        if "intattrib" in params:
            applied["intattrib"] = _try_set(n, "intattrib", str(params["intattrib"]))
        if "smoothfalloff" in params:
            applied["smoothfalloff"] = _try_set(n, "smoothfalloff", bool(params["smoothfalloff"]))
        if "solidratio" in params:
            applied["solidratio"] = _try_set(n, "solidratio", clamp(float(params["solidratio"]), 0.0, 1.0))
        if "exteriorpad" in params:
            applied["exteriorpad"] = _try_set(n, "exteriorpad", clamp(float(params["exteriorpad"]), 0.0, 1.0))
        if "enable_displace" in params:
            applied["enable_displace"] = _try_set(n, "enable_displace", bool(params["enable_displace"]))
        if "displace_amp" in params:
            applied["displace_amp"] = _try_set(n, "displace_amp", clamp(float(params["displace_amp"]), 0.0, 1e5))
        if "displace_elementsize" in params:
            applied["displace_elementsize"] = _try_set(n, "displace_elementsize", clamp(float(params["displace_elementsize"]), 0.0, 1e5))
        if "enable_modulate" in params:
            applied["enable_modulate"] = _try_set(n, "enable_modulate", bool(params["enable_modulate"]))
        if "modulate_gain" in params:
            applied["modulate_gain"] = _try_set(n, "modulate_gain", clamp(float(params["modulate_gain"]), 0.0, 1.0))
        if "modulate_bias" in params:
            applied["modulate_bias"] = _try_set(n, "modulate_bias", clamp(float(params["modulate_bias"]), 0.0, 1.0))
        if "modulate_elementsize" in params:
            applied["modulate_elementsize"] = _try_set(n, "modulate_elementsize", clamp(float(params["modulate_elementsize"]), 0.0, 1e5))
        if "rastergrp" in params:
            applied["rastergrp"] = _try_set(n, "rastergrp", str(params["rastergrp"]))
    elif op == "particles":
        n = child_after(params["input"], "volumerasterizeparticles", params.get("name"))
        if params.get("particles"):
            bridge_input(n, params["particles"], index=1, name_hint="particles")
            applied["particles_input"] = True
        if "filter" in params:
            applied["filter"] = _try_set(n, "filter", str(params["filter"]))
        if "densityattrib" in params:
            applied["densityattrib"] = _try_set(n, "densityattrib", str(params["densityattrib"]))
        if "densityscale" in params:
            applied["densityscale"] = _try_set(n, "densityscale", clamp(float(params["densityscale"]), 0.0, 1e5))
        if "particlescale" in params:
            applied["particlescale"] = _try_set(n, "particlescale", clamp(float(params["particlescale"]), 0.0, 1e5))
        if "minfilter" in params:
            applied["minfilter"] = _try_set(n, "minfilter", clamp(float(params["minfilter"]), 0.0, 1e5))
        if "velocityblur" in params:
            applied["velocityblur"] = _try_set(n, "velocityblur", bool(params["velocityblur"]))
        if "shutter" in params:
            applied["shutter"] = _try_set(n, "shutter", clamp(float(params["shutter"]), 0.0, 1.0))
        if "shutteroffset" in params:
            applied["shutteroffset"] = _try_set(n, "shutteroffset", clamp(float(params["shutteroffset"]), -1.0, 1.0))
        if "blursamples" in params:
            applied["blursamples"] = _try_set(n, "blursamples", int(clamp(int(params["blursamples"]), 1, 10)))
        if "normalize" in params:
            applied["normalize"] = _try_set(n, "normalize", bool(params["normalize"]))
        if "points" in params:
            applied["points"] = _try_set(n, "points", str(params["points"]))
        if "attributes" in params:
            applied["attributes"] = _set_raster_attribs(n, params["attributes"], params.get("method"))
    else:
        raise ValueError("op must be points|particles")
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    n.geometry()
    return {"node": n.path(), "op": op, "applied": applied}


@endpoint("convert_volume")
def convert_volume(params):
    """Native-volume lane via `mode`:
      isooffset -> isooffset: polys -> native Houdini volume/SDF/tetra. output (isosurface|fogvolume|
        sdfvolume|tetramesh), sample_mode (isooffset's internal sampling: rayintersect|metafield|
        minimum|pointcloud|implicitbox|implicitsphere|implicitplane|volume|volumerebuild), offset
        (iso, legacy alias), uniformsamples (nonsquare|x|y|z|max|size axis selector), samplediv
        (sample count), divsize, laserscan, fixsigns, invert.
      tovdb -> convert (totype=VDB) | topoly -> convert (totype=Polygon) | convert -> bare convert.
    BUILT (one cook)."""
    mode = str(params.get("mode", "isooffset"))
    applied = {}
    if mode == "isooffset":
        n = child_after(params["input"], "isooffset", params.get("name"))
        if "output" in params:
            applied["output"] = _menu_set(n, "output", str(params["output"]), _ISOOFFSET_OUTPUT)
        if "sample_mode" in params:
            applied["sample_mode"] = _menu_set(n, "mode", str(params["sample_mode"]), _ISOOFFSET_SAMPLE_MODE)
        if "offset" in params:
            applied["offset"] = _try_set(n, "offset", clamp(float(params["offset"]), -1e6, 1e6))
        if "iso" in params:  # legacy alias for offset
            applied["offset"] = _try_set(n, "offset", clamp(float(params["iso"]), -1e6, 1e6))
        if "uniformsamples" in params:
            applied["uniformsamples"] = _menu_set(n, "uniformsamples", str(params["uniformsamples"]), _ISOOFFSET_UNIFORMSAMPLES)
        if "samplediv" in params:
            applied["samplediv"] = _try_set(n, "samplediv", int(clamp(int(params["samplediv"]), 1, 100000)))
        if "divsize" in params:
            applied["divsize"] = _try_set(n, "divsize", clamp(float(params["divsize"]), 1e-4, 1e5))
        if "laserscan" in params:
            applied["laserscan"] = _try_set(n, "laserscan", bool(params["laserscan"]))
        if "fixsigns" in params:
            applied["fixsigns"] = _try_set(n, "fixsigns", bool(params["fixsigns"]))
        if "invert" in params:
            applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
    elif mode in ("tovdb", "topoly", "convert"):
        n = child_after(params["input"], "convert", params.get("name"))
        if mode == "tovdb":
            applied["totype"] = _try_set(n, "totype", _CONVERT_TOTYPE["vdb"])
        elif mode == "topoly":
            applied["totype"] = _try_set(n, "totype", _CONVERT_TOTYPE["poly"])
    else:
        raise ValueError("mode must be isooffset|tovdb|topoly|convert")
    n.geometry()
    return {"node": n.path(), "mode": mode, "applied": applied}


@endpoint("mesh_pointcloud")
def mesh_pointcloud(params):
    """Mesh a point cloud with a native SOP chain (no python geo loop): Object Merge -> VDB From
    Particles -> Convert VDB -> optional PolyReduce -> optional Cd transfer -> optional confined
    export. `input` = the cloud's display SOP path. Creator: FAILS on name collision.
    """
    name = params["name"]
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    src_sop = resolve_node(params["input"])
    voxel = clamp(float(params.get("voxel_size", 1.0)), 1e-4, 1e5)
    particle_scale = clamp(float(params.get("particle_scale", 1.0)), 0.01, 100.0)
    adaptivity = clamp(float(params.get("adaptivity", 0.0)), 0.0, 1.0)
    reduce_percent = float(params.get("reduce_percent", 0.0) or 0.0)

    mesh_geo = obj.createNode("geo", name)
    om = mesh_geo.createNode("object_merge", "in_cloud")
    om.parm("objpath1").set(src_sop.path())
    _try_set(om, "xformtype", 1)  # "Into This Object"
    last = om
    vdb = mesh_geo.createNode("vdbfromparticles", "vdb")
    vdb.setFirstInput(last)
    _try_set(vdb, "voxelsize", voxel)
    _try_set(vdb, "radiusscale", 1.0)
    _try_set(vdb, "minvoxelradius", particle_scale)
    _try_set(vdb, "builddistance", 1)
    last = vdb
    conv = mesh_geo.createNode("convertvdb", "to_polys")
    conv.setFirstInput(last)
    _try_set(conv, "conversion", 2)  # Polygons
    _try_set(conv, "adaptivity", adaptivity)
    last = conv
    if 0.0 < reduce_percent < 100.0:
        red = mesh_geo.createNode("polyreduce::2.0", "reduce")
        red.setFirstInput(last)
        _try_set(red, "percentage", reduce_percent)
        last = red
    if params.get("transfer_color"):
        at = mesh_geo.createNode("attribtransfer", "xfer_cd")
        at.setFirstInput(last)   # input 0 = destination (mesh)
        at.setInput(1, om)       # input 1 = source (cloud)
        _try_set(at, "pointattriblist", "Cd")
        last = at

    last.setDisplayFlag(True)
    last.setRenderFlag(True)
    mesh_geo.setDisplayFlag(True)
    mesh_geo.layoutChildren()
    g = last.geometry()
    exported = None
    if params.get("export_path"):
        from houdini_executor.server import out_context
        out_path = confined_path(params["export_path"])
        # /out geometry ROP (the `geometry` ROP is probe-verified; rop_geometry errored in-probe).
        rop = out_context().createNode("geometry", "export_" + name)
        rop.parm("soppath").set(last.path())
        rop.parm("sopoutput").set(out_path)
        _try_set(rop, "mkpath", True)
        rop.render()  # executable-confined write
        exported = out_path
    bb = g.boundingBox()
    return {"node": mesh_geo.path(), "sop": last.path(),
            "prims": g.intrinsicValue("primitivecount"),
            "points": g.intrinsicValue("pointcount"),
            "exported": exported,
            "bbox": {"min": list(bb.minvec()), "max": list(bb.maxvec())}}


# ── VOLUME lane Phase 1 (T8 analysis / T9 topology / T7 combine) — all live-probed on H21.0.671.
# PROBE CORRECTIONS baked in below (correcting earlier guessed names):
#   • vdbanalysis.operator: the vector-magnitude token is `length` (label "Length (Vector->Scalar)"),
#     NOT the spec's `magnitude`. The mask restriction is a plain `maskname` parm + input1, not a
#     `maskvdb` parm. `outputname` is a STRING-type menu (keep/append/custom) → token stored directly.
#   • vdbcombine: the SDF CSG modes (sdfunion/sdfintersect/sdfdifference) live in the `operation`
#     Menu, NOT in `collation`. `collation` is a STRING menu about how A/B grids are paired
#     (pairs/awithfirstb/flattena/flattenbtoa/flattenagroups) — the spec conflated the two. input0=A,
#     input1=B. `resample`/`resampleinterp` are ordered Menus.
#   • fog blend is `volumemix`, and its method parm is `mixmethod` (Menu), NOT `operation`; there is
#     no `value` parm (the knobs are `blend` and `range`). input0/input1.
#   • vdbvectormerge type parm is `vectype` (Menu; tokens carry spaces), NOT the spec's `vdbvectortype`;
#     there is no `position` parm. Single input. vdbvectorsplit: single input, no type parm.
#   • vdbactivate has no `reference`/`deactivate` parms; region controls are center/size/min/max +
#     expand/expanddist/expansionpattern (STRING menu). value rides `setvalue`. input1 = region.
#   • vdbclip: `clipper` STRING menu (camera/geometry/mask); padding rides `setpadding`; input1 =
#     mask VDB or bounding geometry.
#   • vdbresample: interpolation parm is `order` (Menu); `mode` (Menu) selects the resample method;
#     scale/rotate/pivot are the s/r/p parm-tuples. input1 = optional transform-reference VDB.
_VDBANALYSIS_OP = ("gradient", "curvature", "laplacian", "closestpoint",
                   "divergence", "curl", "length", "normalize")           # operator (Menu=idx)
_VDBANALYSIS_OUTNAME = ("keep", "append", "custom")                       # outputname (STRING menu)
_VDBCOMBINE_OP = ("copya", "copyb", "inverta", "add", "subtract", "multiply", "divide",
                  "maximum", "minimum", "compatimesb", "apluscompatimesb", "sdfunion",
                  "sdfintersect", "sdfdifference", "replacewithactive", "topounion",
                  "topointersect", "topodifference")                      # operation (Menu=idx)
_VDBCOMBINE_COLLATION = ("pairs", "awithfirstb", "flattena", "flattenbtoa",
                         "flattenagroups")                                # collation (STRING menu)
_VDBCOMBINE_RESAMPLE = ("off", "btoa", "atob", "hitolo", "lotohi")        # resample (Menu=idx)
_VDB_RESAMPLEINTERP = ("point", "linear", "quadratic")                    # resampleinterp/order (Menu=idx)
_VOLUMEMIX_METHOD = ("copy", "add", "sub", "diff", "mul", "div", "invert",
                     "max", "min", "clamp", "blend", "user")              # mixmethod (Menu=idx)
_VDBVECTORMERGE_TYPE = ("invariant", "covariant", "covariant normalize",
                        "contravariant relative", "contravariant absolute")  # vectype (Menu=idx)
_VDBACTIVATE_OP = ("union", "intersect", "subtract", "copy")             # operation (Menu=idx)
_VDBACTIVATE_PATTERN = ("face", "faceedge", "faceedgevertex")            # expansionpattern (STRING menu)
_VDBCLIP_CLIPPER = ("camera", "geometry", "mask")                        # clipper (STRING menu)
_VDBRESAMPLE_MODE = ("explicit", "refvdb", "voxelsizeonly", "voxelscaleonly")  # mode (Menu=idx)


@endpoint("vdb_analysis")
def vdb_analysis(params):
    """Field calculus on a VDB via the VDB Analysis SOP (vdbanalysis) — NO VEX. `operator`:
    gradient (scalar->vector), curvature, laplacian, closestpoint (scalar->vector), divergence
    (vector->scalar), curl, length (vector-magnitude scalar), normalize. An optional mask VDB on
    input1 (`input_b`) restricts the iteration space to its active voxels; `maskname` names the mask
    grid. Output naming: outputname keep|append|custom (custom uses `customname`). BUILT (one cook).
    """
    n = child_after(params["input"], "vdbanalysis", params.get("name"))
    applied = {}
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    if "operator" in params:
        applied["operator"] = _menu_set(n, "operator", str(params["operator"]), _VDBANALYSIS_OP)
    if params.get("input_b"):
        bridge_input(n, params["input_b"], index=1, name_hint="input_b")
        applied["mask_input"] = True
    if "maskname" in params:
        applied["maskname"] = _try_set(n, "maskname", str(params["maskname"]))
    if "outputname" in params:
        applied["outputname"] = _str_menu_set(n, "outputname", str(params["outputname"]), _VDBANALYSIS_OUTNAME)
    if "customname" in params:
        _str_menu_set(n, "outputname", "custom", _VDBANALYSIS_OUTNAME)
        applied["customname"] = _try_set(n, "customname", str(params["customname"]))
    n.geometry()
    return {"node": n.path(), "operator": params.get("operator"), "applied": applied}


@endpoint("vdb_topology")
def vdb_topology(params):
    """Active-voxel-set (topology) ops on a VDB via `op`:
      activate -> vdbactivate: grow/shrink/set the active region. operation (union|intersect|
        subtract|copy), value (rides setvalue), expand (voxel dilation count), expanddist,
        expansionpattern (face|faceedge|faceedgevertex). Optional region VDB/geo on input1 (input_b).
      clip -> vdbclip: clip to a mask VDB or bounding geometry on input1 (input_b). clipper
        (camera|geometry|mask), inside (keep inside), mask (grid name), padding (rides setpadding).
      resample -> vdbresample: voxel rescale / transform. mode (explicit|refvdb|voxelsizeonly|
        voxelscaleonly), order interpolation (point|linear|quadratic), voxelsize, voxelscale,
        scale/rotate/pivot [x,y,z], linearxform. Optional transform-reference VDB on input1.
      segment -> vdbsegmentbyconnectivity: split disjoint components. colorsegments, appendnumber.
    BUILT (one cook)."""
    op = str(params.get("op", "activate"))
    applied = {}
    if op == "activate":
        n = child_after(params["input"], "vdbactivate", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
        if "operation" in params:
            applied["operation"] = _menu_set(n, "operation", str(params["operation"]), _VDBACTIVATE_OP)
        if "value" in params:
            _try_set(n, "setvalue", 1)
            applied["value"] = _try_set(n, "value", clamp(float(params["value"]), -1e12, 1e12))
        if "expand" in params:
            applied["expand"] = _try_set(n, "expand", int(clamp(int(params["expand"]), -100000, 100000)))
        if "expanddist" in params:
            applied["expanddist"] = _try_set(n, "expanddist", clamp(float(params["expanddist"]), -1e9, 1e9))
        if "expansionpattern" in params:
            applied["expansionpattern"] = _str_menu_set(n, "expansionpattern",
                                                        str(params["expansionpattern"]), _VDBACTIVATE_PATTERN)
        if "prune" in params:
            applied["prune"] = _try_set(n, "prune", bool(params["prune"]))
    elif op == "clip":
        n = child_after(params["input"], "vdbclip", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
        if "clipper" in params:
            applied["clipper"] = _str_menu_set(n, "clipper", str(params["clipper"]), _VDBCLIP_CLIPPER)
        if "inside" in params:
            applied["inside"] = _try_set(n, "inside", bool(params["inside"]))
        if "mask" in params:
            applied["mask"] = _try_set(n, "mask", str(params["mask"]))
        if "padding" in params:
            _try_set(n, "setpadding", 1)
            pt = n.parmTuple("padding")           # padding is a per-axis vec3
            pv = params["padding"]
            if pt is not None:
                pad = ([float(x) for x in pv] if isinstance(pv, (list, tuple))
                       else [float(pv)] * len(pt))
                applied["padding"] = _set_vec(n, "padding", pad)
    elif op == "resample":
        n = child_after(params["input"], "vdbresample", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
        if "mode" in params:
            applied["mode"] = _menu_set(n, "mode", str(params["mode"]), _VDBRESAMPLE_MODE)
        if "order" in params:
            applied["order"] = _menu_set(n, "order", str(params["order"]), _VDB_RESAMPLEINTERP)
        if "voxelsize" in params:
            applied["voxelsize"] = _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 1e5))
        if "voxelscale" in params:
            applied["voxelscale"] = _try_set(n, "voxelscale", clamp(float(params["voxelscale"]), 1e-4, 1e5))
        if "scale" in params:
            applied["scale"] = _set_vec(n, "s", params["scale"])
        if "rotate" in params:
            applied["rotate"] = _set_vec(n, "r", params["rotate"])
        if "pivot" in params:
            applied["pivot"] = _set_vec(n, "p", params["pivot"])
        if "linearxform" in params:
            applied["linearxform"] = _try_set(n, "linearxform", bool(params["linearxform"]))
    elif op == "segment":
        n = child_after(params["input"], "vdbsegmentbyconnectivity", params.get("name"))
        if "colorsegments" in params:
            applied["colorsegments"] = _try_set(n, "colorsegments", bool(params["colorsegments"]))
        if "appendnumber" in params:
            applied["appendnumber"] = _try_set(n, "appendnumber", bool(params["appendnumber"]))
    else:
        raise ValueError("op must be activate|clip|resample|segment")
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    n.geometry()
    return {"node": n.path(), "op": op, "applied": applied}


@endpoint("vdb_combine")
def vdb_combine(params):
    """Two-input CSG / field-math on VDBs (the typed answer to "I need a Volume VOP for two fields")
    via `op` — NO VEX. input0 = A (`input`), input1 = B (`input_b`):
      sdf -> vdbcombine: SDF/scalar CSG + arithmetic. operation (copya|copyb|inverta|add|subtract|
        multiply|divide|maximum|minimum|compatimesb|apluscompatimesb|sdfunion|sdfintersect|
        sdfdifference|replacewithactive|topounion|topointersect|topodifference — the sdf* tokens ARE
        the CSG union/intersect/difference), collation (pairs|awithfirstb|flattena|flattenbtoa|
        flattenagroups — how A/B grids are paired), amult, bmult, resample (off|btoa|atob|hitolo|
        lotohi), resampleinterp (point|linear|quadratic), prune.
      fog -> volumemix: fog-volume blend. mixmethod (copy|add|sub|diff|mul|div|invert|max|min|clamp|
        blend|user), blend (0..1), range.
      vectormerge -> vdbvectormerge: assemble scalar .x/.y/.z grids into one vector VDB (prep for
        advection). vectype (invariant|covariant|"covariant normalize"|"contravariant relative"|
        "contravariant absolute"), merge_name, remove_sources. Single input.
      vectorsplit -> vdbvectorsplit: split a vector VDB back into scalar grids. remove_sources.
        Single input.
    BUILT (one cook)."""
    op = str(params.get("op", "sdf"))
    applied = {}
    if op == "sdf":
        n = child_after(params["input"], "vdbcombine", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
        if "operation" in params:
            applied["operation"] = _menu_set(n, "operation", str(params["operation"]), _VDBCOMBINE_OP)
        if "collation" in params:
            applied["collation"] = _str_menu_set(n, "collation", str(params["collation"]), _VDBCOMBINE_COLLATION)
        if "amult" in params:
            applied["amult"] = _try_set(n, "amult", clamp(float(params["amult"]), -1e9, 1e9))
        if "bmult" in params:
            applied["bmult"] = _try_set(n, "bmult", clamp(float(params["bmult"]), -1e9, 1e9))
        if "resample" in params:
            applied["resample"] = _menu_set(n, "resample", str(params["resample"]), _VDBCOMBINE_RESAMPLE)
        if "resampleinterp" in params:
            applied["resampleinterp"] = _menu_set(n, "resampleinterp", str(params["resampleinterp"]), _VDB_RESAMPLEINTERP)
        if "prune" in params:
            applied["prune"] = _try_set(n, "prune", bool(params["prune"]))
    elif op == "fog":
        n = child_after(params["input"], "volumemix", params.get("name"))
        if params.get("input_b"):
            bridge_input(n, params["input_b"], index=1, name_hint="input_b")
        if "mixmethod" in params:
            applied["mixmethod"] = _menu_set(n, "mixmethod", str(params["mixmethod"]), _VOLUMEMIX_METHOD)
        if "blend" in params:
            applied["blend"] = _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
        if "range" in params:
            applied["range"] = _try_set(n, "range", clamp(float(params["range"]), -1e12, 1e12))
    elif op == "vectormerge":
        n = child_after(params["input"], "vdbvectormerge", params.get("name"))
        if "vectype" in params:
            applied["vectype"] = _menu_set(n, "vectype", str(params["vectype"]), _VDBVECTORMERGE_TYPE)
        if "merge_name" in params:
            applied["merge_name"] = _try_set(n, "merge_name", str(params["merge_name"]))
        if "remove_sources" in params:
            applied["remove_sources"] = _try_set(n, "remove_sources", bool(params["remove_sources"]))
    elif op == "vectorsplit":
        n = child_after(params["input"], "vdbvectorsplit", params.get("name"))
        if "remove_sources" in params:
            applied["remove_sources"] = _try_set(n, "remove_sources", bool(params["remove_sources"]))
    else:
        raise ValueError("op must be sdf|fog|vectormerge|vectorsplit")
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    n.geometry()
    return {"node": n.path(), "op": op, "applied": applied}


# ── VOLUME lane Phase 4 (T10 vdb_advect / T11 vdb_shatter / T12 volume_visualize) — all live-probed
# on H21.0.671. PROBE CORRECTIONS baked in (correcting several earlier guessed
# tokens/parms):
#   • vdbadvectpoints.integration tokens are 'fwd euler'/'2nd rk'/'3rd rk'/'4th rk' (STRING menu, with
#     spaces), NOT the spec's RK1/2/4. `operation` (STRING) = advection/projection/cadvection — projection
#     is a VALUE of operation, NOT a separate parm. The substep count parm is `steps` (Int), not
#     `substeps`. inputs: 0=Points to Advect, 1=Velocity VDB, 2=Closest Point VDB.
#   • vdbadvectsdf.advection tokens = semi/mid/rk3/rk4/mac/bfecc (STRING menu; MacCormack='mac',
#     BFECC='bfecc'), + `limiter` none/clamp/revert. Renorm steps = `normsteps`. There is NO `velocity`
#     parm (the vel VDB is input1; `velgroup` names the grid). Substep count = `substeps`.
#     inputs: 0=VDBs to Advect, 1=Velocity VDB.
#   • vdbmorphsdf: the target SDF is input1 (NOT a `target` parm); groups are `sourcegroup`/`targetgroup`.
#     inputs: 0=Source SDF, 1=Target SDF, 2=Optional VDB Alpha Mask. renorm=`normsteps`; alpha mask via
#     `mask`/`maskname`/`invert`/`minmask`/`maxmask`.
#   • vdbfracture visualization parm is `visualizepieces` (ordered Menu idx none/all/new), NOT the spec's
#     `visualization`. inputs: 0=grids to fracture, 1=Cutter geometry, 2=Optional instance points.
#   • vdbtospheres: radiusmin/radiusmax/spheresmin/spheresmax are each gated by a use* toggle
#     (useradiusmin default ON; useradiusmax default OFF; usespheresmin/usespheresmax default ON) — the
#     handler flips the matching toggle whenever it sets the value, so radiusmax actually takes effect.
#     Single input. `worldunits` toggle.
#   • volumevisualization `vismode` is an ordered Menu (none/smoke/heightfield); emission = `emitfield`
#     (grid name) + `emitscale` — there is NO plain `emission`/`smoke` parm (smoke is a vismode token).
#   • volumeslice: the cross-section position parms are `planepos`/`planeoffset` (NOT position/offset);
#     the sampled attrib is `attrib` (NOT attribute); the color map is `vismode` (ordered Menu; NOT
#     `colormapping`) with tokens none/false/pink/mono/blackbody/bipartite/custom (exposed here as
#     `colormap` to avoid clashing with volumevisualization's own vismode). `method`=volume/mesh/points,
#     `plane`=xy/yz/zx (both ordered Menus).
def _set_literal(node, parm, value):
    """Set a float literal, first clearing any default expression/keyframes (probe-safe). The advect
    `timestep` parms default to the Hscript expression `1.0/$FPS`, so a plain .set() would be masked
    on eval — deleteAllKeyframes() drops the expression, leaving the literal. Data-only: clears a
    channel and writes a literal; it never authors an expression."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.deleteAllKeyframes()
        p.set(value)
        return True
    except Exception:
        return False


_ADVECTPOINTS_OP = ("advection", "projection", "cadvection")            # operation (STRING menu)
_ADVECTPOINTS_INTEG = ("fwd euler", "2nd rk", "3rd rk", "4th rk")       # integration (STRING menu)
_ADVECTSDF_ADVECTION = ("semi", "mid", "rk3", "rk4", "mac", "bfecc")    # advection (STRING menu)
_ADVECTSDF_LIMITER = ("none", "clamp", "revert")                        # limiter (STRING menu)
_VDBFRACTURE_VIS = ("none", "all", "new")                               # visualizepieces (Menu=idx)
_VOLVIS_MODE = ("none", "smoke", "heightfield")                         # vismode (Menu=idx)
_VOLSLICE_METHOD = ("volume", "mesh", "points")                         # method (Menu=idx)
_VOLSLICE_PLANE = ("xy", "yz", "zx")                                    # plane (Menu=idx)
_VOLSLICE_COLORMAP = ("none", "false", "pink", "mono", "blackbody", "bipartite", "custom")  # vismode (Menu=idx)


@endpoint("vdb_advect")
def vdb_advect(params):
    """Transport a VDB by a velocity VDB via `op` — NO VEX. BUILT (one cook), never auto-simulated:
      points -> vdbadvectpoints: advect points through a velocity field. `input`=points (input0);
        `velocity`=velocity VDB SOP path (input1); `cpt`=optional closest-point VDB (input2).
        operation (advection|projection|cadvection), integration (fwd euler|2nd rk|3rd rk|4th rk),
        iterations, timestep, steps (substeps), vdbpointsgroups/velgroup.
      sdf -> vdbadvectsdf: advect an SDF/scalar VDB. `input`=VDBs (input0); `velocity`=velocity VDB
        (input1). advection (semi|mid|rk3|rk4|mac|bfecc), limiter (none|clamp|revert), timestep,
        substeps, normsteps (renorm), respectclass, velgroup.
      morph -> vdbmorphsdf: morph a source SDF toward a target SDF. `input`=source (input0);
        `target`=target SDF VDB (input1); optional alpha-mask VDB via `mask_input` (input2). timestep,
        normsteps, invert, minmask, maxmask, maskname."""
    op = str(params.get("op", "sdf"))
    applied = {}
    if op == "points":
        n = child_after(params["input"], "vdbadvectpoints", params.get("name"))
        if params.get("velocity"):
            bridge_input(n, params["velocity"], index=1, name_hint="velocity")
            applied["velocity_input"] = True
        if params.get("cpt"):
            bridge_input(n, params["cpt"], index=2, name_hint="cpt")
            applied["cpt_input"] = True
        if "operation" in params:
            applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _ADVECTPOINTS_OP)
        if "integration" in params:
            applied["integration"] = _str_menu_set(n, "integration", str(params["integration"]), _ADVECTPOINTS_INTEG)
        if "iterations" in params:
            applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 10)))
        if "timestep" in params:
            applied["timestep"] = _set_literal(n, "timestep", clamp(float(params["timestep"]), 0.0, 10.0))
        if "steps" in params:
            applied["steps"] = _try_set(n, "steps", int(clamp(int(params["steps"]), 1, 10)))
        if "vdbpointsgroups" in params:
            applied["vdbpointsgroups"] = _try_set(n, "vdbpointsgroups", str(params["vdbpointsgroups"]))
        if "velgroup" in params:
            applied["velgroup"] = _try_set(n, "velgroup", str(params["velgroup"]))
    elif op == "sdf":
        n = child_after(params["input"], "vdbadvectsdf", params.get("name"))
        if params.get("velocity"):
            bridge_input(n, params["velocity"], index=1, name_hint="velocity")
            applied["velocity_input"] = True
        if "advection" in params:
            applied["advection"] = _str_menu_set(n, "advection", str(params["advection"]), _ADVECTSDF_ADVECTION)
        if "limiter" in params:
            applied["limiter"] = _str_menu_set(n, "limiter", str(params["limiter"]), _ADVECTSDF_LIMITER)
        if "timestep" in params:
            applied["timestep"] = _set_literal(n, "timestep", clamp(float(params["timestep"]), 0.0, 10.0))
        if "substeps" in params:
            applied["substeps"] = _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 10)))
        if "normsteps" in params:
            applied["normsteps"] = _try_set(n, "normsteps", int(clamp(int(params["normsteps"]), 1, 10)))
        if "respectclass" in params:
            applied["respectclass"] = _try_set(n, "respectclass", bool(params["respectclass"]))
        if "velgroup" in params:
            applied["velgroup"] = _try_set(n, "velgroup", str(params["velgroup"]))
    elif op == "morph":
        n = child_after(params["input"], "vdbmorphsdf", params.get("name"))
        if params.get("target"):
            bridge_input(n, params["target"], index=1, name_hint="target")
            applied["target_input"] = True
        if params.get("mask_input"):
            bridge_input(n, params["mask_input"], index=2, name_hint="mask_input")
            applied["mask_input"] = True
        if "timestep" in params:
            applied["timestep"] = _set_literal(n, "timestep", clamp(float(params["timestep"]), 0.0, 10.0))
        if "normsteps" in params:
            applied["normsteps"] = _try_set(n, "normsteps", int(clamp(int(params["normsteps"]), 1, 10)))
        if "invert" in params:
            applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
        if "minmask" in params:
            applied["minmask"] = _try_set(n, "minmask", clamp(float(params["minmask"]), 0.0, 1.0))
        if "maxmask" in params:
            applied["maxmask"] = _try_set(n, "maxmask", clamp(float(params["maxmask"]), 0.0, 1.0))
        if "maskname" in params:
            applied["maskname"] = _try_set(n, "maskname", str(params["maskname"]))
    else:
        raise ValueError("op must be points|sdf|morph")
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    n.geometry()
    return {"node": n.path(), "op": op, "applied": applied}


@endpoint("vdb_shatter")
def vdb_shatter(params):
    """SDF VDB -> discrete pieces / sphere proxies via `op` — NO VEX. BUILT (one cook):
      fracture -> vdbfracture: cut an SDF into pieces with cutter geometry (feeds sim_rbd). `input`=
        SDF grids (input0); `cutter`=cutter-geometry SOP path (input1); `points`=optional points to
        instance the cutter onto (input2). group, separatecutters, cutteroverlap, centercutter,
        randomizerotation, seed, segmentfragments, fragmentgroup, visualizepieces (none|all|new).
      spheres -> vdbtospheres: pack an SDF with proxy spheres (RBD proxies). isovalue, radiusmin,
        radiusmax, spheresmin, spheresmax, scatter, overlapping, worldunits, preserve, doid, dopscale
        (each min/max radius/sphere-count auto-enables its use* toggle). Single input."""
    op = str(params.get("op", "fracture"))
    applied = {}
    if op == "fracture":
        n = child_after(params["input"], "vdbfracture", params.get("name"))
        if params.get("cutter"):
            bridge_input(n, params["cutter"], index=1, name_hint="cutter")
            applied["cutter_input"] = True
        if params.get("points"):
            bridge_input(n, params["points"], index=2, name_hint="points")
            applied["points_input"] = True
        if "separatecutters" in params:
            applied["separatecutters"] = _try_set(n, "separatecutters", bool(params["separatecutters"]))
        if "cutteroverlap" in params:
            applied["cutteroverlap"] = _try_set(n, "cutteroverlap", bool(params["cutteroverlap"]))
        if "centercutter" in params:
            applied["centercutter"] = _try_set(n, "centercutter", bool(params["centercutter"]))
        if "randomizerotation" in params:
            applied["randomizerotation"] = _try_set(n, "randomizerotation", bool(params["randomizerotation"]))
        if "seed" in params:
            applied["seed"] = _try_set(n, "seed", int(clamp(int(params["seed"]), 0, 10)))
        if "segmentfragments" in params:
            applied["segmentfragments"] = _try_set(n, "segmentfragments", bool(params["segmentfragments"]))
        if "fragmentgroup" in params:
            applied["fragmentgroup"] = _try_set(n, "fragmentgroup", str(params["fragmentgroup"]))
        if "visualizepieces" in params:
            applied["visualizepieces"] = _menu_set(n, "visualizepieces", str(params["visualizepieces"]), _VDBFRACTURE_VIS)
    elif op == "spheres":
        n = child_after(params["input"], "vdbtospheres", params.get("name"))
        if "isovalue" in params:
            applied["isovalue"] = _try_set(n, "isovalue", clamp(float(params["isovalue"]), -1.0, 1.0))
        if "worldunits" in params:
            applied["worldunits"] = _try_set(n, "worldunits", bool(params["worldunits"]))
        if "radiusmin" in params:
            _try_set(n, "useradiusmin", 1)
            applied["radiusmin"] = _try_set(n, "radiusmin", clamp(float(params["radiusmin"]), 1e-5, 2.0))
        if "radiusmax" in params:
            _try_set(n, "useradiusmax", 1)
            applied["radiusmax"] = _try_set(n, "radiusmax", clamp(float(params["radiusmax"]), 1e-5, 100.0))
        if "spheresmin" in params:
            _try_set(n, "usespheresmin", 1)
            applied["spheresmin"] = _try_set(n, "spheresmin", int(clamp(int(params["spheresmin"]), 0, 100)))
        if "spheresmax" in params:
            _try_set(n, "usespheresmax", 1)
            applied["spheresmax"] = _try_set(n, "spheresmax", int(clamp(int(params["spheresmax"]), 1, 100)))
        if "scatter" in params:
            applied["scatter"] = _try_set(n, "scatter", int(clamp(int(params["scatter"]), 1000, 50000)))
        if "overlapping" in params:
            applied["overlapping"] = _try_set(n, "overlapping", bool(params["overlapping"]))
        if "preserve" in params:
            applied["preserve"] = _try_set(n, "preserve", bool(params["preserve"]))
        if "doid" in params:
            applied["doid"] = _try_set(n, "doid", bool(params["doid"]))
        if "dopscale" in params:
            applied["dopscale"] = _try_set(n, "dopscale", bool(params["dopscale"]))
    else:
        raise ValueError("op must be fracture|spheres")
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    n.geometry()
    return {"node": n.path(), "op": op, "applied": applied}


@endpoint("volume_visualize")
def volume_visualize(params):
    """Inspect/present a fog volume in the viewport (no render) via `op` — NO VEX. BUILT (one cook):
      shade -> volumevisualization: viewport fog shading. vismode (none|smoke|heightfield),
        densityscale, rangemin, rangemax, shadowscale, densityfield (density grid name), emitfield
        (emission grid name), emitscale. Single input.
      slice -> volumeslice: a 2D cross-section. method (volume|mesh|points), plane (xy|yz|zx),
        relative, planepos, planeoffset, attrib (sampled grid), colormap (none|false|pink|mono|
        blackbody|bipartite|custom), voxelsnap, keep, group. Single input."""
    op = str(params.get("op", "shade"))
    applied = {}
    if op == "shade":
        n = child_after(params["input"], "volumevisualization", params.get("name"))
        if "vismode" in params:
            applied["vismode"] = _menu_set(n, "vismode", str(params["vismode"]), _VOLVIS_MODE)
        if "densityscale" in params:
            applied["densityscale"] = _try_set(n, "densityscale", clamp(float(params["densityscale"]), 0.0, 10.0))
        if "rangemin" in params:
            applied["rangemin"] = _try_set(n, "rangemin", clamp(float(params["rangemin"]), 0.0, 10.0))
        if "rangemax" in params:
            applied["rangemax"] = _try_set(n, "rangemax", clamp(float(params["rangemax"]), 0.0, 10.0))
        if "shadowscale" in params:
            applied["shadowscale"] = _try_set(n, "shadowscale", clamp(float(params["shadowscale"]), 0.0, 10.0))
        if "densityfield" in params:
            applied["densityfield"] = _try_set(n, "densityfield", str(params["densityfield"]))
        if "emitfield" in params:
            applied["emitfield"] = _try_set(n, "emitfield", str(params["emitfield"]))
        if "emitscale" in params:
            applied["emitscale"] = _try_set(n, "emitscale", clamp(float(params["emitscale"]), 0.0, 10.0))
    elif op == "slice":
        n = child_after(params["input"], "volumeslice", params.get("name"))
        if "method" in params:
            applied["method"] = _menu_set(n, "method", str(params["method"]), _VOLSLICE_METHOD)
        if "plane" in params:
            applied["plane"] = _menu_set(n, "plane", str(params["plane"]), _VOLSLICE_PLANE)
        if "relative" in params:
            applied["relative"] = _try_set(n, "relative", bool(params["relative"]))
        if "planepos" in params:
            # planepos is a per-axis vec3 (planeposx/y/z) — a point the absolute slice plane passes
            # through. Accept a [x,y,z] or broadcast a scalar to all three.
            pv = params["planepos"]
            pv = [float(x) for x in pv] if isinstance(pv, (list, tuple)) else [float(pv)] * 3
            applied["planepos"] = _set_vec(n, "planepos", pv)
        if "planeoffset" in params:
            applied["planeoffset"] = _try_set(n, "planeoffset", clamp(float(params["planeoffset"]), -1.0, 1.0))
        if "attrib" in params:
            applied["attrib"] = _try_set(n, "attrib", str(params["attrib"]))
        if "colormap" in params:
            applied["colormap"] = _menu_set(n, "vismode", str(params["colormap"]), _VOLSLICE_COLORMAP)
        if "voxelsnap" in params:
            applied["voxelsnap"] = _try_set(n, "voxelsnap", bool(params["voxelsnap"]))
        if "keep" in params:
            applied["keep"] = _try_set(n, "keep", bool(params["keep"]))
    else:
        raise ValueError("op must be shade|slice")
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    n.geometry()
    return {"node": n.path(), "op": op, "applied": applied}


# ── clean (dirty-geometry cleanup — the parametric complement to polydoctor/mesh_repair) ──────────────
@endpoint("clean")
def clean(params):
    """Clean SOP: parametric cleanup of dirty/scan geometry. Toggles (only supplied ones change):
    `consolidate` (+`distance`) fuses near-coincident points; `remove_degenerate` (+`degenerate_tol`)
    drops zero-area/length prims; `delete_unused_points`; `fix_overlap` (+`delete_overlap`) removes
    overlapping prims; `orient` makes winding consistent (+`reverse_winding`); `delete_nans` drops
    NaN/inf; `make_manifold`; `delete_small` (+`min_prims`) removes tiny disconnected pieces."""
    n = child_after(params["input"], "clean", params.get("name"))
    applied = {}
    _MAP = {
        "consolidate": "fusepts", "remove_degenerate": "deldegengeo",
        "delete_unused_points": "delunusedpts", "fix_overlap": "fixoverlap",
        "delete_overlap": "deleteoverlap", "orient": "orientpoly",
        "reverse_winding": "reversewinding", "delete_nans": "delnans",
        "make_manifold": "make_manifold", "delete_small": "delete_small",
    }
    for key, parm in _MAP.items():
        if key in params:
            applied[key] = _try_set(n, parm, bool(params[key]))
    if "distance" in params:
        applied["distance"] = _try_set(n, "fusedist", clamp(float(params["distance"]), 0.0, 1e6))
    if "degenerate_tol" in params:
        applied["degenerate_tol"] = _try_set(n, "degentol", clamp(float(params["degenerate_tol"]), 0.0, 1e6))
    if "min_prims" in params:
        applied["min_prims"] = _try_set(n, "prim_count", int(clamp(int(params["min_prims"]), 1, 1_000_000)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()), "applied": applied}


_QUADREMESH_RES = ("quad_count", "quad_area", "tolerance",
                   "relative_scale", "absolute_scale")  # quadremesh resolution (Menu=idx; live-probed)


@endpoint("quad_remesh")
def quad_remesh(params):
    """Field-aligned QUAD remesh (native `quadremesh` SOP — no Labs/3rd-party license): turn a
    triangulated / scan mesh into a clean all-quad mesh for subdivision. resolution selects how
    density is set (quad_count->target_quads | quad_area->target_area | ...); adaptivity +
    curvature_weight concentrate quads on curvature; decimation_level pre-decimates for speed.
    Live-probed parm names/ranges."""
    governor_gate("quad_remesh")
    n = child_after(params["input"], "quadremesh", params.get("name"))
    if "resolution" in params:
        _menu_set(n, "resolution", str(params["resolution"]), _QUADREMESH_RES)
    if "target_quads" in params:
        _try_set(n, "targetquadcount", int(clamp(int(params["target_quads"]), 4, 100_000_000)))
    if "target_area" in params:
        _try_set(n, "targetquadarea", clamp(float(params["target_area"]), 0.0, 1.0))
    if "adaptivity" in params:
        _try_set(n, "enableadaptivity", True)
        _try_set(n, "adaptivityweight", clamp(float(params["adaptivity"]), 0.0, 1.0))
    if "curvature_weight" in params:
        _try_set(n, "curvature", True)
        _try_set(n, "localcurvatureweight", clamp(float(params["curvature_weight"]), 0.0, 10.0))
    if "decimation_level" in params:
        _try_set(n, "decimation", True)
        _try_set(n, "decimationlevel", int(clamp(int(params["decimation_level"]), 1, 12)))
    if "feature_boundaries" in params:
        _try_set(n, "featureboundaries", bool(params["feature_boundaries"]))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    g = n.geometry()
    result = advise({"node": n.path(), "prims": len(g.prims())}, n)
    result["magnitude"] = magnitude_advice("quad_remesh", params)
    return result


_VDBRESHAPE_OP = ("dilate", "erode", "open", "close")      # vdbreshapesdf.operation (Menu=index)


@endpoint("vdb_reshape")
def vdb_reshape(params):
    """Reshape an SDF VDB by offsetting its surface (VDB Reshape SDF) — dilate/erode/open/close. The
    hole-fill + delete-inside + collider-shrink workhorse (erode a low-res VDB so the hi-res mesh sits
    on top; dilate to fill pinholes). `amount` is in VOXELS by default; set world_units for metres.
    BUILT (one cook)."""
    n = child_after(params["input"], "vdbreshapesdf", params.get("name"))
    applied = {}
    if "operation" in params:
        op = str(params["operation"])
        if op in _VDBRESHAPE_OP:                            # STRING menu — set the token directly
            applied["operation"] = _try_set(n, "operation", op)
    if bool(params.get("world_units", False)):
        _try_set(n, "useworldspaceunits", True)
        applied["world_units"] = True
        if "amount" in params:
            applied["amount"] = _try_set(n, "radiusworld", clamp(float(params["amount"]), 0.0, 1e6))
    elif "amount" in params:
        # `radius` is an Int voxel count (node soft-max 5) — int-cast so a float amount lands cleanly.
        applied["amount"] = _try_set(n, "radius", int(clamp(int(float(params["amount"])), 1, 1000)))
    if "iterations" in params:
        applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 10)))
    if "voxel_offset" in params:
        applied["voxel_offset"] = _try_set(n, "voxeloffset", clamp(float(params["voxel_offset"]), 0.0, 10.0))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()), "applied": applied}

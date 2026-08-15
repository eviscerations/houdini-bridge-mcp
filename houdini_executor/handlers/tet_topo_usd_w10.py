"""SOP tet / FEM-prep + topo-transfer + SOP<->USD bridge lane.

Three sub-lanes, all verified against live H21.0.671 via hython probes:

  tet / FEM-prep (9): tetrahedralize, tet_conform, tet_embed, tet_layer, tet_partition,
    tet_surface, tet_strata, tet_fracture, solid_embed. Operators on upstream geometry: `input` is
    input 0 (child_after). tet_conform/tet_embed/tet_strata take an optional aux operand
    (additional points / inner boundary, in1); tet_partition REQUIRES region boundaries (in1).
    tet_surface/tet_fracture consume a TET mesh (build one with tetrahedralize first). Each degrades
    to cooked:false gracefully via _finish_op if a genuinely-required operand is missing.

  topo transfer / slide (2): topo_transfer (wrap a template mesh onto a target — the retopo
    workhorse; in0=template, in1=target REQUIRED, in2/in3=optional landmark points), topo_slide
    (curve-guided slide / topo-transfer; in0=target geo, in1=reference geo, in2=reference curves,
    in3=target curves — all aux optional).

  SOP<->USD bridges (6): usd_import_sop (READ a USD file into a fresh /obj geo — generator,
    file-confined READ), usd_export_sop (WRITE the input SOP to a USD file — file-confined WRITE via
    the node's own execute), usd_configure_sop / usd_configure_geometry / usd_configure_prims_from_points
    (author USD prim metadata/attributes on SOP geometry — pure operators, NO file param), unpack_usd
    (unpack packed-USD prims into native geometry — operator).

All 17 node types are new coverage (not wrapped elsewhere).
The existing usd_import / usd_configure tools are LOP-context (Solaris); export_usd is the /out USD
ROP. These are the distinct SOP-context node types, hence the `_sop` suffix where names collided.

DEFERRED (probe-confirmed): tetcraft (H21.0.671 node reports "TetCraft is not fully implemented" —
cannot cook); topoflow / topoflowbake / topoflowsample (optical-flow retopo whose CORE input is a
TEXTURE FILE — file params outside this lane's USD-only file archetype; topoflowsample is moreover a
no-input generator that reads a texture file); topolandmark (interactive: corresponding landmarks are
picked in the viewport and stored in DataParm stashes — no data-cookable headless path).

SECURITY: the curated param sets expose ONLY data params (counts, sizes, tolerances, menu tokens,
booleans, group/attribute-name strings, vec3s) plus — in the SOP<->USD bridge sub-lane ONLY — the USD read path (usd_import_sop)
and USD write path (usd_export_sop), both realpath-confined via confined_path. usdexport's pre/post
render SCRIPT params (python/hscript) are NEVER exposed or set. No VEX/expression/python/callback parm
is exposed anywhere in this lane (probe-confirmed).
"""

import os
import hou
from houdini_executor.server import (
    endpoint, child_after, clamp, resolve_node, bridge_input, confined_path,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared helpers (copied from the modeling_verbs_w9 idiom; probe-safe: never invent a parm) ────────




def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token: set the token directly (validated against the live token set)."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _vec_set(node, parm, values):
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set([float(x) for x in values])
        return True
    except Exception:  # noqa: BLE001
        try:
            pt.set([int(x) for x in values])
            return True
        except Exception:  # noqa: BLE001
            return False


def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  m=index-menu(tokens)
       ms=string-token-menu(tokens)  v=vec/tuple (extra ignored)."""
    for key, parm, kind, extra in spec:
        if key not in params:
            continue
        v = params[key]
        if kind == "f":
            _try_set(node, parm, clamp(float(v), extra[0], extra[1]))
        elif kind == "i":
            _try_set(node, parm, int(clamp(int(v), extra[0], extra[1])))
        elif kind == "b":
            _try_set(node, parm, bool(v))
        elif kind == "s":
            _try_set(node, parm, str(v))
        elif kind == "m":
            _menu_set(node, parm, str(v), extra)
        elif kind == "ms":
            _str_menu_set(node, parm, str(v), extra)
        elif kind == "v":
            _vec_set(node, parm, v)


def _enable(node, params, pairs):
    """Many USD-configure/export params are gated by an enable_* toggle. When the caller supplies the
    data key, flip its enable toggle on so the value actually takes effect. `pairs` = [(key, toggle)]."""
    for key, toggle in pairs:
        if key in params:
            _try_set(node, toggle, True)


def _geo_or_none(n):
    try:
        return n.geometry()
    except Exception:  # noqa: BLE001
        return None


def _finish_op(n, **extra):
    """Report counts when the node cooked; otherwise cooked:false + errors (never crash on a
    not-yet-cooked / input-starved node — guards BOTH the cook and the geometry readback)."""
    r = {"node": n.path()}
    try:
        n.cook()
    except Exception:  # noqa: BLE001 — surfaced via n.errors() below
        pass
    g = _geo_or_none(n)
    if g is None:
        r["cooked"] = False
        e = [str(x) for x in (n.errors() or [])]
        if e:
            r["errors"] = e
    else:
        r["cooked"] = True
        r["points"] = len(g.points())
        r["prims"] = len(g.prims())
    r.update(extra)
    return r


def _fresh_geo(name):
    """A fresh /obj geo that FAILS on name collision (never destroys existing user work). Mirrors the
    ingest.py generator idiom (usd_import_sop is a generator, not an operator)."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("geo", name) if name else obj.createNode("geo")


# reused menu token tuples
_LOCALSCALE = ("none", "constant", "featuresize", "attribute")
_USD_TRAVERSAL = ("std:components", "std:boundables", "std:groups", "none")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SOP tet / FEM-prep
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("tetrahedralize")
def tetrahedralize(params):
    """Tetrahedralize — fill a CLOSED input surface with a tetrahedral (tet) mesh (tetrahedralize) —
    the entry point for FEM / soft-body / finite-element prep. `input` (a watertight polygon mesh) is
    input 0; optional `points` (input 1) seeds extra Delaunay points. mode: conform (fill the volume) |
    refine (refine an existing tet mesh) | convexhull | detect; output: tetrahedra | polytet | polygons
    | polyline; use_quality + max_radius_edge_ratio / min_dihedral_angle bound tet quality;
    use_uniform_max_size + uniform_max_size cap tet size; max_iterations the repair passes. Emits a tet
    mesh feed for tet_surface / tet_partition / tet_fracture."""
    n = child_after(params["input"], "tetrahedralize", params.get("name"))
    if params.get("points"):
        bridge_input(n, params["points"], index=1, name_hint="points")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("batch", "batch", "m", ("entire", "connected", "attrib")),
        ("piece_attrib", "pieceattrib", "s", None),
        ("mode", "mode", "m", ("conform", "refine", "convexhull", "detect")),
        ("output", "output", "m", ("polyline", "tetrahedra", "polygons", "polytet")),
        ("keep_prims", "keepprims", "b", None),
        ("one_face_per_tet", "onefacepertet", "b", None),
        ("use_quality", "usequality", "b", None),
        ("max_radius_edge_ratio", "radedgetol", "f", (0.0, 1000.0)),
        ("min_dihedral_angle", "mindihedralang", "f", (0.0, 180.0)),
        ("use_uniform_max_size", "useuniformmaxsize", "b", None),
        ("uniform_max_size", "uniformmaxsize", "f", (0.0, 1e6)),
        ("max_iterations", "maxiter", "i", (0, 100000)),
        ("random_seed", "randomseed", "i", (0, 1000000)),
        ("handle_failure", "failures", "m", ("removefailed", "keepfailed", "failonerror")),
    ])
    if "max_iterations" in params:
        _try_set(n, "usemaxiter", True)
    return _finish_op(n)


@endpoint("tet_conform")
def tet_conform(params):
    """Tet Conform — build a boundary-CONFORMING tet mesh whose surface matches the input polygons
    (tetconform) — a higher-quality volumetric mesh than a plain fill when the surface must be honoured.
    `input` (polygon mesh) is input 0; optional `points` (additional points/curves) is input 1.
    use_base_size + base_size set the target tet size; local_scaling (none | constant | featuresize |
    attribute) + scale_constant / local_feature_scale / scale_attrib vary density; preserve_input keeps
    the source; high_quality enforces quality; use_sdf + voxel_size fill cavities via an SDF."""
    n = child_after(params["input"], "tetconform", params.get("name"))
    if params.get("points"):
        bridge_input(n, params["points"], index=1, name_hint="points")
    _apply(n, params, [
        ("use_base_size", "usebasesize", "b", None),
        ("base_size", "basesize", "f", (0.0, 1e6)),
        ("use_max_tet_scale", "usemaxtetscale", "b", None),
        ("max_tet_scale", "maxtetscale", "f", (0.0, 1e6)),
        ("local_scaling", "localscaling", "m", _LOCALSCALE),
        ("scale_constant", "scaleconst", "f", (0.0, 1e6)),
        ("local_feature_scale", "scalelocalfeature", "f", (0.0, 1e6)),
        ("scale_attrib", "scaleattrib", "s", None),
        ("preserve_input", "preserveinputgeometry", "b", None),
        ("one_face_per_tet", "onefacepertet", "b", None),
        ("add_surface_triangles", "outputsurftri", "b", None),
        ("allow_surface_mods", "allowsurfacemods", "b", None),
        ("high_quality", "hiquality", "b", None),
        ("use_sdf", "usesdf", "b", None),
        ("voxel_size", "voxelsize", "f", (0.0, 1e6)),
    ])
    return _finish_op(n)


@endpoint("tet_embed")
def tet_embed(params):
    """Tet Embed — embed the input surface inside a coarser background tet lattice (tetembed) — the fast
    FEM/soft-body prep when you want a simulatable tet cage AROUND detailed geometry rather than a
    surface-conforming mesh. `input` (polygon mesh) is input 0; optional `points` (input 1). base_size /
    max_tet_scale / min_triangle_scale size the lattice; local_scaling + scale_* vary density;
    enlarge_input + enlarge_offset grow the cage past the surface; use_voxel_size + voxel_size or
    use_max_res + max_resolution set the discretization."""
    n = child_after(params["input"], "tetembed", params.get("name"))
    if params.get("points"):
        bridge_input(n, params["points"], index=1, name_hint="points")
    _apply(n, params, [
        ("use_base_size", "usebasesize", "b", None),
        ("base_size", "basesize", "f", (0.0, 1e6)),
        ("max_tet_scale", "maxtetscale", "f", (0.0, 1e6)),
        ("min_triangle_scale", "surftriscale", "f", (0.0, 1e6)),
        ("local_scaling", "localscaling", "m", _LOCALSCALE),
        ("scale_constant", "scaleconst", "f", (0.0, 1e6)),
        ("local_feature_scale", "scalelocalfeature", "f", (0.0, 1e6)),
        ("scale_attrib", "scaleattrib", "s", None),
        ("add_surface_triangles", "outputsurftri", "b", None),
        ("enlarge_input", "coverinput", "b", None),
        ("enlarge_offset", "voxeloffset", "f", (0.0, 1e6)),
        ("use_voxel_size", "usevoxelsize", "b", None),
        ("voxel_size", "voxelsize", "f", (0.0, 1e6)),
        ("use_max_res", "usemaxres", "b", None),
        ("max_resolution", "maxres", "i", (1, 100000)),
    ])
    return _finish_op(n)


@endpoint("tet_layer")
def tet_layer(params):
    """Tet Layer — build a single tet layer of a given thickness off a surface (tetlayer) — quick
    volumetric shells for FEM skin/rind or a starting tet band. `input` (surface polygons) is input 0.
    direction: interior (grow inward) | exterior (grow outward); thickness the layer depth;
    thickness_multiplier_attrib (+ its enable) modulates thickness per point; create_boundary_triangles
    caps the new boundary; create_tets emits tets (else just the layered points/prims)."""
    n = child_after(params["input"], "tetlayer", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("direction", "direction", "m", ("interior", "exterior")),
        ("thickness", "thickness", "f", (0.0, 1e6)),
        ("thickness_multiplier_attrib", "thicknessmultiplierattribute", "s", None),
        ("create_boundary_triangles", "createboundarytriangles", "b", None),
        ("create_tets", "createtets", "b", None),
    ])
    if "thickness_multiplier_attrib" in params:
        _try_set(n, "enablethicknessmultiplierattribute", True)
    return _finish_op(n)


@endpoint("tet_partition")
def tet_partition(params):
    """Tet Partition — split a tet mesh into named pieces using region-boundary polygons (tetpartition)
    — carve a solid into FEM regions / fracture chunks. `input` (a TET mesh, e.g. from tetrahedralize)
    is input 0; `boundaries` (region-boundary polygons) is input 1 and is REQUIRED. tet_group /
    polygon_group restrict the source; piece_attrib names the per-piece primitive attribute written on
    the result. Without the `boundaries` input it degrades to cooked:false."""
    n = child_after(params["input"], "tetpartition", params.get("name"))
    if params.get("boundaries"):
        bridge_input(n, params["boundaries"], index=1, name_hint="boundaries")
    _apply(n, params, [
        ("tet_group", "tetgroup", "s", None),
        ("polygon_group", "polygroup", "s", None),
        ("piece_attrib", "attrib", "s", None),
    ])
    return _finish_op(n)


@endpoint("tet_surface")
def tet_surface(params):
    """Tet Surface — extract the outer surface polygons of a tet mesh (tetrasurface) — get a renderable
    / collidable skin back from a volumetric tet mesh. `input` (a TET mesh) is input 0. keep_primitives
    keeps the source tets alongside the surface; keep_points keeps interior points; build_polysoup emits
    a lightweight polygon-soup surface."""
    n = child_after(params["input"], "tetrasurface", params.get("name"))
    _apply(n, params, [
        ("keep_primitives", "keepprimitives", "b", None),
        ("keep_points", "keeppoints", "b", None),
        ("build_polysoup", "buildpolysoup", "b", None),
    ])
    return _finish_op(n)


@endpoint("tet_strata")
def tet_strata(params):
    """Tet Strata — build layered (stratified) tet shells between an outer surface and an inner boundary
    (tetstrata) — multi-layer FEM materials (skin/fat/muscle rinds, laminated solids). `input` (outer
    polygon mesh) is input 0; optional `inner_surface` (inner boundary) is input 1. exterior_thickness /
    exterior_tet_layers build the outer regular layers; interior_thickness / interior_tet_layers the
    inner regular layers; create_exterior_layers / create_interior_layers toggle each band;
    preserve_input keeps the source prims."""
    n = child_after(params["input"], "tetstrata", params.get("name"))
    if params.get("inner_surface"):
        bridge_input(n, params["inner_surface"], index=1, name_hint="inner_surface")
    _apply(n, params, [
        ("create_exterior_layers", "createexteriorlayers", "b", None),
        ("exterior_thickness", "exteriorthickness", "f", (0.0, 1e6)),
        ("exterior_tet_layers", "exteriortetlayers", "i", (0, 1000)),
        ("create_interior_layers", "createinteriorlayers", "b", None),
        ("interior_thickness", "interiorthickness", "f", (0.0, 1e6)),
        ("interior_tet_layers", "interiortetlayers", "i", (0, 1000)),
        ("preserve_input", "preserveinputgeometry", "b", None),
    ])
    return _finish_op(n)


@endpoint("tet_fracture")
def tet_fracture(params):
    """Tet Fracture — fracture geometry into tet-based chunks via a Voronoi / pattern split (tetfracture)
    — pre-fracture solids for FEM/RBD destruction. `input` (geometry to fracture — a tet mesh or solid)
    is input 0. use_base_size + base_size set the chunk size; part_scale scales the pieces; voronoi
    toggles Voronoi fracturing; split_primitives splits the prims at piece boundaries; visualize_pieces
    randomly colours the pieces."""
    n = child_after(params["input"], "tetfracture", params.get("name"))
    _apply(n, params, [
        ("use_base_size", "usebasesize", "b", None),
        ("base_size", "basesize", "f", (0.0, 1e6)),
        ("part_scale", "partscale", "f", (0.0, 1e6)),
        ("voronoi", "voronoi", "b", None),
        ("split_primitives", "splitprims", "b", None),
        ("visualize_pieces", "visualizepieces", "b", None),
    ])
    return _finish_op(n)


@endpoint("solid_embed")
def solid_embed(params):
    """Solid Embed — embed the input geometry in a solid tet lattice sized by a single element scale
    (solidembed) — the one-knob FEM cage builder. `input` is input 0. element_scale sets the tet element
    size relative to the geometry (smaller = denser lattice). Emits an embedding tet mesh carrying the
    original geometry."""
    n = child_after(params["input"], "solidembed", params.get("name"))
    _apply(n, params, [
        ("element_scale", "elementscale", "f", (0.0001, 1e6)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# topo transfer / slide
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("topo_transfer")
def topo_transfer(params):
    """Topo Transfer — wrap a clean TEMPLATE mesh onto a TARGET mesh, transferring the template's
    topology onto the target's shape (topotransfer) — the retopo/character workhorse for matching a
    rigged base mesh to a scan/sculpt. `input` (the template mesh whose topology you keep) is input 0;
    `target` (the shape to wrap onto) is input 1 and is REQUIRED; optional `template_landmarks` (input
    2) + `target_landmarks` (input 3) pin correspondences. constraint_selection (auto | manual);
    iterations / reduced_levels the multiresolution solve; solver_type (nonlinear | linear) +
    solver_iterations; rigid_mask / rigid_primitives hold regions rigid; use_landmark_labels +
    landmark_attrib read landmark correspondences from an attribute. Without `target` it degrades to
    cooked:false."""
    n = child_after(params["input"], "topotransfer", params.get("name"))
    if params.get("target"):
        bridge_input(n, params["target"], index=1, name_hint="target")
    if params.get("template_landmarks"):
        bridge_input(n, params["template_landmarks"], index=2, name_hint="template_landmarks")
    if params.get("target_landmarks"):
        bridge_input(n, params["target_landmarks"], index=3, name_hint="target_landmarks")
    _apply(n, params, [
        ("enable_solve", "enablesolve", "b", None),
        ("enable_geometry_constraints", "enablegeometryconstraints", "b", None),
        ("constraint_selection", "constraintselection", "m", ("auto", "manual")),
        ("iterations", "iterations", "i", (0, 100000)),
        ("reduced_levels", "reducedlevels", "i", (0, 100)),
        ("solver_type", "solvertype", "m", ("nonlinear", "linear")),
        ("solver_iterations", "solveriterations", "i", (0, 100000)),
        ("rigid_mask", "rigidmask", "s", None),
        ("mask_mode", "maskmode", "m", ("maskoff", "maskon")),
        ("rigid_primitives", "rigidprimitives", "s", None),
        ("distance_tolerance", "disttolerance", "f", (0.0, 1e6)),
        ("norm_tolerance", "normtolerance", "f", (0.0, 1e6)),
        ("use_landmark_labels", "uselandmarklabels", "b", None),
        ("landmark_attrib", "landmarkattrib", "s", None),
    ])
    return _finish_op(n)


@endpoint("topo_slide")
def topo_slide(params):
    """Topo Slide — slide a target mesh's points across its surface guided by matched reference/target
    CURVES, or run a curve-guided topo transfer (toposlidebycurverefs) — dial in retopo flow along
    seams/features procedurally. `input` (target geometry to slide) is input 0; optional `reference_geo`
    (input 1), `reference_curves` (input 2) and `target_curves` (input 3) supply the guides. solve_mode
    (topotransfer | slide); blur_iterations / blur_step_size smooth the motion; match_curves pairs the
    curves up; blend the effect strength; mask_attrib / mask_by_radius + radius / radius_attrib localize
    the effect. (The node also ships interactive curve-EDIT buttons; those are not exposed — feed
    procedurally-built curves through the aux inputs instead.)"""
    n = child_after(params["input"], "toposlidebycurverefs", params.get("name"))
    if params.get("reference_geo"):
        bridge_input(n, params["reference_geo"], index=1, name_hint="reference_geo")
    if params.get("reference_curves"):
        bridge_input(n, params["reference_curves"], index=2, name_hint="reference_curves")
    if params.get("target_curves"):
        bridge_input(n, params["target_curves"], index=3, name_hint="target_curves")
    _apply(n, params, [
        ("solve_mode", "solvemode", "m", ("topotransfer", "slide")),
        ("blur_iterations", "bluriterations", "i", (0, 100000)),
        ("blur_step_size", "blurstepsize", "f", (0.0, 1000.0)),
        ("match_curves", "matchcurves", "b", None),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("use_mask_attrib", "usemaskattrib", "b", None),
        ("mask_attrib", "maskattrib", "s", None),
        ("mask_by_radius", "maskbyradius", "b", None),
        ("radius", "radius", "f", (0.0, 1e6)),
        ("use_radius_attrib", "useradiusattrib", "b", None),
        ("radius_attrib", "radiusattrib", "s", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SOP <-> USD bridges
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("usd_import_sop")
def usd_import_sop(params):
    """Import a USD file into SOP geometry inside a fresh /obj geo (the SOP-context `usdimport` — the
    read bridge from a USD stage down into native Houdini SOPs). name = new /obj geo (FAILS on
    collision — never destroys existing work). file = the .usd/.usda/.usdc/.usdz to read (realpath
    READ-confined to the working directory). primitives = a USD primitive-pattern to import (default
    all); traversal (std:components | std:boundables | std:groups | none) picks what counts as a leaf;
    unpack=true unpacks to native geometry (geometry_type = polygons | packedprims), unpack=false keeps
    lightweight packed-USD prims (feed those to unpack_usd). path_attrib / name_attrib write the source
    USD path / name onto the geometry; import_frame samples the stage at a frame; missing_file
    (error | empty) picks the behaviour when the file is absent. Does NOT force the cook."""
    name = params.get("name")
    path = confined_path(params["file"])  # realpath READ-confined
    geo = _fresh_geo(name)
    n = geo.createNode("usdimport")
    _try_set(n, "filepath1", path)
    _apply(n, params, [
        ("primitives", "primpattern", "s", None),
        ("traversal", "importtraversal", "ms", _USD_TRAVERSAL),
        ("path_attrib", "pathattrib", "s", None),
        ("name_attrib", "nameattrib", "s", None),
        ("import_frame", "importtime", "f", (-1e6, 1e6)),
        ("unpack", "input_unpack", "b", None),
        ("geometry_type", "unpack_geomtype", "m", ("packedprims", "polygons")),
        ("display_as", "viewportlod", "m", ("full", "points", "box", "centroid", "hidden")),
        ("pivot", "pivot", "m", ("origin", "centroid")),
        ("missing_file", "missingfile", "m", ("error", "empty")),
    ])
    disp = bool(params.get("display", False))
    n.setDisplayFlag(disp)
    n.setRenderFlag(True)
    geo.setDisplayFlag(disp)
    geo.layoutChildren()
    return {"node": geo.path(), "sop": n.path(), "file": path}


@endpoint("usd_export_sop")
def usd_export_sop(params):
    """Write the `input` SOP geometry to a USD file (the SOP-context `usdexport` — the write bridge from
    native SOPs up to a USD stage; executes the write via the node's own Save-to-Disk). `input` is input
    0; output = the .usd/.usda/.usdc/.usdz path (realpath WRITE-confined to the working directory).
    import_group + group_type (primitive | point) restrict what's exported; path_prefix sets the USD
    scenegraph prefix; transform (none | world) bakes world placement; kind_authoring
    (none | component | nestedgroup | nestedassembly) authors USD kinds; set_default_prim marks a
    default prim; frames = [start, end] writes an animated stage over the range. On a non-commercial
    Houdini the written file carries a forced .usdnc extension — the returned `output` reflects the path
    ACTUALLY written (with requested_output echoing what was asked). The node's pre/post-render SCRIPT
    params are never exposed or set."""
    out_path = confined_path(params["output"])  # realpath WRITE-confined
    n = child_after(params["input"], "usdexport", params.get("name"))
    _try_set(n, "lopoutput", out_path)
    _apply(n, params, [
        ("import_group", "group", "s", None),
        ("group_type", "grouptype", "ms", ("primitive", "point")),
        ("path_prefix", "pathprefix", "s", None),
        ("transform", "xformtype", "m", ("none", "world")),
        ("kind_authoring", "kindschema", "ms",
         ("none", "component", "nestedgroup", "nestedassembly")),
        ("set_default_prim", "setdefaultprim", "b", None),
    ])
    _enable(n, params, [
        ("import_group", "enable_group"), ("group_type", "enable_grouptype"),
        ("path_prefix", "enable_pathprefix"), ("kind_authoring", "enable_kindschema"),
        ("set_default_prim", "enable_setdefaultprim"),
    ])
    frames = params.get("frames")
    if frames and len(frames) == 2:
        _try_set(n, "trange", 1)  # 'normal' = write the range
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        _try_set(n, "f1", f1)
        _try_set(n, "f2", f2)
    ep = n.parm("execute")
    if ep is not None:
        ep.pressButton()  # executable-confined write (SOP usdexport has no HOM .render())
    # Non-commercial Houdini forces `.usdnc`; return the path that actually landed.
    actual = out_path
    if not os.path.exists(actual):
        nc = os.path.splitext(out_path)[0] + ".usdnc"
        if os.path.exists(nc):
            actual = nc
    return {"node": n.path(), "output": actual, "requested_output": out_path,
            "written": os.path.exists(actual)}


@endpoint("usd_configure_sop")
def usd_configure_sop(params):
    """Configure how SOP geometry will be authored to USD — set stage-wide import options as USD
    metadata on the geometry (the SOP-context `usdconfigure`; a pure operator, NO file write). `input`
    is input 0 (optional). import_group + group_type (primitive | point) restrict scope; path_prefix
    the scenegraph prefix; kind_authoring (none | component | nestedgroup | nestedassembly);
    topology (animated | static | none) how mesh topology is time-sampled; set_default_prim marks a
    default prim; sample_frame the frame to sample. Pairs with usd_export_sop / the USD ROP downstream —
    it stamps the config, it does not write a file."""
    n = child_after(params["input"], "usdconfigure", params.get("name"))
    _apply(n, params, [
        ("import_group", "group", "s", None),
        ("group_type", "grouptype", "ms", ("primitive", "point")),
        ("path_prefix", "pathprefix", "s", None),
        ("kind_authoring", "kindschema", "ms",
         ("none", "component", "nestedgroup", "nestedassembly")),
        ("topology", "topology", "ms", ("animated", "static", "none")),
        ("set_default_prim", "setdefaultprim", "b", None),
        ("sample_frame", "sampleframe", "f", (-1e6, 1e6)),
    ])
    _enable(n, params, [
        ("import_group", "enable_group"), ("group_type", "enable_grouptype"),
        ("path_prefix", "enable_pathprefix"), ("kind_authoring", "enable_kindschema"),
        ("topology", "enable_topology"), ("set_default_prim", "enable_setdefaultprim"),
        ("sample_frame", "enable_sampleframe"),
    ])
    return _finish_op(n)


@endpoint("usd_configure_geometry")
def usd_configure_geometry(params):
    """Author per-primitive USD geometry metadata on SOP geometry (the SOP-context
    `usdconfiguregeometry`; a pure operator, NO file write). `input` is input 0 (optional). group
    restricts the prims; prim_path sets the USD scenegraph path; prim_name the leaf name;
    subdivision_scheme (none | catmullClark | loop | bilinear) tags meshes as subdivs; visibility
    (inherit | invisible); purpose (a USD purpose token); active toggles the prim active flag. Stamps
    the USD prim config the export will honour."""
    n = child_after(params["input"], "usdconfiguregeometry", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("prim_name", "name", "s", None),
        ("prim_path", "path", "s", None),
        ("subdivision_scheme", "subdivscheme", "ms",
         ("none", "catmullClark", "loop", "bilinear")),
        ("visibility", "visibility", "ms", ("inherit", "invisible")),
        ("purpose", "purpose", "s", None),
        ("active", "active", "b", None),
    ])
    _enable(n, params, [
        ("prim_name", "enable_name"), ("prim_path", "enable_path"),
        ("subdivision_scheme", "enable_subdivscheme"), ("visibility", "enable_visibility"),
        ("purpose", "enable_purpose"), ("active", "enable_active"),
    ])
    return _finish_op(n)


@endpoint("usd_configure_prims_from_points")
def usd_configure_prims_from_points(params):
    """Author USD prim attributes from POINTS — turn points into configured USD prims (spheres, lights,
    xforms…) with per-prim metadata (the SOP-context `usdconfigureprimsfrompoints`; a pure operator, NO
    file write). `input` (points) is input 0 (optional). group restricts the points; prim_type the USD
    prim type token; prim_path / prim_name the scenegraph location; color [r,g,b], radius, size shape
    the prims; visibility (inherit | invisible); purpose / kind USD tokens. Great for scattering
    configured USD prims (e.g. an instancer feed) from a point cloud."""
    n = child_after(params["input"], "usdconfigureprimsfrompoints", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("prim_type", "primtype", "s", None),
        ("prim_path", "path", "s", None),
        ("prim_name", "name", "s", None),
        ("radius", "radius", "f", (0.0, 1e6)),
        ("size", "size", "f", (0.0, 1e6)),
        ("visibility", "visibility", "ms", ("inherit", "invisible")),
        ("purpose", "purpose", "s", None),
        ("kind", "kind", "s", None),
    ])
    if "color" in params and len(params["color"]) == 3:
        c = params["color"]
        _try_set(n, "colorr", float(c[0]))
        _try_set(n, "colorg", float(c[1]))
        _try_set(n, "colorb", float(c[2]))
    _enable(n, params, [
        ("prim_type", "enable_primtype"), ("prim_path", "enable_path"), ("prim_name", "enable_name"),
        ("color", "enable_color"), ("radius", "enable_radius"), ("size", "enable_size"),
        ("visibility", "enable_visibility"), ("purpose", "enable_purpose"), ("kind", "enable_kind"),
    ])
    return _finish_op(n)


@endpoint("unpack_usd")
def unpack_usd(params):
    """Unpack packed-USD primitives into native Houdini geometry (unpackusd) — turn the lightweight
    packed prims from usd_import_sop (unpack=false) into editable polygons/points. `input` (packed USD
    prims) is input 0. group restricts which prims to unpack; output (packedprims | polygons) the
    result type; traversal (std:components | std:boundables | std:groups | none) how deep to descend;
    delete_original drops the source packed prims; limit_iterations + iterations cap recursion depth;
    pivot (origin | centroid); add_path_attrib / path_attrib + add_name_attrib / name_attrib write
    provenance attributes; transfer_attributes / import_primvars carry USD data down onto the geometry."""
    n = child_after(params["input"], "unpackusd", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("output", "output", "m", ("packedprims", "polygons")),
        ("traversal", "unpacktraversal", "ms", _USD_TRAVERSAL),
        ("delete_original", "deleteorig", "b", None),
        ("limit_iterations", "limititerations", "b", None),
        ("iterations", "iterations", "i", (0, 100000)),
        ("pivot", "pivot", "m", ("origin", "centroid")),
        ("add_path_attrib", "addpathattrib", "b", None),
        ("path_attrib", "pathattrib", "s", None),
        ("add_name_attrib", "addnameattrib", "b", None),
        ("name_attrib", "nameattrib", "s", None),
        ("transfer_attributes", "transferattributes", "s", None),
        ("import_primvars", "importprimvars", "s", None),
    ])
    return _finish_op(n)

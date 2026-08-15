"""SideFX Labs — Geometry/Algorithmic + Partition + Volume + Create. Data-only handlers, params
verified against live H21.0.671 via hython probe.

Two archetypes in this file:
  * Archetype A — generator / SOURCE (0 inputs): chaotic_shapes, mandelbulb_generator,
    wang_tiles_sample, wfc_initialize. Each builds a fresh /obj geo and cooks bare.
  * Archetype B — chain (has inputs): wang_tiles_decoder, connectivity_and_segmentation,
    multi_bounding_box, vdb_transform_properties, wavefunction_collapse_2d, wfc_sample_paint.
    Each uses child_after (auto input 0); second/third operands go through bridge_input.

SECURITY: only wfc_initialize carries a file surface (`filename`, an image READ used when its
texture mode is on) — it is routed through confined_path() and only set when the caller supplies it.
No node in this lane has a code/callback/snippet/opencl parm exposed. Exponential-cost knobs
(point counts, voxel size, solve attempts, bucket iterations) are hard-clamped and noted below.

NAMING: `labs::2d_wavefunctioncollapse::1.1` is wrapped as `wavefunction_collapse_2d` — a bare tool
name cannot begin with a digit.
SKIPPED: `labs::cut_geometry_to_partitions` (a TOP/PDG node, not a SOP — belongs to a later non-SOP
pass) and `labs::disc_generator` (redundant — already wrapped as `disc_generator` in
handlers/labs_mesh_create.py at the same highest version ::1.1).
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)






def _finish(geo, n):
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


def _stats(n):
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── ordered-menu label tuples (position == the node's stored index) ───────────────────────────────
# vdb_transform_properties `vectype` — index-stored menu with meaningful string labels.
_VECTYPE = ("invariant", "covariant", "covariant normalize",
            "contravariant relative", "contravariant absolute")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Archetype A — generators / SOURCE nodes (0 inputs, fresh /obj geo, bare cook)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

# ── 1. chaotic_shapes (generator; 0 inputs) ───────────────────────────────────────────────────────
@endpoint("chaotic_shapes")
def chaotic_shapes(params):
    """Labs Chaotic Shapes (labs::chaotic_shapes::1.0) — a fresh /obj geo holding a point cloud traced
    from a chaotic (strange-attractor) system. The four coefficients `a`/`b`/`c`/`d` shape the
    attractor; `pointcount` is how many iterations/points to trace (COST — hard-clamped to <=2,000,000).
    `computedensity` estimates a local point density (with `searchdistance`/`maxpts`) for downstream
    coloring/scaling. Fails on name collision. Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::chaotic_shapes::1.0")
    for k in ("a", "b", "c", "d"):
        if k in params:
            _try_set(n, k, clamp(float(params[k]), -1e4, 1e4))
    if "pointcount" in params:
        _try_set(n, "pointcount", int(clamp(int(params["pointcount"]), 1, 2_000_000)))  # COST
    if "computedensity" in params:
        _try_set(n, "computedensity", bool(params["computedensity"]))
    if "searchdistance" in params:
        _try_set(n, "searchdistance", clamp(float(params["searchdistance"]), 1e-5, 1e4))
    if "maxpts" in params:
        _try_set(n, "maxpts", int(clamp(int(params["maxpts"]), 1, 10000)))  # neighbour-search cap
    return _finish(geo, n)


# ── 2. mandelbulb_generator (generator; 0 inputs) ─────────────────────────────────────────────────
@endpoint("mandelbulb_generator")
def mandelbulb_generator(params):
    """Labs Mandelbulb Generator (labs::mandelbulb_generator::1.1) — a fresh /obj geo holding a 3D
    Mandelbulb fractal. `voxelsize` is the sampling resolution (COST — smaller explodes memory/time;
    hard-clamped to a floor of 0.005), `power`/`nvalue`/`iteration`/`phase` shape the fractal, `maxiter`
    is the escape-iteration cap (clamped <=200). `convertto` (ordered-menu index 0..3) picks the output
    representation; `npts` caps the emitted point budget (clamped <=2,000,000). `useocl` toggles the
    OpenCL evaluator (leave on where a GPU/OpenCL device is available). Fails on name collision.
    Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::mandelbulb_generator::1.1")
    if "voxelsize" in params:
        _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 0.005, 10.0))  # COST floor
    if "useocl" in params:
        _try_set(n, "useocl", bool(params["useocl"]))
    if "nvalue" in params:
        _try_set(n, "nvalue", clamp(float(params["nvalue"]), 0.0, 64.0))
    if "iteration" in params:
        _try_set(n, "iteration", clamp(float(params["iteration"]), 0.0, 1000.0))
    if "maxiter" in params:
        _try_set(n, "maxiter", int(clamp(int(params["maxiter"]), 1, 200)))  # COST
    if "phase" in params:
        _try_set(n, "phase", clamp(float(params["phase"]), -1e4, 1e4))
    if "power" in params:
        _try_set(n, "power", clamp(float(params["power"]), 0.0, 64.0))
    if "convertto" in params:
        _try_set(n, "convertto", int(clamp(int(params["convertto"]), 0, 3)))  # ordered-menu index
    if "npts" in params:
        _try_set(n, "npts", int(clamp(int(params["npts"]), 1, 2_000_000)))  # COST
    if "addcolor" in params:
        _try_set(n, "addcolor", bool(params["addcolor"]))
    return _finish(geo, n)


# ── 3. wang_tiles_sample (generator; 0 inputs) ────────────────────────────────────────────────────
@endpoint("wang_tiles_sample")
def wang_tiles_sample(params):
    """Labs Wang Tiles Sample (labs::wang_tiles_sample) — a fresh /obj geo holding a stochastic Wang-tile
    sampling (an aperiodic tiling seed set that the Wang Tiles Decoder later expands). `mode`
    (ordered-menu index 0..2) picks the sampling scheme; `bVertexColor` writes the tile code as vertex
    color; `bAlignAndDistribute` lays the tiles out on a grid. Fails on name collision. Data-only."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::wang_tiles_sample")
    if "mode" in params:
        _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 2)))  # ordered-menu index
    if "bVertexColor" in params:
        _try_set(n, "bVertexColor", bool(params["bVertexColor"]))
    if "bAlignAndDistribute" in params:
        _try_set(n, "bAlignAndDistribute", bool(params["bAlignAndDistribute"]))
    return _finish(geo, n)


# ── 4. wfc_initialize (generator; 0 inputs; file surface = image READ) ────────────────────────────
@endpoint("wfc_initialize")
def wfc_initialize(params):
    """Labs WFC Initialize (labs::wfc_initialize) — a fresh /obj geo holding a blank Wave-Function-
    Collapse grid (`rows` x `cols`, each clamped <=1024) that the WFC sample/paint tools then solve.
    With `bFromTexture` on, the grid resolution/seed is read from an input image at `filename`
    (SECURITY: confined to the working directory; only set when supplied). Fails on name collision."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::wfc_initialize")
    if "bFromTexture" in params:
        _try_set(n, "bFromTexture", bool(params["bFromTexture"]))
    if params.get("filename"):
        _try_set(n, "filename", confined_path(params["filename"]))  # SECURITY: image READ confined
    if "rows" in params:
        _try_set(n, "rows", int(clamp(int(params["rows"]), 1, 1024)))
    if "cols" in params:
        _try_set(n, "cols", int(clamp(int(params["cols"]), 1, 1024)))
    return _finish(geo, n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Archetype B — chain nodes (child_after auto-wires input 0)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

# ── 5. wang_tiles_decoder (chain; in0 point grid) ─────────────────────────────────────────────────
@endpoint("wang_tiles_decoder")
def wang_tiles_decoder(params):
    """Labs Wang Tiles Decoder (labs::wang_tiles_decoder) — decodes a Wang-tile point grid (`input`,
    input 0; e.g. a wang_tiles_sample output) into a `rows` x `cols` aperiodic tiling. `mMode` and
    `mColorChannel` (ordered-menu indices 0..2) pick the decode scheme and which colour channel carries
    the tile code; `bVertexColor` re-emits the tile colour. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::wang_tiles_decoder", params.get("name"))
    if "mMode" in params:
        _try_set(n, "mMode", int(clamp(int(params["mMode"]), 0, 2)))  # ordered-menu index
    if "mColorChannel" in params:
        _try_set(n, "mColorChannel", int(clamp(int(params["mColorChannel"]), 0, 2)))  # index
    if "rows" in params:
        _try_set(n, "rows", int(clamp(int(params["rows"]), 1, 512)))
    if "cols" in params:
        _try_set(n, "cols", int(clamp(int(params["cols"]), 1, 512)))
    if "bVertexColor" in params:
        _try_set(n, "bVertexColor", bool(params["bVertexColor"]))
    return _stats(n)


# ── 6. connectivity_and_segmentation (chain; in0 polygons) ────────────────────────────────────────
@endpoint("connectivity_and_segmentation")
def connectivity_and_segmentation(params):
    """Labs Connectivity and Segmentation (labs::connectivity_and_segmentation::1.0) — partitions the
    input polygons (`input`, input 0) into segments and writes a segment id to `segmentattrib`.
    `connectivitytoggle`+`connectmenu` (ordered-menu index 0..1) do plain connectivity; `inputattr`+
    `attrname` segment by an existing attribute; `buckettoggle`+`targetbucket` (clamped) do a k-means
    style clustering into ~N buckets seeded by `clusterseed`. The Refine group (`enable`, `depth`
    index 0..1, `extweight`, `iterations` clamped) cleans bucket boundaries. `edgegroupoutput`+
    `edgegroup` emit the segment-boundary edges as a group. Data-only (attribute/group names are
    labels, not paths)."""
    n = child_after(params["input"], "labs::connectivity_and_segmentation::1.0", params.get("name"))
    if "connectivitytoggle" in params:
        _try_set(n, "connectivitytoggle", bool(params["connectivitytoggle"]))
    if "connectmenu" in params:
        _try_set(n, "connectmenu", int(clamp(int(params["connectmenu"]), 0, 1)))  # ordered-menu index
    if "inputattr" in params:
        _try_set(n, "inputattr", bool(params["inputattr"]))
    if "attrname" in params:
        _try_set(n, "attrname", str(params["attrname"]))
    if "buckettoggle" in params:
        _try_set(n, "buckettoggle", bool(params["buckettoggle"]))
    if "targetbucket" in params:
        _try_set(n, "targetbucket", int(clamp(int(params["targetbucket"]), 1, 1_000_000)))
    if "clusterseed" in params:
        _try_set(n, "clusterseed", clamp(float(params["clusterseed"]), -1e9, 1e9))
    if "enable" in params:
        _try_set(n, "enable", bool(params["enable"]))
    if "depth" in params:
        _try_set(n, "depth", int(clamp(int(params["depth"]), 0, 1)))  # ordered-menu index
    if "extweight" in params:
        _try_set(n, "extweight", clamp(float(params["extweight"]), 0.0, 1e4))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 100)))  # COST
    if "segmentattrib" in params:
        _try_set(n, "segmentattrib", str(params["segmentattrib"]))
    if "edgegroupoutput" in params:
        _try_set(n, "edgegroupoutput", bool(params["edgegroupoutput"]))
    if "edgegroup" in params:
        _try_set(n, "edgegroup", str(params["edgegroup"]))
    return _stats(n)


# ── 7. multi_bounding_box (chain; in0 mesh) ───────────────────────────────────────────────────────
@endpoint("multi_bounding_box")
def multi_bounding_box(params):
    """Labs Multi Bounding Box (labs::multi_bounding_box) — builds bounding boxes over the input mesh
    (`input`, input 0). `iOutputMode` (ordered index) selects the output flavour (e.g. one box for the
    whole mesh vs. a subdivided grid of boxes); `divisions` sets the subdivision count (clamped <=256);
    `isolate_index`+`index` emit just one cell. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::multi_bounding_box", params.get("name"))
    if "iOutputMode" in params:
        _try_set(n, "iOutputMode", int(clamp(int(params["iOutputMode"]), 0, 8)))  # ordered index
    if "divisions" in params:
        _try_set(n, "divisions", int(clamp(int(params["divisions"]), 1, 256)))  # COST
    if "isolate_index" in params:
        _try_set(n, "isolate_index", bool(params["isolate_index"]))
    if "index" in params:
        _try_set(n, "index", int(clamp(int(params["index"]), 0, 1_000_000)))
    return _stats(n)


# ── 8. vdb_transform_properties (chain; in0 volume/VDB) ───────────────────────────────────────────
@endpoint("vdb_transform_properties")
def vdb_transform_properties(params):
    """Labs VDB Transform Properties (labs::vdb_transform_properties::1.0) — re-derives a vector VDB's
    values under the volume's own transform. `input` (input 0) is the volume/VDB stream; `sourcefield`
    names the vector VDB to transform (default `vel`); `vectype` picks the transform law (invariant |
    covariant | covariant normalize | contravariant relative | contravariant absolute). `removesource`
    drops the original field after transforming. Data-only (field name is a label, not a path)."""
    n = child_after(params["input"], "labs::vdb_transform_properties::1.0", params.get("name"))
    if "sourcefield" in params:
        _try_set(n, "sourcefield", str(params["sourcefield"]))
    if "vectype" in params:
        _menu_set(n, "vectype", str(params["vectype"]), _VECTYPE)
    if "removesource" in params:
        _try_set(n, "removesource", bool(params["removesource"]))
    return _stats(n)


# ── 9. wavefunction_collapse_2d (chain; in0 Output Grid, in1 Sample Grid) ─────────────────────────
@endpoint("wavefunction_collapse_2d")
def wavefunction_collapse_2d(params):
    """Labs 2D Wave Function Collapse (labs::2d_wavefunctioncollapse::1.1) — synthesises a larger 2D
    tiling that locally resembles a small colour sample. `input` (input 0) = the OUTPUT GRID whose size
    is filled; `sample` (input 1) = the SAMPLE GRID whose per-cell colour supplies the patterns (BOTH
    required to cook). `iPatternSearchSize` (clamped <=8) is the pattern neighbourhood; `iSeed` seeds
    the solve; `bGenerateRotations`/`bPeriodicInputPatterns`/`bTileableOutput` expand or constrain the
    pattern set; `bAutomaticInputSizeDetection`/`bAutomaticOutputSizeDetection` read the grid sizes from
    the inputs; `iNumSolveAttempts` (clamped) retries a failed collapse. Data-only (no file surface).
    NOTE: tool named `wavefunction_collapse_2d` — a bare name cannot start with a digit."""
    n = child_after(params["input"], "labs::2d_wavefunctioncollapse::1.1", params.get("name"))
    bridge_input(n, params["sample"], index=1, name_hint="sample")  # Sample Grid (input 1, required)
    if "bAutomaticInputSizeDetection" in params:
        _try_set(n, "bAutomaticInputSizeDetection", bool(params["bAutomaticInputSizeDetection"]))
    if "iPatternSearchSize" in params:
        _try_set(n, "iPatternSearchSize", int(clamp(int(params["iPatternSearchSize"]), 1, 8)))  # COST
    if "bPeriodicInputPatterns" in params:
        _try_set(n, "bPeriodicInputPatterns", bool(params["bPeriodicInputPatterns"]))
    if "bAutomaticOutputSizeDetection" in params:
        _try_set(n, "bAutomaticOutputSizeDetection", bool(params["bAutomaticOutputSizeDetection"]))
    if "bGenerateRotations" in params:
        _try_set(n, "bGenerateRotations", bool(params["bGenerateRotations"]))
    if "bTileableOutput" in params:
        _try_set(n, "bTileableOutput", bool(params["bTileableOutput"]))
    if "iSeed" in params:
        _try_set(n, "iSeed", int(params["iSeed"]))
    if "iNumSolveAttempts" in params:
        _try_set(n, "iNumSolveAttempts", int(clamp(int(params["iNumSolveAttempts"]), 1, 100)))  # COST
    return _stats(n)


# ── 10. wfc_sample_paint (chain; in0 WFC Grid, in1 Modules opt) ───────────────────────────────────
@endpoint("wfc_sample_paint")
def wfc_sample_paint(params):
    """Labs WFC Sample Paint (labs::wfc_sample_paint) — the paint front-end for the Wave-Function-
    Collapse workflow: `input` (input 0) = the WFC grid (a wfc_initialize output); optional `modules`
    (input 1) = the tile/module set. This is fundamentally an INTERACTIVE paint SOP — the actual
    constraint strokes are drawn in the viewport and cannot be issued head-lessly; the data-only
    wrapper wires the inputs, toggles `displaygroup`, and sets the `domirror`/`mirror_t`/`mirror_dir`
    symmetry so a downstream solve is set up. All brush/stroke/callback parms are left at default.
    Data-only (no file surface)."""
    n = child_after(params["input"], "labs::wfc_sample_paint", params.get("name"))
    if params.get("modules"):
        bridge_input(n, params["modules"], index=1, name_hint="modules")  # Modules (input 1, opt)
    if "displaygroup" in params:
        _try_set(n, "displaygroup", bool(params["displaygroup"]))
    if "domirror" in params:
        _try_set(n, "domirror", bool(params["domirror"]))
    if "mirror_t" in params:
        _try_set(n, "mirror_t", clamp(float(params["mirror_t"]), -1e6, 1e6))
    if "mirror_dir" in params:
        _try_set(n, "mirror_dir", clamp(float(params["mirror_dir"]), -1e6, 1e6))
    return _stats(n)

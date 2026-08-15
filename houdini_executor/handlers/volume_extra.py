"""SOP Volume / VDB lane — optional tier: the second, lower-frequency half of the Houdini 21
fog/SDF/VDB toolset that extends the core volume lane (houdini_executor/handlers/volume.py). It adds the
specialist processors: break / splice / stamp / patch a volume, convolve / FFT / normalize / compress
it, deform & rasterize a lattice, bake lighting, arrival-time & optical-flow & trail solves, ambient
occlusion, vector-noise detailing, colour / SDF painting, and the VDB utilities (convex-clip-sdf,
diagnostics, LOD, points-delete / points-group, rasterize-frustum, visualize-tree). Data-only handlers,
params + menu tokens verified against live H21.0.671 via hython probe.

Input dialect (probe-confirmed): every handler here is an OPERATOR — `input` is input 0 (the volume /
VDB / geometry to process), created with child_after; the node-specific extra inputs (points, reference
VDBs, lattices, masks, brushes, curves, convex hulls, goal images) are exposed as optional NodePath
params named for their spec label and wired at the exact index with bridge_input. `_finish_op` reports
counts once cooked and returns cooked:false + the node's errors when a node needs more of the network
wired, so the AI can keep assembling instead of crashing. Multi-component (vec2/vec3/array) parms and
`#` multiparm instances are intentionally not exposed — only the curated scalar/menu params are.

SECURITY: NO file-path parm and NO code/callback parm is exposed by ANY handler in this lane. The probe
found the hidden `vex_cwdpath` file parm on the factory-HDA `volumenoisevector` node — its internal VEX
is fixed and the user sets only noise data params, so `vex_cwdpath` is EXCLUDED entirely. `paintsdfvolume`
/ `paintcolorvolume` carry no file/code parm (their `stroke#_*` multiparm brush instances are skipped).
No `*path`/`file`/`vex*`/`script`/`shoppath`/`callback`/`sop`/`shop` parm is ever wrapped.
"""

import hou
from houdini_executor.server import (
    endpoint, child_after, clamp, resolve_node, bridge_input,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared helpers (probe-safe: never invent a parm) ──────────────────────────────────────────────
def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)






def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token: set the token directly (validated against the live token set)."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  m=index-menu(tokens)  ms=string-menu(tokens)."""
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


def _geo_or_none(n):
    """Return the node's geometry, or None if it hasn't cooked / errored (never raises opaquely)."""
    try:
        return n.geometry()
    except Exception:  # noqa: BLE001 — a cook error surfaces via n.errors() below, not a crash
        return None


def _finish_geo(geo, n):
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)
    geo.layoutChildren()
    g = _geo_or_none(n)
    if g is None:  # the generator MUST cook — surface the real diagnostic, not an opaque NoneType
        raise RuntimeError(f"{n.path()} failed to cook: " + "; ".join(n.errors()) or "no geometry")
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


def _finish_op(n, **extra):
    """child_after already set the display/render flags + showed the object. Report counts when the
    node has cooked; when it hasn't (a volume op that needs more of the network wired — e.g. a paint /
    velocity / rasterize node fed a bare volume), return cooked:false + the node's errors instead of
    crashing, so the AI can keep assembling the network and see what's missing."""
    r = {"node": n.path()}
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


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# CONVERT / DEFORM / RASTERIZE-LATTICE
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("lattice_from_volume")
def lattice_from_volume(params):
    """Lattice from Volume (latticefromvolume) — build a lattice / point grid matching a volume's voxel
    layout. `input` (input 0) is the Volumes to Convert; `ref_vdb` (input 1) an optional reference VDB
    for the transform. sampling picks voxel center vs corner; expand grows the grid; type picks the
    output topology (points / polyline / tetrahedron / hexahedron); createattribs adds index attribs."""
    n = child_after(params["input"], "latticefromvolume", params.get("name"))
    if params.get("ref_vdb"):
        bridge_input(n, params["ref_vdb"], index=1, name_hint="ref_vdb")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("sampling", "sampling", "m", ("center", "corner")),
        ("expand", "expand", "i", (0, 10)),
        ("type", "type", "m", ("points", "polyline", "tetrahedron", "hexahedron")),
        ("createattribs", "createattribs", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_deform")
def volume_deform(params):
    """Volume Deform (volumedeform) — deform a volume by a point-deform / moving lattice. `input`
    (input 0) is the Source Volumes; `lattice` (input 1) the Lattice Points driving the deform.
    dosmoothing smooths the result; partialupdate limits the rebuild; scalecompressed + domaxdensityscale
    /maxdensityscale preserve density; prune + prunetolerance drop empty voxels."""
    n = child_after(params["input"], "volumedeform", params.get("name"))
    if params.get("lattice"):
        bridge_input(n, params["lattice"], index=1, name_hint="lattice")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("dosmoothing", "dosmoothing", "b", None),
        ("partialupdate", "partialupdate", "b", None),
        ("scalecompressed", "scalecompressed", "b", None),
        ("domaxdensityscale", "domaxdensityscale", "b", None),
        ("maxdensityscale", "maxdensityscale", "f", (0.0, 10.0)),
        ("prune", "prune", "b", None),
        ("prunetolerance", "prunetolerance", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("volume_rasterize_lattice")
def volume_rasterize_lattice(params):
    """Volume Rasterize Lattice (volumerasterizelattice) — rasterize a moving lattice back into a
    volume. `input` (input 0) is the Target Volumes; `lattice` (input 1) the Lattice Points; `source_volumes`
    (input 2) the Source Volumes to sample. mode attribute/volume; deactivate all/lattice; attrib +
    sourcevols pick what is rasterized; dosmoothing/scalecompressed/domaxdensityscale/maxdensityscale/
    prune/prunetolerance shape the deposit."""
    n = child_after(params["input"], "volumerasterizelattice", params.get("name"))
    if params.get("lattice"):
        bridge_input(n, params["lattice"], index=1, name_hint="lattice")
    if params.get("source_volumes"):
        bridge_input(n, params["source_volumes"], index=2, name_hint="source_volumes")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("enable_preprocess", "enable_preprocess", "b", None),
        ("deactivate", "deactivate", "m", ("all", "lattice")),
        ("mode", "mode", "m", ("attribute", "volume")),
        ("attrib", "attrib", "s", None),
        ("sourcevols", "sourcevols", "s", None),
        ("dosmoothing", "dosmoothing", "b", None),
        ("scalecompressed", "scalecompressed", "b", None),
        ("domaxdensityscale", "domaxdensityscale", "b", None),
        ("maxdensityscale", "maxdensityscale", "f", (0.0, 10.0)),
        ("prune", "prune", "b", None),
        ("prunetolerance", "prunetolerance", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# BREAK / SPLICE / STAMP / PATCH — piecewise volume editing
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_break")
def volume_break(params):
    """Volume Break (volumebreak) — split / break geometry by an SDF volume cutter into pieces. `input`
    (input 0) is the Geometry; `volume` (input 1) the SDF Volume that decides the cut. breaktype
    fracture/outside/inside; closeholes noclose/flatclose/pyramidclose + closegeo seal the cut;
    snapdistance welds near-coincident points; creategroups + the *group names emit inside/outside
    (and closure) groups on the result."""
    n = child_after(params["input"], "volumebreak", params.get("name"))
    if params.get("volume"):
        bridge_input(n, params["volume"], index=1, name_hint="volume")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("breaktype", "breaktype", "m", ("fracture", "outside", "inside")),
        ("closeholes", "closeholes", "m", ("noclose", "flatclose", "pyramidclose")),
        ("closegeo", "closegeo", "b", None),
        ("snapdistance", "snapdistance", "f", (0.0, 1.0)),
        ("creategroups", "creategroups", "b", None),
        ("insidegroup", "insidegroup", "s", None),
        ("insideclosuregroup", "insideclosuregroup", "s", None),
        ("outsidegroup", "outsidegroup", "s", None),
        ("outsideclosuregroup", "outsideclosuregroup", "s", None),
    ])
    return _finish_op(n)


@endpoint("volume_splice")
def volume_splice(params):
    """Volume Splice (volumesplice) — splice / stitch tiled volume pieces back into one grid. `input`
    (input 0) is the tiled volume pieces. group restricts which volumes are spliced; deleteorig removes
    the source tile pieces once merged."""
    n = child_after(params["input"], "volumesplice", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("deleteorig", "deleteorig", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_stamp")
def volume_stamp(params):
    """Volume Stamp (volumestamp) — stamp a source volume into a destination volume at points. `input`
    (input 0) is the Base Volume; `points` (input 1) the Points to Instance at; `stamp_volumes`
    (input 2) the Volumes to Stamp. stamppts restricts the stamp points; mergemethod add/max/min;
    samples the per-point sample count; seed randomizes; dopremult/dounpremult manage premultiplication."""
    n = child_after(params["input"], "volumestamp", params.get("name"))
    if params.get("points"):
        bridge_input(n, params["points"], index=1, name_hint="points")
    if params.get("stamp_volumes"):
        bridge_input(n, params["stamp_volumes"], index=2, name_hint="stamp_volumes")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("stamppts", "stamppts", "s", None),
        ("mergemethod", "mergemethod", "m", ("add", "max", "min")),
        ("samples", "samples", "i", (1, 10)),
        ("seed", "seed", "f", (0.0, 10.0)),
        ("dopremult", "dopremult", "b", None),
        ("dounpremult", "dounpremult", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_patch")
def volume_patch(params):
    """Volume Patch (volumepatch) — patch a region of a volume with another volume (Poisson blend).
    `input` (input 0) is the Base Volume; `patch` (input 1) the Patch Volume; `mask` (input 2) the Mask.
    basegroup/patchgroup/maskgroup restrict each stream; maskcutoff the mask threshold; patchislaplacian
    treats the patch as a Laplacian; tolerance the solver tolerance."""
    n = child_after(params["input"], "volumepatch", params.get("name"))
    if params.get("patch"):
        bridge_input(n, params["patch"], index=1, name_hint="patch")
    if params.get("mask"):
        bridge_input(n, params["mask"], index=2, name_hint="mask")
    _apply(n, params, [
        ("basegroup", "basegroup", "s", None),
        ("patchgroup", "patchgroup", "s", None),
        ("maskgroup", "maskgroup", "s", None),
        ("maskcutoff", "maskcutoff", "f", (0.0, 1.0)),
        ("patchislaplacian", "patchislaplacian", "b", None),
        ("tolerance", "tolerance", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SIGNAL PROCESSING — convolve / FFT / normalize / compress / bin
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_convolve")
def volume_convolve(params):
    """Volume Convolve (volumeconvolve3) — apply a 3x3x3 convolution kernel to a volume. `input`
    (input 0) is the volume. normalize divides by the kernel weight sum; operation add/addabs/mul/max/min
    how neighbour samples combine. (The 3x3x3 kernel arrays are multi-component and left at their node
    defaults; endpoint named volume_convolve for readability.)"""
    n = child_after(params["input"], "volumeconvolve3", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("normalize", "normalize", "b", None),
        ("operation", "operation", "m", ("add", "addabs", "mul", "max", "min")),
    ])
    return _finish_op(n)


@endpoint("volume_fft")
def volume_fft(params):
    """Volume FFT (volumefft) — forward / inverse FFT of a volume (frequency domain). `input` (input 0)
    is the volume. centerdc shifts the DC term to the centre; invert runs the inverse transform;
    normalize scales the result; slices treats the volume as 2D slices; voxelplane picks the slice
    plane (xy / yz / zx)."""
    n = child_after(params["input"], "volumefft", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("centerdc", "centerdc", "b", None),
        ("invert", "invert", "b", None),
        ("normalize", "normalize", "b", None),
        ("slices", "slices", "b", None),
        ("voxelplane", "voxelplane", "m", ("xy", "yz", "zx")),
    ])
    return _finish_op(n)


@endpoint("volume_normalize")
def volume_normalize(params):
    """Volume Normalize Weights (volumenormalize) — normalize a set of volume weights / values. `input`
    (input 0) is the Volumes to Normalize. norm picks the norm (norm0 / norm1 / norm2 / norminf / limit1);
    norm0tol the norm0 tolerance; normalize toggles the normalization; threshold the low cutoff;
    addremainder redistributes the remainder; abs / clampzero / clampone shape the result."""
    n = child_after(params["input"], "volumenormalize", params.get("name"))
    _apply(n, params, [
        ("norm", "norm", "m", ("norm0", "norm1", "norm2", "norminf", "limit1")),
        ("norm0tol", "norm0tol", "f", (0.0, 10.0)),
        ("normalize", "normalize", "b", None),
        ("threshold", "threshold", "f", (0.0, 10.0)),
        ("addremainder", "addremainder", "b", None),
        ("abs", "abs", "b", None),
        ("clampzero", "clampzero", "b", None),
        ("clampone", "clampone", "b", None),
    ])
    return _finish_op(n)


@endpoint("volume_compress")
def volume_compress(params):
    """Volume Compress (volumecompress) — compress a volume's storage (tile / constant pruning). `input`
    (input 0) is the Volumes to Compress; `mask` (input 1) optional Mask Volumes. compression none/
    compress/uncompress/uncompressconstant; updatesettings persists the settings; constanttol/quantizetol
    the pruning tolerances; dither none/ordered; usefp16 stores half-float; maskgrp + domaskmin/maskmin /
    domaskmax/maskmax + invertmask gate the compression by a mask."""
    n = child_after(params["input"], "volumecompress", params.get("name"))
    if params.get("mask"):
        bridge_input(n, params["mask"], index=1, name_hint="mask")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("compression", "compression", "m", ("none", "compress", "uncompress", "uncompressconstant")),
        ("updatesettings", "updatesettings", "b", None),
        ("constanttol", "constanttol", "f", (0.0, 1.0)),
        ("quantizetol", "quantizetol", "f", (0.0, 1.0)),
        ("dither", "dither", "m", ("none", "ordered")),
        ("usefp16", "usefp16", "b", None),
        ("maskgrp", "maskgrp", "s", None),
        ("domaskmin", "domaskmin", "b", None),
        ("maskmin", "maskmin", "f", (-1.0, 1.0)),
        ("domaskmax", "domaskmax", "b", None),
        ("maskmax", "maskmax", "f", (-1.0, 1.0)),
        ("invertmask", "invertmask", "b", None),
    ])
    return _finish_op(n)


# NOTE: volumebin (Volume Bin) DEFERRED — it errors on cook across every headless config tried
# (needs a specifically-named/stenciled volume we couldn't demonstrate); not shipping an unverifiable
# endpoint. Revisit with a focused fixture later, alongside volumerasterize.


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SOLVERS — arrival time / optical flow / trail / ambient occlusion / bake
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_arrival_time")
def volume_arrival_time(params):
    """Volume Arrival Time (volumearrivaltime) — compute front-propagation arrival time through a speed
    volume. `input` (input 0) is the Speed Volumes; `start_points` (input 1) the Start Points. output_name
    names the arrival grid; normalize scales the output 0..1; cutoff caps the time; tol the solver
    tolerance; maxiter the iteration cap."""
    n = child_after(params["input"], "volumearrivaltime", params.get("name"))
    if params.get("start_points"):
        bridge_input(n, params["start_points"], index=1, name_hint="start_points")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("output_name", "name", "s", None),  # node's own output-grid name parm (renamed off mcp `name`)
        ("normalize", "normalize", "b", None),
        ("cutoff", "cutoff", "f", (0.0, 1000000.0)),  # spec range [0,10] clips default 1e6; widened
        ("tol", "tol", "f", (0.0, 1.0)),
        ("maxiter", "maxiter", "i", (0, 1000)),
    ])
    return _finish_op(n)


@endpoint("volume_optical_flow")
def volume_optical_flow(params):
    """Volume Optical Flow (volumeopticalflow) — estimate motion (optical flow) between two volumes.
    `input` (input 0) is the Source Image volume; `goal` (input 1) the Goal Image volume. group/goalgroup
    restrict each stream; tolerance the convergence tolerance; winradius the window radius; gaussian uses
    a Gaussian window; levels/pyramidscale the image pyramid; iterations the per-level passes; approxradius
    the polynomial-expansion radius."""
    n = child_after(params["input"], "volumeopticalflow", params.get("name"))
    if params.get("goal"):
        bridge_input(n, params["goal"], index=1, name_hint="goal")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("goalgroup", "goalgroup", "s", None),
        ("tolerance", "tolerance", "f", (1e-12, 1.0)),
        ("winradius", "winradius", "i", (0, 15)),
        ("gaussian", "gaussian", "b", None),
        ("levels", "levels", "i", (1, 5)),
        ("pyramidscale", "pyramidscale", "f", (0.1, 0.9)),
        ("iterations", "iterations", "i", (1, 5)),
        ("approxradius", "approxradius", "f", (0.25, 4.0)),
    ])
    return _finish_op(n)


@endpoint("volume_trail")
def volume_trail(params):
    """Volume Trail (volumetrail) — advect / trail points through a velocity volume over time. `input`
    (input 0) is the Points to Trail; `velocity` (input 1) the Velocity Volumes. velfield names the
    velocity grid; advectionchoice advectbydistance/advectbytime; traillen the trail length; usecfl + cfl
    the adaptive step; numsteps + usemaxsteps/maxsteps the step counts; keep retains the source points;
    visenable/detectrange/vismax/visramp control the visualization."""
    n = child_after(params["input"], "volumetrail", params.get("name"))
    if params.get("velocity"):
        bridge_input(n, params["velocity"], index=1, name_hint="velocity")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("velfield", "velfield", "s", None),
        ("advectionchoice", "advectionchoice", "m", ("advectbydistance", "advectbytime")),
        ("traillen", "traillen", "f", (0.0, 10.0)),
        ("usecfl", "usecfl", "b", None),
        ("cfl", "cfl", "f", (0.0, 10.0)),
        ("numsteps", "numsteps", "i", (1, 20)),
        ("usemaxsteps", "usemaxsteps", "b", None),
        ("maxsteps", "maxsteps", "i", (1, 10000)),
        ("keep", "keep", "b", None),
        ("visenable", "visenable", "b", None),
        ("detectrange", "detectrange", "b", None),
        ("vismax", "vismax", "f", (0.0, 10.0)),
        ("visramp", "visramp", "m", ("false", "pink", "mono", "blackbody", "bipartite", "custom")),
    ])
    return _finish_op(n)


@endpoint("volume_ambient_occlusion")
def volume_ambient_occlusion(params):
    """Volume Ambient Occlusion (volumeambientocclusion) — compute ambient occlusion into a volume.
    `input` (input 0) is the Volumes to Bake. occlusionname names the output grid; resolutionratio scales
    the working resolution; expand grows the active region; densityscale scales the input density;
    transmissioncutoff the ray termination threshold."""
    n = child_after(params["input"], "volumeambientocclusion", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("occlusionname", "occlusionname", "s", None),
        ("resolutionratio", "resolutionratio", "f", (0.001, 1.0)),
        ("expand", "expand", "i", (0, 5)),
        ("densityscale", "densityscale", "f", (1e-05, 1.0)),
        ("transmissioncutoff", "transmissioncutoff", "f", (1e-05, 0.01)),
    ])
    return _finish_op(n)


@endpoint("volume_bake")
def volume_bake(params):
    """Bake Volume (bakevolume) — bake lighting / scattering into a volume (render prep). `input`
    (input 0) is the Volume to Bake; `points` (input 1) the Points to Sample lights from. output_name
    names the baked colour grid; radiance the light strength; absorption/scattering/emission the material
    response; iso the surface level; computestepsize + stepsizescale the ray march step. (The vec3 colour
    parms are multi-component and left at their node defaults.)"""
    n = child_after(params["input"], "bakevolume", params.get("name"))
    if params.get("points"):
        bridge_input(n, params["points"], index=1, name_hint="points")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("output_name", "name", "s", None),  # node's own output-grid name parm (renamed off mcp `name`)
        ("radiance", "radiance", "f", (0.0, 10.0)),
        ("absorption", "absorption", "f", (0.0, 1.0)),
        ("scattering", "scattering", "f", (0.0, 1.0)),
        ("emission", "emission", "f", (0.0, 1.0)),
        ("iso", "iso", "f", (0.0, 1.0)),
        ("computestepsize", "computestepsize", "b", None),
        ("stepsizescale", "stepsizescale", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# NOISE / PAINT — vector-noise detailing, colour & SDF painting
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("volume_noise_vector")
def volume_noise_vector(params):
    """Volume Noise Vector (volumenoisevector) — add layered noise to a vector volume (velocity
    detailing). `input` (input 0) is the vector volume. vol names the grid; operation how the noise
    combines (set/add/sub/mult/min/max); amplitude the strength; rangemethod remaps the noise range;
    doblend/blendweight/blendmode/blendvol blend it back. SECURITY: the hidden vex_cwdpath file parm is
    NOT exposed."""
    n = child_after(params["input"], "volumenoisevector", params.get("name"))
    _apply(n, params, [
        ("doblend", "doblend", "b", None),
        ("blendweight", "blendweight", "f", (0.0, 1.0)),
        ("blendmode", "blendmode", "m", ("value", "vol")),
        ("blendvol", "blendvol", "s", None),
        ("vol", "vol", "s", None),
        ("operation", "operation", "m", ("set", "add", "sub", "mult", "min", "max")),
        ("rangemethod", "rangemethod", "m",
         ("positive", "negative", "zcentered", "minmax", "minplusrange", "midplusminusrange")),
        ("amplitude", "amplitude", "f", (0.0, 10.0)),
    ])
    return _finish_op(n)


@endpoint("paint_color_volume")
def paint_color_volume(params):
    """Volume Paint Color (paintcolorvolume) — procedurally deposit colour (Cd) into a volume. `input`
    (input 0) is the Collision surface; `volume` (input 1) an existing volume to add to; `brush`
    (input 2) brush geometry. voxelsize the resolution; densityscale/stroke_opacity/flowrate the amount;
    stroke_radius the footprint; fastcomposite the compositing; reprojection where strokes land;
    stroke_projtype the projection. NOTE: designed as a viewport brush — headless it deposits along its
    stroke settings. (The vec3 stroke-colour / projection-centre parms are left at their node defaults.)"""
    n = child_after(params["input"], "paintcolorvolume", params.get("name"))
    if params.get("volume"):
        bridge_input(n, params["volume"], index=1, name_hint="volume")
    if params.get("brush"):
        bridge_input(n, params["brush"], index=2, name_hint="brush")
    _apply(n, params, [
        ("voxelsize", "voxelsize", "f", (0.0, 10.0)),
        ("fastcomposite", "fastcomposite", "b", None),
        ("densityscale", "densityscale", "f", (0.0, 10.0)),
        ("stroke_radius", "stroke_radius", "f", (0.0, 1.0)),
        ("samplerate", "samplerate", "f", (0.0, 5.0)),
        ("stroke_opacity", "stroke_opacity", "f", (0.0, 10.0)),
        ("fade", "fade", "f", (0.0, 10.0)),
        ("useflow", "useflow", "b", None),
        ("flowrate", "flowrate", "f", (0.0, 10.0)),
        ("reprojection", "reprojection", "m", ("none", "ray", "primuv")),
        ("trimcurves", "trimcurves", "b", None),
        ("stroke_projtype", "stroke_projtype", "m", ("xy", "yz", "zx", "screen", "geometry")),
    ])
    return _finish_op(n)


@endpoint("paint_sdf_volume")
def paint_sdf_volume(params):
    """Volume Paint SDF (paintsdfvolume) — procedurally carve / add into an SDF volume. `input` (input 0)
    is the Collision Geometry; `sdf` (input 1) an existing SDF to modify. voxelsize the resolution;
    samplerate the sampling; stroke_radius the footprint; reprojection where strokes land; stroke_projtype
    the projection. NOTE: designed as a viewport brush — headless it deposits along its stroke settings.
    (The `stroke#_*` multiparm brush instances and vec3 projection-centre are not exposed.)"""
    n = child_after(params["input"], "paintsdfvolume", params.get("name"))
    if params.get("sdf"):
        bridge_input(n, params["sdf"], index=1, name_hint="sdf")
    _apply(n, params, [
        ("voxelsize", "voxelsize", "f", (0.0, 10.0)),
        ("samplerate", "samplerate", "f", (0.0, 5.0)),
        ("stroke_radius", "stroke_radius", "f", (0.0, 1.0)),
        ("reprojection", "reprojection", "m", ("none", "ray", "primuv")),
        ("trimcurves", "trimcurves", "b", None),
        ("stroke_projtype", "stroke_projtype", "m", ("xy", "yz", "zx", "screen", "geometry")),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VDB UTILITIES — clip / diagnostics / LOD / points / rasterize-frustum / visualize
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("vdb_convex_clip_sdf")
def vdb_convex_clip_sdf(params):
    """VDB Convex Clip SDF (vdbconvexclipsdf) — convex-clip an SDF VDB by a second convex SDF. `input`
    (input 0) is the VDBs to clip; `convex_hull` (input 1) the convex hull to clip with. group/ptgroup
    restrict each stream; operation intersect/difference/union; voxeloffset + worldoffset shift the clip
    surface."""
    n = child_after(params["input"], "vdbconvexclipsdf", params.get("name"))
    if params.get("convex_hull"):
        bridge_input(n, params["convex_hull"], index=1, name_hint="convex_hull")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("ptgroup", "ptgroup", "s", None),
        ("operation", "operation", "m", ("intersect", "difference", "union")),
        ("voxeloffset", "voxeloffset", "f", (-10.0, 10.0)),
        ("worldoffset", "worldoffset", "f", (-1.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("vdb_diagnostics")
def vdb_diagnostics(params):
    """VDB Diagnostics (vdbdiagnostics) — validate / diagnose a VDB grid (data-only QC). `input`
    (input 0) is the VDB Volumes. usemask/usepoints/respectclass shape the output; verify_fogvolume/
    verify_csg/verify_filtering/verify_advection run the operator-readiness checks; test_finite/
    id_finite/fix_finite and test_background/id_background/fix_background test, tag, and repair
    non-finite and wrong-background voxels."""
    n = child_after(params["input"], "vdbdiagnostics", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("usemask", "usemask", "b", None),
        ("usepoints", "usepoints", "b", None),
        ("respectclass", "respectclass", "b", None),
        ("verify_fogvolume", "verify_fogvolume", "b", None),
        ("verify_csg", "verify_csg", "b", None),
        ("verify_filtering", "verify_filtering", "b", None),
        ("verify_advection", "verify_advection", "b", None),
        ("test_finite", "test_finite", "b", None),
        ("id_finite", "id_finite", "b", None),
        ("fix_finite", "fix_finite", "b", None),
        ("test_background", "test_background", "b", None),
        ("id_background", "id_background", "b", None),
        ("fix_background", "fix_background", "b", None),
    ])
    return _finish_op(n)


@endpoint("vdb_lod")
def vdb_lod(params):
    """VDB LOD (vdblod) — build a level-of-detail (mip) pyramid for a VDB. `input` (input 0) is the VDBs.
    lod single/range/mipmaps picks the LOD mode; level the single-level factor; count the mipmap count;
    reuse reuses existing levels. (The range vec3 parm is left at its node default.)"""
    n = child_after(params["input"], "vdblod", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("lod", "lod", "m", ("single", "range", "mipmaps")),
        ("level", "level", "f", (0.0, 10.0)),
        ("count", "count", "i", (2, 10)),
        ("reuse", "reuse", "b", None),
    ])
    return _finish_op(n)


@endpoint("vdb_points_delete")
def vdb_points_delete(params):
    """VDB Points Delete (vdbpointsdelete) — delete points from a VDB Points grid. `input` (input 0) is
    the VDB Points. vdbpointsgroups selects which VDB-points groups to act on; invert flips the selection;
    dropgroups removes the emptied groups."""
    n = child_after(params["input"], "vdbpointsdelete", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("vdbpointsgroups", "vdbpointsgroups", "s", None),
        ("invert", "invert", "b", None),
        ("dropgroups", "dropgroups", "b", None),
    ])
    return _finish_op(n)


@endpoint("vdb_points_group")
def vdb_points_group(params):
    """VDB Points Group (vdbpointsgroup) — group points within a VDB Points grid. `input` (input 0) is
    the VDB Points; `bounding` (input 1) optional bounding geometry or level set. vdbpointsgroup selects
    the source group; enablecreate + groupname create a group; enablenumber + numbermode/pointpercent/
    pointcount limit by count; enablepercentattribute + percentattribute drive it by an attribute;
    enableboundingbox + boundingmode/boundingname group by a bounding region."""
    n = child_after(params["input"], "vdbpointsgroup", params.get("name"))
    if params.get("bounding"):
        bridge_input(n, params["bounding"], index=1, name_hint="bounding")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("vdbpointsgroup", "vdbpointsgroup", "s", None),
        ("enablecreate", "enablecreate", "b", None),
        ("groupname", "groupname", "s", None),
        ("enablenumber", "enablenumber", "b", None),
        ("numbermode", "numbermode", "m", ("percentage", "total")),
        ("pointpercent", "pointpercent", "f", (0.0, 100.0)),
        ("pointcount", "pointcount", "i", (0, 1000000)),
        ("enablepercentattribute", "enablepercentattribute", "b", None),
        ("percentattribute", "percentattribute", "s", None),
        ("enableboundingbox", "enableboundingbox", "b", None),
        ("boundingmode", "boundingmode", "m", ("boundingbox", "boundingobject")),
        ("boundingname", "boundingname", "s", None),
    ])
    return _finish_op(n)


@endpoint("vdb_rasterize_frustum")
def vdb_rasterize_frustum(params):
    """VDB Rasterize Frustum (vdbrasterizefrustum) — rasterize particles into a camera-frustum-aligned
    VDB. `input` (input 0) is the Particles to rasterize; `transform_vdb` (input 1) an optional VDB
    defining the output transform; `mask` (input 2) an optional VDB / bounding-box mask. vdbpointsgroups
    + mergevdbpoints select VDB points; transformvdb/maskvdb + invertmask pick the transform/mask grids;
    voxelsize the resolution; cliptofrustum/optimizeformemory shape the output; createdensity + densityscale
    /contributionthreshold build density; createmask + attributes rasterize extra attributes."""
    n = child_after(params["input"], "vdbrasterizefrustum", params.get("name"))
    if params.get("transform_vdb"):
        bridge_input(n, params["transform_vdb"], index=1, name_hint="transform_vdb")
    if params.get("mask"):
        bridge_input(n, params["mask"], index=2, name_hint="mask")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("vdbpointsgroups", "vdbpointsgroups", "s", None),
        ("mergevdbpoints", "mergevdbpoints", "b", None),
        ("transformvdb", "transformvdb", "s", None),
        ("maskvdb", "maskvdb", "s", None),
        ("invertmask", "invertmask", "b", None),
        ("voxelsize", "voxelsize", "f", (0.0, 5.0)),
        ("cliptofrustum", "cliptofrustum", "b", None),
        ("optimizeformemory", "optimizeformemory", "b", None),
        ("createdensity", "createdensity", "b", None),
        ("densityscale", "densityscale", "f", (0.0, 10.0)),
        ("contributionthreshold", "contributionthreshold", "f", (0.0, 0.1)),
        ("createmask", "createmask", "b", None),
        ("attributes", "attributes", "s", None),
    ])
    return _finish_op(n)


@endpoint("vdb_visualize_tree")
def vdb_visualize_tree(params):
    """VDB Visualize Tree (vdbvisualizetree) — build viz geometry of a VDB's internal tree structure.
    `input` (input 0) is the VDBs to visualize. addcolor colours the output; previewfrustum draws the
    frustum; drawleafnodes/leafmode, drawinternalnodes/internalmode, drawtiles/tilemode, drawvoxels/
    voxelmode pick which levels are drawn and as wirebox/box/points; ignorestaggered skips staggered
    grids; addindexcoord/addvalue add index-coordinate and value attributes."""
    n = child_after(params["input"], "vdbvisualizetree", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("addcolor", "addcolor", "b", None),
        ("previewfrustum", "previewfrustum", "b", None),
        ("drawleafnodes", "drawleafnodes", "b", None),
        ("leafmode", "leafmode", "m", ("wirebox", "box")),
        ("drawinternalnodes", "drawinternalnodes", "b", None),
        ("internalmode", "internalmode", "m", ("wirebox", "box")),
        ("drawtiles", "drawtiles", "b", None),
        ("tilemode", "tilemode", "m", ("points", "wirebox", "box")),
        ("drawvoxels", "drawvoxels", "b", None),
        ("voxelmode", "voxelmode", "m", ("points", "wirebox", "box")),
        ("ignorestaggered", "ignorestaggered", "b", None),
        ("addindexcoord", "addindexcoord", "b", None),
        ("addvalue", "addvalue", "b", None),
    ])
    return _finish_op(n)

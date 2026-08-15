"""SideFX Labs — World Building: Terrain / Placement / Set Dressing / Vegetation (data-only handlers).

Params verified against live H21.0.671: parm name/type, ordered-menu tokens, input/output counts, and a headless cook
per node with the right minimal upstream. Categories wrapped (highest version per base name):
  Labs/World Building/Terrain      -> hf_combine_masks, hf_insert_mask, terrain_segment, terrain_texture
  Labs/World Building/Placement    -> instance_attributes, mesh_tiler, physics_painter   (pick_and_place SKIPPED)
  Labs/World Building/Set Dressing -> dirtskirt, snow_buildup
  Labs/World Building/Vegetation   -> tree_branch_placer, tree_hierarchy

SECURITY (data-only boundary):
  * terrain_segment carries an FBX tile-export path (`outputpath`); it is confined_path()'d and the
    FBX save is NEVER fired (WIRE-ONLY export — the SOP itself only segments geometry on cook).
  * terrain_texture is a WIRE-ONLY map baker (like tree.py maps_baker): `outputdir` is confined, the
    per-map name/output surfaces stay at HDA default, the bake is never executed -> returns rendered=False.
  * tree_branch_placer has a displacement image surface: `enable_disp` is forced OFF and `disp_texture`
    is never exposed; its `objpath1` is a NodeReference (node path, not a file) left unset.
  * physics_painter's object slots (`objPrevSim`, `objObjPath#`) are NodeReferences (node paths, not
    files) left unset; the sim substeps/count are clamped. No node here exposes a code/callback parm.
All other exposed parms are scalars / toggles / ordered-menus / geometry-group-or-layer NAME strings.
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────


def _try_set_tuple(node, parm, values):
    """Set a tuple parm (vec3 etc.) only if it exists on this node."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(values))
        return True
    except Exception:
        return False


def _menu_idx_set(node, parm, token, tokens):
    """Ordered menu presented with FRIENDLY labels: set index = tokens.index(token), where `tokens`
    is our label tuple aligned to the native menu order (native token may be '0','1',...)."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(tokens.index(token))
        return True
    except Exception:
        return False


def _menu_tok_set(node, parm, token, tokens):
    """Ordered menu whose native tokens are meaningful strings: set by the token string directly
    (proven on this build for every such menu in this lane)."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _wire_parent_curve(n):
    """The Labs tree nodes carry a spine CURVE on OUTPUT 1. child_after wires the parent MESH
    (output 0) -> input 0; the placer/hierarchy nodes ALSO need that parent's curve on input 1, so
    wire the parent's OUTPUT 1 -> this node's input 1. No-op if the parent lacks a second output."""
    p0 = n.input(0)
    if p0 is not None and len(p0.outputConnectors()) > 1:
        try:
            n.setInput(1, p0, 1)
        except hou.OperationFailed:
            pass


def _safe_layer_token(v):
    """Sanitize a heightfield LAYER name / map-name token: reject path separators, parent refs and
    drive letters so a layer name can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("layer/name token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


# ── ordered-menu label tuples (position == the native stored index) ──────────────────────────────
# friendly-label menus (native token is '0','1',... or a different label) -> set by INDEX
_RES = ("256", "512", "1024", "2048", "4096", "8192")                      # terrain_texture resdropdown
_RASTER = ("8i", "16i", "16f", "32f")                                      # terrain_texture iRasterDepth
_TILEMODE = ("full", "piece")                                             # mesh_tiler tilemode
_SIDE = ("negative", "positive")                                          # mesh_tiler xside/zside
_SCALETARGET = ("pscale", "scale", "both")                                # instance_attributes scaletarget
_REORIENT = ("none", "swap_up_forward", "rotate_up_to_forward")           # instance_attributes reorient
_SPINAXIS = ("x", "y", "z")                                               # instance_attributes spinaxis
_SPINMODE = ("uniform", "random", "from_attribute")                       # instance_attributes spinamountmode
_UNIT = ("relative", "world")                                             # snow_buildup unit
_SNOWNOISE = ("simple", "stratification_melted", "shoveled",
              "stratification_holes", "melted_holes")                      # snow_buildup typenoise
_SEAM3 = ("none", "boolean_normal", "normal")                             # tree_branch_placer seam_options
# meaningful-token menus -> set by the native TOKEN string
_VALUETYPE = ("float", "string")                                          # instance_attributes valuetype
_COMBINE_METHOD = ("blur", "boxblur", "expand", "shrink")                 # hf_combine_masks method_1
_COMBINE_MODE = ("replace", "add", "subtract", "diff", "multiply",
                 "max", "min", "blend")                                    # hf_combine_masks mode_1
_PROJTYPE = ("xy", "yz", "zx", "screen", "geometry")                      # physics_painter stroke_projtype
_REPROJ = ("none", "ray", "primuv")                                       # physics_painter reprojection
_SAMPLEMODE = ("def", "point", "circle", "sphere")                        # physics_painter lSamplemode
_ENDCAP4 = ("none", "single", "grid", "sidesingle")                       # tree_branch_placer endcaptype


# ══ Terrain ══════════════════════════════════════════════════════════════════════════════════════

# ── 1. hf_combine_masks (chain; in0 heightfield) — combine/post-process mask layers ──────────────
@endpoint("hf_combine_masks")
def hf_combine_masks(params):
    """Labs Combine Masks (labs::hf_combine_masks) — merges and post-processes heightfield MASK
    layers on the incoming heightfield (`input`, input 0). `srcname1` is the base mask layer; one
    optional combine layer is exposed (`layername`+`method`+`mode`+`blend`+`radius`) which composites
    another named mask over it (the per-layer multiparm list beyond the first stays at HDA default).
    clampmin/clampmax keep the result in 0..1. Data-only (no file/code surface — layer names are
    sanitized to plain tokens)."""
    n = child_after(params["input"], "labs::hf_combine_masks", params.get("name"))
    if "flood" in params:
        _try_set(n, "bFlood", bool(params["flood"]))
    if "srcname1" in params:
        _try_set(n, "srcname1", _safe_layer_token(params["srcname1"]))
    if "clampmin" in params:
        _try_set(n, "clampmin", bool(params["clampmin"]))
    if "clampmax" in params:
        _try_set(n, "clampmax", bool(params["clampmax"]))
    # optional first combine layer (multiparm instance 1)
    layer_keys = ("layername", "method", "mode", "blend", "radius", "layer_clamp")
    if any(k in params for k in layer_keys):
        _try_set(n, "folder0", 1)  # ensure at least one combine instance exists
        if "layername" in params:
            _try_set(n, "layername_1", _safe_layer_token(params["layername"]))
        if "method" in params:
            _menu_tok_set(n, "method_1", str(params["method"]), _COMBINE_METHOD)
        if "mode" in params:
            _menu_tok_set(n, "mode_1", str(params["mode"]), _COMBINE_MODE)
        if "blend" in params:
            _try_set(n, "blend_1", clamp(float(params["blend"]), 0.0, 1.0))
        if "radius" in params:
            _try_set(n, "radius_1", clamp(float(params["radius"]), 0.0, 1000.0))
        if "layer_clamp" in params:
            _try_set(n, "clamp_1", bool(params["layer_clamp"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. hf_insert_mask (chain; in0 heightfield, in1 mask source) — copy a named layer in ──────────
@endpoint("hf_insert_mask")
def hf_insert_mask(params):
    """Labs Insert Mask (labs::hf_insert_mask) — copies a named MASK/height layer from a second
    heightfield (`mask`, input 1) into the base heightfield (`input`, input 0). `srcname` = the layer
    to read from the mask source; `dstname` (with `newname` on) renames it on the way in. Data-only
    (no file/code surface — layer names are sanitized)."""
    n = child_after(params["input"], "labs::hf_insert_mask", params.get("name"))
    if params.get("mask"):
        bridge_input(n, params["mask"], index=1, name_hint="mask")
    # every driving parm is the first multiparm instance -> ensure one instance exists
    _try_set(n, "folder0", 1)
    if "srcname" in params:
        _try_set(n, "srcname_1", _safe_layer_token(params["srcname"]))
    if "newname" in params:
        _try_set(n, "bNewName_1", bool(params["newname"]))
    if "dstname" in params:
        _try_set(n, "dstname_1", _safe_layer_token(params["dstname"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. terrain_segment (chain; in0 heightfield) — tile the terrain (FBX export WIRE-ONLY) ─────────
@endpoint("terrain_segment")
def terrain_segment(params):
    """Labs Terrain Segment (labs::terrain_segment::1.0) — splits the incoming heightfield (`input`,
    input 0) into a `tiles_x` x `tiles_y` grid of meshed terrain tiles (its cooked SOP output IS the
    segmented geometry). `doextrude`+`depth` give the tiles solid skirts; `flat` bakes to a flat mesh;
    `iterations` drives the adaptive-density remesh. SECURITY: the per-tile FBX export path
    (`outputpath`) is confined to the working dir when supplied and the FBX SAVE IS NEVER FIRED
    (WIRE-ONLY export — set the path, then save from the UI). Data-only otherwise."""
    n = child_after(params["input"], "labs::terrain_segment::1.0", params.get("name"))
    if "tiles_x" in params or "tiles_y" in params:
        cur = n.parmTuple("tilecount").eval() if n.parmTuple("tilecount") else (4, 4)
        tx = int(clamp(int(params.get("tiles_x", cur[0])), 1, 64))
        ty = int(clamp(int(params.get("tiles_y", cur[1])), 1, 64))
        _try_set_tuple(n, "tilecount", (tx, ty))
    if "rows" in params:
        _try_set(n, "rows", clamp(float(params["rows"]), 0.01, 1000.0))
    if "flat" in params:
        _try_set(n, "flat", bool(params["flat"]))
    if "doextrude" in params:
        _try_set(n, "doextrude", bool(params["doextrude"]))
    if "depth" in params:
        _try_set(n, "depth", clamp(float(params["depth"]), -1000.0, 1000.0))
    if "adaptive_density" in params:
        _try_set(n, "bAdaptiveDensity", bool(params["adaptive_density"]))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 500)))
    if "layer" in params:
        _try_set(n, "layer", _safe_layer_token(params["layer"]))
    if "singlefile" in params:
        _try_set(n, "singlefile", bool(params["singlefile"]))
    # SECURITY: confine the FBX export target if supplied; never fire the save.
    out_path = None
    if params.get("outputpath"):
        out_path = confined_path(params["outputpath"])
        _try_set(n, "outputpath", out_path)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "output": out_path, "exported": False}


# ── 4. terrain_texture (chain; in0 terrain) — WIRE-ONLY map baker ─────────────────────────────────
@endpoint("terrain_texture")
def terrain_texture(params):
    """Labs Terrain Texture (labs::terrain_texture::1.0) — WIRE-ONLY terrain map baker: bakes
    normal / height / occlusion / cavity / curvature maps of the incoming terrain (`input`, input 0)
    to `outputdir`. Mirrors tree.py maps_baker: the graph is BUILT + configured but the bake is NEVER
    executed (baking is a render — the human fires it), so it returns rendered=False.
    SECURITY: `outputdir` is realpath-confined to the working dir; the per-map name surfaces stay at
    HDA default; nothing is written here. `resolution` (output res) is capped at 8192."""
    n = child_after(params["input"], "labs::terrain_texture::1.0", params.get("name"))
    if "resolution" in params:
        _menu_idx_set(n, "resdropdown", str(params["resolution"]), _RES)
    if "rasterdepth" in params:
        _menu_idx_set(n, "iRasterDepth", str(params["rasterdepth"]), _RASTER)
    if "divide_tiles" in params:
        _try_set(n, "bDivideTiles", bool(params["divide_tiles"]))
    if "tiles_x" in params or "tiles_y" in params:
        cur = n.parmTuple("iNumTiles").eval() if n.parmTuple("iNumTiles") else (4, 4)
        tx = int(clamp(int(params.get("tiles_x", cur[0])), 1, 64))
        ty = int(clamp(int(params.get("tiles_y", cur[1])), 1, 64))
        _try_set_tuple(n, "iNumTiles", (tx, ty))
    for key, parm in (("export_normal", "bExportNormal"), ("export_height", "bExportHeight"),
                      ("export_occlusion", "bExportOcclusion"), ("export_cavity", "bExportCavity"),
                      ("export_curvature", "exportcurvature")):
        if key in params:
            _try_set(n, parm, bool(params[key]))
    if "normalize" in params:
        _try_set(n, "bNormalize", bool(params["normalize"]))
    if "range_min" in params or "range_max" in params:
        cur = n.parmTuple("range").eval() if n.parmTuple("range") else (-100.0, 100.0)
        rmin = clamp(float(params.get("range_min", cur[0])), -1e6, 1e6)
        rmax = clamp(float(params.get("range_max", cur[1])), -1e6, 1e6)
        _try_set_tuple(n, "range", (rmin, rmax))
    # SECURITY: confine the bake output dir if supplied; never fire the bake.
    out_dir = None
    if params.get("outputdir"):
        out_dir = confined_path(params["outputdir"])
        _try_set(n, "outputdir", out_dir)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "output": out_dir, "rendered": False,
            "note": "terrain_texture graph wired (WIRE-ONLY); start the bake yourself"}


# ══ Placement ════════════════════════════════════════════════════════════════════════════════════

# ── 5. instance_attributes (chain; in0 points) — set up instancing attribs ────────────────────────
@endpoint("instance_attributes")
def instance_attributes(params):
    """Labs Instance Attributes (labs::instance_attributes::1.0) — writes the point attributes an
    instancer reads (the `instanceattrib` asset-path attribute + per-point pscale/scale/orient) onto
    the incoming points (`input`, input 0) so a downstream copy/instance can dress a scene. Randomize
    pscale (`randpscale`+`pscalemin/max`), non-uniform scale, and spin about an axis. Data-only: the
    asset-path variant list is left at HDA default (those are attribute VALUES, not files read here)."""
    n = child_after(params["input"], "labs::instance_attributes::1.0", params.get("name"))
    if "instanceattrib" in params:
        _try_set(n, "instanceattrib", _safe_layer_token(params["instanceattrib"]))
    if "valuetype" in params:
        _menu_tok_set(n, "valuetype", str(params["valuetype"]), _VALUETYPE)
    if "delinstanceattrib" in params:
        _try_set(n, "delinstanceattrib", bool(params["delinstanceattrib"]))
    if "uniformscale" in params:
        _try_set(n, "uniformscale", clamp(float(params["uniformscale"]), 0.0, 1e6))
    if "scaletarget" in params:
        _menu_idx_set(n, "scaletarget", str(params["scaletarget"]), _SCALETARGET)
    if "randpscale" in params:
        _try_set(n, "randpscale", bool(params["randpscale"]))
    if "pscalemin" in params:
        _try_set(n, "pscalemin", clamp(float(params["pscalemin"]), 0.0, 1e6))
    if "pscalemax" in params:
        _try_set(n, "pscalemax", clamp(float(params["pscalemax"]), 0.0, 1e6))
    if "randscale" in params:
        _try_set(n, "randscale", bool(params["randscale"]))
    if "reorient" in params:
        _menu_idx_set(n, "reorient", str(params["reorient"]), _REORIENT)
    if "spinamountmode" in params:
        _menu_idx_set(n, "spinamountmode", str(params["spinamountmode"]), _SPINMODE)
    if "spinaxis" in params:
        _menu_idx_set(n, "spinaxis", str(params["spinaxis"]), _SPINAXIS)
    if "spin_uniform" in params:
        _try_set(n, "spin_uniform", clamp(float(params["spin_uniform"]), -3600.0, 3600.0))
    if "spin_min" in params:
        _try_set(n, "spin_min", clamp(float(params["spin_min"]), -3600.0, 3600.0))
    if "spin_max" in params:
        _try_set(n, "spin_max", clamp(float(params["spin_max"]), -3600.0, 3600.0))
    if "rand3drot" in params:
        _try_set(n, "rand3drot", bool(params["rand3drot"]))
    if "rotmin" in params:
        _try_set(n, "rotmin", clamp(float(params["rotmin"]), -3600.0, 3600.0))
    if "rotmax" in params:
        _try_set(n, "rotmax", clamp(float(params["rotmax"]), -3600.0, 3600.0))
    if "seed" in params:
        _try_set(n, "assetrandseed", clamp(float(params["seed"]), -1e9, 1e9))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. mesh_tiler (chain; in0 PACKED pieces) — make geometry tile seamlessly ──────────────────────
@endpoint("mesh_tiler")
def mesh_tiler(params):
    """Labs Mesh Tiler (labs::mesh_tiler::1.0) — wraps PACKED geometry that crosses a unit-tile
    boundary so it tiles seamlessly (pieces exiting one edge re-enter the opposite edge). `input`
    (input 0) MUST be PACKED (unpacked geometry is discarded with a warning). `tilemode` full/piece;
    `xside`/`zside` pick which edge to wrap toward; `edgedensity`/`gridsamples` control the seam
    resolution. Data-only (no file/code surface — attribute names are plain tokens)."""
    n = child_after(params["input"], "labs::mesh_tiler::1.0", params.get("name"))
    if "tilemode" in params:
        _menu_idx_set(n, "tilemode", str(params["tilemode"]), _TILEMODE)
    if "xside" in params:
        _menu_idx_set(n, "xside", str(params["xside"]), _SIDE)
    if "zside" in params:
        _menu_idx_set(n, "zside", str(params["zside"]), _SIDE)
    if "edgedensity" in params:
        _try_set(n, "edgedensity", clamp(float(params["edgedensity"]), 1.0, 1000.0))
    if "gridsamples" in params:
        _try_set(n, "gridsamples", int(clamp(int(params["gridsamples"]), 10, 5000)))
    if "color" in params:
        _try_set(n, "color", bool(params["color"]))
    if "exportplane" in params:
        _try_set(n, "exportplane", bool(params["exportplane"]))
    if "attribname" in params:
        _try_set(n, "attribname", _safe_layer_token(params["attribname"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. physics_painter (chain; in0 surface) — settle scattered objects with Bullet ────────────────
@endpoint("physics_painter")
def physics_painter(params):
    """Labs Physics Painter (labs::physics_painter) — scatters objects across the incoming surface
    (`input`, input 0) and settles them with a short Bullet solve so they rest naturally (rocks on a
    slope, props on a shelf). The object slots are populated interactively in the UI; this tool drives
    the GLOBAL physics: `npts` per stroke, gravity `gravity` [x,y,z], `substeps`, scale range, ground
    plane, restitution/friction. SECURITY: object references (objPrevSim / objObjPath#) are node
    paths (not files) left unset; substeps/npts are clamped (bounded solve cost). Data-only."""
    n = child_after(params["input"], "labs::physics_painter", params.get("name"))
    if "npts" in params:
        _try_set(n, "npts", int(clamp(int(params["npts"]), 1, 2000)))
    if "activate_all" in params:
        _try_set(n, "Activate_All", bool(params["activate_all"]))
    if "stroke_projtype" in params:
        _menu_tok_set(n, "stroke_projtype", str(params["stroke_projtype"]), _PROJTYPE)
    if "reprojection" in params:
        _menu_tok_set(n, "reprojection", str(params["reprojection"]), _REPROJ)
    if "samplemode" in params:
        _menu_tok_set(n, "lSamplemode", str(params["samplemode"]), _SAMPLEMODE)
    if "stroke_padding" in params:
        _try_set(n, "fStrokePadding", clamp(float(params["stroke_padding"]), 0.0, 100.0))
    if "offset_dist" in params:
        _try_set(n, "fOffsetDist", clamp(float(params["offset_dist"]), -100.0, 100.0))
    if "scale_min" in params:
        _try_set(n, "vMinScale", clamp(float(params["scale_min"]), 1e-3, 1000.0))
    if "scale_max" in params:
        _try_set(n, "vMaxScale", clamp(float(params["scale_max"]), 1e-3, 1000.0))
    gvec = [params.get("gravity_x"), params.get("gravity_y"), params.get("gravity_z")]
    if any(v is not None for v in gvec):
        cur = n.parmTuple("vForce").eval() if n.parmTuple("vForce") else (0.0, -9.80665, 0.0)
        vec = [clamp(float(gvec[i]), -1e5, 1e5) if gvec[i] is not None else cur[i] for i in range(3)]
        _try_set_tuple(n, "vForce", vec)
    if "substeps" in params:
        _try_set(n, "iSubsteps", int(clamp(int(params["substeps"]), 1, 100)))
    if "ground_plane" in params:
        _try_set(n, "bGroundPlane", bool(params["ground_plane"]))
    if "floor_height" in params:
        _try_set(n, "fFloorHeight", clamp(float(params["floor_height"]), -1e6, 1e6))
    if "density" in params:
        _try_set(n, "fDensity_Static", clamp(float(params["density"]), 1e-3, 1e9))
    if "bounce" in params:
        _try_set(n, "fBounce_Static", clamp(float(params["bounce"]), 0.0, 10.0))
    if "friction" in params:
        _try_set(n, "fFriction_Static", clamp(float(params["friction"]), 0.0, 10.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ══ Set Dressing ═════════════════════════════════════════════════════════════════════════════════

# ── 8. dirtskirt (chain; in0 object, in1 ground) — debris skirt where object meets ground ─────────
@endpoint("dirtskirt")
def dirtskirt(params):
    """Labs Dirt Skirt (labs::dirtskirt::1.0) — builds a scattered dirt/debris skirt where an object
    (`input`, input 0) meets a ground surface (`ground`, input 1) — the little pile of rubble at a
    rock/wall base. `obj*` controls the noise band riding up the object; `gnd*` the band spreading on
    the ground; `finalcount` caps the scattered debris count; `iterations` grows the band; `threshold`
    trims it. Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::dirtskirt::1.0", params.get("name"))
    if params.get("ground"):
        bridge_input(n, params["ground"], index=1, name_hint="ground")
    if "objdistance" in params:
        _try_set(n, "objdistance", clamp(float(params["objdistance"]), 0.0, 100.0))
    if "objfrequency" in params:
        _try_set(n, "objfrequency", clamp(float(params["objfrequency"]), 0.0, 100.0))
    if "objintensity" in params:
        _try_set(n, "objintensity", clamp(float(params["objintensity"]), 0.0, 100.0))
    if "gnddistance" in params:
        _try_set(n, "gnddistance", clamp(float(params["gnddistance"]), 0.0, 100.0))
    if "gndfrequency" in params:
        _try_set(n, "gndfrequency", clamp(float(params["gndfrequency"]), 0.0, 100.0))
    if "gndintensity" in params:
        _try_set(n, "gndintensity", clamp(float(params["gndintensity"]), 0.0, 100.0))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 100)))
    if "groundoffset" in params:
        _try_set(n, "groundoffset", clamp(float(params["groundoffset"]), -100.0, 100.0))
    if "rotatex" in params:
        _try_set(n, "rotatex", clamp(float(params["rotatex"]), -360.0, 360.0))
    if "rotatez" in params:
        _try_set(n, "rotatez", clamp(float(params["rotatez"]), -360.0, 360.0))
    if "add_vertex_color" in params:
        _try_set(n, "addvtxcolor", bool(params["add_vertex_color"]))
    if "finalcount" in params:
        _try_set(n, "finalcount", int(clamp(int(params["finalcount"]), 0, 200000)))
    if "threshold" in params:
        _try_set(n, "threshold", clamp(float(params["threshold"]), 0.0, 1.0))
    if "zoffset" in params:
        _try_set(n, "zoffset", clamp(float(params["zoffset"]), -100.0, 100.0))
    if "keep_ground_mesh" in params:
        _try_set(n, "keepgroundmesh", bool(params["keep_ground_mesh"]))
    if "keep_object_mesh" in params:
        _try_set(n, "keepobjectmesh", bool(params["keep_object_mesh"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 9. snow_buildup (chain; in0 surface) — accumulate snow on upward faces ─────────────────────────
@endpoint("snow_buildup")
def snow_buildup(params):
    """Labs Snow Buildup (labs::snow_buildup::2.0) — accumulates a snow shell on the upward-facing
    parts of the incoming surface (`input`, input 0). `angle` is the max face slope that holds snow;
    `baseheight`/`snowheight` set the depth; `typenoise` picks the surface look (drifts / melted /
    shoveled); `smoothiterations` softens it. `snow_only` outputs just the snow group. Data-only
    (no file/code surface)."""
    n = child_after(params["input"], "labs::snow_buildup::2.0", params.get("name"))
    if "seed" in params:
        _try_set(n, "seed", int(clamp(int(params["seed"]), 0, 1_000_000_000)))
    if "occlude_mesh" in params:
        _try_set(n, "occludemesh", bool(params["occlude_mesh"]))
    if "angle" in params:
        _try_set(n, "angle", clamp(float(params["angle"]), 0.0, 180.0))
    if "resolution" in params:
        _try_set(n, "resolution", clamp(float(params["resolution"]), 1e-4, 10.0))
    if "unit" in params:
        _menu_idx_set(n, "unit", str(params["unit"]), _UNIT)
    if "baseheight" in params:
        _try_set(n, "baseheight", clamp(float(params["baseheight"]), 0.0, 1000.0))
    if "snowheight" in params:
        _try_set(n, "snowheight", clamp(float(params["snowheight"]), 0.0, 1000.0))
    if "snowfrequency" in params:
        _try_set(n, "snowfrequency", clamp(float(params["snowfrequency"]), 0.0, 1000.0))
    if "minarea" in params:
        _try_set(n, "minarea", clamp(float(params["minarea"]), 0.0, 1000.0))
    if "smoothiterations" in params:
        _try_set(n, "smoothiterations", int(clamp(int(params["smoothiterations"]), 0, 100)))
    if "typenoise" in params:
        _menu_idx_set(n, "typenoise", str(params["typenoise"]), _SNOWNOISE)
    if "intensitynoise" in params:
        _try_set(n, "intensitynoise", clamp(float(params["intensitynoise"]), 0.0, 100.0))
    if "scalenoise" in params:
        _try_set(n, "scalenoise", clamp(float(params["scalenoise"]), 0.0, 100.0))
    if "blur_iterations" in params:
        _try_set(n, "addbluriteration", int(clamp(int(params["blur_iterations"]), 0, 100)))
    if "melt_border" in params:
        _try_set(n, "meltborder", bool(params["melt_border"]))
    if "melt_iterations" in params:
        _try_set(n, "meltiterations", int(clamp(int(params["melt_iterations"]), 0, 100)))
    if "snow_only" in params:
        _try_set(n, "snow", bool(params["snow_only"]))
    if "snow_group" in params:
        _try_set(n, "snowgroupname", _safe_layer_token(params["snow_group"]))
    if "keep_original" in params:
        _try_set(n, "keeporiginal", bool(params["keep_original"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ══ Vegetation ═══════════════════════════════════════════════════════════════════════════════════

# ── 10. tree_branch_placer (chain; in0 mesh, in1 parent curve) — place + shape branches ───────────
@endpoint("tree_branch_placer")
def tree_branch_placer(params):
    """Labs Tree Branch Placer (labs::tree_branch_placer::1.1) — grows/places branches off a parent
    trunk. `input` (input 0) = the parent MESH; the parent's spine CURVE (output 1) is auto-wired to
    input 1 (pass an explicit `curve` to override). Individual branch positions are placed
    interactively in the viewport; this tool drives the GLOBAL branch shape (radius, angle, endcap,
    noise, tropism, seam) and wires the trunk — with no manual placements it passes the trunk mesh
    through. SECURITY: displacement is forced OFF (`enable_disp`), the displacement image
    (`disp_texture`) is never exposed, and `objpath1` (a NodeReference) is left unset."""
    n = child_after(params["input"], "labs::tree_branch_placer::1.1", params.get("name"))
    if params.get("curve"):
        bridge_input(n, params["curve"], index=1, name_hint="curve")
    else:
        _wire_parent_curve(n)  # carry the parent's spine CURVE (output 1) into input 1
    _try_set(n, "enable_disp", False)  # SECURITY: never displace from a disk image
    if "del_prev" in params:
        _try_set(n, "del_prev", bool(params["del_prev"]))
    if "angle" in params:
        _try_set(n, "angle", clamp(float(params["angle"]), 0.0, 360.0))
    if "roll" in params:
        _try_set(n, "roll2", clamp(float(params["roll"]), -720.0, 720.0))
    if "radius" in params:
        _try_set(n, "radius_override", True)
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-3, 100.0))
    if "radius_override" in params:
        _try_set(n, "radius_override", bool(params["radius_override"]))
    if "radius_adjust" in params:
        _try_set(n, "radius_adjust", clamp(float(params["radius_adjust"]), -10.0, 10.0))
    if "lat_branch_start" in params:
        _try_set(n, "lat_branch_start", clamp(float(params["lat_branch_start"]), 0.0, 1.0))
    if "lat_jitter" in params:
        _try_set(n, "lat_jitter", clamp(float(params["lat_jitter"]), 0.0, 10.0))
    if "endcaptype" in params:
        _menu_tok_set(n, "endcaptype", str(params["endcaptype"]), _ENDCAP4)
    if "capdivs" in params:
        _try_set(n, "capdivs", int(clamp(int(params["capdivs"]), 0, 32)))
    if "seam_options" in params:
        _menu_idx_set(n, "seam_options", str(params["seam_options"]), _SEAM3)
    if "detangle" in params:
        _try_set(n, "detangle_toggle", bool(params["detangle"]))
    if "intersect" in params:
        _try_set(n, "intersect_toggle", bool(params["intersect"]))
    if "enable_bend" in params:
        _try_set(n, "enable_bend", bool(params["enable_bend"]))
    if "bend_strength" in params:
        _try_set(n, "bend_strength", clamp(float(params["bend_strength"]), -10.0, 10.0))
    if "enable_grav" in params:
        _try_set(n, "enable_grav", bool(params["enable_grav"]))
    if "grav_strength" in params:
        _try_set(n, "grav_strength", clamp(float(params["grav_strength"]), -5.0, 5.0))
    if "enable_light" in params:
        _try_set(n, "enable_light", bool(params["enable_light"]))
    if "light_strength" in params:
        _try_set(n, "light_strength", clamp(float(params["light_strength"]), -5.0, 5.0))
    if "enable_mesh_noise" in params:
        _try_set(n, "enable_mesh_noise", bool(params["enable_mesh_noise"]))
    if "mesh_noise_amount" in params:
        _try_set(n, "mesh_noise_amount", clamp(float(params["mesh_noise_amount"]), 0.0, 5.0))
    if "res" in params:
        _try_set(n, "res_override", True)
        _try_set(n, "res", clamp(float(params["res"]), 1e-3, 5.0))
    if "seed" in params:
        _try_set(n, "seed", clamp(float(params["seed"]), -1e9, 1e9))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 11. tree_hierarchy (chain; in0 mesh, in1 parent curve) — name/organize the branch hierarchy ───
@endpoint("tree_hierarchy")
def tree_hierarchy(params):
    """Labs Tree Hierarchy (labs::tree_hierarchy::1.0) — tags the branches of a tree with a named
    generation/branch hierarchy (e.g. `gen_0/_branch_1`) for downstream selection, wind, or export.
    `input` (input 0) = the tree MESH; the tree's spine CURVE (output 1) is auto-wired to input 1
    (pass an explicit `curve` to override). `branchlvlprefix`/`branchprefix` name the tiers.
    Data-only (the prefixes are plain name tokens, not paths)."""
    n = child_after(params["input"], "labs::tree_hierarchy::1.0", params.get("name"))
    if params.get("curve"):
        bridge_input(n, params["curve"], index=1, name_hint="curve")
    else:
        _wire_parent_curve(n)
    if "branchlvlprefix" in params:
        _try_set(n, "branchlvlprefix", _safe_layer_token(params["branchlvlprefix"]))
    if "branchprefix" in params:
        _try_set(n, "branchprefix", _safe_layer_token(params["branchprefix"]))
    if "visualize" in params:
        _try_set(n, "visualize", bool(params["visualize"]))
    if "assign_material" in params:
        _try_set(n, "assignmat", bool(params["assign_material"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

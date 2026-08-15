"""SideFX Labs — World Building STRUCTURES handlers (data-only). Params verified against live
H21.0.671. Covers the Architecture / Road / Prop procedural
structure generators:

  building_from_patterns   labs::building_from_patterns::1.1   (Architecture)
  building_generator       labs::building_generator::4.0       (Architecture)
  building_module          labs::building_generator_utility::2.0 (Architecture — module tagger)
  pathfinding_global       labs::pathfinding_global::1.0       (Road)
  road_generator           labs::road_generator::1.2           (Road)
  settlement_connections   labs::settlement_connections::1.0   (Road)
  cable_generator          labs::cable_generator::2.0          (Prop)
  lot_subdivision          labs::lot_subdivision::2.0          (Prop)
  scifi_panels             labs::scifi_panels::1.0             (Prop)
  simple_rope_wrap         labs::simple_rope_wrap::1.0         (Prop)

Every node is a CHAIN node (>=1 input): the primary geometry is wired via `child_after` (input 0);
extra inputs are wired via `bridge_input` (cross-network safe). Each handler exposes a curated,
safe scalar/toggle/enum subset — FolderSet/Folder/Label/Ramp/Button parms are skipped.

SECURITY (data-only): NONE of these nodes carry a python/vex/snippet/opencl/callback parm (probed
clean) and NONE carry a file/path surface, so there is no write/exec surface to confine. The only
node-reference string, road_generator's `objpath1` (Custom Module op-path), is deliberately NOT
exposed and left unset. Cost-exponential levers (pathfinding point count / relaxation, cable
density, lot/scifi iterations) are hard-clamped with sane maxima and noted in each ToolDef.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set






def _str_menu_set(node, parm, token, tokens):
    """Set a STRING (Normal) menu parm by its token string directly."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _result(n):
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── ordered-menu token tuples (position == the node's stored index) ──────────────────────────────
_BFP_ENGINE = ("unreal_instance", "unity_instance")     # engine (String menu — set by token)
_BFP_PIVOT = ("corner", "bottom_middle")                # set_middle (idx 0=Corner / 1=Bottom Middle)
_PF_SOURCE = ("existing_grid", "scattered")             # source (idx 0/1)
_PF_GENERATE = ("total_count", "by_density")            # generatepoints (idx 0/1)
_SC_ANGLEMODE = ("uniform", "varied")                   # anglemode (idx 0/1)
_CABLE_INPUT = ("curve", "connect_surfaces", "through_geometry")   # inputtype (int val 0/1/2)
_CABLE_POLYAS = ("straight", "subd", "interp")          # treatpolysas / geocurvetype (idx 0/1/2)
_CABLE_SIM = ("none", "pseudo_gravity", "wire_sim")     # simtype (idx 0/1/2)
_LOT_ALIGN = ("longest_edge", "bbox_xz")                # alignment (idx 0/1)
_PANEL_UV = ("use_input_uvs", "auto_generate")          # generate_uvs (int val 0/1)
_ROPE_SHAPE = ("circle", "rope", "custom")              # shape (int val 0/1/2)


# ── Architecture ─────────────────────────────────────────────────────────────────────────────────
@endpoint("building_from_patterns")
def building_from_patterns(params):
    """Labs Building From Patterns (labs::building_from_patterns::1.1) — arranges building MODULES over
    a blockout according to a floor/module pattern grammar. `input` (input 0) = the blockout massing;
    optional `patterns` (input 1) = the module/pattern library, `cutout` (input 2), `override_floor`
    (input 3). `pattern` is a grammar STRING (e.g. `<Generic>`, `[F-G]<F>`) — pure data, not code.
    SECURITY: data-only; no file/code surface."""
    n = child_after(params["input"], "labs::building_from_patterns::1.1", params.get("name"))
    if params.get("patterns"):
        bridge_input(n, params["patterns"], index=1, name_hint="patterns")
    if params.get("cutout"):
        bridge_input(n, params["cutout"], index=2, name_hint="cutout")
    if params.get("override_floor"):
        bridge_input(n, params["override_floor"], index=3, name_hint="override_floor")
    if "pack_modules" in params:
        _try_set(n, "pack_modules", bool(params["pack_modules"]))
    if "floorseed" in params:
        _try_set(n, "floorseed", int(params["floorseed"]))
    if "offsetfloorseed" in params:
        _try_set(n, "offsetfloorseed", bool(params["offsetfloorseed"]))
    if "moduleseed" in params:
        _try_set(n, "moduleseed", int(params["moduleseed"]))
    if "offsetmoduleseed" in params:
        _try_set(n, "offsetmoduleseed", bool(params["offsetmoduleseed"]))
    if "height_scale" in params:
        _try_set(n, "height_scale", bool(params["height_scale"]))
    if "override_maxdist" in params:
        _try_set(n, "override_maxdist", clamp(float(params["override_maxdist"]), 0.0, 1e6))
    if "get_instance" in params:
        _try_set(n, "get_instance", bool(params["get_instance"]))
    if "engine" in params:
        _str_menu_set(n, "engine", str(params["engine"]), _BFP_ENGINE)
    if "pivot" in params:
        _menu_set(n, "set_middle", str(params["pivot"]), _BFP_PIVOT)
    if "output_orient" in params:
        _try_set(n, "input", bool(params["output_orient"]))
    if "group" in params:
        _try_set(n, "group1", str(params["group"]))
    if "pattern" in params:
        _try_set(n, "pattern1", str(params["pattern"]))
    return _result(n)


@endpoint("building_generator")
def building_generator(params):
    """Labs Building Generator (labs::building_generator::4.0) — slices a 3D blockout into floors and
    skins it with modules. `input` (input 0) = the Blockout Geometry (a box/mass); optional `modules`
    (input 1) = Building Modules, `handplaced` (input 2), `volumetric` (input 3). Facade/ledge PATTERN
    strings are grammar data. SECURITY: data-only; module-ID reference strings (corner modules) are
    left unset; no file/code surface."""
    n = child_after(params["input"], "labs::building_generator::4.0", params.get("name"))
    if params.get("modules"):
        bridge_input(n, params["modules"], index=1, name_hint="modules")
    if params.get("handplaced"):
        bridge_input(n, params["handplaced"], index=2, name_hint="handplaced")
    if params.get("volumetric"):
        bridge_input(n, params["volumetric"], index=3, name_hint="volumetric")
    if "bColorFloors" in params:
        _try_set(n, "bColorFloors", bool(params["bColorFloors"]))
    if "fFloorHeight" in params:
        _try_set(n, "fFloorHeight", clamp(float(params["fFloorHeight"]), 0.01, 1000.0))
    if "iSeed" in params:
        _try_set(n, "iSeed", int(params["iSeed"]))
    if "bExperimentalLedges" in params:
        _try_set(n, "bExperimentalLedges", bool(params["bExperimentalLedges"]))
    if "bScaleModules" in params:
        _try_set(n, "bScaleModules", bool(params["bScaleModules"]))
    if "snapinputgeo" in params:
        _try_set(n, "snapinputgeo", bool(params["snapinputgeo"]))
    if "sFacadePattern" in params:
        _try_set(n, "sFacadePattern", str(params["sFacadePattern"]))
    if "bFacadeCorner" in params:
        _try_set(n, "bFacadeCorner", bool(params["bFacadeCorner"]))
    if "bTopLedge" in params:
        _try_set(n, "bTopLedge", bool(params["bTopLedge"]))
    if "fTopLedgeHeight" in params:
        _try_set(n, "fTopLedgeHeight", clamp(float(params["fTopLedgeHeight"]), 0.0, 100.0))
    if "sTopLedgePattern" in params:
        _try_set(n, "sTopLedgePattern", str(params["sTopLedgePattern"]))
    if "bTopLedgeCorner" in params:
        _try_set(n, "bTopLedgeCorner", bool(params["bTopLedgeCorner"]))
    if "bBottomLedge" in params:
        _try_set(n, "bBottomLedge", bool(params["bBottomLedge"]))
    if "fBottomLedgeHeight" in params:
        _try_set(n, "fBottomLedgeHeight", clamp(float(params["fBottomLedgeHeight"]), 0.0, 100.0))
    if "sBottomLedgePattern" in params:
        _try_set(n, "sBottomLedgePattern", str(params["sBottomLedgePattern"]))
    if "bBottomLedgeCorner" in params:
        _try_set(n, "bBottomLedgeCorner", bool(params["bBottomLedgeCorner"]))
    return _result(n)


@endpoint("building_module")
def building_module(params):
    """Labs Building Module (labs::building_generator_utility::2.0) — tags an input mesh as a reusable
    building MODULE (name, weight, priority, bounding box) for building_generator / building_from_
    patterns to consume. `input` (input 0) = the module geometry; optional `bbox` (input 1) = a custom
    bounding box. SECURITY: data-only; no file/code surface."""
    n = child_after(params["input"], "labs::building_generator_utility::2.0", params.get("name"))
    if params.get("bbox"):
        bridge_input(n, params["bbox"], index=1, name_hint="bbox")
    if "module_name" in params:
        _try_set(n, "name1", str(params["module_name"]))
    if "weight" in params:
        _try_set(n, "weight", clamp(float(params["weight"]), 0.0, 1e6))
    if "priority" in params:
        _try_set(n, "priority", int(clamp(int(params["priority"]), -1000, 1000)))
    if "fill_dimensions" in params:
        _try_set(n, "FillDimensions", bool(params["fill_dimensions"]))
    if "use_internal_bbox" in params:
        _try_set(n, "bUseInternalBBox", bool(params["use_internal_bbox"]))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e4))
    if "size" in params:
        _try_set(n, "size", clamp(float(params["size"]), 1e-4, 1e4))
    return _result(n)


# ── Road ────────────────────────────────────────────────────────────────────────────────────────
@endpoint("pathfinding_global")
def pathfinding_global(params):
    """Labs Pathfinding Global (labs::pathfinding_global::1.0) — computes least-cost PATHS between
    settlement endpoints over a terrain. `input` (input 0) = the Connection Network (settlement points
    / a settlement_connections output carrying an `endpoints` group), `terrain` (input 1, REQUIRED) =
    the Terrain Mesh to traverse. `numberofpoints` (scattered-source relaxation) is EXPENSIVE and hard-
    clamped. SECURITY: data-only; no file/code surface."""
    n = child_after(params["input"], "labs::pathfinding_global::1.0", params.get("name"))
    bridge_input(n, params["terrain"], index=1, name_hint="terrain")  # required 2nd input
    if "source" in params:
        _menu_set(n, "source", str(params["source"]), _PF_SOURCE)
    if "generate" in params:
        _menu_set(n, "generatepoints", str(params["generate"]), _PF_GENERATE)
    if "numberofpoints" in params:
        _try_set(n, "numberofpoints", int(clamp(int(params["numberofpoints"]), 16, 500000)))  # EXPENSIVE
    if "density" in params:
        _try_set(n, "density", clamp(float(params["density"]), 1e-4, 1e4))
    if "relaxiterations" in params:
        _try_set(n, "relaxiterations", int(clamp(int(params["relaxiterations"]), 0, 100)))  # EXPENSIVE
    if "noiseamplitude" in params:
        _try_set(n, "noiseamplitude", clamp(float(params["noiseamplitude"]), 0.0, 1e4))
    if "enableavoidance" in params:
        _try_set(n, "enableavoidance", bool(params["enableavoidance"]))
    if "avoidanceattribute" in params:
        _try_set(n, "avoidanceattribute", str(params["avoidanceattribute"]))
    if "outputdistance" in params:
        _try_set(n, "outputdistance", bool(params["outputdistance"]))
    if "distancename" in params:
        _try_set(n, "distancename", str(params["distancename"]))
    if "endpoints" in params:
        _try_set(n, "endpoints", str(params["endpoints"]))
    return _result(n)


@endpoint("road_generator")
def road_generator(params):
    """Labs Road Generator (labs::road_generator::1.2) — builds road-surface mesh with intersections
    from input road CURVES (centerlines). `input` (input 0) = the road-network curves. SECURITY:
    data-only; the Custom-Module op-path (`objpath1`) is NOT exposed and left unset; no file/code
    surface."""
    n = child_after(params["input"], "labs::road_generator::1.2", params.get("name"))
    if "width" in params:
        _try_set(n, "width", clamp(float(params["width"]), 1e-3, 1e4))
    if "min_width" in params:
        _try_set(n, "min_width", clamp(float(params["min_width"]), 1e-3, 1e4))
    if "resampleseglen" in params:
        _try_set(n, "resampleseglen", clamp(float(params["resampleseglen"]), 0.01, 1e4))
    if "inlinedist" in params:
        _try_set(n, "inlinedist", clamp(float(params["inlinedist"]), 0.0, 1e4))
    if "fusedist" in params:
        _try_set(n, "fusedist", clamp(float(params["fusedist"]), 0.0, 1e4))
    if "width_model" in params:
        _try_set(n, "width_model", clamp(float(params["width_model"]), 1e-3, 1e4))
    if "modular_size" in params:
        _try_set(n, "modular_size", clamp(float(params["modular_size"]), 1e-3, 1e4))
    if "intersection_length" in params:
        _try_set(n, "value2v1", clamp(float(params["intersection_length"]), 0.0, 1e4))
    if "roundness" in params:
        _try_set(n, "domainu1", clamp(float(params["roundness"]), 0.0, 1.0))
    if "convexity" in params:
        _try_set(n, "amount", clamp(float(params["convexity"]), -10.0, 10.0))
    if "resolution" in params:
        _try_set(n, "segs", int(clamp(int(params["resolution"]), 1, 200)))
    if "subdivide" in params:
        _try_set(n, "T_subdivide", bool(params["subdivide"]))
    if "sharp_corner" in params:
        _try_set(n, "sharp_corner", clamp(float(params["sharp_corner"]), 0.0, 180.0))
    if "corner_blur" in params:
        _try_set(n, "iterations", int(clamp(int(params["corner_blur"]), 0, 200)))
    if "bevel_amount" in params:
        _try_set(n, "bevel_amount", clamp(float(params["bevel_amount"]), 0.0, 1e3))
    if "uv_scale" in params:
        _try_set(n, "uv_scale", clamp(float(params["uv_scale"]), 1e-3, 1e4))
    if "bridge_support" in params:
        _try_set(n, "T_bridge", bool(params["bridge_support"]))
    if "visualize_type" in params:
        _try_set(n, "T_vis", bool(params["visualize_type"]))
    return _result(n)


@endpoint("settlement_connections")
def settlement_connections(params):
    """Labs Settlement Connections (labs::settlement_connections::1.0) — connects settlement POINTS
    into a road-network graph, filtering connections by angle / distance / count. `input` (input 0) =
    the settlement points. Feeds pathfinding_global. SECURITY: data-only; no file/code surface."""
    n = child_after(params["input"], "labs::settlement_connections::1.0", params.get("name"))
    if "enableangle" in params:
        _try_set(n, "enableangle", bool(params["enableangle"]))
    if "limitnum" in params:
        _try_set(n, "limitnum", bool(params["limitnum"]))
    if "anglemode" in params:
        _menu_set(n, "anglemode", str(params["anglemode"]), _SC_ANGLEMODE)
    if "uniformangle" in params:
        _try_set(n, "uniformangle", clamp(float(params["uniformangle"]), 0.0, 180.0))
    if "mindistance" in params:
        _try_set(n, "mindistance", clamp(float(params["mindistance"]), 0.0, 1e6))
    if "minangle" in params:
        _try_set(n, "minangle", clamp(float(params["minangle"]), 0.0, 180.0))
    if "maxdistance" in params:
        _try_set(n, "maxdistance", clamp(float(params["maxdistance"]), 0.0, 1e6))
    if "maxangle" in params:
        _try_set(n, "maxangle", clamp(float(params["maxangle"]), 0.0, 180.0))
    if "connectionlimit" in params:
        _try_set(n, "connectionlimit", int(clamp(int(params["connectionlimit"]), 0, 1000)))
    if "outputdistance" in params:
        _try_set(n, "outputdistance", bool(params["outputdistance"]))
    if "distancename" in params:
        _try_set(n, "distancename", str(params["distancename"]))
    if "endpoints" in params:
        _try_set(n, "endpoints", str(params["endpoints"]))
    return _result(n)


# ── Prop ─────────────────────────────────────────────────────────────────────────────────────────
@endpoint("cable_generator")
def cable_generator(params):
    """Labs Cable Generator (labs::cable_generator::2.0) — builds hanging cable / wire meshes. `input`
    (input 0) = curves (or surfaces to connect); optional `geometry` (input 1) = geometry to route
    cables through (`inputtype` = through_geometry). `curveamountcable`/`geoamountcable` and
    `resolutioncable` drive polycount; `simtype` wire_sim runs an internal sim. SECURITY: data-only;
    no file/code surface."""
    n = child_after(params["input"], "labs::cable_generator::2.0", params.get("name"))
    if params.get("geometry"):
        bridge_input(n, params["geometry"], index=1, name_hint="geometry")
    if "inputtype" in params:
        _menu_set(n, "inputtype", str(params["inputtype"]), _CABLE_INPUT)
    if "surfacedistance" in params:
        _try_set(n, "surfacedistance", clamp(float(params["surfacedistance"]), 0.0, 1e6))
    if "surfacedensity" in params:
        _try_set(n, "surfacedensity", clamp(float(params["surfacedensity"]), 0.0, 1e4))
    if "surfaceblend" in params:
        _try_set(n, "surfaceblend", clamp(float(params["surfaceblend"]), 0.0, 1.0))
    if "curveamountcable" in params:
        _try_set(n, "curveamountcable", int(clamp(int(params["curveamountcable"]), 1, 100)))
    if "treatpolysas" in params:
        _menu_set(n, "treatpolysas", str(params["treatpolysas"]), _CABLE_POLYAS)
    if "curvespacing" in params:
        _try_set(n, "curvespacing", clamp(float(params["curvespacing"]), 0.0, 1e4))
    if "curvevariation" in params:
        _try_set(n, "curvevariation", clamp(float(params["curvevariation"]), 0.0, 1e4))
    if "globalseed" in params:
        _try_set(n, "globalseed", clamp(float(params["globalseed"]), -1e6, 1e6))
    if "geoamountcable" in params:
        _try_set(n, "geoamountcable", int(clamp(int(params["geoamountcable"]), 1, 100)))
    if "geocurvetype" in params:
        _menu_set(n, "geocurvetype", str(params["geocurvetype"]), _CABLE_POLYAS)
    if "mainscale" in params:
        _try_set(n, "mainscale", clamp(float(params["mainscale"]), 1e-4, 1e3))
    if "randradius" in params:
        _try_set(n, "randradius", bool(params["randradius"]))
    if "minscale" in params:
        _try_set(n, "minscale", clamp(float(params["minscale"]), 0.0, 1e3))
    if "maxscale" in params:
        _try_set(n, "maxscale", clamp(float(params["maxscale"]), 0.0, 1e3))
    if "scaleseed" in params:
        _try_set(n, "scaleseed", clamp(float(params["scaleseed"]), -1e6, 1e6))
    if "resolutioncable" in params:
        _try_set(n, "resolutioncable", clamp(float(params["resolutioncable"]), 1e-3, 1e3))
    if "divisions" in params:
        _try_set(n, "divisions", int(clamp(int(params["divisions"]), 3, 64)))
    if "addends" in params:
        _try_set(n, "addends", bool(params["addends"]))
    if "simtype" in params:
        _menu_set(n, "simtype", str(params["simtype"]), _CABLE_SIM)
    if "subcables" in params:
        _try_set(n, "subcables", bool(params["subcables"]))
    if "num_subcables" in params:
        _try_set(n, "iterations", int(clamp(int(params["num_subcables"]), 1, 50)))
    if "subscale" in params:
        _try_set(n, "subscale", clamp(float(params["subscale"]), 1e-4, 1e3))
    if "colors" in params:
        _try_set(n, "colors", bool(params["colors"]))
    return _result(n)


@endpoint("lot_subdivision")
def lot_subdivision(params):
    """Labs Lot Subdivision (labs::lot_subdivision::2.0) — recursively subdivides a 2D polygon block
    into building LOTS. `input` (input 0) = a flat 2D polygon (a block/parcel). `iterations` drives
    the subdivision depth and is clamped. SECURITY: data-only; no file/code surface."""
    n = child_after(params["input"], "labs::lot_subdivision::2.0", params.get("name"))
    if "alignment" in params:
        _menu_set(n, "alignment", str(params["alignment"]), _LOT_ALIGN)
    if "minlotsize" in params:
        _try_set(n, "minlotsize", clamp(float(params["minlotsize"]), 1e-4, 1e4))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 100)))  # subdivision depth
    if "shapeseed" in params:
        _try_set(n, "shapeseed", clamp(float(params["shapeseed"]), -1e6, 1e6))
    if "irregularity" in params:
        _try_set(n, "irregularity", clamp(float(params["irregularity"]), 0.0, 5.0))
    if "vertical_bias" in params:
        _try_set(n, "vertical_bias", clamp(float(params["vertical_bias"]), -10.0, 10.0))
    if "vertical_packing" in params:
        _try_set(n, "vertical_packing", clamp(float(params["vertical_packing"]), 0.0, 100.0))
    if "clusterlots" in params:
        _try_set(n, "clusterlots", bool(params["clusterlots"]))
    if "numberofclusters" in params:
        _try_set(n, "numberofclusters", int(clamp(int(params["numberofclusters"]), 1, 1000)))
    if "seed" in params:
        _try_set(n, "seed", clamp(float(params["seed"]), -1e6, 1e6))
    return _result(n)


@endpoint("scifi_panels")
def scifi_panels(params):
    """Labs Sci-Fi Panels (labs::scifi_panels::1.0) — greebles a mesh with paneling: subdivides the
    surface into lots then extrudes bordered panels with notches / bevels. `input` (input 0) = the
    mesh to panel. SECURITY: data-only; the vertex-color Ramp stays at HDA default; no file/code
    surface."""
    n = child_after(params["input"], "labs::scifi_panels::1.0", params.get("name"))
    if "generate_uvs" in params:
        _menu_set(n, "generate_uvs", str(params["generate_uvs"]), _PANEL_UV)
    if "pattern_rotation" in params:
        _try_set(n, "pattern_rotation", clamp(float(params["pattern_rotation"]), -360.0, 360.0))
    if "border_thickness" in params:
        _try_set(n, "border_thickness", clamp(float(params["border_thickness"]), 0.0, 1e3))
    if "g_seed" in params:
        _try_set(n, "g_seed", clamp(float(params["g_seed"]), -1e6, 1e6))
    if "extrusion_depth" in params:
        _try_set(n, "extrusion_depth", clamp(float(params["extrusion_depth"]), -1e3, 1e3))
    if "panel_deletion_chance" in params:
        _try_set(n, "panel_deletion_chance", clamp(float(params["panel_deletion_chance"]), 0.0, 100.0))
    if "deletion_seed" in params:
        _try_set(n, "deletion_seed", clamp(float(params["deletion_seed"]), -1e6, 1e6))
    if "enable_vertex_colors" in params:
        _try_set(n, "enable_vertex_colors", bool(params["enable_vertex_colors"]))
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    if "irregularity" in params:
        _try_set(n, "irregularity", clamp(float(params["irregularity"]), 0.0, 5.0))
    if "min_lot_size" in params:
        _try_set(n, "min_lot_size", clamp(float(params["min_lot_size"]), 1e-5, 1e4))
    if "vertical_bias" in params:
        _try_set(n, "vertical_bias", clamp(float(params["vertical_bias"]), -10.0, 10.0))
    if "alignment" in params:
        _menu_set(n, "alignment", str(params["alignment"]), _LOT_ALIGN)
    if "cluster_lots" in params:
        _try_set(n, "cluster_lots", bool(params["cluster_lots"]))
    if "number_of_clusters" in params:
        _try_set(n, "number_of_clusters", int(clamp(int(params["number_of_clusters"]), 1, 1000)))
    if "vertical_packing" in params:
        _try_set(n, "vertical_packing", clamp(float(params["vertical_packing"]), 0.0, 100.0))
    if "spacing" in params:
        _try_set(n, "spacing", clamp(float(params["spacing"]), 0.0, 1e3))
    if "spacing_variation" in params:
        _try_set(n, "spacing_variation", clamp(float(params["spacing_variation"]), 0.0, 1e3))
    if "notch_percentage" in params:
        _try_set(n, "notch_percentage", clamp(float(params["notch_percentage"]), 0.0, 100.0))
    if "corner_bevels_chance" in params:
        _try_set(n, "corner_bevels_chance", clamp(float(params["corner_bevels_chance"]), 0.0, 100.0))
    if "corner_bevels_depth" in params:
        _try_set(n, "corner_bevels_depth", clamp(float(params["corner_bevels_depth"]), 0.0, 1e3))
    return _result(n)


@endpoint("simple_rope_wrap")
def simple_rope_wrap(params):
    """Labs Simple Rope Wrap (labs::simple_rope_wrap::1.0) — sweeps rope/cable geometry over polygon
    surfaces and wraps it around a geometry object. `input` (input 0) = the Polygon Surfaces the rope
    runs across; `geometry` (input 1, REQUIRED) = the Geometry Object to wrap around; optional
    `profile` (input 2) = a custom cross-section profile (used with shape=custom). `simulated` runs an
    internal quasi-static sim (`quasistaticframes`). SECURITY: data-only; no file/code surface."""
    n = child_after(params["input"], "labs::simple_rope_wrap::1.0", params.get("name"))
    bridge_input(n, params["geometry"], index=1, name_hint="geometry")  # required 2nd input
    if params.get("profile"):
        bridge_input(n, params["profile"], index=2, name_hint="profile")
    if "resolution" in params:
        _try_set(n, "length", clamp(float(params["resolution"]), 1e-3, 10.0))
    if "optimize_curves" in params:
        _try_set(n, "inline", bool(params["optimize_curves"]))
    if "inlinedist" in params:
        _try_set(n, "inlinedist", clamp(float(params["inlinedist"]), 0.0, 1e3))
    if "simulated" in params:
        _try_set(n, "simulated", bool(params["simulated"]))
    if "quasistaticframes" in params:
        _try_set(n, "quasistaticframes", int(clamp(int(params["quasistaticframes"]), 1, 500)))
    if "shape" in params:
        _menu_set(n, "shape", str(params["shape"]), _ROPE_SHAPE)
    if "diameter" in params:
        _try_set(n, "scale", clamp(float(params["diameter"]), 1e-4, 1e3))
    if "twist_per_unit" in params:
        _try_set(n, "incroll", clamp(float(params["twist_per_unit"]), -3600.0, 3600.0))
    if "rows" in params:
        _try_set(n, "divs", int(clamp(int(params["rows"]), 3, 64)))
    if "cuspangle" in params:
        _try_set(n, "cuspangle", clamp(float(params["cuspangle"]), 0.0, 180.0))
    if "uvscale" in params:
        _try_set(n, "uvscale", clamp(float(params["uvscale"]), 1e-4, 1e4))
    if "uvrotation" in params:
        _try_set(n, "uvrotation", clamp(float(params["uvrotation"]), -360.0, 360.0))
    if "polyreduce" in params:
        _try_set(n, "polyreduce", bool(params["polyreduce"]))
    if "percentage" in params:
        _try_set(n, "percentage", clamp(float(params["percentage"]), 0.0, 100.0))
    if "mass" in params:
        _try_set(n, "mass", clamp(float(params["mass"]), 1e-4, 1e4))
    if "stretchrestscale" in params:
        _try_set(n, "stretchrestscale", clamp(float(params["stretchrestscale"]), 0.0, 10.0))
    if "stretchstiffness" in params:
        _try_set(n, "stretchstiffness", clamp(float(params["stretchstiffness"]), 0.0, 100.0))
    if "bendstiffness" in params:
        _try_set(n, "bendstiffness", clamp(float(params["bendstiffness"]), 0.0, 100.0))
    return _result(n)

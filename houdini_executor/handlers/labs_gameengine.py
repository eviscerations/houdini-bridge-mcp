"""SideFX Labs — Game Engine (data-only handlers). Params verified against live H21.0.671 (parm name/type, ordered-
menu tokens, input/output counts, input LABELS, and a headless cook / wire-check per node).

Two node kinds in this lane, handled per the brief:
  * SOP game-mesh prep (cooked, prims/points>0 or a clean terminal-exporter passthrough):
      gameres, unreal_worldcomposition_prepare, niagara, pcg_export, terrain_layer_export,
      terrain_layer_import (source reader), unreal_groom_export, unreal_spline, vector_field,
      volume_texture
  * ROP / Driver exporters (WIRE-ONLY file-writers — built + wired + path-confined, execute NEVER
      pressed, return exported=False):
      niagara_rop, rbd_to_fbx, vertex_animation_textures, xyz_pointcloud_exporter

SECURITY (data-only boundary):
  * Every file surface the tool sets is realpath-confined via confined_path(): gameres.sOutputFile,
    niagara.outputpath, pcg_export.file_mesh/file_mat, terrain_layer_export.output,
    terrain_layer_import.sHeightmap (READ), unreal_groom_export.filename, unreal_spline
    .file_export_spline, vector_field.outputFile, volume_texture.output_picture, and every ROP
    export path. No bake/export/render is ever fired (SOP writers leave the `execute`/`export`/
    `render` button unpressed; ROPs are built WIRE-ONLY).
  * gameres embeds a maps bake: its FBX low/high side-exports (exportlow/exporthigh) are FORCED OFF
    and their paths (sopoutputlow/high) are never exposed.
  * unreal_spline's `import_spline` (a callback toggle) and every node's pre/post-render SCRIPT parms
    (prerender/postrender/lprerender/lpostrender — code) are left unset and never exposed.
  * Node references (soppath/node_to_export/objpath1/customshapepath/overridenode) are scene node
    PATHS (data, not files) — set as plain strings; the referenced node is never resolved/cooked.
  * Filename tokens (assetname, sNameOverride, sHeightmapName, sPaintLayerPrefix, geosuffix, layer
    names) are sanitized so a name token can never smuggle a filesystem path.

SKIPPED: flipbook_textures,
impostor_texture, motion_vectors (Mantra/GL RENDER ROPs — interactive/rig-dependent, not data
exporters) and unreal_pivotpainter (needs a bespoke Pivots-hierarchy point cloud on input 1 that
generic geometry cannot satisfy — no green headless cook).
"""

import hou
from houdini_executor.server import (endpoint, confined_path, clamp, child_after,
                                     bridge_input, out_context)
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────
def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)




def _menu_set(node, parm, token, tokens):
    """Set an ordered/string menu by TOKEN. Verified on H21.0.671: p.set(str(token)) resolves by
    token for Menu (index-stored), Int-menu and String-menu parms alike (set(int) is WRONG for
    Menu-type — it stores a raw index). No-op if the token isn't a known menu item."""
    if token not in tokens:
        return False
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(str(token))
        return True
    except Exception:
        return False


def _safe_token(v):
    """Sanitize a name/label token (asset/layer/prefix/suffix): reject path separators, parent refs
    and drive letters so a name token can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("name token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


def _node_in_parent(anchor_path, ntype, name=None):
    """Create `ntype` in the (display-SOP) parent network of `anchor_path`, with NO inputs wired.
    For multi-input HDAs whose required inputs are NOT input 0 (e.g. groom Guides=in1/Skin=in2);
    the caller then bridge_input()s each operand into its correct index."""
    src = hou.node(anchor_path)
    if src is None:
        raise ValueError(f"no such node: {anchor_path}")
    try:
        if isinstance(src, hou.ObjNode):
            disp = src.displayNode() or src.renderNode()
            if disp is not None:
                src = disp
    except Exception:
        pass
    parent = src.parent()
    n = parent.createNode(ntype, name) if name else parent.createNode(ntype)
    n.moveToGoodPosition()
    return n


def _out_node(ntype, name=None):
    """Create a Driver/ROP node in /out (created on demand). WIRE-ONLY: never executed."""
    out = out_context()
    return out.createNode(ntype, name) if name else out.createNode(ntype)


# ── ordered-menu token tuples (native tokens; set via _menu_set by token string) ─────────────────
_GAMERES_METHOD = ("0", "1", "3", "4")                       # gameres remesh method (Menu, idx-stored)
_NIAGARA_RANGE = ("off", "normal", "on", "single_frame_time")  # niagara/niagara_rop range_mode
_PCG_ROTMODE = ("0", "1")                                    # pcg_export rotmode
_TILE_METHOD = ("tilesize", "numtiles")                      # terrain_layer_export tile_method
_FILE_NAMING = ("udim", "uvtile", "frame", "xytile")         # terrain_layer_export file_naming
_GROOM_GROUPID = ("groupid", "groupname", "groupidname")     # unreal_groom_export groupidentifier
_GROOM_FORMAT = ("default", "hdf5", "ogawa")                 # unreal_groom_export alembic format
_VF_INPUT_TYPE = ("0", "1")                                  # vector_field input_type
_VT_MODE = ("0", "1", "2", "3")                              # volume_texture mode
_VT_UPAXIS = ("0", "1")                                      # volume_texture up_axis
_VAT_MODE = ("0", "1", "2", "3")                             # vertex_animation_textures mode
_VAT_ENGINE = ("unreal", "unity", "custom")                  # vertex_animation_textures engine
_VAT_IMGFMT = ("exr", "tiff", "png", "tga")                  # vertex_animation_textures imageformat
_VAT_DEPTH = ("int8", "int16", "int32", "float16", "float32")  # vertex_animation_textures depth


# ══ SOP game-mesh prep ═════════════════════════════════════════════════════════════════════════

# ── 1. gameres (chain; in0 hi-res mesh) — game-res LOD + WIRE-ONLY bake ──────────────────────────
@endpoint("gameres")
def gameres(params):
    """SideFX Labs GameRes (labs::gameres::3.1) — reduces a high-res mesh (`input`, input 0) to a
    game-resolution LOD via polyreduce / Instant Meshes / voxel-remesh, and sets up an EMBEDDED map
    bake. Its cooked SOP output IS the reduced mesh. `finalcount` targets the poly budget;
    `use_instantmeshes` swaps to quad-remesh; `enable_voxelization`+`resolution` do a voxel rebuild.
    SECURITY: WIRE-ONLY bake — `execute` is never pressed; the FBX low/high side-exports
    (exportlow/exporthigh) are FORCED OFF and their paths never exposed; `sOutputFile` (bake dir) is
    confined to the working dir when supplied."""
    n = child_after(params["input"], "labs::gameres::3.1", params.get("name"))
    _try_set(n, "exportlow", False)   # SECURITY: never fire the FBX side-writes
    _try_set(n, "exporthigh", False)
    if "finalcount" in params:
        _try_set(n, "finalcount", int(clamp(int(params["finalcount"]), 1, 5_000_000)))
    if "use_instantmeshes" in params:
        _try_set(n, "use_instantmeshes", bool(params["use_instantmeshes"]))
    if "reducepassedtarget" in params:
        _try_set(n, "reducepassedtarget", bool(params["reducepassedtarget"]))
    if "qualitytolerance" in params:
        _try_set(n, "qualitytolerance", clamp(float(params["qualitytolerance"]), 0.0, 1.0))
    if "originalpoints" in params:
        _try_set(n, "originalpoints", bool(params["originalpoints"]))
    if "preservequads" in params:
        _try_set(n, "preservequads", bool(params["preservequads"]))
    if "equalizelengths" in params:
        _try_set(n, "equalizelengths", clamp(float(params["equalizelengths"]), 0.0, 1.0))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _GAMERES_METHOD)
    if "enable_voxelization" in params:
        _try_set(n, "enable_voxelization", bool(params["enable_voxelization"]))
    if "resolution" in params:
        _try_set(n, "resolution", clamp(float(params["resolution"]), 1e-3, 4096.0))
    if "adaptivity" in params:
        _try_set(n, "adaptivity", clamp(float(params["adaptivity"]), 0.0, 1.0))
    if "dilate_erode" in params:
        _try_set(n, "dilate_erode", clamp(float(params["dilate_erode"]), -100.0, 100.0))
    if "project" in params:
        _try_set(n, "project", bool(params["project"]))
    if "post_smooth" in params:
        _try_set(n, "post_smooth", int(clamp(int(params["post_smooth"]), 0, 100)))
    if "sharpen_features" in params:
        _try_set(n, "sharpen_features", bool(params["sharpen_features"]))
    if "edge_tolerance" in params:
        _try_set(n, "edge_tolerance", clamp(float(params["edge_tolerance"]), 0.0, 180.0))
    if "num_points" in params:
        _try_set(n, "num_points", int(clamp(int(params["num_points"]), 1, 5_000_000)))
    out_dir = None
    if params.get("sOutputFile"):
        out_dir = confined_path(params["sOutputFile"])
        _try_set(n, "sOutputFile", out_dir)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "bake_output": out_dir, "baked": False,
            "note": "reduced LOD cooked; embedded map bake WIRE-ONLY (fire it yourself)"}


# ── 2. unreal_worldcomposition_prepare (chain; in0 terrain, in1/2 opt) — tiling prep, no file ────
@endpoint("unreal_worldcomposition_prepare")
def unreal_worldcomposition_prepare(params):
    """SideFX Labs Unreal World Composition Prepare (labs::unreal_worldcomposition_prepare::1.0) —
    prepares an incoming terrain/mesh (`input`, input 0) for Unreal World Composition by writing a
    per-tile attribute and (optionally) proxy/level metadata; its cooked SOP output IS the tagged
    geometry. `tilenum` sets the tile count; `levelpath`/`materialpath` are Unreal CONTENT paths
    written as string attributes (not filesystem paths). Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::unreal_worldcomposition_prepare::1.0", params.get("name"))
    if "maketileattribute" in params:
        _try_set(n, "maketileattribute", bool(params["maketileattribute"]))
    if "tilenum" in params:
        _try_set(n, "tilenum", int(clamp(int(params["tilenum"]), 0, 4096)))
    if "proxies" in params:
        _try_set(n, "proxies", bool(params["proxies"]))
    if "levelpath" in params:
        _try_set(n, "levelpath", str(params["levelpath"]))
    if "materialpath" in params:
        _try_set(n, "materialpath", str(params["materialpath"]))
    if "isolatelayer" in params:
        _try_set(n, "isolatelayer", bool(params["isolatelayer"]))
    if "layer" in params:
        _try_set(n, "layer", _safe_token(params["layer"]))
    if "viscolors" in params:
        _try_set(n, "viscolors", bool(params["viscolors"]))
    if "guides" in params:
        _try_set(n, "guides", bool(params["guides"]))
    if "isolatetile" in params:
        _try_set(n, "isolatetile", bool(params["isolatetile"]))
    if "isolatedtile" in params:
        _try_set(n, "isolatedtile", int(clamp(int(params["isolatedtile"]), 0, 100000)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. niagara (chain; in0 particles/points) — WIRE-ONLY Niagara export ───────────────────────────
@endpoint("niagara")
def niagara(params):
    """SideFX Labs Niagara (labs::niagara::2.0) — a WIRE-ONLY exporter SOP that packages the incoming
    particles/points (`input`, input 0) for Unreal's Niagara particle system. It is a terminal writer
    (0 outputs): its cook passes the point stream through for inspection but writes nothing until the
    human fires `execute`. SECURITY: `outputpath` is confined to the working dir when supplied; the
    export is NEVER auto-fired (returns exported=False). Attribute-cast fields are plain tokens."""
    n = child_after(params["input"], "labs::niagara::2.0", params.get("name"))
    if "range_mode" in params:
        _menu_set(n, "range_mode", str(params["range_mode"]), _NIAGARA_RANGE)
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    if "overwrite" in params:
        _try_set(n, "overwrite", bool(params["overwrite"]))
    if "attr_clamp" in params:
        _try_set(n, "attr_clamp", bool(params["attr_clamp"]))
    if "export_current_frame_as_time_zero" in params:
        _try_set(n, "export_current_frame_as_time_zero", bool(params["export_current_frame_as_time_zero"]))
    if "export_start_frame_as_time_zero" in params:
        _try_set(n, "export_start_frame_as_time_zero", bool(params["export_start_frame_as_time_zero"]))
    out_path = None
    if params.get("outputpath"):
        out_path = confined_path(params["outputpath"])
        _try_set(n, "outputpath", out_path)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "output": out_path, "exported": False,
            "note": "niagara export wired (WIRE-ONLY); fire the export yourself"}


# ── 4. pcg_export (chain; in0 opt points) — WIRE-ONLY Unreal PCG export ───────────────────────────
@endpoint("pcg_export")
def pcg_export(params):
    """SideFX Labs PCG Export (labs::pcg_export::1.0) — a WIRE-ONLY exporter SOP that packages the
    incoming instance points (`input`, input 0) for Unreal's PCG (Procedural Content Generation)
    framework. Terminal writer (0 outputs); the cook passes the points through for inspection.
    SECURITY: `file_mesh`/`file_mat` are confined to the working dir when supplied; the export is
    NEVER auto-fired (returns exported=False). Attribute-name fields are plain tokens."""
    n = child_after(params["input"], "labs::pcg_export::1.0", params.get("name"))
    if "enablemesh" in params:
        _try_set(n, "enablemesh", bool(params["enablemesh"]))
    if "enablemat" in params:
        _try_set(n, "enablemat", bool(params["enablemat"]))
    if "mesh" in params:
        _try_set(n, "mesh", _safe_token(params["mesh"]))
    if "rotmode" in params:
        _menu_set(n, "rotmode", str(params["rotmode"]), _PCG_ROTMODE)
    file_mesh = file_mat = None
    if params.get("file_mesh"):
        file_mesh = confined_path(params["file_mesh"])
        _try_set(n, "file_mesh", file_mesh)
    if params.get("file_mat"):
        file_mat = confined_path(params["file_mat"])
        _try_set(n, "file_mat", file_mat)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "file_mesh": file_mesh, "file_mat": file_mat, "exported": False,
            "note": "pcg export wired (WIRE-ONLY); fire the export yourself"}


# ── 5. terrain_layer_export (chain; in0 heightfield) — WIRE-ONLY UE landscape export ─────────────
@endpoint("terrain_layer_export")
def terrain_layer_export(params):
    """SideFX Labs Terrain Layer Export (labs::terrain_layer_export::1.1) — a WIRE-ONLY exporter SOP
    that writes the incoming heightfield (`input`, input 0) as Unreal/Unity landscape heightmap +
    paint-layer images to `output`. Terminal writer (0 outputs). `tile_output`+`tile_method`/
    `tile_size`/`num_tiles` split the export into landscape tiles; `file_naming` picks the tile
    naming scheme. SECURITY: `output` (dir) is confined; the export is NEVER auto-fired (returns
    exported=False). Layer/name tokens are sanitized."""
    n = child_after(params["input"], "labs::terrain_layer_export::1.1", params.get("name"))
    if "sPaintLayerPrefix" in params:
        _try_set(n, "sPaintLayerPrefix", _safe_token(params["sPaintLayerPrefix"]))
    if "sHeightmapName" in params:
        _try_set(n, "sHeightmapName", _safe_token(params["sHeightmapName"]))
    if "tile_output" in params:
        _try_set(n, "tile_output", bool(params["tile_output"]))
    if "tile_method" in params:
        _menu_set(n, "tile_method", str(params["tile_method"]), _TILE_METHOD)
    if "tile_size" in params:
        _try_set(n, "tile_size", int(clamp(int(params["tile_size"]), 1, 16384)))
    if "num_tiles" in params:
        _try_set(n, "num_tiles", int(clamp(int(params["num_tiles"]), 1, 4096)))
    if "tile_overlap" in params:
        _try_set(n, "tile_overlap", int(clamp(int(params["tile_overlap"]), 0, 4096)))
    if "file_naming" in params:
        _menu_set(n, "file_naming", str(params["file_naming"]), _FILE_NAMING)
    if "tile_padding" in params:
        _try_set(n, "tile_padding", int(clamp(int(params["tile_padding"]), 0, 4096)))
    if "bExportAllLayers" in params:
        _try_set(n, "bExportAllLayers", bool(params["bExportAllLayers"]))
    out_dir = None
    if params.get("output"):
        out_dir = confined_path(params["output"])
        _try_set(n, "output", out_dir)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "output": out_dir, "exported": False,
            "note": "terrain layer export wired (WIRE-ONLY); fire the export yourself"}


# ── 6. terrain_layer_import (source; 0 inputs) — confined heightmap READER ────────────────────────
@endpoint("terrain_layer_import")
def terrain_layer_import(params):
    """SideFX Labs Terrain Layer Import (labs::terrain_layer_import::1.1) — a SOURCE node (0 inputs)
    that reads an Unreal/Unity landscape heightmap image (`sHeightmap`) into a fresh /obj heightfield.
    `voxelsize` sets the resulting HF resolution; `bFlop` flips row order. Fails on name collision.
    SECURITY: `sHeightmap` is a READ path realpath-confined to the working dir; no code/write
    surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::terrain_layer_import::1.1")
    src = None
    if params.get("sHeightmap"):
        src = confined_path(params["sHeightmap"])
        _try_set(n, "sHeightmap", src)
    if "bFlop" in params:
        _try_set(n, "bFlop", bool(params["bFlop"]))
    if "voxelsize" in params:
        _try_set(n, "voxelsize", clamp(float(params["voxelsize"]), 1e-4, 10000.0))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "heightmap": src,
            "points": len(g.points()), "prims": len(g.prims())}


# ── 7. unreal_groom_export (multi-in: Strands/Guides/Skin) — cook + WIRE-ONLY Alembic export ─────
@endpoint("unreal_groom_export")
def unreal_groom_export(params):
    """SideFX Labs Unreal Groom Export (labs::unreal_groom_export::1.0) — packages a Houdini groom
    for Unreal's groom (hair/fur) system and writes it as Alembic. Inputs: `input` = dense Strands
    (input 0, optional); `guides` = groom guides (input 1); `skin` = the skin mesh (input 2). Wire at
    least `guides`+`skin` (the export cooks from those). Its SOP output passes the groom through for
    inspection. SECURITY: WIRE-ONLY — `execute`/`executebackground` are never pressed; `filename`
    (Alembic) is confined to the working dir; alembic `format` is a plain menu. Returns exported=False."""
    anchor = params.get("guides") or params.get("skin") or params.get("input")
    if not anchor:
        raise ValueError("unreal_groom_export needs at least one of: guides, skin, input")
    n = _node_in_parent(anchor, "labs::unreal_groom_export::1.0", params.get("name"))
    if params.get("input"):
        bridge_input(n, params["input"], index=0, name_hint="strands")
    if params.get("guides"):
        bridge_input(n, params["guides"], index=1, name_hint="guides")
    if params.get("skin"):
        bridge_input(n, params["skin"], index=2, name_hint="skin")
    if "outputgroups" in params:
        _try_set(n, "outputgroups", bool(params["outputgroups"]))
    if "groupidentifier" in params:
        _menu_set(n, "groupidentifier", str(params["groupidentifier"]), _GROOM_GROUPID)
    if "outputcolor" in params:
        _try_set(n, "outputcolor", bool(params["outputcolor"]))
    if "outputids" in params:
        _try_set(n, "outputids", bool(params["outputids"]))
    if "doxform" in params:
        _try_set(n, "doxform", bool(params["doxform"]))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-6, 1e6))
    if "format" in params:
        _menu_set(n, "format", str(params["format"]), _GROOM_FORMAT)
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    out_path = None
    if params.get("filename"):
        out_path = confined_path(params["filename"])
        _try_set(n, "filename", out_path)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "output": out_path, "exported": False,
            "note": "groom export wired (WIRE-ONLY); fire the Alembic export yourself"}


# ── 8. unreal_spline (chain; in0 curve) — passthrough + WIRE-ONLY UE spline export ───────────────
@endpoint("unreal_spline")
def unreal_spline(params):
    """SideFX Labs Unreal Spline (labs::unreal_spline::1.0) — packages the incoming curve (`input`,
    input 0) as an Unreal spline; its cooked SOP output passes the curve through (optionally tagged).
    `orient_along_curve` writes per-point orientation; `prim_tags` writes per-primitive tags.
    SECURITY: WIRE-ONLY — `export`/`reimport` are never pressed and the `import_spline` callback
    toggle is left unset; `file_export_spline` is confined to the working dir. Returns exported=False."""
    n = child_after(params["input"], "labs::unreal_spline::1.0", params.get("name"))
    if "orient_along_curve" in params:
        _try_set(n, "orient_along_curve", bool(params["orient_along_curve"]))
    if "prim_tags" in params:
        _try_set(n, "prim_tags", bool(params["prim_tags"]))
    out_path = None
    if params.get("file_export_spline"):
        out_path = confined_path(params["file_export_spline"])
        _try_set(n, "file_export_spline", out_path)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "output": out_path, "exported": False,
            "note": "unreal spline wired (WIRE-ONLY); fire the export yourself"}


# ── 9. vector_field (chain; in0 velocity volume/points) — viz + WIRE-ONLY .fga export ────────────
@endpoint("vector_field")
def vector_field(params):
    """SideFX Labs Vector Field (labs::vector_field) — resamples an incoming velocity field
    (`input`, input 0 — velocity volumes or points carrying a velocity attribute) into a uniform grid
    and prepares an Unreal/Unity `.fga` vector-field export; its cooked SOP output visualizes the
    sampled field. `input_type` picks volumes(0) or points(1); `velocity_volumes`/`velocity_attr`
    name the source; `div` sets the grid resolution divisor. SECURITY: WIRE-ONLY — `render` is never
    pressed; `outputFile` is confined to the working dir. Returns exported=False."""
    n = child_after(params["input"], "labs::vector_field", params.get("name"))
    if "input_type" in params:
        _menu_set(n, "input_type", str(params["input_type"]), _VF_INPUT_TYPE)
    if "velocity_volumes" in params:
        _try_set(n, "velocity_volumes", _safe_token(params["velocity_volumes"]))
    if "velocity_attr" in params:
        _try_set(n, "velocity_attr", _safe_token(params["velocity_attr"]))
    if "override_res" in params:
        _try_set(n, "override_res", bool(params["override_res"]))
    if "div" in params:
        _try_set(n, "div", clamp(float(params["div"]), 1e-3, 1000.0))
    if "npts" in params:
        _try_set(n, "npts", int(clamp(int(params["npts"]), 1, 1_000_000)))
    if "visualise" in params:
        _try_set(n, "visualise", bool(params["visualise"]))
    out_path = None
    if params.get("outputFile"):
        out_path = confined_path(params["outputFile"])
        _try_set(n, "outputFile", out_path)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "output": out_path, "exported": False,
            "note": "vector field wired (WIRE-ONLY); fire the .fga export yourself"}


# ── 10. volume_texture (chain; in0 volume/vdb) — slice atlas + WIRE-ONLY texture export ──────────
@endpoint("volume_texture")
def volume_texture(params):
    """SideFX Labs Volume Texture (labs::volume_texture::1.0) — flattens the incoming volume/VDB
    (`input`, input 0) into a sliced flipbook atlas for a real-time volume-texture shader; its cooked
    SOP output is the slice-preview geometry. `mode` picks the packing; `customfield` names the volume
    field; `slices`/`frameresolution` set the atlas layout; `equalizedensity`/`invertdensity` adjust
    the density. SECURITY: WIRE-ONLY — `render` is never pressed; `output_picture` is confined to the
    working dir. Returns exported=False."""
    n = child_after(params["input"], "labs::volume_texture::1.0", params.get("name"))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _VT_MODE)
    if "customfield" in params:
        _try_set(n, "customfield", _safe_token(params["customfield"]))
    if "equalizedensity" in params:
        _try_set(n, "equalizedensity", bool(params["equalizedensity"]))
    if "densityalpha" in params:
        _try_set(n, "densityalpha", bool(params["densityalpha"]))
    if "invertdensity" in params:
        _try_set(n, "invertdensity", bool(params["invertdensity"]))
    if "up_axis" in params:
        _menu_set(n, "up_axis", str(params["up_axis"]), _VT_UPAXIS)
    if "slices" in params:
        _try_set(n, "slices", int(clamp(int(params["slices"]), 1, 4096)))
    if "frameresolution" in params:
        _try_set(n, "frameresolution", int(clamp(int(params["frameresolution"]), 1, 8192)))
    if "clipping" in params:
        _try_set(n, "clipping", clamp(float(params["clipping"]), 0.0, 1e6))
    if "preview" in params:
        _try_set(n, "preview", bool(params["preview"]))
    out_path = None
    if params.get("output_picture"):
        out_path = confined_path(params["output_picture"])
        _try_set(n, "output_picture", out_path)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "output": out_path, "exported": False,
            "note": "volume texture wired (WIRE-ONLY); fire the texture export yourself"}


# ══ ROP / Driver exporters — WIRE-ONLY file-writers (built in /out, execute NEVER pressed) ═══════

# ── 11. niagara_rop (Driver) — WIRE-ONLY Niagara particle export ─────────────────────────────────
@endpoint("niagara_rop")
def niagara_rop(params):
    """SideFX Labs Niagara ROP (labs::niagara_rop) — the /out Driver form of the Niagara exporter:
    references a SOP by path (`soppath`) and writes it for Unreal's Niagara system. Built WIRE-ONLY in
    /out — `execute` is NEVER pressed. SECURITY: `soppath` is a scene node PATH (data, not a file),
    set as a plain string and never cooked here; `outputpath` is confined to the working dir. Returns
    exported=False."""
    n = _out_node("labs::niagara_rop", params.get("name"))
    if params.get("soppath"):
        _try_set(n, "soppath", str(params["soppath"]))
    if "range_mode" in params:
        _menu_set(n, "range_mode", str(params["range_mode"]), _NIAGARA_RANGE)
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    if "overwrite" in params:
        _try_set(n, "overwrite", bool(params["overwrite"]))
    out_path = None
    if params.get("outputpath"):
        out_path = confined_path(params["outputpath"])
        _try_set(n, "outputpath", out_path)
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "niagara ROP built WIRE-ONLY in /out; fire the export yourself"}


# ── 12. rbd_to_fbx (Driver) — WIRE-ONLY RBD-to-FBX export ────────────────────────────────────────
@endpoint("rbd_to_fbx")
def rbd_to_fbx(params):
    """SideFX Labs RBD to FBX (labs::rbd_to_fbx::3.0) — a /out Driver that exports a packed RBD
    simulation (referenced by `node_to_export`) as a rigid-body FBX for a game engine. Built WIRE-ONLY
    in /out — `execute` is NEVER pressed. `group` limits the export; `bOverrideName`+`sNameOverride`
    rename it; `convertaxis`/`convertunits`/`scale` handle the engine transform. SECURITY:
    `node_to_export` is a scene node PATH (data, not a file); `export_path` (FBX) is confined to the
    working dir; the rename token is sanitized. Returns exported=False."""
    n = _out_node("labs::rbd_to_fbx::3.0", params.get("name"))
    if params.get("node_to_export"):
        _try_set(n, "node_to_export", str(params["node_to_export"]))
    if "group" in params:
        _try_set(n, "group", _safe_token(params["group"]))
    if "bOverrideName" in params:
        _try_set(n, "bOverrideName", bool(params["bOverrideName"]))
    if "sNameOverride" in params:
        _try_set(n, "sNameOverride", _safe_token(params["sNameOverride"]))
    if "convertaxis" in params:
        _try_set(n, "convertaxis", bool(params["convertaxis"]))
    if "convertunits" in params:
        _try_set(n, "convertunits", bool(params["convertunits"]))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-6, 1e6))
    out_path = None
    if params.get("export_path"):
        out_path = confined_path(params["export_path"])
        _try_set(n, "export_path", out_path)
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "rbd_to_fbx built WIRE-ONLY in /out; fire the export yourself"}


# ── 13. vertex_animation_textures (Driver) — WIRE-ONLY VAT export ────────────────────────────────
@endpoint("vertex_animation_textures")
def vertex_animation_textures(params):
    """SideFX Labs Vertex Animation Textures (labs::vertex_animation_textures::3.0) — the flagship VAT
    exporter: bakes an animated SOP (referenced by `soppath`) into position/rotation/color textures +
    a base mesh for Unreal/Unity VAT shaders. Built WIRE-ONLY in /out — `execute`/`renderall` are
    NEVER pressed. `mode` = soft(0)/rigid(1)/fluid(2)/sprite(3); `engine` picks the shader target;
    `imageformat`/`depth` set the texture format; `exportlods`+`lodcount` bake LODs. SECURITY:
    `soppath` is a scene node PATH (data, not a file); `exportpath`+`assetname` are confined /
    sanitized; the pre/post-render SCRIPT parms are never exposed. Returns exported=False."""
    n = _out_node("labs::vertex_animation_textures::3.0", params.get("name"))
    if params.get("soppath"):
        _try_set(n, "soppath", str(params["soppath"]))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _VAT_MODE)
    if "engine" in params:
        _menu_set(n, "engine", str(params["engine"]), _VAT_ENGINE)
    if "imageformat" in params:
        _menu_set(n, "imageformat", str(params["imageformat"]), _VAT_IMGFMT)
    if "depth" in params:
        _menu_set(n, "depth", str(params["depth"]), _VAT_DEPTH)
    if "assetname" in params:
        _try_set(n, "assetname", _safe_token(params["assetname"]))
    if "exportlods" in params:
        _try_set(n, "exportlods", bool(params["exportlods"]))
    if "lodcount" in params:
        _try_set(n, "lodcount", int(clamp(int(params["lodcount"]), 1, 16)))
    if "padpowtwo" in params:
        _try_set(n, "padpowtwo", bool(params["padpowtwo"]))
    out_dir = None
    if params.get("exportpath"):
        out_dir = confined_path(params["exportpath"])
        _try_set(n, "exportpath", out_dir)
    return {"node": n.path(), "output": out_dir, "exported": False,
            "note": "VAT export built WIRE-ONLY in /out; fire the bake yourself"}


# ── 14. xyz_pointcloud_exporter (Driver) — WIRE-ONLY point-cloud CSV/XYZ export ──────────────────
@endpoint("xyz_pointcloud_exporter")
def xyz_pointcloud_exporter(params):
    """SideFX Labs XYZ Pointcloud Exporter (labs::xyz_pointcloud_exporter) — a /out Driver that writes
    a SOP's points (referenced by `objpath1`) to a plain-text XYZ/CSV point cloud. Built WIRE-ONLY in
    /out — `execute` is NEVER pressed. SECURITY: `objpath1` is a scene node PATH (data, not a file);
    `csv_path` is confined to the working dir. Returns exported=False."""
    n = _out_node("labs::xyz_pointcloud_exporter", params.get("name"))
    if params.get("objpath1"):
        _try_set(n, "objpath1", str(params["objpath1"]))
    out_path = None
    if params.get("csv_path"):
        out_path = confined_path(params["csv_path"])
        _try_set(n, "csv_path", out_path)
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "xyz pointcloud export built WIRE-ONLY in /out; fire the export yourself"}

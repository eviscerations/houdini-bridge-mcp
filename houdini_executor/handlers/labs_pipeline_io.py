"""SideFX Labs — Pipeline / IO (data-only handlers). Params verified against live H21.0.671 (parm name/type, ordered-
menu tokens, input/output arity, and a headless cook / wire-check per node).

Three node kinds in this lane, handled per the brief:
  * READ importers (fresh /obj generator that reads a file/cache from disk — the READ path is
      realpath-confined via confined_path()):
        fbx_archive_import, multi_file, obj_importer, regions_from_image, trace_psd_file
  * COOK ops (chain nodes that cook to geometry, no file surface / only confined texture READS):
        extract_filename, quickmaterial
  * WIRE-ONLY writers (cache / baker / exporter file-writers — built + wired + every path confined,
      every save/execute button left UNPRESSED, `loadfromdisk`/side-export toggles forced off, and
      `exported`/`rendered` returned False; the human fires the write):
        filecache, static_fracture_export, simple_baker, unreal_pivotpainter,
        zibravdb_filecache, rop_zibravdb_compress

SECURITY (data-only boundary):
  * Every file surface the tool sets is realpath-confined: fbx_archive_import.sFBXFile (READ),
    multi_file.file_# (READ), obj_importer.sObjFile/sCustomMTL (READ), regions_from_image.imginput
    (READ), trace_psd_file.file (READ), quickmaterial.*_texture_1 (READ), filecache.basedir/file
    (WRITE), simple_baker.base_path/fbx_path (WRITE), unreal_pivotpainter.outputdir (WRITE),
    zibravdb_filecache.file (WRITE), rop_zibravdb_compress.filename (WRITE).
  * No write is ever fired: filecache/zibravdb_filecache force `loadfromdisk`/`loadfromdiskonsave`
    OFF (never read a missing cache on cook) and leave the "Save to Disk" button unpressed;
    simple_baker forces its FBX side-export OFF and leaves Render unpressed; unreal_pivotpainter /
    rop_zibravdb_compress leave Export/Render unpressed. All writers return exported/rendered=False.
  * Name / attribute / container tokens (basename, container_name, asset names, material/attr names)
    are sanitized so a name token can never smuggle a filesystem path.
  * Node references (customfilesop, cop_network) are scene node PATHS (data, not files) — set as
    plain strings; the referenced node is never resolved/cooked. Code/callback parms (the *Script
    surfaces on filecache/zibravdb ROPs, material_to_override's `snippet`) are never exposed.

SKIPPED: cook_with_timeout (button-fired
TOP/cache node — outputs 0 prims in every passthrough mode headlessly; no data-only geometry
result), instant_meshes_core (SOP_InstantMeshes.dll SEGFAULTS the headless session on cook — a crash
risk to the executor), material_to_override (its only operative parm `snippet` is a VEX-style code
override — data-only leaves it inert), pick_and_place (interactive viewport-state placement tool —
placements are authored by clicking; no data-only shaping params), workitem_import (PDG work-item
importer — inert outside a TOP/PDG cook, no standalone file surface), zibravdb_decompress (READ needs
the ZibraVDB plugin+license AND a proprietary .zibravdb asset to cook — cannot verify a green cook).
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("geo", name)




def _menu_set(node, parm, token, tokens=None):
    """Set a STRING-token menu by its stored token (e.g. filecache filetype '.bgeo.sc'). Tries the raw
    token first, then falls back to the token's index in `tokens`."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        pass
    if tokens and token in tokens:
        return _try_set(node, parm, tokens.index(token))
    return False


def _menu_pick(node, parm, value, options):
    """Set an ORDERED (index-stored) menu from a friendly value: `options` lists the friendly names in
    stored-index order, so options.index(value) is the integer the menu stores. Probe-safe."""
    v = str(value)
    if v in options:
        return _try_set(node, parm, options.index(v))
    return False


def _safe_token(v):
    """Sanitize a name / attribute / container token: reject path separators, parent refs and drive
    letters so a name can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("name token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


# ── menu option tuples (friendly value in stored-index order for _menu_pick; raw tokens for _menu_set)
_INPUTMODE = ("above", "custom")            # extract_filename inputmode: 0=above File SOP / 1=custom
_FILETYPE = (".bgeo.sc", ".vdb")            # filecache filetype (STRING tokens)
_FILEMETHOD = ("constructed", "explicit")   # filecache filemethod (STRING tokens)
_EXPORTMODE = ("packed", "piece")           # static_fracture_export mExportMode: 0=packed / 1=piece
_PPVERSION = ("1.0", "2.0")                 # unreal_pivotpainter version: 0=PP1.0 / 1=PP2.0
_PPINPUTDATA = ("generate", "custom")       # unreal_pivotpainter inputData: 0=generate / 1=custom
_MATTYPE = ("principled", "matcap", "labs_pbr")  # quickmaterial materialdefinition idx 0/1/2
_RGN_INPUT = ("image", "cop")               # regions_from_image inputtype: 0=Image / 1=COP network


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  READ importers (fresh /obj generator; the READ path is confined)
# ════════════════════════════════════════════════════════════════════════════════════════════════

@endpoint("fbx_archive_import")
def fbx_archive_import(params):
    """Labs FBX Archive Import (labs::fbx_archive_import) — a fresh /obj geo that imports an FBX file
    (`file`, READ-confined) as merged Houdini geometry, optionally with materials / animation /
    bones. Fails on name collision. SECURITY: `file` is realpath-confined to the working dir; the
    FBX's internal import-path filter (`import_path`) is a plain string, not a file."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::fbx_archive_import")
    path = confined_path(params["file"])
    _try_set(n, "sFBXFile", path)
    for key, parm in (("import_materials", "bImportMaterials"), ("embedded_import", "bEmbeddedImport"),
                      ("convert_units", "bConvertUnits"), ("import_animation", "bImportAnimation"),
                      ("import_skinning", "bImportBoneSkin"), ("convert_yup", "bConvertYUp"),
                      ("unlock_geometry", "bUnlockGeo"), ("per_prim_path", "createprimstring"),
                      ("pack", "pack")):
        if key in params:
            _try_set(n, parm, bool(params[key]))
    if "import_path" in params:
        _try_set(n, "sImportPath", str(params["import_path"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "file": path,
            "points": len(g.points()), "prims": len(g.prims())}


@endpoint("multi_file")
def multi_file(params):
    """Labs Multi File (labs::multi_file) — a fresh /obj geo that imports up to eight geometry files
    at once (`file1`..`file8`, each READ-confined) and merges them, optionally stamping a `name`
    attribute from each filename. `file1` is required. Fails on name collision. SECURITY: every file
    path is realpath-confined to the working dir."""
    slots = [params[k] for k in ("file1", "file2", "file3", "file4",
                                 "file5", "file6", "file7", "file8") if params.get(k)]
    if not slots:
        raise ValueError("at least file1 is required")
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::multi_file")
    confined = [confined_path(f) for f in slots]
    _try_set(n, "filecount", len(confined))
    for i, cf in enumerate(confined, start=1):
        _try_set(n, "file_%d" % i, cf)
    if "name_from_filename" in params:
        _try_set(n, "set_name_attribute_from_filename", bool(params["name_from_filename"]))
    if "output_source_path" in params:
        _try_set(n, "bOutputSourcePath", bool(params["output_source_path"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "files": confined,
            "points": len(g.points()), "prims": len(g.prims())}


@endpoint("obj_importer")
def obj_importer(params):
    """Labs OBJ Importer (labs::obj_importer) — a fresh /obj geo that imports a Wavefront .obj file
    (`file`, READ-confined) with optional custom .mtl (`custom_mtl`, READ-confined). Fails on name
    collision. SECURITY: both `file` and `custom_mtl` are realpath-confined to the working dir."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::obj_importer")
    path = confined_path(params["file"])
    _try_set(n, "sObjFile", path)
    mtl = None
    if params.get("custom_mtl"):
        _try_set(n, "bCustomMTLFile", True)
        mtl = confined_path(params["custom_mtl"])
        _try_set(n, "sCustomMTL", mtl)
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "file": path, "custom_mtl": mtl,
            "points": len(g.points()), "prims": len(g.prims())}


@endpoint("regions_from_image")
def regions_from_image(params):
    """Labs Regions From Image (labs::regions_from_image::1.1) — a fresh /obj geo that reads an image
    (`image`, READ-confined) and generates color-quantized region geometry (`num_colors` regions,
    `smoothing` softens boundaries). `input_type` selects an image file vs a COP network node
    (`cop_network`, a scene node path). Fails on name collision. SECURITY: `image` is realpath-
    confined; `cop_network` is a scene node path (data, not a file)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::regions_from_image::1.1")
    _menu_pick(n, "inputtype", params.get("input_type", "image"), _RGN_INPUT)
    img = None
    if params.get("image"):
        img = confined_path(params["image"])
        _try_set(n, "imginput", img)
    if params.get("cop_network"):
        _try_set(n, "copinput", str(params["cop_network"]))
    if "num_colors" in params:
        _try_set(n, "numcolors", int(clamp(int(params["num_colors"]), 1, 256)))
    if "smoothing" in params:
        _try_set(n, "strength", clamp(float(params["smoothing"]), 0.0, 100.0))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e6))
    if "extended_influence" in params:
        _try_set(n, "extweight", clamp(float(params["extended_influence"]), 0.0, 100.0))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 500)))
    if "add_index" in params:
        _try_set(n, "addindex", bool(params["add_index"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "image": img,
            "points": len(g.points()), "prims": len(g.prims())}


@endpoint("trace_psd_file")
def trace_psd_file(params):
    """Labs Trace PSD File (labs::trace_psd_file::3.0) — a fresh /obj geo that reads a layered image
    (`file`, READ-confined; PSD or a flat image) and traces its layers into 2D polygon outlines.
    Fails on name collision. SECURITY: `file` is realpath-confined to the working dir."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::trace_psd_file::3.0")
    path = confined_path(params["file"])
    _try_set(n, "file", path)
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "file": path,
            "points": len(g.points()), "prims": len(g.prims())}


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  COOK ops (chain nodes; no file WRITE surface, only confined texture READS on quickmaterial)
# ════════════════════════════════════════════════════════════════════════════════════════════════

@endpoint("extract_filename")
def extract_filename(params):
    """Labs Extract Filename (labs::extract_filename) — reads the file path off an upstream File SOP
    (`input`, or `custom_file_sop` when `input_mode`=1) and writes its parts to detail string
    attributes (full path / file path / filename / directory). A pipeline data node — it parses a
    string, it does not touch disk. SECURITY: `custom_file_sop` is a scene node path (data, not a
    file); the output attribute names are sanitized."""
    n = child_after(params["input"], "labs::extract_filename", params.get("name"))
    _menu_pick(n, "inputmode", params.get("input_mode", "above"), _INPUTMODE)
    if params.get("custom_file_sop"):
        _try_set(n, "customfilesop", str(params["custom_file_sop"]))
    for key, parm in (("fullpath_attr", "fullpath_attribute"), ("filepath_attr", "filepath_attribute"),
                      ("filename_attr", "filename_attribute"), ("filedir_attr", "filedir_attribute")):
        if key in params:
            _try_set(n, parm, _safe_token(params[key]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


@endpoint("quickmaterial")
def quickmaterial(params):
    """Labs Quick Material (labs::quickmaterial::2.2) — assigns ONE material (Principled / MatCap /
    Labs PBR) to the input geometry (`input`), optionally to a primitive `group`, driven by texture
    maps (`*_texture`, READ-confined) and scalar levers (roughness / metallic / ior). Builds the
    shader network internally and stamps shop_materialpath. SECURITY: every texture path is realpath-
    confined to the working dir; `material_name` / `group` tokens are sanitized."""
    n = child_after(params["input"], "labs::quickmaterial::2.2", params.get("name"))
    _try_set(n, "mMaterialEntries", 1)  # ensure the first material entry exists
    _menu_pick(n, "materialdefinition_1", params.get("material_type", "principled"), _MATTYPE)
    if "material_name" in params:
        _try_set(n, "materialname_1", _safe_token(params["material_name"]))
    if "group" in params:
        _try_set(n, "groupselection_1", _safe_token(params["group"]))
    if "use_mikkt" in params:
        _try_set(n, "usemikkt", bool(params["use_mikkt"]))
    tex = {"basecolor_texture": "principledshader_basecolor_texture_1",
           "normal_texture": "principledshader_baseNormal_texture_1",
           "roughness_texture": "principledshader_rough_texture_1",
           "metallic_texture": "principledshader_metallic_texture_1",
           "occlusion_texture": "principledshader_occlusion_texture_1",
           "opacity_texture": "principledshader_opaccolor_texture_1"}
    set_tex = {}
    for key, parm in tex.items():
        if params.get(key):
            cp = confined_path(params[key])
            _try_set(n, parm, cp)
            set_tex[key] = cp
    if "roughness" in params:
        _try_set(n, "principledshader_rough_1", clamp(float(params["roughness"]), 0.0, 1.0))
    if "metallic" in params:
        _try_set(n, "principledshader_metallic_1", clamp(float(params["metallic"]), 0.0, 1.0))
    if "ior" in params:
        _try_set(n, "principledshader_ior_1", clamp(float(params["ior"]), 1.0, 4.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "textures": set_tex}


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  WIRE-ONLY writers (built + wired + path-confined; the save/render is NEVER fired here)
# ════════════════════════════════════════════════════════════════════════════════════════════════

@endpoint("filecache")
def filecache(params):
    """Labs File Cache (labs::filecache::2.0) — WIRE-ONLY geometry cache. Wires the input, sets the
    cache target (`basedir` + `basename` + `filetype`, or an explicit `file`) and the version, but
    NEVER presses "Save to Disk" — the human fires the write. `loadfromdisk` is forced OFF so a cook
    just passes the input geometry through (never reads a missing cache). Returns exported=false.
    SECURITY: `basedir` / `file` are realpath-confined to the working dir; `basename` is sanitized;
    the Pre/Post-Render SCRIPT surfaces are never exposed."""
    n = child_after(params["input"], "labs::filecache::2.0", params.get("name"))
    _try_set(n, "loadfromdisk", False)          # SECURITY: never read a cache on cook
    _try_set(n, "loadfromdiskonsave", False)    # SECURITY: never auto-load after a (human) save
    if "basename" in params:
        _try_set(n, "basename", _safe_token(params["basename"]))
    if "filetype" in params:
        _menu_set(n, "filetype", str(params["filetype"]), _FILETYPE)
    if "version" in params:
        _try_set(n, "enableversion", True)
        _try_set(n, "version", int(clamp(int(params["version"]), 0, 1_000_000)))
    basedir = None
    if params.get("basedir"):
        basedir = confined_path(params["basedir"])
        _try_set(n, "basedir", basedir)
    file_out = None
    if params.get("file"):
        _menu_set(n, "filemethod", "explicit", _FILEMETHOD)
        file_out = confined_path(params["file"])
        _try_set(n, "file", file_out)
    g = n.geometry()  # passthrough (loadfromdisk OFF) — proves the wiring
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "basedir": basedir, "file": file_out, "exported": False,
            "note": "filecache wired (WIRE-ONLY); press Save to Disk yourself to write the cache"}


@endpoint("static_fracture_export")
def static_fracture_export(params):
    """Labs Static Fracture Export (labs::static_fracture_export) — WIRE-ONLY exporter for the pieces
    of a fractured object (`input`). Wires + configures the container name / export mode / frame, but
    NEVER presses "Static Export" (the write into a packed container is fired by the human). A cook
    passes the fracture geometry through. Returns exported=false. SECURITY: no file-path surface is
    exposed (the export target is constructed internally); `container_name` / `piece_attribute`
    tokens are sanitized; auto-delete-if-exists is forced OFF."""
    n = child_after(params["input"], "labs::static_fracture_export", params.get("name"))
    _try_set(n, "delete_before_export", False)  # SECURITY: never auto-delete an existing container
    if "frame" in params:
        _try_set(n, "iFrame", int(clamp(int(params["frame"]), -1_000_000, 1_000_000)))
    if "container_name" in params:
        _try_set(n, "sContainerName", _safe_token(params["container_name"]))
    if "export_mode" in params:
        _menu_pick(n, "mExportMode", params["export_mode"], _EXPORTMODE)
    if "piece_attribute" in params:
        _try_set(n, "sPieceAttribute", _safe_token(params["piece_attribute"]))
    g = n.geometry()  # passthrough fracture geometry — proves the wiring
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "exported": False,
            "note": "static_fracture_export wired (WIRE-ONLY); press Static Export yourself"}


@endpoint("simple_baker")
def simple_baker(params):
    """Labs Simple Baker (labs::simple_baker::2.0) — WIRE-ONLY map baker. `input` (input 0) = the low
    /target mesh, `high` (input 1) = the high-res source. Mirrors maps_baker: the graph is BUILT +
    configured (channels, resolution, samples, confined `base_path`) but the bake is NEVER executed
    — baking is a render, so the human fires it. Returns rendered=false. SECURITY: `base_path`
    (image output) and `fbx_path` are realpath-confined; the FBX side-export (`export_fbx`) is
    forced OFF; `resolution` / `samples` are hard-clamped (render-cost)."""
    n = child_after(params["input"], "labs::simple_baker::2.0", params.get("name"))
    if params.get("high"):
        bridge_input(n, params["high"], index=1, name_hint="high")
    _try_set(n, "export_fbx", False)  # SECURITY: never fire the FBX side-export
    base_path = None
    if params.get("base_path"):
        base_path = confined_path(params["base_path"])
        _try_set(n, "base_path", base_path)
    fbx_path = None
    if params.get("fbx_path"):
        fbx_path = confined_path(params["fbx_path"])
        _try_set(n, "fbx_path", fbx_path)
    if "resolution" in params:
        _try_set(n, "vm_uvunwrapres", int(clamp(int(params["resolution"]), 16, 8192)))
    if "samples" in params:
        _try_set(n, "baking_samples", int(clamp(int(params["samples"]), 1, 4096)))
    if "border_padding" in params:
        _try_set(n, "border_padding", int(clamp(int(params["border_padding"]), 0, 512)))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e6))
    for key, parm in (("bake_basecolor", "bake_basecolor"), ("bake_normal", "bake_Nt"),
                      ("bake_opacity", "bake_alpha"), ("bake_roughness", "bake_specrough"),
                      ("bake_metallic", "bake_metallic"), ("bake_world_normal", "bake_N"),
                      ("bake_occlusion", "bake_Oc"), ("bake_curvature", "bake_Cu"),
                      ("bake_thickness", "bake_Th"), ("bake_position", "bake_P"),
                      ("bake_height", "bake_Ds")):
        if key in params:
            _try_set(n, parm, bool(params[key]))
    # WIRE-ONLY: do NOT cook / render (mirror maps_baker).
    return {"node": n.path(), "base_path": base_path, "fbx_path": fbx_path, "rendered": False,
            "note": "simple_baker graph wired (WIRE-ONLY); start the bake yourself"}


@endpoint("unreal_pivotpainter")
def unreal_pivotpainter(params):
    """Labs Unreal Pivot Painter (labs::unreal_pivotpainter::1.1) — WIRE-ONLY exporter that bakes
    pivot / hierarchy textures for UE4/5 wind animation. `input` (input 0) = the geometry;
    `pivots` (input 1) = an optional custom Pivots point cloud (else pivots are generated). Wires +
    configures mode / asset name / confined `outputdir` but NEVER presses "Export" — the write is
    fired by the human. Returns exported=false. SECURITY: `outputdir` is realpath-confined;
    `asset_name` is sanitized."""
    n = child_after(params["input"], "labs::unreal_pivotpainter::1.1", params.get("name"))
    if params.get("pivots"):
        bridge_input(n, params["pivots"], index=1, name_hint="pivots")
    _menu_pick(n, "version", params.get("mode", "1.0"), _PPVERSION)
    _menu_pick(n, "inputData", params.get("input_data", "generate"), _PPINPUTDATA)
    if "asset_name" in params:
        _try_set(n, "assetname", _safe_token(params["asset_name"]))
    outputdir = None
    if params.get("outputdir"):
        outputdir = confined_path(params["outputdir"])
        _try_set(n, "outputdir", outputdir)
    if "account_for_ue_fbx" in params:
        _try_set(n, "accountforcex", bool(params["account_for_ue_fbx"]))
    if "restore_input_scale" in params:
        _try_set(n, "restoreinputscale", bool(params["restore_input_scale"]))
    if "layout_lightmap_uvs" in params:
        _try_set(n, "bLayoutLightmap", bool(params["layout_lightmap_uvs"]))
    if "uv_padding" in params:
        _try_set(n, "uvpadding", int(clamp(int(params["uv_padding"]), 0, 256)))
    # WIRE-ONLY: never press Export.
    return {"node": n.path(), "outputdir": outputdir, "exported": False,
            "note": "unreal_pivotpainter wired (WIRE-ONLY); press Export yourself"}


@endpoint("zibravdb_filecache")
def zibravdb_filecache(params):
    """Labs ZibraVDB File Cache (labs::zibravdb_filecache::1.0) — WIRE-ONLY compressed-VDB cache.
    Wires the input volumes and sets the confined output `file` + `quality`, but NEVER presses
    "Render to Disk" (the compression run needs the ZibraVDB plugin + a license — the human fires
    it). `loadfromdisk` is forced OFF. Returns exported=false. SECURITY: `file` is realpath-confined;
    the Pre/Post-Render SCRIPT surfaces are never exposed. NOTE: running this requires the ZibraVDB
    plugin and a valid license."""
    n = child_after(params["input"], "labs::zibravdb_filecache::1.0", params.get("name"))
    _try_set(n, "loadfromdisk", False)  # SECURITY: never read a cache on cook
    file_out = None
    if params.get("file"):
        file_out = confined_path(params["file"])
        _try_set(n, "file", file_out)
    if "quality" in params:
        _try_set(n, "quality", clamp(float(params["quality"]), 0.0, 1.0))
    # WIRE-ONLY: never press Render to Disk.
    return {"node": n.path(), "file": file_out, "exported": False,
            "note": "zibravdb_filecache wired (WIRE-ONLY); requires the ZibraVDB plugin+license — "
                    "press Render to Disk yourself"}


@endpoint("rop_zibravdb_compress")
def rop_zibravdb_compress(params):
    """Labs ROP ZibraVDB Compress (labs::rop_zibravdb_compress::1.0) — WIRE-ONLY compressed-VDB ROP.
    Wires the input OpenVDB and sets the confined output `filename` + `quality`, but NEVER presses
    "Render to Disk" (the compression run needs the ZibraVDB plugin + a license). A terminal writer
    (no geometry output). Returns exported=false. SECURITY: `filename` is realpath-confined; the
    Pre/Post-Render SCRIPT surfaces are never exposed. NOTE: running this requires the ZibraVDB
    plugin and a valid license."""
    n = child_after(params["input"], "labs::rop_zibravdb_compress::1.0", params.get("name"))
    file_out = None
    if params.get("filename"):
        file_out = confined_path(params["filename"])
        _try_set(n, "filename", file_out)
    if "quality" in params:
        _try_set(n, "quality", clamp(float(params["quality"]), 0.0, 1.0))
    # WIRE-ONLY: never press Render to Disk.
    return {"node": n.path(), "filename": file_out, "exported": False,
            "note": "rop_zibravdb_compress wired (WIRE-ONLY); requires the ZibraVDB plugin+license — "
                    "press Render to Disk yourself"}

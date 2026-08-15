"""KineFX Retarget + mocap/character FILE-I/O — data-only handlers (security-critical). Params
verified against live H21.0.671; every endpoint proven with a
headless cook / wire-proof (sample assets are produced into
the confined working dir by the harness, then imported / exported round-trip).

Archetypes (mirror the Labs A/B/C mapping):
  A source (IMPORTERS): the fbx/gltf/usd/mocap/clip importers + retarget_biped_fbx are 0-input SOURCE
              nodes that READ a real asset off disk and emit KineFX geometry. Built in a fresh /obj geo
              (or after an optional skeleton input for clip_import); their file-read parms are routed
              through confined_path() so a read can never escape the working dir. clip_import also
              accepts an optional input0 skeleton to retarget the clip onto.
  B assembler: character_io — a 3-input character assembler (in0 rest geo, in1 capture pose, in2 animated
              pose). Runs data-only (loadfromdisk default OFF = construct from inputs); its cache
              file/basedir surfaces are confined; the TOP `execute`/`cookoutputnode` write buttons and
              the pre/post-write CALLBACK parms are NEVER pressed or set.
  C WIRE-ONLY (EXPORTERS/ROPs): fbx_anim_export, fbx_character_export, gltf_character_export, clip_export,
              scene_character_export, retarget_fbx_export. Built + wired + the output path confined, but
              NEVER executed (mirrors tree.py maps_baker: an export is a render — the human fires it).
              `execute`/`renderdialog`/bake buttons are never pressed; every t*/pre*/post* callback parm
              is left default (and defensively forced OFF); returns exported=False.

SECURITY (data-only, the whole differentiator — this is the file-I/O lane):
  * EVERY file/path parm (import READ paths AND export WRITE paths) is routed through confined_path():
    fbx/gltf/usd/bvh/asf/amc/trc reads, characterio file/basedir, and outputfilepath/filepath/chopoutput
    writes. An in-workingdir path is accepted (parm set to the confined realpath); an out-of-tree path
    raises PermissionError (proven both directions).
  * NO code/callback parm is ever set or exposed: the ROP pre/post-frame/render script parms
    (prerender/preframe/postframe/postrender + their t*/l* toggles/inline-strings), characterio's
    scriptsfolder/descriptivelabel, and scenecharacterexport's `log` are left at default and never
    surfaced.
  * Exporters/ROPs are WIRE-ONLY: no .render()/.execute()/cook-to-write is ever called; a fresh
    endpoint leaves no file on disk (asserted by the confinement tests).
  * mocapstream is SKIPPED (a live network-device stream: no data-only cookable surface); motionclipcreate
    is SKIPPED (already wrapped as motion_clip_create).
"""

import os
import hou
from houdini_executor.server import clamp, child_after, bridge_input, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────




def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("geo", name)


def _cooked(n):
    g = n.geometry()
    if g is None:  # a failed / errored cook yields no geometry — report structured, don't crash
        return {"node": n.path(), "points": 0, "prims": 0}
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


def _source_result(geo, n):
    """Cook + report a 0-input importer node built inside a fresh /obj geo. A failed load (missing/
    unreadable asset) yields no geometry on the display output — report points=0 rather than crash, so
    the caller sees the node's own error instead of a Python exception."""
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    pts = len(g.points()) if g is not None else 0
    prims = len(g.prims()) if g is not None else 0
    return {"node": geo.path(), "sop": n.path(), "points": pts, "prims": prims}


def _confine_file(n, parm, value):
    """Route a file/path parm through confined_path() and set it. Returns the confined realpath."""
    resolved = confined_path(str(value))
    _try_set(n, parm, resolved)
    return resolved


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_TIMESHIFT = ("bytime", "byframe")
_ANIM_REST = ("animation", "rest")
_ANIM_BIND_REST = ("animation", "bind", "rest")
_USDSOURCE = ("lop", "file")
_MOCAP_FILETYPE = ("acclaim", "biovision", "motanal")
_CLIP_MODE = ("p_transform", "trs")
_CLIP_RATEOPTION = ("nochange", "override", "resample")
_RTB_ANIMATED = ("frame1", "animated", "rest")
_RTB_IGNORESKIN = ("on", "ignoreskin")
_CIO_FILEMETHOD = ("constructed", "explicit")
_CIO_STORAGE = ("none", "static")
_CIO_ANIM_STORAGE = ("none", "static", "motionclip")
_CLIPRANGEMODE = ("useattrib", "off", "normal", "on")
_SKINMETHOD = ("linear", "dualquat", "blenddualquat")
_OUTPUTUNIT = ("cm", "m")
_GLTF_EXPORTTYPE = ("auto", "gltf", "glb")
_GLTF_IMAGEFORMAT = ("originalpng", "originaljpg", "png", "jpeg")
_GLTF_MAXRES = ("0", "256", "512", "1024", "2048", "4096")
_CLIPEXPORT_RANGE = ("full", "frame", "user")
_CLIPEXPORT_UNITS = ("frames", "samples", "seconds")
_SCE_RANGE = ("clipinfo", "full", "frame", "user")

# ROP pre/post-frame/render CALLBACK parms — NEVER set or exposed; defensively forced OFF (their t*
# toggle gates the l*/string script). Kept here so the wire-only helper can hard-disable them.
_ROP_CALLBACK_TOGGLES = ("tprerender", "tpreframe", "tpostframe", "tpostrender")


def _kill_rop_callbacks(n):
    """SECURITY: defensively force every ROP pre/post-frame/render callback toggle OFF (they gate the
    hscript/python script parms). We never set the script strings — this only ensures nothing a prior
    state left armed can fire when the human later renders."""
    for tog in _ROP_CALLBACK_TOGGLES:
        _try_set(n, tog, False)


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# IMPORTERS (A source — read a real asset, confined) ──────────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════════════════════════

# ── 1. fbx_character_import (kinefx::fbxcharacterimport) ──────────────────────────────────────────
@endpoint("fbx_character_import")
def fbx_character_import(params):
    """KineFX FBX Character Import (kinefx::fbxcharacterimport) — imports a full FBX character (skeleton
    on output 0, skin on output 1, blendshapes on output 2), optionally merging animation from a second
    FBX. Built in a fresh /obj geo. SECURITY: `fbx_file` and `anim_fbx_file` are confined_path()-routed
    reads; no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::fbxcharacterimport")
    _confine_file(n, "fbxfile", params["fbx_file"])
    if params.get("anim_fbx_file"):
        _confine_file(n, "animfbxfile", params["anim_fbx_file"])
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "set_new_clip_name" in params:
        _try_set(n, "setnewclipname", bool(params["set_new_clip_name"]))
    if "new_clip_name" in params:
        _try_set(n, "newclipname", str(params["new_clip_name"]))
    if "convert_axis" in params:
        _try_set(n, "convertaxis", bool(params["convert_axis"]))
    if "convert_units" in params:
        _try_set(n, "convertunits", bool(params["convert_units"]))
    if "normalize_joint_scales" in params:
        _try_set(n, "normalizejointscales", bool(params["normalize_joint_scales"]))
    if "import_invisible_shapes" in params:
        _try_set(n, "importinvisibleshapes", bool(params["import_invisible_shapes"]))
    if "import_userdef_attrib" in params:
        _try_set(n, "importuserdefattrib", bool(params["import_userdef_attrib"]))
    if "compute_mikkt_tangents" in params:
        _try_set(n, "computemikkttangents", bool(params["compute_mikkt_tangents"]))
    if "remove_namespaces" in params:
        _try_set(n, "removenamespaces", bool(params["remove_namespaces"]))
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e4))
    return _source_result(geo, n)


# ── 2. fbx_anim_import (kinefx::fbxanimimport) ────────────────────────────────────────────────────
@endpoint("fbx_anim_import")
def fbx_anim_import(params):
    """KineFX FBX Animation Import (kinefx::fbxanimimport) — imports an animated skeleton (a motion clip)
    from an FBX file into a fresh /obj geo. SECURITY: `fbx_file` is a confined_path()-routed read; no
    code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::fbxanimimport")
    _confine_file(n, "fbxfile", params["fbx_file"])
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "set_new_clip_name" in params:
        _try_set(n, "setnewclipname", bool(params["set_new_clip_name"]))
    if "new_clip_name" in params:
        _try_set(n, "newclipname", str(params["new_clip_name"]))
    if "root_node" in params:
        _try_set(n, "rootnode", str(params["root_node"]))
    if "convert_axis" in params:
        _try_set(n, "convertaxis", bool(params["convert_axis"]))
    if "convert_units" in params:
        _try_set(n, "convertunits", bool(params["convert_units"]))
    if "normalize_joint_scales" in params:
        _try_set(n, "normalizejointscales", bool(params["normalize_joint_scales"]))
    if "import_userdef_attrib" in params:
        _try_set(n, "importuserdefattrib", bool(params["import_userdef_attrib"]))
    if "remove_namespaces" in params:
        _try_set(n, "removenamespaces", bool(params["remove_namespaces"]))
    if "output" in params:
        _menu_set(n, "output", str(params["output"]), _ANIM_REST)
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e4))
    return _source_result(geo, n)


# ── 3. fbx_skin_import (kinefx::fbxskinimport) ────────────────────────────────────────────────────
@endpoint("fbx_skin_import")
def fbx_skin_import(params):
    """KineFX FBX Skin Import (kinefx::fbxskinimport) — imports the skinned mesh (carrying `boneCapture`
    weights) from an FBX character into a fresh /obj geo. SECURITY: `fbx_file` is a confined_path()-routed
    read; the `material` node reference is left default; no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::fbxskinimport")
    _confine_file(n, "fbxfile", params["fbx_file"])
    if "skin_geo" in params:
        _try_set(n, "skingeo", str(params["skin_geo"]))
    if "shape_attrib" in params:
        _try_set(n, "shapeattrib", str(params["shape_attrib"]))
    if "convert_axis" in params:
        _try_set(n, "convertaxis", bool(params["convert_axis"]))
    if "convert_units" in params:
        _try_set(n, "convertunits", bool(params["convert_units"]))
    if "normalize_joint_scales" in params:
        _try_set(n, "normalizejointscales", bool(params["normalize_joint_scales"]))
    if "import_invisible_shapes" in params:
        _try_set(n, "importinvisibleshapes", bool(params["import_invisible_shapes"]))
    if "compute_mikkt_tangents" in params:
        _try_set(n, "computemikkttangents", bool(params["compute_mikkt_tangents"]))
    if "remove_namespaces" in params:
        _try_set(n, "removenamespaces", bool(params["remove_namespaces"]))
    return _source_result(geo, n)


# ── 4. gltf_character_import (kinefx::gltfcharacterimport) ────────────────────────────────────────
@endpoint("gltf_character_import")
def gltf_character_import(params):
    """KineFX glTF Character Import (kinefx::gltfcharacterimport) — imports a full glTF/glb character
    (skeleton output 0, skin output 1, blendshapes output 2) into a fresh /obj geo. SECURITY: `gltf_file`
    is a confined_path()-routed read; no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::gltfcharacterimport")
    _confine_file(n, "gltffile", params["gltf_file"])
    if "node_id" in params:
        _try_set(n, "nodeid", int(clamp(int(params["node_id"]), -1, 1000000)))
    if "anim_id" in params:
        _try_set(n, "animid", int(clamp(int(params["anim_id"]), -1, 1000000)))
    if "promote_point_attribs" in params:
        _try_set(n, "promotepointattribs", bool(params["promote_point_attribs"]))
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e4))
    return _source_result(geo, n)


# ── 5. gltf_anim_import (kinefx::gltfanimimport) ──────────────────────────────────────────────────
@endpoint("gltf_anim_import")
def gltf_anim_import(params):
    """KineFX glTF Animation Import (kinefx::gltfanimimport) — imports an animated skeleton (motion clip)
    from a glTF/glb file into a fresh /obj geo. SECURITY: `gltf_file` is a confined_path()-routed read;
    no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::gltfanimimport")
    _confine_file(n, "gltffile", params["gltf_file"])
    if "anim_id" in params:
        _try_set(n, "animid", int(clamp(int(params["anim_id"]), -1, 1000000)))
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e4))
    return _source_result(geo, n)


# ── 6. gltf_skin_import (kinefx::gltfskinimport) ──────────────────────────────────────────────────
@endpoint("gltf_skin_import")
def gltf_skin_import(params):
    """KineFX glTF Skin Import (kinefx::gltfskinimport) — imports the skinned mesh (carrying `boneCapture`
    weights) from a glTF/glb character into a fresh /obj geo. SECURITY: `gltf_file` is a
    confined_path()-routed read; the `materialnode` reference is left default; no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::gltfskinimport")
    _confine_file(n, "gltffile", params["gltf_file"])
    if "node_id" in params:
        _try_set(n, "nodeid", int(clamp(int(params["node_id"]), -1, 1000000)))
    if "promote_point_attribs" in params:
        _try_set(n, "promotepointattribs", bool(params["promote_point_attribs"]))
    return _source_result(geo, n)


# ── 7. usd_character_import (kinefx::usdcharacterimport) ──────────────────────────────────────────
@endpoint("usd_character_import")
def usd_character_import(params):
    """KineFX USD Character Import (kinefx::usdcharacterimport) — imports a USDSkel character (skeleton
    output 0, skin output 1, blendshapes output 2) from a USD file into a fresh /obj geo. Forces the
    file source (not a /stage LOP). SECURITY: `usd_file` is a confined_path()-routed read; no code
    surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::usdcharacterimport")
    _menu_set(n, "usdsource", "file", _USDSOURCE)
    _confine_file(n, "usdfile", params["usd_file"])
    if "skel_root_path" in params:
        _try_set(n, "skelrootpath", str(params["skel_root_path"]))
    if "purpose" in params:
        _try_set(n, "purpose", str(params["purpose"]))
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e4))
    return _source_result(geo, n)


# ── 8. usd_anim_import (kinefx::usdanimimport) ────────────────────────────────────────────────────
@endpoint("usd_anim_import")
def usd_anim_import(params):
    """KineFX USD Animation Import (kinefx::usdanimimport) — imports an animated skeleton (motion clip)
    from a USDSkel file into a fresh /obj geo. Forces the file source. SECURITY: `usd_file` is a
    confined_path()-routed read; no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::usdanimimport")
    _menu_set(n, "usdsource", "file", _USDSOURCE)
    _confine_file(n, "usdfile", params["usd_file"])
    if "skel_root_path" in params:
        _try_set(n, "skelrootpath", str(params["skel_root_path"]))
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "output" in params:
        _menu_set(n, "output", str(params["output"]), _ANIM_BIND_REST)
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e4))
    return _source_result(geo, n)


# ── 9. usd_skin_import (kinefx::usdskinimport) ────────────────────────────────────────────────────
@endpoint("usd_skin_import")
def usd_skin_import(params):
    """KineFX USD Skin Import (kinefx::usdskinimport) — imports the skinned mesh (carrying `boneCapture`
    weights) from a USDSkel character into a fresh /obj geo. Forces the file source. SECURITY: `usd_file`
    is a confined_path()-routed read; no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::usdskinimport")
    _menu_set(n, "usdsource", "file", _USDSOURCE)
    _confine_file(n, "usdfile", params["usd_file"])
    if "skel_root_path" in params:
        _try_set(n, "skelrootpath", str(params["skel_root_path"]))
    if "purpose" in params:
        _try_set(n, "purpose", str(params["purpose"]))
    if "shape_attrib" in params:
        _try_set(n, "shapeattrib", str(params["shape_attrib"]))
    return _source_result(geo, n)


# ── 10. mocap_import (kinefx::mocapimport) ────────────────────────────────────────────────────────
@endpoint("mocap_import")
def mocap_import(params):
    """KineFX Mocap Import (kinefx::mocapimport) — imports raw motion-capture data (Biovision BVH, Acclaim
    ASF+AMC, or Motion-Analysis TRC) as an animated skeleton into a fresh /obj geo. SECURITY: every mocap
    file parm (`bvh_file`/`asf_file`/`amc_file`/`trc_file`/`trc_parent_file`) is a confined_path()-routed
    read; no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::mocapimport")
    if "file_type" in params:
        _menu_set(n, "filetype", str(params["file_type"]), _MOCAP_FILETYPE)
    for pk, pn in (("bvh_file", "bvhfile"), ("asf_file", "asffile"), ("amc_file", "amcfile"),
                   ("trc_file", "trcfile"), ("trc_parent_file", "trcparentfile")):
        if params.get(pk):
            _confine_file(n, pn, params[pk])
    if "align_axes" in params:
        _try_set(n, "alignaxes", bool(params["align_axes"]))
    if "add_leaf_nodes" in params:
        _try_set(n, "addleafnodes", bool(params["add_leaf_nodes"]))
    if "import_all_nodes" in params:
        _try_set(n, "importallnodes", bool(params["import_all_nodes"]))
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "root_node" in params:
        _try_set(n, "rootnode", str(params["root_node"]))
    if "use_fk" in params:
        _try_set(n, "usefk", bool(params["use_fk"]))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-6, 1e6))
    if "use_framerate" in params:
        _try_set(n, "useframerate", bool(params["use_framerate"]))
    if "framerate" in params:
        _try_set(n, "framerate", clamp(float(params["framerate"]), 1e-3, 1e4))
    if "output" in params:
        _menu_set(n, "output", str(params["output"]), _ANIM_REST)
    if "timeshift_method" in params:
        _menu_set(n, "timeshiftmethod", str(params["timeshift_method"]), _TIMESHIFT)
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "frame" in params:
        _try_set(n, "frame", clamp(float(params["frame"]), -1e6, 1e6))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1e4))
    return _source_result(geo, n)


# ── 11. clip_import (kinefx::clipimport) — optional input0 skeleton ───────────────────────────────
@endpoint("clip_import")
def clip_import(params):
    """KineFX Clip Import (kinefx::clipimport) — reads a `.bclip`/`.clip` CHOP motion clip off disk and
    (optionally, when a `skeleton` input 0 is supplied) applies it to that skeleton; otherwise emits the
    clip into a fresh /obj geo. SECURITY: `file` is a confined_path()-routed read; no code surface."""
    if params.get("skeleton"):
        n = child_after(params["skeleton"], "kinefx::clipimport", params.get("name"))
        geo = None
    else:
        geo = _fresh_geo(params["name"])
        n = geo.createNode("kinefx::clipimport")
    _confine_file(n, "file", params["file"])
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _CLIP_MODE)
    if "rate_option" in params:
        _menu_set(n, "rateoption", str(params["rate_option"]), _CLIP_RATEOPTION)
    if "rate" in params:
        _try_set(n, "rate", clamp(float(params["rate"]), 1e-3, 1e4))
    if "interpolate" in params:
        _try_set(n, "interpolate", bool(params["interpolate"]))
    if geo is not None:
        return _source_result(geo, n)
    return _cooked(n)


# ── 12. retarget_biped_fbx (kinefx::retargetbipedfbx) ─────────────────────────────────────────────
@endpoint("retarget_biped_fbx")
def retarget_biped_fbx(params):
    """KineFX Retarget Biped FBX (kinefx::retargetbipedfbx) — imports a biped FBX and retargets its
    animation onto the KineFX biped template (skeleton output 0, anim output 1, skin output 2) in a fresh
    /obj geo. SECURITY: `fbx_file` and `fbx_skin_file` are confined_path()-routed reads; the mapping/skin
    SOP-path references are left default; no code surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("kinefx::retargetbipedfbx")
    _confine_file(n, "fbxfile", params["fbx_file"])
    if params.get("fbx_skin_file"):
        _confine_file(n, "fbxskinfile", params["fbx_skin_file"])
    if "animated" in params:
        _menu_set(n, "animated", str(params["animated"]), _RTB_ANIMATED)
    if "ignore_skin" in params:
        _menu_set(n, "ignoreskin", str(params["ignore_skin"]), _RTB_IGNORESKIN)
    if "rest_clip_name" in params:
        _try_set(n, "restclipname", str(params["rest_clip_name"]))
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "anim_group" in params:
        _try_set(n, "animgroup", str(params["anim_group"]))
    if "children" in params:
        _try_set(n, "children", bool(params["children"]))
    if "namespace" in params:
        _try_set(n, "ns", str(params["namespace"]))
    if "skin_geo" in params:
        _try_set(n, "skingeo", str(params["skin_geo"]))
    return _source_result(geo, n)


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ASSEMBLER (B chain — data-only character construction) ──────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════════════════════════

# ── 13. character_io (kinefx::characterio::2.0) — in0 rest geo, in1 capture pose, in2 animated pose ─
@endpoint("character_io")
def character_io(params):
    """KineFX Character IO (kinefx::characterio::2.0) — assembles a KineFX character from its parts:
    input0 = rest `geometry`, input1 = `capture_pose` skeleton (optional), input2 = `animated_pose`
    skeleton/motionclip (optional). Runs DATA-ONLY: `load_from_disk` defaults OFF (the character is
    constructed from the wired inputs and cooked to output 0), so no disk cache is touched by a normal
    cook. SECURITY: the cache `file`/`base_dir` surfaces are confined_path()-routed; the TOP
    `execute`/`cookoutputnode` write buttons are NEVER pressed; the scriptsfolder/descriptivelabel and
    pre/post-write CALLBACK parms are left default and never surfaced."""
    n = child_after(params["geometry"], "kinefx::characterio::2.0", params.get("name"))
    if params.get("capture_pose"):
        bridge_input(n, params["capture_pose"], index=1, name_hint="capture_pose")
    if params.get("animated_pose"):
        bridge_input(n, params["animated_pose"], index=2, name_hint="animated_pose")
    # DATA-ONLY: default to constructing from inputs (never auto-load/auto-write on cook).
    _try_set(n, "loadfromdisk", bool(params.get("load_from_disk", False)))
    _try_set(n, "loadfromdiskonsave", False)
    if "file_method" in params:
        _menu_set(n, "filemethod", str(params["file_method"]), _CIO_FILEMETHOD)
    if "base_name" in params:
        _try_set(n, "basename", str(params["base_name"]))
    if params.get("base_dir"):
        _confine_file(n, "basedir", params["base_dir"])
    if params.get("file"):
        _confine_file(n, "file", params["file"])
    if "version" in params:
        _try_set(n, "version", int(clamp(int(params["version"]), 1, 1000000)))
    if "rest_frame" in params:
        _try_set(n, "restframe", int(clamp(int(params["rest_frame"]), -100000, 100000)))
    if "rest_geo_storage" in params:
        _menu_set(n, "restgeo_storage", str(params["rest_geo_storage"]), _CIO_STORAGE)
    if "capture_pose_storage" in params:
        _menu_set(n, "capturepose_storage", str(params["capture_pose_storage"]), _CIO_STORAGE)
    if "animated_pose_storage" in params:
        _menu_set(n, "animatedpose_storage", str(params["animated_pose_storage"]), _CIO_ANIM_STORAGE)
    return _cooked(n)


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# EXPORTERS / ROPs (C WIRE-ONLY — build + wire + confine, NEVER execute) ──────────────────────────
# ═════════════════════════════════════════════════════════════════════════════════════════════════

# ── 14. fbx_anim_export (kinefx::rop_fbxanimoutput) — WIRE-ONLY ───────────────────────────────────
@endpoint("fbx_anim_export")
def fbx_anim_export(params):
    """KineFX FBX Animation Output (kinefx::rop_fbxanimoutput) — WIRE-ONLY. Builds + wires + confines the
    FBX motion-clip writer over the animated skeleton at `geometry` (input 0), but NEVER executes it
    (mirrors tree.py maps_baker: an export is a render — the human fires it). Returns exported=False.
    SECURITY: `output_file` is realpath-confined; the `execute`/`renderdialog` buttons are never pressed;
    every pre/post-frame/render CALLBACK parm is left default (defensively forced OFF); no write on cook."""
    n = child_after(params["geometry"], "kinefx::rop_fbxanimoutput", params.get("name"))
    _kill_rop_callbacks(n)
    out_path = confined_path(params["output_file"]) if params.get("output_file") else None
    if out_path:
        _try_set(n, "outputfilepath", out_path)
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "clip_range_mode" in params:
        _menu_set(n, "cliprangemode", str(params["clip_range_mode"]), _CLIPRANGEMODE)
    if "frame_start" in params:
        _try_set(n, "f1", clamp(float(params["frame_start"]), -1e6, 1e6))
    if "frame_end" in params:
        _try_set(n, "f2", clamp(float(params["frame_end"]), -1e6, 1e6))
    if "frame_inc" in params:
        _try_set(n, "f3", clamp(float(params["frame_inc"]), 1e-3, 1e5))
    if "use_rest_pose" in params:
        _try_set(n, "userestpose", bool(params["use_rest_pose"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "make_path" in params:
        _try_set(n, "mkpath", bool(params["make_path"]))
    if "save_binary" in params:
        _try_set(n, "savebinary", bool(params["save_binary"]))
    if "export_userdef_attrib" in params:
        _try_set(n, "exportuserdefattrib", bool(params["export_userdef_attrib"]))
    if "remove_constant_anim_curves" in params:
        _try_set(n, "removeconstantanimcurves", bool(params["remove_constant_anim_curves"]))
    if "convert_axis" in params:
        _try_set(n, "convertaxis", bool(params["convert_axis"]))
    if "output_unit" in params:
        _menu_set(n, "outputunit", str(params["output_unit"]), _OUTPUTUNIT)
    if "convert_units" in params:
        _try_set(n, "convertunits", bool(params["convert_units"]))
    if "remove_joint_scaling" in params:
        _try_set(n, "removejointscaling", bool(params["remove_joint_scaling"]))
    n.moveToGoodPosition()
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "FBX anim output wired (WIRE-ONLY); start the export yourself"}


# ── 15. fbx_character_export (kinefx::rop_fbxcharacteroutput) — WIRE-ONLY ─────────────────────────
@endpoint("fbx_character_export")
def fbx_character_export(params):
    """KineFX FBX Character Output (kinefx::rop_fbxcharacteroutput) — WIRE-ONLY. Builds + wires + confines
    the FBX character writer: input0 = `skin_geo`, input1 = `capture_pose` skeleton, input2 =
    `animated_pose` skeleton (optional). NEVER executes it (mirrors maps_baker). Returns exported=False.
    SECURITY: `output_file` is realpath-confined; `execute`/`renderdialog` are never pressed; every
    pre/post CALLBACK parm is left default (forced OFF); no write on cook."""
    n = child_after(params["skin_geo"], "kinefx::rop_fbxcharacteroutput", params.get("name"))
    bridge_input(n, params["capture_pose"], index=1, name_hint="capture_pose")
    if params.get("animated_pose"):
        bridge_input(n, params["animated_pose"], index=2, name_hint="animated_pose")
    _kill_rop_callbacks(n)
    out_path = confined_path(params["output_file"]) if params.get("output_file") else None
    if out_path:
        _try_set(n, "outputfilepath", out_path)
    if "skin_method" in params:
        _menu_set(n, "skinmethod", str(params["skin_method"]), _SKINMETHOD)
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "clip_range_mode" in params:
        _menu_set(n, "cliprangemode", str(params["clip_range_mode"]), _CLIPRANGEMODE)
    if "frame_start" in params:
        _try_set(n, "f1", clamp(float(params["frame_start"]), -1e6, 1e6))
    if "frame_end" in params:
        _try_set(n, "f2", clamp(float(params["frame_end"]), -1e6, 1e6))
    if "frame_inc" in params:
        _try_set(n, "f3", clamp(float(params["frame_inc"]), 1e-3, 1e5))
    if "use_rest_pose" in params:
        _try_set(n, "userestpose", bool(params["use_rest_pose"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "make_path" in params:
        _try_set(n, "mkpath", bool(params["make_path"]))
    if "save_binary" in params:
        _try_set(n, "savebinary", bool(params["save_binary"]))
    if "embed_media" in params:
        _try_set(n, "embedmedia", bool(params["embed_media"]))
    if "export_userdef_attrib" in params:
        _try_set(n, "exportuserdefattrib", bool(params["export_userdef_attrib"]))
    if "remove_constant_anim_curves" in params:
        _try_set(n, "removeconstantanimcurves", bool(params["remove_constant_anim_curves"]))
    if "convert_axis" in params:
        _try_set(n, "convertaxis", bool(params["convert_axis"]))
    if "output_unit" in params:
        _menu_set(n, "outputunit", str(params["output_unit"]), _OUTPUTUNIT)
    if "convert_units" in params:
        _try_set(n, "convertunits", bool(params["convert_units"]))
    if "remove_joint_scaling" in params:
        _try_set(n, "removejointscaling", bool(params["remove_joint_scaling"]))
    n.moveToGoodPosition()
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "FBX character output wired (WIRE-ONLY); start the export yourself"}


# ── 16. gltf_character_export (kinefx::rop_gltfcharacteroutput) — WIRE-ONLY ───────────────────────
@endpoint("gltf_character_export")
def gltf_character_export(params):
    """KineFX glTF Character Output (kinefx::rop_gltfcharacteroutput) — WIRE-ONLY. Builds + wires +
    confines the glTF/glb character writer: input0 = `skin_geo`, input1 = `capture_pose` skeleton,
    input2 = `animated_pose` skeleton (optional). NEVER executes it (mirrors maps_baker). Returns
    exported=False. SECURITY: `output_file` (`filepath`) is realpath-confined; the additional-texture
    read paths are never surfaced; `execute`/`renderdialog` are never pressed; pre/post CALLBACK parms
    left default (forced OFF); no write on cook."""
    n = child_after(params["skin_geo"], "kinefx::rop_gltfcharacteroutput", params.get("name"))
    bridge_input(n, params["capture_pose"], index=1, name_hint="capture_pose")
    if params.get("animated_pose"):
        bridge_input(n, params["animated_pose"], index=2, name_hint="animated_pose")
    _kill_rop_callbacks(n)
    out_path = confined_path(params["output_file"]) if params.get("output_file") else None
    if out_path:
        _try_set(n, "filepath", out_path)
    if "export_type" in params:
        _menu_set(n, "exporttype", str(params["export_type"]), _GLTF_EXPORTTYPE)
    if "make_path" in params:
        _try_set(n, "mkpath", bool(params["make_path"]))
    if "image_format" in params:
        _menu_set(n, "imageformat", str(params["image_format"]), _GLTF_IMAGEFORMAT)
    if "image_quality" in params:
        _try_set(n, "imagequality", int(clamp(int(params["image_quality"]), 0, 100)))
    if "max_resolution" in params:
        _menu_set(n, "maxresolution", str(params["max_resolution"]), _GLTF_MAXRES)
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "flip_normal_map_y" in params:
        _try_set(n, "flipnormalmapy", bool(params["flip_normal_map_y"]))
    if "export_materials" in params:
        _try_set(n, "exportmaterials", bool(params["export_materials"]))
    if "export_joint_names" in params:
        _try_set(n, "exportjointnames", bool(params["export_joint_names"]))
    if "copyright" in params:
        _try_set(n, "copyright", str(params["copyright"]))
    n.moveToGoodPosition()
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "glTF character output wired (WIRE-ONLY); start the export yourself"}


# ── 17. clip_export (kinefx::clipexport) — WIRE-ONLY ──────────────────────────────────────────────
@endpoint("clip_export")
def clip_export(params):
    """KineFX Clip Export (kinefx::clipexport) — WIRE-ONLY. Builds + wires + confines the CHOP-clip
    (`.bclip`/`.clip`) writer over the animated skeleton / motion clip at `geometry` (input 0), but NEVER
    executes it (mirrors maps_baker). Returns exported=False. SECURITY: `output_file` (`chopoutput`) is
    realpath-confined; the `execute` button is never pressed; no write on cook."""
    n = child_after(params["geometry"], "kinefx::clipexport", params.get("name"))
    out_path = confined_path(params["output_file"]) if params.get("output_file") else None
    if out_path:
        _try_set(n, "chopoutput", out_path)
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _CLIP_MODE)
    if "rate" in params:
        _try_set(n, "rate", clamp(float(params["rate"]), 1e-3, 1e4))
    if "range" in params:
        _menu_set(n, "range", str(params["range"]), _CLIPEXPORT_RANGE)
    if "units" in params:
        _menu_set(n, "units", str(params["units"]), _CLIPEXPORT_UNITS)
    if "start" in params:
        _try_set(n, "start", clamp(float(params["start"]), -1e6, 1e6))
    if "end" in params:
        _try_set(n, "end", clamp(float(params["end"]), -1e6, 1e6))
    n.moveToGoodPosition()
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "clip export wired (WIRE-ONLY); start the export yourself"}


# ── 18. scene_character_export (kinefx::scenecharacterexport) — WIRE-ONLY (scene-bake) ────────────
@endpoint("scene_character_export")
def scene_character_export(params):
    """KineFX Scene Character Export (kinefx::scenecharacterexport) — WIRE-ONLY. Builds + wires the
    character-animation baker: input0 = `geometry`, input1 = `skeleton`. It bakes animation onto scene
    nodes (no disk file surface); the bake is fired by the human `Bake Animation` button, which this
    endpoint NEVER presses. Returns exported=False. SECURITY: the `log` code parm is never set; no bake
    on cook."""
    n = child_after(params["geometry"], "kinefx::scenecharacterexport", params.get("name"))
    bridge_input(n, params["skeleton"], index=1, name_hint="skeleton")
    if "range" in params:
        _menu_set(n, "range", str(params["range"]), _SCE_RANGE)
    if "start" in params:
        _try_set(n, "start_end1", clamp(float(params["start"]), -1e6, 1e6))
    if "end" in params:
        _try_set(n, "start_end2", clamp(float(params["end"]), -1e6, 1e6))
    if "rate" in params:
        _try_set(n, "rate", clamp(float(params["rate"]), 1e-3, 1e4))
    if "hierarchy" in params:
        _try_set(n, "hierarchy", bool(params["hierarchy"]))
    if "max_frames" in params:
        _try_set(n, "maxframes", int(clamp(int(params["max_frames"]), 1, 1000000)))
    n.moveToGoodPosition()
    return {"node": n.path(), "exported": False,
            "note": "scene character export wired (WIRE-ONLY; scene-bake); start the bake yourself"}


# ── 19. retarget_fbx_export (kinefx::retargetfbxexport) — WIRE-ONLY ───────────────────────────────
@endpoint("retarget_fbx_export")
def retarget_fbx_export(params):
    """KineFX Retarget FBX Export (kinefx::retargetfbxexport) — WIRE-ONLY. Builds + wires + confines the
    retarget-and-write FBX exporter over the animated character at `geometry` (input 0), but NEVER
    executes it (mirrors maps_baker). Returns exported=False. SECURITY: `output_file` and the optional
    `input_file` are realpath-confined; the batch retarget path-pattern tokens
    (`pattern`/`outputpathsingle`/...) are left default and never surfaced; `execute`/`renderdialog` are
    never pressed; pre/post CALLBACK parms left default (forced OFF); no write on cook."""
    n = child_after(params["geometry"], "kinefx::retargetfbxexport", params.get("name"))
    _kill_rop_callbacks(n)
    out_path = confined_path(params["output_file"]) if params.get("output_file") else None
    if out_path:
        _try_set(n, "outputfilepath", out_path)
    in_path = None
    if params.get("input_file"):
        in_path = confined_path(params["input_file"])
        _try_set(n, "inputfilepath", in_path)
    if "skin_method" in params:
        _menu_set(n, "skinmethod", str(params["skin_method"]), _SKINMETHOD)
    if "clip_name" in params:
        _try_set(n, "clipname", str(params["clip_name"]))
    if "clip_range_mode" in params:
        _menu_set(n, "cliprangemode", str(params["clip_range_mode"]), _CLIPRANGEMODE)
    if "frame_start" in params:
        _try_set(n, "f1", clamp(float(params["frame_start"]), -1e6, 1e6))
    if "frame_end" in params:
        _try_set(n, "f2", clamp(float(params["frame_end"]), -1e6, 1e6))
    if "frame_inc" in params:
        _try_set(n, "f3", clamp(float(params["frame_inc"]), 1e-3, 1e5))
    if "use_rest_pose" in params:
        _try_set(n, "userestpose", bool(params["use_rest_pose"]))
    if "rest_pose_attrib" in params:
        _try_set(n, "restposeattrib", str(params["rest_pose_attrib"]))
    if "make_path" in params:
        _try_set(n, "mkpath", bool(params["make_path"]))
    if "save_binary" in params:
        _try_set(n, "savebinary", bool(params["save_binary"]))
    if "embed_media" in params:
        _try_set(n, "embedmedia", bool(params["embed_media"]))
    if "convert_axis" in params:
        _try_set(n, "convertaxis", bool(params["convert_axis"]))
    if "output_unit" in params:
        _menu_set(n, "outputunit", str(params["output_unit"]), _OUTPUTUNIT)
    if "convert_units" in params:
        _try_set(n, "convertunits", bool(params["convert_units"]))
    if "remove_joint_scaling" in params:
        _try_set(n, "removejointscaling", bool(params["remove_joint_scaling"]))
    n.moveToGoodPosition()
    return {"node": n.path(), "output": out_path, "input": in_path, "exported": False,
            "note": "retarget FBX export wired (WIRE-ONLY); start the export yourself"}

"""SideFX Labs — Computer-Vision synthetic-data + UV/Mesh/Time geometry utilities (data-only).

Params verified against live H21.0.671. Each handler exposes a
curated, safe scalar subset; ramps stay at HDA default; multiparm instance lists are left at default
(cannot be driven by a flat scalar tool); node/prim-path refs to a dome camera are left unset.

Two node families:
  * ml_cv_* — the SideFX Labs Machine Learning / Computer Vision synthetic-data toolset: import
    source assets, assign keypoint / label / texture-mask / vector metadata, promote synth
    attributes, and (WIRE-ONLY) export COCO-style JSON annotations.
  * geometry utils — visualize_uvs / udim_tile_number / export_uv_wireframe (UV inspect/bake),
    testgeometry_luiz / testgeometry_paul / houdini_icon (test-geometry sources), simple_retime (time).

SECURITY (data-only):
  * ml_cv_directory_import `dir` (a directory READ) and visualize_uvs `texturemap` (an image READ)
    are confined_path()'d ONLY when the caller supplies them; otherwise the bundled SideFX default
    is left in place.
  * ml_cv_rop_annotation_output and export_uv_wireframe are file WRITERS -> WIRE-ONLY: the graph is
    built + wired + the output path confined, the export/render Buttons are NEVER pressed, and the
    handler returns rendered=False (mirrors tree.py maps_baker). No code/callback parm is ever set.
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── local probe-safe helpers (copied per house convention) ────────────────────────────────────────
def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)






def _set_int2(node, parm, value):
    """Set a 2-tuple int parm (e.g. a square resolution) to (value, value)."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set((int(value), int(value)))
        return True
    except Exception:
        return False


def _geo_stats(n):
    """Return (points, prims) for a cooked SOP, or (None, None) if it has no geometry stream yet
    (e.g. a node whose input contract is unmet). Never raises on a None geometry()."""
    try:
        g = n.geometry()
        return len(g.points()), len(g.prims())
    except Exception:
        return None, None


def _safe_leaf(v):
    """Sanitize a filename leaf token so it can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("filename must be a bare leaf (no / \\ .. or drive): %r" % s)
    return s


# ── ordered-menu token tuples (position == the HDA's stored index) ────────────────────────────────
_LABEL_GROUPTYPE = ("guess", "vertices", "edges", "points", "prims")
_LABEL_IDTYPE = ("index", "attribute")                # tokens "0"/"1" -> index 0/1
_PROMOTE_CLASS = ("detail", "primitive", "point", "vertex")
_PROMOTE_METHOD = ("max", "min", "mean", "mode", "median", "sum",
                   "sumsquare", "rms", "first", "last", "array")
_ROP_PARTITION = ("piece", "connectivity")            # tokens "0"/"1" -> index
_ROP_CLASS = ("primitive", "point")
_ROP_GROUPTYPE = ("guess", "breakpoints", "edges", "points", "prims")
_UVWIRE_UNITS = ("image", "pixels")
_UDIM_CLASS = ("primitive", "point", "vertex")


# ══ CV synthetic-data family ══════════════════════════════════════════════════════════════════════

# ── 1. ml_cv_directory_import (source; 0 inputs) — import asset files from a directory ─────────────
@endpoint("ml_cv_directory_import")
def ml_cv_directory_import(params):
    """SideFX Labs ML CV Directory Import (labs::ml_cv_directory_import::1.0) — a SOURCE node
    (0 inputs) that imports asset geometry from a directory matching a filename pattern, the entry
    point for CV synthetic-data staging. Builds a fresh /obj geo; fails on name collision.
    SECURITY: `dir` is a directory READ — confined to the working directory ONLY when supplied;
    otherwise the bundled SideFX sample-asset default is used."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::ml_cv_directory_import::1.0")
    if params.get("dir"):
        _try_set(n, "dir", confined_path(params["dir"]))
    if "filepattern" in params:
        _try_set(n, "filepattern", str(params["filepattern"]))
    if "importnum" in params:
        _try_set(n, "importnum", int(clamp(int(params["importnum"]), 0, 1_000_000)))
    if "importall" in params:
        _try_set(n, "importall", bool(params["importall"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    # HONEST FAILURE: an empty dir / no filename-pattern match / an unsupported asset format leaves the
    # SOP with NO cooked geometry, so a raw n.geometry() would surface an opaque
    # "'NoneType' object has no attribute 'points'". Detect it via the None-safe stats helper and raise
    # an ACTIONABLE message instead (same honest-error contract as the schema-rejection family).
    pts, prims = _geo_stats(n)
    if pts is None:
        # NOTE: deliberately do NOT append n.errors() — the Labs HDA's internal cook failure is a
        # Python traceback carrying the SideFX install path (host-layout recon). The actionable,
        # non-sensitive message below is sufficient; the full node error is logged locally by the
        # server's generic handler, never forwarded (same contract as server.py's 500 path).
        geo.destroy()  # don't leave a dead node blocking a same-name retry
        raise ValueError(
            "ml_cv_directory_import produced no geometry: no files matched pattern %r in the "
            "directory, or the matched asset(s) are an unsupported format (this SOURCE node needs "
            "a directory of importable geometry files)." % str(params.get("filepattern", "*")))
    return {"node": geo.path(), "sop": n.path(), "points": pts, "prims": prims}


# ── 2. ml_cv_keypoint_metadata (chain; in0 mesh) — assign keypoint ground-truth metadata ──────────
@endpoint("ml_cv_keypoint_metadata")
def ml_cv_keypoint_metadata(params):
    """SideFX Labs ML CV Keypoint Metadata (labs::ml_cv_keypoint_metadata::1.0) — assigns keypoint
    ground-truth metadata (keypoint radius, 3D positions, skeleton connectivity) to the input geo for
    pose-estimation training data. `input` (input 0) = the labelled mesh, which MUST already carry a
    `kp_name` point attribute naming each keypoint. The per-keypoint / per-connection multiparm lists
    stay at their HDA defaults; the dome-camera LOP/prim path refs are left unset. Data-only (no file
    surface)."""
    n = child_after(params["input"], "labs::ml_cv_keypoint_metadata::1.0", params.get("name"))
    if "radx" in params:
        _try_set(n, "radx", clamp(float(params["radx"]), 1e-4, 10.0))
    if "compgt" in params:
        _try_set(n, "compgt", bool(params["compgt"]))
    if "kp3d" in params:
        _try_set(n, "kp3d", bool(params["kp3d"]))
    if "hasSkel" in params:
        _try_set(n, "hasSkel", bool(params["hasSkel"]))
    if "assignkp" in params:
        _try_set(n, "assignkp", bool(params["assignkp"]))
    if "viscolor" in params:
        _try_set(n, "viscolor", bool(params["viscolor"]))
    pts, prims = _geo_stats(n)
    return {"node": n.path(), "points": pts, "prims": prims}


# ── 3. ml_cv_label_metadata (chain; in0 mesh, in1 opt label defs) — assign category/instance IDs ──
@endpoint("ml_cv_label_metadata")
def ml_cv_label_metadata(params):
    """SideFX Labs ML CV Label Metadata (labs::ml_cv_label_metadata::1.0) — tags geometry (or a group)
    with a category ID/name + an optional instance ID for segmentation/detection training. `input`
    (input 0) = the mesh; optional `defs` (input 1) supplies label definitions. `idtype` picks
    instance ID from a running index or from a named attribute. Data-only."""
    n = child_after(params["input"], "labs::ml_cv_label_metadata::1.0", params.get("name"))
    if params.get("defs"):
        bridge_input(n, params["defs"], index=1, name_hint="defs")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "grouptype" in params:
        _menu_set(n, "grouptype", str(params["grouptype"]), _LABEL_GROUPTYPE)
    if "categoryid" in params:
        _try_set(n, "categoryid", int(params["categoryid"]))
    if "categoryname" in params:
        _try_set(n, "categoryname", str(params["categoryname"]))
    if "enableinstid" in params:
        _try_set(n, "enableinstid", bool(params["enableinstid"]))
    if "idtype" in params:
        _menu_set(n, "idtype", str(params["idtype"]), _LABEL_IDTYPE)
    if "attribute" in params:
        _try_set(n, "attribute", str(params["attribute"]))
    if "instid" in params:
        _try_set(n, "instid", int(params["instid"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. ml_cv_promote_synth_attribute (chain; in0 mesh) — promote a synth attr across classes ──────
@endpoint("ml_cv_promote_synth_attribute")
def ml_cv_promote_synth_attribute(params):
    """SideFX Labs ML CV Promote Synth Attribute (labs::ml_cv_promote_synth_attribute::1.0) — promotes
    a synthetic-data attribute from one geometry class to another (e.g. primitive -> point) with a
    chosen aggregation method, so labels land on the right elements. `input` (input 0) = the mesh.
    Data-only."""
    n = child_after(params["input"], "labs::ml_cv_promote_synth_attribute::1.0", params.get("name"))
    if "attrname" in params:
        _try_set(n, "attrname", str(params["attrname"]))
    if "attrpromote" in params:
        _try_set(n, "attrpromote", bool(params["attrpromote"]))
    if "inclass" in params:
        _menu_set(n, "inclass", str(params["inclass"]), _PROMOTE_CLASS)
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _PROMOTE_METHOD)
    if "delorig" in params:
        _try_set(n, "delorig", bool(params["delorig"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. ml_cv_rop_annotation_output (WIRE-ONLY writer; in0 mesh, in1 opt cam) — COCO JSON export ───
@endpoint("ml_cv_rop_annotation_output")
def ml_cv_rop_annotation_output(params):
    """SideFX Labs ML CV Annotation Output (labs::ml_cv_rop_annotation_output::1.0) — WIRE-ONLY writer
    that exports COCO-style JSON annotations (category/instance IDs, bounding data) for the input
    synthetic frame. `input` (input 0) = the labelled mesh; optional `cam` (input 1) = the camera.
    Mirrors maps_baker: the graph is BUILT and configured but the Export/Aggregate JSON Buttons are
    NEVER pressed (the human fires the export). Returns rendered=False.
    SECURITY: `outputpath` is realpath-confined to the working directory; `filename` is a sanitized
    bare leaf (no path separators). No code/callback parm is set."""
    n = child_after(params["input"], "labs::ml_cv_rop_annotation_output::1.0", params.get("name"))
    if params.get("cam"):
        bridge_input(n, params["cam"], index=1, name_hint="cam")
    if "partitionby" in params:
        _menu_set(n, "partitionby", str(params["partitionby"]), _ROP_PARTITION)
    if "piece_class" in params:
        _menu_set(n, "class", str(params["piece_class"]), _ROP_CLASS)
    if "pieceattr" in params:
        _try_set(n, "pieceattr", str(params["pieceattr"]))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "grouptype" in params:
        _menu_set(n, "grouptype", str(params["grouptype"]), _ROP_GROUPTYPE)
    if "removegrp" in params:
        _try_set(n, "removegrp", bool(params["removegrp"]))
    out_path = None
    if params.get("outputpath"):
        out_path = confined_path(params["outputpath"])
        _try_set(n, "outputpath", out_path)
    if "filename" in params:
        _try_set(n, "filename", _safe_leaf(params["filename"]))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "note": "ml_cv_rop_annotation_output wired (WIRE-ONLY); export the JSON yourself"}


# ── 6. ml_cv_texture_mask (chain; in0 mesh) — tag texture instance/category IDs ───────────────────
@endpoint("ml_cv_texture_mask")
def ml_cv_texture_mask(params):
    """SideFX Labs ML CV Texture Mask (labs::ml_cv_texture_mask::1.0) — assigns a texture instance ID
    and a category ID/name to the input geometry so a rendered texture region becomes a labelled mask
    in the synthetic dataset. `input` (input 0) = the mesh. Data-only."""
    n = child_after(params["input"], "labs::ml_cv_texture_mask::1.0", params.get("name"))
    if "texinstid" in params:
        _try_set(n, "texinstid", int(params["texinstid"]))
    if "categoryid" in params:
        _try_set(n, "categoryid", int(params["categoryid"]))
    if "categoryname" in params:
        _try_set(n, "categoryname", str(params["categoryname"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. ml_cv_vector_data (chain; in0 mesh, in1 opt prev) — per-point vector (e.g. motion) data ────
@endpoint("ml_cv_vector_data")
def ml_cv_vector_data(params):
    """SideFX Labs ML CV Vector Data (labs::ml_cv_vector_data::1.0) — computes per-point vector data
    (e.g. a screen-space motion/direction vector from a source point) for the synthetic frame.
    `input` (input 0) = the mesh; requires EITHER a `srcept` source-point number OR a `prev` second
    input (input 1). The dome-camera LOP/prim path refs are left unset. Data-only."""
    n = child_after(params["input"], "labs::ml_cv_vector_data::1.0", params.get("name"))
    if params.get("prev"):
        bridge_input(n, params["prev"], index=1, name_hint="prev")
    if "srcept" in params:
        _try_set(n, "srcept", str(params["srcept"]))
    if "visvector" in params:
        _try_set(n, "visvector", bool(params["visvector"]))
    if "vectorattrprefix" in params:
        _try_set(n, "vectorattrprefix", str(params["vectorattrprefix"]))
    pts, prims = _geo_stats(n)
    return {"node": n.path(), "points": pts, "prims": prims}


# ── 8. ml_cv_visualize_keypoints (chain terminus; in0 keypoint geo) — keypoint/skeleton guide geo ─
@endpoint("ml_cv_visualize_keypoints")
def ml_cv_visualize_keypoints(params):
    """SideFX Labs ML CV Visualize Keypoints (labs::ml_cv_visualize_keypoints::1.0) — builds keypoint /
    skeleton-connectivity guide geometry from keypoint-metadata geo for inspecting synthetic-data
    labels. `input` (input 0) = geo carrying keypoint metadata (a terminal display node). Data-only."""
    n = child_after(params["input"], "labs::ml_cv_visualize_keypoints::1.0", params.get("name"))
    if "viskp" in params:
        _try_set(n, "viskp", bool(params["viskp"]))
    if "visskel" in params:
        _try_set(n, "visskel", bool(params["visskel"]))
    if "jointscale" in params:
        _try_set(n, "jointscale", clamp(float(params["jointscale"]), 1e-3, 100.0))
    if "wirewidth" in params:
        _try_set(n, "wirewidth", clamp(float(params["wirewidth"]), 1e-4, 100.0))
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-4, 100.0))
    try:
        g = n.geometry()
        pts, prims = len(g.points()), len(g.prims())
    except Exception:
        pts = prims = None
    return {"node": n.path(), "points": pts, "prims": prims}


# ══ UV / Mesh / Time geometry utilities ═══════════════════════════════════════════════════════════

# ── 9. export_uv_wireframe (WIRE-ONLY writer; in0 UV'd mesh) — render the UV layout to an image ────
@endpoint("export_uv_wireframe")
def export_uv_wireframe(params):
    """SideFX Labs Export UV Wireframe (labs::export_uv_wireframe::1.0) — WIRE-ONLY: renders the input
    mesh's UV layout (wireframe + island fill) to an image file. `input` (input 0) = a UV'd mesh.
    Mirrors maps_baker: the graph is BUILT + configured but the Render Button is NEVER pressed (the
    human fires it). Returns rendered=False.
    SECURITY: `outputfile` is realpath-confined to the working directory; no code/callback parm is set."""
    n = child_after(params["input"], "labs::export_uv_wireframe::1.0", params.get("name"))
    if "uvattrib" in params:
        _try_set(n, "uvattrib", str(params["uvattrib"]))
    if "wirewidth" in params:
        _try_set(n, "wirewidth", clamp(float(params["wirewidth"]), 0.0, 1000.0))
    if "units" in params:
        _menu_set(n, "units", str(params["units"]), _UVWIRE_UNITS)
    if "wireopacity" in params:
        _try_set(n, "wireopacity", clamp(float(params["wireopacity"]), 0.0, 1.0))
    if "islandsopacity" in params:
        _try_set(n, "islandsopacity", clamp(float(params["islandsopacity"]), 0.0, 1.0))
    if "usecd" in params:
        _try_set(n, "usecd", bool(params["usecd"]))
    if "transparentbg" in params:
        _try_set(n, "transparentbg", bool(params["transparentbg"]))
    if "resolution" in params:
        _set_int2(n, "resolution", int(clamp(int(params["resolution"]), 16, 8192)))
    out_path = None
    if params.get("outputfile"):
        out_path = confined_path(params["outputfile"])
        _try_set(n, "outputfile", out_path)
    return {"node": n.path(), "output": out_path, "rendered": False,
            "note": "export_uv_wireframe wired (WIRE-ONLY); press Render yourself"}


# ── 10. udim_tile_number (chain; in0 UV'd mesh) — write a UDIM-tile-number attribute from UVs ──────
@endpoint("udim_tile_number")
def udim_tile_number(params):
    """SideFX Labs UDIM Tile Number (labs::udim_tile_number::1.0) — computes the UDIM tile number for
    each element from its UVs and writes it to an attribute (default `udim_tile`). `input` (input 0) =
    a UV'd mesh. Data-only."""
    n = child_after(params["input"], "labs::udim_tile_number::1.0", params.get("name"))
    if "uvattrib" in params:
        _try_set(n, "uvattrib", str(params["uvattrib"]))
    if "udimattrib" in params:
        _try_set(n, "udimattrib", str(params["udimattrib"]))
    if "udimattribclass" in params:
        _menu_set(n, "udimattribclass", str(params["udimattribclass"]), _UDIM_CLASS)
    if "visualize" in params:
        _try_set(n, "visualize", bool(params["visualize"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 11. visualize_uvs (chain; in0 UV'd mesh) — draw UV islands/seams + texture preview ────────────
@endpoint("visualize_uvs")
def visualize_uvs(params):
    """SideFX Labs Visualize UVs (labs::visualize_uvs::1.2) — builds inspection geometry for a mesh's
    UVs: applies a checker texture-map preview and can draw the UV islands + seams. `input` (input 0)
    = a UV'd mesh.
    SECURITY: `texturemap` is an image READ — confined to the working directory ONLY when supplied;
    otherwise the bundled uvgrid preview is used."""
    n = child_after(params["input"], "labs::visualize_uvs::1.2", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "uvattribute" in params:
        _try_set(n, "uvattribute", str(params["uvattribute"]))
    if params.get("texturemap"):
        _try_set(n, "texturemap", confined_path(params["texturemap"]))
    if "visualizeislands" in params:
        _try_set(n, "visualizeislands", bool(params["visualizeislands"]))
    if "visualizeseams" in params:
        _try_set(n, "visualizeseams", bool(params["visualizeseams"]))
    if "thickness" in params:
        _try_set(n, "thickness", clamp(float(params["thickness"]), 1e-4, 10.0))
    if "worldspace" in params:
        _try_set(n, "worldspace", bool(params["worldspace"]))
    if "blend" in params:
        _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 12. testgeometry_luiz (source; 0 inputs, 3 outputs) — Labs test creature/mesh ─────────────────
@endpoint("testgeometry_luiz")
def testgeometry_luiz(params):
    """SideFX Labs Test Geometry (Luiz) (labs::testgeometry_luiz::2.0) — a SOURCE (0 inputs) that
    builds a ready-made test/showcase mesh (the 'Luiz' asset) for prototyping. Builds a fresh /obj
    geo; fails on name collision. Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::testgeometry_luiz::2.0")
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-3, 1000.0))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


# ── 13. testgeometry_paul (source; 0 inputs, 3 outputs) — Labs test creature/mesh ─────────────────
@endpoint("testgeometry_paul")
def testgeometry_paul(params):
    """SideFX Labs Test Geometry (Paul) (labs::testgeometry_paul::2.0) — a SOURCE (0 inputs) that
    builds a ready-made test/showcase mesh (the 'Paul' asset) for prototyping. Builds a fresh /obj
    geo; fails on name collision. Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::testgeometry_paul::2.0")
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-3, 1000.0))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


# ── 14. houdini_icon (source; 0 inputs) — the Houdini logo mesh ───────────────────────────────────
@endpoint("houdini_icon")
def houdini_icon(params):
    """SideFX Labs Houdini Icon (labs::houdini_icon::1.1) — a SOURCE (0 inputs) that builds the Houdini
    logo as mesh geometry, optionally extruded. Builds a fresh /obj geo; fails on name collision.
    Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::houdini_icon::1.1")
    if "extrude" in params:
        _try_set(n, "extrude", bool(params["extrude"]))
    if "extrudedist" in params:
        _try_set(n, "extrudedist", clamp(float(params["extrudedist"]), 0.0, 100.0))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


# ── 15. simple_retime (chain; in0 animated geo) — retime an input by a speed multiplier ───────────
@endpoint("simple_retime")
def simple_retime(params):
    """SideFX Labs Simple Retime (labs::simple_retime::1.0) — retimes an animated input by a global
    speed multiplier (the per-frame retime Ramp stays at its HDA default). `input` (input 0) = the
    animated geometry. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::simple_retime::1.0", params.get("name"))
    if "speedmultiplier" in params:
        _try_set(n, "speedmultiplier", clamp(float(params["speedmultiplier"]), 0.0, 1000.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

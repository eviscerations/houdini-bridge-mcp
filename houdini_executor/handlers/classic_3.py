"""Classic Rigging (legacy KineFX capture lineage) — data-only handlers. Params
verified against live H21.0.671; every non-deferred endpoint is
proven with a headless cook over the reusable fixture (a 4-joint
skeleton + a proximity-captured tube).

Archetypes (mirror the Labs / classic A/B/C mapping):
  A source  : toon_character_deform_rig (OBJ preset, 0-input full character deform rig) and bone_link
              (SOP `bonelink`, 0-input bone-link geometry source). Built in a fresh container and cooked
              bare; geometry is aggregated to certify the cook.
  B chain   : bone_solidify (in0 = skinned mesh), capture_attribute_unpack (in0 = capture-weighted geo),
              capture_attribute_pack (in0 = unpacked capture geo) and capture_layer_paint (in0 = capture-
              weighted geo). The correct input index is wired explicitly (child_after for input 0).

SECURITY (data-only): only geometric / attribute-name / display / solver-scalar params are surfaced.
  * NO code/callback parm is ever set or exposed. `toon_character_deform_rig`'s OBJ `pickscript` hook,
    and `capture_layer_paint`'s interactive brush surface (`kernel` brush-filter name, `bitmap` brush-
    stamp image file, and every hit/stroke/symmetry brush parm) are LEFT AT DEFAULT and never surfaced —
    this lane exposes NO paint/brush disk or code surface.
  * `rig_path` / `skel_root_path` are in-scene OP-path strings (not files and not code) — plain strings.
  * cost-exponential tet-sizing levers on bone_solidify are hard-clamped.
SKIPPED / DEFERRED nodes: armature FEM pair, the
classic biharmonic / metaball capture solvers, and the six nodes already wrapped in earlier lanes.
"""

import hou
from houdini_executor.server import clamp, child_after, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set
from houdini_executor.handlers._parmutil import _try_set_tuple


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────






def _cooked(n):
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "errors": bool(n.errors())}


def _fresh_geo(name):
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("geo", name)


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_CAPCLASS = ("detail", "primitive", "point", "vertex")
_SOLID_SIZING = ("uniform", "adaptive")
_SOLID_ANIMTYPE = ("0", "1", "2")
_CLP_GROUPTYPE = ("guess", "breakpoints", "edges", "points", "prims")
_CLP_CAPTYPE = ("bone", "wire")
_CLP_PAINTMODE = ("postnormalize", "interactivenormalize")
_CLP_VISLAYER = ("final", "layer")


# ── 1. toon_character_deform_rig (OBJ preset) — A source: full toon character deform rig ──────────
@endpoint("toon_character_deform_rig")
def toon_character_deform_rig(params):
    """Classic Toon Character Deform Rig (OBJ `toon_character_deform_rig`) — instantiates the legacy
    ready-made full toon character: a body-part bone rig (spine / arms / legs / head+neck / hands)
    driving a captured `skin` sub-object. A 0-input preset asset dropped into /obj; cooking it builds
    the character and the endpoint aggregates the `skin` output geometry to certify the cook. Fails on
    name collision. SECURITY: transform/display values only; the OBJ `pickscript` code hook and the
    rig's internal eye-file parms are NEVER set or exposed."""
    name = params.get("name")
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    n = obj.createNode("toon_character_deform_rig", name)
    if "translate" in params:
        _try_set_tuple(n, "t", params["translate"])
    if "rotate" in params:
        _try_set_tuple(n, "r", params["rotate"])
    if "pre_scale" in params:
        _try_set_tuple(n, "s", params["pre_scale"])
    if "uniform_scale" in params:
        _try_set(n, "scale", clamp(float(params["uniform_scale"]), 1e-4, 1e4))
    n.cook(force=True)  # settled-order cook builds the whole rig hierarchy cleanly

    # Primary output / certified deliverable = the character `skin` sub-object's display SOP.
    skin_pts = skin_prims = 0
    skin = hou.node(n.path() + "/skin")
    skin_node = None
    skin_errors = False
    if isinstance(skin, hou.ObjNode):
        dn = skin.displayNode()
        if dn is not None:
            dn.cook(force=True)
            g = dn.geometry()
            skin_pts, skin_prims = len(g.points()), len(g.prims())
            skin_node = dn.path()
            skin_errors = bool(dn.errors())
    # Best-effort total footprint. NOTE: force-cooking the rig's internal object-merge hooks OUT of
    # their settled dependency order re-raises benign `HOOK_IN_WRIST` fetch expressions, so this loop
    # is advisory only and never drives the certified `errors` flag (which tracks the skin output).
    tot_pts = tot_prims = geos = 0
    for ch in n.allSubChildren():
        if isinstance(ch, hou.SopNode) and ch.isDisplayFlagSet():
            try:
                ch.cook(force=True)
                g = ch.geometry()
                if g is not None and len(g.points()):
                    tot_pts += len(g.points()); tot_prims += len(g.prims()); geos += 1
            except Exception:
                pass
    return {"node": n.path(), "skin_output": skin_node, "points": skin_pts, "prims": skin_prims,
            "total_points": tot_pts, "total_prims": tot_prims, "display_geos": geos,
            "errors": skin_errors}


# ── 2. bone_link (bonelink, SOP) — A source: bone-link visualization geometry ────────────────────
@endpoint("bone_link")
def bone_link(params):
    """Classic Bone Link (SOP `bonelink`) — a 0-input SOURCE that emits the bone-link geometry (the
    tapered link shape drawn between a bone's ends, with optional packed-bone / fin / proxy / capture
    visualizations) inside a fresh /obj geo. The classic building block used inside Bone objects. Named
    `bone_link` (vs the KineFX `bone_deform`/`bone_capture` tools). SECURITY: geometric/display values
    only; no file/code surface."""
    geo = _fresh_geo(params.get("name"))
    n = geo.createNode("bonelink")
    if "show_link" in params:
        _try_set(n, "showlink", int(bool(params["show_link"])))
    if "link_type" in params:
        _try_set(n, "linktype", int(clamp(int(params["link_type"]), 0, 4)))
    if "link_scale" in params:
        _try_set(n, "linkscale", clamp(float(params["link_scale"]), 1e-4, 1e4))
    if "use_link_color" in params:
        _try_set(n, "uselinkcolor", int(bool(params["use_link_color"])))
    if "link_color" in params:
        _try_set(n, "uselinkcolor", 1)
        _try_set_tuple(n, "linkcolor", params["link_color"])
    if "pack_bone" in params:
        _try_set(n, "packbone", bool(params["pack_bone"]))
    if "pack_name" in params:
        _try_set(n, "packname", str(params["pack_name"]))
    if "show_link_fin" in params:
        _try_set(n, "showlinkfin", int(bool(params["show_link_fin"])))
    if "link_fin_size" in params:
        _try_set(n, "linkfinsize", clamp(float(params["link_fin_size"]), 1e-4, 1e4))
    if "show_proxy" in params:
        _try_set(n, "showproxy", int(bool(params["show_proxy"])))
    if "proxy_scale" in params:
        _try_set_tuple(n, "proxyscale", params["proxy_scale"])
    if "show_capture" in params:
        _try_set(n, "showcapture", int(bool(params["show_capture"])))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(), "points": len(g.points()), "prims": len(g.prims()),
            "errors": bool(n.errors())}


# ── 3. bone_solidify (bonesolidify, SOP) — B chain: in0 = skinned mesh, opt in1 ──────────────────
@endpoint("bone_solidify")
def bone_solidify(params):
    """Classic Bone Solidify (SOP `bonesolidify`) — tetrahedralizes an input skin `mesh` (input 0) into a
    solid tet mesh bound to the rig, for FEM/soft-body-style bone deformation. `sizing` (uniform vs
    adaptive) + the target/min/max element sizes drive the tet density; piece removal culls tiny islands.
    SECURITY: `rig_path` is an in-scene OP path (not a file); no code surface. The tet-sizing levers (the
    cost-exponential knobs) are hard-clamped."""
    n = child_after(params["mesh"], "bonesolidify", params.get("name"))
    if "use_input_mesh" in params:
        _try_set(n, "useinputmesh", bool(params["use_input_mesh"]))
    if "remesh_surfaces" in params:
        _try_set(n, "remeshsurfaces", bool(params["remesh_surfaces"]))
    if "max_tet_scale" in params:
        _try_set(n, "maxtetscale", clamp(float(params["max_tet_scale"]), 1e-3, 10.0))
    if "sizing" in params:
        _menu_set(n, "sizing", str(params["sizing"]), _SOLID_SIZING)
    if "target_size" in params:
        _try_set(n, "targetsize", clamp(float(params["target_size"]), 1e-3, 1e4))
    if "min_size" in params:
        _try_set(n, "minsize", clamp(float(params["min_size"]), 1e-3, 1e4))
    if "max_size" in params:
        _try_set(n, "maxsize", clamp(float(params["max_size"]), 1e-3, 1e4))
    if "density" in params:
        _try_set(n, "density", clamp(float(params["density"]), 1e-4, 1e4))
    if "gradation" in params:
        _try_set(n, "gradation", clamp(float(params["gradation"]), 0.0, 10.0))
    if "enable_piece_removal" in params:
        _try_set(n, "enablepieceremoval", bool(params["enable_piece_removal"]))
    if "min_piece_points" in params:
        _try_set(n, "bonepiecemin", int(clamp(int(params["min_piece_points"]), 1, 100000)))
    if "bone_animation_type" in params:
        _menu_set(n, "boneanimationtype", str(params["bone_animation_type"]), _SOLID_ANIMTYPE)
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-4, 1e4))
    if "rig_path" in params:
        _try_set(n, "rigpath", str(params["rig_path"]))
    if "unit_length" in params:
        _try_set(n, "unitlength", clamp(float(params["unit_length"]), 1e-4, 1e6))
    if "unit_mass" in params:
        _try_set(n, "unitmass", clamp(float(params["unit_mass"]), 1e-6, 1e6))
    if "tpose_attrib" in params:
        _try_set(n, "tposeattrib", str(params["tpose_attrib"]))
    if "init_frame" in params:
        _try_set(n, "initframe", int(clamp(int(params["init_frame"]), -100000, 100000)))
    return _cooked(n)


# ── 4. capture_attribute_unpack (captureattribunpack, SOP) — B chain: in0 = capture-weighted geo ─
@endpoint("capture_attribute_unpack")
def capture_attribute_unpack(params):
    """Classic Capture Attribute Unpack (SOP `captureattribunpack`) — expands a packed capture attribute
    (default `boneCapture`) on `geometry` (input 0) into its separate `_index` + `_data` component
    attributes, so the raw weights can be edited by generic attribute tools. The inverse of
    capture_attribute_pack. SECURITY: attribute/prefix NAMES only; no file/code surface."""
    n = child_after(params["geometry"], "captureattribunpack", params.get("name"))
    if "attribute_class" in params:
        _menu_set(n, "class", str(params["attribute_class"]), _CAPCLASS)
    if "attribute" in params:
        _try_set(n, "attrib", str(params["attribute"]))
    if "prefix" in params:
        _try_set(n, "prefix", str(params["prefix"]))
    if "secondary_prefix" in params:
        _try_set(n, "secondaryprefix", str(params["secondary_prefix"]))
    if "unpack_properties" in params:
        _try_set(n, "unpackproperties", bool(params["unpack_properties"]))
    if "unpack_data" in params:
        _try_set(n, "unpackdata", bool(params["unpack_data"]))
    if "delete_capture" in params:
        _try_set(n, "deletecapture", bool(params["delete_capture"]))
    return _cooked(n)


# ── 5. capture_attribute_pack (captureattribpack, SOP) — B chain: in0 = unpacked capture geo ─────
@endpoint("capture_attribute_pack")
def capture_attribute_pack(params):
    """Classic Capture Attribute Pack (SOP `captureattribpack`) — collapses the separate capture `_index`
    + `_data` component attributes on `geometry` (input 0) back into a single packed capture attribute
    (default `boneCapture`). The inverse of capture_attribute_unpack (feed unpacked / externally-edited
    weights). SECURITY: attribute/prefix NAMES only; no file/code surface."""
    n = child_after(params["geometry"], "captureattribpack", params.get("name"))
    if "attribute_class" in params:
        _menu_set(n, "class", str(params["attribute_class"]), _CAPCLASS)
    if "attribute" in params:
        _try_set(n, "attrib", str(params["attribute"]))
    if "prefix" in params:
        _try_set(n, "prefix", str(params["prefix"]))
    if "secondary_prefix" in params:
        _try_set(n, "secondaryprefix", str(params["secondary_prefix"]))
    if "pack_properties" in params:
        _try_set(n, "packproperties", bool(params["pack_properties"]))
    if "pack_data" in params:
        _try_set(n, "packdata", bool(params["pack_data"]))
    if "delete_capture" in params:
        _try_set(n, "deletecapture", bool(params["delete_capture"]))
    return _cooked(n)


# ── 6. capture_layer_paint (capturelayerpaint::2.0, SOP) — B chain: in0 = capture-weighted geo ───
@endpoint("capture_layer_paint")
def capture_layer_paint(params):
    """Classic Capture Layer Paint (SOP `capturelayerpaint::2.0`) — edits/normalizes classic capture
    weights on `geometry` (input 0) for the active capture regions; the brush is a viewport tool, so this
    data-only endpoint exposes only the region-selection / normalization / capture-type controls and
    passes the (re-normalized) rig through. `capture_type` = bone vs wire capture. SECURITY: the entire
    interactive brush surface — the `kernel` brush-filter name, the `bitmap` brush-stamp image FILE, and
    all hit/stroke/symmetry brush parms — is NEVER set or exposed; `skel_root_path` is an in-scene OP path
    (not a file); no code parm is touched."""
    n = child_after(params["geometry"], "capturelayerpaint::2.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _CLP_GROUPTYPE)
    if "capture_type" in params:
        _menu_set(n, "capturetype", str(params["capture_type"]), _CLP_CAPTYPE)
    if "deform" in params:
        _try_set(n, "deform", bool(params["deform"]))
    if "skel_root_path" in params:
        _try_set(n, "skelrootpath", str(params["skel_root_path"]))
    if "cregion" in params:
        _try_set(n, "cregion", str(params["cregion"]))
    if "paint_mode" in params:
        _menu_set(n, "paintmode", str(params["paint_mode"]), _CLP_PAINTMODE)
    if "active_regions" in params:
        _try_set(n, "activeregions", str(params["active_regions"]))
    if "visualize" in params:
        _try_set(n, "visualize", bool(params["visualize"]))
    if "visualize_layer" in params:
        _menu_set(n, "vislayer", str(params["visualize_layer"]), _CLP_VISLAYER)
    return _cooked(n)

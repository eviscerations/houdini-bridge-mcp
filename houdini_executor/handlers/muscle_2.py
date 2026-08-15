"""Muscle & Tissue (extended set) — data-only handlers for the modern Muscle/Tissue SOP palette (H21.0.671).

The initial muscle module (muscle_1.py) wrapped the two surface-muscle authoring SOPs (frankenmuscle /
frankenmusclepaint). This module finishes the MODERN muscle/tissue SOP set: the id/solidify build
step, the property/constraint-property authoring family, the tension-line workflow, the deform/flex/
preroll deformers, the merge/mirror/deintersect edit ops, the OTIS configure node, and the tissue
solidify + tissue-property SOPs.

Every param was verified live against H21.0.671 and every endpoint is
proven with a headless cook over the reusable fixture. The canonical fixture chain that feeds these tools:

    tube(surface) -> muscleid -> [surf]                      # a muscle SURFACE carrying `muscle_id`
    [surf] -> musclesolidify -> [solid]                      # tetrahedralized solid + maxthickness
    [solid] -> muscleproperties -> [props]                   # adds the materialW fiber-direction frame
    [surf] -> muscleautotensionlines -> [tlines]             # a tension-line curve for the deformers
    open uncapped tube -> [skin]                             # a tissue skin (unshared boundary edges)

SECURITY (Muscle lane, data-only):
  * No code/callback parm is ever set or exposed — none of these SOPs carry a python/vex/snippet/
    callback parm (verified: has_code_parm=False for all).
  * musclepaint's only file surface is the strokegeo/bakedgeo STASH data blocks (not path strings) and
    its action BUTTONS (reset/recache/erasestrokes); the buttons are NEVER pressed and no path string
    is exposed. String params everywhere else are attribute / group / muscle-id / property-label NAMES.
  * NodeReference params (muscleflex rigpath/rigrestpath, musclepreroll transformref) are NEVER set —
    they point at a rig graph and are out of the data-only surface; left at default.
  * Cost-exponential levers (solve/blur/collision/shrinkwrap iterations, tet density, voxel res,
    preroll frames) are hard-clamped.

DEFERRED (exact cook errors):
  * musclecapture      — cook error "Could not find Muscle ID Attribute. Unsupported Muscle ID
                         Attribute Type." over every fixture upstream; needs an integer muscle-id
                         capture attribute that the data-only string `muscle_id` fixture cannot supply.
  * muscletransfer     — cook error internal group `surface_points` / attribute
                         `__muscletransfer_surfaceptindex` missing; a source->dest character skin-
                         transfer setup that is not synthesizable from the muscle fixture headless.
  * musclesolver / musclesolverfem / musclesolvervellum / tissuesolver / tissuesolvervellum /
    beta::tissuesolver — muscle/tissue DOP SOLVERS (is_solver_like); excluded from this pass per brief.
"""

import hou
from houdini_executor.server import clamp, child_after, bridge_input, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────




def _cooked(n, **extra):
    g = n.geometry()
    out = {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}
    # Honest-return coverage (all guarded — a family member that doesn't produce the value omits it):
    #  * muscle-build steps (muscle_id/franken-family) verify the per-prim muscle_id landed + how many
    #    distinct muscles resulted; `prims` is the surface poly count, not the muscle count.
    #  * deformers (muscle_deform/muscle_flex) are topology-invariant, so points/prims can't prove the
    #    skin MOVED — a bounding box (cheap intrinsic) lets a pass_if compare deformed vs rest.
    try:
        if g.findPrimAttrib("muscle_id") is not None:
            out["muscle_id_written"] = True
            try:
                vals = g.primStringAttribValues("muscle_id")
            except Exception:  # noqa: BLE001 - non-string muscle_id
                vals = g.primIntAttribValues("muscle_id")
            out["muscle_count"] = len(set(vals))
    except Exception:  # noqa: BLE001 - readback convenience must never break a good cook
        pass
    try:
        out["bbox"] = list(g.intrinsicValue("bounds"))   # (xmin,xmax,ymin,ymax,zmin,zmax), cached
    except Exception:  # noqa: BLE001
        pass
    out.update(extra)
    return out


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_GROUPTYPE_V = ("guess", "vertices", "edges", "points", "prims")       # adjustvolume/capture/tissueprops
_GROUPTYPE_B = ("guess", "breakpoints", "edges", "points", "prims")    # tissuesolidifyotis
_VOLMASKMODE = ("none", "attrib")                                      # muscleadjustvolume
_TENSIONMODE = ("none", "byattrib")                                    # muscledeform base/muscle tension
_POINTATTRIB = ("closest", "smooth")                                   # musclesolidify
_THICKSCALE = ("none", "attrib", "value", "attribvalue")               # tissuesolidify::2.0
_TSO_VIS = ("exteriorremesh", "innersurface", "tissuemesh", "coretets", "shelltets", "tinytets")
_TSO_METHOD = ("fused", "separated", "coreonly", "fascia")             # tissuesolidifyotis
_MEND_MODE = ("constrainttoanim", "constrainttobone")                  # otisconfigure ends/rigidpoints
_PRESET_PROPS = ("none", "weak", "blubber", "sponge", "firm")          # tissueproperties(otis)
_PAINT_ATTRTYPE = ("color", "float", "integer")
_PAINT_OP = ("paint", "smooth", "erase", "sample")
_PAINT_MODE = ("over", "add", "max", "min")
_PAINT_SHAPE = ("sphere", "surface", "screen", "fill", "nearest")
_PAINT_RECACHE = ("original", "ray", "primuv", "texuv")


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  BUILD STEP — id / solidify (the surface -> solid pipeline)
# ════════════════════════════════════════════════════════════════════════════════════════════════

# ── 1. muscle_id (muscleid) — B chain, input0 = muscle surface ────────────────────────────────────
@endpoint("muscle_id")
def muscle_id(params):
    """Muscle Muscle ID (muscleid) — assigns a per-primitive `muscle_id` name attribute to each
    connected surface cluster so downstream muscle SOPs can address muscles individually. `surface`
    (input 0) = a clean polygonal muscle surface. SECURITY: attribute/name strings only; no file/code
    surface."""
    n = child_after(params["surface"], "muscleid", params.get("name"))
    if "id_string" in params:
        _try_set(n, "idstring", str(params["id_string"]))
    if "default_name" in params:
        _try_set(n, "defaultname", str(params["default_name"]))
    if "base_name" in params:
        _try_set(n, "basename", str(params["base_name"]))
    if "rename_string" in params:
        _try_set(n, "renamestring", str(params["rename_string"]))
    if "init_frame" in params:
        _try_set(n, "initframe", int(clamp(int(params["init_frame"]), -1000000, 1000000)))
    if "destroy_existing" in params:
        _try_set(n, "destroyexisting", bool(params["destroy_existing"]))
    if "use_symmetry" in params:
        _try_set(n, "usesymmetry", bool(params["use_symmetry"]))
    return _cooked(n)


# ── 2. muscle_solidify (musclesolidify) — B chain, input0 = muscle surface (2 outputs) ────────────
@endpoint("muscle_solidify")
def muscle_solidify(params):
    """Muscle Muscle Solidify (musclesolidify) — tetrahedralizes a muscle SURFACE into a solid muscle
    (carries `muscle_id` + `maxthickness`) ready for properties + simulation. `surface` (input 0) = the
    id'd muscle surface. Output 0 = the solid tets. SECURITY: attribute/name strings only. Cost-tet
    density levers (maxtetsize/iterations/reldensity) are clamped."""
    n = child_after(params["surface"], "musclesolidify", params.get("name"))
    if "max_tet_size" in params:
        _try_set(n, "maxtetsize", clamp(float(params["max_tet_size"]), 1e-3, 1e4))
    if "use_local_feature_size" in params:
        _try_set(n, "uselocalfeaturesize", bool(params["use_local_feature_size"]))
    if "local_feature_scale" in params:
        _try_set(n, "localfeaturescale", clamp(float(params["local_feature_scale"]), 1e-3, 1e3))
    if "one_face_per_tet" in params:
        _try_set(n, "onefacepertet", bool(params["one_face_per_tet"]))
    if "remesh_surfaces" in params:
        _try_set(n, "remeshsurfaces", bool(params["remesh_surfaces"]))
    if "interpolate_point_attribs" in params:
        _try_set(n, "interpolatepointattribs", bool(params["interpolate_point_attribs"]))
    if "point_attrib_method" in params:
        _menu_set(n, "pointattribmethod", str(params["point_attrib_method"]), _POINTATTRIB)
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 50)))
    if "min_size" in params:
        _try_set(n, "minsize", clamp(float(params["min_size"]), 1e-4, 1e4))
    if "max_size" in params:
        _try_set(n, "maxsize", clamp(float(params["max_size"]), 1e-4, 1e4))
    if "rel_density" in params:
        _try_set(n, "reldensity", clamp(float(params["rel_density"]), 1e-3, 1e3))
    if "gradation" in params:
        _try_set(n, "gradation", clamp(float(params["gradation"]), 0.0, 10.0))
    if "tpose_attrib" in params:
        _try_set(n, "tposeattrib", str(params["tpose_attrib"]))
    res = _cooked(n)
    res["tets"] = res["prims"]   # out0 IS the tet mesh — expose the count under its recipe-facing name
    return res


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  PROPERTY / CONSTRAINT-PROPERTY authoring family (per-muscle stiffness/damping etc.)
#  These carry a huge per-muscle multiparm block; we expose the global toggles + the FIRST property
#  block's primary controls (the common case). Guarded _try_set: variant-specific names silently skip.
# ════════════════════════════════════════════════════════════════════════════════════════════════

def _apply_property_block(n, params):
    """Shared curated controls for the muscle/tissue property + constraint-property nodes. Every set is
    probe-safe (_try_set), so a name that a given variant lacks is silently skipped — no parm is ever
    invented and no code/callback surface is touched."""
    for key, parm in (("absolute_radius", "absoluteradius"),
                      ("enable_axial_correction", "enableaxialcorrection"),
                      ("use_tab_labels", "usetablabels"),
                      ("strip_prefix", "strip_prefix")):
        if key in params:
            _try_set(n, parm, bool(params[key]))
    if "group" in params:
        _try_set(n, "group1", str(params["group"]))
    if "property_label" in params:
        _try_set(n, "propertylabel1", str(params["property_label"]))
    if "tab_label" in params:
        _try_set(n, "tablabel1", str(params["tab_label"]))
    if "enable_all" in params:
        _try_set(n, "enableall1", bool(params["enable_all"]))
    # primary stiffness / density values of block 1 (names differ per variant; all guarded)
    for key, parm in (("shape_stiffness", "solidshapestiffness1"),
                      ("volume_stiffness", "solidvolumestiffness1"),
                      ("damping_ratio", "soliddampingratio1"),
                      ("mass_density", "solidmassdensity1"),
                      ("fiber_stiffness", "fiberstiffness1"),
                      ("tendon_stiffness", "tendonstiffness1"),
                      ("muscle_end_stiffness", "muscleendstiffness1"),
                      ("muscle_to_muscle_stiffness", "muscletomusclestiffness1"),
                      ("muscle_to_bone_stiffness", "muscletobonestiffness1")):
        if key in params:
            _try_set(n, parm, clamp(float(params[key]), -1e9, 1e9))
    for key, parm in (("enable_shape", "enableshape1"),
                      ("enable_volume", "enablevolume1"),
                      ("enable_damp", "enabledamp1"),
                      ("enable_mass", "enablemass1"),
                      ("enable_fiber", "enablefiber1"),
                      ("enable_tendon", "enabletendon1"),
                      ("enable_muscle_end_stiffness", "enablemuscleendstiffness1"),
                      ("enable_muscle_to_muscle_stiffness", "enablemuscletomusclestiffness1"),
                      ("enable_muscle_to_bone_stiffness", "enablemuscletobonestiffness1")):
        if key in params:
            _try_set(n, parm, bool(params[key]))


# ── 3. muscle_properties (muscleproperties) — chain, input0 = solid muscle ────────────────────────
@endpoint("muscle_properties")
def muscle_properties(params):
    """Muscle Muscle Properties (muscleproperties) — authors per-muscle solid material properties
    (shape/volume/damping/mass/fiber/tendon stiffness) and computes the `materialW` fiber-direction
    frame on a solid muscle. `muscle` (input 0) = a solidified muscle. SECURITY: group/label/attribute
    names + numeric stiffness values only."""
    n = child_after(params["muscle"], "muscleproperties", params.get("name"))
    _apply_property_block(n, params)
    return _cooked(n)


# ── 4. muscle_properties_otis (musclepropertiesotis) — chain, input0 = solid muscle ───────────────
@endpoint("muscle_properties_otis")
def muscle_properties_otis(params):
    """Muscle Muscle Properties OTIS (musclepropertiesotis) — the OTIS-solver variant of Muscle
    Properties (per-muscle solid material properties for the OTIS muscle-and-tissue sim). `muscle`
    (input 0) = a solidified muscle. SECURITY: group/label/attribute names + numeric values only."""
    n = child_after(params["muscle"], "musclepropertiesotis", params.get("name"))
    _apply_property_block(n, params)
    return _cooked(n)


# ── 5. muscle_constraint_properties_fem (muscleconstraintpropertiesfem) — chain ───────────────────
@endpoint("muscle_constraint_properties_fem")
def muscle_constraint_properties_fem(params):
    """Muscle Muscle Constraint Properties FEM (muscleconstraintpropertiesfem) — authors the per-muscle
    CONSTRAINT properties (end / muscle-to-muscle / muscle-to-bone stiffness, damping, distance) for
    the FEM muscle solver. `muscle` (input 0) = the constrained muscle solid; `reference` (input 1) =
    optional reference geometry. SECURITY: group/label names + numeric values only."""
    n = child_after(params["muscle"], "muscleconstraintpropertiesfem", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    _apply_property_block(n, params)
    if "tpose_attrib" in params:
        _try_set(n, "tposeattrib", str(params["tpose_attrib"]))
    return _cooked(n)


# ── 6. muscle_constraint_properties_otis (muscleconstraintpropertiesotis) — chain ─────────────────
@endpoint("muscle_constraint_properties_otis")
def muscle_constraint_properties_otis(params):
    """Muscle Muscle Constraint Properties OTIS (muscleconstraintpropertiesotis) — the OTIS-solver
    variant of the muscle CONSTRAINT-property authoring node (end / glue / muscle-to-muscle stiffness
    + damping + distance). `muscle` (input 0) = the constrained muscle solid; `reference` (input 1) =
    optional. SECURITY: group/label names + numeric values only."""
    n = child_after(params["muscle"], "muscleconstraintpropertiesotis", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    _apply_property_block(n, params)
    if "boneid_attrib" in params:
        _try_set(n, "boneidattrib", str(params["boneid_attrib"]))
    if "tpose_attrib" in params:
        _try_set(n, "tposeattrib", str(params["tpose_attrib"]))
    return _cooked(n)


# ── 7. muscle_constraint_properties_vellum (muscleconstraintpropertiesvellum) — chain ─────────────
@endpoint("muscle_constraint_properties_vellum")
def muscle_constraint_properties_vellum(params):
    """Muscle Muscle Constraint Properties Vellum (muscleconstraintpropertiesvellum) — the Vellum-solver
    variant of the muscle CONSTRAINT-property authoring node (end / muscle-to-muscle / muscle-to-bone
    stiffness, damping, distance, compress, slide-rate). `muscle` (input 0) = the constrained muscle
    solid; `reference` (input 1) = optional. SECURITY: group/label names + numeric values only."""
    n = child_after(params["muscle"], "muscleconstraintpropertiesvellum", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    _apply_property_block(n, params)
    if "boneid_attrib" in params:
        _try_set(n, "boneidattrib", str(params["boneid_attrib"]))
    if "tpose_attrib" in params:
        _try_set(n, "tposeattrib", str(params["tpose_attrib"]))
    return _cooked(n)


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  TENSION-LINE workflow
# ════════════════════════════════════════════════════════════════════════════════════════════════

# ── 8. muscle_auto_tension_lines (muscleautotensionlines) — chain, input0 = muscle geo ────────────
@endpoint("muscle_auto_tension_lines")
def muscle_auto_tension_lines(params):
    """Muscle Auto Tension Lines (muscleautotensionlines) — auto-generates a tension-line curve down
    the long axis of each `muscle_id` region (the drivers the muscle deformers flex along). `muscle`
    (input 0) = a muscle carrying `muscle_id`. SECURITY: attribute/group names only."""
    n = child_after(params["muscle"], "muscleautotensionlines", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "id_attr" in params:
        _try_set(n, "idattr", str(params["id_attr"]))
    if "end_mask_attr" in params:
        _try_set(n, "endmaskattr", str(params["end_mask_attr"]))
    if "end_mask_thresh" in params:
        _try_set(n, "endmaskthresh", clamp(float(params["end_mask_thresh"]), 0.0, 1.0))
    return _cooked(n)


# ── 9. muscle_tension_lines (muscletensionlines) — chain, input0 = muscle, input1 optional ────────
@endpoint("muscle_tension_lines")
def muscle_tension_lines(params):
    """Muscle Tension Lines (muscletensionlines) — the tension-line authoring node: selects/edits the
    tension lines used to flex muscles, with symmetry support. `muscle` (input 0) = the muscle geo;
    `existing_lines` (input 1) = optional existing tension lines. NOTE: line PICKING is interactive, so
    a headless data-only cook passes through / authors config and may output no lines without a
    selection — use muscle_auto_tension_lines to generate lines programmatically. SECURITY:
    attribute/group/prefix names only."""
    n = child_after(params["muscle"], "muscletensionlines", params.get("name"))
    if params.get("existing_lines"):
        bridge_input(n, params["existing_lines"], index=1, name_hint="existing_lines")
    if "selected_ids" in params:
        _try_set(n, "selectedids", str(params["selected_ids"]))
    if "extra_line_name" in params:
        _try_set(n, "extralinename", str(params["extra_line_name"]))
    if "enable_symmetry" in params:
        _try_set(n, "enablesymmetry", bool(params["enable_symmetry"]))
    if "mirror_from_prefix" in params:
        _try_set(n, "mirrorfromprefix", str(params["mirror_from_prefix"]))
    if "mirror_to_prefix" in params:
        _try_set(n, "mirrortoprefix", str(params["mirror_to_prefix"]))
    if "tpose_attrib" in params:
        _try_set(n, "tposeattrib", str(params["tpose_attrib"]))
    return _cooked(n)


# ── 10. muscle_tension_lines_activate (muscletensionlinesactivate) — chain, in0=tension lines ─────
@endpoint("muscle_tension_lines_activate")
def muscle_tension_lines_activate(params):
    """Muscle Tension Lines Activate (muscletensionlinesactivate) — activates / animates tension lines
    (min/max activation per group, mirror activation across the body). `tension_lines` (input 0) = a
    tension-line curve (e.g. from muscle_auto_tension_lines); `reference` (input 1) = optional.
    SECURITY: attribute/group/prefix names + numeric activation values only."""
    n = child_after(params["tension_lines"], "muscletensionlinesactivate", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    if "attribute" in params:
        _try_set(n, "attribname", str(params["attribute"]))
    if "mirror_activation" in params:
        _try_set(n, "mirroractivation", bool(params["mirror_activation"]))
    if "allow_bidirectional" in params:
        _try_set(n, "allowbidirectional", bool(params["allow_bidirectional"]))
    if "from_prefix" in params:
        _try_set(n, "from_prefix", str(params["from_prefix"]))
    if "to_prefix" in params:
        _try_set(n, "to_prefix", str(params["to_prefix"]))
    if "deform_lines" in params:
        _try_set(n, "deformlines", bool(params["deform_lines"]))
    if "group" in params:
        _try_set(n, "group1", str(params["group"]))
    if "min_active" in params:
        _try_set(n, "minactive1", clamp(float(params["min_active"]), -1e6, 1e6))
    if "max_active" in params:
        _try_set(n, "maxactive1", clamp(float(params["max_active"]), -1e6, 1e6))
    return _cooked(n)


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  DEFORMERS — deform / flex / preroll
# ════════════════════════════════════════════════════════════════════════════════════════════════

# ── 11. muscle_deform (muscledeform::2.0) — chain, THREE required inputs ──────────────────────────
@endpoint("muscle_deform")
def muscle_deform(params):
    """Muscle Muscle Deform (muscledeform::2.0) — the modern quasi-static muscle deformer: solves the
    muscle solid to follow its tension lines with fiber stiffness + tension. Requires THREE inputs:
    `muscle` (input 0) = the muscle solid, `tension_lines` (input 1) = the rest tension lines,
    `tension_lines_anim` (input 2) = the animated tension lines. SECURITY: attribute names + numeric
    solve/tension values only; solve iterations are clamped."""
    n = child_after(params["muscle"], "muscledeform::2.0", params.get("name"))
    bridge_input(n, params["tension_lines"], index=1, name_hint="tension_lines")
    bridge_input(n, params["tension_lines_anim"], index=2, name_hint="tension_lines_anim")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "quasistatic_solve" in params:
        _try_set(n, "quasistaticsolve", bool(params["quasistatic_solve"]))
    if "solve_iterations" in params:
        _try_set(n, "solveiterations", int(clamp(int(params["solve_iterations"]), 1, 1000)))
    if "fiber_stiffness" in params:
        _try_set(n, "fiberstiffness", clamp(float(params["fiber_stiffness"]), 0.0, 1e9))
    if "muscle_end_stiffness" in params:
        _try_set(n, "muscleendstiffness", clamp(float(params["muscle_end_stiffness"]), 0.0, 1e9))
    if "auto_tension" in params:
        _try_set(n, "autotension", clamp(float(params["auto_tension"]), -1e6, 1e6))
    if "muscle_base_tension" in params:
        _try_set(n, "musclebasetension", clamp(float(params["muscle_base_tension"]), -1e6, 1e6))
    if "muscle_base_tension_mode" in params:
        _menu_set(n, "musclebasetensionmode", str(params["muscle_base_tension_mode"]), _TENSIONMODE)
    if "muscle_base_tension_attrib" in params:
        _try_set(n, "musclebasetensionattrib", str(params["muscle_base_tension_attrib"]))
    if "muscle_tension" in params:
        _try_set(n, "muscletension", clamp(float(params["muscle_tension"]), -1e6, 1e6))
    if "muscle_tension_mode" in params:
        _menu_set(n, "muscletensionmode", str(params["muscle_tension_mode"]), _TENSIONMODE)
    if "muscle_tension_attrib" in params:
        _try_set(n, "muscletensionattrib", str(params["muscle_tension_attrib"]))
    return _cooked(n)


# ── 12. muscle_flex (muscleflex::2.0) — chain, input0 = muscle with fiber directions ──────────────
@endpoint("muscle_flex")
def muscle_flex(params):
    """Muscle Muscle Flex (muscleflex::2.0) — flexes a muscle along its tension lines by fiber-scale
    blend (the fast, non-solved bulge). `muscle` (input 0) = a muscle carrying its fiber-direction
    frame (materialW — i.e. run muscle_properties first); `tension_lines` (input 1) = optional tension
    lines; `tension_lines_rest` (input 2) = optional rest lines. SECURITY: NodeReference rig params
    (rigpath/rigrestpath) are NEVER set; attribute names + numeric blend/radius only."""
    n = child_after(params["muscle"], "muscleflex::2.0", params.get("name"))
    if params.get("tension_lines"):
        bridge_input(n, params["tension_lines"], index=1, name_hint="tension_lines")
    if params.get("tension_lines_rest"):
        bridge_input(n, params["tension_lines_rest"], index=2, name_hint="tension_lines_rest")
    if "id_string" in params:
        _try_set(n, "idstring", str(params["id_string"]))
    if "auto_flex_id_string" in params:
        _try_set(n, "autoflexidstring", str(params["auto_flex_id_string"]))
    if "attribute" in params:
        _try_set(n, "attribname", str(params["attribute"]))
    if "blend" in params:
        _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    if "include_fiber_scale_blend" in params:
        _try_set(n, "includefiberscaleblend", bool(params["include_fiber_scale_blend"]))
    if "match_lines_by_name" in params:
        _try_set(n, "matchlinesbyname", bool(params["match_lines_by_name"]))
    if "do_deform" in params:
        _try_set(n, "dodeform", int(bool(params["do_deform"])))
    if "manual_flexing" in params:
        _try_set(n, "manualflexing", bool(params["manual_flexing"]))
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 0.0, 1e4))
    if "rigid_projection" in params:
        _try_set(n, "rigidprojection", bool(params["rigid_projection"]))
    if "enable_delta_mush" in params:
        _try_set(n, "enabledeltamush", bool(params["enable_delta_mush"]))
    if "delta_mush_iterations" in params:
        _try_set(n, "deltamushiterations", int(clamp(int(params["delta_mush_iterations"]), 0, 100)))
    return _cooked(n)


# ── 13. muscle_preroll (musclepreroll) — chain, input0 = muscle ───────────────────────────────────
@endpoint("muscle_preroll")
def muscle_preroll(params):
    """Muscle Muscle Preroll (musclepreroll) — prerolls the muscle deformation from a rest pose over a
    hold + preroll frame range so a sim settles before the shot starts. `muscle` (input 0) = the muscle
    geo. SECURITY: NodeReference `transformref` is NEVER set; numeric frame values are clamped;
    attribute names only."""
    n = child_after(params["muscle"], "musclepreroll", params.get("name"))
    if "init_frame" in params:
        _try_set(n, "initframe", int(clamp(int(params["init_frame"]), -1000000, 1000000)))
    if "hold_frames" in params:
        _try_set(n, "holdframes", int(clamp(int(params["hold_frames"]), 0, 100000)))
    if "preroll_frames" in params:
        _try_set(n, "prerollframes", int(clamp(int(params["preroll_frames"]), 0, 100000)))
    if "match_untransformed" in params:
        _try_set(n, "matchuntransformed", bool(params["match_untransformed"]))
    if "match_reference" in params:
        _try_set(n, "matchreference", bool(params["match_reference"]))
    if "tpose_attrib" in params:
        _try_set(n, "tposeattrib", str(params["tpose_attrib"]))
    return _cooked(n)


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  EDIT ops — merge / mirror / deintersect / adjust volume / slide constraint / tpose
# ════════════════════════════════════════════════════════════════════════════════════════════════

# ── 14. muscle_merge (musclemerge) — source-ish, up to 6 muscle inputs ────────────────────────────
@endpoint("muscle_merge")
def muscle_merge(params):
    """Muscle Muscle Merge (musclemerge) — merges up to six muscle streams into one muscle system
    (keeps `muscle_id` distinct). `muscle` (input 0) required; `muscle2`..`muscle6` optional
    (inputs 1..5). SECURITY: geometry-only, no params, no file/code surface."""
    n = child_after(params["muscle"], "musclemerge", params.get("name"))
    for i, key in enumerate(("muscle2", "muscle3", "muscle4", "muscle5", "muscle6"), start=1):
        if params.get(key):
            bridge_input(n, params[key], index=i, name_hint=key)
    return _cooked(n)


# ── 15. muscle_mirror (musclemirror) — chain, input0 = muscle ─────────────────────────────────────
@endpoint("muscle_mirror")
def muscle_mirror(params):
    """Muscle Muscle Mirror (musclemirror) — mirrors muscles from one side of the body to the other,
    renaming `muscle_id` by prefix swap. `muscle` (input 0) = the muscle geo to mirror. SECURITY:
    attribute/group/prefix names + numeric mirror plane only."""
    n = child_after(params["muscle"], "musclemirror", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "mirror_from_prefix" in params:
        _try_set(n, "mirrorfromprefix", str(params["mirror_from_prefix"]))
    if "mirror_to_prefix" in params:
        _try_set(n, "mirrortoprefix", str(params["mirror_to_prefix"]))
    if "prefixed_attribs" in params:
        _try_set(n, "prefixedattribs", str(params["prefixed_attribs"]))
    if "shape_attribs" in params:
        _try_set(n, "shapeattribs", str(params["shape_attribs"]))
    if "mirror_dist" in params:
        _try_set(n, "mirrordist", clamp(float(params["mirror_dist"]), -1e6, 1e6))
    return _cooked(n)


# ── 16. muscle_deintersect (muscledeintersect) — chain, input0 = muscle, input1 optional ──────────
@endpoint("muscle_deintersect")
def muscle_deintersect(params):
    """Muscle Muscle Deintersect (muscledeintersect) — pushes overlapping muscles apart so they stop
    interpenetrating, out to a thickness offset. `muscle` (input 0) = the muscle geo; `collider`
    (input 1) = optional geometry to also deintersect against. SECURITY: numeric iterations/thickness
    only (iterations clamped)."""
    n = child_after(params["muscle"], "muscledeintersect", params.get("name"))
    if params.get("collider"):
        bridge_input(n, params["collider"], index=1, name_hint="collider")
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 500)))
    if "thickness" in params:
        _try_set(n, "thickness", clamp(float(params["thickness"]), 0.0, 1e4))
    return _cooked(n)


# ── 17. muscle_adjust_volume (muscleadjustvolume) — chain, input0 = muscle, up to 3 inputs ────────
@endpoint("muscle_adjust_volume")
def muscle_adjust_volume(params):
    """Muscle Muscle Adjust Volume (muscleadjustvolume) — grows/shrinks muscle volume along normal +
    tangent, with optional collision resolution against the skin. `muscle` (input 0) = the muscle geo;
    `target` (input 1) / `collider` (input 2) = optional. SECURITY: attribute/group names + numeric
    values only; blur/collision iterations clamped."""
    n = child_after(params["muscle"], "muscleadjustvolume", params.get("name"))
    if params.get("target"):
        bridge_input(n, params["target"], index=1, name_hint="target")
    if params.get("collider"):
        bridge_input(n, params["collider"], index=2, name_hint="collider")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE_V)
    if "volume_change" in params:
        _try_set(n, "volumechange", clamp(float(params["volume_change"]), -1e4, 1e4))
    if "volume_change_mask_mode" in params:
        _menu_set(n, "volumechangemaskmode", str(params["volume_change_mask_mode"]), _VOLMASKMODE)
    if "volume_change_mask_attrib" in params:
        _try_set(n, "volumechangemaskattrib", str(params["volume_change_mask_attrib"]))
    if "scale_tendons" in params:
        _try_set(n, "scaletendons", bool(params["scale_tendons"]))
    if "normal_amount" in params:
        _try_set(n, "normalamount", clamp(float(params["normal_amount"]), -1e4, 1e4))
    if "tangent_amount" in params:
        _try_set(n, "tangentamount", clamp(float(params["tangent_amount"]), -1e4, 1e4))
    if "blur_iterations" in params:
        _try_set(n, "bluriterations", int(clamp(int(params["blur_iterations"]), 0, 500)))
    if "resolve_collisions" in params:
        _try_set(n, "resolvecollisions", bool(params["resolve_collisions"]))
    if "collision_iterations" in params:
        _try_set(n, "collisioniterations", int(clamp(int(params["collision_iterations"]), 0, 500)))
    if "collision_thickness" in params:
        _try_set(n, "collisionthickness", clamp(float(params["collision_thickness"]), 0.0, 1e4))
    return _cooked(n)


# ── 18. muscle_slide_constraint (muscleslideconstraint) — chain, in0=muscle (3 outputs) ───────────
@endpoint("muscle_slide_constraint")
def muscle_slide_constraint(params):
    """Muscle Muscle Slide Constraint (muscleslideconstraint) — builds sliding constraints that let a
    muscle slide over its neighbours / bones while resisting stretch. `muscle` (input 0) = the muscle
    geo; `slide_target` (input 1) / `reference` (input 2) = optional. SECURITY: attribute/group names +
    numeric stiffness/rate only."""
    n = child_after(params["muscle"], "muscleslideconstraint", params.get("name"))
    if params.get("slide_target"):
        bridge_input(n, params["slide_target"], index=1, name_hint="slide_target")
    if params.get("reference"):
        bridge_input(n, params["reference"], index=2, name_hint="reference")
    if "exclude_group" in params:
        _try_set(n, "excludegroup", str(params["exclude_group"]))
    if "use_closest_point" in params:
        _try_set(n, "useclosestpt", bool(params["use_closest_point"]))
    if "use_closest_prim" in params:
        _try_set(n, "useclosestprim", bool(params["use_closest_prim"]))
    if "max_dist_check" in params:
        _try_set(n, "maxdistcheck", bool(params["max_dist_check"]))
    if "max_dist" in params:
        _try_set(n, "maxdist", clamp(float(params["max_dist"]), 0.0, 1e6))
    if "sliding_rate" in params:
        _try_set(n, "slidingrate", clamp(float(params["sliding_rate"]), 0.0, 1e6))
    if "stretch_stiffness" in params:
        _try_set(n, "stretchstiffness", clamp(float(params["stretch_stiffness"]), 0.0, 1e6))
    if "compress_stiffness" in params:
        _try_set(n, "compressstiffness", clamp(float(params["compress_stiffness"]), 0.0, 1e6))
    if "tangent_stiffness" in params:
        _try_set(n, "tangentstiffness", clamp(float(params["tangent_stiffness"]), 0.0, 1e6))
    return _cooked(n)


# ── 19. muscle_tpose (muscletpose) — chain, input0 = muscle, input1 optional ──────────────────────
@endpoint("muscle_tpose")
def muscle_tpose(params):
    """Muscle Muscle T-Pose (muscletpose) — stores / restores the muscle rest (T-pose) shape into a
    named attribute so downstream deformers have a stable reference pose. `muscle` (input 0) = the
    muscle geo; `tpose_source` (input 1) = optional geometry to read the T-pose from. SECURITY:
    attribute name + frame value only."""
    n = child_after(params["muscle"], "muscletpose", params.get("name"))
    if params.get("tpose_source"):
        bridge_input(n, params["tpose_source"], index=1, name_hint="tpose_source")
    if "attribute" in params:
        _try_set(n, "attribname", str(params["attribute"]))
    if "set_switch" in params:
        _try_set(n, "setswitch", int(clamp(int(params["set_switch"]), 0, 8)))
    if "init_frame" in params:
        _try_set(n, "initframe", int(clamp(int(params["init_frame"]), -1000000, 1000000)))
    return _cooked(n)


# ════════════════════════════════════════════════════════════════════════════════════════════════
#  OTIS configure + TISSUE (solidify / properties)
# ════════════════════════════════════════════════════════════════════════════════════════════════

# ── 20. otis_configure_muscle_tissue (otisconfiguremuscleandtissue) — chain (2 outputs) ───────────
@endpoint("otis_configure_muscle_tissue")
def otis_configure_muscle_tissue(params):
    """Muscle OTIS Configure Muscle and Tissue (otisconfiguremuscleandtissue) — assembles the muscle +
    tissue geometry and constraints into the payload the OTIS solver consumes (muscle-end / glue /
    tissue-to-bone constraints, tet quality). `muscle` (input 0) = the muscle solid; `tissue`
    (input 1) / `bones` (input 2) = optional. SECURITY: attribute/group names + numeric values only;
    visualizers are left at default."""
    n = child_after(params["muscle"], "otisconfiguremuscleandtissue", params.get("name"))
    if params.get("tissue"):
        bridge_input(n, params["tissue"], index=1, name_hint="tissue")
    if params.get("bones"):
        bridge_input(n, params["bones"], index=2, name_hint="bones")
    if "ref_frame" in params:
        _try_set(n, "refframe", int(clamp(int(params["ref_frame"]), -1000000, 1000000)))
    if "rest_blend" in params:
        _try_set(n, "restblend", clamp(float(params["rest_blend"]), 0.0, 1.0))
    if "deform_to_ref_bones" in params:
        _try_set(n, "deformtorefbones", bool(params["deform_to_ref_bones"]))
    if "muscles_simulate" in params:
        _try_set(n, "muscles_simulate", bool(params["muscles_simulate"]))
    if "muscle_ends_enable" in params:
        _try_set(n, "muscleends_enable", bool(params["muscle_ends_enable"]))
    if "muscle_ends_threshold" in params:
        _try_set(n, "muscleends_threshold", clamp(float(params["muscle_ends_threshold"]), 0.0, 1e6))
    if "muscle_ends_mode" in params:
        _menu_set(n, "muscleends_mode", str(params["muscle_ends_mode"]), _MEND_MODE)
    if "muscle_glue_enable" in params:
        _try_set(n, "muscleglue_enable", bool(params["muscle_glue_enable"]))
    if "tissue_fascia_collisions" in params:
        _try_set(n, "tissue_fasciacollisions", bool(params["tissue_fascia_collisions"]))
    if "tissue_rigid_points_enable" in params:
        _try_set(n, "tissuerigidpoints_enable", bool(params["tissue_rigid_points_enable"]))
    if "tissue_rigid_points_group" in params:
        _try_set(n, "tissuerigidpoints_group", str(params["tissue_rigid_points_group"]))
    if "tissue_to_bones_enable" in params:
        _try_set(n, "tissuetobones_enable", bool(params["tissue_to_bones_enable"]))
    if "tissue_to_muscle_enable" in params:
        _try_set(n, "tissuetomuscle_enable", bool(params["tissue_to_muscle_enable"]))
    if "tet_quality_enable" in params:
        _try_set(n, "tetquality_enable", bool(params["tet_quality_enable"]))
    if "tet_quality_min" in params:
        _try_set(n, "tetquality_minquality", clamp(float(params["tet_quality_min"]), 0.0, 1.0))
    if "cleanup_attribs" in params:
        _try_set(n, "cleanupattribs", bool(params["cleanup_attribs"]))
    return _cooked(n)


# ── 21. tissue_solidify (tissuesolidify::2.0) — source-ish, input0 = tissue surface (2 outputs) ───
@endpoint("tissue_solidify")
def tissue_solidify(params):
    """Muscle Tissue Solidify (tissuesolidify::2.0) — builds a tetrahedralized tissue (fat/fascia) shell
    of a given thickness under a skin/muscle surface. `surface` (input 0) = the surface to solidify
    inward; `muscles` (input 1) / `core` (input 2) / `backstop` (input 3) = optional. SECURITY:
    attribute names + numeric thickness/density only; tet-density levers are clamped (this node is
    voxel-heavy — keep sizes coarse)."""
    n = child_after(params["surface"], "tissuesolidify::2.0", params.get("name"))
    for i, key in ((1, "muscles"), (2, "core"), (3, "backstop")):
        if params.get(key):
            bridge_input(n, params[key], index=i, name_hint=key)
    if "surface_offset" in params:
        _try_set(n, "surfaceoffset", clamp(float(params["surface_offset"]), -1e4, 1e4))
    if "tissue_thickness" in params:
        _try_set(n, "tissuethickness", clamp(float(params["tissue_thickness"]), 0.0, 1e4))
    if "tissue_thickness_scale_mode" in params:
        _menu_set(n, "tissuethicknessscalemode", str(params["tissue_thickness_scale_mode"]), _THICKSCALE)
    if "tissue_thickness_attrib" in params:
        _try_set(n, "tissuethicknessattrib", str(params["tissue_thickness_attrib"]))
    if "tissue_max_tet_size" in params:
        _try_set(n, "tissuemaxtetsize", clamp(float(params["tissue_max_tet_size"]), 1e-3, 1e4))
    if "remesh_exterior_surface" in params:
        _try_set(n, "remeshexteriorsurface", bool(params["remesh_exterior_surface"]))
    if "min_size" in params:
        _try_set(n, "minsize", clamp(float(params["min_size"]), 1e-4, 1e4))
    if "max_size" in params:
        _try_set(n, "maxsize", clamp(float(params["max_size"]), 1e-4, 1e4))
    if "rel_density" in params:
        _try_set(n, "reldensity", clamp(float(params["rel_density"]), 1e-3, 1e3))
    if "gradation" in params:
        _try_set(n, "gradation", clamp(float(params["gradation"]), 0.0, 10.0))
    if "surface_voxel_size" in params:
        _try_set(n, "surfacevoxelsize", clamp(float(params["surface_voxel_size"]), 1e-3, 1e4))
    if "blur_iterations" in params:
        _try_set(n, "bluriterations", int(clamp(int(params["blur_iterations"]), 0, 200)))
    return _cooked(n)


# ── 22. tissue_solidify_otis (tissuesolidifyotis) — chain, input0 = OPEN skin (2 outputs) ─────────
@endpoint("tissue_solidify_otis")
def tissue_solidify_otis(params):
    """Muscle Tissue Solidify OTIS (tissuesolidifyotis) — the OTIS-solver variant: builds the tissue
    volume between an EXTERIOR skin and an inner shrink-wrapped surface. `skin` (input 0) = an open
    skin mesh (must have unshared boundary edges, or supply a `group`); `muscles` (input 1) /
    `reference` (input 2) = optional. SECURITY: attribute/group names + numeric values only; remesh /
    shrink-wrap iterations are clamped (this node is heavy — keep iterations low)."""
    n = child_after(params["skin"], "tissuesolidifyotis", params.get("name"))
    if params.get("muscles"):
        bridge_input(n, params["muscles"], index=1, name_hint="muscles")
    if params.get("reference"):
        bridge_input(n, params["reference"], index=2, name_hint="reference")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE_B)
    if "keep_biggest_piece" in params:
        _try_set(n, "keepbiggestpiece", bool(params["keep_biggest_piece"]))
    if "visualization" in params:
        _menu_set(n, "visualization", str(params["visualization"]), _TSO_VIS)
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _TSO_METHOD)
    if "smooth_iterations" in params:
        _try_set(n, "smoothiterations", int(clamp(int(params["smooth_iterations"]), 0, 200)))
    if "remesh_exterior_enable" in params:
        _try_set(n, "remeshexterior_enable", bool(params["remesh_exterior_enable"]))
    if "remesh_exterior_iterations" in params:
        _try_set(n, "remeshexterior_iterations", int(clamp(int(params["remesh_exterior_iterations"]), 0, 200)))
    if "inner_shrinkwrap_iterations" in params:
        _try_set(n, "innershrinkwrap_iterations", int(clamp(int(params["inner_shrinkwrap_iterations"]), 0, 200)))
    if "inner_shrinkwrap_preblur_iterations" in params:
        _try_set(n, "innershrinkwrap_prebluriterations", int(clamp(int(params["inner_shrinkwrap_preblur_iterations"]), 0, 200)))
    if "tissue_min_thickness" in params:
        _try_set(n, "tissue_minthickness", clamp(float(params["tissue_min_thickness"]), 0.0, 1e4))
    return _cooked(n)


# ── 23. tissue_properties (tissueproperties) — chain, input0 = tissue solid ───────────────────────
@endpoint("tissue_properties")
def tissue_properties(params):
    """Muscle Tissue Properties (tissueproperties) — authors tissue material properties (surface +
    solid + sliding stiffness/damping/mass, rest scale) from a preset or explicit values, optionally
    masked. `tissue` (input 0) = the tissue solid; `reference` (input 1) = optional. SECURITY:
    attribute/group/mask names + numeric values only."""
    n = child_after(params["tissue"], "tissueproperties", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    _apply_tissue_props(n, params)
    return _cooked(n)


# ── 24. tissue_properties_otis (tissuepropertiesotis) — chain, input0 = tissue solid ──────────────
@endpoint("tissue_properties_otis")
def tissue_properties_otis(params):
    """Muscle Tissue Properties OTIS (tissuepropertiesotis) — the OTIS-solver variant of Tissue
    Properties (core + shell solid stiffness/damping/mass, tissue-to-muscle / tissue-to-bone
    stiffness). `tissue` (input 0) = the tissue solid; `reference` (input 1) = optional. SECURITY:
    attribute/group/mask names + numeric values only."""
    n = child_after(params["tissue"], "tissuepropertiesotis", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    _apply_tissue_props(n, params)
    if "tissue_to_muscle_stiffness" in params:
        _try_set(n, "tissuetomusclestiffness", clamp(float(params["tissue_to_muscle_stiffness"]), 0.0, 1e9))
    if "tissue_to_bone_stiffness" in params:
        _try_set(n, "tissuetobonestiffness", clamp(float(params["tissue_to_bone_stiffness"]), 0.0, 1e9))
    return _cooked(n)


def _apply_tissue_props(n, params):
    """Shared curated controls for the tissue-property nodes (probe-safe)."""
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE_V)
    if "mask" in params:
        _try_set(n, "mask", str(params["mask"]))
    if "invert_mask" in params:
        _try_set(n, "invertmask", bool(params["invert_mask"]))
    if "mask_blend" in params:
        _try_set(n, "maskblend", clamp(float(params["mask_blend"]), 0.0, 1.0))
    if "preset_properties" in params:
        _menu_set(n, "presetproperties", str(params["preset_properties"]), _PRESET_PROPS)
    for key, parm in (("enable_solid_shape_stiffness", "enablesolidshapestiffness"),
                      ("enable_solid_volume_stiffness", "enablesolidvolumestiffness"),
                      ("enable_solid_damping_ratio", "enablesoliddampingratio"),
                      ("enable_solid_mass_density", "enablesolidmassdensity"),
                      ("enable_rest_scale", "enablerestscale")):
        if key in params:
            _try_set(n, parm, bool(params[key]))
    for key, parm in (("solid_shape_stiffness", "solidshapestiffness"),
                      ("solid_volume_stiffness", "solidvolumestiffness"),
                      ("solid_damping_ratio", "soliddampingratio"),
                      ("solid_mass_density", "solidmassdensity"),
                      ("rest_scale", "restscale")):
        if key in params:
            _try_set(n, parm, clamp(float(params[key]), -1e9, 1e9))


# ── 25. muscle_paint (musclepaint) — chain, input0 = muscle geo (data-only paint front-end) ───────
@endpoint("muscle_paint")
def muscle_paint(params):
    """Muscle Muscle Paint (musclepaint) — the paint front-end for muscle attributes / masks on a
    muscle geometry (input 0). Data-only: this configures the target attribute + stroke defaults and
    passes the geometry through (the interactive stroking is not driven headless). SECURITY: no path
    string is exposed; the file/reset/erase BUTTONS (movestashtofile / reset / recache / erasestrokes)
    are NEVER pressed; string params are attribute/group names only."""
    n = child_after(params["muscle"], "musclepaint", params.get("name"))
    if "stroke_group" in params:
        _try_set(n, "stroke_group", str(params["stroke_group"]))
    if "display_group" in params:
        _try_set(n, "displaygroup", bool(params["display_group"]))
    if "otis_attrs" in params:
        _try_set(n, "otisattrs", bool(params["otis_attrs"]))
    if "attribute" in params:
        _try_set(n, "stroke_attrib", str(params["attribute"]))
    if "attribute_type" in params:
        _menu_set(n, "stroke_attribtype", str(params["attribute_type"]), _PAINT_ATTRTYPE)
    if "operation" in params:
        _menu_set(n, "stroke_operation", str(params["operation"]), _PAINT_OP)
    if "paint_mode" in params:
        _menu_set(n, "stroke_paintmode", str(params["paint_mode"]), _PAINT_MODE)
    if "shape" in params:
        _menu_set(n, "stroke_shape", str(params["shape"]), _PAINT_SHAPE)
    if "radius" in params:
        _try_set(n, "stroke_radius", clamp(float(params["radius"]), 0.0, 1e4))
    if "opacity" in params:
        _try_set(n, "stroke_opacity", clamp(float(params["opacity"]), 0.0, 1.0))
    if "soft_edge" in params:
        _try_set(n, "stroke_softedge", clamp(float(params["soft_edge"]), 0.0, 1.0))
    if "fg_value" in params:
        _try_set(n, "fgfloat", clamp(float(params["fg_value"]), -1e6, 1e6))
    if "bg_value" in params:
        _try_set(n, "bgfloat", clamp(float(params["bg_value"]), -1e6, 1e6))
    if "recache_method" in params:
        _menu_set(n, "recachemethod", str(params["recache_method"]), _PAINT_RECACHE)
    if "save_cache" in params:
        _try_set(n, "savecache", bool(params["save_cache"]))
    if "live_mode" in params:
        _try_set(n, "livemode", bool(params["live_mode"]))
    if "do_caching" in params:
        _try_set(n, "docaching", bool(params["do_caching"]))
    return _cooked(n)

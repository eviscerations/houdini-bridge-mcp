"""SideFX Labs — Geometry/Attribute batch. Data-only handlers, params verified against live
H21.0.671. Each node reads/writes point/prim/vertex
attributes and chains onto an upstream SOP (archetype B). `color_blend` is the one dual-input
node (parent mesh -> input 0, a second colored mesh -> input 1, optional mask -> input 2).

SECURITY: this set carries NO file surface and NO code/callback parm. Ramps (color_gradient's
`ramp`, the normalize remap/vis ramps) and the value-replace `filters` multiparm cannot be driven
by a scalar tool, so they stay at their HDA default; the value-replace `btnInitializeValues`
Button (an internal action trigger) is never exposed. Nothing to confine or force off.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set






# ── ordered menu label tuples (position == the live menu index; live-probed) ──────────────────────
_CLASS3 = ("primitive", "point", "vertex")                    # normalize class: idx 0/1/2
_GROUPTYPE = ("guess", "vertices", "edges", "points", "prims")  # grouptype: idx 0..4
_GRAD_AXIS = ("x", "y", "z", "custom")                        # color_gradient axis: idx 0..3
_BLEND_MODE = ("linear", "multiply", "overlay", "screen",
               "add", "darken", "lighten", "difference")      # color_blend blend_mode: idx 0..7
_MMA_TYPE = ("primitive", "point", "vertex")                  # min_max_average attribute_type
_MMA_RENAME = ("add_prefix", "add_suffix")                    # min_max_average attribute_rename
_MMA_METHOD = ("max", "min", "mean", "mode", "median",
               "sum", "sumsquare", "rms", "first", "last")    # min_max_average method1
_SORT_PT = ("none", "vtxord", "byx", "byy", "byz", "rev", "seed", "shift",
            "prox", "vector", "expression", "spatial", "attribute", "circular")  # sort ptsort
_SORT_PRIM = ("none", "byx", "byy", "byz", "rev", "seed", "shift",
              "prox", "vector", "expression", "spatial", "attribute", "circular")  # sort primsort
_VV_DISPLAY = ("geo", "viz")                                  # visualize_vector display
_VV_BODY = ("line", "tube", "cone")                           # visualize_vector arrowbody
_VV_ORIENT = ("none", "right", "left")                        # visualize_vector orientation
_VV_VECTYPE = ("from_attribute", "custom_direction")          # visualize_vector vectortype_1
_VV_COLORING = ("fixed_color", "from_attribute")              # visualize_vector coloring1


# ── 1. attribute_normalize_float (chain; in0 geo w/ a float attr) ─────────────────────────────────
@endpoint("attribute_normalize_float")
def attribute_normalize_float(params):
    """SideFX Labs Attribute Normalize Float (labs::attribute_normalize_float::1.0) — remap a float
    attribute onto `[out_min, out_max]` (default 0..1) using the incoming value range. `input`
    (input 0) supplies the geometry; `attrib` names the float attribute to normalize. Data-only:
    the optional remap/visualize ramps stay at their HDA default."""
    n = child_after(params["input"], "labs::attribute_normalize_float::1.0", params.get("name"))
    if "attrib" in params:
        _try_set(n, "attrib", str(params["attrib"]))
    if "class" in params:
        _menu_set(n, "class", str(params["class"]), _CLASS3)
    if "rename" in params:
        _try_set(n, "rename", bool(params["rename"]))
    if "newname" in params:
        _try_set(n, "newname", str(params["newname"]))
    if "keeporig" in params:
        _try_set(n, "keeporig", bool(params["keeporig"]))
    if "out_min" in params:
        _try_set(n, "outrange1", clamp(float(params["out_min"]), -1e9, 1e9))
    if "out_max" in params:
        _try_set(n, "outrange2", clamp(float(params["out_max"]), -1e9, 1e9))
    if "reportlimitvals" in params:
        _try_set(n, "reportlimitvals", bool(params["reportlimitvals"]))
    if "minmaxprefix" in params:
        _try_set(n, "minmaxprefix", str(params["minmaxprefix"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. attribute_normalize_vector (chain; in0 geo w/ a vector attr) ───────────────────────────────
@endpoint("attribute_normalize_vector")
def attribute_normalize_vector(params):
    """SideFX Labs Attribute Normalize Vector (labs::attribute_normalize_vector::1.0) — normalize a
    vector attribute. `output_unit` (default on) rescales each vector to unit length; with it off the
    magnitudes are remapped into `[out_min, out_max]`. `input` (input 0) supplies the geometry;
    `attrib` names the vector attribute. Data-only: remap/visualize ramps stay at HDA default."""
    n = child_after(params["input"], "labs::attribute_normalize_vector::1.0", params.get("name"))
    if "attrib" in params:
        _try_set(n, "attrib", str(params["attrib"]))
    if "class" in params:
        _menu_set(n, "class", str(params["class"]), _CLASS3)
    if "rename" in params:
        _try_set(n, "rename", bool(params["rename"]))
    if "newname" in params:
        _try_set(n, "newname", str(params["newname"]))
    if "keeporig" in params:
        _try_set(n, "keeporig", bool(params["keeporig"]))
    if "output_unit" in params:
        _try_set(n, "outputunit", bool(params["output_unit"]))
    if "out_min" in params:
        _try_set(n, "outrange1", clamp(float(params["out_min"]), -1e9, 1e9))
    if "out_max" in params:
        _try_set(n, "outrange2", clamp(float(params["out_max"]), -1e9, 1e9))
    if "reportlimitvals" in params:
        _try_set(n, "reportlimitvals", bool(params["reportlimitvals"]))
    if "minmaxprefix" in params:
        _try_set(n, "minmaxprefix", str(params["minmaxprefix"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. attribute_value_replace (chain; in0 geo) ───────────────────────────────────────────────────
@endpoint("attribute_value_replace")
def attribute_value_replace(params):
    """SideFX Labs Attribute Value Replace (labs::attribute_value_replace) — rename an attribute and/or
    seed default init / fallback values on the attributes named in `attribute_list` (default `name`).
    `input` (input 0) supplies the geometry. Data-only: the per-value find/replace `filters` multiparm
    and the `Initialize Values` action button are not exposed (dynamic UI / internal trigger)."""
    n = child_after(params["input"], "labs::attribute_value_replace", params.get("name"))
    if "attribute_list" in params:
        _try_set(n, "pointattriblist", str(params["attribute_list"]))
    if "rename_attr" in params:
        _try_set(n, "bRenameAttr", bool(params["rename_attr"]))
    if "new_attr_name" in params:
        _try_set(n, "sNewAttributeName", str(params["new_attr_name"]))
    if "default_init" in params:
        _try_set(n, "bDefaultInitValue", bool(params["default_init"]))
    if "default_init_value" in params:
        _try_set(n, "sDefaultInitValue", str(params["default_init_value"]))
    if "default_fallback" in params:
        _try_set(n, "bDefaultValue", bool(params["default_fallback"]))
    if "default_fallback_value" in params:
        _try_set(n, "sDefaultValue", str(params["default_fallback_value"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. color_adjustment (chain; in0 geo w/ Cd) ────────────────────────────────────────────────────
@endpoint("color_adjustment")
def color_adjustment(params):
    """SideFX Labs Color Adjustment (labs::color_adjustment) — brightness / contrast / saturation /
    gamma grade on a color attribute (default `Cd`, or a custom attribute). `input` (input 0) supplies
    the geometry. `group`/`group_type` restrict the affected elements. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::color_adjustment", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "custom_attribute" in params:
        _try_set(n, "custom_attribute", bool(params["custom_attribute"]))
    if "custom_attribute_name" in params:
        _try_set(n, "custom_attribute_name", str(params["custom_attribute_name"]))
    if "invert" in params:
        _try_set(n, "invert", bool(params["invert"]))
    if "brightness" in params:
        _try_set(n, "brightness", clamp(float(params["brightness"]), -10.0, 10.0))
    if "contrast" in params:
        _try_set(n, "contrast", clamp(float(params["contrast"]), 0.0, 10.0))
    if "saturation" in params:
        _try_set(n, "saturation", clamp(float(params["saturation"]), 0.0, 10.0))
    if "gamma" in params:
        _try_set(n, "gamma", clamp(float(params["gamma"]), 1e-3, 10.0))
    if "do_clamp" in params:
        _try_set(n, "do_clamp", bool(params["do_clamp"]))
    if "clamp_min" in params:
        _try_set(n, "clampx", clamp(float(params["clamp_min"]), -10.0, 10.0))
    if "clamp_max" in params:
        _try_set(n, "clampy", clamp(float(params["clamp_max"]), -10.0, 10.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. color_blend (DUAL chain; in0 A, in1 B, in2 mask opt) ───────────────────────────────────────
@endpoint("color_blend")
def color_blend(params):
    """SideFX Labs Color Blend (labs::color_blend) — blend two color attributes with a photoshop-style
    `blend_mode`. `input` (input 0) = mesh A carrying `input_1_attr`; `input2` (input 1) = mesh B
    carrying `input_2_attr`; optional `mask` (input 2) modulates the `blend` amount. The result is
    written to `output_attr` (default `Cd`). Data-only (no file surface)."""
    n = child_after(params["input"], "labs::color_blend", params.get("name"))
    bridge_input(n, params["input2"], index=1, name_hint="blend_b")
    if params.get("mask"):
        bridge_input(n, params["mask"], index=2, name_hint="blend_mask")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "input_1_attr" in params:
        _try_set(n, "input_1_attr", str(params["input_1_attr"]))
    if "input_2_attr" in params:
        _try_set(n, "input_2_attr", str(params["input_2_attr"]))
    if "blend_mode" in params:
        _menu_set(n, "blend_mode", str(params["blend_mode"]), _BLEND_MODE)
    if "blend" in params:
        _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    if "output_attr" in params:
        _try_set(n, "blend_attr", str(params["output_attr"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. color_gradient (chain; in0 geo) ────────────────────────────────────────────────────────────
@endpoint("color_gradient")
def color_gradient(params):
    """SideFX Labs Color Gradient (labs::color_gradient) — paint a color gradient along an `axis`
    (X/Y/Z, or Custom rotated by `rotation_angle`) into `Cd` (or a custom attribute). `input`
    (input 0) supplies the geometry. Data-only: the gradient `ramp` stays at its HDA default (a
    scalar tool cannot author a ramp); use `axis`/`rotation_angle` to steer the sweep direction."""
    n = child_after(params["input"], "labs::color_gradient", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _GROUPTYPE)
    if "axis" in params:
        _menu_set(n, "axis", str(params["axis"]), _GRAD_AXIS)
    if "rotation_angle" in params:
        _try_set(n, "fRotationAngle", clamp(float(params["rotation_angle"]), -360.0, 360.0))
    if "custom_attribute" in params:
        _try_set(n, "custom_attribute", bool(params["custom_attribute"]))
    if "custom_attribute_name" in params:
        _try_set(n, "custom_attribute_name", str(params["custom_attribute_name"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. min_max_average (chain; in0 geo w/ an attr) ────────────────────────────────────────────────
@endpoint("min_max_average")
def min_max_average(params):
    """SideFX Labs Min Max Average (labs::min_max_average::1.0) — reduce an attribute to a single
    statistic (`method`: max/min/mean/median/sum/rms/…) and write it back as a detail attribute (or,
    with `detail_attribute` off, promoted per-element) named by `prefix`/`suffix`. `input` (input 0)
    supplies the geometry; `attribute` names the source attribute, `attribute_type` its class."""
    n = child_after(params["input"], "labs::min_max_average::1.0", params.get("name"))
    if "attribute" in params:
        _try_set(n, "attribute", str(params["attribute"]))
    if "attribute_type" in params:
        _menu_set(n, "attribute_type", str(params["attribute_type"]), _MMA_TYPE)
    if "attribute_rename" in params:
        _menu_set(n, "attribute_rename", str(params["attribute_rename"]), _MMA_RENAME)
    if "method" in params:
        _menu_set(n, "method1", str(params["method"]), _MMA_METHOD)
    if "prefix" in params:
        _try_set(n, "prefix1", str(params["prefix"]))
    if "suffix" in params:
        _try_set(n, "suffix1", str(params["suffix"]))
    if "detail_attribute" in params:
        _try_set(n, "detail_attribute1", bool(params["detail_attribute"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 8. radial_sort (chain; in0 geo) ───────────────────────────────────────────────────────────────
@endpoint("radial_sort")
def radial_sort(params):
    """SideFX Labs Radial Sort (labs::radial_sort::1.1) — reorder points and/or primitives by their
    angle around an axis (`*_dir`) so a fan/ring is indexed in a clean rotational order. `input`
    (input 0) supplies the geometry. Enable `point_sort` and/or `prim_sort`; `*_angle_offset` rotates
    the start, `*_reverse` flips the winding. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::radial_sort::1.1", params.get("name"))
    if "point_sort" in params:
        _try_set(n, "ptsort", bool(params["point_sort"]))
    if "point_group" in params:
        _try_set(n, "ptgroup", str(params["point_group"]))
    if "point_dir_x" in params:
        _try_set(n, "pointdirx", clamp(float(params["point_dir_x"]), -1e6, 1e6))
    if "point_dir_y" in params:
        _try_set(n, "pointdiry", clamp(float(params["point_dir_y"]), -1e6, 1e6))
    if "point_dir_z" in params:
        _try_set(n, "pointdirz", clamp(float(params["point_dir_z"]), -1e6, 1e6))
    if "point_angle_offset" in params:
        _try_set(n, "pointangleoffset", clamp(float(params["point_angle_offset"]), -360.0, 360.0))
    if "point_reverse" in params:
        _try_set(n, "pointreverse", bool(params["point_reverse"]))
    if "prim_sort" in params:
        _try_set(n, "primsort", bool(params["prim_sort"]))
    if "prim_group" in params:
        _try_set(n, "primgroup", str(params["prim_group"]))
    if "prim_dir_x" in params:
        _try_set(n, "primdirx", clamp(float(params["prim_dir_x"]), -1e6, 1e6))
    if "prim_dir_y" in params:
        _try_set(n, "primdiry", clamp(float(params["prim_dir_y"]), -1e6, 1e6))
    if "prim_dir_z" in params:
        _try_set(n, "primdirz", clamp(float(params["prim_dir_z"]), -1e6, 1e6))
    if "prim_angle_offset" in params:
        _try_set(n, "primangleoffset", clamp(float(params["prim_angle_offset"]), -360.0, 360.0))
    if "prim_reverse" in params:
        _try_set(n, "primreverse", bool(params["prim_reverse"]))
    if "vertex_prim_order" in params:
        _try_set(n, "vertexprimorder", bool(params["vertex_prim_order"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 9. sort (chain; in0 geo) ──────────────────────────────────────────────────────────────────────
@endpoint("sort_geometry")
def sort_geometry(params):
    """SideFX Labs Sort (labs::sort::1.0) — reorder points and/or primitives by a chosen key:
    axis (byx/byy/byz), random (`seed`), shift (`offset`), along a vector (`*_dir`), spatial locality,
    or by an attribute (`*_attrib`). `input` (input 0) supplies the geometry. Data-only (no file
    surface); the By-Expression mode's expression field is not exposed."""
    n = child_after(params["input"], "labs::sort::1.0", params.get("name"))
    if "point_sort" in params:
        _menu_set(n, "ptsort", str(params["point_sort"]), _SORT_PT)
    if "point_seed" in params:
        _try_set(n, "pointseed", int(params["point_seed"]))
    if "point_offset" in params:
        _try_set(n, "pointoffset", int(params["point_offset"]))
    if "point_dir_x" in params:
        _try_set(n, "pointdirx", clamp(float(params["point_dir_x"]), -1e6, 1e6))
    if "point_dir_y" in params:
        _try_set(n, "pointdiry", clamp(float(params["point_dir_y"]), -1e6, 1e6))
    if "point_dir_z" in params:
        _try_set(n, "pointdirz", clamp(float(params["point_dir_z"]), -1e6, 1e6))
    if "point_attrib" in params:
        _try_set(n, "pointattrib", str(params["point_attrib"]))
    if "point_attrib_comp" in params:
        _try_set(n, "pointattribcomp", int(clamp(int(params["point_attrib_comp"]), 0, 15)))
    if "point_reverse" in params:
        _try_set(n, "pointreverse", bool(params["point_reverse"]))
    if "prim_sort" in params:
        _menu_set(n, "primsort", str(params["prim_sort"]), _SORT_PRIM)
    if "prim_seed" in params:
        _try_set(n, "primseed", int(params["prim_seed"]))
    if "prim_offset" in params:
        _try_set(n, "primoffset", int(params["prim_offset"]))
    if "prim_attrib" in params:
        _try_set(n, "primattrib", str(params["prim_attrib"]))
    if "prim_attrib_comp" in params:
        _try_set(n, "primattribcomp", int(clamp(int(params["prim_attrib_comp"]), 0, 15)))
    if "prim_reverse" in params:
        _try_set(n, "primreverse", bool(params["prim_reverse"]))
    if "vertex_prim_order" in params:
        _try_set(n, "vertexprimorder", bool(params["vertex_prim_order"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 10. visualize_vector (chain; in0 geo w/ a vector attr) ────────────────────────────────────────
@endpoint("visualize_vector")
def visualize_vector(params):
    """SideFX Labs Visualize Vector (labs::visualize_vector::1.0) — build arrow geometry from a vector
    attribute (`vector_attribute`, default `P`) for inspection. `input` (input 0) supplies the
    geometry; `keep_original` (default on) merges the arrows onto the source. `arrow_scale` sizes the
    arrows, `scale_to_magnitude` lengthens them by the vector length. Data-only: the color ramp stays
    at its HDA default."""
    n = child_after(params["input"], "labs::visualize_vector::1.0", params.get("name"))
    if "display" in params:
        _menu_set(n, "display", str(params["display"]), _VV_DISPLAY)
    if "arrows" in params:
        _try_set(n, "arrows", bool(params["arrows"]))
    if "keep_original" in params:
        _try_set(n, "keeporiginal", bool(params["keep_original"]))
    if "arrow_body" in params:
        _menu_set(n, "arrowbody", str(params["arrow_body"]), _VV_BODY)
    if "arrow_thickness" in params:
        _try_set(n, "arrowthickness", clamp(float(params["arrow_thickness"]), 1e-3, 100.0))
    if "arrow_radius" in params:
        _try_set(n, "arrowradius", clamp(float(params["arrow_radius"]), 1e-3, 100.0))
    if "arrow_scale" in params:
        _try_set(n, "arrowscale", clamp(float(params["arrow_scale"]), 1e-5, 1e4))
    if "scale_to_magnitude" in params:
        _try_set(n, "scale_to_magnitude", bool(params["scale_to_magnitude"]))
    if "orientation" in params:
        _menu_set(n, "orientation", str(params["orientation"]), _VV_ORIENT)
    if "show_origin" in params:
        _try_set(n, "showorigin", bool(params["show_origin"]))
    if "origin_radius" in params:
        _try_set(n, "originradius", clamp(float(params["origin_radius"]), 1e-5, 100.0))
    if "vector_attribute" in params:
        _try_set(n, "vectorattribute1", str(params["vector_attribute"]))
    if "vector_type" in params:
        _menu_set(n, "vectortype_1", str(params["vector_type"]), _VV_VECTYPE)
    if "connect" in params:
        _try_set(n, "connect_1", bool(params["connect"]))
    if "normalize" in params:
        _try_set(n, "normalize1", bool(params["normalize"]))
    if "multiplier" in params:
        _try_set(n, "multiplier1", clamp(float(params["multiplier"]), -1e6, 1e6))
    if "coloring" in params:
        _menu_set(n, "coloring1", str(params["coloring"]), _VV_COLORING)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

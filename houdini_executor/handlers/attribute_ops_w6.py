"""SOP modern attribute ops lane — the H20/H21 "attrib*" authoring toolset: the adjust*
family (float/integer/vector/color/array/dict), plus combine/fade/fill/find/frommap/fromparm/
frompieces/mirror/paint/remap/sort/stringedit. Every one is an OPERATOR: `input` is the upstream
geometry (input 0), the node authors/modifies an attribute, and the result is returned via _finish_op.

Params + menu tokens were live-probed on Houdini 21.0.671; nothing is guessed. Style mirrors
handlers/feather.py: typed, clamped, probe-safe
(`_try_set` skips absent parms, never invents one), creators FAIL on name collision (child_after ->
createNode raises rather than clobber user work).

SECURITY (this is the boundary): the adjust* nodes carry a VEXpression sub-path
(usenoiseexpression / noiseexpression / vex_cwdpath) and a Color-Map FILE parm (cmap); attribfrompieces
carries a 'vex' mode + vexcode# snippets; attribexpression is a pure VEX node (handled separately in
the validated-VEX path, NOT wrapped here). The curated param tables below deliberately expose NONE of those code/file
surfaces. The single filesystem parm exposed anywhere is attribfrommap's read-only texture `map_file`
(ToolDef FsPath{write:false}, realpath-confined by the gateway) — a legitimate read-only asset path,
and the node is still usable without it via its Color-Attribute / Volume source modes. No wrangle /
VEX / exec is reachable through this lane.
"""

import hou
from houdini_executor.server import endpoint, child_after, clamp, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared helpers (probe-safe: never invent a parm) ──────────────────────────────────────────────


def _try_set_vec(node, parm, values):
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(float(x) for x in values))
        return True
    except Exception:  # noqa: BLE001
        return False




def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token (StringParmTemplate with a menu): set the token directly."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  v=float-vector(tuple)
       m=index-menu(FULL ordered tokens)  ms=string-token-menu(tokens)."""
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
        elif kind == "v":
            _try_set_vec(node, parm, v)
        elif kind == "m":
            _menu_set(node, parm, str(v), extra)
        elif kind == "ms":
            _str_menu_set(node, parm, str(v), extra)


def _geo_or_none(n):
    try:
        return n.geometry()
    except Exception:  # noqa: BLE001 — a cook error surfaces via n.errors(), not a crash
        return None


def _finish_op(n, **extra):
    """child_after already set display/render + showed the object. Report counts when the node has
    cooked; when it hasn't (e.g. a two-input op called without its second input), return cooked:false
    + the node's errors instead of crashing, so the AI can keep assembling the network."""
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


# exact class-token orders differ PER NODE (probe-verified) — keep them separate.
_CLASS_PVPD = ("point", "vertex", "primitive", "detail")       # adjust float/int/vector/color/array/dict
_CLASS_DPPV = ("detail", "primitive", "point", "vertex")       # attribcombine / attribremap
_CLASS_PPV = ("primitive", "point", "vertex")                  # attribsort
_OP7 = ("init", "set", "add", "sub", "mult", "min", "max")     # adjust float/int operation
# adjust valuetype FULL order (index-mapped); 'cmap' (file) intentionally omitted from the ToolDef Enum.
_VALTYPE = ("const", "rand", "noise", "attrib", "remapattrib", "cmap", "line", "radial", "bbox")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ADJUST FAMILY
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("attrib_adjust_float")
def attrib_adjust_float(params):
    """Attribute Adjust Float — author/modify a float point/vertex/prim/detail attribute with a value
    pattern (attribadjustfloat). `input` is input 0. attrib names the attribute; class its element
    class; operation how the value is applied (set/add/mult/...); value_type the pattern source
    (const/rand/noise/attrib/line/radial/bbox); single_value the constant; min_value/max_value the
    random range; seed the randomization seed. Optional blend fades the effect. Data-only (the node's
    VEXpression + color-map file paths are NOT exposed)."""
    n = child_after(params["input"], "attribadjustfloat", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("attrib", "attrib", "s", None),
        ("attrib_class", "class", "m", _CLASS_PVPD),
        ("operation", "operation", "m", _OP7),
        ("value_type", "valuetype", "m", _VALTYPE),
        ("single_value", "singlevalue", "f", (-1e6, 1e6)),
        ("min_value", "minvalue", "f", (-1e6, 1e6)),
        ("max_value", "maxvalue", "f", (-1e6, 1e6)),
        ("seed", "randomseed", "i", (0, 100000)),
        ("blend", "doblend", "b", None),
        ("blend_weight", "blendweight", "f", (0.0, 1.0)),
        ("clamp_min", "doclampmin", "b", None),
        ("clamp_min_value", "clampminvalue", "f", (-1e6, 1e6)),
        ("clamp_max", "doclampmax", "b", None),
        ("clamp_max_value", "clampmaxvalue", "f", (-1e6, 1e6)),
    ])
    return _finish_op(n)


@endpoint("attrib_adjust_integer")
def attrib_adjust_integer(params):
    """Attribute Adjust Integer — author/modify an integer attribute with a value pattern
    (attribadjustinteger). `input` is input 0. attrib / class target the attribute; operation how the
    value is applied; value_type the pattern (const/rand/noise/attrib/...); single_value the constant;
    min_value/max_value the random integer range; step_size an optional quantisation; seed the seed.
    Data-only (VEXpression + color-map file paths are NOT exposed)."""
    n = child_after(params["input"], "attribadjustinteger", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("attrib", "attrib", "s", None),
        ("attrib_class", "class", "m", _CLASS_PVPD),
        ("operation", "operation", "m", _OP7),
        ("value_type", "valuetype", "m", _VALTYPE),
        ("single_value", "singlevalue", "i", (-1000000, 1000000)),
        ("min_value", "minvalue", "i", (-1000000, 1000000)),
        ("max_value", "maxvalue", "i", (-1000000, 1000000)),
        ("enable_stepping", "enablestepping", "b", None),
        ("step_size", "stepsize", "i", (1, 1000000)),
        ("seed", "randomseed", "i", (0, 100000)),
        ("blend", "doblend", "b", None),
        ("blend_weight", "blendweight", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("attrib_adjust_vector")
def attrib_adjust_vector(params):
    """Attribute Adjust Vector — author/modify a vector attribute's direction and/or length
    (attribadjustvector). `input` is input 0. attrib / class target the attribute; adjust_quantity
    picks direction+length / direction-only / length-only; dirlen_operation how the value is applied;
    value the constant vector [x,y,z]; reverse flips direction; pre_normalize/post_normalize make unit
    length before/after; seed the randomization seed. Data-only (VEXpression not exposed)."""
    n = child_after(params["input"], "attribadjustvector", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("attrib", "attrib", "s", None),
        ("attrib_class", "class", "m", _CLASS_PVPD),
        ("adjust_quantity", "adjustquantity", "m", ("all", "dir", "len")),
        ("dirlen_operation", "dirlen_operation", "m", _OP7),
        ("value", "dirlen_singlevalue", "v", None),
        ("reverse", "reverse", "b", None),
        ("pre_normalize", "prenormalize", "b", None),
        ("post_normalize", "postnormalize", "b", None),
        ("seed", "randomseed", "i", (0, 100000)),
        ("blend", "doblend", "b", None),
        ("blend_weight", "blendweight", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("attrib_adjust_color")
def attrib_adjust_color(params):
    """Attribute Adjust Color — author/modify a color (Cd) attribute (attribadjustcolor). `input` is
    input 0. attrib / class target the attribute; blend_space RGB or HSV; operation the blend op
    (set/add/mult/overlay/screen/...); value_type the pattern (const/rand/attrib/...); color the
    constant color [r,g,b]; seed the randomization seed. Data-only (VEXpression + color-map file paths
    are NOT exposed)."""
    n = child_after(params["input"], "attribadjustcolor", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("attrib", "attrib", "s", None),
        ("attrib_class", "class", "m", _CLASS_PVPD),
        ("blend_space", "blendspace", "m", ("rgb", "hsv")),
        ("operation", "operation", "m",
         ("init", "set", "add", "sub", "mult", "overlay", "screen", "hardmix", "diff", "min", "max")),
        ("value_type", "valuetype", "m", _VALTYPE),
        ("color", "singlevalue", "v", None),
        ("seed", "randomseed", "i", (0, 100000)),
        ("blend", "doblend", "b", None),
        ("blend_weight", "blendweight", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("attrib_adjust_array")
def attrib_adjust_array(params):
    """Attribute Adjust Array — identity/ordering controls for an array attribute (attribadjustarray).
    `input` is input 0. attrib / class target the array attribute; array_type its element type
    (string/int/float/vector2/vector3/vector4); sort / reverse reorder each array. (Per-entry
    add/remove/replace edits live in a multiparm block and are not exposed in this flat wrap.)"""
    n = child_after(params["input"], "attribadjustarray", params.get("name"))
    _apply(n, params, [
        ("attrib", "attrib", "s", None),
        ("attrib_class", "class", "m", _CLASS_PVPD),
        ("array_type", "type", "m", ("string", "int", "float", "vector2", "vector3", "vector4")),
        ("sort", "sort", "b", None),
        ("reverse", "reverse", "b", None),
    ])
    return _finish_op(n)


@endpoint("attrib_adjust_dict")
def attrib_adjust_dict(params):
    """Attribute Adjust Dict — high-level controls for a dictionary attribute (attribadjustdict).
    `input` is input 0. attrib / class target the dict attribute; remove_keys + keys strip keys by
    pattern; delete_empty drops the attribute when a dict becomes empty. (Per-key rename/set edits live
    in multiparm blocks and are not exposed in this flat wrap.)"""
    n = child_after(params["input"], "attribadjustdict", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("attrib", "attrib", "s", None),
        ("attrib_class", "class", "m", _CLASS_PVPD),
        ("remove_keys", "doremovekeys", "b", None),
        ("keys", "removekeys", "s", None),
        ("delete_empty", "deleteemptydict", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# COMBINE / FILL / FADE / REMAP / SORT
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("attrib_combine")
def attrib_combine(params):
    """Attribute Combine — combine attributes into a destination via a math op (attribcombine). `input`
    is input 0; an optional `source` geometry can be wired to input 1 and referenced with
    src_input='second'. dst_attrib is the destination; src_attrib the first source; operation the math
    (copy/add/sub/mul/div/max/min); overall_scale post-scales; class the element class. createmissing
    makes the destination if absent."""
    n = child_after(params["input"], "attribcombine", params.get("name"))
    if params.get("source"):
        bridge_input(n, params["source"], index=1, name_hint="source")
    if params.get("src_attrib") is not None:
        _try_set(n, "numcombines", 1)
    _apply(n, params, [
        ("group", "group", "s", None),
        ("attrib_class", "class", "m", _CLASS_DPPV),
        ("dst_attrib", "dstattrib", "s", None),
        ("src_attrib", "srcattrib1", "s", None),
        ("operation", "combine1", "m", ("copy", "add", "sub", "mul", "div", "max", "min")),
        ("src_input", "srcinput1", "m", ("first", "second")),
        ("overall_scale", "postscale", "f", (0.0, 1000.0)),
        ("create_missing", "createmissing", "b", None),
        ("delete_source", "deletesource", "b", None),
        ("error_on_missing", "errormissing", "b", None),
    ])
    return _finish_op(n)


@endpoint("attrib_fill")
def attrib_fill(params):
    """Attribute Fill — fill/propagate an attribute across a surface by solving a field
    (attribfill). `input` is input 0. mode picks the solve: arrival-time (eikonal), interpolate
    (poisson), blur (heat), extrapolate (transport). attrib is the attribute to fill; source the
    'attribute to match' selecting seed elements; weights / speed optional control attributes; boundary
    an optional boundary group; diffusion_time the blur time step."""
    n = child_after(params["input"], "attribfill", params.get("name"))
    _apply(n, params, [
        ("mode", "mode", "m", ("eikonal", "poisson", "heat", "transport")),
        ("attrib", "attrib", "s", None),
        ("source", "source", "s", None),
        ("weights", "weights", "s", None),
        ("speed", "speed", "s", None),
        ("boundary", "boundary", "s", None),
        ("diffusion_time", "timestep", "f", (0.0, 1.0)),
        ("min_edge_length", "mindist", "f", (0.0, 1.0)),
        ("min_speed", "minspeed", "f", (0.0, 1.0)),
        ("extrapolation_type", "extrapolationtype", "m", ("scalar", "paralleltransport", "radialfield")),
        ("tangential_only", "tangentialonly", "b", None),
        ("global_rotation", "globalrotation", "f", (-180.0, 180.0)),
    ])
    return _finish_op(n)


@endpoint("attrib_fade")
def attrib_fade(params):
    """Attribute Fade — author a per-point fade weight ramping in/holding/out over frames
    (attribfade), typically to fade particles/pieces in and out. `input` is input 0. fade_attrib names
    the output float; fade_in / fade_hold / fade_out set the frame durations; frame_offset shifts the
    curve; start_attrib / duration_attrib optionally drive start-frame / hold per element."""
    n = child_after(params["input"], "attribfade", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("fade_attrib", "fadeattrib", "s", None),
        ("start_attrib", "startattrib", "s", None),
        ("duration_attrib", "durationattrib", "s", None),
        ("frame_offset", "fadeoffset", "f", (-100000.0, 100000.0)),
        ("fade_in", "fadein", "f", (0.0, 100000.0)),
        ("fade_hold", "fadehold", "f", (0.0, 100000.0)),
        ("fade_out", "fadeout", "f", (0.0, 100000.0)),
        ("visualize", "visualize", "b", None),
    ])
    return _finish_op(n)


@endpoint("attrib_remap")
def attrib_remap(params):
    """Attribute Remap — remap a numeric attribute's values from an input range to an output range,
    optionally through a ramp (attribremap). `input` is input 0. in_name is the attribute to remap;
    out_name an optional new name (blank = in place); input_min/max the source range; output_min/max
    the target range; clamp_type how out-of-range values are handled; use_ramp toggles the remap ramp;
    class the element class."""
    n = child_after(params["input"], "attribremap", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("attrib_class", "class", "m", _CLASS_DPPV),
        ("in_name", "inname", "s", None),
        ("out_name", "outname", "s", None),
        ("input_min", "inputmin", "f", (-1e9, 1e9)),
        ("input_max", "inputmax", "f", (-1e9, 1e9)),
        ("output_min", "outputmin", "f", (-1e9, 1e9)),
        ("output_max", "outputmax", "f", (-1e9, 1e9)),
        ("clamp_type", "clamptype", "m", ("edge", "linear", "cycle")),
        ("use_ramp", "useramp", "b", None),
    ])
    return _finish_op(n)


@endpoint("attrib_sort")
def attrib_sort(params):
    """Attribute Sort — reorder points/vertices/prims by the value of an attribute (attribsort).
    `input` is input 0. attrib is the sort key; class the element class (primitive/point/vertex);
    component which vector component to sort on; order ascending or descending; sort_indices optionally
    writes the argsort permutation to an attribute."""
    n = child_after(params["input"], "attribsort", params.get("name"))
    _apply(n, params, [
        ("attrib_class", "class", "m", _CLASS_PPV),
        ("attrib", "attrib", "s", None),
        ("component", "component", "i", (0, 100)),
        ("order", "order", "m", ("ascending", "descending")),
        ("use_indices", "useindices", "b", None),
        ("indices", "indices", "s", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# FIND / FROM-MAP / FROM-PARM / FROM-PIECES  (some need a second input)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("attrib_find")
def attrib_find(params):
    """Attribute Find — for each element, find the element(s) in a SEARCH geometry with a matching
    attribute value (attribfind). `input` (query geometry) is input 0; `search` (the geometry to
    search in) MUST be wired to input 1 — the node errors without it. query_attrib is the value looked
    up; search_in_attrib the attribute searched; mode what to record (first/all element numbers, or
    interpolated prim + uvw); tolerance the match tolerance."""
    n = child_after(params["input"], "attribfind", params.get("name"))
    if params.get("search"):
        bridge_input(n, params["search"], index=1, name_hint="search")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("query_attrib", "queryattrib", "s", None),
        ("search_in_attrib", "searchinattrib", "s", None),
        ("mode", "mode", "m", ("first", "all", "firstuvw", "alluvw", "verts", "points")),
        ("tolerance", "tolerance", "f", (0.0, 100.0)),
        ("nums_attrib", "numattrib", "s", None),
        ("uvw_attrib", "uvwattrib", "s", None),
        ("wrap_unit_cube", "wrapunitcube", "b", None),
    ])
    return _finish_op(n)


@endpoint("attrib_from_map")
def attrib_from_map(params):
    """Attribute From Map — sample a source into a point attribute along UVs (attribfrommap). `input`
    is input 0. map_source picks the source: 'off' = a Cd color attribute already on the geometry,
    'on' = a texture file (map_file), 'vol' = a volume primitive (volume_name) from the input.
    export_attribute names the output; attrib_type float or vector; uv_attrib the UV set; color_channel
    which channel to read. map_file is a read-only, working-dir-confined asset path (only needed for the
    'on' source)."""
    n = child_after(params["input"], "attribfrommap", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("map_source", "use_file", "m", ("off", "on", "vol")),
        ("map_file", "filename", "s", None),
        ("volume_name", "volume_name", "s", None),
        ("uv_attrib", "uvattrib", "s", None),
        ("export_attribute", "export_attribute", "s", None),
        ("attrib_type", "attrib_type", "m", ("float", "vector")),
        ("color_channel", "color_channel", "i", (0, 4)),
        ("visualize", "visualize_map", "b", None),
    ])
    return _finish_op(n)


@endpoint("attrib_from_parm")
def attrib_from_parm(params):
    """Attribute From Parm — import another node's PARAMETER VALUES onto geometry as attributes
    (attribfromparm). `input` is input 0. node_path is the source Houdini node whose parameters are
    read; method how they map (detail from a single node / points from a subnetwork or compiled block);
    attrib the output attribute name; parm_filter / category_filter select which parameters; evaluate
    reads evaluated values. Data-only: reads parameter values, runs no code."""
    n = child_after(params["input"], "attribfromparm", params.get("name"))
    _apply(n, params, [
        ("method", "method", "m", ("single", "subnet", "compile", "singlepoint")),
        ("node_path", "nodepath", "s", None),
        ("attrib", "name", "s", None),
        ("parm_filter", "parmfilter", "s", None),
        ("category_filter", "category", "s", None),
        ("evaluate", "evaluateparms", "b", None),
    ])
    return _finish_op(n)


@endpoint("attrib_from_pieces")
def attrib_from_pieces(params):
    """Attribute From Pieces — assign a per-piece attribute value across named pieces (attribfrompieces).
    `input` (the geometry with pieces) is input 0; a `pieces` geometry MUST be wired to input 1 — the
    node errors without a second source. piece_attrib names the piece id (e.g. 'name'); attrib the
    attribute to write; attrib_type numeric or string; mode how values are distributed across pieces
    (cycle/patches/noise/random/map-attribute); seed / shuffle randomise. (The 'vex' mode + VEXpression
    inputs are NOT exposed.)"""
    n = child_after(params["input"], "attribfrompieces", params.get("name"))
    if params.get("pieces"):
        bridge_input(n, params["pieces"], index=1, name_hint="pieces")
    _apply(n, params, [
        ("piece_attrib", "pieceattrib", "s", None),
        ("piece_filter", "piecefilter", "s", None),
        ("mode", "mode", "m", ("cycle", "worley", "noise", "random", "attrib", "vex")),
        ("attrib", "attrib", "s", None),
        ("attrib_type", "attribtype", "m", ("number", "string")),
        ("copy_attribs", "copyattrib", "s", None),
        ("shuffle", "shuffle", "b", None),
        ("seed", "seed", "i", (0, 100000)),
        ("offset", "offset", "i", (0, 100000)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# MIRROR / PAINT / STRING-EDIT
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("attrib_mirror")
def attrib_mirror(params):
    """Attribute Mirror — copy/mirror an attribute from one side of geometry to the other
    (attribmirror). `input` is input 0. attrib picks WHAT to copy (color / texture-uv / other);
    attrib_name the specific attribute name when 'other'; mirror_method plane/topology/mapping;
    origin + direction define the mirror plane; transform how mirrored vectors/uvs/points are
    reoriented; string_replace + search/replace remap side-tagged string values (e.g. L_* -> R_*)."""
    n = child_after(params["input"], "attribmirror", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("group_type", "grouptype", "m", ("vertices", "points", "prims")),
        ("use_group_as", "usegroupas", "m", ("source", "destination")),
        ("attrib", "attrib", "m", ("colorattrib", "uvattrib", "otherattrib")),
        ("attrib_name", "attribname", "s", None),
        ("mirror_method", "mirroringmethod", "m", ("plane", "topology", "mapping")),
        ("origin", "origin", "v", None),
        ("direction", "dir", "v", None),
        ("transform", "attribmirror", "m", ("nomirror", "uvmirror", "vectormirror", "pointmirror")),
        ("string_replace", "stringreplace", "b", None),
        ("search", "search", "s", None),
        ("replace", "replace", "s", None),
    ])
    return _finish_op(n)


@endpoint("attrib_paint")
def attrib_paint(params):
    """Attribute Paint — set up a paintable attribute (attribpaint). `input` is input 0. attrib names
    the attribute; attrib_type color / float / integer; fg_color / fg_float / fg_int the foreground
    value; enable_mirror mirrors strokes across a plane. NOTE: the actual painting is an interactive
    viewport operation; headless this configures the node and passes geometry through (the stroke-data
    and cache FILE parms are NOT exposed)."""
    n = child_after(params["input"], "attribpaint", params.get("name"))
    _apply(n, params, [
        ("group", "stroke_group", "s", None),
        ("attrib", "stroke_attrib", "s", None),
        ("attrib_type", "stroke_attribtype", "m", ("color", "float", "integer")),
        ("fg_color", "fgcolor", "v", None),
        ("fg_float", "fgfloat", "f", (-1e6, 1e6)),
        ("fg_int", "fgint", "i", (-1000000, 1000000)),
        ("enable_mirror", "domirror", "b", None),
    ])
    return _finish_op(n)


@endpoint("attrib_string_edit")
def attrib_string_edit(params):
    """Attribute String Edit — find/replace on string attribute values (attribstringedit). `input` is
    input 0. Enable the classes to touch with points/prims/detail/vertex + the matching *_list of
    attribute names. A single find -> replace pair is applied to the enabled attributes. (Additional
    replacement pairs and regex mode live in a multiparm block and are not exposed here.)"""
    n = child_after(params["input"], "attribstringedit", params.get("name"))
    _apply(n, params, [
        ("points", "pointattribs", "b", None),
        ("point_list", "pointattriblist", "s", None),
        ("prims", "primitiveattribs", "b", None),
        ("prim_list", "primattriblist", "s", None),
        ("detail", "detailattribs", "b", None),
        ("detail_list", "detailattriblist", "s", None),
        ("vertex", "vertexattribs", "b", None),
        ("vertex_list", "vertexattriblist", "s", None),
    ])
    # single find->replace pair via the `filters` multiparm block. The block ships with one instance
    # whose fields are 0-indexed (from0/to0); ensure >=1 instance, then write the first from<k>/to<k>.
    if params.get("find") is not None or params.get("replace") is not None:
        cnt = n.parm("filters")
        if cnt is not None and cnt.eval() < 1:
            _try_set(n, "filters", 1)
        k = None
        for i in (0, 1):
            if n.parm(f"from{i}") is not None:
                k = i
                break
        if k is not None:
            _try_set(n, f"from{k}", str(params.get("find", "")))
            _try_set(n, f"to{k}", str(params.get("replace", "")))
    return _finish_op(n)

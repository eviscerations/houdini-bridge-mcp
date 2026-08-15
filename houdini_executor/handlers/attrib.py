"""Attribute + group handlers (SOP). Params verified against live H21.0.671. Typed, clamped,
data-shaped — no wrangle/VEX/exec.
"""

from houdini_executor.server import endpoint, child_after, clamp, resolve_node
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set






_CLASS = ("detail", "primitive", "point", "vertex")
_AC_TYPE = ("float", "int", "vector", "index", "floatarray", "intarray", "stringarray", "dict", "dictarray")
_AC_PREC = ("8", "16", "32", "64", "auto")
# typeinfo1 ordered-menu tokens (live-probed 21.0.671; note 'tranform' is the node's own spelling).
_AC_TYPEINFO = ("guess", "none", "point", "vector", "normal", "color", "quaternion", "tranform", "texturecoord")
# existing1 ordered-menu tokens: what to do if the attribute already exists.
_AC_EXISTING = ("error", "warn", "replace", "better")


@endpoint("attribute_create")
def attribute_create(params):
    """Create a typed point/prim/vertex/detail attribute with a constant value (attribcreate). The
    typed non-wrangle way to add Cd/pscale/N/id/material-index or any custom attribute. attrib_name =
    the attribute to create (default 'attr'). type: float|int|vector|index|floatarray|intarray|
    stringarray|dict|dictarray. class: point|prim|vertex|detail. value = a number or [x,y,z] (string
    types take a string). size = tuple size 1..4. precision: 8|16|32|64|auto storage bits. type_info
    tags the attribute's transform semantics (point|vector|normal|color|quaternion|tranform|
    texturecoord|none) so downstream nodes transform it correctly — set 'normal' for N, 'color' for
    Cd, 'point' for positions. on_existing: error|warn|replace|better when the name already exists
    (default error). group (opt) restricts creation to a group."""
    n = child_after(params["input"], "attribcreate::2.0", params.get("name"))
    n.parm("name1").set(str(params.get("attrib_name", "attr")))
    cls = str(params.get("class", "point"))
    _menu_set(n, "class1", "primitive" if cls == "prim" else cls, _CLASS)
    typ = str(params.get("type", "float"))
    _menu_set(n, "type1", typ, _AC_TYPE)
    if "size" in params:
        _try_set(n, "size1", int(clamp(int(params["size"]), 1, 4)))
    prec = str(params.get("precision", "")) if params.get("precision") is not None else ""
    if prec in _AC_PREC:
        _menu_set(n, "precision1", prec, _AC_PREC)
    if params.get("type_info") is not None:
        _menu_set(n, "typeinfo1", str(params["type_info"]), _AC_TYPEINFO)
    if params.get("on_existing"):
        _menu_set(n, "existing1", str(params["on_existing"]), _AC_EXISTING)
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    val = params.get("value")
    if val is not None:
        if isinstance(val, (list, tuple)):
            vals = [float(x) for x in val[:4]] + [0.0] * (4 - min(len(val), 4))
            try:
                n.parmTuple("value1v").set(tuple(vals))
            except Exception:
                pass
        elif isinstance(val, str):
            _try_set(n, "string1", val)
        else:
            try:
                n.parmTuple("value1v").set((float(val), 0.0, 0.0, 0.0))
            except Exception:
                pass
    n.geometry()
    return {"node": n.path(), "attrib": str(params.get("attrib_name", "attr")), "class": cls, "type": typ}


_PROMOTE_METHOD = ("max", "min", "mean", "mode", "median", "sum", "sumsquare", "rms", "first", "last", "array")


@endpoint("attribute_promote")
def attribute_promote(params):
    """Move/aggregate an attribute between element classes (attribpromote) — the standard non-wrangle
    way to turn a point attribute into a per-prim mean, spread a detail value onto points, etc.
    attrib = the source attribute name. from_class/to_class: point|prim|vertex|detail. method =
    how many source values collapse onto one destination element: max|min|mean|mode|median|sum|
    sumsquare|rms|first|last|array (default mean). out_name renames the promoted result (else it
    keeps `attrib`'s name). piece_attrib promotes WITHIN each named piece independently (per-piece
    aggregation). delete_original controls whether the source attribute is removed — NOTE the node
    DELETES the source by default (pass delete_original=false to keep both)."""
    n = child_after(params["input"], "attribpromote", params.get("name"))
    n.parm("inname").set(str(params["attrib"]))
    _menu_set(n, "inclass", _norm_class(params.get("from_class", "point")), _CLASS)
    _menu_set(n, "outclass", _norm_class(params.get("to_class", "prim")), _CLASS)
    m = str(params.get("method", "mean"))
    _menu_set(n, "method", m, _PROMOTE_METHOD)
    if params.get("out_name"):
        _try_set(n, "useoutname", True)
        _try_set(n, "outname", str(params["out_name"]))
    if params.get("piece_attrib"):
        _try_set(n, "usepieceattrib", True)
        _try_set(n, "pieceattrib", str(params["piece_attrib"]))
    if "delete_original" in params:
        _try_set(n, "deletein", bool(params["delete_original"]))
    n.geometry()
    return {"node": n.path(), "attrib": str(params["attrib"]), "method": m}


def _norm_class(c):
    c = str(c)
    return "primitive" if c == "prim" else c


@endpoint("attribute_delete")
def attribute_delete(params):
    """Drop attributes by class + name pattern. point/prim/vertex/detail are space-separated name
    patterns (e.g. "Cd N *"); negate keeps only the listed ones."""
    n = child_after(params["input"], "attribdelete", params.get("name"))
    if params.get("point"):
        _try_set(n, "doptdel", True)
        _try_set(n, "ptdel", str(params["point"]))
    if params.get("prim"):
        _try_set(n, "doprimdel", True)
        _try_set(n, "primdel", str(params["prim"]))
    if params.get("vertex"):
        _try_set(n, "dovtxdel", True)
        _try_set(n, "vtxdel", str(params["vertex"]))
    if params.get("detail"):
        _try_set(n, "dodtldel", True)
        _try_set(n, "dtldel", str(params["detail"]))
    if "negate" in params:
        _try_set(n, "negate", bool(params["negate"]))
    n.geometry()
    return {"node": n.path()}


# attribcast's precision1 is a STRING menu whose real tokens are 'fpreal16'/'int32'/... — NOT the
# bare '16'/'32'/'64' the friendly API accepts. Setting the bare number stores an invalid token and
# the cast silently does nothing (live-probed 21.0.671). Map friendly floats -> fpreal*, and pass
# any explicit node token straight through so int/uint casts stay reachable.
_CAST_PRECISION = {
    "16": "fpreal16", "32": "fpreal32", "64": "fpreal64",
    "uint8": "uint8", "int8": "int8", "int16": "int16", "int32": "int32", "int64": "int64",
    "fpreal16": "fpreal16", "fpreal32": "fpreal32", "fpreal64": "fpreal64", "preferred": "preferred",
}


@endpoint("attribute_cast")
def attribute_cast(params):
    """Cast attribute storage precision (attribcast) — the memory-halving 32->16-bit optimization for
    heavy point clouds / terrain tiles. class: point|prim|vertex|detail. attribs = space-separated
    name patterns (default '*' = all). precision = target storage: the friendly floats 16|32|64 map to
    fpreal16/32/64, or pass an explicit node token (uint8|int8|int16|int32|int64|fpreal16|fpreal32|
    fpreal64|preferred) for integer casts. (Casting to 16-bit float halves an attribute's memory.)"""
    n = child_after(params["input"], "attribcast", params.get("name"))
    _try_set(n, "class1", _norm_class(params.get("class", "point")))
    _try_set(n, "attribs1", str(params.get("attribs", "*")))
    tok = _CAST_PRECISION.get(str(params.get("precision", "16")), "fpreal16")
    _try_set(n, "precision1", tok)
    n.geometry()
    return {"node": n.path(), "attribs": str(params.get("attribs", "*")), "precision": tok}


@endpoint("connectivity")
def connectivity(params):
    """Label each connected piece with a running class id attribute (connectivity) — the input to
    blast-by-piece, despeckle-by-size, per-piece randomize, and assemble. connect_type: point (points
    sharing an edge) | prim (prims sharing a point) — default prim. attrib_name = output id attribute
    (default 'class'). attrib_type: int | string (string prepends `prefix`, e.g. 'piece_3'). prefix =
    string label when attrib_type=string (default empty). group = restrict the labelling to a point/
    prim group (only elements in the group are numbered). by_uv splits connectivity across UV seams
    (needs uv_attrib)."""
    n = child_after(params["input"], "connectivity", params.get("name"))
    ct = str(params.get("connect_type", "prim"))
    _menu_set(n, "connecttype", ct, ("point", "prim"))
    _try_set(n, "attribname", str(params.get("attrib_name", "class")))
    _menu_set(n, "attribtype", str(params.get("attrib_type", "int")), ("int", "string"))
    if params.get("prefix") is not None:
        _try_set(n, "prefix", str(params["prefix"]))
    if params.get("group"):
        # primincgroup / pointincgroup restrict the labelling; set the one matching connect_type.
        _try_set(n, "pointincgroup" if ct == "point" else "primincgroup", str(params["group"]))
    if params.get("by_uv"):
        _try_set(n, "byuv", True)
        if params.get("uv_attrib"):
            _try_set(n, "uvattrib", str(params["uv_attrib"]))
    n.geometry()
    return {"node": n.path(), "attrib": str(params.get("attrib_name", "class"))}


_MEASURE = ("perimeter", "area", "volume", "centroid", "curvature", "gradient", "laplacian",
            "boundaryintegral", "surfaceintegral")
_CURV = ("gaussian", "mean", "principal", "curvedness")
_MEASURE_CLASS = ("points", "prims")


@endpoint("measure")
def measure(params):
    """Compute a geometric quantity into an attribute (measure). measure_type: perimeter | area |
    volume | centroid | curvature | gradient | laplacian | boundaryintegral | surfaceintegral
    (default area). attrib_name = output attribute. class: points | prims — which class receives the
    result (default prims for area/volume, points for curvature; pass to override). curvature_type:
    gaussian | mean | principal | curvedness (only when measure_type=curvature). src_attrib names the
    scalar/vector attribute that gradient / laplacian / *integral operate ON (e.g. measure the
    gradient of a 'height' or 'mask' attribute). total_attrib writes the summed total (area/volume of
    the whole mesh or per piece) into a detail attribute of that name. group restricts the measure."""
    n = child_after(params["input"], "measure::2.0", params.get("name"))
    mt = str(params.get("measure_type", "area"))
    _menu_set(n, "measure", mt, _MEASURE)
    if params.get("attrib_name"):
        _try_set(n, "attribname", str(params["attrib_name"]))
    if params.get("class"):
        c = "points" if str(params["class"]) == "point" else ("prims" if str(params["class"]) == "prim" else str(params["class"]))
        _menu_set(n, "grouptype", c, _MEASURE_CLASS)
    if mt == "curvature":
        _menu_set(n, "curvaturetype", str(params.get("curvature_type", "mean")), _CURV)
    if params.get("src_attrib") is not None:
        _try_set(n, "srcattrib", str(params["src_attrib"]))
    if params.get("total_attrib"):
        _try_set(n, "usetotalattrib", True)
        _try_set(n, "totalattribname", str(params["total_attrib"]))
    if params.get("group"):
        _try_set(n, "group", str(params["group"]))
    n.geometry()
    return {"node": n.path(), "measure_type": mt}


_GC_OPS = {"union": "or", "intersect": "and", "xor": "xor", "subtract": "sub"}
_GC_TYPES = ("guess", "points", "prims", "edges", "vertices")


@endpoint("group_combine")
def group_combine(params):
    """Boolean-combine two named groups into a result group. operation: union|intersect|xor|
    subtract; result = new group name; group_a / group_b = source group names."""
    n = child_after(params["input"], "groupcombine", params.get("name"))
    _try_set(n, "group1", str(params.get("result", "combined")))
    _menu_set(n, "grouptype1", str(params.get("group_type", "guess")), _GC_TYPES)
    _try_set(n, "group_a1", str(params.get("group_a", "")))
    op = str(params.get("operation", "union"))
    _try_set(n, "op_ab1", _GC_OPS.get(op, "or"))
    _try_set(n, "group_b1", str(params.get("group_b", "")))
    n.geometry()
    return {"node": n.path(), "result": str(params.get("result", "combined")), "operation": op}

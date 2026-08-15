"""Solaris / LOP / USD *authoring* lane — prim creation, component/layout structure, and
xform/instancing. Fixed, typed, data-only LOP wrappers. Params + menu tokens verified against live
H21.0.671 via the LOP probe.

Idiom (copied verbatim from usd.py): every node is created with `_stage_node(ntype, name, after)` —
a GENERATOR is born fresh in /stage via server.stage_context(); an OPERATOR is chained onto its
`after` LOP with setInput(0, src). Multi-input nodes wire their extra sources with setInput at the
probed indices. Cook is proven with `n.cook(force=True)` and read back through `n.stage()` (a
pxr.Usd.Stage), subtracting the always-present '/HoudiniLayerInfo' prim.

SECURITY (no-file / no-code guarantee): NONE of these endpoints exposes a filesystem path, texture /
HDRI / IES / map path, save/output path, icon, or any script / callback / VEX / Python / command
parm. Every incidental file/script parm the probe found (componentgeometry.source / sourceproxy /
sourcesimproxy / icon, collection.icon, transformuv.map, componentgeometryvariants variant layer
dirs, prune vexpression target methods, etc.) is deliberately OMITTED from the curated param tables
below — those nodes are driven entirely by their SOP/stage inputs and by typed structural knobs.
There is no filesystem or code-execution surface reachable through this lane. File-I/O nodes
(volume, componentoutput, sopcreate, sopmodify, sublayer) are NOT wrapped here.
"""

from houdini_executor.server import (
    endpoint, resolve_node, clamp, stage_context,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared helpers (probe-safe: never invent a parm) ──────────────────────────────────────────────




def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token: set the token directly (validated against the live token set)."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _set_tuple(node, parm, values, lo, hi, cast):
    """Set a plain tuple parm (t/r/s/shear/p/...) with per-component clamp. Probe-safe."""
    pt = node.parmTuple(parm)
    if pt is None or not isinstance(values, (list, tuple)):
        return False
    try:
        out = []
        for x in values:
            c = clamp(cast(x), lo, hi)
            out.append(int(c) if cast is int else float(c))
        pt.set(tuple(out))
        return True
    except Exception:  # noqa: BLE001
        return False


def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  m=index-menu(tokens)  ms=string-menu(tokens)
       fv=float-tuple[min,max]  iv=int-tuple[min,max]."""
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
        elif kind == "m":
            _menu_set(node, parm, str(v), extra)
        elif kind == "ms":
            _str_menu_set(node, parm, str(v), extra)
        elif kind == "fv":
            _set_tuple(node, parm, v, extra[0], extra[1], float)
        elif kind == "iv":
            _set_tuple(node, parm, v, extra[0], extra[1], int)


def _stage_node(ntype, name=None, after=None):
    """Create a LOP `ntype` in /stage, wired after `after` (a LOP path) if given, else a fresh
    generator in /stage. (Idiom copied verbatim from usd.py::_stage_node.)"""
    if after:
        src = resolve_node(after)
        parent = src.parent()
        n = parent.createNode(ntype, name) if name else parent.createNode(ntype)
        n.setInput(0, src)
    else:
        stage = stage_context()
        n = stage.createNode(ntype, name) if name else stage.createNode(ntype)
    n.moveToGoodPosition()
    return n


def _set_common(n, params, path=False, pattern=False):
    """Set the deterministic prim locators a node supports: primpath (creators) and/or primpattern
    (operators; falls back to the multiparm `primpattern1` on nodes that only expose the indexed
    form). Each caller declares which locators the wrapped node actually carries, so the handler only
    ever consumes the keys its ToolDef exposes."""
    if path and params.get("primpath"):
        _try_set(n, "primpath", str(params["primpath"]))
    if pattern and params.get("primpattern"):
        if n.parm("primpattern") is not None:
            _try_set(n, "primpattern", str(params["primpattern"]))
        else:
            _try_set(n, "primpattern1", str(params["primpattern"]))


def _wire(n, idx, path):
    """Wire an extra LOP input at slot `idx` from a LOP path (probe-safe)."""
    if path:
        try:
            n.setInput(idx, resolve_node(str(path)))
            return True
        except Exception:  # noqa: BLE001
            return False
    return False


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [s.strip() for s in str(v).split(",") if s.strip()]


def _finish(n):
    """Cook, then read the authored prims back off the stage (proof-of-cook), minus HoudiniLayerInfo.
    A USD stage is built incrementally — a node still missing a required input (instancer needs
    prototypes, componentmaterial needs materials) legitimately fails to cook; both n.cook() and
    n.stage() can raise hou.OperationFailed, so BOTH are guarded → return cooked:false + errors rather
    than crashing the caller (mirrors _finish_op / _cooked)."""
    out = {"node": n.path()}
    try:
        n.cook(force=True)
    except Exception:  # noqa: BLE001 — cook failure (e.g. missing input) surfaced via errors below
        pass
    try:
        st = n.stage()
        out["prims"] = [str(p.GetPath()) for p in st.Traverse()
                        if str(p.GetPath()) != "/HoudiniLayerInfo"]
        out["cooked"] = True
    except Exception:  # noqa: BLE001 — node built but stage didn't cook (missing input)
        out["cooked"] = False
    try:
        errs = list(n.errors())
        if errs:
            out["errors"] = errs
    except Exception:  # noqa: BLE001
        pass
    return out


# ── shared range hints ────────────────────────────────────────────────────────────────────────────
# The probe's per-parm ranges are UI-SLIDER hints, not hard limits. Positional / size / scale clamps
# below are widened to practical bounds so the tools are usable (a layout tool clamped to +/-1 unit is
# broken); every ENUM token set and DEFAULT is preserved exactly as probed.
_POS = (-1.0e6, 1.0e6)      # translate / pivot / bbox-center
_ROT = (-3600.0, 3600.0)    # rotate (deg)
_SCL = (-1.0e4, 1.0e4)      # per-axis scale (negative allowed for mirroring)
_SHR = (-10.0, 10.0)        # shear
_SIZE = (0.0, 1.0e6)        # size / radius / height / length
_USCALE = (0.0, 1.0e4)      # uniform scale / globalscale (probe min 0)

_XORD = ["srt", "str", "rst", "rts", "tsr", "trs"]
_RORD = ["xyz", "xzy", "yxz", "yzx", "zxy", "zyx"]
_CREATEPRIMS = ["off", "on", "forceedit"]
_AXIS = ["X", "Y", "Z"]

# reusable transform fragments (only include on nodes whose probe actually carries the parm)
_TRS = [("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL),
        ("shear", "shear", "fv", _SHR)]
_TRS_FULL = _TRS + [("scale", "scale", "f", _USCALE), ("p", "p", "fv", _POS)]


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# PRIM CREATION  (generators; `input` optional Input Stage)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
_CUBE = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
         ("computeextents", "computeextents", "b", None), ("size", "size", "f", _SIZE),
         ("doubleSided", "doubleSided", "b", None)] + _TRS


@endpoint("usd_prim_cube")
def usd_prim_cube(params):
    """Create a USD Cube prim on the stage (cube LOP). primpath = destination; size, transform
    (t/r/s/shear), primcount, primkind. Generator; `input` (opt) layers onto an upstream stage."""
    n = _stage_node("cube", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _CUBE)
    return _finish(n)


_CONE = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
         ("computeextents", "computeextents", "b", None), ("axis", "axis", "ms", _AXIS),
         ("height", "height", "f", _SIZE), ("radius", "radius", "f", _SIZE),
         ("doubleSided", "doubleSided", "b", None),
         ("t", "t", "fv", _POS), ("r", "r", "fv", _ROT)]


@endpoint("usd_prim_cone")
def usd_prim_cone(params):
    """Create a USD Cone prim (cone LOP). primpath, axis (X|Y|Z), height, radius, transform."""
    n = _stage_node("cone", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _CONE)
    return _finish(n)


_CYLINDER = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
             ("computeextents", "computeextents", "b", None), ("axis", "axis", "ms", _AXIS),
             ("height", "height", "f", _SIZE), ("radiusBottom", "radiusBottom", "f", _SIZE),
             ("radiusTop", "radiusTop", "f", _SIZE), ("doubleSided", "doubleSided", "b", None),
             ("t", "t", "fv", _POS)]


@endpoint("usd_prim_cylinder")
def usd_prim_cylinder(params):
    """Create a USD Cylinder prim (cylinder::2.0 LOP). primpath, axis, height, radiusBottom/Top."""
    n = _stage_node("cylinder::2.0", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _CYLINDER)
    return _finish(n)


_SPHERE = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
           ("computeextents", "computeextents", "b", None), ("radius", "radius", "f", _SIZE),
           ("doubleSided", "doubleSided", "b", None)] + _TRS


@endpoint("usd_prim_sphere")
def usd_prim_sphere(params):
    """Create a USD Sphere prim (sphere LOP). primpath, radius, transform (t/r/s/shear)."""
    n = _stage_node("sphere", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _SPHERE)
    return _finish(n)


_CAPSULE = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
            ("computeextents", "computeextents", "b", None), ("axis", "axis", "ms", _AXIS),
            ("height", "height", "f", _SIZE), ("radiusBottom", "radiusBottom", "f", _SIZE),
            ("radiusTop", "radiusTop", "f", _SIZE), ("doubleSided", "doubleSided", "b", None),
            ("t", "t", "fv", _POS)]


@endpoint("usd_prim_capsule")
def usd_prim_capsule(params):
    """Create a USD Capsule prim (capsule::2.0 LOP). primpath, axis, height, radiusBottom/Top."""
    n = _stage_node("capsule::2.0", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _CAPSULE)
    return _finish(n)


_MESH = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
         ("subdivisionScheme", "subdivisionScheme", "ms", ["catmullClark", "loop", "bilinear", "none"]),
         ("triangleSubdivisionRule", "triangleSubdivisionRule", "ms", ["catmullClark", "smooth"]),
         ("faceVaryingLinearInterpolation", "faceVaryingLinearInterpolation", "ms",
          ["all", "none", "boundaries", "cornersOnly", "cornersPlus1", "cornersPlus2"]),
         ("interpolateBoundary", "interpolateBoundary", "ms", ["none", "edgeAndCorner", "edgeOnly"]),
         ("orientation", "orientation", "ms", ["rightHanded", "leftHanded"]),
         ("doubleSided", "doubleSided", "b", None), ("t", "t", "fv", _POS)]


@endpoint("usd_prim_mesh")
def usd_prim_mesh(params):
    """Create an empty USD Mesh prim + subdivision scheme metadata (mesh LOP). primpath,
    subdivisionScheme, faceVarying / boundary interpolation, orientation."""
    n = _stage_node("mesh", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _MESH)
    return _finish(n)


_POINTS = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
           ("doubleSided", "doubleSided", "b", None)] + _TRS_FULL


@endpoint("usd_prim_points")
def usd_prim_points(params):
    """Create a USD Points prim (points LOP). primpath, transform (t/r/s/shear/scale/p)."""
    n = _stage_node("points", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _POINTS)
    return _finish(n)


_BASISCURVES = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
                ("type", "type", "ms", ["linear", "cubic"]),
                ("basis", "basis", "ms", ["bezier", "bspline", "catmullRom"]),
                ("wrap", "wrap", "ms", ["nonperiodic", "periodic", "pinned"]),
                ("doubleSided", "doubleSided", "b", None),
                ("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL)]


@endpoint("usd_prim_basiscurves")
def usd_prim_basiscurves(params):
    """Create a USD BasisCurves prim (basiscurves LOP). primpath, type (linear|cubic), basis, wrap."""
    n = _stage_node("basiscurves", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _BASISCURVES)
    return _finish(n)


_HERMITECURVES = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
                  ("doubleSided", "doubleSided", "b", None)] + _TRS_FULL


@endpoint("usd_prim_hermitecurves")
def usd_prim_hermitecurves(params):
    """Create a USD HermiteCurves prim (hermitecurves LOP). primpath, transform."""
    n = _stage_node("hermitecurves", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _HERMITECURVES)
    return _finish(n)


_PRIMITIVE = [("primkind", "primkind", "s", None), ("parentprimtype", "parentprimtype", "s", None),
              ("primtype", "primtype", "s", None), ("specifier", "specifier", "s", None)]


@endpoint("usd_prim_primitive")
def usd_prim_primitive(params):
    """Create a single generic USD prim of any schema type (primitive LOP) — the escape hatch for
    prim types without a dedicated tool. primpath, primtype (e.g. UsdGeomXform), parentprimtype,
    specifier (def|over|class)."""
    n = _stage_node("primitive", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _PRIMITIVE)
    return _finish(n)


_INSTANCER = [
    ("primkind", "primkind", "s", None),
    ("method", "method", "ms", ["pointinstancer", "instanceablerefprims", "refprims",
                                 "instanceableinheritprims", "inheritprims",
                                 "instanceablespecializeprims", "specializeprims"]),
    ("transformsourcemode", "transformsourcemode", "ms", ["intsop", "extsop", "prims", "points"]),
    ("prunemode", "prunemode", "ms", ["none", "delete", "visibility"]),
    ("protoreftype", "protoreftype", "ms", ["prim", "inherit", "specialize"]),
    ("handlemissingprototypes", "handlemissingprototypes", "ms", ["error", "warn"]),
    ("protoindexsrc", "protoindexsrc", "ms", ["random", "index", "indexattr", "nameattr", "pathattr"]),
    ("setextents", "setextents", "b", None), ("setorient", "setorient", "b", None),
    ("setscale", "setscale", "b", None), ("hidesourceprims", "hidesourceprims", "b", None),
    ("usenameattrib", "usenameattrib", "b", None), ("pruneamount", "pruneamount", "f", (0.0, 1.0)),
]


@endpoint("usd_instancer")
def usd_instancer(params):
    """Build a USD PointInstancer (or reference-based instances) on the stage (instancer LOP).
    primpath, method, protoindexsrc, prune mode/amount, set-orient/scale/extents. `prototypes`
    (opt LOP path) wires the prototype-source stage (2nd input). `input` (opt) = Input Stage."""
    n = _stage_node("instancer", params.get("name"), params.get("input"))
    _wire(n, 1, params.get("prototypes"))
    _set_common(n, params, path=True)
    _apply(n, params, _INSTANCER)
    return _finish(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# COMPONENT / LAYOUT / STRUCTURE
# ══════════════════════════════════════════════════════════════════════════════════════════════════
_COMPGEO = [
    ("sourceusdrefprim", "sourceusdrefprim", "ms", ["automaticPrim", "defaultPrim", ""]),
    ("topologyhandling", "topologyhandling", "ms", ["animated", "static", "none"]),
    ("authortimesamples", "authortimesamples", "ms", ["never", "auto", "always"]),
    ("packedhandling", "packedhandling", "ms",
     ["xforms", "pointinstancer", "nativeinstances", "unpack"]),
    ("bindmaterials", "bindmaterials", "ms", ["nobind", "createbind"]),
    ("drawmode", "drawmode", "ms", ["origin", "bounds", "cards", "default", "inherited"]),
    ("prefixpartitionsubsets", "prefixpartitionsubsets", "b", None),
    ("translateuvtost", "translateuvtost", "b", None),
    ("polygonsassubd", "polygonsassubd", "b", None),
]


@endpoint("usd_component_geometry")
def usd_component_geometry(params):
    """Create a componentgeometry LOP — the render/proxy/simproxy component container driven by its
    internal SOP subnet (NO file params: source/sourceproxy/sourcesimproxy/icon are deliberately
    excluded; feed geometry through the node's SOP network instead). Structural knobs only:
    topology/time-sample handling, packed handling, material binding, draw mode."""
    n = _stage_node("componentgeometry", params.get("name"))  # 0 inputs by design
    _apply(n, params, _COMPGEO)
    return _finish(n)


_COMPGEOVARIANTS = [
    ("variantset", "variantset", "s", None), ("variantprefix", "variantprefix", "s", None),
    ("variantname", "variantname", "s", None),
    ("variantcount", "variantcount", "i", (1, 100)),
    ("setcurrentselection", "setcurrentselection", "b", None),
]


@endpoint("usd_component_geometry_variants")
def usd_component_geometry_variants(params):
    """Pack several input stages into a variant set on a component (componentgeometryvariants LOP).
    `input` = Input Stage (variant 0); `sources` (opt list of LOP paths) wire the additional variant
    inputs. variantset, variantname, variantcount, setcurrentselection."""
    n = _stage_node("componentgeometryvariants", params.get("name"), params.get("input"))
    for i, src in enumerate(_as_list(params.get("sources")), start=1):
        _wire(n, i, src)
    _apply(n, params, _COMPGEOVARIANTS)
    return _finish(n)


_COMPMATERIAL = [
    ("variantset", "variantset", "s", None), ("variantname", "variantname", "s", None),
    ("root", "root", "s", None),
    ("autoroot", "autoroot", "b", None), ("simpleparms", "simpleparms", "b", None),
]


@endpoint("usd_component_material")
def usd_component_material(params):
    """Bind materials to a component and (optionally) build a material variant set (componentmaterial
    LOP). Operator: `input` = Input Stage (required); `materials` (opt LOP path) = the Materials 2nd
    input. primpattern selects the bound geometry; variantset/variantname/root/autoroot."""
    n = _stage_node("componentmaterial", params.get("name"), after=params["input"])
    _wire(n, 1, params.get("materials"))
    _set_common(n, params, pattern=True)
    _apply(n, params, _COMPMATERIAL)
    return _finish(n)


_LAYOUT = [
    ("method", "method", "ms", ["pointinstancer", "instanceablerefprims", "refprims",
                                "instanceableinheritprims", "inheritprims",
                                "instanceablespecializeprims", "specializeprims"]),
    ("localxform", "localxform", "b", None),
] + _TRS_FULL + [("pr", "pr", "fv", _POS), ("globalscale", "globalscale", "f", _USCALE)]


@endpoint("usd_layout")
def usd_layout(params):
    """Scatter/place instances of a prototype prim on the stage (layout LOP). primpath (new instancer
    prim), primpattern (prototype), method, transform (t/r/s/shear/scale/p/pr), globalscale.
    Generator; `input` (opt) = Input Stage."""
    n = _stage_node("layout", params.get("name"), params.get("input"))
    _set_common(n, params, path=True, pattern=True)
    _apply(n, params, _LAYOUT)
    return _finish(n)


_SCENEIMPORT = [
    ("filter", "filter", "ms", ["!!OBJ!!", "!!OBJ/LIGHT!!", "!!OBJ/CAMERA!!", "!!OBJ/GEOMETRY!!"]),
    ("packedhandling", "packedhandling", "ms",
     ["xforms", "pointinstancer", "nativeinstances", "unpack"]),
    ("kindschema", "kindschema", "ms", ["none", "component", "nestedgroup", "nestedassembly"]),
    ("authortimesamples", "authortimesamples", "ms", ["never", "auto", "always"]),
    ("topologyhandling", "topologyhandling", "ms", ["animated", "static", "none"]),
    ("importobjects", "importobjects", "b", None),
    ("importalltimesamples", "importalltimesamples", "b", None),
    ("substeps", "substeps", "i", (1, 100)), ("frange", "frange", "iv", (0, 1000000)),
]


@endpoint("usd_scene_import")
def usd_scene_import(params):
    """Import /obj scene objects (geo/lights/cameras) onto the stage (sceneimport::2.0 LOP). Data-only:
    the `filter` bundle selects which /obj nodes to import (no file path). packedhandling, kindschema,
    time-sample handling, frange. Generator; `input` (opt) = Input Stage."""
    n = _stage_node("sceneimport::2.0", params.get("name"), params.get("input"))
    _apply(n, params, _SCENEIMPORT)
    return _finish(n)


_GRAFTSTAGES = [
    ("destpath", "destpath", "s", None), ("primkind", "primkind", "s", None),
    ("makeuniquepaths", "makeuniquepaths", "b", None),
    ("parentprimtype", "parentprimtype", "s", None), ("specifier", "specifier", "s", None),
]


@endpoint("usd_graft_stages")
def usd_graft_stages(params):
    """Graft another stage's subtree under a destination prim (graftstages LOP). `input` (opt) = base
    Input Stage; `source` (opt LOP path) = the stage to copy in (2nd input). destpath (destination
    parent), primkind, makeuniquepaths, parentprimtype, specifier."""
    n = _stage_node("graftstages", params.get("name"), params.get("input"))
    _wire(n, 1, params.get("source"))
    _set_common(n, params, path=True)
    _apply(n, params, _GRAFTSTAGES)
    return _finish(n)


_GRAFTBRANCHES = [
    ("frameoffsetmode", "frameoffsetmode", "ms", ["match", "offset", "both"]),
    ("frameoffset", "frameoffset", "f", (-100000.0, 100000.0)),
    ("makeuniquepaths", "makeuniquepaths", "b", None), ("destasparent", "destasparent", "b", None),
    ("parentprimtype", "parentprimtype", "s", None), ("specifier", "specifier", "s", None),
    ("src_prim", "srcprimpath1", "s", None), ("dst_prim", "dstprimpath1", "s", None),
]


@endpoint("usd_graft_branches")
def usd_graft_branches(params):
    """Graft branches of a source stage onto destination prims, keeping position/material
    (graftbranches LOP). `input` (opt) = base stage; `source` (opt LOP path) = source for grafting
    (2nd input). src_prim/dst_prim (first branch), frameoffsetmode/frameoffset, destasparent."""
    n = _stage_node("graftbranches", params.get("name"), params.get("input"))
    _wire(n, 1, params.get("source"))
    _set_common(n, params, path=True)
    _apply(n, params, _GRAFTBRANCHES)
    return _finish(n)


_RESTRUCTURE = [
    ("flatteninput", "flatteninput", "b", None), ("createparentprim", "createparentprim", "b", None),
    ("removereferences", "removereferences", "b", None), ("removepayloads", "removepayloads", "b", None),
    ("removeinherits", "removeinherits", "b", None), ("removespecializes", "removespecializes", "b", None),
    ("primnewparent", "primnewparent", "s", None), ("parentprimtype", "parentprimtype", "s", None),
    ("parentspecifier", "parentspecifier", "s", None),
    ("primoldname", "primoldname", "s", None), ("primnewname", "primnewname", "s", None),
]


@endpoint("usd_restructure_scenegraph")
def usd_restructure_scenegraph(params):
    """Reparent / rename prims and strip composition arcs (restructurescenegraph LOP). Operator:
    `input` required. primpattern selects; primnewparent + parentprimtype (reparent), primoldname /
    primnewname (rename), remove references/payloads/inherits/specializes."""
    n = _stage_node("restructurescenegraph", params.get("name"), after=params["input"])
    _set_common(n, params, pattern=True)
    _apply(n, params, _RESTRUCTURE)
    return _finish(n)


_SPLITSCENE = [("flatteninput", "flatteninput", "b", None),
               ("common_primpattern", "common_primpattern", "s", None)]


@endpoint("usd_split_scene")
def usd_split_scene(params):
    """Split the stage into a selected branch and the remainder (splitscene LOP). Operator: `input`
    required. primpattern = the branch to isolate; common_primpattern; flatteninput."""
    n = _stage_node("splitscene", params.get("name"), after=params["input"])
    _set_common(n, params, pattern=True)
    _apply(n, params, _SPLITSCENE)
    return _finish(n)


_ISOLATESCENE = [
    ("mode", "mode", "ms", ["payload", "populationmask", "visibility"]),
    ("maskedpayloads", "maskedpayloads", "b", None), ("newlayerforedits", "newlayerforedits", "b", None),
    ("camera", "camera", "s", None), ("excludepattern", "excludepattern", "s", None),
]


@endpoint("usd_isolate_scene")
def usd_isolate_scene(params):
    """Isolate part of the stage for faster iteration via payload/population-mask/visibility
    (isolatescene LOP). Operator: `input` required. primpattern = what to keep; mode, camera,
    excludepattern."""
    n = _stage_node("isolatescene", params.get("name"), after=params["input"])
    _set_common(n, params, pattern=True)
    _apply(n, params, _ISOLATESCENE)
    return _finish(n)


_SCOPE = [("primkind", "primkind", "s", None), ("primcount", "primcount", "i", (0, 1000)),
          ("primtype", "primtype", "s", None), ("specifier", "specifier", "s", None),
          ("classancestor", "classancestor", "s", None),
          ("parentprimtype", "parentprimtype", "s", None)]


@endpoint("usd_scope")
def usd_scope(params):
    """Create a Scope (grouping) prim, optionally reparenting matched prims under it (scope LOP).
    primpath (new scope), primpattern (prims to move), primtype, specifier, parentprimtype.
    Generator; `input` (opt) = Input Stage."""
    n = _stage_node("scope", params.get("name"), params.get("input"))
    _set_common(n, params, path=True, pattern=True)
    _apply(n, params, _SCOPE)
    return _finish(n)


_COLLECTION = [
    ("defaultprimpath", "defaultprimpath", "s", None),
    ("collection_name", "collectionname1", "s", None),
    ("include_pattern", "includepattern1", "s", None),
    ("exclude_pattern", "excludepattern1", "s", None),
    ("expansionrule", "expansionrule1", "s", None),
    ("createprimitive", "createprimitive", "b", None),
    ("ispathexpression", "ispathexpression1", "b", None),
    ("allowinstanceproxies", "allowinstanceproxies1", "b", None),
    ("doexclusions", "doexclusions1", "b", None),
]


@endpoint("usd_collection")
def usd_collection(params):
    """Author a USD collection (named set of prims) on the stage (collection::2.0 LOP; icon file param
    excluded). defaultprimpath (where the collection prim lives), collection_name, include_pattern /
    exclude_pattern, expansionrule, ispathexpression. Generator; `input` (opt) = Input Stage."""
    n = _stage_node("collection::2.0", params.get("name"), params.get("input"))
    _apply(n, params, _COLLECTION)
    return _finish(n)


_PRUNE = [
    ("primpattern", "primpattern1", "s", None),
    ("targetmethod", "targetmethod1", "ms",
     ["primpattern", "bbox", "primtype", "primkind", "primpurpose"]),
    ("method", "method", "ms", ["deactivate", "makeinvisible"]),
    ("pruneunselected", "pruneunselected", "b", None), ("createasovers", "createasovers", "b", None),
]


@endpoint("usd_prune")
def usd_prune(params):
    """Deactivate or hide prims on the stage (prune LOP). primpattern = target prims; method
    (deactivate|makeinvisible), targetmethod, pruneunselected, createasovers. Generator; `input`
    (opt) = Input Stage. (The `vexpression` target method is excluded — no code surface.)"""
    n = _stage_node("prune", params.get("name"), params.get("input"))
    _apply(n, params, _PRUNE)
    return _finish(n)


_SPLITPRIM = [
    ("nurbscurvehandling", "nurbscurvehandling", "ms",
     ["basiscurves", "pinnedbasiscurves", "nurbscurves"]),
    ("nurbssurfhandling", "nurbssurfhandling", "ms", ["meshes", "nurbspatches"]),
    ("kindschema", "kindschema", "ms", ["none", "component", "nestedgroup", "nestedassembly"]),
    ("authortimesamples", "authortimesamples", "ms", ["never", "auto", "always"]),
    ("topologyhandling", "topologyhandling", "ms", ["animated", "static", "none"]),
    ("importtime", "importtime", "f", (0.0, 1.0e6)),
    ("polygonsassubd", "polygonsassubd", "b", None),
]


@endpoint("usd_split_primitive")
def usd_split_primitive(params):
    """Split composed prims into separately-editable prims (splitprimitive LOP). Operator: `input`
    required. NURBS/curve handling, kindschema, time-sample handling, polygonsassubd."""
    n = _stage_node("splitprimitive", params.get("name"), after=params["input"])
    _apply(n, params, _SPLITPRIM)
    return _finish(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# XFORM / INSTANCING
# ══════════════════════════════════════════════════════════════════════════════════════════════════
_XFORM = [
    ("xOrd", "xOrd", "m", _XORD), ("rOrd", "rOrd", "m", _RORD),
    ("xforminworldspace", "xforminworldspace", "b", None),
    ("setabsolutexform", "setabsolutexform", "b", None),
] + _TRS_FULL + [("pr", "pr", "fv", _POS), ("xformdescription", "xformdescription", "s", None)]


@endpoint("usd_xform")
def usd_xform(params):
    """Author a transform (xformOp) on matched prims (xform LOP). Operator: `input` required.
    primpattern, t/r/s/shear/scale/p/pr, xOrd/rOrd, xforminworldspace, setabsolutexform."""
    n = _stage_node("xform", params.get("name"), after=params["input"])
    _set_common(n, params, pattern=True)
    _apply(n, params, _XFORM)
    return _finish(n)


_CREATEXFORM = [
    ("primcount", "primcount", "i", (0, 1000)),
    ("xOrd", "xOrd", "m", _XORD), ("rOrd", "rOrd", "m", _RORD),
] + _TRS_FULL + [("pr", "pr", "fv", _POS)]


@endpoint("usd_create_xform")
def usd_create_xform(params):
    """Create a new Xform prim with a transform (createxform LOP). primpath (new xform), primpattern
    (optional reparent), t/r/s/shear/scale/p/pr, xOrd/rOrd. Generator; `input` (opt) = Input Stage."""
    n = _stage_node("createxform", params.get("name"), params.get("input"))
    _set_common(n, params, path=True, pattern=True)
    _apply(n, params, _CREATEXFORM)
    return _finish(n)


_POINTXFORM = [
    ("transformsourcemode", "transformsourcemode", "ms", ["intsop", "extsop"]),
    ("pointsoppath", "pointsoppath", "s", None), ("pointsopgroup", "pointsopgroup", "s", None),
    ("attribs", "attribs", "s", None),
]


@endpoint("usd_point_xform")
def usd_point_xform(params):
    """Transform prims by point attributes from a SOP (pointxform LOP). Operator: `input` required.
    transformsourcemode (intsop|extsop), pointsoppath (a SOP node path — not a file), pointsopgroup,
    attribs."""
    n = _stage_node("pointxform", params.get("name"), after=params["input"])
    _apply(n, params, _POINTXFORM)
    return _finish(n)


_TRANSFORMUV = [
    ("primpattern", "primpattern", "s", None),
    ("grouptype", "grouptype", "m", ["guess", "vertices", "edges", "points", "prims"]),
    ("xOrd", "xOrd", "m", _XORD), ("rOrd", "rOrd", "m", _RORD),
    ("type", "type", "m", ["linear", "quadratic", "cubic", "meta"]),
    ("metric", "metric", "m", ["uv", "uvw", "xyz"]),
    ("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL),
    ("shear", "shear", "fv", _SHR), ("p", "p", "fv", _POS), ("global", "global", "b", None),
]


@endpoint("usd_transform_uv")
def usd_transform_uv(params):
    """Transform UV/texture coordinates on matched prims (transformuv LOP; the `map` file param is
    excluded). Operator: `input` required. primpattern, grouptype, type, metric, t/r/s/shear/p."""
    n = _stage_node("transformuv", params.get("name"), after=params["input"])
    _apply(n, params, _TRANSFORMUV)
    return _finish(n)


_RESAMPLEXF = [("dt", "dt", "f", (0.001, 1.0)), ("includeoriginal", "includeoriginal", "b", None)]


@endpoint("usd_resample_transforms")
def usd_resample_transforms(params):
    """Resample animated transform time-samples at a fixed interval (resampletransforms LOP).
    Operator: `input` required. primpattern, dt (sample interval), includeoriginal."""
    n = _stage_node("resampletransforms", params.get("name"), after=params["input"])
    _set_common(n, params, pattern=True)
    _apply(n, params, _RESAMPLEXF)
    return _finish(n)


_DUPLICATE = [
    ("primkind", "primkind", "s", None),
    ("modifysource", "modifysource", "ms", ["deactivate", "hide", "class"]),
    ("xOrd", "xOrd", "m", _XORD), ("rOrd", "rOrd", "m", _RORD),
    ("ncy", "ncy", "i", (0, 1000)),
    ("separatesource", "separatesource", "b", None), ("makeinstances", "makeinstances", "b", None),
    ("xformcumulative", "xformcumulative", "b", None),
] + _TRS_FULL


@endpoint("usd_duplicate")
def usd_duplicate(params):
    """Duplicate matched prims N times, applying a cumulative transform per copy (duplicate LOP).
    Operator: `input` required. primpattern, ncy (copies), modifysource, makeinstances,
    xformcumulative, t/r/s/shear/scale/p."""
    n = _stage_node("duplicate", params.get("name"), after=params["input"])
    _apply(n, params, _DUPLICATE)
    return _finish(n)


_RETIME = [
    ("matchbyid", "matchbyid", "b", None), ("retimeprototypes", "retimeprototypes", "b", None),
    ("retimetransforms", "retimetransforms", "b", None), ("retimeprimvars", "retimeprimvars", "b", None),
    ("onlyretimed", "onlyretimed", "b", None), ("frame", "frame", "f", (-1.0e6, 1.0e6)),
    ("useframeoffsetattrib", "useframeoffsetattrib", "b", None),
    ("offset_variations", "offset_variations", "i", (1, 1000)),
    ("offset_range", "offset_range", "fv", (-100.0, 100.0)),
    ("offset_seed", "offset_seed", "f", (0.0, 1.0)),
]


@endpoint("usd_retime_instances")
def usd_retime_instances(params):
    """Per-instance time offsets / retiming of a point instancer (retimeinstances LOP). Operator:
    `input` required. matchbyid, retime prototypes/transforms/primvars, frame, offset_variations,
    offset_range, offset_seed."""
    n = _stage_node("retimeinstances", params.get("name"), after=params["input"])
    _apply(n, params, _RETIME)
    return _finish(n)


_EXTRACT = [
    ("method", "method", "ms", ["byframe", "bytime"]),
    ("useprimname", "useprimname", "b", None), ("flattenhierarchy", "flattenhierarchy", "b", None),
    ("instanceable", "instanceable", "b", None), ("bindmaterials", "bindmaterials", "b", None),
    ("deactivate", "deactivate", "b", None), ("integerframes", "integerframes", "b", None),
    ("frame", "frame", "f", (-1.0e6, 1.0e6)), ("time", "time", "f", (-1.0e6, 1.0e6)),
    ("nativeinstances", "nativeinstances", "s", None),
]


@endpoint("usd_extract_instances")
def usd_extract_instances(params):
    """Extract point-instancer instances into real prims (extractinstances LOP). Operator: `input`
    required. primpath (output root), method (byframe|bytime), frame/time, instanceable,
    flattenhierarchy, bindmaterials, nativeinstances (prim pattern)."""
    n = _stage_node("extractinstances", params.get("name"), after=params["input"])
    _set_common(n, params, path=True)
    _apply(n, params, _EXTRACT)
    return _finish(n)


_MERGEPI = [("instances", "instances", "s", None)]


@endpoint("usd_merge_point_instancers")
def usd_merge_point_instancers(params):
    """Merge several PointInstancers into one (mergepointinstancers LOP). Operator: `input` required.
    primpath (merged instancer), instances (prim pattern of the instancers to merge)."""
    n = _stage_node("mergepointinstancers", params.get("name"), after=params["input"])
    _set_common(n, params, path=True)
    _apply(n, params, _MERGEPI)
    return _finish(n)


_SPLITPI = [
    ("modifysource", "modifysource", "ms", ["deactivate", "hide"]),
    ("reftype", "reftype", "ms", ["prim", "copy"]),
    ("perprototype", "perprototype", "b", None),
    ("instancers", "instancers", "s", None), ("prototypes", "prototypes", "s", None),
    ("attribute", "attribute", "s", None),
]


@endpoint("usd_split_point_instancers")
def usd_split_point_instancers(params):
    """Split a PointInstancer into subsets by prototype/attribute (splitpointinstancers LOP).
    Operator: `input` required. instancers, prototypes, attribute, reftype (prim|copy),
    modifysource, perprototype."""
    n = _stage_node("splitpointinstancers", params.get("name"), after=params["input"])
    _apply(n, params, _SPLITPI)
    return _finish(n)


_MODIFYPI = [
    ("edittransform", "edittransform", "b", None), ("matchbyid", "matchbyid", "b", None),
    ("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL),
    ("shear", "shear", "fv", _SHR), ("scale", "scale", "f", _USCALE),
]


@endpoint("usd_modify_point_instances")
def usd_modify_point_instances(params):
    """Edit individual instances of a PointInstancer — per-instance transform (modifypointinstances
    LOP). Operator: `input` required. edittransform, matchbyid, t/r/s/shear/scale."""
    n = _stage_node("modifypointinstances", params.get("name"), after=params["input"])
    _apply(n, params, _MODIFYPI)
    return _finish(n)


_COORDSYS = [
    ("projection", "projection", "ms", ["perspective", "orthographic"]),
    ("xOrd", "xOrd", "m", _XORD), ("rOrd", "rOrd", "m", _RORD),
    ("createtarget", "createtarget", "b", None), ("ignoreparentxforms", "ignoreparentxforms", "b", None),
    ("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL),
    ("shear", "shear", "fv", _SHR), ("scale", "scale", "f", _USCALE),
]


@endpoint("usd_coordsys")
def usd_coordsys(params):
    """Bind a named coordinate system (coordsys) prim for texture / projection spaces (coordsys LOP).
    Operator: `input` required. primpath (coordsys prim), primpattern (prims to bind on), projection,
    createtarget, t/r/s/shear/scale."""
    n = _stage_node("coordsys", params.get("name"), after=params["input"])
    _set_common(n, params, path=True, pattern=True)
    _apply(n, params, _COORDSYS)
    return _finish(n)

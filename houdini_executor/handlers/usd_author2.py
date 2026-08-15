"""Solaris / LOP / USD *authoring* lane (materials, lights, variants/props/layer
editing, and shot/editorial). Fixed, typed, data-only LOP wrappers. Params + menu tokens verified
against live H21.0.671 via the LOP probe.

Idiom (copied verbatim from usd_author.py / usd.py): every node is created with
`_stage_node(ntype, name, after)` — a GENERATOR is born fresh in /stage via server.stage_context();
an OPERATOR is chained onto its `after` LOP with setInput(0, src). Multi-input nodes (addvariant,
shotswitch) wire their extra sources at the probed indices. Cook + stage readback is proven with the
GUARDED `_finish` (try/except broad Exception → returns cooked:false + errors; it never calls an
unguarded n.cook() and never references `hou`).

LIGHT ATTRIBUTES: distantlight/portallight expose their USD light attrs as name-mangled
`xn__inputs<attr>_<hash>` value parms plus an `xn__inputs<attr>_control_<hash>` companion, EXACTLY
like the wrapped light::2.0/domelight::3.0. We locate those parms by the stable readable needle (never
the build-fragile <hash>) via `_lop_author` / `_lop_author_tuple` (replicated verbatim from usd.py:
flip the _control companion to 'set', then set the value; guarded no-op when absent). geometrylight
exposes its attrs as PLAIN `lightAPI_*` parms, so those are set directly.

SECURITY (no-file / no-code guarantee): NONE of these endpoints exposes a filesystem path, texture /
HDRI / IES / card-texture / dome-light-texture path, save/output path, layer file path, image, icon,
resolver-context asset path, or any script / callback / VEX / Python / snippet parm. Every incidental
file/script parm the probe found is deliberately OMITTED from the curated tables below (per node:
materialvariation.image#; distantlight.xn__…shapingiesfile; drawmode.cardtexture*/domelighttexture;
configurestage.resolvercontextassetpath; editmaterialproperties.reffilepath;
shotsplit.targetlayer/parentlayer/newlayer; and materialvariation.usesnippet# / sourcemode# — the
snippet/expression code surface). USD scene-graph paths (primpath, primpattern, material/collection
prim paths, node paths) are DATA and are kept. The DEFERRED file-I/O nodes (materiallinker,
assignprototypes, assetreference, configurelayer, layerreplace, loadlayer, shotload, valueclip,
geometrysequence) are NOT wrapped here. There is no filesystem or code-execution surface in this lane.
"""

from houdini_executor.server import (
    endpoint, resolve_node, clamp, stage_context,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared helpers (probe-safe: never invent a parm) — copied verbatim from usd_author.py ──────────




def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token: set the token directly (validated against the live token set)."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _set_tuple(node, parm, values, lo, hi, cast):
    """Set a plain tuple parm (t/r/s/shear/min/max/...) with per-component clamp. Probe-safe."""
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
    generator in /stage. (Idiom copied verbatim from usd_author.py::_stage_node.)"""
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
    (operators; falls back to the multiparm `primpattern1`). Each caller declares which locators the
    wrapped node actually carries, so the handler only ever consumes the keys its ToolDef exposes."""
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
    A USD stage is built incrementally — a node still missing a required input legitimately fails to
    cook; both n.cook() and n.stage() can raise, so BOTH are guarded → return cooked:false + errors
    rather than crashing the caller. (Reused unchanged from usd_author.py::_finish.)"""
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


# ── mangled (xn__...) USD light-attr authoring — replicated verbatim from usd.py ───────────────────
# Solaris light parms that back a USD attribute are name-mangled `xn__inputs<attr>_<hash>` plus a
# companion `xn__inputs<attr>_control_<hash>` string parm gating whether the attribute is authored
# ('set'=author). The <hash> is BUILD-FRAGILE, so parms are located by the stable readable middle
# (the `needle`), never the mangled name. All setters are guarded no-ops when the parm is absent.
def _lop_val_parm(node, needle):
    """Return the VALUE parm whose name embeds `needle` (skipping its _control companion), or None."""
    key = needle.lower() + "_"
    ck = needle.lower() + "_control"
    for p in node.parms():
        n = p.name().lower()
        if ck in n:
            continue
        if key in n:
            return p
    return None


def _lop_ctrl_parm(node, needle):
    """Return the `_control` companion parm for `needle`, or None."""
    ck = needle.lower() + "_control"
    for p in node.parms():
        if ck in p.name().lower():
            return p
    return None


def _lop_author(node, needle, value):
    """Author a mangled scalar/toggle/string USD parm: flip its _control to 'set', then set the
    value. Returns True iff the value parm was found and set. Guarded (never raises)."""
    vp = _lop_val_parm(node, needle)
    if vp is None:
        return False
    cp = _lop_ctrl_parm(node, needle)
    if cp is not None:
        try:
            cp.set("set")
        except Exception:  # noqa: BLE001
            pass
    try:
        vp.set(value)
        return True
    except Exception:  # noqa: BLE001
        return False


def _lop_author_tuple(node, needle, values):
    """Author a mangled tuple (e.g. color3f) USD parm: flip _control to 'set', then set the tuple."""
    cp = _lop_ctrl_parm(node, needle)
    if cp is not None:
        try:
            cp.set("set")
        except Exception:  # noqa: BLE001
            pass
    key = needle.lower() + "_"
    ck = needle.lower() + "_control"
    for pt in node.parmTuples():
        n = pt.name().lower()
        if ck in n:
            continue
        if key in n:
            try:
                pt.set(tuple(values))
                return True
            except Exception:  # noqa: BLE001
                return False
    return False


def _light_attrs(n, params):
    """Author the standard UsdLux light attributes (mangled xn__ needles) shared by distant/portal
    lights — same needles the wrapped usd_light uses. Every call is a guarded no-op if the attr is
    absent on this light type, so passing e.g. `angle` to a portal light simply does nothing."""
    if "intensity" in params:
        _lop_author(n, "inputsintensity", clamp(float(params["intensity"]), 0.0, 1e6))
    if "exposure" in params:
        _lop_author(n, "inputsexposure", clamp(float(params["exposure"]), -20.0, 20.0))
    c = params.get("color")
    if c and len(c) == 3:
        _lop_author_tuple(n, "inputscolor", [clamp(float(v), 0.0, 1.0) for v in c])
    if "diffuse" in params:
        _lop_author(n, "inputsdiffuse", clamp(float(params["diffuse"]), 0.0, 1e4))
    if "specular" in params:
        _lop_author(n, "inputsspecular", clamp(float(params["specular"]), 0.0, 1e4))
    if "normalize" in params:
        _lop_author(n, "inputsnormalize", bool(params["normalize"]))
    if params.get("enable_temperature"):
        _lop_author(n, "inputsenableColorTemperature", True)
    if "temperature" in params:
        _lop_author(n, "inputsenableColorTemperature", True)
        _lop_author(n, "inputscolorTemperature", clamp(float(params["temperature"]), 500.0, 100000.0))
    if "shadow_enable" in params:
        _lop_author(n, "inputsshadowenable", bool(params["shadow_enable"]))
    sc = params.get("shadow_color")
    if sc and len(sc) == 3:
        _lop_author_tuple(n, "inputsshadowcolor", [clamp(float(v), 0.0, 1.0) for v in sc])


# ── shared range hints (probe slider-ranges are UI hints, not hard limits; widened to practical
# bounds for positional/size/scale — every ENUM token set + DEFAULT preserved exactly as probed) ────
_POS = (-1.0e6, 1.0e6)      # translate / pivot
_ROT = (-3600.0, 3600.0)    # rotate (deg)
_SCL = (-1.0e4, 1.0e4)      # per-axis scale (negative allowed for mirroring)
_SHR = (-10.0, 10.0)        # shear
_USCALE = (0.0, 1.0e4)      # uniform scale
_COLOR = (0.0, 1.0)         # color3f component
_RESP = (0.0, 1.0e4)        # diffuse / specular response
_XORD = ["srt", "str", "rst", "rts", "tsr", "trs"]
_RORD = ["xyz", "xzy", "yxz", "yzx", "zxy", "zyx"]

_TRS = [("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL),
        ("shear", "shear", "fv", _SHR)]
_TRS_FULL = _TRS + [("scale", "scale", "f", _USCALE), ("p", "p", "fv", _POS),
                    ("pr", "pr", "fv", _POS)]


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# MATERIALS
# ══════════════════════════════════════════════════════════════════════════════════════════════════
_EDITMATERIAL = [
    ("referencerendervars", "referencerendervars", "b", None),
    ("usebasemat", "usebasemat1", "b", None),
    ("matpath", "matpath1", "s", None),
    ("basematpath", "basematpath1", "s", None),
]


@endpoint("usd_edit_material")
def usd_edit_material(params):
    """Open an existing USD material for editing / basing a new material on it (editmaterial LOP).
    matpath = the Material prim to edit; basematpath = the base material to reference; usebasemat
    toggles basing on it; referencerendervars pulls in render vars. Generator; `input` (opt) = Input
    Stage. (No shader-network / VOP node params exposed — pure structural material-edit authoring.)"""
    n = _stage_node("editmaterial", params.get("name"), params.get("input"))
    _apply(n, params, _EDITMATERIAL)
    return _finish(n)


_EDITMATPROPS = [
    ("primpath", "primpath", "s", None), ("primkind", "primkind", "s", None),
    ("reftype", "reftype", "ms", ["none", "reference", "inherit", "specialize", "reffile", "createclass"]),
    ("primtype", "primtype", "ms", ["", "UsdShadeMaterial", "UsdShadeShader", "UsdShadeNodeGraph"]),
    ("refparentmat", "refparentmat", "b", None), ("instanceable", "instanceable", "b", None),
    ("classancestor", "classancestor", "s", None), ("classprimpath", "classprimpath", "s", None),
    ("parentprimtype", "parentprimtype", "s", None),
]


@endpoint("usd_edit_material_properties")
def usd_edit_material_properties(params):
    """Author / edit properties on a material prim (editmaterialproperties LOP; the `reffilepath`
    file param is excluded). primpattern = target material(s), primpath = new material prim, reftype
    (composition arc), primtype (UsdShadeMaterial|Shader|NodeGraph), classancestor / classprimpath,
    parentprimtype. Generator; `input` (opt) = Input Stage."""
    n = _stage_node("editmaterialproperties", params.get("name"), params.get("input"))
    _set_common(n, params, pattern=True)
    _apply(n, params, _EDITMATPROPS)
    return _finish(n)


_MATVARIATION = [
    ("primitivetype", "primitivetype", "i", (0, 1)),
    ("importtime", "importtime", "f", (0.0, 1.0e6)),
    ("enable", "enable1", "b", None), ("matchbyid", "matchbyid1", "b", None),
    ("bool", "bool1", "b", None), ("int", "int1", "i", (-1000000, 1000000)),
    ("float", "float1", "f", (-1.0e9, 1.0e9)),
]


@endpoint("usd_material_variation")
def usd_material_variation(params):
    """Vary a bound material's shader parameters across instances / prims (materialvariation LOP; the
    `image#` texture-file param and the `usesnippet#`/`sourcemode#` code-snippet surface are excluded).
    Operator: `input` required. primitivetype (0|1), importtime, and the first variation's literal
    value (enable, matchbyid, bool, int, float). Data-only literal variation — no snippets, no maps."""
    n = _stage_node("materialvariation", params.get("name"), after=params["input"])
    _apply(n, params, _MATVARIATION)
    return _finish(n)


_UNASSIGNMAT = [
    ("action", "action1", "ms", ["all", "n"]),
    ("enable", "enable1", "b", None), ("nummat", "nummat1", "i", (0, 1000)),
    ("bindpurpose", "bindpurpose1", "s", None),
]


@endpoint("usd_unassign_material")
def usd_unassign_material(params):
    """Remove material bindings from matched prims (unassignmaterial LOP). primpattern = target prims;
    action (all = drop all bindings, n = drop N), nummat, bindpurpose (bind-purpose token to clear).
    Generator; `input` (opt) = Input Stage."""
    n = _stage_node("unassignmaterial", params.get("name"), params.get("input"))
    if params.get("primpattern"):
        _try_set(n, "primpattern1", str(params["primpattern"]))
    _apply(n, params, _UNASSIGNMAT)
    return _finish(n)


_VARYMATASSIGN = [
    ("bindpurpose", "bindpurpose", "ms", ["", "full", "preview"]),
    ("bindstrength", "bindstrength", "m",
     ["fallbackStrength", "strongerThanDescendants", "weakerThanDescendants"]),
    ("bindmethod", "bindmethod", "i", (0, 1)), ("method", "method", "i", (0, 2)),
    ("spatial_method", "spatial_method", "ms", ["byframe", "bytime"]),
    ("bindcollectionexpand", "bindcollectionexpand", "b", None),
    ("random_seed", "random_seed", "f", (0.0, 1.0e6)),
    ("spatial_frame", "spatial_frame", "f", (-1.0e6, 1.0e6)),
    ("integerframes", "integerframes", "b", None), ("time", "time", "f", (-1.0e6, 1.0e6)),
    ("spatial_cellfreq", "spatial_cellfreq", "fv", (0.0, 1.0e4)),
    ("spatial_celloffset", "spatial_celloffset", "fv", (-1.0e6, 1.0e6)),
    ("spatial_celljitter", "spatial_celljitter", "fv", (0.0, 1.0e4)),
    ("spatial_noisefreq", "spatial_noisefreq", "fv", (0.0, 1.0e4)),
    ("spatial_noiseamp", "spatial_noiseamp", "f", (0.0, 1.0e4)),
]


@endpoint("usd_vary_material_assignment")
def usd_vary_material_assignment(params):
    """Randomly / spatially vary which material is bound across prims (varymaterialassignment LOP).
    Operator: `input` required. bindpurpose/bindstrength/bindmethod, method (0=random,1=..),
    spatial_method (byframe|bytime), random_seed, and the spatial cell/noise frequency, offset,
    jitter, amplitude controls. Data-only."""
    n = _stage_node("varymaterialassignment", params.get("name"), after=params["input"])
    _apply(n, params, _VARYMATASSIGN)
    return _finish(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# LIGHTS  (generators; light attrs via the mangled xn__ needle idiom, except geometrylight = plain)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("usd_light_distant")
def usd_light_distant(params):
    """Create a UsdLux DistantLight (sun) on the stage (distantlight::2.0 LOP; the IES `shapingiesfile`
    file param is excluded). primpath = light prim; intensity, exposure, color=[r,g,b], angle (angular
    diameter deg → soft-shadow penumbra), diffuse, specular, normalize, enable_temperature +
    temperature (Kelvin), shadow_enable, shadow_color; distance (billboard distance). Light attrs are
    authored via the mangled xn__ needle idiom (guarded). Generator; `input` (opt) = Input Stage."""
    n = _stage_node("distantlight::2.0", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _light_attrs(n, params)
    if "angle" in params:
        _lop_author(n, "inputsangle", clamp(float(params["angle"]), 0.0, 360.0))
    if "distance" in params:
        _try_set(n, "distance", clamp(float(params["distance"]), 0.0, 1e9))
    return _finish(n)


_PORTAL_TRS = [("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL),
               ("shear", "shear", "fv", _SHR), ("scale", "scale", "f", _USCALE),
               ("p", "p", "fv", _POS), ("pr", "pr", "fv", _POS)]


@endpoint("usd_light_portal")
def usd_light_portal(params):
    """Create a UsdLux PortalLight — a dome-light portal that concentrates HDRI sampling through an
    opening (portallight LOP). primpath = light prim; the portal is positioned/sized entirely by its
    transform (t/r/s/shear/scale/p/pr) — the probe surfaces no light-attribute parms for this node, so
    none are exposed. Generator; `input` (opt) = Input Stage."""
    n = _stage_node("portallight", params.get("name"), params.get("input"))
    _set_common(n, params, path=True)
    _apply(n, params, _PORTAL_TRS)
    return _finish(n)


_GEOMLIGHT = [
    ("apischema", "apischema", "ms", ["LightAPI", "MeshLightAPI", "VolumeLightAPI"]),
    ("lightAPI_materialSyncMode", "lightAPI_materialSyncMode", "ms",
     ["materialGlowTintsLight", "independent", "noMaterialResponse"]),
    ("meshlightAPI_materialSyncMode", "meshlightAPI_materialSyncMode", "ms",
     ["materialGlowTintsLight", "independent", "noMaterialResponse"]),
    ("volumelightAPI_materialSyncMode", "volumelightAPI_materialSyncMode", "ms",
     ["materialGlowTintsLight", "independent", "noMaterialResponse"]),
    ("intensity", "lightAPI_intensity", "f", (0.0, 1.0e6)),
    ("exposure", "lightAPI_exposure", "f", (-20.0, 20.0)),
    ("color", "lightAPI_color", "fv", _COLOR),
    ("enable_temperature", "lightAPI_enableColorTemperature", "b", None),
    ("temperature", "lightAPI_colorTemperature", "f", (500.0, 100000.0)),
    ("normalize", "lightAPI_normalize", "b", None),
    ("diffuse", "lightAPI_diffuse", "f", _RESP),
    ("specular", "lightAPI_specular", "f", _RESP),
]


@endpoint("usd_light_geometry")
def usd_light_geometry(params):
    """Turn matched geometry into an emissive area light (geometrylight LOP). primpattern = the geo
    prim(s) to light-ify; apischema (LightAPI|MeshLightAPI|VolumeLightAPI) + the matching
    materialSyncMode; intensity, exposure, color=[r,g,b] (0..1), enable_temperature + temperature,
    normalize, diffuse, specular. These attrs are PLAIN `lightAPI_*` parms (set directly). Generator;
    `input` (opt) = Input Stage."""
    n = _stage_node("geometrylight", params.get("name"), params.get("input"))
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    _apply(n, params, _GEOMLIGHT)
    return _finish(n)


_LIGHTMIXER = [
    ("xOrd", "xOrd", "m", _XORD), ("rOrd", "rOrd", "m", _RORD),
    ("localxform", "localxform", "b", None),
    ("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL),
    ("shear", "shear", "fv", _SHR), ("scale", "scale", "f", _USCALE),
    ("p", "p", "fv", _POS), ("pr", "pr", "fv", _POS),
    ("collection_prim", "collection_prim_1", "s", None),
    ("collection_name", "collection_name_1", "s", None),
    ("collection_includes", "collection_includes_1", "s", None),
    ("collection_excludes", "collection_excludes_1", "s", None),
]


@endpoint("usd_light_mixer")
def usd_light_mixer(params):
    """Group and transform lights via light collections for look-dev mixing (lightmixer LOP).
    primpattern = lights to mix; transform (t/r/s/shear/scale/p/pr) + localxform; the first light
    collection row: collection_prim / collection_name / collection_includes / collection_excludes
    (all USD prim-path patterns). Generator; `input` (opt) = Input Stage."""
    n = _stage_node("lightmixer", params.get("name"), params.get("input"))
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    _apply(n, params, _LIGHTMIXER)
    return _finish(n)


_SHADOWCATCHER = [
    ("blocklights", "blocklights", "b", None), ("replacematerial", "replacematerial", "b", None),
    ("matpath", "matpath", "s", None),
]


@endpoint("usd_shadow_catcher")
def usd_shadow_catcher(params):
    """Turn matched prims into shadow-catcher surfaces for compositing CG over a plate (shadowcatcher
    LOP). primpattern = prims to catch shadows on; blocklights, replacematerial, matpath (the
    shadow-catcher Material PRIM path — USD scene-graph data, default /materials/shadow_catcher_mtl).
    Generator; `input` (opt) = Input Stage."""
    n = _stage_node("shadowcatcher", params.get("name"), params.get("input"))
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    _apply(n, params, _SHADOWCATCHER)
    return _finish(n)


_LIGHTFILTERLIB = [
    ("allowparmanim", "allowparmanim", "b", None),
    ("parentprimtype", "parentprimtype", "s", None),
    ("filterpathprefix", "filterpathprefix", "s", None),
    ("containerpath", "containerpath", "s", None),
    ("enable", "enable1", "b", None), ("assign", "assign1", "b", None),
    ("filterpath", "filterpath1", "s", None), ("lightpath", "lightpath1", "s", None),
]


@endpoint("usd_light_filter_library")
def usd_light_filter_library(params):
    """Author a library of light-filter prims and (optionally) assign them to lights
    (lightfilterlibrary LOP). parentprimtype, filterpathprefix / containerpath (USD prim-path roots),
    allowparmanim; first filter row: enable, assign, filterpath (filter prim path), lightpath (light
    prim path to assign it to). VOP filter-net refs are omitted. Generator; `input` (opt) = Input
    Stage."""
    n = _stage_node("lightfilterlibrary", params.get("name"), params.get("input"))
    _apply(n, params, _LIGHTFILTERLIB)
    return _finish(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# VARIANTS / PROPS / LAYER EDITING
# ══════════════════════════════════════════════════════════════════════════════════════════════════
_ADDVARIANT = [
    ("primpath", "primpath", "s", None), ("primkind", "primkind", "s", None),
    ("variantsetstrength", "variantsetstrength", "ms",
     ["prependfront", "prependback", "appendfront", "appendback"]),
    ("sourceprim", "sourceprim", "b", None), ("checkopinions", "checkopinions", "b", None),
    ("createoptionsblock", "createoptionsblock", "b", None),
    ("setvariantselection", "setvariantselection", "b", None),
    ("sourceprimpath", "sourceprimpath", "s", None), ("parentprimtype", "parentprimtype", "s", None),
    ("variantset", "variantset", "s", None), ("variantprimpath", "variantprimpath", "s", None),
    ("variantname", "variantname", "s", None),
]


@endpoint("usd_add_variant")
def usd_add_variant(params):
    """Pack one or more input stages into a variant set on a prim (addvariant LOP). primpath = prim to
    carry the variant set; variantset (name), variantname, variantprimpath, variantsetstrength,
    setvariantselection, sourceprim/sourceprimpath, parentprimtype. Generator; `input` = Input Stage
    (variant 0); `sources` (opt list of LOP paths) wire the additional 'Copy Into Variant' inputs."""
    n = _stage_node("addvariant", params.get("name"), params.get("input"))
    for i, src in enumerate(_as_list(params.get("sources")), start=1):
        _wire(n, i, src)
    _apply(n, params, _ADDVARIANT)
    return _finish(n)


_EXPLOREVARIANTS = [
    ("primpath", "primpath", "s", None),
    ("mode", "mode", "i", (0, 2)), ("duplicate_layout", "duplicate_layout", "i", (0, 2)),
    ("explore_layout", "explore_layout", "i", (0, 1)), ("justify", "justify", "i", (0, 2)),
    ("donested", "donested", "b", None), ("includenosel", "includenosel", "b", None),
    ("flatten", "flatten", "b", None), ("createreferences", "createreferences", "b", None),
    ("flatteninputlayers", "flatteninputlayers", "b", None),
    ("includeinputstage", "includeinputstage", "b", None),
    ("usebounds", "usebounds", "b", None), ("useextentshint", "useextentshint", "b", None),
    ("spacing", "spacing", "f", (0.0, 1.0e6)),
]


@endpoint("usd_explore_variants")
def usd_explore_variants(params):
    """Lay out every variant of a variant set side-by-side for review (explorevariants::2.0 LOP).
    Operator: `input` required. primpattern = prim(s) whose variants to explore; primpath (layout
    root), mode, duplicate_layout / explore_layout / justify, spacing, donested, flatten,
    createreferences, usebounds / useextentshint."""
    n = _stage_node("explorevariants::2.0", params.get("name"), after=params["input"])
    _set_common(n, params, pattern=True)
    _apply(n, params, _EXPLOREVARIANTS)
    return _finish(n)


_CREATELOD = [
    ("primpath", "primpath", "s", None), ("primkind", "primkind", "s", None),
    ("sourceprim", "sourceprim", "b", None), ("checkopinions", "checkopinions", "b", None),
    ("idoffset", "idoffset", "i", (0, 1000)), ("usecustvarnames", "usecustvarnames", "b", None),
    ("displayvariant", "displayvariant", "b", None),
    ("sourceprimpath", "sourceprimpath", "s", None), ("parentprimtype", "parentprimtype", "s", None),
    ("variantset", "variantset", "s", None),
    ("lodpercent", "lodpercent1", "f", (0.0, 100.0)),
    ("preservequads", "preservequads1", "b", None),
    ("boundaryweight", "boundaryweight1", "f", (0.1, 100.0)),
]


@endpoint("usd_create_lod")
def usd_create_lod(params):
    """Build polyreduced level-of-detail variants of a prim (createlod LOP). Operator: `input`
    required. primpath = prim to LOD; variantset (name), idoffset, usecustvarnames, displayvariant,
    sourceprim/sourceprimpath, parentprimtype; the first LOD level: lodpercent (0..100 reduction),
    preservequads, boundaryweight."""
    n = _stage_node("createlod", params.get("name"), after=params["input"])
    _apply(n, params, _CREATELOD)
    return _finish(n)


_AUTOSELECTLOD = [
    ("camera", "camera", "s", None), ("variantset", "variantset1", "s", None),
    ("thresh_dist", "thresh_dist1", "f", (0.0, 1.0e6)), ("uselod", "uselod1", "b", None),
    ("speclod", "speclod1", "s", None),
]


@endpoint("usd_auto_select_lod")
def usd_auto_select_lod(params):
    """Auto-select an LOD variant by camera distance (autoselectlod LOP). Operator: `input` required.
    primpattern = prims to switch; camera (camera prim path), variantset; the first threshold row:
    thresh_dist (switch distance), uselod, speclod (variant name)."""
    n = _stage_node("autoselectlod", params.get("name"), after=params["input"])
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    _apply(n, params, _AUTOSELECTLOD)
    return _finish(n)


_DRAWMODE = [
    ("extents", "extents", "ms", ["missing", "all"]),
    ("cardgeometry", "cardgeometry", "ms", ["cross", "box", "fromTexture"]),
    ("setkind", "setkind", "b", None), ("fixkindhierarchy", "fixkindhierarchy", "b", None),
    ("setextents", "setextents", "b", None),
    ("setapplydrawmode", "setapplydrawmode", "b", None), ("applydrawmode", "applydrawmode", "b", None),
    ("setdrawmode", "setdrawmode", "b", None), ("setdrawmodecolor", "setdrawmodecolor", "b", None),
    ("drawmodecolor", "drawmodecolor", "fv", _COLOR),
    ("setcardgeometry", "setcardgeometry", "b", None),
]


@endpoint("usd_draw_mode")
def usd_draw_mode(params):
    """Set the USD imaging draw mode (bounds / cards / origin proxy) on matched prims (drawmode LOP;
    all card-texture and dome-light-texture file params are excluded). primpattern = target prims;
    extents, cardgeometry (cross|box|fromTexture), setextents, applydrawmode (+setapplydrawmode),
    setdrawmode, drawmodecolor=[r,g,b] (+setdrawmodecolor), setkind, fixkindhierarchy, setcardgeometry.
    Generator; `input` (opt) = Input Stage."""
    n = _stage_node("drawmode", params.get("name"), params.get("input"))
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    _apply(n, params, _DRAWMODE)
    return _finish(n)


_CONFIGUREPROP = [
    ("variability", "variability", "ms", ["varying", "uniform"]),
    ("setvariability", "setvariability", "b", None), ("setcolorspace", "setcolorspace", "b", None),
    ("setinterpolation", "setinterpolation", "b", None),
    ("setelementsize", "setelementsize", "b", None), ("elementsize", "elementsize", "i", (0, 1000000)),
]


@endpoint("usd_configure_property")
def usd_configure_property(params):
    """Configure metadata on matched USD properties/attributes (configureproperty LOP). primpattern =
    target properties; variability (varying|uniform) + setvariability, setcolorspace, setinterpolation,
    setelementsize + elementsize. Generator; `input` (opt) = Input Stage."""
    n = _stage_node("configureproperty", params.get("name"), params.get("input"))
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    _apply(n, params, _CONFIGUREPROP)
    return _finish(n)


_CONFIGURESTAGE = [
    ("editpopulate", "editpopulate", "ms", ["nochange", "addremove", "set", "setall"]),
    ("editload", "editload", "ms", ["nochange", "addremove", "set", "setall"]),
    ("editmute", "editmute", "ms", ["nochange", "addremove", "set", "setnone"]),
    ("populatepattern", "populatepattern", "s", None),
    ("unpopulatepattern", "unpopulatepattern", "s", None),
    ("populatepaths", "populatepaths", "s", None), ("unpopulatepaths", "unpopulatepaths", "s", None),
    ("loadpattern", "loadpattern", "s", None), ("unloadpattern", "unloadpattern", "s", None),
]


@endpoint("usd_configure_stage")
def usd_configure_stage(params):
    """Configure stage-level population / load / mute rules (configurestage LOP; the
    `resolvercontextassetpath` file param is excluded). editpopulate / editload / editmute modes, plus
    the populate/unpopulate patterns & paths and load/unload patterns (all USD prim-path patterns).
    Generator; `input` (opt) = Input Stage."""
    n = _stage_node("configurestage", params.get("name"), params.get("input"))
    _apply(n, params, _CONFIGURESTAGE)
    return _finish(n)


_EDITPROPS = [
    ("primpath", "primpath", "s", None), ("primkind", "primkind", "s", None),
    ("createprims", "createprims", "m", ["off", "on", "forceedit"]),
    ("primcount", "primcount", "i", (0, 1000)), ("computeextents", "computeextents", "b", None),
    ("primtype", "primtype", "s", None), ("specifier", "specifier", "s", None),
    ("classancestor", "classancestor", "s", None), ("parentprimtype", "parentprimtype", "s", None),
]


@endpoint("usd_edit_properties")
def usd_edit_properties(params):
    """Create or edit prims and their properties in bulk (editproperties LOP). primpattern = prims to
    edit; primpath (new prim), primkind, createprims (off|on|forceedit), primcount, computeextents,
    primtype, specifier (def|over|class), classancestor, parentprimtype. Generator; `input` (opt) =
    Input Stage."""
    n = _stage_node("editproperties", params.get("name"), params.get("input"))
    _set_common(n, params, pattern=True)
    _apply(n, params, _EDITPROPS)
    return _finish(n)


_STOREPARMS = [
    ("enable", "enable1", "b", None), ("name_key", "name1", "s", None),
    ("valuestring", "valuestring1", "s", None),
]


@endpoint("usd_store_parameter_values")
def usd_store_parameter_values(params):
    """Store named parameter values as stage data for downstream reuse (storeparametervalues LOP).
    The first stored value: name_key (variable name), valuestring (its string value), enable. Generator;
    `input` (opt) = Input Stage."""
    n = _stage_node("storeparametervalues", params.get("name"), params.get("input"))
    _apply(n, params, _STOREPARMS)
    return _finish(n)


_SETEXTENTS = [
    ("mode", "mode", "i", (0, 2)),
    ("min", "min", "fv", _POS), ("max", "max", "fv", _POS),
    ("t", "t", "fv", _POS), ("s", "s", "fv", _SCL),
    ("worldspacebounds", "worldspacebounds", "b", None), ("primitives", "primitives", "s", None),
]


@endpoint("usd_set_extents")
def usd_set_extents(params):
    """Author / recompute the extent (bounding-box) hint on matched prims (setextents LOP). Operator:
    `input` required. mode (0=compute,1=..), min/max (explicit bbox), t/s (adjust), worldspacebounds,
    primitives (prim pattern, default %payload)."""
    n = _stage_node("setextents", params.get("name"), after=params["input"])
    _apply(n, params, _SETEXTENTS)
    return _finish(n)


_EDITXFORM = [
    ("xOrd", "xOrd", "m", _XORD), ("rOrd", "rOrd", "m", _RORD),
    ("localxform", "localxform", "b", None),
    ("t", "t", "fv", _POS), ("r", "r", "fv", _ROT), ("s", "s", "fv", _SCL),
    ("shear", "shear", "fv", _SHR), ("scale", "scale", "f", _USCALE),
    ("p", "p", "fv", _POS), ("pr", "pr", "fv", _POS),
    ("physprimpattern", "physprimpattern", "s", None),
    ("bypassprimpattern", "bypassprimpattern", "s", None),
    ("xformdescription", "xformdescription", "s", None),
]


@endpoint("usd_edit_xform")
def usd_edit_xform(params):
    """Interactively-authored transform edit on matched prims (edit LOP; the interactive `delta` blob
    is not exposed). primpattern = prims to transform; t/r/s/shear/scale/p/pr, xOrd/rOrd, localxform,
    xformdescription, physprimpattern / bypassprimpattern. Generator; `input` (opt) = Input Stage."""
    n = _stage_node("edit", params.get("name"), params.get("input"))
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    _apply(n, params, _EDITXFORM)
    return _finish(n)


@endpoint("usd_layer_break")
def usd_layer_break(params):
    """Insert a layer break so downstream edits go onto a fresh, independent layer (layerbreak LOP) —
    the 'start a clean edit layer here' marker. No parameters. Generator; `input` (opt) = Input
    Stage."""
    n = _stage_node("layerbreak", params.get("name"), params.get("input"))
    return _finish(n)


_SETVARIANT = [
    ("variantset", "variantset1", "s", None), ("variantname", "variantname1", "s", None),
    ("enable", "enable1", "b", None),
]


@endpoint("usd_set_variant")
def usd_set_variant(params):
    """Select which variant of a variant set is active on matched prims (setvariant LOP). Operator:
    `input` required. primpattern = prims carrying the variant set; variantset (set name), variantname
    (variant to select), enable."""
    n = _stage_node("setvariant", params.get("name"), after=params["input"])
    if params.get("primpattern"):
        _try_set(n, "primpattern1", str(params["primpattern"]))
    _apply(n, params, _SETVARIANT)
    return _finish(n)


_COPYPROPERTY = [
    ("separatedestprimpattern", "separatedestprimpattern", "b", None),
    ("destprimpattern", "destprimpattern", "s", None),
    ("sourceprop", "sourceprop1", "s", None), ("destprop", "destprop1", "s", None),
    ("copymetadata", "copymetadata1", "b", None),
]


@endpoint("usd_copy_property")
def usd_copy_property(params):
    """Copy a property/attribute from source prims to destination prims (copyproperty LOP). Operator:
    `input` required. primpattern = source prims; destprimpattern (+separatedestprimpattern), and the
    first copy row: sourceprop, destprop, copymetadata."""
    n = _stage_node("copyproperty", params.get("name"), after=params["input"])
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    _apply(n, params, _COPYPROPERTY)
    return _finish(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SHOT / SEQUENCE / EDITORIAL
# ══════════════════════════════════════════════════════════════════════════════════════════════════
_SHOTSPLIT = [
    ("enabletargetlayer", "enabletargetlayer", "b", None),
    ("clearsourcelayer", "clearsourcelayer", "b", None),
    ("createnewlayer", "createnewlayer", "b", None),
    ("newlayerindex", "newlayerindex", "i", (0, 1000)),
    ("outputshotpattern", "outputshotpattern1", "s", None),
    ("defaultshot", "defaultshot1", "s", None), ("description", "description1", "s", None),
]


@endpoint("usd_shot_split")
def usd_shot_split(params):
    """Split the stage's edits into per-shot layers for editorial hand-off (shotsplit LOP). Operator:
    `input` required. enabletargetlayer, clearsourcelayer, createnewlayer + newlayerindex; the first
    shot row: outputshotpattern, defaultshot, description. (Layer *file-path* params — targetlayer /
    parentlayer / newlayer — are excluded to preserve the no-file guarantee.)"""
    n = _stage_node("shotsplit", params.get("name"), after=params["input"])
    _apply(n, params, _SHOTSPLIT)
    return _finish(n)


@endpoint("usd_shot_switch")
def usd_shot_switch(params):
    """Switch between several candidate input stages by index for shot assembly (shotswitch LOP).
    `select` = which input to pass through (int); shotsplitpath = a shotsplit LOP/prim path to drive
    the selection from (data, not a file). `sources` (opt list of LOP paths) wire the candidate input
    stages at slots 0+. Generator."""
    srcs = _as_list(params.get("sources"))
    n = _stage_node("shotswitch", params.get("name"))
    for i, src in enumerate(srcs):
        _wire(n, i, src)
    if "select" in params:
        _try_set(n, "input", int(clamp(int(params["select"]), 0, 1000000)))
    if params.get("shotsplitpath"):
        _try_set(n, "shotsplitpath", str(params["shotsplitpath"]))
    return _finish(n)

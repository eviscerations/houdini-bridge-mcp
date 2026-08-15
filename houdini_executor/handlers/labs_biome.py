"""SideFX Labs — World Building / Biome (data-only handlers).

The Labs Biome system is a TIGHTLY-COUPLED config pipeline, not a set of independent filters. The
canonical chain (verified live on H21.0.671):

  biome_define (climate profile per biome, chainable source)
        └─> biome_definitions_file (serialize the biome library to JSON)
  biome_plant_define (plant species tolerances) ─> biome_plant_definitions_file
  biome_profile  (holds the combined biome profile; 0 inputs / 0 outputs — a leaf writer)
        │
  biome_initialize (terrain + biome-region source  ->  Terrain out0 / Regions out1)
        └─> biome_region_assign (regions -> Biome Regions / Guide Geometry)
        └─> biome_attributes_evolve (evolve temperature/precip/soil across the terrain)
        └─> biome_attributes_to_terrain (bake the biome attributes to heightfield layers)
  biome_curve_setup / biome_curve_label (author + tag biome region CURVES by climate)
  region_assignment_subutil / convert_regions_to_curves_subutil (internal region plumbing utils)

The already-shipped `biome_scatter` (instance.py, labs::biome_plant_scatter::1.0) is the SCATTERER
that consumes this config — it is NOT re-wrapped here.

SECURITY (data-only boundary):
  * Every file-path parm (biomeprofile / biomelib / librarypath / filename / imginput / PSD file /
    plant variants dir) is routed through confined_path() so any read/write stays inside the working
    dir — set ONLY when the caller supplies one; otherwise the HDA's own $HIP default is untouched.
  * The definitions-file / profile nodes serialize small JSON to the confined path on cook (a data
    serializer, not a render) — the write target is confined, nothing else is written.
  * All NodeReference slots (copinput / coppath / objpath# / shop_materialpath / variantsmergepath /
    pathtobiomes / meshvariant#) are node paths, not files — left unset.
  * No node here exposes a code/callback/VEX parm; buttons/ramps/visualize-only toggles are skipped.
Every other exposed parm is a scalar / toggle / ordered-menu / plain name-or-glob token (sanitized).
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────
def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)




def _try_set_tuple(node, parm, values):
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(values))
        return True
    except Exception:
        return False


def _menu_idx_set(node, parm, token, tokens):
    """Ordered menu whose NATIVE tokens are numeric ('0','1',...): set by the friendly-label index."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(tokens.index(token))
        return True
    except Exception:
        return False


def _menu_tok_set(node, parm, token, tokens):
    """Ordered menu whose native tokens are meaningful strings: set by the token string directly."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _safe_token(v):
    """Sanitize a name / layer / attribute / glob token: reject path separators, parent refs and
    drive letters so a plain token can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("name/token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


def _set_file(node, parm, value):
    """Confine a caller-supplied file path to the working dir, then set it. Returns the resolved
    path (or None when the caller passed nothing — the HDA keeps its own default)."""
    if value in (None, ""):
        return None
    resolved = confined_path(value)
    _try_set(node, parm, resolved)
    return resolved


def _source_or_chain(params, ntype):
    """Biome sources accept an OPTIONAL input-0 merge stream. With `input` -> chain after it
    (child_after); otherwise build a fresh /obj geo named `name`. Returns (geo_or_None, node)."""
    if params.get("input"):
        return None, child_after(params["input"], ntype, params.get("name"))
    geo = _fresh_geo(params["name"])
    return geo, geo.createNode(ntype)


def _finish(geo, n):
    """Common return: cook-count from the node's geometry; set display flags on a fresh source geo."""
    if geo is not None:
        n.setDisplayFlag(True)
        n.setRenderFlag(True)
        geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
        geo.layoutChildren()
    try:
        g = n.geometry()
        pts, prims = len(g.points()), len(g.prims())
    except Exception:
        pts, prims = None, None
    out = {"node": geo.path() if geo is not None else n.parent().path(),
           "sop": n.path(), "points": pts, "prims": prims}
    return out


# ── ordered-menu token tuples ────────────────────────────────────────────────────────────────────
# INDEX menus (native tokens are '0','1',... -> our friendly tuple aligns to the stored index)
_TERRAINTYPE = ("heightfield", "mesh", "image")
_BIOMEINPUT = ("image", "psd", "curves", "hf_layers", "mesh")
_INPUTTYPE = ("image", "psd", "curves", "hf_layers", "mesh")
_IMAGETYPE = ("file", "cop")
_OUTPUTMODE = ("guide", "hf_layers")
_SRC_DEPTH = ("single", "multi")
_SAMPLERES = ("source", "specified")
_CURVEGROUP = ("connected", "multiparm", "primid")
_LAYERHIER = ("dominant", "manual")
_DISPLAY = ("input", "temperature", "precipitation", "soil", "biome_color")
_AUTOREMAP = ("realworld", "normalize", "manual")
_USEDEFAULT = ("transparent", "fill")
_PLANTTYPE = ("tree", "shrub")
_AUTOFILL = ("directory", "mergepath")
_FILEMODE = ("write", "read")
_CREATE_BIOME = ("geometry", "biome_define_nodes")
_CREATE_PLANT = ("geometry", "plant_define_nodes")
_BIOMEDEFTYPE = ("file", "operator")
_IMGSRC = ("file", "cop")
# TOKEN menus (native tokens are meaningful strings -> set by the token)
_ORIENT = ("xy", "yz", "zx")
_SAMPLING = ("center", "corner")
_MONOOP = ("lum", "ntsclum", "average", "max", "min", "magnitude",
           "hue", "saturation", "red", "green", "blue")
_CSPACE = ("auto", "linear")
_DIVMODE = ("maxaxis", "size")
_NOISE_BASIS = ("sine", "perlin", "pperlin", "simplex", "sparse", "flow", "pflow",
                "worleyFA", "worleyFB", "mworleyFA", "mworleyFB",
                "cworleyFA", "cworleyFB", "alligator")
_FRACTAL = ("none", "fBm", "mfT", "hmfT")
_LAYERMODE = ("replace", "add", "subtract", "diff", "multiply", "max", "min", "blend")


def _set_color(n, params, parm, prefix):
    """Optional RGB visualization color from <prefix>_r/g/b -> the given rgb tuple parm."""
    keys = [prefix + "_r", prefix + "_g", prefix + "_b"]
    if any(k in params for k in keys):
        cur = n.parmTuple(parm).eval() if n.parmTuple(parm) else (1.0, 1.0, 1.0)
        vec = [clamp(float(params.get(keys[i], cur[i])), 0.0, 1.0) for i in range(3)]
        _try_set_tuple(n, parm, vec)


# ══ Definition sources ═════════════════════════════════════════════════════════════════════════

# ── 1. biome_define (source/chain; in0 opt merge) ────────────────────────────────────────────────
@endpoint("biome_define")
def biome_define(params):
    """SideFX Labs Biome Define (labs::biome_define::1.0) — defines ONE biome's climate profile
    (name + average temperature/precipitation + soil flag) as a config point-stream. Chain several by
    passing `input` (the previous biome_define output) so they merge into one biome library; with no
    `input` it builds a fresh /obj geo. Feed the merged output into biome_definitions_file (to persist)
    or biome_initialize (to drive region generation). Data-only (climate scalars + a name token)."""
    geo, n = _source_or_chain(params, "labs::biome_define::1.0")
    if "biomename" in params:
        _try_set(n, "biomename", _safe_token(params["biomename"]))
    if "tempaverage" in params:
        _try_set(n, "tempaverage", clamp(float(params["tempaverage"]), -100.0, 100.0))
    if "precaverage" in params:
        _try_set(n, "precaverage", clamp(float(params["precaverage"]), 0.0, 100000.0))
    if "soil" in params:
        _try_set(n, "soil", bool(params["soil"]))
    _set_color(n, params, "biomecolor", "color")
    return _finish(geo, n)


# ── 2. biome_plant_define (source/chain; in0 opt merge) ───────────────────────────────────────────
@endpoint("biome_plant_define")
def biome_plant_define(params):
    """SideFX Labs Biome Plant Define (labs::biome_plant_define::1.0) — defines ONE plant species and
    its climate tolerances (lower/preferred/upper temperature & precipitation), habit (Tree/Shrub),
    bounds/trunk radius, scale and max density — the record biome_scatter reads to place vegetation.
    Chain several via `input`. SECURITY: the plant-variant DIRECTORY (`variantsdir`) is confined; the
    file glob (`pattern`) is a sanitized token; the material / merge-path / mesh-variant NodeReference
    slots are node paths, left unset."""
    geo, n = _source_or_chain(params, "labs::biome_plant_define::1.0")
    if "plantname" in params:
        _try_set(n, "plantname", _safe_token(params["plantname"]))
    _set_color(n, params, "plantcolor", "color")
    for key, lo, hi in (("templower", -100.0, 100.0), ("temppref", -100.0, 100.0),
                        ("tempupper", -100.0, 100.0), ("preclower", 0.0, 100000.0),
                        ("precpref", 0.0, 100000.0), ("precupper", 0.0, 100000.0),
                        ("densitymax", 0.0, 100.0), ("radius", 1e-3, 1000.0),
                        ("trunkradius", 1e-3, 1000.0), ("scalemult", 1e-3, 1000.0),
                        ("hardiness", 0.0, 1.0), ("normterrain", 0.0, 1.0),
                        ("randomizeyaw", 0.0, 360.0), ("variantspacing", 0.0, 1000.0)):
        if key in params:
            _try_set(n, key, clamp(float(params[key]), lo, hi))
    if "type" in params:
        _menu_idx_set(n, "type", str(params["type"]), _PLANTTYPE)
    if "randscale" in params:
        _try_set(n, "randscale", bool(params["randscale"]))
    if "recursive" in params:
        _try_set(n, "recursive", bool(params["recursive"]))
    if "enginepaths" in params:
        _try_set(n, "enginepaths", bool(params["enginepaths"]))
    if "autofillmode" in params:
        _menu_idx_set(n, "autofillmode", str(params["autofillmode"]), _AUTOFILL)
    if "pattern" in params:
        _try_set(n, "pattern", _safe_token(params["pattern"]))
    _set_file(n, "variantsdir", params.get("variantsdir"))
    return _finish(geo, n)


# ── 3. biome_definitions_file (source/chain; in0 opt) — serialize biome library ───────────────────
@endpoint("biome_definitions_file")
def biome_definitions_file(params):
    """SideFX Labs Biome Definitions File (labs::biome_definitions_file::1.0) — serializes a biome
    library to / from JSON. `mode` write persists the incoming biome_define stream (`input`, input 0)
    to `librarypath`; read loads it back as geometry (or, with `create`=biome_define_nodes, rebuilds
    the nodes). SECURITY: `librarypath` is confined to the working dir (a small JSON serializer, not a
    render) — set only when supplied; otherwise the HDA keeps its $HIP default."""
    geo, n = _source_or_chain(params, "labs::biome_definitions_file::1.0")
    if "mode" in params:
        _menu_idx_set(n, "mode", str(params["mode"]), _FILEMODE)
    if "jsongeo" in params:
        _try_set(n, "jsongeo", bool(params["jsongeo"]))
    if "create" in params:
        _menu_idx_set(n, "create", str(params["create"]), _CREATE_BIOME)
    out = _set_file(n, "librarypath", params.get("librarypath"))
    res = _finish(geo, n)
    res["librarypath"] = out
    return res


# ── 4. biome_plant_definitions_file (source/chain; in0 opt) — serialize plant library ─────────────
@endpoint("biome_plant_definitions_file")
def biome_plant_definitions_file(params):
    """SideFX Labs Biome Plant Definitions File (labs::biome_plant_definitions_file::1.0) — serializes
    the plant-species library to / from JSON (mirror of biome_definitions_file for plant_define).
    `mode` write persists the incoming biome_plant_define stream (`input`) to `librarypath`; read
    loads it back. SECURITY: `librarypath` is confined to the working dir (JSON serializer, not a
    render) — set only when supplied."""
    geo, n = _source_or_chain(params, "labs::biome_plant_definitions_file::1.0")
    if "mode" in params:
        _menu_idx_set(n, "mode", str(params["mode"]), _FILEMODE)
    if "jsongeo" in params:
        _try_set(n, "jsongeo", bool(params["jsongeo"]))
    if "create" in params:
        _menu_idx_set(n, "create", str(params["create"]), _CREATE_PLANT)
    out = _set_file(n, "librarypath", params.get("librarypath"))
    res = _finish(geo, n)
    res["librarypath"] = out
    return res


# ── 5. biome_profile (source; 0 inputs / 0 outputs) — combined profile holder/writer ──────────────
@endpoint("biome_profile")
def biome_profile(params):
    """SideFX Labs Biome Profile (labs::biome_profile::1.0) — holds/writes the combined biome PROFILE
    (the `biomeprofile.json` that biome_initialize / region_assign / curve nodes consume) with per-biome
    average temperature & precipitation. This node has NO inputs and NO outputs (a leaf config writer);
    it is built and configured, then cooks to author the profile. Pass `biome_name`/`avg_temp`/
    `avg_precip` to seed the first profile row. SECURITY: `biomeprofile` is confined to the working dir
    (set only when supplied)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::biome_profile::1.0")
    out = _set_file(n, "biomeprofile", params.get("biomeprofile"))
    if any(k in params for k in ("biome_name", "avg_temp", "avg_precip")):
        _try_set(n, "biomename", 1)  # ensure one multiparm row exists
        if "biome_name" in params:
            _try_set(n, "biomename1", _safe_token(params["biome_name"]))
        if "avg_temp" in params:
            _try_set(n, "avgtemp1", clamp(float(params["avg_temp"]), -100.0, 100.0))
        if "avg_precip" in params:
            _try_set(n, "avgprecip1", clamp(float(params["avg_precip"]), 0.0, 100000.0))
    geo.layoutChildren()
    errs = []
    try:
        n.cook(force=True)
        errs = list(n.errors())
    except Exception as exc:  # noqa: BLE001
        errs = [str(exc)]
    return {"node": geo.path(), "sop": n.path(), "biomeprofile": out,
            "outputs": 0, "errors": errs,
            "note": "biome_profile is a 0-output leaf writer; it authors the profile on cook"}


# ══ Terrain + region pipeline ══════════════════════════════════════════════════════════════════

# ── 6. biome_initialize (source/chain; in0 terrain, in1 biome-region source) ──────────────────────
@endpoint("biome_initialize")
def biome_initialize(params):
    """SideFX Labs Biome Initialize (labs::biome_initialize::1.0) — the pipeline entry: takes a terrain
    and a biome-region source and outputs the prepared Terrain (output 0) + Biome Regions (output 1).
    Wiring: pass `terrain` (a heightfield / mesh) as input 0; `terraintype` selects how it is read
    (heightfield / mesh / image). `biomeinput` selects the region source — use `hf_layers` (region
    masks already on the heightfield) or `mesh` to avoid any external image/PSD file. `numcolors` /
    `strength` / `extweight` / `iterations` drive region extraction + smoothing. SECURITY: the four
    file surfaces (`biomeprofile`, heightfield image `filename`, `imginput`, PSD `file`) are each
    confined to the working dir; the COP NodeReference (`copinput`) is left unset."""
    if params.get("terrain") or params.get("input"):
        src = params.get("terrain") or params.get("input")
        n = child_after(src, "labs::biome_initialize::1.0", params.get("name"))
        geo = None
    else:
        geo = _fresh_geo(params["name"])
        n = geo.createNode("labs::biome_initialize::1.0")
    if params.get("biome"):
        bridge_input(n, params["biome"], index=1, name_hint="biome")
    if "terraintype" in params:
        _menu_idx_set(n, "terraintype", str(params["terraintype"]), _TERRAINTYPE)
    if "biomeinput" in params:
        _menu_idx_set(n, "biomeinput", str(params["biomeinput"]), _BIOMEINPUT)
    for key, lo, hi in (("gridspacing", 1e-3, 1000.0), ("gridspacing_mesh", 1e-3, 1000.0),
                        ("heightscale", 0.0, 1e6), ("strength", 0.0, 1000.0),
                        ("extweight", 0.0, 1000.0), ("uniformscale", 1e-3, 1e6),
                        ("clampmin", -1e6, 1e6), ("clampmax", -1e6, 1e6)):
        if key in params:
            _try_set(n, key, clamp(float(params[key]), lo, hi))
    for key, lo, hi in (("numcolors", 1, 256), ("iterations", 0, 100)):
        if key in params:
            _try_set(n, key, int(clamp(int(params[key]), lo, hi)))
    for key in ("autosize", "clampmintoggle", "clampmaxtoggle", "imgmatchsize"):
        if key in params:
            _try_set(n, key, bool(params[key]))
    if "orient" in params:
        _menu_tok_set(n, "orient", str(params["orient"]), _ORIENT)
    if "sampling" in params:
        _menu_tok_set(n, "sampling", str(params["sampling"]), _SAMPLING)
    if "monoop" in params:
        _menu_tok_set(n, "monoop", str(params["monoop"]), _MONOOP)
    if "imagetype" in params:
        _menu_idx_set(n, "imagetype", str(params["imagetype"]), _IMAGETYPE)
    _set_file(n, "biomeprofile", params.get("biomeprofile"))
    _set_file(n, "filename", params.get("filename"))
    _set_file(n, "imginput", params.get("imginput"))
    _set_file(n, "file", params.get("psd_file"))
    return _finish(geo, n)


# ── 7. biome_region_assign (chain; in0 region source, in1 opt) ────────────────────────────────────
@endpoint("biome_region_assign")
def biome_region_assign(params):
    """SideFX Labs Biome Region Assign (labs::biome_region_assign::1.0) — assigns the biome regions of
    the incoming region source (`input`, input 0) against the biome library, emitting Biome Regions
    (output 0) + Guide Geometry (output 1). `inputtype` picks the region source (image / curves /
    hf_layers / mesh); for a self-contained cook feed a mesh whose regions carry a `name` prim
    attribute with `inputtype`=mesh + `attrname`=name, or heightfield layers with `inputtype`=hf_layers.
    `clustercount`/`clusteriter`/`refineclusters` control image k-means region extraction; `gridsamples`
    /`gridspacing`/`divisionmode` size the output heightfields. NOTE: non-empty output requires biome
    definitions matching the region names (the full biome_initialize -> region_assign workflow with a
    populated profile) — with no matching library it cooks clean but emits 0 regions. SECURITY: the
    definitions file (`biomelib`), the image (`imgfilepath`) and PSD (`file`) are confined; the COP /
    object NodeReferences (`coppath`, `objpath#`) are left unset."""
    n = child_after(params["input"], "labs::biome_region_assign::1.0", params.get("name"))
    if params.get("regions"):
        bridge_input(n, params["regions"], index=1, name_hint="regions")
    if "inputtype" in params:
        _menu_idx_set(n, "inputtype", str(params["inputtype"]), _INPUTTYPE)
    if "outputmode" in params:
        _menu_idx_set(n, "outputmode", str(params["outputmode"]), _OUTPUTMODE)
    if "src_depth" in params:
        _menu_idx_set(n, "src_depth", str(params["src_depth"]), _SRC_DEPTH)
    if "imgsrc" in params:
        _menu_idx_set(n, "imgsrc", str(params["imgsrc"]), _IMGSRC)
    if "sampleresmode" in params:
        _menu_idx_set(n, "sampleresmode", str(params["sampleresmode"]), _SAMPLERES)
    if "samplecspace" in params:
        _menu_tok_set(n, "samplecspace", str(params["samplecspace"]), _CSPACE)
    if "curvegrouping" in params:
        _menu_idx_set(n, "curvegrouping", str(params["curvegrouping"]), _CURVEGROUP)
    if "layerhierarchy" in params:
        _menu_idx_set(n, "layerhierarchy", str(params["layerhierarchy"]), _LAYERHIER)
    if "divisionmode" in params:
        _menu_tok_set(n, "divisionmode", str(params["divisionmode"]), _DIVMODE)
    for key, lo, hi in (("clustercount", 1, 256), ("clusteriter", 1, 1000),
                        ("refineiter", 0, 100), ("gridsamples", 8, 8192)):
        if key in params:
            _try_set(n, key, int(clamp(int(params[key]), lo, hi)))
    if "gridspacing" in params:
        _try_set(n, "gridspacing", clamp(float(params["gridspacing"]), 1e-3, 1000.0))
    for key in ("refineclusters", "definitionmatch", "resolveoverlaps", "resetimgparms"):
        if key in params:
            _try_set(n, key, bool(params[key]))
    if "curveidattrib" in params:
        _try_set(n, "curveidattrib", _safe_token(params["curveidattrib"]))
    if "attrname" in params:
        _try_set(n, "attrname", _safe_token(params["attrname"]))
    _set_file(n, "biomelib", params.get("biomelib"))
    _set_file(n, "imgfilepath", params.get("imgfilepath"))
    _set_file(n, "file", params.get("psd_file"))
    return _finish(n=n, geo=None)


# ── 8. biome_attributes_evolve (chain; in0 terrain, in1 opt) — the rich climate shaper ────────────
@endpoint("biome_attributes_evolve")
def biome_attributes_evolve(params):
    """SideFX Labs Biome Attributes Evolve (labs::biome_attributes_evolve::1.0) — evolves the climate
    attribute layers (temperature / precipitation / soil) across the incoming terrain (`input`, input 0)
    from physical rules: temperature drops with elevation (`lapserate`), precipitation is removed on the
    lee side of mountains (rain shadow: `removebydir` + `startxz` direction + `anglespread`), and soil is
    culled on cliffs (`removebyslope` + min/max slope) and by procedural noise (`removebynoise` + noise
    `basis`/`fractal`/`amp`/`elementsize`). `display` picks the visualization channel; `autoremap` the
    value range. Data-only (no file/code surface; ramps stay at HDA default)."""
    n = child_after(params["input"], "labs::biome_attributes_evolve::1.0", params.get("name"))
    if params.get("regions"):
        bridge_input(n, params["regions"], index=1, name_hint="regions")
    if "display" in params:
        _menu_idx_set(n, "display", str(params["display"]), _DISPLAY)
    if "autoremap" in params:
        _menu_idx_set(n, "autoremap", str(params["autoremap"]), _AUTOREMAP)
    for key in ("evolvetemp", "evolvetempxz", "removebyocclusion", "maskbyheight", "removebydir",
                "removebyslope", "removebyheight", "removebynoise", "enablemask"):
        if key in params:
            _try_set(n, key, bool(params[key]))
    for key, lo, hi in (("lapserate", -50.0, 50.0), ("goalangle", -360.0, 360.0),
                        ("anglespread", 0.0, 180.0), ("minslopeangle", 0.0, 90.0),
                        ("maxslopeangle", 0.0, 90.0), ("basesoil", 0.0, 1.0),
                        ("intensity", 0.0, 100.0), ("amp", 0.0, 1000.0),
                        ("elementsize", 1e-3, 10000.0), ("oct", 1.0, 16.0),
                        ("lac", 1e-3, 10.0), ("rough", 0.0, 2.0), ("blend", 0.0, 1.0)):
        if key in params:
            _try_set(n, key, clamp(float(params[key]), lo, hi))
    if "tempsiter" in params:
        _try_set(n, "tempsiter", int(clamp(int(params["tempsiter"]), 0, 1000)))
    if "rain_x" in params or "rain_z" in params:
        cur = n.parmTuple("startxz").eval() if n.parmTuple("startxz") else (1.0, 0.0)
        vec = (clamp(float(params.get("rain_x", cur[0])), -1.0, 1.0),
               clamp(float(params.get("rain_z", cur[1])), -1.0, 1.0))
        _try_set_tuple(n, "startxz", vec)
    if "noise_basis" in params:
        _menu_tok_set(n, "basis", str(params["noise_basis"]), _NOISE_BASIS)
    if "fractal" in params:
        _menu_tok_set(n, "fractal", str(params["fractal"]), _FRACTAL)
    if "layermode" in params:
        _menu_tok_set(n, "layermode", str(params["layermode"]), _LAYERMODE)
    if "invert_noise" in params:
        _try_set(n, "input", bool(params["invert_noise"]))
    if "soilmaskname" in params:
        _try_set(n, "soilmaskname", _safe_token(params["soilmaskname"]))
    return _finish(n=n, geo=None)


# ── 9. biome_attributes_to_terrain (chain; in0 terrain, in1/in2 opt) ──────────────────────────────
@endpoint("biome_attributes_to_terrain")
def biome_attributes_to_terrain(params):
    """SideFX Labs Biome Attributes To Terrain (labs::biome_attributes_to_terrain::1.0) — bakes the
    biome climate attributes onto the incoming terrain (`input`, input 0) as named heightfield layers
    (temperature / precipitation / soil / biome color) ready for downstream shading or export.
    `display` picks the preview channel; `usedefault` fills gaps transparent or with a constant
    (`temperature` / `precipitation` / `soil` / color) for cells with no biome. Optional `defs`
    (input 1) / `plants` (input 2) supply the biome & plant libraries. Data-only (no file/code
    surface; the Unreal material-path string is left at HDA default)."""
    n = child_after(params["input"], "labs::biome_attributes_to_terrain::1.0", params.get("name"))
    if params.get("defs"):
        bridge_input(n, params["defs"], index=1, name_hint="defs")
    if params.get("plants"):
        bridge_input(n, params["plants"], index=2, name_hint="plants")
    if "display" in params:
        _menu_idx_set(n, "display", str(params["display"]), _DISPLAY)
    if "autoremap" in params:
        _menu_idx_set(n, "autoremap", str(params["autoremap"]), _AUTOREMAP)
    if "usedefault" in params:
        _menu_idx_set(n, "usedefault", str(params["usedefault"]), _USEDEFAULT)
    if "temperature" in params:
        _try_set(n, "temperature", clamp(float(params["temperature"]), -100.0, 100.0))
    if "precipitation" in params:
        _try_set(n, "precipitation", clamp(float(params["precipitation"]), 0.0, 100000.0))
    if "soil" in params:
        _try_set(n, "soil", bool(params["soil"]))
    _set_color(n, params, "biomecolor", "color")
    return _finish(n=n, geo=None)


# ══ Curve authoring ══════════════════════════════════════════════════════════════════════════════

# ── 10. biome_curve_setup (source/chain; in0 curve opt) ───────────────────────────────────────────
@endpoint("biome_curve_setup")
def biome_curve_setup(params):
    """SideFX Labs Biome Curve Setup (labs::biome_curve_setup::1.0) — tags an authored region CURVE
    (`input`, input 0 — a hand-drawn boundary) with the biome it belongs to (`biomename_curve`) and a
    sort order (`biomehierarchy`), producing the merged curve stream biome_region_assign reads in
    `curves` mode. With no `input` it builds a fresh /obj geo (draw the curve into it). SECURITY:
    `biomeprofile` is confined to the working dir (set only when supplied)."""
    geo, n = _source_or_chain(params, "labs::biome_curve_setup::1.0")
    if "biomename_curve" in params:
        _try_set(n, "biomename_curve", _safe_token(params["biomename_curve"]))
    if "biomehierarchy" in params:
        _try_set(n, "biomehierarchy", int(clamp(int(params["biomehierarchy"]), 0, 1000)))
    _set_file(n, "biomeprofile", params.get("biomeprofile"))
    return _finish(geo, n)


# ── 11. biome_curve_label (source/chain; in0 curve opt) ───────────────────────────────────────────
@endpoint("biome_curve_label")
def biome_curve_label(params):
    """SideFX Labs Biome Curve Label (labs::biome_curve_label::1.0) — labels a region CURVE (`input`,
    input 0) directly with explicit climate values (temperature / precipitation / soil / biome color /
    sort order) instead of pulling them from a profile — the manual counterpart to biome_curve_setup.
    `biomedeftype` selects whether the biome list is read from a file or an operator path. SECURITY:
    `biomeprofile` is confined; the biome-define `pathtobiomes` NodeReference is left unset. (The
    dynamic `biome` name menu is populated from the profile at author time — not driven here.)"""
    geo, n = _source_or_chain(params, "labs::biome_curve_label::1.0")
    if "biomedeftype" in params:
        _menu_idx_set(n, "biomedeftype", str(params["biomedeftype"]), _BIOMEDEFTYPE)
    if "temperature" in params:
        _try_set(n, "temperature", clamp(float(params["temperature"]), -100.0, 100.0))
    if "precipitation" in params:
        _try_set(n, "precipitation", clamp(float(params["precipitation"]), 0.0, 100000.0))
    if "soil" in params:
        _try_set(n, "soil", 1 if bool(params["soil"]) else 0)
    if "biomehierarchy" in params:
        _try_set(n, "biomehierarchy", int(clamp(int(params["biomehierarchy"]), 0, 1000)))
    for comp in ("r", "g", "b"):
        key = "color_" + comp
        if key in params:
            _try_set(n, "biomecolor" + comp, clamp(float(params[key]), 0.0, 1.0))
    _set_file(n, "biomeprofile", params.get("biomeprofile"))
    return _finish(geo, n)


# ══ Internal region utilities ════════════════════════════════════════════════════════════════════

# ── 12. region_assignment_subutil (chain; in0 geometry) ───────────────────────────────────────────
@endpoint("region_assignment_subutil")
def region_assignment_subutil(params):
    """SideFX Labs Region Assignment (subutility) (labs::region_assignment_subutil::1.0) — an internal
    plumbing helper used inside the biome region pipeline: it loops `lpcount` times over the incoming
    geometry (`input`, input 0), reading a named HDA parameter (`hda_parm`) per iteration and writing
    its value into a point/prim attribute (`attrib_name`), indexed by `index_parm`. All strings are
    plain name tokens (a parameter name and an attribute name — never code). Data-only."""
    n = child_after(params["input"], "labs::region_assignment_subutil::1.0", params.get("name"))
    if "lpcount" in params:
        _try_set(n, "lpcount", int(clamp(int(params["lpcount"]), 0, 10000)))
    if "index_parm" in params:
        _try_set(n, "indexparm", _safe_token(params["index_parm"]))
    if any(k in params for k in ("hda_parm", "attrib_name")):
        if "hda_parm" in params:
            _try_set(n, "hdaparm1", _safe_token(params["hda_parm"]))
        if "attrib_name" in params:
            _try_set(n, "attname1", _safe_token(params["attrib_name"]))
    return _finish(n=n, geo=None)


# ── 13. convert_regions_to_curves_subutil (chain; in0 region polys w/ piece attr) ─────────────────
@endpoint("convert_regions_to_curves_subutil")
def convert_regions_to_curves_subutil(params):
    """SideFX Labs Convert Regions To Curves (subutility) (labs::convert_regions_to_curves_subutil::1.0)
    — converts region POLYGONS on the incoming geometry (`input`, input 0) into boundary CURVE
    primitives, one closed curve per region. `pieceattrib` names the primitive string attribute that
    partitions the geometry into regions (e.g. `name`). Data-only (a single plain attribute token)."""
    n = child_after(params["input"], "labs::convert_regions_to_curves_subutil::1.0", params.get("name"))
    if "pieceattrib" in params:
        _try_set(n, "pieceattrib", _safe_token(params["pieceattrib"]))
    return _finish(n=n, geo=None)

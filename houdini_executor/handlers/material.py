"""Procedural MATERIAL-GRAPH builder — data-only MaterialX shader authoring.

MaterialX (mtlx* VOP nodes) is a pure typed node graph: every node is created by type name, every
value is a typed literal, every connection is `setNamedInput(name, src, "out")`. There is NO VEX /
CVEX / OSL / snippet code path anywhere here — the whole graph is data, so it stays firmly inside the
data-only MCP boundary. The graph is authored in a /stage LOP `materiallibrary` and is renderer-
PORTABLE: Karma consumes MaterialX natively, AMD ProRender (Hydra delegate) consumes it via USD, and
it round-trips to USD Preview Surface for the GL viewport. One builder feeds every renderer.

Endpoints: material_graph_create (container) -> shader_node_add (add an mtlx node) -> shader_connect
(wire) -> shader_set_param (typed literal, auto-routing the signature-suffix) -> material_graph_assign
(bind to geometry). Convenience macros (material_ramp_on_attribute, material_pbr, material_noise_channel)
compose the primitives. `assign_material` / `assign_usd_material` are UNTOUCHED (this is additive)."""

import hou
from houdini_executor.server import endpoint, resolve_node, clamp, confined_path, stage_context
from houdini_executor.handlers._parmutil import _try_set




def _stage_node(ntype, name=None, after=None):
    """Create a LOP `ntype` in /stage, wired after `after` (a LOP path) if given, else a fresh
    generator in /stage. (Mirror of usd._stage_node — kept local to avoid cross-handler coupling.)"""
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


# MaterialX node-type whitelist — every entry is a typed value/procedural/math/shader node (no code
# strings). Anything not here is rejected by shader_node_add (keeps the surface data-only + auditable).
_MTLX_NODE_WHITELIST = frozenset({
    # shader terminals
    "mtlxstandard_surface", "mtlxopen_pbr_surface", "mtlxUsdPreviewSurface",
    "mtlxsurfacematerial", "mtlxdisplacement", "collect",
    # textures / projection
    "mtlximage", "mtlxtiledimage", "mtlxtriplanarprojection", "mtlxnormalmap", "mtlxheighttonormal",
    # noise / procedural
    "mtlxnoise3d", "mtlxnoise2d", "mtlxfractal3d", "mtlxworleynoise3d", "mtlxworleynoise2d",
    "mtlxunifiednoise3d", "mtlxcellnoise3d", "mtlxcheckerboard",
    # ramps / value sources
    "mtlxramplr", "mtlxramptb", "mtlxramp4", "mtlxconstant",
    # geometry reads
    "mtlxgeompropvalue", "mtlxtexcoord", "mtlxposition", "mtlxnormal", "mtlxtangent", "mtlxbitangent",
    # math / combine
    "mtlxmix", "mtlxremap", "mtlxrange", "mtlxmultiply", "mtlxadd", "mtlxsubtract", "mtlxdivide",
    "mtlxclamp", "mtlxsmoothstep", "mtlxpower", "mtlxabsval", "mtlxinvert", "mtlxdotproduct",
    "mtlxseparate3c", "mtlxcombine3", "mtlxseparate2", "mtlxcombine2", "mtlxseparate4", "mtlxcombine4",
    "mtlxswizzle", "mtlxconvert", "mtlxluminance", "mtlxrgbtohsv", "mtlxhsvtorgb",
})
_MTLX_SIGNATURES = ("default", "color3", "color4", "vector2", "vector3", "vector4")
# arity -> the signature a tuple of that length most likely maps to (used to guess a suffixed variant)
_ARITY_SIG = {2: "vector2", 3: "color3", 4: "color4"}
_FILE_PARMS = ("file", "filex", "filey", "filez")


def _node_signature(n):
    sp = n.parm("signature")
    if sp is None:
        return None
    try:
        return sp.eval() or "default"
    except Exception:
        return "default"


@endpoint("material_graph_create")
def material_graph_create(params):
    """Create an empty PROCEDURAL MaterialX material graph — a /stage LOP `materiallibrary` you then
    fill with shader_node_add / shader_connect / shader_set_param and bind with material_graph_assign.
    The returned `library` is the parent to add mtlx* nodes into; the material prim is authored at
    `matpath_prefix`/<terminal-node-name>. Chain onto an existing LOP with `input` (else a fresh /stage
    branch). Data-only MaterialX — no VEX/code; the same graph renders in Karma, AMD ProRender, and USD
    Preview. This is the foundation of the material-graph builder."""
    name = str(params.get("name") or "matlib")
    ml = _stage_node("materiallibrary", name, params.get("input"))
    prefix = "/materials/"
    mp = ml.parm("matpathprefix")
    if mp is not None:
        try:
            prefix = mp.eval() or prefix
        except Exception:
            pass
    return {"library": ml.path(), "matpath_prefix": prefix, "signatures": list(_MTLX_SIGNATURES)}


@endpoint("shader_node_add")
def shader_node_add(params):
    """Add ONE MaterialX node to a material graph (`library` from material_graph_create). `node_type` =
    a whitelisted mtlx* type:
      • mtlxstandard_surface = the PBR shader TERMINAL (base_color/specular_roughness/metalness/normal/…)
      • mtlximage / mtlxtiledimage = UV texture read; mtlxtriplanarprojection = world-projected texture
        (no UVs — for scan/heightfield meshes)
      • mtlxnoise3d / mtlxfractal3d / mtlxworleynoise3d / mtlxunifiednoise3d = procedural noise
      • mtlxramplr / mtlxramptb / mtlxramp4 = gradient ramp (drive `texcoord` with a scalar)
      • mtlxgeompropvalue = READ A GEOMETRY ATTRIBUTE / primvar into the graph (e.g. a terrain layer)
      • mtlxmix / mtlxremap / mtlxrange / mtlxmultiply / mtlxadd / mtlxclamp = math
      • mtlxnormalmap / mtlxheighttonormal = normal; mtlxdisplacement = displacement TERMINAL
    `signature` sets the node's data type (default=float | color3 | color4 | vector2/3/4) — set it for
    value/procedural nodes so typed values and outputs match. Returns the node path + its input names."""
    library = resolve_node(params["library"])
    ntype = str(params["node_type"])
    if ntype not in _MTLX_NODE_WHITELIST:
        raise ValueError("node_type '%s' is not in the MaterialX whitelist (%d allowed types)"
                         % (ntype, len(_MTLX_NODE_WHITELIST)))
    n = library.createNode(ntype, params.get("name")) if params.get("name") else library.createNode(ntype)
    sig = params.get("signature")
    if sig is not None:
        if str(sig) not in _MTLX_SIGNATURES:
            raise ValueError("signature must be one of %s" % "|".join(_MTLX_SIGNATURES))
        _try_set(n, "signature", str(sig))
    try:
        inputs = list(n.inputNames())
    except Exception:
        inputs = []
    return {"node": n.path(), "node_type": ntype, "inputs": inputs, "output": "out",
            "signature": _node_signature(n)}


@endpoint("shader_connect")
def shader_connect(params):
    """Wire one MaterialX node's output into another's input (build the graph edge). `dst` = the target
    node, `dst_input` = the input NAME (e.g. 'base_color', 'specular_roughness', 'normal', 'texcoord',
    'in1') OR a numeric index, `src` = the source node, `src_output` = the source connector (default
    'out' — every mtlx node's single output). Server resolves the name to the right slot."""
    dst = resolve_node(params["dst"])
    src = resolve_node(params["src"])
    names = list(dst.inputNames())
    di = params["dst_input"]
    if isinstance(di, str) and not di.lstrip("-").isdigit():
        if di not in names:
            raise ValueError("input '%s' not found on %s (valid: %s)" % (di, dst.type().name(), names))
        input_name = di
    else:
        idx = int(di)
        if idx < 0 or idx >= len(names):
            raise ValueError("input index %d out of range on %s (0..%d)" % (idx, dst.type().name(), len(names) - 1))
        input_name = names[idx]
    src_out = str(params.get("src_output") or "out")
    dst.setNamedInput(input_name, src, src_out)
    idx = names.index(input_name)
    return {"dst": dst.path(), "dst_input": input_name, "src": src.path(), "src_output": src_out,
            "connected": dst.input(idx) is not None}


@endpoint("shader_set_param")
def shader_set_param(params):
    """Set a TYPED literal on a MaterialX node — auto-handling the signature-suffix trap. `node`,
    `param` = the BASE parm name (e.g. 'amplitude', 'valuel', 'valuer', 'geomprop', 'file', 'octaves',
    'inlow', 'outhigh'), `value` = a number, an [r,g,b]/[x,y,z] list, or a string. When the node's
    signature != default, the typed value lives in a suffixed variant (e.g. valuel_color3) — the server
    routes to the right variant from the node's signature + the value's arity, so the caller always uses
    the plain base name. File params (file/filex/filey/filez) are read-confined."""
    n = resolve_node(params["node"])
    parm = str(params["param"])
    val = params["value"]
    # Over MCP `value` arrives as a string (the one Kind that fits number|list|string). Coerce a
    # JSON-looking string to its real type ('[1,0,0]' -> list, '2.5' -> float); a plain string like a
    # geomprop/attribute name or a file path stays a string (json.loads fails -> kept).
    if isinstance(val, str):
        s = val.strip()
        if s[:1] == "[" or (s and s.lstrip("-").replace(".", "", 1).isdigit()):
            import json
            try:
                val = json.loads(s)
            except Exception:
                pass
    sig = _node_signature(n)

    if parm in _FILE_PARMS:
        ok = _try_set(n, parm, confined_path(str(val)))
        return {"node": n.path(), "param": parm, "set": ok, "confined": True}

    if isinstance(val, (list, tuple)):
        vals = tuple(float(x) for x in val)
        cand = []
        if sig and sig != "default":
            cand.append("%s_%s" % (parm, sig))
        arity = _ARITY_SIG.get(len(vals))
        if arity and ("%s_%s" % (parm, arity)) not in cand:
            cand.append("%s_%s" % (parm, arity))
        cand.append(parm)
        for c in cand:
            pt = n.parmTuple(c)
            if pt is not None and len(pt) == len(vals):
                pt.set(vals)
                return {"node": n.path(), "param": c, "set": True}
        # per-component fallback (name_r/g/b or namex/y/z)
        for suff in (("r", "g", "b", "a"), ("x", "y", "z", "w")):
            comp = ["%s%s" % (parm, suff[i]) for i in range(len(vals))]
            if all(n.parm(cn) is not None for cn in comp):
                for cn, v in zip(comp, vals):
                    _try_set(n, cn, v)
                return {"node": n.path(), "param": parm, "set": True, "per_component": True}
        raise ValueError("could not set tuple param '%s' on %s (tried %s)" % (parm, n.type().name(), cand))

    if isinstance(val, str):
        ok = _try_set(n, parm, val)
        if not ok:
            raise ValueError("param '%s' not found on %s" % (parm, n.type().name()))
        return {"node": n.path(), "param": parm, "set": True}

    fv = float(val)
    # If the active signature variant is a multi-component TUPLE (e.g. valuel_color3 on a color3
    # node), a bare scalar would otherwise silently land on the inactive base scalar parm (a silent
    # wrong-variant, no effect). Broadcast the scalar across the active tuple instead (grey for a
    # color, uniform for a vector) so the value actually takes on the shading node.
    if sig and sig != "default":
        pt = n.parmTuple("%s_%s" % (parm, sig))
        if pt is not None and len(pt) > 1:
            pt.set(tuple(fv for _ in range(len(pt))))
            return {"node": n.path(), "param": "%s_%s" % (parm, sig), "set": True, "broadcast": True}
    cand = []
    if sig and sig != "default":
        cand.append("%s_%s" % (parm, sig))
    cand.append(parm)
    for c in cand:
        if n.parm(c) is not None:
            _try_set(n, c, fv)
            return {"node": n.path(), "param": c, "set": True}
    raise ValueError("param '%s' not found on %s" % (parm, n.type().name()))


@endpoint("material_graph_assign")
def material_graph_assign(params):
    """Bind a built material graph to geometry on the USD stage (the proven materiallibrary +
    assignmaterial tail). `library` = the materiallibrary from material_graph_create; `shader` = the
    TERMINAL node (mtlxstandard_surface, or a collect/mtlxsurfacematerial joining surface+displacement);
    `prim_pattern` = the geometry prim path/pattern to bind to (REQUIRED — e.g. '/sopimport1' or a
    wildcard, set is_pattern=true for a wildcard). Composes an assignmaterial. Nothing renders."""
    if not params.get("prim_pattern"):
        raise ValueError("prim_pattern is required (the geometry prim path/pattern to bind)")
    ml = resolve_node(params["library"])
    shader = resolve_node(params["shader"])
    try:
        ml.cook(force=True)
    except Exception:
        pass
    prefix = "/materials/"
    mp = ml.parm("matpathprefix")
    if mp is not None:
        try:
            prefix = mp.eval() or prefix
        except Exception:
            pass
    matpath = prefix.rstrip("/") + "/" + shader.name()
    am = _stage_node("assignmaterial", None, ml.path())
    _try_set(am, "primpattern1", str(params["prim_pattern"]))
    _try_set(am, "matspecpath1", matpath)
    if params.get("is_pattern"):
        _try_set(am, "ispathexpression1", 1)
    if params.get("bind_purpose") in ("preview", "full"):
        _try_set(am, "bindpurpose1", str(params["bind_purpose"]))
    try:
        am.cook(force=True)
    except Exception:
        pass
    return {"node": am.path(), "material_library": ml.path(), "material": matpath,
            "bound_to": str(params["prim_pattern"])}


# ── convenience macros (compose the primitives above into one-call common recipes) ──

def _macro_surface(params):
    """Return (library, surface, created_fresh). If `shader` is given, extend that existing graph
    (its parent library + that mtlxstandard_surface); else create a fresh materiallibrary + surface."""
    if params.get("shader"):
        ss = resolve_node(params["shader"])
        return ss.parent(), ss, False
    name = str(params.get("name") or "material")
    ml = _stage_node("materiallibrary", name, params.get("input"))
    ss = ml.createNode("mtlxstandard_surface", name)
    return ml, ss, True


def _macro_assign(ml, ss, params, result):
    """If this macro created the material fresh AND a prim_pattern was given, bind it."""
    if params.get("prim_pattern"):
        result["assigned"] = material_graph_assign({
            "library": ml.path(), "shader": ss.path(),
            "prim_pattern": params["prim_pattern"], "is_pattern": params.get("is_pattern"),
            "bind_purpose": params.get("bind_purpose")})
    return result


@endpoint("material_ramp_on_attribute")
def material_ramp_on_attribute(params):
    """HERO recipe (one call): drive a COLOR shader channel from a RAMP on a GEOMETRY ATTRIBUTE — the
    terrain height->color idiom. Composes mtlxgeompropvalue(attribute) -> mtlxramplr(color3,
    ramp_low..ramp_high) -> a mtlxstandard_surface channel. `attribute` (e.g. 'height'), `channel`
    ('base_color' default | 'emission_color'), `ramp_low`/`ramp_high` = [r,g,b] (low->high across the
    attribute range; e.g. dark soil -> snow white). Pass `shader` to add this onto an EXISTING graph;
    else a fresh material is created and (if `prim_pattern` given) bound. Built from the graph
    primitives — a suggestion, not the only way (use the primitives for arbitrary graphs)."""
    ml, ss, fresh = _macro_surface(params)
    attr = str(params.get("attribute", "height"))
    gp = ml.createNode("mtlxgeompropvalue", "read_" + attr)
    _try_set(gp, "signature", "default")
    _try_set(gp, "geomprop", attr)
    ramp = ml.createNode("mtlxramplr", "ramp_" + attr)
    _try_set(ramp, "signature", "color3")
    lo = params.get("ramp_low", [0.1, 0.08, 0.05])
    hi = params.get("ramp_high", [0.9, 0.9, 0.92])
    ptl = ramp.parmTuple("valuel_color3")
    if ptl is not None:
        ptl.set(tuple(float(c) for c in lo))
    ptr = ramp.parmTuple("valuer_color3")
    if ptr is not None:
        ptr.set(tuple(float(c) for c in hi))
    ramp.setNamedInput("texcoord", gp, "out")
    channel = str(params.get("channel", "base_color"))
    if channel not in ss.inputNames():
        raise ValueError("channel '%s' is not an input on mtlxstandard_surface" % channel)
    ss.setNamedInput(channel, ramp, "out")
    result = {"library": ml.path(), "shader": ss.path(), "channel": channel, "attribute": attr,
              "ramp": ramp.path(), "attribute_reader": gp.path(), "created_fresh": fresh}
    return _macro_assign(ml, ss, params, result) if fresh else result


_MACRO_NOISE = {"fractal": "mtlxfractal3d", "perlin": "mtlxnoise3d",
                "worley": "mtlxworleynoise3d", "unified": "mtlxunifiednoise3d"}


@endpoint("material_noise_channel")
def material_noise_channel(params):
    """Drive a SCALAR shader channel from procedural NOISE (one call): composes noise -> mtlxrange
    (remap into out_low..out_high) -> a mtlxstandard_surface scalar channel. `channel`
    ('specular_roughness' default | 'metalness' | 'coat' | 'specular'), `noise_type`
    (fractal|perlin|worley|unified), `out_low`/`out_high` (the channel's value range, 0..1),
    `octaves`/`lacunarity`/`amplitude` shape the noise. Pass `shader` to add onto an EXISTING graph;
    else a fresh material is created and (if `prim_pattern` given) bound. A suggestion recipe."""
    ml, ss, fresh = _macro_surface(params)
    ntype = _MACRO_NOISE.get(str(params.get("noise_type", "fractal")), "mtlxfractal3d")
    nz = ml.createNode(ntype, "noise")
    _try_set(nz, "signature", "default")   # scalar noise
    if "octaves" in params:
        _try_set(nz, "octaves", int(clamp(int(params["octaves"]), 1, 12)))
    if "lacunarity" in params:
        _try_set(nz, "lacunarity", clamp(float(params["lacunarity"]), 1.0, 10.0))
    if "amplitude" in params:
        _try_set(nz, "amplitude", clamp(float(params["amplitude"]), 0.0, 1e4))
    rng = ml.createNode("mtlxrange", "remap")
    _try_set(rng, "signature", "default")
    _try_set(rng, "outlow", clamp(float(params.get("out_low", 0.0)), 0.0, 1.0))
    _try_set(rng, "outhigh", clamp(float(params.get("out_high", 1.0)), 0.0, 1.0))
    rng.setNamedInput("in", nz, "out")
    channel = str(params.get("channel", "specular_roughness"))
    if channel not in ss.inputNames():
        raise ValueError("channel '%s' is not an input on mtlxstandard_surface" % channel)
    ss.setNamedInput(channel, rng, "out")
    result = {"library": ml.path(), "shader": ss.path(), "channel": channel,
              "noise": nz.path(), "range": rng.path(), "created_fresh": fresh}
    return _macro_assign(ml, ss, params, result) if fresh else result

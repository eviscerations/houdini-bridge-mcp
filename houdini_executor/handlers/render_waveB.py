"""Lop/Solaris USD/Karma render CONFIG handlers (WIRE-ONLY).

These 9 tools wrap 12 pure-config Solaris render LOP types (H21.0.671, live-probed). They author USD RenderSettings / RenderProduct / RenderVar prims and the
Karma property/product/AOV/cryptomatte/metadata config that a downstream renderer consumes. They are
the SAFEST render subset: every one of these node types has NO execute button and NO code-surface
parms (verified: `code_surface_parms: []`), so there is
nothing to press and nothing to blank — they only FEED a renderer the human fires later.

Posture held regardless (defense-in-depth):
  * NEVER execute / render / press any button. Handlers only createNode + setInput + set data parms.
  * Any file-out path (picture / dcmfilename / productName / cryptopicture) is confined via
    confined_path() and ONLY set when the caller supplies it — else the HDA default is left for the
    human to edit before firing (WIRE-ONLY).
  * Cost levers are hard-clamped: resolution 16..8192, samples 1..256.
  * Long mangled `xn__...` USD-attribute parms are located by their readable needle (build-fragile
    hash suffix avoided) and set tolerantly; only human-meaningful levers are exposed.

Version note (H21.0.671): createNode("rendervar") resolves to rendervar::2.0, createNode(
"karmarenderproducts") -> ::2.0, createNode("karmastandardrendervars") -> ::2.0 — so each of those
handlers covers both the base and ::2.0 node types listed in the wave plan.
"""

from houdini_executor.server import (
    endpoint, resolve_node, clamp, confined_path, stage_context,
)
from houdini_executor.handlers._parmutil import _try_set

_RES_LO, _RES_HI = 16, 8192
_SPP_LO, _SPP_HI = 1, 256




def _author(node, base, value):
    """Set a plain USD-attribute parm that has a `<base>_control` companion: flip the control to
    'set' (author the attribute) then set the value. Guarded no-op when the value parm is absent."""
    ctrl = node.parm(base + "_control")
    if ctrl is not None:
        try:
            ctrl.set("set")
        except Exception:
            pass
    return _try_set(node, base, value)


def _author_needle(node, needle, value):
    """Author a mangled `xn__...` USD parm located by its readable `needle` (skipping the _control
    companion), flipping the matching _control to 'set' first. Build-hash tolerant. Guarded."""
    key = needle.lower() + "_"
    ck = needle.lower() + "_control"
    valp = None
    ctrlp = None
    for p in node.parms():
        n = p.name().lower()
        if ck in n:
            ctrlp = ctrlp or p
            continue
        if key in n and valp is None:
            valp = p
    if ctrlp is not None:
        try:
            ctrlp.set("set")
        except Exception:
            pass
    if valp is None:
        return False
    try:
        valp.set(value)
        return True
    except Exception:
        return False


def _set_resolution(node, res, applied):
    """Author resolution [x,y] on a node that gates both components behind a single
    `resolution_control` (rendersettings/renderproduct/karmarenderproducts). Clamped 16..8192."""
    if not res or len(res) != 2:
        return
    rx = int(clamp(int(res[0]), _RES_LO, _RES_HI))
    ry = int(clamp(int(res[1]), _RES_LO, _RES_HI))
    ctrl = node.parm("resolution_control")
    if ctrl is not None:
        try:
            ctrl.set("set")
        except Exception:
            pass
    a = _try_set(node, "resolution1", rx)
    b = _try_set(node, "resolution2", ry)
    if a or b:
        applied["resolution"] = [rx, ry]


def _stage_node(ntype, name=None, after=None):
    """Create LOP `ntype` wired after `after` (a LOP path) if given, else a fresh node in /stage."""
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


_WIRE_NOTE = "built WIRE-ONLY in /stage; nothing rendered — fire the render/export yourself"


# ── USD RenderSettings prim ───────────────────────────────────────────────────
@endpoint("render_settings_usd")
def render_settings_usd(params):
    """USD RenderSettings prim (Solaris rendersettings LOP) — WIRE-ONLY: authors the top-level render
    config (resolution, samples, camera) that a downstream renderer reads; it does NOT render — you
    fire it. Pure config: no execute button, no code surface.

    input (opt) = upstream LOP to layer onto; primpath (opt) = settings prim path; camera (opt) =
    camera PRIM path (USD data, not a file); resolution [x,y] (clamped 16..8192); samples (per-pixel,
    1..256); pathtraced_samples (1..256); name (opt node name)."""
    n = _stage_node("rendersettings", params.get("name"), params.get("input"))
    applied = {}
    if params.get("primpath"):
        applied["primpath"] = _try_set(n, "primpath", str(params["primpath"]))
    if params.get("camera"):
        applied["camera"] = _author(n, "camera", str(params["camera"]))
    _set_resolution(n, params.get("resolution"), applied)
    if "samples" in params:
        applied["samples"] = _author_needle(
            n, "samplesperpixel", int(clamp(int(params["samples"]), _SPP_LO, _SPP_HI)))
    if "pathtraced_samples" in params:
        applied["pathtraced_samples"] = _author_needle(
            n, "pathtracedsamples", int(clamp(int(params["pathtraced_samples"]), _SPP_LO, _SPP_HI)))
    return {"node": n.path(), "output": None, "rendered": False,
            "applied": applied, "note": "RenderSettings " + _WIRE_NOTE}


# ── USD RenderProduct (output image path + format) ────────────────────────────
@endpoint("render_product")
def render_product(params):
    """USD RenderProduct prim (Solaris renderproduct LOP) — WIRE-ONLY: names the OUTPUT IMAGE (path,
    type, framing) a renderer will write; it does NOT render — you fire it. Pure config, no execute
    button, no code surface.

    output (opt) = output image path (write-confined under the working dir; only set when supplied,
    else the HDA default is left for you); product_type (opt) = 'raster' or 'deep'; camera (opt) =
    camera PRIM path; resolution [x,y] (clamped 16..8192); primpath (opt); input (opt); name (opt)."""
    n = _stage_node("renderproduct", params.get("name"), params.get("input"))
    applied = {}
    out_path = None
    if params.get("output"):
        out_path = confined_path(str(params["output"]))
        applied["output"] = _author(n, "productName", out_path)
    pt = params.get("product_type")
    if pt in ("raster", "deep"):
        applied["product_type"] = _author(n, "productType", pt)
    if params.get("camera"):
        applied["camera"] = _author(n, "camera", str(params["camera"]))
    _set_resolution(n, params.get("resolution"), applied)
    if params.get("primpath"):
        applied["primpath"] = _try_set(n, "primpath", str(params["primpath"]))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "applied": applied, "note": "RenderProduct " + _WIRE_NOTE}


# ── USD RenderVar / AOV definition (covers rendervar + rendervar::2.0) ─────────
@endpoint("render_var")
def render_var(params):
    """USD RenderVar / AOV definition (Solaris rendervar[::2.0] LOP) — WIRE-ONLY: declares one AOV /
    render output variable (its source + data type) for a renderer to produce. Pure config, no
    output file of its own, no execute button, no code surface.

    source_name (opt) = the AOV source (e.g. 'color', 'N', a primvar/LPE name); data_type (opt) =
    e.g. 'color3f'|'float'|'vector3f'; source_type (opt) = 'raw'|'primvar'|'lpe'|'intrinsic';
    primpath (opt); input (opt); name (opt)."""
    n = _stage_node("rendervar", params.get("name"), params.get("input"))
    applied = {}
    if params.get("source_name"):
        applied["source_name"] = _author(n, "sourceName", str(params["source_name"]))
    if params.get("data_type"):
        applied["data_type"] = _author(n, "dataType", str(params["data_type"]))
    if params.get("source_type"):
        applied["source_type"] = _author(n, "sourceType", str(params["source_type"]))
    if params.get("primpath"):
        applied["primpath"] = _try_set(n, "primpath", str(params["primpath"]))
    return {"node": n.path(), "output": None, "rendered": False,
            "applied": applied, "note": "RenderVar " + _WIRE_NOTE}


# ── Additional RenderVars (extra AOV rows) ────────────────────────────────────
@endpoint("render_vars_additional")
def render_vars_additional(params):
    """Additional RenderVars (Solaris additionalrendervars LOP) — WIRE-ONLY: appends one extra AOV /
    RenderVar row to the stage's render output set. Pure config, no execute button, no code surface.
    Authors the first multiparm row when values are supplied.

    var_name (opt) = the AOV name; data_type (opt); source_name (opt); source_type (opt);
    parentprimpath (opt); input (opt); name (opt node name)."""
    n = _stage_node("additionalrendervars", params.get("name"), params.get("input"))
    applied = {}
    if params.get("parentprimpath"):
        applied["parentprimpath"] = _try_set(n, "parentprimpath", str(params["parentprimpath"]))
    if params.get("var_name"):
        applied["var_name"] = _try_set(n, "name1", str(params["var_name"]))
    if params.get("data_type"):
        applied["data_type"] = _try_set(n, "dataType1", str(params["data_type"]))
    if params.get("source_name"):
        applied["source_name"] = _try_set(n, "sourceName1", str(params["source_name"]))
    if params.get("source_type"):
        applied["source_type"] = _try_set(n, "sourceType1", str(params["source_type"]))
    return {"node": n.path(), "output": None, "rendered": False,
            "applied": applied, "note": "Additional RenderVars " + _WIRE_NOTE}


# ── Karma Render Properties (settings variant) ────────────────────────────────
@endpoint("karma_render_properties")
def karma_render_properties(params):
    """Karma Render Properties (Solaris karmarenderproperties LOP) — WIRE-ONLY: authors a combined
    Karma render-settings + product config on the stage; it does NOT render — you fire it. No execute
    button, no code surface.

    output (opt) = output image path (write-confined); dcm_file (opt) = deep-camera-map file
    (write-confined); camera (opt) = camera PRIM path; resolution [x,y] (clamped 16..8192, sets
    resolutionx/resolutiony); samples (per-pixel 1..256); pathtraced_samples (1..256); primpath
    (opt); input (opt); name (opt)."""
    n = _stage_node("karmarenderproperties", params.get("name"), params.get("input"))
    applied = {}
    out_path = None
    if params.get("output"):
        out_path = confined_path(str(params["output"]))
        applied["output"] = _try_set(n, "picture", out_path)
    if params.get("dcm_file"):
        applied["dcm_file"] = _try_set(n, "dcmfilename", confined_path(str(params["dcm_file"])))
    if params.get("camera"):
        applied["camera"] = _try_set(n, "camera", str(params["camera"]))
    res = params.get("resolution")
    if res and len(res) == 2:
        rx = int(clamp(int(res[0]), _RES_LO, _RES_HI))
        ry = int(clamp(int(res[1]), _RES_LO, _RES_HI))
        a = _try_set(n, "resolutionx", rx)
        b = _try_set(n, "resolutiony", ry)
        if a or b:
            applied["resolution"] = [rx, ry]
    if "samples" in params:
        applied["samples"] = _try_set(
            n, "samplesperpixel", int(clamp(int(params["samples"]), _SPP_LO, _SPP_HI)))
    if "pathtraced_samples" in params:
        applied["pathtraced_samples"] = _try_set(
            n, "pathtracedsamples", int(clamp(int(params["pathtraced_samples"]), _SPP_LO, _SPP_HI)))
    if params.get("primpath"):
        applied["primpath"] = _try_set(n, "primpath", str(params["primpath"]))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "applied": applied, "note": "Karma render properties " + _WIRE_NOTE}


# ── Karma Render Products (covers karmarenderproducts + ::2.0) ────────────────
@endpoint("karma_render_products")
def karma_render_products(params):
    """Karma Render Products bundle (Solaris karmarenderproducts[::2.0] LOP) — WIRE-ONLY: authors a
    set of Karma output products (beauty + AOVs) on the stage; it does NOT render — you fire it. No
    execute button, no code surface.

    output (opt) = first product's output image path (write-confined); product_name (opt) = first
    product prim name; camera (opt) = camera PRIM path; resolution [x,y] (clamped 16..8192);
    parentprimpath (opt); input (opt); name (opt)."""
    n = _stage_node("karmarenderproducts", params.get("name"), params.get("input"))
    applied = {}
    out_path = None
    if params.get("output"):
        out_path = confined_path(str(params["output"]))
        applied["output"] = _try_set(n, "productName_0", out_path)
    if params.get("product_name"):
        applied["product_name"] = _try_set(n, "primname_0", str(params["product_name"]))
    if params.get("camera"):
        applied["camera"] = _try_set(n, "camera", str(params["camera"]))
    _set_resolution(n, params.get("resolution"), applied)
    if params.get("parentprimpath"):
        applied["parentprimpath"] = _try_set(n, "parentprimpath", str(params["parentprimpath"]))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "applied": applied, "note": "Karma render products " + _WIRE_NOTE}


# ── Karma Standard RenderVars (covers karmastandardrendervars + ::2.0) ────────
@endpoint("karma_render_vars")
def karma_render_vars(params):
    """Karma Standard RenderVars (Solaris karmastandardrendervars[::2.0] LOP) — WIRE-ONLY: authors
    the standard Karma AOV set (beauty, diffuse/glossy/volume splits, etc.) on the stage; it does NOT
    render — you fire it. No output file of its own, no execute button, no code surface.

    parentprimpath (opt) = where the render vars are authored; aov_limit (opt int, 0..64) = the LPE
    AOV limit; input (opt); name (opt)."""
    n = _stage_node("karmastandardrendervars", params.get("name"), params.get("input"))
    applied = {}
    if params.get("parentprimpath"):
        applied["parentprimpath"] = _try_set(n, "parentprimpath", str(params["parentprimpath"]))
    if "aov_limit" in params:
        applied["aov_limit"] = _try_set(n, "lpeaovlimit", int(clamp(int(params["aov_limit"]), 0, 64)))
    return {"node": n.path(), "output": None, "rendered": False,
            "applied": applied, "note": "Karma standard render vars " + _WIRE_NOTE}


# ── Karma Cryptomatte ─────────────────────────────────────────────────────────
@endpoint("karma_cryptomatte")
def karma_cryptomatte(params):
    """Karma Cryptomatte AOV setup (Solaris karmacryptomatte LOP) — WIRE-ONLY: authors cryptomatte ID
    matte outputs on the stage; it does NOT render — you fire it. No execute button, no code surface.

    output (opt) = cryptomatte output image path (write-confined); prim_crypto (opt bool) = emit the
    prim-id cryptomatte; prim_crypto_file (opt) = its sidecar file path (write-confined); input
    (opt); name (opt)."""
    n = _stage_node("karmacryptomatte", params.get("name"), params.get("input"))
    applied = {}
    out_path = None
    if params.get("output"):
        out_path = confined_path(str(params["output"]))
        applied["output"] = _try_set(n, "cryptopicture", out_path)
    if "prim_crypto" in params:
        applied["prim_crypto"] = _try_set(n, "doprimcrypto", bool(params["prim_crypto"]))
    if params.get("prim_crypto_file"):
        applied["prim_crypto_file"] = _try_set(
            n, "primcryptofile", confined_path(str(params["prim_crypto_file"])))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "applied": applied, "note": "Karma cryptomatte " + _WIRE_NOTE}


# ── Husk Image Metadata ───────────────────────────────────────────────────────
@endpoint("husk_image_metadata")
def husk_image_metadata(params):
    """Husk Image Metadata (Solaris huskimagemetadata LOP) — WIRE-ONLY: attaches metadata (which
    prims' attributes to embed) into the rendered output image; it does NOT render — you fire it. No
    output file of its own, no execute button, no code surface.

    prim_list (opt) = prim pattern whose data is embedded as image metadata; input (opt); name
    (opt)."""
    n = _stage_node("huskimagemetadata", params.get("name"), params.get("input"))
    applied = {}
    if params.get("prim_list"):
        applied["prim_list"] = _try_set(n, "primlist", str(params["prim_list"]))
    return {"node": n.path(), "output": None, "rendered": False,
            "applied": applied, "note": "Husk image metadata " + _WIRE_NOTE}

"""SideFX Labs — legacy Cop2 (2D compositing) image/texture nodes. Data-only handlers.

These are the LEGACY `Cop2` category (2D compositing), NOT the H20.5+ Copernicus `Cop` lane in
`cops.py`. Cop2 nodes live inside a `cop2net`, so this file defines a LOCAL `_cop2_context()` helper
(mirrors `server.cop_context()` but for the Cop2 category) that lazily creates/returns a shared
`/obj/cops2` cop2net. Generators are created bare in that net; filters chain onto an existing Cop2
node via `child_after` (setInput 0). Params + input arity live-probed against H21.0.671.

Wraps the Labs normal-map suite (color/combine/invert/levels/map/normalize/rotate) + vector
normalize + texture utilities (grid texture, blackbody, demosaic, attribute-to-texture, Substance
archive). Data-only: `sbs_archive` reads a `.sbsar` file -> its `file` parm is routed through
`confined_path()`; no endpoint exposes a code/callback parm. `dds_file` is intentionally NOT wrapped
(its internal PythonCook imports PySide2 -> GUI-only, cannot cook headless).
"""

import json

import hou
from houdini_executor.server import endpoint, confined_path, child_after, resolve_node
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── local helpers (probe-safe; copied per handler file per house convention) ──────────────────────




def _as_list(val):
    """Normalize a vector/list param arriving as a JSON string or a real list to a list of floats."""
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [float(v) for v in val]
    s = str(val).strip()
    try:
        parsed = json.loads(s)
        if isinstance(parsed, (list, tuple)):
            return [float(v) for v in parsed]
        return [float(parsed)]
    except Exception:
        return [float(p) for p in s.replace(",", " ").split() if p]


def _set_uniform(node, parm, value):
    """Set every component of a parmTuple to `value` (e.g. a square `size`/resolution [w,h])."""
    pt = node.parmTuple(parm)
    if pt is None:
        return _try_set(node, parm, value)
    try:
        pt.set(tuple(value for _ in pt))
        return True
    except Exception:
        return False


def _set_vec(node, parm, values):
    """Set a multi-component parmTuple (color / level pair) from a list, padded/truncated to fit."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    vals = _as_list(values)
    if not vals:
        return False
    n = len(pt)
    vals = (vals + [0.0] * n)[:n]
    try:
        pt.set(tuple(vals))
        return True
    except Exception:
        return False


def _cop2_context():
    """The shared LEGACY Cop2 (2D compositing) network `/obj/cops2`, created on demand. Mirrors
    `server.cop_context()` (which serves the NEW Copernicus `Cop` lane) but for the `Cop2` category:
    Cop2 nodes must live inside a `cop2net`. Cop2 *generator* handlers create their node here; Cop2
    *filter* handlers chain onto an existing Cop2 node with `child_after` (creates in the input's
    parent, so it lands in whatever cop2net the upstream lives in)."""
    return hou.node("/obj/cops2") or hou.node("/obj").createNode("cop2net", "cops2")


def _cop2_gen(ntype, name=None):
    """Create a Cop2 *generator* node in the shared cop2net."""
    net = _cop2_context()
    n = net.createNode(ntype, name) if name else net.createNode(ntype)
    n.moveToGoodPosition()
    return n


# ── texture generators ────────────────────────────────────────────────────────────────────────────
@endpoint("sbs_archive")
def sbs_archive(params):
    """SideFX Labs SBS Archive — a Cop2 GENERATOR that reads a Substance `.sbsar` archive and outputs
    its rendered texture. Created in the shared /obj/cops2 cop2net. Data-only / SECURITY: the `.sbsar`
    `file` path is realpath-confined to the working directory via confined_path() (a file READ); the
    Reload button and per-frame scope params are not exposed."""
    n = _cop2_gen("labs::sbs_archive", params.get("name"))
    out = None
    if params.get("file"):
        out = confined_path(str(params["file"]))
        _try_set(n, "file", out)
    if "resolution" in params:
        _set_uniform(n, "size", int(params["resolution"]))
    return {"node": n.path(), "file": out}


@endpoint("blackbody_texture")
def blackbody_texture(params):
    """SideFX Labs Blackbody (labs::blackbody_cop) — a Cop2 generator mapping temperature (Kelvin) to
    emitted blackbody color across the image (temperature_low..temperature_high), with tonemap / gamma
    / adaptation / burn controls. Optional `input` (a Cop2 node path) drives it from an input
    temperature image (chained via child_after); otherwise it is created bare in /obj/cops2."""
    if params.get("input"):
        n = child_after(params["input"], "labs::blackbody_cop", params.get("name"))
    else:
        n = _cop2_gen("labs::blackbody_cop", params.get("name"))
    if "resolution" in params:
        _set_uniform(n, "size", int(params["resolution"]))
    for key, parm in (("temperature_low", "temperature_0"), ("temperature_high", "temperature_1")):
        if key in params:
            _try_set(n, parm, float(params[key]))
    for parm in ("gamma", "adaptation", "burn", "ramp_intensity", "clip_value"):
        if parm in params:
            _try_set(n, parm, float(params[parm]))
    for parm in ("pyro_shader", "tonemap"):
        if parm in params:
            _try_set(n, parm, bool(params[parm]))
    return {"node": n.path()}


@endpoint("attribute_to_texture")
def attribute_to_texture(params):
    """SideFX Labs Attribute Import (labs::attribute_import) — a Cop2 generator that rasterizes a
    geometry point/vertex ATTRIBUTE into a texture over the geometry's UV layout. `geometry` is a
    read-only scene op-path reference to a SOP (e.g. /obj/geo1/OUT), NOT a filesystem path; `uv_attr`
    selects the UV attribute; `attr_rgb` / `attr_alpha` name the attributes written to RGB / alpha.
    Data-only (no file surface, no code parm)."""
    n = _cop2_gen("labs::attribute_import::1.0", params.get("name"))
    if "resolution" in params:
        _set_uniform(n, "size", int(params["resolution"]))
    _try_set(n, "geometry", str(params["geometry"])) if params.get("geometry") else None
    _try_set(n, "uvattr", str(params["uv_attr"])) if params.get("uv_attr") else None
    _try_set(n, "attrrgb", str(params["attr_rgb"])) if params.get("attr_rgb") else None
    _try_set(n, "attra", str(params["attr_alpha"])) if params.get("attr_alpha") else None
    return {"node": n.path()}


@endpoint("grid_texture")
def grid_texture(params):
    """SideFX Labs Grid Texture (labs::grid_texture) — a Cop2 generator producing a UV checker/grid
    reference texture with optional per-tile text, borders and colors. `tiling` multiplies the grid
    density; colors (foreground_color/bg_color/text_color/border_color/outline_color) take an [r,g,b]
    list. Data-only; the `font` file parm is left at its default (not exposed)."""
    n = _cop2_gen("labs::grid_texture", params.get("name"))
    if "resolution" in params:
        _set_uniform(n, "size", int(params["resolution"]))
    if "tiling" in params:
        _try_set(n, "tilingamount", int(params["tiling"]))
    if "border_thickness" in params:
        _try_set(n, "borderthickness", float(params["border_thickness"]))
    if "text" in params:
        _try_set(n, "text", bool(params["text"]))
    if "text_outline" in params:
        _try_set(n, "textoutline", bool(params["text_outline"]))
    if "border" in params:
        _try_set(n, "border", bool(params["border"]))
    for key, parm in (("foreground_color", "foreground_color"), ("bg_color", "bg_color"),
                      ("text_color", "text_color"), ("outline_color", "color"),
                      ("border_color", "border_color")):
        if key in params:
            _set_vec(n, parm, params[key])
    return {"node": n.path()}


@endpoint("normal_color")
def normal_color(params):
    """SideFX Labs Normal Color (labs::normal_color) — a Cop2 generator emitting a flat tangent-space
    normal-map color field (the default 'up' normal, RGB 0.5/0.5/1) at the chosen resolution; the base
    layer you composite detail normals onto. Data-only (no file surface)."""
    n = _cop2_gen("labs::normal_color", params.get("name"))
    if "resolution" in params:
        _set_uniform(n, "size", int(params["resolution"]))
    return {"node": n.path()}


# ── normal-map filters (chain onto an upstream Cop2 image) ─────────────────────────────────────────
@endpoint("normal_map")
def normal_map(params):
    """SideFX Labs Normal Map (labs::normal_map) — a Cop2 FILTER converting an input height/grayscale
    image (input 0) into a tangent-space normal map. `strength` scales the bump; `blur_strength`
    pre-blurs the height; `flip_x`/`flip_y` flip the derivative axes (green-channel convention).
    Data-only; deprecated `_old_strength` is not exposed."""
    n = child_after(params["input"], "labs::normal_map", params.get("name"))
    if "strength" in params:
        _try_set(n, "multiplier", float(params["strength"]))
    if "blur_strength" in params:
        _try_set(n, "blur_strength", float(params["blur_strength"]))
    if "flip_x" in params:
        _try_set(n, "flip_x", bool(params["flip_x"]))
    if "flip_y" in params:
        _try_set(n, "flip_y", bool(params["flip_y"]))
    return {"node": n.path()}


@endpoint("normal_combine")
def normal_combine(params):
    """SideFX Labs Normal Combine (labs::normal_combine) — a Cop2 FILTER that layers a detail normal
    map (input 1) over a base normal map (input 0) with correct normal reoriented-blending. `input`
    and `input2` are both required Cop2 node paths. Data-only (no params)."""
    n = child_after(params["input"], "labs::normal_combine", params.get("name"))
    n.setInput(1, resolve_node(params["input2"]))
    return {"node": n.path()}


@endpoint("normal_invert")
def normal_invert(params):
    """SideFX Labs Normal Invert (labs::normal_invert) — a Cop2 FILTER that inverts selected axes of a
    tangent-space normal map (input 0). `invert_y` is the usual DirectX<->OpenGL green-channel flip;
    `invert_x`/`invert_z` are also exposed. Data-only."""
    n = child_after(params["input"], "labs::normal_invert", params.get("name"))
    for parm in ("invert_x", "invert_y", "invert_z"):
        if parm in params:
            _try_set(n, parm, bool(params[parm]))
    return {"node": n.path()}


@endpoint("normal_levels")
def normal_levels(params):
    """SideFX Labs Normal Levels (labs::normal_levels) — a Cop2 FILTER applying a levels/gamma remap to
    a normal map (input 0). `input_levels` [low,high] and `output_levels` [low,high] are 2-value lists;
    `gamma` is scalar. Data-only."""
    n = child_after(params["input"], "labs::normal_levels", params.get("name"))
    if "input_levels" in params:
        _set_vec(n, "from", params["input_levels"])
    if "output_levels" in params:
        _set_vec(n, "to", params["output_levels"])
    if "gamma" in params:
        _try_set(n, "gamma", float(params["gamma"]))
    return {"node": n.path()}


@endpoint("normal_rotate")
def normal_rotate(params):
    """SideFX Labs Normal Rotate (labs::normal_rotate) — a Cop2 FILTER that rotates the tangent-space
    normal vectors of an input normal map (input 0) by `angle` degrees about the surface normal (keeps
    the map consistent when the texture is rotated on the UVs). Data-only."""
    n = child_after(params["input"], "labs::normal_rotate", params.get("name"))
    if "angle" in params:
        _try_set(n, "angle", float(params["angle"]))
    return {"node": n.path()}


@endpoint("normal_normalize")
def normal_normalize(params):
    """SideFX Labs Normal Normalize (labs::normal_normalize) — a Cop2 FILTER that re-normalizes every
    pixel of an input normal map (input 0) back to unit length (fixes non-unit normals after blending
    or filtering). Data-only (no params)."""
    n = child_after(params["input"], "labs::normal_normalize", params.get("name"))
    return {"node": n.path()}


@endpoint("vector_normalize")
def vector_normalize(params):
    """SideFX Labs Vector Normalize (labs::vector_normalize) — a Cop2 FILTER that rescales an input
    vector image (input 0) into a normalized range: `enable` turns it on; `min`/`max` set the target
    range the vector magnitudes are fit into. Data-only."""
    n = child_after(params["input"], "labs::vector_normalize::1.0", params.get("name"))
    if "enable" in params:
        _try_set(n, "enable", 1 if bool(params["enable"]) else 0)
    if "min" in params:
        _try_set(n, "min", float(params["min"]))
    if "max" in params:
        _try_set(n, "max", float(params["max"]))
    return {"node": n.path()}


@endpoint("demosaic")
def demosaic(params):
    """SideFX Labs Demosaic (labs::demosaic) — a Cop2 FILTER that unpacks a `rows` x `columns` sprite
    atlas / flipbook sheet (input 0) into an individual frame: `frame` selects the tile, `start_frame`
    offsets the numbering. Data-only."""
    n = child_after(params["input"], "labs::demosaic::1.0", params.get("name"))
    for parm in ("rows", "columns", "frame", "start_frame"):
        if parm in params:
            _try_set(n, parm, int(params[parm]))
    return {"node": n.path()}

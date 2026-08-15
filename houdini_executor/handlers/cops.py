"""Copernicus (COP) handlers — the H20.5+ 2D image-processing lane (category `Cop`, NOT legacy
`Cop2`). Nodes live inside a `copnet`; generators are created in the shared `cop_context()` network
(/obj/cops), filters chain onto an existing COP node via `child_after`. Params live-probed against
H21.0.671 and cross-checked vs the offline SideFX help
(nodes.zip -> cop/<node>.txt). Data-only: NO wrangle/opencl/pythonsnippet endpoints here (RCE-shaped
-> cut or safe-VEX-gated separately).

A COP layer has a SIGNATURE (mono | vec2 | vec3 | vec4) that selects which value parms are live;
handlers set `signature` to match the value they're given.
"""

import json

import hou
from houdini_executor.server import (
    endpoint, clamp, child_after, resolve_node, cop_context, bridge_into,
    confined_path,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


def _input_list(val):
    """Normalize a multi-input `inputs` param to a list of node-ref strings. The catalog has no list
    Kind, so it arrives as a JSON array or a comma-separated string (iterating the raw string would
    walk it character-by-character)."""
    if not val:
        return []
    if isinstance(val, (list, tuple)):
        return [str(v) for v in val]
    s = str(val).strip()
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, list) else [str(parsed)]
    except Exception:
        return [p.strip() for p in s.split(",") if p.strip()]






def _str_menu_set(node, parm, token, tokens):
    """Set a STRING (Normal) menu parm by its token string directly."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _cop_gen(ntype, name=None):
    """Create a COP *generator* node inside the shared cop_context() copnet."""
    net = cop_context()
    n = net.createNode(ntype, name) if name else net.createNode(ntype)
    n.moveToGoodPosition()
    return n


# ── COP menus (live-probed H21.0.671). All are Normal
#    menus where set-by-token works (evalAsString returns the token) — set via _str_menu_set. NOTE:
#    `signature` is a STRING parm (token-stored: mono/vec2/vec3/vec4 or f1/f2/f3/f4), NOT a menu. ──
_NOISE_TYPE = ("torus", "perlin", "worleyA", "worleyB", "white", "alligator")
_METRIC = ("euclidean", "manhattan", "chebyshev")
_RAMP_TYPE = ("horizontal", "vertical", "radial", "concentric")
_RAMP_METHOD = ("clamp", "repeat", "mirror")
_REMAP_OP = ("remap", "threshold")
_REMAP_SIDE = ("greater", "greaterequal", "less", "lessequal")
_REMAP_METHOD = ("clamp", "repeat", "extend")
_INVERT_METHOD = ("complement", "negate", "reciprocal")
_EQ_MODE = ("stretch", "min", "max", "avg", "length")
_EQ_FIT = ("shift", "scale")
_EQ_LUM = ("lum", "ntsclum", "hdtvlum", "average", "max", "min", "magnitude", "hue",
           "saturation", "value", "red", "green", "blue", "comp4")
_BLEND_MODE = ("blend", "over", "under", "add", "subtract", "multiply", "divide", "screen", "hypot",
               "diff", "exclusion", "sharpen", "max", "min", "overlay", "softlight", "hardlight",
               "dodge", "burn", "hue", "sat", "lum", "color")
_HSV_OP = ("adjust", "to_hsv", "to_rgb")
_GB_FILTER = ("box", "gaussian")
_UNITS = ("image", "pixels")
_QUANT_METHOD = ("width", "segments")
_QUANT_ROUND = ("floor", "rint", "ceil", "custom")


# ── generators (created in the shared cop_context copnet; cook bare) ──────────────────────────────
@endpoint("cop_constant")
def cop_constant(params):
    """COP generator: a constant-value layer (Constant). `color` sets both the layer SIGNATURE and the
    value — 1 number = mono, 3 = RGB (vec3), 4 = RGBA (vec4). Created in the shared /obj/cops copnet
    at its resolution (default 1024²). BUILT."""
    n = _cop_gen("constant", params.get("name"))
    if "rgba" in params and len(params["rgba"]) == 4:
        _try_set(n, "signature", "vec4")
        for p, v in zip(("f4r", "f4g", "f4b", "f4a"), params["rgba"]):
            _try_set(n, p, float(v))
        sig = "vec4"
    elif "mono" in params:
        _try_set(n, "signature", "mono")
        _try_set(n, "f1", float(params["mono"]))
        sig = "mono"
    else:
        c = list(params.get("color", [0.0, 0.0, 0.0])) + [0.0, 0.0, 0.0]
        _try_set(n, "signature", "vec3")
        for p, v in zip(("f3r", "f3g", "f3b"), c[:3]):
            _try_set(n, p, float(v))
        sig = "vec3"
    return {"node": n.path(), "signature": sig}


@endpoint("cop_fractal_noise")
def cop_fractal_noise(params):
    """COP generator: fractal noise (Fractal Noise). noise_type (torus/perlin/worleyA/worleyB/white/
    alligator), metric, amplitude, element_size, octaves, lacunarity, roughness, contrast. All noise
    knobs are floats. BUILT."""
    n = _cop_gen("fractalnoise", params.get("name"))
    applied = {}
    if "noise_type" in params:
        applied["noise_type"] = _str_menu_set(n, "noisetype", str(params["noise_type"]), _NOISE_TYPE)
    if "metric" in params:
        applied["metric"] = _str_menu_set(n, "metric", str(params["metric"]), _METRIC)
    if "amplitude" in params:
        applied["amplitude"] = _try_set(n, "amp", clamp(float(params["amplitude"]), 0.0, 1e4))
    if "element_size" in params:
        applied["element_size"] = _try_set(n, "elementsize", clamp(float(params["element_size"]), 1e-4, 1e4))
    if "octaves" in params:
        applied["octaves"] = _try_set(n, "oct", clamp(float(params["octaves"]), 1.0, 20.0))
    if "lacunarity" in params:
        applied["lacunarity"] = _try_set(n, "lac", clamp(float(params["lacunarity"]), 1.0, 10.0))
    if "roughness" in params:
        applied["roughness"] = _try_set(n, "rough", clamp(float(params["roughness"]), 0.0, 1.0))
    if "contrast" in params:
        applied["contrast"] = _try_set(n, "contrast", clamp(float(params["contrast"]), 0.0, 10.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_ramp")
def cop_ramp(params):
    """COP generator: a linear/radial gradient (Ramp). ramp_type (horizontal/vertical/radial/
    concentric), cycles, phase, method (clamp/repeat/mirror for the outside range). BUILT."""
    n = _cop_gen("ramp", params.get("name"))
    applied = {}
    if "ramp_type" in params:
        applied["ramp_type"] = _str_menu_set(n, "rampType", str(params["ramp_type"]), _RAMP_TYPE)
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _RAMP_METHOD)
    if "cycles" in params:
        applied["cycles"] = _try_set(n, "cycles", clamp(float(params["cycles"]), 1e-3, 1000.0))
    if "phase" in params:
        applied["phase"] = _try_set(n, "phase", clamp(float(params["phase"]), -1e6, 1e6))
    return {"node": n.path(), "applied": applied}


# ── filters (chain onto an existing COP node via child_after; need input 0 wired to cook) ─────────
@endpoint("cop_remap")
def cop_remap(params):
    """COP filter: remap a layer's value range (Remap). op (remap/threshold), input_min/input_max ->
    output_min/output_max, method (clamp/repeat/extend); threshold mode: threshold + width + side.
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "remap", params.get("name"))
    applied = {}
    if "op" in params:
        applied["op"] = _str_menu_set(n, "op", str(params["op"]), _REMAP_OP)
    if "input_min" in params:
        applied["input_min"] = _try_set(n, "inputmin", float(params["input_min"]))
    if "input_max" in params:
        applied["input_max"] = _try_set(n, "inputmax", float(params["input_max"]))
    if "output_min" in params:
        applied["output_min"] = _try_set(n, "outputmin", float(params["output_min"]))
    if "output_max" in params:
        applied["output_max"] = _try_set(n, "outputmax", float(params["output_max"]))
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _REMAP_METHOD)
    if "threshold" in params:
        applied["threshold"] = _try_set(n, "threshold", float(params["threshold"]))
    if "width" in params:
        applied["width"] = _try_set(n, "width", clamp(float(params["width"]), 0.0, 1e6))
    if "side" in params:
        applied["side"] = _str_menu_set(n, "side", str(params["side"]), _REMAP_SIDE)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_invert")
def cop_invert(params):
    """COP filter: invert a layer (Invert). method: complement (1-x), negate (-x), reciprocal (1/x).
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "invert", params.get("name"))
    applied = {}
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _INVERT_METHOD)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_equalize")
def cop_equalize(params):
    """COP filter: stretch/shift a layer's value range to normalize contrast (Equalize). mode
    (stretch/min/max/avg/length), fitmethod (shift/scale), lum (luminance type), black/white points,
    target_average. Chains after `input`. BUILT."""
    n = child_after(params["input"], "equalize", params.get("name"))
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _EQ_MODE)
    if "fit_method" in params:
        applied["fit_method"] = _str_menu_set(n, "fitmethod", str(params["fit_method"]), _EQ_FIT)
    if "luminance" in params:
        applied["luminance"] = _str_menu_set(n, "lum", str(params["luminance"]), _EQ_LUM)
    if "black" in params:
        applied["black"] = _try_set(n, "black", float(params["black"]))
    if "white" in params:
        applied["white"] = _try_set(n, "white", float(params["white"]))
    if "target_average" in params:
        applied["target_average"] = _try_set(n, "goalavg", clamp(float(params["target_average"]), 0.0, 1e6))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_blend")
def cop_blend(params):
    """COP filter: composite two layers (Blend). `input` = background (input 0), `fg` = foreground
    (input 1); `mode` = the compositing operation (over/add/multiply/screen/difference/... 23 modes).
    swap flips FG/BG. Chains after `input`. BUILT."""
    n = child_after(params["input"], "blend", params.get("name"))
    fg = resolve_node(params["fg"])
    ref = fg if fg.parent().path() == n.parent().path() else bridge_into(fg, n.parent(), name_hint="fg")
    n.setInput(1, ref)
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _BLEND_MODE)
    if "swap" in params:
        applied["swap"] = _try_set(n, "swap", bool(params["swap"]))
    return {"node": n.path(), "fg_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_bright")
def cop_bright(params):
    """COP filter: brightness/level adjust (Bright). brightness (multiply), shift (add). Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "bright", params.get("name"))
    applied = {}
    if "brightness" in params:
        applied["brightness"] = _try_set(n, "bright", clamp(float(params["brightness"]), 0.0, 1e4))
    if "shift" in params:
        applied["shift"] = _try_set(n, "shift", float(params["shift"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_hsv")
def cop_hsv(params):
    """COP filter: hue/saturation/value adjust or RGB<->HSV convert (HSV Adjust). op (adjust/to_hsv/
    to_rgb), hue_shift, sat_scale, sat_shift, val_scale, val_shift. Chains after `input`. BUILT."""
    n = child_after(params["input"], "hsv", params.get("name"))
    applied = {}
    if "op" in params:
        applied["op"] = _str_menu_set(n, "op", str(params["op"]), _HSV_OP)
    if "hue_shift" in params:
        applied["hue_shift"] = _try_set(n, "hueshift", float(params["hue_shift"]))
    if "sat_scale" in params:
        applied["sat_scale"] = _try_set(n, "satscale", clamp(float(params["sat_scale"]), 0.0, 1e4))
    if "sat_shift" in params:
        applied["sat_shift"] = _try_set(n, "satshift", float(params["sat_shift"]))
    if "val_scale" in params:
        applied["val_scale"] = _try_set(n, "valscale", clamp(float(params["val_scale"]), 0.0, 1e4))
    if "val_shift" in params:
        applied["val_shift"] = _try_set(n, "valshift", float(params["val_shift"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_glow")
def cop_glow(params):
    """COP filter: bloom/glow from bright areas (Glow). threshold, brightness (gain), size (blur
    radius), filter (box/gaussian), units (image/pixels). Chains after `input`. BUILT."""
    n = child_after(params["input"], "glow", params.get("name"))
    applied = {}
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _GB_FILTER)
    if "units" in params:
        applied["units"] = _str_menu_set(n, "units", str(params["units"]), _UNITS)
    if "threshold" in params:
        applied["threshold"] = _try_set(n, "threshold", clamp(float(params["threshold"]), 0.0, 1e4))
    if "brightness" in params:
        applied["brightness"] = _try_set(n, "bright", clamp(float(params["brightness"]), 0.0, 1e4))
    if "size" in params:
        applied["size"] = _try_set(n, "size", clamp(float(params["size"]), 0.0, 10.0))
    if "size_pixels" in params:
        _str_menu_set(n, "units", "pixels", _UNITS)
        applied["size_pixels"] = _try_set(n, "size_pixel", clamp(float(params["size_pixels"]), 0.0, 1e4))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_quantize")
def cop_quantize(params):
    """COP filter: posterize a layer into discrete steps (Quantize). method (width/segments), segments
    (count) or width (step size), round (floor/rint/ceil/custom). Chains after `input`. BUILT."""
    n = child_after(params["input"], "quantize", params.get("name"))
    applied = {}
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _QUANT_METHOD)
    if "segments" in params:
        applied["segments"] = _try_set(n, "segments", int(clamp(int(params["segments"]), 1, 100000)))
    if "width" in params:
        applied["width"] = _try_set(n, "width", clamp(float(params["width"]), 1e-6, 1e6))
    if "round" in params:
        applied["round"] = _str_menu_set(n, "round", str(params["round"]), _QUANT_ROUND)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_blur")
def cop_blur(params):
    """COP filter: blur a layer (Blur). size (radius), filter (box/gaussian), units (image/pixels).
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "blur", params.get("name"))
    applied = {}
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _GB_FILTER)
    if "units" in params:
        applied["units"] = _str_menu_set(n, "units", str(params["units"]), _UNITS)
    if "size" in params:
        applied["size"] = _try_set(n, "size", clamp(float(params["size"]), 0.0, 10.0))
    if "size_pixels" in params:
        _str_menu_set(n, "units", "pixels", _UNITS)
        applied["size_pixels"] = _try_set(n, "size_pixel", clamp(float(params["size_pixels"]), 0.0, 1e4))
    return {"node": n.path(), "applied": applied}


# ── COP: SDF cluster + more filters (params/menus read from reference/houdini_nodes.json,
#    populated by scripts/import_cop_docs.py — live-probed + help-enriched). ───────────────────────
_SDF_SHAPECLASS = ("basic", "marker", "compound")
_SDF_SHAPETYPE_PARM = {"basic": "basictype", "marker": "markertype", "compound": "compoundtype"}
_SDF_BLEND_MODE = ("union", "intersect", "subtract", "diff")
_SDF_FILLET = ("none", "smooth", "round", "chamfer")
_SDF_OUTLINE_MODE = ("inside", "outside", "center")
_MEDIAN_SIZE = ("three", "five")
_STREAK_DIRTYPE = ("angle", "coord")
_STREAK_MODE = ("on", "min", "max")
_COMPARE_OP = ("equal", "notequal", "greater", "greaterequal", "less", "lessequal")
_COMPARE_COMPONENTS = ("all", "any")
_COMPARE_FALLOFF = ("none", "linear", "elendt")


@endpoint("cop_sdf_shape")
def cop_sdf_shape(params):
    """COP generator: a signed-distance-field 2D shape (SDF Shape) — circle, rect, star, triangle,
    and dozens more. shape_class (basic/marker/compound) picks the family; `shape` is the shape name
    (e.g. circle, rect, star, triangle, squircle...); `scale` sizes it; translate [x,y] + rotate
    position it. The SDF feeds sdf_blend / sdf_to_mono / sdf_to_rgb / sdf_adjust. BUILT."""
    n = _cop_gen("sdfshape", params.get("name"))
    applied = {}
    sc = str(params.get("shape_class", "basic"))
    if "shape_class" in params:
        applied["shape_class"] = _str_menu_set(n, "shapeclass", sc, _SDF_SHAPECLASS)
    if "shape" in params:
        applied["shape"] = _try_set(n, _SDF_SHAPETYPE_PARM.get(sc, "basictype"), str(params["shape"]))
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e4))
    if "translate" in params and len(params["translate"]) == 2:
        _try_set(n, "tx", float(params["translate"][0]))
        applied["translate"] = _try_set(n, "ty", float(params["translate"][1]))
    if "rotate" in params:
        applied["rotate"] = _try_set(n, "r", clamp(float(params["rotate"]), -360.0, 360.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_sdf_blend")
def cop_sdf_blend(params):
    """COP filter: combine two SDF layers (SDF Blend). `input` = A (input 0), `b` = B (input 1); mode
    (union/intersect/subtract/diff); fillet (none/smooth/round/chamfer) with smooth/round/chamfer
    amounts joins the shapes organically. Chains after `input`. BUILT."""
    n = child_after(params["input"], "sdfblend", params.get("name"))
    b = resolve_node(params["b"])
    ref = b if b.parent().path() == n.parent().path() else bridge_into(b, n.parent(), name_hint="sdf_b")
    n.setInput(1, ref)
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _SDF_BLEND_MODE)
    if "fillet" in params:
        applied["fillet"] = _str_menu_set(n, "fillet", str(params["fillet"]), _SDF_FILLET)
    if "smooth" in params:
        applied["smooth"] = _try_set(n, "smooth", clamp(float(params["smooth"]), 0.0, 1e4))
    if "round" in params:
        applied["round"] = _try_set(n, "round", clamp(float(params["round"]), 0.0, 1e4))
    if "chamfer" in params:
        applied["chamfer"] = _try_set(n, "chamfer", clamp(float(params["chamfer"]), 0.0, 1e4))
    return {"node": n.path(), "b_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_sdf_to_mono")
def cop_sdf_to_mono(params):
    """COP filter: rasterize an SDF into a mono layer (SDF To Mono) — fill value, background value,
    optional outline (width + inside/outside/center), antialiasing. Chains after `input`. BUILT."""
    n = child_after(params["input"], "sdftomono", params.get("name"))
    applied = {}
    if "shape_value" in params:
        applied["shape_value"] = _try_set(n, "shapevalue", float(params["shape_value"]))
    if "bg_value" in params:
        applied["bg_value"] = _try_set(n, "bgvalue", float(params["bg_value"]))
    if "outline" in params:
        applied["outline"] = _try_set(n, "drawoutline", bool(params["outline"]))
    if "outline_width" in params:
        _try_set(n, "drawoutline", True)
        applied["outline_width"] = _try_set(n, "outlinewidth", clamp(float(params["outline_width"]), 0.0, 1e4))
    if "outline_mode" in params:
        applied["outline_mode"] = _str_menu_set(n, "outlinemode", str(params["outline_mode"]), _SDF_OUTLINE_MODE)
    if "antialias" in params:
        applied["antialias"] = _try_set(n, "doaa", bool(params["antialias"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_sdf_to_rgb")
def cop_sdf_to_rgb(params):
    """COP filter: rasterize an SDF into a colour layer (SDF To RGB) — optional outline (width +
    inside/outside/center), antialiasing, iso offset. Chains after `input`. BUILT."""
    n = child_after(params["input"], "sdftorgb", params.get("name"))
    applied = {}
    if "outline" in params:
        applied["outline"] = _try_set(n, "drawoutline", bool(params["outline"]))
    if "outline_width" in params:
        _try_set(n, "drawoutline", True)
        applied["outline_width"] = _try_set(n, "outlinewidth", clamp(float(params["outline_width"]), 0.0, 1e4))
    if "outline_mode" in params:
        applied["outline_mode"] = _str_menu_set(n, "outlinemode", str(params["outline_mode"]), _SDF_OUTLINE_MODE)
    if "antialias" in params:
        applied["antialias"] = _try_set(n, "doaa", bool(params["antialias"]))
    if "iso" in params:
        applied["iso"] = _try_set(n, "iso", float(params["iso"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_sdf_adjust")
def cop_sdf_adjust(params):
    """COP filter: adjust an SDF (SDF Adjust) — iso_offset dilates/erodes the field, onion makes a
    hollow shell, abs makes it one-sided, invert swaps inside/outside. Chains after `input`. BUILT."""
    n = child_after(params["input"], "sdfadjust", params.get("name"))
    applied = {}
    if "iso_offset" in params:
        applied["iso_offset"] = _try_set(n, "isooffset", float(params["iso_offset"]))
    if "onion" in params:
        _try_set(n, "doonion", True)
        applied["onion"] = _try_set(n, "onion", clamp(float(params["onion"]), 0.0, 1e4))
    if "abs" in params:
        applied["abs"] = _try_set(n, "abs", bool(params["abs"]))
    if "invert" in params:
        applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_id_to_sdf")
def cop_id_to_sdf(params):
    """COP filter: build an SDF from an ID/label layer (ID To SDF) — distance to the nearest ID
    boundary. invert flips the sign, iterations controls propagation, tile_size the block size.
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "idtosdf", params.get("name"))
    applied = {}
    if "invert" in params:
        applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
    if "iterations" in params:
        applied["iterations"] = _try_set(n, "niter", int(clamp(int(params["iterations"]), 1, 1000)))
    if "tile_size" in params:
        applied["tile_size"] = _try_set(n, "tilesize", int(clamp(int(params["tile_size"]), 1, 4096)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_median")
def cop_median(params):
    """COP filter: median filter (Median) — removes salt-and-pepper noise / small speckle while
    keeping edges. size = three or five pixels; mask mixes the result. Chains after `input`. BUILT."""
    n = child_after(params["input"], "median", params.get("name"))
    applied = {}
    if "size" in params:
        applied["size"] = _str_menu_set(n, "fsize", str(params["size"]), _MEDIAN_SIZE)
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_streak_blur")
def cop_streak_blur(params):
    """COP filter: directional/motion blur along a line (Streak Blur). dir_type (angle/coord), angle,
    length, units (image/pixels), mode (on/min/max combine). Chains after `input`. BUILT."""
    n = child_after(params["input"], "streakblur", params.get("name"))
    applied = {}
    if "dir_type" in params:
        applied["dir_type"] = _str_menu_set(n, "dirtype", str(params["dir_type"]), _STREAK_DIRTYPE)
    if "angle" in params:
        applied["angle"] = _try_set(n, "angle", clamp(float(params["angle"]), -360.0, 360.0))
    if "units" in params:
        applied["units"] = _str_menu_set(n, "units", str(params["units"]), _UNITS)
    if "length" in params:
        applied["length"] = _try_set(n, "length", clamp(float(params["length"]), 0.0, 10.0))
    if "length_pixels" in params:
        _str_menu_set(n, "units", "pixels", _UNITS)
        applied["length_pixels"] = _try_set(n, "length_pixels", clamp(float(params["length_pixels"]), 0.0, 1e4))
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _STREAK_MODE)
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_kuwahara")
def cop_kuwahara(params):
    """COP filter: Kuwahara filter (Kuwahara Filter) — edge-preserving painterly smoothing. radius
    (region size, pixels), luminance type, blend, separation. Chains after `input`. BUILT."""
    n = child_after(params["input"], "kuwaharafilter", params.get("name"))
    applied = {}
    if "radius" in params:
        applied["radius"] = _try_set(n, "radius", clamp(float(params["radius"]), 0.0, 1e4))
    if "luminance" in params:
        applied["luminance"] = _str_menu_set(n, "luma", str(params["luminance"]), _EQ_LUM)
    if "blend" in params:
        applied["blend"] = _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    if "separation" in params:
        applied["separation"] = _try_set(n, "separation", clamp(float(params["separation"]), 0.0, 1e4))
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_compare")
def cop_compare(params):
    """COP filter: compare a layer to a value or a second layer, output a 0/1 mask (Compare).
    `input` = A (input 0), optional `b` = B (input 1) else uses `value`; compare op (equal/notequal/
    greater/…), tolerance, components (all/any), falloff. Chains after `input`. BUILT."""
    n = child_after(params["input"], "compare", params.get("name"))
    applied = {}
    if params.get("b"):
        bb = resolve_node(params["b"])
        ref = bb if bb.parent().path() == n.parent().path() else bridge_into(bb, n.parent(), name_hint="cmp_b")
        n.setInput(1, ref)
        applied["b_wired"] = True
    if "value" in params:
        applied["value"] = _try_set(n, "bval", float(params["value"]))
    if "compare" in params:
        applied["compare"] = _str_menu_set(n, "compare", str(params["compare"]), _COMPARE_OP)
    if "tolerance" in params:
        applied["tolerance"] = _try_set(n, "tol", clamp(float(params["tolerance"]), 0.0, 1e6))
    if "components" in params:
        applied["components"] = _str_menu_set(n, "components", str(params["components"]), _COMPARE_COMPONENTS)
    if "falloff" in params:
        applied["falloff"] = _str_menu_set(n, "falloff", str(params["falloff"]), _COMPARE_FALLOFF)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_edge_detect")
def cop_edge_detect(params):
    """COP filter: edge detection (Edge Detect). preblur softens before detection, normalize scales
    the output, low/high thresholds gate weak/strong edges; method + mode are integer selectors.
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "edgedetect", params.get("name"))
    applied = {}
    if "method" in params:
        applied["method"] = _try_set(n, "method", int(clamp(int(params["method"]), 0, 10)))
    if "mode" in params:
        applied["mode"] = _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 10)))
    if "preblur" in params:
        applied["preblur"] = _try_set(n, "preblur", clamp(float(params["preblur"]), 0.0, 1e4))
    if "normalize" in params:
        applied["normalize"] = _try_set(n, "normalize", bool(params["normalize"]))
    if "low_threshold" in params:
        applied["low_threshold"] = _try_set(n, "lowthr", clamp(float(params["low_threshold"]), 0.0, 1e6))
    if "high_threshold" in params:
        applied["high_threshold"] = _try_set(n, "highthr", clamp(float(params["high_threshold"]), 0.0, 1e6))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_sharpen")
def cop_sharpen(params):
    """COP filter: sharpen (Sharpen) — amplifies detail via an unsharp mask. amplitude, gain,
    threshold, size, units (image/pixels). Chains after `input`. BUILT."""
    n = child_after(params["input"], "sharpen", params.get("name"))
    applied = {}
    if "amplitude" in params:
        applied["amplitude"] = _try_set(n, "amplitude", clamp(float(params["amplitude"]), 0.0, 1e4))
    if "gain" in params:
        applied["gain"] = _try_set(n, "gain", clamp(float(params["gain"]), 0.0, 1e4))
    if "threshold" in params:
        applied["threshold"] = _try_set(n, "threshold", clamp(float(params["threshold"]), 0.0, 1e6))
    if "units" in params:
        applied["units"] = _str_menu_set(n, "units", str(params["units"]), _UNITS)
    if "size" in params:
        applied["size"] = _try_set(n, "sizeimage", clamp(float(params["size"]), 0.0, 10.0))
    return {"node": n.path(), "applied": applied}


# ── COP: effects/transitions + region ops (param data from reference/houdini_nodes.json). ─
_FILTER7 = ("point", "bilinear", "box", "triangle", "cubic", "mitchell", "bspline")
_WIPE_OP = ("cross", "dissolve", "wipe")
_WIPE_SHAPE = ("line", "rectangle", "circle", "cornershrink")
_CONVOLVE_COMBINE = ("add", "mul", "max", "min")
_DISTORT_BORDER = ("auto", "constant", "clamp", "mirror", "wrap")
_DISTORT_DIRTYPE = ("angle", "coord")
_DERIV_DIFFMODE = ("central", "forward", "diagonal")
_TILE_PATTERN = ("stackbond", "headerbond", "stretcherbond", "flemishbond", "americanbond",
                 "monkbond", "englishbond", "denglishbond", "windmill", "crosshatch", "basketwave",
                 "hopscotch", "herringbonen1", "herringbone32", "frenchpattern", "custom")
_TILE_MODE = ("seamless", "tilecount", "tilesize")
_SEGCONN_CONN = ("below", "above", "at", "levels")
_SEGVAL_METHOD = ("width", "segments")
_SMOOTHFILL_SIDE = ("below", "above")
_FILL_SOURCE = ("value", "sample", "first", "last")
_FEATHER_DIR = ("diamond", "square", "oct", "custom", "circle")
_FEATHER_DECAY = ("unitdist", "decay")


def _set_vec(node, base, values):
    pt = node.parmTuple(base)
    if pt is None:
        return False
    try:
        pt.set(tuple(float(v) for v in values))
        return True
    except Exception:
        return False


@endpoint("cop_tile_pattern")
def cop_tile_pattern(params):
    """COP generator: a brick/tile pattern (Tile Pattern) — stackbond, herringbone, basketweave, and
    many more masonry/tiling layouts. pattern picks the layout; mode (seamless/tilecount/tilesize)
    controls repetition; tiled_size sets the overall scale. BUILT."""
    n = _cop_gen("tilepattern", params.get("name"))
    applied = {}
    if "pattern" in params:
        applied["pattern"] = _str_menu_set(n, "patterntype", str(params["pattern"]), _TILE_PATTERN)
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "patternmode", str(params["mode"]), _TILE_MODE)
    if "tiled_size" in params:
        applied["tiled_size"] = _try_set(n, "tiledsize", clamp(float(params["tiled_size"]), 1e-4, 1e5))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_sequence_blend")
def cop_sequence_blend(params):
    """COP filter: blend across a temporal sequence (Sequence Blend) — motion-trail / frame-average.
    blend = mix amount, invert flips it. Chains after `input`. BUILT."""
    n = child_after(params["input"], "sequenceblend", params.get("name"))
    applied = {}
    if "blend" in params:
        applied["blend"] = _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    if "invert" in params:
        applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_wipe")
def cop_wipe(params):
    """COP filter: transition/wipe between two layers (Wipe). `input` = A, `b` = B; op (cross/dissolve/
    wipe), shape (line/rectangle/circle/cornershrink), amount (0..1 progress), direction, seed. Chains
    after `input`. BUILT."""
    n = child_after(params["input"], "wipe", params.get("name"))
    b = resolve_node(params["b"])
    ref = b if b.parent().path() == n.parent().path() else bridge_into(b, n.parent(), name_hint="wipe_b")
    n.setInput(1, ref)
    applied = {}
    if "op" in params:
        applied["op"] = _str_menu_set(n, "op", str(params["op"]), _WIPE_OP)
    if "shape" in params:
        applied["shape"] = _str_menu_set(n, "shape", str(params["shape"]), _WIPE_SHAPE)
    if "amount" in params:
        applied["amount"] = _try_set(n, "amount", clamp(float(params["amount"]), 0.0, 1.0))
    if "direction" in params:
        applied["direction"] = _try_set(n, "direction", float(params["direction"]))
    if "seed" in params:
        applied["seed"] = _try_set(n, "seed", float(params["seed"]))
    return {"node": n.path(), "b_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_chromatic_aberration")
def cop_chromatic_aberration(params):
    """COP filter: lens chromatic aberration (Chromatic Aberration) — per-channel scale/rotate to
    fringe the R/G/B. r_scale/g_scale/b_scale, overall_scale, r_angle/g_angle/b_angle, filter. Chains
    after `input`. BUILT."""
    n = child_after(params["input"], "chromaticaberration", params.get("name"))
    applied = {}
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    for key, parm in (("r_scale", "rscale"), ("g_scale", "gscale"), ("b_scale", "bscale"),
                      ("overall_scale", "overallscale"), ("r_angle", "rangle"),
                      ("g_angle", "gangle"), ("b_angle", "bangle")):
        if key in params:
            applied[key] = _try_set(n, parm, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_convolve")
def cop_convolve(params):
    """COP filter: 3x3 convolution kernel (Convolve) — sharpen, emboss, edge, custom effects. Provide
    the kernel rows top/mid/bot (each [a,b,c]); scale multiplies, normalize divides by the kernel sum,
    combine_op combines with the source. Chains after `input`. BUILT."""
    n = child_after(params["input"], "convolve3", params.get("name"))
    applied = {}
    for key in ("top", "mid", "bot"):
        if key in params and len(params[key]) == 3:
            applied[key] = _set_vec(n, key, params[key])
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "normalize" in params:
        applied["normalize"] = _try_set(n, "normalize", bool(params["normalize"]))
    if "combine_op" in params:
        applied["combine_op"] = _str_menu_set(n, "combineop", str(params["combine_op"]), _CONVOLVE_COMBINE)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_distort")
def cop_distort(params):
    """COP filter: warp a layer (Distort) — push pixels along an angle/direction (uniform) or by a
    distortion vector layer wired as `distortion` (input 1). angle, scale, dir_type (angle/coord),
    filter, border. Chains after `input`. BUILT."""
    n = child_after(params["input"], "distort", params.get("name"))
    applied = {}
    if params.get("distortion"):
        dd = resolve_node(params["distortion"])
        ref = dd if dd.parent().path() == n.parent().path() else bridge_into(dd, n.parent(), name_hint="distort_v")
        n.setInput(1, ref)
        applied["distortion_wired"] = True
    if "dir_type" in params:
        applied["dir_type"] = _str_menu_set(n, "dirtype", str(params["dir_type"]), _DISTORT_DIRTYPE)
    if "angle" in params:
        applied["angle"] = _try_set(n, "angle", clamp(float(params["angle"]), -360.0, 360.0))
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _DISTORT_BORDER)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_derivative")
def cop_derivative(params):
    """COP filter: image gradient / slope (Derivative) — rate of change of the layer, for normals /
    edge / relief. angle, scale, offset, difference_mode (central/forward/diagonal). Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "derivative", params.get("name"))
    applied = {}
    if "angle" in params:
        applied["angle"] = _try_set(n, "angle", clamp(float(params["angle"]), -360.0, 360.0))
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "offset" in params:
        applied["offset"] = _try_set(n, "offset", float(params["offset"]))
    if "difference_mode" in params:
        applied["difference_mode"] = _str_menu_set(n, "differencemode", str(params["difference_mode"]), _DERIV_DIFFMODE)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_segment_connectivity")
def cop_segment_connectivity(params):
    """COP filter: label connected regions with unique IDs (Segment By Connectivity) — the front end
    to id_to_sdf / per-region ops. connectivity (below/above/at/levels vs threshold), threshold,
    offset, collapse. Chains after `input`. BUILT."""
    n = child_after(params["input"], "segmentbyconnectivity", params.get("name"))
    applied = {}
    if "connectivity" in params:
        applied["connectivity"] = _str_menu_set(n, "connectivity", str(params["connectivity"]), _SEGCONN_CONN)
    if "threshold" in params:
        applied["threshold"] = _try_set(n, "threshold", float(params["threshold"]))
    if "offset" in params:
        applied["offset"] = _try_set(n, "offset", float(params["offset"]))
    if "collapse" in params:
        applied["collapse"] = _try_set(n, "collapse", bool(params["collapse"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_segment_value")
def cop_segment_value(params):
    """COP filter: quantize a layer into labelled value bands (Segment By Value) — method (width or
    segments), width or segments count, min/max range. Chains after `input`. BUILT."""
    n = child_after(params["input"], "segmentbyvalue", params.get("name"))
    applied = {}
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _SEGVAL_METHOD)
    if "width" in params:
        applied["width"] = _try_set(n, "width", clamp(float(params["width"]), 1e-6, 1e6))
    if "segments" in params:
        applied["segments"] = _try_set(n, "segments", int(clamp(int(params["segments"]), 1, 100000)))
    if "min_value" in params:
        applied["min_value"] = _try_set(n, "minval", float(params["min_value"]))
    if "max_value" in params:
        applied["max_value"] = _try_set(n, "maxval", float(params["max_value"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_smooth_fill")
def cop_smooth_fill(params):
    """COP filter: smoothly fill/extend regions (Smooth Fill) — diffuses source values into the
    `fill_area` (input 1: the region to inpaint), for hole-fill / extend-boundaries. side, threshold,
    iterations. `input` = source (input 0), `fill_area` = where to fill (input 1). BUILT."""
    n = child_after(params["input"], "smoothfill", params.get("name"))
    fa = resolve_node(params["fill_area"])
    ref = fa if fa.parent().path() == n.parent().path() else bridge_into(fa, n.parent(), name_hint="fill_area")
    n.setInput(1, ref)
    applied = {"fill_area_wired": n.input(1) is not None}
    if "side" in params:
        applied["side"] = _str_menu_set(n, "side", str(params["side"]), _SMOOTHFILL_SIDE)
    if "threshold" in params:
        applied["threshold"] = _try_set(n, "threshold", float(params["threshold"]))
    if "iterations" in params:
        applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 10000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_fill")
def cop_fill(params):
    """COP filter: flood-fill a layer (Fill) — replace with a value/sample. source (value/sample/first/
    last), color (fill value), id. Chains after `input`. BUILT."""
    n = child_after(params["input"], "fill", params.get("name"))
    applied = {}
    if "source" in params:
        applied["source"] = _str_menu_set(n, "source", str(params["source"]), _FILL_SOURCE)
    if "color" in params:
        applied["color"] = _try_set(n, "color", float(params["color"]))
    if "id" in params:
        applied["id"] = _try_set(n, "id", int(clamp(int(params["id"]), 0, 10_000_000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_feather")
def cop_feather(params):
    """COP filter: feather/soften edges of a mask (Feather) — direction (diamond/square/oct/circle),
    decay_mode (unitdist/decay), decay, unitdist; outside feathers outward. Chains after `input`.
    BUILT."""
    n = child_after(params["input"], "feather", params.get("name"))
    applied = {}
    if "direction" in params:
        applied["direction"] = _str_menu_set(n, "direction", str(params["direction"]), _FEATHER_DIR)
    if "outside" in params:
        applied["outside"] = _try_set(n, "outside", bool(params["outside"]))
    if "decay_mode" in params:
        applied["decay_mode"] = _str_menu_set(n, "decaymode", str(params["decay_mode"]), _FEATHER_DECAY)
    if "decay" in params:
        applied["decay"] = _try_set(n, "decay", clamp(float(params["decay"]), 0.0, 1e4))
    if "unit_distance" in params:
        applied["unit_distance"] = _try_set(n, "unitdist", clamp(float(params["unit_distance"]), 0.0, 1e4))
    return {"node": n.path(), "applied": applied}


# ── COP: lighting / lens + channel + colour adjust (data from reference/houdini_nodes.json). ─
_LIGHT_NORMALTYPE = ("signed", "offset")
_CHANNELSWAP_SRC = ("red", "green", "blue", "alpha", "zero", "one")
_MONORGB_METHOD = ("clamp", "repeat")
_MONORGBA_ALPHA = ("extend", "value")
_PREMULT_OP = ("mult", "divide")
_CROP_MODE = ("data", "both", "display")
_CROP_BORDER = ("unchanged", "constant", "clamp", "mirror", "wrap")


@endpoint("cop_light")
def cop_light(params):
    """COP filter: shade a layer with a normals layer (Light) — `input` = source (input 0),
    `normals` = the N layer (input 1, e.g. from height_to_normal); light_direction + light_color set
    the light, normal_type (signed/offset) how normals are encoded. BUILT."""
    n = child_after(params["input"], "light", params.get("name"))
    nm = resolve_node(params["normals"])
    ref = nm if nm.parent().path() == n.parent().path() else bridge_into(nm, n.parent(), name_hint="normals")
    n.setInput(1, ref)
    applied = {"normals_wired": n.input(1) is not None}
    if "normal_type" in params:
        applied["normal_type"] = _str_menu_set(n, "normaltype", str(params["normal_type"]), _LIGHT_NORMALTYPE)
    if "light_direction" in params and len(params["light_direction"]) == 3:
        applied["light_direction"] = _set_vec(n, "lightdir", params["light_direction"])
    if "light_color" in params and len(params["light_color"]) == 3:
        applied["light_color"] = _set_vec(n, "lightcolor", params["light_color"])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_bokeh")
def cop_bokeh(params):
    """COP filter: bokeh / depth-of-field blur (Bokeh) — radius, gain (highlight boost), resolution,
    filter kernel, normalize. Chains after `input`. BUILT."""
    n = child_after(params["input"], "bokeh", params.get("name"))
    applied = {}
    if "radius" in params:
        applied["radius"] = _try_set(n, "radius", clamp(float(params["radius"]), 0.0, 1e4))
    if "gain" in params:
        applied["gain"] = _try_set(n, "bokehgain", clamp(float(params["gain"]), 0.0, 1e4))
    if "resolution" in params:
        applied["resolution"] = _try_set(n, "bokehres", int(clamp(int(params["resolution"]), 1, 4096)))
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    if "normalize" in params:
        applied["normalize"] = _try_set(n, "normalize", bool(params["normalize"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_dilate_erode")
def cop_dilate_erode(params):
    """COP filter: morphological dilate/erode (Dilate Erode) — positive radius grows bright areas,
    negative shrinks them; softedge feathers; fill closes holes. Chains after `input`. BUILT."""
    n = child_after(params["input"], "dilateerode", params.get("name"))
    applied = {}
    if "radius" in params:
        applied["radius"] = _try_set(n, "radius", clamp(float(params["radius"]), -1e4, 1e4))
    if "soft_edge" in params:
        applied["soft_edge"] = _try_set(n, "softedge", clamp(float(params["soft_edge"]), 0.0, 1e4))
    if "fill" in params:
        applied["fill"] = _try_set(n, "fill", bool(params["fill"]))
    if "max_radius" in params:
        applied["max_radius"] = _try_set(n, "maxradius", clamp(float(params["max_radius"]), 0.0, 1e4))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_channel_extract")
def cop_channel_extract(params):
    """COP filter: extract a single channel into a mono layer (Channel Extract). channel = index
    (0=R,1=G,2=B,3=A). Chains after `input`. BUILT."""
    n = child_after(params["input"], "channelextract", params.get("name"))
    applied = {}
    if "channel" in params:
        applied["channel"] = _try_set(n, "channel", int(clamp(int(params["channel"]), 0, 16)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_channel_swap")
def cop_channel_swap(params):
    """COP filter: shuffle channels (Channel Swap) — set each output channel (red/green/blue/alpha)
    to any source channel or zero/one. Chains after `input`. BUILT."""
    n = child_after(params["input"], "channelswap", params.get("name"))
    applied = {}
    for key, parm in (("red", "srcred"), ("green", "srcgreen"), ("blue", "srcblue"), ("alpha", "srcalpha")):
        if key in params:
            applied[key] = _str_menu_set(n, parm, str(params[key]), _CHANNELSWAP_SRC)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_mono_to_rgb")
def cop_mono_to_rgb(params):
    """COP filter: map a mono layer to RGB via a value range (Mono To RGB). input_min/max ->
    output_min/max, method (clamp/repeat) for the outside range. Chains after `input`. BUILT."""
    n = child_after(params["input"], "monotorgb", params.get("name"))
    applied = {}
    if "input_min" in params:
        applied["input_min"] = _try_set(n, "inputmin", float(params["input_min"]))
    if "input_max" in params:
        applied["input_max"] = _try_set(n, "inputmax", float(params["input_max"]))
    if "output_min" in params:
        applied["output_min"] = _try_set(n, "outputmin", float(params["output_min"]))
    if "output_max" in params:
        applied["output_max"] = _try_set(n, "outputmax", float(params["output_max"]))
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _MONORGB_METHOD)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_mono_to_rgba")
def cop_mono_to_rgba(params):
    """COP filter: promote a layer to RGBA (Mono To RGBA) — alpha_mode extend (copy value) or value
    (constant alpha_value). Chains after `input`. BUILT."""
    n = child_after(params["input"], "monotorgba", params.get("name"))
    applied = {}
    if "alpha_mode" in params:
        applied["alpha_mode"] = _str_menu_set(n, "alphaextend", str(params["alpha_mode"]), _MONORGBA_ALPHA)
    if "alpha_value" in params:
        applied["alpha_value"] = _try_set(n, "alphaval", float(params["alpha_value"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_premult")
def cop_premult(params):
    """COP filter: premultiply / unpremultiply alpha (Premult). op = mult (premultiply) or divide
    (unpremultiply). Chains after `input`. BUILT."""
    n = child_after(params["input"], "premult", params.get("name"))
    applied = {}
    if "op" in params:
        applied["op"] = _str_menu_set(n, "op", str(params["op"]), _PREMULT_OP)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_crop")
def cop_crop(params):
    """COP filter: crop a layer (Crop). crop_min/crop_max = the [x,y] corners (image units 0..1);
    mode (data/both/display), border handling. Chains after `input`. BUILT."""
    n = child_after(params["input"], "crop", params.get("name"))
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _CROP_MODE)
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _CROP_BORDER)
    if "crop_min" in params and len(params["crop_min"]) == 2:
        applied["crop_min"] = _set_vec(n, "xy", params["crop_min"])
    if "crop_max" in params and len(params["crop_max"]) == 2:
        applied["crop_max"] = _set_vec(n, "rt", params["crop_max"])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_tonemap")
def cop_tonemap(params):
    """COP filter: tone-map HDR to display range (Tonemap). operator = index 0..5 (Reinhard / Hable /
    ACES-style curves), exposure adjusts pre-gain. Chains after `input`. BUILT."""
    n = child_after(params["input"], "tonemap", params.get("name"))
    applied = {}
    if "operator" in params:
        applied["operator"] = _try_set(n, "operator", str(int(clamp(int(params["operator"]), 0, 5))))
    if "exposure" in params:
        applied["exposure"] = _try_set(n, "exposure", float(params["exposure"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_contrast")
def cop_contrast(params):
    """COP filter: contrast adjust (Contrast) — contrast strength around a center pivot. Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "contrast", params.get("name"))
    applied = {}
    if "contrast" in params:
        applied["contrast"] = _try_set(n, "contrast", clamp(float(params["contrast"]), 0.0, 1e4))
    if "center" in params:
        applied["center"] = _try_set(n, "center", float(params["center"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_gamma")
def cop_gamma(params):
    """COP filter: gamma correction (Gamma) — gamma value, optional invert. Chains after `input`.
    BUILT."""
    n = child_after(params["input"], "gamma", params.get("name"))
    applied = {}
    if "gamma" in params:
        applied["gamma"] = _try_set(n, "gamma", clamp(float(params["gamma"]), 1e-4, 100.0))
    if "invert" in params:
        applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
    return {"node": n.path(), "applied": applied}


# ── COP: transform / grade / pattern / key / analysis / multi-input combine (all params +
#    menu STORAGE-types live-probed via parmTemplate; MENU tokens
#    resolved by _str_menu_set with an evalAsString round-trip gate; integer-token menus set by int).
#    Whole set is data-only — no RCE/file/onnx nodes. ──────────────────────────────────────────
_XFORM_ORD = ("srt", "str", "rst", "rts", "tsr", "trs")
_ROT_ORD = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")
_XFORM_BORDER = ("auto", "constant", "clamp", "mirror", "wrap", "clip")  # _DISTORT_BORDER + 'clip'
_CHECKER_SIG = ("f1", "f2", "f3", "f4")
_CLAMP_METHOD = ("clamp", "black")
_HIST_MODE = ("colorbar", "separatebar", "graph")
_HIST_OUTSIDE = ("discard", "clamp")
_VIGNETTE_SHAPE = ("round", "rectangle", "blend")
_AVERAGE_OP = ("add", "average", "multiply", "min", "max", "over")
_WORLEY_LATTICE = ("grid", "hex")


@endpoint("cop_transform")
def cop_transform(params):
    """COP filter: 2D/3D transform a layer (Transform). translate/rotate/scale_xyz/shear/pivot (each
    float3), uniform `scale`; xform_order (srt/str/…), rot_order (xyz/…); invert; border (auto/
    constant/clamp/mirror/wrap/clip) + reconstruction filter (point/bilinear/box/…). Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "xform", params.get("name"))
    applied = {}
    for key, base in (("translate", "t"), ("rotate", "r"), ("scale_xyz", "s"),
                      ("shear", "shear"), ("pivot", "p")):
        if key in params:
            applied[key] = _set_vec(n, base, params[key])
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", clamp(float(params["scale"]), -1e4, 1e4))
    if "xform_order" in params:
        applied["xform_order"] = _str_menu_set(n, "xOrd", str(params["xform_order"]), _XFORM_ORD)
    if "rot_order" in params:
        applied["rot_order"] = _str_menu_set(n, "rOrd", str(params["rot_order"]), _ROT_ORD)
    if "invert" in params:
        applied["invert"] = _try_set(n, "invertxform", bool(params["invert"]))
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _XFORM_BORDER)
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_color_correct")
def cop_color_correct(params):
    """COP filter: tonal-range colour grade (Color Correct). Master band add/mult/gamma/contrast (each
    RGB float3, auto-enables the master band); optional Shadow/Midtone/Highlight bands via *_add
    (float3, auto-enables that band). mask = mix 0..1, premult = treat RGBA as premultiplied. Chains
    after `input`. BUILT."""
    n = child_after(params["input"], "colorcorrect", params.get("name"))
    applied = {}
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    if "premult" in params:
        applied["premult"] = _try_set(n, "ispremult", bool(params["premult"]))
    master = ("master_add", "master_mult", "master_gamma", "master_contrast")
    if any(k in params for k in master):
        _try_set(n, "do_master", True)
    for key in master:
        if key in params:
            applied[key] = _set_vec(n, key, params[key])
    for tog, band in (("do_shadow", "shadow_add"), ("do_mid", "mid_add"),
                      ("do_highlight", "highlight_add")):
        if band in params:
            _try_set(n, tog, True)
            applied[band] = _set_vec(n, band, params[band])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_checkerboard")
def cop_checkerboard(params):
    """COP generator: checkerboard test pattern (Checkerboard). rows/cols divisions; even/odd tile
    values (scalar=mono f1, 3-list=RGB f3, 4-list=RGBA f4 — sets signature accordingly); translate/
    tile_size/bias (float2). Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("checkerboard", params.get("name"))
    applied = {}
    sample = params.get("even", params.get("odd"))
    if isinstance(sample, (list, tuple)):
        sig = {1: "f1", 2: "f2", 3: "f3", 4: "f4"}.get(len(sample), "f3")
    else:
        sig = "f1"
    applied["signature"] = _str_menu_set(n, "signature", sig, _CHECKER_SIG)
    for key in ("even", "odd"):
        if key in params:
            v = params[key]
            v = list(v) if isinstance(v, (list, tuple)) else [float(v)]
            applied[key] = _set_vec(n, key, (v + [v[-1]] * 4)[:4])
    if "rows" in params:
        applied["rows"] = _try_set(n, "rows", int(clamp(int(params["rows"]), 1, 100000)))
    if "cols" in params:
        applied["cols"] = _try_set(n, "cols", int(clamp(int(params["cols"]), 1, 100000)))
    for key, base in (("translate", "t"), ("tile_size", "tilesize"), ("bias", "bias")):
        if key in params:
            applied[key] = _set_vec(n, base, params[key])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_clamp")
def cop_clamp(params):
    """COP filter: clamp values to a lower/upper limit (Clamp). Supplying `lower`/`upper` auto-enables
    that limit; method = clamp (hold at the limit) or black (force to 0). mask = mix. Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "clamp", params.get("name"))
    applied = {}
    if "lower" in params:
        _try_set(n, "dolowerlimit", True)
        applied["lower"] = _try_set(n, "lowerlimit", float(params["lower"]))
    if "upper" in params:
        _try_set(n, "doupperlimit", True)
        applied["upper"] = _try_set(n, "upperlimit", float(params["upper"]))
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _CLAMP_METHOD)
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_channel_join")
def cop_channel_join(params):
    """COP combiner: merge separate mono layers into one RGB/RGBA layer (Channel Join). `inputs` = list
    of 2-4 node refs wired to red/green/blue/alpha; signature auto vec3 (3 inputs) / vec4 (4) unless
    given. `color` = fallback value for a missing channel. Created in the shared /obj/cops copnet.
    BUILT."""
    n = _cop_gen("channeljoin", params.get("name"))
    refs = _input_list(params.get("inputs"))
    wired = 0
    for i, r in enumerate(refs[:4]):
        src = resolve_node(r)
        ref = src if src.parent().path() == n.parent().path() else bridge_into(src, n.parent(), name_hint="chan%d" % i)
        n.setInput(i, ref)
        wired += 1
    applied = {}
    sig = params.get("signature") or ("vec4" if wired >= 4 else "vec3")
    applied["signature"] = _try_set(n, "signature", str(sig))
    if "color" in params:
        cv = params["color"]
        cv = list(cv) if isinstance(cv, (list, tuple)) else [float(cv)]
        applied["color"] = _set_vec(n, "color", (cv + [cv[-1]] * 4)[:4])
    return {"node": n.path(), "inputs_wired": wired, "applied": applied}


@endpoint("cop_chroma_key")
def cop_chroma_key(params):
    """COP filter: HSV-range green/blue-screen keyer (Chroma Key) -> matte. hue_circle (float4 hue/sat
    center+width), lum_range (float2), hue/sat/lum_rolloff soft edges, interpolation (rolloff function
    index 0..4), preview + preview_color (float3), premult (multiply input by the matte). Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "chromakey", params.get("name"))
    applied = {}
    if "hue_circle" in params:
        applied["hue_circle"] = _set_vec(n, "huecircle", params["hue_circle"])
    if "lum_range" in params:
        applied["lum_range"] = _set_vec(n, "lumrange", params["lum_range"])
    if "hue_rolloff" in params:
        applied["hue_rolloff"] = _try_set(n, "huerolloff", float(params["hue_rolloff"]))
    if "sat_rolloff" in params:
        applied["sat_rolloff"] = _try_set(n, "satrolloff", float(params["sat_rolloff"]))
    if "lum_rolloff" in params:
        applied["lum_rolloff"] = _try_set(n, "lumrolloff", float(params["lum_rolloff"]))
    if "interpolation" in params:
        applied["interpolation"] = _try_set(n, "interpolation", int(clamp(int(params["interpolation"]), 0, 4)))
    if "preview" in params:
        applied["preview"] = _try_set(n, "preview", bool(params["preview"]))
    if "preview_color" in params:
        applied["preview_color"] = _set_vec(n, "previewcolor", params["preview_color"])
    if "premult" in params:
        applied["premult"] = _try_set(n, "premult", bool(params["premult"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_histogram")
def cop_histogram(params):
    """COP filter: render a value histogram of the input as an image (Histogram). mode (colorbar/
    separatebar/graph), buckets, min/max range, outside (discard/clamp), scale; set_res + res (float2)
    to override output resolution. Chains after `input`. BUILT."""
    n = child_after(params["input"], "histogram", params.get("name"))
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _HIST_MODE)
    if "buckets" in params:
        applied["buckets"] = _try_set(n, "buckets", clamp(float(params["buckets"]), 1.0, 1e6))
    if "min" in params:
        applied["min"] = _try_set(n, "min", float(params["min"]))
    if "max" in params:
        applied["max"] = _try_set(n, "max", float(params["max"]))
    if "outside" in params:
        applied["outside"] = _str_menu_set(n, "outside", str(params["outside"]), _HIST_OUTSIDE)
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "set_res" in params:
        applied["set_res"] = _try_set(n, "setres", bool(params["set_res"]))
    if "res" in params:
        _try_set(n, "setres", True)
        applied["res"] = _set_vec(n, "res", params["res"])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_vignette")
def cop_vignette(params):
    """COP filter: darken/brighten toward the frame edge (Vignette). shape (round/rectangle/blend),
    brightness, circle_radius/circle_scale (float2), blend amount, rect_size (float2)/rect_roundness,
    center (float2), blur (edge softness), mask. Chains after `input`. BUILT."""
    n = child_after(params["input"], "vignette", params.get("name"))
    applied = {}
    if "shape" in params:
        applied["shape"] = _str_menu_set(n, "shape", str(params["shape"]), _VIGNETTE_SHAPE)
    if "brightness" in params:
        applied["brightness"] = _try_set(n, "bright", float(params["brightness"]))
    if "circle_radius" in params:
        applied["circle_radius"] = _try_set(n, "circle_radius", float(params["circle_radius"]))
    if "circle_scale" in params:
        applied["circle_scale"] = _set_vec(n, "circle_scale", params["circle_scale"])
    if "blend" in params:
        applied["blend"] = _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    if "rect_size" in params:
        applied["rect_size"] = _set_vec(n, "rect_size", params["rect_size"])
    if "rect_roundness" in params:
        applied["rect_roundness"] = _try_set(n, "rect_roundness", float(params["rect_roundness"]))
    if "center" in params:
        applied["center"] = _set_vec(n, "center", params["center"])
    if "blur" in params:
        applied["blur"] = _try_set(n, "blur", clamp(float(params["blur"]), 0.0, 1e4))
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_height_to_normal")
def cop_height_to_normal(params):
    """COP filter: derive a normal-map layer from a mono height layer (Height to Normal) — feeds the
    built cop_light `normals` input for relief shading. normal_type (signed/offset), scale (height gain
    -> steeper normals), read_outside (sample past the boundary), kernel (derivative distance). Chains
    after `input`. BUILT."""
    n = child_after(params["input"], "heighttonormal", params.get("name"))
    applied = {}
    if "normal_type" in params:
        applied["normal_type"] = _str_menu_set(n, "normaltype", str(params["normal_type"]), _LIGHT_NORMALTYPE)
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "read_outside" in params:
        applied["read_outside"] = _try_set(n, "readoutside", bool(params["read_outside"]))
    if "kernel" in params:
        applied["kernel"] = _try_set(n, "kernel", int(clamp(int(params["kernel"]), 1, 64)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_mirror")
def cop_mirror(params):
    """COP filter: mirror/kaleidoscope a layer across one or more planes (Mirror). mode 0 = custom
    planes (angle0/offset0/flip0), 1 = number-and-offset (num_planes + angle/offset); flip reflection.
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "mirror", params.get("name"))
    applied = {}
    if "mode" in params:
        applied["mode"] = _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 1)))
    if "num_planes" in params:
        applied["num_planes"] = _try_set(n, "numberplanes", int(clamp(int(params["num_planes"]), 1, 64)))
    if "flip" in params:
        applied["flip"] = _try_set(n, "flip", bool(params["flip"]))
    if "angle" in params:
        applied["angle"] = _try_set(n, "angle", float(params["angle"]))
    if "offset" in params:
        applied["offset"] = _try_set(n, "offset", float(params["offset"]))
    if "angle0" in params:
        applied["angle0"] = _try_set(n, "angle0", float(params["angle0"]))
    if "offset0" in params:
        applied["offset0"] = _try_set(n, "offset0", float(params["offset0"]))
    if "flip0" in params:
        applied["flip0"] = _try_set(n, "flip0", bool(params["flip0"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_average")
def cop_average(params):
    """COP combiner: combine many input layers with one operation (Average). operation (add/average/
    multiply/min/max/over), `inputs` = list of node refs wired 0..n, signature = output layer type.
    Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("average", params.get("name"))
    refs = _input_list(params.get("inputs"))
    wired = 0
    for i, r in enumerate(refs):
        src = resolve_node(r)
        ref = src if src.parent().path() == n.parent().path() else bridge_into(src, n.parent(), name_hint="avg%d" % i)
        n.setInput(i, ref)
        wired += 1
    applied = {}
    if "operation" in params:
        applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _AVERAGE_OP)
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    return {"node": n.path(), "inputs_wired": wired, "applied": applied}


@endpoint("cop_worley_noise")
def cop_worley_noise(params):
    """COP generator: cellular/Worley (Voronoi) noise (Worley Noise) — complements cop_fractal_noise.
    element_size (cell size), jitter, lattice (grid/hex), metric (euclidean/manhattan/chebyshev),
    offset (float2), tiled + tile_size (float2); post bias/gain/contrast (each auto-enables its
    toggle), complement. Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("worleynoise", params.get("name"))
    applied = {}
    if "element_size" in params:
        applied["element_size"] = _try_set(n, "elementsize", clamp(float(params["element_size"]), 1e-4, 1e4))
    if "jitter" in params:
        applied["jitter"] = _try_set(n, "jitter", clamp(float(params["jitter"]), 0.0, 1.0))
    if "lattice" in params:
        applied["lattice"] = _str_menu_set(n, "lattice", str(params["lattice"]), _WORLEY_LATTICE)
    if "metric" in params:
        applied["metric"] = _str_menu_set(n, "metric", str(params["metric"]), _METRIC)
    if "offset" in params:
        applied["offset"] = _set_vec(n, "off", params["offset"])
    if "tiled" in params:
        applied["tiled"] = _try_set(n, "dotiled", bool(params["tiled"]))
    if "tile_size" in params:
        _try_set(n, "dotiled", True)
        applied["tile_size"] = _set_vec(n, "tilesize", params["tile_size"])
    if "bias" in params:
        _try_set(n, "post_dobias", True)
        applied["bias"] = _try_set(n, "post_bias", float(params["bias"]))
    if "gain" in params:
        _try_set(n, "post_dogain", True)
        applied["gain"] = _try_set(n, "post_gain", float(params["gain"]))
    if "contrast" in params:
        _try_set(n, "post_docontrast", True)
        applied["contrast"] = _try_set(n, "post_contrast", float(params["contrast"]))
    if "complement" in params:
        applied["complement"] = _try_set(n, "post_docomplement", bool(params["complement"]))
    return {"node": n.path(), "applied": applied}


# ── COP: procedural-noise generators + terrain/relief filters + common
#    filters (menu storage-types + tuple lengths + input arity all live-probed via parmTemplate).
#    All MenuParmTemplate menus resolve by token via _str_menu_set
#    (proven, re-gated by evalAsString); numeric-token menus set by int. Data-only. ─────────
_CHLADNI_OUTPUT = ("lines", "abs", "sdf")
_PHASOR_TYPE = ("phasorwave", "phasornoise", "gabornoise", "intensityfield")
_PHASOR_WAVETYPE = ("sine", "rectangle", "saw")
_PHASOR_FIRSTROT = ("uniform", "varying")
_SHADOW_TYPE = ("disk", "sphere", "directional")
_SHADOW_USE = ("spherical", "cartesian")
_CURVATURE_TYPE = ("gaussian", "mean", "principal_max", "principal_min")
_RESAMPLE_SIZECONTROL = ("res", "aspect", "pixel")
_RESAMPLE_BASESIZE = ("parm", "input")
_RESAMPLE_ASPECTMENU = ("none", "1:1", "3:2", "4:3", "16:9")
_RESAMPLE_FIXEDSIDE = ("width", "height", "smaller", "larger")
_RESAMPLE_STRETCH = ("stretch", "horz", "vert", "max", "min")
_MONO_OP = ("lum", "ntsclum", "hdtvlum", "average", "max", "min", "magnitude", "hue", "saturation",
            "value", "red", "green", "blue", "comp4", "custom")


def _set_tuple(node, base, v):
    """Set a float parmTuple, broadcasting a scalar across all components and padding short lists."""
    pt = node.parmTuple(base)
    if pt is None:
        return False
    ln = len(pt)
    vals = list(v) if isinstance(v, (list, tuple)) else [float(v)] * ln
    vals = (vals + [vals[-1]] * ln)[:ln]
    try:
        pt.set(tuple(float(x) for x in vals))
        return True
    except Exception:
        return False


@endpoint("cop_julia")
def cop_julia(params):
    """COP generator: Julia-set fractal (Julia). real/imag = the Julia constant, escape_radius +
    max_iter control the escape test, scale (float2). Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("julia", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "scale" in params:
        applied["scale"] = _set_tuple(n, "scale", params["scale"])
    if "real" in params:
        applied["real"] = _try_set(n, "real", float(params["real"]))
    if "imag" in params:
        applied["imag"] = _try_set(n, "imag", float(params["imag"]))
    if "escape_radius" in params:
        applied["escape_radius"] = _try_set(n, "escaperad", float(params["escape_radius"]))
    if "max_iter" in params:
        applied["max_iter"] = _try_set(n, "maxiter", int(clamp(int(params["max_iter"]), 1, 10000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_chladni")
def cop_chladni(params):
    """COP generator: Chladni / cymatic standing-wave nodal pattern (Chladni). output (lines/abs/sdf),
    threshold + width (nodal-line mode), amp/amp_ratio, freq/freq_ratio, tile_size (float2). Created in
    the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("chladni", params.get("name"))
    applied = {}
    if "output" in params:
        applied["output"] = _str_menu_set(n, "output", str(params["output"]), _CHLADNI_OUTPUT)
    for key, base in (("threshold", "threshold"), ("width", "width"), ("amp", "amp"),
                      ("amp_ratio", "ampratio"), ("freq", "freq"), ("freq_ratio", "freqratio")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "tile_size" in params:
        applied["tile_size"] = _set_tuple(n, "tilesize", params["tile_size"])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_bubble_noise")
def cop_bubble_noise(params):
    """COP generator: bubble/cellular fractal noise (Bubble Noise). amp/center, element_size, phase
    (float4), offset (float2), tile_size (float2), max_octaves, lacunarity, roughness, distort,
    stretch (float2), fold; post bias (auto-enabled). Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("bubblenoise", params.get("name"))
    applied = {}
    for key, base in (("amp", "amp"), ("center", "center"), ("element_size", "elementsize"),
                      ("lacunarity", "lac"), ("roughness", "rough"), ("distort", "distort")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("phase", "phase"), ("offset", "offset"), ("tile_size", "tilesize"),
                      ("stretch", "stretch")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    if "max_octaves" in params:
        applied["max_octaves"] = _try_set(n, "max_octaves", int(clamp(int(params["max_octaves"]), 1, 20)))
    if "fold" in params:
        applied["fold"] = _try_set(n, "dofold", bool(params["fold"]))
    if "bias" in params:
        _try_set(n, "post_dobias", True)
        applied["bias"] = _try_set(n, "post_bias", float(params["bias"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_crystal_noise")
def cop_crystal_noise(params):
    """COP generator: faceted crystalline Worley-derived noise (Crystal Noise). amp/center/contrast,
    metric (euclidean/manhattan/chebyshev), jitter, element_size, secondary + metric2, flatten_faces,
    tiled + tile_size (float2), use_3d. Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("crystalnoise", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    for key, base in (("amp", "amp"), ("center", "center"), ("contrast", "contrast"),
                      ("jitter", "jitter"), ("element_size", "elementsize")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "metric" in params:
        applied["metric"] = _str_menu_set(n, "metric", str(params["metric"]), _METRIC)
    if "secondary" in params:
        applied["secondary"] = _try_set(n, "enablesecondary", bool(params["secondary"]))
    if "metric2" in params:
        _try_set(n, "enablesecondary", True)
        applied["metric2"] = _str_menu_set(n, "metric2", str(params["metric2"]), _METRIC)
    if "flatten_faces" in params:
        applied["flatten_faces"] = _try_set(n, "flattenfaces", bool(params["flatten_faces"]))
    if "tiled" in params:
        applied["tiled"] = _try_set(n, "dotiled", bool(params["tiled"]))
    if "tile_size" in params:
        _try_set(n, "dotiled", True)
        applied["tile_size"] = _set_tuple(n, "tilesize", params["tile_size"])
    if "use_3d" in params:
        applied["use_3d"] = _try_set(n, "use3d", bool(params["use_3d"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_phasor_noise")
def cop_phasor_noise(params):
    """COP generator: phasor/Gabor procedural wave-and-noise field (Phasor Noise). type (phasorwave/
    phasornoise/gabornoise/intensityfield), wave_type (sine/rectangle/saw), amp/center, element,
    wave_bias, blend (kernel radius), offset (float2), seed, kernels, rotation (uniform/varying),
    use_3d. Cooks bare in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("phasornoise", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    for key, base in (("amp", "amp"), ("center", "center"), ("element", "element"),
                      ("wave_bias", "wavebias"), ("blend", "blend")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "type" in params:
        applied["type"] = _str_menu_set(n, "type", str(params["type"]), _PHASOR_TYPE)
    if "wave_type" in params:
        applied["wave_type"] = _str_menu_set(n, "wavetype", str(params["wave_type"]), _PHASOR_WAVETYPE)
    if "rotation" in params:
        applied["rotation"] = _str_menu_set(n, "firstrotmenu", str(params["rotation"]), _PHASOR_FIRSTROT)
    if "offset" in params:
        applied["offset"] = _set_tuple(n, "offset", params["offset"])
    if "seed" in params:
        applied["seed"] = _try_set(n, "seed", int(clamp(int(params["seed"]), 0, 1000000)))
    if "kernels" in params:
        applied["kernels"] = _try_set(n, "kernels", int(clamp(int(params["kernels"]), 1, 64)))
    if "use_3d" in params:
        applied["use_3d"] = _try_set(n, "use3d", bool(params["use_3d"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_height_to_ao")
def cop_height_to_ao(params):
    """COP filter (terrain relief): ambient-occlusion bake from a mono height layer (Height to Ambient
    Occlusion). height_scale, view_radius (ray distance), step_scale, ray_count, hemisphere. Chains
    after `input`. BUILT."""
    n = child_after(params["input"], "heighttoambientocclusion", params.get("name"))
    applied = {}
    for key, base in (("height_scale", "heightscale"), ("view_radius", "viewradius"),
                      ("step_scale", "stepscale")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "ray_count" in params:
        applied["ray_count"] = _try_set(n, "axiscount", int(clamp(int(params["ray_count"]), 1, 256)))
    if "hemisphere" in params:
        applied["hemisphere"] = _try_set(n, "dohemisphere", bool(params["hemisphere"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_height_to_shadow")
def cop_height_to_shadow(params):
    """COP filter (terrain relief): cast-shadow map from a mono height layer + light profile (Height
    to Shadow). light_type (disk/sphere/directional), coord_mode (spherical/cartesian), azimuth/
    altitude/distance (spherical) or position (float3, cartesian), radius, height_scale, view_radius,
    step_scale. Chains after `input`. BUILT."""
    n = child_after(params["input"], "heighttoshadow", params.get("name"))
    applied = {}
    if "light_type" in params:
        applied["light_type"] = _str_menu_set(n, "type", str(params["light_type"]), _SHADOW_TYPE)
    if "coord_mode" in params:
        applied["coord_mode"] = _str_menu_set(n, "use", str(params["coord_mode"]), _SHADOW_USE)
    for key, base in (("radius", "radius"), ("height_scale", "heightmapscale"), ("azimuth", "azimuth"),
                      ("altitude", "altitude"), ("distance", "distance"), ("view_radius", "viewradius"),
                      ("step_scale", "stepscale")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "position" in params:
        applied["position"] = _set_tuple(n, "position", params["position"])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_curvature")
def cop_curvature(params):
    """COP filter (terrain relief): surface curvature from a normal/height layer (Curvature). method
    (index 0/1), curvature_type (gaussian/mean/principal_max/principal_min), output_type (index 0/1/2),
    normal_type (signed/offset), prescale/postscale, kernel, read_outside, normalize + min/max clamp.
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "curvature", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "method" in params:
        applied["method"] = _try_set(n, "method", int(clamp(int(params["method"]), 0, 1)))
    if "curvature_type" in params:
        applied["curvature_type"] = _str_menu_set(n, "curvaturetype", str(params["curvature_type"]), _CURVATURE_TYPE)
    if "output_type" in params:
        applied["output_type"] = _try_set(n, "outputtype", int(clamp(int(params["output_type"]), 0, 2)))
    if "normal_type" in params:
        applied["normal_type"] = _str_menu_set(n, "normaltype", str(params["normal_type"]), _LIGHT_NORMALTYPE)
    for key, base in (("prescale", "prescale"), ("postscale", "postscale"), ("min", "min"), ("max", "max")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "kernel" in params:
        applied["kernel"] = _try_set(n, "kernel", int(clamp(int(params["kernel"]), 1, 64)))
    if "read_outside" in params:
        applied["read_outside"] = _try_set(n, "readoutside", bool(params["read_outside"]))
    if "normalize" in params:
        applied["normalize"] = _try_set(n, "normalize", bool(params["normalize"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_slope_dir")
def cop_slope_dir(params):
    """COP filter (terrain relief): slope-direction (aspect) field from a mono height layer (Slope
    Direction). angle (post-rotation), scale (height-scale adjust), read_outside, kernel (derivative
    neighborhood). Chains after `input`. BUILT."""
    n = child_after(params["input"], "slopedir", params.get("name"))
    applied = {}
    if "angle" in params:
        applied["angle"] = _try_set(n, "angle", float(params["angle"]))
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "read_outside" in params:
        applied["read_outside"] = _try_set(n, "readoutside", bool(params["read_outside"]))
    if "kernel" in params:
        applied["kernel"] = _try_set(n, "kernel", int(clamp(int(params["kernel"]), 1, 64)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_resample")
def cop_resample(params):
    """COP filter: resize/resample a layer (Resample). size_control (res/aspect/pixel), base_size
    (parm/input), resolution (int [w,h]), aspect (float2) + aspect_preset, pixel_size, scale,
    fixed_side, filter (reconstruction), stretch mode, reframe. Chains after `input`. BUILT."""
    n = child_after(params["input"], "resample", params.get("name"))
    applied = {}
    if "size_control" in params:
        applied["size_control"] = _str_menu_set(n, "sizecontrol", str(params["size_control"]), _RESAMPLE_SIZECONTROL)
    if "base_size" in params:
        applied["base_size"] = _str_menu_set(n, "basesize", str(params["base_size"]), _RESAMPLE_BASESIZE)
    if "resolution" in params:
        r = params["resolution"]
        r = list(r) if isinstance(r, (list, tuple)) else [int(r), int(r)]
        pt = n.parmTuple("resolution")
        if pt is not None:
            try:
                pt.set((int(r[0]), int(r[1])))
                applied["resolution"] = True
            except Exception:
                applied["resolution"] = False
    if "aspect" in params:
        applied["aspect"] = _set_tuple(n, "aspect", params["aspect"])
    if "aspect_preset" in params:
        applied["aspect_preset"] = _str_menu_set(n, "aspectmenu", str(params["aspect_preset"]), _RESAMPLE_ASPECTMENU)
    if "pixel_size" in params:
        applied["pixel_size"] = _try_set(n, "pixelsize", float(params["pixel_size"]))
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "fixed_side" in params:
        applied["fixed_side"] = _str_menu_set(n, "fixedside", str(params["fixed_side"]), _RESAMPLE_FIXEDSIDE)
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    if "stretch" in params:
        applied["stretch"] = _str_menu_set(n, "stretch", str(params["stretch"]), _RESAMPLE_STRETCH)
    if "reframe" in params:
        applied["reframe"] = _try_set(n, "reframe", bool(params["reframe"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_mono")
def cop_mono(params):
    """COP filter: combine channels into a single mono/luminance layer (Mono). op (lum/ntsclum/hdtvlum/
    average/max/min/magnitude/hue/saturation/value/red/green/blue/comp4/custom); supplying `weight`
    (float4) sets op=custom + per-channel weights; normalize_weight. Chains after `input`. BUILT."""
    n = child_after(params["input"], "mono", params.get("name"))
    applied = {}
    if "op" in params:
        applied["op"] = _str_menu_set(n, "op", str(params["op"]), _MONO_OP)
    if "weight" in params:
        _str_menu_set(n, "op", "custom", _MONO_OP)
        applied["weight"] = _set_tuple(n, "weight", params["weight"])
    if "normalize_weight" in params:
        applied["normalize_weight"] = _try_set(n, "normalizeweight", bool(params["normalize_weight"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_hextile")
def cop_hextile(params):
    """COP filter: hexagonal seamless texture tiling (Hex Tile). The texture wires to the `textotile`
    input (index 3); size (float2), scale/scale_rand, rotate/rot_rand, seed, contrast/contrast_falloff,
    weight_exp control per-cell randomization + blending. Omit `input` to cook bare. BUILT."""
    if params.get("input"):
        tex = resolve_node(params["input"])
        n = tex.parent().createNode("hextile", params.get("name"))
        n.moveToGoodPosition()
        n.setInput(3, tex)  # 'textotile' — hextile's texture input is index 3, not 0
        wired = n.input(3) is not None
    else:
        n = _cop_gen("hextile", params.get("name"))
        wired = False
    applied = {}
    if "size" in params:
        applied["size"] = _set_tuple(n, "size", params["size"])
    for key, base in (("scale", "scale"), ("scale_rand", "scalerand"), ("rotate", "rot"),
                      ("rot_rand", "rotrand"), ("seed", "seed"), ("contrast", "contrast"),
                      ("contrast_falloff", "contrast_falloff"), ("weight_exp", "weightexp")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "tex_wired": wired, "applied": applied}


# ── COP: normal-map lane + edge-detect/stylize filters + coordinate util + random
#    generators (menu storage-kinds + tuple lengths + input arity live-probed).
#    Numeric-token menus set by int; empty runtime menus set as
#    plain int; word-token menus via _str_menu_set (evalAsString-gated). Data-only. ────────────────
_CONVERTNORMAL_CONV = ("tosigned", "tooffset")
_SWIRL_PARAMMODE = ("uniform", "random")
_SWIRL_WRAPMODE = ("auto", "off", "on")
_POLAR_ANGLEUNIT = ("rad", "deg", "tau")
_RANGEMETHOD = ("minmax", "ramp", "specific")
_COLORMODEL = ("rgb", "hsv")


def _edge_common(n, params, applied):
    """Shared edge-detect knobs (thickness_scale / weight_spread / blur / min_probe_radius)."""
    for key, base in (("thickness_scale", "thickscale"), ("weight_spread", "weightspread"),
                      ("blur", "blur")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "min_probe_radius" in params:
        applied["min_probe_radius"] = _try_set(n, "minproberad", int(clamp(int(params["min_probe_radius"]), 0, 64)))


@endpoint("cop_convert_normal")
def cop_convert_normal(params):
    """COP filter: convert a normal-map layer between encodings (Convert Normal). conversion (tosigned
    -1..1 / tooffset 0..1), normalize, offset (float3), scale (float3). Chains after `input`. BUILT."""
    n = child_after(params["input"], "convertnormal", params.get("name"))
    applied = {}
    if "conversion" in params:
        applied["conversion"] = _str_menu_set(n, "conversion", str(params["conversion"]), _CONVERTNORMAL_CONV)
    if "normalize" in params:
        applied["normalize"] = _try_set(n, "normalize", bool(params["normalize"]))
    if "offset" in params:
        applied["offset"] = _set_tuple(n, "offset", params["offset"])
    if "scale" in params:
        applied["scale"] = _set_tuple(n, "scale", params["scale"])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_combine_normals")
def cop_combine_normals(params):
    """COP combiner: layer/blend two tangent-space normal maps (Combine Normals). `input` = base
    (input 0), `fg` = detail (input 1); normal_type (index 0/1), method (index 0/1/2), mask (mix).
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "combinenormals", params.get("name"))
    fg = resolve_node(params["fg"])
    ref = fg if fg.parent().path() == n.parent().path() else bridge_into(fg, n.parent(), name_hint="fg")
    n.setInput(1, ref)
    applied = {}
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    if "normal_type" in params:
        applied["normal_type"] = _try_set(n, "normaltype", int(clamp(int(params["normal_type"]), 0, 1)))
    if "method" in params:
        applied["method"] = _try_set(n, "method", int(clamp(int(params["method"]), 0, 2)))
    return {"node": n.path(), "fg_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_edge_detect_normal")
def cop_edge_detect_normal(params):
    """COP filter: ink/outline edges from a normal layer's angular discontinuities (Edge Detect
    Normal). tolerance (normal angle), thickness_scale, weight_spread, blur, min_probe_radius. Chains
    after `input`. BUILT."""
    n = child_after(params["input"], "edgedetectnormal", params.get("name"))
    applied = {}
    if "tolerance" in params:
        applied["tolerance"] = _try_set(n, "normtolerance", float(params["tolerance"]))
    _edge_common(n, params, applied)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_edge_detect_depth")
def cop_edge_detect_depth(params):
    """COP filter: crease/occlusion edges from Z-depth steps (Edge Detect Depth). tolerance (depth
    step), thickness_scale, weight_spread, blur, min_probe_radius. Chains after `input`. BUILT."""
    n = child_after(params["input"], "edgedetectdepth", params.get("name"))
    applied = {}
    if "tolerance" in params:
        applied["tolerance"] = _try_set(n, "depthtolerance", float(params["tolerance"]))
    _edge_common(n, params, applied)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_edge_detect_contour")
def cop_edge_detect_contour(params):
    """COP filter: silhouette/contour edges from value discontinuities (Edge Detect Contour).
    tolerance (value step), thickness_scale, weight_spread, blur, min_probe_radius. Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "edgedetectcontour", params.get("name"))
    applied = {}
    if "tolerance" in params:
        applied["tolerance"] = _try_set(n, "conttolerance", float(params["tolerance"]))
    _edge_common(n, params, applied)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_swirl")
def cop_swirl(params):
    """COP filter: spiral + lens-bulge deformation (Swirl). The source texture wires to input 1 (input
    0 is an optional size reference). mode (uniform/random), wrap (auto/off/on), strength, bulge,
    radius, blend_region, rotate, roundness, tile_size (float2), translation (float2); random mode adds
    central_value, scatter, seed. BUILT."""
    tex = resolve_node(params["input"])
    n = tex.parent().createNode("swirl", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, tex)  # 'source' — swirl's texture input is index 1, not 0 (index 0 = size_ref)
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "parametermode", str(params["mode"]), _SWIRL_PARAMMODE)
    if "wrap" in params:
        applied["wrap"] = _str_menu_set(n, "wrapmode", str(params["wrap"]), _SWIRL_WRAPMODE)
    for key, base in (("strength", "strength"), ("bulge", "bulge"), ("radius", "radius"),
                      ("blend_region", "blendregion"), ("rotate", "rotate"), ("roundness", "roundness"),
                      ("central_value", "centralvalue"), ("scatter", "scatter")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "tile_size" in params:
        applied["tile_size"] = _set_tuple(n, "tilesize", params["tile_size"])
    if "translation" in params:
        applied["translation"] = _set_tuple(n, "translation", params["translation"])
    if "seed" in params:
        applied["seed"] = _try_set(n, "seed", int(clamp(int(params["seed"]), 0, 1000000)))
    return {"node": n.path(), "src_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_pixelate")
def cop_pixelate(params):
    """COP filter: mosaic / block-quantize a layer (Pixelate). mode (index 0/1), units (image/pixels),
    block_size or num_blocks (int [x,y]), offset (float2), mask; preblur + preblur_size. Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "pixelate", params.get("name"))
    applied = {}
    if "mode" in params:
        applied["mode"] = _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 1)))
    if "units" in params:
        applied["units"] = _str_menu_set(n, "units", str(params["units"]), _UNITS)
    if "block_size" in params:
        applied["block_size"] = _try_set(n, "blocksize", float(params["block_size"]))
    if "num_blocks" in params:
        r = params["num_blocks"]
        r = list(r) if isinstance(r, (list, tuple)) else [int(r), int(r)]
        pt = n.parmTuple("numblocks")
        if pt is not None:
            try:
                pt.set((int(r[0]), int(r[1])))
                applied["num_blocks"] = True
            except Exception:
                applied["num_blocks"] = False
    if "offset" in params:
        applied["offset"] = _set_tuple(n, "offset", params["offset"])
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    if "preblur" in params:
        applied["preblur"] = _try_set(n, "dopreblur", bool(params["preblur"]))
    if "preblur_size" in params:
        _try_set(n, "dopreblur", True)
        applied["preblur_size"] = _try_set(n, "size", float(params["preblur_size"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_defocus")
def cop_defocus(params):
    """COP filter: physically-parameterised camera defocus + bokeh (Defocus). REQUIRES a `depth` layer
    on input 1 (per-pixel blur amount). focal_length, focus_distance, fstop, radius, bokeh_radius,
    bokeh_gain, bokeh_res, resample, gamma, depth_blend, mask. Chains after `input`. BUILT."""
    n = child_after(params["input"], "defocus", params.get("name"))
    depth = resolve_node(params["depth"])
    dref = depth if depth.parent().path() == n.parent().path() else bridge_into(depth, n.parent(), name_hint="depth")
    n.setInput(1, dref)
    applied = {}
    for key, base in (("focal_length", "focallength"), ("focus_distance", "focusdistance"),
                      ("fstop", "fstop"), ("radius", "radius"), ("bokeh_radius", "bokehradius"),
                      ("bokeh_gain", "bokehgain"), ("resample", "resample"), ("gamma", "gamma")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "bokeh_res" in params:
        applied["bokeh_res"] = _try_set(n, "bokehres", int(clamp(int(params["bokeh_res"]), 1, 4096)))
    if "depth_blend" in params:
        applied["depth_blend"] = _try_set(n, "dodepthblend", bool(params["depth_blend"]))
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "depth_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_flip")
def cop_flip(params):
    """COP filter: mirror a layer (Flip). horizontal (xflip), vertical (yflip), diagonal (flop), mask.
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "flip", params.get("name"))
    applied = {}
    if "horizontal" in params:
        applied["horizontal"] = _try_set(n, "xflip", bool(params["horizontal"]))
    if "vertical" in params:
        applied["vertical"] = _try_set(n, "yflip", bool(params["vertical"]))
    if "diagonal" in params:
        applied["diagonal"] = _try_set(n, "flop", bool(params["diagonal"]))
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_polar_to_uv")
def cop_polar_to_uv(params):
    """COP generator: convert polar (angle, length) coordinates to a UV layer (Polar to UV).
    angle_unit (rad/deg/tau), angle, length. Cooks bare in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("polartouv", params.get("name"))
    applied = {}
    if "angle_unit" in params:
        applied["angle_unit"] = _str_menu_set(n, "angleunit", str(params["angle_unit"]), _POLAR_ANGLEUNIT)
    if "angle" in params:
        applied["angle"] = _try_set(n, "angle", float(params["angle"]))
    if "length" in params:
        applied["length"] = _try_set(n, "length", float(params["length"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_random_mono")
def cop_random_mono(params):
    """COP generator: random mono field (Random Mono). range_method (minmax/ramp/specific), min/max,
    per_pixel, seed, time. Cooks bare in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("randommono", params.get("name"))
    applied = {}
    if "range_method" in params:
        applied["range_method"] = _str_menu_set(n, "rangemethod", str(params["range_method"]), _RANGEMETHOD)
    for key, base in (("min", "min"), ("max", "max"), ("seed", "seed"), ("time", "time")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "per_pixel" in params:
        applied["per_pixel"] = _try_set(n, "perpixel", bool(params["per_pixel"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_random_rgb")
def cop_random_rgb(params):
    """COP generator: random colour field (Random RGB). range_method (minmax/ramp/specific),
    color_model (rgb/hsv), base_color (float3, enables base colour), per-channel random ranges
    rand_r/g/b or rand_hue/sat/val (each float2 min/max), per_pixel, seed. Cooks bare in the shared
    /obj/cops copnet. BUILT."""
    n = _cop_gen("randomrgb", params.get("name"))
    applied = {}
    if "range_method" in params:
        applied["range_method"] = _str_menu_set(n, "rangemethod", str(params["range_method"]), _RANGEMETHOD)
    if "color_model" in params:
        applied["color_model"] = _str_menu_set(n, "randomcolormodel", str(params["color_model"]), _COLORMODEL)
    if "base_color" in params:
        _try_set(n, "dobasecolor", True)
        applied["base_color"] = _set_tuple(n, "basecolor", params["base_color"])
    for key, base in (("rand_r", "randr"), ("rand_g", "randg"), ("rand_b", "randb"),
                      ("rand_hue", "randhue"), ("rand_sat", "randsat"), ("rand_val", "randval")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    if "per_pixel" in params:
        applied["per_pixel"] = _try_set(n, "perpixel", bool(params["per_pixel"]))
    if "seed" in params:
        applied["seed"] = _try_set(n, "seed", float(params["seed"]))
    return {"node": n.path(), "applied": applied}


# ── COP: texturing/projection lane + world-space 3D noise (input indices, menu kinds, tuple
#    lengths live-probed). Texture-input index varies per node:
#    triplanar->2, cornerpin->1, triplanarhextile->0. 3D-noise `off` is float3; noisetype3d leads with
#    `simplex` (NOT the 2D `torus`). Data-only. ──────────────────────────────────────────────────────
_NOISE_TYPE_3D = ("simplex", "perlin", "worleyA", "worleyB", "white", "alligator")
_UVSPACE = ("texture", "image", "pixel")
_UVBORDER = ("clamp", "mirror", "wrap", "extend")
_POSMAP_SOURCE = ("pos", "origin", "view")
_TRIPLANAR_TEXTYPE = ("singletex", "uniformtex")
_CORNERPIN_UNITS = ("image", "texture")


@endpoint("cop_triplanar")
def cop_triplanar(params):
    """COP filter: world-space triplanar projection of a texture (Triplanar). Wires `position` -> input
    0, `normal` (world-space) -> input 1, `texture` -> input 2 (all required — the projection needs a
    position + normal pass, e.g. from cop_pos_map). texture_type (singletex/uniformtex), global
    scale/rotate/offset (float2), per-axis x/y/z scale/rotate/offset (offsets float2), blend. BUILT."""
    tex = resolve_node(params["texture"])
    n = tex.parent().createNode("triplanar", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(2, tex)  # 'texture' is input index 2 on triplanar
    pos = resolve_node(params["position"])
    n.setInput(0, pos if pos.parent().path() == n.parent().path() else bridge_into(pos, n.parent(), name_hint="pos"))
    nrm = resolve_node(params["normal"])
    n.setInput(1, nrm if nrm.parent().path() == n.parent().path() else bridge_into(nrm, n.parent(), name_hint="nrm"))
    applied = {}
    if "texture_type" in params:
        applied["texture_type"] = _str_menu_set(n, "texturetype", str(params["texture_type"]), _TRIPLANAR_TEXTYPE)
    for key, base in (("global_scale", "globalscale"), ("global_rotate", "globalrotate"),
                      ("blend", "triplanarblend"), ("x_scale", "xscale"), ("y_scale", "yscale"),
                      ("z_scale", "zscale"), ("x_rotate", "xrotate"), ("y_rotate", "yrotate"),
                      ("z_rotate", "zrotate")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("global_offset", "globaloffset"), ("x_offset", "xoffset"),
                      ("y_offset", "yoffset"), ("z_offset", "zoffset")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    return {"node": n.path(), "tex_wired": n.input(2) is not None,
            "pos_wired": n.input(0) is not None, "normal_wired": n.input(1) is not None,
            "applied": applied}


@endpoint("cop_triplanar_uv")
def cop_triplanar_uv(params):
    """COP filter: triplanar UV coordinates from a world-position + normal pass (Triplanar UV). Wires
    `position` -> input 0, `normal` -> input 1 (both required, e.g. from cop_pos_map). blend =
    projection-weight smoothing. BUILT."""
    pos = resolve_node(params["position"])
    n = pos.parent().createNode("triplanaruv", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(0, pos)
    nrm = resolve_node(params["normal"])
    n.setInput(1, nrm if nrm.parent().path() == n.parent().path() else bridge_into(nrm, n.parent(), name_hint="nrm"))
    applied = {}
    if "blend" in params:
        applied["blend"] = _try_set(n, "blend", float(params["blend"]))
    return {"node": n.path(), "pos_wired": n.input(0) is not None,
            "normal_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_triplanar_hextile")
def cop_triplanar_hextile(params):
    """COP filter: triplanar projection with per-cell hex-tile randomization (Triplanar Hex Tile). The
    texture wires to input 0. size (float2), scale/scale_rand, rotate/rot_rand, seed, contrast/
    contrast_falloff, weight_exp, blend. Chains after `input`. BUILT."""
    n = child_after(params["input"], "triplanarhextile", params.get("name"))
    applied = {}
    if "size" in params:
        applied["size"] = _set_tuple(n, "size", params["size"])
    for key, base in (("scale", "scale"), ("scale_rand", "scalerand"), ("rotate", "rot"),
                      ("rot_rand", "rotrand"), ("seed", "seed"), ("contrast", "contrast"),
                      ("contrast_falloff", "contrast_falloff"), ("weight_exp", "weightexp"),
                      ("blend", "blend")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_uv_map")
def cop_uv_map(params):
    """COP generator: generate a UV layer (UV Map). uv_space (texture/image/pixel), u_border/v_border
    (clamp/mirror/wrap/extend), u_shift/u_cycle, v_shift/v_cycle. Cooks bare in the shared /obj/cops
    copnet. BUILT."""
    n = _cop_gen("uvmap", params.get("name"))
    applied = {}
    if "uv_space" in params:
        applied["uv_space"] = _str_menu_set(n, "uvspace", str(params["uv_space"]), _UVSPACE)
    if "u_border" in params:
        applied["u_border"] = _str_menu_set(n, "uborder", str(params["u_border"]), _UVBORDER)
    if "v_border" in params:
        applied["v_border"] = _str_menu_set(n, "vborder", str(params["v_border"]), _UVBORDER)
    for key, base in (("u_shift", "ushift"), ("u_cycle", "ucycle"), ("v_shift", "vshift"),
                      ("v_cycle", "vcycle")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pos_map")
def cop_pos_map(params):
    """COP generator: generate a world-position layer (Position Map). source (pos/origin/view), per-axis
    x/y/z border (clamp/mirror/wrap/extend), x/y/z shift + cycle, signature (mono/vec3/...). Cooks bare
    in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("posmap", params.get("name"))
    applied = {}
    if "source" in params:
        applied["source"] = _str_menu_set(n, "source", str(params["source"]), _POSMAP_SOURCE)
    for key, base in (("x_border", "xborder"), ("y_border", "yborder"), ("z_border", "zborder")):
        if key in params:
            applied[key] = _str_menu_set(n, base, str(params[key]), _UVBORDER)
    for key, base in (("x_shift", "xshift"), ("x_cycle", "xcycle"), ("y_shift", "yshift"),
                      ("y_cycle", "ycycle"), ("z_shift", "zshift"), ("z_cycle", "zcycle")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_corner_pin")
def cop_corner_pin(params):
    """COP filter: perspective corner-pin warp (Corner Pin). The texture wires to input 1. units
    (image/texture — corner-coordinate space), bl/br/tl/tr = the four corners (float2). BUILT."""
    tex = resolve_node(params["input"])
    n = tex.parent().createNode("cornerpin", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, tex)  # 'texture' is input index 1 on cornerpin
    applied = {}
    units = str(params.get("units", "image"))
    if "units" in params:
        applied["units"] = _str_menu_set(n, "units", units, _CORNERPIN_UNITS)
    suffix = {"image": "", "texture": "_texture"}.get(units, "")
    for corner in ("bl", "br", "tl", "tr"):
        if corner in params:
            applied[corner] = _set_tuple(n, corner + suffix, params[corner])
    return {"node": n.path(), "tex_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_lens_distort")
def cop_lens_distort(params):
    """COP filter: radial + tangential lens distortion / undistortion (Lens Distort). k1..k6 = radial
    coefficients, p1/p2 = tangential, center (float2), scale (float2), aspect, mask. Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "lensdistort", params.get("name"))
    applied = {}
    for key in ("k1", "k2", "k3", "k4", "k5", "k6", "p1", "p2", "aspect"):
        if key in params:
            applied[key] = _try_set(n, key, float(params[key]))
    if "center" in params:
        applied["center"] = _set_tuple(n, "center", params["center"])
    if "scale" in params:
        applied["scale"] = _set_tuple(n, "scale", params["scale"])
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_uv_to_polar")
def cop_uv_to_polar(params):
    """COP filter: convert a UV layer to polar (angle, length) coordinates (UV to Polar) — inverse of
    cop_polar_to_uv. angle_unit (rad/deg/tau). Chains after `input` (a UV layer). BUILT."""
    n = child_after(params["input"], "uvtopolar", params.get("name"))
    applied = {}
    if "angle_unit" in params:
        applied["angle_unit"] = _str_menu_set(n, "angleunit", str(params["angle_unit"]), _POLAR_ANGLEUNIT)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_fractal_noise_3d")
def cop_fractal_noise_3d(params):
    """COP generator: world-space (3D-sampled) fractal noise (Fractal Noise 3D). noise_type (simplex/
    perlin/worleyA/worleyB/white/alligator), metric, amp/center/contrast, element_size, octaves,
    lacunarity, roughness, jitter, offset (float3); post bias/gain (auto-enabled), complement. Cooks
    bare in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("fractalnoise3d", params.get("name"))
    applied = {}
    if "noise_type" in params:
        applied["noise_type"] = _str_menu_set(n, "noisetype", str(params["noise_type"]), _NOISE_TYPE_3D)
    if "metric" in params:
        applied["metric"] = _str_menu_set(n, "metric", str(params["metric"]), _METRIC)
    for key, base in (("amp", "amp"), ("center", "center"), ("contrast", "contrast"),
                      ("element_size", "elementsize"), ("octaves", "oct"), ("lacunarity", "lac"),
                      ("roughness", "rough"), ("jitter", "jitter")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "offset" in params:
        applied["offset"] = _set_tuple(n, "off", params["offset"])
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "bias" in params:
        _try_set(n, "post_dobias", True)
        applied["bias"] = _try_set(n, "post_bias", float(params["bias"]))
    if "gain" in params:
        _try_set(n, "post_dogain", True)
        applied["gain"] = _try_set(n, "post_gain", float(params["gain"]))
    if "complement" in params:
        applied["complement"] = _try_set(n, "post_docomplement", bool(params["complement"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_worley_noise_3d")
def cop_worley_noise_3d(params):
    """COP generator: world-space cellular/Worley noise (Worley Noise 3D). element_size/element_scale,
    jitter/jitter_scale, metric, offset (float3); post bias/gain (auto-enabled), complement. Cooks bare
    in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("worleynoise3d", params.get("name"))
    applied = {}
    for key, base in (("element_size", "elementsize"), ("element_scale", "elementscale"),
                      ("jitter", "jitter"), ("jitter_scale", "jitterscale")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "metric" in params:
        applied["metric"] = _str_menu_set(n, "metric", str(params["metric"]), _METRIC)
    if "offset" in params:
        applied["offset"] = _set_tuple(n, "off", params["offset"])
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "bias" in params:
        _try_set(n, "post_dobias", True)
        applied["bias"] = _try_set(n, "post_bias", float(params["bias"]))
    if "gain" in params:
        _try_set(n, "post_dogain", True)
        applied["gain"] = _try_set(n, "post_gain", float(params["gain"]))
    if "complement" in params:
        applied["complement"] = _try_set(n, "post_docomplement", bool(params["complement"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_crystal_noise_3d")
def cop_crystal_noise_3d(params):
    """COP generator: world-space faceted crystalline Worley noise (Crystal Noise 3D). metric, amp/
    center/contrast, jitter, element_size, secondary + metric2, flatten_faces, offset (float3),
    signature. Cooks bare in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("crystalnoise3d", params.get("name"))
    applied = {}
    if "metric" in params:
        applied["metric"] = _str_menu_set(n, "metric", str(params["metric"]), _METRIC)
    for key, base in (("amp", "amp"), ("center", "center"), ("contrast", "contrast"),
                      ("jitter", "jitter"), ("element_size", "elementsize")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "secondary" in params:
        applied["secondary"] = _try_set(n, "enablesecondary", bool(params["secondary"]))
    if "metric2" in params:
        _try_set(n, "enablesecondary", True)
        applied["metric2"] = _str_menu_set(n, "metric2", str(params["metric2"]), _METRIC)
    if "flatten_faces" in params:
        applied["flatten_faces"] = _try_set(n, "flattenfaces", bool(params["flatten_faces"]))
    if "offset" in params:
        applied["offset"] = _set_tuple(n, "off", params["offset"])
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_cloud_noise_3d")
def cop_cloud_noise_3d(params):
    """COP generator: world-space billowy cloud noise (Cloud Noise 3D). amp/center, element_size,
    offset (float3 sample offset), max_octaves, lacunarity, roughness, distort, stretch (float3),
    droop (auto-enables dodroop), fold, signature; post bias (auto-enabled). Cooks bare in the shared
    /obj/cops copnet. BUILT."""
    n = _cop_gen("cloudnoise3d", params.get("name"))
    applied = {}
    for key, base in (("amp", "amp"), ("center", "center"), ("element_size", "elementsize"),
                      ("lacunarity", "lac"), ("roughness", "rough"), ("distort", "distort")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "offset" in params:
        applied["offset"] = _set_tuple(n, "offset", params["offset"])
    if "stretch" in params:
        applied["stretch"] = _set_tuple(n, "stretch", params["stretch"])
    if "max_octaves" in params:
        applied["max_octaves"] = _try_set(n, "max_octaves", int(clamp(int(params["max_octaves"]), 1, 20)))
    if "droop" in params:
        _try_set(n, "dodroop", True)
        applied["droop"] = _try_set(n, "droop", float(params["droop"]))
    if "fold" in params:
        applied["fold"] = _try_set(n, "dofold", bool(params["fold"]))
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "bias" in params:
        _try_set(n, "post_dobias", True)
        applied["bias"] = _try_set(n, "post_bias", float(params["bias"]))
    return {"node": n.path(), "applied": applied}


# ── COP: general-purpose util lane — transform family + conversions + cleanup
#    (menu kinds, tuple lengths, input arity live-probed). bend's
#    source texture is input 1 (input0=size_ref). Empty runtime int/string menus set as plain int/str;
#    idtomask.rangemode is a numeric int-menu. Data-only. ──────────────────────────────────────────
_SPACETRANSFORM_VECTYPE = ("position", "vector")
_SPACE = ("buffer", "pixel", "texture", "image", "world")
_BEND_MODE = ("corners", "sides", "angle")
_FILLCONNECTED_SOURCE = ("value", "sample", "first", "last")
_ILLPIXEL_METHOD = ("fixblend", "fixzero", "highlight", "isolate")
_ILLPIXEL_DETECT = ("d_nan", "d_inf", "both", "custom")
_ILLPIXEL_RULE = ("less", "lessequal", "greater", "greaterequal", "equal")
_BOUNDRECT_SIDE = ("less", "greater")
_GEOUNITS = ("image", "texture", "pixel")
_HYPERBOLIC_MAPPING = ("conformal", "elliptic grid", "squircle", "equalarea")


@endpoint("cop_xform_2d")
def cop_xform_2d(params):
    """COP filter: 2D image transform (Transform 2D). translate (float2), rotate, scale_xy (float2) +
    uniform scale, shear, pivot (float2); xform_order, border, filter, invert. Chains after `input`.
    BUILT."""
    n = child_after(params["input"], "xform2d", params.get("name"))
    applied = {}
    for key, base in (("translate", "t"), ("scale_xy", "s"), ("pivot", "p")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    for key, base in (("rotate", "rz"), ("scale", "scale"), ("shear", "shear1")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "xform_order" in params:
        applied["xform_order"] = _str_menu_set(n, "xOrd", str(params["xform_order"]), _XFORM_ORD)
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _XFORM_BORDER)
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    if "invert" in params:
        applied["invert"] = _try_set(n, "invertxform", bool(params["invert"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_vector_xform")
def cop_vector_xform(params):
    """COP filter: transform the 3-vector VALUES in a layer (Vector Transform) — for normal/position/
    velocity layers. translate/rotate/scale_xyz/shear/pivot (each float3), uniform scale, xform_order,
    rot_order, invert. Chains after `input`. BUILT."""
    n = child_after(params["input"], "vectorxform", params.get("name"))
    applied = {}
    for key, base in (("translate", "t"), ("rotate", "r"), ("scale_xyz", "s"), ("shear", "shear"),
                      ("pivot", "p")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "xform_order" in params:
        applied["xform_order"] = _str_menu_set(n, "xOrd", str(params["xform_order"]), _XFORM_ORD)
    if "rot_order" in params:
        applied["rot_order"] = _str_menu_set(n, "rOrd", str(params["rot_order"]), _ROT_ORD)
    if "invert" in params:
        applied["invert"] = _try_set(n, "invertxform", bool(params["invert"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_vector_xform_2d")
def cop_vector_xform_2d(params):
    """COP filter: transform the 2-vector VALUES in a layer (Vector Transform 2D) — for UV/flow layers.
    translate (float2), rotate, scale_xy (float2) + uniform scale, shear, pivot (float2), xform_order,
    invert. Chains after `input`. BUILT."""
    n = child_after(params["input"], "vectorxform2d", params.get("name"))
    applied = {}
    for key, base in (("translate", "t"), ("scale_xy", "s"), ("pivot", "p")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    for key, base in (("rotate", "rz"), ("scale", "scale"), ("shear", "shear1")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "xform_order" in params:
        applied["xform_order"] = _str_menu_set(n, "xOrd", str(params["xform_order"]), _XFORM_ORD)
    if "invert" in params:
        applied["invert"] = _try_set(n, "invertxform", bool(params["invert"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_space_transform")
def cop_space_transform(params):
    """COP filter: convert layer values between coordinate spaces (Space Transform). vector_type
    (position/vector), src_space + dst_space (buffer/pixel/texture/image/world). Chains after `input`.
    BUILT."""
    n = child_after(params["input"], "spacetransform", params.get("name"))
    applied = {}
    if "vector_type" in params:
        applied["vector_type"] = _str_menu_set(n, "vectype", str(params["vector_type"]), _SPACETRANSFORM_VECTYPE)
    if "src_space" in params:
        applied["src_space"] = _str_menu_set(n, "srcspace", str(params["src_space"]), _SPACE)
    if "dst_space" in params:
        applied["dst_space"] = _str_menu_set(n, "dstspace", str(params["dst_space"]), _SPACE)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_bend")
def cop_bend(params):
    """COP filter: bend/warp a layer (Bend). The source texture wires to input 1 (input 0 = size_ref).
    mode (corners/sides/angle); corners bottom_left/bottom_right/top_left/top_right (float2); sides
    bottom/top/left/right (float2); angle bend_angle + capture_origin (float2)/capture_direction/
    capture_length; both_directions. BUILT."""
    tex = resolve_node(params["input"])
    n = tex.parent().createNode("bend", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, tex)  # 'source' is input index 1 on bend (index 0 = size_ref)
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _BEND_MODE)
    for key, base in (("bottom_left", "bottomleft"), ("bottom_right", "bottomright"),
                      ("top_left", "topleft"), ("top_right", "topright"), ("bottom", "bottom"),
                      ("top", "top"), ("left", "left"), ("right", "right"),
                      ("capture_origin", "captureorigin")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    for key, base in (("bend_angle", "bendangle"), ("capture_direction", "capturedirection"),
                      ("capture_length", "capturelength")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "both_directions" in params:
        applied["both_directions"] = _try_set(n, "deforminbothdirections", bool(params["both_directions"]))
    return {"node": n.path(), "src_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_id_to_mask")
def cop_id_to_mask(params):
    """COP filter: build a 0/1 mask from selected IDs (ID to Mask). `input` = an ID layer (input 0).
    group (id spec string), invert; range_mode (index 0/1) + start/end (auto-enables range); random +
    probability + seed; threshold (auto-enables the image-mask). Chains after `input`. BUILT."""
    n = child_after(params["input"], "idtomask", params.get("name"))
    applied = {}
    if "group" in params:
        applied["group"] = _try_set(n, "group", str(params["group"]))
    if "invert" in params:
        applied["invert"] = _try_set(n, "invertmask", bool(params["invert"]))
    if any(k in params for k in ("range_mode", "start", "end")):
        _try_set(n, "enablerange", True)
    if "range_mode" in params:
        applied["range_mode"] = _try_set(n, "rangemode", int(clamp(int(params["range_mode"]), 0, 1)))
    if "start" in params:
        applied["start"] = _try_set(n, "start", int(params["start"]))
    if "end" in params:
        applied["end"] = _try_set(n, "end", int(params["end"]))
    if "random" in params:
        applied["random"] = _try_set(n, "enablerandom", bool(params["random"]))
    if "probability" in params:
        _try_set(n, "enablerandom", True)
        applied["probability"] = _try_set(n, "probability", clamp(float(params["probability"]), 0.0, 1.0))
    if "seed" in params:
        applied["seed"] = _try_set(n, "seed", int(params["seed"]))
    if "threshold" in params:
        _try_set(n, "enableimagemask", True)
        applied["threshold"] = _try_set(n, "threshold", float(params["threshold"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_mono_to_sdf")
def cop_mono_to_sdf(params):
    """COP filter: convert a mono layer to a signed-distance field about an iso threshold (Mono to
    SDF). invert, iso (threshold), iterations, tile_size. Chains after `input`. BUILT."""
    n = child_after(params["input"], "monotosdf", params.get("name"))
    applied = {}
    if "invert" in params:
        applied["invert"] = _try_set(n, "invert", bool(params["invert"]))
    if "iso" in params:
        applied["iso"] = _try_set(n, "iso", float(params["iso"]))
    if "iterations" in params:
        applied["iterations"] = _try_set(n, "niter", int(clamp(int(params["iterations"]), 1, 10000)))
    if "tile_size" in params:
        applied["tile_size"] = _try_set(n, "tilesize", int(clamp(int(params["tile_size"]), 1, 100000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_denoise_tvd")
def cop_denoise_tvd(params):
    """COP filter: total-variation diffusion denoise (Denoise TVD) — pure math, NOT an AI model.
    iterations, speed, mask. Chains after `input`. BUILT."""
    n = child_after(params["input"], "denoisetvd", params.get("name"))
    applied = {}
    if "iterations" in params:
        applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 10000)))
    if "speed" in params:
        applied["speed"] = _try_set(n, "speed", float(params["speed"]))
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_fill_connected")
def cop_fill_connected(params):
    """COP filter: flood-fill a connected region from a seed within a tolerance (Fill Connected).
    seed_location (float2), source_location (float2), tolerance, source (value/sample/first/last),
    color (float4), id. Chains after `input`. BUILT."""
    n = child_after(params["input"], "fillconnected", params.get("name"))
    applied = {}
    if "seed_location" in params:
        applied["seed_location"] = _set_tuple(n, "seedloc", params["seed_location"])
    if "source_location" in params:
        applied["source_location"] = _set_tuple(n, "sourceloc", params["source_location"])
    if "tolerance" in params:
        applied["tolerance"] = _try_set(n, "tol", float(params["tolerance"]))
    if "source" in params:
        applied["source"] = _str_menu_set(n, "source", str(params["source"]), _FILLCONNECTED_SOURCE)
    if "color" in params:
        applied["color"] = _set_tuple(n, "color", params["color"])
    if "id" in params:
        applied["id"] = _try_set(n, "id", int(params["id"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_ill_pixel")
def cop_ill_pixel(params):
    """COP filter: detect/fix/flag illegal pixels (Illegal Pixel). method (fixblend/fixzero/highlight/
    isolate), detect (d_nan/d_inf/both/custom), rule (less/lessequal/greater/greaterequal/equal),
    compare_value, highlight_color (float4). Chains after `input`. BUILT."""
    n = child_after(params["input"], "illpixel", params.get("name"))
    applied = {}
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _ILLPIXEL_METHOD)
    if "detect" in params:
        applied["detect"] = _str_menu_set(n, "detect", str(params["detect"]), _ILLPIXEL_DETECT)
    if "rule" in params:
        applied["rule"] = _str_menu_set(n, "rule", str(params["rule"]), _ILLPIXEL_RULE)
    if "compare_value" in params:
        applied["compare_value"] = _try_set(n, "compval", float(params["compare_value"]))
    if "highlight_color" in params:
        applied["highlight_color"] = _set_tuple(n, "highlightcolor", params["highlight_color"])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_bound_rect")
def cop_bound_rect(params):
    """COP filter: bounding-rectangle mask around pixels passing a threshold (Bound Rect). side (less/
    greater), threshold, fg/bg values, units (image/texture/pixel). Chains after `input`. BUILT."""
    n = child_after(params["input"], "boundrect", params.get("name"))
    applied = {}
    if "side" in params:
        applied["side"] = _str_menu_set(n, "side", str(params["side"]), _BOUNDRECT_SIDE)
    if "threshold" in params:
        applied["threshold"] = _try_set(n, "threshold", float(params["threshold"]))
    if "fg" in params:
        applied["fg"] = _try_set(n, "fg", float(params["fg"]))
    if "bg" in params:
        applied["bg"] = _try_set(n, "bg", float(params["bg"]))
    if "units" in params:
        applied["units"] = _str_menu_set(n, "geounits", str(params["units"]), _GEOUNITS)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_hyperbolic_tile")
def cop_hyperbolic_tile(params):
    """COP generator: hyperbolic (Poincaré-disk) regular-polygon tiling (Hyperbolic Tiling). iterations,
    polygon (sides), mapping (conformal/elliptic grid/squircle/equalarea), flattening, size,
    tile_fitting, rectanglize/stretch_to_fit/disk_mask. Cooks bare in the shared /obj/cops copnet.
    BUILT."""
    n = _cop_gen("hyperbolictile", params.get("name"))
    applied = {}
    if "iterations" in params:
        applied["iterations"] = _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 100)))
    if "polygon" in params:
        applied["polygon"] = _try_set(n, "polygon", int(clamp(int(params["polygon"]), 3, 100)))
    if "mapping" in params:
        applied["mapping"] = _str_menu_set(n, "mappingtype", str(params["mapping"]), _HYPERBOLIC_MAPPING)
    for key, base in (("flattening", "flattening"), ("size", "size"), ("tile_fitting", "tilefitting")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "rectanglize" in params:
        applied["rectanglize"] = _try_set(n, "rectanglize", bool(params["rectanglize"]))
    if "stretch_to_fit" in params:
        applied["stretch_to_fit"] = _try_set(n, "stretchtofit", bool(params["stretch_to_fit"]))
    if "disk_mask" in params:
        applied["disk_mask"] = _try_set(n, "diskmask", bool(params["disk_mask"]))
    return {"node": n.path(), "applied": applied}


# ── COP: convert/composite/project/util lane (menu kinds, tuple lengths, input arity live-
#    probed). Input indices: zcomp bg0/bgdepth1/fg2/fgdepth3,
#    projectonlayer target0/source1, copyxform shape->1, latticedeform source->1, surfacedither uv->0,
#    sample uv0/texture2. convertdepth vs zcomp menus have DIFFERENT token orders. Data-only. ────────
_DEPTH_ENC = ("depth", "dist", "height")            # convertdepth node
_ZCOMP_DEPTH = ("dist", "depth", "height")          # zcomp node — DIFFERENT order, own constant
_UVMAPBYID_MODE = ("uvmap", "center", "min", "max", "size")
_UVSPACE2 = ("texture", "image")
_AUTOSCALE = ("none", "fit")
_UVBORDER3 = ("clamp", "mirror", "wrap")
_CONTACT_VSTACK = ("toptobottom", "bottomtotop")
_CONTACT_HSTACK = ("lefttoright", "righttoleft")
_COPYXFORM_BLEND = ("over", "under", "add", "subtract", "multiply", "max", "min")
_LATTICE_MODE = ("linear", "smooth")
_DITHER_OUTPUT = ("mask", "sdf")
_PREFIXSUM_DIR = ("px", "mx", "py", "ny", "xy", "index")
_PREFIXSUM_OP = ("add", "min", "max", "count")
_PREFIXSUM_SCALE = ("none", "pixel", "texture", "image")
_LAYERPROP_PRECISION = ("b8", "b16", "b32")
_LAYERPROP_BORDER = ("constant", "clamp", "mirror", "wrap")
_LAYERPROP_TYPEINFO = ("none", "color", "position", "vector", "normal", "offsetnormal",
                       "texturecoord", "id", "mask", "sdf", "height")


@endpoint("cop_convert_depth")
def cop_convert_depth(params):
    """COP filter: convert a layer between depth / distance / height encodings (Convert Depth). source
    + dest (depth/dist/height), zero_depth. Chains after `input`. BUILT."""
    n = child_after(params["input"], "convertdepth", params.get("name"))
    applied = {}
    if "source" in params:
        applied["source"] = _str_menu_set(n, "source", str(params["source"]), _DEPTH_ENC)
    if "dest" in params:
        applied["dest"] = _str_menu_set(n, "dest", str(params["dest"]), _DEPTH_ENC)
    if "zero_depth" in params:
        applied["zero_depth"] = _try_set(n, "zerodepth", float(params["zero_depth"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_zcomp")
def cop_zcomp(params):
    """COP compositor: Z-depth composite two layers, nearest-surface wins (Z Composite). `input` = bg
    (input 0), `fg` -> input 2; optional `bg_depth` -> input 1, `fg_depth` -> input 3. depth_encoding
    (dist/depth/height), fg_offset. BUILT."""
    n = child_after(params["input"], "zcomp", params.get("name"))  # input = bg -> input 0
    fg = resolve_node(params["fg"])
    n.setInput(2, fg if fg.parent().path() == n.parent().path() else bridge_into(fg, n.parent(), name_hint="fg"))
    if params.get("bg_depth"):
        bd = resolve_node(params["bg_depth"])
        n.setInput(1, bd if bd.parent().path() == n.parent().path() else bridge_into(bd, n.parent(), name_hint="bgdepth"))
    if params.get("fg_depth"):
        fd = resolve_node(params["fg_depth"])
        n.setInput(3, fd if fd.parent().path() == n.parent().path() else bridge_into(fd, n.parent(), name_hint="fgdepth"))
    applied = {}
    if "depth_encoding" in params:
        applied["depth_encoding"] = _str_menu_set(n, "convertdepth", str(params["depth_encoding"]), _ZCOMP_DEPTH)
    if "fg_offset" in params:
        applied["fg_offset"] = _try_set(n, "fgoffset", float(params["fg_offset"]))
    return {"node": n.path(), "fg_wired": n.input(2) is not None, "applied": applied}


@endpoint("cop_uv_map_by_id")
def cop_uv_map_by_id(params):
    """COP filter: per-island UV map (or center/min/max/size) from an ID layer (UV Map by ID). `input`
    = an ID layer (input 0). mode (uvmap/center/min/max/size), uv_space (texture/image), auto_scale
    (none/fit), u_border/v_border (clamp/mirror/wrap), u_shift/u_cycle/v_shift/v_cycle, zero_invalid.
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "uvmapbyid", params.get("name"))
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _UVMAPBYID_MODE)
    if "uv_space" in params:
        applied["uv_space"] = _str_menu_set(n, "uvspace", str(params["uv_space"]), _UVSPACE2)
    if "auto_scale" in params:
        applied["auto_scale"] = _str_menu_set(n, "autoscale", str(params["auto_scale"]), _AUTOSCALE)
    if "u_border" in params:
        applied["u_border"] = _str_menu_set(n, "uborder", str(params["u_border"]), _UVBORDER3)
    if "v_border" in params:
        applied["v_border"] = _str_menu_set(n, "vborder", str(params["v_border"]), _UVBORDER3)
    for key, base in (("u_shift", "ushift"), ("u_cycle", "ucycle"), ("v_shift", "vshift"),
                      ("v_cycle", "vcycle")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "zero_invalid" in params:
        applied["zero_invalid"] = _try_set(n, "zeroinvalid", bool(params["zero_invalid"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_project_on_layer")
def cop_project_on_layer(params):
    """COP filter: reproject a source layer into a target layer's space (Project on Layer). `input` =
    the target (input 0), `source` -> input 1. invert, border, filter. Chains after `input`. BUILT."""
    n = child_after(params["input"], "projectonlayer", params.get("name"))  # input = target -> 0
    src = resolve_node(params["source"])
    n.setInput(1, src if src.parent().path() == n.parent().path() else bridge_into(src, n.parent(), name_hint="src"))
    applied = {}
    if "invert" in params:
        applied["invert"] = _try_set(n, "invertxform", bool(params["invert"]))
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _XFORM_BORDER)
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    return {"node": n.path(), "source_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_contact_sheet")
def cop_contact_sheet(params):
    """COP combiner: tile many input layers into a montage / contact sheet (Contact Sheet). `inputs` =
    list of node refs wired 0..n; stride (columns), vertical_stack/horizontal_stack, use_rows, scale,
    background (float4), filter. Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("contactsheet", params.get("name"))
    refs = _input_list(params.get("inputs"))
    wired = 0
    for i, r in enumerate(refs):
        src = resolve_node(r)
        n.setInput(i, src if src.parent().path() == n.parent().path() else bridge_into(src, n.parent(), name_hint="img%d" % i))
        wired += 1
    applied = {}
    if "stride" in params:
        applied["stride"] = _try_set(n, "stride", int(clamp(int(params["stride"]), 1, 100000)))
    if "vertical_stack" in params:
        applied["vertical_stack"] = _str_menu_set(n, "stackvertical", str(params["vertical_stack"]), _CONTACT_VSTACK)
    if "horizontal_stack" in params:
        applied["horizontal_stack"] = _str_menu_set(n, "stackhorizontal", str(params["horizontal_stack"]), _CONTACT_HSTACK)
    if "use_rows" in params:
        applied["use_rows"] = _try_set(n, "userows", bool(params["use_rows"]))
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", float(params["scale"]))
    if "background" in params:
        applied["background"] = _set_tuple(n, "background", params["background"])
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    return {"node": n.path(), "inputs_wired": wired, "applied": applied}


@endpoint("cop_copy_xform")
def cop_copy_xform(params):
    """COP filter: stamp N transformed copies of a shape (Copy Transform). The shape wires to input 1.
    count, xform_order, translate (float2), rotate, scale_xy (float2) + uniform scale, pivot (float2)/
    pivot_rotate, blend mode, filter, wrap, tile_size (float2), fg_color (float3). BUILT."""
    tex = resolve_node(params["input"])
    n = tex.parent().createNode("copyxform", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, tex)  # 'shape' is input index 1 on copyxform
    applied = {}
    if "count" in params:
        applied["count"] = _try_set(n, "ncy", int(clamp(int(params["count"]), 1, 100000)))
    if "xform_order" in params:
        applied["xform_order"] = _str_menu_set(n, "xOrd", str(params["xform_order"]), _XFORM_ORD)
    for key, base in (("translate", "t"), ("scale_xy", "s"), ("pivot", "p"), ("tile_size", "tilesize"),
                      ("fg_color", "fg")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    for key, base in (("rotate", "r"), ("scale", "scale"), ("pivot_rotate", "pr")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "blend" in params:
        applied["blend"] = _str_menu_set(n, "blend", str(params["blend"]), _COPYXFORM_BLEND)
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    if "wrap" in params:
        applied["wrap"] = _str_menu_set(n, "wrap", str(params["wrap"]), _SWIRL_WRAPMODE)
    return {"node": n.path(), "shape_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_lattice_deform")
def cop_lattice_deform(params):
    """COP filter: warp a layer through a 4x4 lattice grid (Lattice Deform). The source texture wires
    to input 1. mode (linear/smooth), lod_u/lod_v, cells_per_column; `points` = JSON object mapping
    "row_col" -> [x,y] to move individual lattice points (e.g. {"0_0":[0.1,0.1]}). BUILT."""
    tex = resolve_node(params["input"])
    n = tex.parent().createNode("latticedeform", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, tex)  # 'source' is input index 1 on latticedeform
    applied = {}
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _LATTICE_MODE)
    for key, base in (("lod_u", "lodu"), ("lod_v", "lodv")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "cells_per_column" in params:
        applied["cells_per_column"] = _try_set(n, "cellspercolumn", int(clamp(int(params["cells_per_column"]), 1, 64)))
    if "points" in params:
        pts = params["points"]
        if isinstance(pts, str):
            try:
                pts = json.loads(pts)
            except Exception:
                pts = {}
        if isinstance(pts, dict):
            moved = 0
            for pk, pv in pts.items():
                if _set_tuple(n, "point" + str(pk), pv):
                    moved += 1
            applied["points_moved"] = moved
    return {"node": n.path(), "src_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_surface_dither")
def cop_surface_dither(params):
    """COP filter: surface-stable halftone/dither pattern -> mask or SDF (Surface Dither). `input` = a
    UV layer (input 0). density_scale, pattern_scale, pattern_scale_xy (float2), pattern_offset
    (float2), pattern_rotate, dot_scale, output (mask/sdf), mask_iso, shape_res. Chains after `input`.
    BUILT."""
    n = child_after(params["input"], "surfacedither", params.get("name"))  # input = uv -> 0
    applied = {}
    for key, base in (("density_scale", "densityscale"), ("pattern_scale", "patternscale"),
                      ("pattern_rotate", "patternrotate"), ("dot_scale", "dotscale"),
                      ("mask_iso", "maskiso")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "pattern_scale_xy" in params:
        applied["pattern_scale_xy"] = _set_tuple(n, "patternscalexy", params["pattern_scale_xy"])
    if "pattern_offset" in params:
        applied["pattern_offset"] = _set_tuple(n, "patternoffset", params["pattern_offset"])
    if "output" in params:
        applied["output"] = _str_menu_set(n, "output", str(params["output"]), _DITHER_OUTPUT)
    if "shape_res" in params:
        applied["shape_res"] = _try_set(n, "shaperes", int(clamp(int(params["shape_res"]), 1, 100000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_sample")
def cop_sample(params):
    """COP filter: resample a texture through a UV map (Sample). `input` = the UV layer (input 0),
    `texture` -> input 2. uv_space (texture/image), filter_scale, filter. BUILT."""
    n = child_after(params["input"], "sample", params.get("name"))  # input = uv -> 0
    tex = resolve_node(params["texture"])
    n.setInput(2, tex if tex.parent().path() == n.parent().path() else bridge_into(tex, n.parent(), name_hint="tex"))
    applied = {}
    if "uv_space" in params:
        applied["uv_space"] = _str_menu_set(n, "uvspace", str(params["uv_space"]), _UVSPACE2)
    if "filter_scale" in params:
        applied["filter_scale"] = _try_set(n, "filterscale", float(params["filter_scale"]))
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    return {"node": n.path(), "tex_wired": n.input(2) is not None, "applied": applied}


@endpoint("cop_prefix_sum")
def cop_prefix_sum(params):
    """COP filter: directional running scan across the image (Prefix Sum). sweep_dir (px/mx/py/ny/xy/
    index), op (add/min/max/count), scale (none/pixel/texture/image). Chains after `input`. BUILT."""
    n = child_after(params["input"], "prefixsum", params.get("name"))
    applied = {}
    if "sweep_dir" in params:
        applied["sweep_dir"] = _str_menu_set(n, "sweepdir", str(params["sweep_dir"]), _PREFIXSUM_DIR)
    if "op" in params:
        applied["op"] = _str_menu_set(n, "op", str(params["op"]), _PREFIXSUM_OP)
    if "scale" in params:
        applied["scale"] = _str_menu_set(n, "scale", str(params["scale"]), _PREFIXSUM_SCALE)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_statistics")
def cop_statistics(params):
    """COP filter: compute per-layer statistics (min/max/avg/...) as layer attributes (Statistics),
    readable by downstream nodes. Chains after `input`. BUILT."""
    n = child_after(params["input"], "statistics", params.get("name"))
    return {"node": n.path(), "applied": {}}


@endpoint("cop_layer_properties")
def cop_layer_properties(params):
    """COP filter: set a layer's precision / border / type-info metadata (Layer Properties). precision
    (b8/b16/b32), border (constant/clamp/mirror/wrap), type_info (color/position/normal/id/mask/sdf/
    height/...) — each auto-enables its setter. Chains after `input`. BUILT."""
    n = child_after(params["input"], "layerproperties", params.get("name"))
    applied = {}
    if "precision" in params:
        _try_set(n, "setprecision", True)
        applied["precision"] = _str_menu_set(n, "precision", str(params["precision"]), _LAYERPROP_PRECISION)
    if "border" in params:
        _try_set(n, "setborder", True)
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _LAYERPROP_BORDER)
    if "type_info" in params:
        _try_set(n, "settypeinfo", True)
        applied["type_info"] = _str_menu_set(n, "typeinfo", str(params["type_info"]), _LAYERPROP_TYPEINFO)
    return {"node": n.path(), "applied": applied}


# ── COP: the layer-type casts + tiny layer-attribute utilities. Completes the
#    layer-type-cast subcategory. Some casts join a 2nd input (rgbtorgba alpha->1, uvtorgb mono->1,
#    uvtorgba ba->1). All attribute params are names/globs, NOT paths (probe-confirmed). Data-only. ──
_CAST_CONVERSION = ("cast", "safe", "bitwise")
_LAYERATTRIB_TYPE = ("string", "float", "int")


@endpoint("cop_rgb_to_rgba")
def cop_rgb_to_rgba(params):
    """COP filter: join an RGB layer with an alpha layer -> RGBA (RGB to RGBA). `input` = RGB (input 0),
    optional `alpha` -> input 1; premult (premultiply RGB by alpha). Chains after `input`. BUILT."""
    n = child_after(params["input"], "rgbtorgba", params.get("name"))
    if params.get("alpha"):
        a = resolve_node(params["alpha"])
        n.setInput(1, a if a.parent().path() == n.parent().path() else bridge_into(a, n.parent(), name_hint="alpha"))
    applied = {}
    if "premult" in params:
        applied["premult"] = _try_set(n, "premult", bool(params["premult"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_rgba_to_rgb")
def cop_rgba_to_rgb(params):
    """COP filter: drop the alpha channel -> RGB (RGBA to RGB). unpremult (unpremultiply first). Chains
    after `input`. BUILT."""
    n = child_after(params["input"], "rgbatorgb", params.get("name"))
    applied = {}
    if "unpremult" in params:
        applied["unpremult"] = _try_set(n, "unpremult", bool(params["unpremult"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_id_to_mono")
def cop_id_to_mono(params):
    """COP filter: convert an ID layer to a mono float layer (ID to Mono). conversion (cast/safe/
    bitwise). Chains after `input`. BUILT."""
    n = child_after(params["input"], "idtomono", params.get("name"))
    applied = {}
    if "conversion" in params:
        applied["conversion"] = _str_menu_set(n, "conversion", str(params["conversion"]), _CAST_CONVERSION)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_mono_to_id")
def cop_mono_to_id(params):
    """COP filter: convert a mono layer to an ID layer (Mono to ID). conversion (cast/safe/bitwise).
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "monotoid", params.get("name"))
    applied = {}
    if "conversion" in params:
        applied["conversion"] = _str_menu_set(n, "conversion", str(params["conversion"]), _CAST_CONVERSION)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_id_to_rgb")
def cop_id_to_rgb(params):
    """COP filter: assign a random colour per ID (ID to RGB). seed. Chains after `input`. BUILT."""
    n = child_after(params["input"], "idtorgb", params.get("name"))
    applied = {}
    if "seed" in params:
        applied["seed"] = _try_set(n, "seed", int(params["seed"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_rgb_to_uv")
def cop_rgb_to_uv(params):
    """COP filter: reinterpret an RGB layer as a UV (2-vector) layer (RGB to UV). Chains after `input`.
    BUILT."""
    n = child_after(params["input"], "rgbtouv", params.get("name"))
    return {"node": n.path(), "applied": {}}


@endpoint("cop_uv_to_rgb")
def cop_uv_to_rgb(params):
    """COP filter: reinterpret a UV layer as RGB (UV to RGB); optional `mono` layer -> input 1 supplies
    the blue channel. Chains after `input`. BUILT."""
    n = child_after(params["input"], "uvtorgb", params.get("name"))
    if params.get("mono"):
        m = resolve_node(params["mono"])
        n.setInput(1, m if m.parent().path() == n.parent().path() else bridge_into(m, n.parent(), name_hint="mono"))
    return {"node": n.path(), "applied": {}}


@endpoint("cop_rgba_to_uv")
def cop_rgba_to_uv(params):
    """COP filter: reinterpret an RGBA layer as a UV (2-vector) layer (RGBA to UV). Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "rgbatouv", params.get("name"))
    return {"node": n.path(), "applied": {}}


@endpoint("cop_uv_to_rgba")
def cop_uv_to_rgba(params):
    """COP filter: join two 2-vector layers into RGBA (UV to RGBA). `input` = the rg layer (input 0),
    optional `ba` layer -> input 1. Chains after `input`. BUILT."""
    n = child_after(params["input"], "uvtorgba", params.get("name"))
    if params.get("ba"):
        b = resolve_node(params["ba"])
        n.setInput(1, b if b.parent().path() == n.parent().path() else bridge_into(b, n.parent(), name_hint="ba"))
    return {"node": n.path(), "applied": {}}


@endpoint("cop_channel_split")
def cop_channel_split(params):
    """COP filter: split a multi-channel layer into single-channel outputs (Channel Split) — the
    inverse of cop_channel_join. Chains after `input`. BUILT."""
    n = child_after(params["input"], "channelsplit", params.get("name"))
    return {"node": n.path(), "applied": {}}


@endpoint("cop_layer_attrib_create")
def cop_layer_attrib_create(params):
    """COP filter: add a layer-metadata attribute (Layer Attribute Create). attr_name, attr_type
    (string/float/int), value (typed accordingly). Chains after `input`. BUILT."""
    n = child_after(params["input"], "layerattribcreate", params.get("name"))
    applied = {}
    if "attr_name" in params:
        _try_set(n, "numattrib", 1)
        applied["attr_name"] = _try_set(n, "name1", str(params["attr_name"]))
        atype = str(params.get("attr_type", "float"))
        applied["attr_type"] = _str_menu_set(n, "type1", atype, _LAYERATTRIB_TYPE)
        if "value" in params:
            v = params["value"]
            if atype == "string":
                applied["value"] = _try_set(n, "vals1", str(v))
            elif atype == "int":
                applied["value"] = _try_set(n, "vali1", int(v))
            else:
                applied["value"] = _try_set(n, "valf1", float(v))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_layer_attrib_delete")
def cop_layer_attrib_delete(params):
    """COP filter: delete layer-metadata attributes by name glob (Layer Attribute Delete). delete
    (glob to remove), keep (glob to preserve). Chains after `input`. BUILT."""
    n = child_after(params["input"], "layerattribdelete", params.get("name"))
    applied = {}
    if "delete" in params:
        applied["delete"] = _try_set(n, "delete", str(params["delete"]))
    if "keep" in params:
        applied["keep"] = _try_set(n, "keep", str(params["keep"]))
    return {"node": n.path(), "applied": applied}


# ── COP: the last 11 general-purpose COP node types. Completes the
#    clean general-purpose COP surface (only specialist clusters + gated + infra remain by design).
#    Input indices: dot/cross a0/b1, possample pos0/tex1, statisticsbyid id0/source1, autostereogram
#    source0/depth1, heatdistortbylayer source0/noise1(req). Data-only. ────────────────────────────
_MATCHUDIM_METHOD = ("eye", "data")
_AUTOSTEREO_BORDER = ("mirror", "wrap")
_LAYER_SIG = ("f1", "f2", "f3", "f4", "i")


@endpoint("cop_dot")
def cop_dot(params):
    """COP filter: per-pixel dot product of two vector layers -> mono (Dot). `input` = a (input 0),
    `b` -> input 1. Chains after `input`. BUILT."""
    n = child_after(params["input"], "dot", params.get("name"))
    b = resolve_node(params["b"])
    n.setInput(1, b if b.parent().path() == n.parent().path() else bridge_into(b, n.parent(), name_hint="b"))
    return {"node": n.path(), "b_wired": n.input(1) is not None, "applied": {}}


@endpoint("cop_cross")
def cop_cross(params):
    """COP filter: per-pixel cross product of two vec3 layers (Cross). `input` = a (input 0), `b` ->
    input 1. Chains after `input`. BUILT."""
    n = child_after(params["input"], "cross", params.get("name"))
    b = resolve_node(params["b"])
    n.setInput(1, b if b.parent().path() == n.parent().path() else bridge_into(b, n.parent(), name_hint="b"))
    return {"node": n.path(), "b_wired": n.input(1) is not None, "applied": {}}


@endpoint("cop_pos_sample")
def cop_pos_sample(params):
    """COP filter: sample a texture at coordinates read from a position layer (Position Sample).
    `input` = the position layer (input 0), `texture` -> input 1. Chains after `input`. BUILT."""
    n = child_after(params["input"], "possample", params.get("name"))  # input = pos -> 0
    t = resolve_node(params["texture"])
    n.setInput(1, t if t.parent().path() == n.parent().path() else bridge_into(t, n.parent(), name_hint="tex"))
    return {"node": n.path(), "tex_wired": n.input(1) is not None, "applied": {}}


@endpoint("cop_statistics_by_id")
def cop_statistics_by_id(params):
    """COP filter: per-ID statistics computed as layer attributes (Statistics by ID). `input` = an ID
    layer (input 0), `source` -> input 1 (the values to summarize). Chains after `input`. BUILT."""
    n = child_after(params["input"], "statisticsbyid", params.get("name"))  # input = id -> 0
    src = resolve_node(params["source"])
    n.setInput(1, src if src.parent().path() == n.parent().path() else bridge_into(src, n.parent(), name_hint="src"))
    return {"node": n.path(), "source_wired": n.input(1) is not None, "applied": {}}


@endpoint("cop_match_udim")
def cop_match_udim(params):
    """COP filter: relocate an image onto a chosen UDIM tile (Match UDIM). udim (tile number, enables
    set_udim), invert, method (eye/data). Chains after `input`. BUILT."""
    n = child_after(params["input"], "matchudim", params.get("name"))
    applied = {}
    if "udim" in params:
        _try_set(n, "setudim", True)
        applied["udim"] = _try_set(n, "udim", int(params["udim"]))
    if "invert" in params:
        applied["invert"] = _try_set(n, "invertxform", bool(params["invert"]))
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _MATCHUDIM_METHOD)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_autostereogram")
def cop_autostereogram(params):
    """COP filter: build a Magic-Eye autostereogram from a pattern + depth image (Autostereogram).
    `input` = the pattern (input 0), `depth` -> input 1. scale (float2), depth_range (float2), border
    (mirror/wrap), recenter. Chains after `input`. BUILT."""
    n = child_after(params["input"], "autostereogram", params.get("name"))  # input = source -> 0
    d = resolve_node(params["depth"])
    n.setInput(1, d if d.parent().path() == n.parent().path() else bridge_into(d, n.parent(), name_hint="depth"))
    applied = {}
    if "scale" in params:
        applied["scale"] = _set_tuple(n, "scale", params["scale"])
    if "depth_range" in params:
        applied["depth_range"] = _set_tuple(n, "depthrange", params["depth_range"])
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _AUTOSTEREO_BORDER)
    if "recenter" in params:
        applied["recenter"] = _try_set(n, "recenter", bool(params["recenter"]))
    return {"node": n.path(), "depth_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_uv_xform")
def cop_uv_xform(params):
    """COP filter: translate/rotate/scale a UV layer (UV Transform). translate (float2), rotate,
    scale_xy (float2) + uniform scale, pivot (float2), seed. Chains after `input`. BUILT."""
    n = child_after(params["input"], "uvxform", params.get("name"))
    applied = {}
    for key, base in (("translate", "t"), ("scale_xy", "s"), ("pivot", "p")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    for key, base in (("rotate", "rz"), ("scale", "scale")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "seed" in params:
        applied["seed"] = _try_set(n, "seed", int(params["seed"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_layer")
def cop_layer(params):
    """COP generator: a blank typed layer at a chosen resolution/precision (Layer). signature (f1/f2/
    f3/f4/i), value (mono init), res (float2), precision (b8/b16/b32), border (constant/clamp/mirror/
    wrap), type_info. Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("layer", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _str_menu_set(n, "signature", str(params["signature"]), _LAYER_SIG)
    if "value" in params:
        applied["value"] = _try_set(n, "f1", float(params["value"]))
    if "res" in params:
        applied["res"] = _set_tuple(n, "res", params["res"])
    if "precision" in params:
        applied["precision"] = _str_menu_set(n, "precision", str(params["precision"]), _LAYERPROP_PRECISION)
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _LAYERPROP_BORDER)
    if "type_info" in params:
        applied["type_info"] = _str_menu_set(n, "typeinfo", str(params["type_info"]), _LAYERPROP_TYPEINFO)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_heat_distort")
def cop_heat_distort(params):
    """COP filter: heat-haze distortion from internal noise (Heat Distort). global_scale, scale,
    element_size, detail_scale, roughness, cutoff, angle; distort/detail_distort/streak_blur toggles,
    mask. Chains after `input`. BUILT."""
    n = child_after(params["input"], "heatdistort", params.get("name"))
    applied = {}
    for key, base in (("global_scale", "globaldistortscale"), ("scale", "scale"),
                      ("element_size", "elementsize"), ("detail_scale", "detailscale"),
                      ("roughness", "rough"), ("cutoff", "cutoff"), ("angle", "angle")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "distort" in params:
        applied["distort"] = _try_set(n, "dodistort", bool(params["distort"]))
    if "detail_distort" in params:
        applied["detail_distort"] = _try_set(n, "dodetaildistort", bool(params["detail_distort"]))
    if "streak_blur" in params:
        applied["streak_blur"] = _try_set(n, "streakblur", bool(params["streak_blur"]))
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_heat_distort_by_layer")
def cop_heat_distort_by_layer(params):
    """COP filter: heat-haze distortion driven by a `noise` layer (Heat Distort by Layer). `input` =
    the source (input 0), `noise` -> input 1 (required). scale, angle; streak_blur/use_cfl/
    source_blur (+size)/noise_blur/chromatic_aberration toggles, mask. Chains after `input`. BUILT."""
    n = child_after(params["input"], "heatdistortbylayer", params.get("name"))  # input = source -> 0
    nz = resolve_node(params["noise"])
    n.setInput(1, nz if nz.parent().path() == n.parent().path() else bridge_into(nz, n.parent(), name_hint="noise"))
    applied = {}
    for key, base in (("scale", "scale"), ("angle", "angle")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "streak_blur" in params:
        applied["streak_blur"] = _try_set(n, "streakblur", bool(params["streak_blur"]))
    if "use_cfl" in params:
        applied["use_cfl"] = _try_set(n, "usecfl", bool(params["use_cfl"]))
    if "source_blur" in params:
        _try_set(n, "dosourceblur", True)
        applied["source_blur"] = _try_set(n, "sourceblursize", float(params["source_blur"]))
    if "noise_blur" in params:
        applied["noise_blur"] = _try_set(n, "donoiseblur", bool(params["noise_blur"]))
    if "chromatic_aberration" in params:
        applied["chromatic_aberration"] = _try_set(n, "doca", bool(params["chromatic_aberration"]))
    if "mask" in params:
        applied["mask"] = _try_set(n, "mask", clamp(float(params["mask"]), 0.0, 1.0))
    return {"node": n.path(), "noise_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_heightfield_visualize")
def cop_heightfield_visualize(params):
    """COP filter: scale/offset an incoming heightfield layer for visualization (Heightfield
    Visualize). height_scale, height_offset. Chains after `input`. BUILT."""
    n = child_after(params["input"], "heightfield_visualize", params.get("name"))
    applied = {}
    if "height_scale" in params:
        applied["height_scale"] = _try_set(n, "heightscale", float(params["height_scale"]))
    if "height_offset" in params:
        applied["height_offset"] = _try_set(n, "heightoffset", float(params["height_offset"]))
    return {"node": n.path(), "applied": applied}


# ── COP: Rasterize + geo/curve bridges. Menus live-probed on
#    H21.0.671: all are MenuParmTemplate but set-by-token works
#    and evalAsString round-trips the token → _str_menu_set. INPUT-INDEX MAP (inputLabels()): rasterizegeo/rasterizecurves geometry|curves→INPUT 1 (input 0 = optional
#    camera_ref); layerfromcurves/maskfromcurves curves→INPUT 1 (input 0 = optional size_ref);
#    rasterizesetup source→INPUT 0; layertogeo/layertopoints layer→INPUT 0. `sopimport` = the SOP→COP
#    bridge, a 0-input generator (soppath = a scene NODE PATH, not a disk file → in-session data flow,
#    SAFE like object_merge). ──
_RG_QUICKSETUP = ("menu", "alpha", "position", "normal", "uv", "deptheye")
_RG_OUTTYPE = ("float", "vector2", "vector3", "vector4", "int")
_RG_BORDER = ("auto", "constant", "clamp", "mirror", "wrap")
_RS_SPACE = ("pos", "uv")
_RS_ORIENT = ("yup", "zup")
_RS_FIT = ("none", "bbox", "refbox")
_RC_JOINTS = ("round", "sharp")
_RC_ENDPOINTS = ("flat", "round")
_RC_VSCALING = ("noscaling", "average", "maximum", "minimum")
_TREATPOLYSAS = ("straight", "subd", "interp")
_LTP_METHOD = ("all", "nonzero", "pixel", "unique", "first", "last")


@endpoint("cop_sop_import")
def cop_sop_import(params):
    """COP generator: bridge an in-scene SOP into the copnet (SOP Import). `sop` = a scene SOP node
    path (e.g. /obj/geo1/OUT) whose geometry feeds the rasterize / geo-bridge COP nodes. This is a
    node REFERENCE to in-session geometry, NOT a disk file — in-session data flow, identical in kind
    to object_merge / sop_import. Created in the shared /obj/cops copnet. BUILT."""
    src = resolve_node(params["sop"])
    n = _cop_gen("sopimport", params.get("name"))
    _try_set(n, "usesoppath", True)
    _try_set(n, "soppath", src.path())
    return {"node": n.path(), "soppath": src.path()}


@endpoint("cop_rasterize_geo")
def cop_rasterize_geo(params):
    """COP: rasterize geometry attributes into an image layer (Rasterize Geometry). `geometry` = a COP
    geometry source (e.g. a cop_sop_import) wired to INPUT 1 (input 0 = optional camera_ref). quicksetup
    one-click adds a common attribute (alpha/position/normal/uv/deptheye); or set attribute + outtype
    for a named attribute (Cd/N/uv/...). border wraps out-of-frame samples. BUILT."""
    geo = resolve_node(params["geometry"])
    n = geo.parent().createNode("rasterizegeo", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, geo)
    applied = {}
    if "quicksetup" in params:
        applied["quicksetup"] = _str_menu_set(n, "quicksetup", str(params["quicksetup"]), _RG_QUICKSETUP)
    if "attribute" in params:
        applied["attribute"] = _try_set(n, "name1", str(params["attribute"]))
    if "outtype" in params:
        applied["outtype"] = _str_menu_set(n, "outtype1", str(params["outtype"]), _RG_OUTTYPE)
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _RG_BORDER)
    if "reset_orig" in params:
        applied["reset_orig"] = _try_set(n, "resetorig", bool(params["reset_orig"]))
    return {"node": n.path(), "geo_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_rasterize_setup")
def cop_rasterize_setup(params):
    """COP: configure the rasterize camera / space that precedes Rasterize Geometry (Rasterize Setup).
    `geometry` = a COP geometry source wired to INPUT 0; feed this node's output into cop_rasterize_geo.
    space (pos/uv), orient (yup/zup), fit (none/bbox/refbox), uv_attrib; add_normal / add_depth toggles.
    BUILT."""
    geo = resolve_node(params["geometry"])
    n = geo.parent().createNode("rasterizesetup", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(0, geo)
    applied = {}
    if "space" in params:
        applied["space"] = _str_menu_set(n, "space", str(params["space"]), _RS_SPACE)
    if "orient" in params:
        applied["orient"] = _str_menu_set(n, "orient", str(params["orient"]), _RS_ORIENT)
    if "fit" in params:
        applied["fit"] = _str_menu_set(n, "fit", str(params["fit"]), _RS_FIT)
    if "uv_attrib" in params:
        applied["uv_attrib"] = _try_set(n, "uvattrib", str(params["uv_attrib"]))
    if "add_normal" in params:
        applied["add_normal"] = _try_set(n, "addnormal", bool(params["add_normal"]))
    if "add_depth" in params:
        applied["add_depth"] = _try_set(n, "adddepth", bool(params["add_depth"]))
    return {"node": n.path(), "geo_wired": n.input(0) is not None, "applied": applied}


@endpoint("cop_rasterize_curves")
def cop_rasterize_curves(params):
    """COP: rasterize curve geometry as strokes into a layer (Rasterize Curves). `curves` = a COP curve
    source wired to INPUT 1 (input 0 = optional camera_ref). quicksetup adds a common attribute; width
    (+ units image/pixels), joints (round/sharp), endpoints (flat/round), vscaling, treat_polys_as;
    attribute + outtype for a named attribute. BUILT."""
    cur = resolve_node(params["curves"])
    n = cur.parent().createNode("rasterizecurves", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, cur)
    applied = {}
    if "quicksetup" in params:
        applied["quicksetup"] = _str_menu_set(n, "quicksetup", str(params["quicksetup"]), _RG_QUICKSETUP)
    if "units" in params:
        applied["units"] = _str_menu_set(n, "units", str(params["units"]), _UNITS)
    if "width" in params:
        applied["width"] = _try_set(n, "width", float(params["width"]))
    if "joints" in params:
        applied["joints"] = _str_menu_set(n, "joints", str(params["joints"]), _RC_JOINTS)
    if "endpoints" in params:
        applied["endpoints"] = _str_menu_set(n, "endpoints", str(params["endpoints"]), _RC_ENDPOINTS)
    if "vscaling" in params:
        applied["vscaling"] = _str_menu_set(n, "vscaling", str(params["vscaling"]), _RC_VSCALING)
    if "treat_polys_as" in params:
        applied["treat_polys_as"] = _str_menu_set(n, "treatpolysas", str(params["treat_polys_as"]), _TREATPOLYSAS)
    if "attribute" in params:
        applied["attribute"] = _try_set(n, "name1", str(params["attribute"]))
    if "outtype" in params:
        applied["outtype"] = _str_menu_set(n, "outtype1", str(params["outtype"]), _RG_OUTTYPE)
    return {"node": n.path(), "curves_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_layer_to_geo")
def cop_layer_to_geo(params):
    """COP: convert a COP layer back into SOP geometry (Layer to Geometry) — a volume/VDB primitive.
    Chains after `input` (the layer, INPUT 0). signature sets the accepted layer type
    (mono/vec2/vec3/vec4); optional yields empty geo if the input is unwired. BUILT."""
    n = child_after(params["input"], "layertogeo", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "optional" in params:
        applied["optional"] = _try_set(n, "optional", bool(params["optional"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_layer_to_points")
def cop_layer_to_points(params):
    """COP: emit SOP points from a COP layer (Layer to Points). Chains after `input` (the layer, INPUT
    0). method (all/nonzero/pixel/unique/first/last) selects which pixels emit points; layer_attrib /
    index_attrib name the output point attributes; set_pos writes P from pixel position. BUILT."""
    n = child_after(params["input"], "layertopoints", params.get("name"))
    applied = {}
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _LTP_METHOD)
    if "layer_attrib" in params:
        applied["layer_attrib"] = _try_set(n, "layerattrib", str(params["layer_attrib"]))
    if "index_attrib" in params:
        applied["index_attrib"] = _try_set(n, "indexattrib", str(params["index_attrib"]))
    if "set_pos" in params:
        applied["set_pos"] = _try_set(n, "setpos", bool(params["set_pos"]))
    if "ignore_minus_one" in params:
        applied["ignore_minus_one"] = _try_set(n, "ignoreminusone", bool(params["ignore_minus_one"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_layer_from_curves")
def cop_layer_from_curves(params):
    """COP: colored/profiled strokes from curve geometry into a layer (Layer from Curves). `curves` = a
    COP curve source wired to INPUT 1 (input 0 = optional size_ref). width, joints (round/sharp),
    endpoints (flat/round), treat_polys_as, twist_rate, max_seg_len. BUILT."""
    cur = resolve_node(params["curves"])
    n = cur.parent().createNode("layerfromcurves", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, cur)
    applied = {}
    if "width" in params:
        applied["width"] = _try_set(n, "width", float(params["width"]))
    if "joints" in params:
        applied["joints"] = _str_menu_set(n, "joints", str(params["joints"]), _RC_JOINTS)
    if "endpoints" in params:
        applied["endpoints"] = _str_menu_set(n, "endpoints", str(params["endpoints"]), _RC_ENDPOINTS)
    if "treat_polys_as" in params:
        applied["treat_polys_as"] = _str_menu_set(n, "treatpolysas", str(params["treat_polys_as"]), _TREATPOLYSAS)
    if "twist_rate" in params:
        applied["twist_rate"] = _try_set(n, "twistrate", float(params["twist_rate"]))
    if "max_seg_len" in params:
        applied["max_seg_len"] = _try_set(n, "maxseglen", float(params["max_seg_len"]))
    return {"node": n.path(), "curves_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_mask_from_curves")
def cop_mask_from_curves(params):
    """COP: mask or SDF from curve geometry (Mask from Curves). `curves` = a COP curve source wired to
    INPUT 1 (input 0 = optional size_ref). output (mask/sdf), blur_size (+ blur_units image/pixels),
    treat_polys_as, quality; do_blur toggles the blur. BUILT."""
    cur = resolve_node(params["curves"])
    n = cur.parent().createNode("maskfromcurves", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, cur)
    applied = {}
    if "output" in params:
        applied["output"] = _str_menu_set(n, "output", str(params["output"]), _DITHER_OUTPUT)
    if "blur_units" in params:
        applied["blur_units"] = _str_menu_set(n, "blurunits", str(params["blur_units"]), _UNITS)
    if "blur_size" in params:
        applied["blur_size"] = _try_set(n, "blursize", float(params["blur_size"]))
    if "treat_polys_as" in params:
        applied["treat_polys_as"] = _str_menu_set(n, "treatpolysas", str(params["treat_polys_as"]), _TREATPOLYSAS)
    if "quality" in params:
        applied["quality"] = _try_set(n, "quality", float(params["quality"]))
    if "do_blur" in params:
        applied["do_blur"] = _try_set(n, "doblur", bool(params["do_blur"]))
    return {"node": n.path(), "curves_wired": n.input(1) is not None, "applied": applied}


# ── COP: VDB / volume bridges. Live-probed on H21.0.671.
#    THE MECHANISM: `geotolayer::2.0`
#    (geometry→INPUT 0) reads a NAMED VDB/primitive out of geometry into a TYPED layer (outtype1 incl.
#    floatvdb/intvdb/vectorvdb); the whole VDB family then consumes that FloatVDB *layer*, NOT raw
#    geometry. INPUT-INDEX MAP: vdbposmap size_ref→in0; rasterizevolume density→INPUT 1 (in0=camera_ref
#    + 7 more optional layers); integratevolume density→INPUT 1; layerfromvdb vdb→INPUT 1 (in0=size_ref);
#    vdbfromlayer vdb_ref(FloatVDB layer)→in0 + layer(MONO)→in1 (BOTH required); raytrace geometry→in0 +
#    origins→in1 + directions→in2 (all required). All menus TOKEN round-trip → _str_menu_set; signature
#    is a plain string token. ──
_GTL_OUTTYPE = ("int", "float", "vector2", "vector3", "vector4", "intvdb", "floatvdb", "vectorvdb")
_VDB_SPACE = ("world", "image", "texture", "pixel")
_CONVERTDEPTH = ("dist", "depth", "height")
_INTEGRATE_OP = ("integral", "transmittance", "min", "max")


@endpoint("cop_geo_to_layer")
def cop_geo_to_layer(params):
    """COP: read a named primitive / VDB from geometry into a typed layer (Geometry to Layer). `geometry`
    = a COP geometry source (e.g. a cop_sop_import) wired to input 0. outtype selects the layer type
    (float/vector*/intvdb/floatvdb/vectorvdb); primitive = the primitive/VDB name to read (e.g. 'surface',
    'density'). This is the VDB->layer ENTRY that feeds cop_rasterize_volume / cop_vdb_posmap /
    cop_layer_from_vdb / cop_integrate_volume. BUILT."""
    geo = resolve_node(params["geometry"])
    n = geo.parent().createNode("geotolayer::2.0", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(0, geo)
    applied = {}
    if "outtype" in params:
        applied["outtype"] = _str_menu_set(n, "outtype1", str(params["outtype"]), _GTL_OUTTYPE)
    if "primitive" in params:
        applied["primitive"] = _try_set(n, "primitive1", str(params["primitive"]))
    return {"node": n.path(), "geo_wired": n.input(0) is not None, "applied": applied}


@endpoint("cop_vdb_posmap")
def cop_vdb_posmap(params):
    """COP: VDB voxel position map (VDB Pos Map). Chains after `input` -- a FloatVDB layer (e.g. from
    cop_geo_to_layer outtype=floatvdb) on input 0. space (world/image/texture/pixel) selects the
    coordinate frame; signature sets the output layer type. BUILT."""
    n = child_after(params["input"], "vdbposmap", params.get("name"))
    applied = {}
    if "space" in params:
        applied["space"] = _str_menu_set(n, "space", str(params["space"]), _VDB_SPACE)
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_layer_from_vdb")
def cop_layer_from_vdb(params):
    """COP: convert a FloatVDB layer into a sampled COP layer (Layer from VDB). `input` = a FloatVDB
    layer (e.g. from cop_geo_to_layer outtype=floatvdb) wired to input 1 (input 0 = optional size_ref).
    signature sets the output layer type. BUILT."""
    vdb = resolve_node(params["input"])
    n = vdb.parent().createNode("layerfromvdb", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, vdb)
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    return {"node": n.path(), "vdb_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_vdb_from_layer")
def cop_vdb_from_layer(params):
    """COP: convert a COP layer into a VDB, sized to a reference VDB (VDB from Layer). `input` = the
    (mono) layer to convert -> input 1; `reference_vdb` = a FloatVDB layer (e.g. from cop_geo_to_layer
    outtype=floatvdb) providing voxel sizing -> input 0. Both required. signature sets the layer type.
    BUILT."""
    ref = resolve_node(params["reference_vdb"])
    mono = resolve_node(params["input"])
    n = ref.parent().createNode("vdbfromlayer", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(0, ref)
    monoref = mono if mono.parent().path() == n.parent().path() else bridge_into(mono, n.parent(), name_hint="layer")
    n.setInput(1, monoref)
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    return {"node": n.path(), "ref_wired": n.input(0) is not None, "layer_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_rasterize_volume")
def cop_rasterize_volume(params):
    """COP: raymarch a density VDB layer into an image (Rasterize Volume). `input` = a density FloatVDB
    layer (e.g. from cop_geo_to_layer outtype=floatvdb) wired to input 1 (input 0 = optional camera_ref).
    Built-in raymarch solver (a node param, NOT user code -> SAFE). density_scale, step_size, range_min,
    range_max, max_step_count; convert_depth (dist/depth/height); signature. BUILT."""
    dens = resolve_node(params["input"])
    n = dens.parent().createNode("rasterizevolume", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, dens)
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "convert_depth" in params:
        applied["convert_depth"] = _str_menu_set(n, "convertdepth", str(params["convert_depth"]), _CONVERTDEPTH)
    for key, base in (("density_scale", "densityscale"), ("step_size", "stepsize"),
                      ("range_min", "rangemin"), ("range_max", "rangemax")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "max_step_count" in params:
        applied["max_step_count"] = _try_set(n, "maxstepcount", int(clamp(int(params["max_step_count"]), 1, 100000)))
    return {"node": n.path(), "density_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_integrate_volume")
def cop_integrate_volume(params):
    """COP: ray-integrate a volume layer to mono (Integrate Volume) -- depth / thickness. `input` = a
    density FloatVDB layer wired to input 1 (input 0 = optional camera_ref). operation (integral/
    transmittance/min/max); convert_depth (dist/depth/height); density_scale, step_size; signature.
    BUILT."""
    dens = resolve_node(params["input"])
    n = dens.parent().createNode("integratevolume", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, dens)
    applied = {}
    if "operation" in params:
        applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _INTEGRATE_OP)
    if "convert_depth" in params:
        applied["convert_depth"] = _str_menu_set(n, "convertdepth", str(params["convert_depth"]), _CONVERTDEPTH)
    for key, base in (("density_scale", "densityscale"), ("step_size", "stepsize")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    return {"node": n.path(), "density_wired": n.input(1) is not None, "applied": applied}


# ── COP: secondary VDB ops (VDB leaf/activate, stamp/scatter, layer reproject,
#    VDB visualize, raytrace, bake). Live-probed on H21.0.671.
#    INPUT-INDEX MAP (inputLabels()): vdbleafpoints/vdbvisualize/vdbvisualizeslice/vdbvisualizetree/
#    vdbvisualizevelocity take the VDB layer on INPUT 0 (chain via child_after); layertovdbleafpoints
#    refvdb→0 + thickness(MONO)→1; vdbactivatefrompoints refvdb→0 + activate_pts→1; vdbreshape
#    source→0 + ref→1; rasterizelayer camera_ref=0(optional) + source→1; stamppoint size_ref=0 +
#    points→1 + stamp0→4; curvescatter size_ref=0 + curve→1 + stamps→11; shapescatter size_ref=0 +
#    stamps→11; bakegeometrytextures size_ref=0 + low→1 + high→2 + cage→3; raytrace geometry→0 +
#    origins→1 + directions→2. All menus TOKEN round-trip → _str_menu_set; signature = plain string
#    token. raytrace REQUIRES real polygon geometry (VDB geo -> 'triangle mesh creation failed') and
#    all three inputs; origins = a position-rasterized layer, directions = a normal-rasterized layer. ──
_STAMP_BLEND = ("sorted", "unsorted", "add", "subtract", "multiply", "max", "min")
_SCATTER_VAR = ("uniform", "variance", "minmax")
_STAMP_SHAPE = ("square", "circle")
_STAMP_ATTRIBMODE = ("auto", "instance", "sprite")
_AXIS_XYZ = ("x", "y", "z")
_ROTMETHOD = ("x", "y", "both")
_STAMP_WRAP = ("auto", "off", "on")
_CURVE_DIST = ("distance", "scatter", "count")
_SELECT_MODE = ("cycle", "random", "layer")
_SHAPE_SCALING = ("image", "tile")
_RL_BORDER = ("auto", "constant", "clamp", "mirror", "wrap", "clip")
_RAMPMODE = ("none", "clamp", "periodic")
_SLICE_PLANE = ("xy", "yz", "zx")
_SLICE_VISMODE = ("none", "false", "pink", "mono", "blackbody", "bipartite")
_TREE_NODEMODE = ("wirebox", "box")
_TREE_TILEMODE = ("points", "wirebox", "box")
_RT_CULLING = ("noculling", "backface", "frontface")
_RT_DIRECTION = ("bidirectional", "forward", "backward")
_RT_EDGEMODE = ("both", "concave", "convex")
_BAKE_TRACING = ("surfacenormal", "cagemesh", "singlemesh")
_BAKE_TANGENTS = ("mikkt", "tex", "none")
_BAKE_NORMALS = ("error", "warning", "create")
_BAKE_QUICKSETUP = ("menu", "cd", "pieceid", "name")


def _wire_ref(n, idx, src_node):
    """setInput(idx, src) with a copnet-parent bridge guard (mirrors cop_project_on_layer)."""
    n.setInput(idx, src_node if src_node.parent().path() == n.parent().path()
               else bridge_into(src_node, n.parent(), name_hint="in%d" % idx))


@endpoint("cop_vdb_leafpoints")
def cop_vdb_leafpoints(params):
    """COP: emit points at VDB leaf/voxel centers (VDB Leaf Points). Chains after `input` -- a FloatVDB
    layer (e.g. from cop_geo_to_layer outtype=floatvdb) on input 0. set_pos writes P from the voxel
    position. BUILT."""
    n = child_after(params["input"], "vdbleafpoints", params.get("name"))
    applied = {}
    if "set_pos" in params:
        applied["set_pos"] = _try_set(n, "setpos", bool(params["set_pos"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_layer_to_vdb_leafpoints")
def cop_layer_to_vdb_leafpoints(params):
    """COP: VDB-leaf sample points from a layer (Layer to VDB Leaf Points). `input` = a FloatVDB layer
    (refvdb, input 0); `thickness_layer` = a MONO layer wired to input 1 (thickness field). thickness =
    global thickness scale; signature sets the accepted layer type. BUILT."""
    n = child_after(params["input"], "layertovdbleafpoints", params.get("name"))  # refvdb -> 0
    th = resolve_node(params["thickness_layer"])
    _wire_ref(n, 1, th)
    applied = {"thickness_wired": n.input(1) is not None}
    if "thickness" in params:
        applied["thickness"] = _try_set(n, "thickness", float(params["thickness"]))
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_vdb_activate_from_points")
def cop_vdb_activate_from_points(params):
    """COP: activate VDB voxel regions from point positions (VDB Activate from Points). `input` = the
    reference FloatVDB layer (refvdb, input 0); `points` = a COP points source (e.g. a cop_sop_import of
    scattered points) wired to input 1. leaf_dilation (int), leaf_dilation_dist, voxel_scale (floats),
    sort_leaves toggle. BUILT."""
    n = child_after(params["input"], "vdbactivatefrompoints", params.get("name"))  # refvdb -> 0
    pts = resolve_node(params["points"])
    _wire_ref(n, 1, pts)
    applied = {"points_wired": n.input(1) is not None}
    if "leaf_dilation" in params:
        applied["leaf_dilation"] = _try_set(n, "leafdilation", int(clamp(int(params["leaf_dilation"]), 0, 100000)))
    if "leaf_dilation_dist" in params:
        applied["leaf_dilation_dist"] = _try_set(n, "leafdilationdist", clamp(float(params["leaf_dilation_dist"]), 0.0, 1e6))
    if "voxel_scale" in params:
        applied["voxel_scale"] = _try_set(n, "voxelscale", clamp(float(params["voxel_scale"]), 0.0, 1e6))
    if "sort_leaves" in params:
        applied["sort_leaves"] = _try_set(n, "sortleaves", bool(params["sort_leaves"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_vdb_reshape")
def cop_vdb_reshape(params):
    """COP: conform a VDB to a reference VDB's transform/topology frame (VDB Reshape). `input` = the
    source VDB layer (input 0); `reference` = the reference VDB layer wired to input 1. No parameters --
    a pure two-VDB reshape. BUILT."""
    n = child_after(params["input"], "vdbreshape", params.get("name"))  # source -> 0
    ref = resolve_node(params["reference"])
    _wire_ref(n, 1, ref)
    return {"node": n.path(), "ref_wired": n.input(1) is not None}


@endpoint("cop_stamp_point")
def cop_stamp_point(params):
    """COP: stamp a layer at point positions (Stamp Point). `points` = a COP points source wired to
    input 1; `stamps` = the stamp layer (sprite/atlas) wired to input 4. attrib_mode (auto/instance/
    sprite), cutout_shape, up_axis, rotation_method, filter, blend, wrap; scale/angle/tile_size,
    bg/fg (+ alpha), num_stamps; signature. BUILT."""
    pts = resolve_node(params["points"])
    n = pts.parent().createNode("stamppoint", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, pts)
    _wire_ref(n, 4, resolve_node(params["stamps"]))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "cutout_shape" in params:
        applied["cutout_shape"] = _str_menu_set(n, "cutout_shape", str(params["cutout_shape"]), _STAMP_SHAPE)
    if "attrib_mode" in params:
        applied["attrib_mode"] = _str_menu_set(n, "attribmode", str(params["attrib_mode"]), _STAMP_ATTRIBMODE)
    if "up_axis" in params:
        applied["up_axis"] = _str_menu_set(n, "upaxis", str(params["up_axis"]), _AXIS_XYZ)
    if "rotation_method" in params:
        applied["rotation_method"] = _str_menu_set(n, "rotationmethod", str(params["rotation_method"]), _ROTMETHOD)
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    if "blend" in params:
        applied["blend"] = _str_menu_set(n, "blend", str(params["blend"]), _STAMP_BLEND)
    if "wrap" in params:
        applied["wrap"] = _str_menu_set(n, "wrap", str(params["wrap"]), _STAMP_WRAP)
    for key, base in (("bg", "bg"), ("bg_alpha", "bgalpha"), ("fg", "fg"), ("fg_alpha", "fgalpha"),
                      ("scale", "scale"), ("angle", "angle"), ("tile_size", "tilesize")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "num_stamps" in params:
        applied["num_stamps"] = _try_set(n, "numstamps", int(clamp(int(params["num_stamps"]), 1, 100000)))
    return {"node": n.path(), "points_wired": n.input(1) is not None, "stamps_wired": n.input(4) is not None, "applied": applied}


@endpoint("cop_curve_scatter")
def cop_curve_scatter(params):
    """COP: scatter stamps along curves (Curve Scatter). `curves` = a COP curve source wired to input 1;
    `stamps` = the stamp layer wired to input 11. distribution_mode (distance/scatter/count), scale_mode/
    angle_mode/stretch_mode (uniform/variance/minmax), blend, filter, select_mode; scale/angle/offset/
    jitter/curve_offset/length, seed/max_count/stamp_count (ints); signature. BUILT."""
    cur = resolve_node(params["curves"])
    n = cur.parent().createNode("curvescatter", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, cur)
    _wire_ref(n, 11, resolve_node(params["stamps"]))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "distribution_mode" in params:
        applied["distribution_mode"] = _str_menu_set(n, "distributionmode", str(params["distribution_mode"]), _CURVE_DIST)
    if "scale_mode" in params:
        applied["scale_mode"] = _str_menu_set(n, "scalemode", str(params["scale_mode"]), _SCATTER_VAR)
    if "angle_mode" in params:
        applied["angle_mode"] = _str_menu_set(n, "anglemode", str(params["angle_mode"]), _SCATTER_VAR)
    if "stretch_mode" in params:
        applied["stretch_mode"] = _str_menu_set(n, "stretchmode", str(params["stretch_mode"]), _SCATTER_VAR)
    if "blend" in params:
        applied["blend"] = _str_menu_set(n, "blend", str(params["blend"]), _STAMP_BLEND)
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    if "select_mode" in params:
        applied["select_mode"] = _str_menu_set(n, "selectmode", str(params["select_mode"]), _SELECT_MODE)
    for key, base in (("scale", "scale"), ("angle", "angle"), ("offset", "offset"), ("jitter", "jitter"),
                      ("curve_offset", "curveoffset"), ("length", "length")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("seed", "seed"), ("max_count", "maxcount"), ("stamp_count", "stampcount")):
        if key in params:
            applied[key] = _try_set(n, base, int(clamp(int(params[key]), 0, 10_000_000)))
    return {"node": n.path(), "curves_wired": n.input(1) is not None, "stamps_wired": n.input(11) is not None, "applied": applied}


@endpoint("cop_shape_scatter")
def cop_shape_scatter(params):
    """COP: scatter stamps across an image grid (Shape Scatter) -- no geometry needed. `stamps` = the
    stamp layer wired to input 11. stamp_scaling (image/tile), scale_mode/angle_mode/stretch_mode
    (uniform/variance/minmax), blend, select_mode; stamps_x/stamps_y/seed (ints), scale/angle/jitter/
    density/stretch_x/stretch_y, link_stamps; signature. BUILT."""
    st = resolve_node(params["stamps"])
    n = st.parent().createNode("shapescatter", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(11, st)
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "stamp_scaling" in params:
        applied["stamp_scaling"] = _str_menu_set(n, "stampscaling", str(params["stamp_scaling"]), _SHAPE_SCALING)
    if "scale_mode" in params:
        applied["scale_mode"] = _str_menu_set(n, "scalemode", str(params["scale_mode"]), _SCATTER_VAR)
    if "angle_mode" in params:
        applied["angle_mode"] = _str_menu_set(n, "anglemode", str(params["angle_mode"]), _SCATTER_VAR)
    if "stretch_mode" in params:
        applied["stretch_mode"] = _str_menu_set(n, "stretchmode", str(params["stretch_mode"]), _SCATTER_VAR)
    if "blend" in params:
        applied["blend"] = _str_menu_set(n, "blend", str(params["blend"]), _STAMP_BLEND)
    if "select_mode" in params:
        applied["select_mode"] = _str_menu_set(n, "selectmode", str(params["select_mode"]), _SELECT_MODE)
    for key, base in (("stamps_x", "stampsx"), ("stamps_y", "stampsy"), ("seed", "seed")):
        if key in params:
            applied[key] = _try_set(n, base, int(clamp(int(params[key]), 0, 10_000_000)))
    for key, base in (("scale", "scale"), ("angle", "angle"), ("jitter", "jitter"), ("density", "density"),
                      ("stretch_x", "stretchx"), ("stretch_y", "stretchy")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "link_stamps" in params:
        applied["link_stamps"] = _try_set(n, "linkstamps", bool(params["link_stamps"]))
    return {"node": n.path(), "stamps_wired": n.input(11) is not None, "applied": applied}


@endpoint("cop_rasterize_layer")
def cop_rasterize_layer(params):
    """COP: re-rasterize / reproject an existing layer (Rasterize Layer). `input` = the source layer
    wired to input 1 (input 0 = optional camera_ref). signature sets the layer type; border wraps
    out-of-frame samples; filter is the resample kernel; invert_xform flips the transform. BUILT."""
    src = resolve_node(params["input"])
    n = src.parent().createNode("rasterizelayer", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, src)
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _RL_BORDER)
    if "filter" in params:
        applied["filter"] = _str_menu_set(n, "filter", str(params["filter"]), _FILTER7)
    if "invert_xform" in params:
        applied["invert_xform"] = _try_set(n, "invertxform", bool(params["invert_xform"]))
    return {"node": n.path(), "source_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_vdb_visualize")
def cop_vdb_visualize(params):
    """COP: shade a density VDB into an image (VDB Visualize). Chains after `input` -- a density FloatVDB
    layer on input 0. density_ramp_mode / cd_ramp_mode / emit_ramp_mode / emit_cd_ramp_mode (none/clamp/
    periodic); density_scale, shadow_scale, ambient_exposed, ambient_occluded; signature. BUILT."""
    n = child_after(params["input"], "vdbvisualize", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    for key, base in (("density_ramp_mode", "densityrampmode"), ("cd_ramp_mode", "cdrampmode"),
                      ("emit_ramp_mode", "emitrampmode"), ("emit_cd_ramp_mode", "emitcdrampmode")):
        if key in params:
            applied[key] = _str_menu_set(n, base, str(params[key]), _RAMPMODE)
    for key, base in (("density_scale", "densityscale"), ("shadow_scale", "shadowscale"),
                      ("ambient_exposed", "ambientexposed"), ("ambient_occluded", "ambientoccluded")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_vdb_visualize_slice")
def cop_vdb_visualize_slice(params):
    """COP: slice-plane VDB visualization (VDB Visualize Slice). Chains after `input` -- a VDB layer on
    input 0. plane (xy/yz/zx), vis_mode (none/false/pink/mono/blackbody/bipartite), relative, plane_pos,
    plane_offset, vis_range_min/max; signature. BUILT."""
    n = child_after(params["input"], "vdbvisualizeslice", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "plane" in params:
        applied["plane"] = _str_menu_set(n, "plane", str(params["plane"]), _SLICE_PLANE)
    if "vis_mode" in params:
        applied["vis_mode"] = _str_menu_set(n, "vismode", str(params["vis_mode"]), _SLICE_VISMODE)
    if "relative" in params:
        applied["relative"] = _try_set(n, "relative", bool(params["relative"]))
    for key, base in (("plane_pos", "planepos"), ("plane_offset", "planeoffset"),
                      ("vis_range_min", "visrangemin"), ("vis_range_max", "visrangemax")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_vdb_visualize_tree")
def cop_vdb_visualize_tree(params):
    """COP: VDB tree/topology visualization (VDB Visualize Tree). Chains after `input` -- a VDB layer on
    input 0. draw_leaf_nodes + leaf_mode (wirebox/box), draw_internal_nodes + internal_mode, draw_tiles +
    tile_mode (points/wirebox/box); signature. BUILT."""
    n = child_after(params["input"], "vdbvisualizetree", params.get("name"))
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "draw_leaf_nodes" in params:
        applied["draw_leaf_nodes"] = _try_set(n, "drawleafnodes", bool(params["draw_leaf_nodes"]))
    if "leaf_mode" in params:
        applied["leaf_mode"] = _str_menu_set(n, "leafmode", str(params["leaf_mode"]), _TREE_NODEMODE)
    if "draw_internal_nodes" in params:
        applied["draw_internal_nodes"] = _try_set(n, "drawinternalnodes", bool(params["draw_internal_nodes"]))
    if "internal_mode" in params:
        applied["internal_mode"] = _str_menu_set(n, "internalmode", str(params["internal_mode"]), _TREE_NODEMODE)
    if "draw_tiles" in params:
        applied["draw_tiles"] = _try_set(n, "drawtiles", bool(params["draw_tiles"]))
    if "tile_mode" in params:
        applied["tile_mode"] = _str_menu_set(n, "tilemode", str(params["tile_mode"]), _TREE_TILEMODE)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_vdb_visualize_velocity")
def cop_vdb_visualize_velocity(params):
    """COP: VDB velocity-field visualization (VDB Visualize Velocity). Chains after `input` -- a
    VectorVDB (velocity) layer on input 0 (e.g. from cop_geo_to_layer outtype=vectorvdb). trail_per_voxel,
    num_points, plane (xy/yz/zx), relative, plane_pos, plane_offset, trail_length, vis_max. BUILT."""
    n = child_after(params["input"], "vdbvisualizevelocity", params.get("name"))
    applied = {}
    if "trail_per_voxel" in params:
        applied["trail_per_voxel"] = _try_set(n, "trailpervoxel", bool(params["trail_per_voxel"]))
    if "num_points" in params:
        applied["num_points"] = _try_set(n, "npts", int(clamp(int(params["num_points"]), 1, 10_000_000)))
    if "plane" in params:
        applied["plane"] = _str_menu_set(n, "plane", str(params["plane"]), _SLICE_PLANE)
    if "relative" in params:
        applied["relative"] = _try_set(n, "relative", bool(params["relative"]))
    for key, base in (("plane_pos", "planepos"), ("plane_offset", "planeoffset"),
                      ("trail_length", "traillen"), ("vis_max", "vismax")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_raytrace")
def cop_raytrace(params):
    """COP: raytrace geometry to AO / curvature / thickness / cavity / edge maps (Raytrace). `geometry` =
    a COP polygon-geometry source (a cop_sop_import of REAL polygon geo -- VDB geo fails) wired to input
    0; `origins` = a position-rasterized layer (input 1); `directions` = a normal-rasterized layer
    (input 2). All three required. Per-map do<x> toggles + <x>_samples ints: occlusion, cavity,
    curvature, thickness, edge. visibility_culling, trace_direction, ray_bias, curvature_scale,
    edge_mode. BUILT."""
    geo = resolve_node(params["geometry"])
    n = geo.parent().createNode("raytrace", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(0, geo)
    _wire_ref(n, 1, resolve_node(params["origins"]))
    _wire_ref(n, 2, resolve_node(params["directions"]))
    applied = {}
    if "visibility_culling" in params:
        applied["visibility_culling"] = _str_menu_set(n, "visibilityculling", str(params["visibility_culling"]), _RT_CULLING)
    if "trace_direction" in params:
        applied["trace_direction"] = _str_menu_set(n, "tracedirection", str(params["trace_direction"]), _RT_DIRECTION)
    if "ray_bias" in params:
        applied["ray_bias"] = _try_set(n, "raybias", float(params["ray_bias"]))
    for flag, tog, samp in (("occlusion", "doocclusion", "occlusionsamples"),
                            ("cavity", "docavity", "cavitysamples"),
                            ("curvature", "docurvature", "curvaturesamples"),
                            ("thickness", "dothickness", "thicknesssamples"),
                            ("edge", "doedge", "edgesamples")):
        if flag in params:
            applied[flag] = _try_set(n, tog, bool(params[flag]))
        sk = flag + "_samples"
        if sk in params:
            applied[sk] = _try_set(n, samp, int(clamp(int(params[sk]), 1, 100000)))
    if "curvature_scale" in params:
        applied["curvature_scale"] = _try_set(n, "curvaturescale", float(params["curvature_scale"]))
    if "edge_mode" in params:
        applied["edge_mode"] = _str_menu_set(n, "edgemode", str(params["edge_mode"]), _RT_EDGEMODE)
    return {"node": n.path(), "origins_wired": n.input(1) is not None, "directions_wired": n.input(2) is not None, "applied": applied}


@endpoint("cop_bake_geometry_textures")
def cop_bake_geometry_textures(params):
    """COP: bake normal/AO/curvature/position/thickness/height maps from geometry (Bake Geometry
    Textures). `low` = a COP low-res mesh source (must have UVs) wired to input 1; `high` = an optional
    high-res mesh wired to input 2 (required for tracing_mode=cagemesh). tracing_mode (surfacenormal/
    cagemesh/singlemesh -- surfacenormal uses a GPU tracer), tangents, normals (error/warning/create),
    uv_attribute, quicksetup; bake_<x> toggles (normal/world_normal/position/occlusion/curvature/edge/
    cavity/thickness/height/alpha). BUILT."""
    low = resolve_node(params["low"])
    n = low.parent().createNode("bakegeometrytextures", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(1, low)
    if params.get("high"):
        _wire_ref(n, 2, resolve_node(params["high"]))
    applied = {"low_wired": n.input(1) is not None, "high_wired": n.input(2) is not None}
    if "tracing_mode" in params:
        applied["tracing_mode"] = _str_menu_set(n, "tracingmode", str(params["tracing_mode"]), _BAKE_TRACING)
    if "tangents" in params:
        applied["tangents"] = _str_menu_set(n, "tangents", str(params["tangents"]), _BAKE_TANGENTS)
    if "normals" in params:
        applied["normals"] = _str_menu_set(n, "normals", str(params["normals"]), _BAKE_NORMALS)
    if "uv_attribute" in params:
        applied["uv_attribute"] = _try_set(n, "uvattribute", str(params["uv_attribute"]))
    if "quicksetup" in params:
        applied["quicksetup"] = _str_menu_set(n, "quicksetup", str(params["quicksetup"]), _BAKE_QUICKSETUP)
    for key, base in (("bake_normal", "bakenormal"), ("bake_world_normal", "bakeworldnormal"),
                      ("bake_position", "bakeposition"), ("bake_occlusion", "bakeocclusion"),
                      ("bake_curvature", "bakecurvature"), ("bake_edge", "bakeedge"),
                      ("bake_cavity", "bakecavity"), ("bake_thickness", "bakethickness"),
                      ("bake_height", "bakeheight"), ("bake_alpha", "bakealpha")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}
# NOTE: `projectonlayer` was NOT added here -- it already ships as `cop_project_on_layer`.
# vdbreshape ships with 0 node params (a two-VDB conform). bakegeometrytextures surfacenormal
# mode needs a GPU tracer (headless hython -> 'Cannot initialize tracer'); cagemesh mode (low+high)
# cooks headless and is the verified path.


# ── COP: Pyro microsolvers (10). The Copernicus 2D-image-lane
#    pyro/smoke/fire solve primitives. Data-only: NO disk-file / opencl / wrangle param anywhere in the
#    family (spec SECURITY BOTTOM LINE). Live-probed on H21.0.671.
#    THE MECHANISM: each microsolver consumes TYPED VDB *layers* from
#    cop_geo_to_layer (floatvdb -> FloatVDB for density/temperature; vectorvdb -> VectorVDB for velocity
#    `v`), the primary layer on input 0 via child_after; secondary typed layers wired per the probed
#    input-index map via _wire_ref. INPUT-INDEX MAP (the recurring trap -- primary is NOT always in0):
#      source_from_layer  source(FloatVDB)@0 + density(*MONO layer*, probe #2/3)@3
#      source_from_points source(FloatVDB)@0 + points@1
#      advect             data(Float/VectorVDB)@0 + v(VectorVDB)@1
#      buoyancy           v(VectorVDB)@0 + temperature(FloatVDB)@1
#      dissipate          source(FloatVDB)@0 ; disturbance/turbulence/uniformforce v(VectorVDB)@0
#      activate           density(FloatVDB)@0 + activate_pts@2
#    MENUS: all TOKEN round-trip -> _str_menu_set, EXCEPT `axiscontroldir` which is INDEX-stored
#    (set('y') -> evalAsString '1') -> _menu_set with tokens ('x','y','z'). `signature` = plain string
#    token via _try_set. COOK GATE: all 10 cook standalone with correct wiring (probe #1 + #3); no node
#    required a feedback block. ──
_PYRO_DIVMETHOD = ("voxelsize", "resolution")
_PYRO_SRC_METHOD = ("set", "add", "min", "max")
_PYRO_SRC_BORDER = ("input", "constant", "clamp", "mirror", "wrap")
_PYRO_ADVECT_INTEG = ("path", "average")
_PYRO_ADVECT_METHOD = ("bfecc", "sharpen", "euler")
_PYRO_BUOY_OP = ("set", "add")
_PYRO_DISS_MODE = ("evaprate", "subtractrate", "lifespan", "halflife")
_PYRO_DIST_OP = ("set", "add", "rotate")
_PYRO_DIST_MODE = ("cont", "blocks")
_PYRO_TURB_OP = ("set", "add")
_PYRO_UF_OP = ("set", "add", "drag")
_PYRO_AXISDIR = ("x", "y", "z")  # INDEX-stored menu -> _menu_set


@endpoint("cop_pyro_configure")
def cop_pyro_configure(params):
    """COP pyro: define the sim's voxel grid (Pyro Configure). Created in the shared /obj/cops copnet;
    optional `points` (a COP points source) wires to input 0 as `activate_pts` to seed activation.
    div_method (voxelsize/resolution) selects sizing; voxel_size, resolution, origin [x,y,z],
    leaf_dilation, leaf_dilation_dist. BUILT."""
    n = _cop_gen("pyro_configure", params.get("name"))
    if params.get("points"):
        _wire_ref(n, 0, resolve_node(params["points"]))
    applied = {}
    if "div_method" in params:
        applied["div_method"] = _str_menu_set(n, "divmethod", str(params["div_method"]), _PYRO_DIVMETHOD)
    if "voxel_size" in params:
        applied["voxel_size"] = _try_set(n, "voxelsize", clamp(float(params["voxel_size"]), 1e-6, 1e6))
    if "resolution" in params:
        applied["resolution"] = _try_set(n, "resolution", int(clamp(int(params["resolution"]), 1, 100000)))
    if "origin" in params:
        applied["origin"] = _set_tuple(n, "origin", params["origin"])
    if "leaf_dilation" in params:
        applied["leaf_dilation"] = _try_set(n, "leafdilation", int(clamp(int(params["leaf_dilation"]), 0, 100000)))
    if "leaf_dilation_dist" in params:
        applied["leaf_dilation_dist"] = _try_set(n, "leafdilationdist", clamp(float(params["leaf_dilation_dist"]), 0.0, 1e6))
    return {"node": n.path(), "points_wired": n.input(0) is not None, "applied": applied}


@endpoint("cop_pyro_source_from_layer")
def cop_pyro_source_from_layer(params):
    """COP pyro: emit into a field from a source layer (Pyro Source from Layer). `input` = the FloatVDB
    field being written (e.g. from cop_geo_to_layer outtype=floatvdb) -> input 0; `density` = a MONO
    source layer (the values to add) -> input 3 (REQUIRED to cook -- input 3 is a mono layer, NOT a
    VDB). method (set/add/min/max), border (input/constant/clamp/mirror/wrap); amount, thickness,
    noise_scale, noise_elemsize, noise_offset, distort_scale (floats); do_timestep, noise_enable,
    distort_enable (toggles). BUILT."""
    n = child_after(params["input"], "pyro_sourcefromlayer", params.get("name"))  # source FloatVDB -> 0
    _wire_ref(n, 3, resolve_node(params["density"]))  # MONO source layer -> 3
    applied = {"density_wired": n.input(3) is not None}
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _PYRO_SRC_METHOD)
    if "border" in params:
        applied["border"] = _str_menu_set(n, "border", str(params["border"]), _PYRO_SRC_BORDER)
    for key, base in (("amount", "amount"), ("thickness", "thickness"), ("noise_scale", "noise_scale"),
                      ("noise_elemsize", "noise_elemsize"), ("noise_offset", "noise_offset"),
                      ("distort_scale", "distort_scale")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("do_timestep", "dotimestep"), ("noise_enable", "noise_enable"),
                      ("distort_enable", "distort_enable")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_source_from_points")
def cop_pyro_source_from_points(params):
    """COP pyro: emit into a field from a points source (Pyro Source from Points). `input` = the FloatVDB
    field being written -> input 0; `points` = a COP points source -> input 1 (REQUIRED). method
    (set/add/min/max); size, amount, t (floats); do_timestep, noise_enable, distort_enable (toggles).
    BUILT."""
    n = child_after(params["input"], "pyro_sourcefrompoints", params.get("name"))  # source FloatVDB -> 0
    _wire_ref(n, 1, resolve_node(params["points"]))  # points -> 1
    applied = {"points_wired": n.input(1) is not None}
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _PYRO_SRC_METHOD)
    for key, base in (("size", "size"), ("amount", "amount"), ("t", "t")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("do_timestep", "dotimestep"), ("noise_enable", "noise_enable"),
                      ("distort_enable", "distort_enable")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_advect")
def cop_pyro_advect(params):
    """COP pyro: advect a field by a velocity VectorVDB (Pyro Advect). `input` = the field to advect
    (`data`, a Float/VectorVDB layer) -> input 0; `velocity` = the velocity VectorVDB layer (`v`, e.g.
    from cop_geo_to_layer outtype=vectorvdb) -> input 1 (REQUIRED). integrator (path/average), data_method
    + v_method (bfecc/sharpen/euler); scale, cfl_condition, ambient, data_sharpen, v_sharpen (floats);
    max_step (int); use_time_inc, v_enable (toggles). BUILT."""
    n = child_after(params["input"], "pyro_advect", params.get("name"))  # data -> 0
    _wire_ref(n, 1, resolve_node(params["velocity"]))  # velocity VectorVDB -> 1
    applied = {"velocity_wired": n.input(1) is not None}
    if "integrator" in params:
        applied["integrator"] = _str_menu_set(n, "integrator", str(params["integrator"]), _PYRO_ADVECT_INTEG)
    if "data_method" in params:
        applied["data_method"] = _str_menu_set(n, "data_method", str(params["data_method"]), _PYRO_ADVECT_METHOD)
    if "v_method" in params:
        applied["v_method"] = _str_menu_set(n, "v_method", str(params["v_method"]), _PYRO_ADVECT_METHOD)
    for key, base in (("scale", "scale"), ("cfl_condition", "cflcond"), ("ambient", "ambient"),
                      ("data_sharpen", "data_sharpen"), ("v_sharpen", "v_sharpen")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "max_step" in params:
        applied["max_step"] = _try_set(n, "maxstep", int(clamp(int(params["max_step"]), 1, 100000)))
    for key, base in (("use_time_inc", "usetimeinc"), ("v_enable", "v_enable")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_buoyancy")
def cop_pyro_buoyancy(params):
    """COP pyro: add temperature-driven buoyancy force to velocity (Pyro Buoyancy). `input` = the
    velocity VectorVDB (`v`) -> input 0; `temperature` = a temperature FloatVDB layer -> input 1
    (REQUIRED). signature (string token), operation (set/add); axis_control_dir (x/y/z, INDEX-menu);
    scale, direction [x,y,z], ambient, threshold_range, control_range, axis_control (floats);
    use_threshold, use_control, use_axis_control (toggles). BUILT."""
    n = child_after(params["input"], "pyro_buoyancy", params.get("name"))  # velocity -> 0
    _wire_ref(n, 1, resolve_node(params["temperature"]))  # temperature FloatVDB -> 1
    applied = {"temperature_wired": n.input(1) is not None}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "operation" in params:
        applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _PYRO_BUOY_OP)
    if "axis_control_dir" in params:
        applied["axis_control_dir"] = _menu_set(n, "axiscontroldir", str(params["axis_control_dir"]), _PYRO_AXISDIR)
    if "direction" in params:
        applied["direction"] = _set_tuple(n, "direction", params["direction"])
    for key, base in (("scale", "scale"), ("ambient", "ambient"), ("threshold_range", "thresholdrange"),
                      ("control_range", "controlrange"), ("axis_control", "axiscontrol")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("use_threshold", "usethreshold"), ("use_control", "usecontrol"),
                      ("use_axis_control", "useaxiscontrol")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_dissipate")
def cop_pyro_dissipate(params):
    """COP pyro: dissipate a field over time (Pyro Dissipate). `input` = the field to dissipate
    (`source`, a FloatVDB layer) -> input 0. signature (string token), dissipation_mode (evaprate/
    subtractrate/lifespan/halflife), axis_control_dir (x/y/z, INDEX-menu); dissipation_rate,
    subtract_rate, lifespan, halflife, goal_value, goal_tolerance, min_limit, max_limit (floats);
    use_goal_value, use_goal_tolerance, do_min_limit, do_max_limit, use_control (toggles). BUILT."""
    n = child_after(params["input"], "pyro_dissipate", params.get("name"))  # source -> 0
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "dissipation_mode" in params:
        applied["dissipation_mode"] = _str_menu_set(n, "dissipationmode", str(params["dissipation_mode"]), _PYRO_DISS_MODE)
    if "axis_control_dir" in params:
        applied["axis_control_dir"] = _menu_set(n, "axiscontroldir", str(params["axis_control_dir"]), _PYRO_AXISDIR)
    for key, base in (("dissipation_rate", "dissipationrate"), ("subtract_rate", "subtractrate"),
                      ("lifespan", "lifespan"), ("halflife", "halflife"), ("goal_value", "goalvalue"),
                      ("goal_tolerance", "goaltolerance"), ("min_limit", "minlimit"),
                      ("max_limit", "maxlimit")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("use_goal_value", "usegoalvalue"), ("use_goal_tolerance", "usegoaltolerance"),
                      ("do_min_limit", "dominlimit"), ("do_max_limit", "domaxlimit"),
                      ("use_control", "usecontrol")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_disturbance")
def cop_pyro_disturbance(params):
    """COP pyro: add disturbance detail to velocity (Pyro Disturbance). `input` = the velocity VectorVDB
    (`v`) -> input 0. signature (string token), operation (set/add/rotate), mode (cont/blocks),
    axis_control_dir (x/y/z, INDEX-menu); disturbance, ref_scale, block_size, pulse_length, lacunarity,
    roughness (floats); octaves (int). BUILT."""
    n = child_after(params["input"], "pyro_disturbance", params.get("name"))  # velocity -> 0
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "operation" in params:
        applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _PYRO_DIST_OP)
    if "mode" in params:
        applied["mode"] = _str_menu_set(n, "mode", str(params["mode"]), _PYRO_DIST_MODE)
    if "axis_control_dir" in params:
        applied["axis_control_dir"] = _menu_set(n, "axiscontroldir", str(params["axis_control_dir"]), _PYRO_AXISDIR)
    for key, base in (("disturbance", "disturbance"), ("ref_scale", "refscale"),
                      ("block_size", "blocksize"), ("pulse_length", "pulselength"),
                      ("lacunarity", "lac"), ("roughness", "rough")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "octaves" in params:
        applied["octaves"] = _try_set(n, "oct", int(clamp(int(params["octaves"]), 1, 20)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_turbulence")
def cop_pyro_turbulence(params):
    """COP pyro: add turbulence / curl-noise detail to velocity (Pyro Turbulence). `input` = the velocity
    VectorVDB (`v`) -> input 0. signature (string token), operation (set/add), axis_control_dir (x/y/z,
    INDEX-menu); amp, amp_scale, element_size, element_scale, pulse_duration, atten, seed, lacunarity,
    roughness (floats); octaves (int); curl_noise (toggle). BUILT."""
    n = child_after(params["input"], "pyro_turbulence", params.get("name"))  # velocity -> 0
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "operation" in params:
        applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _PYRO_TURB_OP)
    if "axis_control_dir" in params:
        applied["axis_control_dir"] = _menu_set(n, "axiscontroldir", str(params["axis_control_dir"]), _PYRO_AXISDIR)
    for key, base in (("amp", "amp"), ("amp_scale", "ampscale"), ("element_size", "elementsize"),
                      ("element_scale", "elementscale"), ("pulse_duration", "pulseduration"),
                      ("atten", "atten"), ("seed", "seed"), ("lacunarity", "lac"),
                      ("roughness", "rough")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "octaves" in params:
        applied["octaves"] = _try_set(n, "oct", int(clamp(int(params["octaves"]), 1, 20)))
    if "curl_noise" in params:
        applied["curl_noise"] = _try_set(n, "curlnoise", bool(params["curl_noise"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_uniform_force")
def cop_pyro_uniform_force(params):
    """COP pyro: apply a uniform directional force / drag to velocity (Pyro Uniform Force). `input` = the
    velocity VectorVDB (`v`) -> input 0. signature (string token), operation (set/add/drag),
    axis_control_dir (x/y/z, INDEX-menu); scale, direction [x,y,z], threshold_range, control_range,
    axis_control (floats); do_timestep, use_threshold, use_control, use_axis_control (toggles). BUILT."""
    n = child_after(params["input"], "pyro_uniformforce", params.get("name"))  # velocity -> 0
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "operation" in params:
        applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _PYRO_UF_OP)
    if "axis_control_dir" in params:
        applied["axis_control_dir"] = _menu_set(n, "axiscontroldir", str(params["axis_control_dir"]), _PYRO_AXISDIR)
    if "direction" in params:
        applied["direction"] = _set_tuple(n, "direction", params["direction"])
    for key, base in (("scale", "scale"), ("threshold_range", "thresholdrange"),
                      ("control_range", "controlrange"), ("axis_control", "axiscontrol")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("do_timestep", "dotimestep"), ("use_threshold", "usethreshold"),
                      ("use_control", "usecontrol"), ("use_axis_control", "useaxiscontrol")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_activate")
def cop_pyro_activate(params):
    """COP pyro: grow / activate the sim's active voxel region (Pyro Activate). `input` = the density
    FloatVDB layer -> input 0; optional `points` (a COP points source) -> input 2 as `activate_pts`.
    cutoff, leaf_dilation_dist, vel_scale, tang_scale, ambient (floats); leaf_dilation (int); vel_dilate
    (toggle). Clip box: do_clip (toggle -> enables all 6 clip planes) + clip_min [x,y,z] + clip_max
    [x,y,z]. BUILT."""
    n = child_after(params["input"], "pyro_activate", params.get("name"))  # density -> 0
    if params.get("points"):
        _wire_ref(n, 2, resolve_node(params["points"]))
    applied = {}
    for key, base in (("cutoff", "cutoff"), ("leaf_dilation_dist", "leafdilationdist"),
                      ("vel_scale", "velscale"), ("tang_scale", "tangscale"), ("ambient", "ambient")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "leaf_dilation" in params:
        applied["leaf_dilation"] = _try_set(n, "leafdilation", int(clamp(int(params["leaf_dilation"]), 0, 100000)))
    if "vel_dilate" in params:
        applied["vel_dilate"] = _try_set(n, "veldilate", bool(params["vel_dilate"]))
    if params.get("do_clip"):
        for tog in ("doclipxmin", "doclipxmax", "doclipymin", "doclipymax", "doclipzmin", "doclipzmax"):
            _try_set(n, tog, True)
        applied["do_clip"] = True
    if "clip_min" in params and len(params["clip_min"]) == 3:
        for base, v in zip(("clipminx", "clipminy", "clipminz"), params["clip_min"]):
            _try_set(n, base, float(v))
        applied["clip_min"] = True
    if "clip_max" in params and len(params["clip_max"]) == 3:
        for base, v in zip(("clipmaxx", "clipmaxy", "clipmaxz"), params["clip_max"]):
            _try_set(n, base, float(v))
        applied["clip_max"] = True
    return {"node": n.path(), "points_wired": n.input(2) is not None, "applied": applied}


# ── COP: Pyro microsolvers, secondary set (10): the secondary-8 advection-map/
#    extra-force/lighting/projection/mipmap microsolvers + the pyro feedback-block PAIR. Live-probed on
#    H21.0.671. Same MECHANISM as the
#    Core wave: each consumes TYPED VDB *layers* from cop_geo_to_layer (floatvdb -> FloatVDB for density/
#    temperature/mask/reference/emission; vectorvdb -> VectorVDB for velocity `v` and advection maps),
#    primary layer on input 0 via child_after, secondary typed layers via _wire_ref per the probed map.
#    INPUT-INDEX MAP (inputLabels(), the recurring trap):
#      advect_by_map    source@0 + fwdmap(VectorVDB)@1 + revmap(VectorVDB)@2
#      build_advect_map v(VectorVDB)@0
#      axis_force       v(VectorVDB)@0 + mask(*FloatVDB*, NOT mono)@1
#      light_ambient    density(FloatVDB)@0 + mipmap@1 + light@2 + envmap@3
#      light_from_points density@0 + mipmap@1 + light@2 + points@3
#      light_scatter    density@0 + emission(FloatVDB)@1 + light@2
#      project_electro  v(VectorVDB)@0 + reference(*FloatVDB*, REQUIRED)@1 + goaldiv@2 + collision@3 + collisionv@4
#      packed_mipmap    source(density FloatVDB)@0
#      block_begin      density@0 + v@1 + temperature@2 (all 3 REQUIRED to cook) + feedback@3 + activate_pts(pts)@4 + passthrough@5
#      block_end        density@0 + v@1 + temperature@2 + feedback@3 + divergence@4 + collision@5 + collisionv@6
#    SPEC-GOTCHA RESOLUTIONS (live-probed, corrected vs the spec/task assumptions):
#      * `axiscontroldir` does NOT exist on pyro_axisforce (spec was wrong) -> no INDEX menu here.
#      * pyro_buildadvectionmap.`signature` is a genuine FloatParmTemplate (NOT a token selector) ->
#        NOT exposed (set-token raises "Cannot set a numeric parm to a non-numeric").
#      * The `blockpath` (begin<->end linkage, a scene NODE ref) lives on pyro_block_BEGIN, NOT on
#        pyro_block_end (task assumed end). cop_pyro_block_end therefore sets the *begin* node's
#        blockpath to the end's own path.
#      * pyro_projectnondivergentelectrostatic.`kernel` is an INT (voxel blur-kernel size), SAFE.
#    All value menus TOKEN round-trip -> _str_menu_set. `signature` (where a real StringParmTemplate) =
#    plain string token via _try_set. COOK GATE: all 8 secondary + the block pair cook standalone/
#    first-pass headless with the wiring above. ──
_PYRO_AXISFORCE_OP = ("set", "add", "drag", "ldrag")
_PYRO_ORBIT_FALLOFF = ("inv", "const", "lin")


@endpoint("cop_pyro_advect_by_map")
def cop_pyro_advect_by_map(params):
    """COP pyro: advect a field by a precomputed forward/reverse advection map (Pyro Advect by Map).
    `input` = the field to advect (`source`, a Float/VectorVDB layer) -> input 0; `fwd_map` = the
    forward advection-map VectorVDB (e.g. from cop_pyro_build_advection_map) -> input 1 (REQUIRED);
    optional `rev_map` = the reverse map VectorVDB -> input 2. signature (string token), method
    (bfecc/sharpen/euler); sharpen (float). BUILT."""
    n = child_after(params["input"], "pyro_advectbymap", params.get("name"))  # source -> 0
    _wire_ref(n, 1, resolve_node(params["fwd_map"]))  # forward map VectorVDB -> 1
    applied = {"fwd_map_wired": n.input(1) is not None}
    if params.get("rev_map"):
        _wire_ref(n, 2, resolve_node(params["rev_map"]))
        applied["rev_map_wired"] = n.input(2) is not None
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "method" in params:
        applied["method"] = _str_menu_set(n, "method", str(params["method"]), _PYRO_ADVECT_METHOD)
    if "sharpen" in params:
        applied["sharpen"] = _try_set(n, "sharpen", float(params["sharpen"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_build_advection_map")
def cop_pyro_build_advection_map(params):
    """COP pyro: build a forward/reverse advection map from a velocity field (Pyro Build Advection Map).
    `input` = the velocity VectorVDB (`v`, e.g. from cop_geo_to_layer outtype=vectorvdb) -> input 0. The
    resulting map feeds cop_pyro_advect_by_map. integrator (path/average); scale, cfl_condition, ambient
    (floats); max_step (int); time_inc (toggle). NOTE: the node's `signature` param is a genuine float
    (not a layer-type token) and is intentionally not exposed. BUILT."""
    n = child_after(params["input"], "pyro_buildadvectionmap", params.get("name"))  # velocity -> 0
    applied = {}
    if "integrator" in params:
        applied["integrator"] = _str_menu_set(n, "integrator", str(params["integrator"]), _PYRO_ADVECT_INTEG)
    for key, base in (("scale", "scale"), ("cfl_condition", "cflcond"), ("ambient", "ambient")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "max_step" in params:
        applied["max_step"] = _try_set(n, "maxstep", int(clamp(int(params["max_step"]), 1, 100000)))
    if "time_inc" in params:
        applied["time_inc"] = _try_set(n, "timeinc", bool(params["time_inc"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_axis_force")
def cop_pyro_axis_force(params):
    """COP pyro: vortex / axis / orbit force around an axis (Pyro Axis Force). `input` = the velocity
    VectorVDB (`v`) -> input 0; optional `mask` = a FloatVDB mask layer (NOT a mono layer) -> input 1.
    operation (set/add/drag/ldrag), orbit_speed_falloff (inv/const/lin); start, end, radius, strength,
    suction_strength, suction_thickness, axis_speed_range, axis_strength, orbit_speed_range,
    orbit_strength, mask_range (floats); do_timestep, mask_remap (toggles). BUILT."""
    n = child_after(params["input"], "pyro_axisforce", params.get("name"))  # velocity -> 0
    applied = {}
    if params.get("mask"):
        _wire_ref(n, 1, resolve_node(params["mask"]))  # FloatVDB mask -> 1
        applied["mask_wired"] = n.input(1) is not None
    if "operation" in params:
        applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _PYRO_AXISFORCE_OP)
    if "orbit_speed_falloff" in params:
        applied["orbit_speed_falloff"] = _str_menu_set(n, "orbit_speedfalloff", str(params["orbit_speed_falloff"]), _PYRO_ORBIT_FALLOFF)
    for key, base in (("start", "start"), ("end", "end"), ("radius", "radius"), ("strength", "strength"),
                      ("suction_strength", "suction_strength"), ("suction_thickness", "suction_thickness"),
                      ("axis_speed_range", "axis_speedrange"), ("axis_strength", "axis_strength"),
                      ("orbit_speed_range", "orbit_speedrange"), ("orbit_strength", "orbit_strength"),
                      ("mask_range", "mask_range")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("do_timestep", "dotimestep"), ("mask_remap", "mask_remap")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_light_ambient")
def cop_pyro_light_ambient(params):
    """COP pyro: ambient / environment light contribution into a density field (Pyro Light Ambient).
    `input` = the density FloatVDB layer -> input 0; optional `mipmap` (from cop_pyro_packed_mipmap) ->
    input 1, `light` (accumulation layer) -> input 2, `envmap` -> input 3. ambient_exposed,
    ambient_occluded, intensity, exposure, density_scale, envmap_off (floats); steps_per_mip, max_step,
    envmap_res, mip_level (ints). BUILT."""
    n = child_after(params["input"], "pyro_lightambient", params.get("name"))  # density -> 0
    applied = {}
    for key, base, idx in (("mipmap", "mipmap", 1), ("light", "light", 2), ("envmap", "envmap", 3)):
        if params.get(key):
            _wire_ref(n, idx, resolve_node(params[key]))
            applied[base + "_wired"] = n.input(idx) is not None
    for key, base in (("ambient_exposed", "ambientexposed"), ("ambient_occluded", "ambientoccluded"),
                      ("intensity", "intensity"), ("exposure", "exposure"),
                      ("density_scale", "densityscale"), ("envmap_off", "envmapoff")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("steps_per_mip", "steppermip"), ("max_step", "maxstep"),
                      ("envmap_res", "envmapres"), ("mip_level", "miplevel")):
        if key in params:
            applied[key] = _try_set(n, base, int(clamp(int(params[key]), 0, 100000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_light_from_points")
def cop_pyro_light_from_points(params):
    """COP pyro: point / directional light scattering into a density field (Pyro Light from Points).
    `input` = the density FloatVDB layer -> input 0; optional `mipmap` -> input 1, `light`
    (accumulation) -> input 2, `points` (a COP points source) -> input 3. directional (toggle);
    light_pos [x,y,z], light_dir [x,y,z], color [r,g,b], radius, intensity, exposure, density_scale
    (floats); steps_per_mip, max_step (ints). BUILT."""
    n = child_after(params["input"], "pyro_lightfrompoints", params.get("name"))  # density -> 0
    applied = {}
    for key, base, idx in (("mipmap", "mipmap", 1), ("light", "light", 2), ("points", "points", 3)):
        if params.get(key):
            _wire_ref(n, idx, resolve_node(params[key]))
            applied[base + "_wired"] = n.input(idx) is not None
    if "directional" in params:
        applied["directional"] = _try_set(n, "directional", bool(params["directional"]))
    for key, base in (("light_pos", "lightpos"), ("light_dir", "lightdir"), ("color", "color")):
        if key in params:
            applied[key] = _set_tuple(n, base, params[key])
    for key, base in (("radius", "radius"), ("intensity", "intensity"), ("exposure", "exposure"),
                      ("density_scale", "densityscale")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("steps_per_mip", "steppermip"), ("max_step", "maxstep")):
        if key in params:
            applied[key] = _try_set(n, base, int(clamp(int(params[key]), 0, 100000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_light_scatter")
def cop_pyro_light_scatter(params):
    """COP pyro: multiple-scatter light through density + emission (Pyro Light Scatter). `input` = the
    density FloatVDB layer -> input 0; optional `emission` = an emission FloatVDB layer -> input 1,
    `light` (accumulation) -> input 2. density_scale, absorption, emit_scale (floats); iterations,
    mip_level (ints). BUILT."""
    n = child_after(params["input"], "pyro_lightscatter", params.get("name"))  # density -> 0
    applied = {}
    for key, base, idx in (("emission", "emission", 1), ("light", "light", 2)):
        if params.get(key):
            _wire_ref(n, idx, resolve_node(params[key]))
            applied[base + "_wired"] = n.input(idx) is not None
    for key, base in (("density_scale", "densityscale"), ("absorption", "absorption"),
                      ("emit_scale", "emitscale")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("iterations", "iterations"), ("mip_level", "miplevel")):
        if key in params:
            applied[key] = _try_set(n, base, int(clamp(int(params[key]), 0, 100000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_project_electrostatic")
def cop_pyro_project_electrostatic(params):
    """COP pyro: make a velocity field non-divergent via electrostatic projection (Pyro Project Non
    Divergent Electrostatic). `input` = the velocity VectorVDB (`v`) -> input 0; `reference` = a
    FloatVDB reference/region layer -> input 1 (REQUIRED to cook); optional `goal_div` (FloatVDB) ->
    input 2, `collision` (FloatVDB) -> input 3, `collision_v` (VectorVDB) -> input 4. iterations,
    kernel (INT voxel blur-kernel size -- NOT OpenCL, SAFE), block_radius (ints); ambient (float);
    double_voxel, use_block, block_feather, use_point (toggles). BUILT."""
    n = child_after(params["input"], "pyro_projectnondivergentelectrostatic", params.get("name"))  # v -> 0
    _wire_ref(n, 1, resolve_node(params["reference"]))  # FloatVDB reference -> 1 (required)
    applied = {"reference_wired": n.input(1) is not None}
    for key, idx in (("goal_div", 2), ("collision", 3), ("collision_v", 4)):
        if params.get(key):
            _wire_ref(n, idx, resolve_node(params[key]))
            applied[key + "_wired"] = n.input(idx) is not None
    for key, base in (("iterations", "iterations"), ("kernel", "kernel"), ("block_radius", "blockrad")):
        if key in params:
            applied[key] = _try_set(n, base, int(clamp(int(params[key]), 0, 100000)))
    if "ambient" in params:
        applied["ambient"] = _try_set(n, "ambient", float(params["ambient"]))
    for key, base in (("double_voxel", "doublevoxel"), ("use_block", "useblock"),
                      ("block_feather", "blockfeather"), ("use_point", "usepoint")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_packed_mipmap")
def cop_pyro_packed_mipmap(params):
    """COP pyro: build a packed density mipmap (Pyro Packed Mipmap) -- the accelerator that feeds the
    `mipmap` input of the light microsolvers (cop_pyro_light_ambient / cop_pyro_light_from_points).
    `input` = the density FloatVDB layer (`source`) -> input 0. signature (string token); max_depth
    (int). BUILT."""
    n = child_after(params["input"], "pyro_packedmipmap", params.get("name"))  # source density -> 0
    applied = {}
    if "signature" in params:
        applied["signature"] = _try_set(n, "signature", str(params["signature"]))
    if "max_depth" in params:
        applied["max_depth"] = _try_set(n, "maxdepth", int(clamp(int(params["max_depth"]), 0, 20)))
    return {"node": n.path(), "applied": applied}


# ── The pyro feedback-block PAIR (the COP-native pyro SIM loop primitive). block_begin seeds the
#    per-iteration field state (density/v/temperature all REQUIRED to cook the internal reshape);
#    block_end closes the loop and carries the loop controls (iterations/substeps/cache). The begin<->end
#    linkage is the string NODE-ref `blockpath` on the BEGIN node (probed: block_end has no blockpath) --
#    cop_pyro_block_end sets the begin's blockpath to its own path. Both instantiate + wire + cook a
#    first pass headless; a full multi-iteration resimulate is driven by the
#    interactive `resimulate` button / a live cook context (not exercised headless). The `cache_enabled`
#    toggle is an IN-MEMORY frame ring (cachedframes/checkpointframes ints) -- there is NO disk-path
#    param anywhere on the node, so it never writes frames to disk (BUILD-ONLY, verified). ──
_PYRO_BLOCK_METHOD = ("bfecc", "sharpen", "euler")


@endpoint("cop_pyro_block_begin")
def cop_pyro_block_begin(params):
    """COP pyro: start of the pyro feedback-block loop (Pyro Block Begin) -- seeds the per-iteration
    field state. `input` = the initial density FloatVDB layer -> input 0; `velocity` = the initial
    velocity VectorVDB -> input 1; `temperature` = the initial temperature FloatVDB -> input 2 (ALL
    THREE required for the block to cook). Optional `feedback` (FloatVDB) -> input 3, `points` (a COP
    points source, `activate_pts`) -> input 4, `passthrough` -> input 5. Pair with cop_pyro_block_end,
    which sets this node's `blockpath` linkage. Loop-role params: integrator (path/average), data_method
    + v_method (bfecc/sharpen/euler); cfl_condition, data_sharpen, v_sharpen (floats); max_step (int).
    BUILT (see cluster note: first-pass headless cook only)."""
    n = child_after(params["input"], "pyro_block_begin", params.get("name"))  # density -> 0
    _wire_ref(n, 1, resolve_node(params["velocity"]))       # v -> 1
    _wire_ref(n, 2, resolve_node(params["temperature"]))    # temperature -> 2
    applied = {"velocity_wired": n.input(1) is not None, "temperature_wired": n.input(2) is not None}
    for key, idx in (("feedback", 3), ("points", 4), ("passthrough", 5)):
        if params.get(key):
            _wire_ref(n, idx, resolve_node(params[key]))
            applied[key + "_wired"] = n.input(idx) is not None
    if "integrator" in params:
        applied["integrator"] = _str_menu_set(n, "integrator", str(params["integrator"]), _PYRO_ADVECT_INTEG)
    if "data_method" in params:
        applied["data_method"] = _str_menu_set(n, "data_method", str(params["data_method"]), _PYRO_BLOCK_METHOD)
    if "v_method" in params:
        applied["v_method"] = _str_menu_set(n, "v_method", str(params["v_method"]), _PYRO_BLOCK_METHOD)
    for key, base in (("cfl_condition", "cflcond"), ("data_sharpen", "data_sharpen"),
                      ("v_sharpen", "v_sharpen")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "max_step" in params:
        applied["max_step"] = _try_set(n, "maxstep", int(clamp(int(params["max_step"]), 1, 100000)))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_pyro_block_end")
def cop_pyro_block_end(params):
    """COP pyro: end of the pyro feedback-block loop (Pyro Block End) -- closes the loop and holds the
    loop controls. `input` = the loop body's last node (density out) -> input 0; `velocity` (VectorVDB)
    -> input 1 and `temperature` (FloatVDB) -> input 2 (both REQUIRED to close the loop / cook).
    `block_begin` (REQUIRED) = the paired cop_pyro_block_begin's
    node path -- this handler sets THAT begin node's `blockpath` to this end's path (the linkage lives
    on the begin node, not the end). iterations, substeps, kernel (INT voxel blur size), block_radius,
    start_frame (ints); ambient, time_scale (floats); cache_enabled (in-memory frame cache toggle, NO
    disk write), correct_collision, double_voxel, use_block, block_feather, use_point (toggles). BUILT
    (see cluster note: first-pass headless cook only; full resimulate is interactive)."""
    body = resolve_node(params["input"])
    n = body.parent().createNode("pyro_block_end", params.get("name"))
    n.moveToGoodPosition()
    n.setInput(0, body)  # density out -> 0
    for key, idx in (("velocity", 1), ("temperature", 2)):
        if params.get(key):
            _wire_ref(n, idx, resolve_node(params[key]))
    begin = resolve_node(params["block_begin"])
    linked = False
    bp = begin.parm("blockpath")
    if bp is not None:
        try:
            bp.set(n.path()); linked = bp.eval() == n.path()
        except Exception:
            linked = False
    applied = {}
    for key, base in (("iterations", "iterations"), ("substeps", "substeps"), ("kernel", "kernel"),
                      ("block_radius", "blockrad"), ("start_frame", "startframe")):
        if key in params:
            applied[key] = _try_set(n, base, int(clamp(int(params[key]), 0, 1_000_000)))
    for key, base in (("ambient", "ambient"), ("time_scale", "timescale")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("cache_enabled", "cacheenabled"), ("correct_collision", "correctcollision"),
                      ("double_voxel", "doublevoxel"), ("use_block", "useblock"),
                      ("block_feather", "blockfeather"), ("use_point", "usepoint")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "block_begin": begin.path(), "blockpath_linked": linked,
            "velocity_wired": n.input(1) is not None, "temperature_wired": n.input(2) is not None,
            "applied": applied}


@endpoint("cop_pyro_solver")
def cop_pyro_solver(params):
    """COP pyro MACRO (one call): stamp a minimal COP-native pyro feedback-solve LOOP -- auto-wires
    cop_pyro_block_begin (loop start, seeds the per-iteration density/v/temperature state) -> a minimal
    pyro-advect BODY (advects the loop density field by the loop velocity) -> cop_pyro_block_end (closes
    the loop, holds the loop controls), and sets the begin<->end `blockpath` linkage. `input` = the
    initial density FloatVDB -> begin input 0; `velocity` = the initial velocity VectorVDB -> begin input
    1; `temperature` = the initial temperature FloatVDB -> begin input 2 (all three REQUIRED, same as
    cop_pyro_block_begin). Optional `feedback`/`points`/`passthrough` wire begin inputs 3/4/5. Loop
    controls land on the END node: iterations, substeps (ints). Returns the created node paths
    (block_begin / body / block_end) + wiring/linkage flags. A CONVENIENCE skeleton composed from the
    shipped block primitives -- use cop_pyro_block_begin + the cop_pyro_* microsolvers +
    cop_pyro_block_end directly for an arbitrary loop body. BUILT (first-pass headless build/wire; a
    full multi-iteration resimulate is driven interactively)."""
    base = params.get("name") or "pyro_solve"
    begin = child_after(params["input"], "pyro_block_begin", base + "_begin")  # density -> 0
    _wire_ref(begin, 1, resolve_node(params["velocity"]))       # v -> 1
    _wire_ref(begin, 2, resolve_node(params["temperature"]))    # temperature -> 2
    for key, idx in (("feedback", 3), ("points", 4), ("passthrough", 5)):
        if params.get(key):
            _wire_ref(begin, idx, resolve_node(params[key]))
    net = begin.parent()
    # minimal BODY: advect the loop density (begin output 0) by the loop velocity (begin output 1)
    body = net.createNode("pyro_advect", base + "_body")
    body.setInput(0, begin, 0)   # density field  -> data  (begin output 0)
    body.setInput(1, begin, 1)   # velocity field -> v     (begin output 1)
    body.moveToGoodPosition()
    # END: density carried from BODY (out 0), v + temperature pass through from BEGIN (out 1 / out 2)
    end = net.createNode("pyro_block_end", base + "_end")
    end.setInput(0, body, 0)     # advected density -> 0
    end.setInput(1, begin, 1)    # v -> 1
    end.setInput(2, begin, 2)    # temperature -> 2
    end.moveToGoodPosition()
    linked = False
    bp = begin.parm("blockpath")
    if bp is not None:
        try:
            bp.set(end.path()); linked = bp.eval() == end.path()
        except Exception:
            linked = False
    applied = {}
    if "iterations" in params:
        applied["iterations"] = _try_set(end, "iterations", int(clamp(int(params["iterations"]), 0, 1_000_000)))
    if "substeps" in params:
        applied["substeps"] = _try_set(end, "substeps", int(clamp(int(params["substeps"]), 1, 1_000_000)))
    net.layoutChildren()
    return {"block_begin": begin.path(), "body": body.path(), "block_end": end.path(),
            "velocity_wired": begin.input(1) is not None, "temperature_wired": begin.input(2) is not None,
            "body_wired": body.input(0) is not None and body.input(1) is not None,
            "end_wired": all(end.input(i) is not None for i in (0, 1, 2)),
            "blockpath_linked": linked, "applied": applied}


# ── COP: cryptomatte + grunge generators + cable-bundle core (params/arity live-probed
#    H21.0.671). Cryptomatte consumes an UPSTREAM crypto/ID layer
#    (render AOV or the shipped cop_id_to_* / cop_mono_to_id nodes) — chained via child_after; the
#    handler wires an existing layer, it does not synthesize the ID data. Grunge are self-contained
#    all-scalar GENERATORS (size_ref input optional) built in the shared cop_context copnet like the
#    other noise generators. Cable nodes plumb the Copernicus multi-wire *cable* data bundle. Menus
#    `cablemerge.operation` and `cablesplit.type` are TOKEN-stored (probed) → _str_menu_set. ─────────
_CABLE_MERGE_OP = ("union", "intersection", "difference", "copy", "fullunion", "rename")
_CABLE_SPLIT_TYPE = ("int", "float", "vector2", "vector", "vector4", "geo", "ivdb", "fvdb", "vvdb")
_CABLE_TOKENPOS = ("start", "end")   # cablerename tokenpos — INDEX-stored menu (evalAsString '0'/'1')


def _grunge_common(n, params):
    """Apply the shared grunge base + post-block scalars (all _try_set, probe-safe). center accepts a
    scalar or a 2-list. The post-* value knobs auto-enable their paired do-* toggle."""
    applied = {}
    for key, base in (("amplitude", "amp"), ("contrast", "contrast"), ("element_size", "elementsize"),
                      ("element_scale", "elementscale"), ("offset", "off"), ("tile_size", "tilesize")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    if "center" in params:
        c = params["center"]
        applied["center"] = _set_vec(n, "center", c) if isinstance(c, (list, tuple)) else _try_set(n, "center", float(c))
    if "tiled" in params:
        applied["tiled"] = _try_set(n, "dotiled", bool(params["tiled"]))
    if "fold" in params:
        applied["fold"] = _try_set(n, "post_dofold", bool(params["fold"]))
    if "complement" in params:
        applied["complement"] = _try_set(n, "post_docomplement", bool(params["complement"]))
    for key, dotog, valp in (("bias", "post_dobias", "post_bias"), ("gain", "post_dogain", "post_gain"),
                             ("gamma", "post_dogamma", "post_gamma"),
                             ("post_contrast", "post_docontrast", "post_contrast"),
                             ("clamp_min", "post_doclampmin", "post_minimum"),
                             ("clamp_max", "post_doclampmax", "post_maximum")):
        if key in params:
            _try_set(n, dotog, True)
            applied[key] = _try_set(n, valp, float(params[key]))
    return applied


# ── FLOAT-ramp setter (mirrors attribops._set_float_ramp; the grunge_aurora streakweight ramp is a
#    rampParmType.Float, NOT a colour ramp — a scalar weight curve, value range 0..10). Accepts a JSON
#    string or native list of {"pos":f,"value":f,"interp":token}; interp defaults to linear. ──────────
_FRAMP_INTERP = ("constant", "linear", "catmull-rom", "monotonecubic", "bezier", "bspline", "hermite")
_FRAMP_BASIS_NAME = {
    "constant": "Constant", "linear": "Linear", "catmull-rom": "CatmullRom",
    "monotonecubic": "MonotoneCubic", "bezier": "Bezier", "bspline": "BSpline", "hermite": "Hermite",
}


def _set_float_ramp(node, parm, entries):
    """Set a FLOAT `hou.Ramp` parm from typed entries [{"pos":f,"value":f,"interp":"linear"}, ...]
    (per-key basis; defaults to linear on absent/unknown token). Accepts a JSON string or native list.
    Probe-safe (returns bool, never raises)."""
    p = node.parm(parm)
    if isinstance(entries, str):
        try:
            entries = json.loads(entries)
        except Exception:
            return False
    if p is None or not isinstance(entries, (list, tuple)) or not entries:
        return False
    try:
        pts = []
        for e in entries:
            pos = float(e["pos"])
            val = float(e["value"])
            token = str(e.get("interp", "linear")).lower()
            basis = getattr(hou.rampBasis, _FRAMP_BASIS_NAME.get(token, "Linear"), hou.rampBasis.Linear)
            pts.append((pos, val, basis))
        pts.sort(key=lambda x: x[0])
        p.set(hou.Ramp(tuple(x[2] for x in pts), tuple(x[0] for x in pts), tuple(x[1] for x in pts)))
        return True
    except Exception:
        return False


@endpoint("cop_cryptomatte")
def cop_cryptomatte(params):
    """COP filter: extract a single coverage matte from a cryptomatte layer (Cryptomatte). `input` = an
    upstream packed crypto layer (input 0 `crypto1` — a Karma/render cryptomatte AOV, or built from the
    shipped cop_cryptomatte_encode / cop_id_to_* nodes). select_all sums coverage of ALL ids; else
    `selection` = a comma-separated object-name list to include. Out `mask`. Chains after `input`.
    BUILT."""
    n = child_after(params["input"], "cryptomatte", params.get("name"))
    applied = {}
    if "select_all" in params:
        applied["select_all"] = _try_set(n, "selectall", bool(params["select_all"]))
    if "selection" in params:
        applied["selection"] = _try_set(n, "selection", str(params["selection"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_cryptomatte_decode")
def cop_cryptomatte_decode(params):
    """COP filter: decode a packed cryptomatte layer into id/coverage rank pairs (Cryptomatte Decode).
    `input` = the packed crypto layer (input 0 `crypto`). No params. MULTI-OUTPUT: 4 named outputs in
    order — output 0 `id_a`, 1 `cov_a`, 2 `id_b`, 3 `cov_b` (id + coverage for the top two ranks);
    downstream nodes wire the desired output index. Pairs with cop_cryptomatte_encode. Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "cryptomattedecode", params.get("name"))
    return {"node": n.path(), "outputs": ["id_a", "cov_a", "id_b", "cov_b"], "applied": {}}


@endpoint("cop_cryptomatte_encode")
def cop_cryptomatte_encode(params):
    """COP filter: encode id/coverage rank pairs into one packed cryptomatte layer (Cryptomatte Encode).
    FOUR ORDERED REQUIRED inputs — `input`(=id_a)→0, `cov_a`→1, `id_b`→2, `cov_b`→3 (wire order is
    load-bearing: id_a/cov_a = top rank, id_b/cov_b = second). No params. Out `crypto` (feeds
    cop_cryptomatte / cop_cryptomatte_decode). Node is placed in id_a's network and wired after it.
    BUILT."""
    n = child_after(params["input"], "cryptomatteencode", params.get("name"))
    for key, idx in (("cov_a", 1), ("id_b", 2), ("cov_b", 3)):
        if params.get(key):
            _wire_ref(n, idx, resolve_node(params[key]))
    return {"node": n.path(),
            "inputs_wired": {"id_a": n.input(0) is not None, "cov_a": n.input(1) is not None,
                             "id_b": n.input(2) is not None, "cov_b": n.input(3) is not None},
            "applied": {}}


@endpoint("cop_grunge_aurora")
def cop_grunge_aurora(params):
    """COP generator: aurora/streaked-veil weathering pattern (Grunge Aurora). Shared grunge scalars
    (amplitude, center, contrast, element_size, element_scale, offset, tile_size + post fold/complement/
    bias/gain/gamma/post_contrast/clamp_min/clamp_max) plus distinctive: distortion_strength,
    distortion_size, max_steps (int). `streak_ramp` = the streak-weight FLOAT ramp (parm `streakweight`,
    a scalar-weight curve, value range 0..10) -- a JSON/list of {"pos":f,"value":f,"interp":token}
    control points (interp one of constant/linear/catmull-rom/monotonecubic/bezier/bspline/hermite,
    default linear). Optional `size_ref` input sets resolution. Out `grunge`. BUILT."""
    n = _cop_gen("grunge_aurora", params.get("name"))
    if params.get("size_ref"):
        _wire_ref(n, 0, resolve_node(params["size_ref"]))
    applied = _grunge_common(n, params)
    if "distortion_strength" in params:
        applied["distortion_strength"] = _try_set(n, "diststrength", float(params["distortion_strength"]))
    if "distortion_size" in params:
        applied["distortion_size"] = _try_set(n, "distsize", float(params["distortion_size"]))
    if "max_steps" in params:
        applied["max_steps"] = _try_set(n, "maxsteps", int(clamp(int(params["max_steps"]), 1, 100000)))
    if "streak_ramp" in params:
        applied["streak_ramp"] = _set_float_ramp(n, "streakweight", params["streak_ramp"])
    return {"node": n.path(), "applied": applied}


@endpoint("cop_grunge_birchbark")
def cop_grunge_birchbark(params):
    """COP generator: birch-bark material pattern (Grunge Birch Bark). Shared grunge scalars plus
    distinctive: base_coverage, base_sharpness, lenticels, lenticel_size, cracks, crack_size. Optional
    `size_ref` input sets resolution. Out `grunge`. BUILT."""
    n = _cop_gen("grunge_birchbark", params.get("name"))
    if params.get("size_ref"):
        _wire_ref(n, 0, resolve_node(params["size_ref"]))
    applied = _grunge_common(n, params)
    for key, base in (("base_coverage", "basecoverage"), ("base_sharpness", "basesharpness"),
                      ("lenticels", "lenticels"), ("lenticel_size", "lenticelsize"),
                      ("cracks", "cracks"), ("crack_size", "cracksize")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_grunge_layered_noise")
def cop_grunge_layered_noise(params):
    """COP generator: 4-layer composite noise (Grunge Layered Noise) — base noise + base cells +
    secondary noise + secondary cells. Shared grunge scalars plus per-layer knobs: base_noise_amp,
    base_noise_element_size; base_cells (enable), base_cells_amp, base_cells_element_size; sec_noise
    (enable), sec_noise_amp, sec_noise_element_size; sec_cells (enable), sec_cells_amp,
    sec_cells_element_size. Optional `size_ref` input. Out `grunge`. BUILT."""
    n = _cop_gen("grunge_layerednoise", params.get("name"))
    if params.get("size_ref"):
        _wire_ref(n, 0, resolve_node(params["size_ref"]))
    applied = _grunge_common(n, params)
    for key, base in (("base_noise_amp", "basenoise_amp"), ("base_noise_element_size", "basenoise_elementsize"),
                      ("base_cells_amp", "basecells_amp"), ("base_cells_element_size", "basecells_elementsize"),
                      ("sec_noise_amp", "secnoise_amp"), ("sec_noise_element_size", "secnoise_elementsize"),
                      ("sec_cells_amp", "seccells_amp"), ("sec_cells_element_size", "seccells_elementsize")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    for key, base in (("base_cells", "basecells_enable"), ("sec_noise", "secnoise_enable"),
                      ("sec_cells", "seccells_enable")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_grunge_pinebark")
def cop_grunge_pinebark(params):
    """COP generator: pine-bark material pattern (Grunge Pine Bark). Shared grunge scalars plus
    distinctive: bark_intensity, bark_size, bark_roughness. Optional `size_ref` input sets resolution.
    Out `grunge`. BUILT."""
    n = _cop_gen("grunge_pinebark", params.get("name"))
    if params.get("size_ref"):
        _wire_ref(n, 0, resolve_node(params["size_ref"]))
    applied = _grunge_common(n, params)
    for key, base in (("bark_intensity", "barkintensity"), ("bark_size", "barksize"),
                      ("bark_roughness", "barkroughness")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_grunge_rust")
def cop_grunge_rust(params):
    """COP generator: rust/corrosion pattern (Grunge Rust). Shared grunge scalars plus distinctive:
    coverage, softness, rust, rust_size. Optional `size_ref` input sets resolution. Out `grunge`.
    BUILT."""
    n = _cop_gen("grunge_rust", params.get("name"))
    if params.get("size_ref"):
        _wire_ref(n, 0, resolve_node(params["size_ref"]))
    applied = _grunge_common(n, params)
    for key, base in (("coverage", "coverage"), ("softness", "softness"),
                      ("rust", "rust"), ("rust_size", "rustsize")):
        if key in params:
            applied[key] = _try_set(n, base, float(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_cable_merge")
def cop_cable_merge(params):
    """COP: combine two Copernicus cables (Cable Merge) — `input` = input_cable (input 0), `reference`
    = the second cable (input 1). operation (union/intersection/difference/copy/fullunion/rename)
    controls how the two wire sets combine. Out `merge`. Chains after `input`. BUILT."""
    n = child_after(params["input"], "cablemerge", params.get("name"))
    if params.get("reference"):
        _wire_ref(n, 1, resolve_node(params["reference"]))
    applied = {}
    if "operation" in params:
        applied["operation"] = _str_menu_set(n, "operation", str(params["operation"]), _CABLE_MERGE_OP)
    return {"node": n.path(), "reference_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_cable_split")
def cop_cable_split(params):
    """COP: partition a Copernicus cable's wires into two cables (Cable Split). `input` = cable (input
    0). MULTI-OUTPUT: output 0 `matching`, output 1 `non_matching`. Partition by any combination of:
    pattern (use_pattern + `pattern` name-pattern string), type (use_type + `type`
    int/float/vector2/vector/vector4/geo/ivdb/fvdb/vvdb), range (use_range + start/end/offset with
    enable_start/enable_end), chance (use_chance + probability + seed), and select/of (every Nth).
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "cablesplit", params.get("name"))
    applied = {}
    if "type" in params:
        applied["type"] = _str_menu_set(n, "type", str(params["type"]), _CABLE_SPLIT_TYPE)
    if "pattern" in params:
        applied["pattern"] = _try_set(n, "pattern", str(params["pattern"]))
    for key, base in (("use_pattern", "usepattern"), ("use_type", "usetype"), ("use_range", "userange"),
                      ("use_chance", "usechance"), ("enable_start", "enablestart"),
                      ("enable_end", "enableend")):
        if key in params:
            applied[key] = _try_set(n, base, bool(params[key]))
    for key, base in (("select", "select"), ("of", "of"), ("start", "start"), ("end", "end"),
                      ("offset", "offset"), ("seed", "seed")):
        if key in params:
            applied[key] = _try_set(n, base, int(params[key]))
    if "probability" in params:
        applied["probability"] = _try_set(n, "probability", clamp(float(params["probability"]), 0.0, 1.0))
    return {"node": n.path(), "outputs": ["matching", "non_matching"], "applied": applied}


@endpoint("cop_cable_pack")
def cop_cable_pack(params):
    """COP: assemble named wires into one Copernicus cable (Cable Pack). `input` = the first wire/layer
    (input 0 `input1`; the node grows further input slots as wires are added). Optional `fields` = a
    list of wire NAMES — the `fields` multiparm count is set to len(fields) and each `fieldname{i}` is
    filled (like cop_layer_attrib_create's numattrib). With no `fields` the node cooks on its defaults
    (the interactive `setfields` button autofills from wired inputs). Out `cable`. Chains after
    `input`. BUILT."""
    n = child_after(params["input"], "cablepack", params.get("name"))
    applied = {}
    names = _input_list(params.get("fields"))
    if names:
        if _try_set(n, "fields", len(names)):
            for i, nm in enumerate(names, start=1):
                _try_set(n, "fieldname%d" % i, str(nm))
            applied["fields"] = [str(x) for x in names]
    return {"node": n.path(), "applied": applied}


@endpoint("cop_cable_unpack")
def cop_cable_unpack(params):
    """COP: extract named wires out of a Copernicus cable (Cable Unpack). `input` = cable (input 0).
    DYNAMIC OUTPUTS: the node has 0 static outputs — one output is created per entry in the `fields`
    multiparm. Optional `fields` = a list of wire NAMES to extract — the `fields` count is set to
    len(fields) and each `fieldname{i}` is filled (creating that many outputs). With no `fields` the
    node cooks on its defaults (the interactive `setfields` button autofills from the wired cable).
    Chains after `input`. BUILT."""
    n = child_after(params["input"], "cableunpack", params.get("name"))
    applied = {}
    names = _input_list(params.get("fields"))
    if names:
        if _try_set(n, "fields", len(names)):
            for i, nm in enumerate(names, start=1):
                _try_set(n, "fieldname%d" % i, str(nm))
            applied["fields"] = [str(x) for x in names]
    return {"node": n.path(), "applied": applied}


# ── The 4 remaining cable one-offs (thin wire-stream ops; all security-SAFE, DATA-ONLY — no fs path).
#    Params live-probed H21.0.671:
#    cablefilter = 0 params (drops empty wires); cablesort = single `reverse` toggle; cableswitch =
#    single `input` int 0/1 (first@0 / second@1); cablerename = `filters` multiparm (1-based instances
#    enablefilter#/useregex#/global#/from#/to#) + useindex/tokenpos(INDEX menu start|end)/indexoffset.
#    ──────────
@endpoint("cop_cable_filter")
def cop_cable_filter(params):
    """COP: drop empty wires from a Copernicus cable (Cable Filter). `input` = cable (input 0). No
    params -- outputs the input cable with every empty wire removed (so downstream nodes that require
    present inputs always see real data). Out `filter`. Chains after `input`. BUILT."""
    n = child_after(params["input"], "cablefilter", params.get("name"))
    return {"node": n.path(), "applied": {}}


@endpoint("cop_cable_sort")
def cop_cable_sort(params):
    """COP: alphabetically sort a cable's wires by name (Cable Sort). `input` = cable (input 0).
    `reverse` (toggle) reverses the sorted order. Out `sort`. Chains after `input`. BUILT."""
    n = child_after(params["input"], "cablesort", params.get("name"))
    applied = {}
    if "reverse" in params:
        applied["reverse"] = _try_set(n, "reverse", bool(params["reverse"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_cable_switch")
def cop_cable_switch(params):
    """COP: select one of two cables (Cable Switch). `input` = the first cable (input 0 `first`);
    optional `second` = the second cable (input 1 `second`). `select` (int, 0 or 1) chooses which cable
    to output -- 0 = first, 1 = second. Out `switch`. Chains after `input`. BUILT."""
    n = child_after(params["input"], "cableswitch", params.get("name"))
    applied = {}
    if params.get("second"):
        _wire_ref(n, 1, resolve_node(params["second"]))
    if "select" in params:
        applied["select"] = _try_set(n, "input", int(clamp(int(params["select"]), 0, 1)))
    return {"node": n.path(), "second_wired": n.input(1) is not None, "applied": applied}


@endpoint("cop_cable_rename")
def cop_cable_rename(params):
    """COP: rename a cable's wires by pattern replacement (Cable Rename). `input` = cable (input 0).
    `renames` = a list of replacement filters run in sequence -- each entry a {"from":pattern,
    "to":replacement,"regex":bool,"global":bool} dict (or a [from, to] pair). The `filters` multiparm
    count is set to len(renames) and each 1-based instance is filled (enablefilter{i}=1, from{i}, to{i},
    useregex{i}, global{i}); `from` uses Houdini pattern-replace syntax (or extended regex when regex is
    true), `global` replaces every occurrence (default: first only). Optional `add_index` (useindex
    toggle) appends a wire index, `token_pos` (start|end) sets where the index is added, `index_offset`
    (int 0..10) offsets the wire index. Out `rename`. Chains after `input`. BUILT."""
    n = child_after(params["input"], "cablerename", params.get("name"))
    applied = {}
    entries = params.get("renames")
    if isinstance(entries, str):
        try:
            entries = json.loads(entries)
        except Exception:
            entries = None
    if isinstance(entries, (list, tuple)) and entries:
        if _try_set(n, "filters", len(entries)):
            landed = []
            for i, e in enumerate(entries, start=1):
                if isinstance(e, dict):
                    frm, to = str(e.get("from", "")), str(e.get("to", ""))
                    rgx, glob = bool(e.get("regex", False)), bool(e.get("global", False))
                else:  # a [from, to] pair
                    seq = list(e)
                    frm = str(seq[0]) if len(seq) > 0 else ""
                    to = str(seq[1]) if len(seq) > 1 else ""
                    rgx = glob = False
                _try_set(n, "enablefilter%d" % i, True)
                _try_set(n, "from%d" % i, frm)
                _try_set(n, "to%d" % i, to)
                _try_set(n, "useregex%d" % i, rgx)
                _try_set(n, "global%d" % i, glob)
                landed.append({"from": frm, "to": to, "regex": rgx, "global": glob})
            applied["renames"] = landed
    if "add_index" in params:
        applied["add_index"] = _try_set(n, "useindex", bool(params["add_index"]))
    if "token_pos" in params:
        applied["token_pos"] = _menu_set(n, "tokenpos", str(params["token_pos"]), _CABLE_TOKENPOS)
    if "index_offset" in params:
        applied["index_offset"] = _try_set(n, "indexoffset", int(clamp(int(params["index_offset"]), 0, 10)))
    return {"node": n.path(), "applied": applied}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# COP SECURITY-GATED cluster — the Copernicus nodes that touch the FILESYSTEM or a model file. Every
# filesystem-path parameter is routed through `confined_path` (server.confined_path — realpath-confined
# to the arm.json working dir; RAISES on escape), the SAME last-line-of-defense the SOP file lane uses.
# NO raw caller path ever reaches a parm. Live-probed on H21.0.671:
#   file(0-in)            filename  = FileReference (.exr/.pic/... input image)          -> CONFINED
#   rop_image(1-in)       copoutput = FileReference (output image)                        -> CONFINED
#                         pre/preframe/postframe/postwrite/postrender = SCRIPT-CALLBACK command fields
#                         (RCE-shaped) -> DELIBERATELY NOT EXPOSED (stay empty/default).
#   font(1-in,opt)        file      = FileReference (*.ttf/*.otf/... font file)           -> CONFINED
#   onnx(multi-in)        modelfile = FileReference (*.onnx model/weights)                -> CONFINED
# DATA-ONLY (probe-confirmed: NO filesystem/dir/config-file param exists — nothing to confine, built
# as ordinary data nodes):
#   slapcompimport  in-memory slap-comp render buffer (reload/live/cameraspace/aovs; 0 disk path)
#   cache           in-memory frame cache (maxframes/clearonchange; 0 disk path)
#   fetch           `coppath` = a COP NodeReference (not a filesystem path)
#   cameraimport    `camera`  = an OBJ NodeReference (not a filesystem path)
#   ociotransform   source/to space are OCIO colorspace NAME strings (Regular), not paths
#   livevideo       `source`/`config` = capture-DEVICE id/config strings (Regular), not paths
#   denoiseai       `denoiser` = a built-in denoiser MENU token (Regular); weights ship in the lib —
#                   NO model-file parm exists on the node, so there is no path to confine.
# NOT BUILT (RCE surfaces — must not exist as endpoints): `opencl` (arbitrary GPU-kernel source),
# `pythonsnippet` (arbitrary Python), `wrangle` (raw COP VEX — its `vexsnippet` parm is a different
# VEX context from the SOP/DOP `snippet`, and `validate_attrib_vex` rejects any profile != attrib_v1;
# a COP wrangle would need a NEW validation profile = new security policy, deferred). ─────────
@endpoint("cop_file")
def cop_file(params):
    """COP generator: read an image from disk (File). `filename` = the input image path -- CONFINED to
    the working directory (a path outside it RAISES). Created in the shared /obj/cops copnet. BUILT."""
    n = _cop_gen("file", params.get("name"))
    applied = {}
    if "filename" in params:
        safe = confined_path(str(params["filename"]))  # RAISES on escape
        applied["filename"] = _try_set(n, "filename", safe)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_rop_image")
def cop_rop_image(params):
    """COP output driver: write the incoming COP stream to an image on disk (ROP Image Output). `input`
    = the COP layer to render (input 0, chained). `output` = the output image path -- CONFINED to the
    working directory (outside RAISES). Optional `coppath` = a COP NodeReference to render instead of
    the wired input; `mkpath` creates missing output dirs. The pre/post render/frame SCRIPT-callback
    parms are RCE-shaped and are DELIBERATELY NOT EXPOSED. BUILT."""
    n = child_after(params["input"], "rop_image", params.get("name"))
    applied = {}
    if "output" in params:
        safe = confined_path(str(params["output"]))  # RAISES on escape
        applied["output"] = _try_set(n, "copoutput", safe)
    if "coppath" in params:
        applied["coppath"] = _try_set(n, "coppath", str(params["coppath"]))  # COP node ref, not fs
    if "mkpath" in params:
        applied["mkpath"] = _try_set(n, "mkpath", bool(params["mkpath"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_font")
def cop_font(params):
    """COP: render text as an image (Font). `file` = the font-file path (*.ttf/*.otf/*.ttc/...) --
    CONFINED to the working directory (outside RAISES). `text` = the string to render. Created in the
    shared /obj/cops copnet; optional `input` wires a background layer to input 0. BUILT."""
    n = _cop_gen("font", params.get("name"))
    if params.get("input"):
        _wire_ref(n, 0, resolve_node(params["input"]))
    applied = {}
    if "file" in params:
        safe = confined_path(str(params["file"]))  # RAISES on escape
        applied["file"] = _try_set(n, "file", safe)
    if "text" in params:
        applied["text"] = _try_set(n, "text", str(params["text"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_onnx")
def cop_onnx(params):
    """COP: run ONNX model inference over an image (ONNX Inference). `input` = the source layer (input
    0, chained). `model_file` = the .onnx model/weights path -- CONFINED to the working directory
    (outside RAISES). BUILT."""
    n = child_after(params["input"], "onnx", params.get("name"))
    applied = {}
    if "model_file" in params:
        safe = confined_path(str(params["model_file"]))  # RAISES on escape
        applied["model_file"] = _try_set(n, "modelfile", safe)
    return {"node": n.path(), "applied": applied}


@endpoint("cop_slapcomp_import")
def cop_slapcomp_import(params):
    """COP: pull the in-memory slap-comp render buffer (Slap Comp Import). DATA-ONLY -- no disk path
    (the slap comp is an in-memory render/MPlay buffer). `live` re-imports on cook; `camera_space`
    toggles slap-comp camera space. Optional `input` wires to input 0. Created in /obj/cops. BUILT."""
    n = _cop_gen("slapcompimport", params.get("name"))
    if params.get("input"):
        _wire_ref(n, 0, resolve_node(params["input"]))
    applied = {}
    if "live" in params:
        applied["live"] = _try_set(n, "live", bool(params["live"]))
    if "camera_space" in params:
        applied["camera_space"] = _try_set(n, "slapcompcameraspace", bool(params["camera_space"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_cache")
def cop_cache(params):
    """COP: an in-memory per-frame cache of the incoming layer (Cache). DATA-ONLY -- no disk path (RAM
    cache only). `input` = the layer to cache (input 0, chained). max_frames caps cached frames;
    clear_on_change flushes when upstream changes. BUILT."""
    n = child_after(params["input"], "cache", params.get("name"))
    applied = {}
    if "max_frames" in params:
        applied["max_frames"] = _try_set(n, "maxframes", int(clamp(int(params["max_frames"]), 1, 1000000)))
    if "clear_on_change" in params:
        applied["clear_on_change"] = _try_set(n, "clearonchange", bool(params["clear_on_change"]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_fetch")
def cop_fetch(params):
    """COP generator: fetch another COP node's output by path (Fetch). DATA-ONLY -- `coppath` is a COP
    NodeReference (an in-scene node path), NOT a filesystem path. Created in /obj/cops. BUILT."""
    n = _cop_gen("fetch", params.get("name"))
    applied = {}
    if "coppath" in params:
        applied["coppath"] = _try_set(n, "coppath", str(params["coppath"]))  # COP node ref, not fs
    return {"node": n.path(), "applied": applied}


@endpoint("cop_camera_import")
def cop_camera_import(params):
    """COP generator: import a scene camera's parameters (Camera Import). DATA-ONLY -- `camera` is an
    OBJ NodeReference (an in-scene camera path), NOT a filesystem path. Created in /obj/cops. BUILT."""
    n = _cop_gen("cameraimport", params.get("name"))
    applied = {}
    if "camera" in params:
        applied["camera"] = _try_set(n, "camera", str(params["camera"]))  # OBJ node ref, not fs
    return {"node": n.path(), "applied": applied}


@endpoint("cop_ocio_transform")
def cop_ocio_transform(params):
    """COP: apply an OpenColorIO color-space transform (OCIO Transform). DATA-ONLY -- source_space/
    to_space/to_display/to_view are OCIO color-space NAME strings (resolved against the active OCIO
    config), NOT filesystem paths. `input` = the source layer (input 0, chained). BUILT."""
    n = child_after(params["input"], "ociotransform", params.get("name"))
    applied = {}
    for key, base in (("source_space", "sourcespace"), ("to_space", "tospace"),
                      ("to_display", "todisplay"), ("to_view", "toview")):
        if key in params:
            applied[key] = _try_set(n, base, str(params[key]))
    return {"node": n.path(), "applied": applied}


@endpoint("cop_live_video")
def cop_live_video(params):
    """COP generator: capture frames from a live video/webcam device (Live Video). DATA-ONLY --
    `source`/`config` are capture-DEVICE id/config strings (Regular, device selection), NOT filesystem
    paths. Created in /obj/cops. BUILT."""
    n = _cop_gen("livevideo", params.get("name"))
    applied = {}
    if "source" in params:
        applied["source"] = _try_set(n, "source", str(params["source"]))  # device id, not fs
    if "config" in params:
        applied["config"] = _try_set(n, "config", str(params["config"]))  # device config, not fs
    return {"node": n.path(), "applied": applied}


@endpoint("cop_denoise_ai")
def cop_denoise_ai(params):
    """COP: AI-denoise the incoming layer (Denoise AI). DATA-ONLY -- `denoiser` is a built-in denoiser
    MENU token (weights ship inside the denoiser library); the node exposes NO model-file parm, so
    there is no path to confine. `input` = the noisy layer (input 0, chained). BUILT."""
    n = child_after(params["input"], "denoiseai", params.get("name"))
    applied = {}
    if "denoiser" in params:
        applied["denoiser"] = _try_set(n, "denoiser", str(params["denoiser"]))  # built-in menu, not fs
    return {"node": n.path(), "applied": applied}

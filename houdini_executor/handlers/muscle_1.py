"""Muscle & Tissue — data-only handlers for the modern SURFACE-muscle SOPs (H21.0.671).

Params verified against live H21.0.671; every endpoint is proven with
a headless cook over the reusable fixture (a capped muscle surface with a
`muscle_id` prim attribute, and its tetrahedralized solid).

The modern Muscle & Tissue system is SURFACE / mesh based: a clean polygonal muscle surface gets a
`muscle_id` (Muscle ID SOP), is tetrahedralized (Muscle Solidify SOP), then flexed/simulated. These are
the two surface-muscle SOPs that cook data-only:

  franken_muscle        (frankenmuscle)      — B chain: input0 = muscle geo (target), input1 = optional
                                               id-source geometry; transfers/assigns `muscle_id` sub-
                                               regions by proximity so one solid mesh behaves as several
                                               independent muscles.
  franken_muscle_paint  (frankenmusclepaint) — B chain: input0 = muscle geo; a paint front-end for
                                               `muscle_id` masks. Data-only here = passthrough + attribute
                                               / stroke config; the interactive stroking is not driven.

SECURITY (Muscle lane, data-only):
  * No code/callback parm is ever set or exposed. frankenmuscle has none. frankenmusclepaint's only
    file surface is the two stash paths (`strokegeofile` / `bakedgeofile`), which are routed through
    confined_path(); its file-I/O BUTTONS (`movestashtofile` / `loadstashfromfile`) and all other action
    buttons (`reset` / `recache` / `erasestrokes`) are NEVER pressed. String params otherwise are
    attribute / group / muscle-id NAMES only.

DEFERRED / SKIPPED nodes:
  * muscle (SOP)          — legacy anchor/object-driven metaball muscle; reads anchors from object refs
                            (`../restanchor`), no data-only standalone cook path. DEFERRED.
  * deformmuscle (SOP)    — requires the legacy `metaCaptGroups` detail attr from the metaball-capture
                            pipeline; not producible data-only. DEFERRED.
  * muscleupdatevellum    — DOP muscle-vellum sim node (brief excludes muscle DOP solvers). DEFERRED.
  * fourpointmuscle / threepointmuscle / twopointmuscle / musclepin / musclerig / riggedmuscle — Object-
    context legacy muscle nodes (anchor-object inputs, `pickscript`, no cookable geometry stream). SKIPPED.
  * sidefx::recipe::muscles::* (3) — SOP-tab-menu RECIPES, not instantiable node types. SKIPPED.
  * musclerigstrokebuilder / musclestrokebuilder — HDA-internal interactive stroke builders
    (`state_eventcallback` code + stroke ramps). SKIPPED.
"""

import hou
from houdini_executor.server import clamp, child_after, bridge_input, confined_path, endpoint
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe local helpers (copied per handler file, per house convention) ─────────────────────




def _cooked(n):
    g = n.geometry()
    out = {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}
    # Honest-return coverage: franken_muscle assembles/ids muscles, so a recipe verify reads whether the
    # per-prim muscle_id landed and how many distinct muscles resulted (`prims` is the surface poly count,
    # not the muscle count). Guarded, so it is simply omitted when no muscle_id was written.
    try:
        if g.findPrimAttrib("muscle_id") is not None:
            out["muscle_id_written"] = True
            try:
                vals = g.primStringAttribValues("muscle_id")
            except Exception:  # noqa: BLE001 - non-string muscle_id
                vals = g.primIntAttribValues("muscle_id")
            out["muscle_count"] = len(set(vals))
    except Exception:  # noqa: BLE001 - readback convenience must never break a good cook
        pass
    return out


# ── ordered-menu token tuples (position == the stored index) ─────────────────────────────────────
_FM_GROUPTYPE = ("guess", "breakpoints", "edges", "points", "prims")
_FMP_ATTRTYPE = ("color", "float", "integer")
_FMP_OP = ("paint", "smooth", "erase", "sample", "paintbg", "samplebg")
_FMP_PAINTMODE = ("over", "add", "max", "min", "mul")
_FMP_SHAPE = ("sphere", "surface", "screen", "fill", "nearest")
_FMP_RECACHE = ("original", "ray", "primuv", "texuv")


# ── 1. franken_muscle (frankenmuscle) — B chain, input0=muscle geo, input1=opt id source ─────────
@endpoint("franken_muscle")
def franken_muscle(params):
    """Muscle Franken Muscle (frankenmuscle) — assigns multiple `muscle_id` sub-regions within a single
    muscle geometry so one solid mesh behaves as several independent muscles. `muscle` (input 0) = the
    muscle geometry to id; `id_source` (input 1) = optional geometry whose `muscle_id` attribute is
    transferred onto input 0 by proximity search. SECURITY: attribute/group/muscle-id names only; no
    file/code surface."""
    n = child_after(params["muscle"], "frankenmuscle", params.get("name"))
    if params.get("id_source"):
        bridge_input(n, params["id_source"], index=1, name_hint="id_source")
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "group_type" in params:
        _menu_set(n, "grouptype", str(params["group_type"]), _FM_GROUPTYPE)
    if "max_distance" in params:
        _try_set(n, "maxdist", clamp(float(params["max_distance"]), 0.0, 1e6))
    if "falloff" in params:
        _try_set(n, "falloff", clamp(float(params["falloff"]), 0.0, 1e6))
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 0.0, 1e6))
    if "keep_muscle_id" in params:
        _try_set(n, "keepmuscleid", bool(params["keep_muscle_id"]))
    if "isolate_muscle" in params:
        _try_set(n, "isolatemuscle", bool(params["isolate_muscle"]))
    if "isolate_id" in params:
        _try_set(n, "isolateid", str(params["isolate_id"]))
    return _cooked(n)


# ── 2. franken_muscle_paint (frankenmusclepaint) — B chain, input0=muscle geo ────────────────────
@endpoint("franken_muscle_paint")
def franken_muscle_paint(params):
    """Muscle Franken Muscle Paint (frankenmusclepaint) — the paint front-end for `muscle_id` masks on a
    muscle geometry (input 0). Data-only: this configures the target attribute + stroke defaults and
    passes the geometry through (the interactive stroking is not driven headless). SECURITY: the two
    stash file paths are confined to the working dir and their file-I/O buttons are NEVER pressed;
    string params are attribute/group names only; no code surface."""
    n = child_after(params["muscle"], "frankenmusclepaint", params.get("name"))

    # Target attribute / group selection.
    if "stroke_group" in params:
        _try_set(n, "stroke_group", str(params["stroke_group"]))
    if "display_group" in params:
        _try_set(n, "displaygroup", bool(params["display_group"]))
    if "use_display" in params:
        _try_set(n, "usedisplay", bool(params["use_display"]))
    if "attribute" in params:
        _try_set(n, "stroke_attrib", str(params["attribute"]))
    if "attribute_type" in params:
        _menu_set(n, "stroke_attribtype", str(params["attribute_type"]), _FMP_ATTRTYPE)

    # Stroke defaults (data-only config; no interactive stroking is driven).
    if "operation" in params:
        _menu_set(n, "stroke_operation", str(params["operation"]), _FMP_OP)
    if "paint_mode" in params:
        _menu_set(n, "stroke_paintmode", str(params["paint_mode"]), _FMP_PAINTMODE)
    if "shape" in params:
        _menu_set(n, "stroke_shape", str(params["shape"]), _FMP_SHAPE)
    if "radius" in params:
        _try_set(n, "stroke_radius", clamp(float(params["radius"]), 0.0, 1e4))
    if "opacity" in params:
        _try_set(n, "stroke_opacity", clamp(float(params["opacity"]), 0.0, 1.0))
    if "soft_edge" in params:
        _try_set(n, "stroke_softedge", clamp(float(params["soft_edge"]), 0.0, 1.0))
    if "fg_value" in params:
        _try_set(n, "fgfloat", clamp(float(params["fg_value"]), -1e6, 1e6))
    if "bg_value" in params:
        _try_set(n, "bgfloat", clamp(float(params["bg_value"]), -1e6, 1e6))

    # Caching config (toggles only; the recache/erase BUTTONS are never pressed).
    if "recache_method" in params:
        _menu_set(n, "recachemethod", str(params["recache_method"]), _FMP_RECACHE)
    if "save_cache" in params:
        _try_set(n, "savecache", bool(params["save_cache"]))
    if "live_mode" in params:
        _try_set(n, "livemode", bool(params["live_mode"]))
    if "do_caching" in params:
        _try_set(n, "docaching", bool(params["do_caching"]))

    # SECURITY: file-path strings routed through confined_path (reads stay in the working dir); the
    # file-I/O buttons (movestashtofile / loadstashfromfile) are NEVER pressed.
    stroke_geo_file = None
    if params.get("stroke_geo_file"):
        stroke_geo_file = confined_path(params["stroke_geo_file"])
        _try_set(n, "strokegeofile", stroke_geo_file)
    baked_geo_file = None
    if params.get("baked_geo_file"):
        baked_geo_file = confined_path(params["baked_geo_file"])
        _try_set(n, "bakedgeofile", baked_geo_file)

    out = _cooked(n)
    out["stroke_geo_file"] = stroke_geo_file
    out["baked_geo_file"] = baked_geo_file
    return out

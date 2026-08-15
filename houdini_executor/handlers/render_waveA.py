"""Render/ROP WIRE-ONLY handlers — out/Driver native image renderers.

Six /out Driver render/export ROPs, built + wired + configured but NEVER executed by the MCP: the
human fires the render. Params verified against live H21.0.671 (parm names/types, create-in-/out,
code-hook blanking, file confinement, cost clamps). Reference pattern: labs_gameengine._out_node ROP exporters + tree.py
maps_baker cost clamps.

Nodes (all context out/Driver, all created in /out via _out_node):
  * ifd        (Mantra CPU image render ROP)      -> render_mantra
  * karma      (Karma image render ROP, Driver)   -> render_karma_rop
  * usdrender  (USD/Husk render ROP, Driver)      -> render_usd
  * comp       (COP-network composite write ROP)  -> render_comp
  * image      (COP image render ROP)             -> render_image
  * ifdarchive (Mantra IFD scene-archive export)  -> export_ifd_archive

NON-NEGOTIABLE SECURITY POSTURE (this lane's whole point):
  1. NEVER execute. No .render()/.execute()/executeBackground/pressButton; no render_button_parm
     (execute/executebackground/render/renderdialog/renderpreview) is ever set or pressed.
  2. BLANK every code_surface_parm (defense-in-depth) — the per-frame/per-render code hooks
     prerender/postrender/preframe/postframe (+ l*/t* variants), and per-node husk_prerender/…,
     rendercommand, runcommand, vm_tilecallback. String hooks -> "" ; the t* "separate process"
     gate toggles -> 0. None are ever exposed as params.
  3. CONFINE every file-out through confined_path() and ONLY when the caller supplies it (WIRE-ONLY:
     absent -> leave the ROP default for the human to edit). confined_path realpath-confines to the
     working dir and rejects `..`/path-separator/drive escapes even inside a $F/$(CHANNEL) token.
  4. Render-SOURCE params (camera / objects / lights / coppath / loppath / obj path) are SCENE-NODE
     PATHS = DATA, not files: set verbatim as strings; never confined, never resolved/cooked here.
  5. CLAMP every exposed cost lever: resolution 16-8192, samples 1-256, frames 1-1000.
  6. No code/callback/script param is ever set from input (standing posture).
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, out_context
from houdini_executor.handlers._parmutil import _try_set

# Hard cost bounds (per brief).
_RES_LO, _RES_HI = 16, 8192
_SAMP_LO, _SAMP_HI = 1, 256
_FRAME_LO, _FRAME_HI = 1, 1000


def _out_node(ntype, name=None):
    """Create a Driver/ROP node in /out (created on demand). WIRE-ONLY: never executed."""
    out = out_context()
    return out.createNode(ntype, name) if name else out.createNode(ntype)




def _is_string_parm(p):
    try:
        return isinstance(p.parmTemplate(), hou.StringParmTemplate)
    except Exception:
        return False


def _blank_code(node, names):
    """Defense-in-depth: neutralise every code-execution hook on `node`. String hooks (the actual
    code surface: prerender/postrender/preframe/postframe/l*/t*-frame, husk_*, rendercommand,
    runcommand, vm_tilecallback) -> "" ; t* separate-process gate toggles -> 0. Returns the list of
    string-hook parms confirmed empty, for the verify harness to assert."""
    blanked = []
    for nm in names:
        p = node.parm(nm)
        if p is None:
            continue
        try:
            if _is_string_parm(p):
                p.set("")
                blanked.append(nm)
            else:
                p.set(0)
        except Exception:
            pass
    return blanked


def _confine_out(node, parm, value):
    """Confine a file-out path and set it, ONLY when the caller supplied `value`. Returns the
    realpath-confined string (or None when not supplied)."""
    if not value:
        return None
    resolved = confined_path(value)
    _try_set(node, parm, resolved)
    return resolved


def _set_frames(node, params):
    """Clamp + set the frame range (f1/f2/f3) to 1-1000 when supplied, flip trange to range mode,
    and keep f2 >= f1. WIRE-ONLY cost clamp."""
    if not any(k in params for k in ("f1", "f2", "f3")):
        return None
    f1 = int(clamp(int(params.get("f1", 1)), _FRAME_LO, _FRAME_HI))
    f2 = int(clamp(int(params.get("f2", f1)), _FRAME_LO, _FRAME_HI))
    f2 = max(f1, f2)
    f3 = int(clamp(int(params.get("f3", 1)), 1, _FRAME_HI))
    _try_set(node, "trange", "normal")   # render the given range (menu token; tolerant)
    _try_set(node, "f1", f1)
    _try_set(node, "f2", f2)
    _try_set(node, "f3", f3)
    return [f1, f2, f3]


def _set_res(node, params, xy_parms, toggles=()):
    """Clamp + set a resolution override (16-8192) across the node's candidate res parm names when
    width/height supplied, first enabling any override toggle so the value takes effect."""
    if "width" not in params and "height" not in params:
        return None
    w = int(clamp(int(params.get("width", 256)), _RES_LO, _RES_HI))
    h = int(clamp(int(params.get("height", w)), _RES_LO, _RES_HI))
    for t in toggles:
        _try_set(node, t, 1)
    xp, yp = xy_parms
    _try_set(node, xp, w)
    _try_set(node, yp, h)
    return [w, h]


def _set_samples(node, params, parms):
    """Clamp + set sampling (1-256) across the node's candidate sample parm names."""
    if "samples" not in params:
        return None
    s = int(clamp(int(params["samples"]), _SAMP_LO, _SAMP_HI))
    for p in parms:
        _try_set(node, p, s)
    return s


# Full code-hook lists per node, blanked defense-in-depth.
_CODE_STD = ["lpostframe", "lpostrender", "lpreframe", "lprerender", "postframe", "postrender",
             "preframe", "prerender", "tpostframe", "tpostrender", "tpreframe", "tprerender"]
_CODE_IFD = _CODE_STD + ["vm_tilecallback"]
_CODE_KARMA = _CODE_STD + ["runcommand"]
_CODE_USD = (_CODE_STD + ["runcommand", "rendercommand", "husk_prerender", "husk_postrender",
             "husk_preframe", "husk_postframe", "husk_tprerender", "husk_tpostrender",
             "husk_tpreframe", "husk_tpostframe"])


def _srcpaths(node, params, mapping):
    """Set render-SOURCE scene-node PATH params verbatim (DATA, not files). `mapping` is
    friendly_param -> node_parm. Returns the set of {friendly: value} actually applied."""
    applied = {}
    for friendly, nparm in mapping.items():
        v = params.get(friendly)
        if v:
            _try_set(node, nparm, str(v))
            applied[friendly] = str(v)
    return applied


# ── 1. ifd (Mantra CPU image render ROP) ─────────────────────────────────────────────────────────
@endpoint("render_mantra")
def render_mantra(params):
    """Mantra CPU image render ROP (ifd, out/) — WIRE-ONLY: builds + wires the Mantra render in /out;
    YOU fire it. Render source is scene-node PATHS (data): `camera` (render cam), `objects`
    (force/candidate objects), `lights` (force lights) set verbatim. `output` -> vm_picture (confined).
    Cost clamped: width/height 16-8192 (res override enabled), samples 1-256 (vm_samplesx/y), frames
    1-1000. SECURITY: never executed; all code hooks (pre/post render+frame, vm_tilecallback) blanked;
    render buttons never pressed."""
    n = _out_node("ifd", params.get("name"))
    blanked = _blank_code(n, _CODE_IFD)
    src = _srcpaths(n, params, {"camera": "camera", "objects": "vobject", "lights": "alights"})
    out_path = _confine_out(n, "vm_picture", params.get("output"))
    res = _set_res(n, params, ("res_overridex", "res_overridey"), toggles=("override_camerares",))
    samp = _set_samples(n, params, ("vm_samplesx", "vm_samplesy"))
    frames = _set_frames(n, params)
    return {"node": n.path(), "output": out_path, "rendered": False,
            "sources": src, "resolution": res, "samples": samp, "frames": frames,
            "code_hooks_blanked": blanked,
            "note": "Mantra ROP built WIRE-ONLY in /out; fire the render yourself"}


# ── 2. karma (Karma image render ROP, Driver context) ────────────────────────────────────────────
@endpoint("render_karma_rop")
def render_karma_rop(params):
    """Karma image render ROP in Driver context (karma, out/) — WIRE-ONLY: builds + wires the Karma
    render in /out; YOU fire it. (Distinct from the Solaris setup_karma/karma_render_settings tools —
    this is the /out Driver ROP.) Render source is scene-node PATHS: `camera`, `objects`, `lights`.
    `output` -> picture (confined). Cost clamped: width/height 16-8192, samples 1-256 (samplesperpixel
    + pathtracedsamples), frames 1-1000. SECURITY: never executed; code hooks (pre/post render+frame,
    runcommand) blanked; render buttons never pressed."""
    n = _out_node("karma", params.get("name"))
    blanked = _blank_code(n, _CODE_KARMA)
    src = _srcpaths(n, params, {"camera": "camera", "objects": "objects", "lights": "lights"})
    out_path = _confine_out(n, "picture", params.get("output"))
    res = _set_res(n, params, ("resolutionx", "resolutiony"), toggles=("override_camerares",))
    # karma also carries res_overridex/y — apply the clamped values there too when present.
    if res:
        _try_set(n, "res_overridex", res[0])
        _try_set(n, "res_overridey", res[1])
    samp = _set_samples(n, params, ("samplesperpixel", "pathtracedsamples"))
    frames = _set_frames(n, params)
    return {"node": n.path(), "output": out_path, "rendered": False,
            "sources": src, "resolution": res, "samples": samp, "frames": frames,
            "code_hooks_blanked": blanked,
            "note": "Karma Driver ROP built WIRE-ONLY in /out; fire the render yourself"}


# ── 3. usdrender (USD/Husk render ROP, Driver context) ───────────────────────────────────────────
@endpoint("render_usd")
def render_usd(params):
    """USD/Husk render ROP in Driver context (usdrender, out/) — WIRE-ONLY: builds + wires the Husk
    render in /out; YOU fire it. Render source is scene-node PATHS: `loppath` (the LOP/stage to
    render), `rendersettings` (RenderSettings prim path), `camera` -> override_camera, `renderer`
    (hydra delegate id string). `output` -> outputimage (confined); optional `usd_output` -> lopoutput
    (confined). Cost clamped: frames 1-1000. SECURITY: never executed; ALL code hooks blanked incl.
    husk_prerender/husk_postrender/husk_pre/postframe, rendercommand, runcommand; render buttons never
    pressed; USD/side-file publish toggles left at their (off) defaults."""
    n = _out_node("usdrender", params.get("name"))
    blanked = _blank_code(n, _CODE_USD)
    src = _srcpaths(n, params, {"loppath": "loppath", "rendersettings": "rendersettings",
                                "camera": "override_camera", "renderer": "renderer"})
    out_path = _confine_out(n, "outputimage", params.get("output"))
    usd_out = _confine_out(n, "lopoutput", params.get("usd_output"))
    frames = _set_frames(n, params)
    return {"node": n.path(), "output": out_path, "usd_output": usd_out, "rendered": False,
            "sources": src, "frames": frames, "code_hooks_blanked": blanked,
            "note": "USD/Husk Driver ROP built WIRE-ONLY in /out; fire the render yourself"}


# ── 4. comp (COP-network composite write ROP) ────────────────────────────────────────────────────
@endpoint("render_comp")
def render_comp(params):
    """Composite/COP-network image write ROP (comp, out/) — WIRE-ONLY: builds + wires the composite
    write in /out; YOU fire it. Source is a scene-node PATH: `coppath` (the COP2/COP node whose image
    to write). `output` -> copoutput (confined). Cost clamped: width/height 16-8192 (res1/res2),
    frames 1-1000. SECURITY: never executed; all code hooks (pre/post render+frame) blanked; render
    buttons never pressed."""
    n = _out_node("comp", params.get("name"))
    blanked = _blank_code(n, _CODE_STD)
    src = _srcpaths(n, params, {"coppath": "coppath"})
    out_path = _confine_out(n, "copoutput", params.get("output"))
    res = _set_res(n, params, ("res1", "res2"))
    if res:
        _try_set(n, "resmenu", "specific")   # force the explicit resolution override (tolerant)
    frames = _set_frames(n, params)
    return {"node": n.path(), "output": out_path, "rendered": False,
            "sources": src, "resolution": res, "frames": frames,
            "code_hooks_blanked": blanked,
            "note": "Composite write ROP built WIRE-ONLY in /out; fire the write yourself"}


# ── 5. image (COP image render ROP) ──────────────────────────────────────────────────────────────
@endpoint("render_image")
def render_image(params):
    """COP image render ROP (image, out/) — WIRE-ONLY: builds + wires the COP image write in /out; YOU
    fire it. Source is a scene-node PATH: `coppath` (the COP node whose image to write). `output` ->
    copoutput (confined). Cost clamped: width/height 16-8192 (res1/res2, setres enabled), frames
    1-1000. SECURITY: never executed; all code hooks (pre/post render+frame) blanked; render buttons
    never pressed."""
    n = _out_node("image", params.get("name"))
    blanked = _blank_code(n, _CODE_STD)
    src = _srcpaths(n, params, {"coppath": "coppath"})
    out_path = _confine_out(n, "copoutput", params.get("output"))
    res = _set_res(n, params, ("res1", "res2"), toggles=("setres",))
    frames = _set_frames(n, params)
    return {"node": n.path(), "output": out_path, "rendered": False,
            "sources": src, "resolution": res, "frames": frames,
            "code_hooks_blanked": blanked,
            "note": "COP image ROP built WIRE-ONLY in /out; fire the write yourself"}


# ── 6. ifdarchive (Mantra IFD scene-archive export) ──────────────────────────────────────────────
@endpoint("export_ifd_archive")
def export_ifd_archive(params):
    """Mantra IFD scene-archive export ROP (ifdarchive, out/) — WIRE-ONLY: builds + wires the archive
    export in /out; YOU fire it. Source is a scene-node PATH: `objpath` -> arch_objpath1 (the object to
    archive). `geo_output` -> arch_geofile1 and `mat_output` -> arch_matfile1 (both confined). Cost
    clamped: frames 1-1000. SECURITY: never executed; all code hooks (pre/post render+frame) blanked;
    render buttons never pressed."""
    n = _out_node("ifdarchive", params.get("name"))
    blanked = _blank_code(n, _CODE_STD)
    src = _srcpaths(n, params, {"objpath": "arch_objpath1"})
    geo_out = _confine_out(n, "arch_geofile1", params.get("geo_output"))
    mat_out = _confine_out(n, "arch_matfile1", params.get("mat_output"))
    frames = _set_frames(n, params)
    return {"node": n.path(), "output": geo_out, "mat_output": mat_out, "rendered": False,
            "sources": src, "frames": frames, "code_hooks_blanked": blanked,
            "note": "IFD archive export ROP built WIRE-ONLY in /out; fire the export yourself"}

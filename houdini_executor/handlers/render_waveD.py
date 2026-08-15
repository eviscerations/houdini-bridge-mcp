"""Render/ROP — out/Driver data-cache exporters + ML-example / ML-CV-synthetics ROPs, wrapped
WIRE-ONLY for houdini-bridge-mcp. Node graphs are built + wired + configured; the render/export is
NEVER fired by the MCP — the human presses execute. Param names verified against live H21.0.671 and re-asserted headless.

Nodes in this lane (11):
  out/Driver : channel (CHOP export), mdd, dsmmerge, brickmap, bake_animation, geometryraw,
               ml_exampleraw
  sop        : ml_exampleoutput, rop_ml_exampleraw
  lop/Solaris: labs::ml_cv_synthetics_karma_rop::1.0, labs::ml_cv_synthetics_karma_rop::1.1

SECURITY POSTURE (this lane's whole point — held for every handler here):
  * NEVER execute. No .render()/.execute()/executeBackground/pressButton on any ROP; no render-button
    parm (execute/executebackground/renderdialog/renderpreview) is ever set. The ml_cv_synthetics
    nodes are Karma renderers for synthetic-data generation — their render buttons + any husk/code
    hooks are left untouched (never pressed) and defensively blanked.
  * BLANK every code_surface parm to "" (per-frame/per-render script hooks: pre/postframe,
    pre/postrender + the l*/t* variants). They only fire on execute (which we never call), blanked
    defense-in-depth so even a human-fired render carries no injected script.
  * CONFINE every file-out parm through confined_path() and ONLY when the caller supplies it (WIRE-ONLY
    — absent → leave the HDA default for the human to edit before firing).
  * CLAMP frame-range / sample cost levers (frames 1..1000, samples 1..256, resolution 16..8192).
  * Scene-node PATH params (choppath/soppath/source/camera/primpath/rendersettings) are DATA (they name
    in-scene nodes), set verbatim as plain strings — never confined as files, never cooked here.
"""

import hou
from houdini_executor.server import (endpoint, confined_path, clamp, child_after,
                                     out_context, stage_context)
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────


def _out_node(ntype, name=None):
    """Create a Driver/ROP node in /out (created on demand). WIRE-ONLY: never executed."""
    out = out_context()
    return out.createNode(ntype, name) if name else out.createNode(ntype)


# The full ROP code-surface parm set (superset; _blank_code no-ops on any a node lacks).
_CODE_HOOKS = (
    "prerender", "postrender", "preframe", "postframe",
    "lprerender", "lpostrender", "lpreframe", "lpostframe",
    "tprerender", "tpostrender", "tpreframe", "tpostframe",
    "husk_prerender", "husk_postrender", "husk_preframe", "husk_postframe",
    "husk_tprerender", "husk_tpostrender", "husk_tpreframe", "husk_tpostframe",
    "rendercommand", "runcommand", "vm_tilecallback",
)


def _blank_code(node, names=_CODE_HOOKS):
    """Neutralize every code-execution hook (defense-in-depth). TYPE-AWARE: script/command STRING
    parms (prerender/postframe/rendercommand/husk_*/…) are emptied to ""; their companion ENABLE
    TOGGLES and language menus (t*/l*) are forced to 0 (disabled) — never "" (a bare "" coerces a
    toggle to 1, which would ENABLE the hook). Returns the parms it neutralized."""
    blanked = []
    for nm in names:
        p = node.parm(nm)
        if p is None:
            continue
        try:
            is_string = p.parmTemplate().type() == hou.parmTemplateType.String
        except Exception:
            is_string = False
        try:
            p.set("" if is_string else 0)
            blanked.append(nm)
        except Exception:
            pass
    return blanked


def _clamp_frames(node, params):
    """Clamp the standard f1/f2 (start/end frame) cost levers when supplied."""
    if "f1" in params:
        _try_set(node, "f1", clamp(float(params["f1"]), 1.0, 1000.0))
    if "f2" in params:
        _try_set(node, "f2", clamp(float(params["f2"]), 1.0, 1000.0))
    if "f3" in params:
        _try_set(node, "f3", clamp(float(params["f3"]), 1.0, 1000.0))


# ══ out/Driver data-cache exporters ══════════════════════════════════════════════════════════════

# ── 1. channel (Driver) — WIRE-ONLY CHOP channel/motion export ───────────────────────────────────
@endpoint("export_channel")
def export_channel(params):
    """Channel ROP (out/Driver) — WIRE-ONLY: builds + wires a CHOP channel/motion exporter; you fire
    it. References a CHOP by path (`choppath`) and writes its channels to `output` (a .chan/.bchan/.clip
    file). Built in /out; `execute` is NEVER pressed. SECURITY: `choppath` is a scene node PATH (data,
    not a file), set verbatim; `output` (chopoutput) is confined to the working dir; all pre/post
    render+frame SCRIPT hooks are blanked; frame range is clamped. Returns rendered=False."""
    n = _out_node("channel", params.get("name"))
    blanked = _blank_code(n)
    if params.get("choppath"):
        _try_set(n, "choppath", str(params["choppath"]))
    _clamp_frames(n, params)
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "chopoutput", out_path)
    return {"node": n.path(), "output": out_path, "rendered": False, "code_hooks_blanked": blanked,
            "note": "channel ROP built WIRE-ONLY in /out; fire the export yourself"}


# ── 2. mdd (Driver) — WIRE-ONLY MDD point-cache export ───────────────────────────────────────────
@endpoint("export_mdd")
def export_mdd(params):
    """MDD ROP (out/Driver) — WIRE-ONLY: builds + wires an MDD point-cache exporter; you fire it.
    References a SOP by path (`soppath`) and writes its per-point animation to `output` (a .mdd file).
    Built in /out; `execute` is NEVER pressed. SECURITY: `soppath` is a scene node PATH (data), set
    verbatim; `output` (file) is confined to the working dir; all render+frame SCRIPT hooks are
    blanked; frame range + rest frame are clamped. Returns rendered=False."""
    n = _out_node("mdd", params.get("name"))
    blanked = _blank_code(n)
    if params.get("soppath"):
        _try_set(n, "soppath", str(params["soppath"]))
    _clamp_frames(n, params)
    if "restframe" in params:
        _try_set(n, "restframe", clamp(float(params["restframe"]), 1.0, 1000.0))
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "file", out_path)
    return {"node": n.path(), "output": out_path, "rendered": False, "code_hooks_blanked": blanked,
            "note": "MDD ROP built WIRE-ONLY in /out; fire the export yourself"}


# ── 3. dsmmerge (Driver) — WIRE-ONLY deep-shadow-map merge ───────────────────────────────────────
@endpoint("render_dsm_merge")
def render_dsm_merge(params):
    """Deep-Shadow-Map Merge ROP (out/Driver) — WIRE-ONLY: builds + wires a DSM merge; you fire it.
    Merges deep shadow / deep camera maps into a single `output` (dsm_output). Built in /out; `execute`
    is NEVER pressed. SECURITY: `output` and any supplied input DSM paths (`dsm_source1`/`dsm_source2`)
    are confined to the working dir; all render+frame SCRIPT hooks are blanked; frame range clamped.
    Returns rendered=False."""
    n = _out_node("dsmmerge", params.get("name"))
    blanked = _blank_code(n)
    _clamp_frames(n, params)
    if "dsm_count" in params:
        _try_set(n, "dsm_count", int(clamp(int(params["dsm_count"]), 0, 64)))
    src1 = src2 = None
    if params.get("dsm_source1"):
        src1 = confined_path(params["dsm_source1"])
        _try_set(n, "dsm_source1", src1)
    if params.get("dsm_source2"):
        src2 = confined_path(params["dsm_source2"])
        _try_set(n, "dsm_source2", src2)
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "dsm_output", out_path)
    return {"node": n.path(), "output": out_path, "sources": [src1, src2], "rendered": False,
            "code_hooks_blanked": blanked,
            "note": "DSM merge ROP built WIRE-ONLY in /out; fire the merge yourself"}


# ── 4. brickmap (Driver) — WIRE-ONLY point-cloud → brick-map generator ───────────────────────────
@endpoint("export_brickmap")
def export_brickmap(params):
    """Brick Map ROP (out/Driver) — WIRE-ONLY: builds + wires a point-cloud/i3d → brick-map generator;
    you fire it. References a SOP by path (`sop`) and/or input point-cloud/geo/i3d files, writing the
    brick map to `output`. Built in /out; `execute` is NEVER pressed. SECURITY: `sop` is a scene node
    PATH (data); `output` plus any supplied input file refs (`geofile`/`ptcfile`/`i3dfile`) are confined
    to the working dir; frame range is clamped (no code surface on this node). Returns rendered=False."""
    n = _out_node("brickmap", params.get("name"))
    if params.get("sop"):
        _try_set(n, "sop", str(params["sop"]))
    _clamp_frames(n, params)
    files = {}
    for pin in ("geofile", "ptcfile", "i3dfile", "output"):
        if params.get(pin):
            cp = confined_path(params[pin])
            _try_set(n, pin, cp)
            files[pin] = cp
    return {"node": n.path(), "output": files.get("output"), "files": files, "rendered": False,
            "note": "brick-map ROP built WIRE-ONLY in /out; fire the generation yourself"}


# ── 5. bake_animation (Driver) — WIRE-ONLY animation bake (data-only, no file) ───────────────────
@endpoint("bake_animation_rop")
def bake_animation_rop(params):
    """Bake Animation ROP (out/Driver) — WIRE-ONLY: builds + wires an object-animation bake; you fire
    it. Bakes constraint/expression-driven motion of the objects named by `source` down to plain
    keyframes (or CHOP channels). Built in /out; `execute` is NEVER pressed. SECURITY: `source` and
    `write_to_chop_channel` are scene-graph PATH tokens (data), set verbatim; the copy_* toggles pick
    what is baked; no file or code surface on this node. Returns rendered=False."""
    n = _out_node("bake_animation", params.get("name"))
    if params.get("source"):
        _try_set(n, "source", str(params["source"]))
    if params.get("write_to_chop_channel"):
        _try_set(n, "write_to_chop_channel", str(params["write_to_chop_channel"]))
    for tog in ("copy_transforms", "copy_parameters", "copy_hierarchy", "copy_constraints"):
        if tog in params:
            _try_set(n, tog, bool(params[tog]))
    return {"node": n.path(), "rendered": False,
            "note": "bake-animation ROP built WIRE-ONLY in /out; fire the bake yourself"}


# ── 6. geometryraw (Driver) — WIRE-ONLY raw geometry stream dump ─────────────────────────────────
@endpoint("export_geometry_raw")
def export_geometry_raw(params):
    """Geometry (raw) ROP (out/Driver) — WIRE-ONLY: builds + wires a raw geometry stream dump; you fire
    it. References a SOP by path (`soppath`) and writes its raw geometry to `output` (sopoutput). Built
    in /out; `execute` is NEVER pressed. SECURITY: `soppath` is a scene node PATH (data); `output` is
    confined to the working dir; all render+frame SCRIPT hooks are blanked; frame range is clamped.
    Returns rendered=False."""
    n = _out_node("geometryraw", params.get("name"))
    blanked = _blank_code(n)
    if params.get("soppath"):
        _try_set(n, "soppath", str(params["soppath"]))
    _clamp_frames(n, params)
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "sopoutput", out_path)
    return {"node": n.path(), "output": out_path, "rendered": False, "code_hooks_blanked": blanked,
            "note": "raw-geometry ROP built WIRE-ONLY in /out; fire the dump yourself"}


# ── 7. ml_exampleraw (Driver) — WIRE-ONLY ML training-example raw export ─────────────────────────
@endpoint("export_ml_example_raw")
def export_ml_example_raw(params):
    """ML Example Raw ROP (out/Driver) — WIRE-ONLY: builds + wires a raw ML-training-example exporter;
    you fire it. References a SOP by path (`soppath`) and dumps its per-example raw feature data to
    `output` (sopoutput). Built in /out; `execute` is NEVER pressed. SECURITY: `soppath` is a scene
    node PATH (data); the attribute-name inputs (`inputpointattribute1`/`inputvolumename1`) are plain
    tokens; `output` is confined to the working dir; all render+frame SCRIPT hooks are blanked; frame
    range is clamped. Returns rendered=False."""
    n = _out_node("ml_exampleraw", params.get("name"))
    blanked = _blank_code(n)
    if params.get("soppath"):
        _try_set(n, "soppath", str(params["soppath"]))
    if "inputpointattribute1" in params:
        _try_set(n, "inputpointattribute1", str(params["inputpointattribute1"]))
    if "inputvolumename1" in params:
        _try_set(n, "inputvolumename1", str(params["inputvolumename1"]))
    _clamp_frames(n, params)
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "sopoutput", out_path)
    return {"node": n.path(), "output": out_path, "rendered": False, "code_hooks_blanked": blanked,
            "note": "ML-example-raw ROP built WIRE-ONLY in /out; fire the export yourself"}


# ══ sop-context ML exporters (wired to a SOP input) ══════════════════════════════════════════════

# ── 8. ml_exampleoutput (sop) — WIRE-ONLY ML example dataset output ──────────────────────────────
@endpoint("export_ml_example_output")
def export_ml_example_output(params):
    """ML Example Output ROP (sop) — WIRE-ONLY: builds + wires an ML example-dataset writer after a SOP
    (`input`, input 0); you fire it. Writes the incoming example stream to `output` (sopoutput).
    `execute` is NEVER pressed. SECURITY: `output` is confined to the working dir; attribute-name inputs
    are plain tokens; the pre/post render+frame SCRIPT hooks are blanked. Returns rendered=False."""
    n = child_after(params["input"], "ml_exampleoutput", params.get("name"))
    blanked = _blank_code(n)
    if "inputpointattribute1" in params:
        _try_set(n, "inputpointattribute1", str(params["inputpointattribute1"]))
    if "inputvolumename1" in params:
        _try_set(n, "inputvolumename1", str(params["inputvolumename1"]))
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "sopoutput", out_path)
    return {"node": n.path(), "output": out_path, "rendered": False, "code_hooks_blanked": blanked,
            "note": "ml_exampleoutput wired WIRE-ONLY in SOP; fire the export yourself"}


# ── 9. rop_ml_exampleraw (sop) — WIRE-ONLY ML raw-example export (SOP form) ───────────────────────
@endpoint("export_ml_example_raw_sop")
def export_ml_example_raw_sop(params):
    """ROP ML Example Raw (sop) — WIRE-ONLY: builds + wires the SOP-level raw ML-example exporter after
    a SOP (`input`, input 0); you fire it. Dumps the incoming raw feature data to `output` (sopoutput).
    `execute` is NEVER pressed. SECURITY: `output` is confined to the working dir; the attribute-name
    inputs are plain tokens; `soppath` (if given) is a scene node PATH (data); all render+frame SCRIPT
    hooks are blanked; frame range is clamped. Returns rendered=False."""
    n = child_after(params["input"], "rop_ml_exampleraw", params.get("name"))
    blanked = _blank_code(n)
    if params.get("soppath"):
        _try_set(n, "soppath", str(params["soppath"]))
    if "inputpointattribute1" in params:
        _try_set(n, "inputpointattribute1", str(params["inputpointattribute1"]))
    if "inputvolumename1" in params:
        _try_set(n, "inputvolumename1", str(params["inputvolumename1"]))
    _clamp_frames(n, params)
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "sopoutput", out_path)
    return {"node": n.path(), "output": out_path, "rendered": False, "code_hooks_blanked": blanked,
            "note": "rop_ml_exampleraw wired WIRE-ONLY in SOP; fire the export yourself"}


# ══ lop/Solaris ML-CV synthetic-data Karma renderers ═════════════════════════════════════════════

def _ml_cv_synthetics(ntype, params):
    """Shared builder for the Labs ML-CV synthetics Karma ROPs (v1.0/v1.1). Built WIRE-ONLY in /stage;
    the Karma render is NEVER fired. Render buttons untouched; output image paths confined; render
    cost (resolution/samples/frames) clamped; any code/husk hook defensively blanked. `camera`,
    `rendersettings`/`primpath`/`primpattern` are scene-graph PATH data (set verbatim)."""
    stage = stage_context()
    n = stage.createNode(ntype, params.get("name")) if params.get("name") else stage.createNode(ntype)
    n.moveToGoodPosition()
    # WIRE-ONLY: optionally wire a LOP input by path (same stage), guarded.
    wired = False
    if params.get("input"):
        try:
            src = hou.node(str(params["input"]))
            if src is not None:
                n.setInput(0, src)
                wired = True
        except Exception:
            wired = False
    blanked = _blank_code(n)  # defense-in-depth (node has no declared code surface)
    # Scene-graph PATH data — verbatim, never confined as files, never cooked here.
    if params.get("camera"):
        _try_set(n, "camera", str(params["camera"]))
    if params.get("primpath"):
        _try_set(n, "primpath", str(params["primpath"]))
    if params.get("primpattern"):
        _try_set(n, "primpattern", str(params["primpattern"]))
    # Cost clamps.
    _clamp_frames(n, params)
    if "resolutionx" in params:
        _try_set(n, "resolutionx", int(clamp(int(params["resolutionx"]), 16, 8192)))
    if "resolutiony" in params:
        _try_set(n, "resolutiony", int(clamp(int(params["resolutiony"]), 16, 8192)))
    if "samplesperpixel" in params:
        _try_set(n, "samplesperpixel", int(clamp(int(params["samplesperpixel"]), 1, 256)))
    if "pathtracedsamples" in params:
        _try_set(n, "pathtracedsamples", int(clamp(int(params["pathtracedsamples"]), 1, 256)))
    # Confine the true image-output paths (the *outputcs parms are colorspace tokens, not files).
    files = {}
    for pin in ("outputimage", "picture_rgb", "picture_id", "dcmfilename"):
        if params.get(pin):
            cp = confined_path(params[pin])
            _try_set(n, pin, cp)
            files[pin] = cp
    return {"node": n.path(), "output": files.get("outputimage"), "output_images": files,
            "wired": wired, "rendered": False, "code_hooks_blanked": blanked,
            "note": "ML-CV synthetics Karma ROP built WIRE-ONLY in /stage; fire the render yourself"}


@endpoint("render_ml_cv_synthetics")
def render_ml_cv_synthetics(params):
    """Labs ML-CV Synthetics Karma ROP v1.0 (lop/Solaris) — WIRE-ONLY: builds + wires a Karma renderer
    that generates synthetic ML-CV training imagery (beauty + a large AOV/segmentation set); you fire
    the render. Built in /stage; execute/husk are NEVER pressed. SECURITY: `camera`/`primpath`/
    `primpattern` are scene-graph PATH data (verbatim); the image outputs (`outputimage`/`picture_rgb`/
    `picture_id`/`dcmfilename`) are confined to the working dir; resolution/samples/frame range are
    clamped; render buttons untouched + code/husk hooks blanked. Returns rendered=False."""
    return _ml_cv_synthetics("labs::ml_cv_synthetics_karma_rop::1.0", params)


@endpoint("render_ml_cv_synthetics_v11")
def render_ml_cv_synthetics_v11(params):
    """Labs ML-CV Synthetics Karma ROP v1.1 (lop/Solaris) — WIRE-ONLY: same as render_ml_cv_synthetics
    but the ::1.1 asset (2 inputs; `importsecondaryinputvars` folds a second input's render vars). You
    fire the render. Built in /stage; execute/husk NEVER pressed. SECURITY: scene-graph PATH data set
    verbatim; image outputs confined; resolution/samples/frame range clamped; render buttons untouched
    + code/husk hooks blanked. Returns rendered=False."""
    return _ml_cv_synthetics("labs::ml_cv_synthetics_karma_rop::1.1", params)

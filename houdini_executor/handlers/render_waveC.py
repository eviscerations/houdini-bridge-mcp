"""Render/ROP — SOP-context geometry-export ROPs (WIRE-ONLY). Params verified against live
H21.0.671 (node category,
input/output counts, exact parm names/types, code-hook read-back == "", file-out confinement).

WIRE-ONLY DATA POSTURE (this lane's whole point):
  * NEVER execute. No `.render()`/`.execute()`/`executeBackground`/`pressButton()`; the render/export
    button (`execute`/`executebackground`/`renderdialog`/`renderpreview`) is never touched. The human
    fires the write.
  * Every per-frame CODE hook (prerender/postrender/preframe/postframe + l*/t* variants) is BLANKED to
    "" defense-in-depth so even a human-fired export carries no injected script.
  * Every file-out parm (`sopoutput`/`file`/`output`/`file_out`) is realpath-confined via
    confined_path() and only set when the caller supplies it (WIRE-ONLY: absent -> keep the HDA default
    for the human to edit before firing).
  * Frame-range + resolution cost levers are hard-clamped (span <= 1000 frames; res 16..8192).
  * Scene-node references (`doppath`) are DATA (node paths, not files) — set verbatim, never resolved
    or cooked here.

Not wrapped (already covered by a tool that produces the same output):
  rop_geometry  -> export_geometry / export_cache        (geometry ROP)
  rop_alembic   -> export_alembic                          (alembic ROP)
  rop_fbx       -> export_fbx                              (filmboxfbx ROP)
  rop_gltf      -> export_gltf                             (gltf ROP)
  usdexport     -> export_usd / export_package             (usd ROP)
  usd_rop       -> export_usd / export_package             (LOP-context USD write)
Only the 3 distinct raw-ROP forms with NO live-tool equivalent are wrapped here:
  rop_geometryraw, dopio, heightfield_output.
"""

import hou
from houdini_executor.server import (endpoint, confined_path, clamp, child_after)
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────
_CODE_HOOKS = (
    "prerender", "postrender", "preframe", "postframe",
    "lprerender", "lpostrender", "lpreframe", "lpostframe",
    "tprerender", "tpostrender", "tpreframe", "tpostframe",
)




def _menu_set(node, parm, token, tokens):
    """Set an ordered/string menu by TOKEN (no-op if unknown / parm absent)."""
    if token not in tokens:
        return False
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(str(token))
        return True
    except Exception:
        return False


def _blank_code_hooks(node):
    """SECURITY: neutralize every per-frame code-execution hook (defense-in-depth). The script-STRING
    parms (prerender/postrender/preframe/postframe + the l* language menus) are blanked to ""; the t*
    ENABLE toggles (default 1) are set to 0 so the hook can never fire even if a script were present.
    Verified on H21.0.671: base/l* == String, t* == Toggle."""
    for h in _CODE_HOOKS:
        p = node.parm(h)
        if p is None:
            continue
        try:
            p.deleteAllKeyframes()
        except Exception:
            pass
        try:
            is_toggle = p.parmTemplate().type() == hou.parmTemplateType.Toggle
        except Exception:
            is_toggle = False
        try:
            p.set(0 if is_toggle else "")
        except Exception:
            pass


def _set_frames(node, frames):
    """Set a clamped export frame range (trange=1). Span hard-capped at 1000 frames (cost clamp).
    WIRE-ONLY: this only stores the range on the node; nothing is cooked/rendered here."""
    if not frames or len(frames) != 2:
        return None
    _try_set(node, "trange", 1)
    f1 = int(clamp(int(frames[0]), -100000, 100000))
    f2 = int(clamp(int(frames[1]), f1, f1 + 1000))
    for pn, val in (("f1", f1), ("f2", f2)):
        p = node.parm(pn)
        if p is None:
            continue
        try:
            p.deleteAllKeyframes()  # f1/f2 ship $FSTART/$FEND expr keyframes; clear before literal set
        except Exception:
            pass
        try:
            p.set(val)
        except Exception:
            pass
    return [f1, f2]


def _fresh_geo(name):
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name) if name else obj.createNode("geo")


# ══ SOP-context geometry-export ROPs — WIRE-ONLY (built + wired, execute NEVER pressed) ═══════════

# ── 1. rop_geometryraw (chain; in0 SOP) — WIRE-ONLY raw geometry export ───────────────────────────
@endpoint("rop_geometryraw")
def rop_geometryraw(params):
    """ROP Geometry Output — RAW (`rop_geometryraw`, SOP-context, input 0 = the geometry to export) —
    WIRE-ONLY. The RAW variant writes the geometry stream UN-expanded (no packed-prim unpacking,
    verbatim attributes) to a single file (`sopoutput`, extension picks .bgeo/.bgeo.sc/.geo/etc.) —
    distinct from the `geometry` ROP behind export_geometry/export_cache (which expands). Builds +
    wires the export inside the SOP network; `execute` is NEVER pressed — you fire the write. SECURITY:
    `output` (=`sopoutput`) is realpath-confined to the working dir when supplied; every per-frame code
    hook is blanked to ""; frame range hard-clamped. Returns exported=False.
    Params: input (req, SOP path); output (opt, confined file); frames [f1,f2] (opt, clamped);
    alfprogress (opt bool); name (opt)."""
    n = child_after(params["input"], "rop_geometryraw", params.get("name"))
    _blank_code_hooks(n)                         # SECURITY: no injected per-frame scripts
    if "alfprogress" in params:
        _try_set(n, "alfprogress", bool(params["alfprogress"]))
    applied = _set_frames(n, params.get("frames"))
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "sopoutput", out_path)
        _try_set(n, "mkpath", True)
    return {"node": n.path(), "output": out_path, "frames": applied, "exported": False,
            "note": "rop_geometryraw built WIRE-ONLY in the SOP network; fire the export yourself"}


# ── 2. dopio (source in a geo net; 0 inputs) — WIRE-ONLY DOP field/geometry disk I/O ─────────────
@endpoint("dopio")
def dopio(params):
    """DOP I/O (`dopio`, SOP-context, 0 inputs) — WIRE-ONLY. Caches a DOP network's fields/geometry to
    disk (`file`) so a heavy sim can be written once and streamed back — no live-tool equivalent (the
    existing DOP handlers only IMPORT). It has no SOP input: it references the sim by scene path
    (`doppath`) and writes `file`. Created in the SOP network of `input` when given, else in a fresh
    /obj geo container. Built WIRE-ONLY; `execute` is NEVER pressed — you fire the cache. SECURITY:
    `doppath` is a scene node PATH (data, not a file) set verbatim, never cooked here; `output`
    (=`file`) is realpath-confined; every per-frame code hook is blanked to ""; frame range clamped;
    the `presets` UI-callback menu is never touched. Returns exported=False.
    Params: doppath (opt, DOP network scene path); output (opt, confined file); frames [f1,f2] (opt,
    clamped); compression toggles left at HDA default; input (opt, SOP path to co-locate the node);
    name (opt)."""
    if params.get("input"):
        anchor = hou.node(params["input"])
        if anchor is None:
            raise ValueError(f"no such node: {params['input']}")
        try:
            if isinstance(anchor, hou.ObjNode):
                disp = anchor.displayNode() or anchor.renderNode()
                if disp is not None:
                    anchor = disp
        except Exception:
            pass
        parent = anchor.parent()
        n = parent.createNode("dopio", params.get("name")) if params.get("name") \
            else parent.createNode("dopio")
        n.moveToGoodPosition()
    else:
        geo = _fresh_geo(params.get("name"))
        n = geo.createNode("dopio")
    _blank_code_hooks(n)                         # SECURITY: no injected per-frame scripts
    if params.get("doppath"):
        _try_set(n, "doppath", str(params["doppath"]))   # scene node PATH (data), set verbatim
    if "alfprogress" in params:
        _try_set(n, "alfprogress", bool(params["alfprogress"]))
    applied = _set_frames(n, params.get("frames"))
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "file", out_path)
        _try_set(n, "mkpath", True)
    return {"node": n.path(), "output": out_path, "frames": applied, "exported": False,
            "note": "dopio built WIRE-ONLY; set doppath to the sim and fire the cache yourself"}


# ── 3. heightfield_output (chain; in0 heightfield) — WIRE-ONLY terrain/heightmap export ──────────
@endpoint("heightfield_output")
def heightfield_output(params):
    """Heightfield Output (`heightfield_output`, SOP-context, input 0 = the heightfield/terrain to
    export) — WIRE-ONLY. Writes an incoming HF volume as a heightmap / terrain image (`output`) — the
    terrain-export exit with no live-tool equivalent. `specify_res`+`resolutionx`/`resolutiony`
    override the raster resolution; `tile_output` splits into tiled maps. Builds + wires the export in
    the SOP network; `execute` is NEVER pressed — you fire the write. SECURITY: `output` and `file_out`
    are realpath-confined to the working dir when supplied; resolution + frame range are hard-clamped
    (16..8192 px). This node carries NO per-frame code hooks (verified), so there is no code surface to
    exploit. Returns exported=False.
    Params: input (req, HF SOP path); output (opt, confined file); file_out (opt, confined secondary
    file); specify_res (opt bool); resolutionx/resolutiony (opt int, clamped 16..8192);
    tile_output (opt bool); frames [f1,f2] (opt, clamped); name (opt)."""
    n = child_after(params["input"], "heightfield_output", params.get("name"))
    _blank_code_hooks(n)                         # defensive no-op (node has no code hooks)
    if "specify_res" in params:
        _try_set(n, "specify_res", bool(params["specify_res"]))
    if "resolutionx" in params:
        _try_set(n, "resolutionx", int(clamp(int(params["resolutionx"]), 16, 8192)))
    if "resolutiony" in params:
        _try_set(n, "resolutiony", int(clamp(int(params["resolutiony"]), 16, 8192)))
    if "tile_output" in params:
        _try_set(n, "tile_output", bool(params["tile_output"]))
    applied = _set_frames(n, params.get("frames"))
    out_path = file_out = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "output", out_path)
    if params.get("file_out"):
        file_out = confined_path(params["file_out"])
        _try_set(n, "file_out", file_out)
    return {"node": n.path(), "output": out_path, "file_out": file_out, "frames": applied,
            "exported": False,
            "note": "heightfield_output built WIRE-ONLY in the SOP network; fire the export yourself"}

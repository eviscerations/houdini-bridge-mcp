"""SideFX Labs Real-Time Engine tools — data-only handlers. Params verified live against
H21.0.671.

Batch = the Labs menu categories "Labs/Pipeline/Real-Time Engine" + "Labs/Real-Time Engine".
Of the eight deduped base names in those two menus, SEVEN are wrapped at a STRICTLY HIGHER
version by the sibling "Labs/Game Engine" lane (bare endpoint names would collide 1:1), so they
are deferred there. The one base name unique
to this set is `texture_sheets`.

texture_sheets is a Mantra-driven ROP (Driver context) that renders volume/flipbook texture
SHEETS to an image sequence + packed atlas maps. Rendering is a write + a heavy cook, so this is a
WIRE-ONLY file-writer, mirroring deliver.py `bake_texture` / tree.py `maps_baker`:
  * the graph is BUILT + wired + configured but NEVER executed (the human fires the render);
  * every output path the tool sets (`sequencedir`, `mapdir`) is realpath-confined to the working
    dir via confined_path();
  * `assetname` is sanitized so a filename token can never smuggle a path;
  * the code/callback surfaces (`vm_embedvex`, `vm_vexprofile`, `vm_tilecallback`,
    `apply_stylesheets`) are never exposed or set;
  * returns {"rendered": False}.
"""

import hou
from houdini_executor.server import (
    endpoint, confined_path, clamp, resolve_node, out_context,
)
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────


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


def _safe_name_token(v):
    """Sanitize a filename / asset-name token: reject path separators, parent refs and drive letters
    so an asset name can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("asset-name token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


# ── ordered-menu token tuples (native tokens are meaningful strings) ──────────────────────────────
_RENDER_ENGINE = ("micropoly", "raytrace", "pbrmicropoly", "pbrraytrace", "photon")  # vm_renderengine
_COLORSPACE = ("linear", "gamma")                                                    # vm_colorspace


# ── texture_sheets (Driver ROP; in0 opt, out1) — WIRE-ONLY flipbook/atlas renderer ────────────────
@endpoint("texture_sheets")
def texture_sheets(params):
    """Labs Texture Sheets (labs::texture_sheets::2.0) — WIRE-ONLY texture-sheet / flipbook renderer.
    Renders a volume (or the geometry at `input`) across a frame range into an atlas image sequence
    (`sequencedir`) and optional packed channel maps (`mapdir`), laid out `numperline` frames per row.
    Mirrors deliver.py bake_texture / tree.py maps_baker: the ROP is BUILT + configured but the render
    is NEVER executed (rendering is a heavy cook + a write — the human fires it), so it returns
    rendered=False.
    SECURITY: `sequencedir` / `mapdir` are realpath-confined to the working dir; `assetname` is
    sanitized (no path); the code/callback surfaces (vm_embedvex / vm_vexprofile / vm_tilecallback /
    apply_stylesheets) are never exposed; per-sheet resolution and sample counts are hard-clamped."""
    n = out_context().createNode("labs::texture_sheets::2.0", params.get("name"))

    # Reference the geometry/volume to render (a node path, NOT a file). Validate it exists.
    if params.get("input"):
        src = resolve_node(params["input"])
        _try_set(n, "node_to_render", src.path())

    # Sanitized asset-name token (used to build output filenames).
    if "assetname" in params:
        _try_set(n, "assetname", _safe_name_token(params["assetname"]))

    # SECURITY: confine the two output directories the tool sets; never fire the render.
    seq_dir = None
    if params.get("sequencedir"):
        seq_dir = confined_path(params["sequencedir"])
        _try_set(n, "sequencedir", seq_dir)
    map_dir = None
    if params.get("mapdir"):
        map_dir = confined_path(params["mapdir"])
        _try_set(n, "mapdir", map_dir)

    # Atlas / output-shaping controls.
    if "export_normal" in params:
        _try_set(n, "export_normal", bool(params["export_normal"]))
    if "pack_map_toggle" in params:
        _try_set(n, "pack_map_toggle", bool(params["pack_map_toggle"]))
    if "flipgreen" in params:
        _try_set(n, "flipgreen", bool(params["flipgreen"]))
    if "numperline" in params:
        _try_set(n, "numperline", int(clamp(int(params["numperline"]), 1, 64)))
    if "override_res" in params:
        _try_set(n, "override_res", bool(params["override_res"]))
    if "resolutionx" in params:
        _try_set(n, "resolutionx", float(int(clamp(int(params["resolutionx"]), 16, 8192))))
    if "resolutiony" in params:
        _try_set(n, "resolutiony", float(int(clamp(int(params["resolutiony"]), 16, 8192))))

    # Frame range (frames1=start, frames2=end, frames3=inc). WIRE-ONLY, but clamp for sanity so a
    # later human-fired render can't be handed an absurd range.
    if "frame_start" in params:
        _try_set(n, "frames1", float(clamp(float(params["frame_start"]), -1e5, 1e5)))
    if "frame_end" in params:
        _try_set(n, "frames2", float(clamp(float(params["frame_end"]), -1e5, 1e5)))
    if "frame_inc" in params:
        _try_set(n, "frames3", float(clamp(float(params["frame_inc"]), 1e-3, 1e4)))

    # Render-cost levers (hard clamp; still WIRE-ONLY).
    if "samples" in params:
        s = int(clamp(int(params["samples"]), 1, 64))
        _try_set(n, "vm_samplesx", s)
        _try_set(n, "vm_samplesy", s)
    if "render_engine" in params:
        _menu_tok_set(n, "vm_renderengine", str(params["render_engine"]), _RENDER_ENGINE)
    if "colorspace" in params:
        _menu_tok_set(n, "vm_colorspace", str(params["colorspace"]), _COLORSPACE)

    # WIRE-ONLY: do NOT press execute / render — no cook, no write here.
    return {"node": n.path(), "sequence_dir": seq_dir, "map_dir": map_dir, "rendered": False,
            "note": "texture_sheets ROP wired (WIRE-ONLY); start the render yourself"}

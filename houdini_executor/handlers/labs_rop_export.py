"""SideFX Labs — ROP (/out Driver) data exporters (data-only handlers). Params verified against
live H21.0.671 and a headless wire-check per node.

All three nodes are /out Driver file-writers, handled per the brief as WIRE-ONLY exporters: built in
/out, geometry referenced by scene-node PATH (data, not a file), every output path confined via
confined_path(), and the `execute`/render button is NEVER pressed (returns exported=False /
baked=False). No node is ever cooked/rendered here.

  * games_baker — a texture baker (Karma/COP map bake): writes basecolor/normal/AO/… maps for a
      low-vs-high mesh pair. WIRE-ONLY: base_path (+ tempdirectory) confined, bake fired by the human.
  * csv_exporter — geometry attributes -> CSV writer. WIRE-ONLY: csv_path confined.
  * json_exporter — geometry attributes -> JSON writer. WIRE-ONLY: json_path confined.

SECURITY (data-only boundary):
  * Every file surface set is realpath-confined via confined_path(): games_baker.base_path /
    tempdirectory, csv_exporter.csv_path, json_exporter.json_path.
  * Node references (overridenode, target_mesh_1/source_mesh_1, export_node) are scene node PATHS
    (data, not files) — set as plain strings; the referenced node is never resolved/cooked here.
  * No bake/export is ever fired (the `execute`/`renderdialog` buttons are never pressed).
  * Name/suffix tokens (map suffixes, CSV column suffixes) are sanitized so a token can never smuggle
    a filesystem path. Code/callback surfaces are never touched.

SKIPPED: marmoset_export (launches the
external Marmoset Toolbag app — installdir/librarypath/openmarmoset), 3d_facebook_image (a Mantra
RENDER ROP formatted for the Facebook-3D network target, not a data exporter), zibravdb_compress
(requires the proprietary ZibraVDB / Zibra Effects plugin + license — carries an openManagement
plugin-install button and pre/post-render code parms).
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, out_context
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────
def _out_node(ntype, name=None):
    """Create a Driver/ROP node in /out (created on demand). WIRE-ONLY: never executed."""
    out = out_context()
    return out.createNode(ntype, name) if name else out.createNode(ntype)




def _menu_set(node, parm, token, tokens):
    """Set an ordered/string menu by TOKEN. Verified on H21.0.671: p.set(str(token)) resolves by
    token for Menu (index-stored), Int-menu and String-menu parms alike. No-op if the token isn't a
    known menu item."""
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


def _safe_token(v):
    """Sanitize a name/suffix token (map suffix / CSV column suffix): reject path separators, parent
    refs and drive letters so a token can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("name token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


# ── ordered-menu token tuples (native tokens; set via _menu_set by token string) ─────────────────
_BAKER_UVRES = ("256 256", "512 512", "1024 1024", "2048 2048", "4096 4096")  # games_baker uvresmenu
_BAKER_UDIM = ("none", "borderfill", "backgroundfill", "diffusefill")          # udimpostprocess
_TRANGE = ("off", "normal", "on")                                              # trange (frame range)


# ── 1. games_baker (Driver /out) — WIRE-ONLY texture-map bake ────────────────────────────────────
@endpoint("games_baker")
def games_baker(params):
    """SideFX Labs Games Baker (labs::games_baker::2.0) — a /out Driver that bakes texture maps
    (basecolor / normal / AO / roughness / metallic / curvature / thickness / position / …) from a
    high-res `source` mesh onto a low-res `target` mesh, via Houdini's native COP/Karma bake. Built
    WIRE-ONLY in /out — `execute` is NEVER pressed. `overridenode` / `target_mesh_1` / `source_mesh_1`
    reference the meshes by scene-node PATH; `uvresmenu` sets the map resolution; the `bake_*` toggles
    pick which channels to bake; `baking_samples`/`ray_bias`/`ray_distance`/`border_padding` tune the
    trace. SECURITY: `base_path` (map output dir) + `tempdirectory` are confined to the working dir;
    node refs are plain data strings; map-suffix tokens are sanitized; the bake is never auto-fired.
    Returns baked=false."""
    n = _out_node("labs::games_baker::2.0", params.get("name"))
    # node references (scene paths, data-only)
    if params.get("overridenode"):
        _try_set(n, "overridenode", str(params["overridenode"]))
    if params.get("target_mesh_1"):
        _try_set(n, "target_mesh_1", str(params["target_mesh_1"]))
    if params.get("source_mesh_1"):
        _try_set(n, "source_mesh_1", str(params["source_mesh_1"]))
    # resolution / naming menus
    if "uvresmenu" in params:
        _menu_set(n, "uvresmenu", str(params["uvresmenu"]), _BAKER_UVRES)
    if "udimpostprocess" in params:
        _menu_set(n, "udimpostprocess", str(params["udimpostprocess"]), _BAKER_UDIM)
    if "trange" in params:
        _menu_set(n, "trange", str(params["trange"]), _TRANGE)
    if "vm_uvunwrapres" in params:
        _try_set(n, "vm_uvunwrapres", int(clamp(int(params["vm_uvunwrapres"]), 16, 16384)))
    # trace cost levers (clamped)
    if "baking_samples" in params:
        _try_set(n, "baking_samples", int(clamp(int(params["baking_samples"]), 1, 4096)))
    if "border_padding" in params:
        _try_set(n, "border_padding", int(clamp(int(params["border_padding"]), 0, 512)))
    if "ray_bias" in params:
        _try_set(n, "ray_bias", clamp(float(params["ray_bias"]), -1e4, 1e4))
    if "ray_distance" in params:
        _try_set(n, "ray_distance", clamp(float(params["ray_distance"]), -1e4, 1e4))
    # normal/tangent handling
    if "vm_bake_usemikkt" in params:
        _try_set(n, "vm_bake_usemikkt", bool(params["vm_bake_usemikkt"]))
    if "vm_bake_tangentnormalflipy" in params:
        _try_set(n, "vm_bake_tangentnormalflipy", bool(params["vm_bake_tangentnormalflipy"]))
    if "vm_bake_skipcf" in params:
        _try_set(n, "vm_bake_skipcf", bool(params["vm_bake_skipcf"]))
    if "bBasecolorLinearSpace" in params:
        _try_set(n, "bBasecolorLinearSpace", bool(params["bBasecolorLinearSpace"]))
    # channel toggles (which maps to bake)
    for tog in ("bake_basecolor", "bake_Nt", "bake_alpha", "bake_specrough", "bake_metallic",
                "bake_N", "bake_Oc", "bake_Cu", "bake_Th", "bake_P", "bake_Ds"):
        if tog in params:
            _try_set(n, tog, bool(params[tog]))
    # map-name suffixes (sanitized tokens)
    for sn in ("basecolor_suffix", "Nt_suffix", "alpha_suffix", "specrough_suffix",
               "metallic_suffix", "N_suffix", "Oc_suffix", "Cu_suffix", "Th_suffix",
               "P_suffix", "Ds_suffix"):
        if sn in params:
            _try_set(n, sn, _safe_token(params[sn]))
    # confined output surfaces
    base_path = temp_dir = None
    if params.get("base_path"):
        base_path = confined_path(params["base_path"])
        _try_set(n, "base_path", base_path)
    if params.get("tempdirectory"):
        temp_dir = confined_path(params["tempdirectory"])
        _try_set(n, "tempdirectory", temp_dir)
    return {"node": n.path(), "base_path": base_path, "tempdirectory": temp_dir, "baked": False,
            "note": "games_baker built WIRE-ONLY in /out; fire the map bake yourself"}


# ── 2. csv_exporter (Driver /out) — WIRE-ONLY geometry-attributes -> CSV ─────────────────────────
@endpoint("csv_exporter")
def csv_exporter(params):
    """SideFX Labs CSV Exporter (labs::csv_exporter) — a /out Driver that writes a SOP's point/prim
    attributes (referenced by `export_node`) to a plain-text CSV file. Built WIRE-ONLY in /out —
    `execute` is NEVER pressed. `export_header` writes a header row; `use_custom_header`+
    `custom_header_data` supply a custom header line; `separate_components` splits vector attrs into
    per-component columns named with `suff_x/y/z/w`; `bFilteredExport` limits which attributes go out.
    SECURITY: `export_node` is a scene node PATH (data, not a file); `csv_path` is confined to the
    working dir; the column-suffix tokens are sanitized. Returns exported=false."""
    n = _out_node("labs::csv_exporter", params.get("name"))
    if params.get("export_node"):
        _try_set(n, "export_node", str(params["export_node"]))
    if "export_header" in params:
        _try_set(n, "export_header", bool(params["export_header"]))
    if "use_custom_header" in params:
        _try_set(n, "use_custom_header", bool(params["use_custom_header"]))
    if "custom_header_data" in params:
        _try_set(n, "custom_header_data", str(params["custom_header_data"]))
    if "separate_components" in params:
        _try_set(n, "separate_components", bool(params["separate_components"]))
    if "suff_x" in params:
        _try_set(n, "suff_x", _safe_token(params["suff_x"]))
    if "suff_y" in params:
        _try_set(n, "suff_y", _safe_token(params["suff_y"]))
    if "suff_z" in params:
        _try_set(n, "suff_z", _safe_token(params["suff_z"]))
    if "suff_w" in params:
        _try_set(n, "suff_w", _safe_token(params["suff_w"]))
    if "bFilteredExport" in params:
        _try_set(n, "bFilteredExport", bool(params["bFilteredExport"]))
    out_path = None
    if params.get("csv_path"):
        out_path = confined_path(params["csv_path"])
        _try_set(n, "csv_path", out_path)
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "csv_exporter built WIRE-ONLY in /out; fire the export yourself"}


# ── 3. json_exporter (Driver /out) — WIRE-ONLY geometry-attributes -> JSON ───────────────────────
@endpoint("json_exporter")
def json_exporter(params):
    """SideFX Labs JSON Exporter (labs::json_exporter::1.0) — a /out Driver that writes a SOP's
    attributes (referenced by `export_node`) to a JSON file. Built WIRE-ONLY in /out — `execute` is
    NEVER pressed. `generatename` auto-derives the output filename; `filtered` limits which attributes
    are written. SECURITY: `export_node` is a scene node PATH (data, not a file); `json_path` is
    confined to the working dir. Returns exported=false."""
    n = _out_node("labs::json_exporter::1.0", params.get("name"))
    if params.get("export_node"):
        _try_set(n, "export_node", str(params["export_node"]))
    if "generatename" in params:
        _try_set(n, "generatename", bool(params["generatename"]))
    if "filtered" in params:
        _try_set(n, "filtered", bool(params["filtered"]))
    out_path = None
    if params.get("json_path"):
        out_path = confined_path(params["json_path"])
        _try_set(n, "json_path", out_path)
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "json_exporter built WIRE-ONLY in /out; fire the export yourself"}

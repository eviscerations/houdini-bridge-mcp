"""SideFX Labs — Geometry/UV: Create + UV: Refine tools (data-only handlers). Params verified
against a live H21.0.671 headless probe and each node headless-cooked
green. Each Labs UV HDA is wrapped as a typed handler exposing a curated
scalar/enum subset; ramps, folder headers, viewport-state and interactive/stash params stay at HDA
default.

The batch (highest version of each base name):
  UV: Create
    autouv                        chain in0=mesh                -> one-click auto seam+flatten+pack UVs
    uv_unwrap_cylinder::1.0       chain in0=mesh (tube/pipe)     -> cylindrical UV unwrap
    inside_face_uvs::1.0          chain in0=fractured mesh       -> UV only the interior ("inside") faces
    automatic_trim_texture        chain in0=mesh, in1=trim atlas -> fit mesh islands onto a trim sheet
  UV: Refine
    calculate_uv_distortion::1.0  chain in0=UV'd mesh            -> write a per-elem uv_distortion attr
    merge_small_islands::1.0      chain in0=UV'd mesh            -> merge tiny UV islands into neighbours
    remove_uv_distortion::1.0     chain in0=UV'd mesh            -> relax UV peaks/holes (unstretch)
    texel_density::1.0            chain in0=UV'd mesh            -> measure / apply uniform texel density
    uv_remove_overlap::1.0        chain in0=UV'd mesh            -> detect + repair overlapping UV islands
    uv_unitize::1.1               chain in0=UV'd mesh            -> unitize per-prim / per-island UVs to 0-1

SECURITY: data-only. None of these nodes carry a file/exec surface — no code/callback/file parm is
exposed. String parms that name an *attribute/group* (uvattrib, group, insidegroup, ...) are plain
data names, never a path or code. The interactive/stash-driven trim_texture and the internal
trim_texture_subutil / trim_texture_utility HDAs are SKIPPED.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set




def _tok_menu_set(node, parm, token, valid_tokens):
    """Set a Houdini menu parm by its stored TOKEN string (works for named tokens like 'scp' and
    numeric tokens like '0'/'1'). Falls back to the token's index if a token-string set is rejected."""
    p = node.parm(parm)
    if p is None or token not in valid_tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        try:
            p.set(valid_tokens.index(token))
            return True
        except Exception:
            return False


def _mapped_menu(node, parm, value, friendly_to_token, valid_tokens):
    """Map a friendly enum value to the node's real token, then set by token."""
    token = friendly_to_token.get(str(value), str(value))
    return _tok_menu_set(node, parm, token, valid_tokens)


# ── menu token tables (probed 2026, H21.0.671) ───────────────────────────────────────────────────
_FLATTEN_TOK = ("scp", "abf")  # Spectral / Angle-Based

_AUTOUV_METHOD = {"shortest_path": "0", "cluster": "1", "unwrap": "3", "autoseam": "4"}
_AUTOUV_METHOD_TOK = ("0", "1", "3", "4")
_AUTOUV_PLANES = {"4": "planes4", "5": "planes5", "6": "planes6", "8": "planes8"}
_AUTOUV_PLANES_TOK = ("planes4", "planes5", "planes6", "planes8")
_AUTOUV_ROT = {"none": "none", "180": "PI", "90": "PI2", "45": "PI4",
               "22.5": "PI8", "11.25": "PI16", "5.625": "PI32", "custom": "custom"}
_AUTOUV_ROT_TOK = ("none", "PI", "PI2", "PI4", "PI8", "PI16", "PI32", "custom")
_AUTOUV_RES = {"256": "res1", "512": "res2", "1024": "res3", "2048": "res4", "4096": "res5"}
_AUTOUV_RES_TOK = ("res1", "res2", "res3", "res4", "res5")

_RUD_MODE = {"peaks": "0", "holes": "1"}
_RUD_MODE_TOK = ("0", "1")
_RUD_METRIC_TOK = ("max", "min", "mean", "mode", "median",
                   "sum", "sumsquare", "rms", "first", "last")

_TD_UNIT = {"cm": "0", "m": "1"}
_TD_UNIT_TOK = ("0", "1")

_URO_RES_TOK = ("128", "256", "512", "1024", "2048", "4096", "8192", "16384")

_UNI_GRPTYPE_TOK = ("guess", "vertices", "edges", "points", "prims")
_UNI_MODE = {"primitives": "0", "islands": "1"}
_UNI_MODE_TOK = ("0", "1")


# ══ UV: Create ════════════════════════════════════════════════════════════════════════════════════

# ── 1. autouv (chain; in0 mesh) — one-click auto seam + flatten + pack ────────────────────────────
@endpoint("autouv")
def autouv(params):
    """SideFX Labs Auto UV (labs::autouv) — one-click automatic UV: seams the mesh, flattens each
    island, then packs them into a single atlas. `input` (input 0) = the mesh to UV. `method` picks
    the seam strategy (autoseam default). Distinct from the native `uv` unwrap: this is the Labs
    auto-seam + SCP/ABF flatten + island packer in one node. SECURITY: data-only (no file surface);
    the like/dislike telemetry buttons are never exposed."""
    n = child_after(params["input"], "labs::autouv", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "uvattrib" in params:
        _try_set(n, "uvattrib", str(params["uvattrib"]))
    if "method" in params:
        _mapped_menu(n, "method", params["method"], _AUTOUV_METHOD, _AUTOUV_METHOD_TOK)
    if "collapsedist" in params:
        _try_set(n, "collapsedist", clamp(float(params["collapsedist"]), 0.0, 10.0))
    if "numpaths" in params:
        _try_set(n, "numpaths", int(clamp(int(params["numpaths"]), 1, 1000)))
    if "convexmultiplier" in params:
        _try_set(n, "convexmultiplier", clamp(float(params["convexmultiplier"]), 0.0, 100.0))
    if "occlusionmultiplier" in params:
        _try_set(n, "occlusionmultiplier", clamp(float(params["occlusionmultiplier"]), 0.0, 100.0))
    if "numclusters" in params:
        _try_set(n, "numclusters", int(clamp(int(params["numclusters"]), 1, 10000)))
    if "normalblur" in params:
        _try_set(n, "normalblur", int(clamp(int(params["normalblur"]), 0, 100)))
    if "randomseed" in params:
        _try_set(n, "randomseed", int(params["randomseed"]))
    if "bluramount" in params:
        _try_set(n, "bluramount", int(clamp(int(params["bluramount"]), 0, 100)))
    if "numplanes" in params:
        _mapped_menu(n, "numplanes", params["numplanes"], _AUTOUV_PLANES, _AUTOUV_PLANES_TOK)
    if "graintol" in params:
        _try_set(n, "graintol", clamp(float(params["graintol"]), 0.0, 1.0))
    if "mergethreshold" in params:
        _try_set(n, "mergethreshold", clamp(float(params["mergethreshold"]), 0.0, 1.0))
    if "mergesmallislands" in params:
        _try_set(n, "mergesmallislands", bool(params["mergesmallislands"]))
    if "smallislandcutoff" in params:
        _try_set(n, "smallislandcutoff", clamp(float(params["smallislandcutoff"]), 0.0, 1.0))
    if "optimizeuvborder" in params:
        _try_set(n, "optimizeuvborder", bool(params["optimizeuvborder"]))
    if "flatteningmethod" in params:
        _tok_menu_set(n, "flatteningmethod", str(params["flatteningmethod"]), _FLATTEN_TOK)
    if "rotstep" in params:
        _mapped_menu(n, "rotstep", params["rotstep"], _AUTOUV_ROT, _AUTOUV_ROT_TOK)
    if "packingiterations" in params:
        _try_set(n, "packingiterations", int(clamp(int(params["packingiterations"]), 1, 100)))
    if "islandpadding" in params:
        _try_set(n, "islandpadding", int(clamp(int(params["islandpadding"]), 0, 256)))
    if "resolution" in params:
        _mapped_menu(n, "resolution", params["resolution"], _AUTOUV_RES, _AUTOUV_RES_TOK)
    if "udimtarget" in params:
        _try_set(n, "udimtarget", int(clamp(int(params["udimtarget"]), 1001, 1100)))
    if "cusp_angle" in params:
        _try_set(n, "cusp_angle", clamp(float(params["cusp_angle"]), 0.0, 180.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. uv_unwrap_cylinder (chain; in0 mesh) — cylindrical unwrap ──────────────────────────────────
@endpoint("uv_unwrap_cylinder")
def uv_unwrap_cylinder(params):
    """SideFX Labs UV Unwrap Cylinder (labs::uv_unwrap_cylinder::1.0) — cylindrical UV unwrap for
    pipes / tubes / limbs. `input` (input 0) = the tubular mesh. `sectioncutangle` controls where the
    side seam is auto-placed; `autocutoffset` rolls the seam around the barrel. SECURITY: data-only.
    The `uvseams`/`endcaps` interactive edge-group selections are left at default."""
    n = child_after(params["input"], "labs::uv_unwrap_cylinder::1.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "uvattrib" in params:
        _try_set(n, "uvattrib", str(params["uvattrib"]))
    if "autocutoffset" in params:
        _try_set(n, "autocutoffset", clamp(float(params["autocutoffset"]), -10.0, 10.0))
    if "sectioncutangle" in params:
        _try_set(n, "sectioncutangle", clamp(float(params["sectioncutangle"]), 0.0, 180.0))
    if "manualunwrap" in params:
        _try_set(n, "manualunwrap", bool(params["manualunwrap"]))
    if "visuvislands" in params:
        _try_set(n, "visuvislands", bool(params["visuvislands"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. inside_face_uvs (chain; in0 fractured mesh) — UV the interior faces ─────────────────────────
@endpoint("inside_face_uvs")
def inside_face_uvs(params):
    """SideFX Labs Inside Face UVs (labs::inside_face_uvs::1.0) — flatten UVs onto the interior
    ("inside") faces of a fractured mesh so the fracture interior can be textured. `input` (input 0) =
    the fractured mesh; `insidegroup` = the primitive group naming the interior faces (default
    "inside"). `method` = SCP/ABF flatten. SECURITY: data-only."""
    n = child_after(params["input"], "labs::inside_face_uvs::1.0", params.get("name"))
    if "insidegroup" in params:
        _try_set(n, "insidegroup", str(params["insidegroup"]))
    if "destgroup" in params:
        _try_set(n, "destgroup", str(params["destgroup"]))
    if "attrib" in params:
        _try_set(n, "attrib", str(params["attrib"]))
    if "tiling" in params:
        _try_set(n, "tiling", clamp(float(params["tiling"]), 1e-3, 1000.0))
    if "method" in params:
        _tok_menu_set(n, "method", str(params["method"]), _FLATTEN_TOK)
    if "computenormals" in params:
        _try_set(n, "computenormals", bool(params["computenormals"]))
    if "cuspangle" in params:
        _try_set(n, "cuspangle", clamp(float(params["cuspangle"]), 0.0, 180.0))
    if "normalmethod" in params:
        _try_set(n, "normalmethod", int(clamp(int(params["normalmethod"]), 0, 3)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. automatic_trim_texture (chain; in0 mesh, in1 trim atlas) — fit islands to a trim sheet ─────
@endpoint("automatic_trim_texture")
def automatic_trim_texture(params):
    """SideFX Labs Automatic Trim Texture (labs::automatic_trim_texture) — non-interactively fit the
    mesh's UV islands onto a trim-sheet atlas. `input` (input 0) = the mesh; `trim` (input 1) = the
    trim-atlas geometry defining the trim strips (wired to input 1). `generateuv` regenerates UVs
    before fitting; `fittingbalance` trades off area vs. texel match. SECURITY: data-only (no file
    surface) — this is the automatic counterpart of the interactive trim_texture (which is SKIPPED)."""
    n = child_after(params["input"], "labs::automatic_trim_texture", params.get("name"))
    if params.get("trim"):
        bridge_input(n, params["trim"], index=1, name_hint="trim")
    if "generateuv" in params:
        _try_set(n, "generateuv", bool(params["generateuv"]))
    if "straightenuvs" in params:
        _try_set(n, "straightenuvs", bool(params["straightenuvs"]))
    if "minedgeangle" in params:
        _try_set(n, "minedgeangle", clamp(float(params["minedgeangle"]), 0.0, 180.0))
    if "fittingbalance" in params:
        _try_set(n, "fittingbalance", clamp(float(params["fittingbalance"]), 0.0, 1.0))
    if "area" in params:
        _try_set(n, "area", clamp(float(params["area"]), 0.0, 100.0))
    if "limitdensitymismatch" in params:
        _try_set(n, "limitdensitymismatch", bool(params["limitdensitymismatch"]))
    if "texelmismatch" in params:
        _try_set(n, "texelmismatch", clamp(float(params["texelmismatch"]), 0.0, 10.0))
    if "visualizeerror" in params:
        _try_set(n, "visualizeerror", bool(params["visualizeerror"]))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ══ UV: Refine ════════════════════════════════════════════════════════════════════════════════════

# ── 5. calculate_uv_distortion (chain; in0 UV'd mesh) — write a distortion attribute ──────────────
@endpoint("calculate_uv_distortion")
def calculate_uv_distortion(params):
    """SideFX Labs Calculate UV Distortion (labs::calculate_uv_distortion::1.0) — measure how much the
    UV layout stretches/squashes each element vs. 3D and write it to `distortionattribute`
    (default uv_distortion). `input` (input 0) = a mesh that already has UVs. SECURITY: data-only."""
    n = child_after(params["input"], "labs::calculate_uv_distortion::1.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "uvattribute" in params:
        _try_set(n, "uvattribute", str(params["uvattribute"]))
    if "distortionattribute" in params:
        _try_set(n, "distortionattribute", str(params["distortionattribute"]))
    if "visualize" in params:
        _try_set(n, "visualize", bool(params["visualize"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. merge_small_islands (chain; in0 UV'd mesh) — absorb tiny islands ───────────────────────────
@endpoint("merge_small_islands")
def merge_small_islands(params):
    """SideFX Labs Merge Small Islands (labs::merge_small_islands::1.0) — merge UV islands whose
    relative area is below `cutoff` into an adjacent island (and re-flatten), reducing island count
    for cleaner packing. `input` (input 0) = a UV'd mesh; `method` = SCP/ABF re-flatten. SECURITY:
    data-only."""
    n = child_after(params["input"], "labs::merge_small_islands::1.0", params.get("name"))
    if "uvattrib" in params:
        _try_set(n, "uvattrib", str(params["uvattrib"]))
    if "method" in params:
        _tok_menu_set(n, "method", str(params["method"]), _FLATTEN_TOK)
    if "optimize_uv_border" in params:
        _try_set(n, "optimize_uv_border", bool(params["optimize_uv_border"]))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 10000)))
    if "cutoff" in params:
        _try_set(n, "cutoff", clamp(float(params["cutoff"]), 0.0, 1.0))
    if "fFuseDist" in params:
        _try_set(n, "fFuseDist", clamp(float(params["fFuseDist"]), 0.0, 10.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. remove_uv_distortion (chain; in0 UV'd mesh) — relax peaks/holes ────────────────────────────
@endpoint("remove_uv_distortion")
def remove_uv_distortion(params):
    """SideFX Labs Remove UV Distortion (labs::remove_uv_distortion::1.0) — iteratively relax UV
    stretching by pushing distorted vertices ("peaks") in / pulling squashed ones ("holes") out.
    `input` (input 0) = a UV'd mesh. `mode` targets peaks or holes; `iterations` sets relax strength;
    `douvlayout` re-packs afterwards. SECURITY: data-only."""
    n = child_after(params["input"], "labs::remove_uv_distortion::1.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "mode" in params:
        _mapped_menu(n, "mode", params["mode"], _RUD_MODE, _RUD_MODE_TOK)
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 1, 1000)))
    if "usecluster" in params:
        _try_set(n, "usecluster", bool(params["usecluster"]))
    if "solvestretching" in params:
        _try_set(n, "solvestretching", bool(params["solvestretching"]))
    if "maxnegdist" in params:
        _try_set(n, "maxnegdist", clamp(float(params["maxnegdist"]), -10.0, 0.0))
    if "solvesquashing" in params:
        _try_set(n, "solvesquashing", bool(params["solvesquashing"]))
    if "maxposdist" in params:
        _try_set(n, "maxposdist", clamp(float(params["maxposdist"]), 0.0, 10.0))
    if "regressionmetric" in params:
        _tok_menu_set(n, "regressionmetric", str(params["regressionmetric"]), _RUD_METRIC_TOK)
    if "discardregressions" in params:
        _try_set(n, "discardregressions", bool(params["discardregressions"]))
    if "flattenmethod" in params:
        _tok_menu_set(n, "flattenmethod", str(params["flattenmethod"]), _FLATTEN_TOK)
    if "douvlayout" in params:
        _try_set(n, "douvlayout", bool(params["douvlayout"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 8. texel_density (chain; in0 UV'd mesh) — measure / apply uniform texel density ───────────────
@endpoint("texel_density")
def texel_density(params):
    """SideFX Labs Texel Density (labs::texel_density::1.0) — measure and (optionally) equalize the
    texels-per-unit density across a UV'd mesh for a given `texturesize`. `input` (input 0) = a UV'd
    mesh. Set `applytexeldensity` to scale islands to the target `length`/`unit` density; `layoutuvs`
    re-packs afterwards; `addchecker` writes a checker-visualization attribute. Ramp visualization is
    left at HDA default (not a scalar tool surface). SECURITY: data-only."""
    n = child_after(params["input"], "labs::texel_density::1.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "uvattrib" in params:
        _try_set(n, "uvattrib", str(params["uvattrib"]))
    if "texturesize" in params:
        _try_set(n, "texturesize", int(clamp(int(params["texturesize"]), 1, 65536)))
    if "length" in params:
        _try_set(n, "length", int(clamp(int(params["length"]), 1, 100000)))
    if "unit" in params:
        _mapped_menu(n, "unit", params["unit"], _TD_UNIT, _TD_UNIT_TOK)
    if "applytexeldensity" in params:
        _try_set(n, "applytexeldensity", bool(params["applytexeldensity"]))
    if "layoutuvs" in params:
        _try_set(n, "layoutuvs", bool(params["layoutuvs"]))
    if "addchecker" in params:
        _try_set(n, "addchecker", bool(params["addchecker"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 9. uv_remove_overlap (chain; in0 UV'd mesh) — detect + repair overlapping islands ─────────────
@endpoint("uv_remove_overlap")
def uv_remove_overlap(params):
    """SideFX Labs UV Remove Overlap (labs::uv_remove_overlap::1.0) — detect UV islands that overlap
    in the 0-1 tile (rasterized at `resolution`) and, when `repairoverlaps` is on, nudge them apart.
    Optionally groups the offending prims into `groupname`. `input` (input 0) = a UV'd mesh. The
    viewport guide gizmo is left at HDA default. SECURITY: data-only."""
    n = child_after(params["input"], "labs::uv_remove_overlap::1.0", params.get("name"))
    if "uvattrib" in params:
        _try_set(n, "uvattrib", str(params["uvattrib"]))
    if "resolution" in params:
        _tok_menu_set(n, "resmenu", str(params["resolution"]), _URO_RES_TOK)
    if "creategroup" in params:
        _try_set(n, "creategroup", bool(params["creategroup"]))
    if "groupname" in params:
        _try_set(n, "groupname", str(params["groupname"]))
    if "repairoverlaps" in params:
        _try_set(n, "repairoverlaps", bool(params["repairoverlaps"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 10. uv_unitize (chain; in0 UV'd mesh) — unitize per-prim / per-island UVs to 0-1 ──────────────
@endpoint("uv_unitize")
def uv_unitize(params):
    """SideFX Labs UV Unitize (labs::uv_unitize::1.1) — remap each primitive (or each UV island) so
    its UVs fill the 0-1 unit square — the standard prep for trim-sheet / tiling-texture workflows.
    `input` (input 0) = a UV'd mesh. `mode` = per-primitive or per-island; `preserveaspect` keeps the
    real proportions; `preserveudim` keeps islands in their source UDIM tile. SECURITY: data-only."""
    n = child_after(params["input"], "labs::uv_unitize::1.1", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "grouptype" in params:
        _tok_menu_set(n, "grouptype", str(params["grouptype"]), _UNI_GRPTYPE_TOK)
    if "uvattribute" in params:
        _try_set(n, "uvattribute", str(params["uvattribute"]))
    if "mode" in params:
        _mapped_menu(n, "mode", params["mode"], _UNI_MODE, _UNI_MODE_TOK)
    if "preserveaspect" in params:
        _try_set(n, "preserveaspect", bool(params["preserveaspect"]))
    if "centerinunit" in params:
        _try_set(n, "centerinunit", bool(params["centerinunit"]))
    if "preserveudim" in params:
        _try_set(n, "preserveudim", bool(params["preserveudim"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

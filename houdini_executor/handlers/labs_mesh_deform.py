"""SideFX Labs — Mesh: Deform / Project / Visualize / Reconstruction / Transform lane (data-only
chain handlers). Params verified against live H21.0.671: parm names/types/defaults, ordered-menu tokens+labels, input/output counts, and a
headless cook. Categories wrapped, deduped to the highest version per base name:
  Labs/Geometry/Mesh: Deform     -> path_deform, polydeform, sine_wave
  Labs/Geometry/Mesh: Project    -> decal_projector::1.1, triplanar_displace
  Labs/Geometry/Mesh/Project +
  Labs/Geometry/Mesh: Project    -> detail_mesh::1.1
  Labs/Geometry/Mesh: Visualize  +
  Labs/Geometry/Transform        -> align_and_distribute::2.0 (dedup of unversioned + 2.0)
  Labs/Geometry/Reconstruction   -> delight, straighten::1.0
  Labs/Geometry/Transform        -> axis_align, turntable

Archetypes:
  * Archetype-B single-input CHAIN nodes (child_after auto-wires input 0): sine_wave,
    triplanar_displace, align_and_distribute, delight, straighten, axis_align, turntable.
  * TWO-input "Project"/deform nodes — source on input 0 (child_after) + a REQUIRED second operand
    bridged onto input 1:
        path_deform  : input0=Input Mesh, input1=Input Curve (path to deform along).
        polydeform   : input0=source_mesh, input1=target_mesh (deform-transfer target).
        detail_mesh  : input0=Template (tile mesh), input1=Projection (surface tiled onto).
        decal_projector : input0=Projection Mesh (required); inputs 1/2 (target points / decal
                          geometry) optional.

SECURITY (data-only): the only file surfaces here are IMAGE READS — decal_projector `basecolor`/
`heightmap` and triplanar_displace `texture`/`texture2` (FileReference strings). Each is set ONLY
when the caller supplies a value and is realpath-confined via confined_path() to the working dir;
absent -> the HDA default (a built-in $HFS texture) is left untouched. No code/callback/VEX parms
are exposed. detail_mesh `shop_materialpath1` (a node reference) and the interactive/draw/button
parms (btnUpdateEntries, like_tool, dont_like) are left at default. No node renders/executes.
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────


def _menu_idx_set(node, parm, token, tokens):
    """Ordered/Int menu stored as an INDEX (native tokens are '0','1',...): set index =
    tokens.index(token), where `tokens` is our human-label enum aligned to the native menu order."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(tokens.index(token))
        return True
    except Exception:
        return False


def _menu_tok_set(node, parm, token, tokens):
    """Menu whose native tokens are meaningful strings: set by the token string directly."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


def _set_vec3(node, parm, params, kx, ky, kz, lo=-1e6, hi=1e6):
    """Set a vec3 tuple parm from optional per-component params (read-modify: unset components keep
    the current value). No-op if none supplied or the tuple parm is absent."""
    vals = [params.get(kx), params.get(ky), params.get(kz)]
    if all(v is None for v in vals):
        return
    pt = node.parmTuple(parm)
    if pt is None:
        return
    try:
        cur = list(pt.eval())
    except Exception:
        cur = [0.0, 0.0, 0.0]
    for i, v in enumerate(vals):
        if v is not None:
            cur[i] = clamp(float(v), lo, hi)
    try:
        pt.set(tuple(cur))
    except Exception:
        pass


def _set_comp(node, parm, comp, value, lo, hi):
    """Set one component of a multi-component Float tuple (probe-safe). Used for sine_wave's
    two-wave vec2 parms (component 0 = primary wave, component 1 = secondary wave)."""
    pt = node.parmTuple(parm)
    if pt is None or comp >= len(pt):
        return False
    try:
        pt[comp].set(clamp(float(value), lo, hi))
        return True
    except Exception:
        return False


def _confine_set(node, parm, value):
    """Set a FileReference READ parm through confined_path() (path stays inside the working dir)."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(confined_path(str(value)))
        return True
    except Exception:
        return False


# ── ordered-menu label enums (position == native stored index) ────────────────────────────────────
_AXIS6 = ("+X", "+Y", "+Z", "-X", "-Y", "-Z")            # path_deform axis idx 0..5
_AXIS3 = ("X", "Y", "Z")                                 # sine_wave / turntable axis idx 0..2
_PD_METHOD = ("uniform", "edgelength")                   # polydeform method string tokens
_SW_GRPTYPE = ("guess", "vertices", "edges", "points", "prims")   # sine_wave grouptype string tokens
_AD_SPLITBY = ("connectivity", "piece_attribute")        # align_and_distribute splitby idx 0,1
_AD_SORTBY = ("none", "area", "polycount", "random")     # align_and_distribute sortby idx 0..3
_AD_LAYOUT = ("linear", "grid")                          # align_and_distribute layout idx 0,1
_AD_AXIS = ("x", "y", "z")                               # align_and_distribute axis idx 0..2
_AD_ALIGN = ("positive", "center", "negative")           # align_and_distribute alignment idx 0..2
_AD_ORIENT = ("xy", "yz", "zx")                          # align_and_distribute orientation string tok
_AD_JUSTIFY = ("none", "min", "center", "max")           # align_and_distribute justify* idx 0..3
_DL_GRPTYPE = ("guess", "breakpoints", "edges", "points", "prims")  # delight grouptype string tokens
_ST_GRPTYPE = ("primitive", "point", "edge")             # straighten grouptype string tokens
_AA_MODE = ("no_change", "center", "min", "max")         # axis_align x/y/z idx 0..3


# ── 1. path_deform (TWO-input chain; deform a mesh along a curve) ─────────────────────────────────
@endpoint("path_deform")
def path_deform(params):
    """Labs Path Deform (labs::path_deform) — bends `input` (input 0, the mesh) along the required
    `curve` (input 1, the path); an optional `banking_curve` (input 2) sets the up/banking direction.
    `axis` picks which local axis of the mesh runs along the curve; `curve_offset` slides the mesh
    along it, `scale`/`twist` size and twist the result, `scale_to_length` stretches the mesh to the
    curve length, `collapse`/`clip_min`/`clip_max` trim the ends. Data-only (no file/code surface;
    the scale/twist ramps stay at HDA default)."""
    n = child_after(params["input"], "labs::path_deform", params.get("name"))
    bridge_input(n, params["curve"], index=1, name_hint="curve")          # REQUIRED path curve
    if params.get("banking_curve"):
        bridge_input(n, params["banking_curve"], index=2, name_hint="banking")
    if "axis" in params:
        _menu_idx_set(n, "axis", str(params["axis"]), _AXIS6)
    if "curve_offset" in params:
        _try_set(n, "curve_offset", clamp(float(params["curve_offset"]), -1e6, 1e6))
    if "curve_resolution" in params:
        _try_set(n, "curve_resolution", clamp(float(params["curve_resolution"]), 1e-4, 1e4))
    if "normal_blur" in params:
        _try_set(n, "normal_blur", int(clamp(int(params["normal_blur"]), 0, 1000)))
    if "clip_min" in params:
        _try_set(n, "clip_min", bool(params["clip_min"]))
    if "clip_max" in params:
        _try_set(n, "clip_max", bool(params["clip_max"]))
    if "collapse" in params:
        _try_set(n, "collapse", bool(params["collapse"]))
    if "scale_to_length" in params:
        _try_set(n, "scale_to_length", clamp(float(params["scale_to_length"]), 0.0, 1e6))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 0.0, 1e4))
    if "twist" in params:
        _try_set(n, "twist", clamp(float(params["twist"]), -3600.0, 3600.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. polydeform (TWO-input chain; transfer a sculpt from a proxy) ───────────────────────────────
@endpoint("polydeform")
def polydeform(params):
    """Labs PolyDeform (labs::polydeform) — deforms the high-detail `input` (input 0, source_mesh) to
    follow the sculpted/edited `target` (input 1, target_mesh), transferring the low-res deformation
    onto the full-res mesh. `shape_blend` blends 0..1 toward the target; `retain_features` preserves
    sharp detail; `method` (uniform | edgelength) and the smoothing iteration counts control the
    relaxation; `scale_inputs` equalizes mismatched input scales. Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::polydeform", params.get("name"))
    bridge_input(n, params["target"], index=1, name_hint="target")        # REQUIRED target mesh
    if "retain_features" in params:
        _try_set(n, "retain_features", clamp(float(params["retain_features"]), 0.0, 1.0))
    if "shape_blend" in params:
        _try_set(n, "shape_blend", clamp(float(params["shape_blend"]), 0.0, 1.0))
    if "low_res_preview" in params:
        _try_set(n, "low_res_preview", bool(params["low_res_preview"]))
    if "scale_inputs" in params:
        _try_set(n, "scale_inputs", bool(params["scale_inputs"]))
    if "method" in params:
        _menu_tok_set(n, "method", str(params["method"]), _PD_METHOD)
    if "smoothiter" in params:
        _try_set(n, "smoothiter", int(clamp(int(params["smoothiter"]), 0, 500)))
    if "falloffsmoothiter" in params:
        _try_set(n, "falloffsmoothiter", int(clamp(int(params["falloffsmoothiter"]), 0, 500)))
    if "nmlsmoothiter" in params:
        _try_set(n, "nmlsmoothiter", int(clamp(int(params["nmlsmoothiter"]), 0, 500)))
    if "stepsize" in params:
        _try_set(n, "stepsize", clamp(float(params["stepsize"]), 0.0, 2.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. sine_wave (chain; sine-wave displacement) ──────────────────────────────────────────────────
@endpoint("sine_wave")
def sine_wave(params):
    """Labs Sine Wave (labs::sine_wave) — displaces `input` (input 0) with two summed sine waves along
    `axis` (X|Y|Z). Each wave has an `intensity` (amplitude), `frequency`, `speed` (animation over
    time) and `offset`; the `_b` params drive the second wave (defaults: primary intensity 0, secondary
    intensity 1). Restrict the effect with a `group`/`grouptype` or a scalar `attribute_mask`.
    Data-only (all strings are group/attribute NAMES, never paths; no code surface)."""
    n = child_after(params["input"], "labs::sine_wave", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))                        # geometry group NAME
    if "grouptype" in params:
        _menu_tok_set(n, "grouptype", str(params["grouptype"]), _SW_GRPTYPE)
    if "mask_by_attribute" in params:
        _try_set(n, "mask_by_attribute", bool(params["mask_by_attribute"]))
    if "attribute_mask" in params:
        _try_set(n, "attribute_mask", str(params["attribute_mask"]))      # attribute NAME
    if "axis" in params:
        _menu_idx_set(n, "axis", str(params["axis"]), _AXIS3)
    # two-wave vec2 parms: component 0 = primary wave, component 1 = secondary (`_b`) wave.
    if "intensity" in params:
        _set_comp(n, "intensity", 0, params["intensity"], -1e6, 1e6)
    if "intensity_b" in params:
        _set_comp(n, "intensity", 1, params["intensity_b"], -1e6, 1e6)
    if "frequency" in params:
        _set_comp(n, "frequency", 0, params["frequency"], 0.0, 1e6)
    if "frequency_b" in params:
        _set_comp(n, "frequency", 1, params["frequency_b"], 0.0, 1e6)
    if "speed" in params:
        _set_comp(n, "speed", 0, params["speed"], -1e6, 1e6)
    if "speed_b" in params:
        _set_comp(n, "speed", 1, params["speed_b"], -1e6, 1e6)
    if "offset" in params:
        _set_comp(n, "offset", 0, params["offset"], -1e6, 1e6)
    if "offset_b" in params:
        _set_comp(n, "offset", 1, params["offset_b"], -1e6, 1e6)
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. decal_projector (chain; project a decal onto a surface) ────────────────────────────────────
@endpoint("decal_projector")
def decal_projector(params):
    """Labs Decal Projector (labs::decal_projector::1.1) — projects a decal (base-color + height map)
    onto the surface `input` (input 0, the Projection Mesh). Optional `target_points` (input 1) place
    the decal and `decal_geometry` (input 2) supplies custom decal geo. Position it with `translate`/
    `rotate`/`scale` (vec3) + uniform `scale`; `strength` scales the height displacement,
    `max_distance`/`floating_distance` gate projection depth. Data-only.
    SECURITY: `basecolor`/`heightmap` are IMAGE READS — set only when supplied and realpath-confined
    to the working dir; the multi-decal folder, update button and manual-tweak toggle are untouched."""
    n = child_after(params["input"], "labs::decal_projector::1.1", params.get("name"))
    if params.get("target_points"):
        bridge_input(n, params["target_points"], index=1, name_hint="targetpts")
    if params.get("decal_geometry"):
        bridge_input(n, params["decal_geometry"], index=2, name_hint="decalgeo")
    if "basecolor" in params:
        _confine_set(n, "basecolor", params["basecolor"])                 # SECURITY: confined read
    if "heightmap" in params:
        _confine_set(n, "heightmap", params["heightmap"])                 # SECURITY: confined read
    _set_vec3(n, "t", params, "translate_x", "translate_y", "translate_z")
    _set_vec3(n, "r", params, "rotate_x", "rotate_y", "rotate_z", -3600.0, 3600.0)
    _set_vec3(n, "s", params, "scale_x", "scale_y", "scale_z", 1e-4, 1e6)
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-4, 1e4))
    if "match_image_aspect_ratio" in params:
        _try_set(n, "match_image_aspect_ratio", bool(params["match_image_aspect_ratio"]))
    if "strength" in params:
        _try_set(n, "strength", clamp(float(params["strength"]), -1e4, 1e4))
    if "invert_height_for_basecolor" in params:
        _try_set(n, "invert_height_for_basecolor", bool(params["invert_height_for_basecolor"]))
    if "max_distance" in params:
        _try_set(n, "max_distance", clamp(float(params["max_distance"]), 0.0, 1e6))
    if "floating_distance" in params:
        _try_set(n, "floating_distance", clamp(float(params["floating_distance"]), -1e4, 1e4))
    if "recompute_point_normals" in params:
        _try_set(n, "recompute_point_normals", bool(params["recompute_point_normals"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. detail_mesh (TWO-input chain; tile a detail mesh over a UV'd surface) ───────────────────────
@endpoint("detail_mesh")
def detail_mesh(params):
    """Labs Detail Mesh (labs::detail_mesh::1.1) — tiles the stamp/detail mesh `tile` (input 1) across
    the UV layout of the surface `input` (input 0, the canvas), wrapping the tiles onto it (e.g.
    bricks/shingles over a wall). The canvas surface MUST carry proper UV islands (a `uvunwrap`, not a
    flat planar projection) — the tool follows those UV shells. `tile_scale`/`tile_rotate` size and
    orient the tiles; `fuse_distance`+`relax_strength` weld and relax the seams; `tile_depth_scalar`
    scales the tile depth; `cusp_angle`/`post_triangulate` clean the result. NOTE: the node's own input
    labels (Template/Projection) are reversed vs the live wiring — input 0 is the canvas, input 1 the
    stamp. Data-only: the seam-material node reference and the like/dislike buttons are left at default
    (no file/code surface)."""
    n = child_after(params["input"], "labs::detail_mesh::1.1", params.get("name"))
    bridge_input(n, params["tile"], index=1, name_hint="tile")            # REQUIRED stamp/tile mesh
    if "tile_scale" in params:
        _try_set(n, "s", clamp(float(params["tile_scale"]), 1e-4, 1e4))
    if "tile_rotate" in params:
        _try_set(n, "r", clamp(float(params["tile_rotate"]), -3600.0, 3600.0))
    if "mask_by_color" in params:
        _try_set(n, "bMaskByColor", bool(params["mask_by_color"]))
    if "tile_depth_scalar" in params:
        _try_set(n, "fSurfaceScalar", clamp(float(params["tile_depth_scalar"]), -1e4, 1e4))
    if "prebricker" in params:
        _try_set(n, "prebricker", bool(params["prebricker"]))
    if "fuse_distance" in params:
        _try_set(n, "dist", clamp(float(params["fuse_distance"]), 0.0, 1e4))
    if "relax_strength" in params:
        _try_set(n, "strength", clamp(float(params["relax_strength"]), 0.0, 1e4))
    if "cusp_angle" in params:
        _try_set(n, "cuspangle", clamp(float(params["cusp_angle"]), 0.0, 180.0))
    if "post_triangulate" in params:
        _try_set(n, "usemaxsides", bool(params["post_triangulate"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. triplanar_displace (chain; triplanar texture displacement) ─────────────────────────────────
@endpoint("triplanar_displace")
def triplanar_displace(params):
    """Labs Triplanar Displace (labs::triplanar_displace) — displaces `input` (input 0) by sampling a
    displacement `texture` triplanar-projected onto the mesh (no UVs needed). `texture_scale` sizes the
    projection, `displacement_amount` scales the push, `axis_blend` controls the triplanar blend; an
    optional `color_texture` writes Cd. Noise projection-offset (`use_noise`+`frequency`/`amplitude`/
    `roughness`/`turbulence`) and a `displace_scale_attribute` remap round it out. Data-only.
    SECURITY: `texture`/`color_texture` are IMAGE READS — set only when supplied and realpath-confined
    to the working dir; absent -> the built-in $HFS default texture is used."""
    n = child_after(params["input"], "labs::triplanar_displace", params.get("name"))
    if "displacement" in params:
        _try_set(n, "bDisplacement", bool(params["displacement"]))
    if "texture" in params:
        _confine_set(n, "texture", params["texture"])                     # SECURITY: confined read
    if "color" in params:
        _try_set(n, "bColor", bool(params["color"]))
    if "color_texture" in params:
        _confine_set(n, "texture2", params["color_texture"])              # SECURITY: confined read
    if "texture_scale" in params:
        _try_set(n, "scale", clamp(float(params["texture_scale"]), 1e-4, 1e4))
    if "displacement_amount" in params:
        _try_set(n, "strength", clamp(float(params["displacement_amount"]), -1e4, 1e4))
    if "axis_blend" in params:
        _try_set(n, "exp", clamp(float(params["axis_blend"]), 0.0, 100.0))
    if "smooth_normals" in params:
        _try_set(n, "smooth_normals", bool(params["smooth_normals"]))
    if "mirror_x" in params:
        _try_set(n, "mirror_x", bool(params["mirror_x"]))
    if "mirror_z" in params:
        _try_set(n, "mirror_z", bool(params["mirror_z"]))
    if "use_noise" in params:
        _try_set(n, "use_noise", bool(params["use_noise"]))
    if "amplitude" in params:
        _try_set(n, "amp", clamp(float(params["amplitude"]), -1e4, 1e4))
    if "roughness" in params:
        _try_set(n, "rough", clamp(float(params["roughness"]), 0.0, 1.0))
    if "attenuation" in params:
        _try_set(n, "atten", clamp(float(params["attenuation"]), 0.0, 1e4))
    if "turbulence" in params:
        _try_set(n, "turb", int(clamp(int(params["turbulence"]), 0, 20)))
    if "use_attrib" in params:
        _try_set(n, "use_attrib", bool(params["use_attrib"]))
    if "displace_scale_attribute" in params:
        _try_set(n, "displace_scale", str(params["displace_scale_attribute"]))  # attribute NAME
    if "src_min" in params:
        _try_set(n, "srcmin", clamp(float(params["src_min"]), -1e6, 1e6))
    if "src_max" in params:
        _try_set(n, "srcmax", clamp(float(params["src_max"]), -1e6, 1e6))
    if "dest_min" in params:
        _try_set(n, "destmin", clamp(float(params["dest_min"]), -1e6, 1e6))
    if "dest_max" in params:
        _try_set(n, "destmax", clamp(float(params["dest_max"]), -1e6, 1e6))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. align_and_distribute (chain; lay pieces out in a line or grid) ─────────────────────────────
@endpoint("align_and_distribute")
def align_and_distribute(params):
    """Labs Align and Distribute (labs::align_and_distribute::2.0) — splits `input` (input 0) into
    pieces (by `split_by` connectivity or a piece `attribute_name`), optionally `sort_by` (area/
    polycount/random with `seed`), then lays them out with `spacing` in a `layout` (linear | grid).
    Linear uses `axis`+`alignment`; grid uses `orientation`+`justify_x`/`_y`/`_z`. Data-only (strings
    are attribute NAMES; `visualize_bounds` draws bbox guides only)."""
    n = child_after(params["input"], "labs::align_and_distribute::2.0", params.get("name"))
    if "split_by" in params:
        _menu_idx_set(n, "splitby", str(params["split_by"]), _AD_SPLITBY)
    if "attribute_name" in params:
        _try_set(n, "attributename", str(params["attribute_name"]))       # piece attribute NAME
    if "sort_by" in params:
        _menu_idx_set(n, "sortby", str(params["sort_by"]), _AD_SORTBY)
    if "seed" in params:
        _try_set(n, "seed", clamp(float(params["seed"]), -1e9, 1e9))
    if "spacing" in params:
        _try_set(n, "spacing", clamp(float(params["spacing"]), 0.0, 1e6))
    if "layout" in params:
        _menu_idx_set(n, "layout", str(params["layout"]), _AD_LAYOUT)
    if "axis" in params:
        _menu_idx_set(n, "axis", str(params["axis"]), _AD_AXIS)
    if "alignment" in params:
        _menu_idx_set(n, "alignment", str(params["alignment"]), _AD_ALIGN)
    if "orientation" in params:
        _menu_tok_set(n, "orientation", str(params["orientation"]), _AD_ORIENT)
    if "justify_x" in params:
        _menu_idx_set(n, "justifyx", str(params["justify_x"]), _AD_JUSTIFY)
    if "justify_y" in params:
        _menu_idx_set(n, "justifyy", str(params["justify_y"]), _AD_JUSTIFY)
    if "justify_z" in params:
        _menu_idx_set(n, "justifyz", str(params["justify_z"]), _AD_JUSTIFY)
    if "visualize_bounds" in params:
        _try_set(n, "visualizebounds", bool(params["visualize_bounds"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 8. delight (chain; remove baked lighting from vertex colors) ──────────────────────────────────
@endpoint("delight")
def delight(params):
    """Labs Delight (labs::delight) — removes baked-in lighting/AO from the vertex colors (Cd) of
    `input` (input 0), flattening a scanned/photographed mesh toward even albedo. `samples`+
    `iterations` control the occlusion estimate and blur; `ao_*` params add optional AO re-brightening;
    `lighting_exposure`/`lighting_saturation` tune the recovered albedo. `grouptype` scopes the fix.
    Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::delight", params.get("name"))
    if "samples" in params:
        _try_set(n, "samples", int(clamp(int(params["samples"]), 1, 4096)))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 500)))
    if "grouptype" in params:
        _menu_tok_set(n, "grouptype", str(params["grouptype"]), _DL_GRPTYPE)
    if "ao_brightening" in params:
        _try_set(n, "ao_brightening", bool(params["ao_brightening"]))
    if "ao_strength" in params:
        _try_set(n, "ao_strength", clamp(float(params["ao_strength"]), 0.0, 1e4))
    if "ao_blend_strength" in params:
        _try_set(n, "ao_blend_strength", clamp(float(params["ao_blend_strength"]), 0.0, 1.0))
    if "ao_iterations" in params:
        _try_set(n, "ao_iterations", int(clamp(int(params["ao_iterations"]), 0, 500)))
    if "ao_tint" in params:
        _try_set(n, "ao_tint", clamp(float(params["ao_tint"]), 0.0, 1.0))
    if "lighting_exposure" in params:
        _try_set(n, "lighting_exposure", clamp(float(params["lighting_exposure"]), -10.0, 10.0))
    if "lighting_saturation" in params:
        _try_set(n, "lighting_saturation", clamp(float(params["lighting_saturation"]), 0.0, 4.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 9. straighten (chain; reorient geometry to a canonical frame) ─────────────────────────────────
@endpoint("straighten")
def straighten(params):
    """Labs Straighten (labs::straighten::1.0) — reorients `input` (input 0) into a canonical
    axis-aligned frame using a selected `up_group` (and optionally a `forward_group` when
    `align_forward` is on) of the given `grouptype` (primitive | point | edge) as the up/forward
    reference; `invert_up` flips the up axis. With `output_transform` on, the alignment matrix is
    written to the `xform_attribute` instead of moving the geometry. Data-only (strings are group/
    attribute NAMES; no file/code surface)."""
    n = child_after(params["input"], "labs::straighten::1.0", params.get("name"))
    if "grouptype" in params:
        _menu_tok_set(n, "grouptype", str(params["grouptype"]), _ST_GRPTYPE)
    if "up_group" in params:
        _try_set(n, "upgroup", str(params["up_group"]))                   # geometry group NAME
    if "invert_up" in params:
        _try_set(n, "invertup", bool(params["invert_up"]))
    if "align_forward" in params:
        _try_set(n, "alignforward", bool(params["align_forward"]))
    if "forward_group" in params:
        _try_set(n, "forwardgroup", str(params["forward_group"]))         # geometry group NAME
    if "output_transform" in params:
        _try_set(n, "outputxform", bool(params["output_transform"]))
    if "xform_attribute" in params:
        _try_set(n, "xformattribute", str(params["xform_attribute"]))     # attribute NAME
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 10. axis_align (chain; snap geometry to origin per axis) ──────────────────────────────────────
@endpoint("axis_align")
def axis_align(params):
    """Labs Axis Align (labs::axis_align) — repositions `input` (input 0) relative to the origin per
    axis: each of `x`/`y`/`z` chooses to leave that axis unchanged or snap its bounding box Center,
    Min or Max to 0. `unit_size` additionally uniformly scales the geometry to fit a unit bounding
    box. Data-only (no file/code surface)."""
    n = child_after(params["input"], "labs::axis_align", params.get("name"))
    if "x" in params:
        _menu_idx_set(n, "x", str(params["x"]), _AA_MODE)
    if "y" in params:
        _menu_idx_set(n, "y", str(params["y"]), _AA_MODE)
    if "z" in params:
        _menu_idx_set(n, "z", str(params["z"]), _AA_MODE)
    if "unit_size" in params:
        _try_set(n, "bUnitSize", bool(params["unit_size"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 11. turntable (chain; frame-driven turntable rotation) ────────────────────────────────────────
@endpoint("turntable")
def turntable(params):
    """Labs Turntable (labs::turntable) — rotates `input` (input 0) about `axis` (X|Y|Z) as a function
    of the current frame, completing `num_turns` full rotations over the frame range (a turntable
    preview animation). `rotate_around_origin` spins about the world origin instead of the geometry
    centroid. The cook emits the rotated geometry at the current frame. Data-only (no file/code
    surface)."""
    n = child_after(params["input"], "labs::turntable", params.get("name"))
    if "axis" in params:
        _menu_idx_set(n, "axis", str(params["axis"]), _AXIS3)
    if "num_turns" in params:
        _try_set(n, "num_turns", clamp(float(params["num_turns"]), -1e4, 1e4))
    if "rotate_around_origin" in params:
        _try_set(n, "rotate_around_origin", bool(params["rotate_around_origin"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

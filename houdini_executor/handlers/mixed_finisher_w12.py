"""Mixed finisher lane — four data-only sub-lanes, all verified against live H21.0.671 via
hython probes:

  Object attach / light / camera (11): rivet, sticky, blend_sticky (surface-attach OBJs);
    three_point_light, indirect_light, ambient_light, environment_fog (light/atmosphere OBJs);
    reference_image, stereo_camera, stereo_camera_rig, vr_camera (camera / plate OBJs). Each is an
    /obj generator built with hou.node("/obj").createNode(type, name) — FAILS on name collision (never
    destroys existing user work), sets a typed transform (t/r/s + uniform scale) plus a curated set of
    typed data knobs, flips display on, and lays out /obj. NO shader / material / pickscript / light-
    wrangler / lens-shader / VOP param is ever exposed.

  Driver USD utility exporters (3): usd_stitch, usd_stitch_clips, usd_zip. Built as /out ROPs
    (usdstitch / usdstitchclips / usdzip), file paths set through confined_path, typed params applied —
    then RETURNED UNEXECUTED (WIRE-ONLY: the USER fires the write). The pre/post-render + per-frame
    SCRIPT params (prerender/postrender/... with their hscript|python language menus) are NEVER exposed
    or set.

  LOP editorial + USD constraints (12): shot_load / shot_output / shot_layer_edit (shot
    editorial), usd_value_clip / usd_geometry_sequence / usd_geo_clip_sequence (USD sequence I/O),
    usd_blend_constraint / usd_followpath_constraint / usd_lookat_constraint / usd_parent_constraint /
    usd_points_constraint / usd_surface_constraint (USD xform constraints authored on the /stage). LOP
    /stage operators; sequence-I/O file paths go through confined_path. shot_output is a file-writing
    LOP ROP and is WIRE-ONLY (built + configured, never executed).

  CHOP anim-utility (9): chop_footplant, chop_iksolver, chop_inversekin, chop_transform_chain,
    chop_export_transforms, chop_extract_bone_transforms, chop_extract_pose_drivers, chop_blendpose,
    chop_stashpose. CHOP nodes in a chopnet — GENERATORS (inversekin / extractbonetransforms /
    extractposedrivers, 0 inputs) build in a fresh (or supplied) chopnet; OPERATORS chain onto an input
    CHOP with child_after and wire aux CHOP inputs by direct setInput. Channel / transform data params
    only.

Not wrapped (already covered): 4 USD-exporter candidates —
zibravdb_compress (labs::zibravdb_compress::1.0) duplicates the shipped
rop_zibravdb_compress; kinefx::filmboxfbxanimation / kinefx::filmboxfbxcharacter / kinefx::gltfcharacter
duplicate the shipped fbx_anim_export / fbx_character_export / gltf_character_export. All 35 KEPT node
types are net-new coverage.

SECURITY (data-only): every exposed param is a typed data knob (count / size / tolerance / menu token /
bool / node-path or attribute-name / channel-name string / vec). The ONLY filesystem surfaces are the
file-confined exporters/sequence-I/O below, each realpath-confined via confined_path:
  READ : reference_image.image_file; usd_value_clip.clip_files/manifest_file;
         usd_geometry_sequence.file; usd_geo_clip_sequence.load_clip_file.
  WRITE: usd_stitch.output; usd_stitch_clips.output_template; usd_zip.output; shot_output.output;
         usd_geo_clip_sequence.save_clip_file.
WIRE-ONLY (built + configured, NEVER executed / rendered / cooked-to-disk): usd_stitch, usd_stitch_clips,
usd_zip, shot_output.
DEFERRED (never exposed): the USD-constraint VEX/HScript SNIPPET params (positionsnippet / rollsnippet /
weightssnippet + their use*snippet toggles on followpath/points/surface constraints); the interactive
curve-EDIT widget on followpathconstraint (draw/select buttons + stashed-geometry Data parms); every
ROP pre/post/per-frame SCRIPT param; refimage's Mantra procedural-shader param; vrcam's lens-shader.
"""

import hou
from houdini_executor.server import (
    endpoint, confined_path, clamp, child_after, resolve_node, out_context, stage_context,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared probe-safe helpers (copied per house convention: never invent a parm) ──────────────────


def _try_set_tuple(node, parm, values, lo=None, hi=None):
    pt = node.parmTuple(parm)
    if pt is None or not isinstance(values, (list, tuple)):
        return False
    try:
        out = []
        for x in values:
            v = float(x)
            if lo is not None:
                v = clamp(v, lo, hi)
            out.append(v)
        pt.set(tuple(out))
        return True
    except Exception:  # noqa: BLE001
        return False




def _str_menu_set(node, parm, token, tokens):
    """Menu stored by STRING token: set the token directly (validated against the live token set)."""
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _menu_auto(node, parm, token, tokens):
    """Ambiguous menu: try the STRING token first, fall back to the INDEX. Both guarded."""
    if token not in tokens:
        return False
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(token)
        return True
    except Exception:  # noqa: BLE001
        try:
            p.set(tokens.index(token))
            return True
        except Exception:  # noqa: BLE001
            return False


def _as_list(v):
    """Normalize a multi-item param to a list of strings: accept a real list/tuple, a JSON array
    string, or a comma-separated string (the house convention for list-shaped params, since the
    gateway has no list Kind — they arrive as a Str)."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    s = str(v).strip()
    if s.startswith("["):
        try:
            import json
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:  # noqa: BLE001
            pass
    return [t.strip() for t in s.split(",") if t.strip()]


def _apply(node, params, spec):
    """Apply a curated typed param table. Each row is (mcp_key, parm_name, kind, extra):
       f=float[min,max]  i=int[min,max]  b=bool  s=string  m=index-menu(tokens)
       ms=string-token-menu(tokens)  ma=auto-menu(tokens; string-then-index)
       fv=float-tuple[min,max]  iv=int-tuple[min,max]."""
    for key, parm, kind, extra in spec:
        if key not in params:
            continue
        v = params[key]
        if kind == "f":
            _try_set(node, parm, clamp(float(v), extra[0], extra[1]))
        elif kind == "i":
            _try_set(node, parm, int(clamp(int(v), extra[0], extra[1])))
        elif kind == "b":
            _try_set(node, parm, bool(v))
        elif kind == "s":
            _try_set(node, parm, str(v))
        elif kind == "m":
            _menu_set(node, parm, str(v), extra)
        elif kind == "ms":
            _str_menu_set(node, parm, str(v), extra)
        elif kind == "ma":
            _menu_auto(node, parm, str(v), extra)
        elif kind == "fv":
            _try_set_tuple(node, parm, v, extra[0], extra[1])
        elif kind == "iv":
            _try_set_tuple(node, parm, [int(x) for x in v], extra[0], extra[1])


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Object attach / light / camera  (/obj generators, fresh-name-on-collision)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _fresh_obj(ntype, name):
    """A fresh /obj object of `ntype`. FAILS on name collision (never destroys existing user work)."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    n = obj.createNode(ntype, name) if name else obj.createNode(ntype)
    return n


_XORD = ("srt", "str", "rst", "rts", "tsr", "trs")
_RORD = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")
_T = (-1.0e7, 1.0e7)
_R = (-3.6e3, 3.6e3)
_S = (-1.0e4, 1.0e4)
_USCALE = (0.0, 1.0e4)
_INTENS = (0.0, 1.0e6)
_COL = (0.0, 1.0e3)


def _set_trs(n, params):
    """Apply the common OBJ transform (t/r/s vec3 + uniform scale). Probe-safe."""
    _apply(n, params, [
        ("t", "t", "fv", _T), ("r", "r", "fv", _R), ("s", "s", "fv", _S),
        ("scale", "scale", "f", _USCALE),
    ])


def _finish_obj(n):
    """Display the new OBJ and lay out /obj. Best-effort (a flag failure must not break the build)."""
    try:
        n.setDisplayFlag(True)
    except Exception:  # noqa: BLE001
        pass
    try:
        hou.node("/obj").layoutChildren()
    except Exception:  # noqa: BLE001
        pass
    return {"node": n.path(), "type": n.type().name()}


@endpoint("rivet")
def rivet(params):
    """Create a Rivet OBJ (rivet) — a transform locked to a point/primitive on a deforming surface
    (the classic "stick a prop to an animated mesh" attach). rivet_geo = the Rivet Geometry SOP path;
    point_group restricts the attach point; use_point_attribs + x_attrib/z_attrib orient the rivet
    frame from point vector attributes. t/r/s/scale offset the rivet. NO select-script / material."""
    n = _fresh_obj("rivet", params.get("name"))
    _apply(n, params, [
        ("rivet_geo", "rivetsop", "s", None),
        ("point_group", "rivetgroup", "s", None),
        ("use_point_attribs", "rivetuseattribs", "b", None),
        ("x_attrib", "rivetxattrib", "s", None),
        ("z_attrib", "rivetzattrib", "s", None),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("sticky")
def sticky(params):
    """Create a Sticky OBJ (sticky) — a transform pinned to a UV coordinate on a surface, so it slides
    with the surface as it deforms. sticky_geo = the Sticky Geometry SOP path; attribute = the UV
    attribute name; uv = [u,v] attach coordinate; rotation twists it; orient aligns to the surface
    normal. t/r/s/scale offset the sticky. NO select-script / material."""
    n = _fresh_obj("sticky", params.get("name"))
    _apply(n, params, [
        ("sticky_geo", "stickysop", "s", None),
        ("attribute", "stickyattrib", "s", None),
        ("uv", "stickyuv", "fv", (-1.0e6, 1.0e6)),
        ("rotation", "stickyrot", "f", (-3.6e3, 3.6e3)),
        ("orient", "stickyorient", "b", None),
        ("fetch_world", "fetchworld", "b", None),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("blend_sticky")
def blend_sticky(params):
    """Create a Blend Sticky OBJ (blendsticky) — a Sticky whose position is a weighted BLEND of several
    input sticky objects (parent the source stickies to it). attribute = the UV attribute; orient
    aligns to the surface. t/r/s/scale offset the result. (Per-source blend weights are a viewport
    multiparm and are left at default; drive them by parenting the source stickies.)"""
    n = _fresh_obj("blendsticky", params.get("name"))
    _apply(n, params, [
        ("attribute", "stickyattrib", "s", None),
        ("orient", "stickyorient", "b", None),
        ("fetch_world", "fetchworld", "b", None),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("three_point_light")
def three_point_light(params):
    """Create a Three Point Light rig OBJ (three_point_light) — a single node bundling key / fill / rim
    / bounce lights aimed at a shared target. Per-light: *_enable (on/off), *_intensity, *_color
    [r,g,b] for key/fill/rim/bounce. look_at_target = [x,y,z] the whole rig aims at (enables the
    target). t/r/s/scale place the rig. NO light-wrangler / projection-map / shader param."""
    n = _fresh_obj("three_point_light", params.get("name"))
    if "look_at_target" in params:
        _try_set(n, "use_look_at_target", True)
        _try_set_tuple(n, "look_at_target", params["look_at_target"], -1.0e7, 1.0e7)
    _apply(n, params, [
        ("key_enable", "key_light_light_enable", "b", None),
        ("key_intensity", "key_light_light_intensity", "f", _INTENS),
        ("key_color", "key_light_light_color", "fv", _COL),
        ("fill_enable", "fill_light_light_enable", "b", None),
        ("fill_intensity", "fill_light_light_intensity", "f", _INTENS),
        ("fill_color", "fill_light_light_color", "fv", _COL),
        ("rim_enable", "rim_light_light_enable", "b", None),
        ("rim_intensity", "rim_light_light_intensity", "f", _INTENS),
        ("rim_color", "rim_light_light_color", "fv", _COL),
        ("bounce_enable", "bounce_light_light_enable", "b", None),
        ("bounce_intensity", "bounce_light_light_intensity", "f", _INTENS),
        ("bounce_color", "bounce_light_light_color", "fv", _COL),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("indirect_light")
def indirect_light(params):
    """Create an Indirect (global-illumination bounce) Light OBJ (indirectlight). dimmer scales the
    indirect contribution. t/r/s/scale place it. NO shader / wrangler param."""
    n = _fresh_obj("indirectlight", params.get("name"))
    _apply(n, params, [("dimmer", "dimmer", "f", (0.0, 1.0e3))])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("ambient_light")
def ambient_light(params):
    """Create an Ambient Light OBJ (ambient) — a flat, uniform fill added to the whole scene. color =
    [r,g,b] ambient colour; intensity scales it; enable toggles the light. t/r/s/scale place it."""
    n = _fresh_obj("ambient", params.get("name"))
    _apply(n, params, [
        ("color", "light_color", "fv", _COL),
        ("intensity", "light_intensity", "f", _INTENS),
        ("enable", "light_enable", "b", None),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("environment_fog")
def environment_fog(params):
    """Create an Environment Fog OBJ (fog) — a scene-filling atmospheric volume container. t/r/s/scale
    size and place the fog box. (The fog look is driven by an assigned material downstream — NO shader
    param is exposed here; this authors the data-only fog OBJ + its transform.)"""
    n = _fresh_obj("fog", params.get("name"))
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("reference_image")
def reference_image(params):
    """Create a Reference Image OBJ (refimage) — a flat image plane for modelling reference / matching.
    image_file = the picture (realpath READ-confined to the working dir); alpha fades it; frame picks
    the sequence frame; orient = front|top|right places the plane. t/r/s/scale size and position it."""
    n = _fresh_obj("refimage", params.get("name"))
    if params.get("image_file"):
        _try_set(n, "copfile", confined_path(params["image_file"]))
    _apply(n, params, [
        ("alpha", "alpha", "f", (0.0, 1.0)),
        ("frame", "frame", "i", (-1000000, 1000000)),
        ("orient", "orient", "m", ("front", "top", "right")),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("stereo_camera")
def stereo_camera(params):
    """Create a Stereo Camera OBJ (stereocam) — a container that groups a left + right camera. left_cam
    / right_cam = the two camera OBJ paths. t/r/s/scale place the pair."""
    n = _fresh_obj("stereocam", params.get("name"))
    _apply(n, params, [
        ("left_cam", "leftcam", "s", None),
        ("right_cam", "rightcam", "s", None),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("stereo_camera_rig")
def stereo_camera_rig(params):
    """Create a Stereo Camera Rig OBJ (stereocamrig) — a full parametric stereo rig. interaxial = eye
    separation; zps = zero-parallax setting (+ infinite_zps); toe_in enables converged toe-in. Camera
    intrinsics: focal, aperture, near, far, res=[x,y]. t/r/s/scale place the rig."""
    n = _fresh_obj("stereocamrig", params.get("name"))
    if "res" in params:
        _try_set_tuple(n, "res", [int(x) for x in params["res"]], 1, 16384)
    _apply(n, params, [
        ("interaxial", "interaxial", "f", (0.0, 1.0e4)),
        ("zps", "ZPS", "f", (0.0, 1.0e7)),
        ("infinite_zps", "infinite_ZPS", "b", None),
        ("toe_in", "toe_in", "b", None),
        ("focal", "focal", "f", (0.1, 1.0e4)),
        ("aperture", "aperture", "f", (0.1, 1.0e4)),
        ("near", "near", "f", (0.0, 1.0e9)),
        ("far", "far", "f", (0.0, 1.0e12)),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


@endpoint("vr_camera")
def vr_camera(params):
    """Create a VR Camera OBJ (vrcam) — a stereo panoramic camera for VR renders. projection =
    perspective|ortho|sphere|cylinder (sphere/cylinder = equirectangular / cylindrical panoramas);
    horizontal_fov / vertical_fov the pano coverage; eye_separation the stereo offset. Intrinsics:
    focal, aperture, near, far, res=[x,y]. t/r/s/scale place it. NO lens-shader / background-plate."""
    n = _fresh_obj("vrcam", params.get("name"))
    if "res" in params:
        _try_set_tuple(n, "res", [int(x) for x in params["res"]], 1, 16384)
    _apply(n, params, [
        ("projection", "projection", "ma", ("perspective", "ortho", "sphere", "cylinder")),
        ("focal", "focal", "f", (0.1, 1.0e4)),
        ("aperture", "aperture", "f", (0.1, 1.0e4)),
        ("near", "near", "f", (0.0, 1.0e9)),
        ("far", "far", "f", (0.0, 1.0e12)),
        ("horizontal_fov", "vrhorizontalfov", "f", (0.0, 360.0)),
        ("vertical_fov", "vrverticalfov", "f", (0.0, 360.0)),
        ("eye_separation", "vreyeseparation", "f", (0.0, 1.0e4)),
    ])
    _set_trs(n, params)
    return _finish_obj(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Driver USD utility exporters  (/out ROPs, WIRE-ONLY: built + configured, NEVER executed)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _grow_multiparm(n, control, count):
    """Set a MultiparmBlock instance count so infile1..N (etc.) exist. Guarded no-op if absent."""
    _try_set(n, control, int(count))


@endpoint("usd_stitch")
def usd_stitch(params):
    """WIRE-ONLY: build a USD Stitch ROP (/out usdstitch) that merges several input USD layers into an
    output layer — configured but NEVER executed (the USER fires the write). input_files = list of
    input .usd/.usda/.usdc (each realpath READ-confined); output = the stitched output path (WRITE-
    confined). Returns {node, rendered:False}. Pre/post-render SCRIPT params are never exposed."""
    n = out_context().createNode("usdstitch", params.get("name"))
    inputs = _as_list(params.get("input_files"))
    out_path = confined_path(params["output"]) if params.get("output") else None
    if inputs:
        _grow_multiparm(n, "stitchfiles", len(inputs))
        for i, f in enumerate(inputs, start=1):
            _try_set(n, "enable%d" % i, True)
            _try_set(n, "infile%d" % i, confined_path(f))
            if out_path:
                _try_set(n, "outfile%d" % i, out_path)
    elif out_path:
        _try_set(n, "outfile1", out_path)
    return {"node": n.path(), "rendered": False, "output": out_path,
            "inputs": [confined_path(f) for f in inputs],
            "note": "USD stitch ROP wired; run the write yourself"}


@endpoint("usd_stitch_clips")
def usd_stitch_clips(params):
    """WIRE-ONLY: build a USD Stitch Clips ROP (/out usdstitchclips) that assembles per-frame USD clips
    into a value-clip topology + template — configured but NEVER executed. input_files = list of clip
    .usd files (READ-confined); output_template = the clip template path (WRITE-confined); clip_path =
    the clip primitive path; clip_set = the clip-set name; tcps = time codes per second (+ set_tcps
    mode). Returns {node, rendered:False}."""
    n = out_context().createNode("usdstitchclips", params.get("name"))
    inputs = _as_list(params.get("input_files"))
    tmpl = confined_path(params["output_template"]) if params.get("output_template") else None
    if inputs:
        _grow_multiparm(n, "stitchfiles", len(inputs))
        for i, f in enumerate(inputs, start=1):
            _try_set(n, "enable%d" % i, True)
            _try_set(n, "infile%d" % i, confined_path(f))
            if tmpl:
                _try_set(n, "outtemplatefile%d" % i, tmpl)
            if params.get("clip_path"):
                _try_set(n, "clippath%d" % i, str(params["clip_path"]))
            if params.get("clip_set"):
                _try_set(n, "clipset%d" % i, str(params["clip_set"]))
    _apply(n, params, [
        ("set_tcps", "settcps", "ms", ("specificvalue", "fromfirstclip", "none")),
        ("tcps", "tcps", "f", (0.0, 1.0e6)),
    ])
    return {"node": n.path(), "rendered": False, "output_template": tmpl,
            "inputs": [confined_path(f) for f in inputs],
            "note": "USD stitch-clips ROP wired; run the write yourself"}


@endpoint("usd_zip")
def usd_zip(params):
    """WIRE-ONLY: build a USD Zip ROP (/out usdzip) that packages input USD layers into a .usdz archive
    — configured but NEVER executed. input_files = list of input .usd/.usda/.usdc/asset files (READ-
    confined); output = the .usdz output (WRITE-confined); arkit_asset = author an ARKit-compatible
    package. Returns {node, rendered:False}."""
    n = out_context().createNode("usdzip", params.get("name"))
    inputs = _as_list(params.get("input_files"))
    out_path = confined_path(params["output"]) if params.get("output") else None
    if inputs:
        _grow_multiparm(n, "zipfiles", len(inputs))
        for i, f in enumerate(inputs, start=1):
            _try_set(n, "enable%d" % i, True)
            _try_set(n, "infile%d" % i, confined_path(f))
            if out_path:
                _try_set(n, "outfile%d" % i, out_path)
            if "arkit_asset" in params:
                _try_set(n, "arkitasset%d" % i, bool(params["arkit_asset"]))
    elif out_path:
        _try_set(n, "outfile1", out_path)
    return {"node": n.path(), "rendered": False, "output": out_path,
            "inputs": [confined_path(f) for f in inputs],
            "note": "USD zip ROP wired; run the write yourself"}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# LOP editorial + USD constraints  (/stage operators; sequence-I/O file-confined)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _stage_node(ntype, name=None, after=None):
    """Create a LOP `ntype` in /stage, wired after `after` (a LOP path) if given, else a fresh
    generator in /stage. (Idiom copied verbatim from usd_author.py::_stage_node.)"""
    if after:
        src = resolve_node(after)
        parent = src.parent()
        n = parent.createNode(ntype, name) if name else parent.createNode(ntype)
        n.setInput(0, src)
    else:
        stage = stage_context()
        n = stage.createNode(ntype, name) if name else stage.createNode(ntype)
    n.moveToGoodPosition()
    return n


def _wire(n, idx, path):
    """Wire an extra LOP input at slot `idx` from a LOP path (probe-safe)."""
    if path:
        try:
            n.setInput(idx, resolve_node(str(path)))
            return True
        except Exception:  # noqa: BLE001
            return False
    return False


def _finish_lop(n):
    """Cook (compute the stage — NOT a save-to-disk) and read back authored prims minus
    HoudiniLayerInfo; degrade to cooked:false + errors when a required input is missing."""
    out = {"node": n.path()}
    try:
        n.cook(force=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        st = n.stage()
        out["prims"] = [str(p.GetPath()) for p in st.Traverse()
                        if str(p.GetPath()) != "/HoudiniLayerInfo"]
        out["cooked"] = True
    except Exception:  # noqa: BLE001
        out["cooked"] = False
    try:
        errs = list(n.errors())
        if errs:
            out["errors"] = errs
    except Exception:  # noqa: BLE001
        pass
    return out


_SAMPLE_BEHAVIOR = ("single", "timedep", "multi")


# ── shot editorial ──
@endpoint("shot_load")
def shot_load(params):
    """Load shot layers onto the /stage from the shot pipeline (shotload LOP) — the editorial entry
    point that populates a stage from configured shots. active_shots = the shot pattern to load;
    current_shot = the shot to make current; allow_direct_edit permits in-place edits. Generator;
    `input` (opt) layers onto an upstream stage. Data-only: no file path (shots resolve via the
    configured pipeline)."""
    n = _stage_node("shotload", params.get("name"), params.get("input"))
    _apply(n, params, [
        ("active_shots", "activeshots", "s", None),
        ("current_shot", "current_shot", "s", None),
        ("allow_direct_edit", "allowdirectedit", "b", None),
    ])
    return _finish_lop(n)


@endpoint("shot_output")
def shot_output(params):
    """WIRE-ONLY: build a Shot Output ROP LOP (shotoutput) that saves the stage to disk for a shot —
    configured but NEVER executed (the USER fires the write). Operator: `input` required. output =
    the USD output file (WRITE-confined); output_mode = render|publish|publishandrender; save_style =
    flattenimplicitlayers|flattenalllayers|separate|flattenstage; default_prim names the default prim;
    frames = [start,end]. The pre/post-render SCRIPT params are never exposed. Returns {node,
    rendered:False}."""
    n = _stage_node("shotoutput", params.get("name"), after=params["input"])
    out_path = None
    if params.get("output"):
        out_path = confined_path(params["output"])
        _try_set(n, "lopoutput", out_path)
    _apply(n, params, [
        ("output_mode", "outputmode", "ms", ("render", "publish", "publishandrender")),
        ("save_style", "savestyle", "ms",
         ("flattenimplicitlayers", "flattenalllayers", "separate", "flattenstage")),
        ("default_prim", "defaultprim", "s", None),
    ])
    frames = params.get("frames")
    if frames and len(frames) == 2:
        _try_set(n, "trange", 1)
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        _try_set(n, "f1", f1)
        _try_set(n, "f2", f2)
    return {"node": n.path(), "rendered": False, "output": out_path,
            "note": "shot-output LOP wired; run the save yourself"}


@endpoint("shot_layer_edit")
def shot_layer_edit(params):
    """Route stage edits into a specific shot layer (shotlayeredit LOP) — the editorial layer targeter.
    Operator: `input` required. active_shots = the shot pattern; target_layer / parent_layer name the
    destination + parent layers; create_new_layer + new_layer author a fresh layer. Data-only: layer
    NAMES only, no file path."""
    n = _stage_node("shotlayeredit", params.get("name"), after=params["input"])
    _apply(n, params, [
        ("active_shots", "lop_activeshots", "s", None),
        ("target_layer", "targetlayer", "s", None),
        ("parent_layer", "parentlayer", "s", None),
        ("create_new_layer", "createnewlayer", "b", None),
        ("new_layer", "newlayer", "s", None),
    ])
    return _finish_lop(n)


# ── USD sequence I/O (file-confined) ──
@endpoint("usd_value_clip")
def usd_value_clip(params):
    """Author a USD value-clip prim that streams animation from a set of clip files (valueclip LOP).
    primpath = the prim to hold the clip metadata; clip_files = the ordered clip .usd files (each
    READ-confined); manifest_file = the value-clip manifest (confined); clip_set / clip_prim_path name
    the clip set + source prim; start_time the playback start; clip_time_scale retimes the clips.
    Operator; `input` (opt) layers onto an upstream stage."""
    n = _stage_node("valueclip", params.get("name"), params.get("input"))
    clips = _as_list(params.get("clip_files"))
    if clips:
        _grow_multiparm(n, "clipfiles", len(clips))
        for i, f in enumerate(clips, start=1):
            _try_set(n, "clipfile%d" % i, confined_path(f))
    if params.get("manifest_file"):
        _try_set(n, "manifestfile", confined_path(params["manifest_file"]))
    if "clip_time_scale" in params:
        _try_set(n, "setcliptimescale", True)
    _apply(n, params, [
        ("primpath", "primpath", "s", None),
        ("clip_set", "clipset", "s", None),
        ("clip_prim_path", "clipprimpath", "s", None),
        ("start_time", "starttime", "f", (-1.0e6, 1.0e6)),
        ("clip_time_scale", "cliptimescale", "f", (0.0, 1.0e4)),
    ])
    return _finish_lop(n)


@endpoint("usd_geometry_sequence")
def usd_geometry_sequence(params):
    """Import an animated geometry-file SEQUENCE onto the stage (geometrysequence LOP) — the streaming
    read bridge for a per-frame .bgeo/.vdb/... cache. file = the geometry file/sequence (READ-confined;
    put a $F token for a sequence); missing_frame = error|empty; primpath = the USD destination;
    instanceable makes it instanceable; kind_authoring stamps a USD kind; packed_handling picks how
    packed prims are authored. Operator; `input` (opt) layers onto an upstream stage."""
    n = _stage_node("geometrysequence", params.get("name"), params.get("input"))
    if params.get("file"):
        _try_set(n, "file", confined_path(params["file"]))
    if "kind_authoring" in params:
        _try_set(n, "enable_kindschema", True)
    if "packed_handling" in params:
        _try_set(n, "enable_packedhandling", True)
    _apply(n, params, [
        ("missing_frame", "missingframe", "m", ("error", "empty")),
        ("primpath", "primpath", "s", None),
        ("instanceable", "instanceable", "b", None),
        ("kind_authoring", "kindschema", "ms",
         ("none", "component", "nestedgroup", "nestedassembly")),
        ("packed_handling", "packedhandling", "ms",
         ("xforms", "pointinstancer", "nativeinstances", "unpack")),
    ])
    return _finish_lop(n)


@endpoint("usd_geo_clip_sequence")
def usd_geo_clip_sequence(params):
    """Load / write a USD geometry value-clip sequence (geoclipsequence LOP) — the workhorse for
    caching an animated stage subtree to per-frame clip files and streaming it back. load_clip_file =
    the clip file to READ (confined); save_clip_file = where to WRITE the cache (confined); primpath =
    the target prim; sample_behavior = single|timedep|multi; start_frame/end_frame the range (+
    loop_frames); handle_missing = error|warn|ignore|allow. `input` = base stage; `geo_source` (opt
    LOP path) supplies geometry via the 2nd input (enables Get Geometry From Second Input)."""
    n = _stage_node("geoclipsequence", params.get("name"), params.get("input"))
    if params.get("geo_source"):
        _try_set(n, "usesecondinput", True)
        _wire(n, 1, params.get("geo_source"))
    if params.get("load_clip_file"):
        _try_set(n, "loadclipfilepath", confined_path(params["load_clip_file"]))
    if params.get("save_clip_file"):
        _try_set(n, "saveclipfilepath", confined_path(params["save_clip_file"]))
    if "end_frame" in params:
        _try_set(n, "setendframe", True)
    _apply(n, params, [
        ("primpath", "primpath", "s", None),
        ("sample_behavior", "sample_behavior", "ms", _SAMPLE_BEHAVIOR),
        ("handle_missing", "handlemissingfiles", "ms", ("error", "warn", "ignore", "allow")),
        ("start_frame", "startframe", "f", (-1.0e6, 1.0e6)),
        ("end_frame", "endframe", "f", (-1.0e6, 1.0e6)),
        ("loop_frames", "loopframes", "b", None),
        ("clip_set", "clipset", "s", None),
        ("clip_prim_path", "clipprimpath", "s", None),
    ])
    return _finish_lop(n)


# ── USD xform constraints (VEX/HScript snippet params DEFERRED — never exposed) ──
_XFORM_TOGGLES = [
    ("position", "position", "b", None), ("rotation", "rotation", "b", None),
    ("scale", "scale", "b", None), ("shear", "shear", "b", None),
    ("keep_offset", "keepoffset", "b", None),
]


@endpoint("usd_blend_constraint")
def usd_blend_constraint(params):
    """Author a USD Blend constraint — blend a prim's transform between source + target prims
    (blendconstraint LOP). Operator: `input` = the stage (required); `target_stage` (opt LOP) = the
    2nd input. source / target = the driven + driver prim paths; source_instances / target_instances
    for instancers; method (0/1) picks the blend method; rot_blend (0..3) the rotation-blend mode;
    import_time samples the source. Degrades to cooked:false if the referenced prims are absent."""
    n = _stage_node("blendconstraint", params.get("name"), after=params["input"])
    _wire(n, 1, params.get("target_stage"))
    _apply(n, params, [
        ("source", "source", "s", None), ("target", "target", "s", None),
        ("source_instances", "sourceinstances", "s", None),
        ("target_instances", "targetinstances", "s", None),
        ("method", "method", "i", (0, 1)),
        ("rot_blend", "rotblend", "i", (0, 3)),
        ("import_time", "importtime", "f", (-1.0e6, 1.0e6)),
    ])
    return _finish_lop(n)


@endpoint("usd_followpath_constraint")
def usd_followpath_constraint(params):
    """Author a USD Follow-Path constraint — slide a prim along a curve (followpathconstraint LOP).
    Operator: `input` = the stage (required); `target_stage` (opt LOP) = 2nd input. source = the
    driven prim; target = the path prim, OR sop_path = a SOP curve; pos = position along the path
    (0..1); doposition/dorotation/doscale/doshear + keep_offset gate what is constrained; look_at_mode
    (0..3) orients along the path. The interactive curve-EDIT widget + VEX snippet params are NOT
    exposed. Degrades to cooked:false if inputs are absent."""
    n = _stage_node("followpathconstraint", params.get("name"), after=params["input"])
    _wire(n, 1, params.get("target_stage"))
    _apply(n, params, [
        ("source", "source", "s", None), ("target", "target", "s", None),
        ("sop_path", "soppath", "s", None),
        ("pos", "pos", "f", (-1.0e6, 1.0e6)),
        ("clamp", "clamp", "b", None),
        ("doposition", "doposition", "b", None), ("dorotation", "dorotation", "b", None),
        ("doscale", "doscale", "b", None), ("doshear", "doshear", "b", None),
        ("keep_offset", "keepoffset", "b", None),
        ("look_at_mode", "lookatmode", "i", (0, 3)),
        ("import_time", "importtime", "f", (-1.0e6, 1.0e6)),
    ])
    return _finish_lop(n)


@endpoint("usd_lookat_constraint")
def usd_lookat_constraint(params):
    """Author a USD Look-At constraint — aim a prim at a target (lookatconstraint LOP). Operator:
    `input` = the stage (required); `target_stage` (opt LOP) = 2nd input. source = the aiming prim;
    target = the prim to look at, OR target_pos = [x,y,z]; look_at_axis (0..5) the forward axis; up =
    xaxis|yaxis|zaxis|fromprim|custom + up_vector [x,y,z]; twist rolls about the aim. Degrades to
    cooked:false if inputs are absent."""
    n = _stage_node("lookatconstraint", params.get("name"), after=params["input"])
    _wire(n, 1, params.get("target_stage"))
    if "target_pos" in params:
        _try_set_tuple(n, "targetpos", params["target_pos"], -1.0e7, 1.0e7)
    if "up_vector" in params:
        _try_set_tuple(n, "upvector", params["up_vector"], -1.0e6, 1.0e6)
    _apply(n, params, [
        ("source", "source", "s", None), ("target", "target", "s", None),
        ("look_at_axis", "lookataxis", "m", ("0", "1", "2", "3", "4", "5")),
        ("up", "up", "ms", ("xaxis", "yaxis", "zaxis", "fromprim", "custom")),
        ("twist", "twist", "f", (-3.6e3, 3.6e3)),
        ("hide_target", "hidetarget", "b", None),
        ("import_time", "importtime", "f", (-1.0e6, 1.0e6)),
    ])
    return _finish_lop(n)


@endpoint("usd_parent_constraint")
def usd_parent_constraint(params):
    """Author a USD Parent constraint — parent a prim's transform to a target (parentconstraint LOP).
    Operator: `input` = the stage (required); `target_stage` (opt LOP) = 2nd input. source = the driven
    prim; target = the parent prim; position/rotation/scale/shear gate the channels; keep_offset +
    rel_offset preserve the current offset; method = byframe|bytime + frame/time. Degrades to
    cooked:false if inputs are absent."""
    n = _stage_node("parentconstraint", params.get("name"), after=params["input"])
    _wire(n, 1, params.get("target_stage"))
    _apply(n, params, _XFORM_TOGGLES + [
        ("source", "source", "s", None), ("target", "target", "s", None),
        ("rel_offset", "reloffset", "b", None),
        ("method", "method", "ms", ("byframe", "bytime")),
        ("frame", "frame", "f", (-1.0e6, 1.0e6)),
        ("time", "time", "f", (-1.0e6, 1.0e6)),
        ("import_time", "importtime", "f", (-1.0e6, 1.0e6)),
    ])
    return _finish_lop(n)


@endpoint("usd_points_constraint")
def usd_points_constraint(params):
    """Author a USD Points constraint — constrain a prim to weighted points of a target
    (pointsconstraint LOP). Operator: `input` = the stage (required); `target_stage` (opt LOP) = 2nd
    input. source = the driven prim; target = the points prim; group restricts the points;
    position/rotation/scale/shear gate the channels; keep_offset preserves the offset; look_at_mode
    (0..4) orients. The VEX weights/roll snippet params are NOT exposed. Degrades to cooked:false if
    inputs are absent."""
    n = _stage_node("pointsconstraint", params.get("name"), after=params["input"])
    _wire(n, 1, params.get("target_stage"))
    _apply(n, params, _XFORM_TOGGLES + [
        ("source", "source", "s", None), ("target", "target", "s", None),
        ("group", "group", "s", None),
        ("mode", "mode", "i", (0, 1)),
        ("look_at_mode", "lookatmode", "i", (0, 4)),
        ("import_time", "importtime", "f", (-1.0e6, 1.0e6)),
    ])
    return _finish_lop(n)


@endpoint("usd_surface_constraint")
def usd_surface_constraint(params):
    """Author a USD Surface constraint — pin a prim to a UV location on a target surface
    (surfaceconstraint LOP). Operator: `input` = the stage (required); `target_stage` (opt LOP) = 2nd
    input. source = the driven prim; target = the surface prim; group restricts the surface; mode
    (0..4) the attach mode; uv_attribute + uv = [u,v] the attach coordinate;
    position/rotation/scale/shear gate the channels; keep_offset preserves the offset. The VEX
    position/roll snippet params are NOT exposed. Degrades to cooked:false if inputs are absent."""
    n = _stage_node("surfaceconstraint", params.get("name"), after=params["input"])
    _wire(n, 1, params.get("target_stage"))
    if "uv" in params:
        _try_set_tuple(n, "uv", params["uv"], -1.0e6, 1.0e6)
    _apply(n, params, _XFORM_TOGGLES + [
        ("source", "source", "s", None), ("target", "target", "s", None),
        ("group", "group", "s", None),
        ("mode", "mode", "i", (0, 4)),
        ("uv_attribute", "uvattribute", "s", None),
        ("import_time", "importtime", "f", (-1.0e6, 1.0e6)),
    ])
    return _finish_lop(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# CHOP anim-utility  (chopnet; channel/transform data params only)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _fresh_chopnet(name):
    """A fresh /obj chopnet. FAILS on name collision (never destroys existing user work)."""
    obj = hou.node("/obj")
    if name and obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)
    return obj.createNode("chopnet", name) if name else obj.createNode("chopnet")


def _gen_net(params):
    """Container for a GENERATOR CHOP: reuse the `chopnet` path if given (so several nodes share one
    network), else create a fresh chopnet from `name`."""
    if params.get("chopnet"):
        net = resolve_node(params["chopnet"])
        if net.childTypeCategory() != hou.chopNodeTypeCategory():
            raise ValueError("chopnet is not a CHOP network: %s" % params["chopnet"])
        return net
    return _fresh_chopnet(params.get("name"))


def _wire_extra(node, params, count):
    """Wire optional extra CHOP inputs input1..input<count> (siblings in the same chopnet, direct
    setInput — the SOP object_merge bridge does NOT apply to CHOP inputs)."""
    for i in range(1, count + 1):
        key = "input%d" % i
        if params.get(key):
            node.setInput(i, resolve_node(params[key]))


def _cooked(n):
    """Cook the CHOP and report track/sample counts + errors (the CHOP analogue of prims/points).
    A node still missing a required input legitimately fails to cook; both n.cook() and n.tracks()
    lazily cook and can raise, so BOTH are guarded → cooked:false + error text (mirrors chop_motion)."""
    try:
        n.cook(force=True)
    except hou.OperationFailed:
        pass
    try:
        tracks = n.tracks()
        ntracks = len(tracks)
        samples = len(tracks[0].allSamples()) if tracks else 0
    except hou.OperationFailed:
        ntracks, samples = 0, 0
    try:
        errs = list(n.errors())
    except Exception:  # noqa: BLE001
        errs = []
    return {"node": n.path(), "chopnet": n.parent().path(), "cooked": ntracks > 0,
            "tracks": ntracks, "samples": samples, "errors": errs}


_SRSELECT = ("first", "max", "min", "err")
_EXTEND = ("hold", "slope", "cycle", "mirror", "default", "cyclestep")


@endpoint("chop_footplant")
def chop_footplant(params):
    """CHOP Foot Plant (footplant) — detect + lock foot contacts in a walk animation to kill sliding.
    OPERATOR: chained onto an `input` CHOP. source = input|object|agent; sop_path a skeleton SOP;
    method = speed|distance with speed_threshold / distance_threshold; channel_name names the plant
    channel; blend_in / blend_out frames ease the lock. Data-only (channel math)."""
    n = child_after(params["input"], "footplant", params.get("name"))
    _apply(n, params, [
        ("source", "source", "m", ("input", "object", "agent")),
        ("sop_path", "soppath", "s", None),
        ("group", "group", "s", None),
        ("method", "method", "m", ("speed", "distance")),
        ("speed_threshold", "speedthreshold", "f", (0.0, 1.0e4)),
        ("distance_threshold", "distancethreshold", "f", (0.0, 1.0e4)),
        ("channel_name", "channelname", "s", None),
        ("blend_in", "blendinframes", "i", (0, 1000)),
        ("blend_out", "blendoutframes", "i", (0, 1000)),
        ("scope", "scope", "s", None),
    ])
    return _cooked(n)


@endpoint("chop_iksolver")
def chop_iksolver(params):
    """CHOP IK Solver (iksolver) — solve a bone chain to reach an end affector. OPERATOR: chained onto
    an `input` CHOP; input1/input2 wire aux CHOPs. solver_type = inverse|constraint; chain_names the
    joints; end_affector / twist_affector the goal + twist targets; ik_twist / ik_dampen / blend shape
    the solve. Data-only (transform channels)."""
    n = child_after(params["input"], "iksolver", params.get("name"))
    _wire_extra(n, params, 2)
    _apply(n, params, [
        ("solver_type", "solvertype", "m", ("inverse", "constraint")),
        ("chain_names", "chainnames", "s", None),
        ("end_affector", "endaffectorname", "s", None),
        ("twist_affector", "twistaffectorname", "s", None),
        ("ik_twist", "iktwist", "f", (-3.6e3, 3.6e3)),
        ("ik_dampen", "ikdampen", "f", (0.0, 1.0e3)),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("scope", "scope", "s", None),
    ])
    return _cooked(n)


@endpoint("chop_inversekin")
def chop_inversekin(params):
    """CHOP Inverse Kinematics (inversekin) — the classic bone-chain IK solver driven by OBJ bone
    paths. GENERATOR: builds in a fresh (or supplied `chopnet`) network, references bones by path.
    solver_type = rest|capture|inverse|constraint|curve; root_bone / end_bone the chain ends;
    end_affector / twist_affector the goals; ik_twist / ik_dampen / blend shape the solve. Data-only."""
    n = _gen_net(params).createNode("inversekin")
    _apply(n, params, [
        ("solver_type", "solvertype", "m", ("rest", "capture", "inverse", "constraint", "curve")),
        ("root_bone", "bonerootpath", "s", None),
        ("end_bone", "boneendpath", "s", None),
        ("end_affector", "endaffectorpath", "s", None),
        ("twist_affector", "twistaffectorpath", "s", None),
        ("ik_twist", "iktwist", "f", (-3.6e3, 3.6e3)),
        ("ik_dampen", "ikdampen", "f", (0.0, 1.0e3)),
        ("blend", "blend", "f", (0.0, 1.0)),
        ("scope", "scope", "s", None),
    ])
    return _cooked(n)


@endpoint("chop_transform_chain")
def chop_transform_chain(params):
    """CHOP Transform Chain (transformchain) — recompose a chain of transforms into output channels.
    OPERATOR: chained onto an `input` CHOP. chain_names the joints; in_xord/in_rord + out_xord/out_rord
    set the input / output transform + rotation orders. Data-only (transform channels)."""
    n = child_after(params["input"], "transformchain", params.get("name"))
    _apply(n, params, [
        ("chain_names", "chainnames", "s", None),
        ("in_xord", "inxOrd", "m", _XORD),
        ("in_rord", "inrOrd", "m", _RORD),
        ("out_xord", "outxOrd", "m", _XORD),
        ("out_rord", "outrOrd", "m", _RORD),
        ("scope", "scope", "s", None),
    ])
    return _cooked(n)


@endpoint("chop_export_transforms")
def chop_export_transforms(params):
    """CHOP Export Transforms (exporttransforms) — map transform channels to OBJ node parameters.
    OPERATOR: chained onto an `input` CHOP. mode = xform|trs; node = the Transforms OP path; map = a
    Mappings OP path; enable_exports toggles the export writeback (off by default — this authors the
    mapping data, the USER enables the writeback). Data-only (channel->parm mapping; no code/file)."""
    n = child_after(params["input"], "exporttransforms", params.get("name"))
    _apply(n, params, [
        ("enable_exports", "enable", "b", None),
        ("mode", "mode", "m", ("xform", "trs")),
        ("node", "node", "s", None),
        ("map", "map", "s", None),
        ("scope", "scope", "s", None),
    ])
    return _cooked(n)


@endpoint("chop_extract_bone_transforms")
def chop_extract_bone_transforms(params):
    """CHOP Extract Bone Transforms (extractbonetransforms) — read a KineFX skeleton's bone transforms
    into channels. GENERATOR: builds in a fresh (or supplied `chopnet`) network. geo_path = the
    geometry (skeleton) node; skel_root = the skeleton root path; world_transforms = world vs local
    space; absolute_paths for channel paths; range = full|frame|user + start/end. Data-only."""
    n = _gen_net(params).createNode("extractbonetransforms")
    _apply(n, params, [
        ("geo_path", "geoobjpath", "s", None),
        ("skel_root", "skelrootpath", "s", None),
        ("world_transforms", "worldtransforms", "b", None),
        ("absolute_paths", "absolutepaths", "b", None),
        ("range", "range", "m", ("full", "frame", "user")),
        ("start", "start", "f", (-1.0e6, 1.0e6)),
        ("end", "end", "f", (-1.0e6, 1.0e6)),
        ("scope", "scope", "s", None),
    ])
    return _cooked(n)


@endpoint("chop_extract_pose_drivers")
def chop_extract_pose_drivers(params):
    """CHOP Extract Pose Drivers (extractposedrivers) — extract driver channels (joint xforms / parms)
    that feed a pose-space deformer. GENERATOR: builds in a fresh (or supplied `chopnet`) network.
    geo_path = the geometry node; skel_root = the skeleton root; channel_prefix names the outputs;
    range = full|frame|user + start/end. (The per-driver multiparm is left at default — drive it in the
    UI.) Data-only."""
    n = _gen_net(params).createNode("extractposedrivers")
    _apply(n, params, [
        ("geo_path", "geopath", "s", None),
        ("skel_root", "skelrootpath", "s", None),
        ("channel_prefix", "channelnameprefix", "s", None),
        ("range", "range", "m", ("full", "frame", "user")),
        ("start", "start", "f", (-1.0e6, 1.0e6)),
        ("end", "end", "f", (-1.0e6, 1.0e6)),
        ("scope", "scope", "s", None),
    ])
    return _cooked(n)


@endpoint("chop_blendpose")
def chop_blendpose(params):
    """CHOP Blend Pose (blendpose) — pose-space interpolation (RBF / hyperplane) that blends example
    poses by driver values. OPERATOR: chained onto an `input` CHOP; input1/input2 wire aux CHOPs.
    interp = rbf|hyperplane; kernel = thinplate|biharmonic|cauchy|gaussian|...; interpolation =
    siauto|sibyposes|sibychannels; clamp_input; exponent; falloff; solver = cholesky|svd; damping;
    max_iterations. Data-only (channel math)."""
    n = child_after(params["input"], "blendpose", params.get("name"))
    _wire_extra(n, params, 2)
    _apply(n, params, [
        ("interp", "interp", "m", ("rbf", "hyperplane")),
        ("kernel", "kernel", "m", ("thinplate", "biharmonic", "cauchy", "gaussian",
                                    "multiquadric", "invmultiquadric", "expbump")),
        ("interpolation", "interpolation", "m", ("siauto", "sibyposes", "sibychannels")),
        ("clamp_input", "clampinput", "b", None),
        ("exponent", "exp", "i", (0, 100)),
        ("falloff", "falloff", "f", (0.0, 1.0e3)),
        ("solver", "solver", "m", ("cholesky", "svd")),
        ("damping", "damping", "f", (0.0, 1.0e3)),
        ("max_iterations", "maxiterations", "i", (0, 100000)),
        ("scope", "scope", "s", None),
    ])
    return _cooked(n)


@endpoint("chop_stashpose")
def chop_stashpose(params):
    """CHOP Stash Pose (stashpose) — stash the current pose as a static reference pose for pose-space
    workflows. OPERATOR: chained onto an `input` CHOP; input1/input2 wire aux CHOPs. scope selects the
    channels; srselect reconciles sample rates. Data-only (channel snapshot; no file/code)."""
    n = child_after(params["input"], "stashpose", params.get("name"))
    _wire_extra(n, params, 2)
    _apply(n, params, [
        ("scope", "scope", "s", None),
        ("srselect", "srselect", "m", _SRSELECT),
    ])
    return _cooked(n)

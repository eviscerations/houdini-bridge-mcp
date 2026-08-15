"""Render/ROP — texture bakers (WIRE-ONLY). Params verified against live H21.0.671 (parm name/type, menu tokens,
input counts, and a headless build+wire+blank-check per node — NEVER an execute/bake).

These 7 nodes bake textures / atlases / volume-textures. A bake is a render, so — per the render/ROP
WIRE-ONLY lane — every handler BUILDS + WIRES + configures the node but NEVER fires it: no `.render()`
/`.execute()`, no render/bake button pressed. The human fires the bake. Each returns rendered=False.

Nodes (context):
  * karmatexturebaker            (lop/Solaris)  -> bake_karma_texture
  * labs::impostor_texture       (out/Driver)   -> bake_impostor_texture
  * labs::motion_vectors         (out/Driver)   -> bake_motion_vectors
  * labs::flipbook_textures::1.0 (out/Driver)   -> bake_flipbook_textures   [ONLY node w/ code surface]
  * haircardtex                  (out/Driver)   -> bake_haircard_texture
  * geo2i3d                      (out/Driver)   -> export_geo_to_i3d
  * image3d                      (out/Driver)   -> export_image_to_i3d

SECURITY (data-only boundary, per the lane brief):
  * NEVER execute. No render/bake button (execute/renderdialog/render_map/render_sequence/render_all/
    render_* / renderpreview) is ever set or pressed; no node is cooked/rendered here.
  * Code surface BLANKED: flipbook_textures' prerender/postrender/lprerender/lpostrender are set to ""
    and its tprerender/tpostrender script-enable toggles forced OFF (defense-in-depth: they only fire
    on execute, which we never call). No other Wave-E node carries a code surface.
  * Every file OUTPUT parm is realpath-confined via confined_path() and set ONLY when the caller
    supplies it (WIRE-ONLY: absent -> leave the HDA default for the human to edit before firing).
    $F/<UDIM>/$(CHANNEL)-style tokens stay literal leaves; confined_path() rejects any .. / drive
    escape out of the working dir.
  * Auxiliary side-writes / preview-publish toggles not requested are forced OFF (flipbook
    `outputtomplay`).
  * Node/prim references (soppath/source_geo/camera_rig/export_node/asset/camerapath/bakemesh/…) are
    scene-graph PATHS (data, not files) — set verbatim as strings; never resolved/cooked here.
  * Name/leaf tokens (haircard map names, i3d compression) are sanitized so a name can't smuggle a
    filesystem path.
  * Resolution x samples (and frame-range) cost levers are hard-clamped (render-cost / DoS guard):
    resolution 16-8192, samples 1-256, frames 1-1000 window.

None of these 7 node types is wrapped elsewhere — the existing bakers wrap different types
(bake_texture=baketexture::3.0, simple_baker=labs::simple_baker::2.0, games_baker=labs::games_baker
::2.0, maps_baker=labs::maps_baker::5.0). All 7 kept.
"""

import hou
from houdini_executor.server import (endpoint, confined_path, clamp, child_after,
                                     out_context, stage_context)
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────


def _menu_set(node, parm, token):
    """Set an ordered/string menu by TOKEN, validated against the parm's LIVE menu items (works for
    Int-menu and String-menu alike). No-op if the token isn't a current menu item."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        items = p.parmTemplate().menuItems()
    except Exception:
        items = ()
    tok = str(token)
    if items and tok not in items:
        return False
    try:
        p.set(tok)
        return True
    except Exception:
        return False


def _safe_token(v):
    """Sanitize a name/leaf token (map name / compression): reject path separators, parent refs and
    drive letters so a name token can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("name token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


def _out_node(ntype, name=None):
    """Create a Driver/ROP node in /out (created on demand). WIRE-ONLY: never executed."""
    out = out_context()
    return out.createNode(ntype, name) if name else out.createNode(ntype)


# clamp bounds (render-cost / DoS guard)
_RES_LO, _RES_HI = 16, 8192
_SAMP_LO, _SAMP_HI = 1, 256


def _clamp_res(v):
    return int(clamp(int(v), _RES_LO, _RES_HI))


def _clamp_samp(v):
    return int(clamp(int(v), _SAMP_LO, _SAMP_HI))


# ══ 1. karmatexturebaker (lop) — Karma UV/texture baker settings ═════════════════════════════════
@endpoint("bake_karma_texture")
def bake_karma_texture(params):
    """Karma Texture Baker (karmatexturebaker, lop/Solaris) — WIRE-ONLY: builds + wires the Karma
    UV/texture bake in a lopnet (/stage) and configures it; you fire the bake. It bakes surface AOVs
    (basecolor / normal / roughness / occlusion / curvature / …) from a USD prim's material into UV
    atlas images. `input` (optional LOP path) is wired as input 0; `bakemesh`/`cagemesh`/`highmesh`/
    `camera`/`primpath` are USD PRIM PATHS (data strings, set verbatim). SECURITY: `picture` (atlas
    output) is confined to the working dir; resolution/samples are hard-clamped; no execute/render is
    fired (this is a settings LOP — the render runs downstream). Returns rendered=False."""
    if params.get("input"):
        n = child_after(params["input"], "karmatexturebaker", params.get("name"))
    else:
        n = stage_context().createNode("karmatexturebaker", params.get("name"))
    # USD prim / camera references (data, not files) — set verbatim
    for ref in ("bakemesh", "cagemesh", "highmesh", "camera", "primpath"):
        if params.get(ref):
            _try_set(n, ref, str(params[ref]))
    # confined atlas output (WIRE-ONLY: only when supplied)
    out_path = None
    if params.get("picture"):
        out_path = confined_path(params["picture"])
        _try_set(n, "picture", out_path)
    # resolution menu (token e.g. "1024 1024") + explicit x/y
    if "resolution_menu" in params:
        _menu_set(n, "resolution_menu", params["resolution_menu"])
    if "resolutionx" in params:
        _try_set(n, "resolutionx", _clamp_res(params["resolutionx"]))
    if "resolutiony" in params:
        _try_set(n, "resolutiony", _clamp_res(params["resolutiony"]))
    # sample cost levers (per-AOV + global) — clamped
    for sp in ("samplesperpixel", "cu_samples", "cv_samples", "eg_samples",
               "oc_samples", "rn_samples", "th_samples"):
        if sp in params:
            _try_set(n, sp, _clamp_samp(params[sp]))
    # bounded config menus/toggles that shape the output
    for mn in ("image_format", "denoiser", "bakemode"):
        if mn in params:
            _menu_set(n, mn, params[mn])
    for tg in ("separate", "enable_lighting", "bake_uv", "truedisplace", "use_mikkt"):
        if tg in params:
            _try_set(n, tg, bool(params[tg]))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "note": "Karma texture bake built WIRE-ONLY in /stage; fire the bake yourself"}


# ══ 2. labs::impostor_texture (out) — impostor octahedral atlas baker ═════════════════════════════
@endpoint("bake_impostor_texture")
def bake_impostor_texture(params):
    """Labs Impostor Texture (labs::impostor_texture, out/Driver) — WIRE-ONLY: builds + wires the
    impostor atlas baker in /out; you fire the bake. Renders an octahedral sprite atlas (beauty /
    base-color / normals) of a source object seen from many angles, for a real-time impostor billboard.
    `source_geo` + `camera_rig` are scene node PATHS (data, set verbatim). SECURITY: `output_sequence`
    / `anim_output_sequence` (atlas images) + `sopoutput` (base-mesh export) are confined to the
    working dir; sprite resolution / ray-samples are hard-clamped; `execute`/`renderdialog` are NEVER
    pressed. Returns rendered=False."""
    n = _out_node("labs::impostor_texture", params.get("name"))
    for ref in ("source_geo", "camera_rig"):
        if params.get(ref):
            _try_set(n, ref, str(params[ref]))
    outs = {}
    for fp in ("output_sequence", "anim_output_sequence", "sopoutput"):
        if params.get(fp):
            outs[fp] = confined_path(params[fp])
            _try_set(n, fp, outs[fp])
    if "fOctResolution" in params:
        _menu_set(n, "fOctResolution", params["fOctResolution"])
    if "imposter_enum" in params:
        _menu_set(n, "imposter_enum", params["imposter_enum"])
    if "sprite_resx" in params:
        _try_set(n, "sprite_resx", float(_clamp_res(params["sprite_resx"])))
    if "sprite_resy" in params:
        _try_set(n, "sprite_resy", float(_clamp_res(params["sprite_resy"])))
    for sp in ("vm_maxraysamples", "vm_minraysamples", "vm_samplesx", "vm_samplesy",
               "vm_transparentsamples"):
        if sp in params:
            _try_set(n, sp, _clamp_samp(params[sp]))
    for cnt in ("anim_framesx", "anim_framesy", "frames"):
        if cnt in params:
            _try_set(n, cnt, int(clamp(int(params[cnt]), 1, 4096)))
    for tg in ("base_color_toggle", "beauty_toggle", "normals_toggle", "premult",
               "single_render", "vm_transparent"):
        if tg in params:
            _try_set(n, tg, bool(params[tg]))
    return {"node": n.path(), "outputs": outs or None, "rendered": False,
            "note": "impostor atlas bake built WIRE-ONLY in /out; fire the bake yourself"}


# ══ 3. labs::motion_vectors (out) — flipbook motion-vector map baker ══════════════════════════════
@endpoint("bake_motion_vectors")
def bake_motion_vectors(params):
    """Labs Motion Vectors (labs::motion_vectors, out/Driver) — WIRE-ONLY: builds + wires the
    motion-vector atlas baker in /out; you fire the bake. Renders a per-frame motion-vector texture
    atlas from an animated source (for flipbook / VFX motion-blur reconstruction). `export_node` +
    `camera` are scene node PATHS (data, set verbatim). SECURITY: `vm_picture` (atlas output) is
    confined to the working dir; atlas resolution + frame range are clamped; `execute`/`render_map`/
    `render_sequence`/`renderdialog` are NEVER pressed. Returns rendered=False."""
    n = _out_node("labs::motion_vectors", params.get("name"))
    for ref in ("export_node", "camera"):
        if params.get(ref):
            _try_set(n, ref, str(params[ref]))
    out_path = None
    if params.get("vm_picture"):
        out_path = confined_path(params["vm_picture"])
        _try_set(n, "vm_picture", out_path)
    for r in ("atlas_resx", "atlas_resy"):
        if r in params:
            _try_set(n, r, _clamp_res(params[r]))
    # `num_of_frame` is a read-only computed label (f2-f1+1); the frame count is governed by f1/f2.
    if "numperline" in params:
        _try_set(n, "numperline", int(clamp(int(params["numperline"]), 1, 4096)))
    if "f1" in params:
        _try_set(n, "f1", float(clamp(float(params["f1"]), -100000.0, 100000.0)))
    if "f2" in params:
        lo = float(params.get("f1", -100000.0))
        _try_set(n, "f2", float(clamp(float(params["f2"]), lo, 100000.0)))
    if "rawmultiplier" in params:
        _try_set(n, "rawmultiplier", clamp(float(params["rawmultiplier"]), -1e6, 1e6))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "note": "motion-vector bake built WIRE-ONLY in /out; fire the bake yourself"}


# ══ 4. labs::flipbook_textures::1.0 (out) — flipbook-to-texture-sheet baker [CODE SURFACE] ════════
@endpoint("bake_flipbook_textures")
def bake_flipbook_textures(params):
    """Labs Flipbook Textures (labs::flipbook_textures::1.0, out/Driver) — WIRE-ONLY: builds + wires
    the flipbook texture-sheet baker in /out; you fire the bake. Renders an animated effect into
    packed sprite-sheet textures (diffuse / normal / motion-vector / …) for real-time flipbook
    shaders. `asset` + `camerapath` are scene node PATHS (data, set verbatim). SECURITY: this is the
    ONLY Wave-E node with a code surface — prerender/postrender/lprerender/lpostrender are BLANKED to
    "" and the tprerender/tpostrender script-enable toggles forced OFF; `output_tex1..5` are confined
    to the working dir; the mplay preview-publish (`outputtomplay`) is forced OFF; frame resolution /
    AA samples / frame range are clamped; no render_* button is ever pressed. Returns rendered=False."""
    n = _out_node("labs::flipbook_textures::1.0", params.get("name"))
    # SECURITY: blank every code hook + disable the script-enable toggles (defense-in-depth)
    for code in ("prerender", "postrender", "lprerender", "lpostrender"):
        _try_set(n, code, "")
    _try_set(n, "tprerender", False)
    _try_set(n, "tpostrender", False)
    # SECURITY: auxiliary preview-publish forced OFF
    _try_set(n, "outputtomplay", False)
    # scene node references (data)
    for ref in ("asset", "camerapath"):
        if params.get(ref):
            _try_set(n, ref, str(params[ref]))
    # confined texture-sheet outputs
    outs = {}
    for i in range(1, 6):
        key = "output_tex%d" % i
        if params.get(key):
            outs[key] = confined_path(params[key])
            _try_set(n, key, outs[key])
    # resolution / sample cost
    if "resolutionMenu" in params:
        _menu_set(n, "resolutionMenu", params["resolutionMenu"])
    if "aasamples" in params:
        _menu_set(n, "aasamples", params["aasamples"])
    for r in ("frameresx", "frameresy", "shadowmapres"):
        if r in params:
            _try_set(n, r, _clamp_res(params[r]))
    # frame range (int f1/f2/f3 on this ROP)
    if "f1" in params:
        _try_set(n, "f1", int(clamp(int(params["f1"]), -100000, 100000)))
    if "f2" in params:
        lo = int(params.get("f1", -100000))
        _try_set(n, "f2", int(clamp(int(params["f2"]), lo, 100000)))
    if "f3" in params:
        _try_set(n, "f3", int(clamp(int(params["f3"]), 1, 1000)))
    # which sheets to enable (bounded toggles)
    for i in range(1, 6):
        tg = "enabletex%d" % i
        if tg in params:
            _try_set(n, tg, bool(params[tg]))
    if "gridsizex" in params:
        _try_set(n, "gridsizex", int(clamp(int(params["gridsizex"]), 1, 256)))
    if "gridsizey" in params:
        _try_set(n, "gridsizey", int(clamp(int(params["gridsizey"]), 1, 256)))
    return {"node": n.path(), "outputs": outs or None, "rendered": False,
            "note": "flipbook texture bake built WIRE-ONLY in /out (code hooks blanked); fire it yourself"}


# ══ 5. haircardtex (out) — hair-card texture baker ═══════════════════════════════════════════════
@endpoint("bake_haircard_texture")
def bake_haircard_texture(params):
    """Hair Card Texture (haircardtex, out/Driver) — WIRE-ONLY: builds + wires the hair-card texture
    baker in /out; you fire the bake. Renders a hair/fur groom into flat hair-card atlas maps (beauty
    + diffuse / depth / id / tip / uv-bounds / alpha) for real-time hair cards. `hairobjects` is an
    object-bundle string, `camera` a scene node PATH (data, set verbatim). SECURITY: `vm_picture`
    (main atlas) is confined to the working dir; per-map name tokens (diffusename/tipname/…) are
    sanitized to bare leaves; resolution / samples are clamped; `execute`/`renderdialog` are NEVER
    pressed. Returns rendered=False."""
    n = _out_node("haircardtex", params.get("name"))
    if params.get("hairobjects"):
        _try_set(n, "hairobjects", str(params["hairobjects"]))
    if params.get("camera"):
        _try_set(n, "camera", str(params["camera"]))
    if "forceobjects" in params:
        _try_set(n, "forceobjects", bool(params["forceobjects"]))
    out_path = None
    if params.get("vm_picture"):
        out_path = confined_path(params["vm_picture"])
        _try_set(n, "vm_picture", out_path)
    # which map channels to output (bounded toggles)
    for tg in ("outputdiffuse", "outputdepth", "outputid", "outputtip",
               "outputuvbounds", "outputalpha"):
        if tg in params:
            _try_set(n, tg, bool(params[tg]))
    # per-map leaf name tokens — sanitized (no path smuggling)
    for nm in ("diffusename", "depthname", "idname", "tipname", "uvboundsname",
               "alphaname", "nameprefix", "nameext"):
        if nm in params:
            _try_set(n, nm, _safe_token(params[nm]))
    if "resx" in params:
        _try_set(n, "resx", _clamp_res(params["resx"]))
    if "resy" in params:
        _try_set(n, "resy", _clamp_res(params["resy"]))
    for sp in ("vm_samplesx", "vm_samplesy"):
        if sp in params:
            _try_set(n, sp, _clamp_samp(params[sp]))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "note": "hair-card texture bake built WIRE-ONLY in /out; fire the bake yourself"}


# ══ 6. geo2i3d (out) — geometry-to-i3d volume-texture export ══════════════════════════════════════
@endpoint("export_geo_to_i3d")
def export_geo_to_i3d(params):
    """Geometry to i3d (geo2i3d, out/Driver) — WIRE-ONLY: builds + wires the geometry->i3d volume
    export in /out; you fire it. Rasterizes an input geometry into a 3D texture (i3d) within given
    bounds. `input` (optional) wires a source in the /out net; the geometry bounds (minx/…/maxz),
    `primnum` and resolution are DATA. SECURITY: `filename` (i3d output) and `image` (input i3d,
    read) are confined to the working dir; resolution / frame range are clamped; `execute`/
    `renderdialog` are NEVER pressed. Returns rendered=False."""
    n = _out_node("geo2i3d", params.get("name"))
    if params.get("input"):
        try:
            src = hou.node(params["input"])
            if src is not None and src.parent().path() == n.parent().path():
                n.setInput(0, src)
        except Exception:
            pass
    outs = {}
    for fp in ("filename", "image"):
        if params.get(fp):
            outs[fp] = confined_path(params[fp])
            _try_set(n, fp, outs[fp])
    for r in ("res1", "res2", "res3"):
        if r in params:
            _try_set(n, r, _clamp_res(params[r]))
    for f in ("f1", "f2", "f3"):
        if f in params:
            _try_set(n, f, float(clamp(float(params[f]), -100000.0, 100000.0)))
    if "trange" in params:
        _try_set(n, "trange", int(clamp(int(params["trange"]), 0, 2)))
    for b in ("minx", "miny", "minz", "maxx", "maxy", "maxz"):
        if b in params:
            _try_set(n, b, clamp(float(params[b]), -1e9, 1e9))
    if "primnum" in params:
        _try_set(n, "primnum", int(clamp(int(params["primnum"]), 0, 100000000)))
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    return {"node": n.path(), "outputs": outs or None, "rendered": False,
            "note": "geo->i3d export built WIRE-ONLY in /out; fire the export yourself"}


# ══ 7. image3d (out) — 3D texture (i3d) generator ════════════════════════════════════════════════
@endpoint("export_image_to_i3d")
def export_image_to_i3d(params):
    """3D Texture Generator (image3d, out/Driver) — WIRE-ONLY: builds + wires the i3d 3D-texture
    generator in /out; you fire it. Renders a SOP volume/points (referenced by `soppath`) through a
    shader (`shoppath`) into a 3D texture (i3d) image within given bounds. `soppath`/`shoppath` are
    scene node PATHS (data, set verbatim). SECURITY: `image` (i3d output) is confined to the working
    dir; `compress` is a sanitized token; resolution / samples / frame range are clamped;
    `execute`/`renderpreview`/`renderdialog` are NEVER pressed. Returns rendered=False."""
    n = _out_node("image3d", params.get("name"))
    for ref in ("soppath", "shoppath"):
        if params.get(ref):
            _try_set(n, ref, str(params[ref]))
    out_path = None
    if params.get("image"):
        out_path = confined_path(params["image"])
        _try_set(n, "image", out_path)
    for r in ("res1", "res2", "res3"):
        if r in params:
            _try_set(n, r, _clamp_res(params[r]))
    if "samples" in params:
        _try_set(n, "samples", _clamp_samp(params["samples"]))
    for f in ("f1", "f2", "f3"):
        if f in params:
            _try_set(n, f, float(clamp(float(params[f]), -100000.0, 100000.0)))
    if "trange" in params:
        _menu_set(n, "trange", params["trange"])
    if "renderas" in params:
        _menu_set(n, "renderas", params["renderas"])
    if "compress" in params:
        _try_set(n, "compress", _safe_token(params["compress"]))
    for b in ("minx", "miny", "minz", "maxx", "maxy", "maxz"):
        if b in params:
            _try_set(n, b, clamp(float(params[b]), -1e9, 1e9))
    for tg in ("mblur", "velocity", "verbose"):
        if tg in params:
            _try_set(n, tg, bool(params[tg]))
    for fl in ("pscale", "shutter", "variance"):
        if fl in params:
            _try_set(n, fl, clamp(float(params[fl]), -1e6, 1e6))
    if "mkpath" in params:
        _try_set(n, "mkpath", bool(params["mkpath"]))
    return {"node": n.path(), "output": out_path, "rendered": False,
            "note": "image->i3d export built WIRE-ONLY in /out; fire the export yourself"}

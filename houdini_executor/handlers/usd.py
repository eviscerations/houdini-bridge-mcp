"""Solaris / LOP / USD stage handlers. Params verified against live H21.0.671 nodes
(probe: reference->reference::2.0, domelight->domelight::3.0; light/camera transform + light
intensity/exposure/color carry USD-attribute-backed param names). All are data-shaped, fixed
node-type wrappers. Render nodes are WIRE-ONLY (the human fires the render).
"""

from houdini_executor.server import (
    endpoint, resolve_node, clamp, confined_path, stage_context,
)
from houdini_executor.handlers._parmutil import _try_set




# ── USD-attribute (mangled xn__...) parm authoring ───────────────────────────
# Solaris light/camera parms that back a USD attribute are name-mangled: `xn__inputs<attr>_<hash>`
# plus a companion `xn__inputs<attr>_control_<hash>` string parm that gates whether the attribute is
# authored ('set' = author, 'none' = leave stage default). The <hash> suffix is BUILD-FRAGILE, so we
# locate parms by the stable readable middle (the `needle`) rather than the exact mangled name. The
# trailing '_' in the match key keys off the attribute boundary so 'shadowfalloff' does not also grab
# 'shadowfalloffGamma'. All setters are guarded no-ops when the parm is absent on this build.
def _lop_val_parm(node, needle):
    """Return the VALUE parm whose name embeds `needle` (skipping its _control companion), or None."""
    key = needle.lower() + "_"
    ck = needle.lower() + "_control"
    for p in node.parms():
        n = p.name().lower()
        if ck in n:
            continue
        if key in n:
            return p
    return None


def _lop_ctrl_parm(node, needle):
    """Return the `_control` companion parm for `needle`, or None."""
    ck = needle.lower() + "_control"
    for p in node.parms():
        if ck in p.name().lower():
            return p
    return None


def _lop_author(node, needle, value):
    """Author a mangled scalar/toggle/string USD parm: flip its _control to 'set', then set the
    value. Returns True iff the value parm was found and set. Guarded (never raises)."""
    vp = _lop_val_parm(node, needle)
    if vp is None:
        return False
    cp = _lop_ctrl_parm(node, needle)
    if cp is not None:
        try:
            cp.set("set")
        except Exception:
            pass
    try:
        vp.set(value)
        return True
    except Exception:
        return False


def _lop_author_tuple(node, needle, values):
    """Author a mangled tuple (e.g. color3f) USD parm: flip _control to 'set', then set the tuple."""
    cp = _lop_ctrl_parm(node, needle)
    if cp is not None:
        try:
            cp.set("set")
        except Exception:
            pass
    key = needle.lower() + "_"
    ck = needle.lower() + "_control"
    for pt in node.parmTuples():
        n = pt.name().lower()
        if ck in n:
            continue
        if key in n:
            try:
                pt.set(tuple(values))
                return True
            except Exception:
                return False
    return False


def _set_vec(node, base, values):
    """Set a plain (non-mangled) tuple parm like `color`/`t`/`r`/`s` by its base name. Probe-safe."""
    pt = node.parmTuple(base)
    if pt is None:
        return False
    try:
        pt.set(tuple(float(v) for v in values))
        return True
    except Exception:
        return False


def _stage_node(ntype, name=None, after=None):
    """Create a LOP `ntype` in /stage, wired after `after` (a LOP path) if given, else a fresh
    generator in /stage."""
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


@endpoint("sop_import")
def sop_import(params):
    """Bring a SOP network's geometry onto the USD stage — the SOP->Solaris bridge.

    soppath = the SOP to import; input (opt) = a LOP to layer onto.
    Prim layout: pathprefix (opt) sets the destination stage-path root; pathattr (opt) reads the
    per-prim USD path from a geometry attribute (e.g. 'path,name') — enables it; partitionattribs
    (opt) splits the imported geo into named prims by attribute value (makes a scanned venue
    addressable on the stage) — enables it. polygonsassubd (opt bool) imports polygons as USD
    subdivision surfaces (enables the toggle). Back-compat: all prior params behave unchanged.
    (Probed H21.0.671: sopimport has NO `import_time_dependent` parm on this build — not exposed.)"""
    src = resolve_node(params["soppath"])
    n = _stage_node("sopimport", params.get("name"), params.get("input"))
    n.parm("soppath").set(src.path())
    if params.get("pathprefix"):
        _try_set(n, "enable_pathprefix", True)
        _try_set(n, "pathprefix", str(params["pathprefix"]))
    if params.get("pathattr"):
        _try_set(n, "enable_pathattr", True)
        _try_set(n, "pathattr", str(params["pathattr"]))
    if params.get("partitionattribs"):
        _try_set(n, "enable_partitionattribs", True)
        _try_set(n, "partitionattribs", str(params["partitionattribs"]))
    if "polygonsassubd" in params:
        val = bool(params["polygonsassubd"])
        _try_set(n, "enable_polygonsassubd", val)
        _try_set(n, "polygonsassubd", val)
    n.cook(force=True)
    return {"node": n.path(), "soppath": src.path()}


_REF_MODES = ("reference", "payload", "sublayer")


@endpoint("usd_import")
def usd_import(params):
    """Compose a USD file onto the stage. path = USD file (read-confined); primpath = destination
    prim; mode = reference|payload|sublayer; input (opt) = a LOP to layer onto."""
    path = confined_path(params["path"])
    n = _stage_node("reference::2.0", params.get("name"), params.get("input"))
    _try_set(n, "filepath1", path)
    if params.get("primpath"):
        _try_set(n, "primpath1", str(params["primpath"]))
    mode = str(params.get("mode", "reference"))
    if mode in _REF_MODES:
        _try_set(n, "reftype1", mode)
    n.cook(force=True)
    return {"node": n.path(), "path": path, "mode": mode}


_USD_LIGHT_TYPES = {
    "distant": "UsdLuxDistantLight", "disk": "UsdLuxDiskLight",
    "sphere": "UsdLuxSphereLight", "rect": "UsdLuxRectLight",
    "cylinder": "UsdLuxCylinderLight", "point": "point",
}


@endpoint("usd_light")
def usd_light(params):
    """Add/shape a USD/Karma light on the stage (light::2.0 or domelight::3.0).

    ltype: distant|disk|sphere|rect|cylinder|point|dome. Base: intensity (>=0), exposure (-20..20),
    color=[r,g,b]; dome hdri = equirect HDRI (read-confined).

    Response/quality (light + dome): enable_temperature + temperature (Kelvin ~500..100000, setting
    temperature auto-enables it), normalize, diffuse, specular, sampling_quality. Shadows (light +
    dome where present): shadow_enable, shadow_color=[r,g,b], shadow_distance, shadow_falloff.

    Shape sizing (light only, per applicable ltype): radius (sphere/disk), width/height (rect),
    length (cylinder), angle (distant angular diameter for soft sun shadows). Spot (light only):
    cone_angle (0..180) + cone_softness (0..1) — auto-enables the spotlight. IES (light only):
    ies_file (read-confined) + ies_angle_scale. single_sided (light only).

    Every USD-attribute (xn__) parm is located by readable name and guarded, so unknown params on a
    given build/ltype no-op instead of crashing. Back-compat: all prior params behave unchanged."""
    ltype = str(params.get("ltype", "distant"))
    is_dome = ltype == "dome"
    if is_dome:
        n = _stage_node("domelight::3.0", params.get("name"), params.get("input"))
        if params.get("hdri"):
            _try_set(n, "xn__inputstexturefile_r3ah", confined_path(params["hdri"]))
    else:
        if ltype not in _USD_LIGHT_TYPES:
            raise ValueError("ltype must be distant|disk|sphere|rect|cylinder|point|dome")
        n = _stage_node("light::2.0", params.get("name"), params.get("input"))
        _try_set(n, "lighttype", _USD_LIGHT_TYPES[ltype])
    # ── base (exact mangled names; unchanged for back-compat) ──
    if "intensity" in params:
        _try_set(n, "xn__inputsintensity_i0a", clamp(float(params["intensity"]), 0.0, 1e6))
    if "exposure" in params:
        _try_set(n, "xn__inputsexposure_vya", clamp(float(params["exposure"]), -20.0, 20.0))
    c = params.get("color")
    if c and len(c) == 3:
        # inputs:color is a color3f tuple; components are the mangled base + x/y/z
        base = "xn__inputscolor_zta"
        try:
            n.parmTuple(base).set(tuple(clamp(float(v), 0.0, 1.0) for v in c))
        except Exception:
            for sfx, v in zip(("r", "g", "b"), c):
                _try_set(n, base + sfx, clamp(float(v), 0.0, 1.0))
    # ── NEW: color temperature (light + dome) ──
    if params.get("enable_temperature"):
        _lop_author(n, "inputsenableColorTemperature", True)
    if "temperature" in params:
        _lop_author(n, "inputsenableColorTemperature", True)
        _lop_author(n, "inputscolorTemperature",
                    clamp(float(params["temperature"]), 500.0, 100000.0))
    # ── NEW: response / quality (light + dome) ──
    if "normalize" in params:
        _lop_author(n, "inputsnormalize", bool(params["normalize"]))
    if "diffuse" in params:
        _lop_author(n, "inputsdiffuse", clamp(float(params["diffuse"]), 0.0, 1e4))
    if "specular" in params:
        _lop_author(n, "inputsspecular", clamp(float(params["specular"]), 0.0, 1e4))
    if "sampling_quality" in params:
        _lop_author(n, "karmalightsamplingquality",
                    clamp(float(params["sampling_quality"]), 0.0, 100.0))
    # ── NEW: shadows (light + dome where present) ──
    if "shadow_enable" in params:
        _lop_author(n, "inputsshadowenable", bool(params["shadow_enable"]))
    sc = params.get("shadow_color")
    if sc and len(sc) == 3:
        _lop_author_tuple(n, "inputsshadowcolor",
                          [clamp(float(v), 0.0, 1.0) for v in sc])
    if "shadow_distance" in params:
        _lop_author(n, "inputsshadowdistance", clamp(float(params["shadow_distance"]), 0.0, 1e9))
    if "shadow_falloff" in params:
        _lop_author(n, "inputsshadowfalloff", clamp(float(params["shadow_falloff"]), 0.0, 1e6))
    # ── NEW: shape sizing (light only; harmless no-op on dome / wrong ltype) ──
    if not is_dome:
        if "radius" in params:
            _lop_author(n, "inputsradius", clamp(float(params["radius"]), 0.0, 1e6))
        if "width" in params:
            _lop_author(n, "inputswidth", clamp(float(params["width"]), 0.0, 1e6))
        if "height" in params:
            _lop_author(n, "inputsheight", clamp(float(params["height"]), 0.0, 1e6))
        if "length" in params:
            _lop_author(n, "inputslength", clamp(float(params["length"]), 0.0, 1e6))
        if "angle" in params:
            _lop_author(n, "inputsangle", clamp(float(params["angle"]), 0.0, 360.0))
        # spot cone — authoring cone params implies a spotlight
        if "cone_angle" in params:
            _try_set(n, "spotlightenable", 1)
            _lop_author(n, "shapingconeangle", clamp(float(params["cone_angle"]), 0.0, 180.0))
        if "cone_softness" in params:
            _try_set(n, "spotlightenable", 1)
            _lop_author(n, "shapingconesoftness", clamp(float(params["cone_softness"]), 0.0, 1.0))
        # IES
        if params.get("ies_file"):
            _try_set(n, "iesenable", 1)
            _lop_author(n, "shapingiesfile", confined_path(params["ies_file"]))
        if "ies_angle_scale" in params:
            _lop_author(n, "shapingiesangleScale",
                        clamp(float(params["ies_angle_scale"]), -1.0, 1.0))
        if "single_sided" in params:
            _lop_author(n, "karmalightsinglesided", bool(params["single_sided"]))
    n.cook(force=True)
    return {"node": n.path(), "ltype": ltype}


@endpoint("usd_camera")
def usd_camera(params):
    """Add/shape a camera prim on the USD stage (camera LOP).

    Base: focal (mm, 1..1e4), aperture (mm horizontal), t=[x,y,z], r=[x,y,z] deg, primpath (opt).
    Aperture: vaperture (vertical mm), h_offset/v_offset (aperture offsets = lens shift), aspect.
    Projection: projection = perspective|orthographic. Clipping: clip=[near,far]. DOF: focus_distance
    + fstop (fstop 0 = pinhole/no DOF on this build). exposure. Motion-blur interval:
    shutter_open/shutter_close (pairs with karma_render_settings motion_blur). Aim (USD-native, no
    expression): lookat = target prim path -> enables look-at; upvecmethod = yaxis|xaxis|custom;
    upvec=[x,y,z]. input (opt) = a LOP to layer onto. Back-compat: all prior params unchanged."""
    n = _stage_node("camera", params.get("name"), params.get("input"))
    if params.get("primpath"):
        _try_set(n, "primpath", str(params["primpath"]))
    if "focal" in params:
        _try_set(n, "focalLength", clamp(float(params["focal"]), 1.0, 1e4))
    if "aperture" in params:
        _try_set(n, "horizontalAperture", clamp(float(params["aperture"]), 0.1, 1e4))
    # ── NEW: aperture / lens shift / aspect ──
    if "vaperture" in params:
        _try_set(n, "verticalAperture", clamp(float(params["vaperture"]), 0.1, 1e4))
    if "h_offset" in params:
        _try_set(n, "horizontalApertureOffset", float(params["h_offset"]))
    if "v_offset" in params:
        _try_set(n, "verticalApertureOffset", float(params["v_offset"]))
    # (framing aspect is controlled via horizontalAperture/verticalAperture; the USD `aspectratio`
    #  parm is a conform x/y pair, deliberately not exposed as a scalar to avoid mis-authoring it)
    # ── NEW: projection (probed tokens: perspective|orthographic) ──
    proj = params.get("projection")
    if proj in ("perspective", "orthographic"):
        _try_set(n, "projection", proj)
    # ── NEW: clipping range (2-tuple near/far) ──
    clip = params.get("clip")
    if clip and len(clip) == 2:
        try:
            n.parmTuple("clippingRange").set((float(clip[0]), float(clip[1])))
        except Exception:
            pass
    # ── NEW: DOF + exposure ──
    if "focus_distance" in params:
        _try_set(n, "focusDistance", clamp(float(params["focus_distance"]), 0.0, 1e9))
    if "fstop" in params:
        _try_set(n, "fStop", clamp(float(params["fstop"]), 0.0, 1e4))
    if "exposure" in params:
        _try_set(n, "exposure", clamp(float(params["exposure"]), -20.0, 20.0))
    # ── NEW: shutter interval (mangled) ──
    if "shutter_open" in params:
        _lop_author(n, "shutteropen", float(params["shutter_open"]))
    if "shutter_close" in params:
        _lop_author(n, "shutterclose", float(params["shutter_close"]))
    # ── NEW: aim (USD-native look-at, not an expression/constraint) ──
    if params.get("lookat"):
        _try_set(n, "lookatenable", 1)
        _try_set(n, "lookatprim", str(params["lookat"]))
    upm = params.get("upvecmethod")
    if upm in ("yaxis", "xaxis", "custom"):
        _try_set(n, "upvecmethod", upm)
    up = params.get("upvec")
    if up and len(up) == 3:
        try:
            n.parmTuple("upvec").set(tuple(float(v) for v in up))
        except Exception:
            pass
    t = params.get("t")
    if t and len(t) == 3:
        try:
            n.parmTuple("t").set(tuple(float(v) for v in t))
        except Exception:
            for pn, v in zip(("tx", "ty", "tz"), t):
                _try_set(n, pn, float(v))
    r = params.get("r")
    if r and len(r) == 3:
        try:
            n.parmTuple("r").set(tuple(float(v) for v in r))
        except Exception:
            for pn, v in zip(("rx", "ry", "rz"), r):
                _try_set(n, pn, float(v))
    n.cook(force=True)
    return {"node": n.path()}


@endpoint("karma_render_settings")
def karma_render_settings(params):
    """WIRE-ONLY: build the Karma render graph in LOP (render-settings prim + usdrender ROP). Does
    NOT render — the human fires it (same posture as setup_karma). resolution=[x,y], samples,
    engine=cpu|xpu, camera=prim path, picture=output image (write-confined), input (opt) = LOP."""
    rs = _stage_node("karmarendersettings", params.get("name"), params.get("input"))
    if params.get("camera"):
        _try_set(rs, "camera", str(params["camera"]))
    if params.get("picture"):
        _try_set(rs, "picture", confined_path(params["picture"]))
    res = params.get("resolution")
    if res and len(res) == 2:
        rx = int(clamp(int(res[0]), 1, 16384))
        ry = int(clamp(int(res[1]), 1, 16384))
        # NOTE (probed H21.0.671): on karmarendersettings `resolutiony` is permission-locked and
        # `res_mode` defaults to 'autoheight' (height derived from width + camera aspect); only
        # `resolutionx` (width) is directly settable, so the height set below is a guarded no-op on
        # this build and the render height comes from the camera aspect. Behavior unchanged from the
        # original handler; left as-is intentionally rather than forcing a fixed 720 via 'manual'.
        if not _try_set(rs, "resolutionx", rx):
            try:
                rs.parmTuple("resolution").set((rx, ry))
            except Exception:
                pass
        _try_set(rs, "resolutiony", ry)
    if "samples" in params:
        _try_set(rs, "samplesperpixel", int(clamp(int(params["samples"]), 1, 256)))
    if "engine" in params:
        _try_set(rs, "engine", "xpu" if str(params["engine"]) == "xpu" else "cpu")
    # ── NEW: quality / ray limits ──
    if "pathtraced_samples" in params:
        _try_set(rs, "pathtracedsamples", int(clamp(int(params["pathtraced_samples"]), 1, 256)))
    if "diffuse_limit" in params:
        _try_set(rs, "diffuselimit", clamp(float(params["diffuse_limit"]), 0.0, 32.0))
    if "reflect_limit" in params:
        _try_set(rs, "reflectionlimit", clamp(float(params["reflect_limit"]), 0.0, 32.0))
    if "refract_limit" in params:
        _try_set(rs, "refractionlimit", clamp(float(params["refract_limit"]), 0.0, 32.0))
    # ── NEW: denoiser (probed tokens off|optix|oidn) ──
    den = params.get("denoiser")
    if den in ("off", "optix", "oidn"):
        _try_set(rs, "denoiser", den)
    # ── NEW: motion blur (pairs with usd_camera shutter_open/close) ──
    if "motion_blur" in params:
        _try_set(rs, "enablemblur", bool(params["motion_blur"]))
    # ── NEW: AOV presets (typed only — NO arbitrary LPE strings) ──
    aov = params.get("aovs")
    if aov in ("basic", "full"):
        for pnm in ("albedo", "hitN", "hitPz"):
            _try_set(rs, pnm, 1)
        if aov == "full":
            for pnm in ("ambientocclusion", "motionvectors"):
                _try_set(rs, pnm, 1)
    rop = rs.parent().createNode("usdrender_rop", (params.get("name") or "karma") + "_rop")
    rop.setInput(0, rs)
    rop.moveToGoodPosition()
    return {"node": rs.path(), "rop": rop.path(), "rendered": False,
            "note": "Karma render graph wired; start the render yourself"}


# Render Geometry Settings menus — live-probed H21.0.671. Every
# xn__ menu is hou.menuType.Normal (STRING token == label); authored via _lop_author (flips _control
# to 'set', then sets the token). `rendervisibility` is a free-form Karma category glob (NOT a menu):
# '*' = visible to all; exclude camera rays for a phantom / reflection-only prim.
_HOLDOUT_MODE = {"none": "None", "matte": "Matte", "background": "Background"}
_VBLUR_MODE = {"none": "No Velocity Blur", "velocity": "Velocity Blur", "acceleration": "Acceleration Blur"}


@endpoint("setup_prorender")
def setup_prorender(params):
    """WIRE-ONLY: build a USD-render ROP set to AMD Radeon ProRender (the Hydra delegate `HdRprPlugin`)
    and hand it back UNRENDERED -- the human fires it (same posture as setup_karma / karma_render_settings;
    this removes the resource-DoS / GPU-cook-freeze surface). RPR is Houdini's GPU render path for AMD
    Radeon cards (RDNA2 / gfx1030+), where Karma XPU (NVIDIA/OptiX) falls back to CPU. This tool only
    NAMES the delegate, so it BUILDS fine anywhere; it RENDERS on Radeon only where the optional hdRpr H21
    package is installed in the user's Houdini (see AMDProRender/).

    Node: a /stage `usdrender_rop` with `renderer=HdRprPlugin`. input (opt) = the LOP to render (a stage
    carrying a camera + a RenderSettings prim -- e.g. a rendersettings LOP, sop_import, or a
    materiallibrary output). camera = the camera PRIM path (USD) to override with. rendersettings = the
    RenderSettings prim path (opt). picture = override output image (write-confined under the working dir).
    Resolution/samples live on the RenderSettings prim (author them there), not on this ROP. Returns
    {node, renderer, rendered:False} -- nothing is written until the user starts the render."""
    n = _stage_node("usdrender_rop", params.get("name"), params.get("input"))
    _try_set(n, "renderer", "HdRprPlugin")  # AMD ProRender Hydra delegate id (AMDProRender/UsdRenderers.json)
    if params.get("rendersettings"):
        _try_set(n, "rendersettings", str(params["rendersettings"]))
    if params.get("camera"):
        _try_set(n, "override_camera", str(params["camera"]))
    if params.get("picture"):
        _try_set(n, "outputimage", confined_path(params["picture"]))  # write-confined output image
    return {"node": n.path(), "renderer": "HdRprPlugin", "rendered": False,
            "note": "RPR render graph wired (delegate HdRprPlugin); start the render yourself. "
                    "Renders on AMD Radeon only where the optional hdRpr H21 package is installed."}


@endpoint("render_geo_settings")
def render_geo_settings(params):
    """Author PER-PRIM Karma render settings on a USD stage (Render Geometry Settings LOP) — the
    deliver-lane workhorse used on nearly every element: primary-ray visibility (set `visibility` to
    a Karma category glob — e.g. exclude camera for a PHANTOM / reflection-only prim), holdout/MATTE
    mode, motion + velocity blur, uniform-volume interpretation (+ its sample count), and dicing
    quality. Chains after a stage LOP; `prim_pattern` selects which prims to affect. WIRE-ONLY
    authoring — the human fires the render. BUILT."""
    n = _stage_node("rendergeometrysettings", params.get("name"), after=params["input"])
    applied = {}
    if "prim_pattern" in params:
        applied["prim_pattern"] = _try_set(n, "primpattern", str(params["prim_pattern"]))
    if "visibility" in params:
        applied["visibility"] = _lop_author(n, "rendervisibility", str(params["visibility"]))
    if "holdout" in params:
        tok = _HOLDOUT_MODE.get(str(params["holdout"]).lower())
        if tok is not None:
            applied["holdout"] = _lop_author(n, "holdoutmode", tok)
    if "motion_blur" in params:
        applied["motion_blur"] = _lop_author(n, "mblur", bool(params["motion_blur"]))
    if "velocity_blur" in params:
        tok = _VBLUR_MODE.get(str(params["velocity_blur"]).lower())
        if tok is not None:
            applied["velocity_blur"] = _lop_author(n, "vblur", tok)
    if "uniform_volume" in params:
        applied["uniform_volume"] = _lop_author(n, "volumeuniform", bool(params["uniform_volume"]))
    if "uniform_volume_samples" in params:
        applied["uniform_volume_samples"] = _lop_author(
            n, "volumeuniformsamples", int(clamp(int(params["uniform_volume_samples"]), 1, 256)))
    if "dicing_quality" in params:
        applied["dicing_quality"] = _lop_author(n, "dicingquality", clamp(float(params["dicing_quality"]), 0.0, 16.0))
    n.setDisplayFlag(True)
    return {"node": n.path(), "applied": applied}


# Karma Fog Box shape menu (Normal menu, STRING tokens '0'..'6').
_FOGBOX_SHAPE = {"box": "0", "sphere": "1", "tube": "2", "cone": "3",
                 "capsule": "4", "torus": "5", "custom": "6"}


@endpoint("karma_fog_box")
def karma_fog_box(params):
    """Add an atmospheric FOG VOLUME to a USD stage (Karma Fog Box LOP) — uniform or noise-modulated
    fog inside a box/sphere/etc. bound, for horizon haze / god-rays / depth atmosphere. Controls:
    density, shadow density, scattering `phase` (anisotropy g, -1..1), tint `color`, attenuation,
    optional noise breakup, and a transform. Chains after a stage LOP (or stands alone in /stage).
    WIRE-ONLY — the human fires the render. BUILT."""
    n = _stage_node("karmafogbox", params.get("name"), after=params.get("input"))
    applied = {}
    if "shape" in params:
        tok = _FOGBOX_SHAPE.get(str(params["shape"]).lower())
        if tok is not None:
            applied["shape"] = _try_set(n, "shape", tok)
    if "purpose" in params:
        applied["purpose"] = _try_set(n, "purpose", "proxy" if str(params["purpose"]) == "proxy" else "render")
    if "density" in params:
        applied["density"] = _try_set(n, "density", clamp(float(params["density"]), 0.0, 1e4))
    if "shadow" in params:
        applied["shadow"] = _try_set(n, "shadow", clamp(float(params["shadow"]), 0.0, 1e4))
    if "phase" in params:
        applied["phase"] = _try_set(n, "phase", clamp(float(params["phase"]), -1.0, 1.0))
    if "scale" in params:
        applied["scale"] = _try_set(n, "scale", clamp(float(params["scale"]), 0.0, 1e5))
    if "attenuation" in params:
        applied["attenuation"] = _try_set(n, "atten", clamp(float(params["attenuation"]), 0.0, 1e4))
    if "color" in params and len(params["color"]) == 3:
        applied["color"] = _set_vec(n, "color", params["color"])
    if "noise" in params:
        applied["noise"] = _try_set(n, "addnoise", bool(params["noise"]))
    if "noise_scale" in params:
        _try_set(n, "addnoise", True)
        applied["noise_scale"] = _try_set(n, "noisescale", clamp(float(params["noise_scale"]), 0.0, 1e4))
    if "noise_amplitude" in params:
        _try_set(n, "addnoise", True)
        applied["noise_amplitude"] = _try_set(n, "amplitude", clamp(float(params["noise_amplitude"]), 0.0, 1e4))
    if "noise_octaves" in params:
        applied["noise_octaves"] = _try_set(n, "octaves", int(clamp(int(params["noise_octaves"]), 1, 10)))
    if "translate" in params and len(params["translate"]) == 3:
        applied["translate"] = _set_vec(n, "t", params["translate"])
    if "rotate" in params and len(params["rotate"]) == 3:
        applied["rotate"] = _set_vec(n, "r", params["rotate"])
    if "size" in params and len(params["size"]) == 3:
        applied["size"] = _set_vec(n, "s", params["size"])
    n.setDisplayFlag(True)
    return {"node": n.path(), "applied": applied}


@endpoint("physical_sky")
def physical_sky(params):
    """Build a physically-based Karma sky + sun on the stage (karmaphysicalsky) — the terrain/globe
    sun-study primitive. One call gives a lit dome + directional sun.

    intensity, exposure, skymode = dome|atmosphere, turbidity (1..10), ground_albedo=[r,g,b],
    sun_angle (angular diameter deg -> shadow softness). Sun aim, two modes:
      mode=angles -> altitude (deg) + azimuth (deg);
      mode=geo    -> latitude + longitude + month (1..12) + day (1..31) + hour (0..24, 24hr) +
                     daylight (bool)  [real lat/long/date/time sun position for a georeferenced DEM].
    enable_sun (default on), sun_intensity, sun_color=[r,g,b]. input (opt) = a LOP to layer onto.
    WIRE-ONLY posture: builds the light network, never fires a render."""
    n = _stage_node("karmaphysicalsky", params.get("name"), params.get("input"))
    if "intensity" in params:
        _try_set(n, "intensity", clamp(float(params["intensity"]), 0.0, 1e6))
    if "exposure" in params:
        _try_set(n, "exposure", clamp(float(params["exposure"]), -20.0, 20.0))
    skm = str(params.get("skymode", "")).lower()
    if skm in ("dome", "domelight"):
        _try_set(n, "skymode", 0)
    elif skm in ("atmosphere", "atmospheric"):
        _try_set(n, "skymode", 1)
    if "turbidity" in params:
        _try_set(n, "turbidity", clamp(float(params["turbidity"]), 1.0, 10.0))
    ga = params.get("ground_albedo")
    if ga and len(ga) == 3:
        try:
            n.parmTuple("ground_albedo").set(tuple(clamp(float(v), 0.0, 1.0) for v in ga))
        except Exception:
            pass
    if "sun_angle" in params:
        _try_set(n, "angle", clamp(float(params["sun_angle"]), 0.0, 90.0))
    # sun aim mode
    aim = str(params.get("mode", "")).lower()
    if aim == "angles":
        _try_set(n, "set_using", 0)
    elif aim in ("geo", "geographic", "location"):
        _try_set(n, "set_using", 1)
    if "altitude" in params:
        _try_set(n, "solar_altitude", clamp(float(params["altitude"]), -90.0, 90.0))
    if "azimuth" in params:
        _try_set(n, "solar_azimuth", clamp(float(params["azimuth"]), 0.0, 360.0))
    if "latitude" in params:
        _try_set(n, "geo_latitude", clamp(float(params["latitude"]), -90.0, 90.0))
    if "longitude" in params:
        _try_set(n, "geo_longitude", clamp(float(params["longitude"]), -180.0, 180.0))
    if "month" in params:
        _try_set(n, "geo_month", int(clamp(int(params["month"]), 1, 12)) - 1)  # menu is 0-based
    if "day" in params:
        _try_set(n, "geo_day", int(clamp(int(params["day"]), 1, 31)))
    if "hour" in params:
        _try_set(n, "geo_hr_spec", 2)  # '3' = 24hr clock (menu index 2)
        hh = clamp(float(params["hour"]), 0.0, 24.0)          # geo_time = (hours, minutes) tuple
        whole = int(hh)
        try:
            n.parmTuple("geo_time").set((whole, round((hh - whole) * 60.0)))
        except Exception:
            pass
    if "daylight" in params:
        _try_set(n, "geo_daylight", bool(params["daylight"]))
    if "enable_sun" in params:
        _try_set(n, "enablesun", bool(params["enable_sun"]))
    if "sun_intensity" in params:
        _try_set(n, "sun_intensity", clamp(float(params["sun_intensity"]), 0.0, 1e6))
    scl = params.get("sun_color")
    if scl and len(scl) == 3:
        try:
            n.parmTuple("sun_color").set(tuple(clamp(float(v), 0.0, 1.0) for v in scl))
        except Exception:
            pass
    n.cook(force=True)
    return {"node": n.path(), "skymode": skm or None, "aim": aim or None}


@endpoint("light_link")
def light_link(params):
    """Restrict which geometry a light (de)illuminates via a lightlinker LOP — data-only prim-pattern
    strings, NO expressions. Authors one link row.

    light (req) = light prim path/pattern; geo (req) = target geo prim pattern; mode = link|unlink
    (link -> geo goes in the include set; unlink -> geo goes in the exclude set); link_type =
    light|shadow (shadow = separate shadow-linking); input (opt) = a LOP to layer onto.
    The "this light only hits the building, not the terrain" tool."""
    light = str(params["light"])
    geo = str(params["geo"])
    mode = str(params.get("mode", "link"))
    lt = "shadow" if str(params.get("link_type", "light")) == "shadow" else "light"
    n = _stage_node("lightlinker", params.get("name"), params.get("input"))
    _try_set(n, "num_links", 1)                    # add one multiparm link row
    _try_set(n, "link_enabled_1", 1)
    _try_set(n, "link_prim_1", light)
    _try_set(n, "link_type_1", lt)
    _try_set(n, "link_ispathexpression_1", 1)       # treat include/exclude as prim patterns
    if mode == "unlink":
        _try_set(n, "link_excludes_1", geo)
    else:
        _try_set(n, "link_includes_1", geo)
    n.cook(force=True)
    return {"node": n.path(), "light": light, "geo": geo, "mode": mode, "link_type": lt}


# ── assign_usd_material (MaterialX authoring + stage binding; WIRE-ONLY) ──────────────────────────────
# Closes the material gap: the USD/Karma render lane can now reach a TEXTURED frame. Composes stock
# Solaris LOP ops ONLY (materiallibrary + mtlxstandard_surface [+ mtlximage / mtlxnormalmap] +
# assignmaterial); no VEX, no arbitrary code. Texture-map file paths are read-confined. Contracts +
# end-to-end binding VERIFIED in hython on H21.0.671 (material:binding confirmed via UsdShade).
#
# mtlxstandard_surface parm names differ from Principled (MaterialX naming). Verified subset:
#   scalars: base, metalness, specular_roughness, specular_IOR, coat, coat_roughness, emission
#   color3 tuples (parmTuple, components r/g/b): base_color, emission_color, opacity (yes, a 3-tuple)
#   normal is an INPUT connector (wired via mtlxnormalmap), not a literal.
# Texture map -> (mtlximage signature, shader input connector). mtlximage output connector = "out".

# our typed scalar literal -> the real mtlxstandard_surface parm name
_MTLX_SCALARS = {
    "base": "base", "metalness": "metalness", "roughness": "specular_roughness",
    "ior": "specular_IOR", "coat": "coat", "coat_roughness": "coat_roughness", "emission": "emission",
}
# our typed [r,g,b] literal -> the real mtlxstandard_surface color3 parmTuple name
_MTLX_TUPLES = {"base_color": "base_color", "emission_color": "emission_color"}
# texture map param -> (mtlximage signature token, mtlxstandard_surface input connector name)
_MTLX_MAPS = {
    "basecolor_map": ("color3", "base_color"),
    "roughness_map": ("default", "specular_roughness"),
    "metalness_map": ("default", "metalness"),
    "emission_map": ("color3", "emission_color"),
}


@endpoint("assign_usd_material")
def assign_usd_material(params):
    """WIRE-ONLY Solaris: author a MaterialX Standard Surface material and BIND it to `prim_pattern` on
    the stage -- the typed path to a TEXTURED USD/Karma frame (no VEX, no arbitrary code). Composes
    materiallibrary + mtlxstandard_surface (+ mtlximage per texture map, normal via mtlxnormalmap) +
    assignmaterial. Nothing renders.

    input        : (opt) upstream LOP path to chain onto; else a fresh /stage branch.
    name         : material name -> authored at /materials/<name> (default 'surface').
    prim_pattern : (required) geometry prim path/pattern to bind the material to.
    is_pattern   : (opt bool) set when prim_pattern is a wildcard/expression pattern.
    Typed mtlx literals (all opt): base_color [r,g,b], base, metalness, roughness, ior,
      emission, emission_color [r,g,b], coat, coat_roughness, opacity (scalar 0..1 -> 3-tuple).
    Texture maps (opt, read-confined paths): basecolor_map, roughness_map, metalness_map,
      emission_map, normal_map (routed through mtlxnormalmap).
    projection   : (opt) 'uv' (default; samples pre-existing UVs) or 'triplanar' (world-space
      projection, NO UVs -- for scan / heightfield meshes with no UV layout). triplanar_blend
      (0..1) and triplanar_upaxis (0=X,1=Y,2=Z) tune the triplanar path.
    bind_purpose : (opt) '', 'preview', or 'full'.  Returns the material prim + what it bound to."""
    if not params.get("prim_pattern"):
        raise ValueError("prim_pattern is required (the geometry prim path/pattern to bind)")
    name = str(params.get("name") or "surface")

    # 1. materiallibrary chained onto the upstream stage; MaterialX shader lives in its Vop child net.
    ml = _stage_node("materiallibrary", None, params.get("input"))
    ss = ml.createNode("mtlxstandard_surface", name)
    applied = {}

    # 2. scalar literals
    for key, parm in _MTLX_SCALARS.items():
        if params.get(key) is not None:
            try:
                if _try_set(ss, parm, float(params[key])):
                    applied[key] = float(params[key])
            except (TypeError, ValueError):
                raise ValueError("%s must be a number" % key)

    # 3. color3 tuple literals
    for key, parm in _MTLX_TUPLES.items():
        if params.get(key) is not None:
            rgb = params[key]
            if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
                raise ValueError("%s must be an [r, g, b] list of 3 numbers" % key)
            pt = ss.parmTuple(parm)
            if pt is not None:
                pt.set(tuple(float(c) for c in rgb))
                applied[key] = [float(c) for c in rgb]

    # 4. opacity: our scalar -> the shader's 3-tuple
    if params.get("opacity") is not None:
        o = clamp(float(params["opacity"]), 0.0, 1.0)
        pt = ss.parmTuple("opacity")
        if pt is not None:
            pt.set((o, o, o))
            applied["opacity"] = o

    # 5. texture maps (each read-confined; signature per channel; wired to the shader input).
    # projection: 'uv' -> mtlximage (samples pre-existing UVs); 'triplanar' -> mtlxtriplanarprojection
    # (world-space projection, NO UVs -- for photogrammetry / heightfield meshes with no UV layout).
    # Both take the SAME signature tokens and both output on connector "out", so the map table and
    # the binding below are reused verbatim; only the source node changes. No new confinement surface:
    # triplanar feeds the same confined_path() into its three per-axis file parms.
    projection = str(params.get("projection") or "uv")
    if projection not in ("uv", "triplanar"):
        raise ValueError("projection must be 'uv' or 'triplanar'")
    tri_blend = params.get("triplanar_blend")
    tri_upaxis = params.get("triplanar_upaxis")

    def _mtlx_source(sig, path):
        cpath = confined_path(str(path))          # read-confinement (raises on escape) -- both paths
        if projection == "triplanar":
            n = ml.createNode("mtlxtriplanarprojection")
            _try_set(n, "signature", sig)
            for axis in ("filex", "filey", "filez"):
                _try_set(n, axis, cpath)          # same texture projected on all 3 world axes
            if tri_blend is not None:
                _try_set(n, "blend", clamp(float(tri_blend), 0.0, 1.0))
            if tri_upaxis is not None:
                _try_set(n, "upaxis", int(clamp(int(tri_upaxis), 0, 2)))
        else:
            n = ml.createNode("mtlximage")
            _try_set(n, "signature", sig)
            _try_set(n, "file", cpath)
        return n                                  # output connector is "out" for both

    for key, (sig, connector) in _MTLX_MAPS.items():
        if params.get(key):
            ss.setNamedInput(connector, _mtlx_source(sig, params[key]), "out")
            applied[key] = True
    # normal map routes indirectly: source(vector3) -> mtlxnormalmap -> shader 'normal' input
    if params.get("normal_map"):
        nsrc = _mtlx_source("vector3", params["normal_map"])
        nmap = ml.createNode("mtlxnormalmap")
        nmap.setNamedInput("in", nsrc, "out")
        ss.setNamedInput("normal", nmap, "out")
        applied["normal_map"] = True

    # 5b. displacement/height map: mtlxstandard_surface has NO displacement input (it's a separate
    # shader terminal), so a `collect` node joins the surface + displacement into ONE material. Only
    # built when a displacement_map is supplied; otherwise the surface-only material is unchanged.
    matnode = ss
    if params.get("displacement_map"):
        dsrc = _mtlx_source("default", params["displacement_map"])   # scalar-float height (uv or triplanar)
        disp = ml.createNode("mtlxdisplacement")
        disp.setNamedInput("displacement", dsrc, "out")
        if params.get("displacement_scale") is not None:
            _try_set(disp, "scale", clamp(float(params["displacement_scale"]), 0.0, 1000.0))
        ss.setName(name + "_surf", unique_name=True)   # free `name` BEFORE the collect claims it, else
        col = ml.createNode("collect", name)           # the collect auto-uniquifies to name+1 (wrong matpath)
        col.setNamedInput(col.inputNames()[0], ss, "out")           # slot 0 <- surface
        col.setNamedInput(col.inputNames()[1], disp, "out")         # slot grows -> slot 1 <- displacement
        matnode = col
        applied["displacement_map"] = True

    try:
        ml.cook(force=True)
    except Exception:  # noqa: BLE001 — cook failure surfaces via the returned paths; don't crash the call
        pass

    # 6. deterministic material prim path = matpathprefix + shader node name
    prefix = "/materials/"
    mp = ml.parm("matpathprefix")
    if mp is not None:
        try:
            prefix = mp.eval() or prefix
        except Exception:  # noqa: BLE001
            pass
    matpath = prefix.rstrip("/") + "/" + matnode.name()

    # 7. assignmaterial binding (bind-by-material-path; method 0)
    am = _stage_node("assignmaterial", None, ml.path())
    _try_set(am, "primpattern1", str(params["prim_pattern"]))
    _try_set(am, "matspecpath1", matpath)
    if params.get("is_pattern"):
        _try_set(am, "ispathexpression1", 1)
    if params.get("bind_purpose") in ("preview", "full"):
        _try_set(am, "bindpurpose1", str(params["bind_purpose"]))
    try:
        am.cook(force=True)
    except Exception:  # noqa: BLE001
        pass

    return {"node": am.path(), "material_library": ml.path(), "material": matpath,
            "shader_id": "ND_standard_surface_surfaceshader", "projection": projection,
            "bound_to": str(params["prim_pattern"]), "applied": applied, "rendered": False}

"""Look handlers — lights + cameras. Params verified against live H21.0.671 nodes.

add_light covers the full hlight::2.0 'light_type' palette (point/line/grid/disk/sphere/tube/geo/
distant/sun) plus dome/HDRI (envlight). The reference probe (reference/houdini_nodes.json) is a
name-only index: it confirms 'light_type' is a real parm on hlight::2.0 but stores no menu tokens,
so the enum->token map below is the live-verified H21 hlight Type menu (string tokens, in menu order)
and every set is guarded so a token this build doesn't know no-ops instead of crashing.
"""

import json
import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, resolve_node
from houdini_executor.handlers._parmutil import _try_set




def _set_literal(node, parm, value):
    """Set a static LITERAL value, first clearing any default expression/keyframes on the parm (the
    data-only camera-animation rule: never author an expression/constraint — mirror the flightcam
    pattern of deleteAllKeyframes-then-set). Guarded no-op if the parm is absent."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.deleteAllKeyframes()
    except Exception:
        pass
    try:
        p.set(value)
        return True
    except Exception:
        return False


def _look_rotates(eye, target, up):
    """Return (rx, ry, rz) euler degrees (xyz order) so a Houdini camera at `eye` looks at `target`.
    Pure geometry (the flightcam basis math): builds the camera's world-space axes (camera looks
    down -Z, so +Z points away from the target) and extracts literal rotates. NO expression/
    constraint is authored — the caller sets these as literal values/keyframes."""
    eye = hou.Vector3(eye)
    tgt = hou.Vector3(target)
    up = hou.Vector3(up)
    z = eye - tgt                       # camera +Z points away from what it looks at
    if z.length() < 1e-9:
        z = hou.Vector3(0.0, 0.0, 1.0)
    z = z.normalized()
    x = up.cross(z)                     # right = up x back
    if x.length() < 1e-9:               # up parallel to view dir — pick any orthogonal
        x = hou.Vector3(1.0, 0.0, 0.0).cross(z)
        if x.length() < 1e-9:
            x = hou.Vector3(0.0, 0.0, 1.0).cross(z)
    x = x.normalized()
    y = z.cross(x).normalized()         # recomputed up
    m = hou.Matrix4((x[0], x[1], x[2], 0.0,
                     y[0], y[1], y[2], 0.0,
                     z[0], z[1], z[2], 0.0,
                     eye[0], eye[1], eye[2], 1.0))
    rot = m.extractRotates()            # xyz euler degrees
    return float(rot[0]), float(rot[1]), float(rot[2])


def _resolve_sop(path):
    """Resolve a node path to a SOP; if given an OBJ, dive to its display/render SOP."""
    src = resolve_node(path)
    try:
        if isinstance(src, hou.ObjNode):
            d = src.displayNode() or src.renderNode()
            if d is not None:
                src = d
    except Exception:
        pass
    return src


def _target_point(params):
    """Resolve an aim target: explicit `target` [x,y,z], else the bbox centroid of `target_node`."""
    tgt = params.get("target")
    if tgt and len(tgt) == 3:
        return [float(v) for v in tgt]
    if params.get("target_node"):
        c = _resolve_sop(params["target_node"]).geometry().boundingBox().center()
        return [c[0], c[1], c[2]]
    raise ValueError("need target [x,y,z] or target_node")


_VIEWS = {
    "top": "Top", "bottom": "Bottom", "front": "Front", "back": "Back",
    "left": "Left", "right": "Right", "persp": "Perspective",
}


# enum ltype -> hlight::2.0 'light_type' menu token (string tokens, live-verified H21 hlight Type
# menu, in menu order). The probe (reference/houdini_nodes.json) is name-only and lists 'light_type'
# as a parm but carries no menu values, so this map is the authority. Identity tokens by design:
# each enum name equals its menu token. 'dome' is NOT here — it routes to envlight (no 'light_type'
# parm). Any type not in this map (and not dome) creates a plain hlight with the parm left at default.
# All of point/line/disk = area/soft interior lights; grid/sphere/tube = shaped area lights;
# geo = light emitted from arbitrary geometry; distant/sun = directional parallel rays of constant
# intensity (day/night at globe/outdoor scale — a point light dims to black there).
_LIGHT_TYPE_TOKEN = {
    "point": "point",
    "line": "line",
    "grid": "grid",
    "disk": "disk",
    "sphere": "sphere",
    "tube": "tube",
    "geo": "geo",
    "distant": "distant",
    "sun": "sun",
}


@endpoint("add_light")
def add_light(params):
    """ltype (default 'point'): any hlight::2.0 light_type — 'point' | 'line' | 'grid' | 'disk' |
    'sphere' | 'tube' | 'geo' | 'distant' | 'sun' — or 'dome' (envlight/HDRI). point/line/disk =
    interior area lights; grid/sphere/tube = shaped area lights; geo = geometry-emitted light;
    distant/sun = directional parallel rays of constant intensity (outdoor + globe day/night — aim
    with 'r' rotation, not 't'). dome is envlight with an optional read-confined HDRI (env_map).
    Returns the created light path and the resolved light_type token actually applied."""
    obj = hou.node("/obj")
    ltype = params.get("ltype", "point")
    applied_light_type = None
    if ltype == "dome":
        n = obj.createNode("envlight", params.get("name"))
        if params.get("hdri"):
            n.parm("env_map").set(confined_path(params["hdri"]))
        applied_light_type = "environment"
    else:
        n = obj.createNode("hlight::2.0", params.get("name"))
        token = _LIGHT_TYPE_TOKEN.get(ltype)
        if token is not None and _try_set(n, "light_type", token):
            applied_light_type = token
    if "intensity" in params:
        n.parm("light_intensity").set(float(params["intensity"]))
    c = params.get("color")
    if c and len(c) == 3:
        n.parm("light_colorr").set(float(c[0]))
        n.parm("light_colorg").set(float(c[1]))
        n.parm("light_colorb").set(float(c[2]))
    if "exposure" in params:
        _try_set(n, "light_exposure", float(params["exposure"]))
    # spot cone (valid on point + area lights; authoring cone params enables the cone)
    if "cone_angle" in params or "cone_delta" in params or params.get("cone_enable"):
        _try_set(n, "coneenable", 1)
    if "cone_angle" in params:
        _try_set(n, "coneangle", clamp(float(params["cone_angle"]), 0.0, 180.0))
    if "cone_delta" in params:
        _try_set(n, "conedelta", clamp(float(params["cone_delta"]), 0.0, 180.0))
    if "cone_roll" in params:
        _try_set(n, "coneroll", clamp(float(params["cone_roll"]), 0.001, 10.0))
    # area sizing
    asz = params.get("areasize")
    if asz and len(asz) == 2:
        try:
            n.parmTuple("areasize").set((float(asz[0]), float(asz[1])))
        except Exception:
            pass
    if "normalize_area" in params:
        _try_set(n, "normalizearea", bool(params["normalize_area"]))
    if "single_sided" in params:
        _try_set(n, "singlesided", bool(params["single_sided"]))
    # shadows (probed hlight tokens: off|raytrace|depthmap)
    st = params.get("shadow_type")
    if st in ("off", "raytrace", "depthmap"):
        _try_set(n, "shadow_type", st)
    if "shadow_intensity" in params:
        _try_set(n, "shadow_intensity", clamp(float(params["shadow_intensity"]), 0.0, 1.0))
    # contributions (contribprimary on hlight; diff/spec exist on envlight/dome — guarded no-op else)
    if "contrib_primary" in params:
        _try_set(n, "light_contribprimary", bool(params["contrib_primary"]))
    if "contrib_diffuse" in params:
        _try_set(n, "light_contribdiff", bool(params["contrib_diffuse"]))
    if "contrib_specular" in params:
        _try_set(n, "light_contribspec", bool(params["contrib_specular"]))
    if "sampling_quality" in params:
        _try_set(n, "vm_samplingquality", clamp(float(params["sampling_quality"]), 0.0, 100.0))
    t = params.get("t")
    if t and len(t) == 3:
        n.parmTuple("t").set(tuple(float(x) for x in t))
    r = params.get("r")
    if r and len(r) == 3:
        n.parmTuple("r").set(tuple(float(x) for x in r))
    return {"node": n.path(), "type": ltype, "light_type": applied_light_type}


@endpoint("add_camera")
def add_camera(params):
    """Create/shape an OBJ camera (cam).

    Base: focal/aperture (Houdini units), resx/resy (clamped), t/r=[x,y,z]. Clipping: near, far.
    DOF: focus (distance), fstop (1.4..22; drives Karma DOF). Projection: projection =
    perspective|ortho (+ orthowidth for ortho). aspect. Lens shift (architectural framing):
    win=[winx,winy] (+ winsize=[x,y]). background = read-confined image plate. Back-compat: all
    prior params behave unchanged."""
    obj = hou.node("/obj")
    n = obj.createNode("cam", params.get("name"))
    if "focal" in params:
        n.parm("focal").set(float(params["focal"]))
    if "aperture" in params:
        n.parm("aperture").set(float(params["aperture"]))
    if "resx" in params:
        n.parm("resx").set(int(clamp(int(params["resx"]), 1, 16384)))
    if "resy" in params:
        n.parm("resy").set(int(clamp(int(params["resy"]), 1, 16384)))
    # ── NEW: clipping ──
    if "near" in params:
        _try_set(n, "near", clamp(float(params["near"]), 0.0, 1e9))
    if "far" in params:
        _try_set(n, "far", clamp(float(params["far"]), 0.0, 1e12))
    # ── NEW: DOF ──
    if "focus" in params:
        _try_set(n, "focus", clamp(float(params["focus"]), 0.001, 1e6))
    if "fstop" in params:
        _try_set(n, "fstop", clamp(float(params["fstop"]), 0.0, 1e4))
    # ── NEW: projection (live H21 cam menu tokens: perspective|ortho|sphere|cylinder|lens).
    # Friendly 'orthographic' aliases to the real token 'ortho'; sphere/cylinder are the 360
    # equirectangular / cylindrical panoramic projections (VR/dome). 'lens' needs a lens shader so
    # it is not exposed. Set by live token string (menu accepts the token). ──
    proj = params.get("projection")
    if proj:
        tok = {"orthographic": "ortho", "ortho": "ortho", "perspective": "perspective",
               "sphere": "sphere", "cylinder": "cylinder"}.get(proj)
        if tok:
            _try_set(n, "projection", tok)
    if "orthowidth" in params:
        _try_set(n, "orthowidth", clamp(float(params["orthowidth"]), 0.001, 1e6))
    if "aspect" in params:
        _try_set(n, "aspect", clamp(float(params["aspect"]), 0.05, 2.0))
    # ── NEW: lens shift ──
    win = params.get("win")
    if win and len(win) == 2:
        try:
            n.parmTuple("win").set((float(win[0]), float(win[1])))
        except Exception:
            pass
    ws = params.get("winsize")
    if ws and len(ws) == 2:
        try:
            n.parmTuple("winsize").set((float(ws[0]), float(ws[1])))
        except Exception:
            pass
    # ── NEW: background plate (read-confined) ──
    if params.get("background"):
        _try_set(n, "vm_bgenable", 1)
        _try_set(n, "vm_background", confined_path(params["background"]))
    for key in ("t", "r"):
        v = params.get(key)
        if v and len(v) == 3:
            n.parmTuple(key).set(tuple(float(x) for x in v))
    return {"node": n.path()}


@endpoint("set_view_camera")
def set_view_camera(params):
    """Bind the Scene Viewer to a camera and/or change the standard view. Optional frame-all."""
    sv = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if sv is None:
        raise ValueError("no scene viewer open")
    vp = sv.curViewport()
    applied = {}
    if params.get("camera"):
        cam = resolve_node(params["camera"])
        vp.setCamera(cam)
        applied["camera"] = cam.path()
    view = params.get("view")
    if view:
        if view not in _VIEWS:
            raise ValueError("view must be one of " + "|".join(_VIEWS))
        vp.changeType(getattr(hou.geometryViewportType, _VIEWS[view]))
        applied["view"] = view
    if params.get("frame_all") or params.get("frame_view"):
        vp.frameAll()
        applied["framed"] = True
    return {"applied": applied}


# Display/analysis overlays live on hou.GeometryViewportDisplaySet (verified in H21.0.671 hou.py:
# showPointMarkers / showPointNormals / showPrimNormals / showPointNumbers / showPrimNumbers /
# showPointTrails / showPointPositions / showVertexNormals). We reach them via
# viewport.settings().displaySet(hou.displaySetType.<Set>), and apply each toggle across the sets
# that cover displayed geometry so overlays show whether the viewer is at object level (SceneObject)
# or diving into a SOP (DisplayModel / CurrentModel).
_DISPLAY_SET_TOGGLES = {
    "points": "showPointMarkers",
    "point_normals": "showPointNormals",
    "prim_normals": "showPrimNormals",
    "point_numbers": "showPointNumbers",
    "prim_numbers": "showPrimNumbers",
    "point_trails": "showPointTrails",
    "point_positions": "showPointPositions",
    "vertex_normals": "showVertexNormals",
}

# 'lights' (display light/camera geometry in the viewport) has no HOM viewport-settings boolean on
# this build; attempted via these candidate setters and recorded in `skipped` if none exist. Guarded
# so an unknown method is a safe no-op, never a crash.
_SETTINGS_TOGGLES = {
    "lights": ("displayLights", "showLights", "showObjects"),
}


@endpoint("viewport_display")
def viewport_display(params):
    """Toggle Scene Viewer display/analysis overlays (point markers, point/prim/vertex normals,
    point/prim numbers, point positions, point trails) so a screenshot reads for geometry analysis.
    All params are optional Bool: only the ones supplied are changed; the rest are left untouched.
    Returns {"applied": {param: bool}, "skipped": [params whose setter wasn't found on this build]}.
    """
    sv = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if sv is None:
        raise ValueError("no scene viewer open")
    settings = sv.curViewport().settings()

    # Resolve the display sets that cover displayed geometry (object level + inside a SOP). Guarded:
    # any missing enum / accessor is skipped so this never depends on a specific build's set list.
    display_sets = []
    for st in ("SceneObject", "DisplayModel", "CurrentModel"):
        enum = getattr(hou.displaySetType, st, None)
        if enum is None:
            continue
        try:
            ds = settings.displaySet(enum)
        except Exception:
            ds = None
        if ds is not None:
            display_sets.append(ds)

    applied = {}
    skipped = []

    for key, method in _DISPLAY_SET_TOGGLES.items():
        if key not in params:
            continue
        val = bool(params[key])
        ok = False
        for ds in display_sets:
            fn = getattr(ds, method, None)
            if fn is None:
                continue
            try:
                fn(val)
                ok = True
            except Exception:
                pass
        (applied.__setitem__(key, val) if ok else skipped.append(key))

    for key, candidates in _SETTINGS_TOGGLES.items():
        if key not in params:
            continue
        val = bool(params[key])
        ok = False
        for method in candidates:
            fn = getattr(settings, method, None)
            if fn is None:
                continue
            try:
                fn(val)
                ok = True
                break
            except Exception:
                pass
        (applied.__setitem__(key, val) if ok else skipped.append(key))

    return {"applied": applied, "skipped": skipped}


@endpoint("flightcam")
def flightcam(params):
    """Server-templated flight camera: a keyframed camera driven by a poses .json (read-confined),
    with the source point cloud (read-confined .ply/.bgeo) loaded as context. Creator: FAILS on name
    collision. poses json = {intrinsics:{fx,cx,cy}, image:{w,h}, cameras:[{R[9],center_ply[3],frame}]}.
    """
    poses_path = confined_path(params["poses"])
    if not poses_path.lower().endswith(".json"):
        raise ValueError("poses must be a .json")
    name = params.get("name", "flightcam")
    obj = hou.node("/obj")
    if obj.node(name) is not None or obj.node(name + "_cloud") is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    with open(poses_path) as fh:
        j = json.load(fh)
    intr = j["intrinsics"]
    w = j["image"]["w"]
    h = j["image"]["h"]
    cams = j["cameras"]
    if not cams:
        raise ValueError("poses json has no cameras")

    cloud = None
    if params.get("cloud"):
        cloud_path = confined_path(params["cloud"])
        cloud = obj.createNode("geo", name + "_cloud")
        f = cloud.createNode("file")
        f.parm("file").set(cloud_path)
        f.setDisplayFlag(True)
        f.setRenderFlag(True)
        cloud.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP

    aperture = float(params.get("aperture", 41.4214))
    cam = obj.createNode("cam", name)
    cam.parm("resx").set(int(w))
    cam.parm("resy").set(int(h))
    cam.parm("aperture").set(aperture)
    cam.parm("focal").set(intr["fx"] * aperture / w)
    cam.parm("winx").set((intr["cx"] - w / 2.0) / w)
    cam.parm("winy").set((intr["cy"] - h / 2.0) / h)
    _try_set(cam, "rOrd", "xyz")
    # optional intrinsic/clipping overrides (minor EXTEND — no expression-based path following)
    if "focal" in params:
        cam.parm("focal").set(clamp(float(params["focal"]), 1.0, 1e4))
    if "near" in params:
        _try_set(cam, "near", clamp(float(params["near"]), 0.0, 1e9))
    if "far" in params:
        _try_set(cam, "far", clamp(float(params["far"]), 0.0, 1e12))
    if params.get("frames_dir"):
        frames_dir = confined_path(params["frames_dir"])
        cam.parm("vm_background").set(frames_dir.rstrip("/\\") + r"/f_`padzero(4,$F)`.pgm")

    fmin, fmax = 10 ** 9, -10 ** 9
    for c in cams:
        r = c["R"]
        center = c["center_ply"]
        fr = c["frame"] + 1
        fmin, fmax = min(fmin, fr), max(fmax, fr)
        rgt = (r[0], r[1], r[2])
        upv = (-r[3], -r[4], -r[5])
        bak = (-r[6], -r[7], -r[8])
        m = hou.Matrix4((rgt[0], rgt[1], rgt[2], 0.0, upv[0], upv[1], upv[2], 0.0,
                         bak[0], bak[1], bak[2], 0.0, center[0], center[1], center[2], 1.0))
        rot = m.extractRotates()
        for p, v in (("tx", center[0]), ("ty", center[1]), ("tz", center[2]),
                     ("rx", rot[0]), ("ry", rot[1]), ("rz", rot[2])):
            k = hou.Keyframe()
            k.setFrame(fr)
            k.setValue(v)
            cam.parm(p).setKeyframe(k)
    hou.playbar.setFrameRange(fmin, fmax)
    hou.playbar.setPlaybackRange(fmin, fmax - 1)
    try:
        hou.setFrame(fmin)
    except Exception:
        pass
    return {"node": cam.path(), "cloud": cloud.path() if cloud else None,
            "nposes": len(cams), "frame_range": [fmin, fmax]}


@endpoint("camera_aim")
def camera_aim(params):
    """Point an existing camera at a target — DATA-ONLY (no look-at expression/constraint).

    camera (req) = camera node path. Target: target=[x,y,z] OR target_node (SOP/OBJ centered on its
    bbox centroid). up (opt) = up vector [x,y,z] (default +Y).

    [OBJ cam]: computes the look rotation from the camera position and sets LITERAL rx/ry/rz (and
    tx/ty/tz if `pos` is given). [LOP camera]: sets the native lookatenable + lookatprim (or
    lookatposition) + upvec — a USD attribute, not an expression."""
    cam = resolve_node(params["camera"])
    up = params.get("up") or [0.0, 1.0, 0.0]
    is_lop = False
    try:
        is_lop = cam.type().category().name() == "Lop"
    except Exception:
        is_lop = False

    if is_lop:
        # USD-native look-at (an attribute, not an expression)
        _try_set(cam, "lookatenable", 1)
        prim = params.get("target_node") or params.get("lookat")
        applied = {}
        if prim:
            _try_set(cam, "lookatprim", str(prim))
            applied["lookatprim"] = str(prim)
        else:
            tgt = _target_point(params)
            try:
                cam.parmTuple("lookatposition").set((tgt[0], tgt[1], tgt[2]))
                applied["lookatposition"] = tgt
            except Exception:
                pass
        upm = params.get("upvecmethod")
        if upm in ("yaxis", "xaxis", "custom"):
            _try_set(cam, "upvecmethod", upm)
        if params.get("up") and len(up) == 3:
            try:
                cam.parmTuple("upvec").set((float(up[0]), float(up[1]), float(up[2])))
            except Exception:
                pass
        cam.cook(force=True)
        return {"node": cam.path(), "context": "lop", "applied": applied}

    # OBJ cam — literal rotates from the look matrix
    target = _target_point(params)
    _try_set(cam, "rOrd", "xyz")
    pos = params.get("pos")
    if pos and len(pos) == 3:
        for pn, v in zip(("tx", "ty", "tz"), pos):
            _set_literal(cam, pn, float(v))
        eye = [float(v) for v in pos]
    else:
        eye = [cam.parm("tx").eval(), cam.parm("ty").eval(), cam.parm("tz").eval()]
    rx, ry, rz = _look_rotates(eye, target, up)
    for pn, v in zip(("rx", "ry", "rz"), (rx, ry, rz)):
        _set_literal(cam, pn, v)
    return {"node": cam.path(), "context": "obj", "eye": eye, "target": target,
            "r": [rx, ry, rz]}


@endpoint("camera_path")
def camera_path(params):
    """Animate an OBJ camera ALONG a curve SOP — DATA-ONLY (computed LITERAL keyframes, NO Follow-Path
    constraint / NO $F expression). Generalizes flightcam to any authored path.

    curve (req) = curve SOP path (>=2 points; sampled by segment fraction). frames = [f1,f2] (default
    [1, npoints]); one keyframe per integer frame. Orientation: aim at `target`=[x,y,z] if given
    (look-at flight), else tangent-follow (aim at the next sample). focal/aperture (opt), up (opt),
    name (opt). Fails on name collision."""
    src = _resolve_sop(params["curve"])
    pts = [p.position() for p in src.geometry().points()]
    if len(pts) < 2:
        raise ValueError("curve must have >= 2 points")
    frames = params.get("frames")
    if frames and len(frames) == 2:
        f1, f2 = int(frames[0]), int(frames[1])
    else:
        f1, f2 = 1, len(pts)
    if f2 <= f1:
        f2 = f1 + 1
    nf = f2 - f1 + 1

    obj = hou.node("/obj")
    name = params.get("name") or "camera_path"
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    cam = obj.createNode("cam", name)
    if "focal" in params:
        cam.parm("focal").set(clamp(float(params["focal"]), 1.0, 1e4))
    if "aperture" in params:
        cam.parm("aperture").set(clamp(float(params["aperture"]), 0.1, 1e4))
    _try_set(cam, "rOrd", "xyz")

    up = params.get("up") or [0.0, 1.0, 0.0]
    target = params.get("target")
    last = len(pts) - 1

    def sample(u):
        """Position along the polyline at fraction u in [0,1] (linear per segment)."""
        x = max(0.0, min(1.0, u)) * last
        i = int(x)
        if i >= last:
            return hou.Vector3(pts[last])
        a, b = hou.Vector3(pts[i]), hou.Vector3(pts[i + 1])
        return a + (b - a) * (x - i)

    du = (1.0 / (nf - 1)) if nf > 1 else 0.0
    for k in range(nf):
        fr = f1 + k
        u = k * du
        eye = sample(u)
        if target and len(target) == 3:
            look = [float(v) for v in target]
        else:
            nxt = sample(min(1.0, u + (du if du > 0 else 0.01)))
            look = [nxt[0], nxt[1], nxt[2]]
        rx, ry, rz = _look_rotates([eye[0], eye[1], eye[2]], look, up)
        for pn, v in (("tx", eye[0]), ("ty", eye[1]), ("tz", eye[2]),
                      ("rx", rx), ("ry", ry), ("rz", rz)):
            kf = hou.Keyframe()
            kf.setFrame(fr)
            kf.setValue(float(v))
            cam.parm(pn).setKeyframe(kf)
    hou.playbar.setFrameRange(f1, f2)
    hou.playbar.setPlaybackRange(f1, f2)
    return {"node": cam.path(), "frames": [f1, f2], "npoints": len(pts)}


def _set_color3(sh, base, rgb):
    """Set a color3f parm-tuple (e.g. emitcolor -> emitcolorr/g/b) probe-safely, clamped 0..1."""
    vals = tuple(clamp(float(v), 0.0, 1.0) for v in rgb)
    t = sh.parmTuple(base)
    if t is not None:
        try:
            t.set(vals)
            return True
        except Exception:
            pass
    ok = False
    for sfx, v in zip(("r", "g", "b"), vals):
        ok = _try_set(sh, base + sfx, v) or ok
    return ok


def _set_tex(sh, toggle, pathparm, path, extra_enables=()):
    """Enable a Principled texture slot + set its read-confined path (typed literal, NO VOP wiring).
    `toggle` is the slot's *_useTexture / *_enable parm; extra_enables are master toggles some maps
    need (e.g. normal maps gate on baseBumpAndNormal_enable). Probe-safe."""
    tex = confined_path(path)
    for en in extra_enables:
        _try_set(sh, en, 1)
    _try_set(sh, toggle, 1)
    return _try_set(sh, pathparm, tex)


@endpoint("assign_material")
def assign_material(params):
    """Assign a Principled Shader (principledshader::2.0) to the input via a Material SOP — typed
    literal params ONLY (no VOP/CVEX/vexpr shader authoring).

    Base (back-compat): basecolor=[r,g,b], roughness, metallic, texture (base-color map).
    Scalars (clamped): ior (1..3), reflect (0..1), coat (0..1), coatrough (0..1), sheen (0..1),
      sheentint (0..1 tint the sheen toward basecolor), emitint (0..10), opac (0..1 opacity),
      transparency (0..1).
    Colors: emitcolor=[r,g,b] (emission), opaccolor=[r,g,b] (opacity color).
    Texture maps (each a read-confined path; enables its slot toggle): basecolor_texture (or the
      back-compat `texture`), rough_texture, metallic_texture, reflect_texture, coat_texture,
      emit_texture, opac_texture, normal_texture (also enables baseBumpAndNormal), disp_texture.
    Per-group: group1 binds the shader to only a named primitive group on the Material SOP.
    The shader lives in /mat. Back-compat: every prior param behaves unchanged."""
    n = child_after(params["input"], "material", params.get("name"))
    mat = hou.node("/mat") or hou.node("/").createNode("mat")
    sh = mat.createNode("principledshader::2.0")
    # ── base color + core scalars (back-compat) ──
    c = params.get("basecolor")
    if c and len(c) == 3:
        _try_set(sh, "basecolorr", clamp(float(c[0]), 0.0, 1.0))
        _try_set(sh, "basecolorg", clamp(float(c[1]), 0.0, 1.0))
        _try_set(sh, "basecolorb", clamp(float(c[2]), 0.0, 1.0))
    if "roughness" in params:
        _try_set(sh, "rough", clamp(float(params["roughness"]), 0.0, 1.0))
    if "metallic" in params:
        _try_set(sh, "metallic", clamp(float(params["metallic"]), 0.0, 1.0))
    # ── NEW: typed Principled scalars ──
    if "ior" in params:
        _try_set(sh, "ior", clamp(float(params["ior"]), 1.0, 3.0))
    if "reflect" in params:
        _try_set(sh, "reflect", clamp(float(params["reflect"]), 0.0, 1.0))
    if "coat" in params:
        _try_set(sh, "coat", clamp(float(params["coat"]), 0.0, 1.0))
    if "coatrough" in params:
        _try_set(sh, "coatrough", clamp(float(params["coatrough"]), 0.0, 1.0))
    if "sheen" in params:
        _try_set(sh, "sheen", clamp(float(params["sheen"]), 0.0, 1.0))
    if "sheentint" in params:
        _try_set(sh, "sheentint", clamp(float(params["sheentint"]), 0.0, 1.0))
    if "emitint" in params:
        _try_set(sh, "emitint", clamp(float(params["emitint"]), 0.0, 10.0))
    if "opac" in params:
        _try_set(sh, "opac", clamp(float(params["opac"]), 0.0, 1.0))
    if "transparency" in params:
        _try_set(sh, "transparency", clamp(float(params["transparency"]), 0.0, 1.0))
    # ── NEW: colors (color3f tuples) ──
    ec = params.get("emitcolor")
    if ec and len(ec) == 3:
        _set_color3(sh, "emitcolor", ec)
    oc = params.get("opaccolor")
    if oc and len(oc) == 3:
        _set_color3(sh, "opaccolor", oc)
    # ── texture maps (basecolor keeps the back-compat `texture` alias) ──
    if params.get("texture"):
        _set_tex(sh, "basecolor_useTexture", "basecolor_texture", params["texture"])
    if params.get("basecolor_texture"):
        _set_tex(sh, "basecolor_useTexture", "basecolor_texture", params["basecolor_texture"])
    if params.get("rough_texture"):
        _set_tex(sh, "rough_useTexture", "rough_texture", params["rough_texture"])
    if params.get("metallic_texture"):
        _set_tex(sh, "metallic_useTexture", "metallic_texture", params["metallic_texture"])
    if params.get("reflect_texture"):
        _set_tex(sh, "reflect_useTexture", "reflect_texture", params["reflect_texture"])
    if params.get("coat_texture"):
        _set_tex(sh, "coat_useTexture", "coat_texture", params["coat_texture"])
    if params.get("emit_texture"):
        _set_tex(sh, "emitcolor_useTexture", "emitcolor_texture", params["emit_texture"])
    if params.get("opac_texture"):
        _set_tex(sh, "opaccolor_useTexture", "opaccolor_texture", params["opac_texture"])
    if params.get("normal_texture"):
        # normal maps gate on the master baseBumpAndNormal_enable + its type=normal, plus the slot's
        # own baseNormal_useTexture (probed H21: there is no baseNormal_enable).
        _try_set(sh, "baseBumpAndNormal_type", "normal")
        _set_tex(sh, "baseNormal_useTexture", "baseNormal_texture", params["normal_texture"],
                 extra_enables=("baseBumpAndNormal_enable",))
    if params.get("disp_texture"):
        # displacement uses dispTex_enable (not *_useTexture).
        _set_tex(sh, "dispTex_enable", "dispTex_texture", params["disp_texture"])
    n.parm("shop_materialpath1").set(sh.path())
    # ── NEW: per-group bind on the Material SOP ──
    if params.get("group1"):
        _try_set(n, "group1", str(params["group1"]))
    n.geometry()
    return {"node": n.path(), "material": sh.path()}

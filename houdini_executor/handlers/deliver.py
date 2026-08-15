"""Render / export handlers. Params verified against live H21.0.671 ROPs.

SECURITY CONTRACT:
  - RENDER is WIRE-ONLY. `setup_karma` builds the full render graph but NEVER calls .render() —
    the human fires the render. This removes the resource-DoS + heavy-scene-freeze surface.
  - EXPORT is EXECUTABLE-CONFINED. `export_*` DO write, but only to a realpath-confined output
    path under the working directory. Geometry/interchange export is the deliverable.
"""

import os
import hou
from houdini_executor.server import (
    endpoint, confined_path, resolve_node, out_context, clamp, WORKING_DIR,
)
from houdini_executor.handlers._parmutil import _try_set




def _set_literal(node, parm, value):
    """Pin a literal value on a parm that ships a channel expression (e.g. the geometry ROP's f1/f2,
    which default to $FSTART/$FEND keyframes that MASK a plain .set()): clear the keyframes/expression
    first so the literal wins on eval. Probe-safe no-op if the parm is absent. NEVER setExpression."""
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


def _apply_frames(node, frames):
    """Turn a single-frame export ROP into a frame-RANGE write. Probe-verified: the geometry /
    alembic / usd / filmboxfbx / gltf ROPs all carry a `trange` menu (index 1 = 'normal' = render
    the range) plus `f1`/`f2`. Some of them ship $FSTART/$FEND expression keyframes on f1/f2 that
    mask a plain .set(), so pin the literal via _set_literal (clears the keyframes first). Guarded
    no-op if frames is not a [start, end] pair. Returns the [f1, f2] actually applied, or None."""
    if not (frames and len(frames) == 2):
        return None
    _try_set(node, "trange", 1)  # 'normal' = render the frame range
    f1 = int(clamp(int(frames[0]), -100000, 100000))
    f2 = int(clamp(int(frames[1]), f1, 100000))
    _set_literal(node, "f1", f1)
    _set_literal(node, "f2", f2)
    return [f1, f2]


@endpoint("setup_karma")
def setup_karma(params):
    """WIRE-ONLY: build the OBJ-context Karma render graph (the /out `karma` ROP) and hand it back
    UNRENDERED — the human fires it (this removes the resource-DoS / heavy-scene cook-freeze surface).

    Node: /out/karma ROP. Base: picture (PNG/EXR/JPG by extension; write-confined under the working
    dir), camera (OBJ camera node path), resolutionx/resolutiony (pixels, clamped to 16384),
    samples (samplesperpixel, 1..256). Render-depth (all probed on the karma ROP, guarded):
    engine = cpu|xpu (XPU = GPU+CPU hybrid), denoiser = off|optix|oidn, motion_blur (enablemblur).
    Returns {node, rendered:False} — nothing is written until the user starts the render."""
    out = out_context()
    n = out.createNode("karma", params.get("name"))
    if params.get("picture"):
        n.parm("picture").set(confined_path(params["picture"]))  # write-confined output image
    if params.get("camera"):
        n.parm("camera").set(resolve_node(params["camera"]).path())
    if "resolutionx" in params:
        n.parm("resolutionx").set(int(clamp(int(params["resolutionx"]), 1, 16384)))
    if "resolutiony" in params:
        n.parm("resolutiony").set(int(clamp(int(params["resolutiony"]), 1, 16384)))
    if "samples" in params:
        n.parm("samplesperpixel").set(int(clamp(int(params["samples"]), 1, 256)))
    # ── optional render-depth (probed karma-ROP menus) ──
    if "engine" in params:
        _try_set(n, "engine", "xpu" if str(params["engine"]) == "xpu" else "cpu")
    den = params.get("denoiser")
    if den in ("off", "optix", "oidn"):
        _try_set(n, "denoiser", den)
    if "motion_blur" in params:
        _try_set(n, "enablemblur", bool(params["motion_blur"]))
    return {"node": n.path(), "rendered": False,
            "note": "render graph wired; start the render yourself"}


@endpoint("export_geometry")
def export_geometry(params):
    """Cook the `input` SOP and write it to a single geometry file at a confined output path (the
    /out `geometry` ROP). The output format is chosen by the extension: .bgeo / .bgeo.sc (native,
    lossless, fast — the recommended interchange), .obj (Wavefront), .geo, .ply, .vdb, etc. Writes
    ONE frame (the current frame); for a versioned frame-range cache use `export_cache`. The write
    is realpath-confined to the working directory."""
    out_path = confined_path(params["output"])
    n = out_context().createNode("geometry", params.get("name"))
    n.parm("soppath").set(resolve_node(params["input"]).path())
    n.parm("sopoutput").set(out_path)
    n.parm("mkpath").set(True)
    n.render()  # executable-confined write
    return {"node": n.path(), "output": out_path}


_BATCH_SAFE = None


def _sanitize_token(s):
    """Filesystem-safe token from a partition label (keep A-Za-z0-9._-, others -> _)."""
    out = []
    for ch in str(s):
        out.append(ch if (ch.isalnum() or ch in "._-") else "_")
    tok = "".join(out).strip("_") or "piece"
    return tok[:64]


@endpoint("batch_export")
def batch_export(params):
    """Split `input` geometry into PARTITIONS and write ONE confined file per partition (the #1
    recurring TD ask: "split this by group/name/attribute and export each piece"). split_by:
      • name (default) — one file per distinct value of the `name` primitive string attribute
      • group          — one file per primitive (or point) group
      • attribute      — one file per distinct value of the point/prim attribute named in `attribute`
    Each piece is isolated with a Blast and written via the confined geometry ROP. output_dir
    (confined; defaults to the working dir) + basename + format (bgeo.sc default | bgeo | obj | ply |
    geo | vdb) name the files: <basename>_<partition>.<format>. max_files (default 512) caps the write
    count so a mis-split can't spray thousands of files. Returns the list of files written. Partition
    labels feed a Blast group expression, so `name`/`attribute` values should be token-like (no spaces).
    ALL writes are realpath-confined to the working directory."""
    src = resolve_node(params["input"])
    geo = src.geometry()
    if geo is None:
        raise ValueError("%s failed to cook: %s" % (src.path(), "; ".join(src.errors()) or "no geometry"))
    split_by = str(params.get("split_by", "name"))
    fmt = str(params.get("format", "bgeo.sc")).lstrip(".")
    base = _sanitize_token(params.get("basename", "piece"))
    default_dir = WORKING_DIR
    try:
        from houdini_executor.server import _effective_working_dir
        default_dir = _effective_working_dir()
    except Exception:  # noqa: BLE001 — fall back to the arm-time global
        pass
    out_dir = confined_path(str(params.get("output_dir") or default_dir))
    max_files = int(clamp(int(params.get("max_files", 512)), 1, 5000))

    # Build the partition list: (label, blast-group-expression).
    if split_by == "group":
        names = [g.name() for g in geo.primGroups()] or [g.name() for g in geo.pointGroups()]
        parts = [(nm, nm) for nm in names]
    elif split_by in ("name", "attribute"):
        attr = str(params.get("attribute", "name"))
        if geo.findPrimAttrib(attr) is not None:
            vals = sorted({p.attribValue(attr) for p in geo.prims()}, key=str)
        elif geo.findPointAttrib(attr) is not None:
            vals = sorted({pt.attribValue(attr) for pt in geo.points()}, key=str)
        else:
            raise ValueError("attribute '%s' not found on prims or points of %s" % (attr, src.path()))
        parts = [(v, "@%s=%s" % (attr, v)) for v in vals]
    else:
        raise ValueError("split_by must be name|group|attribute")

    if not parts:
        raise ValueError("no partitions found for split_by=%s (attribute/groups empty?)" % split_by)
    if len(parts) > max_files:
        raise ValueError("%d partitions exceeds max_files=%d — raise max_files or coarsen the split"
                         % (len(parts), max_files))

    parent = src.parent()
    blast = parent.createNode("blast", (params.get("name") or "batch") + "_split")
    blast.setInput(0, src)
    _try_set(blast, "grouptype", 0)   # guess (points vs prims from the expression)
    _try_set(blast, "negate", 1)      # keep ONLY the selected partition
    rop = out_context().createNode("geometry", params.get("name"))
    rop.parm("soppath").set(blast.path())
    _try_set(rop, "mkpath", True)
    written = []
    for label, expr in parts:
        blast.parm("group").set(label if split_by == "group" else expr)
        fpath = confined_path(os.path.join(out_dir, "%s_%s.%s" % (base, _sanitize_token(label), fmt)))
        rop.parm("sopoutput").set(fpath)
        rop.render()  # executable-confined write
        written.append({"partition": str(label), "output": fpath})
    return {"count": len(written), "split_by": split_by, "output_dir": out_dir,
            "format": fmt, "files": written}


@endpoint("export_pointcloud")
def export_pointcloud(params):
    """Write `input` SOP's geometry to a portable point-cloud file at a confined output path -- the
    exit for clouds that entered via import_pointcloud/las_import. format: 'ply' (the ONLY cloud
    format Houdini 21 writes natively: binary big-endian, carries P + Cd colour + N normals; reads
    cleanly in CloudCompare/MeshLab/Open3D/PDAL). LAS/LAZ/E57 are import-only in Houdini (no export
    node exists) and are intentionally unsupported rather than faked."""
    fmt = str(params.get("format", "ply")).lower()
    if fmt != "ply":
        raise ValueError("export_pointcloud supports only 'ply'; LAS/LAZ/E57 are import-only in Houdini")
    out_path = confined_path(params["output"])
    if not out_path.lower().endswith(".ply"):
        raise ValueError("output path must end in .ply")
    n = out_context().createNode("geometry", params.get("name"))
    n.parm("soppath").set(resolve_node(params["input"]).path())
    n.parm("sopoutput").set(out_path)  # the .ply extension selects the gply writer
    n.parm("mkpath").set(True)
    n.render()  # executable-confined write
    return {"node": n.path(), "output": out_path, "format": "ply", "endianness": "binary_big_endian"}


_ABC_FORMATS = ("default", "hdf5", "ogawa")


@endpoint("export_alembic")
def export_alembic(params):
    """Write the `input` SOP to an Alembic (.abc) at a confined output path (the /out `alembic` ROP)
    — the standard interchange for animated/deforming geometry into Maya/Nuke/Blender/UE.

    frames = [start, end] (opt) writes an ANIMATED Alembic across the range (a single .abc holds the
    whole cache); omit for a single static frame. format (opt) = default | ogawa (modern, faster,
    smaller — recommended) | hdf5 (legacy). The write is realpath-confined to the working directory."""
    out_path = confined_path(params["output"])
    n = out_context().createNode("alembic", params.get("name"))
    n.parm("use_sop_path").set(True)
    n.parm("sop_path").set(resolve_node(params["input"]).path())
    n.parm("filename").set(out_path)
    n.parm("mkpath").set(True)
    fmt = str(params.get("format", "")).lower()
    if fmt in _ABC_FORMATS:
        _try_set(n, "format", fmt)
    applied_frames = _apply_frames(n, params.get("frames"))
    n.render()
    return {"node": n.path(), "output": out_path, "frames": applied_frames}


@endpoint("export_usd")
def export_usd(params):
    """Write a USD stage from a LOP network to a confined output path (the /out `usd` ROP). `loppath`
    = the LOP whose stage to write; SOP -> USD must go through a LOP first (e.g. sop_import). The
    output format is chosen by extension: .usd (auto) / .usda (ascii) / .usdc (binary crate) / .usdz
    (zipped package). frames = [start, end] (opt) writes an ANIMATED stage over the range; omit for a
    single frame. For a WIRE-ONLY staged handoff with layer-flattening control use `export_package`
    instead. The write is realpath-confined to the working directory.

    Always writes a SINGLE flattened file (`savestyle=flattenalllayers`): the default
    (flattenimplicitlayers) leaves a `sop_import`'s geometry as a separate implicit sublayer that the
    USD ROP tries to save to a node-path-derived location OUTSIDE the confined working dir (a
    confinement escape) AND throws on the canonical SOP->USD chain -- flattening inlines everything
    into the one confined output, fixing both. On a non-commercial (Apprentice) Houdini the written
    file carries the forced `.usdnc` extension regardless of the requested one; the returned `output`
    reflects the path that was ACTUALLY written (with `requested_output` echoing what was asked).
    (Probe note: the usd ROP has no `mkpath` parm on this build -- the guarded set below is a harmless
    no-op; the confined output already resolves under the existing working dir.)"""
    out_path = confined_path(params["output"])
    n = out_context().createNode("usd", params.get("name"))
    if params.get("loppath"):
        _try_set(n, "loppath", resolve_node(params["loppath"]).path())
    n.parm("lopoutput").set(out_path)
    # Force single-file flatten: prevents the sop_import implicit-sublayer confinement escape and the
    # OperationFailed throw under the default flattenimplicitlayers savestyle (verified H21.0.671).
    _try_set(n, "savestyle", "flattenalllayers")
    _try_set(n, "mkpath", True)  # guarded no-op on the usd ROP (parm absent); kept for other builds
    applied_frames = _apply_frames(n, params.get("frames"))
    n.render()  # executable-confined write
    # Non-commercial Houdini forces `.usdnc`; return the path that actually landed so a downstream
    # consumer never receives a path that does not exist. Both candidates stay under the confined dir.
    actual = out_path
    if not os.path.exists(actual):
        nc = os.path.splitext(out_path)[0] + ".usdnc"
        if os.path.exists(nc):
            actual = nc
    return {"node": n.path(), "output": actual, "requested_output": out_path, "frames": applied_frames}


@endpoint("export_fbx")
def export_fbx(params):
    """Write an FBX (.fbx) from the OBJ containing the `input` SOP to a confined output path (the /out
    `filmboxfbx` ROP) — the standard rigged/animated interchange for Maya/Max/UE/Unity.

    The whole OBJ subnet that owns `input` is exported (via startnode), so parent transforms and
    sibling geometry come along. frames = [start, end] (opt) writes an ANIMATED FBX over the range;
    omit for a single static frame. The write is realpath-confined to the working directory."""
    out_path = confined_path(params["output"])
    src = resolve_node(params["input"])
    n = out_context().createNode("filmboxfbx", params.get("name"))
    n.parm("sopoutput").set(out_path)
    _try_set(n, "startnode", src.parent().path())  # export the source SOP's OBJ
    _try_set(n, "mkpath", True)
    applied_frames = _apply_frames(n, params.get("frames"))
    n.render()
    return {"node": n.path(), "output": out_path, "frames": applied_frames}


@endpoint("export_gltf")
def export_gltf(params):
    """Write a glTF/GLB from the `input` SOP to a confined output path (the /out `gltf` ROP) — the
    web/real-time interchange (three.js, model-viewer, UE/Unity, AR quicklook).

    exporttype (opt) = auto (pick from the extension — default) | gltf (.gltf + external buffers) |
    glb (single-file binary GLB). frames = [start, end] (opt) writes an ANIMATED glTF over the range;
    omit for a single static frame. The write is realpath-confined to the working directory."""
    out_path = confined_path(params["output"])
    src = resolve_node(params["input"])
    n = out_context().createNode("gltf", params.get("name"))
    _try_set(n, "usesoppath", True)
    _try_set(n, "soppath", src.path())
    n.parm("file").set(out_path)
    _try_set(n, "mkpath", True)
    et = str(params.get("exporttype", "")).lower()
    if et in ("auto", "gltf", "glb"):
        _try_set(n, "exporttype", et)
    applied_frames = _apply_frames(n, params.get("frames"))
    n.render()
    return {"node": n.path(), "output": out_path, "frames": applied_frames}


@endpoint("export_cache")
def export_cache(params):
    """Write a versioned geometry cache (a per-frame .bgeo.sc sequence) over a frame range — the
    streaming backbone for sims / animated geo. Uses the /out `geometry` ROP (probe-verified). Put a
    frame token in the output name (e.g. cache_$F4.bgeo.sc) so each frame lands in its own file;
    frames = [start, end] sets the range (each end clamped to +/-100000, end >= start). Cooks and
    WRITES every frame — realpath-confined to the working directory. For a single frame use
    export_geometry; for a single animated container use export_alembic/export_usd."""
    out_path = confined_path(params["output"])
    src = resolve_node(params["input"])
    n = out_context().createNode("geometry", params.get("name"))
    n.parm("soppath").set(src.path())
    n.parm("sopoutput").set(out_path)
    n.parm("mkpath").set(True)
    frames = params.get("frames")
    if frames and len(frames) == 2:
        n.parm("trange").set(1)  # render frame range
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        # The geometry ROP's f1/f2 SHIP $FSTART/$FEND expression keyframes (probe-confirmed); a plain
        # .set() is masked by the expression (f1 kept evaluating to the scene's $FSTART, not the
        # caller's frame), so clear the keyframes first and pin the literal frame.
        _set_literal(n, "f1", f1)
        _set_literal(n, "f2", f2)
    n.render()  # executable-confined write
    return {"node": n.path(), "output": out_path, "frames": frames}


@endpoint("bake_texture")
def bake_texture(params):
    """WIRE-ONLY: build the texture-bake graph (Bake Texture 3.0) and set the confined output +
    resolution, but do NOT execute — baking is a render, so the human fires it (same rule as
    setup_karma). This kills the resource-DoS + heavy-scene cook-freeze surface."""
    out_path = confined_path(params["output"])
    n = out_context().createNode("baketexture::3.0", params.get("name"))
    _try_set(n, "vm_uvoutputpicture1", out_path)
    if "resolution" in params:
        r = int(clamp(int(params["resolution"]), 16, 16384))
        _try_set(n, "vm_uvunwrapresx", r)
        _try_set(n, "vm_uvunwrapresy", r)
    if params.get("input"):
        _try_set(n, "vm_uvobject1", resolve_node(params["input"]).parent().path())
    return {"node": n.path(), "output": out_path, "rendered": False,
            "note": "bake graph wired; start the bake yourself"}


@endpoint("flipbook")
def flipbook(params):
    """Render a viewport flipbook (OpenGL ROP) to a confined output sequence. HEAVY-SCENE GUARD:
    do NOT run this on a heavy heightfield/volume scene — the GPU cook can freeze the session; grab
    the OS screen instead. Executes (writes preview frames) — it is the agent's cheap eyes."""
    out_path = confined_path(params["output"])
    n = out_context().createNode("opengl", params.get("name"))
    n.parm("picture").set(out_path)
    _try_set(n, "mkpath", True)
    if params.get("camera"):
        _try_set(n, "camera", resolve_node(params["camera"]).path())
    if "resx" in params:
        _try_set(n, "res1", int(clamp(int(params["resx"]), 1, 16384)))
        _try_set(n, "tres", True)
    if "resy" in params:
        _try_set(n, "res2", int(clamp(int(params["resy"]), 1, 16384)))
    frames = params.get("frames")
    if frames and len(frames) == 2:
        n.parm("trange").set(1)
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        n.parm("f1").set(f1)
        n.parm("f2").set(f2)
    n.render()
    return {"node": n.path(), "output": out_path, "frames": frames}


@endpoint("snapshot")
def snapshot(params):
    """See/screenshot the 3D result — render a single viewport or camera frame to a PNG returned
    INLINE in the tool result (the agent's eyes for image->3D verification). Supply `camera` for the
    reliable OpenGL-ROP path (honours resx/resy + aa); with no camera it falls back to a viewport
    flipbook (needs an open Scene Viewer). The PNG is written to a filename UNDER the working directory
    (confined; never a caller path), and the return echoes the ACTUAL output `res` [w,h] read from the
    file + `confined_to_working_dir`. Pair with read_geo_stats (bbox/size) to catch "looks right, is 3x
    too big". HEAVY-SCENE GUARD: avoid on a heavy heightfield/volume scene — the GL grab can freeze;
    screenshot the OS screen instead.
    """
    frame_num = params.get("frame")
    if frame_num is not None:
        hou.setFrame(float(frame_num))
    fname = "snapshot_f%04d.png" % int(hou.frame())
    tmp = confined_path(os.path.join(WORKING_DIR, fname)).replace("\\", "/")

    camera = params.get("camera")
    if camera:
        cam = resolve_node(camera)
        rop = out_context().createNode("opengl", "snap_rop")
        _try_set(rop, "camera", cam.path())
        _try_set(rop, "trange", 0)  # current frame
        _try_set(rop, "picture", tmp)
        # REFERENCE-PLATE COMPOSITE (review item-6): the opengl ROP has its OWN background-image parm
        # (`bgimage`) and does NOT inherit the camera's vm_background — so a snapshot through a camera
        # that carries a reference plate would render geometry over a BLANK background, silently
        # breaking the image->3D verify loop (render the model OVER the reference photo). Forward the
        # camera's enabled plate into the ROP so it actually composites. The path is already
        # confined (add_camera runs it through confined_path when setting vm_background).
        bge, bgp = cam.parm("vm_bgenable"), cam.parm("vm_background")
        if bge is not None and bgp is not None and bge.eval() and bgp.eval():
            _try_set(rop, "bgimage", bgp.eval())
        if params.get("aa"):
            # aamode is a 7-entry MENU (none/aa2/aa4/aa8/aa16/aa32/aa64 = indices 0..6); clamp to a
            # valid index so a high `aa` maps to the strongest mode instead of an out-of-range set.
            _try_set(rop, "aamode", int(clamp(int(params["aa"]), 0, 6)))
        # resolution: drive via the camera's own resx/resy (known parm names), fit into 1920x1080
        # when the caller does not specify, restoring the camera's res afterward.
        crx_p, cry_p = cam.parm("resx"), cam.parm("resy")
        saved_res = None
        res_used = None
        if crx_p is not None and cry_p is not None:
            crx, cry = int(crx_p.eval()), int(cry_p.eval())
            if params.get("resx") and params.get("resy"):
                tx, ty = int(params["resx"]), int(params["resy"])
            else:
                tx, ty = crx, cry
                mw, mh = 1920, 1080
                if tx > mw or ty > mh:
                    s = min(mw / float(tx), mh / float(ty))
                    tx, ty = max(1, int(tx * s)), max(1, int(ty * s))
            saved_res = (crx, cry)
            try:
                crx_p.set(tx)
                cry_p.set(ty)
                res_used = [tx, ty]
            except Exception:
                saved_res = None
        try:
            rop.render()
        finally:
            if saved_res is not None:
                try:
                    crx_p.set(saved_res[0])
                    cry_p.set(saved_res[1])
                except Exception:
                    pass
        mode = "opengl_rop"
    else:
        sv = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
        if sv is None:
            raise ValueError("no scene viewer open (supply a 'camera' for the ROP path instead)")
        vp = sv.curViewport()
        if params.get("frame_view"):
            vp.frameAll()
        fb = sv.flipbookSettings().stash()
        fb.frameRange((hou.frame(), hou.frame()))
        if params.get("resx") and params.get("resy"):
            fb.useResolution(True)
            fb.resolution((int(params["resx"]), int(params["resy"])))
        fb.output(tmp)
        sv.flipbook(vp, fb)
        res_used = None
        mode = "flipbook"

    if not os.path.isfile(tmp):
        raise ValueError("render produced no file")
    # Echo the ACTUAL output resolution (review fix: the flipbook branch used to return res:null, so a
    # driving agent couldn't confirm what it got). Read the true width/height from the PNG header — the
    # ground truth after any fit/clamp — regardless of which branch produced it.
    try:
        with open(tmp, "rb") as _fh:
            _head = _fh.read(24)
        if _head[:8] == b"\x89PNG\r\n\x1a\n":
            import struct
            _w, _h = struct.unpack(">II", _head[16:24])
            res_used = [int(_w), int(_h)]
    except Exception:
        pass
    return {"path": tmp, "mode": mode, "frame": hou.frame(), "res": res_used,
            "confined_to_working_dir": True}


# ── UI capture: an OS-real screenshot so any agent driving the MCP has total clarity on Houdini ──

# Requested panel -> Houdini pane-tab type. This is the ROBUST route: we ask Houdini for the pane
# tab of the given type (same API `snapshot` already uses for the SceneViewer) and grab that tab's
# Qt widget geometry, instead of guessing at Qt class names. Falls back to fragment matching, then
# to the whole window.
def _pane_tab_types():
    """Map panel name -> hou.paneTabType enum (built lazily so import never depends on the enum).
    Every value here is a real H21 pane-tab type; each resolves to a live tab via paneTabOfType()
    only when that pane is actually OPEN on the current desktop (else capture_ui falls back to the
    whole window and says so in `panel`)."""
    return {
        "network": hou.paneTabType.NetworkEditor,     # node graph
        "viewport": hou.paneTabType.SceneViewer,      # 3D scene view
        "parameters": hou.paneTabType.Parm,           # parameter editor
        "spreadsheet": hou.paneTabType.DetailsView,   # geometry spreadsheet (attribute VALUES)
    }


def _qt_widgets():
    """Houdini ships PySide (6 on H21, 2 on older). Return the QtWidgets module either way."""
    try:
        from PySide6 import QtWidgets  # noqa: PLC0415
        return QtWidgets
    except Exception:
        from PySide2 import QtWidgets  # noqa: PLC0415
        return QtWidgets


def _qt_core():
    """Houdini ships PySide (6 on H21, 2 on older). Return the QtCore module either way (for the Qt
    aspect/transform enums used by QPixmap/QImage.scaled)."""
    try:
        from PySide6 import QtCore  # noqa: PLC0415
        return QtCore
    except Exception:
        from PySide2 import QtCore  # noqa: PLC0415
        return QtCore


def _qt_gui():
    """QtGui module (for QPixmap, used to read back the GL viewport capture)."""
    try:
        from PySide6 import QtGui  # noqa: PLC0415
        return QtGui
    except Exception:
        from PySide2 import QtGui  # noqa: PLC0415
        return QtGui


def _pane_screen_rect(panel):
    """Resolve the requested pane to its on-screen rectangle via the documented H21 accessor
    hou.PaneTab.qtScreenGeometry() -> QRect (top-left in SCREEN coordinates). This is the robust
    route: it exists on EVERY pane tab (base PaneTab), needs no Qt-widget-tree walking, and is
    multi-monitor correct (screen coords). Returns (x, y, w, h) in logical screen pixels, or None if
    the pane isn't open on the current desktop (→ caller falls back to the whole window). Never
    raises — any API gap yields None.

    NOTE the bug this replaces: the prior code called tab.qtWidget(), which does NOT exist on H21
    (PaneTab exposes qtScreenGeometry/qtParentWindow, not qtWidget), AND built its pane map with
    hou.paneTabType.Parameter, which is not a real member (it is `Parm`) — so map construction itself
    raised and pane isolation silently degraded to the whole window for EVERY panel."""
    ptype = _pane_tab_types().get(panel)
    if ptype is None:
        return None
    try:
        tab = hou.ui.paneTabOfType(ptype)
    except Exception:
        tab = None
    if tab is None:
        return None
    try:
        r = tab.qtScreenGeometry()          # PySide QRect, screen coords
        x, y, w, h = int(r.x()), int(r.y()), int(r.width()), int(r.height())
        if w > 0 and h > 0:
            return (x, y, w, h)
    except Exception:
        pass
    return None


# capture_ui inline-image budget. The gateway base64-embeds this file into the MCP response, and the
# downstream client HARD-REJECTS an image content block much past ~1 MB. At real display resolution a
# whole-window PNG blows past that (the P0 bug: "read the node graph" errored instead of returning an
# image). So cap the ENCODED file here — keep it <= _CAPTURE_MAX_BYTES so the capture always inlines; a
# smaller image beats a hard error. base64 inflates ~4/3, so ~900 KB on disk stays under a ~1.2 MB wire
# payload.
_CAPTURE_MAX_BYTES = 900_000
_CAPTURE_MIN_DIM = 400          # readability floor: never auto-shrink the short edge below this


def _scaled(img, w, h):
    """Downscale a QPixmap/QImage to FIT within (w, h) keeping aspect (smooth). Duck-typed: QPixmap and
    QImage share this scaled() signature, so the size logic is exercisable on a headless QImage."""
    qtc = _qt_core()
    qt = qtc.Qt
    keep = getattr(qt, "KeepAspectRatio", None) or qt.AspectRatioMode.KeepAspectRatio
    smooth = getattr(qt, "SmoothTransformation", None) or qt.TransformationMode.SmoothTransformation
    return img.scaled(int(w), int(h), keep, smooth)


def _save_capture(img, base_no_ext):
    """Save a QPixmap/QImage under the working dir, AUTO-DOWNSCALING/RECOMPRESSING so the encoded file
    stays <= _CAPTURE_MAX_BYTES (so the gateway can inline it under the MCP client's ~1 MB image cap).
    Strategy: try PNG at the given size first; if it's over the cap, recompress to JPEG and progressively
    shrink until it fits (or the readability floor is reached) — a smaller image is ALWAYS returned in
    place of a hard error. `base_no_ext` is joined with the chosen extension and confined byte-for-byte
    like every write here. Duck-typed on `img` (works on a headless QImage for unit tests). Returns
    (path, fmt, downscaled, width, height, nbytes)."""
    png_path = confined_path(base_no_ext + ".png").replace("\\", "/")
    if not img.save(png_path, "PNG"):
        raise RuntimeError("failed to save capture PNG to %s" % png_path)
    n = os.path.getsize(png_path)
    if n <= _CAPTURE_MAX_BYTES:
        return png_path, "PNG", False, img.width(), img.height(), n

    # Oversized PNG -> recompress as JPEG, shrinking until under the cap (or at the size floor).
    jpg_path = confined_path(base_no_ext + ".jpg").replace("\\", "/")
    cur = img
    quality = 88
    best = None
    for _ in range(16):
        if not cur.save(jpg_path, "JPEG", quality):
            break
        n = os.path.getsize(jpg_path)
        best = (jpg_path, "JPEG", True, cur.width(), cur.height(), n)
        if n <= _CAPTURE_MAX_BYTES:
            break
        if min(cur.width(), cur.height()) <= _CAPTURE_MIN_DIM:
            if quality > 55:            # at the size floor: one firmer quality drop, then accept
                quality = 55
                continue
            break
        cur = _scaled(cur, cur.width() * 0.8, cur.height() * 0.8)
    if best is None:                    # JPEG unavailable on this build -> keep the (over-cap) PNG
        return png_path, "PNG", False, img.width(), img.height(), os.path.getsize(png_path)
    try:                                # drop the oversized PNG; only the delivered JPEG remains
        os.remove(png_path)
    except OSError:
        pass
    return best


@endpoint("capture_ui")
def capture_ui(params):
    """LEAK-SAFE screenshot of the LIVE Houdini interface -> a confined image in the working directory,
    inlined so the caller SEES it. Captures Houdini's OWN rendered content only — NEVER a screen grab —
    so another window sitting in front of Houdini (the normal case: the driving agent's own app is
    frontmost) can never bleed into the image. This is a privacy + correctness guarantee.

    Two capture paths, both occlusion-immune:
      * panel='viewport' -> renders Houdini's own GL viewport buffer (a single-frame flipbook, the same
        engine `snapshot` uses) — the real 3D scene regardless of what window is in front. Needs a Scene
        Viewer open. Frame it first (frame_selected / home_view), or pass frame_view=true to frame-all.
      * panel='network' | 'parameters' | 'spreadsheet' | 'window' (default 'window') -> grabs the Houdini
        window's OWN painted content (QWidget.grab), cropped to the pane. UI panes render exactly; the
        3D-viewport region INSIDE these grabs is blank (Qt cannot grab a native GL child) — so use
        panel='viewport' to see the 3D. A pane that isn't open falls back to the whole window (reported
        back in `panel`, which then reads 'window' not the request).

    Sizing — so a real-display capture INLINES instead of hard-erroring on the ~1 MB image cap:
      resx / resy   : optional max width / height in pixels; the grab is downscaled to FIT within them
                      (aspect preserved; never upscaled).
      max_dimension : optional cap on the long edge (pixels); a convenient single-number downscale.
    Regardless of those, the encoded file is AUTO-DOWNSCALED/RECOMPRESSED (PNG -> JPEG, shrinking) when
    it would exceed the inline budget, so a smaller image is always returned rather than an error.
    Returns {path, panel, requested, width, height, res:[w,h], format, bytes, downscaled} -- `downscaled`
    is true when the returned image was shrunk or recompressed from the raw grab (for any reason).
    """
    panel = str(params.get("panel", "window")).lower()
    mw = hou.ui.mainQtWindow()
    if mw is None:
        raise RuntimeError("no Houdini main window (is this an interactive session?)")

    used_panel = panel
    if panel == "viewport":
        # Houdini's OWN GL buffer — a single-frame flipbook, the same engine as `snapshot`. This renders
        # the 3D scene from Houdini's GL context, so it is occlusion-immune and can NEVER contain another
        # window's pixels (unlike a screen grab). A screen crop was the old privacy leak.
        sv = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
        if sv is None:
            raise ValueError("no Scene Viewer open to capture the 3D viewport; open one, or use "
                             "snapshot(camera=...) for a GL render")
        vp = sv.curViewport()
        if params.get("frame_view"):
            try:
                vp.frameAll()
            except Exception:  # noqa: BLE001 — framing is best-effort
                pass
        gl_png = confined_path(
            os.path.join(WORKING_DIR, "capture_viewport_f%04d.png" % int(hou.frame()))).replace("\\", "/")
        fb = sv.flipbookSettings().stash()
        fb.frameRange((hou.frame(), hou.frame()))
        if params.get("resx") and params.get("resy"):
            fb.useResolution(True)
            fb.resolution((int(params["resx"]), int(params["resy"])))
        fb.output(gl_png)
        sv.flipbook(vp, fb)
        if not os.path.isfile(gl_png):
            raise ValueError("viewport GL capture produced no file")
        pix = _qt_gui().QPixmap(gl_png)
        if pix.isNull():
            raise ValueError("viewport GL capture could not be read back")
    else:
        # The Houdini window's OWN painted content. QWidget.grab() re-renders the widget tree offscreen
        # from its own paint — occlusion-IMMUNE, and by construction it can never contain another
        # application's pixels (no screen is read). GL-viewport regions render blank here; that is why
        # panel='viewport' takes the GL path above.
        pix = mw.grab()
        if pix is None or pix.isNull() or pix.width() == 0:
            raise RuntimeError("could not grab the Houdini window content")
        if panel != "window":
            r = _pane_screen_rect(panel)      # (px,py,pw,ph) in screen coords, or None if pane not open
            if r is not None:
                px, py, pw, ph = r
                wtl = mw.mapToGlobal(mw.rect().topLeft())   # window top-left in screen coords
                dpr = pix.devicePixelRatio() or 1.0
                # Crop the WINDOW pixmap to the pane, converting the pane's screen rect to window-local.
                cropped = pix.copy(int((px - wtl.x()) * dpr), int((py - wtl.y()) * dpr),
                                   int(pw * dpr), int(ph * dpr))
                if cropped is not None and not cropped.isNull() and cropped.width() > 0:
                    pix = cropped
                else:
                    used_panel = "window"     # pane rect outside the window grab -> honest fallback
            else:
                used_panel = "window"         # pane not open -> whole window (honest)

    # Optional caller-requested downscale (never upscales a screenshot): fit within resx/resy and/or a
    # max_dimension long-edge cap. Anything already smaller keeps the native grab.
    tw, th = pix.width(), pix.height()
    md = params.get("max_dimension")
    if md is not None:
        md = int(clamp(int(md), _CAPTURE_MIN_DIM, 16384))
        tw, th = min(tw, md), min(th, md)
    if params.get("resx") is not None:
        tw = min(tw, int(clamp(int(params["resx"]), 16, 16384)))
    if params.get("resy") is not None:
        th = min(th, int(clamp(int(params["resy"]), 16, 16384)))
    req_scaled = False
    if tw < pix.width() or th < pix.height():
        pix = _scaled(pix, tw, th)
        req_scaled = True

    base = os.path.join(WORKING_DIR, "capture_%s_f%04d" % (used_panel, int(hou.frame())))
    path, fmt, auto_down, w, h, nbytes = _save_capture(pix, base)
    return {"path": path, "panel": used_panel, "requested": panel,
            "width": w, "height": h, "res": [w, h], "format": fmt,
            "bytes": nbytes, "downscaled": bool(auto_down or req_scaled)}


# ── define_hda (package a network into a reusable digital asset; EXPORT-CONFINED) ────────────────────
# The "make this network a reusable tool" op. DATA-ONLY: createDigitalAsset serializes an existing node
# network into a .hda(nc) file and opens NO new code path (probe-verified on H21.0.671: the default
# packaged subnet emits only Contents.gz/CreateScript/DialogScript/InternalFileOptions — no
# PythonModule/OnCreated/... script sections; the op injects no scripts of its own and never executes
# the packaged network). Any code inside the subnet can only have come from the existing typed data-only
# tools, so it is already vetted. The write is realpath-confined like every export. LICENSE NOTE: HOM
# does NOT gate the extension by license (all of .hda/.hdanc/.otl/.otlnc write successfully); the
# non-commercial restriction is a blessing embedded in the file, so the caller CHOOSES the extension
# (Apprentice -> .hdanc). End-to-end round-trip (write -> installFile -> re-instantiate -> cook) proven.
_HDA_EXTS = (".hda", ".hdanc", ".otl", ".otlnc")


def _hda_ident(s):
    """Node-type-name-safe subset: keep ASCII [A-Za-z0-9_], turn others into '_', strip edges."""
    return "".join(c if (c.isascii() and (c.isalnum() or c == "_")) else "_"
                   for c in str(s)).strip("_")


@endpoint("define_hda")
def define_hda(params):
    """Package an existing SOP subnet into a reusable, path-confined Houdini Digital Asset. Data-only:
    serializes a node network the AI built via typed tools; opens no new code path.

    node       : the subnet to package (must satisfy canCreateDigitalAsset() -- i.e. a subnet).
    output     : confined write path ending in .hda/.hdanc/.otl/.otlnc (Apprentice -> .hdanc).
    type_name  : asset node-type name; used verbatim if it already contains '::' (a full ns::name::ver).
    namespace  : (opt) namespace component, combined with type_name + version -> ns::name::ver.
    version    : (opt, default '1.0') version component.
    label      : (opt) tab-menu description (default = the type name).
    min_inputs / max_inputs : (opt) input-connector counts (0..4).
    description: (opt) author comment metadata.
    Returns the new node path, its final type name, the written library path, and the asset sections."""
    node = resolve_node(params["node"])
    if not node.canCreateDigitalAsset():
        raise ValueError("node %s cannot become an HDA (it must be a subnet)" % node.path())
    src_path = node.path()   # capture BEFORE createDigitalAsset (change_node_type deletes this node)

    out = confined_path(str(params["output"]))
    if not out.lower().endswith(_HDA_EXTS):
        raise ValueError("output must end in one of %s" % (_HDA_EXTS,))

    raw_type = str(params["type_name"])
    if "::" in raw_type:
        full = raw_type                                  # caller supplied a full ns::name::ver
    else:
        base = _hda_ident(raw_type)
        if not base:
            raise ValueError("type_name is empty after sanitizing to an identifier")
        ns = _hda_ident(params["namespace"]) if params.get("namespace") else ""
        ver = str(params.get("version", "1.0")).strip() or "1.0"
        full = hou.hda.fullNodeTypeNameFromComponents("", ns, base, ver)

    label = str(params.get("label") or full)
    mn = int(clamp(int(params.get("min_inputs") or 0), 0, 4))
    mx_raw = params.get("max_inputs")
    mx = int(clamp(int(mx_raw), 0, 4)) if mx_raw is not None else mn
    if mx < mn:
        mx = mn

    try:
        new = node.createDigitalAsset(
            name=full, hda_file_name=out, description=label,
            min_num_inputs=mn, max_num_inputs=mx,
            save_as_embedded=False,          # never embed in the .hip — always to our confined file
            change_node_type=True, create_backup=True,
            comment=(str(params["description"]) if params.get("description") else None),
        )
    except hou.OperationFailed as exc:
        raise ValueError("createDigitalAsset failed: %s" % (str(exc)[:200]))

    d = new.type().definition()
    return {"node": new.path(), "type_name": new.type().name(),
            "library": d.libraryFilePath(), "output": out,
            "sections": sorted(d.sections().keys()), "packaged_from": src_path}

"""SideFX Labs FX Tools — data-only handlers. Params verified against live H21.0.671 via hython
probe and headless-cooked.

Covers the FX-category SOP HDAs: flow-map authoring (flowmap / guide / obstacle / to_color /
visualize), kelvin wakes, SPH splatter + procedural smoke sources, volume look adjust, RBD
destruction cleanup + edge strip, and volume/particle looping (loop_volume / make_loop / lightning).

Each handler exposes a curated scalar/menu subset; folder headers, ramps and pure-UI toggles stay
at HDA default. Cost levers (voxel/particle separation, substeps, arc/spread counts) are hard
clamped. SECURITY: this lane carries no file WRITE surface we expose — every image-read path
(flowmap_visualize diffTexture2/flowmapTexture, lightning texture), the lightning on-disk export
(`sopoutput` + `execute` "Save to Disk" button) and OpenCL/callback toggles are LEFT UNSET and never
exposed. No endpoint runs code or presses a render/export button.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)




def _set_vec_uniform(node, parm, value):
    """Set every component of a vector parm-tuple (e.g. splatter `rad`, procedural_smoke `size`)
    to one scalar — exposes a uniform-scale control for a genuinely vector-valued HDA parm."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set([float(value)] * len(pt))
        return True
    except Exception:
        return False


def _tok_set(node, parm, token, allowed):
    """Set a string-token menu (e.g. kelvin `normal` x/y/z) by its token value, validated."""
    if token in allowed:
        return _try_set(node, parm, str(token))
    return False


def _finish_gen(geo, n):
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


def _finish_chain(n):
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 1. flowmap (chain; in0 surface w/ UV) ─────────────────────────────────────────────────────────
@endpoint("flowmap")
def flowmap(params):
    """SideFX Labs Flowmap (labs::flowmap::2.0) — authors a per-point flow-vector attribute over a
    UV'd surface (`input`, input 0) for driving flow-map material distortion (rivers, lava). `method`
    picks the flow-solve mode. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::flowmap::2.0", params.get("name"))
    if "method" in params:
        _try_set(n, "method", int(clamp(int(params["method"]), 0, 2)))
    if "visualize_flow" in params:
        _try_set(n, "visualize_flow", bool(params["visualize_flow"]))
    return _finish_chain(n)


# ── 2. flowmap_guide (chain; in0 surface, in1 guide curves) ───────────────────────────────────────
@endpoint("flowmap_guide")
def flowmap_guide(params):
    """SideFX Labs Flowmap Guide (labs::flowmap_guide) — steers a surface flow map toward hand-drawn
    guide curves. `input` (input 0) = the flow surface; `guide` (input 1) = guide curves. `strength`
    blends the guide in; `maxsamplecount` (guide samples) is clamped. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::flowmap_guide", params.get("name"))
    if params.get("guide"):
        bridge_input(n, params["guide"], index=1, name_hint="guide")
    if "strength" in params:
        _try_set(n, "strength", clamp(float(params["strength"]), 0.0, 10.0))
    if "effect_width" in params:
        _try_set(n, "effect_width", clamp(float(params["effect_width"]), 0.0, 100.0))
    if "falloff" in params:
        _try_set(n, "falloff", clamp(float(params["falloff"]), 0.0, 10.0))
    if "maxsamplecount" in params:
        _try_set(n, "maxsamplecount", int(clamp(int(params["maxsamplecount"]), 1, 512)))
    if "bReverseDirection" in params:
        _try_set(n, "bReverseDirection", bool(params["bReverseDirection"]))
    return _finish_chain(n)


# ── 3. flowmap_obstacle (chain; in0 surface, in1 obstacle geo) ────────────────────────────────────
@endpoint("flowmap_obstacle")
def flowmap_obstacle(params):
    """SideFX Labs Flowmap Obstacle (labs::flowmap_obstacle::3.0) — deflects a surface flow map around
    obstacle geometry. `input` (input 0) = the flow surface; `obstacle` (input 1) = the obstacle.
    `division_size` is the deflection voxel size (smaller = finer + costlier) and is clamped to a sane
    floor. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::flowmap_obstacle::3.0", params.get("name"))
    if params.get("obstacle"):
        bridge_input(n, params["obstacle"], index=1, name_hint="obstacle")
    if "strength" in params:
        _try_set(n, "strength", clamp(float(params["strength"]), 0.0, 10.0))
    if "division_size" in params:
        _try_set(n, "division_size", clamp(float(params["division_size"]), 1e-2, 100.0))  # voxel floor
    if "dilate_volume" in params:
        _try_set(n, "dilate_volume", clamp(float(params["dilate_volume"]), 0.0, 50.0))
    if "blur_strength" in params:
        _try_set(n, "blur_strength", clamp(float(params["blur_strength"]), 0.0, 50.0))
    return _finish_chain(n)


# ── 4. flowmap_to_color (chain; in0 flowmap geo) ──────────────────────────────────────────────────
@endpoint("flowmap_to_color")
def flowmap_to_color(params):
    """SideFX Labs Flowmap To Color (labs::flowmap_to_color) — bakes a flow-vector attribute into an
    RG(B) color the engine reads as a flow map. `input` (input 0) = flow-map geo. `flip_g` flips the
    green channel for Unity's convention. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::flowmap_to_color", params.get("name"))
    if "node_vis_enabled" in params:
        _try_set(n, "node_vis_enabled", bool(params["node_vis_enabled"]))
    if "flip_g" in params:
        _try_set(n, "flip_g", bool(params["flip_g"]))
    return _finish_chain(n)


# ── 5. flowmap_visualize (chain; in0 flowmap geo) ─────────────────────────────────────────────────
@endpoint("flowmap_visualize")
def flowmap_visualize(params):
    """SideFX Labs Flowmap Visualize (labs::flowmap_visualize) — previews a flow map by animating a
    distortion on `input` (input 0). `speed`/`distortion`/`time` drive the preview; `output` picks the
    preview channel. SECURITY: the two texture-image READ paths (diffTexture2, flowmapTexture) are
    NOT exposed — this handler carries no file surface."""
    n = child_after(params["input"], "labs::flowmap_visualize", params.get("name"))
    if "uvtiling" in params:
        _set_vec_uniform(n, "uvtiling", clamp(float(params["uvtiling"]), 1e-3, 1000.0))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), -100.0, 100.0))
    if "distortion" in params:
        _try_set(n, "distortion", clamp(float(params["distortion"]), 0.0, 10.0))
    if "mode" in params:
        _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 8)))
    if "time" in params:
        _try_set(n, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "output" in params:
        _try_set(n, "output", int(clamp(int(params["output"]), 0, 1)))
    return _finish_chain(n)


# ── 6. kelvin_wakes_deformer (chain; in0 surface, in1 moving object/curve) ────────────────────────
_KELVIN_UP = ("x", "y", "z")
_KELVIN_TARGET = ("points", "heightfield")
_KELVIN_INPUT = ("objects", "curve")
_KELVIN_POLYAS = ("straight", "subd", "interp")


@endpoint("kelvin_wakes_deformer")
def kelvin_wakes_deformer(params):
    """SideFX Labs Kelvin Wakes Deformer (labs::kelvin_wakes_deformer::1.0) — deforms a water surface
    with the physically-based Kelvin wake pattern trailing a moving object. `input` (input 0) = the
    water surface (points or heightfield); `object` (input 1) = the moving object or a path curve.
    `normal` sets the up axis; `target` picks points vs heightfield; `input_mode` picks object vs
    curve. `speed` is the traversal speed. Data-only: the output-attribute-name strings and height
    layer are left at HDA default (no file surface)."""
    n = child_after(params["input"], "labs::kelvin_wakes_deformer::1.0", params.get("name"))
    if params.get("object"):
        bridge_input(n, params["object"], index=1, name_hint="object")
    if "normal" in params:
        _tok_set(n, "normal", str(params["normal"]), _KELVIN_UP)
    if "target" in params:
        _tok_set(n, "target", str(params["target"]), _KELVIN_TARGET)
    if "input_mode" in params:
        _tok_set(n, "input", str(params["input_mode"]), _KELVIN_INPUT)
    if "treatpolysas" in params:
        _tok_set(n, "treatpolysas", str(params["treatpolysas"]), _KELVIN_POLYAS)
    if "gravity" in params:
        _try_set(n, "gravity", clamp(float(params["gravity"]), 0.0, 100.0))
    if "curvestart" in params:
        _try_set(n, "curvestart", clamp(float(params["curvestart"]), -1e5, 1e5))
    if "speed" in params:
        _try_set(n, "speed", clamp(float(params["speed"]), 0.0, 1000.0))
    if "edgeblend" in params:
        _try_set(n, "edgeblend", clamp(float(params["edgeblend"]), 0.0, 100.0))
    if "suppress_radius" in params:
        _try_set(n, "suppress_radius", clamp(float(params["suppress_radius"]), 0.0, 1000.0))
    if "enable_supersample" in params:
        _try_set(n, "enable_supersample", bool(params["enable_supersample"]))
    if "enable_falloff" in params:
        _try_set(n, "enable_falloff", bool(params["enable_falloff"]))
    if "relative_falloff" in params:
        _try_set(n, "relative_falloff", bool(params["relative_falloff"]))
    if "magnitude_multiplier" in params:
        _try_set(n, "magnitude_multiplier", clamp(float(params["magnitude_multiplier"]), 0.0, 100.0))
    return _finish_chain(n)


# ── 7. splatter (generator; opt in0 source, opt in1 collision) — SPH fluid source ─────────────────
@endpoint("splatter")
def splatter(params):
    """SideFX Labs Splatter (labs::splatter) — a self-contained SPH fluid-splatter SOURCE that builds
    a fresh /obj geo emitting particle fluid (paint/blood splats). Optional `source` (input 0) and
    `collision` (input 1) geo. `radius` is a uniform emitter radius; `particleseparation` is the
    particle spacing (smaller = far more particles) and is clamped to a sane floor. `substeps` is
    clamped. SECURITY/cost: OpenCL and the reset-sim button are left at default and never exposed.
    Fails on name collision. (Cooks at the current frame; drives an SPH sim downstream.)"""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::splatter")
    if params.get("source"):
        bridge_input(n, params["source"], index=0, name_hint="source")
    if params.get("collision"):
        bridge_input(n, params["collision"], index=1, name_hint="collision")
    if "radius" in params:
        _set_vec_uniform(n, "rad", clamp(float(params["radius"]), 1e-2, 100.0))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1e-3, 1000.0))
    if "freq" in params:
        _try_set(n, "freq", int(clamp(int(params["freq"]), 1, 64)))
    if "particleseparation" in params:
        _try_set(n, "particleseparation", clamp(float(params["particleseparation"]), 0.02, 10.0))  # cost floor
    if "defstiffness" in params:
        _try_set(n, "defstiffness", clamp(float(params["defstiffness"]), 0.0, 1e6))
    if "viscosityc" in params:
        _try_set(n, "viscosityc", clamp(float(params["viscosityc"]), 0.0, 1e6))
    if "enable_grav" in params:
        _try_set(n, "enable_grav", bool(params["enable_grav"]))
    if "startframe" in params:
        _try_set(n, "startframe", int(clamp(int(params["startframe"]), -10000, 100000)))
    if "minimumsubsteps" in params:
        _try_set(n, "minimumsubsteps", int(clamp(int(params["minimumsubsteps"]), 1, 20)))
    if "substeps" in params:
        _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 20)))  # cost cap
    if "timescale" in params:
        _try_set(n, "timescale", clamp(float(params["timescale"]), 1e-3, 100.0))
    if "add_noise" in params:
        _try_set(n, "add_noise", bool(params["add_noise"]))
    if "noise_height" in params:
        _try_set(n, "height", clamp(float(params["noise_height"]), 0.0, 100.0))
    return _finish_gen(geo, n)


# ── 8. procedural_smoke (generator; 0 inputs) — smoke volume source ───────────────────────────────
@endpoint("procedural_smoke")
def procedural_smoke(params):
    """SideFX Labs Procedural Smoke (labs::procedural_smoke) — builds a fresh /obj geo holding a
    fully-procedural smoke DENSITY volume (no sim) driven by layered noise. `size` is a uniform box
    size; `particlesep` (voxel/point separation) is clamped to a floor (smaller = far more voxels).
    `densityboost` scales the density. Fails on name collision. Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::procedural_smoke")
    if "size" in params:
        _set_vec_uniform(n, "size", clamp(float(params["size"]), 1e-2, 1000.0))
    if "particlesep" in params:
        _try_set(n, "particlesep", clamp(float(params["particlesep"]), 0.02, 10.0))  # cost floor
    if "densityboost" in params:
        _try_set(n, "densityboost", clamp(float(params["densityboost"]), 0.0, 100.0))
    if "pointpreview" in params:
        _try_set(n, "pointpreview", bool(params["pointpreview"]))
    if "elementsize" in params:
        _try_set(n, "elementsize", clamp(float(params["elementsize"]), 1e-3, 100.0))
    if "detailenable" in params:
        _try_set(n, "detailenable", bool(params["detailenable"]))
    if "noise_amp" in params:
        _try_set(n, "amp", clamp(float(params["noise_amp"]), 0.0, 100.0))
    if "rough" in params:
        _try_set(n, "rough", clamp(float(params["rough"]), 0.0, 2.0))
    if "turb" in params:
        _try_set(n, "turb", int(clamp(int(params["turb"]), 0, 16)))
    return _finish_gen(geo, n)


# ── 9. volume_adjust_look (chain; in0 density volume) ─────────────────────────────────────────────
@endpoint("volume_adjust_look")
def volume_adjust_look(params):
    """SideFX Labs Volume Adjust Look (labs::volume_adjust_look::1.0) — art-directs a smoke/pyro
    volume's LOOK (density / shadow / diffuse / emission multipliers, optional greyscale). `input`
    (input 0) = the density volume. `mode` picks the adjust mode; `greyscalemode` picks the luminance
    conversion. Data-only: the volume-field-name bindings are left at HDA default (no file surface)."""
    n = child_after(params["input"], "labs::volume_adjust_look::1.0", params.get("name"))
    if "mode" in params:
        _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 2)))
    if "greyscalemode" in params:
        _try_set(n, "greyscalemode", int(clamp(int(params["greyscalemode"]), 0, 3)))
    if "densitymul" in params:
        _try_set(n, "densitymul", clamp(float(params["densitymul"]), 0.0, 100.0))
    if "shadowmul" in params:
        _try_set(n, "shadowmul", clamp(float(params["shadowmul"]), 0.0, 100.0))
    if "diffusemul" in params:
        _set_vec_uniform(n, "diffusemul", clamp(float(params["diffusemul"]), 0.0, 100.0))
    if "diffusescalemul" in params:
        _try_set(n, "diffusescalemul", clamp(float(params["diffusescalemul"]), 0.0, 100.0))
    if "emitmul" in params:
        _set_vec_uniform(n, "emitmul", clamp(float(params["emitmul"]), 0.0, 100.0))
    if "emitscalemul" in params:
        _try_set(n, "emitscalemul", clamp(float(params["emitscalemul"]), 0.0, 100.0))
    if "relluminancer" in params:
        _try_set(n, "relluminancer", clamp(float(params["relluminancer"]), 0.0, 1.0))
    if "relluminanceg" in params:
        _try_set(n, "relluminanceg", clamp(float(params["relluminanceg"]), 0.0, 1.0))
    if "relluminanceb" in params:
        _try_set(n, "relluminanceb", clamp(float(params["relluminanceb"]), 0.0, 1.0))
    return _finish_chain(n)


# ── 10. destruction_cleanup (chain; in0 packed RBD pieces, opt in1) ───────────────────────────────
@endpoint("destruction_cleanup")
def destruction_cleanup(params):
    """SideFX Labs Destruction Cleanup (labs::destruction_cleanup::2.0) — post-processes RBD/fracture
    sim output: removes inside faces, cusps normals, regenerates piece names, optimizes pieces into
    chunks. `input` (input 0) = the PACKED fractured pieces (feed packed geometry with a `name`
    attribute); optional `constraints` (input 1). Data-only: piece-name / transfer-attribute strings
    and the frame-range are left at HDA default (no file surface)."""
    n = child_after(params["input"], "labs::destruction_cleanup::2.0", params.get("name"))
    if params.get("constraints"):
        bridge_input(n, params["constraints"], index=1, name_hint="constraints")
    if "bVisChunks" in params:
        _try_set(n, "bVisChunks", bool(params["bVisChunks"]))
    if "bFuseSurface" in params:
        _try_set(n, "bFuseSurface", bool(params["bFuseSurface"]))
    if "fuseDistance" in params:
        _try_set(n, "fuseDistance", clamp(float(params["fuseDistance"]), 0.0, 100.0))
    if "bCuspPolygons" in params:
        _try_set(n, "bCuspPolygons", bool(params["bCuspPolygons"]))
    if "mCuspMode" in params:
        _try_set(n, "mCuspMode", int(clamp(int(params["mCuspMode"]), 0, 1)))
    if "cuspAngle" in params:
        _try_set(n, "cuspAngle", clamp(float(params["cuspAngle"]), 0.0, 180.0))
    if "bGenerateName" in params:
        _try_set(n, "bGenerateName", bool(params["bGenerateName"]))
    if "optimizeIntoChunks" in params:
        _try_set(n, "optimizeIntoChunks", bool(params["optimizeIntoChunks"]))
    if "bBoundsAdjust" in params:
        _try_set(n, "bBoundsAdjust", bool(params["bBoundsAdjust"]))
    return _finish_chain(n)


# ── 11. rbd_edge_strip (chain; in0 fractured pieces) ──────────────────────────────────────────────
@endpoint("rbd_edge_strip")
def rbd_edge_strip(params):
    """SideFX Labs RBD Edge Strip (labs::rbd_edge_strip) — extracts thin edge strips along the fracture
    seams of RBD pieces (for edge chipping / detailing). `input` (input 0) = the fractured pieces
    (unpacked, with inside/outside face groups). `insideedgewidth` / `outsideedgewidth` set the strip
    widths. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::rbd_edge_strip", params.get("name"))
    if "mergepieces" in params:
        _try_set(n, "mergepieces", bool(params["mergepieces"]))
    if "insideedgewidth" in params:
        _try_set(n, "insideedgewidth", clamp(float(params["insideedgewidth"]), 0.0, 10.0))
    if "outsideedgewidth" in params:
        _try_set(n, "outsideedgewidth", clamp(float(params["outsideedgewidth"]), 0.0, 10.0))
    return _finish_chain(n)


# ── 12. loop_volume (chain; in0 volume sequence, opt in1 overlay) ─────────────────────────────────
@endpoint("loop_volume")
def loop_volume(params):
    """SideFX Labs Loop Volume (labs::loop_volume::1.0) — cross-fades a volume (smoke/pyro) sequence
    into a seamless loop. `input` (input 0) = the volume sequence. `overlaysource` picks the overlay:
    0 = self (single input, cooks standalone), 1 = a SECOND input stream (wire `overlay`, input 1).
    `blendmode` picks the cross-fade. Data-only: the volume-field bindings are left at HDA default
    (no file surface)."""
    n = child_after(params["input"], "labs::loop_volume::1.0", params.get("name"))
    if params.get("overlay"):
        bridge_input(n, params["overlay"], index=1, name_hint="overlay")
    if "overlaysource" in params:
        _try_set(n, "overlaysource", int(clamp(int(params["overlaysource"]), 0, 1)))
    if "blendmode" in params:
        _try_set(n, "blendmode", int(clamp(int(params["blendmode"]), 0, 2)))
    if "nonuniformfade" in params:
        _try_set(n, "nonuniformfade", bool(params["nonuniformfade"]))
    return _finish_chain(n)


# ── 13. make_loop (chain; in0 animated geo/volume/particles) ──────────────────────────────────────
@endpoint("make_loop")
def make_loop(params):
    """SideFX Labs Make Loop (labs::make_loop::2.1) — turns an animated sequence into a seamless loop
    (geometry, volume or particles). `input` (input 0) = the animated source. `inputtype` picks the
    data type (0 geo / 1 volume / 2 particle); `start_frame`/`end_frame` bound the loop; `loops` sets
    the double-loop count (clamped). Data-only: the Recompute-Max-ID button is not exposed."""
    n = child_after(params["input"], "labs::make_loop::2.1", params.get("name"))
    if "inputtype" in params:
        _try_set(n, "inputtype", int(clamp(int(params["inputtype"]), 0, 2)))
    if "start_frame" in params:
        _try_set(n, "start_frame", int(clamp(int(params["start_frame"]), -10000, 100000)))
    if "end_frame" in params:
        _try_set(n, "end_frame", int(clamp(int(params["end_frame"]), -10000, 100000)))
    if "loops" in params:
        _try_set(n, "loops", int(clamp(int(params["loops"]), 1, 64)))
    if "bornbeforestartmode" in params:
        _try_set(n, "bornbeforestartmode", int(clamp(int(params["bornbeforestartmode"]), 0, 1)))
    if "deadafterendmode" in params:
        _try_set(n, "deadafterendmode", int(clamp(int(params["deadafterendmode"]), 0, 1)))
    if "wrapmode" in params:
        _try_set(n, "wrapmode", int(clamp(int(params["wrapmode"]), 0, 3)))
    if "uniqueid" in params:
        _try_set(n, "uniqueid", bool(params["uniqueid"]))
    if "fadein" in params:
        _try_set(n, "fadein", bool(params["fadein"]))
    if "fadeinduration" in params:
        _try_set(n, "fadeinduration", clamp(float(params["fadeinduration"]), 0.0, 1000.0))
    if "fadeout" in params:
        _try_set(n, "fadeout", bool(params["fadeout"]))
    if "fadeoutduration" in params:
        _try_set(n, "fadeoutduration", clamp(float(params["fadeoutduration"]), 0.0, 1000.0))
    if "previs" in params:
        _try_set(n, "previs", bool(params["previs"]))
    return _finish_chain(n)


# ── 14. lightning (chain; in0 model, opt in1/in2) ─────────────────────────────────────────────────
@endpoint("lightning")
def lightning(params):
    """SideFX Labs Lightning (labs::lightning) — generates procedural lightning/arc geometry across a
    model. `input` (input 0) = the model the arcs span. `lightningarcs` sets the arc count; the spread
    (`spread_begin`/`spread_end`) and relax-scatter counts, `cols` and section `length` are clamped to
    keep polycount bounded. `beam_thickness` sets the tube radius. SECURITY: the on-disk export
    (`sopoutput` write path + `execute` "Save to Disk" button), the `namemodel` string, the noise-type
    string and the checker `texture` READ path are LEFT UNSET and never exposed — no file surface, no
    button is pressed."""
    n = child_after(params["input"], "labs::lightning", params.get("name"))
    if "primseed" in params:
        _try_set(n, "primseed", int(clamp(int(params["primseed"]), 0, 1_000_000_000)))
    if "lightningarcs" in params:
        _try_set(n, "lightningarcs", int(clamp(int(params["lightningarcs"]), 1, 64)))  # cost cap
    if "spread_begin" in params:
        _try_set(n, "numsteps2", int(clamp(int(params["spread_begin"]), 0, 200)))
    if "spread_end" in params:
        _try_set(n, "numsteps", int(clamp(int(params["spread_end"]), 0, 200)))
    if "relax_begin" in params:
        _try_set(n, "relaxiterations2", int(clamp(int(params["relax_begin"]), 0, 200)))
    if "relax_end" in params:
        _try_set(n, "relaxiterations", int(clamp(int(params["relax_end"]), 0, 200)))
    if "cols" in params:
        _try_set(n, "cols", int(clamp(int(params["cols"]), 2, 32)))  # tube cross-section cost cap
    if "length" in params:
        _try_set(n, "length", clamp(float(params["length"]), 1e-3, 1000.0))
    if "beam_thickness" in params:
        _try_set(n, "F_Radius", clamp(float(params["beam_thickness"]), 1e-4, 100.0))
    if "dist" in params:
        _try_set(n, "dist", clamp(float(params["dist"]), -1000.0, 1000.0))
    if "dist2" in params:
        _try_set(n, "dist2", clamp(float(params["dist2"]), -1000.0, 1000.0))
    if "add_noise" in params:
        _try_set(n, "T_Noise", bool(params["add_noise"]))
    if "noise_height" in params:
        _try_set(n, "height", clamp(float(params["noise_height"]), 0.0, 100.0))
    if "noise_elementsize" in params:
        _try_set(n, "elementsize", clamp(float(params["noise_elementsize"]), 1e-3, 100.0))
    if "noise_rough" in params:
        _try_set(n, "rough", clamp(float(params["noise_rough"]), 0.0, 2.0))
    return _finish_chain(n)

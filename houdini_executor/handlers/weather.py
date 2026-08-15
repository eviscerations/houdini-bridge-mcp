"""Weather / atmospherics / ocean handlers (Stage 11). Params verified against the live probe.

Ocean is the large-water primitive (flat spectral surface + optional FLIP coupling). `sky` and
`fog` are intentionally NOT registered — see the TODO at the bottom (no valid node type surfaced
in the probe for either on this build).
"""

import hou
from houdini_executor.server import endpoint, child_after, clamp, resolve_node, bridge_into
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)






def _str_menu_set(node, parm, token, tokens):
    """Set a STRING-type menu parm by its token string directly (probe-safe)."""
    p = node.parm(parm)
    if p is None or token not in tokens:
        return False
    try:
        p.set(token)
        return True
    except Exception:
        return False


# Cloud lane menu tokens — live-probed on H21.0.671. An earlier
# guess had cloudnoise.noisetype = billowy/wispy; the REAL tokens are onoise/snoise/anoise/xnoise/
# correctnoise (STRING menu, default snoise). cloud::2.0.uniformsamples is an ordered Menu (max|size).
_CLOUD_UNIFORMSAMPLES = ("max", "size")                                          # uniformsamples (Menu=idx)
_CLOUDNOISE_TYPE = ("onoise", "snoise", "anoise", "xnoise", "correctnoise")      # noisetype (STRING menu)
# ── modern Cloud Shape toolset (H20+) menu tokens (all STRING-token menus) ──
_CLOUDSHAPE_TYPE = ("cu", "cb")                          # cloudshapegenerate cloudtype (cumulus / cumulonimbus)
_CU_SPECIES = ("hum", "med", "con")                      # cuspecies (Humilis / Mediocris / Congestus)
_CB_SPECIES = ("cal", "cap")                             # cbspecies (Calvus / Capillatus)
_CLOUD_NOISE_BASIS = ("alligator", "perlin", "simplex", "fastsimplex")  # billowy/clip basis


@endpoint("ocean_surface")
def ocean_surface(params):
    """Flat spectral large-water surface: a grid deformed by an ocean spectrum (Ocean Evaluate 2.0).
    Creator: FAILS on name collision."""
    name = params["name"]
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    grid = g.createNode("grid", "surface")
    _try_set(grid, "sizex", clamp(float(params.get("size", 100.0)), 1.0, 1e6))
    _try_set(grid, "sizey", clamp(float(params.get("size", 100.0)), 1.0, 1e6))
    spec = g.createNode("oceanspectrum", "spectrum")
    if "resolution" in params:
        _try_set(spec, "res", int(clamp(int(params["resolution"]), 4, 12)))
    if "wind_speed" in params:
        _try_set(spec, "windspeed", clamp(float(params["wind_speed"]), 0.0, 200.0))
    if "direction" in params:
        _try_set(spec, "winddir", clamp(float(params["direction"]), -360.0, 360.0))
    if "chop" in params:
        _try_set(spec, "chopscale", clamp(float(params["chop"]), 0.0, 10.0))
    if "wave_height" in params:
        _try_set(spec, "ampscale", clamp(float(params["wave_height"]), 0.0, 100.0))
    ev = g.createNode("oceanevaluate::2.0", "evaluate")
    ev.setFirstInput(grid)
    ev.setInput(1, spec)
    ev.setDisplayFlag(display)
    ev.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "spectrum": spec.path(), "evaluate": ev.path()}


_OCEANFOAM_MODE = ("emit", "solve")   # mode — ordered Menu (index-stored)


@endpoint("ocean_foam")
def ocean_foam(params):
    """Generate foam from an ocean spectrum / surface (Ocean Foam SOP). `input` = the ocean SOP.
    EMISSION (both modes): `amount` = foam particle density (parm `density`), `threshold` = min-cusp gate
    (parm `mincusp`, auto-enables domincusp). `mode` (emit|solve) picks Emitter (emit criteria only) vs
    Solver (also runs the 2-D foam sim). SOLVER-tab params (real parm -> range, live-probed H21.0.671):
    life=life expectancy s (life, 0..100), life_variance (lifevar, 0..100), drift_rate (driftrate, 0..1),
    preserve_foam (preservefoam toggle), min_foam_density (minfoamdensity, 0..1000),
    max_foam_density (maxfoamdensity, 0..1000), preservation_rate (foampreserverate, 0..100 -- >1
    preserves clumps indefinitely), reduction_rate (foamreducerate, 0..100), keep_attribs (ptkeep, the
    render attribute list). SIMULATION-tab: start_frame (startframe int), substeps (int 1..100),
    cache_enabled (cacheenabled toggle -- IN-MEMORY only, NO disk path), cache_memory_mb (cachemaxsize
    int MB). Chains after `input`. BUILT (one cook)."""
    n = child_after(params["input"], "oceanfoam", params.get("name"))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _OCEANFOAM_MODE)
    # ── emission (both modes) ──
    if "amount" in params:
        _try_set(n, "density", clamp(float(params["amount"]), 0.0, 1e6))
    if "threshold" in params:
        _try_set(n, "domincusp", True)
        _try_set(n, "mincusp", clamp(float(params["threshold"]), 0.0, 10.0))
    # ── Solver tab -> Foam (real parm -> clamp) ──
    for key, base, lo, hi in (
        ("life", "life", 0.0, 100.0), ("life_variance", "lifevar", 0.0, 100.0),
        ("drift_rate", "driftrate", 0.0, 1.0),
        ("min_foam_density", "minfoamdensity", 0.0, 1000.0),
        ("max_foam_density", "maxfoamdensity", 0.0, 1000.0),
        ("preservation_rate", "foampreserverate", 0.0, 100.0),
        ("reduction_rate", "foamreducerate", 0.0, 100.0),
    ):
        if key in params:
            _try_set(n, base, clamp(float(params[key]), lo, hi))
    if "preserve_foam" in params:
        _try_set(n, "preservefoam", bool(params["preserve_foam"]))
    if "keep_attribs" in params:
        _try_set(n, "ptkeep", str(params["keep_attribs"]))
    # ── Solver tab -> Simulation ──
    if "start_frame" in params:
        _try_set(n, "startframe", int(clamp(int(params["start_frame"]), 1, 1_000_000)))
    if "substeps" in params:
        _try_set(n, "substeps", int(clamp(int(params["substeps"]), 1, 100)))
    if "cache_enabled" in params:
        _try_set(n, "cacheenabled", bool(params["cache_enabled"]))
    if "cache_memory_mb" in params:
        _try_set(n, "cachemaxsize", int(clamp(int(params["cache_memory_mb"]), 0, 1_000_000)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points())}


@endpoint("ocean_source")
def ocean_source(params):
    """[recipe] Couple an ocean spectrum into a FLIP tank (Ocean Source 2.0) — the composited
    outflow. Structural scaffold; FLIP-tank tuning is a post-build job. Creator: FAILS on collision.
    """
    name = params["name"]
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    grid = g.createNode("grid", "surface")
    spec = g.createNode("oceanspectrum", "spectrum")
    if "wind_speed" in params:
        _try_set(spec, "windspeed", clamp(float(params["wind_speed"]), 0.0, 200.0))
    src = g.createNode("oceansource::2.0", "source")
    src.setFirstInput(grid)
    src.setInput(1, spec)
    if "particlesep" in params:
        _try_set(src, "particlesep", clamp(float(params["particlesep"]), 1e-3, 1e4))
    if "waterlevel" in params:
        _try_set(src, "waterlevel", clamp(float(params["waterlevel"]), -1e5, 1e5))
    src.setDisplayFlag(display)
    src.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "spectrum": spec.path(), "source": src.path()}


# Ocean Spectrum authoring menus — live-probed on H21.0.671.
# Both are ORDERED menus (stored value is the index) — set via _menu_set.
_SPECTRUM_TYPE = ("phillips", "tma")                              # spectrumtype (default idx1=tma)
_SPECTRUM_DIST = ("none", "uniform", "gaussian", "lognormal")     # distribution (default idx2=gaussian)
# Wave-instancing + mask menus (re-probed): BOTH are
# Normal (string) menus — set by TOKEN via _str_menu_set, evalAsString returns the token.
_POINTCONFIG = ("auto", "2d", "3d")                               # pointconfig (Auto/2D-fit-plane/3D)
_MASKTYPE = ("suppress", "contribute")                            # masktype (default suppress)
# Ocean Evaluate depth-falloff (Normal/string menu).
_OCEANEVAL_DEPTHFALLOFF = ("none", "exponential", "exponentialfreq")


@endpoint("ocean_spectrum")
def ocean_spectrum(params):
    """Author a full ocean-wave SPECTRUM (Ocean Spectrum) and evaluate it onto a large grid — the
    deep 'look' controls ocean_surface's 6 params can't reach: spectrum model (Phillips/TMA), water
    depth (shallow vs deep), swell, fetch, wind direction + directional bias, deterministic seed and
    a seamless time loop. Returns the spectrum SOP (reuse it to drive ocean_source coupling from the
    SAME deterministic waves) plus the evaluated render surface. Creator: FAILS on name collision.
    BUILT (one cook)."""
    name = params["name"]
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    size = clamp(float(params.get("size", 100.0)), 1.0, 1e6)
    grid = g.createNode("grid", "surface")
    _try_set(grid, "sizex", size)
    _try_set(grid, "sizey", size)
    spec = g.createNode("oceanspectrum", "spectrum")
    _try_set(spec, "gridsize", size)                             # wave-field period matches the grid
    if "resolution" in params:
        _try_set(spec, "res", int(clamp(int(params["resolution"]), 4, 12)))
    if "spectrum_type" in params:
        _menu_set(spec, "spectrumtype", params["spectrum_type"], _SPECTRUM_TYPE)
    if "depth" in params:
        _try_set(spec, "depth", clamp(float(params["depth"]), 5.0, 1e5))  # node hard-floor is 5.0
    if "gravity" in params:
        _try_set(spec, "gravity", clamp(float(params["gravity"]), 0.1, 100.0))
    if "seed" in params:
        _try_set(spec, "seed", int(clamp(int(params["seed"]), 0, 10_000_000)))
    if "wind_speed" in params:
        _try_set(spec, "windspeed", clamp(float(params["wind_speed"]), 0.0, 200.0))
    if "wind_dir" in params:
        _try_set(spec, "winddir", clamp(float(params["wind_dir"]), -360.0, 360.0))
    if "dir_bias" in params:
        _try_set(spec, "dirbias", clamp(float(params["dir_bias"]), -10.0, 10.0))
    if "dir_move" in params:
        _try_set(spec, "dirmove", clamp(float(params["dir_move"]), -10.0, 10.0))
    if "swell" in params:
        _try_set(spec, "swell", clamp(float(params["swell"]), -1.0, 1.0))  # node range is -1..1
    if "fetch" in params:
        _try_set(spec, "fetch", clamp(float(params["fetch"]), 0.0, 1e6))
    if "chop" in params:
        _try_set(spec, "chopscale", clamp(float(params["chop"]), 0.0, 10.0))
    if "amplitude" in params:
        _try_set(spec, "ampscale", clamp(float(params["amplitude"]), 0.0, 100.0))
    if "reference_wind" in params:
        _try_set(spec, "referencewind", clamp(float(params["reference_wind"]), 0.1, 200.0))
    if "distribution" in params:
        _menu_set(spec, "distribution", params["distribution"], _SPECTRUM_DIST)
    if "loop" in params:
        _try_set(spec, "loop", bool(params["loop"]))
    if "loop_period" in params:
        _try_set(spec, "loopperiod", clamp(float(params["loop_period"]), 0.1, 1e5))
    # ── Wave Instancing (folder) — instance a DIFFERENT spectrum per input point to break the
    # obvious tiling repeat on wide/distance shots (recipe #33). Feed the instancing points on the
    # spectrum's input 0; the per-point levers below vary radius/amplitude/wavelength/phase.
    if "instance_points" in params:
        ipts = resolve_node(params["instance_points"])
        spec.setInput(0, bridge_into(ipts, g, xformtype=0, name_hint="wave_pts"))
    if "point_radius" in params:
        _try_set(spec, "dopointrad", True)
        _try_set(spec, "pointrad", clamp(float(params["point_radius"]), 0.0, 1e5))
    if "point_amp" in params:
        _try_set(spec, "dopointamp", True)
        _try_set(spec, "pointamp", clamp(float(params["point_amp"]), 0.0, 100.0))
    if "point_rotation" in params:
        _try_set(spec, "dopointrot", True)
        _try_set(spec, "pointrot", clamp(float(params["point_rotation"]), -360.0, 360.0))
    if "point_offset" in params:
        _try_set(spec, "dopointoffset", True)
        _try_set(spec, "pointoffset", clamp(float(params["point_offset"]), -1e5, 1e5))
    if "point_wavelength" in params:
        _try_set(spec, "dopointwavelen", True)
        _try_set(spec, "pointwavelen", clamp(float(params["point_wavelength"]), 0.0, 1e5))
    if "point_seed" in params:
        _try_set(spec, "pointseed", clamp(float(params["point_seed"]), 0.0, 1e7))
    if "point_config" in params:
        _str_menu_set(spec, "pointconfig", str(params["point_config"]), _POINTCONFIG)
    # ── Mask (folder) — a bound region (input 1) that SUPPRESSES or CONTRIBUTES this spectrum, so a
    # hero/boat area can be locked to the sim spectrum while the tiled background varies.
    if "mask" in params:
        mgeo = resolve_node(params["mask"])
        spec.setInput(1, bridge_into(mgeo, g, xformtype=0, name_hint="spec_mask"))
    if "mask_type" in params:
        _str_menu_set(spec, "masktype", str(params["mask_type"]), _MASKTYPE)
    ev = g.createNode("oceanevaluate::2.0", "evaluate")
    ev.setFirstInput(grid)
    ev.setInput(1, spec)
    ev.setDisplayFlag(display)
    ev.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    return {"node": g.path(), "spectrum": spec.path(), "evaluate": ev.path()}


@endpoint("ocean_evaluate")
def ocean_evaluate(params):
    """Deform ARBITRARY geometry by an ocean SPECTRUM (the SOP-level Ocean Evaluate). Wire any geo on
    input 0 and an ocean_spectrum SOP as `spectrum`, and it displaces the points by the summed wave
    layers — the seamless multi-patch / edge-match / big-wave-distort keystone: the SAME saved
    spectrum drives both the FLIP tank and the surrounding render ocean, so tiled patches share
    coincident rims. Optionally writes velocity + cusp for whitewater/shading, caps evaluated
    resolution, or solos a single spectrum layer. Chains after `input`. BUILT (one cook)."""
    ev = child_after(params["input"], "oceanevaluate::2.0", params.get("name"))
    spec = resolve_node(params["spectrum"])
    ref = bridge_into(spec, ev.parent(), xformtype=0, name_hint="spectrum")
    ev.setInput(1, ref)
    applied = {}
    if "time" in params:
        applied["time"] = _try_set(ev, "time", clamp(float(params["time"]), -1e6, 1e6))
    if "downsample" in params:
        applied["downsample"] = _try_set(ev, "downsample", int(clamp(int(params["downsample"]), 0, 8)))
    if "max_res" in params:
        _try_set(ev, "domaxres", True)
        applied["max_res"] = _try_set(ev, "maxres", int(clamp(int(params["max_res"]), 1, 14)))
    if "solo_layer" in params:
        _try_set(ev, "dosololayer", True)
        applied["solo_layer"] = _try_set(ev, "sololayer", int(clamp(int(params["solo_layer"]), 0, 64)))
    if "depth_falloff" in params:
        applied["depth_falloff"] = _str_menu_set(ev, "depthfalloff", str(params["depth_falloff"]), _OCEANEVAL_DEPTHFALLOFF)
    if "deform_geo" in params:
        applied["deform_geo"] = _try_set(ev, "deformgeo", bool(params["deform_geo"]))
    if "point_velocity" in params:
        applied["point_velocity"] = _try_set(ev, "pointvel", bool(params["point_velocity"]))
    if "cusp" in params:
        applied["cusp"] = _try_set(ev, "cusp", bool(params["cusp"]))
    ev.setDisplayFlag(True)
    ev.setRenderFlag(True)
    ev.parent().layoutChildren()
    return {"node": ev.path(), "spectrum_ref": ref.path(), "applied": applied}


@endpoint("cloud")
def cloud(params):
    """Volumetric cloud primitive: a source geo -> Cloud 2.0 (SDF/density) -> Cloud Noise (->optional
    Cloud Adjust Density Profile). Creator: FAILS on name collision. BUILT (one cook).

    Back-compat: density -> Cloud densitymultiplier; noise_amount/noise_type/freq -> Cloud Noise.
    Cloud 2.0 (SDF/band/density): radiusscale, uniformsamples (max|size), samplediv, divsize,
      useworldspaceunits, exteriorband/interiorband (world units), exteriorbandvoxels/
      interiorbandvoxels (voxel units), spatialscale, densitymultiplier (alias of density).
    Cloud Noise (billowy/wispy depth): noisetype (onoise|snoise|anoise|xnoise|correctnoise),
      noiseoctaves, noiseelementsize (alias of freq), noiserough, noiseamount (alias of noise_amount),
      advectnoise, advectamp, upvectorfalloff (flat-bottom cumulus).
    Optional base/anvil shaping via cloudadjustdensityprofile when `adjust_profile` is set:
      edge_thickness, edge_density, edge_falloff, internal_density."""
    name = params["name"]
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    src = g.createNode("sphere", "shape")
    _try_set(src, "type", "polymesh")
    cld = g.createNode("cloud::2.0", "cloud")
    cld.setFirstInput(src)
    # ── Cloud 2.0: density / SDF / narrow-band shaping
    if "density" in params:
        _try_set(cld, "densitymultiplier", clamp(float(params["density"]), 0.0, 1e4))
    if "densitymultiplier" in params:
        _try_set(cld, "densitymultiplier", clamp(float(params["densitymultiplier"]), 0.0, 1e4))
    if "radiusscale" in params:
        _try_set(cld, "radiusscale", clamp(float(params["radiusscale"]), 0.0, 2.0))
    if "uniformsamples" in params:
        _menu_set(cld, "uniformsamples", str(params["uniformsamples"]), _CLOUD_UNIFORMSAMPLES)
    if "samplediv" in params:
        _try_set(cld, "samplediv", int(clamp(int(params["samplediv"]), 1, 50)))
    if "divsize" in params:
        _try_set(cld, "divsize", clamp(float(params["divsize"]), 0.0, 10.0))
    if "useworldspaceunits" in params:
        _try_set(cld, "useworldspaceunits", bool(params["useworldspaceunits"]))
    if "exteriorband" in params:
        _try_set(cld, "exteriorband", clamp(float(params["exteriorband"]), 1e-5, 10.0))
    if "interiorband" in params:
        _try_set(cld, "interiorband", clamp(float(params["interiorband"]), 1e-5, 10.0))
    if "exteriorbandvoxels" in params:
        _try_set(cld, "exteriorbandvoxels", int(clamp(int(params["exteriorbandvoxels"]), 1, 10)))
    if "interiorbandvoxels" in params:
        _try_set(cld, "interiorbandvoxels", int(clamp(int(params["interiorbandvoxels"]), 1, 10)))
    if "spatialscale" in params:
        _try_set(cld, "spatialscale", clamp(float(params["spatialscale"]), 0.0, 100.0))
    last = cld
    # ── Cloud Noise: billowy / wispy displacement depth
    noise = g.createNode("cloudnoise", "noise")
    noise.setFirstInput(cld)
    if "noise_amount" in params:
        _try_set(noise, "noiseamount", clamp(float(params["noise_amount"]), 0.0, 1.0))
    if "noiseamount" in params:
        _try_set(noise, "noiseamount", clamp(float(params["noiseamount"]), 0.0, 1.0))
    if "noise_type" in params:
        _str_menu_set(noise, "noisetype", str(params["noise_type"]), _CLOUDNOISE_TYPE)
    if "noisetype" in params:
        _str_menu_set(noise, "noisetype", str(params["noisetype"]), _CLOUDNOISE_TYPE)
    if "freq" in params:
        _try_set(noise, "noiseelementsize", clamp(float(params["freq"]), 0.0, 1.0))
    if "noiseelementsize" in params:
        _try_set(noise, "noiseelementsize", clamp(float(params["noiseelementsize"]), 0.0, 1.0))
    if "noiseoctaves" in params:
        _try_set(noise, "noiseoctaves", int(clamp(int(params["noiseoctaves"]), 0, 10)))
    if "noiserough" in params:
        _try_set(noise, "noiserough", clamp(float(params["noiserough"]), 0.0, 1.0))
    if "advectnoise" in params:
        _try_set(noise, "advectnoise", bool(params["advectnoise"]))
    if "advectamp" in params:
        _try_set(noise, "advectamp", clamp(float(params["advectamp"]), -1.0, 1.0))
    if "upvectorfalloff" in params:
        _try_set(noise, "upvectorfalloff", bool(params["upvectorfalloff"]))
    last = noise
    # ── optional base/anvil density-profile shaping
    profile = None
    if params.get("adjust_profile"):
        profile = g.createNode("cloudadjustdensityprofile", "profile")
        profile.setFirstInput(noise)
        if "edge_thickness" in params:
            _try_set(profile, "edge_thickness", clamp(float(params["edge_thickness"]), 0.0, 1.0))
        if "edge_density" in params:
            _try_set(profile, "doedge_density", True)
            _try_set(profile, "edge_density", clamp(float(params["edge_density"]), 0.0, 1.0))
        if "edge_falloff" in params:
            _try_set(profile, "edge_falloff", clamp(float(params["edge_falloff"]), 0.0, 1.0))
        if "internal_density" in params:
            _try_set(profile, "dointernal_density", True)
            _try_set(profile, "internal_density", clamp(float(params["internal_density"]), 0.0, 1.0))
        last = profile
    last.setDisplayFlag(display)
    last.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    out = {"node": g.path(), "cloud": cld.path(), "noise": noise.path()}
    if profile is not None:
        out["profile"] = profile.path()
    return out


@endpoint("cloud_shape")
def cloud_shape(params):
    """Generate a modern volumetric CLOUD with the H20+ Cloud Shape toolset (cloudshapegenerate) — the
    art-directable replacement for the deprecated monolithic `cloud` node. Builds cumulus (cu) /
    cumulonimbus (cb) shape spheres, then (rasterize=true, the default) rasterizes them into a
    render-ready `density` fog VDB ready for cloud_billowy_noise / cloud_wispy_noise / cloud_clip.
    cloud_type cu|cb + species (cu: hum|med|con  cb: cal|cap); size / size_scale = overall scale;
    pointsep = shape density (smaller = puffier); length / width; flatten = flat cumulus bottoms
    (0..1); distort = shape irregularity; secondary_shapes = billowing sub-lobes
    (+ secondary_iterations / secondary_displacement); bend = lean (deg); seed. Creator: FAILS on name
    collision. Returns the shape node + (if rasterized) the density-VDB output node."""
    name = params["name"]
    display = bool(params.get("display", False))
    g = _fresh_geo(name)
    gen = g.createNode("cloudshapegenerate", "shapes")
    ctype = str(params.get("cloud_type", "cu"))
    _str_menu_set(gen, "cloudtype", ctype, _CLOUDSHAPE_TYPE)
    if "species" in params:
        sp = str(params["species"])
        _str_menu_set(gen, "cuspecies" if ctype == "cu" else "cbspecies", sp,
                      _CU_SPECIES if ctype == "cu" else _CB_SPECIES)
    if "size" in params:
        _try_set(gen, "size", clamp(float(params["size"]), 1e-3, 1e6))
    if "size_scale" in params:
        _try_set(gen, "sizescale", clamp(float(params["size_scale"]), 1e-3, 1e6))
    if "pointsep" in params:
        _try_set(gen, "pointsep", clamp(float(params["pointsep"]), 1e-4, 1e4))
    if "length" in params:
        _try_set(gen, "length", clamp(float(params["length"]), 1e-3, 1e6))
    if "width" in params:
        _try_set(gen, "width", clamp(float(params["width"]), 1e-3, 1e6))
    if "flatten" in params:
        _try_set(gen, "doflatten", 1)
        _try_set(gen, "flatten", clamp(float(params["flatten"]), 0.0, 1.0))
    if "distort" in params:
        _try_set(gen, "doshapedistort", 1)
        _try_set(gen, "shapedistort", clamp(float(params["distort"]), 0.0, 10.0))
    if params.get("secondary_shapes"):
        _try_set(gen, "scattersecshapes", 1)
        if "secondary_iterations" in params:
            _try_set(gen, "secniter", int(clamp(int(params["secondary_iterations"]), 1, 10)))
        if "secondary_displacement" in params:
            _try_set(gen, "secdisp", clamp(float(params["secondary_displacement"]), 0.0, 10.0))
    if "bend" in params:
        _try_set(gen, "dobend", 1)
        _try_set(gen, "bend", clamp(float(params["bend"]), -180.0, 180.0))
    if "seed" in params:
        _try_set(gen, "seed", float(params["seed"]))
    last, rasterized = gen, False
    if params.get("rasterize", True):
        cld = g.createNode("cloud::2.0", "rasterize")   # canonical shape->density rasterizer (outputs `density` VDB)
        cld.setFirstInput(gen)
        if "voxelsize" in params:
            # divsize is only honoured in Size mode; cloud::2.0 defaults uniformsamples=max
            # (sample-COUNT), which silently ignores divsize. Switch to size so voxelsize bites.
            _menu_set(cld, "uniformsamples", "size", _CLOUD_UNIFORMSAMPLES)
            _try_set(cld, "divsize", clamp(float(params["voxelsize"]), 1e-3, 10.0))
        if "density" in params:
            _try_set(cld, "densitymultiplier", clamp(float(params["density"]), 0.0, 1e4))
        last, rasterized = cld, True
    last.setDisplayFlag(display)
    last.setRenderFlag(True)
    g.setDisplayFlag(display)
    g.layoutChildren()
    last.cook(force=True)
    gg = last.geometry()
    return {"node": g.path(), "shapes": gen.path(), "output": last.path(),
            "rasterized": rasterized, "prims": len(gg.prims()) if gg else 0}


@endpoint("cloud_billowy_noise")
def cloud_billowy_noise(params):
    """Billowing cauliflower displacement on a cloud DENSITY VDB (cloudbillowynoise) — the modern
    high-detail cumulus modifier. `input` = a density fog VDB (from cloud_shape rasterize, or
    volume_rasterize / vdb_from_particles set to density). basis (alligator|perlin|simplex|
    fastsimplex); amplitude; element_size (feature scale, smaller = finer detail); octaves / lacunarity
    / roughness (fractal); worley_details = cauliflower erosion (+ worley_blend / worley_erosion);
    distort + droop warp the billows; advect_noise self-advects for wispier edges; num_noises layers;
    deepen_valleys carves gaps."""
    n = child_after(params["input"], "cloudbillowynoise", params.get("name"))
    if "basis" in params:
        _str_menu_set(n, "basis", str(params["basis"]), _CLOUD_NOISE_BASIS)
    if "amplitude" in params:
        _try_set(n, "amplitude", clamp(float(params["amplitude"]), 0.0, 1e4))
    if "element_size" in params:
        _try_set(n, "elementsize", clamp(float(params["element_size"]), 1e-4, 1e4))
    if "offset" in params:
        _try_set(n, "offset", float(params["offset"]))
    if "octaves" in params:
        _try_set(n, "oct", int(clamp(int(params["octaves"]), 1, 12)))
    if "lacunarity" in params:
        _try_set(n, "lac", clamp(float(params["lacunarity"]), 1.0, 10.0))
    if "roughness" in params:
        _try_set(n, "rough", clamp(float(params["roughness"]), 0.0, 1.0))
    if params.get("worley_details"):
        _try_set(n, "doworleydetails", 1)
        if "worley_blend" in params:
            _try_set(n, "worleyblend", clamp(float(params["worley_blend"]), 0.0, 1.0))
        if "worley_erosion" in params:
            _try_set(n, "worleyerosion", clamp(float(params["worley_erosion"]), 0.0, 1.0))
    if "distort" in params:
        _try_set(n, "distort", clamp(float(params["distort"]), 0.0, 1e4))
    if "droop" in params:
        _try_set(n, "dodroop", 1)
        _try_set(n, "droop", clamp(float(params["droop"]), 0.0, 1e4))
    if "advect_noise" in params:
        _try_set(n, "advectnoise", bool(params["advect_noise"]))
    if "num_noises" in params:
        _try_set(n, "nnoises", int(clamp(int(params["num_noises"]), 1, 10)))
    if "deepen_valleys" in params:
        _try_set(n, "deepenvalleys", bool(params["deepen_valleys"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()) if g else 0}


@endpoint("cloud_wispy_noise")
def cloud_wispy_noise(params):
    """Wispy / streaky velocity-advected displacement on a cloud DENSITY VDB (cloudwispynoise) — for
    high-altitude cirrus, stretched anvils, wind-blown wisps. `input` = a density fog VDB. amplitude;
    element_size; octaves / roughness; wind (add_wind + wind_strength + wind_dir[x,y,z]); advect_noise
    self-advects; animated + pulse_duration make the wisps evolve over time (needs a cooked frame
    range to see)."""
    n = child_after(params["input"], "cloudwispynoise", params.get("name"))
    if "amplitude" in params:
        _try_set(n, "amplitude", clamp(float(params["amplitude"]), 0.0, 1e4))
    if "element_size" in params:
        _try_set(n, "elementsize", clamp(float(params["element_size"]), 1e-4, 1e4))
    if "octaves" in params:
        _try_set(n, "oct", int(clamp(int(params["octaves"]), 1, 12)))
    if "roughness" in params:
        _try_set(n, "rough", clamp(float(params["roughness"]), 0.0, 1.0))
    if params.get("add_wind"):
        _try_set(n, "addwind", 1)
        if "wind_strength" in params:
            _try_set(n, "windstrength", clamp(float(params["wind_strength"]), 0.0, 1e6))
        if "wind_dir" in params and len(params["wind_dir"]) == 3:
            for pn, v in zip(("winddir1", "winddir2", "winddir3"), params["wind_dir"]):
                _try_set(n, pn, float(v))
    if "advect_noise" in params:
        _try_set(n, "advectnoise", bool(params["advect_noise"]))
    if params.get("animated"):
        _try_set(n, "animated", 1)
        if "pulse_duration" in params:
            _try_set(n, "pulseduration", clamp(float(params["pulse_duration"]), 1e-3, 1e6))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()) if g else 0}


@endpoint("cloud_clip")
def cloud_clip(params):
    """Clip / cut a cloud DENSITY VDB with a plane + optional noise (cloudclip) — flat cumulus BASES,
    sheared anvils, sliced tops. `input` = a density fog VDB. Plane = origin[x,y,z] / direction[x,y,z]
    / distance; negate flips which side is kept; noise (noise=true + basis + noise_amplitude +
    noise_element_size) breaks the cut edge up naturally; edge_density (edge_density=true +
    edge_thickness) softens the cut into a graded base. Keeps output 0 (the primary clipped volume)."""
    n = child_after(params["input"], "cloudclip", params.get("name"))
    if "origin" in params and len(params["origin"]) == 3:
        for pn, v in zip(("originx", "originy", "originz"), params["origin"]):
            _try_set(n, pn, float(v))
    if "direction" in params and len(params["direction"]) == 3:
        for pn, v in zip(("dirx", "diry", "dirz"), params["direction"]):
            _try_set(n, pn, float(v))
    if "distance" in params:
        _try_set(n, "dist", float(params["distance"]))
    if "negate" in params:
        _try_set(n, "negate", bool(params["negate"]))
    if params.get("noise"):
        _try_set(n, "donoise", 1)
        if "basis" in params:
            _str_menu_set(n, "basis", str(params["basis"]), _CLOUD_NOISE_BASIS)
        if "noise_amplitude" in params:
            _try_set(n, "amp", clamp(float(params["noise_amplitude"]), 0.0, 1e4))
        if "noise_element_size" in params:
            _try_set(n, "elementsize", clamp(float(params["noise_element_size"]), 1e-4, 1e4))
    if params.get("edge_density"):
        _try_set(n, "doedgedensity", 1)
        if "edge_thickness" in params:
            _try_set(n, "edgethickness", clamp(float(params["edge_thickness"]), 0.0, 1e4))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()) if g else 0}


# TODO(sky): no valid sky node type surfaced in the probe (OBJ:sky / OBJ:skylight / `sky` all
#   errored on this build). A `sky` endpoint (mode daylight|env|field, time_of_day, turbidity)
#   should pair with the time-of-day sun in add_light once a valid node type is probed. Until then
#   dome/HDRI lighting is available via look.add_light(ltype="dome").
# TODO(fog): the `fog` (atmosphere volume) node errored in the probe ("attempted operation
#   failed"); leave unregistered until a valid node type + parm set is confirmed.

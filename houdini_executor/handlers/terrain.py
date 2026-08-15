"""Terrain / heightfield handlers. Params verified against live H21.0.671 nodes.

All handlers run on Houdini's main thread (the server marshals them there). They take scene-graph
node paths (`input`), build the node, and return the new node path + stats.
"""

import hou
from houdini_executor.server import endpoint, child_after, clamp, resolve_node, confined_path, bridge_input
from houdini_executor.vex_validator import validate_ident
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set




def _hf_insert_before_place(geo, node):
    """Wire `node` in native space: BEFORE a trailing 'place' xform (heightfield ops need native
    voxel space). Returns the tail node of the chain."""
    place = None
    for c in geo.children():
        if c.name() == "place" and c.type().name() == "xform":
            place = c
            break
    if place is not None and place.inputs():
        node.setFirstInput(place.inputs()[0])
        place.setFirstInput(node)
        return place
    src = geo.displayNode() or (geo.children()[-1] if geo.children() else None)
    if src is not None and src is not node:
        node.setFirstInput(src)
    return node


def _geo_of(input_path):
    """Resolve an input SOP path to its containing /obj geo (heightfield ops append into the geo,
    then re-wire in native space)."""
    src = resolve_node(input_path)
    geo = src.parent()
    if geo is None or geo.type().name() != "geo" or not geo.children():
        raise ValueError(f"input {input_path} is not inside a heightfield geo")
    return geo


def _hf_append_native(geo, ntype, name=None, cook=True):
    """Create `ntype` inside `geo`, wire it in NATIVE space (before a trailing 'place' xform),
    finalize display/render flags, force-cook (Manual mode defers geometry()), return (node, tail).

    Pass cook=False when the node needs a SECOND input wired before it can cook (e.g.
    heightfield_maskbyobject needs its bounding object on input 1) — the caller cooks after wiring."""
    n = geo.createNode(ntype, name) if name else geo.createNode(ntype)
    tail = _hf_insert_before_place(geo, n)
    n.setDisplayFlag(False)
    tail.setRenderFlag(True)
    tail.setDisplayFlag(True)
    geo.layoutChildren()
    if cook:
        n.cook(force=True)
    return n, tail


@endpoint("convert_heightfield")
def convert_heightfield(params):
    """Height volume -> renderable/exportable geometry (convertheightfield). The headline "make it
    deliverable" endpoint.

    input: SOP path of the heightfield.
    conversion: output type poly | polysoup (dense, non-editable) | vdb (3D volume, heavy).
    surftype: polygon connectivity (triangles | quads | rows | cols | ...); triangles/quads are the
      useful terrain layouts.
    lod: Density = output-resolution ratio (node range 0.001..5; 0.5 = half res / one poly per 4
      voxels, 2 = 4x supersample). 1 = full res.
    bake_colors: bake the heightfield material/visualization onto the mesh as point Cd (default on)
      so the deliverable carries the gradient.
    extrude_base + depth: give the mesh a solid extruded base (watertight for printing/CFD); depth is
      the base height (negative = downward, node range -10..0).
    """
    n = child_after(params["input"], "convertheightfield", params.get("name"))
    n.parm("lod").set(clamp(float(params.get("lod", 1.0)), 0.001, 5.0))
    if params.get("conversion") is not None:
        _menu_set(n, "conversion", params["conversion"], ("poly", "polysoup", "vdb"))
    if params.get("surftype") is not None:
        _menu_set(n, "surftype", params["surftype"],
                  ("rows", "cols", "rowcol", "triangles", "quads", "alttriangles", "revtriangles"))
    if "extrude_base" in params:
        _try_set(n, "doextrude", bool(params["extrude_base"]))
    if "depth" in params:
        _try_set(n, "doextrude", True)
        _try_set(n, "depth", clamp(float(params["depth"]), -10.0, 0.0))
    if "flatten_base" in params:
        _try_set(n, "flat", bool(params["flatten_base"]))
    # Bake the heightfield's color/visualization onto the output mesh as point Cd, so the
    # DELIVERABLE geometry carries the gradient (probe-verified parm name: bakecd).
    bake = params.get("bake_colors", True)
    bake = True if bake is None else bool(bake)
    _try_set(n, "bakecd", bake)
    g = n.geometry()  # cook
    return {"node": n.path(), "prims": len(g.prims()), "points": len(g.points()),
            "bake_colors": bake}


@endpoint("heightfield_crop")
def heightfield_crop(params):
    """Crop / resize / re-window a heightfield to a size box in metres (heightfield_crop).

    sizex/sizey: width and length of the cropped region (the `size` tuple).
    center: [x,y,z] center of the crop window (the `t` tuple) — moves a "window" across a larger
      field (useful with cropmode=replace to slide over world space).
    cropmode: intersect (default; cut to the overlap of old+new box), replace (use the new box,
      extending past the original with the border policy), or union (bounding box of both).
    voxelpad: extra voxels added around the window for padding/overlap.
    """
    n = child_after(params["input"], "heightfield_crop", params.get("name"))
    if "sizex" in params:
        n.parm("sizex").set(clamp(float(params["sizex"]), 1.0, 1e7))
    if "sizey" in params:
        n.parm("sizey").set(clamp(float(params["sizey"]), 1.0, 1e7))
    if params.get("center") is not None:
        _set_vec(n, "t", params["center"], 3, float)
    if params.get("cropmode") is not None:
        _menu_set(n, "cropmode", params["cropmode"], ("replace", "union", "intersect"))
    if "voxelpad" in params:
        _try_set(n, "voxelpad", int(clamp(int(params["voxelpad"]), 0, 4096)))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims())}


# ── morphology / fill (server-templated volume wrangles on an existing heightfield geo) ───────
_MORPH_PASSES = {  # grayscale morphology as separable min/max passes; (func, axis)
    "dilate": [("max", "x"), ("max", "z")],
    "erode": [("min", "x"), ("min", "z")],
    "close": [("max", "x"), ("max", "z"), ("min", "x"), ("min", "z")],  # fill valleys, keep peaks
    "open": [("min", "x"), ("min", "z"), ("max", "x"), ("max", "z")],
}


@endpoint("heightfield_morph")
def heightfield_morph(params):
    """Grayscale morphology on a height layer (dilate/erode/open/close). `close` fills channels up
    to the surrounding envelope while keeping peaks. Operates on the named /obj heightfield geo.

    name: /obj geo name.  op: dilate|erode|open|close.  radius_m: kernel radius in metres.
    """
    op = str(params.get("op", "close"))
    if op not in _MORPH_PASSES:
        raise ValueError("op must be dilate|erode|open|close")
    name = params["name"]
    geo = hou.node("/obj/" + name)
    if geo is None or geo.type().name() != "geo" or not geo.children():
        raise ValueError(f"no heightfield geo with SOPs: /obj/{name}")
    vs = float(params.get("voxelsize", 1.0) or 1.0)
    radius_m = clamp(float(params.get("radius_m", 100.0)), 0.0, 1e6)
    n = max(1, int(radius_m / vs))
    # `lyr` is interpolated into volumewrangle VEX text below (@<lyr>) — gate it to a bare identifier so
    # a layer name cannot smuggle arbitrary VEX (RT-12). Zero capability cost: layer names ARE identifiers.
    lyr = validate_ident(str(params.get("layer", "height") or "height"), "layer")
    display = bool(params.get("display", False))

    first = None
    prev = None
    for i, (fn, ax) in enumerate(_MORPH_PASSES[op]):
        w = geo.createNode("volumewrangle", "%s_%s_%d" % (op, ax, i))
        off = "set(k*%g,0,0)" % vs if ax == "x" else "set(0,0,k*%g)" % vs
        w.parm("snippet").set(
            'int n=%d; float m=@%s; for(int k=-n;k<=n;k++) m=%s(m, volumesample(0,"%s",@P+%s)); @%s=m;'
            % (n, lyr, fn, lyr, off, lyr))
        if prev is not None:
            w.setFirstInput(prev)
        else:
            first = w
        prev = w
    _hf_insert_before_place(geo, first)
    tail = geo.node("place") or prev
    tail.setDisplayFlag(display)
    tail.setRenderFlag(True)
    geo.setDisplayFlag(display)
    geo.layoutChildren()
    prev.cook(force=True)
    return {"node": geo.path(), "head": first.path(), "tail_op": prev.path(),
            "op": op, "kernel_voxels": n, "layer": lyr}


@endpoint("heightfield_fill")
def heightfield_fill(params):
    """Masked Laplacian relaxation: fill masked voxels (mask==1) while holding mask==0 as a
    Dirichlet boundary. Reconstructs a smooth surface across a channel/hole mask.

    name: /obj geo name.  mask_layer: mask volume name.  iterations: Jacobi steps (capped).
    seed_layer: optional layer to seed masked voxels with before relaxing.
    """
    name = params["name"]
    geo = hou.node("/obj/" + name)
    if geo is None or geo.type().name() != "geo" or not geo.children():
        raise ValueError(f"no heightfield geo with SOPs: /obj/{name}")
    vs = float(params.get("voxelsize", 1.0) or 1.0)
    it = int(clamp(int(params.get("iterations", 40)), 1, 120))
    # `mk` and `seed` are interpolated into volumewrangle VEX text below (@<mk>, @<seed>) — gate both to
    # bare identifiers so a mask/seed layer name cannot smuggle arbitrary VEX (RT-12). Zero capability cost.
    mk = validate_ident(str(params.get("mask_layer", "mask") or "mask"), "mask_layer")
    seed = validate_ident(str(params["seed_layer"]), "seed_layer") if params.get("seed_layer") else None
    display = bool(params.get("display", False))

    first = None
    prev = None
    if seed:
        s = geo.createNode("volumewrangle", "seed")
        s.parm("snippet").set('if(@%s>0.5) @height = @%s;' % (mk, seed))
        first = s
        prev = s
    for i in range(it):
        w = geo.createNode("volumewrangle", "jacobi_%d" % i)
        w.parm("snippet").set(
            'if(@%s>0.5){float vs=%g; @height=0.25*(volumesample(0,"height",@P+set(-vs,0,0))'
            '+volumesample(0,"height",@P+set(vs,0,0))+volumesample(0,"height",@P+set(0,0,-vs))'
            '+volumesample(0,"height",@P+set(0,0,vs)));}' % (mk, vs))
        if prev is not None:
            w.setFirstInput(prev)
        else:
            first = w
        prev = w
    _hf_insert_before_place(geo, first)
    tail = geo.node("place") or prev
    tail.setDisplayFlag(display)
    tail.setRenderFlag(True)
    geo.setDisplayFlag(display)
    geo.layoutChildren()
    prev.cook(force=True)
    return {"node": geo.path(), "head": first.path(), "iterations": it,
            "mask_layer": mk, "seed_layer": seed}


# ── native heightfield SOPs (params verified against the live probe) ──────────────────────────
@endpoint("heightfield_patch")
def heightfield_patch(params):
    """Transfer/blend features from a patch heightfield (input1) onto a base heightfield (input0),
    keeping a smooth boundary — mosaic adjacent DEM tiles or stamp a masked region.

    patch: SOP of the patch field (wired to input 1).
    scale: uniform scale of the patch before transfer (grid + feature magnitude).
    heightscale: scale only the transferred feature heights.
    tx / tz / ry: translate (metres) and rotate-about-Y (degrees) the patch before transfer.
    centerpatch: center the patch by its mask so tx/tz/ry pivot on the masked region (default on).
    """
    n = child_after(params["input"], "heightfield_patch", params.get("name"))
    if params.get("patch"):
        bridge_input(n, params["patch"], index=1, name_hint="patch")
    if "scale" in params:
        n.parm("scale").set(clamp(float(params["scale"]), 0.0, 1e6))
    if "heightscale" in params:
        n.parm("heightscale").set(clamp(float(params["heightscale"]), -1e6, 1e6))
    if "tx" in params:
        _try_set(n, "tx", clamp(float(params["tx"]), -1e7, 1e7))
    if "tz" in params:
        _try_set(n, "tz", clamp(float(params["tz"]), -1e7, 1e7))
    if "ry" in params:
        _try_set(n, "ry", clamp(float(params["ry"]), -360.0, 360.0))
    if "centerpatch" in params:
        _try_set(n, "centerpatch", bool(params["centerpatch"]))
    n.geometry()
    return {"node": n.path()}


@endpoint("heightfield_tilesplit")
def heightfield_tilesplit(params):
    """Split a heightfield into a rows x cols tile grid (native LOD / streaming). Extract one tile
    (tile=index) to save/process it individually — the usual per-tile game-engine / for-each workflow.

    tiles_x / tiles_y: column and row counts. tile: which tile to output (wraps if > total; enables
      Extract Single Tile). overlap / overlap_upper: voxels each tile overlaps its neighbour in the
      negative / positive direction (avoids display cracks + eases re-stitching). voxelpad: extra
      overlap voxels added across all boundaries.
    """
    n = child_after(params["input"], "heightfield_tilesplit", params.get("name"))
    if "tiles_x" in params:
        n.parm("tilecountx").set(int(clamp(int(params["tiles_x"]), 1, 1024)))
    if "tiles_y" in params:
        n.parm("tilecounty").set(int(clamp(int(params["tiles_y"]), 1, 1024)))
    if "overlap" in params:
        n.parm("tileminoverlap").set(int(clamp(int(params["overlap"]), 0, 4096)))
    if "overlap_upper" in params:
        _try_set(n, "tilemaxoverlap", int(clamp(int(params["overlap_upper"]), 0, 4096)))
    if "voxelpad" in params:
        _try_set(n, "voxelpad", int(clamp(int(params["voxelpad"]), 0, 4096)))
    if "tile" in params:
        _try_set(n, "extracttile", 1)
        n.parm("tilenum").set(int(clamp(int(params["tile"]), 0, 1_000_000)))
    n.geometry()
    return {"node": n.path()}


@endpoint("heightfield_clip")
def heightfield_clip(params):
    """Clip height values to a min/max band (outlier clamp / mesa flattening). Emits `mesa` (leveled
    areas) and `cliffs` (clip borders) mask layers for downstream masking.

    minheight / maxheight: clip floor / ceiling (auto-enables the matching clip toggle).
    soft_clip: soften the transition into the clipped value instead of a hard clamp (default on).
    clip_strength: sharpness of the soft-clip transition (0.1..1).
    """
    n = child_after(params["input"], "heightfield_clip", params.get("name"))
    if "minheight" in params:
        n.parm("dominclip").set(True)
        n.parm("minclip").set(clamp(float(params["minheight"]), -1e7, 1e7))
    if "maxheight" in params:
        n.parm("domaxclip").set(True)
        n.parm("maxclip").set(clamp(float(params["maxheight"]), -1e7, 1e7))
    if "soft_clip" in params:
        _try_set(n, "dosoftclip", bool(params["soft_clip"]))
    if "clip_strength" in params:
        _try_set(n, "clipstrength", clamp(float(params["clip_strength"]), 0.1, 1.0))
    n.geometry()
    return {"node": n.path()}


@endpoint("heightfield_cutout")
def heightfield_cutout(params):
    """Cut out a non-rectangular heightfield region bounded by geometry (input1), writing the `Alpha`
    display layer (cutout at Alpha=0.5). The terrain data still exists everywhere; this is a visual
    clip unless crop is on.

    object: the boundary geometry (wired to input 1). invert: set Alpha outside the object instead of
      inside. combine: how to merge with an existing Alpha (replace | intersect | union | subtract).
      crop: shrink the terrain to the smallest active rectangle (default on).
    """
    n = child_after(params["input"], "heightfield_cutoutbyobject", params.get("name"))
    if params.get("object"):
        bridge_input(n, params["object"], index=1, name_hint="object")
    if "invert" in params:
        n.parm("invert").set(bool(params["invert"]))
    if params.get("combine") is not None:
        _menu_set(n, "combine", params["combine"], ("replace", "intersect", "union", "subtract"))
    if "crop" in params:
        _try_set(n, "crop", bool(params["crop"]))
    n.geometry()
    return {"node": n.path()}


@endpoint("heightfield_erode")
def heightfield_erode(params):
    """Hydraulic + thermal erosion at a chosen feature scale (HeightField Erode 3.0). Rainfall +
    weathering remove and transport material, carving channels/slopes/deposits and emitting `height`,
    `sediment`, `debris`, `flow` and `flowdir.x`/`flowdir.y` layers you can feed to
    heightfield_visualize or a Copernicus network for texture synthesis. (Flow DIRECTION is two
    layers `flowdir.x` + `flowdir.y`, not a single `flowdir`; after convert_heightfield they become
    point attributes `flowdir_x`/`flowdir_y` -- the `.`->`_` rename Houdini applies to volume names.)
    Chain several erodes at decreasing `erosionrate` for multi-scale terrain.

    Params: `erosionrate` = erosion feature width in meters (bigger -> broader landforms, smaller ->
    finer detail; clamped to ~3x voxel size); `spread_iters` = material-transport iterations per frame
    (with erosionrate, sets transport distance); `erodability` = overall susceptibility to hydro+thermal
    erosion; `flow` = fluvial flow rate; `seed` randomizes; `duration` = solver iterations.
    `freeze_frame` bakes the sim at that frame (recommended once eroded enough) rather than cooking
    iteratively with the playbar. Optional mask gating: `mask_layer` (or `use_mask`=true, default layer
    "mask") drives the erodability control mask, confining erosion to the masked region.
    """
    n = child_after(params["input"], "heightfield_erode::3.0", params.get("name"))
    if "duration" in params:
        n.parm("iterations").set(int(clamp(int(params["duration"]), 1, 200)))
    if "erosionrate" in params:
        _try_set(n, "erosionscale", clamp(float(params["erosionrate"]), 0.0, 50.0))
    if "flow" in params:
        _try_set(n, "flow", clamp(float(params["flow"]), 0.0, 1.0))
    if "spread_iters" in params:
        _try_set(n, "spreaditers", int(clamp(int(params["spread_iters"]), 1, 64)))
    if "erodability" in params:
        _try_set(n, "erodability", clamp(float(params["erodability"]), 0.0, 1.0))
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    if "freeze_frame" in params:
        # Bake the eroded result at a frame (recommended once erosion is sufficient) instead of
        # cooking iteratively with the playbar.
        _try_set(n, "dofreeze", True)
        _try_set(n, "freezeframe", int(params["freeze_frame"]))
    gate = params.get("mask_layer") or (params.get("use_mask") and "mask")
    if gate:
        # erodability = master "where can erosion happen"; maskmode!=0 enables the control mask.
        _try_set(n, "erodabilitymaskmode", 1)
        _try_set(n, "erodabilitymasklayer", str(gate))
    # ── Erode-3.0 HYDRO solver dials (fluvial: rain -> flow -> erode/transport/deposit). All additive;
    #    absent -> node default. Tune these to shape river networks vs broad slope wash. ──
    if "bank_angle" in params:
        _try_set(n, "bankangle", clamp(float(params["bank_angle"]), 0.0, 90.0))
    if "rainfall_coverage" in params:
        _try_set(n, "coverage", clamp(float(params["rainfall_coverage"]), 0.0, 1.0))
    if "slope_influence" in params:
        _try_set(n, "slopeinfluence", clamp(float(params["slope_influence"]), 0.0, 1.0))
    if "erosion_rate" in params:
        _try_set(n, "erosion", clamp(float(params["erosion_rate"]), 0.0, 1.0))
    if "deposition_rate" in params:
        _try_set(n, "deposition", clamp(float(params["deposition_rate"]), 0.0, 1.0))
    if "removal_rate" in params:
        _try_set(n, "removal", clamp(float(params["removal_rate"]), 0.0, 1.0))
    if "evaporation_rate" in params:
        _try_set(n, "evaporation", clamp(float(params["evaporation_rate"]), 0.0, 1.0))
    # ── Erode-3.0 THERMAL solver dials (weathering + slumping to the angle of repose = talus). ──
    if "weathering" in params:
        _try_set(n, "weathering", clamp(float(params["weathering"]), 0.0, 1.0))
    if "cut_angle" in params:
        _try_set(n, "cutangle", clamp(float(params["cut_angle"]), 0.0, 90.0))
    if "repose_angle" in params:
        _try_set(n, "reposeangle", clamp(float(params["repose_angle"]), 0.0, 90.0))
    # ── Erode-3.0 LAYER BINDINGS (rename the emitted layers; fold debris/sediment into final height). ──
    if "height_layer" in params:
        _try_set(n, "heightlayer", str(params["height_layer"]))
    if "debris_layer" in params:
        _try_set(n, "debrislayer", str(params["debris_layer"]))
    if "sediment_layer" in params:
        _try_set(n, "sedimentlayer", str(params["sediment_layer"]))
    if "flow_layer" in params:
        _try_set(n, "flowlayer", str(params["flow_layer"]))
    if "add_debris" in params:
        _try_set(n, "adddebris", bool(params["add_debris"]))
    if "add_sediment" in params:
        _try_set(n, "addsediment", bool(params["add_sediment"]))
    if "start_frame" in params:
        _try_set(n, "startframe", int(clamp(int(params["start_frame"]), -100000, 100000)))
    n.geometry()
    return {"node": n.path(), "mask_layer": str(gate) if gate else None}


@endpoint("heightfield_flatten")
def heightfield_flatten(params):
    """Flatten a masked region of a heightfield (erase features, or level a building footprint).

    method: value = set masked area to `elevation`; average = level to the masked area's own average
      height; slope = smoothly interpolate the boundary (default; ignores `elevation`).
    elevation: target height for method=value.
    mask_layer: which layer gates the flatten (0 = untouched, 1 = fully flattened; default mask).
    blurradius: soften the mask edge by this world distance.
    """
    n = child_after(params["input"], "heightfield_flatten", params.get("name"))
    if params.get("method") is not None:
        _menu_set(n, "method", params["method"], ("value", "average", "slope"))
    if "elevation" in params:
        if params.get("method") is None:
            _try_set(n, "method", 0)  # elevation only bites in Flatten-to-Value mode
        n.parm("height").set(clamp(float(params["elevation"]), -1e7, 1e7))
    if params.get("mask_layer"):
        _try_set(n, "masklayer", str(params["mask_layer"]))
    if "blurradius" in params:
        _try_set(n, "blurradius", clamp(float(params["blurradius"]), 0.0, 1e5))
    n.geometry()
    return {"node": n.path()}


@endpoint("heightfield_maskbyconcavity")
def heightfield_maskbyconcavity(params):
    """Mask concave regions (riverbeds / valleys / gullies) into a mask layer. Concavity is measured
    by sky visibility — rays are cast from each voxel to see how much horizon is blocked.

    concavity / maxconcavity: add voxels whose concavity is >= concavity and <= maxconcavity (the
      masked band). invert: mask outside that band instead. combine: how to merge with an existing
      mask (replace | add | subtract | multiply | max | min | blend). blend: blend amount when
      combine=blend. viewdistance: ray length for the concavity test (longer = more accurate, slower).
    """
    n = child_after(params["input"], "heightfield_maskbyconcavity", params.get("name"))
    if "concavity" in params:
        _try_set(n, "minconcavity", clamp(float(params["concavity"]), 0.0, 1.0))
    if "maxconcavity" in params:
        _try_set(n, "maxconcavity", clamp(float(params["maxconcavity"]), 0.0, 1.0))
    if params.get("combine") is not None:
        _menu_set(n, "combine", params["combine"], _NOISE_COMBINE)
    if "invert" in params:
        _try_set(n, "invertmask", bool(params["invert"]))
    if "blend" in params:
        _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    if "viewdistance" in params:
        _try_set(n, "viewdistance", clamp(float(params["viewdistance"]), 0.0, 1e6))
    n.geometry()
    return {"node": n.path()}


# ── height/slope visualizer + mask family (native-space inserts; params probe-safe via _try_set) ──
@endpoint("heightfield_visualize")
def heightfield_visualize(params):
    """Color-ramp a heightfield layer so the height/slope gradient is visible in the viewport.
    Inserts in native space (before a trailing 'place') so it reads the un-transformed field.

    input: SOP inside the heightfield geo.  layer: height layer to visualize as the 3D surface
    (default height; real node parm is `heightvolume`).  color_layer: mask layer to tint over the
    elevation ramp (node `cdvolume`).  preset: built-in diffuse color scheme (infrared | pink | mono
    | blackbody | bipartite).  min_elevation / max_elevation: manually pin the height->ramp range
    instead of auto-computing.
    compute_range (default true): auto-press the SOP's "Compute Range" buttons after cooking so
    Min/Max Elevation fill from the real heightfield and the ramp maps to actual elevation.
    """
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_visualize", params.get("name"))
    layer = str(params.get("layer", "height") or "height")
    # Real height-layer parm on heightfield_visualize is `heightvolume` (probe-verified); the old
    # `layer`/`heightlayer` names do not exist on this node.
    _try_set(n, "heightvolume", layer)
    if params.get("color_layer"):
        _try_set(n, "cdvolume", str(params["color_layer"]))
    if params.get("preset") is not None:
        _menu_set(n, "cdpreset", params["preset"],
                  ("none", "false", "pink", "mono", "blackbody", "bipartite"))
    if "min_elevation" in params:
        _try_set(n, "vis_minelevation", clamp(float(params["min_elevation"]), -1e9, 1e9))
    if "max_elevation" in params:
        _try_set(n, "vis_maxelevation", clamp(float(params["max_elevation"]), -1e9, 1e9))
    # Force-cook so the node (and its input heightfield) is evaluated BEFORE we press
    # "Compute Range": that callback reads the incoming elevation, so the field must be
    # cooked first or it computes against an empty/stale range.
    n.cook(force=True)
    # Auto-press the SOP's "Compute Range" button so Min/Max Elevation get filled from the
    # actual heightfield and the height ramp maps to real elevation (gold->green->white by
    # height) instead of sitting on a default range that a human would otherwise click.
    computed_range = None
    height_range = None
    # If the caller pinned min/max elevation manually, don't auto-press Compute Range by default
    # (it would overwrite their values); an explicit compute_range=True still wins.
    manual_elev = ("min_elevation" in params) or ("max_elevation" in params)
    compute = params.get("compute_range", not manual_elev)
    compute = (not manual_elev) if compute is None else bool(compute)
    if compute:
        # This node isn't in the offline probe, so the internal parm name is unknown --
        # try likely names (best guess first) and pressButton() on the FIRST one that is a
        # real hou.Parm, then stop. Guarded so a wrong name / callback error degrades to
        # "range not computed" rather than raising.
        try:
            n.cook(force=True)  # ensure input elevation is available to the callback
            # The HeightField Visualize HDA has MORE THAN ONE "Compute Range" button
            # (`computerange` for the tinting section, `computerange2` for the Material
            # Min/Max Elevation that actually drives the visible height ramp). Press EVERY
            # computerange* button -- pressing the first and stopping misses the one that matters.
            pressed = []
            candidates = [p.name() for p in n.parms() if p.name().startswith("computerange")]
            for extra in ("range", "computeminmax", "computeramprange",
                          "recompute", "computeheightrange"):
                if extra not in candidates and n.parm(extra) is not None:
                    candidates.append(extra)
            for pname in candidates:
                try:
                    p = n.parm(pname)
                    if p is not None:
                        p.pressButton()
                        pressed.append(pname)
                except Exception:
                    continue
            computed_range = pressed or None
        except Exception:
            computed_range = None
        # Best-effort read-back of the filled Min/Max Elevation (guarded, defensive names).
        if computed_range is not None:
            try:
                for lo, hi in (("vis_minelevation", "vis_maxelevation"),
                               ("minheight", "maxheight"),
                               ("minelevation", "maxelevation"),
                               ("rangemin", "rangemax")):
                    pl = n.parm(lo)
                    ph = n.parm(hi)
                    if pl is not None and ph is not None:
                        height_range = [pl.eval(), ph.eval()]
                        break
            except Exception:
                height_range = None
    # Display the COLORED heightfield in the viewport: the tail (placed) node carries the
    # visualization through the transform in its correct world position. Setting its display
    # flag auto-clears others in the same geo (takes display back from a downstream convert mesh).
    display = params.get("display", True)
    display = True if display is None else bool(display)
    displayed = None
    if display and tail is not None:
        tail.setRenderFlag(True)
        tail.setDisplayFlag(True)
        displayed = tail.path()
    return {"node": n.path(), "tail": tail.path(), "layer": layer, "displayed": displayed,
            "computed_range": computed_range, "range": height_range}


def _mask_common(n, params):
    """Apply the shared heightfield-mask-family parms (probe-verified across the maskby* nodes):
    output mask layer, invert, blend, and combine-with-existing (a real Menu)."""
    if params.get("mask_layer"):
        _try_set(n, "masklayer", str(params["mask_layer"]))
    if "invert" in params:
        _try_set(n, "invertmask", bool(params["invert"]))
    if "blend" in params:
        _try_set(n, "blend", clamp(float(params["blend"]), 0.0, 1.0))
    if params.get("combine") is not None:
        _menu_set(n, "combine", params["combine"], _NOISE_COMBINE)


@endpoint("heightfield_maskbyfeature")
def heightfield_maskbyfeature(params):
    """Mask terrain by one or more features (slope / height / facing direction) — isolate peaks,
    valleys, snow-line, plantable ground. When several criteria are on, the mask is their
    INTERSECTION. WARNING: with no criterion enabled the node flood-fills the mask to 1.

    Enable a criterion with its toggle, then set its band:
      maskbyslope + min_slopeangle / max_slopeangle (degrees): mask the slope band.
      maskbyheight + minheight / maxheight: mask the elevation band.
      maskbydir + goal_angle (deg, 0 = faces -X, +90 = faces -Z) + angle_spread: mask by facing.
    smooth_radius blurs the output mask (voxels). Plus the shared mask parms (mask_layer, invert,
    blend, combine).
    """
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_maskbyfeature", params.get("name"))
    _mask_common(n, params)
    _hf_apply(n, params, [
        ("smooth_radius", "smooth_radius", "f", 0.0, 1e5),
        ("maskbyslope", "maskbyslope", "b"),
        ("min_slopeangle", "min_slopeangle", "f", 0.0, 90.0),
        ("max_slopeangle", "max_slopeangle", "f", 0.0, 90.0),
        ("maskbyheight", "maskbyheight", "b"),
        ("minheight", "minheight", "f", -1e7, 1e7),
        ("maxheight", "maxheight", "f", -1e7, 1e7),
        ("maskbydir", "maskbydir", "b"),
        ("goal_angle", "goal_angle", "f", -180.0, 180.0),
        ("angle_spread", "angle_spread", "f", 0.0, 180.0),
        ("maskbycurvature", "maskbycurvature", "b"),
        ("max_curvature", "max_curvature", "f", 0.0, 5.0),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path()}


@endpoint("heightfield_maskbyocclusion")
def heightfield_maskbyocclusion(params):
    """Ambient-occlusion mask (cavities / crevices / sheltered ground) into the mask layer. Occlusion
    = how much of a sphere around each voxel is blocked by nearby terrain (ray-cast).

    minexposure / maxexposure: remap the occlusion band into the mask (below min -> 0, above max ->
      1). dohemisphere: sample only the upward hemisphere (sky occlusion) instead of a full sphere.
    viewdistance: ray length (0 = infinite; longer = more accurate, slower). Plus the shared mask
    parms (mask_layer, invert, blend, combine).
    """
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_maskbyocclusion", params.get("name"))
    _mask_common(n, params)
    _hf_apply(n, params, [
        ("minexposure", "minexposure", "f", 0.0, 1.0),
        ("maxexposure", "maxexposure", "f", 0.0, 1.0),
        ("dohemisphere", "dohemisphere", "b"),
        ("viewdistance", "viewdistance", "f", 0.0, 1e6),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path()}


@endpoint("heightfield_maskbyshadow")
def heightfield_maskbyshadow(params):
    """Mask the areas shadowed from a given sun direction (drives snow-melt, moss, sun/shade dressing).

    lightdir: sun azimuth in degrees (0 = light along +X, +90 = along -Z). lightangle: sun elevation
      in degrees (lower = longer shadows). opacity: mask value in shadow (0..1). falloff: feather
      width at shadow borders (0 = hard shadows). Plus the shared mask parms (mask_layer, invert,
      blend, combine); invert masks the SUNLIT areas instead.
    """
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_maskbyshadow", params.get("name"))
    _mask_common(n, params)
    _hf_apply(n, params, [
        ("lightdir", "lightdir", "f", -180.0, 180.0),
        ("lightangle", "lightangle", "f", 0.0, 90.0),
        ("opacity", "opacity", "f", 0.0, 1.0),
        ("falloff", "falloff", "f", 0.0, 5.0),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path()}


@endpoint("heightfield_maskbyobject")
def heightfield_maskbyobject(params):
    """Mask a heightfield region from other geometry (input1) into the mask layer — the 2D outline of
    surface geometry, or the intersection of a fog/SDF volume (for 3D-height projection use
    heightfield_project instead).

    object: the geometry (object-merged onto input 1). method: ray (project a surface down) | volume
      (fog) | sdf. maskdir: for ray method, project from both sides | above | below. maxdist: max ray
      distance before a projection is a miss. value: mask value where geometry hits. blurradius:
      soften the mask. Plus the shared mask parms (mask_layer, invert, blend, combine).
    """
    geo = _geo_of(params["input"])
    # cook=False: this node can't cook until its bounding object is on input 1 (wire, THEN cook).
    n, tail = _hf_append_native(geo, "heightfield_maskbyobject", params.get("name"), cook=False)
    if params.get("object"):
        # Input 1 must live in the SAME geo — a SOP can't take an input from a different geo object.
        # Object-merge the boundary geometry in first (same bridge scatter_copy uses for cross-geo).
        om = geo.createNode("object_merge", "mask_object")
        om.parm("objpath1").set(resolve_node(params["object"]).path())
        om.moveToGoodPosition()
        n.setInput(1, om)
    _mask_common(n, params)
    _hf_apply(n, params, [
        ("method", "method", "menu", ("ray", "volume", "sdf")),
        ("maskdir", "maskdir", "menu", ("both", "above", "below")),
        ("maxdist", "maxdist", "f", 0.0, 1e9),
        ("value", "value", "f", 0.0, 1.0),
        ("blurradius", "blurradius", "f", 0.0, 1e5),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path()}


@endpoint("heightfield_deform")
def heightfield_deform(params):
    """Deform geometry by a CHANGING heightfield: points rise/fall (and optionally rotate to the new
    slope) by the difference between the rest and current terrain — e.g. float packed props on a
    water surface, or apply isostatic-rebound tilt. The node's whole surface is just two knobs:

    blurradius: world distance the field is blurred before measuring height/slope change (set ~ the
      size of the object being moved). rotate: rotate points / packed prims to follow slope changes.
    """
    n = child_after(params["input"], "heightfield_deform", params.get("name"))
    if "blurradius" in params:
        n.parm("blurradius").set(clamp(float(params["blurradius"]), 0.0, 1e5))
    if "rotate" in params:
        n.parm("dorotate").set(bool(params["rotate"]))
    n.geometry()
    return {"node": n.path()}


_HF_LAYER_OPS = {
    "clear": "heightfield_layerclear",
    "prop": "heightfield_layerproperty",
    "isolate": "heightfield_isolatelayer",
}


@endpoint("heightfield_layer")
def heightfield_layer(params):
    """Layer utility on a named heightfield layer:
      clear   -> set every voxel of the layer to `value` (heightfield_layerclear).
      prop    -> set the layer's border-extension policy / compression (heightfield_layerproperty);
                 `border` = constant | repeat | streak | sdf (matters when tiling/merging fields).
      isolate -> copy the layer into `mask` (and optionally `height`) so the default red-tint
                 viewport shows it (heightfield_isolatelayer). overwrite_height/overwrite_mask control
                 which channels are overwritten.
    """
    op = str(params.get("op", "isolate"))
    if op not in _HF_LAYER_OPS:
        raise ValueError("op must be clear|prop|isolate")
    n = child_after(params["input"], _HF_LAYER_OPS[op], params.get("name"))
    layer = str(params.get("layer", "height"))
    if op == "clear":
        _try_set(n, "layer1", layer)
        if "value" in params:
            _try_set(n, "value1", clamp(float(params["value"]), -1e7, 1e7))
    else:
        _try_set(n, "layer", layer)
    if op == "prop" and params.get("border") is not None:
        _menu_set(n, "border", params["border"], ("constant", "repeat", "streak", "sdf"))
    if op == "isolate":
        if "overwrite_height" in params:
            _try_set(n, "overwriteheight", bool(params["overwrite_height"]))
        if "overwrite_mask" in params:
            _try_set(n, "overwritemask", bool(params["overwrite_mask"]))
    n.geometry()
    return {"node": n.path(), "op": op, "layer": layer}


@endpoint("terrain_analysis")
def terrain_analysis(params):
    """Labs Terrain Analysis: write slope / curvature (and avoidance) point attributes for scattering,
    pathfinding, and shading. The node's OUTPUTS are per-feature toggles (not one mode menu).

    mode (convenience): slope -> enables the `slope` attribute; curvature -> enables horizontal +
      vertical curvature; occlusion -> falls back to `slope` (this node has no native occlusion
      output — use heightfield_maskbyocclusion for that).
    Explicit toggles: slope, horizontal_curvature, vertical_curvature.
    scale: analysis scale, large (broad landforms) | small (fine detail) — the node's `analysismode`.
    neighbourhood_radius: sampling radius (node `raylength`) for the curvature/visibility rays.
    """
    n = child_after(params["input"], "labs::terrain_analysis::1.0", params.get("name"))
    mode = params.get("mode")
    if mode == "slope" or mode == "occlusion":
        _try_set(n, "slope", True)
    elif mode == "curvature":
        _try_set(n, "horizontalcurvature", True)
        _try_set(n, "verticalcurvature", True)
    if "slope" in params:
        _try_set(n, "slope", bool(params["slope"]))
    if "horizontal_curvature" in params:
        _try_set(n, "horizontalcurvature", bool(params["horizontal_curvature"]))
    if "vertical_curvature" in params:
        _try_set(n, "verticalcurvature", bool(params["vertical_curvature"]))
    if params.get("scale") is not None:
        idx = {"large": 0, "small": 1}.get(str(params["scale"]))
        if idx is not None:
            _try_set(n, "analysismode", idx)
    if "neighbourhood_radius" in params:
        _try_set(n, "raylength", clamp(float(params["neighbourhood_radius"]), 0.0, 1e4))
    n.geometry()
    return {"node": n.path()}


# ── packed-tile streaming (mem lane) ──────────────────────────────────────────────────────────
_TILE_LODS = ("full", "points", "box", "centroid", "hidden")


@endpoint("add_tile_packed")
def add_tile_packed(params):
    """Load a baked .bgeo(.sc) tile as a packed-disk proxy (near-zero display cost). Creator: FAILS
    on name collision (never destroys existing user nodes). lod = viewport proxy level."""
    name = params["name"]
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    bgeo = confined_path(params["path"])
    lod = str(params.get("lod", "box"))
    if lod not in _TILE_LODS:
        raise ValueError("lod must be full|points|box|centroid|hidden")
    tx = float(params.get("tx", 0.0))
    tz = float(params.get("tz", 0.0))
    g = obj.createNode("geo", name)
    f = g.createNode("file", "packed_tile")
    f.parm("file").set(bgeo)
    _try_set(f, "loadtype", "packedgeo")  # "Packed Disk Primitive"
    _try_set(f, "delayload", 1)
    f.parm("viewportlod").set(lod)
    last = f
    if tx or tz:
        x = g.createNode("xform", "place")
        x.setFirstInput(f)
        x.parmTuple("t").set((tx, 0.0, -tz))
        last = x
    last.setDisplayFlag(True)
    last.setRenderFlag(True)
    g.setDisplayFlag(True)
    g.layoutChildren()
    last.cook(force=True)
    pg = last.geometry()
    bb = pg.boundingBox()
    return {"node": g.path(), "sop": last.path(), "lod": lod, "packed_prims": len(pg.prims()),
            "bbox": {"min": list(bb.minvec()), "max": list(bb.maxvec())}}


@endpoint("set_tile_lod")
def set_tile_lod(params):
    """Flip one packed tile's viewport LOD (box proxy <-> full geometry) for a hero swap."""
    lod = str(params.get("lod", "box"))
    if lod not in _TILE_LODS:
        raise ValueError("lod must be full|points|box|centroid|hidden")
    g = resolve_node("/obj/" + params["name"] if not params["name"].startswith("/") else params["name"])
    f = g.node("packed_tile")
    if f is None:
        raise ValueError(f"no packed_tile SOP under {g.path()}")
    f.parm("viewportlod").set(lod)
    try:
        f.cook(force=True)
    except Exception:
        pass
    return {"node": g.path(), "lod": lod}


# ── MAX-CAPABILITY native heightfield ops (params verified against live H21.0.671) ─
# Table-driven param application: exposes every meaningful parm of each node, typed + clamped, so
# these wrappers surface the FULL node surface (not a 3-6 subset). Menu handling matches the probe:
#   - real Menu params  -> set BY INDEX via _menu_set (ordered token list)
#   - String-menu params (basis/fractal) -> set the STRING TOKEN directly


def _set_vec(node, parm, val, length, caster):
    """Set a multi-component parm tuple (pads/truncates to `length`, casts each element)."""
    if not isinstance(val, (list, tuple)):
        val = [val]
    vals = [caster(x) for x in val[:length]]
    vals += [caster(0)] * (length - len(vals))
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(vals))
        return True
    except Exception:
        return False


def _hf_apply(node, params, spec):
    """Apply a param spec table. Each entry is a tuple keyed by the caller-facing param name:
        (key, parm, "f", lo, hi)   -> float, clamped to [lo,hi]
        (key, parm, "i", lo, hi)   -> int, clamped to [lo,hi]
        (key, parm, "b")           -> toggle (bool)
        (key, parm, "s")           -> string (also used for string-valued menus: basis/fractal)
        (key, parm, "menu", toks)  -> real Menu set BY INDEX from ordered token tuple
        (key, parm, "vec", n)      -> float tuple of length n
        (key, parm, "ivec", n)     -> int tuple of length n
    Only keys present in `params` are touched (probe-safe: _try_set no-ops a missing parm)."""
    applied = {}
    for entry in spec:
        key = entry[0]
        if key not in params or params[key] is None:
            continue
        parm, kind = entry[1], entry[2]
        v = params[key]
        ok = False
        if kind == "f":
            ok = _try_set(node, parm, clamp(float(v), entry[3], entry[4]))
        elif kind == "i":
            ok = _try_set(node, parm, int(clamp(int(v), entry[3], entry[4])))
        elif kind == "b":
            ok = _try_set(node, parm, bool(v))
        elif kind == "s":
            ok = _try_set(node, parm, str(v))
        elif kind == "menu":
            ok = _menu_set(node, parm, v, entry[3])
        elif kind == "vec":
            ok = _set_vec(node, parm, v, entry[3], float)
        elif kind == "ivec":
            ok = _set_vec(node, parm, v, entry[3], int)
        if ok:
            applied[key] = v
    return applied


# menu token tables (exact tokens from the probe; order == menu index)
_NOISE_COMBINE = ("replace", "add", "subtract", "diff", "multiply", "max", "min", "blend")
_BLUR_METHOD = ("blur", "boxblur", "expand", "shrink", "sharpen")
_BLUR_BORDER = ("none", "constant", "repeat", "streak")
_FLOW_SLUMP = ("smooth", "granular")
_PROJ_MASKDIR = ("both", "above", "below")
_PROJ_COMBINE = ("replace", "add", "multiply", "max", "min")
_PROJ_JITTERCOMBINE = ("avg", "median", "min", "max")
_SCAT_METHOD = ("coverage", "density", "totalpointcount", "perpointcount")
_SCAT_PPC_METHOD = ("poissondist", "exactnumber")
_SCAT_POS_METHOD = ("offset", "origin", "ratio")
_SCAT_VAR_METHOD = ("uniformdist", "normaldist", "exactscale")
_SCAT_REMOVAL = ("onlyflag", "remove")
_SCAT_PIECE = ("attribute", "connectivity", "single")
_TERRACE_UNDULATION = ("0", "1", "2")


@endpoint("heightfield_noise")
def heightfield_noise(params):
    """Add procedural noise to a heightfield layer (the terrain-detail workhorse). Native insert so
    the noise is applied in un-transformed voxel space. Exposes the full noise surface: combine
    method, amplitude/scale/offset, noise basis + fractal, octaves/lacunarity/roughness, gain/bias,
    clipping, and lattice/gradient warp. `combine` is a real Menu (set by index); `basis`/`fractal`
    are string-menu tokens (e.g. basis=sparse, fractal=hmfT)."""
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_noise", params.get("name"), cook=False)
    applied = _hf_apply(n, params, [
        ("layer", "layer", "s"),
        ("masklayer", "masklayer", "s"),
        ("combine", "combine", "menu", _NOISE_COMBINE),
        ("blend", "blend", "f", 0.0, 1.0),
        ("centernoise", "centernoise", "b"),
        ("amp", "amp", "f", 0.0, 1e7),
        ("elementsize", "elementsize", "f", 0.001, 1e7),
        ("elementscale", "elementscale", "vec", 3),
        ("offset", "offset", "vec", 3),
        ("basis", "basis", "s"),
        ("fractal", "fractal", "s"),
        ("period", "period", "vec", 3),
        ("oct", "oct", "f", 0.0, 16.0),
        ("lac", "lac", "f", 0.0, 4.0),
        ("rough", "rough", "f", 0.0, 1.0),
        ("flowrot", "flowrot", "f", 0.0, 1.0),
        ("fold", "fold", "b"),
        ("complement", "complement", "b"),
        ("dogain", "dogain", "b"),
        ("gain", "gain", "f", 0.0, 1.0),
        ("dobias", "dobias", "b"),
        ("bias", "bias", "f", 0.0, 1.0),
        ("clipmin", "clipmin", "f", 0.0, 1.0),
        ("clipmax", "clipmax", "f", 0.0, 1.0),
        ("dolwarp", "dolwarp", "b"),
        ("accuml", "accuml", "b"),
        ("disp", "disp", "f", -0.5, 0.5),
        ("dispfreq", "dispfreq", "f", 0.0, 1.0),
        ("dogwarp", "dogwarp", "b"),
        ("accumg", "accumg", "b"),
        ("gflow", "gflow", "f", -0.5, 0.5),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path(), "applied": applied,
            "combine": n.parm("combine").eval() if n.parm("combine") else None,
            "basis": n.parm("basis").eval() if n.parm("basis") else None}


@endpoint("heightfield_blur")
def heightfield_blur(params):
    """Blur / box-blur / expand / shrink / sharpen a heightfield layer. Native insert. `method` and
    `bordertype` are real Menus (set by index)."""
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_blur", params.get("name"), cook=False)
    applied = _hf_apply(n, params, [
        ("layer", "layer", "s"),
        ("masklayer", "masklayer", "s"),
        ("maskaware", "maskaware", "b"),
        ("iterations", "iterations", "i", 0, 10000),
        ("method", "method", "menu", _BLUR_METHOD),
        ("radius", "radius", "f", 0.0, 1e6),
        ("bordertype", "bordertype", "menu", _BLUR_BORDER),
        ("borderval", "borderval", "f", -1e7, 1e7),
        ("sharpenstrength", "sharpenstrength", "f", 0.0, 10.0),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path(), "applied": applied,
            "method": n.parm("method").eval() if n.parm("method") else None}


@endpoint("heightfield_flowfield")
def heightfield_flowfield(params):
    """Compute a water flow / slump field over a heightfield (drives erosion masks, deposition).
    Native insert. `slumpmode` is a real Menu (set by index). Writes flow/mask/height layers."""
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_flowfield", params.get("name"), cook=False)
    applied = _hf_apply(n, params, [
        ("slumpmode", "slumpmode", "menu", _FLOW_SLUMP),
        ("rainamount", "rainamount", "f", 0.0, 1e6),
        ("raindensity", "raindensity", "f", 0.0, 1.0),
        ("iterations", "iterations", "i", 0, 100000),
        ("smoothiterations", "smoothiterations", "i", 0, 100000),
        ("domask", "domask", "b"),
        ("maskscale", "maskscale", "f", -1e6, 1e6),
        ("doheight", "doheight", "b"),
        ("heightscale", "heightscale", "f", -1e6, 1e6),
        ("heightlayer", "heightlayer", "s"),
        ("waterlayer", "waterlayer", "s"),
        ("flowlayer", "flowlayer", "s"),
        ("flowdirlayer", "flowdirlayer", "s"),
        ("seed", "seed", "f", 0.0, 1e9),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path(), "applied": applied,
            "slumpmode": n.parm("slumpmode").eval() if n.parm("slumpmode") else None}


@endpoint("heightfield_project")
def heightfield_project(params):
    """Raycast an input geometry onto a heightfield layer (stamp real geometry into the terrain).
    Native insert; the geometry to project is optional input1 (object-merged into the geo, matching
    heightfield_maskbyobject). `maskdir`, `combine`, `jittercombine` are real Menus (set by index)."""
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_project", params.get("name"), cook=False)
    if params.get("object"):
        om = geo.createNode("object_merge", "project_object")
        om.parm("objpath1").set(resolve_node(params["object"]).path())
        om.moveToGoodPosition()
        n.setInput(1, om)
    applied = _hf_apply(n, params, [
        ("layer", "layer", "s"),
        ("maskmode", "maskmode", "b"),
        ("maskdir", "maskdir", "menu", _PROJ_MASKDIR),
        ("heightlayer", "heightlayer", "s"),
        ("maskdensity", "maskdensity", "f", 0.0, 1e6),
        ("maskinvert", "maskinvert", "b"),
        ("hitfarthest", "hitfarthest", "b"),
        ("combine", "combine", "menu", _PROJ_COMBINE),
        ("maxraydist", "maxraydist", "f", 0.0, 1e9),
        ("dojitter", "dojitter", "b"),
        ("sample", "sample", "i", 1, 10000),
        ("jitter", "jitter", "f", 0.0, 1e6),
        ("jittercombine", "jittercombine", "menu", _PROJ_JITTERCOMBINE),
        ("seed", "seed", "f", 0.0, 1e9),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path(), "applied": applied,
            "combine": n.parm("combine").eval() if n.parm("combine") else None}


@endpoint("heightfield_scatter")
def heightfield_scatter(params):
    """Scatter tagged points across a heightfield using its mask layer (asset/instance placement).
    Native insert (heightfield_scatter 2.0). Full surface: scatter method, per-point-count,
    positioning, size variability, relaxation, terrain matching, piece definition, seeding, limits.
    All method params (`scattermethod`, `perpointcount_method`, `positioning_method`,
    `variability_method`, `relax_pointremovalmethod`, `piecemode`) are real Menus (set by index)."""
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_scatter::2.0", params.get("name"), cook=False)
    if params.get("source_points"):
        om = geo.createNode("object_merge", "scatter_source")
        om.parm("objpath1").set(resolve_node(params["source_points"]).path())
        om.moveToGoodPosition()
        n.setInput(1, om)
    applied = _hf_apply(n, params, [
        ("tag", "tag", "s"),
        ("scattermethod", "scattermethod", "menu", _SCAT_METHOD),
        ("layer", "layer", "s"),
        ("coverage", "coverage", "f", 0.0, 1.0),
        ("density", "density", "f", 0.0, 1e6),
        ("totalpointcount", "totalpointcount", "i", 0, 100_000_000),
        ("sourcetag", "sourcetag", "s"),
        ("perpointcount_method", "perpointcount_method", "menu", _SCAT_PPC_METHOD),
        ("perpointcount_exactnumber", "perpointcount_exactnumber", "f", 0.0, 1e6),
        ("perpointcount_poissonrange", "perpointcount_poissonrange", "ivec", 2),
        ("positioning_method", "positioning_method", "menu", _SCAT_POS_METHOD),
        ("positioning_origin", "positioning_origin", "vec", 2),
        ("positioning_offset", "positioning_offset", "vec", 2),
        ("positioning_ratio", "positioning_ratio", "vec", 2),
        ("outerradius", "outerradius", "f", 0.0, 1e6),
        ("falloff", "falloff", "f", 0.0, 1.0),
        ("variability_method", "variability_method", "menu", _SCAT_VAR_METHOD),
        ("variability_exactscale", "variability_exactscale", "f", 0.0, 1e6),
        ("variability_unifromrange", "variability_unifromrange", "vec", 2),
        ("variability_normalrange", "variability_normalrange", "vec", 2),
        ("variability_normalspread", "variability_normalspread", "f", 0.0, 1e6),
        ("relax_points", "relax_points", "b"),
        ("relax_selfoverlap", "relax_selfoverlap", "b"),
        ("relax_avoidtag", "relax_avoidtag", "s"),
        ("relax_maskcutoff", "relax_maskcutoff", "f", 0.0, 1.0),
        ("relax_iterations", "relax_iterations", "i", 0, 100000),
        ("relax_removingrate", "relax_removingrate", "f", 0.0, 1.0),
        ("relax_stepratio", "relax_stepratio", "f", 0.0, 1.0),
        ("relax_allowoutofbounds", "relax_allowoutofbounds", "b"),
        ("relax_pointremovalmethod", "relax_pointremovalmethod", "menu", _SCAT_REMOVAL),
        ("keepscatterpoints", "keepscatterpoints", "b"),
        ("keepterrain", "keepterrain", "b"),
        ("matchnormalterrain", "matchnormalterrain", "b"),
        ("matchslopeterrain", "matchslopeterrain", "b"),
        ("randomup", "randomup", "f", 0.0, 180.0),
        ("randomyaw", "randomyaw", "f", 0.0, 180.0),
        ("instancenewpoints", "instancenewpoints", "b"),
        ("piecemode", "piecemode", "menu", _SCAT_PIECE),
        ("pieceattrib", "pieceattrib", "s"),
        ("quant", "quant", "f", 0.0, 1.0),
        ("seed", "seed", "i", 0, 1_000_000_000),
        ("useemergencylimit", "useemergencylimit", "b"),
        ("emergencylimit", "emergencylimit", "i", 0, 1_000_000_000),
    ])
    n.cook(force=True)
    g = n.geometry()
    return {"node": n.path(), "tail": tail.path(), "applied": applied,
            "points": len(g.points()),
            "scattermethod": n.parm("scattermethod").eval() if n.parm("scattermethod") else None}


@endpoint("heightfield_terrace")
def heightfield_terrace(params):
    """Cut stepped terraces / mesas into a heightfield (heightfield_terrace 2.0). Native insert.
    Exposes height range, step/fade controls, undulation noise (basis/fractal string-menus,
    `undulation_type` real Menu by index), and mesa/cliff slope-mask outputs. Ramp parms are not
    exposed (not typed-settable)."""
    geo = _geo_of(params["input"])
    n, tail = _hf_append_native(geo, "heightfield_terrace::2.0", params.get("name"), cook=False)
    applied = _hf_apply(n, params, [
        ("heightlayer", "heightlayer", "s"),
        ("masklayer", "masklayer", "s"),
        ("minheight", "minheight", "f", -1e7, 1e7),
        ("maxheight", "maxheight", "f", -1e7, 1e7),
        ("terrace_fade", "terrace_fade", "f", 0.0, 1.0),
        ("terrace_max_step_size", "terrace_max_step_size", "f", 0.1, 1e6),
        ("terraceoffset", "terraceoffset", "f", -1e7, 1e7),
        ("smoothedges", "smoothedges", "f", 0.0, 1e6),
        ("min_mask", "min_mask", "f", 0.0, 1.0),
        ("undulation_type", "undulation_type", "menu", _TERRACE_UNDULATION),
        ("amp", "amp", "f", -1e7, 1e7),
        ("elementsize", "elementsize", "f", 0.001, 1e7),
        ("offset", "offset", "vec", 3),
        ("basis", "basis", "s"),
        ("fractal", "fractal", "s"),
        ("fold", "fold", "b"),
        ("mesalayer", "mesalayer", "s"),
        ("clifflayer", "clifflayer", "s"),
        ("slopesmoothradius", "slopesmoothradius", "f", 0.0, 1e6),
        ("mesa_maxslope", "mesa_maxslope", "f", 0.0, 90.0),
        ("cliff_minslope", "cliff_minslope", "f", 0.0, 90.0),
    ])
    n.cook(force=True)
    return {"node": n.path(), "tail": tail.path(), "applied": applied,
            "undulation_type": n.parm("undulation_type").eval() if n.parm("undulation_type") else None}


@endpoint("heightfield_remap")
def heightfield_remap(params):
    """Remap a heightfield LAYER's value range (heightfield_remap) — rescale height / mask / any scalar
    layer from [input_min, input_max] to [output_min, output_max]: normalize a DEM to 0..1, boost mask
    contrast, invert a layer (output_min>output_max), compress elevation. `input` = terrain (in0);
    optional mask terrain (in1). layer = which layer to remap (default 'height'); clamp_min / clamp_max
    hold out-of-range values at the output bounds."""
    n = child_after(params["input"], "heightfield_remap", params.get("name"))
    if "layer" in params:
        _try_set(n, "layer", str(params["layer"]))
    if "mask_layer" in params:
        _try_set(n, "masklayer", str(params["mask_layer"]))
    if "input_min" in params:
        _try_set(n, "inputmin", float(params["input_min"]))
    if "input_max" in params:
        _try_set(n, "inputmax", float(params["input_max"]))
    if "output_min" in params:
        _try_set(n, "outputmin", float(params["output_min"]))
    if "output_max" in params:
        _try_set(n, "outputmax", float(params["output_max"]))
    if "clamp_min" in params:
        _try_set(n, "clampmin", bool(params["clamp_min"]))
    if "clamp_max" in params:
        _try_set(n, "clampmax", bool(params["clamp_max"]))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()) if g else 0}


@endpoint("heightfield_resample")
def heightfield_resample(params):
    """Resample a heightfield to a new resolution (heightfield_resample) — down-res a huge DEM for fast
    iteration, or up-res before erosion / export. resolution_scale multiplies the current resolution
    (0.5 = half, 2.0 = double); OR exact_resolution=true with division_mode (maxaxis | size) +
    grid_samples (maxaxis) / grid_spacing (size) for a precise target. filter_scale widens the
    resampling filter (>1 = smoother, softer terrain). `input` = terrain."""
    n = child_after(params["input"], "heightfield_resample", params.get("name"))
    if "exact_resolution" in params:
        _try_set(n, "fixedresample", bool(params["exact_resolution"]))
    if "resolution_scale" in params:
        _try_set(n, "resscale", clamp(float(params["resolution_scale"]), 0.01, 100.0))
    if "division_mode" in params:
        _try_set(n, "fixedresample", 1)
        _menu_set(n, "divisionmode", str(params["division_mode"]), ("maxaxis", "size"))
    if "grid_samples" in params:
        _try_set(n, "fixedresample", 1)
        _try_set(n, "gridsamples", int(clamp(int(params["grid_samples"]), 2, 100000)))
    if "grid_spacing" in params:
        _try_set(n, "fixedresample", 1)
        _try_set(n, "gridspacing", clamp(float(params["grid_spacing"]), 1e-4, 1e6))
    if "filter_scale" in params:
        _try_set(n, "filterscale", clamp(float(params["filter_scale"]), 0.0, 100.0))
    g = n.geometry()
    return {"node": n.path(), "prims": len(g.prims()) if g else 0}

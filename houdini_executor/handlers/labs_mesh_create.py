"""SideFX Labs — Geometry/Mesh: Create (procedural primitive generators). Data-only handlers,
params verified against live H21.0.671 via hython probe.

All nodes in this lane are archetype A (generators / SOURCE nodes: 0 inputs, 1 output). Each builds
a fresh /obj geo and cooks bare. Every exposed param is a plain scalar / toggle / ordered-menu index
or a group-name string — there is NO file surface and NO code/callback param on any of these nodes,
so nothing is confined or forced off (SECURITY: none required; verified during the probe).

Wrapped (highest version of each base name): capsule, cylinder_generator, disc_generator,
hexagon_grid, quad_sphere_generator, simple_shapes, superformula_shapes.
"""

import hou
from houdini_executor.server import endpoint, clamp
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)






def _finish(geo, n):
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


# ── ordered-menu label tuples (position == the node's stored index) ───────────────────────────────
_AXIS3 = ("x", "y", "z")                                   # direction: X/Y/Z axis
_PLANE3 = ("xy", "yz", "zx")                                # orientation: XY/YZ/ZX plane
_CYL_FILL = ("single_polygon", "triangle_fan", "quad_fan")  # cylinder fillmode
_HEX_TYPE = ("polygon", "points")                           # hexagon_grid type
_HEX_CONN = ("individual", "connected")                     # hexagon_grid connectivity
_HEX_SHAPE = ("hexagon", "triangle", "rectangle", "parallelogram")   # hexagon_grid gridshape
_HEX_CELL = ("pointy_top", "flat_top")                      # hexagon_grid cellorientation
_SIMPLE_SHAPE = ("triangle", "diamond", "rectangle", "trapezoid",
                 "polygon", "star", "double_star", "square_star")     # simple_shapes shape
_SF_SHAPE = ("square", "circle", "triangle", "polygon", "diamond", "star", "squircle",
             "rounded_polygon", "clover", "flower", "sunburst", "eye",
             "teardrop", "heart", "custom")                 # superformula_shapes shapeselect


# ── 1. capsule (generator; 0 inputs) ──────────────────────────────────────────────────────────────
@endpoint("capsule")
def capsule(params):
    """Labs Capsule (labs::capsule::1.0) — a fresh /obj geo holding a capsule primitive (a cylinder
    body with two hemispherical caps). Shaping: `radius`, `height` (of the cylindrical body), `sides`
    (radial resolution), `bodysegments`/`capsegments` (lengthwise resolution), `direction` (long axis).
    Fails on name collision. Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::capsule::1.0")
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-4, 1e4))
    if "height" in params:
        _try_set(n, "height", clamp(float(params["height"]), 0.0, 1e4))
    if "sides" in params:
        _try_set(n, "sides", int(clamp(int(params["sides"]), 3, 512)))
    if "bodysegments" in params:
        _try_set(n, "bodysegments", int(clamp(int(params["bodysegments"]), 1, 512)))
    if "capsegments" in params:
        _try_set(n, "capsegments", int(clamp(int(params["capsegments"]), 1, 256)))
    if "direction" in params:
        _menu_set(n, "direction", str(params["direction"]), _AXIS3)
    return _finish(geo, n)


# ── 2. cylinder_generator (generator; 0 inputs) ───────────────────────────────────────────────────
@endpoint("cylinder_generator")
def cylinder_generator(params):
    """Labs Cylinder Generator (labs::cylinder_generator::2.0) — a fresh /obj geo holding a procedural
    cylinder/cone/tube with far more control than the native tube. `uniformradius` ties top+base to
    `radius`; disable it to taper via `topradius`/`baseradius`. `sides`/`divisions` set resolution;
    `opencylinder`+`arcstart`/`arcend` cut an open arc; `endcaps`+`fillmode` cap the ends. Fails on
    name collision. Data-only (group-name strings are labels, not paths; no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::cylinder_generator::2.0")
    if "uniformradius" in params:
        _try_set(n, "uniformradius", bool(params["uniformradius"]))
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-4, 1e4))
    if "topradius" in params:
        _try_set(n, "topradius", clamp(float(params["topradius"]), 0.0, 1e4))
    if "baseradius" in params:
        _try_set(n, "baseradius", clamp(float(params["baseradius"]), 0.0, 1e4))
    if "height" in params:
        _try_set(n, "height", clamp(float(params["height"]), 0.0, 1e4))
    if "sides" in params:
        _try_set(n, "sides", int(clamp(int(params["sides"]), 3, 1024)))
    if "divisions" in params:
        _try_set(n, "divisions", int(clamp(int(params["divisions"]), 1, 1024)))
    if "direction" in params:
        _menu_set(n, "direction", str(params["direction"]), _AXIS3)
    if "opencylinder" in params:
        _try_set(n, "opencylinder", bool(params["opencylinder"]))
    if "arcstart" in params:
        _try_set(n, "arcstart", clamp(float(params["arcstart"]), -360.0, 360.0))
    if "arcend" in params:
        _try_set(n, "arcend", clamp(float(params["arcend"]), -360.0, 360.0))
    if "endcaps" in params:
        _try_set(n, "endcaps", bool(params["endcaps"]))
    if "fillmode" in params:
        _menu_set(n, "fillmode", str(params["fillmode"]), _CYL_FILL)
    if "adduvs" in params:
        _try_set(n, "adduvs", bool(params["adduvs"]))
    return _finish(geo, n)


# ── 3. disc_generator (generator; 0 inputs) ───────────────────────────────────────────────────────
@endpoint("disc_generator")
def disc_generator(params):
    """Labs Disc Generator (labs::disc_generator::1.1) — a fresh /obj geo holding a flat disc / ring /
    annulus. `innerradius`>0 makes a ring/washer; `outerradius` is the rim. `sides`/`divisions` set
    resolution; `arcstart`/`arcend` cut a pie wedge; `orientation` picks the plane; `innerheight`/
    `outerheight` can loft it into a shallow cone/funnel. Fails on name collision. Data-only."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::disc_generator::1.1")
    if "innerradius" in params:
        _try_set(n, "innerradius", clamp(float(params["innerradius"]), 0.0, 1e4))
    if "outerradius" in params:
        _try_set(n, "outerradius", clamp(float(params["outerradius"]), 1e-4, 1e4))
    if "sides" in params:
        _try_set(n, "sides", int(clamp(int(params["sides"]), 3, 1024)))
    if "divisions" in params:
        _try_set(n, "divisions", int(clamp(int(params["divisions"]), 1, 512)))
    if "arcstart" in params:
        _try_set(n, "arcstart", clamp(float(params["arcstart"]), -360.0, 360.0))
    if "arcend" in params:
        _try_set(n, "arcend", clamp(float(params["arcend"]), -360.0, 360.0))
    if "orientation" in params:
        _menu_set(n, "orientation", str(params["orientation"]), _PLANE3)
    if "innerheight" in params:
        _try_set(n, "innerheight", clamp(float(params["innerheight"]), -1e4, 1e4))
    if "outerheight" in params:
        _try_set(n, "outerheight", clamp(float(params["outerheight"]), -1e4, 1e4))
    if "adduvs" in params:
        _try_set(n, "adduvs", bool(params["adduvs"]))
    return _finish(geo, n)


# ── 4. hexagon_grid (generator; 0 inputs) ─────────────────────────────────────────────────────────
@endpoint("hexagon_grid")
def hexagon_grid(params):
    """Labs Hexagon Grid (labs::hexagon_grid::1.0) — a fresh /obj geo holding a hex-tiled grid.
    `type`=polygon builds hex faces (mesh); `type`=points outputs just the hex centers. `gridshape`
    sets the overall footprint (hexagon/triangle/rectangle/parallelogram), `gridsize` its extent,
    `cellradius` the per-hex size, `cellorientation` pointy vs flat top, `orientation` the plane.
    `connectivity`=connected fuses shared edges. Fails on name collision. Data-only (the coordinate
    attribute name is a label, not a path)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::hexagon_grid::1.0")
    if "type" in params:
        _menu_set(n, "type", str(params["type"]), _HEX_TYPE)
    if "connectivity" in params:
        _menu_set(n, "connectivity", str(params["connectivity"]), _HEX_CONN)
    if "orientation" in params:
        _menu_set(n, "orientation", str(params["orientation"]), _PLANE3)
    if "gridshape" in params:
        _menu_set(n, "gridshape", str(params["gridshape"]), _HEX_SHAPE)
    if "gridsize" in params:
        _try_set(n, "gridsize", int(clamp(int(params["gridsize"]), 0, 200)))
    if "cellorientation" in params:
        _menu_set(n, "cellorientation", str(params["cellorientation"]), _HEX_CELL)
    if "cellradius" in params:
        _try_set(n, "cellradius", clamp(float(params["cellradius"]), 1e-4, 1e4))
    return _finish(geo, n)


# ── 5. quad_sphere_generator (generator; 0 inputs) ────────────────────────────────────────────────
@endpoint("quad_sphere_generator")
def quad_sphere_generator(params):
    """Labs Quad Sphere Generator (labs::quad_sphere_generator::1.1) — a fresh /obj geo holding a
    quad-only (subdivided-cube) sphere with clean, even topology (unlike the pole-pinched native
    sphere). `subdivisions` is EXPONENTIAL in polycount (6*4^n quads) and is hard-clamped to <=7.
    Fails on name collision. Data-only (no file surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::quad_sphere_generator::1.1")
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-4, 1e4))
    if "subdivisions" in params:
        _try_set(n, "subdivisions", int(clamp(int(params["subdivisions"]), 0, 7)))  # EXP — hard cap 7
    if "adduvs" in params:
        _try_set(n, "adduvs", bool(params["adduvs"]))
    return _finish(geo, n)


# ── 6. simple_shapes (generator; 0 inputs) ────────────────────────────────────────────────────────
@endpoint("simple_shapes")
def simple_shapes(params):
    """Labs Simple Shapes (labs::simple_shapes::2.0) — a fresh /obj geo holding one of a family of 2D
    profile shapes selected by `shape` (triangle/diamond/rectangle/trapezoid/polygon/star/double_star/
    square_star). `base`/`height` size the rectangular family; `radius`/`sides`/`points`/`innerradius`
    drive the polygon & star families. `closed` closes the profile into a face; `adduvs` adds UVs.
    Fails on name collision. Data-only."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::simple_shapes::2.0")
    if "shape" in params:
        _menu_set(n, "shape", str(params["shape"]), _SIMPLE_SHAPE)
    if "base" in params:
        _try_set(n, "base", clamp(float(params["base"]), 0.0, 1e4))
    if "height" in params:
        _try_set(n, "height", clamp(float(params["height"]), 0.0, 1e4))
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-4, 1e4))
    if "sides" in params:
        _try_set(n, "sides", int(clamp(int(params["sides"]), 3, 512)))
    if "points" in params:
        _try_set(n, "points", int(clamp(int(params["points"]), 2, 512)))
    if "innerradius" in params:
        _try_set(n, "innerradius", clamp(float(params["innerradius"]), 0.0, 1e4))
    if "top" in params:
        _try_set(n, "top", clamp(float(params["top"]), 0.0, 1e4))
    if "shear" in params:
        _try_set(n, "shear", clamp(float(params["shear"]), -1e4, 1e4))
    if "closed" in params:
        _try_set(n, "closed", bool(params["closed"]))
    if "adduvs" in params:
        _try_set(n, "adduvs", bool(params["adduvs"]))
    return _finish(geo, n)


# ── 7. superformula_shapes (generator; 0 inputs) ──────────────────────────────────────────────────
@endpoint("superformula_shapes")
def superformula_shapes(params):
    """Labs Superformula Shapes (labs::superformula_shapes::1.0) — a fresh /obj geo holding a 2D shape
    from the superformula family, selected by `shapeselect` (square/circle/triangle/polygon/diamond/
    star/squircle/rounded_polygon/clover/flower/sunburst/eye/teardrop/heart/custom). `width`/`height`
    size it; `circpointnum` sets circle/curve resolution; `polysides`/`starspokes`+`starpinchbloat`/
    `flowerspokes` drive the polygon/star/flower families. `fillshape` fills the profile into a
    surface (otherwise it is an outline curve); `roundcorners` bevels corners. Fails on name
    collision. Data-only."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::superformula_shapes::1.0")
    if "shapeselect" in params:
        _menu_set(n, "shapeselect", str(params["shapeselect"]), _SF_SHAPE)
    if "width" in params:
        _try_set(n, "width", clamp(float(params["width"]), 1e-4, 1e4))
    if "height" in params:
        _try_set(n, "height", clamp(float(params["height"]), 1e-4, 1e4))
    if "circpointnum" in params:
        _try_set(n, "circpointnum", int(clamp(int(params["circpointnum"]), 3, 8192)))
    if "polysides" in params:
        _try_set(n, "polysides", int(clamp(int(params["polysides"]), 3, 512)))
    if "starspokes" in params:
        _try_set(n, "starspokes", int(clamp(int(params["starspokes"]), 2, 512)))
    if "starpinchbloat" in params:
        _try_set(n, "starpinchbloat", clamp(float(params["starpinchbloat"]), 0.0, 100.0))
    if "flowerspokes" in params:
        _try_set(n, "flowerspokes", int(clamp(int(params["flowerspokes"]), 2, 512)))
    if "roundcorners" in params:
        _try_set(n, "roundcorners", bool(params["roundcorners"]))
    if "fillshape" in params:
        _try_set(n, "fillshape", bool(params["fillshape"]))
    return _finish(geo, n)

"""SOP deformers lane — single-cook geometry deformers: smoothing/relax (delta_mush,
surface_relax), soft/falloff transforms (soft_transform, soft_peak, elastic_transform), magnet-shape
deformers (magnet, bulge), surface projection (creep), convex hull (shrinkwrap), point-cloud driven
deform (vector_deform), collision de-penetration (detangle), and the mesh Laplacian operator
(laplacian).

All params + menu tokens verified against live H21.0.671 via hython probe.
These are single-cook SOPs (NOT sims) and cook headless on a properly-wired fixture. Archetypes:
  * Single-input deformers: delta_mush, soft_transform, soft_peak, elastic_transform, shrinkwrap,
    laplacian, detangle (detangle needs a `prev_pos` vector attribute on the input — set prev_pos to
    an existing vector attr such as "P" for a static/no-collision cook).
  * Two-input deformers (extra operand via bridge_input): magnet + bulge (`magnet` shape, in1),
    creep (`surface` to crawl over, in1), surface_relax (`reference` surface, in1).
  * Three-input: vector_deform (`rest_points` in1 + `deformed_points` in2 drive the deformation).
  Any genuinely-required operand that is missing degrades to cooked:false via _finish_op — no crash.

Not wrapped (already covered): pathdeform -> tool `path_deform` = labs::path_deform.
DEFERRED: linearsolver -> a numeric matrix/linear-algebra solver expecting a matrix encoded in a
volume/attributes ('Volume primitive value not found' headless); it is not a mesh deformer and has no
verifiable data-only cook here — WIRE-only, left for a dedicated numeric-solver lane.

SECURITY: the curated param sets expose ONLY data params (iterations, distances, strengths, menu
tokens, booleans, group/attribute-name strings, vec3s). No file-path, VEX/expression, python, or
callback parm is exposed (probe-confirmed).
"""

import hou
from houdini_executor.server import (
    endpoint, child_after, clamp, resolve_node, bridge_input,
)
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── shared helpers (copied from the feather lane idiom; probe-safe) ──────────────────────────────────




def _str_menu_set(node, parm, token, tokens):
    if token in tokens:
        return _try_set(node, parm, token)
    return False


def _vec_set(node, parm, values):
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set([float(x) for x in values])
        return True
    except Exception:  # noqa: BLE001
        try:
            pt.set([int(x) for x in values])
            return True
        except Exception:  # noqa: BLE001
            return False


def _apply(node, params, spec):
    """kinds: f=float[min,max] i=int[min,max] b=bool s=string m=index-menu(tokens)
       ms=string-menu(tokens) v=vec/tuple."""
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
        elif kind == "v":
            _vec_set(node, parm, v)


def _geo_or_none(n):
    try:
        return n.geometry()
    except Exception:  # noqa: BLE001
        return None


def _finish_op(n, **extra):
    """Report counts when the node cooked; otherwise cooked:false + errors (never crash — guards BOTH
    the cook and the geometry readback for input-starved deformers)."""
    r = {"node": n.path()}
    try:
        n.cook()
    except Exception:  # noqa: BLE001
        pass
    g = _geo_or_none(n)
    if g is None:
        r["cooked"] = False
        e = [str(x) for x in (n.errors() or [])]
        if e:
            r["errors"] = e
    else:
        r["cooked"] = True
        r["points"] = len(g.points())
        r["prims"] = len(g.prims())
    r.update(extra)
    return r


_XORD = ("srt", "str", "rst", "rts", "tsr", "trs")
_RORD = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")
_GT = ("guess", "breakpoints", "edges", "points", "prims")
_DISTMETRIC = ("custom", "edges", "global", "globalconnected", "surface")
_SOFTTYPE = ("linear", "quadratic", "cubic", "meta")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SMOOTHING / RELAX
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("delta_mush")
def delta_mush(params):
    """Delta Mush — smooth a deformed mesh while preserving surface detail (deltamush) — the standard
    fix for lumpy skinning / jittery deformations. `input` (deformed geometry) is input 0; optional
    `reference` (input 1) provides the rest shape. method (uniform | edgelength); iterations +
    step_size control the smoothing strength; pin_border holds boundary points; symmetrize +
    symmetry_axis mirror the smoothing; recompute_normals refreshes normals. Moves points only."""
    n = child_after(params["input"], "deltamush", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("method", "method", "m", ("uniform", "edgelength")),
        ("iterations", "iterations", "i", (0, 200)),
        ("step_size", "stepsize", "f", (0.0, 1.0)),
        ("pin_border", "pinborder", "b", None),
        ("symmetrize", "symmetrize", "b", None),
        ("symmetry_axis", "symmetryaxis", "m", ("x", "y", "z")),
        ("recompute_normals", "updateaffectednmls", "b", None),
    ])
    return _finish_op(n)


@endpoint("surface_relax")
def surface_relax(params):
    """Surface Relax — evenly redistribute points across a surface to relax bunched/stretched topology
    (surfacerelax). `input` (surface) is input 0; optional `reference` (input 1) is a reference
    surface the points are re-projected onto during the relax. iterations the relax passes; pin_group
    holds named points fixed. Improves point distribution without changing the surface shape much."""
    n = child_after(params["input"], "surfacerelax", params.get("name"))
    if params.get("reference"):
        bridge_input(n, params["reference"], index=1, name_hint="reference")
    _apply(n, params, [
        ("iterations", "iterations", "i", (0, 1000)),
        ("pin_group", "pingroup", "s", None),
    ])
    return _finish_op(n)


@endpoint("laplacian")
def laplacian(params):
    """Laplacian — compute the discrete Laplace operator (cotangent / mean-value / Wachspress / Tutte
    weights) of a mesh and store it as a sparse matrix in attributes (laplacian) — the backbone of
    mesh diffusion, smoothing, and geometry-processing solves. `input` (mesh) is input 0. mode picks
    the weighting scheme; separate_mass splits out the mass matrix; diffusion + diffusion_coeff build
    a diffusion matrix instead; epsilon regularizes. This is an analysis/operator node (writes matrix
    attributes), not a shape deformer. Data-only; no code parm."""
    n = child_after(params["input"], "laplacian", params.get("name"))
    _apply(n, params, [
        ("mode", "mode", "m", ("cotan", "meanvalue", "wachspress", "tutte")),
        ("separate_mass", "separatemass", "b", None),
        ("diffusion", "diffusion", "b", None),
        ("diffusion_coeff", "diffusioncoeff", "f", (0.0, 1000.0)),
        ("epsilon", "epsilon", "f", (0.0, 1000.0)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SOFT / FALLOFF TRANSFORMS
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("soft_transform")
def soft_transform(params):
    """Soft Transform — move/rotate/scale a region of points with a smooth radial falloff (softxform) —
    a proportional-edit / magnet grab. `input` is input 0; `group` seeds the affected region.
    translate / rotate / scale the transform; distance_metric how falloff distance is measured
    (custom | edges | global | globalconnected | surface); soft_radius the falloff reach; soft_type the
    falloff profile (linear | quadratic | cubic | meta); attribs which attributes follow. Point-move
    only, no code parm."""
    n = child_after(params["input"], "softxform", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("translate", "t", "v", None),
        ("rotate", "r", "v", None),
        ("scale", "s", "v", None),
        ("distance_metric", "distmetric", "m", _DISTMETRIC),
        ("soft_radius", "rad", "f", (0.0, 1000.0)),
        ("soft_type", "type", "m", _SOFTTYPE),
        ("attribs", "attribs", "s", None),
    ])
    return _finish_op(n)


@endpoint("soft_peak")
def soft_peak(params):
    """Soft Peak — push points along their normals with a smooth radial falloff (softpeak) — a soft
    inflate/dent brush. `input` is input 0; `group` seeds the affected region. distance the push
    amount along normals; distance_metric how falloff distance is measured; soft_radius the falloff
    reach; soft_type the profile (linear | quadratic | cubic | meta); mask a global multiplier. Moves
    points along normals only."""
    n = child_after(params["input"], "softpeak", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("distance", "dist", "f", (-1000.0, 1000.0)),
        ("distance_metric", "distmetric", "m", _DISTMETRIC),
        ("soft_radius", "rad", "f", (0.0, 1000.0)),
        ("soft_type", "type", "m", _SOFTTYPE),
        ("mask", "mask", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)


@endpoint("elastic_transform")
def elastic_transform(params):
    """Elastic Transform — deform a mesh as an elastic solid via a grab / twist / scale / pinch handle
    that propagates through the material (elastictransform) — feels like pulling soft rubber. `input`
    is input 0; `group` seeds the handle region. rigidity how stiffly the deformation spreads; mode
    (grab | twist | scale | pinch); grab_direction + grab_strength drive a grab; twist_angle,
    scale_amount, pinch_strength drive the other modes; origin the handle centre; radius the handle
    reach. Point-deform only, no code parm."""
    n = child_after(params["input"], "elastictransform", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("group_type", "grouptype", "m", ("guess", "vertices", "edges", "points", "prims")),
        ("rigidity", "poissonratio", "f", (0.0, 0.5)),
        ("mode", "stroke_sculptmode", "m", ("grab", "twist", "scale", "pinch")),
        ("grab_direction", "grab_displacement", "v", None),
        ("grab_strength", "grab_strength", "f", (-1000.0, 1000.0)),
        ("twist_angle", "twist_angle", "f", (-360000.0, 360000.0)),
        ("scale_amount", "scale_amount", "f", (-1000.0, 1000.0)),
        ("pinch_strength", "pinch_strength", "f", (-1000.0, 1000.0)),
        ("origin", "stroke_origin", "v", None),
        ("radius", "stroke_radius", "f", (0.0, 1000.0)),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# MAGNET-SHAPE DEFORMERS
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("magnet")
def magnet(params):
    """Magnet — deform `input` points by a moving 'magnet' shape whose metaball-style field falls off
    with distance (magnet) — squash/stretch, dents, muscle bulges driven by a proxy shape. `input`
    (points to deform) is input 0; required `magnet` (the magnet-field geometry, e.g. a metaball or
    mesh) is input 1. translate / rotate / scale move the magnet's influence; deform_group /
    magnet_group restrict the regions; affect_position / affect_color / affect_normal pick what the
    field modulates. Without the `magnet` input it degrades to cooked:false."""
    n = child_after(params["input"], "magnet", params.get("name"))
    if params.get("magnet"):
        bridge_input(n, params["magnet"], index=1, name_hint="magnet")
    _apply(n, params, [
        ("deform_group", "deformGrp", "s", None),
        ("magnet_group", "magnetGrp", "s", None),
        ("group_type", "grouptype", "m", _GT),
        ("translate", "t", "v", None),
        ("rotate", "r", "v", None),
        ("scale", "s", "v", None),
        ("affect_position", "position", "b", None),
        ("affect_color", "color", "b", None),
        ("affect_normal", "nml", "b", None),
    ])
    return _finish_op(n)


@endpoint("bulge")
def bulge(params):
    """Bulge — push `input` points outward/inward along their normals where a 'magnet' shape overlaps
    them (bulge) — a fast localized swell driven by a proxy shape. `input` (points to bulge) is input
    0; required `magnet` (the influence geometry) is input 1. magnitude the bulge strength (+out /
    -in); deform_group / magnet_group restrict the regions; normalize_weight normalizes the field
    weighting. Without the `magnet` input it degrades to cooked:false."""
    n = child_after(params["input"], "bulge", params.get("name"))
    if params.get("magnet"):
        bridge_input(n, params["magnet"], index=1, name_hint="magnet")
    _apply(n, params, [
        ("deform_group", "deformGrp", "s", None),
        ("magnet_group", "magnetGrp", "s", None),
        ("group_type", "grouptype", "m", _GT),
        ("magnitude", "mag", "f", (-1000.0, 1000.0)),
        ("normalize_weight", "nml", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# PROJECTION / POINT-CLOUD DRIVEN / HULL
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("creep")
def creep(params):
    """Creep — project `input` geometry onto a surface's UV space and crawl it across that surface
    (creep) — stick decals/tracks/text onto a mesh, or animate geo sliding over it. `input` (geometry
    to project) is input 0; required `surface` (geometry to project onto) is input 1. translate /
    rotate / scale slide + size the projection in the surface's parametric space; initialize
    (initfill | initundistort) the projection setup; set_uv + uv_name write a creep-UV attribute;
    path_group restricts the crawl path. Without the `surface` input it degrades to cooked:false."""
    n = child_after(params["input"], "creep", params.get("name"))
    if params.get("surface"):
        bridge_input(n, params["surface"], index=1, name_hint="surface")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("path_group", "path", "s", None),
        ("initialize", "Initialize", "m", ("initfill", "initundistort")),
        ("translate", "t", "v", None),
        ("rotate", "r", "v", None),
        ("scale", "s", "v", None),
        ("set_uv", "douv", "b", None),
        ("uv_name", "uvname", "s", None),
    ])
    return _finish_op(n)


@endpoint("vector_deform")
def vector_deform(params):
    """Vector Deform — deform `input` by the difference between two matching point clouds (a rest set
    and a deformed set), interpolating that motion field onto the mesh (vectordeform) — cage/lattice
    style deformation from arbitrary driver points. `input` (mesh to deform) is input 0; required
    `rest_points` (input 1) and `deformed_points` (input 2) drive the field. inner_radius /
    outer_radius the interpolation falloff; steps the interpolation quality; translate / rotate an
    extra transform. Without both driver inputs it degrades to cooked:false."""
    n = child_after(params["input"], "vectordeform", params.get("name"))
    if params.get("rest_points"):
        bridge_input(n, params["rest_points"], index=1, name_hint="rest_points")
    if params.get("deformed_points"):
        bridge_input(n, params["deformed_points"], index=2, name_hint="deformed_points")
    _apply(n, params, [
        ("group", "group", "s", None),
        ("translate", "t", "v", None),
        ("rotate", "r", "v", None),
        ("inner_radius", "innerrad", "f", (0.0, 1000.0)),
        ("outer_radius", "outerrad", "f", (0.0, 1000.0)),
        ("steps", "steps", "i", (1, 100)),
    ])
    return _finish_op(n)


@endpoint("shrinkwrap")
def shrinkwrap(params):
    """Shrinkwrap — wrap a tight convex hull around the `input` points (shrinkwrap) — fast collision
    proxies, bounding shells, simplified silhouettes. `input` (points to hull) is input 0. type
    (xyz = full 3D hull | xy = 2D planar hull); shrink_amount insets the hull inward; plane_origin /
    plane_normal define the projection plane for the 2D mode; preserve_attribs carries source
    attributes; remove_inline_points cleans collinear hull points. Single input; emits the hull."""
    n = child_after(params["input"], "shrinkwrap", params.get("name"))
    _apply(n, params, [
        ("group", "group", "s", None),
        ("type", "type", "m", ("xyz", "xy")),
        ("shrink_amount", "shrinkamount", "f", (0.0, 1000.0)),
        ("plane_origin", "planeorigin", "v", None),
        ("plane_normal", "planenormal", "v", None),
        ("preserve_attribs", "preserveattribs", "b", None),
        ("remove_inline_points", "removeinlinepoints", "b", None),
    ])
    return _finish_op(n)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# COLLISION DE-PENETRATION
# ══════════════════════════════════════════════════════════════════════════════════════════════════
@endpoint("detangle")
def detangle(params):
    """Detangle — push self-intersecting / interpenetrating geometry apart so it stops overlapping
    (detangle) — cleanup for cloth, hair, or crowd meshes that have tangled. `input` (self-colliding
    geometry) is input 0. REQUIRES a `prev_pos` point vector attribute naming the previous positions
    (set it to an existing vector attr such as "P" for a static / no-motion cook); thickness the
    collision shell; self_collisions + resolve_collisions toggle the solve; max_weight caps push
    strength; external_friction / self_friction damp sliding. Point-move only. Without a valid
    `prev_pos` it degrades to cooked:false."""
    n = child_after(params["input"], "detangle", params.get("name"))
    _apply(n, params, [
        ("prev_pos", "prevpos", "s", None),
        ("thickness", "thickness", "f", (0.0, 1000.0)),
        ("self_collisions", "doself", "b", None),
        ("resolve_collisions", "doresolve", "b", None),
        ("max_weight", "maxweight", "f", (0.0, 1.0)),
        ("external_friction", "externalfriction", "f", (0.0, 1.0)),
        ("self_friction", "selffriction", "f", (0.0, 1.0)),
    ])
    return _finish_op(n)

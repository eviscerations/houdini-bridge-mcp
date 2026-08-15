"""SideFX Labs — Geometry/Analysis lane (data-only handlers). Params verified against live
H21.0.671. Each node is an Archetype-B CHAIN node: it takes a
mesh on input 0, MEASURES/ANALYZES it, and writes a result ATTRIBUTE (occlusion, slope, thickness,
border-distance, edge convexity, Gaussian curvature, curvature convex/concave, physical AO, spectral
features) or acts as a geometry-type VALIDATOR. Several also write a display `Cd` (visualization) —
that is a legitimate data output and is wrapped.

SECURITY: NONE of these nodes carry a file/cache/output-path surface and NONE expose a code/callback
parm, so there is no `confined_path` use here and no forced-off write toggle. The only string parms
exposed are ATTRIBUTE NAMES (e.g. `occattr`, `distattr`) and GROUP NAMES — internal geometry labels,
not filesystem paths. Ramps, folder headers, the social `like_btn` button, and all `*ramp*`
point/interp parms are intentionally not exposed (can't be driven by a flat scalar tool).

Note on the `<<CODE?>>` probe flags: params like `convexity*` / `convex_*` matched the substring
"vex" but are curvature (conVEXity) controls, NOT VEX code — confirmed Float/String, safe to set.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set






def _str_menu_set(node, parm, token, tokens):
    """Set a STRING menu parm (token-valued) by its token string, if the token is valid."""
    if token in tokens:
        return _try_set(node, parm, str(token))
    return False


def _result(n, **extra):
    """Cook and report prims/points/errors; tolerates a None geometry (analysis node that
    refused to cook -> surfaced as errors rather than an exception)."""
    g = n.geometry()
    out = {"node": n.path()}
    if g is None:
        out.update({"points": 0, "prims": 0, "errors": [str(e) for e in n.errors()]})
    else:
        out.update({"points": len(g.points()), "prims": len(g.prims())})
    out.update(extra)
    return out


# ── ordered-menu token tuples (position == the stored index) ──────────────────────────────────────
_SMOOTH_METHOD = ("uniform", "edgelength")            # method: post-analysis smoothing walk
_INFLUENCE = ("connectivity", "proximity")            # influencetype: smoothing neighbour source
_DIST_OUTTYPE = ("raw", "normalized", "unboundedraw")  # distance_from_border outputtype
_DIST_METRIC = ("edge", "global", "surface")          # distance_from_border distance metric
_CURV_GROUPTYPE = ("guess", "vertices", "edges", "points", "prims")  # fast_gaussian_curvature group
# validate_geometry_type STRING-menu tokens
_VGT_GEOTYPE = ("Point", "Poly", "Volume", "VDB", "NURBCurve", "BezierCurve", "MetaBall")
_VGT_COMPARE = ("equal", "not equal", "greater", "greateroequal", "less", "lessoequal",
                "range", "outrange")


# ── 1. calculate_occlusion (in0 mesh, in1 optional occluder) — writes Cd + occ attr ───────────────
@endpoint("calculate_occlusion")
def calculate_occlusion(params):
    """SideFX Labs Calculate Occlusion (labs::calculate_occlusion::2.0) — ambient-occlusion / cavity
    analysis: ray-casts against the surface (and an optional `occluder` on input 1) and writes an
    occlusion value into point attribute `occattr` (and a display `Cd` when `colorout` is on). `method`
    + `influencetype` + `iterations` + `blur` control the post-smoothing. Data-only (no file surface)."""
    n = child_after(params["input"], "labs::calculate_occlusion::2.0", params.get("name"))
    if params.get("occluder"):
        bridge_input(n, params["occluder"], index=1, name_hint="occluder")
    if "raycount" in params:
        _try_set(n, "raycount", int(clamp(int(params["raycount"]), 1, 8192)))
    if "bias" in params:
        _try_set(n, "bias", clamp(float(params["bias"]), -10.0, 10.0))
    if "maxdist" in params:
        _try_set(n, "maxdist", clamp(float(params["maxdist"]), 0.0, 1e6))
    if "conewidth" in params:
        _try_set(n, "conewidth", clamp(float(params["conewidth"]), 0.0, 360.0))
    if "colorout" in params:
        _try_set(n, "colorout", bool(params["colorout"]))
    if "occattr" in params:
        _try_set(n, "occattr", str(params["occattr"]))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _SMOOTH_METHOD)
    if "influencetype" in params:
        _menu_set(n, "influencetype", str(params["influencetype"]), _INFLUENCE)
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 500)))
    if "blur" in params:
        _try_set(n, "blur", clamp(float(params["blur"]), 0.0, 100.0))
    if "raybbias" in params:
        _try_set(n, "raybbias", clamp(float(params["raybbias"]), -10.0, 10.0))
    if "iterations2" in params:
        _try_set(n, "iterations2", int(clamp(int(params["iterations2"]), 0, 500)))
    return _result(n)


# ── 2. calculate_slope (in0 mesh) — writes Cd + slope attr ────────────────────────────────────────
@endpoint("calculate_slope")
def calculate_slope(params):
    """SideFX Labs Calculate Slope (labs::calculate_slope) — computes surface slope (angle of each
    point's normal from the up axis) into point attribute `sSlopeAttribute` (and a display `Cd` when
    `bSlopeCd` is on). `bMeshNormals` uses the mesh's own normals; otherwise recomputed. `method` /
    `influencetype` / `iterations` / `stepsize` control the post-smoothing. Data-only."""
    n = child_after(params["input"], "labs::calculate_slope", params.get("name"))
    if "bMeshNormals" in params:
        _try_set(n, "bMeshNormals", bool(params["bMeshNormals"]))
    if "bSlopeCd" in params:
        _try_set(n, "bSlopeCd", bool(params["bSlopeCd"]))
    if "sSlopeAttribute" in params:
        _try_set(n, "sSlopeAttribute", str(params["sSlopeAttribute"]))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _SMOOTH_METHOD)
    if "influencetype" in params:
        _menu_set(n, "influencetype", str(params["influencetype"]), _INFLUENCE)
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 500)))
    if "stepsize" in params:
        _try_set(n, "stepsize", clamp(float(params["stepsize"]), 0.0, 100.0))
    return _result(n)


# ── 3. calculate_thickness (in0 mesh) — writes thickness attr + Cd ────────────────────────────────
@endpoint("calculate_thickness")
def calculate_thickness(params):
    """SideFX Labs Calculate Thickness (labs::calculate_thickness::1.0) — measures local mesh
    thickness by casting `numrays` inward rays per point and writes the distance into point attribute
    `attrname` (default `thickness`; plus a display `Cd` when `outputcolor` is on). `normalized`
    remaps 0..1; `maxdist`/`mindist`/`coneangle` bound the ray search. Data-only."""
    n = child_after(params["input"], "labs::calculate_thickness::1.0", params.get("name"))
    if "numrays" in params:
        _try_set(n, "numrays", int(clamp(int(params["numrays"]), 1, 4096)))
    if "maxdist" in params:
        _try_set(n, "maxdist", clamp(float(params["maxdist"]), 0.0, 1e6))
    if "raymethod" in params:
        _try_set(n, "raymethod", int(clamp(int(params["raymethod"]), 0, 1)))
    if "mindist" in params:
        _try_set(n, "mindist", clamp(float(params["mindist"]), 0.0, 1e6))
    if "coneangle" in params:
        _try_set(n, "coneangle", clamp(float(params["coneangle"]), 0.0, 360.0))
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    if "outputcolor" in params:
        _try_set(n, "outputcolor", bool(params["outputcolor"]))
    if "normalized" in params:
        _try_set(n, "normalized", bool(params["normalized"]))
    if "attrname" in params:
        _try_set(n, "attrname", str(params["attrname"]))
    return _result(n)


# ── 4. distance_from_border (in0 mesh) — writes distance attr + Cd ────────────────────────────────
@endpoint("distance_from_border")
def distance_from_border(params):
    """SideFX Labs Distance From Border (labs::distance_from_border) — for each point computes the
    distance to the nearest open boundary/border edge and writes it into point attribute `distattr`
    (plus a display `Cd` when `bDistanceAsColor` is on). `outputtype` picks raw / normalized /
    unboundedraw; `distmetric` picks edge / global / surface distance; `reverse` flips it. Data-only."""
    n = child_after(params["input"], "labs::distance_from_border", params.get("name"))
    if "outputtype" in params:
        _menu_set(n, "outputtype", str(params["outputtype"]), _DIST_OUTTYPE)
    if "distmetric" in params:
        _menu_set(n, "distmetric", str(params["distmetric"]), _DIST_METRIC)
    if "rad" in params:
        _try_set(n, "rad", clamp(float(params["rad"]), 0.0, 1e6))
    if "reverse" in params:
        _try_set(n, "reverse", bool(params["reverse"]))
    if "bDistanceAsColor" in params:
        _try_set(n, "bDistanceAsColor", bool(params["bDistanceAsColor"]))
    if "distattr" in params:
        _try_set(n, "distattr", str(params["distattr"]))
    if "method" in params:
        _menu_set(n, "method", str(params["method"]), _SMOOTH_METHOD)
    if "influencetype" in params:
        _menu_set(n, "influencetype", str(params["influencetype"]), _INFLUENCE)
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), 0, 500)))
    if "stepsize" in params:
        _try_set(n, "stepsize", clamp(float(params["stepsize"]), 0.0, 100.0))
    return _result(n)


# ── 5. edge_color (in0 mesh) — writes Cd (convex/concave edge visualization) ──────────────────────
@endpoint("edge_color")
def edge_color(params):
    """SideFX Labs Edge Color (labs::edge_color) — writes a display `Cd` that highlights convex vs
    concave edges (a wear/curvature visualization used to drive edge-damage masks). `concave_*` and
    `convex_*` (range_scale / contrast / blur) tune each side; `blend_mode` (0..7) sets how the edge
    color composites. Data-only. (Note: node's own parm names carry the misspelling `ammount`.)"""
    n = child_after(params["input"], "labs::edge_color", params.get("name"))
    if "blend_mode" in params:
        _try_set(n, "blend_mode", int(clamp(int(params["blend_mode"]), 0, 7)))
    if "concave_range_scale" in params:
        _try_set(n, "concave_range_scale", clamp(float(params["concave_range_scale"]), 0.0, 100.0))
    if "concave_contrast" in params:
        _try_set(n, "concave_contrast", clamp(float(params["concave_contrast"]), 0.0, 100.0))
    if "concave_blur_ammount" in params:
        _try_set(n, "concave_blur_ammount", clamp(float(params["concave_blur_ammount"]), 0.0, 100.0))
    if "convex_range_scale" in params:
        _try_set(n, "convex_range_scale", clamp(float(params["convex_range_scale"]), 0.0, 100.0))
    if "convex_contrast" in params:
        _try_set(n, "convex_contrast", clamp(float(params["convex_contrast"]), 0.0, 100.0))
    if "convex_blur_ammount" in params:
        _try_set(n, "convex_blur_ammount", clamp(float(params["convex_blur_ammount"]), 0.0, 100.0))
    return _result(n)


# ── 6. fast_gaussian_curvature (in0 mesh) — writes curvature attr ─────────────────────────────────
@endpoint("fast_gaussian_curvature")
def fast_gaussian_curvature(params):
    """SideFX Labs Fast Gaussian Curvature (labs::fast_gaussian_curvature::1.0) — computes discrete
    Gaussian curvature (angle defect) and writes it into point attribute `attribname_curv` (default
    `curvature`) plus an angle into `attribname_angle`. `grouptype` scopes the analysis; `angleunit`
    (0/1) and `nmlmode` (0/1) select radians-vs-degrees and the normal source; `vis` colors it.
    Data-only. `group` is a geometry group NAME (not a path)."""
    n = child_after(params["input"], "labs::fast_gaussian_curvature::1.0", params.get("name"))
    if "group" in params:
        _try_set(n, "group", str(params["group"]))
    if "grouptype" in params:
        _menu_set(n, "grouptype", str(params["grouptype"]), _CURV_GROUPTYPE)
    if "ignoreunshared" in params:
        _try_set(n, "ignoreunshared", bool(params["ignoreunshared"]))
    if "outputval" in params:
        _try_set(n, "outputval", int(clamp(int(params["outputval"]), 0, 1)))
    if "outputattrib" in params:
        _try_set(n, "outputattrib", int(clamp(int(params["outputattrib"]), 0, 1)))
    if "angleunit" in params:
        _try_set(n, "angleunit", int(clamp(int(params["angleunit"]), 0, 1)))
    if "nmlmode" in params:
        _try_set(n, "nmlmode", int(clamp(int(params["nmlmode"]), 0, 1)))
    if "attribname_angle" in params:
        _try_set(n, "attribname_angle", str(params["attribname_angle"]))
    if "attribname_curv" in params:
        _try_set(n, "attribname_curv", str(params["attribname_curv"]))
    if "vis" in params:
        _try_set(n, "vis", bool(params["vis"]))
    return _result(n)


# ── 7. measure_curvature (in0 mesh) — writes convexity + concavity attrs + Cd ─────────────────────
@endpoint("measure_curvature")
def measure_curvature(params):
    """SideFX Labs Measure Curvature (labs::measure_curvature::3.1) — measures surface curvature and
    writes point attributes `convexityattr` (default `convexity`) and `concavityattr` (default
    `concavity`), plus a display `Cd` when `viscolor` is on. `method` (0..6) picks the estimator;
    `sampleresolution` sets the sampling; `convexitymult`/`concavitymult` + `*blur` shape each side;
    `perpiece` measures per `pieceattr` island. Data-only. (Supersedes the misspelled
    labs::measure_curvarture.)"""
    n = child_after(params["input"], "labs::measure_curvature::3.1", params.get("name"))
    if "method" in params:
        _try_set(n, "method", int(clamp(int(params["method"]), 0, 6)))
    if "sampleresolution" in params:
        _try_set(n, "sampleresolution", int(clamp(int(params["sampleresolution"]), 1, 4096)))
    if "perpiece" in params:
        _try_set(n, "perpiece", bool(params["perpiece"]))
    if "pieceattr" in params:
        _try_set(n, "pieceattr", str(params["pieceattr"]))
    if "convexityattr" in params:
        _try_set(n, "convexityattr", str(params["convexityattr"]))
    if "concavityattr" in params:
        _try_set(n, "concavityattr", str(params["concavityattr"]))
    if "convexitymult" in params:
        _try_set(n, "convexitymult", clamp(float(params["convexitymult"]), 0.0, 100.0))
    if "convexityblur" in params:
        _try_set(n, "convexityblur", clamp(float(params["convexityblur"]), 0.0, 100.0))
    if "concavitymult" in params:
        _try_set(n, "concavitymult", clamp(float(params["concavitymult"]), 0.0, 100.0))
    if "concavityblur" in params:
        _try_set(n, "concavityblur", clamp(float(params["concavityblur"]), 0.0, 100.0))
    if "viscolor" in params:
        _try_set(n, "viscolor", bool(params["viscolor"]))
    if "usegrayscale" in params:
        _try_set(n, "usegrayscale", bool(params["usegrayscale"]))
    return _result(n)


# ── 8. physical_ambient_occlusion (in0 mesh) — writes ao_mask attr + Cd ───────────────────────────
@endpoint("physical_ambient_occlusion")
def physical_ambient_occlusion(params):
    """SideFX Labs Physical Ambient Occlusion (labs::physical_ambient_occlusion::1.1) — a
    physically-based AO bake into point attribute `outputattrib` (default `ao_mask`; plus a display
    `Cd`). `samplecount`/`samplefreq` control quality (cost); `raylength` bounds the search; `exp`
    shapes falloff; `bluriters`/`stepsize` smooth; `normalize`/`invert`/`remap` post-process.
    `mode` (0..3) picks the sampling model. Data-only."""
    n = child_after(params["input"], "labs::physical_ambient_occlusion::1.1", params.get("name"))
    if "mode" in params:
        _try_set(n, "mode", int(clamp(int(params["mode"]), 0, 3)))
    if "samplefreq" in params:
        _try_set(n, "samplefreq", int(clamp(int(params["samplefreq"]), 1, 4096)))
    if "samplecount" in params:
        _try_set(n, "samplecount", int(clamp(int(params["samplecount"]), 1, 8192)))
    if "raylength" in params:
        _try_set(n, "raylength", clamp(float(params["raylength"]), 0.0, 1e6))
    if "exp" in params:
        _try_set(n, "exp", clamp(float(params["exp"]), 0.0, 100.0))
    if "randseed" in params:
        _try_set(n, "randseed", clamp(float(params["randseed"]), -1e9, 1e9))
    if "bluriters" in params:
        _try_set(n, "bluriters", int(clamp(int(params["bluriters"]), 0, 500)))
    if "stepsize" in params:
        _try_set(n, "stepsize", clamp(float(params["stepsize"]), 0.0, 100.0))
    if "outputattrib" in params:
        _try_set(n, "outputattrib", str(params["outputattrib"]))
    if "normalize" in params:
        _try_set(n, "normalize", bool(params["normalize"]))
    if "invert" in params:
        _try_set(n, "invert", bool(params["invert"]))
    if "remap" in params:
        _try_set(n, "remap", bool(params["remap"]))
    if "vis" in params:
        _try_set(n, "vis", bool(params["vis"]))
    if "coneaxis" in params:
        _try_set(n, "coneaxis", int(clamp(int(params["coneaxis"]), 0, 1)))
    if "halfconeangle" in params:
        _try_set(n, "halfconeangle", clamp(float(params["halfconeangle"]), 0.0, 180.0))
    if "rayoffset" in params:
        _try_set(n, "rayoffset", clamp(float(params["rayoffset"]), -10.0, 10.0))
    if "samplescale" in params:
        _try_set(n, "samplescale", clamp(float(params["samplescale"]), 0.0, 100.0))
    return _result(n)


# ── 9. spectral_feature_extract (in0 mesh w/ point vector attr) — writes extracted float/vec ──────
@endpoint("spectral_feature_extract")
def spectral_feature_extract(params):
    """SideFX Labs Spectral Feature Extract (labs::spectral_feature_extract::1.0) — spectral
    (diffusion/PDE) feature analysis: extracts multi-scale features from an input point attribute and
    writes point attributes `outattrib_f` (default `extracted_float`) / `outattrib_v` (default
    `extracted_vec`). REQUIRES a point VECTOR attribute: `projattrib` (projection direction, default
    `N`) and `inattrib` (attribute to analyze, default `N`) — feed a normalled mesh. `time_*` /
    `strength_*` / `filter_*` / `model_*` control the high/low frequency bands. Data-only."""
    n = child_after(params["input"], "labs::spectral_feature_extract::1.0", params.get("name"))
    # default the two required vector-attr references to N so the node cooks on a normalled mesh
    _try_set(n, "projattrib", str(params.get("projattrib", "N")))
    _try_set(n, "inattrib", str(params.get("inattrib", "N")))
    if "intype" in params:
        _try_set(n, "intype", int(clamp(int(params["intype"]), 0, 1)))
    if "vecmode" in params:
        _try_set(n, "vecmode", int(clamp(int(params["vecmode"]), 0, 1)))
    if "outattrib_f" in params:
        _try_set(n, "outattrib_f", str(params["outattrib_f"]))
    if "outattrib_v" in params:
        _try_set(n, "outattrib_v", str(params["outattrib_v"]))
    if "method" in params:
        _try_set(n, "method", int(clamp(int(params["method"]), 0, 1)))
    if "time_high" in params:
        _try_set(n, "time_high", clamp(float(params["time_high"]), 0.0, 1e6))
    if "time_low" in params:
        _try_set(n, "time_low", clamp(float(params["time_low"]), 0.0, 1e6))
    if "strength_high" in params:
        _try_set(n, "strength_high", clamp(float(params["strength_high"]), 0.0, 1e6))
    if "strength_low" in params:
        _try_set(n, "strength_low", clamp(float(params["strength_low"]), 0.0, 1e6))
    if "filter_high" in params:
        _try_set(n, "filter_high", int(clamp(int(params["filter_high"]), 0, 4096)))
    if "filter_low" in params:
        _try_set(n, "filter_low", int(clamp(int(params["filter_low"]), 0, 4096)))
    if "model_high" in params:
        _try_set(n, "model_high", int(clamp(int(params["model_high"]), 0, 2)))
    if "model_low" in params:
        _try_set(n, "model_low", int(clamp(int(params["model_low"]), 0, 2)))
    if "invert" in params:
        _try_set(n, "invert", bool(params["invert"]))
    if "recomputenorm" in params:
        _try_set(n, "recomputenorm", bool(params["recomputenorm"]))
    if "vis" in params:
        _try_set(n, "vis", bool(params["vis"]))
    return _result(n)


# ── 10. validate_geometry_type (in0 geo) — pass-through validator (message/warn/error) ────────────
@endpoint("validate_geometry_type")
def validate_geometry_type(params):
    """SideFX Labs Validate Geometry Type (labs::validate_geometry_type::1.0) — a pipeline GUARD:
    passes the input geometry through unchanged while asserting a rule about it, raising a
    message/warn/error if the rule fails. Supply `geotype` (Point|Poly|Volume|VDB|NURBCurve|
    BezierCurve|MetaBall), a `comparison` and `expectednum` on the primitive count, and a `severity`
    (message|warn|error) to install one rule; omit them for a pure pass-through. Data-only."""
    n = child_after(params["input"], "labs::validate_geometry_type::1.0", params.get("name"))
    has_rule = any(k in params for k in ("geotype", "comparison", "expectednum", "severity"))
    if has_rule:
        _try_set(n, "fd_geo", 1)  # one multiparm rule instance
        if "geotype" in params:
            _str_menu_set(n, "geotype1", str(params["geotype"]), _VGT_GEOTYPE)
        if "comparison" in params:
            _str_menu_set(n, "comparison1", str(params["comparison"]), _VGT_COMPARE)
        if "expectednum" in params:
            _try_set(n, "expectednum1", int(clamp(int(params["expectednum"]), 0, 1_000_000_000)))
        if "severity" in params:
            _menu_set(n, "severity1", str(params["severity"]), ("message", "warn", "error"))
    return _result(n)

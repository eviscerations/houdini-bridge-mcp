"""SideFX Labs — Geometry/Group + Group tools (data-only handlers). Params verified against a live
H21.0.671 headless probe. Each Labs group HDA is wrapped as a
typed chain handler exposing a curated scalar/enum/group-name subset; ramps, folder headers and
pure-visualize toggles stay at HDA default.

The batch (highest version of each base name — all Archetype-B chain nodes, 1 input / 1 output):
  fast_group_unshared::1.0   in0=mesh   -> group unshared (open-boundary) edges/points/prims/verts
  group_by_attribute::1.0    in0=geo    -> one group per discrete value of an attribute
  group_by_measure           in0=geo    -> group prims by an eccentricity measure
  group_curve_corners        in0=curve  -> group the inside/outside corner points of curves
  group_grow (labs::group_expand) in0=geo -> grow/shrink a group along connectivity by N iterations
  group_invert::1.0          in0=geo    -> invert named point/prim/vertex groups
  loops_from_selection::1.0  in0=mesh   -> edge/quad loops grown from a seed edge group
  random_selection::1.1      in0=geo    -> random subset group (ratio/count/probability/periodic)

SECURITY: data-only. No code/callback/file parms exist or are exposed on any of these nodes — none
carry a file surface. The string params these tools DO expose are GROUP NAMES / GROUP-SELECTION
PATTERNS (the whole point of a group tool) and ATTRIBUTE NAMES — never paths, never code. Every such
string is passed through `_safe_group`, which rejects the backtick (hscript command-substitution) and
newline injection vectors before it reaches the SOP's group parser.
"""

import hou
from houdini_executor.server import endpoint, clamp, child_after
from houdini_executor.handlers._parmutil import _try_set




def _idx_menu_set(node, parm, value, choices):
    """Ordered menu whose stored value is an INDEX (Labs group menus use numeric tokens '0','1',...).
    Map a friendly token to its position and set the index."""
    if value in choices:
        return _try_set(node, parm, choices.index(value))
    return False


def _safe_group(value):
    """Sanitize a group-name / group-selection / attribute-name string. These are DATA selectors
    evaluated by Houdini's group parser (not code, not a path), but reject the two injection vectors a
    group field could otherwise carry: the backtick (hscript command substitution) and any newline /
    carriage return. Everything the group syntax legitimately needs (@attr, <>=!, ranges, *, letters,
    digits, _, space, -, ,) passes through untouched."""
    s = str(value)
    if "`" in s or "\n" in s or "\r" in s:
        raise ValueError("group/attribute name must not contain a backtick or newline: %r" % s)
    return s


# ── ordered-menu friendly-token tuples (position == the stored numeric index) ─────────────────────
_UNSHARED_TYPE = ("primitives", "points", "edges", "vertices")     # fast_group_unshared grouptype 0..3
_ENTITY = ("primitives", "points")                                  # group_by_attribute entity 0/1
_MERGEOP = ("replace", "union", "intersect", "subtract")            # group_by_measure mergeop 0..3
_LOOP_MODE = ("edge_loops", "quad_loops")                           # loops_from_selection outputmode 0/1
_QUAD_TERM = ("terminate_at_nonquads", "terminate_before_nonquads")  # quadtermination 0/1
_SEL_CLASS = ("primitives", "points", "pieces")                     # random_selection class 0/1/2
_SEL_MODE = ("exact_preserve_order", "exact_randomize_order",
             "probability", "periodic_constant", "periodic_random")  # selectionmode 0..4
_SEL_SPEC = ("by_ratio", "by_count")                                # specification 0/1


# ── 1. fast_group_unshared (chain; in0 = mesh) ────────────────────────────────────────────────────
@endpoint("fast_group_unshared")
def fast_group_unshared(params):
    """SideFX Labs Fast Group Unshared (labs::fast_group_unshared::1.0) — groups the UNSHARED
    (open-boundary / border) elements of the input mesh (input 0): edges belonging to a single
    primitive, and the points/prims/vertices touching them. `grouptype` picks the element class;
    `outgroup` names the created group; `toattrib` writes an integer attribute instead of a group.
    Data-only (no file surface)."""
    n = child_after(params["input"], "labs::fast_group_unshared::1.0", params.get("name"))
    if "grouptype" in params:
        _idx_menu_set(n, "grouptype", str(params["grouptype"]), _UNSHARED_TYPE)
    if "outgroup" in params:
        _try_set(n, "outgroup", _safe_group(params["outgroup"]))
    if "toattrib" in params:
        _try_set(n, "toattrib", bool(params["toattrib"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. group_by_attribute (chain; in0 = geo) ──────────────────────────────────────────────────────
@endpoint("group_by_attribute")
def group_by_attribute(params):
    """SideFX Labs Group by Attribute (labs::group_by_attribute::1.0) — creates one group per distinct
    value of an attribute on the input (input 0). `entity` = primitives or points; `attribute_name` =
    the attribute to bin by (REQUIRED to create any group; float values are rounded to `precision`
    decimals); `group_prefix` prefixes every created group name. Data-only; the attribute/prefix
    strings are group-safe (no path/code)."""
    n = child_after(params["input"], "labs::group_by_attribute::1.0", params.get("name"))
    if "entity" in params:
        _idx_menu_set(n, "entity", str(params["entity"]), _ENTITY)
    if "attribute_name" in params:
        _try_set(n, "attribute_name", _safe_group(params["attribute_name"]))
    if "group_prefix" in params:
        _try_set(n, "group_prefix", _safe_group(params["group_prefix"]))
    if "precision" in params:
        _try_set(n, "precision", int(clamp(int(params["precision"]), 0, 12)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. group_by_measure (chain; in0 = geo) ────────────────────────────────────────────────────────
@endpoint("group_by_measure")
def group_by_measure(params):
    """SideFX Labs Group by Measure (labs::group_by_measure) — groups primitives by a geometric
    measure (eccentricity: how far a prim's shape departs from a circle/square). `groupname` names the
    output group; `mergeop` combines with an existing group (replace/union/intersect/subtract);
    `eccentricity` is the threshold; `invert` flips the comparison. Data-only."""
    n = child_after(params["input"], "labs::group_by_measure", params.get("name"))
    if "groupname" in params:
        _try_set(n, "groupname", _safe_group(params["groupname"]))
    if "mergeop" in params:
        _idx_menu_set(n, "mergeop", str(params["mergeop"]), _MERGEOP)
    if "eccentricity" in params:
        _try_set(n, "fSquaredness", clamp(float(params["eccentricity"]), 0.0, 1.0))
    if "invert" in params:
        _try_set(n, "bInvertEccentricity", bool(params["invert"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. group_curve_corners (chain; in0 = curve) ───────────────────────────────────────────────────
@endpoint("group_curve_corners")
def group_curve_corners(params):
    """SideFX Labs Group Curve Corners (labs::group_curve_corners) — labels the corner points of input
    curves (input 0) into an `inside` group (convex/left corners) and an `outside` group (concave/right
    corners). `enable_inside`/`enable_outside` toggle each group; `inside_group_name`/
    `outside_group_name` name them; `add_direction_normal` writes an N pointing away from the corner.
    Data-only."""
    n = child_after(params["input"], "labs::group_curve_corners", params.get("name"))
    if "enable_inside" in params:
        _try_set(n, "enable_inside", bool(params["enable_inside"]))
    if "inside_group_name" in params:
        _try_set(n, "inside_group_name", _safe_group(params["inside_group_name"]))
    if "enable_outside" in params:
        _try_set(n, "enable_outside", bool(params["enable_outside"]))
    if "outside_group_name" in params:
        _try_set(n, "outside_group_name", _safe_group(params["outside_group_name"]))
    if "add_direction_normal" in params:
        _try_set(n, "bDirectionNormal", bool(params["add_direction_normal"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. group_grow (labs::group_expand; chain; in0 = geo) — RENAMED (native group_expand exists) ────
@endpoint("group_grow")
def group_grow(params):
    """SideFX Labs Group Expand (labs::group_expand) — grows (or shrinks) an existing group across the
    input geometry's connectivity. `group` = the group to expand (REQUIRED to do anything); `iterations`
    = the number of connectivity steps (positive grows the group outward; negative shrinks it inward).
    Named `group_grow` because a native `group_expand` tool already exists. Data-only; `group` is a
    group-safe selector (no path/code). `iterations` is clamped to [-100, 100]."""
    n = child_after(params["input"], "labs::group_expand", params.get("name"))
    if "group" in params:
        _try_set(n, "group", _safe_group(params["group"]))
    if "iterations" in params:
        _try_set(n, "iterations", int(clamp(int(params["iterations"]), -100, 100)))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. group_invert (chain; in0 = geo) ────────────────────────────────────────────────────────────
@endpoint("group_invert")
def group_invert(params):
    """SideFX Labs Group Invert (labs::group_invert::1.0) — inverts named groups in place: each listed
    group is replaced by its complement (all elements NOT in it). `pointgroups`, `primgroups` and
    `vertexgroups` are space-separated lists / patterns of the groups to invert. Data-only; every list
    is a group-safe selector (no path/code)."""
    n = child_after(params["input"], "labs::group_invert::1.0", params.get("name"))
    if "pointgroups" in params:
        _try_set(n, "pointgroups", _safe_group(params["pointgroups"]))
    if "primgroups" in params:
        _try_set(n, "primgroups", _safe_group(params["primgroups"]))
    if "vertexgroups" in params:
        _try_set(n, "vertexgroups", _safe_group(params["vertexgroups"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. loops_from_selection (chain; in0 = mesh) ───────────────────────────────────────────────────
@endpoint("loops_from_selection")
def loops_from_selection(params):
    """SideFX Labs Loops from Selection (labs::loops_from_selection::1.0) — grows full edge loops (or
    quad loops) out from a seed edge group. `startedgegroup` = the seed edge group; `outputmode` =
    edge_loops or quad_loops; `quadtermination` decides how a quad loop ends at non-quad prims;
    `maxsteps` caps loop length; `pattern`/`selectlen`/`skiplen`/`patternoffset` apply a periodic
    select-N-skip-M pattern along each loop; `outputedgegroup`/`outputprimgroup` name the results;
    `groupperloop` also emits one group per individual loop. Data-only."""
    n = child_after(params["input"], "labs::loops_from_selection::1.0", params.get("name"))
    if "outputmode" in params:
        _idx_menu_set(n, "outputmode", str(params["outputmode"]), _LOOP_MODE)
    if "quadtermination" in params:
        _idx_menu_set(n, "quadtermination", str(params["quadtermination"]), _QUAD_TERM)
    if "startedgegroup" in params:
        _try_set(n, "startedgegroup", _safe_group(params["startedgegroup"]))
    if "maxsteps" in params:
        _try_set(n, "maxsteps", int(clamp(int(params["maxsteps"]), 1, 1000000)))
    if "pattern" in params:
        _try_set(n, "pattern", bool(params["pattern"]))
    if "patternoffset" in params:
        _try_set(n, "patternoffset", int(clamp(int(params["patternoffset"]), 0, 1000000)))
    if "selectlen" in params:
        _try_set(n, "selectlen", int(clamp(int(params["selectlen"]), 1, 100000)))
    if "skiplen" in params:
        _try_set(n, "skiplen", int(clamp(int(params["skiplen"]), 1, 100000)))
    if "outputedgegroup" in params:
        _try_set(n, "outputedgegroup", _safe_group(params["outputedgegroup"]))
    if "outputprimgroup" in params:
        _try_set(n, "outputprimgroup", _safe_group(params["outputprimgroup"]))
    if "groupperloop" in params:
        _try_set(n, "groupperloop", bool(params["groupperloop"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 8. random_selection (chain; in0 = geo) ────────────────────────────────────────────────────────
@endpoint("random_selection")
def random_selection(params):
    """SideFX Labs Random Selection (labs::random_selection::1.1) — selects a random subset of the
    input's elements and turns it into a group. `class` = primitives / points / pieces (`pieceattrib`
    names the piece attribute when class=pieces); `basegroup` restricts the pool. `selectionmode`
    (exact number preserve/randomize order, probability, periodic constant/random) + `specification`
    (by_ratio | by_count) drive the count via `ratio`/`count`/`probability`/`offset` and the periodic
    `selectlen`/`skiplen`(`_min`/`_max`); `randseed` reseeds. `creategroup`+`groupname` emit the group;
    `intattribfromselected`+`attribname` emit an int attribute; `deleteselected`/`deletenonselected`
    keep only one side. Data-only; the color RAMP and color params stay at HDA default."""
    n = child_after(params["input"], "labs::random_selection::1.1", params.get("name"))
    if "basegroup" in params:
        _try_set(n, "basegroup", _safe_group(params["basegroup"]))
    if "class" in params:
        _idx_menu_set(n, "class", str(params["class"]), _SEL_CLASS)
    if "pieceattrib" in params:
        _try_set(n, "pieceattrib", _safe_group(params["pieceattrib"]))
    if "selectionmode" in params:
        _idx_menu_set(n, "selectionmode", str(params["selectionmode"]), _SEL_MODE)
    if "specification" in params:
        _idx_menu_set(n, "specification", str(params["specification"]), _SEL_SPEC)
    if "ratio" in params:
        _try_set(n, "ratio", clamp(float(params["ratio"]), 0.0, 1.0))
    if "count" in params:
        _try_set(n, "count", int(clamp(int(params["count"]), 0, 10000000)))
    if "probability" in params:
        _try_set(n, "probability", clamp(float(params["probability"]), 0.0, 1.0))
    if "offset" in params:
        _try_set(n, "offset", int(clamp(int(params["offset"]), 0, 10000000)))
    if "selectlen" in params:
        _try_set(n, "selectlen", int(clamp(int(params["selectlen"]), 1, 100000)))
    if "skiplen" in params:
        _try_set(n, "skiplen", int(clamp(int(params["skiplen"]), 1, 100000)))
    if "selectlenmin" in params:
        _try_set(n, "selectlenmin", int(clamp(int(params["selectlenmin"]), 1, 100000)))
    if "selectlenmax" in params:
        _try_set(n, "selectlenmax", int(clamp(int(params["selectlenmax"]), 1, 100000)))
    if "skiplenmin" in params:
        _try_set(n, "skiplenmin", int(clamp(int(params["skiplenmin"]), 1, 100000)))
    if "skiplenmax" in params:
        _try_set(n, "skiplenmax", int(clamp(int(params["skiplenmax"]), 1, 100000)))
    if "randseed" in params:
        _try_set(n, "randseed", int(params["randseed"]))
    if "deletenonselected" in params:
        _try_set(n, "deletenonselected", bool(params["deletenonselected"]))
    if "deleteselected" in params:
        _try_set(n, "deleteselected", bool(params["deleteselected"]))
    if "creategroup" in params:
        _try_set(n, "creategroup", bool(params["creategroup"]))
    if "groupname" in params:
        _try_set(n, "groupname", _safe_group(params["groupname"]))
    if "intattribfromselected" in params:
        _try_set(n, "intattribfromselected", bool(params["intattribfromselected"]))
    if "attribname" in params:
        _try_set(n, "attribname", _safe_group(params["attribname"]))
    if "colorselected" in params:
        _try_set(n, "colorselected", bool(params["colorselected"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}

"""SideFX Labs / Integration (DCC-interop) SOP handlers — data-only. Params verified against live
H21.0.671.

This lane is the interchange / convert-for-other-software slice of SideFX Labs. Most of the raw
`Labs/Integration` set are wrappers that SHELL OUT to an external application (AliceVision, RizomUV,
Exoside QuadRemesher, Gaea) or PUBLISH over the network (Sketchfab) — those are NOT data-only and are
SKIPPED. What remains here is the safe subset:
  * instant_meshes      — field-aligned quad REMESH (compiled Labs core; no external exe). chain.
  * osm_filter          — filter imported OpenStreetMap geometry by tag (buildings/roads/…). chain.
  * osm_buildings       — extrude building masses from OSM footprints. chain.
  * substance_material  — assign a Substance material; `.sbsar` archive read is confined. chain.
  * goz_export          — WIRE-ONLY GoZ/ZBrush exporter (confined path; never fired). writer.

SECURITY (data-only boundary):
  * substance_material's `file` (.sbsar) is realpath-confined; its `cop_input` is a COP NODE reference
    (not a file) left unset; `group1` is sanitized to a plain group token.
  * goz_export is WIRE-ONLY (mirrors tree.py maps_baker / labs_worldbuild_scatter terrain_texture):
    the graph is BUILT + wired and its output path is confined, but `send_to_zbrush` (launches ZBrush)
    is NEVER pressed, the `__name_expression` code parm is left at default, and it is not cooked —
    returns exported=False.
  * No node here exposes a code/callback/executable-path parm to the caller. instant_meshes' polycount
    lever `v_count` is hard-clamped.
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set


# ── probe-safe local helpers (copied per handler file, per the lane convention) ──────────────────


def _try_set_tuple(node, parm, values):
    """Set a tuple parm (vec2/vec3) only if it exists on this node."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(values))
        return True
    except Exception:
        return False


def _safe_token(v):
    """Sanitize a group / attribute token: reject path separators, parent refs and drive letters so a
    group name can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


# ── 1. instant_meshes (chain; in0 mesh, in1 optional guide) — field-aligned quad remesh ──────────
@endpoint("instant_meshes")
def instant_meshes(params):
    """SideFX Labs Instant Meshes (labs::instant_meshes::2.0) — field-aligned quad/tri REMESH of the
    incoming mesh (`input`, input 0) via the compiled Instant Meshes core (no external executable is
    launched — it is a data-only cook). Optional `guide` (input 1) supplies an orientation/feature
    stream. `v_count` is the target vertex budget and is hard-clamped. Data-only (no file/code
    surface)."""
    n = child_after(params["input"], "labs::instant_meshes::2.0", params.get("name"))
    if params.get("guide"):
        bridge_input(n, params["guide"], index=1, name_hint="guide")
    if "v_count" in params:
        _try_set(n, "v_count", int(clamp(int(params["v_count"]), 4, 2_000_000)))  # polycount lever
    if "cr_angle" in params:
        _try_set(n, "cr_angle", clamp(float(params["cr_angle"]), 0.0, 180.0))
    if "num_smooth_iter" in params:
        _try_set(n, "num_smooth_iter", int(clamp(int(params["num_smooth_iter"]), 0, 100)))
    if "traceLines" in params:
        _try_set(n, "traceLines", bool(params["traceLines"]))
    if "deterministic" in params:
        _try_set(n, "deterministic_parm", bool(params["deterministic"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 2. osm_filter (chain; in0 OSM geometry) — filter imported OpenStreetMap by tag ────────────────
@endpoint("osm_filter")
def osm_filter(params):
    """SideFX Labs OSM Filter (labs::osm_filter) — keeps only the wanted feature classes from imported
    OpenStreetMap geometry (`input`, input 0 = an osm_import output). Toggle the building / road /
    footway / other classes to pass; everything else is culled. Feeds osm_buildings downstream.
    Data-only (pure tag filter — no file/code surface)."""
    n = child_after(params["input"], "labs::osm_filter", params.get("name"))
    for key in ("buildings", "building_parts", "roads", "motorway_roads", "primary_roads",
                "secondary_roads", "tertiary_roads", "residential_roads", "footway_roads",
                "pedestrian_roads", "other_roads", "other_data"):
        if key in params:
            _try_set(n, key, bool(params[key]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 3. osm_buildings (chain; in0 OSM footprints) — extrude building masses ────────────────────────
@endpoint("osm_buildings")
def osm_buildings(params):
    """SideFX Labs OSM Buildings (labs::osm_buildings) — extrudes 3D building masses from the closed
    OpenStreetMap footprint polygons on `input` (input 0; an osm_import / osm_filter output carrying
    the `building` prim attribute). `level_height` sets the per-storey height; `shrink_factor` insets
    the footprint; `seed` varies the randomized storey counts. NOTE: footprints must be at real-world
    (metre) scale — sub-metre synthetic footprints are area-culled to nothing. Data-only (no file/code
    surface)."""
    n = child_after(params["input"], "labs::osm_buildings", params.get("name"))
    if "level_height" in params:
        _try_set(n, "level_height", clamp(float(params["level_height"]), 0.1, 1000.0))
    if "shrink_factor" in params:
        _try_set(n, "shrink_factor", clamp(float(params["shrink_factor"]), -100.0, 100.0))
    if "seed" in params:
        _try_set(n, "seed", clamp(float(params["seed"]), -1e9, 1e9))
    if "boolean_buildings" in params:
        _try_set(n, "boolean_buildings", bool(params["boolean_buildings"]))
    if "gen_nodata" in params:
        _try_set(n, "gen_nodata", bool(params["gen_nodata"]))
    if "visualize_buildings" in params:
        _try_set(n, "visualize_buildings", bool(params["visualize_buildings"]))
    if "height_min" in params or "height_max" in params:
        cur = n.parmTuple("height_rangemin").eval() if n.parmTuple("height_rangemin") else (10.0, 30.0)
        hmin = clamp(float(params.get("height_min", cur[0])), 0.0, 1e5)
        hmax = clamp(float(params.get("height_max", cur[1])), 0.0, 1e5)
        _try_set_tuple(n, "height_rangemin", (hmin, hmax))
        _try_set_tuple(n, "height_rangemax", (hmin, hmax))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. substance_material (chain; in0 mesh) — assign a Substance material (confined .sbsar read) ──
@endpoint("substance_material")
def substance_material(params):
    """SideFX Labs Substance Material (labs::substance_material) — assigns a Substance material to the
    incoming geometry (`input`, input 0). `file` is a Substance `.sbsar` archive, realpath-CONFINED to
    the working directory (a confined READ, like any importer); when omitted the node still passes the
    geometry through with the material rig attached. `tex_size` sets the output map resolution for both
    map sets. Data-only: `cop_input` is a COP NODE reference (not a file) left unset; `group` is a
    sanitized primitive-group token."""
    n = child_after(params["input"], "labs::substance_material", params.get("name"))
    if params.get("file"):
        _try_set(n, "file", confined_path(params["file"]))  # SECURITY: confined .sbsar read
    if "tex_size" in params:
        sz = int(clamp(int(params["tex_size"]), 16, 8192))
        _try_set_tuple(n, "size1", (sz, sz))
        _try_set_tuple(n, "size2", (sz, sz))
    if "group" in params:
        _try_set(n, "group1", _safe_token(params["group"]))
    if "baseNormal_flipY" in params:
        _try_set(n, "baseNormal_flipY", bool(params["baseNormal_flipY"]))
    if "dispTex_enable" in params:
        _try_set(n, "dispTex_enable", bool(params["dispTex_enable"]))
    if "dispTex_scale" in params:
        _try_set(n, "dispTex_scale", clamp(float(params["dispTex_scale"]), -100.0, 100.0))
    if "dispTex_offset" in params:
        _try_set(n, "dispTex_offset", clamp(float(params["dispTex_offset"]), -100.0, 100.0))
    if "gamma_diffuse" in params:
        _try_set(n, "gamma_diffuse", bool(params["gamma_diffuse"]))
    if "gamma_roughness" in params:
        _try_set(n, "gamma_roughness", bool(params["gamma_roughness"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 5. goz_export (writer; in0 mesh) — WIRE-ONLY GoZ/ZBrush export ────────────────────────────────
@endpoint("goz_export")
def goz_export(params):
    """SideFX Labs GoZ Export (labs::goz_export) — WIRE-ONLY exporter that hands geometry to ZBrush via
    the GoZ bridge. `input` (input 0) = the mesh to export; `export_file` = the confined GoZ output
    path. Mirrors tree.py maps_baker: the node is BUILT + wired + its path confined, but the export is
    NEVER fired — `send_to_zbrush` (which launches ZBrush) is not pressed and the node is not cooked,
    so the human triggers the hand-off. Returns exported=False.
    SECURITY: `export_file` is realpath-confined; the `__name_expression` code parm and the
    `send_to_zbrush` launch button are never touched."""
    n = child_after(params["input"], "labs::goz_export", params.get("name"))
    out_path = None
    if params.get("export_file"):
        out_path = confined_path(params["export_file"])  # SECURITY: confined write path
        _try_set(n, "__export_file", out_path)
    # WIRE-ONLY: never press send_to_zbrush, never touch __name_expression, do not cook.
    return {"node": n.path(), "output": out_path, "exported": False,
            "note": "goz_export graph wired (WIRE-ONLY); send to ZBrush yourself"}

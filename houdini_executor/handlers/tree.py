"""SideFX Labs Tree Tools — data-only handlers. Params verified against live H21.0.671
(reference/houdini_nodes.json). Wraps each Labs tree HDA as a typed handler exposing a curated
scalar subset; ramps stay at HDA default; file-surface params are confined / forced off.

The modular chain (all four masterclass build videos):
  tree_trunk_generator (root; out0=mesh, out1=curve) -> tree_controller (shared settings) ->
  tree_branch_generator xN levels -> tree_leaf_generator (leaf template from tree_simple_leaf).
Plus quick_basic_tree (one-call convenience) and maps_baker (WIRE-ONLY LOD-atlas bake).

SECURITY: trunk/controller/branch force `enable_disp` OFF and never expose `disp_texture`
(image READ). maps_baker is the only node with a file surface — its output is confined_path()'d,
its .fbx side-exports and material-mapping read are forced off, its render-cost levers are hard
clamped, and it is WIRE-ONLY (never cooked/rendered; returns rendered=False).
"""

import hou
from houdini_executor.server import endpoint, confined_path, clamp, child_after, bridge_input
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


def _fresh_geo(name):
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError(f"object already exists: {name} (use a different name)")
    return obj.createNode("geo", name)






def _wire_parent_curve(n):
    """The Labs tree nodes carry a spine CURVE on OUTPUT 1. child_after wires the parent MESH
    (output 0) -> input 0; the branch/leaf generators ALSO need that same parent's curve, so wire
    the parent's OUTPUT 1 -> this node's input 1. No-op if the parent lacks a second output."""
    p0 = n.input(0)
    if p0 is not None and len(p0.outputConnectors()) > 1:
        try:
            n.setInput(1, p0, 1)
        except hou.OperationFailed:
            pass


# ── ordered-menu token tuples (position == the spec's stored index) ──────────────────────────────
_TRUNK_ENDCAP = ("none", "single", "grid")            # endcaptype: idx 0=none..2=grid (def 2)
_SEAM_OPTIONS = ("none", "boolean")                   # seam_options: idx 0=none / 1=boolean-blend
_BRANCH_MODE = ("scatter", "byedgelength")            # mode: idx 0=Scatter / 1=ByEdgeLength
_PHY_ANGLE_3 = ("90", "137", "180")                   # branch lat_phy_angle: idx 90/137/180
_PHY_ANGLE_2 = ("90", "180")                          # leaf lat_phy_angle: idx 90/180
_BAKE_FRAMEMODE = ("current", "range")                # maps_baker framemode: idx 0=current / 1=range


def _safe_map_token(v):
    """Sanitize a maps_baker map-name / channel token (e.g. `$(CHANNEL)`): reject path separators,
    parent refs and drive letters so a map name can never smuggle a filesystem path."""
    s = str(v)
    if "/" in s or "\\" in s or ".." in s or ":" in s:
        raise ValueError("map-name token must not contain a path (no / \\ .. or drive): %r" % s)
    return s


# ── 1. tree_trunk_generator (generator; in0 base geo/pts opt, in1 curve opt) ──────────────────────
@endpoint("tree_trunk_generator")
def tree_trunk_generator(params):
    """Labs Tree Trunk Generator (labs::tree_trunk_generator::1.1) — the ROOT of the modular tree
    chain: builds a fresh /obj geo carrying a trunk mesh (output 0) + a spine curve (output 1) that
    the branch/leaf generators grow from. Optional `base` (input 0) seeds the root position; optional
    `curve` (input 1) supplies a hand-drawn trunk backbone. Fails on name collision.
    SECURITY: displacement (`enable_disp`) is forced OFF and the displacement image (`disp_texture`)
    is never exposed — this handler carries no file surface."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::tree_trunk_generator::1.1")
    if params.get("base"):
        bridge_input(n, params["base"], index=0, name_hint="base")
    if params.get("curve"):
        bridge_input(n, params["curve"], index=1, name_hint="curve")
    _try_set(n, "enable_disp", False)  # SECURITY: never displace from a disk image
    if "trunk_length" in params:
        _try_set(n, "trunk_length", clamp(float(params["trunk_length"]), 0.1, 500.0))
    if "cull_length_rand_toggle" in params:
        _try_set(n, "cull_length_rand_toggle", bool(params["cull_length_rand_toggle"]))
    if "length_main_rand_min" in params:
        _try_set(n, "length_main_rand_min", clamp(float(params["length_main_rand_min"]), -1e6, 1e6))
    if "length_main_rand_max" in params:
        _try_set(n, "length_main_rand_max", clamp(float(params["length_main_rand_max"]), -1e6, 1e6))
    if "rad" in params:
        _try_set(n, "rad", clamp(float(params["rad"]), 1e-3, 50.0))
    if "enablebend" in params:
        _try_set(n, "enablebend", bool(params["enablebend"]))
    if "bend" in params:
        _try_set(n, "bend", clamp(float(params["bend"]), -360.0, 360.0))
    if "upangle" in params:
        _try_set(n, "upangle", clamp(float(params["upangle"]), -360.0, 360.0))
    if "bend_start" in params:
        _try_set(n, "bend_start", clamp(float(params["bend_start"]), 0.0, 1.0))
    if "capture_length" in params:
        _try_set(n, "capture_length", clamp(float(params["capture_length"]), 0.0, 1.0))
    if "roots_toggle" in params:
        _try_set(n, "roots_toggle", bool(params["roots_toggle"]))
    if "root_offset" in params:
        _try_set(n, "root_offset", clamp(float(params["root_offset"]), 0.0, 5.0))
    if "roll" in params:
        _try_set(n, "roll", clamp(float(params["roll"]), -720.0, 720.0))
    if "incroll" in params:
        _try_set(n, "incroll", clamp(float(params["incroll"]), -720.0, 720.0))
    if "enable_line_noise" in params:
        _try_set(n, "enable_line_noise", bool(params["enable_line_noise"]))
    if "line_noise_amount" in params:
        _try_set(n, "line_noise_amount", clamp(float(params["line_noise_amount"]), 0.0, 5.0))
    if "line_noise_size" in params:
        _try_set(n, "line_noise_size", clamp(float(params["line_noise_size"]), 1e-3, 50.0))
    if "enable_mesh_noise" in params:
        _try_set(n, "enable_mesh_noise", bool(params["enable_mesh_noise"]))
    if "mesh_noise_amount" in params:
        _try_set(n, "mesh_noise_amount", clamp(float(params["mesh_noise_amount"]), 0.0, 2.0))
    if "endcaptype" in params:
        _menu_set(n, "endcaptype", str(params["endcaptype"]), _TRUNK_ENDCAP)
    if "res" in params:
        _try_set(n, "res_override", True)  # `res` only takes effect with the override on
        _try_set(n, "res", clamp(float(params["res"]), 1e-3, 5.0))
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


# ── 2. tree_controller (SOURCE; 0 inputs, 1 output; feed into trunk `base`) ───────────────────────
@endpoint("tree_controller")
def tree_controller(params):
    """Labs Tree Controller (labs::tree_controller::1.1) — a SOURCE node (0 inputs, 1 output) holding
    the tree-wide settings (gravity / bend / light tropism, seam booleaning, LOD). Build it FIRST,
    then feed its output into tree_trunk_generator's `base` (input 0); the trunk and downstream
    branch/leaf generators inherit these settings unless they override. The core workflow lever is
    `seam_options`: keep it `none` while building the tree (fast), switch to `boolean` at the end to
    weld the branch seams. Fails on name collision.
    SECURITY: `enable_disp` forced OFF; the displacement image is never exposed."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::tree_controller::1.1")
    _try_set(n, "enable_disp", False)  # SECURITY
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    if "enable_grav" in params:
        _try_set(n, "enable_grav", bool(params["enable_grav"]))
    if "grav_strength" in params:
        _try_set(n, "grav_strength", clamp(float(params["grav_strength"]), -5.0, 5.0))
    if "grav_dir" in params:
        _try_set(n, "grav_dir", clamp(float(params["grav_dir"]), -360.0, 360.0))
    if "enable_bend" in params:
        _try_set(n, "enable_bend", bool(params["enable_bend"]))
    if "bend_strength" in params:
        _try_set(n, "bend_strength", clamp(float(params["bend_strength"]), -10.0, 10.0))
    if "enable_light" in params:
        _try_set(n, "enable_light", bool(params["enable_light"]))
    if "light_strength" in params:
        _try_set(n, "light_strength", clamp(float(params["light_strength"]), -5.0, 5.0))
    if "seam_options" in params:
        _menu_set(n, "seam_options", str(params["seam_options"]), _SEAM_OPTIONS)
    if "bool_smooth" in params:
        _try_set(n, "bool_smooth", clamp(float(params["bool_smooth"]), 0.0, 5.0))
    if "blend_falloff" in params:
        _try_set(n, "blend_falloff", clamp(float(params["blend_falloff"]), 0.0, 1.0))
    if "uv_blend" in params:
        _try_set(n, "uv_blend", bool(params["uv_blend"]))
    if "up_angle" in params:
        _try_set(n, "up_angle", clamp(float(params["up_angle"]), 0.0, 180.0))
    if "down_angle" in params:
        _try_set(n, "down_angle", clamp(float(params["down_angle"]), 0.0, 180.0))
    if "line_noise_amount" in params:
        _try_set(n, "line_noise_amount", clamp(float(params["line_noise_amount"]), 0.0, 5.0))
    if "mesh_noise_amount" in params:
        _try_set(n, "mesh_noise_amount", clamp(float(params["mesh_noise_amount"]), 0.0, 2.0))
    if "res" in params:
        _try_set(n, "res", clamp(float(params["res"]), 1e-3, 5.0))
    if "lod_start" in params:
        _try_set(n, "lod_start", int(clamp(int(params["lod_start"]), 0, 8)))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


# ── 3. tree_branch_generator (chain; in0 parent mesh, in1 parent curve) — the workhorse ───────────
@endpoint("tree_branch_generator")
def tree_branch_generator(params):
    """Labs Tree Branch Generator (labs::tree_branch_generator::1.2) — THE workhorse: grows one level
    of lateral branches off a parent. `input` (input 0) = the parent mesh; `curve` (input 1) = the
    parent spine curve. Chain one per branch level; `del_prev` resets the level tree. `mode` picks
    scatter (num_lat placements) or byedgelength (spacing).
    SECURITY: `enable_disp` forced OFF; the displacement image is never exposed. Node-path /
    string inputs (growth_obj, objpath1, branch_group, manual_prune, branch_profile) are left unset."""
    n = child_after(params["input"], "labs::tree_branch_generator::1.2", params.get("name"))
    _wire_parent_curve(n)  # carry the parent's spine CURVE (output 1) into input 1
    _try_set(n, "enable_disp", False)  # SECURITY
    if "del_prev" in params:
        _try_set(n, "del_prev", bool(params["del_prev"]))
    if "mode" in params:
        _menu_set(n, "mode", str(params["mode"]), _BRANCH_MODE)
    if "num_lat" in params:
        _try_set(n, "num_lat", int(clamp(int(params["num_lat"]), 0, 200)))
    if "lat_branch_start" in params:
        _try_set(n, "lat_branch_start", clamp(float(params["lat_branch_start"]), 0.0, 1.0))
    if "lat_phy_angle" in params:
        _menu_set(n, "lat_phy_angle", str(params["lat_phy_angle"]), _PHY_ANGLE_3)
    if "phy_var" in params:
        _try_set(n, "phy_var", clamp(float(params["phy_var"]), 0.0, 180.0))
    if "lat_angle" in params:
        _try_set(n, "lat_angle", clamp(float(params["lat_angle"]), 0.0, 180.0))
    if "lat_angle_var" in params:
        _try_set(n, "lat_angle_var", clamp(float(params["lat_angle_var"]), 0.0, 180.0))
    if "angle_ramp_toggle" in params:
        _try_set(n, "angle_ramp_toggle", bool(params["angle_ramp_toggle"]))
    if "lat_length" in params:
        _try_set(n, "lat_length", clamp(float(params["lat_length"]), 0.0, 10.0))
    if "lat_length_rand" in params:
        _try_set(n, "lat_length_rand", clamp(float(params["lat_length_rand"]), 0.0, 5.0))
    if "radius" in params:
        _try_set(n, "radius_override", True)  # `radius` takes effect with the override on
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-3, 10.0))
    if "radius_override" in params:
        _try_set(n, "radius_override", bool(params["radius_override"]))
    if "radius_adjust" in params:
        _try_set(n, "radius_adjust", clamp(float(params["radius_adjust"]), -5.0, 5.0))
    if "length_scale" in params:
        _try_set(n, "length_scale", clamp(float(params["length_scale"]), -1e6, 1e6))
    if "tropism_override" in params:
        _try_set(n, "tropism_override", bool(params["tropism_override"]))
    if "enable_grav" in params:
        _try_set(n, "enable_grav", bool(params["enable_grav"]))
    if "grav_strength" in params:
        _try_set(n, "grav_strength", clamp(float(params["grav_strength"]), -5.0, 5.0))
    if "enable_bend" in params:
        _try_set(n, "enable_bend", bool(params["enable_bend"]))
    if "bend_strength" in params:
        _try_set(n, "bend_strength", clamp(float(params["bend_strength"]), -10.0, 10.0))
    if "mesh_noise_override" in params:
        _try_set(n, "mesh_noise_override", bool(params["mesh_noise_override"]))
    if "mesh_noise_amount" in params:
        _try_set(n, "mesh_noise_amount", clamp(float(params["mesh_noise_amount"]), 0.0, 2.0))
    if "meshing_override" in params:
        _try_set(n, "meshing_override", bool(params["meshing_override"]))
    if "seam_options" in params:
        _menu_set(n, "seam_options", str(params["seam_options"]), _SEAM_OPTIONS)
    if "prune_override" in params:
        _try_set(n, "prune_override", bool(params["prune_override"]))
    if "up_angle" in params:
        _try_set(n, "up_angle", clamp(float(params["up_angle"]), 0.0, 180.0))
    if "down_angle" in params:
        _try_set(n, "down_angle", clamp(float(params["down_angle"]), 0.0, 180.0))
    if "detangle_toggle" in params:
        _try_set(n, "detangle_toggle", bool(params["detangle_toggle"]))
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 4. tree_simple_leaf (generator; inputs 0) — leaf template for leaf_generator in2 ──────────────
@endpoint("tree_simple_leaf")
def tree_simple_leaf(params):
    """Labs Tree Simple Leaf (labs::tree_simple_leaf::1.0) — builds a fresh /obj geo holding ONE leaf
    (or needle) template card; wire its output into tree_leaf_generator's `leaf` input to scatter it
    over the tree. `bend`=0 gives a flat needle. Fails on name collision. SECURITY: none (no file
    surface)."""
    geo = _fresh_geo(params["name"])
    n = geo.createNode("labs::tree_simple_leaf::1.0")
    if "leaf_size" in params:
        _try_set(n, "leaf_size", clamp(float(params["leaf_size"]), 1e-3, 10.0))
    if "dist" in params:
        _try_set(n, "dist", clamp(float(params["dist"]), 1e-3, 10.0))
    if "width" in params:
        _try_set(n, "width", clamp(float(params["width"]), 1e-3, 10.0))
    if "points" in params:
        _try_set(n, "points", int(clamp(int(params["points"]), 1, 64)))
    if "cols" in params:
        _try_set(n, "cols", int(clamp(int(params["cols"]), 1, 32)))
    if "shape_method" in params:
        # ordered menu; spec probed only the param name (not the token labels), so take a raw index.
        _try_set(n, "shape_method", int(clamp(int(params["shape_method"]), 0, 8)))
    if "folding_amount" in params:
        _try_set(n, "folding_amount", clamp(float(params["folding_amount"]), 0.0, 1.0))
    if "bend" in params:
        _try_set(n, "bend", clamp(float(params["bend"]), -180.0, 180.0))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 0.0, 1.0))
    if "seed" in params:
        _try_set(n, "seed", clamp(float(params["seed"]), -1e9, 1e9))
    if "mix" in params:
        _try_set(n, "mix", clamp(float(params["mix"]), 0.0, 1.0))
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    geo.layoutChildren()
    g = n.geometry()
    return {"node": geo.path(), "sop": n.path(),
            "points": len(g.points()), "prims": len(g.prims())}


# ── 5. tree_leaf_generator (chain; in0 branch mesh, in1 branch curve, in2 leaf source) — terminus ─
@endpoint("tree_leaf_generator")
def tree_leaf_generator(params):
    """Labs Tree Leaf Generator (labs::tree_leaf_generator::1.0) — the chain terminus: scatters the
    leaf template over the branches. `input` (input 0) = the branch mesh; `curve` (input 1) = the
    branch spine; `leaf` (input 2) = a tree_simple_leaf output. `enable_grav` droops the leaves
    (willow). SECURITY: `light_source` is a node path (not a file); nothing to force off."""
    n = child_after(params["input"], "labs::tree_leaf_generator::1.0", params.get("name"))
    _wire_parent_curve(n)  # carry the parent branch's spine CURVE (output 1) into input 1
    if params.get("leaf"):
        bridge_input(n, params["leaf"], index=2, name_hint="leaf")
    if "pack" in params:
        _try_set(n, "pack", bool(params["pack"]))
    if "num_lat" in params:
        _try_set(n, "num_lat", clamp(float(params["num_lat"]), 1e-3, 1.0))
    if "branches_per_node" in params:
        _try_set(n, "branches_per_node", int(clamp(int(params["branches_per_node"]), 1, 50)))
    if "lat_length" in params:
        _try_set(n, "lat_length", clamp(float(params["lat_length"]), 0.0, 10.0))
    if "lat_length_rand" in params:
        _try_set(n, "lat_length_rand", clamp(float(params["lat_length_rand"]), 0.0, 5.0))
    if "size" in params:
        _try_set(n, "size", clamp(float(params["size"]), 1e-3, 10.0))
    if "lat_phy_angle" in params:
        _menu_set(n, "lat_phy_angle", str(params["lat_phy_angle"]), _PHY_ANGLE_2)
    if "roll" in params:
        _try_set(n, "roll", clamp(float(params["roll"]), -360.0, 360.0))
    if "yaw" in params:
        _try_set(n, "yaw", clamp(float(params["yaw"]), -360.0, 360.0))
    if "randomize_yaw" in params:
        _try_set(n, "randomize_yaw", clamp(float(params["randomize_yaw"]), 0.0, 180.0))
    if "pitch_angle" in params:
        _try_set(n, "pitch_angle", clamp(float(params["pitch_angle"]), -360.0, 360.0))
    if "randomize_pitch" in params:
        _try_set(n, "randomize_pitch", clamp(float(params["randomize_pitch"]), 0.0, 180.0))
    if "twist" in params:
        _try_set(n, "twist", clamp(float(params["twist"]), -360.0, 360.0))
    if "enable_grav" in params:
        _try_set(n, "enable_grav", bool(params["enable_grav"]))
    if "grav_strength" in params:
        _try_set(n, "grav_strength", clamp(float(params["grav_strength"]), -10.0, 10.0))
    if "rows" in params:
        _try_set(n, "rows", int(clamp(int(params["rows"]), 1, 32)))
    if "del_threshold" in params:
        _try_set(n, "del_threshold", clamp(float(params["del_threshold"]), 0.0, 1.0))
    if "offset" in params:
        _try_set(n, "offset", clamp(float(params["offset"]), -5.0, 5.0))
    if "seed" in params:
        _try_set(n, "seed", int(params["seed"]))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 6. quick_basic_tree (chain; input 1 = base surface/pts) — one-call instant tree ──────────────
@endpoint("quick_basic_tree")
def quick_basic_tree(params):
    """Labs Quick Basic Tree (labs::quick_basic_tree) — one-call convenience tree grown from `input`
    (a base surface / point set). `growgen` is EXPONENTIAL in polycount and is hard-clamped to <=8.
    SECURITY: none (no file surface)."""
    n = child_after(params["input"], "labs::quick_basic_tree", params.get("name"))
    if "growgen" in params:
        _try_set(n, "growgen", int(clamp(int(params["growgen"]), 1, 8)))  # EXPONENTIAL — hard cap 8
    if "treeres" in params:
        _try_set(n, "treeres", clamp(float(params["treeres"]), 1e-3, 1.0))
    if "cols" in params:
        _try_set(n, "cols", int(clamp(int(params["cols"]), 3, 32)))
    if "radius" in params:
        _try_set(n, "radius", clamp(float(params["radius"]), 1e-3, 1.0))
    if "bLeaves" in params:
        _try_set(n, "bLeaves", bool(params["bLeaves"]))
    if "distortamnt" in params:
        _try_set(n, "distortamnt", clamp(float(params["distortamnt"]), 0.0, 5.0))
    if "elementsize" in params:
        _try_set(n, "elementsize", clamp(float(params["elementsize"]), 0.0, 5.0))
    if "branchlift" in params:
        _try_set(n, "branchlift", clamp(float(params["branchlift"]), 0.0, 90.0))
    if "branchprune" in params:
        _try_set(n, "branchprune", clamp(float(params["branchprune"]), 0.0, 1.0))
    if "branchstart" in params:
        _try_set(n, "branchstart", clamp(float(params["branchstart"]), 0.0, 1.0))
    if "branchend" in params:
        _try_set(n, "branchend", clamp(float(params["branchend"]), 0.0, 1.0))
    if "minx" in params:
        _try_set(n, "minx", clamp(float(params["minx"]), 0.0, 180.0))
    if "maxx" in params:
        _try_set(n, "maxx", clamp(float(params["maxx"]), 0.0, 180.0))
    if "leafprune" in params:
        _try_set(n, "leafprune", clamp(float(params["leafprune"]), 0.0, 1.0))
    g = n.geometry()
    return {"node": n.path(), "points": len(g.points()), "prims": len(g.prims())}


# ── 7. maps_baker (chain; in0 low/card, in1 high/tree, in2 cage opt) — WIRE-ONLY ─────────────────
@endpoint("maps_baker")
def maps_baker(params):
    """Labs Maps Baker (labs::maps_baker::5.0) — WIRE-ONLY LOD-atlas bake. `input` (input 0) = the low
    /card mesh, `high` (input 1) = the high-res tree, `cage` (input 2) = an optional bake cage. Mirrors
    bake_texture/setup_karma: the graph is BUILT and configured but NOT executed — baking is a render,
    so the human fires it (kills the resource-DoS + cook-freeze surface). Returns rendered=False.
    SECURITY (only tree node with a file surface):
      * `sOutputFile` is realpath-confined to the working directory; map-name / $(CHANNEL) tokens are
        sanitized (no path separators / .. / drive).
      * the .fbx side-exports (`exportlow`/`exporthigh`) and the material-mapping read
        (`materialmapping`) are FORCED OFF and never exposed.
      * `i2Resolution x samplesscalar x framerange` (the render-cost product) is hard-clamped."""
    n = child_after(params["input"], "labs::maps_baker::5.0", params.get("name"))
    if params.get("high"):
        bridge_input(n, params["high"], index=1, name_hint="high")
    if params.get("cage"):
        bridge_input(n, params["cage"], index=2, name_hint="cage")

    # SECURITY: force the write / read file surfaces off; never expose their paths.
    _try_set(n, "exportlow", False)
    _try_set(n, "exporthigh", False)
    _try_set(n, "materialmapping", False)
    _try_set(n, "mBakeMode", 1)  # spec default (idx 1)

    # Confined bake output — only when the caller supplies one (WIRE-ONLY: no bake runs here, so an
    # absent path leaves the HDA default for the human to edit before firing). $(CHANNEL) stays a
    # literal leaf token; confined_path() realpath-confines the rest to the working directory.
    out_path = None
    if params.get("sOutputFile"):
        out_path = confined_path(params["sOutputFile"])
        _try_set(n, "sOutputFile", out_path)

    # Render-cost levers — hard clamp the product i2Resolution x samplesscalar x framerange.
    if "i2Resolution" in params:
        _try_set(n, "i2Resolution", int(clamp(int(params["i2Resolution"]), 16, 8192)))
    if "samplesscalar" in params:
        _try_set(n, "samplesscalar", int(clamp(int(params["samplesscalar"]), 1, 64)))
    if "framerange" in params:
        _try_set(n, "framerange", int(clamp(int(params["framerange"]), 1, 1000)))
    if "edgepadding" in params:
        _try_set(n, "edgepadding", int(clamp(int(params["edgepadding"]), 0, 64)))
    if "framemode" in params:
        _menu_set(n, "framemode", str(params["framemode"]), _BAKE_FRAMEMODE)
    if "opacitytracing" in params:
        _try_set(n, "opacitytracing", bool(params["opacitytracing"]))
    if "fMaxTraceDist" in params:
        _try_set(n, "fMaxTraceDist", clamp(float(params["fMaxTraceDist"]), 1e-4, 1e4))
    if "fRayDistance" in params:
        _try_set(n, "fRayDistance", clamp(float(params["fRayDistance"]), -1.0, 1e4))

    # Map toggles (which channels to bake).
    for tog in ("bDiffuse", "bOpacity", "bNormal", "bVertexCd", "bAO", "bRoughness",
                "bMetallic", "bCurvature", "bHeight", "bAlpha", "bPos"):
        if tog in params:
            _try_set(n, tog, bool(params[tog]))

    # Map-name strings (channel tokens) — sanitized so a map name can't smuggle a path.
    for sn in ("sDiffuse", "sVertexColor", "sAO", "sNormal", "sOpacity"):
        if sn in params:
            _try_set(n, sn, _safe_map_token(params[sn]))

    # WIRE-ONLY: do NOT cook / render — mirror bake_texture (no n.geometry()).
    return {"node": n.path(), "output": out_path, "rendered": False,
            "note": "maps_baker graph wired (WIRE-ONLY); start the bake yourself"}

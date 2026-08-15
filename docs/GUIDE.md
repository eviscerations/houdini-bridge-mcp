# Operator Guide — houdini-bridge-mcp

A day-to-day operating reference for driving this MCP from an AI chat (Claude Desktop or any MCP agent).
It covers how you drive it, what the tool families do, the common end-to-end workflows, and the operating
gotchas — so a session can be productive immediately. Because every step is a typed, explainable, sandboxed
operation, it also doubles as a low-stakes way to *learn* Houdini with an AI at your side — ask it to build
something and watch how it wires the network. For first-time install and setup see the
[README](../README.md) and [docs/SETUP.md](SETUP.md); for exact parameters ask the `node_reference` tool
live, or see the parameter reference in [reference/NODE_REFERENCE.md](../reference/NODE_REFERENCE.md).

---

## How you drive it

You build a **live Houdini scene** by calling the MCP tools from chat. Useful habits:

- Call `scene_info` first to see the current scene (hip file, frame, `/obj` contents).
- The tool can only read/write inside one **working directory** (set during setup). Reference data files
  by their path **relative to that root** — subfolders are traversable (e.g. `tiles/site_a.npy`). Anything
  outside the root is refused.
- Inspect before acting: `read_geo_stats` (geometry readback that is safe on multi-GB clouds),
  `list_node_types` / `node_reference` (what nodes exist and their parameters).
- To *see* results, use `snapshot` (viewport PNG) or `capture_ui` (a screen grab of the live interface).

---

## Install & arm (one-time recap)

Full steps are in the [README](../README.md) / [docs/SETUP.md](SETUP.md). In short:

1. Build the gateway: `cargo build --release` in `gateway/`.
2. Launch the gateway GUI → **Settings → Install Houdini package** (drops the auto-arm package into your
   Houdini user preference directory).
3. Set your **Working directory** to the project root — every subdirectory under it is traversable — and
   turn on **Auto-arm**.
4. Run the firewall harden step (`scripts/harden-firewall.ps1`, elevated) — the executor arms fail-closed
   without it.
5. Register the gateway with your MCP client, pointing at the built `houdini-bridge-mcp.exe` in headless mode
   (`HMCP_GW_HEADLESS=1`).

**Arm the executor:** launch Houdini. It auto-arms from the shared config file — no manual shell snippet.
The GUI status pill shows **Armed** and the connected Houdini version.

**Change the working directory:** type a new root into the GUI's **Working dir** field and click **Apply**.
It rewrites the shared config and takes effect live for the executor and the gateway — no restart.

---

## Tool families

- **Acquire / import** — `acquire_terrain` (fetch real-world elevation for a place), `import_heightfield`
  (a prepared DEM `.npy` → height volume), `import_pointcloud`, `import_geo`, `import_alembic`,
  `import_ecef_tile`, `las_import` (native LAS/LAZ/E57 LIDAR), `osm_import` (OpenStreetMap
  roads/buildings/footprints), `trace_raster`, `create_geo`.
- **Heightfield / terrain** — build, shape, and mask terrain: `heightfield_visualize`, `heightfield_erode`
  (optionally mask-gated), `heightfield_maskby*` (feature / occlusion / shadow / object / concavity),
  `heightfield_flatten` / `clip` / `crop` / `patch` / `layer` / `morph` / `fill` / `cutout` / `deform` /
  `tilesplit`, `convert_heightfield` (→ polygons), `terrain_analysis`, plus packed-tile streaming
  (`add_tile_packed`, `set_tile_lod`).
- **Geometry / model** — `transform`, `boolean`, `polyextrude`, `polybevel`, `remesh`, `polyreduce`,
  `create_primitive`, `create_curve`, `deform`, `drape`, `uv`, `merge`, `fuse`, `normals`,
  `facet_smooth_subdiv`, `lod_create`, `set_color`, `select_group`.
- **Groups / attributes** — `group_create`, `group_combine`, `blast` (delete by group), `attribute_transfer`
  (proximity color transfer), `attribute_create` / `attribute_promote` / `attribute_delete` /
  `attribute_cast`, `connectivity`, `measure`.
- **Cleanup / meshing** — `point_normals`, `segment_planar`, `despeckle`, `level`, `mesh_pointcloud`,
  `mesh_repair`, `polydoctor`, `polyfill`.
- **VDB / volumes** — `vdb_from_polygons`, `vdb_from_particles`, `vdb_convert`, `vdb_filter`,
  `convert_volume`.
- **Instance / scatter** — `scatter`, `scatter_copy`, `copy_to_points`, `instance`, `pack`, `unpack`,
  `biome_scatter`, `tag_radial`.
- **Solvers / sim** — physics scaffolds over real solvers: `sim_rbd` (Bullet), `sim_flip` / `sim_viscosity`
  (FLIP), `sim_pop` / `sim_grains` (POP), `sim_pyro`, `sim_whitewater`, `sim_ripple`, `sim_vellum`
  (Vellum), `sim_mpm` (MPM), plus ocean (`ocean_surface` / `ocean_foam` / `ocean_source`), `cloud`, and
  `fluid_surface`. `solver` is a generic SOP feedback/time-loop (not a physics solver).
- **Point-cloud analysis** — `point_normals`, `segment_planar`, `despeckle`, `level`, `isolate`,
  `tag_radial`.
- **Solaris / LOP / USD** — `sop_import`, `usd_import`, `usd_light`, `usd_camera`, `karma_render_settings`
  (wire-only).
- **Look / camera / material** — `add_camera`, `add_light`, `assign_material`, `set_view_camera`,
  `flightcam`, `build_globe`, `setup_karma` / `bake_texture` (wire-only).
- **Deliver / export / capture** — `export_geometry` / `export_usd` / `export_fbx` / `export_gltf` /
  `export_alembic` / `export_cache`, `flipbook`, `snapshot`, `capture_ui`.
- **Scene / utility** — `scene_info`, `read_geo_stats`, `list_node_types`, `node_reference`, `set_frame`,
  `set_display`, `select_node`, `frame_selected`, `layout_nodes`, `delete_node`, `save_scene`, `mem`,
  `viewport_display`, `viewport_optimize`, `reload_node`.
- **Character rigging & animation (KineFX)** — `character_skeleton` / `orient_joints` / `configure_joints`
  (skeletons), `bone_capture` / `joint_capture_biharmonic` / `capture_layer_paint` (skin capture),
  `joint_deform` / `bone_deform` / `skeleton_deform` / `blend_shapes` (deformation), `rig_pose` /
  `ik_chains` / `full_body_ik` / `fbik_configure_targets` (posing/IK), `motion_clip*` /
  `motion_mixer_*` (motion clips), plus FBX/mocap I/O (`fbx_character_import`, `mocap_import`,
  `retarget_biped_fbx`) — all file I/O working-dir-confined.
- **Crowd** — `crowd_source` / `agent_source` (agents), `crowd_state` / `crowd_transition` /
  `crowd_trigger*` (state machine), `crowd_motion_path*` (path-driven crowds), `agent_layer*` /
  `agent_clip*` (agent authoring).
- **Muscle & tissue** — `muscle_id` / `franken_muscle` (build), `muscle_solidify` (tetrahedralize),
  `muscle_deform` / `muscle_flex` (sim), `tissue_*` / `skin_*` (FEM/OTIS properties + solidify).
- **COP / image compositing** — the `cop_*` family: noise/pattern generators (`cop_fractal_noise`,
  `cop_worley_noise`), color/filter ops (`cop_color_correct`, `cop_blur`, `cop_remap`), PBR-map bakes
  (`cop_height_to_normal` / `_ao`, `cop_bake_geometry_textures`), and `cop_rop_image` (write maps to disk).
- **ML / ONNX** — `onnx_inference`, `ml_regression`, `ml_volume_upres`, `cop_denoise_ai`, and the ML-CV
  synthetics lane (`ml_cv_*`, `render_ml_cv_synthetics`).
- **Procedural / SideFX-Labs** — tree generation (`tree_trunk_generator` / `tree_branch_generator` /
  `quick_basic_tree`, `lsystem`), biomes (`biome_define` / `biome_scatter` / `biome_initialize`),
  and world-building (`building_generator`, `road_generator`, `osm_buildings`, `proc_city` via recipes).

---

## Common workflows

Every path below is confined to the working directory.

### DEM → colored, exportable terrain

```
import_heightfield(npy="<tile>.npy", name="terrain")
heightfield_visualize(input="terrain")        # auto elevation ramp
convert_heightfield(input="terrain", bake_colors=true)
export_geometry(input="terrain", output="terrain.obj")
```

`import_heightfield` needs the `.npy` plus its `.npy.json` sidecar (`cols`, `rows`, `res_m`,
`houdini_center_x/z`, `nodata`); both sit under the working-dir root and paths are relative to it.
`heightfield_visualize` applies an elevation ramp automatically (auto-computes its range).
`convert_heightfield` with `bake_colors` bakes the ramp to point color so the exported mesh keeps it.
`export_geometry` writes a server-ready `.obj` (or use USD/FBX/glTF).

### Shape / weather the terrain

`heightfield_maskby*` to build a mask (slope, features, occlusion, shadow) → `heightfield_erode` with that
mask to erode only where you want → optional `heightfield_flatten` / `clip` for roads, benches, water lines.
Most terrain functions read a mask layer, so **build the mask first**.

### Bare ground → forested hillside

LiDAR DEMs are bare-earth. Build a mask (by height / slope / feature) → `scatter` or `biome_scatter` into
the masked region → `copy_to_points` / `scatter_copy` a few tree models onto the points (even spacing plus
noise). Use packed instancing for large counts so the viewport stays light.

### Point cloud → clean model

```
import_pointcloud(path="<cloud>.ply")
point_normals(...)
segment_planar(...)      # or despeckle / level to classify + clean
mesh_pointcloud(...)
export_geometry(...)     # or export_cache
```

Estimate normals first, clean the cloud (`segment_planar` / `despeckle` / `level`), then mesh and export.
Match `despeckle` radius and `mesh_pointcloud` voxel size to the cloud's real spacing or you'll cull
everything (see Troubleshooting).

### A textured globe with a sun

```
build_globe(texture="<equirect>.jpg", bump="<bump>.jpg")
add_light(ltype="sun", t=[x,y,z], r=[rx,ry,rz])   # position via t, aim via r
select_node(node="/obj/globe")
frame_selected()
capture_ui()
```

An equirectangular `texture` (plus optional `bump`) drapes the sphere. A keyed sun rotation gives a
day/night terminator — render or enable high-quality lighting in the viewport to see it.

### Set up a look

`add_camera` + `add_light` (point or dome/HDRI) + `assign_material` → `setup_karma` (wires the render
graph; you render in Houdini) → `snapshot` / `capture_ui` to review.

### Inspect & navigate

- `scene_info`, `read_geo_stats` — what's in the scene / a node's point & prim counts.
- `list_node_types`, `node_reference` — look up a node type or its parameters.
- `select_node` (with dive), `frame_selected` (home on the selection), `layout_nodes` (tidy the network).
- `viewport_display` — toggle points / normals; then `capture_ui` or `snapshot` for analysis.

### Import existing assets

- `import_geo` — `.obj` / `.bgeo` / `.fbx`
- `import_pointcloud` — `.ply` / `.bgeo`
- `import_alembic` — `.abc`
- `las_import` — native LIDAR `.las` / `.laz` / `.e57`
- `osm_import` — OpenStreetMap roads / buildings / footprints (site context)
- `trace_raster` — image → curves

---

## Operating gotchas

- **Heavy terrain is display-off by default** — a large heightfield can tessellate hundreds of millions of
  voxels on the GPU and stall the viewport. Reveal deliberately; use `viewport_optimize` and `mem` on big
  scenes; avoid frame-all on giant geo — `frame_selected` a specific node instead.
- **Name collisions fail** — creators (`create_*`, `sim_*`, `scatter_copy`, etc.) refuse to overwrite
  existing objects; use a new name or `delete_node` first.
- **Numbers are clamped, not rejected** — an out-of-range value is pinned to the allowed min/max, so a
  "success" with an odd result may have been clamped.
- **`set_display`** controls which node shows in the viewport (setting one clears the others);
  **`delete_node`** (with `reconnect`) removes a node and can bridge the chain so downstream survives.
- **Masks drive everything** — most terrain functions (erosion, scatter density, layering) read a mask
  layer, so build the mask first.
- **Renders are wire-only** — `setup_karma`, `karma_render_settings`, and `bake_texture` build the graph
  but do not execute; you fire the render in Houdini. `export_*`, `flipbook`, `snapshot`, and `save_scene`
  *do* write files.
- **Second-input ops need same-geo operands** — `boolean`, `merge`, `drape`, `copy_to_points` fail across
  different geo objects; put both operands in the same geo or object-merge one in first.
- File paths passed to tools must sit **inside the working directory**; anything outside is refused.

---

## Optional — render on an AMD GPU (ProRender)

`setup_karma` wires a Karma render graph, but Karma XPU's GPU path is NVIDIA-only. On an **AMD Radeon**
(RDNA2 / gfx1030+), the optional [`AMDProRender/`](../AMDProRender/README.md) add-on installs AMD Radeon
ProRender's `hdRpr` delegate built natively for Houdini 21 — "RPR" then shows up as a GPU Hydra renderer in
Solaris (`husk --renderer HdRprPlugin`, or the Scene Viewer renderer menu). It's independent of the core
toolset and needs no code here.
</content>

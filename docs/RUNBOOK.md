# Runbook — houdini-bridge-mcp

A quick operating reference for driving this MCP from an AI chat (Claude or any agent). It covers what the
tool families do, the common end-to-end workflows, and the operating gotchas — so a session can be productive
immediately. For install/setup see the README; for exact parameters ask the tool or see the tool reference.

## How you drive it
You build a **live Houdini scene** by calling the MCP tools from chat. Useful habits:
- Call `scene_info` first to see the current scene (hip file, frame, `/obj` contents).
- The tool can only read/write inside one **working directory** (set during setup). Reference data files by
  their path **relative to that root** — subfolders are traversable (e.g. `tiles/site_a.npy`).
- Inspect before acting: `read_geo_stats` (geometry readback), `list_node_types` / `node_reference`
  (what nodes exist + their params).
- To *see* results, use `snapshot` (viewport PNG) or `capture_ui`.

## Tool families
For the authoritative, maintained family breakdown — geospatial/terrain, geometry, solvers, **character
rigging & animation (KineFX/Crowd/Muscle)**, COP/image, ML/ONNX, SideFX-Labs, and the rest — see
[`GUIDE.md` → Tool families](GUIDE.md#tool-families). It's kept in one place to avoid drift; the
`node_reference` MCP tool and `reference/NODE_REFERENCE.md` give per-tool parameter detail.

## Common workflows

**DEM → colored, exportable terrain**
1. `import_heightfield` (the `.npy` + its `.json` sidecar) → a height volume at true elevation.
2. `heightfield_visualize` → paints an elevation ramp (auto-computes its range) so you can see the terrain.
3. `convert_heightfield` (`bake_colors`) → renderable polygons carrying the color.
4. `export_geometry` → a server-ready `.obj` (or USD/FBX/glTF).

**Shape / weather the terrain**
`heightfield_maskby*` to build a mask (slope, features, occlusion, shadow) → `heightfield_erode` with that
mask to erode only where you want → optional `heightfield_flatten` / `clip` for roads, benches, water lines.

**Bare ground → forested hillside** (LiDAR DEMs are bare-earth)
Build a mask (by height / slope / feature) → `scatter` or `biome_scatter` into the masked region →
`copy_to_points` / `scatter_copy` a few tree models onto the points (even spacing + noise).

**Point cloud → clean model**
`import_pointcloud` → `point_normals` → `segment_planar` / `despeckle` / `level` to classify + clean →
`mesh_pointcloud` (or fit clean geometry to the scan) → `export_*`.

**Set up a look**
`add_camera` + `add_light` (point or dome/HDRI) + `assign_material` → `setup_karma` (wires the render graph;
you render in Houdini) → `snapshot` / `capture_ui` to review.

## Operating gotchas
- **Heavy terrain is display-off by default** — a large heightfield can tessellate on the GPU and stall the
  viewport. Reveal deliberately; use `viewport_optimize` and `mem` on big scenes; avoid frame-all on giant geo.
- **Name collisions fail** — creators (`create_*`, `sim_*`, `scatter_copy`, etc.) refuse to overwrite existing
  objects; use a new name or `delete_node` first.
- **Numbers are clamped**, not rejected — an out-of-range value is pinned to the allowed min/max, so a "success"
  with an odd result may have been clamped.
- **`set_display`** controls which node shows in the viewport (setting one clears the others); **`delete_node`**
  (with `reconnect`) removes a node and can bridge the chain.
- **Masks drive everything** — most terrain functions (erosion, scatter density, layering) read a mask layer,
  so build the mask first.
- File paths passed to tools must sit **inside the working directory**; anything outside is refused.

# How-to

Living document — grows as the tool is tested. Every step below is a typed, sandboxed, explainable
operation, so these flows double as a safe way to *learn* Houdini with an AI driving.

## Install (one-time)

1. Build the gateway: `cargo build --release` in `gateway/`.
2. Launch the gateway GUI → **Settings → Install Houdini package** (drops the auto-arm package into your Houdini user pref dir).
3. Set your **Working directory** to the project root — every subdirectory under it is traversable — and turn on **Auto-arm**.
4. Register the gateway with your MCP client, pointing at `<PATH_TO_REPO>\gateway\target\release\houdini-bridge-mcp.exe` in headless mode.

## Arm the executor

Launch Houdini. It auto-arms from `~/.houdini-bridge-mcp/arm.json` — no manual shell snippet. The GUI's status pill shows **Armed** and the connected Houdini version.

## Change the working directory

Type a new root into the GUI's **Working dir** field and click **Apply**. It writes `arm.json` and takes effect live for the executor and the gateway — no restart.

## Build terrain from a DEM tile

```
import_heightfield(npy="<tile>.npy", name="terrain", display=true)
```
Produces a real Houdini heightfield placed at the tile's scene position (Z-negated). Requires the `.npy` plus its `.npy.json` sidecar (`cols`, `rows`, `res_m`, `houdini_center_x/z`, `nodata`) inside the working directory.

---

## Worked examples

Proven end-to-end flows. Every path is confined to the working directory.

### DEM → colored, exportable terrain

```
import_heightfield(npy="<TILE>.npy", name="terrain")
heightfield_visualize(input="terrain")          # auto elevation ramp
convert_heightfield(input="terrain", bake_colors=true)
export_geometry(input="terrain", output="terrain.obj")
```
`import_heightfield` needs the `.npy` plus its `.npy.json` sidecar (`cols`, `rows`, `res_m`, `houdini_center_x/z`, `nodata`); both sit under the working-dir root and paths are relative to it. `heightfield_visualize` applies an elevation ramp automatically; `convert_heightfield` with `bake_colors` bakes the ramp to point color so the exported mesh keeps it.

### A textured globe with a sun

```
build_globe(texture="<EQUIRECT>.jpg", bump="<BUMP>.jpg")
add_light(ltype="sun", t=[x,y,z], r=[rx,ry,rz])   # position via t, aim via r
select_node(node="/obj/globe")
frame_selected()
capture_ui()
```
An equirectangular `texture` (+ optional `bump`) drapes the sphere. A keyed sun rotation gives a day/night terminator — render or enable high-quality lighting in the viewport to see it.

### Inspect & navigate

- `scene_info`, `read_geo_stats` — what's in the scene / a node's point & prim counts.
- `list_node_types`, `node_reference` — look up a node type or its parameters.
- `select_node` (with dive), `frame_selected` (home on the selection), `layout_nodes` (tidy the network).
- `viewport_display` — toggle points / normals; then `capture_ui` or `snapshot` for analysis.

### Import existing assets

All confined to the working dir:
- `import_geo` — `.obj` / `.bgeo` / `.fbx`
- `import_pointcloud` — `.ply` / `.bgeo`
- `import_alembic` — `.abc`
- `las_import` — native LIDAR `.las` / `.laz` / `.e57`
- `osm_import` — OpenStreetMap roads / buildings / footprints (site context)
- `trace_raster` — image → curves

### Clean a point cloud → mesh

```
import_pointcloud(path="<CLOUD>.ply")
point_normals(...)
segment_planar(...)      # or despeckle / level to clean
mesh_pointcloud(...)
export_geometry(input="<meshed>", output="mesh.obj")   # or export_cache(input=..., output=...)
```
Estimate normals first, clean the cloud (`segment_planar` / `despeckle` / `level`), then mesh and export. Match `despeckle` radius and `mesh_pointcloud` voxel size to the cloud's real spacing or you'll cull everything (see Troubleshooting).

---

## Optional — render on an AMD GPU (ProRender)

`setup_karma` wires a Karma render graph, but Karma XPU's GPU path is NVIDIA-only. If you're on an **AMD
Radeon** (RDNA2 / gfx1030+) and want GPU rendering, the optional [`AMDProRender/`](../AMDProRender/README.md)
add-on installs AMD Radeon ProRender's `hdRpr` delegate built natively for Houdini 21 — "RPR" then shows
up as a GPU Hydra renderer in Solaris (`husk --renderer HdRprPlugin`, or the Scene Viewer renderer menu).
It's independent of the core toolset and needs no code here.

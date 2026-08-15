# Troubleshooting

Living document — grows as the tool is tested. Each entry: **symptom → cause → fix**.

## Paths / confinement

**"path outside working directory" on a path that is inside it**
- A `\\?\` Windows extended-length prefix (from a Rust `canonicalize()`) doesn't match the un-prefixed root. The executor normalizes the prefix before confining.
- The confinement root is read live from `arm.json`'s `working_dir` (set by the GUI's **Apply**); subdirectories under it are traversable. Falls back to the arm-time value if the config is unreadable.

**`SyntaxError: (unicode error) 'unicodeescape'` building a heightfield**
- A Windows path (`C:\Users\...`) interpolated into a server-authored Python SOP string — the `\U` reads as a unicode escape. Forward-slash the path before interpolation.

## Heightfields

**`hou.InvalidSize: … must be the same as the number of voxels in the volume`**
- The HeightField SOP's `sizex/sizey` are **world-size (metres)**, not sample counts. Setting them to `cols/rows` with `gridspacing = res_m` builds `cols/res` voxels — correct only when `res == 1`.
- Fix: `sizex = cols * res_m`, `sizey = rows * res_m`. A nearest-neighbour resample guard also makes `setAllVoxels` robust to any residual off-by-one.

## GUI

**Window renders as a plain white box**
- eframe re-applies the OS theme at the start of every frame, stomping a one-time dark `set_visuals` done in the creation closure (on a light-mode OS).
- Fix: set visuals at the top of `update()`, and give panels explicit dark `Frame` fills.

---

## Licensing

### "FBX/glTF/Alembic export is only supported in Houdini Core/FX"

The FBX, glTF, and Alembic ROP exporters are disabled on Apprentice (Non-Commercial).

Fix: on the free tier, use `export_geometry` (`.obj` / `.bgeo`) or `export_cache` (`.bgeo.sc`). FBX / glTF / Alembic export needs a Core, FX, or Indie license.

---

## Node paths & inputs

### "Invalid node type name" when applying a geometry op

You passed an *object* path (`/obj/foo`) where a SOP was expected — a SOP can't be created in the object network.

Fix: pass the SOP path (`/obj/foo/<sop>`), or let the tool auto-resolve the object's display SOP (recent builds). Use `read_geo_stats` or the returned `sop` path to find it.

### "setInput failed" — a second-input op errors across objects

Second-input ops (`boolean`, `merge`, `drape`, `copy_to_points`) fail when the two operands live in different geo objects. Houdini SOPs can't take an input from a *different* geo object.

Fix: put both operands in the same geo, or object-merge the second geo in first. Same-geo operands work.

### "Cannot create a node inside a locked asset"

The input node is inside a locked Labs HDA and the op tried to build within it.

Fix: operate on an unlocked SOP, or unlock the asset.

---

## Geometry ops

### A tool "succeeds" but returns 0 points / empty geo

This is a parameter-scale mismatch, not a failure:
- `despeckle` — radius too small for the cloud's spacing culls every point.
- `mesh_pointcloud` — voxel size larger than the point spacing yields no surface.
- `ocean_foam` — needs a whitewater / animated source; returns 0 at a static frame.

Fix: match radius / voxel size to the data's real-world scale; advance frames for sim-derived tools.

---

## Rendering & export

### `setup_karma` / `bake_texture` don't produce an image

⚠️ These are WIRE-ONLY — they build the graph, they don't render or bake.

Fix: start the render / bake in Houdini (or via the ROP). `export_*`, `flipbook`, `snapshot`, and `save_scene` DO write files.

### `export_usd` fails to save

USD export needs a valid LOP (Solaris) network to export from. Without one there's nothing to write.

Fix: supply a `loppath` to a LOP net (or build one) before exporting USD.

### The scene looks flat / a light has no visible effect

The viewport defaults to headlight shading, so scene lights (point / sun / etc.) don't shade the geometry.

Fix: switch the viewport to high-quality lighting, or set up and render `setup_karma`.

### AMD ProRender ("RPR") — plugin loads, but "Render Devices" dialog errors

The optional `AMDProRender/` `hdRpr` delegate is working: rebuilt with the MSVC **v143** toolset,
Houdini boots cleanly with the full plugin, "RPR" is a selectable Hydra renderer, and the native RPR
material VOPs, LOP render-settings, and RPR Material Library all load. The one known gap is the RPR
menu's **Render Devices** dialog, which still needs a USD-25 Python-binding port.

Fix: none needed to render — the Render Devices dialog is a convenience, not a prerequisite. Select
"RPR" as the Hydra renderer and render normally.

---

## Point clouds & terrain scale

### A heavy heightfield / scene stalls the viewport

⚠️ Display + frame-all tessellates hundreds of millions of voxels on the GPU.

Fix: keep heavy geo display OFF, use `viewport_optimize` + `mem`, and `frame_selected` a specific node instead of frame-all.

---

## References

When a tool's exact parameters, a node type, or a Houdini behavior is unclear, these are the authoritative
sources — all offline, no network needed:

- **The `node_reference` MCP tool** — the authoritative live-probed node/parameter reference for Houdini
  21.0.671, queryable directly from chat (`node`, `search`, `category`). Nothing in it is guessed; every
  parameter name was read from a live node. This is the fastest way to confirm a param name or its default
  from inside a session.
- **The parameter reference archive** — [`reference/NODE_REFERENCE.md`](../reference/NODE_REFERENCE.md) is
  the human-readable archive backing the `node_reference` tool (one grep-able line per parameter); the
  structured source of record is `reference/houdini_nodes.json`. The full typed tool catalog is
  `reference/catalog.json`. Use these when you want to search the whole reference at once.
- **The local Houdini help server** — every running Houdini serves its complete offline node/parameter
  documentation on its built-in web server at **`http://127.0.0.1:48626/`** (SideFX's default help port).
  The central landing page is [`http://127.0.0.1:48626/help/central.html`](http://127.0.0.1:48626/help/central.html).
  This is the full SideFX docs for the exact Houdini build you have running — the ground-truth reference
  for node behavior beyond just parameter names.

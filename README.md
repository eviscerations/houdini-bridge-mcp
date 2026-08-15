# houdini-bridge-mcp

**Drive SideFX Houdini from an AI chat — a security-first, data-only control surface where the AI authors *validated* wrangles, never arbitrary code.**

A Windows-native MCP ([Model Context Protocol](https://modelcontextprotocol.io)) server that lets an AI
chat client drive [SideFX Houdini](https://www.sidefx.com) across a broad swath of its creative surface —
through a fixed catalog of **typed, validated tools with no arbitrary-code path**. The AI builds and inspects node
networks and can author a *validated, bounded* wrangle; **you** fire the heavy cooks and renders. It also
doubles as a safe way to *learn* Houdini — every step is a guided, explainable, sandboxed operation, not a
black box. The catalog is broad: geometry & cleanup · instancing · simulation (FLIP/Pyro/RBD/Vellum) ·
**character rigging & animation** (KineFX, Crowd, Muscle) · COP/image compositing · look & materials ·
ML/ONNX · SideFX-Labs (tree/biome/world-building) · render & export — plus a unique **real-world geodata
lane** (DEM / USGS 3DEP / LIDAR) that reprojects and places elevation at true scale. One binary runs
alongside Houdini and your AI client; that's the whole install.

> **Status:** **v0.1.0 released** — security-hardened, feature-complete. The in-Houdini executor (the
> typed tool surface), the terrain downloader (global + national coverage), and the Rust driver binary +
> Houdini package are all shipped — grab the gateway from the [Releases](../../releases) page. **Target:
> Houdini 21.0.671** (Apprentice works; Houdini 22 exists but is not yet adopted here). Windows-first;
> other platforms later.

---

## Quickstart

**New to this / not a coder? Start here.** Plenty of Houdini users already live in code and a terminal —
but you do **not** need to. Getting running is: get one program, click a couple of buttons in its window,
launch Houdini, and paste one small block of settings into your AI client. That's the whole job. The three
steps below are the map; the numbered **Steps 1–7** further down walk each one in detail, and you only ever
touch a command line if you choose to build the program from source instead of downloading it.

What you'll need on hand: **Houdini 21.0.671** (the free **Apprentice** edition is fine), a **Windows** PC,
and an AI client that speaks MCP (Claude Desktop, Cursor, etc.). One folder on your disk becomes the
project the AI is allowed to touch — pick it in Step 3.

Three steps to a working setup (full detail in Steps 1–7 below):

1. **Get the gateway** (the one program that connects your AI to Houdini) — either **download** the
   prebuilt `houdini-bridge-mcp.exe` from Releases (no coding), or **build** it from source
   (`cd gateway && cargo build --release`, needs the Rust toolchain). It's a single file with no runtime
   dependencies.
2. **Install & arm** — run the gateway, which opens a small GUI window. In it: click **Install Houdini
   package** (wires Houdini to auto-connect), set your **working directory** and click **Apply** (the one
   folder the AI may read and write), and toggle **Auto-arm** on. Then launch Houdini — the status pill
   should read **Armed**. Before letting anything but this one machine reach it, run the firewall script
   (Step 4).
3. **Connect your AI client** — tell your AI client (Claude Desktop, Cursor, …) where the gateway is by
   pasting one small JSON block into its config (copy-paste ready in Step 6), fully restart the client,
   then run the Step 7 check to confirm the AI can see your Houdini scene.

---

## Why it's different

Other Houdini/Blender MCP servers expose *arbitrary Python execution* to the model — powerful, but it is
remote-code-execution by design (across the surveyed field every comparable bridge ships an
`execute_code`-style tool, and one widely-used Blender bridge has a documented remote-code-execution
issue). This one is the inverse:

- **Data-only by construction.** The AI can only call a fixed registry of **1,467** typed, validated
  operations. There is deliberately **no** arbitrary-code tool, **no** generic node-parameter setter, and
  **no** raw VEX/Python path — those simply do not exist in the catalog, so the boundary cannot be talked
  past. The set of things the server can do *is* the enumerated tool list.
- **Validated authoring — the differentiator, not an escape hatch.** The one code-carrying tool,
  `set_attrib_expr` (opt-in, **default-off**), takes a VEX attribute snippet and **validates it against an
  allowlist before Houdini ever sees it**: no file/host/network reach, allowlisted functions only, and provably
  **total — it always halts.** Control flow is conditionals, **statically-bounded counted loops** (`for` — a literal
  or `min()`-clamped iteration ceiling), and a **leaf-only, snapshot-finite array loop** (`foreach`, whose iteration
  count VEX fixes at entry, and which may not nest inside or contain another loop); `while`/`do`/`gather` stay banned,
  so no infinite-loop construct exists.
  Three capabilities layer on behind their *own* independent default-off consents: bounded loops (`allow_attrib_loops`),
  **deletion topology edits** (`removepoint`/`removeprim`, `allow_attrib_geoedit`), and **construction/growth**
  (`addpoint`/`addprim`/`addvertex`/`removevertex`, `allow_attrib_geogrow`) — all pinned to the input-0 working
  geometry, and each consent independent (enabling one never grants another). Most wrangle work is covered by *typed* operators anyway (field calculus, per-voxel math,
  CSG/advection via `vdb_*`); `vex_reference` also serves the offline function reference for hand-paste.

  **This is the line no other Houdini MCP holds: the AI can author a real, capable wrangle without ever handing
  you a remote shell.** Every third-party bridge ships unvalidated `execute_code`/raw-VEX — RCE by design.
  SideFX's own upcoming official MCP validates *generated* code for correctness after the fact, and only for
  rigging. This validates a *bounded subset of the input, before it runs, across the whole toolset* — a stricter
  model, not a smaller door.
- **Learn Houdini with an AI — safely, not just drive it.** Every action is a typed, sandboxed,
  *explainable* operation, and the AI hands you the exact validated wrangle it proposes — so it doubles as a
  guided tutor: ask it to build something, watch how it wires the network, read the *why*. Nothing it does can
  run arbitrary code on your machine or touch work outside the project folder, which makes it as safe for a
  beginner's first scene as for a locked-down pipeline. The same rails that keep it secure make it a low-stakes
  place to learn how Houdini actually works.
- **One working directory.** Every file read and write is `realpath`-confined to a single project folder
  you choose. Nothing outside it is reachable, even through a symlink or junction.
- **Renders are wire-only.** The AI builds render graphs (Karma, texture bake); **you** fire them. It
  never triggers a render on its own.
- **Built for real-world geodata.** It is the only one of its kind aimed at DEM / 3DEP / LIDAR: it
  reprojects and places elevation at true scale, reconstructs point clouds into clean meshes (plane-fit
  and remesh, not organic blobs), and can pin tiles onto a correct Earth frame.
- **Broad, not just terrain.** The geospatial pipeline is the specialty, but the same typed, data-only
  surface spans most of Houdini: modeling and cleanup, the major solvers, **character rigging and
  animation** (KineFX skeletons/capture/deform, Crowd, Muscle), COP image compositing, ML/ONNX, and the
  SideFX-Labs tree/biome/world-building toolset — all under the same no-RCE boundary.

---

## Learn Houdini with an AI

Houdini is famously deep, and the blank-network moment is where most people bounce off. This bridge is
a guided, low-stakes way to sit down and actually *learn* it — you describe what you want, the AI builds
it in your live session, and you watch the network take shape.

- **It's not a toy.** The tool surface reaches a broad, capable slice of real Houdini — modeling and
  cleanup, geometry sim setup (FLIP / Pyro / RBD / Vellum), character rig & animation (KineFX, Crowd,
  Muscle), COP image compositing, look & materials, and the SideFX-Labs tree/biome/world toolset. You can
  learn a genuine workflow, not a sandbox imitation of one. (See the honest coverage numbers below for
  exactly what's in and out of scope.)

- **The typed endpoints are the learning scaffold.** Every capability is a fixed, typed, validated
  operation, so the AI can only reach *real Houdini operations* — it cannot wander outside what the
  software actually does or invent a step that isn't there. The tool list itself mirrors how Houdini is
  organized (the SOP/COP/DOP/KineFX families, the Labs toolset), so the surface that bounds the AI also
  teaches you how the application is structured.

- **You watch it, you don't run it blind.** Every operation streams live into the gateway GUI's audit
  log, so you *see* the AI work step by step in a running Houdini session — the network gets built in front
  of you, node by node, rather than executed in a headless batch you never observe. That live, watched mode
  is the learning advantage. (Headless operation is still supported for power users who want it.)

- **Mistakes become teaching moments, not disasters.** AI can be wrong — it may pick the wrong node or
  misjudge a parameter. The point isn't that it never errs; it's that the typed, sandboxed, *inspectable*
  surface makes any mistake visible, easy to undo, and harmless. Nothing it does runs arbitrary code or
  touches files outside your project folder, so a bad step is something you *catch and correct while
  learning why*, not something that can damage your machine or your work.
  - **This is why it wasn't built on an existing `execute_code` bridge.** The design assumes the model
    can be wrong, steered (prompt injection), or malfunction — and that giving an agent arbitrary code
    plus a goal is the documented high-severity failure mode (agents that escape their sandbox, act
    autonomously and undetected, and reach credentials/network/files). So rather than iterate from a
    Blender/Houdini MCP that hands the model a shell, this one cuts the code path entirely and rebuilds
    data-only: the fixed typed catalog *is* the boundary. The limitation is the security property. See
    [SECURITY.md](SECURITY.md#design-data-only-executor) for the full rationale.

**Honest coverage — what's in scope and what isn't.** By raw count the catalog reaches a deliberate
*minority* of Houdini's non-deprecated node types — exposed as the **1,467** typed tools in the catalog
(one node type is often reached by several tools, and whole families — VOP / SHOP / COP-internal / PDG —
are excluded by design, not omission). But that raw number *understates* the creative coverage,
because it's weighted hard toward the workflows most people actually use and leaves some whole domains out
on purpose:

- **Well covered (the creative core):** COP compositing **~84%**, SOP modeling/geometry **~49%**,
  SideFX-Labs **~65%**, KineFX rig/animation **~53%**.
- **Deliberately out of scope (scoping decisions, not bugs):** USD / Solaris (LOP) **~10%**, PDG / TOP
  **0%** (the batch / dependency-graph domain), legacy Cop2 and Shop contexts, and VOP internals
  (**1.3%** — by design: a VOP is a graph-internal building block, not a data surface the bridge exposes).

In short: roughly a quarter of Houdini's node surface by raw count, but weighted toward the creative
workflows most people actually use, with a few whole domains (USD/Solaris, PDG) intentionally left out. A
newcomer knows up front what they can learn here and what they can't.

---

## What you can do with it

Once installed and armed, you can say things like this directly in your AI chat client (paths are
relative to the one working directory you configure):

- *"Build the terrain around 46.5°N, 114.0°W at 10 m resolution and put a camera on it."*
- *"Fetch elevation for this bounding box and import it at true scale."*
- *"Load `scans/site.ply`, clean out the speckle, and mesh it."*
- *"Erode this heightfield, then mask the gullies and the shadowed slopes."*
- *"Scatter rocks across the terrain with packed instancing so the viewport stays light."*
- *"Give me a sun light for late afternoon and frame the ridge."*
- *"Wire a Karma render aimed at that camera — I'll press the button."*
- *"Export the terrain mesh as USD into my project folder."*
- *"Build a KineFX skeleton for this mesh, capture it, and deform-test the bind."*
- *"Set up a crowd of agents walking a path across the terrain."*
- *"Splash a FLIP sim into that basin and cache it wire-only."*
- *"What's in the scene right now, and how much memory is Houdini using?"*

---

## How it works

```
  AI / MCP client  ──stdio──▶  houdini-bridge-mcp  (one binary: config + GUI + gateway)
                                        │  loopback HTTP
                                        ▼
                               a data-only executor running inside your live Houdini session
```

- The **binary** is both a small GUI (front-of-house: locate Houdini, set the working directory, generate
  a session token, show a live audit log of every call) and the headless MCP gateway your AI client talks
  to over stdio.
- The **gateway** is the typed front door: every `tools/call` is validated against the catalog — unknown
  keys rejected, numerics clamped to range, enums checked, paths confined — before anything is forwarded.
- The **executor** is a data-only Python package that arms itself automatically inside your Houdini
  session and performs the requested operation on real nodes.

The gateway and executor share one **token**, **port**, and **working directory**, single-sourced from a
small config file the GUI writes — so there are no manual shell snippets and no port-collision dance.

---

## Requirements

1. **Houdini 21.0.671** — Apprentice works (the free edition; no license purchase needed to try this).
2. **A Rust toolchain** (stable) — only if you **build** the gateway yourself; skip it if you download the
   prebuilt `.exe` from Releases. [rustup.rs](https://rustup.rs)
3. **Python** — only for the optional terrain downloader (`rasterio` for the DEM data-prep step); any
   recent CPython works. Not needed for a first run.
4. **Windows** — Windows-first; other platforms later.

---

## Step 1 — Get the gateway

**Prefer no coding?** Download the prebuilt `houdini-bridge-mcp.exe` from Releases and skip straight to
Step 2 — it is the same single binary the build produces. **Want to build from source instead** (or there's
no prebuilt binary for your setup yet)? Run:

```
cd gateway
cargo build --release
```

Either way you end up with one file — the gateway is both the GUI and the headless MCP server. Which mode
it runs in is selected at launch by one environment variable, `HMCP_GW_HEADLESS` — unset opens the GUI
window, `1` runs the headless stdio server. (You won't normally set this by hand: double-clicking the file
opens the GUI, and the config block in Step 6 sets the headless flag for your AI client.)

---

## Step 2 — Install the auto-arm Houdini package

This drops a small Houdini
[package](https://www.sidefx.com/docs/houdini/ref/plugins.html) that arms the executor automatically when
Houdini's GUI starts — so the bridge comes up ready, with no "start the server" step.

**Via the GUI (recommended):** launch the binary, then **Settings → Install Houdini package**.

**Or manually,** copy the two static package files into your Houdini user preference directory (defaults
to `%USERPROFILE%\Documents\houdini21.0`):

```
houdini_package/houdini-bridge-mcp.json            →  <houdini-user-pref-dir>/packages/houdini-bridge-mcp.json
houdini_package/houdini-bridge-mcp/scripts/456.py  →  <houdini-user-pref-dir>/houdini-bridge-mcp/scripts/456.py
```

The package files are shippable — no absolute paths, usernames, or machine values; everything dynamic is
read at runtime from the shared config file.

---

## Step 3 — Configure via the GUI

Launch the binary with `HMCP_GW_HEADLESS` unset so the window appears, then:

1. **Settings** — confirm the **executor port** and **session token** (defaults are fine; the token is
   the shared secret between the two halves).
2. **Working dir** — type your **project root**. Every subdirectory under it is reachable; nothing outside
   it is. Click **Apply**.
3. Back in **Settings**, turn on **Auto-arm Houdini**.

Apply + Auto-arm write the shared config file (`arm.json`, under your user profile) that the GUI, the
executor, and the headless gateway all read live. Changing the working directory later is just **Apply** —
no restart.

**Where `arm.json` lives / enabling safe-VEX.** `arm.json` is the trust root — working dir, session token,
port, and feature flags — at:

```
%USERPROFILE%\.houdini-bridge-mcp\arm.json     (Windows)
~/.houdini-bridge-mcp/arm.json                 (macOS / Linux)
```

The one opt-in code lane, `set_attrib_expr`, is **off by default**. To turn it on, open **Settings →
Safe-VEX (advanced)** and flip **Enable safe-VEX (`allow_attrib_expr`)** — it takes effect immediately (the
executor re-reads the flag per call; no restart). That panel also has **Open arm.json** and **Open config
folder** buttons if you'd rather hand-edit; to enable by hand, set `"allow_attrib_expr": true` in the file.
This is an **operator-only** switch — a driving agent can never reach `arm.json` (it is held off-limits even
when the working dir is misconfigured to an ancestor), so the AI cannot enable its own code lane. Turn it
back off the same way when you're done.

---

## Step 4 — Harden the firewall

The executor arms **fail-closed** — it refuses to arm unless a firewall rule blocks inbound connections
to its loopback port. Run the bundled script once, from an elevated shell:

```
scripts/harden-firewall.ps1              # -Mode loopback (default): loopback-only, single machine
scripts/harden-firewall.ps1 -Mode lan    # allow a trusted studio LAN to reach the executor
```

Use `loopback` (the default) for a single trusted machine; use `lan` only on a trusted studio network.

---

## Step 5 — Arm the executor

Launch Houdini. The installed package auto-arms the executor from the shared config — the console prints:

```
[houdini-bridge-mcp] executor armed
```

The GUI's status pill shows **Armed** with the connected Houdini version — for most people that pill is
all the confirmation you need. No Python-shell snippet required. If you want to double-check from a terminal
(optional, for the curious — use your configured port and token):

```
curl.exe http://127.0.0.1:8765/health -H "X-HMCP-Token: <your-token>"
```

→ `{"ok": true, "service": "houdini-bridge-mcp", ...}`

---

## Step 6 — Register with your MCP client

Point your client (e.g. Claude Desktop — edit the file at `%APPDATA%\Claude\claude_desktop_config.json`;
paste that path into the File Explorer address bar to find it) at the gateway binary in **headless** mode
(no window — the AI drives it directly). The gateway reads the working directory, port, and token from the
shared config file, so the env block only needs the headless flag. Set `command` to the full path of the
`.exe` from Step 1:

```json
{
  "mcpServers": {
    "houdini-bridge-mcp": {
      "command": "<path-to-repo>\\gateway\\target\\release\\houdini-bridge-mcp.exe",
      "env": {
        "HMCP_GW_HEADLESS": "1"
      }
    }
  }
}
```

> Use **double backslashes** in all Windows paths.

Fully quit and reopen the client. In a new chat the `houdini-bridge-mcp` tools appear.

---

## Step 7 — Verify your setup

1. Confirm the GUI status pill reads **Armed** with your Houdini version.
2. In a new client chat, ask for a scene report:

   > *"Run `scene_info`."*

   A successful reply (hip file, frame, Houdini version, `/obj` contents) confirms the
   client → gateway → executor link end to end.
3. Then turn a prepped DEM tile into a real heightfield:

   > *"`import_heightfield` from `terrain.npy`, name it `terrain`, and display it."*

If both return, you are wired. See [docs/SETUP.md](docs/SETUP.md) for the full first-run walkthrough and
[docs/GUIDE.md](docs/GUIDE.md) for day-to-day operation.

---

## Available tools

Around **1,467 typed operations**, grouped into the families below (the generated tables show the exact current catalog). Every tool is a validated handler —
no free-form code path exists. **Full parameter reference: see [docs/GUIDE.md](docs/GUIDE.md), or ask the
`node_reference` tool live in-session.**

<!-- BEGIN TOOLS (generated) -->
<!-- GENERATED by scripts/generate_docs.py from reference/catalog.json — do not hand-edit. -->

### Acquire & import

| Tool | What it does | Key params |
|---|---|---|
| `acquire_terrain` | Fetch real-world elevation for a place and prep it to Houdini-ready tiles in the working directory. | 11 optional |
| `create_geo` | Create an empty /obj geometry, optionally seeded with a starting primitive SOP. | `name` (+1 optional) |
| `import_pointcloud` | Load / import a .ply or .bgeo POINT CLOUD (LIDAR, photogrammetry, scan points) into a new /obj geometry via a File SOP. up_axis z_up rotates Z-up survey data into Houdini's Y-up; downsample keeps every Nth point to lighten heavy clouds; recenter moves it to the origin. | `path`, `name` (+3 optional) |
| `import_heightfield` | Import a prepared DEM (.npy + .json sidecar) as a Houdini height volume, placed at true elevation on a shared project origin (Z-negated). | `npy`, `name` (+1 optional) |
| `import_ecef_tile` | Pin a prepped DEM tile (a prep_ecef .npy of (H,W,3) positions) onto the globe as a curved quad mesh at its true position and elevation. | `npy`, `name` (+1 optional) |
| `list_working_dir` | List the files + folders in the confined WORKING DIRECTORY so you can DISCOVER what assets are present before importing — the answer to 'can you see my file?'. | 5 optional |
| `import_geo` | Load / import a MESH geometry file — .obj, .bgeo/.bgeo.sc, .fbx, .stl, .ply, .geo and other File-SOP formats — into a new /obj geometry. include_prim_types loads as packed geometry (flat-memory for heavy assets). | `path`, `name` (+1 optional) |
| `import_alembic` | Load / import an Alembic archive (.abc) — animated/cached meshes, cameras and transforms — into a new /obj geometry via an Alembic SOP. groupnames chooses how archive paths become primitive groups; polysoup loads polygons as memory-light polygon-soup primitives. | `path`, `name` (+2 optional) |
| `trace_raster` | Trace / vectorize an image raster (.png/.jpg/.tif) into 2D outline CURVES via the Trace SOP — turn a logo, silhouette, mask or map into polygon curves to extrude/sweep. | `file`, `name` (+2 optional) |
| `osm_filter` | SideFX Labs OSM Filter — keeps only the wanted feature classes from imported OpenStreetMap geometry (input 0 = an osm_import output). | `input` (+12 optional) |
| `osm_buildings` | SideFX Labs OSM Buildings — extrudes 3D building masses from the closed OpenStreetMap footprint polygons on input 0 (an osm_import / osm_filter output carrying the `building` prim attribute). | `input` (+8 optional) |
| `obj_importer` | SideFX Labs OBJ Importer — a fresh /obj geo that imports a Wavefront .obj file (`file`, READ-confined) with an optional custom .mtl (`custom_mtl`, READ-confined). | `name`, `file` (+1 optional) |
| `fbx_archive_import` | SideFX Labs FBX Archive Import — a fresh /obj geo that imports an FBX file (`file`, READ-confined) as merged Houdini geometry, optionally with materials / animation / bones. | `name`, `file` (+10 optional) |
| `multi_file` | SideFX Labs Multi File — a fresh /obj geo that imports up to eight geometry files at once (`file1`..`file8`, each READ-confined) and merges them, optionally stamping a `name` attribute from each filename. | `name`, `file1` (+9 optional) |
| `regions_from_image` | SideFX Labs Regions From Image — a fresh /obj geo that reads an image (`image`, READ-confined) and generates color-quantized region geometry (`num_colors` regions; `smoothing` softens the boundaries). | `name` (+9 optional) |
| `trace_psd_file` | SideFX Labs Trace PSD File — a fresh /obj geo that reads a layered image (`file`, READ-confined; a Photoshop .psd) and traces its layers into 2D polygon outlines. | `name`, `file` |
| `las_import` | Native LAS/LAZ/E57 LIDAR ingestion (the real survey/aerial delivery format) into a new /obj geo. | `name`, `file` (+13 optional) |
| `osm_import` | Import OpenStreetMap roads/buildings/footprints (venue-context geometry) into a new /obj geo. | `name`, `file` (+4 optional) |
| `usd_import_sop` | Import a USD file into SOP geometry inside a fresh /obj geo (the SOP-context `usdimport` — the read bridge from a USD stage down into native Houdini SOPs). | `file` (+12 optional) |

### Terrain & heightfields

| Tool | What it does | Key params |
|---|---|---|
| `heightfield_crop` | Crop / resize / re-window a height volume to a size box in metres. sizex/sizey are the window width and length; center [x,y,z] positions the window (slide it across a larger field with cropmode=replace); cropmode is intersect (cut to overlap, default), replace (use the new box, extend past the original via the border policy) or union (bbox of both); voxelpad adds padding voxels. | `input` (+6 optional) |
| `heightfield_patch` | Transfer/blend features from a patch height volume (input1) onto a base (input0) with a smooth boundary — mosaic adjacent DEM tiles or stamp a masked region. scale uniformly scales the patch (grid + feature magnitude) before transfer; heightscale scales only the transferred feature heights; tx/tz translate and ry rotates-about-Y the patch before transfer; centerpatch pivots those handles on the masked region. | `input`, `patch` (+7 optional) |
| `convert_heightfield` | Convert a height volume into renderable/exportable geometry. conversion picks the output (poly \| polysoup dense-non-editable \| vdb 3D volume); surftype is the polygon connectivity (triangles/quads are the useful terrain layouts); lod is Density = output-resolution ratio (0.5 = half res, 2 = 4x supersample); bake_colors bakes the heightfield material onto the mesh as point Cd so the deliverable carries the gradient; extrude_base + depth add a solid extruded base (watertight for print/CFD). | `input` (+8 optional) |
| `heightfield_morph` | Grayscale morphology on a named /obj heightfield's height layer, built server-side as a chain of separable min/max volume-wrangles (no single native SOP). op: dilate (grow peaks) \| erode (grow valleys) \| close (fill channels up to the surrounding envelope, keep peaks) \| open (remove thin peaks). radius_m sets the kernel radius in metres (converted to voxels via voxelsize). | `name` (+5 optional) |
| `heightfield_fill` | Masked Laplacian relaxation, built server-side as a chain of Jacobi volume-wrangles (no single native SOP): fill masked voxels (mask==1) by averaging neighbours while holding unmasked voxels (mask==0) as a Dirichlet boundary — reconstructs a smooth surface across a channel/hole. iterations = Jacobi steps (more = smoother/farther fill); seed_layer optionally pre-seeds the masked voxels. | `name` (+5 optional) |
| `heightfield_tilesplit` | Split a heightfield into a tiles_x by tiles_y grid (native LOD / streaming / per-tile game-engine export). | `input` (+7 optional) |
| `heightfield_clip` | Clip height values to a min/max band (outlier clamp / mesa flattening). minheight/maxheight are the clip floor/ceiling (each auto-enables its clip toggle); soft_clip softens the transition into the clipped value instead of a hard clamp (default on) and clip_strength sets its sharpness. | `input` (+5 optional) |
| `heightfield_cutout` | Cut out a non-rectangular heightfield region bounded by geometry (input1), writing the `Alpha` display layer (cutout at Alpha=0.5). | `input` (+5 optional) |
| `heightfield_erode` | Hydraulic + thermal erosion at a chosen feature scale (HeightField Erode 3.0). | `input` (+27 optional) |
| `heightfield_visualize` | Color-ramp a heightfield so its elevation (and an optional mask tint) is visible in the viewport — inserts in native voxel space. layer is the height layer shown as the 3D surface (node parm `heightvolume`); color_layer tints a mask layer over it; preset picks a built-in diffuse scheme (infrared/pink/mono/blackbody/bipartite); min_elevation/max_elevation pin the height->ramp range, or leave compute_range on (default) to auto-press the SOP's Compute Range buttons so the ramp maps to the real elevation. | `input` (+8 optional) |
| `heightfield_maskbyfeature` | Mask terrain by one or more features (slope / height / facing direction / curvature) — isolate peaks, valleys, snow-line, plantable ground. | `input` (+17 optional) |
| `heightfield_maskbyocclusion` | Ambient-occlusion mask (cavities / crevices / sheltered ground) into the mask layer — occlusion is how much of a sphere around each voxel is blocked by nearby terrain (ray-cast). minexposure/maxexposure remap the occlusion band into the mask (below min->0, above max->1); dohemisphere samples only the upward (sky) hemisphere; viewdistance is the ray length (0=infinite, longer=more accurate/slower). | `input` (+9 optional) |
| `heightfield_maskbyshadow` | Mask the areas shadowed from a given sun direction (drives snow-melt, moss, sun/shade dressing). lightdir is the sun azimuth in degrees (0=light along +X, +90=along -Z); lightangle is the sun elevation in degrees (lower=longer shadows); opacity is the mask value in shadow; falloff feathers the shadow borders (0=hard). | `input` (+9 optional) |
| `heightfield_maskbyobject` | Mask a heightfield region from other geometry (input1, object-merged) into the mask layer — the 2D outline of surface geometry, or the intersection of a fog/SDF volume (for 3D-height projection use heightfield_project instead). method: ray (project a surface down) \| volume (fog) \| sdf; maskdir (ray method): project from both sides \| above \| below; maxdist is the max ray distance before a miss; value is the mask value where geometry hits; blurradius softens the mask. | `input` (+11 optional) |
| `heightfield_flatten` | Flatten a masked region of a heightfield (erase features, or level a building footprint). method: value = set masked area to `elevation` (setting elevation forces this mode); average = level to the masked area's own average; slope = smoothly interpolate the boundary (default; ignores elevation). mask_layer gates the flatten (0=untouched, 1=fully flat); blurradius softens the mask edge. | `input` (+5 optional) |
| `heightfield_maskbyconcavity` | Mask concave regions (riverbeds / valleys / gullies) into a mask layer — concavity is measured by sky visibility (rays cast from each voxel). concavity/maxconcavity set the masked band (add voxels whose concavity is >= concavity and <= maxconcavity); invert masks outside that band; combine merges with an existing mask; viewdistance is the ray length (longer=more accurate/slower). | `input` (+7 optional) |
| `heightfield_deform` | Deform geometry by a CHANGING heightfield: points rise/fall (and optionally rotate to the new slope) by the difference between the rest and current terrain — e.g. float packed props on a water surface, or apply an isostatic-rebound tilt. | `input` (+3 optional) |
| `heightfield_layer` | Per-layer utility on a named heightfield layer. op=clear sets every voxel of the layer to `value`. op=prop sets the layer's border-extension policy `border` (constant \| repeat \| streak \| sdf) — matters when tiling/merging fields. op=isolate copies the layer into `mask` (and optionally `height` via overwrite_height/overwrite_mask) so the default red-tint viewport shows it. | `input` (+7 optional) |
| `terrain_analysis` | Labs Terrain Analysis: write slope / curvature point attributes for scattering, pathfinding and shading. | `input` (+7 optional) |
| `add_tile_packed` | Load a baked .bgeo(.sc) tile as a packed-disk primitive (delay-loaded, near-zero display cost) into a new /obj geo — the memory-safe way to stream many terrain tiles. | `name`, `path` (+3 optional) |
| `set_tile_lod` | Flip one packed tile's viewport LOD (box proxy <-> full geometry) for a hero swap — targets the `packed_tile` File SOP created by add_tile_packed under the named /obj geo. | `name` (+1 optional) |
| `heightfield_noise` | Add procedural noise to a heightfield layer (full noise surface: combine, amp/scale/offset, basis+fractal, octaves, gain/bias, clipping, lattice/gradient warp). | `input` (+32 optional) |
| `heightfield_blur` | Blur / box-blur / expand / shrink / sharpen a heightfield layer. | `input` (+10 optional) |
| `heightfield_flowfield` | Rain onto a heightfield and slump the water downhill to compute flow / flow-direction layers (drives erosion masks, deposition, quick topographic valleys). | `input` (+15 optional) |
| `heightfield_project` | Raycast input geometry (object, object-merged onto input1) onto a heightfield layer as 3D height — stamp real geometry into the terrain (for a flat 2D outline mask use heightfield_maskbyobject). | `input` (+16 optional) |
| `heightfield_scatter` | Scatter tagged points across a heightfield using its mask layer (asset / instance placement, heightfield_scatter 2.0). | `input` (+45 optional) |
| `heightfield_terrace` | Cut stepped terraces / mesas into a heightfield (heightfield_terrace 2.0) with undulation noise and mesa/cliff slope masks. | `input` (+22 optional) |
| `heightfield_remap` | Remap a heightfield LAYER's value range (heightfield_remap) — rescale height/mask/any scalar layer from [input_min,input_max] to [output_min,output_max]: normalize a DEM to 0..1, boost mask contrast, invert a layer (swap output min/max), compress elevation. | `input` (+9 optional) |
| `heightfield_resample` | Resample a heightfield to a new resolution (heightfield_resample) — down-res a huge DEM for fast iteration, or up-res before erosion/export. resolution_scale multiplies current res (0.5=half, 2=double), or exact_resolution + division_mode for a precise target. | `input` (+7 optional) |
| `hf_combine_masks` | SideFX Labs Combine Masks — merges and post-processes heightfield MASK layers on the incoming heightfield (`input`, input 0). | `input` (+11 optional) |
| `hf_insert_mask` | SideFX Labs Insert Mask — copies a named MASK/height layer from a second heightfield (`mask`, input 1) into the base heightfield (`input`, input 0). | `input`, `mask` (+4 optional) |
| `terrain_segment` | SideFX Labs Terrain Segment — splits the incoming heightfield (`input`, input 0) into a tiles_x x tiles_y grid of meshed terrain tiles (its cooked SOP output IS the segmented geometry). doextrude+depth give solid skirts; flat bakes to a flat mesh; iterations drives the adaptive-density remesh. | `input` (+12 optional) |
| `terrain_texture` | SideFX Labs Terrain Texture — WIRE-ONLY terrain map baker: bakes normal / height / occlusion / cavity / curvature maps of the incoming terrain (`input`, input 0) to `outputdir`. | `input` (+15 optional) |
| `terrain_layer_export` | SideFX Labs Terrain Layer Export — WIRE-ONLY exporter SOP that writes the incoming heightfield (`input`, input 0) as Unreal/Unity landscape heightmap + paint-layer images to `output`. | `input` (+12 optional) |
| `terrain_layer_import` | SideFX Labs Terrain Layer Import — SOURCE node (0 inputs) that reads an Unreal/Unity landscape heightmap image (`sHeightmap`) into a fresh /obj heightfield. voxelsize sets the resulting HF resolution; bFlop flips row order. | `name` (+3 optional) |
| `biome_define` | SideFX Labs Biome Define — defines ONE biome's climate profile (name + average temperature/precipitation + soil flag) as a config point-stream. | 9 optional |
| `biome_plant_define` | SideFX Labs Biome Plant Define — defines ONE plant species and its climate tolerances (lower/preferred/upper temperature & precipitation), habit (Tree/Shrub), bounds/trunk radius, scale and max density — the record biome_scatter reads to place vegetation. | 27 optional |
| `biome_definitions_file` | SideFX Labs Biome Definitions File — serializes a biome library to / from JSON. | 6 optional |
| `biome_plant_definitions_file` | SideFX Labs Biome Plant Definitions File — serializes the plant-species library to / from JSON (mirror of biome_definitions_file for plant_define). | 6 optional |
| `biome_profile` | SideFX Labs Biome Profile — holds/writes the combined biome PROFILE (the biomeprofile.json that biome_initialize / region_assign / curve nodes consume) with per-biome average temperature & precipitation. | `name` (+4 optional) |
| `biome_initialize` | SideFX Labs Biome Initialize — the pipeline entry: takes a terrain and a biome-region source and outputs the prepared Terrain (output 0) + Biome Regions (output 1). | 28 optional |
| `biome_region_assign` | SideFX Labs Biome Region Assign — assigns the biome regions of the incoming region source (`input`, input 0) against the biome library, emitting Biome Regions (output 0) + Guide Geometry (output 1). | `input` (+25 optional) |
| `biome_attributes_evolve` | SideFX Labs Biome Attributes Evolve — evolves the climate attribute layers (temperature / precipitation / soil) across the incoming terrain (`input`, input 0) from physical rules: temperature drops with elevation (`lapserate`), precipitation is removed on the lee side of mountains (rain shadow: removebydir + rain_x/rain_z direction + anglespread), and soil is culled on cliffs (removebyslope + min/max slope) and by procedural noise (removebynoise + noise basis/fractal/amp/elementsize). | `input` (+34 optional) |
| `biome_attributes_to_terrain` | SideFX Labs Biome Attributes To Terrain — bakes the biome climate attributes onto the incoming terrain (`input`, input 0) as named heightfield layers (temperature / precipitation / soil / biome color) ready for downstream shading or export. | `input` (+12 optional) |
| `biome_curve_setup` | SideFX Labs Biome Curve Setup — tags an authored region CURVE (`input`, input 0 — a hand-drawn boundary) with the biome it belongs to (`biomename_curve`) and a sort order (`biomehierarchy`), producing the merged curve stream biome_region_assign reads in curves mode. | 5 optional |
| `biome_curve_label` | SideFX Labs Biome Curve Label — labels a region CURVE (`input`, input 0) directly with explicit climate values (temperature / precipitation / soil / biome color / sort order) instead of pulling them from a profile — the manual counterpart to biome_curve_setup. | 11 optional |
| `region_assignment_subutil` | SideFX Labs Region Assignment (subutility) — an internal plumbing helper used inside the biome region pipeline: it loops `lpcount` times over the incoming geometry (`input`, input 0), reading a named HDA parameter (`hda_parm`) per iteration and writing its value into a point/prim attribute (`attrib_name`), indexed by `index_parm`. | `input` (+5 optional) |
| `convert_regions_to_curves_subutil` | SideFX Labs Convert Regions To Curves (subutility) — converts region POLYGONS on the incoming geometry (`input`, input 0) into boundary CURVE primitives, one closed curve per region. | `input` (+2 optional) |

### Model & geometry

| Tool | What it does | Key params |
|---|---|---|
| `remesh` | Even-triangulation remesh (Remesh 2.0) — rebuild a triangulated / scan surface into well-shaped, evenly sized triangles for smoothing, simulation, or clean deformation. targetsize is the target edge length in world units (smaller = denser mesh, higher polycount); sizing=uniform gives one size everywhere, sizing=adaptive concentrates smaller triangles on curvature (density = adaptive target-density multiplier). gradation biases the uniform<->adaptive blend (0 uniform .. | `input` (+13 optional) |
| `polyreduce` | Decimate (PolyReduce 2.0) — collapse a mesh to a fraction of its polycount for LOD / real-time delivery while keeping silhouette and features. target chooses what the reduction targets: poly_percent / pt_percent (percentage, the default, via percentage) or poly_count / pt_count (an absolute finalcount — the LOD workhorse). qualitytolerance trades quality for speed. | `input` (+11 optional) |
| `boolean` | Boolean (mesh CSG) of A against B (boolean::2.0) — cut/combine solids. | `input` (+7 optional) |
| `sweep` | Sweep a cross-section along a backbone curve to make a SURFACE — the curve→geometry keystone: pipes, cables, ropes, rails, road/river ribbons, architectural trim. shape=tube\|square\|ribbon use a built-in profile (tube: radius; square/ribbon: width; cols sets density); shape=input sweeps your own cross_section SOP (input 1). | `input` (+15 optional) |
| `polyextrude` | Extrude polygon faces outward along their normals (polyextrude::2.0) — the workhorse for buildings from footprints, greebles, thickening. distance = push depth; inset shrinks the extruded cap inward; divisions adds side-wall loops; twist rotates the cap (degrees). | `input` (+19 optional) |
| `polybevel` | Bevel/round edges or points (polybevel::3.0) — the hard-surface edge-softening op (chamfers, fillets, weld seams). offset = fillet size; divisions = round segments (1 = flat chamfer, more = smoother round); shape picks the profile (round \| chamfer \| crease \| solid). | `input` (+8 optional) |
| `deform` | Single-node deformer, chosen by op: bend (bends the geometry along an axis, `amount` = angle°), twist (`amount` = twist strength°), mountain (displaces along normals by fractal noise, `amount` = height, `frequency` = noise element size), attribnoise (noise into an attribute, `amount` = amplitude, `frequency` = element size), lattice (cage-warp, set divsx/divsy/divsz), peak (push points along normals, `amount` = distance). | `input` (+7 optional) |
| `drape` | Project/drape the input points onto a collision surface — settle scattered props, curves, or a grid onto terrain. | `input` (+5 optional) |
| `transform` | Move / rotate / scale 3D GEOMETRY in the scene (Transform SOP) — position an object or a point/prim group in 3D space. translate, rotate (deg), uniform + per-axis scale, pivot, group restriction, transform/rotate order. | `input` (+15 optional) |
| `select_group` | Bounded selection then delete-inverse; bbox keeps geometry inside, else pattern selects a named group. | `input` (+4 optional) |
| `merge` | Merge several SOPs into one stream. | `inputs` (+1 optional) |
| `switch` | Output ONE of several inputs, selected by an integer index — variant/LOD assembly and A/B toggles. | `inputs` (+2 optional) |
| `null` | No-op passthrough / named waypoint — the LANDMARK convention: plant a null after each meaningful result and name it OUT_<name> (a stable result handle; downstream object_merge/refs target the NAME, so inserting nodes above never breaks them), IN_<name> (an external-geo entry), or CONTROL (driver parms / spare input). | `input` (+1 optional) |
| `sort` | Deterministically reorder points and/or prims — stable ids for copy-stamp / instancing determinism. | `input` (+7 optional) |
| `polysplit_loop` | Insert parametric edge LOOP(s) (polysplit::2.0 Edge-Loop mode) — add supporting/control loops while keeping quads. | `input`, `seed_edge` (+3 optional) |
| `poly_split` | Cut a FREEFORM edge path across faces (polysplit::2.0 Shortest-Distance mode) — route a new edge run 'up and over' n-gons / boolean seams to recover quads, the mechanical-retopo primitive. | `input`, `path` (+6 optional) |
| `copy_transform` | Copy-and-Transform (copyxform): N copies of the input, each with a CUMULATIVE incremental transform (copy i gets i× the translate/rotate/scale). | `input` (+14 optional) |
| `helix` | Create a fresh /obj geo with a helix / coil curve (spiral SOP) — the spring / coil / thread generator (ejector-rod spring, bolt thread, DNA strand, spiral guide). turns=revolutions, height=axial rise (0=flat spiral), start/end_radius taper the coil. | `name` (+8 optional) |
| `polywire` | Surface a curve / wire into solid tube geometry (polywire) — springs, cables, pipes, ropes, wireframe renders, neurons, branches. divisions=cross-section sides (min 3), segments=subdivisions along the span, joint_correct prevents buckling where wires meet. | `input` (+9 optional) |
| `convex_decompose` | Approximate CONVEX DECOMPOSITION (convexdecomposition) — break a concave mesh into a set of convex hull pieces, the standard way to make cheap RBD/physics COLLISION PROXIES (a convex hull is far cheaper to collide than a concave mesh, and most solvers want convex colliders). max_concavity (0..1) trades fit vs count: lower = tighter + MORE hulls, higher = fewer/looser. output=hulls (convex pieces, default) \| segments (original surface partitioned + tagged). per_piece decomposes each `piece_attrib` island (e.g. | `input` (+10 optional) |
| `set_color` | Assign a constant color. | `input` (+3 optional) |
| `uv` | UV via mode: project (uvproject), unwrap (uvunwrap auto), layout (uvlayout::3.0 atlas packing), transform (uvtransform), or flatten (uvflatten::3.0 seam-driven). | `input` (+17 optional) |
| `uv_transfer` | Transfer a UV set from a SOURCE mesh onto the input geometry — restore UVs a topology change (remesh/quad_remesh/polyreduce) destroyed. | `input`, `source` (+5 optional) |
| `create_primitive` | Create a fresh /obj geo with a primitive SOP (box/grid/sphere/tube/line/circle/platonic/torus) — the starting block for hard-surface + organic modelling. | `name` (+10 optional) |
| `skin` | Loft/skin a surface across ordered profile curves — input is a SOP holding several profile primitives (merge parallel curves first); skin lofts across them in prim order. output_polygons=false yields a spline mesh; v_wrap=wv closes the loft into a loop. | `input` (+10 optional) |
| `revolve` | Lathe a profile curve around an axis → a surface of revolution (vase, tube, bottle, wheel, lampshade). axis+origin define the spin axis (default Y through origin); divisions = sides; revolve_type=openarc\|closedarc + angle=[start,end] make a partial arc; caps closes the ends. | `input` (+11 optional) |
| `mirror` | Reflect geometry across a plane and (by default) weld the seam. axis=x\|y\|z is a shortcut for the plane normal (or give dirx/diry/dirz + originx/originy/originz); dist offsets the plane. keep_original=false replaces with only the mirror; weld fuses the seam; operation=clip cuts at the plane instead of reflecting. | `input` (+15 optional) |
| `dissolve` | Dissolve an edge (or point) group, MERGING the adjacent faces — topology simplification (unlike blast, which deletes and leaves a hole). | `input`, `group` (+6 optional) |
| `bridge` | Bridge two edge loops into a connecting tube/skirt (polybridge). | `input`, `src_group`, `dst_group` (+12 optional) |
| `pointdeform` | Wrap-deform input by the motion of a cage: rest_cage (input1) → deformed_cage (input2). | `input`, `rest_cage`, `deformed_cage` (+7 optional) |
| `crease` | Write creaseweight on an edge group so a downstream subdivide keeps those edges SHARP — the key to credible subdivision-surface hard-surface modeling. group = edge group, weight = crease value (0..10), op = addto\|set\|delete. | `input` (+5 optional) |
| `divide` | Divide/triangulate polygons. triangulate (convex, default on) with max_sides; smooth (Catmull-style subdivide) with divisions; brick=true + brick_size=[x,y,z] tiles the mesh; compute_dual builds the dual mesh; remove_shared_edges merges. | `input` (+10 optional) |
| `polyexpand2d` | Offset 2D curves into variable-width outlines/ribbons — roads from OSM curves, panel lines, insets. input = a 2D curve SOP. offset = half-width; output=curves\|surfaces; inside/outside pick which side(s) to emit; width_attrib names a per-point attribute for variable width. | `input` (+10 optional) |
| `lsystem` | Create a fresh /obj geo with an L-system (procedural branching curves or swept tubes — trees, coral, lightning, growth). premise = the axiom; rules = a list of 'A=...' production strings (an INERT turtle grammar, NOT code); generations/angle/step/thickness are typed scalars; output=skel\|tube. | `name` (+10 optional) |
| `create_curve` | Create a fresh /obj geo holding a curve built from caller-supplied points. | `name`, `points` (+3 optional) |
| `tree_trunk_generator` | SideFX Labs Tree Trunk Generator — the ROOT of the modular tree chain. | `name` (+24 optional) |
| `tree_controller` | SideFX Labs Tree Controller — a SOURCE node (0 inputs, 1 output) holding tree-wide settings (gravity / bend / light tropism, seam booleaning, LOD). | `name` (+18 optional) |
| `tree_branch_generator` | SideFX Labs Tree Branch Generator — THE workhorse: grows one level of lateral branches off a parent. | `input` (+30 optional) |
| `tree_simple_leaf` | SideFX Labs Tree Simple Leaf — builds a fresh /obj geo holding ONE leaf (or needle) template card; wire its output into tree_leaf_generator's `leaf` input to scatter it over the tree. bend=0 gives a flat needle. | `name` (+11 optional) |
| `tree_leaf_generator` | SideFX Labs Tree Leaf Generator — the chain terminus: scatters the leaf template over the branches. | `input` (+21 optional) |
| `quick_basic_tree` | SideFX Labs Quick Basic Tree — one-call convenience tree grown from `input` (a base surface / point set), complementing the modular chain. | `input` (+15 optional) |
| `maps_baker` | SideFX Labs Maps Baker — WIRE-ONLY LOD-atlas texture bake. | `input` (+28 optional) |
| `capsule` | SideFX Labs Capsule — a fresh /obj geo holding a capsule primitive (a cylinder body with two hemispherical caps). radius/height size it, sides sets radial resolution, bodysegments/capsegments the lengthwise resolution, direction the long axis. | `name` (+6 optional) |
| `cylinder_generator` | SideFX Labs Cylinder Generator — a fresh /obj geo holding a procedural cylinder/cone/tube with more control than the native tube. uniformradius ties top+base to radius; disable it to taper via topradius/baseradius. sides/divisions set resolution; opencylinder + arcstart/arcend cut an open arc; endcaps + fillmode cap the ends. | `name` (+14 optional) |
| `disc_generator` | SideFX Labs Disc Generator — a fresh /obj geo holding a flat disc / ring / annulus. innerradius>0 makes a ring/washer; outerradius is the rim. sides/divisions set resolution; arcstart/arcend cut a pie wedge; orientation picks the plane; innerheight/outerheight loft it into a shallow cone/funnel. | `name` (+10 optional) |
| `hexagon_grid` | SideFX Labs Hexagon Grid — a fresh /obj geo holding a hex-tiled grid. type=polygon builds hex faces (mesh); type=points outputs just the hex centers. gridshape sets the footprint (hexagon/triangle/rectangle/parallelogram), gridsize its extent, cellradius the per-hex size, cellorientation pointy vs flat top, orientation the plane. connectivity=connected fuses shared edges. | `name` (+7 optional) |
| `quad_sphere_generator` | SideFX Labs Quad Sphere Generator — a fresh /obj geo holding a quad-only (subdivided-cube) sphere with clean even topology (unlike the pole-pinched native sphere). subdivisions is EXPONENTIAL in polycount (6*4^n quads) and is hard-clamped to <=7. | `name` (+3 optional) |
| `simple_shapes` | SideFX Labs Simple Shapes — a fresh /obj geo holding one of a family of 2D profile shapes selected by `shape` (triangle/diamond/rectangle/trapezoid/polygon/star/double_star/square_star). base/height size the rectangular family; radius/sides/points/innerradius drive the polygon & star families. closed closes the profile into a face; adduvs adds UVs. | `name` (+11 optional) |
| `superformula_shapes` | SideFX Labs Superformula Shapes — a fresh /obj geo holding a 2D shape from the superformula family, selected by `shapeselect` (square/circle/triangle/polygon/diamond/star/squircle/rounded_polygon/clover/flower/sunburst/eye/teardrop/heart/custom). width/height size it; circpointnum sets circle/curve resolution; polysides/starspokes+starpinchbloat/flowerspokes drive the polygon/star/flower families. fillshape fills the profile into a surface (otherwise an outline curve); roundcorners bevels corners. | `name` (+10 optional) |
| `quadrangulate` | SideFX Labs Quadrangulate (labs::quadrangulate::2.0) — converts a triangulated mesh into quads by merging triangle pairs (topology-preserving; NOT a full rebuild like quad_remesh). | `input` (+8 optional) |
| `voxelmesh` | SideFX Labs VoxelMesh (labs::voxelmesh::2.0) — rebuilds `input` (input 0) into a watertight mesh by rasterizing it to a VDB at `resolution` voxels across the longest axis, then meshing the surface (a volume-based remesh, distinct from the native surface remesh). | `input` (+11 optional) |
| `connect_polygon_neighbours` | SideFX Labs Connect Polygon Neighbours (labs::connect_polygon_neighbours::1.0) — emits a point at each polygon centroid of `input` (input 0) and (default mode) polyline edges linking face-adjacent neighbours — the dual/adjacency graph of the mesh. | `input` (+6 optional) |
| `edge_group_to_polylines` | SideFX Labs Edge Group to Polylines (labs::edge_group_to_polylines::1.0) — extracts the edges named by `edgegroup` from `input` (input 0) as individual polyline primitives. | `input` (+2 optional) |
| `edgegroup_to_curve` | SideFX Labs Edge Group to Curve (labs::edgegroup_to_curve::1.1) — like edge_group_to_polylines but stitches the edges named by `group` into connected, ordered curves (chains shared endpoints). | `input` (+8 optional) |
| `symmetrize` | SideFX Labs Symmetrize (labs::symmetrize) — mirrors `input` (input 0) across the plane defined by `origin` + `direction` (normal) and welds the halves into a symmetric mesh. | `input` (+9 optional) |
| `thicken` | SideFX Labs Thicken (labs::thicken::1.1) — gives a surface / open shell thickness by extruding it along its normals by `depth` and bridging the walls (solidify). | `input` (+10 optional) |
| `boolean_curve` | SideFX Labs Boolean Curve — 2D/curve boolean of two curve inputs. | `input` (+5 optional) |
| `curve_branches` | SideFX Labs Curve Branches — scatters child branch curves along the input curve(s) (input 0). | `input` (+14 optional) |
| `curve_resample_by_density` | SideFX Labs Curve Resample by Density — resamples the input curve (input 0) with a non-uniform point density. | `input` (+5 optional) |
| `curve_sweep` | SideFX Labs Curve Sweep — sweeps a cross-section along the backbone curve (input 0) to build a tube/ribbon. | `input` (+6 optional) |
| `merge_splines` | SideFX Labs Merge Splines — fuses/merges overlapping spline curves into a connected network. | `input` (+5 optional) |
| `polywire_uv` | SideFX Labs PolyWire UV — builds UV'd polywire tubes around an edge network or curve (input 0). | `input` (+11 optional) |
| `progressive_resample` | SideFX Labs Progressive Resample — evenly resamples the input curve (input 0) with a progressive segment length driven by a per-point `pscale` attribute. | `input` (+5 optional) |
| `spiral` | SideFX Labs Spiral — a SOURCE node (0 inputs): builds a fresh /obj geo holding a spiral / helix curve. | `name` (+7 optional) |
| `sweep_geometry` | SideFX Labs Sweep Geometry — instances/sweeps a cross-section MESH along a backbone curve. | `input`, `curve` (+11 optional) |
| `view_vertex_order` | SideFX Labs View Vertex Order — annotates the input geometry (input 0) with a vertex-order visualization: per-element color plus optional order arrows, passing the source geometry through. | `input` (+5 optional) |
| `box_clip` | SideFX Labs Box Clip — clips `input` (input 0) against an axis-aligned box, keeping the geometry that survives the enabled side planes (each neg*/pos* toggle turns one of the six clip planes on; all six default ON). size/center (vec3 via _x/_y/_z) and scale size and place the clip box — make it LARGER than the geometry to keep everything, smaller to trim. fillholes caps the cut. | `input` (+16 optional) |
| `boxcutter` | SideFX Labs BoxCutter — a boolean box cutter for `input` (input 0): subtracts, shatters or unions a transformable box against the mesh. boolean_op picks the operation; bevel_divisions/bevel_distance round the cutting box; translate/rotate/scale (vec3 via _x/_y/_z) place and size it; copies (+ copy_translate/copy_rotate vec3) array the cut. | `input` (+20 optional) |
| `boxcutter_subutil` | SideFX Labs BoxCutter Sub-Utility — the single-shape boolean box cutter underlying boxcutter, usable standalone on `input` (input 0). operation picks subtract/shatter/union; translate/rotate/scale (vec3 via _x/_y/_z) place the box; distance extrudes the cut, divisions bevel its corners; copies (+ copy_translate/copy_rotate vec3) array it. active toggles it; passes the mesh through when inactive. | `input` (+21 optional) |
| `mesh_slice` | SideFX Labs Mesh Slice — slices `input` (input 0) with an axis-aligned grid of cutting planes (divisions_x/_y/_z planes per axis) and (with fill_holes) caps the cuts, producing separable pieces. isolate_index + index keep only one piece. | `input` (+7 optional) |
| `polyslice` | SideFX Labs PolySlice — slices `input` (input 0) with num_slices parallel planes, positioned/oriented by center (vec3), size (vec3), scale and rotate (vec3). mode outputs sliced polys or polyline cross-sections. connectivity decides how sliced pieces are grouped; divide_convex triangulates resulting non-convex faces. | `input` (+25 optional) |
| `split_prim_by_normal` | SideFX Labs Split Prim by Normal — selects the primitives of `input` (input 0) whose normal points along `axis` in the chosen `direction`, within spread_angle degrees; invert flips the selection. | `input` (+5 optional) |
| `polyscalpel` | SideFX Labs PolyScalpel — slices the source mesh `input` (input 0) wherever the required `cutter` geometry (input 1) crosses it. cutting_geo_type MUST match the cutter's type (points / polylines / polygon_surfaces); input_geo_type matches the source. surface_output picks points-on-edges vs sliced surfaces; slicing_method picks the exact PolySplit or the faster Boolean-Shatter path. source_group/cutting_group are geometry-group NAMES limiting each side. | `input`, `cutter` (+14 optional) |
| `calculate_occlusion` | SideFX Labs Calculate Occlusion — ambient-occlusion / cavity analysis: ray-casts against the surface (and an optional `occluder` on input 1) and writes an occlusion value into point attribute `occattr` (plus a display `Cd` when `colorout` is on). | `input` (+14 optional) |
| `calculate_slope` | SideFX Labs Calculate Slope — computes surface slope (angle of each point's normal from the up axis) into point attribute `sSlopeAttribute` (plus a display `Cd` when `bSlopeCd` is on). | `input` (+8 optional) |
| `calculate_thickness` | SideFX Labs Calculate Thickness — measures local mesh thickness by casting `numrays` inward rays per point and writes the distance into point attribute `attrname` (default `thickness`; plus a display `Cd` when `outputcolor` is on). | `input` (+10 optional) |
| `distance_from_border` | SideFX Labs Distance From Border — for each point computes the distance to the nearest open boundary/border edge and writes it into point attribute `distattr` (plus a display `Cd` when `bDistanceAsColor` is on). | `input` (+11 optional) |
| `edge_color` | SideFX Labs Edge Color — writes a display `Cd` that highlights convex vs concave edges (a wear/curvature visualization used to drive edge-damage masks). | `input` (+8 optional) |
| `fast_gaussian_curvature` | SideFX Labs Fast Gaussian Curvature — computes discrete Gaussian curvature (angle defect) into point attribute `attribname_curv` (default `curvature`) plus an angle into `attribname_angle`. | `input` (+11 optional) |
| `measure_curvature` | SideFX Labs Measure Curvature — measures surface curvature into point attributes `convexityattr` (default `convexity`) and `concavityattr` (default `concavity`), plus a display `Cd` when `viscolor` is on. | `input` (+13 optional) |
| `physical_ambient_occlusion` | SideFX Labs Physical Ambient Occlusion — a physically-based AO bake into point attribute `outputattrib` (default `ao_mask`; plus a display `Cd`). | `input` (+18 optional) |
| `spectral_feature_extract` | SideFX Labs Spectral Feature Extract — spectral (diffusion/PDE) feature analysis: extracts multi-scale features from an input point attribute and writes point attributes `outattrib_f` (default `extracted_float`) and `outattrib_v` (default `extracted_vec`). | `input` (+19 optional) |
| `validate_geometry_type` | SideFX Labs Validate Geometry Type — a pipeline GUARD: passes the input geometry through unchanged while asserting a rule about it, raising a message/warn/error if the rule fails. | `input` (+5 optional) |
| `autouv` | SideFX Labs Auto UV — one-click automatic UV: auto-seams the mesh, flattens each island (SCP/ABF), then packs them into an atlas. | `input` (+25 optional) |
| `uv_unwrap_cylinder` | SideFX Labs UV Unwrap Cylinder — cylindrical UV unwrap for pipes / tubes / limbs. | `input` (+7 optional) |
| `inside_face_uvs` | SideFX Labs Inside Face UVs — flatten UVs onto the interior ("inside") faces of a fractured mesh so the fracture interior can be textured. | `input` (+9 optional) |
| `automatic_trim_texture` | SideFX Labs Automatic Trim Texture — non-interactively fit the mesh's UV islands onto a trim-sheet atlas. | `input`, `trim` (+10 optional) |
| `calculate_uv_distortion` | SideFX Labs Calculate UV Distortion — measure how much the UV layout stretches/squashes each element vs 3D and write it to `distortionattribute` (default uv_distortion). | `input` (+5 optional) |
| `merge_small_islands` | SideFX Labs Merge Small Islands — merge UV islands whose relative area is below `cutoff` into an adjacent island and re-flatten, reducing island count for cleaner packing. | `input` (+7 optional) |
| `remove_uv_distortion` | SideFX Labs Remove UV Distortion — iteratively relax UV stretching by pushing distorted vertices ("peaks") in / pulling squashed ones ("holes") out. | `input` (+13 optional) |
| `texel_density` | SideFX Labs Texel Density — measure and (optionally) equalize texels-per-unit across a UV'd mesh for a given `texturesize`. | `input` (+9 optional) |
| `uv_remove_overlap` | SideFX Labs UV Remove Overlap — detect UV islands overlapping in the 0-1 tile (rasterized at `resolution`) and, when `repairoverlaps` is on, nudge them apart; optionally groups the offending prims. | `input` (+6 optional) |
| `uv_unitize` | SideFX Labs UV Unitize — remap each primitive (or each UV island) so its UVs fill the 0-1 unit square — standard prep for trim-sheet / tiling-texture workflows. | `input` (+8 optional) |
| `building_from_patterns` | SideFX Labs Building From Patterns — arranges building MODULES over a blockout using a floor/module pattern grammar. | `input` (+17 optional) |
| `building_generator` | SideFX Labs Building Generator — slices a 3D blockout into floors and skins it with modules. | `input` (+20 optional) |
| `building_module` | SideFX Labs Building Module (labs::building_generator_utility) — tags an input mesh as a reusable building MODULE (name, weight, priority, bounding box) for building_generator / building_from_patterns to consume. | `input` (+9 optional) |
| `pathfinding_global` | SideFX Labs Pathfinding Global — computes least-cost PATHS between settlement endpoints over a terrain. | `input`, `terrain` (+12 optional) |
| `road_generator` | SideFX Labs Road Generator — builds road-surface mesh with intersections from input road CURVES (centerlines). | `input` (+19 optional) |
| `settlement_connections` | SideFX Labs Settlement Connections — connects settlement POINTS into a road-network graph, filtering connections by angle / distance / count. | `input` (+13 optional) |
| `cable_generator` | SideFX Labs Cable Generator — builds hanging cable / wire meshes. | `input` (+26 optional) |
| `lot_subdivision` | SideFX Labs Lot Subdivision — recursively subdivides a 2D polygon block into building LOTS. | `input` (+11 optional) |
| `scifi_panels` | SideFX Labs Sci-Fi Panels — greebles a mesh with paneling: subdivides the surface into lots then extrudes bordered panels with notches / bevels. | `input` (+22 optional) |
| `simple_rope_wrap` | SideFX Labs Simple Rope Wrap — sweeps rope/cable geometry over polygon surfaces and wraps it around a geometry object. | `input`, `geometry` (+20 optional) |
| `mesh_tiler` | SideFX Labs Mesh Tiler — wraps PACKED geometry that crosses a unit-tile boundary so it tiles seamlessly (pieces exiting one edge re-enter the opposite edge). | `input` (+9 optional) |
| `dirtskirt` | SideFX Labs Dirt Skirt — builds a scattered dirt/debris skirt where an object (`input`, input 0) meets a ground surface (`ground`, input 1) — the little pile of rubble at a rock/wall base. obj* controls the noise band riding up the object; gnd* the band spreading on the ground; finalcount caps the scattered debris count; iterations grows the band; threshold trims it. | `input`, `ground` (+17 optional) |
| `snow_buildup` | SideFX Labs Snow Buildup — accumulates a snow shell on the upward-facing parts of the incoming surface (`input`, input 0). angle is the max face slope that holds snow; baseheight/snowheight set the depth; typenoise picks the surface look (drifts / melted / shoveled); smoothiterations softens it. snow_only outputs just the snow group. | `input` (+20 optional) |
| `tree_branch_placer` | SideFX Labs Tree Branch Placer — grows/places branches off a parent trunk. | `input` (+25 optional) |
| `tree_hierarchy` | SideFX Labs Tree Hierarchy — tags the branches of a tree with a named generation/branch hierarchy (e.g. gen_0/_branch_1) for downstream selection, wind, or export. | `input` (+6 optional) |
| `cluster_refine` | SideFX Labs Cluster Refine — refines a mesh into welded islands by clustering connected regions and relaxing the cluster boundaries so seams read cleanly. | `input` (+8 optional) |
| `edge_damage` | SideFX Labs Edge Damage — chips/erodes hard edges to add procedural wear via a VDB pass; all displacement is procedural along normals, NOT from a disk image. | `input` (+14 optional) |
| `edge_smooth` | SideFX Labs Edge Smooth — relaxes/smooths mesh edges (optionally only unshared/boundary edges), cleaning faceting on beveled or booleaned geometry. | `input` (+7 optional) |
| `mesh_sharpen` | SideFX Labs Mesh Sharpen — sharpens surface features by pushing points along a curvature field, with an optional smoothing pass; accentuates scanned/soft geometry. | `input` (+12 optional) |
| `soften_normals` | SideFX Labs Soften Normals — recomputes vertex normals with a cusp angle so edges below the angle read smooth and sharper edges stay hard; can additionally harden normals across UV seams. | `input` (+3 optional) |
| `extract_borders` | SideFX Labs Extract Borders — extracts the open boundary edges of a mesh (and optionally the UV-island borders) as polylines or curves. | `input` (+4 optional) |
| `extract_silhouette` | SideFX Labs Extract Silhouette — traces the outer silhouette of a mesh along a view axis and emits it as a curve (cutout cards / trim shapes). | `input` (+6 optional) |
| `straight_skeleton_2d` | SideFX Labs Straight Skeleton 2D — computes the 2D straight skeleton (medial-axis-like topological spine) of a planar polygon/curve, useful for roof/insetting and shape analysis. | `input` (+7 optional) |
| `straight_skeleton_3d` | SideFX Labs Straight Skeleton 3D — extracts a 3D straight-skeleton / medial curve network of a closed mesh via a voxelized solve. | `input` (+5 optional) |
| `dissolve_flat_edges` | SideFX Labs Dissolve Flat Edges — removes edges between (near-)coplanar faces to simplify a mesh without changing its silhouette, and optionally removes inline (colinear) points. | `input` (+8 optional) |
| `remove_inside_faces` | SideFX Labs Remove Inside Faces — deletes interior/occluded faces never visible from outside (e.g. overlapping booleaned kit-bash geometry), reducing poly count. | `input` (+6 optional) |
| `path_deform` | SideFX Labs Path Deform — bends `input` (input 0, the mesh) along the required `curve` (input 1, the path); optional `banking_curve` (input 2) sets the up/banking direction. | `input`, `curve` (+12 optional) |
| `polydeform` | SideFX Labs PolyDeform — deforms the high-detail `input` (input 0, source_mesh) to follow the sculpted/edited `target` (input 1, target_mesh), transferring the low-res deformation onto the full-res mesh. | `input`, `target` (+10 optional) |
| `sine_wave` | SideFX Labs Sine Wave — displaces `input` (input 0) with two summed sine waves along `axis` (X\|Y\|Z). | `input` (+14 optional) |
| `decal_projector` | SideFX Labs Decal Projector — projects a decal (base-color + height map) onto the surface `input` (input 0, the Projection Mesh). | `input` (+21 optional) |
| `detail_mesh` | SideFX Labs Detail Mesh — tiles the stamp/detail mesh `tile` (input 1) across the UV layout of the surface `input` (input 0, the canvas), wrapping the tiles onto it (e.g. bricks/shingles over a wall). | `input`, `tile` (+10 optional) |
| `triplanar_displace` | SideFX Labs Triplanar Displace — displaces `input` (input 0) by sampling a displacement `texture` triplanar-projected onto the mesh (no UVs needed). | `input` (+22 optional) |
| `align_and_distribute` | SideFX Labs Align and Distribute — splits `input` (input 0) into pieces (by `split_by` connectivity or a piece `attribute_name`), optionally `sort_by` (area/polycount/random with `seed`), then lays them out with `spacing` in a `layout` (linear\|grid). | `input` (+14 optional) |
| `delight` | SideFX Labs Delight — removes baked-in lighting/AO from the vertex colors (Cd) of `input` (input 0), flattening a scanned/photographed mesh toward even albedo. | `input` (+11 optional) |
| `straighten` | SideFX Labs Straighten — reorients `input` (input 0) into a canonical axis-aligned frame using a selected `up_group` (and optionally a `forward_group` when `align_forward` is on) of the given `grouptype` (primitive\|point\|edge) as the up/forward reference; `invert_up` flips the up axis. | `input` (+8 optional) |
| `axis_align` | SideFX Labs Axis Align — repositions `input` (input 0) relative to the origin per axis: each of `x`/`y`/`z` chooses to leave that axis unchanged or snap its bounding-box Center, Min or Max to 0. | `input` (+5 optional) |
| `turntable` | SideFX Labs Turntable — rotates `input` (input 0) about `axis` (X\|Y\|Z) as a function of the current frame, completing `num_turns` full rotations over the frame range (a turntable preview animation). | `input` (+4 optional) |
| `chaotic_shapes` | SideFX Labs Chaotic Shapes — a fresh /obj geo holding a point cloud traced from a chaotic (strange-attractor) system. | `name` (+8 optional) |
| `mandelbulb_generator` | SideFX Labs Mandelbulb Generator — a fresh /obj geo holding a 3D Mandelbulb fractal. | `name` (+10 optional) |
| `wang_tiles_sample` | SideFX Labs Wang Tiles Sample — a fresh /obj geo holding a stochastic Wang-tile sampling (an aperiodic tiling seed set that the Wang Tiles Decoder later expands). | `name` (+3 optional) |
| `wfc_initialize` | SideFX Labs WFC Initialize — a fresh /obj geo holding a blank Wave-Function-Collapse grid (`rows` x `cols`, each clamped <=1024) that the WFC sample/paint tools then solve. | `name` (+4 optional) |
| `wang_tiles_decoder` | SideFX Labs Wang Tiles Decoder — decodes a Wang-tile point grid (`input`, input 0; e.g. a wang_tiles_sample output) into a `rows` x `cols` aperiodic tiling. | `input` (+6 optional) |
| `connectivity_and_segmentation` | SideFX Labs Connectivity and Segmentation — partitions the input polygons (`input`, input 0) into segments and writes a segment id to `segmentattrib`. | `input` (+15 optional) |
| `multi_bounding_box` | SideFX Labs Multi Bounding Box — builds bounding boxes over the input mesh (`input`, input 0). | `input` (+5 optional) |
| `wavefunction_collapse_2d` | SideFX Labs 2D Wave Function Collapse — synthesises a larger 2D tiling that locally resembles a small colour/tile sample. | `input`, `sample` (+9 optional) |
| `wfc_sample_paint` | SideFX Labs WFC Sample Paint — the paint front-end of the Wave-Function-Collapse workflow: `input` (input 0) = the WFC grid (a wfc_initialize output); optional `modules` (input 1) = the tile/module set. | `input` (+6 optional) |
| `unreal_worldcomposition_prepare` | SideFX Labs Unreal World Composition Prepare — tag an incoming terrain/mesh (`input`, input 0) for Unreal World Composition; the cooked SOP output IS the tagged geometry. tilenum sets the tile count; levelpath/materialpath are Unreal CONTENT paths written as string attributes (not filesystem paths). | `input` (+12 optional) |
| `ml_cv_directory_import` | SideFX Labs ML CV Directory Import — a SOURCE node (0 inputs) that imports asset geometry from a directory matching a filename pattern; the entry point for computer-vision synthetic-data staging. | `name` (+4 optional) |
| `ml_cv_keypoint_metadata` | SideFX Labs ML CV Keypoint Metadata — assigns keypoint ground-truth metadata (keypoint radius, 3D positions, skeleton connectivity) to the input geo for pose-estimation training data. | `input` (+7 optional) |
| `ml_cv_label_metadata` | SideFX Labs ML CV Label Metadata — tags geometry (or a group) with a category ID/name plus an optional instance ID for segmentation/detection training. | `input` (+10 optional) |
| `ml_cv_promote_synth_attribute` | SideFX Labs ML CV Promote Synth Attribute — promotes a synthetic-data attribute from one geometry class to another (e.g. primitive -> point) with a chosen aggregation method, so labels land on the right elements. | `input` (+6 optional) |
| `ml_cv_rop_annotation_output` | SideFX Labs ML CV Annotation Output — WIRE-ONLY writer that exports COCO-style JSON annotations (category/instance IDs, bounding data) for the input synthetic frame. | `input` (+10 optional) |
| `ml_cv_texture_mask` | SideFX Labs ML CV Texture Mask — assigns a texture instance ID and a category ID/name to the input geometry so a rendered texture region becomes a labelled mask in the synthetic dataset. | `input` (+4 optional) |
| `ml_cv_vector_data` | SideFX Labs ML CV Vector Data — computes per-point vector data (e.g. a screen-space motion/direction vector from a source point) for the synthetic frame. | `input` (+5 optional) |
| `ml_cv_visualize_keypoints` | SideFX Labs ML CV Visualize Keypoints — builds keypoint / skeleton-connectivity guide geometry from keypoint-metadata geo for inspecting synthetic-data labels. | `input` (+6 optional) |
| `export_uv_wireframe` | SideFX Labs Export UV Wireframe — WIRE-ONLY: renders the input mesh's UV layout (wireframe + island fill) to an image file. | `input` (+10 optional) |
| `udim_tile_number` | SideFX Labs UDIM Tile Number — computes the UDIM tile number for each element from its UVs and writes it to an attribute (default `udim_tile`). | `input` (+5 optional) |
| `visualize_uvs` | SideFX Labs Visualize UVs — builds inspection geometry for a mesh's UVs: applies a checker texture-map preview and can draw the UV islands + seams. | `input` (+9 optional) |
| `testgeometry_luiz` | SideFX Labs Test Geometry (Luiz) — a SOURCE node (0 inputs) that builds a ready-made test/showcase mesh (the 'Luiz' asset) for prototyping. | `name` (+1 optional) |
| `testgeometry_paul` | SideFX Labs Test Geometry (Paul) — a SOURCE node (0 inputs) that builds a ready-made test/showcase mesh (the 'Paul' asset) for prototyping. | `name` (+1 optional) |
| `houdini_icon` | SideFX Labs Houdini Icon — a SOURCE node (0 inputs) that builds the Houdini logo as mesh geometry, optionally extruded. | `name` (+2 optional) |
| `simple_retime` | SideFX Labs Simple Retime — retimes an animated input by a global speed multiplier (the per-frame retime Ramp stays at its HDA default). | `input` (+2 optional) |
| `resample` | Resample curves/polylines to even segments (resample SOP). | `input` (+14 optional) |
| `trail` | Motion trail / connectivity over time (trail SOP): trail points across frames, connect them as mesh/polys, or compute velocity from motion. | `input` (+14 optional) |
| `timeshift` | Re-time the upstream geometry — evaluate the input SOP as if the playbar were at a different frame/time (timeshift SOP). method=byframe reads `frame` (with integer_frames snapping); method=bytime reads `time` in seconds. clamp holds the sample at the first/last frame outside a range. | `input` (+6 optional) |
| `polyframe` | Build a per-element orientation frame — tangent (tangentu), normal (N), bitangent (tangentv) attributes — on a curve or surface (polyframe SOP). | `input` (+13 optional) |
| `fuse` | Weld / snap coincident points (Fuse 2.0) — the seam-cleanup workhorse after heightfield_tilesplit, boolean, or scan-tile merges. distance is the 3D snap tolerance (world units): points within it are consolidated into one, closing cracks between tiles. snap_type selects distancesnap (proximity, the default), gridsnap (snap to a grid), or specified (snap via a target attribute). delete_degenerate drops the zero-area/length prims that collapse out when points merge; delete_unused removes now-orphaned points; consolidate merges the snapped points into single points (default on). | `input` (+6 optional) |
| `normals` | Recompute (or reverse) normals via the Normal SOP. mode = which class the N attribute is written to: point (smooth shading, default), vertex (per-face-corner, hard/soft edges), prim (flat per-face) or detail. cusp_angle (degrees) splits smooth vs faceted shading at edges sharper than the angle. reverse flips the normal direction (fix inside-out scan/boolean surfaces); normalize forces unit length; weighting picks how adjacent-face normals are averaged (0 by-area .. | `input` (+6 optional) |
| `facet_smooth_subdiv` | Three surface operators multiplexed by op. facet (Facet SOP): re-facet / consolidate — cusp_angle sharpens edges, unique_points splits shared points (hard faceted look), make_planar flattens each face. smooth (Smooth SOP): relax point positions without adding polygons — strength is the smoothing amount (0..50), method uniform\|scaledominant\|curvaturedominant, filter_quality raises pass count (1..5). subdivide (Subdivide SOP): ADD polygons — iterations subdivision levels (each level ~4x the polycount, so 3 is already 64x; node soft-caps at 3), algorithm picks the scheme (osdcc = OpenSubdiv Catmull-Clark, the smooth-surface standard), close_holes seals open boundaries. | `input` (+11 optional) |
| `lod_create` | LOD / packed-primitive staging via op. lod (Labs LOD Create): build a level-of-detail chain — levels sets the number of LODs (spawns that many reduction slots, all starting at 100%; refine per-slot percentages in the node afterwards). pack (Pack SOP): collapse the input into packed primitives (flat, memory-light instancing units) — packbyname packs one prim per name-attribute value, transfer_attributes/transfer_groups carry patterns up to the packed prims, pivot sets the pack pivot (origin\|centroid). proxy (Pack SOP): the same pack but staged as a cheap viewport proxy via the packed viewport-LOD (lod token, default box) — the general-geometry analog of the terrain set_tile_lod. | `input` (+8 optional) |
| `assemble` | Pack named pieces into PackedFragment primitives (Assemble SOP) — the render/sim-ready packing of a fractured/named mesh. pack defaults on (pack_geo is the toggle that actually emits packed prims). | `input` (+14 optional) |
| `transform_pieces` | Apply per-piece transforms back onto packed pieces (Transform Pieces) — THE sim-result -> packed-geometry round-trip. | `input` (+13 optional) |
| `for_each` | Build a For-Each loop / iterate-over-pieces SCAFFOLD (block_begin + pass-through body + block_end, fully wired and cross-referenced) to loop over geometry per-piece, per-point, or a fixed N times (count loop). | `input` (+14 optional) |
| `for_each_begin` | Create a For-Each block_begin — the composable loop START / entry. | `input` (+4 optional) |
| `for_each_end` | Create a For-Each block_end — the composable loop CLOSE / gather. input = your loop body's output (nodes to iterate over), begin = the paired block_begin, pieces = the geometry whose pieces/points to loop over. | `input` (+14 optional) |
| `compile_block` | Wrap a target in a Compile Block (compile_begin + compile_end, cross-referenced) — the multithread / cook-overhead-strip optimizer around a heavy For-Each loop (set for_each_end's multithread inside it). | `input` (+6 optional) |
| `feather_template` | Feather Template from Shape — the feather lane ENTRY. | `name` (+10 optional) |
| `feather_template_assign` | Feather Template Assign — assign feather templates onto skin points to seed a groom. | `input` (+7 optional) |
| `feather_template_interpolate` | Feather Template Interpolate — grow a full groom by interpolating feathers across a skin from sparse guide feathers + templates. | `input` (+13 optional) |
| `feather_clump` | Feather Clump — split and clump barbs for the characteristic separated, matted feather look. | `input` (+12 optional) |
| `feather_noise` | Feather Noise — add natural break-up to feathers. | `input` (+10 optional) |
| `feather_width` | Feather Width — set shaft and barb widths driving rendered feather thickness. | `input` (+6 optional) |
| `feather_resample` | Feather Resample — change the point resolution of feather shafts and barbs. | `input` (+13 optional) |
| `feather_deintersect` | Feather Deintersect — push overlapping feathers apart so a dense groom reads cleanly. | `input` (+12 optional) |
| `feather_normalize` | Feather Normalize — normalize feather attributes into a canonical rest form. | `input` (+5 optional) |
| `feather_barb_transform` | Feather Barb Transform — convert barb positions between feather-local space and object space. | `input` (+3 optional) |
| `feather_deform` | Feather Deform — capture feathers to a skin and deform them along with an animated skin. | `input` (+12 optional) |
| `feather_attrib_interpolate` | Feather Attrib Interpolate — interpolate barb attributes onto feathers from source feathers. | `input` (+9 optional) |
| `feather_surface` | Feather Surface — build a renderable polygon surface mesh from condensed feathers. | `input` (+10 optional) |
| `feather_surface_blend` | Feather Surface Blend — blend a feather surface toward a target surface (e.g. fold a wing). | `input` (+13 optional) |
| `feather_convert` | Feather Convert — convert condensed feathers into explicit curve or surface geometry. | `input` (+9 optional) |
| `feather_uncondense` | Feather Uncondense — expand a condensed feather (one prim per feather) into full per-barb curve geometry. | `input` (+7 optional) |
| `feather_primitive` | Feather Primitive — edit the condensed feather primitive representation (resolution + naming). | `input` (+8 optional) |
| `feather_barb_tangents` | Feather Barb Tangents — compute per-barb tangent attributes on feathers (needed by some barb styling / shading ops). | `input` (+1 optional) |
| `feather_min_dist` | Feather Minimum Distance — compute a minimum-distance attribute between feathers (input 0) and target feathers (input 3). | `input` (+3 optional) |
| `feather_ray` | Feather Ray — project/ray feathers onto skin or a target geometry, optionally sampling primnum/primuv at the hit. | `input` (+10 optional) |
| `feather_visualize` | Feather Visualize — generate viewport visualization geometry for feathers (barbs as curves or a surface). | `input` (+3 optional) |
| `hair_generate` | Hair Generate (hairgen::2.0) — THE scriptable hair/guide GENERATOR and lane entry: scatter roots on a skin and grow curves, optionally interpolated from a guide set. | `input` (+17 optional) |
| `fur_setup` | Fur (fur) — the all-in-one legacy Fur generator: generate + clump + part hairs from a skin and guides in one node. | `input` (+15 optional) |
| `hair_growth_field` | Hair Growth Field (hairgrowthfield) — build a hair growth field / scatter guide roots from a scalp. | `input` (+14 optional) |
| `guide_initialize` | Guide Initialize (guideinit) — orient freshly-created guides (wind shape, lift, along-skin blend). | `input` (+11 optional) |
| `guide_reguide` | Reguide (reguide) — redistribute / resample the guide set (change guide density and segment count). | `input` (+11 optional) |
| `guide_fill` | Guide Fill (guidefill) — fill gaps in a sparse guide set using a guide interpolation mesh. | `input` (+7 optional) |
| `guide_grow_to_surface` | Guide Grow to Surface (guidegrowtosurface) — grow guide roots out to a target surface (advect source points onto a mesh). | `input` (+10 optional) |
| `guide_process` | Guide Process (guideprocess) — the primary guide STYLING op-stack: pick a single operation with op1 (set direction/lift/length, displace, make wavy, straighten, smooth, frizz, bend, sim attrib). | `input` (+15 optional) |
| `hair_clump` | Hair Clump (hairclump::2.0) — clump hairs/guides into strands (the signature hair look). | `input` (+15 optional) |
| `guide_clump_center` | Guide Clump Center (guideclumpcenter) — compute clump-center guides/attribs that feed hair_clump. | `input` (+5 optional) |
| `guide_partition` | Guide Partition (guidepartition) — create parting lines that split the groom into partition regions. | `input` (+10 optional) |
| `guide_groom` | Guide Groom (guidegroom::2.0) — the brush groomer's data node. | `input` (+13 optional) |
| `hair_comb` | Comb (comb) — comb fur/hair direction. | `input` (+9 optional) |
| `guide_mask` | Guide Mask (guidemask) — author masks (attrib/group) on guides/skin that every other groom op reads. | `input` (+14 optional) |
| `guide_group` | Guide Group (guidegroup) — create guide / parting-line groups by naming convention. | `input` (+5 optional) |
| `guide_find_strays` | Guide Find Strays (guidefindstrays) — detect stray/outlier guides and tag them in a group/attrib. | `input` (+10 optional) |
| `guide_skin_attrib_lookup` | Guide Skin Attribute Lookup (guideskinattriblookup) — copy skin attributes onto guides via the stored skinprim/skinprimuv rooting. | `input` (+9 optional) |
| `guide_tangent_space` | Guide Tangent Space (guidetangentspace) — compute per-guide tangent/normal/bitangent/orient frames needed by the direction ops. | `input` (+12 optional) |
| `guide_interpolation_mesh` | Guide Interpolation Mesh (guideinterpolationmesh) — build the interpolation mesh (remeshed skin + guide weights) that hair_generate uses to interpolate guides. | `input` (+14 optional) |
| `guide_volume` | Guide Volume (guidevolume) — build the guide/skin volume representation (cross-sections / shell / remesh / tets, optional VDB) that many groom ops consume. | `input` (+12 optional) |
| `guide_surface` | Guide Surface (guidesurface) — move/build a surface from guides along a guide interpolation mesh. | `input` (+9 optional) |
| `guide_deform` | Guide Deform (guidedeform) — capture guides to a skin and deform them with an animated skin. | `input` (+16 optional) |
| `guide_transfer` | Guide Transfer (guidetransfer) — transfer a groom from a source skin to a target skin. | `input` (+11 optional) |
| `groom_blend` | Groom Blend (groomblend) — blend two full grooms (guides A vs guides B) by weight/mask. | `input` (+14 optional) |
| `guide_collide_vdb` | Guide Collide With VDB (guidecollidevdb) — push guides out of a collision VDB. | `input` (+11 optional) |
| `guide_advect` | Guide Advect (guideadvect) — advect guides through a velocity VDB or fill collisions. | `input` (+13 optional) |
| `hair_card_generate` | Hair Card Generate (haircardgen) — generate textured hair CARDS (game / realtime output) from hair curves. | `input` (+16 optional) |
| `hair_volume_rasterize` | Volume Rasterize Hair (volumerasterizehair) — rasterize hair curves into a density/color/tangent VDB (render / sim prep). | `input` (+10 optional) |
| `fiber_groom` | Fiber Groom (fibergroom) — muscle-FIBER grooming (KineFX muscle lane, not hair). | `input` (+8 optional) |
| `volume_create` | Volume (volume) — GENERATOR: create a fresh scalar/vector volume primitive in a new /obj geo (a fog/density authoring source). type float/int; rank + components size the volume; volume_name names the grid; initialalpha the fill; zmin/zmax + use_cam_window/camera set a camera-frustum volume (camera is a NodePath scene reference, not a file). | `name` (+9 optional) |
| `vdb_create` | VDB (vdb) — GENERATOR: create a fresh empty typed VDB grid (level-set / fog / vector) in a new /obj geo — the VDB authoring source. grid_class picks the interpretation; grid_type the voxel type; grid_precision single/double; grid_name names the grid. | `name` (+4 optional) |
| `volume_from_attrib` | Volume from Attribute (volumefromattrib) — rasterize a point/vertex attribute into a volume. | `input` (+14 optional) |
| `points_from_volume` | Points from Volume (pointsfromvolume) — scatter points inside a fog/SDF volume. | `input` (+13 optional) |
| `paint_fog_volume` | Volume Paint Fog (paintfogvolume) — procedurally deposit density into a fog volume. | `input` (+15 optional) |
| `volume_rasterize_curve` | Volume Rasterize Curve (volumerasterizecurve) — rasterize curves into a fog volume (density laid along the curves). | `input` (+14 optional) |
| `volume_convert` | Convert Volume (convertvolume) — convert a VDB/volume to a polygonal surface via marching cubes. | `input` (+7 optional) |
| `volume_surface` | Volume Surface (volumesurface) — build a polygon surface from a fog/SDF volume hierarchy with adaptive edge length. | `input` (+15 optional) |
| `extrude_volume` | Extrude Volume (extrudevolume) — extrude polygons into a solid volume along the base normal. | `input` (+11 optional) |
| `convert_vdb_points` | Convert VDB Points (convertvdbpoints) — convert between point clouds and VDB Points grids. | `input` (+15 optional) |
| `volume_merge` | Volume Merge (volumemerge) — merge/composite volumes with a full pre/post add-mul stack. | `input` (+16 optional) |
| `vdb_merge` | VDB Merge (vdbmerge) — merge multiple VDB grids of matching name into one. | `input` (+6 optional) |
| `volume_vector_join` | Volume Vector Join (volumevectorjoin) — join three (or four) scalar volumes into one vector volume. | `input` (+8 optional) |
| `volume_vector_split` | Volume Vector Split (volumevectorsplit) — split a vector volume into three scalar volumes. | `input` (+3 optional) |
| `volume_feather` | Volume Feather (volumefeather) — soften (feather) a volume's values near its border. | `input` (+12 optional) |
| `volume_ramp` | Volume Ramp (volumeramp) — remap a volume's values through a source->dest range. | `input` (+8 optional) |
| `volume_noise_fog` | Volume Noise Fog (volumenoisefog) — add layered noise to a fog volume for density detailing. | `input` (+14 optional) |
| `volume_noise_sdf` | Volume Noise SDF (volumenoisesdf) — add layered noise to an SDF volume for surface detailing. | `input` (+14 optional) |
| `volume_adjust_fog` | Volume Adjust Fog (volumeadjustfog) — adjust a fog volume's look (init / remap combo). | `input` (+13 optional) |
| `volume_resample` | Volume Resample (volumeresample) — resample a volume to a new voxel resolution. | `input` (+10 optional) |
| `volume_resize` | Volume Resize (volumeresize) — resize / re-bound a volume's grid extents. | `input` (+10 optional) |
| `volume_reduce` | Volume Reduce (volumereduce) — reduce a volume to an aggregate value (max/min/average/median/sum/rms...). | `input` (+8 optional) |
| `volume_bound` | Volume Bound (volumebound) — rebuild the active/bounding region of a volume by thresholding. | `input` (+4 optional) |
| `volume_sdf` | Volume SDF (volumesdf) — compute a signed-distance field from a fog/mask volume. | `input` (+9 optional) |
| `vdb_activate_sdf` | VDB Activate SDF (vdbactivatesdf) — activate / expand the narrow band of an SDF VDB. | `input` (+15 optional) |
| `vdb_topology_to_sdf` | VDB Topology to SDF (vdbtopologytosdf) — build an SDF from a VDB's active-voxel topology. | `input` (+10 optional) |
| `vdb_occlusion_mask` | VDB Occlusion Mask (vdbocclusionmask) — build a camera-facing occlusion mask VDB behind the input VDBs. | `input` (+8 optional) |
| `volume_analysis` | Volume Analysis (volumeanalysis) — compute a differential quantity of a volume. | `input` (+4 optional) |
| `volume_velocity_from_curves` | Volume Velocity from Curves (volumevelocityfromcurves) — build a velocity volume that flows along curves. | `input` (+17 optional) |
| `volume_velocity_from_surface` | Volume Velocity from Surface (volumevelocityfromsurface) — build a velocity (+ collision) volume from a surface's motion. | `input` (+9 optional) |
| `lattice_from_volume` | Lattice from Volume (latticefromvolume) — build a lattice / point grid matching a volume's voxel layout. | `input` (+7 optional) |
| `volume_deform` | Volume Deform (volumedeform) — deform a volume by a point-deform / moving lattice. | `input` (+10 optional) |
| `volume_rasterize_lattice` | Volume Rasterize Lattice (volumerasterizelattice) — rasterize a moving lattice back into a volume. | `input` (+15 optional) |
| `volume_break` | Volume Break (volumebreak) — split / break geometry by an SDF volume cutter into pieces. | `input` (+12 optional) |
| `volume_splice` | Volume Splice (volumesplice) — splice / stitch tiled volume pieces back into one grid. | `input` (+3 optional) |
| `volume_stamp` | Volume Stamp (volumestamp) — stamp a source volume into a destination volume at points. | `input` (+10 optional) |
| `volume_patch` | Volume Patch (volumepatch) — patch a region of a volume with another volume (Poisson blend). | `input` (+9 optional) |
| `volume_convolve` | Volume Convolve (volumeconvolve3) — apply a 3x3x3 convolution kernel to a volume. | `input` (+4 optional) |
| `volume_fft` | Volume FFT (volumefft) — forward / inverse FFT of a volume (frequency domain). | `input` (+7 optional) |
| `volume_normalize` | Volume Normalize Weights (volumenormalize) — normalize a set of volume weights / values. | `input` (+9 optional) |
| `volume_compress` | Volume Compress (volumecompress) — compress a volume's storage (tile / constant pruning). | `input` (+15 optional) |
| `volume_arrival_time` | Volume Arrival Time (volumearrivaltime) — compute front-propagation arrival time through a speed volume. | `input` (+8 optional) |
| `volume_optical_flow` | Volume Optical Flow (volumeopticalflow) — estimate motion (optical flow) between two volumes. | `input` (+11 optional) |
| `volume_trail` | Volume Trail (volumetrail) — advect / trail points through a velocity volume over time. | `input` (+16 optional) |
| `volume_ambient_occlusion` | Volume Ambient Occlusion (volumeambientocclusion) — compute ambient occlusion into a volume. | `input` (+7 optional) |
| `volume_bake` | Bake Volume (bakevolume) — bake lighting / scattering into a volume (render prep). | `input` (+11 optional) |
| `volume_noise_vector` | Volume Noise Vector (volumenoisevector) — add layered noise to a vector volume (velocity detailing). | `input` (+9 optional) |
| `paint_color_volume` | Volume Paint Color (paintcolorvolume) — procedurally deposit colour (Cd) into a volume. | `input` (+15 optional) |
| `paint_sdf_volume` | Volume Paint SDF (paintsdfvolume) — procedurally carve / add into an SDF volume. | `input` (+8 optional) |
| `vdb_convex_clip_sdf` | VDB Convex Clip SDF (vdbconvexclipsdf) — convex-clip an SDF VDB by a second convex SDF. | `input` (+7 optional) |
| `vdb_diagnostics` | VDB Diagnostics (vdbdiagnostics) — validate / diagnose a VDB grid (data-only QC). | `input` (+15 optional) |
| `vdb_lod` | VDB LOD (vdblod) — build a level-of-detail (mip) pyramid for a VDB. | `input` (+6 optional) |
| `vdb_points_delete` | VDB Points Delete (vdbpointsdelete) — delete points from a VDB Points grid. | `input` (+5 optional) |
| `vdb_points_group` | VDB Points Group (vdbpointsgroup) — group points within a VDB Points grid. | `input` (+15 optional) |
| `vdb_rasterize_frustum` | VDB Rasterize Frustum (vdbrasterizefrustum) — rasterize particles into a camera-frustum-aligned VDB. | `input` (+17 optional) |
| `vdb_visualize_tree` | VDB Visualize Tree (vdbvisualizetree) — build viz geometry of a VDB's internal tree structure. | `input` (+15 optional) |
| `poly_patch` | Build a smooth polygon patch surface across a hull/cage of curves or a mesh (polypatch) — tidy a rough curve cage into a clean subdiv-ready surface. basis = smoothing basis (cardinal \| bspline); connectivity = how hull rows/cols connect into the patch; divisions [u,v] = output resolution; close_u/close_v wrap it; output_polygons emits polys instead of a mesh primitive. | `input` (+8 optional) |
| `poly_loft` | Skin a polygon surface across a sequence of cross-section curves (polyloft). | `input` (+11 optional) |
| `poly_spline` | Fit a smooth spline through a polyline's points and re-output it as a resampled polygon curve (polyspline) — turn a coarse control polygon into a smooth curve. spline_type = interpolation basis; closure whether to close; division_method how sample density is distributed; segment_length / divisions / sample_divisions the output resolution; tension the CV tension. | `input` (+9 optional) |
| `circle_spline` | Fit circular-arc / ellipse / helix splines through a control polygon (circlespline) — perfectly round curvature a freeform spline can't give. spline_type (hybrid \| circle \| ellipse \| helix); helix_type the winding style; reparm_strength re-parametrizes for even spacing; segment_divisions the output resolution; output_tangent + tangent_attrib write a tangent attribute. | `input` (+8 optional) |
| `poly_cap` | Fill open polygon boundaries (unshared edges) with cap polygons (polycap) — seal a tube/extrusion end or a hole ring. | `input` (+7 optional) |
| `cap` | Add end/pole caps to NURBS/mesh surfaces and open curves, per U/V boundary (cap) — close the ends of tubes/spheres/revolved surfaces. first_u_cap / last_u_cap / first_v_cap / last_v_cap each pick a style (none \| facet \| share \| round \| tangent); divisions_u / divisions_v the rounded-cap resolution; scale_u / scale_v bulge the caps. | `input` (+10 optional) |
| `fillet` | Build a smooth transition surface between adjacent primitives / two curves (fillet) — round hard junctions between surfaces. | `input` (+11 optional) |
| `stitch` | Blend/stitch two adjacent surface HULLS together along shared boundaries (stitch). | `input` (+12 optional) |
| `join` | Connect a sequence of separate primitives (curves or surfaces) end-to-end into a single continuous primitive (join) — turn many little pieces into one long primitive. | `input` (+10 optional) |
| `poly_hinge` | Fold/rotate polygons about a hinge edge or axis, subdividing the crease into segments (polyhinge) — open panels, petals, pop-up folds. group + group_type (primitive \| edge) pick what folds; pivot_mode how the hinge line is defined; hinge_edge the edge to hinge on; hinge_angle the fold angle; divisions the crease segments; enable_inset + inset add a bevel; output_front/back/side toggle the result shells. | `input` (+15 optional) |
| `poly_stitch` | Weld the boundaries of two polygon shells together, filling the gap with bridging polygons (polystitch) — repair seams / join separately-modeled halves. stitch_group / corners restrict which boundary polys/points are stitched; tolerance the max stitch distance; consolidate fuses coincident points; find_corners + corner_angle auto-detect corner points. | `input` (+7 optional) |
| `poly_soup` | Collapse many polygons into a single lightweight 'polysoup' primitive (polysoup) — cut memory + node overhead for dense static meshes, great before instancing / heavy scatter targets. group restricts the source; min_polys the size threshold; convex triangulates to convex polys; use_max_sides + max_sides cap polygon sides; merge_vertices welds identical verts; ignore_attribs / ignore_groups drop per-prim data. | `input` (+9 optional) |
| `poly_cut` | Cut/split polygons along points, edges, or an attribute-crossing, optionally removing the cut region (polycut). group restricts affected polys; type (points \| edges) the cut primitive; cut_points / cut_edges name the cut locations; strategy (remove \| cut) whether to delete or just split; cut_attrib + cut_value + cut_threshold cut where an attribute crosses a value (an isocut); keep_closed re-closes the result. | `input` (+10 optional) |
| `poly_path` | Reconnect loose edges / open polylines into clean continuous paths (polypath) — tidy edge extractions and boundary curves for downstream sweep/resample. connect_ends joins nearby endpoints (within max_end_dist); connect_only_to_ends restricts joins to other endpoints (no mid-curve T-junctions); close_loops closes isolated rings. | `input` (+5 optional) |
| `convert_line` | Convert geometry edges into polyline curves (convertline) — extract a wireframe / edge-curves from a mesh for polywire, resample, or sweep. group restricts the source; connect_path chains edges into continuous paths; keep_order preserves group order; close_loops closes isolated rings; remove_unused drops orphaned points; compute_length + length_name write a per-primitive rest-length attribute. | `input` (+8 optional) |
| `circle_from_edges` | Snap a ring of points/edges onto a best-fit circle (circlefromedges) — make a bolt-hole, pipe end, or wheel arch perfectly round. group + group_type pick the ring; only_boundary uses just the group boundary; explicit_radius + radius force a radius (else best-fit); scale grows/shrinks the fitted circle; output_edge_group names the result edges. | `input` (+8 optional) |
| `orient_along_curve` | Compute per-point orientation frames (tangent/up + rotations) along curves (orientalongcurve) — the rig for sweeping, copy-to-curve, or ribbon twist. | `input` (+17 optional) |
| `delta_mush` | Smooth a deformed mesh while preserving surface detail (deltamush) — the standard fix for lumpy skinning / jittery deformations. | `input` (+10 optional) |
| `surface_relax` | Evenly redistribute points across a surface to relax bunched/stretched topology (surfacerelax) — improve point distribution without changing the shape much. | `input` (+4 optional) |
| `laplacian` | Compute the discrete Laplace operator (cotangent / mean-value / Wachspress / Tutte weights) of a mesh and store it as a sparse matrix in attributes (laplacian) — backbone of mesh diffusion, smoothing, and geometry-processing solves. mode picks the weighting scheme; separate_mass splits out the mass matrix; diffusion + diffusion_coeff build a diffusion matrix instead; epsilon regularizes. | `input` (+6 optional) |
| `soft_transform` | Move/rotate/scale a region of points with a smooth radial falloff (softxform) — a proportional-edit / magnet grab. | `input` (+9 optional) |
| `soft_peak` | Push points along their normals with a smooth radial falloff (softpeak) — a soft inflate/dent brush. | `input` (+7 optional) |
| `elastic_transform` | Deform a mesh as an elastic solid via a grab / twist / scale / pinch handle that propagates through the material (elastictransform) — feels like pulling soft rubber. | `input` (+12 optional) |
| `magnet` | Deform `input` points by a moving 'magnet' shape whose metaball-style field falls off with distance (magnet) — squash/stretch, dents, muscle bulges driven by a proxy shape. | `input` (+11 optional) |
| `bulge` | Push `input` points outward/inward along their normals where a 'magnet' shape overlaps them (bulge) — a fast localized swell driven by a proxy shape. | `input` (+7 optional) |
| `creep` | Project `input` geometry onto a surface's UV space and crawl it across that surface (creep) — stick decals/tracks/text onto a mesh, or animate geo sliding over it. | `input` (+10 optional) |
| `vector_deform` | Deform `input` by the difference between two matching point clouds (a rest set and a deformed set), interpolating that motion field onto the mesh (vectordeform) — cage/lattice-style deformation from arbitrary driver points. | `input` (+9 optional) |
| `shrinkwrap` | Wrap a tight convex hull around the `input` points (shrinkwrap) — fast collision proxies, bounding shells, simplified silhouettes. type (xyz = full 3D hull \| xy = 2D planar hull); shrink_amount insets the hull inward; plane_origin / plane_normal define the projection plane for the 2D mode; preserve_attribs carries source attributes; remove_inline_points cleans collinear hull points. | `input` (+8 optional) |
| `detangle` | Push self-intersecting / interpenetrating geometry apart so it stops overlapping (detangle) — cleanup for cloth, hair, or crowd meshes that have tangled. | `input` (+8 optional) |
| `tetrahedralize` | Fill a CLOSED input surface with a tetrahedral (tet) mesh (tetrahedralize) — the entry point for FEM / soft-body / finite-element prep. | `input` (+17 optional) |
| `tet_conform` | Build a boundary-CONFORMING tet mesh whose surface matches the input polygons (tetconform) — higher-quality volumetric meshing than a plain fill when the surface must be honoured. | `input` (+17 optional) |
| `tet_embed` | Embed the input surface inside a coarser background tet lattice (tetembed) — the fast FEM/soft-body prep when you want a simulatable tet cage AROUND detailed geometry rather than a surface-conforming mesh. | `input` (+17 optional) |
| `tet_layer` | Build a single tet layer of a given thickness off a surface (tetlayer) — quick volumetric shells for FEM skin/rind or a starting tet band. | `input` (+7 optional) |
| `tet_partition` | Split a tet mesh into named pieces using region-boundary polygons (tetpartition) — carve a solid into FEM regions / fracture chunks. | `input` (+5 optional) |
| `tet_surface` | Extract the outer surface polygons of a tet mesh (tetrasurface) — get a renderable / collidable skin back from a volumetric tet mesh. | `input` (+4 optional) |
| `tet_strata` | Build layered (stratified) tet shells between an outer surface and an inner boundary (tetstrata) — multi-layer FEM materials (skin/fat/muscle rinds, laminated solids). | `input` (+9 optional) |
| `tet_fracture` | Fracture geometry into tet-based chunks via a Voronoi / pattern split (tetfracture) — pre-fracture solids for FEM/RBD destruction. | `input` (+7 optional) |
| `solid_embed` | Embed the input geometry in a solid tet lattice sized by a single element scale (solidembed) — the one-knob FEM cage builder. | `input` (+2 optional) |
| `topo_transfer` | Wrap a clean TEMPLATE mesh onto a TARGET mesh, transferring the template's topology onto the target's shape (topotransfer) — the retopo/character workhorse for matching a rigged base mesh to a scan/sculpt. | `input` (+18 optional) |
| `topo_slide` | Slide a target mesh's points across its surface guided by matched reference/target CURVES, or run a curve-guided topo transfer (toposlidebycurverefs) — dial in retopo flow along seams/features procedurally. | `input` (+15 optional) |
| `usd_configure_sop` | Configure how SOP geometry will be authored to USD — set stage-wide import options as USD metadata on the geometry (the SOP-context `usdconfigure`; a pure operator, NO file write). | 9 optional |
| `usd_configure_geometry` | Author per-primitive USD geometry metadata on SOP geometry (the SOP-context `usdconfiguregeometry`; a pure operator, NO file write). | 9 optional |
| `usd_configure_prims_from_points` | Author USD prim attributes from POINTS — turn points into configured USD prims (spheres, lights, xforms…) with per-prim metadata (the SOP-context `usdconfigureprimsfrompoints`; a pure operator, NO file write). | 12 optional |
| `unpack_usd` | Unpack packed-USD primitives into native Houdini geometry (unpackusd) — turn the lightweight packed prims from usd_import_sop (unpack=false) into editable polygons/points. | `input` (+14 optional) |

### Groups & attributes

| Tool | What it does | Key params |
|---|---|---|
| `attribute_normalize_float` | SideFX Labs Attribute Normalize Float — remap a float attribute onto [out_min, out_max] (default 0..1) using its incoming value range. | `input` (+10 optional) |
| `attribute_normalize_vector` | SideFX Labs Attribute Normalize Vector — normalize a vector attribute. | `input` (+11 optional) |
| `attribute_value_replace` | SideFX Labs Attribute Value Replace — rename an attribute and/or seed default init / fallback values on the attributes named in `attribute_list` (default `name`). | `input` (+8 optional) |
| `color_adjustment` | SideFX Labs Color Adjustment — brightness / contrast / saturation / gamma grade on a color attribute (default `Cd`, or a custom attribute). | `input` (+13 optional) |
| `color_blend` | SideFX Labs Color Blend — blend two color attributes with a photoshop-style `blend_mode`. | `input`, `input2` (+9 optional) |
| `color_gradient` | SideFX Labs Color Gradient — paint a color gradient along an `axis` (X/Y/Z, or Custom rotated by `rotation_angle`) into `Cd` (or a custom attribute). | `input` (+7 optional) |
| `min_max_average` | SideFX Labs Min Max Average — reduce an attribute to a single statistic (`method`: max/min/mean/median/sum/rms/…) and write it back as a detail attribute (or, with `detail_attribute` off, promoted per-element) named by `prefix`/`suffix`. | `input` (+8 optional) |
| `radial_sort` | SideFX Labs Radial Sort — reorder points and/or primitives by their angle around an axis (`*_dir`) so a fan/ring is indexed in a clean rotational order. | `input` (+16 optional) |
| `sort_geometry` | SideFX Labs Sort — reorder points and/or primitives by a chosen key: axis (byx/byy/byz), random (`*_seed`), shift (`*_offset`), along a vector (`*_dir`), spatial locality, or by an attribute (`*_attrib`). | `input` (+17 optional) |
| `visualize_vector` | SideFX Labs Visualize Vector — build arrow geometry from a vector attribute (`vector_attribute`, default `P`) for inspection. | `input` (+18 optional) |
| `fast_group_unshared` | SideFX Labs Fast Group Unshared — group the UNSHARED (open-boundary / border) elements of the input mesh (input 0): edges owned by a single primitive plus the points/prims/vertices touching them. | `input` (+4 optional) |
| `group_by_attribute` | SideFX Labs Group by Attribute — create one group per distinct value of an attribute on the input (input 0). | `input` (+5 optional) |
| `group_by_measure` | SideFX Labs Group by Measure — group primitives by a geometric eccentricity measure (how far a prim's shape departs from a circle/square). | `input` (+5 optional) |
| `group_curve_corners` | SideFX Labs Group Curve Corners — label the corner points of input curves (input 0) into an `inside` group (convex corners) and an `outside` group (concave corners). | `input` (+6 optional) |
| `group_grow` | SideFX Labs Group Expand — grow (or shrink) an existing group across the input geometry's connectivity. | `input` (+3 optional) |
| `group_invert` | SideFX Labs Group Invert — invert named groups in place: each listed group is replaced by its complement (all elements NOT in it). | `input` (+4 optional) |
| `loops_from_selection` | SideFX Labs Loops from Selection — grow full edge loops (or quad loops) out from a seed edge group. | `input` (+12 optional) |
| `random_selection` | SideFX Labs Random Selection — select a random subset of the input's elements and turn it into a group. | `input` (+24 optional) |
| `extract_filename` | SideFX Labs Extract Filename — reads the file path off an upstream File SOP (`input`, or `custom_file_sop` when `input_mode`=custom) and writes its parts to detail string attributes (full path / file path / filename / directory). | `input` (+7 optional) |
| `group_create` | Create a NAMED, persistent point/prim/edge group (groupcreate) — the setup step for every targeted op (blast, bevel a group, dissolve, transform-a-group). | `input`, `group_name` (+10 optional) |
| `group_promote` | Convert a group between element classes (grouppromote) — e.g. point group -> prim group, with boundary/unshared options. | `input` (+8 optional) |
| `group_range` | Group elements by numeric index range and/or every-Nth stride (grouprange) — select piece-id subsets, alternate rows, deterministic slices. group_name = group to create. class: points\|prims\|vertices. method: absolute (index start..end) \| relative (fractional 0..1 of the total) \| length \| partition (split into num_partitions even blocks). start/end bound the window; select_amount ('of') + select_total ('every') + select_offset give an every-Nth stride (of=1 every=3 => every 3rd). invert flips membership; merge combines with an existing same-named group. | `input` (+13 optional) |
| `group_expand` | Grow or shrink a group by edge-connected steps (groupexpand) — negative steps shrink. | `input` (+9 optional) |
| `group_transfer` | Transfer group membership from one geometry to another by proximity (grouptransfer). | `input` (+11 optional) |
| `group_delete` | Remove group definitions (geometry untouched) — groupdelete. | `input` (+3 optional) |
| `group_rename` | Rename a group (grouprename). | `input` (+4 optional) |
| `group_geo` | Deep geometric group selection (groupcreate) — the modes group_create lacks: bounding sphere/object/volume/convex, backface-by-camera, edge-angle, unshared/open edges. | `input` (+27 optional) |
| `blast` | Delete geometry by group — the fundamental targeted-delete primitive. group = the group name/pattern (from the group tools) or a raw element range; group_type guides interpretation (guess\|points\|prims\|edges\|breakpoints). delete_non_selected INVERTS: keep ONLY the group, delete everything else (the isolate idiom). fill_hole caps the holes left behind; remove_group drops the group tag afterward. | `input`, `group` (+5 optional) |
| `attribute_transfer` | Transfer point/prim attributes from a SOURCE mesh onto the input by proximity (attribtransfer) — the LIDAR-color / GIS-attribute workhorse: paint Cd from a scan onto a remesh, carry N/uv across a topology change. | `input`, `source` (+4 optional) |
| `attribute_create` | Create a typed point/prim/vertex/detail attribute with a constant value (attribcreate) — the typed non-wrangle way to add Cd/pscale/N/id/material-index or any custom attribute. attrib_name = attribute to create. type = storage type (float\|int\|vector\|...). class = element class. value = a number or [x,y,z] (string types take a string via value as text). size = tuple size 1..4. precision = storage bits. type_info tags transform semantics so downstream nodes transform the attribute correctly (normal for N, color for Cd, point for positions). on_existing decides what happens if the name is already present. group restricts creation. | `input`, `attrib_name` (+9 optional) |
| `attribute_promote` | Move/aggregate an attribute between element classes (attribpromote) — turn a point attribute into a per-prim mean, spread a detail value onto points, etc. attrib = source name. from_class/to_class = point\|prim\|vertex\|detail. method = how source values collapse onto one destination element (max\|min\|mean\|mode\|median\|sum\|first\|last\|array...). out_name renames the result. piece_attrib aggregates WITHIN each named piece independently. delete_original: NOTE the node DELETES the source by default — pass false to keep both. | `input`, `attrib` (+7 optional) |
| `attribute_delete` | Drop attributes by class + space-separated name patterns (attribdelete) — housekeeping to shed Cd/N/rest/temporary attributes before export or a solver. point/prim/vertex/detail are each a space-separated pattern of names to delete (e.g. | `input` (+6 optional) |
| `attribute_cast` | Cast attribute storage precision (attribcast) — the memory-halving 32->16-bit optimization for heavy point clouds / terrain tiles. class = element class. attribs = space-separated name patterns (default * = all). precision = target storage: the friendly floats 16\|32\|64 map to fpreal16/32/64, or pass an explicit node token (uint8\|int8\|int16\|int32\|int64\|fpreal16\|fpreal32\|fpreal64\|preferred) for integer casts. | `input` (+4 optional) |
| `attribute_interpolate` | Interpolate attributes from a source geometry onto points/vertices via UVW or captured weights (attribinterpolate). | `input` (+16 optional) |
| `attribute_from_volume` | Sample a volume/VDB field onto point attributes (attribfromvolume) with input/output remap. | `input` (+10 optional) |
| `attribute_blur` | Smooth/relax attributes across the surface (attribblur) — laplacian/volume-preserving, by connectivity or proximity. | `input` (+15 optional) |
| `attribute_copy` | Copy attributes from one geometry to another (attribcopy), optionally matched by an attribute like piece. | `input` (+13 optional) |
| `attribute_randomize` | Write randomized values into an attribute (attribrandomize) — all 12 distributions incl. ramp / discrete (weighted) / uniformdiscrete. min_limit/max_limit clamp only the unbounded distributions (normal/exponential/lognormal/cauchy), not an already-bounded uniform draw. | `input` (+26 optional) |
| `attribute_composite` | Composite attributes across a merged/stacked stream (attribcomposite) — mean/max/min/over/under. | `input` (+9 optional) |
| `attribute_reorient` | Reorient vector/quaternion attributes to follow a deformation vs a rest/reference (attribreorient). | `input` (+6 optional) |
| `attribute_swap` | Swap / copy / move an attribute to another name (attribswap). | `input` (+6 optional) |
| `assign_name` | Assign the piece-identity name attribute (Name SOP) — the required prep for imported/modelled fragments before assemble/RBD. | `input` (+7 optional) |
| `enumerate` | Write a per-element or per-piece index/name attribute (Enumerate SOP). | `input` (+8 optional) |
| `connectivity` | Label each connected piece with a running class-id attribute (connectivity) — the input to blast-by-piece, despeckle-by-size, per-piece randomize, and assemble. connect_type: point (points sharing an edge) \| prim (prims sharing a point). attrib_name = output id attribute. attrib_type: int \| string (string prepends `prefix`, e.g. | `input` (+8 optional) |
| `measure` | Compute a geometric quantity into an attribute (measure). measure_type: perimeter\|area\|volume\|centroid\|curvature\|gradient\|laplacian\|boundaryintegral\|surfaceintegral. attrib_name = output. class: points\|prims — which class receives the result. curvature_type applies only when measure_type=curvature. src_attrib names the attribute that gradient/laplacian/*integral operate ON (e.g. the gradient of a 'height' field). total_attrib writes the summed total (whole-mesh or per-piece area/volume) to a detail attribute. group restricts. | `input` (+8 optional) |
| `group_combine` | Boolean-combine two named groups into a result group (groupcombine). result = new group name. group_a / group_b = existing source group names. operation: union (in either) \| intersect (in both) \| xor (in exactly one) \| subtract (in A but not B). group_type = the class of all three groups (guess auto-detects). | `input`, `result`, `group_a`, `group_b` (+3 optional) |
| `attrib_adjust_float` | Author/modify a float attribute with a value pattern (attribadjustfloat). | `input` (+16 optional) |
| `attrib_adjust_integer` | Author/modify an integer attribute with a value pattern (attribadjustinteger). | `input` (+14 optional) |
| `attrib_adjust_vector` | Author/modify a vector attribute's direction and/or length (attribadjustvector). | `input` (+13 optional) |
| `attrib_adjust_color` | Author/modify a color (Cd) attribute (attribadjustcolor). | `input` (+11 optional) |
| `attrib_adjust_array` | Identity/ordering controls for an array attribute (attribadjustarray). | `input` (+6 optional) |
| `attrib_adjust_dict` | High-level controls for a dictionary attribute (attribadjustdict). | `input` (+7 optional) |
| `attrib_combine` | Combine attributes into a destination via a math op (attribcombine). | `input` (+12 optional) |
| `attrib_fill` | Fill/propagate an attribute across a surface by solving a field (attribfill). | `input` (+13 optional) |
| `attrib_fade` | Author a per-point fade weight ramping in/holding/out over frames (attribfade), typically to fade particles/pieces in and out. | `input` (+10 optional) |
| `attrib_remap` | Remap a numeric attribute's values from an input range to an output range, optionally through a ramp (attribremap). | `input` (+11 optional) |
| `attrib_sort` | Reorder points/vertices/prims by the value of an attribute (attribsort). | `input` (+7 optional) |
| `attrib_find` | For each element, find the element(s) in a SEARCH geometry with a matching attribute value (attribfind). | `input` (+10 optional) |
| `attrib_from_map` | Sample a source into a point attribute along UVs (attribfrommap). | `input` (+10 optional) |
| `attrib_from_parm` | Import another node's PARAMETER VALUES onto geometry as attributes (attribfromparm). | `input` (+7 optional) |
| `attrib_from_pieces` | Assign a per-piece attribute value across named pieces (attribfrompieces). | `input` (+11 optional) |
| `attrib_mirror` | Copy/mirror an attribute from one side of geometry to the other (attribmirror). | `input` (+13 optional) |
| `attrib_paint` | Set up a paintable attribute (attribpaint). | `input` (+8 optional) |
| `attrib_string_edit` | Find/replace on string attribute values (attribstringedit). | `input` (+11 optional) |

### Cleanup & meshing

| Tool | What it does | Key params |
|---|---|---|
| `mesh_pointcloud` | Turn a point cloud into a mesh (cloud → VDB → polygons) with optional reduction, color transfer, and export. | `name`, `input` (+6 optional) |
| `quad_remesh` | Field-aligned QUAD remesh (native quadremesh SOP — no Labs/3rd-party license): turn a triangulated / scan mesh into a clean all-quad mesh for subdivision or animation. resolution chooses how density is specified: quad_count (an absolute target_quads, the default), quad_area (target_area per quad), tolerance, or a relative/absolute scale. adaptivity (+curvature_weight) concentrates quads on curvature so silhouettes stay crisp with fewer quads; feature_boundaries aligns the quad flow to hard edges. decimation_level pre-decimates the input for speed on dense scans. | `input` (+9 optional) |
| `gameres` | SideFX Labs GameRes — reduce a high-res mesh (`input`, input 0) to a game-resolution LOD via polyreduce / Instant Meshes / voxel-remesh; the cooked SOP output IS the reduced mesh. finalcount targets the poly budget; use_instantmeshes swaps to quad-remesh; enable_voxelization+resolution do a voxel rebuild. | `input` (+19 optional) |
| `instant_meshes` | SideFX Labs Instant Meshes — field-aligned quad/tri REMESH of the input mesh via the compiled Instant Meshes core (no external executable is launched; data-only cook). | `input` (+6 optional) |
| `polydoctor` | Diagnose and repair non-manifold / ill-formed polygons (PolyDoctor) — the pre-boolean / pre-VDB / pre-sim mesh sanitiser. | `input` (+7 optional) |
| `polyfill` | Fill boundary holes (LIDAR/scan dropouts, boolean gaps) with patch polygons (PolyFill). fillmode picks the patch topology: tris / trifan / quadfan / quads / gridquads (grid of quads, best for later subdivision) or none (just group the hole). smooth (+smooth_strength, up to 50) relaxes the new patch to blend with the surrounding surface; tangent_strength controls how strongly the patch follows the border tangents (0..2, default 0.4). patch_group tags the created patch polys for later selection. | `input` (+7 optional) |
| `mesh_repair` | SideFX Labs repair toolkit multiplexed by op. repair (Labs Repair): close holes + fix non-manifold geometry — fillmode chooses the hole-patch topology (tris..gridquads), iterations = repair passes. delete_small_parts: remove disconnected junk shells — mode perimeter\|area, threshold is the relative size cut, extract_largest keeps only the single biggest piece (great for isolating a scanned object from noise). clean_seams: dissolve UV-island seam edges. fast_remesh (Labs Fast Remesh): GPU-style uniform retriangulation — target_polycount sets the output size, iterations = remesh passes. | `input` (+8 optional) |
| `clean` | Clean SOP — parametric cleanup of dirty/scan geometry (the toggle-driven complement to polydoctor/mesh_repair). | `input` (+14 optional) |
| `point_normals` | Estimate a per-point surface normal for a raw point cloud (LIDAR/photogrammetry scan) by plane-fitting each point's neighbourhood (covariance / PCA) — needed before meshing (Poisson/VDB) or wall-vs-floor segmentation, since scans have no normals. radius_m = neighbourhood search radius (metres); maxpts caps neighbours per point (cost). | `input` (+3 optional) |
| `segment_planar` | Classify/segment point-cloud points as vertical WALL vs horizontal FLOOR/CEILING from their normal v@N (run point_normals first) — building/interior scan structure extraction. kwall/coshoriz are the \|N.y\| thresholds (near 0 = wall, near 1 = horizontal). | `input` (+3 optional) |
| `despeckle` | Denoise a point cloud by deleting isolated outlier/stray points that have fewer than min_nbrs neighbours within radius — removes scanner noise/speckle/flyers before meshing. radius = neighbour search distance; min_nbrs = keep threshold. | `input` (+3 optional) |
| `level` | Gravity-align / straighten a tilted point cloud or scan so the ground is flat and horizontal: RANSAC-fit the dominant ground plane, PCA-refine its normal, and rotate the whole cloud so that normal points to +Y (up), via a level xform appended after the input. threshold = RANSAC inlier distance. | `input` (+1 optional) |

### Instance & scatter

| Tool | What it does | Key params |
|---|---|---|
| `scatter_copy` | One-shot scatter-and-instance: randomly scatter `count` points across a target surface and copy/instance a source shape onto every point (foliage, rocks, ice chunks, debris, greebles). | `name` (+6 optional) |
| `instance_attributes` | SideFX Labs Instance Attributes — writes the point attributes an instancer reads (the `instanceattrib` asset-path attribute + per-point pscale/scale/orient) onto the incoming points (`input`, input 0) so a downstream copy/instance can dress a scene. | `input` (+20 optional) |
| `physics_painter` | SideFX Labs Physics Painter — scatters objects across the incoming surface (`input`, input 0) and settles them with a short Bullet solve so they rest naturally (rocks on a slope, props on a shelf). | `input` (+19 optional) |
| `copy_to_points` | Copy/instance the source SOP geometry onto every point of the target SOP (Copy to Points 2.0) — the core instancing op for foliage, rocks, debris, greebles, crowds. | `source`, `target` (+5 optional) |
| `scatter` | Randomly scatter/distribute `count` points across the surface of the input geometry (Scatter 2.0) — the point set you then copy instances onto (with copy_to_points) or use as sample locations. count is the total point count. density_attrib biases where points land by a point float attribute (heightfield mask / occlusion / slope). relax_iterations spreads points to a near-even Poisson-disk spacing (removes clumping). seed reshuffles. | `input` (+6 optional) |
| `pack` | Collapse the input geometry into packed primitives — a lightweight flat-memory reference to the geometry that is far cheaper to copy/instance and transform in bulk (each packed prim behaves like one point you can move/rotate/scale). pack_by_name makes one packed prim per unique `name` attribute value (per-piece packing for fractured/labelled geometry). viewportlod controls how packed prims draw in the viewport (full/points/box/centroid/hidden) — drop to box/points to keep a huge instance count interactive. | `input` (+4 optional) |
| `unpack` | Expand packed primitives back into raw editable geometry (the inverse of pack) — needed before you can edit/deform the underlying points and polygons of packed instances. | `input` (+2 optional) |
| `instance` | Instance SOP: tag the input points so each one is expanded into an instanced copy of geometry at render/expand time — deferred point-instancing that stays cheap until rendered. instance_attrib names the string point attribute holding the SOP/geometry path to instance per point (heterogeneous instancing). pack outputs the expanded instances as packed prims. | `input` (+3 optional) |
| `biome_scatter` | Scatter vegetation / plants across input terrain via the Labs Biome Plant Scatter SOP — ecosystem/foliage dressing (grass, shrubs, trees) with density and spacing control. density multiplies the plant count; spacing sets the minimum gap between plants; seed reshuffles. | `input` (+4 optional) |
| `tag_radial` | Select/tag all points inside a sphere (center + radius) by writing i@tag = 1 on them — a spherical region selection for isolating or masking part of a point cloud. center = sphere center [x,y,z]. | `input` (+3 optional) |
| `point_replicate` | Replicate/multiply each input point into `count` new jittered points spread inside a shape around it (Point Replicate SOP) — turns sparse points into a fuller cloud for spray/mist/dust emission or scatter-in-a-shape. count = replicas per input point; shape (box/sphere/cylinder/cone/grid/circle/line) + size set the spread volume; noise adds extra positional jitter; copy_attribs carries the source point's attributes (Cd, pscale, id...) onto its replicas, and attribstocopy names which. | `input` (+8 optional) |

### VDB & volumes

| Tool | What it does | Key params |
|---|---|---|
| `vdb_transform_properties` | SideFX Labs VDB Transform Properties — re-derives a vector VDB's values under the volume's own transform. | `input` (+4 optional) |
| `volume_texture` | SideFX Labs Volume Texture — flatten the incoming volume/VDB (`input`, input 0) into a sliced flipbook atlas for a real-time volume-texture shader; the cooked SOP output is the slice-preview geometry. mode picks the packing; customfield names the volume field; slices/frameresolution set the atlas layout; equalizedensity/invertdensity adjust the density. | `input` (+12 optional) |
| `vdb_from_particles` | Points/particles -> VDB. op=particles builds SDF/fog/mask/velocity grids (vdbfromparticles); op=fluid surfaces FLIP particles into a fluid-density VDB (vdbfromparticlefluid). | `input` (+26 optional) |
| `vdb_from_polygons` | Polygons -> VDB SDF and/or fog (round-trip meshing / collision / atmospherics) with narrow-band control and optional point-attribute transfer. | `input` (+16 optional) |
| `vdb_convert` | Convert VDB (the round-trip hub): polygons/polysoup/vdb/native-volume, SDF<->fog reclass, precision/type change, iso control, attribute transfer and feature sharpening. | `input` (+15 optional) |
| `vdb_filter` | Single-input field filter on a VDB / native volume (smooth, reshape, renormalize, blur, extrapolate). | `input` (+29 optional) |
| `volume_combine` | Combine named VOLUME fields carried on ONE input by an operation (volumecombine) — dest = op(dest, source) matched by name: add two density fields, multiply a mask into temperature, max two smoke sims. | `input` (+12 optional) |
| `volume_rasterize_attributes` | Rasterize point ATTRIBUTES into named fog VOLUMES (volumerasterizeattributes) — turn a point cloud carrying density/temperature/v/Cd into the matching volume FIELDS in ONE node (a pyro/smoke source, or baking a point sim into renderable volumes). | `input` (+14 optional) |
| `volume_rasterize` | Rasterize points/particles into a density/attribute fog volume (points->density cloud / pyro source). input=Base Volume (input0, defines resolution); source points/particles wire to input1. | `input` (+34 optional) |
| `convert_volume` | Native-volume lane: mode=isooffset (polys -> native Houdini volume/SDF/tetra via isooffset), tovdb/topoly (convert totype), or convert (generic). | `input` (+12 optional) |
| `vdb_analysis` | Field calculus on a VDB (VDB Analysis SOP) with NO VEX: gradient/curvature/laplacian/closest-point/divergence/curl/length/normalize. | `input` (+7 optional) |
| `vdb_topology` | Active-voxel-set (topology) ops via op: activate (vdbactivate), clip (vdbclip), resample (vdbresample), segment (vdbsegmentbyconnectivity). | `input` (+23 optional) |
| `vdb_combine` | Two-input CSG / field-math on VDBs (the typed answer to a Volume VOP, NO VEX) via op: sdf (vdbcombine), fog (volumemix), vectormerge (vdbvectormerge), vectorsplit (vdbvectorsplit). input=A (input0), input_b=B (input1). | `input` (+17 optional) |
| `vdb_advect` | Transport a VDB by a velocity VDB (input1), NO VEX: op=points (vdbadvectpoints), sdf (vdbadvectsdf), morph (vdbmorphsdf toward a target SDF on input1). | `input` (+23 optional) |
| `vdb_shatter` | SDF VDB -> discrete pieces / sphere proxies, NO VEX: op=fracture (vdbfracture; cutter geo on input1; feeds sim_rbd), spheres (vdbtospheres; RBD proxy pack). | `input` (+24 optional) |
| `volume_visualize` | Inspect/present a fog volume in the viewport (no render), NO VEX: op=shade (volumevisualization density/emission shading), slice (volumeslice 2D cross-section). | `input` (+20 optional) |
| `vdb_reshape` | Reshape an SDF VDB by offsetting its surface (VDB Reshape SDF): dilate (grow), erode (shrink), open (erode-then-dilate — removes thin spikes), close (dilate-then-erode — fills pinholes/cracks). | `input` (+6 optional) |

### Solvers & simulation

| Tool | What it does | Key params |
|---|---|---|
| `rbd_guide` | Wire a guide-geometry SOP into an EXISTING rbdbulletsolver's Guide Sim input (index 4) for a guided / art-directed RBD sim (the solver's guide_* params drive the blend). | `solver`, `guide` (+1 optional) |
| `rbd_attach_constraints` | Feed an authored constraint network (glue_cluster / rbd_constraints / set_constraint_field) into an EXISTING rbdbulletsolver's Constraint input (index 1) — attach constraints to a live sim_rbd solver. | `solver`, `constraints` (+2 optional) |
| `flowmap` | SideFX Labs Flowmap — authors a per-point flow-vector attribute over a UV'd surface (`input`, input 0) for driving flow-map material distortion (rivers, lava). | `input` (+3 optional) |
| `flowmap_guide` | SideFX Labs Flowmap Guide — steers a surface flow map toward hand-drawn guide curves. | `input` (+7 optional) |
| `flowmap_obstacle` | SideFX Labs Flowmap Obstacle — deflects a surface flow map around obstacle geometry. | `input` (+6 optional) |
| `flowmap_to_color` | SideFX Labs Flowmap To Color — bakes a flow-vector attribute into an RG(B) color the engine reads as a flow map. | `input` (+3 optional) |
| `flowmap_visualize` | SideFX Labs Flowmap Visualize — previews a flow map by animating a distortion on `input` (input 0). | `input` (+7 optional) |
| `kelvin_wakes_deformer` | SideFX Labs Kelvin Wakes Deformer — deforms a water surface with the physically-based Kelvin wake pattern trailing a moving object. | `input` (+15 optional) |
| `splatter` | SideFX Labs Splatter — a self-contained SPH fluid-splatter SOURCE that builds a fresh /obj geo emitting particle fluid (paint/blood splats). | `name` (+15 optional) |
| `procedural_smoke` | SideFX Labs Procedural Smoke — builds a fresh /obj geo holding a fully-procedural smoke DENSITY volume (no sim) driven by layered noise. | `name` (+9 optional) |
| `volume_adjust_look` | SideFX Labs Volume Adjust Look — art-directs a smoke/pyro volume's LOOK (density / shadow / diffuse / emission multipliers, optional greyscale). | `input` (+12 optional) |
| `destruction_cleanup` | SideFX Labs Destruction Cleanup — post-processes RBD/fracture sim output: removes inside faces, cusps normals, regenerates piece names, optimizes pieces into chunks. | `input` (+11 optional) |
| `rbd_edge_strip` | SideFX Labs RBD Edge Strip — extracts thin edge strips along the fracture seams of RBD pieces (for edge chipping / detailing). | `input` (+4 optional) |
| `loop_volume` | SideFX Labs Loop Volume — cross-fades a volume (smoke/pyro) sequence into a seamless loop. | `input` (+5 optional) |
| `make_loop` | SideFX Labs Make Loop — turns an animated sequence into a seamless loop (geometry, volume or particles). | `input` (+14 optional) |
| `lightning` | SideFX Labs Lightning — generates procedural lightning/arc geometry across a model. | `input` (+16 optional) |
| `rbd_solver` | Bare Bullet solver for ALREADY-fractured pieces + an arbitrary constraint network — the missing link that lets the granular fracture lane (rbd_voronoi/vdb_shatter/rbd_constraints/set_constraint_field) actually be SIMULATED, WITHOUT re-fracturing (unlike sim_rbd/rbd_destruction). pieces = packed fractured SOP (Geometry in0); constraints = optional constraint-net SOP (in1); collider = optional mesh/heightfield (in3). | `pieces` (+50 optional) |
| `sim_rbd` | Rigid-body destruction (SOP Bullet lane): source -> rbdmaterialfracture::3.0 -> rbdbulletsolver. | `name` (+81 optional) |
| `rbd_constraint_properties` | Author RBD constraint PHYSICS (the breaking dial) on a solver's glue network via rbdconstraintproperties::2.0. | `solver` (+18 optional) |
| `rbd_material_fracture` | Pre-fracture geometry by MATERIAL TYPE (rbdmaterialfracture::3.0) WITHOUT a solver — concrete \| glass \| wood \| custom presets. | `input` (+31 optional) |
| `rbd_voronoi` | Raw Voronoi fracture (voronoifracture::2.0) for art-directed control: source -> scatter cells -> fracture (no material presets). | `name` (+18 optional) |
| `rbd_interior` | Interior-face detail on fractured geo (rbdinteriordetail SOP): displaces the 'inside' crack faces with noise so broken concrete/rock reads as real inside, not flat cuts. | `input` (+18 optional) |
| `rbd_constraints` | Build the constraint NETWORK GEOMETRY (bond graph) from fractured pieces: method=rules (rbdconstraintsfromrules) or method=adjacency (connectadjacentpieces). | `input` (+13 optional) |
| `rbd_configure` | Per-piece dynamics + activation on fractured pieces (rbdconfigure SOP): active/animated, density/bounce/friction, minactivationimpulse (impact trigger), overlap, type/pintype presets, visualize. | `input` (+14 optional) |
| `rbd_collision` | The TERRAIN BRIDGE: wire a mesh/heightfield collider into an existing rbdbulletsolver's Collision Geometry input (index 3) so debris settles on real captured terrain. | `solver`, `collider` (+10 optional) |
| `rbd_force` | Typed DOP force (NO VEX) for RBD debris beyond gravity/drag: wind/uniform/point/vortex/fan/drag/explosion (explosion\|blast -> popaxisforce radial shockwave). | 12 optional |
| `rbd_cache` | BUILD (never write) a File Cache 2.0 SOP after an RBD sim, with a confined explicit write path. | `input`, `file` (+7 optional) |
| `rbd_exploded` | Debug/inspection: spread fractured pieces apart to see the break (rbdexplodedview SOP). | `input` (+6 optional) |
| `rbd_destruction` | THE TERRAIN DESTRUCTION MACRO: fracture a reconstructed asset and collapse it onto real captured terrain end-to-end. building -> rbdmaterialfracture (+glue) -> [rbdconstraintproperties] -> rbdbulletsolver with the DEM wired as collision. | `name` (+20 optional) |
| `sim_flip` | FLIP liquid (deep container + solver): builds a flipcontainer + flipsolver fed by a source primitive (a default box, or your `source_geo`), wired source->Sources(0)/container->Container(1). | `name` (+44 optional) |
| `flip_collision` | Geometry -> FLIP collision volume (Collision Source 2.0 SOP). | `input` (+16 optional) |
| `flip_flood` | Terrain flood MACRO: ONE call composes a DEM/heightfield SOP (`input`) -> convertheightfield -> collisionsource collider -> auto-sized flipcontainer (fit to the DEM bbox + padding + headroom) -> flipsolver, with the collider auto-wired into the solver's Collisions input. | `name`, `input` (+22 optional) |
| `flip_source` | Geometry -> FLIP particles (Flip Source SOP): initial fill and/or continuous emit; feeds a flipsolver Sources input. | `input` (+15 optional) |
| `flip_boundary` | Open-boundary source/sink for a FLIP container (Flip Boundary SOP): none/velocity/pressure/hydro_pressure boundary types (hydro = coastal/flood waterline). | `input` (+11 optional) |
| `flip_tank` | Pre-filled pool of FLIP particles (Particle Fluid Tank SOP): a pool/harbor/reservoir that starts already full. | `name` (+11 optional) |
| `flip_force` | Typed force node (no VEX) for a FLIP/DOP sim: ftype -> uniformforce/vortexforce/windforce/drag/pointforce/fan/popaxisforce. | 13 optional |
| `sim_pop` | POP particles (master): a SOP dopnet (input0=emit geo) wrapping popobject -> popsolver::2.0, source on the Sources input (usecontextgeo='first' fix) and a default popforce gravity chained on Pre-Solve. | `name` (+38 optional) |
| `pop_source` | Add a typed particle emitter (popsource::2.0) into an existing POP dopnet and wire it onto the popsolver Sources input. | `dopnet` (+23 optional) |
| `pop_force` | Add ONE typed POP force into a POP dopnet and chain it onto the popsolver Pre-Solve input (forces chain, stacking cleanly). | `dopnet` (+54 optional) |
| `pop_import` | Pull simulated POP particles from a dopnet back to SOP via dopimport::2.0 (the data-only importer; dopio's presets menu does not populate headless). | `dopnet` (+7 optional) |
| `pop_collision` | Collide particles against a SOP/terrain collider (popcollisiondetect) inside a POP dopnet, chained onto Pre-Solve. | `dopnet` (+15 optional) |
| `pop_group` | Group or split a particle stream by TYPED rules (no VEX), chained onto Pre-Solve of a POP dopnet. op=group -> popgroup (tag into groupname; typed bounding region + random subset + boolean combination). op=stream -> popstream (split a named sub-stream by the same typed rules). | `dopnet` (+30 optional) |
| `pop_kill` | Kill / limit / clamp particles by TYPED rules (no VEX), chained onto Pre-Solve of a POP dopnet. op=kill -> popkill (typed bounding region + random subset). op=limit -> poplimit (hard domain box; clamp/bounce/wrap). op=softlimit -> popsoftlimit (soft push-back region). op=speedlimit -> popspeedlimit (clamp speed/spin). enablerule/randomcode never set. | `dopnet` (+36 optional) |
| `pop_property` | Shape per-particle attributes with TYPED POP property nodes (no VEX), chained onto Pre-Solve of a POP dopnet. op=physical -> popproperty (pscale/mass/bounce/friction/drag/cling). op=color -> popcolor (constant/random/ramp/blend Cd + alpha). op=sprite -> popsprite (camera cards). op=velocity -> popvelocity. op=lookat/torque -> orient. | `dopnet` (+39 optional) |
| `pop_instance` | Instancing / render handoff for a POP dopnet (no VEX). op=instance -> popinstance (write instancepath so points instance a SOP at render time; chains onto Pre-Solve). op=replicate -> popreplicate (birth children per parent for secondary sprays; wires onto the Sources input). | `dopnet` (+26 optional) |
| `pop_cache` | BUILD (never write) a File Cache 2.0 SOP after a pop_import node to cache simulated particles to disk. | 12 optional |
| `pop_flock` | Boids / steering for a POP dopnet (no VEX), chaining ONE behaviour node onto Pre-Solve. behavior selects popflock/popinteract/popsteer{seek,avoid,wander,separate,cohesion,align,obstacle}/popproximity. popsteercustom (VEX) is excluded; every uselocal* field (incl. wander's noise preset) is left at default. | `dopnet`, `behavior` (+43 optional) |
| `pop_scatter_sim` | Terrain/scan particle-scatter MACRO (the flip_flood analogue): ONE call composes the whole POP lane into a fresh /obj geo — emit geo -> dopnet(popobject+popsource) -> popsolver + a typed force preset -> optional pop_collision against a terrain/scan collider -> dopimport back to SOP -> optional copy_to_points render handoff. | `name` (+14 optional) |
| `sim_pyro` | Pyro (fire/smoke): MIGRATED to the modern SOP lane pyrosource -> SOP pyrosolver (self-bounding container) + optional collisionsource::2.0 collider. | `name` (+75 optional) |
| `pyro_source` | Pyro emission source (pyrosource SOP): rasterizes geo/points into source fields (density/temperature/fuel/burn/vel) that feed a pyrosolver's Sources input. | `input` (+10 optional) |
| `pyro_collision` | Geometry/terrain -> pyro collision volume (Collision Source 2.0 SOP): the scene-collision bridge; feed into a pyrosolver's Collision input so smoke deflects off a DEM, buildings, or RBD debris. | `input` (+10 optional) |
| `pyro_ground` | Ground/wildfire macro: DEM heightfield -> collider + pyrosource over an emission region -> SOP pyrosolver (tuned per type + wind) -> volumevisualization. | `name`, `input` (+22 optional) |
| `pyro_burst` | Pyro explosion/fireball source (pyroburstsource SOP): turns input points into an explosion/shockwave/muzzle/ring shell + trailing embers feeding a pyrosolver's Sources input. | `input` (+25 optional) |
| `pyro_explosion` | Explosion macro: single burst point at center -> pyroburstsource (explosion + embers) -> SOP pyrosolver (hot fireball) -> volumevisualization. | `name` (+30 optional) |
| `pyro_visualize` | Viewport look for a pyro/volume field (volumevisualization SOP): cheap viewport shading only, NOT a render. | `input` (+14 optional) |
| `pyro_shade` | Render-ready shading fields for a pyro volume (pyrobakevolume SOP): the Karma render-prep node; bakes smoke/fire/scatter look + assigns a Pyro material. | `input` (+25 optional) |
| `pyro_post` | Export/render prep for a pyro sim (pyropostprocess::2.0 SOP): computes field min/max (Karma needs them) + optional native->VDB conversion for a .vdb sequence. | `input` (+11 optional) |
| `pyro_cache` | BUILD (never write) a File Cache 2.0 SOP after a pyro sim, with a confined explicit write path + bgeo/vdb filetype. | `input`, `file` (+7 optional) |
| `whitewater_source` | Whitewater emission source (Whitewater Source 3.0 SOP): emission masks that decide where foam/spray/bubbles are born from a FLIP liquid sim. | `input` (+21 optional) |
| `sim_whitewater` | Whitewater (foam/spray/bubble): MIGRATED to the modern SOP lane whitewatersource::3.0 -> whitewatersolver (SOP) -> optional post. | 39 optional |
| `whitewater_post` | Whitewater post-process (Whitewater Post Process SOP): shapes solved foam/spray/bubble for render — density/pscale ramps, particles/fog/mesh output, container clip. | `input` (+17 optional) |
| `fluid_surface` | Mesh FLIP particles into a fluid surface (Particle Fluid Surface 3.0 SOP). | `input` (+19 optional) |
| `flip_volume_combine` | Combine a LOW-resolution FLIP sim's fields with HIGH-resolution detail for UP-RESSING (flipvolumecombine) — the H20 up-res workflow: sim cheap at low res, blend in high-frequency surface/velocity detail only where it matters. input=low-res fields (in0); high_res=high-res fields (in1); container=high-res reference container (in2); clip_bbox=clipping box (in3), all cross-network auto-bridged. | `input` (+14 optional) |
| `flip_cache` | BUILD (never write) a File Cache 2.0 SOP after a sim, with a confined explicit write path. | `input`, `file` (+6 optional) |
| `sim_ripple` | Cheap surface waves via the Ripple Solver SOP on a grid (rest geometry on input 0). | `name` (+8 optional) |
| `sim_grains` | Granular PBD (sand/snow/wet-sand/debris): a SOP dopnet (input0=emit geo) wrapping popobject -> popsolver::2.0 with a popgrains PBD solver ATTACHED via the solver's 'Solvers to be attached' input + a default gravity popforce. | `name` (+35 optional) |
| `set_constraint_field` | Set / author / name / break RBD (rigid-body destruction) constraint-network attributes by group, as typed LITERAL values via an attribcreate::2.0 — the data-only, zero-VEX / zero-wrangle way to control glue/hard/soft bonds on a fracture: constraint_name (the relationship type the solver maps — Glue/Hard/Soft or a custom name), next_constraint_name (what a bond becomes when it breaks), strength (the breaking threshold), restlength (soft/spring rest length), broken (pre-broken flag 0\|1). | `input` (+8 optional) |
| `glue_cluster` | Chunk / cluster fractured RBD pieces so a structure breaks in CHUNKS or slabs instead of per-shard (gluecluster SOP) — the single most-used destruction art-direction control for buildings/walls collapsing in coherent sections. | `input` (+14 optional) |
| `rbd_constraints_from_curves` | Build / route an RBD (rigid-body destruction) constraint network ALONG user curves (rbdconstraintsfromcurves SOP) — custom bond routing for rebar, cables, chains, stitching, or hand-drawn break lines, and the SOP-reachable HINGE (mechanical) connection type. | `input`, `curves` (+11 optional) |
| `rbd_constraints_from_lines` | Build an RBD (rigid-body destruction) constraint network from explicit LINE SEGMENTS (rbdconstraintsfromlines SOP) — the data-only form of the interactive handle-drawn line tool: each line, given as a literal point-pair, routes a bond between the fractured pieces it crosses. | `input`, `lines` (+13 optional) |
| `rbd_group_constraints` | Name / group / organize an RBD (rigid-body destruction) constraint network into a targetable named primitive group (rbdgroupconstraints SOP) so a solver, set_constraint_field, or rbd_constraint_properties can select those bonds. | `input`, `constraints` (+6 optional) |
| `voronoi_adjacency` | Build the piece-ADJACENCY graph / bond topology (which fractured pieces touch which) from a voronoi fracture (voronoiadjacency SOP) — the adjacency polylines that RBD (rigid-body destruction) constraint networks are routed along. | `input` (+1 optional) |
| `sim_viscosity` | Viscous FLIP scaffold (slushy / meltwater / honey / lava): a flipcontainer + flipsolver with viscosity force-enabled. | `name` (+11 optional) |
| `ocean_surface` | Flat spectral large-water OCEAN / SEA surface — a grid displaced by an ocean spectrum (Ocean Evaluate 2.0) into rolling waves. | `name` (+7 optional) |
| `ocean_spectrum` | Author a full ocean-wave SPECTRUM (Ocean Spectrum) + evaluate it onto a large grid — the deep 'look' controls ocean_surface can't reach: spectrum model, water depth, swell, fetch, wind direction/bias, deterministic seed + seamless loop. | `name` (+29 optional) |
| `ocean_evaluate` | Deform ARBITRARY geometry by an ocean SPECTRUM (SOP-level Ocean Evaluate). | `input`, `spectrum` (+9 optional) |
| `ocean_foam` | Generate FOAM / whitewater / spray points from an ocean surface's cusp (Ocean Foam SOP) — the sea-foam layer on breaking crests. | `input` (+17 optional) |
| `ocean_source` | Couple an ocean spectrum into a FLIP fluid tank (Ocean Source 2.0) — the scaffold that seeds a splashing-water / breaking-wave FLIP sim from the spectral ocean. particlesep = FLIP particle separation; waterlevel = rest sea level. | `name` (+4 optional) |
| `point_velocity` | Author the point velocity attribute v (Point Velocity SOP) — the FX seed-velocity workhorse. | `input` (+10 optional) |
| `volume_velocity` | Author a velocity VOLUME (Volume Velocity SOP) — the non-simulated 'wind tunnel' velocity field that drives crest-spray / snow / rain via pop_force(advect). input = the volume/VDB to write into; optional points input rasterizes v. | `input` (+9 optional) |
| `debris_source` | Emit a secondary-DEBRIS source (Debris Source SOP) off a fractured/static piece surface — the per-frame emission map (density/age/distance attribs) feeding an emit-RBD or POP secondary 'juice' sim. | `input` (+7 optional) |
| `cloud` | Volumetric CLOUD primitive (cumulus / sky cloud / fog volume density field): source geo -> Cloud 2.0 (SDF/density/narrow-band) -> Cloud Noise (billowy/wispy displacement) -> optional Cloud Adjust Density Profile (base/anvil shaping). | `name` (+25 optional) |
| `cloud_shape` | Generate a MODERN art-directable cloud with the H20+ Cloud Shape toolset (cloudshapegenerate) — the replacement for the deprecated monolithic `cloud`. | `name` (+18 optional) |
| `cloud_billowy_noise` | Billowing cauliflower displacement on a cloud DENSITY VDB (cloudbillowynoise) — the modern high-detail cumulus modifier. | `input` (+16 optional) |
| `cloud_wispy_noise` | Wispy / streaky velocity-advected displacement on a cloud DENSITY VDB (cloudwispynoise) — cirrus, stretched anvils, wind-blown wisps. | `input` (+11 optional) |
| `cloud_clip` | Clip / cut a cloud DENSITY VDB with a plane + optional noise (cloudclip) — flat cumulus bases, sheared anvils, sliced tops. | `input` (+11 optional) |
| `solver` | Generic SOP feedback / time-loop solver -- the general-purpose iterative primitive (accumulative erosion, growth, cellular automata, any per-frame feedback), distinct from the DOP sim_* family. | `input` (+6 optional) |
| `sim_vellum` | Vellum (XPBD) master (SOP): source -> Vellum Constraints -> Vellum Solver. | `name` (+65 optional) |
| `vellum_collision` | Wire an external/terrain collider into a Vellum solver's Collision Geometry input (index 2) and tune collision response. | `solver`, `collider` (+14 optional) |
| `vellum_attach` | Attach Vellum cloth/geometry to a (moving) RIG — the dedicated Vellum Attach Constraints SOP. | `input`, `rig` (+9 optional) |
| `vellum_constraint` | Layer an ADDITIONAL Vellum constraint onto an existing chain (welds/glue/pins/attach/stitch/struts) via the second-input append. | `solver` (+36 optional) |
| `vellum_force` | External forces on a Vellum solve. | 24 optional |
| `vellum_drape` | Rest state / pre-roll settle. | `solver` (+29 optional) |
| `vellum_source` | Continuous emission / add constraint patches mid-sim (DOP-scoped, advanced -- the only Vellum tool that drops to DOP). | 12 optional |
| `vellum_post` | Render prep for a Vellum sim (vellumpostprocess SOP): hair-tube generation, smoothing (subdivide), detangle, rigidity. | `input` (+15 optional) |
| `vellum_cache` | BUILD (never write) a File Cache 2.0 SOP after a Vellum sim. | `input`, `file` (+8 optional) |
| `sim_mpm` | MPM (Material Point Method) network (SOP): source -> mpmsource -> mpmsolver. | `name` (+24 optional) |
| `mpm_collider` | Give an MPM sim something to COLLIDE with / INTERACT with — wire a collider into an existing mpmsolver's MPM Colliders input (index 1). | `solver`, `collider` (+11 optional) |
| `mpm_container` | Bound an MPM sim's DOMAIN and set its MASTER resolution — wire an `mpmcontainer` into an existing mpmsolver's MPM Container input (index 2). | `solver` (+9 optional) |
| `mpm_surface` | Make an MPM sim RENDERABLE — mesh / surface the sim particles by building an `mpmsurface` after them. | `input` (+14 optional) |
| `mpm_postfracture` | Sim-THEN-fracture an MPM destruction shot — fracture hi-res geometry driven by where the MPM sim actually stretched and broke it, so the cracks follow the real deformation (unlike pre-fracturing). | `geo`, `particles` (+11 optional) |
| `mpm_deformpieces` | Retarget an MPM sim onto pre-fractured NAMED pieces — drive rigid or hi-res render chunks by a (cheaper) MPM sim so the final geometry deforms/moves with the solve without simming the hi-res directly. | `pieces`, `particles` (+8 optional) |
| `mpm_debrissource` | Emit SECONDARY debris from an MPM sim — spawn extra chunks/particles where the material stretches hard, moves fast, or is near the surface (the shrapnel / spray / spark pass on top of a destruction or impact sim). | `input` (+10 optional) |
| `glue_constraint` | KineFX Glue Constraint Relationship (glueconrel) — DOP constraint-relationship data node that glues bound objects until an impulse over `strength` breaks the bond, then propagates the break. | 10 optional |
| `hard_constraint` | KineFX Hard Constraint Relationship (hardconrel) — stiff DOP relationship pinning bound objects to a rest length, with optional angular motors and solver stiffness (CFM/ERP). | 14 optional |
| `no_constraint` | KineFX No Constraint Relationship (noconrel) — DOP relationship that makes bound objects mutual affectors WITHOUT any constraint force (collision-only / placeholder). | 7 optional |
| `bullet_soft_constraint` | KineFX Bullet Soft Constraint Relationship (bulletsoftconrel) — springy Bullet relationship with linear + optional angular stiffness/damping and optional plasticity (permanent deformation past a threshold). | 18 optional |
| `cone_twist_constraint` | KineFX Cone Twist Constraint Relationship (conetwistconrel) — Bullet cone-twist joint limiting twist/out/up rotation within a cone, with an optional soft limit and motor. | 20 optional |
| `constraint_relationship` | KineFX Constraint Relationship (conrelationship) — the generic relationship data node defining how two bound objects relate (type + two-state break / spring parameters). | 10 optional |
| `apply_constraint` | KineFX Constraint (constraint) — applies a named constraint relationship between `affected` and `affector` sim objects (the DOP node that binds a relationship to objects). | 11 optional |
| `constraint_network_relationship` | KineFX Constraint Network Relationship (constraintnetworkrelationship) — applies a relationship to a constraint NETWORK, optionally matching affected/affector objects by a point attribute. | 12 optional |
| `motion_data` | KineFX Motion (motion) — the DOP Motion data node carrying an object's position / pivot / rotation and linear + angular velocity (the initial-state / target motion for an RBD or agent object). | 11 optional |
| `softbody_constraint` | KineFX SBD Constraint (sbdconstraint) — a soft-body-dynamics constraint pinning (`type` 0) or spring-linking (`type` 1) constrained points of an object to a goal object/points/location, with optional force & length limits. | 19 optional |
| `cloth_stitch_constraint` | KineFX Cloth Stitch Constraint (clothstitchconstraint) — stitches constrained points of a cloth object to a goal object/points with a given stiffness & damping (`type` 0/1). | 11 optional |
| `fem_attach_constraint` | KineFX FEM Attach Constraint (femattachconstraint) — attaches points of a constrained FEM object to a goal object at a rest offset, with optional distance-threshold filtering. | 13 optional |
| `fem_fuse_constraint` | KineFX FEM Fuse Constraint (femfuseconstraint) — fuses matched points of two FEM objects (matched by ordered point group or by an identifier attribute) into a shared boundary. | 12 optional |
| `fem_region_constraint` | KineFX FEM Region Constraint (femregionconstraint) — constrains overlapping tetrahedral regions of two FEM objects together, optionally matching parts by an identifier attribute. | 10 optional |
| `fem_slide_constraint` | KineFX FEM Slide Constraint (femslideconstraint) — constrains points of a FEM object to slide along the surface of a goal object (connection model attract/repel), with optional distance-threshold filtering. | 14 optional |
| `fem_target_constraint` | KineFX FEM Target Constraint (femtargetconstraint) — softly pulls constrained points of a FEM object toward their animated target positions with a given stiffness & damping (`type` 0/1). | 9 optional |
| `ragdoll_solver` | WIRE-ONLY: build a KineFX ragdoll solver (kinefx::ragdollsolver) on the character/skeleton geometry (input 0). | `input` (+16 optional) |
| `muscle_solver` | WIRE-ONLY: build a muscle solver (musclesolver) on the muscle geometry (input 0). | `input` (+16 optional) |
| `muscle_solver_fem` | WIRE-ONLY: build a FEM muscle solver (musclesolverfem) on the muscle geometry (input 0). | `input` (+16 optional) |
| `muscle_solver_vellum` | WIRE-ONLY: build a Vellum muscle solver (musclesolvervellum) on the muscle geometry (input 0). | `input` (+16 optional) |
| `tissue_solver` | WIRE-ONLY: build a tissue (FEM flesh) solver (tissuesolver) on the tissue/skin geometry (input 0). | `input` (+12 optional) |
| `tissue_solver_vellum` | WIRE-ONLY: build a Vellum tissue solver (tissuesolvervellum) on the tissue geometry (input 0). | `input` (+15 optional) |
| `skin_solver_vellum` | WIRE-ONLY: build a Vellum skin solver (skinsolvervellum) on the skin geometry (input 0). | `input` (+16 optional) |
| `armature_deform` | WIRE-ONLY: build an armature deform solver (armaturedeform) on the character geometry (input 0) — quasistatic muscle/skin deformation. | `input` (+13 optional) |
| `fem_solver` | WIRE-ONLY: build a FEM soft-body solve cluster (femsolidobject -> femsolver) inside a fresh dopnet. | `name` (+33 optional) |
| `solid_object_solver` | WIRE-ONLY: build a solid/cloth FEM cluster (solidobject -> femsolver) inside a fresh dopnet. | `name` (+29 optional) |
| `filament_solver` | WIRE-ONLY: build a filament/strand dynamics cluster (filamentobject -> filamentsolver) inside a fresh dopnet. | `name` (+19 optional) |
| `crowd_solver` | WIRE-ONLY: build a crowd/creature agent solve cluster (crowdobject -> crowdsolver::3.0) inside a fresh dopnet, reading agents from the wired source (or an initial-geo SOP path). | `name` (+39 optional) |

### KineFX

| Tool | What it does | Key params |
|---|---|---|
| `character_skeleton` | KineFX Skeleton — the skeleton authoring container (kinefx::skeleton). | `skeleton` (+4 optional) |
| `configure_joints` | KineFX Configure Joints — writes solver-configuration attributes onto a skeleton (input 0) for Full Body IK / Ragdoll / Rig Pose. | `skeleton` (+15 optional) |
| `configure_joint_limits` | KineFX Configure Joint Limits — sets rotation/translation joint limits + limit-guide display on a skeleton (input 0). | `skeleton` (+14 optional) |
| `orient_joints` | KineFX Orient Joints — recomputes joint orientations (the `transform` point attrib) for a skeleton (input 0), aiming each joint at its child with a reference/up vector. | `skeleton` (+10 optional) |
| `parent_joints` | KineFX Parent Joints — reparents joints in a skeleton hierarchy (input 0). | `skeleton` (+2 optional) |
| `delete_joints` | KineFX Delete Joints — deletes (or keeps only) the joints named by `group` from a skeleton (input 0), optionally cascading to children. | `skeleton` (+5 optional) |
| `group_joints` | KineFX Group Joints — creates/updates a named point group of joints on a skeleton (input 0) from a selection expression, with a boolean merge against any existing group. | `skeleton` (+7 optional) |
| `skeleton_blend` | KineFX Skeleton Blend — blends the pose of one or more skeletons into a base skeleton. | `skeleton` (+14 optional) |
| `skeleton_mirror` | KineFX Skeleton Mirror — mirrors joints of a skeleton (input 0) across a plane or point, renaming mirrored joints via find/replace tokens (e.g. | `skeleton` (+13 optional) |
| `rig_doctor` | KineFX Rig Doctor — validates & repairs a skeleton: initializes missing joint names / transforms, sanitizes names, and outputs hierarchy attributes (parent index, child indices, evaluation order) from a rig on input 0. | `skeleton` (+16 optional) |
| `visualize_rig` | KineFX Visualize Rig — generates rig-visualization geometry (joint gnomons / bone links, styled by color/scale) from a skeleton on input 0. | `skeleton` (+11 optional) |
| `rig_pose` | KineFX Rig Pose — the interactive FK/IK posing SOP on a skeleton (input 0). | `skeleton` (+16 optional) |
| `compute_rig_pose` | KineFX Compute Rig Pose — evaluates a rig pose from a skeleton (input 0) and bakes the resulting transforms / parameter attributes onto the geometry (the headless twin of rig_pose). | `skeleton` (+15 optional) |
| `rig_match_pose` | KineFX Rig Match Pose — poses `skeleton` (input 0, the target rig) to match the pose of `source` (input 1, the source rig), optionally aligning by bounding box and a reference frame. | `skeleton`, `source` (+18 optional) |
| `rig_mirror_pose` | KineFX Rig Mirror Pose — mirrors the animated POSE of a skeleton (input 0) across a symmetry axis/plane, matching left/right joints by name tokens (e.g. | `skeleton` (+21 optional) |
| `rig_stash_pose` | KineFX Rig Stash Pose — stores the current pose of a skeleton (input 0) into a point attribute (`mode`=store) or restores a previously stashed pose (`mode`=restore). | `skeleton` (+12 optional) |
| `rig_copy_transforms` | KineFX Rig Copy Transforms — copies joint transforms from `source` (input 1) onto `skeleton` (input 0, the destination rig), pairing joints by a mapping attribute or a match attribute. | `skeleton`, `source` (+6 optional) |
| `ik_chains` | KineFX IK Chains — solves two-bone IK chains on a skeleton (input 0) toward goal positions supplied as `targets` (input 1). | `skeleton`, `targets` (+2 optional) |
| `full_body_ik` | KineFX Full Body IK — solves a whole-skeleton IK pose on `skeleton` (input 0) so the configured effector joints reach their targets; optional `targets` (input 1) supplies goal geometry. | `skeleton` (+25 optional) |
| `fbik_configure_targets` | KineFX Full Body IK Configure Targets — writes the FBIK target configuration (per-joint offsets, rest-pose reference, center-of-mass target) onto a skeleton (input 0); optional input 1 supplies target geometry. | `skeleton` (+13 optional) |
| `spline_ik` | KineFX Spline IK — drives a joint chain of a skeleton (input 0) along a spline fitted through the joints, giving smooth curve-based control (spines, tails, tentacles). | `skeleton` (+17 optional) |
| `reverse_foot` | KineFX Reverse Foot — builds a reverse-foot roll setup on a skeleton (input 0), adding heel/ball/toe pivot markers so a foot can roll and pivot. | `skeleton` (+8 optional) |
| `stabilize_joint` | KineFX Stabilize Joint — removes jitter / locks a joint of an animated skeleton (input 0) in place over a frame range, with position/angle change limits and blend in/out. | `skeleton` (+21 optional) |
| `pose_difference` | KineFX Pose Difference — computes the per-joint difference between the pose on `skeleton` (input 0) and the `reference` pose (input 1), storing it in an output attribute (optionally position/rotation/scale only, inverted, or applied as an offset). | `skeleton`, `reference` (+12 optional) |
| `joint_capture_biharmonic` | KineFX Joint Capture Biharmonic (kinefx::jointcapturebiharmonic) — computes smooth boneCapture skinning weights by solving biharmonic functions over an internally-tetrahedralized `geometry` (input 0) using the `skeleton` (input 1) as the influence rig. | `geometry`, `skeleton` (+22 optional) |
| `joint_capture_proximity` | KineFX Joint Capture Proximity (kinefx::jointcaptureproximity) — assigns boneCapture skinning weights to `geometry` (input 0) by proximity to the `skeleton` (input 1) bones. | `geometry`, `skeleton` (+11 optional) |
| `point_capture_biharmonic` | KineFX Point Capture Biharmonic (kinefx::pointcapturebiharmonic) — biharmonic point-cloud capture of `geometry` (input 0) to the `skeleton` (input 1). | `geometry`, `skeleton` (+3 optional) |
| `joint_capture_paint` | KineFX Joint Capture Paint (kinefx::jointcapturepaint) — initializes / normalizes boneCapture weights on `geometry` (input 0) against the `skeleton` (input 1). | `geometry`, `skeleton` (+5 optional) |
| `capture_packed_geo` | KineFX Capture Packed Geo (kinefx::capturepackedgeo) — transfers/packs the capture on `geometry` (input 0) against the `skeleton` (input 1), optionally packing the input, matching by name, and unpacking the result. | `geometry`, `skeleton` (+13 optional) |
| `capture_proximity` | Classic Capture Proximity (captureproximity) — proximity capture of `geometry` (input 0) to the capture regions on `skeleton` (input 1; a KineFX skeleton whose per-point transform supplies the regions). | `geometry`, `skeleton` (+18 optional) |
| `bone_capture` | Classic Capture (capture) — assigns capture weights to `geometry` (input 0) from the capture regions on `skeleton` (input 1). | `geometry`, `skeleton` (+13 optional) |
| `bone_capture_lines` | Classic Bone Capture Lines (bonecapturelines) — generates classic capture-region line geometry (carrying boneCapture) from the `skeleton` (input 0), for feeding classic capture solvers. | `skeleton` (+17 optional) |
| `capture_region` | Classic Capture Region (cregion) — a 0-input SOURCE that emits one capture-region primitive (a tube with a transform) inside a fresh /obj geo. | `name` (+7 optional) |
| `capture_mirror` | Classic Capture Mirror (capturemirror) — mirrors capture weights on already-captured `geometry` (input 0) across a plane, renaming mirrored regions via find/replace tokens. | `geometry` (+10 optional) |
| `capture_correct` | Classic Capture Correct (capturecorrect) — cleans up capture weights on already-captured `geometry` (input 0): update/remove stale regions, clamp negative/positive weights, limit influences per point, and renormalize. | `geometry` (+14 optional) |
| `capture_override` | Classic Capture Override (captureoverride) — overrides capture weights on already-captured `geometry` (input 0) for the named `cregions`, applying an operation at a set weight. | `geometry` (+8 optional) |
| `name_from_capture_weight` | Labs Name From Capture Weight (labs::name_from_capture_weight::1.0) — writes a point `name` attribute on already-captured `geometry` (input 0) from each point's dominant capture region (its heaviest boneCapture weight). | `geometry` (+3 optional) |
| `skinning_converter` | Labs Skinning Converter (labs::skinning_converter::3.0) — converts a vertex-animated / deforming `geometry` (input 0, time-dependent) into a skeleton + boneCapture skinning weights (a DemBones-family solve over frame_start..frame_end). | `geometry` (+18 optional) |
| `dembones_skinning_converter` | KineFX DemBones Skinning Converter (kinefx::dembones_skinningconverter) — WIRE-ONLY: builds + wires + configures the DemBones external solve that converts an Alembic-cached deforming mesh into a skeleton + skin weights, but NEVER executes it (mirrors maps_baker — an external/heavy solve is fired by the human). | `geometry` (+17 optional) |
| `joint_deform` | KineFX Joint Deform (kinefx::jointdeform) — deforms captured skin by joint transforms. | `skin`, `rest_skeleton`, `deform_skeleton` (+8 optional) |
| `bone_deform` | KineFX Bone Deform (bonedeform) — deforms capture-weighted geometry using bone/joint capture attributes. | `skin` (+12 optional) |
| `deform_skeleton_skin` | KineFX Deform Skeleton/Skin (kinefx::deformskelskin) — poses a skeleton (input 0) and deforms the bound skin (optional input 1) together, then outputs the transformed rig/skin. | `skeleton` (+12 optional) |
| `pose_space_deform_combine` | KineFX Pose-Space Deform Combine (posespacedeformcombine) — merges multiple Pose-Space Deform outputs (input 0..N) into a single corrective result. | `geometry` (+3 optional) |
| `pose_space_edit_configure` | KineFX Pose-Space Edit Configure (posespaceeditconfigure) — sets how Pose-Space Edit computes shape differences (pre/post-deform, orient) on geometry (input 0), optionally re-deforming with bone capture. | `geometry` (+7 optional) |
| `character_blend_shapes_add` | KineFX Character Blend Shapes Add (kinefx::characterblendshapesadd) — packs a new blend-shape (or in-between) target (input 1) onto a base mesh (input 0). | `base` (+10 optional) |
| `character_blend_shapes_core` | KineFX Character Blend Shapes Core (kinefx::characterblendshapescore) — the low-level weighted blend evaluator: input 0 = base mesh, input 1 = packed blend targets + weights. | `base`, `blend_targets` (+6 optional) |
| `character_blend_shapes_extract` | KineFX Character Blend Shapes Extract (kinefx::characterblendshapesextract) — extracts a single named blend-shape (or in-between) target mesh out of a packed blendshape input (input 0). | `blendshape_geo` (+5 optional) |
| `character_blend_shape_channels` | KineFX Character Blend Shape Channels (kinefx::characterblendshapechannels) — defines/updates the blend-shape channel table (weights) for a mesh (input 0), optionally seeded from a second input. | `mesh` (+3 optional) |
| `character_blend_shapes` | KineFX Character Blend Shapes (kinefx::characterblendshapes) — the all-in-one blendshape node: input 0 = base mesh, input 1 = blend-shape meshes, input 2 = channel definitions; applies the weighted blends. | `mesh`, `blend_shapes`, `channels` (+4 optional) |
| `blend_shapes` | Classic Blend Shapes (SOP blendshapes::2.0) — weighted morph of a base mesh (input 0) toward one or more target shapes (input 1..N). | `base` (+14 optional) |
| `secondary_motion` | KineFX Secondary Motion (kinefx::secondarymotion) — adds overlapping/jiggle/spring follow-through to an animated skeleton (input 0). | `skeleton` (+21 optional) |
| `dynamic_warp` | KineFX Dynamic Warp (kinefx::dynamicwarp) — time-warps a source animation (input 1) to align with a reference animation (input 0) using dynamic time warping over matched attributes. | `reference_motion`, `source_motion` (+12 optional) |
| `skeleton_deform` | KineFX/Classic Deform (SOP `deform`) — deforms capture-weighted geometry (input 0) by a skeleton referenced through `skel_root_path` (an in-scene node reference). | `skin` (+15 optional) |
| `motion_clip` | KineFX MotionClip — PACKS an animated skeleton (input 0) sampled across a frame range into a single-frame packed motionclip (channel primitives). | `skeleton` (+17 optional) |
| `motion_clip_create` | KineFX MotionClip Create — builds a motionclip from a live SOP (mode single/fetchsop + source_sop), a clip library, or an imported .bgeo/FBX clip. | 18 optional |
| `motion_clip_compute_create` | KineFX Compute MotionClip Create — packs the animated skeleton at `source_sop` (a Houdini node path) over a frame range into a motionclip using the compute engine (0 geometry inputs). | `parent` (+5 optional) |
| `motion_clip_compute_retime` | KineFX Compute MotionClip Retime — retimes a motionclip (input 0) via the compute engine: shift / absolute time / frame / speed, with optional trim and output range/sample-rate resampling. | `motionclip` (+22 optional) |
| `motion_clip_retime` | KineFX MotionClip Retime — retimes a motionclip (input 0): shift / absolute time / frame / speed, with optional trim, per-frame time/frame/speed overrides, and output range/sample-rate resampling. | `motionclip` (+27 optional) |
| `motion_clip_velocity` | KineFX MotionClip Compute Velocity — computes per-joint velocities on a motionclip (input 0); optional `rest_frame` (input 1) supplies the rest pose. | `motionclip` (+13 optional) |
| `motion_clip_cycle` | KineFX MotionClip Cycle — repeats a motionclip (input 0) before/after itself to build a loop, with locomotion continuity (shift/velocity/mirror) and pose blending at the seam. | `motionclip` (+18 optional) |
| `motion_clip_evaluate` | KineFX MotionClip Evaluate — samples a motionclip (input 0) at a frame back to a live skeleton pose (current frame or a custom frame), with optional COM output and end-behavior. | `motionclip` (+14 optional) |
| `motion_clip_extract` | KineFX MotionClip Extract — extracts poses from a motionclip (input 0) as per-frame skeletons or motion trails over a frame range. | `motionclip` (+16 optional) |
| `motion_clip_key_poses` | KineFX MotionClip Extract Key Poses — reduces a motionclip (input 0) to its key poses (by percentage or count), either extracting them or tagging them. | `motionclip` (+17 optional) |
| `motion_clip_locomotion` | KineFX MotionClip Extract Locomotion — separates a motionclip's (input 0) root locomotion from its in-place motion (compute / prim / joint source), optionally extracting the ground trajectory or flattening the clip in place. | `motionclip` (+15 optional) |
| `motion_clip_merge` | KineFX MotionClip Merge — merges two motionclips (input 0 + optional `merge_clip` on input 1) into one clip stream. | `input` (+5 optional) |
| `motion_clip_pose_delete` | KineFX MotionClip Pose Delete — deletes poses (and/or joints) from a motionclip (input 0) by frame range, frame pattern, pose range, or pose group. | `motionclip` (+13 optional) |
| `motion_clip_pose_insert` | KineFX MotionClip Pose Insert — inserts a single skeleton pose (`pose`, input 1) into a motionclip (input 0) at a frame. | `motionclip`, `pose` (+3 optional) |
| `motion_clip_sequence` | KineFX MotionClip Sequence — concatenates two motionclips end to end: `first` (input 0) then `second` (input 1), with locomotion continuity and a blended seam. | `first`, `second` (+18 optional) |
| `motion_clip_blend` | KineFX MotionClip Blend — layers a `layer` motionclip (input 1) over a `base` motionclip (input 0) with fade-in/fade-out envelopes and a per-joint blend effect. | `base`, `layer` (+19 optional) |
| `motion_clip_unpack` | KineFX MotionClip Unpack — unpacks a motionclip (input 0) back to a live animated skeleton (single frame / range / current frame) or motion trails, carrying a `time` point attribute. | `motionclip` (+20 optional) |
| `motion_clip_update` | KineFX MotionClip Update — updates a motionclip (input 0) with new poses from `poses` (input 1) — an unpacked skeleton STREAM that MUST carry a `time` point attribute (e.g. a motion_clip_unpack output). | `motionclip`, `poses` (+9 optional) |
| `motion_clip_info` | KineFX MotionClip Create Clip Info — ensures a motionclip (optional input 0) carries a `clipinfo` detail attribute, deriving it from the clip's `time` prim attribute when missing. | 3 optional |
| `motion_mixer_retime` | KineFX Motion Mixer Retime — retimes a motion-mixer / motionclip scene (input 0) by absolute frame, time, playback speed, or hold. | `input` (+9 optional) |
| `motion_mixer_smooth` | KineFX Motion Mixer Smooth — Butterworth-filters the channels of a motion-mixer / motionclip scene (input 0) selected by `pattern`, over the t/r/s components. | `input` (+9 optional) |
| `motion_mixer_transform` | KineFX Motion Mixer Transform — applies a TRS(+shear/pivot) transform to the channels of a motion-mixer / motionclip scene (input 0) selected by `group`. | `input` (+10 optional) |
| `fbx_character_import` | KineFX FBX Character Import — imports a full FBX character (skeleton on output 0, skin on output 1, blendshapes on output 2), optionally merging animation from a second FBX, into a fresh /obj geo. | `name`, `fbx_file` (+15 optional) |
| `fbx_anim_import` | KineFX FBX Animation Import — imports an animated skeleton (a motion clip) from an FBX file into a fresh /obj geo. | `name`, `fbx_file` (+14 optional) |
| `fbx_skin_import` | KineFX FBX Skin Import — imports the skinned mesh (carrying `boneCapture` weights) from an FBX character into a fresh /obj geo. | `name`, `fbx_file` (+8 optional) |
| `gltf_character_import` | KineFX glTF Character Import — imports a full glTF/glb character (skeleton output 0, skin output 1, blendshapes output 2) into a fresh /obj geo. | `name`, `gltf_file` (+7 optional) |
| `gltf_anim_import` | KineFX glTF Animation Import — imports an animated skeleton (motion clip) from a glTF/glb file into a fresh /obj geo. | `name`, `gltf_file` (+5 optional) |
| `gltf_skin_import` | KineFX glTF Skin Import — imports the skinned mesh (carrying `boneCapture` weights) from a glTF/glb character into a fresh /obj geo. | `name`, `gltf_file` (+2 optional) |
| `usd_character_import` | KineFX USD Character Import — imports a USDSkel character (skeleton output 0, skin output 1, blendshapes output 2) from a USD file into a fresh /obj geo (forces the file source, not a /stage LOP). | `name`, `usd_file` (+7 optional) |
| `usd_anim_import` | KineFX USD Animation Import — imports an animated skeleton (motion clip) from a USDSkel file into a fresh /obj geo (forces the file source). | `name`, `usd_file` (+7 optional) |
| `usd_skin_import` | KineFX USD Skin Import — imports the skinned mesh (carrying `boneCapture` weights) from a USDSkel character into a fresh /obj geo (forces the file source). | `name`, `usd_file` (+3 optional) |
| `mocap_import` | KineFX Mocap Import — imports raw motion-capture data (Biovision BVH, Acclaim ASF+AMC, or Motion-Analysis TRC) as an animated skeleton into a fresh /obj geo. | `name` (+20 optional) |
| `clip_import` | KineFX Clip Import — reads a .bclip/.clip CHOP motion clip off disk and (optionally, when a `skeleton` input 0 is supplied) applies it to that skeleton; otherwise emits the clip into a fresh /obj geo. | `name`, `file` (+5 optional) |
| `retarget_biped_fbx` | KineFX Retarget Biped FBX — imports a biped FBX and retargets its animation onto the KineFX biped template (skeleton output 0, anim output 1, skin output 2) in a fresh /obj geo. | `name`, `fbx_file` (+9 optional) |
| `character_io` | KineFX Character IO — assembles a KineFX character from its parts: input0 = rest `geometry`, input1 = `capture_pose` skeleton (optional), input2 = `animated_pose` skeleton/motionclip (optional). | `geometry` (+13 optional) |
| `fbx_anim_export` | KineFX FBX Animation Output — WIRE-ONLY. | `geometry` (+17 optional) |
| `fbx_character_export` | KineFX FBX Character Output — WIRE-ONLY. | `skin_geo`, `capture_pose` (+20 optional) |
| `gltf_character_export` | KineFX glTF Character Output — WIRE-ONLY. | `skin_geo`, `capture_pose` (+13 optional) |
| `clip_export` | KineFX Clip Export — WIRE-ONLY. | `geometry` (+8 optional) |
| `scene_character_export` | KineFX Scene Character Export — WIRE-ONLY. | `geometry`, `skeleton` (+7 optional) |
| `retarget_fbx_export` | KineFX Retarget FBX Export — WIRE-ONLY. | `geometry` (+18 optional) |
| `classic_bone` | KineFX/Classic Bone (OBJ `bone`) — creates one classic Bone object: a length-parameterized bone with a bonelink display and adjustable capture / deform capture-region cylinders (the pre-KineFX skinning primitive). | 14 optional |
| `dembones_skinning_export` | KineFX/Classic DemBones Skinning Converter ROP (/out `dembones_skinningconverter`) — WIRE-ONLY: builds + configures the DemBones external solve that converts an animated Alembic cache (+ optional bind-pose FBX) into a skeleton + skin-weighted FBX, but NEVER executes it (mirrors maps_baker — the heavy external solve is fired by the human). | 19 optional |
| `deform_bone_rig_biped_arm` | KineFX/Classic Deform Bone Rig — Biped Arm (OBJ `deform_bone_rig_biped_arm`) — instantiates a ready-made classic bone deformation rig for a biped arm (collarbone/upper-arm/forearm/wrist bones with capture regions). | 9 optional |
| `deform_bone_rig_biped_hand_4f_2s` | KineFX/Classic Deform Bone Rig — Biped Hand, 4 Fingers / 2 Segments (OBJ `deform_bone_rig_biped_hand_4f_2s`) — ready-made classic bone deformation rig for a 4-finger, 2-segment hand. | 9 optional |
| `deform_bone_rig_biped_hand_4f_3s` | KineFX/Classic Deform Bone Rig — Biped Hand, 4 Fingers / 3 Segments (OBJ `deform_bone_rig_biped_hand_4f_3s`) — ready-made classic bone deformation rig for a 4-finger, 3-segment hand. | 9 optional |
| `deform_bone_rig_biped_hand_5f_3s` | KineFX/Classic Deform Bone Rig — Biped Hand, 5 Fingers / 3 Segments (OBJ `deform_bone_rig_biped_hand_5f_3s`) — ready-made classic bone deformation rig for a full 5-finger, 3-segment hand. | 9 optional |
| `deform_bone_rig_biped_head_and_neck` | KineFX/Classic Deform Bone Rig — Biped Head and Neck (OBJ `deform_bone_rig_biped_head_and_neck`) — ready-made classic bone deformation rig for a biped head + neck chain. | 9 optional |
| `deform_bone_rig_biped_leg` | KineFX/Classic Deform Bone Rig — Biped Leg (OBJ `deform_bone_rig_biped_leg`) — ready-made classic bone deformation rig for a biped leg (thigh/shin/foot bones with capture regions). | 9 optional |
| `deform_bone_rig_biped_spine_3pc` | KineFX/Classic Deform Bone Rig — Biped Spine, 3 Pieces (OBJ `deform_bone_rig_biped_spine_3pc`) — ready-made 3-segment classic bone deformation rig for a biped spine. | 9 optional |
| `deform_bone_rig_biped_spine_5pc` | KineFX/Classic Deform Bone Rig — Biped Spine, 5 Pieces (OBJ `deform_bone_rig_biped_spine_5pc`) — ready-made 5-segment classic bone deformation rig for a biped spine. | 9 optional |
| `deform_bone_rig_quadruped_back_leg` | KineFX/Classic Deform Bone Rig — Quadruped Back Leg (OBJ `deform_bone_rig_quadruped_back_leg`) — ready-made classic bone deformation rig for a quadruped hind leg. | 9 optional |
| `deform_bone_rig_quadruped_front_leg` | KineFX/Classic Deform Bone Rig — Quadruped Front Leg (OBJ `deform_bone_rig_quadruped_front_leg`) — ready-made classic bone deformation rig for a quadruped front leg. | 9 optional |
| `deform_bone_rig_quadruped_head_and_neck` | KineFX/Classic Deform Bone Rig — Quadruped Head and Neck (OBJ `deform_bone_rig_quadruped_head_and_neck`) — ready-made classic bone deformation rig for a quadruped head + neck chain. | 9 optional |
| `deform_bone_rig_quadruped_ik_spine` | KineFX/Classic Deform Bone Rig — Quadruped IK Spine (OBJ `deform_bone_rig_quadruped_ik_spine`) — ready-made classic bone deformation rig for a quadruped IK spine chain. | 9 optional |
| `deform_bone_rig_quadruped_tail` | KineFX Deform Bone Rig Quadruped Tail — an /obj bone-deform rig HDA for a quadruped tail chain (A_source: 0 inputs, cooks a default guide/hook rig). | 11 optional |
| `deform_bone_rig_quadruped_toes_4f` | KineFX Deform Bone Rig Quadruped Toes (4 Fingers) — an /obj bone-deform rig HDA for a 4-toe quadruped foot (A_source: 0 inputs). | 11 optional |
| `deform_bone_rig_quadruped_toes_5f` | KineFX Deform Bone Rig Quadruped Toes (5 Fingers) — an /obj bone-deform rig HDA for a 5-toe quadruped foot (A_source: 0 inputs). | 11 optional |
| `deform_rig_biped_arm` | KineFX Deform Rig Biped Arm — an /obj muscle-deform rig HDA for a biped arm (A_source: 0 inputs, cooks a default muscle/guide rig). | 14 optional |
| `deform_rig_biped_hand_4f_2s` | KineFX Deform Rig Biped Hand (4 Fingers, 2 Segments) — an /obj muscle-deform rig HDA for a biped hand (A_source: 0 inputs). | 14 optional |
| `deform_rig_biped_hand_4f_3s` | KineFX Deform Rig Biped Hand (4 Fingers, 3 Segments) — an /obj muscle-deform rig HDA for a biped hand (A_source: 0 inputs). | 14 optional |
| `deform_rig_biped_hand_5f_3s` | KineFX Deform Rig Biped Hand (5 Fingers, 3 Segments) — an /obj muscle-deform rig HDA for a biped hand (A_source: 0 inputs). | 14 optional |
| `deform_rig_biped_head_and_neck` | KineFX Deform Rig Biped Head and Neck — an /obj muscle-deform rig HDA for a biped head+neck (A_source: 0 inputs). | 21 optional |
| `deform_rig_biped_leg` | KineFX Deform Rig Biped Leg — an /obj muscle-deform rig HDA for a biped leg (A_source: 0 inputs). | 14 optional |
| `deform_rig_biped_spine_3pc` | KineFX Deform Rig Biped Spine (3 Pieces) — an /obj muscle-deform rig HDA for a 3-piece biped spine (A_source: 0 inputs). | 14 optional |
| `deform_rig_biped_spine_5pc` | KineFX Deform Rig Biped Spine (5 Pieces) — an /obj muscle-deform rig HDA for a 5-piece biped spine (A_source: 0 inputs). | 14 optional |
| `deform_rig_quadruped_back_leg` | KineFX Deform Rig Quadruped Back Leg — an /obj muscle-deform rig HDA for a quadruped back leg (A_source: 0 inputs). | 14 optional |
| `deform_rig_quadruped_front_leg` | KineFX Deform Rig Quadruped Front Leg — an /obj muscle-deform rig HDA for a quadruped front leg (A_source: 0 inputs). | 14 optional |
| `deform_rig_quadruped_head_and_neck` | KineFX Deform Rig Quadruped Head and Neck — an /obj muscle-deform rig HDA for a quadruped head+neck (A_source: 0 inputs). | 21 optional |
| `deform_rig_quadruped_ik_spine` | KineFX Deform Rig Quadruped IK Spine — an /obj muscle-deform rig HDA for a quadruped IK spine (A_source: 0 inputs). | 14 optional |
| `deform_rig_quadruped_tail` | KineFX Deform Rig Quadruped Tail — an /obj muscle-deform rig HDA for a quadruped tail (A_source: 0 inputs). | 14 optional |
| `deform_rig_quadruped_toes_4f` | KineFX Deform Rig Quadruped Toes (4 Fingers) — an /obj muscle-deform rig HDA for a 4-toe quadruped foot (A_source: 0 inputs). | 14 optional |
| `deform_rig_quadruped_toes_5f` | KineFX Deform Rig Quadruped Toes (5 Fingers) — an /obj muscle-deform rig HDA for a 5-toe quadruped foot (A_source: 0 inputs). | 14 optional |
| `toon_character_deform_rig` | KineFX Toon Character Deform Rig (toon_character_deform_rig) — a 0-input OBJ PRESET that instantiates the legacy ready-made full toon character: a body-part bone rig (spine / arms / legs / head+neck / hands) driving a captured `skin` sub-object. | 5 optional |
| `bone_link` | KineFX Bone Link (bonelink) — a 0-input SOURCE that emits the classic bone-link geometry (the tapered link shape drawn between a bone's ends, with optional packed-bone / fin / proxy / capture visualizations) inside a fresh /obj geo. | 13 optional |
| `bone_solidify` | KineFX Bone Solidify (bonesolidify) — tetrahedralizes an input skin `mesh` (input 0) into a solid tet mesh bound to the rig, for FEM / soft-body-style bone deformation. | `mesh` (+19 optional) |
| `capture_attribute_unpack` | KineFX Capture Attribute Unpack (captureattribunpack) — expands a packed capture attribute (default `boneCapture`) on `geometry` (input 0) into separate `_index` + `_data` component attributes so the raw weights can be edited by generic attribute tools. | `geometry` (+8 optional) |
| `capture_attribute_pack` | KineFX Capture Attribute Pack (captureattribpack) — collapses the separate capture `_index` + `_data` component attributes on `geometry` (input 0) back into a single packed capture attribute (default `boneCapture`). | `geometry` (+8 optional) |
| `capture_layer_paint` | KineFX Capture Layer Paint (capturelayerpaint::2.0) — edits/normalizes classic capture weights on `geometry` (input 0) for the active capture regions; the brush is a viewport tool, so this data-only endpoint exposes only the region-selection / normalization / capture-type controls and passes the re-normalized rig through. | `geometry` (+11 optional) |
| `post_anim_deform` | Labs Post Animation Deform (labs::post_anim_deform) — applies the deformation delta between a rest mesh (input 1) and its deformed version (input 2) onto a matching `deforming` mesh (input 0), optionally transferring an orientation/transform attribute. | `deforming`, `rest`, `deformed` (+6 optional) |
| `neuron_mocap` | Labs Neuron Mocap (labs::neuron_mocap) — a 0-input SOURCE (fresh /obj geo) that configures a Perception Neuron live-mocap stream (character name / IP / port / data format / actor index) and emits the received skeleton. | `name` (+5 optional) |
| `rokoko_mocap` | Labs Rokoko Mocap (labs::rokoko_mocap) — a 0-input SOURCE (fresh /obj geo) that configures a Rokoko Smartsuit live-mocap stream (IP / port / actor / suit name) and an optional recording file, and emits the received skeleton. | `name` (+6 optional) |
| `dembones_skinning_external` | Labs DemBones Skinning Converter (labs::dembones_skinningconverter) — WIRE-ONLY. | `geometry` (+20 optional) |
| `dembones_skinning_bake` | DemBones Skinning Converter, native SOP writer (dembones_skinningconverter::1.0) — WIRE-ONLY. | `geometry` (+21 optional) |
| `skin_properties` | KineFX Skin Properties (skinproperties) — authors per-point muscle/skin SOLVER property attributes on the input skin (input 0): surface & solid stiffness / damping / bend-stiffness / mass-density / sliding-rate, optionally masked and blended, with a material `preset`. | `geometry` (+15 optional) |
| `skin_solidify` | KineFX Skin Solidify (skinsolidify::2.0) — builds a layered SOLID tet shell around an input skin surface (input 0) for FEM / cloth-style skin simulation: `skin_thickness` + `num_layers` set the shell depth, the element-sizing levers (`min_size`/`max_size`/`rel_density`/`gradation`) drive tet density, and a smoothing relaxation (`iterations`/`step_size`) cleans interior weights. | `geometry` (+15 optional) |
| `skin_deform` | KineFX Skin Deform (skindeform) — muscle-aware skin finishing over an input skin (input 0): a muscle-blur pass that smooths skin weights toward the underlying muscle motion, plus an optional skin-sliding relaxation that lets the skin slide over the muscles, resolved against a reference frame. | `geometry` (+12 optional) |
| `animation_rig_biped_arm` | KineFX Animation Rig Biped Arm — an /obj animation (control) rig HDA for a biped arm (A_source: 0 inputs, cooks a default FK/IK control rig). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_biped_hand_4f_2s` | KineFX Animation Rig Biped Hand (4 Fingers, 2 Segments) — an /obj animation rig HDA for a biped hand (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_biped_hand_4f_3s` | KineFX Animation Rig Biped Hand (4 Fingers, 3 Segments) — an /obj animation rig HDA for a biped hand (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_biped_hand_5f_3s` | KineFX Animation Rig Biped Hand (5 Fingers, 3 Segments) — an /obj animation rig HDA for a biped hand (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_biped_head_and_neck` | KineFX Animation Rig Biped Head and Neck — an /obj animation rig HDA for a biped head+neck (A_source: 0 inputs, cooks head/neck/jaw/eye look-at controls). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_biped_leg` | KineFX Animation Rig Biped Leg — an /obj animation rig HDA for a biped leg (A_source: 0 inputs, cooks a default FK/IK control rig). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_biped_spine_3pc` | KineFX Animation Rig Biped Spine (3 Pieces) — an /obj animation rig HDA for a 3-piece biped spine (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_biped_spine_5pc` | KineFX Animation Rig Biped Spine (5 Pieces) — an /obj animation rig HDA for a 5-piece biped spine (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_character_placer` | KineFX Animation Rig Character Placer — the /obj root placement rig HDA that positions a whole character (A_source: 0 inputs). control_scale/control_lod/control_color size & style the placement controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_quadruped_back_leg` | KineFX Animation Rig Quadruped Back Leg — an /obj animation rig HDA for a quadruped back leg (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_quadruped_front_leg` | KineFX Animation Rig Quadruped Front Leg — an /obj animation rig HDA for a quadruped front leg (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_quadruped_head_and_neck` | KineFX Animation Rig Quadruped Head and Neck — an /obj animation rig HDA for a quadruped head+neck (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_quadruped_ik_spine` | KineFX Animation Rig Quadruped IK Spine — an /obj animation rig HDA for a quadruped IK spine (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_quadruped_tail` | KineFX Animation Rig Quadruped Tail — an /obj animation rig HDA for a quadruped tail (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_quadruped_toes_4f` | KineFX Animation Rig Quadruped Toes (4 Fingers) — an /obj animation rig HDA for a 4-toe quadruped foot (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `animation_rig_quadruped_toes_5f` | KineFX Animation Rig Quadruped Toes (5 Fingers) — an /obj animation rig HDA for a 5-toe quadruped foot (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `auto_rig_biped_arm` | KineFX Auto Rig Biped Arm — an /obj auto-rig builder HDA that assembles a full biped-arm control rig from defaults (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `auto_rig_biped_hand_4f_2s` | KineFX Auto Rig Biped Hand (4 Fingers, 2 Segments) — an /obj auto-rig builder HDA that assembles a full biped-hand control rig from defaults (A_source: 0 inputs). control_scale/control_lod/control_color size & style the controls; hook_object references a parent object in-scene. | `name` (+14 optional) |
| `auto_rig_biped_hand_4f_3s` | KineFX Auto Rig Biped Hand (4 Fingers, 3 Segments) — an /obj auto-rig HDA that builds a default 4-finger biped hand control rig (A_source: 0 inputs). | 17 optional |
| `auto_rig_biped_hand_5f_3s` | KineFX Auto Rig Biped Hand (5 Fingers, 3 Segments) — an /obj auto-rig HDA that builds a default 5-finger biped hand control rig (A_source: 0 inputs). | 17 optional |
| `auto_rig_biped_head_and_neck` | KineFX Auto Rig Biped Head and Neck — an /obj auto-rig HDA that builds a default biped head+neck control rig (A_source: 0 inputs). | 16 optional |
| `auto_rig_biped_leg` | KineFX Auto Rig Biped Leg — an /obj auto-rig HDA that builds a default biped leg control rig (A_source: 0 inputs). | 19 optional |
| `auto_rig_biped_spine_3pc` | KineFX Auto Rig Biped Spine (3 Pieces) — an /obj auto-rig HDA that builds a default 3-piece biped spine control rig (A_source: 0 inputs). | 15 optional |
| `auto_rig_biped_spine_5pc` | KineFX Auto Rig Biped Spine (5 Pieces) — an /obj auto-rig HDA that builds a default 5-piece biped spine control rig (A_source: 0 inputs). | 15 optional |
| `auto_rig_quadruped_back_leg` | KineFX Auto Rig Quadruped Back Leg — an /obj auto-rig HDA that builds a default quadruped back-leg control rig (A_source: 0 inputs). | 19 optional |
| `auto_rig_quadruped_front_leg` | KineFX Auto Rig Quadruped Front Leg — an /obj auto-rig HDA that builds a default quadruped front-leg control rig (A_source: 0 inputs). | 19 optional |
| `auto_rig_quadruped_head_and_neck` | KineFX Auto Rig Quadruped Head and Neck — an /obj auto-rig HDA that builds a default quadruped head+neck control rig (A_source: 0 inputs). | 18 optional |
| `auto_rig_quadruped_ik_spine` | KineFX Auto Rig Quadruped IK Spine — an /obj auto-rig HDA that builds a default quadruped IK-spine control rig (A_source: 0 inputs). | 16 optional |
| `auto_rig_quadruped_tail` | KineFX Auto Rig Quadruped Tail — an /obj auto-rig HDA that builds a default quadruped tail control rig (A_source: 0 inputs). | 15 optional |
| `auto_rig_quadruped_toes_4f` | KineFX Auto Rig Quadruped Toes (4 Fingers) — an /obj auto-rig HDA that builds a default 4-toe quadruped foot control rig (A_source: 0 inputs). | 18 optional |
| `auto_rig_quadruped_toes_5f` | KineFX Auto Rig Quadruped Toes (5 Fingers) — an /obj auto-rig HDA that builds a default 5-toe quadruped foot control rig (A_source: 0 inputs). | 18 optional |
| `auto_rig_character_placer` | KineFX Auto Rig Character Placer — an /obj auto-rig HDA that lays out the placement guides a rig is built from (A_source: 0 inputs). | 18 optional |
| `biped_auto_rig` | KineFX Biped Auto Rig — an /obj one-call HDA that builds a full default biped control rig (A_source: 0 inputs). | 24 optional |
| `auto_rig_eye` | KineFX Auto Rig Eye — an /obj auto-rig HDA that builds a single eye rig (A_source: 0 inputs). | 14 optional |
| `impostor_camera_rig` | KineFX Labs Impostor Camera Rig — an /obj rig HDA that builds the multi-view camera rig an impostor bake shoots from (A_source: 0 inputs). | 9 optional |
| `mocap_acclaim` | KineFX Mocap Acclaim — an /obj mocap-import HDA for Acclaim ASF/AMC motion capture (A_source: 0 inputs; cooks green empty until a skeleton is set). | 17 optional |
| `mocap_rig_biped_arm` | KineFX Mocap Rig Biped Arm — an /obj mocap-retarget rig HDA that drives a biped-arm animation rig from a mocap skeleton (A_source: 0 inputs). | 18 optional |
| `mocap_rig_biped_head_and_neck` | KineFX Mocap Rig Biped Head and Neck — an /obj mocap-retarget rig HDA that drives a biped head+neck animation rig from a mocap skeleton (A_source: 0 inputs). | 17 optional |
| `mocap_rig_biped_leg` | KineFX Mocap Rig Biped Leg — an /obj mocap-retarget rig HDA that drives a biped-leg animation rig from a mocap skeleton (A_source: 0 inputs). | 23 optional |
| `mocap_rig_biped_spine_3pc` | KineFX Mocap Rig Biped Spine (3 Pieces) — an /obj mocap-retarget rig HDA that drives a 3-piece biped spine animation rig from a mocap skeleton (A_source: 0 inputs). | 19 optional |
| `mocap_rig_biped_spine_5pc` | KineFX Mocap Rig Biped Spine (5 Pieces) — an /obj mocap-retarget rig HDA that drives a 5-piece biped spine animation rig from a mocap skeleton (A_source: 0 inputs). | 23 optional |
| `mocap_biped_1` | KineFX MoCap Biped 1 — a pre-built MoCap Biped test character with baked locomotion clips (A_source: built bare, 0 inputs wired). | 10 optional |
| `mocap_biped_2` | KineFX MoCap Biped 2 — a pre-built MoCap Biped test character with a large baked clip library (A_source: built bare, 0 inputs wired). | 10 optional |
| `mocap_biped_3` | KineFX MoCap Biped 3 — the advanced pre-built MoCap Biped test character with a categorized clip library and motion-matching (A_source: built bare, 0 inputs wired). | 14 optional |
| `quadruped_auto_rig_4f` | KineFX Quadruped Auto Rig (4 Toes) — an /obj one-call HDA that builds a full default 4-toe quadruped control rig (A_source: 0 inputs). | 28 optional |
| `quadruped_auto_rig_5f` | KineFX Quadruped Auto Rig (5 Toes) — an /obj one-call HDA that builds a full default 5-toe quadruped control rig (A_source: 0 inputs). | 28 optional |
| `toon_character` | KineFX Toon Character — an /obj HDA that builds a full pre-rigged toon character (auto-rig + face + mocap) from defaults (A_source: 0 inputs). | 18 optional |
| `constraint_begin` | KineFX Constraint Get World Space Begin (constraintbegin) — the START of a CHOP constraint network: emits the world transform of `object` as t/r/s tracks (9 tracks) that downstream constraint CHOPs combine. | 6 optional |
| `constraint_object` | KineFX Constraint Object (constraintobject) — emits the world transform of `target` as t/r/s tracks (9), optionally expressed relative to `reference`. | 6 optional |
| `constraint_object_pretransform` | KineFX Constraint Object Pretransform (constraintobjectpretransform) — emits the pre-transform (the object's rest/pivot offset) of `target` as t/r/s tracks (9). | 5 optional |
| `constraint_object_offset` | KineFX Constraint Object Offset (constraintobjectoffset) — emits the offset transform of `target` relative to `reference` as t/r/s tracks (9), masked by `channel_mask`. | 9 optional |
| `constraint_get_world_space` | KineFX Constraint Get World Space (constraintgetworldspace) — emits the WORLD-space transform of `object` as t/r/s tracks (9). | 5 optional |
| `constraint_get_parent_space` | KineFX Constraint Get Parent Space (constraintgetparentspace) — emits the PARENT-space transform of `object` as t/r/s tracks (9); `parent_bone` selects the parent-bone convention. | 6 optional |
| `constraint_get_local_space` | KineFX Constraint Get Local Space (constraintgetlocalspace) — emits the LOCAL-space transform of `object` as t/r/s tracks (9); `mode` picks the local-space convention. | 6 optional |
| `constraint_look_at` | KineFX Constraint Look At (constraintlookat) — emits a rotation that aims `look_at_axis` at a look-at position while keeping `look_up_axis_*` toward an up target (9 tracks). | 15 optional |
| `constraint_path` | KineFX Constraint Path (constraintpath) — emits a transform that rides along the curve at `sop_path` at parametric `position`, oriented by the look-at/look-up settings (9 tracks). | 21 optional |
| `constraint_points` | KineFX Constraint Points (constraintpoints) — emits a transform attached to point(s) of the SOP at `sop_path` (a `group`, or the nearest within `search_distance`/`search_max_points`), oriented by the look-at/look-up settings (9 tracks). | 22 optional |
| `constraint_export` | KineFX Constraint Export (constraintexport) — terminates a constraint network by exporting the combined transform to the constraint object at `constraints_path`; `enable_constraints` toggles it live. | 4 optional |
| `constraint_blend` | KineFX Constraint Blend (constraintblend) — blends two or more constraint transform streams. | `input` (+5 optional) |
| `constraint_sequence` | KineFX Constraint Sequence (constraintsequence) — sequentially blends a chain of constraint streams by `blend`. | `input` (+5 optional) |
| `constraint_offset` | KineFX Constraint Offset (constraintoffset) — applies the offset transform on `input1` (input 1) to the base transform on `input` (input 0) by `blend`. | `input`, `input1` (+6 optional) |
| `constraint_parent` | KineFX Constraint Parent (constraintparent) — composes a child transform under a parent transform (the CHOP parenting primitive). | `input` (+3 optional) |
| `constraint_parent_extended` | KineFX Constraint Parent Extended (constraintparentx) — parenting with a `write_mask` (int bitmask of channels written, default 511). | `input` (+4 optional) |
| `constraint_simple_blend` | KineFX Constraint Simple Blend (constraintsimpleblend) — a lightweight blend of two constraint streams by `blend`. | `input` (+5 optional) |
| `constraint_offset_blend` | KineFX Constraint Offset Blend (constraintoffsetblend) — blends an offset across up to four constraint streams by `blend`. | `input` (+7 optional) |
| `constraint_surface` | KineFX Constraint Surface (constraintsurface) — a CHOP that emits a transform stuck to the SURFACE of the SOP at `sop_path`, located by a UV coordinate (`uv` on `uv_attribute`), a position (`p` on `position_attribute`), or the nearest point within `search_distance`/`search_max_points`, and oriented by the look-at / look-up settings. | 26 optional |
| `constraint_transform` | KineFX Constraint Transform (constrainttransform) — a CHOP that emits an explicit transform built from `translate`/`rotate`/`scale` (with `transform_order`/`rotation_order`), a pivot (`pivot` / `pivot_rotate`), and `mode`/`pivot_mode`; `invert` inverts the result. | 15 optional |
| `constraint_pose` | KineFX Pose (pose) — a Constraints-tab CHOP that emits a stored static pose as t/r/s transform tracks (from `translate`/`rotate`/`scale` with `transform_order`/`rotation_order`). | 8 optional |
| `jiggle` | KineFX Jiggle (jiggle) — a CHOP that adds secondary jiggle motion to the transform stream on `input` (input 0, which MUST carry tx/ty/tz channels). | `input` (+7 optional) |
| `lag` | KineFX Lag (lag) — a CHOP that smooths / delays the channel stream on `input` (input 0). | `input` (+8 optional) |
| `channel_spring` | KineFX Spring (spring, CHOP) — drives the channel stream on `input` (input 0) with a mass-spring system: `spring_constant`, `mass`, `damping`, `method` (disp / force), initial `position` / `speed`, and `use_channel_condition` to seed the initial state from the input. | `input` (+8 optional) |
| `channel_pose_difference` | KineFX Pose Difference (posedifference, CHOP) — computes the difference between the pose stream on `input` (input 0) and a reference pose. | `input` (+3 optional) |
| `chop_wave` | CHOP Wave (wave) — generates a periodic waveform channel (sine/triangle/ramp/square/pulse) over a frame range. | 16 optional |
| `chop_waveform` | CHOP Waveform (waveform) — generates a constant/sine/square waveform channel (data-driven waveform source). | 13 optional |
| `chop_noise` | CHOP Noise (noise) — generates an animated noise channel (sparse/perlin/harmonic/brownian/alligator). | 14 optional |
| `chop_constant` | CHOP Constant (constant) — generates channels holding constant values (up to four named channels). | 10 optional |
| `chop_spline` | CHOP Spline (spline) — generates a spline-interpolated channel (bezier/cubic) over a range. | 11 optional |
| `chop_pulse` | CHOP Pulse (pulse) — generates a sequence of value pulses over a range. | 13 optional |
| `chop_channel` | CHOP Channel (channel) — generates channels sampled from parameter channels / keyframes over a range. | 11 optional |
| `chop_oscillator` | CHOP Oscillator (oscillator) — audio-style oscillator driven by an input channel (REQUIRES an input CHOP). | `input` (+15 optional) |
| `chop_math` | CHOP Math (math) — per-channel and cross-CHOP arithmetic, gain and remap. | `input` (+19 optional) |
| `chop_function` | CHOP Function (function) — applies a math function (sqrt/trig/log/pow/...) to the input channels. | `input` (+12 optional) |
| `chop_filter` | CHOP Filter (filter) — temporal filter (gaussian/box/edge/sharpen/despike) on input channels. | `input` (+9 optional) |
| `chop_limit` | CHOP Limit (limit) — clamps / loops / quantizes input channel values. | `input` (+15 optional) |
| `chop_lag` | CHOP Lag (lag) — smooths input channels with lag/overshoot (spring-like follow). | `input` (+11 optional) |
| `chop_lookup` | CHOP Lookup (lookup) — uses input 0 as an index to look up values in input 1. | `input` (+9 optional) |
| `chop_cycle` | CHOP Cycle (cycle) — repeats/mirrors the input channels before and after with optional blends. | `input` (+13 optional) |
| `chop_blend` | CHOP Blend (blend) — weight-blends channels across wired inputs. | `input` (+10 optional) |
| `chop_merge` | CHOP Merge (merge) — merges the channels of all wired inputs into one stream. | `input` (+9 optional) |
| `chop_warp` | CHOP Warp (warp) — time-warps input 0 by the warp channel on input 1. | `input` (+7 optional) |
| `chop_resample` | CHOP Resample (resample) — resamples the input channels to a new rate / range. | `input` (+14 optional) |
| `chop_shift` | CHOP Shift (shift) — shifts / scrolls the input channels in time. | `input` (+10 optional) |
| `chop_hold` | CHOP Hold (hold) — holds (sample-and-holds) the input channels. | `input` (+5 optional) |
| `chop_spectrum` | CHOP Spectrum (spectrum) — converts input channels to/from the frequency domain. | `input` (+11 optional) |
| `chop_multiply` | CHOP Multiply (multiply) — multiplies the channels of all wired inputs together. | `input` (+7 optional) |
| `chop_invert` | CHOP Invert (invert) — inverts (reciprocal) the input channel values. | `input` (+4 optional) |
| `chop_extend` | CHOP Extend (extend) — sets how the input channels extend before/after their range. | `input` (+7 optional) |
| `chop_stretch` | CHOP Stretch (stretch) — stretches the input channels in time and value. | `input` (+12 optional) |
| `chop_trim` | CHOP Trim (trim) — trims the input channels to a sub-range. | `input` (+9 optional) |
| `chop_area` | CHOP Area (area) — integrates the input channels (area / running integral). | `input` (+13 optional) |
| `chop_envelope` | CHOP Envelope (envelope) — extracts the amplitude envelope of the input channels. | `input` (+11 optional) |
| `chop_interp` | CHOP Interpolate (interp) — interpolates between the wired inputs over time. | `input` (+11 optional) |
| `chop_delay` | CHOP Delay (delay) — adds delayed, gained echoes of the input channels. | `input` (+14 optional) |
| `chop_slope` | CHOP Slope (slope) — computes the slope / acceleration (derivative) of the input channels. | `input` (+6 optional) |
| `chop_fan` | CHOP Fan (fan) — fans one channel out to many, or fans many channels in to one. | `input` (+8 optional) |
| `chop_count` | CHOP Count (count) — counts threshold crossings of the input channels. | `input` (+14 optional) |
| `chop_null` | CHOP Null (null) — pass-through null (a stable named tap into the channel stream). | `input` (+4 optional) |
| `chop_vector` | CHOP Vector (vector) — vector operations (magnitude/normalize/dot/cross/project/...) on channel triples. | `input` (+11 optional) |
| `chop_attribute` | CHOP Attribute (attribute) — manages transform attributes (rotation order / slerp) on the channels. | `input` (+6 optional) |
| `chop_copy` | CHOP Copy (copy) — stamps input 0 at each trigger sample of input 1. | `input` (+7 optional) |
| `chop_shuffle` | CHOP Shuffle (shuffle) — reorders / splits / sequences the input channels. | `input` (+6 optional) |
| `chop_reorder` | CHOP Reorder (reorder) — reorders channels by numeric / character pattern. | `input` (+10 optional) |
| `chop_rename` | CHOP Rename (rename) — renames channels by pattern. | `input` (+7 optional) |
| `chop_delete` | CHOP Delete (delete) — deletes channels by name or number. | `input` (+12 optional) |
| `chop_switch` | CHOP Switch (switch) — passes through one of the wired inputs, selected by index. | `input` (+9 optional) |
| `chop_layer` | CHOP Layer (layer) — layers the wired inputs with per-layer weights (active layer selects the base). | `input` (+8 optional) |
| `chop_composite` | CHOP Composite (comp) — composites (additive rise/peak/release) the wired inputs. | `input` (+18 optional) |
| `chop_trigger` | CHOP Trigger (trigger) — generates an ADSR-style envelope triggered by the input channels. | `input` (+16 optional) |
| `chop_footplant` | CHOP Foot Plant (footplant) — detect + lock foot contacts in a walk animation to kill sliding. | `input` (+11 optional) |
| `chop_iksolver` | CHOP IK Solver (iksolver) — solve a bone chain to reach an end affector. | `input` (+11 optional) |
| `chop_inversekin` | CHOP Inverse Kinematics (inversekin) — the classic bone-chain IK solver driven by OBJ bone paths. | 11 optional |
| `chop_transform_chain` | CHOP Transform Chain (transformchain) — recompose a chain of transforms into output channels. | `input` (+7 optional) |
| `chop_export_transforms` | CHOP Export Transforms (exporttransforms) — map transform channels to OBJ node parameters. | `input` (+6 optional) |
| `chop_extract_bone_transforms` | CHOP Extract Bone Transforms (extractbonetransforms) — read a KineFX skeleton's bone transforms into channels. | 10 optional |
| `chop_extract_pose_drivers` | CHOP Extract Pose Drivers (extractposedrivers) — extract driver channels (joint xforms / parms) that feed a pose-space deformer. | 9 optional |
| `chop_blendpose` | CHOP Blend Pose (blendpose) — pose-space interpolation (RBF / hyperplane) that blends example poses by driver values. | `input` (+13 optional) |
| `chop_stashpose` | CHOP Stash Pose (stashpose) — stash the current pose as a static reference pose for pose-space workflows. | `input` (+5 optional) |

### Crowd

| Tool | What it does | Key params |
|---|---|---|
| `agent_source` | Crowd Agent (agent SOP) — creates/imports agent primitives. input=scene (an /obj bone subnet), disk (agent cache dir), fbx or usd. | 16 optional |
| `agent_look_at` | Crowd Agent Look At (agentlookat::3.0) — orients agent head/eye joints toward a target. input0 = agents, input1 = target points (target_type=points). | `agents` (+19 optional) |
| `agent_terrain_adaptation` | Crowd Agent Terrain Adaptation (agentterrainadaptation::3.0) — DOP crowd microsolver: foot-locking + hip-adjust of agents to terrain. | 17 optional |
| `agent_terrain_projection` | Crowd Agent Terrain Projection (agentterrainprojection) — DOP crowd microsolver projecting agent particles/feet onto a terrain surface. | 14 optional |
| `agent_look_at_apply` | Crowd Agent Look At Apply (agentlookatapply::3.0) — DOP crowd microsolver applying head/eye look-at targeting to agents each sim step. | 14 optional |
| `agent_clip_layer` | Crowd Agent Clip Layer (agentcliplayer) — DOP crowd microsolver that layers/blends animation clips onto agents. | 15 optional |
| `agent_arcing_clip_layer` | Crowd Agent Arcing Clip Layer (agentarcingcliplayer) — DOP crowd microsolver that layers an arcing/turning clip onto agents. | 6 optional |
| `crowd_fuzzy_logic` | Crowd Fuzzy Logic (crowdfuzzylogic) — DOP node combining trigger inputs via fuzzy logic into a trigger attribute. | 7 optional |
| `crowd_object` | Crowd Object (crowdobject) — the DOP object holding the agent crowd in a crowd sim. | 16 optional |
| `crowd_state` | Crowd State (crowdstate::3.0) — a named behaviour state (clip assignment, gait, ragdoll mode) in a crowd state machine. | 13 optional |
| `agent_clip` | KineFX Agent Clip (agentclip::2.0) — bakes a motion source onto agent primitives as a named clip. input0 = agents, input1 = MotionClip (source=sop/chop). | `agents` (+16 optional) |
| `crowd_trigger` | KineFX Crowd Trigger (crowdtrigger::2.0) — evaluates a per-agent condition (proximity/attribute/speed/distance/...) and writes a trigger attribute. | 19 optional |
| `crowd_trigger_logic` | KineFX Crowd Trigger Logic (crowdtriggerlogic::2.0) — combines up to two trigger streams with a boolean operation and writes a trigger attribute. | 7 optional |
| `crowd_transition` | KineFX Crowd Transition (crowdtransition::3.0) — defines a transition between two crowd states, fired by a trigger. | `input` (+17 optional) |
| `crowd_sop_import` | KineFX Crowd SOP Import (sopcrowdimport) — imports a SOP crowd (agent primitives) onto the USD stage as UsdSkel characters. sop_path = the SOP carrying the agents. | `sop_path` (+7 optional) |
| `crowd_render_procedural` | KineFX Crowd Render Procedural (houdinicrowdprocedural) — sets up a render-time (Karma) crowd delayed-load procedural so agents expand at render, not baked. input (opt) = a LOP stage with the crowd. | 13 optional |
| `bake_skinning` | KineFX Bake Skinning (bakeskinning) — bakes UsdSkel skinning on an input stage down to deformed point positions (crowd render-prep after crowd_sop_import). input (REQUIRED) = the LOP stage with skinned characters. | `input` (+1 optional) |
| `agent_channels` | KineFX Agent Channels (agent CHOP) — evaluates an agent primitive's clip or pose transforms into CHOP tracks (drive rigs/lights/objects from crowd animation). sop_path = the SOP carrying the agent. | `sop_path` (+13 optional) |
| `agent_camera` | KineFX Agent Cam (agentcam) — an /obj camera driven by a crowd agent's own camera definition (render through an agent's eyes). agent_source = the SOP carrying the agent. | 9 optional |
| `agent_clip_properties` | Crowd Agent Clip Properties (agentclipproperties) — authors per-clip metadata (frame range, sample units, previewed clip) on an agent's clip catalog. input0 = agents. | `agents` (+5 optional) |
| `agent_clip_transition_graph` | Crowd Agent Clip Transition Graph (agentcliptransitiongraph) — computes clip-to-clip transition blends for an agent. input0 = agents, input1 = existing transition graph, input2 = clip properties. | `agents` (+8 optional) |
| `agent_collision_layer` | Crowd Agent Collision Layer (agentcollisionlayer) — builds/marks a collision layer on agents for ragdoll/bullet collision shapes. input0 = agents. | `agents` (+9 optional) |
| `agent_configure_joints` | Crowd Agent Configure Joints (agentconfigurejoints) — configures per-joint ragdoll limits and guide display on agents. input0 = agents. | `agents` (+4 optional) |
| `agent_constraint_network` | Crowd Agent Constraint Network (agentconstraintnetwork) — builds the ragdoll constraint network (softness / ERP / CFM / bias tuning) for agents. input0 = agents. | `agents` (+12 optional) |
| `agent_definition_cache` | Crowd Agent Definition Cache (agentdefinitioncache) — loads a cached agent definition (rig/layers/shapes/clips/metadata). | 19 optional |
| `agent_edit` | Crowd Agent Edit (agentedit) — overrides an agent's current/collision layer, current clip and clip time. input0 = agents. | `agents` (+7 optional) |
| `agent_layer` | Crowd Agent Layer (agentlayer::2.0) — adds/assigns shape layers to agents and sets the current and collision layers. input0 = agents, input1 = shape geometry, input2 = capture pose. | `agents` (+17 optional) |
| `agent_metadata` | Crowd Agent Metadata (agentmetadata) — reads/merges/sets typed metadata dictionaries on agents. input0 = agents. | `agents` (+10 optional) |
| `agent_prep` | Crowd Agent Prep (agentprep::3.0) — prepares agents for crowd sim (rest clip, limb setup, clip loading). input0 = agents. cachedir + clippaths confined to the working dir; the create-chopnet/reload/save buttons are never pressed. | `agents` (+11 optional) |
| `agent_proxy` | Crowd Agent Proxy (agentproxy) — sets viewport proxy display (LOD / id / color) for agent points, for fast crowd previews. input0 = points carrying agent primitives. | `agents` (+6 optional) |
| `agent_relationship` | Crowd Agent Relationship (agentrelationship) — parents child agents to a parent agent (optionally to a specific joint) with a position/rotation/all constraint. input0 = parent agents, input1 = child agents. | `agents` (+10 optional) |
| `agent_transform_group` | Crowd Agent Transform Group (agenttransformgroup) — defines named transform (joint) groups on agents for weighted deformation/blending. input0 = agents. | `agents` (+10 optional) |
| `agent_unpack` | Crowd Agent Unpack (agentunpack) — unpacks agent primitives into their underlying geometry (deformed \| rest \| joints \| skeleton \| motionclips). input0 = agents. | `agents` (+15 optional) |
| `agent_vellum_unpack` | Crowd Agent Vellum Unpack (agentvellumunpack) — unpacks agents into sim (Vellum) + rest geometry for cloth/soft-body crowd setups. input0 = agents. | `agents` (+16 optional) |
| `crowd_assign_layers` | Crowd Assign Layers (crowdassignlayers) — assigns/randomizes current & collision layers on a crowd of agents by group / layer-pattern / percentage. input0 = agents. | `agents` (+13 optional) |
| `crowd_motion_path` | Crowd Motion Path (crowdmotionpath) — generates editable motion-path curves for a crowd by evaluating each agent's assigned clips (or a cached sim) over a frame range. input0 = a crowd (points carrying agent prims). | `agents` (+15 optional) |
| `crowd_motion_path_apply_relationship` | Crowd Motion Path Apply Relationship (crowdmotionpathapplyrel) — applies agent parent/child relationships onto motion paths. input0 = motion paths, input1 = agents. | `motion_paths` (+3 optional) |
| `crowd_motion_path_arcing_layer` | Crowd Motion Path Arcing Layer (crowdmotionpatharcinglayer) — layers turn (arcing) clips onto a motion path based on turn rate. input0 = motion paths, input1 = agents. | `motion_paths` (+11 optional) |
| `crowd_motion_path_avoid` | Crowd Motion Path Avoid (crowdmotionpathavoid) — steers motion paths to avoid collisions, neighbors and obstacles. input0 = motion paths, input1 = agents (opt), input2 = obstacles (opt). | `motion_paths` (+18 optional) |
| `crowd_motion_path_edit` | Crowd Motion Path Edit (crowdmotionpathedit) — pin-weight / scale-adjustment editing of motion paths (non-interactive data controls). input0 = motion paths, input1 = agents. | `motion_paths` (+6 optional) |
| `crowd_motion_path_edit_core` | Crowd Motion Path Edit Core (crowdmotionpatheditcore) — the data core of the motion-path edit: applies pin-weight / scale-adjustment attributes to motion paths. input0 = motion paths. | `motion_paths` (+9 optional) |
| `crowd_motion_path_evaluate` | Crowd Motion Path Evaluate (crowdmotionpathevaluate) — samples a crowd's motion paths at a given frame, producing the posed crowd points. input0 = motion paths, input1 = agents. | `motion_paths` (+3 optional) |
| `crowd_motion_path_evaluate_core` | Crowd Motion Path Evaluate Core (crowdmotionpathevaluatecore) — the data core of the motion-path evaluate: poses agents from motion paths at a given time. | `agents` (+4 optional) |
| `crowd_motion_path_follow` | Crowd Motion Path Follow (crowdmotionpathfollow) — deforms motion paths to follow guide curves. input0 = motion paths, input1 = agents (opt), input2 = curves to follow (opt). | `motion_paths` (+14 optional) |
| `crowd_motion_path_layer` | Crowd Motion Path Layer (crowdmotionpathlayer) — layers an animation clip onto a motion path when triggered (via trigger groups). input0 = motion paths, input1 = agents. | `motion_paths` (+19 optional) |
| `crowd_motion_path_retime` | Crowd Motion Path Retime (crowdmotionpathretime) — retimes / clips a motion path's frame range and playback speed. input0 = motion paths, input1 = agents (opt). | `motion_paths` (+8 optional) |
| `crowd_motion_path_transition` | Crowd Motion Path Transition (crowdmotionpathtransition) — transitions a motion path from its current clip to a new clip when triggered. input0 = motion paths, input1 = agents. | `motion_paths` (+19 optional) |
| `crowd_source` | Crowd Source (crowdsource::3.0) — generates the crowd point stream (formation grid or scatter) that seeds a crowd sim; each point spawns an agent with an initial state / clip / heading. | 27 optional |
| `crowd_motion_path_trigger` | Crowd Motion Path Trigger (crowdmotionpathtrigger) — evaluates a trigger condition (time / bounds / object-distance / raycast / neighbor-distance / clip) along crowd motion paths and writes a named trigger used by transitions. | `motion_paths` (+29 optional) |
| `agent_animation_unpack` | Agent Animation Unpack (kinefx::agentanimationunpack) — unpacks an agent's animation into a KineFX skeleton `output`: pose / agent-clip pose / rest pose / motion clip / packed motion clips. | `agents` (+14 optional) |
| `agent_character_unpack` | Agent Character Unpack (kinefx::agentcharacterunpack) — unpacks an agent into its component geometry: output 0 = skin shapes, output 1 = skeleton, output 2 = capture pose. | `agents` (+15 optional) |
| `agent_from_rig` | Agent From Rig (kinefx::agentfromrig) — converts a KineFX rig/skeleton into a single Agent primitive (rest pose, no clips). | `rig` (+10 optional) |
| `agent_pose_from_rig` | Agent Pose From Rig (kinefx::agentposefromrig) — drives an agent's pose from a KineFX rig/skeleton pose (both inputs REQUIRED). | `agents`, `rig` (+7 optional) |
| `agent_transforms` | Crowd Agent Transforms (agenttransforms) — data-provider VOP reading an agent primitive's transform matrices. | 7 optional |
| `agent_transform_names` | Crowd Agent Transform Names (agenttransformnames) — data-provider VOP reading the ordered transform (joint) names of an agent's rig. | 6 optional |
| `agent_transform_count` | Crowd Agent Transform Count (agenttransformcount) — data-provider VOP outputting the number of transforms (joints) in an agent's rig. | 6 optional |
| `agent_rig_find` | Crowd Agent Rig Find (agentrigfind) — data-provider VOP returning the transform index of a named joint in an agent's rig. | 7 optional |
| `agent_rig_children` | Crowd Agent Rig Children (agentrigchildren) — data-provider VOP returning the child transform indices of a joint in an agent's rig hierarchy. | 7 optional |
| `agent_rig_parent` | Crowd Agent Rig Parent (agentrigparent) — data-provider VOP returning the parent transform index of a joint in an agent's rig hierarchy. | 7 optional |
| `agent_clip_weights` | Crowd Agent Clip Weights (agentclipweights) — data-provider VOP reading the active per-clip blend weights of an agent. | 6 optional |
| `agent_layers` | Crowd Agent Layers (agentlayers) — data-provider VOP reading the list of layer names on an agent definition. | 6 optional |
| `agent_layer_name` | Crowd Agent Layer Name (agentlayername) — data-provider VOP resolving a layer name for an agent (e.g. current / collision layer). | 7 optional |
| `agent_layer_bindings` | Crowd Agent Layer Bindings (agentlayerbindings) — data-provider VOP reading the shape->transform bindings of a named agent layer. | 8 optional |
| `agent_layer_shapes` | Crowd Agent Layer Shapes (agentlayershapes) — data-provider VOP reading the shape names in a named agent layer, optionally filtered by shape type. | 8 optional |
| `agent_convert_transforms` | Crowd Agent Convert Transforms (agentconverttransforms) — data-provider VOP converting an agent's transforms array between spaces (e.g. local <-> world). | 7 optional |

### Muscle

| Tool | What it does | Key params |
|---|---|---|
| `franken_muscle` | Muscle Franken Muscle (frankenmuscle) — assigns multiple `muscle_id` sub-regions within a single muscle geometry so one solid mesh behaves as several independent muscles. | `muscle` (+10 optional) |
| `franken_muscle_paint` | Muscle Franken Muscle Paint (frankenmusclepaint) — the paint front-end for `muscle_id` masks on a muscle geometry (input 0). | `muscle` (+20 optional) |
| `muscle_id` | Muscle Muscle ID (muscleid) — assigns a per-primitive `muscle_id` name attribute to each connected surface cluster so downstream muscle SOPs address muscles individually. | `surface` (+8 optional) |
| `muscle_solidify` | Muscle Muscle Solidify (musclesolidify) — tetrahedralizes a muscle SURFACE into a solid muscle (carries `muscle_id` + `maxthickness`) ready for properties + simulation. | `surface` (+14 optional) |
| `muscle_properties` | Muscle Muscle Properties (muscleproperties) — authors per-muscle solid material properties (shape/volume/damping/mass/fiber/tendon stiffness) and computes the `materialW` fiber-direction frame on a solid muscle. | `muscle` (+19 optional) |
| `muscle_properties_otis` | Muscle Muscle Properties OTIS (musclepropertiesotis) — the OTIS-solver variant of Muscle Properties (per-muscle solid material properties for the OTIS muscle-and-tissue sim). | `muscle` (+19 optional) |
| `muscle_constraint_properties_fem` | Muscle Muscle Constraint Properties FEM (muscleconstraintpropertiesfem) — authors the per-muscle CONSTRAINT properties (end / muscle-to-muscle / muscle-to-bone stiffness, damping, distance) for the FEM muscle solver. | `muscle` (+13 optional) |
| `muscle_constraint_properties_otis` | Muscle Muscle Constraint Properties OTIS (muscleconstraintpropertiesotis) — the OTIS-solver variant of the muscle CONSTRAINT-property authoring node (end / glue / muscle-to-muscle stiffness + damping + distance). | `muscle` (+11 optional) |
| `muscle_constraint_properties_vellum` | Muscle Muscle Constraint Properties Vellum (muscleconstraintpropertiesvellum) — the Vellum-solver variant of the muscle CONSTRAINT-property authoring node (end / muscle-to-muscle / muscle-to-bone stiffness, damping, distance, compress, slide-rate). | `muscle` (+15 optional) |
| `muscle_auto_tension_lines` | Muscle Auto Tension Lines (muscleautotensionlines) — auto-generates a tension-line curve down the long axis of each `muscle_id` region (the drivers the muscle deformers flex along). | `muscle` (+5 optional) |
| `muscle_tension_lines` | Muscle Tension Lines (muscletensionlines) — the tension-line authoring node: selects/edits the tension lines used to flex muscles, with symmetry support. | `muscle` (+8 optional) |
| `muscle_tension_lines_activate` | Muscle Tension Lines Activate (muscletensionlinesactivate) — activates / animates tension lines (min/max activation per group, mirror activation across the body). | `tension_lines` (+11 optional) |
| `muscle_deform` | Muscle Muscle Deform (muscledeform::2.0) — the modern quasi-static muscle deformer: solves the muscle solid to follow its tension lines with fiber stiffness + tension. | `muscle`, `tension_lines`, `tension_lines_anim` (+13 optional) |
| `muscle_flex` | Muscle Muscle Flex (muscleflex::2.0) — flexes a muscle along its tension lines by fiber-scale blend (the fast, non-solved bulge). | `muscle` (+15 optional) |
| `muscle_preroll` | Muscle Muscle Preroll (musclepreroll) — prerolls the muscle deformation from a rest pose over a hold + preroll frame range so a sim settles before the shot starts. | `muscle` (+7 optional) |
| `muscle_merge` | Muscle Muscle Merge (musclemerge) — merges up to six muscle streams into one muscle system (keeps `muscle_id` distinct). | `muscle` (+6 optional) |
| `muscle_mirror` | Muscle Muscle Mirror (musclemirror) — mirrors muscles from one side of the body to the other, renaming `muscle_id` by prefix swap. | `muscle` (+7 optional) |
| `muscle_deintersect` | Muscle Muscle Deintersect (muscledeintersect) — pushes overlapping muscles apart so they stop interpenetrating, out to a thickness offset. | `muscle` (+4 optional) |
| `muscle_adjust_volume` | Muscle Muscle Adjust Volume (muscleadjustvolume) — grows/shrinks muscle volume along normal + tangent, with optional collision resolution against the skin. | `muscle` (+15 optional) |
| `muscle_slide_constraint` | Muscle Muscle Slide Constraint (muscleslideconstraint) — builds sliding constraints that let a muscle slide over its neighbours / bones while resisting stretch. | `muscle` (+12 optional) |
| `muscle_tpose` | Muscle Muscle T-Pose (muscletpose) — stores / restores the muscle rest (T-pose) shape into a named attribute so downstream deformers have a stable reference pose. | `muscle` (+5 optional) |
| `otis_configure_muscle_tissue` | Muscle OTIS Configure Muscle and Tissue (otisconfiguremuscleandtissue) — assembles the muscle + tissue geometry and constraints into the payload the OTIS solver consumes (muscle-end / glue / tissue-to-bone constraints, tet quality). | `muscle` (+19 optional) |
| `tissue_solidify` | Muscle Tissue Solidify (tissuesolidify::2.0) — builds a tetrahedralized tissue (fat/fascia) shell of a given thickness under a skin/muscle surface. | `surface` (+16 optional) |
| `tissue_solidify_otis` | Muscle Tissue Solidify OTIS (tissuesolidifyotis) — the OTIS-solver variant: builds the tissue volume between an EXTERIOR skin and an inner shrink-wrapped surface. | `skin` (+14 optional) |
| `tissue_properties` | Muscle Tissue Properties (tissueproperties) — authors tissue material properties (surface + solid + sliding stiffness/damping/mass, rest scale) from a preset or explicit values, optionally masked. | `tissue` (+18 optional) |
| `tissue_properties_otis` | Muscle Tissue Properties OTIS (tissuepropertiesotis) — the OTIS-solver variant of Tissue Properties (core + shell solid stiffness/damping/mass, tissue-to-muscle / tissue-to-bone stiffness). | `tissue` (+20 optional) |
| `muscle_paint` | Muscle Muscle Paint (musclepaint) — the paint front-end for muscle attributes / masks on a muscle geometry (input 0). | `muscle` (+18 optional) |

### VEX (validated safe-VEX)

| Tool | What it does | Key params |
|---|---|---|
| `set_attrib_expr` | Run a safe VEX snippet on geometry attributes via a wrangle carrying a VALIDATED safe-VEX attribute snippet — the ONLY code-text lane in the bridge. | `outputs`, `code` (+8 optional) |

### ML / ONNX inference

| Tool | What it does | Key params |
|---|---|---|
| `onnx_inference` | Run a confined ONNX tensor-graph model over point attributes or a volume field — learned super-res / denoise / segmentation of clouds & volumes. | `input`, `modelfile`, `input_name`, `input_type` (+8 optional) |
| `ml_regression` | Train-inline + infer an attribute regression from a Labeled-Examples input — learned mask/label/value prediction on point clouds & heightfields. | `input`, `examples`, `method` (+6 optional) |
| `pca` | Principal Component Analysis over point/volume attributes — feature compression, shape-space analysis, and the preprocessing front end to ml_regression. | `input` (+6 optional) |
| `ml_volume_upres` | Learned volumetric super-resolution — sim coarse, upres detail (pyro/fluid content lane). modelfile is a confined .onnx; configured but NOT cooked here (resolves on downstream cook with a hash-pinned file). | `input`, `modelfile` (+5 optional) |
| `acquire_model` | Download an ONNX model for the ML tools from the HuggingFace host allowlist into <workdir>/models/, verified against a pinned sha256. | `repo`, `file`, `sha256` (+2 optional) |
| `ml_example` | Pair an Input Component (input 0) with a Target Component (input 1, required) into one supervised training EXAMPLE (ml_example) — the atom of an ML dataset (features -> targets). | `input`, `target` (+5 optional) |
| `ml_extract_example` | Pull a single training example (by index) back out of an Examples stream (ml_extractexample) — inspect/preview one sample. | `input` (+3 optional) |
| `ml_attrib_generate` | Synthesise randomised attribute values on a prototype (ml_attribgenerate) — data-augment a training set with controlled random inputs. | `input` (+6 optional) |
| `ml_pose_generate` | Sample randomised skeleton poses from a Pose Prototype (ml_posegenerate) — the training-data generator for pose-space / ML deformers. | `input` (+4 optional) |
| `ml_pose_serialize` | Flatten a skeleton pose into a serial point ATTRIBUTE (ml_poseserialize) — turn a rig pose into the fixed-length feature vector an ML model consumes. | `input` (+9 optional) |
| `ml_example_partition` | Split an Examples stream into parts no larger than max_part_size (ml_examplepartition) — batch a large training set into manageable chunks. | `input` (+2 optional) |
| `ml_deform` | WIRE-ONLY: build the learned character deformer (ml_deform) — apply a TRAINED model to deform a skin, driven by a skeleton pose. | `input`, `modelfile` (+7 optional) |

### Copernicus / COP

| Tool | What it does | Key params |
|---|---|---|
| `cop_constant` | COP generator: a constant-value image layer (Constant). | 4 optional |
| `cop_fractal_noise` | COP generator: fractal noise (Fractal Noise) — the core procedural texture source. noise_type, distance metric, amplitude, element size, octaves, lacunarity, roughness, contrast. | 9 optional |
| `cop_ramp` | COP generator: a linear/radial gradient (Ramp). ramp_type, number of cycles, phase, and the outside-range method. | 5 optional |
| `cop_remap` | COP filter: remap a layer's value range (Remap). op=remap maps input_min/max -> output_min/max with an outside-range method; op=threshold uses threshold+width+side. | `input` (+10 optional) |
| `cop_invert` | COP filter: invert a layer (Invert). method: complement (1-x), negate (-x), or reciprocal (1/x). | `input` (+2 optional) |
| `cop_equalize` | COP filter: normalize contrast by stretching/shifting a layer's range (Equalize). mode, fit_method, luminance type, black/white points, target average. | `input` (+7 optional) |
| `cop_blend` | COP filter: composite two layers (Blend). | `input`, `fg` (+3 optional) |
| `cop_bright` | COP filter: brightness/level adjust (Bright). brightness multiplies, shift adds. | `input` (+3 optional) |
| `cop_hsv` | COP filter: hue/saturation/value adjust or RGB<->HSV convert (HSV Adjust). op, hue_shift, sat_scale, sat_shift, val_scale, val_shift. | `input` (+7 optional) |
| `cop_glow` | COP filter: bloom/glow from bright areas (Glow). threshold, brightness gain, blur size, filter (box/gaussian), units (image/pixels). | `input` (+7 optional) |
| `cop_quantize` | COP filter: posterize a layer into discrete steps (Quantize). method (width/segments), segments count or width, rounding. | `input` (+5 optional) |
| `cop_blur` | COP filter: blur a layer (Blur). size (radius), filter (box/gaussian), units (image/pixels). | `input` (+5 optional) |
| `cop_sdf_shape` | COP generator: a signed-distance-field 2D shape (SDF Shape) — circle, rect, star, triangle, squircle, and dozens more. shape_class picks the family; `shape` is the shape name; scale sizes it; translate + rotate position it. | 6 optional |
| `cop_sdf_blend` | COP filter: combine two SDF layers (SDF Blend). | `input`, `b` (+6 optional) |
| `cop_sdf_to_mono` | COP filter: rasterize an SDF into a mono layer (SDF To Mono) — fill value, background value, optional outline (width + inside/outside/center), antialiasing. | `input` (+7 optional) |
| `cop_sdf_to_rgb` | COP filter: rasterize an SDF into a colour layer (SDF To RGB) — optional outline (width + inside/outside/center), antialiasing, iso offset. | `input` (+6 optional) |
| `cop_sdf_adjust` | COP filter: adjust an SDF (SDF Adjust) — iso_offset dilates/erodes the field, onion makes a hollow shell, abs makes it one-sided, invert swaps inside/outside. | `input` (+5 optional) |
| `cop_id_to_sdf` | COP filter: build an SDF from an ID/label layer (ID To SDF) — distance to the nearest ID boundary. invert flips the sign, iterations controls propagation, tile_size the block size. | `input` (+4 optional) |
| `cop_median` | COP filter: median filter (Median) — removes salt-and-pepper noise / speckle while keeping edges. size = three or five pixels; mask mixes the result. | `input` (+3 optional) |
| `cop_streak_blur` | COP filter: directional/motion blur along a line (Streak Blur). dir_type (angle/coord), angle, length, units, mode (on/min/max combine). | `input` (+8 optional) |
| `cop_kuwahara` | COP filter: Kuwahara filter (Kuwahara Filter) — edge-preserving painterly smoothing. radius (region size, pixels), luminance type, blend, separation. | `input` (+6 optional) |
| `cop_compare` | COP filter: compare a layer to a value or a second layer, output a 0/1 mask (Compare). | `input` (+7 optional) |
| `cop_edge_detect` | COP filter: edge detection (Edge Detect). preblur softens before detection, normalize scales the output, low/high thresholds gate weak/strong edges; method + mode are integer selectors. | `input` (+7 optional) |
| `cop_sharpen` | COP filter: sharpen (Sharpen) — amplifies detail via an unsharp mask. amplitude, gain, threshold, size, units (image/pixels). | `input` (+6 optional) |
| `cop_tile_pattern` | COP generator: a brick/tile pattern (Tile Pattern) — stackbond, herringbone, basketweave, flemishbond, and more masonry layouts. pattern picks the layout; mode (seamless/tilecount/tilesize); tiled_size the scale. | 4 optional |
| `cop_sequence_blend` | COP filter: blend across a temporal sequence (Sequence Blend) — motion trail / frame average. blend = mix amount, invert flips. | `input` (+3 optional) |
| `cop_wipe` | COP filter: transition/wipe between two layers (Wipe). | `input`, `b` (+6 optional) |
| `cop_chromatic_aberration` | COP filter: lens chromatic aberration (Chromatic Aberration) — per-channel scale/rotate to fringe R/G/B. r_scale/g_scale/b_scale, overall_scale, r_angle/g_angle/b_angle, filter. | `input` (+9 optional) |
| `cop_convolve` | COP filter: 3x3 convolution kernel (Convolve) — sharpen/emboss/edge/custom. | `input` (+7 optional) |
| `cop_distort` | COP filter: warp a layer (Distort) — push pixels along an angle (uniform) or by a distortion vector layer wired as `distortion` (input 1). angle, scale, dir_type, filter, border. | `input` (+7 optional) |
| `cop_derivative` | COP filter: image gradient / slope (Derivative) — rate of change of the layer, for normals / edges / relief. angle, scale, offset, difference_mode (central/forward/diagonal). | `input` (+5 optional) |
| `cop_segment_connectivity` | COP filter: label connected regions with unique IDs (Segment By Connectivity) — front end to id_to_sdf / per-region ops. connectivity (below/above/at/levels vs threshold), threshold, offset, collapse. | `input` (+5 optional) |
| `cop_segment_value` | COP filter: quantize a layer into labelled value bands (Segment By Value) — method (width or segments), width or segment count, min/max range. | `input` (+6 optional) |
| `cop_smooth_fill` | COP filter: smoothly fill/extend regions (Smooth Fill) — diffuses source values into the fill_area (inpaint / extend boundaries). | `input`, `fill_area` (+4 optional) |
| `cop_fill` | COP filter: flood-fill a layer (Fill) — replace with a value/sample. source (value/sample/first/last), color (fill value), id. | `input` (+4 optional) |
| `cop_feather` | COP filter: feather/soften mask edges (Feather) — direction (diamond/square/oct/circle), decay_mode (unitdist/decay), decay, unit_distance; outside feathers outward. | `input` (+6 optional) |
| `cop_light` | COP filter: shade a layer with a normals layer (Light). | `input`, `normals` (+4 optional) |
| `cop_bokeh` | COP filter: bokeh / depth-of-field blur (Bokeh) — radius, gain (highlight boost), resolution, filter kernel, normalize. | `input` (+6 optional) |
| `cop_dilate_erode` | COP filter: morphological dilate/erode (Dilate Erode) — positive radius grows bright areas, negative shrinks; soft_edge feathers; fill closes holes. | `input` (+5 optional) |
| `cop_channel_extract` | COP filter: extract a single channel into a mono layer (Channel Extract). channel = index (0=R,1=G,2=B,3=A). | `input` (+2 optional) |
| `cop_channel_swap` | COP filter: shuffle channels (Channel Swap) — set each output channel to any source channel or zero/one. | `input` (+5 optional) |
| `cop_mono_to_rgb` | COP filter: map a mono layer to RGB via a value range (Mono To RGB). input_min/max -> output_min/max, method (clamp/repeat). | `input` (+6 optional) |
| `cop_mono_to_rgba` | COP filter: promote a layer to RGBA (Mono To RGBA) — alpha_mode extend (copy value) or value (constant alpha_value). | `input` (+3 optional) |
| `cop_premult` | COP filter: premultiply / unpremultiply alpha (Premult). op = mult (premultiply) or divide (unpremultiply). | `input` (+2 optional) |
| `cop_crop` | COP filter: crop a layer (Crop). crop_min/crop_max = the [x,y] corners (image units 0..1); mode (data/both/display), border handling. | `input` (+5 optional) |
| `cop_tonemap` | COP filter: tone-map HDR to display range (Tonemap). operator = index 0..5 (Reinhard / Hable / ACES-style curves), exposure adjusts pre-gain. | `input` (+3 optional) |
| `cop_contrast` | COP filter: contrast adjust (Contrast) — contrast strength around a center pivot. | `input` (+3 optional) |
| `cop_gamma` | COP filter: gamma correction (Gamma) — gamma value, optional invert. | `input` (+3 optional) |
| `cop_transform` | COP filter: 2D/3D transform a layer (Transform). translate/rotate/scale_xyz/shear/pivot (each [x,y,z]), uniform scale, transform+rotation order, invert, border handling and reconstruction filter. | `input` (+12 optional) |
| `cop_color_correct` | COP filter: tonal-range colour grade (Color Correct). | `input` (+10 optional) |
| `cop_checkerboard` | COP generator: checkerboard test pattern (Checkerboard). rows/cols divisions, even/odd tile colours [r,g,b], translate/tile_size/bias ([x,y]). | 8 optional |
| `cop_clamp` | COP filter: clamp values to a lower/upper limit (Clamp). | `input` (+5 optional) |
| `cop_channel_join` | COP combiner: merge separate mono layers into one RGB/RGBA layer (Channel Join). | `inputs` (+3 optional) |
| `cop_chroma_key` | COP filter: HSV-range green/blue-screen keyer (Chroma Key) -> matte. hue_circle [4] (hue/sat center+width), lum_range [min,max], hue/sat/lum rolloff soft edges, interpolation (rolloff function 0..4), preview + preview_color [r,g,b], premult (multiply input by the matte). | `input` (+10 optional) |
| `cop_histogram` | COP filter: render a value histogram of the input as an image (Histogram). mode (colorbar/separatebar/graph), buckets, min/max range, outside (discard/clamp), scale; set_res + res [w,h] to override output resolution. | `input` (+9 optional) |
| `cop_vignette` | COP filter: darken/brighten toward the frame edge (Vignette). shape (round/rectangle/blend), brightness, circle_radius/circle_scale [x,y], blend amount, rect_size [x,y]/rect_roundness, center [x,y], blur, mask. | `input` (+11 optional) |
| `cop_height_to_normal` | COP filter: derive a normal-map layer from a mono height layer (Height to Normal) -- feeds cop_light `normals` for relief shading. normal_type (signed/offset), scale (height gain), read_outside, kernel (derivative distance). | `input` (+5 optional) |
| `cop_mirror` | COP filter: mirror/kaleidoscope a layer across one or more planes (Mirror). mode 0 = custom planes (angle0/offset0/flip0), 1 = number-and-offset (num_planes + angle/offset); flip reflection. | `input` (+9 optional) |
| `cop_average` | COP combiner: combine many input layers with one operation (Average). operation (add/average/multiply/min/max/over), `inputs` = COP node paths wired 0..n, signature = output layer type. | `inputs` (+3 optional) |
| `cop_worley_noise` | COP generator: cellular/Worley (Voronoi) noise (Worley Noise) -- complements cop_fractal_noise. element_size (cell size), jitter, lattice (grid/hex), metric, offset [x,y], tiled + tile_size [x,y]; post bias/gain/contrast (auto-enabled), complement. | 12 optional |
| `cop_julia` | COP generator: Julia-set fractal (Julia). real/imag = the Julia constant; escape_radius + max_iter control the escape test; scale [x,y]. | 7 optional |
| `cop_chladni` | COP generator: Chladni / cymatic standing-wave nodal pattern (Chladni). output (lines/abs/sdf), threshold+width (nodal-line mode), amp/amp_ratio, freq/freq_ratio, tile_size [x,y]. | 9 optional |
| `cop_bubble_noise` | COP generator: bubble/cellular fractal noise (Bubble Noise). amp/center, element_size, phase [4], offset [x,y], tile_size [x,y], max_octaves, lacunarity, roughness, distort, stretch [x,y], fold; post bias (auto-enabled). | 14 optional |
| `cop_crystal_noise` | COP generator: faceted crystalline Worley-derived noise (Crystal Noise). amp/center/contrast, metric, jitter, element_size, secondary + metric2, flatten_faces, tiled + tile_size [x,y], use_3d. | 14 optional |
| `cop_phasor_noise` | COP generator: phasor/Gabor procedural wave-and-noise field (Phasor Noise). type (phasorwave/phasornoise/gabornoise/intensityfield), wave_type (sine/rectangle/saw), amp/center, element, wave_bias, blend, offset [x,y], seed, kernels, rotation (uniform/varying), use_3d. | 14 optional |
| `cop_height_to_ao` | COP filter (terrain relief): ambient-occlusion bake from a mono height layer (Height to Ambient Occlusion). height_scale, view_radius (ray distance), step_scale, ray_count, hemisphere. | `input` (+6 optional) |
| `cop_height_to_shadow` | COP filter (terrain relief): cast-shadow map from a mono height layer + light profile (Height to Shadow). light_type (disk/sphere/directional), coord_mode (spherical/cartesian), azimuth/altitude/distance (spherical) or position [x,y,z] (cartesian), radius, height_scale, view_radius, step_scale. | `input` (+11 optional) |
| `cop_curvature` | COP filter (terrain relief): surface curvature from a normal/height layer (Curvature). method (index 0/1), curvature_type (gaussian/mean/principal_max/principal_min), output_type (index 0/1/2), normal_type (signed/offset), prescale/postscale, kernel, read_outside, normalize + min/max clamp. | `input` (+13 optional) |
| `cop_slope_dir` | COP filter (terrain relief): slope-direction (aspect) field from a mono height layer (Slope Direction). angle (post-rotation), scale (height-scale adjust), read_outside, kernel. | `input` (+5 optional) |
| `cop_resample` | COP filter: resize/resample a layer (Resample). size_control (res/aspect/pixel), base_size (parm/input), resolution [w,h], aspect [x,y] + aspect_preset, pixel_size, scale, fixed_side, filter (reconstruction), stretch mode, reframe. | `input` (+12 optional) |
| `cop_mono` | COP filter: combine channels into a single mono/luminance layer (Mono). op (lum/ntsclum/hdtvlum/average/max/min/magnitude/hue/saturation/value/red/green/blue/comp4/custom); supplying `weight` [4] sets op=custom + per-channel weights; normalize_weight. | `input` (+4 optional) |
| `cop_hextile` | COP filter: hexagonal seamless texture tiling (Hex Tile). | 11 optional |
| `cop_convert_normal` | COP filter: convert a normal-map layer between encodings (Convert Normal). conversion (tosigned -1..1 / tooffset 0..1), normalize, offset [x,y,z], scale [x,y,z]. | `input` (+5 optional) |
| `cop_combine_normals` | COP combiner: layer/blend two tangent-space normal maps (Combine Normals). | `input`, `fg` (+4 optional) |
| `cop_edge_detect_normal` | COP filter: ink/outline edges from a normal layer's angular discontinuities (Edge Detect Normal). tolerance, thickness_scale, weight_spread, blur, min_probe_radius. | `input` (+6 optional) |
| `cop_edge_detect_depth` | COP filter: crease/occlusion edges from Z-depth steps (Edge Detect Depth). tolerance, thickness_scale, weight_spread, blur, min_probe_radius. | `input` (+6 optional) |
| `cop_edge_detect_contour` | COP filter: silhouette/contour edges from value discontinuities (Edge Detect Contour). tolerance, thickness_scale, weight_spread, blur, min_probe_radius. | `input` (+6 optional) |
| `cop_swirl` | COP filter: spiral + lens-bulge deformation (Swirl). | `input` (+14 optional) |
| `cop_pixelate` | COP filter: mosaic / block-quantize a layer (Pixelate). mode (index 0/1), units (image/pixels), block_size or num_blocks [x,y], offset [x,y], mask; preblur + preblur_size. | `input` (+9 optional) |
| `cop_defocus` | COP filter: physically-parameterised camera defocus + bokeh (Defocus). | `input`, `depth` (+12 optional) |
| `cop_flip` | COP filter: mirror a layer (Flip). horizontal (xflip), vertical (yflip), diagonal (flop), mask. | `input` (+5 optional) |
| `cop_polar_to_uv` | COP generator: convert polar (angle, length) coordinates to a UV layer (Polar to UV). angle_unit (rad/deg/tau), angle, length. | 4 optional |
| `cop_random_mono` | COP generator: random mono field (Random Mono). range_method (minmax/ramp/specific), min/max, per_pixel, seed, time. | 7 optional |
| `cop_random_rgb` | COP generator: random colour field (Random RGB). range_method (minmax/ramp/specific), color_model (rgb/hsv), base_color [r,g,b] (enables base colour), per-channel random ranges rand_r/g/b or rand_hue/sat/val (each [min,max]), per_pixel, seed. | 12 optional |
| `cop_triplanar` | COP filter: world-space triplanar projection of a texture (Triplanar). | `texture`, `position`, `normal` (+15 optional) |
| `cop_triplanar_uv` | COP filter: triplanar UV coordinates from a world-position + normal pass (Triplanar UV). | `position`, `normal` (+2 optional) |
| `cop_triplanar_hextile` | COP filter: triplanar projection with per-cell hex-tile randomization (Triplanar Hex Tile). | `input` (+11 optional) |
| `cop_uv_map` | COP generator: generate a UV layer (UV Map). uv_space (texture/image/pixel), u_border/v_border (clamp/mirror/wrap/extend), u_shift/u_cycle, v_shift/v_cycle. | 8 optional |
| `cop_pos_map` | COP generator: generate a world-position layer (Position Map). source (pos/origin/view), per-axis x/y/z border (clamp/mirror/wrap/extend), x/y/z shift + cycle, signature (mono/vec3/...). | 12 optional |
| `cop_corner_pin` | COP filter: perspective corner-pin warp (Corner Pin). | `input` (+6 optional) |
| `cop_lens_distort` | COP filter: radial + tangential lens distortion / undistortion (Lens Distort). k1..k6 = radial coefficients, p1/p2 = tangential, center [x,y], scale [x,y], aspect, mask. | `input` (+13 optional) |
| `cop_uv_to_polar` | COP filter: convert a UV layer to polar (angle, length) coordinates (UV to Polar) -- inverse of cop_polar_to_uv. angle_unit (rad/deg/tau). | `input` (+2 optional) |
| `cop_fractal_noise_3d` | COP generator: world-space (3D-sampled) fractal noise (Fractal Noise 3D). noise_type (simplex/perlin/worleyA/worleyB/white/alligator), metric, amp/center/contrast, element_size, octaves, lacunarity, roughness, jitter, offset [x,y,z]; post bias/gain (auto-enabled), complement. | 16 optional |
| `cop_worley_noise_3d` | COP generator: world-space cellular/Worley noise (Worley Noise 3D). element_size/element_scale, jitter/jitter_scale, metric, offset [x,y,z]; post bias/gain (auto-enabled), complement. | 11 optional |
| `cop_crystal_noise_3d` | COP generator: world-space faceted crystalline Worley noise (Crystal Noise 3D). metric, amp/center/contrast, jitter, element_size, secondary + metric2, flatten_faces, offset [x,y,z], signature. | 12 optional |
| `cop_cloud_noise_3d` | COP generator: world-space billowy cloud noise (Cloud Noise 3D). amp/center, element_size, offset [x,y,z], max_octaves, lacunarity, roughness, distort, stretch [x,y,z], droop (auto-enables), fold, signature; post bias (auto-enabled). | 14 optional |
| `cop_xform_2d` | COP filter: 2D image transform (Transform 2D). translate [x,y], rotate, scale_xy [x,y] + uniform scale, shear, pivot [x,y]; xform_order, border, filter, invert. | `input` (+11 optional) |
| `cop_vector_xform` | COP filter: transform the 3-vector VALUES in a layer (Vector Transform) -- for normal/position/velocity layers. translate/rotate/scale_xyz/shear/pivot (each [x,y,z]), uniform scale, xform_order, rot_order, invert. | `input` (+10 optional) |
| `cop_vector_xform_2d` | COP filter: transform the 2-vector VALUES in a layer (Vector Transform 2D) -- for UV/flow layers. translate [x,y], rotate, scale_xy [x,y] + uniform scale, shear, pivot [x,y], xform_order, invert. | `input` (+9 optional) |
| `cop_space_transform` | COP filter: convert layer values between coordinate spaces (Space Transform). vector_type (position/vector), src_space + dst_space (buffer/pixel/texture/image/world). | `input` (+4 optional) |
| `cop_bend` | COP filter: bend/warp a layer (Bend). | `input` (+15 optional) |
| `cop_id_to_mask` | COP filter: build a 0/1 mask from selected IDs (ID to Mask). | `input` (+10 optional) |
| `cop_mono_to_sdf` | COP filter: convert a mono layer to a signed-distance field about an iso threshold (Mono to SDF). invert, iso, iterations, tile_size. | `input` (+5 optional) |
| `cop_denoise_tvd` | COP filter: total-variation diffusion denoise (Denoise TVD) -- pure math, NOT an AI model. iterations, speed, mask. | `input` (+4 optional) |
| `cop_fill_connected` | COP filter: flood-fill a connected region from a seed within a tolerance (Fill Connected). seed_location [x,y], source_location [x,y], tolerance, source (value/sample/first/last), color [r,g,b,a], id. | `input` (+7 optional) |
| `cop_ill_pixel` | COP filter: detect/fix/flag illegal pixels (Illegal Pixel). method (fixblend/fixzero/highlight/isolate), detect (d_nan/d_inf/both/custom), rule (less/lessequal/greater/greaterequal/equal), compare_value, highlight_color [r,g,b,a]. | `input` (+6 optional) |
| `cop_bound_rect` | COP filter: bounding-rectangle mask around pixels passing a threshold (Bound Rect). side (less/greater), threshold, fg/bg, units (image/texture/pixel). | `input` (+6 optional) |
| `cop_hyperbolic_tile` | COP generator: hyperbolic (Poincare-disk) regular-polygon tiling (Hyperbolic Tiling). iterations, polygon (sides), mapping (conformal/elliptic grid/squircle/equalarea), flattening, size, tile_fitting, rectanglize/stretch_to_fit/disk_mask. | 10 optional |
| `cop_convert_depth` | COP filter: convert a layer between depth / distance / height encodings (Convert Depth). source + dest (depth/dist/height), zero_depth. | `input` (+4 optional) |
| `cop_zcomp` | COP compositor: Z-depth composite two layers, nearest-surface wins (Z Composite). | `input`, `fg` (+5 optional) |
| `cop_uv_map_by_id` | COP filter: per-island UV map (or center/min/max/size) from an ID layer (UV Map by ID). | `input` (+11 optional) |
| `cop_project_on_layer` | COP filter: reproject a source layer into a target layer's space (Project on Layer). | `input`, `source` (+4 optional) |
| `cop_contact_sheet` | COP combiner: tile many input layers into a montage / contact sheet (Contact Sheet). | `inputs` (+8 optional) |
| `cop_copy_xform` | COP filter: stamp N transformed copies of a shape (Copy Transform). | `input` (+14 optional) |
| `cop_lattice_deform` | COP filter: warp a layer through a 4x4 lattice grid (Lattice Deform). | `input` (+6 optional) |
| `cop_surface_dither` | COP filter: surface-stable halftone/dither pattern -> mask or SDF (Surface Dither). | `input` (+10 optional) |
| `cop_sample` | COP filter: resample a texture through a UV map (Sample). | `input`, `texture` (+4 optional) |
| `cop_prefix_sum` | COP filter: directional running scan across the image (Prefix Sum). sweep_dir (px/mx/py/ny/xy/index), op (add/min/max/count), scale (none/pixel/texture/image). | `input` (+4 optional) |
| `cop_statistics` | COP filter: compute per-layer statistics (min/max/avg/...) as layer attributes (Statistics), readable by downstream nodes. | `input` (+1 optional) |
| `cop_layer_properties` | COP filter: set a layer's precision / border / type-info metadata (Layer Properties). precision (b8/b16/b32), border (constant/clamp/mirror/wrap), type_info (color/position/normal/id/mask/sdf/height/...) -- each auto-enables its setter. | `input` (+4 optional) |
| `cop_rgb_to_rgba` | COP filter: join an RGB layer with an alpha layer -> RGBA (RGB to RGBA). | `input` (+3 optional) |
| `cop_rgba_to_rgb` | COP filter: drop the alpha channel -> RGB (RGBA to RGB). unpremult (unpremultiply first). | `input` (+2 optional) |
| `cop_id_to_mono` | COP filter: convert an ID layer to a mono float layer (ID to Mono). conversion (cast/safe/bitwise). | `input` (+2 optional) |
| `cop_mono_to_id` | COP filter: convert a mono layer to an ID layer (Mono to ID). conversion (cast/safe/bitwise). | `input` (+2 optional) |
| `cop_id_to_rgb` | COP filter: assign a random colour per ID (ID to RGB). seed. | `input` (+2 optional) |
| `cop_rgb_to_uv` | COP filter: reinterpret an RGB layer as a UV (2-vector) layer (RGB to UV). | `input` (+1 optional) |
| `cop_uv_to_rgb` | COP filter: reinterpret a UV layer as RGB (UV to RGB); optional `mono` layer -> input 1 supplies the blue channel. | `input` (+2 optional) |
| `cop_rgba_to_uv` | COP filter: reinterpret an RGBA layer as a UV (2-vector) layer (RGBA to UV). | `input` (+1 optional) |
| `cop_uv_to_rgba` | COP filter: join two 2-vector layers into RGBA (UV to RGBA). | `input` (+2 optional) |
| `cop_channel_split` | COP filter: split a multi-channel layer into single-channel outputs (Channel Split) -- the inverse of cop_channel_join. | `input` (+1 optional) |
| `cop_layer_attrib_create` | COP filter: add a layer-metadata attribute (Layer Attribute Create). attr_name, attr_type (string/float/int), value (typed accordingly). | `input` (+4 optional) |
| `cop_layer_attrib_delete` | COP filter: delete layer-metadata attributes by name glob (Layer Attribute Delete). delete (glob to remove), keep (glob to preserve). | `input` (+3 optional) |
| `cop_dot` | COP filter: per-pixel dot product of two vector layers -> mono (Dot). | `input`, `b` (+1 optional) |
| `cop_cross` | COP filter: per-pixel cross product of two vec3 layers (Cross). | `input`, `b` (+1 optional) |
| `cop_pos_sample` | COP filter: sample a texture at coordinates read from a position layer (Position Sample). | `input`, `texture` (+1 optional) |
| `cop_statistics_by_id` | COP filter: per-ID statistics computed as layer attributes (Statistics by ID). | `input`, `source` (+1 optional) |
| `cop_match_udim` | COP filter: relocate an image onto a chosen UDIM tile (Match UDIM). udim (tile number, enables set_udim), invert, method (eye/data). | `input` (+4 optional) |
| `cop_autostereogram` | COP filter: build a Magic-Eye autostereogram from a pattern + depth image (Autostereogram). | `input`, `depth` (+5 optional) |
| `cop_uv_xform` | COP filter: translate/rotate/scale a UV layer (UV Transform). translate [x,y], rotate, scale_xy [x,y] + uniform scale, pivot [x,y], seed. | `input` (+7 optional) |
| `cop_layer` | COP generator: a blank typed layer at a chosen resolution/precision (Layer). signature (f1/f2/f3/f4/i), value (mono init), res [w,h], precision (b8/b16/b32), border (constant/clamp/mirror/wrap), type_info. | 7 optional |
| `cop_heat_distort` | COP filter: heat-haze distortion from internal noise (Heat Distort). global_scale, scale, element_size, detail_scale, roughness, cutoff, angle; distort/detail_distort/streak_blur toggles, mask. | `input` (+12 optional) |
| `cop_heat_distort_by_layer` | COP filter: heat-haze distortion driven by a `noise` layer (Heat Distort by Layer). | `input`, `noise` (+9 optional) |
| `cop_heightfield_visualize` | COP filter: scale/offset an incoming heightfield layer for visualization (Heightfield Visualize). height_scale, height_offset. | `input` (+3 optional) |
| `cop_sop_import` | COP generator: bridge an in-scene SOP into the copnet (SOP Import). | `sop` (+1 optional) |
| `cop_rasterize_geo` | COP: rasterize geometry attributes into an image layer (Rasterize Geometry). | `geometry` (+6 optional) |
| `cop_rasterize_setup` | COP: configure the rasterize camera / space that precedes Rasterize Geometry (Rasterize Setup). | `geometry` (+7 optional) |
| `cop_rasterize_curves` | COP: rasterize curve geometry as strokes into a layer (Rasterize Curves). | `curves` (+10 optional) |
| `cop_layer_to_geo` | COP: convert a COP layer back into SOP geometry (Layer to Geometry) -- a volume/VDB primitive. | `input` (+3 optional) |
| `cop_layer_to_points` | COP: emit SOP points from a COP layer (Layer to Points). | `input` (+6 optional) |
| `cop_layer_from_curves` | COP: colored/profiled strokes from curve geometry into a layer (Layer from Curves). | `curves` (+7 optional) |
| `cop_mask_from_curves` | COP: mask or SDF from curve geometry (Mask from Curves). | `curves` (+7 optional) |
| `cop_geo_to_layer` | COP: read a named primitive/VDB from geometry into a typed layer (Geometry to Layer). | `geometry` (+3 optional) |
| `cop_vdb_posmap` | COP: VDB voxel position map (VDB Pos Map). | `input` (+3 optional) |
| `cop_layer_from_vdb` | COP: convert a FloatVDB layer into a sampled COP layer (Layer from VDB). | `input` (+2 optional) |
| `cop_vdb_from_layer` | COP: convert a COP layer into a VDB, sized to a reference VDB (VDB from Layer). | `input`, `reference_vdb` (+2 optional) |
| `cop_rasterize_volume` | COP: raymarch a density VDB layer into an image (Rasterize Volume). | `input` (+8 optional) |
| `cop_integrate_volume` | COP: ray-integrate a volume layer to mono (Integrate Volume) -- depth / thickness. | `input` (+6 optional) |
| `cop_pyro_configure` | COP pyro: define the sim's voxel grid (Pyro Configure). | 8 optional |
| `cop_pyro_source_from_layer` | COP pyro: emit into a field from a source layer (Pyro Source from Layer). | `input`, `density` (+12 optional) |
| `cop_pyro_source_from_points` | COP pyro: emit into a field from a points source (Pyro Source from Points). | `input`, `points` (+8 optional) |
| `cop_pyro_advect` | COP pyro: advect a field by a velocity VectorVDB (Pyro Advect). | `input`, `velocity` (+12 optional) |
| `cop_pyro_buoyancy` | COP pyro: add temperature-driven buoyancy force to velocity (Pyro Buoyancy). | `input`, `temperature` (+13 optional) |
| `cop_pyro_dissipate` | COP pyro: dissipate a field over time (Pyro Dissipate). | `input` (+17 optional) |
| `cop_pyro_disturbance` | COP pyro: add disturbance detail to velocity (Pyro Disturbance). | `input` (+12 optional) |
| `cop_pyro_turbulence` | COP pyro: add turbulence / curl-noise detail to velocity (Pyro Turbulence). | `input` (+15 optional) |
| `cop_pyro_uniform_force` | COP pyro: apply a uniform directional force / drag to velocity (Pyro Uniform Force). | `input` (+13 optional) |
| `cop_pyro_activate` | COP pyro: grow / activate the sim's active voxel region (Pyro Activate). | `input` (+12 optional) |
| `cop_pyro_advect_by_map` | COP pyro: advect a field by a precomputed forward/reverse advection map (Pyro Advect by Map). | `input`, `fwd_map` (+5 optional) |
| `cop_pyro_build_advection_map` | COP pyro: build a forward/reverse advection map from a velocity field (Pyro Build Advection Map). | `input` (+7 optional) |
| `cop_pyro_axis_force` | COP pyro: vortex / axis / orbit force around an axis (Pyro Axis Force). | `input` (+17 optional) |
| `cop_pyro_light_ambient` | COP pyro: ambient / environment light contribution into a density field (Pyro Light Ambient). | `input` (+14 optional) |
| `cop_pyro_light_from_points` | COP pyro: point / directional light scattering into a density field (Pyro Light from Points). | `input` (+14 optional) |
| `cop_pyro_light_scatter` | COP pyro: multiple-scatter light through density + emission (Pyro Light Scatter). | `input` (+8 optional) |
| `cop_pyro_project_electrostatic` | COP pyro: make a velocity field non-divergent via electrostatic projection (Pyro Project Non Divergent Electrostatic). | `input`, `reference` (+12 optional) |
| `cop_pyro_packed_mipmap` | COP pyro: build a packed density mipmap (Pyro Packed Mipmap) -- the accelerator that feeds the `mipmap` input of the light microsolvers (cop_pyro_light_ambient / cop_pyro_light_from_points). | `input` (+3 optional) |
| `cop_pyro_block_begin` | COP pyro: start of the pyro feedback-block loop (Pyro Block Begin) -- seeds the per-iteration field state. | `input`, `velocity`, `temperature` (+11 optional) |
| `cop_pyro_block_end` | COP pyro: end of the pyro feedback-block loop (Pyro Block End) -- closes the loop and holds the loop controls. | `input`, `velocity`, `temperature`, `block_begin` (+14 optional) |
| `cop_pyro_solver` | COP pyro MACRO (one call): stamp a minimal COP-native pyro feedback-solve LOOP -- auto-wires cop_pyro_block_begin (loop start, seeds per-iteration density/v/temperature) -> a minimal pyro-advect BODY (advects the loop density by the loop velocity) -> cop_pyro_block_end (closes the loop, holds the loop controls), and sets the begin<->end blockpath linkage. | `input`, `velocity`, `temperature` (+6 optional) |
| `cop_vdb_leafpoints` | COP: emit points at VDB leaf/voxel centers (VDB Leaf Points). | `input` (+2 optional) |
| `cop_layer_to_vdb_leafpoints` | COP: VDB-leaf sample points from a layer (Layer to VDB Leaf Points). | `input`, `thickness_layer` (+3 optional) |
| `cop_vdb_activate_from_points` | COP: activate VDB voxel regions from point positions (VDB Activate from Points). | `input`, `points` (+5 optional) |
| `cop_vdb_reshape` | COP: conform a VDB to a reference VDB's transform/topology frame (VDB Reshape). | `input`, `reference` (+1 optional) |
| `cop_stamp_point` | COP: stamp a layer at point positions (Stamp Point). | `points`, `stamps` (+17 optional) |
| `cop_curve_scatter` | COP: scatter stamps along curves (Curve Scatter). | `curves`, `stamps` (+18 optional) |
| `cop_shape_scatter` | COP: scatter stamps across an image grid (Shape Scatter) -- no geometry needed. | `stamps` (+18 optional) |
| `cop_rasterize_layer` | COP: re-rasterize / reproject an existing layer (Rasterize Layer). | `input` (+5 optional) |
| `cop_vdb_visualize` | COP: shade a density VDB into an image (VDB Visualize). | `input` (+10 optional) |
| `cop_vdb_visualize_slice` | COP: slice-plane VDB visualization (VDB Visualize Slice). | `input` (+9 optional) |
| `cop_vdb_visualize_tree` | COP: VDB tree/topology visualization (VDB Visualize Tree). | `input` (+8 optional) |
| `cop_vdb_visualize_velocity` | COP: VDB velocity-field visualization (VDB Visualize Velocity). | `input` (+9 optional) |
| `cop_raytrace` | COP: raytrace geometry to AO / curvature / thickness / cavity / edge maps (Raytrace). | `geometry`, `origins`, `directions` (+16 optional) |
| `cop_bake_geometry_textures` | COP: bake normal/AO/curvature/position/thickness/height maps from geometry (Bake Geometry Textures). | `low` (+17 optional) |
| `cop_file` | COP generator: read an image from disk (File). | `filename` (+1 optional) |
| `cop_rop_image` | COP output driver: write the incoming COP stream to an image on disk (ROP Image Output). | `input`, `output` (+3 optional) |
| `cop_font` | COP: render text as an image (Font). | 4 optional |
| `cop_onnx` | COP: run ONNX model inference over an image (ONNX Inference). | `input` (+2 optional) |
| `cop_slapcomp_import` | COP: pull the in-memory slap-comp render buffer (Slap Comp Import). | 4 optional |
| `cop_cache` | COP: an in-memory per-frame cache of the incoming layer (Cache). | `input` (+3 optional) |
| `cop_fetch` | COP generator: fetch another COP node's output by path (Fetch). | 2 optional |
| `cop_camera_import` | COP generator: import a scene camera's parameters (Camera Import). | 2 optional |
| `cop_ocio_transform` | COP: apply an OpenColorIO color-space transform (OCIO Transform). | `input` (+5 optional) |
| `cop_live_video` | COP generator: capture frames from a live video/webcam device (Live Video). | 3 optional |
| `cop_denoise_ai` | COP: AI-denoise the incoming layer (Denoise AI). | `input` (+2 optional) |
| `cop_cryptomatte` | COP filter: extract a single coverage matte from a cryptomatte layer (Cryptomatte). | `input` (+3 optional) |
| `cop_cryptomatte_decode` | COP filter: decode a packed cryptomatte layer into id/coverage rank pairs (Cryptomatte Decode). | `input` (+1 optional) |
| `cop_cryptomatte_encode` | COP filter: encode id/coverage rank pairs into one packed cryptomatte layer (Cryptomatte Encode). | `input`, `cov_a`, `id_b`, `cov_b` (+1 optional) |
| `cop_grunge_aurora` | COP generator: aurora/streaked-veil weathering pattern (Grunge Aurora). | 21 optional |
| `cop_grunge_birchbark` | COP generator: birch-bark material pattern (Grunge Birch Bark). | 24 optional |
| `cop_grunge_layered_noise` | COP generator: 4-layer composite noise (Grunge Layered Noise) -- base noise + base cells + secondary noise + secondary cells. | 29 optional |
| `cop_grunge_pinebark` | COP generator: pine-bark material pattern (Grunge Pine Bark). | 21 optional |
| `cop_grunge_rust` | COP generator: rust/corrosion pattern (Grunge Rust). | 22 optional |
| `cop_cable_merge` | COP: combine two Copernicus cables (Cable Merge) -- `input` = input_cable (input 0), `reference` = the second cable (input 1). operation (union/intersection/difference/copy/fullunion/rename) controls how the two wire sets combine. | `input` (+3 optional) |
| `cop_cable_split` | COP: partition a Copernicus cable's wires into two cables (Cable Split). | `input` (+16 optional) |
| `cop_cable_pack` | COP: assemble named wires into one Copernicus cable (Cable Pack). | `input` (+2 optional) |
| `cop_cable_unpack` | COP: extract named wires out of a Copernicus cable (Cable Unpack). | `input` (+2 optional) |
| `cop_cable_filter` | COP: drop empty wires from a Copernicus cable (Cable Filter). | `input` (+1 optional) |
| `cop_cable_sort` | COP: alphabetically sort a cable's wires by name (Cable Sort). | `input` (+2 optional) |
| `cop_cable_switch` | COP: select one of two cables (Cable Switch). | `input` (+3 optional) |
| `cop_cable_rename` | COP: rename a cable's wires by pattern replacement (Cable Rename). | `input` (+5 optional) |

### Image / texture

| Tool | What it does | Key params |
|---|---|---|
| `sbs_archive` | SideFX Labs SBS Archive — a Cop2 GENERATOR that reads a Substance `.sbsar` archive and outputs its rendered texture into the shared /obj/cops2 cop2net. | 3 optional |
| `blackbody_texture` | SideFX Labs Blackbody (labs::blackbody_cop) — a Cop2 generator mapping temperature (Kelvin) to emitted blackbody color across the image, from temperature_low to temperature_high, with tonemap / gamma / adaptation / burn controls. | 12 optional |
| `attribute_to_texture` | SideFX Labs Attribute Import (labs::attribute_import) — a Cop2 generator that rasterizes a geometry point/vertex ATTRIBUTE into a texture over the geometry's UV layout. | 6 optional |
| `grid_texture` | SideFX Labs Grid Texture (labs::grid_texture) — a Cop2 generator producing a UV checker/grid reference texture with optional per-tile text, borders and colors. | 12 optional |
| `normal_color` | SideFX Labs Normal Color (labs::normal_color) — a Cop2 generator emitting a flat tangent-space normal-map color field (the default 'up' normal, RGB 0.5/0.5/1) at the chosen resolution; the base layer you composite detail normals onto. | 2 optional |
| `normal_map` | SideFX Labs Normal Map (labs::normal_map) — a Cop2 FILTER converting an input height/grayscale image (input 0) into a tangent-space normal map. | `input` (+5 optional) |
| `normal_combine` | SideFX Labs Normal Combine (labs::normal_combine) — a Cop2 FILTER that layers a detail normal map (input 1) over a base normal map (input 0) with correct reoriented normal blending. | `input`, `input2` (+1 optional) |
| `normal_invert` | SideFX Labs Normal Invert (labs::normal_invert) — a Cop2 FILTER that inverts selected axes of a tangent-space normal map (input 0). | `input` (+4 optional) |
| `normal_levels` | SideFX Labs Normal Levels (labs::normal_levels) — a Cop2 FILTER applying a levels/gamma remap to a normal map (input 0). | `input` (+4 optional) |
| `normal_rotate` | SideFX Labs Normal Rotate (labs::normal_rotate) — a Cop2 FILTER that rotates the tangent-space normal vectors of an input normal map (input 0) by `angle` degrees about the surface normal (keeps the map consistent when the texture is rotated on the UVs). | `input` (+2 optional) |
| `normal_normalize` | SideFX Labs Normal Normalize (labs::normal_normalize) — a Cop2 FILTER that re-normalizes every pixel of an input normal map (input 0) back to unit length (fixes non-unit normals after blending or filtering). | `input` (+1 optional) |
| `vector_normalize` | SideFX Labs Vector Normalize (labs::vector_normalize) — a Cop2 FILTER that rescales an input vector image (input 0) into a normalized range: `enable` turns it on; `min`/`max` set the target range the vector magnitudes are fit into. | `input` (+4 optional) |
| `demosaic` | SideFX Labs Demosaic (labs::demosaic) — a Cop2 FILTER that unpacks a rows x columns sprite atlas / flipbook sheet (input 0) into an individual frame: `frame` selects the tile, `start_frame` offsets the numbering. | `input` (+5 optional) |

### Solaris / LOP / USD

| Tool | What it does | Key params |
|---|---|---|
| `usd_layer` | Multi-branch USD / Solaris stage assembly & layer composition (LOP). op=merge combines several LOP branches into one stage (`inputs` wired input0..N; mergestyle sets the layer-composition/flatten style, default flattenloplayers = Simple Merge). op=sublayer composes external .usd/.usda/.usdc files as sublayers (`files`, read-confined; `input` = a LOP to layer onto). op=graft slots a source subtree under a destination prim (`input`=Input Stage, `source`=the LOP to graft into input1, `primpath`=destination parent prim, `src_prims`/`dst_prims`=source and destination prim paths). | 10 optional |
| `usd_configure` | Author USD prim / asset metadata (LOP configureprimitive) or select a variant -- pure metadata, no shader/VEX. op=configure sets, on the prims matching `primpattern`: kind (assembly\|group\|component\|subcomponent, the asset hierarchy), purpose (default\|proxy\|render\|guide), drawmode (default\|origin\|bounds\|cards -- USD-native proxy LOD so heavy assets draw as bounds/cards in the assembly stage and full geo at render), instanceable (bool), visibility (inherit\|invisible\|visible -- show/hide a prim), and specifier (def\|over\|class). op=variant selects a variant set/name (LOD or look switching). | 12 optional |
| `sop_import` | Bring a SOP network's geometry onto the USD stage -- the SOP->Solaris bridge. | `soppath` (+6 optional) |
| `usd_import` | Compose a USD file onto the stage as a reference / payload / sublayer. | `path` (+4 optional) |
| `usd_light` | Add/shape a USD/Karma light on the stage (light::2.0 or domelight::3.0). | 27 optional |
| `usd_camera` | Add/shape a camera prim on the USD stage (camera LOP). | 20 optional |
| `karma_render_settings` | WIRE-ONLY: build the Karma render graph in LOP (render-settings prim + usdrender ROP). | 14 optional |
| `render_geo_settings` | Author PER-PRIM Karma render settings on a USD stage (Render Geometry Settings LOP) — the deliver-lane workhorse: primary-ray visibility (set `visibility` to a Karma category glob — exclude camera for a PHANTOM / reflection-only prim), holdout/MATTE mode, motion + velocity blur, uniform-volume interpretation, and dicing quality. | `input` (+9 optional) |
| `karma_fog_box` | Add an atmospheric FOG VOLUME to a USD stage (Karma Fog Box LOP) — uniform or noise-modulated fog inside a box/sphere/etc. bound, for horizon haze / god-rays / depth. | 17 optional |
| `physical_sky` | Build a physically-based Karma sky + sun on the stage (karmaphysicalsky) -- the terrain/globe sun-study primitive. | 20 optional |
| `light_link` | Restrict which geometry a light (de)illuminates via a lightlinker LOP -- data-only prim-pattern strings, no expressions. | `light`, `geo` (+4 optional) |
| `assign_usd_material` | WIRE-ONLY: author a MaterialX Standard Surface material and BIND it to prim_pattern on the USD stage — the typed path to a TEXTURED Karma frame (materiallibrary + mtlxstandard_surface + assignmaterial; no VEX, no code). | `prim_pattern` (+24 optional) |
| `material_graph_create` | Create an empty PROCEDURAL MaterialX material graph — a /stage LOP materiallibrary you fill with shader_node_add / shader_connect / shader_set_param and bind with material_graph_assign. | 2 optional |
| `shader_node_add` | Add ONE MaterialX node to a material graph (library from material_graph_create). node_type = a whitelisted mtlx* type: mtlxstandard_surface (PBR shader terminal), mtlximage/mtlxtriplanarprojection (texture), mtlxnoise3d/mtlxfractal3d/mtlxworleynoise3d (noise), mtlxramplr/mtlxramp4 (ramp), mtlxgeompropvalue (READ a geometry attribute/terrain layer), mtlxmix/mtlxremap/mtlxmultiply/mtlxclamp (math), mtlxnormalmap/mtlxdisplacement (normal/disp). signature sets the node data type. | `library`, `node_type` (+2 optional) |
| `shader_connect` | Wire one MaterialX node's output into another's input (build a graph edge). dst_input is the input NAME (e.g. base_color, specular_roughness, normal, texcoord, in1) or a numeric index; src_output defaults to 'out' (every mtlx node's single output). | `dst`, `dst_input`, `src` (+1 optional) |
| `shader_set_param` | Set a TYPED literal on a MaterialX node — auto-handling the signature-suffix trap. param = the BASE parm name (e.g. amplitude, valuel, valuer, geomprop, file, octaves, inlow, outhigh); value = a number, an [r,g,b]/[x,y,z] list, or a string. | `node`, `param`, `value` |
| `material_graph_assign` | Bind a built material graph to geometry on the USD stage (materiallibrary + assignmaterial). shader = the TERMINAL node (mtlxstandard_surface, or a collect/mtlxsurfacematerial joining surface+displacement); prim_pattern = the geometry prim path/pattern to bind (required; set is_pattern for a wildcard). | `library`, `shader`, `prim_pattern` (+2 optional) |
| `material_ramp_on_attribute` | HERO one-call recipe: drive a COLOR shader channel from a RAMP on a GEOMETRY ATTRIBUTE — the terrain height->color idiom. | 10 optional |
| `material_noise_channel` | One-call recipe: drive a SCALAR shader channel from procedural NOISE. | 12 optional |
| `usd_prim_cube` | Create a USD Cube prim on the stage (cube LOP): size + transform. | 12 optional |
| `usd_prim_cone` | Create a USD Cone prim on the stage (cone LOP): axis, height, radius, transform. | 12 optional |
| `usd_prim_cylinder` | Create a USD Cylinder prim on the stage (cylinder::2.0 LOP): axis, height, radii. | 12 optional |
| `usd_prim_sphere` | Create a USD Sphere prim on the stage (sphere LOP): radius + transform. | 12 optional |
| `usd_prim_capsule` | Create a USD Capsule prim on the stage (capsule::2.0 LOP): axis, height, radii. | 12 optional |
| `usd_prim_mesh` | Create an empty USD Mesh prim + subdivision metadata (mesh LOP). | 12 optional |
| `usd_prim_points` | Create a USD Points prim on the stage (points LOP): transform. | 12 optional |
| `usd_prim_basiscurves` | Create a USD BasisCurves prim on the stage (basiscurves LOP): type, basis, wrap. | 12 optional |
| `usd_prim_hermitecurves` | Create a USD HermiteCurves prim on the stage (hermitecurves LOP): transform. | 12 optional |
| `usd_prim_primitive` | Create a single generic USD prim of any schema type (primitive LOP). | 7 optional |
| `usd_instancer` | Build a USD PointInstancer / reference-based instances on the stage (instancer LOP). | 17 optional |
| `usd_component_geometry` | Create a componentgeometry container driven by its internal SOP subnet (no file params). | 10 optional |
| `usd_component_geometry_variants` | Pack several input stages into a variant set on a component (componentgeometryvariants LOP). | 8 optional |
| `usd_component_material` | Bind materials to a component and optionally build a material variant set (componentmaterial LOP). | `input` (+8 optional) |
| `usd_layout` | Scatter/place instances of a prototype prim on the stage (layout LOP). | 14 optional |
| `usd_scene_import` | Import /obj scene objects (geo/lights/cameras) onto the stage (sceneimport::2.0 LOP). | 11 optional |
| `usd_graft_stages` | Graft another stage's subtree under a destination prim (graftstages LOP). | 9 optional |
| `usd_graft_branches` | Graft branches of a source stage onto destination prims, keeping position/material (graftbranches LOP). | 12 optional |
| `usd_restructure_scenegraph` | Reparent/rename prims and strip composition arcs (restructurescenegraph LOP). | `input` (+13 optional) |
| `usd_split_scene` | Split the stage into a selected branch and the remainder (splitscene LOP). | `input` (+4 optional) |
| `usd_isolate_scene` | Isolate part of the stage for faster iteration (isolatescene LOP). | `input` (+7 optional) |
| `usd_scope` | Create a Scope (grouping) prim, optionally reparenting matched prims under it (scope LOP). | 10 optional |
| `usd_collection` | Author a USD collection (named set of prims) on the stage (collection::2.0 LOP; icon param excluded). | 11 optional |
| `usd_prune` | Deactivate or hide prims on the stage (prune LOP). | 7 optional |
| `usd_split_primitive` | Split composed prims into separately-editable prims (splitprimitive LOP). | `input` (+8 optional) |
| `usd_xform` | Author a transform (xformOp) on matched prims (xform LOP). | `input` (+14 optional) |
| `usd_create_xform` | Create a new Xform prim with a transform (createxform LOP). | 14 optional |
| `usd_point_xform` | Transform prims by point attributes from a SOP (pointxform LOP). | `input` (+5 optional) |
| `usd_transform_uv` | Transform UV/texture coordinates on matched prims (transformuv LOP; map file param excluded). | `input` (+13 optional) |
| `usd_resample_transforms` | Resample animated transform time-samples at a fixed interval (resampletransforms LOP). | `input` (+4 optional) |
| `usd_duplicate` | Duplicate matched prims N times with a cumulative transform per copy (duplicate LOP). | `input` (+15 optional) |
| `usd_retime_instances` | Per-instance time offsets / retiming of a PointInstancer (retimeinstances LOP). | `input` (+11 optional) |
| `usd_extract_instances` | Extract PointInstancer instances into real prims (extractinstances LOP). | `input` (+12 optional) |
| `usd_merge_point_instancers` | Merge several PointInstancers into one (mergepointinstancers LOP). | `input` (+3 optional) |
| `usd_split_point_instancers` | Split a PointInstancer into subsets by prototype/attribute (splitpointinstancers LOP). | `input` (+7 optional) |
| `usd_modify_point_instances` | Edit individual instances of a PointInstancer — per-instance transform (modifypointinstances LOP). | `input` (+8 optional) |
| `usd_coordsys` | Bind a named coordinate system (coordsys) prim for texture/projection spaces (coordsys LOP). | `input` (+13 optional) |
| `usd_edit_material` | Open a USD material for editing / basing a new material on it (editmaterial LOP). | 6 optional |
| `usd_edit_material_properties` | Author/edit properties on a material prim (editmaterialproperties LOP). | 12 optional |
| `usd_material_variation` | Vary a bound material's shader parameters across prims (materialvariation LOP). | `input` (+8 optional) |
| `usd_unassign_material` | Remove material bindings from matched prims (unassignmaterial LOP). | 7 optional |
| `usd_vary_material_assignment` | Randomly/spatially vary which material is bound across prims (varymaterialassignment LOP). | `input` (+16 optional) |
| `usd_light_distant` | Create a UsdLux DistantLight (sun) on the stage (distantlight::2.0 LOP). | 15 optional |
| `usd_light_portal` | Create a UsdLux PortalLight (dome-light portal) on the stage (portallight LOP). | 10 optional |
| `usd_light_geometry` | Turn matched geometry into an emissive area light (geometrylight LOP). | 15 optional |
| `usd_light_mixer` | Group and transform lights via light collections for look-dev (lightmixer LOP). | 17 optional |
| `usd_shadow_catcher` | Turn matched prims into shadow-catcher surfaces for compositing (shadowcatcher LOP). | 6 optional |
| `usd_light_filter_library` | Author a library of light-filter prims and assign them to lights (lightfilterlibrary LOP). | 10 optional |
| `usd_add_variant` | Pack input stages into a variant set on a prim (addvariant LOP). | 15 optional |
| `usd_explore_variants` | Lay out every variant of a variant set side-by-side (explorevariants::2.0 LOP). | `input` (+16 optional) |
| `usd_create_lod` | Build polyreduced level-of-detail variants of a prim (createlod LOP). | `input` (+14 optional) |
| `usd_auto_select_lod` | Auto-select an LOD variant by camera distance (autoselectlod LOP). | `input` (+7 optional) |
| `usd_draw_mode` | Set USD imaging draw mode (bounds/cards/origin proxy) on matched prims (drawmode LOP). | 14 optional |
| `usd_configure_property` | Configure metadata on matched USD properties (configureproperty LOP). | 9 optional |
| `usd_configure_stage` | Configure stage-level population/load/mute rules (configurestage LOP). | 11 optional |
| `usd_edit_properties` | Create/edit prims and their properties in bulk (editproperties LOP). | 12 optional |
| `usd_store_parameter_values` | Store named parameter values as stage data for reuse (storeparametervalues LOP). | 5 optional |
| `usd_set_extents` | Author/recompute the extent (bbox) hint on matched prims (setextents LOP). | `input` (+8 optional) |
| `usd_edit_xform` | Transform-edit matched prims (edit LOP). | 16 optional |
| `usd_layer_break` | Insert a layer break so downstream edits go onto a fresh layer (layerbreak LOP). | 2 optional |
| `usd_set_variant` | Select which variant of a variant set is active on matched prims (setvariant LOP). | `input` (+5 optional) |
| `usd_copy_property` | Copy a property/attribute from source prims to destination prims (copyproperty LOP). | `input` (+7 optional) |
| `usd_shot_split` | Split stage edits into per-shot layers for editorial hand-off (shotsplit LOP). | `input` (+8 optional) |
| `usd_shot_switch` | Switch between candidate input stages by index for shot assembly (shotswitch LOP). | 4 optional |
| `shot_load` | Load shot layers onto the /stage from the shot pipeline (shotload LOP) — the editorial entry point that populates a stage from configured shots. | 5 optional |
| `shot_output` | WIRE-ONLY: build a Shot Output ROP LOP (shotoutput) that saves the stage to disk for a shot — configured but NEVER executed (you fire the write). output is WRITE-confined; the pre/post-render SCRIPT params are never exposed. | `input`, `output` (+5 optional) |
| `shot_layer_edit` | Route stage edits into a specific shot layer (shotlayeredit LOP) — the editorial layer targeter. | `input` (+6 optional) |
| `usd_value_clip` | Author a USD value-clip prim that streams animation from a set of clip files (valueclip LOP). clip_files and manifest_file are realpath-confined to the working directory. | 9 optional |
| `usd_geometry_sequence` | Import an animated geometry-file SEQUENCE onto the stage (geometrysequence LOP) — the streaming read bridge for a per-frame .bgeo/.vdb cache. file is READ-confined (put a $F token for a sequence). | `file` (+7 optional) |
| `usd_geo_clip_sequence` | Load / write a USD geometry value-clip sequence (geoclipsequence LOP) — cache an animated stage subtree to per-frame clip files and stream it back. load_clip_file (READ) and save_clip_file (WRITE) are realpath-confined. | 13 optional |
| `usd_blend_constraint` | Author a USD Blend constraint — blend a prim's transform between source + target prims (blendconstraint LOP). | `input` (+9 optional) |
| `usd_followpath_constraint` | Author a USD Follow-Path constraint — slide a prim along a curve (followpathconstraint LOP). | `input` (+14 optional) |
| `usd_lookat_constraint` | Author a USD Look-At constraint — aim a prim at a target (lookatconstraint LOP). | `input` (+11 optional) |
| `usd_parent_constraint` | Author a USD Parent constraint — parent a prim's transform to a target (parentconstraint LOP). | `input` (+14 optional) |
| `usd_points_constraint` | Author a USD Points constraint — constrain a prim to weighted points of a target (pointsconstraint LOP). | `input` (+13 optional) |
| `usd_surface_constraint` | Author a USD Surface constraint — pin a prim to a UV location on a target surface (surfaceconstraint LOP). | `input` (+14 optional) |

### Look, lights & camera

| Tool | What it does | Key params |
|---|---|---|
| `build_globe` | Build a WGS84-ellipsoid globe with an analytic lon/lat UV drape (the 'skin'), so an equirectangular texture and ECEF-pinned tiles register by construction. | `name` (+12 optional) |
| `add_light` | Add a light spanning the full hlight Type palette plus dome. | 21 optional |
| `add_camera` | Create a camera to MATCH A REFERENCE PHOTO / recreate an image / camera-solve a shot — set the intrinsics so a render lines up with a target picture. focal length (mm) + aperture (mm) = field of view / perspective compression (shorter focal or wider aperture = wider FOV); resx/resy = resolution gate; aspect. | 17 optional |
| `camera_aim` | Point an existing camera at a target -- data-only (no look-at expression/constraint). | `camera` (+6 optional) |
| `camera_path` | Animate an OBJ camera along a curve SOP -- data-only (computed literal keyframes, NO Follow-Path constraint / $F expression). | `curve` (+6 optional) |
| `setup_karma` | WIRE-ONLY: build an OBJ-context Karma render graph (the /out `karma` ROP wired to a camera + resolution + output image) and hand it back UNRENDERED — the human fires it (this removes the resource-DoS / heavy-scene freeze surface). picture is written under the working directory (PNG/EXR/JPG by extension). | 9 optional |
| `setup_prorender` | WIRE-ONLY: build a Solaris (/stage) USD-render ROP set to AMD Radeon ProRender (the Hydra delegate `HdRprPlugin`) and hand it back UNRENDERED — the human fires it (same posture as setup_karma / karma_render_settings; removes the resource-DoS / GPU-cook-freeze surface). | 5 optional |
| `substance_material` | SideFX Labs Substance Material — assigns a Substance material to the input geometry (input 0). | `input` (+9 optional) |
| `quickmaterial` | SideFX Labs Quick Material — assigns ONE material (Principled / MatCap / Labs PBR) to the input geometry (`input`), optionally to a primitive `group`, driven by texture maps (`*_texture`, READ-confined) and scalar levers (roughness / metallic / ior). | `input` (+14 optional) |
| `set_view_camera` | Control the Scene Viewer viewport: look through a camera (bind the viewport to it) and/or switch to a standard orthographic/perspective view (top/bottom/front/back/left/right/persp), and optionally frame all geometry to fit the view. | 4 optional |
| `flightcam` | Keyframed flight camera driven by a poses .json, with the source cloud loaded as context. | `poses` (+7 optional) |
| `assign_material` | Assign a PBR material / shader (Principled Shader principledshader::2.0) to the input SOP via a Material SOP so it renders with a surface look — typed literal params + texture maps only (no VOP/shader-graph authoring). | `input` (+26 optional) |
| `bake_texture` | WIRE-ONLY: build the texture-bake graph (Bake Texture 3.0) with a confined output; does not execute. | `output` (+3 optional) |
| `three_point_light` | Create a Three Point Light rig OBJ (three_point_light) — one node bundling key / fill / rim / bounce lights aimed at a shared target. | 18 optional |
| `indirect_light` | Create an Indirect (global-illumination bounce) Light OBJ (indirectlight). dimmer scales the indirect contribution. | 6 optional |
| `ambient_light` | Create an Ambient Light OBJ (ambient) — a flat, uniform fill added to the whole scene. | 8 optional |
| `environment_fog` | Create an Environment Fog OBJ (fog) — a scene-filling atmospheric volume container. t/r/s/scale size and place the fog box. | 5 optional |
| `reference_image` | Create a Reference Image OBJ (refimage) — a flat image plane for modelling reference / matching. image_file is realpath READ-confined to the working directory. | 9 optional |
| `stereo_camera` | Create a Stereo Camera OBJ (stereocam) — a container grouping a left + right camera. | 7 optional |
| `stereo_camera_rig` | Create a Stereo Camera Rig OBJ (stereocamrig) — a full parametric stereo rig with interaxial / zero-parallax controls and camera intrinsics. | 14 optional |
| `vr_camera` | Create a VR Camera OBJ (vrcam) — a stereo panoramic camera for VR renders (sphere/cylinder = equirectangular / cylindrical panoramas). | 14 optional |

### Scene, navigation & viewport

| Tool | What it does | Key params |
|---|---|---|
| `scene_info` | Report the current Houdini scene: hip file, frame, version, and /obj contents. | — |
| `read_network` | Read a network's STRUCTURE as text — the durable, token-cheap map for rebuilding your picture of a big node graph (especially after a context compaction) WITHOUT spending budget on a screenshot. | 5 optional |
| `set_frame` | Set the current timeline frame / playhead — jump to a point in time so subsequent cooks, snapshots, exports, or simulation reads evaluate at that frame. | `frame` |
| `set_display` | Set the display and/or render flag on a SOP or OBJ node — clean control over what's shown/rendered. | `node` (+2 optional) |
| `delete_node` | Delete a node (SOP or OBJ) from the scene. | `node` (+1 optional) |
| `clear_scene` | Start fresh in the /obj network without a destructive File->New. mode='hide' (DEFAULT, non-destructive + reversible) turns the display flag OFF on every /obj object so the viewport clears but the nodes remain; mode='delete' REMOVES the /obj objects (destructive — like deleting each). | 2 optional |
| `save_scene` | Save / write the whole Houdini scene (all nodes and networks) to a .hip / .hipnc / .hiplc project file on disk, confined to the working directory — the 'save my work' / snapshot-the-session op. | `path` |
| `select_node` | Select a node (clearing any prior selection) and make it the current node. | `node` (+1 optional) |
| `frame_selected` | Frame the Scene Viewer on a node — the Shift+H 'home selected' equivalent, for precise framing in mixed-scale scenes where frame-all is useless. | 1 optional |
| `layout_nodes` | Auto-arrange a network's children so freshly added nodes don't stack — the Shift+L equivalent. | `parent` |
| `find_error_nodes` | Read-only diagnostic: scan a subtree for nodes in an error (and optionally warning) state and report their paths, types, and messages so an AI agent can self-correct. root (default /obj) scopes the scan (root plus every descendant); a guarded cook is attempted per node so a broken node (e.g. a File SOP pointing at a missing path) surfaces as a captured error, not a raised exception. | 2 optional |
| `batch` | Run up to 64 tool ops in ONE call to cut per-call latency (e.g. build a node chain in a single round-trip). | `ops` (+1 optional) |
| `capabilities` | Start here — getting started, how to use this server, an overview of what it can do, orientation and first steps for a new agent. | — |
| `node_reference` | Query the authoritative live-probed Houdini 21.0.671 node reference — verified node types and their real parameter names, the source of truth for what node chains are possible. | 3 optional |
| `vex_reference` | Query the authoritative offline Houdini 21.0.671 VEX reference: 1073 builtin functions (verbatim signatures, summaries, help groups) plus a curated wrangle workflow/patterns guide. | 4 optional |
| `recipe_reference` | Canonical, tool-mapped workflow recipes — how to ACTUALLY do X with this server's tools, and the ROUTER that picks which recipe fits what you're looking at. | 4 optional |
| `viewport_display` | Toggle Scene Viewer display/analysis overlays (point markers, point/prim/vertex normals, point/prim numbers, point positions, point trails) so a snapshot/capture_ui screenshot reads for geometry analysis. | 9 optional |
| `read_geo_stats` | Read back structured geometry statistics of a node — point/primitive/vertex counts, bounding box (min/max/size/center), and the full list of point/prim/vertex/detail attributes with their types — via fast intrinsics (safe on multi-GB point clouds; no per-point Python loop). | `node` (+1 optional) |
| `isolate` | Crop a point cloud to a region of interest: keep only the points that fall inside an oriented crop box object (uses the box OBJ's own world transform, so a rotated box crops an oriented volume) and delete the rest — trim a scan down to one building/room/area. box = a box OBJ acting as the crop bounds. out optionally writes the cropped cloud to a confined .bgeo/.ply. | `input`, `box` (+1 optional) |
| `object_merge` | Reference / import / pull one or many other SOP or OBJ geometry streams into a network BY PATH, WITHOUT copying the geometry — the large-scene, venue, and multi-object assembly primitive (bring many objects together / combine / gather / instance geometry from elsewhere in the scene, survives huge scenes because nothing is duplicated). | `sources` (+7 optional) |
| `subnet_organize` | Organize / tidy / clean up the node graph (data-only, no cook, no geometry change): op=collapse boxes a set of sibling nodes into a subnet (group nodes together); op=create makes an empty subnet container; op=tag labels a node with a network-editor color, a comment/note, and/or a user-data key/value so an assembled graph is navigable and readable. | 9 optional |
| `matchsize` | Fit / resize / rescale / reposition / align a geometry input to match a reference bounding box or an explicit target size — the typed 'drop this asset into the scene at the right size and position' / 'normalize / snap-to-bounds' node (matchsize SOP). | `input` (+9 optional) |
| `scene_assemble` | One-call staged multi-piece scene assembly / composition macro (the venue-portfolio primitive): build a whole navigable assembled scene from many source geometries in a single fresh /obj geo. | `name`, `pieces` (+2 optional) |
| `list_node_types` | Discover / enumerate / search the available Houdini node-type palette — which operator (SOP/OBJ/LOP/DOP/COP/ROP/VOP/...) types exist by name, with per-category counts. | 3 optional |
| `reload_node` | Force a node to re-read its source file from disk and refresh / recook — use after a File SOP's .bgeo/.obj (or any cached file) was rewritten externally so Houdini picks up the new contents. | `node` |
| `mem` | Report process working set + system RAM + Houdini memory + GPU VRAM (whole-card total/used/avail — the freeze-ceiling signal) for self-monitoring and memory-governed operation sizing: am I running out of memory, how much VRAM / GPU memory headroom is left, what's my memory budget, how much more can I build before it freezes. | — |
| `viewport_snap` | Set / configure Scene Viewer SNAPPING — snap-to-grid, snap to points / prims / geometry / templates / other objects / guides / drawables. | 6 optional |
| `view_message` | Show / flash / display an operator-facing message (notification, on-screen toast, status-line prompt) in the Scene Viewer — the watched-crew UX for telling the human what the agent is doing. type=flash is a transient overlay (duration s); type=prompt sets the persistent status-line prompt at a severity level. | `message` (+3 optional) |
| `home_view` | Home / reset / recenter / frame-all the current viewport to the default view DIRECTION for a target (all \| selected \| grid \| non_templated) — distinct from frame_selected, which reframes but KEEPS the current view direction. | 1 optional |
| `save_view_to_camera` | Bake / save the current interactive viewport view (transform + lens settings) INTO a camera OBJ node — 'save view to camera' / create-a-camera-from-this-view. | `camera` (+1 optional) |
| `construction_plane` | Show / hide / resize the Scene Viewer construction-plane GRID — visibility, cell size, cell count, cells-per-ruler-line. | 4 optional |
| `ui_reference` | Read-only control-surface discoverability / help (sibling of node_reference/vex_reference): DISCOVER the control-surface tools + confirmed enum tokens, and — when a GUI is live — READ the current drivable-UI state (snapping mode, construction-plane visibility, viewer state name, desktop names). | 1 optional |
| `switch_desktop` | Switch / activate a DESKTOP (workspace / saved pane layout — Build, Animate, Solaris, …) by name. | `desktop` |
| `pane_focus_node` | Jump / navigate / point a path-based pane (parm \| network \| scene) AT a node (quick-nav) — makes it the pane's current node; for network you may also dive into the node's own network. | `node` (+2 optional) |
| `pane_pin` | Pin / unpin (or set the link group of) a path-based pane so it STOPS following selection — freeze the parm/network/scene pane on the current node. | 3 optional |
| `pane_tab` | Open / create / close / switch / clone / retype pane TABS by type (data-only) — add a Network Editor / Parameters / Spreadsheet / Details tab, close one, or make one current. op=query lists valid paneTabType tokens + the current tabs (run FIRST to discover pane ids/types); create/set_type/current/clone/close act on the target pane. | 3 optional |
| `pane_layout` | Split / maximize / restore / arrange the PANE layout of the current desktop (reversible session-UI) — split a pane horizontally or vertically, maximize it, or restore. | `op` (+1 optional) |
| `network_navigate` | Navigate / jump / dive the Network Editor through the node graph — dive into a network (path), select + make a node current (current_node), and/or frame the selection (frame). | 3 optional |
| `hotkey_reference` | Read-only default-hotkey / keyboard-shortcut map reader from hou.hotkeys (sibling of vex_reference/node_reference) — look up / find keyboard shortcuts: context → command → assigned keys + human label, with an optional search filter or category mode. | 5 optional |
| `set_node_flags` | Set / toggle NODE FLAGS on one node — display, render, template, bypass, lock, soft-lock, highlight, debug, visible, xray, display-comment, descriptive-name — via setGenericFlag. | `node` (+13 optional) |
| `node_organize` | Organize / tidy / arrange / label / color-code ONE node in the network — set its color, node SHAPE, comment (display-only text), name (rename), and network POSITION. | `node` (+6 optional) |
| `viewport_appearance` | Set GeometryViewport display / inspection / shading settings so geometry is VISIBLE for the visual-acceptance / screenshot loop — shading/display mode (wireframe · shaded · flat · matcap · hidden-line · bounding-box), show point/prim/vertex markers · normals · numbers, backface removal, textures, ambient occlusion, color scheme, lighting. | 19 optional |
| `viewport_layout` | Set the Scene Viewer's viewport LAYOUT — how the pane splits into viewports (single \| quad \| double \| triple variants). | `layout` (+1 optional) |
| `enter_state` | Enter / activate one of the five FIXED built-in Scene Viewer tool states by name (data-only by construction) — view (look-around) \| translate \| rotate \| scale (transform-handle states) \| current_node (the current node's own tool state). | `state` |
| `viewport_optimize` | Speed up a slow / laggy / heavy Scene Viewer by applying display-only performance levers — lower volume quality, cap scene polygon display, enable distance-based packed culling, reduce level-of-detail and antialiasing. | 1 optional |
| `rivet` | Create a Rivet OBJ (rivet) — a transform locked to a point/primitive on a deforming surface (the classic 'stick a prop to an animated mesh' attach). | 10 optional |
| `sticky` | Create a Sticky OBJ (sticky) — a transform pinned to a UV coordinate on a surface, so it slides with the surface as it deforms. | 11 optional |
| `blend_sticky` | Create a Blend Sticky OBJ (blendsticky) — a Sticky whose position is a weighted BLEND of several source sticky objects (parent the source stickies to it). | 8 optional |

### Parameters

| Tool | What it does | Key params |
|---|---|---|
| `set_parm` | Set / write / drive one node parameter to a LITERAL value (literal-only, never an expression) — the safe, data-only counterpart to a generic parm setter. | `node`, `parm`, `value` (+1 optional) |
| `get_parm` | Read / get / inspect one node parameter value (read-only, data-only): returns the evaluated value, the raw / unexpanded value, the parm type, whether it currently holds an expression or keyframes (with the expression string), and whether it is a denied code parm (so an injected expression is visible). | `node`, `parm` (+1 optional) |
| `set_keyframe` | Set / add one keyframe to animate a numeric parm at a frame with a LITERAL numeric value + an optional allowlisted interpolation (constant / linear / bezier / ease / …) — literal-value animation for float / int / toggle / menu parms. | `node`, `parm`, `frame`, `value` (+2 optional) |
| `delete_keyframes` | Remove / clear / delete keyframes on a parm so it returns to a static literal value (un-animate). | `node`, `parm` (+3 optional) |
| `list_keyframes` | Read-only list of a parm's keyframes / animation — each keyframe's frame, literal value, and interpolation string (e.g. | `node`, `parm` (+1 optional) |

### Deliver & export

| Tool | What it does | Key params |
|---|---|---|
| `export_geometry` | Cook a SOP and write it to a SINGLE geometry file (the /out `geometry` ROP; executes the write). | `input`, `output` (+1 optional) |
| `batch_export` | Split `input` geometry into PARTITIONS and write ONE confined file per partition — the #1 recurring TD ask ("split this by group/name/attribute and export each piece"). split_by=name (default) writes one file per distinct value of the `name` primitive attribute; split_by=group writes one file per primitive/point group; split_by=attribute writes one file per distinct value of the point/prim attribute named in `attribute`. | `input` (+7 optional) |
| `export_pointcloud` | Export a point cloud / geometry to PLY inside the working directory — the exit for clouds imported via import_pointcloud/las_import. | `input`, `output` (+2 optional) |
| `export_alembic` | Export a SOP to an Alembic .abc (the /out `alembic` ROP; executes the write) — the standard interchange for animated/deforming geometry into Maya/Nuke/Blender/UE. frames=[start,end] writes an ANIMATED cache into the single .abc; omit for a static frame. format ogawa (modern, faster, smaller — recommended) \| hdf5 (legacy) \| default. | `input`, `output` (+3 optional) |
| `capture_ui` | Screenshot / see / read the LIVE Houdini interface, ISOLATED to a single pane on request. | 5 optional |
| `snapshot` | See/screenshot the 3D result — a single OpenGL PNG of the viewport/camera returned INLINE in the tool result (the agent's eyes for image->3D verification). | 6 optional |
| `niagara` | SideFX Labs Niagara — WIRE-ONLY exporter SOP that packages the incoming particles/points (`input`, input 0) for Unreal's Niagara system. | `input` (+8 optional) |
| `pcg_export` | SideFX Labs PCG Export — WIRE-ONLY exporter SOP that packages the incoming instance points (`input`, input 0) for Unreal's PCG framework. | `input` (+7 optional) |
| `unreal_groom_export` | SideFX Labs Unreal Groom Export — package a Houdini groom for Unreal's groom system and write it as Alembic. | 13 optional |
| `unreal_spline` | SideFX Labs Unreal Spline — package the incoming curve (`input`, input 0) as an Unreal spline; the cooked SOP output passes the curve through (optionally tagged). orient_along_curve writes per-point orientation; prim_tags writes per-primitive tags. | `input` (+4 optional) |
| `vector_field` | SideFX Labs Vector Field — resample an incoming velocity field (`input`, input 0 — velocity volumes or points carrying a velocity attribute) into a uniform grid and prepare an Unreal/Unity .fga vector-field export; the cooked SOP output visualizes the sampled field. input_type picks volumes(0) or points(1); velocity_volumes/velocity_attr name the source; div sets the grid resolution divisor. | `input` (+9 optional) |
| `niagara_rop` | SideFX Labs Niagara ROP — the /out Driver form of the Niagara exporter: references a SOP by path (`soppath`) and writes it for Unreal's Niagara system. | 6 optional |
| `rbd_to_fbx` | SideFX Labs RBD to FBX — a /out Driver that exports a packed RBD simulation (referenced by `node_to_export`) as a rigid-body FBX for a game engine. | 9 optional |
| `vertex_animation_textures` | SideFX Labs Vertex Animation Textures — the flagship VAT exporter: bakes an animated SOP (referenced by `soppath`) into position/rotation/color textures + a base mesh for Unreal/Unity VAT shaders. | 11 optional |
| `xyz_pointcloud_exporter` | SideFX Labs XYZ Pointcloud Exporter — a /out Driver that writes a SOP's points (referenced by `objpath1`) to a plain-text XYZ/CSV point cloud. | 3 optional |
| `texture_sheets` | SideFX Labs Texture Sheets — WIRE-ONLY texture-sheet / flipbook renderer (Mantra ROP). | 18 optional |
| `goz_export` | SideFX Labs GoZ Export — WIRE-ONLY exporter that hands geometry to ZBrush via the GoZ bridge. | `input` (+2 optional) |
| `filecache` | SideFX Labs File Cache — WIRE-ONLY geometry cache. | `input` (+6 optional) |
| `static_fracture_export` | SideFX Labs Static Fracture Export — WIRE-ONLY exporter for the pieces of a fractured object (`input`). | `input` (+5 optional) |
| `simple_baker` | SideFX Labs Simple Baker — WIRE-ONLY map baker. | `input` (+19 optional) |
| `unreal_pivotpainter` | SideFX Labs Unreal Pivot Painter — WIRE-ONLY exporter that bakes pivot / hierarchy textures for UE4/5 wind animation. | `input` (+10 optional) |
| `zibravdb_filecache` | SideFX Labs ZibraVDB File Cache — WIRE-ONLY compressed-VDB cache. | `input` (+3 optional) |
| `rop_zibravdb_compress` | SideFX Labs ROP ZibraVDB Compress — WIRE-ONLY compressed-VDB ROP. | `input` (+3 optional) |
| `games_baker` | SideFX Labs Games Baker — a /out Driver that bakes texture maps (basecolor / normal / AO / roughness / metallic / curvature / thickness / position / …) from a high-res source mesh onto a low-res target mesh via Houdini's native COP/Karma bake. | 40 optional |
| `csv_exporter` | SideFX Labs CSV Exporter — a /out Driver that writes a SOP's point/prim attributes (referenced by export_node) to a plain-text CSV file. | 12 optional |
| `json_exporter` | SideFX Labs JSON Exporter — a /out Driver that writes a SOP's attributes (referenced by export_node) to a JSON file. | 5 optional |
| `export_usd` | Write a USD stage from a LOP network to a confined output path (the /out `usd` ROP; executes the write). | `output` (+3 optional) |
| `export_fbx` | Write an FBX (.fbx) from the OBJ that contains `input` to a confined output path (the /out `filmboxfbx` ROP; executes the write) — the standard rigged/animated interchange for Maya/Max/UE/Unity. | `input`, `output` (+2 optional) |
| `export_gltf` | Write a glTF/GLB from the `input` SOP to a confined output path (the /out `gltf` ROP; executes the write) — the web/real-time interchange (three.js, model-viewer, UE/Unity, AR quicklook). exporttype auto (from extension — default) \| gltf (.gltf + external buffers) \| glb (single-file binary). frames=[start,end] writes an ANIMATED glTF; omit for a static frame. | `input`, `output` (+3 optional) |
| `export_cache` | Write a versioned geometry cache — a per-frame .bgeo.sc sequence — over a frame range (the /out `geometry` ROP; executes the write). | `input`, `output` (+2 optional) |
| `flipbook` | Render a fast OpenGL preview sequence (the /out `opengl` ROP; executes the write) — a viewport-quality flipbook for reviewing motion, NOT a final render (use setup_karma/karma_render_settings for that). | `output` (+5 optional) |
| `export_package` | WIRE-ONLY staged USD export / handoff / package write: build + fully configure a `usd` ROP (Driver) that writes an assembled LOP stage out to a confined .usd/.usda/.usdc/.usdz file, but do NOT execute it -- like setup_karma / bake_texture, a whole-stage flatten can be a heavy write, so the caller/human fires it (returns rendered=false). | `loppath`, `output` (+3 optional) |
| `define_hda` | Package an existing SOP subnet into a reusable, path-confined Houdini Digital Asset — the 'make this network a reusable tool' op. | `node`, `output`, `type_name` (+6 optional) |
| `usd_export_sop` | Write the `input` SOP geometry to a USD file (the SOP-context `usdexport` — the write bridge from native SOPs up to a USD stage; executes the write). output is realpath WRITE-confined to the working directory; extension picks the format (.usd/.usda/.usdc/.usdz). | `input`, `output` (+8 optional) |
| `usd_stitch` | WIRE-ONLY: build a USD Stitch ROP (/out usdstitch) that merges several input USD layers into an output layer — configured but NEVER executed (you fire the write). | `input_files`, `output` (+1 optional) |
| `usd_stitch_clips` | WIRE-ONLY: build a USD Stitch Clips ROP (/out usdstitchclips) that assembles per-frame USD clips into a value-clip topology + template — configured but NEVER executed. | `input_files`, `output_template` (+5 optional) |
| `usd_zip` | WIRE-ONLY: build a USD Zip ROP (/out usdzip) that packages input USD layers into a .usdz archive — configured but NEVER executed. | `input_files`, `output` (+2 optional) |

### Render & output (WIRE-ONLY)

| Tool | What it does | Key params |
|---|---|---|
| `render_mantra` | Mantra CPU image render ROP (ifd, out/) — WIRE-ONLY: builds + wires the Mantra render in /out; YOU fire it. | 11 optional |
| `render_karma_rop` | Karma image render ROP in Driver context (karma, out/) — WIRE-ONLY: builds + wires the Karma render in /out; YOU fire it. | 11 optional |
| `render_usd` | USD/Husk render ROP in Driver context (usdrender, out/) — WIRE-ONLY: builds + wires the Husk render in /out; YOU fire it. | 10 optional |
| `render_comp` | Composite/COP-network image write ROP (comp, out/) — WIRE-ONLY: builds + wires the composite write in /out; YOU fire it. | 8 optional |
| `render_image` | COP image render ROP (image, out/) — WIRE-ONLY: builds + wires the COP image write in /out; YOU fire it. | 8 optional |
| `export_ifd_archive` | Mantra IFD scene-archive export ROP (ifdarchive, out/) — WIRE-ONLY: builds + wires the archive export in /out; YOU fire it. | 7 optional |
| `render_settings_usd` | USD RenderSettings prim (Solaris rendersettings LOP) — WIRE-ONLY: builds + wires the top-level render config (resolution, samples, camera) a downstream renderer reads; you fire the render. | 7 optional |
| `render_product` | USD RenderProduct prim (Solaris renderproduct LOP) — WIRE-ONLY: names the OUTPUT IMAGE (path, type, framing) a renderer will write; you fire the render. | 7 optional |
| `render_var` | USD RenderVar / AOV definition (Solaris rendervar[::2.0] LOP) — WIRE-ONLY: declares one AOV / render output variable (source + data type) for a renderer to produce. | 6 optional |
| `render_vars_additional` | Additional RenderVars (Solaris additionalrendervars LOP) — WIRE-ONLY: appends one extra AOV / RenderVar row to the stage's render output set. | 7 optional |
| `karma_render_properties` | Karma Render Properties (Solaris karmarenderproperties LOP) — WIRE-ONLY: builds + wires a combined Karma render-settings + product config on the stage; you fire the render. | 9 optional |
| `karma_render_products` | Karma Render Products bundle (Solaris karmarenderproducts[::2.0] LOP) — WIRE-ONLY: builds + wires a set of Karma output products (beauty + AOVs) on the stage; you fire the render. | 7 optional |
| `karma_render_vars` | Karma Standard RenderVars (Solaris karmastandardrendervars[::2.0] LOP) — WIRE-ONLY: builds + wires the standard Karma AOV set (beauty, diffuse/glossy/volume splits, etc.) on the stage; you fire the render. | 4 optional |
| `karma_cryptomatte` | Karma Cryptomatte AOV setup (Solaris karmacryptomatte LOP) — WIRE-ONLY: builds + wires cryptomatte ID matte outputs on the stage; you fire the render. | 5 optional |
| `husk_image_metadata` | Husk Image Metadata (Solaris huskimagemetadata LOP) — WIRE-ONLY: builds + wires metadata (which prims' attributes to embed) into the rendered output image; you fire the render. | 3 optional |
| `rop_geometryraw` | ROP Geometry Output — RAW (`rop_geometryraw`, SOP-context) — WIRE-ONLY: builds + wires a raw-geometry export ROP inside the SOP network after `input`; you fire the write. | `input` (+4 optional) |
| `dopio` | DOP I/O (`dopio`, SOP-context) — WIRE-ONLY: builds a DOP field/geometry disk-cache node (no SOP input — it references a DOP network by path and writes a file); you fire the cache. | 6 optional |
| `heightfield_output` | Heightfield Output (`heightfield_output`, SOP-context) — WIRE-ONLY: builds + wires a heightfield/terrain heightmap export ROP after `input`; you fire the write. | `input` (+8 optional) |
| `export_channel` | CHOP channel/motion export ROP (channel, out/Driver) — WIRE-ONLY: builds + wires a CHOP channel/motion exporter; you fire it. choppath is a scene CHOP path (data); output -> chopoutput (confined). | 7 optional |
| `export_mdd` | MDD point-cache export ROP (mdd, out/Driver) — WIRE-ONLY: builds + wires an MDD point-cache exporter; you fire it. soppath is a scene SOP path (data); output -> file (confined). | 8 optional |
| `render_dsm_merge` | Deep-Shadow-Map merge ROP (dsmmerge, out/Driver) — WIRE-ONLY: builds + wires a DSM merge; you fire it. output -> dsm_output (write-confined); dsm_source1/2 are read-confined inputs. | 8 optional |
| `export_brickmap` | Brick-map generator ROP (brickmap, out/Driver) — WIRE-ONLY: builds + wires a point-cloud/i3d -> brick-map generator; you fire it. sop is a scene SOP path (data); output/geofile/ptcfile/i3dfile are confined. | 9 optional |
| `bake_animation_rop` | Bake Animation ROP (bake_animation, out/Driver) — WIRE-ONLY: builds + wires an object-animation bake to keyframes/CHOP channels; you fire it. source and write_to_chop_channel are scene data (verbatim). | 7 optional |
| `export_geometry_raw` | Raw geometry stream ROP (geometryraw, out/Driver) — WIRE-ONLY: builds + wires a raw geometry stream dump; you fire it. soppath is a scene SOP path (data); output -> sopoutput (confined). | 7 optional |
| `export_ml_example_raw` | ML Example Raw ROP (ml_exampleraw, out/Driver) — WIRE-ONLY: builds + wires a raw ML-training-example exporter; you fire it. soppath is a scene SOP path (data); output -> sopoutput (confined). | 9 optional |
| `export_ml_example_output` | ML Example Output ROP (ml_exampleoutput, SOP-context) — WIRE-ONLY: builds + wires an ML example-dataset writer after a SOP (input 0); you fire it. output -> sopoutput (confined). | `input` (+4 optional) |
| `export_ml_example_raw_sop` | ROP ML Example Raw (rop_ml_exampleraw, SOP-context) — WIRE-ONLY: builds + wires the SOP-level raw ML-example exporter after a SOP (input 0); you fire it. soppath is scene data; output -> sopoutput (confined). | `input` (+9 optional) |
| `render_ml_cv_synthetics` | Labs ML-CV Synthetics Karma ROP v1.0 (labs::ml_cv_synthetics_karma_rop::1.0, lop/Solaris) — WIRE-ONLY: builds + wires a Karma synthetic-data renderer (beauty + large AOV set) in /stage; you fire the render. camera/primpath/primpattern are USD scene-graph data; image outputs confined; res/samples/frames clamped; render buttons never pressed. | 16 optional |
| `render_ml_cv_synthetics_v11` | Labs ML-CV Synthetics Karma ROP v1.1 (labs::ml_cv_synthetics_karma_rop::1.1, lop/Solaris) — WIRE-ONLY: same posture as render_ml_cv_synthetics for the ::1.1 asset (2 inputs; importsecondaryinputvars). camera/primpath/primpattern are USD data; image outputs confined; res/samples/frames clamped; render buttons never pressed. | 16 optional |
| `bake_karma_texture` | Karma Texture Baker (karmatexturebaker, lop/Solaris) — WIRE-ONLY: builds + wires the Karma UV/texture bake in /stage and configures it; you fire the bake. | 26 optional |
| `bake_impostor_texture` | Labs Impostor Texture (labs::impostor_texture, out/Driver) — WIRE-ONLY: builds + wires the octahedral impostor atlas baker in /out; you fire the bake. source_geo/camera_rig are scene node paths; output_sequence/anim_output_sequence/sopoutput confined; sprite res + ray-samples clamped; execute/renderdialog never pressed. | 24 optional |
| `bake_motion_vectors` | Labs Motion Vectors (labs::motion_vectors, out/Driver) — WIRE-ONLY: builds + wires the motion-vector atlas baker in /out; you fire the bake. export_node/camera are scene node paths; vm_picture confined; atlas res + frame range clamped; execute/render_map/render_sequence/renderdialog never pressed. | 10 optional |
| `bake_flipbook_textures` | Labs Flipbook Textures (labs::flipbook_textures::1.0, out/Driver) — WIRE-ONLY: builds + wires the flipbook texture-sheet baker in /out; you fire the bake. | 23 optional |
| `bake_haircard_texture` | Hair Card Texture (haircardtex, out/Driver) — WIRE-ONLY: builds + wires the hair-card texture baker in /out; you fire the bake. hairobjects is an object bundle, camera a scene node path; vm_picture confined; per-map name tokens sanitized; res/samples clamped; execute/renderdialog never pressed. | 23 optional |
| `export_geo_to_i3d` | Geometry to i3d (geo2i3d, out/Driver) — WIRE-ONLY: builds + wires the geometry->i3d volume-texture export in /out; you fire it. filename (out) and image (input, read) confined; res/frame range clamped; execute/renderdialog never pressed. | 19 optional |
| `export_image_to_i3d` | 3D Texture Generator (image3d, out/Driver) — WIRE-ONLY: builds + wires the i3d 3D-texture generator in /out; you fire it. soppath/shoppath are scene node paths; image output confined; compress token sanitized; res/samples/frame range clamped; execute/renderpreview/renderdialog never pressed. | 27 optional |

<!-- END TOOLS (generated) -->

---

## References

Four discoverability surfaces back the tool catalog. `capabilities` is the start-here index — it
prints pointers to all of the others (including the live help-server URL), so when in doubt call it first.

- **Tool catalog** — the enumerated list of every typed operation (`reference/catalog.json`, the authoritative count),
  surfaced as the tables above; per-parameter detail comes from the `node_reference` MCP tool and
  `reference/NODE_REFERENCE.md`. This *is* the security boundary: if it isn't in the catalog, the server
  can't do it.
- **Node reference** — the `node_reference` MCP tool answers "what params does node X take?" from
  live-probed ground truth; the human-readable archive is `reference/NODE_REFERENCE.md` (SOP / OBJ /
  LOP / Driver / COP), annotated with which tool exposes each node.
- **VEX reference** — the `vex_reference` MCP tool looks up validated safe-VEX functions; the curated
  guide is `reference/VEX_REFERENCE.md`.
- **Offline Houdini help server** — SideFX's full node/VEX/HOM documentation, served locally and
  launched alongside the bridge. It has no MCP tool; the `capabilities` output prints its URL.

---

## Real-world geospatial data

This is the differentiator. `acquire_terrain` is the one network operation — give it a lat/lon (+ radius)
or an explicit bounding box, and it auto-selects a source, fetches, reprojects, and preps Houdini-ready
tiles into your working directory. Coverage is global (see [`DOWNLOADER_SCOPE.md`](DOWNLOADER_SCOPE.md)
for the full matrix):

- **US** — USGS 3DEP (1 m lidar / 10 m / 30 m) + several state lidar portals.
- **Global 30 m** — Copernicus GLO-30, SRTM, or JAXA ALOS AW3D30 (all anonymous, no key), so any point
  on Earth returns terrain.
- **National hi-res** — Netherlands 0.5 m, UK 1 m, France 1 m / 0.5 m, Spain 5 m, Australia 5 m
  (auto-selected when a "large"/hi-res request falls wholly inside a covered country).
- **Keyed opt-in** — OpenTopography's global API, using the user's own free key (`HMCP_OPENTOPO_KEY`),
  never bundled.

Two placement modes:

- **flat** — local metric heightfields for a single site, imported at true elevation with
  `import_heightfield`.
- **globe** — ECEF tiles pinned onto a WGS84 globe (`build_globe` + `import_ecef_tile`) so a scan sits in
  a correct Earth frame and adjacent tiles register by construction.

Because one project origin is held across calls, successive tiles share a frame and align automatically.
The fetch is confined to a small set of trusted DEM hosts; no arbitrary URL crosses the boundary.

### Coordinate convention

```
1 Houdini unit = 1 meter
Working CRS    = a local UTM zone chosen per project (metric, minimal distortion)
X = east-west,  Y = elevation (up),  Z = north-south, NEGATED (north = -Z)
```

The **Z negation** is the classic mirror trap — it cost a full debugging session. One origin is held per
project so successive tiles share a frame and align automatically. A prepared `<tile>.npy` needs its
`<tile>.npy.json` sidecar (`cols`, `rows`, `res_m`, `houdini_center_x/z`, `nodata`) beside it.

---

## Gotchas — Houdini 21.0.671

Real-world LIDAR/DEM in Houdini breaks in non-obvious ways. These are confirmed on 21.0.671 and are the
hard-won original value of this project:

- **GeoTIFF is unreadable by Houdini's COP2 / `heightfield_file`.** All GeoTIFF I/O happens in system
  Python (rasterio) → `.npy`; only arrays cross into Houdini.
- **`convertheightfield` produces 0 prims from old-style `createVolume` volumes** — but converts cleanly
  from a proper `heightfield` SOP volume (verified: 249k polys from a default heightfield).
- **`heightfield_mosaic` / `heightfield_wrangle` don't exist in H21** — use `heightfield_patch` /
  `volumewrangle` instead.
- **The "12 GB freeze" is viewport GL tessellation, not RAM.** A heavy heightfield tessellates hundreds of
  millions of voxels on the GPU. Fix: build display-OFF, stream packed tiles with a box proxy, and lower
  volume quality (`viewport_optimize`). Data RAM is a non-issue.
- **Never flipbook or OpenGL-render a heavy heightfield scene** — it can hang Houdini. Use `capture_ui`
  (an OS-level screen grab) instead.
- **A `heightfield` SOP volume needs a primitive attribute `name='height'`**, and LIDAR arrays are
  north-row-first, so rows are flipped before `setAllVoxels`.
- **The GL viewport does not show Principled Shader bump** (Karma-render only); real relief needs geometry
  displacement.

---

## Optional: AMD GPU rendering (ProRender)

Houdini's Karma XPU GPU path is NVIDIA/OptiX-only. If you have an **AMD Radeon** card (RDNA2 / gfx1030+)
and want GPU rendering, this repo includes a **from-source build of AMD Radeon ProRender's `hdRpr`
delegate ported to Houdini 21 / USD 25** — AMD ships no prebuilt H21 plugin. It installs as a native Hydra
renderer ("RPR") in Solaris and is entirely optional and independent of the core MCP.

**Status: working** (rebuilt with the MSVC **v143** toolset; "RPR" is a selectable Hydra renderer and the
RPR material VOPs / LOP render-settings / Material Library all load). One known convenience gap: the RPR
menu's **Render Devices** dialog still needs a USD-25 Python-binding port — not required to render. See
**[AMDProRender/README.md](AMDProRender/README.md)** for the prebuilt release, build-from-source steps, and
the port patch.

---

## Configuration

Most configuration happens in the GUI and is written to a shared config file both halves read live. The
only environment variable the MCP client needs is the headless flag.

| Setting | Where | Description |
|---|---|---|
| `HMCP_GW_HEADLESS` | env (client config) | `1` = run the binary as the headless stdio MCP gateway; unset = open the GUI window. |
| `HMCP_MIN_ACTION_INTERVAL_MS` | env (client config) | Action throttle (default `0` = off). When set, the gateway enforces this minimum wall-clock gap, in milliseconds, between successive **destructive** tool calls (`delete_node`, `save_scene`, `delete_keyframes`) — it *paces* them with a short sleep, never rejects. A safety governor so a runaway loop or prompt-injection can't rapid-fire scene-destroying calls. Non-destructive tools (builds, reads) are never delayed. |
| Working directory | GUI → Working dir | Your project root. Every file read/write is `realpath`-confined under it. Change + **Apply** takes effect live, no restart. |
| Executor port | GUI → Settings | Loopback port shared by the gateway and the in-Houdini executor. |
| Session token | GUI → Settings | The shared secret between the gateway and executor. Generated for you. |
| Auto-arm Houdini | GUI → Settings | Arms the executor automatically when Houdini's GUI starts. |

---

## Security

The security model is **the boundary itself**, not a sandbox:

- **Data-only by construction.** No arbitrary code, no generic node driver, no raw VEX or Python ever
  reaches Houdini. The catalog is the attack surface, and the catalog is data-shaped operations. A
  regression test asserts the RCE primitives (`exec` / `node_op` / `wrangle`) can never appear in the
  catalog.
- **`realpath`-confined working directory.** Every file operation resolves and re-checks against one root,
  with symlink/junction escapes closed. Reads must exist under the root; writes may create a new leaf but
  never escape.
- **Fail-closed arming.** The executor refuses to arm unless a firewall rule blocks inbound connections to
  its loopback port (see Step 4).
- **Renders are wire-only.** `setup_karma` and `bake_texture` build graphs but never execute — you fire
  them in Houdini.
- **`batch` grants no privilege.** The `batch` meta-tool runs up to 64 ops in one call to cut latency, but
  each op is dispatched through the *exact same* path as a direct call — schema-validated, numerics
  clamped, filesystem paths `realpath`-confined, and audited in order. A batch can only invoke real
  catalog tools (no arbitrary code, no non-catalog names) and cannot nest (an op named `batch` is
  rejected). It is a latency envelope, not a way around the boundary.
- **Optional action throttle.** `HMCP_MIN_ACTION_INTERVAL_MS` (default off) paces destructive tools
  (`delete_node`, `save_scene`, `delete_keyframes`) with a short sleep so a runaway/injection can't
  rapid-fire scene destruction. It slows, never blocks; ordinary tools are unaffected (see Configuration).
- **Houdini's embedded Python is unsandboxed**, so the guarantee is *what the AI can ask for*, validated at
  the gateway — not process isolation. Treat the AI as semi-trusted input.
- **Intended posture: loopback, single trusted user, trusted machine.** This is a local tool. The
  transport is meant to stay on the local host.

A code-level audit confirms the data-only boundary holds as built. For the full threat model, the current
hardening status, and the known residual items, see [SECURITY.md](SECURITY.md) — read it before running
this anywhere other than a single trusted machine.

---

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for detailed solutions and [docs/GUIDE.md](docs/GUIDE.md)
for day-to-day operation.

Quick checklist:

- The GUI status pill reads **Armed** with your Houdini version.
- Houdini was launched *after* the package was installed and auto-arm was enabled.
- The firewall harden step (Step 4) was run — the executor is fail-closed without it.
- The MCP client config points at the built `houdini-bridge-mcp.exe` with `HMCP_GW_HEADLESS` set to `1`.
- Paths in the client config use **double backslashes** (`C:\\...`).
- The client was fully restarted after editing its config.
- File paths you pass to tools live **inside** the configured working directory.

---

## License

Dual-licensed. **Free for noncommercial use** — personal, educational, research, and evaluation —
under the [PolyForm Noncommercial License 1.0.0](LICENSE). **Commercial, business, and production use
requires a paid license**; see [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md) to obtain one.

The tool bundles **no** elevation data — it downloads on your behalf at runtime. The global sources are
public-domain / open (USGS 3DEP, Copernicus, SRTM, JAXA AW3D30); the national hi-res sources require
attribution under their own open licenses (Netherlands AHN & Spain IGN — CC-BY 4.0; UK EA — OGL; France
IGN — Etalab OL 2.0; Australia GA — CC-BY 4.0). See [DOWNLOADER_SCOPE.md](DOWNLOADER_SCOPE.md) for the
per-source licence/attribution. Third-party dependency notices are generated into
`THIRD-PARTY-LICENSES.md` for releases (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Support

If this saved you time and you're using it noncommercially, a tip is always appreciated —
[ko-fi.com/eviscerations](https://ko-fi.com/eviscerations). It's voluntary and grants no license;
commercial use is covered by [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

## Development & tests

Tests run as three tiers across two environments (Tiers 1–2 in CI, Tier 3 local), split by what a
machine without a Houdini license can honestly prove — see [docs/TESTING.md](docs/TESTING.md) for the
full method:

- **Cloud CI (every push, no Houdini license):** the Rust `cargo test` gates the gateway's security
  invariants — the catalog never exposes an arbitrary-code tool, tool names are unique, and
  `confine_path` rejects `../`, symlink, and junction escapes. The Python job runs the safe-VEX
  validator's red-team corpus, the `confined_path` traversal + symlink-escape boundary, a
  **catalog↔executor parity check across every tool** (each tool maps to exactly one data-only endpoint,
  none RCE-shaped), and a **construct-smoke that calls every tool's handler against a mock Houdini** to
  catch code regressions. These verify the tool surface is structurally sound and every handler's code
  runs — they do not cook geometry.
- **Local (before a push, licensed `hython`):** the behavioural suite in `tests/executor/` cooks real
  geometry and locks in regression tests. Run `hython tests/executor/run_tests.py`.

The full method is documented for contributors in [docs/TESTING.md](docs/TESTING.md).

## Contributing

Pull requests welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). If you test on hardware or a Houdini
configuration not listed here, please open an issue with your results.
</content>
</invoke>

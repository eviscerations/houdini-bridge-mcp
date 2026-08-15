# Optimization settings — binary settings panel

Toggles the desktop binary exposes beyond env config, so a user can tame heavy real-world-data
scenes (the "12 GB freeze" is viewport GL tessellation, NOT RAM — it's a display-budget problem).
Grouped by TYPE: **live** = safe to toggle live (viewport display only), **default** = applied at
build/import time, **limit** = a cache ceiling, **cache-write** = alters stored data on cache write.

## A. Viewport display quality  (live — no data change; applied via the `viewport_optimize` op)
| Setting | Values | Why |
|---|---|---|
| Volume quality | Normal / **Low** / Very Low | the big heightfield lever — voxel tessellation cost |
| Volume B-splines | On / **Off** | smoother but heavier volume display |
| Scene polygon limit | e.g. **10 M** | decimate viewport display past a poly budget |
| Level of detail | 1.0 / **0.5** | halve viewport tessellation density |
| Scene antialias | **1 (off)** / 2 / 4 / 8 | GL AA cost |
| Distance-based packed culling | **On** / off | drop far packed prims from display |
| Lighting mode | **Headlight** / scene lights | headlight is far cheaper in the viewport |

## B. Build / import defaults  (default — set when geometry is created)
| Setting | Default | Why |
|---|---|---|
| Heavy-import display | **OFF** | display+frame of a heavy heightfield tessellates 100s of M voxels → the ~12 GB GPU hang. Build dark, reveal deliberately. |
| Update mode | Manual / **Auto** | Manual defers cooks on heavy graphs (force-cook on read); optional |
| Packed-tile viewport LOD | **box** proxy | the box proxy is what actually collapses VRAM for streamed tiles (not packing alone) |

## C. Cache / memory limits  (limit)
| Setting | Why |
|---|---|
| GL vertex-buffer cache limit | the ~9 GB VBO cap is the real 12 GB-freeze ceiling — expose it so users can raise/lower |
| Texture cache limit | GL texture memory budget |

## D. Cache-write precision  (cache-write — for `export_cache` / File Cache)
- **Pre-cache attribute bit-depth**: cast non-critical attributes to **16-bit float** before a
  `.bgeo` write to ~halve cache size (demo: 430 → 168 MB/frame). Good candidates: velocity `v`,
  normal `N`, `uv` (on the vertex class). Keep `P` at 32-bit if it's dynamic.
- **GUARD (data-integrity, not a preference):** never cast `id` / large-integer attributes to
  16-bit — millions of unique ids overflow 16-bit int range, wrap negative, and the ids are
  **destroyed**. The panel must force-exclude id/integer attributes from down-casting.
- **H21 note:** modern Houdini's File Cache SOP has built-in precision/cast options, so prefer the
  File Cache SOP's own compression parameters over a manual Attribute Cast chain.

## Notes
- GPU: this tool adds **no GPU compute**. GPU only appears when the *user fires a render* on their
  own backend — Karma (CPU/XPU) or, on AMD, **Radeon ProRender** (Vulkan). The tool wires the render
  graph either way; it never runs GPU work itself.
- Live viewport levers (group A) call the same `viewport_optimize` executor op; groups B/C/D are
  applied at the relevant build/cache step.

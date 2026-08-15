# Third-party licenses — AMD Radeon™ ProRender prebuilt package

> **Scope.** This document accompanies the **optional prebuilt ProRender package** (a downloadable
> release artifact for `houdini-bridge-mcp`). It attributes the third-party binaries bundled in that
> package. It does **not** apply to, cover, or relicense the `houdini-bridge-mcp` project itself, which
> is licensed separately under its repository-root `LICENSE`. All components below are redistributed
> under permissive open-source licenses (Apache-2.0 / MIT / NCSA / BSD-3-Clause); none carry a
> proprietary EULA or a no-redistribution / evaluation-only restriction.

Windows x64 · Houdini 21.0.x (MSVC v143 ABI) · AMD RDNA2+ (gfx1030+).

## What is bundled, and under what license

### Built from source (Apache-2.0) — this project's own binaries
Compiled from AMD's open-source `RadeonProRenderUSD` (© Advanced Micro Devices, Inc., Apache-2.0),
with this project's H21/USD-25 port patches applied (see `../patches/`, `../NOTICE.md`):

| Binary | License |
|---|---|
| `hdRpr.dll` (Hydra render delegate) | Apache-2.0 |
| `rprUsd.dll`, `_rprUsd.pyd` (USD schema + Python bindings) | Apache-2.0 |
| `RPR_for_Houdini.dll` (Houdini HDK plugin: LOP/VOP/ROP + RPR menu) | Apache-2.0 |

> Bundles *JSON for Modern C++* (nlohmann/json), **MIT** — notice reproduced in the Apache-2.0 text file.

### AMD Radeon ProRender cores — from `RadeonProRenderSDK` (Apache-2.0, © AMD)

| Binary | License |
|---|---|
| `RadeonProRender64.dll` | Apache-2.0 |
| `Northstar64.dll` (HIP / final) | Apache-2.0 |
| `Tahoe64.dll` | Apache-2.0 |
| `Hybrid.dll`, `HybridPro.dll` (Vulkan) | Apache-2.0 |
| `RprLoadStore64.dll` | Apache-2.0 |
| `plugin/usd/rprUsd/resources/ns_kernels/*.hipbin`, `*.cudabin` (precompiled Northstar kernels) | Apache-2.0 (from `RadeonProRenderSDKKernels`, a submodule of the Apache-2.0 SDK; no standalone license — governed by the parent SDK license) |

### Radeon Image Filters & friends — from `RadeonImageFilter`

| Binary | License | Copyright |
|---|---|---|
| `RadeonImageFilters.dll` (RIF) | Apache-2.0 | © 2020 AMD |
| `plugin/usd/hdRpr/resources/rif_models/*` (`.pb`, `.onnx` denoise/upscale models) | Apache-2.0 (RIF) | © AMD |
| `MIOpen.dll` | **MIT** | © 2017 AMD Compute Libraries |
| `dxcompiler.dll`, `dxil.dll` (DirectX Shader Compiler) | **University of Illinois / NCSA Open Source License** | © 2003-2015 Univ. of Illinois; portions © Microsoft |
| `RadeonML.dll`, `RadeonML_MIOpen.dll`, `RadeonML_DirectML.dll` | **Apache-2.0** | © 2020 AMD |
| `OpenImageDenoise.dll` (if present) | Apache-2.0 | © Intel Corporation |

> `RadeonML` additionally bundles: **MIOpen** (MIT), **Protobuf** (BSD-3-Clause, © 2008 Google Inc.),
> and *filesystem* / *CLI11* / *Half* (MIT). These notices are reproduced in the RadeonML license text.

## License texts that MUST travel in the release (`licenses/`)

Copy these verbatim from the build tree into the release's `licenses/` folder — together they contain
the full text of every license referenced above (Apache-2.0, MIT, NCSA, BSD-3-Clause):

| Bundle file | Copy from | Covers |
|---|---|---|
| `licenses/LICENSE-RadeonProRenderUSD.txt` | `RadeonProRenderUSD/LICENSE.md` | Apache-2.0 + nlohmann/json (MIT) — this project's binaries |
| `licenses/LICENSE-RadeonProRenderSDK.txt` | `deps/RPR/license.txt` | Apache-2.0 — RPR cores + kernels |
| `licenses/LICENSE-RadeonImageFilter.md` | `deps/RIF/License.md` | Apache-2.0 (RIF) + MIT (MIOpen) + NCSA (DXC) + Apache (OIDN) |
| `licenses/LICENSE-RadeonML.md` | RadeonML repo `LICENSE.md` (`github.com/GPUOpen-LibrariesAndSDKs/RadeonML`) — not in the RIF submodule; **already fetched into `licenses/` here** | Apache-2.0 (RadeonML) + MIT (MIOpen) + BSD-3 (Protobuf) + MIT (CLI11/Half/filesystem) |

## Not bundled (user-provided)

- **Vulkan runtime** (`vulkan-1.dll` loader / ICD): provided by the user's AMD GPU **driver**, not
  redistributed here. HybridPro uses the driver's Vulkan RT. Requires a current AMD Adrenalin driver.
- **DirectML** (`RadeonML_DirectML.dll` links it): DirectML is a Windows OS/system component, not bundled.
- **Houdini / HDK / USD**: provided by the user's SideFX Houdini 21 install; nothing from Houdini is
  redistributed. `hdRpr` / `RPR_for_Houdini` link against the user's own Houdini at runtime.

## Trademarks

"AMD", "Radeon", and "Radeon ProRender" are trademarks of Advanced Micro Devices, Inc.; "DirectX" and
"DirectML" are trademarks of Microsoft Corporation. Used only to identify the integrated components.
This package is an independent integration, not affiliated with or endorsed by AMD or Microsoft.

## Warranty

All bundled components are provided **"AS IS", without warranty of any kind**, per their respective
licenses.

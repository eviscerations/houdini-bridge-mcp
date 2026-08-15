# AMD Radeon ProRender for Houdini 21 (optional GPU rendering)

This is an **optional** add-on for `houdini-bridge-mcp`. It gives you a **GPU renderer that runs on AMD
Radeon cards** inside Houdini 21, so the MCP's wire-only `setup_prorender` tool can build a
USD render graph that renders on your Radeon.

**Why this exists.** Houdini's own Karma XPU GPU path is NVIDIA/OptiX-only — on AMD it falls back to
CPU. AMD's Radeon ProRender **is** the GPU path for Radeon, but AMD ships **no prebuilt plugin for
Houdini 21** (their latest, v3.0.4, targets Houdini 20.5 / USD 24.x). Houdini 21 ships **USD 25.05 +
Hydra 2**. This folder is the **from-source port of AMD's open-source `RadeonProRenderUSD` (hdRpr) to
Houdini 21** — the render delegate builds and installs natively, no second Houdini install.

> If you don't need AMD GPU rendering, ignore this folder entirely. The core MCP does not depend on it.

---

## Two ways to get it

1. **Prebuilt release (recommended).** Download the hash-pinned `hdRpr-h21` package from the project's
   Releases page, verify its SHA256, and skip straight to [Install](#install). *(Windows x64, Houdini
   21.0.x.)*
2. **Build it yourself** — [Build from source](#build-from-source) below. ~1 hour, mostly the SDK
   download.

---

## Requirements (build-from-source)

- **Houdini 21.0.x**, Windows x64. Set the `HFS` environment variable to its install dir
  (the folder containing `toolkit/`, `bin/`, `custom/`).
- **MSVC v143 (Visual Studio 2022) — REQUIRED, not optional.** Houdini 21 is a VS 2022 / **v143** build, and
  a Houdini plugin must be compiled with Houdini's *exact* toolset. A newer toolset (e.g. VS 2026 / 14.50)
  **will compile and link**, and the render delegate alone may even load — **but the HDK plugin
  (`RPR_for_Houdini`) then segfaults Houdini on startup.** It is an ABI mismatch: the plugin's
  `pxr_boost::python` / HDK objects cross the DLL boundary into Houdini's v143-built runtime and corrupt
  memory. Install the **v143** build-tools component (VS Installer → Individual Components → "MSVC v143 –
  VS 2022 C++ x64/x86 build tools") and configure with **`-T v143`**. Do **not** build with a newer toolset
  — it looks like it worked right up until Houdini crashes at launch.
- **CMake ≥ 3.15** (the bundled VS CMake is fine).
- **git** (the source uses submodules).
- You do **not** need the ROCm/HIP SDK or the Vulkan SDK to build — the RPR SDK ships precompiled
  device kernels. Your GPU must be **gfx1030 or newer** (RDNA2+) for the HIP render path.

---

## Build from source

```bash
# 1. Clone AMD's RadeonProRenderUSD at the H20.5 baseline (closest to H21), with submodules
git clone --recursive https://github.com/GPUOpen-LibrariesAndSDKs/RadeonProRenderUSD.git
cd RadeonProRenderUSD
git checkout tags/v3.0.4 -b build-h21
git submodule update --init --recursive

# 2. Apply the H21 / USD-25 port patches (from this folder)
git apply <PATH_TO>/AMDProRender/patches/hdRpr-h21-usd25.patch
git apply <PATH_TO>/AMDProRender/patches/rprUsd_h21_pxr_boost_python_bindings.patch

# 3. Configure against Houdini's bundled USD (HFS must be set).
#    -T v143 forces Houdini 21's toolset (REQUIRED — see Requirements; a newer toolset crashes Houdini).
#    PYTHON_SUPPORT=ON builds the rprUsd Python bindings, required for the in-Houdini RPR menu
#    (Render Devices / Cache / Material Library). Set it OFF if you only need headless husk rendering.
cmake -B build -S . -T v143 -DPXR_ENABLE_PYTHON_SUPPORT=ON -DPXR_BUILD_TESTS=OFF ^
      -DCMAKE_INSTALL_PREFIX=package -DCMAKE_POLICY_VERSION_MINIMUM=3.5

# 4. Build + install the delegate into ./package
cmake --build build --config Release --target install --parallel
```

Run this from a **VS Developer Command Prompt** (puts `cl.exe` and CMake on `PATH`) with `HFS` set to
your Houdini 21 install. The result is a self-contained `package/` folder containing `hdRpr.dll`, the
RPR cores (Northstar = HIP/Final, HybridPro = Vulkan), the image filters, and the USD `plugInfo`.

### What the patches do

**`hdRpr-h21-usd25.patch`** — the delegate + HDK-plugin port:

| # | File | Fix |
|---|---|---|
| 1 | `cmake/macros/PlatformIntrospection.cmake` | Accept MSVC `1950` (VS 2026) — the stale allowlist stopped at VS 2022. |
| 2 | `cmake/modules/FindHoudiniUSD.cmake` | Link `libpxr_python` — USD 25 renamed `boost::python` → `pxr_boost::python`, exported there (not in `hboost_python`). |
| 3 | `pxr/imaging/plugin/rprHoudini/CMakeLists.txt` | Drop the `activateHoudiniPlugin` helper (needs the ATL component; the package installs via the JSON instead). |
| 4 | `pxr/imaging/plugin/hdRpr/rprApi.cpp` | `GfVec3f(...)` wrap — USD 25 `GfMatrix4d::Transform()` returns `GfVec3d`, no implicit narrow. |
| 5 | `pxr/imaging/plugin/rprHoudini/VOP_RPRMaterial.{h,cpp}` | `inputLabel`/`outputLabel` now take `OP_InputIdx`/`OP_OutputIdx` (H21 HDK; was `unsigned`). |

**`rprUsd_h21_pxr_boost_python_bindings.patch`** — the RPR-menu Python bindings (needs `PXR_ENABLE_PYTHON_SUPPORT=ON`):

| # | File | Fix |
|---|---|---|
| 6 | `pxr/imaging/rprUsd/wrapConfig.cpp`, `wrapContextHelpers.cpp` | Port the two hand-written binding TUs from `hboost::python` to `pxr_boost::python` so the whole `_rprUsd` module uses **one** boost.python runtime (USD 25's `TF_WRAP_MODULE` is pxr_boost; patch #2 already puts those symbols on the link line). Without this, the `_rprUsd` module mixes two boost.python registries and the RPR menu (Render Devices / Cache / Material Library) throws an "unidentifiable C++ exception" at import. The pxr_boost `using`-directive must follow `PXR_NAMESPACE_USING_DIRECTIVE`. |

> That's the whole port. Both halves of the plugin build — the **`hdRpr` delegate** (the render
> engine) and **`RPR_for_Houdini`** (the render-settings LOP, material VOPs, ROP export, and the RPR
> menu) — and with patch #6 + `PYTHON_SUPPORT=ON` the RPR menu's Python tools load and run. The
> USD-25 + H21-HDK delegate churn was two one-line signature fixes (#4, #5); the menu-binding fix (#6)
> is a namespace-consistency change across two files.

---

## Install

1. Copy the built `package/` folder somewhere permanent (e.g. next to your Houdini prefs, or keep the
   release download).
2. Copy `houdini-package/UsdRenderers.json` (from this folder) into `package/houdini/` — it adds "RPR"
   to Houdini's renderer menu. *(The prebuilt release already includes it.)*
3. Copy `houdini-package/hdRpr.json` into `<HOUDINI_USER_PREF_DIR>/packages/` (e.g.
   `Documents/houdini21.0/packages/`) and set `HDRPR_DIR` in it to the `package/` folder.
4. Restart Houdini.

## Render

In a `/stage` (Solaris) context, set the Scene Viewer's Hydra renderer to **RPR**, point a camera at a
lit scene, and render. Pixels come off the **Northstar (HIP)** path on gfx1030+ Radeon cards, or the
**HybridPro (Vulkan)** path. From `husk`: `husk --renderer HdRprPlugin <scene>.usd`.

---

## Troubleshooting

- **Houdini segfaults at startup after you enable the package** (`Fatal error: Segmentation fault` /
  signal 11, crash log with a corrupt stack running through `pxr_boost::python` and USD `Tf` init). This is
  the MSVC ABI mismatch: the plugin was built with a toolset newer than Houdini 21's **v143**. It builds and
  the delegate may load, but `RPR_for_Houdini` crashes Houdini at launch.
  - **Recover first:** rename the package file in `<HOUDINI_USER_PREF_DIR>/packages/` (e.g.
    `hdRpr.json` → `hdRpr.json.off`) and restart — Houdini boots clean without RPR.
  - **Then fix:** install the **v143** build-tools component, reconfigure with **`-T v143`**, rebuild +
    install, rename the package file back, and restart. Building with `PYTHON_SUPPORT=ON` does **not** help
    — it's the toolset, not the Python bindings.
- **CMake errors on an old submodule's `cmake_minimum_required`.** The `-DCMAKE_POLICY_VERSION_MINIMUM=3.5`
  flag above handles it; make sure it's present.
- **"RPR" isn't in the renderer menu.** Confirm `package/houdini/UsdRenderers.json` exists and the
  package JSON's `HOUDINI_PATH` points at `package/houdini`.
- **Licensing.** See [Licensing & attribution](#licensing--attribution) below.

---

## Licensing & attribution

> **Scoped to this folder only.** The Apache-2.0 license and attribution described here apply **only** to
> the AMD `RadeonProRenderUSD`-derived material in this `AMDProRender/` directory. They do **not** apply
> to, cover, or relicense the parent `houdini-bridge-mcp` project — that is licensed separately under the
> repository-root `LICENSE`. This is an optional, self-contained add-on.

- AMD's **`RadeonProRenderUSD`** (the `hdRpr` delegate + `RPR_for_Houdini`) is **Apache-2.0**,
  © Advanced Micro Devices, Inc. This folder distributes only **port patches**, **package JSONs**, and
  **docs** — it modifies Apache-2.0 files (supplied as patches, applied to a fresh upstream checkout;
  upstream copyright/license headers retained). See [`NOTICE.md`](NOTICE.md) and the bundled
  [`LICENSE.RadeonProRenderUSD.txt`](LICENSE.RadeonProRenderUSD.txt).
- **The Git repo ships no binaries** — only port patches, package JSONs, and docs; build-from-source
  users fetch AMD's SDK/cores themselves. **The prebuilt release, however, bundles the full built stack**
  for a complete drop-in — the `hdRpr` delegate *and* AMD's render cores (`RadeonProRender64`,
  `Northstar64`, `Tahoe64`, `Hybrid`/`HybridPro`, `RprLoadStore64`), Radeon Image Filters, Radeon ML, and
  the precompiled device kernels. **All of it is Apache-2.0** — AMD's
  [`RadeonProRenderSDK`](https://github.com/GPUOpen-LibrariesAndSDKs/RadeonProRenderSDK), `RadeonML`, and
  `RadeonImageFilter` are each Apache-2.0 (the bundled MIOpen is MIT, the DXC runtime NCSA) — so it is
  redistributed under those permissive terms with full attribution. See the release bundle's own
  `THIRD-PARTY-LICENSES.md`. No bundled component carries a proprietary EULA or a no-redistribution restriction.
- **Trademarks:** "AMD", "Radeon", and "Radeon ProRender" are trademarks of Advanced Micro Devices, Inc.,
  used here only to identify the integrated software. This project is not affiliated with or endorsed by AMD.

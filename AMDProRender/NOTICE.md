# Third-party attribution — AMD Radeon™ ProRender

> **Scope — read first.** The Apache-2.0 license and the attribution in this folder apply
> **only** to the AMD `RadeonProRenderUSD`-derived material contained in this `AMDProRender/`
> directory (the port patches and the files they modify). They do **not** apply to, cover, or
> relicense the parent `houdini-bridge-mcp` project, which is licensed separately under its own
> terms (see the repository-root `LICENSE`). This is an optional, self-contained add-on; nothing
> here changes the MCP's license.

This `AMDProRender/` folder integrates, and contains modifications to, third-party
software. It is an **optional** add-on; the core `houdini-bridge-mcp` does not depend
on it.

## What this folder distributes

- **Port patches** (`patches/*.patch`) — source diffs against AMD's open-source
  `RadeonProRenderUSD` that adapt it to build on Houdini 21 / OpenUSD 25.
- **Package/config files** (`houdini-package/*.json`) — Houdini package + renderer
  registration.
- **Documentation** (`README.md`, this file).

This folder (as committed to git) **does not** contain any AMD binaries — no
`RadeonProRender64.dll`, `Northstar64.dll`, `Hybrid.dll` / `HybridPro.dll`,
`RadeonImageFilters`, `RadeonML`, `MIOpen`, HIP/Vulkan device kernels, or any other
compiled AMD component. Building from source obtains those from AMD's own submodules.

**Optional prebuilt release.** A downloadable prebuilt package (assembled by
[`dist/pack_prorender_release.ps1`](dist/pack_prorender_release.ps1), delivered as a GitHub
Release asset — never committed to git) **does** redistribute those binaries. That
redistribution is permitted: every bundled component is Apache-2.0 / MIT / NCSA / BSD-3-Clause
(no proprietary EULA), and the release carries the full attribution bundle in
[`dist/THIRD-PARTY-LICENSES.md`](dist/THIRD-PARTY-LICENSES.md) + `dist/licenses/`. See that
manifest for the per-binary license mapping.

## Upstream work being modified

- **Project:** RadeonProRenderUSD (the `hdRpr` Hydra render delegate + `RPR_for_Houdini`
  Houdini plugin)
- **Upstream:** https://github.com/GPUOpen-LibrariesAndSDKs/RadeonProRenderUSD
- **Baseline:** tag `v3.0.4` (the newest upstream release; targets Houdini 20.5 / USD 24.x)
- **Copyright:** © Advanced Micro Devices, Inc.
- **License:** Apache License, Version 2.0. A verbatim copy is included here as
  [`LICENSE.RadeonProRenderUSD.txt`](LICENSE.RadeonProRenderUSD.txt). It also carries the
  MIT-licensed *JSON for Modern C++* (nlohmann/json) notice bundled by the upstream project.

## Notice of modification (Apache-2.0 §4(b))

The `patches/` in this folder modify files of the upstream Apache-2.0 work to build against
Houdini 21 / USD 25. The modifications are supplied **as patches** (they are applied to a
fresh upstream checkout at build time); the upstream copyright and license headers in the
patched files are retained unchanged. Summary of the changes is in [`README.md`](README.md)
("What the patch does"). These modifications are:

> © 2026 the `houdini-bridge-mcp` project, provided under the Apache License, Version 2.0
> (the same license as the upstream work), and offered upstream in the spirit of the
> project's contribution terms.

## Trademarks

"AMD", "Radeon", and "Radeon ProRender" are trademarks of Advanced Micro Devices, Inc.
They are used here **only** to identify the upstream software this add-on integrates, as
permitted for nominative/descriptive use under Apache-2.0 §6. This project is an
independent integration and is **not affiliated with, sponsored by, or endorsed by AMD**.

## Warranty

The upstream work and these modifications are provided **"AS IS", without warranty of any
kind**, per Apache-2.0 §7. See the license text for the full disclaimer.

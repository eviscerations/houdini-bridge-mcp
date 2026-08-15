<#
    pack_prorender_release.ps1 - assemble the optional prebuilt AMD ProRender package
    for houdini-bridge-mcp into a versioned, SHA256-pinned release zip.

    This is a RELEASE-ASSET builder. It does NOT touch the git repo - the binaries
    ship only as a downloadable release artifact (the repo stays source/patches-only).

    Prereq: you have already built + installed the plugin (rebuild-v143-pyon.ps1),
    so <RprSrc>\package\ is fully populated.

    Usage (from a normal PowerShell prompt):
      powershell -ExecutionPolicy Bypass -File pack_prorender_release.ps1 -Version 0.1.0
      # optional overrides:
      #   -RprSrc  <path-to>\RadeonProRenderUSD   (or set $env:RPR_SRC)
      #   -OutDir  <repo>\AMDProRender\dist\out
#>
[CmdletBinding()]
param(
    # Release version of the ProRender package. Defaults to the current release so the script runs
    # without an interactive prompt; pass -Version x.y.z to override when cutting a new package.
    [string] $Version = "0.1.0",
    [string] $RprSrc = $env:RPR_SRC,
    [string] $OutDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $RprSrc) { throw "Set `$env:RPR_SRC to your RadeonProRenderUSD checkout, or pass -RprSrc <path>." }
$distDir = $PSScriptRoot                              # AMDProRender\dist
if (-not $distDir) { $distDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $distDir) { $distDir = (Get-Location).Path }
if (-not $OutDir)  { $OutDir  = Join-Path $distDir "out" }
$amdDir  = Split-Path $distDir -Parent                # AMDProRender
$pkg     = Join-Path $RprSrc "package"
$name    = "hdRpr-h21-win-x64-v$Version"
$stage   = Join-Path $OutDir $name

Write-Host "== ProRender release packer ==" -ForegroundColor Cyan
Write-Host "  version : $Version"
Write-Host "  package : $pkg"
Write-Host "  output  : $OutDir\$name.zip"

if (-not (Test-Path (Join-Path $pkg "lib\python\rpr\RprUsd\_rprUsd.pyd"))) {
    throw "Built package not found or incomplete at '$pkg'. Run rebuild-v143-pyon.ps1 first."
}

# --- fresh stage dir ---
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

# --- 1) copy the runtime payload, excluding dev-only artifacts ---
#     keep: *.dll *.pyd *.hda *.json *.xml *.ds resources\ (kernels, rif_models, mtlx), scripts\, otls\
#     drop: include\ (headers), *.lib *.exp *.pdb (link/debug artifacts)
Write-Host "  copying package payload (excluding include\, *.lib, *.exp, *.pdb) ..."
$payload = Join-Path $stage "package"
robocopy $pkg $payload /E /XD "include" /XF "*.lib" "*.exp" "*.pdb" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
$global:LASTEXITCODE = 0   # robocopy uses 0-7 for success

# --- 2) attribution bundle (REQUIRED to ship) ---
Write-Host "  adding license bundle ..."
Copy-Item (Join-Path $distDir "THIRD-PARTY-LICENSES.md") $stage -Force
Copy-Item (Join-Path $distDir "licenses") $stage -Recurse -Force
Copy-Item (Join-Path $amdDir  "NOTICE.md") (Join-Path $stage "NOTICE.md") -Force

# --- 3) install config + user-facing install steps ---
$hp = Join-Path $amdDir "houdini-package"
if (Test-Path $hp) { Copy-Item $hp (Join-Path $stage "houdini-package") -Recurse -Force }

@"
AMD Radeon ProRender for Houdini 21 - prebuilt package (optional add-on for houdini-bridge-mcp)
Version: $Version   Platform: Windows x64   Houdini: 21.0.x (v143 ABI)   GPU: AMD RDNA2+ (gfx1030+)

REQUIRES (user-provided, not bundled):
  * SideFX Houdini 21.0.x
  * A current AMD Adrenalin driver (provides the Vulkan runtime for the HybridPro path)

INSTALL:
  1. Extract this folder somewhere permanent (e.g. next to your Houdini prefs).
  2. Copy houdini-package\hdRpr.json into <HOUDINI_USER_PREF_DIR>\packages\
     (e.g. Documents\houdini21.0\packages\) and set HDRPR_DIR in it to this folder's 'package' dir.
  3. Restart Houdini. "RPR" appears in the renderer menu.

RENDER:
  In a /stage (Solaris) context set the Hydra renderer to RPR, or headless:
    husk --renderer HdRprPlugin <scene>.usd

LICENSING: see THIRD-PARTY-LICENSES.md and the licenses\ folder. All bundled components are
Apache-2.0 / MIT / NCSA / BSD-3-Clause. This package is separate from, and does not relicense,
houdini-bridge-mcp itself.
"@ | Set-Content -Encoding ASCII (Join-Path $stage "INSTALL.txt")

# --- 4) zip + checksum ---
$zip = Join-Path $OutDir "$name.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "  compressing ..."
$sevenzip = @("C:\Program Files\7-Zip\7z.exe", "C:\Program Files (x86)\7-Zip\7z.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($sevenzip) {
    Push-Location $stage
    & $sevenzip a -tzip -mx=9 -bso0 -bsp0 $zip "*" | Out-Null
    Pop-Location
    if ($LASTEXITCODE -ne 0) { throw "7-Zip failed ($LASTEXITCODE)" }
} else {
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
}
$sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
"$sha  $name.zip" | Set-Content -Encoding ASCII (Join-Path $OutDir "$name.zip.sha256")

$sizeMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host ""
Write-Host "== DONE ==" -ForegroundColor Green
Write-Host "  zip    : $zip  ($sizeMB MB)"
Write-Host "  sha256 : $sha"
Write-Host "  (sha written to $name.zip.sha256 - publish it beside the release asset)"

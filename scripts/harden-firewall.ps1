<#
.SYNOPSIS
  Manage the Windows Firewall rule that scopes the houdini-bridge-mcp executor port's network reach.

.DESCRIPTION
  The in-Houdini executor serves on a loopback HTTP port, but SideFX `hwebserver.run()` cannot bind
  127.0.0.1-only — it listens on all interfaces. This script sets the transport boundary with a
  Windows Firewall rule (Windows exempts loopback from filtering, and explicit rules override the
  defaults), matching the executor's `network_mode`:

    -Mode loopback (default)  Inbound BLOCK on the port. Nothing off-box reaches the executor;
                              the local gateway's 127.0.0.1 connection is unaffected. Single machine.
    -Mode lan                 Inbound ALLOW on the port scoped to the local subnet (RemoteAddress=
                              LocalSubnet by default, or -Subnet). Other workstations on the studio
                              LAN can drive Houdini; the routable internet cannot; token auth still
                              gates every call. A deliberate opt-in — never the default.

  The executor refuses to arm unless the rule matching its network_mode exists (fail-closed), unless
  the operator sets "allow_insecure_bind": true in ~/.houdini-bridge-mcp/arm.json. Rules persist across
  reboots. Re-run to switch modes; the script removes the other mode's rule first.

.PARAMETER Port
  Executor loopback port (must match arm.json "port"). Default 8766.
.PARAMETER Mode
  loopback (default) or lan.
.PARAMETER Subnet
  LAN mode only: the RemoteAddress scope. Default "LocalSubnet". Accepts a CIDR/range netsh understands
  (e.g. "192.168.1.0/24"). Keep this as tight as your studio subnet.
.PARAMETER Remove
  Delete both rules for the port (loopback-block and lan-allow) and exit.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\harden-firewall.ps1 -Port 8766
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\harden-firewall.ps1 -Port 8766 -Mode lan
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\harden-firewall.ps1 -Port 8766 -Mode lan -Subnet 192.168.1.0/24
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\harden-firewall.ps1 -Port 8766 -Remove
#>
param(
    [int]$Port = 8766,
    [ValidateSet("loopback", "lan")]
    [string]$Mode = "loopback",
    [string]$Subnet = "LocalSubnet",
    [switch]$Remove
)

$denyRule  = "houdini-bridge-mcp-deny-inbound-$Port"   # loopback mode
$allowRule = "houdini-bridge-mcp-allow-lan-$Port"      # lan mode

# --- self-elevate: firewall changes need administrator ---
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Administrator rights required - relaunching elevated (accept the UAC prompt)..."
    $inner = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Port $Port -Mode $Mode -Subnet `"$Subnet`""
    if ($Remove) { $inner += " -Remove" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $inner
    return
}

# Clear both rules first so mode switches are clean (netsh is native; "no rules match" is harmless).
netsh advfirewall firewall delete rule name="$denyRule"  2>$null | Out-Null
netsh advfirewall firewall delete rule name="$allowRule" 2>$null | Out-Null

if ($Remove) {
    Write-Host "Removed firewall rules for port $Port. The executor will refuse to arm unless"
    Write-Host "you re-run this script or set allow_insecure_bind in arm.json."
    return
}

if ($Mode -eq "loopback") {
    netsh advfirewall firewall add rule name="$denyRule" dir=in action=block protocol=TCP localport=$Port profile=any | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    if ($ok) {
        Write-Host "Mode: loopback. Rule '$denyRule' created."
        Write-Host "Inbound TCP $Port is blocked from the network; loopback (127.0.0.1) is unaffected."
    }
} else {
    netsh advfirewall firewall add rule name="$allowRule" dir=in action=allow protocol=TCP localport=$Port remoteip="$Subnet" profile=any | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    if ($ok) {
        Write-Host "Mode: lan. Rule '$allowRule' created (RemoteAddress=$Subnet)."
        Write-Host "Inbound TCP $Port is allowed from $Subnet only; the internet is not. Token auth still applies."
        Write-Host "Set \"network_mode\": \"lan\" in ~/.houdini-bridge-mcp/arm.json so the executor expects this rule."
    }
}

if ($ok) {
    Write-Host "Re-run with -Remove to undo, or with a different -Mode to switch."
} else {
    Write-Error "Failed to create the firewall rule (netsh exit $LASTEXITCODE). Run this in an elevated shell."
}

# houdini-bridge-mcp — setup & first test

Wiring the tool so an AI client (e.g. Claude Desktop) can drive Houdini. Three moving parts:

```
MCP client ──stdio──▶ houdini-bridge-mcp.exe (gateway) ──loopback:PORT──▶ executor (armed inside Houdini)
```

The gateway and the in-Houdini executor share one **token**, **port**, and **working directory** —
all single-sourced from `~/.houdini-bridge-mcp/arm.json`, which the GUI writes. You configure once in the
GUI; Houdini auto-arms on launch. No manual shell snippets, no port-collision dance.

---

## 1. Prerequisites

- **Houdini 21.0.671**.
- **Rust toolchain** (stable) — to build the gateway.
- **Python** — only for the optional tile downloader; any recent CPython works. Its one dependency
  (`numpy`) is declared in `downloader/requirements.txt` (`pip install -r downloader/requirements.txt`).
  The core gateway + in-Houdini executor need no Python packages.

## 2. Build the gateway

```
cd gateway
cargo build --release
```

Produces one binary: `<PATH_TO_REPO>\gateway\target\release\houdini-bridge-mcp.exe`. It is both the GUI and
the headless MCP gateway — the mode is selected by the `HMCP_GW_HEADLESS` env var (unset = GUI window;
`1` = headless stdio server).

## 3. Install the auto-arm Houdini package

This drops a Houdini [package](https://www.sidefx.com/docs/houdini/ref/plugins.html) that arms the
executor automatically at GUI startup.

**Via the GUI (recommended):** launch `houdini-bridge-mcp.exe`, then **Settings → Install Houdini package**.

**Or manually**, copy the two static package files into your Houdini user pref dir
(`<HOUDINI_USER_PREF_DIR>`, which defaults to `%USERPROFILE%\Documents\houdini21.0`):

```
houdini_package/houdini-bridge-mcp.json            →  <HOUDINI_USER_PREF_DIR>/packages/houdini-bridge-mcp.json
houdini_package/houdini-bridge-mcp/scripts/456.py  →  <HOUDINI_USER_PREF_DIR>/houdini-bridge-mcp/scripts/456.py
```

The package `.json` goes inside `packages/`; the plugin folder sits one level up in the pref-dir root.
Both files are shippable — no absolute paths, usernames, or machine values (everything dynamic is read
at runtime from `arm.json`).

## 4. Configure via the GUI

Launch `houdini-bridge-mcp.exe` with `HMCP_GW_HEADLESS` unset so the window appears, then:

1. **Settings** — confirm the **Executor port** and **Session token** (defaults are fine; the token
   is the shared secret).
2. **Working dir** tab — type the **working-directory ROOT** (your project root — every subdirectory
   under it is traversable) and click **Apply**.
3. Back in **Settings**, turn on **Auto-arm Houdini**.

Apply + Auto-arm merge-write `~/.houdini-bridge-mcp/arm.json`:

```json
{
  "enabled": true,
  "working_dir": "<WORKING_DIR>",
  "token": "<YOUR_TOKEN>",
  "port": 8765,
  "executor_root": "<abs dir containing the houdini_executor python package>"
}
```

This file is the single source of truth. The GUI, the executor, and the headless gateway all read
`working_dir` / `port` / `token` from it live — changing the working dir is just Apply, no restart.

## 5. Arm the executor

**Harden the firewall first.** The executor arms **fail-closed** — it refuses to arm unless a firewall
rule blocks inbound connections to its loopback port. Run the bundled script once (elevated):

```
scripts/harden-firewall.ps1              # -Mode loopback (default): loopback-only, single machine
scripts/harden-firewall.ps1 -Mode lan    # allow a studio LAN to reach the executor
```

Use `loopback` (the default) for a single trusted machine; use `lan` only on a trusted studio network.

Then launch Houdini. The installed package auto-arms the executor from `arm.json` — the console prints:

```
[houdini-bridge-mcp] executor armed
```

The GUI's status pill shows **Armed** with the connected Houdini version. No Python-shell snippet.

Verify from any shell:

```
curl.exe http://127.0.0.1:8765/health -H "X-HMCP-Token: <YOUR_TOKEN>"
```

→ `{"ok": true, "service": "houdini-bridge-mcp", ...}` (use your configured port).

## 6. Register with your MCP client

Point your client (e.g. Claude Desktop — `%APPDATA%\Claude\claude_desktop_config.json`) at the gateway
binary in **headless** mode. The gateway reads `working_dir` / `port` / `token` from `arm.json`, so the
env block only needs the headless flag:

```json
{
  "mcpServers": {
    "houdini-bridge-mcp": {
      "command": "<PATH_TO_REPO>\\gateway\\target\\release\\houdini-bridge-mcp.exe",
      "env": {
        "HMCP_GW_HEADLESS": "1"
      }
    }
  }
}
```

Fully quit and reopen the client. In a new chat the `houdini-bridge-mcp` tools appear.

## 7. First test

From an MCP-client chat:

1. `scene_info` → confirms the gateway↔executor link.
2. `import_heightfield(npy="<TILE>.npy", name="terrain", display=true)` → turns a prepped DEM tile
   into a real Houdini heightfield.

The `npy` path is relative to / inside the working-dir ROOT, and each `<TILE>.npy` needs its
`<TILE>.npy.json` sidecar (`cols`, `rows`, `res_m`, `houdini_center_x/z`, `nodata`) beside it.

---

## 8. Optional — AMD GPU rendering (ProRender)

Houdini's Karma XPU GPU path is NVIDIA/OptiX-only. On an **AMD Radeon** (RDNA2 / gfx1030+), the optional
`AMDProRender/` add-on installs AMD's `hdRpr` render delegate built natively for Houdini 21 / USD 25
(AMD ships no prebuilt H21 plugin), so **"RPR"** appears as a GPU Hydra renderer in Solaris. It is
independent of the core MCP — download the prebuilt release or build from source per
[AMDProRender/README.md](../AMDProRender/README.md).

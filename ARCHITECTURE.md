# Architecture — Houdini Bridge MCP

A security-first, data-only control surface that lets an AI agent drive Houdini over MCP across most
of what Houdini does — where the AI authors *validated* wrangles, never arbitrary code. The catalog
spans geometry & cleanup, instancing, simulation, character rigging & animation, COP/image, look &
materials, ML/ONNX, SideFX-Labs, and render/export, plus a unique **real-world geodata lane** (DEM /
3DEP / LIDAR) that reprojects and places elevation at true scale — one strong lane among many, not the
whole story. Windows-first. **Target: Houdini 21.0.671** (H22 not yet adopted, pending stability).

## Design principles
1. **Security by construction, not by filter.** The tool exposes a fixed, typed, *data-only*
   surface. No arbitrary code execution reaches Houdini — no Python-exec, no generic node driver,
   no raw VEX. Houdini's embedded Python is full unsandboxed CPython (host RCE), so the only defense
   is constraining *what can reach it*. The one code-carrying tool — `set_attrib_expr`, opt-in and
   **default-off** — is not an exception: it takes a VEX attribute snippet the executor *validates
   against an allowlist before Houdini ever sees it* (allowlisted functions only, no file/host/network
   I/O, provably total — it always halts), so it is a bounded input subset, never a raw-VEX or
   arbitrary-code path. Conditionals plus statically-bounded counted loops are allowed; opt-in loops
   (`allow_attrib_loops`) and deletion-only topology edits (`removepoint`/`removeprim`,
   `allow_attrib_geoedit`) each sit behind their own default-off consent.
2. **The bridge wires, the human fires.** Render graphs are built fully but never executed by the
   agent — the user triggers renders. Removes resource-DoS, unwanted output, and heavy-scene freezes.
3. **One working directory.** All file reads/writes are `realpath`-confined to a single
   user-configured root. Nothing escapes it.
4. **Watched and auditable.** A live log of every call the agent makes, visible in the GUI.

## Topology

```
  AI / MCP client            gateway (Rust + GUI)                 executor (Python, in Houdini)
  ───────────────  stdio   ───────────────────────  loopback   ─────────────────────────────
  Claude / Cursor  ─────▶   • sole entry point         HTTP/     • hwebserver in the live session
                            • typed, schema-validated  pipe      • fixed table of bounded ops
                            • serialized 1-at-a-time              • no exec / node_op / raw VEX
                            • working-dir confinement             • main-thread-marshalled hou.*
                            • LIVE AUDIT LOG (GUI)                • wire-only render
```

The gateway is the front door; the executor's *capability set* is the security boundary. The LLM
never touches a network port — it speaks stdio MCP to the gateway.

Both halves are built: the gateway is a hand-rolled MCP stdio server (newline-delimited JSON-RPC
2.0 over stdin/stdout) driving a compile-time-typed tool catalog, shipped with a tabbed launcher
GUI; the executor runs inside a live Houdini session, auto-armed at startup with no manual snippet.
See **Runtime mechanisms** below for how arm / hot-reload / working-dir confinement wire together.

## Components

### `houdini_executor/` — the in-Houdini Python executor
- Runs inside Houdini via `hwebserver` (loopback). Full `hou.*` access, but exposes ONLY a fixed
  registry of typed, validated handlers.
- Every handler: numeric/enum/allowlisted-path inputs, clamped numerics, request-size cap.
- Path confinement: all read/write paths resolved via `realpath` and checked against the single
  configured working-directory root.
- Main-thread marshalling for `hou.*` (Houdini's scene model is single-threaded).
- `handlers/` — one module per workflow stage (below).

### `gateway/` — the Rust MCP server + GUI (sole LLM entry point)
- **Hand-rolled MCP stdio server** — newline-delimited JSON-RPC 2.0 over stdin/stdout (no SDK
  dependency). Handles `initialize` / `tools/list` / `tools/call`; STDOUT is reserved for the
  protocol. Exposes the executor's operations as typed MCP tools from a compile-time catalog
  (`tools.rs`), each tool declaring its `Param`s once so schema + validation + dispatch derive from
  one declaration. Unit-tested (`#[cfg(test)] mod tests`).
- **Tabbed launcher GUI** (eframe) — a left-nav app with **Status**, **Working dir**, **Audit log**,
  **Data sources**, and **Settings** tabs, plus an **Armed** status pill (orange when armed). The
  Working-dir tab's **Apply** writes the confinement root to `arm.json`; Settings carries an
  **Auto-arm Houdini** toggle and an **Install Houdini package** action.
- Path/URL allowlisting and typed schema-validation are enforced here, as is an **8 MB inbound-frame
  cap** on the stdio transport (a memory-DoS guard so no single unterminated line can buffer unbounded);
  token auth and the executor's own 1 MB request-body cap are executor-side (see *Executor core* below).
  Requests are dispatched one-at-a-time (serialized); there is no rate limiter — over a single-client
  stdio pipe (the one AI client) rate-limiting adds no real protection, and serialization already bounds
  concurrency. The gateway is the front door — the executor's capability set is the security boundary.
- `arm.json` is the single source of truth for `working_dir` / `port` / `token`; `config.rs`
  resolvers (`resolve_working_dir` / `resolve_executor_port` / `resolve_token`) read it live
  (mtime-cached) so gateway and executor always agree on the same confinement root and endpoint.

### `downloader/` — trusted-source data acquisition
- Provenance-gated fetch of DEM/3DEP from a whitelist of trusted sources (USGS 3DEP / TNM Access,
  state DEM portals, global DEM, etc.). Multi-resolution (3DEP + DEM). No arbitrary-URL import.
- Implemented as a set of source adapters (a shared `fetch`/`net`/`sources` core plus per-portal
  modules) feeding the acquire stage. The source whitelist is the boundary — the design and its
  trusted-source resolution are settled.

## Endpoint surface — 1,467 typed, validated tools across 11 workflow stages
1. Acquire/Import · 2. Terrain (heightfield) · 3. Model/Geometry · 4. Cleanup/Mesh (+VDB) ·
5. Instance/Scatter · 6. Sim (recipe-templated) · 7. Look (materials/lights/cameras) ·
8. Render/Export (render = wire-only, export = executable-confined) · 9. Analysis (templated VEX
lib) · 10. Scene/utility · 11. Weather/Atmospherics/Ocean.

## Runtime mechanisms

How the two halves arm, stay in sync, and hot-iterate:

- **Auto-arm (no manual snippet).** A Houdini 21 package (`houdini_package/` → the user pref dir)
  runs a startup script that, once the UI is up, reads `~/.houdini-bridge-mcp/arm.json` and — if
  `enabled` — puts the executor on `sys.path` and calls `server.auto_arm()`. `auto_arm()` re-reads
  `working_dir` / `token` / `port` from the config (the gateway env is absent because the *user*
  launched Houdini) and arms. Missing/disabled config is a silent no-op; startup is never held up
  (the graphical `hwebserver.run(...)` returns immediately). The GUI's **Install Houdini package**
  action copies the package into place; the **Auto-arm** toggle flips `enabled`.
- **Single-source working dir.** `arm.json`'s `working_dir` — written by the GUI's **Apply** — is
  the confinement root, read *live* (mtime-cached) by **both** sides: the executor via
  `_effective_working_dir()` and the gateway via `config.rs::resolve_working_dir`. Every path is
  `realpath`-resolved and required to sit under that root (subdirectories are traversable; anything
  outside raises). If the config is absent/unreadable/invalid, both fall back to the arm-time root,
  so confinement never silently opens up.
- **Routing — one prefix handler.** hwebserver patterns are exact/prefix, never regex. The executor
  registers exactly one prefix catch-all, `hwebserver.urlHandler("/tool", is_prefix=True)`, plus a
  `/health` route. The handler strips the `/tool/` prefix and calls `_dispatch(name, request)`,
  which looks the handler up in `_REGISTRY` **at request time**. Adding a tool = adding a registry
  entry; no route re-registration (routes lock at `hwebserver.run()`).
- **Hot-reload dev loop.** `POST /tool/reload` reloads every `houdini_executor.handlers.*` module
  in place, re-running their `@endpoint` decorators to overwrite `_REGISTRY` entries — so code
  fixes take effect **without restarting Houdini**. Because the single `/tool` catch-all resolves
  from `_REGISTRY` per request, no routes need re-registering. The `server` module itself (which
  owns `_REGISTRY`) is never reloaded.

## Build status

- **Executor core — built.** Server bootstrap, auth (`X-HMCP-Token`, constant-time compare),
  `realpath` path-confinement, main-thread marshalling (`run_on_main`), 1 MB request cap, the
  handler registry, hot-reload, and proof endpoints (health, scene_info). Data-only: no exec, no
  generic node driver, no raw VEX.
- **Full endpoint set — built.** 1,467 typed, validated tools across the 11 workflow stages, in
  `houdini_executor/handlers/` (one module per stage).
- **Rust gateway + GUI — built.** Hand-rolled MCP stdio server + compile-time typed catalog
  (`tools.rs`, unit-tested) + the tabbed eframe launcher (Status / Working dir / Audit log / Data
  sources / Settings, Armed pill, Install-package + Auto-arm) + `arm.json` single-source config.
- **Downloader — implemented.** Trusted-source DEM/3DEP acquisition; design and source whitelist
  settled.
- **Docs + honest security README + packaging** — the shippable Houdini startup package and this
  document.

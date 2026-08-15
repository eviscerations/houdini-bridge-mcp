# Contributing to houdini-bridge-mcp

Thanks for your interest in contributing. This is an MCP server that gives an AI assistant typed, data-only control of a live Houdini session across most of what Houdini does — geometry, simulation, character rigging & animation, look, render/export, plus a real-world geodata lane (DEM/LiDAR) — where the AI authors *validated* wrangles, never arbitrary code. Contributions that widen tool coverage, harden the security boundary, and improve reliability on real datasets are especially welcome.

---

## Before you start

Check the open issues before starting work to avoid duplicating effort. If you want to work on something not listed, open an issue first to discuss it.

See the design docs under `docs/` (start with `ARCHITECTURE.md`) for the layout, the executor spine, and the security model before making changes.

---

## What we need most

- **Tool coverage on real hardware and datasets** — exercise the existing tools against real Houdini scenes, DEM/LiDAR sources, and node/format combinations, and report what breaks
- **New node and format support** — additional typed endpoints for import/export, geometry ops, and heightfield work, following the data-only pattern
- **Bug reports with reproduction steps** — the exact tool call, params, and the resulting executor traceback
- **Documentation improvements** — clearer setup, tool reference, and troubleshooting

---

## Development setup

The project has two halves: a Rust gateway (the MCP stdio server, GUI, and typed tool catalog) and a Python executor that runs inside Houdini.

```
git clone <PATH_TO_REPO>/houdini-bridge-mcp
cd houdini-bridge-mcp
```

Build the gateway:

```
cd gateway
cargo build --release
```

Use `cargo check` for fast iteration while editing Rust. The Python executor is deployed as a Houdini package (`houdini_package/`) that auto-arms from `~/.houdini-bridge-mcp/arm.json` when Houdini launches.

The dev loop is fast because the two halves reload independently:

- **Handler changes hot-reload live.** After editing a file under `houdini_executor/handlers/`, `POST http://127.0.0.1:<port>/tool/reload` — the single `/tool` prefix catch-all resolves handlers at request time, so no Houdini restart is needed.
- **Executor spine changes need a Houdini relaunch.** Edits to `server.py` require restarting Houdini, which re-arms from `arm.json`.
- **New tools reach the AI's tool list only after a gateway rebuild plus an MCP-host restart.** The gateway exe is locked while the host runs it, so rebuild and restart the host to pick up catalog changes.

---

## Adding or changing a tool

A tool exists in two places that must stay in exact sync: the typed handler in the executor, and its declaration in the gateway catalog.

1. **Handler** — add an `@endpoint("name")` function in the right group under `handlers/<group>.py`. Keep it data-only: run filesystem params through the existing `confined_path`, set uncertain node parms with `_try_set`, and clamp numeric inputs.
2. **Catalog** — add a matching `ToolDef` in `gateway/src/tools.rs` with the params declared in exact sync with the handler.
3. **Gate** — the handler must be `py_compile`-clean (`py -3.14 -m py_compile <file>`) and the gateway must pass `cargo build --release` (or `cargo check` while iterating).
4. **Test** — reload the handler and exercise it against a live scene; it exposes to the AI at the next gateway rebuild.

**Non-negotiable: the executor is data-only.** Never add an arbitrary-code, generic-node, or raw-VEX endpoint — any of those is remote code execution against full CPython. A catalog test asserts that no such tools are ever exposed; keep it green. Every new endpoint follows the typed-dispatch pattern only.

---

## Pull request guidelines

- Keep PRs focused — one fix or feature per PR
- A new or changed tool must update both the handler and the matching `ToolDef` in `gateway/src/tools.rs`
- Confirm the gateway builds (`cargo build --release`) and touched handlers are `py_compile`-clean before submitting
- Keep the no-RCE catalog test green
- If adding a tool, update the tool reference in the docs

---

## Code style

- **Rust** (gateway): keep the catalog the single source of truth for what the AI can call — it is the security boundary
- **Python** (executor): typed, data-only handlers; use `confined_path`, `_try_set`, and `clamp` from the server spine rather than reaching for raw parm sets or unbounded values
- Error messages should be actionable — tell the caller what to fix, not just what went wrong
- No endpoint may evaluate caller-supplied code

---

## Reporting bugs

Open an issue with:
- Houdini version
- Your OS version
- The tool call and the exact params you passed
- Expected vs actual behavior
- The executor traceback, if any

---

## Third-party license notices

`THIRD-PARTY-LICENSES.md` is **generated**, not hand-written. Before a release, produce it with
[`cargo-about`](https://github.com/EmbarkStudios/cargo-about):

```
cd gateway
cargo install cargo-about   # one-time
cargo about generate about.hbs > ../THIRD-PARTY-LICENSES.md
```

The generator config lives at `gateway/about.toml`. Regenerate whenever the dependency set changes so
the notices stay in sync with `Cargo.lock`. Do not edit `THIRD-PARTY-LICENSES.md` by hand.

---

## License and Developer Certificate of Origin

This project is **dual-licensed**: free for noncommercial use under the PolyForm Noncommercial
License 1.0.0 (`LICENSE`), with commercial use under a separate paid agreement
(`COMMERCIAL-LICENSE.md`). For that model to hold, contributions must be granted on terms that let
the maintainer distribute them under **both** licenses.

By submitting a contribution, you agree that:

- You license your contribution to the project and the licensor (Shashin Studio LLC) under the
  PolyForm Noncommercial License 1.0.0, **and** you grant the licensor a perpetual, worldwide,
  non-exclusive, royalty-free right to license your contribution under the project's commercial
  license terms as well. This is what keeps the dual-license viable.
- You certify authorship and right to contribute under the **Developer Certificate of Origin**
  (DCO 1.1, <https://developercertificate.org/>), which you affirm by adding a `Signed-off-by` line
  to each commit:

  ```
  Signed-off-by: Your Name <your.email@example.com>
  ```

  (`git commit -s` adds this automatically.)

If the maintainer later adopts a formal Contributor License Agreement (CLA) instead of the DCO
sign-off, this section will be updated and existing contributors notified.

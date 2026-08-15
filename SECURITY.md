# Security Policy

## Scope

houdini-bridge-mcp is a local, single-user tool. It gives an AI client typed, validated control over a live Houdini session through a small Rust gateway. The attack surface is limited to:

- The stdio JSON-RPC channel between the AI client and the gateway
- The loopback HTTP channel between the gateway and the in-Houdini Python executor
- The local filesystem (paths passed as tool arguments)
- Tool arguments themselves (numbers, enums, node paths, file paths)
- The executor Python loaded into the Houdini session at arm time

---

## Threat model

houdini-bridge-mcp is a **local, single-user tool driven by the machine's owner through their AI client.** Its threat model is the owner running it on their own machine — not an untrusted, multi-tenant, or network-exposed deployment.

- **Trusted:** the machine and its owner, the Houdini install, the AI client that speaks JSON-RPC to the gateway.
- **Not trusted:** the *arguments* that arrive on any tool call. Even with a trusted owner, an AI client can be steered by the content it reads, so every argument is validated on the way in rather than assumed benign.
- Do **not** expose the gateway or the executor's loopback port to untrusted network access. The design assumes both endpoints live inside one trust domain on one machine.

---

## Design: data-only executor

The core security decision is that the in-Houdini executor exposes **only a fixed registry of typed, validated handlers** — and nothing else.

There is deliberately **no arbitrary-code path**: no `exec` endpoint, no generic node driver, no raw VEX/wrangle authoring, no "run this snippet" tool. Houdini's embedded Python is full, unrestricted CPython — so any one of those would be remote code execution with the owner's full privileges. Rather than sandbox a dangerous capability, the capability simply does not exist in the catalog.

### Why data-only — and why this was not built on an exec-based MCP

Most existing DCC MCP servers (including the popular Blender and Houdini ones) expose an `execute_code` / arbitrary-Python or raw-wrangle tool and hand the model the keys — effectively "here's a shell, good luck." This project was **not** iterated from those; it was built data-only from the start, and that is a deliberate response to how AI agents actually fail:

- **The model can be wrong, steered, or degenerate.** A driving agent can hallucinate, be manipulated by content it reads (prompt injection), or simply malfunction. The README says plainly that the AI can make mistakes — this design assumes it *will*, and withholds the dangerous capability by construction rather than trusting the model to use it well.
- **Arbitrary code + an open goal is the documented high-severity failure mode.** Through 2026 the recurring, escalating pattern with agentic AI has been: an agent given code execution and a goal escapes its sandbox, acts autonomously and undetected at machine speed, and reaches credentials, the network, or the filesystem — "win by any means." An `execute_code` tool is exactly that configuration.
- **You cannot reliably sandbox unrestricted CPython/VEX after the fact.** A wrapper you *hope* holds is weaker than a capability that does not exist. So the boundary here is the **fixed typed tool catalog itself** — the model can only ever invoke enumerated, schema-validated, argument-checked handlers.
- **Oversight is preserved by construction.** Renders/caches/sims are WIRE-ONLY (the tool builds the network; the human fires it), new tools require a human-run rebuild, and the one code lane (validated VEX) is a bounded, non-Turing-complete, default-off, operator-consented subset validated *before* it runs — never an open door.

The trade-off is honest and intentional: this MCP is more limited than a shell-handing one, and that limitation **is the security property.** It is why the tool can be pointed at a live Houdini session without the owner betting their machine on the model always behaving.

A test enforces this at build time: the tool catalog is asserted to never contain `exec`, `node_op`, `wrangle`, or `heightfield_op`. New capability is added only by declaring a new typed handler, never by widening an existing one into a general-purpose driver.

The consequence for how you reason about this tool: **the gateway is the front door, not the security boundary. The executor's capability set — the fixed list of typed handlers — is the boundary.** Anything not expressible as a call to one of those handlers cannot be reached, regardless of what a client sends.

---

## Input validation

Every tool declares its parameters as typed values. That single declaration generates both the schema a client sees and the server-side validation every call must pass before anything reaches Houdini. Nothing is free-form.

- **Path confinement.** Every filesystem path parameter is `realpath`-confined to a single working directory (read from `~/.houdini-bridge-mcp/arm.json`; subdirectories are traversable). Resolution follows symlinks and collapses `..` before checking containment, so a junction or symlink cannot tunnel out of the root. Not-yet-existing write targets are allowed only when their resolved parent chain stays confined.
- **Defense in depth.** The gateway confines paths, and the executor **re-checks** every path against the same root — it never trusts the gateway's validation alone. The executor also normalizes Windows extended-length (`\\?\`) prefixes so a canonicalized path still matches the root.
- **Numeric clamps.** Numeric parameters are **clamped** to their declared range, not rejected. A request for 10^9 rows becomes the ceiling, never an out-of-memory crash. Non-finite numbers are rejected.
- **Typed everything else.** Enum parameters must be one of a fixed set; node paths and strings must be non-empty; fixed-length numeric tuples must match their length. Unknown parameter keys are rejected outright — nothing unexpected is smuggled past the boundary.
- **Authentication.** The executor requires a shared session token on every request (`X-HMCP-Token`), compared in constant time. Requests without a valid token are refused.
- **Body cap.** The request body is capped (1 MB) as a denial-of-service guard; oversize requests are rejected before parsing.
- **Single-threaded scene access.** Houdini's API is not thread-safe. Worker threads never touch the scene directly; they marshal each job onto Houdini's main thread. A per-job timeout bounds the *caller's* wait and prevents a late-completing job from mutating the scene after a failure was reported. Honest limit: the timeout cancels jobs that have **not yet started**; a job already executing on the main thread runs to completion — Houdini exposes no safe mid-cook preemption, so a genuinely runaway cook can still block the session until it finishes. The design keeps the common heavy paths off that hazard rather than relying on a watchdog: renders/bakes/ROPs are **WIRE-ONLY** (built + wired, never executed by the MCP — the human fires them), the one code lane (validated VEX) permits only **bounded loops** (`while`/`do`/`gather` stay banned; `for` is accepted only with a static literal or `min()`-clamped ceiling, and `foreach` only as an array loop whose iteration count VEX **fixes at entry** — snapshot-verified finite — and which is **leaf-only** so a runtime count can never be amplified by a surrounding/nested loop; opt-in and default-off) so the subset stays **total / not Turing-complete** — a snippet can be slow but never infinite, and with **no mid-cook preemption** a bounded-but-slow cook still runs to completion before the human can fire it, and numeric magnitudes are clamped. Topology mutation is split into two separate default-off consents, each pinned to the literal input-`0` sandbox geometry and each independent (enabling one never grants the other): **deletion** (`removepoint`/`removeprim`, `allow_attrib_geoedit`) is monotone-shrinking / self-bounding; **construction/growth** (`addpoint`/`addprim`/`addvertex`/`removevertex`, `allow_attrib_geogrow`) has no static total cap, so it is **big-but-finite** (bounded by loop caps × elements) — a heavy build cooks slowly, never infinitely, and the human fires it. The memory governor is **advisory telemetry, not a hard resource gate** (it surfaces a live headroom envelope; only a catastrophic band refuses) — treat it as best-effort, not a guarantee against OOM.
- **`batch` runs each op through the same gate — no bypass.** The native `batch` meta-tool exists only to cut per-call latency (up to 64 ops in one MCP call). It grants no capability a direct call lacks: each sub-op is dispatched through the *identical* code path — tool lookup, `ToolDef` schema-validation, numeric clamping, `realpath` path-confinement, and one ordered audit event per op. A batch can invoke only real catalog tools (an unknown or non-catalog name errors like any direct call), and it **cannot nest** — an op named `batch` is rejected both at structural validation and defensively at dispatch. Batching is an envelope around the boundary, never a hole in it.
- **Optional action throttle (`HMCP_MIN_ACTION_INTERVAL_MS`).** Off by default (`0`). When set to N milliseconds, the gateway enforces a minimum N-ms wall-clock gap between successive **destructive** tool calls — `delete_node`, `clear_scene`, `save_scene`, `delete_keyframes` — by *sleeping* out the remainder of the interval before dispatch. It **paces, it never rejects**: a legitimate slow sequence still completes, but a runaway loop or prompt-injection cannot rapid-fire scene-destroying calls faster than the floor allows, giving a human time to notice. Non-destructive tools (builds, reads) are never delayed, so batch-building and inspection stay fast. This is a safety governor, not a security boundary — it bounds the *rate* of destructive actions, not their authorization (that is still the fixed capability set + validation above).

---

## Supported versions

Security fixes are applied to the latest published version only.

| Version | Supported |
|---|---|
| 0.x (latest) | ✅ |
| older | ❌ |

---

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Use GitHub's private vulnerability reporting on the houdini-bridge-mcp repository:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability** to open a private security advisory.
3. Describe the issue with enough detail to reproduce it.

You'll receive a response within 7 days. If the vulnerability is confirmed, a fix will be released as soon as practical and you'll be credited in the release notes if you wish.

---

## Known design decisions

- **No arbitrary-code capability:** The executor exposes only typed handlers. `exec`, generic node ops, and raw VEX/wrangle authoring are intentionally absent, because Houdini's Python is unrestricted CPython and any of them would be remote code execution. The build has a test that fails if a banned tool ever appears in the catalog.

- **Server-authored node templates (disclosed):** Two categories author node *contents* server-side, disclosed here so a code reader doesn't mistake them for a loose boundary. (1) The one **validated** code lane — `set_attrib_expr` — places a safe-VEX snippet that is checked allowlist-first against a non-Turing-complete subset *before* it is ever set on a wrangle (default-off, gated executor-side by `allow_attrib_expr`). That lane may also **delete** input-0 elements (`removepoint`/`removeprim`, gated behind the *separate* default-off `allow_attrib_geoedit` consent — monotone-shrinking, arg0 pinned to literal `0`) and **construct/grow** them (`addpoint`/`addprim`/`addvertex`/`removevertex`, gated behind a *third* separate default-off `allow_attrib_geogrow` consent — big-but-finite, arg0 pinned to literal `0`); enabling one topology consent never grants the other. (2) A small, **enumerated** set of handlers author a **fixed** template with only type-constrained values interpolated — no raw user string ever reaches the code text. The full set (15 sites across 13 tools, re-verified 2026-08-14) is: **three Python-SOP injectors** — `import_heightfield` and `import_ecef_tile` (a `confined_path` value via `%r` into a fixed `np.load(...)` template) and `create_curve` (`json.dumps` of per-coordinate `float()`-validated `[x,y,z]` triples into a fixed curve-build template); and **twelve VEX attribwrangle templates** — `import_pointcloud` (integer decimation stride), `build_globe` (×3: a constant lon/lat→uv snippet plus confined-path/float triplanar terms), `point_normals`, `segment_planar`, `despeckle`, `tag_radial`, and `isolate` (numeric bounds + a world-transform tuple, all via `%d`/`%g`/`%.9g` after clamping), plus `heightfield_morph` and `heightfield_fill` (×2), whose interpolated layer/attribute **names** are each passed through `validate_ident` and whose numerics go via `%g`. Every interpolation is thus a clamped numeric (`%d`/`%g`/`%.9g`), a `confined_path` value (`%r`), a `json.dumps` of float-validated numbers, or a `validate_ident`-gated identifier — never a raw user string — so none is an injection vector. This list is maintained here as the tool surface grows into new lanes, and the CI source-guard `test_no_raw_vex_sinks.py` (RT-11) fails the build if a new unaudited raw-code-text sink is introduced.

- **Why no raw VEX — and how safe-VEX keeps the human in the loop:** Raw VEX and arbitrary Python are excluded because Houdini's embedded Python is full, unrestricted CPython, and VEX has escape hatches (`system`/`run`, expression/`ophook` bridges, file and network builtins) — either is remote code execution with the owner's full privileges. But wrangles are the *real* tool for the art of the work (threshold-driven breaking, cluster-boundary logic, custom particle masks), so the bridge does not ban them; it **gates** them:
  - The **validated safe-VEX lane** (`set_attrib_expr`) accepts a wrangle snippet, checks it **allowlist-first** against a non-Turing-complete subset (attribute read/write, `ch()`, conditionals, math, `sprintf`, a whitelisted function set, element removal — `removepoint`/`removeprim` on input-0, gated default-off behind the separate `allow_attrib_geoedit` consent — element construction/growth — `addpoint`/`addprim`/`addvertex`/`removevertex` on input-0, gated default-off behind the separate `allow_attrib_geogrow` consent — group writes) and **rejects** everything that enables RCE or I/O — *before* Houdini ever sees the string. It is **default-off**: it runs only when the user has set `allow_attrib_expr`, i.e. explicit consent.
  - The **reference handoff** (`vex_reference`) is read-only: the AI proposes correct VEX *text* for the user to paste into a wrangle by hand. The AI never executes it.

  The intent is **AI-assisted, human-gated**: the AI is led to *surface* a wrangle whenever one is the right tool and offer a suggestion grounded in `vex_reference`; the user decides and fires (either enabling the validated lane, or pasting by hand). That is the whole point of *safe* VEX — safe where every competitor ships unvalidated VEX/exec (i.e. RCE).

- **Gateway is not the boundary:** The gateway validates and forwards, but the security guarantee comes from the executor's fixed capability set. Even a fully compromised or misbehaving client can only invoke handlers that exist, with arguments that pass validation.

- **Path confinement is enforced twice:** Both the gateway and the executor `realpath`-confine every path to the working directory. This is deliberate redundancy — the executor does not assume the gateway ran, so a direct call to the loopback port is still confined.

- **Numeric parameters are clamped, not rejected:** Out-of-range numbers are pinned to the declared range rather than erroring. This avoids resource-exhaustion from an extreme value while keeping calls usable.

- **Loopback + shared token:** The executor listens on loopback only and authenticates with a shared session token. This assumes the gateway and executor share one trust domain on one machine. **Follow-up:** the token protects against other processes on the same host guessing the endpoint, but it is not a cross-trust-domain control — do not treat the loopback channel as a boundary between mutually distrustful parties.

- **Executor Python is loaded from disk:** The executor module is read from disk at arm time, not yet hash-pinned or baked into the gateway binary. A local attacker who can already write to the install could alter it. **Follow-up:** pinning the executor to a known digest (or embedding it in the binary) is planned; until then, treat write access to the install directory as equivalent to code execution.

- **Single-user local scope:** This tool is designed for one owner driving one Houdini session on their own machine. A multi-tenant or network-exposed posture would additionally require OS/container sandboxing and an egress policy — out of scope for a local single-user tool. Do not expose the gateway or the executor's loopback port to untrusted network access.

# Testing method

The standardized, repeatable way this project is tested.

The constraint that shapes everything: **CI runners have no Houdini license**, and the real data scale
(tens of GB of DEM/LIDAR) can never ship to a runner. So the method splits by *what a license-free runner
can honestly prove* versus *what needs a licensed `hython`*. The honesty rule is absolute: a test's
headline says exactly what it proves and nothing more. "Structurally verified" and "executes against a
mock" are not "produces correct geometry."

## The three tiers

### Tier 1 — Structural (cloud CI, deterministic) — the headline
Proves the whole tool surface is internally consistent and data-only, with no Houdini. This is the
strongest claim a reviewer can independently re-run in seconds.

- **Rust catalog integrity** — `cargo test` (gateway job): `emit_catalog_json`, `catalog_names_are_unique`,
  `catalog_never_exposes_rce_tools`, the `confine_path` traversal + symlink/junction cases, the inbound
  frame-cap tests, and the `vex_reference` topic-enum drift guard.
- **Catalog <-> executor parity** — `tests/executor/test_catalog_parity_cloud.py`: every AI-facing
  catalog tool has a registered executor endpoint; no off-catalog endpoint is reachable except a known
  control-plane op; no registered endpoint name is RCE-shaped (the Python-side data-only boundary). This
  makes `scripts/audit_registry_consistency.py` — previously hython-only because it did `import hou` —
  runnable on a bare runner, because endpoint registration happens at *decoration* time and never calls
  `hou`. A permissive stub `hou` is installed only when the real one is absent.
- **VEX validator red-team corpus** — `python houdini_executor/vex_validator.py`: the safe-VEX
  allowlist's must-pass / must-fail corpus (pure Python, no Houdini).
- **Confinement boundary** — `tests/executor/test_confine_cloud.py`: `confined_path()` accepts in-dir,
  rejects outside-absolutes, `../` traversal, and symlink-escape (the crux Windows vector), with `hou`
  stubbed.

### Tier 2 — Construct-smoke (cloud CI, best-effort) — breadth without a license
Proves every tool's handler *Python* runs end to end against a recording **mock `hou`** — node created,
parms set, inputs wired, a well-formed return assembled — catching import errors, attribute/signature
regressions, and param-handling bugs across the full surface. It does **not** cook geometry and does
**not** prove correctness.

- `tests/executor/_houmock.py` — the recording mock: a fake scene tree, nodes/parms/geometry/value-types
  rich enough for a data-only handler's construction path, real `hou.*` exception classes, and a call
  log. Deliberately permissive only on rarely-used top-level `hou` helpers; scene objects are *not*
  catch-all truthy, so real attribute-name bugs on the common path still surface.
- `tests/executor/test_construct_smoke_cloud.py` — synthesizes minimal valid params from each tool's
  catalog schema, resets the scene, calls the handler, and asserts a JSON-serializable return without an
  unexpected raise. Reports how many handlers execute clean against the mock. A small,
  individually-justified **allowlist** covers handlers that genuinely branch on a real cook result; the
  allowlist is reviewed — it is never a dumping ground to force green (a fixable failure means fix the
  mock, not allowlist it).

### Tier 3 — Behavioural (local, licensed hython) — correctness
Proves handlers cook real geometry correctly. Cannot run in cloud CI. Run before every push:

```
hython tests/executor/run_tests.py
```

- `tests/executor/test_confinement.py` — the write-confinement boundary against real Houdini.
- `tests/executor/test_a1_regressions.py` — locked-in regressions for real bugs the long-chain
  integration hunt found (cross-network operands, cloud voxel size, shader value routing, error
  surfacing, fracture count, NURBS polywire, vellum solve).
- Grows by promoting ad-hoc verification scripts into durable `test_*.py` here.

## What CI enforces today
The `executor` CI job runs Tier 1's Python checks + Tier 2 on every push and pull request; the `gateway`
job runs Tier 1's Rust checks. Tier 3 is the local pre-push gate. A change to `houdini_executor/` is not
done until Tier 3 is green locally.

## Adding coverage — the standard loop
1. New tool / handler: Tier 1 parity picks it up automatically (it is schema-derived). Confirm Tier 2
   construct-smoke stays green (enrich the mock if a new `hou` call is exercised; never force-allowlist).
2. A real cook bug found in the field or the integration hunt: write a Tier 3 `test_*.py` that reproduces
   the failing condition first, then fix, so it can never silently return.
3. Never headline a test as proving more than it does. Tier 1 = structural. Tier 2 = handler Python runs.
   Tier 3 = geometry is correct.

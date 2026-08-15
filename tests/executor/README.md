# Executor tests

The full testing method (three tiers, and why they split the way they do) is documented in
[docs/TESTING.md](../../docs/TESTING.md). This directory holds the executor's tests; the short version:

- **Tier 1 + Tier 2 run in cloud CI** with no Houdini license (the `executor` CI job). These are the
  `test_*_cloud.py` files below — they `import hou` against a stub / recording mock, so they run on a
  bare GitHub runner.
- **Tier 3 runs locally under a licensed `hython`** (it cooks real geometry). Run it before every push
  and after any change to `houdini_executor/`:

```
"C:\Program Files\Side Effects Software\Houdini21.0.671\bin\hython.exe" tests/executor/run_tests.py
```

`run_tests.py` discovers every `test_*.py` beside it, runs each in its own hython subprocess, and exits
non-zero if any fail. (The `*_cloud.py` files also run cleanly here — their stub only installs when the
real `hou` is absent, so under hython they exercise the real modules.)

## What's covered

Cloud CI (no license):
- **`test_catalog_parity_cloud.py`** (Tier 1) — every AI-facing catalog tool has a registered executor
  endpoint; no off-catalog endpoint is reachable except a known control-plane op; no endpoint name is
  RCE-shaped; catalog params are well-formed. Verifies the whole tool surface is data-only and in lockstep.
- **`test_confine_cloud.py`** (Tier 1) — `confined_path()` accepts in-dir, rejects outside-absolutes,
  `../` traversal, and symlink-escape (the crux Windows vector), with `hou` stubbed.
- **`test_construct_smoke_cloud.py`** (Tier 2) — calls every tool's handler with schema-synthesized
  params against the recording mock `hou` (`_houmock.py`), catching Python-level regressions across the
  surface. Proves the handler code runs; does NOT cook geometry or prove correctness.
- **`test_no_raw_vex_sinks.py`** (Tier 1) — static guard that no handler routes user text into a raw
  VEX/expression sink; enforces the data-only boundary at the source level (no arbitrary-code path).

Local hython (Tier 3, correctness):
- **`test_confinement.py`** — the write-confinement boundary against real Houdini: `confined_path()`
  accepts in-dir and rejects outside-WD absolutes + `../` traversal; `export_usd` stays confined and
  flattens sublayers (no write escaping the working directory).
- **`test_a1_regressions.py`** — locked-in regressions for the bugs the long-chain integration hunt
  found (cross-network operands, cloud voxel size, shader value routing, error surfacing, fracture
  count, NURBS polywire, vellum solve). Each reproduces the original failing condition.

## Adding a test

Drop a `test_<name>.py` here. It must: set `HMCP_WORKING_DIR`, add the repo root to `sys.path`, import
`hou` + `houdini_executor`, assert its checks, print a `RESULT:` line, and `sys.exit(1)` on any failure
(exit 0 on pass). Keep it fast and deterministic — no heavy sims. This is how the ~130 ad-hoc
verify scripts get promoted into durable, tracked coverage.

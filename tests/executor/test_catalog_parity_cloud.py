"""Cloud-CI-safe STRUCTURAL test: the AI-facing tool catalog and the executor's endpoint registry are
in exact lockstep, and neither exposes an arbitrary-code primitive — WITHOUT a Houdini license.

This is Tier 1 of the testing method: the deterministic structural gate that
verifies the whole tool surface in CI. It makes `scripts/audit_registry_consistency.py` (previously
hython-only, because it did `import hou` to load the handlers) runnable on a bare GitHub runner.

How it runs with no Houdini: endpoint registration happens at DECORATION time — `@endpoint("name")` is a
dict insert into `server._REGISTRY` and never calls `hou`. So we only need `import hou` to SUCCEED, not
to do anything. We stub `hou`/`hwebserver` with a permissive module (any attribute/call returns a benign
object) so every handler module imports and registers, then compare the registry against the committed
`reference/catalog.json` (emitted by `cargo test emit_catalog_json`, so no cargo run is needed here).

Three invariants — the same three the hython audit enforces, kept as a single source of truth by reusing
`server._REGISTRY` and `server._name_is_rce_shaped`:
  1. every catalog tool has a registered executor endpoint   (catalog - registry - gateway_native == {})
  2. no off-catalog endpoint is reachable but a known control-plane op (registry - catalog - control == {})
  3. no registered endpoint name carries an RCE-shaped token   (data-only boundary, Python side)
Plus a light, hou-free schema-sanity pass over the catalog params (kinds/choices/len well-formed).

Run:  python tests/executor/test_catalog_parity_cloud.py   (exit 0 = pass). Under real hython it uses the
real `hou` (the stub only installs when `hou` is absent), so run_tests.py picks it up locally too.
"""
import json
import os
import sys
import types

# --- permissive stub so `import hou` / `import hwebserver` succeed off a licensed box ---------------
# Only stub when absent: under hython the real modules are already imported and must win.
class _Permissive(types.ModuleType):
    """Any attribute access or call returns another permissive object — enough for handler modules to
    IMPORT (and thus register their @endpoint), never used to prove behaviour (that is Tier 2/3)."""
    def __getattr__(self, name):
        return _Permissive(self.__name__ + "." + name)

    def __call__(self, *args, **kwargs):
        return _Permissive(self.__name__ + "()")


for _name in ("hou", "hwebserver"):
    if _name not in sys.modules:
        sys.modules[_name] = _Permissive(_name)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, REPO)

from houdini_executor import server  # noqa: E402
from houdini_executor import handlers  # noqa: E402,F401  (import side effect: registers every @endpoint)

# Tools answered inside the Rust gateway (native::*) — no Python handler by design. Keep in sync with
# gateway/src/gateway.rs and scripts/audit_registry_consistency.py.
GATEWAY_NATIVE = {"acquire_terrain", "acquire_model", "node_reference", "vex_reference",
                  "recipe_reference", "capabilities", "batch"}
# Endpoints deliberately OFF the catalog (control-plane, reachable only by the authed loopback GUI).
# "reload" is dev-only and not registered in a shipped executor, so it is not expected here.
CONTROL_PLANE = {"teardown"}

FAIL = []


def chk(label, cond, detail=""):
    print(("  OK  " if cond else " FAIL ") + label + (("  -> " + detail) if detail and not cond else ""))
    if not cond:
        FAIL.append(label)


# ── load the committed catalog (no cargo needed) ───────────────────────────────────────────────────
with open(os.path.join(REPO, "reference", "catalog.json"), encoding="utf-8") as fh:
    catalog_doc = json.load(fh)
tools = catalog_doc["tools"]
catalog = {t["name"] for t in tools}
registry = set(server._REGISTRY)

print("catalog tools            :", len(catalog))
print("python _REGISTRY handlers:", len(registry))
print("gateway-native (no handler):", len(GATEWAY_NATIVE))
print()

# ── invariant 1: no catalog tool lacks a handler ───────────────────────────────────────────────────
missing_handler = sorted(catalog - registry - GATEWAY_NATIVE)
chk("every catalog tool has an executor endpoint", not missing_handler,
    "missing: " + ", ".join(missing_handler[:20]))

# ── invariant 2: no off-catalog endpoint is reachable (except known control-plane) ─────────────────
off_catalog = sorted(registry - catalog - CONTROL_PLANE)
chk("no off-catalog endpoint is reachable", not off_catalog,
    "off-catalog: " + ", ".join(off_catalog[:20]))

# ── invariant 3: no registered endpoint name is RCE-shaped (Python-side data-only boundary) ────────
rce = sorted(n for n in registry if server._name_is_rce_shaped(n))
chk("no registered endpoint name is RCE-shaped", not rce, "rce-shaped: " + ", ".join(rce))

# ── light, hou-free schema sanity over catalog params ──────────────────────────────────────────────
KNOWN_KINDS = {"Str", "Enum", "Bool", "Int", "Num", "NumVec", "NodePath", "FsPath", "VexSnippet", "OpList"}
schema_errs = []
for t in tools:
    for p in t.get("params", []):
        pid = "%s.%s" % (t["name"], p.get("name", "?"))
        kind = p.get("kind")
        if kind not in KNOWN_KINDS:
            schema_errs.append("%s: unknown kind %r" % (pid, kind))
        if kind == "Enum" and not p.get("choices"):
            schema_errs.append("%s: Enum without choices" % pid)
        if kind == "NumVec" and not isinstance(p.get("len"), int):
            schema_errs.append("%s: NumVec without integer len" % pid)
        if "name" not in p:
            schema_errs.append("%s: param missing name" % pid)
chk("all catalog params are well-formed", not schema_errs,
    "; ".join(schema_errs[:10]) + (" (+%d more)" % (len(schema_errs) - 10) if len(schema_errs) > 10 else ""))

print()
print("catalog<->registry parity:", "ALL GREEN" if not FAIL else "FAILURES: %s" % FAIL)
sys.exit(0 if not FAIL else 1)

"""Executable data-only-boundary audit: Rust catalog  <->  Python _REGISTRY consistency ([#138],
makes the _SECURITY_AUDIT.md invariant runnable). Run under hython (needs `hou` to import handlers):

    hython scripts/audit_registry_consistency.py            # audit the SHIPPED surface
    hython scripts/audit_registry_consistency.py --dev      # allow the dev-only 'reload' endpoint

The gateway's tools.rs catalog is the AI-facing allowlist; the Python _REGISTRY is what an authed
loopback caller actually reaches. Three invariants, all fail the build (exit 1) when violated:

  1. NO catalog tool lacks a handler   (catalog - registry - gateway_native)  -> broken MCP tool
  2. NO off-catalog endpoint is reachable that is not a known control-plane op  (registry - catalog -
     control_plane)                     -> a capability the AI path can't see but the port exposes
  3. NO endpoint name carries an RCE-shaped token  (server._BANNED_ENDPOINT_TOKENS)

This complements `cargo test` (Rust catalog <-> catalog.json) and `generate_docs.py --check`
(catalog.json <-> README); together the three cover the full 3-way.
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
DEV = "--dev" in sys.argv

# Tools answered inside the Rust gateway itself (native::*), so they have NO Python handler by design.
# Kept in sync with the dispatch chain in gateway/src/gateway.rs.
GATEWAY_NATIVE = {"acquire_terrain", "acquire_model", "node_reference", "vex_reference", "recipe_reference", "capabilities", "batch"}

# Endpoints intentionally present in _REGISTRY but deliberately OFF the tools.rs catalog (control-plane,
# reachable only by the authed loopback GUI, never by the AI/MCP path). "reload" is dev-only and is not
# registered at all unless dev_reload is set (so it is absent from a shipped audit).
CONTROL_PLANE = {"teardown"}
if DEV:
    CONTROL_PLANE.add("reload")

import hou  # noqa: E402,F401  (import side effect: makes the handlers importable)
from houdini_executor import server  # noqa: E402
from houdini_executor import handlers  # noqa: E402,F401  (registers every @endpoint into _REGISTRY)

registry = set(server._REGISTRY)
with open(os.path.join(REPO, "reference", "catalog.json"), encoding="utf-8") as fh:
    catalog = {t["name"] for t in json.load(fh)["tools"]}

missing_handler = sorted(catalog - registry - GATEWAY_NATIVE)
off_catalog = sorted(registry - catalog - CONTROL_PLANE)
banned = tuple(server._BANNED_ENDPOINT_TOKENS)
# Single source of truth: reuse the runtime guard's segment-boundary matcher so the audit and the
# fail-closed registration check can never drift (a banned verb trips only as a whole segment, so a
# real node name like `ocean_evaluate` is not a false positive — `evaluate` != `eval`).
rce = sorted(n for n in registry if server._name_is_rce_shaped(n))

print("catalog tools           :", len(catalog))
print("python _REGISTRY handlers:", len(registry))
print("gateway-native (no handler):", len(GATEWAY_NATIVE))
print("control-plane off-catalog :", sorted(CONTROL_PLANE))
print()

ok = True
def report(label, items, hint):
    global ok
    if items:
        ok = False
        print("FAIL  %s (%d): %s" % (label, len(items), ", ".join(items)))
        print("      -> %s" % hint)
    else:
        print("OK    %s" % label)

report("no catalog tool missing a handler", missing_handler,
       "a tools.rs entry has no @endpoint -> MCP tools/call would fail; add the handler or remove the ToolDef")
report("no off-catalog reachable endpoint", off_catalog,
       "an endpoint the loopback port exposes is neither a typed tool nor a known control-plane op; "
       "add it to tools.rs, add it to CONTROL_PLANE with justification, or remove it")
report("no RCE-shaped endpoint name", rce,
       "an endpoint name carries a banned token (%s) -> data-only boundary violation" % (banned,))

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)

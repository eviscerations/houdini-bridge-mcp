"""Cloud-CI-safe SECURITY test: confined_path traversal + symlink-escape, WITHOUT a Houdini license.

`server.py` imports `hou`/`hwebserver` at module load, so we STUB them in sys.modules first (the
"hou-mock" approach) — then import the real `server` and exercise the real `confined_path`, which itself
uses only os/pathlib. This makes the executor's last-line-of-defense path jail a VISIBLE cloud-CI check
(previously only the Rust `confine_path` ran in CI; the Python `confined_path` needed a licensed hython).

Runs on a bare GitHub runner: `python tests/executor/test_confine_cloud.py` (exit 0 = pass).
The full, hython-only boundary test stays in test_confinement.py."""
import os
import sys
import types
import tempfile

# --- stub the Houdini modules so `import hou` / `import hwebserver` succeed off a licensed box -------
for _name in ("hou", "hwebserver"):
    if _name not in sys.modules:
        sys.modules[_name] = types.ModuleType(_name)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from houdini_executor import server  # noqa: E402

FAIL = []


def chk(label, cond):
    print(("  OK  " if cond else " FAIL ") + label)
    if not cond:
        FAIL.append(label)


# Pin the confinement root deterministically (bypass arm.json / global WORKING_DIR across any host).
BASE = os.path.realpath(tempfile.mkdtemp(prefix="hmcp_ci_confine_"))
server._effective_working_dir = lambda: BASE  # noqa: SLF001 — test seam

# 1. accepts a path under the root
inside = os.path.join(BASE, "sub", "ok.txt")
try:
    chk("accepts in-dir path", server.confined_path(inside) == os.path.realpath(inside))
except Exception as e:  # noqa: BLE001
    chk("accepts in-dir path (raised %r)" % e, False)

# 2. rejects an absolute path outside the root
try:
    server.confined_path(os.path.realpath(os.sep))
    chk("rejects absolute-outside", False)
except PermissionError:
    chk("rejects absolute-outside", True)

# 3. rejects a parent-traversal escape
try:
    server.confined_path(os.path.join(BASE, "..", "escape.txt"))
    chk("rejects ../ traversal", False)
except PermissionError:
    chk("rejects ../ traversal", True)

# 4. rejects a SYMLINK-escape (the audit's crux Windows vector): a link inside the root that points
#    outside must not tunnel out — confined_path realpath-resolves the link before checking containment.
outside = os.path.realpath(tempfile.mkdtemp(prefix="hmcp_ci_outside_"))
link = os.path.join(BASE, "sneaky_link")
try:
    os.symlink(outside, link, target_is_directory=True)
    have_symlink = True
except (OSError, NotImplementedError, AttributeError):
    have_symlink = False  # no symlink privilege on this runner -> skip (do NOT fail the suite)
if have_symlink:
    try:
        server.confined_path(os.path.join(link, "escape.txt"))
        chk("rejects symlink-escape", False)
    except PermissionError:
        chk("rejects symlink-escape", True)
else:
    print("  SKIP symlink-escape (no symlink privilege on this host)")

# 5. rejects a path inside the bridge CONFIG / trust-root dir even when the working dir is an ANCESTOR of
#    it (the arm.json-rewrite vector, red-team #8). Simulate the mis-config by pointing _CONFIG_DIR at a
#    subdir of the working root, then confirm arm.json there is refused though it is "under" the root.
cfg_dir = os.path.join(BASE, ".houdini-bridge-mcp")
os.makedirs(cfg_dir, exist_ok=True)
server._CONFIG_DIR = os.path.realpath(cfg_dir)  # noqa: SLF001 — test seam (mimic working_dir ancestor)
try:
    server.confined_path(os.path.join(cfg_dir, "arm.json"))
    chk("rejects a path inside the config/trust-root dir", False)
except PermissionError:
    chk("rejects a path inside the config/trust-root dir", True)
# a normal in-dir path still works with the guard installed
try:
    ok_path = os.path.join(BASE, "normal", "ok.txt")
    chk("still accepts a normal in-dir path with the config guard on",
        server.confined_path(ok_path) == os.path.realpath(ok_path))
except Exception as e:  # noqa: BLE001
    chk("still accepts a normal in-dir path (raised %r)" % e, False)

print("confined_path cloud test:", "ALL GREEN" if not FAIL else "FAILURES: %s" % FAIL)
sys.exit(0 if not FAIL else 1)

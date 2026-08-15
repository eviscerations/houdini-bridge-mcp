"""Executor SECURITY-BOUNDARY functional test: confined_path + export write-confinement.

The gateway allowlists, but the executor NEVER trusts that alone -- confined_path() is the last line
of defense against a write escaping the working directory (realpath so junctions/symlinks can't
tunnel out). Previously only the Rust side's confine_path was tested; the live Python confined_path
that every export_* handler calls was not. This asserts it accepts in-dir paths and REJECTS escapes,
and that export_usd stays confined + flattens (the A1 confinement-escape regression)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
import hou  # noqa: E402,F401
from houdini_executor import server  # noqa: E402

FAIL = []


def chk(label, cond):
    print(("  OK  " if cond else " FAIL ") + label)
    if not cond:
        FAIL.append(label)


BASE = os.path.realpath(server._effective_working_dir())

# --- confined_path accepts a path under the working dir --------------------------------------
inside = os.path.join(BASE, "hmcp_test_confine_ok.txt")
try:
    resolved = server.confined_path(inside)
    chk("confined_path accepts a path under the working dir",
        os.path.realpath(resolved).startswith(os.path.realpath(BASE)))
except Exception as e:  # noqa: BLE001
    chk("confined_path accepts a path under the working dir (raised: %r)" % e, False)

# --- confined_path REJECTS an absolute path outside the working dir --------------------------
for outside in (r"C:\Windows\System32\hmcp_evil.txt", os.path.join(tempfile.gettempdir(), "hmcp_evil.txt")):
    raised = False
    try:
        server.confined_path(outside)
    except PermissionError:
        raised = True
    except Exception:  # noqa: BLE001 — any refusal is acceptable; a pass-through is the failure
        raised = True
    chk("confined_path REJECTS outside-WD path: %s" % outside, raised)

# --- confined_path REJECTS a ../ traversal escape --------------------------------------------
traversal = os.path.join(BASE, "..", "..", "hmcp_escape.txt")
raised = False
try:
    server.confined_path(traversal)
except Exception:  # noqa: BLE001
    raised = True
chk("confined_path REJECTS a ../ traversal escape", raised)

# --- confined_path REJECTS a junction inside the WD that points OUTSIDE it --------------------
# The Windows tunneling vector: a directory junction placed inside the working dir pointing outside
# must not let a read/write escape. realpath resolves the junction to its target, so the startswith
# check fails. (Junctions via `mklink /J` need no admin, unlike symlinks.)
import subprocess  # noqa: E402
jroot = os.path.join(BASE, "hmcp_test_confine_jroot")
joutside = os.path.join(tempfile.gettempdir(), "hmcp_confine_joutside_%d" % os.getpid())
jlink = os.path.join(jroot, "escape")
try:
    import shutil
    shutil.rmtree(jroot, ignore_errors=True)
    os.makedirs(jroot, exist_ok=True)
    os.makedirs(joutside, exist_ok=True)
    with open(os.path.join(joutside, "secret.txt"), "w") as f:
        f.write("top secret")
    made = subprocess.run(["cmd", "/C", "mklink", "/J", jlink, joutside],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if made:
        raised = False
        try:
            server.confined_path(os.path.join(jlink, "secret.txt"))
        except Exception:  # noqa: BLE001 — any refusal is acceptable; a pass-through is the failure
            raised = True
        chk("confined_path REJECTS a read tunneling through a junction that escapes the WD", raised)
    else:
        chk("confined_path junction-escape test SKIPPED (mklink /J unavailable)", True)
finally:
    subprocess.run(["cmd", "/C", "rmdir", jlink], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(jroot, ignore_errors=True)
    shutil.rmtree(joutside, ignore_errors=True)

# --- export_usd stays confined + flattens (A1 confinement-escape regression) -----------------
from houdini_executor.handlers import deliver as DEL  # noqa: E402

wd = os.path.join(BASE, "hmcp_test_confine_export")
if os.path.isdir(wd):
    import shutil
    shutil.rmtree(wd, ignore_errors=True)
os.makedirs(wd, exist_ok=True)
try:
    stage = hou.node("/stage") or hou.node("/").createNode("lopnet", "stage")
    geo = hou.node("/obj").createNode("geo", "confine_src")
    box = geo.createNode("box", "b")
    si = stage.createNode("sopimport", "confine_si")
    si.parm("soppath").set(box.path())
    pre = set()
    import glob, tempfile
    # Belt-and-suspenders leak probe: a portable "outside the working dir" location (the primary
    # confinement check is the realpath assertion below). No .usdnc sublayer must appear here.
    outside = tempfile.gettempdir()
    for p in glob.glob(outside + "/**/*.usdnc", recursive=True):
        pre.add(p)
    r = DEL.export_usd({"loppath": si.path(), "output": os.path.join(wd, "confine.usda")})
    chk("export_usd(sopimport) returns a path that exists", os.path.exists(r["output"]))
    chk("export_usd output stays under the working dir",
        os.path.realpath(r["output"]).startswith(os.path.realpath(BASE)))
    post = set(glob.glob(outside + "/**/*.usdnc", recursive=True))
    chk("export_usd leaks NO sublayer outside the working dir", len(post - pre) == 0)
finally:
    import shutil
    shutil.rmtree(wd, ignore_errors=True)

print("\nRESULT:", "ALL PASS" if not FAIL else ("FAILURES: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)

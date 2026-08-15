"""Executor functional test runner (LOCAL gate — requires a licensed Houdini/hython).

The gateway's security boundary is covered by `cargo test` (catalog_never_exposes_rce_tools,
confine_path traversal, emit_catalog_json). The PYTHON executor — the process that actually runs
handler code inside Houdini — was previously only `python -m compileall` checked in CI. This runner
functionally exercises the executor: confinement, endpoint registry integrity, and locked-in
regression tests for real bugs the long-chain hunt found. It cannot run in cloud CI (no Houdini), so
it is the developer/pre-push local gate:

    "C:\\Program Files\\Side Effects Software\\Houdini21.0.671\\bin\\hython.exe" tests/executor/run_tests.py

Discovers every `test_*.py` beside this file, runs each in its own hython subprocess (isolation), and
exits non-zero if any fail. Each test file must exit 0 on pass, non-zero on failure (print a summary).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
HYTHON = sys.executable  # this script is itself run under hython, so reuse it for the children


def discover():
    return sorted(
        os.path.join(HERE, f)
        for f in os.listdir(HERE)
        if f.startswith("test_") and f.endswith(".py")
    )


def main():
    tests = discover()
    if not tests:
        print("no test_*.py found in", HERE)
        return 1
    print("executor test suite — %d file(s) under %s\n" % (len(tests), HERE))
    failed = []
    for t in tests:
        name = os.path.basename(t)
        print("=" * 70)
        print("RUN", name)
        print("=" * 70)
        r = subprocess.run([HYTHON, t], cwd=os.path.dirname(os.path.dirname(HERE)))
        if r.returncode != 0:
            failed.append(name)
        print()
    print("=" * 70)
    if failed:
        print("EXECUTOR TESTS FAILED (%d/%d): %s" % (len(failed), len(tests), ", ".join(failed)))
        return 1
    print("EXECUTOR TESTS PASSED (%d/%d)" % (len(tests), len(tests)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

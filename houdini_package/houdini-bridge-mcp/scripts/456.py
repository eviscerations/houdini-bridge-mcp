"""houdini-bridge-mcp GUI startup bootstrap (scripts/456.py).

456.py is run at GUI startup AFTER the UI is available (123.py runs earlier,
before the UI), so this is the correct hook for code that touches hou.ui.

What this does:
  * Skips silently in non-GUI / hython sessions.
  * Defers the real work onto Houdini's event loop (via
    hou.ui.addEventLoopCallback) so hou.ui is fully ready, and removes that
    callback the first time it fires so the arm runs exactly once.
  * Reads ~/.houdini-bridge-mcp/arm.json. If it is missing or not enabled, it prints
    a line and stops. Otherwise it puts the configured executor_root on
    sys.path and calls houdini_executor.server.auto_arm(), which re-reads
    arm.json for working_dir/token/port and arms the in-Houdini executor.

Every failure is caught and printed so Houdini startup is never interrupted.
This file is shippable: it contains no personal paths, usernames, or
machine-specific values -- everything dynamic comes from arm.json at runtime.
"""

PREFIX = "[houdini-bridge-mcp]"


def _arm_once():
    """One-shot event-loop callback: read config and arm the executor."""
    import json
    import sys
    from pathlib import Path

    import hou

    # Run exactly once: unregister ourselves before doing any work.
    try:
        hou.ui.removeEventLoopCallback(_arm_once)
    except Exception:
        # Non-fatal: if we somehow can't unregister, the guards below still
        # make a second invocation harmless.
        pass

    try:
        config_path = Path.home() / ".houdini-bridge-mcp" / "arm.json"
        if not config_path.exists():
            print("%s no config at %s; executor not armed." % (PREFIX, config_path))
            return

        with open(str(config_path), "r", encoding="utf-8") as fh:
            config = json.load(fh)

        if config.get("enabled") is not True:
            print("%s config found but 'enabled' is not true; skipping arm." % PREFIX)
            return

        executor_root = config.get("executor_root")
        if not executor_root:
            print("%s config enabled but 'executor_root' is missing; cannot arm." % PREFIX)
            return

        print("%s config found; executor_root=%s" % (PREFIX, executor_root))

        if executor_root not in sys.path:
            sys.path.insert(0, executor_root)

        from houdini_executor.server import auto_arm
        auto_arm()
        print("%s executor armed." % PREFIX)
    except Exception as exc:
        print("%s arm failed: %r" % (PREFIX, exc))


def _bootstrap():
    """Register the deferred one-shot, guarding for a real GUI session."""
    try:
        import hou
    except Exception:
        # No hou module available -- nothing to do.
        return

    # Guard on hou.ui existence: skip silently in non-GUI / hython.
    if not hasattr(hou, "ui") or hou.ui is None:
        return
    try:
        if not hou.isUIAvailable():
            return
    except Exception:
        # If UI availability can't be determined, do not interfere with startup.
        return

    try:
        # Defer onto the event loop so hou.ui is fully ready before we arm.
        hou.ui.addEventLoopCallback(_arm_once)
    except Exception as exc:
        print("%s could not register startup callback: %r" % (PREFIX, exc))


_bootstrap()

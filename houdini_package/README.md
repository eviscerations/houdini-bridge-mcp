# houdini-bridge-mcp startup package

A Houdini 21 [package](https://www.sidefx.com/docs/houdini/ref/plugins.html)
that auto-arms an in-Houdini executor at GUI startup. It adds this package's
plugin folder to `HOUDINI_PATH` so its `scripts/456.py` runs after the UI is
available, then arms the executor from a per-user config file.

The package files are static and shippable: they contain **no** absolute
paths, usernames, or machine-specific values. Everything dynamic is read at
runtime from `~/.houdini-bridge-mcp/arm.json`.

## What's in this package

| File | Purpose |
| --- | --- |
| `houdini-bridge-mcp.json` | Package definition. Adds the sibling `houdini-bridge-mcp` folder to `HOUDINI_PATH` via `"hpath": "$HOUDINI_PACKAGE_PATH/../houdini-bridge-mcp"`. `$HOUDINI_PACKAGE_PATH` is the SideFX-documented variable for "the directory containing this package file", so the JSON is location-independent. |
| `houdini-bridge-mcp/scripts/456.py` | GUI startup bootstrap. `456.py` runs at startup once the UI is available (`123.py` runs earlier, before the UI). It defers work onto the event loop, reads `arm.json`, and arms the executor if enabled. |

## How it works

1. At GUI startup Houdini loads `houdini-bridge-mcp.json`, which puts the plugin
   folder on `HOUDINI_PATH`.
2. Houdini runs `scripts/456.py` from that folder. It skips silently in
   non-GUI / `hython` sessions.
3. `456.py` registers a one-shot `hou.ui.addEventLoopCallback`, which removes
   itself the first time it fires (so it runs exactly once) and then reads
   `~/.houdini-bridge-mcp/arm.json`.
4. If the config is missing or `"enabled"` is not `true`, it prints a
   `[houdini-bridge-mcp]` line and stops. Otherwise it inserts `executor_root` onto
   `sys.path` and calls `houdini_executor.server.auto_arm()`, which re-reads
   the config for `working_dir` / `token` / `port` and arms the executor.

The server starts non-blocking: in a graphical session
`hwebserver.run(...)` defaults `in_background` to `True` and returns
immediately, so Houdini startup is never held up.

### `arm.json` contract

`arm.json` is written by a separate GUI (not by this package):

```json
{
  "enabled": true,
  "working_dir": "<abs path>",
  "token": "<secret>",
  "port": 8765,
  "executor_root": "<abs dir CONTAINING the houdini_executor python package>"
}
```

## Where the files install to

The two files install into your Houdini user preferences directory
(`HOUDINI_USER_PREF_DIR`), which defaults to `%USERPROFILE%\Documents\houdini21.0`
on Windows (or wherever the `HOUDINI_USER_PREF_DIR` environment variable
points):

```
<HOUDINI_USER_PREF_DIR>/packages/houdini-bridge-mcp.json
<HOUDINI_USER_PREF_DIR>/houdini-bridge-mcp/scripts/456.py
```

Note the package `.json` goes inside `packages/`, while the plugin folder sits
one level up in the pref-dir root. `$HOUDINI_PACKAGE_PATH/../houdini-bridge-mcp`
resolves from `packages/` up to that sibling folder, so the same JSON works
regardless of where the pref dir lives.

The GUI's **Install package** action automates this copy; you can also copy the
two files by hand into the locations above.

## Uninstall

Delete `<HOUDINI_USER_PREF_DIR>/packages/houdini-bridge-mcp.json` (and, optionally, the
`<HOUDINI_USER_PREF_DIR>/houdini-bridge-mcp` folder). To disable temporarily, set
`"enabled": false` in `~/.houdini-bridge-mcp/arm.json`.

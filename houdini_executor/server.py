"""houdini_executor / server.py — the in-Houdini, data-only executor core.

Runs inside a live Houdini 21.0.671 session (armed by the gateway binary). Exposes ONLY a fixed
registry of typed, validated handlers over a loopback HTTP server. There is no arbitrary-code path
(no exec, no generic node driver, no raw VEX) — that is the security boundary.

Config comes entirely from the environment the gateway sets, so NOTHING is hardcoded to a machine:
    HMCP_WORKING_DIR  the one directory this process may read/write (realpath-confined)
    HMCP_TOKEN        shared session token (X-HMCP-Token header)
    HMCP_PORT         loopback port (default 8765)

This module is the spine only: bootstrap, auth, path confinement, main-thread marshalling, the
handler registry, request-size cap, plus the two proof endpoints (health, scene_info). Stage
handlers live in `handlers/` and register themselves via the `endpoint` decorator.
"""

import os
import sys
import json
import queue
import threading
import traceback
import secrets

import hou
import hwebserver

# ── config from the environment (never hardcoded) ────────────────────────────
WORKING_DIR = os.path.realpath(os.environ.get("HMCP_WORKING_DIR", os.getcwd()))
# The bridge config / trust-root directory (arm.json + token). confined_path() keeps it off-limits to
# data tools regardless of the working dir, so a tool can never reach arm.json to redirect confinement.
_CONFIG_DIR = os.path.realpath(os.path.join(os.path.expanduser("~"), ".houdini-bridge-mcp"))
TOKEN = os.environ.get("HMCP_TOKEN", "")
PORT = int(os.environ.get("HMCP_PORT", "8765"))
# H1 transport gate: hwebserver.run() can't bind loopback-only, so a Windows Firewall rule on the
# executor port is the transport boundary (Windows exempts loopback from WFP filtering; explicit rules
# override defaults). arm() refuses to start unless the rule matching NETWORK_MODE exists.
#   "loopback" (default): an inbound-BLOCK rule — nothing off-box reaches the executor.
#   "lan": a scoped inbound-ALLOW rule (local subnet only) — a deliberate studio opt-in; token still gates.
# allow_insecure_bind bypasses the gate entirely (no firewall management; binds all interfaces).
NETWORK_MODE = "loopback"
ALLOW_INSECURE_BIND = False
# Dev-loop hot-reload of handler modules. OFF by default so the "reload" endpoint is NOT registered in
# a shipped/release executor (release hardening [#138]): least-surface — no loopback caller can trigger
# an importlib.reload of handler code. A developer knowingly re-enables it with "dev_reload": true in
# ~/.houdini-bridge-mcp/arm.json (keeps the hot-reload dev-loop without restarting Houdini).
DEV_RELOAD = False
MAX_BODY_BYTES = 1_048_576  # 1 MB request-body cap (DoS guard)
MAIN_THREAD_TIMEOUT = 60.0

VERSION = "0.1.0"


# ── main-thread marshalling ──────────────────────────────────────────────────
# hou.* is not thread-safe. Worker threads never touch it directly; they enqueue a job that a
# pump drains on Houdini's main thread. Timeout cancels the job so a worker always returns and a
# late-completing job never mutates the scene after we've reported failure.
_JOBS: "queue.Queue" = queue.Queue()


def _pump():
    while True:
        try:
            job = _JOBS.get_nowait()
        except queue.Empty:
            return
        if job["cancelled"]:
            continue
        try:
            job["result"] = job["fn"](*job["args"])
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller as an error envelope
            job["error"] = exc
        finally:
            job["done"].set()


def run_on_main(fn, *args, timeout=MAIN_THREAD_TIMEOUT):
    job = {"fn": fn, "args": args, "result": None, "error": None,
           "done": threading.Event(), "cancelled": False}
    _JOBS.put(job)
    if not job["done"].wait(timeout):
        job["cancelled"] = True
        raise TimeoutError(f"main-thread job exceeded {timeout}s")
    if job["error"] is not None:
        raise job["error"]
    return job["result"]


# ── security helpers ─────────────────────────────────────────────────────────
def _header(request, name):
    """Case-insensitive header lookup. hwebserver's `request.headers()` is a METHOD returning a
    dict — NOT an attribute; `request.headers.get(...)` raises AttributeError."""
    want = name.lower()
    for k, v in request.headers().items():
        if k.lower() == want:
            return v
    return None


def _authed(request) -> bool:
    supplied = _header(request, "X-HMCP-Token") or ""
    return bool(TOKEN) and secrets.compare_digest(str(supplied), str(TOKEN))


# Live confinement root: single source of truth is ~/.houdini-bridge-mcp/arm.json's working_dir (the GUI
# writes it on Apply). mtime-cached; falls back to the arm-time WORKING_DIR global if the config is
# absent/unreadable/invalid, so confinement never silently opens up.
_WD_CACHE = None  # tuple(mtime, resolved_dir)

def _effective_working_dir():
    global _WD_CACHE
    import pathlib
    cfg = pathlib.Path.home() / ".houdini-bridge-mcp" / "arm.json"
    try:
        mtime = cfg.stat().st_mtime
    except OSError:
        return WORKING_DIR
    if _WD_CACHE is not None and _WD_CACHE[0] == mtime:
        return _WD_CACHE[1]
    wd = WORKING_DIR
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        cand = os.path.realpath(str(data["working_dir"]))
        if os.path.isdir(cand):
            wd = cand
    except Exception:  # noqa: BLE001 — any parse/type error -> keep the safe fallback
        wd = WORKING_DIR
    _WD_CACHE = (mtime, wd)
    return wd

def confined_path(path: str) -> str:
    """Resolve `path` and require it to sit under WORKING_DIR. Raises on escape.

    Uses realpath so junctions/symlinks can't tunnel outside the root. This is the last line of
    defense — the gateway also allowlists, but the executor never trusts that alone.
    """
    # Normalize a Windows extended-length prefix — the gateway's realpath (Rust canonicalize) may
    # prepend \\?\, which is a valid path but wouldn't match the un-prefixed WORKING_DIR.
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    resolved = os.path.realpath(path)
    # The confinement ROOT OF TRUST — arm.json (which names the working dir) and the auth token live in
    # ~/.houdini-bridge-mcp/. It is NEVER reachable through a data tool, even if the working dir is
    # mis-configured to an ancestor of it: that closes the arm.json-rewrite escape (a tool that could
    # read/replace arm.json could redirect the working dir anywhere). The executor reads its own config
    # directly (not via this function), so this guard never blocks legitimate config access.
    cfg_root = _CONFIG_DIR + os.sep
    if resolved == _CONFIG_DIR or resolved.startswith(cfg_root):
        raise PermissionError(f"path is inside the bridge config directory (off-limits to tools): {path}")
    base = _effective_working_dir()
    root = base + os.sep
    if resolved != base and not resolved.startswith(root):
        raise PermissionError(f"path outside working directory: {path}")
    return resolved


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _jsonable(obj):
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return str(obj)


# ── node helpers (handlers operate on scene-graph paths) ─────────────────────
def resolve_node(path: str):
    n = hou.node(path)
    if n is None:
        raise ValueError(f"no such node: {path}")
    return n


def child_after(input_path: str, ntype: str, name=None):
    """Create `ntype` in the input's parent, wired after it. The scene-construction primitive."""
    src = resolve_node(input_path)
    try:
        if isinstance(src, hou.ObjNode):
            disp = src.displayNode() or src.renderNode()
            if disp is not None:
                src = disp
    except Exception:
        pass
    parent = src.parent()
    n = parent.createNode(ntype, name) if name else parent.createNode(ntype)
    n.setInput(0, src)
    n.moveToGoodPosition()
    # [D2] SHOW THE NEWEST RESULT. A build-then-look loop is invisible unless the tail SOP is the
    # displayed one — each new node in a chain otherwise buries the result upstream. Make this tail the
    # display + render SOP (Houdini auto-clears the flag from the prior tail), and ensure the containing
    # object is itself displayed. Best-effort: a flag-set failure must never break the build.
    try:
        n.setDisplayFlag(True)
        n.setRenderFlag(True)
    except Exception:  # noqa: BLE001 — not all node types carry these flags
        pass
    try:
        obj = n.parent()
        if isinstance(obj, hou.ObjNode):
            obj.setDisplayFlag(True)
    except Exception:  # noqa: BLE001
        pass
    return n


def bridge_into(node, dest_parent, xformtype=0, name_hint=None):
    """Return a SOP inside `dest_parent` (a SOP network) carrying `node`'s geometry.

    If `node` already lives in `dest_parent`, it is returned unchanged. Otherwise an
    `object_merge` is inserted into `dest_parent` that references `node` by path -- the
    Houdini idiom for pulling a geometry stream across `/obj` networks (a plain
    `setInput` cannot wire across networks). Same-user, same-scene, path reference only:
    no geometry copy, no exec. `xformtype` is the object_merge menu index:
        0 = none            -> source's own local space (template/stamp semantics)
        1 = Into This Object -> world-correct placement for scene assembly
    """
    if node.parent().path() == dest_parent.path():
        return node
    om = dest_parent.createNode("object_merge", (name_hint or node.name()) + "_ref")
    try:
        om.parm("numobj").set(1)
        om.parm("objpath1").set(node.path())
        p_en = om.parm("enable1")
        if p_en is not None:
            p_en.set(1)
        p_xf = om.parm("xformtype")
        if p_xf is not None:
            p_xf.set(int(xformtype))
    except Exception:
        pass
    om.moveToGoodPosition()
    return om


def bridge_input(node, path, index=1, xformtype=0, name_hint=None):
    """Wire the geometry at `path` into `node`'s input `index`, bridging across /obj networks
    when needed. This is the correct replacement for a bare `node.setInput(index, resolve_node(path))`
    on a SECOND operand: a plain `setInput` cannot wire a SOP across geo networks and cannot accept
    an ObjNode, so passing a separately-created operand (the normal case) raises OperationFailed.

    Two behaviours a raw setInput lacks and this restores (mirroring `child_after`'s input0 path):
      * ObjNode -> display/render SOP unwrap (accept an /obj path, not only its inner SOP);
      * cross-network bridge via `bridge_into` (object_merge reference; path-only, no copy, no exec).
    Safe superset: when the operand already shares `node`'s parent, `bridge_into` returns it
    unchanged, so same-network wiring is byte-for-byte what it was before. Returns the wired ref."""
    src = resolve_node(path)
    try:
        if isinstance(src, hou.ObjNode):
            disp = src.displayNode() or src.renderNode()
            if disp is not None:
                src = disp
    except Exception:
        pass
    ref = bridge_into(src, node.parent(), xformtype=xformtype, name_hint=name_hint)
    node.setInput(index, ref)
    return ref


def out_context():
    """The /out ROP network (created on demand)."""
    return hou.node("/out") or hou.node("/").createNode("ropnet", "out")


def stage_context():
    """The /stage Solaris (LOP) network — the USD-stage authoring context (created on demand)."""
    return hou.node("/stage") or hou.node("/").createNode("lopnet", "stage")


def cop_context():
    """The Copernicus COP network (/obj/cops) — the shared 2D image-processing context, created on
    demand (mirrors stage_context/out_context). COP *generator* handlers create their node here; COP
    *filter* handlers chain onto an existing COP node with child_after (which works across any
    network). Category of children is `Cop` (the H20.5+ Copernicus set), not legacy `Cop2`."""
    return hou.node("/obj/cops") or hou.node("/obj").createNode("copnet", "cops")


# ── handler registry ─────────────────────────────────────────────────────────
# Handlers register at import time; all registration must happen BEFORE arm() calls
# hwebserver.run() (routes lock at run()).
_REGISTRY = {}  # name -> {"fn": callable, "auth": bool}


def endpoint(name, auth=True):
    def deco(fn):
        _REGISTRY[name] = {"fn": fn, "auth": auth}
        return fn
    return deco


# Tokens that must never NAME a registered endpoint — the shapes of an arbitrary-code primitive
# (exec/eval/raw VEX/HScript/generic node driver). Matched at underscore-SEGMENT boundaries (see
# _name_is_rce_shaped), so a banned verb only trips as a whole segment: `eval` blocks an endpoint
# named `eval` but NOT a legitimate node name like `ocean_evaluate`. None of the data-only handler
# names name these. Kept in sync with the gateway's catalog_never_exposes_rce_tools banned set.
_BANNED_ENDPOINT_TOKENS = ("exec", "eval", "wrangle", "hscript", "node_op",
                           "run_code", "os_system", "python_")


def _name_is_rce_shaped(name):
    """True if `name` NAMES an arbitrary-code primitive. Match at underscore-segment boundaries so a
    banned verb only trips when it is a whole segment (or a contiguous run of segments for compound
    tokens like ``node_op``): ``eval`` blocks an endpoint literally named ``eval`` but NOT a real
    node name like ``ocean_evaluate`` (``evaluate`` != ``eval``). The actual security boundary is the
    data-only executor + allowlist; this is the naming-hygiene canary that keeps an RCE-shaped name
    from drifting in — it must not false-positive on legitimate English/node names."""
    hay = "_" + name.lower() + "_"
    return any(("_" + tok.strip("_") + "_") in hay for tok in _BANNED_ENDPOINT_TOKENS)


def _assert_no_rce_endpoints():
    """Fail-closed data-only guard: refuse to arm if any registered endpoint names an arbitrary-code
    primitive. The executor registry (not the gateway catalog) is the boundary an attacker who
    reaches the loopback port sees, so the invariant is re-asserted here."""
    offenders = sorted(n for n in _REGISTRY if _name_is_rce_shaped(n))
    if offenders:
        raise RuntimeError("data-only boundary violation: RCE-shaped endpoint(s) registered: "
                           + ", ".join(offenders))


def _dispatch(name, request):
    spec = _REGISTRY.get(name)
    if spec is None:
        return hwebserver.Response(json.dumps({"error": "unknown endpoint"}),
                                   status=404, content_type="application/json")
    if spec["auth"] and not _authed(request):
        return hwebserver.Response(json.dumps({"error": "unauthorized"}),
                                   status=403, content_type="application/json")
    body = request.body() or b""
    if len(body) > MAX_BODY_BYTES:
        return hwebserver.Response(json.dumps({"error": "request too large"}),
                                   status=413, content_type="application/json")
    try:
        params = json.loads(body) if body else {}
    except ValueError:
        return hwebserver.Response(json.dumps({"error": "invalid json"}),
                                   status=422, content_type="application/json")
    try:
        result = run_on_main(spec["fn"], params)
        return hwebserver.Response(json.dumps({"ok": True, "result": _jsonable(result)}),
                                   content_type="application/json")
    except (PermissionError, ValueError) as exc:
        return hwebserver.Response(json.dumps({"ok": False, "error": str(exc)}),
                                   status=400, content_type="application/json")
    except Exception as exc:  # noqa: BLE001
        # The full traceback (executor source file paths + module layout) is HOST-LAYOUT RECON — log it
        # locally for debugging but do NOT forward it to the caller. The handler-authored `str(exc)`
        # message stays (it is the actionable, non-sensitive part the AI needs to self-correct).
        sys.stderr.write("executor handler error in %r:\n%s\n" % (name, traceback.format_exc()))
        sys.stderr.flush()
        return hwebserver.Response(
            json.dumps({"ok": False, "error": str(exc)}),
            status=500, content_type="application/json")


# ── proof endpoints ──────────────────────────────────────────────────────────
@endpoint("scene_info")
def _scene_info(params):
    obj = hou.node("/obj")
    return {
        "hip": hou.hipFile.name(),
        "frame": hou.frame(),
        "houdini": hou.applicationVersionString(),
        "obj_children": [n.name() for n in (obj.children() if obj else [])],
    }


@endpoint("list_working_dir")
def _list_working_dir(params):
    """List files + folders in the confined WORKING DIRECTORY so an agent can DISCOVER what assets
    exist before importing — the answer to 'can you see my file?'. READ-ONLY and confined: it can only
    see inside the working dir (never elsewhere on disk, never the bridge config dir), and it resolves
    every entry through realpath so a symlink pointing outside is skipped, not followed. Pairs with the
    import tools (import_geo / obj_importer / import_pointcloud): list, then hand the exact path to the
    importer. `subdir` scopes to a relative subfolder; `pattern` is a glob on the file NAME (e.g.
    '*.obj'); `recursive` walks subfolders (depth-capped); results are capped and `truncated` flags it.
    Folders are always listed (for navigation); files are filtered by `pattern`. Paths are RELATIVE to
    the working-dir root."""
    import fnmatch
    base = _effective_working_dir()
    sub = params.get("subdir")
    start = confined_path(os.path.join(base, str(sub))) if sub else base
    if not os.path.isdir(start):
        raise ValueError("not a directory in the working dir: %r" % (sub or "."))
    pattern = str(params.get("pattern") or "*")
    recursive = bool(params.get("recursive", False))
    max_entries = int(clamp(int(params.get("max_entries", 500) or 500), 1, 5000))
    max_depth = int(clamp(int(params.get("max_depth", 4) or 4), 1, 20))

    base_root = base + os.sep
    cfg_root = _CONFIG_DIR + os.sep

    def _inside(fp):
        # realpath-confine each entry: never report a symlink that escapes the working dir or reaches
        # the bridge config dir (mirrors confined_path, but skips rather than raises).
        rp = os.path.realpath(fp)
        if rp == _CONFIG_DIR or rp.startswith(cfg_root):
            return False
        return rp == base or rp.startswith(base_root)

    def rel(fp):
        return os.path.relpath(fp, base).replace("\\", "/")

    entries = []
    truncated = False
    if recursive:
        start_depth = start.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(start):  # followlinks=False (default): no symlink dirs
            if (dirpath.rstrip(os.sep).count(os.sep) - start_depth) >= max_depth:
                dirnames[:] = []
            for fn in sorted(filenames):
                if not fnmatch.fnmatch(fn, pattern):
                    continue
                fp = os.path.join(dirpath, fn)
                if not _inside(fp):
                    continue
                try:
                    size = os.path.getsize(fp)
                except OSError:
                    size = None
                entries.append({"path": rel(fp), "size_bytes": size, "is_dir": False})
                if len(entries) >= max_entries:
                    truncated = True
                    break
            if truncated:
                break
    else:
        for name in sorted(os.listdir(start)):
            fp = os.path.join(start, name)
            is_dir = os.path.isdir(fp)
            if not is_dir and not fnmatch.fnmatch(name, pattern):
                continue
            if not _inside(fp):
                continue
            try:
                size = None if is_dir else os.path.getsize(fp)
            except OSError:
                size = None
            entries.append({"path": rel(fp), "size_bytes": size, "is_dir": is_dir})
            if len(entries) >= max_entries:
                truncated = True
                break

    return {"root": base.replace("\\", "/"), "subdir": (sub or None), "pattern": pattern,
            "recursive": recursive, "count": len(entries), "truncated": truncated, "entries": entries}


@endpoint("clear_scene")
def _clear_scene(params):
    """Start fresh in the /obj network WITHOUT a destructive File->New. mode='hide' (DEFAULT,
    non-destructive + reversible) turns the display flag OFF on every /obj object so the viewport
    clears but the nodes remain; mode='delete' REMOVES the /obj objects (destructive — the same as
    deleting each one). `keep` is a comma-separated list of object names to leave untouched (e.g. the
    one thing you're keeping). This only touches /obj — it never clears the hip file itself and never
    reaches unsaved work elsewhere. Returns {mode, affected, kept, remaining}."""
    mode = str(params.get("mode", "hide")).lower()
    if mode not in ("hide", "delete"):
        raise ValueError("mode must be 'hide' (non-destructive, default) or 'delete'")
    keep = {s.strip() for s in str(params.get("keep", "")).split(",") if s.strip()}
    obj = hou.node("/obj")
    if obj is None:
        return {"mode": mode, "affected": [], "kept": [], "remaining": []}
    affected, kept, failed = [], [], []
    for child in list(obj.children()):
        nm = child.name()
        if nm in keep:
            kept.append(nm)
            continue
        try:
            if mode == "delete":
                child.destroy()
            elif isinstance(child, hou.ObjNode):
                child.setDisplayFlag(False)
            affected.append(nm)
        except Exception as exc:  # noqa: BLE001 — keep going; report failures rather than aborting
            failed.append({"name": nm, "error": str(exc)})
    remaining = [c.name() for c in (obj.children() if obj.children() is not None else [])]
    out = {"mode": mode, "affected": affected, "kept": kept, "remaining": remaining}
    if failed:
        out["failed"] = failed
    return out


@endpoint("read_network")
def _read_network(params):
    """Read a network's STRUCTURE as text — the durable, token-cheap map a driving agent needs to rebuild
    its picture of a big node graph (especially after a context compaction) WITHOUT spending budget on a
    screenshot. For the network at `path` (default /obj) it returns each child node's name, type, INPUT
    WIRING (the sibling feeding each input slot, so the whole DAG is reconstructable), display/render/
    bypass/template flags, and child-count (is it a divable subnet). READ-ONLY and NO COOK — pure
    topology. Point it at /obj to list the objects, or at /obj/<geo> to read the SOP chain wire-by-wire.
    recursive=true descends into child subnets (depth-capped). Complements capture_ui panel=network (the
    visual) with the structural readout; use find_error_nodes for cook-error state.

    params=true ALSO dumps, per node, the NON-DEFAULT parameters (only the ones the artist changed off
    default — the actual choices, so the readout stays token-cheap) with their evaluated values, any
    EXPRESSIONS / channel references verbatim (the ch("../ctrl") links that drive rigs), and the node's
    comment. That turns the topology map into a readable recipe — the fast way to reverse-engineer what an
    existing/in-progress network actually DOES, not just how it's wired. Still READ-ONLY, still NO COOK.
    Long/code values are truncated; per-node param count is capped (both reported when they bite)."""
    root_path = str(params.get("path") or "/obj")
    root = hou.node(root_path)
    if root is None:
        raise ValueError("no such network: %r (nothing to read)" % root_path)
    recursive = bool(params.get("recursive", False))
    want_params = bool(params.get("params", False))
    max_depth = int(clamp(int(params.get("max_depth", 3) or 3), 1, 12))
    max_nodes = int(clamp(int(params.get("max_nodes", 300) or 300), 1, 3000))
    _VAL_CAP = 160          # truncate any single value/expression string past this (code parms, long paths)
    _PARMS_PER_NODE = 60    # cap non-default parms surfaced per node (report truncation)
    state = {"n": 0, "truncated": False}

    def _flags(n):
        f = {}
        for attr, key in (("isDisplayFlagSet", "display"), ("isRenderFlagSet", "render"),
                          ("isBypassed", "bypass"), ("isTemplateFlagSet", "template")):
            fn = getattr(n, attr, None)
            if fn is None:
                continue
            try:
                v = bool(fn())
            except Exception:  # noqa: BLE001 — flag not applicable to this node type
                continue
            # keep it compact: always surface display/render; only surface bypass/template when ON
            if key in ("bypass", "template") and not v:
                continue
            f[key] = v
        return f

    def _inputs(n):
        out = []
        try:
            for inp in n.inputs():
                out.append(inp.name() if inp is not None else None)
        except Exception:  # noqa: BLE001
            pass
        return out

    def _cap(v):
        s = v if isinstance(v, str) else str(v)
        if len(s) > _VAL_CAP:
            return s[:_VAL_CAP] + "…(+%d)" % (len(s) - _VAL_CAP)
        return s

    def _node_params(n):
        """Non-default parms only (the artist's actual choices). Each surfaced as its evaluated value,
        OR — when the parm holds an expression — the raw expression string (the channel-ref link is the
        signal, more useful than the evaluated number). Read-only; every access guarded."""
        pd = {}
        truncated = False
        try:
            plist = n.parms()
        except Exception:  # noqa: BLE001
            return pd, False, None
        for p in plist:
            try:
                if p.isAtDefault():
                    continue
            except Exception:  # noqa: BLE001
                continue
            if len(pd) >= _PARMS_PER_NODE:
                truncated = True
                break
            try:
                expr = p.expression()          # raises if no expression
                pd[p.name()] = {"expr": _cap(expr)}
                continue
            except Exception:  # noqa: BLE001 — no expression on this parm; fall through to the value
                pass
            try:
                val = p.eval()
                pd[p.name()] = _cap(val) if isinstance(val, str) else val
            except Exception as exc:  # noqa: BLE001
                pd[p.name()] = "<eval error: %s>" % (str(exc)[:60])
        comment = None
        try:
            c = n.comment()
            if c:
                comment = _cap(c)
        except Exception:  # noqa: BLE001
            pass
        return pd, truncated, comment

    def _walk(net, depth):
        nodes = []
        try:
            children = net.children()
        except Exception:  # noqa: BLE001
            return nodes
        for c in children:
            if state["n"] >= max_nodes:
                state["truncated"] = True
                break
            state["n"] += 1
            try:
                kids = c.children()
            except Exception:  # noqa: BLE001
                kids = ()
            entry = {"name": c.name(), "type": c.type().name(),
                     "inputs": _inputs(c), "flags": _flags(c), "children": len(kids)}
            if want_params:
                pd, ptrunc, comment = _node_params(c)
                if pd:
                    entry["parms"] = pd
                if ptrunc:
                    entry["parms_truncated"] = True
                if comment:
                    entry["comment"] = comment
            if recursive and kids and depth < max_depth:
                entry["nodes"] = _walk(c, depth + 1)
            nodes.append(entry)
        return nodes

    tree = _walk(root, 1)
    return {"path": root.path(), "type": root.type().name(),
            "child_count": len(root.children()), "returned": state["n"],
            "truncated": state["truncated"], "recursive": recursive, "nodes": tree}


# NOT decorated with @endpoint at import time — DEV-ONLY. arm() registers it into _REGISTRY only when
# DEV_RELOAD is true (arm.json "dev_reload"), so a release executor never exposes it (release hardening
# [#138]). It is also absent from the gateway's tools.rs catalog, so the AI/MCP path could never reach
# it regardless; this gate additionally closes it on the authed-loopback surface for a shipped build.
def _reload(params):
    """Hot-reload every handler module so code fixes take effect WITHOUT restarting Houdini.
    Re-running each module's @endpoint decorators overwrites its _REGISTRY entries in place; the
    single /tool prefix route resolves handlers from _REGISTRY at request time, so no route
    re-registration is needed. This `server` module is never reloaded (it owns _REGISTRY and this
    endpoint). Runs on the main thread (dispatched like any endpoint). DEV-ONLY (see gate above)."""
    import importlib
    reloaded = []
    for modname in list(sys.modules):
        mod = sys.modules.get(modname)
        if modname.startswith("houdini_executor.handlers.") and mod is not None:
            try:
                importlib.reload(mod)
                reloaded.append(modname)
            except Exception as exc:  # noqa: BLE001
                return {"reloaded": sorted(reloaded), "failed": modname, "error": str(exc)}
    return {"reloaded": sorted(reloaded), "registry": len(_REGISTRY)}


# ── H1 transport gate (Windows Firewall) ─────────────────────────────────────
def firewall_rule_name(port, mode="loopback") -> str:
    """Name of the firewall rule that scopes the executor port for the given network_mode.
    loopback -> the inbound-block rule; lan -> the scoped inbound-allow rule. Kept in exact sync
    with scripts/harden-firewall.ps1 (which creates rules by these names)."""
    if mode == "lan":
        return f"houdini-bridge-mcp-allow-lan-{int(port)}"
    return f"houdini-bridge-mcp-deny-inbound-{int(port)}"


def _firewall_rule_present(name) -> bool:
    """True iff a Windows Firewall rule with this exact name exists. `netsh ... show rule name=<n>`
    exits 0 when present, non-zero ("No rules match") when absent. Non-Windows: True (this is a
    Windows control; the tool is Windows-first, other platforms are out of scope for the gate)."""
    if os.name != "nt":
        return True
    import subprocess
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=%s" % name],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode == 0
    except Exception:  # noqa: BLE001 — any failure to verify => treat as ABSENT (fail-closed)
        return False


def firewall_gate_satisfied(port, mode) -> bool:
    """The transport gate is satisfied when the firewall rule matching `mode` exists:
    loopback => an inbound-block rule blocks all off-box reach (loopback stays WFP-exempt);
    lan      => a scoped local-subnet allow rule is present (a deliberate, scoped opening).
    Either way hwebserver's all-interfaces bind is constrained by a rule the operator created, not
    left open by default. Token auth applies in both modes."""
    return _firewall_rule_present(firewall_rule_name(port, mode))


# ── arm / teardown ───────────────────────────────────────────────────────────
def auto_arm():
    """Startup entry (called by the Houdini package's 456.py). Reads ~/.houdini-bridge-mcp/arm.json and
    arms if enabled. A safe no-op when the config is absent or disabled; never raises into Houdini
    startup. Overrides the import-time globals from the config, since at auto-arm time the gateway
    env is not set (Houdini was launched by the user, not the gateway)."""
    global WORKING_DIR, TOKEN, PORT, ALLOW_INSECURE_BIND, NETWORK_MODE, DEV_RELOAD
    import pathlib
    cfg = pathlib.Path.home() / ".houdini-bridge-mcp" / "arm.json"
    try:
        if not cfg.exists():
            print("[houdini-bridge-mcp] no arm.json; executor not armed"); return
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[houdini-bridge-mcp] arm.json unreadable: {exc}"); return
    if not data.get("enabled"):
        print("[houdini-bridge-mcp] arm.json disabled; executor not armed"); return
    try:
        WORKING_DIR = os.path.realpath(data["working_dir"])
        TOKEN = str(data["token"])
        PORT = int(data.get("port", PORT))
        ALLOW_INSECURE_BIND = bool(data.get("allow_insecure_bind", False))
        NETWORK_MODE = "lan" if str(data.get("network_mode", "loopback")).lower() == "lan" else "loopback"
        DEV_RELOAD = bool(data.get("dev_reload", False))  # dev-only hot-reload endpoint gate [#138]
    except Exception as exc:  # noqa: BLE001
        print(f"[houdini-bridge-mcp] arm.json invalid: {exc}"); return
    try:
        arm()
        print(f"[houdini-bridge-mcp] auto-armed on {PORT}; working_dir={WORKING_DIR}")
    except RuntimeError as exc:  # not armed: already-running, OR the H1 firewall gate refused
        print(f"[houdini-bridge-mcp] not armed: {exc}")


def arm():
    """Register all routes and start the loopback server. Blocks (call from the Houdini shell)."""
    if getattr(hou.session, "_HMCP_RUNNING", False):
        raise RuntimeError("executor already armed; run teardown() first")

    # H1 transport gate — checked BEFORE marking running, so a refusal leaves a clean retry state.
    # hwebserver.run() cannot bind loopback-only; without the Windows Firewall rule matching
    # NETWORK_MODE the executor port's reach is left to Windows defaults, so refuse to arm
    # (fail-closed) unless the operator knowingly opted out via arm.json "allow_insecure_bind": true.
    if not ALLOW_INSECURE_BIND and not firewall_gate_satisfied(PORT, NETWORK_MODE):
        raise RuntimeError(
            "refusing to arm: firewall rule '%s' for network_mode=%s is missing, so executor port %d "
            "is not scoped. Run scripts/harden-firewall.ps1 as admin (-Mode %s for this mode), or set "
            "\"allow_insecure_bind\": true in ~/.houdini-bridge-mcp/arm.json to bind on all interfaces knowingly."
            % (firewall_rule_name(PORT, NETWORK_MODE), NETWORK_MODE, PORT, NETWORK_MODE)
        )

    hou.session._HMCP_RUNNING = True

    hou.ui.addEventLoopCallback(_pump)

    # Import the stage handlers — this is what populates _REGISTRY (all registration MUST
    # happen before the urlHandler loop below, since routes lock at hwebserver.run()).
    from houdini_executor import handlers  # noqa: F401

    # Executor-side mirror of the gateway's catalog_never_exposes_rce_tools test. The registry — not
    # the gateway catalog — is the boundary an attacker who reaches the port sees, so re-assert the
    # data-only invariant HERE and refuse to arm if an RCE-shaped endpoint ever drifts in (audit L1).
    _assert_no_rce_endpoints()

    # Dev-only hot-reload endpoint: registered ONLY when the operator set "dev_reload": true in arm.json
    # (release hardening [#138]). A shipped executor leaves "reload" unregistered → no loopback caller can
    # trigger an importlib.reload of handler code. Registered AFTER the RCE assert (its name is not a
    # banned token; this is a re-import affordance, not an RCE primitive).
    if DEV_RELOAD:
        _REGISTRY["reload"] = {"fn": _reload, "auth": True}
        print("[houdini-bridge-mcp] dev_reload ON — 'reload' endpoint registered (dev-loop hot-reload)")

    @hwebserver.urlHandler("/health")
    def _health(request):
        # Unauthenticated liveness probe — intentionally minimal. Do NOT leak the working_dir or any
        # path/config here; anything reachable on the port can read this (security audit H1).
        return hwebserver.Response(
            json.dumps({"ok": True, "service": "houdini-bridge-mcp", "version": VERSION,
                        "houdini": hou.applicationVersionString()}),
            content_type="application/json")

    # ONE prefix catch-all for every tool. hwebserver patterns are exact/prefix (never regex);
    # is_prefix=True matches /tool/<anything>. _dispatch resolves the handler from _REGISTRY at
    # request time, so newly-added or hot-reloaded handlers work with no route changes.
    @hwebserver.urlHandler("/tool", is_prefix=True)
    def _tool(request):
        name = request.path()[len("/tool/"):].strip("/")
        return _dispatch(name, request)

    hwebserver.run(PORT, debug=False, max_num_threads=8)


def teardown():
    try:
        hou.ui.removeEventLoopCallback(_pump)
    except Exception:  # noqa: BLE001
        pass
    hwebserver.requestShutdown()
    hou.session._HMCP_RUNNING = False


@endpoint("teardown")
def _teardown_ep(params):
    """Operator-only disarm — the GUI's "Tear down" control. This is a CONTROL-PLANE endpoint,
    reachable only by an authed loopback caller (the GUI, via X-HMCP-Token); it is deliberately
    NOT in the gateway's `tools.rs` catalog, so the AI's MCP path can never invoke it (the gateway
    rejects any tools/call whose name isn't in the typed catalog). "teardown" also carries none of
    the `_BANNED_ENDPOINT_TOKENS`, so it doesn't trip the data-only guard.

    The actual `hwebserver` shutdown is DEFERRED to the next event-loop tick, NOT run inline: this
    handler is dispatched on the main-thread pump while the server is mid-serving THIS request, so
    calling `requestShutdown()` here would risk dropping the very response the caller is waiting on
    (the self-shutdown race). Scheduling `teardown()` on the next tick lets this request's HTTP
    response flush first, then the server stops.

    LIVE-VERIFY (the one platform unknown, per the teardown research): `requestShutdown()` only
    *signals* the background listener; the OS may not release the port immediately, so an
    immediate re-arm could still hit a bind race. `teardown()` sets `_HMCP_RUNNING=False`, so
    `arm()`'s guard won't block a retry — a short wait before re-arming is the pragmatic mitigation
    until the exact `requestShutdown()`/port-release timing is confirmed in a live H21 session.
    """
    def _deferred_shutdown():
        try:
            hou.ui.removeEventLoopCallback(_deferred_shutdown)
        except Exception:  # noqa: BLE001
            pass
        teardown()
    hou.ui.addEventLoopCallback(_deferred_shutdown)
    return {"status": "teardown scheduled", "port": PORT}

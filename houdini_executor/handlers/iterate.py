"""Iterate / compile lane (Family 6 / Lane C) — the For-Each block
and Compile-block plumbing that keeps big destruction / per-piece setups sane and fast.

These are MULTI-NODE BLOCK structures, not single nodes: a For-Each loop is a `block_begin` +
`block_end` pair (optionally a `block_begin` "metadata" companion) that cross-reference each other by
path; a Compile block is a `compile_begin` + `compile_end` pair. The hard part is the WIRING and the
back-references — every node type, parm name, and menu token below was live-probed on H21.0.671
and every builder is cook-proven:
a count loop iterates N times (N points out), a piece loop round-trips N named pieces, a compiled
for-each cooks with multithread on and zero errors.

Data-only: this lane builds ONLY the typed block STRUCTURE. It authors NO VEX — the per-piece logic
that usually lives inside a For-Each is added later by the safe-VEX lane's `set_attrib_expr` placed
on the loop body. Style mirrors handlers/attribops.py + handlers/constraints.py: `_try_set`/`_menu_set`
skip absent parms (never invent one), numerics clamped, creators FAIL on name collision.

PROBE FINDINGS (the load-bearing discovery):
  block_begin  `method`     Menu ['feedback','piece','metadata','input']  (Fetch Feedback / Extract
                            Piece or Point / Fetch Metadata / Fetch Input). `blockpath` String =
                            back-ref to the paired block_end. Button `createmetablock` spawns the
                            metadata companion (a 2nd block_begin, method='metadata').
  block_end    inputs (0)='Nodes to Iterate Over' (1)='Geometry Pieces to Loop Over'.
                            `itermethod` Menu ['auto','pieces','count']; `method` (gather) Menu
                            ['feedback','merge']; `class` Menu ['primitive','point']; `useattrib`+
                            `attrib` (piece name attr); `iterations`/`startvalue`/`increment` (count);
                            `usemaxiter`+`maxiter` (cap); `multithread` (Multithread When Compiled);
                            `dosinglepass`+`singlepass` (debug); `blockpath` = back-ref to block_begin.
  compile_begin `blockpath` = back-ref to compile_end; `name`; `optional`.
  compile_end   `primarypath` = back-ref to compile_begin; `docompile`; `unload` Menu
                            ['never','flag','always']; `fallback`.
"""

import hou
from houdini_executor.server import endpoint, clamp, resolve_node
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── probe-safe setters (same contract as attribops.py / constraints.py) ──────




def _sop_of(path):
    """Resolve a node path to the SOP a wiring should read: an /obj geo -> its display/render SOP,
    else the node itself. Mirrors child_after's ObjNode unwrap so callers may pass a SOP or its geo."""
    n = resolve_node(path)
    try:
        if isinstance(n, hou.ObjNode):
            disp = n.displayNode() or n.renderNode()
            if disp is not None:
                return disp
    except Exception:
        pass
    return n


def _make_in_parent(anchor_path, ntype, name=None, wire_input=True):
    """Create `ntype` in the parent network of `anchor_path`'s SOP, optionally wired after it.
    Unlike child_after this can create a block node WITHOUT connecting input 0 (a piece-mode
    block_begin has no meaningful input — it extracts from the block_end's pieces input via the
    blockpath link). Creators fail on name collision (createNode raises)."""
    src = _sop_of(anchor_path)
    parent = src.parent()
    n = parent.createNode(ntype, name) if name else parent.createNode(ntype)
    if wire_input:
        n.setInput(0, src)
    n.moveToGoodPosition()
    return n


def _cook(n):
    """Force a cook so the block is proven to build; guarded so a not-yet-complete scaffold (missing
    a required pieces input) leaves the nodes in place rather than failing the build. Returns OK."""
    try:
        n.geometry()
        return True
    except Exception:
        return False


def _relpath(from_node, to_node):
    """Sibling relative path (both live in the same parent network): '../<name>'."""
    return "../" + to_node.name()


# ── menu token tables (probed) ───────────────────────────────────────────────
_BEGIN_METHOD = ("feedback", "piece", "metadata", "input")
_END_ITERMETHOD = ("auto", "pieces", "count")
_END_GATHER = ("feedback", "merge")
_END_CLASS = ("primitive", "point")
_COMPILE_UNLOAD = ("never", "flag", "always")


def _norm_class(c):
    c = str(c)
    if c in ("prim", "prims", "primitive"):
        return "primitive"
    if c in ("point", "points"):
        return "point"
    return c


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK-END CONFIG (shared by for_each + for_each_end)
# ══════════════════════════════════════════════════════════════════════════════
def _configure_block_end(be, params, default_iter="auto", default_class="primitive"):
    """Apply the iteration/gather/piece config onto a block_end. Returns the `applied` dict."""
    applied = {}
    applied["iter_method"] = _menu_set(be, "itermethod",
                                       str(params.get("iter_method", default_iter)), _END_ITERMETHOD)
    applied["gather"] = _menu_set(be, "method", str(params.get("gather", "merge")), _END_GATHER)
    if "iterations" in params:
        _try_set(be, "iterations", int(clamp(int(params["iterations"]), 1, 1000000000)))
    if "start_value" in params:
        _try_set(be, "startvalue", clamp(float(params["start_value"]), -1e12, 1e12))
    if "increment" in params:
        _try_set(be, "increment", clamp(float(params["increment"]), -1e12, 1e12))
    applied["piece_class"] = _menu_set(be, "class",
                                       _norm_class(params.get("piece_class", default_class)), _END_CLASS)
    # Piece attribute: giving one implies useattrib on; an explicit use_attrib overrides.
    if params.get("piece_attrib") is not None:
        _try_set(be, "attrib", str(params["piece_attrib"]))
        _try_set(be, "useattrib", True)
    if "use_attrib" in params:
        _try_set(be, "useattrib", bool(params["use_attrib"]))
    if "max_iterations" in params:
        _try_set(be, "usemaxiter", True)
        _try_set(be, "maxiter", int(clamp(int(params["max_iterations"]), 1, 1000000000)))
    if "multithread" in params:
        applied["multithread"] = _try_set(be, "multithread", bool(params["multithread"]))
    if "single_pass" in params:
        _try_set(be, "dosinglepass", True)
        _try_set(be, "singlepass", int(clamp(int(params["single_pass"]), 0, 1000000000)))
    return applied


# ══════════════════════════════════════════════════════════════════════════════
# FOR-EACH — one-shot scaffold
# ══════════════════════════════════════════════════════════════════════════════
@endpoint("for_each")
def for_each(params):
    """Build a complete, cookable For-Each loop SCAFFOLD around a target — a `block_begin` +
    pass-through body `null` + `block_end`, fully wired and cross-referenced (the block_begin/block_end
    pair reference each other by relative path), ready to fill with per-piece logic (add it later with
    the safe-VEX lane's `set_attrib_expr` on the returned `body` node). Verified: a count loop runs N
    iterations (N points out); a piece loop round-trips N pieces.

    method: piece (Extract Piece or Point — loops over each piece/point of `input`; input is wired to
    the block_end's 'pieces' input) | feedback (accumulate — each iteration fetches the previous
    result; input seeds the block_begin) | input (fetch the block_begin input each iteration) |
    metadata. iter_method: auto|pieces|count (default pieces for method=piece, else count). gather:
    merge (concatenate every iteration, default) | feedback (only the last). iterations = count-mode
    loop count. piece_class: primitive|point; piece_attrib = the `name` attr to split pieces by
    (default: loop connected pieces / each element); use_attrib toggles attribute-based splitting.
    multithread = Multithread When Compiled (only valid inside a compile_block). create_metadata adds
    the metadata companion block (exposes iteration/numiterations/value for a later VEX body).

    Returns begin / body / end / metadata node paths."""
    method = str(params.get("method", "piece"))
    base = params.get("name")
    target = params["input"]
    # block_begin: wire input0 only for the feedback/input methods (piece/metadata extract via the
    # block_end link, so their input0 is left unconnected — cleaner, and verified harmless either way).
    wire_begin = method in ("feedback", "input")
    begin = _make_in_parent(target, "block_begin", (base + "_begin") if base else None, wire_input=wire_begin)
    _menu_set(begin, "method", method, _BEGIN_METHOD)
    parent = begin.parent()
    body = parent.createNode("null", (base + "_body") if base else "foreach_body")
    body.setInput(0, begin)
    body.moveToGoodPosition()
    end = parent.createNode("block_end", (base + "_end") if base else None)
    end.setInput(0, body)
    if method in ("piece", "metadata"):
        end.setInput(1, _sop_of(target))       # Geometry Pieces to Loop Over
    end.moveToGoodPosition()
    # cross-reference the pair by relative path (both are siblings in `parent`)
    _try_set(begin, "blockpath", _relpath(begin, end))
    _try_set(end, "blockpath", _relpath(end, begin))
    default_iter = "pieces" if method == "piece" else ("count" if method in ("feedback", "input") else "auto")
    applied = _configure_block_end(end, params, default_iter=default_iter)
    applied["begin_method"] = method
    meta = None
    if params.get("create_metadata"):
        before = set(c.name() for c in parent.children())
        try:
            begin.parm("createmetablock").pressButton()
            new = [parent.node(n) for n in (set(c.name() for c in parent.children()) - before)]
            if new:
                meta = new[0].path()
        except Exception:
            meta = None
    return {"begin": begin.path(), "body": body.path(), "end": end.path(),
            "metadata": meta, "applied": applied, "cooked": _cook(end)}


# ══════════════════════════════════════════════════════════════════════════════
# FOR-EACH BEGIN — composable primitive
# ══════════════════════════════════════════════════════════════════════════════
@endpoint("for_each_begin")
def for_each_begin(params):
    """Create a single For-Each `block_begin` (the loop entry) — the composable half for wrapping a
    body chain you build yourself: call this, build your per-piece nodes tapping off the returned
    node, then close the loop with `for_each_end` (input = your body's output, begin = this node).

    method: feedback | piece (Extract Piece or Point) | metadata | input. For feedback/input the
    `input` geometry is wired to the block_begin (seed / fetched geometry); for piece/metadata the
    input0 is left unconnected (the pieces come from the block_end's pieces input). pair_end = an
    existing block_end to cross-reference now (sets both blockpaths). create_metadata also spawns the
    metadata companion block (method='metadata', exposing iteration/numiterations/value)."""
    method = str(params.get("method", "piece"))
    wire_begin = method in ("feedback", "input")
    begin = _make_in_parent(params["input"], "block_begin", params.get("name"), wire_input=wire_begin)
    applied = {"method": _menu_set(begin, "method", method, _BEGIN_METHOD)}
    if params.get("pair_end"):
        end = _sop_of(params["pair_end"])
        _try_set(begin, "blockpath", _relpath(begin, end))
        _try_set(end, "blockpath", _relpath(end, begin))
        applied["paired"] = end.path()
    meta = None
    if params.get("create_metadata"):
        parent = begin.parent()
        before = set(c.name() for c in parent.children())
        try:
            begin.parm("createmetablock").pressButton()
            new = [parent.node(n) for n in (set(c.name() for c in parent.children()) - before)]
            if new:
                meta = new[0].path()
        except Exception:
            meta = None
    return {"node": begin.path(), "metadata": meta, "begin_method": method, "applied": applied}


# ══════════════════════════════════════════════════════════════════════════════
# FOR-EACH END — composable primitive (closes a loop over a built body)
# ══════════════════════════════════════════════════════════════════════════════
@endpoint("for_each_end")
def for_each_end(params):
    """Close a For-Each loop: create a `block_end` after `input` (your loop body's output — wired to
    the 'Nodes to Iterate Over' input) and pair it to an existing `begin` block (cross-sets both
    blockpaths). This is how you WRAP a body chain you built with other typed tools.

    begin = the paired block_begin (strongly recommended — without it the loop has no entry). pieces =
    the geometry whose pieces/points to loop over (wired to the block_end's 2nd 'Geometry Pieces to
    Loop Over' input; needed for piece/auto iteration). iter_method: auto|pieces|count. gather:
    merge|feedback. iterations/start_value/increment = count-mode controls. piece_class:
    primitive|point; piece_attrib = the `name` attr to split by; use_attrib toggles it. max_iterations
    caps the loop; multithread = Multithread When Compiled; single_pass cooks only one iteration
    (debug)."""
    end = _make_in_parent(params["input"], "block_end", params.get("name"), wire_input=True)
    if params.get("pieces"):
        end.setInput(1, _sop_of(params["pieces"]))
    applied = _configure_block_end(end, params, default_iter="auto")
    if params.get("begin"):
        begin = _sop_of(params["begin"])
        _try_set(end, "blockpath", _relpath(end, begin))
        _try_set(begin, "blockpath", _relpath(begin, end))
        applied["paired"] = begin.path()
    return {"node": end.path(), "applied": applied, "cooked": _cook(end)}


# ══════════════════════════════════════════════════════════════════════════════
# COMPILE BLOCK — the multithread / cook-overhead-strip optimizer
# ══════════════════════════════════════════════════════════════════════════════
@endpoint("compile_block")
def compile_block(params):
    """Wrap a target in a Compile block — `compile_begin` + `compile_end`, cross-referenced
    (compile_begin.blockpath -> compile_end, compile_end.primarypath -> compile_begin). Compiled
    blocks strip per-node cook overhead and let an enclosed For-Each multithread (set for_each_end's
    `multithread`), the difference between interactive and unusable on heavy per-piece work. Verified:
    a compiled for-each cooks with zero errors and multithread on.

    input is fed to the compile_begin (Uncompiled Source). wrap=True (default) inserts a pass-through
    body `null` between begin and end as the anchor to build the compiled chain on; wrap=False wires
    compile_end straight to compile_begin (a bare block to grow by hand). block_name names the block
    (compile_begin.name) for reuse. unload: never|flag|always (when the compiled result is dropped
    from memory). optional_inputs marks the begin's inputs optional.

    Returns begin / body / end node paths."""
    base = params.get("name")
    begin = _make_in_parent(params["input"], "compile_begin",
                            (base + "_begin") if base else "compile_begin", wire_input=True)
    parent = begin.parent()
    applied = {}
    if params.get("block_name"):
        _try_set(begin, "name", str(params["block_name"]))
    if "optional_inputs" in params:
        _try_set(begin, "optional", bool(params["optional_inputs"]))
    body = None
    if params.get("wrap", True):
        body = parent.createNode("null", (base + "_body") if base else "compile_body")
        body.setInput(0, begin)
        body.moveToGoodPosition()
    end = parent.createNode("compile_end", (base + "_end") if base else "compile_end")
    end.setInput(0, body if body is not None else begin)
    end.moveToGoodPosition()
    _try_set(begin, "blockpath", _relpath(begin, end))
    _try_set(end, "primarypath", _relpath(end, begin))
    if params.get("unload"):
        applied["unload"] = _menu_set(end, "unload", str(params["unload"]), _COMPILE_UNLOAD)
    if "fallback" in params:
        _try_set(end, "fallback", bool(params["fallback"]))
    return {"begin": begin.path(), "body": body.path() if body is not None else None,
            "end": end.path(), "applied": applied, "cooked": _cook(end)}

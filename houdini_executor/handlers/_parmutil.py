"""Shared per-parameter setter helpers for the handler modules.

These were previously copy-pasted into ~90 handler modules (the `_try_set` probe-safe setter alone had
89 byte-identical definitions). Lifting them here removes that duplication so a future behavior/security
fix lands in ONE place. This module depends on nothing but the `hou` node objects passed in (no import of
`houdini_executor.server` or any handler), so it is a safe leaf with zero circular-import risk.

Behavior is preserved EXACTLY. `_try_set` is the single canonical form of the 8 textual `_try_set`
variants (they differed only in docstring/comment). The `_menu_set_*` family is split by the underlying
menu parm's STORAGE kind so each prior call site keeps its exact set mechanism — Houdini menus store
EITHER an integer index (ordered menus) OR the token string, and a single strategy is not correct for
both, so they intentionally remain distinct functions rather than one lossy "superset".
"""


def _try_set(node, parm, value):
    """Set a parm only if it exists on this node (probe-safe: never invents a parm). Returns True iff the
    value was applied. Identical to every prior local `_try_set` (they differed only in docstring)."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(value)
        return True
    except Exception:
        return False


def _menu_set_index(node, parm, token, tokens):
    """Set an ordered / index-stored menu parm by its token: the STORED value is the token's INDEX in
    `tokens` (the menu items, in order). Probe-safe — a no-op (returns False) if the parm is absent or
    the token is not a member. This is the single canonical form of all 55 cluster-A `_menu_set` call
    sites (their two textual shapes are behaviorally identical: True iff parm exists AND token in tokens
    AND the set succeeds). `str(token)` is a defensive no-op for the string tokens every site passes.

    Note: this is the INDEX-stored strategy ONLY. String-stored menus (some Labs/ROP handlers) and the
    live-menu handlers (ml.py / render_waveE) keep their own local `_menu_set` — the stored kind
    genuinely differs, and a single strategy is not correct for both."""
    token = str(token)
    if token in tokens:
        return _try_set(node, parm, tokens.index(token))
    return False


def _try_set_tuple(node, parm, values):
    """Set a parmTuple only if it exists (probe-safe), coercing each value to float. Returns True iff the
    set succeeded. Canonical form of the 19 identical float-coercing `_try_set_tuple` sites. The
    non-coercing (`tuple(values)`), per-component, and clamping variants keep their own local defs —
    their behavior genuinely differs."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(float(v) for v in values))
        return True
    except Exception:
        return False

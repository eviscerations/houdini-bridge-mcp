"""Safe-VEX attribute-expression handler — the executor side of the optional ``set_attrib_expr`` tool.

THIS HANDLER IS THE SECURITY BOUNDARY for the one validated-VEX lane.

The invariants, mirrored from ``server._assert_no_rce_endpoints`` / ``server.confined_path`` (executor
is authoritative — never trust the gateway pre-check):

  1. **Opt-in, default-OFF.** ``allow_attrib_expr`` in ``~/.houdini-bridge-mcp/arm.json`` (read exactly
     like ``allow_insecure_bind`` in server.auto_arm) must be true. Absent/unreadable/false ⇒ the
     handler refuses (fail-closed) before touching anything.
  2. **Validate BEFORE any parm write.** ``validate_attrib_vex(code, outputs)`` runs first; on any
     violation it RAISES ``VexValidationError`` and NOTHING is created and NO snippet is set. Never
     sanitize-and-proceed, never set an unvalidated snippet.
  3. **Audit.** Every ACCEPTED snippet (verbatim) + node path + run_over + outputs + timestamp, and
     every REJECTED snippet + the failing rule, is appended to a confined ``vex_audit.log``. Best-effort
     (a logging failure never blocks/crashes a validated write, and a success is never silently unlogged).
  4. **Belt-and-suspenders.** The snippet parm is set as a LITERAL (``.set``, never ``setExpression``),
     with any stray channel/keyframe cleared first, so the string is used verbatim as VEX and cannot be
     re-interpreted as an hscript/python parm expression. (Wrangle snippet parms carry NO expansion
     toggle — probe-confirmed on H21.0.671 — and the validator already rejects backtick/``$``/``#``, so
     this is pure defense-in-depth.)

Probe-verified live on Houdini 21.0.671:
  * every wrangle's snippet parm is ``snippet`` (String, label "VEXpression").
  * ``class`` is an ordered (index) menu ``[detail, primitive, point, vertex, number]`` present ONLY on
    ``attribwrangle`` + ``kinefx::rigattribwrangle``; the other v1 wrangles have a fixed run-over.
  * ``group`` on all; ``grouptype`` menu ``[guess, vertices, edges, points, prims]`` on
    attribwrangle/kinefx/deformationwrangle.
  * ``sopsolver::2.0`` internal SOP chain is ``dop_geometry`` -> ``OUT`` (display=OUT); the per-frame
    constraint wrangle is inserted between them.

v2 DOP-native wrangles probe-verified live on H21.0.671:
  * node types are unversioned: ``popwrangle``, ``gasfieldwrangle``, ``geometrywrangle`` (no ``::2.0``).
    ``popnet`` is NOT a node type ("Invalid node type name") — the container is the ``dopnet``.
  * ALL THREE create error-free directly inside a bare ``dopnet`` (``errors()`` empty on create), set
    their ``snippet`` literal cleanly (roundtrip-match), stay error-free, and BOTH the wrangle and the
    dopnet ``cook(force=True)`` clean — no host solver is needed for a legal assembly.
  * snippet parm is ``snippet`` (String, label "VEXpression") on all three, same as the SOP family.
  * run-over / group parm names differ from SOP: ``popwrangle`` has NO class menu (fixed = every
    particle) + group via ``partgroup`` gated by the ``usegroup`` toggle (default OFF);
    ``gasfieldwrangle`` has NO class and NO group (runs over voxels of autobound fields);
    ``geometrywrangle`` has ``bindclass`` [detail,primitive,point,vertex,number] +
    ``bindgroup`` + ``bindgrouptype`` [guess,vertices,edges,points,prims] — same menu orders as the
    SOP ``class``/``grouptype``, so ``_CLASS_MENU`` / ``_GROUPTYPE_MENU`` are reused.
  * the SAME ``validate_attrib_vex`` (profile ``attrib_v1``) covers all three: the physics/field READ
    family (``volumesample*``/``volumegradient``/``primintrinsic``/``intersect``/``pgfind``/
    ``getbbox*``/``relbbox``) is already in ``ALLOWED_FUNCS``+``GEO_READ_FUNCS`` (arg0-int gated), and
    physics WRITES (``v@force``/``@density``/``i@active``/…) route through the ``outputs`` write-gate.
    No new validator profile and no new function are required for v2.
"""

import os
import json
import datetime
import pathlib

import hou
from houdini_executor.server import endpoint, child_after, resolve_node, confined_path
from houdini_executor import server as _server
from houdini_executor.vex_validator import validate_attrib_vex, VexValidationError
from houdini_executor.handlers._parmutil import _try_set
from houdini_executor.handlers._parmutil import _menu_set_index as _menu_set


# ── the wrangle-node family (v1 SOP + v2 DOP) ──────────────────────────────────────────────────────
# Per-type spec. `context`: "sop" (wired after a target SOP, or inside a sopsolver) | "dop" (created
# directly inside a caller-supplied dopnet). The run-over / group parm NAMES differ by context, so each
# entry names them explicitly (probe-verified H21.0.671):
#   * `class_parm`     — the ordered run-over menu parm, or None if the node's run-over is fixed.
#                        SOP `attribwrangle`/kinefx use "class"; DOP `geometrywrangle` uses "bindclass".
#   * `group_parm`     — the group-string parm, or None. SOP uses "group"; DOP `popwrangle` uses
#                        "partgroup", DOP `geometrywrangle` uses "bindgroup"; `gasfieldwrangle` has none.
#   * `grouptype_parm` — the ordered group-type menu parm, or None. SOP uses "grouptype"; DOP
#                        `geometrywrangle` uses "bindgrouptype".
#   * `usegroup_parm`  — a toggle that must be enabled for the group parm to take effect (DOP
#                        `popwrangle`'s "usegroup", default OFF), or None.
# `has_class`/`has_grouptype` are kept (redundant with the *_parm fields) for backward-compat readers.
# ALL run-over class menus (SOP `class`, DOP `bindclass`) share the order in `_CLASS_MENU`; ALL group-
# type menus (SOP `grouptype`, DOP `bindgrouptype`) share `_GROUPTYPE_MENU`. The snippet parm is
# uniformly `snippet` (label "VEXpression") across every SOP and DOP wrangle, and ALL route through the
# identical `validate_attrib_vex` (profile `attrib_v1`) — the boundary is the snippet STRING, not the
# node's location/context (corrected).
_WRANGLE_TYPES = {
    "attribwrangle":            {"node_type": "attribwrangle",            "context": "sop", "has_class": True,  "has_grouptype": True,
                                 "class_parm": "class", "group_parm": "group", "grouptype_parm": "grouptype", "usegroup_parm": None},
    "pointwrangle":             {"node_type": "pointwrangle",             "context": "sop", "has_class": False, "has_grouptype": False,
                                 "class_parm": None,    "group_parm": "group", "grouptype_parm": None,        "usegroup_parm": None},
    "volumewrangle":            {"node_type": "volumewrangle",            "context": "sop", "has_class": False, "has_grouptype": False,
                                 "class_parm": None,    "group_parm": "group", "grouptype_parm": None,        "usegroup_parm": None},
    "kinefx::rigattribwrangle": {"node_type": "kinefx::rigattribwrangle", "context": "sop", "has_class": True,  "has_grouptype": True,
                                 "class_parm": "class", "group_parm": "group", "grouptype_parm": "grouptype", "usegroup_parm": None},
    "deformationwrangle":       {"node_type": "deformationwrangle",       "context": "sop", "has_class": False, "has_grouptype": True,
                                 "class_parm": None,    "group_parm": "group", "grouptype_parm": "grouptype", "usegroup_parm": None},
    # ── v2: DOP-native wrangles (created inside a caller-supplied dopnet; SAME validator) ──
    "popwrangle":               {"node_type": "popwrangle",               "context": "dop", "has_class": False, "has_grouptype": False,
                                 "class_parm": None,    "group_parm": "partgroup", "grouptype_parm": None,    "usegroup_parm": "usegroup"},
    "gasfieldwrangle":          {"node_type": "gasfieldwrangle",          "context": "dop", "has_class": False, "has_grouptype": False,
                                 "class_parm": None,    "group_parm": None,    "grouptype_parm": None,        "usegroup_parm": None},
    "geometrywrangle":          {"node_type": "geometrywrangle",          "context": "dop", "has_class": True,  "has_grouptype": True,
                                 "class_parm": "bindclass", "group_parm": "bindgroup", "grouptype_parm": "bindgrouptype", "usegroup_parm": None},
}

# run_over token -> the `class` ordered-menu token (probe: [detail, primitive, point, vertex, number]).
_RUN_OVER_TO_CLASS = {"points": "point", "prims": "primitive", "vertices": "vertex",
                      "detail": "detail", "numbers": "number"}
_CLASS_MENU = ("detail", "primitive", "point", "vertex", "number")
_GROUPTYPE_MENU = ("guess", "vertices", "edges", "points", "prims")


# ── opt-in flag gate (mirror of server.auto_arm's allow_insecure_bind read) ────────────────────────
def _allow_attrib_expr():
    """Fresh, per-call, fail-closed read of ``allow_attrib_expr`` from arm.json — the SAME shape as
    ``bool(data.get("allow_insecure_bind", False))`` in server.auto_arm (server.py L342). Any
    absent/unreadable/invalid config ⇒ disabled."""
    cfg = pathlib.Path.home() / ".houdini-bridge-mcp" / "arm.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return bool(data.get("allow_attrib_expr", False))
    except Exception:  # noqa: BLE001 — missing/unreadable/malformed => stay OFF
        return False


def _allow_attrib_loops():
    """Fresh, per-call, fail-closed read of ``allow_attrib_loops`` from arm.json — the SAME shape as
    ``_allow_attrib_expr`` (mirror of server.auto_arm's ``allow_insecure_bind`` read). This is a SEPARATE
    consent from ``allow_attrib_expr``: bounded counted loops in a validated snippet are permitted ONLY
    when this is true, and it is default-OFF even when ``allow_attrib_expr`` is on. Any
    absent/unreadable/invalid config ⇒ disabled (loops off ⇒ the validator rejects ``for`` as before)."""
    cfg = pathlib.Path.home() / ".houdini-bridge-mcp" / "arm.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return bool(data.get("allow_attrib_loops", False))
    except Exception:  # noqa: BLE001 — missing/unreadable/malformed => stay OFF
        return False


def _allow_attrib_geoedit():
    """Fresh, per-call, fail-closed read of ``allow_attrib_geoedit`` from arm.json — the SAME shape as
    ``_allow_attrib_loops`` (mirror of server.auto_arm's ``allow_insecure_bind`` read). This is a SEPARATE
    consent from ``allow_attrib_expr`` and ``allow_attrib_loops``: DELETION-only topology writers
    (``removepoint``/``removeprim`` on input-0) in a validated snippet are permitted ONLY when this is
    true, and it is default-OFF even when ``allow_attrib_expr``/``allow_attrib_loops`` are on. Any
    absent/unreadable/invalid config ⇒ disabled (deletion off ⇒ the validator rejects the writers)."""
    cfg = pathlib.Path.home() / ".houdini-bridge-mcp" / "arm.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return bool(data.get("allow_attrib_geoedit", False))
    except Exception:  # noqa: BLE001 — missing/unreadable/malformed => stay OFF
        return False


def _allow_attrib_geogrow():
    """Fresh, per-call, fail-closed read of ``allow_attrib_geogrow`` from arm.json — the SAME shape as
    ``_allow_attrib_geoedit``. This is a THIRD SEPARATE consent from ``allow_attrib_expr`` /
    ``allow_attrib_loops`` / ``allow_attrib_geoedit``: CONSTRUCTION/GROWTH topology writers
    (``addpoint``/``addprim``/``addvertex``/``removevertex`` on input-0) in a validated snippet are
    permitted ONLY when this is true, and it is default-OFF even when the other flags are on (enabling
    DELETION does NOT grant GROWTH). Any absent/unreadable/invalid config ⇒ disabled (growth off ⇒ the
    validator rejects the writers)."""
    cfg = pathlib.Path.home() / ".houdini-bridge-mcp" / "arm.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return bool(data.get("allow_attrib_geogrow", False))
    except Exception:  # noqa: BLE001 — missing/unreadable/malformed => stay OFF
        return False


# ── confined audit log ─────────────────────────────────────────────────────────────────────────────
def _audit(status, code, node_path, run_over, outputs, wrangle_type, rule=None):
    """Append one JSONL record to ``<working_dir>/vex_audit.log`` (confined). Best-effort: never let a
    logging failure propagate into the validated write path, but never skip a success silently either —
    this is the after-the-fact reviewability required by the validator design."""
    try:
        base = _server._effective_working_dir()
        path = confined_path(os.path.join(base, "vex_audit.log"))
        rec = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "status": status,               # "ACCEPT" | "REJECT"
            "wrangle_type": wrangle_type,
            "run_over": run_over,
            "outputs": outputs,
            "node": node_path,
            "code": code,                   # verbatim snippet (accepted or rejected)
        }
        if rule is not None:
            rec["rule"] = rule              # the VexValidationError message on a rejection
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 — audit is best-effort; a logging failure must not block the write
        pass


# ── parm helpers (probe-safe: never invent a parm) ─────────────────────────────────────────────────




def _set_snippet_literal(node, validated):
    """Write the VALIDATED snippet to the wrangle's ``snippet`` parm as a LITERAL string. Belt-and-
    suspenders: clear any channel/keyframe first and use ``.set`` (never ``setExpression``) so the value
    is stored + evaluated verbatim as VEX and cannot be re-read as an hscript/python parm expression.
    Wrangle snippet parms have NO hscript/python expansion toggle to disable (probe-confirmed H21.0.671),
    so the literal set + the validator's backtick/$/# rejection is the whole belt."""
    p = node.parm("snippet")
    if p is None:
        raise ValueError("wrangle node %s has no 'snippet' parm" % node.path())
    try:
        p.deleteAllKeyframes()
    except Exception:  # noqa: BLE001
        pass
    p.set(validated)
    return p


def _place_in_sopsolver(dop_target, wname):
    """Create a ``sopsolver::2.0`` inside the given dopnet and an ``attribwrangle`` inside it, wired into
    the editable SOP chain (``dop_geometry`` -> wrangle -> ``OUT``) — the constraint-break-per-frame case.
    The wrangle is the SAME validated string as the standalone lane; only its location differs."""
    dn = resolve_node(dop_target)
    if dn.type().name() != "dopnet":
        raise ValueError("dop_target must be a dopnet, got %s (%s)" % (dop_target, dn.type().name()))
    ss = dn.createNode("sopsolver::2.0")          # auto-unique name (fresh solver holder)
    ss.moveToGoodPosition()
    out = ss.node("OUT")
    dg = ss.node("dop_geometry")
    if out is None or dg is None:
        raise ValueError("sopsolver %s has no editable dop_geometry->OUT chain" % ss.path())
    w = ss.createNode("attribwrangle", wname) if wname else ss.createNode("attribwrangle")
    feeder = out.inputs()[0] if out.inputs() else dg
    w.setInput(0, feeder)
    out.setInput(0, w)
    w.moveToGoodPosition()
    return ss, w


def _place_in_dopnet(dop_target, node_type, wname, wire_to=None):
    """Create a v2 DOP-native wrangle (``popwrangle`` / ``gasfieldwrangle`` / ``geometrywrangle``)
    directly inside the caller-supplied ``dopnet``. Probe-verified:
    each creates error-free in a bare dopnet, its ``snippet`` sets cleanly, ``node.errors()`` is empty,
    and both the node and the dopnet cook clean — no host solver is required for a legal assembly. The
    node is a microsolver/behavior node; ``wire_to`` (optional) feeds its input 0 from an existing node
    inside the dopnet (e.g. a solver's microsolver chain), mirroring ``_place_in_sopsolver``'s
    ``w.setInput(0, feeder)``. The MINIMAL creatable+cook-legal container is the dopnet itself."""
    dn = resolve_node(dop_target)
    if dn.type().name() != "dopnet":
        raise ValueError("dop_target must be a dopnet, got %s (%s)" % (dop_target, dn.type().name()))
    w = dn.createNode(node_type, wname) if wname else dn.createNode(node_type)
    if wire_to:
        w.setInput(0, resolve_node(wire_to))
    w.moveToGoodPosition()
    return dn, w


# ── the endpoint ───────────────────────────────────────────────────────────────────────────────────
@endpoint("set_attrib_expr")
def set_attrib_expr(params):
    """Create a wrangle carrying a VALIDATED safe-VEX attribute snippet. The ONLY code-text lane in the
    tool, and it is executor-validated (loop-free, call-allowlisted, no I/O) BEFORE the snippet is ever
    written. Default-OFF (arm.json ``allow_attrib_expr``). See module docstring for the full contract."""
    # ── (1) opt-in / default-OFF gate — refuse before touching anything (fail-closed) ──
    if not _allow_attrib_expr():
        raise ValueError("set_attrib_expr is disabled; set allow_attrib_expr in arm.json to enable")

    wrangle_type = str(params.get("wrangle_type", "attribwrangle"))
    run_over = str(params.get("run_over", "points"))
    code = params.get("code")
    outputs_raw = params.get("outputs", "")
    name = params.get("name")
    dop_target = params.get("dop_target")

    # typed-param validation (cheap rejects before the VEX gate)
    if wrangle_type not in _WRANGLE_TYPES:
        raise ValueError("unknown wrangle_type %r; allowed: %s"
                         % (wrangle_type, sorted(_WRANGLE_TYPES)))
    if run_over not in _RUN_OVER_TO_CLASS:
        raise ValueError("unknown run_over %r; allowed: %s"
                         % (run_over, sorted(_RUN_OVER_TO_CLASS)))
    if not outputs_raw or not str(outputs_raw).strip():
        raise ValueError("`outputs` is required (comma-separated attribute names the snippet may write)")
    outputs_list = [o.strip() for o in str(outputs_raw).split(",") if o.strip()]

    # ── (2) VALIDATE BEFORE ANY PARM WRITE. On rejection: audit the failing rule and re-raise; NOTHING
    #        is created and NO snippet is set. This is THE boundary. ──
    try:
        validated = validate_attrib_vex(code, outputs_list, allow_loops=_allow_attrib_loops(),
                                        allow_geoedit=_allow_attrib_geoedit(),
                                        allow_geogrow=_allow_attrib_geogrow())
    except VexValidationError as exc:
        _audit("REJECT", code, None, run_over, outputs_list, wrangle_type, rule=str(exc))
        raise

    # ── only now (validated) do we build the node and set the snippet ──
    static_spec = _WRANGLE_TYPES[wrangle_type]
    applied = {}
    if static_spec["context"] == "dop":
        # v2: a DOP-native wrangle placed directly inside the caller's dopnet. Its snippet is the SAME
        # validated string as the SOP lane — only the node type + location differ. dop_target REQUIRED
        # (a DOP wrangle cannot live under a SOP `target`).
        if not dop_target:
            raise ValueError("`dop_target` (a dopnet) is required for DOP wrangle_type %r" % wrangle_type)
        dopnet, node = _place_in_dopnet(dop_target, static_spec["node_type"], name, params.get("wire_to"))
        effective_type = wrangle_type
        applied["placement"] = "dopnet"
        applied["dopnet"] = dopnet.path()
        if params.get("wire_to"):
            applied["wired_to"] = resolve_node(params["wire_to"]).path()
    elif dop_target:
        # v1: constraint-per-frame — attribwrangle inside a sopsolver inside the dopnet (wrangle_type
        # forced to attribwrangle — the sopsolver-internal case). UNCHANGED.
        sopsolver, node = _place_in_sopsolver(dop_target, name)
        effective_type = "attribwrangle"
        applied["placement"] = "sopsolver"
        applied["sopsolver"] = sopsolver.path()
    else:
        if not params.get("target"):
            raise ValueError("`target` is required unless `dop_target` is set")
        node = child_after(params["target"], static_spec["node_type"], name)
        effective_type = wrangle_type
        applied["placement"] = "sop"

    spec = _WRANGLE_TYPES[effective_type]

    # run-over: set the run-over class menu where the node exposes it (SOP `class` / DOP `bindclass`);
    # else the run-over is fixed by the node (POP = every particle; gas = every voxel of the bound field).
    class_parm = spec.get("class_parm")
    if class_parm:
        applied["run_over"] = _menu_set(node, class_parm, _RUN_OVER_TO_CLASS[run_over], _CLASS_MENU)
    else:
        applied["run_over"] = "fixed-by-node"

    # group / group_type — parm names differ by context (SOP `group`/`grouptype`; DOP `partgroup` /
    # `bindgroup` + `bindgrouptype`). A node with no group parm (gasfieldwrangle) silently ignores it.
    group_parm = spec.get("group_parm")
    if params.get("group") is not None and group_parm:
        applied["group"] = _try_set(node, group_parm, str(params["group"]))
        # DOP POP wrangle gates its group behind a use-group toggle (default OFF) — enable it so the
        # supplied group actually takes effect.
        if spec.get("usegroup_parm"):
            _try_set(node, spec["usegroup_parm"], 1)
    grouptype_parm = spec.get("grouptype_parm")
    if params.get("group_type") is not None and grouptype_parm:
        applied["group_type"] = _menu_set(node, grouptype_parm, str(params["group_type"]), _GROUPTYPE_MENU)

    # ── (4) set the VALIDATED snippet as a literal (belt-and-suspenders inside the helper) ──
    _set_snippet_literal(node, validated)
    applied["snippet"] = True

    # ── (3) audit the ACCEPTED snippet (verbatim) — best-effort, never silently skipped ──
    _audit("ACCEPT", validated, node.path(), run_over, outputs_list, effective_type)

    result = {
        "node": node.path(),
        "wrangle": node.path(),
        "wrangle_type": effective_type,
        "run_over": run_over,
        "outputs": outputs_list,
        "applied": applied,
    }
    if dop_target:
        result["dopnet"] = resolve_node(dop_target).path()
        if applied.get("placement") == "sopsolver":
            result["sopsolver"] = applied.get("sopsolver")   # v1 constraint-per-frame case
        if applied.get("wired_to"):
            result["wired_to"] = applied["wired_to"]         # v2 optional microsolver wiring
    return result

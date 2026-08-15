"""Parameter get/set handlers — ``set_parm`` (LITERAL-ONLY) and ``get_parm`` (read-only).

SECURITY CONTRACT — ``set_parm`` deliberately bends the no-generic-driver stance to set ONE node
parameter to a LITERAL value, so it is bounded with extreme care. A naive parm setter is a UNIVERSAL
RCE (write a Python SOP's ``python`` parm, a wrangle's ``snippet``, a ROP's ``prerender`` script, or a
button's callback and code runs on the next cook / render / press). ALL of these are enforced BEFORE
any value is written; any violation RAISES ``ValueError`` (fail-closed) — never sanitize-and-proceed:

  1. DENY code-carrying parms (the load-bearing protection), via BOTH:
       (a) a NAME denylist (case-insensitive, substring) — ``_CODE_NAME_TOKENS``;
       (b) parm-TEMPLATE inspection — ``_is_code_parm()`` — the real boundary, because names vary.
     H21.0.671-probed template signals (see docs / probe_parms_codeparm*.py):
       * a StringParmTemplate whose ``tags()`` carry ``editorlang`` (``python`` / ``VEX`` / ``hscript``)
         => a code editor field   [python SOP ``python``, every wrangle ``snippet``]
       * a StringParmTemplate whose ``tags()`` carry ``editor`` (multi-line editor) — DENIED
         conservatively even without ``editorlang`` (font/comment text is the only known benign case)
       * a non-empty ``scriptCallback()`` — an interactive callback that runs code on press
       * a Button parm (``parmTemplateType.Button``) — pressing it fires a callback
     NOTE (probed): ``stringType()`` is NOT a code signal on H21 — the enum is only
     Regular/FileReference/NodeReference/NodeReferenceList (no "code" member). And ROP script parms
     (``prerender`` / ``preframe`` / ...) are TEMPLATE-INDISTINGUISHABLE from a normal file parm
     (``FileReference``, no editor tag, empty callback) — so the NAME denylist is their ONLY catch;
     the render-script family is therefore hardcoded into ``_CODE_NAME_TOKENS``.
  2. REJECT expression-language string VALUES — a string value carrying a backtick (hscript
     `` `...` `` exec), ``op:`` / ``opinput:`` (node reach), or ``$`` (hscript/env var) is refused
     (mirrors the ``vex_validator`` raw-string rejects).
  3. LITERAL-ONLY — ``parm.set(value)`` only, NEVER ``parm.setExpression(...)``; keyframes/channels
     are cleared first (``deleteAllKeyframes``) so the stored value is a plain literal that cannot be
     re-read as an expression (mirrors ``_set_literal`` elsewhere in the codebase).
  4. TYPE-COERCE to the parm's actual template type (int / float / string / toggle / menu); a value
     that cannot coerce is refused.
  5. CONFINE file-path parms to the working directory. A ``FileReference`` string parm (``stringType()``
     == FileReference — a File SOP's ``file``, an export ROP's ``sopoutput``, a texture path, ...) takes
     a filesystem path; since ``value`` rides the gateway as a generic Str it is NOT FsPath-confined by
     the gateway. It is resolved (relative → against the working dir) and required to sit under
     ``HMCP_WORKING_DIR`` via ``confined_path`` (realpath, junction/symlink-safe); an escape RAISES.
     Empty clears the parm. This is data-confinement (a file parm is never RCE), required before public.

``get_parm`` is read-only + data-only: it returns the parm's evaluated + raw value, type, whether it
currently holds an expression/keyframes, and whether it is a denied code parm (so an agent can see an
injected expression). It never writes.
"""

import os

import hou
from houdini_executor.server import endpoint, resolve_node, confined_path, _effective_working_dir


# ── (2) expression-language string-value rejects (mirror vex_validator raw-string rejects) ──────────
# Boundary-TEACHING rejections: name the rule, say WHY, say the FIX. This is where a blind agent that
# skipped orientation learns the data-only boundary at the moment of need, so a bare type error would
# waste the teachable moment. Run on EVERY value before type coercion (see set_parm) so a numeric parm
# gets the boundary lesson too, not a "not coercible" type error.
_EXPR_FIX = ("set_parm writes LITERAL values only — there is no expression/code path (the data-only "
             "boundary). Pass a literal value; for a driven/computed value, hand it to the user (a "
             "wrangle or a hand-authored expression) rather than setting it here.")


def _reject_expr_value(value):
    """Refuse a string VALUE carrying an expression-language escape, with a message that names the rule,
    the reason, and the fix. A real number/token carries no backtick/$/op:, so this never false-rejects
    a legitimate literal."""
    low = value.lower()
    if "`" in value:
        raise ValueError("REFUSED: expression-language value — backtick (hscript `...`). " + _EXPR_FIX)
    if "$" in value:
        raise ValueError("REFUSED: expression-language value — '$' (hscript / env variable). " + _EXPR_FIX)
    if "op:" in low or "opinput:" in low:
        raise ValueError("REFUSED: expression-language value — 'op:'/'opinput:' node reference. " + _EXPR_FIX)


# ── (5) file-parm value confinement (data-confinement, mirrors the gateway FsPath confine) ───────────
# A FileReference string parm (a File SOP's `file`, an export ROP's `sopoutput`, a texture path, ...)
# takes a filesystem path. set_parm's `value` rides the gateway as a generic Str, so it is NOT
# FsPath-confined by the gateway the way a typed path param is. Confine it HERE so a file parm cannot be
# pointed at an arbitrary read/write location outside HMCP_WORKING_DIR (the one dir this process may
# touch). This is data-confinement, not the code-parm boundary — a file parm is never RCE — but it is
# required before public [#153]. Only FileReference parms are confined; NodeReference/Regular strings
# are not filesystem paths.
def _is_file_reference(pt):
    """True iff this String parm template is a file-path field (stringType FileReference). Fail-soft to
    False on any introspection error: a non-file string parm needs no path confinement, and the value
    has already passed the (2) expression-language reject regardless."""
    try:
        return pt.stringType() == hou.stringParmType.FileReference
    except Exception:  # noqa: BLE001
        return False


def _confine_file_value(value_str):
    """Confine a FileReference parm's value to the working directory. Empty/whitespace is allowed (it
    clears the parm). A relative path resolves against the working dir (NOT the process CWD, which
    Houdini would otherwise use); the RESOLVED, confined absolute path is returned and stored, so what
    is written is exactly what was validated. Raises ValueError (fail-closed) on any escape."""
    v = value_str.strip()
    if not v:
        return value_str  # clearing the parm — nothing to confine
    cand = v if os.path.isabs(v) else os.path.join(_effective_working_dir(), v)
    try:
        return confined_path(cand)  # realpath + under-root check; junction/symlink-safe
    except PermissionError as exc:
        raise ValueError("file parm value must stay inside the working directory (%s)" % exc)
    except OSError as exc:
        raise ValueError("file parm value is not a valid path (%s)" % (str(exc)[:80]))


# ── (1a) NAME denylist ──────────────────────────────────────────────────────────────────────────────
# Case-insensitive substrings. Any parm whose name contains one is treated as a code parm and DENIED.
# Err toward DENY. The render/frame/tile SCRIPT family is included because those ROP command parms run
# code on render yet are template-indistinguishable from a benign file parm (probe-confirmed H21.0.671).
_CODE_NAME_TOKENS = (
    # provided base list. NOTE: bare "vex" is deliberately EXCLUDED — it false-denied benign wrangle
    # CONFIG parms (vex_precision / vex_multithread / vex_cwdpath) while adding no security: the real
    # VEX code parms are caught by "snippet"/"vexpression" (names) AND the editorlang=VEX template layer,
    # and "vexcode" is caught by the "code" token. Wrangle VEX rides the VALIDATED set_attrib_expr path;
    # set_parm's snippet denial just stops it being an unvalidated-VEX backdoor around the validator.
    "snippet", "python", "code", "command", "expression", "vexpression", "callback",
    "script", "oncreated", "hscript", "pythonpanel", "commands", "presscmd",
    "beginscript", "endscript", "edit_script",
    # ROP / node pre|post SCRIPT command parms — NAME is their only catch (no editor tag, empty callback)
    "prerender", "postrender", "preframe", "postframe", "pretile", "posttile",
    "prebackground", "prescript", "postscript", "rendercommand",
)


def _name_is_code(name):
    low = name.lower()
    for tok in _CODE_NAME_TOKENS:
        if tok in low:
            return tok
    return None


# ── (1b) parm-TEMPLATE code detection — the real boundary ────────────────────────────────────────────
def _is_code_parm(parm):
    """Conservative "is this a code parm?" predicate. Returns (True, reason) if the parm can carry or
    trigger code and MUST NOT be written, else (False, None). Combines the NAME denylist (1a) and
    TEMPLATE inspection (1b). When in doubt, DENY."""
    # (1a) name
    tok = _name_is_code(parm.name())
    if tok is not None:
        return True, "name contains code token '%s'" % tok

    # (1b) template
    try:
        pt = parm.parmTemplate()
    except Exception as exc:  # noqa: BLE001 — cannot introspect => fail-closed
        return True, "parm template unreadable (%s); denied fail-closed" % (str(exc)[:60])

    # A Button fires its script callback when pressed.
    try:
        if pt.type() == hou.parmTemplateType.Button:
            return True, "button parm (press-callback)"
    except Exception:  # noqa: BLE001
        return True, "parm type unreadable; denied fail-closed"

    # tags: editorlang (definite code editor) or editor (multi-line editor — conservative deny).
    tags = {}
    try:
        tags = dict(pt.tags())
    except Exception:  # noqa: BLE001
        return True, "parm tags unreadable; denied fail-closed"
    lang = tags.get("editorlang")
    if lang:
        return True, "code-editor parm (editorlang=%s)" % lang
    if "editor" in tags:
        return True, "multi-line editor parm (editor tag; conservative deny)"

    # non-empty script callback => interactive code on press/change.
    try:
        cb = pt.scriptCallback()
    except Exception:  # noqa: BLE001
        cb = ""
    if cb:
        return True, "parm carries a script callback"

    return False, None


# ── (4) type coercion from the caller's string value to the parm's actual type ───────────────────────
_TRUE = frozenset(("1", "true", "yes", "on", "t", "y"))
_FALSE = frozenset(("0", "false", "no", "off", "f", "n", ""))


def _coerce(parm, value_str):
    """Coerce the caller's string ``value`` to the parm's template data type. Returns the coerced value
    ready for ``parm.set``. Raises ValueError on an unsettable parm type or a non-coercible value.
    Expression-language values are rejected earlier (set_parm, before coercion); the string/menu
    branches re-check as belt-and-suspenders."""
    pt = parm.parmTemplate()
    t = pt.type()

    if t == hou.parmTemplateType.Toggle:
        s = value_str.strip().lower()
        if s in _TRUE:
            return 1
        if s in _FALSE:
            return 0
        try:
            return 1 if float(s) != 0.0 else 0
        except ValueError:
            raise ValueError("toggle value must be 0/1/true/false, got %r" % value_str)

    if t == hou.parmTemplateType.Int:
        s = value_str.strip()
        try:
            return int(s)
        except ValueError:
            try:
                return int(round(float(s)))
            except ValueError:
                raise ValueError("int value not coercible: %r" % value_str)

    if t == hou.parmTemplateType.Float:
        try:
            return float(value_str.strip())
        except ValueError:
            raise ValueError("float value not coercible: %r" % value_str)

    if t == hou.parmTemplateType.String:
        _reject_expr_value(value_str)
        if _is_file_reference(pt):
            return _confine_file_value(value_str)   # (5) confine file-path parms to the working dir
        return value_str

    if t == hou.parmTemplateType.Menu:
        # Menu parms accept an integer index or a token string. Prefer int when the value is an
        # integer literal, else set the token (expression-rejected as a string).
        s = value_str.strip()
        try:
            return int(s)
        except ValueError:
            _reject_expr_value(value_str)
            return value_str

    raise ValueError("parm type %s is not a settable literal parm" % t)


def _resolve_parm(node, name, index):
    """Resolve a single scalar parm on ``node``. Primary path: ``node.parm(name)`` (handles a tuple
    component like ``tx``). If that misses and ``name`` is a parmTuple, an ``index`` selects the
    component. Raises ValueError if nothing resolves."""
    p = node.parm(name)
    if p is not None:
        return p
    pt = node.parmTuple(name)
    if pt is not None:
        if index is None:
            raise ValueError(
                "'%s' is a multi-component parm tuple on %s; pass a component name (e.g. '%sx') or an index"
                % (name, node.path(), name))
        try:
            idx = int(index)
        except (ValueError, TypeError):
            raise ValueError("index must be an integer, got %r" % index)
        if idx < 0 or idx >= len(pt):
            raise ValueError("index %d out of range for parm tuple '%s' (len %d)" % (idx, name, len(pt)))
        return pt[idx]
    raise ValueError("no such parm '%s' on node %s" % (name, node.path()))


def _parm_type_name(parm):
    try:
        return str(parm.parmTemplate().type()).split(".")[-1]
    except Exception:  # noqa: BLE001
        return "?"


@endpoint("set_parm")
def set_parm(params):
    """Set ONE node parameter to a LITERAL value. SECURITY-CRITICAL — see the module docstring.

    params: node (NodePath), parm (parm/component name, e.g. 'tx' or 'group'), value (Str; coerced to
    the parm's type), index (optional int, only for targeting a component of a parm tuple by the tuple
    name). Refuses (ValueError) any code-carrying parm, any expression-language string value, any
    unsettable parm type, and any value that cannot coerce. Writes via ``parm.set`` only (keyframes
    cleared first) — NEVER ``setExpression``."""
    node = resolve_node(params["node"])
    name = str(params["parm"])
    value_str = params["value"]
    if value_str is None:
        raise ValueError("value is required")
    value_str = str(value_str)
    index = params.get("index", None)

    parm = _resolve_parm(node, name, index)

    # (1) DENY code parms BEFORE any set.
    is_code, reason = _is_code_parm(parm)
    if is_code:
        raise ValueError(
            "REFUSED: '%s' on %s is a code-carrying parm and cannot be set (%s)"
            % (parm.name(), node.path(), reason))

    # (2) DENY expression-language values BEFORE type coercion — so a numeric parm gets the data-only
    #     boundary lesson, not a bare "not coercible" type error. (A real number carries no `/$/op:.)
    _reject_expr_value(value_str)

    # (4) coerce (string/menu-token values are re-checked inside — harmless belt-and-suspenders).
    coerced = _coerce(parm, value_str)

    # (3) LITERAL-ONLY: clear any channel/keyframe/expression, then plain .set — never setExpression.
    try:
        parm.deleteAllKeyframes()
    except Exception:  # noqa: BLE001 — no keyframes to clear is fine
        pass
    try:
        parm.set(coerced)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("parm '%s' on %s could not be set to %r: %s"
                         % (parm.name(), node.path(), coerced, str(exc)[:120]))

    # verify + report the stored literal (readback proves it stuck as a literal, not an expression).
    try:
        stored_eval = parm.eval()
    except Exception:  # noqa: BLE001
        stored_eval = None
    has_expr = False
    try:
        parm.expression()
        has_expr = True
    except Exception:  # noqa: BLE001 — raises when the parm holds no expression (the expected case)
        has_expr = False
    return {"node": node.path(), "parm": parm.name(), "type": _parm_type_name(parm),
            "set": coerced, "value": stored_eval, "is_expression": has_expr,
            "keyframed": bool(parm.keyframes())}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# KEYFRAME tools — LITERAL-VALUE-ONLY animation. Same threat model as set_parm.
#
# A keyframe carries a numeric VALUE (never a caller expression) plus an interpolation TYPE. The
# interpolation type in Houdini is expression-driven (probe-confirmed H21.0.671: a keyframe read back
# from a parm always reports an interpolation builtin via ``expression()`` — the default is
# ``bezier()``). There is NO non-expression enum API for the interpolation TYPE — ``setSlope`` /
# ``setInSlope`` / ``setAccel`` only tune the tangents of an already-chosen bezier segment, they do not
# select constant/linear/cubic/etc. So interpolation MUST be applied via ``hou.Keyframe.setExpression``.
#
# ▶▶ THE ONE CONTROLLED EXCEPTION TO set_parm's "never setExpression" RULE ◀◀
# ``setExpression`` is called in EXACTLY ONE place below (``set_keyframe``), and it is fed EXCLUSIVELY
# from ``_INTERP_BUILTINS`` VALUES — a handler-controlled, closed allowlist of interpolation-function
# strings. The caller supplies a TOKEN ("bezier"); the handler maps token -> fixed builtin string
# ("bezier()"). A caller NEVER supplies the expression string, and a token not in the allowlist is
# REFUSED before any keyframe is built. This is the single audited exception; it can carry NOTHING but
# an allowlisted zero-argument interpolation builtin.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

# caller TOKEN -> fixed Houdini interpolation builtin string (the ONLY strings ever passed to
# setExpression). Zero-argument interpolation functions, probe-verified to apply + read back on H21.
_INTERP_BUILTINS = {
    "constant": "constant()",   # hold — step to the value, no interpolation
    "linear":   "linear()",     # straight line to the next key
    "cubic":    "cubic()",      # smooth cubic
    "bezier":   "bezier()",     # Houdini default; tangent-editable
    "quintic":  "quintic()",    # smoother (5th order)
    "ease":     "ease()",       # ease in and out
    "easein":   "easein()",     # ease in only
    "easeout":  "easeout()",    # ease out only
    "qlinear":  "qlinear()",    # quaternion-linear
    "spline":   "spline()",     # Catmull-Rom-style spline
}

# Parm template types that can hold a NUMERIC keyframe. String parms are refused (they'd need a
# hou.StringKeyframe, which is expression-carrying by nature — probe: a numeric hou.Keyframe on a
# String parm raises "Keyframe is of the wrong type"). Button/code parms are caught earlier by
# _is_code_parm; Ramp/Data/etc. fall through to refusal.
def _numeric_parm_type(parm):
    t = parm.parmTemplate().type()
    return t in (hou.parmTemplateType.Int, hou.parmTemplateType.Float,
                 hou.parmTemplateType.Toggle, hou.parmTemplateType.Menu)


def _coerce_keyframe_value(parm, value):
    """Coerce the caller's ``value`` to a NUMERIC keyframe value. A keyframe carries a literal number,
    never a caller expression: a string value is expression-rejected (backtick / '$' / 'op:') and then
    ``float()``-coerced, so any expression-looking value (e.g. ``ch("../x")``) fails coercion and is
    REFUSED. Int/Toggle/Menu parms round to an integral value. Raises ValueError on a non-numeric parm
    type or a non-numeric value."""
    if not _numeric_parm_type(parm):
        raise ValueError(
            "parm '%s' (type %s) cannot hold a numeric keyframe — only Int/Float/Toggle/Menu parms can"
            % (parm.name(), _parm_type_name(parm)))
    if isinstance(value, str):
        _reject_expr_value(value)  # loud refusal for backtick/$/op: before the float() attempt
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise ValueError("keyframe value must be numeric, got %r (a keyframe carries a value, "
                         "never an expression)" % (value,))
    t = parm.parmTemplate().type()
    if t in (hou.parmTemplateType.Int, hou.parmTemplateType.Toggle, hou.parmTemplateType.Menu):
        return float(int(round(f)))
    return f


def _kf_readback(kf):
    """Read one keyframe -> a data-only dict {frame, value, interpolation}. Guards KeyframeValueNotSet.
    ``interpolation`` is whatever ``expression()`` reports (the interpolation builtin for our keyframes;
    for a hand-authored scene it may be an arbitrary channel expression — reported verbatim as data)."""
    try:
        frame = kf.frame()
    except Exception:  # noqa: BLE001
        frame = None
    try:
        val = kf.value()
    except Exception:  # noqa: BLE001 — KeyframeValueNotSet when the key is expression-only
        val = None
    try:
        interp = kf.expression()
    except Exception:  # noqa: BLE001 — KeyframeValueNotSet when no expression is set
        interp = None
    return {"frame": frame, "value": val, "interpolation": interp}


@endpoint("set_keyframe")
def set_keyframe(params):
    """Set ONE keyframe on a numeric parm at a frame with a LITERAL numeric value + an optional
    allowlisted interpolation. SECURITY-CRITICAL — see the KEYFRAME block above.

    params: node (NodePath), parm (parm/component name, e.g. 'tx'), frame (number), value (numeric;
    coerced to the parm type), interpolation (optional token from _INTERP_BUILTINS — constant/linear/
    cubic/bezier/quintic/ease/easein/easeout/qlinear/spline), index (optional int for a tuple
    component). REFUSES: any code-carrying parm (_is_code_parm), any non-numeric parm type, any
    non-numeric / expression-looking value, and any interpolation token not in the allowlist. The
    interpolation is the ONLY thing that reaches setExpression, and only as a fixed allowlisted
    builtin — the caller never supplies an expression string."""
    node = resolve_node(params["node"])
    name = str(params["parm"])
    index = params.get("index", None)
    if "frame" not in params or params["frame"] is None:
        raise ValueError("frame is required")
    if "value" not in params or params["value"] is None:
        raise ValueError("value is required")
    try:
        frame = float(params["frame"])
    except (TypeError, ValueError):
        raise ValueError("frame must be numeric, got %r" % (params["frame"],))

    parm = _resolve_parm(node, name, index)

    # (1) DENY code parms BEFORE building or writing anything.
    is_code, reason = _is_code_parm(parm)
    if is_code:
        raise ValueError(
            "REFUSED: '%s' on %s is a code-carrying parm and cannot be keyframed (%s)"
            % (parm.name(), node.path(), reason))

    # (2) LITERAL numeric value (also type-gates the parm + expression-rejects a string value).
    kf_value = _coerce_keyframe_value(parm, params["value"])

    # (3) interpolation — FIXED ALLOWLIST only; caller supplies a token, never the expression string.
    interp_token = params.get("interpolation", None)
    interp_builtin = None
    if interp_token is not None:
        tok = str(interp_token).strip().lower()
        if tok not in _INTERP_BUILTINS:
            raise ValueError(
                "REFUSED: interpolation %r is not in the allowlist %s"
                % (interp_token, sorted(_INTERP_BUILTINS)))
        interp_builtin = _INTERP_BUILTINS[tok]  # handler-controlled string; never caller-supplied

    # (4) build + set the keyframe with a literal frame+value.
    kf = hou.Keyframe()
    kf.setFrame(frame)
    kf.setValue(kf_value)
    if interp_builtin is not None:
        # THE ONE CONTROLLED setExpression — allowlisted interpolation builtin ONLY.
        kf.setExpression(interp_builtin, hou.exprLanguage.Hscript)
    try:
        parm.setKeyframe(kf)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("could not set keyframe on '%s' at frame %s: %s"
                         % (parm.name(), frame, str(exc)[:120]))

    # readback proves the stored keyframe holds a literal value + an interpolation builtin.
    stored = None
    for kk in parm.keyframes():
        if abs(kk.frame() - frame) < 1e-6:
            stored = _kf_readback(kk)
            break
    return {"node": node.path(), "parm": parm.name(), "type": _parm_type_name(parm),
            "frame": frame, "set_value": kf_value,
            "interpolation": interp_builtin if interp_builtin is not None else "(default)",
            "keyframed": bool(parm.keyframes()), "keyframe": stored}


@endpoint("delete_keyframes")
def delete_keyframes(params):
    """Remove keyframes on a parm so it returns to a static literal value. Data-only — no code path.

    params: node (NodePath), parm (parm/component name), start (optional number), end (optional
    number), index (optional int for a tuple component). With neither start nor end, ALL keyframes are
    removed (``deleteAllKeyframes``). With a range, only keyframes whose frame is within [start, end]
    are removed (inclusive; ``deleteKeyframeAtFrame`` per key). After deletion the parm holds a plain
    literal value (mirrors set_parm's literal-only stance)."""
    node = resolve_node(params["node"])
    name = str(params["parm"])
    index = params.get("index", None)
    parm = _resolve_parm(node, name, index)

    start = params.get("start", None)
    end = params.get("end", None)
    before = [k.frame() for k in parm.keyframes()]

    if start is None and end is None:
        parm.deleteAllKeyframes()
        removed = before
    else:
        lo = float(start) if start is not None else float("-inf")
        hi = float(end) if end is not None else float("inf")
        removed = []
        for f in before:
            if lo <= f <= hi:
                try:
                    parm.deleteKeyframeAtFrame(f)
                    removed.append(f)
                except Exception:  # noqa: BLE001 — skip a key that won't delete at this exact frame
                    pass

    remaining = [k.frame() for k in parm.keyframes()]
    try:
        static_value = parm.eval()
    except Exception:  # noqa: BLE001
        static_value = None
    return {"node": node.path(), "parm": parm.name(), "type": _parm_type_name(parm),
            "removed_frames": removed, "removed_count": len(removed),
            "remaining_frames": remaining, "keyframed": bool(parm.keyframes()),
            "value": static_value}


@endpoint("list_keyframes")
def list_keyframes(params):
    """List a parm's keyframes — data-only, read-only. Returns each keyframe's frame, literal value,
    and interpolation (the keyframe's expression string, e.g. 'bezier()'), so an agent can see the
    animation. Never writes.

    params: node (NodePath), parm (parm/component name), index (optional int for a tuple component)."""
    node = resolve_node(params["node"])
    name = str(params["parm"])
    index = params.get("index", None)
    parm = _resolve_parm(node, name, index)

    keys = [_kf_readback(k) for k in parm.keyframes()]
    return {"node": node.path(), "parm": parm.name(), "type": _parm_type_name(parm),
            "keyframed": bool(keys), "count": len(keys), "keyframes": keys}


@endpoint("get_parm")
def get_parm(params):
    """Read ONE node parameter — data-only, read-only. Returns the evaluated value, the raw
    (unexpanded) value, the parm type, whether it currently holds an expression / keyframes, and
    whether it is a denied code parm (so an agent can see an injected expression). Never writes.

    params: node (NodePath), parm (parm/component name), index (optional int for a tuple component)."""
    node = resolve_node(params["node"])
    name = str(params["parm"])
    index = params.get("index", None)
    parm = _resolve_parm(node, name, index)

    try:
        evaluated = parm.eval()
    except Exception as exc:  # noqa: BLE001
        evaluated = "<eval error: %s>" % (str(exc)[:80])
    try:
        raw = parm.unexpandedString()          # string parms: the stored, unexpanded string
    except Exception:  # noqa: BLE001 — numeric parms have no unexpandedString
        try:
            raw = parm.rawValue()
        except Exception:  # noqa: BLE001
            raw = None
    has_expr = False
    expr = None
    try:
        expr = parm.expression()
        has_expr = True
    except Exception:  # noqa: BLE001
        has_expr = False

    is_code, reason = _is_code_parm(parm)
    return {"node": node.path(), "parm": parm.name(), "type": _parm_type_name(parm),
            "value": evaluated, "raw": raw, "is_expression": has_expr,
            "expression": expr, "keyframed": bool(parm.keyframes()),
            "is_code_parm": is_code, "code_parm_reason": reason}

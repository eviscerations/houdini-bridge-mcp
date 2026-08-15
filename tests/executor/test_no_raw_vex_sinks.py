"""Cloud-CI-safe STRUCTURAL guard (RT-11): no NEW raw-code-text sink may enter the executor unaudited.

The data-only boundary has two shape-based guards - the Rust `safe_vex_is_the_only_code_path` (inspects
gateway param *Kinds*) and the Python `_name_is_rce_shaped` (inspects *endpoint names*). A code-text sink
that is neither a `VexSnippet` param nor an RCE-named endpoint sits in the blind spot both share - that is
exactly how RT-12 (a `volumewrangle` snippet built by `%`-interpolating caller layer names in terrain.py)
slipped past both. This test closes that gap the way the red-team recommended: it scans handler SOURCE for
every place a snippet / VEX-expression / Python-SOP parm handle is taken, or `setExpression` is called, and
fails the build if any appears outside the AUDITED allowlist below. New sink in a new file, or an extra sink
in an audited file -> the build goes red until a human re-audits it. It is what would have caught RT-12 at
authoring time, and - at this project's tool velocity - the guardrail against the first-gen pattern recurring.

It tokenizes (does not regex raw text), so a sink named inside a docstring or comment is a single STRING
token and never counts - only real code does. Runs on a bare runner: `python tests/executor/test_no_raw_vex_sinks.py`.

Each audited site is safe for a stated, verified reason:
  * numeric-only interpolation (`%g`/`%d`/`%.9g` + matrix tuples) - no caller string reaches VEX text;
  * `%r`-escaped CONFINED filesystem paths (repr always yields a valid, escaped string literal);
  * `validate_ident()`-gated bare identifiers (attribute / layer / mask names - RT-12 fix);
  * a single allowlisted zero-arg interpolation builtin (`set_keyframe`'s `setExpression`);
  * the ONE validated safe-VEX lane (`vexwrangle`, gated by `vex_validator.validate_attrib_vex`).
"""
import os
import sys
import token as _tok
import tokenize

_HERE = os.path.dirname(os.path.realpath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_EXECUTOR = os.path.join(_REPO, "houdini_executor")

# Parm names that carry EXECUTABLE code text (VEX / Python-SOP / OpenCL / HScript). Taking a handle to one
# of these, or calling setExpression, is a code-text sink that must be audited.
CODE_PARMS = {"snippet", "vexpression", "python", "opencl", "kernel", "hscript", "pickscript",
              "cvex_snippet", "cvexsnippet", "vexpressions"}

# AUDITED allowlist: filename -> (expected sink count, why every sink in it is injection-safe). Keep the
# reason specific - this is the human sign-off the build enforces. Bump a count ONLY after re-verifying.
AUDITED = {
    "analysis.py": (5, "numeric-only interpolation (%g/%d/%.9g + matrix tuples from geometry bbox); "
                       "no caller-controlled string reaches the VEX text"),
    "acquire.py": (6, "snippets are int-clamped (downsample) / fixed-constant / %r-escaped CONFINED paths "
                      "/ computed floats; the two python SOPs (import_heightfield, import_ecef_tile) "
                      "interpolate ONLY a confined path via %r (repr yields an escaped literal)"),
    "terrain.py": (3, "fill/morph layer/mask/seed names are validate_ident()-gated to bare identifiers "
                      "before interpolation into the volumewrangle snippet (RT-12 fix)"),
    "parms.py": (1, "the single controlled setExpression = set_keyframe, fed ONLY an allowlisted zero-arg "
                    "interpolation builtin (never caller text)"),
    "model.py": (1, "create_curve python SOP interpolates json.dumps() of a float-sanitized point list "
                    "(a numeric literal only)"),
    "vexwrangle.py": (1, "the ONE validated safe-VEX lane - the snippet is checked by "
                         "vex_validator.validate_attrib_vex (allowlist-first) BEFORE it is set"),
}

FAIL = []


def _scan_file(path):
    """Return the list of (lineno, kind) code-text sinks in one file, via tokenization."""
    with open(path, "rb") as fh:
        try:
            toks = list(tokenize.tokenize(fh.readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return [("?", "unparseable")]  # a file we can't tokenize is itself a finding
    sinks = []
    # Keep only real NAME/OP/STRING tokens (comments + NL are ignored -> docstring mentions never match,
    # because a docstring is a single STRING token, not the NAME('parm') OP('(') STRING(name) sequence).
    core = [t for t in toks if t.type in (_tok.NAME, _tok.OP, _tok.STRING, _tok.NUMBER)]
    for i, t in enumerate(core):
        # (a) setExpression( call
        if t.type == _tok.NAME and t.string == "setExpression":
            nxt = core[i + 1] if i + 1 < len(core) else None
            if nxt and nxt.type == _tok.OP and nxt.string == "(":
                sinks.append((t.start[0], "setExpression"))
        # (b) .parm("<code-param>") handle:  NAME('parm') OP('(') STRING(code_param) OP(')')
        if t.type == _tok.NAME and t.string == "parm":
            if (i + 3 < len(core) and core[i + 1].type == _tok.OP and core[i + 1].string == "("
                    and core[i + 2].type == _tok.STRING):
                lit = core[i + 2].string
                val = lit[1:-1] if len(lit) >= 2 and lit[0] in "'\"" else lit
                # strip an optional string prefix like r"" / f"" (rare here) is unnecessary: these are plain
                if val in CODE_PARMS:
                    sinks.append((t.start[0], 'parm("%s")' % val))
    return sinks


def main():
    found = {}  # filename -> list[(lineno, kind)]
    for root, _dirs, files in os.walk(_EXECUTOR):
        if "__pycache__" in root:
            continue
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            sinks = _scan_file(os.path.join(root, f))
            if sinks:
                found[f] = sinks

    print("code-text sink audit (RT-11) - scanned houdini_executor/**/*.py")
    print("=" * 90)
    all_files = sorted(set(found) | set(AUDITED))
    for f in all_files:
        got = found.get(f, [])
        n = len(got)
        exp = AUDITED.get(f)
        if exp is None:
            FAIL.append("%s: %d UNAUDITED code-text sink(s) at lines %s - new sink must be reviewed + added "
                        "to AUDITED with a why" % (f, n, [ln for ln, _ in got]))
            print(" FAIL %-16s %d sink(s) NOT in the audited allowlist %s" % (f, n, [ln for ln, _ in got]))
            continue
        want, why = exp
        if n != want:
            FAIL.append("%s: audited count %d != found %d (lines %s) - re-audit each site, then update the "
                        "count" % (f, want, n, [ln for ln, _ in got]))
            print(" FAIL %-16s found %d, audited %d  %s" % (f, n, want, [ln for ln, _ in got]))
        else:
            print("  OK  %-16s %d sink(s) - %s" % (f, n, why[:60] + ("..." if len(why) > 60 else "")))

    print("=" * 90)
    print("RT-11 code-text sink guard:", "ALL GREEN" if not FAIL else "FAILURES:")
    for m in FAIL:
        print("   -", m)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

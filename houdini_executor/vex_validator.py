"""Safe-VEX attribute-expression validator (profile ``attrib_v1``).

THE SECURITY BOUNDARY for the optional ``set_attrib_expr`` tool. Pure Python, NO ``hou`` import, so it
is unit-testable standalone and runs identically in the gateway pre-check and the executor's
authoritative check.

Posture (all enforced below; any violation RAISES ``VexValidationError`` — never sanitize-and-proceed):

  * **Allowlist-first.** Every called identifier MUST be in ``ALLOWED_FUNCS``. A novel/unknown function
    (incl. every file-read/`ch*`/`op*`/write function) is rejected by OMISSION, not by blocklist —
    because ``#include`` can smuggle arbitrary code, a denylist-only filter is unsound.
  * **No language escapes.** ``#`` (preprocessor/``#include``), backtick (hscript ``\`system()\```),
    ``$`` (hscript/env var), and stray ``\\`` are rejected on the raw string before anything else.
  * **Not Turing-complete.** ``while/do/gather`` and ``function``/``struct`` definitions stay banned
    (``while``/``do`` are runtime-conditioned = unbounded; ``gather`` spawns rays). Two LOOP forms are
    allowed, BOTH only under the opt-in ``allow_loops`` flag (default OFF): (1) ``for`` as a
    STATICALLY-BOUNDED counted loop — the header must carry a literal or ``min()``-clamped ceiling (see
    ``_validate_for_header``); (2) ``foreach`` over an array — VEX ``foreach`` SNAPSHOTS the iterated
    array's length at entry (probe-verified: appending inside does NOT extend iteration), so it is ALWAYS
    FINITE (iterations == entry length), never infinite, even though the length is runtime not static. To
    keep a runtime iteration count from being AMPLIFIED, ``foreach`` is LEAF-ONLY: it may not be nested
    inside any loop, nor contain any loop (see ``_validate_foreach_header`` + the loop stack). The accepted
    subset stays TOTAL / not Turing-complete. This does NOT eliminate the main-thread DoS, it BOUNDS it:
    an accepted loop runs a FINITE number of iterations, but there is no mid-cook watchdog, so a bounded
    loop over a huge mesh/array can still cook slowly-but-finitely — the human fires the cook.
  * **No filesystem semantics.** String literals may not contain a path separator (``/`` ``\\``), a
    drive/`op:` colon (``:``), or ``..``.
  * **Writes are gated.** Only attribute BINDINGS (``@attr = ...`` / ``f@x += ...``) and the outputs-gated
    named-attribute/group writers may write, and only to attributes the caller DECLARED in ``outputs``.
    Reads of current-geometry bindings are unrestricted. DELETION-only topology writers (``removepoint`` /
    ``removeprim`` on input-0) are permitted ONLY under the opt-in ``allow_geoedit`` flag (default OFF, a
    SEPARATE consent from ``allow_attrib_expr`` / ``allow_loops`` — enabling writes/loops does NOT grant
    deletion) and ONLY when arg0 is the literal input index ``0`` (the cooked sandbox geometry). They are
    NOT ``outputs``-gated (they address no named attribute — the consent flag is the scope gate, arg0==0
    the target gate); deletion is monotone-shrinking / self-bounding. CONSTRUCTION/GROWTH writers
    (``addpoint``/``addprim``/``addvertex``/``removevertex``) stay excluded (a categorically bigger risk).
  * **Bounded.** ASCII-only; length / line / token / call / nesting caps.

v1 deliberately EXCLUDES cross-element reads (``point``/``prim``/``primpoint``/…) and component/array
writers — they are a documented v2 extension (needs integer-input-arg enforcement). v1 covers exactly
the cited RBD/sim cases: ``s@constraint_name="glue"; f@strength=fit(@dist,0,1,100,0); @Cd=set(1,0,0);
i@broken = @P.y < 0;`` — attribute binds + math + string naming + comparisons + if/else.
"""


class VexValidationError(ValueError):
    """Raised (fail-closed) when a snippet violates the safe-VEX profile. Message = the failing rule."""


# ── bare-identifier gate ───────────────────────────────────────────────────────────────────────────
# A few handlers interpolate a caller-supplied attribute / heightfield-LAYER name into VEX snippet TEXT
# (e.g. terrain's fill/morph volumewrangles bind `@<layer>`). Those names are identifiers by definition,
# so gating them to the identifier charset costs ZERO capability while closing the raw-VEX injection
# vector — a name like `height; <arbitrary VEX>` can no longer smuggle statements past the assignment.
# Explicit ASCII sets (not a regex) keep it homoglyph-proof and ReDoS-free, matching this module's
# hand-tokenizer style.
_IDENT_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_IDENT_CONT = _IDENT_START | set("0123456789")
_MAX_IDENT_LEN = 64


def validate_ident(name, what="attribute/layer name"):
    """Fail-closed: return `name` iff it is a bare VEX identifier (``[A-Za-z_][A-Za-z0-9_]*``, <=64 ASCII
    chars); otherwise raise VexValidationError. Use this on any caller string interpolated into VEX text
    that is semantically an attribute / layer / group NAME."""
    if not isinstance(name, str) or not name:
        raise VexValidationError("%s must be a non-empty string" % what)
    if len(name) > _MAX_IDENT_LEN:
        raise VexValidationError("%s too long (max %d chars)" % (what, _MAX_IDENT_LEN))
    if name[0] not in _IDENT_START or any(c not in _IDENT_CONT for c in name):
        raise VexValidationError(
            "%s %r is not a bare identifier ([A-Za-z_][A-Za-z0-9_]*) — refused to prevent VEX injection"
            % (what, name))
    return name


# ── the positive allowlist: pure, in-memory, side-effect-free, current-geometry-only ──────────────
_MATH = (
    "abs sign sqrt cbrt pow exp exp2 log log10 sin cos tan asin acos atan atan2 sinh cosh tanh "
    "floor ceil round rint trunc frac fmod min max clamp fit fit01 fit11 efit lerp invlerp bias "
    "gain smooth smoothstep sum avg hypot radians degrees "
    "isfinite"                                  # [corpus expansion] pure finite-number predicate (float -> int), no side effect
)
_VECMATRIX = (
    "length length2 distance distance2 dot cross normalize reflect refract project ident transpose "
    "determinant invert rotate qrotate quaternion qmultiply qconvert slerp dihedral lookat "
    "maketransform cracktransform"
)
_NOISE = (
    "noise snoise vnoise anoise onoise pnoise xnoise wnoise flownoise turb curlnoise curlnoise2d "
    "curlxnoise rand random nrandom hash "
    "random_shash"                              # [corpus expansion] pure string->int hash (deterministic seed), no I/O
)
_INTERP = "cubic spline bilerp trilerp"
_ACCESS = "set getcomp"                     # set() = constructor (returns), getcomp = read. NO setcomp (write).
# pure string value-ops (no path/geo/node reach). join/split/match (corpus expansion):
# split(str[,sep])->str[], join(str[],spacer)->str, match(pattern,subject)->int (pure glob predicate).
_STRINGS = "sprintf itoa atoi atof strlen concat join split match"
_DIAG = "printf warning error"
_CASTS = "int float vector vector2 vector4 matrix matrix2 matrix3 string"
# Current-geometry / wired-input reads (measuring, grouping, topology, FIELD SAMPLING, packed-intrinsic
# and collision reads — the essential sim/physics + modeling/character surface). Every GEO_READ call's
# FIRST argument MUST be an integer input index 0-3 (enforced in the call check below), NEVER a string
# geometry source — so an "op:/..." node path or a disk file (e.g. a VDB) cannot be reached. Inputs are
# wired by the typed tool, so an index only reaches controlled geo/fields.
# [cross-domain union, catalog-verified H21.0.671]
_GEO_READ = (
    "point prim vertex detail pointattrib primattrib vertexattrib detailattrib npoints nprims "
    "nvertices vertexcount primvertexcount primpoint primpoints primvertices pointvertex pointvertices "
    "vertexpoint vertexprim pointprims nearpoint nearpoints xyzdist primuv minpos "
    "neighbour neighbours neighbourcount degree "
    "inpointgroup inprimgroup invertexgroup inedgegroup expandpointgroup "
    # volume / field sampling (pyro + FLIP field reads) — the physics field-shaping surface
    "volumesample volumesamplev volumesamplei volumesamplep volumesampleu volumecubicsample "
    "volumecubicsamplev volumesmoothsample volumesmoothsamplev volumegradient volumeindex volumeindexv "
    "volumeindexi volumeindexp volumeindexu volumeindextopos volumepostoindex volumeindexorigin "
    "volumeindexactive volumeres volumevoxeldiameter volumetypeid volume "
    # RBD packed-transform / intrinsic READ (NOT the setprimintrinsic writer), collision/ray/search reads
    "primintrinsic intersect filamentsample pgfind "
    # measure / bbox reads (getbbox = the SAFE <geometry> twin of the DENIED string-filename getbounds)
    "getbbox getbbox_center getbbox_max getbbox_min getbbox_size getpointbbox getpointbbox_center "
    "getpointbbox_max getpointbbox_min getpointbbox_size relbbox relpointbbox surfacedist windingnumber "
    "windingnumber2d uvdist "
    # KineFX joint world-transform READ (its escape twin optransform(string path) stays DENIED)
    "pointtransform "
    # [corpus expansion] additional current-geometry READS — each has <geometry> as its FIRST
    # arg, so the GEO_READ integer-input-index (0-3) gate below applies verbatim: a string geo source / disk
    # file / "op:/..." node path can never reach them. All are pure reads (existence / lookup / topology /
    # normal), zero writes, zero external state. [cook-verified against the H21.0.671 VEX cookbook corpus]
    "hasattrib haspointattrib "                 # attribute-existence predicates (input, class/name) -> int
    "findattribval idtopoint "                  # value/id -> element-number lookups on the wired input
    "hedge_equivcount pointhedge pointhedgenext vertexprimindex "  # half-edge / vertex topology reads
    "prim_normal "                              # primitive normal at parametric (u,v) — pure geo read
    # [borderline item (b)] agent-primitive READS (crowd) — each takes the input
    # index as its FIRST arg, so the int-input-index (0-3) gate below applies verbatim. Pure reads of the
    # wired agent definition (clip catalog/names/length/times, rig-joint find, joint world-transform);
    # zero writes, zero external state. The agent WRITERS (setagentclip*) stay DENIED.
    "agentclipcatalog agentclipnames agentcliplength agentcliptimes agentrigfind agentworldtransform "
    # [borderline item (d)] point-cloud NEIGHBOUR QUERY on a wired geometry INPUT. pcopen/
    # pcfind take the INPUT INDEX as their first arg, so the int-input (0-3) gate refuses the unsafe
    # string-filename `.pc` FILE overload (pcopen("x.pc",...)) — reclassifying them from the old blanket
    # "pc = file read" deny. Same wired-input read surface as point()/volumesample(). The loop-only
    # handle members pciterate/pcimport stay DENIED (their idioms need the banned loops anyway, and
    # pcimport writes by reference). pcnumfound/pcfilter (handle-based, no geo/path arg) are pure — below.
    "pcopen pcfind"
)
GEO_READ_FUNCS = frozenset(_GEO_READ.split())

# Pure compute, NO geometry arg (so NOT gated): conversions, distribution samplers, KineFX/modeling
# local-matrix math (operate on a local `matrix` var by reference — no geo, no path), and pure in-memory
# array ops (bounded by the no-loop rule). All side-effect-free.
_PURE_EXT = (
    "eulertoquaternion qconvert planepointdistance "
    "sample_direction_cone sample_direction_uniform sample_hemisphere sample_sphere_uniform "
    "combinelocaltransform extractlocaltransform makebasis prerotate rotate translate scale "
    "polardecomp diagonalizesymmetric svddecomp "
    "array len resize append push pop insert removeindex removevalue reorder sort argsort slice reverse find "
    # [borderline item (d)] point-cloud HANDLE queries: pcnumfound(handle)->int and
    # pcfilter(handle, channel)->value operate on a handle produced by the (input-gated) pcopen, so they
    # can only ever touch a wired-input cloud — no geo/path/file arg of their own. Pure reads.
    "pcnumfound pcfilter"
)

# Channel / ramp PARAMETER reads on the CURRENT node, by name, returning the parm's value (pure, no I/O,
# no geo write, cannot execute code): ch/chf(->float) chi(->int) chv(->vector) chp(->vector4)
# ch2/ch3/ch4(->matrix2/3/4) chs(->string), and chramp(name,pos) (ramp lookup).
# [corpus expansion] The `ch*` family is the single biggest cookbook unlock: it
# is how tunables/sliders are referenced (blocks 143 of the 238 corpus idioms on its own). Each takes a
# channel NAME as its FIRST arg that COULD be a cross-node path ("../other/tx", "/obj/geo1/tx",
# "op:/..."), so ALL are GATED IDENTICALLY below (the same gate long applied to chramp): arg0 must be a
# bare local parameter-name string literal (no '/', '..' or ':') — reach to another node's parm is
# refused, keeping them strictly current-node-only. They READ a parameter value; no write surface.
_CHAN = "chramp ch chf chi chv chs chp ch2 ch3 ch4"
CHANNEL_NAME_FUNCS = frozenset(_CHAN.split())

# Attribute / group WRITERS — the v2 extension the design
# anticipated, now soundly enforceable with the arg-position gating proven by the GEO_READ / ch* gates.
# Each writes a NAMED attribute/group on the COOKED input-0 geometry:
#   set{point,prim,vertex,detail}attrib(0, "name", elem, value[, "mode"])
#   set{point,prim,vertex}group(0, "name", elem, onoff[, "mode"])
# GATED below to the SAME `outputs` contract as an `@name = ...` binding: arg0 must be the literal input
# index 0, arg1 must be a bare-name string literal that is in the declared `outputs`. That makes them
# EXACTLY as safe as a binding — same outputs allowlist, same sandbox geometry — just addressing a named
# element instead of the current one. A COMPUTED name (e.g. sprintf(...)) rejects (arg1 not a literal).
# [borderline item (b)] Topology writers (add*/remove*) and agent writers
# (setagentclip*) stay DENIED — those are geometry/crowd EDITING, a separate future `geo_edit` ruling.
_ATTR_WRITE = ("setpointattrib setprimattrib setvertexattrib setdetailattrib "
               "setpointgroup setprimgroup setvertexgroup")
ATTR_WRITE_FUNCS = frozenset(_ATTR_WRITE.split())
# setcomp(dst, value, i[, j]) writes a COMPONENT of its first arg. On a LOCAL variable it is pure
# in-memory mutation (safe — the KineFX matrix-compose idiom). On an `@attr` binding it is an attribute
# write → the attr name must be in `outputs` (gated in the call check below alongside ATTR_WRITE_FUNCS).
_SETCOMP = "setcomp"

# Topology DELETION writers — the geo_edit ruling. DELETION-ONLY
# v1: removepoint(0, ptnum) / removeprim(0, primnum[, and_points]) delete an element of the COOKED input-0
# sandbox geometry. GATED below (in the call check) behind BOTH the default-off ``allow_geoedit`` consent
# (a SEPARATE flag from ``allow_attrib_expr`` / ``allow_loops`` — enabling writes/loops does NOT grant
# deletion) AND arg0 == the literal input index 0 (NOT read-only inputs 1-3, NOT a computed/attr source).
# NOT ``outputs``-gated: topology edits address no named attribute, so the consent flag IS the scope gate
# and arg0==0 is the target gate. Deletion is monotone-shrinking / self-bounding (no growth cap needed).
_GEO_EDIT = "removepoint removeprim"
GEO_EDIT_FUNCS = frozenset(_GEO_EDIT.split())

# Topology CONSTRUCTION / GROWTH writers — the geo_grow ruling (owner-ratified). addpoint /
# addprim / addvertex (construction) and removevertex (structure-editing) mutate the topology of the COOKED
# input-0 sandbox geometry. GATED below (in the call check) behind a THIRD default-off consent
# ``allow_geogrow`` — ORTHOGONAL to ``allow_attrib_expr`` / ``allow_loops`` / ``allow_geoedit`` (graduated
# consent: enabling deletion does NOT silently grant GROWTH, which is a categorically different risk —
# deletion is self-bounding, construction is not) — AND arg0 == the literal input index 0 (NOT read-only
# inputs 1-3, NOT a computed/attr source), exactly mirroring the GEO_EDIT arg0/comma gate. NOT
# ``outputs``-gated (they address no named attribute; addpoint/addprim/addvertex RETURN the new element
# number, they do not write a named attr). Honest posture: growth has no STATIC total cap (adds are
# per-element × loop-iters) → "big-but-finite, not infinite; the human fires the cook" — the same downgrade
# accepted for loops; runtime memory is the governor's job, not the static validator's.
_GEO_GROW = "addpoint addprim addvertex removevertex"
GEO_GROW_FUNCS = frozenset(_GEO_GROW.split())

ALLOWED_FUNCS = frozenset((
    _MATH + " " + _VECMATRIX + " " + _NOISE + " " + _INTERP + " " + _ACCESS + " "
    + _STRINGS + " " + _DIAG + " " + _CASTS + " " + _GEO_READ + " " + _PURE_EXT + " " + _CHAN
    + " " + _ATTR_WRITE + " " + _SETCOMP + " " + _GEO_EDIT + " " + _GEO_GROW
).split())

# Defense-in-depth: names that LOOK like safe reads/measures but are genuine ESCAPES (file read, node
# reach, or writers that bypass the `outputs` gate). Already denied by OMISSION from the allowlist; listed
# EXPLICITLY so a future edit cannot accidentally allowlist one, and so the rejection message names the
# reason.
_EXPLICIT_DENY = frozenset((
    "getbounds "                                        # string-filename bbox FILE-READ (the sharpest trap; getbbox is the safe twin)
    "optransform opdigits opfullpath opid oprawparmtransform "   # node-path reach
    # NB set{point,prim,vertex,detail}attrib / set{point,prim,vertex}group / setcomp are NO LONGER denied
    # here — they moved to ATTR_WRITE_FUNCS/_SETCOMP, allowlisted UNDER the outputs-gate (item (b)). The
    # writers that remain denied are the ones with NO named-attr contract to gate against `outputs`:
    "setattrib setprimintrinsic setattribtypeinfo setedgegroup "                 # arbitrary-target / intrinsic / metadata / edge-group writers
    # NB addpoint/addprim/addvertex/removevertex are NO LONGER denied here — they moved to GEO_GROW_FUNCS,
    # allowlisted UNDER the default-off allow_geogrow consent (arg0==0 gate). Deletion writers removepoint/
    # removeprim are in GEO_EDIT_FUNCS (consent-gated by allow_geoedit).
    "setagentclipnames setagentcliptimes setagentclipweights "                   # agent-primitive writers (crowd editing, deferred)
    # pc: pcopen/pcfind/pcnumfound/pcfilter are now ALLOWED (input-gated geo neighbour query, item (d)).
    # These stay DENIED: pciterate/pcimport are loop-only (their idioms need the banned loops; pcimport
    # writes by reference), and pcopenlod/pcgenerate/pcwrite/pcexport are `.pc` FILE read/write.
    "pcimport pciterate pcopenlod pcgenerate pcwrite pcexport "
    "getattrib "                                        # redundant cross read; excluded to keep the surface minimal
    "texture texture3d colormap file_stat metaimport getenv environment "       # file / env reads
).split())

# control-flow / declaration keywords: `if`/`else`/`return` are fine; these are banned outright.
# [borderline item (c) — UPDATED for bounded loops + foreach] `while`/`do`/`gather` (and
# `function`/`struct` definitions) STAY banned: `while`/`do` are runtime-conditioned (unbounded) and
# `gather` spawns rays — none carries a finite, non-amplifiable iteration count. `for` and `foreach` are
# NO LONGER banned here — each is recognized SEPARATELY under the opt-in `allow_loops` flag:
#   * `for`     — a STATICALLY-bounded counted loop (`_validate_for_header`, literal/min() ceiling).
#   * `foreach` — an array loop that VEX SNAPSHOTS at entry (probe-verified: appending inside does NOT
#                 extend iteration), so iterations == the entry length = FINITE (runtime, not static).
#                 Recognized by `_validate_foreach_header`; LEAF-ONLY (may neither nest in nor contain any
#                 loop) so a runtime count can never be amplified by an enclosing/enclosed loop.
# Both are woven into `validate_attrib_vex`'s single structural pass via the loop stack, keeping the subset
# TOTAL / not Turing-complete. There is still NO cook-interrupting watchdog (server.run_on_main cancels
# only UN-STARTED jobs; a running cook cannot be interrupted), so the honest guarantee is "bounded, not
# infinite" — a bounded loop can cook slowly-but-finitely, and the human fires the cook. Do NOT allowlist
# while/do/gather here.
BANNED_KEYWORDS = frozenset("while do gather function struct".split())
# keywords that may legally precede `(` without being a function call.
_CTRL_BEFORE_PAREN = frozenset("if else return".split())

_ASSIGN_OPS = frozenset("= += -= *= /= %= &= |= ^= <<= >>=".split())

# Functions that WRITE their first argument BY REFERENCE. A loop counter passed as arg0 to one of these is
# mutated without an assignment op — e.g. `setcomp(i, 0, 0)` resets the counter → a runtime-UNBOUNDED loop
# that defeats the static iteration cap. The counter-mutation guard rejects the loop counter as arg0 of any
# of these. `setcomp` is the one that applies to a scalar `int` counter; the array mutators are included
# defensively (the counter is always declared `int`, so they would type-error, but fail-closed > clever).
_BYREF_MUTATORS = frozenset(
    "setcomp resize append push pop insert removeindex removevalue reorder sort argsort reverse".split())

# Allowlisted functions with a WRITABLE `int &` export parameter (audited against reference/vex_functions.json).
# A loop counter (declared `int`) passed to one of these can land on the int& export slot (the
# slot POSITION varies by overload — `&success` / `&seed` / `&prim` / `&closest_pt`) and be MUTATED, resetting
# the counter → an infinite loop that defeats the static iteration cap (red-team RT-30). Because the export
# slot is not statically distinguishable from a legitimate int READ arg across overloads, the loop counter is
# rejected ANYWHERE in these calls' arg lists (fail-closed; read uses have a safe by-value twin such as
# point()/prim()/primattrib-via-point). RE-AUDIT THIS LIST whenever a new function is added to ALLOWED_FUNCS.
_INT_EXPORT_ARG_FUNCS = frozenset(
    "detailattrib pointattrib primattrib vertexattrib surfacedist uvdist vnoise wnoise xyzdist".split())

# caps (inner guards; server.py's 1 MB body cap is the outer one)
_MAX_LEN = 2048
_MAX_LINES = 40
_MAX_TOKENS = 400
_MAX_CALLS = 40
_MAX_DEPTH = 16

# bounded-loop caps (active ONLY under the opt-in `allow_loops` flag; enforced by `_validate_for_header`
# + the loop stack in `validate_attrib_vex`). These carry the DYNAMIC story that the STATIC `_MAX_CALLS`/
# `_MAX_TOKENS`/`_MAX_DEPTH` occurrence-counts no longer do once a body may repeat.
_MAX_LOOP_ITERS         = 1024   # per-loop static ceiling / iteration count
_MAX_LOOP_NESTING       = 2      # max simultaneously-open counted loops
_MAX_LOOP_ITERS_PRODUCT = 4096   # product of open-loop ceilings (blocks e.g. 1024x1024 nesting)
_MAX_LOOP_BODY_TOKENS   = 200    # tokens inside any single loop body

_ALLOWED_ESCAPES = frozenset("ntr\"\\%0")          # inside a string literal, only these follow a backslash
_IDENT_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_@"
)


def _reject(msg):
    raise VexValidationError(msg)


def _tokenize(code):
    """Single-pass lexer. Skips comments; parses/validates string literals; emits (kind, value)
    tokens where kind in {id, num, str, op, punct}. Raises on any malformed/dangerous construct."""
    tokens = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        # whitespace
        if c in " \t\r\n":
            i += 1
            continue
        # comments (string-aware because we only reach here outside a string)
        if c == "/" and i + 1 < n and code[i + 1] == "/":
            i += 2
            while i < n and code[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and code[i + 1] == "*":
            i += 2
            while i < n and not (code[i] == "*" and i + 1 < n and code[i + 1] == "/"):
                i += 1
            if i >= n:
                _reject("unterminated block comment")
            i += 2
            continue
        # string literal
        if c == '"':
            j = i + 1
            buf = []
            while j < n:
                ch = code[j]
                if ch == "\\":
                    if j + 1 >= n:
                        _reject("unterminated escape in string literal")
                    esc = code[j + 1]
                    if esc not in _ALLOWED_ESCAPES:
                        _reject("disallowed escape '\\%s' in string literal" % esc)
                    buf.append(esc if esc not in "ntr" else " ")   # normalize whitespace escapes
                    j += 2
                    continue
                if ch == '"':
                    break
                buf.append(ch)
                j += 1
            if j >= n:
                _reject("unterminated string literal")
            body = "".join(buf)
            # no filesystem / path / node-path semantics inside literals
            if "/" in body or "\\" in body:
                _reject("path separator in string literal")
            if ":" in body:
                _reject("colon (drive/op: path) in string literal")
            if ".." in body:
                _reject("parent-traversal '..' in string literal")
            tokens.append(("str", code[i:j + 1]))
            i = j + 1
            continue
        # number (and digit-prefixed binding like 3@orient / 16@xform)
        if c.isdigit() or (c == "." and i + 1 < n and code[i + 1].isdigit()):
            j = i
            while j < n and (code[j].isdigit() or code[j] in ".eExXaAbBcCdDfF+-"):
                # keep it simple: consume a numeric-ish run; exact numeric grammar is not security-relevant
                if code[j] in "+-" and j > i and code[j - 1] not in "eE":
                    break
                j += 1
            if j < n and code[j] == "@":                # digit-prefixed attribute binding
                j += 1
                while j < n and code[j] in _IDENT_CHARS:
                    j += 1
                tokens.append(("id", code[i:j]))
            else:
                tokens.append(("num", code[i:j]))
            i = j
            continue
        # identifier / binding (letters, _, @, and following ident chars)
        if c.isalpha() or c == "_" or c == "@":
            j = i
            while j < n and code[j] in _IDENT_CHARS:
                j += 1
            tokens.append(("id", code[i:j]))
            i = j
            continue
        # operators / punctuation
        if c in "+-*/%=<>!&|^~?:.,;()[]{}":
            # greedily grab multi-char operators (<<=, >>=, ==, +=, &&, ...) so assignment detection is exact
            j = i
            while j < n and code[j] in "+-*/%=<>!&|^~<>" and (j - i) < 3:
                j += 1
            op = code[i:j] if j > i else c
            if op and all(ch in "+-*/%=<>!&|^~" for ch in op):
                tokens.append(("op", op))
                i = j
            else:
                tokens.append(("punct", c))
                i += 1
            continue
        if c == "\\":
            _reject("stray backslash outside string literal")
        _reject("illegal character %r" % c)
    return tokens


def _attr_name(ident):
    """Extract the attribute name from a binding token (``s@constraint_name`` -> ``constraint_name``,
    ``@Cd`` -> ``Cd``, ``3@orient`` -> ``orient``). Returns None if the token is not a binding."""
    at = ident.find("@")
    if at < 0:
        return None
    return ident[at + 1:]


def _as_int(s):
    """Parse a numeric-literal token as a plain base-10 integer, or return None (float / hex / malformed
    → None → the caller rejects). Deliberately strict: only literals usable as a STATIC loop bound pass."""
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _validate_for_header(tokens, k):
    """Recognize a rigid, statically-bounded counted-loop header at token index ``k`` (the ``for`` token)
    and return ``(var, ceiling, iters, brace_idx)``; raise ``VexValidationError`` on ANY deviation.

    The ONLY accepted shape (exact token positions, else reject) is::

        for ( int VAR = INITLIT ; VAR CMP BOUND ; INCR ) {

      * ``int`` REQUIRED — a FRESH local counter (blocks aliasing an outer variable).
      * the condition var (k+7) MUST equal the declared counter (k+3); ``CMP`` in ``{<, <=}`` (up-count).
      * ``BOUND`` carries a STATIC ceiling, exactly one of: an integer literal ``L`` (ceiling = L); or
        ``min(...)`` with >=1 integer-literal arg <= cap (ceiling = the smallest literal arg — sound
        because ``min(...) <= `` every literal arg). A bare runtime bound (``@numpt`` / ``chi(...)`` /
        ``len(...)`` / a plain var) has NO literal ceiling and is rejected.
      * ``INCR`` up-only fixed step: ``VAR++`` / ``++VAR`` / ``VAR += STEPLIT`` (STEPLIT >= 1 literal).
      * a braced ``{`` body is REQUIRED (no brace-less single statement).

    ``iters = ceil((ceiling - INITLIT) / step)`` (+1 span for ``<=``), rejected if it exceeds the per-loop
    cap. NOTE: this function is header-STRUCTURE only — depth tracking, the allowlist check on any calls
    inside ``min(...)``, the nesting / product / body-token caps, and the counter-mutation guard are
    enforced by the single structural pass in ``validate_attrib_vex`` (which re-visits the header tokens).
    """
    n = len(tokens)

    def T(i):
        return tokens[i] if 0 <= i < n else None

    if T(k + 1) != ("punct", "("):
        _reject("for: expected '(' after 'for'")
    if T(k + 2) != ("id", "int"):
        _reject("for: counter must be declared 'int VAR' (a fresh local — reusing an outer var is refused)")
    vt = T(k + 3)
    if vt is None or vt[0] != "id" or "@" in vt[1]:
        _reject("for: expected a bare counter name after 'int'")
    var = vt[1]
    if var in BANNED_KEYWORDS or var in _CTRL_BEFORE_PAREN or var == "int":
        _reject("for: illegal counter name %r" % var)
    if T(k + 4) != ("op", "="):
        _reject("for: counter must be initialized 'int VAR = INITLIT'")
    it = T(k + 5)
    init = _as_int(it[1]) if it is not None and it[0] == "num" else None
    if init is None:
        _reject("for: init value must be an integer literal")
    if T(k + 6) != ("punct", ";"):
        _reject("for: expected ';' after init value")
    if T(k + 7) != ("id", var):
        _reject("for: condition variable must be the loop counter %r" % var)
    ct = T(k + 8)
    if ct is None or ct[0] != "op" or ct[1] not in ("<", "<="):
        _reject("for: condition must be 'VAR < BOUND' or 'VAR <= BOUND' (up-count only)")
    cmp = ct[1]

    # BOUND: integer literal L, or min(...) with a literal ceiling.
    b0 = T(k + 9)
    if b0 is not None and b0[0] == "num":
        ceiling = _as_int(b0[1])
        if ceiling is None:
            _reject("for: bound must be an integer literal")
        after_bound = k + 10
    elif b0 == ("id", "min") and T(k + 10) == ("punct", "("):
        # scan min(...) to its matching ')', splitting args on top-level commas.
        d = 0
        args = [[]]
        close_idx = None
        m = k + 10
        while m < n:
            t = T(m)
            if t == ("punct", "("):
                d += 1
                if d == 1:
                    m += 1
                    continue
            elif t == ("punct", ")"):
                d -= 1
                if d == 0:
                    close_idx = m
                    break
            if d == 1 and t == ("punct", ","):
                args.append([])
            else:
                args[-1].append(t)
            m += 1
        if close_idx is None:
            _reject("for: unterminated min() in bound")
        lits = [iv for a in args
                if len(a) == 1 and a[0][0] == "num"
                for iv in (_as_int(a[0][1]),) if iv is not None]
        lits_le_cap = [L for L in lits if L <= _MAX_LOOP_ITERS]
        if not lits_le_cap:
            _reject("for: min() bound must have an integer-literal arg <= %d (a runtime-only bound is refused)"
                    % _MAX_LOOP_ITERS)
        ceiling = min(lits)   # sound: min(...) <= every literal arg, so the smallest literal is a valid ceiling
        after_bound = close_idx + 1
    else:
        _reject("for: bound must be an integer literal or min(...) with a literal ceiling "
                "(a bare runtime bound like @numpt / chi(...) / len(...) is refused)")

    if ceiling > _MAX_LOOP_ITERS:
        _reject("for: static ceiling %d exceeds _MAX_LOOP_ITERS (%d)" % (ceiling, _MAX_LOOP_ITERS))
    if T(after_bound) != ("punct", ";"):
        _reject("for: expected ';' after the bound")

    # INCR: VAR++ / ++VAR / VAR += STEPLIT (STEPLIT >= 1).
    p = after_bound + 1
    a, b, c = T(p), T(p + 1), T(p + 2)
    if a == ("id", var) and b == ("op", "++"):
        step, after_incr = 1, p + 2
    elif a == ("op", "++") and b == ("id", var):
        step, after_incr = 1, p + 2
    elif a == ("id", var) and b == ("op", "+=") and c is not None and c[0] == "num":
        step = _as_int(c[1])
        if step is None or step < 1:
            _reject("for: '+=' step must be an integer literal >= 1")
        after_incr = p + 3
    else:
        _reject("for: increment must be VAR++ / ++VAR / VAR += STEPLIT (up-count, fixed step only)")

    if T(after_incr) != ("punct", ")"):
        _reject("for: expected ')' to close the header")
    brace_idx = after_incr + 1
    if T(brace_idx) != ("punct", "{"):
        _reject("for: loop body must be a braced block '{ ... }' (no brace-less statement)")

    span = ceiling - init + (1 if cmp == "<=" else 0)
    iters = 0 if span <= 0 else (span + step - 1) // step
    if iters > _MAX_LOOP_ITERS:
        _reject("for: loop iterates %d times, exceeding _MAX_LOOP_ITERS (%d)" % (iters, _MAX_LOOP_ITERS))
    return var, ceiling, iters, brace_idx


# VEX local-declaration types accepted as a foreach loop-variable declaration (`TYPE VAR`). Mirrors the
# _CASTS set; kept explicit so a new cast never silently becomes a legal loop-var type without review.
_LOOP_DECL_TYPES = frozenset(
    "int float vector vector2 vector4 matrix matrix2 matrix3 string".split())


def _validate_foreach_header(tokens, k):
    """Recognize a ``foreach`` array-loop header at token index ``k`` (the ``foreach`` token) and return
    ``(vars, brace_idx)``; raise ``VexValidationError`` on ANY deviation.

    The ONLY accepted shapes (VEX foreach), each ending in a braced body::

        foreach ( TYPE VAL ; ARRAY ) { ... }               # value form
        foreach ( int IDX ; TYPE VAL ; ARRAY ) { ... }      # index + value form

    Each ``TYPE VAR`` declaration must be a FRESH local (exactly a type token + a bare-name id, no ``@``),
    the type drawn from ``_LOOP_DECL_TYPES``. ``ARRAY`` is an arbitrary expression whose tokens are checked
    by the flat allowlist pass (it may be a runtime array such as ``@arr`` or ``neighbours(0, @ptnum)`` —
    no static ceiling is required or claimed, because VEX ``foreach`` SNAPSHOTS the array length at entry
    (probe-verified) so iteration is ALWAYS finite = the entry length). The LEAF-ONLY rule (this loop may
    neither nest inside nor contain another loop) is enforced by the loop-stack in ``validate_attrib_vex``,
    NOT here. This function is header-STRUCTURE only.
    """
    n = len(tokens)

    def T(i):
        return tokens[i] if 0 <= i < n else None

    if T(k + 1) != ("punct", "("):
        _reject("foreach: expected '(' after 'foreach'")
    # scan to the matching ')', splitting on top-level (depth-1) ';' into segments. A ';' can only occur at
    # depth 1 here (call args use ',', and there are no statements inside a header), so this split is exact.
    d = 0
    segs = [[]]
    close_idx = None
    m = k + 1
    while m < n:
        t = T(m)
        if t == ("punct", "("):
            d += 1
            if d == 1:
                m += 1
                continue
        elif t == ("punct", ")"):
            d -= 1
            if d == 0:
                close_idx = m
                break
        if d == 1 and t == ("punct", ";"):
            segs.append([])
        else:
            segs[-1].append(t)
        m += 1
    if close_idx is None:
        _reject("foreach: unterminated header '('")
    if len(segs) not in (2, 3):
        _reject("foreach: header must be 'TYPE VAL ; ARRAY' or 'int IDX ; TYPE VAL ; ARRAY'")
    decls, arr = segs[:-1], segs[-1]
    if not arr:
        _reject("foreach: empty array expression")
    vars_ = []
    for dcl in decls:
        if len(dcl) != 2 or dcl[0][0] != "id" or dcl[1][0] != "id":
            _reject("foreach: each declaration must be 'TYPE VAR' (a fresh local)")
        typ, var = dcl[0][1], dcl[1][1]
        if typ not in _LOOP_DECL_TYPES:
            _reject("foreach: declaration type %r is not an allowed local type" % typ)
        if "@" in var or var in BANNED_KEYWORDS or var in _CTRL_BEFORE_PAREN \
                or var in _LOOP_DECL_TYPES or var == "for" or var == "foreach":
            _reject("foreach: illegal loop-variable name %r" % var)
        vars_.append(var)
    if len(set(vars_)) != len(vars_):
        _reject("foreach: duplicate loop-variable name")
    brace_idx = close_idx + 1
    if T(brace_idx) != ("punct", "{"):
        _reject("foreach: loop body must be a braced block '{ ... }' (no brace-less statement)")
    return vars_, brace_idx


def validate_attrib_vex(code, outputs, profile="attrib_v1", allow_loops=False, allow_geoedit=False,
                        allow_geogrow=False):
    """Validate a safe-VEX attribute snippet. Returns ``code`` unchanged on success; raises
    ``VexValidationError`` (fail-closed) on any violation. ``outputs`` = iterable of attribute names the
    snippet is permitted to WRITE (any other write is rejected).

    ``allow_loops`` (default OFF — a SEPARATE consent from ``allow_attrib_expr``): when False, ``for`` and
    ``foreach`` are rejected (loops off). When True, BOTH bounded loop forms are active — a
    statically-bounded counted ``for`` (per ``_validate_for_header`` + the loop stack, caps, and
    counter-mutation guard below) AND a snapshot-finite ``foreach`` (per ``_validate_foreach_header``,
    LEAF-ONLY: may neither nest inside nor contain another loop). ``while``/``do``/``gather`` stay banned
    regardless.

    ``allow_geoedit`` (default OFF — a SEPARATE consent from ``allow_attrib_expr`` and ``allow_loops``;
    enabling writes/loops does NOT grant deletion): when False, the DELETION-only topology writers
    ``removepoint``/``removeprim`` are rejected (as denied functions). When True, they are accepted ONLY
    when arg0 is the literal input index ``0`` (the cooked input-0 sandbox geometry); a computed/attr arg0
    or a nonzero input still rejects. They are NOT ``outputs``-gated (they address no named attribute).

    ``allow_geogrow`` (default OFF — a THIRD SEPARATE consent, ORTHOGONAL to ``allow_attrib_expr`` /
    ``allow_loops`` / ``allow_geoedit``; enabling deletion does NOT grant growth): when False, the
    CONSTRUCTION/GROWTH topology writers ``addpoint``/``addprim``/``addvertex``/``removevertex`` are
    rejected. When True, they are accepted ONLY when arg0 is the literal input index ``0`` (same arg0/comma
    gate as ``allow_geoedit``); a computed/attr arg0 or a nonzero input still rejects. NOT ``outputs``-gated
    (they address no named attribute). Growth has no static total cap — "big-but-finite, human fires"."""
    if profile != "attrib_v1":
        _reject("unknown safe-VEX profile %r" % profile)
    if code is None or not str(code).strip():
        _reject("empty snippet")
    code = str(code)
    outputs = set(str(o).strip() for o in (outputs or []) if str(o).strip())

    # 1. bounds + hard character rejects (defeat preprocessor / hscript / paths before any parsing)
    if any(ord(ch) < 9 or (13 < ord(ch) < 32) or ord(ch) > 126 for ch in code):
        _reject("non-ASCII or control character in snippet")
    if len(code) > _MAX_LEN:
        _reject("snippet exceeds %d chars" % _MAX_LEN)
    if code.count("\n") + 1 > _MAX_LINES:
        _reject("snippet exceeds %d lines" % _MAX_LINES)
    if "#" in code:
        _reject("'#' (preprocessor/#include) is not allowed")
    if "`" in code:
        _reject("backtick (hscript expression) is not allowed")
    if "$" in code:
        _reject("'$' (hscript/env variable) is not allowed")
    low = code.lower()
    if "op:" in low or "opinput:" in low:
        _reject("'op:' node-path reference is not allowed")

    # 2. lex (validates strings + comments + stray backslash inline)
    tokens = _tokenize(code)
    if len(tokens) > _MAX_TOKENS:
        _reject("snippet exceeds %d tokens" % _MAX_TOKENS)

    # 3. structural checks over the token stream
    depth = 0
    max_depth = 0
    calls = 0
    # bounded-loop stack (only ever non-empty under allow_loops). Each entry:
    #   {var, ceiling, close_depth, body_start} — close_depth is the bracket depth the matching '}' returns
    #   to; body_start is the index of the first token INSIDE the loop body (so the header's own init/incr
    #   are naturally exempt from the counter-mutation guard, which only fires at index >= body_start).
    loop_stack = []
    for k, (kind, val) in enumerate(tokens):
        # nesting depth
        if kind == "punct" and val in "([{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif kind == "punct" and val in ")]}":
            depth -= 1
            if depth < 0:
                _reject("unbalanced brackets")
            # pop a bounded loop when its body '}' returns depth to the loop's close_depth
            if val == "}" and loop_stack and loop_stack[-1]["close_depth"] == depth:
                e = loop_stack.pop()
                if k - e["body_start"] > _MAX_LOOP_BODY_TOKENS:
                    _reject("loop body exceeds _MAX_LOOP_BODY_TOKENS (%d) tokens" % _MAX_LOOP_BODY_TOKENS)

        if kind != "id":
            continue

        # bounded counted loop: `for` is handled here (it is NO LONGER in BANNED_KEYWORDS). Off unless the
        # caller consented via allow_loops; on, the rigid header is recognized and the loop is pushed.
        if val == "for":
            if not allow_loops:
                _reject("keyword 'for' (loops) is not allowed")
            # LEAF-ONLY foreach: a counted loop may not open inside a foreach (would amplify its runtime
            # iteration count by a static factor).
            if any(e.get("is_foreach") for e in loop_stack):
                _reject("a 'for' loop cannot be nested inside a 'foreach' (runtime count must not be amplified)")
            var, ceiling, iters, brace_idx = _validate_for_header(tokens, k)
            if len(loop_stack) + 1 > _MAX_LOOP_NESTING:
                _reject("loop nesting exceeds _MAX_LOOP_NESTING (%d)" % _MAX_LOOP_NESTING)
            if any(e["var"] == var for e in loop_stack):
                _reject("duplicate loop counter name '%s' across open loops" % var)
            product = ceiling
            for e in loop_stack:
                product *= e["ceiling"]
            if product > _MAX_LOOP_ITERS_PRODUCT:
                _reject("product of open-loop ceilings (%d) exceeds _MAX_LOOP_ITERS_PRODUCT (%d)"
                        % (product, _MAX_LOOP_ITERS_PRODUCT))
            loop_stack.append({"var": var, "ceiling": ceiling, "is_foreach": False,
                               "close_depth": depth, "body_start": brace_idx + 1})
            continue

        # snapshot-finite array loop: `foreach` (NO LONGER in BANNED_KEYWORDS). Off unless allow_loops.
        # LEAF-ONLY — it may not open while ANY loop is already open (nor may a loop open inside it, enforced
        # in the `for`/`foreach` branches), so its runtime iteration count can never be amplified. The loop
        # variables are FRESH locals (snapshot semantics ⇒ mutating them is harmless), so they are exempt
        # from the counter-mutation and int-export guards (which filter to non-foreach entries below).
        if val == "foreach":
            if not allow_loops:
                _reject("keyword 'foreach' (loops) is not allowed")
            if loop_stack:
                _reject("a 'foreach' cannot be nested inside another loop (runtime count must not be amplified)")
            fvars, brace_idx = _validate_foreach_header(tokens, k)
            loop_stack.append({"var": None, "vars": fvars, "ceiling": 1, "is_foreach": True,
                               "close_depth": depth, "body_start": brace_idx + 1})
            continue

        # banned control-flow / declaration keywords
        if val in BANNED_KEYWORDS:
            _reject("keyword '%s' (loops/definitions) is not allowed" % val)

        # counter-mutation guard: while a loop is open, reject any assignment / ++ / -- to that loop's
        # counter INSIDE its body (index >= body_start exempts the header's own init/incr). This is the one
        # body-level check loops add — it closes the header bypass (mutating the counter to iterate freely).
        if loop_stack and "@" not in val:
            for e in loop_stack:
                if e["var"] == val and k >= e["body_start"]:
                    # Unwrap enclosing parens around the counter so a PARENTHESIZED lvalue write
                    # (`(i) = 0`, `((i)) -= 1`, `++(i)`) is still detected — the guard is otherwise a
                    # local-adjacency matcher that the parens slip past (red-team RT-30).
                    a = k + 1
                    while a < len(tokens) and tokens[a] == ("punct", ")"):
                        a += 1
                    after = tokens[a] if a < len(tokens) else None
                    p = k - 1
                    while p >= 0 and tokens[p] == ("punct", "("):
                        p -= 1
                    prev = tokens[p] if p >= 0 else None
                    prev_adj = tokens[k - 1] if k > 0 else None   # immediate prev (for the byref '(' check)
                    prev2 = tokens[k - 2] if k > 1 else None
                    # arg0 of a by-reference mutator (e.g. `setcomp(i, 0, 0)`) writes the counter with no
                    # assignment op — detect `<mutator> ( COUNTER` and reject it as a mutation.
                    byref_arg0 = (prev_adj == ("punct", "(") and prev2 is not None
                                  and prev2[0] == "id" and prev2[1] in _BYREF_MUTATORS)
                    mutated = (after is not None and after[0] == "op"
                               and (after[1] in _ASSIGN_OPS or after[1] in ("++", "--"))) \
                        or (prev is not None and prev[0] == "op" and prev[1] in ("++", "--")) \
                        or byref_arg0
                    if mutated:
                        _reject("loop counter '%s' cannot be reassigned / incremented / mutated by-reference "
                                "in the loop body" % val)
                    break

        nxt = tokens[k + 1] if k + 1 < len(tokens) else None

        # function-call allowlist: an identifier immediately followed by '(' is a call
        if nxt is not None and nxt == ("punct", "("):
            if val in _CTRL_BEFORE_PAREN:
                pass                                    # if(/else(/return( — not a call
            elif "@" in val:
                _reject("attribute binding '%s' cannot be called" % val)
            elif val in _EXPLICIT_DENY:
                _reject("function '%s' is explicitly denied (file/node reach or a writer that bypasses the outputs gate)" % val)
            elif val not in ALLOWED_FUNCS:
                _reject("function '%s' is not in the safe allowlist" % val)
            else:
                calls += 1
                # int-export-arg guard: while a loop is open, a call to a function with a writable int&
                # export param must NOT receive the loop counter anywhere in its arg list — it could land
                # on the export slot and mutate the counter → runaway loop (red-team RT-30). Fail-closed:
                # scan the whole call span; a read use has a by-value twin (point()/prim()).
                if loop_stack and val in _INT_EXPORT_ARG_FUNCS and tokens[k + 1] == ("punct", "("):
                    open_vars = frozenset(e["var"] for e in loop_stack)
                    d = 0
                    m = k + 1
                    while m < len(tokens):
                        t = tokens[m]
                        if t == ("punct", "("):
                            d += 1
                        elif t == ("punct", ")"):
                            d -= 1
                            if d == 0:
                                break
                        elif t[0] == "id" and t[1] in open_vars:
                            _reject("loop counter '%s' cannot be passed to %s() (writable int& export param "
                                    "could mutate it — use a by-value read like point()/prim())" % (t[1], val))
                        m += 1
                # GEO_READ: first arg MUST be an integer input index 0-3 (never a string geo source).
                if val in GEO_READ_FUNCS:
                    arg0 = tokens[k + 2] if k + 2 < len(tokens) else None
                    arg0_end = tokens[k + 3] if k + 3 < len(tokens) else None
                    if arg0 is None or arg0[0] != "num":
                        _reject("%s(): first arg must be an integer input index 0-3, not %r"
                                % (val, arg0[1] if arg0 else None))
                    try:
                        iv = int(arg0[1])
                    except (ValueError, TypeError):
                        _reject("%s(): first arg must be an integer input index 0-3" % val)
                    if iv not in (0, 1, 2, 3):
                        _reject("%s(): input index %d out of range 0-3" % (val, iv))
                    # arg0 must be EXACTLY the literal index immediately followed by ',' (more args) or ')'
                    # (single-arg like npoints(0)) — the trailing-token check rejects a 0-prefixed expression
                    # like `point(0 + 9, ...)` whose first token is 0 but evaluates elsewhere. Read-only, so
                    # not an escape; mirrors the GEO_EDIT/GEO_GROW arg0/comma gate for consistency.
                    if arg0_end not in (("punct", ","), ("punct", ")")):
                        _reject("%s(): first arg must be a bare integer input index (a 0-prefixed expression is refused)" % val)
                # ch*/chramp(): first arg MUST be a bare local parameter/ramp name string literal — no
                # cross-node path reach (one gate for the whole channel-read family).
                if val in CHANNEL_NAME_FUNCS:
                    arg0 = tokens[k + 2] if k + 2 < len(tokens) else None
                    if arg0 is None or arg0[0] != "str":
                        _reject("%s(): first arg must be a string channel/ramp name literal, not %r"
                                % (val, arg0[1] if arg0 else None))
                    chname = arg0[1].strip('"')
                    if ("/" in chname) or (".." in chname) or (":" in chname) or not chname:
                        _reject("%s(): channel name %r must be a bare local name (no path reach)" % (val, chname))
                # attribute/group WRITERS: gated to the SAME outputs contract as an `@attr =` binding —
                # arg0 must be the literal input index 0 (the cooked geometry), arg1 the bare attr/group
                # NAME as a string literal, and that name MUST be in the declared outputs. A computed name
                # (e.g. sprintf) rejects because arg1 is not a string literal.
                if val in ATTR_WRITE_FUNCS:
                    arg0 = tokens[k + 2] if k + 2 < len(tokens) else None
                    try:
                        iv0 = int(arg0[1]) if arg0 is not None and arg0[0] == "num" else None
                    except (ValueError, TypeError):
                        iv0 = None
                    if iv0 != 0:
                        _reject("%s(): first arg must be the literal input index 0 (the cooked geometry)" % val)
                    comma = tokens[k + 3] if k + 3 < len(tokens) else None
                    arg1 = tokens[k + 4] if k + 4 < len(tokens) else None
                    if comma != ("punct", ",") or arg1 is None or arg1[0] != "str":
                        _reject("%s(): second arg must be a bare attribute/group name string literal (a computed name is refused)" % val)
                    wname = arg1[1].strip('"')
                    if not wname:
                        _reject("%s(): attribute/group name must be non-empty" % val)
                    if wname not in outputs:
                        _reject("%s(): write to '%s' not in declared outputs %s" % (val, wname, sorted(outputs)))
                # setcomp(dst, ...): writes a COMPONENT of dst. On an `@attr` binding it is an attribute
                # write → the attr name must be in outputs. On a local variable it is pure in-memory (OK).
                if val == "setcomp":
                    arg0 = tokens[k + 2] if k + 2 < len(tokens) else None
                    if arg0 is not None and arg0[0] == "id" and "@" in arg0[1]:
                        aname = _attr_name(arg0[1])
                        if not aname or aname not in outputs:
                            _reject("setcomp(): component write to attribute '%s' not in declared outputs %s"
                                    % (aname, sorted(outputs)))
                # topology DELETION writers (removepoint/removeprim): gated behind BOTH the default-off
                # allow_geoedit consent AND arg0 == the literal input index 0 (the cooked input-0 sandbox
                # geometry — NOT read-only inputs 1-3, NOT a computed/attr source). NOT outputs-gated (they
                # address no named attribute). CONSTRUCTION/GROWTH writers stay in _EXPLICIT_DENY. Every arg
                # still flows through the flat allowlist pass, so a denied fn nested in an arg (e.g.
                # removepoint(0, opdigits("x"))) still rejects.
                if val in GEO_EDIT_FUNCS:
                    if not allow_geoedit:
                        _reject("%s(): topology edit requires allow_attrib_geoedit (default-off)" % val)
                    arg0 = tokens[k + 2] if k + 2 < len(tokens) else None
                    arg0_end = tokens[k + 3] if k + 3 < len(tokens) else None
                    try:
                        iv0 = int(arg0[1]) if arg0 is not None and arg0[0] == "num" else None
                    except (ValueError, TypeError):
                        iv0 = None
                    # arg0 must be EXACTLY the literal 0 immediately followed by ',' — the trailing-comma
                    # check rejects an expression whose FIRST token is 0 but evaluates elsewhere
                    # (e.g. `removeprim(0 + 1, ...)` → input 1). Mirrors the ATTR_WRITE arg0/comma gate.
                    if iv0 != 0 or arg0_end != ("punct", ","):
                        _reject("%s(): first arg must be the literal input index 0 (the cooked geometry)" % val)
                # topology CONSTRUCTION/GROWTH writers (addpoint/addprim/addvertex/removevertex): gated behind
                # BOTH the default-off allow_geogrow consent (SEPARATE from allow_geoedit — enabling deletion
                # does NOT grant growth) AND arg0 == the literal input index 0, the SAME arg0/comma gate as
                # GEO_EDIT (the 0-prefixed-expression bypass `addprim(0 + 1, ...)` is rejected by the trailing
                # comma). NOT outputs-gated (they RETURN the new element number, address no named attribute).
                # Every arg still flows through the flat allowlist pass, so a denied fn nested in an arg
                # (e.g. addpoint(0, opdigits("x"))) still rejects.
                if val in GEO_GROW_FUNCS:
                    if not allow_geogrow:
                        _reject("%s(): topology construction/growth requires allow_attrib_geogrow (default-off)" % val)
                    arg0 = tokens[k + 2] if k + 2 < len(tokens) else None
                    arg0_end = tokens[k + 3] if k + 3 < len(tokens) else None
                    try:
                        iv0 = int(arg0[1]) if arg0 is not None and arg0[0] == "num" else None
                    except (ValueError, TypeError):
                        iv0 = None
                    if iv0 != 0 or arg0_end != ("punct", ","):
                        _reject("%s(): first arg must be the literal input index 0 (the cooked geometry)" % val)

        # write gating: a binding token, optional .comp/[idx] access, then an assignment op = a write
        if "@" in val:
            m = k + 1
            # skip component/array access: .x, [0], .r, etc.
            while m < len(tokens):
                t = tokens[m]
                if t == ("punct", "."):
                    m += 2                              # '.' + component ident
                    continue
                if t == ("punct", "["):
                    d = 1
                    m += 1
                    while m < len(tokens) and d:
                        if tokens[m] == ("punct", "["):
                            d += 1
                        elif tokens[m] == ("punct", "]"):
                            d -= 1
                        m += 1
                    continue
                break
            after = tokens[m] if m < len(tokens) else None
            is_write = after is not None and after[0] == "op" and after[1] in _ASSIGN_OPS
            # ++/-- postfix or prefix also mutate
            if after is not None and after[0] == "op" and after[1] in ("++", "--"):
                is_write = True
            prev = tokens[k - 1] if k > 0 else None
            if prev is not None and prev[0] == "op" and prev[1] in ("++", "--"):
                is_write = True
            if is_write:
                name = _attr_name(val)
                if not name:
                    _reject("malformed attribute write %r" % val)
                if name not in outputs:
                    _reject("write to attribute '%s' not in declared outputs %s" % (name, sorted(outputs)))

    if loop_stack:
        _reject("unclosed loop at end of snippet")
    if depth != 0:
        _reject("unbalanced brackets")
    if max_depth > _MAX_DEPTH:
        _reject("expression nesting exceeds depth %d" % _MAX_DEPTH)
    if calls > _MAX_CALLS:
        _reject("snippet exceeds %d function calls" % _MAX_CALLS)
    return code


# ── standalone red-team + allow corpus (run: `python vex_validator.py`) ────────────────────────────
def _selftest():
    OUT = ["constraint_name", "strength", "restlength", "broken", "Cd", "active", "name",
           "group_broken", "pscale", "id", "mass", "vel", "d", "orient", "force", "v", "density"]

    must_pass = [
        's@constraint_name = "glue";',
        'f@strength = 18500.0;',
        'f@strength *= 0.01;',
        '@Cd = set(1, 0, 0);',
        'i@broken = @P.y < 0;',
        'f@strength = fit(@dist, 0, 1, 100, 0);',
        'if (@restlength < 1.4) { @Cd = set(1,1,0); f@strength *= 0.05; }',
        'if (f@impact > 0.6) { s@constraint_name = "soft"; }',
        's@name = sprintf("piece_%d", @ptnum);',
        'i@group_broken = 1;',
        '@Cd = @P.y > 0 ? set(0,1,0) : set(1,0,0);',
        'f@pscale = clamp(fit01(rand(@ptnum), 0.5, 2.0), 0.1, 5.0);',
        '// name the constraints\ns@constraint_name = "glue"; // trailing comment\nf@strength = 100;',
        'f@mass = length(@v) * 2.0;',
        # cross-element measuring / grouping / topology on points/prims/verts (wired input 0-3)
        'f@restlength = distance(@P, point(0, "P", primpoint(0, @primnum, 1)));',
        'i@active = npoints(0) > 100;',
        'if (inpointgroup(0, "broken", @ptnum)) { @Cd = set(1, 0, 0); }',
        'i@broken = nearpoint(0, @P) != @ptnum;',
        'f@strength = neighbourcount(0, @ptnum) < 3 ? 0.0 : 18500.0;',
        # physics: field sampling, packed intrinsics, bbox, custom force (the sim surface)
        '@vel += volumesamplev(1, "vel", @P);',
        'f@d = volumesample(0, 0, @P);',
        'p@orient = quaternion(matrix3(primintrinsic(0, "packedfulltransform", @ptnum)));',
        'if (relbbox(0, @P).y < 0.1) { i@active = 1; }',
        'v@force = curlnoise(@P + @Time) * fit01(rand(@ptnum), 0.5, 2.0);',
        '@density = @density * 0.99;',
        # chramp: bare local ramp name is allowed (current-node ramp lookup)
        'f@pscale = chramp("size", fit01(@ptnum, 0, 100));',
        '@Cd = chramp("colour", @P.y);',
        # ch* family: bare local channel names are allowed (current-node parameter reads)
        'f@pscale = chf("scale") * fit01(rand(@ptnum), 0.5, 2.0);',
        '@Cd = set(chf("r"), chf("g"), chf("b"));',
        'i@active = @ptnum < chi("count");',
        'v@force = chv("wind") * chf("amp");',
        's@name = chs("prefix");',
        'f@strength = ch("mult") * chramp("falloff", @P.y);',
        # item (b): attribute/group WRITERS gated to declared outputs (as safe as an @attr= binding)
        'setpointattrib(0, "Cd", @ptnum, set(1, 0, 0), "set");',
        'setdetailattrib(0, "density", 1.5, "set");',
        'setpointgroup(0, "active", @ptnum, 1, "set");',
        'setvertexattrib(0, "orient", -1, @vtxnum, {0,0,0,1});',
        # setcomp: pure on a local matrix var; outputs-gated when the target is an @attr binding
        'matrix3 m = ident(); setcomp(m, 2.0, 0, 0); f@mass = getcomp(m, 0, 0);',
        'setcomp(@orient, 0.0, 3);',
        # agent-primitive READS (crowd) under the integer-input gate
        'f@d = agentcliplength(0, @primnum, "walk");',
        'i@active = agentrigfind(0, @primnum, "head");',
        # item (d): point-cloud neighbour query on a wired INPUT (int-gated); refuses the .pc file overload
        '@Cd = pcfilter(pcopen(0, "P", @P, chf("radius"), chi("maxpts")), "Cd");',
        'i@active = pcnumfound(pcopen(0, "P", @P, 1.0, 8)) > 3;',
        'f@d = pcfilter(pcopen(1, "P", @P, chf("radius"), chi("maxpts")), "mask");',
    ]
    must_fail = [
        ('#include "C:/evil.h"\n@Cd = 1;', "#include"),
        ('@Cd = `system("calc.exe")`;', "backtick"),
        ('s@name = $HIP;', "$ var"),
        ('f@x = ch("/obj/other/geo1/tx");', "ch cross-node path reach refused (allowlisted but gated)"),
        ('f@x = chf("/obj/geo1/tx");', "chf absolute node-path reach refused"),
        ('v@force = chv("../other/wind");', "chv parent-traversal path reach refused"),
        ('f@x = chf(@ptnum);', "chf first arg must be a bare string literal, not an attr"),
        ('s@name = chs("op:/obj/geo1/name");', "chs op: node-path reach refused"),
        ('pcwrite("out.pc", @P);', "pcwrite (not allowlisted + path)"),
        ('vector c = colormap("/etc/passwd", 0, 0);', "colormap file-read"),
        ('float s = file_stat("secret", "exists");', "file_stat"),
        ('while (1) { }', "while loop"),
        ('for (int i=0; i<10; i++) { }', "for loop"),
        ('s@x = "op:/obj/geo1";', "op: path in string"),
        ('s@x = "C:/windows/system32";', "drive path in string"),
        ('s@x = "../../etc/passwd";', "traversal in string"),
        ('@Cd = system("ls");', "system() not allowlisted"),
        ('f@strength = 1; @evil = 2;', "write to undeclared attr"),
        ('vector v = texture("map.rat", 0, 0);', "texture file-read"),
        ('pc/**/write("x", @P);', "comment-split token still resolves to a call"),
        ('float x = getenv_notreal();', "unknown function rejected by omission"),
        ('s@name = "a\\x41b";', "disallowed escape"),
        # item (b) writer gates: name-not-in-outputs / wrong-input / computed-name / undeclared-setcomp
        ('setpointattrib(0, "secret", @ptnum, @P, "set");', "attr writer name not in declared outputs"),
        ('setpointgroup(0, "grp", @ptnum, 1, "set");', "group writer name not in declared outputs"),
        ('setpointattrib(1, "Cd", @ptnum, @P, "set");', "attr writer must target input 0, not 1"),
        ('setpointattrib(0, sprintf("a%d", @ptnum), @ptnum, 1.0, "set");', "computed attr name (not a literal) refused"),
        ('setcomp(@evil, 1.0, 0);', "setcomp @attr write to an undeclared attr refused"),
        ('int p = addpoint(0, @P);', "growth writer addpoint rejected without allow_attrib_geogrow (default-off)"),
        # NB removepoint/removeprim are consent-gated by allow_geoedit; addpoint/addprim/addvertex/removevertex
        # are consent-gated by allow_geogrow — their rejection-by-default is proven here, their acceptance
        # (with the flag) in the geogrow section below.
        ('setagentclipnames(0, @primnum, array("walk"));', "agent writer setagentclip* still denied (crowd editing, deferred)"),
        ('f@x = point("op:/obj/geo1", "P", 0);', "point() with string geo source (op: + non-int arg0)"),
        ('f@x = point(9, "P", 0);', "point() input index out of range 0-3"),
        ('f@x = point(@ptnum, "P", 0);', "point() first arg not an integer literal"),
        ('@Cd = pcfilter(pcopen("cloud.pc", "P", @P, 1.0, 5), "Cd");', "pcopen string-filename .pc FILE overload refused (arg0 not an int input)"),
        ('int x = pciterate(h);', "pciterate still denied (loop-only handle iterate)"),
        ('pcimport(h, "P", @Cd);', "pcimport still denied (writes by reference, loop-only)"),
        # physics-surface attacks (must still reject after the allowlist extension)
        ('f@d = volumesample("op:/obj/vol", 0, @P);', "volumesample with op: string geo source"),
        ('f@d = volumesample("C:/f.vdb", 0, @P);', "volumesample with a disk-VDB path"),
        ('f@d = volumesample(9, 0, @P);', "volumesample input index out of range"),
        ('getbounds("C:/f.bgeo", v@mn, v@mx);', "getbounds string-filename file read (explicitly denied)"),
        ('setprimintrinsic(0, "transform", @ptnum, 3@m);', "intrinsic writer still explicitly denied"),
        ('setpointattrib(0, "P", @ptnum, @P);', "attr writer to 'P' (not in declared outputs) refused"),
        ('f@x = chramp("../other/ramp", 0.5);', "chramp path reach (traversal) refused"),
        ('f@x = chramp("/obj/geo1/ramp", 0.5);', "chramp absolute node-path reach refused"),
        ('f@x = chramp("op:/obj/geo1/ramp", 0.5);', "chramp op: path reach refused"),
        ('f@x = chramp(@ptnum, 0.5);', "chramp first arg must be a string literal, not an attr"),
        # extra RT-12/#5 bypass fuzz: escape/comment/unicode/writer-smuggle attempts must all reject
        ('@Cd = set(1,0,0); /* block */ system("x");', "block-comment split then non-allowlisted call"),
        ('s@name = "a\\x0abpath";', "hex escape in string literal"),
        ('f@x = ch\\u0072amp("r", 0.5);', "unicode-escaped identifier smuggling chramp"),
        ('@\\u0043d = 1;', "unicode-escaped attribute name"),
        ('f@x = 0; #define EVIL 1', "trailing #define preprocessor"),
    ]
    # ── bounded-loop corpus. These are validated with allow_loops=True; the CONSENT
    #    GATE section below re-runs a few with allow_loops=False and requires them to REJECT. ──
    loop_must_pass = [
        # 4-corner unroll (literal bound, i++)
        'for (int i = 0; i < 4; i++) { @Cd += set(i, 0, 0); }',
        # <= with step 2
        'for (int i = 0; i <= 8; i += 2) { f@mass += i; }',
        # min(@numpt, 256) scan — i indexes point() as the (runtime-OK) element number, arg0 stays literal 0
        'for (int i = 0; i < min(@numpt, 256); i++) { f@d += point(0, "mass", i); }',
        # min(neighbourcount, 64) neighbour sum
        'for (int i = 0; i < min(neighbourcount(0, @ptnum), 64); i++) { f@d += 1.0; }',
        # attr-writer to a declared output inside the loop
        'for (int i = 0; i < 4; i++) { setpointattrib(0, "Cd", i, set(1, 0, 0), "set"); }',
        # nested 8x8 within the product cap (64 <= 4096), distinct counters
        'for (int i = 0; i < 8; i++) { for (int j = 0; j < 8; j++) { f@mass += i * j; } }',
        # ++VAR prefix increment form
        'for (int i = 0; i < 16; ++i) { f@d += chf("scale"); }',
    ]
    loop_must_fail = [
        ('while (1) { }', "while loop still banned"),
        ('do { f@mass = 1.0; } while (0);', "do-while still banned"),
        ('for (int i=0;i<4;i++){ foreach (float v; @foo) { f@mass = v; } }',
         "foreach nested inside for rejected (leaf-only, no runtime-count amplification)"),
        ('gather (0, @P) { } ', "gather still banned"),
        ('for (int i = 0; i < 4; i++) { while (1) { } }', "while nested in for still banned"),
        ('for (int i = 0; i < @numpt; i++) { f@d += 1.0; }', "runtime-unbounded bound @numpt"),
        ('for (int i = 0; i < chi("n"); i++) { f@d += 1.0; }', "runtime-unbounded bound chi()"),
        ('for (int i = 0; i < 100000; i++) { f@d += 1.0; }', "literal bound over _MAX_LOOP_ITERS"),
        ('for (int i = 0; i < min(@numpt, 100000); i++) { f@d += 1.0; }', "min() bound literal over cap"),
        ('for (int i = 0; ; i++) { f@d += 1.0; }', "empty condition"),
        ('for (int i = 10; i > 0; i--) { f@d += 1.0; }', "down-count (CMP '>' and '--')"),
        ('for (i = 0; i < 4; i++) { f@d += 1.0; }', "reuse outer var (missing 'int')"),
        ('for (int i = 0, j = 0; i < 4; i++) { f@d += 1.0; }', "comma init"),
        ('for (int i = 0; j < 4; i++) { f@d += 1.0; }', "condition var != counter"),
        ('for (int i = 0; i < 4; i++) f@d += 1.0;', "brace-less body"),
        ('for (int i = 0; i < 4; i++) { i = 0; }', "counter reassigned in body (i=0)"),
        ('for (int i = 0; i < 4; i++) { i -= 1; }', "counter mutated in body (i-=1)"),
        ('for (int i = 0; i < 4; i++) { i--; }', "counter decremented in body (i--)"),
        ('for (int i = 0; i < 128; i++) { for (int j = 0; j < 128; j++) { f@d += 1.0; } }',
         "product of ceilings over _MAX_LOOP_ITERS_PRODUCT"),
        ('for (int i = 0; i < 2; i++) { for (int j = 0; j < 2; j++) { for (int k = 0; k < 2; k++) { f@d += 1.0; } } }',
         "nesting over _MAX_LOOP_NESTING"),
        ('for (int i = 0; i < 4; i++) { for (int i = 0; i < 4; i++) { f@d += 1.0; } }',
         "duplicate counter name across open loops"),
        ('for (int i = 0; i < 4; i++) { @evil = i; }', "write to undeclared output in loop"),
        ('for (int i = 0; i < 4; i++) { setpointattrib(0, "secret", i, 1.0, "set"); }',
         "attr-writer name not in declared outputs"),
        ('for (int i = 0; i < 4; i++) { f@d += point(i, "P", 0); }', "GEO_READ input index = loop var"),
        ('for (int i = 0; i < 4; i++) { pcimport(h, "P", @Cd); }', "pcimport (denied) inside loop"),
        ('for (int i = 0; i < 4; i++) { f@d += 1.0; ', "unclosed loop body"),
        ('for (int i = 0; i < 4; i *= 2) { f@d += 1.0; }', "non-additive step (*=)"),
        ('for (int i = 0; i < 4; i += 0) { f@d += 1.0; }', "zero step"),
        # by-reference counter mutation (defeats the static cap without an assignment op)
        ('for (int i = 0; i < 8; i++) { setcomp(i, 0, 0); }', "counter mutated by-reference via setcomp → runtime-unbounded"),
        ('for (int i = 0; i < 8; i++) { resize(i, 999); }', "counter passed to a by-reference array mutator"),
        ('for (int i = 0; i < 4; i++) { for (int j = 0; j < 4; j++) { setcomp(j, 0, 0); } }', "inner counter mutated by-reference via setcomp"),
        # [RT-30] counter mutated via an int& EXPORT param of an allowlisted function (position varies by overload)
        ('for (int i = 0; i < 4; i++) { vector uv; xyzdist(0, @P, i, uv); }', "counter on xyzdist int& export (prim) → reset"),
        ('for (int i = 0; i < 4; i++) { int s; f@d += pointattrib(0, "mass", i, s); }', "counter anywhere in an int-export fn call refused"),
        ('for (int i = 0; i < 4; i++) { float a, b; wnoise(@P.x, i, a, b); }', "counter on wnoise int& seed export"),
        ('for (int i = 0; i < 4; i++) { int s; surfacedist(0, "g", "P", 0, i, "a"); }', "counter on surfacedist int& closest_pt export"),
        # [RT-30] parenthesized-lvalue counter write (adjacency-matcher bypass)
        ('for (int i = 0; i < 10; i++) { (i) = 0; }', "parenthesized counter assignment (i)=0"),
        ('for (int i = 0; i < 10; i++) { ((i)) = 0; }', "double-parenthesized counter assignment"),
        ('for (int i = 0; i < 10; i++) { (i) -= 1; }', "parenthesized counter compound-assign"),
    ]
    # CONSENT GATE: every loop must_pass case MUST reject when allow_loops=False (loops off ⇒ for banned).
    consent_gate = loop_must_pass

    # ── geo_edit corpus. DELETION-only topology writers, gated by
    #    allow_geoedit (default OFF) + arg0 == literal input index 0. The CONSENT GATE + LOOP-OFF sections
    #    below re-run these with the flags off and require them to REJECT. ──
    geoedit_must_pass = [
        'removeprim(0, @primnum, 1);',
        'removeprim(0, @primnum, 0);',
        'if (@P.y < -10) { removepoint(0, @ptnum); }',
        'removepoint(0, @ptnum);',
        # the full A2 idiom (threshold-driven constraint removal):
        # read s@name + a solver float, branch, removeprim on input 0
        'if (s@name == "soft" && f@d > ch("threshold")) { removeprim(0, @primnum, 1); }',
        # GEO_READ + edit compose: read topology (neighbourcount, input-gated), then delete isolated points
        'if (neighbourcount(0, @ptnum) < 2) { removepoint(0, @ptnum); }',
    ]
    # geo_edit inside a bounded loop (allow_geoedit=True AND allow_loops=True): arg0 stays literal 0, the
    # loop var is a (runtime-OK) element number; deletion in a loop is bounded + monotone-shrinking.
    geoedit_loop_must_pass = [
        'for (int i = 0; i < 4; i++) { removeprim(0, i, 1); }',
    ]
    geoedit_must_fail = [
        ('removeprim(1, @primnum, 1);', "geo_edit arg0 wrong input (1) — must be literal 0"),
        ('removepoint(2, @ptnum);', "geo_edit arg0 wrong input (2) — must be literal 0"),
        ('removepoint(@ptnum, 0);', "geo_edit arg0 is an attr, not the literal input index 0"),
        ('removeprim(chi("in"), @primnum, 1);', "geo_edit arg0 is a computed value, not the literal 0"),
        ('removeprim(0 + 1, @primnum, 1);', "geo_edit arg0 '0 + 1' evaluates to input 1 (0-prefixed expr bypass)"),
        ('removepoint(0 + 2, @ptnum);', "geo_edit arg0 '0 + 2' evaluates to input 2 (0-prefixed expr bypass)"),
        ('removeprim(0 * 3, @primnum, 1);', "geo_edit arg0 '0 * 3' is an expression, not the bare literal 0"),
        ('removepoint(0, opdigits("x"));', "denied fn (opdigits) nested in a geo_edit arg still rejects"),
        ('removeprim(0, @primnum, 1); @evil = 1;', "@evil write alongside a geo_edit is still outputs-gated"),
        # cross-flag consent: with allow_geoedit=True but allow_geogrow OFF (default), growth writers reject —
        # enabling DELETION does NOT grant GROWTH.
        ('int p = addpoint(0, @P);', "addpoint requires allow_attrib_geogrow (geoedit does not grant growth)"),
        ('int p = addprim(0, "poly");', "addprim requires allow_attrib_geogrow (geoedit does not grant growth)"),
        ('addvertex(0, @primnum, @ptnum);', "addvertex requires allow_attrib_geogrow (geoedit does not grant growth)"),
        ('removevertex(0, @primnum, @vtxnum);', "removevertex requires allow_attrib_geogrow (geoedit does not grant growth)"),
        ('setprimintrinsic(0, "transform", @ptnum, 3@m);', "setprimintrinsic still explicitly denied"),
    ]
    # CONSENT GATE: every geoedit_must_pass MUST reject when allow_geoedit=False (deletion denied by default).
    geoedit_consent_gate = geoedit_must_pass
    # LOOP-OFF INTERACTION: a bounded loop carrying a geo_edit rejects when allow_loops=False (even if
    # geoedit on), and rejects when allow_geoedit=False (even if allow_loops on).
    geoedit_loop_snippet = 'for (int i = 0; i < 4; i++) { removeprim(0, i, 1); }'

    # ── foreach corpus (owner-ratified; folded into allow_loops). VEX foreach snapshots the
    #    array length at entry (probe-verified) ⇒ finite; LEAF-ONLY (no loop may nest with it). Validated
    #    with allow_loops=True; the CONSENT GATE below re-runs them with allow_loops=False and requires
    #    REJECT. ──
    foreach_must_pass = [
        # value form over a local array
        'float arr[] = {1.0, 2.0, 3.0}; foreach (float v; arr) { f@mass += v; }',
        # index + value form; attr-writer to a declared output using the index
        'float a[] = {1.0, 2.0}; foreach (int i; float v; a) { setpointattrib(0, "Cd", i, set(v, 0, 0), "set"); }',
        # over a runtime geo-read array (A3 cluster idiom): neighbours() is input-gated (arg0 literal 0)
        'int nb[] = neighbours(0, @ptnum); foreach (int pt; nb) { f@d += point(0, "mass", pt); }',
        # foreach value var freely mutated in body (harmless — snapshot semantics)
        'float a[] = {1.0, 2.0, 3.0}; foreach (float v; a) { v *= 2.0; f@mass += v; }',
    ]
    foreach_must_fail = [
        ('foreach (float v; arr) f@mass += v;', "brace-less foreach body"),
        ('foreach (v; arr) { f@mass += v; }', "declaration missing a type ('TYPE VAR')"),
        ('foreach (float v; float w; float x; arr) { }', "too many header segments (>3)"),
        ('foreach (float @bad; arr) { }', "loop variable is an attribute binding, not a fresh local"),
        ('foreach (int i; float i; arr) { f@d += i; }', "duplicate loop-variable name"),
        ('float a[] = {1.0}; foreach (float v; a) { @evil = v; }', "write to undeclared output inside foreach"),
        ('float a[] = {1.0}; foreach (float v; a) { for (int i=0;i<4;i++){ f@d+=v; } }',
         "for nested inside foreach (leaf-only) rejected"),
        ('foreach (float v; arr) { foreach (float w; arr2) { f@d += v; } }',
         "foreach nested inside foreach (leaf-only) rejected"),
        ('float a[] = {1.0}; foreach (badtype v; a) { f@d += 1.0; }', "illegal declaration type"),
    ]
    foreach_consent_gate = [s for s in foreach_must_pass]

    # ── geo_grow corpus (owner-ratified). CONSTRUCTION/GROWTH writers gated by allow_geogrow
    #    (default OFF) + arg0 == literal input index 0. CONSENT GATE + cross-flag sections below re-run with
    #    flags off and require REJECT. ──
    geogrow_must_pass = [
        'int pt = addpoint(0, @P);',
        'int pt = addpoint(0, set(0, 1, 0));',
        'int pr = addprim(0, "poly");',
        'int pt = addpoint(0, @P); int pr = addprim(0, "poly", pt);',
        'addvertex(0, @primnum, @ptnum);',
        'removevertex(0, @primnum, @vtxnum);',
    ]
    # geo_grow inside a bounded loop (allow_geogrow=True AND allow_loops=True): arg0 stays literal 0; adds
    # are bounded by the loop cap × element count = big-but-finite. Also inside a foreach.
    geogrow_loop_must_pass = [
        'for (int i = 0; i < 4; i++) { addpoint(0, set(i, 0, 0)); }',
        'float a[] = {0.0, 1.0}; foreach (float v; a) { addpoint(0, set(v, 0, 0)); }',
    ]
    geogrow_must_fail = [
        ('addpoint(1, @P);', "geo_grow arg0 wrong input (1) — must be literal 0"),
        ('addvertex(2, @primnum, @ptnum);', "geo_grow arg0 wrong input (2) — must be literal 0"),
        ('addpoint(@ptnum, @P);', "geo_grow arg0 is an attr, not the literal input index 0"),
        ('addprim(0 + 1, "poly");', "geo_grow arg0 '0 + 1' evaluates to input 1 (0-prefixed expr bypass)"),
        ('int p = addpoint(0, opdigits("x"));', "denied fn (opdigits) nested in a geo_grow arg still rejects"),
        ('int p = addpoint(0, @P); @evil = 1;', "@evil write alongside a geo_grow is still outputs-gated"),
    ]
    # CONSENT GATE: every geogrow_must_pass MUST reject when allow_geogrow=False (default = growth denied).
    geogrow_consent_gate = geogrow_must_pass
    # cross-flag: geogrow rejects when only allow_geoedit is on (deletion consent ≠ growth consent).
    geogrow_geoedit_only = 'int pt = addpoint(0, @P);'
    # LOOP-OFF: geo_grow in a for loop rejects when allow_loops=False (for banned) even if geogrow on.
    geogrow_loop_off_snippet = 'for (int i = 0; i < 4; i++) { addpoint(0, set(i, 0, 0)); }'

    # validate_ident gate (used where a caller name is interpolated into VEX snippet TEXT, e.g. terrain
    # fill/morph layer names). Bare identifiers pass; anything that could smuggle VEX is rejected.
    ident_pass = ["height", "mask", "seed_layer", "water2", "_tmp", "Debris", "flowdir_x"]
    ident_fail = [
        "height; @Cd=set(1,0,0)",          # the RT-12 injection shape
        'height; removepoint(0,@ptnum); float _x=@height',
        "a b", "a-b", "a.b", "@P", "1abc", "", "x/y", 'a"b', "a)b", "a\nb",
        "op:/obj/x", "x" * 65,
    ]

    ok = True
    for nm in ident_pass:
        try:
            validate_ident(nm)
        except VexValidationError as e:
            ok = False
            print("FAIL ident (should PASS):", repr(nm), "->", e)
    for nm in ident_fail:
        try:
            validate_ident(nm)
            ok = False
            print("FAIL ident (should REJECT):", repr(nm))
        except VexValidationError:
            pass
    for src in must_pass:
        try:
            validate_attrib_vex(src, OUT)
        except VexValidationError as e:
            ok = False
            print("FAIL (should PASS):", repr(src), "->", e)
    for src, why in must_fail:
        try:
            validate_attrib_vex(src, OUT)
            ok = False
            print("FAIL (should REJECT: %s):" % why, repr(src))
        except VexValidationError:
            pass
    # bounded loops: must_pass / must_fail run with allow_loops=True
    for src in loop_must_pass:
        try:
            validate_attrib_vex(src, OUT, allow_loops=True)
        except VexValidationError as e:
            ok = False
            print("FAIL loop (should PASS, allow_loops=True):", repr(src), "->", e)
    for src, why in loop_must_fail:
        try:
            validate_attrib_vex(src, OUT, allow_loops=True)
            ok = False
            print("FAIL loop (should REJECT: %s):" % why, repr(src))
        except VexValidationError:
            pass
    # CONSENT GATE: the SAME loop must_pass snippets MUST reject with allow_loops=False (default = for banned)
    for src in consent_gate:
        try:
            validate_attrib_vex(src, OUT, allow_loops=False)
            ok = False
            print("FAIL consent-gate (should REJECT with allow_loops=False):", repr(src))
        except VexValidationError:
            pass
    # ── geo_edit: deletion-only topology writers (allow_geoedit) ──
    for src in geoedit_must_pass:
        try:
            validate_attrib_vex(src, OUT, allow_geoedit=True)
        except VexValidationError as e:
            ok = False
            print("FAIL geoedit (should PASS, allow_geoedit=True):", repr(src), "->", e)
    for src in geoedit_loop_must_pass:
        try:
            validate_attrib_vex(src, OUT, allow_geoedit=True, allow_loops=True)
        except VexValidationError as e:
            ok = False
            print("FAIL geoedit loop (should PASS, allow_geoedit=True, allow_loops=True):", repr(src), "->", e)
    for src, why in geoedit_must_fail:
        try:
            validate_attrib_vex(src, OUT, allow_geoedit=True)
            ok = False
            print("FAIL geoedit (should REJECT: %s):" % why, repr(src))
        except VexValidationError:
            pass
    # CONSENT GATE: every geoedit_must_pass MUST reject with allow_geoedit=False (deletion off by default)
    for src in geoedit_consent_gate:
        try:
            validate_attrib_vex(src, OUT, allow_geoedit=False)
            ok = False
            print("FAIL geoedit consent-gate (should REJECT with allow_geoedit=False):", repr(src))
        except VexValidationError:
            pass
    # LOOP-OFF INTERACTION: the bounded loop with a geo_edit rejects when allow_loops=False (for banned),
    # even though geoedit is on; and rejects when allow_geoedit=False (deletion off), even though loops on.
    try:
        validate_attrib_vex(geoedit_loop_snippet, OUT, allow_geoedit=True, allow_loops=False)
        ok = False
        print("FAIL geoedit loop-off (should REJECT: for banned with allow_loops=False):", repr(geoedit_loop_snippet))
    except VexValidationError:
        pass
    try:
        validate_attrib_vex(geoedit_loop_snippet, OUT, allow_geoedit=False, allow_loops=True)
        ok = False
        print("FAIL geoedit loop consent (should REJECT: geo_edit with allow_geoedit=False):", repr(geoedit_loop_snippet))
    except VexValidationError:
        pass
    # ── foreach: array loop, folded into allow_loops ──
    for src in foreach_must_pass:
        try:
            validate_attrib_vex(src, OUT, allow_loops=True)
        except VexValidationError as e:
            ok = False
            print("FAIL foreach (should PASS, allow_loops=True):", repr(src), "->", e)
    for src, why in foreach_must_fail:
        try:
            validate_attrib_vex(src, OUT, allow_loops=True)
            ok = False
            print("FAIL foreach (should REJECT: %s):" % why, repr(src))
        except VexValidationError:
            pass
    # CONSENT GATE: every foreach must_pass MUST reject with allow_loops=False (loops off ⇒ foreach banned)
    for src in foreach_consent_gate:
        try:
            validate_attrib_vex(src, OUT, allow_loops=False)
            ok = False
            print("FAIL foreach consent-gate (should REJECT with allow_loops=False):", repr(src))
        except VexValidationError:
            pass
    # ── geo_grow: construction/growth topology writers (allow_geogrow) ──
    for src in geogrow_must_pass:
        try:
            validate_attrib_vex(src, OUT, allow_geogrow=True)
        except VexValidationError as e:
            ok = False
            print("FAIL geogrow (should PASS, allow_geogrow=True):", repr(src), "->", e)
    for src in geogrow_loop_must_pass:
        try:
            validate_attrib_vex(src, OUT, allow_geogrow=True, allow_loops=True)
        except VexValidationError as e:
            ok = False
            print("FAIL geogrow loop (should PASS, allow_geogrow=True, allow_loops=True):", repr(src), "->", e)
    for src, why in geogrow_must_fail:
        try:
            validate_attrib_vex(src, OUT, allow_geogrow=True)
            ok = False
            print("FAIL geogrow (should REJECT: %s):" % why, repr(src))
        except VexValidationError:
            pass
    # CONSENT GATE: every geogrow must_pass MUST reject with allow_geogrow=False (growth off by default)
    for src in geogrow_consent_gate:
        try:
            validate_attrib_vex(src, OUT, allow_geogrow=False)
            ok = False
            print("FAIL geogrow consent-gate (should REJECT with allow_geogrow=False):", repr(src))
        except VexValidationError:
            pass
    # CROSS-FLAG: enabling only allow_geoedit must NOT grant growth (graduated consent)
    try:
        validate_attrib_vex(geogrow_geoedit_only, OUT, allow_geoedit=True, allow_geogrow=False)
        ok = False
        print("FAIL geogrow cross-flag (should REJECT: growth with only allow_geoedit):", repr(geogrow_geoedit_only))
    except VexValidationError:
        pass
    # LOOP-OFF: geo_grow in a for loop rejects when allow_loops=False (for banned) even if geogrow on
    try:
        validate_attrib_vex(geogrow_loop_off_snippet, OUT, allow_geogrow=True, allow_loops=False)
        ok = False
        print("FAIL geogrow loop-off (should REJECT: for banned with allow_loops=False):", repr(geogrow_loop_off_snippet))
    except VexValidationError:
        pass
    print("VEX validator self-test:", "ALL GREEN" if ok else "FAILURES ABOVE")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if _selftest() else 1)

"""Cloud-CI-safe CONSTRUCTION SMOKE gate: every non-allowlisted data-only handler's Python runs end to
end against a recording `hou` mock, WITHOUT a Houdini license and WITHOUT a real cook.

This is Tier 2 of the testing method. Tier 1 (test_catalog_parity_cloud.py) proves the catalog and the
executor registry are in lockstep and RCE-free. Tier 2 proves each registered handler, given a
type-appropriate minimal parameter set, executes its whole CONSTRUCTION path -- resolve inputs, create
the node(s), set the parameters, wire the inputs, read back plausible geometry counts, and build a
JSON-serializable return envelope -- without raising.

WHAT GREEN PROVES
  * For every non-allowlisted tool: the handler's Python is reachable and internally consistent against
    the real `hou` construction surface -- no NameError / AttributeError / wrong-arity / bad parm-tuple
    / unhandled type error on the minimal happy path, and the result serializes exactly as the executor
    would serialize it (via server._jsonable).

WHAT GREEN DOES **NOT** PROVE  (this is NOT a cook / correctness test)
  * It does NOT cook a single node. The mock returns EMPTY geometry (0 points / 0 prims) and never runs
    a solver, VEX, or a file read. So it cannot show a node graph produces the right geometry, that
    node/parm names match a real Houdini build, that a sim converges, or that an exported file is valid.
  * A handler that is only reachable through a genuine cooked-geometry branch (e.g. it must read a real
    attribute a solver wrote) cannot run here and is ALLOWLISTED with a one-line reason -- allowlisting
    means "un-runnable under any reasonable mock", never "failed, so silenced".

Run:  python tests/executor/test_construct_smoke_cloud.py   (exit 0 = pass; non-zero only on an
UNEXPECTED, i.e. non-allowlisted, failure). Under a licensed hython the real `hou` is used (the mock
only installs when `hou` is absent), so run_tests.py picks it up locally too.
"""
import json
import os
import sys
import tempfile
import traceback

_HERE = os.path.dirname(os.path.realpath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)
sys.path.insert(0, _HERE)

import _houmock  # noqa: E402  (the recording hou mock)

# hython pre-loads the real `hou` into sys.modules; the cloud runner does not. This gate is a MOCK
# construction check (Tier 2): under a REAL hou it would need real fixtures for all 1,460 tools (that is
# the Tier-3 behavioural suite's job), so it SKIPS under real hython — see main(). Cloud CI is unaffected.
_ON_REAL_HOU = "hou" in sys.modules
_houmock.install()  # installs mock hou/hwebserver ONLY if the real ones are absent (licensed hython wins)

from houdini_executor import server  # noqa: E402
from houdini_executor import handlers  # noqa: E402,F401  (import side effect: registers every @endpoint)

# Pin confinement to a private tempdir so FsPath params pass server.confined_path deterministically.
_WORKDIR = os.path.realpath(tempfile.mkdtemp(prefix="hmcp_smoke_"))
server._effective_working_dir = lambda: _WORKDIR  # noqa: SLF001 -- the documented test seam

# Enable the opt-in validated-VEX lane (executor-side gate) so the single VexSnippet tool can run its
# construction path. This does NOT weaken the validator -- the snippet is still validated allowlist-first.
try:
    from houdini_executor.handlers import vexwrangle
    vexwrangle._allow_attrib_expr = lambda: True  # noqa: SLF001
except Exception:  # noqa: BLE001
    pass


# -- NodePath fixtures the handlers resolve_node() -----------------------------------------------------
# A generic SOP inside a geo (the overwhelmingly common `input`), a dopnet + a DOP node inside it (sim
# assembly), a chopnet (KineFX constraints), a camera and a light OBJ. reset_scene() wipes them, so they
# are rebuilt before EVERY handler call. A per-tool typed SOLVER node is added inside the dopnet for the
# sim tools that gate on a specific solver type (rbdbulletsolver / flipsolver / vellumsolver / ...).
_SOP_PATH = "/obj/smoke_src/OUT"
_GEO_PATH = "/obj/smoke_src"
_DOP_PATH = "/obj/smoke_dop"
_DOPOBJ_PATH = "/obj/smoke_dop/dopobj"          # a DOP node living inside the dopnet
_SOLVER_PATH = "/obj/smoke_dop/thesolver"       # a typed solver inside the dopnet
_CHOP_PATH = "/obj/smoke_chop"
_CHOPOBJ_PATH = "/obj/smoke_chop/chopobj"       # a CHOP node inside the chopnet (constraint chains)
_CAM_PATH = "/obj/smoke_cam"
_LIGHT_PATH = "/obj/smoke_light"
_SUBNET_PATH = "/obj/smoke_subnet"              # a subnet (HDA packaging etc.)

# tool-name keyword -> the solver node type its handler expects at a `solver` NodePath.
_SOLVER_BY_KEYWORD = (
    ("vellum", "vellumsolver"), ("flip", "flipsolver"), ("mpm", "mpmsolver"),
    ("pop", "popsolver"), ("pyro", "pyrosolver"), ("smoke", "pyrosolver"),
    ("bullet", "rbdbulletsolver"), ("rbd", "rbdbulletsolver"),
)


def _solver_type_for(tool):
    name = tool["name"].lower()
    for kw, stype in _SOLVER_BY_KEYWORD:
        if kw in name:
            return stype
    return "rbdbulletsolver"


def _build_fixtures(tool):
    hou = sys.modules["hou"]
    obj = hou.node("/obj")
    geo = obj.createNode("geo", "smoke_src")
    sop = geo.createNode("null", "OUT")
    sop.setDisplayFlag(True)
    sop.setRenderFlag(True)
    dop = obj.createNode("dopnet", "smoke_dop")
    dop.createNode("rbdbulletsolver", "dopobj")               # a generic DOP node inside the dopnet
    solver = dop.createNode(_solver_type_for(tool), "thesolver")  # a typed solver for the sim tools
    solver.setInput(0, dop.node("dopobj"))                    # some tools require solver input 0 wired
    chop = obj.createNode("chopnet", "smoke_chop")
    chop.createNode("null", "chopobj")                        # a CHOP node inside the chopnet
    obj.createNode("cam", "smoke_cam")
    obj.createNode("hlight", "smoke_light")
    obj.createNode("subnet", "smoke_subnet")                  # for HDA-packaging etc.


def _nodepath_for(param, tool):
    """Route a NodePath param to a fixture (heuristic, using its name + description). solver -> the typed
    solver in the dopnet; DOP targets -> the dopnet; a DOP `input` (DOP-assembly tools) -> a DOP node in
    it; a CHOP input (desc mentions CHOP) -> a CHOP node in the chopnet; chopnet -> the chopnet;
    camera/light -> those OBJs; everything else -> the generic SOP."""
    n = str(param.get("name", "")).lower()
    desc = str(param.get("desc", "")).lower()
    if n in ("solver",):
        return _SOLVER_PATH
    if "dopnet" in n or n == "dop_target" or n.endswith("_dopnet"):
        return _DOP_PATH
    if "chopnet" in n or n == "chop_network":
        return _CHOP_PATH
    if n in ("input", "input0", "input1") and ("chop" in desc):
        return _CHOPOBJ_PATH
    if n in ("input", "dop_input") and _is_dop_assembly(tool):
        return _DOPOBJ_PATH
    if "subnet" in desc:
        return _SUBNET_PATH
    if n == "box" or ("obj" in desc and ("transform" in desc or "bounds" in desc)):
        return _GEO_PATH                                  # an OBJ with a display SOP
    if "cam" in n:
        return _CAM_PATH
    if n == "light" or n.endswith("_light"):
        return _LIGHT_PATH
    return _SOP_PATH


def _is_dop_assembly(tool):
    """A tool whose `input`/`dop_input` is a DOP node inside a caller-supplied dopnet (it declares a
    `dopnet` param)."""
    return any(p.get("name") == "dopnet" for p in tool.get("params", []))


# -- FsPath fixtures -----------------------------------------------------------------------------------
def _fspath_for(param):
    """A confined path for an FsPath param. For read paths we also touch an empty file so a bare
    existence check passes (parsers that need real binary content are a separate, allowlisted concern)."""
    ext = _guess_ext(param.get("desc", ""))
    path = os.path.join(_WORKDIR, "smoke_%s%s" % (param.get("name", "file"), ext))
    if not param.get("write"):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                # a read .json gets a minimal valid document so json.loads() succeeds.
                fh.write("[]" if ext == ".json" else "")
        except Exception:  # noqa: BLE001
            pass
    return path


def _guess_ext(desc):
    """Pull the first plausible file extension out of a param description (e.g. '.hip', '.npy'),
    default '.dat'. Extension can matter to a handler that validates it."""
    tok = ""
    for i, ch in enumerate(desc):
        if ch == "." and i + 1 < len(desc) and desc[i + 1].isalpha():
            j = i + 1
            while j < len(desc) and (desc[j].isalnum()):
                j += 1
            cand = desc[i:j]
            if 2 <= len(cand) <= 6:
                tok = cand.lower()
                break
    return tok or ".dat"


# -- VEX snippet synthesis (profile-aware) -------------------------------------------------------------
def _vex_for(profile):
    # attrib_v1 accepts an attribute-binding write to a declared output; we write `x` and declare it.
    return "f@x = 0;"


_VEX_OUTPUT_ATTR = "x"


# -- per-param value synthesis -------------------------------------------------------------------------
def _clamp_int(param):
    lo = param.get("min")
    hi = param.get("max")
    v = 1
    if isinstance(lo, (int, float)):
        v = max(v, int(lo))
    if isinstance(hi, (int, float)):
        v = min(v, int(hi))
    return int(v)


# Str params are frequently "secretly typed": a filesystem path, a node path (or comma/JSON list of
# them), or a JSON array -- because the catalog has no dedicated Kind for those. We infer the intended
# shape from the param name + description so the handler's parse/resolve step reaches its happy path.
_FS_NAME_HINTS = ("file", "path", "dir", "cache", "npy", "csv", "psd", "fbx", "usd",
                  "folder", "filename", "recording", "executable", "texture", "bump")
_NODEREF_NAME_HINTS = ("inputs", "target_shapes", "sources", "layers", "input2", "input3",
                       "fg", "bg", "distortion", "fill_area", "normals", "matte", "mask_input")


def _str_value(param, tool):
    name = str(param.get("name", "")).lower()
    desc = str(param.get("desc", "")).lower()
    if name == "outputs":
        return _VEX_OUTPUT_ATTR  # VexSnippet write-gate allowlist (must contain the written attr)
    # A param that must be a BARE token / leaf / attribute name (NOT a path) -> keep it bare.
    if ("bare" in desc or "leaf" in desc or "must not contain" in desc or "no path" in desc
            or "identifier" in desc or "attribute name" in desc or "attrib name" in desc):
        return "smoke"
    if name == "value":
        return "1"                                        # a settable scalar (set_parm / shader value)
    # A DIRECTORY param -- a relative subfolder under the working dir (e.g. list_working_dir.subdir).
    # "" = the working-dir root, always a valid confined directory; a synthesized file path would fail
    # the handler's os.path.isdir() check.
    if name == "subdir" or "subfolder" in desc:
        return ""
    # A comma/JSON LIST OF FILE PATHS that is read-confined (e.g. usd_stitch.input_files,
    # usd_value_clip.clip_files) -- these ALSO say "comma-separated or JSON list", so they must be
    # caught before the node-path-list branch below or they'd get a NodePath and fail confined_path. A
    # single confined file path is a valid 1-element list.
    if "file" in name and ("confined" in desc or _guess_ext(desc) != ".dat"):
        return _fspath_for(param)
    # A JSON literal (the catalog has no list/vector Kind, so these arrive as Str).
    if "json" in desc and "[" in desc:
        if "piece" in desc:
            return '[{"path":"%s"}]' % _SOP_PATH
        if "pt1" in desc or "segment" in desc:
            return '[{"pt1":[0,0,0],"pt2":[1,0,0]}]'
        if "[{" in desc:                                  # a list of objects (filters/rules) -> empty
            return "[]"
        if "low" in desc and "high" in desc:
            return "[0.0, 1.0]"
        if ("array of" in desc and ("[x,y,z]" in desc or "triple" in desc)) or name == "points":
            return "[[0,0,0],[1,0,0],[2,1,0]]"
        return "[0.0, 0.0, 0.0]"                          # a single [r,g,b] / [x,y,z] vector
    # A whitelisted MaterialX node type.
    if "mtlx" in desc:
        return "mtlxstandard_surface"
    # A node input given as a NAME or a numeric index -> the numeric index is universally accepted.
    if "numeric index" in desc or "numeric in" in desc:
        return "0"
    # A short enumerated token given by example in the description ("e.g. circle/rect/oval" or "'0e1'").
    tok = _example_token(desc)
    if tok is not None:
        return tok
    # A pipe-separated token menu in the description ("... color scheme: dark | dark_grey | grey").
    tok = _menu_token(desc)
    if tok is not None:
        return tok
    # A marker-visibility param that only cross-references another param's token list.
    if "visibility" in desc or "markers tokens" in desc:
        return "always"
    # A node name OR a full node path -> a resolvable path satisfies both.
    if "full path" in desc:
        return _GEO_PATH
    # A comma/JSON list of node paths, or a node reference declared as Str.
    if "comma-separated or json" in desc or "json list" in desc:
        return _SOP_PATH
    if (name in _NODEREF_NAME_HINTS or "node path" in desc or "sop path" in desc
            or "cop node" in desc or "wired to input" in desc):
        return _SOP_PATH
    # A filesystem path (confined) -- Str params that are really file/dir paths.
    if (any(h in name for h in _FS_NAME_HINTS)
            or "working directory" in desc or "confined" in desc):
        return _fspath_for(param)
    return "smoke"


def _example_token(desc):
    """Recover a legal value from an 'e.g. ...' example so a Str param validated against an in-handler
    allowlist / format gets a valid token. Handles a quoted example ("e.g. '0e1'") and a slash-separated
    token menu ("e.g. circle/rect/oval")."""
    marker = "e.g. "
    i = desc.find(marker)
    if i < 0:
        return None
    tail = desc[i + len(marker):]
    if tail[:1] in ("'", '"'):                            # quoted example -> use it verbatim
        q = tail[0]
        end = tail.find(q, 1)
        if end > 1:
            return tail[1:end]
    j = 0
    while j < len(tail) and (tail[j].isalnum() or tail[j] in "_-"):
        j += 1
    first = tail[:j]
    if first and j < len(tail) and tail[j] == "/":       # slash-separated token menu
        return first
    return None


def _menu_token(desc):
    """Recover the first token of a pipe-separated menu described in prose ('mode: dark | grey | light'
    -> 'dark') so a Str param that a handler resolves against a live enum gets a legal value."""
    if "|" not in desc:
        return None
    head = desc.split("|", 1)[0].split("(")[0]            # drop any "(default)" annotation
    toks = head.replace(":", " ").replace(",", " ").split()
    if not toks:
        return None
    cand = toks[-1].strip(".)")
    if cand and all(c.isalnum() or c in "_-" for c in cand):
        return cand
    return None


def _value_for(param, tool):
    kind = param.get("kind")
    if kind == "Str":
        return _str_value(param, tool)
    if kind == "Enum":
        choices = param.get("choices") or ["smoke"]
        return choices[0]
    if kind == "Bool":
        return False
    if kind == "Int":
        return _clamp_int(param)
    if kind == "Num":
        return 1.0
    if kind == "NumVec":
        n = param.get("len")
        n = n if isinstance(n, int) and n > 0 else 3
        return [1.0] * n
    if kind == "NodePath":
        return _nodepath_for(param, tool)
    if kind == "FsPath":
        return _fspath_for(param)
    if kind == "VexSnippet":
        return _vex_for(param.get("profile"))
    return "smoke"


def _synth_params(tool):
    """Type-appropriate minimal params: ALL required + ALL optional params, each a valid value."""
    params = {}
    has_vex = any(p.get("kind") == "VexSnippet" for p in tool.get("params", []))
    for p in tool.get("params", []):
        params[p["name"]] = _value_for(p, tool)
    # A VexSnippet's companion `outputs` allowlist must contain the attribute the snippet writes.
    if has_vex and "outputs" in params:
        params["outputs"] = _VEX_OUTPUT_ATTR
    return params


# -- ALLOWLIST -----------------------------------------------------------------------------------------
# name -> reason. A handler belongs here ONLY if it cannot run under ANY reasonable construction mock
# because it branches on a genuine COOK RESULT or an external artifact the mock cannot fabricate. Each
# entry is individually justified. This is NOT a dumping ground for fixable mock gaps.
ALLOWLIST = {
    # -- branch on COOKED GEOMETRY the empty mock cannot produce ------------------------------------
    "batch_export": "splits geometry by the distinct values of a real attribute (needs a cooked attrib)",
    "camera_path": "samples a curve's points to build the path (mock curve has 0 points)",
    "level": "fits a plane from the input's points (mock geometry has 0 points)",
    "heightfield_fill": "requires a real heightfield (named volume prims) on the input geometry",
    "heightfield_morph": "requires a real heightfield (named volume prims) on the input geometry",
    "set_tile_lod": "needs a packed-tile SOP subtree (from add_tile_packed) that the mock has no equivalent of",
    # -- validate against a REAL node/VOP schema the mock cannot reproduce --------------------------
    "material_noise_channel": "validates a channel name against the real MaterialX VOP input schema",
    "material_ramp_on_attribute": "validates a channel name against the real MaterialX VOP input schema",
    "define_hda": "authors a real HDA via createDigitalAsset() + reads the written library definition",
    # -- parse a REAL external file the mock cannot fabricate ---------------------------------------
    "import_heightfield": "np.load()s a real .npy elevation array + its JSON sidecar",
    "import_ecef_tile": "np.load()s a real prep_ecef .npy tile + its JSON sidecar",
    "flightcam": "parses a specific poses .json structure (a keyed pose table) the mock cannot fabricate",
    # -- drive live INTERACTIVE GUI state absent in a headless/mock session -------------------------
    "capture_ui": "imports PySide2 to build a Qt capture panel (no Qt in a headless runner)",
    "snapshot": "grabs the interactive viewport window to an image (GUI screenshot; defaults to cwd)",
    "switch_desktop": "switches between live saved desktops (none exist in a headless/mock session)",
    "pane_layout": "splits/maximizes live desktop panes (none exist in a headless/mock session)",
}


# -- run -----------------------------------------------------------------------------------------------
def _serialize_like_dispatch(result):
    """Reproduce exactly how server._dispatch would serialize the handler's return value."""
    jsonable = getattr(server, "_jsonable", None)
    payload = jsonable(result) if callable(jsonable) else result
    json.dumps({"ok": True, "result": payload})


def main():
    if _ON_REAL_HOU:
        print("CONSTRUCTION SMOKE (Tier-2 mock gate) SKIPPED under real hython: its 1,460-tool "
              "construction check is designed for the recording `hou` mock (real fixtures for every "
              "tool are the Tier-3 behavioural suite's job). SKIP = pass; run it in cloud CI / bare "
              "python for the mock-construction gate.")
        return 0
    tools = _load_catalog()
    registry = server._REGISTRY

    clean, failures, missing = [], [], []
    for tool in tools:
        name = tool["name"]
        spec = registry.get(name)
        if spec is None:
            missing.append(name)  # a catalog tool with no Python handler (gateway-native); skip cleanly
            continue
        params = _synth_params(tool)
        _houmock.reset_scene()
        _build_fixtures(tool)
        try:
            result = spec["fn"](params)
            _serialize_like_dispatch(result)
            clean.append(name)
        except BaseException as exc:  # noqa: BLE001 -- the whole point is to catalog every failure
            tb = traceback.format_exc().strip().splitlines()
            last = tb[-1] if tb else repr(exc)
            failures.append((name, type(exc).__name__, last))

    # partition failures into expected (allowlisted) and unexpected
    allow_hit = [(n, t, l) for (n, t, l) in failures if n in ALLOWLIST]
    unexpected = [(n, t, l) for (n, t, l) in failures if n not in ALLOWLIST]
    allow_missing = sorted(set(ALLOWLIST) - {n for (n, _, _) in failures})

    total = len(clean) + len(failures)
    print("=" * 96)
    print("CONSTRUCTION SMOKE (license-free, no cook)")
    print("=" * 96)
    print("catalog tools                : %d" % len(tools))
    print("gateway-native (no handler)  : %d  %s" % (len(missing), sorted(missing)))
    print("handlers exercised           : %d" % total)
    print("execute-clean against mock   : %d / %d  (%.1f%%)"
          % (len(clean), total, (100.0 * len(clean) / total) if total else 0.0))
    print("allowlisted (expected fail)  : %d" % len(allow_hit))
    for n, t, l in sorted(allow_hit):
        print("    - %-32s %-24s | %s" % (n, ALLOWLIST.get(n, ""), t))
    print("UNEXPECTED failures          : %d" % len(unexpected))
    for n, t, l in sorted(unexpected):
        print("    x %-34s %-26s %s" % (n, t, l))
    if allow_missing:
        print("STALE allowlist entries (now pass or absent): %s" % allow_missing)

    print("=" * 96)
    ok = not unexpected
    print("RESULT:", "ALL GREEN" if ok else "FAILURES (%d unexpected)" % len(unexpected))
    return 0 if ok else 1


def _load_catalog():
    with open(os.path.join(_REPO, "reference", "catalog.json"), encoding="utf-8") as fh:
        return json.load(fh)["tools"]


if __name__ == "__main__":
    sys.exit(main())

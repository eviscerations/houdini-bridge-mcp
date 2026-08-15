#!/usr/bin/env python3
"""Auto-derive the tool -> Houdini nodetype map from the handler source.

`reference/tool_nodes.json` powers the per-node coverage flags in NODE_REFERENCE.md
(via `scripts/generate_docs.py --coverage`). It used to be hand-maintained, so it
drifted whenever a handler family landed without a matching hand edit (the COP lane
added 143 tools, none mapped). This script removes the hand-maintenance: it reads
each `@endpoint("<tool>")` handler in `houdini_executor/handlers/*.py` and extracts
the PRIMARY nodetype the handler creates — the string literal of the FIRST node-
creating call in the function body:

    child_after(<input>, "<ntype>" ...)      # filter chained after an input
    _cop_gen("<ntype>" ...)                  # COP generator in the shared copnet
    _stage_node("<ntype>" ...)               # LOP/USD node in the stage graph
    <x>.createNode("<ntype>" ...)            # direct create

Tools with no such call (pure control/util: pane_*, set_parm, keyframes, ml_*, ...)
have no single nodetype and are left unmapped (they surface as the generator's
"absent from tool_nodes.json" residual, which is expected).

MERGE policy (`--write`): existing hand-maintained entries WIN — they are never
overwritten (many carry richer multi-node arrays than a single primary). Only tools
missing from the file are added. COP-lane tools (handlers/cops.py) are tagged
`"category": "Cop"` so the coverage join can disambiguate same-named nodes across
categories (e.g. COP `bend` vs SOP `bend`).

    python scripts/derive_tool_nodes.py            # dry-run: report derived map + merge delta
    python scripts/derive_tool_nodes.py --write     # merge new entries into tool_nodes.json
"""
from __future__ import annotations
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HANDLERS = REPO / "houdini_executor" / "handlers"
TOOL_NODES = REPO / "reference" / "tool_nodes.json"
CATALOG = REPO / "reference" / "catalog.json"

# func-name -> index of the positional arg that carries the nodetype string literal.
NAMED_CREATORS = {
    "child_after": 1,
    "_cop_gen": 0,
    "_stage_node": 0,
    # Labs wave-4 local ROP helpers (labs_gameengine.py): nodetype literal position.
    "_out_node": 0,          # _out_node(ntype, name=None) — /out Driver exporters
    "_node_in_parent": 1,    # _node_in_parent(anchor_path, ntype, name=None)
    # Labs wave-5 biome source/chain helper (labs_biome.py): nodetype literal position.
    "_source_or_chain": 1,   # _source_or_chain(params, ntype) — biome define/serialize/curve sources
    # Labs wave-6 Cop2 generator helper (labs_image.py): nodetype literal position.
    "_cop2_gen": 0,          # _cop2_gen(ntype, name=None) — Cop2 texture generators
}
ATTR_CREATORS = {
    "createNode": 0,
}


def _str_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _creator_ntype(call: ast.Call) -> str | None:
    """If `call` creates a node, return its nodetype string literal (else None)."""
    fn = call.func
    if isinstance(fn, ast.Name) and fn.id in NAMED_CREATORS:
        idx = NAMED_CREATORS[fn.id]
        if idx < len(call.args):
            return _str_literal(call.args[idx])
    elif isinstance(fn, ast.Attribute) and fn.attr in ATTR_CREATORS:
        idx = ATTR_CREATORS[fn.attr]
        if idx < len(call.args):
            return _str_literal(call.args[idx])
    return None


def _endpoint_name(fn: ast.FunctionDef) -> str | None:
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "endpoint":
            if dec.args:
                return _str_literal(dec.args[0])
    return None


def derive_file(path: Path) -> dict[str, str]:
    """tool -> primary nodetype for every @endpoint in one handler module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tool = _endpoint_name(fn)
        if tool is None:
            continue
        # first node-creating call in body order (by source position)
        best: tuple[int, int] | None = None
        best_nt: str | None = None
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                nt = _creator_ntype(node)
                if nt is None:
                    continue
                pos = (getattr(node, "lineno", 1 << 30), getattr(node, "col_offset", 1 << 30))
                if best is None or pos < best:
                    best, best_nt = pos, nt
        if best_nt is not None:
            out[tool] = best_nt
    return out


def derive_all() -> tuple[dict[str, str], set[str]]:
    """Returns (tool -> nodetype) and the set of tools defined in cops.py (category Cop)."""
    mapping: dict[str, str] = {}
    cop_tools: set[str] = set()
    for path in sorted(HANDLERS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        derived = derive_file(path)
        mapping.update(derived)
        if path.name == "cops.py":
            cop_tools.update(derived)
    return mapping, cop_tools


def main() -> int:
    write = "--write" in sys.argv
    derived, cop_tools = derive_all()

    tn = json.loads(TOOL_NODES.read_text(encoding="utf-8"))
    existing = tn.get("tools", {})

    catalog_names = {t["name"] for t in json.loads(CATALOG.read_text(encoding="utf-8"))["tools"]}

    added: dict[str, dict] = {}
    for tool, nt in sorted(derived.items()):
        if tool in existing:
            continue  # hand-maintained entry wins
        if tool not in catalog_names:
            continue  # only map real catalog tools
        entry: dict = {"nodes": [nt]}
        if tool in cop_tools:
            entry["category"] = "Cop"
        added[tool] = entry

    print(f"handlers scanned          : endpoints with a derivable nodetype = {len(derived)}")
    print(f"already present (kept)     : {len(set(derived) & set(existing))}")
    print(f"NEW entries to add         : {len(added)}  ({sum(1 for t in added if t in cop_tools)} COP)")
    still_absent = sorted(catalog_names - set(existing) - set(added))
    print(f"still absent after merge   : {len(still_absent)}")
    print(f"  residual (node-less)     : {still_absent}")

    if not write:
        print("\nDRY-RUN (no file written). Re-run with --write to merge.")
        return 0

    if not added:
        print("\nnothing to add — tool_nodes.json already covers every derivable tool.")
        return 0

    # Textual append: preserve every existing (hand-maintained) line byte-for-byte,
    # only inserting the new compact entries before the tools-object closing brace.
    new_lines: list[str] = []
    for tool, entry in added.items():
        nodes = json.dumps(entry["nodes"])
        if "category" in entry:
            new_lines.append(f'    "{tool}": {{ "nodes": {nodes}, "category": "{entry["category"]}" }}')
        else:
            new_lines.append(f'    "{tool}": {{ "nodes": {nodes} }}')

    stripped = TOOL_NODES.read_text(encoding="utf-8").rstrip()
    if not stripped.endswith("}"):
        sys.exit("tool_nodes.json: unexpected shape (no closing brace).")
    root_close = len(stripped) - 1
    j = root_close - 1
    while j >= 0 and stripped[j] in " \t\r\n":
        j -= 1
    if stripped[j] != "}":
        sys.exit("tool_nodes.json: could not locate the tools-object closing brace.")
    tools_close = j
    head = stripped[:tools_close].rstrip()  # ends with the last existing entry '}'
    result = head + ",\n" + ",\n".join(new_lines) + "\n  " + stripped[tools_close:] + "\n"

    # Validate the result parses and round-trips the additions before writing.
    check = json.loads(result)
    for tool, entry in added.items():
        assert check["tools"][tool] == entry, f"round-trip mismatch for {tool}"
    TOOL_NODES.write_text(result, encoding="utf-8")
    print(f"\nWROTE {TOOL_NODES}  (tools: {len(check['tools'])}, +{len(added)} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
